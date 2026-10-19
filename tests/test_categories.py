"""Configurable library names, native folder creation and reference integrity."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from library_core import (ImportErrorDetail, build_folder_plan, child, children, commit_plan,
                          dump, load_preferences, prop, read_tree, save_preferences)
from library_layout import DEFAULT_CATEGORIES, LibraryCategory, validate_categories
from loader_settings import LoaderSettings
import test_settings as fixtures


class CategoryTests(unittest.TestCase):
    setUp = fixtures.SettingsTests.setUp
    settings = fixtures.SettingsTests.settings

    def custom(self, **kwargs):
        settings = self.settings(**kwargs)
        return replace(settings, categories=(LibraryCategory("Analog", "MyLib_Analog", "Analog_Models"),)).validated(self.workspace)

    def import_plan(self, settings, mode="unpacked"):
        from library_core import associate, build_plan, scan
        inv = scan(self.workspace, "SamacSys", input_root=self.source)
        key = next(iter(inv.symbols))
        fp, model = associate(inv, inv.symbols[key])
        category = settings.categories[0]
        return build_plan(self.workspace, inv, key, fp, model, category.name, "Suggestion", symbol_format=mode,
                          output_root=settings.output_root, input_roots=settings.sources.values(),
                          model_path_mode=settings.model_path_mode, model_variable=settings.model_variable,
                          category_config=category)

    def test_old_preferences_keep_dvl_categories(self):
        settings = LoaderSettings.from_preferences(self.workspace, {"mode": "Suggestion"})
        self.assertEqual(settings.categories, DEFAULT_CATEGORIES)

    def test_category_preferences_round_trip(self):
        settings = self.custom()
        path = self.workspace / ".kicad-importer.json"
        save_preferences(path, {"paths": settings.to_preferences(), "categories": [c.to_preferences() for c in settings.categories]})
        self.assertEqual(LoaderSettings.from_preferences(self.workspace, load_preferences(path)), settings)

    def test_invalid_names_and_manually_typed_suffixes_are_rejected(self):
        for value in ("", " CON", "CON", "NUL.foo", "../escape", "a/b", "a:b", ".git", ".venv", "bad.", "a\n",
                      "MyLib.pretty", "MyLib.KICAD_SYMDIR", "MyLib.kicad_sym", "my.step"):
            for field in ("name", "library_name", "model_folder"):
                with self.subTest(value=value, field=field), self.assertRaises(ValueError):
                    replace(LibraryCategory("Analog", "MyLib", "Models"), **{field: value}).validated()

    def test_duplicate_fields_are_rejected_ignoring_case(self):
        first = LibraryCategory("Analog", "MyLib", "Models")
        for second in (LibraryCategory("ANALOG", "Other", "OtherModels"), LibraryCategory("Other", "MYLIB", "OtherModels"),
                       LibraryCategory("Other", "OtherLib", "MODELS")):
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                validate_categories((first, second))
        with self.assertRaisesRegex(ValueError, "at least one"):
            validate_categories(())

    def test_corrupt_saved_categories_do_not_silently_default(self):
        for raw in (None, [], {}, ["invalid"], [{"name": "Analog"}]):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                LoaderSettings.from_preferences(self.workspace, {"categories": raw})

    def test_unpacked_folder_preview_is_read_only_and_creation_is_idempotent(self):
        settings = self.custom()
        plan = build_folder_plan(self.workspace, settings, "unpacked")
        self.assertFalse(self.output.exists())
        self.assertFalse(plan.files)
        self.assertEqual(set(plan.folders), {self.output / "Symbols/MyLib_Analog.kicad_symdir",
                                           self.output / "Footprints/MyLib_Analog.pretty",
                                           self.output / "3DModels/Analog_Models"})
        commit_plan(self.output, plan)
        for folder in plan.folders:
            self.assertTrue(folder.is_dir())
            self.assertFalse(list(folder.iterdir()))
        commit_plan(self.output, build_folder_plan(self.workspace, settings, "unpacked"))
        self.assertFalse(list(self.output.rglob("*.kicad_sym")))

    def test_packed_preparation_creates_parent_folder_without_fake_symbol_directory(self):
        settings = self.custom()
        plan = build_folder_plan(self.workspace, settings, "packed")
        commit_plan(self.output, plan)
        self.assertTrue((self.output / "Symbols").is_dir())
        self.assertFalse((self.output / "Symbols/MyLib_Analog.kicad_sym").exists())
        self.assertFalse((self.output / "Symbols/MyLib_Analog.kicad_symdir").exists())
        commit_plan(self.output, self.import_plan(settings, "packed"))
        self.assertTrue((self.output / "Symbols/MyLib_Analog.kicad_sym").is_file())

    def test_custom_library_and_model_names_propagate_in_both_formats(self):
        settings = self.custom()
        before = {p.name: p.read_bytes() for p in self.source.iterdir()}
        for mode in ("unpacked", "packed"):
            commit_plan(self.output, build_folder_plan(self.workspace, settings, mode))
            commit_plan(self.output, self.import_plan(settings, mode))
            path = settings.categories[0].symbol_library(self.output, mode)
            if mode == "unpacked":
                path /= "TEST123.kicad_sym"
            symbol = children(read_tree(path), "symbol")[0]
            self.assertTrue(prop(symbol, "Footprint").startswith("MyLib_Analog:"))
        fp_path = next((self.output / "Footprints/MyLib_Analog.pretty").glob("*.kicad_mod"))
        self.assertTrue(child(read_tree(fp_path), "model")[1].startswith("${DVL_LIB_ROOT}/3DModels/Analog_Models/"))
        self.assertTrue(list((self.output / "3DModels/Analog_Models").glob("*.stp")))
        self.assertFalse((self.output / "Footprints/DVL_Analog.pretty").exists())
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.source.iterdir()})

    def test_absolute_model_reference_uses_custom_model_folder(self):
        settings = self.custom(model_path_mode="absolute")
        commit_plan(self.output, self.import_plan(settings))
        footprint = read_tree(next((self.output / "Footprints/MyLib_Analog.pretty").glob("*.kicad_mod")))
        self.assertTrue(Path(child(footprint, "model")[1]).is_relative_to(self.output / "3DModels/Analog_Models"))

    def test_existing_files_and_library_contents_are_preserved_during_preparation(self):
        settings = self.custom()
        commit_plan(self.output, self.import_plan(settings))
        before = {p: p.read_bytes() for p in self.output.rglob("*") if p.is_file()}
        commit_plan(self.output, build_folder_plan(self.workspace, settings, "unpacked"))
        self.assertEqual(before, {p: p.read_bytes() for p in self.output.rglob("*") if p.is_file()})

    def test_conflicting_file_blocks_preparation_before_creating_other_folders(self):
        settings = self.custom()
        self.output.mkdir()
        (self.output / "Footprints").mkdir()
        conflict = self.output / "Footprints/MyLib_Analog.pretty"
        conflict.write_bytes(b"not a folder")
        with self.assertRaisesRegex(ValueError, "file already exists"):
            build_folder_plan(self.workspace, settings, "unpacked")
        self.assertEqual(conflict.read_bytes(), b"not a folder")
        self.assertFalse((self.output / "Symbols").exists())

    def test_conflict_added_after_preview_blocks_creation(self):
        plan = build_folder_plan(self.workspace, self.custom(), "packed")
        self.output.mkdir()
        (self.output / "Footprints").mkdir()
        (self.output / "Footprints/MyLib_Analog.pretty").write_text("new conflicting file")
        with self.assertRaisesRegex(ValueError, "file already exists"):
            commit_plan(self.output, plan)
        self.assertFalse((self.output / "Symbols").exists())

    def test_existing_packed_library_is_validated_without_modification(self):
        settings = self.custom()
        path = self.output / "Symbols/MyLib_Analog.kicad_sym"
        path.parent.mkdir(parents=True)
        path.write_text("not a KiCad library")
        with self.assertRaises(ValueError):
            build_folder_plan(self.workspace, settings, "packed")
        self.assertEqual(path.read_text(), "not a KiCad library")

    def test_switching_category_layout_preserves_old_library_files(self):
        settings = self.custom()
        commit_plan(self.output, self.import_plan(settings))
        paths = {p: p.read_bytes() for p in self.output.rglob("*") if p.is_file()}
        changed = replace(settings, categories=(LibraryCategory("Other", "OtherLib", "OtherModels"),)).validated(self.workspace)
        commit_plan(self.output, self.import_plan(changed))
        self.assertEqual(paths, {p: p.read_bytes() for p in paths})
        self.assertTrue((self.output / "Symbols/OtherLib.kicad_symdir/TEST123.kicad_sym").exists())


if __name__ == "__main__":
    unittest.main()

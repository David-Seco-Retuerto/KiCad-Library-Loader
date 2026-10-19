"""Independent source/output roots and preservation of legacy preferences."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from library_core import (ImportErrorDetail, associate, build_plan, child, children,
                          commit_plan, load_preferences, prop, read_tree, save_preferences, scan)
from loader_settings import LoaderSettings
from providers import PROVIDERS
from test_importer import SYMBOL, FOOTPRINT, STEP


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.workspace = self.base / "application"
        self.workspace.mkdir()
        self.source = self.base / "exports" / "provider"
        self.source.mkdir(parents=True)
        self.other = self.base / "exports" / "unused-provider"
        self.output = self.base / "my-libraries"
        (self.source / "parts.kicad_sym").write_text(SYMBOL, encoding="utf-8")
        (self.source / "GEOM.kicad_mod").write_text(FOOTPRINT, encoding="utf-8")
        (self.source / "TEST123.stp").write_bytes(STEP)

    def settings(self, **kwargs):
        options = dict(sources={"SamacSys": self.source, "LCSC": self.other}, output_root=self.output)
        options.update(kwargs)
        return LoaderSettings(**options).validated(self.workspace)

    def plan(self, settings=None, symbol_format="unpacked"):
        settings = settings or self.settings()
        inv = scan(self.workspace, "SamacSys", input_root=settings.sources["SamacSys"])
        key = next(iter(inv.symbols))
        fp, model = associate(inv, inv.symbols[key])
        return build_plan(self.workspace, inv, key, fp, model, "ICs", "Suggestion", symbol_format=symbol_format,
                          output_root=settings.output_root, input_roots=settings.sources.values(),
                          model_path_mode=settings.model_path_mode, model_variable=settings.model_variable)

    def test_legacy_preferences_keep_legacy_paths(self):
        settings = LoaderSettings.from_preferences(self.workspace, {"mode": "Custom", "custom": "Previous_name"})
        self.assertEqual(settings.output_root, self.workspace)
        self.assertEqual(settings.sources["SamacSys"], self.workspace / "Imports/SamacSys")
        self.assertEqual(settings.model_path_mode, "variable")
        self.assertEqual(settings.model_variable, "DVL_LIB_ROOT")

    def test_independent_folders_and_preferences_round_trip(self):
        settings = self.settings(model_path_mode="absolute")
        path = self.workspace / ".kicad-importer.json"
        save_preferences(path, {"mode": "Custom", "paths": settings.to_preferences()})
        self.assertEqual(LoaderSettings.from_preferences(self.workspace, load_preferences(path)), settings)
        self.assertFalse(self.other.exists())
        self.assertFalse(self.output.exists())

    def test_relative_paths_are_based_on_workspace_not_current_directory(self):
        settings = LoaderSettings({"SamacSys": "../exports/provider", "LCSC": "../exports/unused-provider"}, "../my-libraries").validated(self.workspace)
        self.assertEqual(settings, self.settings())

    def test_new_output_root_in_both_formats_preserves_sources_and_workspace(self):
        before = {p.name: p.read_bytes() for p in self.source.iterdir()}
        for mode in ("unpacked", "packed"):
            with self.subTest(mode=mode):
                plan = self.plan(symbol_format=mode)
                self.assertTrue(all(p.is_relative_to(self.output) for p in plan.files))
                commit_plan(self.output, plan)
        self.assertTrue((self.output / "Symbols/DVL_ICs.kicad_sym").is_file())
        self.assertTrue((self.output / "Symbols/DVL_ICs.kicad_symdir/TEST123.kicad_sym").is_file())
        self.assertFalse((self.workspace / "Symbols").exists())
        self.assertFalse((self.workspace / ".kicad-importer.lock").exists())
        self.assertFalse((self.output / ".kicad-importer.lock").exists())
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.source.iterdir()})

    def test_absolute_model_path_points_to_copied_step(self):
        plan = self.plan(self.settings(model_path_mode="absolute"))
        commit_plan(self.output, plan)
        fp = read_tree(next((self.output / "Footprints/DVL_ICs.pretty").glob("*.kicad_mod")))
        path = Path(child(fp, "model")[1])
        self.assertTrue(path.is_absolute())
        self.assertTrue(path.is_relative_to(self.output))
        self.assertEqual(path.read_bytes(), STEP)
        symbol = children(read_tree(self.output / "Symbols/DVL_ICs.kicad_symdir/TEST123.kicad_sym"), "symbol")[0]
        self.assertEqual(prop(symbol, "Footprint").split(":")[0], "DVL_ICs")

    def test_custom_model_variable_and_existing_transforms_are_preserved(self):
        plan = self.plan(self.settings(model_variable="MY_LIBRARY_ROOT"))
        commit_plan(self.output, plan)
        fp = read_tree(next((self.output / "Footprints/DVL_ICs.pretty").glob("*.kicad_mod")))
        model = child(fp, "model")
        self.assertTrue(model[1].startswith("${MY_LIBRARY_ROOT}/3DModels/ICs/"))
        self.assertEqual(child(model, "offset"), child(child(read_tree(self.source / "GEOM.kicad_mod"), "model"), "offset"))
        self.assertTrue(any(f"MY_LIBRARY_ROOT = {self.output}" in item for item in plan.info))

    def test_output_root_mismatch_cannot_write_using_an_old_plan(self):
        plan = self.plan()
        with self.assertRaisesRegex(ImportErrorDetail, "output root changed"):
            commit_plan(self.workspace, plan)
        self.assertFalse(self.output.exists())

    def test_stale_temporary_file_is_not_deleted_on_failed_import(self):
        plan = self.plan()
        first = next(iter(plan.files))
        first.parent.mkdir(parents=True)
        stale = first.with_name(first.name + ".import-tmp")
        stale.write_bytes(b"left by an earlier interrupted import")
        with self.assertRaises(FileExistsError):
            commit_plan(self.output, plan)
        self.assertEqual(stale.read_bytes(), b"left by an earlier interrupted import")
        self.assertFalse(first.exists())
        self.assertFalse((self.output / ".kicad-importer.lock").exists())

    def test_overlapping_sources_and_output_assets_are_rejected(self):
        for root in (self.source, self.source / "nested-output", self.base / "exports"):
            # A sibling output below exports is valid; an ancestor is also valid
            # unless its asset subfolders actually overlap a source.
            if root == self.base / "exports":
                self.settings(output_root=root)
            else:
                with self.assertRaisesRegex(ValueError, "overlaps"):
                    self.settings(output_root=root)
        with self.assertRaisesRegex(ValueError, "overlaps"):
            self.settings(sources={"SamacSys": self.output / "Symbols" / "incoming", "LCSC": self.other})
        with self.assertRaisesRegex(ValueError, "overlaps"):
            self.settings(sources={"SamacSys": self.source, "LCSC": self.output / "Footprints" / "incoming"})
        with self.assertRaisesRegex(ValueError, "overlaps"):
            self.settings(output_root=self.workspace / "Imports" / "old-provider")

    def test_invalid_config_fields_do_not_fall_back_silently(self):
        for preferences in ({"paths": []}, {"paths": {"sources": []}}, {"paths": {"output_root": ""}},
                            {"paths": {"model_path_mode": []}}, {"paths": {"model_variable": "bad variable"}}):
            with self.subTest(preferences=preferences), self.assertRaises(ValueError):
                LoaderSettings.from_preferences(self.workspace, preferences)

    def test_files_and_metadata_are_not_valid_output_folders(self):
        for value in (self.source / "TEST123.stp", self.source / "TEST123.stp" / "nested", self.workspace / ".git" / "data"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.settings(output_root=value)

    def test_kicad_reserved_variables_rejected_but_unused_absolute_variable_ignored(self):
        for name in ("KIPRJMOD", "KICAD9_3DMODEL_DIR", "9BAD", "bad name"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.settings(model_variable=name)
        self.settings(model_path_mode="absolute", model_variable="bad name")

    def test_all_providers_use_the_same_native_scan_contract(self):
        for identifier, provider in PROVIDERS.items():
            inv = scan(self.workspace, identifier, input_root=self.source)
            self.assertEqual(inv.root, self.source)
            self.assertEqual(len(inv.symbols), 1)
            self.assertEqual(len(inv.footprints), 1)
            self.assertEqual(len(inv.models), 1)
        inv = scan(self.workspace, "LCSC", input_root=self.other)
        self.assertTrue(any("Folder not found" in message for message in inv.notices))
        self.assertFalse(self.other.exists())

    def test_symlinked_output_folder_cannot_escape_the_selected_root(self):
        self.output.mkdir()
        try:
            (self.output / "Symbols").symlink_to(self.source, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"Directory symlinks are not available: {exc}")
        with self.assertRaisesRegex(ValueError, "outside"):
            self.settings()


if __name__ == "__main__":
    unittest.main()

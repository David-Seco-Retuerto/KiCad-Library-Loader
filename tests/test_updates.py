"""Reviewed updates protect manual edits/shared assets and back up prior bytes."""
import json
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from component_updates import build_update_plan
from import_history import BACKUP_FOLDER, HISTORY_FOLDER, read_history
from import_gui import App
from library_core import (ImportErrorDetail, associate, build_plan, children, commit_plan, dump,
                          parse, read_tree, scan)
from test_importer import SYMBOL, FOOTPRINT, STEP


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.source = self.workspace / "Imports/SamacSys"
        self.source.mkdir(parents=True)
        self.symbol_file = self.source / "parts.kicad_sym"
        self.footprint_file = self.source / "GEOM.kicad_mod"
        self.model_file = self.source / "TEST123.stp"
        self.symbol_file.write_text(SYMBOL, encoding="utf-8")
        self.footprint_file.write_text(FOOTPRINT, encoding="utf-8")
        self.model_file.write_bytes(STEP)

    def build(self, builder=build_plan, mode="unpacked", **kwargs):
        inv = scan(self.workspace, "SamacSys")
        key = next(iter(inv.symbols))
        return builder(self.workspace, inv, key, "GEOM.kicad_mod", "TEST123.stp", "ICs", "Original", symbol_format=mode, **kwargs)

    def initial(self, mode="unpacked", **kwargs):
        commit_plan(self.workspace, self.build(mode=mode, **kwargs))

    def change(self, symbol=True, footprint=True, model=True):
        if symbol:
            self.symbol_file.write_text(SYMBOL.replace('"IN"', '"UPDATED_INPUT"'), encoding="utf-8")
        if footprint:
            self.footprint_file.write_text(FOOTPRINT.replace('(size 1 2)', '(size 1.2 2)'), encoding="utf-8")
        if model:
            self.model_file.write_bytes(STEP.replace(b"HEADER;", b"HEADER;\n/* revised */"))

    def test_updates_both_formats_with_exact_backups_and_new_history(self):
        for mode in ("unpacked", "packed"):
            with self.subTest(mode=mode):
                # Separate roots avoid creating two symbol formats sharing assets.
                root = self.workspace / mode
                root.mkdir()
                inv = scan(self.workspace, "SamacSys")
                key = next(iter(inv.symbols))
                initial = build_plan(self.workspace, inv, key, "GEOM.kicad_mod", "TEST123.stp", "ICs", "Original", symbol_format=mode, output_root=root)
                commit_plan(root, initial)
                before = {path: path.read_bytes() for path in initial.assets}
                self.change()
                inv = scan(self.workspace, "SamacSys")
                plan = build_update_plan(self.workspace, inv, next(iter(inv.symbols)), "GEOM.kicad_mod", "TEST123.stp", "ICs", symbol_format=mode, output_root=root)
                self.assertFalse((root / BACKUP_FOLDER).exists())
                self.assertEqual(set(plan.backup_files), set(before))
                commit_plan(root, plan)
                for path, data in before.items():
                    self.assertEqual((plan.backup_directory / path.relative_to(root)).read_bytes(), data)
                    self.assertNotEqual(path.read_bytes(), data)
                records, notices = read_history(root)
                self.assertFalse(notices)
                self.assertEqual(records[0]["operation"], "update")
                self.assertEqual(records[0]["previous_event_id"], records[1]["event_id"])
                self.assertEqual({item["action"] for item in records[0]["outputs"]}, {"updated"})
                self.assertTrue((plan.backup_directory / "manifest.json").is_file())
                self.symbol_file.write_text(SYMBOL, encoding="utf-8")
                self.footprint_file.write_text(FOOTPRINT, encoding="utf-8")
                self.model_file.write_bytes(STEP)

    def test_packed_update_preserves_other_symbols_after_recorded_append(self):
        self.initial("packed")
        self.symbol_file.write_text(SYMBOL.replace("TEST123", "NEXT456"), encoding="utf-8")
        commit_plan(self.workspace, self.build(mode="packed"))
        target = self.workspace / "Symbols/DVL_ICs.kicad_sym"
        previous = next(node for node in children(read_tree(target), "symbol") if node[1] == "NEXT456")
        self.change(footprint=False, model=False)
        plan = self.build(build_update_plan, "packed")
        commit_plan(self.workspace, plan)
        result = children(read_tree(target), "symbol")
        self.assertEqual(next(node for node in result if node[1] == "NEXT456"), previous)
        self.assertEqual(len(result), 2)

    def test_manual_edits_to_any_tracked_asset_are_blocked(self):
        self.initial()
        original = read_history(self.workspace)[0][0]
        self.change()
        for output in original["outputs"]:
            path = self.workspace / output["relative_path"]
            before = path.read_bytes()
            path.write_bytes(before + b"\n")
            with self.subTest(role=output["role"]), self.assertRaisesRegex(ImportErrorDetail, "edited"):
                self.build(build_update_plan)
            path.write_bytes(before)
        self.assertFalse((self.workspace / BACKUP_FOLDER).exists())

    def test_packed_manual_symbol_edit_is_detected_even_after_later_append(self):
        self.initial("packed")
        target = self.workspace / "Symbols/DVL_ICs.kicad_sym"
        target.write_text(target.read_text(encoding="utf-8").replace('"IN"', '"MANUAL_EDIT"'), encoding="utf-8")
        self.symbol_file.write_text(SYMBOL.replace("TEST123", "NEXT456"), encoding="utf-8")
        commit_plan(self.workspace, self.build(mode="packed"))
        self.change(footprint=False, model=False)
        with self.assertRaisesRegex(ImportErrorDetail, "manually edited"):
            self.build(build_update_plan, "packed")

    def test_older_packed_history_without_symbol_fingerprint_is_not_guessed(self):
        self.initial("packed")
        record = next((self.workspace / HISTORY_FOLDER).glob("*.json"))
        data = json.loads(record.read_text(encoding="utf-8"))
        data.pop("symbol_sha256")
        record.write_text(json.dumps(data), encoding="utf-8")
        self.symbol_file.write_text(SYMBOL.replace("TEST123", "NEXT456"), encoding="utf-8")
        commit_plan(self.workspace, self.build(mode="packed"))
        self.change(footprint=False, model=False)
        with self.assertRaisesRegex(ImportErrorDetail, "Older packed history"):
            self.build(build_update_plan, "packed")

    def test_shared_assets_from_history_are_blocked_but_symbol_only_change_is_allowed(self):
        self.initial()
        self.symbol_file.write_text(SYMBOL.replace("TEST123", "NEXT456"), encoding="utf-8")
        commit_plan(self.workspace, self.build())
        self.change()
        with self.assertRaisesRegex(ImportErrorDetail, "Shared assets"):
            self.build(build_update_plan)
        self.footprint_file.write_text(FOOTPRINT, encoding="utf-8")
        self.model_file.write_bytes(STEP)
        self.assertTrue(self.build(build_update_plan).files)

    def test_untracked_symbol_reference_blocks_shared_footprint_change(self):
        self.initial()
        folder = self.workspace / "Symbols/Other.kicad_symdir"
        folder.mkdir()
        (folder / "OTHER.kicad_sym").write_text(SYMBOL.replace("TEST123", "OTHER").replace("Vendor:GEOM", "DVL_ICs:GEOM"), encoding="utf-8")
        self.change(model=False)
        with self.assertRaisesRegex(ImportErrorDetail, "Another symbol references"):
            self.build(build_update_plan)

    def test_untracked_footprint_reference_blocks_shared_model_change(self):
        self.initial()
        folder = self.workspace / "Footprints/Other.pretty"
        folder.mkdir()
        (folder / "EXTRA.kicad_mod").write_text(FOOTPRINT.replace('C:\\\\vendor\\\\TEST123.stp', '${DVL_LIB_ROOT}/3DModels/ICs/GEOM.stp'), encoding="utf-8")
        self.change(footprint=False)
        # Make the external reference explicit without relying on string escaping.
        tree = read_tree(folder / "EXTRA.kicad_mod")
        children(tree, "model")[0][1] = "${DVL_LIB_ROOT}/3DModels/ICs/GEOM.stp"
        (folder / "EXTRA.kicad_mod").write_text(dump(tree), encoding="utf-8")
        with self.assertRaisesRegex(ImportErrorDetail, "Another footprint"):
            self.build(build_update_plan)

    def test_new_dependency_after_review_prevents_commit(self):
        self.initial()
        self.change(model=False)
        plan = self.build(build_update_plan)
        before = {path: path.read_bytes() for path in plan.assets}
        (self.workspace / "Symbols/late.kicad_sym").write_text(SYMBOL, encoding="utf-8")
        with self.assertRaisesRegex(ImportErrorDetail, "Dependency folder changed"):
            commit_plan(self.workspace, plan)
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertFalse((self.workspace / BACKUP_FOLDER).exists())

    def test_destination_edit_after_review_prevents_commit(self):
        self.initial()
        self.change()
        plan = self.build(build_update_plan)
        target = next(path for path, role in plan.assets.items() if role == "footprint")
        target.write_bytes(target.read_bytes() + b"\nmanual")
        with self.assertRaisesRegex(ImportErrorDetail, "Destination changed"):
            commit_plan(self.workspace, plan)
        self.assertTrue(target.read_bytes().endswith(b"manual"))
        self.assertFalse((self.workspace / BACKUP_FOLDER).exists())

    def test_backup_write_failure_leaves_originals_untouched(self):
        self.initial()
        self.change()
        plan = self.build(build_update_plan)
        before = {path: path.read_bytes() for path in plan.assets}
        original_open = Path.open
        def fail(path, *args, **kwargs):
            if BACKUP_FOLDER in path.parts and path.name.endswith(".import-tmp"):
                raise OSError("backup denied")
            return original_open(path, *args, **kwargs)
        with patch.object(Path, "open", fail), self.assertRaisesRegex(OSError, "backup denied"):
            commit_plan(self.workspace, plan)
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertEqual(len(read_history(self.workspace)[0]), 1)

    def test_history_failure_rolls_back_update_and_new_backups(self):
        self.initial()
        self.change()
        plan = self.build(build_update_plan)
        before = {path: path.read_bytes() for path in plan.assets}
        original_open = Path.open
        def fail(path, *args, **kwargs):
            if path.parent.name == HISTORY_FOLDER and path.name.endswith(".import-tmp"):
                raise OSError("history denied")
            return original_open(path, *args, **kwargs)
        with patch.object(Path, "open", fail), self.assertRaisesRegex(OSError, "history denied"):
            commit_plan(self.workspace, plan)
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertEqual(len(read_history(self.workspace)[0]), 1)
        self.assertFalse([path for path in (self.workspace / BACKUP_FOLDER).rglob("*") if path.is_file()])

    def test_no_change_untracked_category_and_missing_assets_are_explicit(self):
        with self.assertRaisesRegex(ImportErrorDetail, "No matching import history"):
            self.build(build_update_plan)
        self.initial()
        with self.assertRaisesRegex(ImportErrorDetail, "No component changes"):
            self.build(build_update_plan)
        self.change()
        model = self.workspace / "3DModels/ICs/GEOM.stp"
        model.unlink()
        with self.assertRaisesRegex(ImportErrorDetail, "is missing"):
            self.build(build_update_plan)

    def test_absolute_model_paths_do_not_leak_staging_directory(self):
        self.initial(model_path_mode="absolute")
        self.change()
        plan = self.build(build_update_plan, model_path_mode="absolute")
        footprint = next(data for path, data in plan.files.items() if path.suffix == ".kicad_mod")
        self.assertNotIn(b"kicad-update-plan-", footprint)
        self.assertIn((self.workspace / "3DModels/ICs/GEOM.stp").as_posix().encode(), footprint)

    def test_names_are_preserved_even_when_source_geometry_name_changes(self):
        self.initial()
        self.change()
        self.footprint_file.write_text(self.footprint_file.read_text(encoding="utf-8").replace('"GEOM"', '"NEW_GEOMETRY"'), encoding="utf-8")
        plan = self.build(build_update_plan)
        self.assertTrue(any(path.name == "GEOM.kicad_mod" for path in plan.files))
        self.assertFalse(any("NEW_GEOMETRY" in path.name for path in plan.files))

    def test_gui_requires_confirmation_and_rechecks_source_before_apply(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        root.withdraw()
        try:
            app = App(root, self.workspace)
            app.mode.set("Original")
            app.validate()
            app.ack.set(True)
            app.import_component()
            self.change()
            dialog = app.review_update()
            self.assertIsNotNone(dialog)
            self.assertFalse(dialog.apply())
            self.assertFalse((self.workspace / BACKUP_FOLDER).exists())
            self.footprint_file.write_text(FOOTPRINT.replace('(size 1 2)', '(size 1.4 2)'), encoding="utf-8")
            dialog.reviewed.set(True)
            with patch("update_dialog.messagebox.showinfo") as notice:
                self.assertFalse(dialog.apply())
                notice.assert_called_once()
            self.assertFalse(dialog.reviewed.get())
            self.assertFalse((self.workspace / BACKUP_FOLDER).exists())
            dialog.reviewed.set(True)
            self.assertTrue(dialog.apply())
            self.assertEqual(read_history(self.workspace)[0][0]["operation"], "update")
            self.assertIn("Component updated", app.log.get("1.0", "end"))
        finally:
            root.destroy()

    def test_current_source_mpn_change_is_blocked_even_without_refresh(self):
        self.initial()
        inv = scan(self.workspace, "SamacSys")
        changed = SYMBOL.replace('(property "Manufacturer_Part_Number" "TEST123")', '(property "Manufacturer_Part_Number" "DIFFERENT_PART")')
        self.symbol_file.write_text(changed, encoding="utf-8")
        with self.assertRaisesRegex(ImportErrorDetail, "current source MPN"):
            build_update_plan(self.workspace, inv, next(iter(inv.symbols)), "GEOM.kicad_mod", "TEST123.stp", "ICs")

    def test_counterpart_format_sharing_changed_assets_is_blocked(self):
        self.initial()
        self.initial("packed")
        self.change()
        with self.assertRaisesRegex(ImportErrorDetail, "another component or symbol format"):
            self.build(build_update_plan)

    def test_asset_removal_and_category_migration_are_not_silent_updates(self):
        self.initial()
        self.change()
        inv = scan(self.workspace, "SamacSys")
        key = next(iter(inv.symbols))
        with self.assertRaisesRegex(ImportErrorDetail, "retain the existing"):
            build_update_plan(self.workspace, inv, key, "GEOM.kicad_mod", "", "ICs")
        with self.assertRaisesRegex(ImportErrorDetail, "No matching import history"):
            build_update_plan(self.workspace, inv, key, "GEOM.kicad_mod", "TEST123.stp", "Power")

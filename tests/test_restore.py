"""Restoration preserves other components and refuses unverifiable state."""
import json
from pathlib import Path
import sys
import tkinter as tk
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from component_restore import build_restore_plan
from component_updates import build_update_plan
from import_gui import App
from import_history import BACKUP_FOLDER, HISTORY_FOLDER, read_history
from library_core import ImportErrorDetail, Plan, build_plan, children, commit_plan, read_tree, scan
from test_importer import SYMBOL, FOOTPRINT, STEP
import test_updates as update_fixtures


class RestoreTests(unittest.TestCase):
    setUp = update_fixtures.UpdateTests.setUp
    build = update_fixtures.UpdateTests.build
    initial = update_fixtures.UpdateTests.initial
    change = update_fixtures.UpdateTests.change

    def updated(self, mode="unpacked", **kwargs):
        self.initial(mode)
        original = {
            self.workspace / item["relative_path"]: (self.workspace / item["relative_path"]).read_bytes()
            for item in read_history(self.workspace)[0][0]["outputs"]}
        self.change(**kwargs)
        update = self.build(build_update_plan, mode)
        commit_plan(self.workspace, update)
        record = read_history(self.workspace)[0][0]
        return original, update, record

    def restore(self, record, **kwargs):
        return build_restore_plan(self.workspace, record["event_id"], **kwargs)

    def test_exact_restore_in_both_formats_with_recovery_backup_and_linked_history(self):
        for mode in ("unpacked", "packed"):
            # Independent categories/output roots avoid shared assets between formats.
            with self.subTest(mode=mode):
                self.setUp()
                self.initial(mode)
                original = {self.workspace / item["relative_path"]: (self.workspace / item["relative_path"]).read_bytes()
                            for item in read_history(self.workspace)[0][0]["outputs"]}
                self.change()
                update = self.build(build_update_plan, mode)
                commit_plan(self.workspace, update)
                record = read_history(self.workspace)[0][0]
                updated = {path: path.read_bytes() for path in original}
                plan = self.restore(record)
                self.assertEqual({path: path.read_bytes() for path in original}, updated)
                commit_plan(self.workspace, plan)
                self.assertEqual({path: path.read_bytes() for path in original}, original)
                for path, data in updated.items():
                    self.assertEqual((plan.backup_directory / path.relative_to(self.workspace)).read_bytes(), data)
                history, notices = read_history(self.workspace)
                self.assertFalse(notices)
                self.assertEqual(history[0]["operation"], "restore")
                self.assertEqual(history[0]["reverted_event_id"], record["event_id"])
                self.assertEqual(history[0]["restored_from_event_id"], record["previous_event_id"])
                self.assertEqual(json.loads((plan.backup_directory / "manifest.json").read_text())["operation"], "restore")
                with self.assertRaisesRegex(ImportErrorDetail, "later recorded"):
                    self.restore(record)

    def test_packed_restore_preserves_symbols_appended_after_the_update(self):
        self.initial("packed")
        self.change(footprint=False, model=False)
        update = self.build(build_update_plan, "packed")
        commit_plan(self.workspace, update)
        record = read_history(self.workspace)[0][0]
        self.symbol_file.write_text(SYMBOL.replace("TEST123", "OTHER456"), encoding="utf-8")
        inventory = scan(self.workspace, "SamacSys")
        later = build_plan(self.workspace, inventory, next(iter(inventory.symbols)), "", "", "ICs", "Original", symbol_format="packed")
        commit_plan(self.workspace, later)
        path = next(path for path, role in update.assets.items() if role == "symbol")
        other = next(node for node in children(read_tree(path), "symbol") if node[1] == "OTHER456")
        plan = self.restore(record)
        commit_plan(self.workspace, plan)
        nodes = children(read_tree(path), "symbol")
        self.assertEqual(len(nodes), 2)
        self.assertEqual(next(node for node in nodes if node[1] == "OTHER456"), other)
        self.assertNotIn("UPDATED_INPUT", path.read_text(encoding="utf-8"))

    def test_manual_edits_missing_outputs_and_modified_backup_are_blocked(self):
        original, update, record = self.updated()
        for path in original:
            data = path.read_bytes()
            path.write_bytes(data + b"\n")
            with self.assertRaisesRegex(ImportErrorDetail, "edited"):
                self.restore(record)
            path.unlink()
            with self.assertRaisesRegex(ImportErrorDetail, "Missing"):
                self.restore(record)
            path.write_bytes(data)
            backup = update.backup_directory / path.relative_to(self.workspace)
            data = backup.read_bytes()
            backup.write_bytes(data + b"tamper")
            with self.assertRaisesRegex(ImportErrorDetail, "hashes"):
                self.restore(record)
            backup.write_bytes(data)

    def test_manifest_mismatch_unsafe_paths_and_corrupt_history_are_blocked(self):
        _, update, record = self.updated()
        manifest = update.backup_directory / "manifest.json"
        original = manifest.read_bytes()
        data = json.loads(original)
        data["files"][0]["relative_path"] = "../outside.kicad_sym"
        manifest.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ImportErrorDetail, "unsafe"):
            self.restore(record)
        data = json.loads(original)
        data["previous_event_id"] = "unrelated"
        manifest.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ImportErrorDetail, "does not match"):
            self.restore(record)
        manifest.unlink()
        with self.assertRaisesRegex(ImportErrorDetail, "manifest is missing"):
            self.restore(record)
        manifest.write_bytes(original)
        (self.workspace / HISTORY_FOLDER / "broken.json").write_text("{broken", encoding="utf-8")
        with self.assertRaisesRegex(ImportErrorDetail, "History could not"):
            self.restore(record)

    def test_initial_import_and_older_update_cannot_be_restored(self):
        self.initial()
        initial = read_history(self.workspace)[0][0]
        with self.assertRaisesRegex(ImportErrorDetail, "Select a recorded"):
            self.restore(initial)
        self.change()
        commit_plan(self.workspace, self.build(build_update_plan))
        first_update = read_history(self.workspace)[0][0]
        self.symbol_file.write_text(SYMBOL.replace('"IN"', '"LATEST"'), encoding="utf-8")
        commit_plan(self.workspace, self.build(build_update_plan))
        with self.assertRaisesRegex(ImportErrorDetail, "later recorded"):
            self.restore(first_update)

    def test_dependency_changes_after_review_block_commit(self):
        original, _, record = self.updated()
        plan = self.restore(record)
        before = {path: path.read_bytes() for path in original}
        (self.workspace / "Symbols/late.kicad_sym").write_text(SYMBOL, encoding="utf-8")
        with self.assertRaisesRegex(ImportErrorDetail, "Dependency folder changed"):
            commit_plan(self.workspace, plan)
        self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_backup_changes_after_review_block_commit(self):
        original, update, record = self.updated()
        plan = self.restore(record)
        before = {path: path.read_bytes() for path in original}
        backup = next(path for path in plan.before if update.backup_directory in path.parents and path.name != "manifest.json")
        backup.write_bytes(backup.read_bytes() + b"changed after review")
        with self.assertRaisesRegex(ImportErrorDetail, "Destination changed"):
            commit_plan(self.workspace, plan)
        self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_shared_untracked_reference_blocks_asset_restoration(self):
        _, _, record = self.updated()
        folder = self.workspace / "Symbols/Other.kicad_symdir"
        folder.mkdir()
        (folder / "OTHER.kicad_sym").write_text(SYMBOL.replace("TEST123", "OTHER").replace("Vendor:GEOM", "DVL_ICs:GEOM"), encoding="utf-8")
        with self.assertRaisesRegex(ImportErrorDetail, "Another symbol references"):
            self.restore(record)

    def test_failed_backup_or_history_write_rolls_back_restoration(self):
        original, _, record = self.updated()
        before = {path: path.read_bytes() for path in original}
        history_before = {p: p.read_bytes() for p in (self.workspace / HISTORY_FOLDER).glob("*.json")}
        backups_before = set(p for p in (self.workspace / BACKUP_FOLDER).rglob("*") if p.is_file())
        real_open = Path.open
        for failure in ("backup", "history"):
            plan = self.restore(record)
            def fail(path, *args, **kwargs):
                if path.name.endswith(".import-tmp") and ((failure == "backup" and BACKUP_FOLDER in path.parts)
                        or (failure == "history" and HISTORY_FOLDER in path.parts)):
                    raise OSError("simulated write failure")
                return real_open(path, *args, **kwargs)
            with patch.object(Path, "open", fail), self.assertRaisesRegex(OSError, "simulated"):
                commit_plan(self.workspace, plan)
            self.assertEqual({path: path.read_bytes() for path in before}, before)
            self.assertEqual({p: p.read_bytes() for p in history_before}, history_before)
            self.assertEqual(set(p for p in (self.workspace / BACKUP_FOLDER).rglob("*") if p.is_file()), backups_before)

    def test_restoration_uses_backups_when_source_exports_are_gone_and_protects_inputs(self):
        original, _, record = self.updated()
        for path in self.source.iterdir():
            path.unlink()
        with self.assertRaisesRegex(ImportErrorDetail, "inside an input"):
            self.restore(record, protected_roots=(self.workspace / BACKUP_FOLDER,))
        commit_plan(self.workspace, self.restore(record))
        self.assertEqual({path: path.read_bytes() for path in original}, original)

    def test_update_after_restoration_is_supported(self):
        _, _, record = self.updated()
        commit_plan(self.workspace, self.restore(record))
        commit_plan(self.workspace, self.build(build_update_plan))
        second_update = read_history(self.workspace)[0][0]
        commit_plan(self.workspace, self.restore(second_update))
        self.assertEqual(read_history(self.workspace)[0][0]["operation"], "restore")

    def test_gui_requires_confirmation_rechecks_and_invalidates_main_plan(self):
        _, _, record = self.updated()
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        root.withdraw()
        try:
            app = App(root, self.workspace)
            history = app.open_history()
            dialog = history.restore_selected()
            self.assertIsNotNone(dialog)
            self.assertTrue(dialog.restoring)
            self.assertFalse(dialog.apply())
            path = next(path for path, role in dialog.plan.assets.items() if role == "footprint")
            saved = path.read_bytes()
            path.write_bytes(saved + b"manual")
            dialog.reviewed.set(True)
            with patch("update_dialog.messagebox.showerror") as error:
                self.assertFalse(dialog.apply())
                error.assert_called_once()
            self.assertFalse(dialog.reviewed.get())
            path.write_bytes(saved)
            app.plan = Plan()
            app.ack.set(True)
            dialog.reviewed.set(True)
            self.assertTrue(dialog.apply())
            self.assertIsNone(app.plan)
            self.assertFalse(app.ack.get())
            self.assertIn("Component restored", app.log.get("1.0", "end"))
            self.assertEqual(str(history.restore_button["state"]), "disabled")
            self.assertEqual(read_history(self.workspace)[0][0]["reverted_event_id"], record["event_id"])
        finally:
            root.destroy()

    def test_symbol_only_and_footprint_only_updates_restore_without_missing_backups(self):
        for mode in ("unpacked", "packed"):
            for changed_role in ("symbol", "footprint"):
                with self.subTest(mode=mode, changed_role=changed_role):
                    self.setUp()
                    self.initial(mode)
                    initial = read_history(self.workspace)[0][0]
                    original = {self.workspace / item["relative_path"]: (self.workspace / item["relative_path"]).read_bytes()
                                for item in initial["outputs"]}
                    self.change(symbol=changed_role == "symbol", footprint=changed_role == "footprint", model=False)
                    update = self.build(build_update_plan, mode)
                    commit_plan(self.workspace, update)
                    record = read_history(self.workspace)[0][0]
                    plan = self.restore(record)
                    self.assertEqual(set(plan.backup_files), {path for path, role in plan.assets.items() if role == changed_role})
                    commit_plan(self.workspace, plan)
                    self.assertEqual({path: path.read_bytes() for path in original}, original)

    def test_packed_manual_target_edit_is_blocked_even_after_recorded_append(self):
        _, update, record = self.updated("packed")
        symbol = next(path for path, role in update.assets.items() if role == "symbol")
        symbol.write_text(symbol.read_text(encoding="utf-8").replace("UPDATED_INPUT", "MANUAL"), encoding="utf-8")
        self.symbol_file.write_text(SYMBOL.replace("TEST123", "OTHER456"), encoding="utf-8")
        inventory = scan(self.workspace, "SamacSys")
        commit_plan(self.workspace, build_plan(self.workspace, inventory, next(iter(inventory.symbols)), "", "", "ICs", "Original", symbol_format="packed"))
        with self.assertRaisesRegex(ImportErrorDetail, "manually edited"):
            self.restore(record)

    def test_archive_provenance_is_preserved_without_reopening_source_archive(self):
        origin = self.source / ".loader-archive-origin.json"
        original_origin = {"archive_path": "original.zip", "archive_sha256": "a" * 64}
        origin.write_text(json.dumps(original_origin), encoding="utf-8")
        _, _, record = self.updated()
        origin.write_text(json.dumps({"archive_path": "replacement.zip", "archive_sha256": "b" * 64}), encoding="utf-8")
        commit_plan(self.workspace, self.restore(record))
        restored = read_history(self.workspace)[0][0]
        self.assertEqual(restored["source_archive"], original_origin)

    def test_gui_packed_append_invalidates_confirmation_and_refreshes_review(self):
        _, _, record = self.updated("packed")
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        root.withdraw()
        try:
            history = App(root, self.workspace).open_history()
            dialog = history.restore_selected()
            self.symbol_file.write_text(SYMBOL.replace("TEST123", "OTHER456"), encoding="utf-8")
            inventory = scan(self.workspace, "SamacSys")
            commit_plan(self.workspace, build_plan(self.workspace, inventory, next(iter(inventory.symbols)), "", "", "ICs", "Original", symbol_format="packed"))
            dialog.reviewed.set(True)
            with patch("update_dialog.messagebox.showinfo") as notice:
                self.assertFalse(dialog.apply())
                notice.assert_called_once()
            self.assertFalse(dialog.reviewed.get())
            self.assertEqual(read_history(self.workspace)[0][0]["symbol"], "OTHER456")
            dialog.reviewed.set(True)
            self.assertTrue(dialog.apply())
            symbol = next(path for path, role in dialog.plan.assets.items() if role == "symbol")
            self.assertEqual(len(children(read_tree(symbol), "symbol")), 2)
        finally:
            root.destroy()

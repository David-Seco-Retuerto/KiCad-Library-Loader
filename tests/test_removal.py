"""Synthetic removal/recovery regressions; all writes stay in temporary libraries."""
import json
from pathlib import Path
import sys
import tkinter as tk
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from component_remove import build_remove_plan, build_recover_plan
from component_move import build_move_plan
from component_restore import build_restore_plan
from component_updates import build_update_plan
from import_gui import App
from import_history import BACKUP_FOLDER, HISTORY_FOLDER, ORIGIN_FILE, current_components, component_identity, read_history
from library_core import ImportErrorDetail, build_plan, children, commit_plan, dump, parse, read_tree, scan
from library_layout import DEFAULT_CATEGORIES
from test_importer import SYMBOL, FOOTPRINT
import test_updates as fixtures


class RemovalTests(unittest.TestCase):
    setUp = fixtures.UpdateTests.setUp
    build = fixtures.UpdateTests.build
    initial = fixtures.UpdateTests.initial
    change = fixtures.UpdateTests.change

    def record(self):
        return read_history(self.workspace)[0][0]

    def remove(self, record=None, **kwargs):
        return build_remove_plan(self.workspace, (record or self.record())["event_id"], **kwargs)

    def recover(self, record=None, **kwargs):
        return build_recover_plan(self.workspace, (record or self.record())["event_id"], **kwargs)

    def files(self):
        return {p: p.read_bytes() for p in self.workspace.rglob("*") if p.is_file()}

    def import_sibling(self, mode="packed", name="OTHER"):
        self.symbol_file.write_text(SYMBOL.replace("TEST123", name), encoding="utf-8")
        commit_plan(self.workspace, self.build(mode=mode))

    def test_remove_and_recover_both_native_formats_exact_assets_and_tombstone(self):
        for mode in ("packed", "unpacked"):
            with self.subTest(mode=mode):
                self.setUp()
                self.initial(mode)
                original = self.record()
                before = {self.workspace / o["relative_path"]: (self.workspace / o["relative_path"]).read_bytes() for o in original["outputs"]}
                source = {p: p.read_bytes() for p in self.source.iterdir()}
                plan = self.remove()
                self.assertFalse((self.workspace / BACKUP_FOLDER).exists())
                commit_plan(self.workspace, plan)
                removed = self.record()
                self.assertEqual(removed["operation"], "remove")
                self.assertEqual(removed["outputs"], [])
                self.assertIsNone(current_components(read_history(self.workspace)[0])[component_identity(original)])
                for p, data in before.items():
                    self.assertEqual((plan.backup_directory / p.relative_to(self.workspace)).read_bytes(), data)
                    if mode == "packed" and p.suffix == ".kicad_sym":
                        self.assertFalse(children(read_tree(p), "symbol"))
                    else:
                        self.assertFalse(p.exists())
                recovered = self.recover()
                commit_plan(self.workspace, recovered)
                for p, data in before.items():
                    self.assertEqual(p.read_bytes(), data)
                self.assertEqual(self.record()["operation"], "recover")
                self.assertEqual(current_components(read_history(self.workspace)[0])[component_identity(original)]["event_id"], self.record()["event_id"])
                self.assertEqual({p: p.read_bytes() for p in source}, source)

    def test_packed_sibling_and_later_append_preserved_on_recovery(self):
        self.initial("packed")
        original = self.record()
        self.import_sibling()
        sibling = self.record()
        plan = self.remove(original)
        self.assertEqual(set(plan.removals), set())  # Shared footprint/model stay.
        commit_plan(self.workspace, plan)
        removed = self.record()
        library = self.workspace / "Symbols/DVL_ICs.kicad_sym"
        self.assertEqual([n[1] for n in children(read_tree(library), "symbol")], ["OTHER"])
        self.import_sibling(name="LATER")
        prior_recovery = library.read_bytes()
        recovery = self.recover(removed)
        commit_plan(self.workspace, recovery)
        self.assertEqual({n[1] for n in children(read_tree(library), "symbol")}, {"OTHER", "LATER", "TEST123"})
        self.assertEqual((recovery.backup_directory / library.relative_to(self.workspace)).read_bytes(), prior_recovery)
        self.symbol_file.write_text(SYMBOL.replace("TEST123", "OTHER").replace('"IN"', '"NEW_IN"'), encoding="utf-8")
        update = self.build(build_update_plan, mode="packed")
        commit_plan(self.workspace, update)
        commit_plan(self.workspace, build_restore_plan(self.workspace, self.record()["event_id"]))
        self.assertEqual({n[1] for n in children(read_tree(library), "symbol")}, {"OTHER", "LATER", "TEST123"})

    def test_untracked_symbol_and_model_references_retain_shared_assets(self):
        self.initial()
        folder = self.workspace / "Symbols/Unknown.kicad_symdir"
        folder.mkdir()
        other = folder / "OTHER.kicad_sym"
        other.write_text(SYMBOL.replace("TEST123", "OTHER").replace("Vendor:GEOM", "DVL_ICs:GEOM"), encoding="utf-8")
        plan = self.remove()
        self.assertEqual({p.suffix for p in plan.removals}, {".kicad_sym"})
        commit_plan(self.workspace, plan)
        self.assertTrue((self.workspace / "Footprints/DVL_ICs.pretty/GEOM.kicad_mod").exists())
        commit_plan(self.workspace, self.recover())
        other.unlink()
        fp_folder = self.workspace / "Footprints/Unknown.pretty"
        fp_folder.mkdir()
        (fp_folder / "OTHER.kicad_mod").write_text(FOOTPRINT.replace('"TEST123.stp"', '"${DVL_LIB_ROOT}/3DModels/ICs/GEOM.stp"'), encoding="utf-8")
        # Use the actual recorded reference, independent of fixture spelling.
        tree = read_tree(fp_folder / "OTHER.kicad_mod")
        children(tree, "model")[0][1] = "${DVL_LIB_ROOT}/3DModels/ICs/GEOM.stp"
        (fp_folder / "OTHER.kicad_mod").write_text(dump(tree), encoding="utf-8")
        plan = self.remove()
        self.assertEqual({p.suffix for p in plan.removals}, {".kicad_sym", ".kicad_mod"})
        commit_plan(self.workspace, plan)
        self.assertTrue((self.workspace / "3DModels/ICs/GEOM.stp").exists())
        commit_plan(self.workspace, self.recover())

    def test_missing_or_manually_changed_assets_block_removal(self):
        self.initial()
        original = self.record()
        for item in original["outputs"]:
            p = self.workspace / item["relative_path"]
            data = p.read_bytes()
            p.write_bytes(data + b"\n")
            with self.assertRaises(ImportErrorDetail):
                self.remove(original)
            p.unlink()
            with self.assertRaises(ImportErrorDetail):
                self.remove(original)
            p.write_bytes(data)

    def test_inherited_dependants_and_unreadable_references_block_removal(self):
        self.initial("packed")
        p = self.workspace / "Symbols/OTHER.kicad_sym"
        p.write_text('(kicad_symbol_lib (version 20220914) (symbol "OTHER" (extends "DVL_ICs:TEST123")))', encoding="utf-8")
        with self.assertRaisesRegex(ImportErrorDetail, "inherits"):
            self.remove()
        p.write_text("broken", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.remove()

    def test_dependency_and_history_changes_after_removal_review_block_commit(self):
        self.initial()
        plan = self.remove()
        p = self.workspace / "Symbols/new.kicad_sym"
        p.write_text(SYMBOL, encoding="utf-8")
        with self.assertRaisesRegex(ImportErrorDetail, "Dependency folder changed"):
            commit_plan(self.workspace, plan)
        p.unlink()
        plan = self.remove()
        record_path = Path(self.record()["record_path"])
        record_path.write_bytes(record_path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ImportErrorDetail, "Destination changed"):
            commit_plan(self.workspace, plan)

    def test_removal_deletion_failure_rolls_back_assets_history_and_backups(self):
        self.initial()
        before = self.files()
        plan = self.remove()
        target = next(p for p in plan.removals if p.suffix == ".stp")
        unlink = Path.unlink
        def fail(path, *args, **kwargs):
            if path == target:
                raise OSError("simulated deletion failure")
            return unlink(path, *args, **kwargs)
        with patch.object(Path, "unlink", fail), self.assertRaisesRegex(OSError, "deletion"):
            commit_plan(self.workspace, plan)
        self.assertEqual(self.files(), before)

    def test_removal_backup_and_history_write_failures_rollback(self):
        self.initial("packed")
        before = self.files()
        open_file = Path.open
        for failure in (BACKUP_FOLDER, HISTORY_FOLDER):
            plan = self.remove()
            def fail(path, *args, **kwargs):
                if failure in path.parts and path.name.endswith(".import-tmp"):
                    raise OSError("simulated write failure")
                return open_file(path, *args, **kwargs)
            with patch.object(Path, "open", fail), self.assertRaisesRegex(OSError, "write failure"):
                commit_plan(self.workspace, plan)
            self.assertEqual(self.files(), before)

    def test_recovery_rejects_changed_or_missing_backups_and_manifest(self):
        self.initial()
        plan = self.remove()
        commit_plan(self.workspace, plan)
        for path in plan.backup_directory.rglob("*"):
            if not path.is_file():
                continue
            data = path.read_bytes()
            path.write_bytes(data + (b"broken" if path.name == "manifest.json" else b"\n"))
            with self.subTest(file=path.name), self.assertRaises(ValueError):
                self.recover()
            path.unlink()
            with self.assertRaises(ValueError):
                self.recover()
            path.write_bytes(data)

    def test_recovery_asset_collisions_and_duplicate_unpacked_names_block_without_writes(self):
        self.initial()
        original = self.record()
        commit_plan(self.workspace, self.remove())
        removed = self.record()
        for item in original["outputs"]:
            p = self.workspace / item["relative_path"]
            p.write_text("different", encoding="utf-8")
            before = self.files()
            with self.assertRaises(ValueError):
                self.recover(removed)
            self.assertEqual(self.files(), before)
            p.unlink()
        other = self.workspace / "Symbols/DVL_ICs.kicad_symdir/different-name.kicad_sym"
        other.write_text(SYMBOL, encoding="utf-8")
        with self.assertRaisesRegex(ImportErrorDetail, "already contains"):
            self.recover(removed)

    def test_identical_recreated_assets_reused_but_shared_edits_block_recovery(self):
        self.initial("packed")
        original = self.record()
        self.import_sibling()
        commit_plan(self.workspace, self.remove(original))
        removed = self.record()
        fp = self.workspace / "Footprints/DVL_ICs.pretty/GEOM.kicad_mod"
        data = fp.read_bytes()
        fp.write_bytes(data + b"\n")
        with self.assertRaisesRegex(ImportErrorDetail, "retained shared"):
            self.recover(removed)
        fp.write_bytes(data)
        commit_plan(self.workspace, self.recover(removed))
        # With no sharing, byte-identical assets recreated after removal can be reused.
        self.setUp(); self.initial()
        original = self.record()
        saved = {self.workspace / o["relative_path"]: (self.workspace / o["relative_path"]).read_bytes() for o in original["outputs"] if o["role"] != "symbol"}
        commit_plan(self.workspace, self.remove())
        for p, data in saved.items():
            p.write_bytes(data)
        recovery = self.recover()
        self.assertTrue(all(p not in recovery.files for p in saved))
        commit_plan(self.workspace, recovery)

    def test_recovered_or_reimported_components_and_old_records_cannot_recover_again(self):
        self.initial()
        original = self.record()
        commit_plan(self.workspace, self.remove())
        removed = self.record()
        with self.assertRaises(ImportErrorDetail):
            self.remove(original)
        with self.assertRaises(ImportErrorDetail):
            self.build(build_update_plan)
        commit_plan(self.workspace, self.recover())
        with self.assertRaisesRegex(ImportErrorDetail, "later operation"):
            self.recover(removed)
        commit_plan(self.workspace, self.remove())
        removed = self.record()
        commit_plan(self.workspace, self.build())
        with self.assertRaisesRegex(ImportErrorDetail, "later operation"):
            self.recover(removed)

    def test_recovery_races_and_write_failures_rollback(self):
        self.initial("packed")
        commit_plan(self.workspace, self.remove())
        removed = self.record()
        before = self.files()
        recovery = self.recover()
        backup = next(p for p in recovery.before if BACKUP_FOLDER in p.parts and p.suffix == ".stp")
        data = backup.read_bytes()
        backup.write_bytes(data + b"\n")
        with self.assertRaisesRegex(ImportErrorDetail, "Destination changed"):
            commit_plan(self.workspace, recovery)
        backup.write_bytes(data)
        open_file = Path.open
        for failure in ("backup", "asset", "history"):
            recovery = self.recover(removed)
            def fail(path, *args, **kwargs):
                if path.name.endswith(".import-tmp") and (
                    (failure == "backup" and BACKUP_FOLDER in path.parts and recovery.backup_directory and recovery.backup_directory in path.parents)
                    or (failure == "asset" and path.suffix == ".import-tmp" and path.parent.name == "ICs")
                    or (failure == "history" and HISTORY_FOLDER in path.parts)):
                    raise OSError("recovery write failure")
                return open_file(path, *args, **kwargs)
            with patch.object(Path, "open", fail), self.assertRaisesRegex(OSError, "write failure"):
                commit_plan(self.workspace, recovery)
            self.assertEqual(self.files(), before)

    def test_symbol_only_and_protected_paths(self):
        inv = scan(self.workspace, "SamacSys")
        plan = build_plan(self.workspace, inv, next(iter(inv.symbols)), "", "", "ICs", "Original")
        commit_plan(self.workspace, plan)
        symbol = next(iter(plan.assets))
        with self.assertRaises(ValueError):
            self.remove(protected_roots=(symbol.parent,))
        commit_plan(self.workspace, self.remove())
        with self.assertRaises(ValueError):
            self.recover(protected_roots=(symbol.parent,))
        commit_plan(self.workspace, self.recover())
        self.assertEqual(len(self.record()["outputs"]), 1)

    def test_provenance_survives_without_original_sources(self):
        provenance = {"archive_path": "example.zip", "archive_sha256": "abc123"}
        (self.source / ORIGIN_FILE).write_text(json.dumps(provenance), encoding="utf-8")
        self.initial()
        original = self.record()
        for p in self.source.iterdir():
            p.unlink()
        commit_plan(self.workspace, self.remove())
        self.assertEqual(self.record()["source_archive"], provenance)
        commit_plan(self.workspace, self.recover())
        self.assertEqual(self.record()["source_archive"], provenance)
        self.assertEqual(self.record()["source_files"], original["source_files"])

    def test_moved_component_can_remove_recover_move_back_and_update(self):
        self.initial()
        target = next(c for c in DEFAULT_CATEGORIES if c.name == "Power")
        commit_plan(self.workspace, build_move_plan(self.workspace, self.record()["event_id"], target))
        commit_plan(self.workspace, self.remove())
        commit_plan(self.workspace, self.recover())
        target = next(c for c in DEFAULT_CATEGORIES if c.name == "ICs")
        commit_plan(self.workspace, build_move_plan(self.workspace, self.record()["event_id"], target))
        self.change(footprint=False, model=False)
        commit_plan(self.workspace, self.build(build_update_plan))
        self.assertEqual(self.record()["operation"], "update")

    def test_gui_confirmation_recovery_buttons_and_settings_guard(self):
        self.initial()
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        root.withdraw()
        try:
            app = App(root, self.workspace)
            app.validate(); app.ack.set(True)
            history = app.open_history()
            self.assertEqual(str(history.remove_button['state']), 'normal')
            review = history.remove_selected()
            self.assertTrue(review.removing)
            self.assertFalse(review.apply())
            self.assertIn("Remove after backup", review.report.get("1.0", "end"))
            review.reviewed.set(True)
            self.assertTrue(review.apply())
            self.assertEqual(str(history.remove_button['state']), 'disabled')
            self.assertEqual(str(history.recover_button['state']), 'normal')
            self.assertFalse(app.ack.get())
            self.assertIn("Component removed", app.log.get("1.0", "end"))
            recovery = history.recover_selected()
            self.assertTrue(recovery.recovering)
            self.assertFalse(recovery.apply())
            recovery.reviewed.set(True)
            self.assertTrue(recovery.apply())
            self.assertIn("Component recovered", app.log.get("1.0", "end"))
            self.assertEqual(str(history.recover_button['state']), 'disabled')
            from dataclasses import replace
            app.settings = replace(app.settings, model_path_mode="absolute")
            with patch('history_dialog.messagebox.showerror') as error:
                self.assertIsNone(history.remove_selected())
                error.assert_called_once()
        finally:
            root.destroy()

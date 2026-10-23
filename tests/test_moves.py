"""Tracked category moves preserve siblings/sharing and roll back all file actions."""
import copy
import json
from pathlib import Path
import sys
import tkinter as tk
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from component_move import build_move_plan
from component_restore import build_restore_plan
from component_updates import build_update_plan
from import_gui import App
from import_history import BACKUP_FOLDER, HISTORY_FOLDER, component_identity, current_components, read_history
from library_core import (ImportErrorDetail, build_plan, children, commit_plan, dump, parse, prop, read_tree, scan)
from library_layout import DEFAULT_CATEGORIES
from test_importer import SYMBOL, FOOTPRINT, STEP
import test_updates as update_fixtures


class MoveTests(unittest.TestCase):
    setUp = update_fixtures.UpdateTests.setUp
    build = update_fixtures.UpdateTests.build
    initial = update_fixtures.UpdateTests.initial
    change = update_fixtures.UpdateTests.change

    def record(self, symbol="TEST123", category="ICs"):
        return next(item for item in read_history(self.workspace)[0] if item["symbol"] == symbol and item["category"] == category)

    def move(self, record=None, target="Power", **kwargs):
        category = next(item for item in DEFAULT_CATEGORIES if item.name == target)
        return build_move_plan(self.workspace, (record or self.record())["event_id"], category, **kwargs)

    def import_other(self, name, category="ICs", mode="packed", symbol_only=False):
        self.symbol_file.write_text(SYMBOL.replace("TEST123", name), encoding="utf-8")
        inv = scan(self.workspace, "SamacSys")
        plan = build_plan(self.workspace, inv, next(iter(inv.symbols)), "" if symbol_only else "GEOM.kicad_mod",
                          "" if symbol_only else "TEST123.stp", category, "Original", symbol_format=mode)
        commit_plan(self.workspace, plan)
        return plan

    def files(self):
        return {p: p.read_bytes() for p in self.workspace.rglob("*") if p.is_file() and BACKUP_FOLDER not in p.parts}

    def test_moves_both_native_formats_with_references_and_exact_backups(self):
        for mode in ("packed", "unpacked"):
            with self.subTest(mode=mode):
                self.setUp()
                self.initial(mode)
                record = self.record()
                old = {self.workspace / item["relative_path"]: (self.workspace / item["relative_path"]).read_bytes() for item in record["outputs"]}
                inputs = {p: p.read_bytes() for p in self.source.iterdir()}
                plan = self.move(record)
                self.assertFalse((self.workspace / BACKUP_FOLDER).exists())
                commit_plan(self.workspace, plan)
                new = {role: path for path, role in plan.assets.items()}
                node = children(read_tree(new["symbol"]), "symbol")[0]
                self.assertEqual(prop(node, "Footprint"), "DVL_Power:GEOM")
                fp = read_tree(new["footprint"])
                self.assertEqual(children(fp, "model")[0][1], "${DVL_LIB_ROOT}/3DModels/Power/GEOM.stp")
                self.assertEqual(children(fp, "model")[0][2:], children(parse(old[next(path for path in old if path.suffix == ".kicad_mod")].decode()), "model")[0][2:])
                self.assertEqual(new["model"].read_bytes(), STEP)
                for path, data in old.items():
                    self.assertEqual((plan.backup_directory / path.relative_to(self.workspace)).read_bytes(), data)
                    if mode == "packed" and path.suffix == ".kicad_sym":
                        self.assertFalse(children(read_tree(path), "symbol"))
                    else:
                        self.assertFalse(path.exists())
                self.assertEqual({p: p.read_bytes() for p in inputs}, inputs)
                records, notices = read_history(self.workspace)
                self.assertFalse(notices)
                self.assertEqual(records[0]["operation"], "move")
                self.assertEqual(records[0]["category"], "Power")
                self.assertIsNone(current_components(records)[component_identity(record)])
                self.assertTrue(records[0]["file_changes"])

    def test_packed_siblings_destination_append_and_shared_assets_are_preserved(self):
        self.initial("packed")
        source_record = self.record()
        source_other = self.import_other("OTHER456")
        dest_other = self.import_other("TARGET789", category="Power")
        original_source = next(path for path, role in source_other.assets.items() if role == "symbol")
        original_target = next(path for path, role in dest_other.assets.items() if role == "symbol")
        source_sibling = next(node for node in children(read_tree(original_source), "symbol") if node[1] == "OTHER456")
        target_sibling = next(node for node in children(read_tree(original_target), "symbol") if node[1] == "TARGET789")
        target_before = original_target.read_bytes()
        plan = self.move(source_record)
        self.assertNotIn(self.workspace / "Footprints/DVL_ICs.pretty/GEOM.kicad_mod", plan.removals)
        self.assertNotIn(self.workspace / "3DModels/ICs/GEOM.stp", plan.removals)
        commit_plan(self.workspace, plan)
        self.assertEqual(children(read_tree(original_source), "symbol"), [source_sibling])
        self.assertIn(target_sibling, children(read_tree(original_target), "symbol"))
        self.assertEqual(len(children(read_tree(original_target), "symbol")), 2)
        self.assertEqual((plan.backup_directory / original_target.relative_to(self.workspace)).read_bytes(), target_before)

    def test_untracked_symbol_reference_retains_source_footprint_and_model(self):
        self.initial()
        folder = self.workspace / "Symbols/Untracked.kicad_symdir"
        folder.mkdir()
        (folder / "OTHER.kicad_sym").write_text(SYMBOL.replace("TEST123", "OTHER").replace("Vendor:GEOM", "DVL_ICs:GEOM"), encoding="utf-8")
        plan = self.move()
        commit_plan(self.workspace, plan)
        self.assertTrue((self.workspace / "Footprints/DVL_ICs.pretty/GEOM.kicad_mod").exists())
        self.assertTrue((self.workspace / "3DModels/ICs/GEOM.stp").exists())

    def test_untracked_model_reference_retains_only_the_shared_model(self):
        self.initial()
        folder = self.workspace / "Footprints/Untracked.pretty"
        folder.mkdir()
        tree = parse(FOOTPRINT)
        children(tree, "model")[0][1] = "${DVL_LIB_ROOT}/3DModels/ICs/GEOM.stp"
        (folder / "OTHER.kicad_mod").write_text(dump(tree), encoding="utf-8")
        plan = self.move()
        commit_plan(self.workspace, plan)
        self.assertFalse((self.workspace / "Footprints/DVL_ICs.pretty/GEOM.kicad_mod").exists())
        self.assertTrue((self.workspace / "3DModels/ICs/GEOM.stp").exists())

    def test_manually_edited_or_missing_assets_are_blocked(self):
        self.initial()
        record = self.record()
        for item in record["outputs"]:
            path = self.workspace / item["relative_path"]
            data = path.read_bytes()
            path.write_bytes(data + b"manual edit")
            with self.assertRaisesRegex(ImportErrorDetail, "Manual edits"):
                self.move(record)
            path.unlink()
            with self.assertRaisesRegex(ImportErrorDetail, "missing"):
                self.move(record)
            path.write_bytes(data)
        self.assertFalse((self.workspace / BACKUP_FOLDER).exists())

    def test_destination_symbol_footprint_and_model_conflicts_block_without_writes(self):
        self.initial()
        for role, path, data in (
            ("symbol", self.workspace / "Symbols/DVL_Power.kicad_symdir/TEST123.kicad_sym", SYMBOL.encode()),
            ("footprint", self.workspace / "Footprints/DVL_Power.pretty/GEOM.kicad_mod", FOOTPRINT.replace("SOIC", "DIFFERENT").encode()),
            ("model", self.workspace / "3DModels/Power/GEOM.stp", b"different model")):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            before = self.files()
            with self.subTest(role=role), self.assertRaises(ImportErrorDetail):
                self.move()
            self.assertEqual(self.files(), before)
            path.unlink()

    def test_inherited_dependants_and_unreadable_libraries_block_move(self):
        self.initial("packed")
        target = self.workspace / "Symbols/Other.kicad_sym"
        target.write_text("broken", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.move()
        target.unlink()
        # A qualified inherited reference in another library must not be broken.
        target.write_text('(kicad_symbol_lib (version 20220914) (symbol "OTHER" (extends "DVL_ICs:TEST123")))', encoding="utf-8")
        with self.assertRaisesRegex(ImportErrorDetail, "inherits"):
            self.move()

    def test_late_reference_or_destination_edit_invalidates_commit(self):
        self.initial()
        plan = self.move()
        before = self.files()
        folder = self.workspace / "Symbols/Other.kicad_symdir"
        folder.mkdir()
        (folder / "OTHER.kicad_sym").write_text(SYMBOL, encoding="utf-8")
        with self.assertRaisesRegex(ImportErrorDetail, "Dependency folder changed"):
            commit_plan(self.workspace, plan)
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        (folder / "OTHER.kicad_sym").unlink()
        folder.rmdir()
        plan = self.move()
        source = next(path for path in plan.removals if path.suffix == ".kicad_sym")
        source.write_bytes(source.read_bytes() + b"\n")
        with self.assertRaisesRegex(ImportErrorDetail, "Destination changed"):
            commit_plan(self.workspace, plan)

    def test_backup_destination_and_history_failures_roll_back(self):
        self.initial("packed")
        before = self.files()
        open_file = Path.open
        for failure in ("backup", "destination", "history"):
            def fail(path, *args, **kwargs):
                if path.name.endswith(".import-tmp"):
                    if ((failure == "backup" and BACKUP_FOLDER in path.parts)
                            or (failure == "destination" and path.parent.name == "Symbols")
                            or (failure == "history" and HISTORY_FOLDER in path.parts)):
                        raise OSError("simulated write failure")
                return open_file(path, *args, **kwargs)
            plan = self.move()
            with patch.object(Path, "open", fail), self.assertRaisesRegex(OSError, "simulated"):
                commit_plan(self.workspace, plan)
            self.assertEqual(self.files(), before)
            self.assertFalse([p for p in (self.workspace / BACKUP_FOLDER).rglob("*") if p.is_file()])

    def test_deletion_failure_restores_removed_source_and_new_destinations(self):
        self.initial()
        before = self.files()
        plan = self.move()
        fail_path = self.workspace / "Footprints/DVL_ICs.pretty/GEOM.kicad_mod"
        unlink = Path.unlink
        def fail(path, *args, **kwargs):
            if path == fail_path:
                raise OSError("cannot remove source")
            return unlink(path, *args, **kwargs)
        with patch.object(Path, "unlink", fail), self.assertRaisesRegex(OSError, "cannot remove"):
            commit_plan(self.workspace, plan)
        self.assertEqual(self.files(), before)
        self.assertFalse([p for p in (self.workspace / BACKUP_FOLDER).rglob("*") if p.is_file()])

    def test_source_packed_sibling_can_update_and_restore_after_move(self):
        self.initial("packed")
        source_record = self.record()
        self.import_other("OTHER456")
        commit_plan(self.workspace, self.move(source_record))
        self.symbol_file.write_text(SYMBOL.replace("TEST123", "OTHER456").replace('"IN"', '"UPDATED_INPUT"'), encoding="utf-8")
        commit_plan(self.workspace, self.build(build_update_plan, "packed"))
        update = self.record("OTHER456")
        commit_plan(self.workspace, build_restore_plan(self.workspace, update["event_id"]))
        source_library = self.workspace / "Symbols/DVL_ICs.kicad_sym"
        self.assertEqual([node[1] for node in children(read_tree(source_library), "symbol")], ["OTHER456"])
        self.assertNotIn("UPDATED_INPUT", source_library.read_text())

    def test_moved_component_can_update_then_restore_in_destination(self):
        self.initial()
        commit_plan(self.workspace, self.move())
        self.change(footprint=False, model=False)
        inv = scan(self.workspace, "SamacSys")
        plan = build_update_plan(self.workspace, inv, next(iter(inv.symbols)), "GEOM.kicad_mod", "TEST123.stp", "Power", "Original")
        commit_plan(self.workspace, plan)
        update = self.record(category="Power")
        commit_plan(self.workspace, build_restore_plan(self.workspace, update["event_id"]))
        self.assertNotIn("UPDATED_INPUT", (self.workspace / "Symbols/DVL_Power.kicad_symdir/TEST123.kicad_sym").read_text())
        with self.assertRaisesRegex(ImportErrorDetail, "moved out"):
            self.build(build_update_plan)

    def test_move_back_works_without_original_exports_and_retires_old_identity(self):
        self.initial()
        initial = self.record()
        commit_plan(self.workspace, self.move(initial))
        moved = self.record(category="Power")
        for path in self.source.iterdir():
            path.unlink()
        commit_plan(self.workspace, self.move(moved, target="ICs"))
        records, notices = read_history(self.workspace)
        self.assertFalse(notices)
        self.assertEqual(records[0]["category"], "ICs")
        self.assertIsNone(current_components(records)[component_identity(moved)])
        with self.assertRaisesRegex(ImportErrorDetail, "latest active"):
            self.move(initial)

    def test_symbol_only_move_keeps_native_format(self):
        inv = scan(self.workspace, "SamacSys")
        initial = build_plan(self.workspace, inv, next(iter(inv.symbols)), "", "", "ICs", "Original")
        commit_plan(self.workspace, initial)
        plan = self.move()
        commit_plan(self.workspace, plan)
        self.assertEqual(set(plan.assets.values()), {"symbol"})
        self.assertFalse((self.workspace / "Footprints/DVL_Power.pretty").exists())

    def test_absolute_model_path_and_protected_input_boundary(self):
        self.initial()
        with self.assertRaises(ValueError):
            self.move(protected_roots=(self.workspace / "Footprints/DVL_Power.pretty",))
        plan = self.move(model_path_mode="absolute")
        footprint = next(data for path, data in plan.files.items() if path.suffix == ".kicad_mod")
        reference = children(parse(footprint.decode()), "model")[0][1]
        self.assertEqual(reference, (self.workspace / "3DModels/Power/GEOM.stp").as_posix())

    def test_gui_review_confirmation_and_settings_changes(self):
        self.initial()
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        root.withdraw()
        try:
            app = App(root, self.workspace)
            history = app.open_history()
            move = history.move_selected()
            move.target.set("Power")
            review = move.review()
            self.assertTrue(review.moving)
            self.assertFalse(review.apply())
            self.assertIn("Remove source", review.report.get("1.0", "end"))
            review.reviewed.set(True)
            self.assertTrue(review.apply())
            self.assertEqual(app.category.get(), "Power")
            self.assertIn("Component moved", app.log.get("1.0", "end"))
            self.assertFalse(app.ack.get())
            self.assertEqual(read_history(self.workspace)[0][0]["operation"], "move")
            move.window.destroy()
            next_move = history.move_selected()
            from dataclasses import replace
            app.settings = replace(app.settings, model_path_mode="absolute")
            with patch("move_dialog.messagebox.showerror") as error:
                self.assertIsNone(next_move.review())
                error.assert_called_once()
        finally:
            root.destroy()

"""Transactional import records, reuse provenance and a read-only history browser."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from archive_import import extract_native_zip
from import_history import HISTORY_FOLDER, ORIGIN_FILE, add_history_record, read_history
from import_gui import App
from library_core import build_plan, commit_plan, scan
from test_importer import SYMBOL, FOOTPRINT, STEP
from test_archives import create_zip


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.source = self.workspace / "Imports/SamacSys"
        self.source.mkdir(parents=True)
        (self.source / "parts.kicad_sym").write_text(SYMBOL, encoding="utf-8")
        (self.source / "GEOM.kicad_mod").write_text(FOOTPRINT, encoding="utf-8")
        (self.source / "TEST123.stp").write_bytes(STEP)

    def plan(self, mode="unpacked", symbol_only=False):
        inventory = scan(self.workspace, "SamacSys")
        return build_plan(self.workspace, inventory, next(iter(inventory.symbols)),
                          "" if symbol_only else "GEOM.kicad_mod", "" if symbol_only else "TEST123.stp",
                          "ICs", "Original", symbol_format=mode)

    def test_records_created_files_hashes_and_source_after_commit_only(self):
        plan = self.plan()
        self.assertFalse((self.workspace / HISTORY_FOLDER).exists())
        commit_plan(self.workspace, plan)
        records, notices = read_history(self.workspace)
        self.assertFalse(notices)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["symbol"], "TEST123")
        self.assertEqual(record["symbol_format"], "unpacked")
        self.assertEqual(record["category"], "ICs")
        self.assertEqual(record["input_root"], str(self.source))
        self.assertIsNone(record["source_archive"])
        self.assertEqual({item["role"] for item in record["outputs"]}, {"symbol", "footprint", "model"})
        for item in record["outputs"]:
            self.assertEqual(item["action"], "created")
            destination = self.workspace / item["relative_path"]
            self.assertEqual(item["sha256"], hashlib.sha256(destination.read_bytes()).hexdigest())

    def test_packed_append_distinguishes_update_and_identical_reuse(self):
        commit_plan(self.workspace, self.plan("packed"))
        first, _ = read_history(self.workspace)
        (self.source / "parts.kicad_sym").write_text(SYMBOL.replace("TEST123", "NEXT456"), encoding="utf-8")
        commit_plan(self.workspace, self.plan("packed"))
        records, notices = read_history(self.workspace)
        self.assertFalse(notices)
        self.assertEqual(len(records), 2)
        self.assertNotEqual(records[0]["event_id"], records[1]["event_id"])
        newest = records[0]
        self.assertEqual(newest["symbol"], "NEXT456")
        self.assertEqual({item["role"]: item["action"] for item in newest["outputs"]},
                         {"symbol": "updated", "footprint": "reused", "model": "reused"})
        self.assertEqual(records[1]["outputs"], first[0]["outputs"])

    def test_symbol_only_has_no_invented_footprint_or_model_outputs(self):
        commit_plan(self.workspace, self.plan(symbol_only=True))
        record = read_history(self.workspace)[0][0]
        self.assertEqual([item["role"] for item in record["outputs"]], ["symbol"])
        self.assertTrue(any("Symbol-only" in warning for warning in record["warnings"]))

    def history_failure(self, path, *args, **kwargs):
        if path.parent.name == HISTORY_FOLDER and path.name.endswith(".import-tmp"):
            raise OSError("History cannot be written")
        return self.original_open(path, *args, **kwargs)

    def test_history_write_failure_rolls_back_new_assets(self):
        self.original_open = Path.open
        plan = self.plan()
        with patch.object(Path, "open", lambda path, *args, **kwargs: self.history_failure(path, *args, **kwargs)):
            with self.assertRaisesRegex(OSError, "History cannot"):
                commit_plan(self.workspace, plan)
        self.assertFalse(list((self.workspace / "Symbols").rglob("*.kicad_sym")))
        self.assertFalse(list((self.workspace / "Footprints").rglob("*.kicad_mod")))
        self.assertFalse(list((self.workspace / "3DModels").rglob("*.stp")))
        self.assertEqual(read_history(self.workspace)[0], [])
        # Retrying this same plan adds exactly one history event.
        commit_plan(self.workspace, plan)
        self.assertEqual(len(read_history(self.workspace)[0]), 1)

    def test_history_failure_restores_existing_packed_library(self):
        commit_plan(self.workspace, self.plan("packed"))
        library = self.workspace / "Symbols/DVL_ICs.kicad_sym"
        before = library.read_bytes()
        original_record = read_history(self.workspace)[0][0]["event_id"]
        (self.source / "parts.kicad_sym").write_text(SYMBOL.replace("TEST123", "NEXT456"), encoding="utf-8")
        self.original_open = Path.open
        with patch.object(Path, "open", lambda path, *args, **kwargs: self.history_failure(path, *args, **kwargs)):
            with self.assertRaises(OSError):
                commit_plan(self.workspace, self.plan("packed"))
        self.assertEqual(library.read_bytes(), before)
        self.assertEqual([record["event_id"] for record in read_history(self.workspace)[0]], [original_record])

    def test_zip_provenance_and_older_cache_are_distinguished(self):
        archive = self.workspace / "part.zip"
        create_zip(archive)
        folder = extract_native_zip(archive, self.workspace)
        inventory = scan(self.workspace, "SamacSys", input_root=folder)
        plan = build_plan(self.workspace, inventory, next(iter(inventory.symbols)),
                          "PART/KiCad/GEOM.kicad_mod", "PART/3D/TEST123.stp", "ICs", "Suggestion")
        commit_plan(self.workspace, plan)
        record = read_history(self.workspace)[0][0]
        self.assertEqual(record["source_archive"]["archive_path"], str(archive))
        self.assertEqual(record["source_archive"]["archive_sha256"], hashlib.sha256(archive.read_bytes()).hexdigest())
        (folder / ORIGIN_FILE).unlink()
        plan = build_plan(self.workspace, inventory, next(iter(inventory.symbols)),
                          "PART/KiCad/GEOM.kicad_mod", "PART/3D/TEST123.stp", "Power", "Suggestion")
        commit_plan(self.workspace, plan)
        self.assertIsNone(read_history(self.workspace)[0][0]["source_archive"])

    def test_missing_or_corrupt_history_is_not_reconstructed_or_overwritten(self):
        self.assertEqual(read_history(self.workspace), ([], []))
        self.assertFalse((self.workspace / HISTORY_FOLDER).exists())
        folder = self.workspace / HISTORY_FOLDER
        folder.mkdir()
        invalid = folder / "broken.json"
        invalid.write_text("{broken", encoding="utf-8")
        commit_plan(self.workspace, self.plan())
        records, notices = read_history(self.workspace)
        self.assertEqual(len(records), 1)
        self.assertEqual(len(notices), 1)
        self.assertEqual(invalid.read_text(encoding="utf-8"), "{broken")

    def test_history_browser_filters_and_records_gui_provider_context(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        root.withdraw()
        try:
            app = App(root, self.workspace)
            app.validate()
            app.ack.set(True)
            app.import_component()
            record = read_history(self.workspace)[0][0]
            self.assertEqual(record["provider"], "SamacSys")
            dialog = app.open_history()
            self.assertEqual(len(dialog.table.get_children()), 1)
            self.assertIn("Component: TEST123", dialog.details.get("1.0", "end"))
            dialog.query.set("does not exist")
            self.assertFalse(dialog.table.get_children())
            dialog.query.set("TEST123")
            self.assertEqual(len(dialog.table.get_children()), 1)
            before = {p: p.read_bytes() for p in (self.workspace / HISTORY_FOLDER).iterdir()}
            dialog.reload()
            self.assertEqual({p: p.read_bytes() for p in (self.workspace / HISTORY_FOLDER).iterdir()}, before)
            dialog.window.destroy()
        finally:
            root.destroy()

"""Stable local ZIP arrivals load only for review; no browser/provider automation."""
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from archive_import import cache_directory
from download_watch import (ArrivalChanged, ZipArrivalTracker, fingerprint, prepare_arrival)
from import_gui import App
from library_core import load_preferences
from test_archives import create_zip
import test_input_choices as input_fixtures


class ArrivalTests(unittest.TestCase):
    def test_baseline_stability_replacements_removal_and_newest_order(self):
        old, new = Path("old.zip"), Path("new.zip")
        tracker = ZipArrivalTracker()
        tracker.baseline({old: (100, 1)})
        tracker.observe({old: (100, 1)}, 100)
        self.assertFalse(tracker.ready(200))
        tracker.observe({old: (101, 2), new: (200, 3)}, 201)
        self.assertFalse(tracker.ready(206))
        self.assertEqual([path for path, _ in tracker.ready(207)], [new, old])
        tracker.consume(new, (200, 3))
        tracker.observe({old: (102, 4), new: (200, 3)}, 208)
        self.assertFalse(tracker.ready(213))
        self.assertEqual(tracker.ready(214), [(old, (102, 4))])
        tracker.observe({new: (200, 3)}, 215)
        self.assertFalse(tracker.ready(300))

    def test_validated_arrival_retains_original_and_only_native_cache_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            archive = root / "LIB_TEST.zip"
            create_zip(archive)
            original = archive.read_bytes()
            folder = prepare_arrival(archive, root, fingerprint(archive))
            self.assertEqual(archive.read_bytes(), original)
            self.assertTrue((folder / "PART/KiCad/part.kicad_sym").exists())
            self.assertFalse((folder / "PART/Other/Build.bat").exists())
            self.assertFalse((root / "Symbols").exists())

    def test_partial_stale_and_cancelled_arrivals_do_not_extract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            archive = root / "LIB_TEST.zip"
            create_zip(archive)
            signature = fingerprint(archive)
            partial = root / "LIB_TEST.zip.crdownload"
            partial.write_bytes(b"in progress")
            with self.assertRaises(ArrivalChanged):
                prepare_arrival(archive, root, signature)
            partial.unlink()
            with self.assertRaises(ArrivalChanged):
                prepare_arrival(archive, root, (1, 2))
            cancelled = threading.Event()
            cancelled.set()
            with self.assertRaises(ArrivalChanged):
                prepare_arrival(archive, root, signature, cancelled)
            self.assertFalse(cache_directory(root).exists())

    def test_changed_during_extraction_is_cleaned_without_touching_zip(self):
        import download_watch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            archive = root / "LIB_TEST.zip"
            create_zip(archive)
            real_extract = download_watch.extract_native_zip
            def extract_then_change(path, workspace):
                folder = real_extract(path, workspace)
                path.write_bytes(path.read_bytes() + b"new download data")
                return folder
            with patch("download_watch.extract_native_zip", side_effect=extract_then_change), self.assertRaises(ArrivalChanged):
                prepare_arrival(archive, root, fingerprint(archive))
            self.assertFalse(list(cache_directory(root).iterdir()))
            self.assertTrue(archive.read_bytes().endswith(b"new download data"))


class ArrivalGuiTests(unittest.TestCase):
    setUp = input_fixtures.InputChoiceGuiTests.setUp
    downloads_mode = input_fixtures.InputChoiceGuiTests.downloads_mode
    poll_once = input_fixtures.InputChoiceGuiTests.poll_once

    def enable(self):
        self.downloads_mode()
        self.assertTrue(self.app.load_download())
        self.app.validate()
        self.app.ack.set(True)
        self.original_plan = self.app.plan
        self.original_inventory = self.app.inv
        self.app.auto_load_zips.set(True)
        self.app.toggle_auto_zip()

    def poll_at(self, now):
        with patch("import_gui.time.monotonic", return_value=now):
            self.poll_once()

    def wait_worker(self, now=10):
        deadline = time.monotonic() + 5
        while self.app.auto_zip_busy and time.monotonic() < deadline:
            self.poll_at(now)
            time.sleep(0.01)
        self.assertFalse(self.app.auto_zip_busy)

    def test_refresh_button_loads_newest_and_does_not_import(self):
        self.downloads_mode()
        self.assertTrue(self.app.load_download())
        newest = self.downloads / "newest.zip"
        create_zip(newest)
        os.utime(self.archive, ns=(1_000_000_000, 1_000_000_000))
        os.utime(newest, ns=(2_000_000_000, 2_000_000_000))
        self.assertTrue(self.app.refresh_action())
        self.assertEqual(self.app.active_zip, str(newest))
        self.assertEqual(self.app.download_zip.get(), newest.name)
        self.assertEqual(self.app.download_combo["values"][0], newest.name)
        self.assertFalse((self.workspace / "Symbols").exists())

    def test_refresh_broken_newest_keeps_loaded_component_and_review(self):
        self.enable()
        newest = self.downloads / "broken.zip"
        newest.write_bytes(b"broken")
        os.utime(self.archive, ns=(1_000_000_000, 1_000_000_000))
        os.utime(newest, ns=(2_000_000_000, 2_000_000_000))
        with patch("import_gui.messagebox.showerror"):
            self.assertFalse(self.app.refresh_action())
        self.assertIs(self.app.inv, self.original_inventory)
        self.assertIs(self.app.plan, self.original_plan)
        self.assertTrue(self.app.ack.get())

    def test_automatic_load_requires_new_stable_arrival_and_never_imports(self):
        self.enable()
        self.poll_at(0)
        self.poll_at(10)
        self.assertIs(self.app.inv, self.original_inventory)
        new = self.downloads / "LIB_NEW.zip"
        create_zip(new)
        self.poll_at(11)
        self.poll_at(16)
        self.assertFalse(self.app.auto_zip_busy)
        self.assertIs(self.app.plan, self.original_plan)
        self.poll_at(17)
        self.wait_worker(18)
        self.assertEqual(self.app.active_zip, str(new))
        self.assertIsNone(self.app.plan)
        self.assertFalse(self.app.ack.get())
        self.assertFalse((self.workspace / "Symbols").exists())
        self.assertIn("automatically for review", self.app.download_status.get())
        loaded = self.app.inv
        self.poll_at(30)
        self.assertIs(self.app.inv, loaded)
        self.assertFalse(self.app.auto_zip_busy)

    def test_partial_sidecar_blocks_load_until_removed(self):
        self.enable()
        new = self.downloads / "LIB_NEW.zip"
        create_zip(new)
        partial = self.downloads / "LIB_NEW.zip.part"
        partial.write_bytes(b"partial")
        self.poll_at(0)
        self.poll_at(10)
        self.assertFalse(self.app.auto_zip_busy)
        partial.unlink()
        self.poll_at(11)
        self.wait_worker(12)
        self.assertEqual(self.app.active_zip, str(new))

    def test_invalid_zip_skipped_once_without_modal_or_losing_review(self):
        self.enable()
        new = self.downloads / "unrelated.zip"
        with zipfile.ZipFile(new, "w") as archive:
            archive.writestr("note.txt", "not a native component")
        self.poll_at(0)
        with patch("import_gui.messagebox.showerror") as error:
            self.poll_at(10)
            self.wait_worker(11)
            error.assert_not_called()
        self.assertIn("Skipped", self.app.download_status.get())
        self.assertIs(self.app.inv, self.original_inventory)
        self.assertIs(self.app.plan, self.original_plan)
        self.assertTrue(self.app.ack.get())
        self.poll_at(30)
        self.assertFalse(self.app.auto_zip_busy)

    def test_failed_preference_save_cleans_extraction_and_keeps_input(self):
        self.enable()
        new = self.downloads / "LIB_NEW.zip"
        create_zip(new)
        self.poll_at(0)
        self.poll_at(10)
        with patch("import_gui.save_preferences", side_effect=OSError("full")):
            self.wait_worker(11)
        self.assertIs(self.app.inv, self.original_inventory)
        self.assertIs(self.app.plan, self.original_plan)
        self.assertEqual(self.app.active_zip, str(self.archive))
        self.assertIn("previous component is retained", self.app.download_status.get())

    def test_mode_and_dialog_changes_defer_or_discard_arrivals(self):
        self.enable()
        new = self.downloads / "LIB_NEW.zip"
        create_zip(new)
        modal = tk.Toplevel(self.root)
        self.poll_at(0)
        self.poll_at(10)
        self.assertFalse(self.app.auto_zip_busy)
        modal.destroy()
        self.poll_at(11)
        self.app.auto_load_zips.set(False)
        self.app.toggle_auto_zip()
        self.wait_worker(12)
        self.assertIs(self.app.inv, self.original_inventory)
        self.assertIs(self.app.plan, self.original_plan)

    def test_browser_handoff_arms_only_new_arrivals_and_is_session_only(self):
        dialog = self.app.open_search()
        dialog.provider.set("SamacSys")
        dialog.watch_new_downloads()
        self.assertFalse(dialog.window.winfo_exists())
        self.assertEqual(self.app.source_choice.get(), "Downloads")
        self.assertTrue(self.app.auto_load_zips.get())
        self.poll_at(100)
        self.assertFalse(self.app.auto_zip_busy)
        preferences = load_preferences(self.app.prefs_path)
        self.assertNotIn("auto_load_zips", preferences)
        other = tk.Toplevel(self.root)
        second = App(other, self.workspace)
        self.assertFalse(second.auto_load_zips.get())
        other.destroy()

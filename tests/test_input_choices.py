"""Downloads intake and short display names preserve exact asset identities."""
import os
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from import_gui import App
from input_choices import downloaded_zips
from library_core import SYMBOL_FORMATS, load_preferences
from test_archives import create_zip
from test_importer import SYMBOL, FOOTPRINT, STEP


class DownloadListTests(unittest.TestCase):
    def test_shallow_zip_list_is_sorted_and_ignores_incomplete_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("old.zip", "recent.ZIP", "partial.zip.crdownload", "note.txt"):
                (root / name).write_bytes(b"fixture")
            (root / "nested").mkdir()
            (root / "nested/hidden.zip").write_bytes(b"fixture")
            os.utime(root / "old.zip", ns=(1_000_000_000, 1_000_000_000))
            os.utime(root / "recent.ZIP", ns=(2_000_000_000, 2_000_000_000))
            self.assertEqual([p.name for p in downloaded_zips(root)], ["recent.ZIP", "old.zip"])


class InputChoiceGuiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.workspace = self.base / "application"
        self.workspace.mkdir()
        self.downloads = self.base / "downloads"
        self.downloads.mkdir()
        self.archive = self.downloads / "LIB_TEST123.zip"
        create_zip(self.archive)
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.app = App(self.root, self.workspace)
        self.app.downloads_folder = self.downloads

    def downloads_mode(self):
        self.app.source_choice.set("Downloads")
        self.app.select_source_choice()

    def test_downloads_selection_lists_without_extracting_and_refresh_discovers_new(self):
        self.downloads_mode()
        self.assertEqual(list(self.app.download_files), [self.archive.name])
        self.assertIsNone(self.app.inv)
        self.assertIsNone(self.app.plan)
        self.assertFalse((self.workspace / ".kicad-importer-cache").exists())
        another = self.downloads / "new.zip"
        create_zip(another)
        self.app.refresh()
        self.assertIn(another.name, self.app.download_files)
        self.assertFalse((self.workspace / ".kicad-importer-cache").exists())

    def test_load_download_short_names_and_both_output_formats(self):
        self.downloads_mode()
        with patch("import_gui.filedialog.askopenfilename") as picker:
            self.assertTrue(self.app.load_download())
            picker.assert_not_called()
        self.assertEqual(self.app.combos["Symbol"].get(), "TEST123")
        self.assertEqual(self.app.combos["Footprint"].get(), "GEOM.kicad_mod")
        self.assertEqual(self.app.combos["STEP model"].get(), "TEST123.stp")
        self.assertEqual(self.app.fp.get(), "PART/KiCad/GEOM.kicad_mod")
        self.assertTrue(self.app.inv.root.is_dir())
        for mode in ("unpacked", "packed"):
            self.app.symbol_format.set(SYMBOL_FORMATS[mode])
            self.app.validate()
            self.assertIsNotNone(self.app.plan)
            self.app.ack.set(True)
            self.app.import_component()
            target = self.app.settings.get_category("ICs").symbol_library(self.workspace, mode)
            self.assertTrue((target / "TEST123.kicad_sym").is_file() if mode == "unpacked" else target.is_file())
        prefs = load_preferences(self.app.prefs_path)
        self.assertEqual(prefs["input_mode"], "downloads")
        self.assertEqual(Path(prefs["downloads_folder"]), self.downloads)
        self.assertEqual(Path(prefs["active_zip"]), self.archive)

    def test_duplicate_asset_names_stay_independently_selectable(self):
        self.downloads_mode()
        self.assertTrue(self.app.load_download())
        source = self.app.inv.root
        for name in ("A", "B"):
            folder = source / name
            folder.mkdir()
            (folder / "duplicate.kicad_sym").write_text(SYMBOL.replace("TEST123", "DUPLICATE"), encoding="utf-8")
            (folder / "GEOM.kicad_mod").write_text(FOOTPRINT, encoding="utf-8")
            (folder / "TEST123.stp").write_bytes(STEP)
        self.app.refresh()
        labels = self.app.combos["Symbol"]["values"]
        self.assertIn("DUPLICATE — A/duplicate.kicad_sym", labels)
        self.assertIn("DUPLICATE — B/duplicate.kicad_sym", labels)
        self.app.asset_displays["Symbol"].set("DUPLICATE — B/duplicate.kicad_sym")
        self.app.select_asset("Symbol")
        self.assertEqual(self.app.inv.symbols[self.app.symbol.get()].path, source / "B/duplicate.kicad_sym")
        self.app.asset_displays["Footprint"].set("GEOM.kicad_mod — A/GEOM.kicad_mod")
        self.app.select_asset("Footprint")
        self.assertEqual(self.app.fp.get(), "A/GEOM.kicad_mod")
        self.app.asset_displays["STEP model"].set("")
        self.app.select_asset("STEP model")
        self.assertEqual(self.app.model.get(), "")
        self.app.refresh()
        self.assertEqual(self.app.model.get(), "")
        self.assertEqual(self.app.combos["Footprint"].get(), "GEOM.kicad_mod — A/GEOM.kicad_mod")

    def test_restart_keeps_active_zip_instead_of_showing_an_unloaded_newer_download(self):
        self.downloads_mode()
        self.assertTrue(self.app.load_download())
        create_zip(self.downloads / "newer.zip")
        second_root = tk.Toplevel(self.root)
        app = App(second_root, self.workspace)
        self.assertEqual(app.source_choice.get(), "Downloads")
        self.assertEqual(app.download_zip.get(), self.archive.name)
        self.assertEqual(app.combos["Symbol"].get(), "TEST123")
        second_root.destroy()

    def test_failed_zip_selection_restores_active_archive_and_plan(self):
        self.downloads_mode()
        self.assertTrue(self.app.load_download())
        self.app.validate()
        plan = self.app.plan
        broken = self.downloads / "broken.zip"
        broken.write_bytes(b"broken")
        self.app.refresh_downloads()
        self.app.download_zip.set(broken.name)
        with patch("import_gui.messagebox.showerror"):
            self.assertFalse(self.app.load_download())
        self.assertEqual(self.app.download_zip.get(), self.archive.name)
        self.assertIs(self.app.plan, plan)

    def test_folder_selection_persists_without_copying_archives(self):
        another = self.base / "other-downloads"
        another.mkdir()
        self.downloads_mode()
        with patch("import_gui.filedialog.askdirectory", return_value=str(another)):
            self.app.choose_downloads_folder()
        self.assertEqual(self.app.downloads_folder, another)
        self.assertFalse(self.app.download_files)
        self.assertEqual(list(another.iterdir()), [])
        self.assertEqual(Path(load_preferences(self.app.prefs_path)["downloads_folder"]), another)

    def test_folder_save_error_keeps_previous_folder(self):
        another = self.base / "other-downloads"
        another.mkdir()
        with patch("import_gui.filedialog.askdirectory", return_value=str(another)), patch("import_gui.save_preferences", side_effect=OSError("disk full")), patch("import_gui.messagebox.showerror"):
            self.app.choose_downloads_folder()
        self.assertEqual(self.app.downloads_folder, self.downloads)

    def test_missing_download_and_provider_switch_do_not_import_assets(self):
        self.downloads_mode()
        self.archive.unlink()
        with patch("import_gui.messagebox.showerror"):
            self.assertFalse(self.app.load_download())
        self.assertFalse(self.app.download_files)
        self.app.source_choice.set("LCSC")
        self.app.select_source_choice()
        self.assertEqual(self.app.source.get(), "LCSC")
        self.assertFalse((self.workspace / "Symbols").exists())

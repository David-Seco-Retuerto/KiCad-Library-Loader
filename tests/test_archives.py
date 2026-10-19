"""Native ZIP intake uses synthetic vendor-style archives and temporary outputs."""
import hashlib
from pathlib import Path
import stat
import sys
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from archive_import import cache_directory, discard_extraction, extract_native_zip
from import_gui import App
from library_core import SYMBOL_FORMATS, load_preferences
from test_importer import SYMBOL, FOOTPRINT, STEP


def create_zip(path, extra=()):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in [("PART/KiCad/part.kicad_sym", SYMBOL),
                           ("PART/KiCad/GEOM.kicad_mod", FOOTPRINT),
                           ("PART/3D/TEST123.stp", STEP),
                           ("license.txt", "Synthetic licence"),
                           ("PART/part_info.txt", "PartNumber=TEST123"),
                           ("PART/Other/Build.bat", "This must never be extracted"), *extra]:
            archive.writestr(name, data)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.archive = self.workspace / "download.zip"
        create_zip(self.archive)

    def test_extract_native_assets_and_metadata_without_changing_zip(self):
        before = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        result = extract_native_zip(self.archive, self.workspace)
        self.assertEqual(result.parent, cache_directory(self.workspace))
        files = {p.relative_to(result).as_posix() for p in result.rglob("*") if p.is_file()}
        self.assertEqual(files, {"PART/KiCad/part.kicad_sym", "PART/KiCad/GEOM.kicad_mod",
                                 "PART/3D/TEST123.stp", "license.txt", "PART/part_info.txt", ".loader-archive-origin.json"})
        self.assertEqual(hashlib.sha256(self.archive.read_bytes()).hexdigest(), before)
        self.assertFalse((self.workspace / "Symbols").exists())
        second = extract_native_zip(self.archive, self.workspace)
        self.assertNotEqual(result, second)
        self.assertTrue((result / "license.txt").exists())

    def test_unsafe_paths_are_rejected_before_extraction(self):
        for name in ("../escape.kicad_sym", "/absolute.step", "C:/drive.step", "a/../../escape.step",
                     "a\\..\\escape.step", "CON.step", "a/file.step."):
            with self.subTest(name=name):
                create_zip(self.archive, [(name, "blocked")])
                with self.assertRaisesRegex(ValueError, "Unsafe archive path"):
                    extract_native_zip(self.archive, self.workspace)
                self.assertFalse(cache_directory(self.workspace).exists())

    def test_links_are_rejected(self):
        info = zipfile.ZipInfo("link.step")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(self.archive, "a") as archive:
            archive.writestr(info, "outside")
        with self.assertRaisesRegex(ValueError, "links are unsupported"):
            extract_native_zip(self.archive, self.workspace)

    def test_case_insensitive_duplicate_paths_are_rejected(self):
        create_zip(self.archive, [("PART/kicad/PART.kicad_sym", SYMBOL)])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            extract_native_zip(self.archive, self.workspace)

    def test_size_and_entry_limits_are_enforced(self):
        for setting in ("MAX_FILE_BYTES", "MAX_TOTAL_BYTES", "MAX_ENTRIES"):
            with self.subTest(setting=setting), patch("archive_import." + setting, 1):
                with self.assertRaises(ValueError):
                    extract_native_zip(self.archive, self.workspace)
        self.assertFalse(cache_directory(self.workspace).exists())

    def test_legacy_only_archive_explains_conversion(self):
        with zipfile.ZipFile(self.archive, "w") as archive:
            archive.writestr("part.lib", "Legacy fixture")
        with self.assertRaisesRegex(ValueError, "need conversion"):
            extract_native_zip(self.archive, self.workspace)

    def test_invalid_native_files_are_removed_from_cache(self):
        with zipfile.ZipFile(self.archive, "w") as archive:
            archive.writestr("broken.kicad_sym", "broken")
        with self.assertRaisesRegex(ValueError, "No readable"):
            extract_native_zip(self.archive, self.workspace)
        self.assertEqual(list(cache_directory(self.workspace).iterdir()), [])

    def test_broken_zip_is_reported(self):
        self.archive.write_bytes(b"not a ZIP")
        with self.assertRaisesRegex(ValueError, "Cannot read ZIP"):
            extract_native_zip(self.archive, self.workspace)

    def test_failure_after_extraction_cleans_only_new_cache(self):
        existing = extract_native_zip(self.archive, self.workspace)
        with patch("library_core.scan_directory", side_effect=OSError("read failed")):
            with self.assertRaises(OSError):
                extract_native_zip(self.archive, self.workspace)
        self.assertEqual(list(cache_directory(self.workspace).iterdir()), [existing])
        with self.assertRaisesRegex(ValueError, "Refusing"):
            discard_extraction(self.workspace, self.workspace)
        self.assertTrue(existing.exists())

    def test_cache_file_is_rejected(self):
        cache_directory(self.workspace).write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "cache path is a file"):
            extract_native_zip(self.archive, self.workspace)


class ArchiveGuiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.archive = self.workspace / "download.zip"
        create_zip(self.archive)
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.app = App(self.root, self.workspace)

    def test_zip_review_and_import_in_both_formats_preserve_preferences(self):
        before = self.archive.read_bytes()
        for mode in ("unpacked", "packed"):
            with self.subTest(mode=mode):
                self.app.symbol_format.set(SYMBOL_FORMATS[mode])
                with patch("import_gui.filedialog.askopenfilename", return_value=str(self.archive)):
                    self.assertTrue(self.app.open_zip())
                self.assertEqual(self.app.selected_format(), mode)
                self.assertEqual(self.app.fp.get(), "PART/KiCad/GEOM.kicad_mod")
                self.assertEqual(self.app.model.get(), "PART/3D/TEST123.stp")
                self.assertIsNone(self.app.plan)
                self.app.validate()
                self.assertIsNotNone(self.app.plan)
                self.app.ack.set(True)
                self.app.import_component()
                library = self.app.settings.get_category("ICs").symbol_library(self.workspace, mode)
                if mode == "unpacked":
                    self.assertTrue(library.is_dir())
                    self.assertTrue((library / "TEST123.kicad_sym").is_file())
                else:
                    self.assertTrue(library.is_file())
                preferences = load_preferences(self.app.prefs_path)
                self.assertEqual(preferences["symbol_format"], mode)
                self.assertEqual(Path(preferences["paths"]["sources"]["SamacSys"]), self.app.inv.root)
                self.assertTrue(self.app.inv.root.is_dir())
        self.assertEqual(self.archive.read_bytes(), before)

    def test_cancel_leaves_settings_and_preferences_unchanged(self):
        before, settings = self.app.prefs_path.read_bytes(), self.app.settings
        with patch("import_gui.filedialog.askopenfilename", return_value=""):
            self.assertFalse(self.app.open_zip())
        self.assertEqual(self.app.settings, settings)
        self.assertEqual(self.app.prefs_path.read_bytes(), before)
        self.assertFalse(cache_directory(self.workspace).exists())

    def test_save_failure_removes_extraction_and_restores_source(self):
        before, settings = self.app.prefs_path.read_bytes(), self.app.settings
        with patch("import_gui.filedialog.askopenfilename", return_value=str(self.archive)), patch("import_gui.save_preferences", side_effect=OSError("disk full")), patch("import_gui.messagebox.showerror") as error:
            self.assertFalse(self.app.open_zip("LCSC"))
            error.assert_called_once()
        self.assertEqual(self.app.source.get(), "SamacSys")
        self.assertEqual(self.app.settings, settings)
        self.assertEqual(self.app.prefs_path.read_bytes(), before)
        self.assertEqual(list(cache_directory(self.workspace).iterdir()), [])

    def test_search_dialog_hands_zip_to_selected_provider_without_importing(self):
        dialog = self.app.open_search()
        dialog.provider.set("LCSC")
        with patch("import_gui.filedialog.askopenfilename", return_value=str(self.archive)):
            dialog.choose_zip()
        self.assertFalse(dialog.window.winfo_exists())
        self.assertEqual(self.app.source.get(), "LCSC")
        self.assertEqual(len(self.app.inv.symbols), 1)
        self.assertFalse((self.workspace / "Symbols").exists())

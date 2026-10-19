"""Browser handoff and downloaded native exports; no live network or production outputs."""
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from import_gui import App
from library_core import load_preferences
from providers import get_provider
from test_importer import SYMBOL, FOOTPRINT, STEP


class SearchUrlTests(unittest.TestCase):
    def test_provider_urls_encode_search_as_data(self):
        query = 'NE555 + A/B & x=1 #? µ'
        for source, host, path, parameter in (("SamacSys", "ms.componentsearchengine.com", "/search.html", "searchString"),
                                              ("LCSC", "www.lcsc.com", "/search", "q")):
            with self.subTest(source=source):
                url = urlsplit(get_provider(source).search_url("  " + query + "  "))
                self.assertEqual((url.scheme, url.netloc, url.path), ("https", host, path))
                self.assertEqual(parse_qs(url.query), {parameter: [query]})
                self.assertEqual(url.fragment, "")
                self.assertNotIn("+", url.query)  # The SamacSys portal uses decodeURIComponent, not form decoding.

    def test_invalid_search_input_is_rejected(self):
        for value in (None, "", "   ", "A\nB", "A\x00B", "A" * 201):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    get_provider("SamacSys").search_url(value)
        with self.assertRaises(ValueError):
            get_provider("Unknown")


class SearchGuiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.workspace = self.base / "application"
        self.workspace.mkdir()
        self.source = self.workspace / "Imports/SamacSys"
        self.source.mkdir(parents=True)
        self.export = self.base / "extracted-download"
        self.export.mkdir()
        for source in (self.source, self.export):
            (source / "parts.kicad_sym").write_text(SYMBOL, encoding="utf-8")
            (source / "GEOM.kicad_mod").write_text(FOOTPRINT, encoding="utf-8")
            (source / "TEST123.stp").write_bytes(STEP)
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.app = App(self.root, self.workspace)
        self.root.update_idletasks()

    def test_search_is_explicit_prefilled_and_does_not_change_import(self):
        before = self.app.prefs_path.read_bytes()
        settings = self.app.settings
        with patch("search_dialog.webbrowser.open", return_value=True) as browser:
            dialog = self.app.open_search()
            dialog.window.withdraw()
            browser.assert_not_called()
            self.assertEqual(dialog.query.get(), self.app.inv.symbols[self.app.symbol.get()].mpn)
            dialog.provider.set("LCSC")
            dialog.query.set("C123 & TEST")
            self.assertTrue(dialog.open_search())
            browser.assert_called_once_with(get_provider("LCSC").search_url("C123 & TEST"), new=2)
            dialog.window.destroy()
        self.assertEqual(self.app.source.get(), "SamacSys")
        self.assertEqual(self.app.settings, settings)
        self.assertEqual(self.app.prefs_path.read_bytes(), before)
        self.assertFalse((self.workspace / "Symbols").exists())

    def test_failed_browser_and_blank_query_show_actionable_errors(self):
        dialog = self.app.open_search()
        with patch("search_dialog.messagebox.showerror") as error, patch("search_dialog.webbrowser.open", return_value=False) as browser:
            self.assertFalse(dialog.open_search())
            self.assertIn("Copy the URL", error.call_args.args[1])
            browser.reset_mock()
            dialog.query.set("")
            self.assertFalse(dialog.open_search())
            browser.assert_not_called()
        dialog.window.destroy()

    def test_export_handoff_uses_chosen_provider_and_preserves_inputs(self):
        before = {p.name: p.read_bytes() for p in self.export.iterdir()}
        original_samacsys = self.app.settings.sources["SamacSys"]
        self.app.validate()
        self.assertIsNotNone(self.app.plan)
        dialog = self.app.open_search()
        dialog.provider.set("LCSC")
        with patch("import_gui.filedialog.askdirectory", return_value=str(self.export)):
            dialog.choose_folder()
        self.assertFalse(dialog.window.winfo_exists())
        self.assertEqual(self.app.source.get(), "LCSC")
        self.assertEqual(self.app.inv.root, self.export)
        self.assertEqual(self.app.settings.sources["SamacSys"], original_samacsys)
        self.assertEqual(self.app.settings.sources["LCSC"], self.export)
        self.assertEqual(self.app.fp.get(), "GEOM.kicad_mod")
        self.assertIsNone(self.app.plan)
        self.assertEqual(load_preferences(self.app.prefs_path)["source"], "LCSC")
        self.assertEqual({p.name: p.read_bytes() for p in self.export.iterdir()}, before)
        self.assertFalse((self.workspace / "Symbols").exists())
        self.app.validate()
        self.assertIsNotNone(self.app.plan)
        self.app.ack.set(True)
        self.app.import_component()
        self.assertTrue((self.workspace / "Symbols/DVL_ICs.kicad_symdir/TEST123.kicad_sym").is_file())
        self.assertEqual({p.name: p.read_bytes() for p in self.export.iterdir()}, before)

    def test_folder_cancel_keeps_preferences_and_reviewed_plan(self):
        self.app.validate()
        plan = self.app.plan
        before = self.app.prefs_path.read_bytes()
        dialog = self.app.open_search()
        with patch("import_gui.filedialog.askdirectory", return_value=""):
            dialog.choose_folder()
        self.assertTrue(dialog.window.winfo_exists())
        self.assertIs(self.app.plan, plan)
        self.assertEqual(self.app.prefs_path.read_bytes(), before)
        dialog.window.destroy()

    def test_overlapping_export_folder_is_rejected(self):
        output = self.workspace / "Symbols"
        output.mkdir()
        settings, before = self.app.settings, self.app.prefs_path.read_bytes()
        with patch("import_gui.filedialog.askdirectory", return_value=str(output)), patch("import_gui.messagebox.showerror") as error:
            self.assertFalse(self.app.use_export_folder("LCSC"))
            error.assert_called_once()
        self.assertEqual(self.app.settings, settings)
        self.assertEqual(self.app.source.get(), "SamacSys")
        self.assertEqual(self.app.prefs_path.read_bytes(), before)

    def test_save_failure_keeps_source_settings_and_inventory(self):
        settings, inventory = self.app.settings, self.app.inv
        before = self.app.prefs_path.read_bytes()
        with patch("import_gui.filedialog.askdirectory", return_value=str(self.export)), patch("import_gui.save_preferences", side_effect=OSError("disk full")), patch("import_gui.messagebox.showerror") as error:
            self.assertFalse(self.app.use_export_folder("LCSC"))
            error.assert_called_once()
        self.assertEqual(self.app.source.get(), "SamacSys")
        self.assertEqual(self.app.settings, settings)
        self.assertIs(self.app.inv, inventory)
        self.assertEqual(self.app.prefs_path.read_bytes(), before)

    def test_refresh_reports_new_assets_and_keeps_existing_selection(self):
        selected = self.app.symbol.get()
        self.app.validate()
        self.assertIsNotNone(self.app.plan)
        (self.source / "new.kicad_sym").write_text(SYMBOL.replace("TEST123", "NEW456"), encoding="utf-8")
        (self.source / "another.kicad_mod").write_text(FOOTPRINT, encoding="utf-8")
        (self.source / "new.step").write_bytes(STEP)
        self.app.refresh()
        self.assertEqual(self.app.symbol.get(), selected)
        self.assertIsNone(self.app.plan)
        message = self.app.log.get("1.0", "end")
        for phrase in ("New symbols found: NEW456", "New footprints found: another.kicad_mod", "New STEP models found: new.step"):
            self.assertIn(phrase, message)
        self.assertFalse((self.workspace / "Symbols").exists())
        self.app.refresh()
        self.assertNotIn("New symbols found", self.app.log.get("1.0", "end"))

    def test_zip_only_folder_is_reported_without_extraction_or_import(self):
        folder = self.base / "zip-download"
        folder.mkdir()
        archive = folder / "model.zip"
        archive.write_bytes(b"unopened synthetic ZIP placeholder")
        with patch("import_gui.filedialog.askdirectory", return_value=str(folder)):
            self.assertTrue(self.app.use_export_folder())
        self.assertFalse(self.app.inv.symbols)
        self.assertIn("export/extract native KiCad", self.app.log.get("1.0", "end"))
        self.assertEqual(list(folder.iterdir()), [archive])
        self.assertFalse((self.workspace / "Symbols").exists())

    def test_invalid_saved_settings_are_not_replaced_by_folder_handoff(self):
        self.app.settings_error = "Invalid saved configuration"
        before = self.app.prefs_path.read_bytes()
        with patch("import_gui.filedialog.askdirectory") as picker, patch("import_gui.messagebox.showerror") as error:
            self.assertFalse(self.app.use_export_folder())
            picker.assert_not_called()
            error.assert_called_once()
        self.assertEqual(self.app.prefs_path.read_bytes(), before)

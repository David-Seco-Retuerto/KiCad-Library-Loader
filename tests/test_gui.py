"""Tk integration smoke test; does not open a visible window or a STEP viewer."""
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from import_gui import App
from library_core import SYMBOL_FORMATS, load_preferences
from test_importer import SYMBOL, FOOTPRINT, STEP


class GuiTests(unittest.TestCase):
    def test_selection_refresh_preferences_validation_and_import(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory).resolve()
            source = repo / "Imports/SamacSys"
            source.mkdir(parents=True)
            (repo / "Imports/LCSC").mkdir()
            (source / "test.kicad_sym").write_text(SYMBOL, encoding="utf-8")
            (source / "GEOM.kicad_mod").write_text(FOOTPRINT, encoding="utf-8")
            (source / "TEST123.stp").write_bytes(STEP)
            try:
                root = tk.Tk()
            except tk.TclError as exc:
                self.skipTest(f"Tk unavailable: {exc}")
            root.withdraw()
            try:
                app = App(root, repo)
                root.update_idletasks()
                self.assertEqual(app.fp.get(), "GEOM.kicad_mod")
                self.assertEqual(app.model.get(), "TEST123.stp")
                self.assertEqual(app.mode.get(), "Suggestion")
                self.assertEqual(app.selected_format(), "unpacked")
                app.model.set("")
                app.refresh()
                self.assertEqual(app.model.get(), "")
                app.source.set("LCSC")
                app.refresh()
                self.assertEqual(app.symbol.get(), "")
                self.assertIsNone(app.plan)
                app.source.set("SamacSys")
                app.refresh()
                app.mode.set("Custom")
                app.custom.set("User_TEST123")
                app.validate()
                self.assertIsNotNone(app.plan)
                app.ack.set(True)
                app.import_component()
                self.assertTrue((repo / "Symbols/DVL_ICs.kicad_symdir/TEST123.kicad_sym").is_file())
                self.assertFalse((repo / "Symbols/DVL_ICs.kicad_sym").exists())
                self.assertTrue((repo / "Footprints/DVL_ICs.pretty/User_TEST123.kicad_mod").is_file())
                app.symbol_format.set(SYMBOL_FORMATS["packed"])
                self.assertIsNone(app.plan)
                self.assertIn("KiCad 9", app.output.get())
                app.validate()
                self.assertTrue(any("other output format" in w for w in app.plan.warnings))
                self.assertEqual(str(app.import_button["state"]), "disabled")
                app.ack.set(True)
                app.import_component()
                self.assertTrue((repo / "Symbols/DVL_ICs.kicad_sym").is_file())
                app.close()
                prefs = load_preferences(repo / ".kicad-importer.json")
                self.assertEqual(prefs["mode"], "Custom")
                self.assertEqual(prefs["symbol_format"], "packed")
                root = tk.Tk()
                root.withdraw()
                second = App(root, repo)
                self.assertEqual(second.custom.get(), "User_TEST123")
                self.assertEqual(second.mode.get(), "Custom")
                self.assertEqual(second.selected_format(), "packed")
            finally:
                try:
                    root.update_idletasks()
                    root.destroy()
                except tk.TclError:
                    pass


if __name__ == "__main__":
    unittest.main()

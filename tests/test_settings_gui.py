"""Hidden-window integration tests for saving and applying folder settings."""
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from import_gui import App
from library_core import load_preferences, save_preferences
from loader_settings import LoaderSettings, MODEL_PATH_MODES
from test_importer import SYMBOL, FOOTPRINT, STEP


class FolderSettingsGuiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.workspace = self.base / "application"
        self.workspace.mkdir()
        self.source = self.base / "external-exports"
        self.source.mkdir()
        (self.source / "parts.kicad_sym").write_text(SYMBOL, encoding="utf-8")
        (self.source / "GEOM.kicad_mod").write_text(FOOTPRINT, encoding="utf-8")
        (self.source / "TEST123.stp").write_bytes(STEP)
        self.destination = self.base / "separate-library"
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.withdraw()
        self.root.update_idletasks()
        self.addCleanup(self.destroy_root)

    def destroy_root(self):
        self.root.update_idletasks()
        self.root.destroy()

    def settings(self, output=None):
        return LoaderSettings({"SamacSys": self.source, "LCSC": self.base / "missing-lcsc"},
                              output or self.destination, "absolute").validated(self.workspace)

    def test_settings_dialog_imports_to_external_root_and_survives_restart(self):
        app = App(self.root, self.workspace)
        self.assertFalse((self.workspace / "Imports").exists())
        dialog = app.open_settings()
        dialog.window.withdraw()
        dialog.sources["SamacSys"].set(str(self.source))
        dialog.sources["LCSC"].set(str(self.base / "missing-lcsc"))
        dialog.output_root.set(str(self.destination))
        dialog.model_mode.set(MODEL_PATH_MODES["absolute"])
        dialog.save()
        self.assertFalse(dialog.window.winfo_exists())
        self.assertEqual(app.settings, self.settings())
        self.assertEqual(app.inv.root, self.source)
        self.assertEqual(app.model.get(), "TEST123.stp")
        self.assertIn(str(self.destination), app.output.get())
        self.assertFalse(self.destination.exists())
        app.validate()
        self.assertIsNotNone(app.plan)
        app.import_component()
        self.assertTrue((self.destination / "Symbols/DVL_ICs.kicad_symdir/TEST123.kicad_sym").is_file())
        self.assertFalse((self.workspace / "Symbols").exists())
        window = tk.Toplevel(self.root)
        window.withdraw()
        second = App(window, self.workspace)
        self.assertEqual(second.settings, app.settings)
        self.assertEqual(second.inv.root, self.source)
        second.close()

    def test_changing_output_invalidates_the_plan_without_moving_assets(self):
        app = App(self.root, self.workspace)
        app.apply_settings(self.settings())
        app.validate()
        old_plan = app.plan
        self.assertIsNotNone(old_plan)
        new_output = self.base / "another-library"
        app.apply_settings(self.settings(new_output))
        self.assertIsNone(app.plan)
        self.assertFalse(app.ack.get())
        self.assertEqual(str(app.import_button["state"]), "disabled")
        self.assertFalse(self.destination.exists())
        self.assertFalse(new_output.exists())
        app.validate()
        self.assertEqual(app.plan.output_root, new_output)

    def test_cancel_and_invalid_save_leave_active_settings_and_preferences_unchanged(self):
        app = App(self.root, self.workspace)
        app.apply_settings(self.settings())
        before = app.prefs_path.read_bytes()
        app.validate()
        old_plan = app.plan
        dialog = app.open_settings()
        dialog.window.withdraw()
        dialog.output_root.set(str(self.source))
        with patch("settings_dialog.messagebox.showerror") as error:
            dialog.save()
            error.assert_called_once()
        self.assertEqual(app.settings, self.settings())
        self.assertIs(app.plan, old_plan)
        self.assertTrue(dialog.window.winfo_exists())
        dialog.restore_defaults()
        dialog.window.destroy()
        self.assertEqual(app.prefs_path.read_bytes(), before)

    def test_invalid_saved_paths_are_reported_and_not_silently_overwritten(self):
        path = self.workspace / ".kicad-importer.json"
        save_preferences(path, {"mode": "Custom", "paths": {"sources": {"SamacSys": ""}}})
        old = path.read_bytes()
        app = App(self.root, self.workspace)
        self.assertTrue(app.settings_error)
        app.custom.set("Name")
        app.validate()
        self.assertIsNone(app.plan)
        self.assertIn("Correct the saved folder settings", app.log.get("1.0", "end"))
        self.assertEqual(path.read_bytes(), old)
        app.apply_settings(self.settings())
        self.assertIsNone(app.settings_error)
        self.assertEqual(app.settings.output_root, self.destination)

    def test_unsaved_settings_cannot_replace_active_output_on_io_error(self):
        app = App(self.root, self.workspace)
        old = app.settings
        with patch.object(app, "write_preferences", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                app.apply_settings(self.settings())
        self.assertEqual(app.settings, old)
        self.assertFalse(self.destination.exists())

    def test_corrupt_json_blocks_import_and_is_preserved_until_explicit_save(self):
        path = self.workspace / ".kicad-importer.json"
        path.write_text('{"paths": broken-json')
        old = path.read_bytes()
        app = App(self.root, self.workspace)
        self.assertTrue(app.settings_error)
        app.custom.set("Do_not_overwrite_settings")
        app.validate()
        self.assertIsNone(app.plan)
        self.assertEqual(path.read_bytes(), old)
        app.apply_settings(self.settings())
        self.assertIsNone(app.settings_error)
        self.assertEqual(load_preferences(path)["paths"]["output_root"], str(self.destination))

    def test_legacy_ui_preferences_remain_intact_when_paths_are_added(self):
        path = self.workspace / ".kicad-importer.json"
        save_preferences(path, {"mode": "Custom", "custom": "Keep_this", "category": "Misc",
                                "symbol_format": "packed", "extension_metadata": {"keep": True}})
        app = App(self.root, self.workspace)
        app.apply_settings(self.settings())
        saved = load_preferences(path)
        self.assertEqual(app.custom.get(), "Keep_this")
        self.assertEqual(app.category.get(), "Misc")
        self.assertEqual(app.selected_format(), "packed")
        self.assertTrue(saved["extension_metadata"]["keep"])
        self.assertEqual(saved["paths"]["output_root"], str(self.destination))


if __name__ == "__main__":
    unittest.main()

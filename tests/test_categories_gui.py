"""Category editor, creation preview and custom import through Tk."""
from dataclasses import replace
from pathlib import Path
import sys
import tkinter as tk
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from import_gui import App
from library_core import ImportErrorDetail, SYMBOL_FORMATS, children, load_preferences, prop, read_tree
from library_layout import LibraryCategory
import test_settings_gui as fixtures


class CategoryGuiTests(unittest.TestCase):
    setUp = fixtures.FolderSettingsGuiTests.setUp
    destroy_root = fixtures.FolderSettingsGuiTests.destroy_root
    settings = fixtures.FolderSettingsGuiTests.settings

    def custom(self):
        return replace(self.settings(), categories=(LibraryCategory("Analog", "MyLib_Analog", "Analog_Models"),))

    def test_editor_saves_custom_category_and_folder_dialog_preserves_it(self):
        app = App(self.root, self.workspace)
        app.apply_settings(self.settings())
        dialog = app.open_categories()
        dialog.window.withdraw()
        dialog.name.set("Analog")
        dialog.library_name.set("MyLib_Analog")
        dialog.model_folder.set("Analog_Models")
        dialog.add()
        dialog.save()
        self.assertFalse(dialog.window.winfo_exists())
        self.assertIn("Analog", app.category_combo["values"])
        self.assertFalse(self.destination.exists())
        folder_dialog = app.open_settings()
        folder_dialog.window.withdraw()
        folder_dialog.save()
        self.assertEqual(app.settings.get_category("Analog").library_name, "MyLib_Analog")
        saved = load_preferences(app.prefs_path)
        self.assertEqual(saved["categories"][-1]["library_name"], "MyLib_Analog")
        window = tk.Toplevel(self.root)
        window.withdraw()
        second = App(window, self.workspace)
        self.assertEqual(second.settings.categories, app.settings.categories)
        second.close()

    def test_folder_preview_creates_correct_suffixes_without_importing_symbols(self):
        app = App(self.root, self.workspace)
        app.apply_settings(self.custom())
        preview = app.prepare_library_folders()
        preview.window.withdraw()
        self.assertFalse(self.destination.exists())
        preview.create()
        self.assertFalse(preview.window.winfo_exists())
        self.assertTrue((self.destination / "Symbols/MyLib_Analog.kicad_symdir").is_dir())
        self.assertTrue((self.destination / "Footprints/MyLib_Analog.pretty").is_dir())
        self.assertTrue((self.destination / "3DModels/Analog_Models").is_dir())
        self.assertFalse(list(self.destination.rglob("*.kicad_sym")))
        self.assertFalse(app.ack.get())
        app.validate()
        self.assertIsNotNone(app.plan)
        app.import_component()
        path = self.destination / "Symbols/MyLib_Analog.kicad_symdir/TEST123.kicad_sym"
        self.assertTrue(prop(children(read_tree(path), "symbol")[0], "Footprint").startswith("MyLib_Analog:"))

    def test_packed_folder_preparation_defers_symbol_file_until_import(self):
        app = App(self.root, self.workspace)
        app.apply_settings(self.custom())
        app.symbol_format.set(SYMBOL_FORMATS["packed"])
        preview = app.prepare_library_folders()
        preview.window.withdraw()
        preview.create()
        target = self.destination / "Symbols/MyLib_Analog.kicad_sym"
        self.assertFalse(target.exists())
        app.validate()
        app.import_component()
        self.assertTrue(target.is_file())
        self.assertFalse((self.destination / "Symbols/MyLib_Analog.kicad_symdir").exists())

    def test_invalid_category_and_suffix_do_not_change_saved_settings(self):
        app = App(self.root, self.workspace)
        before = app.prefs_path.read_bytes()
        dialog = app.open_categories()
        dialog.window.withdraw()
        dialog.name.set("Analog")
        dialog.library_name.set("Wrong.pretty")
        with patch("categories_dialog.messagebox.showerror") as error:
            dialog.add()
            error.assert_called_once()
        self.assertEqual(len(dialog.categories), 4)
        self.assertEqual(app.prefs_path.read_bytes(), before)
        dialog.window.destroy()

    def test_editor_update_remove_and_cancel_do_not_delete_libraries(self):
        app = App(self.root, self.workspace)
        app.apply_settings(self.custom())
        app.validate()
        app.import_component()
        old = self.destination / "Symbols/MyLib_Analog.kicad_symdir/TEST123.kicad_sym"
        data = old.read_bytes()
        dialog = app.open_categories()
        dialog.window.withdraw()
        dialog.tree.selection_set("0")
        dialog.select()
        dialog.name.set("Converters")
        dialog.library_name.set("Lab_Converters")
        dialog.update()
        dialog.save()
        self.assertEqual(app.category.get(), "Converters")
        self.assertIn("Lab_Converters", app.output.get())
        self.assertEqual(old.read_bytes(), data)
        dialog = app.open_categories()
        dialog.window.withdraw()
        dialog.tree.selection_set("0")
        dialog.remove()
        with patch("categories_dialog.messagebox.showerror") as error:
            dialog.save()
            error.assert_called_once()
        self.assertTrue(dialog.window.winfo_exists())
        dialog.restore_defaults()
        dialog.window.destroy()
        self.assertEqual(app.category.get(), "Converters")
        self.assertEqual(old.read_bytes(), data)

    def test_preparation_rejects_stale_settings(self):
        app = App(self.root, self.workspace)
        app.apply_settings(self.custom())
        preview = app.prepare_library_folders()
        preview.window.withdraw()
        old_settings = app.settings
        app.apply_settings(replace(app.settings, categories=(LibraryCategory("New", "NewLib", "NewModels"),)))
        with self.assertRaisesRegex(ImportErrorDetail, "Settings changed"):
            app.create_library_folders(old_settings, "unpacked", preview.plan)
        self.assertFalse(self.destination.exists())
        preview.window.destroy()

    def test_no_reviewed_edits_are_silently_discarded_on_save(self):
        app = App(self.root, self.workspace)
        dialog = app.open_categories()
        dialog.window.withdraw()
        dialog.name.set("Unsaved category")
        with patch("categories_dialog.messagebox.showerror") as error:
            dialog.save()
            error.assert_called_once()
        self.assertTrue(dialog.window.winfo_exists())
        self.assertIsNone(app.settings.get_category("Unsaved category"))
        dialog.window.destroy()


if __name__ == "__main__":
    unittest.main()

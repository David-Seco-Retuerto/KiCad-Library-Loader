"""GUI workflow regressions for review state, small windows and tool navigation."""
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from import_gui import App
from test_importer import SYMBOL, FOOTPRINT, STEP


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        source = self.workspace / "Imports/SamacSys"
        source.mkdir(parents=True)
        (source / "part.kicad_sym").write_text(SYMBOL, encoding="utf-8")
        (source / "GEOM.kicad_mod").write_text(FOOTPRINT, encoding="utf-8")
        (source / "TEST123.stp").write_bytes(STEP)
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.app = App(self.root, self.workspace)

    def test_review_state_and_import_gate_follow_selection_changes(self):
        app = self.app
        self.assertEqual(app.workflow_status.get(), "Review required")
        self.assertEqual(str(app.import_button['state']), 'disabled')
        app.validate()
        self.assertIsNotNone(app.plan)
        self.assertEqual(app.workflow_status.get(), "Review warnings" if app.plan.warnings else "Ready to import")
        app.ack.set(True)
        self.assertEqual(app.workflow_status.get(), "Ready to import")
        self.assertEqual(str(app.import_button['state']), 'normal')
        app.custom.set("changed")
        self.assertEqual(app.workflow_status.get(), "Review required")
        self.assertFalse(app.ack.get())
        self.assertIsNone(app.plan)
        self.assertEqual(str(app.import_button['state']), 'disabled')

    def test_asset_preview_controls_empty_states_and_simultaneous_views(self):
        app = self.app
        self.assertEqual(str(app.model_button['state']), 'normal')
        app.model.set("")
        app.fp.set("")
        app.changed()
        self.assertEqual(str(app.model_button['state']), 'disabled')
        self.assertEqual(str(app.fp_svg_button['state']), 'disabled')
        self.assertTrue(app.fp_view.canvas.find_withtag('empty-state'))
        app.symbol.set("")
        app.changed()
        self.assertEqual(app.workflow_status.get(), "Select a component")
        self.assertTrue(app.symbol_view.canvas.find_withtag('empty-state'))

    def test_locations_dialog_is_read_only_and_keeps_review_and_assets(self):
        app = self.app
        app.validate()
        app.ack.set(True)
        plan = app.plan
        assets = {p: p.read_bytes() for p in self.workspace.rglob('*') if p.is_file()}
        window = app.show_locations()
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        text = next(w for w in descendants(window) if isinstance(w, tk.Text))
        self.assertEqual(str(text['state']), 'disabled')
        self.assertIn(str(app.settings.output_root), text.get('1.0', 'end'))
        self.assertIn('Destination:', text.get('1.0', 'end'))
        window.destroy()
        self.assertIs(app.plan, plan)
        self.assertTrue(app.ack.get())
        self.assertEqual({p: p.read_bytes() for p in self.workspace.rglob("*") if p.is_file()}, assets)

    def test_library_tools_route_to_existing_dialogs_without_implicit_writes(self):
        app = self.app
        self.assertEqual(list(app.tool_buttons), ['Settings…', 'Categories…', 'Check KiCad setup…', 'Import history…'])
        with patch('import_gui.FolderSettingsDialog') as settings:
            app.tool_buttons['Settings…'].invoke()
            settings.assert_called_once()
        self.assertFalse((self.workspace / 'Symbols').exists())

    def test_minimum_window_keeps_import_actions_visible_and_form_scrollable(self):
        app = self.app
        self.root.geometry('1000x680+0+0')
        self.root.deiconify()
        self.root.update()
        for widget in (app.import_button, app.validate_button, app.review_checkbox):
            self.assertTrue(widget.winfo_viewable())
            self.assertGreaterEqual(widget.winfo_rooty(), self.root.winfo_rooty())
            self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(), self.root.winfo_rooty() + self.root.winfo_height())
            self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(), self.root.winfo_rootx() + self.root.winfo_width())
        self.assertGreater(app.form.winfo_height(), app.form_canvas.winfo_height())
        app.form_canvas.yview_moveto(1)
        self.root.update()
        self.assertLess(app.entry.winfo_rooty(), app.form_canvas.winfo_rooty() + app.form_canvas.winfo_height())
        self.assertGreaterEqual(app.entry.winfo_rooty(), app.form_canvas.winfo_rooty())
        # Small preview panes fit the geometry rather than using a hidden 200px minimum.
        canvas = app.symbol_view.canvas
        for item in canvas.find_all():
            if canvas.type(item) in ('line', 'rectangle', 'polygon'):
                coords = canvas.coords(item)
                self.assertTrue(all(-1 <= y <= canvas.winfo_height() + 1 for y in coords[1::2]))
        app.validate()
        self.root.update()
        self.assertGreater(app.log.winfo_height(), 45)
        self.assertTrue(app.symbol_view.winfo_viewable())
        self.assertTrue(app.fp_view.winfo_viewable())
        self.assertLess(app.symbol_view.winfo_rootx(), app.fp_view.winfo_rootx())
        self.assertGreater(app.log.winfo_rooty(), app.symbol_view.winfo_rooty() + app.symbol_view.winfo_height())
        self.root.withdraw()

    def test_download_controls_show_and_hide_without_resetting_the_review(self):
        app = self.app
        app.validate()
        plan = app.plan
        app.source_choice.set('Downloads')
        app.update_downloads_panel()
        self.assertEqual(app.download_frame.winfo_manager(), 'pack')
        self.assertEqual(app.download_status_label.winfo_manager(), 'pack')
        app.source_choice.set('SamacSys')
        app.update_downloads_panel()
        self.assertEqual(app.download_frame.winfo_manager(), '')
        self.assertIs(app.plan, plan)

    def test_expanded_preview_preserves_selection_and_review(self):
        app = self.app
        app.validate()
        app.ack.set(True)
        plan, selection = app.plan, (app.symbol.get(), app.fp.get(), app.model.get())
        window = app.expand_preview('symbol')
        self.assertEqual(window.title(), 'Symbol preview')
        window.destroy()
        self.assertIs(app.plan, plan)
        self.assertEqual((app.symbol.get(), app.fp.get(), app.model.get()), selection)
        self.assertTrue(app.ack.get())

    def test_download_wrapper_releases_its_height_when_returning_to_provider(self):
        app = self.app
        self.root.deiconify()
        self.root.update()
        baseline = app.source_card.winfo_height()
        for _ in range(2):
            app.source_choice.set('Downloads')
            app.update_downloads_panel()
            self.root.update()
            self.assertGreater(app.source_card.winfo_height(), baseline + 80)
            app.source_choice.set('SamacSys')
            app.update_downloads_panel()
            self.root.update()
            self.assertEqual(app.download_wrapper.winfo_manager(), '')
            self.assertLessEqual(app.source_card.winfo_height(), baseline + 2)
        self.root.withdraw()

    def test_output_names_match_each_planned_asset_in_all_naming_modes(self):
        app = self.app
        for mode in ('Original', 'Suggestion', 'Custom'):
            app.mode.set(mode)
            app.custom.set('MyPart')
            app.validate()
            self.assertIsNotNone(app.plan)
            paths = {role: path for path, role in app.plan.assets.items()}
            self.assertEqual(app.output_names['Symbol'].get(), 'DVL_ICs:TEST123')
            self.assertEqual(app.output_names['Footprint'].get(), paths['footprint'].name)
            self.assertEqual(app.output_names['STEP model'].get(), paths['model'].name)
        app.model.set('')
        app.changed()
        self.assertEqual(app.output_names['STEP model'].get(), 'Skipped')

    def test_colored_report_preserves_messages_and_separates_semantic_blocks(self):
        app = self.app
        text = ('Input folder: demo\nLibrary output root: target\nImport history folder: history\n'
                'Symbol output: KiCad 10+\nSymbol destination: part.kicad_sym\n'
                'Register symbol folder in KiCad: symbols\nLibrary nickname: Demo\n'
                'Write: part.kicad_mod\nWARNING: a warning\nPlan valid. Safe to import.\nERROR: example error')
        app.log_text(text)
        rendered = app.log.get('1.0', 'end')
        for line in text.splitlines():
            self.assertIn(line, rendered)
        self.assertIn('Import history folder: history\n\nSymbol output:', rendered)
        for marker, tag in (('Input folder:', 'info'), ('WARNING:', 'warning'), ('Plan valid.', 'success'), ('ERROR:', 'error')):
            index = app.log.search(marker, '1.0')
            self.assertIn(tag, app.log.tag_names(index))
        self.assertEqual(app.log.tag_cget('info', 'foreground'), '#000000')
        # Warning words inside filenames must not turn ordinary paths orange.
        app.log_text('Write: warnings_error.kicad_mod')
        self.assertIn('info', app.log.tag_names('1.0'))

    def test_categories_save_and_prepare_requires_successful_save_first(self):
        app = self.app
        with patch.object(app, 'prepare_library_folders') as prepare:
            dialog = app.open_categories()
            self.assertFalse((self.workspace / 'Symbols').exists())
            dialog.categories = []
            with patch('categories_dialog.messagebox.showerror'):
                dialog.save(prepare=True)
            prepare.assert_not_called()
            self.assertTrue(dialog.window.winfo_exists())
            dialog.categories = list(app.settings.categories)
            dialog.save(prepare=True)
            prepare.assert_called_once()
            self.assertFalse((self.workspace / 'Symbols').exists())

    def test_combobox_repeated_popup_focus_does_not_scroll_form(self):
        app = self.app
        self.root.geometry('1000x680+0+0')
        self.root.deiconify()
        self.root.update()
        app.form_canvas.yview_moveto(.18)
        self.root.update()
        combo = app.combos['Symbol']
        start = app.form_canvas.yview()
        combo.focus_force()
        self.root.update()
        for _ in range(2):
            combo.event_generate('<ButtonPress-1>', x=combo.winfo_width() - 8, y=10)
            self.root.update()
            combo.tk.call('ttk::combobox::Unpost', str(combo))
            app.form.event_generate('<FocusIn>')
            self.root.update()
            self.assertEqual(app.form_canvas.yview(), start)
        self.root.withdraw()

    def test_tab_to_offscreen_custom_entry_still_reveals_it(self):
        app = self.app
        app.mode.set('Custom')
        self.root.geometry('1000x680+0+0')
        self.root.deiconify()
        self.root.update()
        app.form_canvas.yview_moveto(0)
        previous_path = self.root.tk.call('tk_focusPrev', str(app.entry))
        previous = self.root.nametowidget(previous_path)
        previous.focus_force()
        self.root.update()
        previous.event_generate('<KeyPress-Tab>')
        self.root.update()
        self.assertEqual(self.root.focus_get(), app.entry)
        self.assertGreater(app.form_canvas.yview()[0], 0)
        self.assertGreaterEqual(app.entry.winfo_rooty(), app.form_canvas.winfo_rooty())
        self.assertLessEqual(app.entry.winfo_rooty() + app.entry.winfo_height(), app.form_canvas.winfo_rooty() + app.form_canvas.winfo_height())
        self.root.withdraw()

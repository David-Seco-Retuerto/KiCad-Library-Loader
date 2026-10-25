"""Synthetic acquisition tests; never access a provider or production library."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import lcsc_download as acquisition
from archive_import import cache_directory
from import_gui import App
from import_history import ACQUISITION_FILE, read_history
from library_core import (associate, build_plan, commit_plan, load_preferences, scan_directory)
from test_importer import SYMBOL, FOOTPRINT, STEP


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name).resolve()
        self.tool = self.workspace / "external venv/Scripts/easyeda2kicad.exe"
        self.tool.parent.mkdir(parents=True)
        self.tool.write_bytes(b"synthetic executable; never run")
        self.created_commands = []

    def populate(self, folder, model=True, requested="C2040"):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "component.kicad_sym").write_text(SYMBOL.replace('(property "Manufacturer_Part_Number"',
            f'(property "LCSC Part" "{requested}") (property "Manufacturer_Part_Number"'), encoding="utf-8")
        (folder / "GEOM.kicad_mod").write_text(FOOTPRINT.replace("TEST123.stp", "GEOM.wrl"), encoding="utf-8")
        if model:
            (folder / "GEOM.step").write_bytes(STEP)
        return folder

    def fake_popen(self, command, **kwargs):
        self.created_commands.append((command, kwargs))
        self.populate(Path(command[-1]).parent)
        kwargs["stdout"].write(b"-- easyeda2kicad.py v1.0.1 --\n")
        class Process:
            returncode = 0
            def poll(self):
                return self.returncode
        return Process()

    def run_download(self, **kwargs):
        return acquisition.download_lcsc(self.workspace, str(self.tool), "c2040", **kwargs)

    def test_explicit_single_code_command_cache_and_metadata(self):
        with patch("lcsc_download.subprocess.Popen", side_effect=self.fake_popen):
            first = self.run_download()
            second = self.run_download()
        self.assertNotEqual(first.folder, second.folder)
        command, options = self.created_commands[0]
        self.assertEqual(command[:4], [str(self.tool), "--full", "--lcsc_id", "C2040"])
        self.assertEqual(command[4], "--output")
        self.assertEqual(options["cwd"], first.folder.parent)
        self.assertIs(options["shell"], False)
        self.assertNotIn("--overwrite", command)
        self.assertNotIn("--use-cache", command)
        self.assertFalse((self.workspace / "Symbols").exists())
        metadata = json.loads((first.folder / ACQUISITION_FILE).read_text())
        self.assertEqual(metadata["lcsc_id"], "C2040")
        self.assertEqual(metadata["tool_version"], "1.0.1")
        self.assertEqual(len(metadata["files"]), 3)
        self.assertFalse(first.notices)
        self.assertFalse(scan_directory(first.folder).notices)

    def test_invalid_codes_and_missing_tool_do_not_start_or_create_cache(self):
        with patch("lcsc_download.subprocess.Popen") as launch:
            for code in ("", "RP2040", "C0", "C2040 --full", "C2040\nC2", "../C2040", "https://lcsc.com/C2040"):
                with self.subTest(code=code), self.assertRaises(ValueError):
                    acquisition.download_lcsc(self.workspace, str(self.tool), code)
            with self.assertRaises(ValueError):
                acquisition.download_lcsc(self.workspace, "missing.exe", "C2040")
            launch.assert_not_called()
        self.assertFalse(cache_directory(self.workspace).exists())

    def test_nonzero_exit_or_empty_native_result_is_cleaned(self):
        for failure in ("exit", "empty", "wrong part"):
            def launch(command, **kwargs):
                process = self.fake_popen(command, **kwargs)
                if failure == "exit":
                    process.returncode = 1
                    kwargs["stdout"].write(b"synthetic network failure")
                elif failure == "empty":
                    for path in Path(command[-1]).parent.iterdir():
                        path.unlink()
                else:
                    path = Path(command[-1]).parent / "component.kicad_sym"
                    path.write_text(path.read_text().replace("C2040", "C999"), encoding="utf-8")
                return process
            with patch("lcsc_download.subprocess.Popen", side_effect=launch), self.assertRaises(ValueError):
                self.run_download()
            self.assertEqual(list(cache_directory(self.workspace).iterdir()), [])

    def test_cancellation_before_start_and_during_process_terminate_and_clean(self):
        cancelled = threading.Event()
        cancelled.set()
        with patch("lcsc_download.subprocess.Popen") as launch, self.assertRaises(acquisition.DownloadCancelled):
            self.run_download(cancelled=cancelled)
        launch.assert_not_called()
        cancelled.clear()
        state = {"terminated": False}
        def launch(command, **kwargs):
            cancelled.set()
            class Process:
                returncode = None
                def poll(self):
                    return self.returncode
                def terminate(self):
                    state["terminated"] = True
                    self.returncode = -1
                def wait(self, timeout):
                    return self.returncode
            return Process()
        with patch("lcsc_download.subprocess.Popen", side_effect=launch), self.assertRaises(acquisition.DownloadCancelled):
            self.run_download(cancelled=cancelled)
        self.assertTrue(state["terminated"])
        self.assertFalse(list(cache_directory(self.workspace).iterdir()))

    def test_timeout_kills_a_process_that_ignores_termination(self):
        state = {"killed": False}
        class Process:
            returncode = None
            def poll(self):
                return self.returncode
            def terminate(self):
                pass
            def wait(self, timeout):
                if self.returncode is None:
                    raise acquisition.subprocess.TimeoutExpired("fake", timeout)
                return self.returncode
            def kill(self):
                state["killed"] = True
                self.returncode = -1
        with patch("lcsc_download.subprocess.Popen", return_value=Process()), self.assertRaisesRegex(ValueError, "timed out"):
            self.run_download(timeout=-1)
        self.assertTrue(state["killed"])
        self.assertFalse(list(cache_directory(self.workspace).iterdir()))

    def test_oversized_output_is_cleaned_and_unrelated_files_are_preserved(self):
        unrelated = self.workspace / "keep.txt"
        unrelated.write_text("keep", encoding="utf-8")
        with patch("lcsc_download.subprocess.Popen", side_effect=self.fake_popen), patch("lcsc_download.MAX_FILE_BYTES", 8), self.assertRaisesRegex(ValueError, "size limits"):
            self.run_download()
        self.assertEqual(unrelated.read_text(), "keep")
        self.assertFalse(list(cache_directory(self.workspace).iterdir()))
        with self.assertRaisesRegex(ValueError, "Refusing"):
            acquisition.discard_download(self.workspace / "assets", self.workspace)

    def test_absent_step_is_reported_without_fabricating_one(self):
        def launch(command, **kwargs):
            process = self.fake_popen(command, **kwargs)
            (Path(command[-1]).parent / "GEOM.step").unlink()
            return process
        with patch("lcsc_download.subprocess.Popen", side_effect=launch):
            result = self.run_download()
        self.assertIn("No unambiguous STEP", result.notices[0])
        self.assertFalse(scan_directory(result.folder).models)

    def test_wrl_step_association_is_unique_and_never_arbitrary(self):
        folder = self.populate(self.workspace / "source")
        inv = scan_directory(folder)
        key = next(iter(inv.symbols))
        self.assertEqual(associate(inv, inv.symbols[key]), ("GEOM.kicad_mod", "GEOM.step"))
        (folder / "another").mkdir()
        (folder / "another/GEOM.stp").write_bytes(STEP)
        # A matching symbol-named model must not override the ambiguous WRL counterparts.
        (folder / "TEST123.step").write_bytes(STEP)
        inv = scan_directory(folder)
        self.assertEqual(associate(inv, inv.symbols[key])[1], "")

    def test_acquisition_provenance_is_added_to_both_import_formats(self):
        with patch("lcsc_download.subprocess.Popen", side_effect=self.fake_popen):
            result = self.run_download()
        inv = scan_directory(result.folder)
        key = next(iter(inv.symbols))
        fp, model = associate(inv, inv.symbols[key])
        for mode in ("packed", "unpacked"):
            output = self.workspace / mode
            plan = build_plan(self.workspace, inv, key, fp, model, "ICs", "Original", symbol_format=mode, output_root=output)
            commit_plan(output, plan)
            record = read_history(output)[0][0]
            self.assertEqual(record["source_acquisition"]["lcsc_id"], "C2040")
            self.assertIsNone(record["source_archive"])

    def test_process_launch_error_cleans_new_cache(self):
        with patch("lcsc_download.subprocess.Popen", side_effect=OSError("cannot execute")), self.assertRaisesRegex(OSError, "cannot execute"):
            self.run_download()
        self.assertFalse(list(cache_directory(self.workspace).iterdir()))


    def test_loader_converter_discovery_is_limited_to_its_python_environment(self):
        folder = self.workspace / "loader-scripts"
        folder.mkdir()
        name = "easyeda2kicad.exe" if acquisition.os.name == "nt" else "easyeda2kicad"
        with self.assertRaisesRegex(ValueError, "dependency is missing"):
            acquisition.installed_converter(folder)
        target = folder / name
        target.write_bytes(b"fixture; never run")
        with patch("lcsc_download.sysconfig.get_path", return_value=str(folder)) as scripts:
            self.assertEqual(acquisition.installed_converter(), target)
            scripts.assert_called_once_with("scripts")



class DownloadGuiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name).resolve()
        self.tool = self.workspace / "external/easyeda2kicad.exe"
        self.tool.parent.mkdir()
        self.tool.write_bytes(b"fake")
        source = self.workspace / "Imports/SamacSys"
        source.mkdir(parents=True)
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
        self.app.validate()
        self.before_plan = self.app.plan
        self.before_settings = self.app.settings

    def dialog(self):
        dialog = self.app.open_lcsc_download("C2040")
        dialog.executable.set(str(self.tool))
        dialog.use_external.set(True)
        dialog.toggle_external()
        return dialog

    def wait_for(self, dialog):
        deadline = time.monotonic() + 5
        while dialog.running and not dialog.closed and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.assertFalse(dialog.running)

    def result(self):
        cache = cache_directory(self.workspace)
        cache.mkdir(exist_ok=True)
        folder = cache / "lcsc-synthetic/assets"
        DownloadTests.populate(self, folder)
        return acquisition.DownloadResult(folder, "C2040")

    def test_success_loads_for_review_preserves_layout_and_requires_explicit_import(self):
        result = self.result()
        dialog = self.dialog()
        original_format = self.app.symbol_format.get()
        with patch("lcsc_dialog.download_lcsc", return_value=result) as download:
            self.assertTrue(dialog.start())
            self.assertFalse(dialog.start())
            self.wait_for(dialog)
            download.assert_called_once()
        self.assertEqual(self.app.source_choice.get(), "LCSC")
        self.assertEqual(self.app.inv.root, result.folder)
        self.assertEqual(self.app.model.get(), "GEOM.step")
        self.assertEqual(self.app.symbol_format.get(), original_format)
        self.assertEqual(self.app.settings.output_root, self.before_settings.output_root)
        self.assertEqual(self.app.settings.sources["SamacSys"], self.before_settings.sources["SamacSys"])
        self.assertIsNone(self.app.plan)
        self.assertFalse(self.app.ack.get())
        self.assertFalse((self.workspace / "Symbols").exists())
        self.assertEqual(load_preferences(self.app.prefs_path)["easyeda2kicad_executable"], str(self.tool))
        self.assertTrue(result.folder.exists())

    def test_failure_keeps_existing_input_review_and_acknowledgement(self):
        dialog = self.dialog()
        self.app.ack.set(True)
        with patch("lcsc_dialog.download_lcsc", side_effect=ValueError("no model/network error")), patch("lcsc_dialog.messagebox.showerror"):
            dialog.start()
            self.wait_for(dialog)
        self.assertEqual(self.app.settings, self.before_settings)
        self.assertIs(self.app.plan, self.before_plan)
        self.assertTrue(self.app.ack.get())
        self.assertEqual(self.app.source.get(), "SamacSys")

    def test_invalid_code_or_preferences_failure_does_not_launch(self):
        dialog = self.dialog()
        with patch("lcsc_dialog.download_lcsc") as download, patch("lcsc_dialog.messagebox.showerror"):
            dialog.code.set("RP2040")
            self.assertFalse(dialog.start())
            dialog.code.set("C2040")
            with patch("import_gui.save_preferences", side_effect=OSError("full")):
                self.assertFalse(dialog.start())
            download.assert_not_called()
        self.assertEqual(self.app.easyeda_executable, "")
        self.assertIs(self.app.plan, self.before_plan)

    def test_cancel_is_responsive_and_does_not_handoff(self):
        def download(workspace, tool, code, cancelled):
            cancelled.wait(3)
            raise acquisition.DownloadCancelled("Cancelled")
        dialog = self.dialog()
        with patch("lcsc_dialog.download_lcsc", side_effect=download), patch.object(dialog, "loaded") as loaded:
            dialog.start()
            dialog.cancel()
            self.wait_for(dialog)
            loaded.assert_not_called()
        self.assertEqual(self.app.settings, self.before_settings)
        self.assertIs(self.app.plan, self.before_plan)

    def test_window_destruction_cancels_worker_without_late_handoff(self):
        def download(workspace, tool, code, cancelled):
            cancelled.wait(3)
            raise acquisition.DownloadCancelled("Cancelled")
        dialog = self.dialog()
        with patch("lcsc_dialog.download_lcsc", side_effect=download), patch.object(dialog, "loaded") as loaded:
            dialog.start()
            dialog.window.destroy()
            dialog.worker.join(timeout=3)
            self.assertFalse(dialog.worker.is_alive())
            loaded.assert_not_called()
        self.assertTrue(dialog.cancelled.is_set())
        self.assertIsNone(dialog.job)

    def test_save_failure_during_handoff_removes_download_and_preserves_input(self):
        result = self.result()
        dialog = self.dialog()
        dialog.set_running(True)
        dialog.messages.put(("success", result))
        with patch("import_gui.save_preferences", side_effect=OSError("full")), patch("lcsc_dialog.messagebox.showerror"):
            dialog.drain()
        self.assertEqual(self.app.settings, self.before_settings)
        self.assertEqual(self.app.source.get(), "SamacSys")
        self.assertEqual(self.app.source_choice.get(), "SamacSys")
        self.assertIs(self.app.plan, self.before_plan)
        self.assertFalse(result.folder.parent.exists())

    def test_manual_search_remains_and_download_only_opens_for_lcsc(self):
        with patch("search_dialog.webbrowser.open") as browser:
            search = self.app.open_search()
            self.assertEqual(str(search.download_button["state"]), "disabled")
            search.provider.set("LCSC")
            search.query.set("C2040")
            self.assertEqual(str(search.download_button["state"]), "normal")
            search.download_button.invoke()
            dialog = self.app.lcsc_dialog
            self.assertEqual(dialog.code.get(), "C2040")
            self.assertFalse(dialog.running)
            browser.assert_not_called()

    def test_cancelled_completed_result_is_discarded_without_handoff(self):
        result = self.result()
        dialog = self.dialog()
        dialog.set_running(True)
        dialog.messages.put(("success", result))
        dialog.cancelled.set()
        with patch.object(dialog, "loaded") as loaded:
            dialog.drain()
            loaded.assert_not_called()
        self.assertFalse(result.folder.parent.exists())
        self.assertIs(self.app.plan, self.before_plan)

    def test_default_uses_loader_dependency_ignoring_old_saved_external_path(self):
        self.app.easyeda_executable = str(self.workspace / "old-venv/easyeda2kicad.exe")
        dialog = self.app.open_lcsc_download("C2040")
        self.assertFalse(dialog.use_external.get())
        self.assertEqual(dialog.external_frame.winfo_manager(), "")
        result = self.result()
        with patch("lcsc_dialog.installed_converter", return_value=self.tool) as detect, patch("lcsc_dialog.download_lcsc", return_value=result) as download:
            self.assertTrue(dialog.start())
            self.wait_for(dialog)
            detect.assert_called_once_with()
            self.assertEqual(download.call_args.args[1], str(self.tool))
        self.assertIs(load_preferences(self.app.prefs_path)["easyeda2kicad_use_external"], False)

    def test_missing_loader_dependency_explains_setup_and_never_launches(self):
        dialog = self.app.open_lcsc_download("C2040")
        with patch("lcsc_dialog.installed_converter", side_effect=ValueError("Install loader dependencies")), patch("lcsc_dialog.messagebox.showerror") as error, patch("lcsc_dialog.download_lcsc") as download:
            self.assertFalse(dialog.start())
            error.assert_called_once()
            download.assert_not_called()
        self.assertIs(self.app.plan, self.before_plan)

    def test_explicit_external_override_is_remembered(self):
        dialog = self.dialog()
        result = self.result()
        with patch("lcsc_dialog.installed_converter") as detect, patch("lcsc_dialog.download_lcsc", return_value=result):
            self.assertTrue(dialog.start())
            self.wait_for(dialog)
            detect.assert_not_called()
        self.assertIs(load_preferences(self.app.prefs_path)["easyeda2kicad_use_external"], True)

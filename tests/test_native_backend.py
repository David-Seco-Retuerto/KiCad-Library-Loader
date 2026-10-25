"""Native backend routing, subprocess time bounds and notice evidence parsing."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import native_step
from portable_worker import main as worker


class NativeBackendTests(unittest.TestCase):
    def test_source_mode_does_not_pick_up_an_unrelated_executable(self):
        with patch.object(native_step.sys, "frozen", False, create=True):
            self.assertIsNone(native_step.bundled_reader())

    def test_reader_is_resolved_only_inside_the_frozen_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            reader = root / "step-reader/bin" / ("kicad-step-mesher.exe" if native_step.os.name == "nt" else "kicad-step-mesher")
            reader.parent.mkdir(parents=True)
            reader.write_bytes(b"synthetic")
            with patch.object(native_step.sys, "frozen", True, create=True), patch.object(native_step.sys, "_MEIPASS", str(root), create=True):
                self.assertEqual(native_step.bundled_reader(), reader)
                reader.unlink()
                self.assertIsNone(native_step.bundled_reader())

    def test_reader_has_an_explicit_timeout_and_argument_list(self):
        result = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        with patch.object(native_step, "bundled_reader", return_value=Path("/synthetic/reader")), patch.object(native_step.subprocess, "run", return_value=result) as run:
            native_step.run_reader(["--mesh", "model with spaces.step", "out.json"])
        self.assertEqual(run.call_args.args[0], [str(Path("/synthetic/reader")), "--mesh", "model with spaces.step", "out.json"])
        self.assertEqual(run.call_args.kwargs["timeout"], 55)
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_reader_errors_are_bounded_and_reported(self):
        result = subprocess.CompletedProcess([], 1, stdout="", stderr="x"*5000)
        with patch.object(native_step, "bundled_reader", return_value=Path("/synthetic/reader")), patch.object(native_step.subprocess, "run", return_value=result):
            with self.assertRaises(RuntimeError) as error:
                native_step.run_reader(["--mesh", "input", "output"])
        self.assertEqual(len(str(error.exception)), 2000)

    def test_worker_uses_native_backend_when_present(self):
        with patch("portable_worker.bundled_reader", return_value=Path("/synthetic/reader")), patch("portable_worker.run_reader") as run, patch("step_preview.mesh_step") as python:
            self.assertEqual(worker(["--mesh", "input.step", "out.json"]), 0)
            run.assert_called_once_with(["--mesh", "input.step", "out.json"])
            python.assert_not_called()

    def test_reader_version_is_not_inferred_from_a_filename(self):
        result = subprocess.CompletedProcess([], 0, stdout=json.dumps({"version":"7.9.3"}), stderr="")
        with patch.object(native_step, "run_reader", return_value=result):
            self.assertEqual(native_step.reader_version(), "7.9.3")


class RuntimeNoticeTests(unittest.TestCase):
    def test_analysis_is_parsed_as_literals_and_deduplicates_native_entries(self):
        spec = importlib.util.spec_from_file_location("linux_notices_test", ROOT / "tools/linux_runtime_notices.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder).resolve() / "Analysis.toc"
            path.write_text(repr([[("libexample.so", "/usr/lib/example.so", "BINARY"), ("a.py", "/source/a.py", "PYMODULE")], [("libexample.so", "/usr/lib/example.so", "BINARY")]]))
            self.assertEqual(module.binary_entries([path]), [("libexample.so", "/usr/lib/example.so")])
            path.write_text("__import__('os').system('do-not-execute')")
            with self.assertRaises(ValueError):
                module.binary_entries([path])

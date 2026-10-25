"""Build regressions fail visibly instead of waiting for unattended GUI dialogs."""
from contextlib import redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("portable_regression_test", Path(__file__).resolve().parents[1] / "tools/build_portable.py")
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


class RegressionRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "tools").mkdir()
        self.work = self.root / "work"
        self.work.mkdir()
        self.addCleanup(patch.stopall)
        patch.object(build, "ROOT", self.root).start()

    def script(self, code):
        (self.root / "tools/run_regressions.py").write_text(code, encoding="utf-8")

    def test_failure_retains_and_prints_the_actual_error(self):
        self.script("import sys; print('synthetic regression error',file=sys.stderr); sys.exit(2)")
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaisesRegex(RuntimeError, "Regression tests failed"):
            build.run_regression_tests(self.work, os.environ.copy())
        self.assertIn("synthetic regression error", output.getvalue())
        self.assertIn("synthetic regression error", (self.work / "regression.log").read_text())

    def test_blocked_process_is_terminated_at_the_deadline(self):
        self.script("import time; print('synthetic blocked test',flush=True); time.sleep(60)")
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaisesRegex(RuntimeError, "timed out"):
            build.run_regression_tests(self.work, os.environ.copy(), timeout=1)
        self.assertIn("synthetic blocked test", (self.work / "regression.log").read_text())
        self.assertIn("synthetic blocked test", output.getvalue())

    def test_success_retains_the_report_and_allows_packaging_to_continue(self):
        self.script("print('synthetic regression passed')")
        with redirect_stdout(io.StringIO()):
            build.run_regression_tests(self.work, os.environ.copy())
        self.assertIn("synthetic regression passed", (self.work / "regression.log").read_text())

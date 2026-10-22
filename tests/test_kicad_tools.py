"""CLI discovery and verifier preconditions; these are not native CAD tests."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from kicad_tools import find_cli, cli_version
import verify_local


class KiCadToolTests(unittest.TestCase):
    def test_numeric_versions_and_per_user_installation_are_considered(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            system = root / "ProgramFiles"
            local = root / "LocalAppData"
            for path in (system / "KiCad/9.0/bin/kicad-cli.exe", local / "Programs/KiCad/10.0/bin/kicad-cli.exe"):
                path.parent.mkdir(parents=True)
                path.write_bytes(b"synthetic executable placeholder")
            with patch("kicad_tools.shutil.which", return_value=None):
                self.assertEqual(Path(find_cli({"ProgramFiles": str(system), "LOCALAPPDATA": str(local)})), local / "Programs/KiCad/10.0/bin/kicad-cli.exe")

    def test_explicit_path_search_takes_precedence(self):
        with patch("kicad_tools.shutil.which", return_value="chosen-cli"):
            self.assertEqual(find_cli({}), "chosen-cli")

    def test_missing_installations_return_none(self):
        with patch("kicad_tools.shutil.which", return_value=None):
            self.assertIsNone(find_cli({}))

    def test_cli_version_requires_a_successful_numeric_response(self):
        with patch("kicad_tools.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "10.0.7\n", "")):
            self.assertEqual(cli_version("synthetic-cli"), ("10.0.7", 10))
        for status, output in ((1, "10.0.7"), (0, "unknown")):
            with patch("kicad_tools.subprocess.run", return_value=subprocess.CompletedProcess([], status, output, "error")):
                with self.assertRaises(RuntimeError):
                    cli_version("synthetic-cli")

    def test_required_kicad10_rejects_kicad9_before_any_import(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(sys, "argv", ["verify_local.py", "--repo", directory, "--require-kicad-major", "10"]), patch("verify_local.find_cli", return_value="synthetic-cli"), patch("verify_local.cli_version", return_value=("9.0.7", 9)), patch("verify_local.commit_plan") as commit:
                with self.assertRaises(SystemExit) as error:
                    verify_local.main()
                self.assertEqual(error.exception.code, 2)
                commit.assert_not_called()

    def test_explicit_cli_is_used_for_version_check(self):
        with tempfile.TemporaryDirectory() as directory:
            cli = Path(directory) / "explicit-cli.exe"
            with patch.object(sys, "argv", ["verify_local.py", "--repo", directory, "--kicad-cli", str(cli), "--require-kicad-major", "10"]), patch("verify_local.find_cli") as discover, patch("verify_local.cli_version", return_value=("9.0.7", 9)) as version:
                with self.assertRaises(SystemExit):
                    verify_local.main()
                discover.assert_not_called()
                version.assert_called_once_with(str(cli.resolve()))

    def test_verifier_creates_export_directories_and_exercises_native_symdir_branch(self):
        from test_importer import SYMBOL, FOOTPRINT
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Imports/SamacSys"
            source.mkdir(parents=True)
            (source / "part.kicad_sym").write_text(SYMBOL, encoding="utf-8")
            (source / "GEOM.kicad_mod").write_text(FOOTPRINT, encoding="utf-8")
            commands = []
            def export(command, **kwargs):
                folder = Path(command[command.index("--output") + 1])
                self.assertTrue(folder.is_dir(), "The verifier must create the destination before invoking KiCad")
                (folder / "synthetic.svg").write_text("<svg/>", encoding="utf-8")
                commands.append(command)
                return subprocess.CompletedProcess(command, 0, "synthetic export", "")
            with patch.object(sys, "argv", ["verify_local.py", "--repo", str(root), "--require-kicad-major", "10"]), patch("verify_local.find_cli", return_value="synthetic-cli"), patch("verify_local.cli_version", return_value=("10.0.7", 10)), patch("verify_local.subprocess.run", side_effect=export):
                verify_local.main()
            self.assertTrue(any(command[-1].endswith(".kicad_symdir") for command in commands))
            self.assertTrue(any(command[1:4] == ["fp", "export", "svg"] and "--footprint" in command for command in commands))

    def test_required_validation_with_no_symbols_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(sys, "argv", ["verify_local.py", "--repo", directory, "--require-kicad-major", "10"]), patch("verify_local.find_cli", return_value="synthetic-cli"), patch("verify_local.cli_version", return_value=("10.0.7", 10)):
                with self.assertRaisesRegex(RuntimeError, "No native symbols"):
                    verify_local.main()

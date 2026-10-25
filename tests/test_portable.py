"""Portable routing, workspace isolation and source archive boundary checks."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import runtime_support as runtime
from lcsc_download import installed_converter
from portable_worker import main as worker


class PortableTests(unittest.TestCase):
    def test_source_workspace_remains_application_root(self):
        with patch.object(runtime, 'frozen', return_value=False):
            self.assertEqual(runtime.default_workspace(), Path(runtime.__file__).resolve().parents[1])
            command = runtime.mesh_command('input.step', 'output.json')
            self.assertEqual(command[0], sys.executable)
            self.assertEqual(command[2:], ['--mesh', 'input.step', 'output.json'])

    def test_frozen_helpers_are_relative_to_executable_not_current_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory).resolve()
            suffix = '.exe' if sys.platform == 'win32' else ''
            helper = folder / ('kicad-loader-worker' + suffix)
            helper.write_text('synthetic executable')
            with patch.object(runtime, 'frozen', return_value=True), patch.object(runtime.sys, 'executable', str(folder / ('Loader' + suffix))):
                self.assertEqual(runtime.default_workspace(), folder / 'data')
                self.assertEqual(runtime.mesh_command('a.step', 'b.json'), [str(helper), '--mesh', 'a.step', 'b.json'])
                with patch('lcsc_download.frozen', return_value=True):
                    self.assertEqual(installed_converter(), helper)
                helper.unlink()
                with self.assertRaisesRegex(RuntimeError, 'complete release archive'):
                    runtime.bundled_worker()

    def test_worker_routes_converter_argv_and_mesh_failures(self):
        with patch('easyeda2kicad.__main__.main', return_value=0) as convert:
            self.assertEqual(worker(['--help']), 0)
            convert.assert_called_once_with(['--help'])
        self.assertEqual(worker(['--mesh']), 2)
        with patch('step_preview.mesh_step', side_effect=ValueError('invalid synthetic file')):
            self.assertEqual(worker(['--mesh', 'a.step', 'b.json']), 1)

    def test_source_whitelist_excludes_private_state_and_third_party_assets(self):
        path = Path(__file__).resolve().parents[1] / 'tools/build_portable.py'
        spec = importlib.util.spec_from_file_location('portable_build_test', path)
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        files = [p.relative_to(build.ROOT).as_posix() for p in build.source_files()]
        self.assertIn('LICENSE', files)
        self.assertIn('scripts/portable_worker.py', files)
        self.assertTrue(all(not p.startswith(('Imports/', 'Symbols/', '3DModels/', '.git/', '.venv/', '.kicad')) for p in files))
        self.assertTrue(all('AGENTS.md' not in p and '__pycache__' not in p for p in files))

    def test_application_source_archive_is_deterministic_and_contains_no_state(self):
        path = Path(__file__).resolve().parents[1] / 'tools/build_portable.py'
        spec = importlib.util.spec_from_file_location('portable_archive_test', path)
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        import tarfile
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory).resolve() / 'one.tar.gz', Path(directory).resolve() / 'two.tar.gz'
            build.source_archive(first)
            build.source_archive(second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with tarfile.open(first) as archive:
                names = archive.getnames()
                self.assertTrue(any(n.endswith('/LICENSE') for n in names))
                self.assertFalse(any('AGENTS.md' in n or '.kicad-importer.json' in n or '__pycache__' in n for n in names))

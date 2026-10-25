"""Independent workspace extraction preserves paths and never replaces settings."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from library_core import ImportErrorDetail
from loader_settings import LoaderSettings
from migrate_workspace import migrate_preferences


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.old = self.base / "old-library"
        self.new = self.base / "independent-app"
        self.old.mkdir()
        self.new.mkdir()
        self.original = self.old / ".kicad-importer.json"
        self.destination = self.new / self.original.name

    def test_relative_paths_and_custom_preferences_survive(self):
        preferences = {"mode": "Custom", "custom": "MyPart", "source": "LCSC",
                       "category": "Analog", "symbol_format": "packed", "future_key": [1, 2],
                       "paths": {"sources": {"SamacSys": "exports/S", "LCSC": "exports/L"},
                                 "output_root": "library", "model_path_mode": "absolute"},
                       "categories": [{"name": "Analog", "library_name": "MyAnalog", "model_folder": "Models"}]}
        self.original.write_text(json.dumps(preferences), encoding="utf-8")
        before = self.original.read_bytes()
        expected = LoaderSettings.from_preferences(self.old, preferences)
        self.assertEqual(migrate_preferences(self.old, self.new), self.destination)
        result = json.loads(self.destination.read_text(encoding="utf-8"))
        self.assertEqual(LoaderSettings.from_preferences(self.new, result), expected)
        for key in ("mode", "custom", "source", "category", "symbol_format", "future_key"):
            self.assertEqual(result[key], preferences[key])
        self.assertEqual(self.original.read_bytes(), before)
        self.assertFalse((self.old / "library").exists())
        self.assertEqual({p.name for p in self.new.iterdir()}, {self.original.name})

    def test_legacy_defaults_stay_at_old_workspace(self):
        self.original.write_text('{"mode": "Suggestion"}', encoding="utf-8")
        migrate_preferences(self.old, self.new)
        result = json.loads(self.destination.read_text(encoding="utf-8"))
        self.assertEqual(LoaderSettings.from_preferences(self.new, result), LoaderSettings.defaults(self.old))

    def test_existing_preferences_are_never_overwritten(self):
        self.original.write_text('{}', encoding="utf-8")
        self.destination.write_text('keep this', encoding="utf-8")
        with self.assertRaises(FileExistsError):
            migrate_preferences(self.old, self.new)
        self.assertEqual(self.destination.read_text(encoding="utf-8"), 'keep this')

    def test_invalid_json_creates_nothing(self):
        self.original.write_text('{broken', encoding="utf-8")
        with self.assertRaises(ImportErrorDetail):
            migrate_preferences(self.old, self.new)
        self.assertFalse(self.destination.exists())

    def test_missing_preferences_create_nothing(self):
        with self.assertRaises(ValueError):
            migrate_preferences(self.old, self.new)
        self.assertFalse(self.destination.exists())

    def test_entry_point_runs_from_unrelated_directory(self):
        gui = Path(__file__).resolve().parents[1] / "scripts/import_gui.py"
        result = subprocess.run([sys.executable, str(gui), "--help"], cwd=self.base,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--workspace", result.stdout)
        self.assertIn("--repo", result.stdout)

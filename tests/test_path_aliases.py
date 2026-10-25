"""Exercise real Windows 8.3 aliases without weakening containment checks."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from component_updates import build_update_plan
from library_core import build_plan, commit_plan, scan
from test_importer import SYMBOL, FOOTPRINT, STEP


@unittest.skipUnless(os.name == "nt", "Windows 8.3 alias regression")
class ShortPathTests(unittest.TestCase):
    def test_import_and_update_with_short_workspace_and_temp_aliases(self):
        import ctypes
        with tempfile.TemporaryDirectory(prefix="alias fixture ") as directory:
            root = Path(directory).resolve()
            get_short = ctypes.WinDLL("kernel32", use_last_error=True).GetShortPathNameW
            get_short.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
            get_short.restype = ctypes.c_uint32
            buffer = ctypes.create_unicode_buffer(32768)
            if not get_short(str(root), buffer, len(buffer)):
                self.skipTest("An 8.3 alias could not be obtained on this volume")
            alias = Path(buffer.value)
            if alias == root:
                self.skipTest("8.3 aliases are not enabled on this volume")
            self.assertEqual(alias.resolve(), root)
            with patch.object(tempfile, "tempdir", str(alias)):
                for mode in ("packed", "unpacked"):
                    with self.subTest(mode=mode):
                        workspace = alias / mode
                        source = workspace / "Imports/SamacSys"
                        source.mkdir(parents=True)
                        symbol = source / "parts.kicad_sym"
                        symbol.write_text(SYMBOL, encoding="utf-8")
                        (source / "GEOM.kicad_mod").write_text(FOOTPRINT, encoding="utf-8")
                        model = source / "TEST123.stp"
                        model.write_bytes(STEP)
                        inv = scan(workspace, "SamacSys")
                        key = next(iter(inv.symbols))
                        initial = build_plan(workspace, inv, key, "GEOM.kicad_mod", "TEST123.stp", "ICs", "Original",
                                             symbol_format=mode, model_path_mode="absolute")
                        commit_plan(workspace, initial)
                        symbol.write_text(SYMBOL.replace('"IN"', '"UPDATED_INPUT"'), encoding="utf-8")
                        model.write_bytes(STEP.replace(b"HEADER;", b"HEADER;\n/* revised */"))
                        (source / "GEOM.kicad_mod").write_text(FOOTPRINT.replace("(size 1 2)", "(size 1.4 2)"), encoding="utf-8")
                        inv = scan(workspace, "SamacSys")
                        updated = build_update_plan(workspace, inv, key, "GEOM.kicad_mod", "TEST123.stp", "ICs", "Original",
                                                    symbol_format=mode, model_path_mode="absolute")
                        expected_model = (workspace.resolve() / "3DModels/ICs/GEOM.stp").as_posix().encode()
                        footprint = next(data for path, data in updated.files.items() if path.suffix == ".kicad_mod")
                        self.assertIn(expected_model, footprint)
                        self.assertNotIn(b"kicad-update-plan-", footprint)
                        commit_plan(workspace, updated)
                        self.assertEqual((workspace / "3DModels/ICs/GEOM.stp").read_bytes(), model.read_bytes())

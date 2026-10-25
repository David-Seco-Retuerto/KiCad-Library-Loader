"""Optional native helper equivalence checks and safe source-extraction tests."""
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("native_step_build_tests", ROOT / "tools/build_native_step.py")
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


class NativeSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def archive(self, name, link=False):
        archive = self.root / "source.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            info = tarfile.TarInfo(name)
            if link:
                info.type = tarfile.SYMTYPE
                info.linkname = "../../outside"
                bundle.addfile(info)
            else:
                data = b"# synthetic source"
                info.size = len(data)
                bundle.addfile(info, io.BytesIO(data))
        return archive

    def test_source_extraction_has_one_root_and_requires_cmake(self):
        path = build.extract_source(self.archive("OCCT-test/CMakeLists.txt"), self.root / "output")
        self.assertEqual(path, self.root / "output/OCCT-test")
        self.assertEqual((path / "CMakeLists.txt").read_bytes(), b"# synthetic source")

    def test_source_extraction_rejects_traversal_before_writing_files(self):
        for name in ("../outside", "/absolute", "OCCT/../../outside"):
            with self.subTest(name=name):
                output = self.root / str(len(name))
                with self.assertRaises(ValueError):
                    build.extract_source(self.archive(name), output)
                self.assertEqual(list(output.iterdir()), [])

    def test_source_extraction_rejects_links(self):
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            build.extract_source(self.archive("OCCT/link", link=True), self.root / "output")

    def test_source_extraction_preserves_an_existing_directory(self):
        sentinel = self.root / "sentinel"
        sentinel.write_text("keep")
        with self.assertRaises(FileExistsError):
            build.extract_source(self.archive("OCCT/CMakeLists.txt"), self.root)
        self.assertEqual(sentinel.read_text(), "keep")


class NativeHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        value = os.environ.get("KICAD_LOADER_TEST_STEP_HELPER")
        if not value:
            raise unittest.SkipTest("Set KICAD_LOADER_TEST_STEP_HELPER to test the compiled native helper")
        cls.helper = Path(value).resolve()
        if not cls.helper.is_file():
            raise RuntimeError("Configured native helper is missing")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native STEP test ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_helper(self, *args, success=True):
        result = subprocess.run([str(self.helper), *map(str, args)], cwd=self.root, capture_output=True, text=True, timeout=60)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def test_native_version_is_reported(self):
        result = self.run_helper("--self-test")
        self.assertEqual(json.loads(result.stdout)["version"], "7.9.3")

    def test_box_has_correct_bounds_indices_and_outward_winding(self):
        step, output = self.root / "box.step", self.root / "mesh.json"
        self.run_helper("--make-test-step", step)
        self.run_helper("--mesh", step, output)
        mesh = json.loads(output.read_text())
        self.assertEqual(mesh["size_mm"], [2, 4, 6])
        self.assertEqual(len(mesh["triangles"]), 12)
        vertices = mesh["vertices"]
        self.assertTrue(all(math.isfinite(v) for vertex in vertices for v in vertex))
        volume = 0
        for tri in mesh["triangles"]:
            self.assertTrue(all(0 <= i < len(vertices) for i in tri))
            a, b, c = (vertices[i] for i in tri)
            cross = (b[1]*c[2]-b[2]*c[1], b[2]*c[0]-b[0]*c[2], b[0]*c[1]-b[1]*c[0])
            volume += sum(x*y for x, y in zip(a, cross)) / 6
        self.assertAlmostEqual(volume, 48 / math.sqrt(14)**3)

    def test_unicode_input_and_output_paths(self):
        step, output = self.root / "módèle_组件.step", self.root / "malla_组件.json"
        self.run_helper("--make-test-step", step)
        self.run_helper("--mesh", step, output)
        self.assertEqual(json.loads(output.read_text())["size_mm"], [2, 4, 6])

    def test_invalid_step_fails_without_creating_mesh(self):
        step, output = self.root / "bad.step", self.root / "mesh.json"
        step.write_text("not a STEP file")
        self.run_helper("--mesh", step, output, success=False)
        self.assertFalse(output.exists())

    def test_curved_shape_matches_python_reader_bounds(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
        from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
        from step_preview import mesh_step
        step, output = self.root / "cylinder.step", self.root / "mesh.json"
        writer = STEPControl_Writer()
        writer.Transfer(BRepPrimAPI_MakeCylinder(2, 7).Shape(), STEPControl_AsIs)
        writer.Write(str(step))
        self.run_helper("--mesh", step, output)
        native = json.loads(output.read_text())
        python = mesh_step(step)
        for a, b in zip(native["size_mm"], python["size_mm"]):
            self.assertAlmostEqual(a, b, places=6)
        self.assertTrue(native["triangles"])

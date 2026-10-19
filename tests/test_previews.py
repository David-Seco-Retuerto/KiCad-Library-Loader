"""Regression tests for pin label placement and the local STEP renderer."""
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from import_gui import Drawing, App
from library_core import parse
from step_preview import StepWindow, mesh_step, rotate


class PinPreviewTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.withdraw()
        self.root.update_idletasks()
        self.addCleanup(self.root.destroy)
        self.view = Drawing(self.root)
        self.view.pack()

    def test_names_and_numbers_are_separate_and_clear_of_pin_lines(self):
        cases = [(0, "w"), (180, "e"), (90, "center"), (270, "center")]
        for angle, anchor in cases:
            with self.subTest(angle=angle):
                node = parse(f'''(symbol "TEST" (pin passive line
                    (at 0 0 {angle}) (length 5.08)
                    (name "SIGNAL" (effects (font (size 1.27 1.27))))
                    (number "1" (effects (font (size 1.27 1.27))))))''')
                self.view.show(node, True)
                c = self.view.canvas
                names, numbers = c.find_withtag("pin-name"), c.find_withtag("pin-number")
                self.assertEqual(len(names), 1)
                self.assertEqual(len(numbers), 1)
                self.assertEqual(c.itemcget(names[0], "anchor"), anchor)
                line = next(i for i in c.find_all() if c.type(i) == "line")
                x1, y1, x2, y2 = c.coords(line)
                number_bbox = c.bbox(numbers[0])
                if angle in (0, 180):
                    self.assertLess(number_bbox[3], y1)
                    label_x = c.coords(names[0])[0]
                    self.assertGreater(label_x, x2) if angle == 0 else self.assertLess(label_x, x2)
                else:
                    self.assertLess(number_bbox[2], x1)
                    label_y = c.coords(names[0])[1]
                    self.assertLess(label_y, y2) if angle == 90 else self.assertGreater(label_y, y2)

    def test_active_low_signal_marker_is_preserved(self):
        self.view.show(parse('(symbol "TEST" (pin passive line (at 0 0 0) (length 5.08) (name "~{CS}") (number "1")))'), True)
        label = self.view.canvas.find_withtag("pin-name")[0]
        self.assertEqual(self.view.canvas.itemcget(label, "text"), "C\u0305S\u0305")

    def test_step_button_uses_internal_viewer_without_file_association(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.stp"
            path.write_text("test")
            app = object.__new__(App)
            app.root = self.root
            app.model = tk.StringVar(value="test.stp")
            app.inv = type("Inventory", (), {"models": {"test.stp": path}})()
            with patch("import_gui.StepWindow") as viewer:
                app.open_model()
                viewer.assert_called_once_with(self.root, path)


@unittest.skipUnless(importlib.util.find_spec("OCP"), "Install requirements.txt for STEP tests")
class StepPreviewTests(unittest.TestCase):
    def setUp(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic_box.step"
        writer = STEPControl_Writer()
        writer.Transfer(BRepPrimAPI_MakeBox(2, 4, 6).Shape(), STEPControl_AsIs)
        writer.Write(str(self.path))

    def test_real_cad_tessellation_bounds_and_rotation(self):
        mesh = mesh_step(self.path)
        self.assertTrue(mesh["triangles"])
        self.assertEqual(mesh["size_mm"], [2., 4., 6.])
        self.assertTrue(all(math.isfinite(x) for v in mesh["vertices"] for x in v))
        v = mesh["vertices"][0]
        self.assertAlmostEqual(sum(x*x for x in v), sum(x*x for x in rotate(v, .5, -.8)))
        for tri in mesh["triangles"]:
            self.assertTrue(all(0 <= i < len(mesh["vertices"]) for i in tri))

    def test_subprocess_load_and_canvas_surfaces(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        root.withdraw()
        root.update_idletasks()
        try:
            viewer = StepWindow(root, self.path)
            viewer.window.withdraw()
            deadline = time.monotonic() + 20
            while viewer.mesh is None and time.monotonic() < deadline:
                root.update()
                if not viewer.results.empty():
                    viewer.poll()
                    break
                time.sleep(.02)
            self.assertIsNotNone(viewer.mesh, viewer.status.get())
            viewer.draw()
            self.assertTrue(viewer.canvas.find_withtag("surface"))
            viewer.view(0, 0)
            viewer.scroll(1)
            viewer.draw()
            self.assertTrue(viewer.canvas.find_withtag("surface"))
        finally:
            root.update_idletasks()
            root.destroy()

    def test_invalid_step_has_readable_error(self):
        self.path.write_text("not STEP")
        with self.assertRaisesRegex(ValueError, "could not read"):
            mesh_step(self.path)


if __name__ == "__main__":
    unittest.main()

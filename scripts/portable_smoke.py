"""Offline portable verification with synthetic CAD and a temporary workspace."""
import tempfile
from pathlib import Path
import time
import tkinter as tk


def gui_smoke():
    from native_step import bundled_reader, run_reader
    from import_gui import App
    from library_core import SYMBOL_FORMATS
    from step_preview import StepWindow
    from app_version import VERSION
    symbol = '(kicad_symbol_lib (version 20220914) (generator test) (symbol "PORTABLE_TEST" (in_bom yes) (on_board yes) (property "Reference" "U") (property "Value" "PORTABLE_TEST") (property "Footprint" "Test:BOX") (symbol "PORTABLE_TEST_0_1" (rectangle (start -2 -2) (end 2 2) (stroke (width 0) (type default)) (fill (type background))))))'
    footprint = '(footprint "BOX" (version 20221018) (layer "F.Cu") (fp_rect (start -2 -2) (end 2 2) (stroke (width 0.1) (type default)) (layer "F.SilkS")) (model "PORTABLE_TEST.step" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0))))'
    with tempfile.TemporaryDirectory(prefix="loader-portable-smoke-") as folder:
        workspace = Path(folder).resolve()
        source = workspace / "Imports/SamacSys"
        source.mkdir(parents=True)
        (source / "test.kicad_sym").write_text(symbol, encoding="utf-8")
        (source / "BOX.kicad_mod").write_text(footprint, encoding="utf-8")
        step = source / "PORTABLE_TEST.step"
        if bundled_reader():
            run_reader(["--make-test-step", step])
        else:
            from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
            from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
            writer = STEPControl_Writer()
            writer.Transfer(BRepPrimAPI_MakeBox(2, 4, 6).Shape(), STEPControl_AsIs)
            writer.Write(str(step))
        root = tk.Tk()
        root.withdraw()
        try:
            app = App(root, workspace)
            root.update()
            for mode, category in (("unpacked", "ICs"), ("packed", "Power")):
                app.symbol_format.set(SYMBOL_FORMATS[mode])
                app.category.set(category)
                app.validate()
                if app.plan is None:
                    raise RuntimeError(app.log.get("1.0", "end"))
                expected = list(app.plan.assets)
                app.ack.set(True)
                app.import_component()
                if not all(p.is_file() for p in expected):
                    raise RuntimeError("Portable synthetic import failed: " + app.log.get("1.0", "end"))
            viewer = StepWindow(root, step)
            viewer.window.withdraw()
            deadline = time.monotonic() + 75
            while viewer.mesh is None and time.monotonic() < deadline:
                root.update()
                if "unavailable" in viewer.status.get().casefold() or "failed" in viewer.status.get().casefold():
                    break
                time.sleep(.03)
            if viewer.mesh is None:
                raise RuntimeError("Frozen STEP subprocess did not load: " + viewer.status.get())
            triangles = len(viewer.mesh["triangles"])
            viewer.window.destroy()
            return {"passed": True, "version": VERSION, "tk_gui": True, "native_import_formats": ["unpacked", "packed"],
                    "step_subprocess_triangles": triangles, "vendor_assets": False}
        finally:
            root.destroy()

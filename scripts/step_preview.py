"""Local, offline STEP preview using OpenCascade and a Tk shaded mesh.

CAD parsing runs in a separate process so a slow or failing native reader cannot
freeze the GUI. No STEP file association, web service or browser is required.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from tkinter import ttk
from runtime_support import mesh_command


def mesh_step(path):
    try:
        from OCP.BRep import BRep_Tool
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.STEPControl import STEPControl_Reader
        from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopoDS import TopoDS
    except ImportError as exc:
        raise RuntimeError("STEP preview needs OpenCascade. Install it with this Python:\n"
                           f'"{sys.executable}" -m pip install -r requirements.txt') from exc
    reader = STEPControl_Reader()
    if reader.ReadFile(str(Path(path).resolve())) != IFSelect_RetDone:
        raise ValueError("OpenCascade could not read this STEP file.")
    if not reader.TransferRoots():
        raise ValueError("The STEP file contains no transferable shapes.")
    shape = reader.OneShape()
    if shape.IsNull():
        raise ValueError("The STEP file contains no shape.")
    BRepMesh_IncrementalMesh(shape, .08, False, .35, True).Perform()
    vertices, triangles = [], []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        location = TopLoc_Location()
        mesh = BRep_Tool.Triangulation_s(face, location)
        if mesh:
            offset = len(vertices)
            transform = location.Transformation()
            for index in range(1, mesh.NbNodes() + 1):
                p = mesh.Node(index).Transformed(transform)
                vertices.append([p.X(), p.Y(), p.Z()])
            reverse = face.Orientation() == TopAbs_REVERSED
            for index in range(1, mesh.NbTriangles() + 1):
                indices = list(mesh.Triangle(index).Get())
                if reverse:
                    indices.reverse()
                triangles.append([offset + i - 1 for i in indices])
            if len(triangles) > 60000 or len(vertices) > 150000:
                raise ValueError("This model is too detailed for the lightweight preview. Open it in a full CAD viewer.")
        explorer.Next()
    if not triangles:
        raise ValueError("No renderable surfaces were found in this STEP file.")
    low = [min(v[i] for v in vertices) for i in range(3)]
    high = [max(v[i] for v in vertices) for i in range(3)]
    size = [b - a for a, b in zip(low, high)]
    center = [(a + b) / 2 for a, b in zip(low, high)]
    radius = max(math.dist(v, center) for v in vertices) or 1
    vertices = [[(v[i] - center[i]) / radius for i in range(3)] for v in vertices]
    return {"vertices": vertices, "triangles": triangles, "size_mm": size}


def rotate(v, yaw, pitch):
    x, y, z = v
    x, y = x * math.cos(yaw) - y * math.sin(yaw), x * math.sin(yaw) + y * math.cos(yaw)
    return x, y * math.cos(pitch) - z * math.sin(pitch), y * math.sin(pitch) + z * math.cos(pitch)


class StepWindow:
    def __init__(self, parent, path):
        self.window = tk.Toplevel(parent)
        self.window.title(f"STEP preview · {Path(path).name}")
        self.window.geometry("900x650")
        self.window.minsize(560, 420)
        self.path = Path(path)
        self.mesh = None
        self.yaw, self.pitch, self.zoom = .6, -.9, 1.
        self.last_mouse = None
        self.pending = None
        self.poll_job = None
        self.closed = False
        self.window.bind("<Destroy>", self.on_destroy, add=True)
        toolbar = ttk.Frame(self.window, padding=10)
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Drag to rotate · Scroll to zoom").pack(side="left")
        for name, yaw, pitch in [("Isometric", .6, -.9), ("Top", 0, 0), ("Front", 0, -math.pi / 2), ("Side", math.pi / 2, -math.pi / 2)]:
            ttk.Button(toolbar, text=name, command=lambda y=yaw, p=pitch: self.view(y, p)).pack(side="right", padx=3)
        self.canvas = tk.Canvas(self.window, background="#18222e", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.status = tk.StringVar(value="Loading STEP geometry…")
        ttk.Label(self.window, textvariable=self.status, padding=10, wraplength=850).pack(fill="x")
        self.canvas.bind("<Configure>", lambda _: self.schedule_draw())
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<MouseWheel>", lambda e: self.scroll(1 if e.delta > 0 else -1))
        self.canvas.bind("<Button-4>", lambda _: self.scroll(1))
        self.canvas.bind("<Button-5>", lambda _: self.scroll(-1))
        self.process = None
        self.reader_directory = None
        self.reader_log = None
        self.load_error = None
        self.load()
        if self.process is not None:
            self.poll_job = self.window.after(80, self.poll)

    def on_destroy(self, event):
        if event.widget != self.window:
            return
        self.closed = True
        for job in (self.poll_job, self.pending):
            if job is not None:
                self.window.after_cancel(job)
        self.poll_job = self.pending = None
        self.release_reader()

    def release_reader(self):
        # Called only from the Tk thread, including when the window is destroyed.
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=.5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=1)
            self.process = None
        if self.reader_log is not None:
            self.reader_log.close()
            self.reader_log = None
        if self.reader_directory is not None:
            self.reader_directory.cleanup()
            self.reader_directory = None

    def show_error(self, message):
        self.load_error = message[-2000:]
        self.status.set(self.load_error)
        self.canvas.create_text(25, 25, text="STEP preview unavailable. See details below.", fill="white", anchor="nw")

    def load(self):
        # Poll a child process from Tk instead of retaining Tk objects in a worker
        # thread, where cyclic garbage collection can destroy a Tcl interpreter.
        try:
            self.reader_directory = tempfile.TemporaryDirectory(prefix="dvl-step-")
            folder = Path(self.reader_directory.name)
            self.reader_output = folder / "mesh.json"
            self.reader_log_path = folder / "reader.log"
            self.reader_log = self.reader_log_path.open("wb")
            self.reader_deadline = time.monotonic() + 60
            self.process = subprocess.Popen(mesh_command(self.path, self.reader_output),
                                            stdout=self.reader_log, stderr=subprocess.STDOUT,
                                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception as exc:
            self.release_reader()
            self.show_error(str(exc))

    def poll(self):
        if self.poll_job is not None:
            self.window.after_cancel(self.poll_job)
            self.poll_job = None
        if self.closed or self.process is None:
            return
        result = self.process.poll()
        if result is None and time.monotonic() < self.reader_deadline:
            self.poll_job = self.window.after(80, self.poll)
            return
        try:
            if result is None:
                raise TimeoutError("STEP reader timed out after 60 seconds.")
            if result or not self.reader_output.is_file():
                with self.reader_log_path.open("rb") as stream:
                    stream.seek(0, os.SEEK_END)
                    stream.seek(max(0, stream.tell() - 8000))
                    detail = stream.read().decode("utf-8", errors="replace")
                raise ValueError(detail[-2000:] or "STEP reader failed.")
            self.mesh = json.loads(self.reader_output.read_text(encoding="utf-8"))
        except Exception as exc:
            self.show_error(str(exc))
        finally:
            self.release_reader()
        if self.mesh is not None:
            size = " × ".join(f"{v:.2f}" for v in self.mesh["size_mm"])
            self.status.set(f"{self.path.name} · {size} mm · {len(self.mesh['triangles']):,} triangles\n"
                            "Source model geometry only; footprint placement and original material colours are not shown.")
            self.draw()

    def view(self, yaw, pitch):
        self.yaw, self.pitch, self.zoom = yaw, pitch, 1.
        self.schedule_draw()

    def press(self, event):
        self.last_mouse = event.x, event.y

    def drag(self, event):
        if self.last_mouse:
            self.yaw += (event.x - self.last_mouse[0]) * .012
            self.pitch += (event.y - self.last_mouse[1]) * .012
            self.last_mouse = event.x, event.y
            self.schedule_draw()

    def scroll(self, direction):
        self.zoom = max(.2, min(5., self.zoom * (1.12 if direction > 0 else 1 / 1.12)))
        self.schedule_draw()

    def schedule_draw(self):
        if self.pending is None:
            self.pending = self.window.after(25, self.draw)

    def draw(self):
        if self.pending is not None:
            self.window.after_cancel(self.pending)
            self.pending = None
        if not self.mesh:
            return
        c = self.canvas
        c.delete("all")
        width, height = max(c.winfo_width(), 100), max(c.winfo_height(), 100)
        scale = min(width, height) * .42 * self.zoom
        vertices = [rotate(v, self.yaw, self.pitch) for v in self.mesh["vertices"]]
        surfaces = []
        for tri in self.mesh["triangles"]:
            a, b, d = [vertices[i] for i in tri]
            u, v = [b[i] - a[i] for i in range(3)], [d[i] - a[i] for i in range(3)]
            normal = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            length = math.sqrt(sum(n * n for n in normal)) or 1
            light = .32 + .68 * abs(sum(n * l for n, l in zip(normal, (.25, -.4, .88))) / length)
            colour = "#" + "".join(f"{min(255, int(base * light)):02x}" for base in (125, 195, 225))
            xy = [value for p in (a, b, d) for value in (width / 2 + p[0] * scale, height / 2 - p[1] * scale)]
            surfaces.append((sum(p[2] for p in (a, b, d)), xy, colour))
        for _, xy, colour in sorted(surfaces, key=lambda item: item[0]):
            c.create_polygon(*xy, fill=colour, outline=colour, width=1, tags=("surface",))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mesh", nargs=2, metavar=("STEP", "JSON"), required=True)
    args = parser.parse_args()
    try:
        mesh = mesh_step(args.mesh[0])
        Path(args.mesh[1]).write_text(json.dumps(mesh), encoding="utf-8")
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

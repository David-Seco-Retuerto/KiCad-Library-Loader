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
import queue
import subprocess
import sys
import tempfile
import threading
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
        self.results = queue.Queue()
        threading.Thread(target=self.load, daemon=True).start()
        self.poll_job = self.window.after(80, self.poll)

    def on_destroy(self, event):
        if event.widget != self.window:
            return
        self.closed = True
        for job in (self.poll_job, self.pending):
            if job is not None:
                self.window.after_cancel(job)
        self.poll_job = self.pending = None

    def load(self):
        try:
            with tempfile.TemporaryDirectory(prefix="dvl-step-") as directory:
                output = Path(directory) / "mesh.json"
                result = subprocess.run(mesh_command(self.path, output),
                                        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if result.returncode or not output.exists():
                    raise ValueError((result.stderr or result.stdout or "STEP reader failed.")[-2000:])
                self.results.put((json.loads(output.read_text(encoding="utf-8")), None))
        except Exception as exc:
            self.results.put((None, str(exc)))

    def poll(self):
        self.poll_job = None
        if self.closed or not self.window.winfo_exists():
            return
        try:
            self.mesh, error = self.results.get_nowait()
        except queue.Empty:
            self.poll_job = self.window.after(80, self.poll)
            return
        if error:
            self.status.set(error)
            self.canvas.create_text(25, 25, text="STEP preview unavailable. See details below.", fill="white", anchor="nw")
        else:
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

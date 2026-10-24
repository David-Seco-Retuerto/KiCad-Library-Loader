"""Run: python scripts/import_gui.py [--workspace PATH]. Python 3.10+ with Tcl/Tk."""
from __future__ import annotations

import argparse
from dataclasses import replace
import math
import queue
import time
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont
import webbrowser
from step_preview import StepWindow
from loader_settings import LoaderSettings
from providers import PROVIDERS, get_provider
from search_dialog import SearchDialog
from lcsc_dialog import LcscDownloadDialog
from lcsc_download import lcsc_code
from archive_import import extract_native_zip, discard_extraction
from input_choices import asset_choices, downloaded_zips
from download_watch import ZipArrivalTracker, ArrivalChanged, fingerprint, has_partial, prepare_arrival
from diagnostics_dialog import DiagnosticsDialog
from history_dialog import HistoryDialog
from component_updates import build_update_plan
from update_dialog import UpdateDialog
from settings_dialog import FolderSettingsDialog
from categories_dialog import CategoriesDialog, FolderPreviewDialog

from library_core import (SYMBOL_FORMATS, ImportErrorDetail, associate, associate_model,
                          build_folder_plan, build_plan, child, children, commit_plan, load_preferences,
                          read_tree, prop, safe_name, save_preferences, scan, suggestion, walk)


from kicad_tools import find_cli
from gui_layout import build_main_window
from report_text import report_lines


class Drawing(ttk.Frame):
    """Approximate native preview. Exact SVG export is available separately."""
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, background="#18222e", height=270, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.node, self.symbol = None, False
        self.canvas.bind("<Configure>", lambda _: self.draw())

    def show(self, node, symbol=False):
        self.node, self.symbol = node, symbol
        self.draw()

    def draw(self):
        c = self.canvas
        c.delete("all")
        if not self.node:
            c.create_text(max(c.winfo_width(), 300) / 2, max(c.winfo_height(), 200) / 2,
                          text="Select a symbol to preview" if self.symbol else "Select a footprint to preview",
                          fill="#a9b8ce", font=("Segoe UI", 12), tags=("empty-state",))
            return
        shapes = []
        pins = []

        def coords(n, tag):
            p = child(n, tag)
            return [float(v) for v in p[1:]] if p else []

        def point(x, y):
            return x, -y if self.symbol else y

        try:
            for n in walk(self.node, "rectangle" if self.symbol else "fp_rect"):
                a, b = coords(n, "start"), coords(n, "end")
                shapes.append(("rect", [point(*a[:2]), point(*b[:2])], "", "#7dd3fc"))
            for n in walk(self.node, "polyline" if self.symbol else "fp_poly"):
                pts = child(n, "pts") or []
                xy = [point(float(p[1]), float(p[2])) for p in children(pts, "xy")]
                if len(xy) > 1:
                    shapes.append(("line", xy, "", "#7dd3fc"))
            for n in walk(self.node, "fp_line"):
                shapes.append(("line", [point(*coords(n, "start")[:2]), point(*coords(n, "end")[:2])], "", "#7dd3fc"))
            for n in walk(self.node, "circle" if self.symbol else "fp_circle"):
                a, b = coords(n, "center"), coords(n, "radius") if self.symbol else coords(n, "end")
                radius = b[0] if self.symbol else math.dist(a[:2], b[:2])
                shapes.append(("oval", [point(a[0] - radius, a[1] - radius), point(a[0] + radius, a[1] + radius)], "", "#7dd3fc"))
            if self.symbol:
                for n in walk(self.node, "pin"):
                    at, length = coords(n, "at"), coords(n, "length")[0]
                    x, y, angle = at[:3]
                    end = (x + length * math.cos(math.radians(angle)), y + length * math.sin(math.radians(angle)))
                    number, name = child(n, "number"), child(n, "name")
                    names = child(self.node, "pin_names") or []
                    numbers = child(self.node, "pin_numbers") or []
                    visible_name = str(name[1]) if name and "hide" not in names else ""
                    visible_number = str(number[1]) if number and "hide" not in numbers else ""
                    pins.append((point(x, y), point(*end), visible_number, visible_name))
                    shapes.append(("line", [point(x, y), point(*end)], "", "#fbbf24"))
            else:
                for n in children(self.node, "pad"):
                    at, size = coords(n, "at"), coords(n, "size")
                    x, y = at[:2]
                    w, h = size[:2]
                    angle = math.radians(at[2] if len(at) > 2 else 0)
                    corners = [(x + a * math.cos(angle) - b * math.sin(angle), y + a * math.sin(angle) + b * math.cos(angle)) for a, b in [(-w/2, -h/2), (w/2, -h/2), (w/2, h/2), (-w/2, h/2)]]
                    shapes.append(("pad", corners, str(n[1]), "#fbbf24"))
            points = [p for _, pts, _, _ in shapes for p in pts]
            if not points:
                c.create_text(20, 20, text="No supported geometry in this preview; use KiCad SVG.", anchor="nw", fill="white")
                return
            xmin, xmax = min(p[0] for p in points), max(p[0] for p in points)
            ymin, ymax = min(p[1] for p in points), max(p[1] for p in points)
            width = c.winfo_width() if c.winfo_width() > 1 else 300
            height = c.winfo_height() if c.winfo_height() > 1 else 200
            scale = min(max(width - 120, 30) / max(xmax - xmin, 1), max(height - 60, 30) / max(ymax - ymin, 1))

            def project(p):
                return ((p[0] - (xmin + xmax) / 2) * scale + width / 2,
                        (p[1] - (ymin + ymax) / 2) * scale + height / 2)

            for kind, pts, label, color in shapes:
                flattened = [v for p in pts for v in project(p)]
                if kind == "line":
                    c.create_line(*flattened, fill=color, width=2)
                elif kind in ("rect", "oval"):
                    (c.create_rectangle if kind == "rect" else c.create_oval)(*flattened, outline=color, width=2)
                else:
                    c.create_polygon(*flattened, fill="#ad7436", outline=color)
                if label:
                    px = sum(p[0] for p in pts) / len(pts)
                    py = sum(p[1] for p in pts) / len(pts)
                    c.create_text(*project((px, py)), text=label, fill="white", font=("Segoe UI", 8))
            # KiCad pin angles point from the connection towards the symbol body.
            # Draw labels separately: names beyond the body end, numbers above
            # horizontal pins (or left of vertical pins), never centred on a line.
            distances = [math.dist(a[0], b[0]) for i, a in enumerate(pins) for b in pins[i + 1:]
                         if math.dist(a[0], b[0]) > 0.01]
            pixels = max(7, min(12, int(min(distances, default=2.54) * scale * .65)))
            if not hasattr(self, "label_font"):
                self.label_font = tkfont.Font(family="Segoe UI", size=-pixels)
            self.label_font.configure(size=-pixels)
            label_font = self.label_font
            for start, end, number, raw_name in pins:
                sx, sy = project(start)
                ex, ey = project(end)
                dx, dy = ex - sx, ey - sy
                length = math.hypot(dx, dy)
                if length < .01:
                    continue
                ux, uy = dx / length, dy / length
                # Preserve active-low signal marks without displaying KiCad markup.
                name = re.sub(r"~\{([^}]*)\}", lambda m: "".join(ch + "\u0305" for ch in m[1]), raw_name)
                if name == "~":
                    name = ""
                if abs(dx) >= abs(dy):
                    if name:
                        c.create_text(ex + ux * 6, ey, text=name,
                                      anchor="w" if ux > 0 else "e", fill="white",
                                      font=label_font, tags=("pin-name",))
                    if number:
                        c.create_text((sx + ex) / 2, (sy + ey) / 2 - 3,
                                      text=number, anchor="s", fill="#fbbf24",
                                      font=label_font, tags=("pin-number",))
                else:
                    if name:
                        offset = 6 + label_font.measure(name) / 2
                        c.create_text(ex, ey + uy * offset, text=name, angle=90,
                                      fill="white", font=label_font, tags=("pin-name",))
                    if number:
                        c.create_text((sx + ex) / 2 - 4, (sy + ey) / 2,
                                      text=number, anchor="e", fill="#fbbf24",
                                      font=label_font, tags=("pin-number",))
        except (ValueError, TypeError, IndexError) as exc:
            c.create_text(15, 15, text=f"Partial preview: {exc}. Use KiCad SVG.", anchor="nw", fill="white")


class App:
    def __init__(self, root, repo):
        self.root, self.repo = root, Path(repo).resolve()
        self.prefs_path = self.repo / ".kicad-importer.json"
        self.prefs = {}
        self.settings_error = None
        try:
            self.prefs = load_preferences(self.prefs_path, strict=True)
            self.settings = LoaderSettings.from_preferences(self.repo, self.prefs)
        except (OSError, ValueError) as exc:
            self.settings = LoaderSettings.defaults(self.repo)
            self.settings_error = str(exc)
        self.inv, self.plan = None, None
        self.busy = False
        saved_tool = self.prefs.get("easyeda2kicad_executable")
        self.easyeda_executable = saved_tool if isinstance(saved_tool, str) else ""
        self.easyeda_use_external = self.prefs.get("easyeda2kicad_use_external") is True
        self.lcsc_dialog = None
        saved_source = self.prefs.get("source")
        self.source = tk.StringVar(value=saved_source if isinstance(saved_source, str) and saved_source in PROVIDERS else next(iter(PROVIDERS)))
        self.source_choice = tk.StringVar(value="Downloads" if self.prefs.get("input_mode") == "downloads" else self.source.get())
        saved_downloads = self.prefs.get("downloads_folder")
        self.downloads_folder = Path(saved_downloads).expanduser().resolve() if isinstance(saved_downloads, str) and saved_downloads.strip() else Path.home() / "Downloads"
        saved_zip = self.prefs.get("active_zip")
        self.active_zip = saved_zip if isinstance(saved_zip, str) else ""
        self.download_zip = tk.StringVar()
        self.download_files = {}
        self.watch_downloads = tk.BooleanVar(value=self.prefs.get("watch_downloads") is True)
        self.download_status = tk.StringVar()
        self.download_watch_job = None
        self.download_watch_snapshot = None
        self.auto_load_zips = tk.BooleanVar(value=False)
        self.zip_tracker = ZipArrivalTracker()
        self.auto_zip_context = None
        self.auto_zip_generation = 0
        self.auto_zip_cancel = threading.Event()
        self.auto_zip_messages = queue.Queue()
        self.auto_zip_busy = False
        self.download_watch_closed = False
        saved_category = self.prefs.get("category")
        self.category = tk.StringVar(value=saved_category if self.settings.get_category(saved_category) else self.settings.categories[0].name)
        saved_format = self.prefs.get("symbol_format", "unpacked")
        self.symbol_format = tk.StringVar(value=SYMBOL_FORMATS.get(saved_format, SYMBOL_FORMATS["unpacked"]) if isinstance(saved_format, str) else SYMBOL_FORMATS["unpacked"])
        self.mode = tk.StringVar(value=self.prefs.get("mode") if self.prefs.get("mode") in ("Original", "Suggestion", "Custom") else "Suggestion")
        self.custom = tk.StringVar(value=str(self.prefs.get("custom", "")))
        self.symbol, self.fp, self.model = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.output = tk.StringVar()
        self.folder_summary = tk.StringVar()
        self.ack = tk.BooleanVar(value=False)
        self.cli = find_cli()
        build_main_window(self, Drawing, PROVIDERS, SYMBOL_FORMATS)
        for var in (self.category, self.mode, self.custom, self.symbol_format):
            var.trace_add("write", lambda *_: self.changed())
        self.ack.trace_add("write", lambda *_: self.update_import_button())
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()
        root.bind("<Destroy>", self.download_watch_destroyed, add="+")
        self.schedule_download_watch()

    def expand_preview(self, kind):
        """Open the selected simplified drawing at a larger resizable size."""
        view = self.symbol_view if kind == "symbol" else self.fp_view
        window = tk.Toplevel(self.root)
        window.title("Symbol preview" if kind == "symbol" else "Footprint preview")
        window.transient(self.root)
        window.geometry("1000x720")
        window.minsize(500, 380)
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Simplified 2D preview. Symbol units may overlap; some graphics and pad shapes are omitted. Use KiCad SVG for exact graphics.", wraplength=850).pack(anchor="w", pady=(0, 12))
        drawing = Drawing(frame)
        drawing.pack(fill="both", expand=True)
        drawing.show(view.node, symbol=kind == "symbol")
        ttk.Button(frame, text="Close", command=window.destroy).pack(anchor="e", pady=(12, 0))
        return window

    def show_locations(self):
        """Display complete paths without crowding the selection workflow."""
        from tkinter.scrolledtext import ScrolledText
        window = tk.Toplevel(self.root)
        window.title("Library locations")
        window.transient(self.root)
        window.geometry("820x440")
        window.minsize(580, 320)
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Library locations", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        text = ScrolledText(frame, wrap="word", font=("Consolas", 10), height=12)
        text.pack(fill="both", expand=True, pady=14)
        text.insert("end", self.folder_summary.get() + "\n\n" + self.output.get())
        text.configure(state="disabled")
        ttk.Button(frame, text="Close", command=window.destroy).pack(anchor="e")
        return window

    def log_text(self, text):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        for line, tag in report_lines(text):
            self.log.insert("end", line + "\n", tag)
        self.log.configure(state="disabled")

    def persist(self):
        if self.settings_error:
            # Do not silently replace invalid path preferences with defaults.
            return
        try:
            self.write_preferences(self.settings)
        except OSError:
            # Routine UI changes stay usable; the save error is already shown.
            pass

    def write_preferences(self, settings):
        try:
            preferences = dict(self.prefs)
            category_name = self.category.get() if settings.get_category(self.category.get()) else settings.categories[0].name
            preferences.update({"source": self.source.get(), "category": category_name, "mode": self.mode.get(), "custom": self.custom.get(), "symbol_format": self.selected_format(), "paths": settings.to_preferences(),
                                "categories": [category.to_preferences() for category in settings.categories],
                                "input_mode": "downloads" if self.source_choice.get() == "Downloads" else "provider",
                                "downloads_folder": str(self.downloads_folder), "active_zip": self.active_zip,
                                "watch_downloads": self.watch_downloads.get(),
                                "easyeda2kicad_executable": self.easyeda_executable,
                                "easyeda2kicad_use_external": self.easyeda_use_external})
            save_preferences(self.prefs_path, preferences)
            self.prefs = preferences
        except OSError as exc:
            self.log_text(f"Could not save preferences: {exc}")
            raise

    def sync_asset_display(self, label, variable):
        key = variable.get()
        display = next((name for name, value in self.asset_choices[label].items() if value == key), "")
        self.asset_displays[label].set(display)

    def select_asset(self, label):
        variable = {"Symbol": self.symbol, "Footprint": self.fp, "STEP model": self.model}[label]
        variable.set(self.asset_choices[label].get(self.asset_displays[label].get(), ""))
        if label == "Symbol":
            self.select_symbol()
        elif label == "Footprint":
            self.select_fp()
        else:
            self.changed()

    def update_downloads_panel(self):
        if self.source_choice.get() == "Downloads":
            self.download_wrapper.grid()
            self.download_frame.pack(fill="x", pady=(4, 6))
            self.download_status_label.pack(fill="x")
        else:
            self.download_frame.pack_forget()
            self.download_status_label.pack_forget()
            self.download_wrapper.grid_remove()

    def toggle_download_watch(self):
        if not self.watch_downloads.get():
            self.auto_load_zips.set(False)
        self.cancel_auto_zip()
        self.download_watch_snapshot = None
        self.download_status.set("Auto-refresh enabled; ZIPs still need to be selected and loaded."
                                 if self.watch_downloads.get() else "Auto-refresh off. Use Refresh to check for ZIPs.")
        self.persist()

    def cancel_auto_zip(self):
        self.auto_zip_cancel.set()
        self.auto_zip_generation += 1
        self.auto_zip_context = None
        self.zip_tracker.baseline({})

    def toggle_auto_zip(self):
        self.cancel_auto_zip()
        if self.auto_load_zips.get():
            self.watch_downloads.set(True)
            try:
                snapshot = {path: fingerprint(path) for path in downloaded_zips(self.downloads_folder)}
                self.zip_tracker.baseline(snapshot)
                self.auto_zip_context = (self.downloads_folder, self.source.get())
                self.download_status.set("Watching for new ZIPs. Existing ZIPs are skipped; new native assets will load for review only.")
            except (OSError, ValueError) as exc:
                self.download_status.set(str(exc))
        else:
            self.download_status.set("Automatic ZIP loading off. Refresh loads the newest ZIP explicitly.")
        self.persist()

    def watch_browser_downloads(self, provider):
        if self.settings_error:
            messagebox.showerror("Cannot watch Downloads", "Correct the saved settings first.", parent=self.root)
            return False
        self.cancel_auto_zip()
        self.source.set(provider)
        self.source_choice.set("Downloads")
        self.refresh()
        self.auto_load_zips.set(True)
        self.toggle_auto_zip()
        return True

    def refresh_action(self):
        if self.source_choice.get() != "Downloads":
            self.refresh()
            return
        self.cancel_auto_zip()
        notice = self.refresh_downloads()
        if notice:
            self.download_status.set(notice)
            return False
        if not self.download_files:
            self.download_status.set("No ZIP downloads found. Use Folder… to choose a downloads folder.")
            return False
        self.download_zip.set(next(iter(self.download_files)))
        return self.load_download()

    def clean_auto_zip_messages(self):
        while True:
            try:
                context, path, signature, kind, value = self.auto_zip_messages.get_nowait()
            except queue.Empty:
                return
            if kind == "success":
                discard_extraction(value, self.repo)

    def prepare_auto_zip(self, context, path, signature, cancelled):
        try:
            folder = prepare_arrival(path, self.repo, signature, cancelled)
            self.auto_zip_messages.put((context, path, signature, "success", folder))
        except ArrivalChanged as exc:
            self.auto_zip_messages.put((context, path, signature, "changed", str(exc)))
        except Exception as exc:
            self.auto_zip_messages.put((context, path, signature, "error", str(exc)))
        if self.download_watch_closed:
            self.clean_auto_zip_messages()

    def finish_auto_zip(self):
        if any(isinstance(widget, tk.Toplevel) for widget in self.root.winfo_children()):
            return
        try:
            context, path, signature, kind, value = self.auto_zip_messages.get_nowait()
        except queue.Empty:
            return
        self.auto_zip_busy = False
        current = (self.downloads_folder, self.source.get(), self.auto_zip_generation)
        if (context != current or self.auto_zip_cancel.is_set() or not self.auto_load_zips.get()
                or self.source_choice.get() != "Downloads"):
            if kind == "success":
                discard_extraction(value, self.repo)
            return
        if kind == "changed":
            # The next observation resets stability if the file size/date changed.
            self.zip_tracker.pending[path] = (signature, time.monotonic())
            self.download_status.set(str(value))
            return
        self.zip_tracker.consume(path, signature)
        if kind == "error":
            self.download_status.set(f"Skipped {path.name}: {value}. Use Load ZIP to retry manually.")
            return
        previous_zip = self.active_zip
        previous_selection = self.download_zip.get()
        try:
            if fingerprint(path) != signature or has_partial(path):
                raise ValueError("The ZIP changed after validation. Wait for it to finish and retry.")
            self.active_zip = str(path.resolve())
            self.download_zip.set(path.name)
            self.activate_export_folder(value, self.source.get())
        except (OSError, ValueError) as exc:
            self.active_zip = previous_zip
            self.download_zip.set(previous_selection)
            discard_extraction(value, self.repo)
            self.download_status.set(f"Could not load {path.name}: {exc}. The previous component is retained.")
            return
        # One arrival replaces the loaded review. Do not cycle through older pending ZIPs.
        self.zip_tracker.pending = {candidate: value for candidate, value in self.zip_tracker.pending.items()
                                    if value[0][1] > signature[1]}
        self.download_status.set(f"Loaded {path.name} automatically for review. Validate and Import explicitly.")

    def consider_auto_zip(self, paths):
        if self.settings_error:
            self.download_status.set("Correct saved loader settings before automatically loading ZIPs.")
            return
        snapshot = {path: fingerprint(path) for path in paths}
        context = (self.downloads_folder, self.source.get())
        if self.auto_zip_context != context:
            self.zip_tracker.baseline(snapshot)
            self.auto_zip_context = context
            return
        now = time.monotonic()
        self.zip_tracker.observe(snapshot, now)
        if self.auto_zip_busy or self.busy:
            return
        # Wait while another loader dialog is open, so a settings/update review is not replaced.
        if any(isinstance(widget, tk.Toplevel) for widget in self.root.winfo_children()):
            return
        ready = self.zip_tracker.ready(now)
        if not ready:
            return
        path, signature = ready[0]
        if has_partial(path):
            return
        self.auto_zip_busy = True
        self.auto_zip_cancel = threading.Event()
        generation_context = (*context, self.auto_zip_generation)
        self.download_status.set(f"Validating {path.name} for automatic loading…")
        threading.Thread(target=self.prepare_auto_zip,
                         args=(generation_context, path, signature, self.auto_zip_cancel), daemon=False).start()

    def schedule_download_watch(self):
        self.download_watch_job = self.root.after(3000, self.poll_downloads)

    def download_watch_destroyed(self, event):
        if event.widget is self.root:
            self.download_watch_closed = True
            self.auto_zip_cancel.set()
            self.clean_auto_zip_messages()
            if self.download_watch_job is not None:
                self.root.after_cancel(self.download_watch_job)
                self.download_watch_job = None

    def poll_downloads(self):
        self.download_watch_job = None
        try:
            self.finish_auto_zip()
            if self.source_choice.get() != "Downloads" or not self.watch_downloads.get():
                self.download_watch_snapshot = None
                self.cancel_auto_zip()
                return
            if self.busy:
                return
            try:
                paths = downloaded_zips(self.downloads_folder)
                snapshot = (str(self.downloads_folder), tuple(
                    (path.name, path.stat().st_size, path.stat().st_mtime_ns) for path in paths))
            except (OSError, ValueError) as exc:
                self.download_watch_snapshot = None
                self.download_status.set(f"Auto-refresh unavailable: {exc}")
                return
            previous = self.download_watch_snapshot
            if snapshot != previous:
                # A passive list refresh must not load files or invalidate an import review.
                selected = self.download_zip.get()
                self.download_files = {path.name: path for path in paths}
                self.download_combo["values"] = list(self.download_files)
                self.download_zip.set(selected if selected in self.download_files else "")
                self.download_watch_snapshot = snapshot
                self.download_status.set(
                    f"{len(paths)} ZIP downloads available. List refreshed automatically; select a ZIP to load it. "
                    "A listed ZIP may still be downloading.")
            if self.auto_load_zips.get():
                try:
                    self.consider_auto_zip(paths)
                except (OSError, ValueError) as exc:
                    self.download_status.set(f"Automatic ZIP loading unavailable: {exc}")
        finally:
            self.schedule_download_watch()

    def select_source_choice(self):
        self.cancel_auto_zip()
        if self.source_choice.get() in PROVIDERS:
            self.source.set(self.source_choice.get())
        self.refresh()

    def refresh_downloads(self):
        previous = self.download_zip.get()
        try:
            self.download_files = {path.name: path for path in downloaded_zips(self.downloads_folder)}
            self.download_combo["values"] = list(self.download_files)
            if previous in self.download_files:
                selected = previous
            elif self.active_zip:
                selected = next((name for name, path in self.download_files.items() if path == Path(self.active_zip)), "")
            else:
                selected = next(iter(self.download_files), "")
            self.download_zip.set(selected)
            return None
        except (OSError, ValueError) as exc:
            self.download_files = {}
            self.download_combo["values"] = []
            self.download_zip.set("")
            return str(exc)

    def choose_downloads_folder(self):
        if self.settings_error:
            messagebox.showerror("Cannot change Downloads folder", "Correct the saved settings first.", parent=self.root)
            return
        selected = filedialog.askdirectory(parent=self.root, title="Select ZIP downloads folder", mustexist=True,
                                            initialdir=str(self.downloads_folder if self.downloads_folder.is_dir() else self.repo))
        if not selected:
            return
        previous = self.downloads_folder
        try:
            folder = Path(selected).resolve()
            if not folder.is_dir():
                raise ValueError("Choose an existing Downloads folder.")
            self.downloads_folder = folder
            self.write_preferences(self.settings)
        except (OSError, ValueError) as exc:
            self.downloads_folder = previous
            messagebox.showerror("Cannot change Downloads folder", str(exc), parent=self.root)
            return
        self.cancel_auto_zip()
        notice = self.refresh_downloads()
        self.changed()
        self.log_text(notice or f"{len(self.download_files)} ZIP downloads available. Select a ZIP to load it.")

    def load_download(self):
        path = self.download_files.get(self.download_zip.get())
        if path is None:
            messagebox.showinfo("Select a ZIP", "Choose a downloaded ZIP. Refresh rescans the Downloads folder.", parent=self.root)
            return False
        if not path.is_file():
            self.refresh_downloads()
            messagebox.showerror("Download unavailable", "The selected ZIP was moved or removed. Choose another download.", parent=self.root)
            return False
        loaded = self.open_zip(archive_path=path)
        if not loaded:
            self.download_zip.set(next((name for name, candidate in self.download_files.items()
                                        if self.active_zip and candidate == Path(self.active_zip)), ""))
        return loaded

    def open_search(self):
        symbol = self.inv.symbols.get(self.symbol.get()) if self.inv else None
        return SearchDialog(self.root, self.source.get(), symbol.mpn if symbol else "", self.use_export_folder, self.open_zip, self.open_lcsc_download, self.watch_browser_downloads)

    def remember_converter(self, executable, use_external):
        previous = self.easyeda_executable, self.easyeda_use_external
        self.easyeda_executable = executable
        self.easyeda_use_external = use_external
        try:
            self.write_preferences(self.settings)
        except OSError:
            self.easyeda_executable, self.easyeda_use_external = previous
            raise

    def open_lcsc_download(self, initial_code=""):
        if self.settings_error:
            messagebox.showerror("Cannot download component", "Correct the saved loader settings first.", parent=self.root)
            return None
        if self.lcsc_dialog is not None and self.lcsc_dialog.window.winfo_exists():
            self.lcsc_dialog.window.lift()
            return self.lcsc_dialog
        if not initial_code and self.inv and self.symbol.get() in self.inv.symbols:
            initial_code = prop(self.inv.symbols[self.symbol.get()].node, "LCSC Part") or ""
        try:
            initial_code = lcsc_code(initial_code)
        except ValueError:
            initial_code = ""
        self.lcsc_dialog = LcscDownloadDialog(self.root, self.repo, self.easyeda_executable,
                                              initial_code, self.remember_converter, self.load_lcsc_download,
                                              use_external=self.easyeda_use_external)
        return self.lcsc_dialog

    def load_lcsc_download(self, result):
        self.cancel_auto_zip()
        if self.settings_error:
            raise ValueError("Correct the saved loader settings before loading the download.")
        previous_choice, previous_zip = self.source_choice.get(), self.active_zip
        self.source_choice.set("LCSC")
        self.active_zip = ""
        try:
            self.activate_export_folder(result.folder, "LCSC")
        except (OSError, ValueError):
            self.source_choice.set(previous_choice)
            self.active_zip = previous_zip
            raise
        self.log_text(f"Downloaded {result.lcsc_id} using external easyeda2kicad.\nCache: {result.folder}\n" +
                      "\n".join(result.notices) +
                      "\nReview the exact component, package, pin/pad numbering and 3D alignment. Validate the plan, then Import explicitly.")

    def open_zip(self, provider=None, archive_path=None):
        source = provider if provider is not None else self.source.get()
        extracted = None
        try:
            get_provider(source)
            if self.settings_error:
                raise ImportErrorDetail(f"Correct the saved settings before loading a ZIP: {self.settings_error}")
            selected = archive_path or filedialog.askopenfilename(parent=self.root, title=f"Open native KiCad ZIP download for {source}",
                                                  initialdir=str(self.downloads_folder if self.downloads_folder.is_dir() else self.repo),
                                                  filetypes=[("ZIP downloads", "*.zip")])
            if not selected:
                return False
            self.cancel_auto_zip()
            extracted = extract_native_zip(selected, self.repo)
            previous_zip, previous_selection = self.active_zip, self.download_zip.get()
            self.active_zip = str(Path(selected).resolve())
            if self.source_choice.get() == "Downloads":
                self.download_zip.set(next((name for name, path in self.download_files.items() if path == Path(self.active_zip)), ""))
            try:
                self.activate_export_folder(extracted, source)
            except (OSError, ValueError):
                self.active_zip = previous_zip
                self.download_zip.set(previous_selection)
                raise
            return True
        except (OSError, ValueError) as exc:
            if extracted is not None:
                discard_extraction(extracted, self.repo)
            messagebox.showerror("Cannot open ZIP", str(exc), parent=self.root)
            return False

    def activate_export_folder(self, folder, source):
        settings = replace(self.settings, sources={**self.settings.sources, source: folder}).validated(self.repo)
        previous_source, previous_choice = self.source.get(), self.source_choice.get()
        self.source.set(source)
        if previous_choice != "Downloads":
            self.source_choice.set(source)
        try:
            self.apply_settings(settings)
        except (OSError, ValueError):
            self.source.set(previous_source)
            self.source_choice.set(previous_choice)
            raise

    def use_export_folder(self, provider=None):
        source = provider if provider is not None else self.source.get()
        try:
            get_provider(source)
            if self.settings_error:
                raise ImportErrorDetail(f"Correct the saved settings before choosing an export folder: {self.settings_error}")
            folder = self.settings.sources[source]
            selected = filedialog.askdirectory(parent=self.root, title=f"Select extracted native KiCad exports for {source}",
                                                mustexist=True, initialdir=str(folder if folder.is_dir() else self.repo))
            if not selected:
                return False
            selected = Path(selected).resolve()
            if not selected.is_dir():
                raise ImportErrorDetail("Choose an existing folder containing extracted KiCad files.")
            self.activate_export_folder(selected, source)
            return True
        except (OSError, ValueError) as exc:
            messagebox.showerror("Cannot use export folder", str(exc), parent=self.root)
            return False

    def open_settings(self):
        return FolderSettingsDialog(self.root, self.repo, self.settings, self.apply_settings)

    def open_categories(self):
        return CategoriesDialog(self.root, self.repo, self.settings, self.apply_settings, on_prepare=self.prepare_library_folders)

    def open_history(self):
        if self.settings_error:
            messagebox.showerror("Cannot open history", "Correct the saved loader settings first.", parent=self.root)
            return
        settings = self.settings
        return HistoryDialog(self.root, self.settings.output_root, self.restore_applied,
                             tuple(self.settings.sources.values()) + (self.repo / "Imports",),
                             self.settings.model_variable, categories=settings.categories,
                             model_path_mode=settings.model_path_mode, context_valid=lambda: self.settings == settings)

    def check_kicad_setup(self):
        if self.settings_error:
            messagebox.showerror("Cannot check KiCad setup", "Correct the saved loader settings first.", parent=self.root)
            return
        return DiagnosticsDialog(self.root, self.settings, self.selected_format(), self.category.get())

    def prepare_library_folders(self):
        try:
            if self.settings_error:
                raise ImportErrorDetail(f"Correct the saved settings before preparing folders: {self.settings_error}")
            settings, symbol_format = self.settings, self.selected_format()
            plan = build_folder_plan(self.repo, settings, symbol_format)
            return FolderPreviewDialog(self.root, plan, lambda: self.create_library_folders(settings, symbol_format, plan))
        except (OSError, ValueError) as exc:
            messagebox.showerror("Cannot prepare library folders", str(exc), parent=self.root)

    def create_library_folders(self, settings, symbol_format, reviewed_plan):
        if self.settings != settings or self.selected_format() != symbol_format:
            raise ImportErrorDetail("Settings changed. Reopen the folder preview before creating folders.")
        latest = build_folder_plan(self.repo, settings, symbol_format)
        if (latest.before != reviewed_plan.before or latest.directories != reviewed_plan.directories
                or latest.folders != reviewed_plan.folders or latest.warnings != reviewed_plan.warnings):
            raise ImportErrorDetail("Library contents changed. Reopen the folder preview to review the current layout.")
        commit_plan(settings.output_root, latest)
        self.plan = None
        self.ack.set(False)
        self.log_text("Library folders prepared.\n" + "\n".join(latest.info))

    def apply_settings(self, settings):
        settings = settings.validated(self.repo)
        # Save first; failure leaves the active paths and import plan unchanged.
        self.write_preferences(settings)
        previous_source = self.settings.sources[self.source.get()]
        self.settings, self.settings_error = settings, None
        self.category_combo["values"] = [category.name for category in settings.categories]
        if settings.get_category(self.category.get()) is None:
            self.category.set(settings.categories[0].name)
        if previous_source != settings.sources[self.source.get()]:
            self.symbol.set("")
            self.fp.set("")
            self.model.set("")
        self.refresh()

    def refresh(self):
        self.update_downloads_panel()
        download_notice = self.refresh_downloads() if self.source_choice.get() == "Downloads" else None
        self.plan = None
        self.ack.set(False)
        old = self.symbol.get(), self.fp.get(), self.model.get()
        previous_root = self.inv.root if self.inv else None
        previous_entries = ({name: set(getattr(self.inv, name)) for name in ("symbols", "footprints", "models")}
                            if self.inv else {})
        try:
            input_root = self.settings.sources[self.source.get()]
            if self.source_choice.get() == "Downloads" and not input_root.is_relative_to(self.repo / ".kicad-importer-cache"):
                self.inv = None
                for label in self.combos:
                    self.asset_choices[label] = {}
                    self.combos[label]["values"] = []
                self.symbol.set("")
                self.fp.set("")
                self.model.set("")
                self.changed()
                self.log_text(download_notice or ("Select a downloaded ZIP to load its native KiCad assets. No ZIPs are extracted until you select one or click Load ZIP." if self.download_files else "No ZIP downloads found. Use Folder… to choose a downloads folder, then Refresh."))
                return
            self.inv = scan(self.repo, self.source.get(), input_root=input_root)
            for label, entries in [("Symbol", self.inv.symbols), ("Footprint", self.inv.footprints), ("STEP model", self.inv.models)]:
                self.asset_choices[label] = asset_choices(entries, self.inv.root, symbols=label == "Symbol")
                self.combos[label]["values"] = list(self.asset_choices[label]) if label == "Symbol" else ["", *self.asset_choices[label]]
            self.symbol.set(old[0] if old[0] in self.inv.symbols else next(iter(self.inv.symbols), ""))
            self.select_symbol()
            if previous_root == self.inv.root and old[0] == self.symbol.get():
                self.fp.set(old[1] if not old[1] or old[1] in self.inv.footprints else self.fp.get())
                self.model.set(old[2] if not old[2] or old[2] in self.inv.models else self.model.get())
            self.changed()
            additions = []
            if previous_root == self.inv.root:
                for name, label in (("symbols", "symbols"), ("footprints", "footprints"), ("models", "STEP models")):
                    added = sorted(set(getattr(self.inv, name)) - previous_entries.get(name, set()))
                    if added:
                        preview = "; ".join(added[:5])
                        suffix = f"; and {len(added) - 5} more" if len(added) > 5 else ""
                        additions.append(f"New {label} found: {preview}{suffix}")
            self.log_text("\n".join(([download_notice] if download_notice else []) + additions + ([f"Invalid saved settings: {self.settings_error}. Open Settings and save corrected paths; importing is disabled."] if self.settings_error else []) + self.inv.notices + [f"{len(self.inv.symbols)} symbols · {len(self.inv.footprints)} footprints · {len(self.inv.models)} STEP", "Select each file independently. Empty = skip that part.", f"Symbol output: {self.symbol_format.get()}. Only the selected format will be written."]))
        except (OSError, ValueError) as exc:
            self.inv = None
            self.symbol.set("")
            self.fp.set("")
            self.model.set("")
            for label, combo in self.combos.items():
                combo["values"] = []
                self.asset_choices[label] = {}
                self.asset_displays[label].set("")
            self.changed()
            self.log_text(f"ERROR: {exc}")

    def select_symbol(self):
        symbol = self.inv.symbols.get(self.symbol.get()) if self.inv else None
        fp, model = associate(self.inv, symbol) if symbol else ("", "")
        self.fp.set(fp)
        self.model.set(model)
        self.changed()

    def select_fp(self):
        symbol = self.inv.symbols.get(self.symbol.get()) if self.inv else None
        self.model.set(associate_model(self.inv, symbol, self.fp.get()) if symbol else "")
        self.changed()

    def changed(self):
        self.plan = None
        self.ack.set(False)
        self.entry.configure(state="normal" if self.mode.get() == "Custom" else "disabled")
        try:
            symbol = self.inv.symbols.get(self.symbol.get()) if self.inv else None
            fp = self.inv.footprints.get(self.fp.get()) if self.inv else None
            name = (str(read_tree(fp)[1]) if self.mode.get() == "Original" else self.custom.get() if self.mode.get() == "Custom" else suggestion(symbol, fp)) if symbol and fp else "(no footprint)"
            category = self.settings.get_category(self.category.get())
            if category is None:
                raise ImportErrorDetail("Select a configured category.")
            target = category.symbol_library(self.settings.output_root, self.selected_format())
            if symbol and self.selected_format() == "unpacked":
                target /= f"{symbol.name}.kicad_sym"
            self.output.set(f"Footprint / 3D name: {name}\nSymbol output: {self.symbol_format.get()}\nDestination: {target}")
            model = self.inv.models.get(self.model.get()) if self.inv else None
            self.output_names["Symbol"].set(f"{category.library_name}:{symbol.name}" if symbol else "Not selected")
            self.output_names["Footprint"].set(name + ".kicad_mod" if symbol and fp else "Skipped")
            self.output_names["STEP model"].set(name + model.suffix.lower() if symbol and fp and model else "Skipped")
            self.component_summary.set(symbol.name if symbol else "No component selected")
            prefix = f"Downloads: {self.downloads_folder}\n" if self.source_choice.get() == "Downloads" else ""
            self.folder_summary.set(prefix + f"Input ({self.source.get()}): {self.settings.sources[self.source.get()]}\nOutput: {self.settings.output_root}")
            self.symbol_view.show(symbol.node if symbol else None, True)
            self.fp_view.show(read_tree(fp) if fp else None)
        except (OSError, ValueError, IndexError) as exc:
            self.output.set(f"Error: {exc}")
        self.persist()
        self.update_import_button()

    def update_import_button(self):
        valid = self.plan is not None and (not self.plan.warnings or self.ack.get())
        self.import_button.configure(state="normal" if valid else "disabled")
        symbol = self.inv.symbols.get(self.symbol.get()) if self.inv else None
        fp = self.inv.footprints.get(self.fp.get()) if self.inv else None
        model = self.inv.models.get(self.model.get()) if self.inv else None
        self.model_button.configure(state="normal" if model else "disabled")
        self.symbol_svg_button.configure(state="normal" if symbol and self.cli else "disabled")
        self.fp_svg_button.configure(state="normal" if symbol and fp and self.cli else "disabled")
        if self.settings_error:
            status, detail = "Fix library settings", "Open Library tools → Settings… to correct the saved paths."
        elif self.plan is not None:
            status = "Ready to import" if valid else "Review warnings"
            detail = f"{len(self.plan.warnings)} warning(s). Review the plan below before importing." if self.plan.warnings else "Plan validated. Import will not replace an existing component."
        elif symbol:
            status, detail = "Review required", "Validate the current selection to review its destination files and warnings."
        else:
            status, detail = "Select a component", "Load an export and select a symbol to start."
        self.workflow_status.set(status)
        self.review_status.set(detail)

    def make_plan(self, update=False):
        if self.settings_error:
            raise ImportErrorDetail(f"Correct the saved folder settings before importing: {self.settings_error}")
        if self.inv is None:
            raise ImportErrorDetail("Refresh a source folder before importing.")
        builder = build_update_plan if update else build_plan
        return builder(self.repo, self.inv, self.symbol.get(), self.fp.get(), self.model.get(), self.category.get(), self.mode.get(), self.custom.get(), symbol_format=self.selected_format(),
                          output_root=self.settings.output_root, input_roots=self.settings.sources.values(),
                          model_path_mode=self.settings.model_path_mode, model_variable=self.settings.model_variable,
                          category_config=self.settings.get_category(self.category.get()))

    def make_update_plan(self):
        plan = self.make_plan(update=True)
        plan.history.update({"provider": self.source.get(),
                             "input_mode": "downloads" if self.source_choice.get() == "Downloads" else "provider"})
        return plan

    def review_update(self):
        try:
            return UpdateDialog(self.root, self.make_update_plan(), self.make_update_plan, self.update_applied)
        except (OSError, ValueError, KeyError, IndexError) as exc:
            self.log_text(f"Cannot update: {exc}")
            messagebox.showerror("Cannot update component", str(exc), parent=self.root)

    def restore_applied(self, plan):
        if plan.history.get("operation") == "move":
            if self.settings.get_category(plan.history["category"]):
                self.category.set(plan.history["category"])
        self.plan = None
        self.ack.set(False)
        self.update_import_button()
        message = {"move": "Component moved", "remove": "Component removed", "recover": "Component recovered"}.get(plan.history.get("operation"), "Component restored")
        backup = f"\nBackup: {plan.backup_directory}" if plan.backup_directory else ""
        self.log_text(message + ". History recorded.\n" + "\n".join(plan.info) + backup +
                      "\nReview placed instances in KiCad before updating the schematic or PCB.")

    def update_applied(self, plan):
        self.plan = None
        self.ack.set(False)
        self.update_import_button()
        self.log_text("Component updated. History recorded.\n" + "\n".join(plan.info) +
                      f"\nBackup: {plan.backup_directory}\nReview placed instances in KiCad before updating the schematic or PCB.")

    def selected_format(self):
        return next((key for key, label in SYMBOL_FORMATS.items() if label == self.symbol_format.get()), "unpacked")

    def validate(self):
        self.plan = None
        self.ack.set(False)
        try:
            self.plan = self.make_plan()
            self.log_text("\n".join(self.inv.notices + self.plan.info + ["WARNING: " + w for w in self.plan.warnings] + ["Plan valid. Existing components will not be replaced."]))
        except (OSError, ValueError, KeyError, IndexError) as exc:
            self.log_text(f"Cannot import: {exc}")
        self.update_import_button()

    def import_component(self):
        if self.plan is None:
            return
        try:
            latest = self.make_plan()
            if (latest.files != self.plan.files or latest.before != self.plan.before or latest.warnings != self.plan.warnings or latest.directories != self.plan.directories):
                self.validate()
                self.log_text("Files changed. Review the new plan and import again.\n" + "\n".join(self.plan.info + ["WARNING: " + warning for warning in self.plan.warnings]) if self.plan else "Files changed. Validate again.")
                return
            latest.history.update({"provider": self.source.get(),
                                   "input_mode": "downloads" if self.source_choice.get() == "Downloads" else "provider"})
            commit_plan(self.settings.output_root, latest)
            self.log_text("Import completed. History recorded. \n" + "\n".join(latest.info) + "\nRegister the generated symbol and footprint libraries in KiCad. Existing libraries and KiCad settings were not moved or reconfigured.")
            self.plan = None
            self.update_import_button()
        except (OSError, ValueError, KeyError, IndexError) as exc:
            self.plan = None
            self.update_import_button()
            self.log_text(f"Import cancelled: {exc}")

    def open_model(self):
        try:
            path = self.inv.models.get(self.model.get()) if self.inv else None
            if not path or not path.is_file():
                raise ImportErrorDetail("Select an existing STEP file first.")
            StepWindow(self.root, path)
        except (OSError, ValueError) as exc:
            messagebox.showinfo("STEP preview", str(exc))

    def export_svg(self, kind):
        if self.busy:
            return
        if not self.cli:
            messagebox.showinfo("KiCad", "kicad-cli was not found. Add its bin folder to PATH and restart the GUI.")
            return
        symbol = self.inv.symbols.get(self.symbol.get()) if self.inv else None
        fp = self.inv.footprints.get(self.fp.get()) if self.inv else None
        if not symbol or (kind == "footprint" and not fp):
            return
        self.busy = True
        self.log_text("Generating SVG preview with KiCad…")

        def worker():
            try:
                output = Path(tempfile.mkdtemp(prefix="dvl-preview-"))
                if kind == "symbol":
                    command = [self.cli, "sym", "export", "svg", "--symbol", symbol.name, "--output", str(output), str(symbol.path)]
                else:
                    # Standalone footprints can have a filename different from their internal name.
                    library = output / "preview.pretty"
                    library.mkdir()
                    shutil.copyfile(fp, library / (safe_name(str(read_tree(fp)[1])) + ".kicad_mod"))
                    command = [self.cli, "fp", "export", "svg", "--output", str(output), str(library)]
                result = subprocess.run(command, capture_output=True, text=True, timeout=45, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                svgs = sorted(output.glob("*.svg"))
                if result.returncode or not svgs:
                    raise ImportErrorDetail((result.stderr or result.stdout or "KiCad did not produce an SVG")[-2500:])
                # User-requested preview; no shell interpolation or source execution.
                for svg in svgs:
                    webbrowser.open(svg.as_uri())
                self.root.after(0, lambda: self.log_text(f"SVG opened in the browser ({len(svgs)} view(s)). Temporary files: {output}"))
            except Exception as exc:
                message = str(exc)
                self.root.after(0, lambda: self.log_text(f"SVG preview unavailable: {message}"))
            finally:
                self.busy = False
        threading.Thread(target=worker, daemon=True).start()

    def close(self):
        self.auto_zip_cancel.set()
        if self.download_watch_job is not None:
            self.root.after_cancel(self.download_watch_job)
            self.download_watch_job = None
        self.persist()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", "--repo", dest="repo", type=Path,
                        default=Path(__file__).resolve().parents[1],
                        help="Existing folder for local preferences and initial default paths (--repo is an alias).")
    args = parser.parse_args()
    if not args.repo.is_dir():
        parser.error("The workspace must be an existing folder. Configure source and output folders using Settings.")
    root = tk.Tk()
    App(root, args.repo)
    root.mainloop()


if __name__ == "__main__":
    main()

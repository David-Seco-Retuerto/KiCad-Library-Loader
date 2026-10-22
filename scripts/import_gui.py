"""Run: python scripts/import_gui.py [--workspace PATH]. Python 3.10+ with Tcl/Tk."""
from __future__ import annotations

import argparse
from dataclasses import replace
import math
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
from archive_import import extract_native_zip, discard_extraction
from input_choices import asset_choices, downloaded_zips
from diagnostics_dialog import DiagnosticsDialog
from history_dialog import HistoryDialog
from component_updates import build_update_plan
from update_dialog import UpdateDialog
from settings_dialog import FolderSettingsDialog
from categories_dialog import CategoriesDialog, FolderPreviewDialog

from library_core import (SYMBOL_FORMATS, ImportErrorDetail, associate, associate_model,
                          build_folder_plan, build_plan, child, children, commit_plan, load_preferences,
                          read_tree, safe_name, save_preferences, scan, suggestion, walk)


from kicad_tools import find_cli


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
            width, height = max(c.winfo_width(), 300), max(c.winfo_height(), 200)
            scale = min((width - 120) / max(xmax - xmin, 1), (height - 60) / max(ymax - ymin, 1))

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
        saved_source = self.prefs.get("source")
        self.source = tk.StringVar(value=saved_source if isinstance(saved_source, str) and saved_source in PROVIDERS else next(iter(PROVIDERS)))
        self.source_choice = tk.StringVar(value="Downloads" if self.prefs.get("input_mode") == "downloads" else self.source.get())
        saved_downloads = self.prefs.get("downloads_folder")
        self.downloads_folder = Path(saved_downloads).expanduser().resolve() if isinstance(saved_downloads, str) and saved_downloads.strip() else Path.home() / "Downloads"
        saved_zip = self.prefs.get("active_zip")
        self.active_zip = saved_zip if isinstance(saved_zip, str) else ""
        self.download_zip = tk.StringVar()
        self.download_files = {}
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
        root.title("KiCad Library Loader")
        root.geometry("1120x920")
        root.minsize(860, 700)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        main = ttk.Frame(root, padding=16)
        main.grid(sticky="nsew")
        main.columnconfigure(1, weight=1)
        ttk.Label(main, text="Import component", font=("Segoe UI", 17, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(main, textvariable=self.folder_summary, wraplength=1020).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 12))
        options = ttk.Frame(main)
        options.grid(row=2, column=0, columnspan=3, sticky="ew")
        top = ttk.Frame(options)
        top.pack(fill="x")
        ttk.Label(top, text="Source").pack(side="left")
        source = ttk.Combobox(top, textvariable=self.source_choice, values=["Downloads", *PROVIDERS], state="readonly", width=15)
        source.pack(side="left", padx=10)
        source.bind("<<ComboboxSelected>>", lambda _: self.select_source_choice())
        ttk.Button(top, text="Refresh", command=self.refresh).pack(side="left")
        ttk.Button(top, text="Settings…", command=self.open_settings).pack(side="right")
        ttk.Button(top, text="Categories…", command=self.open_categories).pack(side="right", padx=8)
        ttk.Label(top, text="Category").pack(side="left", padx=(35, 10))
        self.category_combo = ttk.Combobox(top, textvariable=self.category,
                                         values=[category.name for category in self.settings.categories], state="readonly", width=18)
        self.category_combo.pack(side="left")
        format_row = ttk.Frame(options)
        format_row.pack(fill="x", pady=(8, 4))
        ttk.Label(format_row, text="Symbol output").pack(side="left")
        self.format_combo = ttk.Combobox(format_row, textvariable=self.symbol_format,
                                         values=list(SYMBOL_FORMATS.values()), state="readonly", width=27)
        self.format_combo.pack(side="left", padx=10)
        ttk.Button(format_row, text="Check KiCad setup…", command=self.check_kicad_setup).pack(side="right", padx=(10, 0))
        ttk.Button(format_row, text="Prepare library folders…", command=self.prepare_library_folders).pack(side="right")
        download_row = ttk.Frame(options)
        download_row.pack(fill="x", pady=(4, 6))
        ttk.Button(download_row, text="Open ZIP…", command=self.open_zip).pack(side="left", padx=(0, 10))
        ttk.Button(download_row, text="Search online…", command=self.open_search).pack(side="left")
        ttk.Button(download_row, text="Use export folder…", command=self.use_export_folder).pack(side="left", padx=10)
        ttk.Label(download_row, text="Open a download ZIP or refresh an export folder.").pack(side="left")
        self.download_frame = ttk.Frame(options)
        ttk.Label(self.download_frame, text="Downloaded ZIP").pack(side="left")
        self.download_combo = ttk.Combobox(self.download_frame, textvariable=self.download_zip, state="readonly")
        self.download_combo.pack(side="left", fill="x", expand=True, padx=10)
        self.download_combo.bind("<<ComboboxSelected>>", lambda _: self.load_download())
        ttk.Button(self.download_frame, text="Load ZIP", command=self.load_download).pack(side="left")
        ttk.Button(self.download_frame, text="Folder…", command=self.choose_downloads_folder).pack(side="left", padx=(10, 0))
        self.asset_displays = {}
        self.asset_choices = {}
        self.combos = {}
        for row, label, var in [(3, "Symbol", self.symbol), (4, "Footprint", self.fp), (5, "STEP model", self.model)]:
            ttk.Label(main, text=label).grid(row=row, column=0, sticky="w", pady=6)
            display = tk.StringVar()
            self.asset_displays[label] = display
            self.asset_choices[label] = {}
            var.trace_add("write", lambda *_, label=label, var=var: self.sync_asset_display(label, var))
            combo = ttk.Combobox(main, textvariable=display, state="readonly")
            combo.grid(row=row, column=1, columnspan=2, sticky="ew", padx=(12, 0))
            self.combos[label] = combo
        for label in self.combos:
            self.combos[label].bind("<<ComboboxSelected>>", lambda _, label=label: self.select_asset(label))
        naming = ttk.Frame(main)
        naming.grid(row=6, column=0, columnspan=3, sticky="ew", pady=10)
        ttk.Label(naming, text="Footprint / 3D name").pack(side="left", padx=(0, 16))
        for value in ("Original", "Suggestion", "Custom"):
            ttk.Radiobutton(naming, text=value, variable=self.mode, value=value).pack(side="left", padx=5)
        self.entry = ttk.Entry(main, textvariable=self.custom)
        self.entry.grid(row=7, column=1, columnspan=2, sticky="ew", padx=(12, 0))
        ttk.Label(main, text="Custom name").grid(row=7, column=0, sticky="w")
        ttk.Label(main, textvariable=self.output, wraplength=950).grid(row=8, column=0, columnspan=3, sticky="w", pady=8)
        ttk.Label(main, text="Simplified 2D previews (symbol units overlap; some graphics and pad shapes are omitted). Use KiCad SVG for an accurate view.", wraplength=1000).grid(row=9, column=0, columnspan=3, sticky="w")
        previews = ttk.Frame(main)
        previews.grid(row=10, column=0, columnspan=3, sticky="nsew", pady=8)
        main.rowconfigure(10, weight=2)
        previews.columnconfigure((0, 1), weight=1)
        previews.rowconfigure(1, weight=1)
        ttk.Label(previews, text="Symbol").grid(row=0, column=0)
        ttk.Label(previews, text="Footprint").grid(row=0, column=1)
        self.symbol_view, self.fp_view = Drawing(previews), Drawing(previews)
        self.symbol_view.grid(row=1, column=0, sticky="nsew", padx=(0, 5))
        self.fp_view.grid(row=1, column=1, sticky="nsew", padx=(5, 0))
        buttons = ttk.Frame(main)
        buttons.grid(row=11, column=0, columnspan=3, sticky="w")
        ttk.Button(buttons, text="Symbol SVG (KiCad)", command=lambda: self.export_svg("symbol")).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Footprint SVG (KiCad)", command=lambda: self.export_svg("footprint")).pack(side="left", padx=8)
        ttk.Button(buttons, text="Preview STEP in 3D", command=self.open_model).pack(side="left", padx=8)
        self.log = tk.Text(main, height=7, wrap="word", state="disabled", font=("Consolas", 9))
        self.log.grid(row=12, column=0, columnspan=3, sticky="nsew", pady=10)
        main.rowconfigure(12, weight=1)
        ttk.Checkbutton(main, text="I have reviewed the warnings and associations", variable=self.ack).grid(row=13, column=0, columnspan=3, sticky="w")
        actions = ttk.Frame(main)
        actions.grid(row=14, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        ttk.Button(actions, text="Import history…", command=self.open_history).pack(side="left")
        ttk.Button(actions, text="Review update…", command=self.review_update).pack(side="left", padx=8)
        ttk.Frame(actions).pack(side="left", fill="x", expand=True)
        ttk.Button(actions, text="Validate / review plan", command=self.validate).pack(side="left", padx=8)
        self.import_button = ttk.Button(actions, text="Import", command=self.import_component, state="disabled")
        self.import_button.pack(side="left")
        for var in (self.category, self.mode, self.custom, self.symbol_format):
            var.trace_add("write", lambda *_: self.changed())
        self.ack.trace_add("write", lambda *_: self.update_import_button())
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()

    def log_text(self, text):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.insert("end", text)
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
                                "downloads_folder": str(self.downloads_folder), "active_zip": self.active_zip})
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
            self.download_frame.pack(fill="x", pady=(4, 6))
        else:
            self.download_frame.pack_forget()

    def select_source_choice(self):
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
        return SearchDialog(self.root, self.source.get(), symbol.mpn if symbol else "", self.use_export_folder, self.open_zip)

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
        return CategoriesDialog(self.root, self.repo, self.settings, self.apply_settings)

    def open_history(self):
        return HistoryDialog(self.root, self.settings.output_root)

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
            self.log_text(str(exc))

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
                self.log_text("Files changed. Review the new plan and import again.\n" + "\n".join(self.plan.info + self.plan.warnings) if self.plan else "Files changed. Validate again.")
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

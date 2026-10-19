"""Read-only configuration report with explicit KiCad profile and project scope."""
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText

from kicad_diagnostics import config_folders, diagnose, format_report


class DiagnosticsDialog:
    def __init__(self, parent, settings, symbol_format, category):
        self.settings, self.symbol_format = settings, symbol_format
        self.window = tk.Toplevel(parent)
        self.window.title("KiCad setup check")
        self.window.transient(parent)
        self.window.geometry("1020x720")
        self.window.minsize(760, 520)
        frame = ttk.Frame(self.window, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(6, weight=1)
        ttk.Label(frame, text="Check library setup", font=("Segoe UI", 15, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(frame, text="Reads saved KiCad settings and generated libraries. Choose the version you use. Select a project folder to include its library overrides.",
                  wraplength=940).grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 12))
        folders = config_folders()
        self.config = tk.StringVar(value=str(folders[0]) if folders else "")
        self.project = tk.StringVar()
        self.category = tk.StringVar(value=category)
        ttk.Label(frame, text="KiCad settings folder").grid(row=2, column=0, sticky="w")
        ttk.Combobox(frame, textvariable=self.config, values=[str(path) for path in folders]).grid(
            row=2, column=1, sticky="ew", padx=10, pady=5)
        ttk.Button(frame, text="Browse…", command=self.choose_config).grid(row=2, column=2)
        ttk.Label(frame, text="Project folder (optional)").grid(row=3, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.project).grid(row=3, column=1, sticky="ew", padx=10, pady=5)
        project_buttons = ttk.Frame(frame)
        project_buttons.grid(row=3, column=2)
        ttk.Button(project_buttons, text="Browse…", command=self.choose_project).pack(side="left")
        ttk.Button(project_buttons, text="Clear", command=lambda: self.project.set("")).pack(side="left", padx=(5, 0))
        ttk.Label(frame, text="Category").grid(row=4, column=0, sticky="w")
        ttk.Combobox(frame, textvariable=self.category, values=["All categories", *[c.name for c in settings.categories]],
                     state="readonly").grid(row=4, column=1, sticky="ew", padx=10, pady=5)
        ttk.Button(frame, text="Run checks", command=self.run_checks).grid(row=4, column=2)
        ttk.Label(frame, text="Checks the output format selected in the main window. Results do not certify native KiCad loading or electrical/package correctness.",
                  wraplength=940).grid(row=5, column=0, columnspan=3, sticky="w", pady=(8, 10))
        self.report = ScrolledText(frame, wrap="word", font=("Consolas", 10), state="disabled")
        self.report.grid(row=6, column=0, columnspan=3, sticky="nsew")
        ttk.Label(frame, text="No KiCad files are changed. Re-run after correcting settings in KiCad. The running KiCad process may have different environment values or unsaved settings.",
                  wraplength=940).grid(row=7, column=0, columnspan=3, sticky="w", pady=10)
        buttons = ttk.Frame(frame)
        buttons.grid(row=8, column=0, columnspan=3, sticky="e")
        ttk.Button(buttons, text="Copy report", command=self.copy_report).pack(side="left", padx=8)
        ttk.Button(buttons, text="Close", command=self.window.destroy).pack(side="left")
        self.run_checks()

    def choose_config(self):
        folder = filedialog.askdirectory(parent=self.window, title="Select KiCad version settings folder (for example 10.0)", mustexist=True)
        if folder:
            self.config.set(folder)

    def choose_project(self):
        folder = filedialog.askdirectory(parent=self.window, title="Select KiCad project folder", mustexist=True)
        if folder:
            self.project.set(folder)

    def run_checks(self):
        if not self.config.get().strip():
            text = "No KiCad settings folder selected. Browse to the version folder containing sym-lib-table, fp-lib-table and kicad_common.json."
        else:
            try:
                findings = diagnose(self.settings, self.symbol_format, Path(self.config.get()),
                                    project=Path(self.project.get()) if self.project.get().strip() else None,
                                    category_name=None if self.category.get() == "All categories" else self.category.get())
                scope = f"Settings: {self.config.get()}\nProject: {self.project.get() or 'not selected (global tables only)'}\nCategory: {self.category.get()}\nSymbol output: {self.symbol_format}\n\n"
                text = scope + format_report(findings)
            except (OSError, ValueError) as exc:
                text = f"Check could not be completed: {exc}"
        self.report.configure(state="normal")
        self.report.delete("1.0", "end")
        self.report.insert("end", text)
        self.report.configure(state="disabled")

    def copy_report(self):
        self.window.clipboard_clear()
        self.window.clipboard_append(self.report.get("1.0", "end-1c"))

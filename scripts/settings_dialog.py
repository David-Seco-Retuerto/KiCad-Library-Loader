"""Folder settings UI; saving preferences does not move or import any assets."""
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from loader_settings import LoaderSettings, MODEL_PATH_MODES
from providers import PROVIDERS


class FolderSettingsDialog:
    def __init__(self, parent, workspace, settings, on_save):
        self.workspace, self.on_save = workspace, on_save
        self.categories = settings.categories
        self.window = tk.Toplevel(parent)
        self.window.title("Library Loader · Settings")
        self.window.transient(parent)
        self.window.minsize(760, 440)
        self.window.resizable(True, False)
        frame = ttk.Frame(self.window, padding=18)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="Input and output folders", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(frame, text="Input folders are read-only sources. Saving settings does not move existing libraries.").grid(row=1, column=0, columnspan=3, sticky="w", pady=(5, 16))
        self.sources = {}
        row = 2
        for key, provider in PROVIDERS.items():
            variable = tk.StringVar(value=str(settings.sources[key]))
            self.sources[key] = variable
            self.folder_row(frame, row, f"{provider.label} input", variable)
            row += 1
        self.output_root = tk.StringVar(value=str(settings.output_root))
        self.folder_row(frame, row, "Library output root", self.output_root)
        row += 1
        ttk.Label(frame, text="Outputs: Symbols/, Footprints/ and 3DModels/ under the selected output root.").grid(row=row, column=0, columnspan=3, sticky="w", pady=(5, 16))
        row += 1
        self.model_mode = tk.StringVar(value=MODEL_PATH_MODES[settings.model_path_mode])
        ttk.Label(frame, text="3D model paths").grid(row=row, column=0, sticky="w")
        ttk.Combobox(frame, textvariable=self.model_mode, values=list(MODEL_PATH_MODES.values()), state="readonly", width=42).grid(row=row, column=1, columnspan=2, sticky="ew", padx=(12, 0), pady=5)
        row += 1
        self.model_variable = tk.StringVar(value=settings.model_variable)
        ttk.Label(frame, text="KiCad path variable").grid(row=row, column=0, sticky="w")
        self.variable_entry = ttk.Entry(frame, textvariable=self.model_variable)
        self.variable_entry.grid(row=row, column=1, columnspan=2, sticky="ew", padx=(12, 0), pady=5)
        row += 1
        ttk.Label(frame, text="Portable mode: set the variable in KiCad to the selected output root. Changing a shared variable also affects older libraries. Absolute mode needs no variable, but paths must be updated if you move the library.", wraplength=720).grid(row=row, column=0, columnspan=3, sticky="w", pady=(8, 12))
        row += 1
        ttk.Label(frame, text="Missing input folders are allowed and will be reported when scanning. Create outputs when importing or with Prepare library folders… in the main window.", wraplength=720).grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 12))
        row += 1
        actions = ttk.Frame(frame)
        actions.grid(row=row, column=0, columnspan=3, sticky="ew")
        ttk.Button(actions, text="Restore defaults", command=self.restore_defaults).pack(side="left")
        ttk.Button(actions, text="Cancel", command=self.window.destroy).pack(side="right")
        ttk.Button(actions, text="Save settings", command=self.save).pack(side="right", padx=10)
        self.model_mode.trace_add("write", lambda *_: self.update_mode())
        self.update_mode()
        self.window.grab_set()

    def folder_row(self, parent, row, label, variable):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=variable, width=65).grid(row=row, column=1, sticky="ew", padx=(12, 8), pady=5)
        ttk.Button(parent, text="Browse…", command=lambda: self.browse(variable)).grid(row=row, column=2)

    def browse(self, variable):
        selected = filedialog.askdirectory(parent=self.window, title="Choose folder", mustexist=True)
        if selected:
            variable.set(selected)

    def update_mode(self):
        self.variable_entry.configure(state="normal" if self.model_mode.get() == MODEL_PATH_MODES["variable"] else "disabled")

    def restore_defaults(self):
        settings = LoaderSettings.defaults(self.workspace)
        for key, variable in self.sources.items():
            variable.set(str(settings.sources[key]))
        self.output_root.set(str(settings.output_root))
        self.model_mode.set(MODEL_PATH_MODES[settings.model_path_mode])
        self.model_variable.set(settings.model_variable)

    def save(self):
        try:
            mode = next(key for key, value in MODEL_PATH_MODES.items() if value == self.model_mode.get())
            settings = LoaderSettings({key: v.get() for key, v in self.sources.items()}, self.output_root.get(),
                                      mode, self.model_variable.get(), self.categories).validated(self.workspace)
            self.on_save(settings)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Settings not saved", str(exc), parent=self.window)
            return
        self.window.destroy()

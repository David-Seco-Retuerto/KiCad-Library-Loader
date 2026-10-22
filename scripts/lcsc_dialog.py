"""Responsive single-part LCSC download using the loader dependency, with an optional external override."""
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from lcsc_download import (DownloadCancelled, converter_path, discard_download,
                           download_lcsc, installed_converter, lcsc_code)


class LcscDownloadDialog:
    def __init__(self, parent, workspace, executable, initial_code, remember, loaded, use_external=False):
        self.workspace, self.remember, self.loaded = workspace, remember, loaded
        self.window = tk.Toplevel(parent)
        self.window.title("Download LCSC component")
        self.window.transient(parent)
        self.window.resizable(True, False)
        self.executable = tk.StringVar(value=executable)
        self.use_external = tk.BooleanVar(value=use_external)
        self.code = tk.StringVar(value=initial_code)
        self.status = tk.StringVar(value="Enter the exact LCSC code. The loader uses its installed converter; nothing is imported automatically.")
        self.cancelled = threading.Event()
        self.messages = queue.Queue()
        self.running = False
        self.closed = False
        self.job = None
        frame = ttk.Frame(self.window, padding=18)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="Download one LCSC component", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        ttk.Label(frame, text="LCSC part code").grid(row=1, column=0, sticky="w", pady=10)
        self.code_entry = ttk.Entry(frame, textvariable=self.code, width=24)
        self.code_entry.grid(row=1, column=1, sticky="w", padx=10)
        ttk.Label(frame, text="Example: C2040").grid(row=1, column=2, sticky="w")
        ttk.Label(frame, text="easyeda2kicad is installed with the loader. Choose the exact manufacturer/package using Search online if needed. "
                  "Downloads are converted in a new cache folder for review; library import still requires your confirmation.",
                  wraplength=740).grid(row=2, column=0, columnspan=3, sticky="w", pady=10)
        self.external_check = ttk.Checkbutton(frame, text="Use an external converter (advanced)", variable=self.use_external,
                                              command=self.toggle_external)
        self.external_check.grid(row=3, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self.external_frame = ttk.Frame(frame)
        self.external_frame.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        self.external_frame.columnconfigure(1, weight=1)
        ttk.Label(self.external_frame, text="Converter executable").grid(row=0, column=0, sticky="w")
        self.tool_entry = ttk.Entry(self.external_frame, textvariable=self.executable, width=64)
        self.tool_entry.grid(row=0, column=1, sticky="ew", padx=10)
        self.browse_button = ttk.Button(self.external_frame, text="Browse…", command=self.browse)
        self.browse_button.grid(row=0, column=2)
        self.toggle_external()
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.grid(row=5, column=0, columnspan=3, sticky="ew")
        ttk.Label(frame, textvariable=self.status, wraplength=740).grid(row=6, column=0, columnspan=3, sticky="w", pady=12)
        buttons = ttk.Frame(frame)
        buttons.grid(row=7, column=0, columnspan=3, sticky="e")
        self.cancel_button = ttk.Button(buttons, text="Close", command=self.cancel)
        self.cancel_button.pack(side="left", padx=8)
        self.download_button = ttk.Button(buttons, text="Download and load for review", command=self.start)
        self.download_button.pack(side="left")
        self.window.protocol("WM_DELETE_WINDOW", self.cancel)
        self.window.bind("<Escape>", lambda _: self.cancel())
        self.window.bind("<Destroy>", self.destroyed, add="+")

    def toggle_external(self):
        if self.use_external.get():
            self.external_frame.grid()
        else:
            self.external_frame.grid_remove()

    def browse(self):
        selected = filedialog.askopenfilename(parent=self.window, title="Select easyeda2kicad executable")
        if selected:
            self.executable.set(selected)

    def set_running(self, running):
        self.running = running
        for widget in (self.tool_entry, self.code_entry, self.browse_button, self.download_button, self.external_check):
            widget.configure(state="disabled" if running else "normal")
        self.cancel_button.configure(text="Cancel download" if running else "Close", state="normal")
        self.progress.configure(value=0)

    def start(self):
        if self.running or self.closed:
            return False
        try:
            code = lcsc_code(self.code.get())
            tool = converter_path(self.executable.get()) if self.use_external.get() else installed_converter()
            self.remember(self.executable.get(), self.use_external.get())
        except (OSError, ValueError) as exc:
            messagebox.showerror("Cannot start download", str(exc), parent=self.window)
            return False
        self.code.set(code)
        self.cancelled.clear()
        self.set_running(True)
        self.status.set(f"Downloading and converting {code}… No library files are being written.")
        self.worker = threading.Thread(target=self.work, args=(str(tool), code), daemon=False)
        self.worker.start()
        self.job = self.window.after(100, self.drain)
        return True

    def work(self, tool, code):
        try:
            result = download_lcsc(self.workspace, tool, code, self.cancelled)
            self.messages.put(("success", result))
            if self.closed:
                self.cleanup_messages()
        except DownloadCancelled as exc:
            self.messages.put(("cancelled", str(exc)))
        except Exception as exc:
            self.messages.put(("error", str(exc)))

    def cleanup_messages(self):
        while True:
            try:
                kind, value = self.messages.get_nowait()
            except queue.Empty:
                return
            if kind == "success":
                discard_download(value.folder, self.workspace)

    def drain(self):
        self.job = None
        if self.closed:
            return
        try:
            kind, value = self.messages.get_nowait()
        except queue.Empty:
            self.progress.step(3)
            self.job = self.window.after(100, self.drain)
            return
        self.set_running(False)
        if kind == "success":
            if self.cancelled.is_set():
                discard_download(value.folder, self.workspace)
                self.status.set("Download cancelled. The previously loaded component is unchanged.")
                return
            try:
                self.loaded(value)
            except (OSError, ValueError) as exc:
                discard_download(value.folder, self.workspace)
                self.status.set("Download could not be loaded. The previous input was retained.")
                messagebox.showerror("Cannot load download", str(exc), parent=self.window)
                return
            self.window.destroy()
        elif kind == "cancelled":
            self.status.set(value)
        else:
            self.status.set("Download failed. The previously loaded component is unchanged.")
            messagebox.showerror("LCSC download failed", value, parent=self.window)

    def cancel(self):
        if self.running:
            self.cancelled.set()
            self.cancel_button.configure(state="disabled")
            self.status.set("Cancelling download…")
        else:
            self.window.destroy()

    def destroyed(self, event):
        if event.widget is self.window:
            self.closed = True
            self.cancelled.set()
            if self.job is not None:
                self.window.after_cancel(self.job)
                self.job = None
            self.cleanup_messages()

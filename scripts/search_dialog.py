"""Browser search handoff; downloads and native-file imports stay explicit."""
import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser

from providers import PROVIDERS, get_provider


class SearchDialog:
    def __init__(self, parent, provider, initial_query, use_export_folder):
        self.window = tk.Toplevel(parent)
        self.window.title("Search for component models")
        self.window.transient(parent)
        self.window.resizable(True, False)
        self.provider = tk.StringVar(value=provider)
        self.query = tk.StringVar(value=initial_query)
        self.url = tk.StringVar()
        self.status = tk.StringVar(value="Search opens your default browser.")
        self.use_export_folder = use_export_folder
        frame = ttk.Frame(self.window, padding=18)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="Find a component", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        ttk.Label(frame, text="Provider").grid(row=1, column=0, sticky="w")
        ttk.Combobox(frame, textvariable=self.provider, values=list(PROVIDERS), state="readonly",
                     width=24).grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=5)
        ttk.Label(frame, text="Part number / keyword").grid(row=2, column=0, sticky="w")
        entry = ttk.Entry(frame, textvariable=self.query, width=52)
        entry.grid(row=2, column=1, sticky="ew", padx=(12, 0), pady=5)
        ttk.Entry(frame, textvariable=self.url, state="readonly").grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(8, 12))
        ttk.Label(frame, text=("1. Search and download the native KiCad files in your browser.\n"
                               "2. Extract ZIP downloads into a separate folder.\n"
                               "3. Use export folder… below, or Refresh in the main window if you used the current input folder.\n"
                               "4. Select the assets and validate the import as usual."),
                  wraplength=620, justify="left").grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text="SamacSys opens ms.componentsearchengine.com. Sign in there first; reopen this search if login clears the results. LCSC exports may need conversion to native KiCad files.",
                  wraplength=620).grid(row=5, column=0, columnspan=2, sticky="w", pady=10)
        ttk.Label(frame, textvariable=self.status, wraplength=620).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(0, 12))
        buttons = ttk.Frame(frame)
        buttons.grid(row=7, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="Open search in browser", command=self.open_search).pack(side="left", padx=5)
        ttk.Button(buttons, text="Use export folder…", command=self.choose_folder).pack(side="left", padx=5)
        ttk.Button(buttons, text="Close", command=self.window.destroy).pack(side="left", padx=5)
        self.query.trace_add("write", lambda *_: self.update_url())
        self.provider.trace_add("write", lambda *_: self.update_url())
        entry.bind("<Return>", lambda _: self.open_search())
        self.window.bind("<Escape>", lambda _: self.window.destroy())
        self.update_url()
        entry.focus_set()

    def update_url(self):
        try:
            self.url.set(get_provider(self.provider.get()).search_url(self.query.get()))
        except ValueError:
            self.url.set("")

    def open_search(self):
        try:
            url = get_provider(self.provider.get()).search_url(self.query.get())
            if not webbrowser.open(url, new=2):
                raise OSError("No browser accepted the request. Copy the URL above into your browser.")
        except (OSError, ValueError, webbrowser.Error) as exc:
            self.status.set("Search could not be opened. No files were imported.")
            messagebox.showerror("Cannot open search", str(exc), parent=self.window)
            return False
        self.status.set("Browser opened. Download and extract the native KiCad files, then choose their folder.")
        return True

    def choose_folder(self):
        if self.use_export_folder(self.provider.get()):
            self.window.destroy()

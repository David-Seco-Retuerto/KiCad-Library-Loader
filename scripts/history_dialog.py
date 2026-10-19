"""Browse immutable import records for the selected output library root."""
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from import_history import describe_record, read_history


class HistoryDialog:
    def __init__(self, parent, output_root):
        self.output_root = output_root
        self.records = []
        self.visible = {}
        self.window = tk.Toplevel(parent)
        self.window.title("Import history")
        self.window.transient(parent)
        self.window.geometry("1080x740")
        self.window.minsize(760, 520)
        frame = ttk.Frame(self.window, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=1)
        frame.rowconfigure(4, weight=2)
        ttk.Label(frame, text="Import history", font=("Segoe UI", 15, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text=f"Output library: {output_root}", wraplength=980).grid(row=1, column=0, sticky="w", pady=6)
        toolbar = ttk.Frame(frame)
        toolbar.grid(row=2, column=0, sticky="ew", pady=8)
        ttk.Label(toolbar, text="Filter").pack(side="left")
        self.query = tk.StringVar()
        ttk.Entry(toolbar, textvariable=self.query, width=45).pack(side="left", padx=10)
        ttk.Button(toolbar, text="Refresh", command=self.reload).pack(side="right")
        self.table = ttk.Treeview(frame, columns=("time", "symbol", "category", "format"), show="headings", height=8)
        for key, title, width in (("time", "Imported (UTC)", 190), ("symbol", "Component", 290),
                                  ("category", "Category", 160), ("format", "Symbol format", 120)):
            self.table.heading(key, text=title)
            self.table.column(key, width=width)
        self.table.grid(row=3, column=0, sticky="nsew")
        self.details = ScrolledText(frame, wrap="word", state="disabled", font=("Consolas", 10))
        self.details.grid(row=4, column=0, sticky="nsew", pady=(10, 0))
        self.status = tk.StringVar()
        ttk.Label(frame, textvariable=self.status, wraplength=980).grid(row=5, column=0, sticky="w", pady=8)
        buttons = ttk.Frame(frame)
        buttons.grid(row=6, column=0, sticky="e")
        ttk.Button(buttons, text="Copy details", command=self.copy_details).pack(side="left", padx=8)
        ttk.Button(buttons, text="Close", command=self.window.destroy).pack(side="left")
        self.table.bind("<<TreeviewSelect>>", lambda _: self.show_selected())
        self.query.trace_add("write", lambda *_: self.render())
        self.reload()

    def reload(self):
        try:
            self.records, notices = read_history(self.output_root)
            self.status.set(f"{len(self.records)} import record(s). " + (" ".join(notices) if notices else "Earlier imports are not reconstructed automatically. History does not delete or undo components."))
        except OSError as exc:
            self.records = []
            self.status.set(f"History could not be read: {exc}")
        self.render()

    def render(self):
        self.table.delete(*self.table.get_children())
        self.visible = {}
        query = self.query.get().casefold().strip()
        for index, record in enumerate(self.records):
            if query and query not in " ".join(str(record.get(key, "")) for key in ("symbol", "mpn", "category", "library_name", "provider")).casefold():
                continue
            key = str(index)
            self.visible[key] = record
            self.table.insert("", "end", iid=key, values=(record["imported_at_utc"], record["symbol"], record["category"], record["symbol_format"]))
        rows = self.table.get_children()
        if rows:
            self.table.selection_set(rows[0])
        self.show_selected()

    def show_selected(self):
        selected = self.table.selection()
        record = self.visible.get(selected[0]) if selected else None
        text = describe_record(record) if record else "No matching import records. New successful imports will appear here."
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("end", text)
        self.details.configure(state="disabled")

    def copy_details(self):
        self.window.clipboard_clear()
        self.window.clipboard_append(self.details.get("1.0", "end-1c"))

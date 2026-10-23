"""Browse immutable import records for the selected output library root."""
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from import_history import describe_record, read_history, component_identity, current_components
from move_dialog import MoveDialog
from component_restore import build_restore_plan
from component_remove import build_remove_plan, build_recover_plan
from update_dialog import UpdateDialog


class HistoryDialog:
    def __init__(self, parent, output_root, applied=None, protected_roots=(), model_variable="DVL_LIB_ROOT", categories=(), model_path_mode="variable", context_valid=lambda: True):
        self.categories, self.model_path_mode, self.context_valid = tuple(categories), model_path_mode, context_valid
        self.applied = applied
        self.protected_roots = protected_roots
        self.model_variable = model_variable
        self.output_root = output_root
        self.records = []
        self.visible = {}
        self.window = tk.Toplevel(parent)
        self.window.title("Import history")
        self.window.transient(parent)
        self.window.geometry("1080x740")
        self.window.minsize(980, 520)
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
        self.move_button = ttk.Button(buttons, text="Move to category…", command=self.move_selected, state="disabled")
        self.move_button.pack(side="left", padx=8)
        self.remove_button = ttk.Button(buttons, text="Remove component…", command=self.remove_selected, state="disabled")
        self.remove_button.pack(side="left", padx=8)
        self.recover_button = ttk.Button(buttons, text="Recover removed…", command=self.recover_selected, state="disabled")
        self.recover_button.pack(side="left", padx=8)
        self.restore_button = ttk.Button(buttons, text="Restore…", command=self.restore_selected, state="disabled")
        self.restore_button.pack(side="left", padx=8)
        ttk.Button(buttons, text="Copy details", command=self.copy_details).pack(side="left", padx=8)
        ttk.Button(buttons, text="Close", command=self.window.destroy).pack(side="left")
        self.table.bind("<<TreeviewSelect>>", lambda _: self.show_selected())
        self.query.trace_add("write", lambda *_: self.render())
        self.reload()

    def reload(self):
        try:
            self.records, notices = read_history(self.output_root)
            self.status.set(f"{len(self.records)} import record(s). " + (" ".join(notices) if notices else "Select the latest component record to move/remove, an update to restore, or a removal to recover. All changes require review."))
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
        active = current_components(self.records).get(component_identity(record)) if record else None
        can_move = active is not None and active["event_id"] == record["event_id"] and bool(self.categories)
        is_active = active is not None and record is not None and active["event_id"] == record["event_id"]
        self.remove_button.configure(state="normal" if is_active else "disabled")
        latest = next((r for r in self.records if record and component_identity(r) == component_identity(record)), None)
        self.recover_button.configure(state="normal" if record and record.get("operation") == "remove" and latest is record else "disabled")
        self.move_button.configure(state="normal" if can_move else "disabled")
        self.restore_button.configure(state="normal" if active is not None and record and active["event_id"] == record["event_id"] and record.get("operation") == "update" else "disabled")
        text = describe_record(record) if record else "No matching import records. New successful imports will appear here."
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("end", text)
        self.details.configure(state="disabled")

    def copy_details(self):
        self.window.clipboard_clear()
        self.window.clipboard_append(self.details.get("1.0", "end-1c"))

    def restore_selected(self):
        selected = self.table.selection()
        record = self.visible.get(selected[0]) if selected else None
        if not record or record.get("operation") != "update":
            return None
        event_id = record["event_id"]

        def rebuild():
            return build_restore_plan(self.output_root, event_id, self.protected_roots, self.model_variable)

        def applied(plan):
            self.reload()
            if self.applied:
                self.applied(plan)

        try:
            return UpdateDialog(self.window, rebuild(), rebuild, applied)
        except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
            messagebox.showerror("Cannot restore component", str(exc), parent=self.window)
            return None

    def move_selected(self):
        selected = self.table.selection()
        record = self.visible.get(selected[0]) if selected else None
        active = current_components(self.records).get(component_identity(record)) if record else None
        if active is None or active["event_id"] != record["event_id"]:
            return None
        def applied(plan):
            self.reload()
            if self.applied:
                self.applied(plan)
        return MoveDialog(self.window, self.output_root, record, self.categories, applied,
                          self.protected_roots, self.model_path_mode, self.model_variable, self.context_valid)

    def review_lifecycle(self, operation):
        selected = self.table.selection()
        record = self.visible.get(selected[0]) if selected else None
        if not record:
            return None
        event_id = record["event_id"]
        def rebuild():
            if not self.context_valid():
                raise ValueError("Loader settings changed. Reopen Import history before applying this action.")
            if operation == "remove":
                return build_remove_plan(self.output_root, event_id, self.protected_roots, self.model_variable)
            return build_recover_plan(self.output_root, event_id, self.protected_roots)
        def applied(plan):
            self.reload()
            if self.applied:
                self.applied(plan)
        try:
            return UpdateDialog(self.window, rebuild(), rebuild, applied)
        except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
            messagebox.showerror("Cannot remove component" if operation == "remove" else "Cannot recover component", str(exc), parent=self.window)
            return None

    def remove_selected(self):
        return self.review_lifecycle("remove")

    def recover_selected(self):
        return self.review_lifecycle("recover")

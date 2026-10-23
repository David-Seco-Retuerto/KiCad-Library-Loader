"""Choose a category and explicitly review a tracked component relocation."""
import tkinter as tk
from tkinter import messagebox, ttk

from component_move import build_move_plan
from update_dialog import UpdateDialog


class MoveDialog:
    def __init__(self, parent, output_root, record, categories, applied, protected_roots=(),
                 model_path_mode="variable", model_variable="DVL_LIB_ROOT", context_valid=lambda: True):
        self.output_root, self.record, self.categories = output_root, record, tuple(categories)
        self.applied, self.protected_roots = applied, protected_roots
        self.model_path_mode, self.model_variable, self.context_valid = model_path_mode, model_variable, context_valid
        self.window = tk.Toplevel(parent)
        self.window.title("Move component to category")
        self.window.transient(parent)
        self.window.resizable(True, False)
        frame = ttk.Frame(self.window, padding=18)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text=f"Move {record['symbol']}", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        ttk.Label(frame, text=f"From: {record['category']} / {record['library_name']} | Format: {record['symbol_format']}").grid(row=1, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text="Destination category").grid(row=2, column=0, sticky="w", pady=12)
        choices = [category.name for category in categories if category.name != record["category"]]
        self.target = tk.StringVar(value=choices[0] if choices else "")
        ttk.Combobox(frame, textvariable=self.target, values=choices, state="readonly", width=32).grid(row=2, column=1, sticky="ew", padx=12)
        self.status = tk.StringVar(value="Review the complete file plan before applying. Existing project assignments are not changed automatically.")
        ttk.Label(frame, textvariable=self.status, wraplength=680).grid(row=3, column=0, columnspan=2, sticky="w", pady=10)
        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="Close", command=self.window.destroy).pack(side="left", padx=8)
        self.review_button = ttk.Button(buttons, text="Review move…", command=self.review, state="normal" if choices else "disabled")
        self.review_button.pack(side="left")

    def build(self):
        if not self.context_valid():
            raise ValueError("Loader settings changed. Reopen Import history before moving a component.")
        target = next((item for item in self.categories if item.name == self.target.get()), None)
        return build_move_plan(self.output_root, self.record["event_id"], target, self.protected_roots,
                               self.model_path_mode, self.model_variable)

    def moved(self, plan):
        self.applied(plan)
        self.review_button.configure(state="disabled")
        self.status.set("Component moved. Close this window and review its library assignments in KiCad.")

    def review(self):
        try:
            return UpdateDialog(self.window, self.build(), self.build, self.moved)
        except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
            messagebox.showerror("Cannot move component", str(exc), parent=self.window)
            return None

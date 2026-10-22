"""Explicit review and confirmation for a tracked in-place component update."""
import difflib
import hashlib
from pathlib import Path
from step_preview import StepWindow
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from component_updates import same_update_plan
from library_core import commit_plan


def describe_changes(plan):
    lines = list(plan.info) + ["", *["WARNING: " + warning for warning in plan.warnings]]
    for path, role in plan.assets.items():
        before = plan.before[path]
        after = plan.files.get(path, before)
        if before == after:
            continue
        lines += ["", f"--- Changed {role}: {path.name} ---",
                  f"Before: {len(before)} bytes | SHA256 {hashlib.sha256(before).hexdigest()}",
                  f"After: {len(after)} bytes | SHA256 {hashlib.sha256(after).hexdigest()}"]
        if role != "model":
            diff = list(difflib.unified_diff(before.decode("utf-8-sig").splitlines(), after.decode("utf-8-sig").splitlines(),
                                           fromfile="Existing", tofile="Incoming", lineterm=""))
            lines.extend(diff[:600])
            if len(diff) > 600:
                lines.append(f"[Diff preview truncated: {len(diff) - 600} more lines]")
        else:
            lines.append("STEP contents differ. Inspect the incoming model in the main window and check its alignment.")
    return "\n".join(lines)


class UpdateDialog:
    def __init__(self, parent, plan, rebuild, applied):
        self.plan, self.rebuild, self.applied = plan, rebuild, applied
        self.window = tk.Toplevel(parent)
        self.window.title("Review component update")
        self.window.transient(parent)
        self.window.geometry("1080x760")
        self.window.minsize(780, 540)
        frame = ttk.Frame(self.window, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)
        ttk.Label(frame, text="Review component update", font=("Segoe UI", 15, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text="Existing names are retained. Changed files will be backed up before replacement. Shared assets and manual edits are blocked. STEP previews show the raw models without footprint transforms.",
                  wraplength=1000).grid(row=1, column=0, sticky="w", pady=10)
        self.report = ScrolledText(frame, wrap="word", font=("Consolas", 10), state="disabled")
        self.report.grid(row=2, column=0, sticky="nsew")
        self.reviewed = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="I reviewed the changes and warnings, including effects on existing designs", variable=self.reviewed).grid(row=3, column=0, sticky="w", pady=10)
        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, sticky="e")
        existing_model = next((path for path, role in plan.assets.items() if role == "model"), None)
        incoming_model = plan.history.get("source_files", {}).get("model")
        if existing_model and incoming_model:
            ttk.Button(buttons, text="Existing STEP…", command=lambda: self.preview_model(existing_model)).pack(side="left", padx=5)
            ttk.Button(buttons, text="Incoming STEP…", command=lambda: self.preview_model(Path(incoming_model))).pack(side="left", padx=5)
        ttk.Button(buttons, text="Cancel", command=self.window.destroy).pack(side="left", padx=8)
        self.apply_button = ttk.Button(buttons, text="Back up and apply update", command=self.apply, state="disabled")
        self.apply_button.pack(side="left")
        self.reviewed.trace_add("write", lambda *_: self.apply_button.configure(state="normal" if self.reviewed.get() else "disabled"))
        self.render()

    def preview_model(self, path):
        try:
            return StepWindow(self.window, path)
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror("STEP preview unavailable", str(exc), parent=self.window)

    def render(self):
        self.report.configure(state="normal")
        self.report.delete("1.0", "end")
        self.report.insert("end", describe_changes(self.plan))
        self.report.configure(state="disabled")

    def apply(self):
        if not self.reviewed.get():
            return False
        try:
            latest = self.rebuild()
            if not same_update_plan(self.plan, latest):
                self.plan = latest
                self.reviewed.set(False)
                self.render()
                messagebox.showinfo("Review changed", "Source, destination or dependencies changed. Review the refreshed plan before applying.", parent=self.window)
                return False
            commit_plan(latest.output_root, latest)
        except (OSError, ValueError, KeyError, IndexError) as exc:
            self.reviewed.set(False)
            messagebox.showerror("Update blocked", str(exc), parent=self.window)
            return False
        self.applied(latest)
        self.window.destroy()
        return True

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
    for path, role in {**plan.assets, **plan.related_assets}.items():
        before = plan.before[path]
        after = None if path in plan.removals else plan.files.get(path, before)
        if before == after:
            continue
        lines += ["", f"--- Changed {role}: {path.name} ---",
                  f"Before: {len(before) if before is not None else 0} bytes | SHA256 {hashlib.sha256(before).hexdigest() if before is not None else 'Not present'}",
                  f"After: {len(after) if after is not None else 0} bytes | SHA256 {hashlib.sha256(after).hexdigest() if after is not None else 'Removed'}"]
        if role not in {"model", "source_model"}:
            diff = list(difflib.unified_diff((before or b"").decode("utf-8-sig").splitlines(), (after or b"").decode("utf-8-sig").splitlines(),
                                           fromfile="Existing", tofile="Incoming", lineterm=""))
            lines.extend(diff[:600])
            if len(diff) > 600:
                lines.append(f"[Diff preview truncated: {len(diff) - 600} more lines]")
        else:
            lines.append("STEP contents differ. Use the STEP previews and check alignment in KiCad.")
    return "\n".join(lines)


class UpdateDialog:
    def __init__(self, parent, plan, rebuild, applied):
        self.plan, self.rebuild, self.applied = plan, rebuild, applied
        self.window = tk.Toplevel(parent)
        self.restoring = plan.history.get("operation") == "restore"
        self.moving = plan.history.get("operation") == "move"
        self.removing = plan.history.get("operation") == "remove"
        self.recovering = plan.history.get("operation") == "recover"
        title = "Review component removal" if self.removing else "Recover removed component" if self.recovering else "Review category move" if self.moving else "Review component restoration" if self.restoring else "Review component update"
        self.window.title(title)
        self.window.transient(parent)
        self.window.geometry("1080x760")
        self.window.minsize(780, 540)
        frame = ttk.Frame(self.window, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)
        ttk.Label(frame, text=title, font=("Segoe UI", 15, "bold")).grid(row=0, column=0, sticky="w")
        explanation = ("Names and format are retained. Shared source assets stay in place. Old symbol references in existing projects need reassignment. Changed/removed files are backed up first." if self.moving else
                       "Existing names are retained. Changed files will be backed up before replacement. Shared assets and manual edits are blocked. STEP previews show the raw models without footprint transforms.")
        if self.removing:
            explanation = "The symbol is removed after backup. Shared footprints/models remain. Existing project references may break; project files are not modified."
        elif self.recovering:
            explanation = "Recover from verified removal backups. Existing symbols and differing files cannot be replaced. Other packed-library symbols are preserved."
        ttk.Label(frame, text=explanation,
                  wraplength=1000).grid(row=1, column=0, sticky="w", pady=10)
        self.report = ScrolledText(frame, wrap="word", font=("Consolas", 10), state="disabled")
        self.report.grid(row=2, column=0, sticky="nsew")
        self.reviewed = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="I reviewed the changes and warnings, including effects on existing designs", variable=self.reviewed).grid(row=3, column=0, sticky="w", pady=10)
        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, sticky="e")
        existing_model = next((path for path, role in plan.assets.items() if role == "model"), None)
        incoming_model = plan.history.get("source_files", {}).get("model")
        if self.removing or self.recovering:
            existing_model = incoming_model = None
        if self.moving:
            old_model = plan.history.get("move_sources", {}).get("model")
            existing_model = plan.output_root / old_model if old_model else None
            incoming_model = None
            if existing_model:
                ttk.Button(buttons, text="STEP model…", command=lambda: self.preview_model(existing_model)).pack(side="left", padx=5)
        if self.restoring and existing_model:
            incoming_model = (plan.output_root / plan.history["restore_backup_folder"] / existing_model.relative_to(plan.output_root)
                              if existing_model in plan.files else existing_model)
        if existing_model and incoming_model:
            ttk.Button(buttons, text="Existing STEP…", command=lambda: self.preview_model(existing_model)).pack(side="left", padx=5)
            ttk.Button(buttons, text="Restored STEP…" if self.restoring else "Incoming STEP…", command=lambda: self.preview_model(Path(incoming_model))).pack(side="left", padx=5)
        ttk.Button(buttons, text="Cancel", command=self.window.destroy).pack(side="left", padx=8)
        self.apply_button = ttk.Button(buttons, text="Back up and remove" if self.removing else "Recover component" if self.recovering else "Back up and move" if self.moving else "Back up and restore" if self.restoring else "Back up and apply update", command=self.apply, state="disabled")
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
            messagebox.showerror("Removal blocked" if self.removing else "Recovery blocked" if self.recovering else "Move blocked" if self.moving else "Restore blocked" if self.restoring else "Update blocked", str(exc), parent=self.window)
            return False
        self.applied(latest)
        self.window.destroy()
        return True

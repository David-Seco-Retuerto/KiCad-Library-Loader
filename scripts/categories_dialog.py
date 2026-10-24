"""Category configuration and explicit, reviewable library-folder preparation."""
from dataclasses import replace
import tkinter as tk
from tkinter import messagebox, ttk

from library_layout import DEFAULT_CATEGORIES, LibraryCategory, validate_categories


class CategoriesDialog:
    def __init__(self, parent, workspace, settings, on_save, on_prepare=None):
        self.workspace, self.settings, self.on_save = workspace, settings, on_save
        self.on_prepare = on_prepare
        self.categories = list(settings.categories)
        self.window = tk.Toplevel(parent)
        self.window.title("Library Loader · Categories")
        self.window.transient(parent)
        self.window.minsize(780, 540)
        frame = ttk.Frame(self.window, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(2, weight=1)
        ttk.Label(frame, text="Categories and library names", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(frame, text="Enter base names only: suffixes are added automatically. Changes affect future imports; existing libraries are never renamed, moved or deleted.", wraplength=740).grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 12))
        table = ttk.Frame(frame)
        table.grid(row=2, column=0, columnspan=3, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(table, columns=("name", "library", "models"), show="headings", selectmode="browse", height=8)
        for key, label in [("name", "Category"), ("library", "Library base name"), ("models", "3D folder")]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=220, minwidth=100)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self.select)
        self.name, self.library_name, self.model_folder = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for row, label, variable in [(3, "Category", self.name), (4, "Library base name", self.library_name), (5, "3D folder", self.model_folder)]:
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=5)
            ttk.Entry(frame, textvariable=variable).grid(row=row, column=1, columnspan=2, sticky="ew", padx=(12, 0), pady=5)
        ttk.Label(frame, text="For a new category, blank library and 3D names use the category name. Example: Analog / MyLib_Analog / Analog.", wraplength=740).grid(row=6, column=0, columnspan=3, sticky="w", pady=5)
        edits = ttk.Frame(frame)
        edits.grid(row=7, column=0, columnspan=3, sticky="w", pady=8)
        for label, command in [("New", self.new), ("Add category", self.add), ("Update selected", self.update), ("Remove selected", self.remove)]:
            ttk.Button(edits, text=label, command=command).pack(side="left", padx=(0, 8))
        ttk.Label(frame, text="Save categories to keep the configuration, or Save & prepare folders… to review folder creation. No folders are created until confirmed in the preview.", wraplength=740).grid(row=8, column=0, columnspan=3, sticky="w", pady=(0, 12))
        actions = ttk.Frame(frame)
        actions.grid(row=9, column=0, columnspan=3, sticky="ew")
        ttk.Button(actions, text="Restore default categories", command=self.restore_defaults).pack(side="left")
        ttk.Button(actions, text="Cancel", command=self.window.destroy).pack(side="right")
        if on_prepare is not None:
            self.prepare_button = ttk.Button(actions, text="Save & prepare folders…", command=lambda: self.save(prepare=True))
            self.prepare_button.pack(side="right", padx=10)
        ttk.Button(actions, text="Save categories", command=self.save).pack(side="right", padx=10)
        self.render()
        self.window.grab_set()

    def render(self, selected=None):
        items = self.tree.get_children()
        if items:
            self.tree.delete(*items)
        for index, category in enumerate(self.categories):
            self.tree.insert("", "end", iid=str(index), values=(category.name, category.library_name, category.model_folder))
        if selected is not None and selected < len(self.categories):
            self.tree.selection_set(str(selected))
            self.tree.focus(str(selected))
            self.select()

    def selected_index(self):
        selection = self.tree.selection()
        return int(selection[0]) if selection else None

    def select(self, _=None):
        index = self.selected_index()
        if index is not None and index < len(self.categories):
            category = self.categories[index]
            self.name.set(category.name)
            self.library_name.set(category.library_name)
            self.model_folder.set(category.model_folder)

    def new(self):
        selection = self.tree.selection()
        if selection:
            self.tree.selection_remove(*selection)
        self.name.set("")
        self.library_name.set("")
        self.model_folder.set("")

    def edited_category(self):
        name = self.name.get()
        return LibraryCategory(name, self.library_name.get() or name, self.model_folder.get() or name).validated()

    def apply_edit(self, replacing=False):
        try:
            category = self.edited_category()
            index = self.selected_index() if replacing else len(self.categories)
            if index is None:
                raise ValueError("Select a category to update.")
            candidate = list(self.categories)
            if replacing:
                candidate[index] = category
            else:
                candidate.append(category)
            validate_categories(candidate)
            self.categories = candidate
            self.render(index)
        except ValueError as exc:
            messagebox.showerror("Invalid category", str(exc), parent=self.window)

    def add(self):
        self.apply_edit()

    def update(self):
        self.apply_edit(replacing=True)

    def remove(self):
        index = self.selected_index()
        if index is not None:
            self.categories.pop(index)
            self.render()
            self.new()

    def restore_defaults(self):
        self.categories = list(DEFAULT_CATEGORIES)
        self.render()
        self.new()

    def save(self, prepare=False):
        try:
            if any((self.name.get(), self.library_name.get(), self.model_folder.get())):
                index = self.selected_index()
                if index is None or self.edited_category() != self.categories[index]:
                    raise ValueError("Use Add category or Update selected to apply the edited fields before saving.")
            categories = validate_categories(self.categories)
            self.on_save(replace(self.settings, categories=categories).validated(self.workspace))
        except (OSError, ValueError) as exc:
            messagebox.showerror("Categories not saved", str(exc), parent=self.window)
            return
        self.window.destroy()
        if prepare and self.on_prepare:
            return self.on_prepare()


class FolderPreviewDialog:
    def __init__(self, parent, plan, on_create):
        self.plan, self.on_create = plan, on_create
        self.window = tk.Toplevel(parent)
        self.window.title("Library Loader · Prepare library folders")
        self.window.transient(parent)
        self.window.geometry("900x560")
        self.window.minsize(680, 420)
        frame = ttk.Frame(self.window, padding=16)
        frame.pack(fill="both", expand=True)
        frame.rowconfigure(2, weight=1)
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text="Review library folders", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text="Only the listed folders will be created or reused. Existing files are preserved.").grid(row=1, column=0, sticky="w", pady=10)
        text_frame = ttk.Frame(frame)
        text_frame.grid(row=2, column=0, sticky="nsew")
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)
        text = tk.Text(text_frame, wrap="word", font=("Consolas", 9))
        text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(text_frame, orient="vertical", command=text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        text.configure(yscrollcommand=scroll.set)
        text.insert("end", "\n".join(plan.info + ["WARNING: " + warning for warning in plan.warnings]))
        text.configure(state="disabled")
        self.ack = tk.BooleanVar(value=False)
        if plan.warnings:
            ttk.Checkbutton(frame, text="I have reviewed the warnings", variable=self.ack).grid(row=3, column=0, sticky="w", pady=10)
        actions = ttk.Frame(frame)
        actions.grid(row=4, column=0, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="Cancel", command=self.window.destroy).pack(side="right")
        self.create_button = ttk.Button(actions, text="Create library folders", command=self.create)
        self.create_button.pack(side="right", padx=10)
        self.ack.trace_add("write", lambda *_: self.update_button())
        self.update_button()
        self.window.grab_set()

    def update_button(self):
        self.create_button.configure(state="normal" if not self.plan.warnings or self.ack.get() else "disabled")

    def create(self):
        if self.plan.warnings and not self.ack.get():
            return
        try:
            self.on_create()
        except (OSError, ValueError) as exc:
            messagebox.showerror("Folders not prepared", str(exc), parent=self.window)
            return
        self.window.destroy()

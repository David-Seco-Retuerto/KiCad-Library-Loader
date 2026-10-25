"""Main-window presentation; import planning and safety remain in the application."""
import tkinter as tk
from tkinter import ttk
from app_version import VERSION


BG = "#f3f6fa"
INK = "#172b45"
MUTED = "#52657d"
ACCENT = "#2563eb"


def configure_style(root):
    style = ttk.Style(root)
    # A single ttk theme keeps cards and controls consistent across Windows dialogs.
    if "clam" in style.theme_names():
        style.theme_use("clam")
    root.configure(background=BG)
    style.configure(".", font=("Segoe UI", 10), foreground=INK, background=BG)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG)
    style.configure("Card.TFrame", background="white")
    style.configure("Card.TLabel", background="white")
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("CardMuted.TLabel", background="white", foreground=MUTED, font=("Segoe UI", 9))
    style.configure("Title.TLabel", font=("Segoe UI", 21, "bold"))
    style.configure("Section.TLabel", background="white", font=("Segoe UI", 12, "bold"))
    style.configure("Status.TLabel", foreground="#1d4ed8", background="#e7efff", padding=(12, 6))
    style.configure("TButton", padding=(10, 6), background="white", bordercolor="#a8b6c8", lightcolor="#a8b6c8", darkcolor="#a8b6c8", borderwidth=1, relief="raised")
    style.map("TButton", background=[("active", "#e7efff"), ("disabled", "#edf1f6")], foreground=[("disabled", "#7a8798")])
    style.configure("Primary.TButton", background=ACCENT, foreground="white", bordercolor=ACCENT, padding=(18, 8))
    style.map("Primary.TButton", background=[("disabled", "#dce4f0"), ("active", "#1d4ed8")], foreground=[("disabled", "#718096"), ("!disabled", "white")])
    style.configure("TMenubutton", padding=(10, 6), background="white")
    style.configure("TCombobox", padding=5, fieldbackground="white", arrowsize=14)
    style.map("TCombobox", fieldbackground=[("readonly", "white")], foreground=[("readonly", INK)])
    style.configure("TEntry", padding=5, fieldbackground="white")
    style.configure("Card.TRadiobutton", background="white", padding=(0, 3))
    style.map("Card.TRadiobutton", background=[("active", "white")])
    style.configure("Card.TCheckbutton", background="white")
    style.map("Card.TCheckbutton", background=[("active", "white")])
    style.configure("TNotebook", background="white", borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.configure("TNotebook.Tab", padding=(18, 8), background=BG)
    style.map("TNotebook.Tab", background=[("selected", "#e7efff")], foreground=[("selected", "#1d4ed8")])
    return style


def card(parent, title, subtitle=None):
    outer = ttk.Frame(parent, style="Card.TFrame", padding=16)
    ttk.Label(outer, text=title, style="Section.TLabel").pack(anchor="w")
    if subtitle:
        ttk.Label(outer, text=subtitle, style="CardMuted.TLabel", wraplength=365).pack(anchor="w", pady=(4, 10))
    content = ttk.Frame(outer, style="Card.TFrame")
    content.pack(fill="both", expand=True, pady=(10 if not subtitle else 0, 0))
    return outer, content


def build_main_window(app, drawing, providers, symbol_formats):
    root = app.root
    app.style = configure_style(root)
    root.title(f"KiCad Library Loader {VERSION}")
    width, height = min(1280, root.winfo_screenwidth() - 60), min(880, root.winfo_screenheight() - 100)
    root.geometry(f"{max(1000, width)}x{max(680, height)}")
    root.minsize(1000, 680)
    root.columnconfigure(0, weight=1)
    root.rowconfigure(1, weight=1)
    header = ttk.Frame(root, padding=(24, 18, 24, 14))
    header.grid(row=0, column=0, sticky="ew")
    header.columnconfigure(0, weight=1)
    ttk.Label(header, text="KiCad Library Loader", style="Title.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(header, text="Choose your assets. Review the plan. Build your library.", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
    tools = ttk.Frame(header)
    tools.grid(row=0, column=1, rowspan=2, sticky="e")
    app.tool_buttons = {}
    for label, command in (("Settings…", app.open_settings), ("Categories…", app.open_categories),
                           ("Check KiCad setup…", app.check_kicad_setup), ("Import history…", app.open_history)):
        button = ttk.Button(tools, text=label, command=command)
        button.pack(side="left", padx=(8, 0))
        app.tool_buttons[label] = button

    workspace = ttk.Frame(root, padding=(24, 0, 24, 0))
    workspace.grid(row=1, column=0, sticky="nsew")
    workspace.columnconfigure(0, minsize=430)
    workspace.columnconfigure(1, weight=1)
    workspace.rowconfigure(0, weight=1)
    app.form_canvas = tk.Canvas(workspace, background=BG, borderwidth=0, highlightthickness=0, width=414)
    app.form_canvas.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
    scrollbar = ttk.Scrollbar(workspace, orient="vertical", command=app.form_canvas.yview)
    scrollbar.grid(row=0, column=0, sticky="nse", padx=(0, 5))
    app.form_canvas.configure(yscrollcommand=scrollbar.set)
    app.form = ttk.Frame(app.form_canvas)
    window = app.form_canvas.create_window((0, 0), window=app.form, anchor="nw")
    app.form.bind("<Configure>", lambda _: app.form_canvas.configure(scrollregion=app.form_canvas.bbox("all")))
    app.form_canvas.bind("<Configure>", lambda event: app.form_canvas.itemconfigure(window, width=event.width))

    source_card, source = card(app.form, "01  Source", "Open a downloaded export or find a component online.")
    app.source_card = source_card
    source_card.pack(fill="x", pady=(0, 12))
    source.columnconfigure(0, weight=1)
    row = ttk.Frame(source, style="Card.TFrame")
    row.grid(row=0, column=0, sticky="ew")
    row.columnconfigure(0, weight=1)
    app.source_combo = ttk.Combobox(row, textvariable=app.source_choice, values=["Downloads", *providers], state="readonly", width=12)
    app.source_combo.grid(row=0, column=0, sticky="ew", padx=(0, 8))
    app.source_combo.bind("<<ComboboxSelected>>", lambda _: app.select_source_choice())
    ttk.Button(row, text="Refresh", command=app.refresh_action).grid(row=0, column=1)
    actions = ttk.Frame(source, style="Card.TFrame")
    actions.grid(row=1, column=0, sticky="ew", pady=(10, 0))
    actions.columnconfigure((0, 1), weight=1, uniform="source-actions")
    for index, (label, command) in enumerate((("Open ZIP…", app.open_zip), ("Search online…", app.open_search),
                                              ("Download LCSC…", app.open_lcsc_download), ("Use export folder…", app.use_export_folder))):
        ttk.Button(actions, text=label, command=command).grid(row=index // 2, column=index % 2, sticky="ew", padx=(0, 6) if index % 2 == 0 else (0, 0), pady=(0, 6))
    # Hide the wrapper itself too: an empty frame retains its last requested size.
    download_wrapper = ttk.Frame(source, style="Card.TFrame")
    download_wrapper.grid(row=2, column=0, sticky="ew")
    app.download_wrapper = download_wrapper
    app.download_frame = ttk.Frame(download_wrapper, style="Card.TFrame")
    app.download_frame.columnconfigure(0, weight=1)
    ttk.Label(app.download_frame, text="Downloaded ZIP", style="CardMuted.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(4, 4))
    app.download_combo = ttk.Combobox(app.download_frame, textvariable=app.download_zip, state="readonly", width=12)
    app.download_combo.grid(row=1, column=0, columnspan=3, sticky="ew")
    app.download_combo.bind("<<ComboboxSelected>>", lambda _: app.load_download())
    ttk.Button(app.download_frame, text="Load ZIP", command=app.load_download).grid(row=2, column=0, sticky="w", pady=6)
    ttk.Button(app.download_frame, text="Folder…", command=app.choose_downloads_folder).grid(row=2, column=2, sticky="e", pady=6)
    ttk.Checkbutton(app.download_frame, text="Auto-refresh", variable=app.watch_downloads, command=app.toggle_download_watch, style="Card.TCheckbutton").grid(row=3, column=0, sticky="w")
    ttk.Checkbutton(app.download_frame, text="Auto-load new ZIPs", variable=app.auto_load_zips, command=app.toggle_auto_zip, style="Card.TCheckbutton").grid(row=3, column=1, columnspan=2, sticky="e")
    app.download_status_label = ttk.Label(download_wrapper, textvariable=app.download_status, style="CardMuted.TLabel", wraplength=365)

    assets_card, assets = card(app.form, "02  Assets", "Select each asset independently; empty = skip.")
    assets_card.pack(fill="x", pady=(0, 12))
    assets.columnconfigure(1, weight=1)
    app.asset_displays, app.asset_choices, app.combos = {}, {}, {}
    for index, (label, var) in enumerate((("Symbol", app.symbol), ("Footprint", app.fp), ("STEP model", app.model))):
        ttk.Label(assets, text=label, style="CardMuted.TLabel").grid(row=index, column=0, sticky="w", padx=(0, 12), pady=8)
        display = tk.StringVar()
        app.asset_displays[label], app.asset_choices[label] = display, {}
        var.trace_add("write", lambda *_, label=label, var=var: app.sync_asset_display(label, var))
        combo = ttk.Combobox(assets, textvariable=display, state="readonly", width=12)
        combo.grid(row=index, column=1, sticky="ew", pady=8)
        combo.bind("<<ComboboxSelected>>", lambda _, label=label: app.select_asset(label))
        app.combos[label] = combo

    target_card, target = card(app.form, "03  Destination")
    target_card.pack(fill="x", pady=(0, 4))
    target.columnconfigure(0, weight=1)
    ttk.Label(target, text="Category", style="CardMuted.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 4))
    app.category_combo = ttk.Combobox(target, textvariable=app.category, values=[c.name for c in app.settings.categories], state="readonly", width=12)
    app.category_combo.grid(row=1, column=0, sticky="ew")
    ttk.Label(target, text="KiCad compatibility", style="CardMuted.TLabel").grid(row=2, column=0, sticky="w", pady=(10, 4))
    app.format_combo = ttk.Combobox(target, textvariable=app.symbol_format, values=list(symbol_formats.values()), state="readonly", width=12)
    app.format_combo.grid(row=3, column=0, sticky="ew")
    ttk.Label(target, text="Footprint / 3D naming", style="CardMuted.TLabel").grid(row=4, column=0, sticky="w", pady=(10, 4))
    naming = ttk.Frame(target, style="Card.TFrame")
    naming.grid(row=5, column=0, sticky="w")
    for value in ("Original", "Suggestion", "Custom"):
        ttk.Radiobutton(naming, text=value, variable=app.mode, value=value, style="Card.TRadiobutton").pack(side="left", padx=(0, 12))
    ttk.Label(target, text="Custom name", style="CardMuted.TLabel").grid(row=6, column=0, sticky="w", pady=(6, 4))
    app.entry = ttk.Entry(target, textvariable=app.custom, width=12)
    app.entry.grid(row=7, column=0, sticky="ew")
    ttk.Label(target, text="Output names", style="Card.TLabel").grid(row=8, column=0, sticky="w", pady=(14, 4))
    app.output_names = {}
    for index, label in enumerate(("Symbol", "Footprint", "STEP model")):
        ttk.Label(target, text=label + (" ID" if label == "Symbol" else " file"), style="CardMuted.TLabel").grid(row=9 + index * 2, column=0, sticky="w", pady=(4, 3))
        value = tk.StringVar()
        app.output_names[label] = value
        ttk.Entry(target, textvariable=value, state="readonly", width=12).grid(row=10 + index * 2, column=0, sticky="ew")
    ttk.Button(target, text="Show locations…", command=app.show_locations).grid(row=15, column=0, sticky="w", pady=(10, 0))

    def scroll_form(event):
        if app.form_canvas.bbox("all") and app.form.winfo_height() > app.form_canvas.winfo_height():
            app.form_canvas.yview_scroll(-int(event.delta / 120) if abs(event.delta) >= 120 else (-1 if event.delta > 0 else 1), "units")
        return "break"
    focus_navigation = {"keyboard": False}

    def keyboard_navigation(_):
        focus_navigation["keyboard"] = True

    def pointer_navigation(_):
        focus_navigation["keyboard"] = False

    def reveal_focus(event):
        widget = event.widget
        # Popup posting/unposting also sends FocusIn to ancestor frames. Only
        # reveal the actual control reached by Tab, never a mouse-opened combo.
        if not focus_navigation["keyboard"] or widget.focus_get() is not widget:
            return
        focus_navigation["keyboard"] = False
        top = widget.winfo_rooty() - app.form.winfo_rooty()
        viewport_top = app.form_canvas.canvasy(0)
        viewport_height = app.form_canvas.winfo_height()
        if top < viewport_top:
            app.form_canvas.yview_moveto(max(0, top - 12) / max(app.form.winfo_height(), 1))
        elif top + widget.winfo_height() > viewport_top + viewport_height:
            app.form_canvas.yview_moveto(max(0, top + widget.winfo_height() - viewport_height + 12) / max(app.form.winfo_height(), 1))

    def bind_scroll(widget):
        widget.bind("<MouseWheel>", scroll_form)
        widget.bind("<FocusIn>", reveal_focus, add="+")
        widget.bind("<KeyPress-Tab>", keyboard_navigation, add="+")
        widget.bind("<Shift-KeyPress-Tab>", keyboard_navigation, add="+")
        if root.tk.call("tk", "windowingsystem") == "x11":
            widget.bind("<ISO_Left_Tab>", keyboard_navigation, add="+")
        widget.bind("<ButtonPress>", pointer_navigation, add="+")
        for child_widget in widget.winfo_children():
            bind_scroll(child_widget)
    bind_scroll(app.form)
    app.form_canvas.bind("<MouseWheel>", scroll_form)

    right = ttk.Frame(workspace)
    right.grid(row=0, column=1, sticky="nsew")
    right.columnconfigure(0, weight=1)
    right.rowconfigure(0, weight=1)
    app.workspace_split = ttk.Panedwindow(right, orient="vertical")
    app.workspace_split.grid(row=0, column=0, sticky="nsew")
    preview_card, preview = card(app.workspace_split, "Previews", "Simplified 2D views. Use KiCad SVG for exact graphics." if app.cli else "Simplified 2D views. KiCad CLI was not found; exact SVG previews are unavailable.")
    # Preview captions can wrap across the wider right pane.
    preview_caption = preview_card.winfo_children()[1]
    preview_card.bind("<Configure>", lambda event: preview_caption.configure(wraplength=max(200, event.width - 32)))
    app.workspace_split.add(preview_card, weight=3)
    preview.columnconfigure(0, weight=1)
    preview.rowconfigure(1, weight=1)
    toolbar = ttk.Frame(preview, style="Card.TFrame")
    toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    toolbar.columnconfigure(0, weight=1)
    app.component_summary = tk.StringVar()
    component_caption = ttk.Label(toolbar, textvariable=app.component_summary, style="CardMuted.TLabel", wraplength=350)
    component_caption.grid(row=0, column=0, sticky="w")
    toolbar.bind("<Configure>", lambda event: component_caption.configure(wraplength=max(90, event.width - 190)))
    app.model_button = ttk.Button(toolbar, text="Preview STEP in 3D", command=app.open_model)
    app.model_button.grid(row=0, column=1, sticky="e", padx=(8, 0))
    previews = ttk.Frame(preview, style="Card.TFrame")
    previews.grid(row=1, column=0, sticky="nsew")
    previews.columnconfigure((0, 1), weight=1, uniform="drawings")
    previews.rowconfigure(0, weight=1)
    views = []
    for index, (kind, title) in enumerate((("symbol", "Symbol"), ("footprint", "Footprint"))):
        tab = ttk.Frame(previews, style="Card.TFrame")
        tab.grid(row=0, column=index, sticky="nsew", padx=(0, 6) if index == 0 else (6, 0))
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        ttk.Label(tab, text=title, style="Card.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        view = drawing(tab)
        view.grid(row=1, column=0, sticky="nsew")
        view.canvas.configure(width=160, height=220)
        preview_actions = ttk.Frame(tab, style="Card.TFrame")
        preview_actions.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(preview_actions, text="Expand…", command=lambda kind=kind: app.expand_preview(kind)).pack(side="left")
        button = ttk.Button(preview_actions, text=f"Open {kind} SVG in KiCad", command=lambda kind=kind: app.export_svg(kind))
        button.pack(side="right")
        views.append((view, button))
    (app.symbol_view, app.symbol_svg_button), (app.fp_view, app.fp_svg_button) = views
    app.symbol_svg_button.configure(text="KiCad SVG")
    app.fp_svg_button.configure(text="KiCad SVG")
    review_card = ttk.Frame(app.workspace_split, style="Card.TFrame", padding=16)
    app.workspace_split.add(review_card, weight=2)
    review_heading = ttk.Frame(review_card, style="Card.TFrame")
    review_heading.pack(fill="x")
    ttk.Label(review_heading, text="04  Review plan", style="Section.TLabel").pack(side="left")
    ttk.Button(review_heading, text="Review update…", command=app.review_update).pack(side="right")
    review = ttk.Frame(review_card, style="Card.TFrame")
    review.pack(fill="both", expand=True, pady=(8, 0))
    review.columnconfigure(0, weight=1)
    review.rowconfigure(1, weight=1)
    app.review_status = tk.StringVar(value="Select a component")
    review_caption = ttk.Label(review, textvariable=app.review_status, style="CardMuted.TLabel", wraplength=550)
    review_caption.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
    review.bind("<Configure>", lambda event: review_caption.configure(wraplength=max(200, event.width)))
    app.log = tk.Text(review, height=6, width=30, wrap="word", state="disabled", font=("Consolas", 10),
                      background="#f8faff", foreground="#000000", relief="flat", borderwidth=0, padx=10, pady=10, highlightthickness=0)
    app.log.grid(row=1, column=0, sticky="nsew")
    report_scroll = ttk.Scrollbar(review, command=app.log.yview)
    report_scroll.grid(row=1, column=1, sticky="ns")
    app.log.configure(yscrollcommand=report_scroll.set)
    for tag, color in (("info", "#000000"), ("success", "#166534"), ("warning", "#b45309"), ("error", "#b91c1c")):
        app.log.tag_configure(tag, foreground=color)

    footer = ttk.Frame(root, padding=(24, 14, 24, 18))
    footer.grid(row=2, column=0, sticky="ew")
    footer.columnconfigure(0, weight=1)
    app.workflow_status = tk.StringVar(value="Select a component")
    ttk.Label(footer, textvariable=app.workflow_status, style="Status.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
    app.review_checkbox = ttk.Checkbutton(footer, text="I have reviewed the warnings and associations", variable=app.ack)
    app.review_checkbox.grid(row=1, column=0, sticky="w")
    controls = ttk.Frame(footer)
    controls.grid(row=0, column=1, rowspan=2, sticky="e")
    app.validate_button = ttk.Button(controls, text="Validate / review plan", command=app.validate)
    app.validate_button.pack(side="left", padx=(0, 10))
    app.import_button = ttk.Button(controls, text="Import component", command=app.import_component, state="disabled", style="Primary.TButton")
    app.import_button.pack(side="left")
    root.bind("<F5>", lambda _: app.refresh_action())

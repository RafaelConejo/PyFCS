import os
import copy
import platform
import tkinter as tk
from tkinter import ttk, filedialog

import numpy as np
from PIL import Image, ImageTk, ImageOps

import Source.interface.modules.UtilsTools as UtilsTools


class ImageInspectionManager:
    """
    Persistent image/FCS inspector used by PyFCS Image Inspection.

    Design goals
    ------------
    - Keep Image Inspection conceptually separate from Color Evaluation.
    - Inspect many pixels without closing/reopening the window.
    - Navigate through workspace images and temporary external images.
    - Keep membership degrees independent from comparison metric/threshold.
    - Preserve the most-similar fuzzy prototype while allowing another
        membership row to be selected for detailed comparison.
    - Maintain independent zoom/pan/sample state per image.
    """

    BG = "#f5f6f8"
    CARD = "#ffffff"
    PANEL = "#fbfbfc"
    SOFT = "#f1f3f6"
    BORDER = "#d9dde3"
    TEXT = "#1f2937"
    MUTED = "#6b7280"
    BLUE = "#1f4e8c"
    BLUE_SOFT = "#e8f0fe"
    GREEN = "#2d6a2d"
    GREEN_BG = "#f3faf3"
    YELLOW = "#9a6500"
    YELLOW_BG = "#fff7e6"
    RED = "#8a1f1f"
    RED_BG = "#f8f2f2"

    FONT = ("Segoe UI", 9)
    FONT_BOLD = ("Segoe UI", 9, "bold")
    FONT_SMALL = ("Segoe UI", 8)
    FONT_SMALL_BOLD = ("Segoe UI", 8, "bold")
    FONT_TITLE = ("Segoe UI", 15, "bold")
    FONT_SECTION = ("Segoe UI", 10, "bold")

    def __init__(self, app, initial_info):
        self.app = app
        self.root = app.root
        self.manager = app.color_manager

        self.win = tk.Toplevel(self.root)
        self.win.title("Image Inspection")
        self.win.configure(bg=self.BG)
        self.win.minsize(1120, 700)
        self.win.protocol("WM_DELETE_WINDOW", self.close)

        # Inspection remains open while the main application is in use.
        try:
            self.win.transient(self.root)
        except Exception:
            pass

        self._maximize_window()

        self._sources = {}
        self._source_order = []
        self._display_to_key = {}
        self._key_to_display = {}
        self._external_counter = 0
        self.current_source_key = None

        # View/sample state per image.
        self._view_state = {}       # key -> {zoom, cx, cy}
        self._last_sample = {}      # key -> sample dict
        self._current_sample = None
        self._selected_proto_label = None
        self._membership_rows = {}
        # Reuse these row widgets as the sampled pixel changes in Live mode.
        self._membership_controls = {}
        self._pinned_samples = []

        self._canvas_photo = None
        self._render_transform = None
        self._pan_state = None
        self._live_after_id = None
        self._live_pending_xy = None
        self._tooltip_enabled = False
        self._details_expanded = False
        self._roi_drag_start = None
        self._roi_drag_current = None
        self._inspect_drag_start_canvas = None

        self._init_threshold_settings()
        self._create_variables()
        self._build_ui()
        self._load_workspace_sources()
        self._select_initial_source(initial_info)

        self.win.bind("<Escape>", lambda _e: self.close())
        self.win.after(50, self._render_image)
        self.win.focus_set()

    # Window / Basic State
    def _maximize_window(self):
        try:
            if platform.system() == "Windows":
                self.win.state("zoomed")
                return
        except Exception:
            pass

        try:
            self.win.update_idletasks()
            sw = self.win.winfo_screenwidth()
            sh = self.win.winfo_screenheight()
            self.win.geometry(f"{sw}x{sh}+0+0")
        except Exception:
            self.win.geometry("1400x850")

    def close(self):
        if self._live_after_id is not None:
            try:
                self.win.after_cancel(self._live_after_id)
            except Exception:
                pass
            self._live_after_id = None

        try:
            if self.win.winfo_exists():
                self.win.destroy()
        except Exception:
            pass

        try:
            self.app._image_inspection_controller = None
            self.app._image_inspection_window = None
        except Exception:
            pass

    def _init_threshold_settings(self):
        current = getattr(self.app, "threshold_settings", None)
        self.app.threshold_settings = self.manager.normalize_threshold_settings(current)

    def _create_variables(self):
        s = self.app.threshold_settings
        preset_map, custom_map = self.manager.get_threshold_display_maps()

        self.source_var = tk.StringVar(value="")
        self.inspection_mode_var = tk.StringVar(value="inspect")
        self.inspection_mode_display_var = tk.StringVar(value="Inspect")
        self.inspection_help_var = tk.StringVar(
            value="Click: pixel · Drag: ROI · Right-drag: pan · Wheel: zoom"
        )
        self.zoom_var = tk.StringVar(value="Fit")

        self.sample_title_var = tk.StringVar(value="No sample selected")
        self.sample_kind_var = tk.StringVar(value="")
        self.sample_coord_var = tk.StringVar(value="Click a pixel in the image")
        self.sample_filters_var = tk.StringVar(value="")
        self.sample_lab_var = tk.StringVar(value="LAB: —")
        self.sample_rgb_var = tk.StringVar(value="RGB: —")
        self.sample_hex_var = tk.StringVar(value="HEX: —")

        # ROI filters do not alter single-pixel or Live measurements.
        self.filter_l_min_enabled = tk.BooleanVar(value=False)
        self.filter_l_max_enabled = tk.BooleanVar(value=False)
        self.filter_a_min_enabled = tk.BooleanVar(value=False)
        self.filter_a_max_enabled = tk.BooleanVar(value=False)
        self.filter_b_min_enabled = tk.BooleanVar(value=False)
        self.filter_b_max_enabled = tk.BooleanVar(value=False)

        self.filter_l_min_var = tk.StringVar(value="0.0")
        self.filter_l_max_var = tk.StringVar(value="100.0")
        self.filter_a_min_var = tk.StringVar(value="-128.0")
        self.filter_a_max_var = tk.StringVar(value="128.0")
        self.filter_b_min_var = tk.StringVar(value="-128.0")
        self.filter_b_max_var = tk.StringVar(value="128.0")

        self.winner_summary_var = tk.StringVar(value="Close Prototype: —")
        self.proto_title_var = tk.StringVar(value="Close Prototype")
        self.proto_name_var = tk.StringVar(value="—")
        self.proto_lab_var = tk.StringVar(value="LAB: —")
        self.proto_rgb_var = tk.StringVar(value="RGB: —")
        self.proto_hex_var = tk.StringVar(value="HEX: —")

        self.comparison_value_var = tk.StringVar(value="Select a sample to compare")
        self.comparison_status_var = tk.StringVar(value="")
        self.details_button_var = tk.StringVar(value="Show detailed comparison ▾")
        self.details_text_var = tk.StringVar(value="")

        self.metric_family_var = tk.StringVar(value=s.get("metric_family", "Perceptual ΔE"))
        self.metric_var = tk.StringVar(value=s.get("metric", "CIEDE2000"))
        self.threshold_mode_var = tk.StringVar(value=s.get("mode", "default"))
        self.threshold_preset_var = tk.StringVar(
            value=preset_map.get(s.get("preset", "pt_at"), "Perceptibility + Acceptability")
        )
        self.threshold_custom_type_var = tk.StringVar(
            value=custom_map.get(s.get("custom_type", "single"), "Single threshold")
        )
        self.threshold_single_var = tk.StringVar(value="" if s.get("single") is None else str(s.get("single")))
        self.threshold_lower_var = tk.StringVar(value="" if s.get("lower") is None else str(s.get("lower")))
        self.threshold_upper_var = tk.StringVar(value="" if s.get("upper") is None else str(s.get("upper")))
        self.metric_help_var = tk.StringVar(value=self.manager.get_metric_description(self.metric_var.get()))

    # UI Building
    def _card(self, parent, title=None, padx=10, pady=10):
        if title:
            return tk.LabelFrame(
                parent,
                text=f" {title} ",
                font=self.FONT_SECTION,
                bg=self.CARD,
                fg=self.TEXT,
                bd=1,
                relief="solid",
                highlightthickness=0,
                padx=padx,
                pady=pady,
                labelanchor="nw",
            )
        return tk.Frame(parent, bg=self.CARD, bd=1, relief="solid")

    def _build_ui(self):
        outer = tk.Frame(self.win, bg=self.BG)
        outer.pack(fill="both", expand=True, padx=14, pady=12)

        self._build_header(outer)

        paned = tk.PanedWindow(
            outer,
            orient="horizontal",
            bg=self.BG,
            bd=0,
            sashwidth=7,
            sashrelief="flat",
        )
        paned.pack(fill="both", expand=True, pady=(10, 0))

        left = tk.Frame(paned, bg=self.BG)
        right = tk.Frame(paned, bg=self.BG)
        paned.add(left, stretch="always", minsize=700)
        paned.add(right, stretch="always", minsize=360)

        self._build_left_image_panel(left)
        self._build_right_scroll_panel(right)

        def _initial_sash():
            try:
                total = paned.winfo_width()
                if total > 1:
                    paned.sash_place(0, int(total * 0.70), 1)
            except Exception:
                pass

        self.win.after(150, _initial_sash)

    def _build_header(self, parent):
        """Build one compact top bar: title, image navigation and color-space name."""
        header = tk.Frame(parent, bg=self.CARD, bd=1, relief="solid")
        header.pack(fill="x")

        inner = tk.Frame(header, bg=self.CARD)
        inner.pack(fill="x", padx=12, pady=7)

        tk.Label(
            inner,
            text="Image Inspection",
            font=("Segoe UI", 13, "bold"),
            bg=self.CARD,
            fg=self.TEXT,
            anchor="w",
        ).pack(side="left", padx=(2, 18))

        tk.Label(
            inner,
            text="Image:",
            font=self.FONT_BOLD,
            bg=self.CARD,
            fg=self.TEXT,
        ).pack(side="left")

        tk.Button(
            inner,
            text="◀",
            width=3,
            command=lambda: self._step_source(-1),
            font=self.FONT_BOLD,
            cursor="hand2",
        ).pack(side="left", padx=(8, 3))

        self.source_combo = ttk.Combobox(
            inner,
            textvariable=self.source_var,
            state="readonly",
            width=34,
        )
        self.source_combo.pack(side="left", padx=3)
        self.source_combo.bind("<<ComboboxSelected>>", self._on_source_combo)

        tk.Button(
            inner,
            text="▶",
            width=3,
            command=lambda: self._step_source(1),
            font=self.FONT_BOLD,
            cursor="hand2",
        ).pack(side="left", padx=(3, 10))

        tk.Button(
            inner,
            text="+ Open Image...",
            command=self._open_external_image,
            font=self.FONT_BOLD,
            bg=self.BLUE_SOFT,
            fg=self.BLUE,
            activebackground="#d7e5fb",
            activeforeground=self.BLUE,
            relief="solid",
            bd=1,
            padx=8,
            pady=3,
            cursor="hand2",
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            inner,
            text="Refresh",
            command=self._refresh_workspace_sources,
            font=self.FONT,
            relief="solid",
            bd=1,
            padx=7,
            pady=3,
            cursor="hand2",
        ).pack(side="left")

        color_space_name = "Loaded color space"
        try:
            value = self.app.file_name_entry.get().strip()
            if value:
                color_space_name = value
        except Exception:
            pass

        tk.Label(
            inner,
            text=f"Color Space: {color_space_name}",
            font=self.FONT_BOLD,
            bg=self.CARD,
            fg=self.BLUE,
        ).pack(side="right", padx=(12, 2))

    def _build_image_navigation(self, parent):
        """Kept for backwards compatibility; navigation now lives in the header."""
        return None

    def _build_left_image_panel(self, parent):
        image_card = self._card(parent, "Image")
        image_card.pack(fill="both", expand=True)

        canvas_holder = tk.Frame(image_card, bg=self.PANEL, bd=1, relief="solid")
        canvas_holder.pack(fill="both", expand=True)

        self.image_canvas = tk.Canvas(
            canvas_holder,
            bg="#eef1f4",
            highlightthickness=0,
            bd=0,
            cursor="crosshair",
        )
        self.image_canvas.pack(fill="both", expand=True)

        self.image_canvas.bind("<Configure>", lambda _e: self._render_image())
        self.image_canvas.bind("<ButtonPress-1>", self._on_canvas_left_press)
        self.image_canvas.bind("<B1-Motion>", self._on_canvas_left_drag)
        self.image_canvas.bind("<ButtonRelease-1>", self._on_canvas_left_release)
        self.image_canvas.bind("<Motion>", self._on_canvas_motion)
        self.image_canvas.bind("<Button-3>", self._start_pan)
        self.image_canvas.bind("<B3-Motion>", self._pan_motion)
        self.image_canvas.bind("<ButtonRelease-3>", self._end_pan)
        self.image_canvas.bind("<Button-2>", self._start_pan)
        self.image_canvas.bind("<B2-Motion>", self._pan_motion)
        self.image_canvas.bind("<ButtonRelease-2>", self._end_pan)
        self.image_canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.image_canvas.bind("<Button-4>", lambda e: self._zoom_at_event(e, 1.12))
        self.image_canvas.bind("<Button-5>", lambda e: self._zoom_at_event(e, 1 / 1.12))

        controls = tk.Frame(image_card, bg=self.CARD)
        controls.pack(fill="x", pady=(8, 0))

        # Left group: inspection mode + pin action.
        left_controls = tk.Frame(controls, bg=self.CARD)
        left_controls.pack(side="left")

        tk.Label(
            left_controls,
            text="Inspection:",
            font=self.FONT_BOLD,
            bg=self.CARD,
            fg=self.TEXT,
        ).pack(side="left")

        self.inspection_mode_combo = ttk.Combobox(
            left_controls,
            textvariable=self.inspection_mode_display_var,
            values=("Inspect", "Live"),
            state="readonly",
            width=8,
        )
        self.inspection_mode_combo.pack(side="left", padx=(7, 6))
        self.inspection_mode_combo.bind("<<ComboboxSelected>>", self._on_inspection_mode_changed)

        self.filters_button = tk.Button(
            left_controls,
            text="Filters...",
            command=self._open_lab_filters,
            font=self.FONT,
            bg="#f8fafc",
            fg=self.TEXT,
            activebackground="#eef2f7",
            activeforeground=self.TEXT,
            relief="solid",
            bd=1,
            padx=9,
            pady=3,
            cursor="hand2",
        )
        self.filters_button.pack(side="left", padx=(0, 6))

        tk.Button(
            left_controls,
            text="☆ Pin Sample",
            command=self._pin_current_sample,
            font=self.FONT_BOLD,
            relief="solid",
            bd=1,
            padx=9,
            pady=3,
            cursor="hand2",
        ).pack(side="left", padx=(0, 10))

        right_controls = tk.Frame(controls, bg=self.CARD)
        right_controls.pack(side="right")

        tk.Button(
            right_controls,
            text="Fit",
            command=self._reset_view,
            font=self.FONT,
            relief="solid",
            bd=1,
            padx=8,
            pady=3,
            cursor="hand2",
        ).pack(side="left", padx=(8, 10))

        tk.Label(
            right_controls,
            text="Zoom:",
            font=self.FONT_SMALL_BOLD,
            bg=self.CARD,
            fg=self.MUTED,
        ).pack(side="left")

        tk.Label(
            right_controls,
            textvariable=self.zoom_var,
            font=self.FONT_SMALL_BOLD,
            bg=self.CARD,
            fg=self.TEXT,
            width=7,
            anchor="w",
        ).pack(side="left", padx=(4, 0))

        tk.Label(
            controls,
            textvariable=self.inspection_help_var,
            font=self.FONT_SMALL,
            bg=self.CARD,
            fg=self.MUTED,
            anchor="center",
            justify="center",
        ).pack(side="left", fill="x", expand=True, padx=6)

        self._build_pinned_samples_panel(image_card)

    def _build_pinned_samples_panel(self, parent):
        pins = self._card(parent, "Pinned Samples", padx=8, pady=7)
        pins.pack(fill="x", pady=(8, 0))

        table_row = tk.Frame(pins, bg=self.CARD)
        table_row.pack(fill="x")

        self.pin_tree = ttk.Treeview(
            table_row,
            columns=("image", "position", "prototype", "membership"),
            show="headings",
            height=3,
        )
        self.pin_tree.heading("image", text="Image")
        self.pin_tree.heading("position", text="Position")
        self.pin_tree.heading("prototype", text="Close Prototype")
        self.pin_tree.heading("membership", text="μ")
        self.pin_tree.column("image", width=190, anchor="w")
        self.pin_tree.column("position", width=130, anchor="center")
        self.pin_tree.column("prototype", width=150, anchor="w")
        self.pin_tree.column("membership", width=75, anchor="center")
        self.pin_tree.pack(side="left", fill="x", expand=True)
        self.pin_tree.bind("<Double-1>", lambda _e: self._restore_selected_pin())

        pin_scroll = ttk.Scrollbar(table_row, orient="vertical", command=self.pin_tree.yview)
        pin_scroll.pack(side="right", fill="y")
        self.pin_tree.configure(yscrollcommand=pin_scroll.set)

        buttons = tk.Frame(pins, bg=self.CARD)
        buttons.pack(fill="x", pady=(6, 0))

        tk.Button(buttons, text="Restore", command=self._restore_selected_pin, font=self.FONT_SMALL).pack(side="left")
        tk.Button(buttons, text="Remove", command=self._remove_selected_pin, font=self.FONT_SMALL).pack(side="left", padx=5)
        tk.Button(buttons, text="Clear", command=self._clear_pins, font=self.FONT_SMALL).pack(side="left")

    def _build_right_scroll_panel(self, parent):
        outer = tk.Frame(parent, bg=self.BG)
        outer.pack(fill="both", expand=True, padx=(8, 0))

        self.right_canvas = tk.Canvas(outer, bg=self.BG, highlightthickness=0, bd=0)
        right_scroll = ttk.Scrollbar(outer, orient="vertical", command=self.right_canvas.yview)
        self.right_canvas.configure(yscrollcommand=right_scroll.set)

        right_scroll.pack(side="right", fill="y")
        self.right_canvas.pack(side="left", fill="both", expand=True)

        self.right_inner = tk.Frame(self.right_canvas, bg=self.BG)
        self.right_window_id = self.right_canvas.create_window((0, 0), window=self.right_inner, anchor="nw")

        self.right_inner.bind(
            "<Configure>",
            lambda _e: self.right_canvas.configure(scrollregion=self.right_canvas.bbox("all"))
        )
        self.right_canvas.bind(
            "<Configure>",
            lambda e: self.right_canvas.itemconfigure(self.right_window_id, width=max(1, e.width - 4))
        )

        self._build_sample_card(self.right_inner)
        self._build_membership_card(self.right_inner)
        self._build_comparison_settings_card(self.right_inner)
        self._build_prototype_card(self.right_inner)

    def _build_sample_card(self, parent):
        card = self._card(parent, "Selected Sample", padx=9, pady=7)
        card.pack(fill="x", pady=(0, 8))

        row = tk.Frame(card, bg=self.CARD)
        row.pack(fill="x")

        # Reserve space for ROI metadata without displacing the color values.
        row.columnconfigure(1, weight=1)
        row.columnconfigure(2, weight=0, minsize=150)

        self.sample_swatch = tk.Canvas(
            row,
            width=58,
            height=58,
            bg=self.CARD,
            highlightthickness=0,
        )
        self.sample_swatch.grid(row=0, column=0, sticky="nw", padx=(0, 10))
        self.sample_swatch_rect = self.sample_swatch.create_rectangle(
            4,
            4,
            54,
            54,
            fill="#d9dde3",
            outline="#707070",
            width=1,
        )

        sample_info = tk.Frame(row, bg=self.CARD)
        sample_info.grid(row=0, column=1, sticky="nsew", padx=(0, 8))

        tk.Label(
            sample_info,
            textvariable=self.sample_title_var,
            font=self.FONT_BOLD,
            bg=self.CARD,
            fg=self.TEXT,
            anchor="w",
        ).pack(fill="x")

        tk.Label(
            sample_info,
            textvariable=self.sample_kind_var,
            font=self.FONT_SMALL,
            bg=self.CARD,
            fg=self.MUTED,
            anchor="w",
        ).pack(fill="x", pady=(2, 0))

        self.sample_coord_label = tk.Label(
            sample_info,
            textvariable=self.sample_coord_var,
            font=self.FONT_SMALL,
            bg=self.CARD,
            fg=self.MUTED,
            anchor="w",
            justify="left",
            wraplength=185,
        )
        self.sample_coord_label.pack(fill="x", pady=(3, 0))

        self.sample_filters_label = tk.Label(
            sample_info,
            textvariable=self.sample_filters_var,
            font=self.FONT_SMALL,
            bg=self.CARD,
            fg=self.MUTED,
            anchor="w",
            justify="left",
            wraplength=185,
        )

        values = tk.Frame(row, bg=self.CARD)
        values.grid(row=0, column=2, sticky="ne")

        tk.Label(
            values,
            textvariable=self.sample_lab_var,
            font=self.FONT_SMALL,
            bg=self.CARD,
            fg=self.TEXT,
            anchor="e",
            justify="right",
        ).pack(anchor="e")

        tk.Label(
            values,
            textvariable=self.sample_rgb_var,
            font=self.FONT_SMALL,
            bg=self.CARD,
            fg=self.TEXT,
            anchor="e",
            justify="right",
        ).pack(anchor="e", pady=(2, 0))

        tk.Label(
            values,
            textvariable=self.sample_hex_var,
            font=self.FONT_SMALL,
            bg=self.CARD,
            fg=self.TEXT,
            anchor="e",
            justify="right",
        ).pack(anchor="e", pady=(2, 0))

    def _build_comparison_settings_card(self, parent):
        card = self._card(parent, "Comparison Settings")
        card.pack(fill="x", pady=(0, 8))

        grid = tk.Frame(card, bg=self.CARD)
        grid.pack(fill="x")
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        tk.Label(grid, text="Metric family", font=self.FONT_SMALL_BOLD, bg=self.CARD, fg=self.TEXT).grid(row=0, column=0, sticky="w")
        tk.Label(grid, text="Metric", font=self.FONT_SMALL_BOLD, bg=self.CARD, fg=self.TEXT).grid(row=0, column=1, sticky="w", padx=(8, 0))

        self.metric_family_combo = ttk.Combobox(
            grid,
            textvariable=self.metric_family_var,
            values=self.manager.get_metric_families(),
            state="readonly",
        )
        self.metric_family_combo.grid(row=1, column=0, sticky="ew", pady=(3, 6))

        self.metric_combo = ttk.Combobox(
            grid,
            textvariable=self.metric_var,
            values=self.manager.get_metrics_for_family(self.metric_family_var.get()),
            state="readonly",
        )
        self.metric_combo.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(3, 6))

        tk.Label(
            grid,
            textvariable=self.metric_help_var,
            font=("Segoe UI", 8, "italic"),
            bg=self.CARD,
            fg=self.MUTED,
            justify="left",
            anchor="w",
            wraplength=420,
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        sep = tk.Frame(card, bg=self.BORDER, height=1)
        sep.pack(fill="x", pady=(0, 8))

        threshold_top = tk.Frame(card, bg=self.CARD)
        threshold_top.pack(fill="x")

        tk.Label(threshold_top, text="Threshold type", font=self.FONT_SMALL_BOLD, bg=self.CARD, fg=self.TEXT).pack(side="left")
        self.threshold_mode_combo = ttk.Combobox(
            threshold_top,
            textvariable=self.threshold_mode_var,
            values=["default", "custom"],
            state="readonly",
            width=13,
        )
        self.threshold_mode_combo.pack(side="right")

        self.threshold_dynamic = tk.Frame(card, bg=self.CARD)
        self.threshold_dynamic.pack(fill="x", pady=(7, 0))
        self._rebuild_threshold_dynamic_controls()

        self.metric_family_combo.bind("<<ComboboxSelected>>", self._on_metric_family_changed)
        self.metric_combo.bind("<<ComboboxSelected>>", lambda _e: self._threshold_changed())
        self.threshold_mode_combo.bind("<<ComboboxSelected>>", lambda _e: self._threshold_mode_changed())

    def _build_membership_card(self, parent):
        card = self._card(parent, "Membership Degree")
        card.pack(fill="x", pady=(0, 8))

        tk.Label(
            card,
            textvariable=self.winner_summary_var,
            bg=self.CARD,
            fg=self.BLUE,
            font=self.FONT_BOLD,
            anchor="w",
        ).pack(fill="x", pady=(0, 6))

        holder = tk.Frame(card, bg=self.CARD, height=115)
        holder.pack(fill="x")
        holder.pack_propagate(False)

        self.membership_canvas = tk.Canvas(holder, bg=self.CARD, highlightthickness=0, bd=0)
        scroll = ttk.Scrollbar(holder, orient="vertical", command=self.membership_canvas.yview)
        self.membership_canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.membership_canvas.pack(side="left", fill="both", expand=True)

        self.membership_inner = tk.Frame(self.membership_canvas, bg=self.CARD)
        self.membership_window_id = self.membership_canvas.create_window((0, 0), window=self.membership_inner, anchor="nw")
        self.membership_inner.bind(
            "<Configure>",
            lambda _e: self.membership_canvas.configure(scrollregion=self.membership_canvas.bbox("all"))
        )
        self.membership_canvas.bind(
            "<Configure>",
            lambda e: self.membership_canvas.itemconfigure(self.membership_window_id, width=max(1, e.width - 3))
        )

    def _build_prototype_card(self, parent):
        self.prototype_card = self._card(parent, "Prototype Details")
        self.prototype_card.pack(fill="x", pady=(0, 8))

        title_row = tk.Frame(self.prototype_card, bg=self.CARD)
        title_row.pack(fill="x")

        title_left = tk.Frame(title_row, bg=self.CARD)
        title_left.pack(side="left", fill="x", expand=True)

        tk.Label(
            title_left,
            textvariable=self.proto_title_var,
            bg=self.CARD,
            fg=self.TEXT,
            font=self.FONT_BOLD,
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            title_left,
            textvariable=self.proto_name_var,
            bg=self.CARD,
            fg=self.BLUE,
            font=("Segoe UI", 12, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(2, 0))

        self.use_winner_button = tk.Button(
            title_row,
            text="Use close prototype",
            command=self._select_winner_prototype,
            font=self.FONT_SMALL,
            relief="solid",
            bd=1,
            cursor="hand2",
        )

        body = tk.Frame(self.prototype_card, bg=self.CARD)
        body.pack(fill="x", pady=(7, 0))

        self.proto_swatch = tk.Canvas(body, width=54, height=54, bg=self.CARD, highlightthickness=0)
        self.proto_swatch.pack(side="left", padx=(0, 10), anchor="n")
        self.proto_swatch_rect = self.proto_swatch.create_rectangle(4, 4, 50, 50, fill="#d9dde3", outline="#707070")

        values = tk.Frame(body, bg=self.CARD)
        values.pack(side="left", fill="x", expand=True)
        tk.Label(values, textvariable=self.proto_lab_var, bg=self.CARD, fg=self.TEXT, font=self.FONT, anchor="w").pack(fill="x")
        tk.Label(values, textvariable=self.proto_rgb_var, bg=self.CARD, fg=self.TEXT, font=self.FONT, anchor="w").pack(fill="x")
        tk.Label(values, textvariable=self.proto_hex_var, bg=self.CARD, fg=self.TEXT, font=self.FONT, anchor="w").pack(fill="x")

        self.result_card = tk.Frame(
            self.prototype_card,
            bg=self.SOFT,
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightbackground=self.BORDER,
        )
        self.result_card.pack(fill="x", pady=(10, 0))

        self.result_header = tk.Frame(self.result_card, bg=self.SOFT)
        self.result_header.pack(fill="x")
        self.result_dot = tk.Canvas(self.result_header, width=18, height=18, bg=self.SOFT, highlightthickness=0, bd=0)
        self.result_dot.pack(side="left", padx=(9, 5), pady=7)
        self.result_dot_oval = self.result_dot.create_oval(3, 3, 15, 15, fill="#9ca3af", outline="#9ca3af")

        tk.Label(
            self.result_header,
            textvariable=self.comparison_status_var,
            bg=self.SOFT,
            fg=self.TEXT,
            font=self.FONT_BOLD,
            anchor="w",
        ).pack(side="left", fill="x", expand=True, padx=(0, 8), pady=7)

        self.result_body = tk.Frame(self.result_card, bg=self.SOFT)
        self.result_body.pack(fill="x", padx=12, pady=(8, 9))
        self.result_value_label = tk.Label(
            self.result_body,
            textvariable=self.comparison_value_var,
            bg=self.SOFT,
            fg=self.TEXT,
            font=("Segoe UI", 10, "bold"),
            anchor="w",
            justify="left",
        )
        self.result_value_label.pack(fill="x")

        self.details_button = tk.Button(
            self.prototype_card,
            textvariable=self.details_button_var,
            command=self._toggle_details,
            font=self.FONT_SMALL_BOLD,
            bg=self.CARD,
            fg=self.BLUE,
            activebackground=self.CARD,
            activeforeground=self.BLUE,
            relief="flat",
            bd=0,
            cursor="hand2",
        )
        self.details_button.pack(anchor="w", pady=(7, 0))

        self.details_frame = tk.Frame(self.prototype_card, bg="#fafafa", bd=1, relief="solid")
        self.details_label = tk.Label(
            self.details_frame,
            textvariable=self.details_text_var,
            bg="#fafafa",
            fg=self.TEXT,
            font=("Consolas", 8),
            anchor="w",
            justify="left",
            wraplength=430,
        )
        self.details_label.pack(fill="x", padx=10, pady=9)

    # Sources / Navigation
    def _load_workspace_sources(self):
        load_names = getattr(self.app, "load_images_names", {}) or {}
        originals = getattr(self.app, "pil_images_original", {}) or {}
        active_workspace_keys = {f"workspace:{window_id}" for window_id in load_names}

        # Discard closed workspace sources, but keep images opened locally.
        stale_keys = [
            key for key in self._source_order
            if key.startswith("workspace:") and key not in active_workspace_keys
        ]
        for key in stale_keys:
            self._sources.pop(key, None)
            self._view_state.pop(key, None)
            self._last_sample.pop(key, None)
            try:
                self._source_order.remove(key)
            except ValueError:
                pass

        for window_id, path in load_names.items():
            key = f"workspace:{window_id}"
            if key in self._sources:
                continue

            pil = originals.get(window_id)
            if pil is None:
                try:
                    pil = self.app._get_best_image_source_pil(window_id, prefer_current_view=False, rgb=False)
                except Exception:
                    pil = None

            if pil is None:
                continue

            self._sources[key] = {
                "key": key,
                "window_id": window_id,
                "path": path,
                "name": os.path.basename(path) if path else str(window_id),
                "pil": pil.copy() if isinstance(pil, Image.Image) else pil,
                "external": False,
            }
            self._source_order.append(key)

        self._rebuild_source_combo()
        if stale_keys:
            # Keep pins for closed images but do not restore them onto other sources.
            self._refresh_pin_tree()

        if self.current_source_key not in self._sources:
            self.current_source_key = None
            if self._source_order:
                self._switch_source(self._source_order[0], restore_sample=True)
            else:
                self.source_var.set("")
                self._clear_sample_ui()
                self._render_image()

    def _refresh_workspace_sources(self):
        self._load_workspace_sources()

    def _rebuild_source_combo(self):
        self._display_to_key.clear()
        self._key_to_display.clear()
        used = {}
        values = []

        for key in self._source_order:
            src = self._sources.get(key)
            if not src:
                continue
            base = src.get("name") or "Image"
            used[base] = used.get(base, 0) + 1
            display = base if used[base] == 1 else f"{base} ({used[base]})"
            if src.get("external"):
                display += "  [local]"
            self._display_to_key[display] = key
            self._key_to_display[key] = display
            values.append(display)

        self.source_combo.configure(values=values)

        if self.current_source_key in self._key_to_display:
            self.source_var.set(self._key_to_display[self.current_source_key])

    def _select_initial_source(self, initial_info):
        image_id = initial_info.get("image_id") if isinstance(initial_info, dict) else None
        initial_key = f"workspace:{image_id}" if image_id is not None else None

        if initial_key in self._sources:
            self._switch_source(initial_key, restore_sample=False)
            sample = self._sample_from_initial_info(initial_info, initial_key)
            if sample is not None:
                self._set_current_sample(sample, remember=True, show_tooltip=False)
            return

        if self._source_order:
            self._switch_source(self._source_order[0], restore_sample=False)
            sample = self._sample_from_initial_info(initial_info, self.current_source_key)
            if sample is not None:
                self._set_current_sample(sample, remember=True, show_tooltip=False)
        else:
            self._clear_sample_ui()

    def _sample_from_initial_info(self, info, source_key):
        if not isinstance(info, dict) or info.get("lab") is None:
            return None

        lab = tuple(float(v) for v in info.get("lab", (0, 0, 0)))
        selection_info = info.get("selection_info")

        if selection_info and selection_info.get("mean_rgb") is not None:
            rgb = tuple(int(v) for v in selection_info["mean_rgb"][:3])
        else:
            try:
                rgb = tuple(int(v) for v in UtilsTools.lab_to_rgb(lab))
            except Exception:
                rgb = (200, 200, 200)

        return self._build_sample(
            source_key=source_key,
            x=int(info.get("x", 0)),
            y=int(info.get("y", 0)),
            rgb=rgb,
            lab=lab,
            is_average=bool(info.get("is_average", False)),
            selection_info=selection_info,
        )

    def _on_source_combo(self, _event=None):
        key = self._display_to_key.get(self.source_var.get())
        if key:
            self._switch_source(key, restore_sample=True)

    def _step_source(self, delta):
        if not self._source_order:
            return
        try:
            idx = self._source_order.index(self.current_source_key)
        except ValueError:
            idx = 0
        idx = (idx + int(delta)) % len(self._source_order)
        self._switch_source(self._source_order[idx], restore_sample=True)

    def _switch_source(self, key, restore_sample=True):
        if key not in self._sources:
            return
        self.current_source_key = key
        self.source_var.set(self._key_to_display.get(key, self._sources[key].get("name", "Image")))

        if key not in self._view_state:
            pil = self._sources[key]["pil"]
            w, h = pil.size
            self._view_state[key] = {"zoom": 1.0, "cx": w / 2.0, "cy": h / 2.0}

        if restore_sample and key in self._last_sample:
            self._set_current_sample(dict(self._last_sample[key]), remember=False, show_tooltip=False)
        elif restore_sample:
            self._current_sample = None
            self._selected_proto_label = None
            self._clear_sample_ui()

        self._render_image()

    def _open_external_image(self):
        base_path = UtilsTools.get_base_path()
        initial_dir = os.path.join(base_path, "image_test")

        if not os.path.isdir(initial_dir):
            initial_dir = base_path

        path = filedialog.askopenfilename(
            title="Open image for Image Inspection",
            initialdir=initial_dir,
            parent=self.win,
            filetypes=[
                ("Image Files", "*.jpg *.jpeg *.png *.bmp *.gif *.tiff *.tif"),
                ("All Files", "*.*"),
            ],
        )

        if not path:
            return

        try:
            with Image.open(path) as img:
                pil = ImageOps.exif_transpose(img).convert("RGBA")
        except Exception as exc:
            self.app.custom_warning(
                "Open Image",
                f"Could not open image:\n{exc}",
                parent=self.win,
            )
            return

        self._external_counter += 1
        key = f"external:{self._external_counter}"

        self._sources[key] = {
            "key": key,
            "window_id": None,
            "path": path,
            "name": os.path.basename(path),
            "pil": pil,
            "external": True,
        }

        self._source_order.append(key)
        self._rebuild_source_combo()
        self._switch_source(key, restore_sample=True)

    # Image View / Coordinate Transform
    def _current_pil(self):
        src = self._sources.get(self.current_source_key)
        if not src:
            return None
        pil = src.get("pil")
        if not isinstance(pil, Image.Image):
            return None
        return pil

    def _reset_view(self):
        pil = self._current_pil()
        if pil is None or self.current_source_key is None:
            return
        w, h = pil.size
        self._view_state[self.current_source_key] = {"zoom": 1.0, "cx": w / 2.0, "cy": h / 2.0}
        self._render_image()

    @staticmethod
    def _clamp(value, low, high):
        return max(low, min(high, value))

    def _render_image(self):
        if not hasattr(self, "image_canvas"):
            return
        pil = self._current_pil()
        if pil is None:
            self.image_canvas.delete("all")
            self.image_canvas.create_text(
                max(1, self.image_canvas.winfo_width() // 2),
                max(1, self.image_canvas.winfo_height() // 2),
                text="No image available",
                fill=self.MUTED,
                font=self.FONT_BOLD,
            )
            self._render_transform = None
            return

        cw = max(10, self.image_canvas.winfo_width())
        ch = max(10, self.image_canvas.winfo_height())
        sw, sh = pil.size

        state = self._view_state.setdefault(
            self.current_source_key,
            {"zoom": 1.0, "cx": sw / 2.0, "cy": sh / 2.0},
        )

        zoom = float(self._clamp(state.get("zoom", 1.0), 1.0, 25.0))
        state["zoom"] = zoom

        fit_scale = min(cw / sw, ch / sh)
        display_scale = max(1e-9, fit_scale * zoom)

        visible_w = min(float(sw), cw / display_scale)
        visible_h = min(float(sh), ch / display_scale)

        cx = float(state.get("cx", sw / 2.0))
        cy = float(state.get("cy", sh / 2.0))

        half_w = visible_w / 2.0
        half_h = visible_h / 2.0
        cx = self._clamp(cx, half_w, max(half_w, sw - half_w))
        cy = self._clamp(cy, half_h, max(half_h, sh - half_h))
        state["cx"], state["cy"] = cx, cy

        left = max(0.0, cx - half_w)
        top = max(0.0, cy - half_h)
        right = min(float(sw), left + visible_w)
        bottom = min(float(sh), top + visible_h)

        # Recompute left/top after right/bottom clipping.
        left = max(0.0, right - visible_w)
        top = max(0.0, bottom - visible_h)

        crop_box = (
            int(round(left)),
            int(round(top)),
            max(int(round(left)) + 1, int(round(right))),
            max(int(round(top)) + 1, int(round(bottom))),
        )
        crop = pil.crop(crop_box)

        draw_w = max(1, min(cw, int(round(crop.width * display_scale))))
        draw_h = max(1, min(ch, int(round(crop.height * display_scale))))
        resized = crop.resize((draw_w, draw_h), Image.Resampling.LANCZOS)

        self._canvas_photo = ImageTk.PhotoImage(resized)
        ox = (cw - draw_w) / 2.0
        oy = (ch - draw_h) / 2.0

        self.image_canvas.delete("all")
        self.image_canvas.create_image(ox, oy, anchor="nw", image=self._canvas_photo, tags=("image",))

        actual_scale_x = draw_w / max(1.0, float(crop.width))
        actual_scale_y = draw_h / max(1.0, float(crop.height))
        self._render_transform = {
            "left": float(crop_box[0]),
            "top": float(crop_box[1]),
            "right": float(crop_box[2]),
            "bottom": float(crop_box[3]),
            "ox": ox,
            "oy": oy,
            "draw_w": draw_w,
            "draw_h": draw_h,
            "scale_x": actual_scale_x,
            "scale_y": actual_scale_y,
        }

        self.zoom_var.set("Fit" if abs(zoom - 1.0) < 1e-6 else f"{zoom * 100:.0f}%")
        self._draw_sample_marker()
        self._draw_roi_preview()

    def _canvas_to_source(self, x, y):
        t = self._render_transform
        pil = self._current_pil()
        if not t or pil is None:
            return None

        if not (t["ox"] <= x < t["ox"] + t["draw_w"] and t["oy"] <= y < t["oy"] + t["draw_h"]):
            return None

        sx = t["left"] + (x - t["ox"]) / max(t["scale_x"], 1e-9)
        sy = t["top"] + (y - t["oy"]) / max(t["scale_y"], 1e-9)
        sw, sh = pil.size
        sx = int(self._clamp(round(sx), 0, sw - 1))
        sy = int(self._clamp(round(sy), 0, sh - 1))
        return sx, sy

    def _source_to_canvas(self, sx, sy):
        t = self._render_transform
        if not t:
            return None
        if not (t["left"] <= sx <= t["right"] and t["top"] <= sy <= t["bottom"]):
            return None
        x = t["ox"] + (sx - t["left"]) * t["scale_x"]
        y = t["oy"] + (sy - t["top"]) * t["scale_y"]
        return x, y

    def _on_mousewheel(self, event):
        factor = 1.12 if event.delta > 0 else 1 / 1.12
        return self._zoom_at_event(event, factor)

    def _zoom_at_event(self, event, factor):
        if self.current_source_key is None or self._current_pil() is None:
            return "break"

        before = self._canvas_to_source(event.x, event.y)
        state = self._view_state[self.current_source_key]
        old_zoom = float(state.get("zoom", 1.0))
        new_zoom = self._clamp(old_zoom * float(factor), 1.0, 25.0)
        if abs(new_zoom - old_zoom) < 1e-9:
            return "break"

        state["zoom"] = new_zoom
        self._render_image()

        # Keep the pixel under the cursor approximately anchored.
        if before is not None:
            after = self._canvas_to_source(event.x, event.y)
            if after is not None:
                state["cx"] += before[0] - after[0]
                state["cy"] += before[1] - after[1]
                self._render_image()

        return "break"

    def _start_pan(self, event):
        if self.current_source_key is None or self._render_transform is None:
            return "break"
        self._pan_state = (event.x, event.y)
        self.image_canvas.configure(cursor="fleur")
        return "break"

    def _pan_motion(self, event):
        if self._pan_state is None or self.current_source_key is None:
            return "break"
        t = self._render_transform
        if not t:
            return "break"
        old_x, old_y = self._pan_state
        dx = event.x - old_x
        dy = event.y - old_y
        self._pan_state = (event.x, event.y)

        state = self._view_state[self.current_source_key]
        state["cx"] -= dx / max(t["scale_x"], 1e-9)
        state["cy"] -= dy / max(t["scale_y"], 1e-9)
        self._render_image()
        return "break"

    def _end_pan(self, _event):
        self._pan_state = None
        self.image_canvas.configure(cursor="crosshair")
        return "break"

    # LAB Filters
    def _lab_filter_bindings(self):
        return {
            "L_min": (self.filter_l_min_enabled, self.filter_l_min_var),
            "L_max": (self.filter_l_max_enabled, self.filter_l_max_var),
            "a_min": (self.filter_a_min_enabled, self.filter_a_min_var),
            "a_max": (self.filter_a_max_enabled, self.filter_a_max_var),
            "b_min": (self.filter_b_min_enabled, self.filter_b_min_var),
            "b_max": (self.filter_b_max_enabled, self.filter_b_max_var),
        }

    def _lab_filter_theme(self):
        return {
            "bg": self.BG,
            "card": self.CARD,
            "text": self.TEXT,
            "muted": self.MUTED,
            "blue": self.BLUE,
            "blue_soft": self.BLUE_SOFT,
            "font": self.FONT,
            "font_bold": self.FONT_BOLD,
            "font_small": self.FONT_SMALL,
            "font_small_bold": self.FONT_SMALL_BOLD,
            "font_section": self.FONT_SECTION,
        }

    def _active_lab_filters(self):
        return UtilsTools.read_lab_filter_bindings(
            self._lab_filter_bindings(),
            strict=False,
        )

    def _update_inspection_help(self):
        mode = self.inspection_mode_var.get().strip().lower()

        if mode == "live":
            text = "Move: inspect · Right-drag: pan · Wheel: zoom"
        else:
            drag_text = "filtered ROI" if self._active_lab_filters() else "ROI"
            text = f"Click: pixel · Drag: {drag_text} · Right-drag: pan · Wheel: zoom"

        self.inspection_help_var.set(text)

    def _update_filter_ui(self):
        filters = self._active_lab_filters()
        try:
            count = len(filters)
            self.filters_button.configure(
                text="Filters..." if count == 0 else f"Filters ({count})"
            )
        except Exception:
            pass
        self._update_inspection_help()

    def _open_lab_filters(self):
        existing = getattr(self, "_filters_window", None)
        try:
            if existing is not None and existing.winfo_exists():
                existing.lift()
                existing.focus_force()
                return
        except Exception:
            pass

        def on_close():
            self._filters_window = None

        self._filters_window = UtilsTools.open_lab_filters_dialog(
            parent=self.win,
            filter_bindings=self._lab_filter_bindings(),
            on_apply=self._on_lab_filters_applied,
            on_close=on_close,
            warning_callback=self.app.custom_warning,
            description=(
                "Enabled limits apply to dragged area averages. "
                "Single-pixel inspection is never filtered."
            ),
            theme=self._lab_filter_theme(),
        )

    def _on_lab_filters_applied(self, _filters=None):
        self._update_filter_ui()

        # Recompute the active ROI immediately so the displayed color,
        # memberships and comparison always correspond to the new limits.
        current = self._current_sample
        selection = current.get("selection_info") if current else None
        if (
            current
            and current.get("is_average")
            and selection
            and selection.get("type") == "roi"
        ):
            self._inspect_roi(
                selection.get("x1", 0),
                selection.get("y1", 0),
                selection.get("x2", 0),
                selection.get("y2", 0),
            )


    # Sample Inspection
    def _on_inspection_mode_changed(self, _event=None):
        display = self.inspection_mode_display_var.get().strip() or "Inspect"
        mode = display.lower()

        if mode not in ("inspect", "live"):
            mode = "inspect"
            display = "Inspect"
            self.inspection_mode_display_var.set(display)

        self.inspection_mode_var.set(mode)

        self._update_inspection_help()

        # Abort any unfinished manual area selection when changing mode.
        self._roi_drag_start = None
        self._roi_drag_current = None
        self._inspect_drag_start_canvas = None
        self._render_image()

    def _on_canvas_left_press(self, event):
        # In Live mode, mouse movement already performs the inspection.
        if self.inspection_mode_var.get() != "inspect":
            return "break"

        point = self._canvas_to_source(event.x, event.y)
        if point is None:
            self._roi_drag_start = None
            self._roi_drag_current = None
            self._inspect_drag_start_canvas = None
            return "break"

        # Store both image and canvas coordinates. Canvas coordinates are used
        # to distinguish a real drag from the tiny movement of a normal click.
        self._roi_drag_start = point
        self._roi_drag_current = point
        self._inspect_drag_start_canvas = (event.x, event.y)
        return "break"

    def _on_canvas_left_drag(self, event):
        if (
            self.inspection_mode_var.get() != "inspect"
            or self._roi_drag_start is None
        ):
            return "break"

        point = self._canvas_to_source(event.x, event.y)
        if point is None:
            return "break"

        self._roi_drag_current = point

        # Require a minimum canvas movement before starting an ROI selection.
        start_canvas = self._inspect_drag_start_canvas
        if start_canvas is not None:
            dx = abs(event.x - start_canvas[0])
            dy = abs(event.y - start_canvas[1])
            if dx >= 4 or dy >= 4:
                self._render_image()

        return "break"

    def _on_canvas_left_release(self, event):
        if self.inspection_mode_var.get() != "inspect":
            return "break"

        point = self._canvas_to_source(event.x, event.y)
        start = self._roi_drag_start
        start_canvas = self._inspect_drag_start_canvas

        self._roi_drag_start = None
        self._roi_drag_current = None
        self._inspect_drag_start_canvas = None

        if point is None or start is None:
            self._render_image()
            return "break"

        # Canvas-distance thresholds remain consistent across zoom levels.
        if start_canvas is None:
            is_drag = False
        else:
            dx = abs(event.x - start_canvas[0])
            dy = abs(event.y - start_canvas[1])
            is_drag = dx >= 4 or dy >= 4

        if is_drag:
            self._inspect_roi(start[0], start[1], point[0], point[1])
        else:
            self._inspect_pixel(point[0], point[1], show_tooltip=True)

        return "break"

    def _on_canvas_motion(self, event):
        if self.inspection_mode_var.get() != "live":
            return
        point = self._canvas_to_source(event.x, event.y)
        if point is None:
            return
        self._live_pending_xy = point
        if self._live_after_id is not None:
            return

        self._live_after_id = self.win.after(65, self._flush_live_inspection)

    def _flush_live_inspection(self):
        self._live_after_id = None
        point = self._live_pending_xy
        self._live_pending_xy = None
        if point is None:
            return
        self._inspect_pixel(point[0], point[1], show_tooltip=False)

    def _inspect_pixel(self, x, y, show_tooltip=False):
        pil = self._current_pil()
        if pil is None or self.current_source_key is None:
            return

        rgba = pil.convert("RGBA").getpixel((int(x), int(y)))
        r, g, b, a = rgba
        if a == 0:
            return

        rgb = (int(r), int(g), int(b))
        lab = tuple(float(v) for v in UtilsTools.rgb_to_lab(rgb))
        sample = self._build_sample(
            source_key=self.current_source_key,
            x=int(x),
            y=int(y),
            rgb=rgb,
            lab=lab,
            is_average=False,
            selection_info=None,
        )
        self._set_current_sample(sample, remember=True, show_tooltip=show_tooltip)

    def _inspect_roi(self, x1, y1, x2, y2):
        pil = self._current_pil()
        if pil is None or self.current_source_key is None:
            return

        left, right = sorted((int(x1), int(x2)))
        top, bottom = sorted((int(y1), int(y2)))

        if right <= left or bottom <= top:
            self._inspect_pixel(left, top, show_tooltip=True)
            return

        rgba = np.asarray(
            pil.convert("RGBA").crop((left, top, right + 1, bottom + 1)),
            dtype=np.uint8,
        )
        if rgba.size == 0:
            return

        visible = rgba[..., 3] > 0
        total_count = int(np.count_nonzero(visible))
        if total_count == 0:
            return

        rgb_pixels = rgba[..., :3][visible].astype(np.float32)
        filters = self._active_lab_filters()
        mean_rgb_arr, used_count = UtilsTools.mean_rgb_with_lab_filters(
            rgb_pixels,
            filters,
        )

        if used_count <= 0 or mean_rgb_arr is None:
            self.app.custom_warning(
                "No Valid Pixels",
                "No pixels in the selected area satisfy the active LAB filters.",
                parent=self.win,
            )
            self._current_sample = None
            self._selected_proto_label = None
            self._clear_sample_ui()
            self._render_image()
            return

        mean_rgb = tuple(int(round(v)) for v in mean_rgb_arr[:3])
        mean_lab = tuple(float(v) for v in UtilsTools.rgb_to_lab(mean_rgb))

        width = right - left + 1
        height = bottom - top + 1
        cx = int(round((left + right) / 2.0))
        cy = int(round((top + bottom) / 2.0))
        filters_applied = bool(filters)

        selection_info = {
            "type": "roi",
            "x1": left,
            "y1": top,
            "x2": right,
            "y2": bottom,
            "width": width,
            "height": height,
            "pixels": int(used_count),
            "total_pixels": int(total_count),
            "filtered_out": int(total_count - used_count),
            "filters_applied": filters_applied,
            "filters": dict(filters),
            "filter_summary": UtilsTools.format_lab_filters(filters, prefix=True)
            if filters_applied else "",
            "mean_rgb": mean_rgb,
        }

        sample = self._build_sample(
            source_key=self.current_source_key,
            x=cx,
            y=cy,
            rgb=mean_rgb,
            lab=mean_lab,
            is_average=True,
            selection_info=selection_info,
        )
        self._set_current_sample(sample, remember=True, show_tooltip=False)

    def _build_sample(self, source_key, x, y, rgb, lab, is_average=False, selection_info=None):
        memberships = self.manager.calculate_memberships(self.app.fuzzy_color_space, lab)
        winner_label = memberships[0][0] if memberships else None
        winner_mu = float(memberships[0][1]) if memberships else 0.0

        return {
            "source_key": source_key,
            "x": int(x),
            "y": int(y),
            "rgb": tuple(int(v) for v in rgb[:3]),
            "lab": tuple(float(v) for v in lab[:3]),
            "hex": UtilsTools.rgb_to_hex(rgb).upper(),
            "is_average": bool(is_average),
            "selection_info": selection_info,
            "memberships": memberships,
            "winner_label": winner_label,
            "winner_mu": winner_mu,
        }

    def _set_current_sample(self, sample, remember=True, show_tooltip=False):
        self._current_sample = sample
        key = sample.get("source_key")
        if key in self._sources and key != self.current_source_key:
            self._switch_source(key, restore_sample=False)

        if remember and key:
            self._last_sample[key] = dict(sample)

        self._tooltip_enabled = bool(show_tooltip)
        self._selected_proto_label = sample.get("winner_label")
        self._update_sample_ui()
        self._populate_memberships()
        self._update_prototype_ui()
        self._render_image()

    def _set_sample_filter_info(self, text):
        text = str(text or "").strip()
        self.sample_filters_var.set(text)

        try:
            if text:
                if not self.sample_filters_label.winfo_manager():
                    self.sample_filters_label.pack(
                        fill="x",
                        pady=(2, 0),
                    )
            else:
                self.sample_filters_label.pack_forget()
        except Exception:
            pass

    def _clear_sample_ui(self):
        self.sample_title_var.set("No sample selected")
        self.sample_kind_var.set("")
        self.sample_coord_var.set("Click a pixel in the image")
        self._set_sample_filter_info("")
        self.sample_lab_var.set("LAB: —")
        self.sample_rgb_var.set("RGB: —")
        self.sample_hex_var.set("HEX: —")
        self.sample_swatch.itemconfig(self.sample_swatch_rect, fill="#d9dde3")

        self.winner_summary_var.set("Close Prototype: —")
        self._clear_membership_rows()

        self.proto_title_var.set("Close Prototype")
        self.proto_name_var.set("—")
        self.proto_lab_var.set("LAB: —")
        self.proto_rgb_var.set("RGB: —")
        self.proto_hex_var.set("HEX: —")
        self.proto_swatch.itemconfig(self.proto_swatch_rect, fill="#d9dde3")
        self.comparison_status_var.set("")
        self.comparison_value_var.set("Select a sample to compare")
        self.details_text_var.set("")
        self.use_winner_button.pack_forget()
        self._apply_result_style("unavailable")

    def _update_sample_ui(self):
        s = self._current_sample
        if not s:
            self._clear_sample_ui()
            return

        selection = s.get("selection_info")
        if s.get("is_average") and selection and selection.get("type") == "roi":
            self.sample_title_var.set("Mean Color")
            self.sample_kind_var.set("ROI average")

            self.sample_coord_var.set(
                f"({selection['x1']}, {selection['y1']}) → "
                f"({selection['x2']}, {selection['y2']})"
            )

            used = int(selection.get("pixels", 0))
            total = int(selection.get("total_pixels", used))

            if selection.get("filters_applied"):
                self._set_sample_filter_info(
                    f"{selection['width']} × {selection['height']} px · "
                    f"{used:,}/{total:,} used"
                )
            else:
                self._set_sample_filter_info(
                    f"{selection['width']} × {selection['height']} px · "
                    f"{used:,} pixels"
                )

        else:
            self.sample_title_var.set("Selected Color")
            self.sample_kind_var.set("Single pixel")
            self.sample_coord_var.set(
                f"({s['x']}, {s['y']})"
            )
            self._set_sample_filter_info("")

        lab = s["lab"]
        rgb = s["rgb"]
        self.sample_lab_var.set(f"LAB: {lab[0]:.2f}, {lab[1]:.2f}, {lab[2]:.2f}")
        self.sample_rgb_var.set(f"RGB: {rgb[0]}, {rgb[1]}, {rgb[2]}")
        self.sample_hex_var.set(f"HEX: {s['hex']}")
        self.sample_swatch.itemconfig(self.sample_swatch_rect, fill=s["hex"])

        if s.get("winner_label") is not None:
            self.winner_summary_var.set(
                f"Close Prototype: {s['winner_label']}   ·   μ = {s['winner_mu']:.4f}"
            )
        else:
            self.winner_summary_var.set("Close Prototype: —")

    def _draw_sample_marker(self):
        s = self._current_sample
        if not s or s.get("source_key") != self.current_source_key:
            return

        selection = s.get("selection_info")
        if s.get("is_average") and selection and selection.get("type") == "roi":
            p1 = self._source_to_canvas(selection["x1"], selection["y1"])
            p2 = self._source_to_canvas(selection["x2"], selection["y2"])
            if p1 and p2:
                self.image_canvas.create_rectangle(
                    p1[0], p1[1], p2[0], p2[1],
                    outline="#d62728", width=2, tags=("sample_marker",)
                )
            return

        p = self._source_to_canvas(s["x"], s["y"])
        if p is None:
            return
        x, y = p
        self.image_canvas.create_line(x - 9, y, x + 9, y, fill="#d62728", width=2, tags=("sample_marker",))
        self.image_canvas.create_line(x, y - 9, x, y + 9, fill="#d62728", width=2, tags=("sample_marker",))
        self.image_canvas.create_oval(x - 5, y - 5, x + 5, y + 5, outline="white", width=1, tags=("sample_marker",))

        if self._tooltip_enabled:
            text = (
                f"RGB {s['rgb'][0]}, {s['rgb'][1]}, {s['rgb'][2]}\n"
                f"LAB {s['lab'][0]:.2f}, {s['lab'][1]:.2f}, {s['lab'][2]:.2f}\n"
                f"{s.get('winner_label') or '—'} · μ={s.get('winner_mu', 0.0):.3f}"
            )
            tx = min(self.image_canvas.winfo_width() - 95, x + 78)
            ty = max(38, y - 42)
            rect = self.image_canvas.create_rectangle(
                tx - 72, ty - 30, tx + 72, ty + 30,
                fill="white", outline="#9ca3af", width=1, tags=("sample_tooltip",)
            )
            self.image_canvas.create_text(
                tx, ty, text=text, fill=self.TEXT, font=self.FONT_SMALL,
                justify="left", tags=("sample_tooltip",)
            )
            self.win.after(1700, self._hide_tooltip)

    def _draw_roi_preview(self):
        if self._roi_drag_start is None or self._roi_drag_current is None:
            return

        start_canvas = self._inspect_drag_start_canvas
        if start_canvas is not None:
            current_canvas = self._source_to_canvas(*self._roi_drag_current)
            if current_canvas is not None:
                dx = abs(current_canvas[0] - start_canvas[0])
                dy = abs(current_canvas[1] - start_canvas[1])
                if dx < 4 and dy < 4:
                    return

        p1 = self._source_to_canvas(*self._roi_drag_start)
        p2 = self._source_to_canvas(*self._roi_drag_current)
        if p1 is None or p2 is None:
            return

        self.image_canvas.create_rectangle(
            p1[0], p1[1], p2[0], p2[1],
            outline="#d97706", width=2, dash=(5, 3),
            tags=("roi_preview",),
        )

    def _hide_tooltip(self):
        self._tooltip_enabled = False
        try:
            self.image_canvas.delete("sample_tooltip")
        except Exception:
            pass

    # Membership / Prototype / Comparison
    def _clear_membership_rows(self):
        for child in self.membership_inner.winfo_children():
            child.destroy()
        self._membership_rows.clear()
        self._membership_controls.clear()

    def _populate_memberships(self):
        s = self._current_sample
        memberships = s.get("memberships", []) if s else []

        if not memberships:
            self._clear_membership_rows()
            tk.Label(
                self.membership_inner,
                text="No memberships available.",
                bg=self.CARD,
                fg=self.MUTED,
                font=self.FONT,
                anchor="w",
            ).pack(fill="x", padx=5, pady=8)
            return

        # Reuse membership rows during Live inspection to avoid rebuilding Tk widgets.
        labels = [label for label, _mu in memberships]
        if len(set(labels)) == len(labels) and set(labels) == set(self._membership_rows):
            for label, mu in memberships:
                row, bar, value = self._membership_controls[label]
                bar.configure(value=max(0.0, min(1.0, float(mu))) * 100.0)
                value.configure(text=f"μ = {float(mu):.4f}")
                row.pack_forget()
                row.pack(fill="x", pady=1, padx=2)
            self._highlight_membership_selection()
            return

        self._clear_membership_rows()
        for label, mu in memberships:
            row = tk.Frame(self.membership_inner, bg=self.CARD, cursor="hand2")
            row.pack(fill="x", pady=1, padx=2)
            self._membership_rows[label] = row

            proto_hex = self._proto_hex(label)
            sw = tk.Canvas(row, width=18, height=18, bg=self.CARD, highlightthickness=0)
            sw.pack(side="left", padx=(3, 6), pady=3)
            sw.create_rectangle(2, 2, 16, 16, fill=proto_hex, outline="#707070")

            name = tk.Label(row, text=str(label), bg=self.CARD, fg=self.TEXT, font=self.FONT, anchor="w")
            name.pack(side="left", fill="x", expand=True)

            bar = ttk.Progressbar(row, orient="horizontal", mode="determinate", maximum=100.0, value=max(0.0, min(1.0, float(mu))) * 100.0, length=105)
            bar.pack(side="left", padx=(5, 8))

            value = tk.Label(row, text=f"μ = {float(mu):.4f}", bg=self.CARD, fg=self.TEXT, font=self.FONT_SMALL, width=10, anchor="e")
            value.pack(side="right", padx=(0, 5))
            self._membership_controls[label] = (row, bar, value)

            for widget in (row, sw, name, bar, value):
                widget.bind("<Button-1>", lambda _e, lbl=label: self._select_prototype(lbl))

        self._highlight_membership_selection()

    def _highlight_membership_selection(self):
        for label, row in self._membership_rows.items():
            bg = self.BLUE_SOFT if label == self._selected_proto_label else self.CARD
            try:
                row.configure(bg=bg)
                for child in row.winfo_children():
                    if isinstance(child, (tk.Label, tk.Canvas)):
                        child.configure(bg=bg)
            except Exception:
                pass

    def _select_prototype(self, label):
        self._selected_proto_label = label
        self._highlight_membership_selection()
        self._update_prototype_ui()

    def _select_winner_prototype(self):
        if self._current_sample and self._current_sample.get("winner_label") is not None:
            self._select_prototype(self._current_sample["winner_label"])

    def _proto_lab(self, label):
        try:
            data = self.app.color_data[label]["positive_prototype"]
            arr = np.asarray(data, dtype=float).reshape(-1)
            return tuple(float(v) for v in arr[:3])
        except Exception:
            return None

    def _proto_rgb(self, label):
        lab = self._proto_lab(label)
        if lab is None:
            return (200, 200, 200)
        try:
            return tuple(int(v) for v in UtilsTools.lab_to_rgb(lab))
        except Exception:
            return (200, 200, 200)

    def _proto_hex(self, label):
        try:
            return UtilsTools.rgb_to_hex(self._proto_rgb(label)).upper()
        except Exception:
            return "#CCCCCC"

    def _update_prototype_ui(self):
        s = self._current_sample
        label = self._selected_proto_label
        if not s or label is None:
            self.proto_name_var.set("—")
            self.comparison_value_var.set("Select a sample to compare")
            self.comparison_status_var.set("")
            self.details_text_var.set("")
            self._apply_result_style("unavailable")
            return

        winner = s.get("winner_label")
        is_winner = label == winner
        self.proto_title_var.set("Close Prototype" if is_winner else "Selected Prototype")
        self.proto_name_var.set(str(label))

        if is_winner:
            self.use_winner_button.pack_forget()
        else:
            self.use_winner_button.pack(side="right", padx=(8, 0))

        proto_lab = self._proto_lab(label)
        proto_rgb = self._proto_rgb(label)
        proto_hex = self._proto_hex(label)

        if proto_lab is None:
            self.proto_lab_var.set("LAB: not available")
        else:
            self.proto_lab_var.set(f"LAB: {proto_lab[0]:.2f}, {proto_lab[1]:.2f}, {proto_lab[2]:.2f}")
        self.proto_rgb_var.set(f"RGB: {proto_rgb[0]}, {proto_rgb[1]}, {proto_rgb[2]}")
        self.proto_hex_var.set(f"HEX: {proto_hex}")
        self.proto_swatch.itemconfig(self.proto_swatch_rect, fill=proto_hex)

        self._refresh_comparison_result()

    def _refresh_comparison_result(self):
        s = self._current_sample
        label = self._selected_proto_label
        proto_lab = self._proto_lab(label) if label is not None else None
        if not s or proto_lab is None:
            self.comparison_status_var.set("")
            self.comparison_value_var.set("Comparison unavailable")
            self.details_text_var.set("")
            self._apply_result_style("unavailable")
            return

        settings = self.app.threshold_settings
        metric = settings.get("metric", "CIEDE2000")
        evaluation = self.manager.evaluate_color_difference_threshold(
            sample_lab=s["lab"],
            prototype_lab=proto_lab,
            metric=metric,
            threshold_settings=settings,
        )

        self.comparison_status_var.set(evaluation.get("evaluation", "Comparison"))
        self.comparison_value_var.set(evaluation.get("detail", "Metric not available"))
        self._apply_result_style(evaluation.get("status", "unavailable"))

        summary = str(evaluation.get("summary_visual", evaluation.get("summary", ""))).strip()
        if summary:
            lines = summary.splitlines()
            # Omit the repeated status line from the detailed comparison.
            detail = "\n".join(lines[1:]).strip()
        else:
            detail = ""

        if not detail:
            try:
                detail = self.manager.format_component_summary(s["lab"], proto_lab, metric).strip()
            except Exception:
                detail = "No detailed comparison available."

        self.details_text_var.set(detail)

    def _apply_result_style(self, status):
        if status in ("inside", "below_pt", "below_at", "below_custom", "below_lower", "within", "below"):
            body, header, accent = self.GREEN_BG, "#dff0d8", self.GREEN
        elif status in ("warning", "between_pt_at", "between_custom", "between"):
            body, header, accent = self.YELLOW_BG, "#ffe0b2", self.YELLOW
        elif status in ("outside", "above_pt", "above_at", "above_custom", "above_upper", "above"):
            body, header, accent = self.RED_BG, "#f2dede", self.RED
        else:
            body, header, accent = self.SOFT, "#eeeeee", "#6b7280"

        try:
            self.result_card.configure(bg=body, highlightbackground=accent, highlightcolor=accent)
            self.result_header.configure(bg=header)
            self.result_dot.configure(bg=header)
            self.result_dot.itemconfig(self.result_dot_oval, fill=accent, outline=accent)
            for child in self.result_header.winfo_children():
                if isinstance(child, tk.Label):
                    child.configure(bg=header)
            self.result_body.configure(bg=body)
            self.result_value_label.configure(bg=body, fg=accent)
        except Exception:
            pass

    def _toggle_details(self):
        self._details_expanded = not self._details_expanded
        if self._details_expanded:
            self.details_button_var.set("Hide detailed comparison ▴")
            self.details_frame.pack(fill="x", pady=(5, 0))
        else:
            self.details_button_var.set("Show detailed comparison ▾")
            self.details_frame.pack_forget()

    # Threshold / Metric Settings
    def _on_metric_family_changed(self, _event=None):
        metrics = self.manager.get_metrics_for_family(self.metric_family_var.get())
        self.metric_combo.configure(values=metrics)
        if self.metric_var.get() not in metrics and metrics:
            self.metric_var.set(metrics[0])
        self._threshold_changed()

    def _threshold_mode_changed(self):
        self._rebuild_threshold_dynamic_controls()
        self._threshold_changed()

    def _rebuild_threshold_dynamic_controls(self):
        for child in self.threshold_dynamic.winfo_children():
            child.destroy()

        mode = self.threshold_mode_var.get().strip().lower()
        if mode == "default":
            tk.Label(
                self.threshold_dynamic,
                text="Default preset",
                font=self.FONT_SMALL_BOLD,
                bg=self.CARD,
                fg=self.TEXT,
            ).pack(side="left")
            combo = ttk.Combobox(
                self.threshold_dynamic,
                textvariable=self.threshold_preset_var,
                values=[
                    "Perceptibility Threshold",
                    "Acceptability Threshold",
                    "Perceptibility + Acceptability",
                ],
                state="readonly",
                width=30,
            )
            combo.pack(side="right", fill="x", expand=True, padx=(10, 0))
            combo.bind("<<ComboboxSelected>>", lambda _e: self._threshold_changed())
            return

        top = tk.Frame(self.threshold_dynamic, bg=self.CARD)
        top.pack(fill="x")
        tk.Label(top, text="Custom mode", font=self.FONT_SMALL_BOLD, bg=self.CARD, fg=self.TEXT).pack(side="left")
        combo = ttk.Combobox(
            top,
            textvariable=self.threshold_custom_type_var,
            values=["Single threshold", "Lower and upper thresholds"],
            state="readonly",
            width=25,
        )
        combo.pack(side="right", fill="x", expand=True, padx=(10, 0))
        combo.bind("<<ComboboxSelected>>", lambda _e: self._custom_threshold_mode_changed())

        entries = tk.Frame(self.threshold_dynamic, bg=self.CARD)
        entries.pack(fill="x", pady=(7, 0))
        self._custom_entries_holder = entries
        self._rebuild_custom_entries()

    def _custom_threshold_mode_changed(self):
        self._rebuild_custom_entries()
        self._threshold_changed()

    def _rebuild_custom_entries(self):
        holder = getattr(self, "_custom_entries_holder", None)
        if holder is None:
            return
        for child in holder.winfo_children():
            child.destroy()

        custom_type = self.threshold_custom_type_var.get()
        if custom_type == "Lower and upper thresholds":
            holder.columnconfigure(1, weight=1)
            holder.columnconfigure(3, weight=1)
            tk.Label(holder, text="Lower", font=self.FONT_SMALL_BOLD, bg=self.CARD).grid(row=0, column=0, sticky="w")
            low = tk.Entry(holder, textvariable=self.threshold_lower_var, width=10, font=self.FONT)
            low.grid(row=0, column=1, sticky="ew", padx=(6, 12))
            tk.Label(holder, text="Upper", font=self.FONT_SMALL_BOLD, bg=self.CARD).grid(row=0, column=2, sticky="w")
            high = tk.Entry(holder, textvariable=self.threshold_upper_var, width=10, font=self.FONT)
            high.grid(row=0, column=3, sticky="ew", padx=(6, 0))
            low.bind("<KeyRelease>", lambda _e: self._threshold_changed())
            high.bind("<KeyRelease>", lambda _e: self._threshold_changed())
        else:
            holder.columnconfigure(1, weight=1)
            tk.Label(holder, text="Threshold", font=self.FONT_SMALL_BOLD, bg=self.CARD).grid(row=0, column=0, sticky="w")
            entry = tk.Entry(holder, textvariable=self.threshold_single_var, width=12, font=self.FONT)
            entry.grid(row=0, column=1, sticky="ew", padx=(8, 0))
            entry.bind("<KeyRelease>", lambda _e: self._threshold_changed())

    def _threshold_changed(self):
        metric = self.metric_var.get().strip()
        self.metric_help_var.set(self.manager.get_metric_description(metric))

        self.app.threshold_settings = self.manager.build_threshold_settings_from_ui_values(
            metric_family=self.metric_family_var.get(),
            metric=metric,
            mode=self.threshold_mode_var.get(),
            preset_display=self.threshold_preset_var.get(),
            custom_type_display=self.threshold_custom_type_var.get(),
            single_value=self.threshold_single_var.get(),
            lower_value=self.threshold_lower_var.get(),
            upper_value=self.threshold_upper_var.get(),
            base_settings=getattr(self.app, "threshold_settings", None),
        )

        # Normalize controls in case family/metric aliases were corrected.
        normalized = self.app.threshold_settings
        self.metric_family_var.set(normalized.get("metric_family", self.metric_family_var.get()))
        self.metric_var.set(normalized.get("metric", self.metric_var.get()))
        self.metric_help_var.set(self.manager.get_metric_description(self.metric_var.get()))
        self._refresh_comparison_result()

    # Pinned Samples
    def _pin_current_sample(self):
        if not self._current_sample:
            return
        sample = copy.deepcopy(self._current_sample)
        self._pinned_samples.append(sample)
        self._refresh_pin_tree()

    def _refresh_pin_tree(self):
        for item in self.pin_tree.get_children():
            self.pin_tree.delete(item)

        for i, sample in enumerate(self._pinned_samples):
            src = self._sources.get(sample.get("source_key"), {})
            name = src.get("name", "[Image unavailable]")
            selection = sample.get("selection_info")
            if sample.get("is_average") and selection and selection.get("type") == "roi":
                pos = f"ROI {selection['width']}×{selection['height']}"
            else:
                pos = f"({sample['x']}, {sample['y']})"
            self.pin_tree.insert(
                "",
                "end",
                iid=str(i),
                values=(name, pos, sample.get("winner_label") or "—", f"{sample.get('winner_mu', 0.0):.4f}"),
            )

    def _restore_selected_pin(self):
        selected = self.pin_tree.selection()
        if not selected:
            return
        try:
            idx = int(selected[0])
            sample = copy.deepcopy(self._pinned_samples[idx])
        except Exception:
            return
        source_key = sample.get("source_key")
        if source_key not in self._sources:
            self.app.custom_warning(
                "Image Unavailable",
                "The original image window for this pinned sample has been closed. "
                "Select its image again and create a new pin.",
                parent=self.win,
            )
            return
        self._set_current_sample(sample, remember=True, show_tooltip=False)

    def _remove_selected_pin(self):
        selected = self.pin_tree.selection()
        if not selected:
            return
        indices = sorted((int(i) for i in selected), reverse=True)
        for idx in indices:
            if 0 <= idx < len(self._pinned_samples):
                del self._pinned_samples[idx]
        self._refresh_pin_tree()

    def _clear_pins(self):
        self._pinned_samples.clear()
        self._refresh_pin_tree()

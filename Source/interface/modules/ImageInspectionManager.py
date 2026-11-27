import os
import copy
import platform
from collections import OrderedDict
import tkinter as tk
from tkinter import ttk, filedialog

import numpy as np
from PIL import Image, ImageTk, ImageOps

import Source.interface.modules.UtilsTools as UtilsTools


from Source.interface.modules.ColorEvaluationManager import (
    rank_membership_frontier as inspection_rank,
    membership_snapshot as inspection_membership_snapshot, nearest_granule)


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
    BLUE = UtilsTools.UI_ACCENT
    BLUE_SOFT = UtilsTools.UI_ACCENT_SOFT
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
        self.win.withdraw()
        self.win.title("Image Inspection")
        self.win.configure(bg=self.BG)
        self.win.minsize(1120, 700)
        self.win.protocol("WM_DELETE_WINDOW", self.close)

        # Inspection remains open while the main application is in use.
        try:
            self.win.transient(self.root)
        except Exception:
            pass

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
        self._selected_proto_label = None  # Always a REAL granule label.
        self._selected_category_label = None
        self._reference_locked = False
        self._category_locked = False
        self._expanded_membership_categories = set()
        self._reference_space_id = None
        self._reference_space = None
        self._membership_topology = {}
        self._membership_roots = ()
        self._membership_descendants = {}
        self._membership_levels = (0,)
        self._membership_frontiers = {}
        self._membership_last_key = None
        self._membership_last_snapshot = None
        self._membership_cache = OrderedDict()
        self._nearest_cache = OrderedDict()
        self._membership_cache_limit = 128
        self._reference_categories = {}
        self._reference_labels = {}
        # Compute display RGB/HEX once per reference instead of converting LAB
        # repeatedly for each inspected pixel in Live mode.
        self._reference_rgb_cache = {}
        self._reference_hex_cache = {}
        self._membership_rows = {}
        # Reuse these row widgets as the sampled pixel changes in Live mode.
        self._membership_controls = {}
        self._pinned_samples = []

        self._canvas_photo = None
        self._render_transform = None
        self._pan_state = None
        self._live_after_id = None
        self._initial_sash_id = None
        self._initial_render_id = None
        self._tooltip_after_id = None
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
        self._initial_render_id = self.win.after(50, self._render_image)
        self.win.update_idletasks()
        self._maximize_window()
        self.win.deiconify()
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
        self._cancel_pending_live_inspection()
        for attr in ("_live_after_id", "_initial_sash_id", "_initial_render_id", "_tooltip_after_id"):
            pending = getattr(self, attr, None)
            if pending is not None:
                try:
                    self.win.after_cancel(pending)
                except tk.TclError:
                    pass
                setattr(self, attr, None)

        # This binding tag is private to the inspector; release its handlers
        # when the window closes so the main GUI never inherits them.
        tag = getattr(self, "_right_wheel_tag", None)
        if tag:
            for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                try:
                    self.win.unbind_class(tag, sequence)
                except tk.TclError:
                    pass

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
            value="Click: sample pixel · Drag: mean color (ROI) · Right-drag: pan · Wheel: zoom"
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

        self.winner_summary_var = tk.StringVar(value="Highest Membership Degree: —")
        space = getattr(self.app, "fuzzy_color_space", None)
        self.tconorm_var = tk.StringVar(value=getattr(space, "tconorm", "bounded_sum").upper())
        self.tconorm_display_var = tk.StringVar(value=self._tconorm_caption(self.tconorm_var.get()))
        self.show_zero_memberships_var = tk.BooleanVar(value=False)
        self.membership_level_var = tk.StringVar(value="Root categories")
        self.proto_category_var = tk.StringVar(value="Category: —")
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
        # Give the inspection controls more space when the window first opens.
        # The sash remains freely adjustable afterwards.
        paned.add(left, stretch="always", minsize=600)
        paned.add(right, stretch="always", minsize=440)

        self._build_left_image_panel(left)
        self._build_right_scroll_panel(right)

        def _initial_sash():
            try:
                total = paned.winfo_width()
                if total > 1:
                    paned.sash_place(0, int(total * 0.62), 1)
            except Exception:
                pass

        self._initial_sash_id = self.win.after(150, _initial_sash)

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

        self.source_combo = UtilsTools.styled_combobox(
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
            activebackground=UtilsTools.UI_ACCENT_HOVER,
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

        # Reserve the footer before the expandable image, just as in Image Based.
        canvas_holder.pack_forget()
        footer = tk.Frame(image_card, bg=self.CARD)
        footer.pack(side="bottom", fill="x", pady=(6, 0))
        footer.grid_columnconfigure(1, weight=1)
        inspection = self._card(footer, "Inspection", padx=7, pady=6)
        inspection.grid(row=0, column=0, sticky="ns", padx=(0, 7))
        inspection_controls = tk.Frame(inspection, bg=self.CARD)
        inspection_controls.pack(expand=True, fill="x", padx=2)
        self.inspection_mode_combo = UtilsTools.styled_combobox(
            inspection_controls, textvariable=self.inspection_mode_display_var,
            values=("Inspect", "Live"), state="readonly", width=10)
        self.inspection_mode_combo.pack(fill="x", pady=(0, 14))
        self.inspection_mode_combo.bind("<<ComboboxSelected>>", self._on_inspection_mode_changed)
        self.filters_button = tk.Button(
            inspection_controls, text="Filters...", command=self._open_lab_filters,
            font=self.FONT, bg="#f8fafc", fg=self.TEXT,
            activebackground="#eef2f7", activeforeground=self.TEXT,
            relief="solid", bd=1, padx=7, pady=4, cursor="hand2")
        self.filters_button.pack(fill="x")
        self._build_pinned_samples_panel(footer)

        controls = tk.Frame(image_card, bg=self.CARD)
        controls.pack(side="bottom", fill="x", pady=(8, 0))
        self.pin_sample_button = tk.Button(
            controls, text="☆ Pin Sample", command=self._pin_current_sample,
            font=self.FONT_SMALL_BOLD, bg=self.YELLOW_BG, fg=self.YELLOW,
            activebackground="#ffedc2", activeforeground=self.YELLOW,
            relief="solid", bd=1, padx=6, pady=2, cursor="hand2")
        self.pin_sample_button.pack(side="left", padx=(0, 5))
        right_controls = tk.Frame(controls, bg=self.CARD)
        right_controls.pack(side="right")
        tk.Label(right_controls, text="Zoom:", font=self.FONT_SMALL,
                 bg=self.CARD, fg=self.MUTED).pack(side="left")
        tk.Label(right_controls, textvariable=self.zoom_var, font=self.FONT_SMALL_BOLD,
                 bg=self.CARD, fg=self.TEXT).pack(side="left", padx=(3, 7))
        self.fit_button = tk.Button(right_controls, text="Fit", command=self._reset_view,
                  font=self.FONT_SMALL, relief="solid", bd=1, padx=4, pady=1,
                  cursor="hand2")
        self.fit_button.pack(side="left")
        self._inspection_help_label = tk.Label(
            controls, textvariable=self.inspection_help_var, font=self.FONT_SMALL,
            bg=self.CARD, fg=self.MUTED, anchor="center", justify="center")
        self._inspection_help_label.pack(side="left", fill="x", expand=True, padx=(3, 6))
        def wrap_help(event):
            width = max(1, event.width - 4)
            if int(self._inspection_help_label.cget("wraplength")) != width:
                self._inspection_help_label.configure(wraplength=width)
        self._inspection_help_label.bind("<Configure>", wrap_help)
        canvas_holder.pack(fill="both", expand=True)

    def _build_pinned_samples_panel(self, parent):
        pins = self._card(parent, "Pinned Samples", padx=8, pady=7)
        pins.configure(labelanchor="n")
        pins.grid(row=0, column=1, sticky="nsew")

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
        self.pin_tree.heading("prototype", text="Root Category")
        self.pin_tree.heading("membership", text="μ")
        self.pin_tree.column("image", width=190, anchor="center")
        self.pin_tree.column("position", width=130, anchor="center")
        self.pin_tree.column("prototype", width=150, anchor="center")
        self.pin_tree.column("membership", width=75, anchor="center")
        self.pin_tree.pack(side="left", fill="x", expand=True)
        self.pin_tree.bind("<Double-1>", lambda _e: self._restore_selected_pin())

        pin_scroll = UtilsTools.styled_scrollbar(table_row, orient="vertical", command=self.pin_tree.yview)
        pin_scroll.pack(side="right", fill="y")
        self.pin_tree.configure(yscrollcommand=pin_scroll.set)

        buttons = tk.Frame(pins, bg=self.CARD)
        buttons.pack(fill="x", pady=(6, 0))

        tk.Button(buttons, text="Clear", command=self._clear_pins, font=self.FONT_SMALL).pack(side="right")
        tk.Button(buttons, text="Remove", command=self._remove_selected_pin, font=self.FONT_SMALL).pack(side="right", padx=5)
        tk.Button(buttons, text="Restore", command=self._restore_selected_pin, font=self.FONT_SMALL).pack(side="right")

    def _build_right_scroll_panel(self, parent):
        outer = tk.Frame(parent, bg=self.BG)
        outer.pack(fill="both", expand=True, padx=(8, 0))

        self.right_canvas = tk.Canvas(outer, bg=self.BG, highlightthickness=0, bd=0)
        right_scroll = UtilsTools.styled_scrollbar(outer, orient="vertical", command=self.right_canvas.yview)
        self.right_canvas.configure(yscrollcommand=right_scroll.set)

        right_scroll.pack(side="right", fill="y")
        self.right_canvas.pack(side="left", fill="both", expand=True)

        self.right_inner = tk.Frame(self.right_canvas, bg=self.BG)
        self.right_window_id = self.right_canvas.create_window((0, 0), window=self.right_inner, anchor="nw")

        self.right_inner.bind("<Configure>", self._on_right_inner_configure)
        self.right_canvas.bind(
            "<Configure>",
            lambda e: self.right_canvas.itemconfigure(self.right_window_id, width=max(1, e.width - 4))
        )

        self._build_sample_card(self.right_inner)
        self._build_membership_card(self.right_inner)
        self._build_comparison_settings_card(self.right_inner)
        self._build_prototype_card(self.right_inner)

        # A private bindtag makes wheel scrolling work over labels, cards,
        # buttons and editable settings without affecting the image zoom or
        # other PyFCS windows. Newly created controls receive it on resize.
        self._right_wheel_tag = f"PyFCSRightWheel_{id(self)}"
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.win.bind_class(self._right_wheel_tag, sequence,
                                self._on_right_panel_wheel)
        self._install_right_wheel_bindtags()

    def _on_right_inner_configure(self, _event=None):
        try:
            self.right_canvas.configure(scrollregion=self.right_canvas.bbox("all"))
            # Membership rows and threshold controls can be rebuilt at runtime.
            self._install_right_wheel_bindtags()
        except tk.TclError:
            pass

    def _install_right_wheel_bindtags(self):
        """Attach a wheel dispatcher before Tk class bindings in this pane."""
        tag = getattr(self, "_right_wheel_tag", None)
        if not tag:
            return
        widgets = [self.right_canvas]
        while widgets:
            widget = widgets.pop()
            try:
                tags = widget.bindtags()
                if tag not in tags:
                    widget.bindtags((tags[0], tag) + tags[1:])
                widgets.extend(widget.winfo_children())
            except tk.TclError:
                # A dynamic control might be destroyed during a refresh.
                pass

    @staticmethod
    def _wheel_units(event):
        if getattr(event, "num", None) == 4:
            return -1
        if getattr(event, "num", None) == 5:
            return 1
        delta = getattr(event, "delta", 0)
        if not delta:
            return 0
        units = max(1, int(abs(delta) / 120))
        return -units if delta > 0 else units

    @staticmethod
    def _canvas_can_scroll(canvas, units):
        first, last = canvas.yview()
        if units < 0:
            return first > 1e-4
        if units > 0:
            return last < 1 - 1e-4
        return False

    def _on_right_panel_wheel(self, event):
        """Scroll the right pane anywhere, keeping nested memberships usable.

        The membership list consumes the wheel while it can scroll in that
        direction; at its limits, scrolling continues in the outer pane.
        """
        units = self._wheel_units(event)
        if not units:
            return "break"
        try:
            widget = event.widget
            is_membership = False
            holder = getattr(self, "membership_scroll_holder", None)
            while holder is not None and widget is not None:
                if widget == holder:
                    is_membership = True
                    break
                widget = getattr(widget, "master", None)
            if (is_membership and
                    self._canvas_can_scroll(self.membership_canvas, units)):
                self.membership_canvas.yview_scroll(units, "units")
            elif self._canvas_can_scroll(self.right_canvas, units):
                self.right_canvas.yview_scroll(units, "units")
        except tk.TclError:
            pass
        return "break"

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
        sample_info.grid(row=0, column=1, sticky="ew", padx=(0, 8))

        tk.Label(
            sample_info,
            textvariable=self.sample_title_var,
            font=self.FONT_BOLD,
            bg=self.CARD,
            fg=self.TEXT,
            anchor="w",
        ).pack(fill="x")

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

        self.metric_family_combo = UtilsTools.styled_combobox(
            grid,
            textvariable=self.metric_family_var,
            values=self.manager.get_metric_families(),
            state="readonly",
        )
        self.metric_family_combo.grid(row=1, column=0, sticky="ew", pady=(3, 6))

        self.metric_combo = UtilsTools.styled_combobox(
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

        # Match the two-column metric controls above. Custom numeric entries
        # occupy a full-width row below, so they never squeeze the preset.
        threshold_top = tk.Frame(card, bg=self.CARD)
        threshold_top.pack(fill="x")
        threshold_top.columnconfigure(0, weight=1)
        threshold_top.columnconfigure(1, weight=2)
        threshold_type = tk.Frame(threshold_top, bg=self.CARD)
        threshold_type.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        tk.Label(threshold_type, text="Threshold type", font=self.FONT_SMALL_BOLD,
                 bg=self.CARD, fg=self.TEXT).pack(anchor="w")
        self.threshold_mode_combo = UtilsTools.styled_combobox(
            threshold_type, textvariable=self.threshold_mode_var,
            values=["default", "custom"], state="readonly", width=10,
        )
        self.threshold_mode_combo.pack(fill="x", pady=(3, 0))
        self.threshold_dynamic = tk.Frame(threshold_top, bg=self.CARD)
        self.threshold_dynamic.grid(row=0, column=1, sticky="nsew")
        self._threshold_entries_row = tk.Frame(threshold_top, bg=self.CARD)
        self._rebuild_threshold_dynamic_controls()

        self.metric_family_combo.bind("<<ComboboxSelected>>", self._on_metric_family_changed)
        self.metric_combo.bind("<<ComboboxSelected>>", lambda _e: self._threshold_changed())
        self.threshold_mode_combo.bind("<<ComboboxSelected>>", lambda _e: self._threshold_mode_changed())

    def _build_membership_card(self, parent):
        card = self._card(parent, "Membership Degrees")
        card.pack(fill="x", pady=(0, 8))

        top = tk.Frame(card, bg=self.CARD)
        top.pack(fill="x", pady=(0, 5))
        winner_label = tk.Label(
            top, textvariable=self.winner_summary_var,
            bg=self.CARD, fg=self.BLUE, font=self.FONT_BOLD,
            anchor="center", justify="center", wraplength=390,
        )
        winner_label.pack(fill="x")
        top.bind("<Configure>", lambda e: winner_label.configure(
            wraplength=max(160, e.width - 12)))

        space = getattr(self.app, "fuzzy_color_space", None)
        granular = bool(getattr(space, "is_granular", False))
        self.tconorm_buttons = {}

        # Show T-conorm in every space so the card keeps the same layout.
        # An atomic category has nothing to aggregate: the dropdown remains
        # visible but disabled, rather than suggesting a change to its μ.
        aggregation = tk.Frame(card, bg=self.CARD)
        aggregation.pack(fill="x", pady=(0, 4))
        self._membership_options_bar = aggregation
        self._membership_options_inner = tk.Frame(aggregation, bg=self.CARD)
        self._membership_options_inner.pack(anchor="center")
        aggregation_controls = self._aggregation_controls = tk.Frame(
            self._membership_options_inner, bg=self.CARD)
        aggregation_controls.grid(row=0, column=0)
        tk.Label(aggregation_controls, text="T-conorm", font=self.FONT_SMALL_BOLD,
                 bg=self.CARD, fg=self.MUTED).pack(side="left", padx=(0, 8))
        self.tconorm_combo = UtilsTools.styled_combobox(
            aggregation_controls, textvariable=self.tconorm_display_var,
            values=("Bounded Sum", "Max"), width=12,
            state="readonly" if granular else "disabled")
        self.tconorm_combo.pack(side="left")
        self.tconorm_combo.bind("<<ComboboxSelected>>", self._on_tconorm_combo_changed)
        self._sync_tconorm_buttons()

        # Explore the hierarchy without changing the root-category winner.
        self.membership_level_row = tk.Frame(self._membership_options_inner, bg=self.CARD)
        level_controls = tk.Frame(self.membership_level_row, bg=self.CARD)
        level_controls.pack(anchor="center")
        tk.Label(level_controls, text="Explore level", font=self.FONT_SMALL_BOLD,
                 bg=self.CARD, fg=self.MUTED).pack(side="left", padx=(0, 6))
        self.membership_level_combo = UtilsTools.styled_combobox(
            level_controls, textvariable=self.membership_level_var,
            values=("Root categories",), state="readonly", width=14)
        self.membership_level_combo.pack(side="left")
        self.membership_level_combo.bind("<<ComboboxSelected>>", self._on_membership_level_changed)
        self._membership_level_visible = bool(granular and space.hierarchy)
        self._layout_membership_options()
        aggregation.bind("<Configure>", self._layout_membership_options)

        # Keep the zero-membership switch beneath the aggregation choice.
        options = self._membership_zero_row = tk.Frame(card, bg=self.CARD)
        options.pack(fill="x", pady=(0, 5))
        tk.Checkbutton(
            options, text="Show zero memberships",
            variable=self.show_zero_memberships_var,
            command=self._populate_memberships,
            bg=self.CARD, activebackground=self.CARD,
            fg=self.MUTED, font=self.FONT_SMALL, bd=0,
            highlightthickness=0, cursor="hand2",
        ).pack(anchor="center")

        # Compact but independently scrollable: large spaces remain usable.
        holder = tk.Frame(card, bg=self.CARD, height=212 if granular else 148)
        self.membership_scroll_holder = holder
        holder.pack(fill="x")
        holder.pack_propagate(False)

        self.membership_canvas = tk.Canvas(holder, bg=self.CARD, highlightthickness=0, bd=0)
        scroll = UtilsTools.styled_scrollbar(holder, orient="vertical", command=self.membership_canvas.yview)
        self.membership_canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.membership_canvas.pack(side="left", fill="both", expand=True)
        self.membership_inner = tk.Frame(self.membership_canvas, bg=self.CARD)
        self.membership_window_id = self.membership_canvas.create_window(
            (0, 0), window=self.membership_inner, anchor="nw")
        self.membership_inner.bind(
            "<Configure>", lambda _e: self.membership_canvas.configure(
                scrollregion=self.membership_canvas.bbox("all")))
        self.membership_canvas.bind(
            "<Configure>", lambda e: self.membership_canvas.itemconfigure(
                self.membership_window_id, width=max(1, e.width - 3)))
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.membership_canvas.bind(sequence, self._on_membership_wheel)

    def _layout_membership_options(self, event=None):
        """Keep both controls side by side, falling back only on narrow panes."""
        level = self.membership_level_row
        if not self._membership_level_visible:
            level.grid_remove()
            return
        available = event.width if event is not None else self._membership_options_bar.winfo_width()
        required = self._aggregation_controls.winfo_reqwidth() + level.winfo_reqwidth() + 12
        # At construction the bar is not yet mapped. Configure will refine it.
        inline = available <= 1 or available >= required
        row, column = (0, 1) if inline else (1, 0)
        old = level.grid_info()
        if not old or (int(old["row"]), int(old["column"])) != (row, column):
            level.grid(row=row, column=column, padx=(12, 0) if inline else 0,
                       pady=(0, 0) if inline else (4, 0))

    @staticmethod
    def _tconorm_caption(mode):
        return {"MAX": "Max", "BOUNDED_SUM": "Bounded Sum"}.get(
            str(mode).strip().upper(), "Bounded Sum")

    def _on_tconorm_combo_changed(self, _event=None):
        mode = {"Bounded Sum": "BOUNDED_SUM", "Max": "MAX"}.get(self.tconorm_display_var.get())
        if mode is not None:
            self._set_tconorm_choice(mode)
        else:
            self._sync_tconorm_buttons()

    def _sync_tconorm_buttons(self):
        """Synchronize the dropdown, including after a rejected change."""
        self.tconorm_display_var.set(self._tconorm_caption(self.tconorm_var.get()))

    def _set_tconorm_choice(self, mode):
        if self.tconorm_var.get().upper() == mode:
            return
        self.tconorm_var.set(mode)
        self._on_tconorm_changed()
        self._sync_tconorm_buttons()

    def _on_membership_wheel(self, event):
        # Existing row bindings stay compatible; the shared dispatcher also
        # lets the outer pane continue scrolling at the list boundaries.
        return self._on_right_panel_wheel(event)

    def _build_prototype_card(self, parent):
        self.prototype_card = self._card(parent, "Color Match")
        self.prototype_card.pack(fill="x", pady=(0, 8))

        # Only show the automatic-reference action when there is a manual choice.
        reference_header = self._reference_header = tk.Frame(self.prototype_card, bg=self.CARD)
        self.use_winner_button = tk.Button(
            reference_header, text="↺ Highest Degree", command=self._select_winner_prototype,
            font=self.FONT_SMALL_BOLD, bg=self.BLUE_SOFT, fg=self.BLUE,
            activebackground=self.BLUE_SOFT, activeforeground=self.BLUE,
            relief="flat", bd=0, highlightthickness=0, padx=8, pady=3, cursor="hand2")
        color_strip = self._comparison_strip = tk.Frame(
            self.prototype_card, bg=self.PANEL, highlightthickness=1, highlightbackground=self.BORDER)
        color_strip.pack(fill="x")
        pair = self._comparison_pair = tk.Frame(color_strip, bg=self.PANEL)
        pair.pack(fill="x", padx=8, pady=8)
        pair.columnconfigure(0, weight=1, uniform="color_pair")
        pair.columnconfigure(2, weight=1, uniform="color_pair")
        sample_column = tk.Frame(pair, bg=self.PANEL)
        reference_column = tk.Frame(pair, bg=self.PANEL)
        sample_column.grid(row=0, column=0, sticky="nsew")
        reference_column.grid(row=0, column=2, sticky="nsew")
        self._comparison_columns = (sample_column, reference_column)
        for column, caption in ((sample_column, "Sample"), (reference_column, "Reference")):
            tk.Label(column, text=caption, bg=self.PANEL, fg=self.TEXT,
                     font=self.FONT_SMALL_BOLD).pack(fill="x", pady=(0, 5))
        self.comparison_sample_swatch = tk.Canvas(sample_column, width=72, height=64,
            bg=self.PANEL, highlightthickness=0, bd=0)
        self.comparison_sample_swatch.pack(anchor="center")
        self.comparison_sample_rect = self.comparison_sample_swatch.create_rectangle(
            3, 3, 69, 61, fill="#d9dde3", outline="#9ca3af")
        self.proto_swatch = tk.Canvas(reference_column, width=72, height=64,
            bg=self.PANEL, highlightthickness=0, bd=0)
        self.proto_swatch.pack(anchor="center")
        self.proto_swatch_rect = self.proto_swatch.create_rectangle(
            3, 3, 69, 61, fill="#d9dde3", outline="#9ca3af")
        tk.Label(pair, text="→", bg=self.PANEL, fg=self.MUTED,
                 font=("Segoe UI", 14)).grid(row=0, column=1, sticky="n", padx=4, pady=(32, 0))
        # Keep each color's numeric coordinates directly underneath it.
        for index, (name_var, coordinate_vars) in enumerate((
            (self.sample_title_var, (self.sample_lab_var, self.sample_rgb_var, self.sample_hex_var)),
            (self.proto_name_var, (self.proto_lab_var, self.proto_rgb_var, self.proto_hex_var)),
        )):
            col = index * 2
            name = tk.Label(pair, textvariable=name_var, bg=self.PANEL, fg=self.TEXT,
                            font=self.FONT_SMALL_BOLD, justify="center", wraplength=145)
            name.grid(row=1, column=col, sticky="ew", pady=(3, 4))
            for row, var in enumerate(coordinate_vars, start=2):
                tk.Label(pair, textvariable=var, bg=self.PANEL, fg=self.MUTED,
                         font=self.FONT_SMALL, justify="center", wraplength=155).grid(row=row, column=col, sticky="ew")
        if getattr(self.app.fuzzy_color_space, "is_granular", False):
            path = tk.Label(color_strip, textvariable=self.proto_category_var,
                            bg=self.PANEL, fg=self.MUTED, font=self.FONT_SMALL,
                            anchor="center", justify="center", wraplength=360)
            path.pack(fill="x", padx=8, pady=(0, 7))
            color_strip.bind("<Configure>", lambda e: path.configure(wraplength=max(100, e.width - 20)))

        # One status row makes the outcome readable without an oversized
        # colored box or a redundant second line.
        self.result_card = tk.Frame(
            self.prototype_card, bg=self.SOFT,
            highlightthickness=1, highlightbackground=self.BORDER,
        )
        self.result_card.pack(fill="x", pady=(10, 0))
        self.result_accent = tk.Frame(self.result_card, width=4, bg=self.MUTED)
        self.result_accent.pack(side="left", fill="y")
        self.result_accent.pack_propagate(False)
        self.result_body = tk.Frame(self.result_card, bg=self.SOFT)
        self.result_body.pack(side="left", fill="both", expand=True, padx=9, pady=9)
        self.result_header = tk.Frame(self.result_body, bg=self.SOFT)
        self.result_header.pack(fill="x")
        self.result_header.columnconfigure(1, weight=1)
        self.result_dot = tk.Canvas(
            self.result_header, width=16, height=16,
            bg=self.SOFT, highlightthickness=0, bd=0,
        )
        self.result_dot.grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.result_dot_oval = self.result_dot.create_oval(
            3, 3, 13, 13, fill="#9ca3af", outline="#9ca3af")
        self.result_status_label = tk.Label(
            self.result_header, textvariable=self.comparison_status_var,
            bg=self.SOFT, fg=self.TEXT, font=self.FONT_BOLD,
            anchor="w", justify="left",
        )
        self.result_status_label.grid(row=0, column=1, sticky="ew")
        self.result_value_label = tk.Label(
            self.result_header, textvariable=self.comparison_value_var,
            bg=self.SOFT, fg=self.TEXT, font=self.FONT_BOLD,
            anchor="e", justify="right", wraplength=190,
        )
        self.result_value_label.grid(row=0, column=2, sticky="e", padx=(8, 0))

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
        self.details_button.pack(anchor="center", pady=(7, 0))

        self.details_frame = tk.Frame(self.prototype_card, bg=self.PANEL, bd=1, relief="solid")
        self.details_label = tk.Label(
            self.details_frame,
            textvariable=self.details_text_var,
            bg=self.PANEL,
            fg=self.TEXT,
            font=("Consolas", 8),
            anchor="w",
            justify="left",
            wraplength=390,
        )
        self.details_label.pack(fill="x", padx=10, pady=9)
        self.details_frame.bind("<Configure>", lambda e: self.details_label.configure(
            wraplength=max(160, e.width - 24)))

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
            self._cancel_pending_live_inspection()
            self.current_source_key = None
            if self._source_order:
                self._switch_source(self._source_order[0], restore_sample=True)
            else:
                self.source_var.set("")
                self._current_sample = None
                self._selected_category_label = None
                self._selected_proto_label = None
                self._category_locked = self._reference_locked = False
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

        sample = self._build_sample(
            source_key=source_key,
            x=int(info.get("x", 0)),
            y=int(info.get("y", 0)),
            rgb=rgb,
            lab=lab,
            is_average=bool(info.get("is_average", False)),
            selection_info=selection_info,
        )
        # Initial handoff may contain a pixel from the original workspace.
        # Only trust native RGB when it agrees with the measured LAB value.
        pil = self._current_pil()
        if pil is not None and not sample["is_average"]:
            x, y = sample["x"], sample["y"]
            if 0 <= x < pil.width and 0 <= y < pil.height:
                r, g, b, alpha = self._read_pixel_rgba(pil, x, y)
                exact = (r, g, b)
                if alpha and np.allclose(UtilsTools.rgb_to_lab(exact), lab, rtol=0, atol=1e-4):
                    sample["native_rgb"] = exact
                    sample["rgb"] = exact
                    sample["hex"] = UtilsTools.rgb_to_hex(exact).upper()
        return sample

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
        self._cancel_pending_live_inspection()
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
            self._selected_category_label = None
            self._reference_locked = False
            self._category_locked = False
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

    def _redraw_sample_overlay(self):
        """Update markers without resizing/copying the underlying image."""
        try:
            self.image_canvas.delete("sample_marker")
            self.image_canvas.delete("sample_tooltip")
            self.image_canvas.delete("roi_preview")
            self._draw_sample_marker()
            self._draw_roi_preview()
        except tk.TclError:
            pass

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
            text = "Move cursor: inspect pixel · Right-drag: pan · Wheel: zoom"
        else:
            drag_text = "filtered mean (ROI)" if self._active_lab_filters() else "mean color (ROI)"
            text = f"Click: sample pixel · Drag: {drag_text} · Right-drag: pan · Wheel: zoom"

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

        self._cancel_pending_live_inspection()
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
                self.image_canvas.delete("roi_preview")
                self._draw_roi_preview()

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
            self._redraw_sample_overlay()
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
        self._live_pending_xy = (self.current_source_key, point)
        if self._live_after_id is not None:
            return

        self._live_after_id = self.win.after(65, self._flush_live_inspection)

    def _cancel_pending_live_inspection(self):
        pending = self._live_after_id
        self._live_after_id = None
        self._live_pending_xy = None
        if pending is not None:
            try:
                self.win.after_cancel(pending)
            except tk.TclError:
                pass

    def _flush_live_inspection(self):
        self._live_after_id = None
        pending = self._live_pending_xy
        self._live_pending_xy = None
        if pending is None or self.inspection_mode_var.get() != "live":
            return
        key, point = pending
        if key != self.current_source_key:
            return
        self._inspect_pixel(point[0], point[1], show_tooltip=False)

    def _read_pixel_rgba(self, pil, x, y):
        """Read one pixel without converting the entire image on every move.

        RGB/RGBA are the common paths in Live mode. Other Pillow modes may
        need a conversion to preserve palette/alpha semantics; reuse that
        converted view for subsequent samples from the same source.
        """
        coords = (int(x), int(y))
        if pil.mode == "RGB":
            return (*pil.getpixel(coords), 255)
        if pil.mode == "RGBA":
            return pil.getpixel(coords)

        source = self._sources.get(self.current_source_key)
        if source is None:
            return pil.convert("RGBA").getpixel(coords)
        converted = source.get("_inspection_rgba")
        if converted is None:
            converted = pil.convert("RGBA")
            source["_inspection_rgba"] = converted
        return converted.getpixel(coords)

    def _inspect_pixel(self, x, y, show_tooltip=False):
        pil = self._current_pil()
        if pil is None or self.current_source_key is None:
            return

        if not (0 <= x < pil.width and 0 <= y < pil.height):
            return
        r, g, b, a = self._read_pixel_rgba(pil, x, y)
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
        sample["native_rgb"] = rgb
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

        filters = self._active_lab_filters()
        mean_lab_arr, used_count, total_count = UtilsTools.mean_lab_of_pil_roi(
            pil, (left, top, right + 1, bottom + 1), filters
        )
        if total_count <= 0:
            return

        if used_count <= 0 or mean_lab_arr is None:
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

        # Scientific result is the mean of individual CIELAB pixels.
        mean_lab = tuple(float(v) for v in mean_lab_arr[:3])
        # sRGB is only a display approximation, never the source for LAB.
        mean_rgb = tuple(UtilsTools.lab_to_rgb(mean_lab))

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

    def _reference_index(self):
        """Cache actual prototypes and the semantic topology per model."""
        space = getattr(self.app, "fuzzy_color_space", None)
        if space is self._reference_space and self._reference_space_id is not None:
            return
        self._reference_space = space
        self._reference_space_id = id(space)
        self._reference_categories = {}
        self._reference_labels = {}
        self._reference_rgb_cache = {}
        self._reference_hex_cache = {}
        self._membership_topology = {}
        self._membership_roots = ()
        self._membership_descendants = {}
        self._membership_last_key = None
        self._membership_last_snapshot = None
        self._membership_cache = OrderedDict()
        self._nearest_cache = OrderedDict()
        self._membership_cache_limit = 128
        self._expanded_membership_categories.clear()
        self._membership_levels = (0,)
        self._membership_frontiers = {}
        if space is None:
            return
        granular = bool(getattr(space, "is_granular", False))
        groups = ((cat.label, cat.prototypes) for cat in space.categories) if granular else (
            (p.label, (p,)) for p in space.prototypes)
        for category, protos in groups:
            for proto in protos:
                lab = tuple(float(x) for x in space.lab_from_model(proto.positive))
                self._reference_labels[proto.label] = (category, lab)
                if space.color_space == "RGB":
                    self._reference_rgb_cache[proto.label] = tuple(int(round(x)) for x in proto.positive)
        self._membership_roots = tuple(space.get_root_categories())
        for category in space.get_all_category_labels():
            labels = tuple(p.label for p in space.get_descendant_granules(category))
            self._membership_descendants[category] = labels
            self._reference_categories[category] = [(g, self._reference_labels[g][1]) for g in labels]
            self._membership_topology[category] = tuple(space.get_category_children(category)) if granular else ()
        # Bound cache storage even for large/deep trees. No color quantization.
        entries = len(self._reference_labels) + sum(
            1 + len(labels) for labels in self._membership_descendants.values())
        self._membership_cache_limit = max(1, min(128, 32768 // max(1, entries)))
        # Stop at the first unchanged frontier. Terminal branches stay in scope.
        levels = [0]
        previous = self._membership_frontiers[0] = space.get_categories_at_level(0)
        for level in range(1, len(self._membership_topology)+1):
            current = space.get_categories_at_level(level)
            if current == previous:
                break
            levels.append(level)
            self._membership_frontiers[level] = current
            previous = current
        self._membership_levels = tuple(levels)
        if hasattr(self, "membership_level_combo"):
            options = ("Root categories",) + tuple(f"Level {i}" for i in levels[1:])
            self.membership_level_combo.configure(values=options)
            self.membership_level_var.set(options[0])
            self._membership_level_visible = len(levels) > 1
            self._layout_membership_options()

    def _membership_level(self):
        value = self.membership_level_var.get()
        return int(value.split()[-1]) if value.startswith("Level ") else 0

    def _membership_snapshot(self, lab, *, rgb=None):
        self._reference_index()
        space = self.app.fuzzy_color_space
        native = rgb is not None and getattr(space, "is_granular", False) and space.color_space == "RGB"
        value, mode = (tuple(rgb), "RGB") if native else (tuple(lab), "LAB")
        key = (id(space), getattr(space, "tconorm", None), mode, value)
        if key != self._membership_last_key:
            cache = self._membership_cache
            if key in cache:
                cache.move_to_end(key)
                snapshot = cache[key]
            else:
                snapshot = inspection_membership_snapshot(
                    space, lab, self.manager, 0, input_value=value,
                    input_space=mode, descendants=self._membership_descendants,
                    frontier=self._membership_frontiers.get(0))
                cache[key] = snapshot
                while len(cache) > self._membership_cache_limit:
                    cache.popitem(last=False)
            self._membership_last_snapshot = snapshot
            self._membership_last_key = key
        return self._membership_last_snapshot

    def _refresh_sample_memberships(self, sample):
        snapshot = self._membership_snapshot(sample["lab"], rgb=sample.get("native_rgb"))
        sample.update(snapshot)
        return sample

    def _on_membership_level_changed(self, _event=None):
        # Navigation only. The reported winner, automatic reference and pins
        # always refer to root categories, regardless of the explored depth.
        depth = self._membership_level()
        opened = set()
        stack = [(('category', label),) for label in reversed(self._membership_roots)]
        while stack:
            path = stack.pop()
            if len(path) > depth:
                continue
            children = self._membership_topology.get(path[-1][1], ())
            if children:
                opened.add(path)
                stack.extend(path + (child,) for child in reversed(children)
                             if child[0] == 'category')
        self._expanded_membership_categories = opened
        self._populate_memberships()

    def _closest_granule(self, category, lab):
        """Choose a REAL prototype by the currently active comparison metric."""
        self._reference_index()
        candidates = self._reference_categories.get(category, [])
        metric = self.metric_var.get() if hasattr(self, "metric_var") else "CIEDE2000"
        key = (category, tuple(lab), metric)
        cache = self._nearest_cache
        if key in cache:
            cache.move_to_end(key)
            return cache[key]
        label = nearest_granule(self.manager, candidates, lab, metric)
        cache[key] = label
        if len(cache) > 256:
            cache.popitem(last=False)
        return label

    def _auto_select_reference(self, *, reset=False):
        sample = self._current_sample
        if sample is None:
            self._selected_proto_label = None
            self._selected_category_label = None
            return
        self._reference_index()
        winner = sample.get("winner_label")
        category = self._selected_category_label if self._category_locked else winner
        if category not in self._reference_categories:
            category = winner
            self._category_locked = False
        if reset:
            self._category_locked = False
            self._reference_locked = False
            category = winner
        self._selected_category_label = category
        if not (self._reference_locked and
                self._selected_proto_label in self._reference_labels and
                self._selected_proto_label in self._membership_descendants.get(category, ())):
            self._reference_locked = False
            self._selected_proto_label = (self._closest_granule(category, sample["lab"])
                                          if category is not None else None)

    def _build_sample(self, source_key, x, y, rgb, lab, is_average=False, selection_info=None):
        result = {
            "source_key": source_key,
            "x": int(x),
            "y": int(y),
            "rgb": tuple(int(v) for v in rgb[:3]),
            "lab": tuple(float(v) for v in lab[:3]),
            "hex": UtilsTools.rgb_to_hex(rgb).upper(),
            "is_average": bool(is_average),
            "selection_info": selection_info,
        }
        return result

    def _set_current_sample(self, sample, remember=True, show_tooltip=False):
        # Pins/last-samples may contain stale degrees after an operator change.
        self._refresh_sample_memberships(sample)
        self._current_sample = sample
        key = sample.get("source_key")
        if key in self._sources and key != self.current_source_key:
            self._switch_source(key, restore_sample=False)
        if remember and key:
            self._last_sample[key] = dict(sample)
        self._tooltip_enabled = bool(show_tooltip)
        self._auto_select_reference()
        self._update_sample_ui()
        self._populate_memberships()
        self._update_prototype_ui()
        # A new sample does not change the image crop, zoom or pan. Repaint
        # only its marker, avoiding PIL resize + ImageTk.PhotoImage in Live mode.
        if self._render_transform is not None and key == self.current_source_key:
            self._redraw_sample_overlay()
        else:
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
        self.comparison_sample_swatch.itemconfig(
            self.comparison_sample_rect, fill="#d9dde3")

        self.winner_summary_var.set("Highest Membership Degree: —")
        self._clear_membership_rows()

        self.proto_category_var.set("Category: —")
        self.proto_name_var.set("—")
        self.proto_lab_var.set("LAB: —")
        self.proto_rgb_var.set("RGB: —")
        self.proto_hex_var.set("HEX: —")
        self.proto_swatch.itemconfig(self.proto_swatch_rect, fill="#d9dde3")
        self.comparison_status_var.set("")
        self.comparison_value_var.set("Select a sample to compare")
        self.details_text_var.set("")
        self.use_winner_button.pack_forget()
        self._reference_header.pack_forget()
        self._apply_result_style("unavailable")

    def _update_sample_ui(self):
        s = self._current_sample
        if not s:
            self._clear_sample_ui()
            return

        selection = s.get("selection_info")
        if s.get("is_average") and selection and selection.get("type") == "roi":
            self.sample_title_var.set("ROI average")
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
            self.sample_title_var.set("Single pixel")
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
        self.comparison_sample_swatch.itemconfig(
            self.comparison_sample_rect, fill=s["hex"])

        if s.get("winner_label") is not None:
            self.winner_summary_var.set(
                f"Highest Membership Degree: {s['winner_label']} · μ = {s['winner_mu']:.4f}"
            )
        else:
            self.winner_summary_var.set("Highest Membership Degree: — · no positive membership")

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
            if self._tooltip_after_id is not None:
                self.win.after_cancel(self._tooltip_after_id)
            self._tooltip_after_id = self.win.after(1700, self._hide_tooltip)

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
        self._tooltip_after_id = None
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
        self._membership_shape = None
        self._membership_display_order = ()

    def _make_membership_row(self, path):
        kind, label = path[-1]
        category = kind == "category"
        children = self._membership_topology.get(label, ()) if category else ()
        row = tk.Frame(self.membership_inner, bg=self.CARD, cursor="hand2", height=28)
        row.pack_propagate(False)
        gutter = tk.Canvas(row, width=min(len(path)-1, 12)*13+19, height=28,
                           bg=self.CARD, highlightthickness=0, bd=0)
        gutter.pack(side="left", fill="y")
        if children:
            gutter.tag_bind("tree_toggle", "<Button-1>",
                            lambda _e, p=path: (self._toggle_membership_category(p), "break")[1])
        swatch = tk.Canvas(row, width=19, height=19, bg=self.CARD, highlightthickness=0, bd=0)
        swatch.pack(side="left", padx=(1, 5))
        refs = self._membership_descendants.get(label, ()) if category else (label,)
        swatch_label = refs[0] if refs else label
        rectangle = swatch.create_rectangle(2, 2, 17, 17, fill=self._proto_hex(swatch_label), outline="#9ca3af")
        value = tk.Label(row, text="μ = 0.0000", bg=self.CARD, fg=self.TEXT,
                         font=self.FONT_SMALL, width=10, anchor="e")
        value.pack(side="right", padx=(3, 3))
        bar = ttk.Progressbar(row, orient="horizontal", mode="determinate", maximum=100, value=0, length=70)
        bar.pack(side="right", padx=(3, 0))
        name = tk.Label(row, text=label, bg=self.CARD, fg=self.TEXT,
                        font=self.FONT_BOLD if category else self.FONT, anchor="w", cursor="hand2")
        name.pack(side="left", fill="x", expand=True)
        callback = (lambda _e, c=label: self._select_category(c)) if category else (
            lambda _e, c=path[-2][1], g=label: self._select_granule(c, g))
        for widget in (row, swatch, name, bar, value):
            widget.bind("<Button-1>", callback)
        for widget in (row, swatch, name, bar, value, gutter):
            for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                widget.bind(sequence, self._on_membership_wheel)
        return {"row": row, "bar": bar, "value": value,
                "swatch": swatch, "rectangle": rectangle, "name": name,
                "gutter": gutter, "degree": None, "guides": None, "highlight": None}

    def _ensure_membership_rows(self):
        self._reference_index()
        expected = self._reference_space_id
        if expected != getattr(self, "_membership_shape", None):
            self._clear_membership_rows()
            self._membership_shape = expected

    def _membership_visible_paths(self, sample, show_zeros):
        categories = sample.get("categories", {})
        granules = sample.get("granules", {})
        winner = sample.get("winner_label")
        def degree(ref):
            kind, label = ref
            return float(categories.get(label, {}).get("degree", 0.0) if kind == "category" else granules.get(label, 0.0))
        def siblings(refs):
            return sorted((r for r in refs if show_zeros or degree(r) > 0),
                          key=lambda r: (-degree(r), r != ("category", winner)))
        roots = siblings(("category", label) for label in self._membership_roots)
        stack = [((ref,), (), False) for ref in reversed(roots)]
        result = []
        while stack:
            path, continuations, more = stack.pop()
            kind, label = path[-1]
            opened = path in self._expanded_membership_categories
            children = siblings(self._membership_topology.get(label, ())) if opened and kind == "category" else []
            # The selected winning frontier is not expanded automatically: keep user state.
            result.append((path, degree(path[-1]), continuations, more, bool(children and opened)))
            if opened:
                for i in reversed(range(len(children))):
                    stack.append((path+(children[i],), continuations+(more,), i < len(children)-1))
        return result

    def _draw_membership_guides(self, ctrl, path, continuations, more, opened):
        kind, label = path[-1]
        expandable = kind == "category" and bool(self._membership_topology.get(label))
        expanded = path in self._expanded_membership_categories
        signature = (continuations, more, opened, expandable, expanded)
        if ctrl["guides"] == signature:
            return
        ctrl["guides"] = signature
        canvas = ctrl["gutter"]
        canvas.delete("all")
        depth = min(len(path)-1, 12)
        x_node = depth*13+8
        for i, continues in enumerate(continuations[-depth:] if depth else ()):
            x = i*13+8
            if i == depth-1:
                canvas.create_line(x, 0, x, 28 if more else 14, fill="#c9bfda")
                canvas.create_line(x, 14, x_node-4 if expandable else x_node+10, 14, fill="#c9bfda")
            elif continues:
                canvas.create_line(x, 0, x, 28, fill="#c9bfda")
        if opened:
            canvas.create_line(x_node, 19, x_node, 28, fill="#c9bfda")
        if expandable:
            canvas.create_text(x_node, 14, text="▾" if expanded else "▸",
                               font=self.FONT_BOLD, fill=self.BLUE, tags=("tree_toggle",))

    def _populate_memberships(self):
        sample = self._current_sample
        if not sample:
            self._clear_membership_rows()
            return
        self._ensure_membership_rows()
        items = self._membership_visible_paths(sample, bool(self.show_zero_memberships_var.get()))
        paths = tuple(item[0] for item in items)
        for path, degree, guides, more, opened in items:
            ctrl = self._membership_controls.get(path)
            if ctrl is None:
                ctrl = self._membership_controls[path] = self._make_membership_row(path)
                self._membership_rows[path] = ctrl["row"]
            if ctrl["degree"] != degree:
                ctrl["degree"] = degree
                ctrl["bar"].configure(value=max(0., min(100., degree*100)))
                ctrl["value"].configure(text=f"μ = {degree:.4f}")
            self._draw_membership_guides(ctrl, path, guides, more, opened)
        if paths != self._membership_display_order:
            keep = set(paths)
            for path in self._membership_display_order:
                if path not in keep:
                    self._membership_controls[path]["row"].pack_forget()
            # Reorder only the rows that are not already in the right position.
            packed = self.membership_inner.pack_slaves()
            previous = None
            for target, path in enumerate(paths):
                row = self._membership_controls[path]["row"]
                if target >= len(packed) or packed[target] is not row:
                    if previous is not None:
                        row.pack(fill="x", after=previous)
                    elif packed:
                        row.pack(fill="x", before=packed[0])
                    else:
                        row.pack(fill="x")
                    if row in packed:
                        packed.remove(row)
                    packed.insert(target, row)
                previous = row
            self._membership_display_order = paths
        self._highlight_membership_selection()

    def _toggle_membership_category(self, path):
        if isinstance(path, str):
            path = (("category", path),)
        if path in self._expanded_membership_categories:
            self._expanded_membership_categories.discard(path)
        else:
            self._expanded_membership_categories.add(path)
        self._populate_memberships()

    def _highlight_membership_selection(self):
        for path in self._membership_display_order:
            ctrl = self._membership_controls[path]
            kind, label = path[-1]
            selected = (label == self._selected_category_label if kind == "category" else
                        self._reference_locked and label == self._selected_proto_label and ("category", self._selected_category_label) in path[:-1])
            bg = self.BLUE_SOFT if selected else self.CARD
            if ctrl["highlight"] != bg:
                self._highlight_row(ctrl["row"], bg)
                ctrl["highlight"] = bg

    def _highlight_row(self, row, background):
        try:
            row.configure(bg=background)
            for widget in row.winfo_children():
                if isinstance(widget, (tk.Label, tk.Canvas)):
                    widget.configure(bg=background)
        except tk.TclError:
            pass

    def _select_category(self, label):
        if label not in self._reference_categories or not self._current_sample:
            return
        self._selected_category_label = label
        self._category_locked = True
        self._reference_locked = False
        self._auto_select_reference()
        self._highlight_membership_selection()
        self._update_prototype_ui()

    def _select_granule(self, category, label):
        if label not in self._membership_descendants.get(category, ()) or not self._current_sample:
            return
        self._selected_category_label = category
        self._selected_proto_label = label
        self._category_locked = True
        self._reference_locked = True
        self._highlight_membership_selection()
        self._update_prototype_ui()

    def _select_prototype(self, label):
        """Preserve external callbacks; labels may be categories or granules."""
        self._reference_index()
        if label in self._reference_categories:
            self._select_category(label)
        elif label in self._reference_labels:
            self._select_granule(self._reference_labels[label][0], label)

    def _select_winner_prototype(self):
        self._auto_select_reference(reset=True)
        self._highlight_membership_selection()
        self._update_prototype_ui()

    def _proto_lab(self, label):
        self._reference_index()
        found = self._reference_labels.get(label)
        if found is not None:
            return found[1]
        return None

    def _proto_rgb(self, label):
        self._reference_index()
        cache = self._reference_rgb_cache
        if label not in cache:
            lab = self._proto_lab(label)
            if lab is None:
                rgb = (200, 200, 200)
            else:
                try:
                    rgb = tuple(int(v) for v in UtilsTools.lab_to_rgb(lab))
                except (ValueError, TypeError):
                    rgb = (200, 200, 200)
            cache[label] = rgb
        return cache[label]

    def _proto_hex(self, label):
        self._reference_index()
        cache = self._reference_hex_cache
        if label not in cache:
            cache[label] = UtilsTools.rgb_to_hex(self._proto_rgb(label)).upper()
        return cache[label]

    def _update_prototype_ui(self):
        sample = self._current_sample
        self._reference_index()
        label = self._selected_proto_label
        if not sample or not label or label not in self._reference_labels:
            self.proto_category_var.set("Category: —")
            self.proto_name_var.set("—")
            self.proto_lab_var.set("LAB: —")
            self.proto_rgb_var.set("RGB: —")
            self.proto_hex_var.set("HEX: —")
            self.proto_swatch.itemconfig(self.proto_swatch_rect, fill="#d9dde3")
            self.comparison_status_var.set("")
            self.comparison_value_var.set("No valid reference selected")
            self.details_text_var.set("")
            self.use_winner_button.pack_forget()
            self._reference_header.pack_forget()
            self._apply_result_style("unavailable")
            return

        owner, proto_lab = self._reference_labels[label]
        category = self._selected_category_label or owner
        self.proto_category_var.set(f"Category: {category}" + (f" · {owner}" if owner != category else ""))
        self.proto_name_var.set(label)
        if self._category_locked or self._reference_locked:
            if not self.use_winner_button.winfo_manager():
                self._reference_header.pack(fill="x", before=self._comparison_strip, pady=(0, 5))
                self.use_winner_button.pack(side="right")
        else:
            self.use_winner_button.pack_forget()
            self._reference_header.pack_forget()
        rgb = self._proto_rgb(label)
        self.proto_lab_var.set(f"LAB: {proto_lab[0]:.2f}, {proto_lab[1]:.2f}, {proto_lab[2]:.2f}")
        self.proto_rgb_var.set(f"RGB: {rgb[0]}, {rgb[1]}, {rgb[2]}")
        self.proto_hex_var.set(f"HEX: {self._proto_hex(label)}")
        self.proto_swatch.itemconfig(self.proto_swatch_rect, fill=self._proto_hex(label))
        self._refresh_comparison_result()

    def _refresh_comparison_result(self):
        sample = self._current_sample
        label = self._selected_proto_label
        proto_lab = self._proto_lab(label) if label is not None else None
        if not sample or proto_lab is None:
            self.comparison_status_var.set("")
            self.comparison_value_var.set("Comparison unavailable")
            self.details_text_var.set("")
            self._apply_result_style("unavailable")
            return
        settings = self.app.threshold_settings
        metric = settings.get("metric", "CIEDE2000")
        evaluation = self.manager.evaluate_color_difference_threshold(
            sample_lab=sample["lab"], prototype_lab=proto_lab,
            metric=metric, threshold_settings=settings)
        self.comparison_status_var.set(evaluation.get("evaluation", "Comparison"))
        self.comparison_value_var.set(evaluation.get("detail", "Metric not available"))
        self._apply_result_style(evaluation.get("status", "unavailable"))
        summary = str(evaluation.get("summary_visual", evaluation.get("summary", ""))).strip()
        if summary:
            lines = summary.splitlines()
            detail = "\n".join(lines[1:]).strip()
        else:
            detail = ""
        if not detail:
            try:
                detail = self.manager.format_component_summary(
                    sample["lab"], proto_lab, metric).strip()
            except Exception:
                detail = "No detailed comparison available."
        self.details_text_var.set(detail)

    def _on_tconorm_changed(self, _event=None):
        self._sync_tconorm_buttons()
        space = getattr(self.app, "fuzzy_color_space", None)
        if not getattr(space, "is_granular", False):
            return
        operator = self.tconorm_var.get().strip().lower()
        if operator == space.tconorm:
            return
        if getattr(self.app, "_has_any_active_job", lambda: False)():
            self.tconorm_var.set(space.tconorm.upper())
            self._sync_tconorm_buttons()
            self.app.custom_warning("Process Running",
                "Finish or cancel the active process before changing the T-conorm.",
                parent=self.win)
            return
        try:
            space.set_tconorm(operator)
        except ValueError as exc:
            self.tconorm_var.set(space.tconorm.upper())
            self._sync_tconorm_buttons()
            self.app.custom_warning("Invalid T-conorm", str(exc), parent=self.win)
            return
        # Existing image mappings were computed with the previous operator.
        # Restore/lock those views using the same procedure as an FCS change.
        prepare = getattr(self.app, "_prepare_open_images_for_color_space_change", None)
        if callable(prepare):
            prepare()
        invalidate = getattr(self.app, "_invalidate_mapping_caches", None)
        if callable(invalidate):
            invalidate()
        for sample in self._pinned_samples:
            self._refresh_sample_memberships(sample)
        for sample in self._last_sample.values():
            self._refresh_sample_memberships(sample)
        if self._current_sample:
            self._refresh_sample_memberships(self._current_sample)
            self._auto_select_reference()
            self._update_sample_ui()
            self._populate_memberships()
            self._update_prototype_ui()
        self._refresh_pin_tree()
        sync = getattr(self.app, "_sync_image_mapping_tconorm_buttons", None)
        if callable(sync):
            sync()

    def _apply_result_style(self, status):
        if status in ("inside", "below_pt", "below_at", "below_custom", "below_lower", "within", "below"):
            body, accent = self.GREEN_BG, self.GREEN
        elif status in ("warning", "between_pt_at", "between_custom", "between"):
            body, accent = self.YELLOW_BG, self.YELLOW
        elif status in ("outside", "above_pt", "above_at", "above_custom", "above_upper", "above"):
            body, accent = self.RED_BG, self.RED
        else:
            body, accent = self.SOFT, self.MUTED

        try:
            self.result_card.configure(bg=body, highlightbackground=self.BORDER,
                                       highlightcolor=self.BORDER)
            self.result_accent.configure(bg=accent)
            self.result_body.configure(bg=body)
            self.result_header.configure(bg=body)
            self.result_dot.configure(bg=body)
            self.result_dot.itemconfig(self.result_dot_oval, fill=accent, outline=accent)
            self.result_status_label.configure(bg=body, fg=accent)
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
        for frame in (self.threshold_dynamic, self._threshold_entries_row):
            for child in frame.winfo_children():
                child.destroy()
        self._threshold_entries_row.grid_remove()
        self._custom_entries_holder = None

        mode = self.threshold_mode_var.get().strip().lower()
        if mode == "default":
            tk.Label(self.threshold_dynamic, text="Default preset",
                     font=self.FONT_SMALL_BOLD, bg=self.CARD, fg=self.TEXT).pack(anchor="w")
            combo = UtilsTools.styled_combobox(
                self.threshold_dynamic, textvariable=self.threshold_preset_var,
                values=["Perceptibility Threshold", "Acceptability Threshold",
                        "Perceptibility + Acceptability"],
                state="readonly", width=28,
            )
            combo.pack(fill="x", pady=(3, 0))
            combo.bind("<<ComboboxSelected>>", lambda _e: self._threshold_changed())
            return

        tk.Label(self.threshold_dynamic, text="Custom mode", font=self.FONT_SMALL_BOLD,
                 bg=self.CARD, fg=self.TEXT).pack(anchor="w")
        combo = UtilsTools.styled_combobox(
            self.threshold_dynamic, textvariable=self.threshold_custom_type_var,
            values=["Single threshold", "Lower and upper thresholds"],
            state="readonly", width=28,
        )
        combo.pack(fill="x", pady=(3, 0))
        combo.bind("<<ComboboxSelected>>", lambda _e: self._custom_threshold_mode_changed())
        self._threshold_entries_row.grid(row=1, column=0, columnspan=2,
                                         sticky="ew", pady=(7, 0))
        entries = tk.Frame(self._threshold_entries_row, bg=self.CARD)
        entries.pack(fill="x")
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
        if self._current_sample and not self._reference_locked:
            self._auto_select_reference()
            self._highlight_membership_selection()
            self._update_prototype_ui()
        else:
            self._refresh_comparison_result()

    # Pinned Samples
    def _pin_current_sample(self):
        if not self._current_sample:
            return
        sample = copy.deepcopy(self._current_sample)
        sample["reference_category"] = self._selected_category_label
        sample["reference_granule"] = self._selected_proto_label
        sample["reference_locked"] = self._reference_locked
        sample["category_locked"] = self._category_locked
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
        self._category_locked = False
        self._reference_locked = False
        self._set_current_sample(sample, remember=True, show_tooltip=False)
        ref_category = sample.get("reference_category")
        ref_granule = sample.get("reference_granule")
        if ref_granule in self._reference_labels and sample.get("reference_locked"):
            self._select_granule(ref_category if ref_granule in self._membership_descendants.get(ref_category, ())
                                 else self._reference_labels[ref_granule][0], ref_granule)
        elif ref_category in self._reference_categories and sample.get("category_locked"):
            self._select_category(ref_category)

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

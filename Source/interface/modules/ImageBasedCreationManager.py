import os
import platform
import threading
import tkinter as tk
from tkinter import ttk, filedialog

import numpy as np
from PIL import Image, ImageTk

import Source.interface.modules.UtilsTools as UtilsTools


class ImageBasedCreationManager:
    """
    Single-workspace image-based fuzzy color space creation tool.

    The workspace keeps image browsing, manual sampling, automatic color
    detection and the selected-color list in one persistent window.
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
    GREEN = "#1f5f3a"
    GREEN_SOFT = "#e0f2e9"
    RED = "#8a1f1f"
    RED_SOFT = "#f8d7da"

    FONT = ("Segoe UI", 9)
    FONT_BOLD = ("Segoe UI", 9, "bold")
    FONT_SMALL = ("Segoe UI", 8)
    FONT_SMALL_BOLD = ("Segoe UI", 8, "bold")
    FONT_SECTION = ("Segoe UI", 10, "bold")

    def __init__(self, app, open_image_on_start=False):
        self.app = app
        self.root = app.root

        self.win = tk.Toplevel(self.root)
        self.win.title("Image-Based Color Space Creation")
        self.win.configure(bg=self.BG)
        self.win.minsize(1120, 700)
        self.win.protocol("WM_DELETE_WINDOW", self.close)

        try:
            self.win.transient(self.root)
        except Exception:
            pass

        self._configure_window_size()

        # Image sources and independent viewport state.
        self._sources = {}
        self._source_order = []
        self._display_to_key = {}
        self._key_to_display = {}
        self.current_source_key = None
        self._view_state = {}
        self._external_counter = 0

        # Image rendering / interaction state.
        self._canvas_photo = None
        self._render_transform = None
        self._pan_state = None
        self._drag_start_source = None
        self._drag_current_source = None
        self._drag_start_canvas = None
        self._current_sample = None

        # Selected colors for the new color space.
        self.colors = {}
        self.color_checks = {}
        self._name_editors = []

        # Automatic detection state.
        self._detection_running = False
        self._spinner_after_id = None
        self._spinner_angle = 0

        self._create_variables()
        self._build_ui()
        self._load_workspace_sources(select_first=True)

        # When Image-Based Creation was launched without an existing workspace
        # image, open a local image picker after the window has been created.
        # Images opened here remain private to this creation workspace and are
        # not added to the main Image Display.
        if open_image_on_start and not self._source_order:
            self.win.after(120, self._open_workspace_image)

        # Let the main application track this as the active creation workflow.
        try:
            self.app._register_creation_window(self.win)
        except Exception:
            pass

        self.win.bind("<Escape>", lambda _e: self.close())
        self.win.after(80, self._render_image)
        self.win.focus_set()

    # ======================================================================
    # WINDOW / STATE
    # ======================================================================
    def _configure_window_size(self):
        """Open the creation workspace as a normal centered window."""
        width = 1200
        height = 700

        try:
            self.win.update_idletasks()
            self.app.center_popup(self.win, width, height)
        except Exception:
            try:
                sw = self.win.winfo_screenwidth()
                sh = self.win.winfo_screenheight()
                x = max(0, (sw - width) // 2)
                y = max(0, (sh - height) // 2)
                self.win.geometry(f"{width}x{height}+{x}+{y}")
            except Exception:
                self.win.geometry(f"{width}x{height}")

    def close(self):
        if self._detection_running:
            return

        try:
            if self.win.winfo_exists():
                self.win.destroy()
        except Exception:
            pass

        try:
            self.app._image_based_creation_controller = None
            self.app._image_based_creation_window = None
        except Exception:
            pass

    def _create_variables(self):
        self.source_var = tk.StringVar(value="")
        self.mode_var = tk.StringVar(value="Manual")
        self.help_var = tk.StringVar(
            value="Click: pixel · Drag: filtered mean · Right-drag: move · Wheel: zoom"
        )
        self.zoom_var = tk.StringVar(value="Fit")

        self.sample_title_var = tk.StringVar(value="No sample selected")
        self.sample_position_var = tk.StringVar(value="Click a pixel or drag an area")
        self.sample_filters_var = tk.StringVar(value="")
        self.sample_rgb_var = tk.StringVar(value="RGB: —")
        self.sample_lab_var = tk.StringVar(value="LAB: —")
        self.sample_hex_var = tk.StringVar(value="HEX: —")

        self.selected_count_var = tk.StringVar(value="0 of 0 selected")

        self.threshold_var = tk.DoubleVar(value=0.50)
        self.min_samples_var = tk.IntVar(value=160)
        self.threshold_text_var = tk.StringVar(value="Threshold: 0.50")
        self.detection_status_var = tk.StringVar(value="")

        # Optional LAB filters shared by automatic detection and manual ROI sampling.
        # Disabled by default, so the original behavior remains unchanged until
        # the user explicitly enables one or more limits.
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
        self.filter_summary_var = tk.StringVar(value="No filters applied")

    # ======================================================================
    # UI BUILDING
    # ======================================================================
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
        paned.add(right, stretch="always", minsize=390)

        self._build_image_workspace(left)
        self._build_selected_colors_panel(right)

        def _initial_sash():
            try:
                total = paned.winfo_width()
                if total > 1:
                    paned.sash_place(0, int(total * 0.70), 1)
            except Exception:
                pass

        self.win.after(150, _initial_sash)

    def _build_header(self, parent):
        header = tk.Frame(parent, bg=self.CARD, bd=1, relief="solid")
        header.pack(fill="x")

        inner = tk.Frame(header, bg=self.CARD)
        inner.pack(fill="x", padx=12, pady=7)

        tk.Label(
            inner,
            text="Image-Based Color Space Creation",
            font=("Segoe UI", 13, "bold"),
            bg=self.CARD,
            fg=self.TEXT,
        ).pack(side="left", padx=(2, 18))

        tk.Label(
            inner,
            text="Image:",
            font=self.FONT_BOLD,
            bg=self.CARD,
            fg=self.TEXT,
        ).pack(side="left")

        self.prev_source_button = tk.Button(
            inner,
            text="◀",
            width=3,
            command=lambda: self._step_source(-1),
            font=self.FONT_BOLD,
            cursor="hand2",
        )
        self.prev_source_button.pack(side="left", padx=(8, 3))

        self.source_combo = ttk.Combobox(
            inner,
            textvariable=self.source_var,
            state="readonly",
            width=34,
        )
        self.source_combo.pack(side="left", padx=3)
        self.source_combo.bind("<<ComboboxSelected>>", self._on_source_combo)

        self.next_source_button = tk.Button(
            inner,
            text="▶",
            width=3,
            command=lambda: self._step_source(1),
            font=self.FONT_BOLD,
            cursor="hand2",
        )
        self.next_source_button.pack(side="left", padx=(3, 10))

        self.open_image_button = tk.Button(
            inner,
            text="+ Open Image...",
            command=self._open_workspace_image,
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
        )
        self.open_image_button.pack(side="left", padx=(0, 6))

        self.refresh_sources_button = tk.Button(
            inner,
            text="Refresh",
            command=lambda: self._load_workspace_sources(select_first=False),
            font=self.FONT,
            relief="solid",
            bd=1,
            padx=7,
            pady=3,
            cursor="hand2",
        )
        self.refresh_sources_button.pack(side="left")

        tk.Label(
            inner,
            text="Build FCS from image samples",
            font=self.FONT_SMALL,
            bg=self.CARD,
            fg=self.MUTED,
        ).pack(side="right", padx=(12, 2))

    def _build_image_workspace(self, parent):
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
        self.image_canvas.bind("<ButtonPress-1>", self._on_left_press)
        self.image_canvas.bind("<B1-Motion>", self._on_left_drag)
        self.image_canvas.bind("<ButtonRelease-1>", self._on_left_release)

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

        left_controls = tk.Frame(controls, bg=self.CARD)
        left_controls.pack(side="left")

        tk.Label(
            left_controls,
            text="Extraction:",
            font=self.FONT_BOLD,
            bg=self.CARD,
            fg=self.TEXT,
        ).pack(side="left")

        self.mode_combo = ttk.Combobox(
            left_controls,
            textvariable=self.mode_var,
            values=("Manual", "Automatic"),
            state="readonly",
            width=11,
        )
        self.mode_combo.pack(side="left", padx=(7, 6))
        self.mode_combo.bind("<<ComboboxSelected>>", self._on_mode_changed)

        # LAB filters are shared by both extraction modes. In Manual mode they
        # are applied pixel-by-pixel before computing the mean of a dragged ROI.
        self.filters_button = tk.Button(
            left_controls,
            text="Filters...",
            command=self._open_detection_filters,
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
        self.filters_button.pack(side="left", padx=(4, 0))

        right_controls = tk.Frame(controls, bg=self.CARD)
        right_controls.pack(side="right", padx=(8, 0))

        tk.Button(
            right_controls,
            text="Fit",
            command=self._reset_view,
            font=self.FONT,
            relief="solid",
            bd=1,
            padx=6,
            pady=2,
            cursor="hand2",
        ).pack(side="left", padx=(0, 8))

        tk.Label(
            right_controls,
            text="Zoom:",
            font=self.FONT_SMALL,
            bg=self.CARD,
            fg=self.MUTED,
        ).pack(side="left")

        tk.Label(
            right_controls,
            textvariable=self.zoom_var,
            font=self.FONT_SMALL,
            bg=self.CARD,
            fg=self.TEXT,
            width=5,
            anchor="w",
        ).pack(side="left", padx=(3, 0))

        tk.Label(
            controls,
            textvariable=self.help_var,
            font=self.FONT_SMALL,
            bg=self.CARD,
            fg=self.MUTED,
            anchor="center",
            justify="center",
        ).pack(side="left", fill="x", expand=True, padx=8)

        self.manual_card = self._card(image_card, "Manual Sample", padx=9, pady=8)
        self.manual_card.pack(fill="x", pady=(8, 0))
        self._build_manual_card(self.manual_card)

        self.auto_card = self._card(image_card, "Automatic Detection", padx=9, pady=8)
        self._build_auto_card(self.auto_card)

    def _build_manual_card(self, card):
        row = tk.Frame(card, bg=self.CARD)
        row.pack(fill="x")
        row.columnconfigure(1, weight=1)

        self.sample_swatch = tk.Canvas(
            row,
            width=58,
            height=58,
            bg=self.CARD,
            highlightthickness=0,
        )
        self.sample_swatch.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 10))
        self.sample_swatch_rect = self.sample_swatch.create_rectangle(
            4, 4, 54, 54, fill="#d9dde3", outline="#707070", width=1
        )

        info = tk.Frame(row, bg=self.CARD)
        info.grid(row=0, column=1, sticky="nsew")

        tk.Label(
            info,
            textvariable=self.sample_title_var,
            font=self.FONT_BOLD,
            bg=self.CARD,
            fg=self.TEXT,
            anchor="w",
        ).pack(fill="x")

        tk.Label(
            info,
            textvariable=self.sample_position_var,
            font=self.FONT_SMALL,
            bg=self.CARD,
            fg=self.MUTED,
            anchor="w",
        ).pack(fill="x", pady=(2, 0))

        # Only shown for ROI samples when one or more LAB filters are active.
        tk.Label(
            info,
            textvariable=self.sample_filters_var,
            font=("Segoe UI", 8, "italic"),
            bg=self.CARD,
            fg=self.MUTED,
            anchor="w",
        ).pack(fill="x", pady=(2, 0))

        values = tk.Frame(row, bg=self.CARD)
        values.grid(row=0, column=2, sticky="ne", padx=(12, 12))

        for var in (self.sample_rgb_var, self.sample_lab_var, self.sample_hex_var):
            tk.Label(
                values,
                textvariable=var,
                font=self.FONT,
                bg=self.CARD,
                fg=self.TEXT,
                anchor="e",
            ).pack(anchor="e")

        self.add_sample_button = tk.Button(
            row,
            text="Add Color",
            command=self._add_current_sample,
            font=self.FONT_BOLD,
            bg=self.GREEN_SOFT,
            fg=self.GREEN,
            activebackground="#cfeadb",
            activeforeground=self.GREEN,
            relief="solid",
            bd=1,
            padx=14,
            pady=5,
            cursor="hand2",
            state="disabled",
        )
        self.add_sample_button.grid(row=0, column=3, rowspan=2, sticky="e")

    def _build_auto_card(self, card):
        top = tk.Frame(card, bg=self.CARD)
        top.pack(fill="x")

        tk.Label(
            top,
            textvariable=self.threshold_text_var,
            font=self.FONT_BOLD,
            bg=self.CARD,
            fg=self.TEXT,
        ).pack(side="left")

        self.threshold_minus_button = tk.Button(
            top,
            text="−",
            width=3,
            command=self._decrease_threshold,
            bg=self.RED_SOFT,
            fg=self.RED,
            relief="solid",
            bd=1,
            cursor="hand2",
        )
        self.threshold_minus_button.pack(side="left", padx=(12, 4))

        self.threshold_plus_button = tk.Button(
            top,
            text="+",
            width=3,
            command=self._increase_threshold,
            bg=self.GREEN_SOFT,
            fg=self.GREEN,
            relief="solid",
            bd=1,
            cursor="hand2",
        )
        self.threshold_plus_button.pack(side="left", padx=(0, 12))

        self.detect_button = tk.Button(
            top,
            text="Detect and Add Colors",
            command=self._run_auto_detection,
            font=self.FONT_BOLD,
            bg=self.BLUE_SOFT,
            fg=self.BLUE,
            activebackground="#d7e5fb",
            activeforeground=self.BLUE,
            relief="solid",
            bd=1,
            padx=12,
            pady=4,
            cursor="hand2",
        )
        self.detect_button.pack(side="right")

        info_row = tk.Frame(card, bg=self.CARD)
        info_row.pack(fill="x", pady=(7, 3))

        tk.Label(
            info_row,
            textvariable=self.filter_summary_var,
            font=self.FONT_SMALL,
            bg=self.CARD,
            fg=self.MUTED,
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        self.detection_status_label = tk.Label(
            info_row,
            textvariable=self.detection_status_var,
            font=self.FONT_SMALL_BOLD,
            bg=self.CARD,
            fg=self.GREEN,
            anchor="e",
        )
        self.detection_status_label.pack(side="right", padx=(12, 0))

        tk.Label(
            card,
            text=(
                "Decrease the threshold if too many colors are detected; "
                "increase it if too few are detected. Active LAB filters are applied "
                "before detected colors are added to the list."
            ),
            font=("Segoe UI", 8, "italic"),
            bg=self.CARD,
            fg=self.MUTED,
            anchor="w",
            justify="left",
            wraplength=700,
        ).pack(fill="x", pady=(2, 0))

    def _build_selected_colors_panel(self, parent):
        outer = tk.Frame(parent, bg=self.BG)
        outer.pack(fill="both", expand=True, padx=(8, 0))

        card = self._card(outer, "Selected Colors", padx=9, pady=8)
        card.pack(fill="both", expand=True)

        toolbar = tk.Frame(card, bg=self.CARD)
        toolbar.pack(fill="x", pady=(0, 8))

        tk.Button(
            toolbar,
            text="Select All",
            command=self._select_all_colors,
            font=self.FONT_SMALL,
        ).pack(side="left")

        tk.Button(
            toolbar,
            text="Deselect All",
            command=self._deselect_all_colors,
            font=self.FONT_SMALL,
        ).pack(side="left", padx=5)

        tk.Button(
            toolbar,
            text="Remove",
            command=self._remove_selected_colors,
            font=self.FONT_SMALL,
        ).pack(side="left")

        tk.Label(
            toolbar,
            textvariable=self.selected_count_var,
            bg=self.CARD,
            fg=self.MUTED,
            font=self.FONT_SMALL,
        ).pack(side="right")

        list_holder = tk.Frame(card, bg=self.CARD, bd=1, relief="solid")
        list_holder.pack(fill="both", expand=True)

        self.colors_canvas = tk.Canvas(
            list_holder,
            bg=self.CARD,
            highlightthickness=0,
            bd=0,
        )
        colors_scroll = ttk.Scrollbar(
            list_holder,
            orient="vertical",
            command=self.colors_canvas.yview,
        )
        self.colors_canvas.configure(yscrollcommand=colors_scroll.set)

        colors_scroll.pack(side="right", fill="y")
        self.colors_canvas.pack(side="left", fill="both", expand=True)

        self.colors_inner = tk.Frame(self.colors_canvas, bg=self.CARD)
        self.colors_window_id = self.colors_canvas.create_window(
            (0, 0), window=self.colors_inner, anchor="nw"
        )

        self.colors_inner.bind(
            "<Configure>",
            lambda _e: self.colors_canvas.configure(
                scrollregion=self.colors_canvas.bbox("all")
            ),
        )
        self.colors_canvas.bind(
            "<Configure>",
            lambda e: self.colors_canvas.itemconfigure(
                self.colors_window_id, width=max(1, e.width - 3)
            ),
        )

        self.colors_canvas.bind("<MouseWheel>", self._on_colors_mousewheel)
        self.colors_inner.bind("<MouseWheel>", self._on_colors_mousewheel)

        footer_sep = tk.Frame(card, bg=self.BORDER, height=1)
        footer_sep.pack(fill="x", pady=(10, 8))

        footer = tk.Frame(card, bg=self.CARD)
        footer.pack(fill="x")

        tk.Button(
            footer,
            text="+ Add Custom Color",
            command=self._add_custom_color,
            font=self.FONT_BOLD,
            relief="solid",
            bd=1,
            padx=10,
            pady=5,
            cursor="hand2",
        ).pack(side="left")

        tk.Button(
            footer,
            text="Create Color Space",
            command=self._create_color_space,
            font=self.FONT_BOLD,
            bg=self.BLUE_SOFT,
            fg=self.BLUE,
            activebackground="#d7e5fb",
            activeforeground=self.BLUE,
            relief="solid",
            bd=1,
            padx=14,
            pady=5,
            cursor="hand2",
        ).pack(side="right")

        self._refresh_color_list()

    # ======================================================================
    # IMAGE SOURCES / NAVIGATION
    # ======================================================================
    def _load_workspace_sources(self, select_first=False):
        previous_keys = set(self._source_order)
        load_names = getattr(self.app, "load_images_names", {}) or {}
        active_workspace_keys = {f"workspace:{window_id}" for window_id in load_names}

        # Remove workspace images that were closed in the main application.
        # Local images opened inside this manager are intentionally preserved.
        stale_keys = [
            key for key in self._source_order
            if key.startswith("workspace:") and key not in active_workspace_keys
        ]
        for key in stale_keys:
            self._sources.pop(key, None)
            self._view_state.pop(key, None)
            try:
                self._source_order.remove(key)
            except ValueError:
                pass

        for window_id, path in load_names.items():
            key = f"workspace:{window_id}"
            if key in self._sources:
                continue

            try:
                pil = self.app._get_best_image_source_pil(
                    window_id,
                    prefer_current_view=False,
                    rgb=False,
                )
            except Exception:
                pil = None

            if pil is None or not isinstance(pil, Image.Image):
                continue

            self._sources[key] = {
                "key": key,
                "window_id": window_id,
                "path": path,
                "name": os.path.basename(path) if path else str(window_id),
                "pil": pil.copy(),
                "external": False,
            }
            self._source_order.append(key)

        self._rebuild_source_combo()

        if self.current_source_key not in self._sources:
            self.current_source_key = None
            if self._source_order:
                self._switch_source(self._source_order[0], clear_sample=True)
            else:
                self.source_var.set("")
                self._clear_current_sample()
                self._render_image()
            return

        if select_first and self.current_source_key is None and self._source_order:
            self._switch_source(self._source_order[0], clear_sample=True)
            return

        new_keys = [key for key in self._source_order if key not in previous_keys]
        if new_keys:
            self._switch_source(new_keys[-1], clear_sample=True)

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

    def _open_workspace_image(self):
        """
        Open an image only inside Image-Based Creation.

        The image is intentionally kept local to this workspace: it is not
        registered in the main PyFCS Image Display and disappears when this
        creation window is closed. Existing main-workspace images remain
        available through the image selector.
        """
        if self._detection_running:
            return
        base_path = UtilsTools.get_base_path()
        initial_dir = os.path.join(base_path, "image_test")
        if not os.path.isdir(initial_dir):
            initial_dir = base_path

        path = filedialog.askopenfilename(
            title="Open image for Image-Based Creation",
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
                pil = img.convert("RGBA")
        except Exception as exc:
            self.app.custom_warning(
                "Open Image",
                f"Could not open image:\n{exc}",
                parent=self.win,
            )
            return

        self._external_counter += 1
        key = f"local:{self._external_counter}"

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
        self._switch_source(key, clear_sample=True)

    def _on_source_combo(self, _event=None):
        if self._detection_running:
            return
        key = self._display_to_key.get(self.source_var.get())
        if key:
            self._switch_source(key, clear_sample=True)

    def _step_source(self, delta):
        if self._detection_running:
            return
        if not self._source_order:
            return
        try:
            idx = self._source_order.index(self.current_source_key)
        except ValueError:
            idx = 0
        idx = (idx + int(delta)) % len(self._source_order)
        self._switch_source(self._source_order[idx], clear_sample=True)

    def _switch_source(self, key, clear_sample=True):
        if key not in self._sources:
            return

        self.current_source_key = key
        self.source_var.set(self._key_to_display.get(key, self._sources[key].get("name", "Image")))

        if key not in self._view_state:
            pil = self._sources[key]["pil"]
            w, h = pil.size
            self._view_state[key] = {"zoom": 1.0, "cx": w / 2.0, "cy": h / 2.0}

        if clear_sample:
            self._clear_current_sample()

        self._render_image()

    def _current_pil(self):
        src = self._sources.get(self.current_source_key)
        if not src:
            return None
        pil = src.get("pil")
        return pil if isinstance(pil, Image.Image) else None

    # ======================================================================
    # IMAGE RENDERING / VIEWPORT
    # ======================================================================
    @staticmethod
    def _clamp(value, low, high):
        return max(low, min(high, value))

    def _reset_view(self):
        pil = self._current_pil()
        if pil is None or self.current_source_key is None:
            return
        w, h = pil.size
        self._view_state[self.current_source_key] = {
            "zoom": 1.0,
            "cx": w / 2.0,
            "cy": h / 2.0,
        }
        self._render_image()

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

        half_w = visible_w / 2.0
        half_h = visible_h / 2.0
        cx = self._clamp(float(state.get("cx", sw / 2.0)), half_w, max(half_w, sw - half_w))
        cy = self._clamp(float(state.get("cy", sh / 2.0)), half_h, max(half_h, sh - half_h))
        state["cx"], state["cy"] = cx, cy

        left = max(0.0, cx - half_w)
        top = max(0.0, cy - half_h)
        right = min(float(sw), left + visible_w)
        bottom = min(float(sh), top + visible_h)
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

        # While automatic detection is running, show a lightly pixelated
        # preview to signal that the image is being processed without hiding it.
        if self._detection_running:
            pixel_w = max(1, draw_w // 5)
            pixel_h = max(1, draw_h // 5)
            resized = resized.resize((pixel_w, pixel_h), Image.Resampling.BILINEAR)
            resized = resized.resize((draw_w, draw_h), Image.Resampling.NEAREST)

        self._canvas_photo = ImageTk.PhotoImage(resized)
        ox = (cw - draw_w) / 2.0
        oy = (ch - draw_h) / 2.0

        self.image_canvas.delete("all")
        self.image_canvas.create_image(ox, oy, anchor="nw", image=self._canvas_photo, tags=("image",))

        self._render_transform = {
            "left": float(crop_box[0]),
            "top": float(crop_box[1]),
            "right": float(crop_box[2]),
            "bottom": float(crop_box[3]),
            "ox": ox,
            "oy": oy,
            "draw_w": draw_w,
            "draw_h": draw_h,
            "scale_x": draw_w / max(1.0, float(crop.width)),
            "scale_y": draw_h / max(1.0, float(crop.height)),
        }

        self.zoom_var.set("Fit" if abs(zoom - 1.0) < 1e-6 else f"{zoom * 100:.0f}%")
        self._draw_current_sample()
        self._draw_drag_preview()

        if self._detection_running:
            self._draw_detection_overlay()

    def _canvas_to_source(self, x, y):
        t = self._render_transform
        pil = self._current_pil()
        if not t or pil is None:
            return None

        if not (
            t["ox"] <= x < t["ox"] + t["draw_w"]
            and t["oy"] <= y < t["oy"] + t["draw_h"]
        ):
            return None

        sx = t["left"] + (x - t["ox"]) / max(t["scale_x"], 1e-9)
        sy = t["top"] + (y - t["oy"]) / max(t["scale_y"], 1e-9)
        sw, sh = pil.size
        return (
            int(self._clamp(round(sx), 0, sw - 1)),
            int(self._clamp(round(sy), 0, sh - 1)),
        )

    def _source_to_canvas(self, sx, sy):
        t = self._render_transform
        if not t:
            return None
        if not (t["left"] <= sx <= t["right"] and t["top"] <= sy <= t["bottom"]):
            return None
        return (
            t["ox"] + (sx - t["left"]) * t["scale_x"],
            t["oy"] + (sy - t["top"]) * t["scale_y"],
        )

    def _on_mousewheel(self, event):
        factor = 1.12 if event.delta > 0 else 1 / 1.12
        return self._zoom_at_event(event, factor)

    def _zoom_at_event(self, event, factor):
        if self._detection_running:
            return "break"
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

        if before is not None:
            after = self._canvas_to_source(event.x, event.y)
            if after is not None:
                state["cx"] += before[0] - after[0]
                state["cy"] += before[1] - after[1]
                self._render_image()

        return "break"

    def _start_pan(self, event):
        if self._detection_running:
            return "break"
        if self.current_source_key is None or self._render_transform is None:
            return "break"
        self._pan_state = (event.x, event.y)
        self.image_canvas.configure(cursor="fleur")
        return "break"

    def _pan_motion(self, event):
        if self._detection_running:
            return "break"
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

    # ======================================================================
    # MANUAL SAMPLING
    # ======================================================================
    def _on_mode_changed(self, _event=None):
        mode = self.mode_var.get().strip().lower()
        if mode == "automatic":
            self.help_var.set("Detection uses original image · Right-drag: move · Wheel: zoom")
            self.manual_card.pack_forget()
            self.auto_card.pack(fill="x", pady=(8, 0))
        else:
            self.help_var.set("Click: pixel · Drag: filtered mean · Right-drag: move · Wheel: zoom")
            self.auto_card.pack_forget()
            self.manual_card.pack(fill="x", pady=(8, 0))

        self._drag_start_source = None
        self._drag_current_source = None
        self._drag_start_canvas = None
        self._render_image()

    def _on_left_press(self, event):
        if self._detection_running:
            return "break"
        if self.mode_var.get().strip().lower() != "manual":
            return "break"

        point = self._canvas_to_source(event.x, event.y)
        if point is None:
            self._drag_start_source = None
            self._drag_current_source = None
            self._drag_start_canvas = None
            return "break"

        self._drag_start_source = point
        self._drag_current_source = point
        self._drag_start_canvas = (event.x, event.y)
        return "break"

    def _on_left_drag(self, event):
        if self._detection_running:
            return "break"
        if self.mode_var.get().strip().lower() != "manual" or self._drag_start_source is None:
            return "break"

        point = self._canvas_to_source(event.x, event.y)
        if point is None:
            return "break"

        self._drag_current_source = point
        start_canvas = self._drag_start_canvas
        if start_canvas is not None:
            if abs(event.x - start_canvas[0]) >= 4 or abs(event.y - start_canvas[1]) >= 4:
                self._render_image()
        return "break"

    def _on_left_release(self, event):
        if self._detection_running:
            return "break"
        if self.mode_var.get().strip().lower() != "manual":
            return "break"

        point = self._canvas_to_source(event.x, event.y)
        start = self._drag_start_source
        start_canvas = self._drag_start_canvas

        self._drag_start_source = None
        self._drag_current_source = None
        self._drag_start_canvas = None

        if point is None or start is None:
            self._render_image()
            return "break"

        is_drag = False
        if start_canvas is not None:
            is_drag = (
                abs(event.x - start_canvas[0]) >= 4
                or abs(event.y - start_canvas[1]) >= 4
            )

        if is_drag:
            self._sample_roi(start[0], start[1], point[0], point[1])
        else:
            self._sample_pixel(point[0], point[1])
        return "break"

    def _sample_pixel(self, x, y):
        pil = self._current_pil()
        if pil is None:
            return

        rgba = pil.convert("RGBA").getpixel((int(x), int(y)))
        r, g, b, a = rgba
        if a == 0:
            return

        rgb = (int(r), int(g), int(b))
        lab = UtilsTools.rgb_to_lab(rgb)
        lab = tuple(float(v) for v in np.asarray(lab, dtype=float).reshape(-1)[:3])

        self._current_sample = {
            "type": "pixel",
            "x": int(x),
            "y": int(y),
            "rgb": rgb,
            "lab": lab,
            "hex": UtilsTools.rgb_to_hex(rgb).upper(),
        }
        self._update_sample_ui()
        self._render_image()

    def _sample_roi(self, x1, y1, x2, y2):
        pil = self._current_pil()
        if pil is None:
            return

        left, right = sorted((int(x1), int(x2)))
        top, bottom = sorted((int(y1), int(y2)))

        if right <= left or bottom <= top:
            self._sample_pixel(left, top)
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

        # Apply the same active LAB limits used by automatic detection, but here
        # pixel-by-pixel BEFORE computing the ROI mean. This is especially useful
        # for excluding highlights, dark areas or unwanted chromatic regions.
        mean_rgb_arr, used_count = self._mean_rgb_with_active_lab_filters(rgb_pixels)

        if used_count <= 0 or mean_rgb_arr is None:
            self.app.custom_warning(
                "No Valid Pixels",
                "No pixels in the selected area satisfy the active LAB filters.",
                parent=self.win,
            )
            # Do not leave a stale mean color visible after filters changed.
            self._clear_current_sample()
            self._render_image()
            return

        mean_rgb = tuple(int(round(v)) for v in mean_rgb_arr[:3])
        lab = UtilsTools.rgb_to_lab(mean_rgb)
        lab = tuple(float(v) for v in np.asarray(lab, dtype=float).reshape(-1)[:3])

        filters_active = bool(self._active_detection_filters())

        self._current_sample = {
            "type": "roi",
            "x1": left,
            "y1": top,
            "x2": right,
            "y2": bottom,
            "width": right - left + 1,
            "height": bottom - top + 1,
            "pixels": int(used_count),
            "total_pixels": int(total_count),
            "filtered_out": int(total_count - used_count),
            "filters_applied": filters_active,
            "rgb": mean_rgb,
            "lab": lab,
            "hex": UtilsTools.rgb_to_hex(mean_rgb).upper(),
        }
        self._update_sample_ui()
        self._render_image()

    def _clear_current_sample(self):
        self._current_sample = None
        self.sample_title_var.set("No sample selected")
        self.sample_position_var.set("Click a pixel or drag an area")
        self.sample_filters_var.set("")
        self.sample_rgb_var.set("RGB: —")
        self.sample_lab_var.set("LAB: —")
        self.sample_hex_var.set("HEX: —")
        try:
            self.sample_swatch.itemconfig(self.sample_swatch_rect, fill="#d9dde3")
            self.add_sample_button.configure(state="disabled")
        except Exception:
            pass

    def _update_sample_ui(self):
        sample = self._current_sample
        if not sample:
            self._clear_current_sample()
            return

        if sample["type"] == "roi":
            self.sample_title_var.set("Mean Color")

            if sample.get("filters_applied"):
                pixel_text = (
                    f"{sample.get('pixels', 0)} / {sample.get('total_pixels', sample.get('pixels', 0))} "
                    "pixels used"
                )
            else:
                pixel_text = f"{sample.get('pixels', 0)} pixels"

            self.sample_position_var.set(
                f"ROI ({sample['x1']}, {sample['y1']}) → ({sample['x2']}, {sample['y2']}) · "
                f"{sample['width']} × {sample['height']} px · {pixel_text}"
            )

            # Show the same active-filter summary used by Automatic Detection,
            # but only for area samples. A single-pixel click is never filtered.
            if sample.get("filters_applied"):
                summary = self.filter_summary_var.get().strip()
                self.sample_filters_var.set(summary if summary != "No filters applied" else "")
            else:
                self.sample_filters_var.set("")
        else:
            self.sample_title_var.set("Selected Color")
            self.sample_position_var.set(f"Pixel ({sample['x']}, {sample['y']})")
            self.sample_filters_var.set("")

        rgb = sample["rgb"]
        lab = sample["lab"]
        self.sample_rgb_var.set(f"RGB: {rgb[0]}, {rgb[1]}, {rgb[2]}")
        self.sample_lab_var.set(f"LAB: {lab[0]:.2f}, {lab[1]:.2f}, {lab[2]:.2f}")
        self.sample_hex_var.set(f"HEX: {sample['hex']}")

        try:
            self.sample_swatch.itemconfig(self.sample_swatch_rect, fill=sample["hex"])
            self.add_sample_button.configure(state="normal")
        except Exception:
            pass

    def _draw_current_sample(self):
        sample = self._current_sample
        if not sample:
            return

        if sample["type"] == "roi":
            p1 = self._source_to_canvas(sample["x1"], sample["y1"])
            p2 = self._source_to_canvas(sample["x2"], sample["y2"])
            if p1 and p2:
                self.image_canvas.create_rectangle(
                    p1[0], p1[1], p2[0], p2[1],
                    outline="#d62728", width=2, tags=("sample_marker",)
                )
            return

        p = self._source_to_canvas(sample["x"], sample["y"])
        if p is None:
            return
        x, y = p
        self.image_canvas.create_line(x - 9, y, x + 9, y, fill="#d62728", width=2)
        self.image_canvas.create_line(x, y - 9, x, y + 9, fill="#d62728", width=2)
        self.image_canvas.create_oval(x - 5, y - 5, x + 5, y + 5, outline="white", width=1)

    def _draw_drag_preview(self):
        if self._drag_start_source is None or self._drag_current_source is None:
            return

        p1 = self._source_to_canvas(*self._drag_start_source)
        p2 = self._source_to_canvas(*self._drag_current_source)
        if p1 is None or p2 is None:
            return

        if self._drag_start_canvas is not None:
            dx = abs(p2[0] - self._drag_start_canvas[0])
            dy = abs(p2[1] - self._drag_start_canvas[1])
            if dx < 4 and dy < 4:
                return

        self.image_canvas.create_rectangle(
            p1[0], p1[1], p2[0], p2[1],
            outline="#d97706", width=2, dash=(5, 3),
        )

    def _add_current_sample(self):
        sample = self._current_sample
        if not sample:
            return

        name = self._next_unique_name("Image Color")
        source = self._sources.get(self.current_source_key, {})
        self._add_color(
            name=name,
            rgb=sample["rgb"],
            lab=sample["lab"],
            source=source.get("name", "Image"),
        )

    # ======================================================================
    # AUTOMATIC DETECTION
    # ======================================================================
    def _update_threshold_label(self):
        self.threshold_text_var.set(f"Threshold: {self.threshold_var.get():.2f}")

    def _decrease_threshold(self):
        if self._detection_running:
            return
        self.threshold_var.set(max(0.0, self.threshold_var.get() - 0.05))
        self.min_samples_var.set(self.min_samples_var.get() + 15)
        self._update_threshold_label()

    def _increase_threshold(self):
        if self._detection_running:
            return
        self.threshold_var.set(min(1.0, self.threshold_var.get() + 0.05))
        self.min_samples_var.set(max(15, self.min_samples_var.get() - 15))
        self._update_threshold_label()

    def _set_detection_busy(self, busy, status=None):
        self._detection_running = bool(busy)

        state = "disabled" if busy else "normal"
        combo_state = "disabled" if busy else "readonly"

        for widget_name in (
            "detect_button",
            "threshold_minus_button",
            "threshold_plus_button",
            "filters_button",
            "prev_source_button",
            "next_source_button",
            "open_image_button",
            "refresh_sources_button",
        ):
            try:
                getattr(self, widget_name).configure(state=state)
            except Exception:
                pass

        try:
            self.mode_combo.configure(state=combo_state)
            self.source_combo.configure(state=combo_state)
        except Exception:
            pass

        if status is not None:
            self.detection_status_var.set(status)

        if busy:
            self._spinner_angle = 0
            self._render_image()
            self._start_detection_spinner()
        else:
            self._stop_detection_spinner()
            self._render_image()

    def _start_detection_spinner(self):
        if self._spinner_after_id is not None:
            return
        self._animate_detection_spinner()

    def _animate_detection_spinner(self):
        if not self._detection_running:
            self._spinner_after_id = None
            return

        self._spinner_angle = (self._spinner_angle + 18) % 360
        self._draw_detection_overlay()

        try:
            self._spinner_after_id = self.win.after(70, self._animate_detection_spinner)
        except Exception:
            self._spinner_after_id = None

    def _stop_detection_spinner(self):
        if self._spinner_after_id is not None:
            try:
                self.win.after_cancel(self._spinner_after_id)
            except Exception:
                pass
            self._spinner_after_id = None

        try:
            self.image_canvas.delete("detection_overlay")
        except Exception:
            pass

    def _draw_detection_overlay(self):
        if not self._detection_running or not hasattr(self, "image_canvas"):
            return

        try:
            self.image_canvas.delete("detection_overlay")

            cw = max(1, self.image_canvas.winfo_width())
            ch = max(1, self.image_canvas.winfo_height())
            cx = cw / 2.0
            cy = ch / 2.0

            # Small neutral card over the lightly pixelated image.
            self.image_canvas.create_rectangle(
                cx - 92, cy - 48, cx + 92, cy + 48,
                fill="white",
                outline="#c8ccd2",
                width=1,
                tags=("detection_overlay",),
            )
            self.image_canvas.create_arc(
                cx - 18, cy - 27, cx + 18, cy + 9,
                start=self._spinner_angle,
                extent=285,
                style="arc",
                width=4,
                outline=self.BLUE,
                tags=("detection_overlay",),
            )
            self.image_canvas.create_text(
                cx, cy + 27,
                text="Detecting colors...",
                fill=self.TEXT,
                font=self.FONT_BOLD,
                tags=("detection_overlay",),
            )
        except Exception:
            pass

    def _lab_filter_bindings(self):
        """Return the Tk variables used by the shared LAB Filters dialog."""
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

    def _open_detection_filters(self):
        if self._detection_running:
            return

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
                "Enabled limits apply to automatic detection and manual area averages."
            ),
            theme=self._lab_filter_theme(),
        )

    def _on_lab_filters_applied(self, _filters=None):
        """Refresh filter UI and recompute an already-selected manual ROI."""
        self._update_filter_summary()

        current = self._current_sample
        if current and current.get("type") == "roi":
            self._sample_roi(
                current.get("x1", 0),
                current.get("y1", 0),
                current.get("x2", 0),
                current.get("y2", 0),
            )

    def _validate_detection_filters(self, parent=None):
        try:
            UtilsTools.read_lab_filter_bindings(
                self._lab_filter_bindings(),
                strict=True,
            )
            return True
        except ValueError as exc:
            self.app.custom_warning(
                "Invalid Filter",
                str(exc),
                parent=parent or self.win,
            )
            return False

    def _active_detection_filters(self):
        return UtilsTools.read_lab_filter_bindings(
            self._lab_filter_bindings(),
            strict=False,
        )

    def _update_filter_summary(self):
        filters = self._active_detection_filters()
        self.filter_summary_var.set(UtilsTools.format_lab_filters(filters, prefix=True))

        # Keep the compact toolbar button informative without adding another
        # permanent label to the image controls.
        try:
            count = len(filters)
            self.filters_button.configure(
                text="Filters..." if count == 0 else f"Filters ({count})"
            )
        except Exception:
            pass

    def _mean_rgb_with_active_lab_filters(self, rgb_pixels):
        return UtilsTools.mean_rgb_with_lab_filters(
            rgb_pixels,
            self._active_detection_filters(),
        )

    def _passes_detection_filters(self, lab):
        return UtilsTools.lab_passes_filters(
            lab,
            self._active_detection_filters(),
        )


    def _run_auto_detection(self):
        if self._detection_running:
            return

        pil = self._current_pil()
        if pil is None:
            self.app.custom_warning(
                "No Image Selected",
                "Select an image first.",
                parent=self.win,
            )
            return

        if not self._validate_detection_filters(parent=self.win):
            return

        detection_img = pil.convert("RGB")
        threshold = float(self.threshold_var.get())
        min_samples = int(self.min_samples_var.get())
        source_name = self._sources.get(self.current_source_key, {}).get("name", "Image")

        self._set_detection_busy(True, "Detecting colors...")

        def worker():
            try:
                detected = self.app.image_manager.get_fcs_image(
                    detection_img,
                    threshold,
                    min_samples,
                    max_pixels=120000,
                    max_side=800,
                    lab_quantization=0.75,
                )
                self.win.after(0, lambda: self._finish_detection(detected, source_name))
            except Exception as exc:
                msg = str(exc)
                self.win.after(0, lambda m=msg: self._finish_detection_error(m))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_detection(self, detected_colors, source_name):
        added = 0
        filtered = 0
        try:
            for item in detected_colors or []:
                rgb = item.get("rgb")
                if hasattr(rgb, "tolist"):
                    rgb = rgb.tolist()
                if isinstance(rgb, list) and len(rgb) == 1 and isinstance(rgb[0], (list, tuple, np.ndarray)):
                    rgb = rgb[0]
                rgb = tuple(int(v) for v in rgb[:3])

                if "lab" in item:
                    lab_value = item["lab"]
                    if isinstance(lab_value, dict):
                        lab = (
                            float(lab_value["L"]),
                            float(lab_value.get("A", lab_value.get("a", 0.0))),
                            float(lab_value.get("B", lab_value.get("b", 0.0))),
                        )
                    else:
                        arr = np.asarray(lab_value, dtype=float).reshape(-1)
                        lab = (float(arr[0]), float(arr[1]), float(arr[2]))
                else:
                    arr = np.asarray(UtilsTools.rgb_to_lab(rgb), dtype=float).reshape(-1)
                    lab = (float(arr[0]), float(arr[1]), float(arr[2]))

                if not self._passes_detection_filters(lab):
                    filtered += 1
                    continue

                requested_name = item.get("name") or "Detected Color"
                name = self._next_unique_name(str(requested_name).strip() or "Detected Color")
                self._add_color(name, rgb, lab, source=source_name, refresh=False)
                added += 1

            self._refresh_color_list()
        finally:
            status = f"✓ {added} color{'s' if added != 1 else ''} added"
            if filtered:
                status += f" · {filtered} filtered out"
            self._set_detection_busy(False, status)

        if added == 0 and not filtered:
            self.app.custom_warning(
                "No Colors Detected",
                "No colors were detected with the current threshold.",
                parent=self.win,
            )

    def _finish_detection_error(self, message):
        self._set_detection_busy(False, "Detection failed")
        self.app.custom_warning(
            "Error",
            f"Could not detect colors from image:\n{message}",
            parent=self.win,
        )

    # ======================================================================
    # SELECTED COLORS
    # ======================================================================
    def _next_unique_name(self, base):
        return UtilsTools.make_unique_color_name(base, self.colors.keys())

    def _add_color(self, name, rgb, lab, source=None, selected=True, refresh=True):
        name = self._next_unique_name(name)
        rgb = tuple(int(v) for v in rgb[:3])
        lab = tuple(float(v) for v in np.asarray(lab, dtype=float).reshape(-1)[:3])

        self.colors[name] = {
            "rgb": rgb,
            "lab": lab,
            "hex": UtilsTools.rgb_to_hex(rgb).upper(),
            "source": source,
        }
        self.color_checks[name] = {
            "var": tk.BooleanVar(value=bool(selected)),
            "lab": lab,
            "rgb": rgb,
        }

        if refresh:
            self._refresh_color_list()
        return name

    def _refresh_color_list(self):
        self._name_editors = []
        selected_state = {}
        for name, item in self.color_checks.items():
            try:
                selected_state[name] = bool(item["var"].get())
            except Exception:
                selected_state[name] = True

        for child in self.colors_inner.winfo_children():
            child.destroy()

        if not self.colors:
            tk.Label(
                self.colors_inner,
                text="No colors added yet.\nSample manually, run automatic detection, or add a custom color.",
                bg=self.CARD,
                fg=self.MUTED,
                font=self.FONT,
                justify="center",
                pady=22,
            ).pack(fill="x")
            self.color_checks = {}
            self._update_selected_count()
            return

        new_checks = {}

        for name, data in self.colors.items():
            var = tk.BooleanVar(value=selected_state.get(name, True))
            new_checks[name] = {
                "var": var,
                "lab": data["lab"],
                "rgb": data["rgb"],
            }

            row = tk.Frame(self.colors_inner, bg=self.CARD, bd=0)
            row.pack(fill="x", padx=6, pady=4)

            check = tk.Checkbutton(
                row,
                variable=var,
                bg=self.CARD,
                activebackground=self.CARD,
                selectcolor=self.CARD,
                command=self._update_selected_count,
            )
            check.pack(side="left", padx=(0, 4))

            swatch = tk.Canvas(row, width=26, height=26, bg=self.CARD, highlightthickness=0)
            swatch.pack(side="left", padx=(0, 8))
            swatch.create_rectangle(2, 2, 24, 24, fill=data["hex"], outline="#707070")

            text_area = tk.Frame(row, bg=self.CARD)
            text_area.pack(side="left", fill="x", expand=True)

            name_var = tk.StringVar(value=name)
            entry = tk.Entry(
                text_area,
                textvariable=name_var,
                font=self.FONT_BOLD,
                relief="flat",
                bg="#f8fafc",
                fg=self.TEXT,
                highlightthickness=1,
                highlightbackground=self.BORDER,
                highlightcolor=self.BLUE,
            )
            entry.pack(fill="x")

            lab = data["lab"]
            source_text = f" · {data['source']}" if data.get("source") else ""
            tk.Label(
                text_area,
                text=f"LAB {lab[0]:.2f}, {lab[1]:.2f}, {lab[2]:.2f}{source_text}",
                bg=self.CARD,
                fg=self.MUTED,
                font=self.FONT_SMALL,
                anchor="w",
            ).pack(fill="x", pady=(2, 0))

            entry.bind(
                "<Return>",
                lambda _e, old=name, nv=name_var: self._commit_color_name(old, nv),
            )
            entry.bind(
                "<FocusOut>",
                lambda _e, old=name, nv=name_var: self._commit_color_name(old, nv),
            )
            self._name_editors.append((name, name_var))

        self.color_checks = new_checks
        self._update_selected_count()

    def _commit_color_name(self, old_name, name_var):
        if old_name not in self.colors:
            return

        requested = str(name_var.get()).strip()[:UtilsTools.MAX_COLOR_NAME_CHARS]
        if not requested:
            name_var.set(old_name)
            self.app.custom_warning(
                "Invalid Color Name",
                "Color name cannot be empty.",
                parent=self.win,
            )
            return

        if requested == old_name:
            return

        if requested in self.colors:
            name_var.set(old_name)
            self.app.custom_warning(
                "Duplicated Color Name",
                f"The color '{requested}' already exists.",
                parent=self.win,
            )
            return

        new_colors = {}
        for key, value in self.colors.items():
            new_colors[requested if key == old_name else key] = value
        self.colors = new_colors

        if old_name in self.color_checks:
            check_data = self.color_checks.pop(old_name)
            new_checks = {}
            for key in self.colors.keys():
                if key == requested:
                    new_checks[key] = check_data
                elif key in self.color_checks:
                    new_checks[key] = self.color_checks[key]
            self.color_checks = new_checks

        # Redraw so callbacks capture the new stable key.
        self.win.after_idle(self._refresh_color_list)

    def _update_selected_count(self):
        total = len(self.color_checks)
        selected = 0
        for item in self.color_checks.values():
            try:
                if item["var"].get():
                    selected += 1
            except Exception:
                pass
        self.selected_count_var.set(f"{selected} of {total} selected")

    def _select_all_colors(self):
        for item in self.color_checks.values():
            try:
                item["var"].set(True)
            except Exception:
                pass
        self._update_selected_count()

    def _deselect_all_colors(self):
        for item in self.color_checks.values():
            try:
                item["var"].set(False)
            except Exception:
                pass
        self._update_selected_count()

    def _remove_selected_colors(self):
        names = []
        for name, item in self.color_checks.items():
            try:
                if item["var"].get():
                    names.append(name)
            except Exception:
                pass

        if not names:
            self.app.custom_warning(
                "No Color Selected",
                "Select at least one color to remove.",
                parent=self.win,
            )
            return

        for name in names:
            self.colors.pop(name, None)
            self.color_checks.pop(name, None)
        self._refresh_color_list()

    def _add_custom_color(self):
        default_name = self._next_unique_name("Custom Color")

        def on_submit(color_name, sample_lab, sample_rgb, sample_hex, dialog, input_vars):
            clean_name = str(color_name).strip()[:UtilsTools.MAX_COLOR_NAME_CHARS]
            if not clean_name:
                input_vars["status_var"].set("Enter a color name.")
                return
            if clean_name in self.colors:
                input_vars["status_var"].set("A color with this name already exists.")
                return

            self._add_color(clean_name, sample_rgb, sample_lab, source="Custom")
            dialog.destroy()

        self.app._open_custom_color_dialog(
            parent=self.win,
            title="Add Custom Color",
            subtitle="Create a color from RGB, LAB or HEX",
            submit_text="Add Color",
            require_name=True,
            default_name=default_name,
            on_submit=on_submit,
        )

    def _commit_pending_color_names(self):
        """Commit every visible editable name before validating/creating the FCS."""
        pending = list(getattr(self, "_name_editors", []))
        changed = False

        for old_name, name_var in pending:
            if old_name not in self.colors:
                continue

            requested = str(name_var.get()).strip()[:UtilsTools.MAX_COLOR_NAME_CHARS]
            if not requested:
                name_var.set(old_name)
                self.app.custom_warning(
                    "Invalid Color Name",
                    "Color name cannot be empty.",
                    parent=self.win,
                )
                return False

            if requested == old_name:
                continue

            if requested in self.colors:
                name_var.set(old_name)
                self.app.custom_warning(
                    "Duplicated Color Name",
                    f"The color '{requested}' already exists.",
                    parent=self.win,
                )
                return False

            new_colors = {}
            for key, value in self.colors.items():
                new_colors[requested if key == old_name else key] = value
            self.colors = new_colors

            if old_name in self.color_checks:
                check_data = self.color_checks.pop(old_name)
                rebuilt_checks = {}
                for key in self.colors.keys():
                    if key == requested:
                        rebuilt_checks[key] = check_data
                    elif key in self.color_checks:
                        rebuilt_checks[key] = self.color_checks[key]
                self.color_checks = rebuilt_checks

            changed = True

        if changed:
            self._refresh_color_list()

        return True


    def _create_color_space(self):
        # Preserve the last typed name even if Create is pressed immediately.
        if not self._commit_pending_color_names():
            return

        selected = []
        for name, item in self.color_checks.items():
            try:
                if item["var"].get():
                    selected.append(name)
            except Exception:
                pass

        if len(selected) < 2:
            self.app.custom_warning(
                "Not Enough Colors",
                "At least two colors must be selected to create the Color Space.",
                parent=self.win,
            )
            return

        previous_checks = getattr(self.app, "color_checks", None)
        self.app.color_checks = self.color_checks

        try:
            result = self.app.create_color_space(parent=self.win)
        finally:
            if previous_checks is None:
                try:
                    delattr(self.app, "color_checks")
                except Exception:
                    pass
            else:
                self.app.color_checks = previous_checks

        if result:
            self.close()

    def _on_colors_mousewheel(self, event):
        try:
            if platform.system() == "Darwin":
                step = -1 if event.delta > 0 else 1
            else:
                step = int(-1 * (event.delta / 120))
                if step == 0:
                    step = -1 if event.delta > 0 else 1
            self.colors_canvas.yview_scroll(step, "units")
        except Exception:
            pass
        return "break"

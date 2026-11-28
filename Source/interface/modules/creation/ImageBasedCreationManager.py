import os
import queue
import platform
import re
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font as tkfont

import numpy as np
from PIL import Image, ImageTk, ImageOps

import Source.interface.modules.common.UtilsTools as UtilsTools
from Source.interface.modules.creation.PaletteBasedCreationManager import PaletteBasedCreationManager


class ImageBasedCreationManager:
    """
    Single-workspace image-based fuzzy color space creation tool.

    The workspace keeps image browsing, manual sampling, automatic color
    detection, imported color sources and the selected-color list in one
    persistent window. Imported .cns/.fcs files contribute representatives; granular JSON
    files preserve all positive granules. The original files and saved FCS
    geometry remain unchanged.
    """

    _filter_cached_rows = True

    BG = "#f5f6f8"
    CARD = "#ffffff"
    PANEL = "#fbfbfc"
    SOFT = "#f1f3f6"
    BORDER = "#d9dde3"
    TEXT = "#1f2937"
    MUTED = "#6b7280"
    BLUE = UtilsTools.UI_ACCENT
    BLUE_SOFT = UtilsTools.UI_ACCENT_SOFT
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
        self.win.withdraw()
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
        # Zoom and pan positions are stored separately for each image.
        self._view_state = {}
        self._external_counter = 0

        # Image rendering / interaction state.
        self._canvas_photo = None
        self._detection_queue = queue.Queue()
        self._detection_poll_id = None
        self._startup_after_ids = []
        self._idle_after_ids = set()
        self._render_transform = None
        self._pan_state = None
        self._drag_start_source = None
        self._drag_current_source = None
        self._drag_start_canvas = None
        self._current_sample = None

        # Categories, each containing at least one positive granule.
        self.colors = {}
        self.color_checks = {}
        self._name_editors = []
        self._row_details = {}
        self._expanded_categories = set()
        self._granule_name_commits_in_progress = set()
        self.loaded_color_sources = {}

        # Automatic detection state.
        self._detection_running = False
        self._detection_worker = None
        self._spinner_after_id = None
        self._spinner_angle = 0

        self._create_variables()
        from Source.interface.modules.data.GranuleManager import InlineCreationTree
        self._inline_tree = InlineCreationTree(self)
        self._build_ui()
        self._load_workspace_sources(select_first=True)

        # Open a private image picker if the creation workspace starts empty.
        if open_image_on_start and not self._source_order:
            self._startup_after_ids.append(self.win.after(120, self._open_workspace_image))

        # Register the active creation window with the main application.
        try:
            self.app._register_creation_window(self.win)
        except Exception:
            pass

        self.win.bind("<Escape>", lambda _e: self.close())
        self._startup_after_ids.append(self.win.after(80, self._render_image))
        self.win.deiconify()
        self.win.focus_set()

    # Window / State
    def _configure_window_size(self):
        """Center the workspace slightly above the parent (screen-safe)."""
        width, height = min(1380, max(1120, self.win.winfo_screenwidth()-50)), 700
        try:
            self.root.update_idletasks()
            self.app.center_popup(self.win, width, height)
            # Preserve the application's positioning logic where possible.
            match = re.fullmatch(r"\d+x\d+([+-]\d+)([+-]\d+)", self.win.geometry())
            if match:
                x, y = int(match.group(1)), int(match.group(2))
            else:
                x = self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2
                y = self.root.winfo_rooty() + (self.root.winfo_height() - height) // 2
            screen_h = self.win.winfo_screenheight()
            y = max(10, min(y - 45, max(10, screen_h - height - 35)))
            self.win.geometry(f"{width}x{height}{x:+d}{y:+d}")
        except (tk.TclError, ValueError, AttributeError):
            screen_w, screen_h = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
            x = max(0, (screen_w - width) // 2)
            y = max(10, (screen_h - height) // 2 - 45)
            self.win.geometry(f"{width}x{height}+{x}+{y}")

    def close(self):
        # DBSCAN cannot be interrupted safely inside sklearn. Retain the
        # controller until its worker exits, without touching destroyed Tk.
        worker = self._detection_worker
        if worker is not None and worker.is_alive():
            self.app._retiring_workspace_workers.append((worker, self))
        self._detection_worker = None
        self._detection_running = False
        self._stop_detection_spinner()
        for callback_id in self._startup_after_ids:
            try:
                self.win.after_cancel(callback_id)
            except tk.TclError:
                pass
        self._startup_after_ids.clear()
        for callback_id in tuple(self._idle_after_ids):
            try:
                self.win.after_cancel(callback_id)
            except tk.TclError:
                pass
        self._idle_after_ids.clear()
        if self._detection_poll_id is not None:
            try:
                self.win.after_cancel(self._detection_poll_id)
            except tk.TclError:
                pass
            self._detection_poll_id = None

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

    def _schedule_idle(self, callback):
        """Run a UI task only while this creation window still exists."""
        holder = {}
        def run():
            self._idle_after_ids.discard(holder.get('id'))
            try:
                if self.win.winfo_exists():
                    callback()
            except tk.TclError:
                pass
        holder['id'] = self.win.after_idle(run)
        self._idle_after_ids.add(holder['id'])
        return holder['id']

    def _used_granule_labels(self):
        """Adapter required by the shared CustomCategoryDialog."""
        return self._all_granule_labels()

    def _create_variables(self):
        self.source_var = tk.StringVar(value="")
        self.mode_var = tk.StringVar(value="Manual")
        self.help_var = tk.StringVar(
            value="Click: sample pixel · Drag: mean color · Right-drag: pan · Wheel: zoom"
        )
        self.zoom_var = tk.StringVar(value="Fit")

        self.sample_title_var = tk.StringVar(value="No sample selected")
        self.sample_position_var = tk.StringVar(value="Click a pixel or drag an area")
        self.sample_filters_var = tk.StringVar(value="")
        self.sample_rgb_var = tk.StringVar(value="RGB: —")
        self.sample_lab_var = tk.StringVar(value="LAB: —")
        self.sample_hex_var = tk.StringVar(value="HEX: —")

        self.selected_count_var = tk.StringVar(value="0 of 0 granules selected")
        self.color_source_status_var = tk.StringVar(value="")
        self.search_var = tk.StringVar(value="")
        self._search_after_id = None
        self.sample_destination_var = tk.StringVar(value="New category")
        self.sample_action_hint_var = tk.StringVar(
            value="Choose a destination to add the sample as a granule."
        )

        self.threshold_var = tk.DoubleVar(value=0.50)
        self.min_samples_var = tk.IntVar(value=160)
        self.threshold_text_var = tk.StringVar(value="Threshold: 0.50")
        self.detection_status_var = tk.StringVar(value="")

        # LAB limits are optional and shared by ROI sampling and detection.
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
        # Explicit requested pane widths prevent the contents of a newly shown
        # extraction card from moving the sash before the first idle layout.
        paned.add(left, stretch="always", minsize=580, width=580)
        paned.add(right, stretch="always", minsize=480, width=480)

        self._build_image_workspace(left)
        self._build_selected_colors_panel(right)

        def _initial_sash():
            try:
                total = paned.winfo_width()
                if total > 1:
                    paned.sash_place(0, max(580, min(int(total * 0.55), total-480)), 1)
            except Exception:
                pass

        self._startup_after_ids.append(self.win.after_idle(_initial_sash))

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

        self.source_combo = UtilsTools.styled_combobox(
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
            activebackground=UtilsTools.UI_ACCENT_HOVER,
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

        subtitle = tk.Label(
            inner,
            text="Build FCS from image samples",
            font=self.FONT_SMALL,
            bg=self.CARD,
            fg=self.MUTED,
        )
        subtitle.pack(side="right", padx=(12, 2))
        widgets = inner.pack_slaves()
        for widget in widgets:
            widget.pack_forget()
        for i, widget in enumerate(widgets):
            widget.grid(row=0, column=i, padx=(0, 7), sticky="ew" if widget is self.source_combo else "w")
            if widget is self.source_combo:
                inner.grid_columnconfigure(i, weight=1)
        self.source_combo.configure(width=20)
        def fit_header(event):
            required = sum(w.winfo_reqwidth() + 7 for w in widgets)
            if event.width < required:
                if subtitle.winfo_manager():
                    subtitle.grid_remove()
            elif not subtitle.winfo_manager():
                subtitle.grid()
        inner.bind("<Configure>", fit_header)

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

        for button in (2, 3):
            self.image_canvas.bind(f"<Button-{button}>", self._start_pan)
            self.image_canvas.bind(f"<B{button}-Motion>", self._pan_motion)
            self.image_canvas.bind(f"<ButtonRelease-{button}>", self._end_pan)
        self.image_canvas.bind("<Button-2>", self._start_pan)
        self.image_canvas.bind("<B2-Motion>", self._pan_motion)
        self.image_canvas.bind("<ButtonRelease-2>", self._end_pan)

        self.image_canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.image_canvas.bind("<Button-4>", lambda e: self._zoom_at_event(e, 1.12))
        self.image_canvas.bind("<Button-5>", lambda e: self._zoom_at_event(e, 1 / 1.12))

        controls = tk.Frame(image_card, bg=self.CARD)
        controls.pack(fill="x", pady=(8, 0))

        right_controls = tk.Frame(controls, bg=self.CARD)
        right_controls.pack(side="right", padx=(8, 0))

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
            anchor="w",
        ).pack(side="left", padx=(2, 4))

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
        ).pack(side="left")

        self._image_help_label = tk.Label(
            controls,
            textvariable=self.help_var,
            font=self.FONT_SMALL,
            bg=self.CARD,
            fg=self.MUTED,
            anchor="center",
            justify="center",
        )
        self._image_help_label.pack(side="left", fill="x", expand=True, padx=(3, 5))
        help_font = tkfont.Font(root=self.win, font=self.FONT_SMALL)
        full_help = self.help_var.get()
        def fit_help(event):
            # Reserve the same number of lines for both modes. Avoid clipping
            # at narrower sash positions or increased Windows text scaling.
            width = max(1, event.width - 4)
            lines, used = 1, 0
            for word in full_help.split():
                size = help_font.measure(word + " ")
                if used and used + size > width:
                    lines += 1
                    used = 0
                used += size
            if (int(self._image_help_label.cget("wraplength")) != width or
                    int(self._image_help_label.cget("height")) != lines):
                self._image_help_label.configure(wraplength=width, height=lines)
        self._image_help_label.bind("<Configure>", fit_help)

        # Both extraction modes occupy the same fixed-height slot. The
        # image viewport therefore stays stable when changing modes.
        self.extraction_footer = tk.Frame(image_card, bg=self.CARD, height=153)
        self.extraction_footer.pack(fill="x", pady=(6, 0))
        self.extraction_footer.grid_propagate(False)
        self.extraction_footer.grid_columnconfigure(1, weight=1)
        self.extraction_footer.grid_rowconfigure(0, weight=1)

        extraction = self._card(self.extraction_footer, "Extraction", padx=7, pady=6)
        extraction.grid(row=0, column=0, sticky="ns", padx=(0, 7))
        extraction_controls = tk.Frame(extraction, bg=self.CARD)
        extraction_controls.pack(expand=True, fill="x", padx=2)
        self.mode_combo = UtilsTools.styled_combobox(
            extraction_controls, textvariable=self.mode_var,
            values=("Manual", "Automatic"), state="readonly", width=10)
        self.mode_combo.pack(fill="x", pady=(0, 8))
        self.mode_combo.bind("<<ComboboxSelected>>", self._on_mode_changed)
        self.filters_button = tk.Button(
            extraction_controls, text="Filters...", command=self._open_detection_filters,
            font=self.FONT, bg="#f8fafc", fg=self.TEXT,
            activebackground="#eef2f7", activeforeground=self.TEXT,
            relief="solid", bd=1, padx=7, pady=4, cursor="hand2")
        self.filters_button.pack(fill="x")

        self.manual_card = self._card(self.extraction_footer, "Manual Sample", padx=7, pady=5)
        self.manual_card.grid(row=0, column=1, sticky="nsew")
        self._build_manual_card(self.manual_card)
        self.auto_card = self._card(self.extraction_footer, "Automatic Detection", padx=7, pady=5)
        self.auto_card.grid(row=0, column=1, sticky="nsew")
        self._build_auto_card(self.auto_card)
        self.auto_card.grid_remove()
        # Reserve the footer and help bar first; the image consumes the
        # remaining height, rather than clipping controls at high DPI.
        canvas_holder.pack_forget()
        controls.pack_forget()
        self.extraction_footer.pack_forget()
        self.extraction_footer.pack(side="bottom", fill="x", pady=(6, 0))
        controls.pack(side="bottom", fill="x", pady=(8, 0))
        canvas_holder.pack(fill="both", expand=True)
        # At higher DPI or narrower sash positions, the destination label
        # moves above the combobox. The shared height is still mode-independent.
        def fit_extraction(event):
            available = max(1, event.width - extraction.winfo_reqwidth() - 7 - 18)
            self._fit_sample_footer(available)
        self.extraction_footer.bind("<Configure>", fit_extraction)

    def _fit_sample_footer(self, available):
        destination = self._sample_destination_frame
        buttons = self._sample_button_frame
        needed = destination.winfo_reqwidth() + buttons.winfo_reqwidth() + 8
        narrow = available < needed
        if getattr(self, '_sample_controls_stacked', None) != narrow:
            self._sample_controls_stacked = narrow
            if narrow:
                destination.grid(row=0, column=0, columnspan=2, padx=0)
                buttons.grid(row=1, column=0, columnspan=2, padx=0, pady=(3, 0))
            else:
                destination.grid(row=0, column=0, columnspan=1, padx=(0, 5))
                buttons.grid(row=0, column=1, columnspan=1, padx=0, pady=0)
        action_h = max(30, destination.winfo_reqheight(), buttons.winfo_reqheight())
        if narrow:
            action_h = destination.winfo_reqheight() + buttons.winfo_reqheight() + 3
        if int(self._sample_actions.cget('height')) != action_h:
            self._sample_actions.configure(height=action_h)
        # Allocate space for title, sample details and two lines of status.
        # Measure fonts rather than relying on a Windows DPI assumption.
        line = tkfont.Font(root=self.win, font=self.FONT_SMALL).metrics('linespace')
        details_h = max(61, self._sample_detail_minimum)
        height = max(153, details_h + action_h + 2*line + 32)
        if int(self.extraction_footer.cget('height')) != height:
            self.extraction_footer.configure(height=height)

    def _quiet_button(self, parent, text, command, *, danger=False,
                      strong=False, compact=False, **kwargs):
        """Subtle secondary actions; purple is reserved for the main action."""
        background = "#FBEDEE" if danger else "#F5F6F8"
        hover = "#F5DEE1" if danger else "#E9ECF1"
        return tk.Button(
            parent, text=text, command=command,
            font=self.FONT_SMALL if compact else (self.FONT_BOLD if strong else self.FONT),
            bg=background, fg=self.TEXT,
            activebackground=hover, activeforeground=self.TEXT,
            relief="solid", bd=1, highlightthickness=0,
            padx=5 if compact else 9, pady=3 if compact else 4, cursor="hand2", **kwargs
        )

    def _add_action_button(self, parent, text, command, *, role="category", **kwargs):
        """Subtle purpose-colored add actions shared across Image-Based UI.

        The final Create Color Space action retains the principal purple.
        """
        styles = {
            # A granule is an action inside an existing category, so it uses
            # the same unboxed purple text as the Palette-Based workspace.
            "granule": (self.CARD, self.BLUE, self.CARD),
            # New category and imported source are distinct secondary actions.
            "category": (UtilsTools.UI_ADD_CATEGORY_BG,
                         UtilsTools.UI_ADD_CATEGORY_FG,
                         UtilsTools.UI_ADD_CATEGORY_HOVER),
            "source": (UtilsTools.UI_ADD_SOURCE_BG,
                       UtilsTools.UI_ADD_SOURCE_FG,
                       UtilsTools.UI_ADD_SOURCE_HOVER),
        }
        bg, fg, hover = styles.get(role, styles["category"])
        return tk.Button(
            parent, text=text, command=command,
            font=self.FONT_BOLD, bg=bg, fg=fg,
            activebackground=hover, activeforeground=fg,
            disabledforeground="#8A9097",
            relief="flat", bd=0, highlightthickness=0,
            padx=7 if role == "granule" else 11,
            pady=5, cursor="hand2", **kwargs,
        )

    def _build_manual_card(self, card):
        """Stable-height sample inspection and clearly grouped add actions."""
        small_line = tkfont.Font(root=self.win, font=self.FONT_SMALL).metrics('linespace')
        title_line = tkfont.Font(root=self.win, font=self.FONT_BOLD).metrics('linespace')
        self._sample_detail_minimum = max(61, title_line + 3*small_line + 9)
        details = tk.Frame(card, bg=self.CARD, height=self._sample_detail_minimum)
        details.pack(fill="x", pady=(0, 4))
        details.grid_propagate(False)
        details.grid_rowconfigure(0, weight=1)
        details.grid_columnconfigure(1, weight=1, minsize=100)

        self.sample_swatch = tk.Canvas(
            details, width=62, height=48, bg=self.CARD,
            highlightthickness=0, bd=0,
        )
        self.sample_swatch.grid(row=0, column=0, sticky="w", padx=(9, 10))
        self.sample_swatch_rect = self.sample_swatch.create_rectangle(
            3, 3, 59, 45, fill="#D9DDE3", outline="#979CA6", width=1,
        )

        # The context is allowed to change from Pixel to ROI without changing
        # the height of the card. Reserve two lines for ROI dimensions.
        description = tk.Frame(details, bg=self.CARD)
        description.grid(row=0, column=1, sticky="nsew", padx=(0, 6))
        tk.Label(
            description, textvariable=self.sample_title_var,
            font=self.FONT_BOLD, bg=self.CARD, fg=self.TEXT,
            anchor="w",
        ).pack(fill="x")
        position_label = tk.Label(
            description, textvariable=self.sample_position_var,
            font=self.FONT_SMALL, bg=self.CARD, fg=self.MUTED,
            anchor="w", justify="left", height=2, wraplength=150,
        )
        position_label.pack(fill="x", pady=(1, 0))
        description.bind("<Configure>", lambda e: position_label.configure(wraplength=max(1, e.width-2)))
        tk.Label(
            description, textvariable=self.sample_filters_var,
            font=("Segoe UI", 8, "italic"), bg=self.CARD, fg=self.MUTED,
            anchor="w", justify="left", height=1,
        ).pack(fill="x", pady=(1, 0))

        # Plain neutral background: no gray inset around RGB/HEX/LAB values.
        values = tk.Frame(details, bg=self.CARD)
        values.grid(row=0, column=2, sticky="e", padx=(5, 1))
        for var in (self.sample_rgb_var, self.sample_hex_var, self.sample_lab_var):
            tk.Label(
                values, textvariable=var, font=self.FONT_SMALL,
                bg=self.CARD, fg=self.TEXT, anchor="e", justify="right",
            ).pack(anchor="e", pady=1)

        tk.Frame(card, bg=self.BORDER, height=1).pack(fill="x", pady=(1, 3))

        actions = self._sample_actions = tk.Frame(card, bg=self.CARD, height=30)
        actions.pack(fill="x")
        actions.pack_propagate(False)
        action_group = tk.Frame(actions, bg=self.CARD)
        action_group.pack(expand=True)
        destination = self._sample_destination_frame = tk.Frame(action_group, bg=self.CARD)
        destination.grid(row=0, column=0, padx=(0, 5))
        self._sample_destination_label = tk.Label(
            destination, text="Add sample to:",
            bg=self.CARD, fg=self.MUTED, font=self.FONT_SMALL,
        )
        self._sample_destination_label.pack(side="left", padx=(0, 6))
        self.sample_destination_combo = UtilsTools.styled_combobox(
            destination, textvariable=self.sample_destination_var,
            values=["New category"], state="readonly", width=14,
        )
        self.sample_destination_combo.pack(side="left")
        self.sample_destination_combo.bind(
            "<<ComboboxSelected>>", lambda _e: self._refresh_sample_destinations()
        )

        buttons = self._sample_button_frame = tk.Frame(action_group, bg=self.CARD)
        buttons.grid(row=0, column=1)

        self.add_sample_button = self._add_action_button(
            buttons, "Add as Category", self._add_current_sample,
            role="category", state="disabled",
        )
        self.add_sample_button.configure(font=self.FONT_SMALL_BOLD, padx=5, pady=3)

        self.add_sample_to_category_button = self._add_action_button(
            buttons, "Add as Granule", self._add_sample_to_category,
            role="granule", state="disabled",
        )
        self.add_sample_to_category_button.configure(font=self.FONT_SMALL_BOLD, padx=3, pady=3)
        self.add_sample_to_category_button.pack(side="left")
        self.add_sample_button.pack(side="left", padx=(4, 0))

        hint = tk.Label(
            card, textvariable=self.sample_action_hint_var,
            bg=self.CARD, fg=self.MUTED, font=self.FONT_SMALL,
            anchor="center", justify="center",
        )
        hint.pack(fill="x", pady=(2, 0))
        card.bind("<Configure>", lambda e: hint.configure(wraplength=max(1, e.width-20)), add="+")

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
        self.threshold_minus_button.pack(side="left", padx=(6, 3))

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
        self.threshold_plus_button.pack(side="left", padx=(0, 5))

        self.detect_button = tk.Button(
            top,
            text="Detect and Add Colors",
            command=self._run_auto_detection,
            font=self.FONT_BOLD,
            bg=self.BLUE_SOFT,
            fg=self.BLUE,
            activebackground=UtilsTools.UI_ACCENT_HOVER,
            activeforeground=self.BLUE,
            relief="solid",
            bd=1,
            padx=12,
            pady=4,
            cursor="hand2",
        )
        self.detect_button.configure(font=self.FONT_SMALL_BOLD, padx=7)
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

        explanation = tk.Label(
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
            wraplength=400,
        )
        explanation.pack(fill="x", pady=(2, 0))
        card.bind("<Configure>", lambda e: explanation.configure(wraplength=max(1, e.width-20)), add="+")

    def _build_selected_colors_panel(self, parent):
        outer = tk.Frame(parent, bg=self.BG)
        outer.pack(fill="both", expand=True, padx=(8, 0))

        card = self._card(outer, "Color Categories", padx=9, pady=8)
        card.pack(fill="both", expand=True)

        toolbar = tk.Frame(card, bg=self.CARD)
        toolbar.pack(fill="x", pady=(0, 8))

        search_box = tk.Frame(toolbar, bg=self.CARD)
        search_box.grid(row=0, column=0, sticky="w")
        tk.Label(search_box, text="Search", font=self.FONT_SMALL_BOLD,
                 bg=self.CARD, fg=self.TEXT).pack(side="left", padx=(0, 4))
        self.color_search_entry = tk.Entry(search_box, textvariable=self.search_var,
                                           font=self.FONT_SMALL, relief="solid", bd=1, width=12)
        self.color_search_entry.pack(side="left")
        tk.Button(search_box, text="Clear", command=lambda: self.search_var.set(""),
                  font=self.FONT_SMALL, bg=self.CARD, fg=self.MUTED, relief="flat",
                  bd=0, padx=3, pady=2, cursor="hand2").pack(side="left", padx=(4, 0))

        bulk = tk.Frame(toolbar, bg=self.CARD)
        bulk.grid(row=0, column=1, sticky="e", padx=(10, 0))
        toolbar.grid_columnconfigure(1, weight=1)
        self._quiet_button(
            bulk, "Select All", self._select_all_colors, compact=True,
        ).pack(side="left")
        self._quiet_button(
            bulk, "Deselect All", self._deselect_all_colors, compact=True,
        ).pack(side="left", padx=(5, 0))
        self._quiet_button(
            bulk, "Remove selected", self._remove_selected_colors, danger=True, compact=True,
        ).pack(side="left", padx=(5, 0))
        self.search_var.trace_add("write", self._schedule_color_search)
        def fit_search(event):
            narrow = event.width < bulk.winfo_reqwidth() + search_box.winfo_reqwidth() + 18
            if getattr(self, '_search_on_second_row', None) == narrow:
                return
            self._search_on_second_row = narrow
            if narrow:
                search_box.grid(row=0, column=0, columnspan=2, sticky="w", padx=0, pady=0)
                bulk.grid(row=1, column=0, columnspan=2, sticky="e", padx=0, pady=(5, 0))
            else:
                search_box.grid(row=0, column=0, columnspan=1, sticky="w", padx=0, pady=0)
                bulk.grid(row=0, column=1, columnspan=1, sticky="e", padx=(10, 0), pady=0)
        toolbar.bind("<Configure>", fit_search)

        group_toolbar = tk.Frame(card, bg=self.CARD)
        group_toolbar.pack(fill="x", pady=(0, 6))
        tk.Label(group_toolbar, textvariable=self.selected_count_var, bg=self.CARD,
                 fg=self.BLUE, font=self.FONT_SMALL_BOLD).pack(side="left", padx=3)
        tk.Button(group_toolbar, text="Create Group", command=self._inline_tree.add_group,
                  bg=self.CARD, fg=self.BLUE, font=self.FONT_SMALL_BOLD, relief="solid", bd=1,
                  activebackground=self.BLUE_SOFT, activeforeground=self.BLUE,
                  padx=12, pady=4, cursor="hand2").pack(side="right")

        list_holder = tk.Frame(card, bg=self.CARD, bd=1, relief="solid")
        list_holder.pack(fill="both", expand=True)

        self.colors_canvas = tk.Canvas(
            list_holder,
            bg=self.CARD,
            highlightthickness=0,
            bd=0,
        )
        colors_scroll = UtilsTools.styled_scrollbar(
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

        for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            self.win.bind(sequence, self._dispatch_colors_mousewheel, add='+')

        footer_sep = tk.Frame(card, bg=self.BORDER, height=1)
        footer_sep.pack(fill="x", pady=(10, 8))

        footer = tk.Frame(card, bg=self.CARD)
        footer.pack(fill="x")

        # Secondary input actions stay together. The explanatory status has
        # its own centered space and never competes with these buttons.
        source_buttons = tk.Frame(footer, bg=self.CARD)
        source_buttons.pack(fill="x")
        input_group = tk.Frame(source_buttons, bg=self.CARD)
        input_group.pack(side="right")
        self._add_action_button(
            input_group, "+ Add Color Category", self._add_custom_color,
            role="category",
        ).pack(side="left")
        self.add_color_source_button = self._add_action_button(
            input_group, "+ Add Color Source...", self._open_color_source,
            role="source",
        )
        self.add_color_source_button.pack(side="left", padx=(7, 0))

        create_row = tk.Frame(footer, bg=self.CARD)
        create_row.pack(fill="x", pady=(8, 0))
        create_row.grid_columnconfigure(0, weight=1)
        create_row.grid_columnconfigure(1, weight=0)

        tk.Label(
            create_row,
            textvariable=self.color_source_status_var,
            bg=self.CARD,
            fg=self.MUTED,
            font=self.FONT_SMALL,
            anchor="w", justify="left",
            wraplength=340,
        ).grid(row=0, column=0, sticky="w", padx=(4, 8))

        tk.Button(
            create_row,
            text="Create Color Space",
            command=self._create_color_space,
            font=self.FONT_BOLD,
            bg=self.BLUE,
            fg=self.CARD,
            activebackground=UtilsTools.UI_ACCENT_DARK,
            activeforeground=self.CARD,
            relief="flat", bd=0,
            padx=12, pady=6,
            cursor="hand2",
        ).grid(row=0, column=1, sticky="e")

        self._refresh_color_list()

    # Image Sources / Navigation
    def _load_workspace_sources(self, select_first=False):
        previous_keys = set(self._source_order)
        load_names = getattr(self.app, "load_images_names", {}) or {}
        active_workspace_keys = {f"workspace:{window_id}" for window_id in load_names}

        # Remove closed workspace images while retaining locally opened sources.
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
                pil = ImageOps.exif_transpose(img).convert("RGBA")
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

    # Image Rendering / Viewport
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

        # A pixelated preview indicates that automatic detection is running.
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

    # Manual Sampling
    def _on_mode_changed(self, _event=None):
        mode = self.mode_var.get().strip().lower()

        if mode == "automatic":
            # Manual samples do not belong to the automatic workflow.
            # Clear the current pixel/ROI selection when switching modes.
            self._clear_current_sample()

            self.help_var.set(
                "Detection uses original image · Right-drag: pan · Wheel: zoom"
            )
            self.manual_card.grid_remove()
            self.auto_card.grid()

        else:
            self.help_var.set(
                "Click: sample pixel · Drag: mean color · Right-drag: pan · Wheel: zoom"
            )
            self.auto_card.grid_remove()
            self.manual_card.grid()

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
                self._redraw_selection_overlay()
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

        rgba = pil.getpixel((int(x), int(y)))
        if not isinstance(rgba, (tuple, list)) or len(rgba) < 3:
            rgba = pil.convert('RGB').getpixel((int(x), int(y)))
        r, g, b = rgba[:3]
        a = rgba[3] if len(rgba) >= 4 else 255
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

        # Evaluate large ROIs in bounded strips to avoid materializing a
        # full-resolution RGB+LAB copy in memory.
        mean_lab_arr, used_count, total_count = UtilsTools.mean_lab_of_pil_roi(
            pil, (left, top, right + 1, bottom + 1),
            self._active_detection_filters()
        )
        if total_count <= 0:
            return

        if used_count <= 0 or mean_lab_arr is None:
            self.app.custom_warning(
                "No Valid Pixels",
                "No pixels in the selected area satisfy the active LAB filters.",
                parent=self.win,
            )
            # Invalidate the previous ROI result when its filter settings change.
            self._clear_current_sample()
            self._render_image()
            return

        lab = tuple(float(v) for v in mean_lab_arr[:3])
        # Display-only sRGB approximation; the saved prototype is the
        # unrounded LAB mean, which can lie outside the display gamut.
        mean_rgb = tuple(UtilsTools.lab_to_rgb(lab))

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
            self.add_sample_to_category_button.configure(state="disabled")
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
            self._refresh_sample_destinations()
        except Exception:
            pass

    def _redraw_selection_overlay(self):
        """Refresh only transient markers; never resize the full photograph."""
        if not hasattr(self, 'image_canvas') or self._render_transform is None:
            return
        self.image_canvas.delete('sample_marker')
        self.image_canvas.delete('drag_marker')
        self._draw_current_sample()
        self._draw_drag_preview()

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
        self.image_canvas.create_line(x - 9, y, x + 9, y, fill="#d62728", width=2, tags=('sample_marker',))
        self.image_canvas.create_line(x, y - 9, x, y + 9, fill="#d62728", width=2, tags=('sample_marker',))
        self.image_canvas.create_oval(x - 5, y - 5, x + 5, y + 5, outline="white", width=1, tags=('sample_marker',))

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
            outline="#d97706", width=2, dash=(5, 3), tags=('drag_marker',),
        )

    def _add_current_sample(self):
        """A manual pixel/ROI becomes a new one-granule category."""
        sample = self._current_sample
        if not sample:
            return
        source = self._sources.get(self.current_source_key, {})
        name = self._next_unique_name("Image Color")
        existing = [
            (key, g["label"], g["lab"])
            for key, data in self.colors.items()
            for g in data["granules"]
        ]
        _, _, error = UtilsTools.check_granule_site(name, sample["lab"], existing)
        if error:
            self.sample_action_hint_var.set(error)
            self.app.custom_warning("Cannot Add Sample", error, parent=self.win)
            return
        added = self._add_color(
            name, sample["rgb"], sample["lab"],
            source=source.get("name", "Image"),
        )
        if added is None:
            error = self._last_add_color_error or "The selected color could not be added."
            self.sample_action_hint_var.set(error)
            self.app.custom_warning("Cannot Add Sample", error, parent=self.win)
            return
        self.color_source_status_var.set("Category added from image · selected")
        self.sample_action_hint_var.set("New category created from the sample.")

    def _refresh_sample_destinations(self):
        if not hasattr(self, "sample_destination_combo"):
            return
        choices = ["New category"] + list(self.colors)
        self.sample_destination_combo.configure(values=choices)
        if self.sample_destination_var.get() not in choices:
            self.sample_destination_var.set("New category")
        category = self.sample_destination_var.get()
        sample = self._current_sample
        can_add = sample is not None and category in self.colors
        if can_add:
            # Warn before the click: a duplicate sample cannot become a new site.
            # Existing labels need not be considered here (a fresh one is made).
            from Source.geometry.Voronoi import Voronoi
            xyz = np.asarray(sample["lab"], dtype=float).reshape(3)
            for key, data in self.colors.items():
                for granule in data["granules"]:
                    other = np.asarray(granule["lab"], dtype=float).reshape(3)
                    if np.linalg.norm(xyz - other) <= Voronoi.DEFAULT_MERGE_EPS:
                        can_add = False
                        self.sample_action_hint_var.set(
                            f"This sample already matches '{granule['label']}' in '{key}'."
                        )
                        break
                if not can_add:
                    break
            else:
                self.sample_action_hint_var.set(
                    f"Add the current sample as a new granule in '{category}'."
                )
        elif sample is not None:
            self.sample_action_hint_var.set(
                "Create a category, or choose an existing one for a new granule."
            )
        else:
            self.sample_action_hint_var.set("Click a pixel or drag an area to sample.")
        self.add_sample_to_category_button.configure(
            state="normal" if can_add else "disabled"
        )

    def _add_sample_to_category(self):
        """Insert the exact LAB sample into an existing category, without UI errors."""
        sample = self._current_sample
        category = self.sample_destination_var.get()
        if not sample or category not in self.colors:
            return
        used = self._all_granule_labels()
        number = len(self.colors[category]["granules"]) + 1
        while True:
            suffix = f"-g{number}"
            candidate = category[:UtilsTools.MAX_COLOR_NAME_CHARS-len(suffix)] + suffix
            if candidate not in used:
                break
            number += 1
        entries = [dict(g) for g in self.colors[category]["granules"]]
        entries.append({"label": candidate, "lab": sample["lab"],
                        "native_rgb": UtilsTools.matching_native_rgb(sample["lab"], sample["rgb"]),
                        "enabled": True})
        error = self._set_category_granules(category, entries)
        if error:
            self.sample_action_hint_var.set(error)
            self.app.custom_warning("Cannot Add Granule", error, parent=self.win)
            self._refresh_sample_destinations()
            return
        self.color_checks[category]["var"].set(True)
        self.color_source_status_var.set(f"Sample added to '{category}'")
        self._refresh_sample_destinations()


    # Automatic Detection
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
            "add_color_source_button",
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

    def _passes_detection_filters(self, lab):
        return UtilsTools.lab_passes_filters(
            lab,
            self._active_detection_filters(),
        )


    def _run_auto_detection(self):
        if self._detection_running:
            return
        if self.app._has_any_active_job():
            self.app.custom_warning("Process Running", "Finish the current operation before detecting colors.", parent=self.win)
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

        # Ignore fully transparent pixels during color detection.
        detection_img = pil.copy()
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
                self._detection_queue.put(('ok', detected, source_name))
            except Exception as exc:
                msg = str(exc)
                self._detection_queue.put(('error', msg, source_name))

        self._detection_worker = threading.Thread(target=worker, daemon=True, name="PyFCS-ColorDetection")
        try:
            self._detection_worker.start()
        except RuntimeError as exc:
            self._detection_worker = None
            self._finish_detection_error(str(exc))
            return
        self._poll_detection_queue()

    def _poll_detection_queue(self):
        """Only Tk's main thread reads worker results and changes widgets."""
        self._detection_poll_id = None
        if not self._detection_running or not self.win.winfo_exists():
            return
        if self._detection_queue.empty():
            self._detection_poll_id = self.win.after(90, self._poll_detection_queue)
            return
        try:
            result, payload, source_name = self._detection_queue.get_nowait()
        except queue.Empty:
            self._detection_poll_id = self.win.after(90, self._poll_detection_queue)
            return
        if result == 'ok':
            self._finish_detection(payload, source_name)
        else:
            self._finish_detection_error(payload)


    def _finish_detection(self, detected_colors, source_name):
        added = 0
        filtered = 0
        added_names = []

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
                added_name = self._add_color(
                    str(requested_name).strip() or "Detected Color",
                    rgb, lab, source=source_name, refresh=False,
                )
                if added_name is None:
                    filtered += 1
                    continue
                added_names.append(added_name)
                added += 1

            if added_names:
                self._append_color_rows(added_names)
                self._update_selected_count()
                self._refresh_sample_destinations()
                self._schedule_idle(self._scroll_colors_to_bottom)

        finally:
            status = f"✓ {added} color{'s' if added != 1 else ''} added"
            if filtered:
                status += f" · {filtered} filtered out"
            self._set_detection_busy(False, status)
            if added > 0:
                self.color_source_status_var.set(
                    f"{added} color{'s' if added != 1 else ''} detected · selected"
                )

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

    # Selected Colors
    def _next_unique_name(self, base):
        return UtilsTools.make_unique_color_name(base, set(self.colors) | set(self._inline_tree.hierarchy))

    @staticmethod
    def _unique_import_label(base, occupied, max_length, additional=()):
        """Use the shared bounded naming policy for imported candidates."""
        return UtilsTools.unique_import_label(
            base, occupied, max_length, additional=additional)

    def _all_granule_labels(self, exclude_category=None):
        return {g['label'] for key, data in self.colors.items()
                if key != exclude_category for g in data.get('granules', [])}

    def _sync_representative(self, category):
        data = self.colors[category]
        items = data['granules']
        first = next((g for g in items if g.get('enabled', True)), items[0])
        lab = tuple(first['lab'])
        rgb = tuple(UtilsTools.lab_to_rgb(lab))
        data.update(lab=lab, rgb=rgb, hex=UtilsTools.rgb_to_hex(rgb).upper())
        self.color_checks[category].update(
            lab=lab, rgb=rgb, native_rgb=first.get('native_rgb'))

    def _set_category_granules(self, category, entries):
        """Update granules atomically; never re-reject unchanged imported sites.

        A source may have deliberately imported an overlapping LAB site as an
        *unselected candidate*. Editing or renaming another granule in that
        category must remain possible. Only a newly changed LAB coordinate is
        checked for collisions here; all selected sites are checked at create.
        """
        if category not in self.colors:
            return "The selected color category is no longer available."
        if not entries:
            return "Every category must contain at least one granule."

        occupied = [
            (key, g['label'], g['lab'])
            for key, data in self.colors.items() if key != category
            for g in data['granules']
        ]
        originals = self.colors[category]['granules']
        validated = []
        for index, entry in enumerate(entries):
            label, label_error = UtilsTools.check_label_name(entry.get('label'), kind='Granule')
            if label_error:
                return label_error
            try:
                point = np.asarray(entry.get('lab'), dtype=float).reshape(-1)
                if (point.size != 3 or not np.all(np.isfinite(point))
                        or not UtilsTools.is_valid_lab(point)):
                    return 'Enter valid LAB coordinates.'
                lab = tuple(float(v) for v in point)
            except (TypeError, ValueError, OverflowError):
                return 'Enter valid LAB coordinates.'
            if not label or len(label) > UtilsTools.MAX_COLOR_NAME_CHARS:
                return f'Granule name must contain 1 to {UtilsTools.MAX_COLOR_NAME_CHARS} characters.'

            # Comparing with the site at the same index supports label-only
            # edits. Checking an existing label+point pair also supports a
            # removal that shifted its sibling indices.
            unchanged = (
                (index < len(originals) and
                 np.array_equal(point, np.asarray(originals[index]['lab'], dtype=float)))
                or any(g['label'] == label and
                       np.array_equal(point, np.asarray(g['lab'], dtype=float))
                       for g in originals)
            )
            if unchanged:
                if any(other_name == label for _key, other_name, _lab in occupied):
                    return f"Granule name '{label}' is already in use."
            else:
                _clean, _point, error = UtilsTools.check_granule_site(
                    label, lab, occupied,
                    max_name_length=UtilsTools.MAX_COLOR_NAME_CHARS,
                )
                if error:
                    return error
            original = next((g for g in originals
                             if g['label'] == label and
                                np.array_equal(point, np.asarray(g['lab'], dtype=float))), None)
            native_rgb = entry.get('native_rgb')
            if native_rgb is None and original is not None:
                native_rgb = original.get('native_rgb')
            validated.append({
                'label': label, 'lab': lab, 'native_rgb': native_rgb,
                'enabled': bool(entry.get('enabled', True)),
            })
            occupied.append((category, label, lab))

        # Commit only after all checks pass; no partial edit on error.
        self.colors[category]['granules'] = validated
        self.color_checks[category]['var'].set(any(g['enabled'] for g in validated))
        self._sync_representative(category)
        self._expanded_categories.add(category)
        self._rebuild_one_category(category)
        self._update_selected_count()
        return None

    def _add_color(self, name, rgb, lab, source=None, selected=True,
                   refresh=True, granules=None, *, import_mode=False,
                   reserved_categories=None, reserved_labels=None):
        """Append a category transactionally, returning its label or None.

        Manually sampled/detected colors are validated against every current
        LAB site, as before. Imported sources may contain alternative copies
        of a prototype: for imports, validate domain and unique *names* only.
        Final FCS construction always validates selected LAB sites globally.
        """
        self._last_add_color_error = None
        requested = str(name or 'Image Color').strip() or 'Image Color'

        # These sets are passed across a batch import to avoid O(n**2)
        # name scans. For ordinary manual/detection additions, keep the
        # established naming and immediate LAB validation behavior.
        if import_mode:
            categories = (reserved_categories if reserved_categories is not None
                          else set(self.colors) | set(self._inline_tree.hierarchy))
            labels = (reserved_labels if reserved_labels is not None
                      else self._all_granule_labels())
            name = self._unique_import_label(
                requested, categories, UtilsTools.MAX_CATEGORY_NAME_CHARS)
            if name is None:
                self._last_add_color_error = 'Cannot allocate a unique category name.'
                return None
            candidate_labels = set()  # Reserve only this category's new labels.
        else:
            name = self._next_unique_name(requested)
            occupied = [
                (key, g['label'], g['lab'])
                for key, data in self.colors.items()
                for g in data['granules']
            ]

        try:
            first_lab = tuple(float(v) for v in np.asarray(lab, dtype=float).reshape(3))
            items = granules if granules is not None else [
                {'label': name, 'lab': first_lab}
            ]
            validated = []
            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    self._last_add_color_error = 'Invalid granule data.'
                    return None
                original = item.get('label') or (name if idx == 0 else f'{name}-g{idx + 1}')
                label = str(original).strip()
                if idx == 0 and label == requested:
                    label = name
                elif import_mode and name != requested and label.startswith(requested + '-g'):
                    # Imported automatic labels follow the renamed category.
                    tail = label[len(requested):]
                    if tail[2:].isdigit():
                        label = name + tail

                coords = item.get('lab', item.get('prototype'))
                if import_mode:
                    # Only reject malformed/out-of-domain LAB input, not a
                    # duplicate of a site in another imported source.
                    point = np.asarray(coords, dtype=float).reshape(-1)
                    if (point.size != 3 or not np.all(np.isfinite(point))
                            or not UtilsTools.is_valid_lab(point)):
                        self._last_add_color_error = 'Enter valid LAB coordinates.'
                        return None
                    unique_label = self._unique_import_label(
                        label, labels, UtilsTools.MAX_COLOR_NAME_CHARS,
                        additional=candidate_labels)
                    if unique_label is None:
                        self._last_add_color_error = 'Cannot allocate a unique granule name.'
                        return None
                    site = tuple(float(v) for v in point)
                    clean = unique_label
                    candidate_labels.add(clean)
                else:
                    if any(label == entry[1] for entry in occupied):
                        base, suffix = label, 2
                        while any(f'{base} ({suffix})' == entry[1] for entry in occupied):
                            suffix += 1
                        label = f'{base} ({suffix})'
                    clean, site, error = UtilsTools.check_granule_site(
                        label, coords, occupied, max_name_length=64,
                    )
                    if error:
                        self._last_add_color_error = error
                        return None
                    occupied.append((name, clean, site))
                native_rgb = item.get('native_rgb')
                if native_rgb is None and idx == 0 and not granules:
                    native_rgb = UtilsTools.matching_native_rgb(site, rgb)
                validated.append({
                    'label': clean, 'lab': site, 'native_rgb': native_rgb,
                    'enabled': bool(item.get('enabled', True)),
                })

            if not validated:
                self._last_add_color_error = 'A category requires at least one valid granule.'
                return None
            chosen = next((g for g in validated if g['enabled']), validated[0])['lab']
            preview_rgb = tuple(UtilsTools.lab_to_rgb(chosen))
        except (TypeError, ValueError, OverflowError, FloatingPointError) as exc:
            self._last_add_color_error = f'Invalid color data: {exc}'
            return None

        # Commit only after the entire category has passed its checks.
        self.colors[name] = {
            'rgb': preview_rgb, 'lab': chosen,
            'hex': UtilsTools.rgb_to_hex(preview_rgb).upper(),
            'granules': validated, 'source': source,
        }
        first = next((g for g in validated if g['enabled']), validated[0])
        self.color_checks[name] = {
            'var': tk.BooleanVar(value=bool(selected)),
            'lab': chosen, 'rgb': preview_rgb,
            'native_rgb': first.get('native_rgb'),
        }
        if import_mode:
            categories.add(name)
            labels.update(candidate_labels)
        if len(validated) > 1:
            self._expanded_categories.add(name)
        if refresh:
            self._append_color_rows([name])
            self._update_selected_count()
            self._refresh_sample_destinations()
            self._schedule_idle(self._scroll_colors_to_bottom)
        return name

    @staticmethod
    def _color_source_key(path):
        """Identify previously imported sources by normalized filename."""
        stem = os.path.splitext(os.path.basename(str(path)))[0]
        return re.sub(r"[\s_\-]+", "", stem).casefold()

    @staticmethod
    def _normalize_source_color(data):
        """Convert imported CNS/FCS representatives into valid LAB and RGB triples."""
        try:
            if isinstance(data, dict):
                lab_source = next(
                    (data[key] for key in ("positive_prototype", "lab", "Color")
                     if key in data),
                    None,
                )
                rgb_source = data.get("rgb")
            else:
                lab_source = data
                rgb_source = None

            if lab_source is None:
                return None

            if isinstance(lab_source, dict):
                lab = (
                    float(lab_source["L"]),
                    float(lab_source.get("A", lab_source.get("a"))),
                    float(lab_source.get("B", lab_source.get("b"))),
                )
            else:
                values = np.asarray(lab_source, dtype=float).reshape(-1)
                if values.size < 3:
                    return None
                lab = tuple(float(v) for v in values[:3])

            if not np.all(np.isfinite(lab)):
                return None

            if rgb_source is None:
                rgb_source = UtilsTools.lab_to_rgb(lab)
            rgb_array = np.asarray(rgb_source, dtype=float).reshape(-1)
            if rgb_array.size < 3 or not np.all(np.isfinite(rgb_array[:3])):
                return None
            rgb = tuple(int(np.clip(round(v), 0, 255)) for v in rgb_array[:3])
            return rgb, lab
        except (ValueError, TypeError, KeyError, IndexError, AttributeError):
            return None

    def _add_color_source_data(self, raw_colors, source_name):
        """Import palette candidates without comparing LAB to existing sites.

        Repeated names receive an available suffix. Existing categories remain
        untouched and imported categories start unselected; coincident LAB
        prototypes are rejected only if selected together during FCS creation.
        Malformed categories are still skipped atomically.
        """
        prepared = []
        skipped = []
        for raw_name, data in (raw_colors or {}).items():
            name = str(raw_name).strip() or 'Color'
            normalized = self._normalize_source_color(data)
            if normalized is None:
                skipped.append((name, 'Invalid or missing color coordinates'))
                continue
            rgb, lab = normalized
            granules = None
            if isinstance(data, dict) and data.get('granules'):
                granules = []
                try:
                    for index, item in enumerate(data['granules']):
                        if not isinstance(item, dict):
                            raise ValueError('Invalid granule record')
                        coords = item.get('prototype', item.get('lab'))
                        if coords is None:
                            raise ValueError('Missing granule prototype')
                        xyz = np.asarray(coords, dtype=float).reshape(3)
                        granules.append({
                            'label': item.get('label') or f'{name}-g{index+1}',
                            'lab': xyz,
                            'native_rgb': item.get('native_rgb'),
                        })
                except (ValueError, TypeError, KeyError) as exc:
                    skipped.append((name, str(exc)))
                    continue
            if granules is None and isinstance(data, dict) and data.get('native_rgb') is not None:
                granules = [{'label': name, 'lab': lab, 'native_rgb': data['native_rgb']}]
            prepared.append((name, rgb, lab, granules))

        added = []
        imported_names = {}
        used_categories = set(self.colors) | set(self._inline_tree.hierarchy)
        used_granules = self._all_granule_labels()
        for name, rgb, lab, granules in prepared:
            # For imported candidates, only uniqueness of the displayed IDs
            # is checked here. The final creator validates LAB coincidences.
            added_name = self._add_color(
                name, rgb, lab, source=source_name,
                selected=False, refresh=False, granules=granules,
                import_mode=True, reserved_categories=used_categories,
                reserved_labels=used_granules,
            )
            if added_name is None:
                skipped.append((name, self._last_add_color_error or 'Invalid category'))
                continue
            added.append(added_name)
            imported_names[name] = added_name

        self._last_import_names = imported_names
        self._last_source_import_report = {
            'added': tuple(added),
            'skipped': tuple(skipped),
        }
        if added:
            self._append_color_rows(added)
            self._update_selected_count()
            self._refresh_sample_destinations()
            self._schedule_idle(self._scroll_colors_to_bottom)
        return added

    def _open_color_source(self):
        """Import CNS/FCS representatives without replacing image samples or geometry."""
        if self._detection_running or not self._commit_pending_color_names():
            return

        initial_dir = UtilsTools.get_color_space_initial_dir()

        path = filedialog.askopenfilename(
            title="Add Color Source",
            initialdir=initial_dir,
            parent=self.win,
            filetypes=[
                ("PyFCS Color Sources", "*.json *.cns *.fcs *.JSON *.CNS *.FCS"),
                ("PyFCS JSON Color Space", "*.json *.JSON"),
                ("Color Name System", "*.cns *.CNS"),
                ("Fuzzy Color Space", "*.fcs *.FCS"),
                ("All Files", "*.*"),
            ],
        )
        if not path:
            return

        source_key = self._color_source_key(path)
        if source_key in self.loaded_color_sources:
            previous_name = self.loaded_color_sources[source_key][0]
            if not messagebox.askyesno(
                "Color Source Already Loaded",
                f"A color source with this name is already loaded:\n"
                f"'{previous_name}'\n\n"
                f"Do you want to load '{os.path.basename(path)}' again?",
                parent=self.win,
            ):
                return

        try:
            # Only color_data is used; imported volumes remain untouched.
            loaded = self.app.fuzzy_manager.load_color_file(path)
            source_name = os.path.basename(path)
            from Source.interface.modules.data.GranuleManager import confirm_tree_import, remember_import_tree, source_colors_with_native_rgb
            loaded_space = loaded.get("fuzzy_color_space")
            if not confirm_tree_import(self, loaded_space):
                return
            added = self._add_color_source_data(source_colors_with_native_rgb(loaded), source_name)
            self._inline_tree.add_import(loaded_space, self._last_import_names)
            skipped = list(getattr(self, '_last_source_import_report', {})
                           .get('skipped', ()))
            if added:
                self.loaded_color_sources.setdefault(source_key, []).append(source_name)
            summary = f"{len(added)} imported"
            if skipped:
                summary += f" · {len(skipped)} skipped"
            if added:
                summary += " · select to include"
            self.color_source_status_var.set(summary)
            if skipped:
                # A single message for the whole source, never one modal
                # warning per duplicate. Include representative reasons.
                details = '\n'.join(
                    f"• {name}: {reason}" for name, reason in skipped[:5]
                )
                if len(skipped) > 5:
                    details += f"\n... and {len(skipped)-5} more."
                self.app.custom_warning(
                    "Some Colors Were Skipped" if added else "No Colors Imported",
                    f"{len(skipped)} categor{'y' if len(skipped)==1 else 'ies'} "
                    f"could not be imported.\n\n{details}\n\n"
                    "Existing colors were preserved.",
                    parent=self.win,
                )
            elif not added:
                self.app.custom_warning(
                    "No Colors Imported",
                    "The selected source contains no valid color categories.",
                    parent=self.win,
                )
        except Exception as exc:
            message = f"The selected color source could not be loaded:\n{exc}"
            self.color_source_status_var.set("Import failed · no changes to existing colors")
            self.app.custom_warning("Color Source Error", message, parent=self.win)

    def _matches_search(self, name):
        tokens = PaletteBasedCreationManager._search_tokens(self.search_var.get())
        if not tokens or self._inline_tree.ancestor_match(name, tokens):
            return True
        data = self.colors.get(name, {})
        parts = [name]
        for granule in data.get('granules', ()):
            parts.extend((granule['label'], *self._color_values(granule)))
        searchable = ' '.join(parts).casefold().replace(',', ' ')
        return all(token.casefold() in searchable for token in tokens)

    def _schedule_color_search(self, *_args):
        # Coalesce typing into one incremental visibility update.
        if self._search_after_id is None:
            def apply():
                self._search_after_id = None
                self._inline_tree.layout()
                self.colors_canvas.yview_moveto(0)
            self._search_after_id = self._schedule_idle(apply)

    def _bulk_selection_targets(self):
        return [name for name in self.colors if self._matches_search(name)]

    def _scroll_to_bottom(self):
        self._scroll_colors_to_bottom()

    def _update_visible_selection(self, name, *, color_changed=False):
        """Update an existing row without destroying/recreating Tk widgets.

        Used by Select All / Deselect All and individual checkboxes. Expanded
        children retain their keyboard focus, widget identity and scroll
        position. Unrelated rows are not touched.
        """
        info = self._row_details.get(name)
        if not info:
            return
        data = self.colors[name]
        active = bool(self.color_checks[name]['var'].get())
        granules = data['granules']
        total = len(granules)
        selected = sum(bool(g.get('enabled', True)) for g in granules) if active else 0
        counter = info.get('count_label')
        if counter is not None:
            counter.configure(text=f'{selected}/{total}')
        for index, variable in info.get('granule_check_vars', ()):
            if index < total:
                variable.set(active and bool(granules[index].get('enabled', True)))

        if counter is not None:
            counter.configure(fg=self.BLUE if total > 1 else self.MUTED)
        if color_changed:
            for label, value in zip(info.get('value_labels', ()), self._color_values(data)):
                label.configure(text=value)
            if info.get('swatch') is not None:
                info['swatch'].configure(bg=data['hex'])

    def _category_toggle(self, name):
        enabled = bool(self.color_checks[name]['var'].get())
        if enabled:
            for granule in self.colors[name]['granules']:
                granule['enabled'] = True
        previous_lab = self.colors[name]['lab']
        self._sync_representative(name)
        changed = previous_lab != self.colors[name]['lab']
        self._update_visible_selection(name, color_changed=changed)
        self._update_selected_count()

    def _granule_toggle(self, name, index, value):
        granules = self.colors[name]['granules']
        if not 0 <= index < len(granules):
            return
        if value and not self.color_checks[name]['var'].get():
            for granule in granules:
                granule['enabled'] = False
        granules[index]['enabled'] = bool(value)
        any_enabled = any(g['enabled'] for g in granules)
        self.color_checks[name]['var'].set(any_enabled)
        previous_lab = self.colors[name]['lab']
        self._sync_representative(name)
        changed = previous_lab != self.colors[name]['lab']
        self._update_visible_selection(name, color_changed=changed)
        self._update_selected_count()

    def _toggle_details(self, name):
        info = self._row_details.get(name)
        if info is None:
            return
        if name in self._expanded_categories:
            self._expanded_categories.discard(name)
            if info['panel'] is not None:
                info['panel'].pack_forget()
        else:
            self._expanded_categories.add(name)
            if info['panel'] is None:
                info['panel'] = self._create_image_granules(name, info)
            info['panel'].pack(fill='x')
        self._refresh_image_summary(name)
        self._layout_leaf_details(name, info['guide']._flags)

    def _rebuild_one_category(self, name):
        """Recreate just the edited row, not the rest of the workspace."""
        info = self._row_details.pop(name, None)
        if info is not None:
            self._name_editors = [(key, var) for key,var in self._name_editors if key != name]
            info['wrapper'].destroy()
        self._create_color_row(name)
        self._inline_tree.layout()

    def _open_granule_picker(self, category, index=None):
        if category not in self.colors:
            return
        granules = self.colors[category]['granules']
        item = dict(granules[index]) if index is not None else None
        used = self._all_granule_labels()
        if item is not None:
            suggested = item['label']
        else:
            number = len(granules) + 1
            while True:
                suffix = f'-g{number}'
                suggested = category[:UtilsTools.MAX_COLOR_NAME_CHARS-len(suffix)] + suffix
                if suggested not in used:
                    break
                number += 1

        def submit(name, lab, _rgb, _hex, _dialog, status):
            try:
                entries = [dict(g) for g in self.colors[category]['granules']]
                new = {'label': name, 'lab': lab,
                       'enabled': item.get('enabled', True) if item else True,
                       'native_rgb': (item.get('native_rgb') if item and np.allclose(lab, item['lab'], rtol=0, atol=1e-10)
                                      else UtilsTools.matching_native_rgb(lab, _rgb))}
                if index is None:
                    entries.append(new)
                else:
                    entries[index] = new
                error = self._set_category_granules(category, entries)
                if error:
                    status.set(error)
                    return False
                return True
            except (ValueError, TypeError, KeyError, tk.TclError) as exc:
                status.set(str(exc))
                return False

        self.app._open_square_color_picker(
            parent=self.win,
            title=f'{"Edit" if item else "Add"} Granule — {category}',
            granule_name=suggested,
            initial_lab=item['lab'] if item else None,
            submit_text='Save changes' if item else 'Add granule',
            on_granule_submit=submit)

    def _remove_granule(self, category, index):
        items = self.colors[category]['granules']
        if len(items) <= 1:
            self.app.custom_warning('Cannot Remove',
                'Every category needs at least one granule. Remove the category instead.', parent=self.win)
            return
        if messagebox.askyesno('Remove Granule',
                f"Remove '{items[index]['label']}'?", parent=self.win):
            error = self._set_category_granules(
                category, [dict(g) for j, g in enumerate(items) if j != index]
            )
            if error:
                self.app.custom_warning('Cannot Remove Granule', error, parent=self.win)

    def _remove_category(self, category):
        """Remove only this category, after confirmation, without affecting others."""
        if category not in self.colors:
            return
        if not self._inline_tree.allow_remove([category]):
            return
        if not messagebox.askyesno(
            "Remove Color Category",
            f"Remove category '{category}' and all its granules?",
            icon="warning", parent=self.win,
        ):
            return
        self.colors.pop(category, None)
        self.color_checks.pop(category, None)
        self._expanded_categories.discard(category)
        if self.sample_destination_var.get() == category:
            self.sample_destination_var.set("New category")
        self.color_source_status_var.set(f"Removed category '{category}'.")
        self._refresh_color_list()

    def _move_granule(self, category, index, destination):
        """Move one granule without unexpectedly enabling other prototypes.

        An empty source category is removed only after confirmation. Imported
        alternative LAB copies remain permissible until the final FCS build.
        """
        if category == destination or category not in self.colors or destination not in self.colors:
            return False
        if not 0 <= index < len(self.colors[category].get('granules', [])):
            return False
        if not self._commit_pending_color_names():
            return False
        # A pending inline rename may have changed the menu's category keys.
        if category not in self.colors or destination not in self.colors:
            return False
        source_items = self.colors[category]['granules']
        if not 0 <= index < len(source_items):
            return False
        moving = dict(source_items[index])
        if any(item['label'] == moving['label']
               for item in self.colors[destination]['granules']):
            self.app.custom_warning(
                'Cannot Move Granule',
                f"Granule '{moving['label']}' already exists in '{destination}'.",
                parent=self.win,
            )
            return False

        is_last = len(source_items) == 1
        if is_last and not self._inline_tree.allow_remove([category]):
            return False
        if is_last and not messagebox.askyesno(
            'Move Last Granule',
            f"Moving '{moving['label']}' to '{destination}' will remove "
            f"the empty category '{category}'.\n\nContinue?",
            icon='warning', parent=self.win,
        ):
            return False

        source_selected = bool(self.color_checks[category]['var'].get())
        destination_selected = bool(self.color_checks[destination]['var'].get())
        moving_selected = source_selected and bool(moving.get('enabled', True))
        if moving_selected and not destination_selected:
            for other in self.colors[destination]['granules']:
                other['enabled'] = False
        elif not moving_selected:
            moving['enabled'] = False

        # The move is now confirmed; no additional UI callback or geometry
        # computation can modify the draft before the following assignments.
        self.colors[destination]['granules'].append(moving)
        if moving_selected:
            self.color_checks[destination]['var'].set(True)

        if is_last:
            self.colors.pop(category, None)
            self.color_checks.pop(category, None)
            self._expanded_categories.discard(category)
            if self.sample_destination_var.get() == category:
                self.sample_destination_var.set('New category')
        else:
            del source_items[index]
            self.color_checks[category]['var'].set(source_selected and any(
                item.get('enabled', True) for item in source_items))
            self._sync_representative(category)

        self._sync_representative(destination)
        self._expanded_categories.add(destination)
        self.color_source_status_var.set(
            f"Granule '{moving['label']}' moved to '{destination}'.")
        self._refresh_color_list()
        self._refresh_sample_destinations()
        return True

    def _move_menu(self, category, index, widget):
        menu = tk.Menu(self.win, tearoff=0)
        for dest in self.colors:
            if dest != category:
                menu.add_command(label=dest, command=lambda d=dest:
                                 self._move_granule(category, index, d))
        if menu.index('end') is None:
            return
        try:
            menu.tk_popup(widget.winfo_rootx(),
                          widget.winfo_rooty() + widget.winfo_height())
        finally:
            menu.grab_release()

    # Shared tree presentation from Palette; the image-specific two-line
    # rows below keep the same controls in a much narrower work area.
    _guide_set = PaletteBasedCreationManager._guide_set
    _guide_draw = PaletteBasedCreationManager._guide_draw
    _action = PaletteBasedCreationManager._action
    _swatch = PaletteBasedCreationManager._swatch
    _palette_group_row = PaletteBasedCreationManager._palette_group_row
    _layout_leaf_details = PaletteBasedCreationManager._layout_leaf_details
    def _layout_inline_tree(self):
        PaletteBasedCreationManager._layout_inline_tree(self)
        if not hasattr(self, 'colors_inner') or not self.colors_inner.winfo_exists():
            return
        label = getattr(self, '_no_color_matches', None)
        if label is None or not label.winfo_exists():
            label = self._no_color_matches = tk.Label(self.colors_inner,
                text='No colors match the current search.', bg=self.CARD, fg=self.MUTED,
                font=self.FONT, pady=20)
        if self.colors and self.search_var.get().strip() and not self._bulk_selection_targets():
            if not label.winfo_manager():
                label.pack(fill='x')
        else:
            label.pack_forget()


    def _guide(self, parent, bg, toggle=None):
        outer = getattr(parent, '_tree_row', parent)
        guide = PaletteBasedCreationManager._guide(self, outer, bg, toggle)
        if outer is not parent:
            guide.pack_configure(before=parent._tree_body)
            guide._midpoint = 17
        return guide

    def _table_row(self, parent, bg):
        row = tk.Frame(parent, bg=bg)
        row.pack(fill='x')
        body = tk.Frame(row, bg=bg)
        body.pack(side='left', fill='both', expand=True)
        top = tk.Frame(body, bg=bg, height=34)
        top.pack(fill='x')
        top.pack_propagate(False)
        actions = tk.Frame(top, bg=bg)
        actions.pack(side='right', padx=(0, 2))
        cell = tk.Frame(top, bg=bg)
        cell.pack(side='left', fill='both', expand=True)
        cell._tree_row = row
        cell._tree_body = body
        return row, cell, actions

    def _color_values(self, data):
        lab = data['lab']
        native = data.get('native_rgb')
        if native is None and data.get('granules'):
            # Representative follows the selected positive granule.
            native = next((g.get('native_rgb') for g in data['granules']
                           if tuple(g['lab']) == tuple(lab)), None)
        rgb = tuple(int(round(v)) for v in (native if native is not None else UtilsTools.lab_to_rgb(lab)))
        return (f'LAB  {lab[0]:.2f}, {lab[1]:.2f}, {lab[2]:.2f}',
                f'RGB  {rgb[0]}, {rgb[1]}, {rgb[2]}', UtilsTools.rgb_to_hex(rgb).upper())

    def _value_row(self, body, data):
        row = tk.Frame(body, bg=self.CARD)
        row.pack(fill='x', pady=(0, 4))
        labels = []
        for i, value in enumerate(self._color_values(data)):
            row.grid_columnconfigure(i, weight=1)
            label = tk.Label(row, text=value, bg=self.CARD, fg=self.MUTED, font=self.FONT_SMALL)
            label.grid(row=0, column=i, sticky='ew')
            labels.append(label)
        return row, labels

    def _add_inline_granule(self, name):
        self._open_granule_picker(name)

    def _refresh_image_summary(self, name):
        info = self._row_details[name]
        opened = name in self._expanded_categories
        singleton = len(self.colors[name]['granules']) == 1
        if opened and singleton:
            info['delete'].pack_forget()
        elif not info['delete'].winfo_manager():
            info['delete'].pack(side='left', padx=2)
        if not opened and singleton:
            info['values_row'].pack(fill='x', pady=(0, 4))
        else:
            info['values_row'].pack_forget()
        self._update_visible_selection(name, color_changed=True)

    def _create_image_granules(self, name, info):
        panel = tk.Frame(info['wrapper'], bg=self.CARD)
        items = self.colors[name]['granules']
        active = self.color_checks[name]['var']
        info['granule_check_vars'] = []
        info['granule_guides'] = []
        info['granule_name_vars'] = []
        for i, g in enumerate(items):
            row, cell, actions = self._table_row(panel, self.CARD)
            info['granule_guides'].append(self._guide(cell, self.CARD))
            var = tk.BooleanVar(value=bool(active.get() and g.get('enabled', True)))
            info['granule_check_vars'].append((i, var))
            tk.Checkbutton(cell, variable=var, bg=self.CARD, activebackground=self.CARD,
                           selectcolor=self.CARD, bd=0, highlightthickness=0, cursor='hand2',
                           command=lambda n=name,j=i,v=var:self._granule_toggle(n,j,v.get())).pack(side='left')
            rgb = g.get('native_rgb')
            if rgb is None: rgb = UtilsTools.lab_to_rgb(g['lab'])
            self._swatch(cell, UtilsTools.rgb_to_hex(rgb), 21)
            name_var = tk.StringVar(master=self.win, value=g['label'])
            entry = tk.Entry(cell, textvariable=name_var, font=self.FONT_SMALL,
                             bg=self.CARD, fg=self.TEXT, relief='solid', bd=1, width=17)
            entry.configure(validate='key', validatecommand=(self.win.register(
                lambda v, var=name_var: len(v) <= UtilsTools.MAX_COLOR_NAME_CHARS or len(v) < len(var.get())), '%P'))
            entry.pack(side='left', padx=(0, 2))
            info['granule_name_vars'].append((i, name_var))
            for event in ('<Return>', '<FocusOut>'):
                entry.bind(event, lambda _e, n=name, j=i, v=name_var: self._commit_granule_name(n, j, v))
            self._action(actions, 'Edit', lambda n=name,j=i:self._open_granule_picker(n,j)).pack(side='left')
            if len(items) > 1:
                if len(self.colors)>1:
                    move = self._action(actions, 'Move', lambda:None)
                    move.configure(command=lambda n=name,j=i,w=move:self._move_menu(n,j,w))
                    move.pack(side='left')
                self._action(actions, 'Delete', lambda n=name,j=i:self._remove_granule(n,j), True).pack(side='left')
            else:
                info['singleton_move'] = self._action(actions,'Move',lambda n=name:self._inline_tree.move_category(n))
                info['singleton_delete'] = self._action(actions,'Delete',lambda n=name:self._remove_category(n),True)
                info['singleton_delete'].pack(side='left')
            self._value_row(cell._tree_body, g)
        return panel

    def _create_color_row(self, name):
        if name not in self.colors or name not in self.color_checks:
            return
        data = self.colors[name]
        wrapper = tk.Frame(self.colors_inner, bg=self.CARD)
        row, cell, actions = self._table_row(wrapper, self.CARD)
        toggle = lambda n=name:self._toggle_details(n)
        guide = self._guide(cell, self.CARD, toggle)
        tk.Checkbutton(cell, variable=self.color_checks[name]['var'], bg=self.CARD,
                       activebackground=self.CARD, selectcolor=self.CARD, bd=0,
                       highlightthickness=0, cursor='hand2',
                       command=lambda n=name:self._category_toggle(n)).pack(side='left')
        swatch = self._swatch(cell, data['hex'], toggle=toggle)
        var = tk.StringVar(value=name)
        entry = tk.Entry(cell, textvariable=var, font=self.FONT_BOLD, relief='solid', bd=1, width=17)
        entry.pack(side='left', padx=(0, 2))
        entry.configure(validate='key', validatecommand=(self.win.register(lambda v:len(v)<=UtilsTools.MAX_CATEGORY_NAME_CHARS or len(v)<len(var.get())), '%P'))
        for event in ('<Return>', '<FocusOut>'):
            entry.bind(event, lambda _e,n=name,v=var:self._commit_color_name(n,v))
        self._name_editors.append((name,var))
        count = self._action(actions, '', toggle)
        count.pack(side='left', padx=2)
        move = self._action(actions, 'Move', lambda n=name:self._inline_tree.move_category(n))
        delete = self._action(actions, 'Delete', lambda n=name:self._remove_category(n), True)
        delete.pack(side='left', padx=2)
        values_row, labels = self._value_row(cell._tree_body, data)
        info = self._row_details[name] = dict(wrapper=wrapper, guide=guide, swatch=swatch,
            panel=None, move=move, delete=delete, count_label=count, values_row=values_row,
            value_labels=labels, granule_check_vars=[], granule_guides=[])
        if name in self._expanded_categories:
            info['panel'] = self._create_image_granules(name, info)
            info['panel'].pack(fill='x')
        self._refresh_image_summary(name)

    def _append_color_rows(self, names):
        if not hasattr(self, 'colors_inner'):
            return
        # CustomCategoryDialog calls this after committing its private list.
        # Confirm this creation in the same status area as image samples and
        # imported color sources; ordinary imports/detections use their own
        # final summaries and therefore do not match `custom=True`.
        new_custom = [name for name in names
                      if name in self.colors and self.colors[name].get('custom')]
        if new_custom:
            name = new_custom[-1]
            count = len(self.colors[name].get('granules', []))
            self.color_source_status_var.set(
                f"Category '{name}' added · {count} granule{'s' if count != 1 else ''}"
            )
        # The Move action first becomes available when a second category is
        # created. Refresh that one transition so pre-existing granule rows
        # also expose the action; ordinary additions remain append-only.
        if len(self.colors) > 1 and len(self.colors) - len(names) == 1:
            # Only the existing multi-granule panel needs its new Move action.
            # The shared reconciler preserves every other widget.
            previous = next((n for n in self.colors if n not in names), None)
            if previous in self._expanded_categories and len(self.colors[previous]['granules']) > 1:
                self._inline_tree._dirty_leaf_rows = set(getattr(self._inline_tree, '_dirty_leaf_rows', ())) | {previous}
            self._inline_tree.refresh()
            return
        if len(self.colors) == len(names):
            for child in self.colors_inner.winfo_children():
                child.destroy()
            self._name_editors = []
            self._row_details = {}
        for name in names:
            self._create_color_row(name)
        self._inline_tree.layout()
        self._refresh_sample_destinations()

    def _refresh_color_list(self):
        if not hasattr(self, 'colors_inner'):
            return
        top = self.colors_canvas.yview()[0]
        for widget in self.colors_inner.winfo_children():
            widget.destroy()
        self._name_editors = []
        self._row_details = {}
        if not self.colors:
            tk.Label(self.colors_inner,
                     text='No categories yet.\nSample an image, detect colors or add a category.',
                     bg=self.CARD, fg=self.MUTED, font=self.FONT,
                     justify='center', pady=20).pack(fill='x')
        for name in self.colors:
            self._create_color_row(name)
        self._inline_tree.layout()
        self._update_selected_count()
        self._refresh_sample_destinations()
        self._schedule_idle(lambda: self.colors_canvas.yview_moveto(top)
                            if self.colors_canvas.winfo_exists() else None)

    def _scroll_colors_to_bottom(self):
        """Move the Selected Colors viewport to the most recently added rows."""
        try:
            self.colors_canvas.update_idletasks()
            self.colors_canvas.configure(
                scrollregion=self.colors_canvas.bbox("all")
            )
            self.colors_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _commit_color_name(self, old_name, name_var):
        if old_name not in self.colors:
            return True
        requested, error = UtilsTools.check_label_name(name_var.get(), max_length=UtilsTools.MAX_CATEGORY_NAME_CHARS, kind='Category')
        if requested == old_name and not error:
            return True
        name_var.set(old_name)  # Prevent duplicate FocusOut warning on modal.
        if error:
            self.app.custom_warning('Invalid Category Name',
                f'Category name must contain 1 to {UtilsTools.MAX_CATEGORY_NAME_CHARS} characters.',
                parent=self.win)
            return False
        if requested in (set(self.colors) | set(self._inline_tree.hierarchy)):
            self.app.custom_warning('Duplicate Category',
                f"Category '{requested}' already exists.", parent=self.win)
            return False
        old_data = self.colors[old_name]
        candidate = [dict(g) for g in old_data['granules']]
        for item in candidate:
            label = item['label']
            if label == old_name:
                item['label'] = requested
            elif label.startswith(old_name+'-g') and label[len(old_name)+2:].isdigit():
                suffix = label[len(old_name):]
                item['label'] = requested[:UtilsTools.MAX_COLOR_NAME_CHARS-len(suffix)] + suffix
        # A category rename does not change geometry. Validate unique labels
        # only; imported alternative copies may deliberately share LAB with
        # other categories until the final FCS selection is validated.
        occupied_labels = self._all_granule_labels(exclude_category=old_name)
        for g in candidate:
            label = str(g['label']).strip()
            if not label or len(label) > UtilsTools.MAX_COLOR_NAME_CHARS:
                self.app.custom_warning('Invalid Category Name',
                    f'Granule names must contain 1 to {UtilsTools.MAX_COLOR_NAME_CHARS} characters.',
                    parent=self.win)
                return False
            if label in occupied_labels:
                self.app.custom_warning('Invalid Category Name',
                    f"Granule name '{label}' is already in use.", parent=self.win)
                return False
            occupied_labels.add(label)
        self.colors = {requested if key == old_name else key: data
                       for key, data in self.colors.items()}
        self.color_checks = {requested if key == old_name else key: data
                             for key, data in self.color_checks.items()}
        self.colors[requested]['granules'] = candidate
        if old_name in self._expanded_categories:
            self._expanded_categories.remove(old_name)
            self._expanded_categories.add(requested)
        self._inline_tree.rename_leaf(old_name, requested)
        self._sync_representative(requested)
        self._refresh_color_list()
        return True

    def _update_selected_count(self):
        if self._inline_tree._batch_selection:
            return
        granules = sum(sum(g.get('enabled', True) for g in data['granules'])
                       for name, data in self.colors.items()
                       if self.color_checks[name]['var'].get())
        self.selected_count_var.set(f'{granules} of {sum(len(d["granules"]) for d in self.colors.values())} granules selected')
        self._inline_tree.update_checks()

    def _select_all_colors(self):
        """Select in O(N) without recreating any category/granule widgets."""
        for name in self._bulk_selection_targets():
            check = self.color_checks[name]
            check['var'].set(True)
            for granule in self.colors[name]['granules']:
                granule['enabled'] = True
            old_lab = self.colors[name]['lab']
            self._sync_representative(name)
            self._update_visible_selection(
                name, color_changed=(old_lab != self.colors[name]['lab']))
        self._update_selected_count()

    def _deselect_all_colors(self):
        """Deselect in place; preserve granule flags for later reactivation."""
        for name in self._bulk_selection_targets():
            check = self.color_checks[name]
            check['var'].set(False)
            self._update_visible_selection(name)
        self._update_selected_count()

    def _remove_selected_colors(self):
        names = [name for name in self._bulk_selection_targets() if self.color_checks[name]['var'].get()]
        if not names:
            self.app.custom_warning('No Category Selected',
                                    'Select at least one category to remove.', parent=self.win)
            return
        if not self._inline_tree.allow_remove(names):
            return
        for name in names:
            del self.colors[name]
            del self.color_checks[name]
            self._expanded_categories.discard(name)
        self._refresh_color_list()

    def _add_custom_color(self):
        """Re-use the same full granular category dialog as Palette Creation."""
        self._inline_tree.add_category()

    def _commit_granule_name(self, category, index, variable):
        """Rename a sampled granule in place, preserving its exact coordinates."""
        items = self.colors.get(category, {}).get('granules', [])
        if not 0 <= index < len(items):
            return False
        old = items[index]['label']
        new, error = UtilsTools.check_label_name(variable.get(), kind='Granule')
        if new == old and not error:
            return True
        variable.set(old)
        if self._detection_running or self.app._has_any_active_job():
            error = 'Finish the active process first.'
        occupied = self._all_granule_labels(exclude_category=category)
        occupied.update(g['label'] for i, g in enumerate(items) if i != index)
        if error or new in occupied:
            self.app.custom_warning('Invalid Granule Name', error or f"Granule '{new}' already exists.", parent=self.win)
            return False
        items[index]['label'] = new
        variable.set(new)
        if self.search_var.get().strip():
            self._schedule_color_search()
        return True

    def _commit_pending_granule_names(self):
        for category, info in list(self._row_details.items()):
            for index, variable in info.get('granule_name_vars', []):
                if not self._commit_granule_name(category, index, variable):
                    return False
        return True

    def _commit_pending_color_names(self):
        for old_name, name_var in list(self._name_editors):
            if old_name not in self.colors:
                continue
            proposed = name_var.get().strip()
            if proposed != old_name:
                if not self._commit_color_name(old_name, name_var):
                    return False
        return True

    def _selected_category_granules(self):
        selected = {}
        for name, check in self.color_checks.items():
            if not check['var'].get():
                continue
            active = {g['label']: np.asarray(g['lab'], dtype=float)
                      for g in self.colors[name]['granules'] if g.get('enabled', True)}
            if active:
                selected[name] = active
        return selected

    def _create_color_space(self):
        if self._detection_running:
            return
        self._inline_tree.configure()

    def _dispatch_colors_mousewheel(self, event):
        """Scroll over any child of the category list, not other controls."""
        try:
            x = self.win.winfo_pointerx()
            y = self.win.winfo_pointery()
            cx, cy = self.colors_canvas.winfo_rootx(), self.colors_canvas.winfo_rooty()
            if not (cx <= x < cx + self.colors_canvas.winfo_width() and
                    cy <= y < cy + self.colors_canvas.winfo_height()):
                return None
        except tk.TclError:
            return None
        return self._on_colors_mousewheel(event)

    def _on_colors_mousewheel(self, event):
        try:
            if getattr(event, 'num', None) == 4:
                step = -1
            elif getattr(event, 'num', None) == 5:
                step = 1
            elif getattr(event, 'delta', 0):
                delta = event.delta
                step = -int(delta / 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
            else:
                return 'break'
            self.colors_canvas.yview_scroll(step, 'units')
        except tk.TclError:
            pass
        return 'break'

"""Tkinter controller for Model 3D. Owns view state, selection and surface jobs.

The application owns the active scientific model, shared T-conorm controls,
pixel inspection and common dialogs. VisualManager remains the renderer.
"""
import threading
import tkinter as tk
import numpy as np
from matplotlib.figure import Figure
from matplotlib.transforms import offset_copy
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from Source.fuzzy.GranularFuzzyColorSpace import GranularFuzzyColorSpace
from Source.interface.modules.common import UtilsTools
from Source.interface.modules.visualization.VisualManager import VisualManager


class Model3DManager:
    def __init__(self, app):
        self.app = app
        self.root = app.root
        self.graph_widget = None
        self._model_3d_surface_job = None
        self._surface_poll_id = None
        self._threshold_job_running = False

    def build_tab(self, *, CARD_BG, PANEL_BG, MUTED, TEXT, BLUE,
                  FONT, FONT_BOLD, FONT_SMALL, FONT_SMALL_BOLD):
        """Build the Model 3D tab in the existing application notebook."""
        model_3d_tab = tk.Frame(self.app.notebook, bg=CARD_BG)
        self.app.notebook.add(model_3d_tab, text="Model 3D")

        self.model_3d_options = {}

        options_bar = tk.Frame(model_3d_tab, bg=CARD_BG)
        options_bar.pack(side="top", fill="x", padx=12, pady=(12, 8))

        # Keep the shared evaluation operator above Colors. It is not a
        # geometry layer: changing it uses the existing mapping/inspection API.
        options_bar.grid_columnconfigure(0, weight=1)
        display_controls = tk.Frame(options_bar, bg=CARD_BG)
        display_controls.grid(row=0, column=0, sticky="w")
        self.app._mapping_tconorm_bar = tk.Frame(options_bar, bg=CARD_BG)
        self.app._mapping_tconorm_bar.grid(row=0, column=1, sticky="e")
        tk.Label(self.app._mapping_tconorm_bar, text="T-conorm", font=FONT_SMALL_BOLD,
                 bg=CARD_BG, fg=MUTED).pack(side="left", padx=(0, 5))
        self.app._mapping_tconorm_buttons = {}
        for mode, caption in (("bounded_sum", "Bounded Sum"), ("max", "Max")):
            button = tk.Button(
                self.app._mapping_tconorm_bar, text=caption, font=FONT_SMALL,
                relief="solid", bd=1, padx=4, pady=0, cursor="hand2",
                command=lambda value=mode: self.app._set_image_mapping_tconorm(value),
            )
            button.pack(side="left", padx=(0, 3 if mode == "bounded_sum" else 0))
            self.app._mapping_tconorm_buttons[mode] = button
        self.app._sync_image_mapping_tconorm_buttons()

        tk.Label(
            display_controls,
            text="Display:",
            font=FONT_SMALL_BOLD,
            bg=CARD_BG,
            fg=MUTED
        ).pack(side="left", padx=(0, 5))

        options = ["Representative", "Core", "0.5-cut", "Support"]
        for option in options:
            var = tk.BooleanVar(value=(option == "Representative"))
            self.model_3d_options[option] = var

            tk.Checkbutton(
                display_controls,
                text=option,
                variable=var,
                bg=CARD_BG,
                fg=TEXT,
                activebackground=CARD_BG,
                activeforeground=TEXT,
                selectcolor=CARD_BG,
                font=FONT,
                command=self.on_option_select,
                cursor="hand2"
            ).pack(side="left", padx=(0, 4))

        def _fit_model_options(event):
            # Keep all controls accessible when the main sash is dragged left.
            narrow = event.width < (display_controls.winfo_reqwidth()
                                    + self.app._mapping_tconorm_bar.winfo_reqwidth() + 8)
            if narrow == getattr(options_bar, "_pyfcs_wrapped", None):
                return
            options_bar._pyfcs_wrapped = narrow
            self.app._mapping_tconorm_bar.grid_configure(
                row=1 if narrow else 0, column=0 if narrow else 1,
                columnspan=2 if narrow else 1, sticky="e",
                pady=(4, 0) if narrow else 0,
            )

        options_bar.bind("<Configure>", _fit_model_options, add="+")

        # Internal split for the 3D model tab
        paned = tk.PanedWindow(
            model_3d_tab,
            orient="horizontal",
            sashrelief="flat",
            bg=CARD_BG,
            sashwidth=6,
            bd=0
        )
        paned.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # Match the figure background, including the reserved Pixel Information footer.
        self.Canvas1 = tk.Frame(
            paned,
            bg=CARD_BG,
            borderwidth=1,
            relief="solid",
            width=760,
            highlightthickness=0
        )
        paned.add(self.Canvas1, stretch="always", minsize=300)

        # Color button panel
        self.colors_frame = tk.Frame(
            paned,
            bg=CARD_BG,
            width=185,
            bd=1,
            relief="solid",
            highlightthickness=0
        )
        paned.add(self.colors_frame, minsize=165, stretch="never", width=185)
        self._model_3d_paned = paned

        self.colors_frame.configure(width=185)

        def _position_model_3d_sash(_event=None):
            # Keep the default width through startup geometry negotiation.
            # Once the user drags the sash, preserve their chosen width.
            try:
                if not paned.winfo_exists() or paned.winfo_width() < 471:
                    return
                width = paned.winfo_width()
                current = width - paned.sash_coord(0)[0] - 6
                wanted = min(185, max(165, width - 306))
                if (not getattr(paned, "_pyfcs_sash_manual", False) and abs(current-wanted) > 2) or current < 165:
                    paned.sash_place(0, width - wanted - 6, 1)
            except tk.TclError:
                pass

        def _remember_manual_sash(event):
            if paned.identify(event.x, event.y):
                paned._pyfcs_sash_manual = True

        paned.bind("<ButtonPress-1>", _remember_manual_sash, add="+")
        def _queue_model_3d_sash(_event=None):
            # Tk reports the new outer width before the sash geometry settles.
            if getattr(paned, "_pyfcs_sash_pending", None) is None:
                def apply():
                    paned._pyfcs_sash_pending = None
                    _position_model_3d_sash()
                paned._pyfcs_sash_pending = paned.after_idle(apply)

        def _cancel_model_3d_sash(_event=None):
            pending = getattr(paned, "_pyfcs_sash_pending", None)
            if pending is not None:
                paned.after_cancel(pending)
                paned._pyfcs_sash_pending = None

        paned.bind("<Configure>", _queue_model_3d_sash, add="+")
        paned.bind("<Destroy>", _cancel_model_3d_sash, add="+")
        _queue_model_3d_sash()

        # Keep selector controls fixed while scrolling a long hierarchy.
        self._model_3d_header = tk.Frame(self.colors_frame, bg=CARD_BG)
        self._model_3d_header.pack(side="top", fill="x", padx=6, pady=(7, 3))
        heading = tk.Frame(self._model_3d_header, bg=CARD_BG)
        heading.pack(fill="x", pady=(0, 4))
        tk.Label(heading, text="Colors", bg=CARD_BG, fg=TEXT, font=FONT_BOLD).pack(side="left")
        self._model_3d_count_var = tk.StringVar(value="")
        self._model_3d_tree_notice = tk.Label(self._model_3d_header, text="", bg=CARD_BG,
                                              fg=MUTED, font=FONT_SMALL, wraplength=150)
        tk.Label(heading, textvariable=self._model_3d_count_var, bg=CARD_BG,
                 fg=BLUE, font=FONT_SMALL_BOLD).pack(side="right")

        self.scrollable_canvas = tk.Canvas(
            self.colors_frame,
            bg=CARD_BG,
            highlightthickness=0,
            borderwidth=0,
            width=132
        )
        self.scrollable_canvas.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=(0, 8))

        self.scrollbar = UtilsTools.styled_scrollbar(
            self.colors_frame,
            orient="vertical",
            command=self.scrollable_canvas.yview
        )
        self.scrollbar.pack(side="right", fill="y", pady=(0, 8), padx=(0, 4))

        self.scrollable_canvas.configure(yscrollcommand=self.scrollbar.set)

        self.inner_frame = tk.Frame(self.scrollable_canvas, bg=CARD_BG)
        self.inner_frame.bind(
            "<Configure>",
            lambda _e: self.scrollable_canvas.configure(
                scrollregion=self.scrollable_canvas.bbox("all")
            )
        )

        self.app._register_vertical_mousewheel_canvas(self.scrollable_canvas)

        self.colors_canvas_window_id = self.scrollable_canvas.create_window(
            (0, 0),
            window=self.inner_frame,
            anchor="nw"
        )

        def resize_color_inner_frame(event):
            try:
                self.scrollable_canvas.itemconfig(
                    self.colors_canvas_window_id,
                    width=max(event.width - 4, 90)
                )
            except Exception:
                pass

        self.scrollable_canvas.bind("<Configure>", resize_color_inner_frame)

        self.color_buttons_frame = tk.Frame(
            self._model_3d_header,
            bg=CARD_BG
        )
        self.color_buttons_frame.pack(fill="x", pady=(2, 5))

        button_style = {
            "width": 1,
            "height": 1,
            "font": ("Segoe UI", 8, "bold"),
            "relief": "flat",
            "bd": 0,
            "cursor": "hand2",
            "bg": "#eef2f7",
            "fg": "#1f2937",
            "activebackground": "#e5e7eb",
            "activeforeground": "#1f2937",
            "highlightthickness": 0
        }

        self.select_all_button = tk.Button(
            self.color_buttons_frame,
            text="Select All",
            command=self.select_all_color,
            **button_style
        )
        if self.app.COLOR_SPACE:
            self.select_all_button.pack(side="left", fill="x", expand=True, padx=(0, 3))

        self.deselect_all_button = tk.Button(
            self.color_buttons_frame,
            text="Deselect All",
            command=self.deselect_all_color,
            **button_style
        )
        if self.app.COLOR_SPACE:
            self.deselect_all_button.pack(side="left", fill="x", expand=True, padx=(3, 0))

        # Search only filters the sidebar; it never changes 3D selection.
        self._model_3d_search_var = tk.StringVar(value="")

        self._model_3d_search_frame = tk.Frame(self._model_3d_header, bg=CARD_BG)

        tk.Label(self._model_3d_search_frame, text="Search", bg=CARD_BG,
                 fg=TEXT, font=FONT_SMALL_BOLD).pack(side="left", padx=(0, 4))
        tk.Button(self._model_3d_search_frame, text="Clear", bg=CARD_BG, fg=MUTED,
                  font=FONT_SMALL, relief="flat", bd=0, highlightthickness=0,
                  cursor="hand2", command=lambda: self._model_3d_search_var.set("")).pack(side="right", padx=(3, 0))
        tk.Entry(self._model_3d_search_frame, textvariable=self._model_3d_search_var,
                 font=FONT_SMALL, bg=CARD_BG, fg=TEXT, relief="solid", bd=1,
                 width=9).pack(side="left")

        self._model_3d_search_var.trace_add(
            "write", lambda *_: self._filter_model_3d_colors())
        self.tab = model_3d_tab
        model_3d_tab.bind("<Destroy>", self._on_tab_destroy, add="+")

    def _on_tab_destroy(self, event):
        """Stop speculative surface work and its Tk poll on application exit."""
        if event.widget is not self.tab:
            return
        job = self._model_3d_surface_job
        if job is not None:
            job["cancel"].set()
            self._model_3d_surface_job = None
        if self._surface_poll_id is not None:
            try:
                self.root.after_cancel(self._surface_poll_id)
            except tk.TclError:
                pass
            self._surface_poll_id = None
        if self.graph_widget is not None:
            pending = getattr(self.graph_widget, "_idle_draw_id", None)
            if pending is not None:
                try:
                    self.root.after_cancel(pending)
                except tk.TclError:
                    pass
                self.graph_widget._idle_draw_id = None


    def _geometry_for_categories(self, selected_labels, granule_labels=None):
        """Select real Voronoi/Core/Support objects without rebuilding geometry.

        ``granule_labels=None`` retains the legacy all-granules semantics used
        while loading a space; an explicit empty set selects no geometry.
        """
        space = getattr(self.app, "fuzzy_color_space", None)
        selected = set(selected_labels)
        if isinstance(space, GranularFuzzyColorSpace):
            granules = {p.label for label in space.get_all_category_labels()
                        if label in selected for p in space.get_descendant_granules(label)}
            if granule_labels is not None:
                granules.intersection_update(granule_labels)
            selected_entries = [(cat, i) for cat in space.categories
                                for i, p in enumerate(cat.prototypes) if p.label in granules]
            return (
                [cat.prototypes[i] for cat, i in selected_entries],
                [cat.cores[i] for cat, i in selected_entries],
                [cat.supports[i] for cat, i in selected_entries],
            )
        indices = [i for i, proto in enumerate(getattr(self.app, "prototypes", []))
                   if proto.label in selected]
        return ([self.app.prototypes[i] for i in indices],
                [self.app.cores[i] for i in indices],
                [self.app.supports[i] for i in indices])


    def _selected_model_granules(self):
        """Return visible granule names, defaulting to all before controls exist."""
        space = getattr(self.app, "fuzzy_color_space", None)
        if not isinstance(space, GranularFuzzyColorSpace):
            return None
        state = getattr(self, "selected_granules", None)
        if not isinstance(state, dict):
            return {p.label for cat in space.categories for p in cat.prototypes}
        return {name for name, var in state.items() if var.get()}


    def _granular_visualization_data(self, active=None):
        """Return markers for only the selected real granules in native geometry."""
        space = getattr(self.app, "fuzzy_color_space", None)
        state = getattr(self, "selected_granules", None)
        if active is None and state is not None:
            active = {n for n, v in state.items() if v.get()}
        sites = getattr(self, "_model_3d_sites", {})
        if getattr(self, "_model_3d_site_space", None) is not space:
            prototypes = (space.get_all_prototypes() if isinstance(space, GranularFuzzyColorSpace)
                          else space.prototypes)
            sites = {p.label: (p, {"positive_prototype": np.asarray(p.positive, dtype=float)},
                              VisualManager._fallback_model_hex(p.positive, space.color_space))
                     for p in prototypes}
        color_data, hexes = {}, {}
        for name, (_proto, row, hex_color) in sites.items():
            if active is None or name in active:
                color_data[name] = row
                hexes[hex_color] = row["positive_prototype"]
        return color_data, hexes


    def _init_3d_canvas(self):
        """
        Create the matplotlib 3D figure, axis and Tk canvas only once.

        The interactive button is also created here and kept alive across redraws.
        """
        if hasattr(self, "fig_3d") and self.fig_3d is not None:
            return

        self.fig_3d = Figure(figsize=(8, 6), dpi=120, facecolor=self.Canvas1.cget("bg"))
        self.ax_3d = self.fig_3d.add_subplot(111, projection="3d")

        self.graph_widget = FigureCanvasTkAgg(self.fig_3d, master=self.Canvas1)
        # Fill the entire viewport with one Matplotlib canvas. Reserve the
        # Pixel Information margin INSIDE the figure, not with Tk pack padding.
        widget = self.graph_widget.get_tk_widget()
        widget.configure(bg=self.Canvas1.cget("bg"), bd=0, highlightthickness=0)
        widget.pack(fill="both", expand=True)
        self.graph_widget.mpl_connect("resize_event", self._layout_model_3d_axes)
        self._model_3d_initial_view = None
        self._last_plot_signature = None
        self._model_3d_orientation_signature = None
        self._model_3d_inset_refreshing = False
        self._model_3d_mouse_click_id = self.graph_widget.mpl_connect(
            "button_press_event", self._on_model_3d_inset_click)

        # The axes3D renderer may draw a clipped tick/line into this corner
        # for some spaces and window sizes. An opaque Tk overlay isolates the
        # button from matplotlib artists without changing the 3D plot.
        self._model_3d_action_host = tk.Frame(
            self.Canvas1, bg="#ffffff", bd=0,
            highlightthickness=0,
        )
        self._model_3d_action_host.place(
            relx=1.0, rely=0.0, anchor="ne", width=126, height=65)
        self.add_button = tk.Button(
            self._model_3d_action_host,
            text="Interactive\nView ↗",
            font=("Segoe UI", 8, "bold"),
            justify="center",
            bg="#FFFFFF",
            fg=UtilsTools.UI_ACCENT_DARK,
            activebackground=UtilsTools.UI_ACCENT_SOFT,
            activeforeground=UtilsTools.UI_ACCENT_DARK,
            relief="solid",
            bd=1,
            highlightthickness=0,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self._on_add_graph_current,
        )
        self.add_button.pack(side="top", anchor="e", padx=(0, 13), pady=(10, 0))
        self._model_3d_action_host.lift()


    def _layout_model_3d_axes(self, _event=None):
        """Reserve the overlay margin within the full-height figure.

        Use the same plot/compass proportions as the previous shorter canvas,
        mapping its coordinates into the portion above Pixel Information.
        Reapply on resize without rebuilding geometry or resetting the camera.
        """
        if self.graph_widget is None or self.ax_3d is None:
            return
        widget = self.graph_widget.get_tk_widget()
        height = widget.winfo_height()
        if height <= 1:
            height = max(1, self.Canvas1.winfo_height() - 2)
        footer_height = max(36, round(30 * float(self.root.tk.call("tk", "scaling"))))
        footer = min(0.25, footer_height / height)
        usable = 1.0 - footer

        def position(x, y, width, h):
            return [x, footer + usable * y, width, usable * h]

        narrow = self.Canvas1.winfo_width() < 555
        self.ax_3d.set_position(position(0.02 if narrow else 0.08,
                                         0.15, 0.80 if narrow else 0.83, 0.75))
        self.ax_3d.zaxis.labelpad = 3 if narrow else 10
        marker = VisualManager.get_orientation_inset(self.fig_3d)
        if marker is not None:
            # Keep the six LAB direction labels below the main x-axis label.
            # The inset axes contain empty margins, so their box can extend
            # slightly into the reserved footer while the glyph remains above it.
            marker.set_position(position(0.0, -0.035, 0.16, 0.16))


    def _on_add_graph_current(self):
        """
        Open the interactive 3D figure using the currently active display options.
        """
        selected_options = [
            key for key, var in self.model_3d_options.items()
            if var.get()
        ]

        if selected_options:
            pending = getattr(self, "_model_3d_surface_job", None)
            if pending is not None:
                layers = {"Core": self.selected_core, "0.5-cut": self.selected_alpha, "Support": self.selected_support}
                native = self.app.fuzzy_color_space.color_space
                if any(not VisualManager.has_cached_projected_display_faces(p, self.app.volume_limits, native, native)
                       for layer in selected_options for p in layers.get(layer, ())):
                    self.app.custom_warning("Model 3D", "Display surfaces are being prepared. Try Interactive View when they are ready.")
                    return
            self.on_add_graph(selected_options)


    @staticmethod
    def _model_3d_view_snapshot(ax):
        """Capture camera orientation and zoom/pan limits in plotting order."""
        return {
            "elev": float(ax.elev), "azim": float(ax.azim),
            "roll": float(getattr(ax, "roll", 0)),
            "xlim": tuple(ax.get_xlim()), "ylim": tuple(ax.get_ylim()),
            "zlim": tuple(ax.get_zlim()),
        }


    @staticmethod
    def _apply_model_3d_view(ax, state):
        """Restore orientation and navigation limits after a model redraw."""
        if not state:
            return
        try:
            ax.view_init(elev=state["elev"], azim=state["azim"],
                         roll=state.get("roll", 0))
        except TypeError:  # Matplotlib 3.3–3.5 lack the roll parameter.
            ax.view_init(elev=state["elev"], azim=state["azim"])
        ax.set_xlim(state["xlim"])
        ax.set_ylim(state["ylim"])
        ax.set_zlim(state["zlim"])


    def _on_model_3d_inset_click(self, event):
        """The orientation marker is a reset button, not a second 3D camera."""
        if event.button != 1 or not getattr(self.app, "COLOR_SPACE", False):
            return
        marker = VisualManager.get_orientation_inset(getattr(self, "fig_3d", None))
        if marker is None or event.inaxes is not marker:
            return
        original = getattr(self, "_model_3d_initial_view", None)
        ax = getattr(self, "ax_3d", None)
        if original is None or ax is None:
            return
        self._apply_model_3d_view(ax, original)
        self.graph_widget.draw_idle()


    def _clear_model_3d_color_controls(self, hide_buttons=False):
        """Discard old model rows and search when the active space changes.

        The rows are ordinary Tk frames, separate from the Matplotlib canvas:
        destroying the figure alone leaves obsolete category controls behind.
        Clear callback references first so StringVar tracing cannot repack them.
        """
        rows = getattr(self, "_model_3d_rows_container", None)
        self._model_3d_category_rows = {}
        self._model_3d_category_counts = {}
        self._model_3d_color_groups = {}
        self._model_3d_sites = {}
        self._model_3d_site_space = None
        self._model_3d_legacy_labs = {}
        self._model_3d_selection_key = None
        self._model_3d_active = frozenset()
        self._model_3d_enabled_counts = {}
        self._model_3d_match_cache = {}
        self._model_3d_tree_limited = False
        notice = getattr(self, "_model_3d_tree_notice", None)
        if notice is not None:
            notice.pack_forget()
        self._last_plot_signature = None
        self._model_3d_rows_container = None
        self._last_color_button_signature = None
        self.selected_colors = {}
        self.selected_granules = None
        self.color_buttons = []
        self._model_3d_expanded_categories = set()
        count_var = getattr(self, "_model_3d_count_var", None)
        if count_var is not None:
            count_var.set("")
        if rows is not None:
            try:
                if rows.winfo_exists():
                    rows.destroy()
            except tk.TclError:
                pass
        search = getattr(self, "_model_3d_search_var", None)
        if search is not None and search.get():
            search.set("")
        if hide_buttons:
            for attr in ("select_all_button", "deselect_all_button"):
                button = getattr(self, attr, None)
                if button is not None:
                    try:
                        button.pack_forget()
                    except tk.TclError:
                        pass


    def _destroy_model_3d_widget(self):
        """Cancel a pending TkAgg idle paint before disposing of its canvas."""
        widget = self.graph_widget.get_tk_widget()
        pending = getattr(self.graph_widget, "_idle_draw_id", None)
        if pending is not None:
            try:
                widget.after_cancel(pending)
            except tk.TclError:
                pass
            self.graph_widget._idle_draw_id = None
        widget.destroy()


    def _reset_3d_canvas(self):
        """
        Fully reset the embedded 3D canvas when a new color space is loaded.
        """
        if hasattr(self, "graph_widget") and self.graph_widget is not None:
            try:
                self._destroy_model_3d_widget()
            except Exception:
                pass
            self.graph_widget = None

        if hasattr(self, "add_button") and self.add_button is not None:
            try:
                self.add_button.destroy()
            except Exception:
                pass
            self.add_button = None

        host = getattr(self, "_model_3d_action_host", None)
        if host is not None:
            try:
                host.destroy()
            except tk.TclError:
                pass
            self._model_3d_action_host = None

        self.fig_3d = None
        self.ax_3d = None
        self._model_3d_initial_view = None
        self._model_3d_orientation_signature = None
        self._clear_model_3d_color_controls()


    def _reset_3d_view_state(self):
        """
        Reset cached 3D view state.

        Call this when a new color space is loaded, because the plot structure
        and the available colors may have changed completely.
        """
        self._last_selected_options = None
        self._last_color_button_signature = None
        self._last_plot_signature = None
        self.selected_granules = None
        self._model_3d_expanded_categories = set()
        self._model_3d_initial_view = None

        if hasattr(self, "filtered_points"):
            self.filtered_points = {}
        self._threshold_analysis_cache = None
        self._threshold_display_mode = None

        if self.graph_widget:
            try:
                self._destroy_model_3d_widget()
            except Exception:
                pass
            self.graph_widget = None
            self.fig_3d = None
            self.ax_3d = None

        # Do not leave an orphaned Interactive View overlay on redraw/reset.
        action_host = getattr(self, "_model_3d_action_host", None)
        if action_host is not None:
            try:
                action_host.destroy()
            except tk.TclError:
                pass
            self._model_3d_action_host = None
            self.add_button = None


    def _threshold_view_signature(self, selected_options=None):
        """Identify the exact geometry shown by the threshold search.

        Cache identity includes the source model, selected prototype volumes,
        and active geometric layer. A different selection or a rebuilt model
        therefore cannot silently reuse stale threshold points.
        """
        if selected_options is None:
            selected_options = [
                name for name, var in self.model_3d_options.items() if var.get()
            ]
        by_priority = (
            ("Support", self.selected_support),
            ("0.5-cut", self.selected_alpha),
            ("Core", self.selected_core),
        )
        active = next(
            ((name, volumes) for name, volumes in by_priority
             if name in selected_options and volumes), None
        )
        if active is None:
            return None
        layer, volumes = active
        space = getattr(self.app, "fuzzy_color_space", None)
        color_space = getattr(space, "color_space", "LAB")
        signature = (
            id(space), layer, color_space, 0.25, "CIEDE2000", 0.8, 1.8,
            tuple((proto.label, id(proto.voronoi_volume)) for proto in volumes),
        )
        return signature, volumes, color_space


    def _threshold_points_for_current_view(self, selected_options=None):
        """Select cached PT, AT or both without re-running the search."""
        cache = getattr(self, "_threshold_analysis_cache", None)
        mode = getattr(self, "_threshold_display_mode", None)
        current = self._threshold_view_signature(selected_options)
        if not cache or not current or current[0] != cache["signature"]:
            return {}
        result = cache["results"]
        if mode == "BOTH":
            return {"PT": result["PT"]["points"],
                    "AT_ONLY": result["AT_ONLY"]["points"]}
        if mode in ("PT", "AT"):
            return {mode: result[mode]["points"]}
        return {}


    def _prepare_model_3d_surfaces(self, signature, selected_options, space):
        """Warm exact render polygons off Tk; prioritize the latest Display request.

        Prewarm all layers for moderate models (up to 600 selected volumes).
        Large models stay demand-driven. Never mutate membership geometry.
        """
        layers = {"Core": self.selected_core, "0.5-cut": self.selected_alpha,
                  "Support": self.selected_support}
        domain = self.app.volume_limits
        color_space = getattr(space, "color_space", "LAB")
        def ready(p):
            return VisualManager.has_cached_projected_display_faces(p, domain, color_space, color_space)
        requested = tuple(p for name, prototypes in layers.items() if name in selected_options
                          for p in prototypes if not ready(p))
        button = getattr(self, "add_button", None)
        if button is not None and button.winfo_exists():
            button.configure(text="Preparing\nsurfaces…" if requested else "Interactive\nView ↗",
                             state=tk.DISABLED if requested else tk.NORMAL)
        total = sum(len(protos) for protos in layers.values())
        extra = tuple(p for protos in layers.values() for p in protos
                      if not ready(p)) if total <= 600 else ()
        pending = getattr(self, "_model_3d_surface_job", None)
        if pending is not None:
            if pending["space"] is space:
                pending["priority"] = requested
                pending["extra"] = extra
                pending["signature"] = signature
            else:
                pending["cancel"].set()
            return not requested
        if not requested and not extra:
            return True
        job = {"signature": signature, "space": space, "error": None,
               "finished": threading.Event(), "cancel": threading.Event(),
               "priority": requested, "extra": extra}
        self._model_3d_surface_job = job

        def work():
            done = set()
            try:
                while not job["cancel"].is_set():
                    proto = next((p for p in (*job["priority"], *job["extra"]) if id(p) not in done), None)
                    if proto is None:
                        break
                    VisualManager._cached_projected_display_faces(proto, domain, color_space, color_space)
                    done.add(id(proto))
            except Exception as exc:
                job["error"] = exc
            finally:
                job["finished"].set()

        def poll():
            self._surface_poll_id = None
            if self._model_3d_surface_job is not job:
                return
            current = getattr(self.app, "fuzzy_color_space", None)
            if current is not space:
                job["cancel"].set()
            if not job["finished"].is_set():
                # Publish requested layers as soon as they are ready, without
                # waiting for speculative warming of the other display layers.
                if current is space and job["priority"] and all(
                        ready(p) for p in job["priority"]):
                    job["priority"] = ()
                    self.on_option_select()
                self._surface_poll_id = self.root.after(25, poll)
                return
            self._model_3d_surface_job = None
            if job["error"] is not None and current is space:
                self._model_3d_failed_signature = job["signature"]
                self.app.custom_warning("Model 3D", f"Could not prepare display surfaces: {job['error']}")
            current_button = getattr(self, "add_button", None)
            if current_button is not None and current_button.winfo_exists():
                current_button.configure(text="Interactive\nView ↗", state=tk.NORMAL)
            if getattr(self.app, "COLOR_SPACE", False):
                if current is not space:
                    self._last_plot_signature = None
                self.on_option_select()

        try:
            threading.Thread(target=work, daemon=True, name="PyFCS-Model3DSurfaces").start()
        except (RuntimeError, OSError):
            self._model_3d_surface_job = None
            if button is not None and button.winfo_exists():
                button.configure(text="Interactive\nView ↗", state=tk.NORMAL)
            raise
        self._surface_poll_id = self.root.after(25, poll)
        return not requested


    def on_option_select(self):
        """
        Refresh the embedded 3D model using the current visualization options.

        The matplotlib figure is reused instead of recreated on every update.
        """
        if not self.app.COLOR_SPACE:
            return

        self._init_3d_canvas()
        selected_options = [
            key for key, var in self.model_3d_options.items()
            if var.get()
        ]
        # Initialize or synchronize the sidebar before deriving plot/cache data.
        self.display_color_buttons(self.app.color_matrix)
        self._update_model_3d_selection()
        self.filtered_points = self._threshold_points_for_current_view(selected_options)
        # A repeated request for the same model/layers/selection need not clear
        # Matplotlib's axes or rebuild its collections. Threshold result objects
        # are published as a new cache by the analysis worker.
        plot_signature = (id(self.ax_3d), getattr(self, "_last_color_button_signature", None),
                          getattr(self, "_model_3d_selection_key", None),
                          tuple(selected_options), str(self.app.file_base_name),
                          self.Canvas1.winfo_width() < 555,
                          tuple((k, id(v)) for k, v in self.filtered_points.items()),
                          getattr(self, "_threshold_display_mode", None))
        if plot_signature == getattr(self, "_last_plot_signature", None):
            # Returning to the already displayed layer can happen while a
            # different layer is still being prepared. Update its priority
            # and button state even if no new Matplotlib paint is necessary.
            if getattr(self, "_model_3d_surface_job", None) is not None:
                self._prepare_model_3d_surfaces(plot_signature, selected_options,
                                               getattr(self.app, "fuzzy_color_space", None))
            return
        if plot_signature == getattr(self, "_model_3d_failed_signature", None):
            return
        self._model_3d_failed_signature = None
        space = getattr(self.app, "fuzzy_color_space", None)
        if not self._prepare_model_3d_surfaces(plot_signature, selected_options, space):
            return

        # Even with no visible layers, draw the empty *model-domain* axes.
        # A bare ax.cla() resets all limits to (0, 1); the next update would
        # capture those temporary limits as camera state and restore them
        # over the newly rendered model, hiding every representative/volume.
        # The shared renderer handles selected_options=[] without geometry
        # while retaining valid LAB/RGB limits, orientation and view state.

        space = getattr(self.app, "fuzzy_color_space",None)
        plot_centroids, plot_hex = (self._granular_visualization_data(self._model_3d_active) if space else
                                    (self.selected_centroids, self.selected_hex_color))
        previous_view = (self._model_3d_view_snapshot(self.ax_3d)
                         if self._model_3d_initial_view is not None else None)
        VisualManager.plot_combined_3D(
            self.ax_3d, self.app.file_base_name, plot_centroids,
            self.selected_core, self.selected_alpha, self.selected_support,
            self.app.volume_limits, plot_hex, selected_options, self.filtered_points,
            color_space=space.color_space if space else "LAB",
            display_color_space=space.color_space if space else "LAB",
            reuse_surface_collection=True,
        )

        # Anchor the heading to the figure, not the 3D axes. Its height
        # must not depend on the aspect ratio or camera of the model.
        narrow = self.Canvas1.winfo_width() < 555
        header_x = 0.42 if narrow else 0.47
        display_name = str(self.app.file_base_name).replace("_", " ")
        title_transform = offset_copy(self.fig_3d.transFigure, fig=self.fig_3d,
                                      y=-8, units="points")
        self.ax_3d.text2D(
            header_x, 1.0, display_name,
            transform=title_transform,
            fontsize=10.2,
            color="#242633",
            fontweight="semibold",
            ha="center", va="top",
        )
        if space:
            subtitle = f"{space.typology_description}  ·  {space.color_space}"
            if self.filtered_points:
                display_mode = getattr(self, "_threshold_display_mode", None)
                mode_label = {"PT": "PT < 0.8", "AT": "AT < 1.8",
                              "BOTH": "PT + AT"}.get(display_mode)
                if mode_label:
                    subtitle += f"  ·  {mode_label}"
            subtitle_transform = offset_copy(self.fig_3d.transFigure, fig=self.fig_3d,
                                             y=-21, units="points")
            self.ax_3d.text2D(
                header_x, 1.0, subtitle,
                transform=subtitle_transform,
                fontsize=6.9,
                fontweight="normal",
                color=UtilsTools.UI_ACCENT_MUTED,
                ha="center", va="top",
            )

        # Preserve the approved layout inside the full-height figure.
        self._layout_model_3d_axes()

        if self._model_3d_initial_view is None:
            self._model_3d_initial_view = self._model_3d_view_snapshot(self.ax_3d)
        elif previous_view is not None:
            self._apply_model_3d_view(self.ax_3d, previous_view)
        self._last_plot_signature = plot_signature
        # TkAgg combines multiple queued paints into one; the model and all
        # render inputs are still updated synchronously before returning.
        self.graph_widget.draw_idle()
        action_host = getattr(self, "_model_3d_action_host", None)
        if action_host is not None and action_host.winfo_exists():
            action_host.lift()

        if hasattr(self.app, "lab_value_frame"):
            self.app.lab_value_frame.lift()


    def _clear_model_3d_plot(self):
        """
        Remove the current 3D plot widget content.
        """
        if self.graph_widget:
            try:
                self._destroy_model_3d_widget()
            except Exception:
                pass
            self.graph_widget = None
            self.fig_3d = None
            self.ax_3d = None

        # Do not leave an orphaned Interactive View overlay on redraw/reset.
        action_host = getattr(self, "_model_3d_action_host", None)
        if action_host is not None:
            try:
                action_host.destroy()
            except tk.TclError:
                pass
            self._model_3d_action_host = None
            self.add_button = None

        self._last_plot_signature = None


    def on_add_graph(self, selected_options):
        """
        Generate the interactive Plotly figure and open it in the default browser.
        """
        space = getattr(self.app, "fuzzy_color_space",None)
        plot_centroids, plot_hex = (self._granular_visualization_data() if space else
                                    (self.selected_centroids, self.selected_hex_color))
        granular_categories = None
        color_tree = {"roots": [["granule", name] for name in plot_centroids], "children": {}}
        if isinstance(space, GranularFuzzyColorSpace):
            granular_categories = {}
            color_tree = {"roots": [["category", name] for name in space.get_root_categories()],
                          "children": {name: list(space.get_category_children(name))
                                       for name in space.get_all_category_labels()}}
            stack = [((), n) for n in reversed(space.get_root_categories())]
            visited = set()
            while stack:
                ancestors, name = stack.pop()
                if name in visited:
                    continue
                visited.add(name)
                path = ancestors + (name,)
                for kind, child in reversed(space.get_category_children(name)):
                    if kind == "category":
                        stack.append((path, child))
                    else:
                        granular_categories.setdefault(child, " / ".join(path))
        fig = VisualManager.plot_more_combined_3D(
            filename=self.app.file_base_name,
            color_data=plot_centroids,
            core=self.selected_core,
            alpha=self.selected_alpha,
            support=self.selected_support,
            volume_limits=self.app.volume_limits,
            hex_color=plot_hex,
            selected_options=selected_options,
            filtered_points=self.filtered_points,
            color_space=space.color_space if space else "LAB",
            display_color_space=space.color_space if space else "LAB",
            granule_categories=granular_categories,
        )

        if hasattr(self.app, "lab_value_frame"):
            self.app.lab_value_frame.lift()

        self.app._open_plotly_figure_in_browser(
            fig,
            filename_prefix="pyfcs_3d_plot", color_tree=color_tree
        )


    def select_all_color(self):
        """Show every atomic prototype or every real granule."""
        if not self.app.COLOR_SPACE:
            return
        for var in getattr(self, "selected_colors", {}).values():
            var.set(True)
        for var in (getattr(self, "selected_granules", None) or {}).values():
            var.set(True)
        self.select_color()


    def deselect_all_color(self):
        """Hide all model objects, preserving the category/granule layout."""
        if not self.app.COLOR_SPACE:
            return
        for var in getattr(self, "selected_colors", {}).values():
            var.set(False)
        for var in (getattr(self, "selected_granules", None) or {}).values():
            var.set(False)
        self.select_color()


    def _toggle_model_3d_category(self, category_label):
        """Toggle all of a category's granules (one in atomic models)."""
        category_var = getattr(self, "selected_colors", {}).get(category_label)
        if category_var is None:
            return
        enabled = category_var.get() == 1
        groups = getattr(self, "_model_3d_color_groups", {})
        for name in groups.get(category_label, (category_label,)):
            granule_var = (getattr(self, "selected_granules", None) or {}).get(name)
            if granule_var is not None:
                granule_var.set(enabled)
        self.select_color()


    def _toggle_model_3d_granule(self, _granule_label):
        """Keep parent categories in sync when a granule is toggled."""
        self.select_color()


    def _sync_model_3d_category_counts(self, active=None):
        """Read Tcl variables once, and reuse the active set across all parents."""
        groups = getattr(self, "_model_3d_color_groups", {})
        state = getattr(self, "selected_granules", None) or {}
        if active is None:
            active = frozenset(name for name, var in state.items() if var.get() == 1)
        if active == getattr(self, "_model_3d_active", None) and getattr(self, "_model_3d_enabled_counts", None):
            return active
        self._model_3d_active = active
        counts = self._model_3d_enabled_counts = {}
        counters = getattr(self, "_model_3d_category_counts", {})
        count_var = getattr(self, "_model_3d_count_var", None)
        if count_var is not None:
            count_var.set(f"{len(active)}/{len(state)}")
        for category, names in groups.items():
            enabled = counts[category] = sum(name in active for name in names)
            selected = getattr(self, "selected_colors", {}).get(category)
            target = 1 if enabled == len(names) else (-1 if enabled else 0)
            if selected is not None and selected.get() != target:
                selected.set(target)
            for counter in counters.get(category, ()):
                text = f"{enabled}/{len(names)}"
                if counter.cget("text") != text:
                    counter.configure(text=text)
        return active


    def select_color(self):
        """Render after a visibility change, without rebuilding geometry."""
        self.on_option_select()


    def _update_model_3d_selection(self):
        """Prepare geometry and native marker inputs from one visibility snapshot."""
        space = getattr(self.app, "fuzzy_color_space", None)
        active = self._sync_model_3d_category_counts()
        key = (id(space), active)
        if key == getattr(self, "_model_3d_selection_key", None):
            return
        if isinstance(space, GranularFuzzyColorSpace):
            entries = [(cat, i) for cat in space.categories
                       for i, p in enumerate(cat.prototypes) if p.label in active]
            self.selected_centroids = {cat.label: self.app.color_data[cat.label]
                                       for cat, _i in entries if cat.label in self.app.color_data}
            self.selected_alpha = [cat.prototypes[i] for cat, i in entries]
            self.selected_core = [cat.cores[i] for cat, i in entries]
            self.selected_support = [cat.supports[i] for cat, i in entries]
            # Keep the historical LAB fields for other callers, but calculate
            # each site's LAB and display HEX only once per loaded model.
            cache = self._model_3d_legacy_labs
            for proto in self.selected_alpha:
                if proto.label not in cache:
                    lab = space.lab_from_model(proto.positive)
                    cache[proto.label] = (UtilsTools.lab_to_hex(lab), lab)
            self.selected_hex_color = {cache[p.label][0]: cache[p.label][1]
                                       for p in self.selected_alpha}
        else:
            self.selected_centroids = {color: self.app.color_data[color] for color in self.app.color_data
                                       if color in active}
            selected_labs = {tuple(np.asarray(row["positive_prototype"]).reshape(-1))
                             for row in self.selected_centroids.values()}
            self.selected_hex_color = {k: v for k, v in self.app.hex_color.items()
                                       if tuple(np.asarray(v).reshape(-1)) in selected_labs}
            self.selected_alpha, self.selected_core, self.selected_support = self._geometry_for_categories(active)
        self._model_3d_selection_key = key


    def _toggle_model_3d_expanded(self, path):
        expanded = self._model_3d_expanded_categories
        if path in expanded:
            expanded.remove(path)
        else:
            expanded.add(path)
        if self._model_3d_search_var.get().strip():
            self._filter_model_3d_colors()
        else:
            self._model_3d_tree_limited = False
            self._model_3d_apply_branch(path)
            self._show_model_3d_tree_limit()


    def _model_3d_make_row(self, parent, path, kind, name, last):
        """Create a single row. Descendants are constructed only on demand."""
        records = self._model_3d_category_rows
        if path in records:
            return records[path]
        white = "#ffffff"
        wrapper = tk.Frame(parent, bg=white)
        row = tk.Frame(wrapper, bg=white)
        row.pack(fill="x", pady=2)
        is_category = kind == "category"
        children = self._model_3d_children.get(name, ()) if is_category else ()
        arrow = None
        if children:
            arrow = tk.Button(row, text="▸", bg=white, fg=UtilsTools.UI_ACCENT,
                              activebackground=white, relief="flat", bd=0, highlightthickness=0, padx=0, pady=0,
                              font=("Segoe UI", 9, "bold"), width=1, cursor="hand2",
                              command=lambda: self._toggle_model_3d_expanded(path))
            arrow.pack(side="left")
        else:
            tk.Frame(row, width=13, bg=white).pack(side="left")
        var = self.selected_colors[name] if is_category else self.selected_granules[name]
        command = (lambda: self._toggle_model_3d_category(name)) if is_category else (lambda: self._toggle_model_3d_granule(name))
        tk.Checkbutton(row, variable=var, command=command, onvalue=1, offvalue=0,
                       tristatevalue=-1, bg=white, activebackground=white, selectcolor=white,
                       highlightthickness=0, bd=0, padx=0, cursor="hand2").pack(side="left")
        names = self._model_3d_color_groups[name] if is_category else (name,)
        swatch = tk.Canvas(row, width=14, height=14, bg=white, highlightthickness=0, bd=0)
        swatch.pack(side="left", padx=(1, 4))
        swatch.create_rectangle(0, 0, 14, 14, fill=self._model_3d_hexes[names[0]], outline="#aab0b8")
        label = tk.Label(row, text=name, bg=white, fg="#1f2937", justify="left", anchor="w",
                         font=("Segoe UI", 8, "bold" if is_category else "normal"), cursor="hand2")
        label.pack(side="left", fill="x", expand=True)
        count = None
        if is_category and (len(names) > 1 or children and any(k == "category" for k, _ in children)):
            enabled = getattr(self, "_model_3d_enabled_counts", {}).get(name, len(names))
            count = tk.Label(row, text=f"{enabled}/{len(names)}", bg=white,
                             fg=UtilsTools.UI_ACCENT if len(names) > 1 else "#6b7280",
                             font=("Segoe UI", 7))
            count.pack(side="right")
            self._model_3d_category_counts.setdefault(name, []).append(count)
        def activate(_event=None):
            if children:
                self._toggle_model_3d_expanded(path)
            else:
                var.set(0 if var.get() == 1 else 1)
                command()
        for widget in (label, swatch):
            widget.bind("<Button-1>", activate)
        def wrap_text(_event=None):
            width = max(35, row.winfo_width() - sum(w.winfo_reqwidth() for w in row.pack_slaves() if w is not label) - 4)
            if int(label.cget("wraplength")) != width:
                label.configure(wraplength=width)
        row.bind("<Configure>", wrap_text, add="+")
        branch = tk.Frame(wrapper, bg=white)
        # A narrow continuous guide, inside the wrapper, so collapse removes it too.
        guide = tk.Canvas(branch, width=12, height=1, bg=white, highlightthickness=0, bd=0)
        guide.pack(side="left", fill="y")
        holder = tk.Frame(branch, bg=white)
        holder.pack(side="left", fill="both", expand=True)
        def draw_guides(_event=None):
            guide.delete("all")
            visible = holder.pack_slaves()
            if not visible:
                return
            ys = [r.winfo_y() + r.pack_slaves()[0].winfo_height()//2 + r.pack_slaves()[0].winfo_y() for r in visible]
            guide.create_line(3, 0, 3, ys[-1], fill="#c9bfda")
            for y in ys:
                guide.create_line(3, y, 12, y, fill="#c9bfda")
        guide.bind("<Configure>", draw_guides, add="+")
        holder.bind("<Configure>", draw_guides, add="+")
        record = dict(wrapper=wrapper, row=row, branch=branch, holder=holder, arrow=arrow,
                      children=children, name=name, kind=kind, guide=draw_guides)
        records[path] = record
        return record


    def _model_3d_apply_branch(self, path, query="", inherited=False):
        record = self._model_3d_category_rows[path]
        children = record["children"]
        if not children:
            return
        opened = path in self._model_3d_expanded_categories or bool(query)
        if opened and len(path) >= 64:
            self._model_3d_tree_limited = True
            opened = False
        if not opened:
            record["branch"].pack_forget()
            record["arrow"].configure(text="▸")
            return
        record["branch"].pack(fill="x")
        record["arrow"].configure(text="▾")
        for i, (kind, name) in enumerate(children):
            child_path = path + ((kind, name),)
            matches = not query or inherited or self._model_3d_matches(kind, name, query)
            child = self._model_3d_category_rows.get(child_path)
            if not matches:
                if child: child["wrapper"].pack_forget()
                continue
            if child is None:
                if len(self._model_3d_category_rows) >= len(self._model_3d_roots) + 2000:
                    self._model_3d_tree_limited = True
                    break
                child = self._model_3d_make_row(record["holder"], child_path, kind, name, i == len(children)-1)
                child["wrapper"].bind("<Configure>", record["guide"], add="+")
                child["row"].bind("<Configure>", record["guide"], add="+")
            if not child["wrapper"].winfo_manager():
                following = next((self._model_3d_category_rows.get(path+((k,n),)) for k,n in children[i+1:]
                                  if self._model_3d_category_rows.get(path+((k,n),)) and self._model_3d_category_rows[path+((k,n),)]["wrapper"].winfo_manager()), None)
                opts = {"before": following["wrapper"]} if following else {}
                child["wrapper"].pack(fill="x", **opts)
            self._model_3d_apply_branch(child_path, query, inherited or bool(query and query in name.casefold()))
        record["guide"]()


    def _model_3d_matches(self, kind, name, query):
        cache = self._model_3d_match_cache
        root = (kind, name)
        stack = [(root, False)]
        while stack:
            key, done = stack.pop()
            if key in cache:
                continue
            k, n = key
            if query in n.casefold():
                cache[key] = True
            elif k != "category":
                cache[key] = False
            else:
                children = self._model_3d_children.get(n, ())
                if done:
                    cache[key] = any(cache[child] for child in children)
                else:
                    stack.append((key, True))
                    stack.extend((child, False) for child in children if child not in cache)
        return cache[root]


    def _show_model_3d_tree_limit(self):
        notice = getattr(self, "_model_3d_tree_notice", None)
        if notice is None:
            return
        if getattr(self, "_model_3d_tree_limited", False):
            notice.configure(text="Branch limit reached. Refine search or Clear.")
            notice.pack(fill="x")
        else:
            notice.pack_forget()


    def _reset_model_3d_descendant_rows(self):
        """Reclaim cached nested widgets after exceptionally broad searches."""
        rows = self._model_3d_category_rows
        for path, record in tuple(rows.items()):
            if len(path) == 2:
                record["wrapper"].destroy()
            if len(path) > 1:
                del rows[path]
        for name, widgets in self._model_3d_category_counts.items():
            self._model_3d_category_counts[name] = [w for w in widgets if w.winfo_exists()]


    def _filter_model_3d_colors(self):
        """Search shows matching branches without changing selection or the camera."""
        rows = getattr(self, "_model_3d_category_rows", {})
        if not rows:
            return
        query = self._model_3d_search_var.get().strip().casefold()
        if len(rows) >= len(self._model_3d_roots) + 2000:
            self._reset_model_3d_descendant_rows()
        self._model_3d_tree_limited = False
        self._model_3d_match_cache = {}
        roots = self._model_3d_roots
        for i, name in enumerate(roots):
            path = (("category", name),)
            record = rows[path]
            if not query or self._model_3d_matches("category", name, query):
                if not record["wrapper"].winfo_manager():
                    following = next((rows[(("category", n),)]["wrapper"] for n in roots[i+1:]
                                      if rows[(("category", n),)]["wrapper"].winfo_manager()), None)
                    record["wrapper"].pack(fill="x", pady=(1, 3), **({"before":following} if following else {}))
                self._model_3d_apply_branch(path, query, bool(query and query in name.casefold()))
            else:
                record["wrapper"].pack_forget()
        self._show_model_3d_tree_limit()


    def display_color_buttons(self, colors):
        """Display semantic roots; every checkbox maps to unique geometric sites."""
        space = getattr(self.app, "fuzzy_color_space", None)
        if space is None:
            return
        signature = (id(space), tuple(space.get_all_category_labels()))
        if signature == getattr(self, "_last_color_button_signature", None):
            return
        self._clear_model_3d_color_controls()
        labels = space.get_all_category_labels()
        granular = isinstance(space, GranularFuzzyColorSpace)
        self._model_3d_roots = tuple(space.get_root_categories())
        self._model_3d_color_groups = ({n: tuple(p.label for p in space.get_descendant_granules(n)) for n in labels}
                                       if granular else {n: (n,) for n in labels})
        self._model_3d_children = {n: tuple(space.get_category_children(n)) if granular else () for n in labels}
        prototypes = space.get_all_prototypes() if granular else space.prototypes
        self._model_3d_hexes = {p.label: VisualManager._fallback_model_hex(p.positive, space.color_space) for p in prototypes}
        self._model_3d_site_space = space
        self._model_3d_legacy_labs = {}
        self._model_3d_sites = {p.label: (p, {"positive_prototype": np.asarray(p.positive, dtype=float)},
                                        self._model_3d_hexes[p.label]) for p in prototypes}
        self.selected_granules = {p.label: tk.IntVar(master=self.inner_frame, value=1) for p in prototypes}
        self.selected_colors = {n: tk.IntVar(master=self.inner_frame, value=1) for n in labels}
        holder = tk.Frame(self.inner_frame, bg="#ffffff")
        holder.pack(fill="x", padx=2)
        self._model_3d_rows_container = holder
        for i, name in enumerate(self._model_3d_roots):
            path = (("category", name),)
            record = self._model_3d_make_row(holder, path, "category", name, i == len(self._model_3d_roots)-1)
            record["wrapper"].pack(fill="x", pady=(1, 3))
        self._sync_model_3d_category_counts()
        self._last_color_button_signature = signature
        # The clear helper also clears the historic controls list. Keep this
        # alias for old reset/layout code, but use the tree records internally.
        self.color_buttons = [r["row"] for r in self._model_3d_category_rows.values()]


    def get_umbral_points(self, threshold=None, mode=None):
        """Compute PT + AT together, then display either or both on demand."""
        if not getattr(self.app, "COLOR_SPACE", False):
            self.app.custom_warning(
                "No Color Space", "Load a fuzzy color space before displaying PT or AT."
            )
            return
        if self.app._has_any_active_job():
            self.app.custom_warning("Process Running", "A processing task is already running.")
            return

        if mode is None:
            mode = "PT" if threshold is not None and abs(float(threshold) - 0.8) < 1e-9 else "AT"
        mode = str(mode).upper()
        if mode not in ("PT", "AT", "BOTH"):
            self.app.custom_warning("Threshold Mode", "Choose PT, AT, or Both.")
            return

        selected_options = [
            name for name, var in self.model_3d_options.items() if var.get()
        ]
        current = self._threshold_view_signature(selected_options)
        if current is None:
            self.app.custom_warning(
                "Select a Volume", "Enable Core, 0.5-cut or Support before displaying thresholds."
            )
            return
        signature, selected_volume, geometric_mode = current

        # Switching PT <-> AT <-> Both only changes which stored layer is
        # plotted. Neither the metric nor the geometric search is repeated.
        cached = getattr(self, "_threshold_analysis_cache", None)
        if cached is not None and cached["signature"] == signature:
            self._threshold_display_mode = mode
            self.on_option_select()
            return

        self._threshold_job_running = True
        try:
            self.app.show_loading(
                title="Processing Color Evaluation",
                message="Computing PT and AT in a single exploration...",
                note="Both results will be available independently in Display Threshold."
            )
        except Exception:
            self._threshold_job_running = False
            raise

        def run_threshold_process():
            try:
                result = self.app.color_manager.filter_points_with_thresholds(
                    selected_volume, step=0.25, metric="CIEDE2000",
                    color_space=geometric_mode, pt_threshold=0.8, at_threshold=1.8, inclusive=True,
                )
                for region in ("PT", "AT"):
                    self.app.color_manager.create_csv(
                        self.app.file_base_name, result[region]["limits"],
                        mode=region, color_space=geometric_mode,
                    )

                def finish_success():
                    try:
                        # The model/selection may have changed while the
                        # background worker was running: never display stale
                        # results against a different geometry.
                        latest = self._threshold_view_signature()
                        if latest is None or latest[0] != signature:
                            return
                        self._threshold_analysis_cache = {
                            "signature": signature, "results": result,
                        }
                        self._threshold_display_mode = mode
                        self.on_option_select()
                    except Exception as exc:
                        self.app.custom_warning(
                            "Threshold Visualization Error", str(exc)
                        )
                    finally:
                        self._threshold_job_running = False
                        self.app.hide_loading()

                self.root.after(0, finish_success)
            except Exception as exc:
                error_message = str(exc)

                def finish_error(message=error_message):
                    self._threshold_job_running = False
                    self.app.hide_loading()
                    self.app.custom_warning(
                        "Threshold Processing Error",
                        f"Could not compute the threshold regions: {message}",
                    )

                try:
                    self.root.after(0, finish_error)
                except (RuntimeError, tk.TclError):
                    self._threshold_job_running = False

        threading.Thread(target=run_threshold_process, daemon=True).start()


    def clear_selection(self):
        """Clear the display selection when the application has no model."""
        self.selected_centroids = {}
        self.selected_alpha = []
        self.selected_core = []
        self.selected_support = []
        self._clear_model_3d_color_controls(hide_buttons=True)
        self._model_3d_search_frame.pack_forget()
        self._model_3d_search_var.set("")

    def show_selection_controls(self):
        """Show selection and search controls after a successful model load."""
        if not self._model_3d_search_frame.winfo_manager():
            self._model_3d_search_frame.pack(anchor="center", pady=(0, 5))
        if not self.select_all_button.winfo_manager():
            self.select_all_button.pack(side="left", fill="x", expand=True, padx=(0, 3))
        if not self.deselect_all_button.winfo_manager():
            self.deselect_all_button.pack(side="left", fill="x", expand=True, padx=(3, 0))

    def refresh_model(self):
        """Synchronize markers/volumes with the application’s loaded model."""
        self.selected_centroids = self.app.color_data
        self.selected_hex_color = self.app.hex_color
        self.selected_alpha, self.selected_core, self.selected_support = (
            self._geometry_for_categories(self.app.color_data)
        )
        self._model_3d_selection_key = None
        self._last_plot_signature = None
        self.on_option_select()

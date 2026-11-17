import os
import sys

# Resolve project imports before loading third-party modules.
current_dir = os.path.dirname(os.path.abspath(__file__))

if getattr(sys, "frozen", False):
    BASE_PATH = os.path.dirname(sys.executable)
else:
    BASE_PATH = os.path.abspath(os.path.join(current_dir, "..", ".."))

if BASE_PATH not in sys.path:
    sys.path.insert(0, BASE_PATH)


import math
import time
import copy
import random
import platform
import colorsys
import itertools
import threading
import webbrowser
import numpy as np
import tkinter as tk
from pathlib import Path
from matplotlib.figure import Figure
from PIL import Image, ImageTk, ImageOps, ImageDraw, ImageFont, ImageEnhance
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from tkinter import ttk, Menu, filedialog, messagebox, Scrollbar, DISABLED, NORMAL

# Project modules
from Source.input_output.Input import Input
from Source.interface.modules.VisualManager import VisualManager
from Source.colorspace.ReferenceDomain import ReferenceDomain
from Source.fuzzy.FuzzyColorSpace import FuzzyColorSpace
from Source.fuzzy.GranularFuzzyColorSpace import GranularFuzzyColorSpace
from Source.fuzzy.FuzzyColorSpaceBuilder import FuzzyColorSpaceBuilder, rebuild_in_color_space, lab_to_rgb_model_checked
from Source.interface.modules.ColorProcessingEngine import ColorProcessingEngine
from Source.interface.modules.FuzzyColorSpaceManager import FuzzyColorSpaceManager
from Source.interface.modules.ColorEvaluationManager import ColorEvaluationManager
from Source.interface.modules.ImageInspectionManager import ImageInspectionManager
from Source.interface.modules.ImageWorkspaceManager import ImageWorkspaceManager
from Source.interface.modules.ImageBasedCreationManager import ImageBasedCreationManager
from Source.interface.modules.PaletteBasedCreationManager import PaletteBasedCreationManager
import Source.interface.modules.DataManager as DataManager

import Source.interface.modules.UtilsTools as UtilsTools


class PyFCSApp:
    # Embed the distributed license so that Help > License also works in the
    # one-file executable, where a repository-level LICENSE may not be present.
    MIT_LICENSE_TEXT = 'MIT License\n\nCopyright (c) 2025 Rafael Vázquez Conejo\n\nPermission is hereby granted, free of charge, to any person obtaining a copy\nof this software and associated documentation files (the "Software"), to deal\nin the Software without restriction, including without limitation the rights\nto use, copy, modify, merge, publish, distribute, sublicense, and/or sell\ncopies of the Software, and to permit persons to whom the Software is\nfurnished to do so, subject to the following conditions:\n\nThe above copyright notice and this permission notice shall be included in all\ncopies or substantial portions of the Software.\n\nTHE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\nIMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\nFITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE\nAUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\nLIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\nOUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE\nSOFTWARE.\n'

    def __init__(self, root):
        # Core references / managers
        self.root = root
        # Tk callbacks should never terminate a user's workflow with an
        # unhandled traceback. Log technical details, show a concise dialog.
        self._reporting_ui_error = False
        self.root.report_callback_exception = self._report_ui_callback_exception

        logo_path = UtilsTools.get_resource_path(
            os.path.join("Source", "external", "icons", "logo.png")
        )
        self.logo = tk.PhotoImage(file=logo_path)
        self.root.iconphoto(True, self.logo)

        self.color_processing_engine = ColorProcessingEngine(
            root=self.root,
            custom_warning=self.custom_warning if hasattr(self, "custom_warning") else None,
            center_popup=self.center_popup if hasattr(self, "center_popup") else None,
        )
        # Compatibility alias: existing image views and workspace controllers
        # access the same shared processing engine through app.image_manager.
        self.image_manager = self.color_processing_engine
        self.fuzzy_manager = FuzzyColorSpaceManager(root=self.root)
        # Keep generated CSV files in the runtime directory, not the installation folder.
        self.color_manager = ColorEvaluationManager(
            output_dir=UtilsTools.get_runtime_temp_dir("threshold_results", create=False)
        )
        self._image_inspection_controller = None
        self._image_inspection_window = None
        self._full_resolution_workspace_controller = None
        self._image_based_creation_controller = None
        self._image_based_creation_window = None
        self._palette_based_creation_controller = None
        self._palette_based_creation_window = None

        # Image Display workspace state.
        # A card move or resize switches the workspace from grid to manual layout.
        self._image_workspace_layout_mode = "grid"
        self._image_workspace_focus_id = None
        self._image_workspace_active_id = None
        self._image_workspace_focus_return_mode = "grid"
        self._image_workspace_focus_saved_state = None
        self._image_workspace_focus_saved_collapsed = None
        # Geometry callbacks are registered per card, not globally.
        self._image_workspace_callbacks = {}

        self.volume_limits = ReferenceDomain.default_voronoi_reference_domain()
        # Geometry settings are stored in each .json; this is the in-session default.
        self._fcs_creation_defaults = {"color_space": "LAB", "lambda1": 0.5,
                                       "lambda2": 1.5, "disjoint": True,
                                       "covering": True, "samples": 27}

        # Shared runtime state
        self.COLOR_SPACE = False
        self.FIRST_DBSCAN = True
        self.SHOW_ORIGINAL = {}
        self.CAN_APPLY_MAPPING = {}
        self.hex_color = []
        self.images = {}
        self.color_entry_detect = {}
        self.display_pil = {}
        # Each image card owns its cancellation and progress state.
        self.image_jobs = {}

        # Floating image viewport zoom state
        self.image_view_source = {}
        self.image_view_state = {}
        self._image_zoom_hover_window = None
        self._image_zoom_callbacks = {}
        self._image_zoom_mousewheel_bound = False

        # Additional runtime state
        self.rgb_data = []
        self.graph_widget = None
        # The 3D model always displays the FCS in its native geometric space.
        # An explicit conversion/rebuild is available from the Data tab.
        self.loaded_source_color_space = "LAB"
        # The model may be rebuilt in memory without immediately overwriting
        # an imported CNS / JFCS / PyFCS file on disk.
        self._model_space_unsaved = False

        # Retain Tk image references for the lifetime of their widgets.
        self.ui_icons = {}

        # Temporary Plotly output is stored outside the packaged application.
        self.TEMP_PLOT_MAX_FILES = 30
        self.TEMP_PLOT_CLEANUP_EVERY = 5
        self._temp_plot_creation_count = 0

        # Visual constants
        APP_BG = "#f5f6f8"
        CARD_BG = "#ffffff"
        PANEL_BG = "#fbfbfc"
        SOFT_BG = "#f1f3f6"
        BORDER = "#d9dde3"
        TEXT = "#1f2937"
        MUTED = "#6b7280"
        BLUE = UtilsTools.UI_ACCENT
        BLUE_BG = UtilsTools.UI_ACCENT_SOFT
        BLUE_BG_ACTIVE = UtilsTools.UI_ACCENT_HOVER
        GREEN = "#1f5f3a"
        GREEN_BG = "#e0f2e9"
        GREEN_BG_ACTIVE = "#cfeadb"
        RED = "#8a1f1f"
        RED_BG = "#f8d7da"
        RED_BG_ACTIVE = "#f1c4c9"

        FONT = ("Segoe UI", 9)
        FONT_BOLD = ("Segoe UI", 9, "bold")
        FONT_TITLE = ("Segoe UI", 10, "bold")
        FONT_SMALL = ("Segoe UI", 8)
        FONT_SMALL_BOLD = ("Segoe UI", 8, "bold")

        # Main window configuration
        self.root.title("PyFCS Interface")
        self.root.geometry("1200x720")
        self.root.minsize(1050, 620)
        self.root.configure(bg=APP_BG)

        try:
            self.root.attributes("-fullscreen", True)
        except tk.TclError:
            try:
                if platform.system() == "Windows":
                    self.root.state("zoomed")
                else:
                    screen_width = self.root.winfo_screenwidth()
                    screen_height = self.root.winfo_screenheight()
                    self.root.geometry(f"{screen_width}x{screen_height}+0+0")
            except Exception:
                pass

        self.root.bind("<Escape>", self.toggle_fullscreen)
        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.protocol("WM_DELETE_WINDOW", self.exit_app)

        # ttk style
        try:
            style = ttk.Style(self.root)
            try:
                style.theme_use("clam")
            except tk.TclError:
                pass

            style.configure(
                "PyFCS.TNotebook",
                background=APP_BG,
                borderwidth=0
            )
            style.configure(
                "PyFCS.TNotebook.Tab",
                font=FONT,
                padding=(14, 7),
                background=SOFT_BG,
                foreground=TEXT
            )
            style.map(
                "PyFCS.TNotebook.Tab",
                background=[("selected", CARD_BG)],
                foreground=[("selected", TEXT)]
            )
            style.configure(
                "PyFCS.TPanedwindow",
                background=APP_BG,
                borderwidth=0
            )
        except Exception:
            pass

        # Local UI helpers
        def create_card(parent, title=None, padx=10, pady=10):
            """
            Create a clean card-like container without heavy black borders.
            """
            if title:
                frame = tk.LabelFrame(
                    parent,
                    text=f" {title} ",
                    font=FONT_TITLE,
                    bg=CARD_BG,
                    fg=TEXT,
                    bd=0,
                    relief="flat",
                    padx=padx,
                    pady=pady,
                    labelanchor="nw"
                )
            else:
                frame = tk.Frame(
                    parent,
                    bg=CARD_BG,
                    bd=0,
                    relief="flat"
                )

            return frame

        def create_toolbar_button(parent, text, command, image=None, side="left", padx=5, pady=3, width=None):
            """
            Create a toolbar button with a clear button-like appearance.
            Compatible with Windows, macOS and Linux.
            """
            btn = tk.Button(
                parent,
                text=text,
                command=command,
                image=image,
                compound="left",
                font=FONT_BOLD,
                bg="#f8fafc",
                fg=TEXT,
                activebackground=UtilsTools.UI_ACCENT_SOFT,
                activeforeground=TEXT,
                relief="raised",
                bd=2,
                padx=8,
                pady=4,
                cursor="hand2",
                highlightthickness=0
            )

            if width is not None:
                btn.configure(width=width)

            def on_enter(_event):
                try:
                    btn.configure(bg="#eef2f7")
                except Exception:
                    pass

            def on_leave(_event):
                try:
                    btn.configure(bg="#f8fafc")
                except Exception:
                    pass

            btn.bind("<Enter>", on_enter)
            btn.bind("<Leave>", on_leave)

            btn.pack(side=side, padx=4, pady=2)
            return btn
        

        def add_toolbar_separator(parent):
            """
            Add a subtle vertical separator between toolbar groups.
            """
            sep = tk.Frame(
                parent,
                bg=BORDER,
                width=1
            )
            sep.pack(side="left", fill="y", padx=8, pady=6)
            return sep

        def create_action_button(parent, text, command, bg, fg, active_bg):
            """Subtle Data action button; placement is handled by the footer."""
            btn = tk.Button(
                parent, text=text, command=command,
                font=FONT, bg=bg, fg=fg,
                activebackground=active_bg, activeforeground=fg,
                relief="solid", bd=1, padx=10, pady=6,
                cursor="hand2", highlightthickness=0,
                disabledforeground=MUTED,
            )
            # Hover applies to normal Tk buttons on Windows and X11; on macOS
            # the platform may draw native controls differently.
            btn.bind("<Enter>", lambda _e: btn.configure(bg=active_bg))
            btn.bind("<Leave>", lambda _e: btn.configure(bg=bg))
            return btn

        def bind_vertical_mousewheel(canvas):
            """Register a scrollable canvas without using bind_all()/unbind_all()."""
            self._register_vertical_mousewheel_canvas(canvas)

        # Menu bar
        self.menubar = Menu(self.root)
        self.root.config(menu=self.menubar)

        # File
        file_menu = Menu(self.menubar, tearoff=0)

        file_menu.add_command(
            label="Exit",
            command=self.exit_app
        )

        self.menubar.add_cascade(
            label="File",
            menu=file_menu,
            underline=0,  # F
        )

        # Image Manager
        img_menu = Menu(self.menubar, tearoff=0)

        img_menu.add_command(
            label="Open Image",
            command=self.open_image
        )

        img_menu.add_command(
            label="Save Image",
            command=self.save_image
        )

        img_menu.add_separator()

        img_menu.add_command(
            label="Image Inspection",
            command=self.open_image_inspection
        )
        img_menu.add_command(
            label="Open in Image Workspace",
            command=lambda: self.open_full_resolution_image_workspace(None)
        )

        # Separate inspection/actions from the destructive global action.
        img_menu.add_separator()

        img_menu.add_command(
            label="Close All",
            command=self.close_all_image
        )

        self.menubar.add_cascade(
            label="Image",
            menu=img_menu,
            underline=0,  # I
        )

        # Fuzzy Color Space Manager
        fuzzy_menu = Menu(self.menubar, tearoff=0)

        # Native submenu in the application menu.
        new_color_space_menu = Menu(fuzzy_menu, tearoff=0)
        new_color_space_menu.add_command(
            label="Palette-Based Creation",
            command=self.palette_based_creation
        )
        new_color_space_menu.add_command(
            label="Image-Based Creation",
            command=self.image_based_creation
        )

        fuzzy_menu.add_cascade(
            label="New Color Space",
            menu=new_color_space_menu
        )

        fuzzy_menu.add_separator()

        fuzzy_menu.add_command(
            label="Load Color Space",
            command=self.load_color_space
        )

        self.menubar.add_cascade(
            label="Fuzzy Color Space",
            menu=fuzzy_menu,
            underline=6,  # C
        )

        # Matching dropdown used by the toolbar button.
        self.menu_create_fcs = Menu(self.root, tearoff=0)
        self.menu_create_fcs.add_command(
            label="Palette-Based Creation",
            command=self.palette_based_creation
        )
        self.menu_create_fcs.add_command(
            label="Image-Based Creation",
            command=self.image_based_creation
        )

        # Color Analysis
        analysis_menu = Menu(self.menubar, tearoff=0)

        analysis_menu.add_command(
            label="Color Evaluation",
            command=self.color_evaluation
        )

        self.menubar.add_cascade(
            label="Color Analysis",
            menu=analysis_menu,
            underline=6,  # A
        )

        # Help
        help_menu = Menu(self.menubar, tearoff=0)

        help_menu.add_command(
            label="License",
            command=self.license_info
        )
        help_menu.add_command(
            label="About",
            command=self.about_info
        )

        self.menubar.add_cascade(
            label="Help",
            menu=help_menu,
            underline=0,  # H
        )

        # Menu mnemonics
        # Tk uses the underline metadata natively where supported.
        # Bind Alt mnemonics outside macOS, where Option is used for text input.
        if platform.system() != "Darwin":
            def _open_top_menu(index):
                try:
                    self.menubar.postcascade(index)
                except Exception:
                    pass
                return "break"

            menu_mnemonics = {
                "f": 0,  # File
                "i": 1,  # Image
                "c": 2,  # Fuzzy Color Space
                "a": 3,  # Color Analysis
                "h": 4,  # Help
            }

            for key, index in menu_mnemonics.items():
                self.root.bind_all(
                    f"<Alt-KeyPress-{key}>",
                    lambda _event, idx=index: _open_top_menu(idx),
                    add="+",
                )
                self.root.bind_all(
                    f"<Alt-KeyPress-{key.upper()}>",
                    lambda _event, idx=index: _open_top_menu(idx),
                    add="+",
                )

        # Toolbar area
        main_frame = tk.Frame(self.root, bg=APP_BG)
        main_frame.pack(fill="x", padx=12, pady=(8, 6))

        toolbar_card = tk.Frame(
            main_frame,
            bg=CARD_BG,
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightbackground=BORDER
        )
        toolbar_card.pack(fill="x")

        toolbar_inner = tk.Frame(toolbar_card, bg=CARD_BG)
        toolbar_inner.pack(fill="x", padx=10, pady=7)

        icon_size = (30, 30)
        load_image_icon = self.load_toolbar_icon("LoadImage.png", icon_size)
        save_image_icon = self.load_toolbar_icon("SaveImage.png", icon_size)
        image_inspection_icon = self.load_toolbar_icon("ColorInspection.png", icon_size)
        new_fcs_icon = self.load_toolbar_icon("NewFCS1.png", icon_size)
        load_fcs_icon = self.load_toolbar_icon("LoadFCS.png", icon_size)
        pt_icon = self.load_toolbar_icon("PT.png", icon_size)
        evaluate_icon = self.load_toolbar_icon("evaluateColor.png", icon_size)

        image_manager_frame = create_card(
            toolbar_inner,
            title="Image Manager",
            padx=6,
            pady=5
        )
        image_manager_frame.pack(side="left", fill="y", expand=False, padx=(0, 10))

        create_toolbar_button(
            image_manager_frame,
            text="Open Image",
            image=load_image_icon,
            command=self.open_image
        )
        create_toolbar_button(
            image_manager_frame,
            text="Save Image",
            image=save_image_icon,
            command=self.save_image
        )
        create_toolbar_button(
            image_manager_frame,
            text="Image Inspection",
            image=image_inspection_icon,
            command=self.open_image_inspection
        )

        add_toolbar_separator(toolbar_inner)

        fuzzy_manager_frame = create_card(
            toolbar_inner,
            title="Fuzzy Color Space Manager",
            padx=6,
            pady=5
        )
        fuzzy_manager_frame.pack(side="left", fill="y", expand=False, padx=(0, 10))

        self.new_color_space_button = create_toolbar_button(
            fuzzy_manager_frame,
            text="New Color Space ▼",
            image=new_fcs_icon,
            command=self.show_menu_create_fcs
        )
        create_toolbar_button(
            fuzzy_manager_frame,
            text="Load Color Space",
            image=load_fcs_icon,
            command=self.load_color_space
        )

        add_toolbar_separator(toolbar_inner)

        color_evaluation_frame = create_card(
            toolbar_inner,
            title="Color Difference Evaluation",
            padx=6,
            pady=5
        )
        color_evaluation_frame.pack(side="left", fill="y", expand=False, padx=(0, 0))

        # Threshold display menu: PT and AT share one toolbar action.
        self.menu_display_threshold = Menu(self.root, tearoff=0)
        self.menu_display_threshold.add_command(
            label="Perceptibility Threshold (PT)",
            command=self.deploy_pt
        )
        self.menu_display_threshold.add_command(
            label="Acceptability Threshold (AT)",
            command=self.deploy_at
        )

        self.display_threshold_button = create_toolbar_button(
            color_evaluation_frame,
            text="Display Threshold ▼",
            image=pt_icon,
            command=self.show_menu_display_threshold
        )

        create_toolbar_button(
            color_evaluation_frame,
            text="Color Evaluation",
            image=evaluate_icon,
            command=self.color_evaluation
        )

        # Main working area
        main_content_frame = tk.Frame(self.root, bg=APP_BG)
        main_content_frame.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        main_paned = ttk.Panedwindow(
            main_content_frame,
            orient="horizontal",
            style="PyFCS.TPanedwindow"
        )
        main_paned.pack(fill="both", expand=True)

        # Image Display: title, status, T-conorm and workspace actions share
        # ONE compact header, rather than a LabelFrame title + a second toolbar.
        image_area_frame = tk.Frame(main_paned, bg=CARD_BG, padx=10, pady=7)
        image_workspace_bar = tk.Frame(image_area_frame, bg=CARD_BG)
        image_workspace_bar.pack(fill="x", pady=(0, 5))
        # Keep the heading at the left.  A single compact control group is
        # anchored to the right so T-conorm belongs visually with Focus/Grid,
        # rather than floating alone in the middle of Image Display.
        image_workspace_bar.grid_columnconfigure(0, weight=1)
        image_workspace_bar.grid_columnconfigure(1, weight=0)

        workspace_heading = tk.Frame(image_workspace_bar, bg=CARD_BG)
        workspace_heading.grid(row=0, column=0, sticky="w")
        tk.Label(
            workspace_heading, text="Image Display", font=FONT_TITLE,
            bg=CARD_BG, fg=TEXT, anchor="w",
        ).pack(anchor="w")
        self.image_workspace_status_var = tk.StringVar(value="0 images")
        tk.Label(
            workspace_heading, textvariable=self.image_workspace_status_var,
            font=FONT_SMALL, bg=CARD_BG, fg=MUTED, anchor="w",
        ).pack(anchor="w", pady=(3, 0))

        # T-conorm and workspace actions form one right-aligned cluster.
        workspace_controls = tk.Frame(image_workspace_bar, bg=CARD_BG)
        workspace_controls.grid(row=0, column=1, sticky="e")
        self._mapping_tconorm_bar = tk.Frame(
            workspace_controls, bg=CARD_BG,
            highlightthickness=1, highlightbackground="#e5e7eb",
        )
        self._mapping_tconorm_bar.pack(side="left", padx=(0, 10))
        tk.Label(
            self._mapping_tconorm_bar, text="T-conorm",
            font=("Segoe UI", 8, "bold"), bg=CARD_BG, fg=MUTED,
            anchor="center",
        ).pack(fill="x", pady=(1, 0))
        operator_buttons = tk.Frame(self._mapping_tconorm_bar, bg=CARD_BG)
        operator_buttons.pack(padx=4, pady=(1, 2))
        self._mapping_tconorm_buttons = {}
        for mode, caption in (("bounded_sum", "Bounded Sum"), ("max", "Max")):
            button = tk.Button(
                operator_buttons, text=caption, font=("Segoe UI", 8),
                relief="solid", bd=1, padx=5, pady=0, cursor="hand2",
                command=lambda value=mode: self._set_image_mapping_tconorm(value),
            )
            button.pack(side="left", padx=(0, 3 if mode == "bounded_sum" else 0))
            self._mapping_tconorm_buttons[mode] = button
        self._sync_image_mapping_tconorm_buttons()

        # Stack Focus above Grid without creating an extra header row.
        workspace_actions = tk.Frame(workspace_controls, bg=CARD_BG)
        workspace_actions.pack(side="left")
        self.image_workspace_focus_button = tk.Button(
            workspace_actions, text="Focus",
            command=self._focus_active_image_workspace_card,
            font=FONT_SMALL_BOLD, bg="#f8fafc", fg=TEXT,
            activebackground=BLUE_BG, relief="solid", bd=1,
            width=6, padx=4, pady=0, cursor="hand2", state="disabled",
        )
        self.image_workspace_focus_button.pack(anchor="e", pady=(0, 2))
        self.image_workspace_grid_button = tk.Button(
            workspace_actions, text="Grid",
            command=self._arrange_image_workspace_grid,
            font=FONT_SMALL_BOLD, bg="#f8fafc", fg=TEXT,
            activebackground=BLUE_BG, relief="solid", bd=1,
            width=6, padx=4, pady=0, cursor="hand2",
        )
        self.image_workspace_grid_button.pack(anchor="e")

        image_canvas_shell = tk.Frame(image_area_frame, bg=PANEL_BG)
        image_canvas_shell.pack(fill="both", expand=True)
        image_canvas_shell.grid_rowconfigure(0, weight=1)
        image_canvas_shell.grid_columnconfigure(0, weight=1)

        self.image_canvas = tk.Canvas(
            image_canvas_shell,
            bg=PANEL_BG,
            borderwidth=1,
            relief="solid",
            highlightthickness=0,
            yscrollincrement=24,
        )
        self.image_canvas.grid(row=0, column=0, sticky="nsew")

        self.image_workspace_vscroll = ttk.Scrollbar(
            image_canvas_shell,
            orient="vertical",
            command=self.image_canvas.yview,
        )
        self.image_workspace_vscroll.grid(row=0, column=1, sticky="ns")
        self.image_canvas.configure(yscrollcommand=self.image_workspace_vscroll.set)

        # Mapping controls are embedded in the corresponding image card.
        # No separate dock/window is used, so image + mapping controls always
        # move, minimize and stack as one visual unit.
        self.image_mapping_dock = None
        self.image_mapping_dock_visible = False
        self._mapping_all_palette_by_window = {}
        # Palette/display state cannot be shared between duplicate image windows.
        self._mapping_all_pack_by_window = {}

        self._image_workspace_focus_id = None
        self._image_workspace_active_id = None
        self._image_workspace_reflow_after_id = None
        self._image_workspace_callbacks = {}

        self.image_canvas.bind(
            "<Configure>",
            lambda _e: self._schedule_image_workspace_reflow(),
            add="+",
        )

        # Right pane: notebook area
        notebook_container = tk.Frame(
            main_paned,
            bg=CARD_BG,
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightbackground=BORDER
        )
        notebook_container.pack_propagate(False)

        self.notebook = ttk.Notebook(
            notebook_container,
            style="PyFCS.TNotebook"
        )
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)

        main_paned.add(image_area_frame, weight=5)
        main_paned.add(notebook_container, weight=6)

        def set_initial_main_sash():
            """Set the initial main workspace proportions."""
            total_width = main_paned.winfo_width()
            if total_width > 1:
                main_paned.sashpos(0, int(total_width * 0.42))

        self.root.after(140, set_initial_main_sash)

        # Tab: Model 3D
        model_3d_tab = tk.Frame(self.notebook, bg=CARD_BG)
        self.notebook.add(model_3d_tab, text="Model 3D")

        self.model_3d_options = {}

        options_bar = tk.Frame(model_3d_tab, bg=CARD_BG)
        options_bar.pack(side="top", fill="x", padx=12, pady=(12, 8))

        tk.Label(
            options_bar,
            text="Display:",
            font=FONT_SMALL_BOLD,
            bg=CARD_BG,
            fg=MUTED
        ).pack(side="left", padx=(0, 10))

        options = ["Representative", "Core", "0.5-cut", "Support"]
        for option in options:
            var = tk.BooleanVar(value=(option == "Representative"))
            self.model_3d_options[option] = var

            tk.Checkbutton(
                options_bar,
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
            ).pack(side="left", padx=(0, 22))

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

        # 3D display area
        self.Canvas1 = tk.Frame(
            paned,
            bg=PANEL_BG,
            borderwidth=1,
            relief="solid",
            width=760,
            highlightthickness=0
        )
        paned.add(self.Canvas1, stretch="always", minsize=430)

        # Color button panel
        self.colors_frame = tk.Frame(
            paned,
            bg=CARD_BG,
            width=205,
            bd=1,
            relief="solid",
            highlightthickness=0
        )
        paned.add(self.colors_frame, minsize=125)
        self._model_3d_paned = paned

        self.colors_frame.configure(width=205)

        def _position_model_3d_sash(_event=None):
            # Run only once after the pane acquires its real width. Repositioning
            # on later resizes would override the user's manual sash movement.
            if getattr(paned, "_pyfcs_sash_initialized", False):
                return
            try:
                if paned.winfo_exists() and paned.winfo_width() > 590:
                    paned.sash_place(0, paned.winfo_width() - 208, 1)
                    paned._pyfcs_sash_initialized = True
            except tk.TclError:
                pass

        paned.bind("<Configure>", _position_model_3d_sash, add="+")
        self.root.after(140, _position_model_3d_sash)


        self.scrollable_canvas = tk.Canvas(
            self.colors_frame,
            bg=CARD_BG,
            highlightthickness=0,
            borderwidth=0,
            width=132
        )
        self.scrollable_canvas.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=(0, 8))

        self.scrollbar = tk.Scrollbar(
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

        bind_vertical_mousewheel(self.scrollable_canvas)

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
            self.inner_frame,
            bg=CARD_BG
        )
        self.color_buttons_frame.pack(fill="x", pady=(2, 8), padx=4)

        button_style = {
            "width": 12,
            "height": 1,
            "font": ("Segoe UI", 9, "bold"),
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
        if self.COLOR_SPACE:
            self.select_all_button.pack(fill="x", pady=(2, 4))

        self.deselect_all_button = tk.Button(
            self.color_buttons_frame,
            text="Deselect All",
            command=self.deselect_all_color,
            **button_style
        )
        if self.COLOR_SPACE:
            self.deselect_all_button.pack(fill="x", pady=(0, 4))

        # Search only filters the sidebar; it never changes 3D selection.
        self._model_3d_search_var = tk.StringVar(value="")

        self._model_3d_search_frame = tk.Frame(self.inner_frame, bg=CARD_BG)

        tk.Label(
            self._model_3d_search_frame,
            text="Search",
            bg=CARD_BG,
            fg=MUTED,
            font=("Segoe UI", 8),
            anchor="center"
        ).pack(fill="x", pady=(0, 3))

        tk.Entry(
            self._model_3d_search_frame,
            textvariable=self._model_3d_search_var,
            font=("Segoe UI", 8),
            bg="#ffffff",
            fg="#1f2937",
            relief="solid",
            bd=1,
            width=15,
        ).pack(fill="x")

        self._model_3d_search_var.trace_add(
            "write", lambda *_: self._filter_model_3d_colors())

        # Tab: Data
        data_tab = tk.Frame(self.notebook, bg=CARD_BG)
        self.notebook.add(data_tab, text="Data")

        data_main = tk.Frame(data_tab, bg=CARD_BG)
        data_main.pack(fill="both", expand=True, padx=12, pady=12)

        data_panel = tk.Frame(
            data_main,
            bg=CARD_BG,
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightbackground=BORDER
        )
        data_panel.pack(fill="both", expand=True)

        # Data header: short title, secondary geometry metadata and file name.
        data_header = tk.Frame(data_panel, bg=SOFT_BG, height=62)
        data_header.pack(fill="x")
        data_header.pack_propagate(False)

        header_left = tk.Frame(data_header, bg=SOFT_BG)
        header_left.pack(side="left", fill="y", padx=16)

        self.data_header_title = tk.Label(
            header_left,
            text="No Fuzzy Color Space Loaded",
            font=("Segoe UI", 13, "bold"),
            bg=SOFT_BG,
            fg=TEXT,
            anchor="w"
        )
        self.data_header_title.pack(anchor="w", pady=(10, 0))

        self.data_model_summary = tk.Label(
            header_left,
            text="No color space loaded",
            font=FONT_SMALL,
            bg=SOFT_BG,
            fg=MUTED,
            anchor="w"
        )
        self.data_model_summary.pack(anchor="w", pady=(2, 0))

        name_row = tk.Frame(data_header, bg=SOFT_BG)
        name_row.pack(side="right", fill="y", padx=16)

        tk.Label(
            name_row,
            text="Name:",
            font=FONT_BOLD,
            bg=SOFT_BG,
            fg=TEXT
        ).pack(side="left", padx=(0, 8))

        self.file_name_entry = tk.Entry(
            name_row,
            font=FONT,
            width=28,
            justify="center",
            takefocus=0,  # Read-only metadata must not receive keyboard focus.
            relief="solid",
            bd=1,
            bg=CARD_BG,
            fg=TEXT,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=BLUE
        )
        self.file_name_entry.pack(side="left")
        self.file_name_entry.insert(0, "")

        # The read-only name is informational. When Data is opened, Tk may
        # otherwise leave its text selected in blue from an earlier focus.
        def clear_data_name_focus(_event=None):
            try:
                if self.notebook.select() != str(data_tab):
                    return
                name_entry = self.file_name_entry
                if name_entry.winfo_exists():
                    name_entry.selection_clear()
                    name_entry.icursor(tk.END)
                    # Focus on the tab container, not on a read-only Entry.
                    if self.root.focus_get() is name_entry:
                        self.notebook.focus_set()
            except tk.TclError:
                pass

        self.notebook.bind(
            "<<NotebookTabChanged>>",
            lambda _event: self.root.after_idle(clear_data_name_focus),
            add="+",
        )

        # Canvas area directly inside the main panel
        canvas_area = tk.Frame(data_panel, bg=CARD_BG)
        canvas_area.pack(fill="both", expand=True, padx=8, pady=(5, 6))

        canvas_area.rowconfigure(0, weight=1)
        canvas_area.columnconfigure(0, weight=1)

        canvas_frame = tk.Frame(canvas_area, bg=CARD_BG)
        canvas_frame.grid(row=0, column=0, sticky="nsew")

        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        self.data_window = tk.Canvas(
            canvas_frame,
            bg=CARD_BG,
            borderwidth=0,
            relief="flat",
            highlightthickness=0
        )
        self.data_window.grid(row=0, column=0, sticky="nsew")

        self.data_scrollbar_v = tk.Scrollbar(
            canvas_frame,
            orient="vertical",
            command=self.data_window.yview
        )
        self.data_scrollbar_v.grid(row=0, column=1, sticky="ns")

        # The Data table adapts to the available width; horizontal scrolling
        # adds no value here. Keep only the vertical scrollbar.
        self.data_window.configure(yscrollcommand=self.data_scrollbar_v.set)

        # SCROLL FIX (cross-platform)
        self.data_window.bind(
            "<MouseWheel>",
            lambda event: self.on_mouse_wheel(event, self.data_window)
        )
        self.data_window.bind(
            "<Button-4>",
            lambda event: self.on_mouse_wheel(event, self.data_window)
        )
        self.data_window.bind(
            "<Button-5>",
            lambda event: self.on_mouse_wheel(event, self.data_window)
        )

        self.inner_frame_data = tk.Frame(self.data_window, bg=CARD_BG)
        self.data_window.create_window((0, 0), window=self.inner_frame_data, anchor="nw")

        self.inner_frame_data.bind(
            "<Configure>",
            lambda _e: self.data_window.configure(
                scrollregion=self.data_window.bbox("all")
            )
        )

        # SCROLL FIX (inside content)
        self.inner_frame_data.bind(
            "<MouseWheel>",
            lambda event: self.on_mouse_wheel(event, self.data_window)
        )
        self.inner_frame_data.bind(
            "<Button-4>",
            lambda event: self.on_mouse_wheel(event, self.data_window)
        )
        self.inner_frame_data.bind(
            "<Button-5>",
            lambda event: self.on_mouse_wheel(event, self.data_window)
        )

        # Footer: a quiet divider separates the table from its actions.
        # Keep the buttons together on the right; stack them only if the
        # notebook is too narrow. Both operations remain independent.
        bottom_bar = tk.Frame(data_panel, bg=CARD_BG)
        bottom_bar.pack(fill="x", padx=11, pady=(0, 11))

        tk.Frame(bottom_bar, bg=BORDER, height=1).pack(
            fill="x", pady=(0, 9)
        )

        actions_row = tk.Frame(bottom_bar, bg=CARD_BG, height=34)
        actions_row.pack(fill="x")
        actions_row.pack_propagate(False)

        actions_group = tk.Frame(actions_row, bg=CARD_BG)
        actions_group.pack(side="right")

        self.modify_fcs_button = create_action_button(
            actions_group,
            text="Edit Fuzzy Color Space",
            command=self.open_modify_fcs,
            bg="#F3EEF8", fg=TEXT, active_bg="#E9DDF1",
        )
        delete_button = create_action_button(
            actions_group,
            text="Delete Color Space",
            command=self.delete_color_space,
            bg="#FBEDEE", fg=TEXT, active_bg="#F4DFE1",
        )

        footer_mode = {"narrow": None}

        def _layout_data_actions(event=None):
            if event is None:
                return
            needed = (
                self.modify_fcs_button.winfo_reqwidth()
                + delete_button.winfo_reqwidth() + 9
            )
            narrow = event.width < needed
            if footer_mode["narrow"] == narrow:
                return
            footer_mode["narrow"] = narrow
            self.modify_fcs_button.grid_forget()
            delete_button.grid_forget()
            if narrow:
                actions_row.configure(height=76)
                self.modify_fcs_button.grid(
                    row=0, column=0, sticky="e", pady=(0, 7)
                )
                delete_button.grid(row=1, column=0, sticky="e")
            else:
                actions_row.configure(height=34)
                self.modify_fcs_button.grid(row=0, column=0, sticky="e")
                delete_button.grid(row=0, column=1, sticky="e", padx=(9, 0))

        actions_row.bind("<Configure>", _layout_data_actions)

        # Internal status variable
        self.status_var = tk.StringVar(value="Ready")


    ########################################################################################### Utils APP ###########################################################################################
    def exit_app(self):
        """
        Prompt the user to confirm exiting the application.
        If the user confirms, close the application.
        """
        if getattr(self, "_model_space_unsaved", False):
            prompt = ("The reconstructed model has not been saved.\n\n"
                      "Exit without using Apply Changes?")
        else:
            prompt = "Are you sure you want to exit?"
        confirm_exit = messagebox.askyesno("Exit", prompt, parent=self.root)
        if confirm_exit:
            controller = getattr(self, "_full_resolution_workspace_controller", None)
            if controller is not None:
                controller.close()
            self.root.destroy()


    def _get_valid_dialog_parent(self, parent=None):
        """
        Return a valid Tk/Toplevel parent for dialogs.
        If a Frame or child widget is passed, it returns its top-level window.
        """
        if parent is None:
            parent = getattr(self, "root", None)

        try:
            if parent is not None and parent.winfo_exists():
                return parent.winfo_toplevel()
        except Exception:
            pass

        return getattr(self, "root", None)


    
    def toggle_fullscreen(self, event=None):
        """Toggle between fullscreen and maximized window mode."""
        try:
            is_fullscreen = bool(self.root.attributes("-fullscreen"))

            if is_fullscreen:
                # Leave fullscreen mode.
                self.root.attributes("-fullscreen", False)

                def maximize_window():
                    try:
                        if platform.system() == "Windows":
                            self.root.state("zoomed")
                        else:
                            self.root.attributes("-zoomed", True)
                    except tk.TclError:
                        # Keep a normal window if maximizing is unsupported.
                        pass

                self.root.after_idle(maximize_window)

            else:
                # Return to fullscreen mode.
                self.root.attributes("-fullscreen", True)

        except tk.TclError:
            pass

        return "break"



    def switch_tab(self, notebook, forward=True):
        """
        Switch between notebook tabs (Ctrl+Tab behavior).
        """
        # Get the index of the currently selected tab
        current_index = notebook.index(notebook.select())

        # Get the total number of tabs in the notebook
        total_tabs = len(notebook.tabs())

        if forward:
            # Move to the next tab (wrap around to the first tab if needed)
            new_index = (current_index + 1) % total_tabs
        else:
            new_index = (current_index - 1) % total_tabs

        notebook.select(new_index)


    def _register_vertical_mousewheel_canvas(self, canvas):
        """
        Register a main-window canvas for cross-platform vertical wheel scrolling.

        A single dispatcher is bound to the main Toplevel. It checks which
        registered canvas is actually under the pointer, so no component needs
        bind_all()/unbind_all() and one scrollable area cannot remove another
        component's wheel/zoom bindings.
        """
        if canvas is None:
            return

        if not hasattr(self, "_vertical_wheel_canvases"):
            self._vertical_wheel_canvases = []

        if canvas not in self._vertical_wheel_canvases:
            self._vertical_wheel_canvases.append(canvas)

        if not hasattr(self, "_vertical_wheel_bound_toplevels"):
            self._vertical_wheel_bound_toplevels = set()

        try:
            top = canvas.winfo_toplevel()
            top_key = str(top)
        except Exception:
            top = self.root
            top_key = str(self.root)

        if top_key in self._vertical_wheel_bound_toplevels:
            return

        top.bind("<MouseWheel>", self._dispatch_vertical_mousewheel, add="+")
        top.bind("<Button-4>", self._dispatch_vertical_mousewheel, add="+")
        top.bind("<Button-5>", self._dispatch_vertical_mousewheel, add="+")
        self._vertical_wheel_bound_toplevels.add(top_key)


    def _dispatch_vertical_mousewheel(self, event):
        """Scroll only the registered canvas currently under the mouse pointer."""
        canvases = list(getattr(self, "_vertical_wheel_canvases", []) or [])
        if not canvases:
            return None

        try:
            pointer_x = self.root.winfo_pointerx()
            pointer_y = self.root.winfo_pointery()
        except Exception:
            return None

        alive = []
        target = None
        for canvas in canvases:
            try:
                if not canvas.winfo_exists():
                    continue
                alive.append(canvas)
                x0 = canvas.winfo_rootx()
                y0 = canvas.winfo_rooty()
                x1 = x0 + canvas.winfo_width()
                y1 = y0 + canvas.winfo_height()
                if x0 <= pointer_x < x1 and y0 <= pointer_y < y1:
                    target = canvas
            except Exception:
                continue

        self._vertical_wheel_canvases = alive
        if target is None:
            return None

        system_name = platform.system()
        try:
            if getattr(event, "num", None) == 4:
                step = -1
            elif getattr(event, "num", None) == 5:
                step = 1
            else:
                delta = int(getattr(event, "delta", 0) or 0)
                if delta == 0:
                    return None
                if system_name == "Darwin":
                    step = -1 if delta > 0 else 1
                else:
                    step = int(-delta / 120)
                    if step == 0:
                        step = -1 if delta > 0 else 1
            target.yview_scroll(step, "units")
            return "break"
        except Exception:
            return None


    def load_toolbar_icon(self, filename, size=None):
        if not hasattr(self, "ui_icons"):
            self.ui_icons = {}

        key = (filename, size)

        if key in self.ui_icons:
            return self.ui_icons[key]

        icon_path = UtilsTools.get_resource_path(
            os.path.join("Source", "external", "icons", filename)
        )
        img = Image.open(icon_path)

        if size is not None:
            img = img.resize(size, Image.Resampling.LANCZOS)

        tk_img = ImageTk.PhotoImage(img)
        self.ui_icons[key] = tk_img
        return tk_img


        
    def custom_warning(self, title="Warning", message="Warning", parent=None):
        """Show a compact, modal warning using the Loading/Processing visual style."""
        parent_win = self._get_active_dialog_parent(parent)
        accent = UtilsTools.UI_ACCENT
        accent_dark = UtilsTools.UI_ACCENT_DARK
        bg = "#f5f6f8"
        white = "#ffffff"
        muted = "#667085"

        dialog = tk.Toplevel(parent_win)
        dialog.withdraw()
        dialog.title(str(title))
        dialog.configure(bg=bg)
        dialog.resizable(False, False)
        dialog.transient(parent_win)

        try:
            dialog.iconphoto(True, self.logo)
        except (AttributeError, tk.TclError):
            pass

        # Card
        shell = tk.Frame(dialog, bg="#e5e7eb")
        shell.pack(fill="both", expand=True, padx=10, pady=10)

        card = tk.Frame(shell, bg=white)
        card.pack(fill="both", expand=True, padx=1, pady=1)

        body = tk.Frame(card, bg=white, padx=22, pady=20)
        body.pack(fill="both", expand=True)

        # Warning icon
        icon_box = tk.Frame(
            body, bg=white, width=52, height=52
        )
        icon_box.pack(side="left", anchor="n", padx=(0, 17))
        icon_box.pack_propagate(False)

        try:
            icon_image = self.load_toolbar_icon(
                "warning.png", size=(38, 35)
            )
            icon_label = tk.Label(
                icon_box, image=icon_image,
                bg=white, bd=0
            )
            icon_label.image = icon_image
        except Exception:
            icon_label = tk.Label(
                icon_box,
                text="!",
                font=("Segoe UI", 22, "bold"),
                fg="#a16207",
                bg=white,
                bd=0
            )

        icon_label.pack(expand=True)

        # Message
        content = tk.Frame(body, bg=white)
        content.pack(side="left", fill="both", expand=True)

        tk.Label(
            content,
            text=str(title),
            font=("Segoe UI", 12, "bold"),
            bg=white,
            fg="#242735",
            anchor="w",
            justify="left",
            wraplength=395
        ).pack(fill="x", anchor="w", pady=(0, 7))

        tk.Label(
            content,
            text=str(message),
            font=("Segoe UI", 10),
            bg=white,
            fg=muted,
            anchor="w",
            justify="left",
            wraplength=395
        ).pack(fill="x", anchor="w")

        # Footer
        tk.Frame(
            card, bg="#ebe7f0", height=1
        ).pack(fill="x")

        footer = tk.Frame(
            card, bg="#faf9fc", padx=18, pady=12
        )
        footer.pack(fill="x")

        def close_dialog(_event=None):
            try:
                if dialog.winfo_exists():
                    try:
                        dialog.grab_release()
                    except tk.TclError:
                        pass
                    dialog.destroy()
            except tk.TclError:
                pass

        ok_btn = tk.Button(
            footer,
            text="OK",
            command=close_dialog,
            font=("Segoe UI", 9, "bold"),
            bg=accent,
            fg="white",
            activebackground=accent_dark,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=23,
            pady=7,
            cursor="hand2",
            highlightthickness=0
        )
        ok_btn.pack(side="right")

        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        dialog.bind("<Return>", close_dialog)
        dialog.bind("<Escape>", close_dialog)

        # Automatic sizing and centering
        dialog.update_idletasks()

        width = max(485, min(dialog.winfo_reqwidth() + 6, 650))
        height = max(180, dialog.winfo_reqheight() + 6)

        self.center_popup_to_parent(
            dialog, width, height, parent_win
        )

        dialog.deiconify()

        try:
            dialog.lift(parent_win)
        except tk.TclError:
            dialog.lift()

        # Tk supports one active grab: restore the parent's modal grab after
        # a nested warning closes (e.g. Change Color Space / Creation).
        try:
            previous_grab = dialog.grab_current()
        except tk.TclError:
            previous_grab = None
        try:
            dialog.grab_set()
            ok_btn.focus_set()
            dialog.wait_window()
        finally:
            if previous_grab is not None and previous_grab != dialog:
                try:
                    if previous_grab.winfo_exists():
                        previous_grab.grab_set()
                except tk.TclError:
                    pass



    def show_loading_color_space(self):
        """Display a compact loading dialog while a color space is prepared."""
        popup = tk.Toplevel(self.root)
        popup.withdraw()
        popup.title("Loading Color Space")
        popup.configure(bg="#f6f6f8")
        popup.resizable(False, False)
        popup.transient(self.root)
        popup.protocol("WM_DELETE_WINDOW", lambda: None)
        self.load_window = popup

        card = tk.Frame(popup, bg="#ffffff", padx=24, pady=21)
        card.pack(fill="both", expand=True, padx=10, pady=10)
        tk.Label(
            card, text="Loading Color Space",
            bg="#ffffff", fg="#262832",
            font=("Segoe UI", 13, "bold"), anchor="w"
        ).pack(fill="x")
        tk.Label(
            card, text="Reading colors and preparing the model...",
            bg="#ffffff", fg="#667085",
            font=("Segoe UI", 9), anchor="w"
        ).pack(fill="x", pady=(6, 16))
        self._loading_color_space_progress = ttk.Progressbar(
            card, mode="indeterminate", orient="horizontal",
            length=325, style="PyFCS.Load.Horizontal.TProgressbar"
        )
        self._loading_color_space_progress.pack(fill="x")
        self._loading_color_space_progress.start(12)
        tk.Label(
            card, text="The current workspace is preserved until loading completes.",
            bg="#ffffff", fg="#89909c",
            font=("Segoe UI", 8), anchor="w"
        ).pack(fill="x", pady=(12, 0))

        style = ttk.Style(popup)
        style.configure(
            "PyFCS.Load.Horizontal.TProgressbar",
            troughcolor="#eae7ef", background=UtilsTools.UI_ACCENT,
            borderwidth=0, thickness=7
        )
        self.center_popup(popup, 430, 188)
        popup.deiconify()
        popup.grab_set()
        # Do not enter a nested event loop; the caller returns promptly to
        # Tk's mainloop while the file is prepared in the worker thread.
        popup.update_idletasks()


    def show_loading(self, title="Processing Color Space",
                     message="Preparing the color-space geometry...",
                     note="This window closes automatically when the operation finishes."):
        """Unified, non-blocking progress window for save/threshold operations.

        Start indeterminate: computing Voronoi geometry has no meaningful
        per-step percentage. Switch to determinate only when a writer reports
        its actual progress.
        """
        popup = tk.Toplevel(self.root)
        popup.withdraw()
        popup.title(title)
        popup.configure(bg="#f6f6f8")
        popup.resizable(False, False)
        popup.transient(self.root)
        popup.protocol("WM_DELETE_WINDOW", lambda: None)
        self.load_window = popup

        style = ttk.Style(popup)
        style.configure(
            "PyFCS.Load.Horizontal.TProgressbar",
            troughcolor="#eae7ef", background=UtilsTools.UI_ACCENT,
            borderwidth=0, thickness=7
        )

        card = tk.Frame(popup, bg="#ffffff", padx=24, pady=21)
        card.pack(fill="both", expand=True, padx=10, pady=10)
        tk.Label(
            card, text=title, bg="#ffffff", fg="#262832",
            font=("Segoe UI", 13, "bold"), anchor="w"
        ).pack(fill="x")
        self._processing_status_label = tk.Label(
            card, text=message, bg="#ffffff", fg="#667085",
            font=("Segoe UI", 9), justify="left", anchor="w",
            wraplength=370
        )
        self._processing_status_label.pack(fill="x", pady=(6, 16))

        self.progress = ttk.Progressbar(
            card, mode="indeterminate", orient="horizontal",
            length=325, style="PyFCS.Load.Horizontal.TProgressbar"
        )
        self.progress.pack(fill="x")
        self.progress.start(12)
        tk.Label(
            card, text=note, bg="#ffffff", fg="#89909c",
            font=("Segoe UI", 8), anchor="w", wraplength=370
        ).pack(fill="x", pady=(12, 0))

        self.center_popup(popup, 430, 188)
        popup.deiconify()
        popup.grab_set()
        popup.update_idletasks()

    def _set_processing_progress(self, value=None, message=None):
        """Update the Processing window on the Tk main thread only."""
        popup = getattr(self, "load_window", None)
        progress = getattr(self, "progress", None)
        if popup is None or progress is None:
            return
        try:
            if not popup.winfo_exists() or not progress.winfo_exists():
                return
            label = getattr(self, "_processing_status_label", None)
            if message is not None and label is not None and label.winfo_exists():
                label.configure(text=message)
            if value is not None:
                if str(progress.cget("mode")) != "determinate":
                    progress.stop()
                    progress.configure(mode="determinate", maximum=100)
                progress["value"] = max(0.0, min(100.0, float(value)))
        except tk.TclError:
            pass

    def hide_loading(self):
        """Close either progress dialog safely (Tk main thread only).

        ttk.Progressbar.stop() must run *before* destroying its Toplevel.
        Detach the references first to make repeated/reentrant cleanup safe.
        """
        popup = getattr(self, "load_window", None)
        bars = (
            getattr(self, "_loading_color_space_progress", None),
            getattr(self, "progress", None),
        )
        self._loading_color_space_progress = None
        self.progress = None
        self._processing_status_label = None
        self.load_window = None

        for indicator in bars:
            if indicator is None:
                continue
            try:
                if indicator.winfo_exists():
                    indicator.stop()
            except (tk.TclError, RuntimeError):
                # The root/dialog may have been closed independently.
                pass

        if popup is not None:
            try:
                if popup.winfo_exists():
                    try:
                        popup.grab_release()
                    except (tk.TclError, RuntimeError):
                        pass
                    popup.destroy()
            except (tk.TclError, RuntimeError):
                pass


    def license_info(self):
        """Show the complete MIT license, with copy and keyboard shortcuts."""
        popup = tk.Toplevel(self.root)
        popup.withdraw()
        popup.title("License - PyFCS")
        popup.configure(bg="#f5f6f8")
        popup.resizable(True, True)
        popup.minsize(540, 400)

        try:
            popup.iconphoto(True, self.logo)
        except Exception:
            pass

        outer = tk.Frame(popup, bg="#f5f6f8")
        outer.pack(fill="both", expand=True, padx=14, pady=14)
        card = tk.Frame(outer, bg="white", bd=1, relief="solid")
        card.pack(fill="both", expand=True)

        tk.Label(
            card, text="MIT License", font=("Segoe UI", 16, "bold"),
            fg="#1f2937", bg="white"
        ).pack(pady=(18, 2))
        tk.Label(
            card, text="PyFCS · Rafael Vázquez Conejo",
            font=("Segoe UI", 9), fg="#6b7280", bg="white"
        ).pack(pady=(0, 14))

        body = tk.Frame(card, bg="white")
        body.pack(fill="both", expand=True, padx=20)
        scrollbar = ttk.Scrollbar(body, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        license_body = tk.Text(
            body, wrap="word", font=("Consolas", 9),
            bg="#fafafa", fg="#374151", bd=1, relief="solid",
            padx=12, pady=10, undo=False,
            yscrollcommand=scrollbar.set,
        )
        license_body.pack(side="left", fill="both", expand=True)
        scrollbar.configure(command=license_body.yview)
        license_body.insert("1.0", self.MIT_LICENSE_TEXT)
        license_body.configure(state="disabled")

        footer = tk.Frame(card, bg="white")
        footer.pack(fill="x", padx=20, pady=(14, 16))
        actions = tk.Frame(footer, bg="white")
        actions.pack(anchor="center")

        def copy_license():
            popup.clipboard_clear()
            popup.clipboard_append(self.MIT_LICENSE_TEXT)
            popup.update_idletasks()
            copy_button.configure(text="Copied!")

        def close_license(_event=None):
            try:
                popup.grab_release()
            except Exception:
                pass
            popup.destroy()

        copy_button = tk.Button(
            actions, text="Copy License", command=copy_license,
            font=("Segoe UI", 9, "bold"), bg="#f3f4f6", fg="#374151",
            activebackground="#e5e7eb", relief="solid", bd=1,
            padx=16, pady=7, cursor="hand2",
        )
        copy_button.pack(side="left", padx=5)
        close_button = tk.Button(
            actions, text="Close", command=close_license,
            font=("Segoe UI", 9, "bold"),
            bg=UtilsTools.UI_ACCENT_SOFT, fg=UtilsTools.UI_ACCENT_DARK,
            activebackground=UtilsTools.UI_ACCENT_HOVER,
            relief="solid", bd=1, padx=22, pady=7, cursor="hand2",
        )
        close_button.pack(side="left", padx=5)

        popup.protocol("WM_DELETE_WINDOW", close_license)
        popup.bind("<Escape>", close_license)
        popup.update_idletasks()
        self.center_popup(popup, 700, 575)
        popup.transient(self.root)
        popup.deiconify()
        popup.grab_set()
        close_button.focus_set()

    def about_info(self):
        """
        Display an improved About window for PyFCS.
        """
        about_window = tk.Toplevel(self.root)
        about_window.withdraw()
        about_window.title("About PyFCS")
        about_window.configure(bg="#f5f6f8")
        about_window.resizable(False, False)

        try:
            about_window.iconphoto(True, self.logo)
        except Exception:
            pass

        WIN_W = 520
        WIN_H = 420
        WEBSITE_URL = "https://pyfcs.com/"

        def close_about():
            try:
                about_window.grab_release()
            except Exception:
                pass
            about_window.destroy()

        def open_website(_event=None):
            try:
                webbrowser.open_new_tab(WEBSITE_URL)
            except Exception:
                pass

        about_window.protocol("WM_DELETE_WINDOW", close_about)

        # Main outer container
        outer = tk.Frame(
            about_window,
            bg="#f5f6f8"
        )
        outer.pack(fill="both", expand=True, padx=14, pady=14)

        card = tk.Frame(
            outer,
            bg="white",
            bd=1,
            relief="solid"
        )
        card.pack(fill="both", expand=True)

        # Header with logo
        header = tk.Frame(card, bg="white")
        header.pack(fill="x", padx=22, pady=(18, 6))

        try:
            logo_img = self.load_toolbar_icon("logo.png", size=(64, 64))

            logo_label = tk.Label(
                header,
                image=logo_img,
                bg="white",
                bd=0
            )
            logo_label.image = logo_img
            logo_label.pack(anchor="center", pady=(0, 8))

        except Exception:
            pass

        tk.Label(
            header,
            text="PyFCS",
            font=("Segoe UI", 18, "bold"),
            bg="white",
            fg="#1f2937"
        ).pack(anchor="center")

        tk.Label(
            header,
            text="Python Fuzzy Color Software",
            font=("Segoe UI", 10),
            bg="white",
            fg="#6b7280"
        ).pack(anchor="center", pady=(2, 0))

        # Body text
        body = tk.Frame(card, bg="white")
        body.pack(fill="x", padx=28, pady=(10, 8))

        tk.Label(
            body,
            text="A color modeling Python software based on Fuzzy Color Spaces.",
            font=("Segoe UI", 10),
            bg="white",
            fg="#374151",
            justify="center",
            wraplength=420
        ).pack(anchor="center", pady=(0, 12))

        info_box = tk.Frame(
            body,
            bg="#f8fafc",
            bd=0,
            relief="flat"
        )
        info_box.pack(fill="x", padx=12, pady=(2, 0))

        tk.Label(
            info_box,
            text="Version 1.5.0",
            font=("Segoe UI", 10, "bold"),
            bg="#f8fafc",
            fg="#1f2937"
        ).pack(anchor="center", pady=(10, 2))

        tk.Label(
            info_box,
            text="Contact: rafaconejo@ugr.es",
            font=("Segoe UI", 9),
            bg="#f8fafc",
            fg="#4b5563"
        ).pack(anchor="center", pady=(0, 4))

        website_label = tk.Label(
            info_box,
            text=WEBSITE_URL,
            font=("Segoe UI", 9, "underline"),
            bg="#f8fafc",
            fg=UtilsTools.UI_ACCENT,
            cursor="hand2"
        )
        website_label.pack(anchor="center", pady=(0, 10))
        website_label.bind("<Button-1>", open_website)

        # Footer
        footer = tk.Frame(card, bg="white")
        footer.pack(fill="x", padx=22, pady=(12, 18))

        close_button = tk.Button(
            footer,
            text="Close",
            command=close_about,
            font=("Segoe UI", 10, "bold"),
            bg=UtilsTools.UI_ACCENT_SOFT,
            fg=UtilsTools.UI_ACCENT,
            activebackground=UtilsTools.UI_ACCENT_HOVER,
            activeforeground=UtilsTools.UI_ACCENT,
            relief="raised",
            bd=1,
            padx=30,
            pady=7,
            cursor="hand2",
            highlightthickness=0
        )
        close_button.pack(anchor="center")

        # Keyboard shortcuts
        about_window.bind("<Escape>", lambda _event: close_about())
        about_window.bind("<Return>", lambda _event: close_about())

        # Center after layout
        about_window.update_idletasks()
        self.center_popup(about_window, WIN_W, WIN_H)

        about_window.transient(self.root)
        about_window.deiconify()
        about_window.grab_set()
        about_window.focus_set()

        try:
            close_button.focus_set()
        except Exception:
            pass


    def show_menu_create_fcs(self):
        """Display the creation-mode menu directly below New Color Space."""
        try:
            button = self.new_color_space_button
            x = button.winfo_rootx()
            y = button.winfo_rooty() + button.winfo_height()
            self.menu_create_fcs.post(x, y)
        except Exception:
            self.menu_create_fcs.post(
                self.root.winfo_pointerx(),
                self.root.winfo_pointery()
            )


    def show_menu_display_threshold(self):
        """Display the PT/AT selection menu directly below its toolbar button."""
        try:
            button = self.display_threshold_button
            x = button.winfo_rootx()
            y = button.winfo_rooty() + button.winfo_height()
            self.menu_display_threshold.post(x, y)
        except Exception:
            self.menu_display_threshold.post(
                self.root.winfo_pointerx(),
                self.root.winfo_pointery()
            )


    def _ensure_image_loaded_for_feature(self, feature_name):
        """
        Ensure that at least one workspace image is loaded.

        If no image is available, offer to open one using the normal PyFCS
        image-loading workflow. Returns True only when an image is available.
        """
        if bool(getattr(self, "load_images_names", {})):
            return True

        load_now = messagebox.askyesno(
            feature_name,
            f"{feature_name} requires a loaded image.\n\n"
            "Do you want to open an image now?",
            parent=self._get_active_dialog_parent(),
            icon="warning"
        )

        if not load_now:
            return False

        self.open_image()

        return bool(getattr(self, "load_images_names", {}))


    def _ensure_fuzzy_color_space_loaded_for_feature(self, feature_name, on_success=None):
        """
        Ensure that a Fuzzy Color Space is loaded.

        If none is active, offer to load one using the normal PyFCS
        color-space-loading workflow. Returns True only when loading succeeds.
        """
        if (
            getattr(self, "COLOR_SPACE", False)
            and getattr(self, "fuzzy_color_space", None) is not None
        ):
            return True

        load_now = messagebox.askyesno(
            feature_name,
            f"{feature_name} requires a loaded Fuzzy Color Space.\n\n"
            "Do you want to load one now?",
            parent=self._get_active_dialog_parent(),
            icon="warning"
        )

        if not load_now:
            return False

        # Loading is asynchronous. Re-open the requested feature only when
        # the new model is actually ready; never use the previously loaded one.
        self.load_color_space(on_success=on_success)
        return False


    def on_mouse_wheel(self, event, target):
        """Scroll a widget using Windows, macOS or X11/Linux wheel events."""
        num = getattr(event, "num", None)
        delta = int(getattr(event, "delta", 0) or 0)

        if num == 4:
            step = -1
        elif num == 5:
            step = 1
        elif delta:
            if platform.system() == "Darwin":
                step = -1 if delta > 0 else 1
            else:
                step = int(-delta / 120)
                if step == 0:
                    step = -1 if delta > 0 else 1
        else:
            return None

        target.yview_scroll(step, "units")
        return "break"


    def center_popup(self, popup, width, height):
        """
        Center a popup window relative to the main window when possible.
        If the main window is minimized or not in a usable state, center on screen.
        """
        try:
            popup.update_idletasks()
        except Exception:
            pass

        try:
            self.root.update_idletasks()
            root_state = self.root.state()
        except Exception:
            root_state = None

        # If root is minimized/hidden, center on screen
        if root_state in ("iconic", "withdrawn"):
            screen_width = popup.winfo_screenwidth()
            screen_height = popup.winfo_screenheight()

            popup_x = (screen_width - width) // 2
            popup_y = (screen_height - height) // 2
        else:
            try:
                root_x = self.root.winfo_rootx()
                root_y = self.root.winfo_rooty()
                root_width = self.root.winfo_width()
                root_height = self.root.winfo_height()

                # Fallback if geometry is invalid
                if root_width <= 1 or root_height <= 1:
                    raise ValueError("Root window geometry is not usable.")

                popup_x = root_x + (root_width - width) // 2
                popup_y = root_y + (root_height - height) // 2
            except Exception:
                screen_width = popup.winfo_screenwidth()
                screen_height = popup.winfo_screenheight()

                popup_x = (screen_width - width) // 2
                popup_y = (screen_height - height) // 2

        popup.geometry(f"{width}x{height}+{popup_x}+{popup_y}")


    def center_popup_to_parent(self, popup, width, height, parent=None):
        """
        Center a popup relative to the given parent window when possible.
        Falls back to the screen center if the parent is unavailable.
        """
        try:
            popup.update_idletasks()
        except Exception:
            pass

        parent_win = self._get_active_dialog_parent(parent)

        try:
            parent_win.update_idletasks()
            parent_state = parent_win.state()
        except Exception:
            parent_state = None

        if parent_state in ("iconic", "withdrawn"):
            screen_width = popup.winfo_screenwidth()
            screen_height = popup.winfo_screenheight()
            popup_x = (screen_width - width) // 2
            popup_y = (screen_height - height) // 2
        else:
            try:
                parent_x = parent_win.winfo_rootx()
                parent_y = parent_win.winfo_rooty()
                parent_width = parent_win.winfo_width()
                parent_height = parent_win.winfo_height()

                if parent_width <= 1 or parent_height <= 1:
                    raise ValueError("Parent geometry is not usable.")

                popup_x = parent_x + (parent_width - width) // 2
                popup_y = parent_y + (parent_height - height) // 2
            except Exception:
                screen_width = popup.winfo_screenwidth()
                screen_height = popup.winfo_screenheight()
                popup_x = (screen_width - width) // 2
                popup_y = (screen_height - height) // 2

        popup.geometry(f"{width}x{height}+{popup_x}+{popup_y}")


    def _ensure_creation_state(self):
        """Lazy init for the color-space creation workflow state."""
        if not hasattr(self, "_creation_windows"):
            self._creation_windows = []

        if not hasattr(self, "_creation_in_progress"):
            self._creation_in_progress = False


    def _register_creation_window(self, win):
        """Track a creation-related window and auto-clean dead references."""
        self._ensure_creation_state()

        if win is None:
            return

        # Clean dead refs first
        alive = []
        for w in self._creation_windows:
            try:
                if w is not None and w.winfo_exists():
                    alive.append(w)
            except Exception:
                pass
        self._creation_windows = alive

        if win not in self._creation_windows:
            self._creation_windows.append(win)

        self._creation_in_progress = True

        def _cleanup(_event=None, window=win):
            try:
                self._creation_windows = [
                    w for w in self._creation_windows
                    if w is not None and w.winfo_exists() and w != window
                ]
            except Exception:
                self._creation_windows = []

            if not self._creation_windows:
                self._creation_in_progress = False

            for attr in (
                "_palette_based_creation_window",
                "_image_based_creation_window",
            ):
                if getattr(self, attr, None) is window:
                    setattr(self, attr, None)

        try:
            win.bind("<Destroy>", _cleanup, add="+")
        except Exception:
            pass


    def _close_creation_windows(self):
        """Close all creation-related windows and reset workflow state."""
        self._ensure_creation_state()

        popup_attrs = (
            "_image_based_creation_window",
            "_palette_based_creation_window",
        )

        windows = list(self._creation_windows)
        for attr in popup_attrs:
            win = getattr(self, attr, None)
            if win is not None:
                windows.append(win)

        seen = set()
        for win in windows:
            if win is None:
                continue

            window_id = id(win)
            if window_id in seen:
                continue
            seen.add(window_id)

            try:
                if win.winfo_exists():
                    win.destroy()
            except Exception:
                pass

        for attr in popup_attrs:
            setattr(self, attr, None)

        self._creation_windows = []
        self._creation_in_progress = False
        self._image_based_creation_controller = None
        self._image_based_creation_window = None
        self._palette_based_creation_controller = None
        self._palette_based_creation_window = None


    def _can_start_new_creation(self):
        """Allow only one color-space creation workflow at a time."""
        self._ensure_creation_state()

        alive = []
        for w in self._creation_windows:
            try:
                if w is not None and w.winfo_exists():
                    alive.append(w)
            except Exception:
                pass
        self._creation_windows = alive

        if self._creation_windows:
            replace = messagebox.askyesno(
                "Creation in Progress",
                "There is already a color space creation in progress.\n\n"
                "Do you want to close it and start a new one?"
            )
            if not replace:
                return False

            self._close_creation_windows()

        self._creation_in_progress = True
        return True


    def _open_plotly_figure_in_browser(self, fig, filename_prefix="plot"):
        """
        Save a Plotly figure as a temporary HTML file and open it in the default browser.

        Files are stored in:
            external/temp/plots/

        Older files are cleaned automatically every self.TEMP_PLOT_CLEANUP_EVERY plots.
        """
        try:
            plot_dir = self._get_temp_plot_dir()

            safe_prefix = self._safe_plot_filename_prefix(filename_prefix)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            counter = int(getattr(self, "_temp_plot_creation_count", 0)) + 1

            filename = f"{safe_prefix}_{timestamp}_{counter:04d}.html"
            file_path = os.path.join(plot_dir, filename)

            fig.write_html(
                file_path,
                include_plotlyjs=True,
                full_html=True,
                auto_open=False,
                config={
                    "responsive": True,
                    "displaylogo": False,
                }
            )

            webbrowser.open_new_tab(
                Path(file_path).resolve().as_uri()
            )

            self._register_temp_plot_creation()

            return file_path

        except Exception as e:
            try:
                self.custom_warning(
                    "Plot Error",
                    f"Could not open external plot:\n{e}",
                    parent=getattr(self, "_color_evaluation_window", None)
                )
            except Exception:
                pass

            return None


    def _get_temp_plot_dir(self):
        """
        Return the writable folder used for temporary external Plotly files.

        Source execution:
            <project>/Source/external/temp/plots/

        Frozen PyInstaller execution:
            <OS temp>/PyFCS/plots/

        This keeps the familiar external folder during development while
        allowing the distributed one-file application to run without any
        Source/external directory beside it.
        """
        return UtilsTools.get_runtime_temp_dir("plots")


    def _safe_plot_filename_prefix(self, filename_prefix):
        """
        Convert a plot prefix into a safe filename fragment.
        """
        text = str(filename_prefix or "plot").strip()

        safe = "".join(
            ch if ch.isalnum() or ch in ("_", "-", ".") else "_"
            for ch in text
        )

        safe = safe.strip("._-")

        return safe or "plot"


    def _cleanup_temp_plot_files(self):
        """
        Delete the oldest temporary plot HTML files if the folder exceeds
        self.TEMP_PLOT_MAX_FILES.

        Only .html files inside the PyFCS temporary plots directory are affected.
        """
        try:
            plot_dir = self._get_temp_plot_dir()
            max_files = int(getattr(self, "TEMP_PLOT_MAX_FILES", 30))

            if max_files <= 0:
                return

            html_files = []

            for name in os.listdir(plot_dir):
                if not name.lower().endswith(".html"):
                    continue

                full_path = os.path.join(plot_dir, name)

                if os.path.isfile(full_path):
                    html_files.append(full_path)

            if len(html_files) <= max_files:
                return

            html_files.sort(
                key=lambda path: os.path.getmtime(path)
            )

            files_to_delete = html_files[:len(html_files) - max_files]

            for path in files_to_delete:
                try:
                    os.remove(path)
                except Exception:
                    pass

        except Exception:
            pass


    def _register_temp_plot_creation(self):
        """
        Count created external plots and run cleanup every self.TEMP_PLOT_CLEANUP_EVERY creations.
        """
        try:
            current_count = int(getattr(self, "_temp_plot_creation_count", 0))
        except Exception:
            current_count = 0

        current_count += 1
        self._temp_plot_creation_count = current_count

        try:
            cleanup_every = int(getattr(self, "TEMP_PLOT_CLEANUP_EVERY", 5))
        except Exception:
            cleanup_every = 5

        cleanup_every = max(1, cleanup_every)

        if current_count % cleanup_every == 0:
            self._cleanup_temp_plot_files()


    def open_image_inspection(self, initial_info=None):
        """
        Open the persistent Image Inspection workspace.

        A loaded Fuzzy Color Space is required, but an image is not. If no
        color space is active, the user is offered the normal load workflow.
        If initial_info is provided, Image Inspection starts from that selected
        pixel/ROI. Otherwise it opens in general inspection mode.
        """

        # Option A: an image is not required here. The inspection workspace can
        # open empty and its own Open Image action can be used afterwards.
        if not self._ensure_fuzzy_color_space_loaded_for_feature(
            "Image Inspection",
            on_success=lambda: self.open_image_inspection(initial_info=initial_info),
        ):
            return

        self._ensure_threshold_settings()
        self._close_image_inspection_window()

        controller = ImageInspectionManager(
            self,
            initial_info if isinstance(initial_info, dict) else {}
        )

        self._image_inspection_controller = controller
        self._image_inspection_window = controller.win

















    # ============================================================================================================================================================
    #  MAIN FUNCTIONS
    # ============================================================================================================================================================

    def update_volumes(self):
        # An empty dataset means that no color space is currently loaded.
        # Handle it explicitly so update_prototypes_info() cannot accidentally
        # re-enable COLOR_SPACE after a Delete operation.
        if not self.color_data:
            self.prototypes = []
            self.cores = []
            self.supports = []
            self.fuzzy_color_space = None

            self.selected_centroids = {}
            self.selected_alpha = []
            self.selected_core = []
            self.selected_support = []

            self.COLOR_SPACE = False
            self._clear_model_3d_color_controls(hide_buttons=True)

            # Hide Search when no color space is loaded.
            self._model_3d_search_frame.pack_forget()
            self._model_3d_search_var.set("")

            self.CAN_APPLY_MAPPING = {key: False for key in self.CAN_APPLY_MAPPING}

            self._invalidate_mapping_caches()
            return

        # Process color prototypes from the input color data
        self.prototypes = UtilsTools.process_prototypes(self.color_data)

        # update_volumes is only used when building a fresh space from .cns;
        # loaded .fcs/.json spaces retain their saved geometry.
        self.fuzzy_color_space = FuzzyColorSpace(space_name=" ", prototypes=self.prototypes)

        # Precompute internal fuzzy structures for efficiency
        self.fuzzy_color_space.precompute_pack()

        # Retrieve core and support regions from the fuzzy color space
        self.cores = self.fuzzy_color_space.get_cores()
        self.supports = self.fuzzy_color_space.get_supports()

        self.update_prototypes_info()


    def _geometry_for_categories(self, selected_labels, granule_labels=None):
        """Select real Voronoi/Core/Support objects without rebuilding geometry.

        ``granule_labels=None`` retains the legacy all-granules semantics used
        while loading a space; an explicit empty set selects no geometry.
        """
        space = getattr(self, "fuzzy_color_space", None)
        selected = set(selected_labels)
        if isinstance(space, GranularFuzzyColorSpace):
            granules = None if granule_labels is None else set(granule_labels)
            selected_entries = [
                (cat, i) for cat in space.categories if cat.label in selected
                for i, p in enumerate(cat.prototypes)
                if granules is None or p.label in granules
            ]
            return (
                [cat.prototypes[i] for cat, i in selected_entries],
                [cat.cores[i] for cat, i in selected_entries],
                [cat.supports[i] for cat, i in selected_entries],
            )
        indices = [i for i, proto in enumerate(getattr(self, "prototypes", []))
                   if proto.label in selected]
        return ([self.prototypes[i] for i in indices],
                [self.cores[i] for i in indices],
                [self.supports[i] for i in indices])

    def _selected_model_granules(self):
        """Return visible granule names, defaulting to all before controls exist."""
        space = getattr(self, "fuzzy_color_space", None)
        if not isinstance(space, GranularFuzzyColorSpace):
            return None
        state = getattr(self, "selected_granules", None)
        if not isinstance(state, dict):
            return {p.label for cat in space.categories for p in cat.prototypes}
        return {name for name, var in state.items() if var.get()}

    def _granular_visualization_data(self):
        """Return markers for only the selected real granules in native geometry."""
        space = getattr(self, "fuzzy_color_space", None)
        selected = set(self.selected_centroids)
        color_data, hexes = {}, {}
        if not isinstance(space, GranularFuzzyColorSpace):
            return self.selected_centroids, self.hex_color
        visible = self._selected_model_granules()
        for cat in space.categories:
            if cat.label not in selected:
                continue
            for proto in cat.prototypes:
                if proto.label not in visible:
                    continue
                xyz = np.asarray(proto.positive, dtype=float)
                lab = space.lab_from_model(xyz)
                color_data[proto.label] = {"positive_prototype": xyz}
                hexes[UtilsTools.lab_to_hex(lab)] = xyz
        return color_data, hexes

    def _granular_save_options(self, new_color_data):
        """Prepare a complete grouped model from Data (no silent flattening).

        Unedited native RGB coordinates are preserved bit-for-bit. Any edited
        LAB prototype is converted with the same gamut checks as atomic FCS.
        Explicit negative references follow their old granule if it moves.
        """
        space = self.fuzzy_color_space
        old_groups = ({cat.label: cat for cat in space.categories}
                      if isinstance(space, GranularFuzzyColorSpace) else {})
        old_sites = ({p.label: np.asarray(p.positive, dtype=float)
                      for cat in space.categories for p in cat.prototypes}
                     if isinstance(space, GranularFuzzyColorSpace) else
                     {p.label: np.asarray(p.positive, dtype=float)
                      for p in space.prototypes})
        pending = getattr(self, "_pending_granules", {}) or {}
        categories = {}
        updated_by_old = {}
        for label, row in new_color_data.items():
            source = row.get("fcs_original_label", label)
            if source in pending:
                entries = copy.deepcopy(pending[source])
            elif source in old_groups:
                entries = [{"label": p.label, "original_label": p.label,
                            "prototype_lab": list(space.lab_from_model(p.positive))}
                           for p in old_groups[source].prototypes]
            elif source in old_sites:
                entries = [{"label": source, "original_label": source,
                            "prototype_lab": list(space.lab_from_model(old_sites[source]))}]
            else:
                entries = [{"label": label, "original_label": None,
                            "prototype_lab": list(row["positive_prototype"])}]
            # The visible Data representative is always the first real granule.
            # It may have been edited after closing the Granules dialog.
            entries[0]["prototype_lab"] = list(np.asarray(
                row["positive_prototype"], dtype=float).reshape(3))
            converted = {}
            for item in entries:
                glabel = item["label"]
                lab = np.asarray(item["prototype_lab"], dtype=float).reshape(3)
                old = item.get("original_label")
                if old in old_sites and np.linalg.norm(
                        np.asarray(space.lab_from_model(old_sites[old])) - lab) < 1e-5:
                    value = old_sites[old].copy()
                elif space.color_space == "LAB":
                    value = lab
                else:
                    value = lab_to_rgb_model_checked(lab.reshape(1, 3))[0]
                converted[glabel] = value
                if old in old_sites:
                    updated_by_old[old] = value
            categories[label] = converted

        auxiliary = [tuple(map(float, p)) for p in getattr(space, "auxiliary_negatives", [])]
        negatives = {}
        if not space.disjoint:
            for label, row in new_color_data.items():
                source = row.get("fcs_original_label", label)
                own = []
                for q in space.negative_prototypes.get(source, []):
                    xyz = np.asarray(q, dtype=float).reshape(3)
                    if any(np.linalg.norm(xyz - aux) < 1e-7 for aux in auxiliary):
                        continue
                    match = next((old for old, v in old_sites.items()
                                  if np.linalg.norm(v - xyz) < 1e-7), None)
                    if match is not None:
                        if match not in updated_by_old:
                            raise ValueError(f"A negative used by '{label}' refers to a deleted granule '{match}'.")
                        xyz = updated_by_old[match]
                    own.append(tuple(xyz))
                negatives[label] = own

        prebuilt = None
        if isinstance(space, GranularFuzzyColorSpace):
            # Renaming the file or reapplying unchanged Data must not rerun
            # Voronoi or perturb already-imported stored polyhedra.
            original_cats = {cat.label: cat for cat in space.categories}
            if list(categories) == list(original_cats) and all(
                list(granules) == [p.label for p in original_cats[label].prototypes]
                and all(np.array_equal(np.asarray(value, dtype=float), old.positive)
                        for value, old in zip(granules.values(), original_cats[label].prototypes))
                for label, granules in categories.items()
            ):
                prebuilt = space
        return {
            "_granular_prebuilt_space": prebuilt,
            "_granular_categories": categories,
            "color_space": space.color_space,
            "reference_domain": space.reference_domain,
            "lambda1": space.lambda1, "lambda2": space.lambda2,
            "disjoint": space.disjoint, "covering": space.covering,
            "samples": space.samples or 27,
            "negative_prototypes": negatives,
            "auxiliary_negatives": auxiliary if not space.covering else [],
            "tconorm": (getattr(self, "_pending_granular_tconorm", None)
                        or getattr(space, "tconorm", "bounded_sum")),
        }

    def update_prototypes_info(self):
        # Update 3D graph flags and application state variables
        self.COLOR_SPACE = True
        self._sync_image_mapping_tconorm_buttons()

        # Show Search when a color space is loaded.
        if not self._model_3d_search_frame.winfo_manager():
            self._model_3d_search_frame.pack(
                fill="x",
                padx=5,
                pady=(0, 5)
            )

        locked = getattr(self, "mapping_locked_until_original", {}) or {}
        self.CAN_APPLY_MAPPING = {
            key: not bool(locked.get(key, False))
            for key in self.CAN_APPLY_MAPPING
        }

        # Display selection control buttons
        if not self.select_all_button.winfo_ismapped():
            self.select_all_button.pack(pady=5)

        if not self.deselect_all_button.winfo_ismapped():
            self.deselect_all_button.pack(pady=5)

        # Store current selections for visualization and processing
        self.selected_centroids = self.color_data
        self.selected_hex_color = self.hex_color
        self.selected_alpha, self.selected_core, self.selected_support = (
            self._geometry_for_categories(self.color_data)
        )

        # Trigger update based on the selected options
        self.on_option_select()


    def _sync_image_mapping_tconorm_buttons(self):
        """Display the single shared operator; atomic spaces cannot aggregate."""
        buttons = getattr(self, "_mapping_tconorm_buttons", {})
        space = getattr(self, "fuzzy_color_space", None)
        enabled = bool(getattr(space, "is_granular", False))
        current = getattr(space, "tconorm", "bounded_sum")
        for mode, button in buttons.items():
            active = mode == current
            button.configure(
                state="normal" if enabled else "disabled",
                bg=UtilsTools.UI_ACCENT_SOFT if active else "#f5f5f5",
                fg=UtilsTools.UI_ACCENT_DARK if active else "#535965",
                activebackground=UtilsTools.UI_ACCENT_HOVER if active else "#f5f5f5",
                font=("Segoe UI", 8, "bold" if active else "normal"),
            )

    def _set_image_mapping_tconorm(self, operator):
        """Change the shared T-conorm and refresh already-displayed mappings."""
        space = getattr(self, "fuzzy_color_space", None)
        if not getattr(space, "is_granular", False):
            return
        if operator == space.tconorm:
            return
        if self._has_any_active_job():
            self.custom_warning("Process Running",
                "Finish or cancel the active process before changing the T-conorm.")
            return
        # Capture the displayed selections BEFORE restoring old mappings.
        snapshots = []
        for wid, mode in list(getattr(self, "window_mapping_mode", {}).items()):
            if mode in ("single", "all"):
                info = getattr(self, "proto_options", {}).get(wid, {})
                snapshots.append((wid, mode, info.get("selection"),
                                  info.get("display_style", "gray"),
                                  getattr(self, "_mapping_all_pack_by_window", {}).get(wid, {}).get("level", "categories"),
                                  getattr(self, "_mapping_all_pack_by_window", {}).get(wid, {}).get("scheme", "original")))
        controller = getattr(self, "_image_inspection_controller", None)
        inspector_open = False
        try:
            inspector_open = bool(controller and controller.win.winfo_exists())
        except Exception:
            pass
        if inspector_open:
            # The inspection controller already handles membership refresh and
            # cache invalidation, so avoid a duplicate invalidation here.
            controller._set_tconorm_choice(operator.upper())
        else:
            self._prepare_open_images_for_color_space_change()
            space.set_tconorm(operator)
            self._invalidate_mapping_caches()
        self._sync_image_mapping_tconorm_buttons()
        if space.tconorm != operator:
            return
        # Reapply existing maps from the original image. A new membership
        # calculation is necessary; palette-only changes remain instantaneous.
        for wid, mode, selection, style, level, scheme in snapshots:
            if wid not in getattr(self, "window_image_key", {}):
                continue
            if mode == "all":
                self._mapping_all_initial_view = getattr(self, "_mapping_all_initial_view", {})
                self._mapping_all_initial_view[wid] = (level, scheme)
                self.color_mapping_all(wid)
            elif mode == "single":
                self.color_mapping(wid)
                info = getattr(self, "proto_options", {}).get(wid)
                if isinstance(info, dict):
                    info["display_style"] = style
                    if selection is not None:
                        info["selection"] = selection
                        self._refresh_single_mapping_rows(wid)
                        self._render_proto_options(wid)
                        self.get_proto_percentage(wid)

    def _prepare_open_images_for_color_space_change(self):
        """
        Detach current image mappings from the color space that produced them.

        Single-prototype mappings return to Original immediately. Mapping-All
        views may stay visible, but are explicitly locked as results of the old
        color space until the user chooses a valid view/mapping for the new one.
        """
        if not hasattr(self, "mapping_locked_until_original"):
            self.mapping_locked_until_original = {}

        if not hasattr(self, "floating_images") or not self.floating_images:
            return

        for window_id in list(self.floating_images.keys()):
            mode = getattr(self, "window_mapping_mode", {}).get(window_id)

            if mode == "single":
                try:
                    self.show_original_image(window_id)
                except Exception:
                    pass

            elif mode == "all":
                self.mapping_locked_until_original[window_id] = True
                self.CAN_APPLY_MAPPING[window_id] = False
                try:
                    self.image_canvas.itemconfig(f"{window_id}_pct_text", text="")
                except Exception:
                    pass


    def _invalidate_mapping_caches(self):
        """Invalidate all results whose memberships depend on the active FCS."""
        self._sync_image_mapping_tconorm_buttons()
        # Image Inspection also changes the shared operator. Keep the compact
        # readout synchronized whichever window initiated the change.
        self._refresh_pixel_info_memberships()
        if hasattr(self, "cm_cache_by_image"):
            self.cm_cache_by_image.clear()
        if hasattr(self, "proto_percentage_cache_by_image"):
            self.proto_percentage_cache_by_image.clear()
        if hasattr(self, "_mapping_all_pack_by_window"):
            self._mapping_all_pack_by_window.clear()
        controller = getattr(self, "_full_resolution_workspace_controller", None)
        if controller is not None:
            try:
                controller.invalidate_model()
            except tk.TclError:
                pass


    def _prepare_color_space_load(self, filename):
        """Parse/validate/build the candidate FCS outside the Tk event loop.

        This worker phase must not access Tk widgets or mutate the currently
        active workspace. CNS warnings are returned for display on the UI
        thread instead of opening messageboxes inside the worker.
        """
        extension = os.path.splitext(filename)[1].lower()
        handler = Input.instance(extension)
        warning_message = None
        if extension == ".cns":
            new_color_data = handler.read_file(filename)
            source_type = "cns"
            source_native = str(getattr(handler, "last_color_space", "LAB") or "LAB").upper()
            warning_message = getattr(handler, "last_warning", None)
            data = {"color_data": new_color_data, "type": source_type,
                    "source_color_space": source_native}
        elif extension in (".fcs", ".json"):
            new_color_data, new_fuzzy_color_space = handler.read_file(filename)
            source_type = "fcs"
            data = {"color_data": new_color_data, "type": source_type,
                    "fuzzy_color_space": new_fuzzy_color_space}
        else:
            raise ValueError(f"Unsupported color-space file format: {extension}")

        if not isinstance(data, dict) or "color_data" not in data or "type" not in data:
            raise ValueError("The selected file did not return valid color-space data.")

        new_color_data = data["color_data"]
        if not isinstance(new_color_data, dict) or len(new_color_data) < 2:
            raise ValueError("The file must contain at least two valid, named colors.")
        for color_label, row in new_color_data.items():
            if not str(color_label).strip() or not isinstance(row, dict):
                raise ValueError("The file contains an empty or malformed color entry.")
            coords = np.asarray(row.get("positive_prototype", []), dtype=float).reshape(-1)
            if coords.size != 3 or not np.all(np.isfinite(coords)):
                raise ValueError(f"Invalid color coordinates for '{color_label}'.")

        if source_type == "cns":
            # Data rows remain LAB; the geometry is built in the CNS's native
            # space exactly as in the previous synchronous implementation.
            native = data["source_color_space"]
            if native not in ("LAB", "RGB"):
                raise ValueError("CNS color space must be LAB or RGB.")
            native_points = {
                label: np.asarray(
                    row["Color"] if native == "RGB" else row["positive_prototype"],
                    dtype=float,
                ).reshape(3)
                for label, row in new_color_data.items()
            }
            new_fuzzy_color_space = FuzzyColorSpaceBuilder.build(
                os.path.splitext(os.path.basename(filename))[0],
                native_points, color_space=native,
            )
        else:
            new_fuzzy_color_space = data.get("fuzzy_color_space")
            if new_fuzzy_color_space is None:
                raise ValueError("The selected FCS file does not contain a valid fuzzy color space.")
            native = new_fuzzy_color_space.color_space

        new_fuzzy_color_space.precompute_pack()
        return {
            "color_data": new_color_data,
            "space": new_fuzzy_color_space,
            "source_type": source_type,
            "native_source": native,
            "warning_message": warning_message,
        }

    def _commit_color_space_load(self, filename, prepared):
        """Update the GUI and active workspace on Tk's main thread only."""
        editor = getattr(self, "_modify_fcs_dialog", None)
        if editor is not None:
            editor.close()  # A new FCS invalidates the old editing snapshot.
        new_color_data = prepared["color_data"]
        new_fuzzy_color_space = prepared["space"]
        source_type = prepared["source_type"]

        # Only replace the current model after parsing and construction have
        # succeeded; a malformed input never clears the old FCS.
        self._reset_image_inspection_state()
        self._prepare_open_images_for_color_space_change()

        self.file_path = filename
        self.file_base_name = os.path.splitext(os.path.basename(filename))[0]
        self._data_expanded_categories = set()
        self.color_data = new_color_data
        self.edit_color_data = copy.deepcopy(new_color_data)
        self._pending_granules = {}
        self._pending_granular_tconorm = None
        self.fuzzy_color_space = new_fuzzy_color_space
        self._model_space_unsaved = False
        native_source = str(prepared["native_source"]).upper()
        if native_source not in ("LAB", "RGB"):
            native_source = "LAB"
        self.loaded_source_color_space = native_source
        if source_type == "cns":
            self.prototypes = new_fuzzy_color_space.get_prototypes()
            self.cores = new_fuzzy_color_space.get_cores()
            self.supports = new_fuzzy_color_space.get_supports()
        else:
            self.prototypes = new_fuzzy_color_space.prototypes
            self.cores = new_fuzzy_color_space.cores
            self.supports = new_fuzzy_color_space.supports
        self.volume_limits = new_fuzzy_color_space.reference_domain
        self._fcs_creation_defaults = self._options_from_loaded_space(new_fuzzy_color_space)

        self._invalidate_mapping_caches()
        self.display_data_window()
        self._reset_3d_canvas()
        self.update_prototypes_info()
        self._update_model_space_indicator()

    def load_color_space(self, filename=None, *, on_success=None):
        """Start loading asynchronously so the Loading indicator keeps moving.

        Returns True when a load is successfully *started* (not completed).
        The optional on_success callback runs on Tk's thread only after the
        model has been committed. No work on Tk widgets runs in the worker.
        """
        if self._has_any_active_job():
            self.custom_warning(
                "Process Running",
                "There is a process currently running. Please wait for it to finish or cancel it before loading a Color Space."
            )
            return False

        if filename is None:
            filename = UtilsTools.prompt_file_selection(
                "fuzzy_color_spaces/",
                parent=self._get_active_dialog_parent(
                    getattr(self, "_color_evaluation_window", None)
                )
            )
        if not filename:
            return False
        if getattr(self, "_model_space_unsaved", False):
            if not messagebox.askyesno(
                "Unsaved Model Color Space",
                "The reconstructed model has not been saved.\n\n"
                "Load another color space and discard it?",
                parent=self.root,
            ):
                return False

        self._loading_color_space_running = True
        try:
            self.show_loading_color_space()
        except Exception:
            self._loading_color_space_running = False
            raise

        result = {"prepared": None, "error": None}
        finished = threading.Event()

        def worker():
            try:
                result["prepared"] = self._prepare_color_space_load(filename)
            except Exception as exc:
                result["error"] = exc
            finally:
                finished.set()

        def poll_result():
            if not finished.is_set():
                self.root.after(35, poll_result)
                return

            error = result["error"]
            prepared = result["prepared"]
            if error is None:
                try:
                    self._commit_color_space_load(filename, prepared)
                except Exception as exc:
                    error = exc

            # Release the modal grab before opening any subsequent messagebox.
            self._loading_color_space_running = False
            self.hide_loading()
            if error is not None:
                self.custom_warning("File Error", str(error))
                return
            if prepared["warning_message"]:
                messagebox.showwarning(
                    "CNS File Warning", prepared["warning_message"], parent=self.root
                )
            if on_success is not None:
                on_success()

        try:
            self.root.after(35, poll_result)
            threading.Thread(target=worker, daemon=True).start()
        except Exception:
            self._loading_color_space_running = False
            self.hide_loading()
            raise
        return True


    def _options_from_loaded_space(self, space, new_color_data=None):
        """Save the current model, its exact coordinates and negative choices.

        Editable Data rows are LAB because the evaluation pipeline works in
        CIELAB. Persist *native* representatives unchanged when they have not
        been edited, particularly for an imported RGB or JFCS space.
        """
        if space is None:
            return {}
        rows = new_color_data if new_color_data is not None else getattr(self, "color_data", {})
        originals = {p.label: np.asarray(p.positive, dtype=float) for p in space.prototypes}
        source_by_label = {name: entry.get("fcs_original_label", name)
                           for name, entry in rows.items()}
        old_to_new = {original: name for name, original in source_by_label.items()}
        options = dict(
            color_space=space.color_space, reference_domain=space.reference_domain,
            lambda1=space.lambda1, lambda2=space.lambda2,
            disjoint=space.disjoint, covering=space.covering,
            samples=space.samples or 27,
            description=space.description,
        )
        native_points = {}
        for name, old_name in source_by_label.items():
            if old_name not in originals:
                continue
            row = rows[name]
            original_lab = np.asarray(space.lab_from_model(originals[old_name]), dtype=float)
            current_lab = np.asarray(row.get("positive_prototype", row.get("Color", [])), dtype=float).reshape(-1)
            if current_lab.shape == (3,) and np.all(np.isfinite(current_lab)) and np.linalg.norm(
                    original_lab - current_lab) < 1e-5:
                native_points[name] = originals[old_name].copy()
        options["model_points"] = native_points

        if not space.disjoint:
            # Match negatives that refer to a category by label so renaming a
            # category retains its relationships. Preserve independent negative
            # coordinates as LAB triples rather than discarding them.
            auxiliary = np.asarray(getattr(space, "auxiliary_negatives", []), dtype=float).reshape(-1, 3)
            negative_choices = {}
            for new_name, old_name in source_by_label.items():
                choices = []
                for neg in space.negative_prototypes.get(old_name, []):
                    xyz = np.asarray(neg, dtype=float).reshape(3)
                    if len(auxiliary) and np.any(np.linalg.norm(auxiliary - xyz, axis=1) < 1e-6):
                        continue
                    matching = next((label for label, value in originals.items()
                                     if label != old_name and np.linalg.norm(xyz - value) < 1e-6), None)
                    if matching is not None:
                        if matching in old_to_new:
                            choices.append(old_to_new[matching])
                    else:
                        choices.append(tuple(space.lab_from_model(xyz)))
                negative_choices[new_name] = list(dict.fromkeys(choices))
            options["negative_prototypes"] = negative_choices
        return options

    def create_color_space(self, parent=None):
        """
        Create a fuzzy color space from the selected colors and prompt the user for its name.
        Once confirmed, save the color space.

        Returns
        -------
        bool
            True if the color space creation/save process was started.
            False if cancelled, invalid, or not enough colors were selected.
        """
        selected_colors_lab = {}
        for name, data in getattr(self, "color_checks", {}).items():
            try:
                if not data.get("var") or not data["var"].get():
                    continue
                lab = data.get("lab")
                if isinstance(lab, dict):
                    arr = np.array([lab["L"], lab["A"], lab["B"]], dtype=float)
                else:
                    arr = np.asarray(lab, dtype=float).reshape(-1)
                if arr.size != 3 or not np.all(np.isfinite(arr)):
                    raise ValueError("Coordinates must contain three finite numbers.")
                selected_colors_lab[name] = arr
            except (KeyError, ValueError, TypeError) as exc:
                self.custom_warning("Invalid Color", f"Cannot use '{name}': {exc}")
                return False

        parent_win = parent if parent is not None else self.root

        try:
            if parent_win is None or not parent_win.winfo_exists():
                parent_win = self.root
        except Exception:
            parent_win = self.root

        if len(selected_colors_lab) < 2:
            self.custom_warning(
                "Warning",
                "At least two colors must be selected to create the Color Space.",
                parent=parent_win
            )
            return False

        # Validate the selected prototypes using the same reference domain and
        # merge tolerance as the shared geometry utilities.
        invalid_colors = [
            name
            for name, lab in selected_colors_lab.items()
            if not UtilsTools.is_valid_lab(lab)
        ]
        if invalid_colors:
            preview = ", ".join(invalid_colors[:6])
            if len(invalid_colors) > 6:
                preview += f", ... (+{len(invalid_colors) - 6})"
            self.custom_warning(
                "Invalid LAB Colors",
                "The selected colors contain LAB values outside the PyFCS reference domain:\n\n"
                + preview,
                parent=parent_win,
            )
            return False

        duplicate_lab_pairs = UtilsTools.find_duplicate_lab_pairs(selected_colors_lab)

        if duplicate_lab_pairs:
            lines = []
            max_lines = 6
            for name_a, name_b, lab in duplicate_lab_pairs[:max_lines]:
                lines.append(
                    f"• {name_a} / {name_b}  "
                    f"(L*={lab[0]:.4f}, a*={lab[1]:.4f}, b*={lab[2]:.4f})"
                )

            if len(duplicate_lab_pairs) > max_lines:
                lines.append(
                    f"• ... and {len(duplicate_lab_pairs) - max_lines} more duplicate pair(s)"
                )

            self.custom_warning(
                "Duplicate LAB Colors",
                "A Color Space cannot contain two selected colors whose CIELAB "
                "prototypes collide within the Voronoi merge tolerance.\n\n"
                + "\n".join(lines),
                parent=parent_win,
            )
            return False

        # UI-only component: all geometry, validation and persistence stay in
        # the existing application and FuzzyColorSpaceBuilder.
        from Source.geometry.Voronoi import Voronoi

        def on_create(name, options):
            mode = options["color_space"]
            domain = options["reference_domain"]
            points = {
                label: (
                    np.asarray(lab, dtype=float)
                    if mode == "LAB" else
                    lab_to_rgb_model_checked(np.asarray(lab, dtype=float).reshape(1, 3))[0]
                )
                for label, lab in selected_colors_lab.items()
            }
            Voronoi._validate_points_in_domain(
                np.asarray(list(points.values())), domain, Voronoi.DEFAULT_EPS
            )
            return self.save_cs(name, selected_colors_lab, options=options)

        dialog = UtilsTools.FCSCreationDialog(
            parent_win,
            selected_colors_lab,
            on_accept=on_create,
            warn=self.custom_warning,
            # A new FCS starts in LAB even if the currently loaded model is RGB.
        )
        dialog.transient(parent_win)
        dialog.grab_set()
        try:
            dialog.lift(parent_win)
            dialog.focus_force()
        except Exception:
            pass
        dialog.wait_window()
        return bool(dialog.result)


    def _on_color_space_saved_success(self, name, file_path=None):
        self._close_creation_windows()

        load_now = messagebox.askyesno(
            "Color Space Created",
            f"Color Space '{name}' created successfully.\n\nDo you want to load it now?"
        )

        if load_now:
            if file_path and os.path.exists(file_path):
                self.load_color_space(file_path)
            else:
                self.custom_warning(
                    "Load Error",
                    "The color space was created successfully, but its file path could not be determined."
                )


    def _on_apply_changes_saved_success(
        self,
        name,
        file_path,
        saved_color_data,
        fuzzy_color_space,
    ):
        self._reset_image_inspection_state()
        self._prepare_open_images_for_color_space_change()
        self._invalidate_mapping_caches()

        self.color_data = copy.deepcopy(saved_color_data)
        # A saved JSON space has *new* canonical labels. Reset its source-label
        # pointers, otherwise subsequent renames may refer to stale labels.
        for color_label, item in self.color_data.items():
            item["fcs_original_label"] = color_label
        if isinstance(fuzzy_color_space, GranularFuzzyColorSpace):
            # Keep the Data rows in sync with the *actual* saved granule list.
            for category in fuzzy_color_space.categories:
                row = self.color_data[category.label]
                labs = [np.asarray(fuzzy_color_space.lab_from_model(p.positive), dtype=float)
                        for p in category.prototypes]
                row["granules"] = [
                    {"label": proto.label, "prototype": lab}
                    for proto, lab in zip(category.prototypes, labs)
                ]
                row["positive_prototype"] = labs[0].copy()
                row["Color"] = labs[0].tolist()
        else:
            # After a model conversion, the actual saved representative may
            # differ infinitesimally from the input LAB because of the
            # conversion. Make all downstream consumers use the saved model.
            for prototype in fuzzy_color_space.prototypes:
                lab = np.asarray(
                    fuzzy_color_space.lab_from_model(prototype.positive),
                    dtype=float,
                )
                row = self.color_data[prototype.label]
                row["positive_prototype"] = lab.copy()
                row["Color"] = lab.tolist()
        self.edit_color_data = copy.deepcopy(self.color_data)
        self._pending_granules = {}
        self._pending_granular_tconorm = None
        self.file_path = file_path
        # Preserve the actual space name; the last color label must never
        # replace it (e.g. "Black" when the space is named "a").
        self.file_base_name = name

        # The writer already built the Voronoi geometry; reuse it after saving.
        self.fuzzy_color_space = fuzzy_color_space
        self.fuzzy_color_space.space_name = name
        self._model_space_unsaved = False
        # Editing/saving may change the model's geometric space.
        self.loaded_source_color_space = fuzzy_color_space.color_space
        self.prototypes = fuzzy_color_space.get_prototypes()
        self.fuzzy_color_space.precompute_pack()
        self.cores = fuzzy_color_space.get_cores()
        self.supports = fuzzy_color_space.get_supports()
        self.volume_limits = fuzzy_color_space.reference_domain
        self._fcs_creation_defaults = self._options_from_loaded_space(fuzzy_color_space)
        self.update_prototypes_info()
        self._update_model_space_indicator()

        self.display_data_window()

        messagebox.showinfo(
            "Changes Applied",
            f"Color Space '{name}' was updated successfully."
        )
        

    def _save_color_space_file(self, name, color_dict, saved_color_data=None,
                               apply_after_save=False, options=None):
        """Build and atomically save a JSON color space without blocking Tk."""
        if self._has_any_active_job() or getattr(self, "_processing_job_running", False):
            self.custom_warning("Process Running", "Finish the current task before saving a color space.")
            return False

        # Validate and ask *before* launching any worker. The JSON writer preserves complete Core/Voronoi/Support geometry.
        try:
            safe_name = UtilsTools.validate_color_space_name(name)
            target_file = os.path.abspath(os.path.join(
                UtilsTools.get_base_path(), "fuzzy_color_spaces", safe_name + ".json"
            ))
        except (TypeError, ValueError) as exc:
            self.custom_warning("Invalid Color Space Name", str(exc))
            return False

        current_file = getattr(self, "file_path", None)
        editing_same_file = (
            apply_after_save and current_file is not None
            and os.path.normcase(os.path.abspath(str(current_file)))
                == os.path.normcase(target_file)
        )
        if os.path.isfile(target_file) and not editing_same_file:
            # Prefer the grabbed creation/data dialog, if any. A confirmation
            # behind that modal window would be impossible to interact with.
            try:
                confirm_parent = self.root.grab_current()
            except tk.TclError:
                confirm_parent = None
            if confirm_parent is None:
                confirm_parent = self._get_active_dialog_parent()
            if not messagebox.askyesno(
                "Overwrite Color Space",
                f"The color space '{safe_name}' already exists.\n\n"
                "Do you want to replace its file?",
                parent=confirm_parent,
                icon="warning",
            ):
                return False

        self._processing_job_running = True
        try:
            self.show_loading(
                title="Processing Color Space",
                message="Building Core, Voronoi and Support geometry...",
                note="The color-space file is saved only after processing succeeds."
            )
        except Exception:
            self._processing_job_running = False
            raise

        def update_progress(current_line, total_lines):
            """The writer reports actual serialized lines, not geometry time."""
            if total_lines <= 0:
                return
            pct = 100.0 * current_line / total_lines
            try:
                self.root.after(
                    0,
                    lambda value=pct: self._set_processing_progress(
                        value=value, message="Writing the JSON file..."
                    )
                )
            except (RuntimeError, tk.TclError):
                pass

        def run_save_process():
            result = None
            error = None
            try:
                writer = Input.instance(".json")
                save_options = dict(options or {})
                granular_categories = save_options.pop("_granular_categories", None)
                prebuilt_space = save_options.pop("_granular_prebuilt_space", None)
                target_for_modify = save_options.pop("_target_model_for_modify", None)
                modified_draft = save_options.pop("_modified_draft", None)
                original_model = save_options.pop("_original_model", None)
                save_options.pop("_from_modify_fcs", None)
                if modified_draft is not None:
                    prepared = DataManager.build_model_from_draft(
                        name, modified_draft, original_model, target_for_modify,
                    )
                    result = writer.save_space(
                        prepared, name=name, progress_callback=update_progress,
                        return_fuzzy_space=apply_after_save,
                    )
                elif target_for_modify is not None:
                    # Prepare the full edited model in the worker and only then
                    # save it; never write an intermediate model or mutate the
                    # active FCS before the JSON write completes.
                    prepared = DataManager.prepare_modified_model(
                        name, color_dict, save_options, target_for_modify,
                        prebuilt=prebuilt_space,
                        granular_categories=granular_categories,
                    )
                    result = writer.save_space(
                        prepared, name=name, progress_callback=update_progress,
                        return_fuzzy_space=apply_after_save,
                    )
                elif prebuilt_space is not None:
                    # Runtime-only t-conorm may have changed in the editor;
                    # this is not part of the serialized JSON geometry.
                    operator = save_options.get("tconorm", "bounded_sum")
                    prebuilt_space.set_tconorm(operator)
                    result = writer.save_space(
                        prebuilt_space, name=name, progress_callback=update_progress,
                        return_fuzzy_space=apply_after_save,
                    )
                elif granular_categories is not None:
                    result = writer.write_granular_file(
                        name, granular_categories, progress_callback=update_progress,
                        return_fuzzy_space=apply_after_save,
                        **save_options,
                    )
                else:
                    result = writer.write_file(
                        name, color_dict, progress_callback=update_progress,
                        return_fuzzy_space=apply_after_save,
                        **save_options,
                    )
            except Exception as exc:
                error = exc

            # All UI operations, including hiding the modal loading popup,
            # happen in one ordered main-thread callback. In particular, the
            # success/warning dialogs must never appear under its grab.
            def finalize():
                self._processing_job_running = False
                self.hide_loading()
                editor = getattr(self, "_modify_fcs_dialog", None)
                editing_from_modify = bool((options or {}).get("_from_modify_fcs"))
                if error is not None:
                    if editing_from_modify and editor is not None:
                        editor.on_save_failure(str(error))
                    self.custom_warning("Error", f"An error occurred while saving: {error}")
                elif apply_after_save:
                    file_path, space = result
                    if editing_from_modify and editor is not None:
                        editor.on_save_success()
                    self._on_apply_changes_saved_success(
                        name, file_path, saved_color_data, space
                    )
                else:
                    self._on_color_space_saved_success(name, result)

            try:
                self.root.after(0, finalize)
            except (RuntimeError, tk.TclError):
                self._processing_job_running = False

        try:
            threading.Thread(target=run_save_process, daemon=True).start()
        except Exception:
            self._processing_job_running = False
            self.hide_loading()
            raise
        return True

    def save_cs(self, name, selected_colors_lab, options=None):
        return self._save_color_space_file(name, selected_colors_lab, options=options)


    def save_json(self, name, colors, color_dict=None, apply_after_save=False,
                 options=None):
        if color_dict is None:
            color_dict = {}
            used_names = set()

            for idx, item in enumerate(colors):
                color_name = item.get("name", "").strip()
                if not color_name:
                    color_name = f"Color_{idx + 1}"

                base_name = color_name
                suffix = 2
                while color_name in used_names:
                    color_name = f"{base_name}_{suffix}"
                    suffix += 1

                used_names.add(color_name)
                color_dict[color_name] = np.array(item["lab"], dtype=float)

            self.color_entry_detect.clear()

        return self._save_color_space_file(
            name,
            color_dict,
            saved_color_data=copy.deepcopy(colors),
            apply_after_save=apply_after_save,
            options=options,
        )
    

    def _get_color_wheel_image(self, canvas_size=300):
        """
        Build the color wheel image once and reuse it in subsequent popups.
        """
        cache_key = f"color_wheel_{canvas_size}"

        if not hasattr(self, "_ui_cache"):
            self._ui_cache = {}

        if cache_key in self._ui_cache:
            return self._ui_cache[cache_key]

        center = canvas_size // 2
        radius = center - 5

        wheel_img = Image.new("RGB", (canvas_size, canvas_size), "white")
        pixels = wheel_img.load()

        for y in range(canvas_size):
            dy = y - center
            for x in range(canvas_size):
                dx = x - center
                dist = math.sqrt(dx * dx + dy * dy)

                if dist <= radius:
                    angle = math.atan2(dy, dx)
                    hue = (angle / (2 * math.pi)) % 1.0
                    r, g, b = UtilsTools.hsv_to_rgb(hue, 1, 1)
                    pixels[x, y] = (r, g, b)

        tk_wheel_img = ImageTk.PhotoImage(wheel_img)
        self._ui_cache[cache_key] = {
            "pil": wheel_img,
            "tk": tk_wheel_img,
            "center": center,
            "radius": radius,
            "size": canvas_size,
        }
        return self._ui_cache[cache_key]


    # ============================================================================
    # Palette-Based Fuzzy Color Space Creation
    # ============================================================================
    def palette_based_creation(self):
        """
        Open the single-window Palette-Based Color Space Creation workspace.
        """
        if not self._can_start_new_creation():
            return

        try:
            controller = PaletteBasedCreationManager(self)
        except Exception:
            self._creation_in_progress = False
            raise

        self._palette_based_creation_controller = controller
        self._palette_based_creation_window = controller.win


    def image_based_creation(self):
        """
        Open the single-workspace Image-Based Color Space Creation tool.

        Existing workspace images are available automatically. If none is
        loaded, offer to open one specifically for this creation workspace.
        Images opened from Image-Based Creation are temporary and are not added
        to the main Image Display.
        """
        has_workspace_images = bool(getattr(self, "load_images_names", {}))
        open_image_on_start = False

        if not has_workspace_images:
            open_image_on_start = messagebox.askyesno(
                "Image-Based Creation",
                "Image-Based Creation requires an image.\n\n"
                "Do you want to open one now?",
                parent=self._get_active_dialog_parent(),
                icon="warning",
            )

            if not open_image_on_start:
                return

        if not self._can_start_new_creation():
            return

        self.FIRST_DBSCAN = True

        try:
            controller = ImageBasedCreationManager(
                self,
                open_image_on_start=open_image_on_start,
            )
        except Exception:
            self._creation_in_progress = False
            raise

        self._image_based_creation_controller = controller
        self._image_based_creation_window = controller.win


    def _get_best_image_source_pil(self, window_id, prefer_current_view=True, rgb=True):
        """
        Return the best available PIL image source for image tools.

        If prefer_current_view=True:
            Use the current visible source first. This may be Original, Color Mapping,
            or Color Mapping All.

        If prefer_current_view=False:
            Use the real original image first. This is the correct mode for:
            - Image-Based Color Space Creation
            - Manual color picking
            - Automatic color detection
        """
        def _to_pil(obj):
            if isinstance(obj, Image.Image):
                return obj.convert("RGB") if rgb else obj.copy()

            if isinstance(obj, np.ndarray):
                arr = obj

                if arr.dtype != np.uint8:
                    arr = np.clip(arr, 0, 255).astype(np.uint8)

                if arr.ndim == 2:
                    img = Image.fromarray(arr, "L")
                    return img.convert("RGB") if rgb else img

                if arr.ndim == 3:
                    if arr.shape[2] == 4:
                        img = Image.fromarray(arr, "RGBA")
                        return img.convert("RGB") if rgb else img

                    if arr.shape[2] >= 3:
                        img = Image.fromarray(arr[:, :, :3], "RGB")
                        return img.convert("RGB") if rgb else img

            if isinstance(obj, str) and os.path.exists(obj):
                with Image.open(obj) as image_file:
                    img = ImageOps.exif_transpose(image_file)
                    return img.convert("RGB") if rgb else img.copy()

            raise ValueError("Unsupported image format.")

        candidates = []

        if prefer_current_view:
            candidates.append(("image_view_source", getattr(self, "image_view_source", {}).get(window_id)))
            candidates.append(("display_pil", getattr(self, "display_pil", {}).get(window_id)))

        # Original image priority.
        candidates.append(("pil_images_original", getattr(self, "pil_images_original", {}).get(window_id)))

        # Reload from original file path if needed.
        if hasattr(self, "load_images_names") and window_id in self.load_images_names:
            candidates.append(("load_images_names", self.load_images_names.get(window_id)))

        # Last fallback only.
        candidates.append(("images", getattr(self, "images", {}).get(window_id)))

        for _name, obj in candidates:
            if obj is None:
                continue

            try:
                return _to_pil(obj)
            except Exception:
                continue

        raise ValueError(f"No valid image source found for window_id: {window_id}")























    # ============================================================================================================================================================
    #  FUNCTIONS MODEL 3D
    # ============================================================================================================================================================
    def _init_3d_canvas(self):
        """
        Create the matplotlib 3D figure, axis and Tk canvas only once.

        The interactive button is also created here and kept alive across redraws.
        """
        if hasattr(self, "fig_3d") and self.fig_3d is not None:
            return

        self.fig_3d = Figure(figsize=(8, 6), dpi=120)
        self.ax_3d = self.fig_3d.add_subplot(111, projection="3d")

        self.graph_widget = FigureCanvasTkAgg(self.fig_3d, master=self.Canvas1)
        self.graph_widget.draw()
        self.graph_widget.get_tk_widget().pack(fill="both", expand=True)
        self._model_3d_initial_view = None
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


    def _on_add_graph_current(self):
        """
        Open the interactive 3D figure using the currently active display options.
        """
        selected_options = [
            key for key, var in self.model_3d_options.items()
            if var.get()
        ]

        if selected_options:
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
        if event.button != 1 or not getattr(self, "COLOR_SPACE", False):
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
        self._model_3d_rows_container = None
        self._last_color_button_signature = None
        self.selected_colors = {}
        self.selected_granules = None
        self.color_buttons = []
        self._model_3d_expanded_categories = set()
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


    def _reset_3d_canvas(self):
        """
        Fully reset the embedded 3D canvas when a new color space is loaded.
        """
        if hasattr(self, "graph_widget") and self.graph_widget is not None:
            try:
                self.graph_widget.get_tk_widget().destroy()
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

        if self.graph_widget:
            try:
                self.graph_widget.get_tk_widget().destroy()
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


    def _report_ui_callback_exception(self, exc_type, exc_value, exc_traceback):
        """Last-resort GUI error boundary; validation should still happen locally."""
        import traceback
        traceback.print_exception(exc_type, exc_value, exc_traceback)
        if self._reporting_ui_error:
            return
        self._reporting_ui_error = True
        try:
            messagebox.showerror(
                "PyFCS - Operation could not be completed",
                "The requested action could not be completed. "
                "Your previous data has not been intentionally discarded.\n\n"
                f"Details: {exc_value}",
                parent=self.root,
            )
        except (tk.TclError, RuntimeError):
            pass
        finally:
            self._reporting_ui_error = False

    def _update_model_space_indicator(self):
        """Refresh the Data model status and availability of geometry conversion."""
        model = getattr(self, "fuzzy_color_space", None)
        loaded = model is not None and bool(getattr(self, "COLOR_SPACE", False))
        button = getattr(self, "change_model_button", None)
        if button is not None and button.winfo_exists():
            button.configure(state=tk.NORMAL if loaded else tk.DISABLED)
        self._update_data_model_summary()

    def _update_data_model_summary(self):
        """Show topology, geometric model and unsaved status below the short title."""
        label = getattr(self, "data_model_summary", None)
        if label is None or not label.winfo_exists():
            return
        model = getattr(self, "fuzzy_color_space", None)
        if model is None or not getattr(self, "COLOR_SPACE", False):
            label.configure(text="No color space loaded")
            return
        try:
            n_granules = (sum(len(cat.prototypes) for cat in model.categories)
                          if isinstance(model, GranularFuzzyColorSpace)
                          else len(model.prototypes))
            n_categories = (len(model.categories)
                            if isinstance(model, GranularFuzzyColorSpace)
                            else len(model.prototypes))
            counts = f"{n_categories} categories · {n_granules} granules"
        except (AttributeError, TypeError):
            counts = ""
        pieces = [counts, f"{model.color_space} model"]
        if getattr(self, "_model_space_unsaved", False):
            pieces.append("Unsaved")
        label.configure(text="  ·  ".join(piece for piece in pieces if piece))

    def _has_pending_model_data_edits(self):
        """Do not silently discard Data edits when changing the geometry."""
        if getattr(self, "_pending_granules", None):
            return True
        rows = getattr(self, "edit_color_data", {}) or {}
        committed = getattr(self, "color_data", {}) or {}
        if list(rows) != list(committed):
            return True
        for label, value in rows.items():
            old = committed[label]
            for key in ("positive_prototype", "Color"):
                if key in value or key in old:
                    a = np.asarray(value.get(key, []), dtype=float).reshape(-1)
                    b = np.asarray(old.get(key, []), dtype=float).reshape(-1)
                    if a.shape != b.shape or not np.array_equal(a, b):
                        return True
        return False

    def _apply_model_color_space(self, target, prepared_space=None):
        """Rebuild atomically in memory; persist only through Apply Changes."""
        space = getattr(self, "fuzzy_color_space", None)
        if space is None or not getattr(self, "COLOR_SPACE", False):
            raise ValueError("Load a Fuzzy Color Space first.")
        if self._has_any_active_job():
            raise ValueError("Cancel or finish running image-mapping jobs before changing the model.")
        if not self._commit_pending_data_label_changes():
            return False
        if self._has_pending_model_data_edits():
            raise ValueError("Apply your pending changes in Data before changing the model color space.")
        if str(target).upper() == space.color_space:
            return False

        # PREPARE. This may fail (out-of-gamut, duplicates, bad geometry) but
        # MUST NOT mutate the existing model, image jobs, or caches.
        if prepared_space is None:
            rebuilt = rebuild_in_color_space(space, target)
        else:
            if str(prepared_space.color_space).upper() != str(target).upper():
                raise ValueError("The prepared geometry does not match the selected color space.")
            rebuilt = prepared_space
        new_data = copy.deepcopy(self.color_data)
        for proto in rebuilt.prototypes:
            row = new_data[proto.label]
            lab = np.asarray(rebuilt.lab_from_model(proto.positive), dtype=float)
            row["positive_prototype"] = lab
            row["Color"] = lab.tolist()
            row["fcs_original_label"] = proto.label

        # COMMIT. Image-inspection and mapping displays of the old model must
        # not be treated as results of the rebuilt geometry.
        self._reset_image_inspection_state()
        self._prepare_open_images_for_color_space_change()
        self.fuzzy_color_space = rebuilt
        self.color_data = new_data
        self.edit_color_data = copy.deepcopy(new_data)
        self.prototypes = rebuilt.get_prototypes()
        self.cores = rebuilt.get_cores()
        self.supports = rebuilt.get_supports()
        self.volume_limits = rebuilt.reference_domain
        self.loaded_source_color_space = rebuilt.color_space
        self._fcs_creation_defaults = self._options_from_loaded_space(rebuilt)
        self._model_space_unsaved = True
        self._invalidate_mapping_caches()
        self.display_data_window()
        self._reset_3d_canvas()
        self.update_prototypes_info()
        self._update_model_space_indicator()
        return True

    def change_model_color_space(self):
        """Explicitly convert and rebuild the FCS in the selected LAB/RGB space."""
        current = getattr(self, "fuzzy_color_space", None)
        if current is None or not getattr(self, "COLOR_SPACE", False):
            self.custom_warning("Change Color Space", "Load a fuzzy color space first.")
            return
        if self._has_any_active_job():
            self.custom_warning("Change Color Space", "Finish or cancel the active mapping first.")
            return

        popup = tk.Toplevel(self.root)
        popup.withdraw()  # Never display at a temporary/unpositioned location.
        popup.title("Change Color Space")
        popup.configure(bg="#ffffff")
        popup.resizable(False, False)
        popup.transient(self.root)
        popup.protocol("WM_DELETE_WINDOW", popup.destroy)
        popup.bind("<Escape>", lambda _event: popup.destroy())

        content = tk.Frame(popup, bg="#ffffff")
        content.pack(fill="both", expand=True, padx=22, pady=18)
        tk.Label(content, text="Change Color Space", font=("Segoe UI", 12, "bold"),
                 fg="#242633", bg="#ffffff").pack(anchor="w")
        tk.Label(content, text=f"Current color space: {current.color_space}",
                 font=("Segoe UI", 9), fg=UtilsTools.UI_ACCENT_MUTED,
                 bg="#ffffff").pack(anchor="w", pady=(3, 13))

        choice = tk.StringVar(popup, value="RGB" if current.color_space == "LAB" else "LAB")
        choices = tk.Frame(content, bg="#ffffff")
        choices.pack(fill="x")
        for code, desc in (("LAB", "CIELAB"), ("RGB", "sRGB (0–255)")):
            tk.Radiobutton(
                choices, text=f"{code}  —  {desc}", value=code, variable=choice,
                bg="#ffffff", fg="#242633", selectcolor="#ffffff",
                activebackground="#ffffff", activeforeground="#242633",
                font=("Segoe UI", 10), anchor="w", cursor="hand2"
            ).pack(anchor="w", pady=4)

        tk.Frame(content, height=1, bg="#e3e0e7").pack(fill="x", pady=(14, 10))
        explanation = (
            "This rebuilds the Voronoi regions, cores and supports in the "
            "selected model. Memberships may change. The target model uses "
            "its standard reference domain; auxiliary negatives are resampled.\n\n"
            "The original file is not modified until you use Apply Changes. "
            "LAB colors outside the sRGB gamut cannot be converted safely."
        )
        tk.Label(content, text=explanation, wraplength=415, justify="left",
                 font=("Segoe UI", 9), fg="#5e6570", bg="#ffffff").pack(fill="x")
        # The geometry is built away from Tk's event thread so the progress
        # indicator continues to animate. Only the final UI commit runs on Tk.
        busy = {"value": False}
        # A worker completion event avoids raising queue.Empty during normal
        # polling (and avoids Visual Studio/VS Code breaking on it).
        completed = threading.Event()
        outcome = {"rebuilt": None, "error": None}

        ttk.Style(popup).configure(
            "PyFCS.Load.Horizontal.TProgressbar",
            troughcolor="#eae7ef", background=UtilsTools.UI_ACCENT,
            borderwidth=0, thickness=7
        )
        indicator = ttk.Progressbar(
            content, orient="horizontal", mode="indeterminate",
            style="PyFCS.Load.Horizontal.TProgressbar"
        )
        status = tk.Label(
            content, text="", bg="#ffffff", fg="#687180",
            font=("Segoe UI", 9), anchor="w"
        )
        actions = tk.Frame(content, bg="#ffffff")
        actions.pack(pady=(16, 0), anchor="center")

        def close_dialog():
            if not busy["value"]:
                popup.destroy()

        def set_busy(active):
            busy["value"] = active
            self._model_rebuild_running = active
            rebuild_button.configure(state=tk.DISABLED if active else tk.NORMAL)
            cancel_button.configure(state=tk.DISABLED if active else tk.NORMAL)
            for radio in choices.winfo_children():
                radio.configure(state=tk.DISABLED if active else tk.NORMAL)
            if active:
                status.configure(text="Rebuilding Core, Voronoi and Support...")
                status.pack(fill="x", before=actions, pady=(14, 0))
                indicator.pack(fill="x", before=actions, pady=(8, 0))
                indicator.start(12)
            else:
                indicator.stop()
                indicator.pack_forget()
                status.pack_forget()

        def poll_result():
            if not popup.winfo_exists():
                return
            if not completed.is_set():
                popup.after(60, poll_result)
                return

            rebuilt, error = outcome["rebuilt"], outcome["error"]
            if error is not None:
                set_busy(False)
                self.custom_warning("Model Conversion Not Applied", str(error), parent=popup)
                return

            # Background work is finished. Drop its global busy flag before
            # _apply_model_color_space checks for *other* active jobs. Tk owns
            # the commit so there is no concurrent UI mutation at this point.
            self._model_rebuild_running = False
            status.configure(text="Updating workspace...")
            try:
                if self._apply_model_color_space(choice.get(), prepared_space=rebuilt):
                    popup.destroy()
                else:
                    set_busy(False)
            except (ValueError, TypeError, RuntimeError, tk.TclError) as exc:
                set_busy(False)
                self.custom_warning("Model Conversion Not Applied", str(exc), parent=popup)

        def confirm():
            if busy["value"]:
                return
            chosen = choice.get()
            if chosen == current.color_space:
                popup.destroy()
                return
            try:
                if self._has_any_active_job():
                    raise ValueError("Finish or cancel the active mapping first.")
                if not self._commit_pending_data_label_changes():
                    return
                if self._has_pending_model_data_edits():
                    raise ValueError("Apply pending Data changes before rebuilding the model.")
            except (ValueError, TypeError, RuntimeError, tk.TclError) as exc:
                self.custom_warning("Model Conversion Not Applied", str(exc), parent=popup)
                return

            set_busy(True)

            def prepare_geometry():
                try:
                    outcome["rebuilt"] = rebuild_in_color_space(current, chosen)
                except Exception as exc:
                    outcome["error"] = exc
                finally:
                    # Event publication makes the result visible to Tk; the
                    # worker never touches any widget.
                    completed.set()

            threading.Thread(target=prepare_geometry, daemon=True).start()
            popup.after(60, poll_result)

        rebuild_button = tk.Button(
            actions, text="Rebuild Geometry", command=confirm,
            bg=UtilsTools.UI_ACCENT, fg="white",
            activebackground=UtilsTools.UI_ACCENT_DARK,
            activeforeground="white", font=("Segoe UI", 9, "bold"),
            bd=0, relief="flat", padx=16, pady=7, cursor="hand2"
        )
        rebuild_button.pack(side="left", padx=5)
        cancel_button = tk.Button(
            actions, text="Cancel", command=close_dialog,
            bg="#f2f3f5", fg="#242633", activebackground="#e7e8eb",
            font=("Segoe UI", 9), bd=0, relief="flat",
            padx=18, pady=7, cursor="hand2"
        )
        cancel_button.pack(side="left", padx=5)

        popup.protocol("WM_DELETE_WINDOW", close_dialog)
        popup.bind("<Escape>", lambda _event: close_dialog())
        self.center_popup(popup, 470, 390)
        popup.deiconify()
        popup.grab_set()
        popup.focus_set()

    def on_option_select(self):
        """
        Refresh the embedded 3D model using the current visualization options.

        The matplotlib figure is reused instead of recreated on every update.
        """
        if not self.COLOR_SPACE:
            return

        self._init_3d_canvas()
        self.filtered_points = {}

        selected_options = [
            key for key, var in self.model_3d_options.items()
            if var.get()
        ]

        # Keep the color controls visible and synchronized.
        self.display_color_buttons(self.color_matrix)

        if not selected_options:
            self.ax_3d.cla()
            self.graph_widget.draw()

            if hasattr(self, "lab_value_frame"):
                self.lab_value_frame.lift()
            return

        space = getattr(self,"fuzzy_color_space",None)
        plot_hex = self.hex_color
        plot_centroids = self.selected_centroids
        if space and space.color_space == "RGB":
            plot_hex = {h:space.model_from_lab(lab) for h,lab in self.hex_color.items()}
            plot_centroids = {k:{**v,"positive_prototype":space.model_from_lab(
                v.get("positive_prototype",v.get("Color")))} for k,v in self.selected_centroids.items()}
        if isinstance(space, GranularFuzzyColorSpace):
            plot_centroids, plot_hex = self._granular_visualization_data()
        previous_view = (self._model_3d_view_snapshot(self.ax_3d)
                         if self._model_3d_initial_view is not None else None)
        VisualManager.plot_combined_3D(
            self.ax_3d, self.file_base_name, plot_centroids,
            self.selected_core, self.selected_alpha, self.selected_support,
            self.volume_limits, plot_hex, selected_options, self.filtered_points,
            color_space=space.color_space if space else "LAB",
            display_color_space=space.color_space if space else "LAB",
        )

        # Independent title and subtitle; avoid using the same large bold
        # font for the space name and its typology. Keep the button separate.
        display_name = str(self.file_base_name).replace("_", " ")
        space = getattr(self, "fuzzy_color_space", None)
        self.ax_3d.set_title(
            display_name,
            fontsize=11,
            color="#242633",
            fontweight="semibold",
            pad=20,
            loc="center",
        )
        if space:
            subtitle = f"{space.typology_description}  ·  {space.color_space}"
            self.ax_3d.text2D(
                0.5, 1.017, subtitle,
                transform=self.ax_3d.transAxes,
                fontsize=7.4,
                fontweight="normal",
                color=UtilsTools.UI_ACCENT_MUTED,
                ha="center", va="bottom",
            )

        # Keep the right-hand z-axis title inside the figure with a 168px
        # selector on the other side of the sash. No labels are cropped.
        if self.Canvas1.winfo_width() < 555:
            self.ax_3d.set_position([0.02, 0.10, 0.80, 0.79])
            self.ax_3d.zaxis.labelpad = 3
        else:
            self.ax_3d.set_position([0.08, 0.10, 0.83, 0.79])

        if self._model_3d_initial_view is None:
            self._model_3d_initial_view = self._model_3d_view_snapshot(self.ax_3d)
        elif previous_view is not None:
            self._apply_model_3d_view(self.ax_3d, previous_view)
        self.graph_widget.draw()
        action_host = getattr(self, "_model_3d_action_host", None)
        if action_host is not None and action_host.winfo_exists():
            action_host.lift()

        if hasattr(self, "lab_value_frame"):
            self.lab_value_frame.lift()


    def _clear_model_3d_plot(self):
        """
        Remove the current 3D plot widget content.
        """
        if self.graph_widget:
            try:
                self.graph_widget.get_tk_widget().destroy()
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
        space = getattr(self,"fuzzy_color_space",None)
        plot_hex = self.hex_color
        plot_centroids = self.selected_centroids
        if space and space.color_space == "RGB":
            plot_hex = {h:space.model_from_lab(lab) for h,lab in self.hex_color.items()}
            plot_centroids = {k:{**v,"positive_prototype":space.model_from_lab(
                v.get("positive_prototype",v.get("Color")))} for k,v in self.selected_centroids.items()}
        if isinstance(space, GranularFuzzyColorSpace):
            plot_centroids, plot_hex = self._granular_visualization_data()
        granular_categories = (
            {p.label: cat.label for cat in space.categories for p in cat.prototypes}
            if isinstance(space, GranularFuzzyColorSpace) else None
        )
        fig = VisualManager.plot_more_combined_3D(
            filename=self.file_base_name,
            color_data=plot_centroids,
            core=self.selected_core,
            alpha=self.selected_alpha,
            support=self.selected_support,
            volume_limits=self.volume_limits,
            hex_color=plot_hex,
            selected_options=selected_options,
            filtered_points=self.filtered_points,
            color_space=space.color_space if space else "LAB",
            display_color_space=space.color_space if space else "LAB",
            granule_categories=granular_categories,
        )

        if hasattr(self, "lab_value_frame"):
            self.lab_value_frame.lift()

        self._open_plotly_figure_in_browser(
            fig,
            filename_prefix="pyfcs_3d_plot"
        )


    def select_all_color(self):
        """Show every atomic prototype or every real granule."""
        if not self.COLOR_SPACE:
            return
        for var in getattr(self, "selected_colors", {}).values():
            var.set(True)
        for var in (getattr(self, "selected_granules", None) or {}).values():
            var.set(True)
        self.select_color()

    def deselect_all_color(self):
        """Hide all model objects, preserving the category/granule layout."""
        if not self.COLOR_SPACE:
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
        enabled = bool(category_var.get())
        groups = getattr(self, "_model_3d_color_groups", {})
        for name in groups.get(category_label, (category_label,)):
            granule_var = (getattr(self, "selected_granules", None) or {}).get(name)
            if granule_var is not None:
                granule_var.set(enabled)
        self.select_color()

    def _toggle_model_3d_granule(self, _granule_label):
        """Keep parent categories in sync when a granule is toggled."""
        self.select_color()

    def _sync_model_3d_category_counts(self):
        """Synchronize one-granule and multi-granule categories identically."""
        groups = getattr(self, "_model_3d_color_groups", {})
        state = getattr(self, "selected_granules", None) or {}
        counters = getattr(self, "_model_3d_category_counts", {})
        for category, names in groups.items():
            enabled = sum(bool(state.get(name) and state[name].get()) for name in names)
            selected = getattr(self, "selected_colors", {}).get(category)
            if selected is not None:
                selected.set(enabled == len(names))
            counter = counters.get(category)
            if counter is not None:
                counter.configure(
                    text=f"{enabled}/{len(names)}" if len(names) > 1 else "",
                    fg=(UtilsTools.UI_ACCENT if 0 < enabled < len(names)
                        else "#6b7280"))

    def select_color(self):
        """Update visible geometric objects; never recompute membership geometry."""
        selected_centroids = {}
        space = getattr(self, "fuzzy_color_space", None)
        if isinstance(space, GranularFuzzyColorSpace):
            self._sync_model_3d_category_counts()
            active_granules = self._selected_model_granules()
            selected_centroids = {
                cat.label: self.color_data[cat.label]
                for cat in space.categories if cat.label in self.color_data
                and any(proto.label in active_granules for proto in cat.prototypes)
            }
            self.selected_centroids = selected_centroids
            self.selected_alpha, self.selected_core, self.selected_support = (
                self._geometry_for_categories(selected_centroids, active_granules))
            self.selected_hex_color = {
                UtilsTools.lab_to_hex(space.lab_from_model(proto.positive)):
                    space.lab_from_model(proto.positive)
                for cat in space.categories for proto in cat.prototypes
                if proto.label in active_granules
            }
        else:
            self._sync_model_3d_category_counts()
            selected_centroids = {
                color: self.color_data[color]
                for color, var in getattr(self, "selected_colors", {}).items()
                if var.get() and color in self.color_data
            }
            self.selected_centroids = selected_centroids
            selected_labs = {
                tuple(np.asarray(row["positive_prototype"]).reshape(-1))
                for row in selected_centroids.values()
            }
            self.selected_hex_color = {
                key: value for key, value in self.hex_color.items()
                if tuple(np.asarray(value).reshape(-1)) in selected_labs
            }
            self.selected_alpha, self.selected_core, self.selected_support = (
                self._geometry_for_categories(selected_centroids))
        self.on_option_select()

    def _activate_model_3d_category_row(self, category_label, expandable):
        """Handle clicks on row contents, leaving the checkbox independent.

        A multi-granule row expands/collapses; a single-granule (or atomic)
        row toggles the representative's visibility instead of creating an
        unnecessary disclosure level.
        """
        if expandable:
            self._toggle_model_3d_expanded(category_label)
            return
        selected = getattr(self, "selected_colors", {}).get(category_label)
        if selected is None:
            return
        selected.set(not bool(selected.get()))
        self._toggle_model_3d_category(category_label)


    def _toggle_model_3d_expanded(self, label):
        expanded = getattr(self, "_model_3d_expanded_categories", set())
        if label in expanded:
            expanded.remove(label)
        else:
            expanded.add(label)
        self._model_3d_expanded_categories = expanded
        self._filter_model_3d_colors()

    def _filter_model_3d_colors(self):
        """Filter the sidebar without changing the geometry or original row order."""
        rows = getattr(self, "_model_3d_category_rows", None)
        if not rows:
            return
        query_var = getattr(self, "_model_3d_search_var", None)
        query = str(query_var.get()).strip().casefold() if query_var else ""
        expanded = getattr(self, "_model_3d_expanded_categories", set())
        # Repacking only these small sidebar rows keeps the source order stable
        # when the search is cleared, without rebuilding controls or variables.
        for entry in rows.values():
            entry["row"].pack_forget()
            entry["children"].pack_forget()
            for child in entry["child_rows"].values():
                child.pack_forget()
        for label, entry in rows.items():
            matches_parent = query in label.casefold()
            matching = [name for name in entry["names"]
                        if query in name.casefold()]
            if query and not (matches_parent or matching):
                continue
            entry["row"].pack(fill="x", anchor="w", padx=2, pady=2)
            show_children = bool(entry["names"]) and (
                label in expanded or bool(query and not matches_parent))
            if show_children:
                entry["children"].pack(fill="x", padx=(15, 0), pady=(0, 2))
                for name, child in entry["child_rows"].items():
                    if not query or matches_parent or name in matching:
                        child.pack(fill="x", anchor="w")
            arrow = entry.get("arrow")
            if arrow is not None:
                arrow.configure(text="▾" if show_children else "▸")
        try:
            self.scrollable_canvas.configure(
                scrollregion=self.scrollable_canvas.bbox("all"))
        except tk.TclError:
            pass

    def display_color_buttons(self, colors):
        """Unified compact selector for atomic and granular color spaces.

        Every category has at least one real color, including legacy atomic
        colors and JSON granular categories with a single granule. Only groups
        containing more than one granule receive a disclosure control.
        """
        space = getattr(self, "fuzzy_color_space", None)
        granular = isinstance(space, GranularFuzzyColorSpace)
        category_objects = ({cat.label: cat for cat in space.categories}
                            if granular else {})
        groups = ({label: tuple(p.label for p in category_objects[label].prototypes)
                   for label in colors} if granular else
                  {label: (label,) for label in colors})
        signature = (id(space), tuple(colors), tuple(groups.items()))
        if signature == getattr(self, "_last_color_button_signature", None):
            return

        old_categories = {k: bool(v.get()) for k, v in
                          getattr(self, "selected_colors", {}).items()}
        old_granules = getattr(self, "selected_granules", None)
        old_granules = ({k: bool(v.get()) for k, v in old_granules.items()}
                        if isinstance(old_granules, dict) else {})
        old_rows = getattr(self, "_model_3d_rows_container", None)
        if old_rows is not None:
            old_rows.destroy()
        self.selected_colors = {}
        self.selected_granules = {}
        self._model_3d_color_groups = groups
        self._model_3d_category_counts = {}
        self._model_3d_category_rows = {}
        self.color_buttons = []
        rows_holder = tk.Frame(self.inner_frame, bg="#ffffff")
        rows_holder.pack(fill="x", padx=2)
        self._model_3d_rows_container = rows_holder

        def color_hex(category, name):
            try:
                if granular:
                    cat = category_objects[category]
                    proto = next(p for p in cat.prototypes if p.label == name)
                    lab = space.lab_from_model(proto.positive)
                else:
                    lab = self.color_data[category]["positive_prototype"]
                return UtilsTools.lab_to_hex(lab)
            except (KeyError, IndexError, ValueError, StopIteration, TypeError):
                return "#b8bec8"

        def add_swatch(parent, palette, size=12):
            """Borderless miniature with up to three equally sized color bands."""
            thumbnail = tk.Canvas(parent, bg="#ffffff", width=size, height=size,
                                  highlightthickness=0, bd=0, relief="flat")
            thumbnail.pack(side="left", padx=(1, 4))
            colors_to_draw = palette[:3] or ("#b8bec8",)
            for i, hx in enumerate(colors_to_draw):
                thumbnail.create_rectangle(
                    i * size / len(colors_to_draw), 0,
                    (i + 1) * size / len(colors_to_draw), size,
                    fill=hx, outline="", width=0)
            return thumbnail

        for category in colors:
            names = groups.get(category, (category,))
            enabled = old_categories.get(category, True)
            self.selected_colors[category] = tk.BooleanVar(value=enabled)
            for name in names:
                self.selected_granules[name] = tk.BooleanVar(
                    value=old_granules.get(name, enabled))
            row = tk.Frame(rows_holder, bg="#ffffff")
            row.pack(fill="x", anchor="w", padx=1, pady=2)
            category_checkbox = tk.Checkbutton(
                row, variable=self.selected_colors[category],
                bg="#ffffff", activebackground="#ffffff",
                selectcolor="#ffffff", onvalue=True, offvalue=False,
                cursor="hand2", highlightthickness=0, bd=0, padx=0,
                command=lambda cat=category: self._toggle_model_3d_category(cat),
            )
            category_checkbox.pack(side="left")
            category_swatch = add_swatch(
                row, [color_hex(category, name) for name in names])
            label = tk.Label(
                row, text=category, bg="#ffffff", fg="#1f2937",
                font=("Segoe UI", 8), anchor="w", wraplength=83,
                cursor="hand2", justify="left")
            label.pack(side="left", fill="x", expand=True)
            # Tk bindings do not bubble from children to their Frame. Bind
            # the swatch/text/count separately, and leave the checkbox's
            # native control and disclosure button to their own commands.
            expand = len(names) > 1
            click = lambda _event, cat=category, can_expand=expand: (
                self._activate_model_3d_category_row(cat, can_expand))
            for widget in (row, category_swatch, label):
                widget.bind("<Button-1>", click)
            count = None
            arrow = None
            child_rows = {}
            child_holder = tk.Frame(rows_holder, bg="#ffffff")
            if len(names) > 1:
                count = tk.Label(row, text=f"{len(names)}/{len(names)}",
                                 bg="#ffffff", fg="#6b7280",
                                 font=("Segoe UI", 7), padx=0)
                count.pack(side="right")
                count.configure(cursor="hand2")
                count.bind("<Button-1>", click)
                arrow = tk.Button(
                    row, text="▸", bg="#ffffff", fg=UtilsTools.UI_ACCENT,
                    activebackground="#ffffff", relief="flat", bd=0,
                    font=("Segoe UI", 9, "bold"), padx=0, cursor="hand2",
                    command=lambda cat=category: self._toggle_model_3d_expanded(cat))
                arrow.pack(side="right")
                for name in names:
                    child_row = tk.Frame(child_holder, bg="#ffffff")
                    child_rows[name] = child_row
                    tk.Checkbutton(
                        child_row, variable=self.selected_granules[name],
                        bg="#ffffff", selectcolor="#ffffff",
                        activebackground="#ffffff", highlightthickness=0,
                        bd=0, padx=0, cursor="hand2",
                        command=lambda n=name: self._toggle_model_3d_granule(n),
                    ).pack(side="left")
                    child_swatch = add_swatch(
                        child_row, [color_hex(category, name)], size=10)
                    child_name = tk.Label(
                        child_row, text=name, bg="#ffffff", fg="#4b5563",
                        font=("Segoe UI", 8), anchor="w", wraplength=82,
                        justify="left", cursor="hand2")
                    child_name.pack(side="left", fill="x", expand=True)
                    def select_child(_event, granule=name):
                        state = self.selected_granules.get(granule)
                        if state is None:
                            return
                        state.set(not state.get())
                        self._toggle_model_3d_granule(granule)
                    for widget in (child_row, child_swatch, child_name):
                        widget.bind("<Button-1>", select_child)
                self._model_3d_category_counts[category] = count
            self.color_buttons.append(row)
            self._model_3d_category_rows[category] = {
                "row": row, "children": child_holder,
                "names": names if len(names) > 1 else (),
                "arrow": arrow, "child_rows": child_rows,
            }
        self._sync_model_3d_category_counts()
        self._filter_model_3d_colors()
        self._last_color_button_signature = signature


    # ============================================================================================================================================================
    #  FUNCTIONS DATA
    # ============================================================================================================================================================
    def display_data_window(self):
        """Read-only, granular-aware Data table (owned by DataManager)."""
        DataManager.render_data(self)


    def open_modify_fcs(self):
        """Edit a private draft; the loaded model is committed after JSON save."""
        if not getattr(self, "COLOR_SPACE", False) or getattr(self, "fuzzy_color_space", None) is None:
            self.custom_warning("Edit Fuzzy Color Space", "Load a Fuzzy Color Space first.")
            return
        if self._has_any_active_job():
            self.custom_warning("Process Running", "Finish or cancel the active process first.")
            return
        previous = getattr(self, "_modify_fcs_dialog", None)
        if previous is not None:
            try:
                if previous.win.winfo_exists():
                    previous.win.lift()
                    previous.win.focus_force()
                    return
            except tk.TclError:
                pass
        try:
            self._modify_fcs_dialog = DataManager.ModifyFCSDialog(self)
        except (ValueError, RuntimeError, tk.TclError) as exc:
            self.custom_warning("Edit Fuzzy Color Space", str(exc))


    def remove_color(self, index):
        """Remove a color from the editable dataset and refresh the display."""
        if len(self.edit_color_data) <= 2:
            self.custom_warning(
                "Cannot Remove Color",
                "At least two colors must remain. The color was not removed.",
                parent=getattr(self, "root", None)
            )
            return

        color_name = self.color_matrix[index]

        if color_name in self.edit_color_data:
            # The optimized Voronoi engine derives competitors directly from
            # the complete positive-prototype matrix, so removing a color no
            # longer requires updating N redundant negative lists.
            del self.edit_color_data[color_name]

        self.display_data_window()


    def addColor_data_window(self):
        """
        Add a new color to the editable dataset and update the display.

        Uses the reusable custom color dialog, allowing RGB, LAB, HEX,
        and visual Pick Color selection.
        """
        if not self.COLOR_SPACE:
            return

        import copy

        parent = self._get_valid_dialog_parent(
            getattr(self, "_data_window", None)
            or getattr(self, "data_window", None)
            or self.root
        )

        new_color_data = copy.deepcopy(self.edit_color_data)

        def on_submit(color_name, sample_lab, sample_rgb, sample_hex, dialog, input_vars):
            clean_name = str(color_name).strip()

            if not clean_name:
                input_vars["status_var"].set("Enter a color name.")
                self.custom_warning(
                    "Invalid Color Name",
                    "Enter a color name.",
                    parent=dialog
                )
                return

            if clean_name in new_color_data:
                input_vars["status_var"].set("A color with this name already exists.")
                self.custom_warning(
                    "Duplicated Color Name",
                    f"The color '{clean_name}' already exists in the current color space.",
                    parent=dialog
                )
                return

            try:
                L, A, B = sample_lab
                L = float(L)
                A = float(A)
                B = float(B)
            except Exception:
                input_vars["status_var"].set("Invalid LAB color values.")
                self.custom_warning(
                    "Invalid LAB Values",
                    "The selected color could not be converted to valid LAB values.",
                    parent=dialog
                )
                return

            positive_prototype = np.array([L, A, B], dtype=float)

            if not UtilsTools.is_valid_lab(positive_prototype):
                input_vars["status_var"].set("LAB values are outside the valid domain.")
                self.custom_warning(
                    "Invalid LAB Values",
                    "LAB values must be within L [0,100], a [-128,128], b [-128,128].",
                    parent=dialog
                )
                return

            duplicate_name = UtilsTools.find_duplicate_lab_name(
                new_color_data,
                positive_prototype,
            )
            if duplicate_name is not None:
                input_vars["status_var"].set("A color with the same LAB prototype already exists.")
                self.custom_warning(
                    "Duplicated LAB Prototype",
                    f"The color '{duplicate_name}' already uses the same LAB prototype. "
                    "Voronoi prototypes must be unique.",
                    parent=dialog
                )
                return

            new_color_data[clean_name] = {
                "Color": [L, A, B],
                "positive_prototype": positive_prototype,
            }

            self.edit_color_data = new_color_data

            dialog.destroy()
            self.display_data_window()

        self._open_custom_color_dialog(
            parent=parent,
            title="Add New Color",
            subtitle="Add a color to the editable color space",
            submit_text="Add Color",
            require_name=True,
            default_name="New Color",
            on_submit=on_submit
        )


    def clear_data_window(self):
        """Clear the data display area and reset related UI/state."""
        if hasattr(self, "_data_info_tooltip") and self._data_info_tooltip is not None:
            try:
                self._data_info_tooltip.destroy()
            except Exception:
                pass
            self._data_info_tooltip = None

        if hasattr(self, "data_window"):
            for child in self.data_window.winfo_children():
                child.destroy()
            self.data_window.delete("all")
            self.data_window.configure(scrollregion=(0, 0, 0, 0))
            try:
                self.data_window.config(cursor="")
            except Exception:
                pass

        if hasattr(self, "file_name_entry"):
            try:
                self.file_name_entry.configure(state="normal")
                self.file_name_entry.delete(0, tk.END)
                self.file_name_entry.configure(state="readonly")
            except tk.TclError:
                pass

        if hasattr(self, "data_header_title"):
            self.data_header_title.config(text="No Fuzzy Color Space Loaded")
        self._update_data_model_summary()

        self.file_base_name = ""
        self.color_matrix = []
        self.hex_color = {}

        self._data_name_source = None
        self._data_expanded_categories = set()
        self._data_scroll_width = 0
        self._data_table_center_x = 0
        self._data_label_editors = []


    def _commit_pending_data_label_changes(self):
        """
        Commit all visible label edits before saving.

        The Apply Changes button may run before Tkinter processes the
        Entry FocusOut event. Reading the StringVar objects directly
        guarantees that the latest text is included in the saved data.
        """
        editors = getattr(self, "_data_label_editors", [])
        current_data = getattr(self, "edit_color_data", {})

        if not editors or not current_data:
            return True

        max_label_chars = 24
        rename_map = {}

        # Read every visible Entry before modifying edit_color_data.
        for editor in editors:
            old_name = str(editor.get("old_name", "")).strip()
            variable = editor.get("variable")

            if variable is None or old_name not in current_data:
                continue

            new_name = str(variable.get()).strip()

            if len(new_name) > max_label_chars:
                new_name = new_name[:max_label_chars]
                variable.set(new_name)

            if not new_name:
                variable.set(old_name[:max_label_chars])

                self.custom_warning(
                    "Invalid Color Name",
                    "Color name cannot be empty.",
                    parent=getattr(self, "root", None)
                )
                return False

            rename_map[old_name] = new_name

        # Validate the complete resulting list. This also supports several
        # labels being edited before Apply Changes is pressed.
        final_names = []

        for old_name in current_data.keys():
            final_name = rename_map.get(old_name, old_name)

            if final_name in final_names:
                self.custom_warning(
                    "Duplicated Color Name",
                    f"The color '{final_name}' already exists.",
                    parent=getattr(self, "root", None)
                )
                return False

            final_names.append(final_name)

        if all(old_name == rename_map.get(old_name, old_name)
               for old_name in current_data.keys()):
            return True

        # Rebuild the dictionary while preserving row order.
        renamed_data = {}

        for old_name, value in current_data.items():
            new_name = rename_map.get(old_name, old_name)
            renamed_data[new_name] = value

        self.edit_color_data = renamed_data
        self.color_matrix = list(renamed_data.keys())

        # Keep related selection/edit references coherent.
        selected_name = getattr(self, "selected_color_name", None)
        if selected_name in rename_map:
            self.selected_color_name = rename_map[selected_name]

        current_edit_name = getattr(self, "current_color_to_edit", None)
        if current_edit_name in rename_map:
            self.current_color_to_edit = rename_map[current_edit_name]

        # Keep callback state synchronized in case FocusOut is processed
        # after the Apply Changes command.
        for editor in editors:
            old_name = str(editor.get("old_name", "")).strip()
            if old_name in rename_map:
                editor["old_name"] = rename_map[old_name]

        return True


    def apply_changes(self):
        """Apply the pending changes made to the editable color list."""
        if not self.COLOR_SPACE:
            self.custom_warning(
                "Error",
                "No Color Space has been loaded.",
                parent=getattr(self, "root", None)
            )
            return

        if self._has_any_active_job():
            self.custom_warning(
                "Process Running",
                "There is a process currently running. Please wait for it to finish or cancel it before applying changes.",
                parent=getattr(self, "root", None)
            )
            return

        # Commit the current Entry text immediately, even when the user
        # presses Apply Changes before the FocusOut event is processed.
        if not self._commit_pending_data_label_changes():
            return

        try:
            output_name = self.file_name_entry.get().strip()

            if not output_name:
                self.custom_warning(
                    "Error",
                    "Please enter a valid file name.",
                    parent=getattr(self, "root", None)
                )
                return

            if not getattr(self, "edit_color_data", None):
                self.custom_warning(
                    "Error",
                    "There are no colors to save.",
                    parent=getattr(self, "root", None)
                )
                return

            if len(self.edit_color_data) < 2:
                self.custom_warning(
                    "Error",
                    "At least two colors are required to save a color space.",
                    parent=getattr(self, "root", None)
                )
                return

            new_color_data = copy.deepcopy(self.edit_color_data)

            color_dict = {}

            for key, value in new_color_data.items():
                if "positive_prototype" in value:
                    color_dict[key] = value["positive_prototype"]
                elif "Color" in value:
                    color_dict[key] = np.array(value["Color"])
                else:
                    raise ValueError(f"Color '{key}' does not contain valid LAB data.")

            has_pending = bool(getattr(self, "_pending_granules", None))
            active = getattr(self, "fuzzy_color_space", None)
            if isinstance(active, GranularFuzzyColorSpace) or has_pending:
                options = self._granular_save_options(new_color_data)
            else:
                options = self._options_from_loaded_space(
                    active, new_color_data=new_color_data
                )

            # The active name is updated only after the save operation succeeds.
            self.save_json(
                output_name, new_color_data, color_dict=color_dict,
                apply_after_save=True, options=options
            )

        except Exception as e:
            self.custom_warning(
                "Error",
                f"Changes could not be prepared: {e}",
                parent=getattr(self, "root", None)
            )


    def delete_color_space(self):
        """Delete the currently loaded color space file (.json, .fcs or .cns) and clear the app state."""
        if not self.COLOR_SPACE:
            self.custom_warning(
                "Error",
                "No Color Space has been loaded.",
                parent=getattr(self, "root", None)
            )
            return

        if self._has_any_active_job():
            self.custom_warning(
                "Process Running",
                "There is a process currently running. Please wait for it to finish or cancel it before deleting the Color Space.",
                parent=getattr(self, "root", None)
            )
            return

        if getattr(self, "_model_space_unsaved", False):
            if not messagebox.askyesno(
                "Unsaved Model Color Space",
                "The reconstructed model has not been saved.\n\n"
                "Continue deleting the original file?",
                parent=self.root,
            ):
                return
        file_path = getattr(self, "file_path", None)
        file_name = os.path.basename(file_path) if file_path else "current color space"

        confirm = messagebox.askyesno(
            "Delete Color Space",
            f"Are you sure you want to permanently delete:\n\n{file_name}\n\nThis action cannot be undone.",
            parent=getattr(self, "root", None)
        )

        if not confirm:
            return

        editor = getattr(self, "_modify_fcs_dialog", None)
        if editor is not None:
            editor.close()
        self._reset_image_inspection_state()

        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)

            self.COLOR_SPACE = False
            self._model_space_unsaved = False
            self.color_data = {}
            self.edit_color_data = {}
            self._update_model_space_indicator()
            self.file_path = None
            self.file_base_name = ""

            if hasattr(self, "selected_color_name"):
                self.selected_color_name = None

            if hasattr(self, "selected_color_index"):
                self.selected_color_index = None

            if hasattr(self, "current_color_to_edit"):
                self.current_color_to_edit = None

            if hasattr(self, "_data_info_tooltip") and self._data_info_tooltip is not None:
                try:
                    self._data_info_tooltip.destroy()
                except Exception:
                    pass
                self._data_info_tooltip = None

            self.clear_data_window()

            # Clear the Model 3D view and all cached 3D state.
            self._reset_3d_canvas()
            self._reset_3d_view_state()

            self.update_volumes()

            messagebox.showinfo(
                "Deleted",
                f"{file_name} was deleted successfully.",
                parent=getattr(self, "root", None)
            )

        except Exception as e:
            self.custom_warning(
                "Error",
                f"The Color Space could not be deleted: {e}",
                parent=getattr(self, "root", None)
            )


    def _center_data_horizontal_scroll(self):
        """Center the Data table horizontally inside its canvas."""
        if not hasattr(self, "data_window"):
            return

        try:
            self.data_window.update_idletasks()

            visible_width = float(self.data_window.winfo_width())
            scroll_width = float(
                getattr(self, "_data_scroll_width", visible_width)
            )
            table_center = float(
                getattr(self, "_data_table_center_x", visible_width / 2)
            )

            if scroll_width <= visible_width or scroll_width <= 0:
                self.data_window.xview_moveto(0.0)
                return

            # Position the viewport so that the table center is in the
            # center of the visible canvas.
            desired_left = table_center - visible_width / 2
            maximum_left = scroll_width - visible_width

            desired_left = max(0.0, min(desired_left, maximum_left))

            self.data_window.xview_moveto(desired_left / scroll_width)

        except Exception:
            pass
























    # ============================================================================================================================================================
    #  FUNCTIONS IMAGE DISPLAY
    # ============================================================================================================================================================
    def save_image(self, window_id=None):
        """
        Save the currently displayed image.

        Parameters
        ----------
        window_id : str or None
            When provided (for example from an image card's context menu), save
            that image directly. When omitted, keep the toolbar/menu behavior
            and ask the user which open image should be saved.

        If the target is a Color Mapping All result, a standalone legend image
        is saved beside it using the palette currently displayed.
        """
        if not hasattr(self, "load_images_names") or not self.load_images_names:
            self.custom_warning(message="There are currently no images available to save.")
            return

        if self._has_any_active_job():
            self.custom_warning(
                "Process Running",
                "Finish or cancel the current color mapping process before saving an image."
            )
            return

        def _build_legend_pil(labels, colors, box_size=28, padding=10, row_gap=6):
            """Build a standalone legend image from labels and RGB uint8 colors."""
            font = ImageFont.load_default()
            max_text_w = 0
            for lbl in labels:
                lbl = str(lbl)
                try:
                    bbox = font.getbbox(lbl)
                    max_text_w = max(max_text_w, bbox[2] - bbox[0])
                except Exception:
                    max_text_w = max(max_text_w, len(lbl) * 7)

            width = padding * 2 + box_size + 10 + max_text_w
            height = padding * 2 + len(labels) * (box_size + row_gap) - row_gap
            legend = Image.new("RGB", (max(1, width), max(1, height)), "white")
            draw = ImageDraw.Draw(legend)
            y = padding

            for lbl, col in zip(labels, colors):
                try:
                    r, g, b = int(col[0]), int(col[1]), int(col[2])
                except Exception:
                    r, g, b = 0, 0, 0

                draw.rectangle(
                    [padding, y, padding + box_size, y + box_size],
                    fill=(r, g, b), outline=(0, 0, 0)
                )
                draw.text(
                    (padding + box_size + 10, y + 7),
                    str(lbl), fill="black", font=font
                )
                y += box_size + row_gap

            return legend

        def _get_mapping_all_legend_data(target_window_id):
            """Return the labels and palette that are actually visible now."""
            if getattr(self, "window_mapping_mode", {}).get(target_window_id) != "all":
                return None, None

            # Export ALL assigned categories/granules, even when the compact
            # on-screen category group is collapsed or scrolled out of view.
            pack = getattr(self, "_mapping_all_pack_by_window", {}).get(target_window_id)
            if pack and "level_palettes" in pack:
                level = pack.get("level", "categories")
                scheme = pack.get("scheme", "original")
                palette = np.asarray(pack["level_palettes"][level][scheme], dtype=np.uint8)
                if level == "categories":
                    labels = [str(p.label) for p in self.prototypes]
                elif getattr(self.fuzzy_color_space, "is_granular", False):
                    labels = [
                        (f"{cat.label} / {p.label}" if len(cat.prototypes) > 1
                         else str(cat.label))
                        for cat in self.fuzzy_color_space.categories
                        for p in cat.prototypes
                    ]
                else:
                    labels = [str(p.label) for p in self.prototypes]
                colors = palette[:len(labels)]
                alpha_values = pack.get("alpha_values")
                unassigned = pack.get("label_map")
                if unassigned is not None and alpha_values is not None:
                    uncovered = (np.asarray(unassigned) < 0) & (np.asarray(alpha_values) > 0)
                    if np.any(uncovered):
                        labels.append("Unassigned (original)")
                        colors = np.vstack([colors, np.asarray([220, 220, 220], dtype=np.uint8)])
                return labels, colors

            # Legacy fallback for a mapping result created before the current
            # per-window pack existed or locked to an older color space.
            panel_info = getattr(self, "proto_options", {}).get(target_window_id)
            if isinstance(panel_info, dict) and panel_info.get("kind") == "all":
                rows = list(panel_info.get("rows", []) or [])
                if rows:
                    labels = []
                    colors = []
                    for row in rows:
                        if isinstance(row, dict):
                            if row.get("type") == "group":
                                continue
                            label = row.get("export_name", row.get("name", ""))
                            rgb = row.get("rgb", (0, 0, 0))
                        else:
                            prototype, rgb = row
                            label = getattr(prototype, "label", prototype)
                        labels.append(str(label))
                        try:
                            rgb_values = np.asarray(rgb, dtype=np.uint8).reshape(-1)[:3]
                            if rgb_values.size != 3:
                                raise ValueError("Invalid RGB legend color")
                            colors.append(tuple(int(v) for v in rgb_values))
                        except Exception:
                            colors.append((0, 0, 0))
                    return labels, np.asarray(colors, dtype=np.uint8)

            labels = [p.label for p in getattr(self, "prototypes", []) or []]
            if not labels:
                return None, None

            # Fall back to the last palette stored for this window.
            palette = getattr(self, "_mapping_all_palette_by_window", {}).get(target_window_id)
            if palette is not None:
                try:
                    palette = np.asarray(palette, dtype=np.uint8)
                    if len(palette) >= len(labels):
                        return labels, palette[:len(labels)]
                except Exception:
                    pass

            # Handle views created before the per-window palette was stored.
            if not hasattr(self, "window_image_key") or target_window_id not in self.window_image_key:
                return None, None

            image_key = self.window_image_key.get(target_window_id)
            color_space_key = getattr(self, "file_path", None)
            cache_pack = getattr(self, "_mapping_all_pack_by_window", {}).get(target_window_id)
            if not cache_pack:
                return None, None

            palettes = cache_pack.get("palettes")
            scheme = cache_pack.get("scheme")
            if not palettes or not scheme or scheme not in palettes:
                return None, None

            return labels, np.asarray(palettes[scheme], dtype=np.uint8)[:len(labels)]

        def _save_window(target_window_id, parent_to_close=None):
            if target_window_id not in self.load_images_names:
                self.custom_warning("Error", "The selected image is no longer open.")
                return

            source_name = os.path.basename(self.load_images_names.get(target_window_id, "image"))
            stem = os.path.splitext(source_name)[0] or "image"
            save_path = filedialog.asksaveasfilename(
                parent=self._get_active_dialog_parent(),
                initialfile=f"{stem}.png",
                defaultextension=".png",
                filetypes=[
                    ("PNG files", "*.png"),
                    ("JPEG files", "*.jpg"),
                    ("All Files", "*.*")
                ]
            )
            if not save_path:
                return

            try:
                # Export the full image mode, not the zoomed viewport shown on the canvas.
                img_to_save = getattr(self, "image_view_source", {}).get(target_window_id)
                if img_to_save is None:
                    img_to_save = getattr(self, "display_pil", {}).get(target_window_id)
                if img_to_save is None:
                    self.custom_warning("Error", "No displayed image available to save for this window.")
                    return
                img_to_save = img_to_save.copy()
                ext = os.path.splitext(save_path)[1].lower()
                if ext in (".jpg", ".jpeg") and img_to_save.mode in ("RGBA", "LA"):
                    img_to_save = img_to_save.convert("RGB")
                img_to_save.save(save_path)

                legend_path = None
                labels, legend_colors = _get_mapping_all_legend_data(target_window_id)
                if labels is not None and legend_colors is not None:
                    legend_img = _build_legend_pil(labels, legend_colors)
                    base, _ext = os.path.splitext(save_path)
                    legend_path = base + "_legend.png"
                    legend_img.save(legend_path)

                if legend_path:
                    messagebox.showinfo(
                        "Success",
                        f"Image saved successfully at:\n{save_path}\n\nLegend saved at:\n{legend_path}",
                        parent=self._get_active_dialog_parent(),
                    )
                elif getattr(self, "window_mapping_mode", {}).get(target_window_id) == "all":
                    messagebox.showinfo(
                        "Success",
                        f"Image saved successfully at:\n{save_path}\n\n"
                        "The Mapping All legend could not be reconstructed for export.",
                        parent=self._get_active_dialog_parent(),
                    )
                else:
                    messagebox.showinfo(
                        "Success",
                        f"Image saved successfully at:\n{save_path}",
                        parent=self._get_active_dialog_parent(),
                    )
            except Exception as exc:
                self.custom_warning("Error", f"Failed to save image:\n{exc}")
            finally:
                if parent_to_close is not None:
                    try:
                        parent_to_close.destroy()
                    except Exception:
                        pass

        # Context-menu path: the image is already known, so do not ask again.
        if window_id is not None:
            _save_window(window_id)
            return

        # Toolbar/main-menu path: use a styled image picker instead of the
        # legacy Listbox popup. This makes it clear which current view will be
        # exported and whether Mapping All will also generate a legend file.
        window_ids = list(self.load_images_names.keys())
        parent = self._get_active_dialog_parent()

        popup = tk.Toplevel(parent)
        popup.withdraw()
        popup.title("Save Image")
        popup.configure(bg="#eeeeee")
        popup.resizable(False, False)
        popup.transient(parent)

        selected_id = {"value": None}
        row_refs = {}
        thumb_refs = []
        # Keep PhotoImage thumbnails alive after save_image() returns.
        popup._thumb_refs = thumb_refs

        outer = tk.Frame(popup, bg="#eeeeee")
        outer.pack(fill="both", expand=True, padx=12, pady=12)

        panel = tk.Frame(outer, bg="white", bd=1, relief="solid")
        panel.pack(fill="both", expand=True)

        header = tk.Frame(panel, bg="#f6f6f6", height=58)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(
            header,
            text="Save Image",
            font=("Sans", 13, "bold"),
            bg="#f6f6f6",
            fg="#222222",
            anchor="w",
            padx=16,
        ).pack(side="left", fill="y")

        tk.Label(
            header,
            text="Choose an open image to export",
            font=("Sans", 9, "italic"),
            bg="#f6f6f6",
            fg="#666666",
            padx=16,
        ).pack(side="right", fill="y")

        body = tk.Frame(panel, bg="white")
        body.pack(fill="both", expand=True, padx=14, pady=(12, 8))

        list_canvas = tk.Canvas(
            body,
            bg="white",
            highlightthickness=0,
            bd=0,
            width=430,
            height=min(300, max(92, len(window_ids) * 78)),
        )
        list_canvas.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(body, orient="vertical", command=list_canvas.yview)
        scrollbar.pack(side="right", fill="y")
        list_canvas.configure(yscrollcommand=scrollbar.set)

        rows_frame = tk.Frame(list_canvas, bg="white")
        rows_window = list_canvas.create_window((0, 0), window=rows_frame, anchor="nw")

        def _mode_text(wid):
            mode = getattr(self, "window_mapping_mode", {}).get(wid)
            if mode == "single":
                return "Color Mapping"
            if mode == "all":
                return "Color Mapping All · legend included"
            return "Original Image"

        def _set_selected(wid):
            if wid not in row_refs:
                return
            selected_id["value"] = wid
            for item_id, refs in row_refs.items():
                chosen = item_id == wid
                refs["frame"].configure(
                    bg="#eef4ff" if chosen else "white",
                    highlightbackground="#6f9ee8" if chosen else "#d9dde3",
                    highlightthickness=1,
                )
                refs["text_frame"].configure(bg="#eef4ff" if chosen else "white")
                refs["name"].configure(bg="#eef4ff" if chosen else "white")
                refs["mode"].configure(bg="#eef4ff" if chosen else "white")
            save_btn.configure(state="normal")

        def _save_selected(_event=None):
            wid = selected_id.get("value")
            if wid is None:
                return
            _save_window(wid, parent_to_close=popup)

        for index, wid in enumerate(window_ids):
            filename = self.load_images_names.get(wid, "image")
            row = tk.Frame(
                rows_frame,
                bg="white",
                bd=0,
                highlightthickness=1,
                highlightbackground="#d9dde3",
                cursor="hand2",
            )
            row.pack(fill="x", padx=1, pady=(0, 7))

            # Thumbnail of exactly the current displayed view.
            pil_thumb = getattr(self, "display_pil", {}).get(wid)
            if pil_thumb is None:
                pil_thumb = getattr(self, "pil_images_original", {}).get(wid)
            if pil_thumb is not None:
                thumb = pil_thumb.convert("RGB").copy()
                thumb.thumbnail((72, 54), Image.Resampling.LANCZOS)
                thumb_bg = Image.new("RGB", (72, 54), "white")
                tx = (72 - thumb.width) // 2
                ty = (54 - thumb.height) // 2
                thumb_bg.paste(thumb, (tx, ty))
                thumb_tk = ImageTk.PhotoImage(thumb_bg)
                thumb_refs.append(thumb_tk)
                thumb_label = tk.Label(row, image=thumb_tk, bg="white", bd=1, relief="solid")
            else:
                thumb_label = tk.Label(row, text="No preview", width=10, height=3, bg="#f5f5f5")
            thumb_label.pack(side="left", padx=8, pady=7)

            text_frame = tk.Frame(row, bg="white")
            text_frame.pack(side="left", fill="both", expand=True, padx=(2, 10), pady=7)

            name_label = tk.Label(
                text_frame,
                text=os.path.basename(filename),
                font=("Sans", 10, "bold"),
                fg="#1f2937",
                bg="white",
                anchor="w",
            )
            name_label.pack(fill="x")

            mode_label = tk.Label(
                text_frame,
                text=_mode_text(wid),
                font=("Sans", 8),
                fg=UtilsTools.UI_ACCENT if getattr(self, "window_mapping_mode", {}).get(wid) else "#6b7280",
                bg="white",
                anchor="w",
            )
            mode_label.pack(fill="x", pady=(4, 0))

            row_refs[wid] = {
                "frame": row,
                "text_frame": text_frame,
                "name": name_label,
                "mode": mode_label,
            }

            for widget in (row, thumb_label, text_frame, name_label, mode_label):
                widget.bind("<Button-1>", lambda _e, w=wid: _set_selected(w))
                widget.bind("<Double-Button-1>", lambda _e, w=wid: (_set_selected(w), _save_selected()))

        rows_frame.update_idletasks()
        list_canvas.configure(scrollregion=list_canvas.bbox("all"))
        list_canvas.itemconfigure(rows_window, width=max(1, list_canvas.winfo_reqwidth()))

        def _sync_rows_width(event):
            try:
                list_canvas.itemconfigure(rows_window, width=max(1, event.width - 2))
            except Exception:
                pass
        list_canvas.bind("<Configure>", _sync_rows_width)

        def _wheel_list(event):
            try:
                px = popup.winfo_pointerx()
                py = popup.winfo_pointery()
                x0 = list_canvas.winfo_rootx()
                y0 = list_canvas.winfo_rooty()
                x1 = x0 + list_canvas.winfo_width()
                y1 = y0 + list_canvas.winfo_height()
                if not (x0 <= px < x1 and y0 <= py < y1):
                    return None

                if getattr(event, "num", None) == 4:
                    step = -1
                elif getattr(event, "num", None) == 5:
                    step = 1
                else:
                    delta = int(getattr(event, "delta", 0) or 0)
                    if delta == 0:
                        return None
                    if platform.system() == "Darwin":
                        step = -1 if delta > 0 else 1
                    else:
                        step = int(-delta / 120)
                        if step == 0:
                            step = -1 if delta > 0 else 1
                list_canvas.yview_scroll(step, "units")
                return "break"
            except Exception:
                return None
        popup.bind("<MouseWheel>", _wheel_list, add="+")
        popup.bind("<Button-4>", _wheel_list, add="+")
        popup.bind("<Button-5>", _wheel_list, add="+")

        footer = tk.Frame(panel, bg="white")
        footer.pack(fill="x", padx=14, pady=(0, 12))

        tk.Button(
            footer,
            text="Cancel",
            font=("Helvetica", 9),
            bg="#f2f2f2",
            fg="#333333",
            relief="solid",
            bd=1,
            padx=14,
            pady=4,
            command=popup.destroy,
        ).pack(side="right", padx=(8, 0))

        save_btn = tk.Button(
            footer,
            text="Save Selected",
            font=("Helvetica", 9, "bold"),
            bg=UtilsTools.UI_ACCENT_SOFT,
            fg=UtilsTools.UI_ACCENT,
            activebackground=UtilsTools.UI_ACCENT_HOVER,
            activeforeground=UtilsTools.UI_ACCENT,
            relief="solid",
            bd=1,
            padx=16,
            pady=4,
            state="disabled",
            command=_save_selected,
        )
        save_btn.pack(side="right")

        popup.bind("<Escape>", lambda _e: popup.destroy())
        popup.bind("<Return>", _save_selected)

        popup.update_idletasks()
        dialog_w = 500
        dialog_h = min(440, max(190, popup.winfo_reqheight()))
        try:
            self.center_popup_to_parent(popup, dialog_w, dialog_h, parent=parent)
        except Exception:
            self.center_popup(popup, dialog_w, dialog_h)

        # Preselect the active card when available; otherwise choose the first.
        initial = getattr(self, "_image_workspace_active_id", None)
        if initial not in window_ids and window_ids:
            initial = window_ids[0]
        if initial is not None:
            _set_selected(initial)
        popup.deiconify()
        popup.grab_set()


    def open_full_resolution_image_workspace(self, window_id=None):
        """Open a maximizable image workspace using the original source pixels."""
        if window_id is None:
            image_ids = list((getattr(self, "load_images_names", None) or {}).keys())
            if not image_ids:
                self.custom_warning("Image Workspace", "Open an image first.")
                return
            window_id = getattr(self, "_image_workspace_active_id", None)
            if window_id not in image_ids:
                window_id = image_ids[0]
        controller = getattr(self, "_full_resolution_workspace_controller", None)
        if controller is not None:
            try:
                if controller.win.winfo_exists() and controller.source_window_id == window_id:
                    controller.win.lift()
                    controller.win.focus_force()
                    return
                controller.close()
            except tk.TclError:
                pass
        try:
            self._full_resolution_workspace_controller = ImageWorkspaceManager(self, window_id)
        except (ValueError, OSError, tk.TclError) as exc:
            self.custom_warning("Image Workspace", f"Could not open the image workspace:\n{exc}")


    def close_all_image(self):
        """
        Closes all floating windows and cleans up associated UI/window resources.

        Important:
        - This does NOT clear the persistent image-result caches.
        - It only removes window-bound state so cached mappings can be reused
        if the same image is opened again during the session.
        """
        controller = getattr(self, "_full_resolution_workspace_controller", None)
        if controller is not None:
            controller.close()
        if not hasattr(self, "floating_images"):
            return

        # If any process is running, ask once before cancelling and closing everything
        if self._has_any_active_job():
            confirm = messagebox.askyesno(
                "Processes Running",
                "There are one or more processes currently running.\n\n"
                "Do you want to cancel them and close all images?"
            )
            if not confirm:
                return

        for window_id in list(self.floating_images.keys()):
            # Cancel running job linked to the window
            try:
                self._cancel_window_job(window_id)
            except Exception:
                pass

            # Remove rectangle / pixel sampling state
            try:
                self._disable_original_rectangle_sampling(window_id)
            except Exception:
                pass

            # Remove all canvas items with this window tag
            try:
                self.image_canvas.delete(window_id)
            except Exception:
                pass

            # Destroy legend/options UI if present
            if hasattr(self, "proto_options") and window_id in self.proto_options:
                info = self.proto_options.get(window_id)
                if info:
                    frame = info.get("frame")
                    canvas_item = info.get("canvas_item")

                    try:
                        if canvas_item:
                            self.image_canvas.delete(canvas_item)
                    except Exception:
                        pass

                    try:
                        if frame and frame.winfo_exists():
                            frame.destroy()
                    except Exception:
                        pass

                del self.proto_options[window_id]

            # Remove window-bound state only
            for attr_name in (
                "floating_images",
                "pil_images_original",
                "floating_window_state",
                "images",
                "display_pil",
                "original_images",
                "image_dimensions",
                "original_image_dimensions",
                "_resize_callbacks",
                "_pixel_click_callbacks",
                "current_protos",
                "load_images_names",
                "window_image_key",
                "window_mapping_mode",
                "image_view_source",
                "image_view_state",
                "_image_zoom_callbacks",
                "CAN_APPLY_MAPPING",
                "SHOW_ORIGINAL",
                "modified_image",
                "mapping_locked_until_original",
            ):
                if hasattr(self, attr_name):
                    d = getattr(self, attr_name)
                    if isinstance(d, dict) and window_id in d:
                        del d[window_id]

            if getattr(self, "_image_zoom_hover_window", None) == window_id:
                self._image_zoom_hover_window = None

        # Reset leftover per-window dimension dicts if they still exist
        if hasattr(self, "image_dimensions"):
            self.image_dimensions.clear()
        if hasattr(self, "original_image_dimensions"):
            self.original_image_dimensions.clear()

        self._clear_image_display_selection()
        self._image_workspace_focus_id = None
        self._image_workspace_active_id = None
        self._image_workspace_focus_saved_state = None
        self._image_workspace_focus_saved_collapsed = None
        self._image_workspace_callbacks = {}
        self._image_view_pan_state = None
        try:
            self._mapping_all_palette_by_window.clear()
            self._mapping_all_pack_by_window.clear()
        except Exception:
            pass
        self._schedule_image_workspace_reflow(delay=0)


    def _image_workspace_window_ids(self):
        """Return live image-window ids in stable opening order."""
        ids = []
        names = getattr(self, "load_images_names", {}) or {}
        states = getattr(self, "floating_window_state", {}) or {}
        for window_id in names.keys():
            if window_id in states and self._window_exists(window_id):
                ids.append(window_id)
        return ids


    def _update_image_workspace_status(self):
        ids = self._image_workspace_window_ids()
        count = len(ids)
        focus_id = getattr(self, "_image_workspace_focus_id", None)
        layout_mode = getattr(self, "_image_workspace_layout_mode", "grid")

        image_count = f"{count} image{'s' if count != 1 else ''}"
        if focus_id in ids:
            # Focus is a distinct workspace mode; report the underlying layout
            # too, so it remains clear whether it was manual or automatic.
            previous = getattr(self, "_image_workspace_focus_return_mode", layout_mode)
            origin = "Manual" if previous == "manual" else "Automatic"
            text = f"{image_count} · Focus ({origin})"
        else:
            text = f"{image_count} · {'Manual' if layout_mode == 'manual' else 'Automatic'}"

        try:
            self.image_workspace_status_var.set(text)
        except Exception:
            pass

        try:
            focus_active = focus_id in ids
            self.image_workspace_focus_button.configure(
                state="disabled" if (not count or focus_active) else "normal"
            )
            self.image_workspace_grid_button.configure(
                state="normal" if count else "disabled"
            )
        except Exception:
            pass


    def _schedule_image_workspace_reflow(self, delay=35):
        """Debounce workspace layout after resize/open/close/state changes."""
        if not hasattr(self, "image_canvas"):
            return

        previous = getattr(self, "_image_workspace_reflow_after_id", None)
        if previous is not None:
            try:
                self.image_canvas.after_cancel(previous)
            except Exception:
                pass

        try:
            self._image_workspace_reflow_after_id = self.image_canvas.after(
                max(0, int(delay)), self._reflow_image_workspace
            )
        except Exception:
            self._image_workspace_reflow_after_id = None


    def _set_image_workspace_active(self, window_id):
        if window_id not in self._image_workspace_window_ids():
            return
        self._image_workspace_active_id = window_id
        self._focus_floating_window(window_id)
        self._update_image_workspace_status()


    def _display_cached_mapping_all(self, window_id):
        """Recolor the selected label map without repeating any fuzzy calculation."""
        pack = getattr(self, "_mapping_all_pack_by_window", {}).get(window_id)
        if not pack:
            return "break"
        level = pack["level"]
        scheme = pack["scheme"]
        palette = pack["level_palettes"][level][scheme]
        label_map = pack["label_maps"][level]
        colored = self.image_manager.recolor_label_map(
            label_map, palette, pack.get("alpha_values"))
        if not getattr(self.fuzzy_color_space, "covering", True):
            # Uncovered regions retain the original image, including alpha.
            source = self._get_mapping_source_image(window_id)
            source_rgb = np.asarray(UtilsTools._pil_rgb_for_processing(source))
            alpha = UtilsTools._get_alpha_values_from_pil(source)
            missing = (label_map < 0) & (alpha > 0)
            if np.any(missing):
                colored[missing, :3] = source_rgb[missing, :3]
                colored[missing, 3] = alpha[missing]
        pack["label_map"] = label_map  # Compatibility with image export.
        pack["palettes"] = pack["level_palettes"][level]
        self._display_mapping_all_result(window_id, colored, palette)
        return "break"

    def _set_mapping_all_palette(self, window_id, scheme):
        """Switch the Mapping All palette without recomputing category winners."""
        if self._has_active_job(window_id):
            return "break"
        if getattr(self, "mapping_locked_until_original", {}).get(window_id, False):
            self.custom_warning("Old Color Space",
                "This Mapping All result belongs to a previous Color Space. Press Original first.")
            return "break"
        pack = getattr(self, "_mapping_all_pack_by_window", {}).get(window_id)
        if not pack or scheme == pack.get("scheme") or scheme not in ("original", "alt"):
            return "break"
        previous = pack.get("scheme", "original")
        pack["scheme"] = scheme
        try:
            return self._display_cached_mapping_all(window_id)
        except Exception as exc:
            pack["scheme"] = previous
            self.custom_warning("Mapping Display Error", str(exc))
            return "break"

    def _set_mapping_all_level(self, window_id, level):
        """Switch between aggregated categories and explanatory granules."""
        if self._has_active_job(window_id):
            return "break"
        if getattr(self, "mapping_locked_until_original", {}).get(window_id, False):
            self.custom_warning("Old Color Space",
                "This Mapping All result belongs to a previous Color Space. Press Original first.")
            return "break"
        pack = getattr(self, "_mapping_all_pack_by_window", {}).get(window_id)
        if not pack or level == pack.get("level") or level not in ("categories", "granules"):
            return "break"
        old = pack["level"]
        pack["level"] = level
        try:
            return self._display_cached_mapping_all(window_id)
        except Exception as exc:
            pack["level"] = old
            self.custom_warning("Mapping Display Error", str(exc))
            return "break"

    def _toggle_mapping_all_palette(self, window_id):
        """Compatibility wrapper for older callbacks using the toggle action."""
        pack = getattr(self, "_mapping_all_pack_by_window", {}).get(window_id)
        if not pack:
            return "break"
        next_scheme = "original" if pack.get("scheme") == "alt" else "alt"
        return self._set_mapping_all_palette(window_id, next_scheme)


    def _arrange_image_workspace_grid(self):
        """Return to automatic non-overlapping card layout."""
        # A layout change invalidates selection coordinates from the previous card geometry.
        self._clear_image_display_selection()

        self._image_workspace_focus_id = None
        self._image_workspace_layout_mode = "grid"
        self._image_workspace_focus_return_mode = "grid"
        self._image_workspace_focus_saved_state = None
        self._image_workspace_focus_saved_collapsed = None
        self._reflow_image_workspace()


    def _set_image_workspace_manual(self):
        """Keep the current geometry but stop automatic card repositioning."""
        if getattr(self, "_image_workspace_focus_id", None) is not None:
            return
        self._image_workspace_layout_mode = "manual"
        self._update_image_workspace_status()


    def _focus_active_image_workspace_card(self):
        ids = self._image_workspace_window_ids()
        if not ids:
            return

        # Focus is an exclusive workspace mode. Once active, Grid is the only
        # supported way back to the multi-image workspace. This avoids running
        # the focus geometry twice and accumulating size/viewport drift.
        if getattr(self, "_image_workspace_focus_id", None) in ids:
            return

        active = getattr(self, "_image_workspace_active_id", None)
        if active not in ids:
            active = ids[0]
        self._set_image_workspace_focus(active)


    def _set_image_workspace_focus(self, window_id=None):
        """Maximize one image card inside Image Display."""
        ids = self._image_workspace_window_ids()
        if window_id is None or window_id not in ids:
            return

        # Do not allow Focus -> Focus. Re-entering this path used to resize the
        # same card repeatedly and could desynchronize the viewport geometry.
        # Grid is deliberately the only exit from Focus mode.
        if getattr(self, "_image_workspace_focus_id", None) is not None:
            return

        # Focus changes both position and displayed dimensions. Any pixel/ROI
        # marker belongs to the old geometry and must not survive the switch.
        self._clear_image_display_selection()

        # Remember the exact manual rectangle so leaving Focus does not destroy
        # a user-positioned/resized layout. Grid layouts can simply be recomputed.
        self._image_workspace_focus_return_mode = getattr(
            self, "_image_workspace_layout_mode", "grid"
        )
        self._image_workspace_focus_saved_state = None
        state = getattr(self, "floating_window_state", {}).get(window_id)
        self._image_workspace_focus_saved_collapsed = bool(
            state.get("collapsed", False)
        ) if state else False

        if self._image_workspace_focus_return_mode == "manual" and state:
            self._image_workspace_focus_saved_state = dict(state)

        # Focus always opens the selected card. The minimize control is hidden
        # while focused, so there is no conflicting collapsed/focus geometry.
        if state:
            state["collapsed"] = False

        self._image_workspace_focus_id = window_id
        self._image_workspace_active_id = window_id
        self._reflow_image_workspace()


    def _toggle_image_workspace_focus(self, window_id):
        """Enter Focus when possible; Grid is the only supported exit."""
        if getattr(self, "_image_workspace_focus_id", None) is not None:
            return
        self._set_image_workspace_focus(window_id)


    def _is_workspace_card_collapsed(self, window_id):
        state = getattr(self, "floating_window_state", {}).get(window_id, {})
        return bool(state.get("collapsed", False))


    def _sync_workspace_card_item_states(self, window_id):
        """Apply collapsed/focus state without changing image data or callbacks."""
        if window_id not in getattr(self, "floating_window_state", {}):
            return

        collapsed = self._is_workspace_card_collapsed(window_id)
        focus_id = getattr(self, "_image_workspace_focus_id", None)
        hidden_by_focus = focus_id is not None and focus_id != window_id

        if hidden_by_focus:
            try:
                self.image_canvas.itemconfigure(window_id, state="hidden")
            except Exception:
                pass
            return

        try:
            self.image_canvas.itemconfigure(window_id, state="normal")
        except Exception:
            pass

        content_state = "hidden" if collapsed else "normal"
        for tag in (
            f"{window_id}_img_item",
            f"{window_id}_click_image",
            f"{window_id}_pct_text",
            f"{window_id}_selection_rect",
            f"{window_id}_legend",
        ):
            try:
                self.image_canvas.itemconfigure(tag, state=content_state)
            except Exception:
                pass

        # Resize is a manual display action. It is available in Grid/Manual view;
        # grabbing it switches to manual layout. Focus View uses the whole panel.
        resize_state = "hidden" if collapsed or focus_id == window_id else "normal"
        try:
            self.image_canvas.itemconfigure(f"{window_id}_resize_handle", state=resize_state)
        except Exception:
            pass

        minimize_state = "hidden" if focus_id == window_id else "normal"
        for tag in (f"{window_id}_minimize_rect", f"{window_id}_minimize_text"):
            try:
                self.image_canvas.itemconfigure(tag, state=minimize_state)
            except Exception:
                pass

        try:
            self.image_canvas.itemconfigure(
                f"{window_id}_minimize_text",
                text="+" if collapsed else "−"
            )
        except Exception:
            pass


    def _set_workspace_card_visibility(self, window_id, visible=True):
        state = "normal" if visible else "hidden"
        try:
            self.image_canvas.itemconfigure(window_id, state=state)
        except Exception:
            pass

        if visible:
            self._sync_workspace_card_item_states(window_id)


    def _workspace_legend_width(self, window_id):
        """Mapping panels are stacked below the image, so they add no side width."""
        return 0


    def _workspace_legend_height(self, window_id):
        """Return a compact content-sized height for the mapping panel."""
        info = getattr(self, "proto_options", {}).get(window_id)
        if not isinstance(info, dict):
            return 0

        # Keep the selector visually compact: at most four rows are visible.
        # Larger spaces use the internal scrollbar instead of reserving empty
        # vertical space. Short lists shrink to exactly the rows they contain.
        row_count = len(info.get("rows", []) or [])
        visible_rows = max(1, min(row_count if row_count else 1, 4))
        row_h = 24
        pad_top = 5
        footer_h = 66 if info.get("kind") == "all" else 40
        bottom_pad = 4
        return pad_top + visible_rows * row_h + footer_h + bottom_pad


    def _workspace_legend_extra_height(self, window_id):
        """Vertical footprint added by a mapping panel stacked below the image."""
        legend_h = self._workspace_legend_height(window_id)
        if legend_h <= 0:
            return 0

        # The normal card already reserves 50 px below the image. The mapping
        # panel begins after the percentage/status line and then needs a small
        # bottom margin, so almost its full height is additional card space.
        return legend_h + 4


    def _toggle_image_card_minimize(self, window_id):
        """Collapse/restore one card while preserving all image/mapping state."""
        if self._has_active_job(window_id):
            return

        if getattr(self, "_image_workspace_focus_id", None) == window_id:
            return

        state = getattr(self, "floating_window_state", {}).get(window_id)
        if not state:
            return

        state["collapsed"] = not bool(state.get("collapsed", False))
        self._schedule_image_workspace_reflow(delay=0)


    def _update_manual_workspace_scrollregion(self):
        """Keep manually moved cards reachable through the Image Display scrollbars."""
        try:
            bbox = self.image_canvas.bbox("all")
            canvas_w = max(1, int(self.image_canvas.winfo_width()))
            canvas_h = max(1, int(self.image_canvas.winfo_height()))
            if bbox:
                _x1, _y1, x2, y2 = bbox
                self.image_canvas.configure(
                    scrollregion=(0, 0, max(canvas_w, x2 + 20), max(canvas_h, y2 + 20))
                )
            else:
                self.image_canvas.configure(scrollregion=(0, 0, canvas_w, canvas_h))
        except Exception:
            pass


    def _reflow_image_workspace(self):
        """
        Arrange image cards while preserving all existing image functionality.

        Modes
        -----
        grid:
            Automatic non-overlapping cards.
        manual:
            User positions/resizes cards freely. Pressing Grid restores the
            automatic arrangement.
        focus:
            One card temporarily uses almost the whole Image Display area.
        """
        self._image_workspace_reflow_after_id = None

        # Avoid resizing/repositioning a card while a mapping worker is writing
        # its result. The layout is retried immediately after the job settles.
        try:
            if self._has_any_active_job():
                self._schedule_image_workspace_reflow(delay=160)
                return
        except Exception:
            pass

        ids = self._image_workspace_window_ids()
        if not ids:
            try:
                self.image_canvas.configure(scrollregion=(0, 0, 1, 1))
                self.image_canvas.yview_moveto(0.0)
            except Exception:
                pass
            self._image_workspace_focus_id = None
            self._image_workspace_active_id = None
            self._image_workspace_layout_mode = "grid"
            self._update_image_workspace_status()
            return

        if getattr(self, "_image_workspace_active_id", None) not in ids:
            self._image_workspace_active_id = ids[0]

        focus_id = getattr(self, "_image_workspace_focus_id", None)
        if focus_id not in ids:
            focus_id = None
            self._image_workspace_focus_id = None

        try:
            self.image_canvas.update_idletasks()
            canvas_w = max(320, int(self.image_canvas.winfo_width()))
            canvas_h = max(260, int(self.image_canvas.winfo_height()))
        except Exception:
            canvas_w, canvas_h = 620, 520

        outer = 14
        gap_x = 14
        gap_y = 14
        title_pad_x = 24
        card_footer = 50
        collapsed_h = 34

        callbacks = getattr(self, "_image_workspace_callbacks", {})

        # Focus / maximize view
        if focus_id is not None:
            # The main window itself may have been resized while Focus is active.
            # Clear transient selection before recomputing focused geometry.
            self._clear_image_display_selection(focus_id)

            state = self.floating_window_state.get(focus_id)
            if state:
                state["collapsed"] = False

            for wid in ids:
                self._set_workspace_card_visibility(wid, wid == focus_id)

            legend_extra = self._workspace_legend_extra_height(focus_id)
            legend_width = self._workspace_legend_width(focus_id)
            available_w = max(180, canvas_w - (outer * 2))
            available_h = max(160, canvas_h - (outer * 2) - card_footer - legend_extra)

            target_w = min(max(160, available_w - title_pad_x - legend_width), 1100)
            target_h = min(max(140, available_h), 800)

            cb = callbacks.get(focus_id, {})
            resize_cb = cb.get("resize")
            relayout_cb = cb.get("relayout")

            if callable(resize_cb):
                resize_cb(focus_id, target_w, target_h, reset_view=False)

            state = self.floating_window_state.get(focus_id)
            if state:
                state["x"] = outer
                state["y"] = outer

            if callable(relayout_cb):
                relayout_cb(focus_id)

            self._sync_workspace_card_item_states(focus_id)
            content_h = max(
                canvas_h,
                outer * 2
                + (state.get("h", 250) if state else 250)
                + card_footer
                + self._workspace_legend_extra_height(focus_id)
            )
            try:
                self.image_canvas.configure(scrollregion=(0, 0, canvas_w, content_h))
                self.image_canvas.yview_moveto(0.0)
            except Exception:
                pass

            self._image_workspace_active_id = focus_id
            self._focus_floating_window(focus_id)
            self._update_image_workspace_status()
            return

        # Manual layout: preserve exact user geometry.
        if getattr(self, "_image_workspace_layout_mode", "grid") == "manual":
            for wid in ids:
                self._set_workspace_card_visibility(wid, True)
                cb = callbacks.get(wid, {})
                relayout_cb = cb.get("relayout")
                if callable(relayout_cb):
                    relayout_cb(wid)
                self._sync_workspace_card_item_states(wid)

            self._update_manual_workspace_scrollregion()
            self._update_image_workspace_status()
            return

        # Automatic grid
        # Grid may resize/reposition cards after a main-window resize, opening
        # a mapping panel, or returning from Focus. Never leave a selection
        # marker tied to the previous geometry.
        self._clear_image_display_selection()
        self._image_workspace_layout_mode = "grid"
        for wid in ids:
            self._set_workspace_card_visibility(wid, True)

        # Choose the largest useful column count for the image cards. Mapping
        # panels are stacked below their images and therefore add no side width.
        max_panel_w = max((self._workspace_legend_width(wid) for wid in ids), default=0)
        preferred = 3 if canvas_w >= 960 and len(ids) >= 3 else (2 if canvas_w >= 560 and len(ids) >= 2 else 1)
        columns = 1
        for candidate in range(preferred, 0, -1):
            candidate_slot = max(220, int((canvas_w - outer * 2 - gap_x * (candidate - 1)) / candidate))
            if candidate_slot - title_pad_x - 8 - max_panel_w >= 180 or candidate == 1:
                columns = candidate
                break

        slot_w = max(220, int((canvas_w - outer * 2 - gap_x * (columns - 1)) / columns))

        # Row heights adapt to minimized cards and to mapping panels below images.
        row_groups = [ids[i:i + columns] for i in range(0, len(ids), columns)]
        row_heights = []
        for group in row_groups:
            if all(self._is_workspace_card_collapsed(wid) for wid in group):
                row_heights.append(collapsed_h + 8)
            else:
                legend_extra = max(
                    (self._workspace_legend_extra_height(wid) for wid in group),
                    default=0,
                )
                row_heights.append(315 + legend_extra)

        y_offsets = []
        current_y = outer
        for height in row_heights:
            y_offsets.append(current_y)
            current_y += height + gap_y

        for index, wid in enumerate(ids):
            row = index // columns
            col = index % columns
            x = outer + col * (slot_w + gap_x)
            y = y_offsets[row]

            cb = callbacks.get(wid, {})
            resize_cb = cb.get("resize")
            relayout_cb = cb.get("relayout")

            if not self._is_workspace_card_collapsed(wid):
                target_w = max(
                    150,
                    slot_w - title_pad_x - 8 - self._workspace_legend_width(wid)
                )
                target_h = 245
                if callable(resize_cb):
                    resize_cb(wid, target_w, target_h, reset_view=False)

            state = self.floating_window_state.get(wid)
            if state:
                state["x"] = x
                state["y"] = y

            if callable(relayout_cb):
                relayout_cb(wid)
            self._sync_workspace_card_item_states(wid)

        content_h = max(canvas_h, current_y + outer)
        try:
            self.image_canvas.configure(scrollregion=(0, 0, canvas_w, content_h))
        except Exception:
            pass

        self._update_image_workspace_status()


    def open_image(self):
        """Allow the user to open an image in the automatic Image Display workspace."""
        if self._has_any_active_job():
            self.custom_warning(
                "Process Running",
                "Finish or cancel the current color mapping process before opening a new image."
            )
            return

        initial_directory = os.path.join(BASE_PATH, 'image_test')

        filetypes = [
            ("Image Files", "*.jpg *.jpeg *.png *.bmp *.gif *.tiff *.tif *.webp *.JPG *.JPEG *.PNG *.BMP *.GIF *.TIFF *.TIF *.WEBP"),
            ("All Files", "*.*")
        ]

        filename = filedialog.askopenfilename(
            title="Select an Image",
            initialdir=initial_directory,
            filetypes=filetypes,
            parent=self.root,
        )

        if filename:
            self.create_floating_window(14, 14, filename)


    def _clear_original_selection_rectangle(self, window_id):
        """
        Remove the current original-image selection rectangle for a floating window
        without disabling rectangle sampling bindings/state.
        """
        if not hasattr(self, "_original_sampling_state"):
            return

        state = self._original_sampling_state.get(window_id)
        if not state:
            return

        rect_id = state.get("rect_id")
        if rect_id is not None:
            try:
                self.image_canvas.delete(rect_id)
            except Exception:
                pass

        state["rect_id"] = None
        state["dragging"] = False
        state["drag_start"] = None


    def _clear_image_display_selection(self, window_id=None, clear_info=True):
        """
        Clear transient pixel/ROI selection state from Image Display.

        Layout changes (Grid, Focus, move, resize) change the canvas geometry,
        therefore a marker drawn before the change must never be kept.
        """
        if window_id is None:
            ids = list(getattr(self, "_original_sampling_state", {}).keys())
        else:
            ids = [window_id]

        for wid in ids:
            try:
                self._clear_original_selection_rectangle(wid)
            except Exception:
                pass

        if not clear_info:
            return

        info = getattr(self, "_last_pixel_info", None)
        if info is not None:
            info_id = info.get("image_id") if isinstance(info, dict) else None
            if window_id is None or info_id == window_id:
                self._last_pixel_info = None
                frame = getattr(self, "lab_value_frame", None)
                if frame is not None:
                    try:
                        if frame.winfo_exists():
                            frame.destroy()
                    except Exception:
                        pass
                for attr in (
                    "lab_value_frame", "coord_value",
                    "lab_value_print", "proto_value_text",
                ):
                    try:
                        delattr(self, attr)
                    except Exception:
                        pass


    def _get_image_view_crop_box(self, window_id):
        """Return the visible crop in current view-source coordinates."""
        source = getattr(self, "image_view_source", {}).get(window_id)
        if source is None:
            source = getattr(self, "pil_images_original", {}).get(window_id)
        if source is None:
            return None

        source_w, source_h = source.size
        state = getattr(self, "image_view_state", {}).get(window_id)
        if not state:
            state = {"zoom": 1.0, "cx": source_w / 2.0, "cy": source_h / 2.0}
            self.image_view_state[window_id] = state

        zoom = max(1.0, float(state.get("zoom", 1.0)))
        crop_w = max(1.0, source_w / zoom)
        crop_h = max(1.0, source_h / zoom)
        cx = float(state.get("cx", source_w / 2.0))
        cy = float(state.get("cy", source_h / 2.0))
        left = max(0.0, min(source_w - crop_w, cx - crop_w / 2.0))
        top = max(0.0, min(source_h - crop_h, cy - crop_h / 2.0))
        return left, top, left + crop_w, top + crop_h


    def _canvas_xy_to_view_source(self, window_id, canvas_x, canvas_y):
        """Map canvas coordinates to the currently displayed view source."""
        st = getattr(self, "floating_window_state", {}).get(window_id)
        crop = self._get_image_view_crop_box(window_id)
        if not st or crop is None:
            return None

        img_left = float(st["x"]) + 12.0
        img_top = float(st["y"]) + 44.0
        draw_w = max(1.0, float(st["w"]))
        draw_h = max(1.0, float(st["h"]))
        rel_x = float(canvas_x) - img_left
        rel_y = float(canvas_y) - img_top
        if not (0.0 <= rel_x < draw_w and 0.0 <= rel_y < draw_h):
            return None

        left, top, right, bottom = crop
        source_x = left + (rel_x / draw_w) * (right - left)
        source_y = top + (rel_y / draw_h) * (bottom - top)
        return source_x, source_y, rel_x, rel_y


    def _view_source_xy_to_original(self, window_id, source_x, source_y):
        """Convert coordinates from a mapped/original view source to original pixels."""
        source = getattr(self, "image_view_source", {}).get(window_id)
        original = getattr(self, "pil_images_original", {}).get(window_id)
        if source is None or original is None:
            return None

        sw, sh = source.size
        ow, oh = original.size
        if sw <= 0 or sh <= 0 or ow <= 0 or oh <= 0:
            return None

        # Use normalized position because mapping views may be computed at a
        # display/processing resolution different from the original image.
        ox = (float(source_x) / float(sw)) * float(ow)
        oy = (float(source_y) / float(sh)) * float(oh)
        ox = int(max(0, min(ow - 1, ox)))
        oy = int(max(0, min(oh - 1, oy)))
        return ox, oy


    def _canvas_xy_to_original_image(self, window_id, canvas_x, canvas_y):
        """Map a visible canvas point to the corresponding original-image pixel."""
        point = self._canvas_xy_to_view_source(window_id, canvas_x, canvas_y)
        if point is None:
            return None
        sx, sy, rel_x, rel_y = point
        original = self._view_source_xy_to_original(window_id, sx, sy)
        if original is None:
            return None
        return original[0], original[1], rel_x, rel_y


    def _set_image_zoom_source(self, window_id, pil_source, reset_zoom=True):
        """
        Set the PIL image used by the viewport zoom system.

        This must be called every time the visible image changes:
        - Original Image
        - Color Mapping
        - Color Mapping All
        - Recoloring Color Mapping All
        """
        if pil_source is None:
            return

        if not hasattr(self, "image_view_source"):
            self.image_view_source = {}

        if not hasattr(self, "image_view_state"):
            self.image_view_state = {}

        self.image_view_source[window_id] = pil_source

        if reset_zoom or window_id not in self.image_view_state:
            w, h = pil_source.size
            self.image_view_state[window_id] = {
                "zoom": 1.0,
                "cx": w / 2,
                "cy": h / 2,
            }

        try:
            self.image_canvas.itemconfig(f"{window_id}_pct_text", text="")
        except Exception:
            pass


    def _ensure_image_zoom_mousewheel_binding(self):
        """
        Bind mouse wheel zoom once directly to the image canvas.

        Important:
        - Image zoom is bound directly to image_canvas.
        - Scrollable panels use independent pointer-aware dispatchers, so
          their wheel handling cannot replace or remove this binding.
        """
        if getattr(self, "_image_zoom_mousewheel_bound", False):
            return

        if not hasattr(self, "image_canvas"):
            return

        if not hasattr(self, "_image_zoom_callbacks"):
            self._image_zoom_callbacks = {}

        def _get_window_id_from_current_canvas_item():
            """
            Try to recover the floating window id from the canvas item currently
            under the mouse pointer.
            """
            try:
                current_items = self.image_canvas.find_withtag("current")
                if not current_items:
                    return None

                tags = self.image_canvas.gettags(current_items[0])

                for tag in tags:
                    if (
                        hasattr(self, "floating_window_state")
                        and tag in self.floating_window_state
                    ):
                        return tag

            except Exception:
                pass

            return None

        def _event_is_inside_image(window_id, event):
            """
            Ensure the wheel event happened inside the displayed image area,
            not just somewhere else in the image canvas.
            """
            try:
                if (
                    not hasattr(self, "floating_window_state")
                    or window_id not in self.floating_window_state
                ):
                    return False

                st = self.floating_window_state[window_id]

                IMG_LEFT_PAD = 12
                IMG_TOP_PAD = 44

                img_left = st["x"] + IMG_LEFT_PAD
                img_top = st["y"] + IMG_TOP_PAD
                img_right = img_left + st["w"]
                img_bottom = img_top + st["h"]

                abs_x = self.image_canvas.canvasx(event.x)
                abs_y = self.image_canvas.canvasy(event.y)

                return img_left <= abs_x < img_right and img_top <= abs_y < img_bottom

            except Exception:
                return False

        def _get_legend_target_window():
            """
            Return the image id whose canvas-native mapping legend is currently
            under the mouse pointer. Mapping legends are drawn with normal Canvas
            primitives, so wheel events must be dispatched from the Canvas itself:
            Canvas.tag_bind() does not accept <MouseWheel>.
            """
            try:
                current_items = self.image_canvas.find_withtag("current")
                if not current_items:
                    return None

                tags = self.image_canvas.gettags(current_items[0])
                if "legend" not in tags:
                    return None

                panels = getattr(self, "proto_options", {}) or {}
                for tag in tags:
                    if tag in panels:
                        return tag
            except Exception:
                pass

            return None

        def _get_zoom_target_window(event):
            """
            Get the current floating image window that should receive the zoom event.
            Prefer the hover window, but fall back to the canvas current item.
            """
            window_id = getattr(self, "_image_zoom_hover_window", None)

            if not window_id:
                window_id = _get_window_id_from_current_canvas_item()

            if not window_id:
                return None

            if not _event_is_inside_image(window_id, event):
                return None

            return window_id

        def _dispatch_mousewheel(event):
            # Mapping legend scrolling has priority over image zoom whenever the
            # pointer is physically over the legend. This keeps both behaviors on
            # one legal Canvas-level <MouseWheel> binding.
            legend_window = _get_legend_target_window()
            if legend_window:
                delta = -1 if getattr(event, "delta", 0) > 0 else 1
                return self._scroll_proto_options(legend_window, delta)

            window_id = _get_zoom_target_window(event)
            if not window_id:
                return None

            callbacks = self._image_zoom_callbacks.get(window_id)
            if not callbacks:
                return None

            callback = callbacks.get("wheel")
            if callback:
                return callback(event)

            return None

        def _dispatch_linux_wheel_up(event):
            legend_window = _get_legend_target_window()
            if legend_window:
                return self._scroll_proto_options(legend_window, -1)

            window_id = _get_zoom_target_window(event)
            if not window_id:
                return None

            callbacks = self._image_zoom_callbacks.get(window_id)
            if not callbacks:
                return None

            callback = callbacks.get("linux_up")
            if callback:
                return callback(event)

            return None

        def _dispatch_linux_wheel_down(event):
            legend_window = _get_legend_target_window()
            if legend_window:
                return self._scroll_proto_options(legend_window, 1)

            window_id = _get_zoom_target_window(event)
            if not window_id:
                return None

            callbacks = self._image_zoom_callbacks.get(window_id)
            if not callbacks:
                return None

            callback = callbacks.get("linux_down")
            if callback:
                return callback(event)

            return None

        # Bind directly to the image canvas, not globally. Scrollable panels
        # use their own pointer-aware Toplevel dispatcher.
        self.image_canvas.bind("<MouseWheel>", _dispatch_mousewheel, add="+")
        self.image_canvas.bind("<Button-4>", _dispatch_linux_wheel_up, add="+")
        self.image_canvas.bind("<Button-5>", _dispatch_linux_wheel_down, add="+")

        self._image_zoom_mousewheel_bound = True


    def create_floating_window(self, x, y, filename):
        """
        Create an image card inside the automatic Image Display workspace.

        The existing canvas implementation is intentionally preserved so mapping,
        ROI inspection, saving and viewport zoom continue using the same window ids
        and callbacks. Placement and display size are managed automatically to avoid
        overlapping images.

        Cache design:
        - Window UI state is keyed by window_id.
        - Persistent mapping caches are keyed by:
            ((abs_path, mtime, size), color_space_key)
        so cached results survive window close/reopen within the same session.
        """
        if self._has_any_active_job():
            self.custom_warning(
                "Process Running",
                "Finish or cancel the current color mapping process before opening a new image."
            )
            return

        # Lazy-init dictionaries
        if not hasattr(self, "load_images_names"):
            self.load_images_names = {}
        if not hasattr(self, "images"):
            self.images = {}
        if not hasattr(self, "floating_images"):
            self.floating_images = {}
            self.original_images = {}
            self.modified_image = {}

        # Store original PIL images for correct pixel mapping after resize
        if not hasattr(self, "pil_images_original"):
            self.pil_images_original = {}

        if not hasattr(self, "image_dimensions"):
            self.image_dimensions = {}
        if not hasattr(self, "original_image_dimensions"):
            self.original_image_dimensions = {}

        # Store window top-left and current size for move/resize consistency
        if not hasattr(self, "floating_window_state"):
            self.floating_window_state = {}  # window_id -> dict(x,y,w,h)

        # Store the currently displayed PIL image (source of truth for saving)
        if not hasattr(self, "display_pil"):
            self.display_pil = {}

        # Store viewport zoom state for each floating image
        if not hasattr(self, "image_view_source"):
            self.image_view_source = {}

        if not hasattr(self, "image_view_state"):
            self.image_view_state = {}

        if not hasattr(self, "_image_zoom_callbacks"):
            self._image_zoom_callbacks = {}

        if not hasattr(self, "_image_zoom_hover_window"):
            self._image_zoom_hover_window = None

        self._ensure_image_zoom_mousewheel_binding()

        # Persistent caches by image + color space
        if not hasattr(self, "window_image_key"):
            self.window_image_key = {}
        if not hasattr(self, "cm_cache_by_image"):
            # Cache reusable mapping calculations independently from card presentation.
            self.cm_cache_by_image = {}
        if not hasattr(self, "proto_percentage_cache_by_image"):
            self.proto_percentage_cache_by_image = {}

        # Generate unique ID
        while True:
            window_id = f"floating_{random.randint(1000, 9999)}"
            if window_id not in self.load_images_names:
                break

        self.load_images_names[window_id] = filename

        # Stable cache key for this image during the session
        image_key = (
            os.path.abspath(filename),
            os.path.getmtime(filename),
            os.path.getsize(filename)
        )
        self.window_image_key[window_id] = image_key

        # State flags
        self.CAN_APPLY_MAPPING[window_id] = bool(self.COLOR_SPACE)
        self.SHOW_ORIGINAL[window_id] = False

        # Load images
        with Image.open(filename) as image_file:
            pil_original = ImageOps.exif_transpose(image_file).convert("RGBA")
        original_width, original_height = pil_original.size
        self.pil_images_original[window_id] = pil_original
        self.original_image_dimensions[window_id] = (original_width, original_height)

        # Initial target size (image area)
        target_w, target_h = 250, 250
        scale = min(target_w / original_width, target_h / original_height)
        new_width = max(1, int(original_width * scale))
        new_height = max(1, int(original_height * scale))

        pil_resized = pil_original.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Store resized display image and dimensions
        self.images[window_id] = pil_resized
        self.image_dimensions[window_id] = (new_width, new_height)

        # Store the currently displayed PIL image (source of truth for saving)
        self.display_pil[window_id] = pil_resized

        # Viewport zoom source and state.
        # Viewport crops never replace the original source image.
        self.image_view_source[window_id] = pil_original
        self.image_view_state[window_id] = {
            "zoom": 1.0,
            "cx": original_width / 2,
            "cy": original_height / 2,
        }


        img_tk = ImageTk.PhotoImage(pil_resized)
        self.floating_images[window_id] = img_tk
        self.original_images[window_id] = img_tk

        # Window paddings
        PAD_X = 24
        PAD_Y = 50
        TITLE_H = 34
        IMG_TOP_PAD = 44
        IMG_LEFT_PAD = 12
        HANDLE_SIZE = 10

        # Save initial window state
        self.floating_window_state[window_id] = {
            "x": x,
            "y": y,
            "w": new_width,
            "h": new_height,
            "collapsed": False,
        }

        # Create canvas items
        self.image_canvas.create_rectangle(
            x, y, x + new_width + PAD_X, y + new_height + PAD_Y,
            outline="#cfd5dd", fill="#ffffff", width=1,
            tags=(window_id, "floating", f"{window_id}_bg")
        )

        self.image_canvas.create_rectangle(
            x, y, x + new_width + PAD_X, y + TITLE_H,
            outline="#cfd5dd", fill="#f1f3f6",
            tags=(window_id, "floating", f"{window_id}_title")
        )

        self.image_canvas.create_text(
            x + 34, y + TITLE_H / 2, anchor="w",
            text=os.path.basename(filename),
            fill="#1f2937", font=("Segoe UI", 9, "bold"),
            tags=(window_id, "floating", f"{window_id}_title_text")
        )

        self.image_canvas.create_rectangle(
            x + new_width + PAD_X - 7, y + 7,
            x + new_width + PAD_X - 27, y + 27,
            outline="#d9dde3", fill="#ffffff",
            tags=(window_id, "floating", f"{window_id}_close_button", f"{window_id}_close_rect")
        )
        self.image_canvas.create_text(
            x + new_width + PAD_X - 17, y + 17,
            text="×", fill="#8a1f1f", font=("Segoe UI", 11, "bold"),
            tags=(window_id, "floating", f"{window_id}_close_button", f"{window_id}_close_text")
        )

        # Keep only the compact minimize control in each card header.
        # Focus remains available from the workspace toolbar / context menu,
        # while manual enlargement is handled by the bottom-right resize grip.

        self.image_canvas.create_rectangle(
            x + new_width + PAD_X - 53, y + 7,
            x + new_width + PAD_X - 33, y + 27,
            outline="#d9dde3", fill="#ffffff",
            tags=(window_id, "floating", f"{window_id}_minimize_button", f"{window_id}_minimize_rect")
        )
        self.image_canvas.create_text(
            x + new_width + PAD_X - 43, y + 17,
            text="−", fill=UtilsTools.UI_ACCENT, font=("Segoe UI", 11, "bold"),
            tags=(window_id, "floating", f"{window_id}_minimize_button", f"{window_id}_minimize_text")
        )

        self.image_canvas.create_text(
            x + 15, y + TITLE_H / 2, text="⋮",
            fill=UtilsTools.UI_ACCENT, font=("Segoe UI", 13, "bold"),
            tags=(window_id, "floating", f"{window_id}_arrow_button", f"{window_id}_arrow_text")
        )

        self.image_canvas.create_image(
            x + IMG_LEFT_PAD, y + IMG_TOP_PAD,
            anchor="nw",
            image=self.floating_images[window_id],
            tags=(window_id, "floating", f"{window_id}_click_image", f"{window_id}_img_item")
        )

        self.image_canvas.create_text(
            x + IMG_LEFT_PAD + new_width / 2,
            y + IMG_TOP_PAD + new_height + 8,
            anchor="n",
            text="",
            fill="#374151",
            font=("Sans", 8),
            tags=(window_id, "floating", f"{window_id}_pct_text")
        )

        hx1 = x + new_width + PAD_X - HANDLE_SIZE - 2
        hy1 = y + new_height + PAD_Y - HANDLE_SIZE - 2
        hx2 = x + new_width + PAD_X - 2
        hy2 = y + new_height + PAD_Y - 2
        self.image_canvas.create_rectangle(
            hx1, hy1, hx2, hy2,
            outline="black", fill="lightgray",
            tags=(window_id, "floating", f"{window_id}_resize_handle")
        )

        # Helpers to relayout + resize
        def _relayout(window_id):
            """Update all canvas item positions based on stored floating window state."""
            st = self.floating_window_state[window_id]
            wx, wy, ww, wh = st["x"], st["y"], st["w"], st["h"]

            collapsed = bool(st.get("collapsed", False))
            legend_h = 0 if collapsed else self._workspace_legend_height(window_id)
            legend_info = getattr(self, "proto_options", {}).get(window_id, {})
            legend_w = 0 if collapsed or not isinstance(legend_info, dict) else max(180, int(ww))

            # The mapping panel now sits below the image. Card width therefore
            # remains compact, only growing when a very narrow manually resized
            # image needs the selector's 210 px minimum width.
            base_right = wx + ww + PAD_X
            legend_right = wx + IMG_LEFT_PAD + legend_w + 12 if legend_h else base_right
            card_right = max(base_right, legend_right)

            if collapsed:
                card_bottom = wy + TITLE_H
            elif legend_h:
                # The mapping panel is the final visual element of the card.
                # Use the same dynamic gap as _reposition_proto_options and end
                # the card exactly at the panel border: no white strip below.
                legend_info = getattr(self, "proto_options", {}).get(window_id, {})
                panel_gap = int(legend_info.get("gap", 7)) if isinstance(legend_info, dict) else 7
                panel_y = wy + IMG_TOP_PAD + wh + panel_gap
                card_bottom = panel_y + legend_h
            else:
                card_bottom = wy + wh + PAD_Y

            self.image_canvas.coords(f"{window_id}_bg", wx, wy, card_right, card_bottom)
            self.image_canvas.coords(f"{window_id}_title", wx, wy, card_right, wy + TITLE_H)

            self.image_canvas.coords(f"{window_id}_title_text", wx + 34, wy + TITLE_H / 2)
            self.image_canvas.coords(f"{window_id}_arrow_text", wx + 15, wy + TITLE_H / 2)

            self.image_canvas.coords(
                f"{window_id}_close_rect",
                card_right - 7, wy + 7,
                card_right - 27, wy + 27
            )
            self.image_canvas.coords(f"{window_id}_close_text", card_right - 17, wy + 17)

            self.image_canvas.coords(
                f"{window_id}_minimize_rect",
                card_right - 53, wy + 7,
                card_right - 33, wy + 27
            )
            self.image_canvas.coords(f"{window_id}_minimize_text", card_right - 43, wy + 17)

            self.image_canvas.coords(f"{window_id}_img_item", wx + IMG_LEFT_PAD, wy + IMG_TOP_PAD)

            hx1 = wx + ww + PAD_X - HANDLE_SIZE - 2
            hy1 = wy + wh + PAD_Y - HANDLE_SIZE - 2
            hx2 = wx + ww + PAD_X - 2
            hy2 = wy + wh + PAD_Y - 2
            self.image_canvas.coords(f"{window_id}_resize_handle", hx1, hy1, hx2, hy2)

            self._reposition_proto_options(window_id)

            # Keep mapping coverage centered under the displayed image.
            # Its position therefore remains correct after Grid/Focus/manual
            # resizing instead of being visually attached to the left edge.
            pct_y = wy + IMG_TOP_PAD + wh + 4
            legend_info = getattr(self, "proto_options", {}).get(window_id, {})
            if isinstance(legend_info, dict) and legend_info:
                gap_now = int(legend_info.get("gap", 7))
                if gap_now >= 18:
                    pct_y = wy + IMG_TOP_PAD + wh + 3

            self.image_canvas.coords(
                f"{window_id}_pct_text",
                wx + IMG_LEFT_PAD + ww / 2,
                pct_y,
            )

            self._reposition_window_loading(window_id)

            if hasattr(self, "_original_sampling_state") and window_id in self._original_sampling_state:
                state = self._original_sampling_state[window_id]
                state["img_x"] = wx + IMG_LEFT_PAD
                state["img_y"] = wy + IMG_TOP_PAD
                state["draw_w"] = ww
                state["draw_h"] = wh

            self._sync_workspace_card_item_states(window_id)
            self._focus_floating_window(window_id)

        def _update_image_to_size(window_id, target_w, target_h, reset_view=True):
            """
            Resize the floating image window while preserving aspect ratio.

            Important:
            - This changes the window/image display size.
            - Mouse-wheel zoom does NOT call this function anymore.
            - Mouse-wheel zoom only changes the viewport crop.
            """
            source_pil = self.image_view_source.get(
                window_id,
                self.pil_images_original[window_id]
            )

            ow, oh = source_pil.size

            scale = min(target_w / ow, target_h / oh)
            new_w = max(30, int(ow * scale))
            new_h = max(30, int(oh * scale))

            self.floating_window_state[window_id]["w"] = new_w
            self.floating_window_state[window_id]["h"] = new_h
            self.image_dimensions[window_id] = (new_w, new_h)

            if reset_view:
                self.image_view_state[window_id] = {
                    "zoom": 1.0,
                    "cx": ow / 2,
                    "cy": oh / 2,
                }

            _render_image_view(window_id)
            _relayout(window_id)


        # Viewport zoom helpers
        def _clamp(value, min_value, max_value):
            """Clamp value between min_value and max_value."""
            return max(min_value, min(max_value, value))


        def _get_view_crop_box(window_id):
            """Return the visible crop in current view-source coordinates."""
            crop = self._get_image_view_crop_box(window_id)
            if crop is None:
                source_pil = self.image_view_source.get(
                    window_id, self.pil_images_original[window_id]
                )
                return 0.0, 0.0, float(source_pil.size[0]), float(source_pil.size[1])
            return crop


        def _render_image_view(window_id):
            """
            Render the current viewport crop into the existing floating image size.

            This is the key difference:
            - The image item keeps the same width/height.
            - The crop area changes according to zoom and center.
            """
            if window_id not in self.floating_window_state:
                return

            source_pil = self.image_view_source.get(
                window_id,
                self.pil_images_original[window_id]
            )

            st = self.floating_window_state[window_id]
            draw_w = max(1, int(st["w"]))
            draw_h = max(1, int(st["h"]))

            left, top, right, bottom = _get_view_crop_box(window_id)

            crop = source_pil.crop((
                int(round(left)),
                int(round(top)),
                int(round(right)),
                int(round(bottom))
            ))

            pil_view = crop.resize((draw_w, draw_h), Image.Resampling.LANCZOS)

            self.images[window_id] = pil_view
            self.image_dimensions[window_id] = (draw_w, draw_h)
            self.display_pil[window_id] = pil_view

            img_tk = ImageTk.PhotoImage(pil_view)
            self.floating_images[window_id] = img_tk

            self.image_canvas.itemconfig(
                f"{window_id}_img_item",
                image=self.floating_images[window_id]
            )


        def _canvas_point_to_view_source(event, window_id):
            """Map a mouse event to the current view-source coordinates."""
            abs_x = self.image_canvas.canvasx(event.x)
            abs_y = self.image_canvas.canvasy(event.y)
            return self._canvas_xy_to_view_source(window_id, abs_x, abs_y)


        def _canvas_point_to_original_image(event, window_id):
            """Map a mouse event to the real full-resolution original pixel."""
            abs_x = self.image_canvas.canvasx(event.x)
            abs_y = self.image_canvas.canvasy(event.y)
            return self._canvas_xy_to_original_image(window_id, abs_x, abs_y)


        def _apply_zoom(window_id, factor=None, reset=False, event=None):
            """
            Apply zoom to the viewport without changing the floating window size.

            Wheel zoom behavior:
            - The point under the cursor remains under the cursor after zooming.
            - Only the internal crop changes.
            """
            if self._has_active_job(window_id):
                return "break"

            try:
                self._clear_original_selection_rectangle(window_id)
            except Exception:
                pass

            source_pil = self.image_view_source.get(
                window_id,
                self.pil_images_original[window_id]
            )
            source_w, source_h = source_pil.size

            if reset:
                self.image_view_state[window_id] = {
                    "zoom": 1.0,
                    "cx": source_w / 2,
                    "cy": source_h / 2,
                }

                _render_image_view(window_id)

                try:
                    self.image_canvas.itemconfig(f"{window_id}_pct_text", text="")
                except Exception:
                    pass

                return "break"

            if factor is None:
                return "break"

            state = self.image_view_state.get(window_id)
            if not state:
                state = {
                    "zoom": 1.0,
                    "cx": source_w / 2,
                    "cy": source_h / 2,
                }
                self.image_view_state[window_id] = state

            point_info = None
            if event is not None:
                point_info = _canvas_point_to_view_source(event, window_id)

            old_zoom = float(state.get("zoom", 1.0))
            new_zoom = _clamp(old_zoom * factor, 1.0, 12.0)

            # If zoom did not change, stop.
            if abs(new_zoom - old_zoom) < 1e-9:
                return "break"

            state["zoom"] = new_zoom

            # If the mouse is over the image, keep that source point under the cursor.
            if point_info is not None:
                source_x, source_y, rel_x, rel_y = point_info

                st = self.floating_window_state[window_id]
                draw_w = max(1, int(st["w"]))
                draw_h = max(1, int(st["h"]))

                crop_w = max(1.0, source_w / new_zoom)
                crop_h = max(1.0, source_h / new_zoom)

                rel_fx = rel_x / draw_w
                rel_fy = rel_y / draw_h

                new_left = source_x - rel_fx * crop_w
                new_top = source_y - rel_fy * crop_h

                new_left = _clamp(new_left, 0, max(0, source_w - crop_w))
                new_top = _clamp(new_top, 0, max(0, source_h - crop_h))

                state["cx"] = new_left + crop_w / 2
                state["cy"] = new_top + crop_h / 2

            _render_image_view(window_id)

            try:
                self.image_canvas.itemconfig(
                    f"{window_id}_pct_text",
                    text=f"Zoom: {new_zoom * 100:.0f}%"
                )
            except Exception:
                pass

            return "break"


        def _zoom_mousewheel(event):
            """Mouse wheel zoom handler for Windows/macOS."""
            if event.delta > 0:
                return _apply_zoom(window_id, factor=1.15, event=event)
            else:
                return _apply_zoom(window_id, factor=1 / 1.15, event=event)


        def _zoom_linux_in(event):
            """Mouse wheel up zoom handler for Linux."""
            return _apply_zoom(window_id, factor=1.15, event=event)


        def _zoom_linux_out(event):
            """Mouse wheel down zoom handler for Linux."""
            return _apply_zoom(window_id, factor=1 / 1.15, event=event)


        def _activate_image_zoom(event):
            """Mark this floating image as the current mouse-wheel zoom target."""
            self._image_zoom_hover_window = window_id
            return None


        def _deactivate_image_zoom(event):
            """Clear the mouse-wheel zoom target when leaving this image."""
            if getattr(self, "_image_zoom_hover_window", None) == window_id:
                self._image_zoom_hover_window = None
            return None

        # Right-drag viewport move
        def _start_view_pan(event):
            """Start moving the zoomed viewport with the right mouse button."""
            if self._has_active_job(window_id):
                return "break"

            state = self.image_view_state.get(window_id)
            if not state or float(state.get("zoom", 1.0)) <= 1.000001:
                # At Fit there is no hidden image area to move.
                return "break"

            self._set_image_workspace_active(window_id)
            self._clear_image_display_selection(window_id)

            source_pil = self.image_view_source.get(
                window_id,
                self.pil_images_original.get(window_id)
            )
            if source_pil is None:
                return "break"

            source_w, source_h = source_pil.size
            zoom = max(1.0, float(state.get("zoom", 1.0)))
            crop_w = max(1.0, source_w / zoom)
            crop_h = max(1.0, source_h / zoom)

            self._image_view_pan_state = {
                "window_id": window_id,
                "start_x": self.image_canvas.canvasx(event.x),
                "start_y": self.image_canvas.canvasy(event.y),
                "start_cx": float(state.get("cx", source_w / 2.0)),
                "start_cy": float(state.get("cy", source_h / 2.0)),
                "crop_w": crop_w,
                "crop_h": crop_h,
                "source_w": float(source_w),
                "source_h": float(source_h),
            }

            try:
                self.image_canvas.configure(cursor="fleur")
            except Exception:
                pass

            return "break"

        def _drag_view_pan(event):
            """Move the current zoom crop while right-dragging."""
            pan = getattr(self, "_image_view_pan_state", None)
            if not isinstance(pan, dict) or pan.get("window_id") != window_id:
                return "break"

            state = self.image_view_state.get(window_id)
            st = self.floating_window_state.get(window_id)
            if not state or not st:
                return "break"

            draw_w = max(1.0, float(st.get("w", 1)))
            draw_h = max(1.0, float(st.get("h", 1)))

            current_x = self.image_canvas.canvasx(event.x)
            current_y = self.image_canvas.canvasy(event.y)
            dx = current_x - pan["start_x"]
            dy = current_y - pan["start_y"]

            # Convert displayed-pixel movement to source-image movement.
            # Dragging the image right/down moves the viewport center left/up.
            source_dx = dx * (pan["crop_w"] / draw_w)
            source_dy = dy * (pan["crop_h"] / draw_h)

            half_w = pan["crop_w"] / 2.0
            half_h = pan["crop_h"] / 2.0
            min_cx = half_w
            max_cx = max(half_w, pan["source_w"] - half_w)
            min_cy = half_h
            max_cy = max(half_h, pan["source_h"] - half_h)

            state["cx"] = _clamp(pan["start_cx"] - source_dx, min_cx, max_cx)
            state["cy"] = _clamp(pan["start_cy"] - source_dy, min_cy, max_cy)

            _render_image_view(window_id)
            return "break"

        def _end_view_pan(_event=None):
            """Finish a right-drag viewport move."""
            pan = getattr(self, "_image_view_pan_state", None)
            if isinstance(pan, dict) and pan.get("window_id") == window_id:
                self._image_view_pan_state = None

            try:
                self.image_canvas.configure(cursor="")
            except Exception:
                pass

            return "break"
        

        # Menu action wrappers
        def _show_original_image_action():
            self._clear_image_display_selection(window_id)
            self.show_original_image(window_id)

        def _color_mapping_action():
            self._clear_image_display_selection(window_id)
            self.color_mapping(window_id)

        def _color_mapping_all_action():
            self._clear_image_display_selection(window_id)
            self.color_mapping_all(window_id)

        # Close window
        def close_window(event):
            """Close the floating window and remove all associated data and canvas items."""
            controller = getattr(self, "_full_resolution_workspace_controller", None)
            if controller is not None and controller.source_window_id == window_id:
                controller.close()


            # Prevent closing while a job is running
            if self._has_active_job(window_id):
                confirm = messagebox.askyesno(
                    "Cancel Process",
                    "A process is running for this image.\n\nDo you want to cancel it and close the window?"
                )
                if not confirm:
                    return "break"

                self._cancel_window_job(window_id)

            try:
                self._disable_original_rectangle_sampling(window_id)
            except Exception:
                pass

            self.image_canvas.delete(window_id)

            for attr_name in (
                "floating_images",
                "pil_images_original",
                "floating_window_state",
                "images",
                "display_pil",
                "original_images",
                "image_dimensions",
                "original_image_dimensions",
                "_resize_callbacks",
                "_pixel_click_callbacks",
                "current_protos",
                "load_images_names",
                "window_image_key",
                "window_mapping_mode",
                "image_view_source",
                "image_view_state",
                "_image_zoom_callbacks",
                "CAN_APPLY_MAPPING",
                "SHOW_ORIGINAL",
                "modified_image",
                "mapping_locked_until_original",
            ):
                if hasattr(self, attr_name):
                    d = getattr(self, attr_name)
                    if isinstance(d, dict) and window_id in d:
                        del d[window_id]

            if getattr(self, "_image_zoom_hover_window", None) == window_id:
                self._image_zoom_hover_window = None
            pan_state = getattr(self, "_image_view_pan_state", None)
            if isinstance(pan_state, dict) and pan_state.get("window_id") == window_id:
                self._image_view_pan_state = None

            if hasattr(self, "proto_options") and window_id in self.proto_options:
                info = self.proto_options.get(window_id)
                if info:
                    frame = info.get("frame")
                    canvas_item = info.get("canvas_item")

                    try:
                        if canvas_item:
                            self.image_canvas.delete(canvas_item)
                    except Exception:
                        pass

                    try:
                        if frame and frame.winfo_exists():
                            frame.destroy()
                    except Exception:
                        pass

                    del self.proto_options[window_id]

            if getattr(self, "_image_workspace_focus_id", None) == window_id:
                self._image_workspace_focus_id = None
                self._image_workspace_focus_saved_state = None
                self._image_workspace_focus_saved_collapsed = None
            try:
                getattr(self, "_mapping_all_palette_by_window", {}).pop(window_id, None)
                getattr(self, "_mapping_all_pack_by_window", {}).pop(window_id, None)
            except Exception:
                pass

            if getattr(self, "_image_workspace_active_id", None) == window_id:
                remaining = self._image_workspace_window_ids()
                self._image_workspace_active_id = remaining[0] if remaining else None

            try:
                self._image_workspace_callbacks.pop(window_id, None)
            except Exception:
                pass

            self._schedule_image_workspace_reflow()

        # Dropdown menu
        def show_menu_image(event):
            """Display per-image view, mapping, zoom and save actions."""
            if self._has_active_job(window_id):
                return "break"

            menu = Menu(self.root, tearoff=0)
            is_focus = getattr(self, "_image_workspace_focus_id", None) == window_id
            current_mode = getattr(self, "window_mapping_mode", {}).get(window_id)
            mapping_enabled = bool(getattr(self, "COLOR_SPACE", False))

            # Focus is enter-only. While Focus View is active, Grid is the
            # single, predictable way back to the multi-image workspace.
            menu.add_command(
                label="Focus Image",
                state=DISABLED if is_focus else NORMAL,
                command=lambda: self._set_image_workspace_focus(window_id)
            )
            menu.add_command(
                label="Open in Image Workspace (Original Resolution)",
                command=lambda: self.open_full_resolution_image_workspace(window_id)
            )

            menu.add_separator()

            # These three are direct view modes. Mapping computations always
            # use pil_images_original, so changing mode never needs an explicit
            # intermediate return to Original Image.
            menu.add_command(
                label="Original Image",
                state=DISABLED if current_mode is None else NORMAL,
                command=_show_original_image_action
            )
            menu.add_command(
                label="Color Mapping",
                state=DISABLED if (not mapping_enabled or current_mode == "single") else NORMAL,
                command=_color_mapping_action
            )
            old_mapping_locked = bool(
                getattr(self, "mapping_locked_until_original", {}).get(window_id, False)
            )
            menu.add_command(
                label="Color Mapping All",
                state=DISABLED if (
                    not mapping_enabled or (current_mode == "all" and not old_mapping_locked)
                ) else NORMAL,
                command=_color_mapping_all_action
            )

            menu.add_separator()

            zoom_menu = Menu(menu, tearoff=0)
            zoom_menu.add_command(
                label="Zoom In",
                command=lambda: _apply_zoom(window_id, factor=1.15)
            )
            zoom_menu.add_command(
                label="Zoom Out",
                command=lambda: _apply_zoom(window_id, factor=1 / 1.15)
            )
            zoom_menu.add_command(
                label="Fit",
                command=lambda: _apply_zoom(window_id, reset=True)
            )
            menu.add_cascade(label="Zoom", menu=zoom_menu)

            menu.add_separator()
            menu.add_command(
                label="Save Image",
                command=lambda: self.save_image(window_id=window_id)
            )

            menu.post(event.x_root, event.y_root)
            return "break"

        # Move window
        def start_move(event):
            if self._has_active_job(window_id):
                return "break"
            if getattr(self, "_image_workspace_focus_id", None) is not None:
                return "break"

            self._set_image_workspace_active(window_id)

            self._clear_image_display_selection(window_id)

            mx = self.image_canvas.canvasx(event.x)
            my = self.image_canvas.canvasy(event.y)
            self._image_workspace_move_state = {
                "window_id": window_id,
                "x": mx,
                "y": my,
                "start_x": mx,
                "start_y": my,
                "moved": False,
            }
            return "break"

        def move_window(event):
            if self._has_active_job(window_id):
                return "break"

            move_state = getattr(self, "_image_workspace_move_state", None)
            if not isinstance(move_state, dict) or move_state.get("window_id") != window_id:
                return "break"

            mx = self.image_canvas.canvasx(event.x)
            my = self.image_canvas.canvasy(event.y)

            # A simple click/double-click must not turn Grid into Manual. Only
            # an actual drag changes the workspace layout mode.
            if not move_state.get("moved", False):
                total_dx = mx - move_state["start_x"]
                total_dy = my - move_state["start_y"]
                if abs(total_dx) < 3 and abs(total_dy) < 3:
                    return "break"
                self._set_image_workspace_manual()
                move_state["moved"] = True

            dx = mx - move_state["x"]
            dy = my - move_state["y"]

            st = self.floating_window_state[window_id]
            st["x"] = max(6, st["x"] + dx)
            st["y"] = max(6, st["y"] + dy)

            _relayout(window_id)
            self._update_manual_workspace_scrollregion()

            move_state["x"] = mx
            move_state["y"] = my
            return "break"

        def end_move(_event):
            move_state = getattr(self, "_image_workspace_move_state", None)
            if isinstance(move_state, dict) and move_state.get("window_id") == window_id:
                self._image_workspace_move_state = None
            self._update_manual_workspace_scrollregion()
            return "break"

        # Resize window
        def start_resize(event):
            if self._has_active_job(window_id):
                return "break"
            if getattr(self, "_image_workspace_focus_id", None) is not None:
                return "break"

            self._set_image_workspace_active(window_id)
            self._set_image_workspace_manual()

            self._clear_image_display_selection(window_id)

            st = self.floating_window_state[window_id]
            self._resize_start = {
                "w": st["w"],
                "h": st["h"],
                "mx": self.image_canvas.canvasx(event.x),
                "my": self.image_canvas.canvasy(event.y)
            }

        def do_resize(event):
            if self._has_active_job(window_id):
                return "break"

            if not hasattr(self, "_resize_start") or self._resize_start is None:
                return "break"

            mx = self.image_canvas.canvasx(event.x)
            my = self.image_canvas.canvasy(event.y)

            start = self._resize_start
            dw = mx - start["mx"]
            dh = my - start["my"]

            desired_w = max(30, int(start["w"] + dw))
            desired_h = max(30, int(start["h"] + dh))

            _update_image_to_size(
                window_id,
                desired_w,
                desired_h,
                reset_view=True
            )
            return "break"

        def end_resize(event):
            """
            Finish resizing.

            Important:
            - We do NOT clear persistent caches here.
            - Cache keys already include (width, height), so a resize naturally
            leads to a different cache entry when needed.
            """
            if self._has_active_job(window_id):
                return "break"

            self._cancel_window_job(window_id)
            self._resize_start = None
            self._update_manual_workspace_scrollregion()

            try:
                self._clear_original_selection_rectangle(window_id)
            except Exception:
                pass

            try:
                self.image_canvas.itemconfig(f"{window_id}_pct_text", text="")
            except Exception:
                pass

            return "break"

        if not hasattr(self, "_resize_callbacks"):
            self._resize_callbacks = {}
        self._resize_callbacks[window_id] = (start_resize, do_resize, end_resize)

        # Pixel picking
        def get_pixel_value(event, window_id=window_id):
            if self._has_active_job(window_id):
                return "break"

            self._set_image_workspace_active(window_id)

            point_info = _canvas_point_to_original_image(event, window_id)
            if point_info is None:
                return "break"

            x_original, y_original, _rel_x, _rel_y = point_info

            pil_original = self.pil_images_original[window_id]
            ow, oh = pil_original.size

            x_original = int(_clamp(x_original, 0, ow - 1))
            y_original = int(_clamp(y_original, 0, oh - 1))

            pixel_value = pil_original.getpixel((x_original, y_original))

            # If image has transparency, ignore fully transparent pixels
            if len(pixel_value) == 4:
                r, g, b, a = pixel_value

                if a == 0:
                    return "break"

                pixel_rgb = (r, g, b)
            else:
                pixel_rgb = pixel_value

            pixel_lab = UtilsTools.rgb_to_lab(pixel_rgb)

            if self.COLOR_SPACE:
                self.display_pixel_value(
                    x_original,
                    y_original,
                    pixel_lab,
                    is_average=False,
                    image_id=window_id
                )

            return "break"

        if not hasattr(self, "_pixel_click_callbacks"):
            self._pixel_click_callbacks = {}
        self._pixel_click_callbacks[window_id] = get_pixel_value

        # Bindings
        # Title drag restores the original ability to move cards. The first drag
        # switches the workspace from automatic Grid to Manual layout. Grid can
        # be pressed at any time to arrange everything again.
        for title_tag in (f"{window_id}_title", f"{window_id}_title_text"):
            self.image_canvas.tag_bind(title_tag, "<Button-1>", start_move)
            self.image_canvas.tag_bind(title_tag, "<B1-Motion>", move_window)
            self.image_canvas.tag_bind(title_tag, "<ButtonRelease-1>", end_move)
            self.image_canvas.tag_bind(
                title_tag,
                "<Double-Button-1>",
                lambda _e, wid=window_id: self._toggle_image_workspace_focus(wid),
            )

        self.image_canvas.tag_bind(f"{window_id}_close_button", "<Button-1>", close_window)
        self.image_canvas.tag_bind(
            f"{window_id}_minimize_button",
            "<Button-1>",
            lambda _e, wid=window_id: self._toggle_image_card_minimize(wid),
        )
        self.image_canvas.tag_bind(f"{window_id}_click_image", "<Button-1>", get_pixel_value)
        self.image_canvas.tag_bind(f"{window_id}_arrow_button", "<Button-1>", show_menu_image)

        # Right-drag moves only the internal zoom viewport. It never moves the
        # image card itself; card movement remains a left-drag on the title bar.
        for button_num in (2, 3):
            self.image_canvas.tag_bind(
                f"{window_id}_click_image", f"<ButtonPress-{button_num}>", _start_view_pan
            )
            self.image_canvas.tag_bind(
                f"{window_id}_click_image", f"<B{button_num}-Motion>", _drag_view_pan
            )
            self.image_canvas.tag_bind(
                f"{window_id}_click_image", f"<ButtonRelease-{button_num}>", _end_view_pan
            )

        # Mouse hover target for wheel zoom.
        # Canvas.tag_bind() does not support <MouseWheel>, so wheel dispatch is
        # bound directly to image_canvas and routed to the hovered image tag.
        self.image_canvas.tag_bind(
            f"{window_id}_click_image",
            "<Enter>",
            _activate_image_zoom
        )

        self.image_canvas.tag_bind(
            f"{window_id}_click_image",
            "<Leave>",
            _deactivate_image_zoom
        )

        self._image_zoom_callbacks[window_id] = {
            "wheel": _zoom_mousewheel,
            "linux_up": _zoom_linux_in,
            "linux_down": _zoom_linux_out,
        }

        self.image_canvas.tag_bind(f"{window_id}_resize_handle", "<Button-1>", start_resize)
        self.image_canvas.tag_bind(f"{window_id}_resize_handle", "<B1-Motion>", do_resize)
        self.image_canvas.tag_bind(f"{window_id}_resize_handle", "<ButtonRelease-1>", end_resize)

        self._image_workspace_callbacks[window_id] = {
            "relayout": _relayout,
            "resize": _update_image_to_size,
        }

        _relayout(window_id)

        try:
            self._enable_original_rectangle_sampling(
                window_id=window_id,
                target_w=new_width,
                target_h=new_height
            )
        except Exception as e:
            print(f"Warning enabling original rectangle sampling for {window_id}: {e}")

        self._set_image_workspace_active(window_id)
        self._schedule_image_workspace_reflow(delay=0)


    def _ensure_image_jobs(self):
        """Lazy-init job registry used to bind one running process per image/window."""
        if not hasattr(self, "image_jobs"):
            self.image_jobs = {}
        if not hasattr(self, "_image_job_counter"):
            self._image_job_counter = itertools.count(1)


    def _window_exists(self, window_id):
        """Returns True if the floating window still exists on the canvas."""
        try:
            items = self.image_canvas.find_withtag(window_id)
            return bool(items)
        except Exception:
            return False


    def _has_active_job(self, window_id):
        """Returns True if there is an active job for this image."""
        self._ensure_image_jobs()
        info = self.image_jobs.get(window_id)
        if not info:
            return False

        th = info.get("thread")
        cancel_event = info.get("cancel_event")
        return th is not None and th.is_alive() and cancel_event is not None and not cancel_event.is_set()


    def _is_current_job(self, window_id, job_id):
        """Checks whether job_id is still the active job for window_id."""
        self._ensure_image_jobs()
        info = self.image_jobs.get(window_id)
        return bool(info and info.get("job_id") == job_id)


    def _cancel_window_job(self, window_id, cleanup_ui=True):
        """Cancels the active job associated with a floating image/window."""
        self._ensure_image_jobs()
        info = self.image_jobs.get(window_id)
        if not info:
            return

        try:
            info["cancel_event"].set()
        except Exception:
            pass

        # Restore menu state because the image remains in its previous/original state
        try:
            self.CAN_APPLY_MAPPING[window_id] = True
            self.SHOW_ORIGINAL[window_id] = False
        except Exception:
            pass

        if cleanup_ui:
            self._hide_window_loading(window_id)


    def _is_job_cancelled(self, window_id, cancel_event, job_id):
        """Worker-safe cancellation check; never query Tk widgets here.

        Closing/replacing an image sets its cancel_event on the UI thread.
        Checking the job ID also prevents obsolete results from being applied.
        """
        if cancel_event.is_set():
            return True
        info = getattr(self, "image_jobs", {}).get(window_id)
        return info is None or info.get("job_id") != job_id


    def _start_window_job(self, window_id, kind, target):
        """
        Starts a thread-bound job associated with one image/window.
        Only one job can run at a time per window_id.
        """
        self._ensure_image_jobs()

        if self._has_active_job(window_id):
            self.custom_warning(
                "Process Running",
                f"A '{self.image_jobs[window_id]['kind']}' process is already running for this image."
            )
            return None

        cancel_event = threading.Event()
        job_id = next(self._image_job_counter)

        self.image_jobs[window_id] = {
            "thread": None,
            "cancel_event": cancel_event,
            "job_id": job_id,
            "kind": kind,
            "loading_widgets": {}
        }

        def runner():
            try:
                target(cancel_event, job_id)
            except Exception as e:
                error_msg = str(e)

                def _ui_error(msg=error_msg):
                    self.custom_warning("Process Error", f"Unexpected error: {msg}")

                try:
                    self.image_canvas.after(0, _ui_error)
                except Exception:
                    pass
            finally:
                def _cleanup():
                    info = self.image_jobs.get(window_id)
                    if info and info.get("job_id") == job_id:
                        self._hide_window_loading(window_id)
                        self.image_jobs.pop(window_id, None)

                try:
                    self.image_canvas.after(0, _cleanup)
                except Exception:
                    pass

        th = threading.Thread(target=runner, daemon=True)
        self.image_jobs[window_id]["thread"] = th
        th.start()

        return job_id


    def _raise_all_loading_panels(self):
        """
        Keep every visible loading panel above floating windows and legend panels.

        This prevents a running job's loading overlay from disappearing when another
        floating window is moved, focused, or closed.
        """
        self._ensure_image_jobs()

        for window_id, info in self.image_jobs.items():
            widgets = info.get("loading_widgets", {})
            if not widgets:
                continue

            try:
                self.image_canvas.tag_raise(f"{window_id}_loading")
            except Exception:
                pass


    def _show_window_loading(self, window_id, text="Processing..."):
        """Creates a canvas-only loading panel linked to a specific floating image/window."""
        self._ensure_image_jobs()

        self._hide_window_loading(window_id)

        if not hasattr(self, "floating_window_state") or window_id not in self.floating_window_state:
            return

        st = self.floating_window_state[window_id]
        wx, wy, ww, wh = st["x"], st["y"], st["w"], st["h"]

        # Place the loading panel on top of the image area
        IMG_LEFT_PAD = 12
        IMG_TOP_PAD = 44

        panel_w = min(170, max(140, ww - 20))
        panel_h = 95

        panel_x = wx + IMG_LEFT_PAD + max(0, (ww - panel_w) // 2)
        panel_y = wy + IMG_TOP_PAD + max(0, (wh - panel_h) // 2)

        tags = (window_id, f"{window_id}_loading", "loading")

        # Background panel
        bg = self.image_canvas.create_rectangle(
            panel_x, panel_y, panel_x + panel_w, panel_y + panel_h,
            fill="white", outline="black", width=1,
            tags=tags
        )

        # Title
        title = self.image_canvas.create_text(
            panel_x + panel_w / 2,
            panel_y + 20,
            text=text,
            fill="black",
            font=("Sans", 12, "bold"),
            tags=tags
        )

        # Progress text
        progress = self.image_canvas.create_text(
            panel_x + panel_w / 2,
            panel_y + 50,
            text="0.0%",
            fill="black",
            font=("Sans", 10),
            tags=(window_id, f"{window_id}_loading", "loading", f"{window_id}_loading_progress")
        )

        # Cancel button background
        btn_w = panel_w - 20
        btn_h = 18
        btn_x1 = panel_x + 10
        btn_y1 = panel_y + panel_h - 28
        btn_x2 = btn_x1 + btn_w
        btn_y2 = btn_y1 + btn_h

        cancel_bg = self.image_canvas.create_rectangle(
            btn_x1, btn_y1, btn_x2, btn_y2,
            fill="#e6e6e6", outline="gray",
            tags=(window_id, f"{window_id}_loading", "loading", f"{window_id}_loading_cancel")
        )

        cancel_txt = self.image_canvas.create_text(
            (btn_x1 + btn_x2) / 2,
            (btn_y1 + btn_y2) / 2,
            text="Cancel",
            fill="black",
            font=("Sans", 10),
            tags=(window_id, f"{window_id}_loading", "loading", f"{window_id}_loading_cancel")
        )

        # A cancelled Mapping All must not leave the image in an unfinished view mode.
        def _cancel_loading_job(_event=None):
            info = self.image_jobs.get(window_id, {})
            if info.get("kind") == "color_mapping_all":
                self.show_original_image(window_id)
            else:
                self._cancel_window_job(window_id)

        self.image_canvas.tag_bind(
            f"{window_id}_loading_cancel",
            "<Button-1>",
            _cancel_loading_job
        )

        if window_id in self.image_jobs:
            self.image_jobs[window_id]["loading_widgets"] = {
                "bg": bg,
                "title": title,
                "progress": progress,
                "cancel_bg": cancel_bg,
                "cancel_txt": cancel_txt,
                "panel_w": panel_w,
                "panel_h": panel_h,
            }

        # Ensure all visible loading panels remain above floating windows
        self._raise_all_loading_panels()


    def _hide_window_loading(self, window_id):
        """Destroys the loading panel associated with one floating image/window."""
        self._ensure_image_jobs()

        info = self.image_jobs.get(window_id)
        if not info:
            return

        try:
            self.image_canvas.delete(f"{window_id}_loading")
        except Exception:
            pass

        info["loading_widgets"] = {}


    def _update_window_progress(self, window_id, job_id, current_step, total_steps):
        """Updates the per-window loading progress safely from background threads."""
        if total_steps <= 0:
            return

        pct = (current_step / total_steps) * 100.0

        def _ui():
            if not self._is_current_job(window_id, job_id):
                return

            try:
                self.image_canvas.itemconfig(f"{window_id}_loading_progress", text=f"{pct:.1f}%")
            except Exception:
                pass

        try:
            self.image_canvas.after(0, _ui)
        except Exception:
            pass


    def _reposition_window_loading(self, window_id):
        """Repositions the loading panel so it stays centered over the image."""
        self._ensure_image_jobs()

        info = self.image_jobs.get(window_id)
        if not info:
            return

        widgets = info.get("loading_widgets", {})
        if not widgets:
            return

        if not hasattr(self, "floating_window_state") or window_id not in self.floating_window_state:
            return

        st = self.floating_window_state[window_id]
        wx, wy, ww, wh = st["x"], st["y"], st["w"], st["h"]

        IMG_LEFT_PAD = 12
        IMG_TOP_PAD = 44

        panel_w = min(170, max(140, ww - 20))
        panel_h = 95

        panel_x = wx + IMG_LEFT_PAD + max(0, (ww - panel_w) // 2)
        panel_y = wy + IMG_TOP_PAD + max(0, (wh - panel_h) // 2)

        btn_w = panel_w - 20
        btn_h = 18
        btn_x1 = panel_x + 10
        btn_y1 = panel_y + panel_h - 28
        btn_x2 = btn_x1 + btn_w
        btn_y2 = btn_y1 + btn_h

        try:
            self.image_canvas.coords(
                widgets["bg"],
                panel_x, panel_y, panel_x + panel_w, panel_y + panel_h
            )
            self.image_canvas.coords(
                widgets["title"],
                panel_x + panel_w / 2, panel_y + 20
            )
            self.image_canvas.coords(
                widgets["progress"],
                panel_x + panel_w / 2, panel_y + 50
            )
            self.image_canvas.coords(
                widgets["cancel_bg"],
                btn_x1, btn_y1, btn_x2, btn_y2
            )
            self.image_canvas.coords(
                widgets["cancel_txt"],
                (btn_x1 + btn_x2) / 2, (btn_y1 + btn_y2) / 2
            )

            # Keep it visible above other windows
            self.image_canvas.tag_raise(f"{window_id}_loading")

        except Exception:
            pass


    def _has_any_active_job(self):
        """Returns True if there is any running job in any image/window."""
        self._ensure_image_jobs()

        if (getattr(self, "_threshold_job_running", False)
                or getattr(self, "_processing_job_running", False)
                or getattr(self, "_loading_color_space_running", False)
                or getattr(self, "_model_rebuild_running", False)):
            return True

        # Full-resolution mapping/export runs on a separate worker.
        # Do not replace the shared FCS or its T-conorm while that worker
        # is evaluating or exporting the previous space.
        workspace = getattr(self, "_full_resolution_workspace_controller", None)
        if workspace is not None and not getattr(workspace, "_closed", True):
            worker = getattr(workspace, "_worker", None)
            if getattr(workspace, "_mapping_busy", False) or getattr(workspace, "_saving", False):
                return True
            if worker is not None and worker.is_alive():
                return True

        for info in self.image_jobs.values():
            th = info.get("thread")
            cancel_event = info.get("cancel_event")
            if th is not None and th.is_alive() and cancel_event is not None and not cancel_event.is_set():
                return True
        return False


    def _reposition_proto_options(self, window_id):
        """
        Keep the mapping selector/legend directly BELOW its image.

        The panel is drawn with native Canvas primitives and shares the same
        ``window_id`` tag as the image card, so it moves, minimizes, focuses
        and participates in z-order as part of the same visual object.
        """
        info = getattr(self, "proto_options", {}).get(window_id)
        if not isinstance(info, dict):
            return

        st = getattr(self, "floating_window_state", {}).get(window_id)
        if not st:
            return

        wx, wy, ww, wh = st["x"], st["y"], st["w"], st["h"]
        img_left_pad = 12
        img_top_pad = 44

        # Reserve room for the percentage/status line only when it actually
        # contains text. In the neutral Color Mapping state this keeps the
        # selector much closer to the image instead of leaving a blank band.
        pct_text = ""
        try:
            pct_items = self.image_canvas.find_withtag(f"{window_id}_pct_text")
            if pct_items:
                pct_text = str(self.image_canvas.itemcget(pct_items[0], "text") or "").strip()
        except Exception:
            pct_text = ""

        # Keep the percentage as a compact caption between image and panel.
        # The gap is deliberately small so resizing the image does not create
        # a large white band inside the card.
        panel_gap = 21 if pct_text else 7
        info["gap"] = panel_gap
        panel_y = wy + img_top_pad + wh + panel_gap

        # Keep the selector slightly narrower than the image and centered.
        # The minimum still leaves enough room for normal prototype names.
        available_w = max(150, int(ww) - 24)
        preferred_w = max(145, int(round(float(ww) * 0.74)))
        panel_w = min(285, available_w, preferred_w)
        panel_x = wx + img_left_pad + max(0, (int(ww) - panel_w) // 2)
        panel_h = self._workspace_legend_height(window_id)

        old_x = info.get("x")
        old_y = info.get("y")
        old_w = info.get("width")
        old_h = info.get("height")

        # Width/height changes alter text space and the number of visible rows,
        # therefore redraw instead of only translating existing Canvas items.
        if (
            old_x is None
            or old_y is None
            or old_w != panel_w
            or old_h != panel_h
        ):
            info["x"] = panel_x
            info["y"] = panel_y
            info["width"] = panel_w
            info["height"] = panel_h
            self._render_proto_options(window_id)
            return

        dx = panel_x - old_x
        dy = panel_y - old_y
        if dx or dy:
            try:
                self.image_canvas.move(f"{window_id}_legend", dx, dy)
            except Exception:
                pass
            info["x"] = panel_x
            info["y"] = panel_y


    def _focus_floating_window(self, window_id):
        """Bring one complete image card, including its mapping panel, to the front."""
        try:
            # All pieces, including the legend, are native Canvas items carrying
            # the same window_id tag, so they really move through one z-order.
            self.image_canvas.tag_raise(window_id)
            self._raise_all_loading_panels()
        except Exception:
            pass





















    # ============================================================================================================================================================
    #  FUNCTIONS IMAGE UTILS
    # ============================================================================================================================================================
    def _get_mapping_source_image(self, window_id, target_size=None):
        """
        Return an original-image-derived PIL image for mapping computation.

        ``self.images[window_id]`` is the current DISPLAY image and may already
        contain a grayscale Color Mapping, a Color Mapping All result, or a
        zoomed/resized representation. It must therefore never be used as the
        source for a new membership calculation.

        Mapping caches remain keyed by the stable image file identity, current
        color space and processing size; closing/reopening a file can reuse
        valid cached results, while a prototype that was never calculated is
        still computed from the original image.
        """
        originals = getattr(self, "pil_images_original", {}) or {}
        original = originals.get(window_id)
        if original is None:
            raise ValueError("Original image is not available for mapping.")

        if target_size is None:
            target_size = getattr(self, "image_dimensions", {}).get(window_id)

        if target_size is None:
            return original.copy()

        try:
            width = max(1, int(target_size[0]))
            height = max(1, int(target_size[1]))
        except Exception:
            return original.copy()

        if original.size == (width, height):
            return original.copy()

        return original.resize((width, height), Image.Resampling.LANCZOS)


    def _destroy_proto_options(self, window_id):
        """Destroy and unregister the canvas-native mapping panel for one image."""
        self.proto_options = getattr(self, "proto_options", {})
        self.proto_options.pop(window_id, None)
        try:
            self.image_canvas.delete(f"{window_id}_legend")
        except Exception:
            pass


    @staticmethod
    def _legend_display_name(name, max_chars=22):
        text = str(name)
        if len(text) <= max_chars:
            return text
        return text[:max(1, max_chars - 1)] + "…"


    def _mapping_category_rows(self, space, expanded, *, include_granules=True):
        """Category/granule descriptors shared by atomic and granular spaces."""
        rows = []
        granular = bool(getattr(space, "is_granular", False))
        flat = (space.get_all_prototypes() if granular else space.prototypes)
        flat_rgb = self.image_manager.build_original_palette_uint8(
            flat, space.color_space)
        offset = 0
        for category_index, cat_proto in enumerate(space.prototypes):
            granules = (space.categories[category_index].prototypes if granular
                        else [cat_proto])
            count = len(granules)
            swatches = flat_rgb[offset:offset + count]
            rows.append({
                "type": "category", "name": str(cat_proto.label),
                "category": category_index, "count": count,
                "swatches": swatches, "rgb": tuple(int(c) for c in swatches[0]),
                "selection": ("category", category_index),
            })
            if include_granules and count > 1 and category_index in expanded:
                for index, proto in enumerate(granules):
                    rows.append({
                        "type": "granule", "name": str(proto.label),
                        "category": category_index, "granule": index,
                        "rgb": tuple(int(c) for c in swatches[index]),
                        "selection": ("granule", category_index, index),
                    })
            offset += count
        return rows

    def _refresh_single_mapping_rows(self, window_id):
        info = getattr(self, "proto_options", {}).get(window_id)
        space = getattr(self, "fuzzy_color_space", None)
        if not isinstance(info, dict) or info.get("kind") != "single" or space is None:
            return
        info["rows"] = self._mapping_category_rows(
            space, info.setdefault("expanded_categories", set()))

    def _refresh_mapping_all_legend_rows(self, window_id):
        info = getattr(self, "proto_options", {}).get(window_id)
        pack = getattr(self, "_mapping_all_pack_by_window", {}).get(window_id)
        space = getattr(self, "fuzzy_color_space", None)
        if not isinstance(info, dict) or info.get("kind") != "all" or not pack or space is None:
            return
        level = pack.get("level", "categories")
        palette = np.asarray(pack["palettes"][pack["scheme"]], dtype=np.uint8)
        rows = []
        expanded = info.setdefault("expanded_categories", set())
        if level == "categories":
            for i, proto in enumerate(space.prototypes):
                rows.append({"type": "color", "name": proto.label,
                             "rgb": tuple(int(v) for v in palette[i]),
                             "export_name": proto.label})
        else:
            granular = bool(getattr(space, "is_granular", False))
            index = 0
            for category_index, proto in enumerate(space.prototypes):
                granules = (space.categories[category_index].prototypes if granular
                            else [proto])
                count = len(granules)
                if count > 1:
                    rows.append({"type": "group", "name": proto.label,
                                 "category": category_index, "count": count,
                                 "swatches": palette[index:index + count]})
                if count == 1 or category_index in expanded:
                    for local_i, granule in enumerate(granules):
                        rows.append({
                            "type": "color", "name": str(granule.label),
                            "category": category_index, "indent": count > 1,
                            "rgb": tuple(int(v) for v in palette[index + local_i]),
                            "export_name": (f"{proto.label} / {granule.label}"
                                            if count > 1 else proto.label),
                        })
                index += count
        if not space.covering and np.any(
            (np.asarray(pack["label_map"]) < 0) &
            (np.asarray(pack["alpha_values"]) > 0)):
            rows.append({"type": "unassigned", "name": "Unassigned (original)",
                         "rgb": (220, 220, 220),
                         "export_name": "Unassigned (original)"})
        info["rows"] = rows
        info["level"] = level

    def _toggle_mapping_legend_category(self, window_id, category_index):
        info = getattr(self, "proto_options", {}).get(window_id)
        if not isinstance(info, dict):
            return "break"
        expanded = info.setdefault("expanded_categories", set())
        if category_index in expanded:
            expanded.discard(category_index)
        else:
            expanded.add(category_index)
        if info.get("kind") == "single":
            self._refresh_single_mapping_rows(window_id)
        else:
            self._refresh_mapping_all_legend_rows(window_id)
        self._reposition_proto_options(window_id)
        self._render_proto_options(window_id)
        self._schedule_image_workspace_reflow()
        return "break"

    def _scroll_proto_options(self, window_id, delta):
        info = getattr(self, "proto_options", {}).get(window_id)
        if not isinstance(info, dict):
            return "break"
        total = len(info.get("rows", []))
        visible = max(1, int(info.get("visible_rows", 1)))
        info["scroll_index"] = max(0, min(max(0, total - visible),
                                           int(info.get("scroll_index", 0)) + int(delta)))
        self._render_proto_options(window_id)
        return "break"

    def _set_single_mapping_style(self, window_id, style):
        """Switch grayscale/weighted RGB without recomputing membership."""
        if style not in ("gray", "color") or self._has_active_job(window_id):
            return "break"
        info = getattr(self, "proto_options", {}).get(window_id)
        if not isinstance(info, dict) or info.get("kind") != "single":
            return "break"
        if info.get("display_style", "gray") == style:
            return "break"
        info["display_style"] = style
        self._render_proto_options(window_id)
        selected = info.get("selection")
        if selected is not None and info.get("displayed_for") == selected:
            gray = getattr(self, "modified_image", {}).get(window_id)
            if isinstance(gray, np.ndarray) and gray.ndim == 2:
                self.display_color_mapping(gray, window_id)
        return "break"

    def _select_mapping_item(self, window_id, selection):
        if self._has_active_job(window_id):
            return "break"
        info = getattr(self, "proto_options", {}).get(window_id)
        if not isinstance(info, dict) or info.get("kind") != "single":
            return "break"
        info["selection"] = tuple(selection)
        for row in info.get("rows", []):
            if row.get("selection") == info["selection"]:
                current = getattr(self, "current_protos", {}).get(window_id)
                if current is not None:
                    current.set(row["name"])
                break
        self._render_proto_options(window_id)
        self.get_proto_percentage(window_id)
        return "break"

    def _select_proto_from_legend(self, window_id, color_name):
        """Keep compatibility with the old category-name selection callback."""
        space = getattr(self, "fuzzy_color_space", None)
        if space is not None:
            for i, proto in enumerate(space.prototypes):
                if str(proto.label) == str(color_name):
                    return self._select_mapping_item(window_id, ("category", i))
        return "break"

    def _jump_proto_options_scroll(self, window_id, event, track_top, track_height):
        info = getattr(self, "proto_options", {}).get(window_id)
        if not isinstance(info, dict):
            return "break"
        visible = max(1, int(info.get("visible_rows", 1)))
        max_offset = max(0, len(info.get("rows", [])) - visible)
        if max_offset <= 0:
            return "break"
        y = float(self.image_canvas.canvasy(event.y))
        ratio = max(0.0, min(1.0, (y - float(track_top)) / max(1.0, float(track_height))))
        info["scroll_index"] = int(round(ratio * max_offset))
        self._render_proto_options(window_id)
        return "break"

    def _render_proto_options(self, window_id):
        """Compact native-canvas category/granule selector and Mapping All legend."""
        info = getattr(self, "proto_options", {}).get(window_id)
        st = getattr(self, "floating_window_state", {}).get(window_id)
        if not isinstance(info, dict) or not st:
            return
        try:
            self.image_canvas.delete(f"{window_id}_legend")
        except Exception:
            pass
        x = float(info.get("x", st["x"] + 12))
        y = float(info.get("y", st["y"] + 44 + st["h"] + info.get("gap", 7)))
        w = int(info.get("width", max(180, int(st.get("w", 250)))))
        h = int(info.get("height", self._workspace_legend_height(window_id)))
        kind = info.get("kind", "single")
        rows = list(info.get("rows", []))
        tag = f"{window_id}_legend"
        common = (window_id, "floating", tag, "legend")
        self.image_canvas.create_rectangle(x, y, x + w, y + h,
            fill="white", outline="#2f2f2f", width=1, tags=common)
        footer_h = 66 if kind == "all" else 40
        row_h = 24
        top = y + 5
        bottom = y + h - footer_h - 4
        visible_rows = max(1, int((bottom - top) // row_h))
        info["visible_rows"] = visible_rows
        scroll = max(0, min(int(info.get("scroll_index", 0)),
                            max(0, len(rows) - visible_rows)))
        info["scroll_index"] = scroll
        right = x + w - 15
        expanded = info.get("expanded_categories", set())
        for offset, row in enumerate(rows[scroll:scroll + visible_rows]):
            n = scroll + offset
            y1 = top + offset * row_h
            y2 = y1 + row_h - 3
            cy = (y1 + y2) / 2
            row_tag = f"{tag}_row_{n}"
            selected = kind == "single" and row.get("selection") == info.get("selection")
            self.image_canvas.create_rectangle(
                x + 3, y1, right, y2,
                fill=UtilsTools.UI_ACCENT_SOFT if selected else "#ffffff",
                outline="", tags=common + (row_tag,))
            indent = row.get("type") == "granule" or row.get("indent", False)
            left = x + (28 if indent else 8)
            if kind == "single":
                self.image_canvas.create_oval(left, cy - 4.5, left + 9, cy + 4.5,
                    fill="#ffffff", outline="#60646e", width=1, tags=common + (row_tag,))
                if selected:
                    self.image_canvas.create_oval(left + 2.5, cy - 2, left + 6.5, cy + 2,
                        fill=UtilsTools.UI_ACCENT_DARK, outline="", tags=common + (row_tag,))
                left += 13
            if row.get("type") in ("category", "group") and row.get("count", 1) > 1:
                swatches = list(row.get("swatches", []))[:3]
                for index, rgb in enumerate(swatches):
                    rgb = np.asarray(rgb, dtype=int)
                    hx = "#{:02x}{:02x}{:02x}".format(*rgb[:3])
                    x1 = left + index * 5
                    self.image_canvas.create_rectangle(x1, cy - 5, x1 + 5, cy + 5,
                        fill=hx, outline="", tags=common + (row_tag,))
                left += 19
            else:
                rgb = np.asarray(row.get("rgb", (210, 210, 210)), dtype=int)
                hx = "#{:02x}{:02x}{:02x}".format(*rgb[:3])
                self.image_canvas.create_rectangle(left, cy - 5, left + 11, cy + 5,
                    fill=hx, outline="", tags=common + (row_tag,))
                left += 14
            expandable = row.get("type") in ("category", "group") and row.get("count", 1) > 1
            end_reserved = 33 if expandable else 4
            available = max(3, int((right - end_reserved - left) // 5.4))
            label = self._legend_display_name(row.get("name", ""), min(24, available))
            self.image_canvas.create_text(left, cy, text=label, anchor="w",
                fill=UtilsTools.UI_ACCENT_DARK if selected else "#1f2937",
                font=("Segoe UI", 8, "bold" if selected else "normal"),
                tags=common + (row_tag,))
            if expandable:
                cat_index = row["category"]
                marker = "▾" if cat_index in expanded else "▸"
                arrow_tag = f"{tag}_expand_{n}"
                self.image_canvas.create_text(right - 18, cy,
                    text=marker, anchor="center", font=("Segoe UI", 9, "bold"),
                    fill=UtilsTools.UI_ACCENT_DARK, tags=common + (arrow_tag,))
                self.image_canvas.tag_bind(arrow_tag, "<Button-1>",
                    lambda _e, wid=window_id, ci=cat_index:
                    self._toggle_mapping_legend_category(wid, ci))
                if kind == "all":
                    self.image_canvas.tag_bind(row_tag, "<Button-1>",
                        lambda _e, wid=window_id, ci=cat_index:
                        self._toggle_mapping_legend_category(wid, ci))
            if kind == "single":
                selection = row.get("selection")
                self.image_canvas.tag_bind(row_tag, "<Button-1>",
                    lambda _e, wid=window_id, item=selection:
                    self._select_mapping_item(wid, item))
        if len(rows) > visible_rows:
            sx1, sx2 = x + w - 11, x + w - 6
            sy1, sy2 = top + 3, max(top + 21, bottom - 3)
            length = sy2 - sy1
            self.image_canvas.create_rectangle(sx1, sy1, sx2, sy2,
                fill="#e7e7e7", outline="#b8b8b8", tags=common)
            fraction = min(1.0, visible_rows / len(rows))
            thumb_h = max(20, length * fraction)
            thumb_y = sy1 + (length - thumb_h) * (
                scroll / max(1, len(rows) - visible_rows))
            self.image_canvas.create_rectangle(sx1 - 1, thumb_y,
                sx2 + 1, thumb_y + thumb_h, fill="#888888", outline="#777777",
                tags=common)
            track_tag = f"{tag}_scroll_track"
            # Add an invisible mouse target over the complete track.
            self.image_canvas.create_rectangle(sx1 - 2, sy1, sx2 + 2, sy2,
                outline="", fill="", tags=common + (track_tag,))
            self.image_canvas.tag_bind(track_tag, "<Button-1>",
                lambda e, wid=window_id, track_y=sy1, track_h=length:
                self._jump_proto_options_scroll(wid, e, track_y, track_h))
        # Segmented controls. Mapping All has two compact rows, each of which
        # recolors an already-computed pair of label maps without membership work.
        def segmented(options, selected_mode, y1, callback):
            y2 = y1 + 24
            half = (w - 14) / len(options)
            for i, (mode, caption) in enumerate(options):
                x1, x2 = x + 7 + i * half, x + 7 + (i + 1) * half
                active = selected_mode == mode
                btag = f"{tag}_button_{y1:.0f}_{mode}"
                self.image_canvas.create_rectangle(x1, y1, x2, y2,
                    fill=UtilsTools.UI_ACCENT_SOFT if active else "#f5f5f5",
                    outline=UtilsTools.UI_ACCENT_MUTED if active else "#b8b8b8",
                    tags=common + (btag,))
                self.image_canvas.create_text((x1 + x2) / 2, (y1 + y2) / 2,
                    text=caption, fill=UtilsTools.UI_ACCENT_DARK if active else "#333333",
                    font=("Segoe UI", 8, "bold" if active else "normal"),
                    tags=common + (btag,))
                self.image_canvas.tag_bind(btag, "<Button-1>",
                    lambda _e, wid=window_id, m=mode: callback(wid, m))
        if kind == "single":
            segmented((("gray", "Grayscale"), ("color", "Color")),
                      info.get("display_style", "gray"), y + h - 34,
                      self._set_single_mapping_style)
        else:
            pack = getattr(self, "_mapping_all_pack_by_window", {}).get(window_id, {})
            segmented((("categories", "Categories"), ("granules", "Granules")),
                      pack.get("level", "categories"), y + h - 61,
                      self._set_mapping_all_level)
            segmented((("original", "Original"), ("alt", "Alt. Colors")),
                      pack.get("scheme", "original"), y + h - 32,
                      self._set_mapping_all_palette)
        self._sync_workspace_card_item_states(window_id)
        self._focus_floating_window(window_id)

    def _create_single_mapping_panel(self, window_id):
        """Create a compact hierarchical selector below the image."""
        self._destroy_proto_options(window_id)
        if not hasattr(self, "current_protos"):
            self.current_protos = {}
        current = self.current_protos.get(window_id)
        if current is None:
            current = tk.StringVar(value="")
            self.current_protos[window_id] = current
        else:
            current.set("")
        try:
            self.image_canvas.itemconfig(f"{window_id}_pct_text", text="")
        except Exception:
            pass
        self.proto_options = getattr(self, "proto_options", {})
        self.proto_options[window_id] = {
            "kind": "single", "rows": [], "selection": None,
            "expanded_categories": set(), "gap": 7, "scroll_index": 0,
            "display_style": "gray", "displayed_for": None,
        }
        self._refresh_single_mapping_rows(window_id)
        self._reposition_proto_options(window_id)
        self._sync_workspace_card_item_states(window_id)
        self._schedule_image_workspace_reflow(delay=0)

    def _create_mapping_all_panel(self, window_id, palette_uint8):
        """Create the active category/granule Mapping All legend."""
        old = getattr(self, "proto_options", {}).get(window_id, {})
        expanded = set(old.get("expanded_categories", set()))
        scroll = int(old.get("scroll_index", 0))
        self._destroy_proto_options(window_id)
        if old.get("kind") != "all":
            space = getattr(self, "fuzzy_color_space", None)
            if getattr(space, "is_granular", False):
                expanded = {i for i, cat in enumerate(space.categories)
                            if len(cat.prototypes) > 1}
        self.proto_options = getattr(self, "proto_options", {})
        self.proto_options[window_id] = {
            "kind": "all", "rows": [], "expanded_categories": expanded,
            "gap": 7, "scroll_index": scroll,
        }
        self._refresh_mapping_all_legend_rows(window_id)
        self._reposition_proto_options(window_id)
        self._sync_workspace_card_item_states(window_id)
        self._schedule_image_workspace_reflow(delay=0)

    def color_mapping(self, window_id):
        """Open Color Mapping directly from Original or Mapping All."""
        if not self.image_canvas.find_withtag(window_id):
            self.custom_warning("No Window", f"No floating window found with id {window_id}")
            return
        if not getattr(self, "COLOR_SPACE", False):
            self.custom_warning("No Color Space", "Load a Fuzzy Color Space before applying Color Mapping.")
            return

        previous_mode = getattr(self, "window_mapping_mode", {}).get(window_id)
        locked = getattr(self, "mapping_locked_until_original", {}).get(window_id, False)

        # Color Mapping starts in a neutral state with no prototype selected.
        # If another mapping is currently displayed (including one belonging to
        # an older FCS), restore the original pixels internally first. This is
        # not a user-visible prerequisite; it simply gives the selector a clean
        # starting image while every later calculation still uses the original.
        if previous_mode == "all" or locked:
            self.show_original_image(window_id)

        if not hasattr(self, "window_mapping_mode"):
            self.window_mapping_mode = {}
        self.window_mapping_mode[window_id] = "single"

        try:
            self._disable_original_rectangle_sampling(window_id)
        except Exception:
            pass

        self.CAN_APPLY_MAPPING[window_id] = False
        self.SHOW_ORIGINAL[window_id] = True
        self._set_image_workspace_active(window_id)
        self._create_single_mapping_panel(window_id)


    def get_proto_percentage(self, window_id):
        """
        Compute/display the prototype coverage mapping for the currently selected prototype.

        UI/job/cache orchestration stays in the main class.
        Image/membership computation lives in ColorProcessingEngine.
        """
        if getattr(self, "mapping_locked_until_original", {}).get(window_id, False):
            self.custom_warning(
                "Restore Original Image",
                "This image belongs to a previous Color Space. Press Original before selecting a prototype."
            )
            return

        if not hasattr(self, "current_protos") or window_id not in self.current_protos:
            self.custom_warning("Error", "No prototype selected for this window.")
            return

        if not hasattr(self, "window_image_key") or window_id not in self.window_image_key:
            self.custom_warning("Error", "Image cache key not found for this window.")
            return

        info = getattr(self, "proto_options", {}).get(window_id, {})
        choice = info.get("selection")
        if choice is None:
            self.custom_warning("Select a Color", "Choose a category or granule first.")
            return
        kind, pos = choice[0], int(choice[1])
        if pos < 0 or pos >= len(self.prototypes):
            self.custom_warning("Invalid Selection", "The selected category no longer exists.")
            return
        granule_index = int(choice[2]) if kind == "granule" else None
        if kind == "granule":
            if not getattr(self.fuzzy_color_space, "is_granular", False):
                self.custom_warning("Invalid Selection", "This space has no individual granules.")
                return
            cat = self.fuzzy_color_space.categories[pos]
            if not 0 <= granule_index < len(cat.prototypes):
                self.custom_warning("Invalid Selection", "The selected granule no longer exists.")
                return
            selected_proto = f"{cat.label} / {cat.prototypes[granule_index].label}"
        else:
            selected_proto = str(self.prototypes[pos].label)

        image_key = self.window_image_key[window_id]
        color_space_key = getattr(self, "file_path", None)
        cache_scope = (image_key, color_space_key)

        def run_process(cancel_event, job_id):
            try:
                if self._is_job_cancelled(window_id, cancel_event, job_id):
                    return

                if not hasattr(self, "proto_percentage_cache_by_image"):
                    self.proto_percentage_cache_by_image = {}
                scope_cache = self.proto_percentage_cache_by_image.setdefault(cache_scope, {})

                if not hasattr(self, "images") or window_id not in self.images:
                    self.image_canvas.after(
                        0,
                        lambda: self.custom_warning("Error", "Current image not found for this window.")
                    )
                    return

                source_img = self._get_mapping_source_image(window_id)
                w, h = source_img.size

                valid_mask = UtilsTools._get_alpha_mask_from_pil(source_img)
                processing_img = UtilsTools._pil_rgb_for_processing(source_img)

                cache_key = (kind, pos, granule_index, w, h,
                             getattr(self.fuzzy_color_space, "tconorm", None)
                             if kind == "category" else None)
                cached_entry = scope_cache.get(cache_key)

                if cached_entry is not None:
                    if self._is_job_cancelled(window_id, cancel_event, job_id):
                        return
                    grayscale_image_array = cached_entry["array"]
                    pct = cached_entry["pct"]
                else:
                    def update_progress(current_step, total_steps):
                        if cancel_event.is_set():
                            raise RuntimeError("__JOB_CANCELLED__")
                        self._update_window_progress(window_id, job_id, current_step, total_steps)

                    grayscale_image_array = self.image_manager.get_proto_percentage(
                        prototypes=self.prototypes,
                        image=processing_img,
                        fuzzy_color_space=self.fuzzy_color_space,
                        selected_option=pos,
                        granule_index=granule_index,
                        progress_callback=update_progress,
                        cancel_callback=lambda: cancel_event.is_set()
                    )

                    if grayscale_image_array is None:
                        return

                    # Force transparent/background pixels to 0 in the grayscale map.
                    if grayscale_image_array.ndim == 2:
                        grayscale_image_array[~valid_mask] = 0

                    if self._is_job_cancelled(window_id, cancel_event, job_id):
                        return

                    pct, thresh = self.image_manager.estimate_proto_coverage(
                        grayscale_image_array,
                        valid_mask
                    )

                    scope_cache[cache_key] = {
                        "array": grayscale_image_array,
                        "pct": pct,
                        "thresh_used": thresh
                    }

                def _ui():
                    if self._is_job_cancelled(window_id, cancel_event, job_id):
                        return

                    self.display_color_mapping(grayscale_image_array, window_id)
                    current_info = getattr(self, "proto_options", {}).get(window_id)
                    if isinstance(current_info, dict) and current_info.get("kind") == "single":
                        current_info["displayed_for"] = choice
                    self.image_canvas.itemconfig(
                        f"{window_id}_pct_text",
                        text=f"{selected_proto}: {pct:.2f}%"
                    )

                    # Percentage text changes the compact spacing between image
                    # and selector. Reposition and relayout immediately so the
                    # caption remains centered after Grid/Focus/manual resize.
                    self._reposition_proto_options(window_id)
                    callbacks = getattr(self, "_image_workspace_callbacks", {}).get(window_id, {})
                    relayout_cb = callbacks.get("relayout") if isinstance(callbacks, dict) else None
                    if callable(relayout_cb):
                        relayout_cb(window_id)

                    self.image_canvas.tag_raise(f"{window_id}_pct_text")

                self.image_canvas.after(0, _ui)

            except RuntimeError as e:
                if str(e) != "__JOB_CANCELLED__":
                    error_msg = str(e)
                    self.image_canvas.after(
                        0,
                        lambda msg=error_msg: self.custom_warning(
                            "Error",
                            f"Error in run_process: {msg}"
                        )
                    )
            except Exception as e:
                error_msg = str(e)
                self.image_canvas.after(
                    0,
                    lambda msg=error_msg: self.custom_warning(
                        "Error",
                        f"Error in run_process: {msg}"
                    )
                )

        job_id = self._start_window_job(window_id, "proto_percentage", run_process)
        if job_id is not None:
            self._show_window_loading(window_id, "Color Mapping...")


    def display_color_mapping(self, grayscale_image_array, window_id):
        """Display one membership map as grayscale or JFCS-style weighted RGB."""
        try:
            try:
                self._disable_original_rectangle_sampling(window_id)
            except Exception:
                pass

            self.modified_image[window_id] = grayscale_image_array

            # Apply the original alpha channel at the mapping resolution.
            try:
                map_h, map_w = grayscale_image_array.shape[:2]
                source_img = self._get_mapping_source_image(
                    window_id,
                    target_size=(map_w, map_h),
                )
                alpha_values = UtilsTools._get_alpha_values_from_pil(source_img)
            except Exception:
                alpha_values = np.full(grayscale_image_array.shape[:2], 255, dtype=np.uint8)

            # Preserve raw grayscale memberships in modified_image/cache.
            # The Color style is a *rendering* of that same result: pixel RGB
            # multiplied by its membership, exactly as in JFCS.
            info = getattr(self, "proto_options", {}).get(window_id, {})
            use_color = (
                isinstance(info, dict)
                and info.get("kind") == "single"
                and info.get("display_style", "gray") == "color"
                and grayscale_image_array.ndim == 2
            )
            if use_color:
                # Convert through PIL so palette (P), grayscale (L) and RGBA
                # originals all produce their actual visible RGB colors.
                source_rgb = np.asarray(source_img.convert("RGB"), dtype=np.uint8)
                colored = self.image_manager.colorize_membership_map(
                    grayscale_image_array, source_rgb
                )
                rgba_array = UtilsTools._apply_alpha_to_rgb_array(colored, alpha_values)
            elif grayscale_image_array.ndim == 2:
                rgba_array = UtilsTools._apply_alpha_to_gray_array(grayscale_image_array, alpha_values)
            else:
                rgba_array = UtilsTools._apply_alpha_to_rgb_array(grayscale_image_array, alpha_values)
            grayscale_image = Image.fromarray(rgba_array.astype(np.uint8), mode="RGBA")

            # Make zoom work over the generated Color Mapping image, not over the original.
            self._set_image_zoom_source(window_id, grayscale_image, reset_zoom=True)

            # Resize only for display
            new_width, new_height = self.image_dimensions[window_id]
            grayscale_image_display = grayscale_image.resize(
                (new_width, new_height),
                Image.Resampling.LANCZOS
            )

            self.images[window_id] = grayscale_image_display
            self.display_pil[window_id] = grayscale_image_display

            if hasattr(self, "display_pil"):
                self.display_pil[window_id] = grayscale_image_display

            img_tk = ImageTk.PhotoImage(grayscale_image_display)
            self.floating_images[window_id] = img_tk

            image_items = self.image_canvas.find_withtag(f"{window_id}_click_image")
            if image_items:
                self.image_canvas.itemconfig(image_items[0], image=img_tk)
            else:
                self.custom_warning("Image Error", f"No image found for window_id: {window_id}")

        except Exception as e:
            self.custom_warning("Display Error", f"Error displaying the image: {e}")


    def show_original_image(self, window_id):
        """Displays the original image, preserving the current resized dimensions of the floating window."""
        try:
            # Cancel any running process linked to this image before restoring the original
            self._cancel_window_job(window_id)

            if hasattr(self, "window_mapping_mode"):
                self.window_mapping_mode.pop(window_id, None)
            try:
                getattr(self, "_mapping_all_palette_by_window", {}).pop(window_id, None)
                getattr(self, "_mapping_all_pack_by_window", {}).pop(window_id, None)
            except Exception:
                pass

            if hasattr(self, "mapping_locked_until_original"):
                self.mapping_locked_until_original.pop(window_id, None)

            # Hide percentage text when showing original image
            try:
                self.image_canvas.itemconfig(f"{window_id}_pct_text", text="")
            except Exception:
                pass

            # Remove the mapping selector/legend from this card.
            try:
                self._destroy_proto_options(window_id)
            except Exception as e:
                self.custom_warning("Window Error", f"Error trying to destroy the proto_options panel: {e}")
                return

            # Ensure we have the original PIL image stored
            if not hasattr(self, "pil_images_original") or window_id not in self.pil_images_original:
                self.custom_warning("Not Original Image", f"Original PIL image not found for window_id: {window_id}")
                return

            pil_original = self.pil_images_original[window_id]

            # Restore zoom source to the original full-resolution image.
            self._set_image_zoom_source(window_id, pil_original, reset_zoom=True)

            # Preserve the current displayed size if the window was resized
            if hasattr(self, "image_dimensions") and window_id in self.image_dimensions:
                target_w, target_h = self.image_dimensions[window_id]
            else:
                target_w, target_h = pil_original.size

            target_w = max(1, int(target_w))
            target_h = max(1, int(target_h))

            # Resize the original image to the current window size
            pil_resized = pil_original.resize((target_w, target_h), Image.Resampling.LANCZOS)

            # Update the current displayed PIL image too
            if hasattr(self, "images"):
                self.images[window_id] = pil_resized

            # Update the PIL image used as source of truth for saving
            if not hasattr(self, "display_pil"):
                self.display_pil = {}
            self.display_pil[window_id] = pil_resized

            # Create a new PhotoImage with the preserved size
            img_tk = ImageTk.PhotoImage(pil_resized)

            # Keep a reference to avoid garbage collection
            if not hasattr(self, "floating_images"):
                self.floating_images = {}
            self.floating_images[window_id] = img_tk

            # Refresh the cache storing the currently displayed original image
            if not hasattr(self, "original_images"):
                self.original_images = {}
            self.original_images[window_id] = img_tk

            # Find the image item in the canvas
            image_items = self.image_canvas.find_withtag(f"{window_id}_img_item")
            if not image_items:
                image_items = self.image_canvas.find_withtag(f"{window_id}_click_image")

            if image_items:
                image_id = image_items[0]
                self.image_canvas.itemconfig(image_id, image=img_tk)
            else:
                self.custom_warning("Image Error", f"No canvas image found for window_id: {window_id}")
                return

            # Reset flags
            self.SHOW_ORIGINAL[window_id] = False
            if self.COLOR_SPACE:
                self.CAN_APPLY_MAPPING[window_id] = True

            # Enable rectangle sampling only when the original image is being shown
            try:
                self._enable_original_rectangle_sampling(
                    window_id=window_id,
                    target_w=target_w,
                    target_h=target_h
                )
            except Exception as e:
                print(f"Warning enabling original rectangle sampling for {window_id}: {e}")

            # Resynchronize the card without destroying manual move/resize controls.
            try:
                if hasattr(self, "floating_window_state") and window_id in self.floating_window_state:
                    self.floating_window_state[window_id]["w"] = target_w
                    self.floating_window_state[window_id]["h"] = target_h
                self._sync_workspace_card_item_states(window_id)
                self._schedule_image_workspace_reflow()
            except Exception:
                pass

        except Exception as e:
            self.custom_warning("Display Error", f"Error displaying the original image: {e}")
            return


    def _display_mapping_all_result(self, window_id, recolored_image, palette_uint8):
        """Display Mapping-All and keep its vertical legend inside the same card."""
        try:
            self.modified_image[window_id] = recolored_image
            if recolored_image.ndim == 3 and recolored_image.shape[-1] == 4:
                pil_to_show = Image.fromarray(recolored_image.astype(np.uint8), mode="RGBA")
            else:
                pil_to_show = Image.fromarray(recolored_image.astype(np.uint8), mode="RGB")

            self._set_image_zoom_source(window_id, pil_to_show, reset_zoom=True)
            target_size = getattr(self, "image_dimensions", {}).get(window_id)
            if target_size:
                pil_display = pil_to_show.resize(
                    (max(1, int(target_size[0])), max(1, int(target_size[1]))),
                    Image.Resampling.LANCZOS,
                )
            else:
                pil_display = pil_to_show

            self.images[window_id] = pil_display
            self.display_pil[window_id] = pil_display
            img_tk = ImageTk.PhotoImage(pil_display)
            self.floating_images[window_id] = img_tk

            image_items = self.image_canvas.find_withtag(f"{window_id}_click_image")
            if not image_items:
                self.custom_warning("Image Error", f"No image found for window_id: {window_id}")
                return
            self.image_canvas.itemconfig(image_items[0], image=img_tk)

            if not hasattr(self, "_mapping_all_palette_by_window"):
                self._mapping_all_palette_by_window = {}
            self._mapping_all_palette_by_window[window_id] = np.asarray(palette_uint8).copy()

            self._create_mapping_all_panel(window_id, palette_uint8)
            self._focus_floating_window(window_id)

        except Exception as exc:
            self.custom_warning("Display Error", f"Error displaying the image: {exc}")


    def color_mapping_all(self, window_id):
        """Compute Mapping All directly from any current image view."""
        if not self.image_canvas.find_withtag(window_id):
            self.custom_warning("No Window", f"No floating window found with id {window_id}")
            return
        if not getattr(self, "COLOR_SPACE", False):
            self.custom_warning("No Color Space", "Load a Fuzzy Color Space before applying Color Mapping All.")
            return

        # The calculation below always starts from pil_images_original, so an
        # old or different mapping view can be replaced directly. Clear only
        # the old-space display lock; no intermediate Original action is needed.
        try:
            getattr(self, "mapping_locked_until_original", {}).pop(window_id, None)
        except Exception:
            pass

        if not hasattr(self, "window_image_key") or window_id not in self.window_image_key:
            self.custom_warning("Error", "Image cache key not found for this window.")
            return
        if not hasattr(self, "window_mapping_mode"):
            self.window_mapping_mode = {}
        self.window_mapping_mode[window_id] = "all"
        initial_view = getattr(self, "_mapping_all_initial_view", {}).pop(
            window_id, ("categories", "original"))

        cache_scope = (self.window_image_key[window_id], getattr(self, "file_path", None))
        try:
            self._disable_original_rectangle_sampling(window_id)
        except Exception:
            pass
        self._sync_workspace_card_item_states(window_id)
        try:
            self.image_canvas.itemconfig(f"{window_id}_pct_text", text="")
        except Exception:
            pass
        self.CAN_APPLY_MAPPING[window_id] = False
        self.SHOW_ORIGINAL[window_id] = True
        self._destroy_proto_options(window_id)
        self._set_image_workspace_active(window_id)

        def update_progress(job_id, current_step, total_steps):
            if total_steps > 0:
                self._update_window_progress(window_id, job_id, current_step, total_steps)

        def run_process(cancel_event, job_id):
            try:
                if self._is_job_cancelled(window_id, cancel_event, job_id):
                    return
                source_img = self._get_mapping_source_image(window_id)
                w, h = source_img.size
                alpha_values = UtilsTools._get_alpha_values_from_pil(source_img)
                valid_mask = alpha_values > 0
                processing_img = UtilsTools._pil_rgb_for_processing(source_img)
                if not hasattr(self, "cm_cache_by_image"):
                    self.cm_cache_by_image = {}
                scope_cache = self.cm_cache_by_image.setdefault(cache_scope, {})
                proto_labels = tuple(p.label for p in self.prototypes)
                flat = (self.fuzzy_color_space.get_all_prototypes()
                        if getattr(self.fuzzy_color_space, "is_granular", False)
                        else self.prototypes)
                cache_key = (w, h, proto_labels, tuple(p.label for p in flat),
                             getattr(self.fuzzy_color_space, "tconorm", None))
                maps = scope_cache.get(cache_key)
                if maps is None:
                    maps = self.image_manager.get_category_granule_label_maps(
                        image=processing_img, fuzzy_color_space=self.fuzzy_color_space,
                        valid_mask=valid_mask,
                        progress_callback=lambda current, total: update_progress(job_id, current, total),
                        cancel_callback=lambda: self._is_job_cancelled(window_id, cancel_event, job_id))
                    if maps is None:
                        return
                    scope_cache[cache_key] = maps
                if self._is_job_cancelled(window_id, cancel_event, job_id):
                    return
                label_maps = {"categories": maps[0], "granules": maps[1]}
                category_original = self.image_manager.build_original_palette_uint8(
                    self.prototypes, self.fuzzy_color_space.color_space)
                category_alt = self.image_manager.build_alt_palette_uint8(self.prototypes)
                granule_original = self.image_manager.build_original_palette_uint8(
                    flat, self.fuzzy_color_space.color_space)
                granule_alt = self.image_manager.build_granule_alt_palette_uint8(
                    self.fuzzy_color_space, category_alt)
                level_palettes = {
                    "categories": {"original": category_original, "alt": category_alt},
                    "granules": {"original": granule_original, "alt": granule_alt},
                }
                level, scheme = initial_view
                if level not in label_maps:
                    level = "categories"
                if scheme not in ("original", "alt"):
                    scheme = "original"
                palette = level_palettes[level][scheme]
                label_map = label_maps[level]
                recolored_image = self.image_manager.recolor_label_map(
                    label_map, palette, alpha_values)
                if not self.fuzzy_color_space.covering:
                    missing = (label_map < 0) & valid_mask
                    if np.any(missing):
                        recolored_image[missing, :3] = np.asarray(processing_img)[missing, :3]
                        recolored_image[missing, 3] = alpha_values[missing]
                window_pack = {
                    "label_maps": label_maps, "level_palettes": level_palettes,
                    "label_map": label_map, "alpha_values": alpha_values,
                    "palettes": level_palettes[level], "level": level,
                    "scheme": scheme, "cache_key": cache_key,
                }
                def _ui():
                    if self._is_job_cancelled(window_id, cancel_event, job_id):
                        return
                    self._mapping_all_pack_by_window[window_id] = window_pack
                    self._display_mapping_all_result(window_id, recolored_image, palette)
                self.image_canvas.after(0, _ui)
            except RuntimeError as exc:
                if str(exc) != "__JOB_CANCELLED__":
                    msg = str(exc)
                    self.image_canvas.after(0, lambda m=msg: self.custom_warning("Processing Error", f"Error in color mapping: {m}"))
            except Exception as exc:
                msg = str(exc)
                self.image_canvas.after(0, lambda m=msg: self.custom_warning("Processing Error", f"Error in color mapping: {m}"))

        job_id = self._start_window_job(window_id, "color_mapping_all", run_process)
        if job_id is not None:
            self._show_window_loading(window_id, "Color Mapping All...")


    def get_umbral_points(self, threshold, mode=None):
        """
        Filter points inside the selected fuzzy volumes using the given threshold
        and update the embedded 3D view.
        """
        # Ensure a color space is available before running the evaluation.
        if not hasattr(self, "COLOR_SPACE") or not self.COLOR_SPACE:
            self.custom_warning("No Color Space", "Please load a fuzzy color space before deploying AT or PT.")
            return

        if self._has_any_active_job():
            self.custom_warning("Process Running", "A processing task is already running.")
            return

        selected_options = [key for key, var in self.model_3d_options.items() if var.get()]
        if not any(opt in selected_options for opt in ("Support", "0.5-cut", "Core")):
            return
        self._threshold_job_running = True
        try:
            self.show_loading(
                title="Processing Color Evaluation",
                message="Evaluating colors within the selected volumes...",
                note="The 3D visualization will update when the analysis finishes."
            )
        except Exception:
            self._threshold_job_running = False
            raise

        def update_status(message):
            try:
                self.root.after(
                    0, lambda text=message: self._set_processing_progress(message=text)
                )
            except (RuntimeError, tk.TclError):
                pass

        def run_threshold_process():
            """
            Run the threshold filtering in a background thread and refresh the 3D plot
            on the main Tkinter thread when the computation finishes.
            """
            try:
                # Define the volume priority used for threshold filtering.
                priority_map = {
                    "Support": self.selected_support,
                    "0.5-cut": self.selected_alpha,
                    "Core": self.selected_core,
                }

                selected_option = next(
                    (opt for opt in ["Support", "0.5-cut", "Core"] if opt in selected_options),
                    None,
                )
                selected_volume = priority_map[selected_option]

                # Step 1: filter the LAB points inside the selected volume.
                geometric_mode = (self.fuzzy_color_space.color_space
                                  if getattr(self,"fuzzy_color_space",None) else "LAB")
                filtered_points, volume_limits = self.color_manager.filter_points_with_threshold(
                    selected_volume, threshold, step=0.25,
                    color_space=geometric_mode,
                )

                # Save the computed ranges as CSV.
                csv_path = self.color_manager.create_csv(
                    self.file_base_name, volume_limits, mode,
                    color_space=geometric_mode)
                print(f"Threshold CSV saved: {csv_path}")

                # Step 2: prepare the plot refresh.
                update_status("Preparing the updated 3D visualization...")

                def redraw_filtered_plot():
                    """
                    Refresh the existing embedded 3D figure with the filtered points.
                    """
                    self.filtered_points = filtered_points
                    self._init_3d_canvas()

                    space = getattr(self,"fuzzy_color_space",None)
                    plot_hex = self.hex_color
                    plot_centroids = self.selected_centroids
                    if space and space.color_space == "RGB":
                        plot_hex = {h:space.model_from_lab(lab) for h,lab in self.hex_color.items()}
                        plot_centroids = {k:{**v,"positive_prototype":space.model_from_lab(
                            v.get("positive_prototype",v.get("Color")))} for k,v in self.selected_centroids.items()}
                    VisualManager.plot_combined_3D(
                        self.ax_3d, self.file_base_name, plot_centroids,
                        self.selected_core, self.selected_alpha, self.selected_support,
                        self.volume_limits, plot_hex, selected_options,
                        self.filtered_points, color_space=space.color_space if space else "LAB",
                    )

                    self.graph_widget.draw()

                    if hasattr(self, "lab_value_frame"):
                        self.lab_value_frame.lift()

                # Step 3: redraw the figure on the Tkinter main thread.
                def finish_success():
                    try:
                        redraw_filtered_plot()
                    finally:
                        self._threshold_job_running = False
                        self.hide_loading()

                self.root.after(0, finish_success)

            except Exception as exc:
                error_msg = str(exc)

                def finish_error(msg=error_msg):
                    self._threshold_job_running = False
                    self.hide_loading()
                    self.custom_warning(
                        "Error", f"An error occurred while filtering points: {msg}"
                    )

                try:
                    self.root.after(0, finish_error)
                except (RuntimeError, tk.TclError):
                    self._threshold_job_running = False

        # Run the expensive filtering process in a background thread.
        threading.Thread(target=run_threshold_process, daemon=True).start()


    def deploy_at(self):
        if self._has_any_active_job():
            self.custom_warning(
                "Process Running",
                "There is a process currently running. Please wait for it to finish or cancel it before loading a Color Space."
            )
            return
        self.get_umbral_points(1.8, mode="AT")

    def deploy_pt(self):
        if self._has_any_active_job():
            self.custom_warning(
                "Process Running",
                "There is a process currently running. Please wait for it to finish or cancel it before loading a Color Space."
            )
            return
        self.get_umbral_points(0.8, mode="PT")
























    # ============================================================================================================================================================
    #  FUNCTIONS DISPLAY PIXEL INFO
    # ============================================================================================================================================================
    def _ensure_threshold_settings(self):
        """
        Ensure shared threshold settings exist and are normalized by ColorEvaluationManager.
        """
        manager = self._get_color_evaluation_manager()

        current_settings = getattr(self, "threshold_settings", None)
        self.threshold_settings = manager.normalize_threshold_settings(current_settings)


    def _apply_color_evaluation_result_style(self, vars_dict, status):
        """Apply the shared threshold result visual style to the Color Evaluation result card."""
        refs = vars_dict.get("analysis_result_refs")
        if not refs:
            return

        self._apply_threshold_result_style(refs, status)


    def _update_color_evaluation_result_card(self, vars_dict, title, detail="", summary="", status="neutral"):
        """Update the styled result card used in the Color Evaluation panel."""
        vars_dict["selected_result_var"].set(title)
        vars_dict["selected_detail_var"].set(detail)
        vars_dict["selected_summary_var"].set(summary)

        self._apply_color_evaluation_result_style(vars_dict, status)


    def _get_threshold_display_maps(self):
        """Return display maps used by all threshold UIs."""
        manager = self._get_color_evaluation_manager()
        return manager.get_threshold_display_maps()


    def _get_threshold_reverse_maps(self):
        """Return reverse display maps used by all threshold UIs."""
        manager = self._get_color_evaluation_manager()
        return manager.get_threshold_reverse_maps()


    def _create_shared_threshold_vars(self):
        """
        Create the threshold-related Tk variables shared by all windows.
        """
        self._ensure_threshold_settings()

        preset_display_map, custom_type_display_map = self._get_threshold_display_maps()

        saved_mode = self.threshold_settings.get("mode", "default")
        if saved_mode == "known":
            saved_mode = "default"

        return {
            "threshold_metric_family_var": tk.StringVar(
                value=self.threshold_settings.get("metric_family", "Perceptual ΔE")
            ),
            "threshold_metric_var": tk.StringVar(
                value=self.threshold_settings.get("metric", "CIEDE2000")
            ),
            "threshold_metric_help_var": tk.StringVar(value=""),

            "threshold_mode_var": tk.StringVar(value=saved_mode),
            "threshold_preset_var": tk.StringVar(
                value=preset_display_map.get(
                    self.threshold_settings.get("preset", "pt_at"),
                    "Perceptibility + Acceptability"
                )
            ),
            "threshold_custom_type_var": tk.StringVar(
                value=custom_type_display_map.get(
                    self.threshold_settings.get("custom_type", "single"),
                    "Single threshold"
                )
            ),
            "threshold_single_var": tk.StringVar(
                value="" if self.threshold_settings.get("single") is None
                else str(self.threshold_settings.get("single"))
            ),
            "threshold_lower_var": tk.StringVar(
                value="" if self.threshold_settings.get("lower") is None
                else str(self.threshold_settings.get("lower"))
            ),
            "threshold_upper_var": tk.StringVar(
                value="" if self.threshold_settings.get("upper") is None
                else str(self.threshold_settings.get("upper"))
            ),
            "config_hint_var": tk.StringVar(value=""),

            # Result-style block
            "threshold_result_title_var": tk.StringVar(value=""),
            "threshold_result_detail_var": tk.StringVar(value=""),
            "threshold_result_summary_var": tk.StringVar(value=""),
            "threshold_result_message_var": tk.StringVar(value=""),

            # Summary-style block
            "threshold_summary_title_var": tk.StringVar(value=""),
            "threshold_summary_detail_var": tk.StringVar(value=""),
            "threshold_summary_extra_var": tk.StringVar(value=""),
        }


    def _merge_threshold_vars(self, target_dict):
        """
        Inject shared threshold vars into an existing vars dict.
        """
        shared = self._create_shared_threshold_vars()
        target_dict.update(shared)
        return target_dict


    def _sync_threshold_settings_from_vars(self, vars_dict):
        """
        Persist threshold UI values into self.threshold_settings.
        Translation/normalization logic lives in ColorEvaluationManager.
        """
        manager = self._get_color_evaluation_manager()

        self.threshold_settings = manager.build_threshold_settings_from_ui_values(
            metric_family=vars_dict["threshold_metric_family_var"].get(),
            metric=vars_dict["threshold_metric_var"].get(),
            mode=vars_dict["threshold_mode_var"].get(),
            preset_display=vars_dict["threshold_preset_var"].get(),
            custom_type_display=vars_dict["threshold_custom_type_var"].get(),
            single_value=vars_dict["threshold_single_var"].get(),
            lower_value=vars_dict["threshold_lower_var"].get(),
            upper_value=vars_dict["threshold_upper_var"].get(),
            base_settings=getattr(self, "threshold_settings", None),
        )


    def _refresh_threshold_metric_controls(self, vars_dict, refs):
        """
        Refresh metric combo values and metric help text from selected metric family.
        """
        manager = self._get_color_evaluation_manager()

        family = vars_dict["threshold_metric_family_var"].get().strip()
        metrics = manager.get_metrics_for_family(family)

        metric_combo = refs.get("metric_combo")

        if metric_combo is not None:
            metric_combo.configure(values=metrics)

        current_metric = vars_dict["threshold_metric_var"].get().strip()

        if current_metric not in metrics:
            current_metric = metrics[0] if metrics else "CIEDE2000"
            vars_dict["threshold_metric_var"].set(current_metric)

        vars_dict["threshold_metric_help_var"].set(
            manager.get_metric_description(current_metric)
        )


    def _hide_threshold_config_controls(self, refs):
        """Hide all threshold config widgets before rebuilding the visible subset."""
        for key in (
            "preset_label", "preset_combo",
            "custom_type_label", "custom_type_combo",
            "single_label", "single_entry",
            "lower_label", "lower_entry",
            "upper_label", "upper_entry",
            "config_hint_label",
        ):
            try:
                refs[key].grid_remove()
            except Exception:
                pass


    def _apply_threshold_result_style(self, threshold_refs, status):
        """
        Apply the shared visual style used by threshold result cards.
        Accepts both old threshold statuses and new generic metric statuses.
        """
        styles = {
            "red": {
                "body_bg": "#f8f2f2",
                "header_bg": "#f2dede",
                "border": "#b94a48",
                "accent": "#b30000",
                "separator": "#e7b6b6",
            },
            "yellow": {
                "body_bg": "#fff7e6",
                "header_bg": "#ffe0b2",
                "border": "#f0a23a",
                "accent": "#b26a00",
                "separator": "#f3c27a",
            },
            "green": {
                "body_bg": "#f3faf3",
                "header_bg": "#dff0d8",
                "border": "#468847",
                "accent": "#2d6a2d",
                "separator": "#b9d8b1",
            },
            "neutral": {
                "body_bg": "#f7f7f7",
                "header_bg": "#eeeeee",
                "border": "#bdbdbd",
                "accent": "#666666",
                "separator": "#dddddd",
            }
        }

        status_to_theme = {
            # Existing statuses
            "below_pt": "green",
            "below_at": "green",
            "below_custom": "green",
            "below_lower": "green",
            "between_pt_at": "yellow",
            "between_custom": "yellow",
            "above_pt": "red",
            "above_at": "red",
            "above_custom": "red",
            "above_upper": "red",

            # Generic new statuses
            "inside": "green",
            "warning": "yellow",
            "outside": "red",
            "within": "green",
            "between": "yellow",
            "above": "red",
            "below": "green",

            # Neutral/error
            "invalid": "neutral",
            "unavailable": "neutral",
            "unsupported_metric": "neutral",
            "unknown_mode": "neutral",
        }

        theme_key = status_to_theme.get(status, "neutral")
        theme = styles[theme_key]

        if "result_card" not in threshold_refs:
            return

        try:
            threshold_refs["result_card"].configure(
                bg=theme["body_bg"],
                highlightbackground=theme["border"],
                highlightcolor=theme["border"]
            )
            threshold_refs["result_header"].configure(bg=theme["header_bg"])
            threshold_refs["result_status_dot"].configure(bg=theme["header_bg"])
            threshold_refs["result_title_label"].configure(bg=theme["header_bg"])
            threshold_refs["result_value_label"].configure(
                bg=theme["header_bg"] if threshold_refs.get("value_in_header") else theme["body_bg"],
                fg=theme["accent"]
            )
            threshold_refs["result_separator"].configure(bg=theme["separator"])
            threshold_refs["result_summary_row"].configure(bg=theme["body_bg"])
            threshold_refs["result_summary_icon"].configure(bg=theme["body_bg"])
            threshold_refs["result_body"].configure(bg=theme["body_bg"])
            threshold_refs["result_summary_label"].configure(bg=theme["body_bg"])

            threshold_refs["result_summary_icon"].itemconfig(
                threshold_refs["result_summary_icon_circle"],
                outline=theme["accent"]
            )
            threshold_refs["result_summary_icon"].itemconfig(
                threshold_refs["result_summary_icon_text"],
                fill=theme["accent"]
            )
            threshold_refs["result_status_dot"].itemconfig(
                threshold_refs["result_status_dot_oval"],
                fill=theme["border"],
                outline=theme["border"]
            )
        except Exception:
            pass


    def _update_threshold_summary_text(self, vars_dict):
        """
        Update the compact textual summary for threshold configuration.
        Metric explanation is intentionally NOT repeated here.
        """
        manager = self._get_color_evaluation_manager()

        title, detail, extra = manager.get_threshold_summary_parts(self.threshold_settings)

        vars_dict["threshold_summary_title_var"].set(title)
        vars_dict["threshold_summary_detail_var"].set(detail)
        vars_dict["threshold_summary_extra_var"].set(extra)


    def _build_shared_threshold_panel(self, parent, vars_dict, title="Threshold", variant="result"):
        """
        Shared threshold UI builder.

        variant:
            - 'result'  -> like Image Inspection: config + colored result card
            - 'summary' -> like Color Evaluation: config + textual summary
        """
        threshold_panel = tk.Frame(parent, bg="white", bd=1, relief="solid")
        threshold_panel.pack(fill="x", pady=(6, 0), anchor="n")

        tk.Label(
            threshold_panel,
            text=title,
            font=("Sans", 11, "bold"),
            anchor="w",
            bg="white",
            padx=12,
            pady=7 if variant == "summary" else 10
        ).pack(fill="x")

        threshold_body = tk.Frame(threshold_panel, bg="white")
        threshold_body.pack(fill="x", padx=12, pady=(0, 6 if variant == "summary" else 10))

        if variant == "result":
            selection_w = 280
            config_w = 285
            result_w = 380

            threshold_body.grid_columnconfigure(0, minsize=selection_w, weight=0)
            threshold_body.grid_columnconfigure(1, minsize=1, weight=0)
            threshold_body.grid_columnconfigure(2, minsize=config_w, weight=0)
            threshold_body.grid_columnconfigure(3, minsize=1, weight=0)
            threshold_body.grid_columnconfigure(4, minsize=result_w, weight=0)

            section_selection = tk.Frame(threshold_body, bg="white", width=selection_w)
            section_selection.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
            section_selection.grid_propagate(False)

            tk.Frame(threshold_body, bg="#d8d8d8", width=1, height=165).grid(
                row=0, column=1, sticky="ns", padx=(0, 12), pady=2
            )

            section_config = tk.Frame(threshold_body, bg="white", width=config_w)
            section_config.grid(row=0, column=2, sticky="nsw", padx=(0, 12))
            section_config.grid_propagate(False)

            tk.Frame(threshold_body, bg="#d8d8d8", width=1, height=165).grid(
                row=0, column=3, sticky="ns", padx=(0, 12), pady=2
            )

            section_output = tk.Frame(threshold_body, bg="white", width=result_w)
            section_output.grid(row=0, column=4, sticky="nsw")
            section_output.grid_propagate(False)
            section_output.grid_columnconfigure(0, weight=1)
            section_output.grid_rowconfigure(1, weight=1)

        else:
            # In Color Evaluation the first column contains full metric descriptions.
            # Allow it to grow on wide screens while keeping workable minimum widths
            # for the configuration and summary when the window is narrower.
            selection_w = 350
            config_w = 410

            threshold_body.grid_columnconfigure(0, minsize=selection_w, weight=2)
            threshold_body.grid_columnconfigure(1, minsize=1, weight=0)
            threshold_body.grid_columnconfigure(2, minsize=config_w, weight=3)
            threshold_body.grid_columnconfigure(3, minsize=1, weight=0)
            threshold_body.grid_columnconfigure(4, minsize=225, weight=1)

            section_selection = tk.Frame(threshold_body, bg="white", width=selection_w)
            section_selection.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
            section_selection.grid_propagate(False)

            # A fixed 140px divider prevented any vertical-space saving when
            # the metric description no longer needed two lines.
            tk.Frame(threshold_body, bg="#d8d8d8", width=1, height=1).grid(
                row=0, column=1, sticky="ns", padx=(0, 12), pady=2
            )

            section_config = tk.Frame(threshold_body, bg="white", width=config_w)
            section_config.grid(row=0, column=2, sticky="nsew", padx=(0, 12))
            section_config.grid_propagate(False)

            tk.Frame(threshold_body, bg="#d8d8d8", width=1, height=1).grid(
                row=0, column=3, sticky="ns", padx=(0, 12), pady=2
            )

            section_output = tk.Frame(threshold_body, bg="white")
            section_output.grid(row=0, column=4, sticky="nsew")

        # Left: metric selection
        manager = self._get_color_evaluation_manager()

        tk.Label(
            section_selection,
            text="Metric Family",
            font=("Sans", 10, "bold"),
            anchor="w",
            bg="white"
        ).pack(anchor="w", pady=(0, 4))

        metric_family_combo = ttk.Combobox(
            section_selection,
            textvariable=vars_dict["threshold_metric_family_var"],
            state="readonly",
            width=30 if variant == "result" else 34,
            values=manager.get_metric_families()
        )
        metric_family_combo.pack(anchor="w", pady=(0, 8))

        tk.Label(
            section_selection,
            text="Metric",
            font=("Sans", 10, "bold"),
            anchor="w",
            bg="white"
        ).pack(anchor="w", pady=(0, 4))

        metric_combo = ttk.Combobox(
            section_selection,
            textvariable=vars_dict["threshold_metric_var"],
            state="readonly",
            width=30 if variant == "result" else 34,
            values=manager.get_metrics_for_family(
                vars_dict["threshold_metric_family_var"].get()
            )
        )
        metric_combo.pack(anchor="w", pady=(0, 6))

        metric_help_label = tk.Label(
            section_selection,
            textvariable=vars_dict["threshold_metric_help_var"],
            bg="white",
            fg="#666666",
            anchor="w",
            justify="left",
            wraplength=255 if variant == "result" else 0,
            font=("Sans", 8, "italic")
        )
        metric_help_label.pack(anchor="w", fill="x", pady=(0, 4))

        if variant == "summary":
            # At full width show the entire description on one line.
            # On smaller screens, wrap instead of clipping the information.
            def _resize_metric_help(event=None):
                try:
                    available = max(1, section_selection.winfo_width() - 8)
                    needed = int(metric_help_label.tk.call(
                        "font", "measure", metric_help_label.cget("font"),
                        vars_dict["threshold_metric_help_var"].get()
                    )) + 12
                    target_wrap = 0 if needed <= available else available
                    if int(metric_help_label.cget("wraplength")) != target_wrap:
                        metric_help_label.configure(wraplength=target_wrap)
                except tk.TclError:
                    pass

            section_selection.bind("<Configure>", _resize_metric_help)
            vars_dict["threshold_metric_help_var"].trace_add(
                "write", lambda *_: section_selection.after_idle(_resize_metric_help)
            )

        # Center: configuration
        tk.Label(
            section_config,
            text="Configuration",
            font=("Sans", 10, "bold"),
            anchor="w",
            bg="white"
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))

        section_config.grid_columnconfigure(0, minsize=115, weight=0)
        section_config.grid_columnconfigure(1, minsize=90, weight=1)
        section_config.grid_columnconfigure(2, minsize=115, weight=0)
        section_config.grid_columnconfigure(3, minsize=90, weight=1)

        mode_label = tk.Label(section_config, text="Threshold type:", bg="white", anchor="w")
        mode_combo = ttk.Combobox(
            section_config,
            textvariable=vars_dict["threshold_mode_var"],
            state="readonly",
            width=26 if variant == "result" else 28,
            values=["default", "custom"]
        )
        mode_label.grid(row=1, column=0, sticky="w", pady=(0, 6), padx=(0, 10))
        mode_combo.grid(row=1, column=1, columnspan=3, sticky="ew", pady=(0, 6))

        preset_label = tk.Label(section_config, text="Default preset:", bg="white", anchor="w")
        preset_combo = ttk.Combobox(
            section_config,
            textvariable=vars_dict["threshold_preset_var"],
            state="readonly",
            width=26 if variant == "result" else 28,
            values=[
                "Perceptibility Threshold",
                "Acceptability Threshold",
                "Perceptibility + Acceptability"
            ]
        )

        custom_type_label = tk.Label(section_config, text="Custom mode:", bg="white", anchor="w")
        custom_type_combo = ttk.Combobox(
            section_config,
            textvariable=vars_dict["threshold_custom_type_var"],
            state="readonly",
            width=26 if variant == "result" else 28,
            values=[
                "Single threshold",
                "Lower and upper thresholds"
            ]
        )

        single_label = tk.Label(section_config, text="Threshold:", bg="white", anchor="w")
        single_entry = tk.Entry(section_config, textvariable=vars_dict["threshold_single_var"], width=12)

        lower_label = tk.Label(section_config, text="Lower threshold:", bg="white", anchor="w")
        lower_entry = tk.Entry(section_config, textvariable=vars_dict["threshold_lower_var"], width=10)

        upper_label = tk.Label(section_config, text="Upper threshold:", bg="white", anchor="w")
        upper_entry = tk.Entry(section_config, textvariable=vars_dict["threshold_upper_var"], width=10)

        config_hint_label = tk.Label(
            section_config,
            textvariable=vars_dict["config_hint_var"],
            bg="white",
            fg="#666666",
            anchor="w",
            justify="left",
            wraplength=360,
            font=("Sans", 9, "italic")
        )

        def _update_config_hint_wrap(event=None):
            try:
                available_width = max(section_config.winfo_width() - 20, 220)
                config_hint_label.configure(wraplength=available_width)
            except Exception:
                pass

        section_config.bind("<Configure>", _update_config_hint_wrap)

        refs = {
            "metric_family_combo": metric_family_combo,
            "metric_combo": metric_combo,
            "metric_help_label": metric_help_label,
            "mode_label": mode_label,
            "mode_combo": mode_combo,
            "preset_label": preset_label,
            "preset_combo": preset_combo,
            "custom_type_label": custom_type_label,
            "custom_type_combo": custom_type_combo,
            "single_label": single_label,
            "single_entry": single_entry,
            "lower_label": lower_label,
            "lower_entry": lower_entry,
            "upper_label": upper_label,
            "upper_entry": upper_entry,
            "config_hint_label": config_hint_label,
            "variant": variant,
        }

        # Right: output
        if variant == "result":
            results_title = tk.Label(
                section_output,
                text="Results",
                font=("Sans", 10, "bold"),
                anchor="w",
                bg="white"
            )
            results_title.grid(row=0, column=0, sticky="ew", pady=(0, 8))

            result_card = tk.Frame(
                section_output,
                bg="#f7f7f7",
                bd=0,
                relief="flat",
                highlightthickness=2,
                highlightbackground="#bdbdbd",
                highlightcolor="#bdbdbd"
            )
            result_card.grid(row=1, column=0, sticky="nsew", padx=(0, 6), pady=(0, 2))

            result_header = tk.Frame(result_card, bg="#eeeeee")
            result_header.pack(fill="x")

            result_status_dot = tk.Canvas(
                result_header,
                width=18,
                height=18,
                bg="#eeeeee",
                highlightthickness=0,
                bd=0
            )
            result_status_dot.pack(side="left", padx=(10, 6), pady=8)
            result_status_dot_oval = result_status_dot.create_oval(
                3, 3, 15, 15, fill="#bdbdbd", outline="#bdbdbd"
            )

            result_title_label = tk.Label(
                result_header,
                textvariable=vars_dict["threshold_result_title_var"],
                anchor="w",
                justify="left",
                bg="#eeeeee",
                font=("Sans", 10, "bold"),
                wraplength=300
            )
            result_title_label.pack(side="left", fill="x", expand=True, padx=(0, 12), pady=8)

            result_body = tk.Frame(result_card, bg="#f7f7f7")
            result_body.pack(fill="x", padx=12, pady=(10, 12))

            result_value_label = tk.Label(
                result_body,
                textvariable=vars_dict["threshold_result_detail_var"],
                anchor="w",
                justify="left",
                bg="#f7f7f7",
                fg="#666666",
                font=("Sans", 9, "bold")
            )
            result_value_label.pack(anchor="w", fill="x", pady=(0, 12))

            result_separator = tk.Frame(result_body, bg="#dddddd", height=2)
            result_separator.pack(fill="x", padx=6, pady=(0, 10))

            result_summary_row = tk.Frame(result_body, bg="#f7f7f7")
            result_summary_row.pack(fill="x")

            result_summary_icon = tk.Canvas(
                result_summary_row,
                width=20,
                height=20,
                bg="#f7f7f7",
                highlightthickness=0,
                bd=0
            )
            result_summary_icon.pack(side="left", padx=(0, 8), anchor="n")

            icon_circle = result_summary_icon.create_oval(2, 2, 18, 18, outline="#666666", width=2)
            icon_text = result_summary_icon.create_text(10, 10, text="!", fill="#666666", font=("Sans", 9, "bold"))

            result_text_container = tk.Frame(result_summary_row, bg="#f7f7f7")
            result_text_container.pack(side="left", fill="both", expand=True)

            result_summary_label = tk.Label(
                result_text_container,
                textvariable=vars_dict["threshold_result_summary_var"],
                anchor="w",
                justify="left",
                bg="#f7f7f7",
                wraplength=260,
                font=("Sans", 8)
            )
            result_summary_label.pack(anchor="w", fill="x")

            def _update_result_wrap(event=None):
                try:
                    result_width = max(section_output.winfo_width() - 30, 180)
                    title_wrap = max(result_width - 55, 120)
                    summary_wrap = max(result_width - 70, 120)
                    result_title_label.config(wraplength=title_wrap)
                    result_summary_label.config(wraplength=summary_wrap)
                except Exception:
                    pass

            section_output.bind("<Configure>", _update_result_wrap)

            refs.update({
                "result_card": result_card,
                "result_header": result_header,
                "result_status_dot": result_status_dot,
                "result_status_dot_oval": result_status_dot_oval,
                "result_title_label": result_title_label,
                "result_body": result_body,
                "result_value_label": result_value_label,
                "result_separator": result_separator,
                "result_summary_row": result_summary_row,
                "result_summary_icon": result_summary_icon,
                "result_summary_icon_circle": icon_circle,
                "result_summary_icon_text": icon_text,
                "result_summary_label": result_summary_label,
            })

        else:
            tk.Label(
                section_output,
                text="Current Threshold Summary",
                font=("Sans", 10, "bold"),
                anchor="w",
                bg="white"
            ).pack(anchor="w", pady=(0, 8))

            tk.Label(
                section_output,
                textvariable=vars_dict["threshold_summary_title_var"],
                anchor="w",
                justify="left",
                bg="white",
                font=("Sans", 10, "bold"),
                wraplength=320
            ).pack(anchor="w", fill="x", pady=(0, 6))

            tk.Label(
                section_output,
                textvariable=vars_dict["threshold_summary_detail_var"],
                anchor="w",
                justify="left",
                bg="white",
                wraplength=320
            ).pack(anchor="w", fill="x", pady=(0, 6))

            tk.Label(
                section_output,
                textvariable=vars_dict["threshold_summary_extra_var"],
                anchor="w",
                justify="left",
                bg="white",
                wraplength=320
            ).pack(anchor="w", fill="x")

        return refs


    def _refresh_shared_threshold_ui(self, vars_dict, refs, proto_lab=None, sample_lab=None):
        """
        Shared refresh for threshold controls.

        - For variant='summary': updates the summary texts only.
        - For variant='result': updates config + evaluation result card.
        """
        self._refresh_threshold_metric_controls(vars_dict, refs)
        self._sync_threshold_settings_from_vars(vars_dict)
        self._hide_threshold_config_controls(refs)

        mode_value = self.threshold_settings.get("mode", "default")
        custom_type = self.threshold_settings.get("custom_type", "single")

        single_text = vars_dict["threshold_single_var"].get().strip()
        lower_text = vars_dict["threshold_lower_var"].get().strip()
        upper_text = vars_dict["threshold_upper_var"].get().strip()

        if mode_value == "default":
            refs["preset_label"].grid(row=2, column=0, sticky="w", pady=(0, 6), padx=(0, 10))
            refs["preset_combo"].grid(row=2, column=1, columnspan=3, sticky="ew", pady=(0, 6))

            vars_dict["config_hint_var"].set(
                "Use predefined perceptibility and/or acceptability thresholds."
            )
            refs["config_hint_label"].grid(row=3, column=0, columnspan=4, sticky="ew", pady=(2, 0))

        elif mode_value == "custom":
            refs["custom_type_label"].grid(row=2, column=0, sticky="w", pady=(0, 6), padx=(0, 10))
            refs["custom_type_combo"].grid(row=2, column=1, columnspan=3, sticky="ew", pady=(0, 6))

            if custom_type == "single":
                refs["single_label"].grid(row=3, column=0, sticky="w", pady=(0, 6), padx=(0, 10))
                refs["single_entry"].grid(row=3, column=1, sticky="w", pady=(0, 6))

                vars_dict["config_hint_var"].set("Define one threshold greater than 0.")

                if single_text == "":
                    vars_dict["config_hint_var"].set("Enter a threshold greater than 0.")
                else:
                    _, err_single = self._parse_positive_threshold(single_text)
                    if err_single:
                        vars_dict["config_hint_var"].set(err_single)

                refs["config_hint_label"].grid(row=4, column=0, columnspan=4, sticky="ew", pady=(2, 0))

            else:
                refs["lower_label"].grid(row=3, column=0, sticky="w", pady=(0, 6), padx=(0, 10))
                refs["lower_entry"].grid(row=3, column=1, sticky="w", pady=(0, 6), padx=(0, 12))
                refs["upper_label"].grid(row=3, column=2, sticky="w", pady=(0, 6), padx=(8, 10))
                refs["upper_entry"].grid(row=3, column=3, sticky="w", pady=(0, 6))

                vars_dict["config_hint_var"].set(
                    "Define two thresholds greater than 0, with lower < upper."
                )

                if lower_text == "" or upper_text == "":
                    vars_dict["config_hint_var"].set(
                        "Enter both thresholds. Values must be greater than 0."
                    )
                else:
                    _, _, err_range = self._validate_custom_range(lower_text, upper_text)
                    if err_range:
                        vars_dict["config_hint_var"].set(err_range)

                refs["config_hint_label"].grid(row=4, column=0, columnspan=4, sticky="ew", pady=(2, 0))

        else:
            vars_dict["config_hint_var"].set("")

        if refs.get("variant") == "summary":
            self._update_threshold_summary_text(vars_dict)
            return

        if proto_lab is None or sample_lab is None:
            vars_dict["threshold_result_title_var"].set("Select a prototype to evaluate")
            vars_dict["threshold_result_detail_var"].set("")
            vars_dict["threshold_result_summary_var"].set("")
            self._apply_threshold_result_style(refs, "unavailable")
            return

        evaluation = self.evaluate_color_difference_threshold(
            sample_lab=sample_lab,
            prototype_lab=proto_lab,
            metric=self.threshold_settings.get("metric", "CIEDE2000"),
            threshold_settings=self.threshold_settings
        )

        metric_value = evaluation.get("metric_value", evaluation.get("delta_e"))
        status = evaluation.get("status", "unavailable")

        if metric_value is None:
            vars_dict["threshold_result_title_var"].set("Metric not available")
            vars_dict["threshold_result_detail_var"].set("Unable to compute selected metric")
            vars_dict["threshold_result_summary_var"].set(evaluation.get("summary", ""))
            self._apply_threshold_result_style(refs, status)
            return

        vars_dict["threshold_result_title_var"].set(
            evaluation.get("evaluation", "No evaluation available")
        )
        vars_dict["threshold_result_detail_var"].set(
            evaluation.get(
                "detail",
                f"{self.threshold_settings.get('metric', 'Metric')} = {metric_value:.3f}"
            )
        )
        vars_dict["threshold_result_summary_var"].set(
            evaluation.get("summary_visual", evaluation.get("summary", ""))
        )

        self._apply_threshold_result_style(refs, status)


    def _enable_original_rectangle_sampling(self, window_id, target_w, target_h):
        """
        Enable click + drag rectangle sampling for the ORIGINAL image shown in a floating window.

        The displayed image is anchored at the same position used in create_floating_window():
            x + 15, y + IMG_TOP_PAD
        so coordinates are mapped back to the original PIL image using the current
        floating window geometry and the current displayed size.
        """
        if not hasattr(self, "_original_sampling_state"):
            self._original_sampling_state = {}

        if not hasattr(self, "floating_window_state") or window_id not in self.floating_window_state:
            return

        if not hasattr(self, "pil_images_original") or window_id not in self.pil_images_original:
            return

        pil_original = self.pil_images_original[window_id]
        full_w, full_h = pil_original.size

        # Read current floating window geometry
        st = self.floating_window_state[window_id]
        wx, wy = st["x"], st["y"]

        # These values must match create_floating_window()
        IMG_LEFT_PAD = 12
        IMG_TOP_PAD = 44

        # Top-left corner of the displayed image inside the main canvas
        img_x = wx + IMG_LEFT_PAD
        img_y = wy + IMG_TOP_PAD

        self._original_sampling_state[window_id] = {
            "dragging": False,
            "drag_start": None,
            "rect_id": None,
            "img_x": img_x,
            "img_y": img_y,
            "draw_w": max(1, int(target_w)),
            "draw_h": max(1, int(target_h)),
            "full_w": full_w,
            "full_h": full_h,
        }

        # Replace the simple click behavior with press-drag-release behavior
        self.image_canvas.tag_bind(
            f"{window_id}_img_item",
            "<ButtonPress-1>",
            lambda e, wid=window_id: self._on_original_mouse_down(e, wid)
        )
        self.image_canvas.tag_bind(
            f"{window_id}_img_item",
            "<B1-Motion>",
            lambda e, wid=window_id: self._on_original_mouse_drag(e, wid)
        )
        self.image_canvas.tag_bind(
            f"{window_id}_img_item",
            "<ButtonRelease-1>",
            lambda e, wid=window_id: self._on_original_mouse_up(e, wid)
        )

        # Keep the fallback tag in sync too
        self.image_canvas.tag_bind(
            f"{window_id}_click_image",
            "<ButtonPress-1>",
            lambda e, wid=window_id: self._on_original_mouse_down(e, wid)
        )
        self.image_canvas.tag_bind(
            f"{window_id}_click_image",
            "<B1-Motion>",
            lambda e, wid=window_id: self._on_original_mouse_drag(e, wid)
        )
        self.image_canvas.tag_bind(
            f"{window_id}_click_image",
            "<ButtonRelease-1>",
            lambda e, wid=window_id: self._on_original_mouse_up(e, wid)
        )


    def _disable_original_rectangle_sampling(self, window_id):
        """
        Disable click/drag sampling for a floating image window and restore simple click picking.

        This is used whenever the displayed content is no longer the original image.
        """
        if hasattr(self, "_original_sampling_state") and window_id in self._original_sampling_state:
            self._clear_original_selection_rectangle(window_id)
            del self._original_sampling_state[window_id]

        # Remove drag-based bindings from both tags
        try:
            self.image_canvas.tag_unbind(f"{window_id}_img_item", "<ButtonPress-1>")
            self.image_canvas.tag_unbind(f"{window_id}_img_item", "<B1-Motion>")
            self.image_canvas.tag_unbind(f"{window_id}_img_item", "<ButtonRelease-1>")
        except Exception:
            pass

        try:
            self.image_canvas.tag_unbind(f"{window_id}_click_image", "<ButtonPress-1>")
            self.image_canvas.tag_unbind(f"{window_id}_click_image", "<B1-Motion>")
            self.image_canvas.tag_unbind(f"{window_id}_click_image", "<ButtonRelease-1>")
        except Exception:
            pass


    def _clip_original_canvas_point_to_image(self, x, y, window_id):
        """
        Clamp a canvas point to the visible bounds of the displayed original image.
        Returns the clipped (x, y) in canvas coordinates.
        """
        if not hasattr(self, "_original_sampling_state") or window_id not in self._original_sampling_state:
            return x, y

        state = self._original_sampling_state[window_id]

        img_x = state["img_x"]
        img_y = state["img_y"]
        draw_w = state["draw_w"]
        draw_h = state["draw_h"]

        clipped_x = max(img_x, min(img_x + draw_w, x))
        clipped_y = max(img_y, min(img_y + draw_h, y))

        return clipped_x, clipped_y

    def _on_original_mouse_down(self, event, window_id):
        """Start rectangle selection on an original floating image."""
        if not hasattr(self, "_original_sampling_state") or window_id not in self._original_sampling_state:
            return

        if self._has_active_job(window_id):
            return "break"

        state = self._original_sampling_state[window_id]

        canvas_x = self.image_canvas.canvasx(event.x)
        canvas_y = self.image_canvas.canvasy(event.y)
        start_x, start_y = self._clip_original_canvas_point_to_image(canvas_x, canvas_y, window_id)

        state["dragging"] = True
        state["drag_start"] = (start_x, start_y)

        if state["rect_id"] is not None:
            try:
                self.image_canvas.delete(state["rect_id"])
            except Exception:
                pass
            state["rect_id"] = None

        state["rect_id"] = self.image_canvas.create_rectangle(
            start_x, start_y, start_x, start_y,
            outline="#ff0000",
            width=2,
            tags=(window_id, "floating", f"{window_id}_selection_rect")
        )

        return "break"


    def _on_original_mouse_drag(self, event, window_id):
        """Update the selection rectangle while dragging, clipped to image bounds."""
        if not hasattr(self, "_original_sampling_state") or window_id not in self._original_sampling_state:
            return

        state = self._original_sampling_state[window_id]
        if not state.get("dragging") or state.get("rect_id") is None:
            return

        x0, y0 = state["drag_start"]
        canvas_x = self.image_canvas.canvasx(event.x)
        canvas_y = self.image_canvas.canvasy(event.y)
        x1, y1 = self._clip_original_canvas_point_to_image(canvas_x, canvas_y, window_id)

        self.image_canvas.coords(state["rect_id"], x0, y0, x1, y1)

        return "break"


    def _on_original_mouse_up(self, event, window_id):
        """
        Finish selection on the original image.

        Behavior:
        - Tiny drag: treat it as a single-pixel click.
        - Larger drag: compute the average RGB value inside the selected rectangle.
        """
        if not hasattr(self, "_original_sampling_state") or window_id not in self._original_sampling_state:
            return

        state = self._original_sampling_state[window_id]
        if not state.get("dragging"):
            return

        state["dragging"] = False

        if not hasattr(self, "pil_images_original") or window_id not in self.pil_images_original:
            return

        pil = self.pil_images_original[window_id].convert("RGB")

        img_x = state["img_x"]
        img_y = state["img_y"]
        draw_w = state["draw_w"]
        draw_h = state["draw_h"]
        full_w = state["full_w"]
        full_h = state["full_h"]

        x0, y0 = state["drag_start"]
        canvas_x = self.image_canvas.canvasx(event.x)
        canvas_y = self.image_canvas.canvasy(event.y)
        x1, y1 = self._clip_original_canvas_point_to_image(canvas_x, canvas_y, window_id)

        left = min(x0, x1)
        right = max(x0, x1)
        top = min(y0, y1)
        bottom = max(y0, y1)

        # Treat a tiny drag as a normal click. Use the same viewport-aware
        # conversion used by simple pixel picking, so zoom and Canvas scroll
        # cannot change which original pixel is selected.
        if (right - left) < 3 and (bottom - top) < 3:
            point = self._canvas_xy_to_original_image(window_id, canvas_x, canvas_y)
            if point is None:
                return "break"
            full_x, full_y, _rel_x, _rel_y = point

            r, g, b = pil.getpixel((full_x, full_y))
            pixel_lab = UtilsTools.rgb_to_lab((r, g, b))

            if self.COLOR_SPACE:
                self.display_pixel_value(full_x, full_y, pixel_lab, is_average=False, selection_info=None, image_id=window_id)

            return "break"

        # Convert rectangle from canvas coordinates to image-local coordinates
        left_i = left - img_x
        right_i = right - img_x
        top_i = top - img_y
        bottom_i = bottom - img_y

        # Clip to displayed image bounds
        left_i = max(0, min(draw_w, left_i))
        right_i = max(0, min(draw_w, right_i))
        top_i = max(0, min(draw_h, top_i))
        bottom_i = max(0, min(draw_h, bottom_i))

        if right_i <= left_i or bottom_i <= top_i:
            return "break"

        # Map the displayed rectangle through the CURRENT zoom viewport and
        # then into full-resolution original coordinates. This is the critical
        # step that keeps ROI sampling correct after Grid/Focus/zoom/scroll.
        crop = self._get_image_view_crop_box(window_id)
        source = getattr(self, "image_view_source", {}).get(window_id)
        original = getattr(self, "pil_images_original", {}).get(window_id)
        if crop is None or source is None or original is None:
            return "break"

        crop_left, crop_top, crop_right, crop_bottom = crop
        crop_w = crop_right - crop_left
        crop_h = crop_bottom - crop_top
        sw, sh = source.size
        ow, oh = original.size

        src_left = crop_left + (left_i / draw_w) * crop_w
        src_right = crop_left + (right_i / draw_w) * crop_w
        src_top = crop_top + (top_i / draw_h) * crop_h
        src_bottom = crop_top + (bottom_i / draw_h) * crop_h

        full_left = int((src_left / max(1, sw)) * ow)
        full_right = int(np.ceil((src_right / max(1, sw)) * ow))
        full_top = int((src_top / max(1, sh)) * oh)
        full_bottom = int(np.ceil((src_bottom / max(1, sh)) * oh))

        full_left = max(0, min(full_w - 1, full_left))
        full_right = max(0, min(full_w, full_right))
        full_top = max(0, min(full_h - 1, full_top))
        full_bottom = max(0, min(full_h, full_bottom))

        if full_right <= full_left or full_bottom <= full_top:
            return "break"

        # Compute the mean directly in CIELAB, converting each pixel first.
        crop = pil.crop((full_left, full_top, full_right, full_bottom))
        pixel_lab, _used = UtilsTools.mean_lab_with_filters(
            np.asarray(crop.convert("RGB"), dtype=np.uint8),
        )
        if pixel_lab is None:
            return "break"
        pixel_lab = tuple(float(v) for v in pixel_lab)
        # RGB represents the LAB mean for screen display only.
        r, g, b = UtilsTools.lab_to_rgb(pixel_lab)

        # Representative coordinates = rectangle center
        cx = (full_left + full_right) // 2
        cy = (full_top + full_bottom) // 2

        selection_info = {
            "type": "roi",
            "x1": full_left,
            "y1": full_top,
            "x2": full_right - 1,
            "y2": full_bottom - 1,
            "width": full_right - full_left,
            "height": full_bottom - full_top,
            "pixels": (full_right - full_left) * (full_bottom - full_top),
            "center_x": cx,
            "center_y": cy,
            "mean_rgb": (r, g, b),
        }

        if self.COLOR_SPACE:
            self.display_pixel_value(
                cx,
                cy,
                pixel_lab,
                is_average=True,
                selection_info=selection_info,
                image_id=window_id
            )

        return "break"


    @staticmethod
    def _pixel_info_elide(text, max_pixels, font):
        """End-elide by actual font width, rather than by character count."""
        text = str(text)
        if font.measure(text) <= max_pixels:
            return text
        ellipsis = "…"
        if max_pixels <= font.measure(ellipsis):
            return ellipsis
        low, high = 0, len(text)
        while low < high:
            mid = (low + high + 1) // 2
            if font.measure(text[:mid] + ellipsis) <= max_pixels:
                low = mid
            else:
                high = mid - 1
        return text[:low] + ellipsis


    def _fit_pixel_info_bar(self):
        """Center pixel information and preserve coordinates when space is tight.

        Each section is measured using the actual Tk font metrics.  If a ROI
        would overflow, compact its notation before eliding important values.
        The bar remains bounded by the Model 3D viewport at every size.
        """
        frame = getattr(self, "lab_value_frame", None)
        fields = getattr(self, "_pixel_info_values", None)
        content = getattr(self, "_pixel_info_content", None)
        if frame is None or fields is None or content is None:
            return
        try:
            if not frame.winfo_exists():
                return
            from tkinter import font as tkfont
            if not hasattr(self, "_pixel_info_value_font"):
                self._pixel_info_value_font = tkfont.Font(
                    root=self.root, family="Segoe UI", size=9)
                self._pixel_info_prefix_font = tkfont.Font(
                    root=self.root, family="Segoe UI", size=8, weight="bold")
            value_font = self._pixel_info_value_font
            prefix_font = self._pixel_info_prefix_font

            canvas_width = max(1, self.Canvas1.winfo_width())
            # Padding: 8px left, 31px for the inspection icon, two 1px
            # separators with their own horizontal padding.
            actual_width = content.winfo_width()
            if actual_width <= 1 or actual_width > canvas_width:
                actual_width = canvas_width - 43
            available = max(3, actual_width - 30)

            labels = ("Coords:", "LAB:", "Prototype:")
            raw_coords = str(fields["coords"])
            selection = (getattr(self, "_last_pixel_info", None) or {}).get(
                "selection_info")
            compact_coords = raw_coords
            if isinstance(selection, dict) and selection.get("type") == "roi":
                try:
                    compact_coords = (
                        f"ROI {selection['x1']},{selection['y1']}–"
                        f"{selection['x2']},{selection['y2']}")
                except (KeyError, TypeError, ValueError):
                    pass
            lab = fields["lab"]
            lab_full = f"{lab[0]:.2f}, {lab[1]:.2f}, {lab[2]:.2f}"
            lab_short = f"{lab[0]:.1f}, {lab[1]:.1f}, {lab[2]:.1f}"
            best = str(fields["best"])
            texts = [raw_coords, lab_full, best]
            lead_width = [prefix_font.measure(title) + 5 for title in labels]

            def measured(i):
                return lead_width[i] + value_font.measure(texts[i]) + 4

            desired = [measured(i) for i in range(3)]
            overflow = sum(desired) - available
            if overflow > 0 and compact_coords != raw_coords:
                # Save horizontal space by changing only the presentation;
                # original full ROI bounds stay in _last_pixel_info.
                texts[0] = compact_coords
                desired[0] = measured(0)
                overflow = sum(desired) - available
            if overflow > 0:
                texts[1] = lab_short
                desired[1] = measured(1)
                overflow = sum(desired) - available
            if overflow > 0:
                # Long prototype labels are the first to elide. For ordinary
                # short names, this ordering usually keeps all three values.
                minimums = [lead_width[0] + 16, lead_width[1] + 16,
                            lead_width[2] + 12]
                for i in (2, 0, 1):
                    if overflow <= 0:
                        break
                    reduction = min(overflow, max(0, desired[i] - minimums[i]))
                    desired[i] -= reduction
                    overflow -= reduction

            # One shared grid-uniform group preserves these measured widths,
            # while the child frames center each label + value as a unit.
            for column, size in zip((0, 2, 4), desired):
                content.grid_columnconfigure(
                    column, weight=max(1, int(size)), uniform="pixel_fields")
            refs = (self.coord_value, self.lab_value_print,
                    self.proto_value_text)
            for i, widget in enumerate(refs):
                room = max(1, desired[i] - lead_width[i] - 4)
                widget.configure(text=self._pixel_info_elide(
                    texts[i], room, value_font))
        except (tk.TclError, ValueError, TypeError):
            # Resizing or switching color spaces can destroy the overlay while
            # a deferred Tk redraw is still pending.
            return


    def display_pixel_value(self, x_original, y_original, pixel_lab, is_average=False, selection_info=None, image_id=None):
        """Display pixel/ROI LAB and the best category, using the active T-conorm.

        This status bar has a bounded width. Full coordinates, LAB precision and
        category memberships remain available in Image Inspection.
        """
        if not hasattr(self, "lab_value_frame") or not self.lab_value_frame.winfo_exists():
            bg, muted, text = "#ffffff", "#6b7280", "#1f2937"
            self.lab_value_frame = tk.Frame(
                self.Canvas1, bg=bg, bd=0, relief="flat",
                highlightthickness=1, highlightbackground="#d9dde3")
            self.lab_value_frame.place(
                relx=0.5, rely=0.987, relwidth=1.0, width=-12, anchor="s")
            content = tk.Frame(self.lab_value_frame, bg=bg)
            content.pack(fill="x", expand=True, padx=(8, 31), pady=3)
            self._pixel_info_content = content
            # Center the combined heading/value in each section, keeping the
            # two separators from the original Pixel Info design.
            for column, weight in ((0, 38), (2, 34), (4, 28)):
                content.grid_columnconfigure(column, weight=weight,
                                             uniform="pixel_fields")

            def make_field(column, title):
                group = tk.Frame(content, bg=bg)
                group.grid(row=0, column=column, sticky="nsew")
                centered = tk.Frame(group, bg=bg)
                centered.pack(expand=True)
                tk.Label(
                    centered, text=title, font=("Segoe UI", 8, "bold"),
                    bg=bg, fg=muted,
                ).pack(side="left", padx=(0, 3))
                result = tk.Label(
                    centered, font=("Segoe UI", 9), bg=bg, fg=text,
                    anchor="center", justify="center",
                )
                result.pack(side="left")
                return result

            self.coord_value = make_field(0, "Coords:")
            tk.Frame(content, bg="#d9dde3", width=1, height=18).grid(
                row=0, column=1, sticky="ns", padx=(6, 7), pady=1)
            self.lab_value_print = make_field(2, "LAB:")
            tk.Frame(content, bg="#d9dde3", width=1, height=18).grid(
                row=0, column=3, sticky="ns", padx=(6, 7), pady=1)
            self.proto_value_text = make_field(4, "Prototype:")

            search_icon = self.load_toolbar_icon("Search.png", (17, 17))
            inspection_button = tk.Label(
                self.lab_value_frame, image=search_icon, bg=bg,
                cursor="hand2", padx=3, pady=2)
            inspection_button.image = search_icon
            inspection_button.place(relx=1.0, rely=0.5, x=-3, anchor="e")
            inspection_button.bind(
                "<Button-1>", lambda _e: self.show_image_inspection_pixel())
            inspection_button.bind(
                "<Enter>", lambda _e: inspection_button.configure(bg="#f1f5f9"))
            inspection_button.bind(
                "<Leave>", lambda _e: inspection_button.configure(bg=bg))

            # Subscribe only once: repeated ROI picks must not accumulate
            # <Configure> handlers on the long-lived 3D canvas frame.
            if not getattr(self, "_pixel_info_resize_bound", False):
                self.Canvas1.bind(
                    "<Configure>", lambda _e: self._fit_pixel_info_bar(), add="+")
                self._pixel_info_resize_bound = True

        pixel_lab = tuple(float(v) for v in pixel_lab)
        space = self.fuzzy_color_space
        membership_degrees = space.calculate_membership(pixel_lab)
        winner = None
        winner_mu = 0.0
        if membership_degrees:
            # Avoid evaluating all granule geometries twice on ordinary
            # clicks. Only saturated/tied categories need the shared Mapping
            # All tie-breaker (distance to the nearest REAL granule).
            winner = max(membership_degrees, key=membership_degrees.get)
            if getattr(space, "is_granular", False):
                top = float(membership_degrees[winner])
                ties = sum(abs(float(score) - top) <= 1e-12
                           for score in membership_degrees.values())
                if ties > 1:
                    idx = space.best_prototype_index(pixel_lab)
                    if 0 <= idx < len(space.categories):
                        proposed = space.categories[idx].label
                        if proposed in membership_degrees:
                            winner = proposed
            winner_mu = float(membership_degrees[winner])
            top_memberships = sorted(
                membership_degrees.items(),
                key=lambda pair: (-float(pair[1]), 0 if pair[0] == winner else 1),
            )
        else:
            top_memberships = []

        # Keep the FULL sample for Image Inspection, never the shortened UI text.
        self._last_pixel_info = {
            "x": x_original,
            "y": y_original,
            "lab": pixel_lab,
            "is_average": bool(is_average),
            "selection_info": selection_info,
            "winner_label": winner if winner is not None else "None",
            "winner_mu": winner_mu,
            "top_memberships": top_memberships,
            "all_memberships": top_memberships,
            "image_id": image_id,
            "image_path": (
                getattr(self, "load_images_names", {}).get(image_id)
                if image_id is not None else None
            ),
        }

        if selection_info and selection_info.get("type") == "roi":
            coord_text = (
                f"ROI ({selection_info['x1']},{selection_info['y1']})"
                f"→({selection_info['x2']},{selection_info['y2']})"
            )
        else:
            coord_text = f"({x_original}, {y_original})"
        self._pixel_info_values = {
            "coords": coord_text, "lab": pixel_lab,
            "best": str(winner) if winner is not None else "—",
        }
        self._fit_pixel_info_bar()


    def _refresh_pixel_info_memberships(self):
        """Refresh the last visible sample after an in-session T-conorm change."""
        info = getattr(self, "_last_pixel_info", None)
        bar = getattr(self, "lab_value_frame", None)
        if not isinstance(info, dict) or bar is None:
            return
        try:
            if not bar.winfo_exists() or self.fuzzy_color_space is None:
                return
        except tk.TclError:
            return
        self.display_pixel_value(
            info["x"], info["y"], info["lab"],
            is_average=info.get("is_average", False),
            selection_info=info.get("selection_info"),
            image_id=info.get("image_id"),
        )


    def _close_image_inspection_window(self):
        """Close the persistent Image Inspection window if it is open."""
        controller = getattr(self, "_image_inspection_controller", None)
        if controller is not None:
            try:
                controller.close()
            except Exception:
                pass

        self._image_inspection_controller = None
        self._image_inspection_window = None


    def _reset_image_inspection_state(self):
        """
        Close Image Inspection and discard pixel/ROI information associated
        with the previous fuzzy color space.
        """
        self._close_image_inspection_window()
        self._last_pixel_info = None

        lab_frame = getattr(self, "lab_value_frame", None)
        if lab_frame is not None:
            try:
                if lab_frame.winfo_exists():
                    lab_frame.destroy()
            except Exception:
                pass

        for attr in (
            "lab_value_frame",
            "coord_value",
            "lab_value_print",
            "proto_value_text",
        ):
            try:
                if hasattr(self, attr):
                    delattr(self, attr)
            except Exception:
                pass


    def show_image_inspection_pixel(self):
        """
        Open Image Inspection using the sample currently selected in an image.
        This is the entry point used by the magnifying-glass button.
        """
        info = getattr(self, "_last_pixel_info", None)

        if not info:
            messagebox.showinfo(
                "Image Inspection",
                "Click on an image pixel first.",
                parent=self._get_active_dialog_parent()
            )
            return

        self.open_image_inspection(initial_info=info)


    def _safe_hex_from_rgb(self, rgb, default="#cccccc"):
        """Convert an RGB tuple into a safe HEX string."""
        try:
            r, g, b = rgb
            r = max(0, min(255, int(round(r))))
            g = max(0, min(255, int(round(g))))
            b = max(0, min(255, int(round(b))))
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return default


    def _get_proto_lab(self, label):
        """Return the LAB prototype tuple for a given label, or None if unavailable."""
        try:
            proto = self.color_data[label]["positive_prototype"]
            if isinstance(proto, np.ndarray):
                proto = proto.tolist()
            return tuple(float(v) for v in proto)
        except Exception:
            return None


    def _get_proto_rgb(self, label):
        """Return the RGB prototype tuple for a given label."""
        try:
            proto_lab = self._get_proto_lab(label)
            if proto_lab is None:
                return (200, 200, 200)
            return UtilsTools.lab_to_rgb(proto_lab)
        except Exception:
            return (200, 200, 200)


    def _get_proto_hex(self, label):
        """Return the HEX color for a given prototype label."""
        return self._safe_hex_from_rgb(self._get_proto_rgb(label))


    def _parse_positive_threshold(self, value):
        """
        Compatibility wrapper. Logic lives in ColorEvaluationManager.
        """
        manager = self._get_color_evaluation_manager()
        return manager.parse_positive_threshold(value)
    

    def _validate_custom_range(self, lower_value, upper_value):
        """
        Compatibility wrapper. Logic lives in ColorEvaluationManager.
        """
        manager = self._get_color_evaluation_manager()
        return manager.validate_custom_range(lower_value, upper_value)


    def evaluate_color_difference_threshold(self, sample_lab, prototype_lab, metric="CIEDE2000", threshold_settings=None):
        """
        Compatibility wrapper. Logic lives in ColorEvaluationManager.
        """
        manager = self._get_color_evaluation_manager()

        return manager.evaluate_color_difference_threshold(
            sample_lab=sample_lab,
            prototype_lab=prototype_lab,
            metric=metric,
            threshold_settings=threshold_settings or self.threshold_settings
        )




























    # ============================================================================================================================================================
    #  COLOR EVALUATION FUNCTIONS
    # ============================================================================================================================================================
    def color_evaluation(self):
        """Open a window to study color spaces and threshold configurations."""
        try:
            if hasattr(self, "_color_evaluation_window") and self._color_evaluation_window is not None:
                if self._color_evaluation_window.winfo_exists():
                    self._color_evaluation_window.lift()
                    self._color_evaluation_window.focus_force()
                    return
        except Exception:
            pass

        self._ensure_threshold_settings()

        win = tk.Toplevel(self.root)
        win.withdraw()
        self._color_evaluation_window = win

        win.title("Color Space Evaluation")
        WIN_W, WIN_H = 1080, 760
        win.geometry(f"{WIN_W}x{WIN_H}")
        win.minsize(980, 680)
        win.resizable(True, True)
        win.configure(bg="#f2f2f2")
        win.protocol("WM_DELETE_WINDOW", self._on_close_color_evaluation_window)

        # Fullscreen toggle for this specific Toplevel window
        def toggle_color_evaluation_fullscreen(event=None):
            try:
                current_state = bool(win.attributes("-fullscreen"))
                win.attributes("-fullscreen", not current_state)

                # When leaving fullscreen, restore a normal usable size
                if current_state:
                    win.geometry(f"{WIN_W}x{WIN_H}")
                    win.update_idletasks()
                    try:
                        self.center_popup(win, WIN_W, WIN_H)
                    except Exception:
                        pass

            except tk.TclError:
                # Fallback for systems/window managers where -fullscreen is not available
                try:
                    if platform.system() == "Windows":
                        if win.state() == "zoomed":
                            win.state("normal")
                            win.geometry(f"{WIN_W}x{WIN_H}")
                        else:
                            win.state("zoomed")
                    else:
                        screen_width = win.winfo_screenwidth()
                        screen_height = win.winfo_screenheight()
                        win.geometry(f"{screen_width}x{screen_height}+0+0")
                except Exception:
                    pass

        win.bind("<Escape>", toggle_color_evaluation_fullscreen)
        win.bind("<F11>", toggle_color_evaluation_fullscreen)

        self._build_color_evaluation_window(win)
        win.update_idletasks()

        # Prepare a full-size geometry while still hidden. Some window managers
        # only honour -fullscreen once a window is mapped, so its first frame
        # must already match the main window instead of flashing at 1080x760.
        try:
            self.root.update_idletasks()
            root_w, root_h = self.root.winfo_width(), self.root.winfo_height()
            if root_w < 980 or root_h < 680:
                raise ValueError("Main window dimensions unavailable")
            x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
            win.geometry(f"{root_w}x{root_h}+{x}+{y}")
        except (ValueError, tk.TclError):
            sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
            win.geometry(f"{sw}x{sh}+0+0")

        try:
            win.attributes("-fullscreen", True)
        except tk.TclError:
            if platform.system() == "Windows":
                try:
                    win.state("zoomed")
                except tk.TclError:
                    pass

        if platform.system() != "Windows":
            # If fullscreen is unsupported before mapping, size the hidden
            # window to the screen so even the fallback opens without a jump.
            try:
                if not bool(win.attributes("-fullscreen")):
                    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
                    win.geometry(f"{sw}x{sh}+0+0")
            except tk.TclError:
                pass

        win.deiconify()
        # Linux/X11 and some Windows managers may defer fullscreen until map.
        try:
            if not bool(win.attributes("-fullscreen")):
                win.attributes("-fullscreen", True)
        except tk.TclError:
            if platform.system() == "Windows":
                try:
                    win.state("zoomed")
                except tk.TclError:
                    pass
        win.focus_set()
        win.after_idle(self._set_color_evaluation_initial_sash)


    def _get_active_dialog_parent(self, fallback=None):
        """
        Return the best parent window for dialogs so they appear above the
        currently active tool window instead of the main root.
        """
        candidates = [
            getattr(self, "_image_based_creation_window", None),
            getattr(self, "_image_inspection_window", None),
            getattr(self, "_color_evaluation_window", None),
            fallback,
            self.root,
        ]

        for win in candidates:
            try:
                if win is not None and win.winfo_exists():
                    return win
            except Exception:
                pass

        return self.root


    def _on_close_color_evaluation_window(self):
        """Handle manual closing of the Color Evaluation window."""
        try:
            if hasattr(self, "_color_evaluation_window") and self._color_evaluation_window is not None:
                if self._color_evaluation_window.winfo_exists():
                    self._color_evaluation_window.destroy()
        except Exception:
            pass
        finally:
            self._color_evaluation_window = None
            self._color_evaluation_paned = None
            self._color_evaluation_vars = None


    def _set_color_evaluation_initial_sash(self):
        """Set the initial PanedWindow split after the window has its final size."""
        try:
            paned = getattr(self, "_color_evaluation_paned", None)
            if paned is None or not paned.winfo_exists():
                return

            paned.update_idletasks()
            total_w = paned.winfo_width()

            if total_w <= 1:
                return

            sash_x = max(330, min(int(total_w * 0.41), total_w - 540))  # color explorer | analysis
            paned.sash_place(0, sash_x, 1)
        except Exception:
            pass


    def _build_color_evaluation_window(self, win):
        """Build the full Color Evaluation window."""
        vars_dict = self._create_color_evaluation_vars()
        self._color_evaluation_vars = vars_dict

        main = tk.Frame(win, bg="#f2f2f2")
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # Top: Threshold settings
        refs = self._build_shared_threshold_panel(
            parent=main,
            vars_dict=vars_dict,
            title="Threshold Configuration",
            variant="summary"
        )

        # Color Space Data block
        table_panel = tk.Frame(main, bg="white", bd=1, relief="solid")
        table_panel.pack(fill="both", expand=True)

        # Compact header: the active FCS is immediately readable on the left;
        # file-loading actions stay together on the right. Only visual layout
        # changes here: both commands and their data flow are unchanged.
        header_container = tk.Frame(table_panel, bg="#f8fafc")
        header_container.pack(fill="x", padx=10, pady=(5, 4))

        space_identity = tk.Frame(header_container, bg="#f8fafc")
        space_identity.pack(side="left", fill="x", expand=True, padx=(8, 12))

        tk.Label(
            space_identity,
            text="Color Space Data",
            font=("Segoe UI", 12, "bold"),
            anchor="w",
            bg="#f8fafc",
            fg="#1f2937"
        ).pack(anchor="w")

        summary_row = tk.Frame(space_identity, bg="#f8fafc")
        summary_row.pack(anchor="w", pady=(3, 0))

        tk.Label(
            summary_row,
            text="Color space:",
            font=("Segoe UI", 9, "bold"),
            bg="#f8fafc",
            fg="#6b7280"
        ).pack(side="left", padx=(0, 5))

        tk.Label(
            summary_row,
            textvariable=vars_dict["space_name_var"],
            font=("Segoe UI", 9, "bold"),
            bg="#f8fafc",
            fg=UtilsTools.UI_ACCENT
        ).pack(side="left", padx=(0, 16))

        tk.Label(
            summary_row,
            textvariable=vars_dict["space_items_label_var"],
            font=("Segoe UI", 9, "bold"),
            bg="#f8fafc",
            fg="#6b7280"
        ).pack(side="left", padx=(0, 5))

        tk.Label(
            summary_row,
            textvariable=vars_dict["space_count_var"],
            font=("Segoe UI", 9, "bold"),
            bg="#f8fafc",
            fg="#1f2937"
        ).pack(side="left")

        buttons_row = tk.Frame(header_container, bg="#f8fafc")
        buttons_row.pack(side="right", anchor="center", padx=(4, 8), pady=3)

        tk.Button(
            buttons_row,
            text="Use loaded color space",
            command=lambda: self._load_current_color_space_for_evaluation(vars_dict),
            font=("Segoe UI", 9, "bold"),
            bg=UtilsTools.UI_ADD_CATEGORY_BG,
            fg=UtilsTools.UI_ADD_CATEGORY_FG,
            activebackground=UtilsTools.UI_ADD_CATEGORY_HOVER,
            activeforeground=UtilsTools.UI_ADD_CATEGORY_FG,
            relief="solid", bd=1, padx=11, pady=6,
            cursor="hand2",
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            buttons_row,
            text="Load new color space",
            command=lambda: self._load_external_color_space_for_evaluation(vars_dict),
            font=("Segoe UI", 9, "bold"),
            # Palette-Based Creation's shared "Add Color Source" style.
            bg=UtilsTools.UI_ADD_SOURCE_BG,
            fg=UtilsTools.UI_ADD_SOURCE_FG,
            activebackground=UtilsTools.UI_ADD_SOURCE_HOVER,
            activeforeground=UtilsTools.UI_ADD_SOURCE_FG,
            relief="solid", bd=1, padx=11, pady=6,
            cursor="hand2",
        ).pack(side="left")

        tk.Frame(table_panel, bg="#e5e7eb", height=1).pack(
            fill="x", padx=12, pady=(0, 7)
        )

        # PanedWindow real
        paned = tk.PanedWindow(
            table_panel,
            orient="horizontal",
            sashwidth=8,
            sashrelief="raised",
            bd=0,
            bg="white"
        )
        paned.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        left_panel = tk.Frame(paned, bg="white", bd=1, relief="solid")
        right_panel = tk.Frame(paned, bg="white", bd=1, relief="solid")

        paned.add(left_panel, minsize=315)
        paned.add(right_panel, minsize=520)

        self._color_evaluation_paned = paned

        # Left: searchable category/granule explorer.  All entries are real
        # LAB colors; category headers never stand in for a fictitious centroid.
        explorer_top = tk.Frame(left_panel, bg="#f6f8fb")
        explorer_top.pack(fill="x", padx=1, pady=(1, 0))
        tk.Label(explorer_top, text="Explore Colors", font=("Segoe UI", 11, "bold"),
                 bg="#f6f8fb", fg="#1f2937").pack(side="left", padx=10, pady=9)
        value_header = tk.Frame(explorer_top, bg="#f6f8fb")
        value_header.pack(side="right", padx=8)
        previous_mode_button = tk.Button(
            value_header, text="◀", font=("Segoe UI", 9), width=2,
            bg="white", fg="#1f2937", relief="solid", bd=1,
            cursor="hand2",
            command=lambda: self._rotate_color_evaluation_table_display_mode(
                vars_dict, direction=-1),
        )
        previous_mode_button.pack(side="left", padx=(0, 5))
        display_mode_combo = ttk.Combobox(
            value_header, textvariable=vars_dict["color_display_mode_var"],
            values=UtilsTools.get_supported_color_value_spaces(),
            state="readonly", width=12,
        )
        display_mode_combo.pack(side="left", padx=(0, 5))
        next_mode_button = tk.Button(
            value_header, text="▶", font=("Segoe UI", 9), width=2,
            bg="white", fg="#1f2937", relief="solid", bd=1,
            cursor="hand2",
            command=lambda: self._rotate_color_evaluation_table_display_mode(
                vars_dict, direction=1),
        )
        next_mode_button.pack(side="left")
        display_mode_combo.bind(
            "<<ComboboxSelected>>",
            lambda e: self._refresh_color_evaluation_table_display_mode(vars_dict)
        )
        vars_dict["color_display_navigation"] = (
            previous_mode_button, display_mode_combo, next_mode_button)

        search_holder = tk.Frame(left_panel, bg="white")
        search_holder.pack(fill="x", padx=9, pady=(6, 8))
        tk.Label(search_holder, text="Search", bg="white", fg="#6b7280",
                 font=("Segoe UI", 9)).pack(side="left", padx=(1, 8))
        tk.Entry(search_holder, textvariable=vars_dict["color_search_var"],
                 font=("Segoe UI", 10), relief="solid", bd=1,
                 highlightthickness=0).pack(side="left", fill="x", expand=True)

        tk.Frame(left_panel, bg="#e5e7eb", height=1).pack(fill="x")
        rows_canvas = tk.Canvas(left_panel, bg="white", highlightthickness=0, bd=0)
        rows_scroll = ttk.Scrollbar(left_panel, orient="vertical",
                                    command=rows_canvas.yview)
        rows_inner = tk.Frame(rows_canvas, bg="white")
        rows_inner.bind("<Configure>", lambda e: rows_canvas.configure(
            scrollregion=rows_canvas.bbox("all")))
        inner_window = rows_canvas.create_window((0, 0), window=rows_inner, anchor="nw")
        rows_canvas.bind("<Configure>", lambda e: rows_canvas.itemconfigure(
            inner_window, width=max(1, e.width)))
        rows_canvas.configure(yscrollcommand=rows_scroll.set)
        rows_canvas.pack(side="left", fill="both", expand=True)
        rows_scroll.pack(side="right", fill="y")
        self._register_vertical_mousewheel_canvas(rows_canvas)

        # Right panel
        tk.Label(
            right_panel,
            text="Color Comparison & Threshold Analysis",
            font=("Segoe UI", 11, "bold"),
            anchor="center",
            justify="center",
            bg="white",
            fg="#1f2937",
            padx=12,
            pady=6
        ).pack(fill="x")

        analysis_actions = tk.Frame(right_panel, bg="white")
        analysis_actions.pack(fill="x", padx=12, pady=(0, 4))

        def _run_analysis_action(action_key, callback):
            # Clear is a one-shot action, not a persistent analysis mode.
            self._set_color_evaluation_active_action(
                vars_dict, None if action_key == "clear" else action_key
            )
            callback()

        btn_compare = tk.Button(
            analysis_actions,
            text="Compare with Another Color",
            font=("Segoe UI", 9, "bold"),
            relief="solid", bd=1, padx=8, pady=4,
            cursor="hand2",
            command=lambda: _run_analysis_action(
                "compare",
                lambda: self._enable_color_evaluation_comparison_mode(vars_dict)
            )
        )
        btn_compare.pack(side="left", fill="x", expand=True, padx=(0, 6))

        btn_custom = tk.Button(
            analysis_actions,
            text="Evaluate Custom Color",
            font=("Segoe UI", 9, "bold"),
            relief="solid", bd=1, padx=8, pady=4,
            cursor="hand2",
            command=lambda: _run_analysis_action(
                "custom",
                lambda: self._open_custom_color_input_dialog(vars_dict)
            )
        )
        btn_custom.pack(side="left", fill="x", expand=True, padx=(0, 6))

        btn_sample = tk.Button(
            analysis_actions,
            text="Sample from Image",
            font=("Segoe UI", 9, "bold"),
            relief="solid", bd=1, padx=8, pady=4,
            cursor="hand2",
            command=lambda: _run_analysis_action(
                "sample",
                lambda: self._open_color_evaluation_image_sampler(vars_dict)
            )
        )
        btn_sample.pack(side="left", fill="x", expand=True)

        analysis_extra_actions = tk.Frame(right_panel, bg="white")
        analysis_extra_actions.pack(fill="x", padx=12, pady=(0, 5))

        btn_closest = tk.Button(
            analysis_extra_actions,
            text="Find closest prototype",
            font=("Segoe UI", 9, "bold"),
            relief="solid", bd=1, padx=8, pady=4,
            cursor="hand2",
            command=lambda: _run_analysis_action(
                "closest",
                lambda: self._show_color_evaluation_closest_prototypes(vars_dict)
            )
        )
        btn_closest.pack(side="left", fill="x", expand=True, padx=(0, 6))

        btn_clear = tk.Button(
            analysis_extra_actions,
            text="Clear Comparison",
            font=("Segoe UI", 9, "bold"),
            relief="solid", bd=1, padx=8, pady=4,
            cursor="hand2",
            command=lambda: _run_analysis_action(
                "clear",
                lambda: self._clear_color_evaluation_comparison(vars_dict)
            )
        )
        btn_clear.pack(side="left", fill="x", expand=True)

        vars_dict["closest_action_button"] = btn_closest
        vars_dict["analysis_action_buttons"] = {
            "compare": btn_compare,
            "custom": btn_custom,
            "sample": btn_sample,
            "closest": btn_closest,
            "clear": btn_clear,
        }

        self._set_color_evaluation_active_action(vars_dict, None)

        tk.Label(
            right_panel,
            textvariable=vars_dict["analysis_mode_var"],
            anchor="center",
            justify="center",
            bg="#f5f5f5",
            fg="#555555",
            font=("Segoe UI", 9, "italic"),
            padx=10,
            pady=3
        ).pack(fill="x", padx=12, pady=(0, 5))

        # Scrollable analysis body
        analysis_scroll_container = tk.Frame(right_panel, bg="white")
        analysis_scroll_container.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        analysis_canvas = tk.Canvas(
            analysis_scroll_container,
            bg="white",
            highlightthickness=0,
            bd=0
        )

        analysis_scrollbar = ttk.Scrollbar(
            analysis_scroll_container,
            orient="vertical",
            command=analysis_canvas.yview
        )

        analysis_body = tk.Frame(analysis_canvas, bg="white")

        analysis_body_window = analysis_canvas.create_window(
            (0, 0),
            window=analysis_body,
            anchor="nw"
        )

        analysis_canvas.configure(yscrollcommand=analysis_scrollbar.set)

        analysis_canvas.pack(side="left", fill="both", expand=True)
        analysis_scrollbar.pack(side="right", fill="y")

        def _update_analysis_scroll_region(event=None):
            try:
                analysis_canvas.configure(scrollregion=analysis_canvas.bbox("all"))
            except Exception:
                pass

        def _update_analysis_body_width(event=None):
            try:
                canvas_width = analysis_canvas.winfo_width()
                analysis_canvas.itemconfig(analysis_body_window, width=canvas_width)
            except Exception:
                pass

        analysis_body.bind("<Configure>", _update_analysis_scroll_region)
        analysis_canvas.bind("<Configure>", _update_analysis_body_width)

        self._register_vertical_mousewheel_canvas(analysis_canvas)

        # Side-by-side visual comparison. Color swatches share a neutral surround;
        # selected/secondary labels and LAB readouts are driven by existing state.
        preview_bg = "#f8fafc"
        preview_border = "#d6dce5"
        preview_text = "#1f2937"
        colors_row = tk.Frame(analysis_body, bg="white")
        colors_row.pack(fill="x", pady=(0, 5))
        colors_row.grid_columnconfigure(0, weight=1, uniform="colors")
        colors_row.grid_columnconfigure(1, weight=0)
        colors_row.grid_columnconfigure(2, weight=1, uniform="colors")

        def _build_comparison_preview(column, heading, name_var, meta_var, lab_var,
                                      initial_hex):
            card = tk.Frame(colors_row, bg=preview_bg, highlightthickness=1,
                            highlightbackground=preview_border)
            card.grid(row=0, column=column, sticky="nsew", padx=3, pady=2)
            tk.Label(card, text=heading, bg=preview_bg, fg="#6b7280",
                     font=("Segoe UI", 9, "bold")).pack(pady=(4, 2))
            swatch = tk.Canvas(card, width=74, height=70, bg=preview_bg,
                               highlightthickness=0, bd=0)
            swatch.pack(anchor="center")
            rect = swatch.create_rectangle(3, 3, 71, 67, fill=initial_hex,
                                            outline="#848b95", width=1)
            tk.Label(card, textvariable=name_var, bg=preview_bg, fg=preview_text,
                     font=("Segoe UI", 10, "bold"), wraplength=200,
                     justify="center").pack(fill="x", padx=6, pady=(2, 0))
            meta_label = tk.Label(
                card, textvariable=meta_var, bg=preview_bg, fg="#687284",
                font=("Segoe UI", 8), wraplength=200, justify="center")
            lab_label = tk.Label(
                card, textvariable=lab_var, bg=preview_bg, fg="#586174",
                font=("Consolas", 8), wraplength=210, justify="center")
            lab_label.pack(fill="x", padx=6, pady=(1, 4))

            def _show_meta_when_available(*_args):
                # An empty caption must not reserve a blank row in atomic spaces.
                if meta_var.get().strip():
                    if not meta_label.winfo_manager():
                        meta_label.pack(before=lab_label, fill="x", padx=6)
                elif meta_label.winfo_manager():
                    meta_label.pack_forget()

            meta_var.trace_add("write", _show_meta_when_available)
            _show_meta_when_available()
            swatch._pyfcs_meta_label = meta_label
            return swatch, rect

        primary_swatch, primary_rect = _build_comparison_preview(
            0, "Selected color", vars_dict["primary_name_var"],
            vars_dict["primary_meta_var"], vars_dict["primary_lab_var"], "#cccccc"
        )
        btn_swap = tk.Button(
            colors_row, text="⇄", font=("Segoe UI", 16, "bold"),
            bg="white", fg=UtilsTools.UI_ACCENT, relief="flat",
            activebackground=UtilsTools.UI_ACCENT_SOFT,
            cursor="hand2", state="disabled",
            command=lambda: self._swap_color_evaluation_rows(vars_dict)
        )
        btn_swap.grid(row=0, column=1, padx=5)
        vars_dict["swap_color_button"] = btn_swap
        secondary_swatch, secondary_rect = _build_comparison_preview(
            2, "Reference color", vars_dict["secondary_name_var"],
            vars_dict["secondary_meta_var"], vars_dict["secondary_lab_var"], "#f0f0f0"
        )

        # The compact Quick Samples strip keeps experiment history separate from
        # the color-space explorer. Each tile can be assigned to Selected or
        # Reference, pinned, or revisited without reopening a dialog.
        quick_outer = tk.Frame(analysis_body, bg="#f8fafc", highlightbackground="#d6dce5", highlightthickness=1)
        quick_header = tk.Frame(quick_outer, bg="#f8fafc")
        quick_header.pack(fill="x", padx=8, pady=(1, 1))
        quick_header.grid_columnconfigure(0, weight=1)
        quick_header.grid_columnconfigure(1, weight=0)
        quick_header.grid_columnconfigure(2, weight=1)

        # Left: section title. Center: target for selected sample. Right: clear.
        quick_title_btn = tk.Button(
            quick_header, text="▾  Quick Samples", font=("Segoe UI", 9, "bold"),
            fg=UtilsTools.UI_ACCENT_DARK, bg="#f8fafc", relief="flat", bd=0, cursor="hand2",
            command=lambda: self._toggle_color_evaluation_quick_samples(vars_dict))
        quick_title_btn.grid(row=0, column=0, sticky="w")
        target_controls = tk.Frame(quick_header, bg="#f8fafc")
        target_controls.grid(row=0, column=1)
        tk.Label(target_controls, text="Add to:", bg="#f8fafc", fg="#697386",
                 font=("Segoe UI", 8)).pack(side="left", padx=(0, 3))
        for value, label in (("A", "Selected"), ("B", "Reference")):
            tk.Radiobutton(target_controls, text=label, value=value,
                           variable=vars_dict["quick_samples_target_var"],
                           bg="#f8fafc", activebackground="#f8fafc",
                           font=("Segoe UI", 8), padx=1).pack(side="left", padx=(0, 1))
        tk.Button(quick_header, text="Clear recent", font=("Segoe UI", 8, "bold"),
                  bg="#f8fafc", fg=UtilsTools.UI_ACCENT, relief="flat", cursor="hand2",
                  activebackground="#f8fafc", activeforeground=UtilsTools.UI_ACCENT_DARK,
                  command=lambda: self._clear_color_evaluation_recent_samples(vars_dict)
                  ).grid(row=0, column=2, sticky="e")
        quick_body = tk.Frame(quick_outer, bg="#f8fafc")
        quick_body.pack(fill="x", padx=6, pady=(0, 1))

        # There is exactly one results card below Quick Samples. Avoid the
        # duplicate red/green status strip that hid the actual analysis.
        quick_canvas = tk.Canvas(quick_body, height=53, bd=0,
                                 highlightthickness=0, bg="#f8fafc")
        quick_scroll = ttk.Scrollbar(quick_body, orient="horizontal",
                                     command=quick_canvas.xview)
        quick_tiles = tk.Frame(quick_canvas, bg="#f8fafc")
        quick_canvas.create_window((0, 0), window=quick_tiles, anchor="nw")
        quick_canvas.configure(xscrollcommand=quick_scroll.set)
        quick_canvas.pack(fill="x", expand=True)
        quick_scroll.pack(fill="x")
        quick_empty_label = tk.Label(
            quick_body,
            text="No samples yet. Select a color or use Custom Color / Sample from Image.",
            bg="#f8fafc", fg="#6b7280", font=("Segoe UI", 9),
            anchor="center", justify="center", wraplength=450,
        )
        def _fit_quick_sample_scroll(_event=None):
            quick_canvas.configure(scrollregion=quick_canvas.bbox("all"))
            # Avoid losing a line of space to an unnecessary scrollbar.
            overflowing = quick_tiles.winfo_reqwidth() > quick_canvas.winfo_width() + 2
            if overflowing and not quick_scroll.winfo_manager():
                quick_scroll.pack(fill="x")
            elif not overflowing and quick_scroll.winfo_manager():
                quick_scroll.pack_forget()

        quick_tiles.bind("<Configure>", _fit_quick_sample_scroll)
        quick_canvas.bind("<Configure>", _fit_quick_sample_scroll)
        vars_dict.update({
            "quick_samples_outer": quick_outer,
            "quick_samples_tiles": quick_tiles,
            "quick_samples_canvas": quick_canvas,
            "quick_samples_scroll": quick_scroll,
            "quick_samples_empty_label": quick_empty_label,
            "quick_samples_title_btn": quick_title_btn,
            "quick_samples_body": quick_body,
            "quick_samples_after": colors_row,
        })
        self._render_color_evaluation_quick_samples(vars_dict)

        tk.Frame(analysis_body, bg="#e5e7eb", height=1).pack(fill="x", pady=(2, 3))

        # Results + Membership column
        results_block = tk.Frame(analysis_body, bg="white")
        results_block.pack(fill="both", expand=True)

        results_columns = tk.Frame(results_block, bg="white")
        results_columns.pack(fill="x", expand=False)

        # Fixed right column for Graphs / Membership.
        # Left column takes the remaining width.
        results_columns.grid_columnconfigure(0, weight=1)
        results_columns.grid_columnconfigure(1, weight=0, minsize=200)
        results_columns.grid_rowconfigure(0, weight=1)

        result_left = tk.Frame(results_columns, bg="white")
        result_left.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 8)
        )

        # Right side column: Membership panel + Graph buttons
        # Hidden by default; shown only when a custom/sample color exists.
        # Membership height will be synchronized with the Results card.
        right_side_column = tk.Frame(
            results_columns,
            bg="white"
        )
        right_side_column.grid(
            row=0,
            column=1,
            sticky="new",
            padx=(8, 0)
        )

        # Historical spacer retained only for compatibility (not packed).
        membership_title_spacer = tk.Label(
            right_side_column,
            text="",
            font=("Sans", 10, "bold"),
            anchor="w",
            bg="white"
        )
        # Do not pack here.

        # Membership panel
        membership_right = tk.Frame(
            right_side_column,
            bg="white",
            bd=1,
            relief="solid",
            width=300,
            height=220
        )
        membership_right.pack_propagate(False)

        tk.Label(
            membership_right,
            text="Membership Degree (μ)",
            font=("Sans", 10, "bold"),
            anchor="w",
            bg="white",
            padx=10,
            pady=8
        ).pack(fill="x")

        membership_list_canvas = tk.Canvas(
            membership_right,
            bg="white",
            highlightthickness=0,
            bd=0
        )

        membership_list_scroll = ttk.Scrollbar(
            membership_right,
            orient="vertical",
            command=membership_list_canvas.yview
        )

        membership_list_inner = tk.Frame(
            membership_list_canvas,
            bg="white"
        )

        membership_list_window = membership_list_canvas.create_window(
            (0, 0),
            window=membership_list_inner,
            anchor="nw"
        )

        membership_list_canvas.configure(
            yscrollcommand=membership_list_scroll.set
        )

        def _update_membership_list_scroll_region(event=None):
            try:
                membership_list_canvas.configure(
                    scrollregion=membership_list_canvas.bbox("all")
                )
            except Exception:
                pass

        def _update_membership_list_width(event=None):
            try:
                canvas_width = membership_list_canvas.winfo_width()
                membership_list_canvas.itemconfig(
                    membership_list_window,
                    width=max(canvas_width - 2, 1)
                )
            except Exception:
                pass

        membership_list_inner.bind(
            "<Configure>",
            _update_membership_list_scroll_region
        )

        membership_list_canvas.bind(
            "<Configure>",
            _update_membership_list_width
        )

        membership_list_canvas.pack(
            side="left",
            fill="both",
            expand=True,
            padx=(10, 0),
            pady=(0, 10)
        )

        membership_list_scroll.pack(
            side="right",
            fill="y",
            padx=(0, 8),
            pady=(0, 10)
        )

        self._register_vertical_mousewheel_canvas(membership_list_canvas)

        # Full-width horizontal graph toolbar, located beneath Results.
        # Membership stays alongside Results only for custom/sample colors.
        graph_buttons_card = self._create_color_evaluation_graph_buttons_card(
            results_block, vars_dict
        )
        graph_buttons_card.pack(fill="x", pady=(8, 0))
        right_side_column.grid_remove()

        # Show the results card directly, without a redundant "Results" title.
        result_card = tk.Frame(
            result_left,
            bg="#f7f7f7",
            bd=0,
            relief="flat",
            highlightthickness=2,
            highlightbackground="#bdbdbd",
            highlightcolor="#bdbdbd"
        )
        result_card.pack(fill="x", pady=(0, 2))

        result_header = tk.Frame(result_card, bg="#eeeeee")
        result_header.pack(fill="x")

        result_status_dot = tk.Canvas(
            result_header,
            width=18,
            height=18,
            bg="#eeeeee",
            highlightthickness=0,
            bd=0
        )
        result_status_dot.pack(side="left", padx=(10, 6), pady=8)

        result_status_dot_oval = result_status_dot.create_oval(
            3, 3, 15, 15,
            fill="#bdbdbd",
            outline="#bdbdbd"
        )

        result_title_label = tk.Label(
            result_header,
            textvariable=vars_dict["selected_result_var"],
            anchor="w",
            justify="left",
            bg="#eeeeee",
            font=("Sans", 10, "bold"),
            wraplength=300
        )
        result_title_label.pack(side="left", fill="x", expand=True, padx=(0, 6), pady=6)

        # Keep the metric value on the SAME line as the evaluation status.
        # It remains centered within the right half of the results header.
        result_value_label = tk.Label(
            result_header,
            textvariable=vars_dict["selected_detail_var"],
            anchor="center",
            justify="center",
            bg="#eeeeee",
            fg="#666666",
            font=("Segoe UI", 9, "bold"),
            wraplength=230,
        )
        result_value_label.pack(side="left", fill="x", expand=True, padx=(0, 6), pady=6)

        result_body = tk.Frame(result_card, bg="#f7f7f7")
        result_body.pack(fill="x", padx=10, pady=(6, 8))

        result_separator = tk.Frame(result_body, bg="#dddddd", height=1)
        result_separator.pack(fill="x", padx=4, pady=(0, 6))

        result_summary_row = tk.Frame(result_body, bg="#f7f7f7")
        result_summary_row.pack(fill="x")

        result_summary_icon = tk.Canvas(
            result_summary_row,
            width=20,
            height=20,
            bg="#f7f7f7",
            highlightthickness=0,
            bd=0
        )
        result_summary_icon.pack(side="left", padx=(0, 8), anchor="n")

        result_summary_icon_circle = result_summary_icon.create_oval(
            2, 2, 18, 18,
            outline="#666666",
            width=2
        )

        result_summary_icon_text = result_summary_icon.create_text(
            10, 10,
            text="!",
            fill="#666666",
            font=("Sans", 9, "bold")
        )

        result_text_container = tk.Frame(result_summary_row, bg="#f7f7f7")
        result_text_container.pack(side="left", fill="both", expand=True)

        result_summary_label = tk.Label(
            result_text_container,
            textvariable=vars_dict["selected_summary_var"],
            anchor="w",
            justify="left",
            bg="#f7f7f7",
            wraplength=300,
            font=("Consolas", 8)
        )
        result_summary_label.pack(anchor="w", fill="x")

        def _sync_membership_height_with_result(event=None):
            """
            Keep Membership Degree card visually aligned with the Results card.
            Graphs will then appear just below the Results height.
            """
            try:
                result_h = max(result_card.winfo_height(), 180)
                membership_right.configure(height=result_h)
            except Exception:
                pass

        result_card.bind("<Configure>", _sync_membership_height_with_result)
        result_card.after_idle(_sync_membership_height_with_result)

        # Color inspector
        def _create_color_evaluation_inspector_card(parent):
            """
            Create one Color Inspector card.

            Two instances are created:
            - one inside result_left for custom/sample mode;
            - one below results_columns for non-custom modes.
            Both use the same StringVars, so the text stays synchronized.
            """
            inspector_card = tk.Frame(
                parent,
                bg="#fafafa",
                bd=0,
                relief="flat",
                highlightthickness=1,
                highlightbackground="#bdbdbd",
                highlightcolor="#bdbdbd"
            )
            inspector_card.pack(fill="x", pady=(8, 0))

            inspector_header = tk.Frame(inspector_card, bg="#f3f3f3")
            inspector_header.pack(fill="x")

            tk.Label(
                inspector_header,
                textvariable=vars_dict["inspector_title_var"],
                font=("Sans", 9, "bold"),
                anchor="w",
                bg="#f3f3f3",
                padx=10,
                pady=5
            ).pack(side="left", fill="x", expand=True)

            tk.Label(
                inspector_header,
                textvariable=vars_dict["inspector_source_var"],
                font=("Sans", 8, "italic"),
                anchor="e",
                bg="#f3f3f3",
                fg="#666666",
                padx=10
            ).pack(side="right")

            inspector_body = tk.Frame(inspector_card, bg="#fafafa")
            inspector_body.pack(fill="x", padx=10, pady=(8, 8))

            inspector_preview = tk.Canvas(
                inspector_body,
                width=72,
                height=54,
                bg="#fafafa",
                highlightthickness=0,
                bd=0
            )
            inspector_preview.pack(side="left", padx=(0, 12), anchor="n")

            inspector_preview_rect = inspector_preview.create_rectangle(
                8, 8, 64, 46,
                fill="#d9d9d9",
                outline="#555555",
                width=1
            )

            inspector_values = tk.Frame(inspector_body, bg="#fafafa")
            inspector_values.pack(side="left", fill="x", expand=True)
            inspector_values.grid_columnconfigure(0, weight=1, uniform="inspector")
            inspector_values.grid_columnconfigure(1, weight=1, uniform="inspector")

            # First column: LAB, RGB, HEX. Second: CIELUV, LCh, CIE1931.
            # The field labels and values stay together when the inspector is
            # narrower (for example alongside the membership panel).
            for index, (label_text, variable) in enumerate((
                ("CIELAB", vars_dict["inspector_lab_var"]),
                ("RGB", vars_dict["inspector_rgb_var"]),
                ("HEX", vars_dict["inspector_hex_var"]),
                ("CIELUV", vars_dict["inspector_luv_var"]),
                ("LCh", vars_dict["inspector_lch_var"]),
                ("CIE1931", vars_dict["inspector_cie1931_var"]),
            )):
                column, row = divmod(index, 3)
                field = tk.Frame(inspector_values, bg="#fafafa")
                field.grid(row=row, column=column, sticky="new",
                           padx=(0, 9) if column == 0 else (9, 0), pady=(0, 3))
                tk.Label(
                    field, text=label_text, bg="#fafafa", fg="#333333",
                    anchor="w", font=("Segoe UI", 8, "bold"),
                ).pack(side="left", anchor="n", padx=(0, 5))
                value_label = tk.Label(
                    field, textvariable=variable, bg="#fafafa", fg="#222222",
                    anchor="w", justify="left", font=("Consolas", 8),
                    wraplength=230,
                )
                value_label.pack(side="left", fill="x", expand=True)

                def _fit_value_wrap(event, label=value_label, name=label_text):
                    # Keep both columns readable without expanding the inspector
                    # outside the narrow left panel in custom/sample mode.
                    label_width = (61 if name in ("CIELUV", "CIE1931") else 53)
                    label.configure(wraplength=max(72, event.width - label_width - 22))

                field.bind("<Configure>", _fit_value_wrap)

            return inspector_card, inspector_preview, inspector_preview_rect


        # Inspector used in custom/sample mode: left side, below Results.
        left_inspector_card, left_inspector_preview, left_inspector_preview_rect = (
            _create_color_evaluation_inspector_card(result_left)
        )

        # Inspector used in single / prototype-prototype mode:
        # full width below Results + Graphs.
        full_inspector_card, full_inspector_preview, full_inspector_preview_rect = (
            _create_color_evaluation_inspector_card(results_block)
        )

        # Initial mode is single color, so show the full-width inspector.
        left_inspector_card.pack_forget()

        vars_dict["left_inspector_card"] = left_inspector_card
        vars_dict["full_inspector_card"] = full_inspector_card

        vars_dict["inspector_preview"] = left_inspector_preview
        vars_dict["inspector_preview_rect"] = left_inspector_preview_rect

        vars_dict["inspector_previews"] = [
            (left_inspector_preview, left_inspector_preview_rect),
            (full_inspector_preview, full_inspector_preview_rect),
        ]

        # Store references
        vars_dict["analysis_result_refs"] = {
            "results_columns": results_columns,
            "result_left": result_left,

            "left_inspector_card": left_inspector_card,
            "full_inspector_card": full_inspector_card,

            "result_card": result_card,
            "result_header": result_header,
            "result_status_dot": result_status_dot,
            "result_status_dot_oval": result_status_dot_oval,
            "result_title_label": result_title_label,
            "result_body": result_body,
            "result_value_label": result_value_label,
            "value_in_header": True,
            "result_separator": result_separator,
            "result_summary_row": result_summary_row,
            "result_summary_icon": result_summary_icon,
            "result_summary_icon_circle": result_summary_icon_circle,
            "result_summary_icon_text": result_summary_icon_text,
            "result_summary_label": result_summary_label,

            "right_side_column": right_side_column,
            "membership_title_spacer": membership_title_spacer,
            "membership_right": membership_right,
            "membership_list_canvas": membership_list_canvas,
            "membership_list_inner": membership_list_inner,
            "graph_buttons_card": graph_buttons_card,
        }

        def _update_analysis_result_wrap(event=None):
            try:
                result_width = max(result_left.winfo_width() - 24, 200)
                title_wrap = max(result_width - 55, 140)
                summary_wrap = max(result_width - 70, 140)

                result_title_label.config(wraplength=max(120, title_wrap // 2))
                result_value_label.config(wraplength=max(120, result_width // 2 - 35))
                result_summary_label.config(wraplength=summary_wrap)
            except Exception:
                pass

        results_block.bind("<Configure>", _update_analysis_result_wrap)

        vars_dict["rows_canvas"] = rows_canvas
        vars_dict["rows_inner"] = rows_inner
        vars_dict["primary_swatch"] = primary_swatch
        vars_dict["primary_rect"] = primary_rect
        vars_dict["secondary_swatch"] = secondary_swatch
        vars_dict["secondary_rect"] = secondary_rect
        vars_dict["color_row_refs"] = {}
        vars_dict["primary_label"] = None
        vars_dict["secondary_label"] = None
        vars_dict["comparison_mode"] = False

        for widget in (
            refs["metric_family_combo"],
            refs["metric_combo"],
            refs["mode_combo"],
            refs["preset_combo"],
            refs["custom_type_combo"],
        ):
            widget.bind(
                "<<ComboboxSelected>>",
                lambda e: self._refresh_color_evaluation_threshold_ui(vars_dict, refs)
            )

        for widget in (
            refs["single_entry"],
            refs["lower_entry"],
            refs["upper_entry"],
        ):
            widget.bind(
                "<KeyRelease>",
                lambda e: self._refresh_color_evaluation_threshold_ui(vars_dict, refs)
            )

        self._refresh_color_evaluation_threshold_ui(vars_dict, refs)
        self._load_current_color_space_for_evaluation(vars_dict)
        self._update_color_evaluation_graph_buttons(vars_dict)


    def _set_color_evaluation_inspector_layout(self, vars_dict):
        """
        Switch Color Inspector placement depending on the current analysis mode.

        - Single color / prototype-prototype comparison:
            show full-width inspector below Results + Graphs.
        - Custom/sample color:
            show left inspector below Results, next to Membership/Graphs.
        """
        refs = vars_dict.get("analysis_result_refs", {})

        left_inspector_card = refs.get("left_inspector_card") or vars_dict.get("left_inspector_card")
        full_inspector_card = refs.get("full_inspector_card") or vars_dict.get("full_inspector_card")

        has_custom = any(
            vars_dict.get(prefix + "_mode") == "custom"
            and vars_dict.get(prefix + "_custom_lab") is not None
            for prefix in ("primary", "secondary")
        )

        try:
            if has_custom:
                if full_inspector_card is not None:
                    full_inspector_card.pack_forget()

                if (
                    left_inspector_card is not None
                    and not left_inspector_card.winfo_ismapped()
                ):
                    left_inspector_card.pack(fill="x", pady=(8, 0))

            else:
                if left_inspector_card is not None:
                    left_inspector_card.pack_forget()

                if (
                    full_inspector_card is not None
                    and not full_inspector_card.winfo_ismapped()
                ):
                    full_inspector_card.pack(fill="x", pady=(8, 0))

        except Exception:
            pass


    def _get_evaluation_proto_hex(self, vars_dict, label):
        """Return HEX color for a prototype in the Color Evaluation loaded space."""
        refs_map = vars_dict.get("color_row_refs", {})

        if label in refs_map:
            return refs_map[label].get("hex", "#cccccc")

        data_source = vars_dict.get("loaded_space_data") or {}

        try:
            color_value = data_source[label]

            lab = None
            if isinstance(color_value, dict):
                if "positive_prototype" in color_value:
                    lab = color_value["positive_prototype"]
                elif "Color" in color_value:
                    lab = color_value["Color"]

            if lab is None:
                return "#cccccc"

            lab_arr = np.array(lab, dtype=float)
            rgb = UtilsTools.lab_to_rgb(lab_arr)
            return self._safe_hex_from_rgb(rgb)

        except Exception:
            return "#cccccc"


    def _update_color_evaluation_membership_panel(self, vars_dict, sample_lab=None):
        """
        Update the membership list shown on the right side of the Color Evaluation window.

        Layout behavior:
        - The right column always stays visible.
        - Graphs are always shown on the right.
        - Membership Degree is shown only when a custom/sample color exists.
        - Graph buttons are filtered depending on the current state.
        """
        refs = vars_dict.get("analysis_result_refs", {})

        right_side_column = refs.get("right_side_column")
        membership_title_spacer = refs.get("membership_title_spacer")
        membership_right = refs.get("membership_right")
        membership_list_canvas = refs.get("membership_list_canvas")
        list_inner = refs.get("membership_list_inner")
        graph_buttons_card = refs.get("graph_buttons_card")
        result_card = refs.get("result_card")

        if membership_right is None or membership_list_canvas is None or list_inner is None:
            return

        # Rebuild category membership rows only when a sampled/custom color is active.
        for child in list_inner.winfo_children():
            child.destroy()
        self._update_color_evaluation_graph_buttons(vars_dict)

        has_custom_membership = sample_lab is not None
        if not has_custom_membership:
            try:
                membership_right.pack_forget()
                if right_side_column is not None:
                    right_side_column.grid_remove()
                membership_list_canvas.yview_moveto(0)
            except tk.TclError:
                pass
            return

        try:
            if right_side_column is not None:
                right_side_column.grid(row=0, column=1, sticky="new", padx=(8, 0))
            if not membership_right.winfo_manager():
                membership_right.pack(side="top", fill="x")
            if result_card is not None:
                membership_right.configure(height=max(result_card.winfo_height(), 180))
        except tk.TclError:
            pass

        memberships = self._calculate_evaluation_memberships(vars_dict, sample_lab)

        if not memberships:
            tk.Label(
                list_inner,
                text="No fuzzy membership data available.",
                bg="white",
                fg="#777777",
                anchor="nw",
                justify="left",
                wraplength=210,
                font=("Sans", 9, "italic")
            ).pack(fill="x", padx=4, pady=4)

            try:
                membership_list_canvas.update_idletasks()
                membership_list_canvas.configure(
                    scrollregion=membership_list_canvas.bbox("all")
                )
                membership_list_canvas.yview_moveto(0)
            except Exception:
                pass

            return

        visible_memberships = [
            (label, mu)
            for label, mu in memberships
            if float(mu) > 0
        ]

        if not visible_memberships:
            tk.Label(
                list_inner,
                text="All membership degrees are 0.0000 for this color.",
                bg="white",
                fg="#777777",
                anchor="nw",
                justify="left",
                wraplength=210,
                font=("Sans", 9, "italic")
            ).pack(fill="x", padx=4, pady=4)

            try:
                membership_list_canvas.update_idletasks()
                membership_list_canvas.configure(
                    scrollregion=membership_list_canvas.bbox("all")
                )
                membership_list_canvas.yview_moveto(0)
            except Exception:
                pass

            return

        for label, mu in visible_memberships:
            row = tk.Frame(list_inner, bg="white")
            row.pack(fill="x", padx=4, pady=4)

            proto_hex = self._get_evaluation_proto_hex(vars_dict, label)

            swatch = tk.Canvas(
                row,
                width=16,
                height=16,
                bg="white",
                highlightthickness=0,
                bd=0
            )
            swatch.pack(side="left", padx=(0, 6), pady=1)

            swatch.create_rectangle(
                1, 1, 15, 15,
                fill=proto_hex,
                outline="#707070"
            )

            text_block = tk.Frame(row, bg="white")
            text_block.pack(side="left", fill="x", expand=True)

            tk.Label(
                text_block,
                text=str(label),
                bg="white",
                anchor="w",
                justify="left",
                font=("Sans", 9),
                wraplength=155
            ).pack(anchor="w", fill="x")

            tk.Label(
                text_block,
                text=f"μ = {float(mu):.4f}",
                bg="white",
                fg="#555555",
                anchor="w",
                justify="left",
                font=("Consolas", 8)
            ).pack(anchor="w", fill="x", pady=(1, 0))

        try:
            membership_list_canvas.update_idletasks()
            membership_list_canvas.configure(
                scrollregion=membership_list_canvas.bbox("all")
            )
            membership_list_canvas.yview_moveto(0)
        except Exception:
            pass


    def _load_color_space_for_evaluation_from_file(self, filename):
        """
        Load a color space file for evaluation purposes without replacing
        the application's main active color space.
        """
        data = self.fuzzy_manager.load_color_file(filename)

        result = {
            "file_path": filename,
            "space_name": os.path.splitext(os.path.basename(filename))[0],
            "type": data.get("type"),
            "color_data": data.get("color_data", {}),
            "fuzzy_color_space": None,
            "cores": None,
            "supports": None,
            "prototypes": None,
        }

        if data.get("type") == "fcs":
            fuzzy_cs = data.get("fuzzy_color_space")
            if fuzzy_cs is not None:
                try:
                    fuzzy_cs.precompute_pack()
                except Exception:
                    pass

                result["fuzzy_color_space"] = fuzzy_cs
                result["cores"] = getattr(fuzzy_cs, "cores", None)
                result["supports"] = getattr(fuzzy_cs, "supports", None)
                result["prototypes"] = getattr(fuzzy_cs, "prototypes", None) # Used as 0.5-cut in plots

        return result
    

    def _get_current_color_space_for_evaluation(self):
        """
        Return the currently active application color space in a format
        suitable for the Color Space Evaluation window.
        """
        data_source = getattr(self, "color_data", None)
        if not data_source:
            data_source = getattr(self, "edit_color_data", None)

        if not data_source:
            return None

        fuzzy_cs = getattr(self, "fuzzy_color_space", None)

        return {
            "file_path": getattr(self, "file_path", None),
            "space_name": getattr(self, "file_base_name", "Current loaded color space"),
            "type": "fcs" if fuzzy_cs is not None else "cns",
            "color_data": data_source,
            "fuzzy_color_space": fuzzy_cs,
            "cores": getattr(self, "cores", None),
            "supports": getattr(self, "supports", None),
            "prototypes": getattr(self, "prototypes", None),
        }


    def _create_color_evaluation_vars(self):
        """Create and return all Tk variables used by the Color Evaluation window."""
        vars_dict = {
            "space_name_var": tk.StringVar(value="None"),
            "space_count_var": tk.StringVar(value="0"),
            "space_items_label_var": tk.StringVar(value="Prototypes:"),
            "color_search_var": tk.StringVar(value=""),
            "category_rows": [],
            "category_open": {},
            "color_row_order": [],
            "color_display_mode_var": tk.StringVar(value="CIELAB"),

            "analysis_mode_var": tk.StringVar(value="Select a color from the list."),
            "primary_name_var": tk.StringVar(value="None"),
            "secondary_name_var": tk.StringVar(value="None"),
            "primary_meta_var": tk.StringVar(value=""),
            "secondary_meta_var": tk.StringVar(value=""),
            "primary_lab_var": tk.StringVar(value=""),
            "secondary_lab_var": tk.StringVar(value=""),

            "selected_result_var": tk.StringVar(value="Select a prototype from the list."),
            "selected_detail_var": tk.StringVar(value=""),
            "selected_summary_var": tk.StringVar(value=""),

            # Color inspector
            "inspector_title_var": tk.StringVar(value="Color Inspector"),
            "inspector_source_var": tk.StringVar(value="Source: -"),

            "inspector_rgb_var": tk.StringVar(value="-"),
            "inspector_lab_var": tk.StringVar(value="-"),
            "inspector_hex_var": tk.StringVar(value="-"),
            "inspector_luv_var": tk.StringVar(value="-"),
            "inspector_lch_var": tk.StringVar(value="-"),
            "inspector_cie1931_var": tk.StringVar(value="-"),

            "loaded_space_data": None,
            "loaded_space_name": "",
            "loaded_space_type": None,
            "loaded_fuzzy_color_space": None,
            "loaded_cores": None,
            "loaded_supports": None,
            "loaded_prototypes": None,
            "loaded_file_path": None,

            # Comparison state
            "secondary_mode": None,          # None | "row" | "custom"
            "secondary_custom_lab": None,
            "secondary_custom_rgb": None,
            "secondary_custom_hex": None,
            "secondary_custom_name": "Custom Color",

            "analysis_view_mode": "comparison",   # "comparison" | "closest"
            "primary_mode": "row",             # "row" | "custom"
            "primary_custom_lab": None,
            "primary_custom_rgb": None,
            "primary_custom_hex": None,
            "primary_custom_name": "Sample",
            "primary_custom_source": "custom",
            "secondary_custom_source": "custom",
            "quick_samples": [],
            "quick_samples_sequence": 0,
            "quick_samples_target_var": tk.StringVar(value="B"),
            "quick_samples_expanded": True,

            # Last Threshold Analysis action
            "active_analysis_action": None,
            "analysis_action_buttons": {},

            # Closest ranking cache
            "closest_ranking": [],
            "closest_best": None,
            "closest_metric": None,
        }

        return self._merge_threshold_vars(vars_dict)
    

    def _set_color_evaluation_active_action(self, vars_dict, action_key):
        """
        Visually mark the last pressed button in the Threshold Analysis action area.
        """
        vars_dict["active_analysis_action"] = action_key

        buttons = vars_dict.get("analysis_action_buttons", {})

        # Clear is a one-shot action; only persistent analysis modes are highlighted.
        for key, button in buttons.items():
            try:
                is_active = key == action_key and key != "clear"
                button.configure(
                    bg=UtilsTools.UI_ACCENT_SOFT if is_active else "#f8fafc",
                    fg=UtilsTools.UI_ACCENT_DARK if is_active else "#1f2937",
                    activebackground=UtilsTools.UI_ACCENT_HOVER if is_active else UtilsTools.UI_ACCENT_SOFT,
                    activeforeground=UtilsTools.UI_ACCENT_DARK if is_active else UtilsTools.UI_ACCENT,
                    relief="solid",
                    bd=2 if is_active else 1,
                    highlightthickness=0,
                )
            except Exception:
                pass


    def _refresh_color_evaluation_threshold_ui(self, vars_dict, refs):
        """
        Refresh threshold controls, validate inputs, update summary,
        and preserve the active analysis view.
        """
        self._refresh_shared_threshold_ui(
            vars_dict=vars_dict,
            refs=refs,
            proto_lab=None,
            sample_lab=None
        )

        # Clear cached ranking because metric or thresholds may have changed.
        vars_dict["closest_ranking"] = []
        vars_dict["closest_best"] = None
        vars_dict["closest_metric"] = None

        if vars_dict.get("analysis_view_mode") == "closest":
            self._show_color_evaluation_closest_prototypes(vars_dict)
        else:
            self._refresh_color_evaluation_comparison(vars_dict)


    def _get_color_evaluation_threshold_description(self):
        """
        Return a compact textual description of the active threshold settings.
        """
        self._ensure_threshold_settings()
        manager = self._get_color_evaluation_manager()

        return manager.get_threshold_description(
            threshold_settings=self.threshold_settings,
            include_metric_description=True
        )


    def _load_current_color_space_for_evaluation(self, vars_dict):
        """Load the currently active color space into the evaluation window."""
        loaded = self._get_current_color_space_for_evaluation()

        if not loaded or not loaded.get("color_data"):
            vars_dict["space_name_var"].set("None")
            vars_dict["space_count_var"].set("0")

            vars_dict["loaded_space_data"] = None
            vars_dict["loaded_space_name"] = ""
            vars_dict["loaded_space_type"] = None
            vars_dict["loaded_fuzzy_color_space"] = None
            vars_dict["loaded_cores"] = None
            vars_dict["loaded_supports"] = None
            vars_dict["loaded_prototypes"] = None
            vars_dict["loaded_file_path"] = None

            self._render_color_evaluation_cards(vars_dict, {})
            return

        vars_dict["loaded_space_data"] = loaded["color_data"]
        vars_dict["loaded_space_name"] = loaded["space_name"]
        vars_dict["loaded_space_type"] = loaded["type"]
        vars_dict["loaded_fuzzy_color_space"] = loaded["fuzzy_color_space"]
        vars_dict["loaded_cores"] = loaded["cores"]
        vars_dict["loaded_supports"] = loaded["supports"]
        vars_dict["loaded_prototypes"] = loaded["prototypes"]
        vars_dict["loaded_file_path"] = loaded["file_path"]

        self._update_color_evaluation_space_summary(vars_dict)
        self._render_color_evaluation_cards(vars_dict, loaded["color_data"])


    def _load_external_color_space_for_evaluation(self, vars_dict):
        """Load another color space from disk for inspection/evaluation only."""
        try:
            if self._color_evaluation_window is not None and self._color_evaluation_window.winfo_exists():
                self._color_evaluation_window.lift()
                self._color_evaluation_window.focus_force()
        except Exception:
            pass

        filename = UtilsTools.prompt_file_selection(
            "fuzzy_color_spaces/",
            parent=self._color_evaluation_window
        )
        if not filename:
            return

        try:
            loaded = self._load_color_space_for_evaluation_from_file(filename)
        except Exception as exc:
            self.custom_warning(
                "Color Space Could Not Be Loaded",
                f"The selected file could not be read:\n{exc}",
                parent=getattr(self, "_color_evaluation_window", None)
            )
            return

        if not loaded or not isinstance(loaded.get("color_data"), dict):
            self.custom_warning(
                "Invalid Color Space",
                "The selected file contains no valid color-space data.",
                parent=getattr(self, "_color_evaluation_window", None)
            )
            return

        vars_dict["loaded_space_data"] = loaded["color_data"]
        vars_dict["loaded_space_name"] = loaded["space_name"]
        vars_dict["loaded_space_type"] = loaded["type"]
        vars_dict["loaded_fuzzy_color_space"] = loaded["fuzzy_color_space"]
        vars_dict["loaded_cores"] = loaded["cores"]
        vars_dict["loaded_supports"] = loaded["supports"]
        vars_dict["loaded_prototypes"] = loaded["prototypes"]
        vars_dict["loaded_file_path"] = loaded["file_path"]

        self._update_color_evaluation_space_summary(vars_dict)
        self._render_color_evaluation_cards(vars_dict, loaded["color_data"])


    def _calculate_evaluation_memberships(self, vars_dict, sample_lab):
        """
        Compatibility wrapper. Logic lives in ColorEvaluationManager.
        """
        manager = self._get_color_evaluation_manager()
        return manager.calculate_memberships(
            fuzzy_color_space=vars_dict.get("loaded_fuzzy_color_space"),
            sample_lab=sample_lab
        )


    def _update_color_evaluation_space_summary(self, vars_dict):
        data_source = vars_dict.get("loaded_space_data") or {}
        space_name = vars_dict.get("loaded_space_name", "Unnamed color space")
        valid_rows = self._extract_color_space_rows(data_source)
        vars_dict["space_name_var"].set(space_name)
        space = vars_dict.get("loaded_fuzzy_color_space")
        if isinstance(space, GranularFuzzyColorSpace):
            n_granules = sum(len(c.prototypes) for c in space.categories)
            vars_dict["space_items_label_var"].set("Categories / granules:")
            vars_dict["space_count_var"].set(f"{len(space.categories)} / {n_granules}")
        else:
            vars_dict["space_items_label_var"].set("Prototypes:")
            vars_dict["space_count_var"].set(str(len(valid_rows)))
        closest_button = vars_dict.get("closest_action_button")
        if closest_button is not None:
            closest_button.configure(text=("Find closest granule" if
                isinstance(space, GranularFuzzyColorSpace) else "Find closest prototype"))


    def _extract_color_space_rows(self, data_source):
        """
        Compatibility wrapper. Logic lives in ColorEvaluationManager.
        """
        manager = self._get_color_evaluation_manager()
        return manager.extract_color_space_rows(data_source)


    def _set_custom_color_as_evaluation_comparison(self, vars_dict, sample_lab,
                                                    sample_rgb, sample_hex,
                                                    name="Custom Color", source="custom"):
        """Compatibility entry point: a new external color is assigned to B."""
        return self._use_color_evaluation_external_sample(
            vars_dict, name=name, lab=sample_lab, rgb=sample_rgb,
            hex_color=sample_hex, source=source, target="B")

    def _refresh_color_evaluation_table_display_mode(self, vars_dict):
        """
        Refresh the value column of the Color Evaluation table according to
        the selected color space display mode.
        """
        try:
            display_mode = vars_dict["color_display_mode_var"].get()
        except Exception:
            display_mode = "CIELAB"

        for label, refs in vars_dict.get("color_row_refs", {}).items():
            value_label = refs.get("value_label")
            lab = refs.get("lab")

            if value_label is None or lab is None:
                continue

            try:
                value_label.configure(text=self._format_color_evaluation_value(
                    lab, display_mode, rgb=refs.get("rgb")))
            except Exception:
                value_label.configure(text="-")

        # The two comparison cards use the same display mode as Explore Colors.
        # Updating only the captions avoids recalculating memberships or ΔE.
        self._refresh_color_evaluation_preview_values(vars_dict)


    def _refresh_color_evaluation_preview_values(self, vars_dict):
        """Update both preview captions without changing their source LAB data."""
        mode = vars_dict["color_display_mode_var"].get()
        for side, prefix in (("A", "primary"), ("B", "secondary")):
            sample = self._get_color_evaluation_side_sample(vars_dict, side)
            vars_dict[prefix + "_lab_var"].set(
                self._format_color_evaluation_value(
                    sample["lab"], mode, rgb=sample["rgb"],
                    hex_color=sample["hex"], card=True)
                if sample else ""
            )


    def _rotate_color_evaluation_table_display_mode(self, vars_dict, direction=1):
        """Cycle the displayed color coordinates forward or backward."""
        spaces = UtilsTools.get_supported_color_value_spaces()
        if not spaces:
            return

        try:
            current = UtilsTools.normalize_color_value_space(
                vars_dict["color_display_mode_var"].get()
            )
        except Exception:
            current = "CIELAB"

        if current not in spaces:
            next_space = spaces[0] if direction >= 0 else spaces[-1]
        else:
            next_space = spaces[(spaces.index(current) + (1 if direction >= 0 else -1))
                                % len(spaces)]

        vars_dict["color_display_mode_var"].set(next_space)
        self._refresh_color_evaluation_table_display_mode(vars_dict)


    @staticmethod
    def _color_evaluation_actual_entries(data_source, fuzzy_space):
        """Return selectable real LAB sites, grouped by their model categories.

        Never evaluate a granular category via its legacy representative: a
        category is a fuzzy union and does not have a unique comparison LAB.
        """
        if isinstance(fuzzy_space, GranularFuzzyColorSpace):
            groups = []
            for category in fuzzy_space.categories:
                entries = []
                for proto in category.prototypes:
                    try:
                        lab = np.asarray(fuzzy_space.lab_from_model(proto.positive),
                                         dtype=float).reshape(3)
                        if np.isfinite(lab).all():
                            entries.append((proto.label, lab))
                    except (TypeError, ValueError):
                        continue
                if entries:
                    groups.append((category.label, entries))
            return groups
        groups = []
        if isinstance(data_source, dict):
            for label, value in data_source.items():
                if not isinstance(value, dict):
                    continue
                lab = value.get("positive_prototype", value.get("Color"))
                try:
                    lab = np.asarray(lab, dtype=float).reshape(3)
                    if np.isfinite(lab).all():
                        groups.append((label, [(label, lab)]))
                except (TypeError, ValueError):
                    continue
        return groups

    @staticmethod
    def _color_evaluation_lab_caption(lab):
        try:
            return f"LAB: {float(lab[0]):.2f}, {float(lab[1]):.2f}, {float(lab[2]):.2f}"
        except (TypeError, IndexError, ValueError):
            return ""

    @staticmethod
    def _format_color_evaluation_value(lab, display_mode, *, rgb=None,
                                       hex_color=None, card=False):
        """Format color coordinates consistently in the explorer and previews.

        In particular, keep the RGB of an actual sampled pixel rather than
        converting its stored, full-precision LAB values back into RGB.
        """
        try:
            mode = UtilsTools.normalize_color_value_space(display_mode)
            if mode == "RGB":
                values = (UtilsTools.safe_rgb_tuple(rgb) if rgb is not None else
                          UtilsTools.lab_to_color_value(lab, "RGB"))
                r, g, b = (int(component) for component in values)
                text = f"R={r}, G={g}, B={b}"
                return f"RGB: {text}" if card else text
            if mode == "CIELAB" and card:
                return PyFCSApp._color_evaluation_lab_caption(lab)
            if mode == "HEX" and hex_color and card:
                return f"HEX: {str(hex_color).upper()}"
            text = UtilsTools.format_lab_color_value(lab, mode)
            if not card:
                return text
            prefix = {"HEX": "HEX", "CIELUV": "LUV", "LCh": "LCh",
                      "CIE1931": "CIE1931"}.get(mode, mode)
            return f"{prefix}: {text}"
        except (TypeError, ValueError, IndexError, OverflowError):
            return ""

    def _highlight_color_evaluation_rows(self, vars_dict):
        """Refresh selection colors in-place without rebuilding entry widgets."""
        primary = vars_dict.get("primary_label")
        secondary = vars_dict.get("secondary_label") if vars_dict.get("secondary_mode") == "row" else None
        for info in vars_dict.get("category_rows", []):
            if info.get("single"):
                selected = info["labels"][0] in (primary, secondary)
                info["header"].configure(bg="#e8f0ff" if selected else "#f1f3f8")
                for child in info["header"].winfo_children():
                    if not isinstance(child, tk.Canvas):
                        try:
                            child.configure(bg="#e8f0ff" if selected else "#f1f3f8")
                            for subchild in child.winfo_children():
                                subchild.configure(bg="#e8f0ff" if selected else "#f1f3f8")
                        except (tk.TclError, ValueError):
                            pass
        for key, refs in vars_dict.get("color_row_refs", {}).items():
            bg = ("#e9e1ff" if key == primary == secondary else
                  "#e8f0ff" if key == primary else
                  "#f1e8ff" if key == secondary else "white")
            refs["frame"].configure(bg=bg, highlightbackground=(
                UtilsTools.UI_ACCENT if key in (primary, secondary) else "#e5e7eb"))
            refs["content"].configure(bg=bg)
            for widget in refs["widgets"]:
                if widget is refs.get("swatch"):
                    continue
                try:
                    widget.configure(bg=bg)
                except (tk.TclError, ValueError):
                    pass

    def _render_color_evaluation_cards(self, vars_dict, data_source):
        """Build the searchable atomic/granular color explorer.

        Category headings only expand/collapse. A selectable row always refers
        to a real prototype/granule and supports comparisons within a category.
        """
        rows_inner = vars_dict["rows_inner"]
        for child in rows_inner.winfo_children():
            child.destroy()
        vars_dict["color_row_refs"] = {}
        vars_dict["category_rows"] = []
        vars_dict["color_row_order"] = []
        vars_dict["category_open"] = {}
        vars_dict["primary_label"] = None
        vars_dict["primary_mode"] = "row"
        vars_dict["primary_custom_lab"] = None
        vars_dict["primary_custom_rgb"] = None
        vars_dict["primary_custom_hex"] = None
        vars_dict["secondary_label"] = None
        vars_dict["comparison_mode"] = False
        vars_dict["analysis_view_mode"] = "comparison"
        vars_dict["secondary_mode"] = None
        vars_dict["secondary_custom_lab"] = None
        vars_dict["secondary_custom_rgb"] = None
        vars_dict["secondary_custom_hex"] = None
        vars_dict["secondary_custom_name"] = "Custom Color"
        self._set_color_evaluation_active_action(vars_dict, None)
        vars_dict["analysis_mode_var"].set("Select a color from the list.")

        space = vars_dict.get("loaded_fuzzy_color_space")
        is_granular = isinstance(space, GranularFuzzyColorSpace)
        groups = self._color_evaluation_actual_entries(data_source, space)
        if not groups:
            tk.Label(rows_inner, text="No color space data available.", bg="white",
                     fg="#6b7280", font=("Segoe UI", 10)).pack(padx=12, pady=16)
            self._clear_color_evaluation_analysis(vars_dict)
            return

        def _select(label):
            if label not in vars_dict["color_row_refs"]:
                return
            if vars_dict.get("comparison_mode"):
                primary = vars_dict.get("primary_label")
                if primary is None and vars_dict.get("primary_mode") != "custom":
                    vars_dict["primary_label"] = label
                    vars_dict["secondary_label"] = None
                    vars_dict["secondary_mode"] = None
                    vars_dict["analysis_mode_var"].set("Choose a reference color to compare.")
                elif label == primary:
                    vars_dict["analysis_mode_var"].set(
                        "Choose a different color or granule for the reference.")
                    return
                else:
                    vars_dict["secondary_label"] = label
                    vars_dict["secondary_mode"] = "row"
                    vars_dict["secondary_custom_lab"] = None
                    vars_dict["secondary_custom_rgb"] = None
                    vars_dict["secondary_custom_hex"] = None
                    vars_dict["analysis_mode_var"].set(
                        "Comparison active. Select another reference or clear comparison.")
            else:
                vars_dict["primary_label"] = label
                vars_dict["primary_mode"] = "row"
                vars_dict["primary_custom_lab"] = None
                vars_dict["secondary_label"] = None
                if vars_dict.get("secondary_mode") == "custom" and vars_dict.get("secondary_custom_lab") is not None:
                    vars_dict["analysis_mode_var"].set(
                        "Custom comparison active. Select another color to compare.")
                else:
                    vars_dict["analysis_mode_var"].set("Single color selected.")
            refs = vars_dict["color_row_refs"][label]
            self._add_color_evaluation_quick_sample(
                vars_dict, name=label, lab=refs["lab"], rgb=refs["rgb"],
                hex_color=refs["hex"], source="granule" if refs.get("category") else "prototype",
                category=refs.get("category"), row_label=label)
            self._refresh_color_evaluation_comparison(vars_dict)
            self._highlight_color_evaluation_rows(vars_dict)

        def _make_entry(parent, label, lab, category=None):
            try:
                rgb = UtilsTools.lab_to_rgb(lab)
                rgb = tuple(max(0, min(255, int(round(v)))) for v in rgb)
            except Exception:
                rgb = (200, 200, 200)
            hex_color = self._safe_hex_from_rgb(rgb)
            row = tk.Frame(parent, bg="white", highlightthickness=1,
                           highlightbackground="#e5e7eb", cursor="hand2")
            row.pack(fill="x", padx=(13 if category else 8, 8), pady=3)
            content = tk.Frame(row, bg="white", cursor="hand2")
            content.pack(fill="x", padx=8, pady=6)
            swatch = tk.Canvas(content, width=70, height=58, bg="#f1f1f1",
                               highlightthickness=0, bd=0, cursor="hand2")
            swatch.pack(side="left", padx=(0, 10))
            swatch.create_rectangle(4, 4, 66, 54, fill=hex_color,
                                     outline="#686f78", width=1)
            details = tk.Frame(content, bg="white", cursor="hand2")
            details.pack(side="left", fill="both", expand=True)
            name = tk.Label(details, text=label, bg="white", fg="#243043",
                            anchor="w", font=("Segoe UI", 10, "bold"),
                            cursor="hand2")
            name.pack(anchor="w")
            if category:
                subtitle = tk.Label(details, text=f"Granule · {category}",
                                    bg="white", fg="#697386", anchor="w",
                                    font=("Segoe UI", 8), cursor="hand2")
                subtitle.pack(anchor="w", pady=(1, 0))
            else:
                subtitle = None
            value = tk.Label(details, text=self._format_color_evaluation_value(
                lab, vars_dict["color_display_mode_var"].get(), rgb=rgb),
                bg="white", fg="#526074", anchor="w", justify="left",
                wraplength=280, font=("Consolas", 8), cursor="hand2")
            value.pack(anchor="w", fill="x", pady=(3, 0))
            widgets = [content, name, value, details]
            if subtitle is not None:
                widgets.append(subtitle)
            vars_dict["color_row_refs"][label] = {
                "frame": row, "content": content, "widgets": widgets,
                "lab": lab, "rgb": rgb, "hex": hex_color,
                "swatch": swatch, "value_label": value, "category": category,
            }
            vars_dict["color_row_order"].append(label)
            for widget in (row, content, swatch, details, name, value):
                widget.bind("<Button-1>", lambda e, key=label: _select(key))
            if subtitle is not None:
                subtitle.bind("<Button-1>", lambda e, key=label: _select(key))
            return row

        for category, entries in groups:
            if not is_granular:
                _make_entry(rows_inner, entries[0][0], entries[0][1])
                continue
            group_frame = tk.Frame(rows_inner, bg="white")
            group_frame.pack(fill="x", pady=(2, 0))
            category_header = tk.Frame(group_frame, bg="#f1f3f8", cursor="hand2")
            category_header.pack(fill="x", padx=7, pady=(3, 2))
            multi_swatch = tk.Canvas(category_header, width=70, height=54,
                                     bg="#f1f3f8", highlightthickness=0,
                                     cursor="hand2")
            multi_swatch.pack(side="left", padx=(9, 9), pady=5)
            shown = entries[:3]
            swatch_width = 64 / max(1, len(shown))
            for idx, (_, candidate_lab) in enumerate(shown):
                try:
                    color = UtilsTools.lab_to_hex(candidate_lab)
                except Exception:
                    color = "#cccccc"
                x1 = 3 + idx * swatch_width
                x2 = 3 + (idx + 1) * swatch_width
                multi_swatch.create_rectangle(x1, 4, x2, 49,
                                               fill=color, outline="#808891", width=1)
            title_holder = tk.Frame(category_header, bg="#f1f3f8", cursor="hand2")
            title_holder.pack(side="left", fill="x", expand=True)
            title = tk.Label(title_holder, text=category, bg="#f1f3f8",
                             fg="#283449", font=("Segoe UI", 10, "bold"),
                             anchor="w", cursor="hand2")
            title.pack(anchor="w")
            subtitle = tk.Label(title_holder,
                                text=("1 granule · click to evaluate" if len(entries) == 1
                                      else f"{len(entries)} granules · choose a granule"),
                                bg="#f1f3f8", fg="#697386",
                                font=("Segoe UI", 8), anchor="w", cursor="hand2")
            subtitle.pack(anchor="w", pady=(2, 0))
            arrow = tk.Label(category_header, text="▸", bg="#f1f3f8",
                             fg=UtilsTools.UI_ACCENT, font=("Segoe UI", 13, "bold"),
                             cursor="hand2")
            arrow.pack(side="right", padx=12)
            children = tk.Frame(group_frame, bg="white")
            labels = []
            for label, lab in entries:
                _make_entry(children, label, lab, category)
                labels.append(label)
            info = {"label": category, "frame": group_frame, "children": children,
                    "header": category_header, "arrow": arrow, "labels": labels,
                    "single": len(entries) == 1, "open": False}
            vars_dict["category_rows"].append(info)
            vars_dict["category_open"][category] = False
            def _toggle(event=None, current=info):
                current["open"] = not current["open"]
                vars_dict["category_open"][current["label"]] = current["open"]
                self._filter_color_evaluation_entries(vars_dict)
            if len(entries) == 1:
                arrow.configure(text="")
            for widget in (category_header, multi_swatch, title_holder, title, subtitle, arrow):
                if len(entries) == 1:
                    widget.bind("<Button-1>", lambda e, key=labels[0]: _select(key))
                else:
                    widget.bind("<Button-1>", _toggle)

        if is_granular and vars_dict["category_rows"]:
            vars_dict["category_rows"][0]["open"] = True
            vars_dict["category_open"][vars_dict["category_rows"][0]["label"]] = True
        self._filter_color_evaluation_entries(vars_dict)
        first_label = vars_dict["color_row_order"][0]
        vars_dict["primary_label"] = first_label
        vars_dict["primary_mode"] = "row"
        vars_dict["analysis_mode_var"].set("Single color selected.")
        self._refresh_color_evaluation_comparison(vars_dict)
        self._highlight_color_evaluation_rows(vars_dict)
        # A StringVar trace is recreated with each window; remove an old one
        # when reloading the data so search remains one callback per edit.
        if not vars_dict.get("search_trace_registered"):
            vars_dict["color_search_var"].trace_add(
                "write", lambda *_: self._filter_color_evaluation_entries(vars_dict))
            vars_dict["search_trace_registered"] = True

    def _filter_color_evaluation_entries(self, vars_dict):
        """Filter prebuilt rows, retaining the color-space's original order."""
        query = vars_dict["color_search_var"].get().strip().casefold()
        category_rows = vars_dict.get("category_rows", [])
        if category_rows:
            # Repack only existing frames in model order, not in the order in
            # which a search query happened to reveal them.
            for info in category_rows:
                info["frame"].pack_forget()
            for info in category_rows:
                category_match = query in info["label"].casefold()
                child_matches = {label for label in info["labels"]
                                 if query in label.casefold()}
                show_group = not query or category_match or bool(child_matches)
                if show_group:
                    info["frame"].pack(fill="x", pady=(2, 0))
                for label in info["labels"]:
                    vars_dict["color_row_refs"][label]["frame"].pack_forget()
                for label in info["labels"]:
                    if not query or category_match or label in child_matches:
                        vars_dict["color_row_refs"][label]["frame"].pack(
                            fill="x", padx=(13, 8), pady=3)
                expanded = bool(info["open"] or (query and show_group))
                if expanded and show_group and not info.get("single"):
                    info["children"].pack(fill="x")
                else:
                    info["children"].pack_forget()
                if not info.get("single"):
                    info["arrow"].configure(text="▾" if expanded else "▸")
        else:
            for label in vars_dict.get("color_row_order", []):
                vars_dict["color_row_refs"][label]["frame"].pack_forget()
            for label in vars_dict.get("color_row_order", []):
                if query in label.casefold():
                    vars_dict["color_row_refs"][label]["frame"].pack(
                        fill="x", padx=(8, 8), pady=3)


    @staticmethod
    def _evaluation_sample_snapshot(name, lab, rgb, hex_color, source="custom",
                                    category=None, row_label=None):
        """Validated, independent copy of an actual LAB color (never a category mean)."""
        lab = tuple(float(value) for value in np.asarray(lab, dtype=float).reshape(3))
        if not np.isfinite(lab).all():
            raise ValueError("Sample LAB coordinates must be finite.")
        rgb = UtilsTools.safe_rgb_tuple(rgb)
        hex_color = str(hex_color).strip()
        if not hex_color.startswith("#") or len(hex_color) != 7:
            hex_color = UtilsTools.rgb_to_hex(rgb)
        return {
            "name": str(name).strip() or "Sample",
            "lab": lab, "rgb": tuple(rgb), "hex": hex_color,
            "source": str(source or "custom"),
            "category": category, "row_label": row_label,
        }

    def _add_color_evaluation_quick_sample(self, vars_dict, name, lab, rgb,
                                           hex_color, source="custom",
                                           category=None, row_label=None):
        """Remember recent colors, preserving original LAB precision and pins."""
        try:
            sample = self._evaluation_sample_snapshot(
                name, lab, rgb, hex_color, source, category, row_label)
        except (TypeError, ValueError, OverflowError):
            return None
        history = vars_dict.setdefault("quick_samples", [])
        signature = (sample["row_label"], sample["source"], sample["name"],
                     tuple(round(c, 8) for c in sample["lab"]))
        existing = next((item for item in history if item.get("signature") == signature), None)
        if existing is not None:
            history.remove(existing)
            history.insert(0, existing)
            item = existing
        else:
            vars_dict["quick_samples_sequence"] = vars_dict.get("quick_samples_sequence", 0) + 1
            item = dict(sample, id=vars_dict["quick_samples_sequence"],
                        pinned=False, signature=signature)
            history.insert(0, item)
        # Keep at most 12 unpinned samples; pinned ones are deliberately retained.
        recent = 0
        for saved in list(history):
            if not saved["pinned"]:
                recent += 1
                if recent > 12:
                    history.remove(saved)
        self._render_color_evaluation_quick_samples(vars_dict)
        return item

    def _render_color_evaluation_quick_samples(self, vars_dict):
        """Update the horizontal thumbnail strip without rebuilding the main UI."""
        outer = vars_dict.get("quick_samples_outer")
        inner = vars_dict.get("quick_samples_tiles")
        if outer is None or inner is None:
            return
        history = vars_dict.get("quick_samples", [])
        # Keep the Quick Samples header visible even before the first sample;
        # otherwise the new workflow looks identical to the previous version.
        if not outer.winfo_manager():
            outer.pack(fill="x", pady=(0, 5), after=vars_dict.get("quick_samples_after"))
        # Widgets are rebuilt only when the actual sample history changes.
        for child in inner.winfo_children():
            child.destroy()
        for item in ([row for row in history if row["pinned"]]
                     + [row for row in history if not row["pinned"]]):
            # Color-only thumbnails: names and precise values are retained in
            # the history and shown when selected, not repeated in the strip.
            tile = tk.Frame(inner, bg="white", highlightthickness=1,
                            highlightbackground="#d7dce5")
            tile.pack(side="left", padx=3, pady=2)
            swatch = tk.Canvas(tile, width=42, height=39, bd=0,
                               highlightthickness=0, bg="white", cursor="hand2")
            swatch.create_rectangle(3, 3, 39, 36, fill=item["hex"],
                                    outline="#7f8793", width=1)
            swatch.pack(side="left", padx=(3, 1), pady=3)
            swatch.bind("<Button-1>",
                        lambda _event, sid=item["id"]:
                        self._select_color_evaluation_quick_sample(vars_dict, sid))
            tk.Button(
                tile, text="★" if item["pinned"] else "☆",
                font=("Segoe UI", 9), relief="flat", bd=0, bg="white",
                fg=UtilsTools.UI_ACCENT if item["pinned"] else "#718096",
                activebackground=UtilsTools.UI_ACCENT_SOFT,
                cursor="hand2", padx=1, pady=0,
                command=lambda sid=item["id"]: self._pin_color_evaluation_sample(vars_dict, sid)
            ).pack(side="left", padx=(0, 2), anchor="n")
        vars_dict["quick_samples_title_btn"].configure(
            text=("▾" if vars_dict.get("quick_samples_expanded", True) else "▸")
            + f"  Quick Samples ({len(history)})")
        body = vars_dict["quick_samples_body"]
        canvas = vars_dict["quick_samples_canvas"]
        scroll = vars_dict["quick_samples_scroll"]
        empty_label = vars_dict["quick_samples_empty_label"]
        if not vars_dict.get("quick_samples_expanded", True):
            body.pack_forget()
            return
        body.pack(fill="x", padx=6, pady=(0, 1))
        if history:
            empty_label.pack_forget()
            canvas.pack(fill="x", expand=True)
            # The canvas resize callback shows horizontal scroll only if needed.
        else:
            canvas.pack_forget()
            scroll.pack_forget()
            empty_label.pack(fill="x", padx=4, pady=(2, 4))

    def _toggle_color_evaluation_quick_samples(self, vars_dict):
        vars_dict["quick_samples_expanded"] = not vars_dict.get("quick_samples_expanded", True)
        self._render_color_evaluation_quick_samples(vars_dict)

    def _pin_color_evaluation_sample(self, vars_dict, sample_id):
        for item in vars_dict.get("quick_samples", []):
            if item["id"] == sample_id:
                item["pinned"] = not item["pinned"]
                break
        self._render_color_evaluation_quick_samples(vars_dict)

    def _clear_color_evaluation_recent_samples(self, vars_dict):
        vars_dict["quick_samples"] = [item for item in vars_dict.get("quick_samples", [])
                                       if item["pinned"]]
        self._render_color_evaluation_quick_samples(vars_dict)

    def _get_color_evaluation_side_sample(self, vars_dict, side):
        """Return an independent sample for A or B, whether a row or an external color."""
        is_a = side == "A"
        mode = vars_dict.get("primary_mode", "row") if is_a else vars_dict.get("secondary_mode")
        prefix = "primary" if is_a else "secondary"
        if mode == "custom":
            lab = vars_dict.get(prefix + "_custom_lab")
            rgb = vars_dict.get(prefix + "_custom_rgb")
            hx = vars_dict.get(prefix + "_custom_hex")
            if lab is None or rgb is None or hx is None:
                return None
            return self._evaluation_sample_snapshot(
                vars_dict.get(prefix + "_custom_name", "Sample"), lab, rgb, hx,
                vars_dict.get(prefix + "_custom_source", "custom"))
        if mode == "row" or (is_a and mode is None):
            label = vars_dict.get(prefix + "_label")
            refs = vars_dict.get("color_row_refs", {}).get(label)
            if refs is not None:
                return self._evaluation_sample_snapshot(
                    label, refs["lab"], refs["rgb"], refs["hex"],
                    "granule" if refs.get("category") else "prototype",
                    refs.get("category"), label)
        return None

    def _set_color_evaluation_side_sample(self, vars_dict, side, sample):
        """Assign A/B without recomputing until both sides are ready."""
        prefix = "primary" if side == "A" else "secondary"
        label = sample.get("row_label") if sample else None
        refs = vars_dict.get("color_row_refs", {}).get(label)
        # After loading another space, old row snapshots become external samples.
        matching_row = bool(refs is not None and np.allclose(
            np.asarray(refs["lab"]), np.asarray(sample["lab"]), rtol=0, atol=1e-7)) if sample else False
        if matching_row:
            vars_dict[prefix + "_mode"] = "row"
            vars_dict[prefix + "_label"] = label
            vars_dict[prefix + "_custom_lab"] = None
            vars_dict[prefix + "_custom_rgb"] = None
            vars_dict[prefix + "_custom_hex"] = None
        elif sample is not None:
            vars_dict[prefix + "_mode"] = "custom"
            vars_dict[prefix + "_label"] = None
            vars_dict[prefix + "_custom_lab"] = sample["lab"]
            vars_dict[prefix + "_custom_rgb"] = sample["rgb"]
            vars_dict[prefix + "_custom_hex"] = sample["hex"]
            vars_dict[prefix + "_custom_name"] = sample["name"]
            vars_dict[prefix + "_custom_source"] = sample["source"]
        elif side == "B":
            vars_dict["secondary_mode"] = None
            vars_dict["secondary_label"] = None
        vars_dict["comparison_mode"] = False
        vars_dict["analysis_view_mode"] = "comparison"
        vars_dict["closest_ranking"] = []
        vars_dict["closest_best"] = None
        vars_dict["closest_metric"] = None

    def _select_color_evaluation_quick_sample(self, vars_dict, sample_id):
        """Immediately compare the selected saved color against the other side."""
        item = next((item for item in vars_dict.get("quick_samples", [])
                     if item["id"] == sample_id), None)
        if item is None:
            return
        history = vars_dict["quick_samples"]
        history.remove(item)
        history.insert(0, item)
        self._render_color_evaluation_quick_samples(vars_dict)
        side = vars_dict["quick_samples_target_var"].get()
        self._set_color_evaluation_side_sample(vars_dict, side, item)
        vars_dict["analysis_mode_var"].set(
            "Comparison active. Select another sample or reference." if
            self._get_color_evaluation_side_sample(vars_dict, "B") else "Sample selected.")
        self._refresh_color_evaluation_comparison(vars_dict)
        self._highlight_color_evaluation_rows(vars_dict)

    def _use_color_evaluation_external_sample(self, vars_dict, *, name, lab,
                                              rgb, hex_color, source="custom", target="B"):
        """Save and use one externally supplied color, leaving its picker open."""
        item = self._add_color_evaluation_quick_sample(
            vars_dict, name=name, lab=lab, rgb=rgb,
            hex_color=hex_color, source=source)
        if item is None:
            self.custom_warning("Invalid Sample", "The selected color is not valid.",
                                parent=getattr(self, "_color_evaluation_window", None))
            return False
        self._set_color_evaluation_side_sample(vars_dict, target, item)
        vars_dict["quick_samples_target_var"].set(target)
        vars_dict["analysis_mode_var"].set(
            f"{name} added to {self._get_color_evaluation_target_display_name(target)}. Choose another sample to continue comparing.")
        self._refresh_color_evaluation_comparison(vars_dict)
        self._highlight_color_evaluation_rows(vars_dict)
        return True

    def _get_color_evaluation_manager(self):
        """
        Return the shared ColorEvaluationManager instance.
        """
        manager = getattr(self, "color_evaluation_manager", None)

        if manager is None:
            manager = getattr(self, "color_eval_manager", None)

        if manager is None:
            manager = ColorEvaluationManager()
            self.color_evaluation_manager = manager

        return manager


    def _get_color_evaluation_target_display_name(self, side):
        """Return the UI display name for a comparison side."""
        return "Selected" if str(side).upper() == "A" else "Reference"


    def _clear_color_evaluation_analysis(self, vars_dict):
        """Reset the analysis panel."""
        vars_dict["primary_name_var"].set("None")
        vars_dict["secondary_name_var"].set("None")
        for key in ("primary_meta_var", "secondary_meta_var", "primary_lab_var", "secondary_lab_var"):
            vars_dict[key].set("")

        vars_dict["primary_swatch"].itemconfig(vars_dict["primary_rect"], fill="#cccccc")
        vars_dict["secondary_swatch"].itemconfig(vars_dict["secondary_rect"], fill="#f0f0f0")

        vars_dict["secondary_mode"] = None
        vars_dict["secondary_custom_lab"] = None
        vars_dict["secondary_custom_rgb"] = None
        vars_dict["secondary_custom_hex"] = None
        vars_dict["secondary_custom_name"] = "Custom Color"

        self._update_color_evaluation_result_card(
            vars_dict=vars_dict,
            title="Select a prototype to evaluate.",
            detail="",
            summary="",
            status="unavailable"
        )

        self._update_color_evaluation_conversion_inspector(vars_dict)
        self._update_color_evaluation_membership_panel(vars_dict, sample_lab=None)


    def _swap_color_evaluation_rows(self, vars_dict):
        """Exchange A and B, including custom/image colors and precise LAB values."""
        first = self._get_color_evaluation_side_sample(vars_dict, "A")
        second = self._get_color_evaluation_side_sample(vars_dict, "B")
        if first is None or second is None:
            return
        self._set_color_evaluation_side_sample(vars_dict, "A", second)
        self._set_color_evaluation_side_sample(vars_dict, "B", first)
        self._refresh_color_evaluation_comparison(vars_dict)
        self._highlight_color_evaluation_rows(vars_dict)

    def _enable_color_evaluation_comparison_mode(self, vars_dict):
        """Enable comparison mode so clicked colors become comparison colors."""
        primary = self._get_color_evaluation_side_sample(vars_dict, "A")

        if primary is None:
            vars_dict["comparison_mode"] = False
            vars_dict["analysis_mode_var"].set("Select a primary color first.")
            return

        vars_dict["comparison_mode"] = True
        vars_dict["analysis_mode_var"].set(
            "Comparison mode enabled. Click another color to compare against the selected one."
        )


    def _clear_color_evaluation_comparison(self, vars_dict, clear_custom=True):
        """Clear the comparison color and return to single-color analysis."""
        vars_dict["analysis_view_mode"] = "comparison"

        vars_dict["comparison_mode"] = False
        vars_dict["secondary_label"] = None
        vars_dict["secondary_mode"] = None

        if clear_custom:
            vars_dict["secondary_custom_lab"] = None
            vars_dict["secondary_custom_rgb"] = None
            vars_dict["secondary_custom_hex"] = None
            vars_dict["secondary_custom_name"] = "Custom Color"

        if self._get_color_evaluation_side_sample(vars_dict, "A") is not None:
            vars_dict["analysis_mode_var"].set("Single color selected.")
        else:
            vars_dict["analysis_mode_var"].set("Select a color from the list.")

        self._refresh_color_evaluation_comparison(vars_dict)

        for label, refs in vars_dict.get("color_row_refs", {}).items():
            bg = "#e8f0ff" if label == vars_dict.get("primary_label") else "white"

            refs["frame"].configure(bg=bg)
            refs["content"].configure(bg=bg)

            for widget in refs["widgets"]:
                if widget is refs.get("swatch"):
                    continue  # Use a neutral surround so the preview does not bias color comparison.
                try:
                    widget.configure(bg=bg)
                except Exception:
                    pass


    def _refresh_color_evaluation_comparison(self, vars_dict):
        """Update the analysis from two real LAB samples (rows or external colors)."""
        vars_dict["analysis_view_mode"] = "comparison"
        self._set_color_evaluation_inspector_layout(vars_dict)
        first = self._get_color_evaluation_side_sample(vars_dict, "A")
        second = self._get_color_evaluation_side_sample(vars_dict, "B")
        swap = vars_dict.get("swap_color_button")
        if swap is not None:
            swap.configure(state="normal" if first and second else "disabled")
        if first is None:
            self._clear_color_evaluation_analysis(vars_dict)
            return

        def update_side(side, sample):
            prefix = "primary" if side == "A" else "secondary"
            vars_dict[prefix + "_name_var"].set(sample["name"] if sample else "None")
            vars_dict[prefix + "_meta_var"].set(
                (f"Granule · {sample['category']}" if sample.get("category") else
                 "" if sample.get("row_label") else
                 "Image sample" if sample["source"].startswith("image") else
                 "Custom / saved sample") if sample else "")
            vars_dict[prefix + "_lab_var"].set(
                self._format_color_evaluation_value(
                    sample["lab"], vars_dict["color_display_mode_var"].get(),
                    rgb=sample["rgb"], hex_color=sample["hex"], card=True)
                if sample else "")
            vars_dict[prefix + "_swatch"].itemconfig(
                vars_dict[prefix + "_rect"], fill=sample["hex"] if sample else "#f0f0f0")

        update_side("A", first)
        update_side("B", second)
        active = second if second else first
        self._update_color_evaluation_conversion_inspector(
            vars_dict=vars_dict, lab=active["lab"], rgb=active["rgb"],
            hex_color=active["hex"], name=active["name"], source=active["source"])
        external = next((s for s in (second, first) if s is not None
                         and not s.get("row_label")), None)
        self._update_color_evaluation_membership_panel(
            vars_dict, sample_lab=external["lab"] if external else None)

        if second is None:
            self._update_color_evaluation_result_card(
                vars_dict, title="Single color selected. Comparison not active.",
                detail="", summary=("Select another color, add a custom/image sample, "
                                    "or reuse a color from Quick Samples."),
                status="unavailable")
            self._update_color_evaluation_graph_buttons(vars_dict)
            return

        metric_name = self.threshold_settings.get("metric", "CIEDE2000")
        evaluation = self.evaluate_color_difference_threshold(
            sample_lab=first["lab"], prototype_lab=second["lab"],
            metric=metric_name, threshold_settings=self.threshold_settings)
        metric_value = evaluation.get("metric_value", evaluation.get("delta_e"))
        self._update_color_evaluation_result_card(
            vars_dict, title=evaluation.get("evaluation", "Metric unavailable"),
            detail=(evaluation.get("detail", f"{metric_name} = {metric_value:.3f}")
                    if metric_value is not None else "Unable to compute selected metric"),
            summary=evaluation.get("summary_visual", evaluation.get("summary", "")),
            status=evaluation.get("status", "unavailable"))
        self._update_color_evaluation_graph_buttons(vars_dict)

    def _open_color_evaluation_image_sampler(self, vars_dict):
        """
        Open a compact image sampler for the Color Evaluation window.

        It allows:
        - selecting one loaded image;
        - clicking one pixel;
        - dragging a rectangle to sample the average RGB;
        - sending the sampled color as the custom comparison color.
        """
        # This dialog accepts loaded originals and temporary images alike.
        # It deliberately does not add the latter to the application's image list.
        parent = getattr(self, "_color_evaluation_window", self.root)

        popup = tk.Toplevel(parent)
        popup.withdraw()
        popup.title("Sample Color from Image")
        popup.configure(bg="#eeeeee")
        popup.resizable(True, True)
        popup.transient(parent)

        WIN_W, WIN_H = 660, 710
        popup.minsize(620, 620)

        try:
            self.center_popup_to_parent(popup, WIN_W, WIN_H, parent=parent)
        except Exception:
            self.center_popup(popup, WIN_W, WIN_H)

        state = {
            "window_id": None,
            "pil_img": None,
            "photo": None,
            "display_w": 560,
            "display_h": 340,
            "scale": 1.0,
            "offset_x": 0,
            "offset_y": 0,
            "view_zoom": 1.0,
            "view_cx": 0.0,
            "view_cy": 0.0,
            "display_img_w": 0,
            "display_img_h": 0,
            "drag_start": None,
            "rect_id": None,
            "sample_rgb": None,
            "sample_lab": None,
            "sample_hex": None,
            "sample_name": "Image Sample",
        }

        # Main shell
        outer = tk.Frame(popup, bg="#eeeeee")
        outer.pack(fill="both", expand=True, padx=12, pady=12)

        panel = tk.Frame(outer, bg="white", bd=1, relief="solid")
        panel.pack(fill="both", expand=True)

        header = tk.Frame(panel, bg="#f6f6f6", height=54)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(
            header,
            text="Sample Color from Image",
            font=("Sans", 13, "bold"),
            bg="#f6f6f6",
            fg="#222222",
            anchor="w",
            padx=16
        ).pack(side="left", fill="y")

        tk.Label(
            header,
            text="Click pixel or drag ROI",
            font=("Sans", 9, "italic"),
            bg="#f6f6f6",
            fg="#666666",
            padx=16
        ).pack(side="right", fill="y")

        body = tk.Frame(panel, bg="white")
        body.pack(fill="both", expand=True, padx=14, pady=10)

        # Image selector
        selector_card = tk.Frame(body, bg="#fafafa", bd=1, relief="solid")
        selector_card.pack(fill="x", pady=(0, 8))

        selector_row = tk.Frame(selector_card, bg="#fafafa")
        selector_row.pack(fill="x", padx=12, pady=8)

        tk.Label(
            selector_row,
            text="Image:",
            bg="#fafafa",
            font=("Sans", 10, "bold")
        ).pack(side="left", padx=(0, 8))

        image_ids = []
        image_names = []
        temp_sources = {}
        for wid, path in (getattr(self, "load_images_names", None) or {}).items():
            if not path:
                continue
            image_ids.append(wid)
            image_names.append(f"{os.path.basename(path)} [loaded]")

        selected_image_var = tk.StringVar(value=image_names[0] if image_names else "")
        image_combo = ttk.Combobox(
            selector_row, textvariable=selected_image_var,
            state="readonly", values=image_names, width=35)
        image_combo.pack(side="left", fill="x", expand=True)
        open_temp_button = tk.Button(
            selector_row, text="+ Open image...", relief="solid", bd=1,
            bg=UtilsTools.UI_ACCENT_SOFT, fg=UtilsTools.UI_ACCENT_DARK,
            cursor="hand2", font=("Segoe UI", 9, "bold"))
        open_temp_button.pack(side="left", padx=(8, 0))

        # Image preview
        image_card = tk.Frame(body, bg="#fafafa", bd=1, relief="solid")
        image_card.pack(fill="both", expand=True, pady=(0, 8))

        tk.Label(
            image_card,
            text="Image preview",
            bg="#fafafa",
            font=("Sans", 10, "bold"),
            anchor="w",
            padx=12,
            pady=7
        ).pack(fill="x")

        canvas = tk.Canvas(
            image_card,
            width=state["display_w"],
            height=state["display_h"],
            bg="white",
            highlightthickness=0,
            bd=0
        )
        canvas.pack(padx=12, pady=(0, 6))

        tip_var = tk.StringVar(
            value=("Mouse wheel: zoom · Click: pixel · Drag: ROI. "
                   "Open a temporary image if none is loaded.")
        )

        tk.Label(
            image_card,
            textvariable=tip_var,
            bg="#fafafa",
            fg="#666666",
            font=("Sans", 9, "italic"),
            wraplength=570,
            justify="left",
            padx=12,
            pady=0
        ).pack(fill="x", pady=(0, 8))

        # Sampled color panel
        sample_card = tk.Frame(body, bg="#fafafa", bd=1, relief="solid")
        sample_card.pack(fill="x", pady=(0, 0))

        tk.Label(
            sample_card,
            text="Sampled color",
            bg="#fafafa",
            font=("Sans", 10, "bold"),
            anchor="w",
            padx=12,
            pady=7
        ).pack(fill="x")

        sample_row = tk.Frame(sample_card, bg="#fafafa")
        sample_row.pack(fill="x", padx=12, pady=(0, 10))

        values_frame = tk.Frame(sample_row, bg="#fafafa")
        values_frame.pack(side="left", fill="x", expand=True)

        rgb_var = tk.StringVar(value="RGB: -")
        lab_var = tk.StringVar(value="LAB: -")
        hex_var = tk.StringVar(value="HEX: -")

        tk.Label(
            values_frame,
            textvariable=rgb_var,
            bg="#fafafa",
            anchor="w",
            font=("Consolas", 9)
        ).pack(anchor="w")

        tk.Label(
            values_frame,
            textvariable=lab_var,
            bg="#fafafa",
            anchor="w",
            font=("Consolas", 9)
        ).pack(anchor="w", pady=(2, 0))

        tk.Label(
            values_frame,
            textvariable=hex_var,
            bg="#fafafa",
            anchor="w",
            font=("Consolas", 9)
        ).pack(anchor="w", pady=(2, 0))

        preview_canvas = tk.Canvas(
            sample_row,
            width=130,
            height=42,
            bg="#fafafa",
            highlightthickness=0,
            bd=0
        )
        preview_canvas.pack(side="left", padx=(12, 12))

        preview_rect = preview_canvas.create_rectangle(
            8, 7, 122, 35,
            fill="#d9d9d9",
            outline="#555555"
        )

        use_button = ttk.Button(sample_row, text="Add to Reference", state="disabled")
        use_button.pack(side="right", padx=(5, 0))
        add_to_a_button = ttk.Button(sample_row, text="Add to Selected", state="disabled")
        add_to_a_button.pack(side="right")

        # Bottom buttons
        footer = tk.Frame(panel, bg="white")
        footer.pack(fill="x", padx=14, pady=(0, 12))

        tk.Button(
            footer,
            text="Done",
            width=12,
            command=popup.destroy
        ).pack(side="right")

        # Helpers
        def _get_selected_window_id():
            current_name = selected_image_var.get()

            if current_name in image_names:
                return image_ids[image_names.index(current_name)]

            return image_ids[0] if image_ids else None

        def _image_object_to_pil(img_obj):
            """
            Convert different internal image representations to PIL RGB.
            """
            if isinstance(img_obj, Image.Image):
                return img_obj.convert("RGB")

            if isinstance(img_obj, np.ndarray):
                arr = img_obj

                if arr.dtype != np.uint8:
                    arr = np.clip(arr, 0, 255).astype(np.uint8)

                if arr.ndim == 2:
                    return Image.fromarray(arr, "L").convert("RGB")

                if arr.ndim == 3 and arr.shape[2] >= 3:
                    return Image.fromarray(arr[:, :, :3], "RGB").convert("RGB")

            if isinstance(img_obj, str) and os.path.exists(img_obj):
                with Image.open(img_obj) as image_file:
                    return ImageOps.exif_transpose(image_file).convert("RGB")

            raise ValueError("Unsupported image format.")

        def _clamp(value, min_value, max_value):
            """Clamp a numeric value."""
            return max(min_value, min(max_value, value))


        def _is_point_inside_display(canvas_x, canvas_y):
            """Return True if a canvas coordinate is inside the displayed image area."""
            disp_w = state.get("display_img_w", 0)
            disp_h = state.get("display_img_h", 0)

            if disp_w <= 0 or disp_h <= 0:
                return False

            ox = state["offset_x"]
            oy = state["offset_y"]

            return (
                ox <= canvas_x < ox + disp_w
                and oy <= canvas_y < oy + disp_h
            )


        def _clamp_canvas_point_to_display(canvas_x, canvas_y):
            """Clamp a canvas coordinate to the displayed image area."""
            disp_w = max(1, state.get("display_img_w", 1))
            disp_h = max(1, state.get("display_img_h", 1))

            ox = state["offset_x"]
            oy = state["offset_y"]

            x = _clamp(canvas_x, ox, ox + disp_w - 1)
            y = _clamp(canvas_y, oy, oy + disp_h - 1)

            return x, y


        def _get_view_crop_box():
            """
            Return the current visible crop box in full-image coordinates.

            The canvas/display size stays fixed. Only this crop changes with zoom.
            """
            if state["pil_img"] is None:
                return None

            img_w, img_h = state["pil_img"].size

            zoom = max(1.0, float(state.get("view_zoom", 1.0)))
            cx = float(state.get("view_cx", img_w / 2))
            cy = float(state.get("view_cy", img_h / 2))

            crop_w = max(1.0, img_w / zoom)
            crop_h = max(1.0, img_h / zoom)

            left = cx - crop_w / 2
            top = cy - crop_h / 2

            left = _clamp(left, 0, max(0, img_w - crop_w))
            top = _clamp(top, 0, max(0, img_h - crop_h))

            right = left + crop_w
            bottom = top + crop_h

            return left, top, right, bottom


        def _render_preview():
            """
            Render the current zoom viewport into the fixed preview canvas.
            """
            if state["pil_img"] is None:
                return

            crop_box = _get_view_crop_box()
            if crop_box is None:
                return

            left, top, right, bottom = crop_box

            crop = state["pil_img"].crop((
                int(round(left)),
                int(round(top)),
                int(round(right)),
                int(round(bottom))
            ))

            disp_w = max(1, int(state["display_img_w"]))
            disp_h = max(1, int(state["display_img_h"]))

            resized = crop.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
            state["photo"] = ImageTk.PhotoImage(resized)

            canvas.delete("image")
            canvas.create_image(
                state["offset_x"],
                state["offset_y"],
                image=state["photo"],
                anchor="nw",
                tags=("image",)
            )

            try:
                canvas.tag_lower("image")
            except Exception:
                pass


        def _canvas_to_image_xy(canvas_x, canvas_y):
            """
            Convert canvas coordinates to full-image coordinates,
            taking the current zoom viewport into account.
            """
            if state["pil_img"] is None:
                return None

            disp_w = max(1, state.get("display_img_w", 1))
            disp_h = max(1, state.get("display_img_h", 1))

            canvas_x, canvas_y = _clamp_canvas_point_to_display(canvas_x, canvas_y)

            rel_x = canvas_x - state["offset_x"]
            rel_y = canvas_y - state["offset_y"]

            crop_box = _get_view_crop_box()
            if crop_box is None:
                return None

            left, top, right, bottom = crop_box

            crop_w = right - left
            crop_h = bottom - top

            x = left + (rel_x / disp_w) * crop_w
            y = top + (rel_y / disp_h) * crop_h

            img_w, img_h = state["pil_img"].size

            x = int(_clamp(x, 0, img_w - 1))
            y = int(_clamp(y, 0, img_h - 1))

            return x, y


        def _clear_preview_rectangle():
            """Remove the current ROI rectangle from the preview canvas."""
            if state["rect_id"] is not None:
                try:
                    canvas.delete(state["rect_id"])
                except Exception:
                    pass

            state["rect_id"] = None
            state["drag_start"] = None


        def _apply_preview_zoom(factor=None, reset=False, event=None):
            """
            Apply zoom to the preview without changing the canvas size.

            If the mouse is over the image, the zoom is centered around that point.
            """
            if state["pil_img"] is None:
                return "break"

            img_w, img_h = state["pil_img"].size

            _clear_preview_rectangle()

            if reset:
                state["view_zoom"] = 1.0
                state["view_cx"] = img_w / 2
                state["view_cy"] = img_h / 2
                _render_preview()
                tip_var.set(
                    "Mouse wheel to zoom. Click to sample one pixel, or drag to sample the average color of a region."
                )
                return "break"

            if factor is None:
                return "break"

            old_zoom = float(state.get("view_zoom", 1.0))
            new_zoom = _clamp(old_zoom * factor, 1.0, 16.0)

            if abs(new_zoom - old_zoom) < 1e-9:
                return "break"

            point_info = None
            if event is not None and _is_point_inside_display(event.x, event.y):
                source_xy = _canvas_to_image_xy(event.x, event.y)
                if source_xy is not None:
                    disp_w = max(1, state.get("display_img_w", 1))
                    disp_h = max(1, state.get("display_img_h", 1))

                    rel_x = event.x - state["offset_x"]
                    rel_y = event.y - state["offset_y"]

                    point_info = (
                        source_xy[0],
                        source_xy[1],
                        rel_x / disp_w,
                        rel_y / disp_h
                    )

            state["view_zoom"] = new_zoom

            if point_info is not None:
                source_x, source_y, rel_fx, rel_fy = point_info

                crop_w = max(1.0, img_w / new_zoom)
                crop_h = max(1.0, img_h / new_zoom)

                new_left = source_x - rel_fx * crop_w
                new_top = source_y - rel_fy * crop_h

                new_left = _clamp(new_left, 0, max(0, img_w - crop_w))
                new_top = _clamp(new_top, 0, max(0, img_h - crop_h))

                state["view_cx"] = new_left + crop_w / 2
                state["view_cy"] = new_top + crop_h / 2

            _render_preview()

            tip_var.set(
                f"Zoom: {new_zoom * 100:.0f}%. Click to sample one pixel, or drag to sample an average color."
            )

            return "break"


        def _on_preview_mousewheel(event):
            """Windows/macOS mouse wheel zoom."""
            if event.delta > 0:
                return _apply_preview_zoom(factor=1.15, event=event)
            else:
                return _apply_preview_zoom(factor=1 / 1.15, event=event)


        def _on_preview_linux_zoom_in(event):
            """Linux wheel up zoom."""
            return _apply_preview_zoom(factor=1.15, event=event)


        def _on_preview_linux_zoom_out(event):
            """Linux wheel down zoom."""
            return _apply_preview_zoom(factor=1 / 1.15, event=event)

        def _set_sample_rgb(rgb, source_text="image sample", lab_override=None):
            try:
                rgb = UtilsTools.safe_rgb_tuple(rgb)
                lab = UtilsTools.rgb_to_lab(rgb) if lab_override is None else lab_override
                lab = UtilsTools.safe_lab_tuple(lab)
                hex_color = UtilsTools.rgb_to_hex(rgb)

                state["sample_rgb"] = rgb
                state["sample_lab"] = lab
                state["sample_hex"] = hex_color

                rgb_var.set(f"RGB: {rgb[0]}, {rgb[1]}, {rgb[2]}")
                lab_var.set(f"LAB: {lab[0]:.4f}, {lab[1]:.4f}, {lab[2]:.4f}")
                hex_var.set(f"HEX: {hex_color.upper()}")

                preview_canvas.itemconfig(preview_rect, fill=hex_color)
                use_button.config(state="normal")
                add_to_a_button.config(state="normal")

                self._update_color_evaluation_conversion_inspector(
                    vars_dict=vars_dict,
                    lab=lab,
                    rgb=rgb,
                    hex_color=hex_color,
                    name="Image sample",
                    source=source_text
                )

            except Exception:
                state["sample_rgb"] = None
                state["sample_lab"] = None
                state["sample_hex"] = None

                rgb_var.set("RGB: -")
                lab_var.set("LAB: -")
                hex_var.set("HEX: -")

                preview_canvas.itemconfig(preview_rect, fill="#d9d9d9")
                use_button.config(state="disabled")
                add_to_a_button.config(state="disabled")

        def _clear_sample():
            state["sample_rgb"] = None
            state["sample_lab"] = None
            state["sample_hex"] = None

            rgb_var.set("RGB: -")
            lab_var.set("LAB: -")
            hex_var.set("HEX: -")

            preview_canvas.itemconfig(preview_rect, fill="#d9d9d9")
            use_button.config(state="disabled")
            add_to_a_button.config(state="disabled")


        def _get_best_sampler_source_pil(window_id):
            """
            Return the best available original PIL source for the sampler.

            Important:
            This Color Evaluation sampler should always sample from the real original image,
            not from Color Mapping or Color Mapping All visualizations.
            """
            if window_id in temp_sources:
                return temp_sources[window_id]

            if (
                hasattr(self, "pil_images_original")
                and window_id in self.pil_images_original
                and self.pil_images_original[window_id] is not None
            ):
                return _image_object_to_pil(self.pil_images_original[window_id])

            # Reload the original file if the in-memory source is unavailable.
            if (
                hasattr(self, "load_images_names")
                and window_id in self.load_images_names
                and self.load_images_names[window_id]
                and os.path.exists(self.load_images_names[window_id])
            ):
                with Image.open(self.load_images_names[window_id]) as image_file:
                    return ImageOps.exif_transpose(image_file).convert("RGB")

            # Retain compatibility with image windows lacking an original PIL reference.
            if (
                hasattr(self, "images")
                and window_id in self.images
                and self.images[window_id] is not None
            ):
                return _image_object_to_pil(self.images[window_id])

            raise ValueError("No valid original image source found.")

        def _open_temporary_image():
            base = UtilsTools.get_base_path()
            candidates = (
                os.path.join(base, "test_images"),
                os.path.join(base, "image_test"),
                os.path.join(base, "Source", "test_images"),
                os.path.join(base, "Source", "image_test"),
                base,
            )
            initial_dir = next((p for p in candidates if os.path.isdir(p)), os.getcwd())
            path = filedialog.askopenfilename(
                parent=popup, title="Open temporary image for color sampling",
                initialdir=initial_dir,
                filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp"),
                           ("All files", "*.*")])
            if not path:
                return
            try:
                with Image.open(path) as img:
                    pil_image = ImageOps.exif_transpose(img).convert("RGB")
            except Exception as exc:
                self.custom_warning("Image Error", f"Could not open this image:\n{exc}",
                                    parent=popup)
                return
            key = f"evaluation-temp-{len(temp_sources) + 1}"
            label_base = f"{os.path.basename(path)} [temporary]"
            label = label_base
            suffix = 2
            while label in image_names:
                label = f"{label_base} ({suffix})"
                suffix += 1
            temp_sources[key] = pil_image
            image_ids.append(key)
            image_names.append(label)
            image_combo.configure(values=image_names)
            selected_image_var.set(label)
            _load_selected_image()

        def _load_selected_image(*_):
            window_id = _get_selected_window_id()

            if window_id is None:
                tip_var.set("No image selected. Click '+ Open image...' to sample a temporary image.")
                return

            try:
                pil_img = _get_best_sampler_source_pil(window_id)
            except Exception:
                self.custom_warning(
                    "Image Error",
                    "Could not load the selected image.",
                    parent=popup
                )
                return

            state["window_id"] = window_id
            state["pil_img"] = pil_img

            img_w, img_h = pil_img.size
            canvas_w = state["display_w"]
            canvas_h = state["display_h"]

            scale = min(canvas_w / img_w, canvas_h / img_h)
            disp_w = max(1, int(round(img_w * scale)))
            disp_h = max(1, int(round(img_h * scale)))

            state["scale"] = scale
            state["offset_x"] = int((canvas_w - disp_w) / 2)
            state["offset_y"] = int((canvas_h - disp_h) / 2)
            state["display_img_w"] = disp_w
            state["display_img_h"] = disp_h

            # Reset viewport zoom for the newly selected image
            state["view_zoom"] = 1.0
            state["view_cx"] = img_w / 2
            state["view_cy"] = img_h / 2

            canvas.delete("all")
            state["rect_id"] = None
            state["drag_start"] = None

            _render_preview()
            _clear_sample()

            tip_var.set(
                "Mouse wheel to zoom. Click to sample one pixel, or drag to sample the average color of a region."
            )

        def _sample_roi_from_canvas(x1, y1, x2, y2):
            if state["pil_img"] is None:
                return

            p1 = _canvas_to_image_xy(x1, y1)
            p2 = _canvas_to_image_xy(x2, y2)

            if p1 is None or p2 is None:
                return

            ix1, iy1 = p1
            ix2, iy2 = p2

            left = min(ix1, ix2)
            right = max(ix1, ix2)
            top = min(iy1, iy2)
            bottom = max(iy1, iy2)

            source_name = selected_image_var.get().split(" [", 1)[0]
            if abs(right - left) <= 1 and abs(bottom - top) <= 1:
                state["sample_name"] = f"{source_name} ({left}, {top})"
                rgb = state["pil_img"].getpixel((left, top))
                _set_sample_rgb(rgb, source_text="image pixel")
                return

            state["sample_name"] = f"{source_name} ROI ({left},{top})–({right},{bottom})"
            crop = state["pil_img"].crop((left, top, right + 1, bottom + 1))
            mean_lab, count = UtilsTools.mean_lab_with_filters(
                np.asarray(crop.convert("RGB"), dtype=np.uint8)
            )
            if not count:
                return
            rgb = tuple(UtilsTools.lab_to_rgb(mean_lab))
            _set_sample_rgb(rgb, source_text="image ROI LAB average",
                            lab_override=mean_lab)

        def _on_mouse_down(event):
            if state["pil_img"] is None:
                return

            if not _is_point_inside_display(event.x, event.y):
                return

            x, y = _clamp_canvas_point_to_display(event.x, event.y)

            state["drag_start"] = (x, y)

            if state["rect_id"] is not None:
                try:
                    canvas.delete(state["rect_id"])
                except Exception:
                    pass

            state["rect_id"] = canvas.create_rectangle(
                x,
                y,
                x,
                y,
                outline="#ffcc00",
                width=2
            )


        def _on_mouse_drag(event):
            if state["drag_start"] is None or state["rect_id"] is None:
                return

            x0, y0 = state["drag_start"]
            x1, y1 = _clamp_canvas_point_to_display(event.x, event.y)

            canvas.coords(
                state["rect_id"],
                x0,
                y0,
                x1,
                y1
            )


        def _on_mouse_up(event):
            if state["drag_start"] is None:
                return

            x0, y0 = state["drag_start"]
            x1, y1 = _clamp_canvas_point_to_display(event.x, event.y)

            state["drag_start"] = None

            _sample_roi_from_canvas(x0, y0, x1, y1)

        def _use_sampled_color(target="B"):
            if any(state[key] is None for key in ("sample_rgb", "sample_lab", "sample_hex")):
                return
            name = state.get("sample_name", "Image Sample")
            if self._use_color_evaluation_external_sample(
                    vars_dict, name=name, lab=state["sample_lab"],
                    rgb=state["sample_rgb"], hex_color=state["sample_hex"],
                    source="image", target=target):
                tip_var.set(f"Sample added to {self._get_color_evaluation_target_display_name(target)}. Continue sampling, or select Done.")

        use_button.configure(command=lambda: _use_sampled_color("B"))
        add_to_a_button.configure(command=lambda: _use_sampled_color("A"))
        open_temp_button.configure(command=_open_temporary_image)

        image_combo.bind("<<ComboboxSelected>>", _load_selected_image)

        canvas.bind("<ButtonPress-1>", _on_mouse_down)
        canvas.bind("<B1-Motion>", _on_mouse_drag)
        canvas.bind("<ButtonRelease-1>", _on_mouse_up)

        # Preview zoom with mouse wheel
        canvas.bind("<MouseWheel>", _on_preview_mousewheel, add="+")
        canvas.bind("<Button-4>", _on_preview_linux_zoom_in, add="+")
        canvas.bind("<Button-5>", _on_preview_linux_zoom_out, add="+")

        canvas.bind("<Double-Button-3>", lambda event: _apply_preview_zoom(reset=True))

        popup.bind("<Escape>", lambda e: popup.destroy())

        _load_selected_image()
        popup.deiconify()
        popup.grab_set()


    def _get_custom_color_input_mode_help(self, mode):
        """
        Compatibility wrapper. Logic lives in ColorEvaluationManager.
        """
        manager = self._get_color_evaluation_manager()
        return manager.get_custom_color_input_mode_help(mode)


    def _open_custom_color_input_dialog(self, vars_dict):
        """Use PyFCS's shared visual Color Picker directly for a quick A/B sample."""
        if not vars_dict.get("loaded_space_data"):
            self.custom_warning(
                "No Color Space Loaded", "Load a color space before evaluating colors.",
                parent=getattr(self, "_color_evaluation_window", None))
            return
        parent = getattr(self, "_color_evaluation_window", None) or self.root
        target = vars_dict["quick_samples_target_var"].get()
        active = self._get_color_evaluation_side_sample(vars_dict, target)
        initial_rgb = active["rgb"] if active else (217, 217, 217)

        def _add_selected_color(rgb, hex_value):
            rgb = UtilsTools.safe_rgb_tuple(rgb)
            lab = UtilsTools.safe_lab_tuple(UtilsTools.rgb_to_lab(rgb))
            accepted = self._use_color_evaluation_external_sample(
                vars_dict, name="Custom Color", lab=lab, rgb=rgb,
                hex_color=hex_value, source="custom", target=target)
            if not accepted:
                raise ValueError("The selected color could not be added.")

        return self._open_square_color_picker(
            parent=parent, initial_rgb=initial_rgb, on_apply=_add_selected_color,
            submit_text=f"Add to {self._get_color_evaluation_target_display_name(target)}", title="Evaluate Custom Color")


    def _open_custom_color_dialog(
        self,
        parent=None,
        title="Custom Color",
        subtitle="",
        submit_text="OK",
        require_name=False,
        default_name="Custom Color",
        on_submit=None,
        initial_lab=None,
        allow_evaluation_target=False,
        initial_evaluation_target="B",
    ):
        """
        Open a reusable styled dialog to input a custom color in RGB, LAB, or HEX.

        Parameters
        ----------
        parent : tk widget
            Parent window.
        title : str
            Dialog title.
        subtitle : str
            Kept for compatibility with existing callers; the mode selector
            communicates the available color representations.
        submit_text : str
            Text for the submit button.
        require_name : bool
            Whether to request a color name.
        default_name : str
            Initial color name when require_name=True.
        initial_lab : sequence of 3 floats, optional
            Prefill an existing granule with its unrounded LAB coordinates.
        on_submit : callable
            Callback called as:
                on_submit(name, sample_lab, sample_rgb, sample_hex, dialog, input_vars)
        """
        MAX_NAME_CHARS = UtilsTools.MAX_COLOR_NAME_CHARS

        parent = self._get_valid_dialog_parent(
            parent or getattr(self, "_color_evaluation_window", self.root)
        )

        dialog = tk.Toplevel(parent)
        dialog.withdraw()
        dialog.title(title)
        dialog.resizable(False, False)
        dialog.configure(bg="#f5f6f8")
        dialog.transient(parent)

        WIN_W = 760
        WIN_H = 420 if require_name else (435 if allow_evaluation_target else 390)

        try:
            if parent is not None and hasattr(parent, "winfo_x"):
                self.center_popup_to_parent(dialog, WIN_W, WIN_H, parent=parent)
            else:
                self.center_popup(dialog, WIN_W, WIN_H)
        except Exception:
            self.center_popup(dialog, WIN_W, WIN_H)

        input_vars = {
            "mode_var": tk.StringVar(value="RGB"),
            "name_var": tk.StringVar(value=str(default_name)[:MAX_NAME_CHARS]),
            "v1_var": tk.StringVar(value=""),
            "v2_var": tk.StringVar(value=""),
            "v3_var": tk.StringVar(value=""),
            "hex_var": tk.StringVar(value=""),
            "status_var": tk.StringVar(value="Enter a color value."),
            "limits_var": tk.StringVar(value=""),
            "example_var": tk.StringVar(value=""),
            "preview_hex_var": tk.StringVar(value="#D9D9D9"),
            "preview_rgb_var": tk.StringVar(value="—"),
            "preview_lab_var": tk.StringVar(value="—"),
            "evaluation_target_var": tk.StringVar(
                value=initial_evaluation_target if initial_evaluation_target in ("A", "B") else "B"),
        }

        state = {"suspend_validation": False, "previous_mode": "RGB"}

        style = ttk.Style(dialog)
        try:
            style.configure("CustomColor.TCombobox", padding=4)
            style.configure("CustomColor.Secondary.TButton", font=("Helvetica", 10), padding=(14, 8))
        except Exception:
            pass

        outer = tk.Frame(dialog, bg="#f5f6f8")
        outer.pack(fill="both", expand=True, padx=14, pady=14)

        panel = tk.Frame(outer, bg="white", highlightbackground="#d9dde3", highlightthickness=1)
        panel.pack(fill="both", expand=True)

        header = tk.Frame(panel, bg="#f6f7f9", height=58)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(
            header, text=title, font=("Sans", 13, "bold"), bg="#f6f7f9",
            fg="#222222", anchor="w", padx=16
        ).pack(side="left", fill="y")

        # The selected input mode already explains which formats are available.
        # Keep `subtitle` in the signature for compatibility with callers,
        # but do not repeat hard-coded mode names in the window header.

        body = tk.Frame(panel, bg="white")
        body.pack(fill="both", expand=True, padx=18, pady=14)
        body.grid_columnconfigure(0, weight=1, minsize=290)
        body.grid_columnconfigure(1, weight=0, minsize=14)
        body.grid_columnconfigure(2, weight=1, minsize=320)

        # Left side: preview and derived values
        left_panel = tk.Frame(body, bg="white")
        left_panel.grid(row=0, column=0, sticky="nsew")

        preview_card = tk.Frame(left_panel, bg="#fafafa", bd=1, relief="solid", width=285, height=255)
        preview_card.pack(fill="both", expand=True)
        preview_card.pack_propagate(False)

        tk.Label(
            preview_card, text="Color preview", bg="#fafafa", fg="#222222",
            font=("Sans", 10, "bold"), anchor="center", pady=8
        ).pack(fill="x")

        preview_canvas = tk.Canvas(
            preview_card, width=240, height=75, bg="#fafafa",
            highlightthickness=0, bd=0
        )
        preview_canvas.pack(fill="x", padx=12, pady=(0, 7))
        preview_rect = preview_canvas.create_rectangle(
            5, 6, 235, 69, fill="#d9d9d9", outline="#8c93a0", width=1
        )

        def _resize_preview(event):
            preview_canvas.coords(preview_rect, 5, 6, max(6, event.width - 5), max(7, event.height - 6))

        preview_canvas.bind("<Configure>", _resize_preview)

        # One centered two-column group: captions beside values, not stacked.
        values_block = tk.Frame(preview_card, bg="#fafafa")
        values_block.pack(anchor="center", pady=(2, 6))
        for row_index, (caption, variable) in enumerate((
            ("HEX", input_vars["preview_hex_var"]),
            ("RGB", input_vars["preview_rgb_var"]),
            ("CIELAB", input_vars["preview_lab_var"]),
        )):
            tk.Label(
                values_block, text=caption, bg="#fafafa", fg="#667085",
                font=("Segoe UI", 9, "bold"), anchor="e", width=7
            ).grid(row=row_index, column=0, sticky="e", padx=(0, 12), pady=4)
            tk.Label(
                values_block, textvariable=variable, bg="#fafafa", fg="#1f2937",
                font=("Consolas", 9), anchor="w", width=22
            ).grid(row=row_index, column=1, sticky="w", pady=4)

        # Separator
        separator = tk.Frame(body, bg="#dddddd", width=1)
        separator.grid(row=0, column=1, sticky="ns", padx=10)

        # Right side: editable fields
        right_panel = tk.Frame(body, bg="white")
        right_panel.grid(row=0, column=2, sticky="nsew")
        right_panel.grid_columnconfigure(1, weight=1)

        current_row = 0
        if require_name:
            tk.Label(right_panel, text="Granule name", bg="white", anchor="w", font=("Sans", 10, "bold")
                     ).grid(row=current_row, column=0, sticky="w", pady=(2, 10), padx=(0, 10))

            def _validate_name_length(proposed_text):
                return len(proposed_text) <= MAX_NAME_CHARS

            name_vcmd = (dialog.register(_validate_name_length), "%P")
            name_entry = tk.Entry(
                right_panel, textvariable=input_vars["name_var"], font=("Sans", 10),
                validate="key", validatecommand=name_vcmd, relief="solid", bd=1
            )
            name_entry.grid(row=current_row, column=1, sticky="ew", pady=(2, 10))
            current_row += 1

        tk.Label(right_panel, text="Input mode", bg="white", anchor="w", font=("Sans", 10, "bold")
                 ).grid(row=current_row, column=0, sticky="w", pady=(2, 10), padx=(0, 10))

        mode_holder = tk.Frame(right_panel, bg="white")
        mode_holder.grid(row=current_row, column=1, sticky="ew", pady=(2, 10))
        mode_holder.grid_columnconfigure(1, weight=1)
        mode_combo = ttk.Combobox(
            mode_holder, textvariable=input_vars["mode_var"], state="readonly", width=10,
            values=["RGB", "LAB", "HEX"], style="CustomColor.TCombobox"
        )
        mode_combo.grid(row=0, column=0, sticky="w")
        pick_color_btn = tk.Button(
            mode_holder, text="Pick color...", font=("Segoe UI", 9, "bold"),
            bg=UtilsTools.UI_ACCENT_SOFT, fg=UtilsTools.UI_ACCENT,
            activebackground=UtilsTools.UI_ACCENT_HOVER,
            activeforeground=UtilsTools.UI_ACCENT_DARK,
            relief="flat", bd=0, highlightthickness=0,
            padx=12, pady=5, cursor="hand2",
        )
        pick_color_btn.grid(row=0, column=1, sticky="e")
        current_row += 1

        lbl1 = tk.Label(right_panel, text="R:", bg="white", anchor="w", font=("Sans", 10))
        entry1 = tk.Entry(right_panel, textvariable=input_vars["v1_var"], font=("Sans", 10), relief="solid", bd=1)
        lbl2 = tk.Label(right_panel, text="G:", bg="white", anchor="w", font=("Sans", 10))
        entry2 = tk.Entry(right_panel, textvariable=input_vars["v2_var"], font=("Sans", 10), relief="solid", bd=1)
        lbl3 = tk.Label(right_panel, text="B:", bg="white", anchor="w", font=("Sans", 10))
        entry3 = tk.Entry(right_panel, textvariable=input_vars["v3_var"], font=("Sans", 10), relief="solid", bd=1)
        hex_label = tk.Label(right_panel, text="HEX:", bg="white", anchor="w", font=("Sans", 10))
        hex_entry = tk.Entry(right_panel, textvariable=input_vars["hex_var"], font=("Sans", 10), relief="solid", bd=1)
        input_start_row = current_row

        hint_label = tk.Label(right_panel, textvariable=input_vars["limits_var"], bg="white", fg="#667085",
                              justify="center", anchor="center", wraplength=285, font=("Sans", 9))
        example_label = tk.Label(right_panel, textvariable=input_vars["example_var"], bg="white", fg="#8c8c8c",
                                 justify="center", anchor="center", wraplength=285, font=("Sans", 9, "italic"))

        if allow_evaluation_target:
            target_row = tk.Frame(panel, bg="white")
            target_row.pack(fill="x", padx=16, pady=(0, 5))
            tk.Label(target_row, text="Add color to:", bg="white", fg="#526074",
                     font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 8))
            for target in ("A", "B"):
                tk.Radiobutton(target_row, text=f"Sample {target}", value=target,
                               variable=input_vars["evaluation_target_var"],
                               bg="white", activebackground="white",
                               font=("Segoe UI", 9)).pack(side="left", padx=(0, 14))

        footer = tk.Frame(panel, bg="white")
        footer.pack(fill="x", padx=16, pady=(0, 14))

        status_label = tk.Label(
            footer, textvariable=input_vars["status_var"], bg="white", fg="#8a4f00",
            anchor="w", justify="left", wraplength=390, font=("Sans", 9, "italic")
        )
        status_label.pack(side="left", fill="x", expand=True)

        buttons_frame = tk.Frame(footer, bg="white")
        buttons_frame.pack(side="right")
        btn_cancel = tk.Button(
            buttons_frame, text="Cancel", command=dialog.destroy,
            font=("Segoe UI", 10), bg="#E8E9EC", fg="#263044",
            activebackground="#DDE0E5", relief="flat", bd=0,
            padx=16, pady=8, cursor="hand2",
        )
        btn_cancel.pack(side="left", padx=(0, 8))
        btn_submit = tk.Button(
            buttons_frame, text=submit_text, state="disabled",
            font=("Segoe UI", 10, "bold"),
            bg=UtilsTools.UI_ACCENT_SOFT, fg="white",
            activebackground=UtilsTools.UI_ACCENT_DARK,
            activeforeground="white", disabledforeground="#9b90a5",
            relief="flat", bd=0, highlightthickness=0,
            padx=16, pady=8, cursor="hand2",
        )
        btn_submit.pack(side="left")

        def _set_submit_enabled(enabled):
            btn_submit.configure(
                state="normal" if enabled else "disabled",
                bg=UtilsTools.UI_ACCENT if enabled else UtilsTools.UI_ACCENT_SOFT,
            )

        def _clear_numeric_fields():
            input_vars["v1_var"].set("")
            input_vars["v2_var"].set("")
            input_vars["v3_var"].set("")

        def _clear_hex_field():
            input_vars["hex_var"].set("")

        def _set_status(message, ok=False):
            input_vars["status_var"].set(message)
            status_label.configure(fg="#2d6a2d" if ok else "#8a4f00")

        def _reset_preview():
            preview_canvas.itemconfig(preview_rect, fill="#d9d9d9")
            input_vars["preview_hex_var"].set("#D9D9D9")
            input_vars["preview_rgb_var"].set("—")
            input_vars["preview_lab_var"].set("—")

        def _validate_name():
            if not require_name:
                return True, ""
            name = input_vars["name_var"].get().strip()
            if not name:
                return False, "Enter a color name."
            if len(name) > MAX_NAME_CHARS:
                return False, f"Color name must contain at most {MAX_NAME_CHARS} characters."
            return True, ""

        def _validate_live(*_):
            if state["suspend_validation"]:
                return
            name_ok, name_message = _validate_name()
            if not name_ok:
                _reset_preview()
                _set_status(name_message, ok=False)
                _set_submit_enabled(False)
                return
            mode = input_vars["mode_var"].get().strip().upper()
            ok, message, sample_lab, sample_rgb, _ = self._normalize_custom_color_input(
                input_mode=mode,
                value_1=input_vars["v1_var"].get(),
                value_2=input_vars["v2_var"].get(),
                value_3=input_vars["v3_var"].get(),
                hex_value=input_vars["hex_var"].get()
            )
            if ok and sample_rgb is not None:
                preview_hex = self._safe_hex_from_rgb(sample_rgb)
                preview_canvas.itemconfig(preview_rect, fill=preview_hex)
                input_vars["preview_hex_var"].set(preview_hex.upper())
                input_vars["preview_rgb_var"].set(", ".join(str(int(round(float(v)))) for v in sample_rgb[:3]))
                input_vars["preview_lab_var"].set(", ".join(f"{float(v):.2f}" for v in sample_lab[:3]))
                _set_status(message or "Valid color input.", ok=True)
                _set_submit_enabled(True)
            else:
                _reset_preview()
                _set_status(message or "Enter a valid color value.", ok=False)
                _set_submit_enabled(False)

        def _refresh_inputs(*_):
            mode = input_vars["mode_var"].get().strip().upper()
            previous = state.get("previous_mode", "RGB")
            previous_lab = previous_rgb = None
            if previous != mode:
                ok, _, previous_lab, previous_rgb, _ = self._normalize_custom_color_input(
                    input_mode=previous,
                    value_1=input_vars["v1_var"].get(),
                    value_2=input_vars["v2_var"].get(),
                    value_3=input_vars["v3_var"].get(),
                    hex_value=input_vars["hex_var"].get(),
                )
                if not ok:
                    previous_lab = previous_rgb = None
            state["suspend_validation"] = True
            try:
                state["previous_mode"] = mode
                help_data = self._get_custom_color_input_mode_help(mode)
                input_vars["limits_var"].set(help_data["limits"])
                input_vars["example_var"].set(help_data["example"])
                for widget in (lbl1, entry1, lbl2, entry2, lbl3, entry3, hex_label, hex_entry, hint_label, example_label):
                    try:
                        widget.grid_remove()
                    except Exception:
                        pass
                _clear_numeric_fields()
                _clear_hex_field()
                _reset_preview()
                _set_status("Enter a color value.", ok=False)
                _set_submit_enabled(False)
                if mode in ("RGB", "LAB"):
                    lbl1.config(text=f"{help_data['labels'][0]}:")
                    lbl2.config(text=f"{help_data['labels'][1]}:")
                    lbl3.config(text=f"{help_data['labels'][2]}:")
                    lbl1.grid(row=input_start_row, column=0, sticky="w", pady=5, padx=(0, 10))
                    entry1.grid(row=input_start_row, column=1, sticky="ew", pady=5)
                    lbl2.grid(row=input_start_row + 1, column=0, sticky="w", pady=5, padx=(0, 10))
                    entry2.grid(row=input_start_row + 1, column=1, sticky="ew", pady=5)
                    lbl3.grid(row=input_start_row + 2, column=0, sticky="w", pady=5, padx=(0, 10))
                    entry3.grid(row=input_start_row + 2, column=1, sticky="ew", pady=5)
                    dialog.after_idle(entry1.focus_set)
                    next_row = input_start_row + 3
                else:
                    hex_label.grid(row=input_start_row, column=0, sticky="w", pady=5, padx=(0, 10))
                    hex_entry.grid(row=input_start_row, column=1, sticky="ew", pady=5)
                    dialog.after_idle(hex_entry.focus_set)
                    next_row = input_start_row + 1
                hint_label.grid(row=next_row, column=0, columnspan=2, sticky="ew", pady=(12, 2))
                example_label.grid(row=next_row + 1, column=0, columnspan=2, sticky="ew", pady=(0, 2))
                if previous_lab is not None and previous_rgb is not None:
                    if mode == "LAB":
                        for variable, value in zip((input_vars["v1_var"], input_vars["v2_var"], input_vars["v3_var"]), previous_lab):
                            variable.set(f"{float(value):.15g}")
                    elif mode == "RGB":
                        for variable, value in zip((input_vars["v1_var"], input_vars["v2_var"], input_vars["v3_var"]), previous_rgb):
                            variable.set(str(int(round(float(value)))))
                    else:
                        input_vars["hex_var"].set(self._safe_hex_from_rgb(previous_rgb).upper())
            finally:
                state["suspend_validation"] = False
                _validate_live()

        def _submit():
            name_ok, name_message = _validate_name()
            if not name_ok:
                _set_status(name_message, ok=False)
                self.custom_warning("Invalid Color Name", name_message, parent=dialog)
                return
            ok, message, sample_lab, sample_rgb, sample_hex = self._normalize_custom_color_input(
                input_mode=input_vars["mode_var"].get(),
                value_1=input_vars["v1_var"].get(),
                value_2=input_vars["v2_var"].get(),
                value_3=input_vars["v3_var"].get(),
                hex_value=input_vars["hex_var"].get()
            )
            if not ok:
                _set_status(message, ok=False)
                self.custom_warning("Invalid Custom Color", message, parent=dialog)
                return
            color_name = input_vars["name_var"].get().strip() if require_name else default_name
            if callable(on_submit):
                on_submit(color_name, sample_lab, sample_rgb, sample_hex, dialog, input_vars)
            else:
                dialog.destroy()

        def _get_current_rgb_for_picker():
            mode = input_vars["mode_var"].get().strip().upper()
            ok, _, _, sample_rgb, _ = self._normalize_custom_color_input(
                input_mode=mode,
                value_1=input_vars["v1_var"].get(),
                value_2=input_vars["v2_var"].get(),
                value_3=input_vars["v3_var"].get(),
                hex_value=input_vars["hex_var"].get()
            )
            if ok and sample_rgb is not None:
                return sample_rgb
            return (217, 217, 217)

        def _open_picker():
            self._open_square_color_picker(parent=dialog, initial_rgb=_get_current_rgb_for_picker(), on_apply=_apply_picker_result)

        def _apply_picker_result(rgb, hex_value=None):
            state["suspend_validation"] = True
            try:
                self._fill_custom_color_dialog_from_rgb(input_vars, rgb)
            finally:
                state["suspend_validation"] = False
                dialog.after_idle(_validate_live)

        pick_color_btn.configure(command=_open_picker)
        btn_submit.configure(command=_submit)
        mode_combo.bind("<<ComboboxSelected>>", _refresh_inputs)
        for var_name in ("v1_var", "v2_var", "v3_var", "hex_var", "name_var"):
            input_vars[var_name].trace_add("write", _validate_live)
        dialog.bind("<Return>", lambda e: btn_submit.invoke() if str(btn_submit["state"]) == "normal" else None)
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        _refresh_inputs()
        if initial_lab is not None:
            try:
                values = np.asarray(initial_lab, dtype=float).reshape(3)
                input_vars["mode_var"].set("LAB")
                _refresh_inputs()
                for variable, value in zip((input_vars["v1_var"], input_vars["v2_var"], input_vars["v3_var"]), values):
                    variable.set(f"{float(value):.15g}")
                _validate_live()
            except (ValueError, TypeError):
                pass
        dialog.deiconify()
        dialog.grab_set()
        return dialog


    def _submit_custom_color_input(self, vars_dict, input_vars, dialog):
        """Validate the custom color input and use it as comparison color."""
        ok, message, sample_lab, sample_rgb, sample_hex = self._normalize_custom_color_input(
            input_mode=input_vars["mode_var"].get(),
            value_1=input_vars["v1_var"].get(),
            value_2=input_vars["v2_var"].get(),
            value_3=input_vars["v3_var"].get(),
            hex_value=input_vars["hex_var"].get()
        )

        if not ok:
            input_vars["status_var"].set(message)

            self.custom_warning(
                "Invalid Custom Color",
                message,
                parent=dialog
            )
            return

        dialog.destroy()

        self._set_custom_color_as_evaluation_comparison(
            vars_dict=vars_dict,
            sample_lab=sample_lab,
            sample_rgb=sample_rgb,
            sample_hex=sample_hex
        )


    def _fill_custom_color_dialog_from_rgb(self, input_vars, rgb):
        """
        Fill the reusable custom color dialog from a selected RGB color.

        If current input mode is:
        - RGB: fills R, G, B
        - LAB: converts RGB to LAB and fills L, a, b
        - HEX: fills HEX
        """
        mode = input_vars["mode_var"].get().strip().upper()

        r, g, b = UtilsTools.safe_rgb_tuple(rgb)

        if mode == "RGB":
            input_vars["v1_var"].set(str(r))
            input_vars["v2_var"].set(str(g))
            input_vars["v3_var"].set(str(b))
            input_vars["hex_var"].set("")

        elif mode == "LAB":
            lab = UtilsTools.rgb_to_lab((r, g, b))
            L, a, b_lab = lab

            input_vars["v1_var"].set(f"{float(L):.2f}")
            input_vars["v2_var"].set(f"{float(a):.2f}")
            input_vars["v3_var"].set(f"{float(b_lab):.2f}")
            input_vars["hex_var"].set("")

        else:
            input_vars["hex_var"].set(UtilsTools.rgb_to_hex((r, g, b)).upper())
            input_vars["v1_var"].set("")
            input_vars["v2_var"].set("")
            input_vars["v3_var"].set("")


    def _open_square_color_picker(
        self, parent, initial_rgb=(217, 217, 217), on_apply=None,
        *, initial_lab=None, granule_name=None, on_granule_submit=None,
        submit_text=None, title=None,
    ):
        """Compatibility entry-point; shared UI lives in UtilsTools."""
        return UtilsTools.open_square_color_picker(
            self, parent, initial_rgb=initial_rgb, on_apply=on_apply,
            initial_lab=initial_lab, granule_name=granule_name,
            on_granule_submit=on_granule_submit, submit_text=submit_text,
            title=title,
        )


    def _update_color_evaluation_conversion_inspector(
        self,
        vars_dict,
        lab=None,
        rgb=None,
        hex_color=None,
        name="Color",
        source="-"
    ):
        """
        Update the Color Inspector.

        There may be two synchronized inspector cards:
        - left inspector for custom/sample mode;
        - full-width inspector for single/prototype-prototype mode.
        """
        def _set_all_preview_colors(fill_color):
            preview_refs = vars_dict.get("inspector_previews")

            if preview_refs:
                for canvas, rect in preview_refs:
                    try:
                        canvas.itemconfig(rect, fill=fill_color)
                    except Exception:
                        pass
                return

            try:
                vars_dict["inspector_preview"].itemconfig(
                    vars_dict["inspector_preview_rect"],
                    fill=fill_color
                )
            except Exception:
                pass

        def _reset_inspector(source_text="-"):
            vars_dict["inspector_title_var"].set("Color Inspector")
            vars_dict["inspector_source_var"].set(f"Source: {source_text}")

            vars_dict["inspector_lab_var"].set("-")
            vars_dict["inspector_rgb_var"].set("-")
            vars_dict["inspector_hex_var"].set("-")
            vars_dict["inspector_luv_var"].set("-")
            vars_dict["inspector_lch_var"].set("-")
            vars_dict["inspector_cie1931_var"].set("-")

            _set_all_preview_colors("#d9d9d9")

        try:
            if lab is None and rgb is None:
                _reset_inspector("-")
                return

            if lab is None and rgb is not None:
                rgb = UtilsTools.safe_rgb_tuple(rgb)
                lab = UtilsTools.rgb_to_lab(rgb)

            if rgb is None and lab is not None:
                rgb = UtilsTools.lab_to_rgb(lab)

            rgb = UtilsTools.safe_rgb_tuple(rgb)
            lab = UtilsTools.safe_lab_tuple(lab)

            if hex_color is None:
                hex_color = UtilsTools.rgb_to_hex(rgb)

            hex_color = str(hex_color).upper()

            if not hex_color.startswith("#"):
                hex_color = "#" + hex_color

            display_name = str(name).strip() if name else "Color"
            display_source = str(source).strip() if source else "-"

            vars_dict["inspector_title_var"].set(f"Color Inspector · {display_name}")
            vars_dict["inspector_source_var"].set(f"Source: {display_source}")

            vars_dict["inspector_lab_var"].set(
                UtilsTools.format_lab_color_value(lab, "CIELAB")
            )
            vars_dict["inspector_rgb_var"].set(
                UtilsTools.format_lab_color_value(lab, "RGB")
            )
            vars_dict["inspector_hex_var"].set(
                UtilsTools.format_lab_color_value(lab, "HEX")
            )
            vars_dict["inspector_luv_var"].set(
                UtilsTools.format_lab_color_value(lab, "CIELUV")
            )
            vars_dict["inspector_lch_var"].set(
                UtilsTools.format_lab_color_value(lab, "LCh")
            )
            vars_dict["inspector_cie1931_var"].set(
                UtilsTools.format_lab_color_value(lab, "CIE1931")
            )

            _set_all_preview_colors(hex_color)

        except Exception:
            _reset_inspector("error")


    def _get_active_color_evaluation_sample(self, vars_dict):
        """
        Compatibility wrapper. Logic lives in ColorEvaluationManager.
        """
        manager = self._get_color_evaluation_manager()
        return manager.get_active_color_evaluation_sample(vars_dict)
    

    def _classify_for_active_thresholds(self, metric_value):
        """
        Classify the active scalar metric value using the active threshold configuration.
        """
        manager = self._get_color_evaluation_manager()
        result = manager.classify_metric_value(
            value=metric_value,
            threshold_settings=self.threshold_settings,
        )
        return result.get("class_label", "Unavailable"), result.get("class_order", 9)


    def _show_color_evaluation_closest_prototypes(self, vars_dict):
        """
        Rank the 7 closest loaded prototypes using the active metric against the active custom color.
        """
        manager = self._get_color_evaluation_manager()

        sample = next((row for row in (
            self._get_color_evaluation_side_sample(vars_dict, "B"),
            self._get_color_evaluation_side_sample(vars_dict, "A"))
                       if row is not None and not row.get("row_label")), None)
        sample_lab = sample["lab"] if sample else None
        sample_rgb = sample["rgb"] if sample else None
        sample_hex = sample["hex"] if sample else None
        sample_name = sample["name"] if sample else "Custom Color"

        metric_name = self.threshold_settings.get("metric", "CIEDE2000")
        vars_dict["analysis_view_mode"] = "closest"

        if (
            sample is None
            or sample_lab is None
            or sample_rgb is None
            or sample_hex is None
        ):
            self._update_color_evaluation_result_card(
                vars_dict=vars_dict,
                title="Custom color required.",
                detail="",
                summary=(
                    "Use 'Evaluate custom color' or 'Sample from image' first. "
                    "The closest-prototype search only works with a custom color."
                ),
                status="unavailable"
            )
            self._update_color_evaluation_membership_panel(vars_dict, sample_lab=None)
            return

        rows = self._extract_color_space_rows(vars_dict.get("loaded_space_data") or {})

        if not rows:
            self._update_color_evaluation_result_card(
                vars_dict=vars_dict,
                title="No prototypes available.",
                detail="",
                summary="Load a valid color space before using closest-prototype mode.",
                status="unavailable"
            )
            return

        top_7 = manager.rank_closest_prototypes(
            sample_lab=sample_lab,
            color_rows=rows,
            metric=metric_name,
            threshold_settings=self.threshold_settings,
            top_n=7,
            fuzzy_color_space=vars_dict.get("loaded_fuzzy_color_space"),
        )

        if not top_7:
            self._update_color_evaluation_result_card(
                vars_dict=vars_dict,
                title="Closest prototype not available.",
                detail="",
                summary="Could not compute color-difference values for the loaded prototypes.",
                status="unavailable"
            )
            return

        best = top_7[0]

        vars_dict["closest_ranking"] = top_7
        vars_dict["closest_best"] = best
        vars_dict["closest_metric"] = metric_name

        summary = manager.format_closest_ranking_summary(
            ranking=top_7,
            metric_name=metric_name,
            threshold_settings=self.threshold_settings,
            include_threshold_description=False
        )

        status = manager.status_from_class_order(best.get("class_order", 9))

        self._update_color_evaluation_result_card(
            vars_dict=vars_dict,
            title=(f"Closest granule: {best.get('granule_label', best['label'])} "
                   f"(category: {best['label']})"
                   if isinstance(vars_dict.get("loaded_fuzzy_color_space"), GranularFuzzyColorSpace)
                   else f"Closest prototype: {best['label']}"),
            detail=f"Minimum {metric_name} = {best.get('metric_value', best['delta_e']):.3f}",
            summary=summary,
            status=status
        )

        self._update_color_evaluation_membership_panel(
            vars_dict,
            sample_lab=sample_lab
        )

        self._update_color_evaluation_conversion_inspector(
            vars_dict=vars_dict,
            lab=sample_lab,
            rgb=sample_rgb,
            hex_color=sample_hex,
            name=sample_name,
            source="custom"
        )


    def _normalize_custom_color_input(self, input_mode, value_1="", value_2="", value_3="", hex_value=""):
        """
        Compatibility wrapper. Logic lives in ColorEvaluationManager.
        """
        manager = self._get_color_evaluation_manager()

        return manager.normalize_custom_color_input(
            input_mode=input_mode,
            value_1=value_1,
            value_2=value_2,
            value_3=value_3,
            hex_value=hex_value,
            utils_tools=UtilsTools,
        )


    def _get_color_evaluation_volume_limits(self, vars_dict):
        """
        Compatibility wrapper. Logic lives in ColorEvaluationManager.
        """
        manager = self._get_color_evaluation_manager()

        space=vars_dict.get("loaded_fuzzy_color_space")
        limits=(ReferenceDomain.default_voronoi_reference_domain()
                if space is not None and space.color_space == "RGB"
                else getattr(self, "volume_limits", None))
        return manager.resolve_volume_limits(
            volume_limits=limits,
            fuzzy_color_space=space,
        )
    

    def _get_color_evaluation_plot_context(
        self,
        vars_dict,
        require_custom=False,
        require_closest=False
    ):
        """
        Build a shared context for all Color Evaluation plots.

        Works with or without custom/sample color.

        Parameters
        ----------
        require_custom : bool
            True when the plot needs a custom/sample color.
        require_closest : bool
            True when the plot needs closest-prototype ranking.
        """
        sample = next((row for row in (
            self._get_color_evaluation_side_sample(vars_dict, "B"),
            self._get_color_evaluation_side_sample(vars_dict, "A"))
                       if row is not None and not row.get("row_label")), None)
        sample_lab = sample["lab"] if sample else None
        sample_rgb = sample["rgb"] if sample else None
        sample_hex = sample["hex"] if sample else None
        has_custom = sample is not None

        if require_custom and not has_custom:
            self.custom_warning(
                "Custom Color Required",
                "Use 'Evaluate custom color' or 'Sample from image' first.",
                parent=getattr(self, "_color_evaluation_window", None)
            )
            return None

        data_source = vars_dict.get("loaded_space_data") or {}
        rows = self._extract_color_space_rows(data_source)

        if not rows:
            self.custom_warning(
                "No Color Space",
                "Load a valid color space first.",
                parent=getattr(self, "_color_evaluation_window", None)
            )
            return None

        if require_closest:
            if not has_custom:
                self.custom_warning(
                    "Custom Color Required",
                    "Closest-prototype plots require a custom or sampled color.",
                    parent=getattr(self, "_color_evaluation_window", None)
                )
                return None

            if not vars_dict.get("closest_ranking"):
                self._show_color_evaluation_closest_prototypes(vars_dict)

        color_data = {}
        hex_color = {}

        loaded_space = vars_dict.get("loaded_fuzzy_color_space")
        display_groups = self._color_evaluation_actual_entries(data_source, loaded_space)
        for _, entries in display_groups:
            for label, lab in entries:
                try:
                    lab_arr = np.asarray(lab, dtype=float).reshape(-1)[:3]
                    color_data[label] = {"positive_prototype": lab_arr}
                    hex_color[UtilsTools.lab_to_hex(lab_arr)] = lab_arr
                except (TypeError, ValueError):
                    continue

        core = vars_dict.get("loaded_cores")
        alpha = vars_dict.get("loaded_prototypes")
        support = vars_dict.get("loaded_supports")
        loaded_space = vars_dict.get("loaded_fuzzy_color_space")
        if isinstance(loaded_space, GranularFuzzyColorSpace):
            core = loaded_space.get_all_cores()
            alpha = loaded_space.get_all_prototypes()
            support = loaded_space.get_all_supports()

        volume_limits = self._get_color_evaluation_volume_limits(vars_dict)

        closest_best = vars_dict.get("closest_best")
        closest_label = None
        closest_lab = None
        closest_hex = None

        if closest_best:
            closest_label = closest_best.get("label")
            if isinstance(loaded_space, GranularFuzzyColorSpace) and closest_best.get("granule_lab") is not None:
                closest_lab = np.asarray(closest_best["granule_lab"], dtype=float)
                closest_label = closest_best.get("granule_label", closest_label)
                closest_hex = UtilsTools.lab_to_hex(closest_lab)

            for label, lab in rows:
                if closest_lab is not None:
                    break
                if str(label) == str(closest_label):
                    closest_lab = np.asarray(lab, dtype=float).reshape(-1)[:3]
                    closest_hex = self._get_evaluation_proto_hex(vars_dict, label)
                    break

        filename = (
            vars_dict.get("loaded_space_name")
            or vars_dict["space_name_var"].get()
            or "Color Space Evaluation"
        )

        metric_name = (
            vars_dict.get("closest_metric")
            or self.threshold_settings.get("metric", "CIEDE2000")
        )

        return {
            "filename": filename,
            "color_data": color_data,
            "core": core,
            "alpha": alpha,
            "support": support,
            "volume_limits": volume_limits,
            "hex_color": hex_color,

            "custom_lab": sample_lab if has_custom else None,
            "custom_rgb": sample_rgb if has_custom else None,
            "custom_hex": sample_hex if has_custom else None,

            "closest_label": closest_label,
            "closest_lab": closest_lab,
            "closest_hex": closest_hex,

            "ranking": vars_dict.get("closest_ranking") or [],
            "metric_name": metric_name,
        }


    def _open_color_evaluation_3d_plot(self, vars_dict):
        """
        Open Plotly 3D LAB visualization.
        Works with or without custom/sample color.
        """
        ctx = self._get_color_evaluation_plot_context(
            vars_dict,
            require_custom=False,
            require_closest=False
        )

        if ctx is None:
            return

        space = vars_dict.get("loaded_fuzzy_color_space")
        mode = space.color_space if space is not None else "LAB"
        points = ctx["color_data"]
        hex_points = ctx["hex_color"]
        if isinstance(space, GranularFuzzyColorSpace):
            points = {}
            hex_points = {}
            for category in space.categories:
                for proto in category.prototypes:
                    lab = np.asarray(space.lab_from_model(proto.positive), dtype=float)
                    points[proto.label] = {"positive_prototype": lab}
                    hex_points[UtilsTools.lab_to_hex(lab)] = lab
        custom = ctx.get("custom_lab")
        closest = ctx.get("closest_lab")
        limits = ctx["volume_limits"]
        if mode == "RGB":
            points = {k:{**v,"positive_prototype":space.model_from_lab(v["positive_prototype"])}
                      for k,v in points.items()}
            hex_points = {key:space.model_from_lab(lab) for key,lab in hex_points.items()}
            custom = space.model_from_lab(custom) if custom is not None else None
            closest = space.model_from_lab(closest) if closest is not None else None
            limits = space.reference_domain
        fig = VisualManager.plot_more_combined_3D(
            filename=ctx["filename"], color_data=points,
            core=ctx["core"], alpha=ctx["alpha"], support=ctx["support"],
            volume_limits=limits, hex_color=hex_points,
            selected_options=["Representative"],
            custom_lab=custom, custom_hex=ctx.get("custom_hex", "#ff0000"),
            closest_label=ctx.get("closest_label"), closest_lab=closest,
            closest_hex=ctx.get("closest_hex", "#000000"),
            color_space=mode,
        )

        self._show_color_eval_plotly_figure_in_browser(
            fig,
            filename_prefix="color_eval_3d_lab"
        )


    def _open_color_evaluation_ab_plot(self, vars_dict):
        """
        Open 2D a*b* projection.
        Works with or without custom/sample color.
        """
        ctx = self._get_color_evaluation_plot_context(
            vars_dict,
            require_custom=False,
            require_closest=False
        )

        if ctx is None:
            return

        fig = VisualManager.plot_color_evaluation_ab_projection(
            color_data=ctx["color_data"],
            hex_color=ctx["hex_color"],
            custom_lab=ctx["custom_lab"],
            custom_hex=ctx["custom_hex"],
            closest_label=ctx["closest_label"],
            closest_lab=ctx["closest_lab"],
            closest_hex=ctx["closest_hex"],
            filename=ctx["filename"],
        )

        self._show_color_eval_plotly_figure_in_browser(
            fig,
            filename_prefix="color_eval_ab_projection"
        )


    def _open_color_evaluation_lc_plot(self, vars_dict):
        """
        Open L*C* projection.
        Works with or without custom/sample color.
        """
        ctx = self._get_color_evaluation_plot_context(
            vars_dict,
            require_custom=False,
            require_closest=False
        )

        if ctx is None:
            return

        fig = VisualManager.plot_color_evaluation_lc_projection(
            color_data=ctx["color_data"],
            hex_color=ctx["hex_color"],
            custom_lab=ctx["custom_lab"],
            custom_hex=ctx["custom_hex"],
            closest_label=ctx["closest_label"],
            closest_lab=ctx["closest_lab"],
            closest_hex=ctx["closest_hex"],
            filename=ctx["filename"],
        )

        self._show_color_eval_plotly_figure_in_browser(
            fig,
            filename_prefix="color_eval_lc_projection"
        )


    def _open_color_evaluation_lch_plot(self, vars_dict):
        """
        Open polar LCh hue/chroma plot.
        Works with or without custom/sample color.
        """
        ctx = self._get_color_evaluation_plot_context(
            vars_dict,
            require_custom=False,
            require_closest=False
        )

        if ctx is None:
            return

        fig = VisualManager.plot_color_evaluation_lch_polar(
            color_data=ctx["color_data"],
            hex_color=ctx["hex_color"],
            custom_lab=ctx["custom_lab"],
            custom_hex=ctx["custom_hex"],
            closest_label=ctx["closest_label"],
            closest_lab=ctx["closest_lab"],
            closest_hex=ctx["closest_hex"],
            filename=ctx["filename"],
        )

        self._show_color_eval_plotly_figure_in_browser(
            fig,
            filename_prefix="color_eval_lch_polar"
        )


    def _open_color_evaluation_top7_plot(self, vars_dict):
        """
        Open horizontal bar chart with the 7 closest prototypes.
        Requires custom/sample color.
        """
        ctx = self._get_color_evaluation_plot_context(
            vars_dict,
            require_custom=True,
            require_closest=True
        )

        if ctx is None:
            return

        ranking = ctx.get("ranking") or []

        if not ranking:
            self.custom_warning(
                "Ranking Not Available",
                "Could not compute the closest prototypes.",
                parent=getattr(self, "_color_evaluation_window", None)
            )
            return

        fig = VisualManager.plot_color_evaluation_top7_bar(
            ranking=ranking,
            metric_name=ctx["metric_name"],
            title=f"Top 7 closest prototypes | {ctx['metric_name']}",
            threshold_settings=self.threshold_settings,
        )

        self._show_color_eval_plotly_figure_in_browser(
            fig,
            filename_prefix="color_eval_top7"
        )


    def _open_color_evaluation_membership_plot(self, vars_dict):
        """Bar chart for the active external sample, on either side A or B."""
        sample = next((color for color in (
            self._get_color_evaluation_side_sample(vars_dict, "B"),
            self._get_color_evaluation_side_sample(vars_dict, "A"))
                       if color is not None and not color.get("row_label")), None)
        if sample is None:
            self.custom_warning("Custom Color Required",
                                "Add a custom or image sample to A or B first.",
                                parent=getattr(self, "_color_evaluation_window", None))
            return
        memberships = self._calculate_evaluation_memberships(vars_dict, sample["lab"])
        if not memberships:
            self.custom_warning("Memberships Not Available",
                                "No fuzzy membership data are available for this sample.",
                                parent=getattr(self, "_color_evaluation_window", None))
            return
        fig = VisualManager.plot_color_evaluation_membership_bar(
            memberships=memberships,
            title=f"Membership degrees | {sample['name']}", top_n=10)
        self._show_color_eval_plotly_figure_in_browser(
            fig, filename_prefix="color_eval_memberships")

    def _open_color_evaluation_component_plot(self, vars_dict):
        """Graph signed LAB/LCh components between any actual colors A and B."""
        first = self._get_color_evaluation_side_sample(vars_dict, "A")
        second = self._get_color_evaluation_side_sample(vars_dict, "B")
        if first is None or second is None:
            self.custom_warning("Comparison Required",
                                "Select both a color A and a color B first.",
                                parent=getattr(self, "_color_evaluation_window", None))
            return
        components = self._calculate_color_evaluation_component_differences(
            first["lab"], second["lab"])
        fig = VisualManager.plot_color_evaluation_component_differences(
            components=components,
            title=f"Component differences | {first['name']} vs {second['name']}")
        self._show_color_eval_plotly_figure_in_browser(
            fig, filename_prefix="color_eval_components")

    def _calculate_color_evaluation_component_differences(self, lab_1, lab_2):
        """
        Compatibility wrapper. Logic lives in ColorEvaluationManager.
        """
        manager = self._get_color_evaluation_manager()
        return manager.calculate_visual_component_differences(lab_1, lab_2)


    def _show_color_eval_plotly_figure_in_browser(
        self,
        fig,
        filename_prefix="color_eval_plot"
    ):
        """
        Open a Color Evaluation Plotly figure in the default browser.
        """
        self._open_plotly_figure_in_browser(
            fig,
            filename_prefix=filename_prefix
        )


    def _get_color_evaluation_available_graph_keys(self, vars_dict):
        """
        Return the graph buttons that should be visible according to the current state.
        The state logic lives in ColorEvaluationManager; the GUI only filters by available openers.
        """
        manager = self._get_color_evaluation_manager()

        data_source = vars_dict.get("loaded_space_data") or {}
        rows = self._extract_color_space_rows(data_source)

        secondary_mode = vars_dict.get("secondary_mode")
        has_primary = self._get_color_evaluation_side_sample(vars_dict, "A") is not None

        has_custom = any(
            vars_dict.get(prefix + "_mode") == "custom"
            and vars_dict.get(prefix + "_custom_lab") is not None
            for prefix in ("primary", "secondary")
        )
        if secondary_mode is None and has_custom:
            secondary_mode = "custom"

        available = manager.get_color_evaluation_available_graph_keys(
            rows=rows,
            secondary_mode=secondary_mode,
            has_primary=has_primary,
            secondary_label_available=vars_dict.get("secondary_label") is not None,
            has_custom=has_custom,
            has_fuzzy_color_space=vars_dict.get("loaded_fuzzy_color_space") is not None,
        )
        # A single external sample is enough for ranking/memberships, but not
        # for a component-difference graph, which always requires two colors.
        if self._get_color_evaluation_side_sample(vars_dict, "B") is None:
            available = [key for key in available if key != "components"]

        method_map = {
            "3d": "_open_color_evaluation_3d_plot",
            "ab": "_open_color_evaluation_ab_plot",
            "lc": "_open_color_evaluation_lc_plot",
            "lch": "_open_color_evaluation_lch_plot",
            "top7": "_open_color_evaluation_top7_plot",
            "memberships": "_open_color_evaluation_membership_plot",
            "components": "_open_color_evaluation_component_plot",
        }

        return [
            key
            for key in available
            if callable(getattr(self, method_map.get(key, ""), None))
        ]


    def _create_color_evaluation_graph_buttons_card(self, parent, vars_dict):
        """
        Create a compact Graphs card.

        The card is shown in the right-side analysis column.
        The actual buttons are rebuilt dynamically by
        _update_color_evaluation_graph_buttons() so the layout can change:
        - one column for single color / prototype-prototype comparison;
        - two columns for custom/sample color mode.
        """
        graph_buttons_card = tk.Frame(
            parent,
            bg="#fafafa",
            bd=1,
            relief="solid"
        )

        tk.Label(
            graph_buttons_card,
            text="Graphs",
            font=("Sans", 9, "bold"),
            anchor="w",
            bg="#fafafa",
            padx=8,
            pady=4
        ).pack(fill="x")

        graph_buttons_body = tk.Frame(
            graph_buttons_card,
            bg="#fafafa"
        )
        graph_buttons_body.pack(
            fill="x",
            padx=8,
            pady=(0, 8)
        )

        graph_specs = {
            "3d": {
                "text": "3D LAB",
                "command": lambda: self._open_color_evaluation_3d_plot(vars_dict)
            },
            "ab": {
                "text": "a*b*",
                "command": lambda: self._open_color_evaluation_ab_plot(vars_dict)
            },
            "lc": {
                "text": "L*C*",
                "command": lambda: self._open_color_evaluation_lc_plot(vars_dict)
            },
            "lch": {
                "text": "LCh",
                "command": lambda: self._open_color_evaluation_lch_plot(vars_dict)
            },
            "top7": {
                "text": "Top 7",
                "command": lambda: self._open_color_evaluation_top7_plot(vars_dict)
            },
            "memberships": {
                "text": "Memberships",
                "command": lambda: self._open_color_evaluation_membership_plot(vars_dict)
            },
            "components": {
                "text": "Components Δ",
                "command": lambda: self._open_color_evaluation_component_plot(vars_dict)
            },
        }

        graph_buttons_card._pyfcs_graph_body = graph_buttons_body
        graph_buttons_card._pyfcs_graph_specs = graph_specs

        return graph_buttons_card


    def _update_color_evaluation_graph_buttons(self, vars_dict):
        """Display available graphs in a wide, responsive horizontal toolbar."""
        refs = vars_dict.get("analysis_result_refs", {})
        side_card = refs.get("graph_buttons_card")
        results_columns = refs.get("results_columns")
        membership_right = refs.get("membership_right")
        if side_card is None:
            return
        body = getattr(side_card, "_pyfcs_graph_body", None)
        specs = getattr(side_card, "_pyfcs_graph_specs", {})
        if body is None:
            return

        has_custom = any(
            vars_dict.get(prefix + "_mode") == "custom"
            and vars_dict.get(prefix + "_custom_lab") is not None
            for prefix in ("primary", "secondary")
        )
        try:
            if results_columns is not None:
                results_columns.grid_columnconfigure(1, minsize=215 if has_custom else 0,
                                                     weight=0)
            if membership_right is not None:
                membership_right.configure(width=215)
        except tk.TclError:
            pass

        available = self._get_color_evaluation_available_graph_keys(vars_dict)
        for child in body.winfo_children():
            child.destroy()
        if not available:
            side_card.pack_forget()
            return
        if not side_card.winfo_manager():
            side_card.pack(fill="x", pady=(8, 0))

        # 3D LAB / a*b* / L*C* / LCh are always available; additional analyses
        # appear below only when their prerequisites are satisfied.
        ordered = [key for key in ("3d", "ab", "lc", "lch", "top7", "memberships", "components")
                   if key in available and key in specs]
        for offset in range(0, len(ordered), 4):
            row = tk.Frame(body, bg="#fafafa")
            row.pack(fill="x", pady=(0, 5 if offset + 4 < len(ordered) else 0))
            for key in ordered[offset:offset + 4]:
                spec = specs[key]
                tk.Button(
                    row, text=spec["text"], command=spec["command"],
                    font=("Segoe UI", 9), bg="#f8fafc", fg="#253044",
                    relief="solid", bd=1, pady=5, cursor="hand2",
                    activebackground=UtilsTools.UI_ACCENT_SOFT
                ).pack(side="left", fill="x", expand=True, padx=3)





def start_up():
    root = tk.Tk()
    app = PyFCSApp(root)
    root.mainloop()

if __name__ == '__main__':
    start_up()

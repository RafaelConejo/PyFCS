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
import platform
import threading
import webbrowser
import numpy as np
import tkinter as tk
from pathlib import Path
from PIL import Image, ImageTk
from tkinter import ttk, Menu, messagebox, DISABLED, NORMAL

# Project modules
from Source.input_output.Input import Input
from Source.interface.modules.visualization.VisualManager import VisualManager
from Source.interface.modules.visualization.Model3DManager import Model3DManager
from Source.colorspace.ReferenceDomain import ReferenceDomain
from Source.fuzzy.FuzzyColorSpace import FuzzyColorSpace
from Source.fuzzy.GranularFuzzyColorSpace import GranularFuzzyColorSpace
from Source.fuzzy.FuzzyColorSpaceBuilder import FuzzyColorSpaceBuilder, rebuild_in_color_space, lab_to_rgb_model_checked
from Source.interface.modules.image.ColorProcessingEngine import ColorProcessingEngine, mapping_membership_summary
from Source.interface.modules.creation.FuzzyColorSpaceManager import FuzzyColorSpaceManager
from Source.interface.modules.evaluation.ColorEvaluationManager import (ColorEvaluationManager, membership_snapshot, nearest_granule)
from Source.interface.modules.evaluation.ColorEvaluationWindow import ColorEvaluationWindow
from Source.interface.modules.image.ImageInspectionManager import ImageInspectionManager
from Source.interface.modules.image.ImageDisplayManager import ImageDisplayManager
from Source.interface.modules.image.ColorMappingManager import ColorMappingManager
from Source.interface.modules.creation.ImageBasedCreationManager import ImageBasedCreationManager
from Source.interface.modules.creation.PaletteBasedCreationManager import PaletteBasedCreationManager
import Source.interface.modules.data.DataManager as DataManager

import Source.interface.modules.common.UtilsTools as UtilsTools


def _image_display_attribute(name):
    """Forward legacy workspace attributes without duplicating manager state."""
    def get(app):
        return getattr(app.image_display, name)
    def set_(app, value):
        setattr(app.image_display, name, value)
    def delete(app):
        delattr(app.image_display, name)
    return property(get, set_, delete)


def _mapping_attribute(name):
    """Forward legacy mapping state to its sole owner."""
    def get(app):
        return getattr(app.color_mapping_manager, name)
    def set_(app, value):
        setattr(app.color_mapping_manager, name, value)
    def delete(app):
        delattr(app.color_mapping_manager, name)
    return property(get, set_, delete)


class PyFCSApp:
    # Embed the distributed license so that Help > License also works in the
    # one-file executable, where a repository-level LICENSE may not be present.
    MIT_LICENSE_TEXT = 'MIT License\n\nCopyright (c) 2025 Rafael Vázquez Conejo\n\nPermission is hereby granted, free of charge, to any person obtaining a copy\nof this software and associated documentation files (the "Software"), to deal\nin the Software without restriction, including without limitation the rights\nto use, copy, modify, merge, publish, distribute, sublicense, and/or sell\ncopies of the Software, and to permit persons to whom the Software is\nfurnished to do so, subject to the following conditions:\n\nThe above copyright notice and this permission notice shall be included in all\ncopies or substantial portions of the Software.\n\nTHE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\nIMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\nFITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE\nAUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\nLIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\nOUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE\nSOFTWARE.\n'

    # Color Evaluation window state is owned by its controller.
    @property
    def _color_evaluation_paned(self):
        return self.color_evaluation_window._color_evaluation_paned

    @_color_evaluation_paned.setter
    def _color_evaluation_paned(self, value):
        self.color_evaluation_window._color_evaluation_paned = value

    @property
    def _color_evaluation_vars(self):
        return self.color_evaluation_window._color_evaluation_vars

    @_color_evaluation_vars.setter
    def _color_evaluation_vars(self, value):
        self.color_evaluation_window._color_evaluation_vars = value

    @property
    def _color_evaluation_window(self):
        return self.color_evaluation_window._color_evaluation_window

    @_color_evaluation_window.setter
    def _color_evaluation_window(self, value):
        self.color_evaluation_window._color_evaluation_window = value

    # Transitional compatibility for consumers of the original image workspace API.
    # The manager is the single owner; aliases never create a second copy.
    _full_resolution_workspace_controller = _image_display_attribute('_full_resolution_workspace_controller')
    _image_view_pan_state = _image_display_attribute('_image_view_pan_state')
    _image_workspace_active_id = _image_display_attribute('_image_workspace_active_id')
    _image_workspace_callbacks = _image_display_attribute('_image_workspace_callbacks')
    _image_workspace_focus_id = _image_display_attribute('_image_workspace_focus_id')
    _image_workspace_focus_return_mode = _image_display_attribute('_image_workspace_focus_return_mode')
    _image_workspace_focus_saved_collapsed = _image_display_attribute('_image_workspace_focus_saved_collapsed')
    _image_workspace_focus_saved_state = _image_display_attribute('_image_workspace_focus_saved_state')
    _image_workspace_layout_mode = _image_display_attribute('_image_workspace_layout_mode')
    _image_workspace_move_state = _image_display_attribute('_image_workspace_move_state')
    _image_workspace_reflow_after_id = _image_display_attribute('_image_workspace_reflow_after_id')
    _image_zoom_callbacks = _image_display_attribute('_image_zoom_callbacks')
    _image_zoom_hover_window = _image_display_attribute('_image_zoom_hover_window')
    _image_zoom_mousewheel_bound = _image_display_attribute('_image_zoom_mousewheel_bound')
    _original_sampling_state = _image_display_attribute('_original_sampling_state')
    _pixel_click_callbacks = _image_display_attribute('_pixel_click_callbacks')
    _resize_callbacks = _image_display_attribute('_resize_callbacks')
    _resize_start = _image_display_attribute('_resize_start')
    display_pil = _image_display_attribute('display_pil')
    floating_images = _image_display_attribute('floating_images')
    floating_window_state = _image_display_attribute('floating_window_state')
    image_canvas = _image_display_attribute('image_canvas')
    image_dimensions = _image_display_attribute('image_dimensions')
    image_view_source = _image_display_attribute('image_view_source')
    image_view_state = _image_display_attribute('image_view_state')
    image_workspace_focus_button = _image_display_attribute('image_workspace_focus_button')
    image_workspace_grid_button = _image_display_attribute('image_workspace_grid_button')
    image_workspace_status_var = _image_display_attribute('image_workspace_status_var')
    image_workspace_vscroll = _image_display_attribute('image_workspace_vscroll')
    images = _image_display_attribute('images')
    load_images_names = _image_display_attribute('load_images_names')
    original_image_dimensions = _image_display_attribute('original_image_dimensions')
    original_images = _image_display_attribute('original_images')
    pil_images_original = _image_display_attribute('pil_images_original')

    # Mapping controller owns the job registry, result caches and legend state.
    CAN_APPLY_MAPPING = _mapping_attribute('CAN_APPLY_MAPPING')
    SHOW_ORIGINAL = _mapping_attribute('SHOW_ORIGINAL')
    _image_job_counter = _mapping_attribute('_image_job_counter')
    _mapping_all_initial_view = _mapping_attribute('_mapping_all_initial_view')
    _mapping_all_pack_by_window = _mapping_attribute('_mapping_all_pack_by_window')
    _mapping_all_palette_by_window = _mapping_attribute('_mapping_all_palette_by_window')
    _mapping_tconorm_buttons = _mapping_attribute('_mapping_tconorm_buttons')
    cm_cache_by_image = _mapping_attribute('cm_cache_by_image')
    current_protos = _mapping_attribute('current_protos')
    image_jobs = _mapping_attribute('image_jobs')
    image_mapping_dock = _mapping_attribute('image_mapping_dock')
    image_mapping_dock_visible = _mapping_attribute('image_mapping_dock_visible')
    mapping_locked_until_original = _mapping_attribute('mapping_locked_until_original')
    modified_image = _mapping_attribute('modified_image')
    proto_options = _mapping_attribute('proto_options')
    proto_percentage_cache_by_image = _mapping_attribute('proto_percentage_cache_by_image')
    window_image_key = _mapping_attribute('window_image_key')
    window_mapping_mode = _mapping_attribute('window_mapping_mode')

    def __init__(self, root):
        # Core references / managers
        self.root = root
        self._retiring_workspace_workers = []
        self.image_display = ImageDisplayManager(self)
        self.color_mapping_manager = ColorMappingManager(self)
        self.color_evaluation_window = ColorEvaluationWindow(self)
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
        self._image_based_creation_controller = None
        self._image_based_creation_window = None
        self._palette_based_creation_controller = None
        self._palette_based_creation_window = None


        self.volume_limits = ReferenceDomain.default_voronoi_reference_domain()
        # Geometry settings are stored in each .json; this is the in-session default.
        self._fcs_creation_defaults = {"color_space": "LAB", "lambda1": 0.5,
                                       "lambda2": 1.5, "disjoint": True,
                                       "covering": True, "samples": 27}

        # Shared runtime state
        self.COLOR_SPACE = False
        self.FIRST_DBSCAN = True
        self.hex_color = []
        self.color_entry_detect = {}

        # Additional runtime state
        self.rgb_data = []
        self.model_3d = Model3DManager(self)
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
                font=FONT_BOLD,
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
        self.menu_display_threshold.add_command(
            label="Both thresholds (PT + AT)",
            command=self.deploy_pt_at
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

        image_area_frame = self.image_display.build_workspace(
            main_paned, CARD_BG=CARD_BG, PANEL_BG=PANEL_BG, MUTED=MUTED,
            TEXT=TEXT, BLUE_BG=BLUE_BG, FONT_TITLE=FONT_TITLE,
            FONT_SMALL=FONT_SMALL, FONT_SMALL_BOLD=FONT_SMALL_BOLD,
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
        self.model_3d.build_tab(
            CARD_BG=CARD_BG, PANEL_BG=PANEL_BG, MUTED=MUTED, TEXT=TEXT,
            BLUE=BLUE, FONT=FONT, FONT_BOLD=FONT_BOLD,
            FONT_SMALL=FONT_SMALL, FONT_SMALL_BOLD=FONT_SMALL_BOLD,
        )

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

        self.data_scrollbar_v = UtilsTools.styled_scrollbar(
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
        """Exit only when background jobs cannot leave partial user files.

        Mapping cancellation is asynchronous; a cancelled thread may still be
        flushing results. Saving and model construction cannot be interrupted
        safely. Keep the GUI responsive until all workers have actually exited.
        """
        if self._has_any_active_job():
            self.custom_warning(
                "Process Running",
                "A background operation is still running. Finish or cancel it "
                "and allow it to stop before exiting PyFCS.",
                parent=self.root,
            )
            return
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


    def show_loading_color_space(self, parent=None):
        """Display a compact loading dialog while a color space is prepared."""
        parent_win = self._get_active_dialog_parent(parent if parent is not None else self.root)
        popup = tk.Toplevel(parent_win)
        popup.withdraw()
        popup.title("Loading Color Space")
        popup.configure(bg="#f6f6f8")
        popup.resizable(False, False)
        popup.transient(parent_win)
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
        self.center_popup_to_parent(popup, 430, 188, parent=parent_win)
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
        scrollbar = UtilsTools.styled_scrollbar(body, orient="vertical")
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
            # Toplevel bindtags also receive Destroy events from children.
            # A row, modal dialog or search widget is not the creator itself.
            if _event is not None and _event.widget is not window:
                return
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
        # Prefer controller cleanup (cancel search/detection/idle callbacks).
        # Keep the window as fallback even if legacy tracking lost its entry.
        for attr in ("_palette_based_creation_controller", "_image_based_creation_controller"):
            controller = getattr(self, attr, None)
            if controller is not None:
                windows.append(controller.win)
                try:
                    controller.close()
                except (tk.TclError, RuntimeError):
                    pass
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
        if self._has_any_active_job():
            self.custom_warning("Process Running", "Finish or cancel the current operation before starting another creation.")
            return False
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


    def _open_plotly_figure_in_browser(self, fig, filename_prefix="plot", color_tree=None):
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

            if color_tree is not None:
                VisualManager.write_model_3d_html(fig, file_path, color_tree)
            else:
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

            self.COLOR_SPACE = False
            self.model_3d.clear_selection()

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
        if prebuilt is None and getattr(space, "hierarchy", None):
            raise ValueError("Base geometry changes would invalidate hierarchy references. "
                             "Use Edit Fuzzy Color Space to manage semantic groups.")
        if prebuilt is None and getattr(space, "geometry_only_import", False):
            raise ValueError("Cannot rebuild geometry-only data without the original construction sites.")
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

        # Show Search and selection controls when a model is loaded.
        self.model_3d.show_selection_controls()

        locked = getattr(self, "mapping_locked_until_original", {}) or {}
        self.CAN_APPLY_MAPPING = {
            key: not bool(locked.get(key, False))
            for key in self.CAN_APPLY_MAPPING
        }

        # Synchronize canonical labels before Model 3D is refreshed. Data is
        # rendered afterwards; its previous matrix may still contain a renamed
        # category or a color that is now a semantic parent.
        self.color_matrix = ([cat.label for cat in self.fuzzy_color_space.categories]
                             if isinstance(self.fuzzy_color_space, GranularFuzzyColorSpace)
                             else [p.label for p in self.fuzzy_color_space.prototypes])
        self.hex_color = {UtilsTools.lab_to_hex(row["positive_prototype"]): row["positive_prototype"]
                          for row in self.color_data.values()}
        self.model_3d.refresh_model()


    def _sync_image_mapping_tconorm_buttons(self):
        return self.color_mapping_manager._sync_image_mapping_tconorm_buttons()

    def _set_image_mapping_tconorm(self, operator):
        return self.color_mapping_manager._set_image_mapping_tconorm(operator)

    def _prepare_open_images_for_color_space_change(self):
        return self.color_mapping_manager._prepare_open_images_for_color_space_change()


    def _invalidate_mapping_caches(self):
        return self.color_mapping_manager._invalidate_mapping_caches()


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
            warning_message = getattr(new_fuzzy_color_space, "import_warnings", None)
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
        self.model_3d._reset_3d_canvas()
        self.update_prototypes_info()
        self._update_model_space_indicator()

    def load_color_space(self, filename=None, *, on_success=None, parent=None):
        """Start loading asynchronously so the Loading indicator keeps moving.

        Returns True when a load is successfully *started* (not completed).
        The optional on_success callback runs on Tk's thread only after the
        model has been committed. No work on Tk widgets runs in the worker.
        An explicit parent owns every loading dialog from the start, including
        errors and confirmations, so a fullscreen tool does not raise root.
        """
        def dialog_parent():
            if parent is not None:
                try:
                    if parent.winfo_exists():
                        return parent
                except tk.TclError:
                    pass
            return self.root

        if self._has_any_active_job():
            self.custom_warning(
                "Process Running",
                "There is a process currently running. Please wait for it to finish or cancel it before loading a Color Space.",
                parent=dialog_parent() if parent is not None else None,
            )
            return False

        if filename is None:
            filename = UtilsTools.prompt_file_selection(
                "fuzzy_color_spaces/",
                parent=(dialog_parent() if parent is not None else
                        self._get_active_dialog_parent(
                            getattr(self, "_color_evaluation_window", None)))
            )
        if not filename:
            return False
        if getattr(self, "_model_space_unsaved", False):
            if not messagebox.askyesno(
                "Unsaved Model Color Space",
                "The reconstructed model has not been saved.\n\n"
                "Load another color space and discard it?",
                parent=dialog_parent(),
            ):
                return False

        self._loading_color_space_running = True
        try:
            self.show_loading_color_space(parent=dialog_parent())
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
                self.custom_warning("File Error", str(error),
                                    parent=dialog_parent() if parent is not None else None)
                return
            if prepared["warning_message"]:
                messagebox.showwarning(
                    ("CNS File Warning" if prepared.get("source_type") == "cns"
                     else "JSON Import Warning"),
                    prepared["warning_message"], parent=dialog_parent()
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
                        choices.append(tuple(float(v) for v in xyz))
                negative_choices[new_name] = [v if isinstance(v,str) else {"native":list(v)}
                                              for v in dict.fromkeys(choices)]
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
                    np.asarray(lab, dtype=float) if mode == "LAB" else
                    (np.asarray(self.color_checks[label]["native_rgb"], dtype=float)
                     if self.color_checks[label].get("native_rgb") is not None else
                     lab_to_rgb_model_checked(np.asarray(lab, dtype=float).reshape(1, 3))[0])
                )
                for label, lab in selected_colors_lab.items()
            }
            Voronoi._validate_points_in_domain(
                np.asarray(list(points.values())), domain, Voronoi.DEFAULT_EPS
            )
            save_options = dict(options)
            if mode == "RGB":
                native = {}
                for label, lab in selected_colors_lab.items():
                    raw = self.color_checks[label].get("native_rgb")
                    if raw is not None:
                        xyz = np.asarray(raw, dtype=float).reshape(-1)
                        if xyz.shape != (3,) or not np.all(np.isfinite(xyz)) or np.any((xyz < 0) | (xyz > 255)):
                            raise ValueError(f"Invalid native RGB prototype for '{label}'.")
                        native[label] = xyz.copy()
                    else:
                        native[label] = points[label]
                save_options["model_points"] = native
            return self.save_cs(name, selected_colors_lab, options=save_options)

        dialog = UtilsTools.FCSCreationDialog(
            parent_win,
            selected_colors_lab,
            on_accept=on_create,
            warn=self.custom_warning,
            native_rgb={k:{k:self.color_checks[k].get('native_rgb')} for k in selected_colors_lab},
            app=self,
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
                    {"label": proto.label, "prototype": lab,
                     **({"native_rgb": proto.positive.copy()} if fuzzy_color_space.color_space == "RGB" else {})}
                    for proto, lab in zip(category.prototypes, labs)
                ]
                row["positive_prototype"] = labs[0].copy()
                row["Color"] = labs[0].tolist()
                if fuzzy_color_space.color_space == "RGB":
                    row["native_rgb"] = category.prototypes[0].positive.copy()
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
        safe_name, error = UtilsTools.check_color_space_name(name)
        if error:
            self.custom_warning("Invalid Color Space Name", error)
            return False
        target_file = os.path.abspath(os.path.join(
            UtilsTools.get_color_space_dir(), safe_name + ".json"
        ))

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

        # Keep the configuration alive until the worker finishes, for both
        # Automatic and Custom. No file or active space is committed on failure.
        creation_dialog = None
        if not apply_after_save:
            try:
                grabbed = self.root.grab_current()
                if isinstance(grabbed, UtilsTools.FCSCreationDialog):
                    creation_dialog = grabbed
            except tk.TclError:
                pass
        self._processing_job_running = True
        try:
            self.show_loading(
                title="Processing Color Space",
                message="Building Core, Voronoi and Support geometry...",
                note="The color-space file is saved only after processing succeeds."
            )
            if creation_dialog is not None:
                creation_dialog.begin_save()
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
                modified_hierarchy = save_options.pop("_modified_hierarchy", None)
                modified_negatives = save_options.pop("_modified_negatives", None)
                modified_negative_names = save_options.pop("_modified_negative_names", None)
                save_options.pop("_from_modify_fcs", None)
                if modified_draft is not None:
                    prepared = DataManager.build_model_from_draft(
                        name, modified_draft, original_model, target_for_modify,
                        hierarchy=modified_hierarchy, negative_override=modified_negatives,
                        negative_names_override=modified_negative_names,
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
                    if creation_dialog is not None and creation_dialog.winfo_exists():
                        creation_dialog.on_save_failure(str(error))
                        self.custom_warning("Error", f"An error occurred while saving: {error}", parent=creation_dialog)
                    else:
                        self.custom_warning("Error", f"An error occurred while saving: {error}")
                elif apply_after_save:
                    file_path, space = result
                    if editing_from_modify and editor is not None:
                        editor.on_save_success()
                    self._on_apply_changes_saved_success(
                        name, file_path, saved_color_data, space
                    )
                else:
                    if creation_dialog is not None and creation_dialog.winfo_exists():
                        creation_dialog.on_save_success()
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
            if creation_dialog is not None and creation_dialog.winfo_exists():
                creation_dialog.on_save_failure('Could not start construction.')
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
        return self.image_display._get_best_image_source_pil(window_id, prefer_current_view, rgb)


    # ============================================================================================================================================================
    #  MODEL 3D COMPATIBILITY ENTRY POINTS
    # ============================================================================================================================================================

    # Compatibility entry points for the desktop controller.
    def on_option_select(self):
        return self.model_3d.on_option_select()

    def on_add_graph(self, selected_options):
        return self.model_3d.on_add_graph(selected_options)

    def select_all_color(self):
        return self.model_3d.select_all_color()

    def deselect_all_color(self):
        return self.model_3d.deselect_all_color()

    def select_color(self):
        return self.model_3d.select_color()

    def display_color_buttons(self, colors):
        return self.model_3d.display_color_buttons(colors)

    def get_umbral_points(self, threshold=None, mode=None):
        return self.model_3d.get_umbral_points(threshold, mode)

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
                "Check the current workspace before continuing.\n\n"
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
            n_categories = len(model.get_all_category_labels())
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
        self.model_3d._reset_3d_canvas()
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
        if (getattr(self.fuzzy_color_space, "source_file_format", "") == "JAVA_JSON_REFERENCE"
                and "reused across" in getattr(self.fuzzy_color_space, "import_warnings", "")):
            self.custom_warning("Edit Fuzzy Color Space",
                                "This Java export has ambiguous geometry references. "
                                "Use an unambiguous reconstruction for editing.")
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
            self.model_3d._reset_3d_canvas()
            self.model_3d._reset_3d_view_state()

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
        return self.image_display.save_image(window_id)


    def open_full_resolution_image_workspace(self, window_id=None):
        return self.image_display.open_full_resolution_image_workspace(window_id)


    def close_all_image(self):
        return self.image_display.close_all_image()


    def _image_workspace_window_ids(self):
        return self.image_display._image_workspace_window_ids()


    def _update_image_workspace_status(self):
        return self.image_display._update_image_workspace_status()


    def _cancel_image_workspace_reflow(self):
        return self.image_display._cancel_image_workspace_reflow()

    def _schedule_image_workspace_reflow(self, delay=35):
        return self.image_display._schedule_image_workspace_reflow(delay)


    def _set_image_workspace_active(self, window_id):
        return self.image_display._set_image_workspace_active(window_id)


    def _display_cached_mapping_all(self, window_id):
        return self.color_mapping_manager._display_cached_mapping_all(window_id)

    def _set_mapping_all_palette(self, window_id, scheme):
        return self.color_mapping_manager._set_mapping_all_palette(window_id, scheme)

    def _set_mapping_all_level(self, window_id, level):
        return self.color_mapping_manager._set_mapping_all_level(window_id, level)

    def _toggle_mapping_all_palette(self, window_id):
        return self.color_mapping_manager._toggle_mapping_all_palette(window_id)


    def _arrange_image_workspace_grid(self):
        return self.image_display._arrange_image_workspace_grid()


    def _set_image_workspace_manual(self):
        return self.image_display._set_image_workspace_manual()


    def _focus_active_image_workspace_card(self):
        return self.image_display._focus_active_image_workspace_card()


    def _set_image_workspace_focus(self, window_id=None):
        return self.image_display._set_image_workspace_focus(window_id)


    def _toggle_image_workspace_focus(self, window_id):
        return self.image_display._toggle_image_workspace_focus(window_id)


    def _is_workspace_card_collapsed(self, window_id):
        return self.image_display._is_workspace_card_collapsed(window_id)


    def _sync_workspace_card_item_states(self, window_id):
        return self.image_display._sync_workspace_card_item_states(window_id)


    def _set_workspace_card_visibility(self, window_id, visible=True):
        return self.image_display._set_workspace_card_visibility(window_id, visible)


    def _workspace_legend_width(self, window_id):
        return self.image_display._workspace_legend_width(window_id)


    def _workspace_legend_height(self, window_id):
        return self.image_display._workspace_legend_height(window_id)


    def _workspace_legend_extra_height(self, window_id):
        return self.image_display._workspace_legend_extra_height(window_id)


    def _toggle_image_card_minimize(self, window_id):
        return self.image_display._toggle_image_card_minimize(window_id)


    def _update_manual_workspace_scrollregion(self):
        return self.image_display._update_manual_workspace_scrollregion()


    def _reflow_image_workspace(self):
        return self.image_display._reflow_image_workspace()


    def open_image(self):
        return self.image_display.open_image()


    def _clear_original_selection_rectangle(self, window_id):
        return self.image_display._clear_original_selection_rectangle(window_id)


    def _clear_image_display_selection(self, window_id=None, clear_info=True):
        return self.image_display._clear_image_display_selection(window_id, clear_info)


    def _get_image_view_crop_box(self, window_id):
        return self.image_display._get_image_view_crop_box(window_id)


    def _canvas_xy_to_view_source(self, window_id, canvas_x, canvas_y):
        return self.image_display._canvas_xy_to_view_source(window_id, canvas_x, canvas_y)


    def _view_source_xy_to_original(self, window_id, source_x, source_y):
        return self.image_display._view_source_xy_to_original(window_id, source_x, source_y)


    def _canvas_xy_to_original_image(self, window_id, canvas_x, canvas_y):
        return self.image_display._canvas_xy_to_original_image(window_id, canvas_x, canvas_y)


    def _set_image_zoom_source(self, window_id, pil_source, reset_zoom=True):
        return self.image_display._set_image_zoom_source(window_id, pil_source, reset_zoom)


    def _ensure_image_zoom_mousewheel_binding(self):
        return self.image_display._ensure_image_zoom_mousewheel_binding()


    def create_floating_window(self, x, y, filename):
        return self.image_display.create_floating_window(x, y, filename)


    def _ensure_image_jobs(self):
        return self.color_mapping_manager._ensure_image_jobs()


    def _window_exists(self, window_id):
        """Returns True if the floating window still exists on the canvas."""
        try:
            items = self.image_canvas.find_withtag(window_id)
            return bool(items)
        except Exception:
            return False


    def _has_active_job(self, window_id):
        return self.color_mapping_manager._has_active_job(window_id)


    def _is_current_job(self, window_id, job_id):
        return self.color_mapping_manager._is_current_job(window_id, job_id)


    def _cancel_window_job(self, window_id, cleanup_ui=True):
        return self.color_mapping_manager._cancel_window_job(window_id, cleanup_ui)


    def _is_job_cancelled(self, window_id, cancel_event, job_id):
        return self.color_mapping_manager._is_job_cancelled(window_id, cancel_event, job_id)


    def _start_window_job(self, window_id, kind, target):
        return self.color_mapping_manager._start_window_job(window_id, kind, target)


    def _raise_all_loading_panels(self):
        return self.color_mapping_manager._raise_all_loading_panels()


    def _show_window_loading(self, window_id, text='Processing...'):
        return self.color_mapping_manager._show_window_loading(window_id, text)


    def _hide_window_loading(self, window_id):
        return self.color_mapping_manager._hide_window_loading(window_id)


    def _update_window_progress(self, window_id, job_id, current_step, total_steps):
        return self.color_mapping_manager._update_window_progress(window_id, job_id, current_step, total_steps)


    def _reposition_window_loading(self, window_id):
        return self.color_mapping_manager._reposition_window_loading(window_id)


    def _has_any_active_job(self):
        """Returns True if there is any running job in any image/window."""
        self._ensure_image_jobs()
        retired = getattr(self, "_retiring_workspace_workers", [])
        retired[:] = [(worker, controller) for worker, controller in retired if worker.is_alive()]
        if retired:
            return True
        creation = getattr(self, "_image_based_creation_controller", None)
        worker = getattr(creation, "_detection_worker", None)
        if getattr(creation, "_detection_running", False) or (worker is not None and worker.is_alive()):
            return True

        if (getattr(self.model_3d, "_threshold_job_running", False)
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
            if th is not None and th.is_alive():
                return True
        return False


    def _reposition_proto_options(self, window_id):
        return self.color_mapping_manager._reposition_proto_options(window_id)


    def _focus_floating_window(self, window_id):
        return self.image_display._focus_floating_window(window_id)


    # ============================================================================================================================================================
    #  FUNCTIONS IMAGE UTILS
    # ============================================================================================================================================================
    def _mapping_source_spec(self, window_id, target_size=None):
        return self.color_mapping_manager._mapping_source_spec(window_id, target_size)

    def _get_mapping_source_image(self, window_id, target_size=None):
        return self.color_mapping_manager._get_mapping_source_image(window_id, target_size)

    def _peek_mapping_preprocessing(self, window_id, mapping_space, target_size=None):
        return self.color_mapping_manager._peek_mapping_preprocessing(window_id, mapping_space, target_size)


    def _destroy_proto_options(self, window_id):
        return self.color_mapping_manager._destroy_proto_options(window_id)


    @staticmethod
    def _legend_display_name(name, max_chars=22):
        return ColorMappingManager._legend_display_name(name, max_chars)


    def _mapping_category_rows(self, space, expanded, *, include_granules=True):
        return self.color_mapping_manager._mapping_category_rows(space, expanded, include_granules=include_granules)

    def _refresh_single_mapping_rows(self, window_id):
        return self.color_mapping_manager._refresh_single_mapping_rows(window_id)

    def _refresh_mapping_all_legend_rows(self, window_id):
        return self.color_mapping_manager._refresh_mapping_all_legend_rows(window_id)

    def _toggle_mapping_legend_category(self, window_id, category_index):
        return self.color_mapping_manager._toggle_mapping_legend_category(window_id, category_index)

    def _scroll_proto_options(self, window_id, delta):
        return self.color_mapping_manager._scroll_proto_options(window_id, delta)

    def _set_single_mapping_level(self, window_id, level):
        return self.color_mapping_manager._set_single_mapping_level(window_id, level)

    def _set_single_mapping_style(self, window_id, style):
        return self.color_mapping_manager._set_single_mapping_style(window_id, style)

    def _select_mapping_item(self, window_id, selection):
        return self.color_mapping_manager._select_mapping_item(window_id, selection)

    def _select_proto_from_legend(self, window_id, color_name):
        return self.color_mapping_manager._select_proto_from_legend(window_id, color_name)

    def _jump_proto_options_scroll(self, window_id, event, track_top, track_height):
        return self.color_mapping_manager._jump_proto_options_scroll(window_id, event, track_top, track_height)

    def _render_proto_options(self, window_id):
        return self.color_mapping_manager._render_proto_options(window_id)

    def _create_single_mapping_panel(self, window_id):
        return self.color_mapping_manager._create_single_mapping_panel(window_id)

    def _create_mapping_all_panel(self, window_id, palette_uint8):
        return self.color_mapping_manager._create_mapping_all_panel(window_id, palette_uint8)

    def color_mapping(self, window_id):
        return self.color_mapping_manager.color_mapping(window_id)


    def get_proto_percentage(self, window_id):
        return self.color_mapping_manager.get_proto_percentage(window_id)


    def display_color_mapping(self, grayscale_image_array, window_id):
        return self.color_mapping_manager.display_color_mapping(grayscale_image_array, window_id)


    def show_original_image(self, window_id):
        return self.color_mapping_manager.show_original_image(window_id)


    def _display_mapping_all_result(self, window_id, recolored_image, palette_uint8):
        return self.color_mapping_manager._display_mapping_all_result(window_id, recolored_image, palette_uint8)


    def color_mapping_all(self, window_id):
        return self.color_mapping_manager.color_mapping_all(window_id)


    def deploy_at(self):
        if self._has_any_active_job():
            self.custom_warning(
                "Process Running",
                "There is a process currently running. Please wait for it to finish or cancel it before loading a Color Space."
            )
            return
        self.model_3d.get_umbral_points(1.8, mode="AT")

    def deploy_pt(self):
        if self._has_any_active_job():
            self.custom_warning(
                "Process Running", "A processing task is already running."
            )
            return
        self.model_3d.get_umbral_points(0.8, mode="PT")

    def deploy_pt_at(self):
        """Overlay perceptible points and the additional acceptable shell."""
        self.model_3d.get_umbral_points(mode="BOTH")

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
        return self.color_evaluation_window._apply_color_evaluation_result_style(vars_dict, status)


    def _update_color_evaluation_result_card(self, vars_dict, title, detail='', summary='', status='neutral'):
        return self.color_evaluation_window._update_color_evaluation_result_card(vars_dict, title, detail, summary, status)


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
            "config_hint_label", "numeric_row",
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
        if variant == "summary":
            # Three sibling cards rather than an extra title above all controls.
            threshold_panel = tk.Frame(parent, bg=parent.cget("bg"))
        else:
            threshold_panel = tk.Frame(parent, bg="white", bd=1, relief="solid")
            tk.Label(
                threshold_panel, text=title, font=("Sans", 11, "bold"),
                anchor="w", bg="white", padx=12, pady=10
            ).pack(fill="x")
        threshold_panel.pack(fill="x", pady=(2, 0) if variant == "summary" else (6, 0), anchor="n")

        threshold_body = tk.Frame(threshold_panel, bg=threshold_panel.cget("bg"))
        threshold_body.pack(fill="x", padx=0 if variant == "summary" else 12,
                            pady=(0, 0) if variant == "summary" else (0, 10))

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
            # Equal card title heights and identical inner margins align the four
            # dropdowns, while giving the metric description room to breathe.
            selection_w = 350
            config_w = 390
            for col, minimum, weight in ((0, selection_w, 4), (1, 0, 0),
                                         (2, config_w, 4), (3, 0, 0), (4, 220, 1)):
                threshold_body.grid_columnconfigure(col, minsize=minimum, weight=weight,
                    uniform="threshold_controls" if col in (0, 2) else "")

            def summary_card(label, column, right_gap=8):
                card = tk.LabelFrame(
                    threshold_body, text=label, labelanchor="n", bg="white",
                    fg="#1f2937", font=("Segoe UI", 11, "bold"), bd=1,
                    relief="solid", padx=10, pady=8,
                )
                card.grid(row=0, column=column, sticky="nsew", padx=(0, right_gap))
                return card

            section_selection = summary_card("Metric Configuration", 0)
            section_config = summary_card("Threshold Configuration", 2)
            section_output = summary_card("Current Summary", 4, 0)

        # Left: metric selection
        manager = self._get_color_evaluation_manager()

        metric_row = tk.Frame(section_selection, bg="white")
        metric_row.pack(fill="x")
        if variant == "summary":
            family_box = tk.Frame(metric_row, bg="white")
            metric_box = tk.Frame(metric_row, bg="white")
            metric_row.grid_columnconfigure(0, weight=1, uniform="metric")
            metric_row.grid_columnconfigure(1, weight=1, uniform="metric")
            family_box.grid(row=0, column=0, sticky="ew", padx=(0, 6))
            metric_box.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        else:
            family_box = metric_box = metric_row

        tk.Label(
            family_box,
            text="Metric Family",
            font=("Sans", 10, "bold"),
            anchor="w",
            bg="white"
        ).pack(anchor="w", pady=(0, 4))

        metric_family_combo = UtilsTools.styled_combobox(
            family_box,
            textvariable=vars_dict["threshold_metric_family_var"],
            state="readonly",
            width=30 if variant == "result" else 12,
            values=manager.get_metric_families()
        )
        metric_family_combo.pack(anchor="w", fill="x", pady=(0, 8))

        tk.Label(
            metric_box,
            text="Metric",
            font=("Sans", 10, "bold"),
            anchor="w",
            bg="white"
        ).pack(anchor="w", pady=(0, 4))

        metric_combo = UtilsTools.styled_combobox(
            metric_box,
            textvariable=vars_dict["threshold_metric_var"],
            state="readonly",
            width=30 if variant == "result" else 12,
            values=manager.get_metrics_for_family(
                vars_dict["threshold_metric_family_var"].get()
            )
        )
        metric_combo.pack(anchor="w", fill="x", pady=(0, 8))

        metric_help_label = tk.Label(
            section_selection,
            textvariable=vars_dict["threshold_metric_help_var"],
            bg="white",
            fg="#666666",
            anchor="center" if variant == "summary" else "w",
            justify="center" if variant == "summary" else "left",
            wraplength=255 if variant == "result" else 320,
            font=("Sans", 8, "italic")
        )
        metric_help_label.pack(anchor="w", fill="x", pady=(0, 4))

        if variant == "summary":
            # At full width show the entire description on one line.
            # On smaller screens, wrap instead of clipping the information.
            def _resize_metric_help(event=None):
                try:
                    available = max(1, section_selection.winfo_width() - 24)
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
        if variant != "summary":
            tk.Label(
                section_config,
                text="Configuration",
                font=("Sans", 10, "bold"),
                anchor="w",
                bg="white"
            ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))

        if variant == "summary":
            for col, minimum, weight in ((0, 65, 0), (1, 53, 0), (2, 62, 0), (3, 135, 1)):
                section_config.grid_columnconfigure(col, minsize=minimum, weight=weight)
        else:
            section_config.grid_columnconfigure(0, minsize=115, weight=0)
            section_config.grid_columnconfigure(1, minsize=90, weight=1)
            section_config.grid_columnconfigure(2, minsize=115, weight=0)
            section_config.grid_columnconfigure(3, minsize=90, weight=1)

        mode_label = tk.Label(section_config, text="Threshold type" if variant == "summary" else "Threshold type:", bg="white", anchor="w")
        if variant == "summary":
            mode_label.configure(font=("Sans", 10, "bold"))
        mode_combo = UtilsTools.styled_combobox(
            section_config,
            textvariable=vars_dict["threshold_mode_var"],
            state="readonly",
            width=26 if variant == "result" else 8,
            values=["default", "custom"]
        )
        if variant == "summary":
            mode_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 4))
            mode_combo.grid(row=2, column=0, columnspan=2, sticky="ew", padx=(0, 8), pady=(0, 6))
        else:
            mode_label.grid(row=1, column=0, sticky="w", pady=(0, 6), padx=(0, 10))
            mode_combo.grid(row=1, column=1, columnspan=3, sticky="ew", pady=(0, 6))

        preset_label = tk.Label(section_config, text="Default preset" if variant == "summary" else "Default preset:", bg="white", anchor="w")
        if variant == "summary":
            preset_label.configure(font=("Sans", 10, "bold"))
        preset_combo = UtilsTools.styled_combobox(
            section_config,
            textvariable=vars_dict["threshold_preset_var"],
            state="readonly",
            width=26 if variant == "result" else 25,
            values=[
                "Perceptibility Threshold",
                "Acceptability Threshold",
                "Perceptibility + Acceptability"
            ]
        )

        custom_type_label = tk.Label(section_config, text="Custom mode" if variant == "summary" else "Custom mode:", bg="white", anchor="w")
        if variant == "summary":
            custom_type_label.configure(font=("Sans", 10, "bold"))
        custom_type_combo = UtilsTools.styled_combobox(
            section_config,
            textvariable=vars_dict["threshold_custom_type_var"],
            state="readonly",
            width=26 if variant == "result" else 25,
            values=[
                "Single threshold",
                "Lower and upper thresholds"
            ]
        )

        # Keep numeric fields independent of the dropdown grid so that they
        # are centered without changing either dropdown's width.
        numeric_row = tk.Frame(section_config, bg="white") if variant == "summary" else None
        numeric_parent = numeric_row if numeric_row is not None else section_config
        single_label = tk.Label(numeric_parent, text="Threshold" if variant == "summary" else "Threshold:", bg="white", anchor="w")
        single_entry = tk.Entry(numeric_parent, textvariable=vars_dict["threshold_single_var"], width=8 if variant == "summary" else 12)

        lower_label = tk.Label(numeric_parent, text="Lower" if variant == "summary" else "Lower threshold:", bg="white", anchor="w")
        lower_entry = tk.Entry(numeric_parent, textvariable=vars_dict["threshold_lower_var"], width=6 if variant == "summary" else 10)

        upper_label = tk.Label(numeric_parent, text="Upper" if variant == "summary" else "Upper threshold:", bg="white", anchor="w")
        upper_entry = tk.Entry(numeric_parent, textvariable=vars_dict["threshold_upper_var"], width=6 if variant == "summary" else 10)

        config_hint_label = tk.Label(
            section_config,
            textvariable=vars_dict["config_hint_var"],
            bg="white",
            fg="#666666",
            anchor="center" if variant == "summary" else "w",
            justify="center" if variant == "summary" else "left",
            wraplength=360,
            font=("Sans", 9, "italic")
        )

        def _update_config_hint_wrap(event=None):
            try:
                available_width = max(section_config.winfo_width() - 24, 1) if variant == "summary" else max(section_config.winfo_width() - 20, 220)
                if int(config_hint_label.cget("wraplength")) != available_width:
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
            "numeric_row": numeric_row,
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
                textvariable=vars_dict["threshold_summary_title_var"],
                anchor="center",
                justify="center",
                bg="white",
                font=("Sans", 10, "bold"),
                wraplength=320
            ).pack(anchor="center", fill="x", pady=(0, 6))

            tk.Label(
                section_output,
                textvariable=vars_dict["threshold_summary_detail_var"],
                anchor="center",
                justify="center",
                bg="white",
                wraplength=320
            ).pack(anchor="center", fill="x", pady=(0, 6))

            tk.Label(
                section_output,
                textvariable=vars_dict["threshold_summary_extra_var"],
                anchor="center",
                justify="center",
                bg="white",
                wraplength=320
            ).pack(anchor="center", fill="x")

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
            if refs.get("variant") == "summary":
                refs["preset_label"].grid(row=1, column=2, columnspan=2, sticky="w", padx=(8, 0), pady=(0, 4))
                refs["preset_combo"].grid(row=2, column=2, columnspan=2, sticky="ew", padx=(8, 0), pady=(0, 6))
            else:
                refs["preset_label"].grid(row=2, column=0, sticky="w", pady=(0, 6), padx=(0, 10))
                refs["preset_combo"].grid(row=2, column=1, columnspan=3, sticky="ew", pady=(0, 6))

            vars_dict["config_hint_var"].set(
                "Use predefined perceptibility and/or acceptability thresholds."
            )
            refs["config_hint_label"].grid(row=3, column=0, columnspan=4, sticky="ew", pady=(2, 0))

        elif mode_value == "custom":
            if refs.get("variant") == "summary":
                refs["custom_type_label"].grid(row=1, column=2, columnspan=2, sticky="w", padx=(8, 0), pady=(0, 4))
                refs["custom_type_combo"].grid(row=2, column=2, columnspan=2, sticky="ew", padx=(8, 0), pady=(0, 6))
            else:
                refs["custom_type_label"].grid(row=2, column=0, sticky="w", pady=(0, 6), padx=(0, 10))
                refs["custom_type_combo"].grid(row=2, column=1, columnspan=3, sticky="ew", pady=(0, 6))

            if custom_type == "single":
                if refs.get("variant") == "summary":
                    refs["numeric_row"].grid(row=3, column=0, columnspan=4, pady=(0, 6))
                    refs["single_label"].grid(row=0, column=0, padx=(0, 8))
                    refs["single_entry"].grid(row=0, column=1)
                else:
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
                if refs.get("variant") == "summary":
                    refs["numeric_row"].grid(row=3, column=0, columnspan=4, pady=(0, 6))
                    refs["lower_label"].grid(row=0, column=0, padx=(0, 8))
                    refs["lower_entry"].grid(row=0, column=1, padx=(0, 18))
                    refs["upper_label"].grid(row=0, column=2, padx=(0, 8))
                    refs["upper_entry"].grid(row=0, column=3)
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
        return self.image_display._enable_original_rectangle_sampling(window_id, target_w, target_h)


    def _disable_original_rectangle_sampling(self, window_id):
        return self.image_display._disable_original_rectangle_sampling(window_id)


    def _clip_original_canvas_point_to_image(self, x, y, window_id):
        return self.image_display._clip_original_canvas_point_to_image(x, y, window_id)

    def _on_original_mouse_down(self, event, window_id):
        return self.image_display._on_original_mouse_down(event, window_id)


    def _on_original_mouse_drag(self, event, window_id):
        return self.image_display._on_original_mouse_drag(event, window_id)


    def _on_original_mouse_up(self, event, window_id):
        return self.image_display._on_original_mouse_up(event, window_id)


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

            canvas_width = max(1, self.model_3d.Canvas1.winfo_width())
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


    def display_pixel_value(self, x_original, y_original, pixel_lab, is_average=False, selection_info=None, image_id=None, native_rgb=None):
        """Display pixel/ROI LAB and the best category, using the active T-conorm.

        This status bar has a bounded width. Full coordinates, LAB precision and
        category memberships remain available in Image Inspection.
        """
        if not hasattr(self, "lab_value_frame") or not self.lab_value_frame.winfo_exists():
            bg, muted, text = "#ffffff", "#6b7280", "#1f2937"
            self.lab_value_frame = tk.Frame(
                self.model_3d.Canvas1, bg=bg, bd=0, relief="flat",
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
                self.model_3d.Canvas1.bind(
                    "<Configure>", lambda _e: self._fit_pixel_info_bar(), add="+")
                self._pixel_info_resize_bound = True

        pixel_lab = tuple(float(v) for v in pixel_lab)
        space = self.fuzzy_color_space
        native_rgb = tuple(native_rgb) if native_rgb is not None and not is_average else None
        use_rgb = native_rgb is not None and space.color_space == "RGB"
        value, mode = (native_rgb, "RGB") if use_rgb else (pixel_lab, "LAB")
        membership_degrees, winner, winner_mu = mapping_membership_summary(space, value, mode)
        top_memberships = sorted(membership_degrees.items(),
                                 key=lambda pair: (-float(pair[1]), pair[0] != winner))

        # Keep the FULL sample for Image Inspection, never the shortened UI text.
        self._last_pixel_info = {
            "x": x_original,
            "y": y_original,
            "lab": pixel_lab,
            "native_rgb": native_rgb,
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
            native_rgb=info.get("native_rgb"),
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
        return self.color_evaluation_window.color_evaluation()


    def _get_active_dialog_parent(self, fallback=None):
        """
        Return the best parent window for dialogs so they appear above the
        currently active tool window instead of the main root.
        """
        try:
            grabbed = self.root.grab_current()
        except tk.TclError:
            grabbed = None
        candidates = [
            fallback, grabbed,
            getattr(self, "_image_based_creation_window", None),
            getattr(self, "_palette_based_creation_window", None),
            getattr(self, "_image_inspection_window", None),
            getattr(self, "_color_evaluation_window", None),
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
        return self.color_evaluation_window._on_close_color_evaluation_window()


    def _set_color_evaluation_initial_sash(self):
        return self.color_evaluation_window._set_color_evaluation_initial_sash()


    def _build_color_evaluation_window(self, win):
        return self.color_evaluation_window._build_color_evaluation_window(win)


    def _set_color_evaluation_inspector_layout(self, vars_dict):
        return self.color_evaluation_window._set_color_evaluation_inspector_layout(vars_dict)


    def _get_evaluation_proto_hex(self, vars_dict, label):
        return self.color_evaluation_window._get_evaluation_proto_hex(vars_dict, label)


    def _evaluation_membership_snapshot(self, vars_dict, sample_lab, sample=None):
        return self.color_evaluation_window._evaluation_membership_snapshot(vars_dict, sample_lab, sample)

    def _sync_color_evaluation_operator(self):
        return self.color_evaluation_window._sync_color_evaluation_operator()

    def _change_color_evaluation_operator(self, v):
        return self.color_evaluation_window._change_color_evaluation_operator(v)

    def _update_color_evaluation_membership_panel(self, vars_dict, sample_lab=None, sample=None):
        return self.color_evaluation_window._update_color_evaluation_membership_panel(vars_dict, sample_lab, sample)

    def _explore_color_evaluation_level(self, v):
        return self.color_evaluation_window._explore_color_evaluation_level(v)

    _evaluation_tree_guides = staticmethod(ColorEvaluationWindow._evaluation_tree_guides)

    def _render_evaluation_membership_tree(self, v):
        return self.color_evaluation_window._render_evaluation_membership_tree(v)

    _pack_evaluation_rows = staticmethod(ColorEvaluationWindow._pack_evaluation_rows)

    def _use_evaluation_highest_degree(self, v):
        return self.color_evaluation_window._use_evaluation_highest_degree(v)

    def _use_evaluation_reference(self, v, kind, name):
        return self.color_evaluation_window._use_evaluation_reference(v, kind, name)


    def _load_color_space_for_evaluation_from_file(self, filename):
        return self.color_evaluation_window._load_color_space_for_evaluation_from_file(filename)
    

    def _get_current_color_space_for_evaluation(self):
        return self.color_evaluation_window._get_current_color_space_for_evaluation()


    def _create_color_evaluation_vars(self):
        return self.color_evaluation_window._create_color_evaluation_vars()
    

    def _set_color_evaluation_active_action(self, vars_dict, action_key):
        return self.color_evaluation_window._set_color_evaluation_active_action(vars_dict, action_key)


    def _refresh_color_evaluation_threshold_ui(self, vars_dict, refs):
        return self.color_evaluation_window._refresh_color_evaluation_threshold_ui(vars_dict, refs)


    def _get_color_evaluation_threshold_description(self):
        return self.color_evaluation_window._get_color_evaluation_threshold_description()


    def _load_current_color_space_for_evaluation(self, vars_dict):
        return self.color_evaluation_window._load_current_color_space_for_evaluation(vars_dict)


    def _load_external_color_space_for_evaluation(self, vars_dict):
        return self.color_evaluation_window._load_external_color_space_for_evaluation(vars_dict)


    def _calculate_evaluation_memberships(self, vars_dict, sample_lab, sample=None):
        return self.color_evaluation_window._calculate_evaluation_memberships(vars_dict, sample_lab, sample)


    def _update_color_evaluation_space_summary(self, vars_dict):
        return self.color_evaluation_window._update_color_evaluation_space_summary(vars_dict)


    def _extract_color_space_rows(self, data_source):
        return self.color_evaluation_window._extract_color_space_rows(data_source)


    def _set_custom_color_as_evaluation_comparison(self, vars_dict, sample_lab, sample_rgb, sample_hex, name='Custom Color', source='custom'):
        return self.color_evaluation_window._set_custom_color_as_evaluation_comparison(vars_dict, sample_lab, sample_rgb, sample_hex, name, source)

    def _refresh_color_evaluation_table_display_mode(self, vars_dict):
        return self.color_evaluation_window._refresh_color_evaluation_table_display_mode(vars_dict)


    def _refresh_color_evaluation_preview_values(self, vars_dict):
        return self.color_evaluation_window._refresh_color_evaluation_preview_values(vars_dict)


    def _rotate_color_evaluation_table_display_mode(self, vars_dict, direction=1):
        return self.color_evaluation_window._rotate_color_evaluation_table_display_mode(vars_dict, direction)


    _color_evaluation_actual_entries = staticmethod(ColorEvaluationWindow._color_evaluation_actual_entries)

    _color_evaluation_lab_caption = staticmethod(ColorEvaluationWindow._color_evaluation_lab_caption)

    _format_color_evaluation_value = staticmethod(ColorEvaluationWindow._format_color_evaluation_value)

    def _highlight_color_evaluation_rows(self, vars_dict):
        return self.color_evaluation_window._highlight_color_evaluation_rows(vars_dict)

    def _render_color_evaluation_cards(self, vars_dict, data_source):
        return self.color_evaluation_window._render_color_evaluation_cards(vars_dict, data_source)

    def _filter_color_evaluation_entries(self, vars_dict):
        return self.color_evaluation_window._filter_color_evaluation_entries(vars_dict)


    _evaluation_sample_snapshot = staticmethod(ColorEvaluationWindow._evaluation_sample_snapshot)

    def _add_color_evaluation_quick_sample(self, vars_dict, name, lab, rgb, hex_color, source='custom', category=None, row_label=None):
        return self.color_evaluation_window._add_color_evaluation_quick_sample(vars_dict, name, lab, rgb, hex_color, source, category, row_label)

    def _render_color_evaluation_quick_samples(self, vars_dict):
        return self.color_evaluation_window._render_color_evaluation_quick_samples(vars_dict)

    def _toggle_color_evaluation_quick_samples(self, vars_dict):
        return self.color_evaluation_window._toggle_color_evaluation_quick_samples(vars_dict)

    def _pin_color_evaluation_sample(self, vars_dict, sample_id):
        return self.color_evaluation_window._pin_color_evaluation_sample(vars_dict, sample_id)

    def _clear_color_evaluation_recent_samples(self, vars_dict):
        return self.color_evaluation_window._clear_color_evaluation_recent_samples(vars_dict)

    def _get_color_evaluation_side_sample(self, vars_dict, side):
        return self.color_evaluation_window._get_color_evaluation_side_sample(vars_dict, side)

    def _set_color_evaluation_side_sample(self, vars_dict, side, sample):
        return self.color_evaluation_window._set_color_evaluation_side_sample(vars_dict, side, sample)

    def _select_color_evaluation_quick_sample(self, vars_dict, sample_id):
        return self.color_evaluation_window._select_color_evaluation_quick_sample(vars_dict, sample_id)

    def _use_color_evaluation_external_sample(self, vars_dict, *, name, lab, rgb, hex_color, source='custom', target='B'):
        return self.color_evaluation_window._use_color_evaluation_external_sample(vars_dict, name=name, lab=lab, rgb=rgb, hex_color=hex_color, source=source, target=target)

    def _get_color_evaluation_manager(self):
        """
        Return the shared ColorEvaluationManager instance.
        """
        manager = getattr(self, "color_manager", None)
        if manager is None:
            manager = getattr(self, "color_evaluation_manager", None)
        if manager is None:
            manager = getattr(self, "color_eval_manager", None)

        if manager is None:
            manager = ColorEvaluationManager()
            self.color_evaluation_manager = manager

        return manager


    def _get_color_evaluation_target_display_name(self, side):
        return self.color_evaluation_window._get_color_evaluation_target_display_name(side)


    def _clear_color_evaluation_analysis(self, vars_dict):
        return self.color_evaluation_window._clear_color_evaluation_analysis(vars_dict)


    def _swap_color_evaluation_rows(self, vars_dict):
        return self.color_evaluation_window._swap_color_evaluation_rows(vars_dict)

    def _enable_color_evaluation_comparison_mode(self, vars_dict):
        return self.color_evaluation_window._enable_color_evaluation_comparison_mode(vars_dict)


    def _clear_color_evaluation_comparison(self, vars_dict, clear_custom=True):
        return self.color_evaluation_window._clear_color_evaluation_comparison(vars_dict, clear_custom)


    def _refresh_color_evaluation_comparison(self, vars_dict):
        return self.color_evaluation_window._refresh_color_evaluation_comparison(vars_dict)

    def _open_color_evaluation_image_sampler(self, vars_dict):
        return self.color_evaluation_window._open_color_evaluation_image_sampler(vars_dict)


    def _get_custom_color_input_mode_help(self, mode):
        return self.color_evaluation_window._get_custom_color_input_mode_help(mode)


    def _open_custom_color_input_dialog(self, vars_dict):
        return self.color_evaluation_window._open_custom_color_input_dialog(vars_dict)


    def _open_custom_color_dialog(self, parent=None, title='Custom Color', subtitle='', submit_text='OK', require_name=False, default_name='Custom Color', on_submit=None, initial_lab=None, allow_evaluation_target=False, initial_evaluation_target='B'):
        return self.color_evaluation_window._open_custom_color_dialog(parent, title, subtitle, submit_text, require_name, default_name, on_submit, initial_lab, allow_evaluation_target, initial_evaluation_target)


    def _submit_custom_color_input(self, vars_dict, input_vars, dialog):
        return self.color_evaluation_window._submit_custom_color_input(vars_dict, input_vars, dialog)


    def _fill_custom_color_dialog_from_rgb(self, input_vars, rgb):
        return self.color_evaluation_window._fill_custom_color_dialog_from_rgb(input_vars, rgb)


    def _open_square_color_picker(self, parent, initial_rgb=(217, 217, 217), on_apply=None, *, initial_lab=None, granule_name=None, on_granule_submit=None, submit_text=None, title=None, initial_mode=None):
        return self.color_evaluation_window._open_square_color_picker(parent, initial_rgb, on_apply, initial_lab=initial_lab, granule_name=granule_name, on_granule_submit=on_granule_submit, submit_text=submit_text, title=title, initial_mode=initial_mode)


    def _update_color_evaluation_conversion_inspector(self, vars_dict, lab=None, rgb=None, hex_color=None, name='Color', source='-'):
        return self.color_evaluation_window._update_color_evaluation_conversion_inspector(vars_dict, lab, rgb, hex_color, name, source)


    def _get_active_color_evaluation_sample(self, vars_dict):
        return self.color_evaluation_window._get_active_color_evaluation_sample(vars_dict)
    

    def _classify_for_active_thresholds(self, metric_value):
        return self.color_evaluation_window._classify_for_active_thresholds(metric_value)


    def _show_color_evaluation_closest_prototypes(self, vars_dict):
        return self.color_evaluation_window._show_color_evaluation_closest_prototypes(vars_dict)


    def _normalize_custom_color_input(self, input_mode, value_1='', value_2='', value_3='', hex_value=''):
        return self.color_evaluation_window._normalize_custom_color_input(input_mode, value_1, value_2, value_3, hex_value)


    def _get_color_evaluation_volume_limits(self, vars_dict):
        return self.color_evaluation_window._get_color_evaluation_volume_limits(vars_dict)
    

    def _get_color_evaluation_plot_context(self, vars_dict, require_custom=False, require_closest=False):
        return self.color_evaluation_window._get_color_evaluation_plot_context(vars_dict, require_custom, require_closest)


    def _open_color_evaluation_3d_plot(self, vars_dict):
        return self.color_evaluation_window._open_color_evaluation_3d_plot(vars_dict)


    def _open_color_evaluation_ab_plot(self, vars_dict):
        return self.color_evaluation_window._open_color_evaluation_ab_plot(vars_dict)


    def _open_color_evaluation_lc_plot(self, vars_dict):
        return self.color_evaluation_window._open_color_evaluation_lc_plot(vars_dict)


    def _open_color_evaluation_lch_plot(self, vars_dict):
        return self.color_evaluation_window._open_color_evaluation_lch_plot(vars_dict)


    def _open_color_evaluation_top7_plot(self, vars_dict):
        return self.color_evaluation_window._open_color_evaluation_top7_plot(vars_dict)


    def _open_color_evaluation_membership_plot(self, vars_dict):
        return self.color_evaluation_window._open_color_evaluation_membership_plot(vars_dict)

    def _open_color_evaluation_component_plot(self, vars_dict):
        return self.color_evaluation_window._open_color_evaluation_component_plot(vars_dict)

    def _calculate_color_evaluation_component_differences(self, lab_1, lab_2):
        return self.color_evaluation_window._calculate_color_evaluation_component_differences(lab_1, lab_2)


    def _show_color_eval_plotly_figure_in_browser(self, fig, filename_prefix='color_eval_plot', color_tree=None):
        return self.color_evaluation_window._show_color_eval_plotly_figure_in_browser(fig, filename_prefix, color_tree)


    def _get_color_evaluation_available_graph_keys(self, vars_dict):
        return self.color_evaluation_window._get_color_evaluation_available_graph_keys(vars_dict)


    def _create_color_evaluation_graph_buttons_card(self, parent, vars_dict):
        return self.color_evaluation_window._create_color_evaluation_graph_buttons_card(parent, vars_dict)


    def _update_color_evaluation_graph_buttons(self, vars_dict):
        return self.color_evaluation_window._update_color_evaluation_graph_buttons(vars_dict)







def start_up():
    root = tk.Tk()
    app = PyFCSApp(root)
    root.mainloop()

if __name__ == '__main__':
    start_up()

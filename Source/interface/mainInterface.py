import os
import sys

# --- bootstrap paths (before ANY non-stdlib / project imports) ---
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
from skimage import color
from matplotlib.figure import Figure
from PIL import Image, ImageTk, ImageDraw, ImageFont, ImageEnhance
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from tkinter import ttk, Menu, filedialog, messagebox, Scrollbar, DISABLED, NORMAL

# --- project imports ---
from Source.input_output.Input import Input
from Source.interface.modules.VisualManager import VisualManager
from Source.colorspace.ReferenceDomain import ReferenceDomain
from Source.fuzzy.FuzzyColorSpace import FuzzyColorSpace
from Source.interface.modules.ImageManager import ImageManager
from Source.interface.modules.FuzzyColorSpaceManager import FuzzyColorSpaceManager
from Source.interface.modules.ColorEvaluationManager import ColorEvaluationManager

import Source.interface.modules.UtilsTools as UtilsTools




class PyFCSApp:
    def __init__(self, root):
        # ---------------------------------------------------------------------
        # Core references / managers
        # ---------------------------------------------------------------------
        self.root = root

        logo_path = os.path.join(BASE_PATH, "Source", "external", "icons", "logo.png")
        self.logo = tk.PhotoImage(file=logo_path)
        self.root.iconphoto(True, self.logo)

        self.image_manager = ImageManager(
            root=self.root,
            custom_warning=self.custom_warning if hasattr(self, "custom_warning") else None,
            center_popup=self.center_popup if hasattr(self, "center_popup") else None,
        )
        self.fuzzy_manager = FuzzyColorSpaceManager(root=self.root)
        self.color_manager = ColorEvaluationManager(output_dir="test_results/Color_Evaluation")
        self.volume_limits = ReferenceDomain(0, 100, -128, 127, -128, 127)

        # ---------------------------------------------------------------------
        # Shared runtime state
        # ---------------------------------------------------------------------
        self.COLOR_SPACE = False
        self.FIRST_DBSCAN = True
        self.SHOW_ORIGINAL = {}
        self.CAN_APPLY_MAPPING = {}
        self.hex_color = []
        self.images = {}
        self.color_entry_detect = {}
        self.display_pil = {}
        self.image_jobs = {}

        # Additional runtime state
        self.rgb_data = []
        self.graph_widget = None

        # Centralized image/icon references to avoid garbage collection
        self.ui_icons = {}

        # Temporary external Plotly output
        self.TEMP_PLOT_DIR = os.path.join("external", "temp", "plots")
        self.TEMP_PLOT_MAX_FILES = 30
        self.TEMP_PLOT_CLEANUP_EVERY = 5
        self._temp_plot_creation_count = 0

        # ---------------------------------------------------------------------
        # Visual constants
        # ---------------------------------------------------------------------
        APP_BG = "#f5f6f8"
        CARD_BG = "#ffffff"
        PANEL_BG = "#fbfbfc"
        SOFT_BG = "#f1f3f6"
        BORDER = "#d9dde3"
        TEXT = "#1f2937"
        MUTED = "#6b7280"
        BLUE = "#1f4e8c"
        BLUE_BG = "#e8f0fe"
        BLUE_BG_ACTIVE = "#d7e5fb"
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

        # ---------------------------------------------------------------------
        # Main window configuration
        # ---------------------------------------------------------------------
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

        # ---------------------------------------------------------------------
        # ttk style
        # ---------------------------------------------------------------------
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

        # ---------------------------------------------------------------------
        # Local UI helpers
        # ---------------------------------------------------------------------
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
                activebackground="#e8f0fe",
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

        def create_action_button(parent, text, command, bg, fg, active_bg, side="left", padx=(0, 10)):
            """
            Create a styled action button for the Data tab footer.
            """
            btn = tk.Button(
                parent,
                text=text,
                command=command,
                font=FONT_BOLD,
                bg=bg,
                fg=fg,
                activebackground=active_bg,
                activeforeground=fg,
                relief="solid",
                bd=1,
                padx=14,
                pady=7,
                cursor="hand2",
                highlightthickness=0
            )
            btn.pack(side=side, padx=padx)
            return btn

        def bind_vertical_mousewheel(canvas):
            """
            Enable mouse wheel scrolling only while the pointer is inside the target canvas.
            Compatible with Windows, macOS and Linux.
            """
            system_name = platform.system()

            def on_mousewheel(event):
                if system_name == "Darwin":
                    step = -1 if event.delta > 0 else 1
                else:
                    step = int(-1 * (event.delta / 120))
                    if step == 0:
                        step = -1 if event.delta > 0 else 1

                canvas.yview_scroll(step, "units")
                return "break"

            def on_mousewheel_linux_up(event):
                canvas.yview_scroll(-1, "units")
                return "break"

            def on_mousewheel_linux_down(event):
                canvas.yview_scroll(1, "units")
                return "break"

            def bind_events(_event):
                if system_name in ("Windows", "Darwin"):
                    canvas.bind_all("<MouseWheel>", on_mousewheel)
                else:
                    canvas.bind_all("<Button-4>", on_mousewheel_linux_up)
                    canvas.bind_all("<Button-5>", on_mousewheel_linux_down)

            def unbind_events(_event):
                if system_name in ("Windows", "Darwin"):
                    canvas.unbind_all("<MouseWheel>")
                else:
                    canvas.unbind_all("<Button-4>")
                    canvas.unbind_all("<Button-5>")

            canvas.bind("<Enter>", bind_events)
            canvas.bind("<Leave>", unbind_events)

        # ---------------------------------------------------------------------
        # Menu bar
        # ---------------------------------------------------------------------
        self.menubar = Menu(self.root)
        self.root.config(menu=self.menubar)

        file_menu = Menu(self.menubar, tearoff=0)
        file_menu.add_command(label="Exit", command=self.exit_app)
        self.menubar.add_cascade(label="File", menu=file_menu)

        img_menu = Menu(self.menubar, tearoff=0)
        img_menu.add_command(label="Open Image", command=self.open_image)
        img_menu.add_command(label="Save Image", command=self.save_image)
        img_menu.add_command(label="Close All", command=self.close_all_image)
        self.menubar.add_cascade(label="Image Manager", menu=img_menu)

        fuzzy_menu = Menu(self.menubar, tearoff=0)
        fuzzy_menu.add_command(label="New Color Space", command=self.show_menu_create_fcs)
        fuzzy_menu.add_command(label="Load Color Space", command=self.load_color_space)
        self.menubar.add_cascade(label="Fuzzy Color Space Manager", menu=fuzzy_menu)

        self.menubar.add_command(
            label="Color Evaluation",
            command=self.color_evaluation
        )

        help_menu = Menu(self.menubar, tearoff=0)
        help_menu.add_command(label="About", command=self.about_info)
        self.menubar.add_cascade(label="Help", menu=help_menu)

        # Submenu used by the "New Color Space" button
        self.menu_create_fcs = Menu(self.root, tearoff=0)
        self.menu_create_fcs.add_command(
            label="Palette-Based Creation",
            command=self.palette_based_creation
        )
        self.menu_create_fcs.add_command(
            label="Image-Based Creation",
            command=self.image_based_creation
        )

        # ---------------------------------------------------------------------
        # Toolbar area
        # ---------------------------------------------------------------------
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

        # Load icons once
        icon_size = (30, 30)
        load_image_icon = self.load_toolbar_icon("LoadImage.png", icon_size)
        save_image_icon = self.load_toolbar_icon("SaveImage.png", icon_size)
        new_fcs_icon = self.load_toolbar_icon("NewFCS1.png", icon_size)
        load_fcs_icon = self.load_toolbar_icon("LoadFCS.png", icon_size)
        at_icon = self.load_toolbar_icon("AT.png", icon_size)
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

        add_toolbar_separator(toolbar_inner)

        fuzzy_manager_frame = create_card(
            toolbar_inner,
            title="Fuzzy Color Space Manager",
            padx=6,
            pady=5
        )
        fuzzy_manager_frame.pack(side="left", fill="y", expand=False, padx=(0, 10))

        create_toolbar_button(
            fuzzy_manager_frame,
            text="New Color Space",
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

        create_toolbar_button(
            color_evaluation_frame,
            text="Display PT",
            image=pt_icon,
            command=self.deploy_pt
        )
        create_toolbar_button(
            color_evaluation_frame,
            text="Display AT",
            image=at_icon,
            command=self.deploy_at
        )
        create_toolbar_button(
            color_evaluation_frame,
            text="Color Evaluation",
            image=evaluate_icon,
            command=self.color_evaluation
        )

        # ---------------------------------------------------------------------
        # Main working area
        # ---------------------------------------------------------------------
        main_content_frame = tk.Frame(self.root, bg=APP_BG)
        main_content_frame.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        main_paned = ttk.Panedwindow(
            main_content_frame,
            orient="horizontal",
            style="PyFCS.TPanedwindow"
        )
        main_paned.pack(fill="both", expand=True)

        # Left pane: Image Display
        image_area_frame = create_card(
            main_paned,
            title="Image Display",
            padx=10,
            pady=10
        )

        self.image_canvas = tk.Canvas(
            image_area_frame,
            bg=PANEL_BG,
            borderwidth=1,
            relief="solid",
            highlightthickness=0
        )
        self.image_canvas.pack(fill="both", expand=True)

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
            """
            Set the initial split with a balanced layout.
            """
            total_width = main_paned.winfo_width()
            if total_width > 1:
                main_paned.sashpos(0, int(total_width * 0.42))

        self.root.after(140, set_initial_main_sash)

        # ---------------------------------------------------------------------
        # Tab: Model 3D
        # ---------------------------------------------------------------------
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
        paned.add(self.Canvas1, stretch="always", minsize=520)

        # Color button panel
        self.colors_frame = tk.Frame(
            paned,
            bg=CARD_BG,
            width=155,
            bd=1,
            relief="solid",
            highlightthickness=0
        )
        paned.add(self.colors_frame, minsize=145)

        colors_header = tk.Frame(self.colors_frame, bg=CARD_BG)
        colors_header.pack(fill="x", padx=8, pady=(8, 4))

        tk.Label(
            colors_header,
            text="Colors",
            font=FONT_SMALL_BOLD,
            bg=CARD_BG,
            fg=TEXT,
            anchor="w"
        ).pack(side="left")

        self.scrollable_canvas = tk.Canvas(
            self.colors_frame,
            bg=CARD_BG,
            highlightthickness=0,
            borderwidth=0,
            width=145
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
                    width=max(event.width - 4, 120)
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

        # ---------------------------------------------------------------------
        # Tab: Data
        # ---------------------------------------------------------------------
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

        # ---------------------------------------------------------------------
        # Header: title + file name
        # ---------------------------------------------------------------------
        data_header = tk.Frame(data_panel, bg=SOFT_BG, height=66)
        data_header.pack(fill="x")
        data_header.pack_propagate(False)

        header_left = tk.Frame(data_header, bg=SOFT_BG)
        header_left.pack(side="left", fill="y", padx=16)

        self.data_header_title = tk.Label(
            header_left,
            text="Color Space Data (0)",
            font=("Segoe UI", 13, "bold"),
            bg=SOFT_BG,
            fg=TEXT,
            anchor="w"
        )
        self.data_header_title.pack(anchor="w", pady=(10, 0))

        tk.Label(
            header_left,
            text="Edit prototypes, add colors, apply or delete the current color space",
            font=FONT_SMALL,
            bg=SOFT_BG,
            fg=MUTED,
            anchor="w"
        ).pack(anchor="w", pady=(2, 0))

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

        # ---------------------------------------------------------------------
        # Canvas area directly inside the main panel
        # ---------------------------------------------------------------------
        canvas_area = tk.Frame(data_panel, bg=CARD_BG)
        canvas_area.pack(fill="both", expand=True, padx=16, pady=(16, 8))

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

        self.data_scrollbar_h = tk.Scrollbar(
            canvas_area,
            orient="horizontal",
            command=self.data_window.xview
        )
        self.data_scrollbar_h.grid(row=1, column=0, sticky="ew", pady=(4, 0))

        self.data_window.configure(
            yscrollcommand=self.data_scrollbar_v.set,
            xscrollcommand=self.data_scrollbar_h.set
        )

        # ------------------- SCROLL FIX (cross-platform) -------------------
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
        # ------------------------------------------------------------------

        self.inner_frame_data = tk.Frame(self.data_window, bg=CARD_BG)
        self.data_window.create_window((0, 0), window=self.inner_frame_data, anchor="nw")

        self.inner_frame_data.bind(
            "<Configure>",
            lambda _e: self.data_window.configure(
                scrollregion=self.data_window.bbox("all")
            )
        )

        # ------------------- SCROLL FIX (inside content) -------------------
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
        # ------------------------------------------------------------------

        # ---------------------------------------------------------------------
        # Footer buttons
        # ---------------------------------------------------------------------
        bottom_bar = tk.Frame(data_panel, bg=CARD_BG)
        bottom_bar.pack(fill="x", padx=16, pady=(0, 14))

        left_actions = tk.Frame(bottom_bar, bg=CARD_BG)
        left_actions.pack(side="left")

        right_actions = tk.Frame(bottom_bar, bg=CARD_BG)
        right_actions.pack(side="right")

        add_button = create_action_button(
            left_actions,
            text="+ Add New Color",
            command=self.addColor_data_window,
            bg=GREEN_BG,
            fg=GREEN,
            active_bg=GREEN_BG_ACTIVE,
            side="left",
            padx=(0, 10)
        )

        apply_button = create_action_button(
            left_actions,
            text="Apply Changes",
            command=self.apply_changes,
            bg=BLUE_BG,
            fg=BLUE,
            active_bg=BLUE_BG_ACTIVE,
            side="left",
            padx=(0, 10)
        )

        delete_button = create_action_button(
            right_actions,
            text="Delete Color Space",
            command=self.delete_color_space,
            bg=RED_BG,
            fg=RED,
            active_bg=RED_BG_ACTIVE,
            side="right",
            padx=(0, 0)
        )

        # ---------------------------------------------------------------------
        # Internal status variable
        # ---------------------------------------------------------------------
        self.status_var = tk.StringVar(value="Ready")






    ########################################################################################### Utils APP ###########################################################################################
    def exit_app(self):
        """
        Prompt the user to confirm exiting the application.
        If the user confirms, close the application.
        """
        confirm_exit = messagebox.askyesno("Exit", "Are you sure you want to exit?")
        if confirm_exit:
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
        """
        Toggle between fullscreen and windowed mode.
        If the current state is fullscreen, switch to windowed mode, and vice versa.
        """
        try:
            current_state = self.root.attributes("-fullscreen")
            self.root.attributes("-fullscreen", not current_state)
        except tk.TclError:
            # Fallback: resize manually if fullscreen fails
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            self.root.geometry(f"{screen_width}x{screen_height}+0+0")



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
            # Move to the previous tab (wrap around to the last tab if needed)
            new_index = (current_index - 1) % total_tabs

        # Select the new tab
        notebook.select(new_index)



    def _ensure_creation_state(self):
        """Lazy init for color-space creation workflow state."""
        if not hasattr(self, "_creation_in_progress"):
            self._creation_in_progress = False

        if not hasattr(self, "_creation_windows"):
            self._creation_windows = []



    def load_toolbar_icon(self, filename, size=None):
        if not hasattr(self, "ui_icons"):
            self.ui_icons = {}

        key = (filename, size)

        if key in self.ui_icons:
            return self.ui_icons[key]

        icon_path = os.path.join(BASE_PATH, "Source", "external", "icons", filename)
        img = Image.open(icon_path)

        if size is not None:
            img = img.resize(size, Image.Resampling.LANCZOS)

        tk_img = ImageTk.PhotoImage(img)
        self.ui_icons[key] = tk_img
        return tk_img



    def custom_warning(self, title="Warning", message="Warning", parent=None):
        """
        Creates a custom warning message window with improved visual style.
        Uses self.center_popup for positioning.
        """

        parent_win = self._get_active_dialog_parent(parent)

        warning_win = tk.Toplevel(parent_win)
        warning_win.title(title)
        warning_win.configure(bg="#eeeeee")
        warning_win.resizable(False, False)

        WIN_W = 400
        WIN_H = 120

        message_text = str(message)
        if len(message_text) > 120:
            WIN_H = 145
        if len(message_text) > 220:
            WIN_H = 175

        # ------------------------------------------------------------
        # Main panel
        # ------------------------------------------------------------
        outer = tk.Frame(warning_win, bg="#eeeeee")
        outer.pack(fill="both", expand=True, padx=10, pady=10)

        panel = tk.Frame(
            outer,
            bg="white",
            bd=1,
            relief="solid"
        )
        panel.pack(fill="both", expand=True)

        # ------------------------------------------------------------
        # Content row
        # ------------------------------------------------------------
        body = tk.Frame(panel, bg="white")
        body.pack(fill="both", expand=True, padx=14, pady=(12, 8))

        # Warning icon from Source/external/icons
        try:
            warning_icon = self.load_toolbar_icon("warning.png", size=(45, 40))

            icon_label = tk.Label(
                body,
                image=warning_icon,
                bg="white",
                bd=0
            )
            icon_label.image = warning_icon
            icon_label.pack(side="left", anchor="n", padx=(0, 12), pady=(0, 0))

        except Exception:
            icon_label = tk.Label(
                body,
                text="!",
                font=("Segoe UI", 18, "bold"),
                fg="#9a6500",
                bg="#fff4d6",
                width=2,
                height=1,
                relief="solid",
                bd=1,
                anchor="center"
            )
            icon_label.pack(side="left", anchor="n", padx=(0, 12), pady=(0, 0))

        tk.Label(
            body,
            text=message_text,
            font=("Sans", 10),
            fg="#333333",
            bg="white",
            justify="left",
            anchor="w",
            wraplength=290
        ).pack(side="left", fill="both", expand=True)

        # ------------------------------------------------------------
        # Button row
        # ------------------------------------------------------------
        footer = tk.Frame(panel, bg="white")
        footer.pack(fill="x", padx=14, pady=(0, 10))

        btn_ok = tk.Button(
            footer,
            text="OK",
            font=("Helvetica", 9, "bold"),
            bg="#E8F0FE",
            fg="#1f4e8c",
            activebackground="#D7E5FB",
            activeforeground="#1f4e8c",
            relief="solid",
            bd=1,
            padx=18,
            pady=4,
            cursor="hand2",
            command=warning_win.destroy
        )
        btn_ok.pack(side="right")

        warning_win.bind("<Return>", lambda event: warning_win.destroy())
        warning_win.bind("<Escape>", lambda event: warning_win.destroy())

        btn_ok.focus_set()

        # ------------------------------------------------------------
        # Important: center after layout is already calculated
        # ------------------------------------------------------------
        warning_win.update_idletasks()
        self.center_popup(warning_win, WIN_W, WIN_H)

        # Keep this after centering, like your original function
        warning_win.transient(parent_win)
        warning_win.grab_set()

        try:
            warning_win.lift(parent_win)
        except Exception:
            warning_win.lift()

        warning_win.wait_window()


    
    def show_loading_color_space(self):
        """
        Display a simple loading window with the message 'Loading Color Space...'.
        """
        self.load_window = tk.Toplevel(self.root)
        self.load_window.title("Loading")
        self.load_window.resizable(False, False)

        # Label with large font
        label = tk.Label(self.load_window, text="Loading Color Space...", font=("Sans", 16, "bold"), padx=20, pady=20)
        label.pack(pady=(10, 5))

        self.center_popup(self.load_window, 300, 100)

        # Disable interactions with the main window
        self.load_window.grab_set()

        # Ensure the loading window updates and displays properly
        self.load_window.update()  



    def show_loading(self):
        """
        Display a visually appealing loading window with a progress bar.
        """
        # Create a new top-level window for the loading message
        self.load_window = tk.Toplevel(self.root)
        self.load_window.title("Loading")
        self.load_window.resizable(False, False)  # Disable resizing

        # Label for the loading message
        label = tk.Label(self.load_window, text="Processing...", font=("Sans", 12), padx=10, pady=10)
        label.pack(pady=(10, 5))

        # Progress bar
        self.progress = ttk.Progressbar(self.load_window, orient="horizontal", mode="determinate", length=200)
        self.progress.pack(pady=(0, 10))

        # Center the popup
        self.center_popup(self.load_window, 300, 150)

        # Disable interactions with the main window
        self.load_window.grab_set()

        # Ensure the loading window updates and displays properly
        self.root.update_idletasks()



    def hide_loading(self):
        """
        Close the loading window if it exists.
        This method ensures that the loading window is properly destroyed.
        """
        if hasattr(self, "load_window"):
            try:
                if self.load_window.winfo_exists():
                    try:
                        self.load_window.grab_release()
                    except Exception:
                        pass

                    self.load_window.destroy()
            except Exception:
                pass

            try:
                del self.load_window
            except Exception:
                pass

        if hasattr(self, "progress"):
            try:
                del self.progress
            except Exception:
                pass



    def about_info(self):
        """
        Display an improved About window for PyFCS.
        """
        about_window = tk.Toplevel(self.root)
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

        # ------------------------------------------------------------
        # Main outer container
        # ------------------------------------------------------------
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

        # ------------------------------------------------------------
        # Header with logo
        # ------------------------------------------------------------
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

        # ------------------------------------------------------------
        # Body text
        # ------------------------------------------------------------
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
            text="Version 1.4.0",
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
            fg="#1f4e8c",
            cursor="hand2"
        )
        website_label.pack(anchor="center", pady=(0, 10))
        website_label.bind("<Button-1>", open_website)

        # ------------------------------------------------------------
        # Footer
        # ------------------------------------------------------------
        footer = tk.Frame(card, bg="white")
        footer.pack(fill="x", padx=22, pady=(12, 18))

        close_button = tk.Button(
            footer,
            text="Close",
            command=close_about,
            font=("Segoe UI", 10, "bold"),
            bg="#e8f0fe",
            fg="#1f4e8c",
            activebackground="#d7e5fb",
            activeforeground="#1f4e8c",
            relief="raised",
            bd=1,
            padx=30,
            pady=7,
            cursor="hand2",
            highlightthickness=0
        )
        close_button.pack(anchor="center")

        # ------------------------------------------------------------
        # Keyboard shortcuts
        # ------------------------------------------------------------
        about_window.bind("<Escape>", lambda _event: close_about())
        about_window.bind("<Return>", lambda _event: close_about())

        # ------------------------------------------------------------
        # Center after layout
        # ------------------------------------------------------------
        about_window.update_idletasks()
        self.center_popup(about_window, WIN_W, WIN_H)

        about_window.transient(self.root)
        about_window.grab_set()
        about_window.focus_set()

        try:
            close_button.focus_set()
        except Exception:
            pass



    def show_menu_create_fcs(self):
        self.menu_create_fcs.post(self.root.winfo_pointerx(), self.root.winfo_pointery())


    def on_mouse_wheel(self, event, target):
        """
        Scroll a widget using the mouse wheel in a cross-platform way.

        Supported cases:
        - Windows / macOS: <MouseWheel> events use event.delta
        - Linux: <Button-4> and <Button-5> events are used instead

        Args:
            event: Tkinter mouse wheel event.
            target: Scrollable widget supporting xview_scroll() or yview_scroll().
        """
        if event.num == 4:          # Linux scroll up
            step = -1
        elif event.num == 5:        # Linux scroll down
            step = 1
        elif event.delta != 0:      # Windows / macOS
            step = -int(event.delta / 120)
        else:
            return

        target.yview_scroll(step, "units")



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
                "_palette_popup",
                "_manual_popup",
                "_detected_popup",
                "_manual_picker_win",
                "_detected_picker_win",
            ):
                if getattr(self, attr, None) is window:
                    setattr(self, attr, None)

        try:
            win.bind("<Destroy>", _cleanup, add="+")
        except Exception:
            pass


    def _close_manual_picker_window(self):
        """Close the manual/custom color picker dialog if it is currently open."""
        try:
            if hasattr(self, "_manual_picker_window") and self._manual_picker_window is not None:
                if self._manual_picker_window.winfo_exists():
                    self._manual_picker_window.destroy()
        except Exception:
            pass
        finally:
            self._manual_picker_window = None


    def _close_creation_windows(self):
        """Close all creation-related windows and reset workflow state."""
        self._ensure_creation_state()

        self._close_manual_picker_window()

        for win in list(self._creation_windows):
            try:
                if win is not None and win.winfo_exists():
                    win.destroy()
            except Exception:
                pass

        self._creation_windows = []
        self._creation_in_progress = False

        self._palette_popup = None
        self._manual_popup = None
        self._detected_popup = None


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


    def _start_image_based_mode_and_close_popup(self, popup, mode):
        """Start image-based creation and close the mode selector safely."""
        try:
            if popup is not None and popup.winfo_exists():
                popup.destroy()
        except Exception:
            pass

        self._start_image_based_mode(popup, mode=mode)


    def _recalculate_detected_colors(self, popup, colors, threshold, min_samples):
        """Close current detected-colors popup and continue with recalculate flow."""
        try:
            if popup is not None and popup.winfo_exists():
                popup.destroy()
        except Exception:
            pass

        self.get_fcs_image_recalculate(colors, threshold, min_samples, popup=None)


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
        Return the folder used for temporary external Plotly plots.

        The default target is:
            external/temp/plots/

        If the app is running from Source/interface, this resolves to:
            Source/external/temp/plots/
        """
        try:
            # mainInterface.py suele estar en Source/interface/
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        except Exception:
            base_dir = os.getcwd()

        plot_dir = os.path.join(base_dir, self.TEMP_PLOT_DIR)
        os.makedirs(plot_dir, exist_ok=True)

        return plot_dir


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

        Only .html files inside external/temp/plots are affected.
        """
        try:
            plot_dir = self._get_temp_plot_dir()
            max_files = int(getattr(self, "self.TEMP_PLOT_MAX_FILES", 30))

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
            cleanup_every = int(getattr(self, "self.TEMP_PLOT_CLEANUP_EVERY", 5))
        except Exception:
            cleanup_every = 5

        cleanup_every = max(1, cleanup_every)

        if current_count % cleanup_every == 0:
            self._cleanup_temp_plot_files()



































    # ============================================================================================================================================================
    #  MAIN FUNCTIONS
    # ============================================================================================================================================================

    def update_volumes(self):
        # Process color prototypes from the input color data
        self.prototypes = UtilsTools.process_prototypes(self.color_data)

        # Create and store the fuzzy color space using the generated prototypes
        self.fuzzy_color_space = FuzzyColorSpace(space_name=" ", prototypes=self.prototypes)

        # Precompute internal fuzzy structures for efficiency
        self.fuzzy_color_space.precompute_pack()

        # Retrieve core and support regions from the fuzzy color space
        self.cores = self.fuzzy_color_space.get_cores()
        self.supports = self.fuzzy_color_space.get_supports()

        # Update application state and UI with the new prototype information
        self.update_prototypes_info()



    def update_prototypes_info(self):
        # Update 3D graph flags and application state variables
        self.COLOR_SPACE = True
        self.CAN_APPLY_MAPPING = {key: True for key in self.CAN_APPLY_MAPPING}

        # Display selection control buttons
        if not self.select_all_button.winfo_ismapped():
            self.select_all_button.pack(pady=5)

        if not self.deselect_all_button.winfo_ismapped():
            self.deselect_all_button.pack(pady=5)

        # Store current selections for visualization and processing
        self.selected_centroids = self.color_data
        self.selected_hex_color = self.hex_color
        self.selected_alpha = self.prototypes
        self.selected_core = self.cores
        self.selected_support = self.supports

        # Trigger update based on the selected options
        self.on_option_select()



    def load_color_space(self, filename=None):
        """
        Load a fuzzy color space file and update the application state.
        """
        if self._has_any_active_job():
            self.custom_warning(
                "Process Running",
                "There is a process currently running. Please wait for it to finish or cancel it before loading a Color Space."
            )
            return
        
        # Close pixel/ROI info window because its content belongs to the previous color space
        self._close_more_info_window()

        if filename is None:
            filename = UtilsTools.prompt_file_selection(
                "fuzzy_color_spaces/",
                parent=self._get_active_dialog_parent(
                    getattr(self, "_color_evaluation_window", None)
                )
            )
        if not filename:
            return

        if not hasattr(self, "mapping_locked_until_original"):
            self.mapping_locked_until_original = {}

        if hasattr(self, "floating_images") and self.floating_images:
            for window_id in list(self.floating_images.keys()):
                mode = getattr(self, "window_mapping_mode", {}).get(window_id)

                if mode == "single":
                    self.show_original_image(window_id)

                elif mode == "all":
                    # Keep the displayed image and its options visible,
                    # but mark it as belonging to an old color space.
                    self.mapping_locked_until_original[window_id] = True
                    self.CAN_APPLY_MAPPING[window_id] = False

                    try:
                        self.image_canvas.itemconfig(f"{window_id}_pct_text", text="")
                    except Exception:
                        pass

        self.show_loading_color_space()

        try:
            data = self.fuzzy_manager.load_color_file(filename)

            self.file_path = filename
            self.file_base_name = os.path.splitext(os.path.basename(filename))[0]

            if hasattr(self, "cm_cache_by_image"):
                self.cm_cache_by_image.clear()
            if hasattr(self, "proto_percentage_cache_by_image"):
                self.proto_percentage_cache_by_image.clear()

            self.color_data = data["color_data"]
            self.edit_color_data = copy.deepcopy(self.color_data)
            self.display_data_window()
            self._reset_3d_canvas()

            if data["type"] == "cns":
                self.update_volumes()

            elif data["type"] == "fcs":
                self.fuzzy_color_space = data["fuzzy_color_space"]
                self.cores = self.fuzzy_color_space.cores
                self.supports = self.fuzzy_color_space.supports
                self.prototypes = self.fuzzy_color_space.prototypes
                self.fuzzy_color_space.precompute_pack()
                self.update_prototypes_info()

        except ValueError as e:
            self.custom_warning("File Error", str(e))

        finally:
            self.hide_loading()



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
        selected_colors_lab = {
            name: np.array([data["lab"]["L"], data["lab"]["A"], data["lab"]["B"]])
            if isinstance(data["lab"], dict)
            else np.array(data["lab"])
            for name, data in self.color_checks.items()
            if data["var"].get()
        }

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

        popup = tk.Toplevel(parent_win)
        popup.title("Color Space Name")
        popup.resizable(False, False)
        popup.configure(bg="#eeeeee")

        result = {
            "created": False,
            "saving": False
        }

        # ------------------------------------------------------------------
        # Main shell
        # ------------------------------------------------------------------
        outer = tk.Frame(popup, bg="#eeeeee")
        outer.pack(fill="both", expand=True, padx=12, pady=12)

        panel = tk.Frame(outer, bg="white", bd=1, relief="solid")
        panel.pack(fill="both", expand=True)

        tk.Label(
            panel,
            text="Name for the fuzzy color space:",
            bg="white",
            fg="#222222",
            font=("Sans", 10, "bold")
        ).pack(pady=(14, 6))

        name_entry = tk.Entry(
            panel,
            font=("Sans", 10),
            width=28,
            justify="center",
            relief="solid",
            bd=1
        )
        name_entry.pack(pady=(0, 8))

        def on_ok():
            if result.get("saving", False):
                return

            name = name_entry.get().strip()

            if not name:
                self.custom_warning(
                    "Warning",
                    "Please enter a name for the fuzzy color space.",
                    parent=popup
                )
                return

            try:
                # ----------------------------------------------------------
                # Lock input while starting the Color Space creation.
                # The loading window is handled inside save_cs()
                # through _save_color_space_file().
                # ----------------------------------------------------------
                result["saving"] = True

                popup.config(cursor="watch")
                name_entry.config(state="disabled")
                ok_button.config(state="disabled")
                cancel_button.config(state="disabled")
                popup.update_idletasks()

                self.save_cs(name, selected_colors_lab)

                result["created"] = True
                popup.destroy()

            except Exception as e:
                result["created"] = False
                result["saving"] = False

                try:
                    if popup.winfo_exists():
                        popup.config(cursor="")
                        name_entry.config(state="normal")
                        ok_button.config(state="normal")
                        cancel_button.config(state="normal")
                except Exception:
                    pass

                self.custom_warning(
                    "Error",
                    f"The Color Space could not be saved: {e}",
                    parent=popup
                )

        def on_cancel():
            if result.get("saving", False):
                return

            result["created"] = False
            popup.destroy()

        button_row = tk.Frame(panel, bg="white")
        button_row.pack(fill="x", padx=16, pady=(0, 12))

        cancel_button = tk.Button(
            button_row,
            text="Cancel",
            font=("Helvetica", 9),
            bg="#f2f2f2",
            fg="#333333",
            relief="solid",
            bd=1,
            padx=14,
            pady=4,
            command=on_cancel
        )
        cancel_button.pack(side="right", padx=(8, 0))

        ok_button = tk.Button(
            button_row,
            text="OK",
            font=("Helvetica", 9, "bold"),
            bg="#E8F0FE",
            fg="#1f4e8c",
            activebackground="#D7E5FB",
            activeforeground="#1f4e8c",
            relief="solid",
            bd=1,
            padx=18,
            pady=4,
            command=on_ok
        )
        ok_button.pack(side="right")

        popup.bind("<Return>", lambda event: on_ok())
        popup.bind("<Escape>", lambda event: on_cancel())
        popup.protocol("WM_DELETE_WINDOW", on_cancel)

        # ------------------------------------------------------------------
        # Use your existing centering function
        # ------------------------------------------------------------------
        popup.update_idletasks()
        self.center_popup(popup, 340, 135)

        popup.transient(parent_win)
        popup.grab_set()

        try:
            popup.lift(parent_win)
            popup.focus_force()
        except Exception:
            pass

        name_entry.focus_set()

        popup.wait_window()

        return result["created"]



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


    def _on_apply_changes_saved_success(self, name, file_path, saved_color_data):
        self.color_data = copy.deepcopy(saved_color_data)
        self.edit_color_data = copy.deepcopy(saved_color_data)
        self.file_path = file_path
        self.file_base_name = name

        self.update_volumes()
        self.display_data_window()

        messagebox.showinfo(
            "Changes Applied",
            f"Color Space '{name}' was updated successfully."
        )
        

    def _save_color_space_file(self, name, color_dict, saved_color_data=None, apply_after_save=False):
        """
        Save a fuzzy color space file in a background thread.
        """
        self.show_loading()

        def update_progress(current_line, total_lines):
            """Safely update the progress bar if it exists."""
            try:
                if total_lines <= 0:
                    return

                if not hasattr(self, "progress") or self.progress is None:
                    return

                if not hasattr(self, "load_window") or self.load_window is None:
                    return

                try:
                    if not self.progress.winfo_exists():
                        return
                except Exception:
                    return

                try:
                    if not self.load_window.winfo_exists():
                        return
                except Exception:
                    return

                progress_percentage = (current_line / total_lines) * 100
                self.progress["value"] = progress_percentage
                self.load_window.update_idletasks()

            except Exception:
                pass

        def run_save_process():
            try:
                input_class = Input.instance(".fcs")
                file_path = input_class.write_file(
                    name,
                    color_dict,
                    progress_callback=update_progress
                )

                if apply_after_save:
                    self.root.after(
                        0,
                        lambda: self._on_apply_changes_saved_success(name, file_path, saved_color_data)
                    )
                else:
                    self.root.after(
                        0,
                        lambda: self._on_color_space_saved_success(name, file_path)
                    )

            except Exception as e:
                error_msg = f"An error occurred while saving: {e}"
                self.root.after(
                    0,
                    lambda msg=error_msg: self.custom_warning("Error", msg)
                )

            finally:
                self.root.after(0, self.hide_loading)

        threading.Thread(target=run_save_process, daemon=True).start()


    def save_cs(self, name, selected_colors_lab):
        self._save_color_space_file(name, selected_colors_lab)


    def save_fcs(self, name, colors, color_dict=None, apply_after_save=False):
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

        self._save_color_space_file(
            name,
            color_dict,
            saved_color_data=copy.deepcopy(colors),
            apply_after_save=apply_after_save
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


    def _close_creation_windows(self):
        """
        Close any active fuzzy color space creation popups.
        """
        popup_attrs = (
            "_manual_popup",
            "_manual_picker_win",
            "_palette_popup",
            "_create_fcs_popup",
        )

        for attr in popup_attrs:
            if hasattr(self, attr):
                win = getattr(self, attr)
                try:
                    if win is not None and win.winfo_exists():
                        win.destroy()
                except Exception:
                    pass
                setattr(self, attr, None)



    def addColor_create_fcs(self, popup, colors, on_color_added=None):
        """
        Add a new custom color to the palette used for fuzzy color space creation.
        The new color is automatically selected.
        """

        def on_submit(color_name, sample_lab, sample_rgb, sample_hex, dialog, input_vars):
            clean_name = color_name.strip()

            if not clean_name:
                input_vars["status_var"].set("Enter a color name.")
                self.custom_warning(
                    "Invalid Color Name",
                    "Enter a color name.",
                    parent=dialog
                )
                return

            if clean_name in colors:
                input_vars["status_var"].set("A color with this name already exists.")
                self.custom_warning(
                    "Duplicated Color Name",
                    f"The color '{clean_name}' already exists in the palette.",
                    parent=dialog
                )
                return

            colors[clean_name] = {
                "rgb": sample_rgb,
                "lab": sample_lab,
                "hex": sample_hex,
            }

            self.fuzzy_manager.create_color_display_frame(
                parent=self.scroll_palette_create_fcs,
                color_name=clean_name,
                rgb=sample_rgb,
                lab=sample_lab,
                color_checks=self.color_checks,
                selected=True,
                on_toggle=on_color_added
            )

            if callable(on_color_added):
                on_color_added()

            dialog.destroy()

            try:
                self.scroll_palette_create_fcs.update_idletasks()
            except Exception:
                pass

        self._open_custom_color_dialog(
            parent=popup,
            title="Add New Color",
            subtitle="Create a palette color from RGB, LAB or HEX",
            submit_text="Add Color",
            require_name=True,
            default_name="New Color",
            on_submit=on_submit
        )
        


    # ============================================================================
    # Palette-Based Fuzzy Color Space Creation
    # ----------------------------------------------------------------------------
    # This section implements the workflow for creating a fuzzy color space
    # using a predefined color palette. It allows the user to:
    #
    #   - Load a predefined color palette from a .cns file.
    #   - Open a popup window displaying all available palette colors.
    #   - Visually inspect each color in RGB and LAB color spaces.
    #   - Select multiple colors using checkboxes.
    #   - Add new custom colors to the palette.
    #   - Create a new fuzzy color space from the selected colors.
    #
    # The popup interface provides a scrollable layout to handle large palettes
    # and includes action buttons for extending the palette or finalizing the
    # color space creation. UI components are styled consistently to ensure
    # clarity and usability.
    # ============================================================================
    def palette_based_creation(self):
        """
        Logic for creating a new fuzzy color space using a predefined palette.
        Allows the user to select colors through a popup and creates a new fuzzy color space.
        """
        if not self._can_start_new_creation():
            return

        color_space_path = os.path.join(
            BASE_PATH,
            "fuzzy_color_spaces",
            "cns",
            "ISCC_NBS_BASIC.cns"
        )
        colors = UtilsTools.load_color_data(color_space_path)

        popup = tk.Toplevel(self.root)
        popup.title("Palette-Based Color Space Creation")
        popup.configure(bg="#eeeeee")
        popup.resizable(False, False)
        popup.transient(self.root)

        WIN_W, WIN_H = 620, 620
        self.center_popup(popup, WIN_W, WIN_H)

        self._palette_popup = popup
        self._register_creation_window(popup)

        def on_close():
            self._close_manual_picker_window()
            self._palette_popup = None
            popup.destroy()

        popup.protocol("WM_DELETE_WINDOW", on_close)

        self.color_checks = {}

        # ------------------------------------------------------------------
        # Styles
        # ------------------------------------------------------------------
        style = ttk.Style(popup)

        try:
            style.configure(
                "Palette.Primary.TButton",
                font=("Helvetica", 10, "bold"),
                padding=(12, 8)
            )
            style.configure(
                "Palette.Secondary.TButton",
                font=("Helvetica", 10),
                padding=(10, 7)
            )
            style.configure(
                "Palette.Row.TFrame",
                background="#ffffff"
            )
        except Exception:
            pass

        # ------------------------------------------------------------------
        # Main shell
        # ------------------------------------------------------------------
        outer = tk.Frame(popup, bg="#eeeeee")
        outer.pack(fill="both", expand=True, padx=14, pady=14)

        panel = tk.Frame(outer, bg="white", bd=1, relief="solid")
        panel.pack(fill="both", expand=True)

        # ------------------------------------------------------------------
        # Header
        # ------------------------------------------------------------------
        header = tk.Frame(panel, bg="#f6f6f6", height=68)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(
            header,
            text="Select Colors for your Color Space",
            font=("Sans", 13, "bold"),
            bg="#f6f6f6",
            fg="#222222",
            anchor="w",
            padx=16
        ).pack(side="left", fill="y")

        tk.Label(
            header,
            text="Choose palette colors or add custom ones",
            font=("Sans", 10, "italic"),
            bg="#f6f6f6",
            fg="#666666",
            anchor="e",
            padx=16
        ).pack(side="right", fill="y")

        # ------------------------------------------------------------------
        # Toolbar
        # ------------------------------------------------------------------
        toolbar = tk.Frame(panel, bg="white")
        toolbar.pack(fill="x", padx=16, pady=(14, 8))

        selected_count_var = tk.StringVar(value="0 selected")

        def update_selected_count():
            try:
                selected = sum(
                    1 for item in self.color_checks.values()
                    if item["var"].get()
                )
                total = len(self.color_checks)
                selected_count_var.set(f"{selected} of {total} selected")
            except Exception:
                selected_count_var.set("0 selected")

        def select_all_colors():
            for item in self.color_checks.values():
                try:
                    item["var"].set(True)
                except Exception:
                    pass
            update_selected_count()

        def deselect_all_colors():
            for item in self.color_checks.values():
                try:
                    item["var"].set(False)
                except Exception:
                    pass
            update_selected_count()

        ttk.Button(
            toolbar,
            text="Select All",
            command=select_all_colors,
            style="Palette.Secondary.TButton"
        ).pack(side="left", padx=(0, 8))

        ttk.Button(
            toolbar,
            text="Deselect All",
            command=deselect_all_colors,
            style="Palette.Secondary.TButton"
        ).pack(side="left", padx=(0, 8))

        tk.Label(
            toolbar,
            textvariable=selected_count_var,
            bg="white",
            fg="#666666",
            font=("Sans", 9, "italic"),
            anchor="e"
        ).pack(side="right")

        # ------------------------------------------------------------------
        # List card
        # ------------------------------------------------------------------
        list_card = tk.Frame(panel, bg="#fafafa", bd=1, relief="solid")
        list_card.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        list_header = tk.Frame(list_card, bg="#f2f2f2", height=34)
        list_header.pack(fill="x")
        list_header.pack_propagate(False)

        tk.Label(
            list_header,
            text="Available Colors",
            bg="#f2f2f2",
            fg="#222222",
            font=("Sans", 10, "bold"),
            anchor="w",
            padx=12
        ).pack(side="left", fill="y")

        tk.Label(
            list_header,
            text="LAB values",
            bg="#f2f2f2",
            fg="#666666",
            font=("Sans", 9, "italic"),
            anchor="e",
            padx=12
        ).pack(side="right", fill="y")

        # ------------------------------------------------------------------
        # Scrollable area
        # ------------------------------------------------------------------
        canvas = tk.Canvas(
            list_card,
            bg="#fafafa",
            highlightthickness=0,
            bd=0
        )

        scrollbar = ttk.Scrollbar(
            list_card,
            orient="vertical",
            command=canvas.yview
        )

        self.scroll_palette_create_fcs = tk.Frame(canvas, bg="#fafafa")

        scroll_window = canvas.create_window(
            (0, 0),
            window=self.scroll_palette_create_fcs,
            anchor="nw"
        )

        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_frame_configure(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfig(scroll_window, width=event.width)

        self.scroll_palette_create_fcs.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(event):
            try:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        canvas.bind("<MouseWheel>", _on_mousewheel)
        self.scroll_palette_create_fcs.bind("<MouseWheel>", _on_mousewheel)

        # ------------------------------------------------------------------
        # Load colors
        # ------------------------------------------------------------------
        for color_name, data in colors.items():
            self.fuzzy_manager.create_color_display_frame(
                parent=self.scroll_palette_create_fcs,
                color_name=color_name,
                rgb=data["rgb"],
                lab=data["lab"],
                color_checks=self.color_checks,
                selected=False,
                on_toggle=update_selected_count
            )

        update_selected_count()

        def create_color_space_and_close():
            """Create the color space and close the palette window if creation succeeds."""
            try:
                result = self.create_color_space(parent=popup)

                # If creation was cancelled or failed, keep this window open.
                if result is False:
                    return

                self._palette_popup = None

                try:
                    popup.destroy()
                except Exception:
                    pass

            except Exception as e:
                self.custom_warning(
                    "Error",
                    f"The Color Space could not be created: {e}",
                    parent=popup
                )

        # ------------------------------------------------------------------
        # Footer buttons
        # ------------------------------------------------------------------
        footer = tk.Frame(panel, bg="white")
        footer.pack(fill="x", padx=16, pady=(0, 14))

        ttk.Button(
            footer,
            text="Add New Color",
            command=lambda: self.addColor_create_fcs(
                popup=popup,
                colors=colors,
                on_color_added=update_selected_count
            ),
            style="Palette.Secondary.TButton"
        ).pack(side="left")

        ttk.Button(
            footer,
            text="Create Color Space",
            command=create_color_space_and_close,
            style="Palette.Primary.TButton"
        ).pack(side="right")


    def image_based_creation(self):
        """
        Unified image-based fuzzy color space creation.

        Opens:
        - a palette-like window, initially empty, where selected colors are collected;
        - a secondary image tool window docked to the right for manual sampling
        and automatic color detection.
        """
        if not hasattr(self, "load_images_names") or not self.load_images_names:
            self.custom_warning(message="No images are currently available to display.")
            return

        if not self._can_start_new_creation():
            return

        self.FIRST_DBSCAN = True
        self._open_unified_image_based_creation()



    def _open_unified_image_based_creation(self):
        """
        Open the unified image-based creation workspace.

        Left/main popup:
            - collected colors
            - editable color names
            - Select All / Deselect All / Remove Color
            - Image Color Tools / Add New Color
            - Create Color Space

        Right popup:
            - image selector
            - manual color picker from image
            - automatic color detection
        """
        colors = {}

        popup = tk.Toplevel(self.root)
        popup.title("Image-Based Color Space Creation")
        popup.configure(bg="#eeeeee")
        popup.resizable(False, False)

        WIN_W, WIN_H = 620, 620
        self.center_popup(popup, WIN_W, WIN_H)

        self._manual_popup = popup
        self._image_creation_popup = popup
        self._register_creation_window(popup)

        self.color_checks = {}

        def on_close():
            self._close_manual_picker_window()

            if hasattr(self, "_image_creation_tool_win"):
                try:
                    if self._image_creation_tool_win and self._image_creation_tool_win.winfo_exists():
                        self._image_creation_tool_win.destroy()
                except Exception:
                    pass
                self._image_creation_tool_win = None

            self._manual_popup = None
            self._image_creation_popup = None
            popup.destroy()

        popup.protocol("WM_DELETE_WINDOW", on_close)

        # ------------------------------------------------------------------
        # Styles
        # ------------------------------------------------------------------
        style = ttk.Style(popup)

        try:
            style.configure(
                "ImageCreate.Primary.TButton",
                font=("Helvetica", 10, "bold"),
                padding=(12, 8)
            )
            style.configure(
                "ImageCreate.Secondary.TButton",
                font=("Helvetica", 10),
                padding=(10, 7)
            )
        except Exception:
            pass

        # ------------------------------------------------------------------
        # Main shell
        # ------------------------------------------------------------------
        outer = tk.Frame(popup, bg="#eeeeee")
        outer.pack(fill="both", expand=True, padx=14, pady=14)

        panel = tk.Frame(outer, bg="white", bd=1, relief="solid")
        panel.pack(fill="both", expand=True)

        # ------------------------------------------------------------------
        # Header
        # ------------------------------------------------------------------
        header = tk.Frame(panel, bg="#f6f6f6", height=68)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(
            header,
            text="Select Colors",
            font=("Sans", 13, "bold"),
            bg="#f6f6f6",
            fg="#222222",
            anchor="w",
            padx=16
        ).pack(side="left", fill="y")

        tk.Label(
            header,
            text="Sample manually or detect colors automatically from images",
            font=("Sans", 10, "italic"),
            bg="#f6f6f6",
            fg="#666666",
            anchor="e",
            padx=16
        ).pack(side="right", fill="y")

        # ------------------------------------------------------------------
        # Toolbar
        # ------------------------------------------------------------------
        toolbar = tk.Frame(panel, bg="white")
        toolbar.pack(fill="x", padx=16, pady=(14, 8))

        selected_count_var = tk.StringVar(value="0 of 0 selected")

        def update_selected_count():
            try:
                selected = sum(
                    1 for item in self.color_checks.values()
                    if item["var"].get()
                )
                total = len(self.color_checks)
                selected_count_var.set(f"{selected} of {total} selected")
            except Exception:
                selected_count_var.set("0 of 0 selected")

        def select_all_colors():
            for item in self.color_checks.values():
                try:
                    item["var"].set(True)
                except Exception:
                    pass
            update_selected_count()

        def deselect_all_colors():
            for item in self.color_checks.values():
                try:
                    item["var"].set(False)
                except Exception:
                    pass
            update_selected_count()

        def rename_color(old_name, requested_name):
            """Rename a color in the local colors dictionary and color_checks."""
            MAX_NAME_CHARS = 16

            old_name = str(old_name).strip()
            new_name = str(requested_name).strip()

            if len(new_name) > MAX_NAME_CHARS:
                new_name = new_name[:MAX_NAME_CHARS]

            if not new_name:
                self.custom_warning(
                    "Invalid Color Name",
                    "Color name cannot be empty.",
                    parent=popup
                )
                return old_name

            if new_name == old_name:
                return old_name

            if new_name in colors:
                self.custom_warning(
                    "Duplicated Color Name",
                    f"The color '{new_name}' already exists.",
                    parent=popup
                )
                return old_name

            if old_name not in colors:
                return old_name

            colors[new_name] = colors.pop(old_name)

            if old_name in self.color_checks:
                self.color_checks[new_name] = self.color_checks.pop(old_name)

            update_selected_count()
            return new_name

        def redraw_color_list():
            """
            Redraw the collected color list from the local colors dictionary.
            Used after adding/removing/renaming colors.
            """
            previous_selected = {}

            try:
                for name, item in self.color_checks.items():
                    previous_selected[name] = bool(item["var"].get())
            except Exception:
                previous_selected = {}

            try:
                for widget in self.scroll_palette_create_fcs.winfo_children():
                    widget.destroy()
            except Exception:
                pass

            self.color_checks = {}

            for color_name, data in colors.items():
                try:
                    rgb = data.get("rgb")
                    lab = data.get("lab")

                    if isinstance(lab, dict):
                        lab = (
                            float(lab.get("L", 0.0)),
                            float(lab.get("A", lab.get("a", 0.0))),
                            float(lab.get("B", lab.get("b", 0.0)))
                        )
                    elif lab is not None:
                        lab_arr = np.array(lab, dtype=float).reshape(-1)
                        lab = (
                            float(lab_arr[0]),
                            float(lab_arr[1]),
                            float(lab_arr[2])
                        )

                    if rgb is None and lab is not None:
                        rgb = UtilsTools.lab_to_rgb(lab)

                    if rgb is None:
                        rgb = (217, 217, 217)

                    selected = previous_selected.get(color_name, True)

                    self.fuzzy_manager.create_color_display_frame(
                        parent=self.scroll_palette_create_fcs,
                        color_name=color_name,
                        rgb=rgb,
                        lab=lab,
                        color_checks=self.color_checks,
                        selected=selected,
                        on_toggle=update_selected_count,
                        editable_name=True,
                        on_name_change=rename_color
                    )

                except Exception:
                    continue

            update_selected_count()

        def remove_selected_colors():
            """Remove selected colors from the current image-based color list."""
            selected_names = []

            for color_name, item in list(self.color_checks.items()):
                try:
                    if item["var"].get():
                        selected_names.append(color_name)
                except Exception:
                    pass

            if not selected_names:
                self.custom_warning(
                    "No Color Selected",
                    "Select at least one color to remove.",
                    parent=popup
                )
                return

            for color_name in selected_names:
                colors.pop(color_name, None)

            redraw_color_list()

        ttk.Button(
            toolbar,
            text="Select All",
            command=select_all_colors,
            style="ImageCreate.Secondary.TButton"
        ).pack(side="left", padx=(0, 8))

        ttk.Button(
            toolbar,
            text="Deselect All",
            command=deselect_all_colors,
            style="ImageCreate.Secondary.TButton"
        ).pack(side="left", padx=(0, 8))

        ttk.Button(
            toolbar,
            text="Remove Color",
            command=remove_selected_colors,
            style="ImageCreate.Secondary.TButton"
        ).pack(side="left", padx=(0, 8))

        tk.Label(
            toolbar,
            textvariable=selected_count_var,
            bg="white",
            fg="#666666",
            font=("Sans", 9, "italic"),
            anchor="e"
        ).pack(side="right")

        # ------------------------------------------------------------------
        # List card
        # ------------------------------------------------------------------
        list_card = tk.Frame(panel, bg="#fafafa", bd=1, relief="solid")
        list_card.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        list_header = tk.Frame(list_card, bg="#f2f2f2", height=34)
        list_header.pack(fill="x")
        list_header.pack_propagate(False)

        tk.Label(
            list_header,
            text="Selected Colors",
            bg="#f2f2f2",
            fg="#222222",
            font=("Sans", 10, "bold"),
            anchor="w",
            padx=12
        ).pack(side="left", fill="y")

        tk.Label(
            list_header,
            text="Name and LAB values",
            bg="#f2f2f2",
            fg="#666666",
            font=("Sans", 9, "italic"),
            anchor="e",
            padx=12
        ).pack(side="right", fill="y")

        canvas = tk.Canvas(
            list_card,
            bg="#fafafa",
            highlightthickness=0,
            bd=0
        )

        scrollbar = ttk.Scrollbar(
            list_card,
            orient="vertical",
            command=canvas.yview
        )

        self.scroll_palette_create_fcs = tk.Frame(canvas, bg="#fafafa")

        scroll_window = canvas.create_window(
            (0, 0),
            window=self.scroll_palette_create_fcs,
            anchor="nw"
        )

        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_frame_configure(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfig(scroll_window, width=event.width)

        self.scroll_palette_create_fcs.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        canvas.bind(
            "<MouseWheel>",
            lambda event: self.on_mouse_wheel(event, canvas)
        )
        self.scroll_palette_create_fcs.bind(
            "<MouseWheel>",
            lambda event: self.on_mouse_wheel(event, canvas)
        )

        def reopen_image_color_tools():
            """
            Open the Image Color Tools window.

            If it is already open, close it first and open a fresh one.
            This reloads the available image list in case new images were loaded.
            """
            try:
                if (
                    hasattr(self, "_image_creation_tool_win")
                    and self._image_creation_tool_win is not None
                    and self._image_creation_tool_win.winfo_exists()
                ):
                    self._image_creation_tool_win.destroy()
            except Exception:
                pass

            self._image_creation_tool_win = None
            self._manual_picker_win = None

            self._open_image_creation_tool_window(
                parent_popup=popup,
                colors=colors,
                target_frame=self.scroll_palette_create_fcs,
                update_selected_count=redraw_color_list
            )

        def create_color_space_and_close():
            """Create the color space and close the image-based creation windows if creation succeeds."""
            try:
                selected_colors = [
                    color_name
                    for color_name, item in self.color_checks.items()
                    if item["var"].get()
                ]

                if len(selected_colors) < 2:
                    self.custom_warning(
                        "Not Enough Colors",
                        "At least two colors must be selected to create the Color Space.",
                        parent=popup
                    )
                    return

                result = self.create_color_space(parent=popup)

                # If create_color_space explicitly returns False, keep the window open.
                if result is False:
                    return

                try:
                    if (
                        hasattr(self, "_image_creation_tool_win")
                        and self._image_creation_tool_win is not None
                        and self._image_creation_tool_win.winfo_exists()
                    ):
                        self._image_creation_tool_win.destroy()
                except Exception:
                    pass

                self._image_creation_tool_win = None
                self._manual_picker_win = None
                self._manual_popup = None
                self._image_creation_popup = None

                try:
                    popup.destroy()
                except Exception:
                    pass

            except Exception as e:
                self.custom_warning(
                    "Error",
                    f"The Color Space could not be created: {e}",
                    parent=popup
                )

        # ------------------------------------------------------------------
        # Footer buttons
        # ------------------------------------------------------------------
        footer = tk.Frame(panel, bg="white")
        footer.pack(fill="x", padx=16, pady=(0, 14))

        ttk.Button(
            footer,
            text="Image Color Tools",
            command=reopen_image_color_tools,
            style="ImageCreate.Secondary.TButton"
        ).pack(side="left", padx=(0, 8))

        ttk.Button(
            footer,
            text="Add New Color",
            command=lambda: self.addColor_create_fcs(
                popup=popup,
                colors=colors,
                on_color_added=redraw_color_list
            ),
            style="ImageCreate.Secondary.TButton"
        ).pack(side="left")

        ttk.Button(
            footer,
            text="Create Color Space",
            command=create_color_space_and_close,
            style="ImageCreate.Primary.TButton"
        ).pack(side="right")

        # Open image tool window to the right
        reopen_image_color_tools()

        update_selected_count()


    def _open_image_creation_tool_window(self, parent_popup, colors, target_frame, update_selected_count):
        """
        Open the right-side image tool window.

        It supports:
        - selecting image;
        - manual sampling by click or rectangle;
        - automatic color detection;
        - adding sampled/detected colors to the main color list.
        """
        if not hasattr(self, "load_images_names") or not self.load_images_names:
            self.custom_warning(message="No images are currently available to display.")
            return

        if hasattr(self, "_image_creation_tool_win"):
            try:
                if self._image_creation_tool_win and self._image_creation_tool_win.winfo_exists():
                    self._image_creation_tool_win.lift()
                    self._image_creation_tool_win.focus_force()
                    return
            except Exception:
                pass

        win = tk.Toplevel(parent_popup)
        win.title("Image Color Tools")
        win.configure(bg="#eeeeee")
        win.resizable(False, False)
        win.transient(parent_popup)

        self._image_creation_tool_win = win
        self._manual_picker_win = win

        self._manual_dragging = False
        self._manual_drag_start = None
        self._manual_rect_id = None
        self._picked_rgb = None
        self._picked_lab = None

        WIN_W, WIN_H = 560, 625

        def dock_tool_window(event=None):
            """Keep the tool window docked next to the image-based creation window."""
            try:
                if not parent_popup.winfo_exists() or not win.winfo_exists():
                    return

                parent_popup.update_idletasks()
                win.update_idletasks()

                px = parent_popup.winfo_rootx()
                py = parent_popup.winfo_rooty()
                pw = parent_popup.winfo_width()

                gap = 12

                x = px + pw + gap
                y = py

                screen_w = parent_popup.winfo_screenwidth()
                screen_h = parent_popup.winfo_screenheight()

                # If it does not fit on the right, place it on the left.
                if x + WIN_W > screen_w:
                    x = max(0, px - WIN_W - gap)

                # Keep it vertically visible.
                if y + WIN_H > screen_h:
                    y = max(0, screen_h - WIN_H - 40)

                win.geometry(f"{WIN_W}x{WIN_H}+{x}+{y}")

            except Exception:
                pass

        dock_tool_window()

        try:
            dock_bind_id = parent_popup.bind("<Configure>", dock_tool_window, add="+")
        except Exception:
            dock_bind_id = None

        style = ttk.Style(win)

        try:
            style.configure(
                "ImageTool.Primary.TButton",
                font=("Helvetica", 10, "bold"),
                padding=(12, 8)
            )
            style.configure(
                "ImageTool.Secondary.TButton",
                font=("Helvetica", 10),
                padding=(10, 7)
            )
            style.configure(
                "ImageTool.CompactPrimary.TButton",
                font=("Helvetica", 9, "bold"),
                padding=(8, 5)
            )
        except Exception:
            pass

        outer = tk.Frame(win, bg="#eeeeee")
        outer.pack(fill="both", expand=True, padx=12, pady=12)

        panel = tk.Frame(outer, bg="white", bd=1, relief="solid")
        panel.pack(fill="both", expand=True)

        # ------------------------------------------------------------------
        # Header
        # ------------------------------------------------------------------
        header = tk.Frame(panel, bg="#f6f6f6", height=60)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(
            header,
            text="Image Color Tools",
            font=("Sans", 13, "bold"),
            bg="#f6f6f6",
            fg="#222222",
            anchor="w",
            padx=16
        ).pack(side="left", fill="y")

        tk.Label(
            header,
            text="Manual sampling and automatic detection",
            font=("Sans", 9, "italic"),
            bg="#f6f6f6",
            fg="#666666",
            padx=16
        ).pack(side="right", fill="y")

        body = tk.Frame(panel, bg="white")
        body.pack(fill="both", expand=True, padx=14, pady=12)

        # ------------------------------------------------------------------
        # Compact top controls: image selector + mode selector
        # ------------------------------------------------------------------
        selector_card = tk.Frame(body, bg="#fafafa", bd=1, relief="solid")
        selector_card.pack(fill="x", pady=(0, 10))

        selector_row = tk.Frame(selector_card, bg="#fafafa")
        selector_row.pack(fill="x", padx=12, pady=8)

        tk.Label(
            selector_row,
            text="Image:",
            bg="#fafafa",
            fg="#222222",
            font=("Sans", 10, "bold")
        ).pack(side="left", padx=(0, 8))

        image_names = []
        image_ids = []

        for wid, path in self.load_images_names.items():
            image_ids.append(wid)
            image_names.append(os.path.basename(path))

        selected_image_var = tk.StringVar(value=image_names[0] if image_names else "")

        image_combo = ttk.Combobox(
            selector_row,
            textvariable=selected_image_var,
            state="readonly",
            values=image_names,
            width=27
        )
        image_combo.pack(side="left", fill="x", expand=True)

        tk.Label(
            selector_row,
            text="Mode:",
            bg="#fafafa",
            fg="#222222",
            font=("Sans", 10, "bold")
        ).pack(side="left", padx=(12, 6))

        mode_var = tk.StringVar(value="Manual")

        mode_combo = ttk.Combobox(
            selector_row,
            textvariable=mode_var,
            state="readonly",
            values=["Manual", "Automatic"],
            width=12
        )
        mode_combo.pack(side="left")

        # ------------------------------------------------------------------
        # Image canvas
        # ------------------------------------------------------------------
        image_card = tk.Frame(body, bg="#fafafa", bd=1, relief="solid")
        image_card.pack(fill="x", pady=(0, 10))

        tk.Label(
            image_card,
            text="Image Preview",
            bg="#fafafa",
            fg="#222222",
            font=("Sans", 10, "bold"),
            anchor="w",
            padx=12,
            pady=7
        ).pack(fill="x")

        self._manual_img_canvas = tk.Canvas(
            image_card,
            width=465,
            height=285,
            bg="white",
            highlightthickness=0,
            bd=0
        )
        self._manual_img_canvas.pack(padx=12, pady=(0, 8))

        tip_var = tk.StringVar(
            value="Manual: click for a pixel or drag a rectangle to sample an average color."
        )

        tk.Label(
            image_card,
            textvariable=tip_var,
            bg="#fafafa",
            fg="#666666",
            font=("Sans", 9, "italic"),
            wraplength=455,
            justify="left",
            padx=12,
            pady=0
        ).pack(fill="x", pady=(0, 8))

        # ------------------------------------------------------------------
        # Manual card
        # ------------------------------------------------------------------
        manual_card = tk.Frame(body, bg="#fafafa", bd=1, relief="solid")
        manual_card.pack(fill="x", pady=(0, 10))

        tk.Label(
            manual_card,
            text="Manual Selected Color",
            bg="#fafafa",
            fg="#222222",
            font=("Sans", 10, "bold"),
            anchor="w",
            padx=12,
            pady=7
        ).pack(fill="x")

        manual_row = tk.Frame(manual_card, bg="#fafafa")
        manual_row.pack(fill="x", padx=12, pady=(0, 10))

        values_frame = tk.Frame(manual_row, bg="#fafafa")
        values_frame.pack(side="left", fill="x", expand=True)

        self._picked_rgb_var = tk.StringVar(value="RGB: -")
        self._picked_lab_var = tk.StringVar(value="LAB: -")

        tk.Label(
            values_frame,
            textvariable=self._picked_rgb_var,
            bg="#fafafa",
            fg="#333333",
            font=("Sans", 9),
            anchor="w"
        ).pack(anchor="w")

        tk.Label(
            values_frame,
            textvariable=self._picked_lab_var,
            bg="#fafafa",
            fg="#333333",
            font=("Sans", 9),
            anchor="w"
        ).pack(anchor="w", pady=(2, 0))

        self._picked_preview = tk.Canvas(
            manual_row,
            width=135,
            height=38,
            bg="#fafafa",
            highlightthickness=0,
            bd=0
        )
        self._picked_preview.pack(side="left", padx=(14, 14))

        self._picked_preview_rect = self._picked_preview.create_rectangle(
            8, 6, 127, 32,
            fill="#d9d9d9",
            outline="#555555",
            width=1
        )

        manual_add_button = ttk.Button(
            manual_row,
            text="Add",
            command=lambda: self._image_creation_add_picked_color(
                colors=colors,
                target_frame=target_frame,
                update_selected_count=update_selected_count
            ),
            style="ImageTool.Primary.TButton"
        )
        manual_add_button.pack(side="right")

        # ------------------------------------------------------------------
        # Automatic card
        # ------------------------------------------------------------------
        auto_card = tk.Frame(body, bg="#fafafa", bd=1, relief="solid")
        auto_card.pack(fill="x")

        tk.Label(
            auto_card,
            text="Automatic Detection",
            bg="#fafafa",
            fg="#222222",
            font=("Sans", 10, "bold"),
            anchor="w",
            padx=12,
            pady=7
        ).pack(fill="x")

        auto_controls = tk.Frame(auto_card, bg="#fafafa")
        auto_controls.pack(fill="x", padx=12, pady=(0, 6))

        threshold = tk.DoubleVar(value=0.50)
        min_samples = tk.IntVar(value=160)

        threshold_text = tk.StringVar(value="Threshold: 0.50")

        def update_threshold_label():
            threshold_text.set(f"Threshold: {threshold.get():.2f}")

        def decrease_threshold():
            threshold.set(max(0.0, threshold.get() - 0.05))
            min_samples.set(min_samples.get() + 15)
            update_threshold_label()

        def increase_threshold():
            threshold.set(min(1.0, threshold.get() + 0.05))
            min_samples.set(max(15, min_samples.get() - 15))
            update_threshold_label()

        tk.Label(
            auto_controls,
            textvariable=threshold_text,
            bg="#fafafa",
            fg="#333333",
            font=("Sans", 9)
        ).pack(side="left")

        minus_button = tk.Button(
            auto_controls,
            text="-",
            width=3,
            bg="#f8d7da",
            fg="#8a1f1f",
            relief="solid",
            bd=1,
            command=decrease_threshold
        )
        minus_button.pack(side="left", padx=(12, 4))

        plus_button = tk.Button(
            auto_controls,
            text="+",
            width=3,
            bg="#e0f2e9",
            fg="#1f5f3a",
            relief="solid",
            bd=1,
            command=increase_threshold
        )
        plus_button.pack(side="left", padx=(0, 12))

        # Small explanation
        tk.Label(
            auto_card,
            text=(
                "If too many colors are detected, try decreasing it; if too few are detected, try increasing it."
            ),
            bg="#fafafa",
            fg="#666666",
            font=("Sans", 8, "italic"),
            wraplength=505,
            justify="left",
            anchor="w",
            padx=12,
            pady=0
        ).pack(fill="x", pady=(0, 8))

        busy_state = {
            "running": False,
            "angle": 0
        }

        def draw_loading_overlay():
            """Draw a loading overlay over the image canvas."""
            try:
                self._manual_img_canvas.delete("auto_spinner")

                cw = int(self._manual_img_canvas["width"])
                ch = int(self._manual_img_canvas["height"])

                cx = cw // 2
                cy = ch // 2

                self._manual_img_canvas.create_rectangle(
                    cx - 82,
                    cy - 46,
                    cx + 82,
                    cy + 50,
                    fill="white",
                    outline="#cfcfcf",
                    tags=("auto_spinner",)
                )

                self._manual_img_canvas.create_arc(
                    cx - 18,
                    cy - 26,
                    cx + 18,
                    cy + 10,
                    start=busy_state["angle"],
                    extent=285,
                    style="arc",
                    width=4,
                    outline="#1f5fa8",
                    tags=("auto_spinner",)
                )

                self._manual_img_canvas.create_text(
                    cx,
                    cy + 28,
                    text="Detecting...",
                    fill="#333333",
                    font=("Sans", 9, "bold"),
                    tags=("auto_spinner",)
                )

            except Exception:
                pass

        def animate_loading_overlay():
            """Animate the loading overlay while automatic detection is running."""
            if not busy_state["running"]:
                try:
                    self._manual_img_canvas.delete("auto_spinner")
                except Exception:
                    pass
                return

            busy_state["angle"] = (busy_state["angle"] + 18) % 360
            draw_loading_overlay()

            try:
                win.after(70, animate_loading_overlay)
            except Exception:
                pass

        def set_tool_busy(is_busy):
            """Block/unblock the image tool controls."""
            busy_state["running"] = bool(is_busy)

            try:
                image_combo.config(state="disabled" if is_busy else "readonly")
                mode_combo.config(state="disabled" if is_busy else "readonly")
                manual_add_button.config(state="disabled" if is_busy else "normal")
                minus_button.config(state="disabled" if is_busy else "normal")
                plus_button.config(state="disabled" if is_busy else "normal")
                detect_button.config(state="disabled" if is_busy else "normal")
            except Exception:
                pass

            if is_busy:
                animate_loading_overlay()
            else:
                try:
                    self._manual_img_canvas.delete("auto_spinner")
                except Exception:
                    pass

        def add_detected_colors_to_list(detected_colors, window_id):
            """Add detected colors to the main selected-colors list."""
            if not detected_colors:
                self.custom_warning(
                    "No Colors Detected",
                    "No colors were detected with the current threshold.",
                    parent=win
                )
                return

            added = 0

            for item in detected_colors:
                try:
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
                                float(lab_value["A"]),
                                float(lab_value["B"])
                            )
                        else:
                            lab_arr = np.array(lab_value, dtype=float).reshape(-1)
                            lab = (
                                float(lab_arr[0]),
                                float(lab_arr[1]),
                                float(lab_arr[2])
                            )
                    else:
                        lab = UtilsTools.srgb_to_lab(rgb[0], rgb[1], rgb[2])
                        lab = (
                            float(lab[0]),
                            float(lab[1]),
                            float(lab[2])
                        )

                    base_name = item.get("name", f"Detected Color {len(colors) + 1}")
                    name = base_name
                    suffix = 2

                    while name in colors:
                        name = f"{base_name}_{suffix}"
                        suffix += 1

                    colors[name] = {
                        "rgb": rgb,
                        "lab": lab,
                        "source_image": window_id,
                        "source": "auto_image"
                    }

                    self.fuzzy_manager.create_color_display_frame(
                        parent=target_frame,
                        color_name=name,
                        rgb=rgb,
                        lab=lab,
                        color_checks=self.color_checks,
                        selected=True,
                        on_toggle=update_selected_count
                    )

                    added += 1

                except Exception:
                    continue

            if callable(update_selected_count):
                update_selected_count()

            if added == 0:
                self.custom_warning(
                    "No Colors Added",
                    "Detected colors could not be converted into valid colors.",
                    parent=win
                )

        def run_auto_detection():
            """Run automatic color detection in a background thread."""
            if busy_state["running"]:
                return

            window_id = get_selected_window_id()

            if window_id is None:
                self.custom_warning("No Image Selected", "Select an image first.", parent=win)
                return

            if window_id not in self.images:
                self.custom_warning("Image Not Available", "Selected image is not available.", parent=win)
                return

            set_tool_busy(True)

            current_threshold = float(threshold.get())
            current_min_samples = int(min_samples.get())

            def worker():
                try:
                    detected_colors = self.image_manager.get_fcs_image(
                        self.images[window_id],
                        current_threshold,
                        current_min_samples
                    )

                    def finish_ok():
                        try:
                            add_detected_colors_to_list(detected_colors, window_id)
                        finally:
                            set_tool_busy(False)

                    win.after(0, finish_ok)

                except Exception as e:
                    def finish_error():
                        try:
                            self.custom_warning(
                                "Error",
                                f"Could not detect colors from image: {e}",
                                parent=win
                            )
                        finally:
                            set_tool_busy(False)

                    win.after(0, finish_error)

            threading.Thread(target=worker, daemon=True).start()

        detect_button = ttk.Button(
            auto_controls,
            text="Detect and Add Colors",
            command=run_auto_detection,
            style="ImageTool.CompactPrimary.TButton"
        )
        detect_button.pack(side="right")

        # ------------------------------------------------------------------
        # Behavior
        # ------------------------------------------------------------------
        def get_selected_window_id():
            current_name = selected_image_var.get()
            if current_name in image_names:
                return image_ids[image_names.index(current_name)]
            return image_ids[0] if image_ids else None

        def load_selected_image(*_):
            window_id = get_selected_window_id()
            if window_id is None:
                return
            self._manual_load_image_from_window_id(window_id)

        def on_mode_change(*_):
            mode = mode_var.get().strip().lower()

            if mode == "manual":
                tip_var.set("Manual: click for a pixel or drag a rectangle to sample an average color.")
                auto_card.pack_forget()
                manual_card.pack(fill="x", pady=(0, 10))
            else:
                tip_var.set("Automatic: press 'Detect and Add Colors' to add detected colors to the list.")
                manual_card.pack_forget()
                auto_card.pack(fill="x")

        image_combo.bind("<<ComboboxSelected>>", load_selected_image)

        mode_var.trace_add("write", on_mode_change)
        mode_combo.bind("<<ComboboxSelected>>", on_mode_change)

        self._manual_img_canvas.bind("<ButtonPress-1>", self._manual_on_mouse_down)
        self._manual_img_canvas.bind("<B1-Motion>", self._manual_on_mouse_drag)
        self._manual_img_canvas.bind("<ButtonRelease-1>", self._manual_on_mouse_up)

        def on_close():
            if busy_state.get("running", False):
                return

            try:
                if dock_bind_id is not None and parent_popup.winfo_exists():
                    parent_popup.unbind("<Configure>", dock_bind_id)
            except Exception:
                pass

            self._image_creation_tool_win = None
            self._manual_picker_win = None

            try:
                win.destroy()
            except Exception:
                pass

        win.protocol("WM_DELETE_WINDOW", on_close)

        load_selected_image()
        on_mode_change()



    def _image_creation_add_picked_color(self, colors, target_frame, update_selected_count=None):
        """Add the currently sampled image color to the main color list with an automatic name."""
        if target_frame is None or not target_frame.winfo_exists():
            self.custom_warning(message="The color list window is closed. Open it again to add colors.")
            return

        if not hasattr(self, "_picked_rgb") or not hasattr(self, "_picked_lab"):
            self.custom_warning(message="Pick a color from the image first.")
            return

        if self._picked_rgb is None or self._picked_lab is None:
            self.custom_warning(message="Pick a color from the image first.")
            return

        # Automatic unique name
        base_name = "Image Color"
        index = len(colors) + 1
        name = f"{base_name} {index}"

        while name in colors:
            index += 1
            name = f"{base_name} {index}"

        try:
            lab = (
                float(self._picked_lab[0]),
                float(self._picked_lab[1]),
                float(self._picked_lab[2])
            )

            rgb = tuple(int(v) for v in self._picked_rgb[:3])

        except Exception:
            self.custom_warning("Invalid Color", "The selected color could not be converted correctly.")
            return

        colors[name] = {
            "rgb": rgb,
            "lab": lab,
            "source_image": getattr(self, "_manual_image_id", None),
            "source": "manual_image"
        }

        self.fuzzy_manager.create_color_display_frame(
            parent=target_frame,
            color_name=name,
            rgb=rgb,
            lab=lab,
            color_checks=self.color_checks,
            selected=True,
            on_toggle=update_selected_count
        )

        if callable(update_selected_count):
            update_selected_count()



    def _image_creation_detect_and_add_colors(
        self,
        colors,
        target_frame,
        update_selected_count=None,
        threshold=0.5,
        min_samples=160
    ):
        """Detect colors from the selected image and add them directly to the main color list."""
        if target_frame is None or not target_frame.winfo_exists():
            self.custom_warning(message="The color list window is closed. Open it again to add colors.")
            return

        window_id = getattr(self, "_manual_image_id", None)

        if not window_id:
            self.custom_warning(message="Select an image first.")
            return

        if window_id not in self.images:
            self.custom_warning(message="Selected image is not available.")
            return

        try:
            detected_colors = self.image_manager.get_fcs_image(
                self.images[window_id],
                threshold,
                min_samples
            )
        except Exception as e:
            self.custom_warning("Error", f"Could not detect colors from image: {e}")
            return

        if not detected_colors:
            self.custom_warning(
                "No Colors Detected",
                "No colors were detected with the current threshold."
            )
            return

        added = 0

        for i, item in enumerate(detected_colors):
            try:
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
                            float(lab_value["A"]),
                            float(lab_value["B"])
                        )
                    else:
                        lab_arr = np.array(lab_value, dtype=float).reshape(-1)
                        lab = (
                            float(lab_arr[0]),
                            float(lab_arr[1]),
                            float(lab_arr[2])
                        )
                else:
                    lab = UtilsTools.srgb_to_lab(rgb[0], rgb[1], rgb[2])
                    lab = (
                        float(lab[0]),
                        float(lab[1]),
                        float(lab[2])
                    )

                base_name = item.get("name", f"Detected Color {len(colors) + 1}")
                name = base_name
                suffix = 2

                while name in colors:
                    name = f"{base_name}_{suffix}"
                    suffix += 1

                colors[name] = {
                    "rgb": rgb,
                    "lab": lab,
                    "source_image": window_id,
                    "source": "auto_image"
                }

                self.fuzzy_manager.create_color_display_frame(
                    parent=target_frame,
                    color_name=name,
                    rgb=rgb,
                    lab=lab,
                    color_checks=self.color_checks,
                    selected=True,
                    on_toggle=update_selected_count
                )

                added += 1

            except Exception:
                continue

        if callable(update_selected_count):
            update_selected_count()

        if added == 0:
            self.custom_warning(
                "No Colors Added",
                "Detected colors could not be converted into valid colors."
            )





    def _manual_load_image_from_window_id(self, window_id: str):
        """Load an image from the internal images dict and render it in the picker canvas."""
        if window_id not in self.images:
            self.custom_warning(message="Selected image is not available.")
            return

        self._manual_image_id = window_id
        image = self.images[window_id]

        if isinstance(image, Image.Image):
            pil = image.convert("RGB")
        else:
            pil = Image.fromarray(image).convert("RGB")

        self._manual_pil_full = pil

        cw = int(self._manual_img_canvas["width"])
        ch = int(self._manual_img_canvas["height"])

        img_w, img_h = pil.size
        scale = min(cw / img_w, ch / img_h)

        new_w = max(1, int(img_w * scale))
        new_h = max(1, int(img_h * scale))

        resized = pil.resize((new_w, new_h), Image.Resampling.LANCZOS)

        try:
            resized = ImageEnhance.Sharpness(resized).enhance(1.2)
        except Exception:
            pass

        self._manual_scale = scale
        self._manual_draw_w = new_w
        self._manual_draw_h = new_h
        self._manual_offset_x = (cw - new_w) // 2
        self._manual_offset_y = (ch - new_h) // 2

        self._manual_tk_img = ImageTk.PhotoImage(resized)

        self._manual_img_canvas.delete("all")
        self._manual_img_canvas.configure(bg="white")
        self._manual_img_canvas.create_image(
            self._manual_offset_x,
            self._manual_offset_y,
            anchor="nw",
            image=self._manual_tk_img
        )

        self._manual_dragging = False
        self._manual_drag_start = None
        self._manual_rect_id = None

        self._picked_rgb = None
        self._picked_lab = None

        if hasattr(self, "_picked_rgb_var"):
            self._picked_rgb_var.set("RGB: -")

        if hasattr(self, "_picked_lab_var"):
            self._picked_lab_var.set("LAB: -")

        if hasattr(self, "_picked_preview") and hasattr(self, "_picked_preview_rect"):
            self._picked_preview.itemconfig(self._picked_preview_rect, fill="#d9d9d9")


    def _manual_on_image_click(self, event):
        """Pick the pixel under the cursor, compute LAB, and update the UI preview."""
        if not hasattr(self, "_manual_pil_full") or self._manual_pil_full is None:
            return

        # Map click to the drawn image area inside the canvas
        x = event.x - self._manual_offset_x
        y = event.y - self._manual_offset_y
        if x < 0 or y < 0 or x >= self._manual_draw_w or y >= self._manual_draw_h:
            return

        # Map back to full-resolution coordinates
        full_x = int(x / self._manual_scale)
        full_y = int(y / self._manual_scale)

        full_w, full_h = self._manual_pil_full.size
        full_x = max(0, min(full_w - 1, full_x))
        full_y = max(0, min(full_h - 1, full_y))

        r, g, b = self._manual_pil_full.getpixel((full_x, full_y))
        lab = UtilsTools.srgb_to_lab(r, g, b)

        # Store picked values for later "Add Selected Color"
        self._picked_rgb = (r, g, b)
        self._picked_lab = lab

        # Update UI
        self._picked_rgb_var.set(f"RGB: ({r}, {g}, {b})")
        self._picked_lab_var.set(f"LAB: ({lab[0]:.2f}, {lab[1]:.2f}, {lab[2]:.2f})")

        hex_color = f"#{r:02x}{g:02x}{b:02x}"
        self._picked_preview.itemconfig(self._picked_preview_rect, fill=hex_color)


    def _manual_on_mouse_down(self, event):
        """Start rectangle selection on the preview canvas."""
        if not hasattr(self, "_manual_pil_full") or self._manual_pil_full is None:
            return

        # Start point in canvas coordinates
        self._manual_dragging = True
        self._manual_drag_start = (event.x, event.y)

        # Remove previous rectangle
        if self._manual_rect_id is not None:
            try:
                self._manual_img_canvas.delete(self._manual_rect_id)
            except Exception:
                pass
            self._manual_rect_id = None

        # Create a new rubber-band rectangle
        self._manual_rect_id = self._manual_img_canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline="#ff0000", width=2
        )


    def _manual_on_mouse_drag(self, event):
        """Update rectangle while dragging."""
        if not getattr(self, "_manual_dragging", False):
            return
        if self._manual_rect_id is None:
            return

        x0, y0 = self._manual_drag_start
        x1, y1 = event.x, event.y

        # Update rectangle coordinates
        self._manual_img_canvas.coords(self._manual_rect_id, x0, y0, x1, y1)


    def _manual_on_mouse_up(self, event):
        """Finish selection, compute average color in the selected rectangle (or single pixel)."""
        if not getattr(self, "_manual_dragging", False):
            return
        self._manual_dragging = False

        if not hasattr(self, "_manual_pil_full") or self._manual_pil_full is None:
            return
        if self._manual_drag_start is None:
            return

        x0, y0 = self._manual_drag_start
        x1, y1 = event.x, event.y

        # Normalize rect in canvas coordinates
        left = min(x0, x1)
        right = max(x0, x1)
        top = min(y0, y1)
        bottom = max(y0, y1)

        # If selection is tiny -> treat as click
        if (right - left) < 3 and (bottom - top) < 3:
            # Reuse your existing single-pixel logic
            fake = type("E", (), {"x": event.x, "y": event.y})
            self._manual_on_image_click(fake)
            # Remove rectangle
            if self._manual_rect_id is not None:
                self._manual_img_canvas.delete(self._manual_rect_id)
                self._manual_rect_id = None
            return

        # Map canvas rectangle to drawn image coords
        left_d = left - self._manual_offset_x
        right_d = right - self._manual_offset_x
        top_d = top - self._manual_offset_y
        bottom_d = bottom - self._manual_offset_y

        # Clip to drawn image bounds
        left_d = max(0, min(self._manual_draw_w, left_d))
        right_d = max(0, min(self._manual_draw_w, right_d))
        top_d = max(0, min(self._manual_draw_h, top_d))
        bottom_d = max(0, min(self._manual_draw_h, bottom_d))

        if right_d <= left_d or bottom_d <= top_d:
            return

        # Map to full-resolution coords
        full_left = int(left_d / self._manual_scale)
        full_right = int(right_d / self._manual_scale)
        full_top = int(top_d / self._manual_scale)
        full_bottom = int(bottom_d / self._manual_scale)

        full_w, full_h = self._manual_pil_full.size
        full_left = max(0, min(full_w - 1, full_left))
        full_right = max(0, min(full_w, full_right))
        full_top = max(0, min(full_h - 1, full_top))
        full_bottom = max(0, min(full_h, full_bottom))

        if full_right <= full_left or full_bottom <= full_top:
            return

        # Crop and compute mean RGB
        crop = self._manual_pil_full.crop((full_left, full_top, full_right, full_bottom))
        arr = np.asarray(crop, dtype=np.float32)  # (h,w,3)
        mean_rgb = arr.reshape(-1, 3).mean(axis=0)

        r = int(round(mean_rgb[0]))
        g = int(round(mean_rgb[1]))
        b = int(round(mean_rgb[2]))

        lab = UtilsTools.srgb_to_lab(r, g, b)

        # Store picked values for "Add Selected Color"
        self._picked_rgb = (r, g, b)
        self._picked_lab = lab

        # Update UI
        self._picked_rgb_var.set(f"RGB (avg): ({r}, {g}, {b})")
        self._picked_lab_var.set(f"LAB (avg): ({lab[0]:.2f}, {lab[1]:.2f}, {lab[2]:.2f})")

        hex_color = f"#{r:02x}{g:02x}{b:02x}"
        self._picked_preview.itemconfig(self._picked_preview_rect, fill=hex_color)

        # Optional: keep rectangle visible or remove it
        # If you prefer to remove it after selection:
        # self._manual_img_canvas.delete(self._manual_rect_id)
        # self._manual_rect_id = None





















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

        self.add_button = tk.Button(
            self.Canvas1,
            text="Interactive\nFigure",
            font=("Segoe UI", 9, "bold"),
            justify="center",
            bg="#e8f0fe",
            fg="#1f4e8c",
            activebackground="#d7e5fb",
            activeforeground="#1f4e8c",
            relief="raised",
            bd=1,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._on_add_graph_current,
        )
        self.add_button.place(relx=0.965, rely=0.05, anchor="ne")


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

        self.fig_3d = None
        self.ax_3d = None


    def _reset_3d_view_state(self):
        """
        Reset cached 3D view state.

        Call this when a new color space is loaded, because the plot structure
        and the available colors may have changed completely.
        """
        self._last_selected_options = None
        self._last_color_button_signature = None
        self._last_plot_signature = None

        if hasattr(self, "filtered_points"):
            self.filtered_points = {}

        if self.graph_widget:
            try:
                self.graph_widget.get_tk_widget().destroy()
            except Exception:
                pass
            self.graph_widget = None

        if hasattr(self, "_interactive_button") and self._interactive_button is not None:
            try:
                self._interactive_button.destroy()
            except Exception:
                pass
            self._interactive_button = None


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

        VisualManager.plot_combined_3D(
            self.ax_3d,
            self.file_base_name,
            self.selected_centroids,
            self.selected_core,
            self.selected_alpha,
            self.selected_support,
            self.volume_limits,
            self.hex_color,
            selected_options,
            self.filtered_points,
        )

        # Softer and smaller title
        display_name = str(self.file_base_name).replace("_", " ")
        self.ax_3d.set_title(
            display_name,
            fontsize=13,
            fontweight="semibold",
            pad=10
        )

        self.graph_widget.draw()

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

        if hasattr(self, "_interactive_button") and self._interactive_button is not None:
            try:
                self._interactive_button.destroy()
            except Exception:
                pass
            self._interactive_button = None

        self._last_plot_signature = None


    def on_add_graph(self, selected_options):
        """
        Generate the interactive Plotly figure and open it in the default browser.
        """
        fig = VisualManager.plot_more_combined_3D(
            filename=self.file_base_name,
            color_data=self.selected_centroids,
            core=self.selected_core,
            alpha=self.selected_alpha,
            support=self.selected_support,
            volume_limits=self.volume_limits,
            hex_color=self.hex_color,
            selected_options=selected_options,
            filtered_points=self.filtered_points,
        )

        if hasattr(self, "lab_value_frame"):
            self.lab_value_frame.lift()

        self._open_plotly_figure_in_browser(
            fig,
            filename_prefix="pyfcs_3d_plot"
        )


    def select_all_color(self):
        """
        Select all available colors and refresh the 3D model only if needed.
        """
        if not self.COLOR_SPACE:
            return

        self.selected_centroids = self.color_data
        self.selected_hex_color = self.hex_color
        self.selected_alpha = self.prototypes
        self.selected_core = self.cores
        self.selected_support = self.supports

        for _, var in self.selected_colors.items():
            var.set(True)

        self.on_option_select()


    def deselect_all_color(self):
        """
        Deselect all available colors and refresh the 3D model.
        """
        if not self.COLOR_SPACE:
            return

        self.selected_centroids = {}
        self.selected_hex_color = {}
        self.selected_alpha = []
        self.selected_core = []
        self.selected_support = []

        for _, var in self.selected_colors.items():
            var.set(False)

        self.on_option_select()


    def select_color(self):
        """
        Update the current color selection and refresh the 3D model.
        """
        selected_centroids = {}
        selected_indices = []
        color_keys = list(self.color_data.keys())

        for color_name, selected in self.selected_colors.items():
            if selected.get() and color_name in self.color_data:
                selected_centroids[color_name] = self.color_data[color_name]
                selected_indices.append(color_keys.index(color_name))

        self.selected_centroids = selected_centroids

        if selected_indices:
            self.selected_hex_color = {
                hex_color_key: lab_value
                for index in selected_indices
                for hex_color_key, lab_value in self.hex_color.items()
                if np.array_equal(lab_value, self.color_data[color_keys[index]]["positive_prototype"])
            }
            self.selected_alpha = [self.prototypes[i] for i in selected_indices]
            self.selected_core = [self.cores[i] for i in selected_indices]
            self.selected_support = [self.supports[i] for i in selected_indices]
        else:
            self.selected_hex_color = {}
            self.selected_alpha = []
            self.selected_core = []
            self.selected_support = []

        self.on_option_select()


    def display_color_buttons(self, colors):
        """
        Display color selection checkboxes.

        Rebuild the button list only when the available color set changes.
        Preserve previous selection states whenever possible.
        """
        color_signature = tuple(colors)

        if color_signature == getattr(self, "_last_color_button_signature", None):
            return

        previous_selected_colors = {
            color: var.get() for color, var in getattr(self, "selected_colors", {}).items()
        } if hasattr(self, "selected_colors") else {}

        if hasattr(self, "color_buttons"):
            for button in self.color_buttons:
                try:
                    button.destroy()
                except Exception:
                    pass

        self.selected_colors = {}
        self.color_buttons = []

        CARD_BG = "#ffffff"
        TEXT = "#1f2937"
        MUTED = "#6b7280"

        for color in colors:
            is_selected = previous_selected_colors.get(color, True)
            self.selected_colors[color] = tk.BooleanVar(value=is_selected)

            row = tk.Frame(
                self.inner_frame,
                bg=CARD_BG,
                bd=0,
                relief="flat"
            )
            row.pack(fill="x", anchor="w", pady=2, padx=4)

            button = tk.Checkbutton(
                row,
                text=color,
                variable=self.selected_colors[color],
                bg=CARD_BG,
                fg=TEXT,
                activebackground=CARD_BG,
                activeforeground=TEXT,
                selectcolor=CARD_BG,
                font=("Segoe UI", 10),
                onvalue=True,
                offvalue=False,
                command=self.select_color,
                cursor="hand2",
                bd=0,
                highlightthickness=0,
                anchor="w"
            )
            button.pack(fill="x", anchor="w", padx=4, pady=1)

            self.color_buttons.append(row)

        self.scrollable_canvas.update_idletasks()
        self.scrollable_canvas.configure(scrollregion=self.scrollable_canvas.bbox("all"))
        self._last_color_button_signature = color_signature















    # ============================================================================================================================================================
    #  FUNCTIONS DATA
    # ============================================================================================================================================================
    def display_data_window(self):
        """
        Displays the color data in a visually improved scrollable table within the canvas.
        Updates the table with LAB values, editable labels and color previews.
        """
        if hasattr(self, "file_name_entry"):
            self.file_name_entry.delete(0, "end")
            self.file_name_entry.insert(0, getattr(self, "file_base_name", ""))

        # Destroy previous embedded widgets, such as editable label entries
        try:
            for child in self.data_window.winfo_children():
                child.destroy()
        except Exception:
            pass

        self.data_window.delete("all")
        self.data_window.update_idletasks()

        data_source = getattr(self, "edit_color_data", {})

        self.color_matrix = []
        self.hex_color = {}

        # Update header counter
        if hasattr(self, "data_header_title"):
            self.data_header_title.config(text=f"Color Space Data ({len(data_source)})")

        # -------------------------
        # Tooltip management
        # -------------------------
        if hasattr(self, "_data_info_tooltip") and self._data_info_tooltip is not None:
            try:
                self._data_info_tooltip.destroy()
            except Exception:
                pass
            self._data_info_tooltip = None

        def _hide_info_tooltip(event=None):
            if hasattr(self, "_data_info_tooltip") and self._data_info_tooltip is not None:
                try:
                    self._data_info_tooltip.destroy()
                except Exception:
                    pass
                self._data_info_tooltip = None

            try:
                self.data_window.config(cursor="")
            except Exception:
                pass

        def _show_info_tooltip(event, rgb_text, hex_text):
            _hide_info_tooltip()

            try:
                tooltip = tk.Toplevel(self.data_window)
                tooltip.wm_overrideredirect(True)
                tooltip.configure(bg="#fefefe", bd=1, relief="solid")

                x_root = event.x_root + 14
                y_root = event.y_root + 10
                tooltip.geometry(f"+{x_root}+{y_root}")

                tk.Label(
                    tooltip,
                    text=f"HEX: {hex_text.upper()}\nRGB: {rgb_text}",
                    justify="left",
                    anchor="w",
                    bg="#fefefe",
                    fg="#222222",
                    font=("Sans", 9),
                    padx=10,
                    pady=6
                ).pack()

                self._data_info_tooltip = tooltip
                self.data_window.config(cursor="hand2")

            except Exception:
                self._data_info_tooltip = None

        if not data_source:
            if hasattr(self, "data_header_title"):
                self.data_header_title.config(text="Color Space Data (0)")
            self.data_window.configure(scrollregion=(0, 0, 0, 0))
            return

        canvas_width = self.data_window.winfo_width()
        if canvas_width <= 1:
            canvas_width = 760

        # =========================
        # Layout configuration
        # =========================
        col_widths = {
            "L": 70,
            "a": 70,
            "b": 70,
            "Label": 200,
            "Color": 100,
            "Action": 105,
        }

        table_width = sum(col_widths.values())
        x_start = max((canvas_width - table_width) // 2, 24)

        y = 14

        header_height = 38
        row_height = 66
        row_gap = 8

        border_color = "#d0d0d0"
        header_bg = "#f2f2f2"

        # =========================
        # Header row
        # =========================
        self.data_window.create_rectangle(
            x_start,
            y,
            x_start + table_width,
            y + header_height,
            fill=header_bg,
            outline=border_color
        )

        headers = ["L", "a", "b", "Label", "Color", "Action"]

        current_x = x_start

        for header in headers:
            width = col_widths[header]

            self.data_window.create_text(
                current_x + width / 2,
                y + header_height / 2,
                text=header,
                anchor="center",
                font=("Sans", 10, "bold"),
                fill="#222222"
            )

            if header != headers[-1]:
                self.data_window.create_line(
                    current_x + width,
                    y + 8,
                    current_x + width,
                    y + header_height - 8,
                    fill="#d7d7d7"
                )

            current_x += width

        y += header_height + row_gap

        # =========================
        # Editable label helpers
        # =========================
        MAX_LABEL_CHARS = 16

        def _rename_color_label(old_name, requested_name, entry_var=None):
            """Rename a color key in edit_color_data while preserving the current order."""
            old_name = str(old_name).strip()
            new_name = str(requested_name).strip()

            if len(new_name) > MAX_LABEL_CHARS:
                new_name = new_name[:MAX_LABEL_CHARS]

            if not new_name:
                if entry_var is not None:
                    entry_var.set(old_name[:MAX_LABEL_CHARS])

                self.custom_warning(
                    "Invalid Color Name",
                    "Color name cannot be empty.",
                    parent=getattr(self, "root", None)
                )
                return False

            if new_name == old_name:
                if entry_var is not None:
                    entry_var.set(old_name[:MAX_LABEL_CHARS])
                return False

            if new_name in self.edit_color_data:
                if entry_var is not None:
                    entry_var.set(old_name[:MAX_LABEL_CHARS])

                self.custom_warning(
                    "Duplicated Color Name",
                    f"The color '{new_name}' already exists.",
                    parent=getattr(self, "root", None)
                )
                return False

            if old_name not in self.edit_color_data:
                if entry_var is not None:
                    entry_var.set(old_name[:MAX_LABEL_CHARS])
                return False

            # Rebuild dict to preserve row order
            renamed_data = {}

            for key, value in self.edit_color_data.items():
                if key == old_name:
                    renamed_data[new_name] = value
                else:
                    renamed_data[key] = value

            self.edit_color_data = renamed_data

            # Keep related selection/edit references coherent if they exist
            if getattr(self, "selected_color_name", None) == old_name:
                self.selected_color_name = new_name

            if getattr(self, "current_color_to_edit", None) == old_name:
                self.current_color_to_edit = new_name

            self.display_data_window()
            return True

        # =========================
        # Data rows
        # =========================
        for i, (color_name, color_value) in enumerate(data_source.items()):

            if "positive_prototype" in color_value:
                lab = np.array(color_value["positive_prototype"], dtype=float)
            elif "Color" in color_value:
                lab = np.array(color_value["Color"], dtype=float)
            else:
                continue

            if len(lab) < 3:
                continue

            L, A, B = float(lab[0]), float(lab[1]), float(lab[2])

            self.color_matrix.append(color_name)

            row_bg = "#ffffff" if i % 2 == 0 else "#fbfbfb"
            row_top = y
            row_bottom = y + row_height

            self.data_window.create_rectangle(
                x_start,
                row_top,
                x_start + table_width,
                row_bottom,
                fill=row_bg,
                outline="#dddddd"
            )

            current_x = x_start

            # =========================
            # LAB cells
            # =========================
            for value, header in zip([L, A, B], ["L", "a", "b"]):
                width = col_widths[header]

                self.data_window.create_text(
                    current_x + width / 2,
                    row_top + row_height / 2,
                    text=f"{value:.2f}",
                    anchor="center",
                    font=("Consolas", 10),
                    fill="#333333"
                )

                self.data_window.create_line(
                    current_x + width,
                    row_top + 10,
                    current_x + width,
                    row_bottom - 10,
                    fill="#eeeeee"
                )

                current_x += width

            # =========================
            # Editable Label cell
            # =========================
            label_width = col_widths["Label"]

            label_var = tk.StringVar(value=str(color_name)[:MAX_LABEL_CHARS])

            def _validate_label_text(proposed_text):
                try:
                    return len(proposed_text) <= MAX_LABEL_CHARS
                except Exception:
                    return False

            vcmd = (self.data_window.register(_validate_label_text), "%P")

            label_entry = tk.Entry(
                self.data_window,
                textvariable=label_var,
                font=("Sans", 10, "bold"),
                fg="#222222",
                bg=row_bg,
                relief="solid",
                bd=1,
                justify="left",
                validate="key",
                validatecommand=vcmd,
                insertbackground="#222222"
            )

            def _commit_label_change(event=None, old_name=color_name, var=label_var):
                _rename_color_label(old_name, var.get(), entry_var=var)

            label_entry.bind("<Return>", _commit_label_change)
            label_entry.bind("<FocusOut>", _commit_label_change)

            # Pressing Escape restores the original name
            label_entry.bind(
                "<Escape>",
                lambda event, old_name=color_name, var=label_var: var.set(str(old_name)[:MAX_LABEL_CHARS])
            )

            entry_w = label_width - 24
            entry_h = 28

            self.data_window.create_window(
                current_x + 12,
                row_top + row_height / 2,
                window=label_entry,
                width=entry_w,
                height=entry_h,
                anchor="w"
            )

            self.data_window.create_line(
                current_x + label_width,
                row_top + 10,
                current_x + label_width,
                row_bottom - 10,
                fill="#eeeeee"
            )

            current_x += label_width

            # =========================
            # Color preview cell
            # =========================
            color_width = col_widths["Color"]

            try:
                rgb_data = UtilsTools.lab_to_rgb(lab)
                hex_color = UtilsTools.rgb_to_hex(rgb_data)
            except Exception:
                rgb_data = (217, 217, 217)
                hex_color = "#d9d9d9"

            self.hex_color[hex_color] = lab

            swatch_w = 88
            swatch_h = 36

            swatch_x = current_x + (color_width - swatch_w) / 2
            swatch_y = row_top + (row_height - swatch_h) / 2

            self.data_window.create_rectangle(
                swatch_x - 2,
                swatch_y - 2,
                swatch_x + swatch_w + 2,
                swatch_y + swatch_h + 2,
                fill="#e6e6e6",
                outline="#d0d0d0"
            )

            self.data_window.create_rectangle(
                swatch_x,
                swatch_y,
                swatch_x + swatch_w,
                swatch_y + swatch_h,
                fill=hex_color,
                outline="#444444"
            )

            self.data_window.create_line(
                current_x + color_width,
                row_top + 10,
                current_x + color_width,
                row_bottom - 10,
                fill="#eeeeee"
            )

            current_x += color_width

            # =========================
            # Action cell
            # =========================
            action_width = col_widths["Action"]

            info_tag = f"info_{i}"
            delete_tag = f"delete_{i}"

            btn_w = 30
            btn_h = 28
            btn_gap = 10

            total_btns_width = btn_w * 2 + btn_gap
            start_btn_x = current_x + (action_width - total_btns_width) / 2
            btn_y = row_top + (row_height - btn_h) / 2

            # -------------------------
            # Info button, left
            # -------------------------
            info_x = start_btn_x

            self.data_window.create_rectangle(
                info_x,
                btn_y,
                info_x + btn_w,
                btn_y + btn_h,
                fill="#f1f7ff",
                outline="#9bbce3",
                tags=(info_tag,)
            )

            self.data_window.create_text(
                info_x + btn_w / 2,
                btn_y + btn_h / 2,
                text="ⓘ",
                fill="#1f5fa8",
                font=("Sans", 12, "bold"),
                anchor="center",
                tags=(info_tag,)
            )

            rgb_text = f"{rgb_data[0]}, {rgb_data[1]}, {rgb_data[2]}"
            hex_text = hex_color

            self.data_window.tag_bind(
                info_tag,
                "<Enter>",
                lambda event, rgb_text=rgb_text, hex_text=hex_text: _show_info_tooltip(event, rgb_text, hex_text)
            )

            self.data_window.tag_bind(
                info_tag,
                "<Motion>",
                lambda event, rgb_text=rgb_text, hex_text=hex_text: _show_info_tooltip(event, rgb_text, hex_text)
            )

            self.data_window.tag_bind(
                info_tag,
                "<Leave>",
                _hide_info_tooltip
            )

            # -------------------------
            # Delete button, right
            # -------------------------
            del_x = info_x + btn_w + btn_gap

            self.data_window.create_rectangle(
                del_x,
                btn_y,
                del_x + btn_w,
                btn_y + btn_h,
                fill="#fff5f5",
                outline="#d8b0b0",
                tags=(delete_tag,)
            )

            self.data_window.create_text(
                del_x + btn_w / 2,
                btn_y + btn_h / 2,
                text="✕",
                fill="#8a1f1f",
                font=("Sans", 11, "bold"),
                anchor="center",
                tags=(delete_tag,)
            )

            self.data_window.tag_bind(
                delete_tag,
                "<Button-1>",
                lambda event, idx=i: self.remove_color(idx)
            )

            self.data_window.tag_bind(
                delete_tag,
                "<Enter>",
                lambda event: self.data_window.config(cursor="hand2")
            )

            self.data_window.tag_bind(
                delete_tag,
                "<Leave>",
                _hide_info_tooltip
            )

            y += row_height + row_gap

        y += 20

        # Keep horizontal scroll useful when the available area is narrower than the table
        scroll_width = max(canvas_width, x_start + table_width + 24)

        self.data_window.configure(scrollregion=(0, 0, scroll_width, y))

        if not getattr(self, "_data_window_configure_bound", False):
            self.data_window.bind("<Configure>", lambda event: self.display_data_window())
            self._data_window_configure_bound = True



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
            color_entry = self.edit_color_data[color_name]

            if "positive_prototype" in color_entry:
                removed_positive = np.array(color_entry["positive_prototype"])
            elif "Color" in color_entry:
                removed_positive = np.array(color_entry["Color"])
            else:
                return

            for existing_color, data in self.edit_color_data.items():
                if existing_color == color_name:
                    continue

                negatives = data.get("negative_prototypes", [])

                filtered = [
                    prototype for prototype in negatives
                    if not np.array_equal(prototype, removed_positive)
                ]

                data["negative_prototypes"] = np.array(filtered)

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

            positive_prototype = np.array([L, A, B])

            negative_prototypes = []

            for _, data in new_color_data.items():
                if "positive_prototype" in data:
                    negative_prototypes.append(np.array(data["positive_prototype"]))
                elif "Color" in data:
                    negative_prototypes.append(np.array(data["Color"]))

            negative_prototypes = np.array(negative_prototypes)

            new_color_data[clean_name] = {
                "Color": [L, A, B],
                "positive_prototype": positive_prototype,
                "negative_prototypes": negative_prototypes
            }

            for existing_color, data in new_color_data.items():
                if existing_color == clean_name:
                    continue

                existing_negatives = data.get("negative_prototypes", [])

                if len(existing_negatives) > 0:
                    updated_negatives = np.vstack([
                        existing_negatives,
                        positive_prototype
                    ])
                else:
                    updated_negatives = np.array([positive_prototype])

                new_color_data[existing_color]["negative_prototypes"] = updated_negatives

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
            self.data_window.delete("all")
            self.data_window.configure(scrollregion=(0, 0, 0, 0))
            try:
                self.data_window.config(cursor="")
            except Exception:
                pass

        if hasattr(self, "file_name_entry"):
            self.file_name_entry.delete(0, tk.END)

        if hasattr(self, "data_header_title"):
            self.data_header_title.config(text="Color Space Data (0)")

        self.file_base_name = ""
        self.color_matrix = []
        self.hex_color = {}



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

            self.save_fcs(
                output_name,
                new_color_data,
                color_dict=color_dict,
                apply_after_save=True
            )

        except Exception as e:
            self.custom_warning(
                "Error",
                f"Changes could not be prepared: {e}",
                parent=getattr(self, "root", None)
            )


    def delete_color_space(self):
        """Delete the currently loaded color space file (.fcs or .cns) and clear the app state."""
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

        file_path = getattr(self, "file_path", None)
        file_name = os.path.basename(file_path) if file_path else "current color space"

        confirm = messagebox.askyesno(
            "Delete Color Space",
            f"Are you sure you want to permanently delete:\n\n{file_name}\n\nThis action cannot be undone.",
            parent=getattr(self, "root", None)
        )

        if not confirm:
            return

        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)

            self.COLOR_SPACE = None
            self.color_data = {}
            self.edit_color_data = {}
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





























    # ============================================================================================================================================================
    #  FUNCTIONS IMAGE DISPLAY
    # ============================================================================================================================================================
    def save_image(self):
        """Save the currently displayed image for a selected window. If it is a Color Mapping All view, also save a legend image."""
        # Verify we have at least one window to save from
        if not hasattr(self, "load_images_names") or not self.load_images_names:
            self.custom_warning(message="There are currently no images available to save.")
            return
        
        if self._has_any_active_job():
            self.custom_warning(
                "Process Running",
                "Finish or cancel the current color mapping process before opening a new image."
            )
            return

        # Create a popup window for image selection
        popup, listbox = UtilsTools.create_selection_popup(
            parent=self.image_canvas,
            title="Select an Image to Save",
            width=220,
            height=220,
            items=[os.path.basename(filename) for filename in self.load_images_names.values()]
        )

        self.center_popup(popup, 220, 220)

        def _build_legend_pil(labels, colors, box_size=24, padding=10, row_gap=6):
            """Build a standalone legend image (PIL) from labels and RGB uint8 colors."""
            font = ImageFont.load_default()

            # Compute legend width based on longest label
            max_text_w = 0
            for lbl in labels:
                try:
                    bbox = font.getbbox(lbl)
                    max_text_w = max(max_text_w, bbox[2] - bbox[0])
                except Exception:
                    max_text_w = max(max_text_w, len(lbl) * 6)

            width = padding * 2 + box_size + 8 + max_text_w
            height = padding * 2 + len(labels) * (box_size + row_gap) - row_gap

            legend = Image.new("RGB", (max(1, width), max(1, height)), "white")
            draw = ImageDraw.Draw(legend)

            y = padding
            for lbl, col in zip(labels, colors):
                # Color box
                draw.rectangle(
                    [padding, y, padding + box_size, y + box_size],
                    fill=(int(col[0]), int(col[1]), int(col[2])),
                    outline=(0, 0, 0)
                )
                # Text
                draw.text(
                    (padding + box_size + 8, y + 4),
                    lbl,
                    fill="black",
                    font=font
                )
                y += box_size + row_gap

            return legend

        def on_select(event):
            selection = listbox.curselection()
            if not selection:
                return

            index = selection[0]
            window_ids = list(self.load_images_names.keys())
            if index >= len(window_ids):
                self.custom_warning("Error", "Invalid selection index.")
                return

            window_id = window_ids[index]

            save_path = filedialog.asksaveasfilename(
                defaultextension=".png",
                filetypes=[("PNG files", "*.png"), ("JPEG files", "*.jpg"), ("All Files", "*.*")]
            )
            if not save_path:
                return

            try:
                # Always save what is currently displayed (source of truth)
                if not hasattr(self, "display_pil") or window_id not in self.display_pil:
                    self.custom_warning("Error", "No displayed image available to save for this window.")
                    return

                self.display_pil[window_id].save(save_path)

                # If this window has a Color Mapping All legend available, save it separately
                is_mapping_all = (
                    hasattr(self, "prototype_color_sets") and
                    hasattr(self, "current_color_scheme") and
                    window_id in self.prototype_color_sets and
                    window_id in self.current_color_scheme
                )

                legend_path = None
                if is_mapping_all:
                    # Get legend labels + current palette colors
                    labels = [p.label for p in self.prototypes]
                    scheme = self.current_color_scheme[window_id]  # "original" or "alt"
                    colors = self.prototype_color_sets[window_id][scheme]  # list/array of RGB

                    legend_img = _build_legend_pil(labels, colors)

                    base, _ext = os.path.splitext(save_path)
                    legend_path = base + "_legend.png"
                    legend_img.save(legend_path)

                # Feedback
                if legend_path:
                    messagebox.showinfo(
                        "Success",
                        f"Image saved successfully at:\n{save_path}\n\nLegend saved at:\n{legend_path}"
                    )
                else:
                    messagebox.showinfo("Success", f"Image saved successfully at:\n{save_path}")

            except Exception as e:
                self.custom_warning("Error", f"Failed to save image:\n{str(e)}")
            finally:
                popup.destroy()

        listbox.bind("<<ListboxSelect>>", on_select)

    


    def close_all_image(self):
        """
        Closes all floating windows and cleans up associated UI/window resources.

        Important:
        - This does NOT clear the persistent image-result caches.
        - It only removes window-bound state so cached mappings can be reused
        if the same image is opened again during the session.
        """
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
            ):
                if hasattr(self, attr_name):
                    d = getattr(self, attr_name)
                    if isinstance(d, dict) and window_id in d:
                        del d[window_id]

        # Reset leftover per-window dimension dicts if they still exist
        if hasattr(self, "image_dimensions"):
            self.image_dimensions.clear()
        if hasattr(self, "original_image_dimensions"):
            self.original_image_dimensions.clear()


    
    def open_image(self):
        """Allows the user to select an image file and display it in a floating window."""
        if self._has_any_active_job():
            self.custom_warning(
                "Process Running",
                "Finish or cancel the current color mapping process before opening a new image."
            )
            return

        initial_directory = os.path.join(BASE_PATH, 'image_test')

        filetypes = [
            ("Image Files", "*.jpg *.jpeg *.png *.bmp *.gif *.tiff"),
            ("All Files", "*.*")
        ]

        filename = filedialog.askopenfilename(
            title="Select an Image",
            initialdir=initial_directory,
            filetypes=filetypes
        )

        if filename:
            self.create_floating_window(50, 50, filename)



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


    def create_floating_window(self, x, y, filename):
        """
        Creates a floating window with the selected image, a title bar, and a dropdown menu.
        The window is movable (from title bar only), resizable (bottom-right handle),
        and includes options for displaying the original image and color mapping.

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

        # ---------------------------
        # Lazy-init dictionaries
        # ---------------------------
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

        # Persistent caches by image + color space
        if not hasattr(self, "window_image_key"):
            self.window_image_key = {}
        if not hasattr(self, "cm_cache_by_image"):
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

        # ---------------------------
        # Load images
        # ---------------------------
        pil_original = Image.open(filename).convert("RGBA")
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

        img_tk = ImageTk.PhotoImage(pil_resized)
        self.floating_images[window_id] = img_tk
        self.original_images[window_id] = img_tk

        # Window paddings
        PAD_X = 30
        PAD_Y = 50
        TITLE_H = 30
        IMG_TOP_PAD = 40
        IMG_LEFT_PAD = 15
        HANDLE_SIZE = 12

        # Save initial window state
        self.floating_window_state[window_id] = {"x": x, "y": y, "w": new_width, "h": new_height}

        # ---------------------------
        # Create canvas items
        # ---------------------------
        self.image_canvas.create_rectangle(
            x, y, x + new_width + PAD_X, y + new_height + PAD_Y,
            outline="black", fill="white", width=2,
            tags=(window_id, "floating", f"{window_id}_bg")
        )

        self.image_canvas.create_rectangle(
            x, y, x + new_width + PAD_X, y + TITLE_H,
            outline="black", fill="gray",
            tags=(window_id, "floating", f"{window_id}_title")
        )

        self.image_canvas.create_text(
            x + 50, y + 15, anchor="w",
            text=os.path.basename(filename),
            fill="white", font=("Sans", 10),
            tags=(window_id, "floating", f"{window_id}_title_text")
        )

        self.image_canvas.create_rectangle(
            x + new_width + PAD_X - 5, y + 5,
            x + new_width + PAD_X - 25, y + 25,
            outline="black", fill="red",
            tags=(window_id, "floating", f"{window_id}_close_button", f"{window_id}_close_rect")
        )
        self.image_canvas.create_text(
            x + new_width + PAD_X - 15, y + 15,
            text="X", fill="white", font=("Sans", 10, "bold"),
            tags=(window_id, "floating", f"{window_id}_close_button", f"{window_id}_close_text")
        )

        self.image_canvas.create_text(
            x + 15, y + 15, text="▼",
            fill="white", font=("Sans", 12),
            tags=(window_id, "floating", f"{window_id}_arrow_button", f"{window_id}_arrow_text")
        )

        self.image_canvas.create_image(
            x + IMG_LEFT_PAD, y + IMG_TOP_PAD,
            anchor="nw",
            image=self.floating_images[window_id],
            tags=(window_id, "floating", f"{window_id}_click_image", f"{window_id}_img_item")
        )

        self.image_canvas.create_text(
            x + IMG_LEFT_PAD,
            y + IMG_TOP_PAD + new_height + 10,
            anchor="nw",
            text="",
            fill="black",
            font=("Sans", 10),
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

        # ---------------------------
        # Helpers to relayout + resize
        # ---------------------------
        def _relayout(window_id):
            """Update all canvas item positions based on stored floating window state."""
            st = self.floating_window_state[window_id]
            wx, wy, ww, wh = st["x"], st["y"], st["w"], st["h"]

            self.image_canvas.coords(f"{window_id}_bg", wx, wy, wx + ww + PAD_X, wy + wh + PAD_Y)
            self.image_canvas.coords(f"{window_id}_title", wx, wy, wx + ww + PAD_X, wy + TITLE_H)

            self.image_canvas.coords(f"{window_id}_title_text", wx + 50, wy + 15)
            self.image_canvas.coords(f"{window_id}_arrow_text", wx + 15, wy + 15)

            self.image_canvas.coords(
                f"{window_id}_close_rect",
                wx + ww + PAD_X - 5, wy + 5,
                wx + ww + PAD_X - 25, wy + 25
            )
            self.image_canvas.coords(f"{window_id}_close_text", wx + ww + PAD_X - 15, wy + 15)

            self.image_canvas.coords(f"{window_id}_img_item", wx + IMG_LEFT_PAD, wy + IMG_TOP_PAD)

            hx1 = wx + ww + PAD_X - HANDLE_SIZE - 2
            hy1 = wy + wh + PAD_Y - HANDLE_SIZE - 2
            hx2 = wx + ww + PAD_X - 2
            hy2 = wy + wh + PAD_Y - 2
            self.image_canvas.coords(f"{window_id}_resize_handle", hx1, hy1, hx2, hy2)

            self._reposition_proto_options(window_id)

            self.image_canvas.coords(
                f"{window_id}_pct_text",
                wx + IMG_LEFT_PAD,
                wy + IMG_TOP_PAD + wh + 10
            )

            self._reposition_window_loading(window_id)

            if hasattr(self, "_original_sampling_state") and window_id in self._original_sampling_state:
                state = self._original_sampling_state[window_id]
                state["img_x"] = wx + IMG_LEFT_PAD
                state["img_y"] = wy + IMG_TOP_PAD
                state["draw_w"] = ww
                state["draw_h"] = wh

            self._focus_floating_window(window_id)

        def _update_image_to_size(window_id, target_w, target_h):
            """
            Resize the displayed image to fit target_w/target_h while preserving aspect ratio.
            """
            pil_original = self.pil_images_original[window_id]
            ow, oh = pil_original.size

            scale = min(target_w / ow, target_h / oh)
            new_w = max(30, int(ow * scale))
            new_h = max(30, int(oh * scale))

            pil_resized = pil_original.resize((new_w, new_h), Image.Resampling.LANCZOS)
            self.images[window_id] = pil_resized
            self.image_dimensions[window_id] = (new_w, new_h)

            img_tk = ImageTk.PhotoImage(pil_resized)
            self.floating_images[window_id] = img_tk
            self.display_pil[window_id] = pil_resized

            self.image_canvas.itemconfig(f"{window_id}_img_item", image=self.floating_images[window_id])

            self.floating_window_state[window_id]["w"] = new_w
            self.floating_window_state[window_id]["h"] = new_h
            _relayout(window_id)

        # ---------------------------
        # Menu action wrappers
        # ---------------------------
        def _show_original_image_action():
            try:
                self._clear_original_selection_rectangle(window_id)
            except Exception:
                pass
            self.show_original_image(window_id)

        def _color_mapping_action():
            try:
                self._clear_original_selection_rectangle(window_id)
            except Exception:
                pass
            self.color_mapping(window_id)

        def _color_mapping_all_action():
            try:
                self._clear_original_selection_rectangle(window_id)
            except Exception:
                pass
            self.color_mapping_all(window_id)

        # ---------------------------
        # Close window
        # ---------------------------
        def close_window(event):
            """Close the floating window and remove all associated data and canvas items."""

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
            ):
                if hasattr(self, attr_name):
                    d = getattr(self, attr_name)
                    if isinstance(d, dict) and window_id in d:
                        del d[window_id]

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

        # ---------------------------
        # Dropdown menu
        # ---------------------------
        def show_menu_image(event):
            """Display the context menu with options for the floating window."""
            if self._has_active_job(window_id):
                return "break"

            locked_until_original = getattr(self, "mapping_locked_until_original", {}).get(window_id, False)
            mapping_enabled = self.CAN_APPLY_MAPPING[window_id] and not locked_until_original

            menu = Menu(self.root, tearoff=0)
            menu.add_command(
                label="Original Image",
                state=NORMAL if self.SHOW_ORIGINAL[window_id] else DISABLED,
                command=_show_original_image_action
            )
            menu.add_separator()
            menu.add_command(
                label="Color Mapping",
                state=NORMAL if mapping_enabled else DISABLED,
                command=_color_mapping_action
            )
            menu.add_separator()
            menu.add_command(
                label="Color Mapping All",
                state=NORMAL if mapping_enabled else DISABLED,
                command=_color_mapping_all_action
            )
            menu.post(event.x_root, event.y_root)
            return "break"

        # ---------------------------
        # Move window
        # ---------------------------
        def start_move(event):
            if self._has_active_job(window_id):
                return "break"

            self._focus_floating_window(window_id)

            try:
                self._clear_original_selection_rectangle(window_id)
            except Exception:
                pass

            self.last_x, self.last_y = event.x, event.y

        def move_window(event):
            if self._has_active_job(window_id):
                return "break"

            self._focus_floating_window(window_id)

            dx, dy = event.x - self.last_x, event.y - self.last_y
            st = self.floating_window_state[window_id]
            st["x"] += dx
            st["y"] += dy

            _relayout(window_id)

            self.last_x, self.last_y = event.x, event.y
            return "break"

        # ---------------------------
        # Resize window
        # ---------------------------
        def start_resize(event):
            if self._has_active_job(window_id):
                return "break"

            try:
                self._clear_original_selection_rectangle(window_id)
            except Exception:
                pass

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

            _update_image_to_size(window_id, desired_w, desired_h)
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

        # ---------------------------
        # Pixel picking
        # ---------------------------
        def get_pixel_value(event, window_id=window_id):
            if self._has_active_job(window_id):
                return "break"

            pil_original = self.pil_images_original[window_id]
            ow, oh = pil_original.size

            resized_w, resized_h = self.image_dimensions[window_id]
            if resized_w <= 0 or resized_h <= 0:
                return "break"

            abs_x = self.image_canvas.canvasx(event.x)
            abs_y = self.image_canvas.canvasy(event.y)

            st = self.floating_window_state[window_id]
            img_left = st["x"] + IMG_LEFT_PAD
            img_top = st["y"] + IMG_TOP_PAD

            relative_x = abs_x - img_left
            relative_y = abs_y - img_top

            if not (0 <= relative_x < resized_w and 0 <= relative_y < resized_h):
                return "break"

            scale_x = ow / resized_w
            scale_y = oh / resized_h

            x_original = int(relative_x * scale_x)
            y_original = int(relative_y * scale_y)

            pixel_value = pil_original.getpixel((x_original, y_original))

            # If image has transparency, ignore fully transparent pixels
            if len(pixel_value) == 4:
                r, g, b, a = pixel_value

                if a == 0:
                    return "break"

                pixel_rgb = (r, g, b)
            else:
                pixel_rgb = pixel_value

            pixel_rgb_np = np.array([[pixel_rgb]], dtype=np.uint8)
            pixel_lab = color.rgb2lab(pixel_rgb_np)[0][0]

            if self.COLOR_SPACE:
                self.display_pixel_value(x_original, y_original, pixel_lab, is_average=False)

            return "break"

        if not hasattr(self, "_pixel_click_callbacks"):
            self._pixel_click_callbacks = {}
        self._pixel_click_callbacks[window_id] = get_pixel_value

        # ---------------------------
        # Bindings
        # ---------------------------
        self.image_canvas.tag_bind(f"{window_id}_title", "<Button-1>", start_move)
        self.image_canvas.tag_bind(f"{window_id}_title", "<B1-Motion>", move_window)
        self.image_canvas.tag_bind(f"{window_id}_title_text", "<Button-1>", start_move)
        self.image_canvas.tag_bind(f"{window_id}_title_text", "<B1-Motion>", move_window)

        self.image_canvas.tag_bind(f"{window_id}_close_button", "<Button-1>", close_window)
        self.image_canvas.tag_bind(f"{window_id}_click_image", "<Button-1>", get_pixel_value)
        self.image_canvas.tag_bind(f"{window_id}_arrow_button", "<Button-1>", show_menu_image)

        self.image_canvas.tag_bind(f"{window_id}_resize_handle", "<Button-1>", start_resize)
        self.image_canvas.tag_bind(f"{window_id}_resize_handle", "<B1-Motion>", do_resize)
        self.image_canvas.tag_bind(f"{window_id}_resize_handle", "<ButtonRelease-1>", end_resize)

        _relayout(window_id)

        try:
            self._enable_original_rectangle_sampling(
                window_id=window_id,
                target_w=new_width,
                target_h=new_height
            )
        except Exception as e:
            print(f"Warning enabling original rectangle sampling for {window_id}: {e}")

        self._focus_floating_window(window_id)





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
        """Returns True if the window/job is no longer valid."""
        if cancel_event.is_set():
            return True
        if not self._window_exists(window_id):
            return True
        if not self._is_current_job(window_id, job_id):
            return True
        return False



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
                def _ui_error():
                    self.custom_warning("Process Error", f"Unexpected error: {e}")
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
        IMG_LEFT_PAD = 15
        IMG_TOP_PAD = 40

        panel_w = min(170, max(140, ww - 20))
        panel_h = 95

        panel_x = wx + IMG_LEFT_PAD + max(0, (ww - panel_w) // 2)
        panel_y = wy + IMG_TOP_PAD + max(0, (wh - panel_h) // 2)

        tags = (f"{window_id}_loading", "loading")

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
            tags=(f"{window_id}_loading", "loading", f"{window_id}_loading_progress")
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
            tags=(f"{window_id}_loading", "loading", f"{window_id}_loading_cancel")
        )

        cancel_txt = self.image_canvas.create_text(
            (btn_x1 + btn_x2) / 2,
            (btn_y1 + btn_y2) / 2,
            text="Cancel",
            fill="black",
            font=("Sans", 10),
            tags=(f"{window_id}_loading", "loading", f"{window_id}_loading_cancel")
        )

        # Bind cancel click
        self.image_canvas.tag_bind(
            f"{window_id}_loading_cancel",
            "<Button-1>",
            lambda event: self._cancel_window_job(window_id)
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

        IMG_LEFT_PAD = 15
        IMG_TOP_PAD = 40

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

        for info in self.image_jobs.values():
            th = info.get("thread")
            cancel_event = info.get("cancel_event")
            if th is not None and th.is_alive() and cancel_event is not None and not cancel_event.is_set():
                return True
        return False



    def _reposition_proto_options(self, window_id):
        """Repositions the legend/prototype options panel associated with a floating window."""
        if not hasattr(self, "proto_options") or window_id not in self.proto_options:
            return

        info = self.proto_options[window_id]
        if not isinstance(info, dict):
            return

        frame = info.get("frame")
        canvas_item = info.get("canvas_item")

        if not frame or not canvas_item:
            return

        if not frame.winfo_exists():
            return

        if not hasattr(self, "floating_window_state") or window_id not in self.floating_window_state:
            return

        st = self.floating_window_state[window_id]
        wx, wy, ww, wh = st["x"], st["y"], st["w"], st["h"]

        PAD_X = 30

        frame_x = wx + ww + PAD_X + 10
        frame_y = wy

        canvas_width = self.image_canvas.winfo_width()
        canvas_height = self.image_canvas.winfo_height()

        desired_w = frame.winfo_width() if frame.winfo_width() > 1 else 150
        desired_h = frame.winfo_height() if frame.winfo_height() > 1 else min(300, wh)

        if frame_x + desired_w > canvas_width:
            frame_x = max(0, canvas_width - desired_w)
        if frame_y + desired_h > canvas_height:
            frame_y = max(0, canvas_height - desired_h)

        try:
            self.image_canvas.coords(canvas_item, frame_x, frame_y)
            self.image_canvas.itemconfigure(canvas_item, width=desired_w, height=desired_h)
        except Exception:
            pass


    def _focus_floating_window(self, window_id):
        """
        Bring one floating image window to the front while keeping auxiliary
        legend/prototype panels behind the active image.

        Loading panels are always kept above all floating windows so a running
        process remains visible even if other windows are moved or focused.
        """
        try:
            # First, send all legend panels behind floating windows
            if hasattr(self, "proto_options"):
                for other_window_id, info in self.proto_options.items():
                    if not isinstance(info, dict):
                        continue

                    canvas_item = info.get("canvas_item")
                    if canvas_item:
                        try:
                            self.image_canvas.tag_lower(canvas_item)
                        except Exception:
                            pass

                    try:
                        self.image_canvas.tag_lower(f"{other_window_id}_legend")
                    except Exception:
                        pass

            # Raise the whole floating window group
            try:
                self.image_canvas.tag_raise(window_id)
            except Exception:
                pass

            # Raise specific items explicitly to guarantee order inside the window
            for tag in (
                f"{window_id}_bg",
                f"{window_id}_title",
                f"{window_id}_title_text",
                f"{window_id}_img_item",
                f"{window_id}_click_image",
                f"{window_id}_pct_text",
                f"{window_id}_close_button",
                f"{window_id}_close_rect",
                f"{window_id}_close_text",
                f"{window_id}_arrow_button",
                f"{window_id}_arrow_text",
                f"{window_id}_resize_handle",
                f"{window_id}_selection_rect",
            ):
                try:
                    self.image_canvas.tag_raise(tag)
                except Exception:
                    pass

            # Finally, keep ALL loading panels above everything else
            self._raise_all_loading_panels()

        except Exception:
            pass


































    # ============================================================================================================================================================
    #  FUNCTIONS IMAGE UTILS 
    # ============================================================================================================================================================
    def _destroy_proto_options(self, window_id):
        """Destroy and unregister the legend/prototype options panel for one floating image."""
        self.proto_options = getattr(self, "proto_options", {})
        info = self.proto_options.pop(window_id, None)

        if not isinstance(info, dict):
            return

        canvas_item = info.get("canvas_item")
        frame = info.get("frame")

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



    def color_mapping(self, window_id):
        """Displays the prototype coverage mapping for a selected prototype."""
        # Check if the floating window exists
        items = self.image_canvas.find_withtag(window_id)
        if not items:
            self.custom_warning("No Window", f"No floating window found with id {window_id}")
            return

        if getattr(self, "mapping_locked_until_original", {}).get(window_id, False):
            self.custom_warning(
                "Restore Original Image",
                "This image belongs to a previous Color Space. Press Original before applying Color Mapping."
            )
            return

        if not hasattr(self, "window_mapping_mode"):
            self.window_mapping_mode = {}

        self.window_mapping_mode[window_id] = "single"

        # Disable original-image rectangle sampling because the view is no longer the original image
        try:
            self._disable_original_rectangle_sampling(window_id)
        except Exception:
            pass

        # Disable resizing by removing the resize handle and its bindings
        try:
            self.image_canvas.delete(f"{window_id}_resize_handle")
            self.image_canvas.tag_unbind(f"{window_id}_resize_handle", "<Button-1>")
            self.image_canvas.tag_unbind(f"{window_id}_resize_handle", "<B1-Motion>")
            self.image_canvas.tag_unbind(f"{window_id}_resize_handle", "<ButtonRelease-1>")
        except Exception:
            pass

        self.CAN_APPLY_MAPPING[window_id] = False
        self.SHOW_ORIGINAL[window_id] = True

        if not hasattr(self, "proto_options"):
            self.proto_options = {}

        # Safely delete any previous legend/options frame for this window
        if window_id in self.proto_options:
            info = self.proto_options.get(window_id)
            if isinstance(info, dict):
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

        # -----------------------------
        # Create legend frame
        # -----------------------------
        proto_options = tk.Frame(self.image_canvas, bg="white", relief="solid", bd=1)

        canvas = tk.Canvas(proto_options, bg="white", highlightthickness=0)
        v_scroll = tk.Scrollbar(proto_options, orient=tk.VERTICAL, command=canvas.yview)
        h_scroll = tk.Scrollbar(proto_options, orient=tk.HORIZONTAL, command=canvas.xview)

        canvas.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        canvas.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")

        inner_frame = tk.Frame(canvas, bg="white")
        canvas.create_window((0, 0), window=inner_frame, anchor="nw", tags="inner")

        if not hasattr(self, "current_protos"):
            self.current_protos = {}
        default_proto = self.color_matrix[0] if self.color_matrix else ""
        self.current_protos[window_id] = tk.StringVar(value=default_proto)

        for color in self.color_matrix:
            rb = tk.Radiobutton(
                inner_frame,
                text=color,
                variable=self.current_protos[window_id],
                value=color,
                bg="white",
                anchor="w",
                font=("Sans", 10),
                relief="flat",
                command=lambda: self.get_proto_percentage(window_id)
            )
            rb.pack(fill="x", padx=5, pady=2)

        def resize_inner(event):
            """Keep the inner frame width synchronized with the outer canvas width."""
            canvas.itemconfig("inner", width=event.width)

        canvas.bind("<Configure>", resize_inner)

        def on_frame_configure(event):
            """Update the scroll region after the inner frame changes size."""
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner_frame.bind("<Configure>", lambda e: canvas.after_idle(on_frame_configure, e))

        # Mouse wheel scrolling
        def bind_scroll_events(canvas):
            def _on_mousewheel(event):
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

            def _bind_mousewheel(event):
                canvas.bind_all("<MouseWheel>", _on_mousewheel)

            def _unbind_mousewheel(event):
                canvas.unbind_all("<MouseWheel>")

            canvas.bind("<Enter>", _bind_mousewheel)
            canvas.bind("<Leave>", _unbind_mousewheel)

        bind_scroll_events(canvas)

        inner_frame.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

        proto_options.grid_rowconfigure(0, weight=1)
        proto_options.grid_columnconfigure(0, weight=1)

        # -----------------------------
        # Position legend using create_window
        # -----------------------------
        x1, y1, x2, y2 = self.image_canvas.bbox(items[0])
        frame_x = x2 + 10
        frame_y = y1
        img_h = (y2 - y1)

        desired_w = 150
        desired_h = min(300, img_h)

        legend_item = self.image_canvas.create_window(
            frame_x, frame_y,
            window=proto_options,
            anchor="nw",
            width=desired_w,
            height=desired_h,
            tags=(f"{window_id}_legend", "legend")
        )

        # Store structured legend info
        self.proto_options[window_id] = {
            "frame": proto_options,
            "canvas_item": legend_item
        }



    def get_proto_percentage(self, window_id):
        """
        Compute/display the prototype coverage mapping for the currently selected prototype.

        UI/job/cache orchestration stays in the main class.
        Image/membership computation lives in ImageManager.
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

        selected_proto = self.current_protos[window_id].get()
        if selected_proto not in self.color_matrix:
            self.custom_warning("Error", "Selected prototype is not available in the current Color Space.")
            return

        pos = self.color_matrix.index(selected_proto)

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

                source_img = self.images[window_id]
                w, h = source_img.size

                valid_mask = UtilsTools._get_alpha_mask_from_pil(source_img)
                processing_img = UtilsTools._pil_rgb_for_processing(source_img)

                cache_key = (pos, w, h)
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
                    if not self._is_current_job(window_id, job_id):
                        return
                    if not self._window_exists(window_id):
                        return

                    self.display_color_mapping(grayscale_image_array, window_id)
                    self.image_canvas.itemconfig(
                        f"{window_id}_pct_text",
                        text=f"{selected_proto}: {pct:.2f}%"
                    )
                    self.image_canvas.tag_raise(f"{window_id}_pct_text")

                self.image_canvas.after(0, _ui)

            except RuntimeError as e:
                if str(e) != "__JOB_CANCELLED__":
                    self.image_canvas.after(0, lambda: self.custom_warning("Error", f"Error in run_process: {e}"))
            except Exception as e:
                self.image_canvas.after(0, lambda: self.custom_warning("Error", f"Error in run_process: {e}"))

        job_id = self._start_window_job(window_id, "proto_percentage", run_process)
        if job_id is not None:
            self._show_window_loading(window_id, "Color Mapping...")



    def display_color_mapping(self, grayscale_image_array, window_id):
        """Displays the generated grayscale image in the graphical interface, preserving transparency."""
        try:
            try:
                self._disable_original_rectangle_sampling(window_id)
            except Exception:
                pass

            self.modified_image[window_id] = grayscale_image_array

            # Get alpha mask from the current source image
            source_img = self.images.get(window_id)
            if source_img is not None:
                valid_mask = UtilsTools._get_alpha_mask_from_pil(source_img)
            else:
                valid_mask = np.ones(grayscale_image_array.shape[:2], dtype=bool)

            # Convert numpy array to PIL image with transparency
            if grayscale_image_array.ndim == 2:
                rgba_array = UtilsTools._apply_alpha_to_gray_array(grayscale_image_array, valid_mask)
                grayscale_image = Image.fromarray(rgba_array.astype(np.uint8), mode="RGBA")
            else:
                # If the returned image is RGB, preserve transparency too
                rgba_array = UtilsTools._apply_alpha_to_rgb_array(grayscale_image_array, valid_mask)
                grayscale_image = Image.fromarray(rgba_array.astype(np.uint8), mode="RGBA")

            # Resize only for display
            new_width, new_height = self.image_dimensions[window_id]
            grayscale_image_display = grayscale_image.resize(
                (new_width, new_height),
                Image.Resampling.LANCZOS
            )

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

            if hasattr(self, "mapping_locked_until_original"):
                self.mapping_locked_until_original.pop(window_id, None)

            # Hide percentage text when showing original image
            try:
                self.image_canvas.itemconfig(f"{window_id}_pct_text", text="")
            except Exception:
                pass

            # Destroy proto_options if it exists to keep the UI consistent
            if hasattr(self, "proto_options") and window_id in self.proto_options:
                try:
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
                except Exception as e:
                    self.custom_warning("Window Error", f"Error trying to destroy the proto_options window: {e}")
                    return

            # Ensure we have the original PIL image stored
            if not hasattr(self, "pil_images_original") or window_id not in self.pil_images_original:
                self.custom_warning("Not Original Image", f"Original PIL image not found for window_id: {window_id}")
                return

            pil_original = self.pil_images_original[window_id]

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

            # Re-enable resize handle
            try:
                if not hasattr(self, "floating_window_state") or window_id not in self.floating_window_state:
                    return

                st = self.floating_window_state[window_id]
                wx, wy = st["x"], st["y"]

                # Synchronize stored size with the actual displayed size
                st["w"], st["h"] = target_w, target_h
                ww, wh = st["w"], st["h"]

                PAD_X = 30
                PAD_Y = 50
                HANDLE_SIZE = 12

                existing = self.image_canvas.find_withtag(f"{window_id}_resize_handle")

                hx1 = wx + ww + PAD_X - HANDLE_SIZE - 2
                hy1 = wy + wh + PAD_Y - HANDLE_SIZE - 2
                hx2 = wx + ww + PAD_X - 2
                hy2 = wy + wh + PAD_Y - 2

                if existing:
                    self.image_canvas.coords(f"{window_id}_resize_handle", hx1, hy1, hx2, hy2)
                else:
                    self.image_canvas.create_rectangle(
                        hx1, hy1, hx2, hy2,
                        outline="black", fill="lightgray",
                        tags=(window_id, "floating", f"{window_id}_resize_handle")
                    )

                # Re-bind resize callbacks stored in create_floating_window
                if hasattr(self, "_resize_callbacks") and window_id in self._resize_callbacks:
                    start_resize, do_resize, end_resize = self._resize_callbacks[window_id]
                    self.image_canvas.tag_bind(f"{window_id}_resize_handle", "<Button-1>", start_resize)
                    self.image_canvas.tag_bind(f"{window_id}_resize_handle", "<B1-Motion>", do_resize)
                    self.image_canvas.tag_bind(f"{window_id}_resize_handle", "<ButtonRelease-1>", end_resize)
                    self.image_canvas.tag_raise(f"{window_id}_resize_handle")

            except Exception:
                pass

        except Exception as e:
            self.custom_warning("Display Error", f"Error displaying the original image: {e}")
            return



    def color_mapping_all(self, window_id):
        """
        Fast Tkinter Color Mapping All operation.

        UI/job/cache orchestration stays here.
        Label-map computation, palette generation and recoloring live in ImageManager.
        """
        items = self.image_canvas.find_withtag(window_id)
        if not items:
            self.custom_warning("No Window", f"No floating window found with id {window_id}")
            return

        if getattr(self, "mapping_locked_until_original", {}).get(window_id, False):
            self.custom_warning(
                "Restore Original Image",
                "This image belongs to a previous Color Space. Press Original before applying Color Mapping All."
            )
            return

        if not hasattr(self, "window_mapping_mode"):
            self.window_mapping_mode = {}

        if not hasattr(self, "window_image_key") or window_id not in self.window_image_key:
            self.custom_warning("Error", "Image cache key not found for this window.")
            return

        self.window_mapping_mode[window_id] = "all"

        image_key = self.window_image_key[window_id]
        color_space_key = getattr(self, "file_path", None)
        cache_scope = (image_key, color_space_key)

        try:
            self._disable_original_rectangle_sampling(window_id)
        except Exception:
            pass

        try:
            self.image_canvas.delete(f"{window_id}_resize_handle")
            self.image_canvas.tag_unbind(f"{window_id}_resize_handle", "<Button-1>")
            self.image_canvas.tag_unbind(f"{window_id}_resize_handle", "<B1-Motion>")
            self.image_canvas.tag_unbind(f"{window_id}_resize_handle", "<ButtonRelease-1>")
        except Exception:
            pass

        try:
            self.image_canvas.itemconfig(f"{window_id}_pct_text", text="")
        except Exception:
            pass

        self.CAN_APPLY_MAPPING[window_id] = False
        self.SHOW_ORIGINAL[window_id] = True

        if hasattr(self, "_destroy_proto_options"):
            self._destroy_proto_options(window_id)
        else:
            self.proto_options = getattr(self, "proto_options", {})
            info = self.proto_options.pop(window_id, None)
            if isinstance(info, dict):
                try:
                    if info.get("canvas_item"):
                        self.image_canvas.delete(info.get("canvas_item"))
                except Exception:
                    pass
                try:
                    frame = info.get("frame")
                    if frame and frame.winfo_exists():
                        frame.destroy()
                except Exception:
                    pass

        def update_progress(job_id, current_step, total_steps):
            if total_steps <= 0:
                return
            self._update_window_progress(window_id, job_id, current_step, total_steps)

        def build_legend_frame(prototypes, parent_canvas, palette_uint8):
            """Create and return the legend frame for the current palette."""
            legend_frame = tk.Frame(parent_canvas, bg="white", relief="solid", bd=1)
            legend_frame.grid_rowconfigure(0, weight=1)
            legend_frame.grid_columnconfigure(0, weight=1)

            canvas = tk.Canvas(legend_frame, bg="white", highlightthickness=0)
            v_scroll = tk.Scrollbar(legend_frame, orient=tk.VERTICAL, command=canvas.yview)
            h_scroll = tk.Scrollbar(legend_frame, orient=tk.HORIZONTAL, command=canvas.xview)

            canvas.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
            canvas.grid(row=0, column=0, sticky="nsew")
            v_scroll.grid(row=0, column=1, sticky="ns")
            h_scroll.grid(row=1, column=0, sticky="ew")

            inner_frame = tk.Frame(canvas, bg="white")
            canvas.create_window((0, 0), window=inner_frame, anchor="nw", tags="inner")

            def resize_inner(event):
                canvas.itemconfig("inner", width=event.width)

            canvas.bind("<Configure>", resize_inner)

            def on_frame_configure(_event=None):
                canvas.configure(scrollregion=canvas.bbox("all"))

            inner_frame.bind("<Configure>", lambda e: canvas.after_idle(on_frame_configure))

            def bind_scroll_events(c):
                def _on_mousewheel(event):
                    c.yview_scroll(int(-1 * (event.delta / 120)), "units")

                def _bind_mousewheel(_event):
                    c.bind_all("<MouseWheel>", _on_mousewheel)

                def _unbind_mousewheel(_event):
                    c.unbind_all("<MouseWheel>")

                c.bind("<Enter>", _bind_mousewheel)
                c.bind("<Leave>", _unbind_mousewheel)

            bind_scroll_events(canvas)

            for i, prototype in enumerate(prototypes):
                rgb = palette_uint8[i].astype(int)
                color_hex = "#{:02x}{:02x}{:02x}".format(rgb[0], rgb[1], rgb[2])

                luminance = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
                text_color = "white" if luminance < 80 else "black"

                label = tk.Label(
                    inner_frame,
                    text=prototype.label,
                    bg=color_hex,
                    fg=text_color,
                    padx=5,
                    pady=2
                )
                label.pack(fill="x", padx=5, pady=2)

            inner_frame.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))

            return legend_frame

        def update_ui(recolored_image, new_legend_frame):
            """Update the UI safely from the main thread."""
            try:
                self.modified_image[window_id] = recolored_image

                if recolored_image.ndim == 3 and recolored_image.shape[-1] == 4:
                    pil_to_show = Image.fromarray(recolored_image.astype(np.uint8), mode="RGBA")
                else:
                    pil_to_show = Image.fromarray(recolored_image.astype(np.uint8), mode="RGB")

                img_tk = ImageTk.PhotoImage(pil_to_show)
                self.floating_images[window_id] = img_tk

                if hasattr(self, "display_pil"):
                    self.display_pil[window_id] = pil_to_show

                image_items = self.image_canvas.find_withtag(f"{window_id}_click_image")
                if image_items:
                    self.image_canvas.itemconfig(image_items[0], image=img_tk)
                else:
                    self.custom_warning("Image Error", f"No image found for window_id: {window_id}")

                # Remove previous legend canvas item before adding the new one.
                if hasattr(self, "_destroy_proto_options"):
                    self._destroy_proto_options(window_id)
                else:
                    self.proto_options = getattr(self, "proto_options", {})
                    old_info = self.proto_options.pop(window_id, None)
                    if isinstance(old_info, dict):
                        try:
                            if old_info.get("canvas_item"):
                                self.image_canvas.delete(old_info.get("canvas_item"))
                        except Exception:
                            pass
                        try:
                            old_frame = old_info.get("frame")
                            if old_frame and old_frame is not new_legend_frame and old_frame.winfo_exists():
                                old_frame.destroy()
                        except Exception:
                            pass

                bbox = self.image_canvas.bbox(items[0])
                if not bbox:
                    return

                x1, y1, x2, y2 = bbox
                frame_x = x2 + 10
                frame_y = y1
                img_h = (y2 - y1)
                desired_w = 150
                desired_h = min(300, img_h)

                legend_item = self.image_canvas.create_window(
                    frame_x,
                    frame_y,
                    window=new_legend_frame,
                    anchor="nw",
                    width=desired_w,
                    height=desired_h,
                    tags=(f"{window_id}_legend", "legend")
                )

                btn = tk.Button(
                    new_legend_frame,
                    text="Alt. Colors",
                    command=lambda: recolor(window_id)
                )
                btn.grid(row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

                self.proto_options[window_id] = {
                    "frame": new_legend_frame,
                    "canvas_item": legend_item
                }

            except Exception as e:
                self.custom_warning("Display Error", f"Error displaying the image: {e}")

        def recolor(window_id):
            """Switch displayed palette without recomputing memberships."""
            if getattr(self, "mapping_locked_until_original", {}).get(window_id, False):
                self.custom_warning(
                    "Old Color Space",
                    "This Color Mapping All result belongs to a previous Color Space. Press Original to use the new one."
                )
                return

            if not self._window_exists(window_id):
                return

            scope_cache = getattr(self, "cm_cache_by_image", {}).get(cache_scope)
            if not scope_cache:
                return

            cache_pack = scope_cache.get("last_pack")
            if not cache_pack:
                return

            label_map = cache_pack["label_map"]
            palettes = cache_pack["palettes"]
            current = cache_pack["scheme"]

            new = "original" if current == "alt" else "alt"
            cache_pack["scheme"] = new

            palette = palettes[new]
            recolored_image = self.image_manager.recolor_label_map(label_map, palette)

            new_legend_frame = build_legend_frame(self.prototypes, self.image_canvas, palette)
            cache_pack["legend_frame"] = new_legend_frame

            self.image_canvas.after(0, lambda: update_ui(recolored_image, new_legend_frame))

        def run_process(cancel_event, job_id):
            try:
                if self._is_job_cancelled(window_id, cancel_event, job_id):
                    return

                if not hasattr(self, "images") or window_id not in self.images:
                    self.image_canvas.after(
                        0,
                        lambda: self.custom_warning("Processing Error", "Current image not found for this window.")
                    )
                    return

                source_img = self.images[window_id]
                w, h = source_img.size

                valid_mask = UtilsTools._get_alpha_mask_from_pil(source_img)
                processing_img = UtilsTools._pil_rgb_for_processing(source_img)

                if not hasattr(self, "cm_cache_by_image"):
                    self.cm_cache_by_image = {}
                scope_cache = self.cm_cache_by_image.setdefault(cache_scope, {})

                proto_labels = tuple([p.label for p in self.prototypes])
                cache_key = (w, h, proto_labels)
                label_map = scope_cache.get(cache_key)

                if label_map is None:
                    label_map = self.image_manager.get_best_prototype_label_map(
                        image=processing_img,
                        fuzzy_color_space=self.fuzzy_color_space,
                        valid_mask=valid_mask,
                        progress_callback=lambda current, total: update_progress(job_id, current, total),
                        cancel_callback=lambda: self._is_job_cancelled(window_id, cancel_event, job_id)
                    )

                    if label_map is None:
                        return

                    scope_cache[cache_key] = label_map

                if self._is_job_cancelled(window_id, cancel_event, job_id):
                    return

                original_palette = self.image_manager.build_original_palette_uint8(self.prototypes)
                alt_palette = self.image_manager.build_alt_palette_uint8(self.prototypes, self.hex_color)

                # Show representative color-space colors first.
                scheme = "alt"
                palette = alt_palette
                recolored_image = self.image_manager.recolor_label_map(label_map, palette)
                new_legend_frame = build_legend_frame(self.prototypes, self.image_canvas, palette)

                scope_cache["last_pack"] = {
                    "label_map": label_map,
                    "palettes": {"original": original_palette, "alt": alt_palette},
                    "scheme": scheme,
                    "legend_frame": new_legend_frame,
                    "cache_key": cache_key,
                }

                def _ui():
                    if not self._is_current_job(window_id, job_id):
                        return
                    if not self._window_exists(window_id):
                        return
                    update_ui(recolored_image, new_legend_frame)

                self.image_canvas.after(0, _ui)

            except RuntimeError as e:
                if str(e) != "__JOB_CANCELLED__":
                    self.image_canvas.after(
                        0,
                        lambda: self.custom_warning("Processing Error", f"Error in color mapping: {e}")
                    )
            except Exception as e:
                self.image_canvas.after(
                    0,
                    lambda: self.custom_warning("Processing Error", f"Error in color mapping: {e}")
                )

        job_id = self._start_window_job(window_id, "color_mapping_all", run_process)
        if job_id is not None:
            self._show_window_loading(window_id, "Color Mapping All...")








































    # ============================================================================================================================================================
    #  FUNCTIONS AT and PT
    # ============================================================================================================================================================
    def get_umbral_points(self, threshold, mode=None):
        """
        Filter points inside the selected fuzzy volumes using the given threshold
        and update the embedded 3D view.
        """
        # Ensure a color space is available before running the evaluation.
        if not hasattr(self, "COLOR_SPACE") or not self.COLOR_SPACE:
            self.custom_warning("No Color Space", "Please load a fuzzy color space before deploying AT or PT.")
            return

        selected_options = [key for key, var in self.model_3d_options.items() if var.get()]
        if selected_options == ["Representative"]:
            return
        else:
            self.show_loading()

        def update_progress(current_step, total_steps):
            """
            Update the loading progress bar.
            """
            progress_percentage = (current_step / total_steps) * 100
            self.progress["value"] = progress_percentage
            self.load_window.update_idletasks()

        def run_threshold_process():
            """
            Run the threshold filtering in a background thread and refresh the 3D plot
            on the main Tkinter thread when the computation finishes.
            """
            try:
                # Define the volume priority used for threshold filtering.
                priority_map = {
                    "Support": self.selected_core,
                    "0.5-cut": self.selected_alpha,
                    "Core": self.selected_support,
                }

                selected_option = next(
                    (opt for opt in ["Support", "0.5-cut", "Core"] if opt in selected_options),
                    None,
                )
                selected_volume = priority_map[selected_option]

                # Step 1: filter the LAB points inside the selected volume.
                update_progress(1, 3)
                self.filtered_points, volume_limits = self.color_manager.filter_points_with_threshold(
                    selected_volume,
                    threshold,
                    step=0.25,
                )

                # Save the computed ranges as CSV.
                csv_path = self.color_manager.create_csv(self.file_base_name, volume_limits, mode)
                print(f"CSV saved in test_results/: {csv_path}")

                # Step 2: prepare the plot refresh.
                update_progress(2, 3)

                def redraw_filtered_plot():
                    """
                    Refresh the existing embedded 3D figure with the filtered points.
                    """
                    self._init_3d_canvas()

                    VisualManager.plot_combined_3D(
                        self.ax_3d,
                        self.file_base_name,
                        self.selected_centroids,
                        self.selected_core,
                        self.selected_alpha,
                        self.selected_support,
                        self.volume_limits,
                        self.hex_color,
                        selected_options,
                        self.filtered_points,
                    )

                    self.graph_widget.draw()

                    if hasattr(self, "lab_value_frame"):
                        self.lab_value_frame.lift()

                # Step 3: redraw the figure on the Tkinter main thread.
                update_progress(3, 3)
                self.root.after(0, redraw_filtered_plot)

            except Exception as e:
                self.root.after(
                    0,
                    lambda: self.custom_warning("Error", f"An error occurred while filtering points: {e}")
                )
            finally:
                self.root.after(0, self.hide_loading)

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
            threshold_refs["result_value_label"].configure(bg=theme["body_bg"], fg=theme["accent"])
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
            - 'result'  -> like More Info: config + colored result card
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
            pady=10
        ).pack(fill="x")

        threshold_body = tk.Frame(threshold_panel, bg="white")
        threshold_body.pack(fill="x", padx=12, pady=(0, 10))

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
            selection_w = 310
            config_w = 300

            threshold_body.grid_columnconfigure(0, minsize=selection_w, weight=0)
            threshold_body.grid_columnconfigure(1, minsize=1, weight=0)
            threshold_body.grid_columnconfigure(2, minsize=config_w, weight=1)
            threshold_body.grid_columnconfigure(3, minsize=1, weight=0)
            threshold_body.grid_columnconfigure(4, weight=1)

            section_selection = tk.Frame(threshold_body, bg="white", width=selection_w)
            section_selection.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
            section_selection.grid_propagate(False)

            tk.Frame(threshold_body, bg="#d8d8d8", width=1, height=140).grid(
                row=0, column=1, sticky="ns", padx=(0, 12), pady=2
            )

            section_config = tk.Frame(threshold_body, bg="white", width=config_w)
            section_config.grid(row=0, column=2, sticky="nsew", padx=(0, 12))
            section_config.grid_propagate(False)

            tk.Frame(threshold_body, bg="#d8d8d8", width=1, height=140).grid(
                row=0, column=3, sticky="ns", padx=(0, 12), pady=2
            )

            section_output = tk.Frame(threshold_body, bg="white")
            section_output.grid(row=0, column=4, sticky="nsew")

        # -------------------------
        # Left: metric selection
        # -------------------------
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
            wraplength=255 if variant == "result" else 285,
            font=("Sans", 8, "italic")
        )
        metric_help_label.pack(anchor="w", fill="x", pady=(0, 4))

        # -------------------------
        # Center: configuration
        # -------------------------
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

        # -------------------------
        # Right: output
        # -------------------------
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


    def _apply_more_info_threshold_result_style(self, refs, status):
        """
        Apply the same formal threshold result style used in Color Evaluation.
        """
        self._apply_threshold_result_style(refs, status)


    def _refresh_more_info_threshold_ui(self, vars_dict, refs, proto_lab=None, sample_lab=None):
        """
        Refresh the More Info threshold UI.

        It keeps the formal result style and uses the existing informative
        summary sentence generated by ColorEvaluationManager, without showing
        the component breakdown.
        """
        original_variant = refs.get("variant", "more_info")

        try:
            refs["variant"] = "summary"
            self._refresh_shared_threshold_ui(
                vars_dict=vars_dict,
                refs=refs,
                proto_lab=None,
                sample_lab=None
            )
        finally:
            refs["variant"] = original_variant

        if proto_lab is None or sample_lab is None:
            vars_dict["threshold_result_title_var"].set("Select a prototype to evaluate")
            vars_dict["threshold_result_detail_var"].set("")
            vars_dict["threshold_result_summary_var"].set("")
            self._apply_more_info_threshold_result_style(refs, "unavailable")
            return

        evaluation = self.evaluate_color_difference_threshold(
            sample_lab=sample_lab,
            prototype_lab=proto_lab,
            metric=self.threshold_settings.get("metric", "CIEDE2000"),
            threshold_settings=self.threshold_settings
        )

        metric_value = evaluation.get("metric_value", evaluation.get("delta_e"))
        status = evaluation.get("status", "unavailable")
        metric_name = self.threshold_settings.get("metric", "Metric")

        if metric_value is None:
            vars_dict["threshold_result_title_var"].set(
                evaluation.get("evaluation", "Metric not available")
            )
            vars_dict["threshold_result_detail_var"].set(
                "Unable to compute selected metric"
            )

            summary_text = evaluation.get("summary_visual", evaluation.get("summary", ""))
            short_summary = str(summary_text).strip().splitlines()[0] if str(summary_text).strip() else ""

            vars_dict["threshold_result_summary_var"].set(short_summary)
            self._apply_more_info_threshold_result_style(refs, status)
            return

        vars_dict["threshold_result_title_var"].set(
            evaluation.get("evaluation", "No evaluation available")
        )

        vars_dict["threshold_result_detail_var"].set(
            evaluation.get(
                "detail",
                f"{metric_name} = {metric_value:.3f}"
            )
        )

        # Use only the first informative line:
        # "Invalid threshold using CIEDE2000."
        # and discard the following "Component breakdown..." lines.
        summary_text = evaluation.get("summary_visual", evaluation.get("summary", ""))
        summary_text = str(summary_text).strip()

        if summary_text:
            short_summary = summary_text.splitlines()[0].strip()
        else:
            short_summary = f"{evaluation.get('evaluation', 'Result')} using {metric_name}."

        vars_dict["threshold_result_summary_var"].set(short_summary)

        self._apply_more_info_threshold_result_style(refs, status)



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
        IMG_LEFT_PAD = 15
        IMG_TOP_PAD = 40

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

        start_x, start_y = self._clip_original_canvas_point_to_image(event.x, event.y, window_id)

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
        x1, y1 = self._clip_original_canvas_point_to_image(event.x, event.y, window_id)

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
        x1, y1 = self._clip_original_canvas_point_to_image(event.x, event.y, window_id)

        left = min(x0, x1)
        right = max(x0, x1)
        top = min(y0, y1)
        bottom = max(y0, y1)

        # Treat a tiny drag as a normal click
        if (right - left) < 3 and (bottom - top) < 3:
            local_x = event.x - img_x
            local_y = event.y - img_y

            # Ignore clicks outside the displayed image
            if local_x < 0 or local_y < 0 or local_x >= draw_w or local_y >= draw_h:
                return "break"

            full_x = int(local_x * full_w / draw_w)
            full_y = int(local_y * full_h / draw_h)

            full_x = max(0, min(full_w - 1, full_x))
            full_y = max(0, min(full_h - 1, full_y))

            r, g, b = pil.getpixel((full_x, full_y))
            pixel_lab = UtilsTools.srgb_to_lab(r, g, b)

            if self.COLOR_SPACE:
                self.display_pixel_value(full_x, full_y, pixel_lab, is_average=False, selection_info=None)

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

        # Map displayed-image coordinates back to original-image coordinates
        full_left = int(left_i * full_w / draw_w)
        full_right = int(right_i * full_w / draw_w)
        full_top = int(top_i * full_h / draw_h)
        full_bottom = int(bottom_i * full_h / draw_h)

        full_left = max(0, min(full_w - 1, full_left))
        full_right = max(0, min(full_w, full_right))
        full_top = max(0, min(full_h - 1, full_top))
        full_bottom = max(0, min(full_h, full_bottom))

        if full_right <= full_left or full_bottom <= full_top:
            return "break"

        # Compute mean RGB inside the selected rectangle
        crop = pil.crop((full_left, full_top, full_right, full_bottom))
        arr = np.asarray(crop, dtype=np.float32)
        mean_rgb = arr.reshape(-1, 3).mean(axis=0)

        r = int(round(mean_rgb[0]))
        g = int(round(mean_rgb[1]))
        b = int(round(mean_rgb[2]))

        pixel_lab = UtilsTools.srgb_to_lab(r, g, b)

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
                selection_info=selection_info
            )

        return "break"



    def display_pixel_value(self, x_original, y_original, pixel_lab, is_average=False, selection_info=None):
        """
        Display selected pixel/ROI LAB information in a compact floating info bar.
        Shows coordinates, LAB value, selected prototype and a More Info action.
        Stores pixel/ROI info for the More Info popup.
        """
        # ---------------------------------------------------------------------
        # Create compact floating info bar only once
        # ---------------------------------------------------------------------
        if not hasattr(self, "lab_value_frame"):
            BAR_BG = "#ffffff"
            TEXT = "#1f2937"
            MUTED = "#6b7280"
            SEPARATOR = "#d9dde3"
            LINK = "#1f4e8c"

            self.lab_value_frame = tk.Frame(
                self.Canvas1,
                bg=BAR_BG,
                bd=0,
                relief="flat",
                highlightthickness=1,
                highlightbackground="#d9dde3"
            )

            # Más abajo que antes
            self.lab_value_frame.place(relx=0.5, rely=0.987, anchor="s")

            text_frame = tk.Frame(self.lab_value_frame, bg=BAR_BG)
            text_frame.pack(side="left", padx=(10, 6), pady=4)

            label_font = ("Segoe UI", 8, "bold")
            value_font = ("Segoe UI", 9)

            def add_separator(parent):
                tk.Frame(
                    parent,
                    bg=SEPARATOR,
                    width=1,
                    height=18
                ).pack(side="left", padx=8, pady=2)

            def make_info_item(parent, label_text):
                group = tk.Frame(parent, bg=BAR_BG)
                group.pack(side="left")

                tk.Label(
                    group,
                    text=f"{label_text}:",
                    font=label_font,
                    bg=BAR_BG,
                    fg=MUTED
                ).pack(side="left")

                value_label = tk.Label(
                    group,
                    text="",
                    font=value_font,
                    bg=BAR_BG,
                    fg=TEXT
                )
                value_label.pack(side="left", padx=(4, 0))

                return value_label

            self.coord_value = make_info_item(text_frame, "Coords")
            add_separator(text_frame)

            self.lab_value_print = make_info_item(text_frame, "LAB")
            add_separator(text_frame)

            self.proto_value_text = make_info_item(text_frame, "Prototype")

            search_icon = self.load_toolbar_icon("Search.png", (17, 17))

            more_info_button = tk.Label(
                self.lab_value_frame,
                image=search_icon,
                bg=BAR_BG,
                cursor="hand2",
                padx=5,
                pady=2
            )
            more_info_button.image = search_icon
            more_info_button.bind("<Button-1>", lambda e: self.show_more_info_pixel())

            def _search_enter(_event):
                try:
                    more_info_button.configure(bg="#f1f5f9")
                except Exception:
                    pass

            def _search_leave(_event):
                try:
                    more_info_button.configure(bg=BAR_BG)
                except Exception:
                    pass

            more_info_button.bind("<Enter>", _search_enter)
            more_info_button.bind("<Leave>", _search_leave)
            more_info_button.pack(side="right", padx=(2, 8), pady=4)

        # ---------------------------------------------------------------------
        # Membership computation
        # ---------------------------------------------------------------------
        membership_degrees = self.fuzzy_color_space.calculate_membership(pixel_lab)

        if membership_degrees:
            max_proto = max(membership_degrees, key=membership_degrees.get)
            winner_mu = float(membership_degrees[max_proto])
            top_memberships = sorted(membership_degrees.items(), key=lambda kv: kv[1], reverse=True)
        else:
            max_proto = None
            winner_mu = 0.0
            top_memberships = []

        # ---------------------------------------------------------------------
        # Store data for the "More Info" popup
        # ---------------------------------------------------------------------
        self._last_pixel_info = {
            "x": x_original,
            "y": y_original,
            "lab": pixel_lab,
            "is_average": bool(is_average),
            "selection_info": selection_info,
            "winner_label": max_proto if max_proto is not None else "None",
            "winner_mu": winner_mu,
            "top_memberships": top_memberships,
            "all_memberships": top_memberships,
        }

        # ---------------------------------------------------------------------
        # Prepare compact display text
        # ---------------------------------------------------------------------
        if selection_info and selection_info.get("type") == "roi":
            coord_text = (
                f"ROI ({selection_info['x1']},{selection_info['y1']})"
                f"→({selection_info['x2']},{selection_info['y2']})"
            )
        else:
            coord_text = f"({x_original}, {y_original})"

        max_coord_len = 24
        if len(coord_text) > max_coord_len:
            coord_text = coord_text[:max_coord_len - 1] + "…"

        lab_text = f"{pixel_lab[0]:.2f}, {pixel_lab[1]:.2f}, {pixel_lab[2]:.2f}"

        if max_proto is None:
            proto_text = "—"
        else:
            proto_text = str(max_proto)
            max_proto_len = 18
            if len(proto_text) > max_proto_len:
                proto_text = proto_text[:max_proto_len - 1] + "…"

        # ---------------------------------------------------------------------
        # Update UI
        # ---------------------------------------------------------------------
        self.coord_value.config(text=coord_text)
        self.lab_value_print.config(text=lab_text)
        self.proto_value_text.config(text=proto_text, fg="#1f2937")



    def _close_more_info_window(self):
        """Close the 'More Info' window if it is currently open."""
        if hasattr(self, "_more_info_window") and self._more_info_window is not None:
            try:
                if self._more_info_window.winfo_exists():
                    self._more_info_window.destroy()
            except Exception:
                pass
            finally:
                self._more_info_window = None



    def show_more_info_pixel(self):
        """Show detailed info for the last clicked pixel/ROI with clickable prototype preview."""
        info = getattr(self, "_last_pixel_info", None)
        if not info:
            messagebox.showinfo(
                "More Info",
                "Click on an image pixel first.",
                parent=self._get_active_dialog_parent()
            )
            return

        self._ensure_threshold_settings()

        # Close any previous More Info window first
        self._close_more_info_window()

        win = tk.Toplevel(self.root)
        self._more_info_window = win

        win.title("More Info")

        WIN_W, WIN_H = 980, 640
        win.geometry(f"{WIN_W}x{WIN_H}")
        win.resizable(False, False)
        win.configure(bg="#f2f2f2")

        # Ensure reference is released if user closes the window manually
        win.protocol("WM_DELETE_WINDOW", lambda: self._on_close_more_info_window())

        ui = self._build_more_info_pixel_window(win, info)

        # Modal-like behavior
        win.transient(self.root)
        win.grab_set()
        win.focus_set()

        win.update_idletasks()
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()

        x = root_x + (root_w - WIN_W) // 2
        y = root_y + (root_h - WIN_H) // 2
        win.geometry(f"{WIN_W}x{WIN_H}+{x}+{y}")



    def _on_close_more_info_window(self):
        """Handle manual closing of the More Info window."""
        try:
            if hasattr(self, "_more_info_window") and self._more_info_window is not None:
                if self._more_info_window.winfo_exists():
                    self._more_info_window.destroy()
        except Exception:
            pass
        finally:
            self._more_info_window = None


    def _build_more_info_pixel_window(self, win, info):
        """
        Build the full 'More Info' window UI and wire all interactions.
        Returns a dictionary with relevant UI references.
        """
        base_data = self._get_more_info_base_data(info)
        self._ensure_threshold_settings()

        vars_dict = self._create_more_info_vars(base_data)

        main = tk.Frame(win, bg="#f2f2f2")
        main.pack(fill="both", expand=True, padx=10, pady=10)

        self._build_more_info_header(main, base_data)

        content_refs = self._build_more_info_content(main, base_data, vars_dict)

        self._populate_more_info_memberships(
            base_data=base_data,
            vars_dict=vars_dict,
            refs=content_refs
        )

        btns = tk.Frame(main, bg="#f2f2f2")
        btns.pack(fill="x", pady=(10, 0))
        tk.Button(btns, text="Close", command=self._on_close_more_info_window, width=12).pack(side="right")

        return {
            "base_data": base_data,
            "vars_dict": vars_dict,
            "refs": content_refs
        }



    def _get_more_info_base_data(self, info):
        """Extract and normalize the base data used by the More Info window."""
        lab = info.get("lab", (0, 0, 0))
        selection_info = info.get("selection_info")
        is_average = bool(info.get("is_average", False))

        if selection_info and selection_info.get("mean_rgb") is not None:
            sampled_rgb = selection_info["mean_rgb"]
        else:
            try:
                sampled_rgb = UtilsTools.lab_to_rgb(lab)
            except Exception:
                sampled_rgb = (200, 200, 200)

        memberships = info.get("all_memberships")
        if not memberships:
            memberships = info.get("top_memberships", [])

        winner_label = info.get("winner_label", "None")
        winner_mu = float(info.get("winner_mu", 0.0))

        sampled_hex = self._safe_hex_from_rgb(sampled_rgb)
        sampled_title = "Mean Color" if is_average else "Selected Color"

        if selection_info and selection_info.get("type") == "roi":
            coord_text = (
                f"ROI: ({selection_info['x1']}, {selection_info['y1']}) "
                f"→ ({selection_info['x2']}, {selection_info['y2']})"
            )
            roi_text = (
                f"Size: {selection_info['width']} x {selection_info['height']} px"
                f"    |    Pixels: {selection_info['pixels']}"
                f"    |    Center: ({selection_info['center_x']}, {selection_info['center_y']})"
            )
        else:
            coord_text = f"Coordinates: ({info.get('x', 0)}, {info.get('y', 0)})"
            roi_text = None

        return {
            "info": info,
            "lab": lab,
            "selection_info": selection_info,
            "is_average": is_average,
            "sampled_rgb": sampled_rgb,
            "sampled_hex": sampled_hex,
            "sampled_title": sampled_title,
            "memberships": memberships,
            "winner_label": winner_label,
            "winner_mu": winner_mu,
            "coord_text": coord_text,
            "roi_text": roi_text,
        }



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


    def _create_more_info_vars(self, base_data):
        """Create and return all Tk variables used by the More Info window."""
        vars_dict = {
            "selected_label_var": tk.StringVar(
                value=base_data["winner_label"] if base_data["winner_label"] != "None" else ""
            ),
            "selected_rgb_var": tk.StringVar(value=""),
            "selected_hex_var": tk.StringVar(value=""),
            "selected_lab_var": tk.StringVar(value=""),
        }

        return self._merge_threshold_vars(vars_dict)


    def _build_more_info_header(self, parent, base_data):
        """Build the top header section of the More Info window."""
        header = tk.Frame(parent, bg="white", bd=1, relief="solid")
        header.pack(fill="x", pady=(0, 10))

        tk.Label(
            header,
            text=base_data["coord_text"],
            anchor="w",
            bg="white",
            font=("Sans", 11, "bold"),
            padx=12,
            pady=6
        ).pack(fill="x")

        if base_data["roi_text"]:
            tk.Label(
                header,
                text=base_data["roi_text"],
                anchor="w",
                bg="white",
                font=("Sans", 10),
                padx=12,
                pady=0
            ).pack(fill="x", pady=(0, 4))

        lab = base_data["lab"]
        sampled_rgb = base_data["sampled_rgb"]
        sampled_hex = base_data["sampled_hex"]

        lab_text = f"{float(lab[0]):.2f}, {float(lab[1]):.2f}, {float(lab[2]):.2f}"
        rgb_text = f"{int(sampled_rgb[0])}, {int(sampled_rgb[1])}, {int(sampled_rgb[2])}"
        hex_text = sampled_hex.upper()

        tk.Label(
            header,
            text=f"LAB: {lab_text}    |    RGB: {rgb_text}    |    HEX: {hex_text}",
            anchor="w",
            bg="white",
            font=("Sans", 10),
            padx=12,
            pady=0
        ).pack(fill="x", pady=(0, 8))


    def _build_more_info_content(self, parent, base_data, vars_dict):
        """Build the main content area and return references to important widgets."""
        content = tk.Frame(parent, bg="#f2f2f2")
        content.pack(fill="both", expand=True)

        top_content = tk.Frame(content, bg="#f2f2f2")
        top_content.pack(fill="x", anchor="n")

        left = tk.Frame(top_content, bg="white", bd=1, relief="solid", width=320, height=280)
        left.pack(side="left", fill="y", padx=(0, 6), anchor="n")
        left.pack_propagate(False)

        center = tk.Frame(top_content, bg="white", bd=1, relief="solid", height=270)
        center.pack(side="left", fill="x", expand=True, padx=(6, 0), anchor="n")
        center.pack_propagate(False)

        membership_refs = self._build_more_info_membership_panel(left, base_data)
        prototype_refs = self._build_more_info_prototype_panel(center, base_data, vars_dict)
        threshold_refs = self._build_more_info_threshold_panel(content, vars_dict)

        return {
            "content": content,
            "left": left,
            "center": center,
            "membership_refs": membership_refs,
            "prototype_refs": prototype_refs,
            "threshold_refs": threshold_refs,
        }



    def _build_more_info_membership_panel(self, parent, base_data):
        """Build the left memberships panel."""
        tk.Label(
            parent,
            text="Membership Degree (μ)",
            font=("Sans", 11, "bold"),
            anchor="w",
            bg="white",
            padx=12,
            pady=10
        ).pack(fill="x")

        tk.Label(
            parent,
            text=f"Winner: {base_data['winner_label']}    |    μ = {base_data['winner_mu']:.4f}",
            anchor="w",
            bg="white",
            padx=12
        ).pack(fill="x", pady=(0, 10))

        tk.Label(
            parent,
            text="Memberships:",
            font=("Sans", 10, "bold"),
            anchor="w",
            bg="white",
            padx=12
        ).pack(fill="x", pady=(0, 6))

        memberships_box = tk.Frame(parent, bg="white", bd=1, relief="solid", height=140)
        memberships_box.pack(fill="x", padx=12, pady=(0, 8))
        memberships_box.pack_propagate(False)

        list_canvas = tk.Canvas(
            memberships_box,
            bg="white",
            highlightthickness=0,
            bd=0
        )
        list_scroll = ttk.Scrollbar(
            memberships_box,
            orient="vertical",
            command=list_canvas.yview
        )
        list_inner = tk.Frame(list_canvas, bg="white")

        list_inner.bind(
            "<Configure>",
            lambda e: list_canvas.configure(scrollregion=list_canvas.bbox("all"))
        )

        list_canvas.create_window((0, 0), window=list_inner, anchor="nw")
        list_canvas.configure(yscrollcommand=list_scroll.set)

        list_canvas.pack(side="left", fill="both", expand=True)
        list_scroll.pack(side="right", fill="y")

        def _on_membership_mousewheel(event):
            list_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        list_canvas.bind("<Enter>", lambda e: list_canvas.bind_all("<MouseWheel>", _on_membership_mousewheel))
        list_canvas.bind("<Leave>", lambda e: list_canvas.unbind_all("<MouseWheel>"))

        tip_container = tk.Frame(parent, bg="white")
        tip_container.pack(fill="x", side="bottom", padx=12, pady=(0, 10))

        tk.Frame(tip_container, bg="#d0d0d0", height=1).pack(fill="x", pady=(0, 6))

        tk.Label(
            tip_container,
            text="ℹ Click a color to inspect it.",
            justify="center",
            anchor="center",
            wraplength=260,
            bg="white",
            fg="#555555",
            font=("Sans", 9, "italic"),
            pady=6
        ).pack(fill="x")

        return {
            "memberships_box": memberships_box,
            "list_canvas": list_canvas,
            "list_inner": list_inner,
            "membership_rows": {},
        }



    def _build_more_info_prototype_panel(self, parent, base_data, vars_dict):
        """Build the center prototype/sample comparison panel."""
        SWATCH_W = 100
        SWATCH_H = 75
        PAD_X = 10
        PAD_Y = 10

        canvas_w = SWATCH_W + 2 * PAD_X
        canvas_h = SWATCH_H + 2 * PAD_Y

        top_colors = tk.Frame(parent, bg="white")
        top_colors.pack(fill="x", pady=(8, 6), padx=10)

        left_card = tk.Frame(top_colors, bg="white")
        left_card.pack(side="left", fill="both", expand=True, padx=(0, 8))

        right_card = tk.Frame(top_colors, bg="white")
        right_card.pack(side="left", fill="both", expand=True, padx=(8, 0))

        tk.Label(
            left_card,
            text="Selected Prototype",
            font=("Sans", 11, "bold"),
            bg="white"
        ).pack(fill="x")

        selected_name_label = tk.Label(
            left_card,
            textvariable=vars_dict["selected_label_var"],
            bg="white",
            font=("Sans", 10, "bold")
        )
        selected_name_label.pack(pady=(6, 2))

        selected_proto_canvas = tk.Canvas(
            left_card,
            width=canvas_w,
            height=canvas_h,
            bg="white",
            highlightthickness=0
        )
        selected_proto_canvas.pack(pady=(4, 8))

        selected_proto_rect = selected_proto_canvas.create_rectangle(
            PAD_X,
            PAD_Y,
            PAD_X + SWATCH_W,
            PAD_Y + SWATCH_H,
            fill="#cccccc",
            outline="#606060",
            width=1
        )

        tk.Label(
            left_card,
            textvariable=vars_dict["selected_lab_var"],
            bg="white",
            font=("Sans", 10),
            justify="center",
            wraplength=240
        ).pack()

        tk.Label(
            left_card,
            textvariable=vars_dict["selected_rgb_var"],
            bg="white",
            font=("Sans", 10)
        ).pack()

        tk.Label(
            left_card,
            textvariable=vars_dict["selected_hex_var"],
            bg="white",
            font=("Sans", 10)
        ).pack(pady=(2, 0))

        tk.Label(
            right_card,
            text=base_data["sampled_title"],
            font=("Sans", 11, "bold"),
            bg="white"
        ).pack(fill="x")

        sampled_canvas = tk.Canvas(
            right_card,
            width=canvas_w,
            height=canvas_h,
            bg="white",
            highlightthickness=0
        )
        sampled_canvas.pack(pady=(28, 8))

        sampled_canvas.create_rectangle(
            PAD_X,
            PAD_Y,
            PAD_X + SWATCH_W,
            PAD_Y + SWATCH_H,
            fill=base_data["sampled_hex"],
            outline="#606060",
            width=1
        )

        lab = base_data["lab"]
        sampled_rgb = base_data["sampled_rgb"]

        tk.Label(
            right_card,
            text=f"LAB: {float(lab[0]):.2f}, {float(lab[1]):.2f}, {float(lab[2]):.2f}",
            bg="white",
            font=("Sans", 10)
        ).pack()

        tk.Label(
            right_card,
            text=f"RGB: {int(sampled_rgb[0])}, {int(sampled_rgb[1])}, {int(sampled_rgb[2])}",
            bg="white",
            font=("Sans", 10)
        ).pack()

        tk.Label(
            right_card,
            text=f"HEX: {base_data['sampled_hex'].upper()}",
            bg="white",
            font=("Sans", 10)
        ).pack(pady=(2, 0))

        return {
            "selected_proto_canvas": selected_proto_canvas,
            "selected_proto_rect": selected_proto_rect,
        }



    def _build_more_info_threshold_panel(self, parent, vars_dict):
        """
        Build a compact Threshold panel for the More Info window.

        This keeps the same shared threshold variables/settings, but uses a
        narrower layout and a simplified result card.
        """
        threshold_panel = tk.Frame(parent, bg="white", bd=1, relief="solid")
        threshold_panel.pack(fill="x", pady=(6, 0), anchor="n")

        tk.Label(
            threshold_panel,
            text="Threshold",
            font=("Segoe UI", 11, "bold"),
            anchor="w",
            bg="white",
            fg="#1f2937",
            padx=12,
            pady=8
        ).pack(fill="x")

        threshold_body = tk.Frame(threshold_panel, bg="white")
        threshold_body.pack(fill="x", padx=12, pady=(0, 10))

        # Compact 3-block layout:
        # Metric | Configuration | Result
        threshold_body.grid_columnconfigure(0, minsize=230, weight=0)
        threshold_body.grid_columnconfigure(1, minsize=1, weight=0)
        threshold_body.grid_columnconfigure(2, minsize=330, weight=1)
        threshold_body.grid_columnconfigure(3, minsize=1, weight=0)
        threshold_body.grid_columnconfigure(4, minsize=230, weight=0)

        section_selection = tk.Frame(threshold_body, bg="white", width=230)
        section_selection.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        section_selection.grid_propagate(False)

        tk.Frame(threshold_body, bg="#e5e7eb", width=1, height=118).grid(
            row=0, column=1, sticky="ns", padx=(0, 10), pady=2
        )

        section_config = tk.Frame(threshold_body, bg="white")
        section_config.grid(row=0, column=2, sticky="nsew", padx=(0, 10))

        tk.Frame(threshold_body, bg="#e5e7eb", width=1, height=118).grid(
            row=0, column=3, sticky="ns", padx=(0, 10), pady=2
        )

        section_output = tk.Frame(threshold_body, bg="white", width=230)
        section_output.grid(row=0, column=4, sticky="nsew")
        section_output.grid_propagate(False)

        manager = self._get_color_evaluation_manager()

        # ------------------------------------------------------------------
        # Metric selection
        # ------------------------------------------------------------------
        tk.Label(
            section_selection,
            text="Metric Family",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
            bg="white",
            fg="#1f2937"
        ).pack(anchor="w", pady=(0, 3))

        metric_family_combo = ttk.Combobox(
            section_selection,
            textvariable=vars_dict["threshold_metric_family_var"],
            state="readonly",
            width=24,
            values=manager.get_metric_families()
        )
        metric_family_combo.pack(anchor="w", fill="x", pady=(0, 7))

        tk.Label(
            section_selection,
            text="Metric",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
            bg="white",
            fg="#1f2937"
        ).pack(anchor="w", pady=(0, 3))

        metric_combo = ttk.Combobox(
            section_selection,
            textvariable=vars_dict["threshold_metric_var"],
            state="readonly",
            width=24,
            values=manager.get_metrics_for_family(
                vars_dict["threshold_metric_family_var"].get()
            )
        )
        metric_combo.pack(anchor="w", fill="x", pady=(0, 5))

        metric_help_label = tk.Label(
            section_selection,
            textvariable=vars_dict["threshold_metric_help_var"],
            bg="white",
            fg="#6b7280",
            anchor="w",
            justify="left",
            wraplength=210,
            font=("Segoe UI", 8, "italic")
        )
        metric_help_label.pack(anchor="w", fill="x")

        # ------------------------------------------------------------------
        # Configuration
        # ------------------------------------------------------------------
        tk.Label(
            section_config,
            text="Configuration",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
            bg="white",
            fg="#1f2937"
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 7))

        section_config.grid_columnconfigure(0, minsize=98, weight=0)
        section_config.grid_columnconfigure(1, minsize=90, weight=1)
        section_config.grid_columnconfigure(2, minsize=95, weight=0)
        section_config.grid_columnconfigure(3, minsize=70, weight=1)

        mode_label = tk.Label(
            section_config,
            text="Threshold type:",
            bg="white",
            fg="#1f2937",
            anchor="w",
            font=("Segoe UI", 9)
        )

        mode_combo = ttk.Combobox(
            section_config,
            textvariable=vars_dict["threshold_mode_var"],
            state="readonly",
            width=20,
            values=["default", "custom"]
        )

        mode_label.grid(row=1, column=0, sticky="w", pady=(0, 6), padx=(0, 8))
        mode_combo.grid(row=1, column=1, columnspan=3, sticky="ew", pady=(0, 6))

        preset_label = tk.Label(
            section_config,
            text="Default preset:",
            bg="white",
            fg="#1f2937",
            anchor="w",
            font=("Segoe UI", 9)
        )

        preset_combo = ttk.Combobox(
            section_config,
            textvariable=vars_dict["threshold_preset_var"],
            state="readonly",
            width=20,
            values=[
                "Perceptibility Threshold",
                "Acceptability Threshold",
                "Perceptibility + Acceptability"
            ]
        )

        custom_type_label = tk.Label(
            section_config,
            text="Custom mode:",
            bg="white",
            fg="#1f2937",
            anchor="w",
            font=("Segoe UI", 9)
        )

        custom_type_combo = ttk.Combobox(
            section_config,
            textvariable=vars_dict["threshold_custom_type_var"],
            state="readonly",
            width=20,
            values=[
                "Single threshold",
                "Lower and upper thresholds"
            ]
        )

        single_label = tk.Label(
            section_config,
            text="Threshold:",
            bg="white",
            fg="#1f2937",
            anchor="w",
            font=("Segoe UI", 9)
        )
        single_entry = tk.Entry(
            section_config,
            textvariable=vars_dict["threshold_single_var"],
            width=9,
            font=("Segoe UI", 9)
        )

        lower_label = tk.Label(
            section_config,
            text="Lower:",
            bg="white",
            fg="#1f2937",
            anchor="w",
            font=("Segoe UI", 9)
        )
        lower_entry = tk.Entry(
            section_config,
            textvariable=vars_dict["threshold_lower_var"],
            width=8,
            font=("Segoe UI", 9)
        )

        upper_label = tk.Label(
            section_config,
            text="Upper:",
            bg="white",
            fg="#1f2937",
            anchor="w",
            font=("Segoe UI", 9)
        )
        upper_entry = tk.Entry(
            section_config,
            textvariable=vars_dict["threshold_upper_var"],
            width=8,
            font=("Segoe UI", 9)
        )

        config_hint_label = tk.Label(
            section_config,
            textvariable=vars_dict["config_hint_var"],
            bg="white",
            fg="#6b7280",
            anchor="w",
            justify="left",
            wraplength=310,
            font=("Segoe UI", 8, "italic")
        )

        def _update_config_hint_wrap(event=None):
            try:
                available_width = max(section_config.winfo_width() - 20, 220)
                config_hint_label.configure(wraplength=available_width)
            except Exception:
                pass

        section_config.bind("<Configure>", _update_config_hint_wrap)

        # ------------------------------------------------------------------
        # Result: formal card, same style as Color Evaluation, but shorter
        # ------------------------------------------------------------------
        tk.Label(
            section_output,
            text="Results",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
            bg="white",
            fg="#1f2937"
        ).pack(anchor="w", pady=(0, 7))

        result_card = tk.Frame(
            section_output,
            bg="#f7f7f7",
            bd=0,
            relief="flat",
            highlightthickness=2,
            highlightbackground="#bdbdbd",
            highlightcolor="#bdbdbd"
        )
        result_card.pack(fill="both", expand=True)

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
            textvariable=vars_dict["threshold_result_title_var"],
            anchor="w",
            justify="left",
            bg="#eeeeee",
            font=("Segoe UI", 10, "bold"),
            wraplength=170
        )
        result_title_label.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 10),
            pady=8
        )

        result_body = tk.Frame(result_card, bg="#f7f7f7")
        result_body.pack(fill="both", expand=True, padx=12, pady=(10, 10))

        result_value_label = tk.Label(
            result_body,
            textvariable=vars_dict["threshold_result_detail_var"],
            anchor="w",
            justify="left",
            bg="#f7f7f7",
            fg="#666666",
            font=("Segoe UI", 9, "bold"),
            wraplength=185
        )
        result_value_label.pack(anchor="w", fill="x", pady=(0, 9))

        result_separator = tk.Frame(
            result_body,
            bg="#dddddd",
            height=2
        )
        result_separator.pack(fill="x", padx=4, pady=(0, 8))

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
        result_summary_icon.pack(side="left", padx=(0, 7), anchor="n")

        result_summary_icon_circle = result_summary_icon.create_oval(
            2, 2, 18, 18,
            outline="#666666",
            width=2
        )

        result_summary_icon_text = result_summary_icon.create_text(
            10, 10,
            text="!",
            fill="#666666",
            font=("Segoe UI", 9, "bold")
        )

        result_text_container = tk.Frame(result_summary_row, bg="#f7f7f7")
        result_text_container.pack(side="left", fill="both", expand=True)

        result_summary_label = tk.Label(
            result_text_container,
            textvariable=vars_dict["threshold_result_summary_var"],
            anchor="w",
            justify="left",
            bg="#f7f7f7",
            wraplength=165,
            font=("Segoe UI", 8)
        )
        result_summary_label.pack(anchor="w", fill="x")

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

            "variant": "more_info",

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
            "result_summary_icon_circle": result_summary_icon_circle,
            "result_summary_icon_text": result_summary_icon_text,
            "result_summary_label": result_summary_label,
        }

        return refs



    def _populate_more_info_memberships(self, base_data, vars_dict, refs):
        """Populate memberships list and wire row selection + shared threshold refresh."""
        membership_refs = refs["membership_refs"]
        prototype_refs = refs["prototype_refs"]
        threshold_refs = refs["threshold_refs"]

        membership_rows = membership_refs["membership_rows"]
        list_inner = membership_refs["list_inner"]

        memberships = base_data["memberships"]
        sample_lab = base_data["lab"]

        def highlight_selected_row(active_label):
            for lbl, row in membership_rows.items():
                bg = "#e8f0ff" if lbl == active_label else "white"
                row.configure(bg=bg)
                for child in row.winfo_children():
                    try:
                        child.configure(bg=bg)
                    except Exception:
                        pass

        def refresh_threshold_section(proto_lab=None):
            if threshold_refs.get("variant") == "more_info":
                self._refresh_more_info_threshold_ui(
                    vars_dict=vars_dict,
                    refs=threshold_refs,
                    proto_lab=proto_lab,
                    sample_lab=sample_lab
                )
            else:
                self._refresh_shared_threshold_ui(
                    vars_dict=vars_dict,
                    refs=threshold_refs,
                    proto_lab=proto_lab,
                    sample_lab=sample_lab
                )

        def select_membership(label):
            vars_dict["selected_label_var"].set(label)

            proto_rgb = self._get_proto_rgb(label)
            proto_hex = self._safe_hex_from_rgb(proto_rgb)
            proto_lab = self._get_proto_lab(label)

            prototype_refs["selected_proto_canvas"].itemconfig(
                prototype_refs["selected_proto_rect"],
                fill=proto_hex
            )

            if proto_lab is not None:
                vars_dict["selected_lab_var"].set(
                    f"LAB: {proto_lab[0]:.2f}, {proto_lab[1]:.2f}, {proto_lab[2]:.2f}"
                )
            else:
                vars_dict["selected_lab_var"].set("LAB: not available")

            vars_dict["selected_rgb_var"].set(
                f"RGB: {int(proto_rgb[0])}, {int(proto_rgb[1])}, {int(proto_rgb[2])}"
            )
            vars_dict["selected_hex_var"].set(f"HEX: {proto_hex.upper()}")

            self._current_threshold_proto_lab = proto_lab
            refresh_threshold_section(proto_lab=proto_lab)
            highlight_selected_row(label)

        for widget in (
            threshold_refs["metric_family_combo"],
            threshold_refs["metric_combo"],
            threshold_refs["mode_combo"],
            threshold_refs["preset_combo"],
            threshold_refs["custom_type_combo"],
        ):
            widget.bind(
                "<<ComboboxSelected>>",
                lambda e: refresh_threshold_section(
                    proto_lab=getattr(self, "_current_threshold_proto_lab", None)
                )
            )

        for widget in (
            threshold_refs["single_entry"],
            threshold_refs["lower_entry"],
            threshold_refs["upper_entry"],
        ):
            widget.bind(
                "<KeyRelease>",
                lambda e: refresh_threshold_section(
                    proto_lab=getattr(self, "_current_threshold_proto_lab", None)
                )
            )

        if memberships:
            for lbl, mu in memberships:
                row = tk.Frame(list_inner, bg="white", cursor="hand2", bd=0, highlightthickness=0)
                row.pack(fill="x", pady=1, padx=2)

                membership_rows[lbl] = row

                proto_hex = self._get_proto_hex(lbl)

                swatch = tk.Canvas(row, width=16, height=16, bg="white", highlightthickness=0)
                swatch.pack(side="left", padx=(4, 6), pady=2)
                swatch.create_rectangle(1, 1, 15, 15, fill=proto_hex, outline="#707070")

                lbl_name = tk.Label(row, text=str(lbl), anchor="w", bg="white", font=("Sans", 10))
                lbl_name.pack(side="left", fill="x", expand=True)

                lbl_mu = tk.Label(row, text=f"μ = {float(mu):.4f}", anchor="e", bg="white", font=("Sans", 10))
                lbl_mu.pack(side="right", padx=(6, 4))

                for widget in (row, swatch, lbl_name, lbl_mu):
                    widget.bind(
                        "<Button-1>",
                        lambda e, label=lbl: select_membership(label)
                    )
        else:
            tk.Label(
                list_inner,
                text="No memberships available.",
                anchor="w",
                bg="white"
            ).pack(fill="x")

        if memberships:
            initial_label = (
                base_data["winner_label"]
                if base_data["winner_label"] not in (None, "None", "")
                else memberships[0][0]
            )
            if initial_label not in dict(memberships):
                initial_label = memberships[0][0]

            select_membership(initial_label)
        else:
            refresh_threshold_section(proto_lab=None)


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
        self._color_evaluation_window = win

        win.title("Color Space Evaluation")
        WIN_W, WIN_H = 1080, 760
        win.geometry(f"{WIN_W}x{WIN_H}")
        win.minsize(980, 680)
        win.resizable(True, True)
        win.configure(bg="#f2f2f2")
        win.protocol("WM_DELETE_WINDOW", self._on_close_color_evaluation_window)

        # ------------------------------------------------------------------
        # Fullscreen toggle for this specific Toplevel window
        # ------------------------------------------------------------------
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

        win.focus_set()

        # Open fullscreen by default
        try:
            win.attributes("-fullscreen", True)
        except tk.TclError:
            try:
                if platform.system() == "Windows":
                    win.state("zoomed")
                else:
                    screen_width = win.winfo_screenwidth()
                    screen_height = win.winfo_screenheight()
                    win.geometry(f"{screen_width}x{screen_height}+0+0")
            except Exception:
                pass

        win.after_idle(self._set_color_evaluation_initial_sash)



    def _get_active_dialog_parent(self, fallback=None):
        """
        Return the best parent window for dialogs so they appear above the
        currently active tool window instead of the main root.
        """
        candidates = [
            getattr(self, "_more_info_window", None),
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

            sash_x = int(total_w * 0.48)  # compact table | wider analysis panel
            paned.sash_place(0, sash_x, 1)
        except Exception:
            pass


    def _build_color_evaluation_window(self, win):
        """Build the full Color Evaluation window."""
        vars_dict = self._create_color_evaluation_vars()

        main = tk.Frame(win, bg="#f2f2f2")
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # =========================
        # Top: Threshold settings
        # =========================
        refs = self._build_shared_threshold_panel(
            parent=main,
            vars_dict=vars_dict,
            title="Threshold Configuration",
            variant="summary"
        )

        # =========================
        # Color Space Data block
        # =========================
        table_panel = tk.Frame(main, bg="white", bd=1, relief="solid")
        table_panel.pack(fill="both", expand=True)

        # Header row
        header_container = tk.Frame(table_panel, bg="white", height=42)
        header_container.pack(fill="x", padx=12, pady=(4, 2))
        header_container.pack_propagate(False)

        tk.Label(
            header_container,
            text="Color Space Data",
            font=("Sans", 11, "bold"),
            anchor="w",
            bg="white"
        ).pack(side="left")

        buttons_row = tk.Frame(header_container, bg="white")
        buttons_row.place(relx=0.5, rely=0.0, anchor="n")

        tk.Button(
            buttons_row,
            text="Use loaded color space",
            width=22,
            command=lambda: self._load_current_color_space_for_evaluation(vars_dict)
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            buttons_row,
            text="Load new color space",
            width=22,
            command=lambda: self._load_external_color_space_for_evaluation(vars_dict)
        ).pack(side="left")

        summary_row = tk.Frame(table_panel, bg="white")
        summary_row.pack(anchor="center", pady=(0, 0))

        tk.Label(
            summary_row,
            text="Color space:",
            font=("Sans", 10, "bold"),
            bg="white"
        ).pack(side="left", padx=(0, 4))

        tk.Label(
            summary_row,
            textvariable=vars_dict["space_name_var"],
            font=("Sans", 10),
            bg="white"
        ).pack(side="left", padx=(0, 20))

        tk.Label(
            summary_row,
            text="Prototypes:",
            font=("Sans", 10, "bold"),
            bg="white"
        ).pack(side="left", padx=(0, 4))

        tk.Label(
            summary_row,
            textvariable=vars_dict["space_count_var"],
            font=("Sans", 10),
            bg="white"
        ).pack(side="left")

        # =========================
        # PanedWindow real
        # =========================
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

        paned.add(left_panel, minsize=360)
        paned.add(right_panel, minsize=520)

        self._color_evaluation_paned = paned

        # -------------------------
        # Left panel
        # -------------------------
        list_header = tk.Frame(left_panel, bg="#f4f4f4")
        list_header.pack(fill="x", padx=1, pady=(1, 0))

        list_header.grid_columnconfigure(0, minsize=110)
        list_header.grid_columnconfigure(1, minsize=210)
        list_header.grid_columnconfigure(2, minsize=260)
        list_header.grid_columnconfigure(3, weight=1)

        header_font = ("Sans", 10, "bold")

        tk.Label(
            list_header,
            text="",
            bg="#f4f4f4",
            font=header_font
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=(8, 4),
            pady=8
        )

        tk.Label(
            list_header,
            text="Label",
            bg="#f4f4f4",
            font=header_font,
            anchor="w"
        ).grid(
            row=0,
            column=1,
            sticky="w",
            padx=(2, 2),
            pady=8
        )

        value_header = tk.Frame(list_header, bg="#f4f4f4")
        value_header.grid(
            row=0,
            column=2,
            sticky="w",
            padx=(2, 8),
            pady=5
        )

        tk.Label(
            value_header,
            text="Value:",
            bg="#f4f4f4",
            font=header_font,
            anchor="w"
        ).pack(side="left", padx=(0, 6))

        color_display_combo = ttk.Combobox(
            value_header,
            textvariable=vars_dict["color_display_mode_var"],
            values=UtilsTools.get_supported_color_value_spaces(),
            state="readonly",
            width=12
        )
        color_display_combo.pack(side="left", padx=(0, 6))

        tk.Button(
            value_header,
            text="Next",
            width=6,
            command=lambda: self._rotate_color_evaluation_table_display_mode(vars_dict)
        ).pack(side="left")

        color_display_combo.bind(
            "<<ComboboxSelected>>",
            lambda e: self._refresh_color_evaluation_table_display_mode(vars_dict)
        )

        tk.Frame(left_panel, bg="#d8d8d8", height=1).pack(fill="x", padx=1)

        rows_canvas = tk.Canvas(
            left_panel,
            bg="white",
            highlightthickness=0,
            bd=0
        )

        rows_scroll = ttk.Scrollbar(
            left_panel,
            orient="vertical",
            command=rows_canvas.yview
        )

        rows_inner = tk.Frame(rows_canvas, bg="white")

        rows_inner.bind(
            "<Configure>",
            lambda e: rows_canvas.configure(scrollregion=rows_canvas.bbox("all"))
        )

        rows_canvas.create_window((0, 0), window=rows_inner, anchor="nw")
        rows_canvas.configure(yscrollcommand=rows_scroll.set)

        rows_canvas.pack(side="left", fill="both", expand=True)
        rows_scroll.pack(side="right", fill="y")

        # -------------------------
        # Right panel
        # -------------------------
        tk.Label(
            right_panel,
            text="Threshold Analysis",
            font=("Sans", 11, "bold"),
            anchor="w",
            bg="white",
            padx=12,
            pady=10
        ).pack(fill="x")

        analysis_actions = tk.Frame(right_panel, bg="white")
        analysis_actions.pack(fill="x", padx=12, pady=(0, 6))

        def _run_analysis_action(action_key, callback):
            self._set_color_evaluation_active_action(vars_dict, action_key)
            callback()

        btn_compare = tk.Button(
            analysis_actions,
            text="Compare with another color",
            command=lambda: _run_analysis_action(
                "compare",
                lambda: self._enable_color_evaluation_comparison_mode(vars_dict)
            )
        )
        btn_compare.pack(side="left", fill="x", expand=True, padx=(0, 6))

        btn_custom = tk.Button(
            analysis_actions,
            text="Evaluate custom color",
            command=lambda: _run_analysis_action(
                "custom",
                lambda: self._open_custom_color_input_dialog(vars_dict)
            )
        )
        btn_custom.pack(side="left", fill="x", expand=True, padx=(0, 6))

        btn_sample = tk.Button(
            analysis_actions,
            text="Sample from image",
            command=lambda: _run_analysis_action(
                "sample",
                lambda: self._open_color_evaluation_image_sampler(vars_dict)
            )
        )
        btn_sample.pack(side="left", fill="x", expand=True)

        analysis_extra_actions = tk.Frame(right_panel, bg="white")
        analysis_extra_actions.pack(fill="x", padx=12, pady=(0, 8))

        btn_closest = tk.Button(
            analysis_extra_actions,
            text="Find closest prototype",
            command=lambda: _run_analysis_action(
                "closest",
                lambda: self._show_color_evaluation_closest_prototypes(vars_dict)
            )
        )
        btn_closest.pack(side="left", fill="x", expand=True, padx=(0, 6))

        btn_clear = tk.Button(
            analysis_extra_actions,
            text="Clear comparison",
            command=lambda: _run_analysis_action(
                "clear",
                lambda: self._clear_color_evaluation_comparison(vars_dict)
            )
        )
        btn_clear.pack(side="left", fill="x", expand=True)

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
            anchor="w",
            bg="white",
            fg="#555555",
            font=("Sans", 9, "italic"),
            padx=12
        ).pack(fill="x", pady=(0, 8))

        # ------------------------------------------------------------------
        # Scrollable analysis body
        # ------------------------------------------------------------------
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

        def _on_analysis_mousewheel(event):
            try:
                analysis_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        analysis_canvas.bind(
            "<Enter>",
            lambda e: analysis_canvas.bind_all("<MouseWheel>", _on_analysis_mousewheel)
        )
        analysis_canvas.bind(
            "<Leave>",
            lambda e: analysis_canvas.unbind_all("<MouseWheel>")
        )

        # ------------------------------------------------------------------
        # Selected/comparison color preview
        # ------------------------------------------------------------------
        colors_row = tk.Frame(analysis_body, bg="white")
        colors_row.pack(fill="x", pady=(0, 8))

        selected_block = tk.Frame(colors_row, bg="white")
        selected_block.pack(side="left", fill="both", expand=True, padx=(0, 8))

        comparison_block = tk.Frame(colors_row, bg="white")
        comparison_block.pack(side="left", fill="both", expand=True, padx=(8, 0))

        tk.Label(
            selected_block,
            text="Selected color",
            font=("Sans", 10, "bold"),
            anchor="center",
            bg="white"
        ).pack(fill="x", pady=(0, 6))

        primary_swatch = tk.Canvas(
            selected_block,
            width=120,
            height=80,
            bg="white",
            highlightthickness=0
        )
        primary_swatch.pack(anchor="center", pady=(0, 8))

        primary_rect = primary_swatch.create_rectangle(
            10, 10, 110, 70,
            fill="#cccccc",
            outline="#606060",
            width=1
        )

        tk.Label(
            selected_block,
            textvariable=vars_dict["primary_name_var"],
            font=("Sans", 10, "bold"),
            anchor="center",
            bg="white"
        ).pack(fill="x", pady=(0, 6))

        tk.Label(
            comparison_block,
            text="Comparison color",
            font=("Sans", 10, "bold"),
            anchor="center",
            bg="white"
        ).pack(fill="x", pady=(0, 6))

        secondary_swatch = tk.Canvas(
            comparison_block,
            width=120,
            height=80,
            bg="white",
            highlightthickness=0
        )
        secondary_swatch.pack(anchor="center", pady=(0, 8))

        secondary_rect = secondary_swatch.create_rectangle(
            10, 10, 110, 70,
            fill="#f0f0f0",
            outline="#606060",
            width=1
        )

        tk.Label(
            comparison_block,
            textvariable=vars_dict["secondary_name_var"],
            font=("Sans", 10, "bold"),
            anchor="center",
            bg="white"
        ).pack(fill="x", pady=(0, 6))

        tk.Frame(analysis_body, bg="#d8d8d8", height=1).pack(fill="x", pady=(6, 6))

        # ------------------------------------------------------------------
        # Results + Membership column
        # ------------------------------------------------------------------
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

        # --------------------------------------------------
        # Right side column: Membership panel + Graph buttons
        # Hidden by default; shown only when a custom/sample color exists.
        # Membership height will be synchronized with the Results card.
        # --------------------------------------------------
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

        # Spacer aligned with the "Results" title on the left column.
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

        def _on_membership_mousewheel(event):
            try:
                membership_list_canvas.yview_scroll(
                    int(-1 * (event.delta / 120)),
                    "units"
                )
            except Exception:
                pass

        membership_list_canvas.bind(
            "<Enter>",
            lambda e: membership_list_canvas.bind_all("<MouseWheel>", _on_membership_mousewheel)
        )

        membership_list_canvas.bind(
            "<Leave>",
            lambda e: membership_list_canvas.unbind_all("<MouseWheel>")
        )

        # Graph buttons shown in the right column when Membership is visible.
        graph_buttons_card = self._create_color_evaluation_graph_buttons_card(
            right_side_column,
            vars_dict
        )
        graph_buttons_card.pack(
            side="top",
            fill="x",
            pady=(8, 0)
        )

        # ------------------------------------------------------------------
        # Results card
        # ------------------------------------------------------------------
        tk.Label(
            result_left,
            text="Results",
            font=("Sans", 10, "bold"),
            anchor="w",
            bg="white"
        ).pack(anchor="w", pady=(0, 8))

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
        result_title_label.pack(side="left", fill="x", expand=True, padx=(0, 12), pady=8)

        result_body = tk.Frame(result_card, bg="#f7f7f7")
        result_body.pack(fill="x", padx=12, pady=(10, 12))

        result_value_label = tk.Label(
            result_body,
            textvariable=vars_dict["selected_detail_var"],
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

        # ------------------------------------------------------------------
        # Color inspector
        # ------------------------------------------------------------------
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

            inspector_values.grid_columnconfigure(0, minsize=70, weight=0)
            inspector_values.grid_columnconfigure(1, weight=1)

            def _add_inspector_row(row, label_text, variable):
                tk.Label(
                    inspector_values,
                    text=label_text,
                    bg="#fafafa",
                    fg="#333333",
                    anchor="w",
                    font=("Sans", 8, "bold")
                ).grid(row=row, column=0, sticky="w", pady=(0, 2), padx=(0, 8))

                tk.Label(
                    inspector_values,
                    textvariable=variable,
                    bg="#fafafa",
                    fg="#222222",
                    anchor="w",
                    justify="left",
                    font=("Consolas", 8),
                    wraplength=390
                ).grid(row=row, column=1, sticky="ew", pady=(0, 2))

            _add_inspector_row(0, "CIELAB", vars_dict["inspector_lab_var"])
            _add_inspector_row(1, "RGB", vars_dict["inspector_rgb_var"])
            _add_inspector_row(2, "HEX", vars_dict["inspector_hex_var"])
            _add_inspector_row(3, "CIELUV", vars_dict["inspector_luv_var"])
            _add_inspector_row(4, "LCh", vars_dict["inspector_lch_var"])
            _add_inspector_row(5, "CIE1931", vars_dict["inspector_cie1931_var"])

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

        # ------------------------------------------------------------------
        # Store references
        # ------------------------------------------------------------------
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

                result_title_label.config(wraplength=title_wrap)
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

        has_custom = (
            vars_dict.get("secondary_mode") == "custom"
            and vars_dict.get("secondary_custom_lab") is not None
            and vars_dict.get("secondary_custom_rgb") is not None
            and vars_dict.get("secondary_custom_hex") is not None
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

        # Make sure the right column is visible.
        try:
            if right_side_column is not None and not right_side_column.winfo_ismapped():
                right_side_column.grid(
                    row=0,
                    column=1,
                    sticky="new",
                    padx=(8, 0)
                )
        except Exception:
            pass

        # Clear old membership rows
        for child in list_inner.winfo_children():
            child.destroy()

        # Refresh usable graph buttons
        self._update_color_evaluation_graph_buttons(vars_dict)

        has_custom_membership = (
            sample_lab is not None
            and vars_dict.get("secondary_mode") == "custom"
        )

        # --------------------------------------------------
        # No custom/sample color:
        # hide Membership Degree, keep Graphs on the right.
        # --------------------------------------------------
        if not has_custom_membership:
            try:
                # Keep spacer so Graphs starts aligned with the Results card,
                # not with the "Results" title.
                if (
                    membership_title_spacer is not None
                    and not membership_title_spacer.winfo_ismapped()
                ):
                    membership_title_spacer.pack(
                        side="top",
                        fill="x",
                        pady=(0, 8),
                        before=graph_buttons_card
                    )

                membership_right.pack_forget()

                if graph_buttons_card is not None:
                    graph_buttons_card.pack_configure(pady=(0, 0))

            except Exception:
                pass

            try:
                membership_list_canvas.update_idletasks()
                membership_list_canvas.configure(
                    scrollregion=membership_list_canvas.bbox("all")
                )
                membership_list_canvas.yview_moveto(0)
            except Exception:
                pass

            return

        # --------------------------------------------------
        # Custom/sample color active:
        # show Membership Degree above Graphs.
        # --------------------------------------------------
        try:
            if (
                membership_title_spacer is not None
                and not membership_title_spacer.winfo_ismapped()
            ):
                membership_title_spacer.pack(
                    side="top",
                    fill="x",
                    pady=(0, 8),
                    before=graph_buttons_card
                )

            if not membership_right.winfo_ismapped():
                membership_right.pack(
                    side="top",
                    fill="x",
                    before=graph_buttons_card
                )

            if graph_buttons_card is not None:
                graph_buttons_card.pack_configure(pady=(8, 0))

            if result_card is not None:
                result_h = max(result_card.winfo_height(), 180)
                membership_right.configure(height=result_h)

        except Exception:
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
            "color_display_mode_var": tk.StringVar(value="CIELAB"),

            "analysis_mode_var": tk.StringVar(value="Select a color from the list."),
            "primary_name_var": tk.StringVar(value="None"),
            "secondary_name_var": tk.StringVar(value="None"),

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

        active_bg = "#dfeeff"
        active_fg = "#003366"
        active_border = "#4a78b8"

        normal_bg = "#f0f0f0"
        normal_fg = "#000000"
        normal_border = "#d9d9d9"

        for key, button in buttons.items():
            try:
                if key == action_key:
                    button.configure(
                        bg=active_bg,
                        fg=active_fg,
                        activebackground=active_bg,
                        activeforeground=active_fg,
                        relief="sunken",
                        bd=2,
                        highlightbackground=active_border,
                        highlightcolor=active_border
                    )
                else:
                    button.configure(
                        bg=normal_bg,
                        fg=normal_fg,
                        activebackground=normal_bg,
                        activeforeground=normal_fg,
                        relief="raised",
                        bd=1,
                        highlightbackground=normal_border,
                        highlightcolor=normal_border
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
        except Exception:
            loaded = None

        if not loaded or not isinstance(loaded.get("color_data"), dict):
            vars_dict["space_name_var"].set("Invalid file")
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
        vars_dict["space_count_var"].set(str(len(valid_rows)))


    def _extract_color_space_rows(self, data_source):
        """
        Compatibility wrapper. Logic lives in ColorEvaluationManager.
        """
        manager = self._get_color_evaluation_manager()
        return manager.extract_color_space_rows(data_source)



    def _set_custom_color_as_evaluation_comparison(self, vars_dict, sample_lab, sample_rgb, sample_hex):
        """Set a manually entered custom color as the active comparison color."""
        vars_dict["comparison_mode"] = False
        vars_dict["secondary_label"] = None

        vars_dict["secondary_mode"] = "custom"
        vars_dict["secondary_custom_lab"] = tuple(float(v) for v in sample_lab)
        vars_dict["secondary_custom_rgb"] = tuple(int(round(v)) for v in sample_rgb)
        vars_dict["secondary_custom_hex"] = str(sample_hex)
        vars_dict["secondary_custom_name"] = "Custom Color"

        vars_dict["closest_ranking"] = []
        vars_dict["closest_best"] = None
        vars_dict["closest_metric"] = None

        if vars_dict.get("primary_label"):
            vars_dict["analysis_mode_var"].set(
                "Custom color active. Select prototypes to compare manually or use 'Find closest prototype'."
            )
        else:
            vars_dict["analysis_mode_var"].set(
                "Custom color loaded. Use 'Find closest prototype' or select a prototype."
            )

        self._refresh_color_evaluation_comparison(vars_dict)

        # Repaint row highlights so only primary stays highlighted
        for label, refs in vars_dict.get("color_row_refs", {}).items():
            bg = "#e8f0ff" if label == vars_dict.get("primary_label") else "white"

            refs["frame"].configure(bg=bg)
            refs["content"].configure(bg=bg)

            for widget in refs["widgets"]:
                try:
                    widget.configure(bg=bg)
                except Exception:
                    pass


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
                value_label.configure(
                    text=UtilsTools.format_lab_color_value(lab, display_mode)
                )
            except Exception:
                value_label.configure(text="-")


    def _rotate_color_evaluation_table_display_mode(self, vars_dict):
        """
        Rotate the value column through the available color spaces.
        """
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
            next_space = spaces[0]
        else:
            next_space = spaces[(spaces.index(current) + 1) % len(spaces)]

        vars_dict["color_display_mode_var"].set(next_space)
        self._refresh_color_evaluation_table_display_mode(vars_dict)


    def _render_color_evaluation_cards(self, vars_dict, data_source):
        """Render color prototypes as selectable rows aligned with the header."""
        rows_inner = vars_dict["rows_inner"]

        for child in rows_inner.winfo_children():
            child.destroy()

        vars_dict["color_row_refs"] = {}
        vars_dict["primary_label"] = None
        vars_dict["secondary_label"] = None
        vars_dict["comparison_mode"] = False
        vars_dict["analysis_view_mode"] = "comparison"

        vars_dict["secondary_mode"] = None
        vars_dict["secondary_custom_lab"] = None
        vars_dict["secondary_custom_rgb"] = None
        vars_dict["secondary_custom_hex"] = None
        vars_dict["secondary_custom_name"] = "Custom Color"

        vars_dict["analysis_mode_var"].set("Select a color from the list.")

        rows = self._extract_color_space_rows(data_source)

        if not rows:
            tk.Label(
                rows_inner,
                text="No color space data available.",
                anchor="w",
                bg="white",
                font=("Sans", 10)
            ).pack(fill="x", padx=12, pady=12)

            self._clear_color_evaluation_analysis(vars_dict)
            return

        def _get_display_mode():
            try:
                return vars_dict["color_display_mode_var"].get()
            except Exception:
                return "CIELAB"

        def _highlight_rows():
            primary = vars_dict.get("primary_label")
            secondary = vars_dict.get("secondary_label")

            for label, refs in vars_dict["color_row_refs"].items():
                if label == primary and label == secondary:
                    bg = "#dfeeff"
                elif label == primary:
                    bg = "#e8f0ff"
                elif label == secondary:
                    bg = "#fff4dd"
                else:
                    bg = "white"

                refs["frame"].configure(bg=bg)
                refs["content"].configure(bg=bg)

                for widget in refs["widgets"]:
                    try:
                        widget.configure(bg=bg)
                    except Exception:
                        pass

        def _on_select_row(label):
            refs_map = vars_dict["color_row_refs"]

            if label not in refs_map:
                return

            if vars_dict.get("comparison_mode", False):
                primary = vars_dict.get("primary_label")

                if primary is None:
                    vars_dict["primary_label"] = label
                    vars_dict["secondary_label"] = None

                    vars_dict["secondary_mode"] = None
                    vars_dict["secondary_custom_lab"] = None
                    vars_dict["secondary_custom_rgb"] = None
                    vars_dict["secondary_custom_hex"] = None

                    vars_dict["analysis_mode_var"].set(
                        "Primary color selected. Choose another color to compare."
                    )
                else:
                    if label == primary:
                        vars_dict["analysis_mode_var"].set(
                            "Comparison mode active. Choose a different color than the selected one."
                        )
                        self._refresh_color_evaluation_comparison(vars_dict)
                        _highlight_rows()
                        return

                    vars_dict["secondary_label"] = label
                    vars_dict["secondary_mode"] = "row"

                    vars_dict["secondary_custom_lab"] = None
                    vars_dict["secondary_custom_rgb"] = None
                    vars_dict["secondary_custom_hex"] = None

                    vars_dict["analysis_mode_var"].set(
                        "Comparison mode active. Click another color to update the comparison or clear it to exit."
                    )
            else:
                vars_dict["primary_label"] = label
                vars_dict["secondary_label"] = None

                if (
                    vars_dict.get("secondary_mode") == "custom"
                    and vars_dict.get("secondary_custom_lab") is not None
                ):
                    vars_dict["analysis_mode_var"].set(
                        "Custom comparison active. Click different selected colors to compare against the custom color."
                    )
                else:
                    vars_dict["analysis_mode_var"].set("Single color selected.")

            self._refresh_color_evaluation_comparison(vars_dict)
            _highlight_rows()

        for label, lab in rows:
            try:
                rgb = UtilsTools.lab_to_rgb(lab)
                rgb = tuple(max(0, min(255, int(round(v)))) for v in rgb)
            except Exception:
                rgb = (200, 200, 200)

            hex_color = self._safe_hex_from_rgb(rgb)

            row = tk.Frame(
                rows_inner,
                bg="white",
                bd=1,
                relief="solid",
                cursor="hand2"
            )
            row.pack(fill="x", padx=8, pady=3)

            content = tk.Frame(row, bg="white")
            content.pack(fill="x", padx=8, pady=7)

            content.grid_columnconfigure(0, minsize=110)
            content.grid_columnconfigure(1, minsize=210)
            content.grid_columnconfigure(2, minsize=260)
            content.grid_columnconfigure(3, weight=1)

            swatch = tk.Canvas(
                content,
                width=90,
                height=42,
                bg="white",
                highlightthickness=0
            )
            swatch.grid(row=0, column=0, sticky="w", padx=(8, 4), pady=6)

            swatch.create_rectangle(
                6, 6, 84, 36,
                fill=hex_color,
                outline="#404040",
                width=1
            )

            lbl_name = tk.Label(
                content,
                text=label,
                anchor="w",
                justify="left",
                bg="white",
                font=("Sans", 10, "bold")
            )
            lbl_name.grid(row=0, column=1, sticky="w", padx=(2, 2))

            lbl_value = tk.Label(
                content,
                text=UtilsTools.format_lab_color_value(lab, _get_display_mode()),
                anchor="center",
                justify="center",
                bg="white",
                font=("Consolas", 9)
            )
            lbl_value.grid(row=0, column=2, sticky="w", padx=(2, 8))

            widgets = [
                swatch,
                lbl_name,
                lbl_value,
            ]

            vars_dict["color_row_refs"][label] = {
                "frame": row,
                "content": content,
                "widgets": widgets,
                "lab": lab,
                "rgb": rgb,
                "hex": hex_color,
                "value_label": lbl_value,
            }

            for widget in [row, content, *widgets]:
                widget.bind("<Button-1>", lambda e, lbl=label: _on_select_row(lbl))

        if rows:
            first_label = rows[0][0]
            vars_dict["primary_label"] = first_label
            vars_dict["secondary_label"] = None
            vars_dict["analysis_mode_var"].set("Single color selected.")
            self._refresh_color_evaluation_comparison(vars_dict)
            _highlight_rows()


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


    def _clear_color_evaluation_analysis(self, vars_dict):
        """Reset the analysis panel."""
        vars_dict["primary_name_var"].set("None")
        vars_dict["secondary_name_var"].set("None")

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



    def _enable_color_evaluation_comparison_mode(self, vars_dict):
        """Enable comparison mode so clicked colors become comparison colors."""
        primary = vars_dict.get("primary_label")

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

        if vars_dict.get("primary_label"):
            vars_dict["analysis_mode_var"].set("Single color selected.")
        else:
            vars_dict["analysis_mode_var"].set("Select a color from the list.")

        self._refresh_color_evaluation_comparison(vars_dict)

        for label, refs in vars_dict.get("color_row_refs", {}).items():
            bg = "#e8f0ff" if label == vars_dict.get("primary_label") else "white"

            refs["frame"].configure(bg=bg)
            refs["content"].configure(bg=bg)

            for widget in refs["widgets"]:
                try:
                    widget.configure(bg=bg)
                except Exception:
                    pass


    def _refresh_color_evaluation_comparison(self, vars_dict):
        """
        Refresh the right-side analysis panel for single, row-comparison, or custom-comparison mode.
        """
        vars_dict["analysis_view_mode"] = "comparison"

        refs_map = vars_dict.get("color_row_refs", {})
        primary_label = vars_dict.get("primary_label")
        secondary_label = vars_dict.get("secondary_label")
        secondary_mode = vars_dict.get("secondary_mode")

        self._set_color_evaluation_inspector_layout(vars_dict)

        primary_refs = refs_map.get(primary_label)
        secondary_refs = refs_map.get(secondary_label)

        if not primary_refs:
            self._clear_color_evaluation_analysis(vars_dict)
            return

        p_lab = primary_refs["lab"]
        p_rgb = primary_refs.get("rgb")
        p_hex = primary_refs["hex"]

        vars_dict["primary_name_var"].set(primary_label)
        vars_dict["primary_swatch"].itemconfig(vars_dict["primary_rect"], fill=p_hex)

        self._update_color_evaluation_conversion_inspector(
            vars_dict=vars_dict,
            lab=p_lab,
            rgb=p_rgb,
            hex_color=p_hex,
            name=primary_label,
            source="prototype"
        )

        if secondary_mode not in ("row", "custom"):
            vars_dict["secondary_name_var"].set("None")
            vars_dict["secondary_swatch"].itemconfig(vars_dict["secondary_rect"], fill="#f0f0f0")

            self._update_color_evaluation_result_card(
                vars_dict=vars_dict,
                title="Single color selected. Comparison not active.",
                detail="",
                summary=(
                    "Use 'Compare with another color' to evaluate the selected color "
                    "against a second prototype, or 'Evaluate custom color' to compare it "
                    "against a manually entered color."
                ),
                status="unavailable"
            )

            if (
                vars_dict.get("secondary_custom_lab") is not None
                and vars_dict.get("secondary_custom_rgb") is not None
                and vars_dict.get("secondary_custom_hex") is not None
            ):
                self._update_color_evaluation_conversion_inspector(
                    vars_dict=vars_dict,
                    lab=vars_dict.get("secondary_custom_lab"),
                    rgb=vars_dict.get("secondary_custom_rgb"),
                    hex_color=vars_dict.get("secondary_custom_hex"),
                    name=vars_dict.get("secondary_custom_name", "Custom Color"),
                    source="custom"
                )

            self._update_color_evaluation_membership_panel(vars_dict, sample_lab=None)
            return

        if secondary_mode == "row":
            if not secondary_refs:
                vars_dict["secondary_name_var"].set("None")
                vars_dict["secondary_swatch"].itemconfig(vars_dict["secondary_rect"], fill="#f0f0f0")
                self._update_color_evaluation_result_card(
                    vars_dict=vars_dict,
                    title="Comparison color not available.",
                    detail="",
                    summary="Select another color from the list or clear the comparison.",
                    status="unavailable"
                )
                return

            s_lab = secondary_refs["lab"]
            s_rgb = secondary_refs.get("rgb")
            s_hex = secondary_refs["hex"]
            secondary_display_name = secondary_label

            self._update_color_evaluation_conversion_inspector(
                vars_dict=vars_dict,
                lab=s_lab,
                rgb=s_rgb,
                hex_color=s_hex,
                name=secondary_display_name,
                source="comparison prototype"
            )

        else:
            s_lab = vars_dict.get("secondary_custom_lab")
            s_rgb = vars_dict.get("secondary_custom_rgb")
            s_hex = vars_dict.get("secondary_custom_hex")

            if s_lab is None or s_rgb is None or s_hex is None:
                vars_dict["secondary_name_var"].set("None")
                vars_dict["secondary_swatch"].itemconfig(vars_dict["secondary_rect"], fill="#f0f0f0")
                self._update_color_evaluation_result_card(
                    vars_dict=vars_dict,
                    title="Custom comparison color not available.",
                    detail="",
                    summary="Enter a valid custom color or clear the comparison.",
                    status="unavailable"
                )
                return

            secondary_display_name = vars_dict.get("secondary_custom_name", "Custom Color")

            self._update_color_evaluation_conversion_inspector(
                vars_dict=vars_dict,
                lab=s_lab,
                rgb=s_rgb,
                hex_color=s_hex,
                name=secondary_display_name,
                source="custom"
            )

        vars_dict["secondary_name_var"].set(secondary_display_name)
        vars_dict["secondary_swatch"].itemconfig(vars_dict["secondary_rect"], fill=s_hex)

        if secondary_mode == "custom":
            self._update_color_evaluation_membership_panel(vars_dict, sample_lab=s_lab)
        else:
            self._update_color_evaluation_membership_panel(vars_dict, sample_lab=None)

        metric_name = self.threshold_settings.get("metric", "CIEDE2000")

        evaluation = self.evaluate_color_difference_threshold(
            sample_lab=p_lab,
            prototype_lab=s_lab,
            metric=metric_name,
            threshold_settings=self.threshold_settings
        )

        metric_value = evaluation.get("metric_value", evaluation.get("delta_e"))
        status = evaluation.get("status", "unavailable")

        if metric_value is None:
            self._update_color_evaluation_result_card(
                vars_dict=vars_dict,
                title=evaluation.get("evaluation", "Metric not available"),
                detail="Unable to compute selected metric",
                summary=evaluation.get("summary_visual", evaluation.get("summary", "")),
                status=status
            )
            return

        self._update_color_evaluation_result_card(
            vars_dict=vars_dict,
            title=evaluation.get("evaluation", "No evaluation available"),
            detail=evaluation.get("detail", f"{metric_name} = {metric_value:.3f}"),
            summary=evaluation.get("summary_visual", evaluation.get("summary", "")),
            status=status
        )

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
        if not hasattr(self, "load_images_names") or not self.load_images_names:
            self.custom_warning(
                "No Images Available",
                "No images are currently loaded.",
                parent=getattr(self, "_color_evaluation_window", None)
            )
            return

        if not hasattr(self, "images") or not self.images:
            self.custom_warning(
                "No Images Available",
                "Image data are not available.",
                parent=getattr(self, "_color_evaluation_window", None)
            )
            return

        parent = getattr(self, "_color_evaluation_window", self.root)

        popup = tk.Toplevel(parent)
        popup.title("Sample Color from Image")
        popup.configure(bg="#eeeeee")
        popup.resizable(True, True)
        popup.transient(parent)
        popup.grab_set()

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
            "drag_start": None,
            "rect_id": None,
            "sample_rgb": None,
            "sample_lab": None,
            "sample_hex": None,
        }

        # =====================================================================
        # Main shell
        # =====================================================================
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

        # =====================================================================
        # Image selector
        # =====================================================================
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

        for wid, path in self.load_images_names.items():
            image_ids.append(wid)
            image_names.append(os.path.basename(path))

        selected_image_var = tk.StringVar(value=image_names[0] if image_names else "")

        image_combo = ttk.Combobox(
            selector_row,
            textvariable=selected_image_var,
            state="readonly",
            values=image_names,
            width=55
        )
        image_combo.pack(side="left", fill="x", expand=True)

        # =====================================================================
        # Image preview
        # =====================================================================
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
            value="Click to sample one pixel, or drag to sample the average color of a region."
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

        # =====================================================================
        # Sampled color panel
        # =====================================================================
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

        use_button = ttk.Button(
            sample_row,
            text="Use sampled color",
            state="disabled"
        )
        use_button.pack(side="right")

        # =====================================================================
        # Bottom buttons
        # =====================================================================
        footer = tk.Frame(panel, bg="white")
        footer.pack(fill="x", padx=14, pady=(0, 12))

        tk.Button(
            footer,
            text="Cancel",
            width=12,
            command=popup.destroy
        ).pack(side="right")

        # =====================================================================
        # Helpers
        # =====================================================================
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
                return Image.open(img_obj).convert("RGB")

            raise ValueError("Unsupported image format.")

        def _canvas_to_image_xy(canvas_x, canvas_y):
            if state["pil_img"] is None:
                return None

            x = int(round((canvas_x - state["offset_x"]) / state["scale"]))
            y = int(round((canvas_y - state["offset_y"]) / state["scale"]))

            w, h = state["pil_img"].size

            x = max(0, min(w - 1, x))
            y = max(0, min(h - 1, y))

            return x, y

        def _set_sample_rgb(rgb, source_text="image sample"):
            try:
                rgb = UtilsTools.safe_rgb_tuple(rgb)
                lab = UtilsTools.rgb_to_lab(rgb)
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

        def _clear_sample():
            state["sample_rgb"] = None
            state["sample_lab"] = None
            state["sample_hex"] = None

            rgb_var.set("RGB: -")
            lab_var.set("LAB: -")
            hex_var.set("HEX: -")

            preview_canvas.itemconfig(preview_rect, fill="#d9d9d9")
            use_button.config(state="disabled")

        def _load_selected_image(*_):
            window_id = _get_selected_window_id()

            if window_id is None or window_id not in self.images:
                return

            try:
                pil_img = _image_object_to_pil(self.images[window_id])
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

            resized = pil_img.resize((disp_w, disp_h), Image.LANCZOS)
            state["photo"] = ImageTk.PhotoImage(resized)

            canvas.delete("all")
            canvas.create_image(
                state["offset_x"],
                state["offset_y"],
                image=state["photo"],
                anchor="nw",
                tags=("image",)
            )

            _clear_sample()

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

            if abs(right - left) <= 1 and abs(bottom - top) <= 1:
                rgb = state["pil_img"].getpixel((left, top))
                _set_sample_rgb(rgb, source_text="image pixel")
                return

            crop = state["pil_img"].crop((left, top, right + 1, bottom + 1))
            arr = np.array(crop, dtype=float)

            if arr.ndim == 2:
                mean_value = int(round(float(np.mean(arr))))
                rgb = (mean_value, mean_value, mean_value)
            else:
                mean_rgb = np.mean(arr.reshape(-1, arr.shape[-1])[:, :3], axis=0)
                rgb = tuple(int(round(v)) for v in mean_rgb)

            _set_sample_rgb(rgb, source_text="image ROI average")

        def _on_mouse_down(event):
            if state["pil_img"] is None:
                return

            state["drag_start"] = (event.x, event.y)

            if state["rect_id"] is not None:
                try:
                    canvas.delete(state["rect_id"])
                except Exception:
                    pass

            state["rect_id"] = canvas.create_rectangle(
                event.x,
                event.y,
                event.x,
                event.y,
                outline="#ffcc00",
                width=2
            )

        def _on_mouse_drag(event):
            if state["drag_start"] is None or state["rect_id"] is None:
                return

            x0, y0 = state["drag_start"]

            canvas.coords(
                state["rect_id"],
                x0,
                y0,
                event.x,
                event.y
            )

        def _on_mouse_up(event):
            if state["drag_start"] is None:
                return

            x0, y0 = state["drag_start"]
            state["drag_start"] = None

            _sample_roi_from_canvas(x0, y0, event.x, event.y)

        def _use_sampled_color():
            if (
                state["sample_rgb"] is None
                or state["sample_lab"] is None
                or state["sample_hex"] is None
            ):
                return

            self._set_custom_color_as_evaluation_comparison(
                vars_dict=vars_dict,
                sample_lab=state["sample_lab"],
                sample_rgb=state["sample_rgb"],
                sample_hex=state["sample_hex"]
            )

            vars_dict["secondary_custom_name"] = "Image Sample"

            self._update_color_evaluation_conversion_inspector(
                vars_dict=vars_dict,
                lab=state["sample_lab"],
                rgb=state["sample_rgb"],
                hex_color=state["sample_hex"],
                name="Image Sample",
                source="image"
            )

            popup.destroy()

        use_button.configure(command=_use_sampled_color)

        image_combo.bind("<<ComboboxSelected>>", _load_selected_image)

        canvas.bind("<ButtonPress-1>", _on_mouse_down)
        canvas.bind("<B1-Motion>", _on_mouse_drag)
        canvas.bind("<ButtonRelease-1>", _on_mouse_up)

        popup.bind("<Escape>", lambda e: popup.destroy())

        _load_selected_image()






    def _get_custom_color_input_mode_help(self, mode):
        """
        Compatibility wrapper. Logic lives in ColorEvaluationManager.
        """
        manager = self._get_color_evaluation_manager()
        return manager.get_custom_color_input_mode_help(mode)




    def _open_custom_color_input_dialog(self, vars_dict):
        """Open a dialog to input and evaluate a custom color in RGB, LAB, or HEX."""
        data_source = vars_dict.get("loaded_space_data") or {}

        if not self._extract_color_space_rows(data_source):
            self.custom_warning(
                "No Color Space Loaded",
                "Load a valid color space before evaluating a custom color.",
                parent=getattr(self, "_color_evaluation_window", None)
            )
            return

        parent = getattr(self, "_color_evaluation_window", self.root)

        def on_submit(color_name, sample_lab, sample_rgb, sample_hex, dialog, input_vars):
            dialog.destroy()

            self._set_custom_color_as_evaluation_comparison(
                vars_dict=vars_dict,
                sample_lab=sample_lab,
                sample_rgb=sample_rgb,
                sample_hex=sample_hex
            )

        self._open_custom_color_dialog(
            parent=parent,
            title="Evaluate Custom Color",
            subtitle="Compare a custom RGB, LAB or HEX color",
            submit_text="Evaluate",
            require_name=False,
            default_name="Custom Color",
            on_submit=on_submit
        )


    
    def _open_custom_color_dialog(
        self,
        parent=None,
        title="Custom Color",
        subtitle="RGB, LAB or HEX",
        submit_text="OK",
        require_name=False,
        default_name="Custom Color",
        on_submit=None,
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
            Header subtitle.
        submit_text : str
            Text for the submit button.
        require_name : bool
            Whether to request a color name.
        default_name : str
            Initial color name when require_name=True.
        on_submit : callable
            Callback called as:
                on_submit(name, sample_lab, sample_rgb, sample_hex, dialog, input_vars)
        """
        parent = self._get_valid_dialog_parent(
            parent or getattr(self, "_color_evaluation_window", self.root)
        )

        dialog = tk.Toplevel(parent)
        dialog.title(title)
        dialog.resizable(False, False)
        dialog.configure(bg="#eeeeee")
        dialog.transient(parent)
        dialog.grab_set()

        WIN_W = 700
        WIN_H = 450 if require_name else 400

        try:
            if parent is not None and hasattr(parent, "winfo_x"):
                self.center_popup_to_parent(dialog, WIN_W, WIN_H, parent=parent)
            else:
                self.center_popup(dialog, WIN_W, WIN_H)
        except Exception:
            self.center_popup(dialog, WIN_W, WIN_H)

        input_vars = {
            "mode_var": tk.StringVar(value="RGB"),
            "name_var": tk.StringVar(value=default_name),
            "v1_var": tk.StringVar(value=""),
            "v2_var": tk.StringVar(value=""),
            "v3_var": tk.StringVar(value=""),
            "hex_var": tk.StringVar(value=""),
            "status_var": tk.StringVar(value="Enter a color value."),
            "limits_var": tk.StringVar(value=""),
            "example_var": tk.StringVar(value=""),
            "preview_hex_var": tk.StringVar(value="#D9D9D9"),
        }

        state = {"suspend_validation": False}

        # ------------------------------------------------------------------
        # Local styling
        # ------------------------------------------------------------------
        style = ttk.Style(dialog)

        try:
            style.configure(
                "CustomColor.TCombobox",
                padding=4
            )
            style.configure(
                "CustomColor.Primary.TButton",
                font=("Helvetica", 10, "bold"),
                padding=(14, 8)
            )
            style.configure(
                "CustomColor.Secondary.TButton",
                font=("Helvetica", 10),
                padding=(14, 8)
            )
        except Exception:
            pass

        # ------------------------------------------------------------------
        # Main shell
        # ------------------------------------------------------------------
        outer = tk.Frame(dialog, bg="#eeeeee")
        outer.pack(fill="both", expand=True, padx=14, pady=14)

        panel = tk.Frame(outer, bg="white", bd=1, relief="solid")
        panel.pack(fill="both", expand=True)

        header = tk.Frame(panel, bg="#f6f6f6", height=58)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(
            header,
            text=title,
            font=("Sans", 13, "bold"),
            bg="#f6f6f6",
            fg="#222222",
            anchor="w",
            padx=16
        ).pack(side="left", fill="y")

        tk.Label(
            header,
            text=subtitle,
            font=("Sans", 10, "italic"),
            fg="#666666",
            bg="#f6f6f6",
            padx=16
        ).pack(side="right", fill="y")

        body = tk.Frame(panel, bg="white")
        body.pack(fill="both", expand=True, padx=18, pady=16)

        body.grid_columnconfigure(0, weight=1, minsize=255)
        body.grid_columnconfigure(1, weight=0, minsize=16)
        body.grid_columnconfigure(2, weight=1, minsize=235)

        # ------------------------------------------------------------------
        # Left panel
        # ------------------------------------------------------------------
        left_panel = tk.Frame(body, bg="white")
        left_panel.grid(row=0, column=0, sticky="nsew")

        left_panel.grid_columnconfigure(0, minsize=115, weight=0)
        left_panel.grid_columnconfigure(1, minsize=165, weight=0)
        left_panel.grid_columnconfigure(2, weight=1)

        current_row = 0

        if require_name:
            tk.Label(
                left_panel,
                text="Color name",
                bg="white",
                anchor="w",
                font=("Sans", 10, "bold")
            ).grid(row=current_row, column=0, sticky="w", pady=(2, 10))

            name_entry = tk.Entry(
                left_panel,
                textvariable=input_vars["name_var"],
                width=21,
                font=("Sans", 10)
            )
            name_entry.grid(row=current_row, column=1, sticky="w", pady=(2, 10))

            current_row += 1

        tk.Label(
            left_panel,
            text="Input mode",
            bg="white",
            anchor="w",
            font=("Sans", 10, "bold")
        ).grid(row=current_row, column=0, sticky="w", pady=(2, 12))

        mode_combo = ttk.Combobox(
            left_panel,
            textvariable=input_vars["mode_var"],
            state="readonly",
            width=18,
            values=["RGB", "LAB", "HEX"],
            style="CustomColor.TCombobox"
        )
        mode_combo.grid(row=current_row, column=1, sticky="w", pady=(2, 12))

        pick_color_btn = ttk.Button(
            left_panel,
            text="Pick Color...",
            width=14
        )
        pick_color_btn.grid(row=current_row, column=2, sticky="w", padx=(8, 0), pady=(2, 12))

        input_start_row = current_row + 1

        lbl1 = tk.Label(left_panel, text="R:", bg="white", anchor="w", font=("Sans", 10))
        entry1 = tk.Entry(left_panel, textvariable=input_vars["v1_var"], width=21, font=("Sans", 10))

        lbl2 = tk.Label(left_panel, text="G:", bg="white", anchor="w", font=("Sans", 10))
        entry2 = tk.Entry(left_panel, textvariable=input_vars["v2_var"], width=21, font=("Sans", 10))

        lbl3 = tk.Label(left_panel, text="B:", bg="white", anchor="w", font=("Sans", 10))
        entry3 = tk.Entry(left_panel, textvariable=input_vars["v3_var"], width=21, font=("Sans", 10))

        hex_label = tk.Label(left_panel, text="HEX:", bg="white", anchor="w", font=("Sans", 10))
        hex_entry = tk.Entry(left_panel, textvariable=input_vars["hex_var"], width=23, font=("Sans", 10))

        # ------------------------------------------------------------------
        # Separator
        # ------------------------------------------------------------------
        separator = tk.Frame(body, bg="#dddddd", width=1)
        separator.grid(row=0, column=1, sticky="ns", padx=10)

        # ------------------------------------------------------------------
        # Right panel
        # ------------------------------------------------------------------
        right_panel = tk.Frame(body, bg="white", width=270, height=220)
        right_panel.grid(row=0, column=2, sticky="nsew")
        right_panel.grid_propagate(False)
        right_panel.pack_propagate(False)

        guide_card = tk.Frame(
            right_panel,
            bg="#fafafa",
            bd=1,
            relief="solid",
            width=260,
            height=100
        )
        guide_card.pack(fill="x", pady=(0, 12))
        guide_card.pack_propagate(False)

        tk.Label(
            guide_card,
            text="Input Guide",
            bg="#fafafa",
            fg="#222222",
            font=("Sans", 10, "bold"),
            anchor="w",
            padx=12,
            pady=7
        ).pack(fill="x")

        tk.Label(
            guide_card,
            textvariable=input_vars["limits_var"],
            bg="#fafafa",
            fg="#333333",
            justify="left",
            anchor="nw",
            wraplength=230,
            padx=12
        ).pack(fill="x", pady=(0, 5))

        tk.Label(
            guide_card,
            textvariable=input_vars["example_var"],
            bg="#fafafa",
            fg="#666666",
            justify="left",
            anchor="w",
            wraplength=230,
            font=("Sans", 9, "italic"),
            padx=12
        ).pack(fill="x", pady=(0, 8))

        preview_card = tk.Frame(
            right_panel,
            bg="#fafafa",
            bd=1,
            relief="solid",
            width=260,
            height=160
        )
        preview_card.pack(fill="x")
        preview_card.pack_propagate(False)

        preview_header = tk.Frame(preview_card, bg="#fafafa")
        preview_header.pack(fill="x")

        tk.Label(
            preview_header,
            text="Preview",
            bg="#fafafa",
            fg="#222222",
            font=("Sans", 10, "bold"),
            anchor="w",
            padx=12,
            pady=9
        ).pack(side="left")

        tk.Label(
            preview_header,
            textvariable=input_vars["preview_hex_var"],
            bg="#fafafa",
            fg="#555555",
            font=("Sans", 9),
            padx=12
        ).pack(side="right")

        preview_canvas = tk.Canvas(
            preview_card,
            width=205,
            height=66,
            bg="#fafafa",
            highlightthickness=0,
            bd=0
        )
        preview_canvas.pack(padx=12, pady=(0, 8))

        preview_rect = preview_canvas.create_rectangle(
            10, 8, 195, 58,
            fill="#d9d9d9",
            outline="#555555",
            width=1
        )

        # ------------------------------------------------------------------
        # Status + buttons
        # ------------------------------------------------------------------
        footer = tk.Frame(panel, bg="white")
        footer.pack(fill="x", padx=16, pady=(0, 14))

        status_label = tk.Label(
            footer,
            textvariable=input_vars["status_var"],
            bg="white",
            fg="#8a4f00",
            anchor="w",
            justify="left",
            wraplength=390,
            font=("Sans", 9, "italic")
        )
        status_label.pack(side="left", fill="x", expand=True)

        buttons_frame = tk.Frame(footer, bg="white")
        buttons_frame.pack(side="right")

        btn_cancel = ttk.Button(
            buttons_frame,
            text="Cancel",
            command=dialog.destroy,
            style="CustomColor.Secondary.TButton"
        )
        btn_cancel.pack(side="left", padx=(0, 8))

        btn_submit = ttk.Button(
            buttons_frame,
            text=submit_text,
            state="disabled",
            style="CustomColor.Primary.TButton"
        )
        btn_submit.pack(side="left")

        # ------------------------------------------------------------------
        # Helpers
        # ------------------------------------------------------------------
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

        def _validate_name():
            if not require_name:
                return True, ""

            name = input_vars["name_var"].get().strip()

            if not name:
                return False, "Enter a color name."

            return True, ""

        def _validate_live(*_):
            if state["suspend_validation"]:
                return

            name_ok, name_message = _validate_name()
            if not name_ok:
                _reset_preview()
                _set_status(name_message, ok=False)
                btn_submit.config(state="disabled")
                return

            mode = input_vars["mode_var"].get().strip().upper()

            ok, message, _, sample_rgb, _ = self._normalize_custom_color_input(
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

                _set_status(message or "Valid color input.", ok=True)
                btn_submit.config(state="normal")
            else:
                _reset_preview()
                _set_status(message or "Enter a valid color value.", ok=False)
                btn_submit.config(state="disabled")

        def _refresh_inputs(*_):
            state["suspend_validation"] = True

            try:
                mode = input_vars["mode_var"].get().strip().upper()
                help_data = self._get_custom_color_input_mode_help(mode)

                input_vars["limits_var"].set(help_data["limits"])
                input_vars["example_var"].set(help_data["example"])

                # Hide all input widgets first
                for widget in (
                    lbl1, entry1,
                    lbl2, entry2,
                    lbl3, entry3,
                    hex_label, hex_entry
                ):
                    try:
                        widget.grid_remove()
                    except Exception:
                        pass

                # Important:
                # Always clear fields when switching input mode.
                # This avoids validating previous RGB values as LAB, LAB values as RGB, etc.
                _clear_numeric_fields()
                _clear_hex_field()

                _reset_preview()
                _set_status("Enter a color value.", ok=False)
                btn_submit.config(state="disabled")

                if mode in ("RGB", "LAB"):
                    lbl1.config(text=f"{help_data['labels'][0]}:")
                    lbl2.config(text=f"{help_data['labels'][1]}:")
                    lbl3.config(text=f"{help_data['labels'][2]}:")

                    lbl1.grid(row=input_start_row, column=0, sticky="w", pady=7)
                    entry1.grid(row=input_start_row, column=1, sticky="w", pady=7)

                    lbl2.grid(row=input_start_row + 1, column=0, sticky="w", pady=7)
                    entry2.grid(row=input_start_row + 1, column=1, sticky="w", pady=7)

                    lbl3.grid(row=input_start_row + 2, column=0, sticky="w", pady=7)
                    entry3.grid(row=input_start_row + 2, column=1, sticky="w", pady=7)

                    dialog.after_idle(entry1.focus_set)

                else:
                    hex_label.grid(row=input_start_row, column=0, sticky="w", pady=7)
                    hex_entry.grid(row=input_start_row, column=1, sticky="w", pady=7)

                    dialog.after_idle(hex_entry.focus_set)

            finally:
                state["suspend_validation"] = False

        def _submit():
            name_ok, name_message = _validate_name()
            if not name_ok:
                _set_status(name_message, ok=False)
                self.custom_warning(
                    "Invalid Color Name",
                    name_message,
                    parent=dialog
                )
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
                self.custom_warning(
                    "Invalid Custom Color",
                    message,
                    parent=dialog
                )
                return

            color_name = input_vars["name_var"].get().strip() if require_name else default_name

            if callable(on_submit):
                on_submit(
                    color_name,
                    sample_lab,
                    sample_rgb,
                    sample_hex,
                    dialog,
                    input_vars
                )
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
            self._open_square_color_picker(
                parent=dialog,
                initial_rgb=_get_current_rgb_for_picker(),
                on_apply=_apply_picker_result
            )

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

        dialog.bind(
            "<Return>",
            lambda e: btn_submit.invoke() if str(btn_submit["state"]) == "normal" else None
        )
        dialog.bind("<Escape>", lambda e: dialog.destroy())

        _refresh_inputs()



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


    def _open_square_color_picker(self, parent, initial_rgb=(217, 217, 217), on_apply=None):
        """
        Open an optimized custom color picker with:
        - saturation/value square
        - hue slider
        - Select Color button

        The picker is optimized by:
        - building the hue bar only once
        - rebuilding the saturation/value square only when hue changes
        - using numpy instead of per-pixel putpixel loops
        """
        popup = tk.Toplevel(parent)
        popup.title("Color Picker")
        popup.configure(bg="#1f2430")
        popup.resizable(False, False)
        popup.transient(parent)
        popup.grab_set()

        WIN_W, WIN_H = 460, 440

        try:
            self.center_popup_to_parent(popup, WIN_W, WIN_H, parent=parent)
        except Exception:
            self.center_popup(popup, WIN_W, WIN_H)

        # ------------------------------------------------------------------
        # Initial HSV from RGB
        # ------------------------------------------------------------------
        r0, g0, b0 = initial_rgb
        h0, s0, v0 = colorsys.rgb_to_hsv(
            r0 / 255.0,
            g0 / 255.0,
            b0 / 255.0
        )

        state = {
            "h": h0,
            "s": s0,
            "v": v0,
            "sv_photo": None,
            "hue_photo": None,
        }

        sv_w, sv_h = 385, 215
        hue_w, hue_h = 385, 18

        # ------------------------------------------------------------------
        # Layout
        # ------------------------------------------------------------------
        main = tk.Frame(popup, bg="#1f2430")
        main.pack(fill="both", expand=True, padx=14, pady=14)

        header = tk.Frame(main, bg="#202531")
        header.pack(fill="x", pady=(0, 10))

        tk.Label(
            header,
            text="Pick your Color",
            font=("Sans", 12, "bold"),
            bg="#202531",
            fg="white",
            anchor="w",
            padx=10,
            pady=8
        ).pack(side="left", fill="y")

        tk.Label(
            header,
            text="Saturation / Brightness + Hue",
            font=("Sans", 9, "italic"),
            bg="#202531",
            fg="#bfc7d5",
            anchor="e",
            padx=10
        ).pack(side="right", fill="y")

        sv_canvas = tk.Canvas(
            main,
            width=sv_w,
            height=sv_h,
            bg="black",
            highlightthickness=1,
            highlightbackground="#40485a",
            bd=0
        )
        sv_canvas.pack()

        hue_canvas = tk.Canvas(
            main,
            width=hue_w,
            height=hue_h,
            bg="#1f2430",
            highlightthickness=0,
            bd=0
        )
        hue_canvas.pack(pady=(12, 0))

        # ------------------------------------------------------------------
        # Info panel
        # ------------------------------------------------------------------
        info_frame = tk.Frame(main, bg="#1f2430")
        info_frame.pack(fill="x", pady=(12, 0))

        hex_var = tk.StringVar()
        rgb_var = tk.StringVar()
        hsv_var = tk.StringVar()

        hex_card = tk.Frame(info_frame, bg="#252b38", bd=1, relief="solid")
        hex_card.pack(side="left", fill="x", expand=True, padx=(0, 6))

        rgb_card = tk.Frame(info_frame, bg="#252b38", bd=1, relief="solid")
        rgb_card.pack(side="left", fill="x", expand=True, padx=(6, 6))

        hsv_card = tk.Frame(info_frame, bg="#252b38", bd=1, relief="solid")
        hsv_card.pack(side="left", fill="x", expand=True, padx=(6, 0))

        tk.Label(
            hex_card,
            text="HEX",
            bg="#252b38",
            fg="#cfd6e6",
            font=("Sans", 8)
        ).pack(pady=(4, 0))

        tk.Label(
            hex_card,
            textvariable=hex_var,
            bg="#252b38",
            fg="white",
            font=("Consolas", 10, "bold")
        ).pack(pady=(0, 5))

        tk.Label(
            rgb_card,
            text="RGB",
            bg="#252b38",
            fg="#cfd6e6",
            font=("Sans", 8)
        ).pack(pady=(4, 0))

        tk.Label(
            rgb_card,
            textvariable=rgb_var,
            bg="#252b38",
            fg="white",
            font=("Consolas", 10)
        ).pack(pady=(0, 5))

        tk.Label(
            hsv_card,
            text="HSV",
            bg="#252b38",
            fg="#cfd6e6",
            font=("Sans", 8)
        ).pack(pady=(4, 0))

        tk.Label(
            hsv_card,
            textvariable=hsv_var,
            bg="#252b38",
            fg="white",
            font=("Consolas", 10)
        ).pack(pady=(0, 5))

        # ------------------------------------------------------------------
        # Buttons
        # ------------------------------------------------------------------
        button_row = tk.Frame(main, bg="#1f2430")
        button_row.pack(fill="x", pady=(14, 0))

        # ------------------------------------------------------------------
        # Image generation helpers
        # ------------------------------------------------------------------
        def _clamp(value, low, high):
            return max(low, min(high, value))

        def _get_current_rgb():
            rr, gg, bb = colorsys.hsv_to_rgb(
                state["h"],
                state["s"],
                state["v"]
            )

            return (
                int(round(rr * 255)),
                int(round(gg * 255)),
                int(round(bb * 255)),
            )

        def _rgb_to_hex(rgb):
            return "#{:02X}{:02X}{:02X}".format(*rgb)

        def _build_hue_image_fast():
            """
            Build hue bar once using numpy.
            """
            xs = np.linspace(0.0, 1.0, hue_w, dtype=np.float32)

            rgb_row = np.zeros((hue_w, 3), dtype=np.uint8)

            for x, h_value in enumerate(xs):
                rr, gg, bb = colorsys.hsv_to_rgb(float(h_value), 1.0, 1.0)
                rgb_row[x] = [
                    int(rr * 255),
                    int(gg * 255),
                    int(bb * 255)
                ]

            img_array = np.tile(rgb_row[np.newaxis, :, :], (hue_h, 1, 1))
            return ImageTk.PhotoImage(Image.fromarray(img_array, "RGB"))

        def _build_sv_image_fast(h_value):
            """
            Build saturation/value square using numpy.

            This is much faster than nested putpixel loops.
            """
            s_values = np.linspace(0.0, 1.0, sv_w, dtype=np.float32)
            v_values = np.linspace(1.0, 0.0, sv_h, dtype=np.float32)

            s_grid, v_grid = np.meshgrid(s_values, v_values)

            # HSV to RGB vectorized manually
            h = float(h_value) * 6.0
            i = int(np.floor(h)) % 6
            f = h - np.floor(h)

            p = v_grid * (1.0 - s_grid)
            q = v_grid * (1.0 - f * s_grid)
            t = v_grid * (1.0 - (1.0 - f) * s_grid)

            if i == 0:
                r, g, b = v_grid, t, p
            elif i == 1:
                r, g, b = q, v_grid, p
            elif i == 2:
                r, g, b = p, v_grid, t
            elif i == 3:
                r, g, b = p, q, v_grid
            elif i == 4:
                r, g, b = t, p, v_grid
            else:
                r, g, b = v_grid, p, q

            img_array = np.dstack((r, g, b))
            img_array = np.clip(img_array * 255.0, 0, 255).astype(np.uint8)

            return ImageTk.PhotoImage(Image.fromarray(img_array, "RGB"))

        # ------------------------------------------------------------------
        # Canvas items
        # ------------------------------------------------------------------
        state["hue_photo"] = _build_hue_image_fast()
        state["sv_photo"] = _build_sv_image_fast(state["h"])

        sv_image_id = sv_canvas.create_image(
            0,
            0,
            anchor="nw",
            image=state["sv_photo"]
        )

        hue_image_id = hue_canvas.create_image(
            0,
            0,
            anchor="nw",
            image=state["hue_photo"]
        )

        sv_marker = sv_canvas.create_oval(
            0,
            0,
            0,
            0,
            outline="white",
            width=2
        )

        sv_marker_shadow = sv_canvas.create_oval(
            0,
            0,
            0,
            0,
            outline="#222222",
            width=1
        )

        hue_marker = hue_canvas.create_rectangle(
            0,
            0,
            0,
            hue_h,
            outline="white",
            width=2
        )

        # ------------------------------------------------------------------
        # Redraw helpers
        # ------------------------------------------------------------------
        def _update_info():
            rgb = _get_current_rgb()
            hex_value = _rgb_to_hex(rgb)

            hex_var.set(hex_value)
            rgb_var.set(f"{rgb[0]}, {rgb[1]}, {rgb[2]}")

            h_deg = int(round(state["h"] * 360))
            s_pct = int(round(state["s"] * 100))
            v_pct = int(round(state["v"] * 100))
            hsv_var.set(f"{h_deg}°, {s_pct}%, {v_pct}%")

        def _redraw_markers_only():
            """
            Move markers only. Do not rebuild images.
            This is used while dragging inside the saturation/value square.
            """
            x_sv = int(state["s"] * (sv_w - 1))
            y_sv = int((1.0 - state["v"]) * (sv_h - 1))

            sv_canvas.coords(
                sv_marker_shadow,
                x_sv - 7,
                y_sv - 7,
                x_sv + 7,
                y_sv + 7
            )

            sv_canvas.coords(
                sv_marker,
                x_sv - 6,
                y_sv - 6,
                x_sv + 6,
                y_sv + 6
            )

            x_h = int(state["h"] * (hue_w - 1))
            hue_canvas.coords(
                hue_marker,
                x_h - 3,
                0,
                x_h + 3,
                hue_h
            )

            _update_info()

        def _redraw_sv_image_and_markers():
            """
            Rebuild saturation/value square only when hue changes.
            """
            state["sv_photo"] = _build_sv_image_fast(state["h"])
            sv_canvas.itemconfig(sv_image_id, image=state["sv_photo"])
            _redraw_markers_only()

        # ------------------------------------------------------------------
        # Events
        # ------------------------------------------------------------------
        def _on_sv_event(event):
            x = _clamp(event.x, 0, sv_w - 1)
            y = _clamp(event.y, 0, sv_h - 1)

            state["s"] = x / max(sv_w - 1, 1)
            state["v"] = 1.0 - (y / max(sv_h - 1, 1))

            # Fast: only move marker and update labels
            _redraw_markers_only()

        def _on_hue_event(event):
            x = _clamp(event.x, 0, hue_w - 1)

            state["h"] = x / max(hue_w - 1, 1)

            # Rebuild square only when hue changes
            _redraw_sv_image_and_markers()

        sv_canvas.bind("<Button-1>", _on_sv_event)
        sv_canvas.bind("<B1-Motion>", _on_sv_event)

        hue_canvas.bind("<Button-1>", _on_hue_event)
        hue_canvas.bind("<B1-Motion>", _on_hue_event)

        # ------------------------------------------------------------------
        # Apply selected color
        # ------------------------------------------------------------------
        def _select_color():
            rgb = _get_current_rgb()
            hex_value = _rgb_to_hex(rgb)

            if callable(on_apply):
                on_apply(rgb, hex_value)

            popup.destroy()

        tk.Button(
            button_row,
            text="Cancel",
            width=13,
            command=popup.destroy
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            button_row,
            text="Select Color",
            width=14,
            command=_select_color
        ).pack(side="right")

        _redraw_markers_only()



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

        sample_lab = vars_dict.get("secondary_custom_lab")
        sample_rgb = vars_dict.get("secondary_custom_rgb")
        sample_hex = vars_dict.get("secondary_custom_hex")
        sample_name = vars_dict.get("secondary_custom_name", "Custom Color")

        metric_name = self.threshold_settings.get("metric", "CIEDE2000")
        vars_dict["analysis_view_mode"] = "closest"

        if (
            vars_dict.get("secondary_mode") != "custom"
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
            top_n=7
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
            title=f"Closest prototype: {best['label']}",
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

        return manager.resolve_volume_limits(
            volume_limits=getattr(self, "volume_limits", None),
            fuzzy_color_space=vars_dict.get("loaded_fuzzy_color_space"),
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
        sample_lab = vars_dict.get("secondary_custom_lab")
        sample_rgb = vars_dict.get("secondary_custom_rgb")
        sample_hex = vars_dict.get("secondary_custom_hex")

        has_custom = (
            vars_dict.get("secondary_mode") == "custom"
            and sample_lab is not None
            and sample_rgb is not None
            and sample_hex is not None
        )

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

        for label, lab in rows:
            try:
                lab_arr = np.asarray(lab, dtype=float).reshape(-1)[:3]

                color_data[label] = {
                    "positive_prototype": lab_arr
                }

                proto_hex = self._get_evaluation_proto_hex(vars_dict, label)
                hex_color[proto_hex] = lab_arr

            except Exception:
                continue

        core = vars_dict.get("loaded_cores")
        alpha = vars_dict.get("loaded_prototypes")
        support = vars_dict.get("loaded_supports")

        volume_limits = self._get_color_evaluation_volume_limits(vars_dict)

        closest_best = vars_dict.get("closest_best")
        closest_label = None
        closest_lab = None
        closest_hex = None

        if closest_best:
            closest_label = closest_best.get("label")

            for label, lab in rows:
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

        fig = VisualManager.plot_more_combined_3D(
            filename=ctx["filename"],
            color_data=ctx["color_data"],
            core=ctx["core"],
            alpha=ctx["alpha"],
            support=ctx["support"],
            volume_limits=ctx["volume_limits"],
            hex_color=ctx["hex_color"],
            selected_options=["Representative"],
            custom_lab=ctx.get("custom_lab"),
            custom_hex=ctx.get("custom_hex", "#ff0000"),
            closest_label=ctx.get("closest_label"),
            closest_lab=ctx.get("closest_lab"),
            closest_hex=ctx.get("closest_hex", "#000000"),
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
        """
        Open membership degree bar chart for the current custom/sample color.
        Requires custom/sample color and fuzzy membership data.
        """
        sample_lab = vars_dict.get("secondary_custom_lab")

        if vars_dict.get("secondary_mode") != "custom" or sample_lab is None:
            self.custom_warning(
                "Custom Color Required",
                "Use 'Evaluate custom color' or 'Sample from image' first.",
                parent=getattr(self, "_color_evaluation_window", None)
            )
            return

        memberships = self._calculate_evaluation_memberships(vars_dict, sample_lab)

        if not memberships:
            self.custom_warning(
                "Memberships Not Available",
                "The loaded color space has no fuzzy membership data available.",
                parent=getattr(self, "_color_evaluation_window", None)
            )
            return

        fig = VisualManager.plot_color_evaluation_membership_bar(
            memberships=memberships,
            title="Membership degrees for custom color",
            top_n=10,
        )

        self._show_color_eval_plotly_figure_in_browser(
            fig,
            filename_prefix="color_eval_memberships"
        )


    def _open_color_evaluation_component_plot(self, vars_dict):
        """
        Open signed component-differences plot.

        Works with:
        - prototype vs prototype comparison;
        - prototype vs custom/sample color comparison.
        """
        refs_map = vars_dict.get("color_row_refs", {})
        primary_label = vars_dict.get("primary_label")
        secondary_label = vars_dict.get("secondary_label")
        secondary_mode = vars_dict.get("secondary_mode")

        primary_refs = refs_map.get(primary_label)

        if not primary_refs:
            self.custom_warning(
                "Comparison Required",
                "Select a prototype first.",
                parent=getattr(self, "_color_evaluation_window", None)
            )
            return

        p_lab = primary_refs.get("lab")

        if secondary_mode == "row":
            secondary_refs = refs_map.get(secondary_label)
            if not secondary_refs:
                self.custom_warning(
                    "Comparison Required",
                    "Compare the selected prototype with another prototype first.",
                    parent=getattr(self, "_color_evaluation_window", None)
                )
                return

            s_lab = secondary_refs.get("lab")
            title = f"Component differences | {primary_label} vs {secondary_label}"

        elif secondary_mode == "custom":
            s_lab = vars_dict.get("secondary_custom_lab")

            if s_lab is None:
                self.custom_warning(
                    "Comparison Required",
                    "Evaluate a custom color or sample a color from an image first.",
                    parent=getattr(self, "_color_evaluation_window", None)
                )
                return

            custom_name = vars_dict.get("secondary_custom_name", "Custom Color")
            title = f"Component differences | {primary_label} vs {custom_name}"

        else:
            self.custom_warning(
                "Comparison Required",
                "Use 'Compare with another color' or 'Evaluate custom color' first.",
                parent=getattr(self, "_color_evaluation_window", None)
            )
            return

        components = self._calculate_color_evaluation_component_differences(
            p_lab,
            s_lab
        )

        fig = VisualManager.plot_color_evaluation_component_differences(
            components=components,
            title=title
        )

        self._show_color_eval_plotly_figure_in_browser(
            fig,
            filename_prefix="color_eval_components"
        )


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
        has_primary = vars_dict.get("primary_label") is not None

        has_custom = (
            secondary_mode == "custom"
            and vars_dict.get("secondary_custom_lab") is not None
            and vars_dict.get("secondary_custom_rgb") is not None
            and vars_dict.get("secondary_custom_hex") is not None
        )

        available = manager.get_color_evaluation_available_graph_keys(
            rows=rows,
            secondary_mode=secondary_mode,
            has_primary=has_primary,
            secondary_label_available=vars_dict.get("secondary_label") is not None,
            has_custom=has_custom,
            has_fuzzy_color_space=vars_dict.get("loaded_fuzzy_color_space") is not None,
        )

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
        """
        Refresh visible graph buttons.

        Layout behavior:
        - Single color / prototype-prototype comparison:
            narrow right column, one button per row.
        - Custom/sample color:
            compact right column, two-button layout when possible.
        """
        refs = vars_dict.get("analysis_result_refs", {})

        side_card = refs.get("graph_buttons_card")
        results_columns = refs.get("results_columns")
        right_side_column = refs.get("right_side_column")
        membership_right = refs.get("membership_right")

        if side_card is None:
            return

        body = getattr(side_card, "_pyfcs_graph_body", None)
        specs = getattr(side_card, "_pyfcs_graph_specs", {})

        if body is None:
            return

        available = self._get_color_evaluation_available_graph_keys(vars_dict)

        secondary_mode = vars_dict.get("secondary_mode")

        has_custom = (
            secondary_mode == "custom"
            and vars_dict.get("secondary_custom_lab") is not None
            and vars_dict.get("secondary_custom_rgb") is not None
            and vars_dict.get("secondary_custom_hex") is not None
        )

        # --------------------------------------------------
        # Dynamic right-column width
        # --------------------------------------------------
        if has_custom:
            # Width of the whole right column in custom/sample mode
            right_width = 185

            layout = [
                ["3d", "ab"],
                ["lc", "lch"],
                ["top7"],
                ["memberships"],
                ["components"],
            ]
        else:
            # Width of the right column in single / prototype-prototype mode
            right_width = 140

            layout = [
                ["3d"],
                ["ab"],
                ["lc"],
                ["lch"],
                ["components"],
            ]

        try:
            if results_columns is not None:
                results_columns.grid_columnconfigure(
                    1,
                    weight=0,
                    minsize=right_width
                )
        except Exception:
            pass

        try:
            if right_side_column is not None:
                right_side_column.configure(width=right_width)
        except Exception:
            pass

        try:
            if membership_right is not None:
                membership_right.configure(width=right_width)
        except Exception:
            pass

        # --------------------------------------------------
        # Rebuild visible buttons
        # --------------------------------------------------
        for child in body.winfo_children():
            child.destroy()

        visible_rows = []

        for row_keys in layout:
            visible_keys = [
                key
                for key in row_keys
                if key in available and key in specs
            ]

            if visible_keys:
                visible_rows.append(visible_keys)

        for row_index, row_keys in enumerate(visible_rows):
            row = tk.Frame(body, bg="#fafafa")
            row.pack(
                fill="x",
                pady=(0, 4) if row_index < len(visible_rows) - 1 else (0, 0)
            )

            for button_index, key in enumerate(row_keys):
                spec = specs[key]

                btn = tk.Button(
                    row,
                    text=spec["text"],
                    command=spec["command"],
                    width=8 if has_custom else 14
                )

                btn.pack(
                    side="left",
                    fill="x",
                    expand=True,
                    padx=(0, 4) if button_index < len(row_keys) - 1 else (0, 0)
                )


















def start_up():
    root = tk.Tk()
    app = PyFCSApp(root)
    root.mainloop()

if __name__ == '__main__':
    start_up()

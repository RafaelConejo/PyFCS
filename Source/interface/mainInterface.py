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
import itertools
import threading
import numpy as np
import tkinter as tk
from skimage import color
import tkinter.font as tkFont
from functools import partial
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from PIL import Image, ImageTk, ImageDraw, ImageFont, ImageEnhance
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from tkinter import ttk, Menu, filedialog, messagebox, Scrollbar, DISABLED, NORMAL

from PyQt5.QtCore import QUrl, QEventLoop
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QApplication, QMainWindow
from PyQt5.QtWebEngineWidgets import QWebEngineView

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
        self.app_qt = None
        self.more_graph_window = None

        # Centralized image/icon references to avoid garbage collection
        self.ui_icons = {}
        
        # ---------------------------------------------------------------------
        # Main window configuration
        # ---------------------------------------------------------------------
        self.root.title("PyFCS Interface")
        self.root.geometry("1200x650")
        # self.root.attributes("-fullscreen", True)
        self.root.configure(bg="gray82")

        # ---------------------------------------------------------------------
        # Local UI helpers
        # ---------------------------------------------------------------------
        def create_toolbar_button(parent, text, command, image=None, side="left", padx=4, pady=2, width=None):
            """
            Create a toolbar button with consistent styling.
            """
            btn_kwargs = {
                "parent": parent,
                "text": text,
                "command": command,
                "compound": "left",
                "padx": 6,
                "pady": 3,
            }

            if image is not None:
                btn_kwargs["image"] = image

            if width is not None:
                btn_kwargs["width"] = width

            btn = tk.Button(
                btn_kwargs["parent"],
                text=btn_kwargs["text"],
                command=btn_kwargs["command"],
                compound=btn_kwargs["compound"],
                padx=btn_kwargs["padx"],
                pady=btn_kwargs["pady"],
                image=btn_kwargs.get("image"),
                font=("Sans", 10, "bold"),
            )
            btn.pack(side=side, padx=padx, pady=pady)
            return btn

        def bind_vertical_mousewheel(canvas):
            """
            Enable mouse wheel scrolling only while the pointer is inside the target canvas.
            Supports Windows, macOS, and Linux.
            """
            system_name = platform.system()

            def on_mousewheel(event):
                if system_name in ("Windows", "Darwin"):
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

            def on_mousewheel_linux_up(event):
                canvas.yview_scroll(-1, "units")

            def on_mousewheel_linux_down(event):
                canvas.yview_scroll(1, "units")

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
        main_frame = tk.Frame(self.root, bg="gray82")
        main_frame.pack(fill="x", padx=10, pady=(10, 6))

        # Load icons once
        icon_size = (35, 35)
        load_image_icon = self.load_toolbar_icon("LoadImage.png", icon_size)
        save_image_icon = self.load_toolbar_icon("SaveImage.png", icon_size)
        new_fcs_icon = self.load_toolbar_icon("NewFCS1.png", icon_size)
        load_fcs_icon = self.load_toolbar_icon("LoadFCS.png", icon_size)
        at_icon = self.load_toolbar_icon("AT.png", icon_size)
        pt_icon = self.load_toolbar_icon("PT.png", icon_size)
        evaluate_icon = self.load_toolbar_icon("evaluateColor.png", icon_size)

        image_manager_frame = tk.LabelFrame(
            main_frame,
            text="Image Manager",
            font=("Segoe UI", 10),
            bg="gray95",
            padx=8,
            pady=8
        )
        image_manager_frame.pack(side="left", fill="y", expand=False, padx=4, pady=4)

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

        fuzzy_manager_frame = tk.LabelFrame(
            main_frame,
            text="Fuzzy Color Space Manager",
            font=("Segoe UI", 10),
            bg="gray95",
            padx=8,
            pady=8
        )
        fuzzy_manager_frame.pack(side="left", fill="y", expand=False, padx=4, pady=4)

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

        color_evaluation_frame = tk.LabelFrame(
            main_frame,
            text="Color Difference Evaluation",
            font=("Segoe UI", 10),
            bg="gray95",
            padx=8,
            pady=8
        )
        color_evaluation_frame.pack(side="left", fill="y", expand=False, padx=4, pady=4)

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
        main_content_frame = tk.Frame(self.root, bg="gray82")
        main_content_frame.pack(fill="both", expand=True, padx=10, pady=(4, 10))

        main_paned = ttk.Panedwindow(main_content_frame, orient="horizontal")
        main_paned.pack(fill="both", expand=True)

        # Left pane: wider image display area
        image_area_frame = tk.LabelFrame(
            main_paned,
            text="Image Display",
            bg="gray95",
            padx=8,
            pady=8
        )
        self.image_canvas = tk.Canvas(
            image_area_frame,
            bg="white",
            borderwidth=2,
            relief="ridge",
            highlightthickness=0
        )
        self.image_canvas.pack(fill="both", expand=True)

        # Right pane: notebook area
        notebook_container = tk.Frame(main_paned, bg="gray82")
        self.notebook = ttk.Notebook(notebook_container)
        self.notebook.pack(fill="both", expand=True)

        # Make the image display area wider than before
        main_paned.add(image_area_frame, weight=5)
        main_paned.add(notebook_container, weight=4)

        def set_initial_main_sash():
            """
            Set the initial split so the image display area is visibly wider.
            """
            total_width = main_paned.winfo_width()
            if total_width > 1:
                main_paned.sashpos(0, int(total_width * 0.40))

        self.root.after(120, set_initial_main_sash)

        # ---------------------------------------------------------------------
        # Tab: Model 3D
        # ---------------------------------------------------------------------
        model_3d_tab = tk.Frame(self.notebook, bg="gray95")
        self.notebook.add(model_3d_tab, text="Model 3D")

        self.model_3d_options = {}

        buttons_frame = tk.Frame(model_3d_tab, bg="gray95")
        buttons_frame.pack(side="top", fill="x", pady=5)

        options = ["Representative", "Core", "0.5-cut", "Support"]
        for option in options:
            var = tk.BooleanVar(value=(option == "Representative"))
            self.model_3d_options[option] = var
            tk.Checkbutton(
                buttons_frame,
                text=option,
                variable=var,
                bg="gray95",
                font=("Sans", 10),
                command=self.on_option_select
            ).pack(side="left", padx=16)

        # Internal split for the 3D model tab
        paned = tk.PanedWindow(
            model_3d_tab,
            orient="horizontal",
            sashrelief="raised",
            bg="gray95",
            sashwidth=6
        )
        paned.pack(fill="both", expand=True)

        # 3D display area: larger
        self.Canvas1 = tk.Frame(
            paned,
            bg="white",
            borderwidth=2,
            relief="ridge",
            width=760
        )
        paned.add(self.Canvas1, stretch="always", minsize=500)

        # Color button panel: narrower
        self.colors_frame = tk.Frame(
            paned,
            bg="gray95",
            width=130
        )
        paned.add(self.colors_frame, minsize=110)

        self.scrollable_canvas = tk.Canvas(
            self.colors_frame,
            bg="gray95",
            highlightthickness=0,
            width=135
        )
        self.scrollable_canvas.pack(side="left", fill="both", expand=True)

        self.scrollbar = tk.Scrollbar(
            self.colors_frame,
            orient="vertical",
            command=self.scrollable_canvas.yview
        )
        self.scrollbar.pack(side="right", fill="y")

        self.scrollable_canvas.configure(yscrollcommand=self.scrollbar.set)

        self.inner_frame = tk.Frame(self.scrollable_canvas, bg="gray95")
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

        self.color_buttons_frame = tk.Frame(
            self.inner_frame,
            bg=self.inner_frame["bg"]
        )
        self.color_buttons_frame.pack(fill="x", pady=5)

        button_style = {
            "width": 10,
            "height": 1,
            "font": ("Sans", 10),
            "relief": "raised",
            "bd": 2,
            "cursor": "hand2",
        }

        self.select_all_button = tk.Button(
            self.color_buttons_frame,
            text="Select All",
            command=self.select_all_color,
            **button_style
        )
        if self.COLOR_SPACE:
            self.select_all_button.pack(pady=4)

        self.deselect_all_button = tk.Button(
            self.color_buttons_frame,
            text="Deselect All",
            command=self.deselect_all_color,
            **button_style
        )
        if self.COLOR_SPACE:
            self.deselect_all_button.pack(pady=4)

        # ---------------------------------------------------------------------
        # Tab: Data
        # ---------------------------------------------------------------------
        data_tab = tk.Frame(self.notebook, bg="gray95")
        self.notebook.add(data_tab, text="Data")

        name_data = tk.Frame(data_tab, bg="#e0e0e0", pady=5)
        name_data.pack(fill="x")

        tk.Label(
            name_data,
            text="Name:",
            font=("Helvetica", 12, "bold"),
            bg="#e0e0e0"
        ).pack(side="top", pady=5)

        self.file_name_entry = tk.Entry(
            name_data,
            font=("Helvetica", 12),
            width=30,
            justify="center"
        )
        self.file_name_entry.pack(side="top", pady=5)
        self.file_name_entry.insert(0, "")

        canvas_frame = tk.Frame(data_tab, bg="white")
        canvas_frame.pack(fill="both", expand=True)

        self.data_window = tk.Canvas(
            canvas_frame,
            bg="white",
            borderwidth=2,
            relief="ridge",
            highlightthickness=0
        )
        self.data_window.grid(row=0, column=0, sticky="nsew")

        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        self.data_scrollbar_v = Scrollbar(
            canvas_frame,
            orient="vertical",
            command=self.data_window.yview
        )
        self.data_scrollbar_v.grid(row=0, column=1, sticky="ns")

        self.data_scrollbar_h = Scrollbar(
            canvas_frame,
            orient="horizontal",
            command=self.data_window.xview
        )
        self.data_scrollbar_h.grid(row=1, column=0, sticky="ew")

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

        self.inner_frame_data = tk.Frame(self.data_window, bg="white")
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

        bottom_bar = tk.Frame(data_tab, bg="#e0e0e0", pady=5)
        bottom_bar.pack(fill="x", side="bottom")

        button_container = tk.Frame(bottom_bar, bg="#e0e0e0")
        button_container.pack(pady=5)

        add_button = tk.Button(
            button_container,
            text="Add New Color",
            font=("Helvetica", 12, "bold"),
            bg="#E0F2E9",
            command=self.addColor_data_window
        )
        add_button.pack(side="left", padx=20)

        apply_button = tk.Button(
            button_container,
            text="Apply Changes",
            font=("Helvetica", 12, "bold"),
            bg="#E0F2E9",
            command=self.apply_changes
        )
        apply_button.pack(side="left", padx=20)

        delete_button = tk.Button(
        button_container,
            text="Delete Color Space",
            font=("Helvetica", 12, "bold"),
            bg="#F8D7DA",
            command=self.delete_color_space
        )
        delete_button.pack(side="left", padx=20)






    ########################################################################################### Utils APP ###########################################################################################
    def exit_app(self):
        """
        Prompt the user to confirm exiting the application.
        If the user confirms, close the application.
        """
        confirm_exit = messagebox.askyesno("Exit", "Are you sure you want to exit?")
        if confirm_exit:
            self.root.destroy()



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



    def custom_warning(self, title="Warning", message="Warning"):
        """Creates a custom, aesthetic warning message window with gray tones."""
        warning_win = tk.Toplevel(self.root)
        warning_win.title(title)
        warning_win.configure(bg="#f5f5f5")  # Light gray background

        # Warning text
        label = tk.Label(warning_win, text=message, font=("Sans", 11, "bold"), 
                        fg="#333333", bg="#f5f5f5", wraplength=350)
        label.pack(pady=15, padx=20)

        # Stylized close button
        btn_ok = tk.Button(warning_win, text="OK", font=("Sans", 11, "bold"), 
                        bg="#999999", fg="white", bd=0, padx=10, pady=0, 
                        relief="flat", activebackground="#8c8c8c", 
                        command=warning_win.destroy)
        btn_ok.pack(pady=5)

        # Bind keyboard keys to close the warning (Enter and Escape)
        warning_win.bind("<Return>", lambda event: warning_win.destroy())
        warning_win.bind("<Escape>", lambda event: warning_win.destroy())

        # Optionally focus on the button so Enter works immediately
        btn_ok.focus_set()
        
        # Center the window
        self.center_popup(warning_win, 400, 100)

        # Keep the window on top of the main one
        warning_win.transient(self.root)
        warning_win.grab_set()


    
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
        if hasattr(self, 'load_window'):  # Check if the loading window exists
            self.load_window.destroy()



    def about_info(self):
        """Displays a popup window with 'About' information."""
        # Create a new top-level window (popup)
        about_window = tk.Toplevel(self.root)  
        about_window.title("About PyFCS")  # Set the title of the popup window
        
        # Disable resizing of the popup window
        about_window.resizable(False, False)

        # Center the popup window
        self.center_popup(about_window, 600, 200)

        # Create and add a label with the software information
        about_label = tk.Label(
            about_window, 
            text="PyFCS: Python Fuzzy Color Software\n"
                "A color modeling Python Software based on Fuzzy Color Spaces.\n"
                "Version 1.0\n\n"
                "Contact: rafaconejo@ugr.es", 
            padx=20, pady=20, font=("Helvetica", 12, "bold"), justify="center",
            bg="#f0f0f0", fg="#333333"  # Background color and text color
        )
        about_label.pack(pady=20)  # Add the label to the popup window with padding

        # Create a frame to style the close button
        button_frame = tk.Frame(about_window, bg="#f0f0f0")
        button_frame.pack(pady=10)

        # Create a 'Close' button to close the popup window with enhanced styling
        close_button = tk.Button(
            button_frame,
            text="Close",
            command=about_window.destroy,
            font=("Helvetica", 10, "bold"),
            bg="#884786",  # Green background
            fg="white",    # White text
            relief=tk.FLAT,
            padx=10,
            pady=5
        )
        close_button.pack(pady=10)  # Add the button to the frame



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
            filename = UtilsTools.prompt_file_selection("fuzzy_color_spaces/")
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



    def create_color_space(self):
        """
        Create a fuzzy color space from the selected colors and prompt the user for its name.
        Once confirmed, save the color space.
        """
        selected_colors_lab = {
            name: np.array([data["lab"]["L"], data["lab"]["A"], data["lab"]["B"]])
            if isinstance(data["lab"], dict)
            else np.array(data["lab"])
            for name, data in self.color_checks.items()
            if data["var"].get()
        }

        if len(selected_colors_lab) < 2:
            self.custom_warning("Warning", "At least two colors must be selected to create the Color Space.")
            return

        popup = tk.Toplevel(self.root)
        popup.title("Color Space Name")
        popup.resizable(False, False)
        popup.transient(self.root)
        popup.grab_set()
        self.center_popup(popup, 320, 120)

        tk.Label(popup, text="Name for the fuzzy color space:").pack(pady=(12, 5))

        name_entry = tk.Entry(popup)
        name_entry.pack(pady=5)
        name_entry.focus_set()

        def on_ok():
            name = name_entry.get().strip()
            if not name:
                self.custom_warning("Warning", "Please enter a name for the fuzzy color space.")
                return

            popup.destroy()
            self.save_cs(name, selected_colors_lab)

        ok_button = tk.Button(popup, text="OK", command=on_ok)
        ok_button.pack(pady=8)

        popup.bind("<Return>", lambda event: on_ok())
        popup.bind("<Escape>", lambda event: popup.destroy())



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
            if total_lines <= 0:
                return
            progress_percentage = (current_line / total_lines) * 100
            self.progress["value"] = progress_percentage
            self.load_window.update_idletasks()

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
                self.root.after(0, lambda msg=error_msg: self.custom_warning("Error", msg))
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



    def addColor(self, window, colors):
        """
        Opens a popup window to add a new color by entering LAB values or selecting a color from a color wheel.
        Returns the color name and LAB values if the user confirms the input.
        """
        popup = tk.Toplevel(window)
        popup.title("Add New Color")
        popup.geometry("500x500")
        popup.resizable(False, False)
        popup.transient(window)
        popup.grab_set()

        self.center_popup(popup, 500, 300)  # Center the popup window

        # Variables to store user input
        color_name_var = tk.StringVar()
        l_value_var = tk.StringVar()
        a_value_var = tk.StringVar()
        b_value_var = tk.StringVar()

        result = {"color_name": None, "lab": None}  # Dictionary to store the result

        # Title and instructions
        ttk.Label(popup, text="Add New Color", font=("Helvetica", 14, "bold")).pack(pady=10)
        ttk.Label(popup, text="Enter the LAB values and the color name:").pack(pady=5)

        # Form frame for input fields
        form_frame = ttk.Frame(popup)
        form_frame.pack(padx=20, pady=10)

        # Color name field
        ttk.Label(form_frame, text="Color Name:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(form_frame, textvariable=color_name_var, width=30).grid(row=0, column=1, padx=5, pady=5)

        # L value field
        ttk.Label(form_frame, text="L Value (0-100):").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(form_frame, textvariable=l_value_var, width=10).grid(row=1, column=1, padx=5, pady=5)

        # A value field
        ttk.Label(form_frame, text="A Value (-128 to 127):").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(form_frame, textvariable=a_value_var, width=10).grid(row=2, column=1, padx=5, pady=5)

        # B value field
        ttk.Label(form_frame, text="B Value (-128 to 127):").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(form_frame, textvariable=b_value_var, width=10).grid(row=3, column=1, padx=5, pady=5)

        def confirm_color():
            """
            Validates the input and stores the new color result.
            Closes the popup only if the input is valid.
            """
            color_name = color_name_var.get().strip()

            if not color_name:
                self.custom_warning("Invalid Input", "The color name cannot be empty.")
                return

            # Optional: case-insensitive duplicate check
            existing_names = {name.strip().lower() for name in colors.keys()}
            if color_name.lower() in existing_names:
                self.custom_warning(
                    "Invalid Input",
                    f"The color name '{color_name}' already exists."
                )
                return

            try:
                l_value = float(l_value_var.get())
                a_value = float(a_value_var.get())
                b_value = float(b_value_var.get())
            except ValueError:
                self.custom_warning(
                    "Invalid Input",
                    "L, A and B values must be valid numbers."
                )
                return

            if not (0 <= l_value <= 100):
                self.custom_warning("Invalid Input", "L value must be between 0 and 100.")
                return

            if not (-128 <= a_value <= 127):
                self.custom_warning("Invalid Input", "A value must be between -128 and 127.")
                return

            if not (-128 <= b_value <= 127):
                self.custom_warning("Invalid Input", "B value must be between -128 and 127.")
                return

            result["color_name"] = color_name
            result["lab"] = {"L": l_value, "A": a_value, "B": b_value}

            popup.destroy()


        def browse_color():
            """
            Open a color picker window using a cached color wheel image.
            Convert the selected RGB color to LAB and update the input fields.
            """
            color_picker = tk.Toplevel(popup)
            color_picker.title("Select a Color")
            color_picker.geometry("350x450")
            color_picker.resizable(False, False)
            color_picker.transient(popup)
            color_picker.grab_set()

            x_offset = popup.winfo_x() + popup.winfo_width() + 10
            y_offset = popup.winfo_y()
            color_picker.geometry(f"350x450+{x_offset}+{y_offset}")

            wheel = self._get_color_wheel_image(canvas_size=300)
            canvas_size = wheel["size"]
            center = wheel["center"]
            radius = wheel["radius"]

            def on_click(event):
                """
                Read the selected color from the cached color wheel and update LAB fields.
                """
                x, y = event.x, event.y
                dx, dy = x - center, y - center
                dist = math.sqrt(dx * dx + dy * dy)

                if dist > radius:
                    return

                # Read color directly from the cached PIL image
                r, g, b = wheel["pil"].getpixel((x, y))
                color_hex = f"#{r:02x}{g:02x}{b:02x}"

                preview_canvas.config(bg=color_hex)

                rgb = np.array([[r, g, b]], dtype=np.float32) / 255.0
                lab = color.rgb2lab(rgb.reshape((1, 1, 3)))[0][0]

                l_value_var.set(f"{lab[0]:.2f}")
                a_value_var.set(f"{lab[1]:.2f}")
                b_value_var.set(f"{lab[2]:.2f}")

            def confirm_selection():
                """
                Close the color picker popup.
                """
                color_picker.destroy()

            canvas = tk.Canvas(color_picker, width=canvas_size, height=canvas_size, highlightthickness=1)
            canvas.pack(pady=(10, 0))
            canvas.create_image(0, 0, anchor="nw", image=wheel["tk"])
            canvas.image = wheel["tk"]  # Keep local reference
            canvas.bind("<Button-1>", on_click)

            preview_canvas = tk.Canvas(color_picker, width=100, height=50, bg="white")
            preview_canvas.pack(pady=10)

            ttk.Button(color_picker, text="Confirm", command=confirm_selection).pack(pady=10)

        # Button frame for "Browse Color" and "Add" buttons
        button_frame = ttk.Frame(popup)
        button_frame.pack(pady=20)

        ttk.Button(button_frame, text="Browse Color", command=browse_color, style="Accent.TButton").pack(side="left", padx=10)
        ttk.Button(button_frame, text="Add Color", command=confirm_color, style="Accent.TButton").pack(side="left", padx=10)

        popup.wait_window()  # Wait for the popup to close

        if result["color_name"] is None or result["lab"] is None:
            return None, None
        return result["color_name"], result["lab"]  # Return the result



    def addColor_create_fcs(self, window, colors):
        color_name, new_color = self.addColor(window, colors)

        # update interface
        if color_name is not None:
            self.fuzzy_manager.create_color_display_frame_add(
                parent=self.scroll_palette_create_fcs,
                color_name=color_name,
                lab=new_color,
                color_checks=self.color_checks
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

        color_space_path = os.path.join(BASE_PATH, 'fuzzy_color_spaces', 'cns', 'ISCC_NBS_BASIC.cns')
        colors = UtilsTools.load_color_data(color_space_path)

        popup, self.scroll_palette_create_fcs = UtilsTools.create_popup_window(
            parent=self.root,
            title="Select colors for your Color Space",
            width=450,
            height=500,
            header_text="Select colors for your Color Space"
        )
        self._palette_popup = popup
        self._register_creation_window(popup)

        def on_close():
            self._close_manual_picker_window()
            self._palette_popup = None
            popup.destroy()

        popup.protocol("WM_DELETE_WINDOW", on_close)

        self.center_popup(popup, 450, 500)

        self.color_checks = {}

        for color_name, data in colors.items():
            self.fuzzy_manager.create_color_display_frame(
                parent=self.scroll_palette_create_fcs,
                color_name=color_name,
                rgb=data["rgb"],
                lab=data["lab"],
                color_checks=self.color_checks
            )

        button_frame = ttk.Frame(popup)
        button_frame.pack(pady=20)

        ttk.Button(
            button_frame,
            text="Add New Color",
            command=lambda: self.addColor_create_fcs(popup, colors),
            style="Accent.TButton"
        ).pack(side="left", padx=20)

        ttk.Button(
            button_frame,
            text="Create Color Space",
            command=self.create_color_space,
            style="Accent.TButton"
        ).pack(side="left", padx=20)

        style = ttk.Style()
        style.configure("Accent.TButton", font=("Helvetica", 10, "bold"), padding=10)



    def image_based_creation(self):
        """
        Now shows a mode selector:
        - Manual color selection from Image
        - Automatic Color detection (existing flow -> get_fcs_image)
        """
        if not hasattr(self, "load_images_names") or not self.load_images_names:
            self.custom_warning(message="No images are currently available to display.")
            return

        if not self._can_start_new_creation():
            return

        self.FIRST_DBSCAN = True
        self._popup_choose_image_creation_mode()


    def _popup_choose_image_creation_mode(self):
        """Popup with two buttons: Manual / Automatic."""
        popup = tk.Toplevel(self.root)
        popup.title("Image-Based Creation Mode")
        popup.resizable(False, False)

        self._register_creation_window(popup)

        frame = tk.Frame(popup, padx=20, pady=12)
        frame.pack(fill="both", expand=True)

        tk.Label(
            frame,
            text="Choose creation mode:",
            anchor="w",
            justify="left"
        ).pack(fill="x", pady=(0, 10))

        btn_manual = tk.Button(
            frame,
            text="Manual Color Selection from Image",
            width=30,
            command=lambda: self._start_image_based_mode_and_close_popup(popup, mode="manual")
        )
        btn_manual.pack(fill="x", pady=4)

        btn_auto = tk.Button(
            frame,
            text="Automatic Color Detection from Image",
            width=30,
            command=lambda: self._start_image_based_mode_and_close_popup(popup, mode="auto")
        )
        btn_auto.pack(fill="x", pady=4)

        self.center_popup(popup, 360, 140)


    def _start_image_based_mode(self, mode_popup, mode: str):
        """Closes mode popup and continues with the selected flow."""
        try:
            mode_popup.destroy()
        except Exception:
            pass

        if mode == "auto":
            # Existing behavior: select image -> get_fcs_image
            self._popup_select_image(callback=self.get_fcs_image)

        elif mode == "manual":
            # Manual flow: select image -> YOUR manual handler
            self.get_fcs_image_manual()


    def _popup_select_image(self, callback):
        """
        Reusable image selection popup.
        Uses your existing UtilsTools.create_selection_popup + handle_image_selection.
        """
        popup, listbox = UtilsTools.create_selection_popup(
            parent=self.image_canvas,
            title="Select an Image",
            width=200,
            height=200,
            items=[os.path.basename(filename) for filename in self.load_images_names.values()]
        )

        self.center_popup(popup, 200, 200)

        listbox.bind(
            "<<ListboxSelect>>",
            lambda event: UtilsTools.handle_image_selection(
                event=event,
                listbox=listbox,
                popup=popup,
                images_names=self.load_images_names,
                callback=callback
            )
        )





    # ============================================================================
    # Manual Image-Based Fuzzy Color Space Creation
    # ----------------------------------------------------------------------------
    # This section implements the manual workflow for creating a fuzzy color space
    # from images. It allows the user to:
    #
    #   - Open a palette-like popup to collect colors for a new color space.
    #   - Open a secondary image picker window docked to the right of the main popup.
    #   - Select an image from the currently loaded images.
    #   - Click on any pixel in the image to sample its color.
    #   - Inspect the sampled color in RGB and LAB color spaces.
    #   - Assign a custom name to the sampled color.
    #   - Add the color to the palette list in the main popup.
    #
    # All colors collected in this workflow are stored locally and are discarded
    # when the manual creation popup is closed. The implementation carefully
    # manages window lifecycles to avoid stale references and ensures that UI
    # updates are only performed on valid widgets.
    # ============================================================================
    def get_fcs_image_manual(self, *args, **kwargs):
        """Open the manual FCS creation popup (palette-like) and manage its local color state."""
        colors = {}

        popup, self.scroll_palette_create_fcs = UtilsTools.create_popup_window(
            parent=self.root,
            title="Select colors for your Color Space",
            width=480,
            height=520,
            header_text="Select colors for your Color Space"
        )
        self._register_creation_window(popup)
        self.center_popup(popup, 480, 520)

        self._manual_popup = popup
        self.color_checks = {}

        def on_close():
            self._close_manual_picker_window()
            self._manual_popup = None
            popup.destroy()

        popup.protocol("WM_DELETE_WINDOW", on_close)

        button_frame = ttk.Frame(popup)
        button_frame.pack(fill="x", padx=20, pady=15)
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)

        btn_add_img = ttk.Button(
            button_frame,
            text="Add Color from Image",
            command=partial(self._open_manual_image_picker_window, colors, self.scroll_palette_create_fcs),
            style="Accent.TButton"
        )

        btn_add_new = ttk.Button(
            button_frame,
            text="Add New Color",
            command=lambda: [self._close_manual_picker_window(), self.addColor_create_fcs(popup, colors)],
            style="Accent.TButton"
        )

        btn_create = ttk.Button(
            button_frame,
            text="Create Color Space",
            command=self.create_color_space,
            style="Accent.TButton"
        )

        btn_add_img.grid(row=0, column=0, sticky="ew", padx=5, pady=(0, 8))
        btn_add_new.grid(row=0, column=1, sticky="ew", padx=5, pady=(0, 8))
        btn_create.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5)


    def _open_manual_image_picker_window(self, colors, target_frame):
        """Open a separate image picker window (docked to the right) to sample colors from images."""
        # Ensure there are loaded images available
        if not hasattr(self, "load_images_names") or not self.load_images_names:
            self.custom_warning(message="No images are currently available to display.")
            return

        # If the picker is already open, bring it to front
        if hasattr(self, "_manual_picker_win") and self._manual_picker_win and self._manual_picker_win.winfo_exists():
            self._manual_picker_win.lift()
            self._manual_picker_win.focus_force()
            return

        # Create the picker window
        win = tk.Toplevel(self.root)
        win.title("Pick Color from Image")
        win.resizable(False, False)
        self._manual_picker_win = win

        # Rectangle selection state
        self._manual_dragging = False
        self._manual_drag_start = None      # (x_canvas, y_canvas)
        self._manual_rect_id = None         # canvas item id for selection rect

        # Dock the picker to the right of the main manual popup
        self._dock_window_to_right(parent=self._manual_popup, child=win, gap=12)

        # Layout containers
        container = ttk.Frame(win, padding=10)
        container.pack(fill="both", expand=True)

        left = ttk.Frame(container)
        left.pack(side="left", fill="y")

        right = ttk.Frame(container)
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))

        ttk.Label(left, text="Loaded Images").pack(anchor="w")

        # Listbox shows real filenames, while we keep an index -> window_id mapping
        listbox = tk.Listbox(left, width=22, height=18)
        listbox.pack(pady=6)

        self._manual_listbox_map = []  # Listbox index -> window_id

        window_ids = list(self.load_images_names.keys())
        for wid in window_ids:
            path = self.load_images_names.get(wid, wid)
            display = os.path.basename(path)  # Display the real filename
            listbox.insert("end", display)
            self._manual_listbox_map.append(wid)

        # When a list item is selected, load that image in the canvas
        listbox.bind("<<ListboxSelect>>", lambda e: self._manual_on_select_image(listbox))

        # Image canvas (click to sample a pixel)
        ttk.Label(
            right,
            text="Tip: Click to sample a single pixel.\nClick and drag to select a rectangle and sample the average color.",
            wraplength=420,
            justify="left"
        ).pack(anchor="w")
        self._manual_img_canvas = tk.Canvas(right, width=350, height=300, bg="black", highlightthickness=1)
        self._manual_img_canvas.pack(pady=6)

        # Picked color info (RGB/LAB + name + preview)
        info = ttk.Frame(right)
        info.pack(fill="x", pady=6)

        self._picked_rgb_var = tk.StringVar(value="RGB: -")
        self._picked_lab_var = tk.StringVar(value="LAB: -")
        ttk.Label(info, textvariable=self._picked_rgb_var).pack(anchor="w")
        ttk.Label(info, textvariable=self._picked_lab_var).pack(anchor="w")

        ttk.Label(info, text="Color name:").pack(anchor="w", pady=(8, 0))

        name_row = ttk.Frame(info)
        name_row.pack(fill="x", pady=2)

        # Smaller name entry
        self._picked_name_entry = ttk.Entry(name_row, width=18)
        self._picked_name_entry.pack(side="left")

        # Preview box placed to the right of the name entry
        self._picked_preview = tk.Canvas(name_row, width=60, height=20, highlightthickness=1)
        self._picked_preview.pack(side="left", padx=10)
        self._picked_preview_rect = self._picked_preview.create_rectangle(
            0, 0, 60, 20, fill="#000000", outline=""
        )

        # Add the currently picked color into the main popup list
        ttk.Button(
            info,
            text="Add Selected Color",
            command=lambda: self._manual_add_picked_color(colors, target_frame),
            style="Accent.TButton"
        ).pack(fill="x", pady=6)

        # Button style
        style = ttk.Style()
        style.configure("Accent.TButton", font=("Helvetica", 10, "bold"), padding=10)

        # Drag-to-select rectangle (press / drag / release)
        self._manual_img_canvas.bind("<ButtonPress-1>", self._manual_on_mouse_down)
        self._manual_img_canvas.bind("<B1-Motion>", self._manual_on_mouse_drag)
        self._manual_img_canvas.bind("<ButtonRelease-1>", self._manual_on_mouse_up)


    def _dock_window_to_right(self, parent, child, gap=10):
        """Position a child window to the right of a parent window with a small gap."""
        parent.update_idletasks()
        child.update_idletasks()

        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()

        x = px + pw + gap
        y = py

        child.geometry(f"+{x}+{y}")


    def _manual_on_select_image(self, listbox):
        """Resolve the selected listbox item to a window_id and load that image in the picker."""
        sel = listbox.curselection()
        if not sel:
            return

        idx = sel[0]
        window_id = self._manual_listbox_map[idx]
        self._manual_load_image_from_window_id(window_id)


    def _manual_load_image_from_window_id(self, window_id: str):
        """Load an image from the internal images dict and render it in the picker canvas."""
        if window_id not in self.images:
            self.custom_warning(message="Selected image is not available.")
            return

        self._manual_image_id = window_id
        image = self.images[window_id]

        # Normalize to PIL.Image
        if isinstance(image, Image.Image):
            pil = image.convert("RGB")
        else:
            # Assume numpy array-like
            pil = Image.fromarray(image).convert("RGB")

        self._manual_pil_full = pil

        # Fit the image into the canvas while preserving aspect ratio
        cw = int(self._manual_img_canvas["width"])
        ch = int(self._manual_img_canvas["height"])

        img_w, img_h = pil.size
        scale = min(cw / img_w, ch / img_h)
        new_w = max(1, int(img_w * scale))
        new_h = max(1, int(img_h * scale))

        resized = pil.resize((new_w, new_h), Image.Resampling.LANCZOS)
        try:
            resized = ImageEnhance.Sharpness(resized).enhance(1.2)  # 1.0 = original
        except Exception:
            pass

        # Store geometry for mapping click coordinates back to the full-resolution image
        self._manual_scale = scale
        self._manual_draw_w = new_w
        self._manual_draw_h = new_h
        self._manual_offset_x = (cw - new_w) // 2
        self._manual_offset_y = (ch - new_h) // 2

        # Keep a reference to avoid garbage collection
        self._manual_tk_img = ImageTk.PhotoImage(resized)

        self._manual_img_canvas.delete("all")
        self._manual_img_canvas.create_image(
            self._manual_offset_x,
            self._manual_offset_y,
            anchor="nw",
            image=self._manual_tk_img
        )


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



    def _manual_add_picked_color(self, colors, target_frame):
        """Add the currently picked color to the main manual popup list and local colors dict."""
        # If the main popup has been closed, the target frame is no longer valid
        if target_frame is None or not target_frame.winfo_exists():
            self.custom_warning(message="The color list window is closed. Open it again to add colors.")
            return

        if not hasattr(self, "_picked_rgb") or not hasattr(self, "_picked_lab"):
            self.custom_warning(message="Pick a color by clicking on the image first.")
            return

        # Read and validate the requested color name
        name = self._picked_name_entry.get().strip()
        if not name:
            self.custom_warning(message="Please enter a name for the selected color.")
            return

        # Avoid name collisions
        base = name
        i = 2
        while name in colors:
            name = f"{base}_{i}"
            i += 1

        # Convert picked LAB (tuple/list) into the dict format required by create_color_display_frame_add
        lab = {
            "L": float(self._picked_lab[0]),
            "A": float(self._picked_lab[1]),
            "B": float(self._picked_lab[2]),
        }

        # Persist in local dict (resets on popup close)
        colors[name] = {"lab": lab, "source_image": getattr(self, "_manual_image_id", None)}

        # Render the new row into the target scrollable frame
        self.fuzzy_manager.create_color_display_frame_add(
            parent=target_frame,
            color_name=name,
            lab=lab,
            color_checks=self.color_checks
        )

        # Clear the input for the next color
        self._picked_name_entry.delete(0, "end")















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
            text="Interactive Figure",
            font=("Sans", 12),
            command=self._on_add_graph_current,
        )
        self.add_button.place(relx=0.95, rely=0.05, anchor="ne")


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
        Generate the interactive Plotly figure and show it in a PyQt window.
        """

        def rebuild_menu():
            """
            Rebuild the Tk menu bar to prevent UI glitches after using PyQt.
            """
            self.menubar.destroy()
            self.menubar = Menu(self.root)
            self.root.config(menu=self.menubar)

            menu_font = tkFont.Font(family="Sans", size=11)

            file_menu = Menu(self.menubar, tearoff=0)
            file_menu.add_command(label="Exit", command=self.exit_app, font=menu_font)
            self.menubar.add_cascade(label="File", menu=file_menu)

            img_menu = Menu(self.menubar, tearoff=0)
            img_menu.add_command(label="Open Image", command=self.open_image, font=menu_font)
            img_menu.add_command(label="Save Image", command=self.save_image, font=menu_font)
            img_menu.add_command(label="Close All", command=self.close_all_image, font=menu_font)
            self.menubar.add_cascade(label="Image Manager", menu=img_menu)

            fuzzy_menu = Menu(self.menubar, tearoff=0)
            fuzzy_menu.add_command(label="New Color Space", command=self.show_menu_create_fcs, font=menu_font)
            fuzzy_menu.add_command(label="Load Color Space", command=self.load_color_space, font=menu_font)
            self.menubar.add_cascade(label="Fuzzy Color Space Manager", menu=fuzzy_menu)

            help_menu = Menu(self.menubar, tearoff=0)
            help_menu.add_command(label="About", command=self.about_info, font=menu_font)
            self.menubar.add_cascade(label="Help", menu=help_menu)

        def close_event(event):
            """
            Release the PyQt window reference when the interactive window is closed.
            """
            self.more_graph_window = None
            rebuild_menu()
            event.accept()

        fig = VisualManager.plot_more_combined_3D(
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

        if hasattr(self, "lab_value_frame"):
            self.lab_value_frame.lift()

        file_path = os.path.abspath(os.path.join(BASE_PATH, "Source", "external", "temp_plot.html"))
        fig.write_html(file_path)
        file_path = file_path.replace("\\", "/")

        if self.app_qt is None:
            self.app_qt = QApplication(sys.argv)

        if self.more_graph_window is None or not self.more_graph_window.isVisible():
            self.more_graph_window = QMainWindow()
            self.more_graph_window.setWindowTitle("Interactive 3D Figure")
            self.more_graph_window.setGeometry(100, 100, 800, 600)

            webview = QWebEngineView()
            webview.setUrl(QUrl(f"file:///{file_path}"))

            layout = QVBoxLayout()
            layout.addWidget(webview)

            central_widget = QWidget()
            central_widget.setLayout(layout)
            self.more_graph_window.setCentralWidget(central_widget)

            cursor_pos = QApplication.desktop().cursor().pos()
            screen_number = QApplication.desktop().screenNumber(cursor_pos)
            screen_geom = QApplication.desktop().screenGeometry(screen_number)

            width = 800
            height = 600
            popup_x = screen_geom.x() + (screen_geom.width() - width) // 2
            popup_y = screen_geom.y() + (screen_geom.height() - height) // 2

            self.more_graph_window.setGeometry(popup_x, popup_y, width, height)
            self.more_graph_window.show()
            self.more_graph_window.closeEvent = close_event

        loop = QEventLoop()
        self.more_graph_window.destroyed.connect(loop.quit)
        loop.exec_()


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

        for color in colors:
            is_selected = previous_selected_colors.get(color, True)
            self.selected_colors[color] = tk.BooleanVar(value=is_selected)

            button = tk.Checkbutton(
                self.inner_frame,
                text=color,
                variable=self.selected_colors[color],
                bg="gray95",
                font=("Sans", 10),
                onvalue=True,
                offvalue=False,
                command=self.select_color,
            )
            button.pack(anchor="w", pady=2, padx=10)
            self.color_buttons.append(button)

        self.scrollable_canvas.update_idletasks()
        self.scrollable_canvas.configure(scrollregion=self.scrollable_canvas.bbox("all"))
        self._last_color_button_signature = color_signature















    # ============================================================================================================================================================
    #  FUNCTIONS DATA
    # ============================================================================================================================================================
    def display_data_window(self):
        """
        Displays the color data in a scrollable table within the canvas.
        Updates the table with LAB values, labels, and color previews.
        """
        if hasattr(self, "file_name_entry"):
            self.file_name_entry.delete(0, "end")
            self.file_name_entry.insert(0, getattr(self, "file_base_name", ""))

        self.data_window.delete("all")
        self.data_window.update_idletasks()

        data_source = getattr(self, "edit_color_data", {})

        if not data_source:
            self.data_window.configure(scrollregion=(0, 0, 0, 0))
            self.color_matrix = []
            self.hex_color = {}
            return

        canvas_width = self.data_window.winfo_width()
        column_widths = [80, 80, 80, 200, 150]
        table_width = sum(column_widths)
        margin = max((canvas_width - table_width) // 2, 20)

        x_start = margin
        y_start = 20

        headers = ["L", "a", "b", "Label", "Color"]
        header_height = 30

        for i, header in enumerate(headers):
            x_pos = x_start + sum(column_widths[:i])
            self.data_window.create_rectangle(
                x_pos, y_start, x_pos + column_widths[i], y_start + header_height,
                fill="#d3d3d3", outline="#a9a9a9"
            )
            self.data_window.create_text(
                x_pos + column_widths[i] / 2, y_start + header_height / 2,
                text=header, anchor="center", font=("Sans", 10, "bold")
            )

        y_start += header_height + 10
        row_height = 40
        rect_width = 120
        rect_height = 30

        self.hex_color = {}
        self.color_matrix = []

        for i, (color_name, color_value) in enumerate(data_source.items()):
            if "positive_prototype" in color_value:
                lab = np.array(color_value["positive_prototype"])
            elif "Color" in color_value:
                lab = np.array(color_value["Color"])
            else:
                continue

            self.color_matrix.append(color_name)

            for j, value in enumerate([lab[0], lab[1], lab[2], color_name]):
                x_pos = x_start + sum(column_widths[:j])
                self.data_window.create_rectangle(
                    x_pos, y_start, x_pos + column_widths[j], y_start + row_height,
                    fill="white", outline="#a9a9a9"
                )
                self.data_window.create_text(
                    x_pos + column_widths[j] / 2, y_start + row_height / 2,
                    text=str(round(value, 2)) if j < 3 else value,
                    anchor="center", font=("Sans", 10)
                )

            rgb_data = tuple(map(lambda x: int(x * 255), color.lab2rgb([lab])[0]))
            hex_color = f'#{rgb_data[0]:02x}{rgb_data[1]:02x}{rgb_data[2]:02x}'
            self.hex_color[hex_color] = lab

            color_x_pos = x_start + sum(column_widths[:4])
            self.data_window.create_rectangle(
                color_x_pos + (column_widths[4] - rect_width) / 2, y_start + (row_height - rect_height) / 2,
                color_x_pos + (column_widths[4] - rect_width) / 2 + rect_width,
                y_start + (row_height - rect_height) / 2 + rect_height,
                fill=hex_color, outline="black"
            )

            action_x_pos = x_start + table_width + 20
            self.data_window.create_text(
                action_x_pos, y_start + row_height / 2,
                text="❌", fill="black", font=("Sans", 10, "bold"), anchor="center",
                tags=(f"delete_{i}",)
            )
            self.data_window.tag_bind(f"delete_{i}", "<Button-1>", lambda event, idx=i: self.remove_color(idx))

            y_start += row_height + 10

        self.data_window.configure(scrollregion=self.data_window.bbox("all"))
        self.data_window.bind("<Configure>", lambda event: self.display_data_window())

            

    def remove_color(self, index):
        """Remove a color from the editable dataset and refresh the display."""
        if len(self.edit_color_data) <= 2:
            self.custom_warning(
                "Cannot Remove Color",
                "At least two colors must remain. The color was not removed."
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

                negatives = data["negative_prototypes"]
                filtered = [
                    prototype for prototype in negatives
                    if not np.array_equal(prototype, removed_positive)
                ]
                data["negative_prototypes"] = np.array(filtered)

            del self.edit_color_data[color_name]

        self.display_data_window()



    def addColor_data_window(self):
        """Add a new color to the editable dataset and update the display."""
        if not self.COLOR_SPACE:
            return

        import copy
        new_color_data = copy.deepcopy(self.edit_color_data)
        new_color, lab_values = self.addColor(self.inner_frame_data, new_color_data)

        if new_color and lab_values:
            positive_prototype = np.array([
                lab_values["L"],
                lab_values["A"],
                lab_values["B"]
            ])

            negative_prototypes = []
            for _, data in new_color_data.items():
                if "positive_prototype" in data:
                    negative_prototypes.append(np.array(data["positive_prototype"]))
                elif "Color" in data:
                    negative_prototypes.append(np.array(data["Color"]))

            negative_prototypes = np.array(negative_prototypes)

            new_color_data[new_color] = {
                "Color": [lab_values["L"], lab_values["A"], lab_values["B"]],
                "positive_prototype": positive_prototype,
                "negative_prototypes": negative_prototypes
            }

            for existing_color, data in new_color_data.items():
                if existing_color == new_color:
                    continue

                existing_negatives = data.get("negative_prototypes", [])

                if len(existing_negatives) > 0:
                    updated_negatives = np.vstack([existing_negatives, positive_prototype])
                else:
                    updated_negatives = np.array([positive_prototype])

                new_color_data[existing_color]["negative_prototypes"] = updated_negatives

            self.edit_color_data = new_color_data
            self.display_data_window()



    def clear_data_window(self):
        """Clear the data display area and reset related UI/state."""
        if hasattr(self, "data_window"):
            self.data_window.delete("all")
            self.data_window.configure(scrollregion=(0, 0, 0, 0))

        if hasattr(self, "file_name_entry"):
            self.file_name_entry.delete(0, tk.END)

        self.file_base_name = ""
        self.color_matrix = []
        self.hex_color = {}



    def apply_changes(self):
        """Apply the pending changes made to the editable color list."""
        if not self.COLOR_SPACE:
            self.custom_warning("Error", "No Color Space has been loaded.")
            return

        if self._has_any_active_job():
            self.custom_warning(
                "Process Running",
                "There is a process currently running. Please wait for it to finish or cancel it before loading a Color Space."
            )
            return

        try:
            output_name = self.file_name_entry.get().strip()
            if not output_name:
                self.custom_warning("Error", "Please enter a valid file name.")
                return

            new_color_data = copy.deepcopy(self.edit_color_data)

            color_dict = {
                key: value["positive_prototype"]
                for key, value in new_color_data.items()
            }

            self.save_fcs(
                output_name,
                new_color_data,
                color_dict=color_dict,
                apply_after_save=True
            )

        except Exception as e:
            self.custom_warning("Error", f"Changes could not be prepared: {e}")


    def delete_color_space(self):
        """Delete the currently loaded color space file (.fcs or .cns) and clear the app state."""
        if not self.COLOR_SPACE:
            self.custom_warning("Error", "No Color Space has been loaded.")
            return

        if self._has_any_active_job():
            self.custom_warning(
                "Process Running",
                "There is a process currently running. Please wait for it to finish or cancel it before deleting the Color Space."
            )
            return

        file_path = getattr(self, "file_path", None)
        file_name = os.path.basename(file_path) if file_path else "current color space"

        confirm = messagebox.askyesno(
            "Delete Color Space",
            f"Are you sure you want to permanently delete:\n\n{file_name}\n\nThis action cannot be undone."
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

            self.clear_data_window()
            self.update_volumes()

            messagebox.showinfo("Deleted", f"{file_name} was deleted successfully.")

        except Exception as e:
            self.custom_warning("Error", f"The Color Space could not be deleted: {e}")























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
        pil_original = Image.open(filename).convert("RGB")
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
            pixel_rgb_np = np.array([[pixel_value]], dtype=np.uint8)
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
    def display_detected_colors(self, colors, threshold, min_samples):
        """
        Displays a popup window showing the detected colors with options to adjust the threshold,
        recalculate, add new image colors, and create a fuzzy color space.
        """
        # Create a popup window
        popup = tk.Toplevel(self.root)
        popup.title("Detected Colors")
        popup.configure(bg="#f5f5f5")

        self._register_creation_window(popup)

        # Center the popup window
        self.center_popup(popup, 500, 600)

        # Function to handle window closing
        def on_closing():
            """Clears the color entry dictionary when the window is closed."""
            self.color_entry_detect.clear()
            self._close_manual_picker_window()
            self._detected_popup = None
            popup.destroy()

        # Bind the closing event to the on_closing function
        popup.protocol("WM_DELETE_WINDOW", on_closing)

        # Header
        tk.Label(
            popup,
            text="Detected Colors",
            font=("Helvetica", 14, "bold"),
            bg="#f5f5f5"
        ).pack(pady=15)

        # Threshold and controls
        controls_frame = tk.Frame(popup, bg="#f5f5f5", pady=10)
        controls_frame.pack(pady=10)

        # Create a rectangular frame for the Threshold section
        threshold_frame = tk.Frame(controls_frame, bg="#e5e5e5", bd=1, relief="solid", padx=10, pady=5)
        threshold_frame.grid(row=0, column=0, columnspan=2, padx=10, pady=5)

        tk.Label(
            threshold_frame,
            text="Threshold:",
            font=("Helvetica", 12),
            bg="#f5f5f5"
        ).grid(row=0, column=0, padx=5)

        threshold_label = tk.Label(
            threshold_frame,
            text=f"{threshold:.2f}",
            font=("Helvetica", 12),
            bg="#f5f5f5"
        )
        threshold_label.grid(row=0, column=1, padx=5)

        def increase_threshold():
            nonlocal threshold, min_samples
            if threshold < 1.0:  
                threshold = min(threshold + 0.05, 1.0)
                min_samples = max(15, min_samples - 15)  
                threshold_label.config(text=f"{threshold:.2f}")

        def decrease_threshold():
            nonlocal threshold, min_samples
            if threshold > 0.0:  
                threshold = max(threshold - 0.05, 0.0)
                min_samples += 15  
                threshold_label.config(text=f"{threshold:.2f}")


        # Adjust the order and styling of buttons
        tk.Button(
            controls_frame,
            text="-",
            command=decrease_threshold,
            bg="#f0d2d2",
            font=("Helvetica", 10, "bold"),
            width=2
        ).grid(row=0, column=2, padx=2)

        tk.Button(
            controls_frame,
            text="+",
            command=increase_threshold,
            bg="#d4f0d2",
            font=("Helvetica", 10, "bold"),
            width=2
        ).grid(row=0, column=3, padx=2)

        tk.Button(
            controls_frame,
            text="Recalculate",
            command=lambda: self._recalculate_detected_colors(popup, colors, threshold, min_samples),
            bg="#d2dff0",
            font=("Helvetica", 10, "bold"),
            padx=10
        ).grid(row=0, column=4, padx=10)

        # Frame to display colors with a scrollbar
        frame_container = ttk.Frame(popup)
        frame_container.pack(pady=10, fill="both", expand=True)

        canvas = tk.Canvas(frame_container, bg="#f5f5f5")
        scrollbar = ttk.Scrollbar(frame_container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        canvas.bind("<MouseWheel>", lambda event: self.on_mouse_wheel(event, canvas))

        scrollable_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def remove_detect_color(frame, index):
            """Removes a detected color from the list and updates the UI."""
            frame.destroy()  # Remove the color row
            colors.pop(index)  # Remove the color from the list

            # Remove the corresponding entry without rebuilding the dictionary
            self.color_entry_detect.pop(f"color_{index}", None)

            # Update the indices in self.color_entry_detect
            for new_index, old_key in enumerate(list(self.color_entry_detect.keys())):
                self.color_entry_detect[f"color_{new_index}"] = self.color_entry_detect.pop(old_key)

            # Reorganize the frames and their buttons after removal
            update_color_frames()

        def update_color_frames():
            """Updates the color frames in the scrollable area."""
            previous_names = {key: entry.get() for key, entry in self.color_entry_detect.items()}

            # Clear the container before redrawing
            for widget in scrollable_frame.winfo_children():
                widget.destroy()

            self.color_entry_detect.clear()  # Reset the entry dictionary

            for i, dect_color in enumerate(colors):
                rgb = dect_color["rgb"]

                # Normalize RGB in case it comes as nested list/array
                if hasattr(rgb, "tolist"):
                    rgb = rgb.tolist()

                if isinstance(rgb, list) and len(rgb) == 1 and isinstance(rgb[0], (list, tuple)):
                    rgb = rgb[0]

                rgb = tuple(int(v) for v in rgb[:3])

                if "lab" in dect_color:
                    lab_data = dect_color["lab"]

                    if isinstance(lab_data, dict):
                        lab = np.array([
                            float(lab_data["L"]),
                            float(lab_data["A"]),
                            float(lab_data["B"])
                        ], dtype=float)
                    else:
                        lab = np.array(lab_data, dtype=float).reshape(3,)
                else:
                    lab = color.rgb2lab(
                        np.array(rgb, dtype=np.uint8).reshape(1, 1, 3) / 255
                    )[0, 0]

                default_name = dect_color.get("name", f"Color {i + 1}")

                frame = ttk.Frame(scrollable_frame)
                frame.pack(fill="x", pady=8, padx=10)

                # Color preview
                color_box = tk.Label(
                    frame,
                    bg=UtilsTools.rgb_to_hex(rgb),
                    width=4,
                    height=2,
                    relief="solid",
                    bd=1
                )
                color_box.pack(side="left", padx=10)

                # Retrieve the saved name or use the default
                entry_name_key = f"color_{i}"
                saved_name = previous_names.get(entry_name_key, default_name)

                # Entry field for the color name
                entry = ttk.Entry(frame, font=("Helvetica", 12))
                entry.insert(0, saved_name)
                entry.pack(side="left", padx=10, fill="x", expand=True)
                self.color_entry_detect[entry_name_key] = entry

                # LAB values
                lab_values = f"L: {lab[0]:.1f}, A: {lab[1]:.1f}, B: {lab[2]:.1f}"
                tk.Label(
                    frame,
                    text=lab_values,
                    font=("Helvetica", 10, "italic"),
                    bg="#f5f5f5"
                ).pack(side="left", padx=10)

                # Remove button
                remove_button = tk.Button(
                    frame,
                    text="❌",
                    font=("Helvetica", 10, "bold"),
                    command=lambda f=frame, idx=i: remove_detect_color(f, idx),
                    bg="#f5f5f5",
                    relief="flat"
                )
                remove_button.pack(side="right", padx=5)

        # Display the initial colors
        update_color_frames()

        # Keep references to this popup so the picker can dock to it
        self._detected_popup = popup

        # Action buttons
        button_frame = ttk.Frame(popup)
        button_frame.pack(pady=20, fill="x", padx=20)

        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)

        add_colors_button = ttk.Button(
            button_frame,
            text="Detect Colors from other Image",
            command=lambda: [self._close_manual_picker_window(), self.add_new_image_colors(popup, colors, threshold, min_samples)],
            style="Accent.TButton"
        )
        add_colors_button.grid(row=0, column=0, sticky="ew", padx=5, pady=(0, 8))

        add_single_color_button = ttk.Button(
            button_frame,
            text="Add Manual Color",
            command=lambda: [self._close_manual_picker_window(), self.addColor_to_image(popup, colors, update_color_frames)],
            style="Accent.TButton"
        )
        add_single_color_button.grid(row=0, column=1, sticky="ew", padx=5, pady=(0, 8))

        add_from_image_button = ttk.Button(
            button_frame,
            text="Add Manual Color from Image",
            command=lambda: self._open_detected_image_picker_window(colors, update_color_frames),
            style="Accent.TButton"
        )
        add_from_image_button.grid(row=1, column=0, sticky="ew", padx=5, pady=(0, 8))

        save_button = ttk.Button(
            button_frame,
            text="Create Fuzzy Color Space",
            command=lambda: self.process_fcs(colors, popup),
            style="Accent.TButton"
        )
        save_button.grid(row=1, column=1, sticky="ew", padx=5, pady=(0, 8))

        # Style for buttons
        style = ttk.Style()
        style.configure("Accent.TButton", font=("Helvetica", 8, "bold"), padding=10)



    def add_new_image_colors(self, popup, colors, threshold, min_samples):
        """
        Allows the user to select another image and adds the detected colors to the current list.
        Ensures that only unique images are selected and handles cases where no images are available.
        """
        # Get unique source image IDs from the current colors
        unique_ids = {color.get("source_image") for color in colors}

        # Check if there are available images to display
        if not hasattr(self, "load_images_names") or not self.load_images_names:
            self.custom_warning(message="No images are currently available to display.")
            return

        # Filter out images that have already been selected
        available_image_ids = [
            image_id for image_id in self.images.keys()
            if image_id not in unique_ids
        ]

        # If no available images, show a message and return
        if not available_image_ids:
            self.custom_warning("No Available Images", "All images have already been selected.")
            return

        # Get the filenames of the available images
        available_image_names = [
            self.load_images_names[image_id] for image_id in available_image_ids
            if image_id in self.load_images_names
        ]

        # Create a popup window for selecting another image
        select_popup, listbox = UtilsTools.create_selection_popup(
            parent=popup,
            title="Select Another Image",
            width=200,
            height=200,
            items=[os.path.basename(filename) for filename in available_image_names]
        )

        # Center the popup window
        self.center_popup(select_popup, 200, 200)

        # Bind the listbox selection event to handle image selection
        listbox.bind(
            "<<ListboxSelect>>",
            lambda event: UtilsTools.handle_image_selection(
                event=event,
                listbox=listbox,
                popup=select_popup,
                images_names=self.load_images_names,
                callback=lambda window_id: [
                    self.get_fcs_image_merge(window_id, colors, threshold, min_samples),
                    popup.destroy()
                ]
            )
        )



    def _open_detected_image_picker_window(self, colors, update_callback):
        """Open a separate image picker window to add a sampled image color to detected colors."""
        if not hasattr(self, "load_images_names") or not self.load_images_names:
            self.custom_warning(message="No images are currently available to display.")
            return

        if hasattr(self, "_detected_picker_win") and self._detected_picker_win and self._detected_picker_win.winfo_exists():
            self._detected_picker_win.lift()
            self._detected_picker_win.focus_force()
            return

        win = tk.Toplevel(self.root)
        win.title("Pick Color from Image")
        win.resizable(False, False)
        self._detected_picker_win = win

        # Rectangle selection state
        self._manual_dragging = False
        self._manual_drag_start = None
        self._manual_rect_id = None

        # Dock to the right of the detected-colors popup
        if hasattr(self, "_detected_popup") and self._detected_popup and self._detected_popup.winfo_exists():
            self._dock_window_to_right(parent=self._detected_popup, child=win, gap=12)

        container = ttk.Frame(win, padding=10)
        container.pack(fill="both", expand=True)

        left = ttk.Frame(container)
        left.pack(side="left", fill="y")

        right = ttk.Frame(container)
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))

        ttk.Label(left, text="Loaded Images").pack(anchor="w")

        listbox = tk.Listbox(left, width=22, height=18)
        listbox.pack(pady=6)

        self._manual_listbox_map = []

        window_ids = list(self.load_images_names.keys())
        for wid in window_ids:
            path = self.load_images_names.get(wid, wid)
            display = os.path.basename(path)
            listbox.insert("end", display)
            self._manual_listbox_map.append(wid)

        listbox.bind("<<ListboxSelect>>", lambda e: self._manual_on_select_image(listbox))

        ttk.Label(
            right,
            text="Tip: Click to sample a single pixel.\nClick and drag to select a rectangle and sample the average color.",
            wraplength=420,
            justify="left"
        ).pack(anchor="w")

        self._manual_img_canvas = tk.Canvas(right, width=350, height=300, bg="black", highlightthickness=1)
        self._manual_img_canvas.pack(pady=6)

        info = ttk.Frame(right)
        info.pack(fill="x", pady=6)

        self._picked_rgb_var = tk.StringVar(value="RGB: -")
        self._picked_lab_var = tk.StringVar(value="LAB: -")

        ttk.Label(info, textvariable=self._picked_rgb_var).pack(anchor="w")
        ttk.Label(info, textvariable=self._picked_lab_var).pack(anchor="w")

        ttk.Label(info, text="Color name:").pack(anchor="w", pady=(8, 0))

        name_row = ttk.Frame(info)
        name_row.pack(fill="x", pady=2)

        self._picked_name_entry = ttk.Entry(name_row, width=18)
        self._picked_name_entry.pack(side="left")

        self._picked_preview = tk.Canvas(name_row, width=60, height=20, highlightthickness=1)
        self._picked_preview.pack(side="left", padx=10)
        self._picked_preview_rect = self._picked_preview.create_rectangle(
            0, 0, 60, 20, fill="#000000", outline=""
        )

        ttk.Button(
            info,
            text="Add Selected Color",
            command=lambda: self._detected_add_picked_color(colors, update_callback),
            style="Accent.TButton"
        ).pack(fill="x", pady=6)

        style = ttk.Style()
        style.configure("Accent.TButton", font=("Helvetica", 10, "bold"), padding=10)

        self._manual_img_canvas.bind("<ButtonPress-1>", self._manual_on_mouse_down)
        self._manual_img_canvas.bind("<B1-Motion>", self._manual_on_mouse_drag)
        self._manual_img_canvas.bind("<ButtonRelease-1>", self._manual_on_mouse_up)

        def on_close():
            self._detected_picker_win = None
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", on_close)



    def _close_manual_picker_window(self):
        """Safely close any manual image picker window and clear related references."""
        for attr_name in ("_manual_picker_win", "_detected_picker_win"):
            win = getattr(self, attr_name, None)
            if win is not None:
                try:
                    if win.winfo_exists():
                        win.destroy()
                except Exception:
                    pass
                setattr(self, attr_name, None)

        # Clear transient picker state
        self._manual_dragging = False
        self._manual_drag_start = None
        self._manual_rect_id = None



    def _detected_add_picked_color(self, colors, update_callback):
        """Append the picked color to detected colors and refresh the detected-colors list."""
        if not hasattr(self, "_picked_rgb") or not hasattr(self, "_picked_lab"):
            self.custom_warning(message="Pick a color by clicking on the image first.")
            return

        name = self._picked_name_entry.get().strip()

        r, g, b = self._picked_rgb
        rgb = (int(r), int(g), int(b))

        lab = {
            "L": float(self._picked_lab[0]),
            "A": float(self._picked_lab[1]),
            "B": float(self._picked_lab[2]),
        }

        new_color = {
            "rgb": rgb,
            "lab": lab,
        }

        if name:
            new_color["name"] = name

        colors.append(new_color)

        if callable(update_callback):
            update_callback()

        self._picked_name_entry.delete(0, "end")


    def process_fcs(self, colors, detected_popup=None):
        """
        Saves the names of the colors edited by the user in a file with a .cns extension.
        Prompts the user to enter a name for the fuzzy color space and validates the input.
        """
        if len(self.color_entry_detect) < 2:
            self.custom_warning("Not Enough Colors", "At least two colors must be selected to create the Color Space.")
            return

        popup = tk.Toplevel(self.root)
        popup.title("Input")
        self._register_creation_window(popup)
        self.center_popup(popup, 300, 100)

        tk.Label(popup, text="Name for the fuzzy color space:").pack(pady=5)
        name_entry = tk.Entry(popup)
        name_entry.pack(pady=5)

        name = tk.StringVar()

        def on_ok():
            """Callback function for the OK button."""
            name.set(name_entry.get().strip())

            if not name.get():
                self.custom_warning("Warning", "Please enter a name for the fuzzy color space.")
                return

            try:
                prepared_colors = []

                for i, item in enumerate(colors):
                    new_item = dict(item)

                    entry = self.color_entry_detect.get(f"color_{i}")
                    if entry is not None and entry.winfo_exists():
                        edited_name = entry.get().strip()
                        if edited_name:
                            new_item["name"] = edited_name

                    lab_value = new_item.get("lab")
                    if isinstance(lab_value, dict):
                        new_item["lab"] = [
                            float(lab_value["L"]),
                            float(lab_value["A"]),
                            float(lab_value["B"]),
                        ]
                    elif lab_value is not None:
                        lab_arr = np.array(lab_value, dtype=float).reshape(-1)
                        new_item["lab"] = [
                            float(lab_arr[0]),
                            float(lab_arr[1]),
                            float(lab_arr[2]),
                        ]
                    else:
                        rgb = new_item.get("rgb")
                        if hasattr(rgb, "tolist"):
                            rgb = rgb.tolist()
                        if isinstance(rgb, list) and len(rgb) == 1 and isinstance(rgb[0], (list, tuple, np.ndarray)):
                            rgb = rgb[0]
                        rgb = [int(v) for v in rgb[:3]]

                        lab_arr = color.rgb2lab(
                            np.array(rgb, dtype=np.uint8).reshape(1, 1, 3) / 255
                        )[0, 0]

                        new_item["lab"] = [
                            float(lab_arr[0]),
                            float(lab_arr[1]),
                            float(lab_arr[2]),
                        ]

                    prepared_colors.append(new_item)

                popup.destroy()

                if detected_popup is not None and detected_popup.winfo_exists():
                    detected_popup.destroy()

                self.save_fcs(name.get(), prepared_colors)

            except Exception as e:
                self.custom_warning("Error", f"Could not prepare colors for saving: {e}")

        ok_button = tk.Button(popup, text="OK", command=on_ok)
        ok_button.pack(pady=5)

        popup.deiconify()



    def get_fcs_image(self, window_id, threshold=0.5, min_samples=160):
        """
        Retrieves the fuzzy color space for the specified image and displays the detected colors.
        Adds the source image identifier to each color if it doesn't already exist.
        """
        image = self.images[window_id]
        self.last_window_id = window_id
        colors = self.image_manager.get_fcs_image(image, threshold, min_samples)

        # Add the source image identifier to each color if it doesn't exist
        for id in colors:
            if "source_image" not in id:
                id["source_image"] = window_id

        # Display the detected colors
        self.display_detected_colors(colors, threshold, min_samples)



    def get_fcs_image_merge(self, new_window_id, colors, threshold, min_samples):
        """
        Retrieves the fuzzy color space for a new image and merges it with the existing colors.
        Adds the source image identifier to each new color if it doesn't already exist.
        """
        if new_window_id and not any(id.get("source_image") == new_window_id for id in colors):
            new_colors = self.image_manager.get_fcs_image(self.images[new_window_id], threshold, min_samples)

            # Add the source image identifier to each new color if it doesn't exist
            for id in new_colors:
                if "source_image" not in id:
                    id["source_image"] = new_window_id

            # Merge the new colors with the existing ones
            colors.extend(new_colors)
            self.display_detected_colors(colors, threshold, min_samples)



    def recalculate(self, window_id, colors, threshold, min_samples):
        """
        Recalculates the fuzzy color space for the specified image and updates the color list.
        Filters out colors that do not belong to the current image.
        """
        self.color_entry_detect = {}

        # Filter out colors that do not belong to the current image
        filtered_colors = [id for id in colors if id.get("source_image") != window_id]
        self.get_fcs_image_merge(window_id, filtered_colors, threshold, min_samples)



    def get_fcs_image_recalculate(self, colors, threshold=0.5, min_samples=160, popup=None):
        """
        Recalculates the fuzzy color space for the selected image.
        If multiple images are available, prompts the user to select one.
        """
        # Get unique source image IDs from the current colors
        unique_ids = {id.get("source_image") for id in colors}

        if len(unique_ids) > 1:
            # If there are multiple images, prompt the user to select one
            popup, listbox = UtilsTools.create_selection_popup(
                parent=self.image_canvas,
                title="Select an Image",
                width=200,
                height=200,
                items=[os.path.basename(filename) for filename in self.load_images_names.values()]
            )

            self.center_popup(popup, 200, 200)

            # Bind the listbox selection event to handle image selection
            listbox.bind(
                "<<ListboxSelect>>",
                lambda event: UtilsTools.handle_image_selection(
                    event=event,
                    listbox=listbox,
                    popup=popup,
                    images_names=self.load_images_names,
                    callback=lambda window_id: [self.recalculate(window_id, colors, threshold, min_samples), popup.destroy()]
                )
            )

        elif len(unique_ids) == 0:
            self.custom_warning(
                title="Warning",
                message="No colors were detected under this configuration. The last version will be reloaded"
            )
            self.get_fcs_image(self.last_window_id, threshold, min_samples)

        else:
            # If there is only one image, recalculate its colors directly
            window_id = unique_ids.pop() if unique_ids else None
            self.get_fcs_image(window_id, threshold, min_samples)
            popup.destroy()


    def _build_named_colors_for_save(self, colors):
        """
        Build a normalized color list using the names currently written by the user
        in the detected-colors entries.
        """
        prepared_colors = []

        used_names = set()

        for i, item in enumerate(colors):
            new_item = dict(item)

            entry = self.color_entry_detect.get(f"color_{i}")
            if entry is not None and entry.winfo_exists():
                color_name = entry.get().strip()
            else:
                color_name = new_item.get("name", f"Color_{i+1}")

            if not color_name:
                color_name = f"Color_{i+1}"

            # Avoid duplicates
            base_name = color_name
            suffix = 2
            while color_name in used_names:
                color_name = f"{base_name}_{suffix}"
                suffix += 1

            used_names.add(color_name)
            new_item["name"] = color_name

            # Normalize RGB
            rgb = new_item.get("rgb")
            if rgb is not None:
                if hasattr(rgb, "tolist"):
                    rgb = rgb.tolist()

                if isinstance(rgb, list) and len(rgb) == 1 and isinstance(rgb[0], (list, tuple, np.ndarray)):
                    rgb = rgb[0]

                new_item["rgb"] = [int(v) for v in rgb[:3]]

            # Normalize LAB
            lab_value = new_item.get("lab")
            if lab_value is None:
                rgb = new_item.get("rgb")
                if rgb is None:
                    raise ValueError(f"Color at index {i} has neither 'lab' nor 'rgb'.")
                lab_arr = color.rgb2lab(
                    np.array(rgb, dtype=np.uint8).reshape(1, 1, 3) / 255
                )[0, 0]
                new_item["lab"] = [
                    float(lab_arr[0]),
                    float(lab_arr[1]),
                    float(lab_arr[2]),
                ]
            elif isinstance(lab_value, dict):
                new_item["lab"] = [
                    float(lab_value["L"]),
                    float(lab_value["A"]),
                    float(lab_value["B"]),
                ]
            else:
                lab_arr = np.array(lab_value, dtype=float).reshape(-1)
                if lab_arr.size != 3:
                    raise ValueError(f"Invalid LAB format at index {i}: {lab_value}")
                new_item["lab"] = [
                    float(lab_arr[0]),
                    float(lab_arr[1]),
                    float(lab_arr[2]),
                ]

            prepared_colors.append(new_item)

        return prepared_colors



    def _normalize_detected_colors_for_save(self, colors):
        """
        Normalize detected/manual colors to the structure expected by save_fcs:
        each color keeps rgb/source_image/name and stores lab as a flat [L, A, B] list.
        """
        normalized = []

        for i, item in enumerate(colors):
            new_item = dict(item)

            # Normalize RGB if present
            rgb = new_item.get("rgb")
            if rgb is not None:
                if hasattr(rgb, "tolist"):
                    rgb = rgb.tolist()

                if isinstance(rgb, list) and len(rgb) == 1 and isinstance(rgb[0], (list, tuple, np.ndarray)):
                    rgb = rgb[0]

                rgb = [int(v) for v in rgb[:3]]
                new_item["rgb"] = rgb

            # Normalize LAB
            lab_value = new_item.get("lab")

            if lab_value is None:
                if rgb is None:
                    raise ValueError(f"Color at index {i} has neither 'lab' nor valid 'rgb'.")
                lab_arr = color.rgb2lab(
                    np.array(rgb, dtype=np.uint8).reshape(1, 1, 3) / 255
                )[0, 0]
                new_item["lab"] = [
                    float(lab_arr[0]),
                    float(lab_arr[1]),
                    float(lab_arr[2]),
                ]

            elif isinstance(lab_value, dict):
                new_item["lab"] = [
                    float(lab_value["L"]),
                    float(lab_value["A"]),
                    float(lab_value["B"]),
                ]

            else:
                lab_arr = np.array(lab_value, dtype=float).reshape(-1)
                if lab_arr.size != 3:
                    raise ValueError(f"Invalid LAB format at index {i}: {lab_value}")
                new_item["lab"] = [
                    float(lab_arr[0]),
                    float(lab_arr[1]),
                    float(lab_arr[2]),
                ]

            normalized.append(new_item)

        return normalized











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
        self.current_protos[window_id] = tk.StringVar(value=0)

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
                command=lambda color=color: self.get_proto_percentage(window_id)
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

        Cache scope:
            (image_key, color_space_key)

        Cache key inside that scope:
            (selected_proto_index, displayed_width, displayed_height)
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
                        image=source_img,
                        fuzzy_color_space=self.fuzzy_color_space,
                        selected_option=pos,
                        progress_callback=update_progress,
                        cancel_callback=lambda: cancel_event.is_set()
                    )

                    if self._is_job_cancelled(window_id, cancel_event, job_id):
                        return

                    unique_vals = np.unique(grayscale_image_array) if grayscale_image_array.ndim == 2 else None
                    if grayscale_image_array.ndim == 2 and unique_vals is not None and unique_vals.size <= 3 and 255 in unique_vals:
                        thresh = 255
                    else:
                        thresh = 128

                    if grayscale_image_array.ndim == 2:
                        colored = np.count_nonzero(grayscale_image_array >= thresh)
                        total = grayscale_image_array.size
                    else:
                        colored = np.count_nonzero(np.any(grayscale_image_array != 0, axis=-1))
                        total = grayscale_image_array.shape[0] * grayscale_image_array.shape[1]

                    pct = 100.0 * (colored / total) if total else 0.0

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
                    self.image_canvas.itemconfig(f"{window_id}_pct_text", text=f"{selected_proto}: {pct:.2f}%")
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
        """Displays the generated grayscale image in the graphical interface (resized only for display)."""
        try:
            # Disable original-image rectangle sampling because the view is no longer the original image
            try:
                self._disable_original_rectangle_sampling(window_id)
            except Exception:
                pass

            # Store the ORIGINAL result (do not store the resized display version)
            self.modified_image[window_id] = grayscale_image_array

            # Convert numpy array to PIL image with the correct mode
            if grayscale_image_array.ndim == 2:
                grayscale_image = Image.fromarray(grayscale_image_array.astype(np.uint8), mode="L")
            else:
                grayscale_image = Image.fromarray(grayscale_image_array.astype(np.uint8))

            # Resize only for display to match the current window dimensions
            new_width, new_height = self.image_dimensions[window_id]
            grayscale_image_display = grayscale_image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Store the exact PIL image currently displayed
            if hasattr(self, "display_pil"):
                self.display_pil[window_id] = grayscale_image_display

            # Convert to PhotoImage for Tkinter
            img_tk = ImageTk.PhotoImage(grayscale_image_display)

            # Keep a reference to prevent garbage collection
            self.floating_images[window_id] = img_tk

            # Update canvas image item
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
        Fast Tkinter "Color Mapping All" operation.

        Main cache design:
        - Persistent cache is stored by (image_key, color_space_key)
        - Inside that scope we cache label_map by:
            (width, height, prototype_labels)

        This allows reopening the same image and reusing previously computed results
        as long as the image identity and color space remain the same.
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

        self.proto_options = getattr(self, "proto_options", {})
        info = self.proto_options.pop(window_id, None)
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

        def update_progress(job_id, current_step, total_steps):
            if total_steps <= 0:
                return
            self._update_window_progress(window_id, job_id, current_step, total_steps)

        def build_legend_frame(prototypes, parent_canvas, palette_uint8):
            """
            Creates and returns the legend frame.

            palette_uint8: (N,3) uint8 array with one display color per prototype.
            """
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

        def build_original_palette_uint8():
            """Build the original HSV palette in prototype order."""
            cmap = plt.get_cmap("hsv", len(self.prototypes))
            palette = []
            for i, p in enumerate(self.prototypes):
                rgb01 = np.array(cmap(i)[:3], dtype=float)
                rgb255 = (np.clip(rgb01, 0, 1) * 255).astype(np.uint8)
                if p.label.lower() == "black":
                    rgb255 = np.array([0, 0, 0], dtype=np.uint8)
                palette.append(rgb255)
            return np.stack(palette, axis=0).astype(np.uint8)

        def build_alt_palette_uint8():
            """Build the alternate palette using the colors stored in self.hex_color."""
            hex_colors = list(self.hex_color.keys())
            alt = []
            for i, _p in enumerate(self.prototypes):
                if i < len(hex_colors):
                    hx = hex_colors[i]
                    rgb = np.array([int(hx[j:j + 2], 16) for j in (1, 3, 5)], dtype=np.uint8)
                else:
                    rgb = np.array([0, 0, 0], dtype=np.uint8)
                alt.append(rgb)
            return np.stack(alt, axis=0).astype(np.uint8)

        def recolor(window_id):
            """
            Switch displayed palette without recomputing memberships.
            Reuses cached label_map + palettes from the persistent cache.
            """
            if getattr(self, "mapping_locked_until_original", {}).get(window_id, False):
                self.custom_warning(
                    "Old Color Space",
                    "This Color Mapping All result belongs to a previous Color Space. Press Original to use the new one."
                )
                return

            if not self._window_exists(window_id):
                return

            if not hasattr(self, "cm_cache_by_image"):
                return

            scope_cache = self.cm_cache_by_image.get(cache_scope)
            if not scope_cache:
                return

            cache_pack = scope_cache.get("last_pack")
            if not cache_pack:
                return

            label_map = cache_pack["label_map"]
            palettes = cache_pack["palettes"]
            current = cache_pack["scheme"]
            new = "alt" if current == "original" else "original"
            cache_pack["scheme"] = new

            palette = palettes[new]

            recolored_image = np.zeros((label_map.shape[0], label_map.shape[1], 3), dtype=np.uint8)
            valid_mask = (label_map >= 0)
            if np.any(valid_mask):
                recolored_image[valid_mask] = palette[label_map[valid_mask].astype(np.int32)]

            old_legend_frame = cache_pack.get("legend_frame")
            if old_legend_frame:
                try:
                    if old_legend_frame.winfo_exists():
                        old_legend_frame.destroy()
                except Exception:
                    pass

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

                if not hasattr(self, "cm_cache_by_image"):
                    self.cm_cache_by_image = {}
                scope_cache = self.cm_cache_by_image.setdefault(cache_scope, {})

                proto_labels = tuple([p.label for p in self.prototypes])
                cache_key = (w, h, proto_labels)

                label_map = scope_cache.get(cache_key)

                self.fuzzy_color_space.precompute_pack()

                if self._is_job_cancelled(window_id, cancel_event, job_id):
                    return

                if label_map is None:
                    img_np = np.array(source_img)
                    if img_np.ndim == 3 and img_np.shape[-1] == 4:
                        img_np = img_np[..., :3]

                    img01 = img_np.astype(np.float32) / 255.0
                    lab_img = color.rgb2lab(img01)

                    lab_q = np.round(lab_img, 2)
                    height, width = lab_q.shape[0], lab_q.shape[1]

                    lab_int = np.round(lab_q.reshape(-1, 3) * 100.0).astype(np.int32)
                    uniq, inv = np.unique(lab_int, axis=0, return_inverse=True)

                    best_for_uniq = np.empty((uniq.shape[0],), dtype=np.int32)

                    total_uniqs = int(uniq.shape[0])
                    last_update = time.perf_counter()

                    for i in range(total_uniqs):
                        if self._is_job_cancelled(window_id, cancel_event, job_id):
                            return

                        L_i, A_i, B_i = uniq[i].astype(np.float32) / 100.0
                        best_idx = self.fuzzy_color_space.best_prototype_index_from_lab((L_i, A_i, B_i))
                        best_for_uniq[i] = int(best_idx)

                        now = time.perf_counter()
                        if now - last_update > 0.03 or i == total_uniqs - 1:
                            update_progress(job_id, i + 1, total_uniqs)
                            last_update = now

                    label_map = best_for_uniq[inv].reshape(height, width).astype(np.int32)
                    scope_cache[cache_key] = label_map

                if self._is_job_cancelled(window_id, cancel_event, job_id):
                    return

                original_palette = build_original_palette_uint8()
                alt_palette = build_alt_palette_uint8()

                scheme = "original"
                palette = original_palette

                recolored_image = np.zeros((label_map.shape[0], label_map.shape[1], 3), dtype=np.uint8)
                valid_mask = (label_map >= 0)
                if np.any(valid_mask):
                    recolored_image[valid_mask] = palette[label_map[valid_mask].astype(np.int32)]

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

        def update_ui(recolored_image, new_legend_frame):
            """Update the UI safely from the main thread."""
            try:
                self.modified_image[window_id] = recolored_image

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

                x1, y1, x2, y2 = self.image_canvas.bbox(items[0])
                frame_x = x2 + 10
                frame_y = y1
                img_h = (y2 - y1)
                desired_w = 150
                desired_h = min(300, img_h)

                legend_item = self.image_canvas.create_window(
                    frame_x, frame_y,
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

        job_id = self._start_window_job(window_id, "color_mapping_all", run_process)
        if job_id is not None:
            self._show_window_loading(window_id, "Color Mapping All...")
































    # ============================================================================================================================================================
    #  FUNCTIONS DISPLAY PIXEL INFO
    # ============================================================================================================================================================

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
        Displays the pixel value in LAB format and its coordinates within a frame at the bottom of the canvas.
        Shows only the selected prototype in black text.
        Stores pixel/ROI info for the "More Info" popup.
        """
        # Create the frame and labels only once
        if not hasattr(self, "lab_value_frame"):
            self.lab_value_frame = tk.Frame(self.Canvas1, bg="lightgray", bd=1, relief="solid")
            self.lab_value_frame.place(relx=0.5, rely=0.97, anchor="s")

            text_frame = tk.Frame(self.lab_value_frame, bg="lightgray")
            text_frame.pack(side="left", padx=8, pady=4)

            bold_font = ("Sans", 11, "bold")
            normal_font = ("Sans", 11)

            # Coordinates
            tk.Label(text_frame, text="Coords:", font=bold_font, bg="lightgray").pack(side="left")
            self.coord_value = tk.Label(text_frame, text="", font=normal_font, bg="lightgray")
            self.coord_value.pack(side="left")

            tk.Label(text_frame, text="  |  ", font=bold_font, bg="lightgray").pack(side="left")

            # LAB
            tk.Label(text_frame, text="LAB:", font=bold_font, bg="lightgray").pack(side="left")
            self.lab_value_print = tk.Label(text_frame, text="", font=normal_font, bg="lightgray")
            self.lab_value_print.pack(side="left")

            tk.Label(text_frame, text="  |  ", font=bold_font, bg="lightgray").pack(side="left")

            # Selected prototype
            tk.Label(text_frame, text="Prototype:", font=bold_font, bg="lightgray").pack(side="left")
            self.proto_value_text = tk.Label(text_frame, text="", font=normal_font, bg="lightgray", fg="black")
            self.proto_value_text.pack(side="left")

            search_icon = self.load_toolbar_icon("Search.png", (24, 24))
            more_info_button = tk.Label(
                self.lab_value_frame,
                image=search_icon,
                bg="lightgray",
                cursor="hand2"
            )
            more_info_button.bind("<Button-1>", lambda e: self.show_more_info_pixel())
            more_info_button.pack(side="right", padx=6, pady=2)

        # ---------------------------
        # Membership computation
        # ---------------------------
        membership_degrees = self.fuzzy_color_space.calculate_membership(pixel_lab)

        if membership_degrees:
            max_proto = max(membership_degrees, key=membership_degrees.get)
            winner_mu = float(membership_degrees[max_proto])
            top_memberships = sorted(membership_degrees.items(), key=lambda kv: kv[1], reverse=True)
        else:
            max_proto = None
            winner_mu = 0.0
            top_memberships = []

        # ---------------------------
        # Store data for the "More Info" popup
        # ---------------------------
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

        # ---------------------------
        # Update UI
        # ---------------------------
        if selection_info and selection_info.get("type") == "roi":
            coord_text = f"({selection_info['x1']},{selection_info['y1']})→({selection_info['x2']},{selection_info['y2']})"
        else:
            coord_text = f"({x_original}, {y_original})"

        # Limit coordinates length a bit so LAB and prototype remain visible
        max_coord_len = 28
        if len(coord_text) > max_coord_len:
            coord_text = coord_text[:max_coord_len - 1] + "…"

        self.coord_value.config(text=f" {coord_text}")
        self.lab_value_print.config(text=f" {pixel_lab[0]:.2f}, {pixel_lab[1]:.2f}, {pixel_lab[2]:.2f}")

        if max_proto is None:
            self.proto_value_text.config(text=" —", fg="black")
        else:
            self.proto_value_text.config(text=f" {max_proto}", fg="black")

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
            messagebox.showinfo("More Info", "Click on an image pixel first.")
            return

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
        # ---------------------------
        # Base data
        # ---------------------------
        base_data = self._get_more_info_base_data(info)

        if not hasattr(self, "threshold_settings"):
            self.threshold_settings = {
                "metric": "CIEDE2000",
                "mode": "default",                   # default | custom
                "preset": "pt_at",                   # pt | at | pt_at
                "custom_type": "single",             # single | lower_upper
                "single": 1.0,
                "lower": 0.8,
                "upper": 1.8,
            }

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
        preset_display_map = {
            "pt": "Perceptibility Threshold",
            "at": "Acceptability Threshold",
            "pt_at": "Perceptibility + Acceptability"
        }

        custom_type_display_map = {
            "single": "Single threshold",
            "lower_upper": "Lower and upper thresholds"
        }

        saved_mode = self.threshold_settings.get("mode", "known")
        display_mode = "default" if saved_mode == "known" else saved_mode

        return {
            "selected_label_var": tk.StringVar(
                value=base_data["winner_label"] if base_data["winner_label"] != "None" else ""
            ),
            "selected_rgb_var": tk.StringVar(value=""),
            "selected_hex_var": tk.StringVar(value=""),
            "selected_lab_var": tk.StringVar(value=""),

            "threshold_metric_var": tk.StringVar(
                value=self.threshold_settings.get("metric", "CIEDE2000")
            ),
            "threshold_mode_var": tk.StringVar(value=display_mode),
            "threshold_preset_var": tk.StringVar(
                value=preset_display_map.get(
                    self.threshold_settings.get("preset", "pt_at"),
                    "Perceptibility + Acceptability"
                )
            ),
            "threshold_lower_var": tk.StringVar(
                value=str(self.threshold_settings.get("lower", 0.8))
            ),
            "threshold_upper_var": tk.StringVar(
                value=str(self.threshold_settings.get("upper", 1.8))
            ),
            "threshold_custom_type_var": tk.StringVar(
                value=custom_type_display_map.get(
                    self.threshold_settings.get("custom_type", "single"),
                    "Single threshold"
                )
            ),
            "threshold_single_var": tk.StringVar(
                value=str(self.threshold_settings.get("single", 1.0))
            ),

            "threshold_result_title_var": tk.StringVar(value=""),
            "threshold_result_detail_var": tk.StringVar(value=""),
            "threshold_result_summary_var": tk.StringVar(value=""),
            "config_hint_var": tk.StringVar(value=""),
        }


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
        """Build the threshold panel and return all relevant controls."""
        threshold_panel = tk.Frame(parent, bg="white", bd=1, relief="solid")
        threshold_panel.pack(fill="x", pady=(6, 0), anchor="n")

        tk.Label(
            threshold_panel,
            text="Threshold",
            font=("Sans", 11, "bold"),
            anchor="w",
            bg="white",
            padx=12,
            pady=10
        ).pack(fill="x")

        threshold_body = tk.Frame(threshold_panel, bg="white")
        threshold_body.pack(fill="x", padx=12, pady=(0, 10))

        # =========================================================
        # Fixed layout widths
        # =========================================================
        selection_w = 140
        config_w = 370
        result_w = 380

        threshold_body.grid_columnconfigure(0, minsize=selection_w, weight=0)
        threshold_body.grid_columnconfigure(1, minsize=1, weight=0)
        threshold_body.grid_columnconfigure(2, minsize=config_w, weight=0)
        threshold_body.grid_columnconfigure(3, minsize=1, weight=0)
        threshold_body.grid_columnconfigure(4, minsize=result_w, weight=0)

        # ---------------------------
        # Left: selection
        # ---------------------------
        section_selection = tk.Frame(threshold_body, bg="white", width=selection_w)
        section_selection.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        section_selection.grid_propagate(False)

        sep_1 = tk.Frame(threshold_body, bg="#d8d8d8", width=1, height=165)
        sep_1.grid(row=0, column=1, sticky="ns", padx=(0, 12), pady=2)

        # ---------------------------
        # Center: configuration
        # ---------------------------
        section_config = tk.Frame(threshold_body, bg="white", width=config_w)
        section_config.grid(row=0, column=2, sticky="nsw", padx=(0, 12))
        section_config.grid_propagate(False)

        sep_2 = tk.Frame(threshold_body, bg="#d8d8d8", width=1, height=165)
        sep_2.grid(row=0, column=3, sticky="ns", padx=(0, 12), pady=2)

        # ---------------------------
        # Right: results
        # ---------------------------
        section_result = tk.Frame(threshold_body, bg="white", width=result_w)
        section_result.grid(row=0, column=4, sticky="nsw")
        section_result.grid_propagate(False)
        section_result.grid_columnconfigure(0, weight=1)
        section_result.grid_rowconfigure(1, weight=1)

        # ===== Selection =====
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
            width=16,
            values=["CIEDE2000"]
        )
        metric_combo.pack(anchor="w", pady=(0, 10))

        tk.Label(
            section_selection,
            text="Threshold Type",
            font=("Sans", 10, "bold"),
            anchor="w",
            bg="white"
        ).pack(anchor="w", pady=(0, 4))

        mode_combo = ttk.Combobox(
            section_selection,
            textvariable=vars_dict["threshold_mode_var"],
            state="readonly",
            width=16,
            values=["default", "custom"]
        )
        mode_combo.pack(anchor="w")

        # ===== Configuration =====
        tk.Label(
            section_config,
            text="Configuration",
            font=("Sans", 10, "bold"),
            anchor="w",
            bg="white"
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        section_config.grid_columnconfigure(0, minsize=135, weight=0)
        section_config.grid_columnconfigure(1, minsize=config_w - 155, weight=0)

        preset_label = tk.Label(section_config, text="Default preset:", bg="white", anchor="w")
        preset_combo = ttk.Combobox(
            section_config,
            textvariable=vars_dict["threshold_preset_var"],
            state="readonly",
            width=34,
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
            width=34,
            values=[
                "Single threshold",
                "Lower and upper thresholds"
            ]
        )

        single_label = tk.Label(section_config, text="Threshold:", bg="white", anchor="w")
        single_entry = tk.Entry(section_config, textvariable=vars_dict["threshold_single_var"], width=12)

        lower_label = tk.Label(section_config, text="Lower threshold:", bg="white", anchor="w")
        lower_entry = tk.Entry(section_config, textvariable=vars_dict["threshold_lower_var"], width=12)

        upper_label = tk.Label(section_config, text="Upper threshold:", bg="white", anchor="w")
        upper_entry = tk.Entry(section_config, textvariable=vars_dict["threshold_upper_var"], width=12)

        config_hint_label = tk.Label(
            section_config,
            textvariable=vars_dict["config_hint_var"],
            bg="white",
            fg="#666666",
            anchor="w",
            justify="left",
            wraplength=config_w - 20,
            font=("Sans", 9, "italic")
        )

        # ===== Results =====
        results_title = tk.Label(
            section_result,
            text="Results",
            font=("Sans", 10, "bold"),
            anchor="w",
            bg="white"
        )
        results_title.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        result_card = tk.Frame(
            section_result,
            bg="#f8f2f2",
            bd=0,
            relief="flat",
            highlightthickness=2,
            highlightbackground="#b94a48",
            highlightcolor="#b94a48"
        )
        result_card.grid(row=1, column=0, sticky="nsew", padx=(0, 6), pady=(0, 2))

        result_header = tk.Frame(result_card, bg="#f2dede")
        result_header.pack(fill="x")

        result_status_dot = tk.Canvas(
            result_header,
            width=18,
            height=18,
            bg="#f2dede",
            highlightthickness=0,
            bd=0
        )
        result_status_dot.pack(side="left", padx=(10, 6), pady=8)
        result_status_dot_oval = result_status_dot.create_oval(3, 3, 15, 15, fill="#b94a48", outline="#b94a48")

        result_title_label = tk.Label(
            result_header,
            textvariable=vars_dict["threshold_result_title_var"],
            anchor="w",
            justify="left",
            bg="#f2dede",
            font=("Sans", 10, "bold"),
            wraplength=result_w - 65
        )
        result_title_label.pack(side="left", fill="x", expand=True, padx=(0, 12), pady=8)

        result_body = tk.Frame(result_card, bg="#f8f2f2")
        result_body.pack(fill="x", padx=12, pady=(10, 12))

        result_value_label = tk.Label(
            result_body,
            textvariable=vars_dict["threshold_result_detail_var"],
            anchor="w",
            justify="left",
            bg="#f8f2f2",
            fg="#b30000",
            font=("Sans", 9, "bold")
        )
        result_value_label.pack(anchor="w", fill="x", pady=(0, 12))

        result_separator = tk.Frame(
            result_body,
            bg="#e7b6b6",
            height=2
        )
        result_separator.pack(fill="x", padx=6, pady=(0, 10))

        result_summary_row = tk.Frame(result_body, bg="#f8f2f2")
        result_summary_row.pack(fill="x")

        result_summary_icon = tk.Canvas(
            result_summary_row,
            width=20,
            height=20,
            bg="#f8f2f2",
            highlightthickness=0,
            bd=0
        )
        result_summary_icon.pack(side="left", padx=(0, 8), anchor="n")

        icon_circle = result_summary_icon.create_oval(2, 2, 18, 18, outline="#b30000", width=2)
        icon_text = result_summary_icon.create_text(10, 10, text="!", fill="#b30000", font=("Sans", 9, "bold"))

        result_text_container = tk.Frame(result_summary_row, bg="#f8f2f2")
        result_text_container.pack(side="left", fill="both", expand=True)

        result_summary_label = tk.Label(
            result_text_container,
            textvariable=vars_dict["threshold_result_summary_var"],
            anchor="w",
            justify="left",
            bg="#f8f2f2",
            wraplength=260,
            font=("Sans", 8)
        )
        result_summary_label.pack(anchor="w", fill="x")

        def _update_result_wrap(event=None):
            try:
                result_width = max(section_result.winfo_width() - 30, 180)
                title_wrap = max(result_width - 55, 120)
                summary_wrap = max(result_width - 70, 120)

                result_title_label.config(wraplength=title_wrap)
                result_summary_label.config(wraplength=summary_wrap)
            except Exception:
                pass

        section_result.bind("<Configure>", _update_result_wrap)

        return {
            "metric_combo": metric_combo,
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
        }



    def _populate_more_info_memberships(self, base_data, vars_dict, refs):
        """Populate memberships list and wire row selection + threshold refresh."""
        membership_refs = refs["membership_refs"]
        prototype_refs = refs["prototype_refs"]
        threshold_refs = refs["threshold_refs"]

        membership_rows = membership_refs["membership_rows"]
        list_inner = membership_refs["list_inner"]

        memberships = base_data["memberships"]
        lab = base_data["lab"]

        preset_display_map = {
            "pt": "Perceptibility Threshold",
            "at": "Acceptability Threshold",
            "pt_at": "Perceptibility + Acceptability"
        }
        preset_reverse_map = {v: k for k, v in preset_display_map.items()}

        custom_type_display_map = {
            "single": "Single threshold",
            "lower_upper": "Lower and upper thresholds"
        }
        custom_type_reverse_map = {v: k for k, v in custom_type_display_map.items()}

        def highlight_selected_row(active_label):
            for lbl, row in membership_rows.items():
                if lbl == active_label:
                    row.configure(bg="#e8f0ff")
                    for child in row.winfo_children():
                        try:
                            child.configure(bg="#e8f0ff")
                        except Exception:
                            pass
                else:
                    row.configure(bg="white")
                    for child in row.winfo_children():
                        try:
                            child.configure(bg="white")
                        except Exception:
                            pass

        def apply_result_style(status):
            styles = {
                "red": {
                    "body_bg": "#f8f2f2",
                    "header_bg": "#f2dede",
                    "border": "#b94a48",
                    "accent": "#b30000",
                    "separator": "#e7b6b6",
                },
                "yellow": {
                    "body_bg": "#fffaf0",
                    "header_bg": "#fcf8e3",
                    "border": "#c09853",
                    "accent": "#9a6b00",
                    "separator": "#ecd9a3",
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

                "invalid": "neutral",
                "unavailable": "neutral",
                "unsupported_metric": "neutral",
                "unknown_mode": "neutral",
            }

            theme_key = status_to_theme.get(status, "neutral")
            theme = styles[theme_key]

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
                threshold_refs["result_summary_icon"].itemconfig(
                    threshold_refs["result_summary_icon_circle"],
                    outline=theme["accent"]
                )
                threshold_refs["result_summary_icon"].itemconfig(
                    threshold_refs["result_summary_icon_text"],
                    fill=theme["accent"]
                )
                threshold_refs["result_summary_label"].configure(bg=theme["body_bg"])

                threshold_refs["result_status_dot"].itemconfig(
                    threshold_refs["result_status_dot_oval"],
                    fill=theme["border"],
                    outline=theme["border"]
                )
            except Exception:
                pass

        def refresh_threshold_section(proto_lab=None):
            mode_value = vars_dict["threshold_mode_var"].get().strip().lower()
            internal_mode = "known" if mode_value == "default" else mode_value

            selected_preset_display = vars_dict["threshold_preset_var"].get().strip()
            selected_preset_key = preset_reverse_map.get(selected_preset_display, "pt_at")

            selected_custom_type_display = vars_dict["threshold_custom_type_var"].get().strip()
            selected_custom_type_key = custom_type_reverse_map.get(selected_custom_type_display, "single")

            single_text = vars_dict["threshold_single_var"].get().strip()
            lower_text = vars_dict["threshold_lower_var"].get().strip()
            upper_text = vars_dict["threshold_upper_var"].get().strip()

            self.threshold_settings["metric"] = vars_dict["threshold_metric_var"].get().strip()
            self.threshold_settings["mode"] = internal_mode
            self.threshold_settings["preset"] = selected_preset_key
            self.threshold_settings["custom_type"] = selected_custom_type_key

            self.threshold_settings["single"] = single_text if single_text != "" else None
            self.threshold_settings["lower"] = lower_text if lower_text != "" else None
            self.threshold_settings["upper"] = upper_text if upper_text != "" else None

            threshold_refs["preset_label"].grid_remove()
            threshold_refs["preset_combo"].grid_remove()
            threshold_refs["custom_type_label"].grid_remove()
            threshold_refs["custom_type_combo"].grid_remove()
            threshold_refs["single_label"].grid_remove()
            threshold_refs["single_entry"].grid_remove()
            threshold_refs["lower_label"].grid_remove()
            threshold_refs["lower_entry"].grid_remove()
            threshold_refs["upper_label"].grid_remove()
            threshold_refs["upper_entry"].grid_remove()
            threshold_refs["config_hint_label"].grid_remove()

            if mode_value == "default":
                threshold_refs["preset_label"].grid(row=1, column=0, sticky="w", pady=(0, 6), padx=(0, 10))
                threshold_refs["preset_combo"].grid(row=1, column=1, sticky="ew", pady=(0, 6))

                vars_dict["config_hint_var"].set(
                    "Use predefined perceptibility and/or acceptability thresholds."
                )
                threshold_refs["config_hint_label"].grid(
                    row=2, column=0, columnspan=2, sticky="ew", pady=(2, 0)
                )

            elif mode_value == "custom":
                threshold_refs["custom_type_label"].grid(row=1, column=0, sticky="w", pady=(0, 6), padx=(0, 10))
                threshold_refs["custom_type_combo"].grid(row=1, column=1, sticky="ew", pady=(0, 6))

                if selected_custom_type_key == "single":
                    threshold_refs["single_label"].grid(row=2, column=0, sticky="w", pady=(0, 6), padx=(0, 10))
                    threshold_refs["single_entry"].grid(row=2, column=1, sticky="w", pady=(0, 6))

                    vars_dict["config_hint_var"].set("Define one threshold greater than 0.")

                    if single_text == "":
                        vars_dict["config_hint_var"].set("Enter a threshold greater than 0.")
                    else:
                        _, err_single = self._parse_positive_threshold(single_text)
                        if err_single:
                            vars_dict["config_hint_var"].set(err_single)

                    threshold_refs["config_hint_label"].grid(
                        row=3, column=0, columnspan=2, sticky="ew", pady=(2, 0)
                    )

                else:
                    threshold_refs["lower_label"].grid(row=2, column=0, sticky="w", pady=(0, 6), padx=(0, 10))
                    threshold_refs["lower_entry"].grid(row=2, column=1, sticky="w", pady=(0, 6))
                    threshold_refs["upper_label"].grid(row=3, column=0, sticky="w", pady=(0, 6), padx=(0, 10))
                    threshold_refs["upper_entry"].grid(row=3, column=1, sticky="w", pady=(0, 6))

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

                    threshold_refs["config_hint_label"].grid(
                        row=4, column=0, columnspan=2, sticky="ew", pady=(2, 0)
                    )

            else:
                vars_dict["config_hint_var"].set("")

            if proto_lab is None:
                vars_dict["threshold_result_title_var"].set("Select a prototype to evaluate")
                vars_dict["threshold_result_detail_var"].set("")
                vars_dict["threshold_result_summary_var"].set("")
                apply_result_style("unavailable")
                return

            evaluation = self.evaluate_color_difference_threshold(
                sample_lab=lab,
                prototype_lab=proto_lab,
                metric=self.threshold_settings.get("metric", "CIEDE2000"),
                threshold_settings=self.threshold_settings
            )

            delta_e_value = evaluation.get("delta_e")
            status = evaluation.get("status", "unavailable")

            if delta_e_value is None:
                vars_dict["threshold_result_title_var"].set("ΔE not available")
                vars_dict["threshold_result_detail_var"].set("Unable to compute color difference")
                vars_dict["threshold_result_summary_var"].set(
                    evaluation.get("summary", "")
                )
                apply_result_style(status)
                return

            vars_dict["threshold_result_title_var"].set(
                evaluation.get("evaluation", "No evaluation available")
            )
            vars_dict["threshold_result_detail_var"].set(f"ΔE00 = {delta_e_value:.3f}")
            vars_dict["threshold_result_summary_var"].set(
                evaluation.get("summary_visual", evaluation.get("summary", ""))
            )

            apply_result_style(status)

        def select_membership(label, mu):
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
                        lambda e, label=lbl, mu_value=mu: select_membership(label, mu_value)
                    )
        else:
            tk.Label(
                list_inner,
                text="No memberships available.",
                anchor="w",
                bg="white"
            ).pack(fill="x")

        if memberships:
            initial_label = base_data["winner_label"] if base_data["winner_label"] not in (None, "None", "") else memberships[0][0]
            initial_mu = None
            for lbl, mu in memberships:
                if lbl == initial_label:
                    initial_mu = mu
                    break
            if initial_mu is None:
                initial_label, initial_mu = memberships[0]

            select_membership(initial_label, initial_mu)



    def _parse_positive_threshold(self, value):
        if value is None:
            return None, "Threshold cannot be empty."

        text = str(value).strip()
        if text == "":
            return None, "Threshold cannot be empty."

        try:
            parsed = float(text)
        except Exception:
            return None, "Threshold must be a valid number."

        if parsed <= 0:
            return None, "Threshold must be greater than 0."

        return parsed, None
    

    def _validate_custom_range(self, lower_value, upper_value):
        lower, err_lower = self._parse_positive_threshold(lower_value)
        if err_lower:
            return None, None, f"Lower threshold: {err_lower}"

        upper, err_upper = self._parse_positive_threshold(upper_value)
        if err_upper:
            return None, None, f"Upper threshold: {err_upper}"

        if lower >= upper:
            return None, None, "Lower thr. must be smaller than upper thr."

        return lower, upper, None


    def evaluate_color_difference_threshold(self, sample_lab, prototype_lab, metric="CIEDE2000", threshold_settings=None):
        """
        Compute the color difference between a sampled color and a prototype color,
        then evaluate that difference according to the active threshold configuration.
        """
        default_settings = {
            "mode": "default",
            "preset": "pt_at",
            "custom_type": "single",
            "single": None,
            "lower": None,
            "upper": None,
        }

        if threshold_settings is None:
            threshold_settings = default_settings
        else:
            merged = default_settings.copy()
            merged.update(threshold_settings)
            threshold_settings = merged

        mode = threshold_settings.get("mode", "default")
        if mode == "known":
            mode = "default"

        result = {
            "metric": metric,
            "delta_e": None,
            "mode": mode,
            "preset": threshold_settings.get("preset"),
            "lower": None,
            "upper": None,
            "status": "unavailable",
            "evaluation": "Color difference could not be computed.",
            "summary": "ΔE: not available",
            "summary_visual": "No threshold result available."
        }

        try:
            if metric == "CIEDE2000":
                delta_e_value = float(self.color_manager.delta_e_ciede2000(prototype_lab, sample_lab))
            else:
                result["status"] = "unsupported_metric"
                result["evaluation"] = f"Metric '{metric}' is not supported yet."
                result["summary"] = f"Metric: {metric} (not supported)"
                result["summary_visual"] = "This metric is not supported yet."
                return result
        except Exception:
            return result

        result["delta_e"] = delta_e_value

        # ---------------------------
        # DEFAULT MODE
        # ---------------------------
        if mode == "default":
            preset = threshold_settings.get("preset", "pt_at")
            result["preset"] = preset

            if preset == "pt":
                lower = 0.8
                result["lower"] = lower

                if delta_e_value <= lower:
                    result["status"] = "below_pt"
                    result["evaluation"] = "Within perceptibility threshold."
                    result["summary_visual"] = "The sampled color is within the perceptibility threshold."
                else:
                    result["status"] = "above_pt"
                    result["evaluation"] = "Outside perceptibility threshold."
                    result["summary_visual"] = "The sampled color exceeds the perceptibility threshold."

                result["summary"] = f"ΔE = {delta_e_value:.3f} | PT = {lower:.3f}"
                return result

            elif preset == "at":
                upper = 1.8
                result["upper"] = upper

                if delta_e_value <= upper:
                    result["status"] = "below_at"
                    result["evaluation"] = "Within acceptability threshold."
                    result["summary_visual"] = "The sampled color is within the acceptability threshold."
                else:
                    result["status"] = "above_at"
                    result["evaluation"] = "Outside acceptability threshold."
                    result["summary_visual"] = "The sampled color exceeds the acceptability threshold."

                result["summary"] = f"ΔE = {delta_e_value:.3f} | AT = {upper:.3f}"
                return result

            else:  # pt_at
                lower = 0.8
                upper = 1.8

                result["lower"] = lower
                result["upper"] = upper

                if delta_e_value <= lower:
                    result["status"] = "below_pt"
                    result["evaluation"] = "Below perceptibility threshold."
                    result["summary_visual"] = "The sampled color is below the perceptibility threshold."
                elif delta_e_value <= upper:
                    result["status"] = "between_pt_at"
                    result["evaluation"] = "Between perceptibility and acceptability thresholds."
                    result["summary_visual"] = "The sampled color is perceptible, but still within the acceptability range."
                else:
                    result["status"] = "above_at"
                    result["evaluation"] = "Above acceptability threshold."
                    result["summary_visual"] = "The sampled color exceeds the acceptability threshold."

                result["summary"] = f"ΔE = {delta_e_value:.3f} | PT = {lower:.3f} | AT = {upper:.3f}"
                return result

        # ---------------------------
        # CUSTOM MODE
        # ---------------------------
        if mode == "custom":
            custom_type = threshold_settings.get("custom_type", "single")
            result["custom_type"] = custom_type

            if custom_type == "single":
                single, err_single = self._parse_positive_threshold(
                    threshold_settings.get("single")
                )
                result["single"] = single

                if err_single:
                    result["status"] = "invalid"
                    result["evaluation"] = err_single
                    result["summary"] = f"ΔE = {delta_e_value:.3f}"
                    result["summary_visual"] = "Please enter a valid custom threshold."
                    return result

                if delta_e_value <= single:
                    result["status"] = "below_custom"
                    result["evaluation"] = "Within custom threshold."
                    result["summary_visual"] = "The sampled color is within the selected custom threshold."
                else:
                    result["status"] = "above_custom"
                    result["evaluation"] = "Outside custom threshold."
                    result["summary_visual"] = "The sampled color exceeds the selected custom threshold."

                result["summary"] = f"ΔE = {delta_e_value:.3f} | threshold = {single:.3f}"
                return result

            elif custom_type == "lower_upper":
                lower, upper, err_range = self._validate_custom_range(
                    threshold_settings.get("lower"),
                    threshold_settings.get("upper")
                )

                result["lower"] = lower
                result["upper"] = upper

                if err_range:
                    result["status"] = "invalid"
                    result["evaluation"] = err_range
                    result["summary"] = f"ΔE = {delta_e_value:.3f}"
                    result["summary_visual"] = "Please enter a valid lower and upper threshold."
                    return result

                if delta_e_value <= lower:
                    result["status"] = "below_lower"
                    result["evaluation"] = "Below lower threshold."
                    result["summary_visual"] = "The sampled color is below the lower threshold."
                elif delta_e_value <= upper:
                    result["status"] = "between_custom"
                    result["evaluation"] = "Between lower and upper thresholds."
                    result["summary_visual"] = "The sampled color falls between the lower and upper thresholds."
                else:
                    result["status"] = "above_upper"
                    result["evaluation"] = "Above upper threshold."
                    result["summary_visual"] = "The sampled color exceeds the upper threshold."

                result["summary"] = f"ΔE = {delta_e_value:.3f} | lower = {lower:.3f} | upper = {upper:.3f}"
                return result

        result["status"] = "unknown_mode"
        result["evaluation"] = f"Unknown threshold mode: {mode}"
        result["summary"] = f"ΔE = {delta_e_value:.3f}"
        result["summary_visual"] = "The threshold mode could not be interpreted."
        return result




















    # ============================================================================================================================================================
    #  COLOR EVALUATION FUNCTIONS
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





    def color_evaluation(self):
        """Open a window to study color spaces and threshold configurations."""
        # Close previous window if already open
        try:
            if hasattr(self, "_color_evaluation_window") and self._color_evaluation_window is not None:
                if self._color_evaluation_window.winfo_exists():
                    self._color_evaluation_window.lift()
                    self._color_evaluation_window.focus_force()
                    return
        except Exception:
            pass

        if not hasattr(self, "threshold_settings"):
            self.threshold_settings = {
                "metric": "CIEDE2000",
                "mode": "default",           # default | custom
                "preset": "pt_at",           # pt | at | pt_at
                "custom_type": "single",     # single | lower_upper
                "single": 1.0,
                "lower": 0.8,
                "upper": 1.8,
            }

        win = tk.Toplevel(self.root)
        self._color_evaluation_window = win

        win.title("Color Space Evaluation")
        WIN_W, WIN_H = 1080, 760
        win.geometry(f"{WIN_W}x{WIN_H}")
        win.minsize(980, 680)
        win.resizable(True, True)

        win.configure(bg="#f2f2f2")
        win.protocol("WM_DELETE_WINDOW", self._on_close_color_evaluation_window)

        self._build_color_evaluation_window(win)

        # Quitar transient para permitir maximizar/minimizar normal
        win.focus_set()

        try:
            win.state("zoomed")
        except Exception:
            pass

        win.after_idle(self._set_color_evaluation_initial_sash)




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

            sash_x = int(total_w * 0.8)  # 75% table | 25% analysis
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
        threshold_panel = tk.Frame(main, bg="white", bd=1, relief="solid")
        threshold_panel.pack(fill="x", pady=(0, 10))

        tk.Label(
            threshold_panel,
            text="Threshold Configuration",
            font=("Sans", 11, "bold"),
            anchor="w",
            bg="white",
            padx=12,
            pady=10
        ).pack(fill="x")

        threshold_body = tk.Frame(threshold_panel, bg="white")
        threshold_body.pack(fill="x", padx=12, pady=(0, 10))

        section_selection = tk.Frame(threshold_body, bg="white")
        section_selection.pack(side="left", fill="y", padx=(0, 12))

        sep_1 = tk.Frame(threshold_body, bg="#d8d8d8", width=1, height=120)
        sep_1.pack(side="left", fill="y", padx=(0, 12), pady=2)

        section_config = tk.Frame(threshold_body, bg="white")
        section_config.pack(side="left", fill="both", expand=True, padx=(0, 12))

        sep_2 = tk.Frame(threshold_body, bg="#d8d8d8", width=1, height=120)
        sep_2.pack(side="left", fill="y", padx=(0, 12), pady=2)

        section_summary = tk.Frame(threshold_body, bg="white")
        section_summary.pack(side="left", fill="both", expand=True)

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
            width=18,
            values=["CIEDE2000"]
        )
        metric_combo.pack(anchor="w", pady=(0, 10))

        tk.Label(
            section_selection,
            text="Threshold Type",
            font=("Sans", 10, "bold"),
            anchor="w",
            bg="white"
        ).pack(anchor="w", pady=(0, 4))

        mode_combo = ttk.Combobox(
            section_selection,
            textvariable=vars_dict["threshold_mode_var"],
            state="readonly",
            width=18,
            values=["default", "custom"]
        )
        mode_combo.pack(anchor="w")

        tk.Label(
            section_config,
            text="Configuration",
            font=("Sans", 10, "bold"),
            anchor="w",
            bg="white"
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        preset_label = tk.Label(section_config, text="Default preset:", bg="white", anchor="w")
        preset_combo = ttk.Combobox(
            section_config,
            textvariable=vars_dict["threshold_preset_var"],
            state="readonly",
            width=28,
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
            width=28,
            values=[
                "Single threshold",
                "Lower and upper thresholds"
            ]
        )

        single_label = tk.Label(section_config, text="Threshold:", bg="white", anchor="w")
        single_entry = tk.Entry(section_config, textvariable=vars_dict["threshold_single_var"], width=10)

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
            wraplength=280,
            font=("Sans", 9, "italic")
        )

        tk.Label(
            section_summary,
            text="Current Threshold Summary",
            font=("Sans", 10, "bold"),
            anchor="w",
            bg="white"
        ).pack(anchor="w", pady=(0, 8))

        tk.Label(
            section_summary,
            textvariable=vars_dict["threshold_summary_title_var"],
            anchor="w",
            justify="left",
            bg="white",
            font=("Sans", 10, "bold"),
            wraplength=300
        ).pack(anchor="w", fill="x", pady=(0, 6))

        tk.Label(
            section_summary,
            textvariable=vars_dict["threshold_summary_detail_var"],
            anchor="w",
            justify="left",
            bg="white",
            wraplength=300
        ).pack(anchor="w", fill="x", pady=(0, 6))

        tk.Label(
            section_summary,
            textvariable=vars_dict["threshold_summary_extra_var"],
            anchor="w",
            justify="left",
            bg="white",
            wraplength=300
        ).pack(anchor="w", fill="x")

        refs = {
            "metric_combo": metric_combo,
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
        }

        # =========================
        # Color Space Data block
        # =========================
        table_panel = tk.Frame(main, bg="white", bd=1, relief="solid")
        table_panel.pack(fill="both", expand=True)

        # Header row
        header_container = tk.Frame(table_panel, bg="white", height=42)
        header_container.pack(fill="x", padx=12, pady=(4, 2))
        header_container.pack_propagate(False)

        # Title on the left
        tk.Label(
            header_container,
            text="Color Space Data",
            font=("Sans", 11, "bold"),
            anchor="w",
            bg="white"
        ).pack(side="left")

        # Centered buttons, independent from title width
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

        # Summary stays on its own row, centered
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

        paned.add(left_panel, minsize=620)
        paned.add(right_panel, minsize=360)

        # Save reference to paned window so sash can be positioned after final window sizing
        self._color_evaluation_paned = paned

        # -------------------------
        # Left panel
        # -------------------------
        list_header = tk.Frame(left_panel, bg="#f4f4f4")
        list_header.pack(fill="x", padx=1, pady=(1, 0))

        # Columnas fijas + filler
        list_header.grid_columnconfigure(0, minsize=110)  # swatch
        list_header.grid_columnconfigure(1, minsize=190)  # label
        list_header.grid_columnconfigure(2, minsize=170)  # lab
        list_header.grid_columnconfigure(3, minsize=135)  # rgb
        list_header.grid_columnconfigure(4, minsize=105)  # hex
        list_header.grid_columnconfigure(5, weight=1)     # filler

        header_font = ("Sans", 10, "bold")

        tk.Label(list_header, text="", bg="#f4f4f4", font=header_font).grid(
            row=0, column=0, sticky="w", padx=(8, 4), pady=8
        )
        tk.Label(list_header, text="Label", bg="#f4f4f4", font=header_font, anchor="w").grid(
            row=0, column=1, sticky="w", padx=(2, 2), pady=8
        )
        tk.Label(list_header, text="LAB", bg="#f4f4f4", font=header_font, anchor="center").grid(
            row=0, column=2, sticky="ew", padx=(2, 2), pady=8
        )
        tk.Label(list_header, text="RGB", bg="#f4f4f4", font=header_font, anchor="center").grid(
            row=0, column=3, sticky="ew", padx=(2, 2), pady=8
        )
        tk.Label(list_header, text="HEX", bg="#f4f4f4", font=header_font, anchor="center").grid(
            row=0, column=4, sticky="ew", padx=(2, 6), pady=8
        )
        tk.Label(list_header, text="", bg="#f4f4f4", font=header_font).grid(
            row=0, column=5, sticky="ew", padx=0, pady=8
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
        analysis_actions.pack(fill="x", padx=12, pady=(0, 8))

        tk.Button(
            analysis_actions,
            text="Compare with another color",
            command=lambda: self._enable_color_evaluation_comparison_mode(vars_dict)
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))

        tk.Button(
            analysis_actions,
            text="Clear comparison",
            command=lambda: self._clear_color_evaluation_comparison(vars_dict)
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))

        tk.Button(
            analysis_actions,
            text="Evaluate custom color",
            command=lambda: self._open_custom_color_input_dialog(vars_dict)
        ).pack(side="left", fill="x", expand=True)

        tk.Label(
            right_panel,
            textvariable=vars_dict["analysis_mode_var"],
            anchor="w",
            bg="white",
            fg="#555555",
            font=("Sans", 9, "italic"),
            padx=12
        ).pack(fill="x", pady=(0, 8))

        analysis_body = tk.Frame(right_panel, bg="white")
        analysis_body.pack(fill="both", expand=True, padx=12, pady=(0, 10))

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

        results_block = tk.Frame(analysis_body, bg="white")
        results_block.pack(fill="both", expand=True)

        tk.Label(
            results_block,
            text="Results",
            font=("Sans", 10, "bold"),
            anchor="w",
            bg="white"
        ).pack(anchor="w", pady=(0, 8))

        tk.Label(
            results_block,
            textvariable=vars_dict["selected_result_var"],
            anchor="w",
            justify="left",
            wraplength=360,
            bg="white",
            font=("Sans", 10, "bold")
        ).pack(fill="x", pady=(0, 6))

        tk.Label(
            results_block,
            textvariable=vars_dict["selected_summary_var"],
            anchor="w",
            justify="left",
            wraplength=360,
            bg="white"
        ).pack(fill="x")

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
            metric_combo,
            mode_combo,
            preset_combo,
            custom_type_combo,
        ):
            widget.bind(
                "<<ComboboxSelected>>",
                lambda e: self._refresh_color_evaluation_threshold_ui(vars_dict, refs)
            )

        for widget in (
            single_entry,
            lower_entry,
            upper_entry,
        ):
            widget.bind(
                "<KeyRelease>",
                lambda e: self._refresh_color_evaluation_threshold_ui(vars_dict, refs)
            )

        self._refresh_color_evaluation_threshold_ui(vars_dict, refs)
        self._load_current_color_space_for_evaluation(vars_dict)



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
                result["prototypes"] = getattr(fuzzy_cs, "prototypes", None)

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
        preset_display_map = {
            "pt": "Perceptibility Threshold",
            "at": "Acceptability Threshold",
            "pt_at": "Perceptibility + Acceptability"
        }

        custom_type_display_map = {
            "single": "Single threshold",
            "lower_upper": "Lower and upper thresholds"
        }

        saved_mode = self.threshold_settings.get("mode", "default")
        if saved_mode == "known":
            saved_mode = "default"

        return {
            "threshold_metric_var": tk.StringVar(
                value=self.threshold_settings.get("metric", "CIEDE2000")
            ),
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
                value=str(self.threshold_settings.get("single", 1.0))
            ),
            "threshold_lower_var": tk.StringVar(
                value=str(self.threshold_settings.get("lower", 0.8))
            ),
            "threshold_upper_var": tk.StringVar(
                value=str(self.threshold_settings.get("upper", 1.8))
            ),

            "threshold_summary_title_var": tk.StringVar(value=""),
            "threshold_summary_detail_var": tk.StringVar(value=""),
            "threshold_summary_extra_var": tk.StringVar(value=""),
            "config_hint_var": tk.StringVar(value=""),

            "space_name_var": tk.StringVar(value="None"),
            "space_count_var": tk.StringVar(value="0"),

            "analysis_mode_var": tk.StringVar(value="Select a color from the list."),
            "primary_name_var": tk.StringVar(value="None"),

            "secondary_name_var": tk.StringVar(value="None"),

            "selected_result_var": tk.StringVar(value="Select a prototype from the list."),
            "selected_summary_var": tk.StringVar(value=""),

            "loaded_space_data": None,
            "loaded_space_name": "",
            "loaded_space_type": None,
            "loaded_fuzzy_color_space": None,
            "loaded_cores": None,
            "loaded_supports": None,
            "loaded_prototypes": None,
            "loaded_file_path": None,
        }




    def _refresh_color_evaluation_threshold_ui(self, vars_dict, refs):
        """Refresh threshold controls, validate inputs, and update summary."""
        preset_display_map = {
            "pt": "Perceptibility Threshold",
            "at": "Acceptability Threshold",
            "pt_at": "Perceptibility + Acceptability"
        }
        preset_reverse_map = {v: k for k, v in preset_display_map.items()}

        custom_type_display_map = {
            "single": "Single threshold",
            "lower_upper": "Lower and upper thresholds"
        }
        custom_type_reverse_map = {v: k for k, v in custom_type_display_map.items()}

        mode_value = vars_dict["threshold_mode_var"].get().strip().lower()
        selected_preset_display = vars_dict["threshold_preset_var"].get().strip()
        selected_custom_type_display = vars_dict["threshold_custom_type_var"].get().strip()

        single_text = vars_dict["threshold_single_var"].get().strip()
        lower_text = vars_dict["threshold_lower_var"].get().strip()
        upper_text = vars_dict["threshold_upper_var"].get().strip()

        self.threshold_settings["metric"] = vars_dict["threshold_metric_var"].get().strip()
        self.threshold_settings["mode"] = mode_value
        self.threshold_settings["preset"] = preset_reverse_map.get(selected_preset_display, "pt_at")
        self.threshold_settings["custom_type"] = custom_type_reverse_map.get(selected_custom_type_display, "single")
        self.threshold_settings["single"] = single_text if single_text != "" else None
        self.threshold_settings["lower"] = lower_text if lower_text != "" else None
        self.threshold_settings["upper"] = upper_text if upper_text != "" else None

        refs["preset_label"].grid_remove()
        refs["preset_combo"].grid_remove()
        refs["custom_type_label"].grid_remove()
        refs["custom_type_combo"].grid_remove()
        refs["single_label"].grid_remove()
        refs["single_entry"].grid_remove()
        refs["lower_label"].grid_remove()
        refs["lower_entry"].grid_remove()
        refs["upper_label"].grid_remove()
        refs["upper_entry"].grid_remove()
        refs["config_hint_label"].grid_remove()

        if mode_value == "default":
            refs["preset_label"].grid(row=1, column=0, sticky="w", pady=(0, 6))
            refs["preset_combo"].grid(row=1, column=1, sticky="w", pady=(0, 6))

            vars_dict["config_hint_var"].set(
                "Use predefined perceptibility and/or acceptability thresholds."
            )
            refs["config_hint_label"].grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))

            preset_key = self.threshold_settings.get("preset", "pt_at")
            if preset_key == "pt":
                vars_dict["threshold_summary_title_var"].set("Default mode")
                vars_dict["threshold_summary_detail_var"].set("Preset: Perceptibility Threshold")
                vars_dict["threshold_summary_extra_var"].set("PT = 0.800")
            elif preset_key == "at":
                vars_dict["threshold_summary_title_var"].set("Default mode")
                vars_dict["threshold_summary_detail_var"].set("Preset: Acceptability Threshold")
                vars_dict["threshold_summary_extra_var"].set("AT = 1.800")
            else:
                vars_dict["threshold_summary_title_var"].set("Default mode")
                vars_dict["threshold_summary_detail_var"].set("Preset: Perceptibility + Acceptability")
                vars_dict["threshold_summary_extra_var"].set("PT = 0.800 | AT = 1.800")

        elif mode_value == "custom":
            refs["custom_type_label"].grid(row=1, column=0, sticky="w", pady=(0, 6))
            refs["custom_type_combo"].grid(row=1, column=1, sticky="w", pady=(0, 6))

            custom_type = self.threshold_settings.get("custom_type", "single")

            if custom_type == "single":
                refs["single_label"].grid(row=2, column=0, sticky="w", pady=(0, 6))
                refs["single_entry"].grid(row=2, column=1, sticky="w", pady=(0, 6))

                vars_dict["threshold_summary_title_var"].set("Custom mode")
                vars_dict["threshold_summary_detail_var"].set("Configuration: Single threshold")

                if single_text == "":
                    vars_dict["config_hint_var"].set("Enter a threshold greater than 0.")
                    vars_dict["threshold_summary_extra_var"].set("Threshold not defined yet.")
                else:
                    parsed, err = self._parse_positive_threshold(single_text)
                    if err:
                        vars_dict["config_hint_var"].set(err)
                        vars_dict["threshold_summary_extra_var"].set("Invalid threshold value.")
                    else:
                        vars_dict["config_hint_var"].set("Define one threshold greater than 0.")
                        vars_dict["threshold_summary_extra_var"].set(f"Threshold = {parsed:.3f}")

                refs["config_hint_label"].grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 0))

            else:
                refs["lower_label"].grid(row=2, column=0, sticky="w", pady=(0, 6))
                refs["lower_entry"].grid(row=2, column=1, sticky="w", pady=(0, 6))
                refs["upper_label"].grid(row=3, column=0, sticky="w", pady=(0, 6))
                refs["upper_entry"].grid(row=3, column=1, sticky="w", pady=(0, 6))

                vars_dict["threshold_summary_title_var"].set("Custom mode")
                vars_dict["threshold_summary_detail_var"].set("Configuration: Lower and upper thresholds")

                if lower_text == "" or upper_text == "":
                    vars_dict["config_hint_var"].set("Enter both thresholds. Values must be greater than 0.")
                    vars_dict["threshold_summary_extra_var"].set("Thresholds not fully defined yet.")
                else:
                    lower, upper, err = self._validate_custom_range(lower_text, upper_text)
                    if err:
                        vars_dict["config_hint_var"].set(err)
                        vars_dict["threshold_summary_extra_var"].set("Invalid threshold range.")
                    else:
                        vars_dict["config_hint_var"].set(
                            "Define two thresholds greater than 0, with lower < upper."
                        )
                        vars_dict["threshold_summary_extra_var"].set(
                            f"Lower = {lower:.3f} | Upper = {upper:.3f}"
                        )

                refs["config_hint_label"].grid(row=4, column=0, columnspan=2, sticky="w", pady=(2, 0))

        else:
            vars_dict["threshold_summary_title_var"].set("Unknown mode")
            vars_dict["threshold_summary_detail_var"].set("")
            vars_dict["threshold_summary_extra_var"].set("")
            vars_dict["config_hint_var"].set("")

        self._refresh_color_evaluation_comparison(vars_dict)




    def _get_color_evaluation_threshold_description(self):
        """Return a compact textual description of the active threshold settings."""
        metric = self.threshold_settings.get("metric", "CIEDE2000")
        mode = self.threshold_settings.get("mode", "default")

        if mode == "known":
            mode = "default"

        if mode == "default":
            preset = self.threshold_settings.get("preset", "pt_at")
            if preset == "pt":
                return f"Thresholds -> Metric: {metric} | Mode: default | PT = 0.800"
            elif preset == "at":
                return f"Thresholds -> Metric: {metric} | Mode: default | AT = 1.800"
            return f"Thresholds -> Metric: {metric} | Mode: default | PT = 0.800 | AT = 1.800"

        if mode == "custom":
            custom_type = self.threshold_settings.get("custom_type", "single")
            if custom_type == "single":
                val = self.threshold_settings.get("single")
                parsed, err = self._parse_positive_threshold(val)
                if err:
                    return f"Thresholds -> Metric: {metric} | Mode: custom | Single threshold: invalid"
                return f"Thresholds -> Metric: {metric} | Mode: custom | Threshold = {parsed:.3f}"

            lower, upper, err = self._validate_custom_range(
                self.threshold_settings.get("lower"),
                self.threshold_settings.get("upper")
            )
            if err:
                return f"Thresholds -> Metric: {metric} | Mode: custom | Lower/Upper thresholds: invalid"
            return f"Thresholds -> Metric: {metric} | Mode: custom | Lower = {lower:.3f} | Upper = {upper:.3f}"

        return f"Thresholds -> Metric: {metric} | Mode: {mode}"



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
        Calculate membership degrees using the color space currently loaded
        in the Color Space Evaluation window.
        """
        fuzzy_cs = vars_dict.get("loaded_fuzzy_color_space")

        if fuzzy_cs is None:
            return []

        try:
            membership_degrees = fuzzy_cs.calculate_membership(sample_lab)
        except Exception:
            return []

        if not membership_degrees:
            return []

        return sorted(
            membership_degrees.items(),
            key=lambda kv: kv[1],
            reverse=True
        )


    def _update_color_evaluation_space_summary(self, vars_dict):
        data_source = vars_dict.get("loaded_space_data") or {}
        space_name = vars_dict.get("loaded_space_name", "Unnamed color space")

        valid_rows = self._extract_color_space_rows(data_source)

        vars_dict["space_name_var"].set(space_name)
        vars_dict["space_count_var"].set(str(len(valid_rows)))
        

    def _extract_color_space_rows(self, data_source):
        """Return normalized rows [(label, lab_array), ...] from a color space dict."""
        rows = []

        if not isinstance(data_source, dict):
            return rows

        for color_name, color_value in data_source.items():
            if not isinstance(color_value, dict):
                continue

            lab = None
            if "positive_prototype" in color_value:
                lab = color_value["positive_prototype"]
            elif "Color" in color_value:
                lab = color_value["Color"]

            if lab is None:
                continue

            try:
                lab_arr = np.array(lab, dtype=float)
                if lab_arr.shape[0] < 3:
                    continue
                rows.append((color_name, lab_arr))
            except Exception:
                continue

        return rows
        


    def _render_color_evaluation_cards(self, vars_dict, data_source):
        """Render color prototypes as selectable rows aligned with the header."""
        rows_inner = vars_dict["rows_inner"]

        for child in rows_inner.winfo_children():
            child.destroy()

        vars_dict["color_row_refs"] = {}
        vars_dict["primary_label"] = None
        vars_dict["secondary_label"] = None
        vars_dict["comparison_mode"] = False
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
                    vars_dict["analysis_mode_var"].set(
                        "Comparison mode active. Click another color to update the comparison or clear it to exit."
                    )
            else:
                vars_dict["primary_label"] = label
                vars_dict["secondary_label"] = None
                vars_dict["analysis_mode_var"].set("Single color selected.")

            self._refresh_color_evaluation_comparison(vars_dict)
            _highlight_rows()

        for label, lab in rows:
            try:
                rgb_float = color.lab2rgb([lab])[0]
                rgb = tuple(max(0, min(255, int(v * 255))) for v in rgb_float)
            except Exception:
                rgb = (200, 200, 200)

            hex_color = self._safe_hex_from_rgb(rgb)

            row = tk.Frame(rows_inner, bg="white", bd=1, relief="solid", cursor="hand2")
            row.pack(fill="x", padx=8, pady=3)

            content = tk.Frame(row, bg="white")
            content.pack(fill="x", padx=8, pady=7)

            content.grid_columnconfigure(0, minsize=110)
            content.grid_columnconfigure(1, minsize=190)
            content.grid_columnconfigure(2, minsize=170)
            content.grid_columnconfigure(3, minsize=135)
            content.grid_columnconfigure(4, minsize=105)
            content.grid_columnconfigure(5, weight=1)

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

            lbl_lab = tk.Label(
                content,
                text=f"{lab[0]:.2f}, {lab[1]:.2f}, {lab[2]:.2f}",
                anchor="center",
                justify="center",
                bg="white",
                font=("Sans", 10)
            )
            lbl_lab.grid(row=0, column=2, sticky="ew", padx=(2, 2))

            lbl_rgb = tk.Label(
                content,
                text=f"{int(rgb[0])}, {int(rgb[1])}, {int(rgb[2])}",
                anchor="center",
                justify="center",
                bg="white",
                font=("Sans", 10)
            )
            lbl_rgb.grid(row=0, column=3, sticky="ew", padx=(2, 2))

            lbl_hex = tk.Label(
                content,
                text=hex_color.upper(),
                anchor="center",
                justify="center",
                bg="white",
                font=("Sans", 10)
            )
            lbl_hex.grid(row=0, column=4, sticky="ew", padx=(2, 6))

            filler = tk.Label(content, text="", bg="white")
            filler.grid(row=0, column=5, sticky="ew")

            widgets = [swatch, lbl_name, lbl_lab, lbl_rgb, lbl_hex, filler]

            vars_dict["color_row_refs"][label] = {
                "frame": row,
                "content": content,
                "widgets": widgets,
                "lab": lab,
                "rgb": rgb,
                "hex": hex_color,
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



    def _clear_color_evaluation_analysis(self, vars_dict):
        """Reset the analysis panel."""
        vars_dict["primary_name_var"].set("None")

        vars_dict["secondary_name_var"].set("None")

        vars_dict["selected_result_var"].set("Select a prototype from the list.")
        vars_dict["selected_summary_var"].set("")

        vars_dict["primary_swatch"].itemconfig(vars_dict["primary_rect"], fill="#cccccc")
        vars_dict["secondary_swatch"].itemconfig(vars_dict["secondary_rect"], fill="#f0f0f0")



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


    def _clear_color_evaluation_comparison(self, vars_dict):
        """Clear the comparison color and return to single-color analysis."""
        vars_dict["comparison_mode"] = False
        vars_dict["secondary_label"] = None

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
        """Refresh the right-side analysis panel for single or comparison mode."""
        refs_map = vars_dict.get("color_row_refs", {})
        primary_label = vars_dict.get("primary_label")
        secondary_label = vars_dict.get("secondary_label")

        primary_refs = refs_map.get(primary_label)
        secondary_refs = refs_map.get(secondary_label)

        if not primary_refs:
            self._clear_color_evaluation_analysis(vars_dict)
            return

        p_lab = primary_refs["lab"]
        p_hex = primary_refs["hex"]

        vars_dict["primary_name_var"].set(primary_label)
        vars_dict["primary_swatch"].itemconfig(vars_dict["primary_rect"], fill=p_hex)

        if not secondary_refs:
            vars_dict["secondary_name_var"].set("None")
            vars_dict["secondary_swatch"].itemconfig(vars_dict["secondary_rect"], fill="#f0f0f0")

            vars_dict["selected_result_var"].set("Single color selected. Comparison not active.")
            vars_dict["selected_summary_var"].set(
                "Use 'Compare with another color' to evaluate the selected color against a second prototype.\n"
                + self._get_color_evaluation_threshold_description()
            )
            return

        s_lab = secondary_refs["lab"]
        s_hex = secondary_refs["hex"]

        vars_dict["secondary_name_var"].set(secondary_label)
        vars_dict["secondary_swatch"].itemconfig(vars_dict["secondary_rect"], fill=s_hex)

        evaluation = self.evaluate_color_difference_threshold(
            sample_lab=p_lab,
            prototype_lab=s_lab,
            metric=self.threshold_settings.get("metric", "CIEDE2000"),
            threshold_settings=self.threshold_settings
        )

        vars_dict["selected_result_var"].set(
            evaluation.get("evaluation", "No evaluation available")
        )
        vars_dict["selected_summary_var"].set(
            evaluation.get("summary", "")
        )











    def _open_custom_color_input_dialog(self, vars_dict):
        """Open a dialog to input a custom color in RGB, LAB, or HEX."""
        data_source = vars_dict.get("loaded_space_data") or {}
        if not self._extract_color_space_rows(data_source):
            self.custom_warning(
                "No Color Space Loaded",
                "Load a valid color space before evaluating a custom color."
            )
            return

        parent = getattr(self, "_color_evaluation_window", self.root)

        dialog = tk.Toplevel(parent)
        dialog.title("Evaluate Custom Color")
        dialog.geometry("420x240")
        dialog.resizable(False, False)
        dialog.configure(bg="#f2f2f2")
        dialog.transient(parent)
        dialog.grab_set()

        input_vars = {
            "mode_var": tk.StringVar(value="RGB"),
            "v1_var": tk.StringVar(value=""),
            "v2_var": tk.StringVar(value=""),
            "v3_var": tk.StringVar(value=""),
            "hex_var": tk.StringVar(value=""),
            "status_var": tk.StringVar(value="Enter a color value."),
        }

        main = tk.Frame(dialog, bg="#f2f2f2")
        main.pack(fill="both", expand=True, padx=12, pady=12)

        panel = tk.Frame(main, bg="white", bd=1, relief="solid")
        panel.pack(fill="both", expand=True)

        tk.Label(
            panel,
            text="Custom Color Input",
            font=("Sans", 11, "bold"),
            bg="white",
            anchor="w",
            padx=12,
            pady=10
        ).pack(fill="x")

        body = tk.Frame(panel, bg="white")
        body.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        tk.Label(body, text="Input mode", bg="white").grid(row=0, column=0, sticky="w", pady=(0, 8))

        mode_combo = ttk.Combobox(
            body,
            textvariable=input_vars["mode_var"],
            state="readonly",
            width=12,
            values=["RGB", "LAB", "HEX"]
        )
        mode_combo.grid(row=0, column=1, sticky="w", pady=(0, 8))

        lbl1 = tk.Label(body, text="R:", bg="white")
        lbl1.grid(row=1, column=0, sticky="w", pady=4)
        entry1 = tk.Entry(body, textvariable=input_vars["v1_var"], width=12)
        entry1.grid(row=1, column=1, sticky="w", pady=4)

        lbl2 = tk.Label(body, text="G:", bg="white")
        lbl2.grid(row=2, column=0, sticky="w", pady=4)
        entry2 = tk.Entry(body, textvariable=input_vars["v2_var"], width=12)
        entry2.grid(row=2, column=1, sticky="w", pady=4)

        lbl3 = tk.Label(body, text="B:", bg="white")
        lbl3.grid(row=3, column=0, sticky="w", pady=4)
        entry3 = tk.Entry(body, textvariable=input_vars["v3_var"], width=12)
        entry3.grid(row=3, column=1, sticky="w", pady=4)

        hex_label = tk.Label(body, text="HEX:", bg="white")
        hex_entry = tk.Entry(body, textvariable=input_vars["hex_var"], width=16)

        def refresh_inputs(*_):
            mode = input_vars["mode_var"].get().strip().upper()

            lbl1.grid_remove()
            entry1.grid_remove()
            lbl2.grid_remove()
            entry2.grid_remove()
            lbl3.grid_remove()
            entry3.grid_remove()
            hex_label.grid_remove()
            hex_entry.grid_remove()

            if mode == "RGB":
                lbl1.config(text="R:")
                lbl2.config(text="G:")
                lbl3.config(text="B:")
                lbl1.grid(row=1, column=0, sticky="w", pady=4)
                entry1.grid(row=1, column=1, sticky="w", pady=4)
                lbl2.grid(row=2, column=0, sticky="w", pady=4)
                entry2.grid(row=2, column=1, sticky="w", pady=4)
                lbl3.grid(row=3, column=0, sticky="w", pady=4)
                entry3.grid(row=3, column=1, sticky="w", pady=4)

            elif mode == "LAB":
                lbl1.config(text="L:")
                lbl2.config(text="a:")
                lbl3.config(text="b:")
                lbl1.grid(row=1, column=0, sticky="w", pady=4)
                entry1.grid(row=1, column=1, sticky="w", pady=4)
                lbl2.grid(row=2, column=0, sticky="w", pady=4)
                entry2.grid(row=2, column=1, sticky="w", pady=4)
                lbl3.grid(row=3, column=0, sticky="w", pady=4)
                entry3.grid(row=3, column=1, sticky="w", pady=4)

            else:
                hex_label.grid(row=1, column=0, sticky="w", pady=4)
                hex_entry.grid(row=1, column=1, sticky="w", pady=4)

        mode_combo.bind("<<ComboboxSelected>>", refresh_inputs)
        refresh_inputs()

        tk.Label(
            body,
            textvariable=input_vars["status_var"],
            bg="white",
            fg="#666666",
            anchor="w",
            justify="left",
            wraplength=340,
            font=("Sans", 9, "italic")
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))

        buttons = tk.Frame(panel, bg="white")
        buttons.pack(fill="x", padx=12, pady=(0, 10))

        tk.Button(
            buttons,
            text="Cancel",
            width=12,
            command=dialog.destroy
        ).pack(side="right")

        tk.Button(
            buttons,
            text="Evaluate",
            width=12,
            command=lambda: self._submit_custom_color_input(vars_dict, input_vars, dialog)
        ).pack(side="right", padx=(0, 6))



    def _submit_custom_color_input(self, vars_dict, input_vars, dialog):
        """Validate the custom color input and open the result window."""
        try:
            sample_lab, sample_rgb, sample_hex = self._normalize_custom_color_input(
                input_mode=input_vars["mode_var"].get(),
                value_1=input_vars["v1_var"].get(),
                value_2=input_vars["v2_var"].get(),
                value_3=input_vars["v3_var"].get(),
                hex_value=input_vars["hex_var"].get()
            )
        except ValueError as exc:
            input_vars["status_var"].set(str(exc))
            return

        dialog.destroy()

        base_data = self._get_custom_color_base_data(
            vars_dict=vars_dict,
            sample_lab=sample_lab,
            sample_rgb=sample_rgb,
            sample_hex=sample_hex
        )

        self._open_custom_color_result_window(vars_dict, base_data)



    def _normalize_custom_color_input(self, input_mode, value_1="", value_2="", value_3="", hex_value=""):
        """
        Normalize a user-entered color into LAB, RGB, and HEX.

        Parameters
        ----------
        input_mode : str
            One of: RGB, LAB, HEX
        value_1, value_2, value_3 : str
            Numeric channel values for RGB or LAB.
        hex_value : str
            Hexadecimal color string for HEX mode.

        Returns
        -------
        tuple
            (sample_lab, sample_rgb, sample_hex)

        Raises
        ------
        ValueError
            If the input is invalid.
        """
        mode = str(input_mode).strip().upper()

        if mode == "RGB":
            try:
                r = int(str(value_1).strip())
                g = int(str(value_2).strip())
                b = int(str(value_3).strip())
            except Exception:
                raise ValueError("RGB values must be valid integers.")

            if not (0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255):
                raise ValueError("RGB values must be between 0 and 255.")

            sample_rgb = (r, g, b)
            sample_lab = UtilsTools.srgb_to_lab(r, g, b)
            sample_hex = UtilsTools.rgb_to_hex(sample_rgb)

            return sample_lab, sample_rgb, sample_hex

        elif mode == "LAB":
            try:
                L = float(str(value_1).strip())
                a = float(str(value_2).strip())
                b = float(str(value_3).strip())
            except Exception:
                raise ValueError("LAB values must be valid numbers.")

            sample_lab = (L, a, b)
            sample_rgb = UtilsTools.lab_to_rgb(sample_lab)
            sample_hex = UtilsTools.rgb_to_hex(sample_rgb)

            return sample_lab, sample_rgb, sample_hex

        elif mode == "HEX":
            hex_text = str(hex_value).strip().upper()

            if hex_text.startswith("#"):
                hex_text = hex_text[1:]

            if len(hex_text) != 6:
                raise ValueError("HEX value must contain exactly 6 hexadecimal characters.")

            try:
                r = int(hex_text[0:2], 16)
                g = int(hex_text[2:4], 16)
                b = int(hex_text[4:6], 16)
            except Exception:
                raise ValueError("HEX value is not valid.")

            sample_rgb = (r, g, b)
            sample_lab = UtilsTools.srgb_to_lab(r, g, b)
            sample_hex = UtilsTools.rgb_to_hex(sample_rgb)

            return sample_lab, sample_rgb, sample_hex

        raise ValueError("Unsupported input mode.")



    def _get_custom_color_base_data(self, vars_dict, sample_lab, sample_rgb, sample_hex):
        """Build the base data dictionary for a custom user-entered color."""
        top_memberships = self._calculate_evaluation_memberships(vars_dict, sample_lab)

        if top_memberships:
            winner_label = top_memberships[0][0]
            winner_mu = float(top_memberships[0][1])
        else:
            winner_label = "None"
            winner_mu = 0.0

        return {
            "info": None,
            "lab": sample_lab,
            "selection_info": None,
            "is_average": False,
            "sampled_rgb": sample_rgb,
            "sampled_hex": sample_hex,
            "sampled_title": "Custom Color",
            "memberships": top_memberships,
            "winner_label": winner_label,
            "winner_mu": winner_mu,
            "coord_text": "Custom color input",
            "roi_text": None,
        }


    def _open_custom_color_result_window(self, vars_dict, base_data):
        """Open a result window for a manually entered custom color."""
        parent = getattr(self, "_color_evaluation_window", self.root)

        win = tk.Toplevel(parent)
        win.title("Custom Color Evaluation")

        WIN_W, WIN_H = 980, 650
        win.geometry(f"{WIN_W}x{WIN_H}")
        win.resizable(False, False)
        win.configure(bg="#f2f2f2")
        win.transient(parent)
        win.grab_set()
        win.focus_set()

        result_vars = self._create_more_info_vars(base_data)

        main = tk.Frame(win, bg="#f2f2f2")
        main.pack(fill="both", expand=True, padx=10, pady=10)

        self._build_more_info_header(main, base_data)

        content_refs = self._build_more_info_content(main, base_data, result_vars)

        self._populate_more_info_memberships(
            base_data=base_data,
            vars_dict=result_vars,
            refs=content_refs
        )

        btns = tk.Frame(main, bg="#f2f2f2")
        btns.pack(fill="x", pady=(10, 0))

        tk.Button(
            btns,
            text="Use another color",
            width=16,
            command=lambda: (win.destroy(), self._open_custom_color_input_dialog(vars_dict))
        ).pack(side="right", padx=(6, 0))

        tk.Button(
            btns,
            text="Close",
            width=12,
            command=win.destroy
        ).pack(side="right")





















def start_up():
    root = tk.Tk()
    app = PyFCSApp(root)
    root.mainloop()

if __name__ == '__main__':
    start_up()

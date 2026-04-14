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
        self.cm_cache = {}
        self.proto_percentage_cache = {}
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
        def load_toolbar_icon(filename, size=None):
            """
            Load an icon once and keep a persistent reference.
            Optionally resize it to keep the toolbar compact.
            """
            icon_path = os.path.join(BASE_PATH, "Source", "external", "icons", filename)
            img = Image.open(icon_path)

            if size is not None:
                img = img.resize(size, Image.LANCZOS)

            tk_img = ImageTk.PhotoImage(img)
            self.ui_icons[filename] = tk_img
            return tk_img

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
        load_image_icon = load_toolbar_icon("LoadImage.png", icon_size)
        save_image_icon = load_toolbar_icon("SaveImage.png", icon_size)
        new_fcs_icon = load_toolbar_icon("NewFCS1.png", icon_size)
        load_fcs_icon = load_toolbar_icon("LoadFCS.png", icon_size)
        at_icon = load_toolbar_icon("AT.png", icon_size)
        pt_icon = load_toolbar_icon("PT.png", icon_size)

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
            text="Color Evaluation",
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



    def load_color_space(self):
        """
        Load a fuzzy color space file and update the application state.
        """
        if self._has_any_active_job():
            self.custom_warning(
                "Process Running",
                "There is a process currently running. Please wait for it to finish or cancel it before loading a Color Space."
            )
            return

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

            self.cm_cache.clear()
            self.proto_percentage_cache.clear()

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
        Once confirmed, save the color space and close the creation popup.
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
            self._close_creation_windows()
            self.save_cs(name, selected_colors_lab)

        ok_button = tk.Button(popup, text="OK", command=on_ok)
        ok_button.pack(pady=8)

        popup.bind("<Return>", lambda event: on_ok())
        popup.bind("<Escape>", lambda event: popup.destroy())



    def _on_color_space_saved_success(self, name):
        messagebox.showinfo(
            "Color Space Created",
            f"Color Space '{name}' created successfully."
        )
        self._close_creation_windows()


    def _save_color_space_file(self, name, color_dict):
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
                input_class.write_file(name, color_dict, progress_callback=update_progress)
                self.root.after(0, lambda: self._on_color_space_saved_success(name))
            except Exception as e:
                error_msg = f"An error occurred while saving: {e}"
                self.root.after(0, lambda msg=error_msg: self.custom_warning("Error", msg))
            finally:
                self.root.after(0, self.hide_loading)

        threading.Thread(target=run_save_process, daemon=True).start()


    def save_cs(self, name, selected_colors_lab):
        self._save_color_space_file(name, selected_colors_lab)


    def save_fcs(self, name, colors, color_dict=None):
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

        self._save_color_space_file(name, color_dict)

    

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
        """Applies the pending changes made to the editable color list."""
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
            self.color_data = copy.deepcopy(self.edit_color_data)

            color_dict = {
                key: value["positive_prototype"]
                for key, value in self.color_data.items()
            }

            output_name = self.file_name_entry.get().strip()
            if not output_name:
                self.custom_warning("Error", "Please enter a valid file name.")
                return

            # Save always as .fcs the new one
            self.save_fcs(output_name, self.color_data, color_dict)

            # Update new path
            self.file_path = os.path.join(
                UtilsTools.get_base_path(),
                "fuzzy_color_spaces",
                f"{output_name}.fcs"
            )

            self.update_volumes()

        except Exception as e:
            self.custom_warning("Error", f"Changes could not be saved: {e}")


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
        Closes all floating windows and cleans up associated resources.
        """
        if hasattr(self, "floating_images"):
            for window_id in list(self.floating_images.keys()):
                # Delete rectangle o pixel info
                try:
                    self._disable_original_rectangle_sampling(window_id)
                except Exception:
                    pass
        
                # Close each window
                self.image_canvas.delete(window_id)
                del self.floating_images[window_id]

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

                if hasattr(self, "load_images_names") and window_id in self.load_images_names:
                    del self.load_images_names[window_id]

        # Reset dict
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

        # Generate unique ID
        while True:
            window_id = f"floating_{random.randint(1000, 9999)}"
            if window_id not in self.load_images_names:
                break

        self.load_images_names[window_id] = filename

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

        # Window paddings (must stay consistent with other methods)
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
        # Background
        self.image_canvas.create_rectangle(
            x, y, x + new_width + PAD_X, y + new_height + PAD_Y,
            outline="black", fill="white", width=2,
            tags=(window_id, "floating", f"{window_id}_bg")
        )

        # Title bar
        self.image_canvas.create_rectangle(
            x, y, x + new_width + PAD_X, y + TITLE_H,
            outline="black", fill="gray",
            tags=(window_id, "floating", f"{window_id}_title")
        )

        # Title text
        self.image_canvas.create_text(
            x + 50, y + 15, anchor="w",
            text=os.path.basename(filename),
            fill="white", font=("Sans", 10),
            tags=(window_id, "floating", f"{window_id}_title_text")
        )

        # Close button
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

        # Arrow button
        self.image_canvas.create_text(
            x + 15, y + 15, text="▼",
            fill="white", font=("Sans", 12),
            tags=(window_id, "floating", f"{window_id}_arrow_button", f"{window_id}_arrow_text")
        )

        # Image item (anchor="nw" avoids coordinate offsets)
        self.image_canvas.create_image(
            x + IMG_LEFT_PAD, y + IMG_TOP_PAD,
            anchor="nw",
            image=self.floating_images[window_id],
            tags=(window_id, "floating", f"{window_id}_click_image", f"{window_id}_img_item")
        )

        # Percentage text below the image (hidden by default)
        self.image_canvas.create_text(
            x + IMG_LEFT_PAD,
            y + IMG_TOP_PAD + new_height + 10,
            anchor="nw",
            text="",
            fill="black",
            font=("Sans", 10),
            tags=(window_id, "floating", f"{window_id}_pct_text")
        )

        # Resize handle (bottom-right)
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
            """Update all canvas item positions based on the stored floating window state."""
            st = self.floating_window_state[window_id]
            wx, wy, ww, wh = st["x"], st["y"], st["w"], st["h"]

            # Background and title bar
            self.image_canvas.coords(f"{window_id}_bg", wx, wy, wx + ww + PAD_X, wy + wh + PAD_Y)
            self.image_canvas.coords(f"{window_id}_title", wx, wy, wx + ww + PAD_X, wy + TITLE_H)

            # Title text and arrow
            self.image_canvas.coords(f"{window_id}_title_text", wx + 50, wy + 15)
            self.image_canvas.coords(f"{window_id}_arrow_text", wx + 15, wy + 15)

            # Close button
            self.image_canvas.coords(
                f"{window_id}_close_rect",
                wx + ww + PAD_X - 5, wy + 5,
                wx + ww + PAD_X - 25, wy + 25
            )
            self.image_canvas.coords(f"{window_id}_close_text", wx + ww + PAD_X - 15, wy + 15)

            # Image top-left (anchor nw)
            self.image_canvas.coords(
                f"{window_id}_img_item",
                wx + IMG_LEFT_PAD, wy + IMG_TOP_PAD
            )

            # Resize handle
            hx1 = wx + ww + PAD_X - HANDLE_SIZE - 2
            hy1 = wy + wh + PAD_Y - HANDLE_SIZE - 2
            hx2 = wx + ww + PAD_X - 2
            hy2 = wy + wh + PAD_Y - 2
            self.image_canvas.coords(f"{window_id}_resize_handle", hx1, hy1, hx2, hy2)

            # Reposition proto_options frame if it exists
            self._reposition_proto_options(window_id)

            # Percentage text below the image
            self.image_canvas.coords(
                f"{window_id}_pct_text",
                wx + IMG_LEFT_PAD,
                wy + IMG_TOP_PAD + wh + 10
            )

            # Reposition loading panel if it exists
            self._reposition_window_loading(window_id)

            # Keep original-image rectangle sampling geometry in sync after moves/resizes
            if hasattr(self, "_original_sampling_state") and window_id in self._original_sampling_state:
                state = self._original_sampling_state[window_id]
                state["img_x"] = wx + IMG_LEFT_PAD
                state["img_y"] = wy + IMG_TOP_PAD
                state["draw_w"] = ww
                state["draw_h"] = wh

            # Keep this floating window visually focused
            self._focus_floating_window(window_id)

        def _update_image_to_size(window_id, target_w, target_h):
            """
            Resize the displayed image so it fits within target_w/target_h while keeping aspect ratio.
            Also refresh layout and, if original rectangle sampling is active, keep it synchronized.
            """
            pil_original = self.pil_images_original[window_id]
            ow, oh = pil_original.size

            # Keep aspect ratio (fit)
            scale = min(target_w / ow, target_h / oh)
            new_w = max(30, int(ow * scale))  # Avoid collapsing
            new_h = max(30, int(oh * scale))

            pil_resized = pil_original.resize((new_w, new_h), Image.Resampling.LANCZOS)
            self.images[window_id] = pil_resized
            self.image_dimensions[window_id] = (new_w, new_h)

            img_tk = ImageTk.PhotoImage(pil_resized)
            self.floating_images[window_id] = img_tk

            # Update displayed PIL image after resizing
            self.display_pil[window_id] = pil_resized

            # Update canvas image item
            self.image_canvas.itemconfig(f"{window_id}_img_item", image=self.floating_images[window_id])

            # Update state size and relayout
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
            # Cancel any running process linked to this image
            self._cancel_window_job(window_id)

            # Make sure rectangle sampling state is cleaned up
            try:
                self._disable_original_rectangle_sampling(window_id)
            except Exception:
                pass

            self.image_canvas.delete(window_id)

            if window_id in self.floating_images:
                del self.floating_images[window_id]
            if hasattr(self, "pil_images_original") and window_id in self.pil_images_original:
                del self.pil_images_original[window_id]
            if hasattr(self, "floating_window_state") and window_id in self.floating_window_state:
                del self.floating_window_state[window_id]
            if hasattr(self, "images") and window_id in self.images:
                del self.images[window_id]
            if hasattr(self, "display_pil") and window_id in self.display_pil:
                del self.display_pil[window_id]
            if hasattr(self, "original_images") and window_id in self.original_images:
                del self.original_images[window_id]
            if hasattr(self, "image_dimensions") and window_id in self.image_dimensions:
                del self.image_dimensions[window_id]
            if hasattr(self, "original_image_dimensions") and window_id in self.original_image_dimensions:
                del self.original_image_dimensions[window_id]
            if hasattr(self, "proto_percentage_cache") and window_id in self.proto_percentage_cache:
                del self.proto_percentage_cache[window_id]
            if hasattr(self, "cm_cache") and window_id in self.cm_cache:
                del self.cm_cache[window_id]
            if hasattr(self, "_resize_callbacks") and window_id in self._resize_callbacks:
                del self._resize_callbacks[window_id]
            if hasattr(self, "_pixel_click_callbacks") and window_id in self._pixel_click_callbacks:
                del self._pixel_click_callbacks[window_id]
            if hasattr(self, "current_protos") and window_id in self.current_protos:
                del self.current_protos[window_id]

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

            if hasattr(self, "load_images_names") and window_id in self.load_images_names:
                del self.load_images_names[window_id]

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
        # Move window (title bar only)
        # ---------------------------
        def start_move(event):
            """Store the initial mouse position when pressing on the title bar."""
            if self._has_active_job(window_id):
                return "break"
            
            self._focus_floating_window(window_id)

            try:
                self._clear_original_selection_rectangle(window_id)
            except Exception:
                pass

            self.last_x, self.last_y = event.x, event.y

        def move_window(event):
            """Move the floating window while dragging from the title bar."""
            if self._has_active_job(window_id):
                return "break"
            
            self._focus_floating_window(window_id)

            dx, dy = event.x - self.last_x, event.y - self.last_y

            # Update stored position
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
            """Store initial state for resizing using the bottom-right handle."""
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
            """Resize the floating window while dragging the bottom-right handle."""
            if self._has_active_job(window_id):
                return "break"

            if not hasattr(self, "_resize_start") or self._resize_start is None:
                return "break"

            mx = self.image_canvas.canvasx(event.x)
            my = self.image_canvas.canvasy(event.y)

            start = self._resize_start
            dw = mx - start["mx"]
            dh = my - start["my"]

            # Desired image-area size before aspect correction
            desired_w = max(30, int(start["w"] + dw))
            desired_h = max(30, int(start["h"] + dh))

            _update_image_to_size(window_id, desired_w, desired_h)
            return "break"

        def end_resize(event):
            """Finish resizing, clear related caches, and remove stale percentage text."""
            if self._has_active_job(window_id):
                return "break"

            # Cancel any running process because the displayed image size has changed
            self._cancel_window_job(window_id)

            self._resize_start = None

            try:
                self._clear_original_selection_rectangle(window_id)
            except Exception:
                pass

            # Clear cached results for this window when resizing ends
            try:
                if hasattr(self, "proto_percentage_cache") and window_id in self.proto_percentage_cache:
                    self.proto_percentage_cache[window_id].clear()
                if hasattr(self, "cm_cache") and window_id in self.cm_cache:
                    self.cm_cache[window_id].clear()
            except Exception:
                pass

            # Clear coverage text because it may be outdated after resizing
            try:
                self.image_canvas.itemconfig(f"{window_id}_pct_text", text="")
            except Exception:
                pass

            return "break"

        # Store resize callbacks so they can be rebound later
        if not hasattr(self, "_resize_callbacks"):
            self._resize_callbacks = {}
        self._resize_callbacks[window_id] = (start_resize, do_resize, end_resize)

        # ---------------------------
        # Pixel picking (single click)
        # ---------------------------
        def get_pixel_value(event, window_id=window_id):
            """Get the LAB value of the clicked pixel, accounting for window movement and resizing."""
            if self._has_active_job(window_id):
                return "break"

            pil_original = self.pil_images_original[window_id]
            ow, oh = pil_original.size

            resized_w, resized_h = self.image_dimensions[window_id]
            if resized_w <= 0 or resized_h <= 0:
                return "break"

            abs_x = self.image_canvas.canvasx(event.x)
            abs_y = self.image_canvas.canvasy(event.y)

            # Top-left corner of the displayed image (anchor="nw")
            st = self.floating_window_state[window_id]
            img_left = st["x"] + IMG_LEFT_PAD
            img_top = st["y"] + IMG_TOP_PAD

            relative_x = abs_x - img_left
            relative_y = abs_y - img_top

            # Ignore clicks outside the displayed image area
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

        # Store the normal click callback so it can be restored after disabling
        # original-image rectangle sampling
        if not hasattr(self, "_pixel_click_callbacks"):
            self._pixel_click_callbacks = {}
        self._pixel_click_callbacks[window_id] = get_pixel_value

        # ---------------------------
        # Bindings
        # ---------------------------
        # Move only from title bar
        self.image_canvas.tag_bind(f"{window_id}_title", "<Button-1>", start_move)
        self.image_canvas.tag_bind(f"{window_id}_title", "<B1-Motion>", move_window)
        self.image_canvas.tag_bind(f"{window_id}_title_text", "<Button-1>", start_move)
        self.image_canvas.tag_bind(f"{window_id}_title_text", "<B1-Motion>", move_window)

        # Close, menu, click
        self.image_canvas.tag_bind(f"{window_id}_close_button", "<Button-1>", close_window)
        self.image_canvas.tag_bind(f"{window_id}_click_image", "<Button-1>", get_pixel_value)
        self.image_canvas.tag_bind(f"{window_id}_arrow_button", "<Button-1>", show_menu_image)

        # Resize handle bindings
        self.image_canvas.tag_bind(f"{window_id}_resize_handle", "<Button-1>", start_resize)
        self.image_canvas.tag_bind(f"{window_id}_resize_handle", "<B1-Motion>", do_resize)
        self.image_canvas.tag_bind(f"{window_id}_resize_handle", "<ButtonRelease-1>", end_resize)

        # Initial relayout to ensure everything stays consistent
        _relayout(window_id)

        # Enable rectangle sampling from the start because a newly opened floating
        # window is already showing the original image
        try:
            self._enable_original_rectangle_sampling(
                window_id=window_id,
                target_w=new_width,
                target_h=new_height
            )
        except Exception as e:
            print(f"Warning enabling original rectangle sampling for {window_id}: {e}")

        # Focus the newly created window
        self._focus_floating_window(window_id)



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


    def addColor_to_image(self, window, colors, update_ui_callback):
        """
        Opens a popup window to add a new color by entering LAB values or selecting a color from a color wheel.
        Returns the color name and LAB values if the user confirms the input.
        """
        self.image_manager.addColor_to_image(window, colors, update_ui_callback)


























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

        This makes the image being moved appear above proto_options panels.
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

            # Also keep loading panels behind the active floating window
            try:
                self.image_canvas.tag_lower("loading")
            except Exception:
                pass

            # Raise the whole floating window group
            try:
                self.image_canvas.tag_raise(window_id)
            except Exception:
                pass

            # Raise specific items explicitly to guarantee order
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

            # Keep this window loading panel above its own image if it exists
            try:
                self.image_canvas.tag_raise(f"{window_id}_loading")
            except Exception:
                pass

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
        if getattr(self, "mapping_locked_until_original", {}).get(window_id, False):
            self.custom_warning(
                "Restore Original Image",
                "This image belongs to a previous Color Space. Press Original before selecting a prototype."
            )
            return

        if not hasattr(self, "current_protos") or window_id not in self.current_protos:
            self.custom_warning("Error", "No prototype selected for this window.")
            return

        selected_proto = self.current_protos[window_id].get()
        pos = self.color_matrix.index(selected_proto)

        def run_process(cancel_event, job_id):
            try:
                if self._is_job_cancelled(window_id, cancel_event, job_id):
                    return

                if not hasattr(self, "proto_percentage_cache"):
                    self.proto_percentage_cache = {}
                if window_id not in self.proto_percentage_cache:
                    self.proto_percentage_cache[window_id] = {}

                if not hasattr(self, "images") or window_id not in self.images:
                    self.image_canvas.after(
                        0,
                        lambda: self.custom_warning("Error", "Current image not found for this window.")
                    )
                    return

                source_img = self.images[window_id]
                w, h = source_img.size
                cache_key = (pos, w, h)

                cached_entry = self.proto_percentage_cache[window_id].get(cache_key)
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

                    self.proto_percentage_cache[window_id][cache_key] = {
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
        Improved / faster version of the Tkinter "Color Mapping All" operation.

        Key optimizations:
        1) Compute the winner label_map by processing only UNIQUE quantized LAB values.
        2) Avoid building a full dict(label -> membership) for every pixel.
        3) Recolor the image in O(H*W) using the cached label_map.

        Safety behavior:
        - If a pixel does not match any prototype (best_idx == -1), it is rendered in black.
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

        self.window_mapping_mode[window_id] = "all"

        # Disable original-image rectangle sampling because the view is no longer the original image
        try:
            self._disable_original_rectangle_sampling(window_id)
        except Exception:
            pass

        # Disable resizing while mapping is active
        try:
            self.image_canvas.delete(f"{window_id}_resize_handle")
            self.image_canvas.tag_unbind(f"{window_id}_resize_handle", "<Button-1>")
            self.image_canvas.tag_unbind(f"{window_id}_resize_handle", "<B1-Motion>")
            self.image_canvas.tag_unbind(f"{window_id}_resize_handle", "<ButtonRelease-1>")
        except Exception:
            pass

        # Hide per-prototype percentage text for the "all" mapping
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

        # -----------------------------
        # UI-safe progress update helper
        # -----------------------------
        def update_progress(job_id, current_step, total_steps):
            """Thread-safe progress update helper."""
            if total_steps <= 0:
                return
            self._update_window_progress(window_id, job_id, current_step, total_steps)

        # ----------------------------------------
        # Build legend frame
        # ----------------------------------------
        def build_legend_frame(prototypes, parent_canvas, palette_uint8):
            """
            Creates and returns the legend frame.

            palette_uint8: (N,3) uint8, where palette_uint8[i] is the display color
            assigned to prototypes[i].
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
                """Keep the inner frame width synchronized with the outer canvas width."""
                canvas.itemconfig("inner", width=event.width)

            canvas.bind("<Configure>", resize_inner)

            def on_frame_configure(_event=None):
                """Update scroll region after legend content changes."""
                canvas.configure(scrollregion=canvas.bbox("all"))

            inner_frame.bind("<Configure>", lambda e: canvas.after_idle(on_frame_configure))

            # Mouse wheel scrolling
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

            # One legend row per prototype
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

        # -----------------------------
        # Palette builders
        # -----------------------------
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

        # -------------------------------------------------------
        # Fast recolor: use label_map directly without recomputing memberships
        # -------------------------------------------------------
        def recolor(window_id):
            """Switch palette without recomputing memberships."""
            if getattr(self, "mapping_locked_until_original", {}).get(window_id, False):
                self.custom_warning(
                    "Old Color Space",
                    "This Color Mapping All result belongs to a previous Color Space. Press Original to use the new one."
                )
                return

            if not self._window_exists(window_id):
                return

            if not hasattr(self, "cm_cache") or window_id not in self.cm_cache:
                return

            cache_pack = self.cm_cache[window_id].get("last_pack")
            if not cache_pack:
                return

            label_map = cache_pack["label_map"]
            palettes = cache_pack["palettes"]
            current = cache_pack["scheme"]
            new = "alt" if current == "original" else "original"
            cache_pack["scheme"] = new

            palette = palettes[new]

            # Render black where no valid prototype exists
            recolored_image = np.zeros((label_map.shape[0], label_map.shape[1], 3), dtype=np.uint8)
            valid_mask = (label_map >= 0)
            if np.any(valid_mask):
                recolored_image[valid_mask] = palette[label_map[valid_mask].astype(np.int32)]

            # Replace current legend with a new one using the new palette
            new_legend_frame = cache_pack.get("legend_frame")
            if new_legend_frame:
                try:
                    if new_legend_frame.winfo_exists():
                        new_legend_frame.destroy()
                except Exception:
                    pass

            new_legend_frame = build_legend_frame(self.prototypes, self.image_canvas, palette)
            cache_pack["legend_frame"] = new_legend_frame

            self.image_canvas.after(0, lambda: update_ui(recolored_image, new_legend_frame))

        # -----------------------------
        # Main worker thread
        # -----------------------------
        def run_process(cancel_event, job_id):
            try:
                if self._is_job_cancelled(window_id, cancel_event, job_id):
                    return

                # Ensure the current resized image exists
                if not hasattr(self, "images") or window_id not in self.images:
                    self.image_canvas.after(0, lambda: self.custom_warning("Processing Error", "Current image not found for this window."))
                    return

                source_img = self.images[window_id]
                w, h = source_img.size

                # Ensure cache structure exists
                if not hasattr(self, "cm_cache"):
                    self.cm_cache = {}
                if window_id not in self.cm_cache:
                    self.cm_cache[window_id] = {}

                # Cache key depends on image size and prototype labels
                proto_labels = tuple([p.label for p in self.prototypes])
                cache_key = (w, h, proto_labels)

                # Reuse cached label_map if possible
                label_map = self.cm_cache[window_id].get(cache_key)

                # Ensure fuzzy color space fast structures exist
                self.fuzzy_color_space.precompute_pack()

                if self._is_job_cancelled(window_id, cancel_event, job_id):
                    return

                if label_map is None:
                    # Convert PIL -> RGB float -> LAB
                    img_np = np.array(source_img)
                    if img_np.ndim == 3 and img_np.shape[-1] == 4:
                        img_np = img_np[..., :3]

                    img01 = img_np.astype(np.float32) / 255.0
                    lab_img = color.rgb2lab(img01)

                    # Quantize LAB values to 0.01
                    lab_q = np.round(lab_img, 2)
                    height, width = lab_q.shape[0], lab_q.shape[1]

                    # Process unique LAB values only
                    lab_int = np.round(lab_q.reshape(-1, 3) * 100.0).astype(np.int32)
                    uniq, inv = np.unique(lab_int, axis=0, return_inverse=True)

                    # int32 is required because -1 means "no prototype found"
                    best_for_uniq = np.empty((uniq.shape[0],), dtype=np.int32)

                    total_uniqs = int(uniq.shape[0])
                    last_update = time.perf_counter()

                    for i in range(total_uniqs):
                        if self._is_job_cancelled(window_id, cancel_event, job_id):
                            return

                        L_i, A_i, B_i = uniq[i].astype(np.float32) / 100.0

                        # Fast argmax with no dict allocations
                        best_idx = self.fuzzy_color_space.best_prototype_index_from_lab((L_i, A_i, B_i))
                        best_for_uniq[i] = int(best_idx)

                        now = time.perf_counter()
                        if now - last_update > 0.03 or i == total_uniqs - 1:
                            update_progress(job_id, i + 1, total_uniqs)
                            last_update = now

                    # Reconstruct full label_map
                    label_map = best_for_uniq[inv].reshape(height, width).astype(np.int32)

                    # Cache it
                    self.cm_cache[window_id][cache_key] = label_map

                if self._is_job_cancelled(window_id, cancel_event, job_id):
                    return

                # Build palettes
                original_palette = build_original_palette_uint8()
                alt_palette = build_alt_palette_uint8()

                scheme = "original"
                palette = original_palette

                # Render black where label_map == -1
                recolored_image = np.zeros((label_map.shape[0], label_map.shape[1], 3), dtype=np.uint8)
                valid_mask = (label_map >= 0)
                if np.any(valid_mask):
                    recolored_image[valid_mask] = palette[label_map[valid_mask].astype(np.int32)]

                # Create legend frame
                new_legend_frame = build_legend_frame(self.prototypes, self.image_canvas, palette)

                # Store everything needed for instant recolor switching
                self.cm_cache[window_id]["last_pack"] = {
                    "label_map": label_map,
                    "palettes": {"original": original_palette, "alt": alt_palette},
                    "scheme": scheme,
                    "legend_frame": new_legend_frame,
                    "cache_key": cache_key,
                }

                def _ui():
                    """Apply processed result on the main thread."""
                    if not self._is_current_job(window_id, job_id):
                        return
                    if not self._window_exists(window_id):
                        return
                    update_ui(recolored_image, new_legend_frame)

                self.image_canvas.after(0, _ui)

            except RuntimeError as e:
                if str(e) != "__JOB_CANCELLED__":
                    self.image_canvas.after(0, lambda: self.custom_warning("Processing Error", f"Error in color mapping: {e}"))
            except Exception as e:
                self.image_canvas.after(0, lambda: self.custom_warning("Processing Error", f"Error in color mapping: {e}"))

        # -----------------------------
        # UI update
        # -----------------------------
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
            self.lab_value_frame = tk.Frame(self.Canvas1, bg="lightgray")
            self.lab_value_frame.place(relx=0.5, rely=0.97, anchor="s")

            # Left-aligned text container
            text_frame = tk.Frame(self.lab_value_frame, bg="lightgray")
            text_frame.pack(side="left", padx=10, pady=5, fill="x")

            bold_font = ("Sans", 12, "bold")
            normal_font = ("Sans", 12)

            coord_label = tk.Label(text_frame, text="Coordinates: ", font=bold_font, bg="lightgray")
            coord_label.pack(side="left")
            self.coord_value = tk.Label(text_frame, text="", font=normal_font, bg="lightgray")
            self.coord_value.pack(side="left")

            lab_label = tk.Label(text_frame, text="LAB: ", font=bold_font, bg="lightgray")
            lab_label.pack(side="left")
            self.lab_value_print = tk.Label(text_frame, text="", font=normal_font, bg="lightgray")
            self.lab_value_print.pack(side="left")

            proto_label = tk.Label(text_frame, text="Selected Prototype: ", font=bold_font, bg="lightgray")
            proto_label.pack(side="left")

            self.proto_value_text = tk.Label(text_frame, text="", font=normal_font, bg="lightgray", fg="black")
            self.proto_value_text.pack(side="left")

            more_info_button = tk.Button(
                self.lab_value_frame,
                text="🔍",
                font=("Sans", 9),
                bg="white",
                command=self.show_more_info_pixel,
                relief="flat",
                borderwidth=0
            )
            more_info_button.pack(side="right", padx=5, pady=2)

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

        self.coord_value.config(text=f"{coord_text}    |    ")
        self.lab_value_print.config(text=f"{pixel_lab[0]:.2f}, {pixel_lab[1]:.2f}, {pixel_lab[2]:.2f}    |    ")

        if max_proto is None:
            self.proto_value_text.config(text="—", fg="black")
        else:
            self.proto_value_text.config(text=f"{max_proto}", fg="black")




    def show_more_info_pixel(self):
        """Show detailed info for the last clicked pixel/ROI with clickable prototype preview."""
        info = getattr(self, "_last_pixel_info", None)
        if not info:
            messagebox.showinfo("More Info", "Click on an image pixel first.")
            return

        win = tk.Toplevel(self.root)
        win.title("More Info")

        WIN_W, WIN_H = 980, 640
        win.geometry(f"{WIN_W}x{WIN_H}")
        win.resizable(False, False)
        win.configure(bg="#f2f2f2")

        # ---------------------------
        # Helpers
        # ---------------------------
        def safe_hex_from_rgb(rgb, default="#cccccc"):
            try:
                r, g, b = rgb
                r = max(0, min(255, int(round(r))))
                g = max(0, min(255, int(round(g))))
                b = max(0, min(255, int(round(b))))
                return f"#{r:02x}{g:02x}{b:02x}"
            except Exception:
                return default

        def get_proto_lab(label):
            try:
                proto = self.color_data[label]["positive_prototype"]
                if isinstance(proto, np.ndarray):
                    proto = proto.tolist()
                return tuple(float(v) for v in proto)
            except Exception:
                return None

        def get_proto_rgb(label):
            try:
                proto_lab = get_proto_lab(label)
                if proto_lab is None:
                    return (200, 200, 200)
                return UtilsTools.lab_to_rgb(proto_lab)
            except Exception:
                return (200, 200, 200)

        def get_proto_hex(label):
            return safe_hex_from_rgb(get_proto_rgb(label))

        # ---------------------------
        # Base data
        # ---------------------------
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

        sampled_hex = safe_hex_from_rgb(sampled_rgb)
        sampled_title = "Mean Color" if is_average else "Selected Color"

        memberships = info.get("all_memberships")
        if not memberships:
            memberships = info.get("top_memberships", [])

        winner_label = info.get("winner_label", "None")
        winner_mu = float(info.get("winner_mu", 0.0))

        selected_label_var = tk.StringVar(value=winner_label if winner_label != "None" else "")
        selected_rgb_var = tk.StringVar(value="")
        selected_hex_var = tk.StringVar(value="")
        selected_lab_var = tk.StringVar(value="")

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

        preset_display_map = {
            "pt": "Perceptibility Threshold",
            "at": "Acceptability Threshold",
            "pt_at": "Perceptibility + Acceptability"
        }
        preset_reverse_map = {v: k for k, v in preset_display_map.items()}

        saved_mode = self.threshold_settings.get("mode", "known")
        display_mode = "default" if saved_mode == "known" else saved_mode

        threshold_metric_var = tk.StringVar(value=self.threshold_settings.get("metric", "CIEDE2000"))
        threshold_mode_var = tk.StringVar(value=display_mode)
        threshold_preset_var = tk.StringVar(
            value=preset_display_map.get(
                self.threshold_settings.get("preset", "pt_at"),
                "Perceptibility + Acceptability"
            )
        )
        threshold_lower_var = tk.StringVar(value=str(self.threshold_settings.get("lower", 0.8)))
        threshold_upper_var = tk.StringVar(value=str(self.threshold_settings.get("upper", 1.8)))

        custom_type_display_map = {
            "single": "Single threshold",
            "lower_upper": "Lower and upper thresholds"
        }
        custom_type_reverse_map = {v: k for k, v in custom_type_display_map.items()}

        threshold_custom_type_var = tk.StringVar(
            value=custom_type_display_map.get(
                self.threshold_settings.get("custom_type", "single"),
                "Single threshold"
            )
        )
        threshold_single_var = tk.StringVar(value=str(self.threshold_settings.get("single", 1.0)))

        threshold_result_title_var = tk.StringVar(value="")
        threshold_result_detail_var = tk.StringVar(value="")
        threshold_result_summary_var = tk.StringVar(value="")
        threshold_info_var = tk.StringVar(value="")
        threshold_result_var = tk.StringVar(value="")
        membership_rows = {}

        # ---------------------------
        # Main container
        # ---------------------------
        main = tk.Frame(win, bg="#f2f2f2")
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # ---------------------------
        # Header
        # ---------------------------
        header = tk.Frame(main, bg="white", bd=1, relief="solid")
        header.pack(fill="x", pady=(0, 10))

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

        tk.Label(
            header,
            text=coord_text,
            anchor="w",
            bg="white",
            font=("Sans", 11, "bold"),
            padx=12,
            pady=6
        ).pack(fill="x")

        if roi_text:
            tk.Label(
                header,
                text=roi_text,
                anchor="w",
                bg="white",
                font=("Sans", 10),
                padx=12,
                pady=0
            ).pack(fill="x", pady=(0, 4))

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

        # ---------------------------
        # Content area
        # ---------------------------
        content = tk.Frame(main, bg="#f2f2f2")
        content.pack(fill="both", expand=True)

        top_content = tk.Frame(content, bg="#f2f2f2")
        top_content.pack(fill="x", anchor="n")

        left = tk.Frame(top_content, bg="white", bd=1, relief="solid", width=320, height=285)
        left.pack(side="left", fill="y", padx=(0, 6), anchor="n")
        left.pack_propagate(False)

        center = tk.Frame(top_content, bg="white", bd=1, relief="solid", height=285)
        center.pack(side="left", fill="x", expand=True, padx=(6, 0), anchor="n")
        center.pack_propagate(False)

        # ---------------------------
        # Left: memberships
        # ---------------------------
        tk.Label(
            left,
            text="Membership Degree (μ)",
            font=("Sans", 11, "bold"),
            anchor="w",
            bg="white",
            padx=12,
            pady=10
        ).pack(fill="x")

        tk.Label(
            left,
            text=f"Winner: {winner_label}    |    μ = {winner_mu:.4f}",
            anchor="w",
            bg="white",
            padx=12
        ).pack(fill="x", pady=(0, 10))

        tk.Label(
            left,
            text="Memberships:",
            font=("Sans", 10, "bold"),
            anchor="w",
            bg="white",
            padx=12
        ).pack(fill="x", pady=(0, 6))

        memberships_box = tk.Frame(left, bg="white", bd=1, relief="solid", height=140)
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

        # Info below memberships
        tip_container = tk.Frame(left, bg="white")
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

        # ---------------------------
        # Center: selected prototype + selected/mean color side by side
        # ---------------------------
        SWATCH_W = 100
        SWATCH_H = 75
        PAD_X = 10
        PAD_Y = 10

        canvas_w = SWATCH_W + 2 * PAD_X
        canvas_h = SWATCH_H + 2 * PAD_Y

        top_colors = tk.Frame(center, bg="white")
        top_colors.pack(fill="x", pady=(8, 6), padx=10)

        left_card = tk.Frame(top_colors, bg="white")
        left_card.pack(side="left", fill="both", expand=True, padx=(0, 8))

        right_card = tk.Frame(top_colors, bg="white")
        right_card.pack(side="left", fill="both", expand=True, padx=(8, 0))

        # Selected Prototype
        tk.Label(
            left_card,
            text="Selected Prototype",
            font=("Sans", 11, "bold"),
            bg="white"
        ).pack(fill="x")

        selected_name_label = tk.Label(
            left_card,
            textvariable=selected_label_var,
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

        selected_lab_label = tk.Label(
            left_card,
            textvariable=selected_lab_var,
            bg="white",
            font=("Sans", 10),
            justify="center",
            wraplength=240
        )
        selected_lab_label.pack()

        selected_rgb_label = tk.Label(
            left_card,
            textvariable=selected_rgb_var,
            bg="white",
            font=("Sans", 10)
        )
        selected_rgb_label.pack()

        selected_hex_label = tk.Label(
            left_card,
            textvariable=selected_hex_var,
            bg="white",
            font=("Sans", 10)
        )
        selected_hex_label.pack(pady=(2, 0))

        # Selected / Mean Color
        tk.Label(
            right_card,
            text=sampled_title,
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
            fill=sampled_hex,
            outline="#606060",
            width=1
        )

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
            text=f"HEX: {sampled_hex.upper()}",
            bg="white",
            font=("Sans", 10)
        ).pack(pady=(2, 0))

        # ---------------------------
        # Bottom independent block: Threshold
        # ---------------------------
        threshold_panel = tk.Frame(content, bg="white", bd=1, relief="solid")
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

        # 3 visual sections
        section_selection = tk.Frame(threshold_body, bg="white")
        section_selection.pack(side="left", fill="y", padx=(0, 12))

        sep_1 = tk.Frame(threshold_body, bg="#d8d8d8", width=1, height=120)
        sep_1.pack(side="left", fill="y", padx=(0, 12), pady=2)

        section_config = tk.Frame(threshold_body, bg="white")
        section_config.pack(side="left", fill="both", expand=True, padx=(0, 12))

        sep_2 = tk.Frame(threshold_body, bg="#d8d8d8", width=1, height=120)
        sep_2.pack(side="left", fill="y", padx=(0, 12), pady=2)

        section_result = tk.Frame(threshold_body, bg="white")
        section_result.pack(side="left", fill="both", expand=True)

        # ---------------------------
        # Section 1: Selection
        # ---------------------------
        tk.Label(
            section_selection,
            text="Metric",
            font=("Sans", 10, "bold"),
            anchor="w",
            bg="white"
        ).pack(anchor="w", pady=(0, 4))

        metric_combo = ttk.Combobox(
            section_selection,
            textvariable=threshold_metric_var,
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
            textvariable=threshold_mode_var,
            state="readonly",
            width=18,
            values=["default", "custom"]
        )
        mode_combo.pack(anchor="w")

        # ---------------------------
        # Section 2: Configuration
        # ---------------------------
        tk.Label(
            section_config,
            text="Configuration",
            font=("Sans", 10, "bold"),
            anchor="w",
            bg="white"
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        preset_label = tk.Label(
            section_config,
            text="Default preset:",
            bg="white",
            anchor="w"
        )

        preset_combo = ttk.Combobox(
            section_config,
            textvariable=threshold_preset_var,
            state="readonly",
            width=28,
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
            anchor="w"
        )

        custom_type_combo = ttk.Combobox(
            section_config,
            textvariable=threshold_custom_type_var,
            state="readonly",
            width=28,
            values=[
                "Single threshold",
                "Lower and upper thresholds"
            ]
        )

        single_label = tk.Label(
            section_config,
            text="Threshold:",
            bg="white",
            anchor="w"
        )
        single_entry = tk.Entry(
            section_config,
            textvariable=threshold_single_var,
            width=10
        )

        lower_label = tk.Label(
            section_config,
            text="Lower threshold:",
            bg="white",
            anchor="w"
        )
        lower_entry = tk.Entry(
            section_config,
            textvariable=threshold_lower_var,
            width=10
        )

        upper_label = tk.Label(
            section_config,
            text="Upper threshold:",
            bg="white",
            anchor="w"
        )
        upper_entry = tk.Entry(
            section_config,
            textvariable=threshold_upper_var,
            width=10
        )

        config_hint_var = tk.StringVar(value="")
        config_hint_label = tk.Label(
            section_config,
            textvariable=config_hint_var,
            bg="white",
            fg="#666666",
            anchor="w",
            justify="left",
            wraplength=260,
            font=("Sans", 9, "italic")
        )

        # ---------------------------
        # Section 3: Result
        # ---------------------------
        tk.Label(
            section_result,
            text="Results",
            font=("Sans", 10, "bold"),
            anchor="w",
            bg="white"
        ).pack(anchor="w", pady=(0, 8))

        threshold_result_title_label = tk.Label(
            section_result,
            textvariable=threshold_result_title_var,
            anchor="w",
            justify="left",
            bg="white",
            font=("Sans", 10, "bold"),
            wraplength=300
        )
        threshold_result_title_label.pack(anchor="w", fill="x", pady=(0, 6))

        threshold_result_detail_label = tk.Label(
            section_result,
            textvariable=threshold_result_detail_var,
            anchor="w",
            justify="left",
            bg="white",
            wraplength=300
        )
        threshold_result_detail_label.pack(anchor="w", fill="x", pady=(0, 6))

        threshold_result_summary_label = tk.Label(
            section_result,
            textvariable=threshold_result_summary_var,
            anchor="w",
            justify="left",
            bg="white",
            wraplength=300
        )
        threshold_result_summary_label.pack(anchor="w", fill="x")


        def refresh_threshold_section(proto_lab=None):
            """
            Refresh threshold controls visibility and result text.
            If proto_lab is provided, also evaluate the selected prototype.
            """
            mode_value = threshold_mode_var.get().strip().lower()
            internal_mode = "known" if mode_value == "default" else mode_value

            selected_preset_display = threshold_preset_var.get().strip()
            selected_preset_key = preset_reverse_map.get(selected_preset_display, "pt_at")

            selected_custom_type_display = threshold_custom_type_var.get().strip()
            selected_custom_type_key = custom_type_reverse_map.get(selected_custom_type_display, "single")

            single_text = threshold_single_var.get().strip()
            lower_text = threshold_lower_var.get().strip()
            upper_text = threshold_upper_var.get().strip()

            # Save UI state into self.threshold_settings
            self.threshold_settings["metric"] = threshold_metric_var.get().strip()
            self.threshold_settings["mode"] = internal_mode
            self.threshold_settings["preset"] = selected_preset_key
            self.threshold_settings["custom_type"] = selected_custom_type_key

            self.threshold_settings["single"] = single_text if single_text != "" else None
            self.threshold_settings["lower"] = lower_text if lower_text != "" else None
            self.threshold_settings["upper"] = upper_text if upper_text != "" else None

            # Reset config controls
            preset_label.grid_remove()
            preset_combo.grid_remove()
            custom_type_label.grid_remove()
            custom_type_combo.grid_remove()
            single_label.grid_remove()
            single_entry.grid_remove()
            lower_label.grid_remove()
            lower_entry.grid_remove()
            upper_label.grid_remove()
            upper_entry.grid_remove()
            config_hint_label.grid_remove()

            if mode_value == "default":
                preset_label.grid(row=1, column=0, sticky="w", pady=(0, 6))
                preset_combo.grid(row=1, column=1, sticky="w", pady=(0, 6))

                config_hint_var.set("Use predefined perceptibility and/or acceptability thresholds.")
                config_hint_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))

            elif mode_value == "custom":
                custom_type_label.grid(row=1, column=0, sticky="w", pady=(0, 6))
                custom_type_combo.grid(row=1, column=1, sticky="w", pady=(0, 6))

                if selected_custom_type_key == "single":
                    single_label.grid(row=2, column=0, sticky="w", pady=(0, 6))
                    single_entry.grid(row=2, column=1, sticky="w", pady=(0, 6))
                    config_hint_var.set("Define one threshold greater than 0.")

                    # Optional live validation message
                    if single_text == "":
                        config_hint_var.set("Enter a threshold greater than 0.")
                    else:
                        parsed_single, err_single = self._parse_positive_threshold(single_text)
                        if err_single:
                            config_hint_var.set(err_single)

                    config_hint_label.grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 0))

                else:  # lower_upper
                    lower_label.grid(row=2, column=0, sticky="w", pady=(0, 6))
                    lower_entry.grid(row=2, column=1, sticky="w", pady=(0, 6))
                    upper_label.grid(row=3, column=0, sticky="w", pady=(0, 6))
                    upper_entry.grid(row=3, column=1, sticky="w", pady=(0, 6))

                    config_hint_var.set("Define two thresholds greater than 0, with lower < upper.")

                    if lower_text == "" or upper_text == "":
                        config_hint_var.set("Enter both thresholds. Values must be greater than 0.")
                    else:
                        _, _, err_range = self._validate_custom_range(lower_text, upper_text)
                        if err_range:
                            config_hint_var.set(err_range)

                    config_hint_label.grid(row=4, column=0, columnspan=2, sticky="w", pady=(2, 0))

            else:
                config_hint_var.set("")

            if proto_lab is None:
                threshold_result_title_var.set("Select a prototype to evaluate.")
                threshold_result_detail_var.set("")
                threshold_result_summary_var.set("")
                return

            evaluation = self.evaluate_color_difference_threshold(
                sample_lab=lab,
                prototype_lab=proto_lab,
                metric=self.threshold_settings.get("metric", "CIEDE2000"),
                threshold_settings=self.threshold_settings
            )

            delta_e_value = evaluation.get("delta_e")
            if delta_e_value is None:
                threshold_result_title_var.set("ΔE not available")
            else:
                threshold_result_title_var.set(
                    evaluation.get("evaluation", "No evaluation available")
                )

            mode_text = evaluation.get("mode", "")
            preset_text = evaluation.get("preset", "")
            custom_type_text = evaluation.get("custom_type", "")

            if mode_text == "default":
                if preset_text == "pt":
                    detail = "Default preset: Perceptibility Threshold"
                elif preset_text == "at":
                    detail = "Default preset: Acceptability Threshold"
                else:
                    detail = "Default preset: Perceptibility + Acceptability"
            elif mode_text == "custom":
                if custom_type_text == "single":
                    detail = "Custom mode: Single threshold"
                else:
                    detail = "Custom mode: Lower and upper thresholds"
            else:
                detail = f"Mode: {mode_text}"

            threshold_result_detail_var.set(detail)
            threshold_result_summary_var.set(evaluation.get("summary", ""))


        #Bind Controls
        metric_combo.bind(
            "<<ComboboxSelected>>",
            lambda e: refresh_threshold_section(
                proto_lab=getattr(self, "_current_threshold_proto_lab", None)
            )
        )

        mode_combo.bind(
            "<<ComboboxSelected>>",
            lambda e: refresh_threshold_section(
                proto_lab=getattr(self, "_current_threshold_proto_lab", None)
            )
        )

        preset_combo.bind(
            "<<ComboboxSelected>>",
            lambda e: refresh_threshold_section(
                proto_lab=getattr(self, "_current_threshold_proto_lab", None)
            )
        )

        lower_entry.bind(
            "<KeyRelease>",
            lambda e: refresh_threshold_section(
                proto_lab=getattr(self, "_current_threshold_proto_lab", None)
            )
        )

        upper_entry.bind(
            "<KeyRelease>",
            lambda e: refresh_threshold_section(
                proto_lab=getattr(self, "_current_threshold_proto_lab", None)
            )
        )

        custom_type_combo.bind(
            "<<ComboboxSelected>>",
            lambda e: refresh_threshold_section(
                proto_lab=getattr(self, "_current_threshold_proto_lab", None)
            )
        )

        single_entry.bind(
            "<KeyRelease>",
            lambda e: refresh_threshold_section(
                proto_lab=getattr(self, "_current_threshold_proto_lab", None)
            )
        )

        # ---------------------------
        # Selection / update logic
        # ---------------------------
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

        def select_membership(label, mu):
            selected_label_var.set(label)

            proto_rgb = get_proto_rgb(label)
            proto_hex = safe_hex_from_rgb(proto_rgb)
            proto_lab = get_proto_lab(label)

            selected_proto_canvas.itemconfig(selected_proto_rect, fill=proto_hex)

            if proto_lab is not None:
                selected_lab_var.set(
                    f"LAB: {proto_lab[0]:.2f}, {proto_lab[1]:.2f}, {proto_lab[2]:.2f}"
                )
            else:
                selected_lab_var.set("LAB: not available")

            selected_rgb_var.set(f"RGB: {int(proto_rgb[0])}, {int(proto_rgb[1])}, {int(proto_rgb[2])}")
            selected_hex_var.set(f"HEX: {proto_hex.upper()}")

            self._current_threshold_proto_lab = proto_lab
            refresh_threshold_section(proto_lab=proto_lab)
            highlight_selected_row(label)

        # ---------------------------
        # Populate memberships
        # ---------------------------
        if memberships:
            for lbl, mu in memberships:
                row = tk.Frame(list_inner, bg="white", cursor="hand2", bd=0, highlightthickness=0)
                row.pack(fill="x", pady=1, padx=2)

                membership_rows[lbl] = row

                proto_hex = get_proto_hex(lbl)

                swatch = tk.Canvas(row, width=16, height=16, bg="white", highlightthickness=0)
                swatch.pack(side="left", padx=(4, 6), pady=2)
                swatch.create_rectangle(1, 1, 15, 15, fill=proto_hex, outline="#707070")

                lbl_name = tk.Label(
                    row,
                    text=str(lbl),
                    anchor="w",
                    bg="white",
                    font=("Sans", 10)
                )
                lbl_name.pack(side="left", fill="x", expand=True)

                lbl_mu = tk.Label(
                    row,
                    text=f"μ = {float(mu):.4f}",
                    anchor="e",
                    bg="white",
                    font=("Sans", 10)
                )
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

        # Initial selection = winner
        if memberships:
            initial_label = winner_label if winner_label not in (None, "None", "") else memberships[0][0]
            initial_mu = None
            for lbl, mu in memberships:
                if lbl == initial_label:
                    initial_mu = mu
                    break
            if initial_mu is None:
                initial_label, initial_mu = memberships[0]
            select_membership(initial_label, initial_mu)

        # ---------------------------
        # Bottom buttons
        # ---------------------------
        btns = tk.Frame(main, bg="#f2f2f2")
        btns.pack(fill="x", pady=(10, 0))
        tk.Button(btns, text="Close", command=win.destroy, width=12).pack(side="right")

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
            return None, None, "Lower threshold must be smaller than upper threshold."

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
            "summary": "ΔE: not available"
        }

        # ---------------------------
        # Compute metric
        # ---------------------------
        try:
            if metric == "CIEDE2000":
                delta_e_value = float(self.color_manager.delta_e_ciede2000(prototype_lab, sample_lab))
            else:
                result["status"] = "unsupported_metric"
                result["evaluation"] = f"Metric '{metric}' is not supported yet."
                result["summary"] = f"Metric: {metric} (not supported)"
                return result
        except Exception:
            return result

        result["delta_e"] = delta_e_value

        # ---------------------------
        # RAW MODE
        # ---------------------------
        if mode == "raw":
            result["status"] = "raw"
            result["evaluation"] = "Raw color difference only."
            result["summary"] = f"ΔE = {delta_e_value:.3f}"
            return result

        # ---------------------------
        # DEFAULT MODE
        # ---------------------------
        if mode == "default":
            preset = threshold_settings.get("preset", "pt_at")
            result["preset"] = preset

            if preset == "pt":
                lower = 0.8
                upper = None

                result["lower"] = lower
                result["upper"] = upper

                if delta_e_value <= lower:
                    result["status"] = "below_pt"
                    result["evaluation"] = "Below perceptibility threshold."
                else:
                    result["status"] = "above_pt"
                    result["evaluation"] = "Above perceptibility threshold."

                result["summary"] = f"ΔE = {delta_e_value:.3f} | PT = {lower:.3f}"
                return result

            elif preset == "at":
                lower = 1.8
                upper = None

                result["lower"] = lower
                result["upper"] = upper

                if delta_e_value <= lower:
                    result["status"] = "below_at"
                    result["evaluation"] = "Below acceptability threshold."
                else:
                    result["status"] = "above_at"
                    result["evaluation"] = "Above acceptability threshold."

                result["summary"] = f"ΔE = {delta_e_value:.3f} | AT = {lower:.3f}"
                return result

            else:  # pt_at
                lower = 0.8
                upper = 1.8

                result["lower"] = lower
                result["upper"] = upper

                if delta_e_value <= lower:
                    result["status"] = "below_pt"
                    result["evaluation"] = "Below perceptibility threshold."
                elif delta_e_value <= upper:
                    result["status"] = "between_pt_at"
                    result["evaluation"] = "Between perceptibility and acceptability thresholds."
                else:
                    result["status"] = "above_at"
                    result["evaluation"] = "Above acceptability threshold."

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
                    return result

                if delta_e_value <= single:
                    result["status"] = "below_custom"
                    result["evaluation"] = "Below custom threshold."
                else:
                    result["status"] = "above_custom"
                    result["evaluation"] = "Above custom threshold."

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
                    return result

                if delta_e_value <= lower:
                    result["status"] = "below_lower"
                    result["evaluation"] = "Below lower threshold."
                elif delta_e_value <= upper:
                    result["status"] = "between_custom"
                    result["evaluation"] = "Between lower and upper thresholds."
                else:
                    result["status"] = "above_upper"
                    result["evaluation"] = "Above upper threshold."

                result["summary"] = f"ΔE = {delta_e_value:.3f} | lower = {lower:.3f} | upper = {upper:.3f}"
                return result

        result["status"] = "unknown_mode"
        result["evaluation"] = f"Unknown threshold mode: {mode}"
        result["summary"] = f"ΔE = {delta_e_value:.3f}"
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











def start_up():
    root = tk.Tk()
    app = PyFCSApp(root)
    root.mainloop()

if __name__ == '__main__':
    start_up()

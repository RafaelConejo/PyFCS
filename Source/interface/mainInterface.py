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
import random
import platform
import threading
import numpy as np
import tkinter as tk
from skimage import color
import tkinter.font as tkFont
from functools import partial
from PIL import Image, ImageTk, ImageDraw, ImageFont
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from tkinter import ttk, Menu, filedialog, messagebox, Scrollbar, DISABLED, NORMAL

from PyQt5.QtCore import QUrl, QEventLoop
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QApplication, QMainWindow
from PyQt5.QtWebEngineWidgets import QWebEngineView
import matplotlib.pyplot as plt

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
        self.root = root  # Keep a reference to the main Tk window

        # Initialize application managers (image I/O, fuzzy spaces, evaluation, etc.)
        self.image_manager = ImageManager(
            root=self.root,
            custom_warning=self.custom_warning if hasattr(self, 'custom_warning') else None,
            center_popup=self.center_popup if hasattr(self, 'center_popup') else None
        )
        self.fuzzy_manager = FuzzyColorSpaceManager(root=self.root)
        self.color_manager = ColorEvaluationManager(output_dir="test_results/Color_Evaluation")
        self.volume_limits = ReferenceDomain(0, 100, -128, 127, -128, 127)

        # ---------------------------------------------------------------------
        # Utility flags / shared state
        # ---------------------------------------------------------------------
        self.COLOR_SPACE = False       # True if a color space is currently loaded/active
        self.FIRST_DBSCAN = True       # Used to treat the first DBSCAN run differently
        self.ORIGINAL_IMG = {}         # Stores original image data/state
        self.MEMBERDEGREE = {}         # Stores membership degree / color mapping results
        self.hex_color = []            # Stores point colors (hex) used for visualization
        self.images = {}               # Cache for images loaded/processed in the app
        self.color_entry_detect = {}   # Keeps track of UI entries used for color detection/edition
        self.cm_cache = {}             # Cache for the color mappings all
        self.proto_percentage_cache = {} # Cache for prototype-percentage grayscale maps
        self.display_pil = {}          # window_id -> PIL.Image currently displayed

        # ---------------------------------------------------------------------
        # Main window configuration
        # ---------------------------------------------------------------------
        root.title("PyFCS Interface")          # Window title
        root.geometry("1000x500")             # Default window size
        # self.root.attributes("-fullscreen", True)  # Optional fullscreen startup
        root.configure(bg="gray82")           # Window background

        # ---------------------------------------------------------------------
        # Menu bar (top-level)
        # ---------------------------------------------------------------------
        self.menubar = Menu(root)
        root.config(menu=self.menubar)

        # File menu
        file_menu = Menu(self.menubar, tearoff=0)
        file_menu.add_command(label="Exit", command=self.exit_app)
        self.menubar.add_cascade(label="File", menu=file_menu)

        # Image Manager menu
        img_menu = Menu(self.menubar, tearoff=0)
        img_menu.add_command(label="Open Image", command=self.open_image)
        img_menu.add_command(label="Save Image", command=self.save_image)
        img_menu.add_command(label="Close All", command=self.close_all_image)
        self.menubar.add_cascade(label="Image Manager", menu=img_menu)

        # Fuzzy Color Space Manager menu
        fuzzy_menu = Menu(self.menubar, tearoff=0)
        fuzzy_menu.add_command(label="New Color Space", command=self.show_menu_create_fcs)
        fuzzy_menu.add_command(label="Load Color Space", command=self.load_color_space)
        self.menubar.add_cascade(label="Fuzzy Color Space Manager", menu=fuzzy_menu)

        # Help menu
        help_menu = Menu(self.menubar, tearoff=0)
        help_menu.add_command(label="About", command=self.about_info)
        self.menubar.add_cascade(label="Help", menu=help_menu)

        # ---------------------------------------------------------------------
        # Top toolbar area (buttons grouped in sections)
        # ---------------------------------------------------------------------
        main_frame = tk.Frame(root, bg="gray82")
        main_frame.pack(padx=10, pady=10, fill="x")

        # --- "Image Manager" group
        image_manager_frame = tk.LabelFrame(
            main_frame, text="Image Manager", bg="gray95", padx=10, pady=10
        )
        image_manager_frame.pack(side="left", fill="both", expand=False, padx=5, pady=5)

        # Load toolbar icons
        load_image = os.path.join(BASE_PATH, 'Source', 'external', 'icons', 'LoadImage.png')
        load_image = Image.open(load_image)
        load_image = ImageTk.PhotoImage(load_image)

        save_image = os.path.join(BASE_PATH, 'Source', 'external', 'icons', 'SaveImage.png')
        save_image = Image.open(save_image)
        save_image = ImageTk.PhotoImage(save_image)

        new_fcs = os.path.join(BASE_PATH, 'Source', 'external', 'icons', 'NewFCS1.png')
        new_fcs = Image.open(new_fcs)
        new_fcs = ImageTk.PhotoImage(new_fcs)

        load_fcs = os.path.join(BASE_PATH, 'Source', 'external', 'icons', 'LoadFCS.png')
        load_fcs = Image.open(load_fcs)
        load_fcs = ImageTk.PhotoImage(load_fcs)

        at_image = os.path.join(BASE_PATH, 'Source', 'external', 'icons', 'AT.png')
        at_image = Image.open(at_image)
        at_image = ImageTk.PhotoImage(at_image)

        pt_image = os.path.join(BASE_PATH, 'Source', 'external', 'icons', 'PT.png')
        pt_image = Image.open(pt_image)
        pt_image = ImageTk.PhotoImage(pt_image)

        # Buttons for image operations
        tk.Button(
            image_manager_frame,
            image=load_image,
            text="Open Image",
            command=self.open_image,
            compound="left"
        ).pack(side="left", padx=5)
        image_manager_frame.load_image = load_image  # Keep reference to avoid garbage collection

        tk.Button(
            image_manager_frame,
            image=save_image,
            text=" Save Image",
            command=self.save_image,
            compound="left"
        ).pack(side="left", padx=5)
        image_manager_frame.save_image = save_image  # Keep reference to avoid garbage collection

        # --- "Fuzzy Color Space Manager" group
        fuzzy_manager_frame = tk.LabelFrame(
            main_frame, text="Fuzzy Color Space Manager", bg="gray95", padx=10, pady=10
        )
        fuzzy_manager_frame.pack(side="left", fill="both", expand=False, padx=5, pady=5)

        tk.Button(
            fuzzy_manager_frame,
            text="New Color Space",
            image=new_fcs,
            command=self.show_menu_create_fcs,
            compound="left"
        ).pack(side="left", padx=5)
        fuzzy_manager_frame.new_fcs = new_fcs  # Keep reference

        # Submenu for creating a new color space (two creation modes)
        self.menu_create_fcs = Menu(root, tearoff=0)
        self.menu_create_fcs.add_command(label="Palette-Based Creation", command=self.palette_based_creation)
        self.menu_create_fcs.add_command(label="Image-Based Creation", command=self.image_based_creation)

        tk.Button(
            fuzzy_manager_frame,
            text="Load Color Space",
            image=load_fcs,
            command=self.load_color_space,
            compound="left"
        ).pack(side="left", padx=5)
        fuzzy_manager_frame.load_fcs = load_fcs  # Keep reference

        # --- "Color Evaluation" group
        color_evaluation_frame = tk.LabelFrame(
            main_frame, text="Color Evaluation", bg="gray95", padx=10, pady=10
        )
        color_evaluation_frame.pack(side="left", fill="both", expand=False, padx=5, pady=5)

        tk.Button(
            color_evaluation_frame,
            text="Display AT",
            image=at_image,
            command=self.deploy_at,
            compound="left"
        ).pack(side="left", padx=5)
        color_evaluation_frame.at_image = at_image  # Keep reference

        tk.Button(
            color_evaluation_frame,
            text="Display PT",
            image=pt_image,
            command=self.deploy_pt,
            compound="left"
        ).pack(side="left", padx=5)
        color_evaluation_frame.pt_image = pt_image  # Keep reference

        # ---------------------------------------------------------------------
        # Main working area: split view (Image Display | Notebook tabs)
        # ---------------------------------------------------------------------
        main_content_frame = tk.Frame(root, bg="gray82")
        main_content_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # User-resizable horizontal split: Image Display (left) and Notebook (right)
        main_paned = ttk.Panedwindow(main_content_frame, orient="horizontal")
        main_paned.pack(fill="both", expand=True)

        # Left pane: image display area
        image_area_frame = tk.LabelFrame(
            main_paned, text="Image Display", bg="gray95", padx=10, pady=10
        )
        self.image_canvas = tk.Canvas(
            image_area_frame, bg="white", borderwidth=2, relief="ridge"
        )
        self.image_canvas.pack(fill="both", expand=True)

        # Right pane: notebook with different tabs (Model 3D, Data, ...)
        notebook_container = tk.Frame(main_paned, bg="gray82")
        self.notebook = ttk.Notebook(notebook_container)
        self.notebook.pack(fill="both", expand=True)

        # Add panes (weights control how extra space is distributed)
        main_paned.add(image_area_frame, weight=1)
        main_paned.add(notebook_container, weight=2)

        # Set an initial split ratio (30% left / 70% right) after the UI is laid out
        def set_initial_sash():
            total = main_paned.winfo_width()
            if total > 1:
                main_paned.sashpos(0, int(total * 0.30))

        self.root.after(100, set_initial_sash)

        # ---------------------------------------------------------------------
        # Tab: "Model 3D"
        # ---------------------------------------------------------------------
        model_3d_tab = tk.Frame(self.notebook, bg="gray95")
        self.notebook.add(model_3d_tab, text="Model 3D")

        # State container for 3D display options checkboxes
        self.model_3d_options = {}

        # Top bar with checkboxes for 3D visualization modes
        buttons_frame = tk.Frame(model_3d_tab, bg="gray95")
        buttons_frame.pack(side="top", fill="x", pady=5)

        # Available visualization options (default: Representative = True)
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
            ).pack(side="left", padx=20)

        # Split inside Model 3D tab: left (3D canvas) | right (color button list)
        paned = tk.PanedWindow(model_3d_tab, orient="horizontal", sashrelief="raised", bg="gray95")
        paned.pack(fill="both", expand=True)

        # Left side: container where the 3D graph/widget will be embedded
        self.Canvas1 = tk.Frame(paned, bg="white", borderwidth=2, relief="ridge", width=500)
        paned.add(self.Canvas1, stretch="always")

        # Right side: container for color buttons (scrollable)
        self.colors_frame = tk.Frame(paned, bg="gray95", width=2)
        paned.add(self.colors_frame)

        # Scrollable canvas to host many color buttons
        self.scrollable_canvas = tk.Canvas(self.colors_frame, bg="gray95", highlightthickness=0)
        self.scrollable_canvas.pack(side="left", fill="both", expand=True)

        # Vertical scrollbar for the color-button canvas
        self.scrollbar = tk.Scrollbar(self.colors_frame, orient="vertical", command=self.scrollable_canvas.yview)
        self.scrollbar.pack(side="right", fill="y")

        # Connect canvas scrolling to scrollbar and set a fixed width for the color panel
        self.scrollable_canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollable_canvas.configure(width=150)

        # Inner frame placed inside the scrollable canvas (holds the button widgets)
        self.inner_frame = tk.Frame(self.scrollable_canvas, bg="gray95")
        self.inner_frame.bind(
            "<Configure>",
            lambda e: self.scrollable_canvas.configure(scrollregion=self.scrollable_canvas.bbox("all"))
        )

        # Enable mouse wheel scrolling only when the cursor is over this specific canvas
        def bind_scroll_events(canvas):
            def _on_mousewheel(event):
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

            def _bind_mousewheel(event):
                if platform.system() == 'Windows':
                    canvas.bind_all("<MouseWheel>", _on_mousewheel)
                elif platform.system() == 'Darwin':  # macOS
                    canvas.bind_all("<MouseWheel>", _on_mousewheel)
                else:  # Linux
                    canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
                    canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))

            def _unbind_mousewheel(event):
                canvas.unbind_all("<MouseWheel>")

            canvas.bind("<Enter>", _bind_mousewheel)
            canvas.bind("<Leave>", _unbind_mousewheel)

        bind_scroll_events(self.scrollable_canvas)

        # Insert inner_frame into the scrollable canvas
        self.colors_canvas_window_id = self.scrollable_canvas.create_window(
            (0, 0), window=self.inner_frame, anchor="nw"
        )

        # Container for action buttons and generated color buttons
        self.color_buttons_frame = tk.Frame(self.inner_frame, bg=self.inner_frame["bg"])
        self.color_buttons_frame.pack(pady=5)

        # Shared style for color-related buttons
        button_style = {
            "width": 10,
            "height": 1,
            "font": ("Sans", 10, "bold"),
            "relief": "raised",
            "bd": 2,
            "cursor": "hand2"
        }

        # Select/Deselect all buttons (shown only when a color space is active)
        self.select_all_button = tk.Button(
            self.color_buttons_frame,
            text="Select All",
            command=self.select_all_color,
            **button_style
        )
        if self.COLOR_SPACE:
            self.select_all_button.pack(pady=5)

        self.deselect_all_button = tk.Button(
            self.color_buttons_frame,
            text="Deselect All",
            command=self.deselect_all_color,
            **button_style
        )
        if self.COLOR_SPACE:
            self.deselect_all_button.pack(pady=5)

        # ---------------------------------------------------------------------
        # Tab: "Data"
        # ---------------------------------------------------------------------
        data_tab = tk.Frame(self.notebook, bg="gray95")
        self.notebook.add(data_tab, text="Data")

        # Header area: dataset/name field
        name_data = tk.Frame(data_tab, bg="#e0e0e0", pady=5)
        name_data.pack(fill="x")
        tk.Label(
            name_data, text="Name:", font=("Helvetica", 12, "bold"), bg="#e0e0e0"
        ).pack(side="top", pady=5)

        self.file_name_entry = tk.Entry(name_data, font=("Helvetica", 12), width=30, justify="center")
        self.file_name_entry.pack(side="top", pady=5)
        self.file_name_entry.insert(0, "")  # Default/initial name

        # Main area: table canvas + scrollbars
        canvas_frame = tk.Frame(data_tab, bg="white")
        canvas_frame.pack(fill="both", expand=True)

        # Canvas used to render the editable color table/grid
        self.data_window = tk.Canvas(canvas_frame, bg="white", borderwidth=2, relief="ridge")
        self.data_window.grid(row=0, column=0, sticky="nsew")

        # Let the canvas expand in both directions
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        # Vertical scrollbar for the data canvas
        self.data_scrollbar_v = Scrollbar(canvas_frame, orient="vertical", command=self.data_window.yview)
        self.data_scrollbar_v.grid(row=0, column=1, sticky="ns")

        # Horizontal scrollbar for the data canvas
        self.data_scrollbar_h = Scrollbar(canvas_frame, orient="horizontal", command=self.data_window.xview)
        self.data_scrollbar_h.grid(row=1, column=0, sticky="ew")
        self.data_scrollbar_h.bind("<MouseWheel>", lambda event: self.on_mouse_wheel(event, self.data_scrollbar_h))

        # Attach scrollbars to canvas
        self.data_window.configure(
            yscrollcommand=self.data_scrollbar_v.set,
            xscrollcommand=self.data_scrollbar_h.set
        )

        # Inner frame placed inside the data canvas (holds the table widgets)
        self.inner_frame_data = tk.Frame(self.data_window, bg="white")
        self.data_window.create_window((0, 0), window=self.inner_frame_data, anchor="nw")

        # Keep the canvas scrollable region updated when the inner frame changes size
        def update_scroll_region_2(event):
            self.data_window.configure(scrollregion=self.data_window.bbox("all"))

        self.inner_frame_data.bind("<Configure>", update_scroll_region_2)

        # Bottom bar: action buttons ("Add New Color", "Apply Changes")
        bottom_bar = tk.Frame(data_tab, bg="#e0e0e0", pady=5)
        bottom_bar.pack(fill="x", side="bottom")

        button_container = tk.Frame(bottom_bar, bg="#e0e0e0")
        button_container.pack(pady=5)

        add_button = tk.Button(
            button_container,
            text="Add New Color",
            font=("Helvetica", 12, "bold"),
            bg="#E0F2E9",
            command=lambda: self.addColor_data_window()
        )
        add_button.pack(side="left", padx=20)

        apply_button = tk.Button(
            button_container,
            text="Apply Changes",
            font=("Helvetica", 12, "bold"),
            bg="#E0F2E9",
            command=lambda: self.apply_changes()
        )
        apply_button.pack(side="left", padx=20)

        # ---------------------------------------------------------------------
        # Additional runtime state
        # ---------------------------------------------------------------------
        self.rgb_data = []          # RGB points for 3D visualization
        self.graph_widget = None    # Tracks the current 3D graph widget instance
        self.app_qt = None          # Reference to any Qt bridge/app (if used)
        self.more_graph_window = None

        # ---------------------------------------------------------------------
        # Global keyboard shortcuts
        # ---------------------------------------------------------------------
        self.root.bind("<Escape>", self.toggle_fullscreen)

        self.root.bind("<Control-o>", lambda event: self.open_image())         # Open image
        self.root.bind("<Control-s>", lambda event: self.save_image())         # Save image
        self.root.bind("<Control-w>", lambda event: self.close_all_image())    # Close all images
        self.root.bind("<Control-n>", lambda event: self.show_menu_create_fcs())  # New color space
        self.root.bind("<Control-l>", lambda event: self.load_color_space())      # Load color space
        self.root.bind("<Control-a>", lambda event: self.select_all_color())      # Select all colors

        # Optional: tab switching shortcuts (currently disabled)
        # self.root.bind("<Control-Tab>", lambda event: self.switch_tab(notebook, forward=True))
        # self.root.bind("<Control-Shift-Tab>", lambda event: self.switch_tab(notebook, forward=False))






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
        """Cambiar entre pestañas del notebook (Ctrl+Tab)."""
        current_index = notebook.index(notebook.select())
        total_tabs = len(notebook.tabs())
        if forward:
            new_index = (current_index + 1) % total_tabs
        else:
            new_index = (current_index - 1) % total_tabs
        notebook.select(new_index)

    

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
            bg="#4CAF50",  # Green background
            fg="white",    # White text
            relief=tk.FLAT,
            padx=10,
            pady=5
        )
        close_button.pack(pady=10)  # Add the button to the frame



    def show_menu_create_fcs(self):
        self.menu_create_fcs.post(self.root.winfo_pointerx(), self.root.winfo_pointery())



    def on_mouse_wheel(self, event, scrollbar):
        scrollbar.yview_scroll(-1 * (event.delta // 120), "units")



    def center_popup(self, popup, width, height):
        """
        Centers a popup window on the same screen as the parent widget.
        
        Args:
            parent: The parent widget (e.g., self.root).
            popup: The popup window to center.
            width: The width of the popup window.
            height: The height of the popup window.
        """
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_width = self.root.winfo_width()
        root_height = self.root.winfo_height()

        popup_x = root_x + (root_width - width) // 2
        popup_y = root_y + (root_height - height) // 2

        popup.geometry(f"{width}x{height}+{popup_x}+{popup_y}")













    ########################################################################################### Main Functions ###########################################################################################
    def update_volumes(self):
        self.prototypes = UtilsTools.process_prototypes(self.color_data)

        # Create and save the fuzzy color space
        self.fuzzy_color_space = FuzzyColorSpace(space_name=" ", prototypes=self.prototypes)
        self.fuzzy_color_space.precompute_pack()
        self.cores = self.fuzzy_color_space.get_cores()
        self.supports = self.fuzzy_color_space.get_supports()

        self.update_prototypes_info()
    


    def update_prototypes_info(self):
        # Update 3D graph and app state vars
        self.COLOR_SPACE = True
        self.MEMBERDEGREE = {key: True for key in self.MEMBERDEGREE}
        self.select_all_button.pack(pady=5)
        self.deselect_all_button.pack(pady=5)

        self.selected_centroids = self.color_data
        self.selected_hex_color = self.hex_color
        self.selected_alpha = self.prototypes
        self.selected_core = self.cores
        self.selected_support = self.supports
        self.on_option_select()



    def load_color_space(self):
        """
        Allows the user to select a fuzzy color space file and displays its color data in a scrollable table.
        This includes loading the file, extracting the data, and displaying it visually on a canvas.
        """
        filename = UtilsTools.prompt_file_selection('fuzzy_color_spaces/')
        if not filename:
            return

        # Activate the 'Original Image' option for all open windows
        if hasattr(self, 'floating_images') and self.floating_images:
            for window_id in list(self.floating_images.keys()):
                self.show_original_image(window_id)

        self.show_loading_color_space()

        try:
            data = self.fuzzy_manager.load_color_file(filename)

            self.file_path = filename
            self.file_base_name = os.path.splitext(os.path.basename(filename))[0]

            # Clear color-mapping cache when loading a new FCS/CNS
            if hasattr(self, "cm_cache"):
                self.cm_cache.clear()
            else:
                self.cm_cache = {}

            # Clear caches when loading a new color space (FCS/CNS)
            if hasattr(self, "proto_percentage_cache"):
                self.proto_percentage_cache.clear()
            else:
                self.proto_percentage_cache = {}


            if data['type'] == 'cns':
                self.color_data = data['color_data']
                self.display_data_window()
                self.update_volumes()

            elif data['type'] == 'fcs':
                self.color_data = data['color_data']
                self.fuzzy_color_space = data['fuzzy_color_space']
                self.cores = self.fuzzy_color_space.cores
                self.supports = self.fuzzy_color_space.supports
                self.prototypes = self.fuzzy_color_space.prototypes
                self.fuzzy_color_space.precompute_pack()

                self.display_data_window()
                self.update_prototypes_info()

        except ValueError as e:
            self.custom_warning("File Error", str(e))

        finally:
            self.hide_loading()



    def create_color_space(self):
        """
        Creates a fuzzy color space from selected colors and prompts the user to name it.
        The selected colors are converted to LAB values, and the color space is saved.
        """
        # Extract selected colors and their LAB values
        selected_colors_lab = {
            name: np.array([data["lab"]["L"], data["lab"]["A"], data["lab"]["B"]]) if isinstance(data["lab"], dict)
            else np.array(data["lab"])
            for name, data in self.color_checks.items() if data["var"].get()
        }

        # Ensure at least two colors are selected
        if len(selected_colors_lab) < 2:
            self.custom_warning("Warning", "At least two colors must be selected to create the Color Space.")
            return  # Early return to avoid unnecessary processing

        # Create a popup window for the user to name the color space
        popup = tk.Toplevel(self.root)  # Create a secondary window
        popup.title("Color Space Name")
        self.center_popup(popup, 300, 100)  # Center the popup window

        # Add a label and entry field for the color space name
        tk.Label(popup, text="Name for the fuzzy color space:").pack(pady=5)
        name_entry = tk.Entry(popup)
        name_entry.pack(pady=5)

        # Variable to store the entered name
        name = tk.StringVar()

        def on_ok():
            """Callback function for the OK button."""
            name.set(name_entry.get())  # Set the value in the StringVar
            popup.destroy()  # Close the popup window
            self.save_cs(name.get(), selected_colors_lab)  # Save the color space

        # Add an OK button to confirm the name
        ok_button = tk.Button(popup, text="OK", command=on_ok)
        ok_button.pack(pady=5)

        # Display the popup window
        popup.deiconify()



    def save_cs(self, name, selected_colors_lab):
        """
        Saves the color space with the given name and LAB values.
        Displays a loading indicator and updates the progress bar during the save process.
        """
        self.show_loading()  # Show loading indicator

        def update_progress(current_line, total_lines):
            """
            Updates the progress bar based on the number of lines written.
            
            Args:
                current_line (int): The current line being processed.
                total_lines (int): The total number of lines to process.
            """
            progress_percentage = (current_line / total_lines) * 100
            self.progress["value"] = progress_percentage
            self.load_window.update_idletasks()  # Refresh the UI

        def run_save_process():
            """
            Saves the file in a separate thread to avoid blocking the main UI.
            Handles exceptions and ensures the loading indicator is hidden afterward.
            """
            try:
                # Initialize the input class for .fcs files
                input_class = Input.instance('.fcs')
                # Write the file with the provided name, LAB values, and progress callback
                input_class.write_file(name, selected_colors_lab, progress_callback=update_progress)
            except Exception as e:
                # Show an error message if something goes wrong
                self.custom_warning("Error", f"An error occurred while saving: {e}")
            finally:
                # Ensure the loading indicator is hidden and show a success message
                self.load_window.after(0, self.hide_loading)
                self.load_window.after(0, lambda: messagebox.showinfo(
                    "Color Space Created", f"Color Space '{name}' created successfully."
                ))

        # Start the save process in a separate thread
        threading.Thread(target=run_save_process, daemon=True).start()


    
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
            Validates the input and adds the new color to the colors dictionary.
            Closes the popup if the input is valid.
            """
            try:
                color_name = color_name_var.get().strip()
                l_value = float(l_value_var.get())
                a_value = float(a_value_var.get())
                b_value = float(b_value_var.get())

                # Validate inputs
                if not color_name:
                    raise ValueError("The color name cannot be empty.")
                if not (0 <= l_value <= 100):
                    raise ValueError("L value must be between 0 and 100.")
                if not (-128 <= a_value <= 127):
                    raise ValueError("A value must be between -128 and 127.")
                if not (-128 <= b_value <= 127):
                    raise ValueError("B value must be between -128 and 127.")
                if color_name in colors:
                    raise ValueError(f"The color name '{color_name}' already exists.")

                # Store the result
                result["color_name"] = color_name
                result["lab"] = {"L": l_value, "A": a_value, "B": b_value}

                # Add the color to the dictionary
                colors[color_name] = {"lab": result["lab"]}
                popup.destroy()  # Close the popup

            except ValueError as e:
                self.custom_warning("Invalid Input", str(e))  # Show error message for invalid input

        def browse_color():
            """
            Opens a color picker window to select a color from a color wheel.
            Converts the selected color to LAB values and updates the input fields.
            """
            color_picker = tk.Toplevel()
            color_picker.title("Select a Color")
            color_picker.geometry("350x450")
            color_picker.transient(popup)
            color_picker.grab_set()

            # Position the color picker window to the right of the "Add New Color" window
            x_offset = popup.winfo_x() + popup.winfo_width() + 10
            y_offset = popup.winfo_y()
            color_picker.geometry(f"350x450+{x_offset}+{y_offset}")

            canvas_size = 300
            center = canvas_size // 2
            radius = center - 5

            def draw_color_wheel():
                """Draws the color wheel on the canvas."""
                for y in range(canvas_size):
                    for x in range(canvas_size):
                        dx, dy = x - center, y - center
                        dist = math.sqrt(dx**2 + dy**2)
                        if dist <= radius:
                            angle = math.atan2(dy, dx)
                            hue = (angle / (2 * math.pi)) % 1
                            r, g, b = UtilsTools.hsv_to_rgb(hue, 1, 1)
                            color_code = f'#{r:02x}{g:02x}{b:02x}'
                            canvas.create_line(x, y, x + 1, y, fill=color_code)

            def on_click(event):
                """Gets the selected color from the color wheel and updates the LAB values."""
                x, y = event.x, event.y
                dx, dy = x - center, y - center
                dist = math.sqrt(dx**2 + dy**2)

                if dist <= radius:
                    angle = math.atan2(dy, dx)
                    hue = (angle / (2 * math.pi)) % 1
                    r, g, b = UtilsTools.hsv_to_rgb(hue, 1, 1)
                    color_hex = f'#{r:02x}{g:02x}{b:02x}'

                    preview_canvas.config(bg=color_hex)  # Update the preview canvas

                    # Convert RGB to LAB
                    rgb = np.array([[r, g, b]]) / 255
                    lab = color.rgb2lab(rgb.reshape((1, 1, 3)))[0][0]

                    # Update the LAB values in the main window
                    l_value_var.set(f"{lab[0]:.2f}")
                    a_value_var.set(f"{lab[1]:.2f}")
                    b_value_var.set(f"{lab[2]:.2f}")

            def confirm_selection():
                """Closes the color picker window."""
                color_picker.destroy()

            # Create and draw the color wheel
            canvas = tk.Canvas(color_picker, width=canvas_size, height=canvas_size)
            canvas.pack()
            draw_color_wheel()
            canvas.bind("<Button-1>", on_click)

            # Preview canvas for selected color
            preview_canvas = tk.Canvas(color_picker, width=100, height=50, bg="white")
            preview_canvas.pack(pady=10)

            # Confirm button
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
    


    def palette_based_creation(self):
        """
        Logic for creating a new fuzzy color space using a predefined palette.
        Allows the user to select colors through a popup and creates a new fuzzy color space.
        """
        # Load color data from the BASIC.cns file
        color_space_path = os.path.join(BASE_PATH, 'fuzzy_color_spaces', 'cns', 'ISCC_NBS_BASIC.cns')
        colors = UtilsTools.load_color_data(color_space_path)

        # Create a popup window for color selection
        popup, self.scroll_palette_create_fcs = UtilsTools.create_popup_window(
            parent=self.root,
            title="Select colors for your Color Space",
            width=450,
            height=500,
            header_text="Select colors for your Color Space"
        )

        # Center the popup window
        self.center_popup(popup, 450, 500)

        # Dictionary to store the Checkbuttons for selected colors
        self.color_checks = {}

        # Populate the scrollable frame with color data
        for color_name, data in colors.items():
            self.fuzzy_manager.create_color_display_frame(
                parent=self.scroll_palette_create_fcs,
                color_name=color_name,
                rgb=data["rgb"],
                lab=data["lab"],
                color_checks=self.color_checks
            )

        # Add action buttons to the popup
        button_frame = ttk.Frame(popup)
        button_frame.pack(pady=20)

        # Button to add a new color
        ttk.Button(
            button_frame,
            text="Add New Color",
            command=lambda: self.addColor_create_fcs(popup, colors),
            style="Accent.TButton"
        ).pack(side="left", padx=20)

        # Button to create the color space
        ttk.Button(
            button_frame,
            text="Create Color Space",
            command=self.create_color_space,
            style="Accent.TButton"
        ).pack(side="left", padx=20)

        # Style configuration for buttons
        style = ttk.Style()
        style.configure("Accent.TButton", font=("Helvetica", 10, "bold"), padding=10)



    def image_based_creation(self):
        """
        Now shows a mode selector:
        - Manual color selection from Image
        - Automatic Color detection (existing flow -> get_fcs_image)
        """
        # Verify if there are available images to display
        if not hasattr(self, "load_images_names") or not self.load_images_names:
            self.custom_warning(message="No images are currently available to display.")
            return

        self.FIRST_DBSCAN = True

        # Ask for creation mode first
        self._popup_choose_image_creation_mode()


    def _popup_choose_image_creation_mode(self):
        """Popup with two buttons: Manual / Automatic."""
        popup = tk.Toplevel(self.root)
        popup.title("Image-Based Creation Mode")
        popup.resizable(False, False)

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
            command=lambda: self._start_image_based_mode(popup, mode="manual")
        )
        btn_manual.pack(fill="x", pady=4)

        btn_auto = tk.Button(
            frame,
            text="Automatic Color Detection from Image",
            width=30,
            command=lambda: self._start_image_based_mode(popup, mode="auto")
        )
        btn_auto.pack(fill="x", pady=4)

        # Center popup
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
        colors = {}  # Local storage for user-added colors (resets when the popup is closed)

        # Create the main popup window and the scrollable area where colors will be displayed
        popup, self.scroll_palette_create_fcs = UtilsTools.create_popup_window(
            parent=self.root,
            title="Select colors for your Color Space",
            width=480,
            height=520,
            header_text="Select colors for your Color Space"
        )
        self.center_popup(popup, 480, 520)

        # Keep references to the active manual popup and selection checkbuttons
        self._manual_popup = popup
        self.color_checks = {}

        # Cleanup on close (also closes the picker window if it is open)
        def on_close():
            """Destroy associated picker window and clear references when closing the manual popup."""
            if hasattr(self, "_manual_picker_win") and self._manual_picker_win and self._manual_picker_win.winfo_exists():
                self._manual_picker_win.destroy()
            self._manual_picker_win = None
            self._manual_popup = None
            popup.destroy()

        popup.protocol("WM_DELETE_WINDOW", on_close)

        # Buttons container (2 columns + a full-width Create button)
        button_frame = ttk.Frame(popup)
        button_frame.pack(fill="x", padx=20, pady=15)
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)

        # Open image picker (pass local colors dict + the target frame where rows will be added)
        btn_add_img = ttk.Button(
            button_frame,
            text="Add Color from Image",
            command=partial(self._open_manual_image_picker_window, colors, self.scroll_palette_create_fcs),
            style="Accent.TButton"
        )

        # Add a new color via the generic "addColor" flow (uses local colors dict)
        btn_add_new = ttk.Button(
            button_frame,
            text="Add New Color",
            command=lambda: self.addColor_create_fcs(popup, colors),
            style="Accent.TButton"
        )

        # Create the fuzzy color space using the currently selected colors
        btn_create = ttk.Button(
            button_frame,
            text="Create Color Space",
            command=self.create_color_space,
            style="Accent.TButton"
        )

        # Row 0: two buttons
        btn_add_img.grid(row=0, column=0, sticky="ew", padx=5, pady=(0, 8))
        btn_add_new.grid(row=0, column=1, sticky="ew", padx=5, pady=(0, 8))

        # Row 1: create button spans both columns
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
        ttk.Label(right, text="Click on the image to pick a color").pack(anchor="w")
        self._manual_img_canvas = tk.Canvas(right, width=420, height=320, bg="black", highlightthickness=1)
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

        # Bind canvas click for picking colors
        self._manual_img_canvas.bind("<Button-1>", self._manual_on_image_click)


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


















    ########################################################################################### Funtions Model 3D ###########################################################################################
    def on_option_select(self):
        if self.COLOR_SPACE:  # Check if a color space is loaded
            self.filtered_points = {}
            selected_options = [key for key, var in self.model_3d_options.items() if var.get()]  # Get all selected options
            
            if not selected_options and self.graph_widget:
                self.display_color_buttons(self.color_matrix)
                self.graph_widget.get_tk_widget().destroy() 
            else:
                fig = VisualManager.plot_combined_3D(
                    self.file_base_name,
                    self.selected_centroids,
                    self.selected_core,
                    self.selected_alpha,
                    self.selected_support,
                    self.volume_limits,
                    self.hex_color,
                    selected_options
                )
                self.draw_model_3D(fig, selected_options)  # Pass each figure to be drawn on the Tkinter Canvas
                if hasattr(self, "lab_value_frame"):
                    self.lab_value_frame.lift()



    def draw_model_3D(self, fig, selected_options):
        """Draws the 3D plot on the Tkinter canvas."""
        if self.graph_widget:  # Check if a previous graph exists
            self.graph_widget.get_tk_widget().destroy()  # Destroy the previous widget

        # Create a new matplotlib widget and draw the figure
        self.graph_widget = FigureCanvasTkAgg(fig, master=self.Canvas1)
        self.graph_widget.draw()  # Draw the figure
        self.graph_widget.get_tk_widget().pack(fill="both", expand=True)  # Pack the widget into the canvas

        # Display the color selection buttons
        self.display_color_buttons(self.color_matrix)

        # Crear y añadir un botón con el símbolo "+"
        self.add_button = tk.Button(self.Canvas1, text="Interactive Figure", font=("Sans", 12), command=lambda: self.on_add_graph(selected_options))
        self.add_button.place(relx=0.95, rely=0.05, anchor="ne")  # Posiciona el botón en la esquina superior derecha



    def on_add_graph(self, selected_options):
        """Generates the figure with Plotly, saves it as HTML, and displays it in a PyQt5 window."""

        def rebuild_menu():
            """Rebuilds the menu bar to prevent UI glitches after PyQt5 is used."""
            self.menubar.destroy()  # Elimina la barra de menú anterior
            self.menubar = Menu(self.root)  # Crea una nueva barra de menú
            self.root.config(menu=self.menubar)  # Asigna la nueva barra de menú

            # Define el tamaño de la fuente que se usará en los menús
            menu_font = tkFont.Font(family="Sans", size=11)  # Puedes ajustar el tamaño (size) aquí

            # File menu
            file_menu = Menu(self.menubar, tearoff=0)
            file_menu.add_command(label="Exit", command=self.exit_app, font=menu_font)
            self.menubar.add_cascade(label="File", menu=file_menu)

            # Image Manager menu
            img_menu = Menu(self.menubar, tearoff=0)
            img_menu.add_command(label="Open Image", command=self.open_image, font=menu_font)
            img_menu.add_command(label="Save Image", command=self.save_image, font=menu_font)
            img_menu.add_command(label="Close All", command=self.close_all_image, font=menu_font)
            self.menubar.add_cascade(label="Image Manager", menu=img_menu)

            # Fuzzy Color Space Manager menu
            fuzzy_menu = Menu(self.menubar, tearoff=0)
            fuzzy_menu.add_command(label="New Color Space", command=self.show_menu_create_fcs, font=menu_font)
            fuzzy_menu.add_command(label="Load Color Space", command=self.load_color_space, font=menu_font)
            self.menubar.add_cascade(label="Fuzzy Color Space Manager", menu=fuzzy_menu)

            # Help menu
            help_menu = Menu(self.menubar, tearoff=0)
            help_menu.add_command(label="About", command=self.about_info, font=menu_font)
            self.menubar.add_cascade(label="Help", menu=help_menu)



        def close_event(event):
            """Handles the window close event."""
            self.more_graph_window = None  # Releases the reference to the window
            rebuild_menu() 
            event.accept()  # Accepts the close event

        fig = VisualManager.plot_more_combined_3D(
                    self.file_base_name,
                    self.selected_centroids,
                    self.selected_core,
                    self.selected_alpha,
                    self.selected_support,
                    self.volume_limits,
                    self.hex_color,
                    selected_options,
                    self.filtered_points
                )
        if hasattr(self, "lab_value_frame"):
                    self.lab_value_frame.lift()

        file_path = os.path.abspath(os.path.join(BASE_PATH, 'Source', 'external', 'temp_plot.html'))
        fig.write_html(file_path)
        file_path = file_path.replace("\\", "/")  # Correct solution

        # Check if the application is already created
        if self.app_qt is None:
            self.app_qt = QApplication(sys.argv)

        if self.more_graph_window is None or not self.more_graph_window.isVisible():
            self.more_graph_window = QMainWindow()
            self.more_graph_window.setWindowTitle("Interactive 3D Figure")
            self.more_graph_window.setGeometry(100, 100, 800, 600)

            # Create a web viewer for the HTML
            webview = QWebEngineView()
            webview.setUrl(QUrl(f"file:///{file_path}"))  # 🚀 Correct solution

            # Add the viewer to the window
            layout = QVBoxLayout()
            layout.addWidget(webview)
            central_widget = QWidget()
            central_widget.setLayout(layout)
            self.more_graph_window.setCentralWidget(central_widget)

            # Detect the screen where the cursor is located
            cursor_pos = QApplication.desktop().cursor().pos()
            screen_number = QApplication.desktop().screenNumber(cursor_pos)
            screen_geom = QApplication.desktop().screenGeometry(screen_number)

            # Calculate the centered position on the same monitor
            width = 800
            height = 600
            popup_x = screen_geom.x() + (screen_geom.width() - width) // 2
            popup_y = screen_geom.y() + (screen_geom.height() - height) // 2

            # Set the position on the same screen
            self.more_graph_window.setGeometry(popup_x, popup_y, width, height)
            self.more_graph_window.show()

            # Connect the close event signal to release the reference
            self.more_graph_window.closeEvent = close_event

        loop = QEventLoop()
        self.more_graph_window.destroyed.connect(loop.quit)
        loop.exec_()

        

    def select_all_color(self):
        """Handles the 'select all' option for colors."""
        if self.COLOR_SPACE:
            self.selected_centroids = self.color_data
            self.selected_hex_color = self.hex_color
            self.selected_alpha = self.prototypes
            self.selected_core = self.cores
            self.selected_support = self.supports

            # Uncheck all the color selection buttons
            for _, var in self.selected_colors.items():
                var.set(True)
            
            self.on_option_select()  # Redraw the 3D model after selecting all colors

    def deselect_all_color(self):
        """Handles the 'deselect all' option for colors."""
        if self.COLOR_SPACE:
            # Vaciar todas las listas/atributos relacionados con la selección
            self.selected_centroids = []
            self.selected_hex_color = []
            self.selected_alpha = []
            self.selected_core = []
            self.selected_support = []

            # Desmarcar todos los botones de selección de color
            for _, var in self.selected_colors.items():
                var.set(False)

            self.on_option_select()  # Redibujar el modelo 3D sin colores seleccionados




    def select_color(self):
        """Handles the individual color selection from the checkboxes."""
        selected_centroids = {}
        selected_indices = []

        # Iterate through the selected colors and store the selected ones
        for color_name, selected in self.selected_colors.items():
            if selected.get():  # If the color is selected
                # Get the corresponding color data
                if color_name in self.color_data:
                    selected_centroids[color_name] = self.color_data[color_name]
                    keys = list(self.color_data.keys())
                    selected_indices.append(keys.index(color_name))

        # Ensure indices exist before using them
        if selected_indices:
            self.selected_hex_color = {
                hex_color_key: lab_value for index in selected_indices
                for hex_color_key, lab_value in self.hex_color.items()
                if np.array_equal(lab_value, self.color_data[keys[index]]['positive_prototype'])
            }
            self.selected_alpha = [self.prototypes[i] for i in selected_indices]
            self.selected_core = [self.cores[i] for i in selected_indices]
            self.selected_support = [self.supports[i] for i in selected_indices]

        # Store selected centroids
        self.selected_centroids = selected_centroids

        # Redraw the 3D model based on the selected colors
        self.on_option_select()


        

    def display_color_buttons(self, colors):
        """Displays color selection checkboxes with all options initially selected, but remembers previous states."""
        
        # Store previous selection states if they exist
        previous_selected_colors = {
            color: var.get() for color, var in getattr(self, 'selected_colors', {}).items()
        } if hasattr(self, 'selected_colors') else {}

        # Remove old buttons if they exist
        if hasattr(self, 'color_buttons'):
            for button in self.color_buttons:
                button.destroy()

        # Reinitialize variables and button list
        self.selected_colors = {}
        self.color_buttons = []

        # Create a checkbox for each color inside the scrollable inner_frame
        for color in colors:
            # Restore previous state if it exists; otherwise, select by default
            is_selected = previous_selected_colors.get(color, True)  
            self.selected_colors[color] = tk.BooleanVar(value=is_selected)

            # Create the checkbox button
            button = tk.Checkbutton(
                self.inner_frame,  # Use inner_frame for scrollable content
                text=color,
                variable=self.selected_colors[color],  # Variable for checkbox state
                bg="gray95",  # Button background color
                font=("Sans", 10),
                onvalue=True,  # Value when checked
                offvalue=False,  # Value when unchecked
                command=self.select_color,  # Call select_color on change
            )
            button.pack(anchor="w", pady=2, padx=10)  # Pack the button into the UI frame
            
            self.color_buttons.append(button)  # Store the created button

        # Update the scrollable canvas region to fit new content
        self.scrollable_canvas.update_idletasks()
        self.scrollable_canvas.configure(scrollregion=self.scrollable_canvas.bbox("all"))


















    ########################################################################################### Funtions Data ###########################################################################################
    def display_data_window(self):
        """
        Displays the color data in a scrollable table within the canvas.
        Updates the table with LAB values, labels, and color previews.
        """
        # Update the "Name" field with the current file name
        self.file_name_entry.delete(0, "end")  # Clear previous text in the entry
        self.file_name_entry.insert(0, self.file_base_name)  # Insert the current file name

        # Clear the canvas
        self.data_window.delete("all")
        self.data_window.update_idletasks()  # Ensure the canvas is updated

        # Calculate canvas and table dimensions
        canvas_width = self.data_window.winfo_width()  # Canvas width
        column_widths = [80, 80, 80, 200, 150]  # Column widths (without Action)
        table_width = sum(column_widths)  # Total table width
        margin = max((canvas_width - table_width) // 2, 20)  # Dynamic margin or minimum of 20

        # Starting coordinates
        x_start = margin
        y_start = 20

        # Column headers and dimensions
        headers = ["L", "a", "b", "Label", "Color"]
        header_height = 30

        # Draw table headers
        for i, header in enumerate(headers):
            x_pos = x_start + sum(column_widths[:i])  # Calculate header position
            self.data_window.create_rectangle(
                x_pos, y_start, x_pos + column_widths[i], y_start + header_height,
                fill="#d3d3d3", outline="#a9a9a9"
            )
            self.data_window.create_text(
                x_pos + column_widths[i] / 2, y_start + header_height / 2,
                text=header, anchor="center", font=("Sans", 10, "bold")
            )

        # Adjust starting point for rows
        y_start += header_height + 10
        row_height = 40
        rect_width = 120  # Width of the color rectangle
        rect_height = 30

        self.hex_color = {}  # Store HEX color mapping
        self.color_matrix = []  # Store color names

        # Iterate through color data and populate rows
        for i, (color_name, color_value) in enumerate(self.color_data.items()):
            lab = np.array(color_value['positive_prototype'])  # Extract and convert LAB color values
            self.color_matrix.append(color_name)

            # Draw table columns (L, a, b, Label)
            for j, value in enumerate([lab[0], lab[1], lab[2], color_name]):
                x_pos = x_start + sum(column_widths[:j])  # Column starting position
                self.data_window.create_rectangle(
                    x_pos, y_start, x_pos + column_widths[j], y_start + row_height,
                    fill="white", outline="#a9a9a9"
                )
                self.data_window.create_text(
                    x_pos + column_widths[j] / 2, y_start + row_height / 2,
                    text=str(round(value, 2)) if j < 3 else value, anchor="center", font=("Sans", 10)
                )

            # Convert LAB to RGB and draw the color rectangle
            rgb_data = tuple(map(lambda x: int(x * 255), color.lab2rgb([lab])[0]))
            hex_color = f'#{rgb_data[0]:02x}{rgb_data[1]:02x}{rgb_data[2]:02x}'
            self.hex_color[hex_color] = lab

            color_x_pos = x_start + sum(column_widths[:4])  # Color column position
            self.data_window.create_rectangle(
                color_x_pos + (column_widths[4] - rect_width) / 2, y_start + (row_height - rect_height) / 2,
                color_x_pos + (column_widths[4] - rect_width) / 2 + rect_width,
                y_start + (row_height - rect_height) / 2 + rect_height,
                fill=hex_color, outline="black"
            )

            # Draw the delete button outside the table
            action_x_pos = x_start + table_width + 20  # Position to the right of the table
            self.data_window.create_text(
                action_x_pos, y_start + row_height / 2,
                text="❌", fill="black", font=("Sans", 10, "bold"), anchor="center",
                tags=(f"delete_{i}",)
            )
            self.data_window.tag_bind(f"delete_{i}", "<Button-1>", lambda event, idx=i: self.remove_color(idx))

            # Move to the next row
            y_start += row_height + 10

        # Adjust the scrollable region of the canvas
        self.data_window.configure(scrollregion=self.data_window.bbox("all"))
        self.data_window.bind("<Configure>", lambda event: self.display_data_window())

            

    def remove_color(self, index):
        """Remove a color at a specific index and refresh the display."""
        if len(self.color_data) <= 2:
            # Ensure at least two colors remain in the dataset
            self.custom_warning("Cannot Remove Color", "At least two colors must remain. The color was not removed.")
            return  
        
        # Get the name of the color to remove using the provided index
        color_name = self.color_matrix[index]
        
        # Check if the color exists in color_data
        if color_name in self.color_data:
            # Iterate over other colors to remove the corresponding negative prototype
            for _, data in self.color_data.items():
                # Filter out the negative prototypes matching the positive prototype of the color being removed
                data["negative_prototypes"] = [
                    prototype for prototype in data["negative_prototypes"]
                    if not np.array_equal(prototype, self.color_data[color_name]["positive_prototype"])
                ]
            
            # Remove the color from color_data
            del self.color_data[color_name]
        
        # Refresh the display and prototypes to reflect the changes
        self.display_data_window()
        self.update_volumes()



    def addColor_data_window(self):
        """Add a new color to the dataset and update the display."""
        if self.COLOR_SPACE:
            # Call `addColor` to get the new color's data
            new_color_data = self.color_data.copy()
            new_color, lab_values = self.addColor(self.inner_frame_data, new_color_data)
            new_color_data = self.color_data.copy()

            # Verify if the user added a valid color
            if new_color and lab_values:
                # Create the data structure for the new color
                positive_prototype = np.array([lab_values["L"], lab_values["A"], lab_values["B"]])
                negative_prototypes = []

                # Gather positive prototypes of other colors to use as negative prototypes for the new color
                for existing_color, data in new_color_data.items():
                    negative_prototypes.append(data["positive_prototype"])

                # Convert the list of negative prototypes into a NumPy array
                negative_prototypes = np.array(negative_prototypes)

                # Add the new color to color_data
                new_color_data[new_color] = {
                    "Color": [lab_values["L"], lab_values["A"], lab_values["B"]],
                    "positive_prototype": positive_prototype,
                    "negative_prototypes": negative_prototypes
                }

                # Add the new color's positive prototype as a negative prototype to other colors
                for existing_color, data in new_color_data.items():
                    if existing_color != new_color:
                        existing_prototypes = data["negative_prototypes"]
                        updated_prototypes = (
                            np.vstack([existing_prototypes, positive_prototype]) 
                            if len(existing_prototypes) > 0 
                            else positive_prototype
                        )
                        new_color_data[existing_color]["negative_prototypes"] = updated_prototypes

                # Update color_data with the new dataset
                self.color_data = new_color_data.copy()

                # Refresh the display and prototypes to include the new color
                self.display_data_window()
                self.update_volumes()



    def apply_changes(self):
        """Applies the changes made to the color list."""
        if not self.file_path:
            self.custom_warning("Error", "No file has been loaded.")
            return

        try:
            # Delete the original file
            if os.path.exists(self.file_path):
                with open(self.file_path, 'w') as f:
                    f.close()
                os.remove(self.file_path)

            # Save the changes in a new file with the same name
            with open(self.file_path, "w", encoding="utf-8") as file:
                color_dict = {key: value['positive_prototype'] for key, value in self.color_data.items()}
                self.save_fcs(self.file_name_entry.get(), self.color_data, color_dict)
        
        except Exception as e:
            self.custom_warning("Error", f"Changes could not be saved: {e}")

        

















    ########################################################################################### Functions Image Display ###########################################################################################
    def save_image(self):
        """Save the currently displayed image for a selected window. If it is a Color Mapping All view, also save a legend image."""
        # Verify we have at least one window to save from
        if not hasattr(self, "load_images_names") or not self.load_images_names:
            self.custom_warning(message="There are currently no images available to save.")
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
                # Close each window
                self.image_canvas.delete(window_id)
                del self.floating_images[window_id]

                if hasattr(self, "proto_options") and window_id in self.proto_options:
                    if self.proto_options[window_id].winfo_exists():
                        self.proto_options[window_id].destroy()
                    del self.proto_options[window_id]

                if hasattr(self, "load_images_names") and window_id in self.load_images_names:
                    del self.load_images_names[window_id]

        # Reset dict
        if hasattr(self, "image_dimensions"):
            self.image_dimensions.clear()
        if hasattr(self, "original_image_dimensions"):
            self.original_image_dimensions.clear()


    
    def open_image(self):
        """Allows the user to select an image file and display its colors in columns with a scrollbar."""
        # Set the initial directory to 'image_test\\' within the current working directory
        initial_directory = BASE_PATH
        initial_directory = os.path.join(BASE_PATH, 'image_test')
        
        # Define the file types that can be selected (e.g., .jpg, .jpeg, .png, .bmp)
        filetypes = [
            ("Image Files", "*.jpg *.jpeg *.png *.bmp *.gif *.tiff"),
            ("All Files", "*.*")
        ]
        
        # Open a file dialog for the user to select an image
        filename = filedialog.askopenfilename(
            title="Select an Image",  # Title of the file dialog
            initialdir=initial_directory,  # Set the initial directory for file selection
            filetypes=filetypes  # Restrict the file selection to the defined filetypes
        )
        
        # If the user selects a file, create a floating window to display the image
        if filename:
            self.create_floating_window(50, 50, filename)



    def create_floating_window(self, x, y, filename):
        """
        Creates a floating window with the selected image, a title bar, and a dropdown menu.
        The window is movable (from title bar only), resizable (bottom-right handle),
        and includes options for displaying the original image and color mapping.
        """

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

        # Generate unique ID
        while True:
            window_id = f"floating_{random.randint(1000, 9999)}"
            if window_id not in self.load_images_names:
                break

        self.load_images_names[window_id] = filename

        # State flags
        self.MEMBERDEGREE[window_id] = bool(self.COLOR_SPACE)
        self.ORIGINAL_IMG[window_id] = False

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

        # Window paddings (same as your layout)
        PAD_X = 30
        PAD_Y = 50
        TITLE_H = 30
        IMG_TOP_PAD = 40
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

        # Image item (IMPORTANT: anchor="nw" to avoid offset weirdness)
        self.image_canvas.create_image(
            x + 15, y + IMG_TOP_PAD,
            anchor="nw",
            image=self.floating_images[window_id],
            tags=(window_id, "floating", f"{window_id}_click_image", f"{window_id}_img_item")
        )

        # Percentage text below the image (hidden by default: empty text)
        self.image_canvas.create_text(
            x + 15,
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
            """Updates all canvas items positions based on stored window state."""
            st = self.floating_window_state[window_id]
            wx, wy, ww, wh = st["x"], st["y"], st["w"], st["h"]

            # Background & title
            self.image_canvas.coords(f"{window_id}_bg", wx, wy, wx + ww + PAD_X, wy + wh + PAD_Y)
            self.image_canvas.coords(f"{window_id}_title", wx, wy, wx + ww + PAD_X, wy + TITLE_H)

            # Title text & arrow
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
                wx + 15, wy + IMG_TOP_PAD
            )

            # Resize handle
            hx1 = wx + ww + PAD_X - HANDLE_SIZE - 2
            hy1 = wy + wh + PAD_Y - HANDLE_SIZE - 2
            hx2 = wx + ww + PAD_X - 2
            hy2 = wy + wh + PAD_Y - 2
            self.image_canvas.coords(f"{window_id}_resize_handle", hx1, hy1, hx2, hy2)

            # Keep on top
            self.image_canvas.tag_raise(window_id)
            self.image_canvas.tag_raise(f"{window_id}_close_button")
            self.image_canvas.tag_raise(f"{window_id}_arrow_button")
            self.image_canvas.tag_raise(f"{window_id}_resize_handle")

            # Reposition proto_options frame if exists
            if hasattr(self, "proto_options") and window_id in self.proto_options:
                proto_option_frame = self.proto_options[window_id]
                if proto_option_frame.winfo_exists():
                    frame_x = wx + ww + PAD_X + 10
                    frame_y = wy

                    canvas_width = self.image_canvas.winfo_width()
                    canvas_height = self.image_canvas.winfo_height()

                    if frame_x + 120 > canvas_width:
                        frame_x = max(0, canvas_width - 120)
                    if frame_y + 150 > canvas_height:
                        frame_y = max(0, canvas_height - 150)

                    proto_option_frame.place(x=frame_x, y=frame_y)
                    proto_option_frame.lift()
            
            # Percentage text below the image
            self.image_canvas.coords(
                f"{window_id}_pct_text",
                wx + 15,
                wy + IMG_TOP_PAD + wh + 10
            )
            self.image_canvas.tag_raise(f"{window_id}_pct_text")


        def _update_image_to_size(window_id, target_w, target_h):
            """
            Resizes the displayed image to fit within target_w/target_h keeping aspect ratio,
            updates PhotoImage reference, and refreshes layout.
            """
            pil_original = self.pil_images_original[window_id]
            ow, oh = pil_original.size

            # Keep aspect ratio (fit)
            scale = min(target_w / ow, target_h / oh)
            new_w = max(30, int(ow * scale))  # Min size to avoid collapsing
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
        # Close window
        # ---------------------------
        def close_window(event):
            """Closes the floating window and removes all associated elements."""
            self.image_canvas.delete(window_id)

            if window_id in self.floating_images:
                del self.floating_images[window_id]
            if hasattr(self, "pil_images_original") and window_id in self.pil_images_original:
                del self.pil_images_original[window_id]
            if hasattr(self, "floating_window_state") and window_id in self.floating_window_state:
                del self.floating_window_state[window_id]

            if hasattr(self, "proto_options") and window_id in self.proto_options:
                if self.proto_options[window_id].winfo_exists():
                    self.proto_options[window_id].destroy()
                del self.proto_options[window_id]

            if hasattr(self, "load_images_names") and window_id in self.load_images_names:
                del self.load_images_names[window_id]

        # ---------------------------
        # Dropdown menu
        # ---------------------------
        def show_menu_image(event):
            """Displays a context menu with options for the floating window."""
            menu = Menu(self.root, tearoff=0)
            menu.add_command(
                label="Original Image",
                state=NORMAL if self.ORIGINAL_IMG[window_id] else DISABLED,
                command=lambda: self.show_original_image(window_id)
            )
            menu.add_separator()
            menu.add_command(
                label="Color Mapping",
                state=NORMAL if self.MEMBERDEGREE[window_id] else DISABLED,
                command=lambda: self.color_mapping(window_id)
            )
            menu.add_separator()
            menu.add_command(
                label="Color Mapping All",
                state=NORMAL if self.MEMBERDEGREE[window_id] else DISABLED,
                command=lambda: self.color_mapping_all(window_id)
            )
            menu.post(event.x_root, event.y_root)

        # ---------------------------
        # Move window (TITLE BAR ONLY)
        # ---------------------------
        def start_move(event):
            """Stores the initial position when the mouse is pressed on the title bar."""
            self.last_x, self.last_y = event.x, event.y

        def move_window(event):
            """Moves the floating window based on the mouse drag (title bar only)."""
            dx, dy = event.x - self.last_x, event.y - self.last_y

            # Update stored position
            st = self.floating_window_state[window_id]
            st["x"] += dx
            st["y"] += dy

            _relayout(window_id)
            self.last_x, self.last_y = event.x, event.y

        # ---------------------------
        # Resize window
        # ---------------------------
        def start_resize(event):
            """Stores initial state for resizing using the bottom-right handle."""
            st = self.floating_window_state[window_id]
            self._resize_start = {
                "w": st["w"], "h": st["h"],
                "mx": self.image_canvas.canvasx(event.x),
                "my": self.image_canvas.canvasy(event.y)
            }

        def do_resize(event):
            """Resizes window while dragging the bottom-right handle."""
            if not hasattr(self, "_resize_start") or self._resize_start is None:
                return "break"

            mx = self.image_canvas.canvasx(event.x)
            my = self.image_canvas.canvasy(event.y)

            start = self._resize_start
            dw = mx - start["mx"]
            dh = my - start["my"]

            # Desired size (image area), before aspect correction
            desired_w = max(30, int(start["w"] + dw))
            desired_h = max(30, int(start["h"] + dh))

            _update_image_to_size(window_id, desired_w, desired_h)
            return "break"

        def end_resize(event):
            """Ends resizing operation."""
            self._resize_start = None

            # Clear cached results for this window when resizing ends (avoid cache growth)
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

        # Store resize callbacks so they can be re-bound later (e.g., after color mapping)
        if not hasattr(self, "_resize_callbacks"):
            self._resize_callbacks = {}
        self._resize_callbacks[window_id] = (start_resize, do_resize, end_resize)

        # ---------------------------
        # Pixel picking (ANCHOR NW)
        # ---------------------------
        def get_pixel_value(event, window_id=window_id):
            """Gets the pixel value where the image is clicked, considering window movement and resizing."""
            pil_original = self.pil_images_original[window_id]
            ow, oh = pil_original.size

            resized_w, resized_h = self.image_dimensions[window_id]
            if resized_w <= 0 or resized_h <= 0:
                return "break"

            abs_x = self.image_canvas.canvasx(event.x)
            abs_y = self.image_canvas.canvasy(event.y)

            # Top-left corner of the displayed image (anchor="nw")
            st = self.floating_window_state[window_id]
            img_left = st["x"] + 15
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
                self.display_pixel_value(x_original, y_original, pixel_lab)

            return "break"

        # ---------------------------
        # Bindings
        # ---------------------------
        # Move only from title bar (NOT from whole window)
        self.image_canvas.tag_bind(f"{window_id}_title", "<Button-1>", start_move)
        self.image_canvas.tag_bind(f"{window_id}_title", "<B1-Motion>", move_window)
        self.image_canvas.tag_bind(f"{window_id}_title_text", "<Button-1>", start_move)
        self.image_canvas.tag_bind(f"{window_id}_title_text", "<B1-Motion>", move_window)

        # Close / menu / click
        self.image_canvas.tag_bind(f"{window_id}_close_button", "<Button-1>", close_window)
        self.image_canvas.tag_bind(f"{window_id}_click_image", "<Button-1>", get_pixel_value)
        self.image_canvas.tag_bind(f"{window_id}_arrow_button", "<Button-1>", show_menu_image)

        # Resize handle bindings
        self.image_canvas.tag_bind(f"{window_id}_resize_handle", "<Button-1>", start_resize)
        self.image_canvas.tag_bind(f"{window_id}_resize_handle", "<B1-Motion>", do_resize)
        self.image_canvas.tag_bind(f"{window_id}_resize_handle", "<ButtonRelease-1>", end_resize)

        # Initial relayout to ensure everything consistent
        _relayout(window_id)









    def show_more_info(self):
        """Shows detailed information about the last clicked pixel in a 2-column popup (membership vs ΔE00)."""
        info = getattr(self, "_last_pixel_info", None)
        if not info:
            messagebox.showinfo("More Info", "Click on an image pixel first.")
            return

        win = tk.Toplevel(self.root)
        win.title("More Info")

        # Fixed initial size (prevents the right column from collapsing)
        WIN_W, WIN_H = 640, 320
        win.geometry(f"{WIN_W}x{WIN_H}")
        win.resizable(False, False)

        # Grid: left | separator | right
        win.grid_rowconfigure(0, weight=1)
        win.grid_columnconfigure(0, weight=1, minsize=380)  # left min width
        win.grid_columnconfigure(1, weight=0)               # separator
        win.grid_columnconfigure(2, weight=1, minsize=240)  # right min width

        left = tk.Frame(win, padx=12, pady=10)
        left.grid(row=0, column=0, sticky="nsew")

        separator = tk.Frame(win, width=1, bg="#b0b0b0")
        separator.grid(row=0, column=1, sticky="ns", padx=6)

        right = tk.Frame(win, padx=12, pady=10)
        right.grid(row=0, column=2, sticky="nsew")

        # Header (bottom)
        header = tk.Frame(win, padx=12, pady=8)
        header.grid(row=1, column=0, columnspan=3, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        lab = info["lab"]
        header_label = tk.Label(
            header,
            text=f"Coordinates: ({info['x']}, {info['y']})    |    LAB: {lab[0]:.2f}, {lab[1]:.2f}, {lab[2]:.2f}",
            anchor="w"
        )
        header_label.grid(row=0, column=0, sticky="ew")

        # ---------------------------
        # Left: Membership
        # ---------------------------
        tk.Label(left, text="Membership Degree (μ)", font=("Sans", 11, "bold"), anchor="w").pack(fill="x")

        winner_label = info.get("winner_label", "None")
        winner_mu = float(info.get("winner_mu", 0.0))
        tk.Label(left, text=f"Winner: {winner_label}  |  μ = {winner_mu:.4f}", anchor="w").pack(fill="x", pady=(6, 0))

        tk.Label(left, text="Legend (μ thresholds):", font=("Sans", 10, "bold"), anchor="w").pack(fill="x", pady=(10, 0))
        tk.Label(
            left,
            text="Green   :        μ ≥ 0.80\nOrange :   0.50 ≤ μ < 0.80\nRed       :        μ < 0.50",
            justify="left",
            anchor="w"
        ).pack(fill="x")

        top_memberships = info.get("top_memberships", [])
        tk.Label(left, text="Top memberships:", font=("Sans", 10, "bold"), anchor="w").pack(fill="x", pady=(10, 0))

        # Use wrap="word" so it doesn't force horizontal expansion/cropping
        txt = tk.Text(left, height=6, wrap="word")
        txt.pack(fill="x", expand=False, pady=(4, 0))

        if top_memberships:
            for lbl, mu in top_memberships:
                txt.insert("end", f"- {lbl}: {float(mu):.4f}\n")
        else:
            txt.insert("end", "No memberships available.\n")
        txt.config(state="disabled")

        # ---------------------------
        # Right: CIEDE2000
        # ---------------------------
        tk.Label(right, text="CIEDE2000 (ΔE00)", font=("Sans", 11, "bold"), anchor="w").pack(fill="x")

        delta_e = info.get("delta_e", None)
        if delta_e is None:
            tk.Label(
                right,
                text="ΔE00: not available for this pixel/prototype.",
                anchor="w",
                justify="left",
                wraplength=220  # force wrapping inside the right panel
            ).pack(fill="x", pady=(6, 0))
        else:
            tk.Label(
                right,
                text=f"ΔE00 (vs positive prototype): {float(delta_e):.3f}",
                anchor="w",
                wraplength=220
            ).pack(fill="x", pady=(6, 0))

            tk.Label(right, text="Legend (ΔE00 thresholds):", font=("Sans", 10, "bold"), anchor="w").pack(fill="x", pady=(10, 0))
            tk.Label(
                right,
                text="PT  :      ΔE ≤ 0.8\nAT  :   0.8 < ΔE ≤ 1.8\n∅    :      ΔE > 1.8",
                justify="left",
                anchor="w",
                wraplength=220
            ).pack(fill="x")

        # Buttons
        btns = tk.Frame(win, padx=12, pady=10)
        btns.grid(row=2, column=0, columnspan=3, sticky="e")
        tk.Button(btns, text="Close", command=win.destroy).pack()

        # Modal-ish behavior
        win.transient(self.root)
        win.grab_set()
        win.focus_set()

        # Center over root (same screen)
        win.update_idletasks()
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()

        x = root_x + (root_w - WIN_W) // 2
        y = root_y + (root_h - WIN_H) // 2
        win.geometry(f"{WIN_W}x{WIN_H}+{x}+{y}")





    def display_pixel_value(self, x_original, y_original, pixel_lab):
        """
        Displays the pixel value in LAB format and its coordinates within a frame at the bottom of the canvas.
        Shows the closest prototype, its membership degree, and colors the text using membership (μ) thresholds.
        Also computes ΔE00 (CIEDE2000) and includes it in the text + stores detailed info for "More Info".
        """
        # Create the frame and labels only once if they don't exist
        if not hasattr(self, "lab_value_frame"):
            self.lab_value_frame = tk.Frame(self.Canvas1, bg="lightgray")
            self.lab_value_frame.place(relx=0.5, rely=0.97, anchor="s")

            # Frame for left-aligned text
            text_frame = tk.Frame(self.lab_value_frame, bg="lightgray")
            text_frame.pack(side="left", padx=10, pady=5, fill="x")

            # Define fonts for labels
            bold_font = ("Sans", 12, "bold")
            normal_font = ("Sans", 12)

            # Coordinates label and value
            coord_label = tk.Label(text_frame, text="Coordinates: ", font=bold_font, bg="lightgray")
            coord_label.pack(side="left")
            self.coord_value = tk.Label(text_frame, text="", font=normal_font, bg="lightgray")
            self.coord_value.pack(side="left")

            # LAB values label and value
            lab_label = tk.Label(text_frame, text="LAB: ", font=bold_font, bg="lightgray")
            lab_label.pack(side="left")
            self.lab_value_print = tk.Label(text_frame, text="", font=normal_font, bg="lightgray")
            self.lab_value_print.pack(side="left")

            # FC label and value
            proto_label = tk.Label(text_frame, text="Fuzzy Color: ", font=bold_font, bg="lightgray")
            proto_label.pack(side="left")

            self.proto_value_text = tk.Label(text_frame, text="", font=normal_font, bg="lightgray")
            self.proto_value_text.pack(side="left")

            self.proto_value_symbol = tk.Label(
                text_frame,
                text="",
                font=("Sans", 20, "bold"),  # BIG symbol
                bg="lightgray"
            )
            self.proto_value_symbol.pack(side="left", padx=(2, 0))

            # "More Info" button
            more_info_button = tk.Button(
                self.lab_value_frame, text="🔍", font=("Sans", 9),
                bg="white", command=self.show_more_info, relief="flat", borderwidth=0
            )
            more_info_button.pack(side="right", padx=5, pady=2)

        # ---------------------------
        # Membership computation
        # ---------------------------
        membership_degrees = self.fuzzy_color_space.calculate_membership(pixel_lab)

        if membership_degrees:
            max_proto = max(membership_degrees, key=membership_degrees.get)
            winner_mu = float(membership_degrees[max_proto])

            # Top-k memberships for the "More Info" popup
            top_memberships = sorted(membership_degrees.items(), key=lambda kv: kv[1], reverse=True)[:5]
        else:
            max_proto = None
            winner_mu = 0.0
            top_memberships = []

        # ---------------------------
        # ΔE00 computation (CIEDE2000)
        # ---------------------------
        delta_e = None
        if max_proto is not None:
            try:
                positive = self.color_data[max_proto]["positive_prototype"]
                delta_e = float(self.color_manager.delta_e_ciede2000(positive, pixel_lab))
            except Exception:
                delta_e = None

        # ---------------------------
        # Color by membership (μ) confidence (recommended)
        # ---------------------------
        if max_proto is None:
            c = "black"
            mu_class = "none"
        else:
            if winner_mu >= 0.80:
                c = "green"
                mu_class = "high"
            elif winner_mu >= 0.50:
                c = "orange"
                mu_class = "medium"
            else:
                c = "red"
                mu_class = "low"

        # ---------------------------
        # Store last click info for "More Info"
        # ---------------------------
        self._last_pixel_info = {
            "x": x_original,
            "y": y_original,
            "lab": pixel_lab,

            # Membership info
            "winner_label": max_proto if max_proto is not None else "None",
            "winner_mu": winner_mu,
            "mu_class": mu_class,
            "top_memberships": top_memberships,
            "mu_thresholds": {"green": 0.80, "orange": 0.50},  # green>=0.80, orange>=0.50, else red

            # CIEDE2000 info
            "delta_e": delta_e,
            "delta_e_thresholds": {"green": 0.8, "orange": 1.8},
        }

        # Classify ΔE00 into short categories (for compact UI)
        if delta_e is None:
            de_class = "—"   # no value / not available
        elif delta_e <= 0.8:
            de_class = "PT"  # perceptually tolerable / very close
        elif delta_e <= 1.8:
            de_class = "AT"  # acceptable tolerance / close
        else:
            de_class = "∅" # far


        # ---------------------------
        # Build text (μ + ΔE00)
        # ---------------------------
        if max_proto is None:
            proto_text = "—"
        else:
            proto_text = f"{max_proto} | {de_class}"

        # ---------------------------
        # Update UI
        # ---------------------------
        self.coord_value.config(text=f"({x_original}, {y_original})    |    ")
        self.lab_value_print.config(text=f"{pixel_lab[0]:.2f}, {pixel_lab[1]:.2f}, {pixel_lab[2]:.2f}    |    ")
        
        if max_proto is None:
            self.proto_value_text.config(text="—", fg=c)
            self.proto_value_symbol.config(text="")
        else:
            self.proto_value_text.config(text=f"{max_proto}  |", fg=c)

            # Bigger symbol only
            if de_class == "∅":
                self.proto_value_symbol.config(text=de_class, fg=c)
            else:
                # PT / AT / Far → normal size, keep it in text
                self.proto_value_text.config(text=f"{max_proto}  |  {de_class}", fg=c)
                self.proto_value_symbol.config(text="")














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



    def display_detected_colors(self, colors, threshold, min_samples):
        """
        Displays a popup window showing the detected colors with options to adjust the threshold,
        recalculate, add new image colors, and create a fuzzy color space.
        """
        # Create a popup window
        popup = tk.Toplevel(self.root)
        popup.title("Detected Colors")
        popup.configure(bg="#f5f5f5")

        # Center the popup window
        self.center_popup(popup, 500, 600)

        # Function to handle window closing
        def on_closing():
            """Clears the color entry dictionary when the window is closed."""
            self.color_entry_detect.clear()  # Reset the entry dictionary
            popup.destroy()  # Close the window

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
            command=lambda: [self.get_fcs_image_recalculate(colors, threshold, min_samples, popup), popup.destroy()],
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
                lab = color.rgb2lab(np.array(dect_color["rgb"], dtype=np.uint8).reshape(1, 1, 3) / 255)
                default_name = f"Color {i + 1}"  # Default name

                frame = ttk.Frame(scrollable_frame)
                frame.pack(fill="x", pady=8, padx=10)

                # Color preview
                color_box = tk.Label(frame, bg=UtilsTools.rgb_to_hex(rgb), width=4, height=2, relief="solid", bd=1)
                color_box.pack(side="left", padx=10)

                # Retrieve the saved name or use the default
                entry_name_key = f"color_{i}"
                saved_name = previous_names.get(entry_name_key, default_name)

                # Entry field for the color name
                entry = ttk.Entry(frame, font=("Helvetica", 12))
                entry.insert(0, saved_name)  # Insert the saved or default name
                entry.pack(side="left", padx=10, fill="x", expand=True)
                self.color_entry_detect[entry_name_key] = entry

                # LAB values
                lab = lab[0, 0]
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

        # Action buttons
        button_frame = ttk.Frame(popup)
        button_frame.pack(pady=20)

        add_colors_button = ttk.Button(
            button_frame,
            text="Add New Image Colors",
            command=lambda: self.add_new_image_colors(popup, colors, threshold, min_samples),
            style="Accent.TButton"
        )
        add_colors_button.pack(side="left", padx=10)

        # --- New "Add New Color" button inserted here ---
        add_single_color_button = ttk.Button(
            button_frame,
            text="Add Color",
            command=lambda: self.addColor_to_image(popup, colors, update_color_frames),
            style="Accent.TButton"
        )
        add_single_color_button.pack(side="left", padx=10)

        save_button = ttk.Button(
            button_frame,
            text="Create Fuzzy Color Space",
            command=lambda: [self.process_fcs(colors), popup.destroy()],
            style="Accent.TButton"
        )
        save_button.pack(side="left", padx=10)

        # Style for buttons
        style = ttk.Style()
        style.configure("Accent.TButton", font=("Helvetica", 8, "bold"), padding=10)



    def process_fcs(self, colors):
        """
        Saves the names of the colors edited by the user in a file with a .cns extension.
        Prompts the user to enter a name for the fuzzy color space and validates the input.
        """
        # Ensure at least two colors are selected
        if len(self.color_entry_detect) < 2:
            self.custom_warning("Not Enough Colors", "At least two colors must be selected to create the Color Space.")
            return

        # Create a popup window for the user to name the color space
        popup = tk.Toplevel(self.root)
        popup.title("Input")
        self.center_popup(popup, 300, 100)

        # Add a label and entry field for the color space name
        tk.Label(popup, text="Name for the fuzzy color space:").pack(pady=5)
        name_entry = tk.Entry(popup)
        name_entry.pack(pady=5)

        # Variable to store the entered name
        name = tk.StringVar()

        def on_ok():
            """Callback function for the OK button."""
            name.set(name_entry.get())  # Set the value in the StringVar
            popup.destroy()  # Close the popup window
            self.save_fcs(name.get(), colors)  # Save the color space

        # Add an OK button to confirm the name
        ok_button = tk.Button(popup, text="OK", command=on_ok)
        ok_button.pack(pady=5)

        # Display the popup window
        popup.deiconify()


    def save_fcs(self, name, colors, color_dict=None):
        """
        Saves the fuzzy color space to a file with the given name and color data.
        Displays a loading indicator and updates the progress bar during the save process.
        """
        # If no color_dict is provided, create one from the detected colors
        if color_dict is None:
            color_dict = {key: np.array(colors[idx]['lab']) for idx, key in enumerate(self.color_entry_detect)}
            self.color_entry_detect.clear()

        # Show loading indicator
        self.show_loading()

        def update_progress(current_line, total_lines):
            """
            Updates the progress bar based on the number of lines written.
            """
            progress_percentage = (current_line / total_lines) * 100
            self.progress["value"] = progress_percentage
            self.load_window.update_idletasks()  # Refresh the UI

        def run_save_process():
            """
            Saves the file in a separate thread to avoid blocking the main UI.
            Handles exceptions and ensures the loading indicator is hidden afterward.
            """
            try:
                # Initialize the input class for .fcs files
                input_class = Input.instance('.fcs')
                # Write the file with the provided name, color data, and progress callback
                input_class.write_file(name, color_dict, progress_callback=update_progress)
            except Exception as e:
                # Show an error message if something goes wrong
                self.custom_warning("Error", f"An error occurred while saving: {e}")
            finally:
                # Hide the loading indicator and show a success message
                self.load_window.after(0, self.hide_loading)
                self.load_window.after(0, lambda: messagebox.showinfo(
                    "Color Space Created", f"Color Space '{name}' created successfully."
                ))

        # Start the save process in a separate thread
        threading.Thread(target=run_save_process, daemon=True).start()


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



    def get_fcs_image_recalculate(self, colors, threshold=0.5, min_samples=160, popup = None):
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
                message=f"No colors were detected under this configuration. The last version will be reloaded"
            )
            self.get_fcs_image(self.last_window_id, threshold, min_samples)


        else:
            # If there is only one image, recalculate its colors directly
            window_id = unique_ids.pop() if unique_ids else None

            self.get_fcs_image(window_id, threshold, min_samples)
            popup.destroy()


    def _get_or_compute_label_map(self, window_id, source_img, progress_callback=None):
        """
        Returns a cached label_map for this window_id if available and valid for current prototypes.
        Otherwise computes it once, caches it, and returns it.

        label_map contains the winning prototype index per pixel (uint16) for the ORIGINAL image size.
        """
        if not hasattr(self, "cm_cache"):
            self.cm_cache = {}

        # Cache validity check: must match current prototypes set/order and image size
        proto_labels = tuple([p.label for p in self.prototypes])

        cached = self.cm_cache.get(window_id)
        if cached is not None:
            if cached.get("proto_labels") == proto_labels and cached.get("shape") == source_img.size[::-1]:
                return cached["label_map"]

        # Compute new label_map
        self.fuzzy_color_space.precompute_pack()

        img_np = np.array(source_img)
        if img_np.ndim == 3 and img_np.shape[-1] == 4:
            img_np = img_np[..., :3]
        img_np = img_np / 255.0

        lab_img = color.rgb2lab(img_np)
        lab_q = np.round(lab_img, 2)  # 0.01 precision

        height, width = lab_q.shape[0], lab_q.shape[1]
        total_pixels = height * width

        # Map prototype label -> index
        proto_index = {p.label: i for i, p in enumerate(self.prototypes)}

        # Output: winning prototype index per pixel
        label_map = np.zeros((height, width), dtype=np.uint16)

        membership_cache = {}  # key (L,a,b int*100) -> best_index
        processed_pixels = 0
        last_update = time.perf_counter()

        for y in range(height):
            for x in range(width):
                lab_color = lab_q[y, x]
                key = (int(lab_color[0] * 100), int(lab_color[1] * 100), int(lab_color[2] * 100))

                best_idx = membership_cache.get(key)
                if best_idx is None and key not in membership_cache:
                    degrees = self.fuzzy_color_space.calculate_membership(lab_color)
                    if degrees:
                        best_label = max(degrees, key=degrees.get)
                        best_idx = proto_index.get(best_label, 0)
                    else:
                        best_idx = 0
                    membership_cache[key] = best_idx

                label_map[y, x] = best_idx

                processed_pixels += 1
                if progress_callback:
                    now = time.perf_counter()
                    if now - last_update > 0.03 or processed_pixels == total_pixels:
                        progress_callback(processed_pixels, total_pixels)
                        last_update = now

        # Cache it
        self.cm_cache[window_id] = {
            "label_map": label_map,
            "shape": (height, width),
            "proto_labels": proto_labels
        }

        return label_map



    def color_mapping(self, window_id):
        # if window exist
        items = self.image_canvas.find_withtag(window_id)
        if not items:
            self.custom_warning("No Window", f"No floating window found with id {window_id}")
            return
        
        # Disable resizing: remove the resize handle and its bindings
        try:
            # Delete handle shape from canvas
            self.image_canvas.delete(f"{window_id}_resize_handle")

            # Unbind resize events (safe even if not bound)
            self.image_canvas.tag_unbind(f"{window_id}_resize_handle", "<Button-1>")
            self.image_canvas.tag_unbind(f"{window_id}_resize_handle", "<B1-Motion>")
            self.image_canvas.tag_unbind(f"{window_id}_resize_handle", "<ButtonRelease-1>")
        except Exception:
            # If something goes wrong, do not break the mapping process
            pass

        self.MEMBERDEGREE[window_id] = False
        self.ORIGINAL_IMG[window_id] = True

        if not hasattr(self, "proto_options"):
            self.proto_options = {}

        if window_id in self.proto_options and self.proto_options[window_id].winfo_exists():
            self.proto_options[window_id].destroy()

        proto_options = tk.Frame(self.image_canvas, bg="white", relief="solid", bd=1)
        self.proto_options[window_id] = proto_options

        canvas = tk.Canvas(proto_options, bg="white", highlightthickness=0)
        v_scroll = tk.Scrollbar(proto_options, orient=tk.VERTICAL, command=canvas.yview)
        h_scroll = tk.Scrollbar(proto_options, orient=tk.HORIZONTAL, command=canvas.xview)

        canvas.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        canvas.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")

        inner_frame = tk.Frame(canvas, bg="white")
        canvas_window = canvas.create_window((0, 0), window=inner_frame, anchor="nw", tags="inner")

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
            canvas.itemconfig("inner", width=event.width)

        canvas.bind("<Configure>", resize_inner)

        def on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner_frame.bind("<Configure>", lambda e: canvas.after_idle(on_frame_configure, e))

        # Mouse control
        def _on_mouse_wheel(event):
            if event.delta:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            elif event.num == 4:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                canvas.yview_scroll(1, "units")

        # correct scroll
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

        x1, y1, x2, y2 = self.image_canvas.bbox(items[0])
        frame_x = x2 + 10
        frame_y = y1
        proto_options.place(x=frame_x, y=frame_y, width=100, height=300)



    def get_proto_percentage(self, window_id):
        """Generates and displays the grayscale mask and shows coverage % under the image (cached by size)."""
        self.show_loading()

        def update_progress(current_step, total_steps):
            progress_percentage = (current_step / total_steps) * 100
            self.progress["value"] = progress_percentage
            self.load_window.update_idletasks()

        def run_process():
            try:
                pos = self.color_matrix.index(self.current_protos[window_id].get())

                if not hasattr(self, "proto_percentage_cache"):
                    self.proto_percentage_cache = {}
                if window_id not in self.proto_percentage_cache:
                    self.proto_percentage_cache[window_id] = {}

                # IMPORTANT: compute on CURRENT displayed image so resizing changes the result
                if not hasattr(self, "images") or window_id not in self.images:
                    self.image_canvas.after(0, lambda: self.custom_warning("Error", "Current image not found for this window."))
                    return

                source_img = self.images[window_id]
                w, h = source_img.size
                cache_key = (pos, w, h)

                cached_entry = self.proto_percentage_cache[window_id].get(cache_key)
                if cached_entry is not None:
                    grayscale_image_array = cached_entry["array"]
                    pct = cached_entry["pct"]
                else:
                    grayscale_image_array = self.image_manager.get_proto_percentage(
                        prototypes=self.prototypes,
                        image=source_img,  # <-- CURRENT size
                        fuzzy_color_space=self.fuzzy_color_space,
                        selected_option=pos,
                        progress_callback=update_progress
                    )

                    # Auto-threshold decision
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
                    self.display_color_mapping(grayscale_image_array, window_id)

                    proto_name = self.current_protos[window_id].get()
                    txt = f"{proto_name}: {pct:.2f}%"
                    self.image_canvas.itemconfig(f"{window_id}_pct_text", text=txt)
                    self.image_canvas.tag_raise(f"{window_id}_pct_text")

                self.image_canvas.after(0, _ui)

            except Exception as e:
                self.image_canvas.after(0, lambda: self.custom_warning("Error", f"Error in run_process: {e}"))
            finally:
                self.image_canvas.after(0, self.hide_loading)

        threading.Thread(target=run_process, daemon=True).start()








    def display_color_mapping(self, grayscale_image_array, window_id):
        """Displays the generated grayscale image in the graphical interface (resized only for display)."""
        try:
            # Store the ORIGINAL result (do not store the resized display version)
            self.modified_image[window_id] = grayscale_image_array

            # Convert numpy array to PIL image with the correct mode
            if grayscale_image_array.ndim == 2:
                # 2D array -> grayscale image
                grayscale_image = Image.fromarray(grayscale_image_array.astype(np.uint8), mode="L")
            else:
                # 3D array (e.g., RGB) -> let PIL infer
                grayscale_image = Image.fromarray(grayscale_image_array.astype(np.uint8))

            # Resize ONLY for display to match the current window dimensions
            new_width, new_height = self.image_dimensions[window_id]
            grayscale_image_display = grayscale_image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Store the exact PIL image that is currently displayed (for saving)
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
            # Hide percentage text when showing original image (always)
            try:
                self.image_canvas.itemconfig(f"{window_id}_pct_text", text="")
            except Exception:
                pass

            # Destroy proto_options if it exists (keeps UI consistent)
            if hasattr(self, "proto_options") and window_id in self.proto_options:
                try:
                    if self.proto_options[window_id].winfo_exists():
                        self.proto_options[window_id].destroy()
                    del self.proto_options[window_id]
                except Exception as e:
                    self.custom_warning("Window Error", f"Error trying to destroy the proto_options window: {e}")
                    return

            # Ensure we have the original PIL image stored
            if not hasattr(self, "pil_images_original") or window_id not in self.pil_images_original:
                self.custom_warning("Not Original Image", f"Original PIL image not found for window_id: {window_id}")
                return

            pil_original = self.pil_images_original[window_id]

            # Preserve the current displayed size (if resized)
            if hasattr(self, "image_dimensions") and window_id in self.image_dimensions:
                target_w, target_h = self.image_dimensions[window_id]
            else:
                target_w, target_h = pil_original.size

            target_w = max(1, int(target_w))
            target_h = max(1, int(target_h))

            # Resize the original PIL image to the current window size
            pil_resized = pil_original.resize((target_w, target_h), Image.Resampling.LANCZOS)

            # Update the "current displayed" PIL image too (important for your logic)
            if hasattr(self, "images"):
                self.images[window_id] = pil_resized

            # Source of truth for saving: ensure dict exists and update it
            if not hasattr(self, "display_pil"):
                self.display_pil = {}
            self.display_pil[window_id] = pil_resized

            # Create a new PhotoImage with the preserved size
            img_tk = ImageTk.PhotoImage(pil_resized)

            # Keep a reference to avoid garbage collection
            if not hasattr(self, "floating_images"):
                self.floating_images = {}
            self.floating_images[window_id] = img_tk

            # Refresh original_images cache to the "current size"
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
            self.ORIGINAL_IMG[window_id] = False
            if self.COLOR_SPACE:
                self.MEMBERDEGREE[window_id] = True

            # ---------------------------
            # Re-enable resize handle
            # ---------------------------
            try:
                if not hasattr(self, "floating_window_state") or window_id not in self.floating_window_state:
                    return

                st = self.floating_window_state[window_id]
                wx, wy = st["x"], st["y"]

                # Sync stored size with the actual displayed size
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

                # Rebind resize events (requires callbacks stored from create_floating_window)
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
        """Applies color mapping to the CURRENT (resized) image and updates the floating window with a progress bar."""

        items = self.image_canvas.find_withtag(window_id)
        if not items:
            self.custom_warning("No Window", f"No floating window found with id {window_id}")
            return

        # Disable resizing: remove the resize handle and its bindings
        try:
            self.image_canvas.delete(f"{window_id}_resize_handle")
            self.image_canvas.tag_unbind(f"{window_id}_resize_handle", "<Button-1>")
            self.image_canvas.tag_unbind(f"{window_id}_resize_handle", "<B1-Motion>")
            self.image_canvas.tag_unbind(f"{window_id}_resize_handle", "<ButtonRelease-1>")
        except Exception:
            pass

        # Hide proto-percentage text for "all" (optional; remove if you want to show something else)
        try:
            self.image_canvas.itemconfig(f"{window_id}_pct_text", text="")
        except Exception:
            pass

        self.MEMBERDEGREE[window_id] = False
        self.ORIGINAL_IMG[window_id] = True

        self.proto_options = getattr(self, "proto_options", {})
        legend_frame = self.proto_options.pop(window_id, None)
        if legend_frame and legend_frame.winfo_exists():
            legend_frame.destroy()

        self.show_loading()

        def update_progress(current_step, total_steps):
            """Update the progress bar."""
            self.progress["value"] = (current_step / total_steps) * 100
            self.load_window.update_idletasks()

        def build_legend_frame(prototypes, parent_canvas):
            """Creates and returns the legend frame (no heavy computation)."""
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

            def on_frame_configure(event):
                canvas.configure(scrollregion=canvas.bbox("all"))

            inner_frame.bind("<Configure>", lambda e: canvas.after_idle(on_frame_configure, e))

            # Scroll wheel handling
            def bind_scroll_events(c):
                def _on_mousewheel(event):
                    c.yview_scroll(int(-1 * (event.delta / 120)), "units")
                def _bind_mousewheel(event):
                    c.bind_all("<MouseWheel>", _on_mousewheel)
                def _unbind_mousewheel(event):
                    c.unbind_all("<MouseWheel>")
                c.bind("<Enter>", _bind_mousewheel)
                c.bind("<Leave>", _unbind_mousewheel)

            bind_scroll_events(canvas)

            # Palette logic
            color_map = plt.get_cmap('hsv', len(prototypes))
            prototype_colors = {p.label: color_map(i)[:3] for i, p in enumerate(prototypes)}
            for label in prototype_colors:
                if label.lower() == "black":
                    prototype_colors[label] = (0, 0, 0)

            # Labels
            for prototype in prototypes:
                color_rgb = np.array(prototype_colors[prototype.label]) * 255
                color_hex = "#{:02x}{:02x}{:02x}".format(int(color_rgb[0]), int(color_rgb[1]), int(color_rgb[2]))
                label = tk.Label(
                    inner_frame, text=prototype.label, bg=color_hex,
                    fg="black" if np.mean(color_rgb) > 128 else "white",
                    padx=5, pady=2
                )
                label.pack(fill="x", padx=5, pady=2)

            inner_frame.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))

            # Save both color sets
            original_colors = [np.array(prototype_colors[proto.label]) * 255 for proto in self.prototypes]
            hex_colors = list(self.hex_color.keys())
            alt_colors = [
                np.array([int(hex_colors[i][j:j+2], 16) for j in (1, 3, 5)])
                for i, _ in enumerate(self.prototypes)
            ]

            if not hasattr(self, "prototype_color_sets"):
                self.prototype_color_sets = {}
            if not hasattr(self, "current_color_scheme"):
                self.current_color_scheme = {}

            self.prototype_color_sets[window_id] = {"original": original_colors, "alt": alt_colors}
            self.current_color_scheme[window_id] = "original"

            return legend_frame, prototype_colors

        def run_process():
            """Run the processing in a separate thread (CURRENT resized image)."""
            try:
                # IMPORTANT: use the current resized image so resizing requires recomputation
                if not hasattr(self, "images") or window_id not in self.images:
                    self.image_canvas.after(0, lambda: self.custom_warning("Processing Error", "Current image not found for this window."))
                    return

                source_img = self.images[window_id]  # <-- CURRENT size
                w, h = source_img.size

                # Ensure cm_cache exists
                if not hasattr(self, "cm_cache"):
                    self.cm_cache = {}
                if window_id not in self.cm_cache:
                    self.cm_cache[window_id] = {}

                # Cache key depends on image size + prototypes (so resize forces recompute)
                proto_labels = tuple([p.label for p in self.prototypes])
                cache_key = (w, h, proto_labels)

                # Get or compute label_map
                label_map = self.cm_cache[window_id].get(cache_key)
                if label_map is None:
                    # Compute label_map (winner prototype index per pixel) for CURRENT image
                    self.fuzzy_color_space.precompute_pack()

                    img_np = np.array(source_img)
                    if img_np.ndim == 3 and img_np.shape[-1] == 4:
                        img_np = img_np[..., :3]
                    img_np = img_np / 255.0

                    lab_img = color.rgb2lab(img_np)
                    lab_q = np.round(lab_img, 2)

                    height, width = lab_q.shape[0], lab_q.shape[1]
                    total_pixels = height * width

                    proto_index = {p.label: i for i, p in enumerate(self.prototypes)}
                    label_map = np.zeros((height, width), dtype=np.uint16)

                    membership_cache = {}  # (L,a,b int*100) -> best_idx
                    processed_pixels = 0
                    last_update = time.perf_counter()

                    for yy in range(height):
                        for xx in range(width):
                            lab_color = lab_q[yy, xx]
                            key = (int(lab_color[0] * 100), int(lab_color[1] * 100), int(lab_color[2] * 100))

                            best_idx = membership_cache.get(key)
                            if best_idx is None and key not in membership_cache:
                                degrees = self.fuzzy_color_space.calculate_membership(lab_color)
                                if degrees:
                                    best_label = max(degrees, key=degrees.get)
                                    best_idx = proto_index.get(best_label, 0)
                                else:
                                    best_idx = 0
                                membership_cache[key] = best_idx

                            label_map[yy, xx] = best_idx

                            processed_pixels += 1
                            if update_progress:
                                now = time.perf_counter()
                                if now - last_update > 0.03 or processed_pixels == total_pixels:
                                    update_progress(processed_pixels, total_pixels)
                                    last_update = now

                    # Cache it
                    self.cm_cache[window_id][cache_key] = label_map

                # Build colors and create recolored image (same size as current image)
                color_map = plt.get_cmap('hsv', len(self.prototypes))
                prototype_colors = {p.label: color_map(i)[:3] for i, p in enumerate(self.prototypes)}
                for label in prototype_colors:
                    if label.lower() == "black":
                        prototype_colors[label] = (0, 0, 0)

                proto_rgb_uint8 = np.array(
                    [(np.array(prototype_colors[p.label]) * 255).astype(np.uint8) for p in self.prototypes],
                    dtype=np.uint8
                )  # (N,3)

                recolored_image = proto_rgb_uint8[label_map]  # (H,W,3)

                # Legend frame
                new_legend_frame, _ = build_legend_frame(self.prototypes, self.image_canvas)

                self.image_canvas.after(0, lambda: update_ui(recolored_image, new_legend_frame))

            except Exception as e:
                self.image_canvas.after(0, lambda: self.custom_warning("Processing Error", f"Error in color mapping: {e}"))
            finally:
                self.image_canvas.after(0, self.hide_loading)

        def recolor(window_id):
            """Switch palette without recomputing memberships (only recolor current modified_image)."""
            current = self.current_color_scheme[window_id]
            new = "alt" if current == "original" else "original"
            self.current_color_scheme[window_id] = new

            original_colors = self.prototype_color_sets[window_id][current]
            new_colors = self.prototype_color_sets[window_id][new]

            img = self.modified_image[window_id]
            recolored = img.copy()

            for orig_color, new_color in zip(original_colors, new_colors):
                mask = np.all(img == orig_color.astype(np.uint8), axis=-1)
                recolored[mask] = new_color.astype(np.uint8)

            img_tk = ImageTk.PhotoImage(Image.fromarray(recolored))  # already current size
            self.floating_images[window_id] = img_tk
            self.modified_image[window_id] = recolored

            image_items = self.image_canvas.find_withtag(f"{window_id}_click_image")
            if image_items:
                self.image_canvas.itemconfig(image_items[0], image=img_tk)
            else:
                self.custom_warning("Image Error", f"No image found for window_id: {window_id}")

            # Update legend labels (same as your code)
            new_legend_frame = self.proto_options[window_id]
            canvas = new_legend_frame.winfo_children()[0]
            inner_frame_id = canvas.find_withtag("inner")
            if inner_frame_id:
                inner_frame = canvas.nametowidget(canvas.itemcget(inner_frame_id[0], "window"))
            else:
                self.custom_warning("Legend Error", "No inner frame found in legend canvas")
                return

            for widget in inner_frame.winfo_children():
                widget.destroy()

            for i, prototype in enumerate(self.prototypes):
                current_colors = self.prototype_color_sets[window_id][self.current_color_scheme[window_id]]
                color_rgb = current_colors[i]
                color_hex = "#{:02x}{:02x}{:02x}".format(int(color_rgb[0]), int(color_rgb[1]), int(color_rgb[2]))
                label = tk.Label(
                    inner_frame,
                    text=prototype.label,
                    bg=color_hex,
                    fg="black" if np.mean(color_rgb) > 128 else "white",
                    padx=5, pady=2
                )
                label.pack(fill="x", padx=5, pady=2)

            inner_frame.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))

            self.image_canvas.after(0, lambda: update_ui(recolored, new_legend_frame))

        def update_ui(recolored_image, new_legend_frame):
            """Update the UI safely from the main thread."""
            try:
                self.modified_image[window_id] = recolored_image

                # IMPORTANT: recolored_image is already at current size (no resize needed)
                pil_to_show = Image.fromarray(recolored_image.astype(np.uint8))
                img_tk = ImageTk.PhotoImage(pil_to_show)
                self.floating_images[window_id] = img_tk

                # Store displayed PIL image (for saving)
                if hasattr(self, "display_pil"):
                    self.display_pil[window_id] = pil_to_show

                image_items = self.image_canvas.find_withtag(f"{window_id}_click_image")
                if image_items:
                    self.image_canvas.itemconfig(image_items[0], image=img_tk)
                else:
                    self.custom_warning("Image Error", f"No image found for window_id: {window_id}")

                x1, y1, x2, _ = self.image_canvas.bbox(items[0])
                new_legend_frame.place(x=x2 + 10, y=y1, width=100, height=300)

                use_original_button = tk.Button(
                    new_legend_frame,
                    text="Alt. Colors",
                    command=lambda: recolor(window_id)
                )
                use_original_button.grid(row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

                self.proto_options[window_id] = new_legend_frame

            except Exception as e:
                self.custom_warning("Display Error", f"Error displaying the image: {e}")

        threading.Thread(target=run_process, daemon=True).start()



















    ########################################################################################### Color Evaluation Functions ###########################################################################################
    def get_umbral_points(self, threshold, mode=None):
        """
        Filters points within the fuzzy color space volumes based on the given threshold.
        Displays the filtered points in a 3D model with a loading indicator.
        """
        # Check if the fuzzy color space is loaded
        if not hasattr(self, 'COLOR_SPACE') or not self.COLOR_SPACE:
            self.custom_warning("No Color Space", "Please load a fuzzy color space before deploying AT or PT.")
            return

        selected_options = [key for key, var in self.model_3d_options.items() if var.get()]
        if selected_options == ["Representative"]:
            return 
        else:   
            self.show_loading()

        # 🔹 Mostrar indicador de carga
        def update_progress(current_step, total_steps):
            """Updates the progress bar based on the current computation step."""
            progress_percentage = (current_step / total_steps) * 100
            self.progress["value"] = progress_percentage
            self.load_window.update_idletasks()

        def run_threshold_process():
            """Runs the threshold-based filtering and 3D visualization in a separate thread."""
            try:
                # Define prioridad de volumen
                priority_map = {
                    "Support": self.selected_core,
                    "0.5-cut": self.selected_alpha,
                    "Core": self.selected_support
                }

                selected_option = next((opt for opt in ["Support", "0.5-cut", "Core"] if opt in selected_options), None)
                selected_volume = priority_map[selected_option]

                # Paso 1: Filtrar puntos
                update_progress(1, 3)
                self.filtered_points, volume_limits = self.color_manager.filter_points_with_threshold(
                    selected_volume, threshold, step=0.25
                )

                # 🔸 Crear DataFrame con formato "min - max"
                csv_path = self.color_manager.create_csv(self.file_base_name, volume_limits, mode)
                print(f"✅ CSV saved in test_results/: {csv_path}")

                # Paso 2: Crear el gráfico 3D
                update_progress(2, 3)
                fig = VisualManager.plot_combined_3D(
                    self.file_base_name,
                    self.selected_centroids,
                    self.selected_core,
                    self.selected_alpha,
                    self.selected_support,
                    self.volume_limits,
                    self.hex_color,
                    selected_options,
                    self.filtered_points
                )
                if hasattr(self, "lab_value_frame"):
                    self.lab_value_frame.lift()

                # Paso 3: Dibujar el modelo 3D
                update_progress(3, 3)
                self.load_window.after(0, lambda: self.draw_model_3D(fig, selected_options))

            except Exception as e:
                self.custom_warning("Error", f"An error occurred while filtering points: {e}")
            finally:
                # 🔹 Ocultar el loading al terminar
                self.load_window.after(0, self.hide_loading)

        # Ejecutar en hilo separado para no bloquear la UI
        threading.Thread(target=run_threshold_process, daemon=True).start()



    def deploy_at(self):
        self.get_umbral_points(1.8, mode="AT")

    def deploy_pt(self):
        self.get_umbral_points(0.8, mode="PT")











def start_up():
    root = tk.Tk()
    app = PyFCSApp(root)
    root.mainloop()

if __name__ == '__main__':
    start_up()

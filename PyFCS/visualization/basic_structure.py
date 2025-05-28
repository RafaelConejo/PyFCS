import tkinter as tk
from tkinter import ttk, Menu, filedialog, messagebox, Scrollbar, DISABLED, NORMAL
import tkinter.font as tkFont
import sys
import os
from skimage import color
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from PIL import Image, ImageTk
import threading
import colorsys
import math
import random
from PyQt5.QtCore import QUrl
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QApplication, QMainWindow
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QEventLoop
import matplotlib.pyplot as plt





current_dir = os.path.dirname(__file__)
pyfcs_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))

# Add the PyFCS path to sys.path
sys.path.append(pyfcs_dir)

### my libraries ###
from PyFCS import Input, Visual_tools, ReferenceDomain, Prototype, FuzzyColorSpace
import PyFCS.visualization.utils_structure as utils_structure


class PyFCSApp:
    def __init__(self, root):
        # Initialize main app variables
        self.root = root
        self.COLOR_SPACE = False  # Flag for managing color spaces
        self.ORIGINAL_IMG = {}  # Bool function original image 
        self.MEMBERDEGREE = {}  # Bool function Color Mapping
        self.hex_color = []  # Save points colors for visualization
        self.images = {}
        self.color_entry_detect = {}

        self.volume_limits = ReferenceDomain(0, 100, -128, 127, -128, 127)

        # General configuration for the main window
        root.title("PyFCS Interface")  # Set the window title
        root.geometry("1000x500")  # Set default window size
        # self.root.attributes("-fullscreen", True)
        root.configure(bg="gray82")  # Set background color for the window

        # Menu bar configuration
        self.menubar = Menu(root)
        root.config(menu=self.menubar)  # Attach menu bar to the root window

        # File menu with options
        file_menu = Menu(self.menubar, tearoff=0)
        file_menu.add_command(label="Exit", command=self.exit_app)  # Add "Exit" option
        self.menubar.add_cascade(label="File", menu=file_menu)  # Add "File" menu to the menu bar

        # Image Manager menu
        img_menu = Menu(self.menubar, tearoff=0)
        img_menu.add_command(label="Open Image", command=self.open_image)  # Placeholder for opening images
        img_menu.add_command(label="Save Image", command=self.save_image)  # Placeholder for saving images
        img_menu.add_command(label="Close All", command=self.close_all_image)  # Placeholder for closing all images
        self.menubar.add_cascade(label="Image Manager", menu=img_menu)

        # Fuzzy Color Space Manager menu
        fuzzy_menu = Menu(self.menubar, tearoff=0)
        fuzzy_menu.add_command(label="New Color Space", command=self.show_menu_create_fcs)  # Create new color space
        fuzzy_menu.add_command(label="Load Color Space", command=self.load_color_space)  # Load existing color space
        self.menubar.add_cascade(label="Fuzzy Color Space Manager", menu=fuzzy_menu)

        # Help menu
        help_menu = Menu(self.menubar, tearoff=0)
        help_menu.add_command(label="About", command=self.about_info)  # Show "About" information
        self.menubar.add_cascade(label="Help", menu=help_menu)

        # Main frame for organizing sections
        main_frame = tk.Frame(root, bg="gray82")
        main_frame.pack(padx=10, pady=10, fill="x")

        # "Image Manager" section
        image_manager_frame = tk.LabelFrame(main_frame, text="Image Manager", bg="gray95", padx=10, pady=10)
        image_manager_frame.grid(row=0, column=0, padx=5, pady=5)

        # Load Icons 
        load_image = os.path.join(os.getcwd(), 'PyFCS', 'visualization', 'icons', 'LoadImage.png')
        load_image = Image.open(load_image)
        load_image = ImageTk.PhotoImage(load_image)

        save_image = os.path.join(os.getcwd(), 'PyFCS', 'visualization', 'icons', 'SaveImage.png')
        save_image = Image.open(save_image)
        save_image = ImageTk.PhotoImage(save_image)

        new_fcs = os.path.join(os.getcwd(), 'PyFCS', 'visualization', 'icons', 'NewFCS1.png')
        new_fcs = Image.open(new_fcs)
        new_fcs = ImageTk.PhotoImage(new_fcs)

        load_fcs = os.path.join(os.getcwd(), 'PyFCS', 'visualization', 'icons', 'LoadFCS.png')
        load_fcs = Image.open(load_fcs)
        load_fcs = ImageTk.PhotoImage(load_fcs)

        at_image = os.path.join(os.getcwd(), 'PyFCS', 'visualization', 'icons', 'AT.png')
        at_image = Image.open(at_image)
        at_image = ImageTk.PhotoImage(at_image)

        pt_image = os.path.join(os.getcwd(), 'PyFCS', 'visualization', 'icons', 'PT.png')
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
        image_manager_frame.load_image = load_image

        tk.Button(image_manager_frame, 
            image=save_image, 
            text=" Save Image", 
            command=self.save_image,
            compound="left"
        ).pack(side="left", padx=5)
        image_manager_frame.save_image = save_image

        # "Fuzzy Color Space Manager" section
        fuzzy_manager_frame = tk.LabelFrame(main_frame, text="Fuzzy Color Space Manager", bg="gray95", padx=10, pady=10)
        fuzzy_manager_frame.grid(row=0, column=1, padx=5, pady=5)

        # Buttons for fuzzy color space management
        tk.Button(fuzzy_manager_frame,
            text="New Color Space", 
            image=new_fcs,
            command=self.show_menu_create_fcs,
            compound="left" 
        ).pack(side="left", padx=5)
        fuzzy_manager_frame.new_fcs = new_fcs

        self.menu_create_fcs = Menu(root, tearoff=0)
        self.menu_create_fcs.add_command(label="Palette-Based Creation", command=self.palette_based_creation)
        self.menu_create_fcs.add_command(label="Image-Based Creation", command=self.image_based_creation)

        tk.Button(fuzzy_manager_frame,
            text="Load Color Space", 
            image=load_fcs,
            command=self.load_color_space,
            compound="left" 
        ).pack(side="left", padx=5)
        fuzzy_manager_frame.load_fcs = load_fcs


        # "Color Evaluation" section
        color_evaluation_frame = tk.LabelFrame(main_frame, text="Color Evaluation", bg="gray95", padx=10, pady=10)
        color_evaluation_frame.grid(row=0, column=2, padx=5, pady=5)

        tk.Button(color_evaluation_frame,
            text="Display AT", 
            image=at_image,
            command=self.deploy_at,
            compound="left" 
        ).pack(side="left", padx=5)
        color_evaluation_frame.at_image = at_image

        tk.Button(color_evaluation_frame,
            text="Display PT", 
            image=pt_image,
            command=self.deploy_pt,
            compound="left" 
        ).pack(side="left", padx=5)
        color_evaluation_frame.pt_image = pt_image


        # Main content frame for tabs and the right area
        main_content_frame = tk.Frame(root, bg="gray82")
        main_content_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Frame for image display
        image_area_frame = tk.LabelFrame(main_content_frame, text="Image Display", bg="gray95", padx=10, pady=10)
        image_area_frame.pack(side="left", fill="both", expand=True, padx=5, pady=5)

        # Canvas for displaying images
        self.image_canvas = tk.Canvas(image_area_frame, bg="white", borderwidth=2, relief="ridge")
        self.image_canvas.pack(fill="both", expand=True)

        # Notebook for tabs
        notebook = ttk.Notebook(main_content_frame)
        notebook.pack(side="right", fill="both", expand=True, padx=5, pady=5)



        # "Model 3D" tab
        model_3d_tab = tk.Frame(notebook, bg="gray95")
        notebook.add(model_3d_tab, text="Model 3D")

        # Dictionary to store the state of each checkbox
        self.model_3d_options = {}
        buttons_frame = tk.Frame(model_3d_tab, bg="gray95")
        buttons_frame.pack(side="top", fill="x", pady=5)

        # Create radiobuttons for different 3D options
        options = ["Representative", "Core", "0.5-cut", "Support"]
        for option in options:
            var = tk.BooleanVar(value=(option == "Representative"))
            self.model_3d_options[option] = var
            tk.Checkbutton(
                buttons_frame,
                text=option,
                variable=var,
                bg="gray95",
                font=("Arial", 10),
                command=self.on_option_select
            ).pack(side="left", padx=20)

        # Canvas for the 3D graph
        self.Canvas1 = tk.Frame(model_3d_tab, bg="white", borderwidth=2, relief="ridge")
        self.Canvas1.pack(side="left", fill="both", expand=True)

        # Frame for color buttons on the right
        self.colors_frame = tk.Frame(model_3d_tab, bg="gray95", width=50)
        self.colors_frame.pack(side="right", fill="y", padx=2, pady=10)

        # Canvas to enable scrolling
        self.scrollable_canvas = tk.Canvas(self.colors_frame, bg="gray95", highlightthickness=0)
        self.scrollable_canvas.pack(side="left", fill="both", expand=True)

        # Scrollbar for the canvas
        self.scrollbar = tk.Scrollbar(self.colors_frame, orient="vertical", command=self.scrollable_canvas.yview)
        self.scrollbar.pack(side="right", fill="y")

        # Configure the canvas and scrollbar
        self.scrollable_canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollable_canvas.configure(width=150)

        # Frame inside the canvas to hold the buttons
        self.inner_frame = tk.Frame(self.scrollable_canvas, bg="gray95")
        self.inner_frame.bind(
            "<Configure>",
            lambda e: self.scrollable_canvas.configure(scrollregion=self.scrollable_canvas.bbox("all"))
        )

        # Aquí aplicamos el método de scroll para el mouse
        def bind_scroll_events(canvas):
            def _on_mousewheel(event):
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

            def _bind_mousewheel(event):
                canvas.bind_all("<MouseWheel>", _on_mousewheel)

            def _unbind_mousewheel(event):
                canvas.unbind_all("<MouseWheel>")

            canvas.bind("<Enter>", _bind_mousewheel)
            canvas.bind("<Leave>", _unbind_mousewheel)

        # Llamamos a la función para habilitar el scroll para ese canvas específico
        bind_scroll_events(self.scrollable_canvas)

        # Add the inner_frame to the canvas
        self.canvas_window = self.scrollable_canvas.create_window((0, 0), window=self.inner_frame, anchor="nw")

        # "Select All" button for color operations
        self.select_all_button = tk.Button(
            self.inner_frame,
            text="Select All",
            bg="lightgray",
            font=("Arial", 10),
            command=self.select_all_color  
        )
        if self.COLOR_SPACE:
            self.select_all_button.pack(pady=5)







        # "Data" tab
        data_tab = tk.Frame(notebook, bg="gray95")
        notebook.add(data_tab, text="Data")

        # Header with centered "Name"
        name_data = tk.Frame(data_tab, bg="#e0e0e0", pady=5)
        name_data.pack(fill="x")
        tk.Label(name_data, text="Name:", font=("Helvetica", 12, "bold"), bg="#e0e0e0").pack(side="top", pady=5)
        self.file_name_entry = tk.Entry(name_data, font=("Helvetica", 12), width=30, justify="center")
        self.file_name_entry.pack(side="top", pady=5)
        self.file_name_entry.insert(0, "")  # Initial file name

        # Main area with canvas and scrollbars
        canvas_frame = tk.Frame(data_tab, bg="white")
        canvas_frame.pack(fill="both", expand=True)

        # Canvas for color table
        self.data_window = tk.Canvas(canvas_frame, bg="white", borderwidth=2, relief="ridge")
        self.data_window.grid(row=0, column=0, sticky="nsew")  # Expandir en todas las direcciones

        # Configure canvas_frame for dinamic restructure
        canvas_frame.rowconfigure(0, weight=1)  
        canvas_frame.columnconfigure(0, weight=1)  

        # Vertical scrollbar
        self.data_scrollbar_v = Scrollbar(canvas_frame, orient="vertical", command=self.data_window.yview)
        self.data_scrollbar_v.grid(row=0, column=1, sticky="ns")  

        # Horizontal scrollbar
        self.data_scrollbar_h = Scrollbar(canvas_frame, orient="horizontal", command=self.data_window.xview)
        self.data_scrollbar_h.grid(row=1, column=0, sticky="ew")  
        self.data_scrollbar_h.bind("<MouseWheel>", lambda event: self.on_mouse_wheel(event, self.data_scrollbar_h))

        self.data_window.configure(yscrollcommand=self.data_scrollbar_v.set, xscrollcommand=self.data_scrollbar_h.set)


        # Frame for the content inside the canvas
        self.inner_frame_data = tk.Frame(self.data_window, bg="white")
        self.data_window.create_window((0, 0), window=self.inner_frame_data, anchor="nw")

        # Ensure the canvas scrolls properly with the frame
        def update_scroll_region_2(event):
            self.data_window.configure(scrollregion=self.data_window.bbox("all"))

        self.inner_frame_data.bind("<Configure>", update_scroll_region_2)

        # Bottom bar with centered "Add Color" and "Apply" buttons
        bottom_bar = tk.Frame(data_tab, bg="#e0e0e0", pady=5)
        bottom_bar.pack(fill="x", side="bottom")

        button_container = tk.Frame(bottom_bar, bg="#e0e0e0")  # Center container for buttons
        button_container.pack(pady=5)

        add_button = tk.Button(
            button_container, text="Add New Color", font=("Helvetica", 12, "bold"),
            bg="#E0F2E9", command=lambda: self.addColor_data_window()
        )
        add_button.pack(side="left", padx=20)

        apply_button = tk.Button(
            button_container, text="Apply Changes", font=("Helvetica", 12, "bold"),
            bg="#E0F2E9", command=lambda: self.apply_changes()
        )
        apply_button.pack(side="left", padx=20)





        # Additional variables
        self.rgb_data = []  # RGB data for 3D visualization
        self.graph_widget = None  # Track 3D graph widget state
        self.app_qt = None
        self.more_graph_window = None

        # Bind the Escape key to toggle fullscreen mode
        self.root.bind("<Escape>", self.toggle_fullscreen)






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
        current_state = self.root.attributes("-fullscreen")
        self.root.attributes("-fullscreen", not current_state)


    
    def custom_warning(self, title="Warning", message="Warning"):
        """Creates a custom, aesthetic warning message window with gray tones."""
        warning_win = tk.Toplevel(self.root)
        warning_win.title(title)
        warning_win.configure(bg="#f5f5f5")  # Light gray background

        # Warning text
        label = tk.Label(warning_win, text=message, font=("Arial", 11, "bold"), 
                        fg="#333333", bg="#f5f5f5", wraplength=350)
        label.pack(pady=15, padx=20)

        # Stylized close button
        btn_ok = tk.Button(warning_win, text="OK", font=("Arial", 11, "bold"), 
                        bg="#999999", fg="white", bd=0, padx=10, pady=0, 
                        relief="flat", activebackground="#8c8c8c", 
                        command=warning_win.destroy)
        btn_ok.pack(pady=5)
        
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
        label = tk.Label(self.load_window, text="Loading Color Space...", font=("Arial", 16, "bold"), padx=20, pady=20)
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
        label = tk.Label(self.load_window, text="Processing...", font=("Arial", 12), padx=10, pady=10)
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
        self.prototypes = utils_structure.process_prototypes(self.color_data)

        # Create and save the fuzzy color space
        self.fuzzy_color_space = FuzzyColorSpace(space_name=" ", prototypes=self.prototypes)
        self.cores = self.fuzzy_color_space.get_cores()
        self.supports = self.fuzzy_color_space.get_supports()

        self.update_prototypes_info()
    


    def update_prototypes_info(self):
        # Update 3D graph and app state vars
        self.COLOR_SPACE = True
        self.MEMBERDEGREE = {key: True for key in self.MEMBERDEGREE}
        self.select_all_button.pack(pady=5)

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
        # Prompt the user to select a file
        filename = utils_structure.prompt_file_selection('fuzzy_color_spaces\\')

        if not filename:
            # Notify the user if no file was selected
            self.custom_warning(message="No file was selected.")
            return  # Early return to avoid unnecessary processing

        # Activate the 'Original Image' option for all open windows
        if hasattr(self, 'floating_images') and self.floating_images:
            for window_id in self.floating_images:
                self.show_original_image(window_id)

        self.show_loading_color_space()

        # Store file path and base name
        self.file_path = filename
        self.file_base_name = os.path.splitext(os.path.basename(filename))[0]

        # Determine file extension
        extension = os.path.splitext(filename)[1].lower()  # Use lower() for case-insensitive comparison

        # Initialize input class based on file extension
        input_class = Input.instance(extension)

        if extension == '.cns':
            # Read the file and prepare color data
            self.color_data = input_class.read_file(filename)
            self.display_data_window()
            self.update_volumes()

        elif extension == '.fcs':
            # Read the file and prepare color data along with fuzzy color space
            self.color_data, self.fuzzy_color_space = input_class.read_file(filename)

            # Cache frequently accessed data to avoid multiple method calls
            self.cores = self.fuzzy_color_space.cores  
            self.supports = self.fuzzy_color_space.supports
            self.prototypes = self.fuzzy_color_space.prototypes

            self.display_data_window()
            self.update_prototypes_info()

        else:
            # Notify the user if the file format is unsupported
            self.custom_warning("File Error", "Unsupported file format.")

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

            def hsv_to_rgb(h, s, v):
                """Converts HSV to RGB in the range 0-255."""
                r, g, b = colorsys.hsv_to_rgb(h, s, v)
                return int(r * 255), int(g * 255), int(b * 255)

            def draw_color_wheel():
                """Draws the color wheel on the canvas."""
                for y in range(canvas_size):
                    for x in range(canvas_size):
                        dx, dy = x - center, y - center
                        dist = math.sqrt(dx**2 + dy**2)
                        if dist <= radius:
                            angle = math.atan2(dy, dx)
                            hue = (angle / (2 * math.pi)) % 1
                            r, g, b = hsv_to_rgb(hue, 1, 1)
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
                    r, g, b = hsv_to_rgb(hue, 1, 1)
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
            utils_structure.create_color_display_frame_add(
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
        color_space_path = os.path.join(os.getcwd(), 'fuzzy_color_spaces', 'cns', 'ISCC_NBS_BASIC.cns')
        colors = utils_structure.load_color_data(color_space_path)

        # Create a popup window for color selection
        popup, self.scroll_palette_create_fcs = utils_structure.create_popup_window(
            parent=self.root,
            title="Select colors for your Color Space",
            width=400,
            height=500,
            header_text="Select colors for your Color Space"
        )

        # Center the popup window
        self.center_popup(popup, 400, 500)

        # Dictionary to store the Checkbuttons for selected colors
        self.color_checks = {}

        # Populate the scrollable frame with color data
        for color_name, data in colors.items():
            utils_structure.create_color_display_frame(
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
        Displays a popup window to select an image by filename and creates a floating window for the selected image.
        If no images are available, it shows an informational message.
        """
        # Verify if there are available images to display
        if not hasattr(self, "load_images_names") or not self.load_images_names:
            self.custom_warning(message="No images are currently available to display.")
            return  # Early return if no images are available

        # Create a popup window for image selection
        popup, listbox = utils_structure.create_selection_popup(
            parent=self.image_canvas,
            title="Select an Image",
            width=200,
            height=200,
            items=[os.path.basename(filename) for filename in self.load_images_names.values()]
        )

        # Center the popup window
        self.center_popup(popup, 200, 200)

        # Bind the listbox selection event to handle image selection
        listbox.bind(
            "<<ListboxSelect>>",
            lambda event: utils_structure.handle_image_selection(
                event=event,
                listbox=listbox,
                popup=popup,
                images_names=self.load_images_names,
                callback=self.get_fuzzy_color_space
            )
        )












    ########################################################################################### Funtions Model 3D ###########################################################################################
    def on_option_select(self):
        if self.COLOR_SPACE:  # Check if a color space is loaded
            self.filtered_points = {}
            selected_options = [key for key, var in self.model_3d_options.items() if var.get()]  # Get all selected options
            
            if not selected_options and self.graph_widget:
                self.display_color_buttons(self.color_matrix)
                self.graph_widget.get_tk_widget().destroy() 
            else:
                fig = Visual_tools.plot_combined_3D(
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
        self.add_button = tk.Button(self.Canvas1, text="Interactive Figure", font=("Arial", 12), command=lambda: self.on_add_graph(selected_options))
        self.add_button.place(relx=0.95, rely=0.05, anchor="ne")  # Posiciona el botón en la esquina superior derecha



    def on_add_graph(self, selected_options):
        """Generates the figure with Plotly, saves it as HTML, and displays it in a PyQt5 window."""

        def rebuild_menu():
            """Rebuilds the menu bar to prevent UI glitches after PyQt5 is used."""
            self.menubar.destroy()  # Elimina la barra de menú anterior
            self.menubar = Menu(self.root)  # Crea una nueva barra de menú
            self.root.config(menu=self.menubar)  # Asigna la nueva barra de menú

            # Define el tamaño de la fuente que se usará en los menús
            menu_font = tkFont.Font(family="Arial", size=11)  # Puedes ajustar el tamaño (size) aquí

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

        fig = Visual_tools.plot_more_combined_3D(
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

        file_path = os.path.abspath(os.path.join(os.getcwd(), 'PyFCS', 'external', 'temp_plot.html'))
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
                font=("Arial", 10),
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
                text=header, anchor="center", font=("Arial", 10, "bold")
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
                    text=str(round(value, 2)) if j < 3 else value, anchor="center", font=("Arial", 10)
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
                text="❌", fill="black", font=("Arial", 10, "bold"), anchor="center",
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
        # Verify if there are available images to save
        if not hasattr(self, "modified_image") or not self.modified_image:
            self.custom_warning(message="There are currently no modified images available to save.")
            return  # Early return if no images are available

        # Create a popup window for image selection
        popup, listbox = utils_structure.create_selection_popup(
            parent=self.image_canvas,
            title="Select an Image to Save",
            width=200,
            height=200,
            items=[os.path.basename(filename) for filename in self.load_images_names.values()]
        )

        # Center the popup window
        self.center_popup(popup, 200, 200)

        # Function to handle selection and save the image
        def on_select(event):
            selection = listbox.curselection()
            if not selection:
                return
            
            index = selection[0]
            selected_image = list(self.modified_image.values())[index]

            # Ask the user where to save the image
            save_path = filedialog.asksaveasfilename(
                defaultextension=".png",
                filetypes=[("PNG files", "*.png"), ("JPEG files", "*.jpg"), ("All Files", "*.*")]
            )

            if save_path:
                try:
                    img = Image.fromarray(selected_image)
                    img.save(save_path)

                    messagebox.showinfo("Success", f"Image saved successfully at:\n{save_path}")
                except Exception as e:
                    self.custom_warning("Error", f"Failed to save image:\n{str(e)}")

            popup.destroy()

        # Bind the listbox selection event to the save function
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
        initial_directory = os.getcwd()
        initial_directory = os.path.join(initial_directory, 'image_test\\')
        
        # Define the file types that can be selected (e.g., .jpg, .jpeg, .png, .bmp)
        filetypes = [("All Files", "*.jpg;*.jpeg;*.png;*.bmp")]
        
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
        The window is movable, resizable, and includes options for displaying the original image and color mapping.
        """
        # Initialize the load_images_names dictionary if it doesn't exist
        if not hasattr(self, "load_images_names"):
            self.load_images_names = {}

        # Generate a unique window ID based on the number of existing images
        while True:
            window_id = f"floating_{random.randint(1000, 9999)}"
            if window_id not in self.load_images_names:
                break

        self.load_images_names[window_id] = filename

        # Set initial values for whether the window should display color space and original image
        self.MEMBERDEGREE[window_id] = bool(self.COLOR_SPACE)
        self.ORIGINAL_IMG[window_id] = False

        # Load the image from the selected file
        img = Image.open(filename)
        original_width, original_height = img.size  # Get the original dimensions of the image

        # Set the desired size for the rectangle (window) where the image will be displayed
        rect_width = 250
        rect_height = 250

        # Calculate the maximum scale factor to fit the image within the defined rectangle size without distortion
        scale = min(rect_width / original_width, rect_height / original_height)

        # Calculate the new dimensions of the image after scaling
        new_width = int(original_width * scale)
        new_height = int(original_height * scale)

        # Resize the image using the new dimensions
        img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Store the resized image dimensions in a dictionary for later reference
        if not hasattr(self, "image_dimensions"):
            self.image_dimensions = {}
            self.original_image_dimensions = {}
        self.original_image_dimensions[window_id] = (original_width, original_height)
        self.image_dimensions[window_id] = (new_width, new_height)

        # Update the rectangle dimensions to match the resized image
        rect_width, rect_height = new_width, new_height

        # Create a dictionary to store the image
        self.images[window_id] = img_resized
        img_tk = ImageTk.PhotoImage(img_resized)

        # Initialize the dictionaries to store floating images and frames if they don't exist
        if not hasattr(self, "floating_images"):
            self.floating_images = {}
            self.original_images = {}
            self.modified_image = {}

        # Store the image reference in the floating images dictionary
        self.floating_images[window_id] = img_tk
        self.original_images[window_id] = img_tk

        # Create a background rectangle for the floating window
        self.image_canvas.create_rectangle(
            x, y, x + rect_width + 30, y + rect_height + 50, outline="black", fill="white", width=2, tags=(window_id, "floating")
        )

        # Create the title bar at the top of the window
        self.image_canvas.create_rectangle(
            x, y, x + rect_width + 30, y + 30, outline="black", fill="gray", tags=(window_id, "floating")
        )

        # Display the image filename in the title bar
        self.image_canvas.create_text(
            x + 50, y + 15, anchor="w", text=os.path.basename(filename), fill="white", font=("Arial", 10), tags=(window_id, "floating")
        )

        # Create a close button in the title bar
        self.image_canvas.create_rectangle(
            x + rect_width + 25, y + 5, x + rect_width + 5, y + 25, outline="black", fill="red", tags=(window_id, "floating", f"{window_id}_close_button")
        )
        self.image_canvas.create_text(
            x + rect_width + 15, y + 15, text="X", fill="white", font=("Arial", 10, "bold"), tags=(window_id, "floating", f"{window_id}_close_button")
        )

        # Add an arrow button to the left side of the title bar
        self.image_canvas.create_text(
            x + 15, y + 15, text="▼", fill="white", font=("Arial", 12), tags=(window_id, "floating", f"{window_id}_arrow_button")
        )

        # Display the image inside the frame using a Label widget
        self.image_canvas.create_image(
            x + 15 + rect_width // 2, y + 40 + rect_height // 2, image=self.floating_images[window_id], tags=(window_id, "floating", f"{window_id}_click_image")
        )

        # Function to close the floating window when the close button is clicked
        def close_window(event):
            """Closes the floating window and removes all associated elements."""
            self.image_canvas.delete(window_id)
            del self.floating_images[window_id]

            if hasattr(self, "proto_options") and window_id in self.proto_options:
                if self.proto_options[window_id].winfo_exists():
                    self.proto_options[window_id].destroy()
                del self.proto_options[window_id]

            if hasattr(self, "load_images_names") and window_id in self.load_images_names:
                del self.load_images_names[window_id]

        # Function to show the dropdown menu when the arrow button is clicked
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

        # Function to make the floating window movable
        def start_move(event):
            """Stores the initial position when the mouse is pressed on the window."""
            self.last_x, self.last_y = event.x, event.y

        def move_window(event):
            """Moves the floating window based on the mouse drag."""
            dx, dy = event.x - self.last_x, event.y - self.last_y
            self.image_canvas.move(window_id, dx, dy)
            self.image_canvas.tag_raise(window_id)
            self.image_canvas.tag_raise(f"{window_id}_close_button")
            self.image_canvas.tag_raise(f"{window_id}_arrow_button")
            self.image_canvas.tag_raise(f"{window_id}_image")

            if hasattr(self, "proto_options") and window_id in self.proto_options:
                proto_option_frame = self.proto_options[window_id]
                if proto_option_frame.winfo_exists():
                    items = self.image_canvas.find_withtag(window_id)
                    if items:
                        x1, y1, x2, y2 = self.image_canvas.bbox(items[0])
                        frame_x = x2 + 10
                        frame_y = y1

                        canvas_width = self.image_canvas.winfo_width()
                        canvas_height = self.image_canvas.winfo_height()

                        if frame_x + 120 > canvas_width:
                            frame_x = canvas_width - 120
                        if frame_y + 150 > canvas_height:
                            frame_y = canvas_height - 150

                        proto_option_frame.place(x=frame_x, y=frame_y)
                        proto_option_frame.lift()

            self.last_x, self.last_y = event.x, event.y

        def get_pixel_value(event, window_id=window_id):
            """Gets the pixel value where the image is clicked, considering window movement."""
            img = self.images[window_id]
            resized_width, resized_height = self.image_dimensions[window_id]
            original_width, original_height = img.size

            abs_x = self.image_canvas.canvasx(event.x)
            abs_y = self.image_canvas.canvasy(event.y)

            image_items = self.image_canvas.find_withtag(f"{window_id}_click_image")
            if not image_items:
                self.custom_warning("No window", f"No floating window found with id {window_id}")
                return

            x1, y1, _, _ = self.image_canvas.bbox(image_items[0])
            relative_x = abs_x - x1
            relative_y = abs_y - y1

            scale_x = original_width / resized_width
            scale_y = original_height / resized_height

            x_original = int(relative_x * scale_x)
            y_original = int(relative_y * scale_y)

            if 0 <= x_original < original_width and 0 <= y_original < original_height:
                pixel_value = img.getpixel((x_original, y_original))
                if len(pixel_value) == 4:
                    pixel_value = pixel_value[:3]

                pixel_rgb_np = np.array([[pixel_value]], dtype=np.uint8)
                pixel_lab = color.rgb2lab(pixel_rgb_np)[0][0]

                if self.COLOR_SPACE:
                    self.display_pixel_value(x_original, y_original, pixel_lab)

            return "break"

        # Bind events for moving the window
        self.image_canvas.tag_bind(window_id, "<Button-1>", start_move)
        self.image_canvas.tag_bind(window_id, "<B1-Motion>", move_window)

        # Bind events for the close button
        self.image_canvas.tag_bind(f"{window_id}_close_button", "<Button-1>", close_window)

        # Bind events for click
        self.image_canvas.tag_bind(f"{window_id}_click_image", "<Button-1>", get_pixel_value)

        # Bind events for the arrow button (to show the context menu)
        self.image_canvas.tag_bind(f"{window_id}_arrow_button", "<Button-1>", show_menu_image)


    
    # ADD THIS
    def show_more_info(self):
        messagebox.showinfo("More Info", "No prototype found or additional information about the pixel.")


    def display_pixel_value(self, x_original, y_original, pixel_lab):
        """
        Displays the pixel value in LAB format and its coordinates within a frame at the bottom of the canvas.
        Also shows the closest prototype and its membership degree.
        """
        # Create the frame and labels only once if they don't exist
        if not hasattr(self, "lab_value_frame"):
            self.lab_value_frame = tk.Frame(self.Canvas1, bg="lightgray", height=40)
            self.lab_value_frame.pack(side="bottom", fill="x", padx=10, pady=5)

            # Frame for left-aligned text
            text_frame = tk.Frame(self.lab_value_frame, bg="lightgray")
            text_frame.pack(side="left", padx=10, pady=5, fill="x")

            # Define fonts for labels
            bold_font = ("Arial", 12, "bold")
            normal_font = ("Arial", 12)

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
            self.proto_value = tk.Label(text_frame, text="", font=normal_font, bg="lightgray")
            self.proto_value.pack(side="left")

            # "More Info" button
            more_info_button = tk.Button(
                self.lab_value_frame, text="🔍", font=("Arial", 9),
                bg="white", command=self.show_more_info, relief="flat", borderwidth=0
            )
            more_info_button.pack(side="right", padx=5, pady=2)

        # Calculate the closest prototype and its membership degree
        membership_degrees = self.fuzzy_color_space.calculate_membership(pixel_lab)
        if membership_degrees:
            max_proto = max(membership_degrees, key=membership_degrees.get)
            proto_text = f"{max_proto} | {round(membership_degrees[max_proto], 2)}"
        else:
            proto_text = "None"

        
        positive = self.color_data[max_proto]["positive_prototype"]
        delta_e = utils_structure.delta_e_ciede2000(positive, pixel_lab)
        if delta_e <= 0.8:
            c = "green"
        elif delta_e <= 1.8:
            c = "orange"
        else:
            c = "red"

        # Update the labels with the new values
        self.coord_value.config(text=f"({x_original}, {y_original})    |    ")
        self.lab_value_print.config(text=f"{pixel_lab[0]:.2f}, {pixel_lab[1]:.2f}, {pixel_lab[2]:.2f}    |    ")
        self.proto_value.config(text=proto_text, fg=c)




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
        select_popup, listbox = utils_structure.create_selection_popup(
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
            lambda event: utils_structure.handle_image_selection(
                event=event,
                listbox=listbox,
                popup=select_popup,
                images_names=self.load_images_names,
                callback=lambda window_id: [
                    self.get_fuzzy_color_space_merge(window_id, colors, threshold, min_samples),
                    popup.destroy()
                ]
            )
        )



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
            command=lambda: [self.get_fuzzy_color_space_recalculate(colors, threshold, min_samples, popup), popup.destroy()],
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
                color_box = tk.Label(frame, bg=utils_structure.rgb_to_hex(rgb), width=4, height=2, relief="solid", bd=1)
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
        add_colors_button.pack(side="left", padx=20)

        save_button = ttk.Button(
            button_frame,
            text="Create Fuzzy Color Space",
            command=lambda: [self.process_fcs(colors), popup.destroy()],
            style="Accent.TButton"
        )
        save_button.pack(side="left", padx=20)

        # Style for buttons
        style = ttk.Style()
        style.configure("Accent.TButton", font=("Helvetica", 10, "bold"), padding=10)



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


    def get_fuzzy_color_space(self, window_id, threshold=0.5, min_samples=160):
        """
        Retrieves the fuzzy color space for the specified image and displays the detected colors.
        Adds the source image identifier to each color if it doesn't already exist.
        """
        image = self.images[window_id]
        colors = utils_structure.get_fuzzy_color_space(image, threshold, min_samples)

        # Add the source image identifier to each color if it doesn't exist
        for id in colors:
            if "source_image" not in id:
                id["source_image"] = window_id

        # Display the detected colors
        self.display_detected_colors(colors, threshold, min_samples)



    def get_fuzzy_color_space_merge(self, new_window_id, colors, threshold, min_samples):
        """
        Retrieves the fuzzy color space for a new image and merges it with the existing colors.
        Adds the source image identifier to each new color if it doesn't already exist.
        """
        if new_window_id and not any(id.get("source_image") == new_window_id for id in colors):
            new_colors = utils_structure.get_fuzzy_color_space(self.images[new_window_id], threshold, min_samples)

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
        self.get_fuzzy_color_space_merge(window_id, filtered_colors, threshold, min_samples)



    def get_fuzzy_color_space_recalculate(self, colors, threshold=0.5, min_samples=160, popup = None):
        """
        Recalculates the fuzzy color space for the selected image.
        If multiple images are available, prompts the user to select one.
        """
        # Get unique source image IDs from the current colors
        unique_ids = {id.get("source_image") for id in colors}

        if len(unique_ids) > 1:
            # If there are multiple images, prompt the user to select one
            popup, listbox = utils_structure.create_selection_popup(
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
                lambda event: utils_structure.handle_image_selection(
                    event=event,
                    listbox=listbox,
                    popup=popup,
                    images_names=self.load_images_names,
                    callback=lambda window_id: [self.recalculate(window_id, colors, threshold, min_samples), popup.destroy()]
                )
            )

        else:
            # If there is only one image, recalculate its colors directly
            self.get_fuzzy_color_space(unique_ids.pop(), threshold, min_samples)
            popup.destroy()



    def color_mapping(self, window_id):
        # if window exist
        items = self.image_canvas.find_withtag(window_id)
        if not items:
            self.custom_warning("No Window", f"No floating window found with id {window_id}")
            return

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
                font=("Arial", 10),
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
        """Action triggered when a color button is clicked; generates and displays the grayscale image."""
        # Show a loading indicator while processing
        self.show_loading()

        def update_progress(current_step, total_steps):
            """Callback to update the progress bar."""
            progress_percentage = (current_step / total_steps) * 100
            self.progress["value"] = progress_percentage
            self.load_window.update_idletasks()

        def run_process():
            """Processing function that will run in a separate thread."""
            try:
                # Get the index of the selected prototype color
                pos = self.color_matrix.index(self.current_protos[window_id].get())

                # Generate the grayscale image
                grayscale_image_array = utils_structure.get_proto_percentage(
                    prototypes=self.prototypes,          # Prototypes used for the transformation
                    image=self.images[window_id],        # The current image for the given window_id
                    fuzzy_color_space=self.fuzzy_color_space,  # Fuzzy color space
                    selected_option=pos,                 # Index of the selected option
                    progress_callback=update_progress    # Progress callback function
                )

                # Send the result back to the main thread for further processing
                self.display_color_mapping(grayscale_image_array, window_id)
            except Exception as e:
                self.custom_warning("Error", f"Error in run_process: {e}")
                return

            finally:
                # Hide the loading indicator once processing is complete
                self.hide_loading()

        # Execute the processing function in a separate thread
        threading.Thread(target=run_process).start()



    def display_color_mapping(self, grayscale_image_array, window_id):
        """Displays the generated grayscale image in the graphical interface."""
        try:
            self.modified_image[window_id] = grayscale_image_array

            # Convert the array into an image that Tkinter can use
            grayscale_image = Image.fromarray(grayscale_image_array)

            # Resize the image to match the original dimensions
            new_width, new_height = self.image_dimensions[window_id]
            grayscale_image = grayscale_image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Convert the image to a PhotoImage format
            img_tk = ImageTk.PhotoImage(grayscale_image)

            # Update the PhotoImage reference to prevent garbage collection
            self.floating_images[window_id] = img_tk

            # Find the image item ID in the canvas using the window_id tag
            image_items = self.image_canvas.find_withtag(f"{window_id}_click_image")

            if image_items:
                image_id = image_items[0]  # Assuming there's only one image per window_id
                self.image_canvas.itemconfig(image_id, image=img_tk)
            else:
                self.custom_warning("Image Error", f"No image found for window_id: {window_id}")

        except Exception as e:
            self.custom_warning("Display Error", f"Error displaying the image: {e}")



    def show_original_image(self, window_id):
        """Displays the original image stored in floating_images."""
        try:
            # Retrieve the original image stored in floating_images
            img_tk = self.original_images.get(window_id)

            if img_tk is not None:
                # Check if there is a proto_options window for this window_id
                if hasattr(self, "proto_options") and window_id in self.proto_options:
                    try:
                        # If the proto_options window exists, destroy it
                        if self.proto_options[window_id].winfo_exists():
                            self.proto_options[window_id].destroy()

                        # Remove the reference to the proto_options window
                        del self.proto_options[window_id]
                    except Exception as e:
                        self.custom_warning("Window Error", f"Error trying to destroy the proto_options window: {e}")
                        return

                # Find the image item in the canvas using the window_id tag
                image_items = self.image_canvas.find_withtag(f"{window_id}_click_image")

                if image_items:
                    image_id = image_items[0]  # Assuming there's only one image per window_id
                    # Update the image to the original
                    self.image_canvas.itemconfig(image_id, image=img_tk)
                else:
                    self.custom_warning("Image Error", f"No canvas image found for window_id: {window_id}")
                    return

                # Reset flags
                self.ORIGINAL_IMG[window_id] = False
                if self.COLOR_SPACE:
                    self.MEMBERDEGREE[window_id] = True

            else:
                self.custom_warning("Not Original Image", f"Original image not found for window_id: {window_id}")
                return

        except Exception as e:
            self.custom_warning("Display Error", f"Error displaying the original image: {e}")
            return




    def color_mapping_all(self, window_id):
        """Applies color mapping to the image and updates the floating window with a progress bar."""

        # Check if the window exists
        items = self.image_canvas.find_withtag(window_id)
        if not items:
            self.custom_warning("No Window", f"No floating window found with id {window_id}")
            return

        # Set initial states
        self.MEMBERDEGREE[window_id] = False
        self.ORIGINAL_IMG[window_id] = True

        # Initialize proto_options and remove legend if it exists
        self.proto_options = getattr(self, "proto_options", {})
        legend_frame = self.proto_options.pop(window_id, None)
        if legend_frame and legend_frame.winfo_exists():
            legend_frame.destroy()

        # Show loading indicator
        self.show_loading()

        def update_progress(current_step, total_steps):
            """Update the progress bar."""
            self.progress["value"] = (current_step / total_steps) * 100
            self.load_window.update_idletasks()

        def color_mapping_and_legend(fuzzy_color_space, prototypes, image, parent_canvas, progress_callback=None):
            """
            Processes an image to map its colors to a fuzzy color space and returns 
            the recolored image and a legend in a Tkinter Frame.
            """
            img_np = np.array(image)

            if img_np.shape[-1] == 4:
                img_np = img_np[..., :3]  

            img_np = img_np / 255.0
            lab_img = color.rgb2lab(img_np)

            color_map = plt.cm.get_cmap('hsv', len(prototypes))
            prototype_colors = {prototype.label: color_map(i)[:3] for i, prototype in enumerate(prototypes)}

            height, width = image.height, image.width
            total_pixels = height * width
            colorized_image = np.zeros((height, width, 3), dtype=np.uint8) 
            membership_cache = {}

            processed_pixels = 0  

            for y in range(height):
                for x in range(width):
                    lab_color = tuple(lab_img[y, x])

                    if lab_color in membership_cache:
                        membership_degrees = membership_cache[lab_color]
                    else:
                        membership_degrees = fuzzy_color_space.calculate_membership(lab_color)
                        membership_cache[lab_color] = membership_degrees  

                    if not membership_degrees:
                        colorized_image[y, x] = [0, 0, 0]  
                    else:
                        best_prototype = max(membership_degrees, key=membership_degrees.get)
                        rgb_color = np.array(prototype_colors[best_prototype]) * 255
                        colorized_image[y, x] = rgb_color.astype(np.uint8)

                    processed_pixels += 1
                    if progress_callback:
                        progress_callback(processed_pixels, total_pixels)

            # Create the legend in a Tkinter Frame
            legend_frame = tk.Frame(parent_canvas, bg="white", relief="solid", bd=1)

            # Configure expansion inside the grid
            legend_frame.grid_rowconfigure(0, weight=1)
            legend_frame.grid_columnconfigure(0, weight=1)

            # Create Canvas with scrollbars
            canvas = tk.Canvas(legend_frame, bg="white", highlightthickness=0)
            v_scroll = tk.Scrollbar(legend_frame, orient=tk.VERTICAL, command=canvas.yview)
            h_scroll = tk.Scrollbar(legend_frame, orient=tk.HORIZONTAL, command=canvas.xview)

            canvas.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

            # Pack using grid
            canvas.grid(row=0, column=0, sticky="nsew")
            v_scroll.grid(row=0, column=1, sticky="ns")
            h_scroll.grid(row=1, column=0, sticky="ew")

            # Create a Frame inside the Canvas for the legend elements
            inner_frame = tk.Frame(canvas, bg="white")
            window_id_in_canvas = canvas.create_window((0, 0), window=inner_frame, anchor="nw", tags="inner")


            # Ensure the inner_frame width follows the canvas size
            def resize_inner(event):
                canvas.itemconfig("inner", width=event.width)

            canvas.bind("<Configure>", resize_inner)

            # Function to update scrollable area
            def on_frame_configure(event):
                canvas.configure(scrollregion=canvas.bbox("all"))

            inner_frame.bind("<Configure>", lambda e: canvas.after_idle(on_frame_configure, e))

            # Allow scrolling with mouse wheel
            def _on_mouse_wheel(event):
                if event.delta:  # Windows / macOS
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                else:  # Linux
                    if event.num == 4:
                        canvas.yview_scroll(-1, "units")
                    elif event.num == 5:
                        canvas.yview_scroll(1, "units")

            # Apply scroll functionality for the canvas
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

            # Add color labels to the legend
            for i, prototype in enumerate(prototypes):
                color_rgb = np.array(prototype_colors[prototype.label]) * 255
                color_hex = "#{:02x}{:02x}{:02x}".format(int(color_rgb[0]), int(color_rgb[1]), int(color_rgb[2]))
                label = tk.Label(inner_frame, text=prototype.label, bg=color_hex, 
                                fg="black" if np.mean(color_rgb) > 128 else "white", padx=5, pady=2)
                label.pack(fill="x", padx=5, pady=2)

            # **Key solution**: Ensure `canvas.bbox("all")` captures all content
            inner_frame.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))


            # Original invented colors
            original_colors = [np.array(prototype_colors[proto.label]) * 255 for proto in self.prototypes]

            # Colors from self.hex_color
            hex_colors = list(self.hex_color.keys())
            alt_colors = [
                np.array([
                    int(hex_colors[i][j:j+2], 16)
                    for j in (1, 3, 5)
                ]) for i, proto in enumerate(self.prototypes)
            ]

            # Save both color sets
            if not hasattr(self, "prototype_color_sets"):
                self.prototype_color_sets = {}
            if not hasattr(self, "current_color_scheme"):
                self.current_color_scheme = {}

            self.prototype_color_sets[window_id] = {
                "original": original_colors,
                "alt": alt_colors
            }
            self.current_color_scheme[window_id] = "original"


            return colorized_image, legend_frame

        def run_process():
            """Run the processing in a separate thread."""
            try:
                recolored_image, new_legend_frame = color_mapping_and_legend(
                    self.fuzzy_color_space, self.prototypes, self.images[window_id], 
                    self.image_canvas, progress_callback=update_progress
                )

                self.image_canvas.after(0, lambda: update_ui(recolored_image, new_legend_frame))
            
            except Exception as e:
                self.image_canvas.after(0, lambda: self.custom_warning("Processing Error", f"Error in color mapping: {e}"))
            
            finally:
                self.image_canvas.after(0, self.hide_loading)  

        
        def recolor(window_id):
            # Select alternative color set
            current = self.current_color_scheme[window_id]
            new = "alt" if current == "original" else "original"
            self.current_color_scheme[window_id] = new

            original_colors = self.prototype_color_sets[window_id][current]
            new_colors = self.prototype_color_sets[window_id][new]

            img = self.modified_image[window_id]
            recolored = img.copy()

            # Reselect colors sets
            for orig_color, new_color in zip(original_colors, new_colors):
                mask = np.all(img == orig_color.astype(np.uint8), axis=-1)
                recolored[mask] = new_color.astype(np.uint8)

            # Update image and legend 
            new_width, new_height = self.image_dimensions[window_id]
            img_tk = ImageTk.PhotoImage(Image.fromarray(recolored).resize((new_width, new_height), Image.Resampling.LANCZOS))
            self.floating_images[window_id] = img_tk
            self.modified_image[window_id] = recolored
            image_items = self.image_canvas.find_withtag(f"{window_id}_click_image")
            if image_items:
                self.image_canvas.itemconfig(image_items[0], image=img_tk)
            else:
                self.custom_warning("Image Error", f"No image found for window_id: {window_id}")

            # New frame
            new_legend_frame = self.proto_options[window_id]
            canvas = new_legend_frame.winfo_children()[0]
            inner_frame_id = canvas.find_withtag("inner")
            if inner_frame_id:
                inner_frame = canvas.nametowidget(canvas.itemcget(inner_frame_id[0], "window"))
            else:
                self.custom_warning("Legend Error", "No inner frame found in legend canvas")
                return

            # Clean labels in inner_frame 
            for widget in inner_frame.winfo_children():
                widget.destroy()

            # Add new colors labels
            for i, prototype in enumerate(self.prototypes):
                current_colors = self.prototype_color_sets[window_id][self.current_color_scheme[window_id]]
                color_rgb = current_colors[i]
                color_hex = "#{:02x}{:02x}{:02x}".format(int(color_rgb[0]), int(color_rgb[1]), int(color_rgb[2]))

                label = tk.Label(inner_frame, text=prototype.label, bg=color_hex, 
                                fg="black" if np.mean(color_rgb) > 128 else "white", padx=5, pady=2)
                label.pack(fill="x", padx=5, pady=2)

                # Update scroll 
                inner_frame.update_idletasks()
                canvas.configure(scrollregion=canvas.bbox("all"))

            self.image_canvas.after(0, lambda: update_ui(recolored, new_legend_frame))


        def update_ui(recolored_image, new_legend_frame):
            """Update the UI safely from the main thread."""
            try:
                self.modified_image[window_id] = recolored_image

                new_width, new_height = self.image_dimensions[window_id]
                img_tk = ImageTk.PhotoImage(Image.fromarray(recolored_image).resize((new_width, new_height), Image.Resampling.LANCZOS))

                self.floating_images[window_id] = img_tk
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
    def get_umbral_points(self, threshold):
        """
        Filters points within the fuzzy color space volumes based on the given threshold.
        Displays the filtered points in a 3D model.
        """
        # Check if the fuzzy color space is loaded
        if not hasattr(self, 'COLOR_SPACE') or not self.COLOR_SPACE:
            self.custom_warning("No Color Space", "Please load a fuzzy color space before deploying AT or PT.")
            return

        selected_options = [key for key, var in self.model_3d_options.items() if var.get()]  # Get all selected options
        if selected_options == ["Representative"]:
            return
        
        priority_map = {
            "Support": self.selected_core,
            "0.5-cut": self.selected_alpha,
            "Core": self.selected_support
        } 
        selected_option = next((opt for opt in ["Support", "0.5-cut", "Core"] if opt in selected_options), None)
        selected_volume = priority_map[selected_option]
        

        # Find PT or AT points
        self.filtered_points = utils_structure.filter_points_with_threshold(selected_volume, threshold, step=0.5)

        # Plot the filtered points and display the 3D model
        fig = Visual_tools.plot_combined_3D(
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
        self.draw_model_3D(fig, selected_options)  # Pass each figure to be drawn on the Tkinter Canvas



    def deploy_at(self):
        self.get_umbral_points(1.8)

    def deploy_pt(self):
        self.get_umbral_points(0.8)











def start_up():
    root = tk.Tk()
    app = PyFCSApp(root)
    root.mainloop()

if __name__ == '__main__':
    start_up()

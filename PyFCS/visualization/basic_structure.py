import tkinter as tk
from tkinter import ttk, Menu, filedialog, messagebox, Scrollbar, DISABLED, NORMAL
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

current_dir = os.path.dirname(__file__)
pyfcs_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))

# Add the PyFCS path to sys.path
sys.path.append(pyfcs_dir)

### my libraries ###
from PyFCS import Input, Visual_tools, ReferenceDomain, Prototype, FuzzyColorSpace
import PyFCS.visualization.utils_structure as utils_structure

class PyFCSApp:
    def __init__(self, root):
        # Initialize main app variablesG
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
        menubar = Menu(root)
        root.config(menu=menubar)  # Attach menu bar to the root window

        # File menu with options
        file_menu = Menu(menubar, tearoff=0)
        file_menu.add_command(label="Exit", command=self.exit_app)  # Add "Exit" option
        menubar.add_cascade(label="File", menu=file_menu)  # Add "File" menu to the menu bar

        # Image Manager menu
        img_menu = Menu(menubar, tearoff=0)
        img_menu.add_command(label="Open Image")  # Placeholder for opening images
        img_menu.add_command(label="Save Image")  # Placeholder for saving images
        img_menu.add_command(label="Close All")  # Placeholder for closing all images
        menubar.add_cascade(label="Image Manager", menu=img_menu)

        # Fuzzy Color Space Manager menu
        fuzzy_menu = Menu(menubar, tearoff=0)
        fuzzy_menu.add_command(label="New Color Space", command=self.show_menu_create_fcs)  # Create new color space
        fuzzy_menu.add_command(label="Load Color Space", command=self.load_color_space)  # Load existing color space
        menubar.add_cascade(label="Fuzzy Color Space Manager", menu=fuzzy_menu)

        # Help menu
        help_menu = Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self.about_info)  # Show "About" information
        menubar.add_cascade(label="Help", menu=help_menu)

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
            text="Deploy AT", 
            command=self.deploy_at
        ).pack(side="left", padx=5)

        tk.Button(color_evaluation_frame,
            text="Deploy PT", 
            command=self.deploy_pt
        ).pack(side="left", padx=5)


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

        # Radiobuttons for selecting 3D visualization modes
        self.model_3d_option = tk.StringVar(value="Representative")  # Default value for options
        buttons_frame = tk.Frame(model_3d_tab, bg="gray95")
        buttons_frame.pack(side="top", fill="x", pady=5)

        # Create radiobuttons for different 3D options
        options = ["Representative", "Core", "0.5-cut", "Support"]
        for option in options:
            tk.Radiobutton(
                buttons_frame,
                text=option,
                variable=self.model_3d_option,
                value=option,
                bg="gray95",
                font=("Arial", 10),
                command=self.on_option_select
            ).pack(side="left", padx=20)

        # Canvas for the 3D graph
        self.Canvas1 = tk.Canvas(model_3d_tab, bg="white", borderwidth=2, relief="ridge")
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

        self.inner_frame.bind("<MouseWheel>", lambda event: self.on_mouse_wheel(event, self.scrollable_canvas))

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
        def update_scroll_region(event):
            self.data_window.configure(scrollregion=self.data_window.bbox("all"))

        self.inner_frame_data.bind("<Configure>", update_scroll_region)

        # Bottom bar with centered "Add Color" and "Apply" buttons
        bottom_bar = tk.Frame(data_tab, bg="#e0e0e0", pady=5)
        bottom_bar.pack(fill="x", side="bottom")

        button_container = tk.Frame(bottom_bar, bg="#e0e0e0")  # Center container for buttons
        button_container.pack(pady=5)

        add_button = tk.Button(
            button_container, text="Add Color", font=("Helvetica", 12, "bold"),
            bg="#d4f4d2", command=lambda: self.addColor_data_window()
        )
        add_button.pack(side="left", padx=20)

        apply_button = tk.Button(
            button_container, text="Apply", font=("Helvetica", 12, "bold"),
            bg="#cce5ff", command=lambda: self.apply_changes()
        )
        apply_button.pack(side="left", padx=20)





        # Additional variables
        self.rgb_data = []  # RGB data for 3D visualization
        self.graph_widget = None  # Track 3D graph widget state

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
                "Version 0.1\n\n"
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

        self.selected_centroids = self.color_data
        self.selected_hex_color = self.hex_color
        self.selected_proto = self.prototypes
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

        if filename:
            # Activate the 'Original Image' option for all open windows
            if hasattr(self, 'floating_images') and self.floating_images:
                for window_id in self.floating_images.keys():
                    self.show_original_image(window_id)

            self.file_base_name = os.path.splitext(os.path.basename(filename))[0]

            extension = os.path.splitext(filename)[1]
            if extension == '.cns':
                # Read the file and prepare color data
                input_class = Input.instance(extension)
                self.color_data = input_class.read_file(filename)

                self.display_data_window()
                self.update_volumes()

            elif extension == '.fcs':
                input_class = Input.instance(extension)
                self.color_data, self.fuzzy_color_space = input_class.read_file(filename)

                self.cores = self.fuzzy_color_space.get_cores()
                self.supports = self.fuzzy_color_space.get_supports()
                self.prototypes = self.fuzzy_color_space.get_prototypes()

                self.display_data_window()
                self.update_prototypes_info()

            else:
                messagebox.showwarning("File Error", "Unsupported file format.")
                        

        else:
            # Notify the user if no file was selected
            messagebox.showwarning("No File Selected", "No file was selected.")


    
    def create_color_space(self):
        # Get selected colors and their LAB values
        selected_colors_lab = {
            name: np.array([data["lab"]["L"], data["lab"]["A"], data["lab"]["B"]]) if isinstance(data["lab"], dict) else np.array(data["lab"])
            for name, data in self.color_checks.items() if data["var"].get()
        }

        if len(selected_colors_lab) < 2:
            messagebox.showwarning("Warning", "You must select at least two color.")
        
        else:
            # Ask the user to enter the name for the color space
            popup = tk.Toplevel(self.root)  # Create a secondary window
            popup.title("Color Space Name")
            self.center_popup(popup, 300, 100)
            tk.Label(popup, text="Name for the fuzzy color space:").pack(pady=5)
            name_entry = tk.Entry(popup)
            name_entry.pack(pady=5)

            name = tk.StringVar()

            def on_ok():
                name.set(name_entry.get())  # Set the value in the StringVar
                popup.destroy()

                self.save_cs(name.get(), selected_colors_lab)

            # OK button
            ok_button = tk.Button(popup, text="OK", command=on_ok)
            ok_button.pack(pady=5)

            popup.deiconify()

    def save_cs(self, name, selected_colors_lab):
        self.show_loading()  # Mostrar indicador de carga

        def update_progress(current_line, total_lines):
            """Actualiza la barra de progreso en función de las líneas escritas."""
            progress_percentage = (current_line / total_lines) * 100
            self.progress["value"] = progress_percentage
            self.load_window.update_idletasks()  # Refresca la UI

        def run_save_process():
            """Función que guarda el archivo en un hilo separado."""
            try:
                input_class = Input.instance('.fcs')
                input_class.write_file(name, selected_colors_lab, progress_callback=update_progress)
            except Exception as e:
                tk.messagebox.showwarning("Error", f"Error en run_save_process: {e}")
                return
            finally:
                self.load_window.after(0, self.hide_loading)
                self.load_window.after(0, lambda: messagebox.showinfo("Color Space Created", f"Color Space '{name}' created."))

        threading.Thread(target=run_save_process).start()


    def addColor(self, window, colors):
        popup = tk.Toplevel(window)
        popup.title("Add New Color")
        popup.geometry("500x500")
        popup.resizable(False, False)
        popup.transient(window)
        popup.grab_set()

        self.center_popup(popup, 500, 300)

        color_name_var = tk.StringVar()
        l_value_var = tk.StringVar()
        a_value_var = tk.StringVar()
        b_value_var = tk.StringVar()

        result = {"color_name": None, "lab": None}

        ttk.Label(popup, text="Add New Color", font=("Helvetica", 14, "bold")).pack(pady=10)
        ttk.Label(popup, text="Enter the LAB values and the color name:").pack(pady=5)

        form_frame = ttk.Frame(popup)
        form_frame.pack(padx=20, pady=10)

        ttk.Label(form_frame, text="Color Name:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(form_frame, textvariable=color_name_var, width=30).grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(form_frame, text="L Value (0-100):").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(form_frame, textvariable=l_value_var, width=10).grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(form_frame, text="A Value (-128 to 127):").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(form_frame, textvariable=a_value_var, width=10).grid(row=2, column=1, padx=5, pady=5)

        ttk.Label(form_frame, text="B Value (-128 to 127):").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(form_frame, textvariable=b_value_var, width=10).grid(row=3, column=1, padx=5, pady=5)

        def confirm_color():
            try:
                color_name = color_name_var.get().strip()
                l_value = float(l_value_var.get())
                a_value = float(a_value_var.get())
                b_value = float(b_value_var.get())

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

                result["color_name"] = color_name
                result["lab"] = {"L": l_value, "A": a_value, "B": b_value}

                colors[color_name] = {"lab": result["lab"]}
                popup.destroy()

            except ValueError as e:
                messagebox.showerror("Invalid Input", str(e))

        def browse_color():
            """Abre una ventana con una rueda de colores para seleccionar un color."""
            color_picker = tk.Toplevel()
            color_picker.title("Select a Color")
            color_picker.geometry("350x450")
            color_picker.transient(popup)
            color_picker.grab_set()

            # Posicionar la ventana a la derecha de "Add New Color"
            x_offset = popup.winfo_x() + popup.winfo_width() + 10
            y_offset = popup.winfo_y()
            color_picker.geometry(f"350x450+{x_offset}+{y_offset}")

            canvas_size = 300
            center = canvas_size // 2
            radius = center - 5

            def hsv_to_rgb(h, s, v):
                """Convierte HSV a RGB en escala 0-255."""
                r, g, b = colorsys.hsv_to_rgb(h, s, v)
                return int(r * 255), int(g * 255), int(b * 255)

            def draw_color_wheel():
                """Dibuja la rueda de colores en el Canvas."""
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
                """Obtiene el color seleccionado al hacer clic en la rueda."""
                x, y = event.x, event.y
                dx, dy = x - center, y - center
                dist = math.sqrt(dx**2 + dy**2)

                if dist <= radius:
                    angle = math.atan2(dy, dx)
                    hue = (angle / (2 * math.pi)) % 1
                    r, g, b = hsv_to_rgb(hue, 1, 1)
                    color_hex = f'#{r:02x}{g:02x}{b:02x}'

                    preview_canvas.config(bg=color_hex)

                    # Convertir a LAB
                    rgb = np.array([[r, g, b]]) / 255
                    lab = color.rgb2lab(rgb.reshape((1, 1, 3)))[0][0]

                    # Actualizar los valores en la ventana principal
                    l_value_var.set(f"{lab[0]:.2f}")
                    a_value_var.set(f"{lab[1]:.2f}")
                    b_value_var.set(f"{lab[2]:.2f}")

            def confirm_selection():
                color_picker.destroy()

            canvas = tk.Canvas(color_picker, width=canvas_size, height=canvas_size)
            canvas.pack()
            draw_color_wheel()
            canvas.bind("<Button-1>", on_click)

            preview_canvas = tk.Canvas(color_picker, width=100, height=50, bg="white")
            preview_canvas.pack(pady=10)

            ttk.Button(color_picker, text="Confirm", command=confirm_selection).pack(pady=10)

        button_frame = ttk.Frame(popup)
        button_frame.pack(pady=20)

        ttk.Button(button_frame, text="Add", command=confirm_color, style="Accent.TButton").pack(side="left", padx=10)
        ttk.Button(button_frame, text="Browse Color", command=browse_color, style="Accent.TButton").pack(side="left", padx=10)
        ttk.Button(button_frame, text="Cancel", command=popup.destroy, style="Accent.TButton").pack(side="left", padx=10)

        popup.wait_window()
        return result["color_name"], result["lab"]




    def addColor_create_fcs(self, window, colors):
        color_name, new_color = self.addColor(window, colors)
        # Actualizar la interfaz
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
        color_space_path = os.path.join(os.getcwd(), 'fuzzy_color_spaces\\cns\\BASIC.cns')
        colors = utils_structure.load_color_data(color_space_path)

        # Create a popup window for color selection
        popup, self.scroll_palette_create_fcs = utils_structure.create_popup_window(
            parent=self.root,
            title="Select colors for your Color Space",
            width=400,
            height=500,
            header_text="Select colors for your Color Space"
        )

        # Center the popup
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

        ttk.Button(
            button_frame,
            text="Add Color",
            command=lambda: self.addColor_create_fcs(popup, colors),
            style="Accent.TButton"
        ).pack(side="left", padx=20)

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
        """
        # Verify if there are available images to display
        if not hasattr(self, "load_images_names") or not self.load_images_names:
            tk.messagebox.showinfo("No Images", "No images are currently available to display.")
            return

        # Create a popup window for image selection
        popup, listbox = utils_structure.create_selection_popup(
            parent=self.image_canvas,
            title="Select an Image",
            width=200,
            height=200,
            items=[os.path.basename(filename) for filename in self.load_images_names.values()]
        )

        # Center the popup
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
            option = self.model_3d_option.get()  # Get the selected option value
            
            # Dictionary to map the options to their corresponding functions
            option_map = {
                "Representative": lambda: Visual_tools.plot_all_centroids(self.file_base_name, self.selected_centroids, self.selected_hex_color),
                "0.5-cut": lambda: Visual_tools.plot_all_prototypes(self.selected_proto, self.volume_limits, self.hex_color),
                "Core": lambda: Visual_tools.plot_all_prototypes(self.selected_core, self.volume_limits, self.hex_color),
                "Support": lambda: Visual_tools.plot_all_prototypes(self.selected_support, self.volume_limits, self.hex_color),
            }

            # If the selected option is in the dictionary, generate and draw the figure
            if option in option_map:
                fig = option_map[option]()  # Call the corresponding function
                self.draw_model_3D(fig)  # Pass the figure to draw it on the Tkinter Canvas




    def draw_model_3D(self, fig):
        """Draws the 3D plot on the Tkinter canvas."""
        if self.graph_widget:  # Check if a previous graph exists
            self.graph_widget.get_tk_widget().destroy()  # Destroy the previous widget

        # Create a new matplotlib widget and draw the figure
        self.graph_widget = FigureCanvasTkAgg(fig, master=self.Canvas1)
        self.graph_widget.draw()  # Draw the figure
        self.graph_widget.get_tk_widget().pack(fill="both", expand=True)  # Pack the widget into the canvas

        # Display the color selection buttons
        self.display_color_buttons(self.color_matrix)

    

    def select_all_color(self):
        if self.COLOR_SPACE:
            """Handles the 'select all' option for colors."""
            self.selected_centroids = self.color_data
            self.selected_hex_color = self.hex_color
            self.selected_proto = self.prototypes
            self.selected_core = self.cores
            self.selected_support = self.supports

            # Uncheck all the color selection buttons
            for _, var in self.selected_colors.items():
                var.set(False)
            
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

        # Update the selected colors and prototypes
        self.selected_hex_color = {
            hex_color_key: lab_value for index in selected_indices
            for hex_color_key, lab_value in self.hex_color.items()
            if np.array_equal(lab_value, self.color_data[keys[index]]['positive_prototype'])
        }
        self.selected_proto = [self.prototypes[i] for i in selected_indices]
        self.selected_core = [self.cores[i] for i in selected_indices]
        self.selected_support = [self.supports[i] for i in selected_indices]
        
        self.selected_centroids = selected_centroids
        self.on_option_select()  # Redraw the 3D model based on the selected colors


        

    def display_color_buttons(self, colors):
        """Displays color selection checkboxes."""
        # Store previously selected colors if they exist
        selected_colors = {color for color, var in self.selected_colors.items() if var.get()} if hasattr(self, 'selected_colors') else set()

        # Remove the old buttons if they exist
        if hasattr(self, 'color_buttons'):
            for button in self.color_buttons:
                button.destroy()

        # Reinitialize the color variables and buttons list
        self.selected_colors = {}
        self.color_buttons = []

        # Create a checkbox for each color inside the scrollable inner_frame
        for color in colors:
            is_selected = color in selected_colors  # Check if the color was previously selected

            # Create a BooleanVar for the checkbox state
            self.selected_colors[color] = tk.BooleanVar(value=is_selected)

            # Create the checkbox button
            button = tk.Checkbutton(
                self.inner_frame,  # Use the inner_frame for scrollable content
                text=color,
                variable=self.selected_colors[color],  # Variable for the checkbox state
                bg="gray95",  # Button background color
                font=("Arial", 10),
                onvalue=True,  # Value when checked
                offvalue=False,  # Value when unchecked
                command=lambda c=color: self.select_color(),  # Call select_color on change
            )
            button.pack(anchor="w", pady=2, padx=10)  # Pack the button into the UI frame
            
            self.color_buttons.append(button)  # Store the created button

        # Update the scrollregion of the canvas to fit new content
        self.scrollable_canvas.update_idletasks()
        self.scrollable_canvas.configure(scrollregion=self.scrollable_canvas.bbox("all"))














    ########################################################################################### Funtions Data ###########################################################################################
    # ADD IF FCS
    def display_data_window(self):
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
            lab = color_value['positive_prototype']  # Extract LAB color values
            lab = np.array(lab)  # Convert to numpy array
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
            rgb_data = tuple(map(lambda x: int(x * 255), color.lab2rgb([color_value['positive_prototype']])[0]))
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
            messagebox.showwarning("Cannot Remove Color", "At least two colors must remain. The color was not removed.")
            return  
        
        # Get the name of the color to remove using the provided index
        color_name = self.color_matrix[index]
        
        # Check if the color exists in color_data
        if color_name in self.color_data:
            # Iterate over other colors to remove the corresponding negative prototype
            for other_color, data in self.color_data.items():
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
        """Aplica los cambios hechos en la lista de colores."""
        






















    ########################################################################################### Functions Image Display ###########################################################################################
    def open_image(self):
        """Allows the user to select an image file and display its colors in columns with a scrollbar."""
        # Set the initial directory to 'image_test\\VITA_CLASSICAL\\' within the current working directory
        initial_directory = os.getcwd()
        initial_directory = os.path.join(initial_directory, 'image_test\\VITA_CLASSICAL\\')
        
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
        """Creates a floating window with the selected image, a title bar, and a dropdown menu."""
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
        self.MEMBERDEGREE[window_id] = True if self.COLOR_SPACE else False
        self.ORIGINAL_IMG[window_id] = False

        # Load the image from the selected file
        img = Image.open(filename)
        original_width, original_height = img.size  # Get the original dimensions of the image

        # Set the desired size for the rectangle (window) where the image will be displayed
        rect_width = 250
        rect_height = 250

        # Calculate the maximum scale factor to fit the image within the defined rectangle size without distortion
        scale_width = rect_width / original_width
        scale_height = rect_height / original_height

        # Use the smaller scale to maintain the aspect ratio
        scale = min(scale_width, scale_height)

        # Calculate the new dimensions of the image after scaling
        new_width = int(original_width * scale)
        new_height = int(original_height * scale)

        # Resize the image using the new dimensions
        img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Store the resized image dimensions in a dictionary for later reference
        if not hasattr(self, "image_dimensions"):
            self.image_dimensions = {}  # Initialize the dictionary if it doesn't exist
            self.original_image_dimensions = {}
        self.original_image_dimensions[window_id] = (original_width, original_height)
        self.image_dimensions[window_id] = (new_width, new_height)

        # Update the rectangle dimensions to match the resized image
        rect_width = new_width
        rect_height = new_height

        # Create a dictionary to store the image
        self.images[window_id] = img_resized
        img_tk = ImageTk.PhotoImage(img_resized)

        # Initialize the dictionaries to store floating images and frames if they don't exist
        if not hasattr(self, "floating_images"):
            self.floating_images = {}
            self.original_images = {}

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
            # Remove all elements associated with the window ID from the canvas
            self.image_canvas.delete(window_id)
            
            # Remove the image reference from the dictionary
            del self.floating_images[window_id]

            # If there are any associated proto_options, destroy and remove them as well
            if hasattr(self, "proto_options") and window_id in self.proto_options:
                if self.proto_options[window_id].winfo_exists():
                    self.proto_options[window_id].destroy()
                del self.proto_options[window_id]
            
            # Remove the window ID from load_images_names
            if hasattr(self, "load_images_names") and window_id in self.load_images_names:
                del self.load_images_names[window_id]


        # Function to show the dropdown menu when the arrow button is clicked
        def show_menu_image(event):
            """Displays a context menu with options for the floating window (e.g., Original Image, Color Mapping)."""
            # Create a new menu instance
            menu = Menu(self.root, tearoff=0)
            
            # Add the "Original Image" option to the menu, which is enabled if the window shows the original image
            menu.add_command(
                label="Original Image", 
                state=NORMAL if self.ORIGINAL_IMG[window_id] else DISABLED,  # Enable or disable based on the state
                command=lambda: self.show_original_image(window_id)  # Function to show the original image
            )

            menu.add_separator()  # Add a separator line in the menu

            # Add the "Color Mapping" option to the menu, which is enabled based on the color mapping state
            menu.add_command(
                label="Color Mapping",
                state=NORMAL if self.MEMBERDEGREE[window_id] else DISABLED,  # Enable or disable based on the state
                command=lambda: self.plot_proto_options(window_id)  # Function to plot color mapping options
            )
            
            # Display the menu at the location of the mouse click
            menu.post(event.x_root, event.y_root)

        # Function to make the floating window movable
        def start_move(event):
            """Store the initial position when the mouse is pressed on the window."""
            self.last_x, self.last_y = event.x, event.y  # Store initial x and y coordinates for movement

        def move_window(event):
            """Move the floating window based on the mouse drag."""
            # Calculate the change in position
            dx, dy = event.x - self.last_x, event.y - self.last_y

            # Move all elements associated with the window_id on the canvas
            self.image_canvas.move(window_id, dx, dy)

            # Raise all associated elements to the front so they are not obscured
            self.image_canvas.tag_raise(window_id)  # Bring the window itself to the front
            self.image_canvas.tag_raise(f"{window_id}_close_button")  # Bring the close button to the front
            self.image_canvas.tag_raise(f"{window_id}_arrow_button")  # Bring the arrow button to the front
            self.image_canvas.tag_raise(f"{window_id}_image")  # Bring the image to the front

            # Move the associated proto_options window if it exists
            if hasattr(self, "proto_options") and window_id in self.proto_options:
                proto_option_frame = self.proto_options[window_id]
                
                if proto_option_frame.winfo_exists():  # If the proto_option window exists
                    # Get the current bounding box of the window on the canvas
                    items = self.image_canvas.find_withtag(window_id)
                    if items:
                        # Get the coordinates of the bounding box (x1, y1, x2, y2)
                        x1, y1, x2, y2 = self.image_canvas.bbox(items[0])
                        
                        # Set the new x and y position of the proto_option window based on the main window's position
                        frame_x = x2 + 10  # Position the proto_option to the right of the image
                        frame_y = y1  # Keep the same vertical position as the main window

                        # Ensure the proto_option stays within the canvas bounds
                        canvas_width = self.image_canvas.winfo_width()
                        canvas_height = self.image_canvas.winfo_height()

                        if frame_x + 120 > canvas_width:  # Avoid moving off the right side of the canvas
                            frame_x = canvas_width - 120

                        if frame_y + 150 > canvas_height:  # Avoid moving off the bottom of the canvas
                            frame_y = canvas_height - 150

                        # Move the proto_option window to the new position
                        proto_option_frame.place(x=frame_x, y=frame_y)
                        proto_option_frame.lift()  # Raise the proto_option window to the front

            # Update the coordinates for the next move event
            self.last_x, self.last_y = event.x, event.y

        def get_pixel_value(event, window_id=window_id):
            """Obtiene el valor del píxel donde se hizo clic en la imagen, considerando el movimiento de la ventana."""
            img = self.images[window_id]  
            
            # Obtener dimensiones redimensionadas
            resized_width, resized_height = self.image_dimensions[window_id]
            
            # Obtener dimensiones originales
            original_width, original_height = img.size

            # Obtener la posición absoluta del clic en el Canvas
            abs_x = self.image_canvas.canvasx(event.x)
            abs_y = self.image_canvas.canvasy(event.y)

            # Obtener la posición actual de la imagen en el Canvas
            image_items = self.image_canvas.find_withtag(f"{window_id}_click_image")
            if not image_items:
                tk.messagebox.showwarning("No window", f"No floating window found with id {window_id}")
                return 

            # Bounding box de la imagen
            x1, y1, _, _ = self.image_canvas.bbox(image_items[0])

            # 📏 Ajustar las coordenadas del clic en función del movimiento
            relative_x = abs_x - x1
            relative_y = abs_y - y1

            # Escalar las coordenadas
            scale_x = original_width / resized_width
            scale_y = original_height / resized_height

            x_original = int(relative_x * scale_x)
            y_original = int(relative_y * scale_y)

            # Verificar que las coordenadas estén dentro de la imagen original
            if 0 <= x_original < original_width and 0 <= y_original < original_height:
                # Obtener el valor del píxel en la imagen original
                pixel_value = img.getpixel((x_original, y_original))
                if len(pixel_value) == 4:
                    pixel_value = pixel_value[:3]

                pixel_rgb_np = np.array([[pixel_value]], dtype=np.uint8)
                pixel_lab = color.rgb2lab(pixel_rgb_np)[0][0]

                # print(f"Coordenadas: ({x_original}, {y_original}), Valor LAB: {pixel_value}")
                
                if self.COLOR_SPACE:
                    self.display_pixel_value(x_original, y_original, pixel_lab)

            # Evitar propagación del evento para que no mueva la ventana
            return "break"



        


        # Bind events for moving the window
        self.image_canvas.tag_bind(window_id, "<Button-1>", start_move)  # When mouse is pressed, start moving
        self.image_canvas.tag_bind(window_id, "<B1-Motion>", move_window)  # When mouse is dragged, move the window

        # Bind events for the close button
        self.image_canvas.tag_bind(f"{window_id}_close_button", "<Button-1>", close_window)  # Close window on click

        # Bind events for click 
        self.image_canvas.tag_bind(f"{window_id}_click_image", "<Button-1>", get_pixel_value)
        # label.bind("<Button-1>", lambda event, window_id=window_id: get_pixel_value(event, window_id))

        # Bind events for the arrow button (to show the context menu)
        self.image_canvas.tag_bind(f"{window_id}_arrow_button", "<Button-1>", show_menu_image)  # Show menu on click




    def display_pixel_value(self, x_original, y_original, pixel_lab):
            """Muestra el valor del píxel en LAB y sus coordenadas dentro de un frame en la parte inferior."""
        
            # Si el frame no existe, créalo
            if not hasattr(self, "lab_value_frame"):
                self.lab_value_frame = tk.Frame(self.Canvas1, bg="lightgray", height=40)
                self.lab_value_frame.pack(side="bottom", fill="x", padx=10, pady=5)

                self.lab_value_label = tk.Label(self.lab_value_frame, text="", bg="lightgray", font=("Arial", 12), anchor="w")
                self.lab_value_label.pack(pady=5, padx=10)

            # Actualizar el Label con los nuevos valores LAB y las coordenadas
            lab_text = f"Coordenadas: ({x_original}, {y_original}) | LAB: {pixel_lab[0]:.2f}, {pixel_lab[1]:.2f}, {pixel_lab[2]:.2f}"
            self.lab_value_label.config(text=lab_text)







    def add_new_image_colors(self, popup, colors, threshold, min_samples):
        """
        Permite al usuario seleccionar otra imagen y añade los colores detectados a la lista actual.
        """
        unique_ids = {id.get("source_image") for id in colors}
        if not hasattr(self, "load_images_names") or not self.load_images_names:
            tk.messagebox.showinfo("No Images", "No images are currently available to display.")
            return
        
        available_image_ids = [
            image_id for image_id in self.images.keys() 
            if image_id not in unique_ids
        ]

        if not available_image_ids:
            tk.messagebox.showinfo("No Available Images", "All images have already been selected.")
            return
        
        available_image_names = [
            self.load_images_names[image_id] for image_id in available_image_ids if image_id in self.load_images_names
        ]


        # Crear ventana emergente para seleccionar nueva imagen
        select_popup, listbox = utils_structure.create_selection_popup(
            parent=popup,
            title="Select Another Image",
            width=200,
            height=200,
            items=[os.path.basename(filename) for filename in available_image_names]
        )

        self.center_popup(select_popup, 200, 200)

        # Bind para manejar la selección de la imagen y actualizar la lista de colores
        listbox.bind(
            "<<ListboxSelect>>",
            lambda event: utils_structure.handle_image_selection(
                event=event,
                listbox=listbox,
                popup=select_popup,
                images_names=self.load_images_names,
                callback=lambda window_id: [self.get_fuzzy_color_space_merge(window_id, colors, threshold, min_samples), popup.destroy()]
            )
        )


    def display_detected_colors(self, colors, threshold, min_samples):
        # Crear ventana emergente
        popup = tk.Toplevel(self.root)
        popup.title("Detected Colors")
        popup.configure(bg="#f5f5f5")

        # Centrar la ventana emergente
        self.center_popup(popup, 500, 600)

        # Encabezado
        tk.Label(
            popup,
            text="Detected Colors",
            font=("Helvetica", 14, "bold"),
            bg="#f5f5f5"
        ).pack(pady=15)

        # Umbral y controles
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

        # Frame para mostrar los colores con scrollbar
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
            frame.destroy()  # Eliminar la fila del color
            colors.pop(index)  # Eliminar el color de la lista

            # Eliminar la entrada correspondiente sin reconstruir el diccionario
            self.color_entry_detect.pop(f"color_{index}", None)

            # Actualizar los índices en self.color_entry_detect
            for new_index, old_key in enumerate(list(self.color_entry_detect.keys())):
                self.color_entry_detect[f"color_{new_index}"] = self.color_entry_detect.pop(old_key)

            # Reorganizar los frames y sus botones después de eliminar
            update_color_frames()

        def update_color_frames():
            # Guardar los nombres personalizados antes de limpiar
            previous_names = {key: entry.get() for key, entry in self.color_entry_detect.items()}

            # Limpiar el contenedor de colores antes de volver a dibujarlos
            for widget in scrollable_frame.winfo_children():
                widget.destroy()

            self.color_entry_detect.clear()  # Reiniciar el diccionario de entradas

            for i, dect_color in enumerate(colors):
                rgb = dect_color["rgb"]
                lab = color.rgb2lab(np.array(dect_color["rgb"], dtype=np.uint8).reshape(1, 1, 3) / 255)
                default_name = f"Color {i + 1}"  # Nombre predeterminado

                frame = ttk.Frame(scrollable_frame)
                frame.pack(fill="x", pady=8, padx=10)

                # Muestra del color
                color_box = tk.Label(frame, bg=utils_structure.rgb_to_hex(rgb), width=4, height=2, relief="solid", bd=1)
                color_box.pack(side="left", padx=10)

                # Recuperar el nombre guardado o usar el predeterminado
                entry_name_key = f"color_{i}"
                saved_name = previous_names.get(entry_name_key, default_name)

                # Campo de entrada para el nombre del color
                entry = ttk.Entry(frame, font=("Helvetica", 12))
                entry.insert(0, saved_name)  # Insertar el nombre recuperado o predeterminado
                entry.pack(side="left", padx=10, fill="x", expand=True)
                self.color_entry_detect[entry_name_key] = entry

                # Valores LAB
                lab = lab[0, 0]
                lab_values = f"L: {lab[0]:.1f}, A: {lab[1]:.1f}, B: {lab[2]:.1f}"
                tk.Label(
                    frame,
                    text=lab_values,
                    font=("Helvetica", 10, "italic"),
                    bg="#f5f5f5"
                ).pack(side="left", padx=10)

                # Botón para eliminar color
                remove_button = tk.Button(
                    frame,
                    text="❌",
                    font=("Helvetica", 10, "bold"),
                    command=lambda f=frame, idx=i: remove_detect_color(f, idx),
                    bg="#f5f5f5",
                    relief="flat"
                )
                remove_button.pack(side="right", padx=5)

        # Mostrar los colores inicialmente
        update_color_frames()

        # Botones de acción
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
            command=lambda: self.process_fcs(colors),
            style="Accent.TButton"
        )
        save_button.pack(side="left", padx=20)

        # Estilo para botones
        style = ttk.Style()
        style.configure("Accent.TButton", font=("Helvetica", 10, "bold"), padding=10)




    # CHANGE TO .FCS FILE
    def process_fcs(self, colors):
        """
        Saves the names of the colors edited by the user in a file with a .cns extension.
        """
        if len(self.color_entry_detect) < 2:
            tk.messagebox.showwarning("Not enough colors", "You must select at least two colors to create the Color Space")
            return

        # Ask the user to enter the name for the color space
        popup = tk.Toplevel(self.root)  # Create a secondary window
        popup.title("Input")
        self.center_popup(popup, 300, 100)
        tk.Label(popup, text="Name for the fuzzy color space:").pack(pady=5)
        name_entry = tk.Entry(popup)
        name_entry.pack(pady=5)

        name = tk.StringVar()

        def on_ok():
            name.set(name_entry.get())  # Set the value in the StringVar
            popup.destroy()

            self.save_fcs(name.get(), colors)

        # OK button
        ok_button = tk.Button(popup, text="OK", command=on_ok)
        ok_button.pack(pady=5)

        popup.deiconify()

    def save_fcs(self, name, colors):
        color_dict = {key: np.array(colors[idx]['lab']) for idx, key in enumerate(self.color_entry_detect)}
        self.show_loading()  # Mostrar indicador de carga

        def update_progress(current_line, total_lines):
            """Actualiza la barra de progreso en función de las líneas escritas."""
            progress_percentage = (current_line / total_lines) * 100
            self.progress["value"] = progress_percentage
            self.load_window.update_idletasks()  # Refresca la UI

        def run_save_process():
            """Función que guarda el archivo en un hilo separado."""
            try:
                input_class = Input.instance('.fcs')
                input_class.write_file(name, color_dict, progress_callback=update_progress)
            except Exception as e:
                tk.messagebox.showwarning("Error", f"Error en run_save_process: {e}")
                return

            finally:
                self.load_window.after(0, self.hide_loading)
                self.load_window.after(0, lambda: messagebox.showinfo("Color Space Created", f"Color Space '{name}' created."))

        threading.Thread(target=run_save_process).start()




    def get_fuzzy_color_space(self, window_id, threshold=0.5, min_samples=160):
        image = self.images[window_id]
        colors = utils_structure.get_fuzzy_color_space(window_id, image, threshold, min_samples)

        # Añadir el identificador de la imagen a cada color si no lo tiene
        for id in colors:
            if "source_image" not in id:
                id["source_image"] = window_id

        self.display_detected_colors(colors, threshold, min_samples)


    def get_fuzzy_color_space_merge(self, new_window_id, colors, threshold, min_samples):
        """
        Obtiene los colores de la nueva imagen y los añade a la lista de colores actual.
        """
        if new_window_id and not any(id.get("source_image") == new_window_id for id in colors):
            new_colors = utils_structure.get_fuzzy_color_space(new_window_id, self.images[new_window_id], threshold, min_samples)

            for id in new_colors:  # Itera sobre los nuevos colores
                if "source_image" not in id:  
                    id["source_image"] = new_window_id 
                
            colors.extend(new_colors)  
            self.display_detected_colors(colors, threshold, min_samples)


    def recalculate(self, window_id, colors, threshold, min_samples):
        # Evitar errores de nombres previos
        self.color_entry_detect = {}
        # Filtrar los colores que no tienen el mismo ID que la ventana actual
        filtered_colors = [id for id in colors if id.get("source_image") != window_id]
        self.get_fuzzy_color_space_merge(window_id, filtered_colors, threshold, min_samples)


    def get_fuzzy_color_space_recalculate(self, colors, threshold=0.5, min_samples=160, popup = None):
        # Verificar cuántos IDs diferentes hay en colors
        unique_ids = {id.get("source_image") for id in colors}

        if len(unique_ids) > 1:
            # Si hay más de 2 IDs diferentes, preguntar al usuario cuál imagen quiere recalcular
            popup, listbox = utils_structure.create_selection_popup(
                parent=self.image_canvas,
                title="Select an Image",
                width=200,
                height=200,
                items=[os.path.basename(filename) for filename in self.load_images_names.values()]
            )

            self.center_popup(popup, 200, 200)

            # Bind para manejar la selección de la imagen
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
            self.get_fuzzy_color_space(unique_ids.pop(), threshold, min_samples)
            popup.destroy()




    def plot_proto_options(self, window_id):
        """Creates a Frame within image_canvas with Radiobuttons and scrollbars for selecting color options."""
        # Find the window associated with the window_id to ensure it exists
        items = self.image_canvas.find_withtag(window_id)
        
        # If no window is found with the given window_id, print an error message and return
        if not items:
            tk.messagebox.showwarning("No window", f"No floating window found with id {window_id}")
            return

        # Set initial states for the member degree and original image for the window
        self.MEMBERDEGREE[window_id] = False
        self.ORIGINAL_IMG[window_id] = True

        # Initialize the proto_options dictionary if it does not exist
        if not hasattr(self, "proto_options"):
            self.proto_options = {}

        # If a proto_options window already exists for this window_id, destroy it first
        if window_id in self.proto_options and self.proto_options[window_id].winfo_exists():
            self.proto_options[window_id].destroy()

        # Create a new proto_options frame for the window
        proto_options = tk.Frame(self.image_canvas, bg="white", relief="solid", bd=1)
        self.proto_options[window_id] = proto_options

        # Create the canvas within the proto_options frame and set up its grid
        self.canvas = tk.Canvas(proto_options, bg="white")
        self.canvas.grid(row=0, column=0, sticky="nsew")

        # Create an inner frame inside the canvas to hold the radio buttons
        self.inner_frame = tk.Frame(self.canvas, bg="white")
        self.canvas.create_window((0, 0), window=self.inner_frame, anchor="nw")

        # Initialize a variable to hold the selected color (default value is '0')
        self.current_proto = tk.StringVar(value=0)

        # Create Radiobuttons for each color in the color matrix
        colors = self.color_matrix
        for color in colors:
            rb = tk.Radiobutton(
                self.inner_frame, 
                text=color, 
                variable=self.current_proto, 
                value=color, 
                bg="white", 
                anchor="w", 
                font=("Arial", 10), 
                relief="flat", 
                command=lambda color=color: self.get_proto_percentage(window_id)  # Command to fetch percentage for selected color
            )
            rb.pack(fill="x", padx=5, pady=2)  # Pack each radiobutton with padding

        # Create vertical scrollbar for the proto_options canvas
        self.v_scroll = tk.Scrollbar(proto_options, orient=tk.VERTICAL, command=self.canvas.yview)
        self.v_scroll.grid(row=0, column=1, sticky="ns", padx=5)

        # Create horizontal scrollbar for the proto_options canvas
        self.h_scroll = tk.Scrollbar(proto_options, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.h_scroll.grid(row=1, column=0, sticky="ew", padx=5)
        self.h_scroll.bind("<MouseWheel>", lambda event: self.on_mouse_wheel(event, self.h_scroll))

        # Configure the canvas to respond to the scrollbars
        self.canvas.configure(yscrollcommand=self.v_scroll.set, xscrollcommand=self.h_scroll.set)

        # Update the inner frame's layout and set the scrollable region for the canvas
        self.inner_frame.update_idletasks()
        self.canvas.config(scrollregion=self.canvas.bbox("all"))

        # Make sure the proto_options frame resizes properly when its content changes
        proto_options.grid_rowconfigure(0, weight=1)
        proto_options.grid_columnconfigure(0, weight=1)

        # Position the proto_options frame next to the floating window
        x1, y1, x2, y2 = self.image_canvas.bbox(items[0])  # Get the bounding box of the floating window
        frame_x = x2 + 10  # Position proto_options slightly to the right of the floating window
        frame_y = y1  # Align it vertically with the floating window
        proto_options.place(x=frame_x, y=frame_y, width=100, height=200)  # Place proto_options at calculated position



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
                pos = self.color_matrix.index(self.current_proto.get())

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
                tk.messagebox.showwarning("Error", f"Error in run_process: {e}")
                return

            finally:
                # Hide the loading indicator once processing is complete
                self.hide_loading()

        # Execute the processing function in a separate thread
        threading.Thread(target=run_process).start()



    def display_color_mapping(self, grayscale_image_array, window_id):
        """Displays the generated grayscale image in the graphical interface."""
        try:
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
                tk.messagebox.showwarning("Image Error", f"No image found for window_id: {window_id}")

        except Exception as e:
            tk.messagebox.showwarning("Display Error", f"Error displaying the image: {e}")



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
                        tk.messagebox.showwarning("Window Error", f"Error trying to destroy the proto_options window: {e}")
                        return

                # Find the image item in the canvas using the window_id tag
                image_items = self.image_canvas.find_withtag(f"{window_id}_click_image")

                if image_items:
                    image_id = image_items[0]  # Assuming there's only one image per window_id
                    # Update the image to the original
                    self.image_canvas.itemconfig(image_id, image=img_tk)
                else:
                    tk.messagebox.showwarning("Image Error", f"No canvas image found for window_id: {window_id}")
                    return

                # Reset flags
                self.ORIGINAL_IMG[window_id] = False
                if self.COLOR_SPACE:
                    self.MEMBERDEGREE[window_id] = True

            else:
                tk.messagebox.showwarning("Not Original Image", f"Original image not found for window_id: {window_id}")
                return

        except Exception as e:
            tk.messagebox.showwarning("Display Error", f"Error displaying the original image: {e}")
            return




    












    ########################################################################################### Color Evaluation Functions ###########################################################################################
    def get_umbral_points(self, threshold):
        # Verificar si el espacio de color difuso está cargado
        if not hasattr(self, 'COLOR_SPACE') or not self.COLOR_SPACE:
            messagebox.showwarning("No Color Space", "Please load a fuzzy color space before deploying AT.")
            return

        # Obtener la opción seleccionada en el menú desplegable
        option = self.model_3d_option.get()

        # Mapa de opciones para acceder a los volúmenes correspondientes
        option_map = {
            "Representative": lambda: Visual_tools.plot_all_centroids(self.file_base_name, self.selected_centroids, self.selected_hex_color),
            "Core": self.selected_core,
            "Support": self.selected_support,
            "0.5-cut": self.selected_proto
        }

        if option != 'Representative':
            selected_volume = option_map[option]
            filtered_points = {}  # Diccionario para almacenar los puntos filtrados

            # Iterar sobre cada volumen y su prototipo correspondiente
            for idx, prototype in enumerate(selected_volume):
                positive = prototype.positive

                # Generar puntos dentro del volumen de Voronoi
                points_inside = utils_structure.generate_points_within_volume(prototype.voronoi_volume, step=1.0)
                points_within_threshold = []

                # Filtrar puntos por diferencia de color (deltaE)
                for point in points_inside:
                    point_lab = tuple(point)  # Convertir a formato (L, a, b)
                    delta_e = utils_structure.delta_e_ciede2000(positive, point_lab)

                    if delta_e < threshold:
                        points_within_threshold.append(point)

                filtered_points[f'Volume_{idx}'] = points_within_threshold

                
            fig = Visual_tools.plot_all_prototypes_filtered_points(selected_volume, self.volume_limits, self.hex_color, filtered_points)
            self.draw_model_3D(fig)  # Pass the figure to draw it on the Tkinter Canvas



    def deploy_at(self):
        self.get_umbral_points(0.8)

    def deploy_pt(self):
        self.get_umbral_points(1.8)











def start_up():
    root = tk.Tk()
    app = PyFCSApp(root)
    root.mainloop()

if __name__ == '__main__':
    start_up()

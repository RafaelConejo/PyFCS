import tkinter as tk
from tkinter import ttk, Menu, filedialog, messagebox, Scrollbar, DISABLED, NORMAL
import sys
import os
from skimage import color
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from PIL import Image, ImageTk
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler

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
        fuzzy_menu.add_command(label="New Color Space", command=self.new_color_space)  # Create new color space
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

        # Buttons for image operations
        tk.Button(image_manager_frame, text="Open Image", command=self.open_image).pack(side="left", padx=5)
        tk.Button(image_manager_frame, text="Save Image").pack(side="left", padx=5)

        # "Fuzzy Color Space Manager" section
        fuzzy_manager_frame = tk.LabelFrame(main_frame, text="Fuzzy Color Space Manager", bg="gray95", padx=10, pady=10)
        fuzzy_manager_frame.grid(row=0, column=1, padx=5, pady=5)

        # Buttons for fuzzy color space management
        tk.Button(fuzzy_manager_frame, text="New Color Space", command=self.new_color_space).pack(side="left", padx=5)
        tk.Button(fuzzy_manager_frame, text="Load Color Space", command=self.load_color_space).pack(side="left", padx=5)

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
        self.colors_frame = tk.Frame(model_3d_tab, bg="gray95")
        self.colors_frame.pack(side="right", fill="y", padx=10, pady=10)

        # "Select All" button for color operations
        self.select_all_button = tk.Button(
            self.colors_frame,
            text="Select All",
            bg="lightgray",
            font=("Arial", 10),
            command=self.select_all_color  
        )
        self.select_all_button.pack(pady=5)

        # "Data" tab
        data_tab = tk.Frame(notebook, bg="gray95")
        notebook.add(data_tab, text="Data")

        # Canvas and scrollbar for data display
        self.Canvas2 = tk.Canvas(data_tab, bg="white", borderwidth=2, relief="ridge")
        self.Canvas2.pack(side="left", fill="both", expand=True)

        self.scrollbar = Scrollbar(data_tab, orient="vertical", command=self.Canvas2.yview)
        self.scrollbar.pack(side="right", fill="y")
        self.Canvas2.configure(yscrollcommand=self.scrollbar.set)

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
        Display a loading window to indicate a background process.
        This creates a new small window with a "Loading..." label.
        """
        # Create a new top-level window for the loading message
        self.load_window = tk.Toplevel(self.root)
        self.load_window.title("Loading")
        label = tk.Label(self.load_window, text="Loading...", padx=20, pady=20)
        label.pack()

        # Set size and position for the loading window
        self.load_window.geometry("200x100")

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
        """
        Display the "About" information dialog.
        Delegates the display logic to a utility function for better separation of concerns.
        """
        utils_structure.about_info(self.root)  









    ########################################################################################### Main Functions ###########################################################################################

    def load_color_space(self):
        """
        Allows the user to select a fuzzy color space file and displays its color data in a scrollable table.
        This includes loading the file, extracting the data, and displaying it visually on a canvas.
        """
        # Set the initial directory to the fuzzy_color_spaces folder
        initial_directory = os.path.join(os.getcwd(), 'fuzzy_color_spaces\\')
        filetypes = [("All Files", "*.*")]
        
        # Prompt the user to select a file
        filename = filedialog.askopenfilename(
            title="Select Fuzzy Color Space File",
            initialdir=initial_directory,
            filetypes=filetypes
        )
        
        if filename:
            ################ HERE LOADING ???? #########################################
            # Activate the 'Original Image' option for all open windows
            if hasattr(self, 'floating_images') and self.floating_images:
                for window_id in self.floating_images.keys():
                    self.show_original_image(window_id)
        
            # Read the file and extract color data
            extension = os.path.splitext(filename)[1]
            input_class = Input.instance(extension)
            color_data = input_class.read_file(filename)

            # Clear the Canvas and adjust scroll region for new data
            self.Canvas2.delete("all")
            self.Canvas2.configure(scrollregion=(0, 0, 1000, len(color_data) * 30 + 50))

            # Table column properties
            x_start = 10  # Starting X-coordinate for columns
            y_start = 10  # Starting Y-coordinate for header row
            rect_width, rect_height = 50, 20  # Dimensions of color rectangles

            # Draw table headers
            headers = ["L", "a", "b", "Label", "Color"]
            column_widths = [50, 50, 50, 150, 70]
            for i, header in enumerate(headers):
                self.Canvas2.create_text(
                    x_start + sum(column_widths[:i]) + column_widths[i] / 2, y_start,
                    text=header, anchor="center", font=("Arial", 10, "bold")
                )

            # Offset for data rows
            y_start += 30


            # Generate the Voronoi diagram using color data
            self.volume_limits = ReferenceDomain(0, 100, -128, 127, -128, 127)
            self.prototypes = []

            # Draw color data in rows
            self.hex_color = {}
            self.color_matrix = []
            for color_name, color_value in color_data.items():
                lab = color_value['positive_prototype']
                lab = np.array(lab)
                self.color_matrix.append(color_name)

                # Draw individual columns (L, a, b, Label)
                self.Canvas2.create_text(
                    x_start + column_widths[0] / 2, y_start,
                    text=str(round(lab[0], 2)), anchor="center"
                )
                self.Canvas2.create_text(
                    x_start + column_widths[0] + column_widths[1] / 2, y_start,
                    text=str(round(lab[1], 2)), anchor="center"
                )
                self.Canvas2.create_text(
                    x_start + sum(column_widths[:2]) + column_widths[2] / 2, y_start,
                    text=str(round(lab[2], 2)), anchor="center"
                )
                self.Canvas2.create_text(
                    x_start + sum(column_widths[:3]) + column_widths[3] / 2, y_start,
                    text=color_name, anchor="center"
                )

                # Convert LAB to RGB and store hex colors
                rgb_data = tuple(map(lambda x: int(x * 255), color.lab2rgb([color_value['positive_prototype']])[0]))
                self.hex_color[(f'#{rgb_data[0]:02x}{rgb_data[1]:02x}{rgb_data[2]:02x}')] = lab

                # Draw color rectangle
                self.Canvas2.create_rectangle(
                    x_start + sum(column_widths[:4]) + 10, y_start - rect_height / 2,
                    x_start + sum(column_widths[:4]) + 10 + rect_width, y_start + rect_height / 2,
                    fill=f'#{rgb_data[0]:02x}{rgb_data[1]:02x}{rgb_data[2]:02x}', outline="black"
                )

                # Move to the next row
                y_start += 30


                # Prototype creation
                positive_prototype = color_value['positive_prototype']
                negative_prototypes = color_value['negative_prototypes']
                prototype = Prototype(label=color_name, positive=positive_prototype, negatives=negative_prototypes, add_false=True)
                self.prototypes.append(prototype)
                

            # Create and save the fuzzy color space
            self.fuzzy_color_space = FuzzyColorSpace(space_name=" ", prototypes=self.prototypes)
            self.cores = self.fuzzy_color_space.get_cores()
            self.supports = self.fuzzy_color_space.get_supports()


            # Update 3D graph and app state vars
            self.COLOR_SPACE = True
            self.MEMBERDEGREE = {key: True for key in self.MEMBERDEGREE}
            self.file_base_name = os.path.splitext(os.path.basename(filename))[0]
            self.color_data = color_data

            self.selected_centroids = color_data
            self.colors = self.hex_color
            self.selected_proto = self.prototypes
            self.selected_core = self.cores
            self.selected_support = self.supports
            self.on_option_select()

        else:
            # Notify the user if no file was selected
            messagebox.showwarning("No File Selected", "No file was selected.")



    @staticmethod
    def rgb_to_hex(rgb):
        return "#%02x%02x%02x" % rgb
    
    def create_color_space(self):
        # Get selected colors
        selected_colors = [name for name, var in self.color_checks.items() if var.get()]

        if not selected_colors:
            messagebox.showwarning("Warning", "You must select at least one color.")
            return

        # Ask for the name of the new color space
        name = tk.simpledialog.askstring("Color Space Name", "Enter a name for the new Color Space:")

        if name:
            # Logic for creating the new color space would go here
            messagebox.showinfo("Color Space Created", f"Color Space '{name}' created with the following colors: {', '.join(selected_colors)}")
        else:
            messagebox.showinfo("Cancelled", "Color Space creation was cancelled.")


    

    def new_color_space(self):
        """
        Placeholder logic for creating a new fuzzy color space.
        Displays a message indicating this action.
        """
        color_space_path = os.path.join(os.getcwd(), 'fuzzy_color_spaces\\BASIC.cns') 
        input_class = Input.instance('.cns')
        color_data = input_class.read_file(color_space_path)

        # Convertir los colores a RGB
        colors = {}
        for color_name, color_value in color_data.items():
            lab = np.array(color_value['positive_prototype'])
            rgb = tuple(map(lambda x: int(x * 255), color.lab2rgb([lab])[0]))
            colors[color_name] = {"rgb": rgb, "lab": lab}

        # Crear ventana emergente
        popup = tk.Toplevel(self.root)
        popup.title("Select colors for your Color Space")
        popup.geometry("350x500")
        popup.configure(bg="#f5f5f5")

        # Encabezado
        tk.Label(
            popup,
            text="Select colors for your Color Space",
            font=("Helvetica", 14, "bold"),
            bg="#f5f5f5"
        ).pack(pady=15)

        # Frame para mostrar los colores con scrollbar
        frame_container = ttk.Frame(popup)
        frame_container.pack(pady=10, fill="both", expand=True)

        canvas = tk.Canvas(frame_container, bg="#f5f5f5")
        scrollbar = ttk.Scrollbar(frame_container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Diccionario para almacenar los Checkbuttons
        self.color_checks = {}

        for color_name, data in colors.items():
            rgb = data["rgb"]
            lab = data["lab"]

            frame = ttk.Frame(scrollable_frame)
            frame.pack(fill="x", pady=8, padx=10)

            # Muestra el recuadro del color
            color_box = tk.Label(frame, bg=self.rgb_to_hex(rgb), width=4, height=2, relief="solid", bd=1)
            color_box.pack(side="left", padx=10)

            # Muestra el nombre del color
            tk.Label(
                frame,
                text=color_name,
                font=("Helvetica", 12),
                bg="#f5f5f5"
            ).pack(side="left", padx=10)

            # Muestra los valores LAB
            lab_values = f"L: {lab[0]:.1f}, A: {lab[1]:.1f}, B: {lab[2]:.1f}"
            tk.Label(
                frame,
                text=lab_values,
                font=("Helvetica", 10, "italic"),
                bg="#f5f5f5"
            ).pack(side="left", padx=10)

            # Checkbutton para seleccionar
            var = tk.BooleanVar()
            self.color_checks[color_name] = var
            check = ttk.Checkbutton(frame, variable=var)
            check.pack(side="right", padx=10)

        # Botones de acción
        button_frame = ttk.Frame(popup)
        button_frame.pack(pady=20)

        close_button = ttk.Button(
            button_frame,
            text="Close",
            command=popup.destroy,
            style="Accent.TButton"
        )
        close_button.pack(side="left", padx=20)

        create_button = ttk.Button(
            button_frame,
            text="Create Color Space",
            command=self.create_color_space,
            style="Accent.TButton"
        )
        create_button.pack(side="left", padx=20)

        # Estilo para botones
        style = ttk.Style()
        style.configure("Accent.TButton", font=("Helvetica", 10, "bold"), padding=10)




    ########################################################################################### Funtions Model 3D ###########################################################################################
    def on_option_select(self):
        if self.COLOR_SPACE:  # Check if a color space is loaded
            option = self.model_3d_option.get()  # Get the selected option value
            
            # Dictionary to map the options to their corresponding functions
            option_map = {
                "Representative": lambda: Visual_tools.plot_all_centroids(self.file_base_name, self.selected_centroids, self.colors),
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
        """Handles the 'select all' option for colors."""
        self.selected_centroids = self.color_data
        self.colors = self.hex_color
        self.selected_proto = self.prototypes
        self.selected_core = self.cores
        self.selected_support = self.supports

        # Uncheck all the color selection buttons
        for color, var in self.selected_colors.items():
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
        self.colors = {
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

        # Create a checkbox for each color
        for color in colors:
            is_selected = color in selected_colors  # Check if the color was previously selected

            # Create a BooleanVar for the checkbox state
            self.selected_colors[color] = tk.BooleanVar(value=is_selected)

            # Create the checkbox button
            button = tk.Checkbutton(
                self.colors_frame,
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
        # Generate a unique window ID based on the number of existing images
        window_id = f"floating_{len(self.image_canvas.find_all())}"

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
        self.image_dimensions[window_id] = (new_width, new_height)

        # Update the rectangle dimensions to match the resized image
        rect_width = new_width
        rect_height = new_height

        # Create a dictionary to store the image
        self.images = {}
        self.images[window_id] = img_resized
        img_tk = ImageTk.PhotoImage(img_resized)

        # Initialize the dictionaries to store floating images and frames if they don't exist
        if not hasattr(self, "floating_images"):
            self.floating_images = {}
            self.floating_frames = {}

        # Store the image reference in the floating images dictionary
        self.floating_images[window_id] = img_tk

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

        # Create a frame inside the canvas for displaying the image
        frame = tk.Frame(self.image_canvas, width=rect_width, height=rect_height, bg="white")
        self.floating_frames[window_id] = frame

        # Position the frame within the canvas
        self.image_canvas.create_window(
            x + 10, y + 40, anchor="nw", window=frame, tags=(window_id, "floating", f"{window_id}_image")
        )

        # Display the image inside the frame using a Label widget
        label = tk.Label(frame, image=self.floating_images[window_id], bg="white")
        label.pack(expand=True, fill=tk.BOTH)

        # Function to close the floating window when the close button is clicked
        def close_window(event):
            # Remove all elements associated with the window ID from the canvas
            self.image_canvas.delete(window_id)
            
            # Remove the image reference from the dictionary
            del self.floating_images[window_id]
            
            # Destroy and remove the frame associated with the window ID
            if window_id in self.floating_frames:
                self.floating_frames[window_id].destroy()
                del self.floating_frames[window_id]

            # If there are any associated proto_options, destroy and remove them as well
            if hasattr(self, "proto_options") and window_id in self.proto_options:
                if self.proto_options[window_id].winfo_exists():
                    self.proto_options[window_id].destroy()
                del self.proto_options[window_id]


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

            menu.add_separator()  # Add a separator line in the menu

            # Add the "Color Mapping" option to the menu, which is enabled based on the color mapping state
            menu.add_command(
                label="Get Fuzzy Color Space",
                state=NORMAL,  # Enable or disable based on the state
                command=lambda: self.get_fuzzy_color_space(window_id)  # Function to plot color mapping options
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

            # Ensure that the frame containing the image is also raised to the front
            if window_id in self.floating_frames:
                frame = self.floating_frames[window_id]
                self.image_canvas.tag_raise(f"{window_id}_image")  # Ensure the frame stays on top
                frame.lift()  # Lift the frame above other frames in the canvas

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

        # Bind events for moving the window
        self.image_canvas.tag_bind(window_id, "<Button-1>", start_move)  # When mouse is pressed, start moving
        self.image_canvas.tag_bind(window_id, "<B1-Motion>", move_window)  # When mouse is dragged, move the window

        # Bind events for the close button
        self.image_canvas.tag_bind(f"{window_id}_close_button", "<Button-1>", close_window)  # Close window on click

        # Bind events for the arrow button (to show the context menu)
        self.image_canvas.tag_bind(f"{window_id}_arrow_button", "<Button-1>", show_menu_image)  # Show menu on click








    def display_detected_colors(self, colors):
        """
        Muestra los colores detectados en una ventana con opciones para ver los valores LAB
        y permitir que el usuario cambie el nombre del color.
        """
        # Crear ventana emergente
        popup = tk.Toplevel(self.root)
        popup.title("Detected Colors")
        popup.geometry("400x600")
        popup.configure(bg="#f5f5f5")

        # Encabezado
        tk.Label(
            popup,
            text="Detected Colors",
            font=("Helvetica", 14, "bold"),
            bg="#f5f5f5"
        ).pack(pady=15)

        # Frame para mostrar los colores con scrollbar
        frame_container = ttk.Frame(popup)
        frame_container.pack(pady=10, fill="both", expand=True)

        canvas = tk.Canvas(frame_container, bg="#f5f5f5")
        scrollbar = ttk.Scrollbar(frame_container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Mostrar los colores
        self.color_entries = {}  # Guardar referencias a los campos de entrada

        for i, color in enumerate(colors):
            rgb = color["rgb"]
            lab = color["lab"]
            default_name = f"Color {i + 1}"  # Nombre predeterminado

            frame = ttk.Frame(scrollable_frame)
            frame.pack(fill="x", pady=8, padx=10)

            # Muestra del color
            color_box = tk.Label(frame, bg=self.rgb_to_hex(rgb), width=4, height=2, relief="solid", bd=1)
            color_box.pack(side="left", padx=10)

            # Campo de entrada para el nombre del color
            entry = ttk.Entry(frame, font=("Helvetica", 12))
            entry.insert(0, default_name)  # Nombre inicial
            entry.pack(side="left", padx=10, fill="x", expand=True)
            self.color_entries[f"color_{i}"] = entry

            # Valores LAB
            lab_values = f"L: {lab[0]:.1f}, A: {lab[1]:.1f}, B: {lab[2]:.1f}"
            tk.Label(
                frame,
                text=lab_values,
                font=("Helvetica", 10, "italic"),
                bg="#f5f5f5"
            ).pack(side="left", padx=10)

        # Botones de acción
        button_frame = ttk.Frame(popup)
        button_frame.pack(pady=20)

        close_button = ttk.Button(
            button_frame,
            text="Close",
            command=popup.destroy,
            style="Accent.TButton"
        )
        close_button.pack(side="left", padx=20)

        save_button = ttk.Button(
            button_frame,
            text="Save Colors",
            command=self.save_color_data,
            style="Accent.TButton"
        )
        save_button.pack(side="left", padx=20)

        # Estilo para botones
        style = ttk.Style()
        style.configure("Accent.TButton", font=("Helvetica", 10, "bold"), padding=10)


    def save_color_data(self):
        """
        Guarda los nombres de los colores editados por el usuario.
        """
        for key, entry in self.color_entries.items():
            color_name = entry.get()
            print(f"{key}: {color_name}")


    def get_fuzzy_color_space(self, window_id):
        """
        Detecta los colores principales en una imagen usando clustering DBSCAN
        y muestra los resultados en una ventana con opciones de edición.
        """
        # Buscar la ventana asociada al window_id
        items = self.image_canvas.find_withtag(window_id)

        if not items:
            print(f"No floating window found with id {window_id}")
            return

        # Obtener la imagen asociada al window_id
        image = self.images[window_id]
        img_np = np.array(image)

        # Manejar canal alfa si está presente
        if img_np.shape[-1] == 4:  # Si tiene 4 canales (RGBA)
            img_np = img_np[..., :3]  # Elimina el canal alfa y conserva solo RGB

        # Normalizar los valores de los píxeles
        img_np = img_np / 255.0

        # Convertir la imagen en una lista de píxeles
        pixels = img_np.reshape((-1, 3))

        # Escalar los valores de los colores para clustering
        scaler = StandardScaler()
        scaled_pixels = scaler.fit_transform(pixels)

        # Aplicar clustering DBSCAN
        dbscan = DBSCAN(eps=0.3, min_samples=100)       # AJUSTAR
        labels = dbscan.fit_predict(scaled_pixels)

        # Obtener colores representativos
        unique_labels = set(labels)
        colors = []
        for label in unique_labels:
            if label == -1:  # Ignorar ruido
                continue
            group = pixels[labels == label]
            # Calcular el promedio del grupo y desnormalizar a escala RGB
            mean_color_rgb = tuple((group.mean(axis=0) * 255).astype(int))
            mean_color_lab = group.mean(axis=0)  # LAB ya está normalizado entre 0 y 1
            colors.append({"rgb": mean_color_rgb, "lab": mean_color_lab})

        # Mostrar los colores detectados en una ventana
        self.display_detected_colors(colors)










    def plot_proto_options(self, window_id):
        """Creates a Frame within image_canvas with Radiobuttons and scrollbars for selecting color options."""
        # Find the window associated with the window_id to ensure it exists
        items = self.image_canvas.find_withtag(window_id)
        
        # If no window is found with the given window_id, print an error message and return
        if not items:
            print(f"No floating window found with id {window_id}")
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

        try:
            # Retrieve the index of the selected prototype color from the color matrix
            pos = self.color_matrix.index(self.current_proto.get())

            # Generate the grayscale image based on the selected prototype
            grayscale_image_array = utils_structure.get_proto_percentage(
                prototypes=self.prototypes,        # The prototypes to use for the transformation
                image=self.images[window_id],      # The current image for the window
                fuzzy_color_space=self.fuzzy_color_space,  # The color space for fuzzy mapping
                selected_option=pos                # The selected color option (index)
            )

            # Convert the array into an image format that can be displayed with tkinter
            grayscale_image = Image.fromarray(grayscale_image_array)

            # Resize the grayscale image to match the dimensions of the original image
            (new_width, new_height) = self.image_dimensions[window_id]
            grayscale_image = grayscale_image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Convert the image into a PhotoImage object for tkinter compatibility
            img_tk = ImageTk.PhotoImage(grayscale_image)

            # Update the Frame associated with the given window_id to display the new image
            frame = self.floating_frames.get(window_id)
            if frame:
                # Remove all previous widgets in the frame (if any)
                for widget in frame.winfo_children():
                    widget.destroy()

                # Create a new Label widget to display the new grayscale image
                label = tk.Label(frame, image=img_tk, bg="black")
                label.image = img_tk  # Keep a reference to the image to prevent it from being garbage collected
                label.pack(expand=True, fill=tk.BOTH)
            else:
                print(f"Frame not found for window_id: {window_id}")

        except Exception as e:
            print(f"Error in get_proto_percentage: {e}")

        finally:
            # Hide the loading indicator once processing is complete
            self.hide_loading()



    def show_original_image(self, window_id):
        """Displays the original image stored in floating_images."""
        try:
            # Retrieve the original image stored in floating_images
            img_tk = self.floating_images.get(window_id)

            if img_tk is not None:
                # Update the Frame associated with the given window_id
                frame = self.floating_frames.get(window_id)
                if frame:
                    # Remove all previous widgets in the frame
                    for widget in frame.winfo_children():
                        widget.destroy()

                    # Create a Label widget to display the original image
                    label = tk.Label(frame, image=img_tk, bg="white")
                    label.image = img_tk  # Keep a reference to the image to prevent garbage collection
                    label.pack(expand=True, fill=tk.BOTH)

                    # Check if there is a proto_options window for this window_id
                    if hasattr(self, "proto_options") and window_id in self.proto_options:
                        try:
                            # If the proto_options window exists, destroy it
                            if self.proto_options[window_id].winfo_exists():
                                self.proto_options[window_id].destroy()

                            # Remove the reference to the proto_options window
                            del self.proto_options[window_id]
                        except Exception as e:
                            print(f"Error trying to destroy the proto_options window: {e}")

                    # Set the image to be the original (reset flags)
                    self.ORIGINAL_IMG[window_id] = False
                    if self.COLOR_SPACE:
                        self.MEMBERDEGREE[window_id] = True

                else:
                    print(f"Frame not found for window_id: {window_id}")
            else:
                print(f"Original image not found for window_id: {window_id}")

        except Exception as e:
            print(f"Error displaying the original image: {e}")



    






def start_up():
    root = tk.Tk()
    app = PyFCSApp(root)
    root.mainloop()

if __name__ == '__main__':
    start_up()

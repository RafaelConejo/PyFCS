import tkinter as tk
from tkinter import ttk
from skimage import color
import math, colorsys, numpy as np
from sklearn.cluster import DBSCAN

### my libraries ###
from PyFCS.interface.modules import UtilsTools  

class ImageManager:
    """Gestor de funciones relacionadas con imágenes y colores (independiente de la GUI principal)."""

    def __init__(self, root=None, custom_warning=None, center_popup=None):
        """
        root: referencia a la ventana principal (opcional)
        custom_warning: callback para mostrar advertencias personalizadas
        center_popup: callback para centrar popups
        """
        self.root = root
        self.custom_warning = custom_warning
        self.center_popup = center_popup

    # ------------------------------------------------------------------
    # Utilidades simples
    # ------------------------------------------------------------------

    def addColor_to_image(self, window, colors, update_ui_callback):
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
        # ttk.Label(form_frame, text="Color Name:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        # ttk.Entry(form_frame, textvariable=color_name_var, width=30).grid(row=0, column=1, padx=5, pady=5)

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
                # if not color_name:
                #     raise ValueError("The color name cannot be empty.")
                if not (0 <= l_value <= 100):
                    raise ValueError("L value must be between 0 and 100.")
                if not (-128 <= a_value <= 127):
                    raise ValueError("A value must be between -128 and 127.")
                if not (-128 <= b_value <= 127):
                    raise ValueError("B value must be between -128 and 127.")
                # if color_name in colors:
                #     raise ValueError(f"The color name '{color_name}' already exists.")

                # Store the result
                result["color_name"] = color_name
                result["lab"] = {"L": l_value, "A": a_value, "B": b_value}

                # Add the new color as a dict
                colors.append({
                    "lab": (l_value, a_value, b_value),
                    "rgb": UtilsTools.lab_to_rgb((l_value, a_value, b_value)),  # asumiendo que tienes esta función
                    "source_image": "added_manually"
                })

                if update_ui_callback:
                    update_ui_callback()  # Actualiza la interfaz si es necesario

                popup.destroy()

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
    


    def get_proto_percentage(self, prototypes, image, fuzzy_color_space, selected_option, progress_callback=None):
        """Generates a grayscale image without using a matplotlib figure."""
        # Convert the image to a NumPy array
        img_np = np.array(image)

        # Check if the image has an alpha channel (RGBA)
        if img_np.shape[-1] == 4:  # If it has 4 channels (RGBA)
            img_np = img_np[..., :3]  # Remove the alpha channel and keep only RGB

        # Normalize the image values to the range [0, 1]
        img_np = img_np / 255.0

        # Convert the image from RGB to LAB color space
        lab_image = color.rgb2lab(img_np)

        # Retrieve the selected prototype
        selected_prototype = prototypes[selected_option]
        print(f"Selected Prototype: {selected_prototype.label}")

        # Create an empty grayscale image (same dimensions as the input image)
        grayscale_image = np.zeros((lab_image.shape[0], lab_image.shape[1]), dtype=np.uint8)
        
        # Dictionary to store computed membership values for each lab_color
        membership_cache = {}

        # Vectorize: Flatten the lab_image for processing
        lab_image_flat = lab_image.reshape(-1, 3)

        # Precompute membership for all unique colors
        unique_lab_colors = np.unique(lab_image_flat, axis=0)

        # Calculate membership for all unique lab colors
        for index, lab_color in enumerate(unique_lab_colors):
            lab_color_tuple = tuple(lab_color)
            if lab_color_tuple not in membership_cache:
                membership_degree = fuzzy_color_space.calculate_membership_for_prototype(lab_color, selected_option)
                membership_cache[lab_color_tuple] = membership_degree

            if progress_callback:
                progress_callback(index + 1, len(unique_lab_colors))

        # Map the computed membership values to the flattened image
        flattened_memberships = np.array([membership_cache[tuple(color)] for color in lab_image_flat])

        # Reshape back to the original image dimensions and scale to grayscale
        grayscale_image = (flattened_memberships * 255).reshape(lab_image.shape[0], lab_image.shape[1]).astype(np.uint8)

        # Return the generated grayscale image as a NumPy array
        return grayscale_image
        
      


    def get_fuzzy_color_space(self, image, threshold=0.5, min_samples=160):
        """
        Detects the main colors in an image using DBSCAN clustering and triggers a callback with the detected colors.

        Args:
            image: PIL Image object to process.
            threshold: Float, controls the DBSCAN epsilon (closeness of clusters).
            min_samples: Int, minimum number of points to form a cluster.
            display_callback: Callable, function to execute with the detected colors.
        """
        # Convert image to numpy array
        img_np = np.array(image)

        # Handle alpha channel if present
        if img_np.shape[-1] == 4:  # If it has 4 channels (RGBA)
            img_np = img_np[..., :3]  # Remove the alpha channel and keep only RGB

        # Normalize pixel values
        img_np = img_np / 255.0
        lab_img = color.rgb2lab(img_np)

        # Flatten the image into a list of pixels
        pixels = lab_img.reshape((-1, 3))

        # Apply DBSCAN clustering
        eps = 1.5 - threshold
        dbscan = DBSCAN(eps=eps, min_samples=min_samples)
        labels = dbscan.fit_predict(pixels)

        # Extract representative colors
        unique_labels = set(labels)
        colors = []
        for label in unique_labels:
            if label == -1:  # Ignore noise
                continue
            group = pixels[labels == label]
            # Calculate the mean color of the group in LAB
            mean_color_lab = group.mean(axis=0)

            # Convert mean LAB to RGB
            mean_color_rgb = color.lab2rgb([[mean_color_lab]])  # lab2rgb expects a 2D array
            mean_color_rgb = (mean_color_rgb[0, 0] * 255).astype(int)  # Scale to [0, 255]

            colors.append({"rgb": tuple(mean_color_rgb), "lab": tuple(mean_color_lab)})

        # Trigger the callback with the detected colors
        return colors



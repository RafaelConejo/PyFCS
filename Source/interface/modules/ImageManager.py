import tkinter as tk
from tkinter import ttk
from skimage import color
import matplotlib.pyplot as plt
import math, colorsys, numpy as np
from sklearn.cluster import DBSCAN

### my libraries ###
from Source.interface.modules import UtilsTools  


"""
Module summary
--------------
This module encapsulates image- and color-related utilities that are independent from the main GUI.

It provides:
    - A Tkinter popup workflow to manually add a color by entering LAB values or selecting a color
    from an HSV color wheel (with live LAB updates).
    - Generation of a grayscale membership map for a selected prototype by computing fuzzy membership
    values in LAB space (with caching + optional progress reporting).
    - Automatic main-color detection in an image using DBSCAN clustering in LAB space, returning
    representative colors in both LAB and RGB.
"""
class ImageManager:
    def __init__(self, root=None, custom_warning=None, center_popup=None):
        """
        Args:
            root: Optional reference to the main application window.
            custom_warning: Optional callback to display custom warning dialogs/messages.
            center_popup: Optional callback to center popup windows on screen.
        """
        self.root = root
        self.custom_warning = custom_warning
        self.center_popup = center_popup

    # ------------------------------------------------------------------
    # Simple utilities
    # ------------------------------------------------------------------

    def addColor_to_image(self, window, colors, update_ui_callback):
        """
        Opens a popup window to add a new color.

        The user can:
          - Enter LAB values manually, or
          - Pick a color from a color wheel (HSV), which is converted to LAB and written into the fields.

        On confirmation:
          - Validates LAB ranges
          - Appends a new entry to the provided `colors` list containing:
              * "lab": (L, A, B)
              * "rgb": converted RGB tuple (via UtilsTools.lab_to_rgb)
              * "source_image": "added_manually"
          - Calls `update_ui_callback()` if provided
          - Returns (color_name, lab_dict) where:
              * color_name: string (may be empty if name field is not used)
              * lab_dict: {"L": ..., "A": ..., "B": ...}

        If the popup is closed without confirmation, returns (None, None).
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

        # Container to store the result
        result = {"color_name": None, "lab": None}

        # Title and instructions
        ttk.Label(popup, text="Add New Color", font=("Helvetica", 14, "bold")).pack(pady=10)
        ttk.Label(popup, text="Enter the LAB values and the color name:").pack(pady=5)

        # Form frame for input fields
        form_frame = ttk.Frame(popup)
        form_frame.pack(padx=20, pady=10)

        # Color name field (currently unused / commented out)
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
            Validate the user's input and append the new color to the `colors` list.

            - Reads LAB values from the entry fields
            - Validates allowed ranges:
                * L in [0, 100]
                * A in [-128, 127]
                * B in [-128, 127]
            - Builds the result and appends the color
            - Calls the UI update callback if provided
            - Closes the popup

            If validation fails, a warning is displayed via `custom_warning`.
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

                # Store the result for returning to the caller
                result["color_name"] = color_name
                result["lab"] = {"L": l_value, "A": a_value, "B": b_value}

                # Append the new color entry to the provided list
                colors.append(
                    {
                        "lab": (l_value, a_value, b_value),
                        "rgb": UtilsTools.lab_to_rgb((l_value, a_value, b_value)),
                        "source_image": "added_manually",
                    }
                )

                # Refresh the UI if the caller provided a callback
                if update_ui_callback:
                    update_ui_callback()

                popup.destroy()

            except ValueError as e:
                self.custom_warning("Invalid Input", str(e))

        def browse_color():
            """
            Open a secondary popup with an HSV color wheel.

            - Clicking on the wheel selects an RGB color (hue-based, full saturation/value)
            - The selected RGB is converted to LAB and written into the L/A/B entry fields
            - A preview panel shows the selected color
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
                """Convert HSV to RGB in the [0, 255] integer range."""
                r, g, b = colorsys.hsv_to_rgb(h, s, v)
                return int(r * 255), int(g * 255), int(b * 255)

            def draw_color_wheel():
                """Draw the HSV color wheel by plotting pixels/lines across the circular region."""
                for y in range(canvas_size):
                    for x in range(canvas_size):
                        dx, dy = x - center, y - center
                        dist = math.sqrt(dx**2 + dy**2)
                        if dist <= radius:
                            angle = math.atan2(dy, dx)
                            hue = (angle / (2 * math.pi)) % 1
                            r, g, b = hsv_to_rgb(hue, 1, 1)
                            color_code = f"#{r:02x}{g:02x}{b:02x}"
                            canvas.create_line(x, y, x + 1, y, fill=color_code)

            def on_click(event):
                """
                Handle click on the wheel:
                  - Read the hue at the click position
                  - Convert HSV -> RGB -> LAB
                  - Update the preview + L/A/B fields
                """
                x, y = event.x, event.y
                dx, dy = x - center, y - center
                dist = math.sqrt(dx**2 + dy**2)

                if dist <= radius:
                    angle = math.atan2(dy, dx)
                    hue = (angle / (2 * math.pi)) % 1
                    r, g, b = hsv_to_rgb(hue, 1, 1)
                    color_hex = f"#{r:02x}{g:02x}{b:02x}"

                    # Update preview
                    preview_canvas.config(bg=color_hex)

                    # Convert RGB -> LAB (skimage expects float RGB in [0, 1])
                    rgb = np.array([[r, g, b]]) / 255
                    lab = color.rgb2lab(rgb.reshape((1, 1, 3)))[0][0]

                    # Update LAB fields in the main popup
                    l_value_var.set(f"{lab[0]:.2f}")
                    a_value_var.set(f"{lab[1]:.2f}")
                    b_value_var.set(f"{lab[2]:.2f}")

            def confirm_selection():
                """Close the color picker window."""
                color_picker.destroy()

            # Build and draw the color wheel
            canvas = tk.Canvas(color_picker, width=canvas_size, height=canvas_size)
            canvas.pack()
            draw_color_wheel()
            canvas.bind("<Button-1>", on_click)

            # Preview area for the chosen color
            preview_canvas = tk.Canvas(color_picker, width=100, height=50, bg="white")
            preview_canvas.pack(pady=10)

            # Confirm button (closes the picker)
            ttk.Button(color_picker, text="Confirm", command=confirm_selection).pack(pady=10)

        # Button frame for "Browse Color" and "Add Color"
        button_frame = ttk.Frame(popup)
        button_frame.pack(pady=20)

        ttk.Button(
            button_frame,
            text="Browse Color",
            command=browse_color,
            style="Accent.TButton",
        ).pack(side="left", padx=10)

        ttk.Button(
            button_frame,
            text="Add Color",
            command=confirm_color,
            style="Accent.TButton",
        ).pack(side="left", padx=10)

        # Block until the popup is closed
        popup.wait_window()

        # If the user never confirmed, return Nones
        if result["color_name"] is None or result["lab"] is None:
            return None, None

        return result["color_name"], result["lab"]



    @staticmethod
    def _pil_to_rgb_uint8(image):
        """Return a uint8 RGB NumPy array from a PIL image, safely handling grayscale/RGBA images."""
        img_np = np.asarray(image)

        if img_np.ndim == 2:
            img_np = np.stack([img_np, img_np, img_np], axis=-1)
        elif img_np.shape[-1] == 4:
            img_np = img_np[..., :3]
        elif img_np.shape[-1] > 3:
            img_np = img_np[..., :3]

        return img_np.astype(np.uint8, copy=False)

    def _pil_to_lab_image(self, image):
        """Convert a PIL image to LAB using skimage, returning an H x W x 3 float array."""
        img_rgb = self._pil_to_rgb_uint8(image)
        img01 = img_rgb.astype(np.float32) / 255.0
        return color.rgb2lab(img01)

    def get_proto_percentage(
        self,
        prototypes,
        image,
        fuzzy_color_space,
        selected_option,
        progress_callback=None,
        cancel_callback=None,
    ):
        """
        Generate a grayscale membership map for one selected prototype.

        Optimized version:
        - Converts RGB -> LAB once.
        - Quantizes LAB to 0.01.
        - Computes membership only for unique LAB values.
        - Reconstructs the full image using the inverse map.
        """
        if selected_option < 0 or selected_option >= len(prototypes):
            raise ValueError("Selected prototype index is out of range.")

        if cancel_callback and cancel_callback():
            return None

        lab_image = self._pil_to_lab_image(image)
        height, width = lab_image.shape[:2]

        lab_int = np.round(lab_image.reshape(-1, 3) * 100.0).astype(np.int32)
        uniq, inv = np.unique(lab_int, axis=0, return_inverse=True)

        values_for_uniq = np.empty((uniq.shape[0],), dtype=np.float32)
        total_uniqs = int(uniq.shape[0])

        for i in range(total_uniqs):
            if cancel_callback and cancel_callback():
                return None

            lab_tuple = tuple((uniq[i].astype(np.float32) / 100.0).tolist())
            value = fuzzy_color_space.calculate_membership_for_prototype(
                lab_tuple,
                selected_option
            )
            values_for_uniq[i] = np.clip(float(value), 0.0, 1.0)

            if progress_callback and (i % 500 == 0 or i == total_uniqs - 1):
                if cancel_callback and cancel_callback():
                    return None
                progress_callback(i + 1, total_uniqs)

        grayscale_image = (
            values_for_uniq[inv]
            .reshape(height, width)
            * 255.0
        ).astype(np.uint8)

        return grayscale_image

    @staticmethod
    def estimate_proto_coverage(grayscale_image_array, valid_mask):
        """
        Estimate the percentage of valid pixels covered by a prototype membership map.

        Keeps your previous threshold behavior:
        - binary-like maps with 255 use threshold 255
        - continuous maps use threshold 128
        """
        if grayscale_image_array is None:
            return 0.0, 128

        valid_total = int(np.count_nonzero(valid_mask))
        if valid_total == 0:
            return 0.0, 128

        if grayscale_image_array.ndim == 2:
            unique_vals = np.unique(grayscale_image_array)
            if unique_vals.size <= 3 and 255 in unique_vals:
                threshold = 255
            else:
                threshold = 128

            colored = int(np.count_nonzero((grayscale_image_array >= threshold) & valid_mask))
        else:
            threshold = 128
            colored = int(np.count_nonzero(np.any(grayscale_image_array != 0, axis=-1) & valid_mask))

        pct = 100.0 * (colored / valid_total)
        return pct, threshold

    def get_best_prototype_label_map(
        self,
        image,
        fuzzy_color_space,
        valid_mask=None,
        progress_callback=None,
        cancel_callback=None,
    ):
        """
        Compute the best-prototype label map for the full image.

        Returns:
            np.ndarray of shape (H, W), dtype int32.
            Pixels without assignment/background are -1 when valid_mask is supplied.
        """
        if cancel_callback and cancel_callback():
            return None

        fuzzy_color_space.precompute_pack()

        lab_image = self._pil_to_lab_image(image)
        height, width = lab_image.shape[:2]

        lab_int = np.round(lab_image.reshape(-1, 3) * 100.0).astype(np.int32)
        uniq, inv = np.unique(lab_int, axis=0, return_inverse=True)

        best_for_uniq = np.empty((uniq.shape[0],), dtype=np.int32)
        total_uniqs = int(uniq.shape[0])

        for i in range(total_uniqs):
            if cancel_callback and cancel_callback():
                return None

            lab_tuple = tuple((uniq[i].astype(np.float32) / 100.0).tolist())
            best_idx = fuzzy_color_space.best_prototype_index_from_lab(lab_tuple)
            best_for_uniq[i] = int(best_idx) if best_idx is not None else -1

            if progress_callback and (i % 500 == 0 or i == total_uniqs - 1):
                if cancel_callback and cancel_callback():
                    return None
                progress_callback(i + 1, total_uniqs)

        label_map = best_for_uniq[inv].reshape(height, width).astype(np.int32)

        if valid_mask is not None:
            if valid_mask.shape != label_map.shape:
                raise ValueError("valid_mask shape does not match the generated label map.")
            label_map[~valid_mask] = -1

        return label_map

    @staticmethod
    def build_original_palette_uint8(prototypes):
        """
        Build a dynamic high-contrast visualization palette in prototype order.
        Requires: import matplotlib.pyplot as plt
        """
        n = len(prototypes)
        if n == 0:
            return np.zeros((0, 3), dtype=np.uint8)

        qualitative_cmaps = ["tab20", "tab20b", "tab20c", "Set3", "Dark2", "Accent"]
        colors = []

        for cmap_name in qualitative_cmaps:
            cmap = plt.get_cmap(cmap_name)
            for i in range(cmap.N):
                rgb01 = np.array(cmap(i)[:3], dtype=float)
                colors.append((np.clip(rgb01, 0, 1) * 255).astype(np.uint8))
                if len(colors) >= n:
                    break
            if len(colors) >= n:
                break

        if len(colors) < n:
            remaining = n - len(colors)
            hsv = plt.get_cmap("hsv", remaining)
            for i in range(remaining):
                rgb01 = np.array(hsv(i)[:3], dtype=float)
                colors.append((np.clip(rgb01, 0, 1) * 255).astype(np.uint8))

        palette = []
        for i, prototype in enumerate(prototypes):
            rgb255 = colors[i].copy()
            if getattr(prototype, "label", "").lower() == "black":
                rgb255 = np.array([0, 0, 0], dtype=np.uint8)
            palette.append(rgb255)

        return np.stack(palette, axis=0).astype(np.uint8)

    @staticmethod
    def build_alt_palette_uint8(prototypes, hex_color):
        """Build the representative-color palette using the colors stored in hex_color."""
        if isinstance(hex_color, dict):
            hex_colors = list(hex_color.keys())
        else:
            hex_colors = list(hex_color or [])

        alt = []
        for i, _prototype in enumerate(prototypes):
            rgb = np.array([0, 0, 0], dtype=np.uint8)

            if i < len(hex_colors):
                hx = str(hex_colors[i]).strip()
                if hx.startswith("#") and len(hx) == 7:
                    try:
                        rgb = np.array(
                            [int(hx[j:j + 2], 16) for j in (1, 3, 5)],
                            dtype=np.uint8
                        )
                    except ValueError:
                        rgb = np.array([0, 0, 0], dtype=np.uint8)

            alt.append(rgb)

        if not alt:
            return np.zeros((0, 3), dtype=np.uint8)

        return np.stack(alt, axis=0).astype(np.uint8)

    @staticmethod
    def recolor_label_map(label_map, palette_uint8):
        """
        Convert a label map to an RGBA image using a palette.
        label_map == -1 remains transparent/background.
        """
        h, w = label_map.shape[:2]
        recolored_rgb = np.zeros((h, w, 3), dtype=np.uint8)

        valid_label_mask = (label_map >= 0) & (label_map < len(palette_uint8))
        if np.any(valid_label_mask):
            idx = label_map[valid_label_mask].astype(np.int32)
            recolored_rgb[valid_label_mask] = palette_uint8[idx]

        return UtilsTools._apply_alpha_to_rgb_array(recolored_rgb, valid_label_mask)





    def get_fcs_image(self, image, threshold=0.5, min_samples=160):
        """
        Detect the main colors in an image using DBSCAN clustering in LAB space.

        Steps:
          - Convert input PIL image to NumPy RGB array (discard alpha channel if present)
          - Normalize RGB to [0, 1] and convert to LAB
          - Flatten pixels into (N, 3) LAB samples
          - Run DBSCAN with:
              * eps = 1.5 - threshold
              * min_samples = min_samples
          - For each cluster (excluding noise label -1):
              * Compute the mean LAB color
              * Convert mean LAB back to RGB (0..255 integer)
              * Append {"rgb": (R,G,B), "lab": (L,A,B)} to results

        Args:
            image: PIL Image object to process.
            threshold: Float controlling DBSCAN epsilon (higher threshold => smaller eps).
            min_samples: Minimum samples required to form a cluster.

        Returns:
            List[dict]: [{"rgb": (R,G,B), "lab": (L,A,B)}, ...]
        """
        # Convert image to numpy array
        img_np = np.array(image)

        # Handle alpha channel if present (RGBA -> RGB)
        if img_np.shape[-1] == 4:
            img_np = img_np[..., :3]

        # Normalize pixel values to [0, 1]
        img_np = img_np / 255.0
        lab_img = color.rgb2lab(img_np)

        # Flatten the image into a list of pixels
        pixels = lab_img.reshape((-1, 3))

        # Apply DBSCAN clustering
        eps = 1.5 - threshold
        dbscan = DBSCAN(eps=eps, min_samples=min_samples)
        labels = dbscan.fit_predict(pixels)

        # Extract representative colors (cluster centroids in LAB)
        unique_labels = set(labels)
        colors = []
        for label in unique_labels:
            if label == -1:  # Ignore noise
                continue

            group = pixels[labels == label]

            # Compute the mean LAB of the cluster
            mean_color_lab = group.mean(axis=0)

            # Convert mean LAB to RGB (skimage expects a 2D array)
            mean_color_rgb = color.lab2rgb([[mean_color_lab]])
            mean_color_rgb = (mean_color_rgb[0, 0] * 255).astype(int)

            colors.append({"rgb": tuple(mean_color_rgb), "lab": tuple(mean_color_lab)})

        return colors



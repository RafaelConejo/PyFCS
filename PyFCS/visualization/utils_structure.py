import tkinter as tk
import os
from tkinter import ttk, filedialog
import numpy as np
from skimage import color
from sklearn.cluster import DBSCAN
from scipy.spatial import distance

### my libraries ###
from PyFCS import Input, Visual_tools, ReferenceDomain, Prototype, FuzzyColorSpace

def prompt_file_selection(initial_subdir):
    """
    Prompts the user to select a file and returns the selected filename.
    """
    initial_directory = os.path.join(os.getcwd(), initial_subdir)
    filetypes = [("All Files", "*.*")]
    return filedialog.askopenfilename(
        title="Select Fuzzy Color Space File",
        initialdir=initial_directory,
        filetypes=filetypes
    )



def process_prototypes(color_data):
    """
    Creates prototypes from color data.
    """
    prototypes = []
    for color_name, color_value in color_data.items():
        positive_prototype = color_value['positive_prototype']
        negative_prototypes = color_value['negative_prototypes']
        prototype = Prototype(label=color_name, positive=positive_prototype, negatives=negative_prototypes, add_false=True)
        prototypes.append(prototype)
    return prototypes



@staticmethod
def rgb_to_hex(rgb):
    return "#%02x%02x%02x" % rgb

def lab_to_rgb(lab):
    if isinstance(lab, dict):
        lab = np.array([[lab['L'], lab['A'], lab['B']]])
    else:
        lab = np.array([lab])  

    rgb = color.lab2rgb(lab)  

    # RGB to [0, 255]
    rgb_scaled = (rgb[0] * 255).astype(int)

    return tuple(np.clip(rgb_scaled, 0, 255))



def load_color_data(file_path):
    """
    Reads color data from a file and converts LAB values to RGB.
    Returns a dictionary of colors with their LAB and RGB values.
    """
    input_class = Input.instance('.cns')
    color_data = input_class.read_file(file_path)

    colors = {}
    for color_name, color_value in color_data.items():
        lab = np.array(color_value['positive_prototype'])
        rgb = tuple(map(lambda x: int(x * 255), color.lab2rgb([lab])[0]))
        colors[color_name] = {"rgb": rgb, "lab": lab}
    return colors



def create_popup_window(parent, title, width, height, header_text):
    """
    Creates a popup window with a header and a scrollable frame.
    Returns the popup window and the scrollable frame.
    """
    popup = tk.Toplevel(parent)
    popup.title(title)
    popup.geometry(f"{width}x{height}")
    popup.configure(bg="#f5f5f5")

    tk.Label(
        popup,
        text=header_text,
        font=("Helvetica", 14, "bold"),
        bg="#f5f5f5"
    ).pack(pady=15)

    # Create a scrollable frame
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

    return popup, scrollable_frame



def create_color_display_frame(parent, color_name, rgb, lab, color_checks):
    """
    Creates a frame for displaying color information, including a color box, labels, and a Checkbutton.
    """
    frame = ttk.Frame(parent)
    frame.pack(fill="x", pady=8, padx=10)

    # Color box
    color_box = tk.Label(frame, bg=rgb_to_hex(rgb), width=4, height=2, relief="solid", bd=1)
    color_box.pack(side="left", padx=10)

    # Color name
    tk.Label(
        frame,
        text=color_name,
        font=("Helvetica", 12),
        bg="#f5f5f5"
    ).pack(side="left", padx=10)

    # LAB values
    lab_values = f"L: {lab[0]:.1f}, A: {lab[1]:.1f}, B: {lab[2]:.1f}"
    tk.Label(
        frame,
        text=lab_values,
        font=("Helvetica", 10, "italic"),
        bg="#f5f5f5"
    ).pack(side="left", padx=10)

    # Checkbutton for selection
    var = tk.BooleanVar()
    color_checks[color_name] = {"var": var, "lab": lab}
    ttk.Checkbutton(frame, variable=var).pack(side="right", padx=10)


def create_color_display_frame_add(parent, color_name, lab, color_checks):
    """
    Creates a frame for displaying color information, including labels for the color name, LAB values, and a Checkbutton.
    """
    frame = ttk.Frame(parent)
    frame.pack(fill="x", pady=8, padx=10)

    rgb = lab_to_rgb(lab)

    # Color box
    color_box = tk.Label(frame, bg=rgb_to_hex(rgb), width=4, height=2, relief="solid", bd=1)
    color_box.pack(side="left", padx=10)

    # Color name
    tk.Label(
        frame,
        text=color_name,
        font=("Helvetica", 12),
        bg="#f5f5f5"
    ).pack(side="left", padx=10)

    # LAB values
    lab_values = f"L: {lab['L']:.1f}, A: {lab['A']:.1f}, B: {lab['B']:.1f}"
    tk.Label(
        frame,
        text=lab_values,
        font=("Helvetica", 10, "italic"),
        bg="#f5f5f5"
    ).pack(side="left", padx=10)

    # Checkbutton for selection
    var = tk.BooleanVar()
    color_checks[color_name] = {"var": var, "lab": lab}
    ttk.Checkbutton(frame, variable=var).pack(side="right", padx=10)



def create_selection_popup(parent, title, width, height, items):
    """
    Creates a popup window with a listbox to select an item.
    Returns the popup window and the listbox widget.
    """
    popup = tk.Toplevel(parent)
    popup.title(title)
    popup.geometry(f"{width}x{height}")
    popup.resizable(False, False)

    # Add a listbox to display the items
    listbox = tk.Listbox(popup, width=40, height=10)
    for item in items:
        listbox.insert(tk.END, item)
    listbox.pack(pady=10)

    # Center the popup relative to the parent window
    popup.transient(parent)
    popup.grab_set()

    return popup, listbox



def handle_image_selection(event, listbox, popup, images_names, callback):
    """
    Handles the selection of an image from the listbox.
    Closes the popup and triggers a callback with the selected image ID.
    """
    selected_index = listbox.curselection()
    if not selected_index:
        return  # Do nothing if no selection is made

    selected_filename = listbox.get(selected_index)

    # Find the image ID associated with the selected filename
    selected_img_id = next(
        img_id for img_id, fname in images_names.items() if os.path.basename(fname) == selected_filename
    )

    # Close the popup
    popup.destroy()

    # Call the provided callback with the selected image ID
    callback(selected_img_id)



def get_proto_percentage(prototypes, image, fuzzy_color_space, selected_option, progress_callback=None):
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



def get_fuzzy_color_space(image, threshold=0.5, min_samples=160):
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





import numpy as np
import heapq
from scipy.spatial import distance

def filter_points_with_threshold(selected_volume, threshold, step):
    """
    Filtra los puntos dentro de un volumen de Voronoi priorizando los más cercanos al prototipo positivo.
    Se detiene temprano en direcciones con muchos puntos fuera del umbral.
    """
    filtered_points = {}

    for idx, prototype in enumerate(selected_volume):
        positive = np.array(prototype.positive)

        # Obtener los límites del volumen
        limits = get_volume_limits(prototype.voronoi_volume)

        # Inicializar lista de puntos dentro del umbral
        points_within_threshold = []

        # Usar un heap (cola de prioridad) para evaluar primero los puntos más cercanos
        heap = [(0, tuple(positive))]  # (distancia, punto)
        visited = set()
        consecutive_failures = 0
        max_failures = 10  # Número máximo de fallos antes de detener una dirección

        while heap:
            _, point = heapq.heappop(heap)  # Extraer el punto más cercano
            if point in visited:
                continue
            visited.add(point)

            # Calcular deltaE
            delta_e = delta_e_ciede2000(positive, point)
            if delta_e < threshold:
                points_within_threshold.append(point)
                consecutive_failures = 0
            else:
                consecutive_failures += 1

            if consecutive_failures > max_failures:
                break  # Detener búsqueda en esta dirección

            # Expandir en 6 direcciones (vecinos ortogonales)
            neighbors = [
                (point[0] + step, point[1], point[2]),
                (point[0] - step, point[1], point[2]),
                (point[0], point[1] + step, point[2]),
                (point[0], point[1] - step, point[2]),
                (point[0], point[1], point[2] + step),
                (point[0], point[1], point[2] - step),
            ]

            for neighbor in neighbors:
                if is_within_limits(neighbor, limits) and is_point_inside_volume(neighbor, prototype.voronoi_volume):
                    heapq.heappush(heap, (distance.euclidean(neighbor, positive), neighbor))

        filtered_points[f'Volume_{idx}'] = points_within_threshold

    return filtered_points

def get_volume_limits(volume):
    """
    Obtiene los límites de un volumen de Voronoi a partir de sus caras.
    """
    all_vertices = np.array([
        [vertex.x, vertex.y, vertex.z] if hasattr(vertex, "x") else vertex
        for face in volume.faces if not face.infinity
        for vertex in face.vertex
    ])

    return {
        "L": (np.min(all_vertices[:, 0]), np.max(all_vertices[:, 0])),
        "a": (np.min(all_vertices[:, 1]), np.max(all_vertices[:, 1])),
        "b": (np.min(all_vertices[:, 2]), np.max(all_vertices[:, 2])),
    }

def is_within_limits(point, limits):
    """
    Verifica si un punto está dentro de los límites del volumen.
    """
    L, a, b = point
    return limits["L"][0] <= L <= limits["L"][1] and limits["a"][0] <= a <= limits["a"][1] and limits["b"][0] <= b <= limits["b"][1]



def is_point_inside_volume(point, volume):
    """
    Verifica si un punto está dentro de un volumen de Voronoi, evaluando su relación con los planos de las caras.
    """
    for face in volume.faces:
        if face.infinity:
            continue  # Ignorar caras infinitas
        
        plane = face.p
        if plane:
            # Evaluar la ecuación del plano: Ax + By + Cz + D
            A, B, C, D = plane.A, plane.B, plane.C, plane.D
            if (A * point[0] + B * point[1] + C * point[2] + D) > 0:
                return False  # Está fuera si no cumple la desigualdad
    return True  # Si cumple todas, está dentro



def delta_e_ciede2000(lab1, lab2):
    """
    Implementación de la fórmula CIEDE2000 para calcular la diferencia de color entre dos colores en el espacio Lab.

    Parámetros:
    - lab1: Tuple o lista con valores (L, a, b) del primer color.
    - lab2: Tuple o lista con valores (L, a, b) del segundo color.

    Retorna:
    - delta_E: Diferencia de color según CIEDE2000.
    """
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2

    # Paso 1: Calcular C*
    C1 = np.sqrt(a1**2 + b1**2)
    C2 = np.sqrt(a2**2 + b2**2)
    
    # Promedio de Chroma
    C_avg = (C1 + C2) / 2
    
    # Factor G
    G = 0.5 * (1 - np.sqrt((C_avg**7) / (C_avg**7 + 25**7)))
    
    # Ajuste de a'
    a1_prime = (1 + G) * a1
    a2_prime = (1 + G) * a2

    # Nuevo C'
    C1_prime = np.sqrt(a1_prime**2 + b1**2)
    C2_prime = np.sqrt(a2_prime**2 + b2**2)

    # Paso 2: Calcular h'
    h1_prime = np.degrees(np.arctan2(b1, a1_prime)) % 360
    h2_prime = np.degrees(np.arctan2(b2, a2_prime)) % 360

    # Paso 3: Diferencias de color
    delta_L = L2 - L1
    delta_C = C2_prime - C1_prime

    # Cálculo de delta_h
    delta_h = h2_prime - h1_prime
    if abs(delta_h) > 180:
        delta_h -= 360 * np.sign(delta_h)
    delta_H = 2 * np.sqrt(C1_prime * C2_prime) * np.sin(np.radians(delta_h / 2))

    # Promedios para CIEDE2000
    L_avg = (L1 + L2) / 2
    C_avg_prime = (C1_prime + C2_prime) / 2

    # Cálculo de H_avg
    if C1_prime * C2_prime == 0:
        H_avg = h1_prime + h2_prime
    else:
        if abs(h1_prime - h2_prime) > 180:
            H_avg = (h1_prime + h2_prime + 360) / 2
        else:
            H_avg = (h1_prime + h2_prime) / 2

    # Pesos para ajustes
    T = (1 - 0.17 * np.cos(np.radians(H_avg - 30)) +
         0.24 * np.cos(np.radians(2 * H_avg)) +
         0.32 * np.cos(np.radians(3 * H_avg + 6)) -
         0.20 * np.cos(np.radians(4 * H_avg - 63)))

    # Factores de ajuste SL, SC, SH
    SL = 1 + ((0.015 * (L_avg - 50) ** 2) / np.sqrt(20 + (L_avg - 50) ** 2))
    SC = 1 + 0.045 * C_avg_prime
    SH = 1 + 0.015 * C_avg_prime * T

    # Factor de rotación
    delta_theta = 30 * np.exp(-((H_avg - 275) / 25) ** 2)
    RC = 2 * np.sqrt((C_avg_prime ** 7) / (C_avg_prime ** 7 + 25 ** 7))
    RT = -RC * np.sin(np.radians(2 * delta_theta))

    # Cálculo final de Delta E 2000
    delta_E = np.sqrt(
        (delta_L / SL) ** 2 +
        (delta_C / SC) ** 2 +
        (delta_H / SH) ** 2 +
        RT * (delta_C / SC) * (delta_H / SH)
    )

    return delta_E

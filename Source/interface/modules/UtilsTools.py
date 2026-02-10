import os
import sys
import numpy as np
from skimage import color
import tkinter as tk
from tkinter import ttk, filedialog
import colorsys

### my libraries ###
from Source.input_output.Input import Input
from Source.geometry.Prototype import Prototype

"""
Utility functions for PyFCS

This module provides a collection of helper functions used across the PyFCS
application. It includes:
- Path resolution that works both for .py execution and frozen .exe builds.
- Color space conversions (RGB, HSV, LAB, sRGB).
- File selection dialogs and popup window utilities for the GUI.
- Helper routines to process color prototypes and load color data from files.

Overall, this module acts as a shared toolbox for GUI handling, color conversion,
and data preparation.
"""


def get_base_path():
    """
    Return the base directory of the application.

    Behavior depends on how the application is executed:
    - When running as a .py file → returns the project root directory.
    - When running as a frozen .exe (e.g., via PyInstaller) → returns the
      directory containing the executable.
    """
    if getattr(sys, "frozen", False):
        # Running as a bundled executable
        return os.path.dirname(sys.executable)
    else:
        # UtilsTools.py is located in: PyFCS/interface/modules/
        # Move up three levels to reach the project root
        return os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )


@staticmethod
def rgb_to_hex(rgb):
    """
    Convert an RGB tuple (0–255) into a hexadecimal color string.

    Parameters
    ----------
    rgb : tuple
        (R, G, B) values in the range [0, 255].

    Returns
    -------
    str
        Hex color string in the form '#rrggbb'.
    """
    return "#%02x%02x%02x" % rgb


@staticmethod
def hsv_to_rgb(h, s, v):
    """
    Convert HSV values to RGB.

    Parameters
    ----------
    h, s, v : float
        Hue, saturation, and value components (expected in [0, 1]).

    Returns
    -------
    tuple
        (R, G, B) values scaled to the range [0, 255].
    """
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


@staticmethod
def lab_to_rgb(lab):
    """
    Convert LAB color values to RGB.

    Parameters
    ----------
    lab : dict or iterable
        Either a dictionary with keys {'L', 'A', 'B'} or an iterable (L, a, b).

    Returns
    -------
    tuple
        (R, G, B) values clipped to the range [0, 255].
    """
    if isinstance(lab, dict):
        lab = np.array([[lab['L'], lab['A'], lab['B']]])
    else:
        lab = np.array([lab])

    # Convert LAB to RGB in [0, 1]
    rgb = color.lab2rgb(lab)

    # Scale to [0, 255] and clip
    rgb_scaled = (rgb[0] * 255).astype(int)
    return tuple(np.clip(rgb_scaled, 0, 255))


@staticmethod
def srgb_to_lab(r, g, b):
    """
    Convert sRGB values to CIELAB using manual linearization and XYZ conversion.

    Parameters
    ----------
    r, g, b : int
        sRGB channel values in the range [0, 255].

    Returns
    -------
    tuple
        (L, a, b) values in CIELAB space.
    """

    def inv_gamma(u):
        # Inverse gamma correction for sRGB
        u = u / 255.0
        return u / 12.92 if u <= 0.04045 else ((u + 0.055) / 1.055) ** 2.4

    # Linearize sRGB channels
    R = inv_gamma(r)
    G = inv_gamma(g)
    B = inv_gamma(b)

    # Convert linear RGB to XYZ (D65)
    X = R * 0.4124564 + G * 0.3575761 + B * 0.1804375
    Y = R * 0.2126729 + G * 0.7151522 + B * 0.0721750
    Z = R * 0.0193339 + G * 0.1191920 + B * 0.9503041

    # Reference white (D65)
    Xn, Yn, Zn = 0.95047, 1.00000, 1.08883
    x = X / Xn
    y = Y / Yn
    z = Z / Zn

    def f(t):
        # Nonlinear LAB transfer function
        return t ** (1 / 3) if t > 0.008856 else (7.787 * t + 16 / 116)

    fx, fy, fz = f(x), f(y), f(z)

    # Compute LAB components
    L = 116 * fy - 16
    a = 500 * (fx - fy)
    bb = 200 * (fy - fz)

    return (L, a, bb)


def prompt_file_selection(initial_subdir):
    """
    Prompt the user to select a file using a file dialog.

    Parameters
    ----------
    initial_subdir : str
        Subdirectory (relative to the application base path) used as
        the initial directory in the dialog.

    Returns
    -------
    str
        Full path to the selected file, or an empty string if cancelled.
    """
    base_path = get_base_path()
    initial_directory = os.path.join(base_path, initial_subdir)

    filetypes = [("All Files", "*.*")]
    return filedialog.askopenfilename(
        title="Select Fuzzy Color Space File",
        initialdir=initial_directory,
        filetypes=filetypes
    )


def process_prototypes(color_data):
    """
    Create Prototype objects from parsed color data.

    Parameters
    ----------
    color_data : dict
        Dictionary mapping color names to their data, including
        'positive_prototype' and 'negative_prototypes'.

    Returns
    -------
    list
        List of Prototype instances.
    """
    prototypes = []

    for color_name, color_value in color_data.items():
        positive_prototype = color_value['positive_prototype']
        negative_prototypes = color_value['negative_prototypes']

        prototype = Prototype(
            label=color_name,
            positive=positive_prototype,
            negatives=negative_prototypes,
            add_false=True
        )
        prototypes.append(prototype)

    return prototypes


def load_color_data(file_path):
    """
    Load color data from a .cns file and convert LAB values to RGB.

    Parameters
    ----------
    file_path : str
        Path to the .cns file.

    Returns
    -------
    dict
        Dictionary mapping color names to:
        {
            "rgb": (R, G, B),
            "lab": LAB array
        }
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
    Create a popup window with a header and a scrollable content area.

    Parameters
    ----------
    parent : tk.Widget
        Parent window.
    title : str
        Title of the popup window.
    width : int
        Width of the popup window.
    height : int
        Height of the popup window.
    header_text : str
        Text displayed at the top of the popup.

    Returns
    -------
    (tk.Toplevel, ttk.Frame)
        The popup window and the scrollable frame where content can be added.
    """
    popup = tk.Toplevel(parent)
    popup.title(title)
    popup.geometry(f"{width}x{height}")
    popup.configure(bg="#f5f5f5")

    # Header label
    tk.Label(
        popup,
        text=header_text,
        font=("Helvetica", 14, "bold"),
        bg="#f5f5f5"
    ).pack(pady=15)

    # Container for scrollable content
    frame_container = ttk.Frame(popup)
    frame_container.pack(pady=10, fill="both", expand=True)

    canvas = tk.Canvas(frame_container, bg="#f5f5f5")
    scrollbar = ttk.Scrollbar(
        frame_container, orient="vertical", command=canvas.yview
    )
    scrollable_frame = ttk.Frame(canvas)

    # Update scroll region when content size changes
    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    return popup, scrollable_frame


@staticmethod
def create_selection_popup(parent, title, width, height, items):
    """
    Create a popup window containing a listbox for item selection.

    Parameters
    ----------
    parent : tk.Widget
        Parent window.
    title : str
        Title of the popup.
    width : int
        Width of the popup window.
    height : int
        Height of the popup window.
    items : list
        List of items to display in the listbox.

    Returns
    -------
    (tk.Toplevel, tk.Listbox)
        The popup window and the listbox widget.
    """
    popup = tk.Toplevel(parent)
    popup.title(title)
    popup.geometry(f"{width}x{height}")
    popup.resizable(False, False)

    listbox = tk.Listbox(popup, width=40, height=10)
    for item in items:
        listbox.insert(tk.END, item)
    listbox.pack(pady=10)

    # Make popup modal relative to parent
    popup.transient(parent)
    popup.grab_set()

    return popup, listbox


@staticmethod
def handle_image_selection(event, listbox, popup, images_names, callback):
    """
    Handle the selection of an image from a listbox.

    This function:
    - Retrieves the selected filename.
    - Resolves it to the corresponding image ID.
    - Closes the popup window.
    - Calls the provided callback with the selected image ID.

    Parameters
    ----------
    event : tk.Event
        The listbox selection event.
    listbox : tk.Listbox
        Listbox widget containing image filenames.
    popup : tk.Toplevel
        Popup window to be closed after selection.
    images_names : dict
        Dictionary mapping image IDs to file paths.
    callback : callable
        Function to be called with the selected image ID.
    """
    selected_index = listbox.curselection()
    if not selected_index:
        # No selection made
        return

    selected_filename = listbox.get(selected_index)

    # Find the image ID associated with the selected filename
    selected_img_id = next(
        img_id
        for img_id, fname in images_names.items()
        if os.path.basename(fname) == selected_filename
    )

    # Close the popup
    popup.destroy()

    # Trigger callback with the selected image ID
    callback(selected_img_id)

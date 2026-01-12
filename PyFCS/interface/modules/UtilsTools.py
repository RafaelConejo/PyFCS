import os
import numpy as np
from skimage import color
import tkinter as tk
from tkinter import ttk, filedialog
import colorsys

### my libraries ###
from PyFCS import Input, Prototype


@staticmethod
def rgb_to_hex(rgb):
    return "#%02x%02x%02x" % rgb


@staticmethod
def hsv_to_rgb(h, s, v):
    """Converts HSV to RGB in the range 0-255."""
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


@staticmethod
def lab_to_rgb(lab):
    if isinstance(lab, dict):
        lab = np.array([[lab['L'], lab['A'], lab['B']]])
    else:
        lab = np.array([lab])  
    rgb = color.lab2rgb(lab)  

    # RGB to [0, 255]
    rgb_scaled = (rgb[0] * 255).astype(int)
    return tuple(np.clip(rgb_scaled, 0, 255))


@staticmethod
def srgb_to_lab(r, g, b):
    def inv_gamma(u):
        u = u / 255.0
        return u / 12.92 if u <= 0.04045 else ((u + 0.055) / 1.055) ** 2.4

    R = inv_gamma(r)
    G = inv_gamma(g)
    B = inv_gamma(b)

    X = R * 0.4124564 + G * 0.3575761 + B * 0.1804375
    Y = R * 0.2126729 + G * 0.7151522 + B * 0.0721750
    Z = R * 0.0193339 + G * 0.1191920 + B * 0.9503041

    Xn, Yn, Zn = 0.95047, 1.00000, 1.08883
    x = X / Xn
    y = Y / Yn
    z = Z / Zn

    def f(t):
        return t ** (1/3) if t > 0.008856 else (7.787 * t + 16/116)

    fx, fy, fz = f(x), f(y), f(z)

    L = 116 * fy - 16
    a = 500 * (fx - fy)
    bb = 200 * (fy - fz)
    return (L, a, bb)



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



@staticmethod
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



@staticmethod
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



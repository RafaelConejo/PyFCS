import tkinter as tk
import os
from tkinter import ttk, Menu, filedialog, messagebox, Scrollbar
import numpy as np
from skimage import color
from PIL import Image, ImageTk
import matplotlib.pyplot as plt


def about_info(root):
    """Displays a popup window with 'About' information."""
    # Create a new top-level window (popup)
    about_window = tk.Toplevel(root)  
    about_window.title("About PyFCS")  # Set the title of the popup window
    
    # Disable resizing of the popup window
    about_window.resizable(False, False)

    # Create and add a label with the software information
    about_label = tk.Label(
        about_window, 
        text="PyFCS: Python Fuzzy Color Software\n"
              "A color modeling Python Software based on Fuzzy Color Spaces.\n"
              "Version 0.1\n\n"
              "Contact: rafaconejo@ugr.es", 
        padx=20, pady=20, font=("Arial", 12), justify="center"
    )
    about_label.pack()  # Add the label to the popup window

    # Create a 'Close' button to close the popup window
    close_button = tk.Button(about_window, text="Close", command=about_window.destroy)
    close_button.pack(pady=10)  # Add the button to the popup window




def get_proto_percentage(prototypes, image, fuzzy_color_space, selected_option):
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
    for lab_color in unique_lab_colors:
        lab_color_tuple = tuple(lab_color)
        if lab_color_tuple not in membership_cache:
            membership_degree = fuzzy_color_space.calculate_membership_for_prototype(lab_color, selected_option)
            membership_cache[lab_color_tuple] = membership_degree

    # Map the computed membership values to the flattened image
    flattened_memberships = np.array([membership_cache[tuple(color)] for color in lab_image_flat])

    # Reshape back to the original image dimensions and scale to grayscale
    grayscale_image = (flattened_memberships * 255).reshape(lab_image.shape[0], lab_image.shape[1]).astype(np.uint8)

    # Return the generated grayscale image as a NumPy array
    return grayscale_image




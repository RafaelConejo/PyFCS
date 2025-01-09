import tkinter as tk
import os
from tkinter import ttk, Menu, filedialog, messagebox, Scrollbar
import numpy as np
from skimage import color
from PIL import Image, ImageTk
import matplotlib.pyplot as plt


def about_info(root):
    """Muestra la ventana emergente con la información 'About'."""
    about_window = tk.Toplevel(root)  # Crear una nueva ventana emergente
    about_window.title("About PyFCS")
    
    # Desactivar la posibilidad de redimensionar la ventana
    about_window.resizable(False, False)

    # Contenido del "About"
    about_label = tk.Label(about_window, text="PyFCS: Python Fuzzy Color Software\n"
                                                "A color modeling Python Software based on Fuzzy Color Spaces.\n"
                                                "Version 0.1\n\n"
                                                "Contact: rafaconejo@ugr.es", 
                            padx=20, pady=20, font=("Arial", 12), justify="center")
    about_label.pack()

    # Botón para cerrar la ventana de "About"
    close_button = tk.Button(about_window, text="Close", command=about_window.destroy)
    close_button.pack(pady=10)




def get_proto_percentage(prototypes, image, fuzzy_color_space, selected_option):
    """Genera la imagen en escala de grises sin necesidad de una figura de matplotlib."""
    # Convertir la imagen a un array NumPy
    img_np = np.array(image)

    # Comprobar si la imagen tiene un canal alfa (RGBA)
    if img_np.shape[-1] == 4:  # Si tiene 4 canales (RGBA)
        img_np = img_np[..., :3]  # Elimina el canal alfa para quedarte solo con RGB

    # Normalizar los valores de la imagen a rango [0, 1]
    img_np = img_np / 255.0

    lab_image = color.rgb2lab(img_np)
    selected_prototype = prototypes[selected_option]
    print(f"Selected Prototype: {selected_prototype.label}")

    grayscale_image = np.zeros((lab_image.shape[0], lab_image.shape[1]), dtype=np.uint8)
    for y in range(lab_image.shape[0]):
        for x in range(lab_image.shape[1]):
            lab_color = lab_image[y, x]
            membership_degree = fuzzy_color_space.calculate_membership_for_prototype(lab_color, selected_option)

            # Escalar a escala de grises
            grayscale_image[y, x] = int(membership_degree * 255)

    # Devolver la imagen en escala de grises como un array
    return grayscale_image

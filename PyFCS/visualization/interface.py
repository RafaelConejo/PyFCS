import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Get the path to the directory containing PyFCS
current_dir = os.path.dirname(__file__)
pyfcs_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))

# Add the PyFCS path to sys.path
sys.path.append(pyfcs_dir)

### my libraries ###
from PyFCS import Input, Prototype, Visual_tools

# Función para cargar el archivo
def cargar_archivo():
    # Configurar la carpeta por defecto
    default_dir = os.path.join(current_dir, '..', '..', 'fuzzy_color_spaces')
    archivo_path = filedialog.askopenfilename(initialdir=default_dir, filetypes=[("Archivos CNS", "*.cns")])
    if archivo_path:
        procesar_archivo(archivo_path)

# Función para procesar el archivo y generar la visualización
def procesar_archivo(file_path):
    try:
        colorspace_name = os.path.basename(file_path)
        name_colorspace = os.path.splitext(colorspace_name)[0]
        extension = os.path.splitext(colorspace_name)[1]

        # Step 1: Reading the .cns file using the Input class
        input_class = Input.instance(extension)
        color_data = input_class.read_file(file_path)

        # Mostrar la información de los datos en la pestaña correspondiente
        mostrar_info_datos(color_data)

        # Step 2: Creating Prototype objects for each color
        prototypes = []
        for color_name, color_value in color_data.items():
            # Assume that 'color_value' contains the positive prototype and set of negatives
            positive_prototype = color_value['positive_prototype']
            negative_prototypes = color_value['negative_prototypes']

            # Create a Prototype object for each color
            prototype = Prototype(label=color_name, positive=positive_prototype, negatives=negative_prototypes)
            prototypes.append(prototype)

        # Step 3: Visualization of the Voronoi Regions
        mostrar_grafica(prototypes)
    except Exception as e:
        messagebox.showerror("Error", f"Ocurrió un error al procesar el archivo: {e}")

# Función para mostrar la información de los datos
def mostrar_info_datos(color_data):
    info_text.delete('1.0', tk.END)  # Limpiar el contenido anterior
    for color_name, color_value in color_data.items():
        info_text.insert(tk.END, f"Color: {color_name}\n")
        info_text.insert(tk.END, f"  Prototipo positivo: {color_value['positive_prototype']}\n")
        info_text.insert(tk.END, f"  Prototipos negativos: {color_value['negative_prototypes']}\n\n")

# Función para mostrar la gráfica dentro de la pestaña de gráfica
def mostrar_grafica(prototypes):
    # Crear la figura con plot_3d_all
    fig = Visual_tools.plot_3d_all(prototypes)

    # Limpiar el contenido anterior del frame_grafica
    for widget in frame_grafica.winfo_children():
        widget.destroy()

    # Crear un canvas para matplotlib y añadirlo al frame_grafica
    canvas = FigureCanvasTkAgg(fig, master=frame_grafica)
    canvas.draw()
    canvas.get_tk_widget().pack(expand=True, fill='both')

# Configuración de la interfaz gráfica
root = tk.Tk()
root.title("Generador de Gráficos de Colores")
root.geometry('800x600')

# Frame superior para el botón de cargar archivo
top_frame = tk.Frame(root)
top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

# Botón para cargar el archivo
btn_cargar = tk.Button(top_frame, text="Cargar Archivo", command=cargar_archivo)
btn_cargar.pack(side=tk.LEFT)

# Crear un notebook (pestañas) para la gráfica y los datos
notebook = ttk.Notebook(root)
notebook.pack(expand=True, fill='both', padx=10, pady=10)

# Crear el frame para la pestaña de la gráfica
frame_grafica = ttk.Frame(notebook)
notebook.add(frame_grafica, text='Gráfica')

# Crear el frame para la pestaña de información de datos
frame_info = ttk.Frame(notebook)
notebook.add(frame_info, text='Información de Datos')

# Text widget para mostrar la información de los datos en la pestaña correspondiente
info_text = tk.Text(frame_info)
info_text.pack(expand=True, fill='both')

# Ejecución de la interfaz gráfica
root.mainloop()

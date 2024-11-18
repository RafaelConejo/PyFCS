import tkinter as tk
from tkinter import ttk, Menu, filedialog, messagebox, Scrollbar
import sys
import os
from skimage import color
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np

current_dir = os.path.dirname(__file__)
pyfcs_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))

# Add the PyFCS path to sys.path
sys.path.append(pyfcs_dir)

### my libraries ###
from PyFCS import Input

class PyFCSApp:
    def __init__(self, root):
        self.root = root

        # Configuración general de la ventana
        root.title("PyFCS")
        root.geometry("1000x500")
        # self.root.attributes("-fullscreen", True)
        root.configure(bg="gray82")

        # Barra de menú superior
        menubar = Menu(root)
        root.config(menu=menubar)

        # Menús principales
        file_menu = Menu(menubar, tearoff=0)
        file_menu.add_command(label="Exit", command=self.exit_app)
        menubar.add_cascade(label="File", menu=file_menu)

        img_menu = Menu(menubar, tearoff=0)
        img_menu.add_command(label="Open Image")
        img_menu.add_command(label="Save Image")
        img_menu.add_command(label="Close All")
        menubar.add_cascade(label="Image Manager", menu=img_menu)

        fuzzy_menu = Menu(menubar, tearoff=0)
        fuzzy_menu.add_command(label="New Color Space", command=self.new_color_space)
        fuzzy_menu.add_command(label="Load Color Space", command=self.load_color_space)
        fuzzy_menu.add_command(label="Save Color Space", command=self.save_color_space)
        menubar.add_cascade(label="Fuzzy Color Space Manager", menu=fuzzy_menu)

        help_menu = Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self.about_info)
        menubar.add_cascade(label="Help", menu=help_menu)

        # Frame principal de botones y secciones
        main_frame = tk.Frame(root, bg="gray82")
        main_frame.pack(padx=10, pady=10, fill="x")

        # Sección "Image Manager"
        image_manager_frame = tk.LabelFrame(main_frame, text="Image Manager", bg="gray95", padx=10, pady=10)
        image_manager_frame.grid(row=0, column=0, padx=5, pady=5)

        tk.Button(image_manager_frame, text="Open Image").pack(side="left", padx=5)
        tk.Button(image_manager_frame, text="Flickr").pack(side="left", padx=5)
        tk.Button(image_manager_frame, text="Save Image").pack(side="left", padx=5)

        # Sección "Fuzzy Color Space Manager"
        fuzzy_manager_frame = tk.LabelFrame(main_frame, text="Fuzzy Color Space Manager", bg="gray95", padx=10, pady=10)
        fuzzy_manager_frame.grid(row=0, column=1, padx=5, pady=5)

        tk.Button(fuzzy_manager_frame, text="New Color Space").pack(side="left", padx=5)
        tk.Button(fuzzy_manager_frame, text="Load Color Space", command=self.load_color_space).pack(side="left", padx=5)
        tk.Button(fuzzy_manager_frame, text="Save Color Space").pack(side="left", padx=5)

        # Frame para la gráfica 3D y la tabla
        main_canvas_frame = tk.Frame(root, bg="gray82")
        main_canvas_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Pestaña izquierda: LabelFrame "Model 3D"
        model_frame = tk.LabelFrame(main_canvas_frame, text="Model 3D", bg="gray95", padx=10, pady=10, font=("Arial", 12, "bold"))
        model_frame.pack(side="left", fill="both", expand=True, padx=5, pady=5)

        # Canvas para la gráfica 3D
        self.Canvas1 = tk.Canvas(model_frame, bg="white", borderwidth=2, relief="ridge")
        self.Canvas1.pack(fill="both", expand=True)

        # Pestaña derecha: LabelFrame "Data"
        data_frame = tk.LabelFrame(main_canvas_frame, text="Data", bg="gray95", padx=10, pady=10, font=("Arial", 12, "bold"))
        data_frame.pack(side="right", fill="both", expand=True, padx=5, pady=5)

        # Canvas para la tabla de datos
        self.Canvas2 = tk.Canvas(data_frame, bg="white", borderwidth=2, relief="ridge")
        self.Canvas2.pack(side="left", fill="both", expand=True)

        # Barra de desplazamiento para la tabla de datos
        self.scrollbar = Scrollbar(data_frame, orient="vertical", command=self.Canvas2.yview)
        self.scrollbar.pack(side="right", fill="y")

        # Asociar scrollbar al Canvas
        self.Canvas2.configure(yscrollcommand=self.scrollbar.set)

        # Variables adicionales
        self.rgb_data = []  # Datos RGB para la gráfica 3D
        self.graph_widget = None  # Para rastrear el gráfico en el Canvas izquierdo

        self.root.bind("<Escape>", self.toggle_fullscreen)




    def exit_app(self):
        """Pregunta al usuario si quiere salir de la aplicación."""
        confirm_exit = messagebox.askyesno("Exit", "Are you sure you want to exit?")
        if confirm_exit:
            self.root.destroy()


    def new_color_space(self):
        """Lógica para crear un nuevo espacio de color."""
        messagebox.showinfo("New Color Space", "Creating a new color space...")


    def load_color_space(self):
        """Permite seleccionar un archivo de fuzzy_color_spaces y mostrar colores en columnas con barra de scroll."""
        initial_directory = os.getcwd()
        initial_directory = os.path.join(initial_directory, 'fuzzy_color_spaces\\')
        filetypes = [("All Files", "*.*")]
        filename = filedialog.askopenfilename(
            title="Select Fuzzy Color Space File",
            initialdir=initial_directory,
            filetypes=filetypes
        )
        if filename:
            # Leer el archivo y obtener los datos de color
            extension = os.path.splitext(filename)[1]
            input_class = Input.instance(extension)
            color_data = input_class.read_file(filename)

            # Guardar los datos RGB para la gráfica 3D
            self.rgb_data = [
                tuple(map(lambda x: int(x * 255), color.lab2rgb([color_value['positive_prototype']])[0]))
                for color_name, color_value in color_data.items()
            ]

            # Limpiar el Canvas de la tabla de datos
            self.Canvas2.delete("all")
            self.Canvas2.configure(scrollregion=(0, 0, 1000, len(color_data) * 30 + 50))  # Ajustar área de scroll

            x_start = 10  # Coordenada inicial para las columnas
            y_start = 10  # Coordenada inicial para la fila de encabezados
            rect_width, rect_height = 50, 20  # Tamaño de los rectángulos de color

            # Dibujar encabezados de la tabla
            headers = ["R", "G", "B", "Label", "Color"]
            column_widths = [50, 50, 50, 150, 70]  # Ancho de cada columna
            for i, header in enumerate(headers):
                self.Canvas2.create_text(
                    x_start + sum(column_widths[:i]) + column_widths[i] / 2, y_start,
                    text=header, anchor="center", font=("Arial", 10, "bold")
                )

            # Línea inicial para datos
            y_start += 30  # Espacio entre encabezados y datos

            # Dibujar datos en filas
            for color_name, rgb in zip(color_data.keys(), self.rgb_data):
                # Columna R
                self.Canvas2.create_text(
                    x_start + column_widths[0] / 2, y_start,
                    text=str(rgb[0]), anchor="center"
                )
                # Columna G
                self.Canvas2.create_text(
                    x_start + column_widths[0] + column_widths[1] / 2, y_start,
                    text=str(rgb[1]), anchor="center"
                )
                # Columna B
                self.Canvas2.create_text(
                    x_start + sum(column_widths[:2]) + column_widths[2] / 2, y_start,
                    text=str(rgb[2]), anchor="center"
                )
                # Columna Label
                self.Canvas2.create_text(
                    x_start + sum(column_widths[:3]) + column_widths[3] / 2, y_start,
                    text=color_name, anchor="center"
                )
                # Columna Color (rectángulo)
                self.Canvas2.create_rectangle(
                    x_start + sum(column_widths[:4]) + 10, y_start - rect_height / 2,
                    x_start + sum(column_widths[:4]) + 10 + rect_width, y_start + rect_height / 2,
                    fill=f'#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}', outline="black"
                )

                # Avanzar a la siguiente fila
                y_start += 30

            # Actualizar la gráfica 3D
            self.draw_3d_points(filename, len(color_data))
        else:
            messagebox.showwarning("No File Selected", "No file was selected.")

    def draw_3d_points(self, filename, num_elements):
        """Dibuja los puntos RGB en 3D en el Canvas izquierdo usando Matplotlib."""
        if self.graph_widget:
            self.graph_widget.get_tk_widget().destroy()

        fig = plt.Figure(figsize=(5, 4), dpi=100)
        ax = fig.add_subplot(111, projection='3d')

        # Separar los datos RGB
        r_values = [rgb[0] for rgb in self.rgb_data]
        g_values = [rgb[1] for rgb in self.rgb_data]
        b_values = [rgb[2] for rgb in self.rgb_data]

        # Normalizar los valores RGB a [0, 1]
        r_values_normalized = np.array(r_values) / 255
        g_values_normalized = np.array(g_values) / 255
        b_values_normalized = np.array(b_values) / 255

        # Graficar los puntos RGB en 3D con colores normalizados
        ax.scatter(
            r_values_normalized,
            g_values_normalized,
            b_values_normalized,
            c=list(zip(r_values_normalized, g_values_normalized, b_values_normalized)),
            marker='o'
        )

        # Títulos y etiquetas
        file_base_name = os.path.splitext(os.path.basename(filename))[0]
        ax.set_title(f'{file_base_name} - {num_elements} colors', fontsize=10)
        ax.set_xlabel("R")
        ax.set_ylabel("G")
        ax.set_zlabel("B")

        # Agregar la gráfica al Canvas
        self.graph_widget = FigureCanvasTkAgg(fig, master=self.Canvas1)
        self.graph_widget.draw()
        self.graph_widget.get_tk_widget().pack(fill="both", expand=True)

    
    def save_color_space(self):
        """Lógica para guardar el espacio de color."""
        messagebox.showinfo("Save Color Space", "Saving the current color space...")

    def toggle_fullscreen(self, event=None):
        """Alterna entre pantalla completa y ventana normal."""
        current_state = self.root.attributes("-fullscreen")
        self.root.attributes("-fullscreen", not current_state)

    def about_info(self):
        """Muestra la ventana emergente con la información 'About'."""
        about_window = tk.Toplevel(self.root)  # Crear una nueva ventana emergente
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


def start_up():
    root = tk.Tk()
    app = PyFCSApp(root)
    root.mainloop()

if __name__ == '__main__':
    start_up()

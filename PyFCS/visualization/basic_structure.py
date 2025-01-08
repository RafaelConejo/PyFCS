import tkinter as tk
from tkinter import ttk, Menu, filedialog, messagebox, Scrollbar, DISABLED, NORMAL
import sys
import os
from skimage import color
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from PIL import Image, ImageTk

current_dir = os.path.dirname(__file__)
pyfcs_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))

# Add the PyFCS path to sys.path
sys.path.append(pyfcs_dir)

### my libraries ###
from PyFCS import Input, Visual_tools, ReferenceDomain, Prototype, FuzzyColorSpace
import PyFCS.visualization.utils_structure as utils_structure

class PyFCSApp:

    def __init__(self, root):
        self.root = root
        self.COLOR_SPACE = False
        self.hex_color = []         # Save points colors

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

        tk.Button(image_manager_frame, text="Open Image", command=self.open_image).pack(side="left", padx=5)
        tk.Button(image_manager_frame, text="Flickr").pack(side="left", padx=5)
        tk.Button(image_manager_frame, text="Save Image").pack(side="left", padx=5)

        # Sección "Fuzzy Color Space Manager"
        fuzzy_manager_frame = tk.LabelFrame(main_frame, text="Fuzzy Color Space Manager", bg="gray95", padx=10, pady=10)
        fuzzy_manager_frame.grid(row=0, column=1, padx=5, pady=5)

        tk.Button(fuzzy_manager_frame, text="New Color Space").pack(side="left", padx=5)
        tk.Button(fuzzy_manager_frame, text="Load Color Space", command=self.load_color_space).pack(side="left", padx=5)
        tk.Button(fuzzy_manager_frame, text="Save Color Space").pack(side="left", padx=5)

        # Frame principal para organizar pestañas y área derecha
        main_content_frame = tk.Frame(root, bg="gray82")
        main_content_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Área para imágenes
        image_area_frame = tk.LabelFrame(main_content_frame, text="Image Display", bg="gray95", padx=10, pady=10)
        image_area_frame.pack(side="left", fill="both", expand=True, padx=5, pady=5)

        self.image_canvas = tk.Canvas(image_area_frame, bg="white", borderwidth=2, relief="ridge")
        self.image_canvas.pack(fill="both", expand=True)

        # Notebook con pestañas para "Model 3D" y "Data"
        notebook = ttk.Notebook(main_content_frame)
        notebook.pack(side="right", fill="both", expand=True, padx=5, pady=5)

        # Pestaña "Model 3D"
        model_3d_tab = tk.Frame(notebook, bg="gray95")
        notebook.add(model_3d_tab, text="Model 3D")

        # Variable para manejar el estado de los botones de opción
        self.model_3d_option = tk.StringVar(value="Centroid")  # Valor inicial

        # Frame para los botones de opción
        buttons_frame = tk.Frame(model_3d_tab, bg="gray95")
        buttons_frame.pack(side="top", fill="x", pady=5)

        # Crear los botones de opción
        options = ["Centroid", "Core", "0.5-cut", "Support"]
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

        # Canvas para la gráfica 3D
        self.Canvas1 = tk.Canvas(model_3d_tab, bg="white", borderwidth=2, relief="ridge")
        self.Canvas1.pack(side="left", fill="both", expand=True)

        # Crear un Frame a la derecha para los botones de color
        self.colors_frame = tk.Frame(model_3d_tab, bg="gray95")
        self.colors_frame.pack(side="right", fill="y", padx=10, pady=10)

        # Botón "Select All"
        self.select_all_button = tk.Button(
            self.colors_frame,
            text="Select All",
            bg="lightgray",
            font=("Arial", 10),
            command=self.select_all_color  # Asume que tienes una función para esto
        )
        self.select_all_button.pack(pady=5)


        # Pestaña "Data"
        data_tab = tk.Frame(notebook, bg="gray95")
        notebook.add(data_tab, text="Data")

        self.Canvas2 = tk.Canvas(data_tab, bg="white", borderwidth=2, relief="ridge")
        self.Canvas2.pack(side="left", fill="both", expand=True)

        self.scrollbar = Scrollbar(data_tab, orient="vertical", command=self.Canvas2.yview)
        self.scrollbar.pack(side="right", fill="y")
        self.Canvas2.configure(yscrollcommand=self.scrollbar.set)

        # Variables adicionales
        self.rgb_data = []  # Datos RGB para la gráfica 3D
        self.graph_widget = None  # Para rastrear el gráfico en el Canvas izquierdo

        self.root.bind("<Escape>", self.toggle_fullscreen)







    ########################################################################################### Utils APP ###########################################################################################
    def exit_app(self):
        """Pregunta al usuario si quiere salir de la aplicación."""
        confirm_exit = messagebox.askyesno("Exit", "Are you sure you want to exit?")
        if confirm_exit:
            self.root.destroy()
    

    def toggle_fullscreen(self, event=None):
        """Alterna entre pantalla completa y ventana normal."""
        current_state = self.root.attributes("-fullscreen")
        self.root.attributes("-fullscreen", not current_state)


    def show_loading(self):
        # Crear una nueva ventana para mostrar "Loading..."
        self.load_window = tk.Toplevel(self.root)
        self.load_window.title("Cargando")
        label = tk.Label(self.load_window, text="Loading...", padx=20, pady=20)
        label.pack()
        self.load_window.geometry("200x100")

        # Asegúrate de que se actualice la ventana
        self.root.update_idletasks()


    def hide_loading(self):
        if hasattr(self, 'load_window'):
            self.load_window.destroy()


    def about_info(self):
        utils_structure.about_info(self.root)








    ########################################################################################### Main Functions ###########################################################################################
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

            # Limpiar el Canvas de la tabla de datos
            self.Canvas2.delete("all")
            self.Canvas2.configure(scrollregion=(0, 0, 1000, len(color_data) * 30 + 50))  # Ajustar área de scroll

            x_start = 10  # Coordenada inicial para las columnas
            y_start = 10  # Coordenada inicial para la fila de encabezados
            rect_width, rect_height = 50, 20  # Tamaño de los rectángulos de color

            # Dibujar encabezados de la tabla
            headers = ["L", "a", "b", "Label", "Color"]
            column_widths = [50, 50, 50, 150, 70]  # Ancho de cada columna
            for i, header in enumerate(headers):
                self.Canvas2.create_text(
                    x_start + sum(column_widths[:i]) + column_widths[i] / 2, y_start,
                    text=header, anchor="center", font=("Arial", 10, "bold")
                )

            # Línea inicial para datos
            y_start += 30  # Espacio entre encabezados y datos

            # Dibujar datos en filas
            self.hex_color = {}
            self.color_matrix = []
            for color_name, color_value in color_data.items():
                lab = color_value['positive_prototype']
                lab = np.array(lab)

                self.color_matrix.append(color_name)

                # Columna L (el primer componente de LAB)
                self.Canvas2.create_text(
                    x_start + column_widths[0] / 2, y_start,
                    text=str(round(lab[0], 2)), anchor="center"  # Mostrar el valor L con 2 decimales
                )
                # Columna A (el segundo componente de LAB)
                self.Canvas2.create_text(
                    x_start + column_widths[0] + column_widths[1] / 2, y_start,
                    text=str(round(lab[1], 2)), anchor="center"  # Mostrar el valor A con 2 decimales
                )
                # Columna B (el tercer componente de LAB)
                self.Canvas2.create_text(
                    x_start + sum(column_widths[:2]) + column_widths[2] / 2, y_start,
                    text=str(round(lab[2], 2)), anchor="center"  # Mostrar el valor B con 2 decimales
                )
                # Columna Label
                self.Canvas2.create_text(
                    x_start + sum(column_widths[:3]) + column_widths[3] / 2, y_start,
                    text=color_name, anchor="center"
                )

                # Guardar los datos RGB para la gráfica 3D
                rgb_data = tuple(map(lambda x: int(x * 255), color.lab2rgb([color_value['positive_prototype']])[0]))
                self.hex_color[(f'#{rgb_data[0]:02x}{rgb_data[1]:02x}{rgb_data[2]:02x}')] = lab

                self.Canvas2.create_rectangle(
                    x_start + sum(column_widths[:4]) + 10, y_start - rect_height / 2,
                    x_start + sum(column_widths[:4]) + 10 + rect_width, y_start + rect_height / 2,
                    fill=f'#{rgb_data[0]:02x}{rgb_data[1]:02x}{rgb_data[2]:02x}', outline="black"  
                )

                # Avanzar a la siguiente fila
                y_start += 30


            # Create Voronoi
            self.volume_limits = ReferenceDomain(0, 100, -128, 127, -128, 127)

            # Step 2: Creating Prototype objects for each color
            self.prototypes = []
            for color_name, color_value in color_data.items():
                # Assume that 'color_value' contains the positive prototype and set of negatives
                positive_prototype = color_value['positive_prototype']
                negative_prototypes = color_value['negative_prototypes']

                # Create a Prototype object for each color
                prototype = Prototype(label=color_name, positive=positive_prototype, negatives=negative_prototypes, add_false=True)
                self.prototypes.append(prototype)
            
            self.fuzzy_color_space = FuzzyColorSpace(space_name=" " , prototypes=self.prototypes)
            self.cores = self.fuzzy_color_space.get_cores()
            self.supports = self.fuzzy_color_space.get_supports()


            # Actualizar la gráfica 3D
            self.COLOR_SPACE = True
            self.file_base_name = os.path.splitext(os.path.basename(filename))[0]
            self.color_data = color_data

            self.selected_centroids = color_data
            self.colors = self.hex_color
            self.selected_proto = self.prototypes
            self.selected_core = self.cores
            self.selected_support = self.supports
            self.on_option_select()

        else:
            messagebox.showwarning("No File Selected", "No file was selected.")



    def new_color_space(self):
        """Lógica para crear un nuevo espacio de color."""
        messagebox.showinfo("New Color Space", "Creating a new color space...")
    
    def save_color_space(self):
        """Lógica para guardar el espacio de color."""
        messagebox.showinfo("Save Color Space", "Saving the current color space...")









    ########################################################################################### Funtions Model 3D ###########################################################################################
    def on_option_select(self):
            if self.COLOR_SPACE:
                option = self.model_3d_option.get()  # Obtiene el valor seleccionado
                if option == "Centroid":
                    fig = Visual_tools.plot_all_centroids(self.file_base_name, self.selected_centroids, self.colors) 
                    self.draw_model_3D(fig)  # Pasar la figura al Canvas para dibujarla
                
                elif option == "0.5-cut":
                    fig = Visual_tools.plot_all_prototypes(self.selected_proto, self.volume_limits, self.hex_color) 
                    self.draw_model_3D(fig)  # Pasar la figura al Canvas para dibujarla
                
                elif option == "Core":
                    fig = Visual_tools.plot_all_prototypes(self.selected_core, self.volume_limits, self.hex_color) 
                    self.draw_model_3D(fig)  # Pasar la figura al Canvas para dibujarla
                
                elif option == "Support":
                    fig = Visual_tools.plot_all_prototypes(self.selected_support, self.volume_limits, self.hex_color) 
                    self.draw_model_3D(fig)  # Pasar la figura al Canvas para dibujarla


    def draw_model_3D(self, fig):
        """Dibuja la gráfica 3D en el canvas de Tkinter."""
        if self.graph_widget:
            self.graph_widget.get_tk_widget().destroy()

        self.graph_widget = FigureCanvasTkAgg(fig, master=self.Canvas1)  # Crear el widget de matplotlib
        self.graph_widget.draw()  # Dibujar la figura
        self.graph_widget.get_tk_widget().pack(fill="both", expand=True)  # Empacar el widget en el canvas

        self.display_color_buttons(self.color_matrix)
    

    def select_all_color(self):
        # Función que maneja los botones de opción
        self.selected_centroids = self.color_data
        self.colors = self.hex_color
        self.selected_proto = self.prototypes

        # Desmarcar todos los botones
        for color, var in self.selected_colors.items():
            var.set(False) 
        
        self.on_option_select()



    def select_color(self):
        # Función que maneja los botones de opción
        # Crear una lista para guardar las posiciones de los colores seleccionados
        selected_centroids = {}
        selected_indices = []

        # Iterar sobre los colores y verificar cuáles están seleccionados
        for color_name, selected in self.selected_colors.items():
            if selected.get():  # Si el color está marcado
                # Obtener la posición del color en color_data
                if color_name in self.color_data:
                    selected_centroids[color_name] = self.color_data[color_name]
                    keys = list(self.color_data.keys())
                    selected_indices.append(keys.index(color_name))
        
        self.colors = {
            hex_color_key: lab_value for index in selected_indices
            for hex_color_key, lab_value in self.hex_color.items()
            if np.array_equal(lab_value, self.color_data[keys[index]]['positive_prototype'])
        }
        self.selected_proto = [self.prototypes[i] for i in selected_indices]
        self.selected_core = [self.cores[i] for i in selected_indices]
        self.selected_support = [self.supports[i] for i in selected_indices]
        
        self.selected_centroids = selected_centroids
        self.on_option_select()

        

    def display_color_buttons(self, colors):
        # Si ya existían botones previamente, mantener los colores seleccionados
        selected_colors = {color for color, var in self.selected_colors.items() if var.get()} if hasattr(self, 'selected_colors') else set()

        # Solo eliminar los botones si los colores han cambiado
        if hasattr(self, 'color_buttons'):
            for button in self.color_buttons:
                button.destroy()

        # Crear un botón por cada color cargado
        self.selected_colors = {}  # Reiniciar el diccionario de variables
        self.color_buttons = []  # Lista para almacenar los botones creados

        for color in colors:
            # Si el color estaba seleccionado previamente, lo mantenemos marcado
            is_selected = color in selected_colors

            # Crear la variable BooleanVar con el estado correspondiente
            self.selected_colors[color] = tk.BooleanVar(value=is_selected)

            # Crear el botón
            button = tk.Checkbutton(
                self.colors_frame,
                text=color,
                variable=self.selected_colors[color],  # Variable para seleccionar el color
                bg="gray95",  # Fondo del botón
                font=("Arial", 10),
                onvalue=True,  # Valor cuando está marcado
                offvalue=False,  # Valor cuando no está marcado
                command=lambda c=color: self.select_color(),
            )
            button.pack(anchor="w", pady=2, padx=10)
            
            self.color_buttons.append(button)  # Almacenamos el botón creado












    ########################################################################################### Functions Image Display ###########################################################################################
    def open_image(self):
        """Permite seleccionar un archivo de fuzzy_color_spaces y mostrar colores en columnas con barra de scroll."""
        initial_directory = os.getcwd()
        initial_directory = os.path.join(initial_directory, 'image_test\\VITA_CLASSICAL\\')
        filetypes = [("All Files", "*.jpg;*.jpeg;*.png;*.bmp")]
        filename = filedialog.askopenfilename(
            title="Select an Image",
            initialdir=initial_directory,
            filetypes=filetypes
        )
        if filename:
            # Crear ventana flotante
            self.create_floating_window(50, 50, filename)


    def create_floating_window(self, x, y, filename):
        """Crea una ventana flotante con la imagen dentro, barra de título y menú desplegable."""
        # Generar un identificador único para la ventana
        window_id = f"floating_{len(self.image_canvas.find_all())}"

        # Cargar la imagen y asociarla al window_id
        img = Image.open(filename)
        img.thumbnail((300, 300))  # Ajustar el tamaño si es necesario

        self.images = {}
        self.images[window_id] = img
        img_tk = ImageTk.PhotoImage(img)

        # Guardar la referencia de la imagen en un diccionario
        if not hasattr(self, "floating_images"):
            self.floating_images = {}
            self.floating_frames = {}
        self.floating_images[window_id] = img_tk

        # Crear rectángulo de fondo para la ventana
        self.image_canvas.create_rectangle(
            x, y, x + 320, y + 360, outline="black", fill="white", width=2, tags=(window_id, "floating")
        )

        # Crear barra de título en la parte superior
        self.image_canvas.create_rectangle(
            x, y, x + 320, y + 30, outline="black", fill="gray", tags=(window_id, "floating")
        )

        # Agregar texto con el nombre del archivo en la barra de título
        self.image_canvas.create_text(
            x + 50, y + 15, anchor="w", text=os.path.basename(filename), fill="white", font=("Arial", 10), tags=(window_id, "floating")
        )

        # Agregar botón de cierre en la barra de título
        self.image_canvas.create_rectangle(
            x + 290, y + 5, x + 310, y + 25, outline="black", fill="red", tags=(window_id, "floating", f"{window_id}_close_button")
        )
        self.image_canvas.create_text(
            x + 300, y + 15, text="X", fill="white", font=("Arial", 10, "bold"), tags=(window_id, "floating", f"{window_id}_close_button")
        )

        # Agregar una flecha en la parte izquierda de la barra de título
        self.image_canvas.create_text(
            x + 15, y + 15, text="▼", fill="white", font=("Arial", 12), tags=(window_id, "floating", f"{window_id}_arrow_button")
        )

        # Dibujar la imagen dentro del rectángulo de la ventana
        self.image_canvas.create_image(
            x + 10, y + 40, anchor="nw", image=self.floating_images[window_id], tags=(window_id, "floating")
        )

        # Función para cerrar la ventana flotante
        def close_window(event):
            # Eliminar todos los elementos asociados al window_id
            self.image_canvas.delete(window_id)
            # Eliminar la imagen del diccionario
            del self.floating_images[window_id]
            
            # Cerrar y eliminar el Frame del diccionario
            if window_id in self.floating_frames:
                # Destruir el Frame
                self.floating_frames[window_id].destroy()  
                
                # Verificar si este Frame es el proto_options actual
                if self.proto_options is self.floating_frames[window_id]:
                    self.proto_options = None  # Restablecer la referencia a None

                # Eliminar del diccionario
                del self.floating_frames[window_id]

        # Función para mostrar el menú desplegable
        def show_menu_image(event):
            menu = Menu(self.root, tearoff=0)
            menu.add_command(label="Original Image", state=DISABLED)

            menu.add_separator()

            menu.add_command(
                label="Get MemberDegree",
                state=NORMAL if self.COLOR_SPACE else DISABLED,  # Habilitar/Deshabilitar
                command=lambda: self.plot_proto_options(window_id)  
            )
            menu.post(event.x_root, event.y_root)

        # Hacer que la ventana flotante sea movible
        def start_move(event):
            # Guardar las coordenadas iniciales
            self.last_x, self.last_y = event.x, event.y

        def move_window(event):
            # Calcular el desplazamiento
            dx, dy = event.x - self.last_x, event.y - self.last_y
            # Mover todos los elementos asociados al window_id
            self.image_canvas.move(window_id, dx, dy)
            self.last_x, self.last_y = event.x, event.y

        # Vincular eventos para mover la ventana
        self.image_canvas.tag_bind(window_id, "<Button-1>", start_move)
        self.image_canvas.tag_bind(window_id, "<B1-Motion>", move_window)
        # Vincular eventos para el botón de cierre
        self.image_canvas.tag_bind(f"{window_id}_close_button", "<Button-1>", close_window)
        # Vincular eventos para la flecha (menú desplegable)
        self.image_canvas.tag_bind(f"{window_id}_arrow_button", "<Button-1>", show_menu_image)




    def plot_proto_options(self, window_id):
        """Crea un Frame dentro de image_canvas con Radiobuttons y scrollbars."""
        items = self.image_canvas.find_withtag(window_id)
        if not items:
            print(f"No se encontró una ventana flotante con id {window_id}")
            return

        # Si ya existe el Frame de opciones para este window_id, simplemente lo traemos a primer plano
        if window_id in self.floating_frames:
            self.proto_options = self.floating_frames[window_id] 
            self.proto_options.tkraise()  # Lleva el Frame al frente
            return

        # Si no existe, creamos un nuevo Frame
        self.proto_options = tk.Frame(self.image_canvas, bg="white", relief="solid", bd=1)
        self.floating_frames[window_id] = self.proto_options  # Guardar el Frame en el diccionario

        # Continuar con la creación del Canvas y los Radiobuttons como antes...
        self.canvas = tk.Canvas(self.proto_options, bg="white")
        self.canvas.grid(row=0, column=0, sticky="nsew")

        self.inner_frame = tk.Frame(self.canvas, bg="white")
        self.canvas.create_window((0, 0), window=self.inner_frame, anchor="nw")

        # Aquí puedes seguir con la creación de Radiobuttons, Scrollbars, etc.
        colors = self.color_matrix
        self.current_proto = tk.StringVar(value=colors[0])

        for color in colors:
            rb = tk.Radiobutton(self.inner_frame, text=color, variable=self.current_proto, value=color,
                                bg="white", anchor="w", font=("Arial", 10), relief="flat", command=self.get_proto_percentage(window_id))
            rb.pack(fill="x", padx=5, pady=2)

        # Configurar scrollbars y demás...
        self.v_scroll = tk.Scrollbar(self.proto_options, orient=tk.VERTICAL, command=self.canvas.yview)
        self.v_scroll.grid(row=0, column=1, sticky="ns", padx=5)

        self.h_scroll = tk.Scrollbar(self.proto_options, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.h_scroll.grid(row=1, column=0, sticky="ew", padx=5)

        self.canvas.configure(yscrollcommand=self.v_scroll.set, xscrollcommand=self.h_scroll.set)
        self.inner_frame.update_idletasks()
        self.canvas.config(scrollregion=self.canvas.bbox("all"))

        self.proto_options.grid_rowconfigure(0, weight=1)
        self.proto_options.grid_columnconfigure(0, weight=1)

        x1, y1, x2, y2 = self.image_canvas.bbox(items[0])  
        frame_x = x2 + 10
        frame_y = y1
        self.proto_options.place(x=frame_x, y=frame_y, width=100, height=200)

        # Vincular el movimiento del Frame a la ventana flotante
        self.image_canvas.bind("<B1-Motion>", lambda event: self.copy_main_move(event, window_id))




    def copy_main_move(self, event, window_id):
        """Mover la barra de opciones junto con la ventana flotante."""
        items = self.image_canvas.find_withtag(window_id)
        if items:
            x1, y1, x2, y2 = self.image_canvas.bbox(items[0])
            frame_width = 120
            frame_height = 150

            # Calcular nueva posición del Frame
            frame_x = x2 + 10
            frame_y = y1

            # Restringir el Frame al área de `image_canvas`
            canvas_width = self.image_canvas.winfo_width()
            canvas_height = self.image_canvas.winfo_height()

            if frame_x + frame_width > canvas_width:  # Si se sale por la derecha
                frame_x = canvas_width - frame_width

            if frame_y + frame_height > canvas_height:  # Si se sale por abajo
                frame_y = canvas_height - frame_height

            if hasattr(self, "proto_options") and self.proto_options is not None:
                self.proto_options.place(x=frame_x, y=frame_y)




    def get_proto_percentage(self, window_id):
        """Acción al hacer clic en un botón de color."""
        self.show_loading()
        pos = self.color_matrix.index(self.current_proto.get())
        fig = utils_structure.get_proto_percentage(prototypes=self.prototypes, image=self.images[window_id], fuzzy_color_space=self.fuzzy_color_space, selected_option=pos)
        self.hide_loading()

        # Convertir la figura a un objeto compatible con Tkinter
        canvas = FigureCanvasTkAgg(fig, master=self.image_canvas)
        canvas.draw() 

        # Obtener la imagen de la figura
        img = canvas.get_tk_widget()

        # Primero, calcula la posición donde quieres colocar la imagen
        x, y, _, _ = self.image_canvas.bbox(window_id) 

        # Colocar el widget de la imagen en la ventana flotante
        img.place(x=x + 10, y=y + 40)
    







def start_up():
    root = tk.Tk()
    app = PyFCSApp(root)
    root.mainloop()

if __name__ == '__main__':
    start_up()

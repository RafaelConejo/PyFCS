import tkinter as tk
from tkinter import ttk, Menu

class PyFCSApp:
    def __init__(self, root):
        root.title("PyFCS")
        root.geometry("800x400")
        root.configure(bg="gray82")
        
        # Barra de menú superior
        menubar = Menu(root)
        root.config(menu=menubar)
        
        # Menús principales
        menubar.add_cascade(label="File")
        menubar.add_cascade(label="Image Manager")
        menubar.add_cascade(label="Fuzzy Color Space Manager")
        menubar.add_cascade(label="Help")
        
        # Frame principal de botones y secciones
        main_frame = tk.Frame(root, bg="gray82")
        main_frame.pack(padx=10, pady=10, fill="x")
        
        # Sección "Image Manager"
        image_manager_frame = tk.LabelFrame(main_frame, text="Image Manager", bg="gray82", padx=10, pady=10)
        image_manager_frame.grid(row=0, column=0, padx=5, pady=5)
        
        tk.Button(image_manager_frame, text="Add Image").pack(side="left", padx=5)
        tk.Button(image_manager_frame, text="Flickr").pack(side="left", padx=5)
        tk.Button(image_manager_frame, text="Properties").pack(side="left", padx=5)
        
        # Sección "Fuzzy Color Space Manager"
        fuzzy_manager_frame = tk.LabelFrame(main_frame, text="Fuzzy Color Space Manager", bg="gray82", padx=10, pady=10)
        fuzzy_manager_frame.grid(row=0, column=1, padx=5, pady=5)
        
        tk.Button(fuzzy_manager_frame, text="Add Color Space").pack(side="left", padx=5)
        tk.Button(fuzzy_manager_frame, text="Info").pack(side="left", padx=5)
        tk.Button(fuzzy_manager_frame, text="Edit").pack(side="left", padx=5)

        # Canvas (malla) en la parte inferior
        canvas_frame = tk.Frame(root, bg="gray82")
        canvas_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.Canvas1 = tk.Canvas(canvas_frame, bg="white", borderwidth=2, relief="ridge")
        self.Canvas1.pack(fill="both", expand=True)
        self.Canvas1.create_text(100, 50, text="Malla", fill="black")

def start_up():
    root = tk.Tk()
    app = PyFCSApp(root)
    root.mainloop()

if __name__ == '__main__':
    start_up()

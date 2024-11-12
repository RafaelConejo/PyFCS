import os
import sys
from skimage import color
import numpy as np
import matplotlib.pyplot as plt

# Get the path to the directory containing PyFCS
current_dir = os.path.dirname(__file__)
pyfcs_dir = os.path.abspath(os.path.join(current_dir, '..', '..', '..'))

# Add the PyFCS path to sys.path
sys.path.append(pyfcs_dir)

### my libraries ###
from PyFCS import Input, Prototype, FuzzyColorSpace
from PyFCS.input_output.utils import Utils

# Función para reconstruir la imagen y guardarla con las divisiones y leyenda
def reconstruct_and_save_image_with_legend(colorized_image, prototypes, prototype_colors, img_path):
    # Crear el directorio de resultados si no existe
    results_dir = os.path.join("imagen_test", "VITA_RESULTS")
    os.makedirs(results_dir, exist_ok=True)

    # Ruta para guardar la imagen resultante
    result_image_path = os.path.join(results_dir, os.path.basename(img_path))

    # Crear la figura y mostrar la imagen procesada
    fig, ax = plt.subplots()
    ax.imshow(colorized_image)
    plt.title('Processed Image (Colored by Closest Prototype)')
    plt.axis('off')  # Ocultar ejes

    # Crear líneas de división para dividir en 3x3 secciones
    img_height, img_width, _ = colorized_image.shape
    height_third = img_height // 3
    width_third = img_width // 3

    # Dibujar líneas verticales y horizontales para la división en 3x3
    for i in range(1, 3):
        ax.axhline(i * height_third, color='white', linewidth=1)
        ax.axvline(i * width_third, color='white', linewidth=1)

    # Crear leyenda con los prototipos
    handles = [plt.Line2D([0], [0], marker='o', color='w', markerfacecolor=prototype_colors[p.label], markersize=10)
               for p in prototypes]
    labels = [p.label for p in prototypes]

    # Ajustar la leyenda y colocarla fuera de la imagen
    plt.legend(handles, labels, loc='center left', bbox_to_anchor=(1, 0.5), title='Prototypes')
    plt.tight_layout()

    # Guardar la figura completa con la leyenda y las líneas de división
    plt.savefig(result_image_path, bbox_inches='tight')
    plt.close(fig)
    print(f"Imagen procesada guardada en: {result_image_path}")

# Función principal para procesar todas las imágenes en el directorio
def main():
    colorspace_name = 'VITA-CLASSICAL-BLACK-2.cns'
    img_dir = os.path.join(".", "imagen_test", "VITA_CLASSICAL")
    IMG_WIDTH = 308
    IMG_HEIGHT = 448

    name_colorspace = os.path.splitext(colorspace_name)[0]
    extension = os.path.splitext(colorspace_name)[1]

    # Leer el archivo .cns usando la clase Input
    actual_dir = os.getcwd()
    color_space_path = os.path.join(actual_dir, 'fuzzy_color_spaces', colorspace_name)
    input_class = Input.instance(extension)
    color_data = input_class.read_file(color_space_path)

    # Crear objetos Prototype para cada color
    prototypes = []
    for color_name, color_value in color_data.items():
        positive_prototype = color_value['positive_prototype']
        negative_prototypes = color_value['negative_prototypes']
        prototype = Prototype(label=color_name, positive=positive_prototype, negatives=negative_prototypes)
        prototypes.append(prototype)

    # Crear el espacio de color difuso con los objetos Prototype
    fuzzy_color_space = FuzzyColorSpace(space_name=name_colorspace, prototypes=prototypes)

    # Definir colores diferenciados para los prototipos
    color_map = plt.cm.get_cmap('tab20', len(prototypes))
    prototype_colors = {prototype.label: color_map(i)[:3] for i, prototype in enumerate(prototypes)}
    prototype_colors["BLACK"] = (0, 0, 0)  # RGB para negro

    # Procesar cada imagen en el directorio
    for filename in os.listdir(img_dir):
        if filename.endswith(".png"):
            img_path = os.path.join(img_dir, filename)
            image = Utils.image_processing(img_path, IMG_WIDTH, IMG_HEIGHT)

            if image is None:
                print(f"Failed to load the image {filename}.")
                continue

            lab_image = color.rgb2lab(image)
            colorized_image = np.zeros((image.shape[0], image.shape[1], 3), dtype=np.uint8)
            membership_cache = {}

            # Procesar cada píxel de la imagen
            for y in range(image.shape[0]):
                for x in range(image.shape[1]):
                    lab_color = tuple(lab_image[y, x])

                    # Comprobar si el color LAB ya ha sido procesado
                    if lab_color in membership_cache:
                        membership_degrees = membership_cache[lab_color]
                    else:
                        # Calcular los grados de pertenencia si no están en el diccionario
                        membership_degrees = fuzzy_color_space.calculate_membership(lab_color)
                        membership_cache[lab_color] = membership_degrees

                    # Encontrar el prototipo con el mayor grado de pertenencia
                    max_membership = -1
                    best_prototype = None

                    for name, degree in membership_degrees.items():
                        if degree > max_membership:
                            max_membership = degree
                            best_prototype = next(p for p in prototypes if p.label == name)

                    # Asignar el color RGB del prototipo al píxel
                    if best_prototype:
                        rgb_color = np.array(prototype_colors[best_prototype.label]) * 255
                        colorized_image[y, x] = rgb_color.astype(np.uint8)

            # Llamar a la función para reconstruir y guardar la imagen con leyenda y divisiones
            reconstruct_and_save_image_with_legend(colorized_image, prototypes, prototype_colors, img_path)

if __name__ == "__main__":
    main()

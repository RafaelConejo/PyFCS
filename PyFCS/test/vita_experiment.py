import os
import sys
from skimage import color
import numpy as np
import matplotlib.pyplot as plt

# Get the path to the directory containing PyFCS
current_dir = os.path.dirname(__file__)
pyfcs_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))

# Add the PyFCS path to sys.path
sys.path.append(pyfcs_dir)

### my libraries ###
from PyFCS import Input, Prototype, FuzzyColorSpace
from PyFCS.input_output.utils import Utils

def process_image(img_path, prototypes, fuzzy_color_space, prototype_colors):
    IMG_WIDTH = 308 
    IMG_HEIGHT = 448 
    image = Utils.image_processing(img_path, IMG_WIDTH, IMG_HEIGHT)

    if image is None:
        print(f"Failed to load the image {img_path}.")
        return None

    lab_image = color.rgb2lab(image)
    colorized_image = np.zeros((image.shape[0], image.shape[1], 3), dtype=np.uint8)
    membership_values = np.zeros((image.shape[0], image.shape[1]), dtype=object)

    membership_cache = {}
    region_counts = [{}, {}, {}]  # Tres regiones correspondientes a 1,2; 2,2; 3,2

    # Definir los límites para las divisiones en 3x3
    height_third = image.shape[0] // 3
    width_third = image.shape[1] // 3

    # Recorrer solo los píxeles en la columna central de cada tercio
    for y in range(image.shape[0]):
        for x in range(image.shape[1]):
            # Identificar si el píxel cae en una de las tres secciones centrales
            if width_third <= x < 2 * width_third:  # Solo columna central
                if y < height_third:
                    region_idx = 0  # Región 1,2
                elif height_third <= y < 2 * height_third:
                    region_idx = 1  # Región 2,2
                elif 2 * height_third <= y < image.shape[0]:
                    region_idx = 2  # Región 3,2
                else:
                    continue  # Saltar cualquier otro caso (aunque no debería haber)

                lab_color = tuple(lab_image[y, x])

                # Calcular grados de membresía si no están en caché
                if lab_color in membership_cache:
                    membership_degrees = membership_cache[lab_color]
                else:
                    membership_degrees = fuzzy_color_space.calculate_membership(lab_color)
                    membership_cache[lab_color] = membership_degrees

                membership_values[y, x] = membership_degrees
                max_membership = -1
                best_prototype = None

                # Determinar el prototipo con mayor membresía
                for name, degree in membership_degrees.items():
                    if degree > max_membership:
                        max_membership = degree
                        best_prototype = next(p for p in prototypes if p.label == name)

                if best_prototype:
                    rgb_color = np.array(prototype_colors[best_prototype.label]) * 255
                    colorized_image[y, x] = rgb_color.astype(np.uint8)

                    label = best_prototype.label
                    if label in region_counts[region_idx]:
                        region_counts[region_idx][label] += 1
                    else:
                        region_counts[region_idx][label] = 1

    # Obtener los 3 prototipos principales por cada región central
    top_prototypes_per_section = []
    for counts in region_counts:
        sorted_prototypes = sorted(
            {k: v for k, v in counts.items() if k != "BLACK"}.items(),
            key=lambda item: item[1],
            reverse=True
        )
        top_prototypes_per_section.append([proto for proto, _ in sorted_prototypes[:3]])

    return top_prototypes_per_section



def main():
    colorspace_name = 'VITA-CLASSICAL-BLACK-2.cns'
    img_dir = os.path.join(".", "imagen_test\\VITA_CLASSICAL")

    name_colorspace = os.path.splitext(colorspace_name)[0]
    extension = os.path.splitext(colorspace_name)[1]

    actual_dir = os.getcwd()
    color_space_path = os.path.join(actual_dir, 'fuzzy_color_spaces\\' + colorspace_name)
    input_class = Input.instance(extension)
    color_data = input_class.read_file(color_space_path)

    prototypes = []
    for color_name, color_value in color_data.items():
        positive_prototype = color_value['positive_prototype']
        negative_prototypes = color_value['negative_prototypes']
        prototype = Prototype(label=color_name, positive=positive_prototype, negatives=negative_prototypes)
        prototypes.append(prototype)

    fuzzy_color_space = FuzzyColorSpace(space_name=name_colorspace, prototypes=prototypes)
    color_map = plt.cm.get_cmap('tab20', len(prototypes))
    prototype_colors = {prototype.label: color_map(i)[:3] for i, prototype in enumerate(prototypes)}
    prototype_colors["BLACK"] = (0, 0, 0)

    image_top_prototypes = {}
    for filename in os.listdir(img_dir):
        if filename.endswith(".png"):
            img_path = os.path.join(img_dir, filename)
            top_prototypes = process_image(img_path, prototypes, fuzzy_color_space, prototype_colors)
            if top_prototypes:
                image_top_prototypes[filename] = top_prototypes

    # Print or save the results
    print("Top 3 prototypes per section for each image:")
    for image_name, top_prototypes in image_top_prototypes.items():
        print(f"{image_name}: {top_prototypes}")

if __name__ == "__main__":
    main()

import cv2
import numpy as np
from skimage import color
import matplotlib.pyplot as plt

### my libraries ###
from input_output import read_color_space
from geometry.Point import Point
from geometry.ReferenceDomain import ReferenceDomain
from fuzzy.VoronoiFuzzyColor import VoronoiFuzzyColor
from fuzzy.membershipfunction.Spline05Function1D import Spline05Function1D


def main():
    # Aca estoy usando el 70 por ciento del tamaño original de la imagen, lo mejor para reducir 
    IMG_WIDTH = 335
    IMG_HEIGHT = 400
    img_path = ".\\imagen_test\\cuadro.png"
    color_space_path = '.\\fuzzy_color_spaces\\BRUGUER-ACRYLIC.cns'


######################################################################## Read Image ########################################################################
    imagen = read_color_space.image_processing(img_path, IMG_WIDTH, IMG_HEIGHT)

    # Convertir la imagen RGB a CIELAB
    lab_image = color.rgb2lab(imagen)

    # Crear una matriz para almacenar los valores LAB
    matriz_lab = []

    # Crear un diccionario para agrupar píxeles con el mismo color en LAB
    color_groups = {}

    # Obtener los valores de L*, a*, y b* de cada píxel en la zona dental
    for y in range(lab_image.shape[0]):
        for x in range(lab_image.shape[1]):
            if lab_image[y, x, 0] > 0:  # Verificar si el píxel está en la zona dental
                lab_values = (lab_image[y, x, 0], lab_image[y, x, 1], lab_image[y, x, 2])
                matriz_lab.append(lab_values)

                # Agrupar píxeles con el mismo color en un diccionario
                color_key = tuple(np.round(lab_values, 2))
                if color_key not in color_groups:
                    color_groups[color_key] = []
                color_groups[color_key].append((y, x))

    # Convertir el diccionario de grupos a una lista
    color_groups_list = list(color_groups.values())



######################################################################## Read color space ########################################################################
    try:
        color_data = read_color_space.read_cns_file(color_space_path)
        # Display the extracted data
        print(color_data)
    except ValueError as e:
        print(f"Error al procesar {color_space_path}: {e}")

    # Extraer solo los valores RGB de la lista de diccionarios
    colors_rgb = np.array([list(entry.values()) for entry in color_data['representative_values']], dtype=np.uint8)

    # Normalizar los valores RGB al rango [0, 1]
    colors_rgb_normalized = colors_rgb / 255.0

    # Convertir de RGB a LAB
    colors_lab = color.rgb2lab(colors_rgb_normalized)



######################################################################## Voronoi ########################################################################
    # Negativos adicionales para evitar unbounded
    num_parts = 3
    prototypes_neg = VoronoiFuzzyColor.divide_lab_space(num_parts)

    # Suponiendo que tienes una instancia de ReferenceDomain llamada "lab_reference_domain"
    lab_reference_domain = ReferenceDomain.default_voronoi_reference_domain()


    # Pre-cálculo de Voronoi, core y soporte para cada color
    voronoi_values = []
    core_values = []
    support_values = []

    for center_index in range(len(colors_lab)):
        voronoi_volume = VoronoiFuzzyColor.create_voronoi_volumen(colors_lab, center_index, prototypes_neg)
        scaling_factor = 0.5
        core_volume, support_volume = VoronoiFuzzyColor.create_kernel_support(colors_lab, center_index, voronoi_volume, scaling_factor)

        voronoi_values.append(voronoi_volume)
        core_values.append(core_volume)
        support_values.append(support_volume)

    function = Spline05Function1D()


######################################################################## Membership Value ########################################################################
    # Recorrer grupos de píxeles con el mismo color en LAB
    new_image = np.zeros_like(imagen)
    for color_group in color_groups_list:
        # Obtener el valor LAB del primer píxel en el grupo
        lab_pixel = matriz_lab[color_group[0][0] * lab_image.shape[1] + color_group[0][1]]
        lab_pixel = Point(lab_pixel[0], lab_pixel[1], lab_pixel[2])

        # Encontrar el color con el mayor porcentaje de membresía en el grupo
        porcentaje_max_membresia = 0.0
        color_max_membresia = None

        for i, center_index in enumerate(range(len(colors_lab))):
            voronoi_volume = voronoi_values[i]
            core_volume = core_values[i]
            support_volume = support_values[i]

            membership_value = VoronoiFuzzyColor.get_membership_value(lab_pixel, lab_reference_domain, core_volume, voronoi_volume, support_volume, function)

            if membership_value >= 0.98:
                color_max_membresia = colors_rgb[i]
                break

            if membership_value > porcentaje_max_membresia:
                color_max_membresia = colors_rgb[i]
                porcentaje_max_membresia = membership_value

        # Asignar el color con el mayor porcentaje de membresía a todos los píxeles en el grupo
        for y, x in color_group:
            new_image[y, x] = color_max_membresia

    new_image = new_image / 255.0

    new_image = np.nan_to_num(new_image)

######################################################################## Results ########################################################################
    # Mostrar la imagen original
    plt.subplot(1, 2, 1)
    plt.imshow(imagen)
    plt.title('Imagen Original')

    # Mostrar la imagen coloreada
    plt.subplot(1, 2, 2)
    plt.imshow(new_image)
    plt.title('Imagen Coloreada')

    plt.savefig('.\\results\\imagen_coloreada.png')

    plt.show()
    cv2.waitKey(0)

if __name__ == "__main__":
    main()
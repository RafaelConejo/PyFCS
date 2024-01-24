from PIL import Image
import numpy as np
from skimage import color, io
import testing
import cv2
from geometry.Point import Point
import matplotlib.pyplot as plt

IMG_WIDTH = 64
IMG_HEIGHT = 64

def image_preproceso(img_path):
    # Abre la imagen
    imagen = cv2.imread(img_path)
    imagen = cv2.resize(imagen, (IMG_WIDTH, IMG_HEIGHT))
    
    # Convierte la imagen a formato RGB
    imagen = cv2.cvtColor(imagen, cv2.COLOR_BGR2RGB)
    
    # Normaliza la imagen
    imagen = imagen.astype(np.float32) / 255.0
    
    return imagen

# Ruta de la imagen
img_path = ".\\imagen_test\\banana.png"

# Aplica la función de preprocesamiento a la imagen
imagen = image_preproceso(img_path)

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

# Definir la matriz de valores RGB
colors_rgb = np.array([
    [254.0, 181.0, 186.0],   # Pink
    [200.0, 1.0, 25.0],      # Red
    [243.0, 132.0, 1.0],     # Orange
    [138.0, 40.0, 27.0],     # Brown
    [243.0, 195.0, 1.0],     # Yellow
    [102.0, 93.0, 30.0],     # Olive
    [141.0, 182.0, 1.0],     # Yellow-Green
    [1.0, 98.0, 45.0],       # Green
    [1.0, 103.0, 194.0],     # Blue
    [154.0, 78.0, 174.0],    # Purple
    [252.0, 252.0, 249.0],   # White
    [135.0, 134.0, 134.0],   # Gray
    [7.0, 7.0, 7.0]          # Black
], dtype=np.uint8)

# Normalizar los valores RGB al rango [0, 1]
colors_rgb_normalized = colors_rgb / 255.0

# Convertir de RGB a LAB
colors_lab = color.rgb2lab(colors_rgb_normalized)

# Negativos adicionales para evitar unbounded
num_parts = 3
prototypes_neg = testing.divide_lab_space(num_parts)

# Suponiendo que tienes una instancia de ReferenceDomain llamada "lab_reference_domain"
lab_reference_domain = testing.ReferenceDomain.default_voronoi_reference_domain()

# Crear una matriz para almacenar los colores finales
matriz_colores_finales = np.zeros_like(matriz_lab)
new_image = np.zeros_like(imagen)

# Recorrer grupos de píxeles con el mismo color en LAB
for color_group in color_groups_list:
    # Obtener el valor LAB del primer píxel en el grupo
    lab_pixel = matriz_lab[color_group[0][0] * lab_image.shape[1] + color_group[0][1]]
    lab_pixel = Point(lab_pixel[0], lab_pixel[1], lab_pixel[2])

    # Inicializar variables para el color y el porcentaje de membresía máximo
    color_max_membresia = None
    porcentaje_max_membresia = 0.0

    # Calcular la membresía para cada color
    for i, center_index in enumerate(range(len(colors_lab))):
        voronoi_volume = testing.create_voronoi_volumen(colors_lab, center_index, prototypes_neg)
        scaling_factor = 0.5
        core_volume, support_volume = testing.create_kernel_support(colors_lab, center_index, voronoi_volume, scaling_factor)

        # Suponiendo que tienes una instancia de la clase Spline05Function1D llamada "some_function"
        some_function = testing.Spline05Function1D()

        # Calcular el valor de pertenencia con el punto original
        membership_value = testing.get_membership_value(lab_pixel, lab_reference_domain, core_volume, voronoi_volume, support_volume, some_function)

        # Actualizar el color y el porcentaje máximo si encontramos una membresía más alta
        if membership_value > 0.9:
            color_max_membresia = colors_rgb[i]
            break

        if membership_value > porcentaje_max_membresia:
            color_max_membresia = colors_rgb[i]
            porcentaje_max_membresia = membership_value

    # Asignar el color con el mayor porcentaje de membresía a todos los píxeles en el grupo
    for y, x in color_group:
        new_image[y, x] = color_max_membresia

new_image = new_image / 255.0

# Mostrar la imagen original
plt.subplot(1, 2, 1)
plt.imshow(imagen)
plt.title('Imagen Original')

# Mostrar la imagen coloreada
plt.subplot(1, 2, 2)
plt.imshow(new_image)
plt.title('Imagen Coloreada')

plt.show()
cv2.waitKey(0)



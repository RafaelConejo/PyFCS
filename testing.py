import numpy as np
import math
import matplotlib.pyplot as plt
from scipy.spatial import Voronoi, voronoi_plot_2d
from skimage import color, io

from geometry.Plane import Plane
from geometry.Point import Point
from geometry.GeometryTools import GeometryTools
from geometry.Face import Face
from geometry.ReferenceDomain import ReferenceDomain
from geometry.Volume import Volume
from fuzzy.membershipfunction.Spline05Function1D import Spline05Function1D



# # Definir la matriz de valores RGB
# colors_rgb = np.array([
#     [254.0, 181.0, 186.0],   # Pink
#     [200.0, 1.0, 25.0],      # Red
#     [243.0, 132.0, 1.0],     # Orange
#     [138.0, 40.0, 27.0],     # Brown
#     [243.0, 195.0, 1.0],     # Yellow
#     [102.0, 93.0, 30.0],     # Olive
#     [141.0, 182.0, 1.0],     # Yellow-Green
#     [1.0, 98.0, 45.0],       # Green
#     [1.0, 103.0, 194.0],     # Blue
#     [154.0, 78.0, 174.0],    # Purple
#     [252.0, 252.0, 249.0],   # White
#     [135.0, 134.0, 134.0],   # Gray
#     [7.0, 7.0, 7.0]          # Black
# ], dtype=np.uint8)

# # Normalizar los valores RGB al rango [0, 1]
# colors_rgb_normalized = colors_rgb / 255.0

# # Convertir de RGB a LAB
# colors_lab = color.rgb2lab(colors_rgb_normalized)


# # Negativos adicionales para evitar unbounded
# num_parts = 3
# prototypes_neg = divide_lab_space(num_parts)


# # Suponiendo que tienes una instancia de ReferenceDomain llamada "lab_reference_domain"
# lab_reference_domain = ReferenceDomain.default_voronoi_reference_domain()

# # Suponiendo que tienes un punto de prueba en LAB, debes reemplazarlo con el punto real que deseas probar
# lab_point = Point(80.55352847, 27.16606465,  8.08171757)  

# # Imprimir el punto LAB original
# print("Punto LAB original:", lab_point)


# for i in range(len(colors_rgb)):
#     center_index = i # Índice del centro positivo
#     voronoi_volume = create_voronoi_volumen(colors_lab, center_index, prototypes_neg)

#     scaling_factor = 0.5
#     core_volume, support_volume = create_kernel_support(colors_lab, center_index, voronoi_volume, scaling_factor)


#     if i == 0:
#         # Crear el diagrama de Voronoi 2D utilizando voronoi_plot_2d
#         vor = Voronoi(colors_lab[:, :2])
#         voronoi_plot_2d(vor)
#         plt.plot(colors_lab[center_index, 0], colors_lab[center_index, 1], 'ro')  # Marcar el centro positivo en rojo
#         plt.plot(lab_point.get_x(), lab_point.get_y(), 'bx', markersize=10)  # Marcar lab_point con una X en azul
#         plt.title('Diagrama de Voronoi 2D')
#         plt.xlabel('Coordenada X')
#         plt.ylabel('Coordenada Y')
#         plt.show()



#     # Suponiendo que tienes una instancia de la clase Spline05Function1D llamada "some_function"
#     some_function = Spline05Function1D()

#     # Calcular el valor de pertenencia con el punto original
#     membership_value = get_membership_value(lab_point, lab_reference_domain, core_volume, voronoi_volume, support_volume, some_function)
#     print("Membership Value con centro " + str(i) + ":", membership_value)




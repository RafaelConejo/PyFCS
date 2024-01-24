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





def get_membership_value(o, reference_domain, core_volume, voronoi_volume, support_volume, func):
    # Assuming you have a method to transform o if it's not a Point
    if not isinstance(o, Point):
        o = reference_domain.transform(Point(o.x, o.y, o.z))  # Asegúrate de tener la referencia correcta para la transformación

    xyz = o

    if support_volume.is_inside(xyz) and not support_volume.is_in_face(xyz):
        if core_volume.is_inside(xyz):
            return 1
        else:
            dist_cube = float('inf')
            p_cube = GeometryTools.intersection_with_volume(reference_domain.get_volume(), voronoi_volume.get_representative(), xyz)
            if p_cube is not None:
                dist_cube = GeometryTools.euclidean_distance(voronoi_volume.get_representative(), p_cube)
            else:
                print("No intersection with cube")

            # param 'a' -> intersection with kernel volume
            dist_face = float('inf')
            p_face = GeometryTools.intersection_with_volume(core_volume, core_volume.get_representative(), xyz)
            if p_face is not None:
                dist_face = GeometryTools.euclidean_distance(core_volume.get_representative(), p_face)
            else:
                dist_face = dist_cube

            param_a = dist_face

            # param 'b' -> intersection with voronoi volume
            dist_face = float('inf')
            p_face = GeometryTools.intersection_with_volume(voronoi_volume, voronoi_volume.get_representative(), xyz)
            if p_face is not None:
                dist_face = GeometryTools.euclidean_distance(voronoi_volume.get_representative(), p_face)
            else:
                dist_face = dist_cube

            param_b = dist_face

            # param 'c' -> intersection with support volume
            dist_face = float('inf')
            p_face = GeometryTools.intersection_with_volume(support_volume, support_volume.get_representative(), xyz)
            if p_face is not None:
                dist_face = GeometryTools.euclidean_distance(support_volume.get_representative(), p_face)
            else:
                dist_face = dist_cube

            param_c = dist_face

            func.setParam([param_a, param_b, param_c])
            value = func.getValue(GeometryTools.euclidean_distance(voronoi_volume.get_representative(), xyz))

            if value == 0 or value == 1:
                print("Error membership value with point [{},{},{}] in support. Value must be (0,1)".format(xyz.x, xyz.y, xyz.z))

            return value

    else:
        return 0














def add_face_to_kernel_support(voronoi, face, lam):
    dist = GeometryTools.distance_point_plane(face.plane, voronoi.get_representative()) * (1 - lam)
    # Creamos caras para kernel y support
    par = GeometryTools.parallel_planes(face.plane, dist)
    f1 = Face(par[0], face.is_infinity)
    f2 = Face(par[1], face.is_infinity)

    if face.vertices:
        # Creamos nuevos vértices para cada cara del kernel y support
        for v in face.vertices:
            f1.add_vertex(GeometryTools.intersection_plane_rect(f1.plane, voronoi.get_representative(), v))
            f2.add_vertex(GeometryTools.intersection_plane_rect(f2.plane, voronoi.get_representative(), v))

    # Añadimos cara correspondiente a kernel y support
    if GeometryTools.distance_point_plane(f1.plane, voronoi.get_representative()) < GeometryTools.distance_point_plane(f2.plane, voronoi.get_representative()):
        voronoi.kernel.add_face(f1)
        voronoi.support.add_face(f2)
    else:
        voronoi.kernel.add_face(f2)
        voronoi.support.add_face(f1)


# Función para convertir un VoronoiFace en un Volume
def face_to_volume(voronoi_faces, representative):
    converted_faces = []

    for voronoi_face in voronoi_faces:
        # Convierte la representación de la cara a la clase Plane
        plane = Plane(voronoi_face.p.A, voronoi_face.p.B, voronoi_face.p.C, voronoi_face.p.D)
        
        # Crea una nueva instancia de Face con la información de la cara del Voronoi
        converted_face = Face(p=plane, infinity=voronoi_face.is_infinity)
        
        # Añade los vértices convertidos a la nueva instancia de Face
        converted_face.vertex = [Point(v[0], v[1], v[2]) for v in voronoi_face.get_array_vertex()]

        # Añade la nueva instancia de Face a la lista
        converted_faces.append(converted_face)

    # Crea el volumen con el representante y las caras convertidas del Voronoi
    voronoi_volume = Volume(representative=representative, faces=converted_faces)

    return voronoi_volume

def create_voronoi_volumen(centroids, center_index, prototypes_neg):
    positive_centroid = centroids[center_index]
    negative_centroids = np.delete(centroids, center_index, axis=0)
    negative = np.vstack((negative_centroids, prototypes_neg))
    points = np.vstack((positive_centroid, negative))
    voronoi = Voronoi(points)

    voronoi_faces = []
    for region in voronoi.regions:
        if -1 not in region and len(region) > 0:
            voronoi_face = Face(p=None)
            vertices = voronoi.vertices[region]

            voronoi_face.vertex = vertices.tolist()
            voronoi_faces.append(voronoi_face)

    for voronoi_face in voronoi_faces:
        # Get face vertices
        voronoi_vertices = np.array(voronoi_face.vertex)

        # Calculate normals to planes
        voronoi_normal = np.cross(voronoi_vertices[1] - voronoi_vertices[0], voronoi_vertices[2] - voronoi_vertices[0])

        # Normalize normals
        voronoi_normal /= np.linalg.norm(voronoi_normal)

        # Calculate D term of the plane equation
        voronoi_D_term = -np.dot(voronoi_normal, voronoi_vertices[0])

        # Assign instances of Plane to faces
        voronoi_face.p = Plane(voronoi_normal[0], voronoi_normal[1], voronoi_normal[2], voronoi_D_term)

    representative = Point(*positive_centroid)
    voronoi_volume = face_to_volume(voronoi_faces, representative)

    return voronoi_volume


def add_face_to_kernel_support(face, representative, lambda_value, kernel, support):
    dist = GeometryTools.distance_point_plane(face.p, representative) * (1 - lambda_value)
    
    # Creamos planos paralelos para kernel y soporte
    parallel_planes = GeometryTools.parallel_planes(face.p, dist)
    face_kernel = Face(p=parallel_planes[0], infinity=face.infinity)
    face_support = Face(p=parallel_planes[1], infinity=face.infinity)

    if face.get_array_vertex() is not None:
        # Creamos nuevos vértices para cada cara del kernel y soporte
        for v in face.get_array_vertex():
            vertex_kernel = GeometryTools.intersection_plane_rect(face_kernel.p, representative, v)
            vertex_soporte = GeometryTools.intersection_plane_rect(face_support.p, representative, v)
            face_kernel.add_vertex(vertex_kernel)
            face_support.add_vertex(vertex_soporte)

    # Añadimos la cara correspondiente a kernel y soporte
    if GeometryTools.distance_point_plane(face_kernel.p, representative) < GeometryTools.distance_point_plane(face_support.p, representative):
        kernel.add_face(face_kernel)
        support.add_face(face_support)
    else:
        kernel.add_face(face_support)
        support.add_face(face_kernel)


def create_kernel_support(centroids, center_index, volume_fc, lambda_value):
    positive_centroid = centroids[center_index]
    kernel_volume = Volume(Point(*positive_centroid))
    soporte_volume = Volume(Point(*positive_centroid))

    for face in volume_fc.get_faces():

            add_face_to_kernel_support(face, Point(*positive_centroid), lambda_value, kernel_volume, soporte_volume)

    return kernel_volume, soporte_volume














def divide_lab_space(num_parts):
    # Rangos típicos de LAB
    l_range = [0, 100]
    a_range = [-128, 128]
    b_range = [-128, 128]

    # Dividir cada componente en partes iguales
    l_intervals = np.linspace(l_range[0], l_range[1], num_parts + 1)
    a_intervals = np.linspace(a_range[0], a_range[1], num_parts + 1)
    b_intervals = np.linspace(b_range[0], b_range[1], num_parts + 1)

    # Generar prototipo negativo para cada celda
    prototypes = []
    for l_start, l_end in zip(l_intervals[:-1], l_intervals[1:]):
        for a_start, a_end in zip(a_intervals[:-1], a_intervals[1:]):
            for b_start, b_end in zip(b_intervals[:-1], b_intervals[1:]):
                # Cada combinación de intervalos define una celda
                prototype = [(l, a, b) for l in [l_start, l_end] for a in [a_start, a_end] for b in [b_start, b_end]]

                # Calcular punto central
                centro_prototipo = (
                    sum(x for x, _, _ in prototype) / len(prototype),
                    sum(y for _, y, _ in prototype) / len(prototype),
                    sum(z for _, _, z in prototype) / len(prototype)
                )

                prototypes.append(centro_prototipo)

    return prototypes












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
prototypes_neg = divide_lab_space(num_parts)


# Suponiendo que tienes una instancia de ReferenceDomain llamada "lab_reference_domain"
lab_reference_domain = ReferenceDomain.default_voronoi_reference_domain()

# Suponiendo que tienes un punto de prueba en LAB, debes reemplazarlo con el punto real que deseas probar
lab_point = Point(80.78950801,  3.18038656, 52.19191259)  

# Imprimir el punto LAB original
print("Punto LAB original:", lab_point)

# Suponiendo que tienes una instancia de Volume llamada "volumeFC"
center_index = 4 # Índice del centro positivo
voronoi_volume = create_voronoi_volumen(colors_lab, center_index, prototypes_neg)

scaling_factor = 0.5
core_volume, support_volume = create_kernel_support(colors_lab, center_index, voronoi_volume, scaling_factor)



# Crear el diagrama de Voronoi 2D utilizando voronoi_plot_2d
vor = Voronoi(colors_lab[:, :2])
voronoi_plot_2d(vor)
plt.plot(colors_lab[center_index, 0], colors_lab[center_index, 1], 'ro')  # Marcar el centro positivo en rojo
plt.plot(lab_point.get_x(), lab_point.get_y(), 'bx', markersize=10)  # Marcar lab_point con una X en azul
plt.title('Diagrama de Voronoi 2D')
plt.xlabel('Coordenada X')
plt.ylabel('Coordenada Y')
plt.show()



# Suponiendo que tienes una instancia de la clase Spline05Function1D llamada "some_function"
some_function = Spline05Function1D()

# Calcular el valor de pertenencia con el punto original
membership_value = get_membership_value(lab_point, lab_reference_domain, core_volume, voronoi_volume, support_volume, some_function)
print("Membership Value con el punto original:", membership_value)




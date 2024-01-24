import numpy as np
import math
from scipy.spatial import Voronoi

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
            # !!!!!!!!!!!!!!!!!!!!!!!!!!!! REVISAR DESPUES, CHEKEA EL CUBO
            # p_cube = GeometryTools.intersection_with_volume(reference_domain.get_volume(), core_volume.get_representative(), xyz)
            # if p_cube is not None:
            #     dist_cube = GeometryTools.euclidean_distance(core_volume.get_representative(), p_cube)
            # else:
            #     print("No intersection with cube")

            # param 'a' -> intersection with kernel volume
            dist_face = float('inf')
            p_face = GeometryTools.intersection_with_volume(voronoi_volume, voronoi_volume.get_representative(), xyz)
            if p_face is not None:
                dist_face = GeometryTools.euclidean_distance(voronoi_volume.get_representative(), p_face)
            else:
                dist_face = dist_cube

            param_a = dist_face

            # param 'b' -> intersection with voronoi volume
            dist_face = float('inf')
            p_face = GeometryTools.intersection_with_volume(core_volume.get_representative(), core_volume.get_representative(), xyz)
            if p_face is not None:
                dist_face = GeometryTools.euclidean_distance(core_volume.get_representative(), p_face)
            else:
                dist_face = dist_cube

            param_b = dist_face

            # param 'c' -> intersection with support volume
            dist_face = float('inf')
            p_face = GeometryTools.intersection_with_volume(support_volume.get_representative(), support_volume.get_representative(), xyz)
            if p_face is not None:
                dist_face = GeometryTools.euclidean_distance(support_volume.get_representative(), p_face)
            else:
                dist_face = dist_cube

            param_c = dist_face

            func.setParam([param_a, param_b, param_c])
            value = func.getValue(GeometryTools.euclidean_distance(core_volume.get_representative(), xyz))

            if value == 0 or value == 1:
                print("Error membership value with point [{},{},{}] in support. Value must be (0,1)".format(xyz.x, xyz.y, xyz.z))

            return value

    else:
        return 0







def create_core_support_faces(voronoi, scaling_factor_core=0.5, scaling_factor_support=1.5):
    core_faces = []
    voronoi_faces = []
    support_faces = []

    for region in voronoi.regions:
        if -1 not in region and len(region) > 0:
            core_face = Face(p=None)  # No Plane object, will be updated later
            voronoi_face = Face(p=None)
            support_face = Face(p=None)

            vertices = voronoi.vertices[region]

            # Scale vertices to define core, voronoi, and support
            core_vertices = vertices * scaling_factor_core
            voronoi_vertices = vertices
            support_vertices = vertices * scaling_factor_support

            core_face.vertex = core_vertices.tolist()
            core_faces.append(core_face)

            voronoi_face.vertex = voronoi_vertices.tolist()
            voronoi_faces.append(voronoi_face)

            support_face.vertex = support_vertices.tolist()
            support_faces.append(support_face)

    # Now update faces with the actual plane of the face
    for core_face, voronoi_face, support_face in zip(core_faces, voronoi_faces, support_faces):
        # Get face vertices
        core_vertices = np.array(core_face.vertex)
        voronoi_vertices = np.array(voronoi_face.vertex)
        support_vertices = np.array(support_face.vertex)

        # Calculate normals to planes
        core_normal = np.cross(core_vertices[1] - core_vertices[0], core_vertices[2] - core_vertices[0])
        voronoi_normal = np.cross(voronoi_vertices[1] - voronoi_vertices[0], voronoi_vertices[2] - voronoi_vertices[0])
        support_normal = np.cross(support_vertices[1] - support_vertices[0], support_vertices[2] - support_vertices[0])

        # Normalize normals
        core_normal /= np.linalg.norm(core_normal)
        voronoi_normal /= np.linalg.norm(voronoi_normal)
        support_normal /= np.linalg.norm(support_normal)

        # Calculate D term of the plane equation
        core_D_term = -np.dot(core_normal, core_vertices[0])
        voronoi_D_term = -np.dot(voronoi_normal, voronoi_vertices[0])
        support_D_term = -np.dot(support_normal, support_vertices[0])

        # Assign instances of Plane to faces
        core_face.p = Plane(core_normal[0], core_normal[1], core_normal[2], core_D_term)
        voronoi_face.p = Plane(voronoi_normal[0], voronoi_normal[1], voronoi_normal[2], voronoi_D_term)
        support_face.p = Plane(support_normal[0], support_normal[1], support_normal[2], support_D_term)

    return core_faces, voronoi_faces, support_faces


def create_core_support_for_voronoi(centroids, center_index, scaling_factor_core=0.5, scaling_factor_support=1.5):
    positive_centroid = centroids[center_index]
    negative_centroids = np.delete(centroids, center_index, axis=0)
    points = np.vstack((positive_centroid, negative_centroids))
    voronoi = Voronoi(points)

    core_faces, voronoi_faces, support_faces = create_core_support_faces(voronoi, scaling_factor_core, scaling_factor_support)

    # Now update faces with the actual plane of the face
    for i, (core_face, voronoi_face, support_face) in enumerate(zip(core_faces, voronoi_faces, support_faces)):
        core_face.p = Plane(core_face.p.A, core_face.p.B, core_face.p.C, core_face.p.D)
        voronoi_face.p = Plane(voronoi_face.p.A, voronoi_face.p.B, voronoi_face.p.C, voronoi_face.p.D)
        support_face.p = Plane(support_face.p.A, support_face.p.B, support_face.p.C, support_face.p.D)

    # Create instances of the Volume class to represent volumes
    positive_centroid_point = Point(*positive_centroid)
    core_volume = Volume(representative=positive_centroid_point, faces=core_faces)
    voronoi_volume = Volume(representative=positive_centroid_point, faces=voronoi_faces)
    support_volume = Volume(representative=positive_centroid_point, faces=support_faces)

    return core_volume, voronoi_volume, support_volume

def distance_point_plane(plane, p):
    return abs(p[0] * plane.get_A() + p[1] * plane.get_B() + p[2] * plane.get_C() + plane.get_D()) / math.sqrt(plane.get_A()**2 + plane.get_B()**2 + plane.get_C()**2)


def calculate_membership_percentage(point, core_face, voronoi_face, support_face):
    # Calcular la distancia del punto a las caras del core, voronoi y support
    distance_to_core = distance_point_plane(core_face.get_plane(), point)
    distance_to_voronoi = distance_point_plane(voronoi_face.get_plane(), point)
    distance_to_support = distance_point_plane(support_face.get_plane(), point)

    # Calcular el porcentaje de pertenencia utilizando la función Spline05Function1D
    total_distance = distance_to_core + distance_to_voronoi + distance_to_support
    if total_distance == 0:
        membership_percentage = 1.0  # El punto coincide exactamente con el centro
    else:
        spline_function = Spline05Function1D(0, distance_to_core, total_distance)
        membership_percentage = spline_function.getValue(distance_to_core)

    return membership_percentage

# Definir los centroides en 3 dimensiones
centroids = np.array([
    [77.4, -0.7, 15.2],
    [75.0, 0.7, 19.0],
    [73.0, 1.1, 21.8],
    [69.6, 2.3, 23.6],
    [64.8, 2.5, 23.0],
    [76.1, -1.5, 12.7],
    [73.9, -1.1, 17.3],
    [71.4, 1.0, 24.7],
    [69.2, 1.1, 24.9],
    [71.5, -0.3, 15.1],
    [68.4, 0.2, 17.2],
    [65.5, 1.3, 19.0],
    [64.5, 1.7, 22.1],
    [69.3, 0.4, 13.3],
    [68.8, 0.9, 18.0],
    [68.6, -0.1, 21.9]
])



# Suponiendo que tienes una instancia de ReferenceDomain llamada "lab_reference_domain"
lab_reference_domain = ReferenceDomain.default_voronoi_reference_domain()

# Suponiendo que tienes un punto de prueba en LAB, debes reemplazarlo con el punto real que deseas probar
lab_point = Point(7.4, -0.7, 15.2)  # Ejemplo: L=50, A=0, B=0

# Imprimir el punto LAB original
print("Punto LAB original:", lab_point)

# Suponiendo que tienes una instancia de Volume llamada "volumeFC"
center_index = 1 # Índice del centro positivo
core_volume, voronoi_volume, support_volume = create_core_support_for_voronoi(centroids, center_index)

# Suponiendo que tienes una instancia de la clase Spline05Function1D llamada "some_function"
some_function = Spline05Function1D()

# Calcular el valor de pertenencia con el punto original
membership_value = get_membership_value(lab_point, lab_reference_domain, core_volume, voronoi_volume, support_volume, some_function)
print("Membership Value con el punto original:", membership_value)


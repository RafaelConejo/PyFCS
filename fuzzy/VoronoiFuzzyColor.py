from scipy.spatial import Voronoi, voronoi_plot_2d
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

### my libraries ###
from geometry.Plane import Plane
from geometry.Point import Point
from geometry.GeometryTools import GeometryTools
from geometry.Face import Face
from geometry.Volume import Volume
from geometry.Vector import Vector


class VoronoiFuzzyColor:
    def __init__(self):
        pass

    @staticmethod
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

                # param 'a' -> intersection with core volume
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






    # Función para convertir un VoronoiFace en un Volume

    def face_to_volume(faces, representative):
        volume = Volume(representative)

        for face in faces:
            volume.add_face(face)

        return volume


    def visualize_voronoi(volume):
        if volume is not None:
            # Extract information from the Volume object
            faces = volume.get_faces()

            # Extract vertices from faces
            all_vertices = []
            for face in faces:
                vertices = face.get_array_vertex()
                if vertices is not None and len(vertices) >= 3:
                    all_vertices.extend(vertices)


            # Visualization code
            fig = plt.figure(figsize=(8, 8))
            ax = fig.add_subplot(111, projection='3d')

            # Plot Voronoi diagram
            for face in faces:
                vertices = face.get_array_vertex()
                if vertices is not None and len(vertices) >= 3:
                    polygon = np.array(vertices)
                    ax.plot(polygon[:, 0], polygon[:, 1], polygon[:, 2], 'gray', linewidth=2, alpha=0.6)

            # Plot points used to generate Voronoi diagram
            ax.scatter(volume.representative.x, volume.representative.y, volume.representative.z, c='blue', marker='*', s=200, label='Positive Centroid')

            ax.set_title('Voronoi Diagram')
            ax.set_xlabel('X-axis')
            ax.set_ylabel('Y-axis')
            ax.set_zlabel('Z-axis')
            ax.legend()
            plt.show()
        else:
            print("No valid Voronoi regions found.")


    @staticmethod
    def create_voronoi_volumen(centroids, center_index, prototypes_neg, test):
        # if test == 'si':
        #     positive_centroid = centroids[center_index]
        #     negative = np.delete(centroids, center_index, axis=0)
        #     negative_centroids = np.vstack((negative, prototypes_neg))
        # elif test == 'no':
        #     positive_centroid = centroids[center_index]
        #     negative_centroids = np.delete(centroids, center_index, axis=0)


        positive_centroid = centroids[center_index]
        negative_centroids = np.delete(centroids, center_index, axis=0)

        points = np.vstack((positive_centroid, negative_centroids))
        voronoi = Voronoi(points, qhull_options='Fi Fo p Fv')

        regions, vertices = voronoi.regions, voronoi.vertices
        valid_regions = regions # [region for region in regions if -1 not in region]

        faces = []

        if valid_regions:
            # Iterate through the valid_regions and create Face instances
            for region_index in range(len(valid_regions)):
                region = valid_regions[region_index]
                # Filter out -1 indices (infinitos)
                region_vertices = [vertices[i] for i in region if i != -1]

                # Check if the region has enough vertices to create a face
                if len(region_vertices) >= 3:
                    # Assume the normal vector of the plane points outward
                    normal_vector = np.cross(region_vertices[1] - region_vertices[0], region_vertices[2] - region_vertices[0])

                    # Create a Plane instance using the first three vertices of the region
                    plane = Plane.from_point_and_normal(Point(region_vertices[0][0], region_vertices[0][1], region_vertices[0][2]), Vector.from_array(normal_vector))

                    # Create a Face instance using the vertices and the created plane
                    face = Face(p=plane)
                    face.set_array_vertex(region_vertices)

                    faces.append(face)

            representative = Point(*positive_centroid)
            voronoi_volume = VoronoiFuzzyColor.face_to_volume(faces, representative)





            # voronoi_proj = Voronoi(points[:, :2], qhull_options='Fi Fo p Fv')

            # # Visualization code
            # plt.figure(figsize=(8, 8))

            # # Plot Voronoi diagram
            # voronoi_plot_2d(voronoi_proj, show_vertices=False, line_colors='gray', line_width=2, line_alpha=0.6, point_size=10)

            # # Plot points used to generate Voronoi diagram
            # plt.scatter(points[:, 0], points[:, 1], c='red', marker='o', label='Centroids')

            # # Highlight positive centroid
            # plt.scatter(positive_centroid[0], positive_centroid[1], c='blue', marker='*', s=200, label='Positive Centroid')

            # plt.title('Voronoi Diagram')
            # plt.xlabel('X-axis')
            # plt.ylabel('Y-axis')
            # plt.legend()
            # plt.show()





            #VoronoiFuzzyColor.visualize_voronoi(voronoi_volume)
            plt.close('all')


            return voronoi_volume
        else:
            # Handle the case where there are no valid Voronoi regions
            print("No valid Voronoi regions found.")
            return None  # Or you can return an empty volume or handl
        




    @staticmethod
    def add_face_to_core_support(face, representative, lambda_value, core, support):
        # Calculate the distance between the face and the representative point
        dist = GeometryTools.distance_point_plane(face.p, representative) * (1 - lambda_value)
        
        # Create parallel planes for core and support
        parallel_planes = GeometryTools.parallel_planes(face.p, dist)
        face_core = Face(p=parallel_planes[0], infinity=face.infinity)
        face_support = Face(p=parallel_planes[1], infinity=face.infinity)

        if face.get_array_vertex() is not None:
            # Create new vertices for each face of the core and support
            for v in face.get_array_vertex():
                vertex_core = GeometryTools.intersection_plane_rect(face_core.p, representative, Point(v[0], v[1], v[2]))
                vertex_support = GeometryTools.intersection_plane_rect(face_support.p, representative, Point(v[0], v[1], v[2]))
                face_core.add_vertex(vertex_core)
                face_support.add_vertex(vertex_support)

        # Add the corresponding face to core and support
        if GeometryTools.distance_point_plane(face_core.p, representative) < GeometryTools.distance_point_plane(face_support.p, representative):
            core.add_face(face_core)
            support.add_face(face_support)
        else:
            core.add_face(face_support)
            support.add_face(face_core)


    @staticmethod
    def create_core_support(centroids, center_index, volume_fc, lambda_value):
        positive_centroid = centroids[center_index]
        core_volume = Volume(Point(*positive_centroid))
        soporte_volume = Volume(Point(*positive_centroid))

        for face in volume_fc.get_faces():

                VoronoiFuzzyColor.add_face_to_core_support(face, Point(*positive_centroid), lambda_value, core_volume, soporte_volume)

        return core_volume, soporte_volume


    @staticmethod
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






    # @staticmethod
    # def face_to_volume(voronoi_faces, representative):
    #     converted_faces = []

    #     for voronoi_face in voronoi_faces:
    #         # Convierte la representación de la cara a la clase Plane
    #         plane = Plane(voronoi_face.p.A, voronoi_face.p.B, voronoi_face.p.C, voronoi_face.p.D)
            
    #         # Crea una nueva instancia de Face con la información de la cara del Voronoi
    #         converted_face = Face(p=plane, infinity=voronoi_face.is_infinity)
            
    #         # Añade los vértices convertidos a la nueva instancia de Face
    #         converted_face.vertex = [Point(v[0], v[1], v[2]) for v in voronoi_face.get_array_vertex()]

    #         # Añade la nueva instancia de Face a la lista
    #         converted_faces.append(converted_face)

    #     # Crea el volumen con el representante y las caras convertidas del Voronoi
    #     voronoi_volume = Volume(representative=representative, faces=converted_faces)

    #     return voronoi_volume


    # @staticmethod
    # def create_voronoi_volumen(centroids, center_index, prototypes_neg, test):
    #     if test == 'si':
    #         positive_centroid = centroids[center_index]
    #         negative = np.delete(centroids, center_index, axis=0)
    #         negative_centroids = np.vstack((negative, prototypes_neg))
    #     elif test == 'no':
    #         positive_centroid = centroids[center_index]
    #         negative_centroids = np.delete(centroids, center_index, axis=0)

    #     points = np.vstack((positive_centroid, negative_centroids))
    #     voronoi = Voronoi(points, qhull_options='Fi Fo p Fv')

    #     voronoi_faces = []
    #     for region in voronoi.regions:
    #         # if -1 not in region and len(region) > 0:
    #         if len(region) > 0:
    #             voronoi_face = Face(p=None)
    #             vertices = voronoi.vertices[region]

    #             voronoi_face.vertex = vertices.tolist()
    #             voronoi_faces.append(voronoi_face)

    #     for voronoi_face in voronoi_faces:
    #         # Get face vertices
    #         voronoi_vertices = np.array(voronoi_face.vertex)

    #         # Calculate normals to planes
    #         voronoi_normal = np.cross(voronoi_vertices[1] - voronoi_vertices[0], voronoi_vertices[2] - voronoi_vertices[0])

    #         # Normalize normals
    #         voronoi_normal /= np.linalg.norm(voronoi_normal)

    #         # Calculate D term of the plane equation
    #         voronoi_D_term = -np.dot(voronoi_normal, voronoi_vertices[0])

    #         # Assign instances of Plane to faces
    #         voronoi_face.p = Plane(voronoi_normal[0], voronoi_normal[1], voronoi_normal[2], voronoi_D_term)

    #     representative = Point(*positive_centroid)
    #     voronoi_volume = VoronoiFuzzyColor.face_to_volume(voronoi_faces, representative)

    #     return voronoi_volume
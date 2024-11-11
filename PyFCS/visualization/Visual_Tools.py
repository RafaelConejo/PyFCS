import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from matplotlib.patches import Polygon

from scipy.spatial import ConvexHull
from itertools import product
import matplotlib.colors as mcolors

class Visual_tools:

    def calculate_intersection_with_plane(point, normal, D):
        # Calcula la intersección entre la línea desde el punto y el plano
        # La línea se extiende en la dirección del normal
        line_direction = normal / np.linalg.norm(normal)  # Normaliza el vector normal
        t = - (D + np.dot(normal, point)) / np.dot(normal, line_direction)
        intersection_point = point + t * line_direction
        return intersection_point

    def create_plane_mesh(A, B, C, D, x_range, y_range):
        x_min, x_max = x_range
        y_min, y_max = y_range

        # Crear una malla de valores X y Y
        x_vals = np.linspace(x_min, x_max, 10)
        y_vals = np.linspace(y_min, y_max, 10)
        X, Y = np.meshgrid(x_vals, y_vals)

        # Calcular Z usando la ecuación del plano
        Z = -(A * X + B * Y + D) / C  # Resolviendo para Z

        return X, Y, Z

    def plot_plane(ax, X, Y, Z, color='cyan', alpha=0.5):
        ax.plot_surface(X, Y, Z, color=color, alpha=alpha, edgecolor='none')

    def calculate_plane_equation(P1, P2, P3):
        # Vectores del plano
        v1 = P2 - P1
        v2 = P3 - P1

        # Producto cruzado para obtener el vector normal
        normal = np.cross(v1, v2)

        A, B, C = normal
        D = -np.dot(normal, P1)  # Calculando D
        
        return A, B, C, D

    @staticmethod
    def get_intersection_with_cube(A, B, C, D, volume_limits):
        intersections = set() 

        # Definir los límites del cubo
        x_min, x_max = volume_limits.comp1
        y_min, y_max = volume_limits.comp2
        z_min, z_max = volume_limits.comp3

        # Función auxiliar para resolver la ecuación del plano
        def solve_plane_for_x(y, z):
            if A != 0:
                return -(B * y + C * z + D) / A
            return None

        def solve_plane_for_y(x, z):
            if B != 0:
                return -(A * x + C * z + D) / B
            return None

        def solve_plane_for_z(x, y):
            if C != 0:
                return -(A * x + B * y + D) / C
            return None

        # Intersecciones con las caras del cubo
        for x, y, z in product([x_min, x_max], [y_min, y_max], [z_min, z_max]):
            # Evaluar intersecciones para las tres variables
            x_plane = solve_plane_for_x(y, z)
            if x_plane is not None and x_min <= x_plane <= x_max:
                intersections.add((x_plane, y, z))

            y_plane = solve_plane_for_y(x, z)
            if y_plane is not None and y_min <= y_plane <= y_max:
                intersections.add((x, y_plane, z))

            z_plane = solve_plane_for_z(x, y)
            if z_plane is not None and z_min <= z_plane <= z_max:
                intersections.add((x, y, z_plane))

        return np.array(list(intersections))

    @staticmethod
    def order_points_by_angle(points):
        """
        Ordena los puntos alrededor del primer punto en la lista por el ángulo en el plano XY.
        
        Args:
            points (np.ndarray): Arreglo de puntos en el espacio 3D.
        
        Returns:
            np.ndarray: Puntos ordenados por ángulo.
        """
        # Tomar el primer punto como el centro
        center = points[0]
        
        # Calcular ángulos respecto al punto central
        angles = np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0])
        
        # Ordenar puntos según los ángulos
        sorted_indices = np.argsort(angles)
        return points[sorted_indices]

    @staticmethod
    def create_voronoi_volume_shape(prototype, volume_limits, alpha=0.5):
        """
        Create a 3D shape representing the Voronoi volume around the positive point.
        
        Args:
            prototype: An instance containing positive and negative points, with Voronoi volume data.
            volume_limits: Limits for the volume in each axis direction.
            alpha (float): Transparency level of the Voronoi volume (0 to 1).
        """
        fig = plt.figure()
        ax = fig.add_subplot(111, projection='3d')
        
        # Puntos de los positivos y negativos
        negatives = np.array(prototype.negatives)
        positives = np.array(prototype.positive)

        # Filtrar puntos negativos dentro de los límites
        negatives_filtered = negatives[
            (negatives[:, 0] >= volume_limits.comp1[0]) & (negatives[:, 0] <= volume_limits.comp1[1]) &
            (negatives[:, 1] >= volume_limits.comp2[0]) & (negatives[:, 1] <= volume_limits.comp2[1]) &
            (negatives[:, 2] >= volume_limits.comp3[0]) & (negatives[:, 2] <= volume_limits.comp3[1])
        ]
        
        # Graficar el punto positivo si está dentro de los límites
        if (positives[0] >= volume_limits.comp1[0] and positives[0] <= volume_limits.comp1[1] and
            positives[1] >= volume_limits.comp2[0] and positives[1] <= volume_limits.comp2[1] and
            positives[2] >= volume_limits.comp3[0] and positives[2] <= volume_limits.comp3[1]):
            ax.scatter(positives[0], positives[1], positives[2], color='green', marker='^', s=100, label='Positive')
        
        # Graficar puntos negativos
        ax.scatter(negatives_filtered[:, 0], negatives_filtered[:, 1], negatives_filtered[:, 2], 
                color='red', marker='o', label='Negatives')

        # Extraer vértices para el volumen de Voronoi
        voronoi_faces = []
        faces = prototype.voronoi_volume.faces  # Cada cara contiene sus vértices

        for face in faces:
            vertices = np.array(face.vertex)
            
            if face.infinity:
                # Procesar caras infinitas
                A, B, C, D = face.p.getA(), face.p.getB(), face.p.getC(), face.p.getD()
                intersection_points = Visual_tools.get_intersection_with_cube(A, B, C, D, volume_limits)
                
                if intersection_points.size > 0:
                    all_vertices = np.vstack((vertices, intersection_points))
                    all_vertices = np.unique(all_vertices, axis=0)

                    if len(intersection_points) >= 3:
                        P1, P2, P3 = intersection_points[:3]
                        voronoi_faces.append(np.array([P1, P2, P3]))
                    else:
                        voronoi_faces.append(intersection_points)

            else:
                # Simplemente añadir los vértices de la cara finita, ordenándolos
                ordered_vertices = Visual_tools.order_points_by_angle(vertices)
                voronoi_faces.append(ordered_vertices)

        # Crear el volumen envolvente usando Poly3DCollection con transparencia
        for face_vertices in voronoi_faces:
            if len(face_vertices) >= 3:
                # Calcular la ecuación del plano y graficar
                A, B, C, D = Visual_tools.calculate_plane_equation(face_vertices[0], face_vertices[1], face_vertices[2])
                x_range = (volume_limits.comp1[0], volume_limits.comp1[1])
                y_range = (volume_limits.comp2[0], volume_limits.comp2[1])
                X, Y, Z = Visual_tools.create_plane_mesh(A, B, C, D, x_range, y_range)
                Visual_tools.plot_plane(ax, X, Y, Z, color='cyan', alpha=alpha)

        # Etiquetas de los ejes
        ax.set_xlabel('L*')
        ax.set_ylabel('a*')
        ax.set_zlabel('b*')

        # Ajustar límites de los ejes según el volumen
        ax.set_xlim(volume_limits.comp1[0], volume_limits.comp1[1])
        ax.set_ylim(volume_limits.comp2[0], volume_limits.comp2[1])
        ax.set_zlim(volume_limits.comp3[0], volume_limits.comp3[1])

        # Mostrar la leyenda y el gráfico
        ax.legend()
        plt.show()

























    # @staticmethod
    # def plot_prototype(prototype, volume_limits):
    #     fig = plt.figure()
    #     ax = fig.add_subplot(111, projection='3d')

    #     # 1. Puntos negativos
    #     negatives = np.array(prototype.negatives)
    #     positives = np.array(prototype.positive)

    #     # Filtrar puntos negativos dentro de los límites
    #     negatives_filtered = negatives[
    #         (negatives[:, 0] >= volume_limits.comp1[0]) & (negatives[:, 0] <= volume_limits.comp1[1]) &
    #         (negatives[:, 1] >= volume_limits.comp2[0]) & (negatives[:, 1] <= volume_limits.comp2[1]) &
    #         (negatives[:, 2] >= volume_limits.comp3[0]) & (negatives[:, 2] <= volume_limits.comp3[1])
    #     ]
        
    #     # Filtrar punto positivo dentro de los límites
    #     if (positives[0] >= volume_limits.comp1[0] and positives[0] <= volume_limits.comp1[1] and
    #         positives[1] >= volume_limits.comp2[0] and positives[1] <= volume_limits.comp2[1] and
    #         positives[2] >= volume_limits.comp3[0] and positives[2] <= volume_limits.comp3[1]):
    #         ax.scatter(positives[0], positives[1], positives[2], color='green', marker='^', s=100, label='Positive')

    #     # Graficar puntos negativos
    #     ax.scatter(negatives_filtered[:, 0], negatives_filtered[:, 1], negatives_filtered[:, 2], color='red', marker='o', label='Negatives')

    #     # 3. Volumen de Voronoi (Caras)
    #     faces = prototype.voronoi_volume.faces  # Cada cara contiene sus vértices

    #     for face in faces:
    #         vertices = np.array(face.vertex)

    #         # Filtrar caras que están fuera del volumen
    #         if face.infinity:  # Si la cara es infinita
    #             # Coeficientes del plano (A, B, C, D)
    #             A = face.p.getA()
    #             B = face.p.getB()
    #             C = face.p.getC()
    #             D = face.p.getD()

    #             # Calcular intersecciones de la cara infinita con el cubo
    #             intersection_points = Visual_tools.get_intersection_with_cube(A, B, C, D, volume_limits)

    #             all_vertices = np.vstack((vertices, intersection_points))
    #             unique_intersections = np.unique(all_vertices, axis=0)

    #             # Ordenar los puntos
    #             ordered_intersections = Visual_tools.order_points_by_angle(unique_intersections)

    #             if len(all_vertices) > 3:  # Asegurarse de que hay suficientes puntos
    #                 poly3d = Poly3DCollection([ordered_intersections], facecolors='red', edgecolors='yellow', linewidths=1, alpha=0.5)
    #                 ax.add_collection3d(poly3d)

    #         else:
    #             # Caras finitas normales
    #             poly3d = Poly3DCollection([vertices], facecolors='cyan', edgecolors='blue', linewidths=1, alpha=0.5)
    #             ax.add_collection3d(poly3d)

    #     # Etiquetas de los ejes
    #     ax.set_xlabel('L*')
    #     ax.set_ylabel('a*')
    #     ax.set_zlabel('b*')

    #     # Ajustar límites de los ejes según el volumen
    #     ax.set_xlim(volume_limits.comp1[0], volume_limits.comp1[1])
    #     ax.set_ylim(volume_limits.comp2[0], volume_limits.comp2[1])
    #     ax.set_zlim(volume_limits.comp3[0], volume_limits.comp3[1])

    #     # Mostrar la leyenda
    #     ax.legend()

    #     # Mostrar el gráfico
    #     plt.show()




    # @staticmethod
    # def get_intersection_with_cube(A, B, C, D, volume_limits):
    #     intersections = []

    #     # Definir los límites del cubo
    #     x_min, x_max = volume_limits.comp1
    #     y_min, y_max = volume_limits.comp2
    #     z_min, z_max = volume_limits.comp3

    #     # Función auxiliar para resolver la ecuación del plano
    #     def solve_plane_for_x(y, z):
    #         if A != 0:
    #             return -(B * y + C * z + D) / A
    #         return None

    #     def solve_plane_for_y(x, z):
    #         if B != 0:
    #             return -(A * x + C * z + D) / B
    #         return None

    #     def solve_plane_for_z(x, y):
    #         if C != 0:
    #             return -(A * x + B * y + D) / C
    #         return None

    #     # Intersecciones con las caras Z = constante (XY planes)
    #     for z in [z_min, z_max]:
    #         for y in [y_min, y_max]:
    #             x = solve_plane_for_x(y, z)
    #             if x is not None and x_min <= x <= x_max:
    #                 intersections.append((x, y, z))

    #     # Intersecciones con las caras Y = constante (XZ planes)
    #     for y in [y_min, y_max]:
    #         for z in [z_min, z_max]:
    #             x = solve_plane_for_x(y, z)
    #             if x is not None and x_min <= x <= x_max:
    #                 intersections.append((x, y, z))

    #     # Intersecciones con las caras X = constante (YZ planes)
    #     for x in [x_min, x_max]:
    #         for z in [z_min, z_max]:
    #             y = solve_plane_for_y(x, z)
    #             if y is not None and y_min <= y <= y_max:
    #                 intersections.append((x, y, z))

    #     return np.array(intersections)



    # @staticmethod
    # def order_points_by_angle(points):
    #     # Calcular el centroide
    #     centroid = np.mean(points, axis=0)

    #     # Calcular los ángulos
    #     angles = np.arctan2(points[:, 1] - centroid[1], points[:, 0] - centroid[0])

    #     # Ordenar los puntos por el ángulo
    #     ordered_indices = np.argsort(angles)
    #     return points[ordered_indices]

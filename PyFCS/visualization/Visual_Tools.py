import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from matplotlib.patches import Polygon

from scipy.spatial import ConvexHull
from itertools import product
import matplotlib.colors as mcolors

### my libraries ###
from PyFCS import Prototype

class Visual_tools:
    @staticmethod
    def plot_prototype(prototype, volume_limits):
        fig = plt.figure()
        ax = fig.add_subplot(111, projection='3d')

        # 1. Puntos negativos
        negatives = np.array(prototype.negatives)
        positives = np.array(prototype.positive)

        # Filtrar puntos negativos dentro de los límites
        negatives_filtered = negatives[
            (negatives[:, 0] >= volume_limits.comp1[0]) & (negatives[:, 0] <= volume_limits.comp1[1]) &
            (negatives[:, 1] >= volume_limits.comp2[0]) & (negatives[:, 1] <= volume_limits.comp2[1]) &
            (negatives[:, 2] >= volume_limits.comp3[0]) & (negatives[:, 2] <= volume_limits.comp3[1])
        ]
        
        # Filtrar punto positivo dentro de los límites
        if (positives[0] >= volume_limits.comp1[0] and positives[0] <= volume_limits.comp1[1] and
            positives[1] >= volume_limits.comp2[0] and positives[1] <= volume_limits.comp2[1] and
            positives[2] >= volume_limits.comp3[0] and positives[2] <= volume_limits.comp3[1]):
            ax.scatter(positives[0], positives[1], positives[2], color='green', marker='^', s=100, label='Positive')

        # Graficar puntos negativos, aquellos no falsos
        false_negatives = Prototype.get_falseNegatives()
        negatives_filtered_no_false = [
            point for point in negatives_filtered
            if not any(np.array_equal(point, fn) for fn in false_negatives)
        ]
        negatives_filtered = np.array(negatives_filtered_no_false)

        ax.scatter(negatives_filtered[:, 0], negatives_filtered[:, 1], negatives_filtered[:, 2], color='red', marker='o', label='Negatives')

        # 3. Volumen de Voronoi (Caras)
        faces = prototype.voronoi_volume.faces  # Cada cara contiene sus vértices

        for face in faces:
            vertices = np.array(face.vertex)

            # Filtrar caras que están fuera del volumen
            if face.infinity:  # Si la cara es infinita
                # Coeficientes del plano (A, B, C, D)
                A = face.p.getA()
                B = face.p.getB()
                C = face.p.getC()
                D = face.p.getD()

                # Calcular intersecciones de la cara infinita con el cubo
                intersection_points = Visual_tools.get_intersection_with_cube(A, B, C, D, volume_limits)

                all_vertices = np.vstack((vertices, intersection_points))
                unique_intersections = np.unique(all_vertices, axis=0)

                # Ordenar los puntos
                ordered_intersections = Visual_tools.order_points_by_angle(unique_intersections)

                if len(all_vertices) > 3:  # Asegurarse de que hay suficientes puntos
                    poly3d = Poly3DCollection([ordered_intersections], facecolors='red', edgecolors='yellow', linewidths=1, alpha=0.5)
                    ax.add_collection3d(poly3d)

            else:
                # Caras finitas normales
                poly3d = Poly3DCollection([vertices], facecolors='cyan', edgecolors='blue', linewidths=1, alpha=0.5)
                ax.add_collection3d(poly3d)

        # Etiquetas de los ejes
        ax.set_xlabel('L*')
        ax.set_ylabel('a*')
        ax.set_zlabel('b*')

        # Ajustar límites de los ejes según el volumen
        ax.set_xlim(volume_limits.comp1[0], volume_limits.comp1[1])
        ax.set_ylim(volume_limits.comp2[0], volume_limits.comp2[1])
        ax.set_zlim(volume_limits.comp3[0], volume_limits.comp3[1])

        # Mostrar la leyenda
        ax.legend()

        # Mostrar el gráfico
        plt.show()




    @staticmethod
    def get_intersection_with_cube(A, B, C, D, volume_limits):
        intersections = []

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

        # Intersecciones con las caras Z = constante (XY planes)
        for z in [z_min, z_max]:
            for y in [y_min, y_max]:
                x = solve_plane_for_x(y, z)
                if x is not None and x_min <= x <= x_max:
                    intersections.append((x, y, z))

        # Intersecciones con las caras Y = constante (XZ planes)
        for y in [y_min, y_max]:
            for z in [z_min, z_max]:
                x = solve_plane_for_x(y, z)
                if x is not None and x_min <= x <= x_max:
                    intersections.append((x, y, z))

        # Intersecciones con las caras X = constante (YZ planes)
        for x in [x_min, x_max]:
            for z in [z_min, z_max]:
                y = solve_plane_for_y(x, z)
                if y is not None and y_min <= y <= y_max:
                    intersections.append((x, y, z))

        return np.array(intersections)



    @staticmethod
    def order_points_by_angle(points):
        # Calcular el centroide
        centroid = np.mean(points, axis=0)

        # Calcular los ángulos
        angles = np.arctan2(points[:, 1] - centroid[1], points[:, 0] - centroid[0])

        # Ordenar los puntos por el ángulo
        ordered_indices = np.argsort(angles)
        return points[ordered_indices]

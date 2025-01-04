import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from matplotlib import cm

### my libraries ###
from PyFCS import Prototype

class Visual_tools:
    @staticmethod
    def plot_all_centroids(filename, color_data, hex_color):
        """Dibuja los puntos RGB en 3D en el Canvas izquierdo usando Matplotlib y devuelve la figura."""
        fig = plt.Figure(figsize=(5, 4), dpi=100)
        ax = fig.add_subplot(111, projection='3d')

        num_elements = len(color_data)

        # Extraer los valores LAB de color_data
        lab_values = [color_value['positive_prototype'] for color_name, color_value in color_data.items()]
        lab_array = np.array(lab_values)

        # Separar los valores de L, A, y B para graficar en 3D
        L_values = lab_array[:, 0]  # Primer componente (L)
        A_values = lab_array[:, 1]  # Segundo componente (A)
        B_values = lab_array[:, 2]  # Tercer componente (B)

        # Graficar los puntos RGB en 3D con colores normalizados
        ax.scatter(L_values, A_values, B_values, c=hex_color, marker='o')

        # Títulos y etiquetas
        ax.set_title(f'{filename} - {num_elements} colors', fontsize=7)
        ax.set_xlabel("L*")
        ax.set_ylabel("a*")
        ax.set_zlabel("b*")

        return fig  # Devolver la figura



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
                vertices_clipped_ordered = Visual_tools.clip_face_to_volume(vertices, volume_limits)
                poly3d = Poly3DCollection([vertices_clipped_ordered], facecolors='cyan', edgecolors='blue', linewidths=1, alpha=0.5)
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
    def plot_all_prototypes(prototypes, volume_limits):
        """
        Dibuja los volúmenes de múltiples prototipos, cada uno en un color diferente.
        """
        fig = plt.figure()
        ax = fig.add_subplot(111, projection='3d')

        # Colores predefinidos para los volúmenes
        colormap = cm.get_cmap('viridis', len(prototypes))
        
        for idx, prototype in enumerate(prototypes):
            color = colormap(idx)  # Color único para cada prototipo

            # 1. Puntos negativos
            negatives = np.array(prototype.negatives)

            # Filtrar puntos negativos dentro de los límites
            negatives_filtered = negatives[
                (negatives[:, 0] >= volume_limits.comp1[0]) & (negatives[:, 0] <= volume_limits.comp1[1]) &
                (negatives[:, 1] >= volume_limits.comp2[0]) & (negatives[:, 1] <= volume_limits.comp2[1]) &
                (negatives[:, 2] >= volume_limits.comp3[0]) & (negatives[:, 2] <= volume_limits.comp3[1])
            ]

            # Graficar puntos negativos, aquellos no falsos
            false_negatives = Prototype.get_falseNegatives()
            negatives_filtered_no_false = [
                point for point in negatives_filtered
                if not any(np.array_equal(point, fn) for fn in false_negatives)
            ]
            negatives_filtered = np.array(negatives_filtered_no_false)

            # Graficar puntos negativos
            ax.scatter(negatives_filtered[:, 0], negatives_filtered[:, 1], negatives_filtered[:, 2],
                       color=color, marker='o', label=f'Negatives {idx+1}')

            # 3. Volumen de Voronoi (Caras)
            faces = prototype.voronoi_volume.faces  # Cada cara contiene sus vértices

            for face in faces:
                vertices = np.array(face.vertex)

                # Si la cara es infinita, calcular intersecciones con el volumen
                if face.infinity:
                    A, B, C, D = face.p.getA(), face.p.getB(), face.p.getC(), face.p.getD()
                    # intersection_points = Visual_tools.get_intersection_with_cube(A, B, C, D, volume_limits)
                    # all_vertices = np.vstack((vertices, intersection_points))
                    # unique_intersections = np.unique(all_vertices, axis=0)
                    # ordered_intersections = Visual_tools.order_points_by_angle(unique_intersections)

                    # if len(ordered_intersections) >= 3:
                    #     poly3d = Poly3DCollection([ordered_intersections], facecolors=color, edgecolors='black',
                    #                                linewidths=1, alpha=0.5)
                    #     ax.add_collection3d(poly3d)
                else:
                    # Recortar las caras finitas al volumen
                    vertices_clipped = Visual_tools.clip_face_to_volume(vertices, volume_limits)
                    if len(vertices_clipped) >= 3:
                        poly3d = Poly3DCollection([vertices_clipped], facecolors=color, edgecolors='black',
                                                   linewidths=1, alpha=0.5)
                        ax.add_collection3d(poly3d)

        # Etiquetas de los ejes
        ax.set_xlabel('L*')
        ax.set_ylabel('a*')
        ax.set_zlabel('b*')

        # Ajustar límites de los ejes según el volumen
        ax.set_xlim(volume_limits.comp1[0], volume_limits.comp1[1])
        ax.set_ylim(volume_limits.comp2[0], volume_limits.comp2[1])
        ax.set_zlim(volume_limits.comp3[0], volume_limits.comp3[1])

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
    

    @staticmethod
    def clip_face_to_volume(vertices, volume_limits):
        """
        Ajusta una cara a los límites del volumen especificado.
        """
        # Lista para almacenar puntos ajustados
        adjusted_vertices = []

        # Limitar coordenadas a los valores del volumen
        for vertex in vertices:
            adjusted_vertex = np.array([
                np.clip(vertex[0], volume_limits.comp1[0], volume_limits.comp1[1]),
                np.clip(vertex[1], volume_limits.comp2[0], volume_limits.comp2[1]),
                np.clip(vertex[2], volume_limits.comp3[0], volume_limits.comp3[1]),
            ])
            adjusted_vertices.append(adjusted_vertex)

        return np.array(adjusted_vertices)


    

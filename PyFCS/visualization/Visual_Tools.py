import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from matplotlib import cm

### my libraries ###
from PyFCS.geometry.Point import Point
from PyFCS import Prototype

class Visual_tools:
    @staticmethod
    def plot_all_centroids(filename, color_data, hex_color):
        """Dibuja los puntos RGB en 3D en el Canvas izquierdo usando Matplotlib y devuelve la figura."""
        if len(color_data) != 0:
            fig = Figure(figsize=(6, 5), dpi=120)
            ax = fig.add_subplot(111, projection='3d')

            # Extraer los valores LAB de los datos
            lab_values = [color_value['positive_prototype'] for color_value in color_data.values()]
            lab_array = np.array(lab_values)

            # Separar los componentes LAB
            L_values = lab_array[:, 0]  # L* (luminosidad)
            A_values = lab_array[:, 1]  # a* (componente de verde a rojo)
            B_values = lab_array[:, 2]  # b* (componente de azul a amarillo)

            # Obtener los colores hexadecimales en el mismo orden que los datos
            colors = []
            for lab in lab_values:
                # Inicializar un color por defecto
                color_found = '#000000'  # Color negro por defecto
                
                # Buscar si el lab está en hex_color
                for hex_key, lab_value in hex_color.items():
                    if np.array_equal(lab, lab_value):  # Comparar usando np.array_equal
                        color_found = hex_key  # Obtener el color hexadecimal correspondiente
                        break  # Salir del bucle si se encuentra el color

                colors.append(color_found)  # Agregar el color encontrado a la lista

            # Graficar los puntos en 3D
            scatter = ax.scatter(
                A_values, B_values, L_values,
                c=colors, marker='o', s=50, edgecolor='k', alpha=0.8
            )

            # Configuración de títulos y etiquetas
            ax.set_title(f'{filename} - {len(color_data)} colors', fontsize=10, fontweight='bold', pad=15)
            ax.set_xlabel("a* (Green-Red)", fontsize=9, labelpad=10)
            ax.set_ylabel("b* (Blue-Yellow)", fontsize=9, labelpad=10)
            ax.set_zlabel("L* (Luminosity)", fontsize=9, labelpad=10)

            # Ajuste de los límites de los ejes
            ax.set_xlim(-128, 127)   # a* 
            ax.set_ylim(-128, 127)   # b* 
            ax.set_zlim(0, 100)      # L* 

            # Estilización adicional de la gráfica
            ax.grid(True, linestyle='--', linewidth=0.5, alpha=0.7)
            ax.tick_params(axis='both', which='major', labelsize=8)

            return fig  # Devolver la figura



    @staticmethod
    def plot_all_prototypes(prototypes, volume_limits, hex_color):
        """
        Dibuja los volúmenes de múltiples prototipos, con el eje L* siempre en el eje Z.
        """
        if len(prototypes) != 0:
            fig = Figure(figsize=(8, 6), dpi=120)
            ax = fig.add_subplot(111, projection='3d')

            # Filtra todos los puntos
            all_points = np.vstack((np.array(prototypes[0].positive), np.array(prototypes[0].negatives)))
            false_negatives = Prototype.get_falseNegatives()
            negatives_filtered_no_false = [
                point for point in all_points
                if not any(np.array_equal(point, fn) for fn in false_negatives)
            ]
            all_points = np.array(negatives_filtered_no_false)

            # Limita los puntos al rango de volumen especificado
            all_points = all_points[
                (all_points[:, 0] >= volume_limits.comp1[0]) & (all_points[:, 0] <= volume_limits.comp1[1]) &
                (all_points[:, 1] >= volume_limits.comp2[0]) & (all_points[:, 1] <= volume_limits.comp2[1]) &
                (all_points[:, 2] >= volume_limits.comp3[0]) & (all_points[:, 2] <= volume_limits.comp3[1])
            ]

            # Dibuja los puntos individuales con L* en el eje Z
            for i in range(all_points.shape[0]):
                point = all_points[i]
                color = '#000000'  # Default a negro si no se encuentra coincidencia
                for hex_color_key, lab_value in hex_color.items():
                    if np.array_equal(point, lab_value):  # Compara el punto con el valor LAB
                        color = hex_color_key
                        break

                ax.scatter(
                    all_points[i, 1], all_points[i, 2], all_points[i, 0],  # Cambiar orden: a*, b*, L*
                    color=color, marker='o', s=30, label=f'Points {i + 1}', edgecolor='k', alpha=0.8
                )

            # Dibuja los volúmenes de Voronoi con L* en el eje Z
            for idx, prototype in enumerate(prototypes):
                # Usa el color basado en `hex_color` si es posible
                color = '#000000'  # Color por defecto
                for hex_color_key, lab_value in hex_color.items():
                    if np.array_equal(prototype.positive, lab_value):  # Asocia prototipos con colores
                        color = hex_color_key
                        break

                # Agregar las caras del volumen de Voronoi
                faces = prototype.voronoi_volume.faces  # Cada cara contiene sus vértices
                for face in faces:
                    vertices = np.array(face.vertex)
                    if face.infinity:
                        continue  # Ignorar caras infinitas
                    else:
                        vertices_clipped = Visual_tools.clip_face_to_volume(vertices, volume_limits)
                        if len(vertices_clipped) >= 3:  # Al menos 3 vértices para formar una cara
                            # Cambiar orden de los vértices: a*, b*, L*
                            vertices_clipped = vertices_clipped[:, [1, 2, 0]]
                            poly3d = Poly3DCollection(
                                [vertices_clipped], facecolors=color, edgecolors='black',
                                linewidths=1, alpha=0.5
                            )
                            ax.add_collection3d(poly3d)

            # Configuración de los ejes (ajustados para que L* esté en el eje Z)
            ax.set_xlabel('a* (Green-Red)', fontsize=10, labelpad=10)
            ax.set_ylabel('b* (Blue-Yellow)', fontsize=10, labelpad=10)
            ax.set_zlabel('L* (Luminosity)', fontsize=10, labelpad=10)

            # Ajustar los límites de los ejes según los límites del volumen
            ax.set_xlim(volume_limits.comp2[0], volume_limits.comp2[1])  # a*
            ax.set_ylim(volume_limits.comp3[0], volume_limits.comp3[1])  # b*
            ax.set_zlim(volume_limits.comp1[0], volume_limits.comp1[1])  # L*

            # Estilización adicional
            ax.grid(True, linestyle='--', linewidth=0.5, alpha=0.7)

            return fig




    @staticmethod
    def plot_all_prototypes_filtered_points(prototypes, volume_limits, hex_color, threshold_points):
        """
        Dibuja los volúmenes de múltiples prototipos y marca con una 'X' los puntos dentro del volumen que cumplen el umbral.

        Parámetros:
        - prototypes: Lista de prototipos (cada uno con su volumen de Voronoi).
        - volume_limits: Límites del volumen para restringir la visualización.
        - hex_color: Diccionario con colores hex para los prototipos.
        - threshold_points: Lista de puntos (L*, a*, b*) que cumplen con el umbral, para ser marcados con "X".
        """
        if len(prototypes) != 0:
            fig = plt.figure(figsize=(8, 6), dpi=120)
            ax = fig.add_subplot(111, projection='3d')

            # Filtra todos los puntos
            all_points = np.vstack((np.array(prototypes[0].positive), np.array(prototypes[0].negatives)))
            false_negatives = Prototype.get_falseNegatives()
            negatives_filtered_no_false = [
                point for point in all_points
                if not any(np.array_equal(point, fn) for fn in false_negatives)
            ]
            all_points = np.array(negatives_filtered_no_false)

            # Limita los puntos al rango de volumen especificado
            all_points = all_points[
                (all_points[:, 0] >= volume_limits.comp1[0]) & (all_points[:, 0] <= volume_limits.comp1[1]) &
                (all_points[:, 1] >= volume_limits.comp2[0]) & (all_points[:, 1] <= volume_limits.comp2[1]) &
                (all_points[:, 2] >= volume_limits.comp3[0]) & (all_points[:, 2] <= volume_limits.comp3[1])
            ]

            # Dibuja los puntos individuales con L* en el eje Z
            for i in range(all_points.shape[0]):
                point = all_points[i]
                color = '#000000'  # Default a negro si no se encuentra coincidencia
                for hex_color_key, lab_value in hex_color.items():
                    if np.array_equal(point, lab_value):  # Compara el punto con el valor LAB
                        color = hex_color_key
                        break

                ax.scatter(
                    all_points[i, 1], all_points[i, 2], all_points[i, 0],  # Cambiar orden: a*, b*, L*
                    color=color, marker='o', s=30, edgecolor='k', alpha=0.8
                )

            # Dibuja los puntos dentro del volumen que cumplen el umbral con una "X"
            all_filtered_points = np.vstack([np.array(v) for v in threshold_points.values()])
            for point in all_filtered_points:
                ax.scatter(
                    point[1], point[2], point[0],  # Cambiar orden: a*, b*, L*
                    color='b', marker='x', s=20, linewidths=2, label='Threshold Points'
                )

            # Dibuja los volúmenes de Voronoi con L* en el eje Z
            for idx, prototype in enumerate(prototypes):
                color = '#000000'  # Color por defecto
                for hex_color_key, lab_value in hex_color.items():
                    if np.array_equal(prototype.positive, lab_value):
                        color = hex_color_key
                        break

                faces = prototype.voronoi_volume.faces  # Cada cara contiene sus vértices
                for face in faces:
                    vertices = np.array(face.vertex)
                    if face.infinity:
                        continue
                    else:
                        vertices_clipped = Visual_tools.clip_face_to_volume(vertices, volume_limits)
                        if len(vertices_clipped) >= 3:
                            vertices_clipped = vertices_clipped[:, [1, 2, 0]]
                            poly3d = Poly3DCollection(
                                [vertices_clipped], facecolors=color, edgecolors='black',
                                linewidths=1, alpha=0.5
                            )
                            ax.add_collection3d(poly3d)

            # Configuración de los ejes (ajustados para que L* esté en el eje Z)
            ax.set_xlabel('a* (Green-Red)', fontsize=10, labelpad=10)
            ax.set_ylabel('b* (Blue-Yellow)', fontsize=10, labelpad=10)
            ax.set_zlabel('L* (Luminosity)', fontsize=10, labelpad=10)

            # Ajustar los límites de los ejes según los límites del volumen
            ax.set_xlim(volume_limits.comp2[0], volume_limits.comp2[1])  # a*
            ax.set_ylim(volume_limits.comp3[0], volume_limits.comp3[1])  # b*
            ax.set_zlim(volume_limits.comp1[0], volume_limits.comp1[1])  # L*

            # Estilización adicional
            ax.grid(True, linestyle='--', linewidth=0.5, alpha=0.7)

            return fig















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
            if isinstance(vertex, Point):
                vertex = vertex.get_double_point()
    
            adjusted_vertex = np.array([
                np.clip(vertex[0], volume_limits.comp1[0], volume_limits.comp1[1]),
                np.clip(vertex[1], volume_limits.comp2[0], volume_limits.comp2[1]),
                np.clip(vertex[2], volume_limits.comp3[0], volume_limits.comp3[1]),
            ])
            adjusted_vertices.append(adjusted_vertex)

        return np.array(adjusted_vertices)


    

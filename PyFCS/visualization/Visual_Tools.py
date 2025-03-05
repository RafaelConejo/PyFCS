import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from matplotlib import cm
import plotly.graph_objects as go

### my libraries ###
from PyFCS.geometry.Point import Point
from PyFCS import Prototype

class Visual_tools:
    @staticmethod
    def plot_all_centroids(fig, color_data, hex_color):
        """Dibuja puntos RGB en 3D usando Plotly."""
        if not color_data:
            return
        
        lab_values = [v['positive_prototype'] for v in color_data.values()]
        lab_array = np.array(lab_values)
        A = lab_array[:, 1]  # a*
        B = lab_array[:, 2]  # b*
        L = lab_array[:, 0]  # L*
        
        colors = []
        for lab in lab_values:
            hex_key = next((k for k, v in hex_color.items() if np.array_equal(v, lab)), "#000000")
            colors.append(hex_key)
        
        scatter = go.Scatter3d(
            x=A, y=B, z=L,
            mode='markers',
            marker=dict(
                size=5,
                color=colors,
                opacity=0.8,
                line=dict(color='black', width=1)
            ),
            name="Centroides"
        )
        fig.add_trace(scatter)

    @staticmethod
    def triangulate_face(vertices):
        """Convierte una cara poligonal en triángulos (fan triangulation)."""
        triangles = []
        for i in range(1, len(vertices) - 1):
            triangles.append([vertices[0], vertices[i], vertices[i + 1]])
        return triangles
    
    @staticmethod
    def plot_all_prototypes(fig, prototypes, volume_limits, hex_color):
        """Dibuja volúmenes como mallas 3D en Plotly."""
        if not prototypes:
            return
        
        for prototype in prototypes:
            color = next((k for k, v in hex_color.items() if np.array_equal(prototype.positive, v)), "#000000")
            vertices = []
            faces = []
            
            for face in prototype.voronoi_volume.faces:
                if not face.infinity:
                    clipped = Visual_tools.clip_face_to_volume(np.array(face.vertex), volume_limits)
                    if len(clipped) >= 3:
                        clipped = clipped[:, [1, 2, 0]]  # Reordenar a a*, b*, L*
                        triangles = Visual_tools.triangulate_face(clipped)
                        for tri in triangles:
                            idx = len(vertices)
                            vertices.extend(tri)
                            faces.append([idx, idx + 1, idx + 2])
            
            if vertices:
                vertices = np.array(vertices)
                mesh = go.Mesh3d(
                    x=vertices[:, 0],
                    y=vertices[:, 1],
                    z=vertices[:, 2],
                    i=[f[0] for f in faces],
                    j=[f[1] for f in faces],
                    k=[f[2] for f in faces],
                    color=color,
                    opacity=0.5,
                    name="Prototipo"
                )
                fig.add_trace(mesh)

    @staticmethod
    def plot_combined_3D(filename, color_data, core, alpha, support, volume_limits, hex_color, selected_options):
        """Genera figura combinada con Plotly."""
        fig = go.Figure()
        
        options = {
            "Representative": (Visual_tools.plot_all_centroids, [fig, color_data, hex_color]),
            "0.5-cut": (Visual_tools.plot_all_prototypes, [fig, alpha, volume_limits, hex_color]),
            "Core": (Visual_tools.plot_all_prototypes, [fig, core, volume_limits, hex_color]),
            "Support": (Visual_tools.plot_all_prototypes, [fig, support, volume_limits, hex_color]),
        }
        
        for option in selected_options:
            if option in options:
                func, args = options[option]
                func(*args)
        
        axis_limits = {}
        if volume_limits:
            axis_limits = dict(
                xaxis=dict(range=volume_limits.comp2),
                yaxis=dict(range=volume_limits.comp3),
                zaxis=dict(range=volume_limits.comp1)
            )
        
        fig.update_layout(
            scene=dict(
                xaxis_title='a* (Green-Red)',
                yaxis_title='b* (Blue-Yellow)',
                zaxis_title='L* (Luminosity)',
                **axis_limits
            ),
            margin=dict(l=0, r=0, b=0, t=0)
        )
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


    

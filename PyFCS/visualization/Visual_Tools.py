import numpy as np
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import plotly.graph_objects as go

### my libraries ###
from PyFCS.geometry.Point import Point

class Visual_tools:
    @staticmethod
    def plot_more_combined_3D(filename, color_data, core, alpha, support, volume_limits, hex_color, selected_options, filtered_points=None):
        """Generates a 3D figure in Plotly by combining centroids and prototypes based on selected options."""
        fig = go.Figure()

        def triangulate_face(vertices):
            """Converts a polygonal face into triangles (fan triangulation)."""
            triangles = []
            for i in range(1, len(vertices) - 1):
                triangles.append([vertices[0], vertices[i], vertices[i + 1]])
            return triangles

        def plot_centroids():
            """Draws RGB points in 3D."""
            if not color_data:
                return
            
            lab_values = [v['positive_prototype'] for v in color_data.values()]
            lab_array = np.array(lab_values)
            A, B, L = lab_array[:, 1], lab_array[:, 2], lab_array[:, 0]

            colors = [next((k for k, v in hex_color.items() if np.array_equal(v, lab)), "#000000") for lab in lab_values]

            fig.add_trace(go.Scatter3d(
                x=A, y=B, z=L,
                mode='markers',
                marker=dict(size=5, color=colors, opacity=0.8, line=dict(color='black', width=1)),
                name="Centroids"
            ))

        def plot_prototypes(prototypes):
            """Draws volumes as 3D meshes."""
            if not prototypes:
                return
            
            for prototype in prototypes:
                color = next((k for k, v in hex_color.items() if np.array_equal(prototype.positive, v)), "#000000")
                vertices, faces = [], []

                for face in prototype.voronoi_volume.faces:
                    if not face.infinity:
                        clipped = Visual_tools.clip_face_to_volume(np.array(face.vertex), volume_limits)
                        if len(clipped) >= 3:
                            clipped = clipped[:, [1, 2, 0]]  # Reorder to a*, b*, L*
                            triangles = triangulate_face(clipped)
                            for tri in triangles:
                                idx = len(vertices)
                                vertices.extend(tri)
                                faces.append([idx, idx + 1, idx + 2])

                if vertices:
                    vertices = np.array(vertices)
                    fig.add_trace(go.Mesh3d(
                        x=vertices[:, 0], y=vertices[:, 1], z=vertices[:, 2],
                        i=[f[0] for f in faces], j=[f[1] for f in faces], k=[f[2] for f in faces],
                        color=color, opacity=0.5, name="Prototype"
                    ))
        
        def plot_filtered_points():
            """Draws filtered points as black markers."""
            if filtered_points:
                for proto_name, points in filtered_points.items():
                    if len(points) > 0:
                        points_array = np.array(points)
                        L_points, A_points, B_points = points_array[:, 0], points_array[:, 1], points_array[:, 2]

                        fig.add_trace(go.Scatter3d(
                            x=A_points, y=B_points, z=L_points,
                            mode='markers',
                            marker=dict(size=5, color='black', opacity=0.8, line=dict(color='black', width=1)),
                            name=f"Filtered Points: {proto_name}"
                        ))

        # Mapping of selected options to their corresponding functions
        options_map = {
            "Representative": plot_centroids,
            "0.5-cut": lambda: plot_prototypes(alpha),
            "Core": lambda: plot_prototypes(core),
            "Support": lambda: plot_prototypes(support),
        }

        for option in selected_options:
            if option in options_map:
                options_map[option]()

        # Plot the filtered points if they exist
        plot_filtered_points()

        # Axis settings and limits
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
            margin=dict(l=0, r=0, b=0, t=30),
            title=dict(text=f"{filename}", font=dict(size=10), x=0.5, y=0.95)
        )

        return fig



    @staticmethod
    def plot_combined_3D(filename, color_data, core, alpha, support, volume_limits, hex_color, selected_options, filtered_points=None):
        """Generates a single figure combining centroids and prototypes based on selected options."""
        fig = Figure(figsize=(8, 6), dpi=120)
        ax = fig.add_subplot(111, projection='3d')

        # Dictionary to map each option to its corresponding data
        data_map = {
            "Representative": color_data,
            "0.5-cut": alpha,
            "Core": core,
            "Support": support
        }

        # Loop through the selected options and plot corresponding data
        for option, data in data_map.items():
            if option in selected_options and data:
                if isinstance(data, dict):  # Color data (centroids)
                    lab_values = [v['positive_prototype'] for v in data.values()]
                    lab_array = np.array(lab_values)

                    # Extract L*, A*, B* values from the LAB color space
                    L_values, A_values, B_values = lab_array[:, 0], lab_array[:, 1], lab_array[:, 2]

                    # Assign colors to points based on their LAB values
                    colors = [
                        next((hex_key for hex_key, lab_val in hex_color.items() if np.array_equal(lab, lab_val)), "#000000")
                        for lab in lab_values
                    ]

                    # Scatter plot of the centroids in 3D
                    ax.scatter(A_values, B_values, L_values, c=colors, marker='o', s=30, edgecolor='k', alpha=0.8)

                elif isinstance(data, list):  # Prototypes (Voronoi volumes)
                    for prototype in data:
                        # Determine the color for each prototype based on its positive LAB value
                        color = next(
                            (hex_key for hex_key, lab_val in hex_color.items() if np.array_equal(prototype.positive, lab_val)),
                            "#000000"
                        )

                        # Clip the Voronoi faces to the volume limits and plot them
                        valid_faces = [
                            Visual_tools.clip_face_to_volume(np.array(face.vertex), volume_limits)
                            for face in prototype.voronoi_volume.faces if not face.infinity
                        ]
                        valid_faces = [f[:, [1, 2, 0]] for f in valid_faces if len(f) >= 3]

                        # If valid faces exist, add the prototype's 3D polyhedron to the plot
                        if valid_faces:
                            ax.add_collection3d(Poly3DCollection(valid_faces, facecolors=color, edgecolors='black', linewidths=1, alpha=0.5))



                if filtered_points is not None:
                    # Represent filtered points as a zone of intensity (scatter or density)
                    for idx, proto_name in enumerate(filtered_points):
                        # Get the points for the current volume
                        points = filtered_points[proto_name]

                        # Calculate the density of points within each volume (e.g., using a voxel grid)
                        if len(points) > 0:
                            # Split the points into A*, B*, and L* coordinates
                            points_array = np.array(points)
                            L_points, A_points, B_points = points_array[:, 0], points_array[:, 1], points_array[:, 2]

                            # Use a scatter plot to represent the intensity of points
                            # positive_color = np.array(prototype.positive)
                            # opposite_color = np.array([positive_color[0], -positive_color[1], -positive_color[2]])

                            ax.scatter(A_points, B_points, L_points, c='k', marker='o', s=10, alpha=0.8)

        # Configure the axes
        ax.set_xlabel('a* (Green-Red)', fontsize=10, labelpad=10)
        ax.set_ylabel('b* (Blue-Yellow)', fontsize=10, labelpad=10)
        ax.set_zlabel('L* (Luminosity)', fontsize=10, labelpad=10)

        # Apply volume limits to the plot if specified
        if volume_limits:
            ax.set_xlim(volume_limits.comp2[0], volume_limits.comp2[1])  # a*
            ax.set_ylim(volume_limits.comp3[0], volume_limits.comp3[1])  # b*
            ax.set_zlim(volume_limits.comp1[0], volume_limits.comp1[1])  # L*

        ax.grid(True, linestyle='--', linewidth=0.5, alpha=0.7)
        ax.set_title(filename, fontsize=12, pad=10)

        return fig








    @staticmethod
    def get_intersection_with_cube(A, B, C, D, volume_limits):
        intersections = []

        # Define the cube's limits
        x_min, x_max = volume_limits.comp1
        y_min, y_max = volume_limits.comp2
        z_min, z_max = volume_limits.comp3

        # Auxiliary function to solve the plane equation for x
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

        # Intersections with the Z = constant faces (XY planes)
        for z in [z_min, z_max]:
            for y in [y_min, y_max]:
                x = solve_plane_for_x(y, z)
                if x is not None and x_min <= x <= x_max:
                    intersections.append((x, y, z))

        # Intersections with the Y = constant faces (XZ planes)
        for y in [y_min, y_max]:
            for z in [z_min, z_max]:
                x = solve_plane_for_x(y, z)
                if x is not None and x_min <= x <= x_max:
                    intersections.append((x, y, z))

        # Intersections with the X = constant faces (YZ planes)
        for x in [x_min, x_max]:
            for z in [z_min, z_max]:
                y = solve_plane_for_y(x, z)
                if y is not None and y_min <= y <= y_max:
                    intersections.append((x, y, z))

        return np.array(intersections)


    @staticmethod
    def order_points_by_angle(points):
        # Calculate the centroid
        centroid = np.mean(points, axis=0)

        # Calculate the angles
        angles = np.arctan2(points[:, 1] - centroid[1], points[:, 0] - centroid[0])

        # Order the points by the angle
        ordered_indices = np.argsort(angles)
        return points[ordered_indices]


    @staticmethod
    def clip_face_to_volume(vertices, volume_limits):
        """
        Adjusts a face to the specified volume limits.
        """
        # List to store adjusted points
        adjusted_vertices = []

        # Limit coordinates to the values of the volume
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

    #     # Graficar puntos negativos, aquellos no falsos
    #     false_negatives = Prototype.get_falseNegatives()
    #     negatives_filtered_no_false = [
    #         point for point in negatives_filtered
    #         if not any(np.array_equal(point, fn) for fn in false_negatives)
    #     ]
    #     negatives_filtered = np.array(negatives_filtered_no_false)

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
    #             vertices_clipped_ordered = Visual_tools.clip_face_to_volume(vertices, volume_limits)
    #             poly3d = Poly3DCollection([vertices_clipped_ordered], facecolors='cyan', edgecolors='blue', linewidths=1, alpha=0.5)
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


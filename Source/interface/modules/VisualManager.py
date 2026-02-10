import numpy as np
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import plotly.graph_objects as go
import plotly.express as px

### my libraries ###
from Source.geometry.Point import Point

"""
Module summary
--------------
This module centralizes 3D visualization utilities for LAB color-space data and Voronoi-based
prototype volumes.

It provides:
    - Plotly-based 3D interactive rendering that can combine:
        * Representative centroids (LAB points)
        * Prototype polyhedra (Voronoi volumes) for Core / 0.5-cut / Support
        * Optional filtered points, displayed only when they truly fall inside each prototype volume
        * Legend handling to avoid duplicated legend entries
    - A Matplotlib-based 3D rendering alternative for centroids and prototype volumes
    - Geometry helpers to:
        * Clip polygon faces to a bounding volume (cube limits)
        * Compute plane/cube intersections
        * Order face points by angle for consistent polygon traversal
"""
class VisualManager:
    # Global-like flag used to control legend display across multiple prototype traces
    SHOW_LEGENDS = True

    @staticmethod
    def plot_more_combined_3D(
        filename,
        color_data,
        core,
        alpha,
        support,
        volume_limits,
        hex_color,
        selected_options,
        filtered_points=None,
    ):
        """Generates a 3D figure in Plotly combining centroids, prototypes, and filtered points."""
        fig = go.Figure()

        # ---------- Helper: triangulate polygonal faces ----------
        def triangulate_face(vertices):
            """
            Convert a polygon face (N vertices) into triangles using a fan triangulation:
            [v0,v1,v2], [v0,v2,v3], ...
            """
            triangles = []
            for i in range(1, len(vertices) - 1):
                triangles.append([vertices[0], vertices[i], vertices[i + 1]])
            return triangles

        # ---------- Plot centroids ----------
        def plot_centroids():
            """Plot representative centroids as 3D points (a*, b*, L*) using Plotly."""
            if not color_data:
                return

            # Extract LAB values from color_data (positive prototype for each entry)
            lab_values = [v["positive_prototype"] for v in color_data.values()]
            lab_array = np.array(lab_values)

            # Reorder axes for visualization: x=a*, y=b*, z=L*
            A, B, L = lab_array[:, 1], lab_array[:, 2], lab_array[:, 0]

            # Map each LAB value to its hex color if present, otherwise default to black
            colors = [
                next(
                    (k for k, v in hex_color.items() if np.array_equal(v, lab)),
                    "#000000",
                )
                for lab in lab_values
            ]

            fig.add_trace(
                go.Scatter3d(
                    x=A,
                    y=B,
                    z=L,
                    mode="markers",
                    marker=dict(
                        size=5,
                        color=colors,
                        opacity=0.8,
                        line=dict(color="black", width=1),
                    ),
                    name="Centroids",
                )
            )

        # ---------- Plot prototypes ----------
        def plot_prototypes(prototypes, label):
            """
            Plot prototype Voronoi volumes as Mesh3d surfaces.
            Legend handling:
              - Uses a global flag and presence of filtered points to decide whether to show legends.
              - After first use, SHOW_LEGENDS is set to False to avoid repeated legend entries.
            """
            if not prototypes:
                return

            global_flag = VisualManager.SHOW_LEGENDS  # access the shared legend flag

            # Detect whether any filtered points exist (affects whether prototype legend is shown)
            has_filtered = filtered_points and any(
                len(pts) > 0 for pts in filtered_points.values()
            )

            for idx, prototype in enumerate(prototypes):
                # Determine prototype color from its positive LAB value
                color = next(
                    (
                        k
                        for k, v in hex_color.items()
                        if np.array_equal(prototype.positive, v)
                    ),
                    "#000000",
                )

                vertices, faces = [], []

                # Build a triangulated mesh for each finite Voronoi face
                for face in prototype.voronoi_volume.faces:
                    if not face.infinity:
                        clipped = VisualManager.clip_face_to_volume(
                            np.array(face.vertex), volume_limits
                        )
                        if len(clipped) >= 3:
                            # Reorder to a*, b*, L* for plotting coordinates
                            clipped = clipped[:, [1, 2, 0]]
                            triangles = triangulate_face(clipped)
                            for tri in triangles:
                                idx0 = len(vertices)
                                vertices.extend(tri)
                                faces.append([idx0, idx0 + 1, idx0 + 2])

                if vertices:
                    vertices = np.array(vertices)

                    # Show prototype legend only if there are NO filtered points and the global flag is enabled
                    show_legend = (not has_filtered) and global_flag

                    fig.add_trace(
                        go.Mesh3d(
                            x=vertices[:, 0],
                            y=vertices[:, 1],
                            z=vertices[:, 2],
                            i=[f[0] for f in faces],
                            j=[f[1] for f in faces],
                            k=[f[2] for f in faces],
                            color=color,
                            opacity=0.5,
                            name=(prototype.label),
                            showlegend=show_legend,
                            legendgroup=prototype.label,
                        )
                    )

            # Disable legends for subsequent prototype groups so they do not repeat
            VisualManager.SHOW_LEGENDS = False

        # ---------- Plot filtered points ----------
        def plot_filtered_points(prototypes, point_color="black"):
            """
            Plot filtered points only if they fall inside the actual Voronoi volume of each prototype.

            Implementation detail:
              - Adds one real Scatter3d trace with showlegend=False (actual points).
              - Adds one "dummy" Scatter3d trace (outside plot range) with showlegend=True
                to create a clean legend entry per volume with a distinctive border color.
            """
            if not filtered_points or not prototypes:
                return

            # Edge-color palette to distinguish volumes (up to 24 clearly visible colors)
            border_colors = px.colors.qualitative.Dark24

            for proto_name, points in filtered_points.items():
                # Parse index from name like "Volume_3" -> 3
                idx = int(proto_name.split("_")[-1])
                if idx >= len(prototypes):
                    continue

                prototype = prototypes[idx]

                # Keep only points that are truly inside the prototype volume
                points_inside = [
                    p for p in points if prototype.voronoi_volume.isInside(Point(*p))
                ]
                if not points_inside:
                    continue

                pts = np.array(points_inside)
                L, A, B = pts[:, 0], pts[:, 1], pts[:, 2]

                # Adaptive point size: more points => smaller markers (bounded)
                point_size = max(4, min(10, int(300 / len(points_inside))))

                # Assign a unique border color per volume
                border_color = border_colors[idx % len(border_colors)]

                # 1) Real plot: the points
                fig.add_trace(
                    go.Scatter3d(
                        x=A,
                        y=B,
                        z=L,
                        mode="markers",
                        marker=dict(
                            size=point_size,
                            color=point_color,  # base color (e.g., red or black)
                            opacity=0.7,
                            line=dict(color=border_color, width=0.8),
                        ),
                        name=f"{prototype.label}",
                        legendgroup=f"{prototype.label}",
                        showlegend=False,  # do not show this trace in the legend
                    )
                )

                # 2) Dummy legend-only trace (place a marker outside the visible range)
                x_dummy = [volume_limits.comp2[0] - 10]
                y_dummy = [volume_limits.comp3[0] - 10]
                z_dummy = [volume_limits.comp1[0] - 10]
                fig.add_trace(
                    go.Scatter3d(
                        x=x_dummy,
                        y=y_dummy,
                        z=z_dummy,
                        mode="markers",
                        marker=dict(
                            size=8,
                            color=border_color,  # legend marker color (border color)
                            opacity=1.0,
                            symbol="circle",
                        ),
                        name=f"{prototype.label}",
                        legendgroup=f"{prototype.label}",
                        showlegend=True,  # only this appears in the legend
                    )
                )

        # ---------- Mapping of user-selected options ----------
        # Each option triggers one specific plotting routine
        options_map = {
            "Representative": lambda: plot_centroids(),
            "0.5-cut": lambda: plot_prototypes(alpha, "0.5-cut"),
            "Core": lambda: plot_prototypes(core, "Core"),
            "Support": lambda: plot_prototypes(support, "Support"),
        }

        # Execute the main traces based on user selection
        for option in selected_options:
            if option in options_map:
                options_map[option]()

        # Plot filtered points once (uses whichever prototypes list is available)
        plot_filtered_points(core or alpha or support)

        # ---------- Configure axes and layout ----------
        axis_limits = {}
        if volume_limits:
            axis_limits = dict(
                xaxis=dict(range=volume_limits.comp2),
                yaxis=dict(range=volume_limits.comp3),
                zaxis=dict(range=volume_limits.comp1),
            )

        fig.update_layout(
            scene=dict(
                xaxis_title="a* (Red-Green)",
                yaxis_title="b* (Blue-Yellow)",
                zaxis_title="L* (Luminosity)",
                **axis_limits,
            ),
            margin=dict(l=0, r=0, b=0, t=30),
            title=dict(text=f"{filename}", font=dict(size=10), x=0.5, y=0.95),
        )

        # Reset the global legend flag for future executions
        VisualManager.SHOW_LEGENDS = True
        return fig

    @staticmethod
    def plot_combined_3D(
        filename,
        color_data,
        core,
        alpha,
        support,
        volume_limits,
        hex_color,
        selected_options,
        filtered_points=None,
    ):
        """Generates a single figure combining centroids and prototypes based on selected options."""
        fig = Figure(figsize=(8, 6), dpi=120)
        ax = fig.add_subplot(111, projection="3d")

        # Map each selectable option to its corresponding data object
        data_map = {
            "Representative": color_data,
            "0.5-cut": alpha,
            "Core": core,
            "Support": support,
        }

        # Loop through selected options and plot the corresponding data
        for option, data in data_map.items():
            if option in selected_options and data:
                if isinstance(data, dict):
                    # ---- Color data (centroids) ----
                    lab_values = [v["positive_prototype"] for v in data.values()]
                    lab_array = np.array(lab_values)

                    # Extract L*, a*, b* values from LAB
                    L_values, A_values, B_values = (
                        lab_array[:, 0],
                        lab_array[:, 1],
                        lab_array[:, 2],
                    )

                    # Assign a hex color to each centroid based on LAB match
                    colors = [
                        next(
                            (
                                hex_key
                                for hex_key, lab_val in hex_color.items()
                                if np.array_equal(lab, lab_val)
                            ),
                            "#000000",
                        )
                        for lab in lab_values
                    ]

                    # Scatter plot: x=a*, y=b*, z=L*
                    ax.scatter(
                        A_values,
                        B_values,
                        L_values,
                        c=colors,
                        marker="o",
                        s=30,
                        edgecolor="k",
                        alpha=0.8,
                    )

                elif isinstance(data, list):
                    # ---- Prototypes (Voronoi volumes) ----
                    for prototype in data:
                        # Determine prototype color from its positive LAB value
                        color = next(
                            (
                                hex_key
                                for hex_key, lab_val in hex_color.items()
                                if np.array_equal(prototype.positive, lab_val)
                            ),
                            "#000000",
                        )

                        # Clip finite Voronoi faces to volume bounds
                        valid_faces = [
                            VisualManager.clip_face_to_volume(
                                np.array(face.vertex), volume_limits
                            )
                            for face in prototype.voronoi_volume.faces
                            if not face.infinity
                        ]
                        # Reorder to a*, b*, L* for plotting
                        valid_faces = [
                            f[:, [1, 2, 0]] for f in valid_faces if len(f) >= 3
                        ]

                        # Render the polyhedron if faces exist
                        if valid_faces:
                            ax.add_collection3d(
                                Poly3DCollection(
                                    valid_faces,
                                    facecolors=color,
                                    edgecolors="black",
                                    linewidths=1,
                                    alpha=0.5,
                                )
                            )

                        # Plot filtered points inside this volume (if provided)
                        if filtered_points is not None:
                            for idx, proto_name in enumerate(filtered_points):
                                points = filtered_points[proto_name]

                                points_filter = [
                                    p
                                    for p in points
                                    if prototype.voronoi_volume.isInside(Point(*p))
                                ]

                                if len(points_filter) > 0:
                                    points_array = np.array(points_filter)
                                    L_points, A_points, B_points = (
                                        points_array[:, 0],
                                        points_array[:, 1],
                                        points_array[:, 2],
                                    )
                                    ax.scatter(
                                        A_points,
                                        B_points,
                                        L_points,
                                        c="red",
                                        marker="o",
                                        s=10,
                                        alpha=0.8,
                                    )

        # ---------- Configure axes ----------
        ax.set_xlabel("a* (Red-Green)", fontsize=10, labelpad=10)
        ax.set_ylabel("b* (Blue-Yellow)", fontsize=10, labelpad=10)
        ax.set_zlabel("L* (Luminosity)", fontsize=10, labelpad=10)

        # Apply volume limits if provided
        if volume_limits:
            ax.set_xlim(volume_limits.comp2[0], volume_limits.comp2[1])  # a*
            ax.set_ylim(volume_limits.comp3[0], volume_limits.comp3[1])  # b*
            ax.set_zlim(volume_limits.comp1[0], volume_limits.comp1[1])  # L*

        ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.7)
        ax.set_title(filename, fontsize=12, pad=10)

        return fig

    @staticmethod
    def get_intersection_with_cube(A, B, C, D, volume_limits):
        """
        Compute candidate intersection points between a plane (Ax + By + Cz + D = 0)
        and the faces of the axis-aligned cube defined by volume_limits.

        Returns:
            np.ndarray of intersection points (x, y, z) that lie within the cube bounds.
        """
        intersections = []

        # Define the cube limits
        x_min, x_max = volume_limits.comp1
        y_min, y_max = volume_limits.comp2
        z_min, z_max = volume_limits.comp3

        # Helper: solve the plane equation for x, y, or z (when the coefficient is non-zero)
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

        # Intersections with Z-constant faces (XY planes)
        for z in [z_min, z_max]:
            for y in [y_min, y_max]:
                x = solve_plane_for_x(y, z)
                if x is not None and x_min <= x <= x_max:
                    intersections.append((x, y, z))

        # Intersections with Y-constant faces (XZ planes)
        for y in [y_min, y_max]:
            for z in [z_min, z_max]:
                x = solve_plane_for_x(y, z)
                if x is not None and x_min <= x <= x_max:
                    intersections.append((x, y, z))

        # Intersections with X-constant faces (YZ planes)
        for x in [x_min, x_max]:
            for z in [z_min, z_max]:
                y = solve_plane_for_y(x, z)
                if y is not None and y_min <= y <= y_max:
                    intersections.append((x, y, z))

        return np.array(intersections)

    @staticmethod
    def order_points_by_angle(points):
        """
        Order 2D-projected points around their centroid by polar angle.
        This is useful to ensure polygon vertices are consistently ordered.
        """
        # Compute centroid
        centroid = np.mean(points, axis=0)

        # Compute angles around centroid (using x/y components)
        angles = np.arctan2(points[:, 1] - centroid[1], points[:, 0] - centroid[0])

        # Sort by angle
        ordered_indices = np.argsort(angles)
        return points[ordered_indices]

    @staticmethod
    def clip_face_to_volume(vertices, volume_limits):
        """
        Clip/adjust a set of face vertices to the axis-aligned bounding box defined by volume_limits.

        For each vertex component, values are clamped to:
          - comp1 range for x
          - comp2 range for y
          - comp3 range for z

        Args:
            vertices: Iterable of vertices; can include custom Point objects.
            volume_limits: Object holding comp1, comp2, comp3 ranges.

        Returns:
            np.ndarray of adjusted vertices.
        """
        adjusted_vertices = []

        for vertex in vertices:
            # Convert from custom Point type if needed
            if isinstance(vertex, Point):
                vertex = vertex.get_double_point()

            adjusted_vertex = np.array(
                [
                    np.clip(vertex[0], volume_limits.comp1[0], volume_limits.comp1[1]),
                    np.clip(vertex[1], volume_limits.comp2[0], volume_limits.comp2[1]),
                    np.clip(vertex[2], volume_limits.comp3[0], volume_limits.comp3[1]),
                ]
            )
            adjusted_vertices.append(adjusted_vertex)

        return np.array(adjusted_vertices)

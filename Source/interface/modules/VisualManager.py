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
    # Shared flag that can be used to control legend duplication across traces.
    SHOW_LEGENDS = True

    @staticmethod
    def clip_face_to_volume(vertices, volume_limits):
        """
        Clamp face vertices to the axis-aligned LAB bounding box defined by volume_limits.
        """
        if vertices is None:
            return np.empty((0, 3), dtype=float)

        processed_vertices = [
            vertex.get_double_point() if isinstance(vertex, Point) else vertex
            for vertex in vertices
        ]

        if not processed_vertices:
            return np.empty((0, 3), dtype=float)

        vertices_array = np.asarray(processed_vertices, dtype=float)

        lower_bounds = np.array(
            [volume_limits.comp1[0], volume_limits.comp2[0], volume_limits.comp3[0]],
            dtype=float,
        )
        upper_bounds = np.array(
            [volume_limits.comp1[1], volume_limits.comp2[1], volume_limits.comp3[1]],
            dtype=float,
        )

        return np.clip(vertices_array, lower_bounds, upper_bounds)



    @staticmethod
    def plot_combined_3D(
        ax,
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
        """
        Draw the complete 3D model on an existing Axes3D instance.

        This function reuses the provided axis instead of creating a new figure
        every time. That makes repeated updates much cheaper.

        Args:
            ax: Existing matplotlib 3D axis.
            filename: Title shown on the plot.
            color_data: Dictionary with representative color data.
            core: List of core prototypes.
            alpha: List of 0.5-cut prototypes.
            support: List of support prototypes.
            volume_limits: LAB axis limits.
            hex_color: Mapping from display hex colors to LAB prototype values.
            selected_options: Active visualization layers.
            filtered_points: Optional filtered LAB points grouped by prototype name.
        """
        # Clear previous artists while keeping the same figure and widget alive.
        ax.cla()

        data_map = {
            "Representative": color_data,
            "0.5-cut": alpha,
            "Core": core,
            "Support": support,
        }

        def lab_to_key(lab):
            """
            Convert a LAB vector into a rounded hashable key.
            """
            return tuple(np.round(np.asarray(lab, dtype=float), 6))

        # Build inverse color lookup once for this draw call.
        inverse_hex_color = {
            lab_to_key(lab_val): hex_key
            for hex_key, lab_val in hex_color.items()
        }

        # Preconvert filtered points once to NumPy arrays.
        filtered_points_arrays = {}
        if filtered_points is not None:
            for proto_name, points in filtered_points.items():
                if points:
                    filtered_points_arrays[proto_name] = np.asarray(points, dtype=float)

        # ------------------------------------------------------------------
        # Draw representative points
        # ------------------------------------------------------------------
        if "Representative" in selected_options and isinstance(color_data, dict):
            lab_values = [value["positive_prototype"] for value in color_data.values()]

            if lab_values:
                lab_array = np.asarray(lab_values, dtype=float)

                colors = [
                    inverse_hex_color.get(lab_to_key(lab), "#000000")
                    for lab in lab_values
                ]

                # Plot as x=a*, y=b*, z=L* for a more intuitive LAB view.
                ax.scatter(
                    lab_array[:, 1],
                    lab_array[:, 2],
                    lab_array[:, 0],
                    c=colors,
                    s=30,
                    edgecolor="k",
                    linewidths=0.6,
                    alpha=0.8,
                    depthshade=False,
                )

        # ------------------------------------------------------------------
        # Draw fuzzy volumes and filtered points
        # ------------------------------------------------------------------
        for option in ("0.5-cut", "Core", "Support"):
            if option not in selected_options:
                continue

            prototypes = data_map.get(option)
            if not prototypes:
                continue

            all_faces = []
            all_facecolors = []
            all_filtered_points = []

            for prototype in prototypes:
                color = inverse_hex_color.get(
                    lab_to_key(prototype.positive),
                    "#000000",
                )

                # Cache clipped faces for each prototype and option to avoid
                # recomputing the same geometry on every redraw.
                cache_attr = f"_cached_faces_{option.replace('-', '_')}"
                if not hasattr(prototype, cache_attr):
                    valid_faces = []

                    for face in prototype.voronoi_volume.faces:
                        if face.infinity or face.vertex is None:
                            continue

                        clipped_face = VisualManager.clip_face_to_volume(
                            face.vertex,
                            volume_limits,
                        )

                        if len(clipped_face) >= 3:
                            valid_faces.append(clipped_face[:, [1, 2, 0]])

                    setattr(prototype, cache_attr, valid_faces)

                valid_faces = getattr(prototype, cache_attr)

                for face_vertices in valid_faces:
                    all_faces.append(face_vertices)
                    all_facecolors.append(color)

                # Check which filtered points belong to the current prototype volume.
                if filtered_points_arrays:
                    for _proto_name, points_array in filtered_points_arrays.items():
                        if len(points_array) == 0:
                            continue

                        points_inside = [
                            point
                            for point in points_array
                            if prototype.voronoi_volume.isInside(Point(*point))
                        ]

                        if points_inside:
                            all_filtered_points.extend(points_inside)

            if all_faces:
                ax.add_collection3d(
                    Poly3DCollection(
                        all_faces,
                        facecolors=all_facecolors,
                        edgecolors="black",
                        linewidths=0.5,
                        alpha=0.5,
                    )
                )

            # Draw all filtered points for the current option in a single scatter.
            if all_filtered_points:
                points_array = np.asarray(all_filtered_points, dtype=float)

                ax.scatter(
                    points_array[:, 1],  # a*
                    points_array[:, 2],  # b*
                    points_array[:, 0],  # L*
                    c="red",
                    marker="o",
                    s=10,
                    alpha=0.8,
                    depthshade=False,
                )

        # ------------------------------------------------------------------
        # Configure axes
        # ------------------------------------------------------------------
        ax.set_xlabel("a* (Green-Red)", fontsize=10, labelpad=10)
        ax.set_ylabel("b* (Blue-Yellow)", fontsize=10, labelpad=10)
        ax.set_zlabel("L* (Lightness)", fontsize=10, labelpad=10)

        if volume_limits:
            ax.set_xlim(volume_limits.comp2)
            ax.set_ylim(volume_limits.comp3)
            ax.set_zlim(volume_limits.comp1)

        ax.set_title(filename)
        ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.7)

        try:
            ax.set_box_aspect((1, 1, 1))
        except Exception:
            pass

        fig = ax.get_figure()
        VisualManager.draw_orientation_inset(fig, ax)


    @staticmethod
    def draw_orientation_inset(fig, ax_main=None):
        """
        Draw a fixed-position 3D orientation inset with a fixed camera,
        independent from the main axes.
        """
        for existing_ax in fig.axes[:]:
            if hasattr(existing_ax, "_is_orientation_inset"):
                fig.delaxes(existing_ax)

        ax_inset = fig.add_axes([0.02, 0.02, 0.18, 0.30], projection="3d")
        ax_inset._is_orientation_inset = True

        # Remove white background
        ax_inset.set_facecolor((1, 1, 1, 0))
        ax_inset.patch.set_alpha(0)

        # Fixed orientation
        ax_inset.view_init(elev=30, azim=-60)

        lim = 1.2
        ax_inset.set_xlim(-lim, lim)
        ax_inset.set_ylim(-lim, lim)
        ax_inset.set_zlim(-lim, lim)

        ax_inset.set_xticks([])
        ax_inset.set_yticks([])
        ax_inset.set_zticks([])
        ax_inset.set_xlabel("")
        ax_inset.set_ylabel("")
        ax_inset.set_zlabel("")
        ax_inset.set_axis_off()

        # También por si Matplotlib deja panes visibles en 3D
        try:
            ax_inset.xaxis.pane.fill = False
            ax_inset.yaxis.pane.fill = False
            ax_inset.zaxis.pane.fill = False

            ax_inset.xaxis.pane.set_edgecolor((1, 1, 1, 0))
            ax_inset.yaxis.pane.set_edgecolor((1, 1, 1, 0))
            ax_inset.zaxis.pane.set_edgecolor((1, 1, 1, 0))
        except Exception:
            pass

        # a*: Green <-> Red
        ax_inset.quiver(0, 0, 0,  1, 0, 0, color="red",   arrow_length_ratio=0.2)
        ax_inset.quiver(0, 0, 0, -1, 0, 0, color="green", arrow_length_ratio=0.2)

        # b*: Blue <-> Yellow
        ax_inset.quiver(0, 0, 0, 0,  1, 0, color="gold", arrow_length_ratio=0.2)
        ax_inset.quiver(0, 0, 0, 0, -1, 0, color="blue", arrow_length_ratio=0.2)

        # L*: Dark <-> Light
        ax_inset.quiver(0, 0, 0, 0, 0,  1, color="gray",  arrow_length_ratio=0.2)
        ax_inset.quiver(0, 0, 0, 0, 0, -1, color="black", arrow_length_ratio=0.2)

        ax_inset.text( 1.18, -0.05,  0.00, "+a*", fontsize=8)
        ax_inset.text(-1.32,  0.02,  0.02, "-a*", fontsize=8)

        ax_inset.text( 0.06,  1.18,  0.02, "+b*", fontsize=8)
        ax_inset.text(-0.10, -1.34, -0.08, "-b*", fontsize=8)

        ax_inset.text( 0.02,  0.02,  1.18, "+L*", fontsize=8)
        ax_inset.text( 0.04, -0.08, -1.34, "-L*", fontsize=8)

        return ax_inset








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
                    if face.infinity or face.vertex is None:
                        continue

                    clipped = VisualManager.clip_face_to_volume(
                        face.vertex,
                        volume_limits
                    )
                    if len(clipped) >= 3:
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
                zaxis_title="L* (Lightness)",
                **axis_limits,
            ),
            margin=dict(l=0, r=0, b=0, t=30),
            title=dict(text=f"{filename}", font=dict(size=10), x=0.5, y=0.95),
        )

        # Reset the global legend flag for future executions
        VisualManager.SHOW_LEGENDS = True
        return fig

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




    @staticmethod
    def _lab_key(lab):
        """
        Convert LAB into a stable rounded key.
        """
        return tuple(np.round(np.asarray(lab, dtype=float).reshape(-1)[:3], 6))


    @staticmethod
    def _find_hex_for_lab(lab, hex_color, default="#000000"):
        """
        Find the HEX color associated with a LAB value.
        hex_color is expected as:
            {
                "#rrggbb": lab
            }
        """
        if not isinstance(hex_color, dict):
            return default

        target_key = VisualManager._lab_key(lab)

        for hex_value, lab_value in hex_color.items():
            try:
                if VisualManager._lab_key(lab_value) == target_key:
                    return hex_value
            except Exception:
                continue

        return default


    @staticmethod
    def _triangulate_face(vertices):
        """
        Convert a polygon face with N vertices into triangles.
        """
        triangles = []

        for i in range(1, len(vertices) - 1):
            triangles.append([vertices[0], vertices[i], vertices[i + 1]])

        return triangles


    @staticmethod
    def plot_more_color_evaluation_3D(
        filename,
        color_data,
        core,
        alpha,
        support,
        volume_limits,
        hex_color,
        custom_lab,
        custom_hex="#ff0000",
        closest_label=None,
        closest_lab=None,
        closest_hex="#000000",
        initial_volume_mode="Representative",
    ):
        """
        Plotly 3D LAB visualization for the Color Evaluation tool.

        It shows:
        - all representative prototypes;
        - optional Core / 0.5-cut / Support volumes selectable from buttons;
        - custom color as a highlighted point;
        - closest prototype as a highlighted point;
        - line between custom color and closest prototype;
        - right legend with all prototype labels so the user can click/hide colors.
        """
        fig = go.Figure()

        color_data = color_data or {}
        custom_lab = np.asarray(custom_lab, dtype=float).reshape(-1)[:3]

        if closest_lab is not None:
            closest_lab = np.asarray(closest_lab, dtype=float).reshape(-1)[:3]

        # ------------------------------------------------------------------
        # Prepare volume groups
        # ------------------------------------------------------------------
        volume_groups = {
            "Representative": None,
            "Core": core,
            "0.5-cut": alpha,
            "Support": support,
        }

        if initial_volume_mode not in volume_groups:
            initial_volume_mode = "Representative"

        volume_trace_indices = {
            "Representative": [],
            "Core": [],
            "0.5-cut": [],
            "Support": [],
        }

        always_visible_indices = []

        # ------------------------------------------------------------------
        # Representative prototypes, one trace per color.
        # This gives a clickable legend on the right.
        # ------------------------------------------------------------------
        for label, value in color_data.items():
            try:
                lab = np.asarray(value["positive_prototype"], dtype=float).reshape(-1)[:3]
            except Exception:
                continue

            proto_hex = VisualManager._find_hex_for_lab(lab, hex_color, default="#000000")

            is_closest = closest_label is not None and str(label) == str(closest_label)

            marker_size = 7 if is_closest else 5
            marker_line_width = 3 if is_closest else 1

            fig.add_trace(
                go.Scatter3d(
                    x=[lab[1]],
                    y=[lab[2]],
                    z=[lab[0]],
                    mode="markers",
                    marker=dict(
                        size=marker_size,
                        color=proto_hex,
                        opacity=0.95,
                        line=dict(color="black", width=marker_line_width),
                    ),
                    name=str(label),
                    legendgroup=str(label),
                    showlegend=True,
                    hovertemplate=(
                        f"<b>{label}</b><br>"
                        "L*: %{z:.3f}<br>"
                        "a*: %{x:.3f}<br>"
                        "b*: %{y:.3f}<extra></extra>"
                    ),
                )
            )

            always_visible_indices.append(len(fig.data) - 1)

        # ------------------------------------------------------------------
        # Volumes: Core / 0.5-cut / Support.
        # Mesh traces share legendgroup with representative points.
        # They are controlled by Plotly buttons.
        # ------------------------------------------------------------------
        for mode_name, prototypes in (
            ("Core", core),
            ("0.5-cut", alpha),
            ("Support", support),
        ):
            if not prototypes:
                continue

            for prototype in prototypes:
                try:
                    proto_label = str(prototype.label)
                    proto_hex = VisualManager._find_hex_for_lab(
                        prototype.positive,
                        hex_color,
                        default="#000000"
                    )

                    vertices = []
                    faces = []

                    for face in prototype.voronoi_volume.faces:
                        if face.infinity or face.vertex is None:
                            continue

                        clipped = VisualManager.clip_face_to_volume(
                            face.vertex,
                            volume_limits
                        )

                        if len(clipped) < 3:
                            continue

                        # Reorder from LAB to a*, b*, L*
                        clipped = clipped[:, [1, 2, 0]]

                        triangles = VisualManager._triangulate_face(clipped)

                        for tri in triangles:
                            base_idx = len(vertices)
                            vertices.extend(tri)
                            faces.append([base_idx, base_idx + 1, base_idx + 2])

                    if not vertices:
                        continue

                    vertices = np.asarray(vertices, dtype=float)

                    fig.add_trace(
                        go.Mesh3d(
                            x=vertices[:, 0],
                            y=vertices[:, 1],
                            z=vertices[:, 2],
                            i=[f[0] for f in faces],
                            j=[f[1] for f in faces],
                            k=[f[2] for f in faces],
                            color=proto_hex,
                            opacity=0.28,
                            name=f"{mode_name}: {proto_label}",
                            legendgroup=proto_label,
                            showlegend=False,
                            visible=(mode_name == initial_volume_mode),
                            hoverinfo="skip",
                        )
                    )

                    volume_trace_indices[mode_name].append(len(fig.data) - 1)

                except Exception:
                    continue

        # ------------------------------------------------------------------
        # Custom color
        # ------------------------------------------------------------------
        fig.add_trace(
            go.Scatter3d(
                x=[custom_lab[1]],
                y=[custom_lab[2]],
                z=[custom_lab[0]],
                mode="markers",
                marker=dict(
                    size=11,
                    color=custom_hex,
                    symbol="diamond",
                    opacity=1.0,
                    line=dict(color="black", width=2),
                ),
                name="Custom color",
                legendgroup="__custom__",
                showlegend=True,
                hovertemplate=(
                    "<b>Custom color</b><br>"
                    "L*: %{z:.3f}<br>"
                    "a*: %{x:.3f}<br>"
                    "b*: %{y:.3f}<extra></extra>"
                ),
            )
        )
        always_visible_indices.append(len(fig.data) - 1)

        # ------------------------------------------------------------------
        # Closest prototype highlighted separately
        # ------------------------------------------------------------------
        if closest_lab is not None:
            fig.add_trace(
                go.Scatter3d(
                    x=[closest_lab[1]],
                    y=[closest_lab[2]],
                    z=[closest_lab[0]],
                    mode="markers",
                    marker=dict(
                        size=12,
                        color=closest_hex,
                        symbol="circle",
                        opacity=1.0,
                        line=dict(color="black", width=4),
                    ),
                    name=f"Closest: {closest_label}",
                    legendgroup="__closest__",
                    showlegend=True,
                    hovertemplate=(
                        f"<b>Closest: {closest_label}</b><br>"
                        "L*: %{z:.3f}<br>"
                        "a*: %{x:.3f}<br>"
                        "b*: %{y:.3f}<extra></extra>"
                    ),
                )
            )
            always_visible_indices.append(len(fig.data) - 1)

            # Line between custom and closest
            fig.add_trace(
                go.Scatter3d(
                    x=[custom_lab[1], closest_lab[1]],
                    y=[custom_lab[2], closest_lab[2]],
                    z=[custom_lab[0], closest_lab[0]],
                    mode="lines",
                    line=dict(color="black", width=5),
                    name="Custom → closest",
                    legendgroup="__distance__",
                    showlegend=True,
                    hoverinfo="skip",
                )
            )
            always_visible_indices.append(len(fig.data) - 1)

        # ------------------------------------------------------------------
        # Buttons for volume mode
        # ------------------------------------------------------------------
        total_traces = len(fig.data)

        def visibility_for(mode_name):
            visibility = [False] * total_traces

            # Representative points + custom + closest + line are always visible
            for idx in always_visible_indices:
                if 0 <= idx < total_traces:
                    visibility[idx] = True

            # Selected volume layer
            for idx in volume_trace_indices.get(mode_name, []):
                if 0 <= idx < total_traces:
                    visibility[idx] = True

            return visibility

        buttons = []

        for mode_name in ("Representative", "Core", "0.5-cut", "Support"):
            buttons.append(
                dict(
                    label=mode_name,
                    method="update",
                    args=[
                        {"visible": visibility_for(mode_name)},
                        {"title": f"{filename} | {mode_name}"}
                    ],
                )
            )

        # ------------------------------------------------------------------
        # Axis limits
        # ------------------------------------------------------------------
        axis_limits = {}

        if volume_limits:
            axis_limits = dict(
                xaxis=dict(range=volume_limits.comp2),
                yaxis=dict(range=volume_limits.comp3),
                zaxis=dict(range=volume_limits.comp1),
            )

        fig.update_layout(
            title=dict(
                text=f"{filename} | {initial_volume_mode}",
                font=dict(size=13),
                x=0.5,
                y=0.96,
            ),
            scene=dict(
                xaxis_title="a* (Red-Green)",
                yaxis_title="b* (Blue-Yellow)",
                zaxis_title="L* (Lightness)",
                **axis_limits,
            ),
            updatemenus=[
                dict(
                    type="buttons",
                    direction="right",
                    x=0.5,
                    y=1.08,
                    xanchor="center",
                    yanchor="top",
                    buttons=buttons,
                )
            ],
            legend=dict(
                x=1.02,
                y=1.0,
                xanchor="left",
                yanchor="top",
                groupclick="togglegroup",
                title=dict(text="Colors"),
            ),
            margin=dict(l=0, r=230, b=0, t=75),
        )

        return fig


    @staticmethod
    def plot_color_evaluation_top7_bar(
        ranking,
        metric_name="CIEDE2000",
        title="Top 7 closest prototypes",
    ):
        """
        Horizontal bar chart for the closest 7 prototypes.
        """
        ranking = ranking or []
        ranking = ranking[:7]

        labels = [str(item["label"]) for item in ranking]
        values = [float(item["delta_e"]) for item in ranking]

        fig = go.Figure()

        fig.add_trace(
            go.Bar(
                x=values[::-1],
                y=labels[::-1],
                orientation="h",
                text=[f"{v:.3f}" for v in values[::-1]],
                textposition="auto",
                hovertemplate="<b>%{y}</b><br>" + metric_name + ": %{x:.3f}<extra></extra>",
            )
        )

        fig.update_layout(
            title=dict(text=title, x=0.5),
            xaxis_title=metric_name,
            yaxis_title="Prototype",
            margin=dict(l=120, r=30, t=55, b=45),
        )

        return fig


    @staticmethod
    def plot_color_evaluation_ab_projection(
        color_data,
        hex_color,
        custom_lab,
        custom_hex="#ff0000",
        closest_label=None,
        closest_lab=None,
        closest_hex="#000000",
        filename="Color evaluation",
    ):
        """
        2D a*b* projection with all prototypes, custom color, and closest prototype.
        """
        fig = go.Figure()

        color_data = color_data or {}
        custom_lab = np.asarray(custom_lab, dtype=float).reshape(-1)[:3]

        for label, value in color_data.items():
            try:
                lab = np.asarray(value["positive_prototype"], dtype=float).reshape(-1)[:3]
            except Exception:
                continue

            proto_hex = VisualManager._find_hex_for_lab(lab, hex_color, default="#000000")

            fig.add_trace(
                go.Scatter(
                    x=[lab[1]],
                    y=[lab[2]],
                    mode="markers",
                    marker=dict(
                        size=9,
                        color=proto_hex,
                        line=dict(color="black", width=1),
                    ),
                    name=str(label),
                    legendgroup=str(label),
                    showlegend=True,
                    hovertemplate=(
                        f"<b>{label}</b><br>"
                        "a*: %{x:.3f}<br>"
                        "b*: %{y:.3f}<extra></extra>"
                    ),
                )
            )

        fig.add_trace(
            go.Scatter(
                x=[custom_lab[1]],
                y=[custom_lab[2]],
                mode="markers",
                marker=dict(
                    size=15,
                    color=custom_hex,
                    symbol="diamond",
                    line=dict(color="black", width=2),
                ),
                name="Custom color",
                showlegend=True,
                hovertemplate="<b>Custom color</b><br>a*: %{x:.3f}<br>b*: %{y:.3f}<extra></extra>",
            )
        )

        if closest_lab is not None:
            closest_lab = np.asarray(closest_lab, dtype=float).reshape(-1)[:3]

            fig.add_trace(
                go.Scatter(
                    x=[closest_lab[1]],
                    y=[closest_lab[2]],
                    mode="markers",
                    marker=dict(
                        size=16,
                        color=closest_hex,
                        symbol="circle",
                        line=dict(color="black", width=4),
                    ),
                    name=f"Closest: {closest_label}",
                    showlegend=True,
                    hovertemplate=(
                        f"<b>Closest: {closest_label}</b><br>"
                        "a*: %{x:.3f}<br>"
                        "b*: %{y:.3f}<extra></extra>"
                    ),
                )
            )

            fig.add_trace(
                go.Scatter(
                    x=[custom_lab[1], closest_lab[1]],
                    y=[custom_lab[2], closest_lab[2]],
                    mode="lines",
                    line=dict(color="black", width=2),
                    name="Custom → closest",
                    showlegend=True,
                    hoverinfo="skip",
                )
            )

        fig.update_layout(
            title=dict(text=f"{filename} | a*b* projection", x=0.5),
            xaxis_title="a* (Red-Green)",
            yaxis_title="b* (Blue-Yellow)",
            legend=dict(
                x=1.02,
                y=1.0,
                xanchor="left",
                yanchor="top",
                groupclick="togglegroup",
                title=dict(text="Colors"),
            ),
            margin=dict(l=60, r=230, t=55, b=55),
        )

        fig.update_xaxes(zeroline=True, zerolinewidth=1, zerolinecolor="gray")
        fig.update_yaxes(zeroline=True, zerolinewidth=1, zerolinecolor="gray")

        return fig


    @staticmethod
    def plot_color_evaluation_membership_bar(
        memberships,
        title="Membership degrees",
        top_n=10,
    ):
        """
        Horizontal bar chart for membership degrees.
        memberships is expected as:
            [(label, mu), ...]
        """
        memberships = memberships or []
        memberships = sorted(
            memberships,
            key=lambda item: float(item[1]),
            reverse=True
        )[:top_n]

        labels = [str(label) for label, _mu in memberships]
        values = [float(mu) for _label, mu in memberships]

        fig = go.Figure()

        fig.add_trace(
            go.Bar(
                x=values[::-1],
                y=labels[::-1],
                orientation="h",
                text=[f"{v:.4f}" for v in values[::-1]],
                textposition="auto",
                hovertemplate="<b>%{y}</b><br>μ = %{x:.4f}<extra></extra>",
            )
        )

        fig.update_layout(
            title=dict(text=title, x=0.5),
            xaxis_title="Membership degree (μ)",
            yaxis_title="Prototype",
            xaxis=dict(range=[0, 1]),
            margin=dict(l=130, r=30, t=55, b=45),
        )

        return fig

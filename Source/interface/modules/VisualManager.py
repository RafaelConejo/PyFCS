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
        * Optional custom/sample color markers for Color Evaluation
        * Optional closest-prototype highlighting
        * Legend handling to avoid duplicated legend entries
    - Matplotlib-based 3D rendering alternative for centroids and prototype volumes
    - Color Evaluation plots:
        * 3D LAB
        * a*b* projection
        * L*C* projection
        * LCh polar hue/chroma plot
        * Top-7 ranking bar plot
        * Membership-degree bar plot
        * Component-difference plot
    - Geometry helpers to:
        * Clip polygon faces to a bounding volume
        * Triangulate polygonal faces
        * Find display HEX colors from LAB coordinates
"""


class VisualManager:
    # Shared flag that can be used to control legend duplication across traces.
    SHOW_LEGENDS = True

    # ============================================================================================================================================================
    #  GEOMETRY / COLOR HELPERS
    # ============================================================================================================================================================

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
    def _safe_lab(lab):
        """
        Convert input LAB-like value to a 3-component numpy array.
        """
        if lab is None:
            return None

        arr = np.asarray(lab, dtype=float).reshape(-1)

        if arr.shape[0] < 3:
            return None

        return arr[:3]


    @staticmethod
    def _lab_to_lch(lab):
        """
        Convert CIELAB to CIELCh(ab).

        Returns
        -------
        tuple
            (L*, C*, h°)
        """
        lab = VisualManager._safe_lab(lab)

        if lab is None:
            return None

        L, a, b = lab
        C = float(np.sqrt(a ** 2 + b ** 2))
        h = float(np.degrees(np.arctan2(b, a)) % 360.0)

        return float(L), C, h


    @staticmethod
    def _format_metric_value(value, metric_name="CIEDE2000"):
        """
        Format ranking/metric values for hover labels and bar text.
        """
        try:
            value = float(value)
        except Exception:
            return "-"

        metric_name = str(metric_name)

        if metric_name in ("|ΔR|", "|ΔG|", "|ΔB|"):
            return f"{value:.0f}"

        if metric_name == "RGB Euclidean":
            return f"{value:.2f}"

        if metric_name == "|Δh°|":
            return f"{value:.2f}°"

        return f"{value:.3f}"


    @staticmethod
    def _get_ranking_metric_value(item):
        """
        Retrieve metric value from ranking item, preserving backwards compatibility.
        """
        if not isinstance(item, dict):
            return None

        return item.get("metric_value", item.get("delta_e"))


    # ============================================================================================================================================================
    #  EMBEDDED MATPLOTLIB 3D MODEL
    # ============================================================================================================================================================

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
        """
        ax.cla()

        data_map = {
            "Representative": color_data,
            "0.5-cut": alpha,
            "Core": core,
            "Support": support,
        }

        def lab_to_key(lab):
            return tuple(np.round(np.asarray(lab, dtype=float), 6))

        inverse_hex_color = {
            lab_to_key(lab_val): hex_key
            for hex_key, lab_val in hex_color.items()
        }

        filtered_points_arrays = {}

        if filtered_points is not None:
            for proto_name, points in filtered_points.items():
                if points:
                    filtered_points_arrays[proto_name] = np.asarray(points, dtype=float)

        # ------------------------------------------------------------------
        # Representative points
        # ------------------------------------------------------------------
        if "Representative" in selected_options and isinstance(color_data, dict):
            lab_values = [value["positive_prototype"] for value in color_data.values()]

            if lab_values:
                lab_array = np.asarray(lab_values, dtype=float)

                colors = [
                    inverse_hex_color.get(lab_to_key(lab), "#000000")
                    for lab in lab_values
                ]

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
        # Fuzzy volumes and filtered points
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

            if all_filtered_points:
                points_array = np.asarray(all_filtered_points, dtype=float)

                ax.scatter(
                    points_array[:, 1],
                    points_array[:, 2],
                    points_array[:, 0],
                    c="red",
                    marker="o",
                    s=10,
                    alpha=0.8,
                    depthshade=False,
                )

        # ------------------------------------------------------------------
        # Axes
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

        ax_inset.set_facecolor((1, 1, 1, 0))
        ax_inset.patch.set_alpha(0)

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
        ax_inset.quiver(0, 0, 0, 1, 0, 0, color="red", arrow_length_ratio=0.2)
        ax_inset.quiver(0, 0, 0, -1, 0, 0, color="green", arrow_length_ratio=0.2)

        # b*: Blue <-> Yellow
        ax_inset.quiver(0, 0, 0, 0, 1, 0, color="gold", arrow_length_ratio=0.2)
        ax_inset.quiver(0, 0, 0, 0, -1, 0, color="blue", arrow_length_ratio=0.2)

        # L*: Dark <-> Light
        ax_inset.quiver(0, 0, 0, 0, 0, 1, color="gray", arrow_length_ratio=0.2)
        ax_inset.quiver(0, 0, 0, 0, 0, -1, color="black", arrow_length_ratio=0.2)

        ax_inset.text(1.18, -0.05, 0.00, "+a*", fontsize=8)
        ax_inset.text(-1.32, 0.02, 0.02, "-a*", fontsize=8)

        ax_inset.text(0.06, 1.18, 0.02, "+b*", fontsize=8)
        ax_inset.text(-0.10, -1.34, -0.08, "-b*", fontsize=8)

        ax_inset.text(0.02, 0.02, 1.18, "+L*", fontsize=8)
        ax_inset.text(0.04, -0.08, -1.34, "-L*", fontsize=8)

        return ax_inset


    # ============================================================================================================================================================
    #  GENERAL INTERACTIVE PLOTLY 3D MODEL
    # ============================================================================================================================================================

    @staticmethod
    def plot_more_combined_3D(
        filename,
        color_data,
        core,
        alpha,
        support,
        volume_limits,
        hex_color,
        selected_options=None,
        filtered_points=None,
        custom_lab=None,
        custom_hex="#ff0000",
        closest_label=None,
        closest_lab=None,
        closest_hex="#000000",
    ):
        """
        Generate a unified interactive Plotly 3D LAB figure.

        Features
        --------
        - Representative / Core / 0.5-cut / Support can be toggled independently.
        - Several volume layers can be superimposed at once.
        - Select/Deselect all colors respects the currently displayed geometry.
        - Optional custom/sample color is drawn as a smaller diamond.
        - Optional closest prototype is highlighted.
        - Optional custom-to-closest distance line can be toggled with a button.
        """

        fig = go.Figure()

        color_data = color_data or {}
        selected_options = selected_options or ["Representative"]

        # ------------------------------------------------------------------
        # Title: only color-space name.
        # ------------------------------------------------------------------
        title_text = str(filename).split("|")[0].strip()

        # ------------------------------------------------------------------
        # Normalize layer names for backwards compatibility.
        # ------------------------------------------------------------------
        def _normalize_option(option):
            text = str(option).strip().lower()

            if text in ("representative", "representatives", "centroid", "centroids"):
                return "Representative"

            if text == "core":
                return "Core"

            if text in ("0.5-cut", "0.5cut", "0.5 cut", "alpha", "alpha-cut", "alphacut"):
                return "0.5-cut"

            if text in ("support", "suppport"):
                return "Support"

            return str(option).strip()

        selected_options = {
            _normalize_option(option)
            for option in selected_options
        }

        custom_lab = VisualManager._safe_lab(custom_lab)
        closest_lab = VisualManager._safe_lab(closest_lab)

        has_distance_line = custom_lab is not None and closest_lab is not None

        # ------------------------------------------------------------------
        # Visual constants.
        # ------------------------------------------------------------------
        layer_names = ("Representative", "Core", "0.5-cut", "Support")

        layer_opacity = {
            "Representative": 0.96,
            "Core": 0.42,
            "0.5-cut": 0.26,
            "Support": 0.16,
        }

        marker_sizes = {
            "Representative": 5.8,
            "Custom": 8.2,
            "Closest": 10.5,
        }

        layer_indices = {
            "Representative": [],
            "Core": [],
            "0.5-cut": [],
            "Support": [],
            "Distance line": [],
        }

        color_control_indices = []
        legend_labels_added = set()

        # ------------------------------------------------------------------
        # Small helpers.
        # ------------------------------------------------------------------
        def _prototype_hex_from_lab(lab):
            return VisualManager._find_hex_for_lab(
                lab,
                hex_color,
                default="#000000"
            )

        def _safe_label(value):
            try:
                return str(value)
            except Exception:
                return "Prototype"

        def _initial_opacity(layer_name):
            return layer_opacity[layer_name] if layer_name in selected_options else 0.0

        def _initial_visible(layer_name):
            return True if layer_name in selected_options else "legendonly"

        def _add_legend_anchor(label, proto_hex, rank):
            """
            Add one clean legend item per prototype.

            Real traces do not show legend entries. They share this legendgroup.
            This avoids duplicated legend entries when several volumes are active.
            """
            label = _safe_label(label)

            if label in legend_labels_added:
                return

            fig.add_trace(
                go.Scatter3d(
                    x=[None],
                    y=[None],
                    z=[None],
                    mode="markers",
                    marker=dict(
                        size=7,
                        color=proto_hex,
                        opacity=1.0,
                        line=dict(color="black", width=0.8),
                    ),
                    name=label,
                    legendgroup=label,
                    showlegend=True,
                    legendrank=rank,
                    hoverinfo="skip",
                )
            )

            legend_labels_added.add(label)

        def _build_mesh_vertices_and_faces(prototype):
            vertices = []
            faces = []

            try:
                voronoi_faces = prototype.voronoi_volume.faces
            except Exception:
                return None, None

            for face in voronoi_faces:
                try:
                    if face.infinity or face.vertex is None:
                        continue

                    clipped = VisualManager.clip_face_to_volume(
                        face.vertex,
                        volume_limits
                    )

                    if len(clipped) < 3:
                        continue

                    # Plotly axes: x=a*, y=b*, z=L*
                    clipped = clipped[:, [1, 2, 0]]
                    triangles = VisualManager._triangulate_face(clipped)

                    for triangle in triangles:
                        base_idx = len(vertices)
                        vertices.extend(triangle)
                        faces.append([base_idx, base_idx + 1, base_idx + 2])

                except Exception:
                    continue

            if not vertices or not faces:
                return None, None

            return np.asarray(vertices, dtype=float), faces

        # ------------------------------------------------------------------
        # Legend anchors first, one per prototype.
        # ------------------------------------------------------------------
        for rank, (label, value) in enumerate(color_data.items()):
            try:
                lab = np.asarray(value["positive_prototype"], dtype=float).reshape(-1)[:3]
            except Exception:
                continue

            proto_hex = _prototype_hex_from_lab(lab)
            _add_legend_anchor(label, proto_hex, rank)

        # ------------------------------------------------------------------
        # Representative points.
        # ------------------------------------------------------------------
        for label, value in color_data.items():
            try:
                lab = np.asarray(value["positive_prototype"], dtype=float).reshape(-1)[:3]
            except Exception:
                continue

            label = _safe_label(label)
            proto_hex = _prototype_hex_from_lab(lab)

            is_closest = closest_label is not None and label == str(closest_label)

            fig.add_trace(
                go.Scatter3d(
                    x=[lab[1]],
                    y=[lab[2]],
                    z=[lab[0]],
                    mode="markers",
                    marker=dict(
                        size=7.6 if is_closest else marker_sizes["Representative"],
                        color=proto_hex,
                        opacity=_initial_opacity("Representative"),
                        line=dict(
                            color="black",
                            width=2.4 if is_closest else 0.9,
                        ),
                    ),
                    visible=_initial_visible("Representative"),
                    name=label,
                    legendgroup=label,
                    showlegend=False,
                    hovertemplate=(
                        f"<b>{label}</b><br>"
                        "L*: %{z:.3f}<br>"
                        "a*: %{x:.3f}<br>"
                        "b*: %{y:.3f}<extra></extra>"
                    ),
                )
            )

            trace_idx = len(fig.data) - 1
            layer_indices["Representative"].append(trace_idx)
            color_control_indices.append(trace_idx)

        # ------------------------------------------------------------------
        # Volumes: Core / 0.5-cut / Support.
        # ------------------------------------------------------------------
        volume_sources = {
            "Core": core,
            "0.5-cut": alpha,
            "Support": support,
        }

        for layer_name, prototypes in volume_sources.items():
            if not prototypes:
                continue

            for prototype in prototypes:
                try:
                    proto_label = _safe_label(prototype.label)
                    proto_hex = _prototype_hex_from_lab(prototype.positive)
                except Exception:
                    continue

                vertices, faces = _build_mesh_vertices_and_faces(prototype)

                if vertices is None or faces is None:
                    continue

                fig.add_trace(
                    go.Mesh3d(
                        x=vertices[:, 0],
                        y=vertices[:, 1],
                        z=vertices[:, 2],
                        i=[face[0] for face in faces],
                        j=[face[1] for face in faces],
                        k=[face[2] for face in faces],
                        color=proto_hex,
                        opacity=_initial_opacity(layer_name),
                        visible=_initial_visible(layer_name),
                        name=f"{layer_name}: {proto_label}",
                        legendgroup=proto_label,
                        showlegend=False,
                        hoverinfo="skip",
                        flatshading=False,
                        lighting=dict(
                            ambient=0.58,
                            diffuse=0.72,
                            specular=0.18,
                            roughness=0.82,
                            fresnel=0.08,
                        ),
                        lightposition=dict(
                            x=120,
                            y=160,
                            z=240,
                        ),
                    )
                )

                trace_idx = len(fig.data) - 1
                layer_indices[layer_name].append(trace_idx)
                color_control_indices.append(trace_idx)

        # ------------------------------------------------------------------
        # Optional filtered points.
        # ------------------------------------------------------------------
        def _plot_filtered_points(reference_prototypes):
            if not filtered_points or not reference_prototypes:
                return

            border_colors = px.colors.qualitative.Dark24

            for proto_name, points in filtered_points.items():
                try:
                    proto_idx = int(str(proto_name).split("_")[-1])
                except Exception:
                    continue

                if proto_idx < 0 or proto_idx >= len(reference_prototypes):
                    continue

                prototype = reference_prototypes[proto_idx]

                try:
                    proto_label = _safe_label(prototype.label)
                except Exception:
                    proto_label = f"Prototype {proto_idx}"

                points_inside = []

                for point in points:
                    try:
                        if prototype.voronoi_volume.isInside(Point(*point)):
                            points_inside.append(point)
                    except Exception:
                        continue

                if not points_inside:
                    continue

                pts = np.asarray(points_inside, dtype=float)

                if pts.ndim != 2 or pts.shape[1] < 3:
                    continue

                point_size = max(3, min(8, int(260 / max(len(points_inside), 1))))
                border_color = border_colors[proto_idx % len(border_colors)]

                fig.add_trace(
                    go.Scatter3d(
                        x=pts[:, 1],
                        y=pts[:, 2],
                        z=pts[:, 0],
                        mode="markers",
                        marker=dict(
                            size=point_size,
                            color="black",
                            opacity=0.62,
                            line=dict(color=border_color, width=0.8),
                        ),
                        visible=True,
                        name=f"Filtered: {proto_label}",
                        legendgroup=proto_label,
                        showlegend=False,
                        hovertemplate=(
                            f"<b>Filtered point: {proto_label}</b><br>"
                            "L*: %{z:.3f}<br>"
                            "a*: %{x:.3f}<br>"
                            "b*: %{y:.3f}<extra></extra>"
                        ),
                    )
                )

                color_control_indices.append(len(fig.data) - 1)

        _plot_filtered_points(core or alpha or support)

        # ------------------------------------------------------------------
        # Optional custom color.
        # ------------------------------------------------------------------
        if custom_lab is not None:
            fig.add_trace(
                go.Scatter3d(
                    x=[custom_lab[1]],
                    y=[custom_lab[2]],
                    z=[custom_lab[0]],
                    mode="markers",
                    marker=dict(
                        size=marker_sizes["Custom"],
                        color=custom_hex,
                        symbol="diamond",
                        opacity=1.0,
                        line=dict(color="black", width=1.7),
                    ),
                    name="Custom color",
                    legendgroup="__custom__",
                    showlegend=True,
                    legendrank=10_000,
                    hovertemplate=(
                        "<b>Custom color</b><br>"
                        "L*: %{z:.3f}<br>"
                        "a*: %{x:.3f}<br>"
                        "b*: %{y:.3f}<extra></extra>"
                    ),
                )
            )

        # ------------------------------------------------------------------
        # Optional closest prototype highlight.
        # ------------------------------------------------------------------
        if closest_lab is not None:
            fig.add_trace(
                go.Scatter3d(
                    x=[closest_lab[1]],
                    y=[closest_lab[2]],
                    z=[closest_lab[0]],
                    mode="markers",
                    marker=dict(
                        size=marker_sizes["Closest"],
                        color=closest_hex,
                        symbol="circle",
                        opacity=1.0,
                        line=dict(color="black", width=3.2),
                    ),
                    name=f"Closest: {closest_label}",
                    legendgroup="__closest__",
                    showlegend=True,
                    legendrank=10_001,
                    hovertemplate=(
                        f"<b>Closest: {closest_label}</b><br>"
                        "L*: %{z:.3f}<br>"
                        "a*: %{x:.3f}<br>"
                        "b*: %{y:.3f}<extra></extra>"
                    ),
                )
            )

        # ------------------------------------------------------------------
        # Optional custom-to-closest line.
        # Starts hidden. It can be activated with the Distance line button.
        # ------------------------------------------------------------------
        if has_distance_line:
            fig.add_trace(
                go.Scatter3d(
                    x=[custom_lab[1], closest_lab[1]],
                    y=[custom_lab[2], closest_lab[2]],
                    z=[custom_lab[0], closest_lab[0]],
                    mode="lines",
                    line=dict(
                        color="black",
                        width=4,
                        dash="dash",
                    ),
                    visible="legendonly",
                    name="Custom → closest",
                    legendgroup="__distance__",
                    showlegend=True,
                    legendrank=10_002,
                    hoverinfo="skip",
                )
            )

            layer_indices["Distance line"].append(len(fig.data) - 1)

        # ------------------------------------------------------------------
        # Layer toggle buttons.
        #
        # Important:
        # Layers are controlled with opacity AND visible.
        # Color buttons only change visible, so Select all colors does not
        # reactivate hidden geometry because hidden layers keep opacity = 0.
        # ------------------------------------------------------------------
        layer_button_positions = {
            "Representative": 0.020,
            "Core": 0.155,
            "0.5-cut": 0.220,
            "Support": 0.305,
        }

        layer_menus = []

        for layer_name in layer_names:
            indices = layer_indices.get(layer_name, [])

            if layer_name == "Representative":
                on_update = {
                    "visible": True,
                    "marker.opacity": layer_opacity[layer_name],
                }
                off_update = {
                    "visible": "legendonly",
                    "marker.opacity": 0.0,
                }
            else:
                on_update = {
                    "visible": True,
                    "opacity": layer_opacity[layer_name],
                }
                off_update = {
                    "visible": "legendonly",
                    "opacity": 0.0,
                }

            layer_menus.append(
                dict(
                    type="buttons",
                    direction="right",
                    x=layer_button_positions[layer_name],
                    y=0.915,
                    xanchor="left",
                    yanchor="top",
                    active=0 if layer_name in selected_options else -1,
                    showactive=True,
                    buttons=[
                        dict(
                            label=layer_name,
                            method="restyle",
                            args=[on_update, indices],
                            args2=[off_update, indices],
                        )
                    ],
                    pad=dict(r=1, t=1, b=1),
                )
            )

        # ------------------------------------------------------------------
        # Optional distance line button.
        # ------------------------------------------------------------------
        if has_distance_line:
            layer_menus.append(
                dict(
                    type="buttons",
                    direction="right",
                    x=0.395,
                    y=0.915,
                    xanchor="left",
                    yanchor="top",
                    active=-1,
                    showactive=True,
                    buttons=[
                        dict(
                            label="Distance line",
                            method="restyle",
                            args=[{"visible": True}, layer_indices["Distance line"]],
                            args2=[{"visible": "legendonly"}, layer_indices["Distance line"]],
                        )
                    ],
                    pad=dict(r=1, t=1, b=1),
                )
            )

        # ------------------------------------------------------------------
        # Color visibility buttons.
        #
        # These buttons only modify trace visibility.
        # They do not touch opacity, so they respect Displayed geometry.
        # ------------------------------------------------------------------
        color_buttons = [
            dict(
                label="Select all colors",
                method="restyle",
                args=[{"visible": True}, color_control_indices],
            ),
            dict(
                label="Deselect all colors",
                method="restyle",
                args=[{"visible": "legendonly"}, color_control_indices],
            ),
        ]

        color_menu = dict(
            type="buttons",
            direction="down",
            x=0.805,
            y=0.915,
            xanchor="left",
            yanchor="top",
            active=-1,
            showactive=False,
            buttons=color_buttons,
            pad=dict(r=1, t=1, b=1),
        )

        # ------------------------------------------------------------------
        # Axes ranges.
        # ------------------------------------------------------------------
        xaxis_range = volume_limits.comp2 if volume_limits else None
        yaxis_range = volume_limits.comp3 if volume_limits else None
        zaxis_range = volume_limits.comp1 if volume_limits else None

        # ------------------------------------------------------------------
        # Legend configuration.
        #
        # Compatible with older Plotly versions.
        # Plotly requires itemwidth >= 30.
        # ------------------------------------------------------------------
        legend_config = dict(
            x=0.805,
            y=0.845,
            xanchor="left",
            yanchor="top",
            title=dict(text="Colors"),
            groupclick="togglegroup",
            bgcolor="rgba(255,255,255,0.96)",
            bordercolor="rgba(0,0,0,0.12)",
            borderwidth=1,
            font=dict(size=9, color="#24364f"),
            itemsizing="constant",
            tracegroupgap=0,
        )

        # ------------------------------------------------------------------
        # Layout.
        # ------------------------------------------------------------------
        fig.update_layout(
            title=dict(
                text=title_text,
                x=0.395,
                y=0.992,
                xanchor="center",
                yanchor="top",
                font=dict(
                    size=17,
                    family="Arial, sans-serif",
                    color="#24364f",
                ),
            ),
            scene=dict(
                domain=dict(
                    x=[0.010, 0.790],
                    y=[0.015, 0.885],
                ),
                xaxis=dict(
                    title="a*  (green ↔ red)",
                    range=xaxis_range,
                    backgroundcolor="#f7f8fa",
                    gridcolor="white",
                    zerolinecolor="#c9ced8",
                    showbackground=True,
                    showspikes=False,
                ),
                yaxis=dict(
                    title="b*  (blue ↔ yellow)",
                    range=yaxis_range,
                    backgroundcolor="#f7f8fa",
                    gridcolor="white",
                    zerolinecolor="#c9ced8",
                    showbackground=True,
                    showspikes=False,
                ),
                zaxis=dict(
                    title="L*  (lightness)",
                    range=zaxis_range,
                    backgroundcolor="#f7f8fa",
                    gridcolor="white",
                    zerolinecolor="#c9ced8",
                    showbackground=True,
                    showspikes=False,
                ),
                camera=dict(
                    eye=dict(x=1.55, y=1.65, z=1.18),
                    up=dict(x=0, y=0, z=1),
                ),
                aspectmode="cube",
            ),
            updatemenus=layer_menus + [color_menu],
            annotations=[
                dict(
                    text="<b>Displayed geometry</b>",
                    x=0.020,
                    y=0.948,
                    xref="paper",
                    yref="paper",
                    showarrow=False,
                    xanchor="left",
                    yanchor="top",
                    font=dict(size=12, color="#24364f"),
                ),
                dict(
                    text="<b>Color visibility</b>",
                    x=0.805,
                    y=0.948,
                    xref="paper",
                    yref="paper",
                    showarrow=False,
                    xanchor="left",
                    yanchor="top",
                    font=dict(size=12, color="#24364f"),
                ),
            ],
            legend=legend_config,
            margin=dict(
                l=8,
                r=330,
                b=8,
                t=58,
            ),
            paper_bgcolor="white",
            plot_bgcolor="white",
            hoverlabel=dict(
                bgcolor="white",
                bordercolor="#24364f",
                font=dict(color="#24364f"),
            ),
        )

        return fig


    @staticmethod
    def plot_color_evaluation_ab_projection(
        color_data,
        hex_color,
        custom_lab=None,
        custom_hex="#ff0000",
        closest_label=None,
        closest_lab=None,
        closest_hex="#000000",
        filename="Color evaluation",
    ):
        """
        2D a*b* projection with all prototypes.

        Works with or without a custom/sample color.
        If custom and closest colors are available, they are highlighted and connected.
        """
        fig = go.Figure()

        color_data = color_data or {}
        custom_lab = VisualManager._safe_lab(custom_lab)
        closest_lab = VisualManager._safe_lab(closest_lab)

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

        if custom_lab is not None:
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
                    hovertemplate=(
                        "<b>Custom color</b><br>"
                        "a*: %{x:.3f}<br>"
                        "b*: %{y:.3f}<extra></extra>"
                    ),
                )
            )

        if closest_lab is not None:
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

        if custom_lab is not None and closest_lab is not None:
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
    def plot_color_evaluation_lc_projection(
        color_data,
        hex_color,
        custom_lab=None,
        custom_hex="#ff0000",
        closest_label=None,
        closest_lab=None,
        closest_hex="#000000",
        filename="Color evaluation",
    ):
        """
        2D L*C* projection.

        Shows lightness L* versus chroma C* for all prototypes.
        Works with or without a custom/sample color.
        """
        fig = go.Figure()

        color_data = color_data or {}
        custom_lab = VisualManager._safe_lab(custom_lab)
        closest_lab = VisualManager._safe_lab(closest_lab)

        for label, value in color_data.items():
            try:
                lab = np.asarray(value["positive_prototype"], dtype=float).reshape(-1)[:3]
                L, C, _h = VisualManager._lab_to_lch(lab)
            except Exception:
                continue

            proto_hex = VisualManager._find_hex_for_lab(lab, hex_color, default="#000000")

            fig.add_trace(
                go.Scatter(
                    x=[C],
                    y=[L],
                    mode="markers",
                    marker=dict(
                        size=10,
                        color=proto_hex,
                        line=dict(color="black", width=1),
                    ),
                    name=str(label),
                    legendgroup=str(label),
                    showlegend=True,
                    hovertemplate=(
                        f"<b>{label}</b><br>"
                        "C*: %{x:.3f}<br>"
                        "L*: %{y:.3f}<extra></extra>"
                    ),
                )
            )

        if custom_lab is not None:
            L, C, _h = VisualManager._lab_to_lch(custom_lab)

            fig.add_trace(
                go.Scatter(
                    x=[C],
                    y=[L],
                    mode="markers",
                    marker=dict(
                        size=15,
                        color=custom_hex,
                        symbol="diamond",
                        line=dict(color="black", width=2),
                    ),
                    name="Custom color",
                    showlegend=True,
                    hovertemplate=(
                        "<b>Custom color</b><br>"
                        "C*: %{x:.3f}<br>"
                        "L*: %{y:.3f}<extra></extra>"
                    ),
                )
            )

        if closest_lab is not None:
            L, C, _h = VisualManager._lab_to_lch(closest_lab)

            fig.add_trace(
                go.Scatter(
                    x=[C],
                    y=[L],
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
                        "C*: %{x:.3f}<br>"
                        "L*: %{y:.3f}<extra></extra>"
                    ),
                )
            )

        if custom_lab is not None and closest_lab is not None:
            L1, C1, _h1 = VisualManager._lab_to_lch(custom_lab)
            L2, C2, _h2 = VisualManager._lab_to_lch(closest_lab)

            fig.add_trace(
                go.Scatter(
                    x=[C1, C2],
                    y=[L1, L2],
                    mode="lines",
                    line=dict(color="black", width=2),
                    name="Custom → closest",
                    showlegend=True,
                    hoverinfo="skip",
                )
            )

        fig.update_layout(
            title=dict(text=f"{filename} | L*C* projection", x=0.5),
            xaxis_title="C* (Chroma)",
            yaxis_title="L* (Lightness)",
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
        fig.update_yaxes(range=[0, 100], zeroline=True, zerolinewidth=1, zerolinecolor="gray")

        return fig


    @staticmethod
    def plot_color_evaluation_lch_polar(
        color_data,
        hex_color,
        custom_lab=None,
        custom_hex="#ff0000",
        closest_label=None,
        closest_lab=None,
        closest_hex="#000000",
        filename="Color evaluation",
    ):
        """
        Polar LCh plot.

        Angle = hue h°
        Radius = chroma C*
        Marker hover includes L*.
        Works with or without a custom/sample color.
        """
        fig = go.Figure()

        color_data = color_data or {}
        custom_lab = VisualManager._safe_lab(custom_lab)
        closest_lab = VisualManager._safe_lab(closest_lab)

        for label, value in color_data.items():
            try:
                lab = np.asarray(value["positive_prototype"], dtype=float).reshape(-1)[:3]
                L, C, h = VisualManager._lab_to_lch(lab)
            except Exception:
                continue

            proto_hex = VisualManager._find_hex_for_lab(lab, hex_color, default="#000000")

            fig.add_trace(
                go.Scatterpolar(
                    r=[C],
                    theta=[h],
                    mode="markers",
                    marker=dict(
                        size=10,
                        color=proto_hex,
                        line=dict(color="black", width=1),
                    ),
                    name=str(label),
                    legendgroup=str(label),
                    showlegend=True,
                    hovertemplate=(
                        f"<b>{label}</b><br>"
                        "h°: %{theta:.2f}<br>"
                        "C*: %{r:.3f}<br>"
                        f"L*: {L:.3f}<extra></extra>"
                    ),
                )
            )

        if custom_lab is not None:
            L, C, h = VisualManager._lab_to_lch(custom_lab)

            fig.add_trace(
                go.Scatterpolar(
                    r=[C],
                    theta=[h],
                    mode="markers",
                    marker=dict(
                        size=15,
                        color=custom_hex,
                        symbol="diamond",
                        line=dict(color="black", width=2),
                    ),
                    name="Custom color",
                    showlegend=True,
                    hovertemplate=(
                        "<b>Custom color</b><br>"
                        "h°: %{theta:.2f}<br>"
                        "C*: %{r:.3f}<br>"
                        f"L*: {L:.3f}<extra></extra>"
                    ),
                )
            )

        if closest_lab is not None:
            L, C, h = VisualManager._lab_to_lch(closest_lab)

            fig.add_trace(
                go.Scatterpolar(
                    r=[C],
                    theta=[h],
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
                        "h°: %{theta:.2f}<br>"
                        "C*: %{r:.3f}<br>"
                        f"L*: {L:.3f}<extra></extra>"
                    ),
                )
            )

        fig.update_layout(
            title=dict(text=f"{filename} | LCh hue/chroma", x=0.5),
            polar=dict(
                radialaxis=dict(title="C*"),
                angularaxis=dict(direction="counterclockwise", rotation=0),
            ),
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

        return fig


    @staticmethod
    def plot_color_evaluation_top7_bar(
        ranking,
        metric_name="CIEDE2000",
        title="Top 7 closest prototypes",
    ):
        """
        Horizontal bar chart for the closest 7 prototypes.

        Ranking items may contain:
            - metric_value
            - delta_e
        """
        ranking = ranking or []
        ranking = ranking[:7]

        labels = []
        values = []

        for item in ranking:
            try:
                labels.append(str(item["label"]))
                values.append(float(VisualManager._get_ranking_metric_value(item)))
            except Exception:
                continue

        fig = go.Figure()

        fig.add_trace(
            go.Bar(
                x=values[::-1],
                y=labels[::-1],
                orientation="h",
                text=[
                    VisualManager._format_metric_value(v, metric_name)
                    for v in values[::-1]
                ],
                textposition="auto",
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    + metric_name
                    + ": %{x:.3f}<extra></extra>"
                ),
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


    @staticmethod
    def plot_color_evaluation_component_differences(
        components,
        title="Component differences",
    ):
        """
        Bar chart for signed component differences.

        Expected keys:
            ΔL*, Δa*, Δb*, ΔC*, Δh°, ΔH*
        """
        components = components or {}

        keys = ["ΔL*", "Δa*", "Δb*", "ΔC*", "Δh°", "ΔH*"]
        values = []

        for key in keys:
            try:
                values.append(float(components.get(key, 0.0)))
            except Exception:
                values.append(0.0)

        fig = go.Figure()

        fig.add_trace(
            go.Bar(
                x=keys,
                y=values,
                text=[f"{v:+.3f}" for v in values],
                textposition="auto",
                hovertemplate="<b>%{x}</b><br>Value: %{y:+.3f}<extra></extra>",
            )
        )

        fig.update_layout(
            title=dict(text=title, x=0.5),
            xaxis_title="Component",
            yaxis_title="Signed difference",
            margin=dict(l=60, r=30, t=55, b=55),
        )

        fig.update_yaxes(zeroline=True, zerolinewidth=1, zerolinecolor="gray")

        return fig
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from matplotlib.colors import to_rgba
import plotly.graph_objects as go
import plotly.express as px

# Project modules
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
    # Shared legend setting for plot traces.
    SHOW_LEGENDS = True

    # Geometry / Color Helpers

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

        # Clamp vertices for display; this does not close clipped polytopes.
        return np.clip(vertices_array, lower_bounds, upper_bounds)


    @staticmethod
    def display_polygons_for_volume(volume, domain, include_domain_caps=True):
        """Clip a fuzzy polyhedron to the view domain, without changing its geometry.

        This is VISUAL geometry only: the real fuzzy halfspaces are clipped
        against the display domain, including the resulting closing faces.
        Those domain caps are essential to display closed Core / Voronoi /
        Support volumes.  They do not become membership boundaries: the fuzzy
        engine continues to ignore domain faces during radial membership.

        For diagnostic use, include_domain_caps=False yields open surfaces.
        """
        from Source.geometry.Voronoi import Voronoi

        eps = Voronoi.DEFAULT_EPS
        merge_eps = Voronoi.DEFAULT_MERGE_EPS
        faces = Voronoi._create_domain_faces(domain)
        rep = volume.getRepresentative()
        for face in volume.getFaces():
            if face.isDomainBoundary():
                continue
            plane = face.getPlane()
            normal = np.array([plane.A, plane.B, plane.C], dtype=float)
            offset = float(plane.D)
            length = float(np.linalg.norm(normal))
            if length <= eps:
                continue
            # All clip planes must point towards the representative.
            if float(np.dot(normal, [rep.x,rep.y,rep.z]) + offset) < 0:
                normal = -normal
                offset = -offset
            normal /= length
            offset /= length
            vertices = Voronoi._collect_vertices(faces)
            if len(vertices) == 0:
                return []
            if np.min(vertices @ normal + offset) >= -eps:
                continue
            faces = Voronoi._clip_polyhedron(
                faces, normal, offset, face.getSourceIndex(), eps, merge_eps)
            if not faces:
                return []
        return [np.asarray(face.vertices, dtype=float)
                for face in faces
                if face.vertices is not None and len(face.vertices) >= 3
                and (include_domain_caps or not face.is_domain_boundary)]

    @staticmethod
    def _cached_display_polygons(prototype, domain):
        """Reuse the expensive plane/domain intersection between plot backends.

        Geometry is rebuilt with a new volume on ordinary model updates.  The
        plane coefficients in the key also catch in-place support corrections.
        """
        volume = prototype.voronoi_volume
        limits = (tuple(domain.comp1), tuple(domain.comp2), tuple(domain.comp3))
        planes = tuple((float(f.getPlane().A), float(f.getPlane().B),
                        float(f.getPlane().C), float(f.getPlane().D),
                        bool(f.isDomainBoundary())) for f in volume.getFaces())
        key = (id(volume), limits, planes)
        cached = getattr(prototype, "_cached_visible_fuzzy_surfaces", None)
        if cached is not None and cached[0] == key:
            return cached[1]
        # Render the complete CLIPPED polyhedron (including caps at RGB/LAB
        # domain edges).  This does not affect the membership geometry.
        polygons = VisualManager.display_polygons_for_volume(
            volume, domain, include_domain_caps=True)
        prototype._cached_visible_fuzzy_surfaces = (key, polygons)
        return polygons

    @staticmethod
    def _cached_projected_display_faces(prototype, domain, source_space,
                                       display_space):
        """Return view-space polygons in plotting axis order (y,z,x).

        Avoid repeated LAB/RGB conversions on every Matplotlib redraw, and
        share projections with the optional Plotly Interactive View.
        """
        polygons = VisualManager._cached_display_polygons(prototype, domain)
        source_space = str(source_space).upper()
        display_space = str(display_space).upper()
        old = getattr(prototype, "_cached_projected_fuzzy_surfaces", None)
        if (old is not None and old[0] is polygons
                and old[1] == source_space and old[2] == display_space):
            return old[3]
        if polygons:
            lengths = [len(polygon) for polygon in polygons]
            combined = np.concatenate(polygons, axis=0)
            converted = VisualManager.reproject_points(
                combined, source_space, display_space)[:, [1, 2, 0]]
            stops = np.cumsum(lengths)[:-1]
            result = np.split(converted, stops)
        else:
            result = []
        prototype._cached_projected_fuzzy_surfaces = (
            polygons, source_space, display_space, result)
        return result


    @staticmethod
    def _cached_plotly_display_mesh(prototype, domain, source_space,
                                    display_space):
        """Triangulate each visible polygon once, without duplicating triangles' vertices.

        Keep separate vertices for separate faces. Apart from saving work and
        reducing the serialized Mesh3d arrays, this preserves the per-face
        appearance (no vertex sharing between neighbouring faces).
        """
        polygons = VisualManager._cached_projected_display_faces(
            prototype, domain, source_space, display_space)
        previous = getattr(prototype, "_cached_plotly_visible_mesh", None)
        if previous is not None and previous[0] is polygons:
            return previous[1]

        vertices = []
        i_indices = []
        j_indices = []
        k_indices = []
        for polygon in polygons:
            n = len(polygon)
            if n < 3:
                continue
            first = len(vertices)
            vertices.extend(polygon)
            for corner in range(1, n - 1):
                i_indices.append(first)
                j_indices.append(first + corner)
                k_indices.append(first + corner + 1)

        if not i_indices:
            mesh = None
        else:
            mesh = (np.asarray(vertices, dtype=float),
                    i_indices, j_indices, k_indices)
        prototype._cached_plotly_visible_mesh = (polygons, mesh)
        return mesh


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


    @staticmethod
    def valid_projection_request(points, source_space="LAB", display_space="LAB"):
        """Return False for unsupported modes or non-finite/non-3D coordinates."""
        if (str(source_space).strip().upper() not in ("LAB", "RGB") or
                str(display_space).strip().upper() not in ("LAB", "RGB")):
            return False
        try:
            matrix = np.asarray(points, dtype=float)
        except (ValueError, TypeError):
            return False
        return (matrix.ndim >= 1 and matrix.shape[-1] == 3
                and bool(np.all(np.isfinite(matrix))))

    @staticmethod
    def reproject_points(points, source_space="LAB", display_space="LAB"):
        """Reproject ONLY 3D visualization coordinates, never membership geometry.

        CIELAB -> sRGB is gamut-clipped, so transformed polygons approximate
        the geometric surface (they are not new Voronoi polytopes in sRGB).
        """
        from skimage import color as skcolor

        src = str(source_space).strip().upper()
        dst = str(display_space).strip().upper()
        if src not in ("LAB", "RGB") or dst not in ("LAB", "RGB"):
            raise ValueError("Visualization supports LAB and RGB only.")
        arr = np.asarray(points, dtype=float)
        if arr.shape[-1] != 3 or not np.all(np.isfinite(arr)):
            raise ValueError("Color coordinates must be finite triplets.")
        if src == dst:
            return arr.copy()
        original_shape = arr.shape
        matrix = arr.reshape(-1, 3)
        with np.errstate(invalid="ignore", over="ignore", under="ignore"):
            if src == "LAB":
                # Out-of-gamut LAB vertices occur in clipped reference domains.
                # They are intentionally clipped for display; never change
                # the stored model or its membership calculations.
                import warnings
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=UserWarning,
                                             message="Conversion from CIE-LAB.*")
                    out = skcolor.lab2rgb(matrix.reshape(-1, 1, 3)).reshape(-1, 3)
                out = np.clip(out * 255.0, 0.0, 255.0)
            else:
                out = skcolor.rgb2lab(
                    np.clip(matrix, 0, 255).reshape(-1, 1, 3) / 255.0
                ).reshape(-1, 3)
        if not np.all(np.isfinite(out)):
            raise ValueError("Color coordinates cannot be displayed in this space.")
        return out.reshape(original_shape)

    @staticmethod
    def display_limits(volume_limits, source_space="LAB", display_space="LAB"):
        if str(source_space).upper() == str(display_space).upper():
            return volume_limits
        from Source.colorspace.ReferenceDomain import ReferenceDomain
        return ReferenceDomain.for_color_space(display_space)

    # Embedded Matplotlib 3D Model

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
        color_space="LAB",
        display_color_space=None,
    ):
        """
        Draw the complete 3D model on an existing Axes3D instance.

        This function reuses the provided axis instead of creating a new figure
        every time. That makes repeated updates much cheaper.
        """
        ax.cla()
        display_color_space = (display_color_space or color_space).upper()
        target_limits = VisualManager.display_limits(volume_limits, color_space, display_color_space)
        to_display = lambda xyz: VisualManager.reproject_points(xyz, color_space, display_color_space)

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

        # Representative points
        if "Representative" in selected_options and isinstance(color_data, dict):
            lab_values = [value["positive_prototype"] for value in color_data.values()]

            if lab_values:
                lab_array = to_display(np.asarray(lab_values, dtype=float))

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

        # Sort the surfaces from ALL selected layers together.  Separate
        # transparent Poly3DCollections are sorted as whole objects by mplot3d;
        # with nested Core / 0.5-cut / Support volumes this produces the odd
        # dark patches that depend on the camera angle. One collection allows
        # face-by-face depth sorting and per-layer alpha values.
        active_layers = [name for name in ("Core", "0.5-cut", "Support")
                         if name in selected_options and data_map.get(name)]
        all_faces = []
        all_facecolors = []
        all_edgecolors = []
        filtered_coords = []
        multiple_layers = len(active_layers) > 1
        primary_layer = active_layers[0] if active_layers else None
        solo_alpha = {"Core": 0.38, "0.5-cut": 0.30, "Support": 0.18}
        # Keep the inner layer legible but make outer translucent shells much
        # lighter when more than one nested volume is selected.
        nested_alpha = {"Core": 0.34, "0.5-cut": 0.18, "Support": 0.07}

        for option in active_layers:
            prototypes = data_map[option]
            opacity = (solo_alpha[option] if not multiple_layers
                       else (nested_alpha[option] if option == primary_layer
                             else nested_alpha[option] * 0.80))
            # The real clipping caps MUST remain in the visible geometry;
            # otherwise the domain-bounded volumes appear open or triangular.
            # Their rendering never changes the functional membership faces.
            for prototype in prototypes:
                color = inverse_hex_color.get(
                    lab_to_key(prototype.positive), "#000000")
                valid_faces = VisualManager._cached_projected_display_faces(
                    prototype, volume_limits, color_space, display_color_space)
                # The same material is applied to every polygon of a given
                # prototype/layer. Prepare it once rather than per face.
                face_rgba = to_rgba(color, opacity)
                edge_alpha = (0.34 if option == primary_layer else 0.16)
                if not multiple_layers:
                    edge_alpha = 0.48 if option == "Core" else 0.38
                edge_rgba = (0.08, 0.08, 0.08, edge_alpha)
                all_faces.extend(valid_faces)
                all_facecolors.extend([face_rgba] * len(valid_faces))
                all_edgecolors.extend([edge_rgba] * len(valid_faces))

                if filtered_points_arrays:
                    for points_array in filtered_points_arrays.values():
                        if len(points_array) == 0:
                            continue
                        filtered_coords.extend(
                            point for point in points_array
                            if prototype.voronoi_volume.isInside(Point(*point)))

        if all_faces:
            ax.add_collection3d(
                Poly3DCollection(
                    all_faces,
                    facecolors=all_facecolors,
                    edgecolors=all_edgecolors,
                    linewidths=0.26 if multiple_layers else 0.34,
                    zsort="average",
                )
            )

        if filtered_coords:
            points_array = to_display(np.asarray(filtered_coords, dtype=float))
            ax.scatter(points_array[:, 1], points_array[:, 2], points_array[:, 0],
                       c="red", marker="o", s=10, alpha=0.8,
                       depthshade=False)

        if str(display_color_space).upper() == "RGB":
            ax.set_xlabel("G (Green)", fontsize=10, labelpad=10)
            ax.set_ylabel("B (Blue)", fontsize=10, labelpad=10)
            ax.set_zlabel("R (Red)", fontsize=10, labelpad=10)
        else:
            ax.set_xlabel("a* (Green-Red)", fontsize=10, labelpad=10)
            ax.set_ylabel("b* (Blue-Yellow)", fontsize=10, labelpad=10)
            ax.set_zlabel("L* (Lightness)", fontsize=10, labelpad=10)

        if target_limits:
            ax.set_xlim(target_limits.comp2)
            ax.set_ylim(target_limits.comp3)
            ax.set_zlim(target_limits.comp1)

        # The embedding UI owns the title/subtitle styling and positioning.
        ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.7)

        try:
            ax.set_box_aspect((1, 1, 1))
        except Exception:
            pass

        fig = ax.get_figure()
        if str(display_color_space).upper() == "LAB":
            VisualManager.draw_orientation_inset(fig, ax)
        else:
            for existing_ax in list(fig.axes):
                if hasattr(existing_ax, "_is_orientation_inset"):
                    fig.delaxes(existing_ax)


    @staticmethod
    def draw_orientation_inset(fig, ax_main=None):
        """
        Draw a fixed-position 3D orientation inset with a fixed camera,
        independent from the main axes.
        """
        # The inset has a fixed camera and fixed labels; it is independent
        # of the currently displayed fuzzy geometry. Reuse it across option
        # changes instead of deleting and redrawing six 3D arrows each time.
        for existing_ax in fig.axes:
            if hasattr(existing_ax, "_is_orientation_inset"):
                return existing_ax

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


    # General Interactive Plotly 3D Model

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
        color_space="LAB",
        display_color_space=None,
    ):
        """
        Generate a unified interactive Plotly 3D figure.

        Features
        --------
        - Representative / Core / 0.5-cut / Support can be toggled independently.
        - Several volume layers can be superimposed at once.
        - Select/Deselect all colors respects the currently displayed geometry.
        - Optional custom/sample color is drawn as a smaller diamond.
        - Optional closest prototype is highlighted.
        - Optional custom-to-closest distance line can be toggled with a button.
        - Layout adapts its height when many colors are shown.
        """

        fig = go.Figure()
        display_color_space = (display_color_space or color_space).upper()
        target_limits = VisualManager.display_limits(volume_limits, color_space, display_color_space)
        to_display = lambda xyz: VisualManager.reproject_points(xyz, color_space, display_color_space)

        color_data = color_data or {}
        selected_options = selected_options or ["Representative"]

        title_text = str(filename).split("|")[0].strip()

        # Normalize layer names.
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

        # Resolve the comparison prototype from its label or LAB distance.
        if custom_lab is not None and closest_lab is None:
            # Try to recover closest_lab from closest_label.
            if closest_label is not None:
                for label, value in color_data.items():
                    if str(label) != str(closest_label):
                        continue

                    try:
                        inferred_lab = np.asarray(
                            value["positive_prototype"],
                            dtype=float
                        ).reshape(-1)[:3]

                        closest_lab = inferred_lab
                        closest_hex = VisualManager._find_hex_for_lab(
                            closest_lab,
                            hex_color,
                            default=closest_hex,
                        )
                        break
                    except Exception:
                        continue

            # If closest_label was not available or did not match, compute closest LAB point.
            if closest_lab is None:
                best_label = None
                best_lab = None
                best_hex = closest_hex
                best_distance = float("inf")

                for label, value in color_data.items():
                    try:
                        lab = np.asarray(
                            value["positive_prototype"],
                            dtype=float
                        ).reshape(-1)[:3]

                        distance = float(np.linalg.norm(custom_lab - lab))

                        if distance < best_distance:
                            best_distance = distance
                            best_label = str(label)
                            best_lab = lab
                            best_hex = VisualManager._find_hex_for_lab(
                                lab,
                                hex_color,
                                default=closest_hex,
                            )
                    except Exception:
                        continue

                if best_lab is not None:
                    closest_label = best_label
                    closest_lab = best_lab
                    closest_hex = best_hex

        has_distance_line = custom_lab is not None and closest_lab is not None

        # Dynamic figure height.
        # Scale figure height with the number of legend entries.
        n_colors = len(color_data)
        figure_height = max(760, min(1250, 520 + n_colors * 15))

        layer_names = ("Representative", "Core", "0.5-cut", "Support")

        layer_opacity = {
            "Representative": 0.96,
            "Core": 0.42,
            "0.5-cut": 0.26,
            "Support": 0.16,
        }
        active_volumes = [name for name in ("Core", "0.5-cut", "Support")
                          if name in selected_options]
        if len(active_volumes) > 1:
            # Plotly also has transparency-ordering limitations with nested
            # Mesh3d traces; avoid opaque-looking stacked shells.
            soft_opacity = {"Core": 0.34, "0.5-cut": 0.15, "Support": 0.055}
            for name in active_volumes:
                layer_opacity[name] = (soft_opacity[name] if name == active_volumes[0]
                                       else soft_opacity[name] * 0.8)

        marker_sizes = {
            "Representative": 5.8,
            "Custom": 6.4,
            "Closest": 6.4,
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

        # The plot draws the same prototypes in several layers. Resolve the
        # representative-to-HEX lookup once instead of scanning the palette
        # for every marker and every mesh. Retain the first-match semantics.
        hex_lookup = {}
        if isinstance(hex_color, dict):
            for candidate_hex, candidate_value in hex_color.items():
                try:
                    hex_lookup.setdefault(VisualManager._lab_key(candidate_value),
                                          candidate_hex)
                except (ValueError, TypeError):
                    continue

        def _prototype_hex_from_lab(lab):
            return hex_lookup.get(VisualManager._lab_key(lab), "#000000")

        def _safe_label(value):
            try:
                return str(value)
            except Exception:
                return "Prototype"

        def _initial_opacity(layer_name):
            return layer_opacity[layer_name] if layer_name in selected_options else 0.0

        def _add_legend_anchor(label, proto_hex, rank):
            """
            Add one visible legend item per prototype.

            These dummy traces carry the legend entries. The real geometry traces
            share the same legendgroup but do not appear separately in the legend.
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
                        line=dict(color="black", width=0.8),
                    ),
                    opacity=1.0,
                    visible=True,
                    name=label,
                    legendgroup=label,
                    showlegend=True,
                    legendrank=rank,
                    hoverinfo="skip",
                )
            )

            trace_idx = len(fig.data) - 1
            color_control_indices.append(trace_idx)
            legend_labels_added.add(label)

        # Legend anchors first.
        for rank, (label, value) in enumerate(color_data.items()):
            try:
                lab = np.asarray(value["positive_prototype"], dtype=float).reshape(-1)[:3]
            except Exception:
                continue

            proto_hex = _prototype_hex_from_lab(lab)
            _add_legend_anchor(label, proto_hex, rank)

        # Representative points.
        for label, value in color_data.items():
            try:
                lab = np.asarray(value["positive_prototype"], dtype=float).reshape(-1)[:3]
            except Exception:
                continue

            label = _safe_label(label)
            proto_hex = _prototype_hex_from_lab(lab)

            is_closest = closest_label is not None and label == str(closest_label)
            shown = to_display(lab)

            fig.add_trace(
                go.Scatter3d(
                    x=[shown[1]],
                    y=[shown[2]],
                    z=[shown[0]],
                    mode="markers",
                    marker=dict(
                        size=7.6 if is_closest else marker_sizes["Representative"],
                        color=proto_hex,
                        line=dict(
                            color="black",
                            width=2.4 if is_closest else 0.9,
                        ),
                    ),
                    opacity=_initial_opacity("Representative"),
                    visible=True,
                    name=label,
                    legendgroup=label,
                    showlegend=False,
                    hovertemplate=(
                        f"<b>{label}</b><br>"
                        + ("R: %{z:.2f}<br>G: %{x:.2f}<br>B: %{y:.2f}<extra></extra>"
                           if display_color_space == "RGB" else
                           "L*: %{z:.3f}<br>a*: %{x:.3f}<br>b*: %{y:.3f}<extra></extra>")
                    ),
                )
            )

            trace_idx = len(fig.data) - 1
            layer_indices["Representative"].append(trace_idx)
            color_control_indices.append(trace_idx)

        # Volumes: Core / 0.5-cut / Support.
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

                try:
                    mesh = VisualManager._cached_plotly_display_mesh(
                        prototype, volume_limits, color_space, display_color_space)
                except (ValueError, TypeError, ArithmeticError):
                    continue
                if mesh is None:
                    continue
                vertices, i_indices, j_indices, k_indices = mesh

                fig.add_trace(
                    go.Mesh3d(
                        x=vertices[:, 0],
                        y=vertices[:, 1],
                        z=vertices[:, 2],
                        i=i_indices,
                        j=j_indices,
                        k=k_indices,
                        color=proto_hex,
                        opacity=_initial_opacity(layer_name),
                        visible=True,
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

        # Optional filtered points.
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

                pts = to_display(np.asarray(points_inside, dtype=float))

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
                            line=dict(color=border_color, width=0.8),
                        ),
                        opacity=0.62,
                        visible=True,
                        name=f"Filtered: {proto_label}",
                        legendgroup=proto_label,
                        showlegend=False,
                        hovertemplate=(
                            f"<b>Filtered point: {proto_label}</b><br>" +
                            ("R: %{z:.2f}<br>G: %{x:.2f}<br>B: %{y:.2f}<extra></extra>"
                             if display_color_space == "RGB" else
                             "L*: %{z:.3f}<br>a*: %{x:.3f}<br>b*: %{y:.3f}<extra></extra>")
                        ),
                    )
                )

                color_control_indices.append(len(fig.data) - 1)

        _plot_filtered_points(core or alpha or support)

        if closest_lab is not None:
            closest_lab = to_display(closest_lab)
        if custom_lab is not None:
            custom_lab = to_display(custom_lab)
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
                        line=dict(color="black", width=1.7),
                    ),
                    opacity=1.0,
                    visible=True,
                    name="Custom color",
                    legendgroup="__custom__",
                    showlegend=True,
                    legendrank=10_000,
                    hovertemplate=(
                        "<b>Custom color</b><br>"
                        + ("R: %{z:.2f}<br>G: %{x:.2f}<br>B: %{y:.2f}<extra></extra>"
                           if display_color_space == "RGB" else
                           "L*: %{z:.3f}<br>a*: %{x:.3f}<br>b*: %{y:.3f}<extra></extra>")
                    ),
                )
            )

        # Optional closest prototype highlight.
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
                        line=dict(color="black", width=3.2),
                    ),
                    opacity=1.0,
                    visible=True,
                    name=f"Closest: {closest_label}",
                    legendgroup="__closest__",
                    showlegend=True,
                    legendrank=10_001,
                    hovertemplate=(
                        f"<b>Closest: {closest_label}</b><br>"
                        + ("R: %{z:.2f}<br>G: %{x:.2f}<br>B: %{y:.2f}<extra></extra>"
                           if display_color_space == "RGB" else
                           "L*: %{z:.3f}<br>a*: %{x:.3f}<br>b*: %{y:.3f}<extra></extra>")
                    ),
                )
            )

        # Optional custom-to-closest line.
        # It appears active by default.
        # The user can still click it in the legend to show/hide it.
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
                    opacity=1.0,
                    visible=True,
                    name=f"Custom → closest line ({closest_label})",
                    legendgroup="__distance__",
                    showlegend=True,
                    legendrank=10_002,
                    hoverinfo="skip",
                )
            )

            layer_indices["Distance line"].append(len(fig.data) - 1)

        # Displayed geometry buttons.
        # Layer controls change opacity; hidden layers remain hidden on Select All.
        layer_button_positions = {
            "Representative": 0.020,
            "Core": 0.150,
            "0.5-cut": 0.210,
            "Support": 0.290,
        }

        layer_menus = []

        for layer_name in layer_names:
            indices = layer_indices.get(layer_name, [])

            layer_menus.append(
                dict(
                    type="buttons",
                    direction="right",
                    x=layer_button_positions[layer_name],
                    y=0.925,
                    xanchor="left",
                    yanchor="top",
                    active=0 if layer_name in selected_options else -1,
                    showactive=True,
                    buttons=[
                        dict(
                            label=layer_name,
                            method="restyle",
                            args=[{"opacity": layer_opacity[layer_name]}, indices],
                            args2=[{"opacity": 0.0}, indices],
                        )
                    ],
                    pad=dict(r=1, t=1, b=1),
                )
            )

        # Color visibility buttons.
        # Color visibility controls retain each layer's current opacity.
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
            x=0.992,
            y=0.925,
            xanchor="right",
            yanchor="top",
            active=-1,
            showactive=False,
            buttons=color_buttons,
            pad=dict(r=1, t=1, b=1),
        )

        xaxis_range = target_limits.comp2 if target_limits else None
        yaxis_range = target_limits.comp3 if target_limits else None
        zaxis_range = target_limits.comp1 if target_limits else None

        # Legend.
        # Keep the legend at the right edge without version-specific size options.
        legend_config = dict(
            x=0.992,
            y=0.790,
            xanchor="right",
            yanchor="top",
            title=dict(text="Colors"),
            groupclick="togglegroup",
            bgcolor="rgba(255,255,255,0.96)",
            bordercolor="rgba(0,0,0,0.12)",
            borderwidth=1,
            font=dict(size=9, color="#3F374C"),
            itemsizing="constant",
            tracegroupgap=0,
        )

        layout_annotations = [
            dict(
                text="<b>Color visibility</b>",
                x=0.992,
                y=0.955,
                xref="paper",
                yref="paper",
                showarrow=False,
                xanchor="right",
                yanchor="top",
                font=dict(size=12, color="#3F374C"),
            ),
        ]

        fig.update_layout(
            height=figure_height,
            title=dict(
                text=title_text,
                x=0.385,
                y=0.990,
                xanchor="center",
                yanchor="top",
                font=dict(
                    size=17,
                    family="Arial, sans-serif",
                    color="#3F374C",
                ),
            ),
            scene=dict(
                domain=dict(
                    x=[0.005, 0.765],
                    y=[0.015, 0.895],
                ),
                xaxis=dict(
                    title=("G (Green)" if display_color_space == "RGB" else "a*  (green ↔ red)"),
                    range=xaxis_range,
                    backgroundcolor="#f7f8fa",
                    gridcolor="white",
                    zerolinecolor="#c9ced8",
                    showbackground=True,
                    showspikes=False,
                ),
                yaxis=dict(
                    title=("B (Blue)" if display_color_space == "RGB" else "b*  (blue ↔ yellow)"),
                    range=yaxis_range,
                    backgroundcolor="#f7f8fa",
                    gridcolor="white",
                    zerolinecolor="#c9ced8",
                    showbackground=True,
                    showspikes=False,
                ),
                zaxis=dict(
                    title=("R (Red)" if display_color_space == "RGB" else "L*  (lightness)"),
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
                    projection=dict(type="orthographic"),
                ),
                aspectmode="cube",
            ),
            updatemenus=layer_menus + [color_menu],
            annotations=layout_annotations,
            legend=legend_config,
            margin=dict(
                l=8,
                r=8,
                b=8,
                t=58,
            ),
            paper_bgcolor="white",
            plot_bgcolor="white",
            hoverlabel=dict(
                bgcolor="white",
                bordercolor="#3F374C",
                font=dict(color="#3F374C"),
            ),
        )

        if str(color_space).upper() == "RGB":
            for trace in fig.data:
                tmpl = getattr(trace, "hovertemplate", None)
                if isinstance(tmpl, str):
                    trace.hovertemplate = (tmpl.replace("L*:", "R:")
                                               .replace("a*:", "G:")
                                               .replace("b*:", "B:"))

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
        The default interaction mode is pan instead of zoom.
        """
        fig = go.Figure()

        color_data = color_data or {}
        custom_lab = VisualManager._safe_lab(custom_lab)
        closest_lab = VisualManager._safe_lab(closest_lab)

        # Resolve the comparison prototype from its label or LAB distance.
        if custom_lab is not None and closest_lab is None:
            if closest_label is not None:
                for label, value in color_data.items():
                    if str(label) != str(closest_label):
                        continue

                    try:
                        inferred_lab = np.asarray(
                            value["positive_prototype"],
                            dtype=float
                        ).reshape(-1)[:3]

                        closest_lab = inferred_lab
                        closest_hex = VisualManager._find_hex_for_lab(
                            closest_lab,
                            hex_color,
                            default=closest_hex,
                        )
                        break
                    except Exception:
                        continue

            if closest_lab is None:
                best_label = None
                best_lab = None
                best_hex = closest_hex
                best_distance = float("inf")

                for label, value in color_data.items():
                    try:
                        lab = np.asarray(
                            value["positive_prototype"],
                            dtype=float
                        ).reshape(-1)[:3]

                        distance = float(np.linalg.norm(custom_lab - lab))

                        if distance < best_distance:
                            best_distance = distance
                            best_label = str(label)
                            best_lab = lab
                            best_hex = VisualManager._find_hex_for_lab(
                                lab,
                                hex_color,
                                default=closest_hex,
                            )
                    except Exception:
                        continue

                if best_lab is not None:
                    closest_label = best_label
                    closest_lab = best_lab
                    closest_hex = best_hex

        has_distance_line = custom_lab is not None and closest_lab is not None

        # Draw connection line first, so markers remain above it.
        if has_distance_line:
            # Faint underlying stroke
            fig.add_trace(
                go.Scatter(
                    x=[custom_lab[1], closest_lab[1]],
                    y=[custom_lab[2], closest_lab[2]],
                    mode="lines",
                    line=dict(
                        color="rgba(255,255,255,0.95)",
                        width=6,
                    ),
                    showlegend=False,
                    hoverinfo="skip",
                )
            )

            # Foreground dashed stroke
            fig.add_trace(
                go.Scatter(
                    x=[custom_lab[1], closest_lab[1]],
                    y=[custom_lab[2], closest_lab[2]],
                    mode="lines",
                    line=dict(
                        color="rgba(35,54,79,0.95)",
                        width=2.6,
                        dash="dot",
                    ),
                    name="Custom → closest line",
                    showlegend=True,
                    hoverinfo="skip",
                )
            )

        for label, value in color_data.items():
            try:
                lab = np.asarray(value["positive_prototype"], dtype=float).reshape(-1)[:3]
            except Exception:
                continue

            proto_hex = VisualManager._find_hex_for_lab(
                lab,
                hex_color,
                default="#000000"
            )

            is_closest = (
                closest_label is not None
                and str(label) == str(closest_label)
            )

            fig.add_trace(
                go.Scatter(
                    x=[lab[1]],
                    y=[lab[2]],
                    mode="markers",
                    marker=dict(
                        size=11 if is_closest else 8,
                        color=proto_hex,
                        line=dict(
                            color="black",
                            width=3 if is_closest else 1,
                        ),
                        symbol="circle",
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
                        size=10,
                        color=custom_hex,
                        symbol="diamond",
                        line=dict(color="black", width=1.8),
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

        # It shares legendgroup with the closest prototype, so if the user
        # hides that color from the legend, this highlight also disappears.
        if closest_lab is not None:
            fig.add_trace(
                go.Scatter(
                    x=[closest_lab[1]],
                    y=[closest_lab[2]],
                    mode="markers",
                    marker=dict(
                        size=14,
                        color=closest_hex,
                        symbol="circle-open",
                        line=dict(color="black", width=3.5),
                    ),
                    name=str(closest_label),
                    legendgroup=str(closest_label),
                    showlegend=False,
                    hovertemplate=(
                        f"<b>{closest_label}</b><br>"
                        "a*: %{x:.3f}<br>"
                        "b*: %{y:.3f}<extra></extra>"
                    ),
                )
            )

        fig.update_layout(
            title=dict(
                text=f"{filename} | a*b* projection",
                x=0.5,
                font=dict(
                    size=16,
                    family="Arial, sans-serif",
                    color="#3F374C",
                ),
            ),
            dragmode="pan",
            xaxis_title="a* (green ↔ red)",
            yaxis_title="b* (blue ↔ yellow)",
            legend=dict(
                x=1.02,
                y=1.0,
                xanchor="left",
                yanchor="top",
                groupclick="togglegroup",
                title=dict(text="Colors"),
                bgcolor="rgba(255,255,255,0.94)",
                bordercolor="rgba(0,0,0,0.12)",
                borderwidth=1,
                font=dict(size=10, color="#3F374C"),
                itemsizing="constant",
            ),
            margin=dict(l=65, r=230, t=60, b=60),
            paper_bgcolor="white",
            plot_bgcolor="white",
            hoverlabel=dict(
                bgcolor="white",
                bordercolor="#3F374C",
                font=dict(color="#3F374C"),
            ),
        )

        fig.update_xaxes(
            zeroline=True,
            zerolinewidth=1,
            zerolinecolor="gray",
            gridcolor="rgba(0,0,0,0.08)",
            showline=True,
            linecolor="rgba(0,0,0,0.25)",
            mirror=True,
        )

        fig.update_yaxes(
            zeroline=True,
            zerolinewidth=1,
            zerolinecolor="gray",
            gridcolor="rgba(0,0,0,0.08)",
            showline=True,
            linecolor="rgba(0,0,0,0.25)",
            mirror=True,
            scaleanchor="x",
            scaleratio=1,
        )

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
        The default interaction mode is pan instead of zoom.
        If custom color is available, the closest prototype is inferred when needed.
        """
        fig = go.Figure()

        color_data = color_data or {}
        custom_lab = VisualManager._safe_lab(custom_lab)
        closest_lab = VisualManager._safe_lab(closest_lab)

        # Resolve the comparison prototype from its label or LAB distance.
        if custom_lab is not None and closest_lab is None:
            if closest_label is not None:
                for label, value in color_data.items():
                    if str(label) != str(closest_label):
                        continue

                    try:
                        closest_lab = np.asarray(
                            value["positive_prototype"],
                            dtype=float
                        ).reshape(-1)[:3]

                        closest_hex = VisualManager._find_hex_for_lab(
                            closest_lab,
                            hex_color,
                            default=closest_hex,
                        )
                        break
                    except Exception:
                        continue

            if closest_lab is None:
                best_label = None
                best_lab = None
                best_hex = closest_hex
                best_distance = float("inf")

                for label, value in color_data.items():
                    try:
                        lab = np.asarray(
                            value["positive_prototype"],
                            dtype=float
                        ).reshape(-1)[:3]

                        distance = float(np.linalg.norm(custom_lab - lab))

                        if distance < best_distance:
                            best_distance = distance
                            best_label = str(label)
                            best_lab = lab
                            best_hex = VisualManager._find_hex_for_lab(
                                lab,
                                hex_color,
                                default=closest_hex,
                            )
                    except Exception:
                        continue

                if best_lab is not None:
                    closest_label = best_label
                    closest_lab = best_lab
                    closest_hex = best_hex

        has_distance_line = custom_lab is not None and closest_lab is not None

        # Distance line first, so markers remain above it.
        if has_distance_line:
            L1, C1, _h1 = VisualManager._lab_to_lch(custom_lab)
            L2, C2, _h2 = VisualManager._lab_to_lch(closest_lab)

            # Faint underlying stroke
            fig.add_trace(
                go.Scatter(
                    x=[C1, C2],
                    y=[L1, L2],
                    mode="lines",
                    line=dict(
                        color="rgba(255,255,255,0.95)",
                        width=6,
                    ),
                    showlegend=False,
                    hoverinfo="skip",
                )
            )

            # Foreground dashed stroke
            fig.add_trace(
                go.Scatter(
                    x=[C1, C2],
                    y=[L1, L2],
                    mode="lines",
                    line=dict(
                        color="rgba(35,54,79,0.95)",
                        width=2.6,
                        dash="dot",
                    ),
                    name="Custom → closest line",
                    showlegend=True,
                    hoverinfo="skip",
                )
            )

        for label, value in color_data.items():
            try:
                lab = np.asarray(value["positive_prototype"], dtype=float).reshape(-1)[:3]
                L, C, _h = VisualManager._lab_to_lch(lab)
            except Exception:
                continue

            proto_hex = VisualManager._find_hex_for_lab(
                lab,
                hex_color,
                default="#000000"
            )

            is_closest = (
                closest_label is not None
                and str(label) == str(closest_label)
            )

            fig.add_trace(
                go.Scatter(
                    x=[C],
                    y=[L],
                    mode="markers",
                    marker=dict(
                        size=11 if is_closest else 8,
                        color=proto_hex,
                        symbol="circle",
                        line=dict(
                            color="black",
                            width=3 if is_closest else 1,
                        ),
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
                        size=10,
                        color=custom_hex,
                        symbol="diamond",
                        line=dict(color="black", width=1.8),
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

        # Same legendgroup, so it disappears when the user hides that color.
        if closest_lab is not None:
            L, C, _h = VisualManager._lab_to_lch(closest_lab)

            fig.add_trace(
                go.Scatter(
                    x=[C],
                    y=[L],
                    mode="markers",
                    marker=dict(
                        size=14,
                        color=closest_hex,
                        symbol="circle-open",
                        line=dict(color="black", width=3.5),
                    ),
                    name=str(closest_label),
                    legendgroup=str(closest_label),
                    showlegend=False,
                    hovertemplate=(
                        f"<b>{closest_label}</b><br>"
                        "C*: %{x:.3f}<br>"
                        "L*: %{y:.3f}<extra></extra>"
                    ),
                )
            )

        fig.update_layout(
            title=dict(
                text=f"{filename} | L*C* projection",
                x=0.5,
                font=dict(
                    size=16,
                    family="Arial, sans-serif",
                    color="#3F374C",
                ),
            ),
            dragmode="pan",
            xaxis_title="C* (Chroma)",
            yaxis_title="L* (Lightness)",
            legend=dict(
                x=1.02,
                y=1.0,
                xanchor="left",
                yanchor="top",
                groupclick="togglegroup",
                title=dict(text="Colors"),
                bgcolor="rgba(255,255,255,0.94)",
                bordercolor="rgba(0,0,0,0.12)",
                borderwidth=1,
                font=dict(size=10, color="#3F374C"),
                itemsizing="constant",
            ),
            margin=dict(l=65, r=230, t=60, b=60),
            paper_bgcolor="white",
            plot_bgcolor="white",
            hoverlabel=dict(
                bgcolor="white",
                bordercolor="#3F374C",
                font=dict(color="#3F374C"),
            ),
        )

        fig.update_xaxes(
            zeroline=True,
            zerolinewidth=1,
            zerolinecolor="gray",
            gridcolor="rgba(0,0,0,0.08)",
            showline=True,
            linecolor="rgba(0,0,0,0.25)",
            mirror=True,
        )

        fig.update_yaxes(
            range=[0, 100],
            zeroline=True,
            zerolinewidth=1,
            zerolinecolor="gray",
            gridcolor="rgba(0,0,0,0.08)",
            showline=True,
            linecolor="rgba(0,0,0,0.25)",
            mirror=True,
        )

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
        If custom color is available, the closest prototype is inferred when needed.
        """
        fig = go.Figure()

        color_data = color_data or {}
        custom_lab = VisualManager._safe_lab(custom_lab)
        closest_lab = VisualManager._safe_lab(closest_lab)

        # Resolve the comparison prototype from its label or LAB distance.
        if custom_lab is not None and closest_lab is None:
            if closest_label is not None:
                for label, value in color_data.items():
                    if str(label) != str(closest_label):
                        continue

                    try:
                        closest_lab = np.asarray(
                            value["positive_prototype"],
                            dtype=float
                        ).reshape(-1)[:3]

                        closest_hex = VisualManager._find_hex_for_lab(
                            closest_lab,
                            hex_color,
                            default=closest_hex,
                        )
                        break
                    except Exception:
                        continue

            if closest_lab is None:
                best_label = None
                best_lab = None
                best_hex = closest_hex
                best_distance = float("inf")

                for label, value in color_data.items():
                    try:
                        lab = np.asarray(
                            value["positive_prototype"],
                            dtype=float
                        ).reshape(-1)[:3]

                        distance = float(np.linalg.norm(custom_lab - lab))

                        if distance < best_distance:
                            best_distance = distance
                            best_label = str(label)
                            best_lab = lab
                            best_hex = VisualManager._find_hex_for_lab(
                                lab,
                                hex_color,
                                default=closest_hex,
                            )
                    except Exception:
                        continue

                if best_lab is not None:
                    closest_label = best_label
                    closest_lab = best_lab
                    closest_hex = best_hex

        has_distance_line = custom_lab is not None and closest_lab is not None

        # Distance line first, so markers remain above it.
        if has_distance_line:
            L1, C1, h1 = VisualManager._lab_to_lch(custom_lab)
            L2, C2, h2 = VisualManager._lab_to_lch(closest_lab)

            # Faint underlying stroke
            fig.add_trace(
                go.Scatterpolar(
                    r=[C1, C2],
                    theta=[h1, h2],
                    mode="lines",
                    line=dict(
                        color="rgba(255,255,255,0.95)",
                        width=6,
                    ),
                    showlegend=False,
                    hoverinfo="skip",
                )
            )

            # Foreground dashed stroke
            fig.add_trace(
                go.Scatterpolar(
                    r=[C1, C2],
                    theta=[h1, h2],
                    mode="lines",
                    line=dict(
                        color="rgba(35,54,79,0.95)",
                        width=2.6,
                        dash="dot",
                    ),
                    name="Custom → closest line",
                    showlegend=True,
                    hoverinfo="skip",
                )
            )

        for label, value in color_data.items():
            try:
                lab = np.asarray(value["positive_prototype"], dtype=float).reshape(-1)[:3]
                L, C, h = VisualManager._lab_to_lch(lab)
            except Exception:
                continue

            proto_hex = VisualManager._find_hex_for_lab(
                lab,
                hex_color,
                default="#000000"
            )

            is_closest = (
                closest_label is not None
                and str(label) == str(closest_label)
            )

            fig.add_trace(
                go.Scatterpolar(
                    r=[C],
                    theta=[h],
                    mode="markers",
                    marker=dict(
                        size=11 if is_closest else 8,
                        color=proto_hex,
                        symbol="circle",
                        line=dict(
                            color="black",
                            width=3 if is_closest else 1,
                        ),
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
                        size=10,
                        color=custom_hex,
                        symbol="diamond",
                        line=dict(color="black", width=1.8),
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

        # Same legendgroup, so it disappears when the user hides that color.
        if closest_lab is not None:
            L, C, h = VisualManager._lab_to_lch(closest_lab)

            fig.add_trace(
                go.Scatterpolar(
                    r=[C],
                    theta=[h],
                    mode="markers",
                    marker=dict(
                        size=14,
                        color=closest_hex,
                        symbol="circle-open",
                        line=dict(color="black", width=3.5),
                    ),
                    name=str(closest_label),
                    legendgroup=str(closest_label),
                    showlegend=False,
                    hovertemplate=(
                        f"<b>{closest_label}</b><br>"
                        "h°: %{theta:.2f}<br>"
                        "C*: %{r:.3f}<br>"
                        f"L*: {L:.3f}<extra></extra>"
                    ),
                )
            )

        fig.update_layout(
            title=dict(
                text=f"{filename} | LCh hue/chroma",
                x=0.5,
                font=dict(
                    size=16,
                    family="Arial, sans-serif",
                    color="#3F374C",
                ),
            ),
            dragmode="pan",
            polar=dict(
                radialaxis=dict(
                    title="C*",
                    gridcolor="rgba(0,0,0,0.08)",
                    linecolor="rgba(0,0,0,0.25)",
                ),
                angularaxis=dict(
                    direction="counterclockwise",
                    rotation=0,
                    gridcolor="rgba(0,0,0,0.08)",
                    linecolor="rgba(0,0,0,0.25)",
                ),
                bgcolor="white",
            ),
            legend=dict(
                x=1.02,
                y=1.0,
                xanchor="left",
                yanchor="top",
                groupclick="togglegroup",
                title=dict(text="Colors"),
                bgcolor="rgba(255,255,255,0.94)",
                bordercolor="rgba(0,0,0,0.12)",
                borderwidth=1,
                font=dict(size=10, color="#3F374C"),
                itemsizing="constant",
            ),
            margin=dict(l=65, r=230, t=60, b=60),
            paper_bgcolor="white",
            plot_bgcolor="white",
            hoverlabel=dict(
                bgcolor="white",
                bordercolor="#3F374C",
                font=dict(color="#3F374C"),
            ),
        )

        return fig


    @staticmethod
    def plot_color_evaluation_top7_bar(
        ranking,
        metric_name="CIEDE2000",
        title="Top 7 closest prototypes",
        threshold_settings=None,
    ):
        """
        Horizontal bar chart for the closest 7 prototypes.

        Ranking items may contain:
            - metric_value
            - delta_e

        Visual improvements:
            - Best/closest prototype highlighted.
            - Cleaner background and grid.
            - Threshold guide lines follow the active threshold settings.
            - Default interaction mode set to pan.
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

        if not labels or not values:
            fig.update_layout(
                title=dict(text=title, x=0.5),
                paper_bgcolor="white",
                plot_bgcolor="white",
            )
            return fig

        labels_plot = labels[::-1]
        values_plot = values[::-1]

        # Closest is the first item in the original ranking.
        # After reversing, it is the last displayed bar, visually at the top.
        colors = []

        for label in labels_plot:
            if label == labels[0]:
                colors.append("rgba(35,54,79,0.95)")      # Closest prototype
            else:
                colors.append("rgba(135,157,184,0.72)")   # Other prototypes

        fig.add_trace(
            go.Bar(
                x=values_plot,
                y=labels_plot,
                orientation="h",
                marker=dict(
                    color=colors,
                    line=dict(
                        color="rgba(35,54,79,0.45)",
                        width=1,
                    ),
                ),
                text=[
                    VisualManager._format_metric_value(v, metric_name)
                    for v in values_plot
                ],
                textposition="outside",
                cliponaxis=False,
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    + str(metric_name)
                    + ": %{x:.3f}<extra></extra>"
                ),
            )
        )

        # Active threshold guide lines.
        # This is linked to threshold_settings:
        #   mode="default":
        #       preset="pt"    -> PT only
        #       preset="at"    -> AT only
        #       preset="pt_at" -> PT + AT
        #   mode="custom":
        #       custom_type="single"      -> one custom threshold
        #       custom_type="lower_upper" -> lower + upper thresholds
        def _safe_positive_float(value):
            try:
                parsed = float(value)
                if parsed > 0:
                    return parsed
            except Exception:
                pass
            return None

        def _metric_matches_threshold_settings():
            if not threshold_settings:
                return False

            active_metric = str(threshold_settings.get("metric", "")).strip()
            current_metric = str(metric_name).strip()

            # If no metric is stored in settings, allow the guide.
            if not active_metric:
                return True

            return active_metric == current_metric

        def _get_active_threshold_guides():
            if not threshold_settings or not _metric_matches_threshold_settings():
                return []

            mode = str(threshold_settings.get("mode", "default")).strip().lower()
            preset = str(threshold_settings.get("preset", "pt_at")).strip().lower()
            custom_type = str(threshold_settings.get("custom_type", "single")).strip().lower()

            guides = []

            if mode in ("default", "known"):
                if preset == "pt":
                    guides.append(
                        (0.8, "PT 0.8", "rgba(64,128,64,0.75)")
                    )

                elif preset == "at":
                    guides.append(
                        (1.8, "AT 1.8", "rgba(180,120,35,0.75)")
                    )

                else:
                    guides.extend([
                        (0.8, "PT 0.8", "rgba(64,128,64,0.75)"),
                        (1.8, "AT 1.8", "rgba(180,120,35,0.75)"),
                    ])

            elif mode == "custom":
                if custom_type == "single":
                    value = _safe_positive_float(threshold_settings.get("single"))

                    if value is not None:
                        guides.append(
                            (value, f"Threshold {value:g}", "rgba(90,90,160,0.80)")
                        )

                else:
                    lower = _safe_positive_float(threshold_settings.get("lower"))
                    upper = _safe_positive_float(threshold_settings.get("upper"))

                    if lower is not None:
                        guides.append(
                            (lower, f"Lower {lower:g}", "rgba(64,128,64,0.75)")
                        )

                    if upper is not None:
                        guides.append(
                            (upper, f"Upper {upper:g}", "rgba(180,80,65,0.75)")
                        )

            return guides

        shapes = []
        annotations = []

        active_guides = _get_active_threshold_guides()

        for x_value, label_text, color in active_guides:
            shapes.append(
                dict(
                    type="line",
                    x0=x_value,
                    x1=x_value,
                    y0=-0.5,
                    y1=len(labels_plot) - 0.5,
                    xref="x",
                    yref="y",
                    line=dict(
                        color=color,
                        width=1.7,
                        dash="dot",
                    ),
                )
            )

            annotations.append(
                dict(
                    x=x_value,
                    y=1.04,
                    xref="x",
                    yref="paper",
                    text=label_text,
                    showarrow=False,
                    font=dict(
                        size=10,
                        color=color,
                    ),
                    xanchor="center",
                )
            )

        fig.update_layout(
            title=dict(
                text=title,
                x=0.5,
                font=dict(
                    size=16,
                    family="Arial, sans-serif",
                    color="#3F374C",
                ),
            ),
            dragmode="pan",
            xaxis_title=metric_name,
            yaxis_title="Prototype",
            shapes=shapes,
            annotations=annotations,
            margin=dict(l=135, r=70, t=65, b=55),
            paper_bgcolor="white",
            plot_bgcolor="white",
            bargap=0.28,
            hoverlabel=dict(
                bgcolor="white",
                bordercolor="#3F374C",
                font=dict(color="#3F374C"),
            ),
        )

        fig.update_xaxes(
            zeroline=True,
            zerolinewidth=1,
            zerolinecolor="rgba(0,0,0,0.35)",
            gridcolor="rgba(0,0,0,0.08)",
            showline=True,
            linecolor="rgba(0,0,0,0.25)",
            mirror=True,
        )

        fig.update_yaxes(
            gridcolor="rgba(0,0,0,0.04)",
            showline=True,
            linecolor="rgba(0,0,0,0.20)",
            mirror=True,
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

        Visual improvements:
            - Color encodes membership strength.
            - Winner is visually emphasized.
            - Cleaner grid and fixed 0-1 scale.
            - Default interaction mode set to pan.
        """
        memberships = memberships or []
        memberships = sorted(
            memberships,
            key=lambda item: float(item[1]),
            reverse=True
        )[:top_n]

        labels = []
        values = []

        for label, mu in memberships:
            try:
                labels.append(str(label))
                values.append(float(mu))
            except Exception:
                continue

        fig = go.Figure()

        if not labels or not values:
            fig.update_layout(
                title=dict(text=title, x=0.5),
                paper_bgcolor="white",
                plot_bgcolor="white",
            )
            return fig

        labels_plot = labels[::-1]
        values_plot = values[::-1]

        def _membership_color(mu):
            if mu >= 0.75:
                return "rgba(46,125,82,0.92)"       # high
            if mu >= 0.40:
                return "rgba(58,112,165,0.86)"      # medium
            if mu >= 0.15:
                return "rgba(190,139,56,0.82)"      # low-medium
            return "rgba(160,160,160,0.70)"         # low

        colors = [_membership_color(v) for v in values_plot]

        fig.add_trace(
            go.Bar(
                x=values_plot,
                y=labels_plot,
                orientation="h",
                marker=dict(
                    color=colors,
                    line=dict(
                        color="rgba(35,54,79,0.35)",
                        width=1,
                    ),
                ),
                text=[f"{v:.4f}" for v in values_plot],
                textposition="outside",
                cliponaxis=False,
                hovertemplate="<b>%{y}</b><br>μ = %{x:.4f}<extra></extra>",
            )
        )

        shapes = [
            dict(
                type="rect",
                x0=0.0,
                x1=0.4,
                y0=-0.5,
                y1=len(labels_plot) - 0.5,
                xref="x",
                yref="y",
                fillcolor="rgba(160,160,160,0.055)",
                line=dict(width=0),
                layer="below",
            ),
            dict(
                type="rect",
                x0=0.4,
                x1=0.75,
                y0=-0.5,
                y1=len(labels_plot) - 0.5,
                xref="x",
                yref="y",
                fillcolor="rgba(58,112,165,0.045)",
                line=dict(width=0),
                layer="below",
            ),
            dict(
                type="rect",
                x0=0.75,
                x1=1.0,
                y0=-0.5,
                y1=len(labels_plot) - 0.5,
                xref="x",
                yref="y",
                fillcolor="rgba(46,125,82,0.055)",
                line=dict(width=0),
                layer="below",
            ),
        ]

        fig.update_layout(
            title=dict(
                text=title,
                x=0.5,
                font=dict(
                    size=16,
                    family="Arial, sans-serif",
                    color="#3F374C",
                ),
            ),
            dragmode="pan",
            xaxis_title="Membership degree (μ)",
            yaxis_title="Prototype",
            shapes=shapes,
            margin=dict(l=140, r=75, t=60, b=55),
            paper_bgcolor="white",
            plot_bgcolor="white",
            bargap=0.28,
            hoverlabel=dict(
                bgcolor="white",
                bordercolor="#3F374C",
                font=dict(color="#3F374C"),
            ),
        )

        fig.update_xaxes(
            range=[0, 1.05],
            tickformat=".2f",
            zeroline=True,
            zerolinewidth=1,
            zerolinecolor="rgba(0,0,0,0.35)",
            gridcolor="rgba(0,0,0,0.08)",
            showline=True,
            linecolor="rgba(0,0,0,0.25)",
            mirror=True,
        )

        fig.update_yaxes(
            gridcolor="rgba(0,0,0,0.04)",
            showline=True,
            linecolor="rgba(0,0,0,0.20)",
            mirror=True,
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

        Visual improvements:
            - Positive/negative components are visually separated.
            - Zero baseline is emphasized.
            - Cleaner grid and better text placement.
            - Default interaction mode set to pan.
        """
        components = components or {}

        keys = ["ΔL*", "Δa*", "Δb*", "ΔC*", "Δh°", "ΔH*"]
        values = []

        for key in keys:
            try:
                values.append(float(components.get(key, 0.0)))
            except Exception:
                values.append(0.0)

        max_abs = max([abs(v) for v in values] + [1.0])
        y_padding = max_abs * 0.18

        colors = []

        for value in values:
            if value > 0:
                colors.append("rgba(190,88,64,0.88)")      # positive
            elif value < 0:
                colors.append("rgba(58,112,165,0.88)")     # negative
            else:
                colors.append("rgba(160,160,160,0.70)")    # zero

        fig = go.Figure()

        fig.add_trace(
            go.Bar(
                x=keys,
                y=values,
                marker=dict(
                    color=colors,
                    line=dict(
                        color="rgba(35,54,79,0.35)",
                        width=1,
                    ),
                ),
                text=[f"{v:+.3f}" for v in values],
                textposition=[
                    "outside" if v >= 0 else "outside"
                    for v in values
                ],
                cliponaxis=False,
                hovertemplate="<b>%{x}</b><br>Value: %{y:+.3f}<extra></extra>",
            )
        )

        fig.update_layout(
            title=dict(
                text=title,
                x=0.5,
                font=dict(
                    size=16,
                    family="Arial, sans-serif",
                    color="#3F374C",
                ),
            ),
            dragmode="pan",
            xaxis_title="Component",
            yaxis_title="Signed difference",
            margin=dict(l=70, r=45, t=60, b=60),
            paper_bgcolor="white",
            plot_bgcolor="white",
            bargap=0.34,
            hoverlabel=dict(
                bgcolor="white",
                bordercolor="#3F374C",
                font=dict(color="#3F374C"),
            ),
            shapes=[
                dict(
                    type="line",
                    x0=-0.5,
                    x1=len(keys) - 0.5,
                    y0=0,
                    y1=0,
                    xref="x",
                    yref="y",
                    line=dict(
                        color="rgba(35,54,79,0.75)",
                        width=1.8,
                    ),
                )
            ],
        )

        fig.update_xaxes(
            showline=True,
            linecolor="rgba(0,0,0,0.25)",
            mirror=True,
            gridcolor="rgba(0,0,0,0.04)",
        )

        fig.update_yaxes(
            range=[
                min(values) - y_padding,
                max(values) + y_padding,
            ],
            zeroline=False,
            gridcolor="rgba(0,0,0,0.08)",
            showline=True,
            linecolor="rgba(0,0,0,0.25)",
            mirror=True,
        )

        return fig
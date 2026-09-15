from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from Source.colorspace.ReferenceDomain import ReferenceDomain
from Source.geometry.Face import Face
from Source.geometry.Plane import Plane
from Source.geometry.Point import Point
from Source.geometry.Volume import Volume


@dataclass
class _PolyFace:
    normal: np.ndarray
    offset: float
    vertices: np.ndarray
    source_index: Optional[int] = None
    is_domain_boundary: bool = False


class Voronoi:
    """
    Optimized 3D Euclidean Voronoi-cell builder for PyFCS.

    The implementation is specialized for bounded CIELAB Voronoi cells.  Each
    cell starts as the reference-domain box and is incrementally clipped by the
    perpendicular-bisector half-spaces between the selected prototype and the
    remaining prototypes.

    No external qvoronoi process, temporary files, or triple-plane exhaustive
    reconstruction is required.
    """

    DEFAULT_EPS = 1e-9
    DEFAULT_MERGE_EPS = 1e-8

    @classmethod
    def build_cell(
        cls,
        positive,
        negatives,
        reference_domain=None,
        eps=DEFAULT_EPS,
        merge_eps=DEFAULT_MERGE_EPS,
    ):
        """
        Build the bounded Voronoi cell of ``positive`` against ``negatives``.

        Parameters
        ----------
        positive : array-like, shape (3,)
            Prototype whose Voronoi cell is requested.
        negatives : array-like, shape (N, 3)
            Competing prototypes.
        reference_domain : ReferenceDomain, optional
            Bounding CIELAB domain.  The standard PyFCS domain is used when
            omitted.
        eps : float
            Half-space numerical tolerance.
        merge_eps : float
            Vertex deduplication tolerance.

        Returns
        -------
        Volume
            PyFCS Volume containing only the faces that actually bound the
            clipped cell.
        """
        p = cls._as_point_array(positive)
        neg = cls._as_points_array(negatives)

        if reference_domain is None:
            reference_domain = ReferenceDomain.default_voronoi_reference_domain()

        cls._validate_points_in_domain(
            np.vstack((p.reshape(1, 3), neg)) if len(neg) else p.reshape(1, 3),
            reference_domain,
            eps,
        )
        cls._validate_no_duplicate_competitors(p, neg, merge_eps)

        if len(neg) == 0:
            faces = cls._create_domain_faces(reference_domain)
            return cls._to_volume(p, faces)

        # Preserve the historical local indexing convention used by Prototype:
        # the positive site is index 0 and the negatives are 1..N.
        source_indices = np.arange(1, len(neg) + 1, dtype=int)

        faces = cls._build_cell_internal(
            positive=p,
            competitors=neg,
            competitor_indices=source_indices,
            reference_domain=reference_domain,
            eps=eps,
            merge_eps=merge_eps,
        )
        return cls._to_volume(p, faces)

    @classmethod
    def build_diagram(
        cls,
        points,
        reference_domain=None,
        eps=DEFAULT_EPS,
        merge_eps=DEFAULT_MERGE_EPS,
    ):
        """
        Build all bounded Voronoi cells for a 3D point set.

        This is the preferred PyFCS entry point because the complete color space
        is handled in one coordinated call and no Prototype launches an external
        process or rebuilds geometry independently.
        """
        pts = cls._as_points_array(points)

        if reference_domain is None:
            reference_domain = ReferenceDomain.default_voronoi_reference_domain()

        n = len(pts)
        if n == 0:
            return []

        cls._validate_points_in_domain(pts, reference_domain, eps)
        cls._validate_no_duplicate_points(pts, merge_eps)

        volumes = []
        all_indices = np.arange(n, dtype=int)

        for i in range(n):
            mask = all_indices != i
            competitors = pts[mask]
            competitor_indices = all_indices[mask]

            faces = cls._build_cell_internal(
                positive=pts[i],
                competitors=competitors,
                competitor_indices=competitor_indices,
                reference_domain=reference_domain,
                eps=eps,
                merge_eps=merge_eps,
            )
            volumes.append(cls._to_volume(pts[i], faces))

        return volumes

    @classmethod
    def _build_cell_internal(
        cls,
        positive,
        competitors,
        competitor_indices,
        reference_domain,
        eps,
        merge_eps,
    ):
        faces = cls._create_domain_faces(reference_domain)

        if len(competitors) == 0:
            return faces

        diff = competitors - positive
        dist2 = np.einsum("ij,ij->i", diff, diff)
        order = np.argsort(dist2)

        # The current cell is always bounded by the reference domain, so its
        # farthest point from the representative is one of its vertices.
        current_vertices = cls._collect_vertices(faces)
        radius2 = cls._max_radius_squared(current_vertices, positive)

        duplicate_threshold2 = merge_eps * merge_eps

        for order_pos in order:
            d2 = float(dist2[order_pos])

            # Duplicated or numerically indistinguishable sites do not define
            # a unique Voronoi partition.  They are rejected explicitly so the
            # no-overlap invariant is preserved.
            if d2 <= duplicate_threshold2:
                raise ValueError(
                    "Duplicate or near-duplicate LAB prototypes are not allowed "
                    "in a Voronoi color space."
                )

            # Exact rejection bound.  If |p-q| > 2R, where R is the current
            # maximum distance from p to the cell, q cannot cut this cell.  The
            # remaining competitors are even farther away because of sorting.
            if np.isfinite(radius2) and d2 > 4.0 * radius2 + eps:
                break

            q = competitors[order_pos]
            source_index = int(competitor_indices[order_pos])

            normal, offset = cls._bisector_halfspace(positive, q)

            # Reuse the vertex cache from the previous iteration. It is only
            # rebuilt after a clipping operation actually changes the cell.
            values = current_vertices @ normal + offset

            # Entire polyhedron already lies in the valid half-space.
            if np.min(values) >= -eps:
                continue

            faces = cls._clip_polyhedron(
                faces=faces,
                normal=normal,
                offset=offset,
                source_index=source_index,
                eps=eps,
                merge_eps=merge_eps,
            )

            if not faces:
                raise RuntimeError(
                    "Voronoi cell became empty. Check prototype coordinates, "
                    "reference-domain bounds, and numerical tolerances."
                )

            current_vertices = cls._collect_vertices(faces)
            radius2 = cls._max_radius_squared(current_vertices, positive)

        return faces

    @staticmethod
    def _as_point_array(point):
        arr = np.asarray(point, dtype=np.float64).reshape(-1)
        if arr.size != 3:
            raise ValueError("A Voronoi prototype must contain exactly 3 coordinates.")
        if not np.all(np.isfinite(arr)):
            raise ValueError("Voronoi prototype coordinates must be finite.")
        return arr

    @staticmethod
    def _as_points_array(points):
        if points is None:
            return np.empty((0, 3), dtype=np.float64)

        arr = np.asarray(points, dtype=np.float64)
        if arr.size == 0:
            return np.empty((0, 3), dtype=np.float64)

        if arr.ndim == 1:
            if arr.size != 3:
                raise ValueError("Voronoi points must have shape (N, 3).")
            arr = arr.reshape(1, 3)

        if arr.ndim != 2 or arr.shape[1] != 3:
            raise ValueError("Voronoi points must have shape (N, 3).")
        if not np.all(np.isfinite(arr)):
            raise ValueError("Voronoi point coordinates must be finite.")

        return arr

    @staticmethod
    def _validate_points_in_domain(points, reference_domain, eps):
        pts = np.asarray(points, dtype=np.float64).reshape(-1, 3)
        mins = np.array(
            [reference_domain.get_min(i) for i in range(3)],
            dtype=np.float64,
        )
        maxs = np.array(
            [reference_domain.get_max(i) for i in range(3)],
            dtype=np.float64,
        )

        invalid = np.where(
            np.any((pts < (mins - eps)) | (pts > (maxs + eps)), axis=1)
        )[0]

        if invalid.size:
            idx = int(invalid[0])
            point = pts[idx]
            raise ValueError(
                "Voronoi prototype outside the reference domain at index "
                f"{idx}: [{point[0]}, {point[1]}, {point[2]}]."
            )

    @classmethod
    def _validate_no_duplicate_competitors(cls, positive, competitors, merge_eps):
        if competitors is None or len(competitors) == 0:
            return

        eps2 = merge_eps * merge_eps
        delta = np.asarray(competitors, dtype=np.float64) - positive
        dist2 = np.einsum("ij,ij->i", delta, delta)
        duplicate = np.where(dist2 <= eps2)[0]

        if duplicate.size:
            raise ValueError(
                "Duplicate or near-duplicate LAB prototypes are not allowed "
                "in a Voronoi color space."
            )

    @classmethod
    def _validate_no_duplicate_points(cls, points, merge_eps):
        """Reject duplicate/near-duplicate sites without allocating an NxN matrix."""
        pts = np.asarray(points, dtype=np.float64)
        if len(pts) < 2:
            return

        eps2 = merge_eps * merge_eps
        order = np.argsort(pts[:, 0], kind="mergesort")
        ordered = pts[order]

        for i in range(len(ordered) - 1):
            j = i + 1
            while j < len(ordered) and ordered[j, 0] - ordered[i, 0] <= merge_eps:
                if cls._distance_squared(ordered[i], ordered[j]) <= eps2:
                    raise ValueError(
                        "Duplicate or near-duplicate LAB prototypes are not "
                        f"allowed (indices {int(order[i])} and {int(order[j])})."
                    )
                j += 1

    @staticmethod
    def _bisector_halfspace(p, q):
        """
        Return a normalized plane n.x + d = 0 whose non-negative side contains p.
        """
        normal = p - q
        norm = float(np.linalg.norm(normal))
        if norm == 0.0:
            return np.zeros(3, dtype=np.float64), 0.0

        offset = (float(np.dot(q, q)) - float(np.dot(p, p))) * 0.5
        normal = normal / norm
        offset /= norm
        return normal, offset

    @classmethod
    def _create_domain_faces(cls, domain):
        x0, x1 = float(domain.get_min(0)), float(domain.get_max(0))
        y0, y1 = float(domain.get_min(1)), float(domain.get_max(1))
        z0, z1 = float(domain.get_min(2)), float(domain.get_max(2))

        v000 = np.array([x0, y0, z0], dtype=np.float64)
        v001 = np.array([x0, y0, z1], dtype=np.float64)
        v010 = np.array([x0, y1, z0], dtype=np.float64)
        v011 = np.array([x0, y1, z1], dtype=np.float64)
        v100 = np.array([x1, y0, z0], dtype=np.float64)
        v101 = np.array([x1, y0, z1], dtype=np.float64)
        v110 = np.array([x1, y1, z0], dtype=np.float64)
        v111 = np.array([x1, y1, z1], dtype=np.float64)

        def face(normal, offset, vertices):
            return _PolyFace(
                normal=np.asarray(normal, dtype=np.float64),
                offset=float(offset),
                vertices=np.asarray(vertices, dtype=np.float64),
                source_index=None,
                is_domain_boundary=True,
            )

        # Every domain plane is oriented so that its non-negative half-space is
        # the interior, matching ReferenceDomain.create_volume().
        return [
            face([1.0, 0.0, 0.0], -x0, [v000, v001, v011, v010]),
            face([-1.0, 0.0, 0.0], x1, [v100, v110, v111, v101]),
            face([0.0, 1.0, 0.0], -y0, [v000, v100, v101, v001]),
            face([0.0, -1.0, 0.0], y1, [v010, v011, v111, v110]),
            face([0.0, 0.0, 1.0], -z0, [v000, v010, v110, v100]),
            face([0.0, 0.0, -1.0], z1, [v001, v101, v111, v011]),
        ]

    @classmethod
    def _clip_polyhedron(
        cls,
        faces: List[_PolyFace],
        normal,
        offset,
        source_index,
        eps,
        merge_eps,
    ):
        clipped_faces = []
        cap_points = []

        for face in faces:
            clipped_polygon, intersections = cls._clip_polygon(
                face.vertices,
                normal,
                offset,
                eps,
                merge_eps,
            )

            if intersections:
                cap_points.extend(intersections)

            if len(clipped_polygon) >= 3 and cls._polygon_is_valid(clipped_polygon, merge_eps):
                clipped_faces.append(
                    _PolyFace(
                        normal=face.normal,
                        offset=face.offset,
                        vertices=clipped_polygon,
                        source_index=face.source_index,
                        is_domain_boundary=face.is_domain_boundary,
                    )
                )

        cap_points = cls._unique_points(cap_points, merge_eps)

        if len(cap_points) >= 3:
            cap = np.asarray(cap_points, dtype=np.float64)
            cap = cls._order_points_on_plane(cap, normal)

            if cls._polygon_is_valid(cap, merge_eps):
                clipped_faces.append(
                    _PolyFace(
                        normal=np.asarray(normal, dtype=np.float64),
                        offset=float(offset),
                        vertices=cap,
                        source_index=source_index,
                        is_domain_boundary=False,
                    )
                )

        return clipped_faces

    @classmethod
    def _clip_polygon(cls, vertices, normal, offset, eps, merge_eps):
        if vertices is None or len(vertices) == 0:
            return np.empty((0, 3), dtype=np.float64), []

        polygon = np.asarray(vertices, dtype=np.float64)
        output = []
        intersections = []

        start = polygon[-1]
        start_value = float(np.dot(normal, start) + offset)
        start_inside = start_value >= -eps

        for end in polygon:
            end_value = float(np.dot(normal, end) + offset)
            end_inside = end_value >= -eps

            if start_inside and end_inside:
                output.append(end)

            elif start_inside and not end_inside:
                intersection = cls._segment_plane_intersection(
                    start, end, start_value, end_value
                )
                output.append(intersection)
                intersections.append(intersection)

            elif not start_inside and end_inside:
                intersection = cls._segment_plane_intersection(
                    start, end, start_value, end_value
                )
                output.append(intersection)
                output.append(end)
                intersections.append(intersection)

            start = end
            start_value = end_value
            start_inside = end_inside

        output = cls._deduplicate_polygon(output, merge_eps)
        if len(output) < 3:
            return np.empty((0, 3), dtype=np.float64), intersections

        return np.asarray(output, dtype=np.float64), intersections

    @staticmethod
    def _segment_plane_intersection(start, end, start_value, end_value):
        denom = start_value - end_value
        if denom == 0.0:
            return np.asarray(start, dtype=np.float64).copy()

        t = start_value / denom
        t = min(1.0, max(0.0, t))
        return start + t * (end - start)

    @staticmethod
    def _distance_squared(p, q):
        dx = float(p[0] - q[0])
        dy = float(p[1] - q[1])
        dz = float(p[2] - q[2])
        return dx * dx + dy * dy + dz * dz

    @classmethod
    def _deduplicate_polygon(cls, points, eps):
        if not points:
            return []

        eps2 = eps * eps
        cleaned = []
        for p in points:
            p = np.asarray(p, dtype=np.float64)
            if not cleaned or cls._distance_squared(p, cleaned[-1]) > eps2:
                cleaned.append(p)

        if len(cleaned) > 1 and cls._distance_squared(cleaned[0], cleaned[-1]) <= eps2:
            cleaned.pop()

        return cleaned

    @classmethod
    def _unique_points(cls, points, eps):
        eps2 = eps * eps
        unique = []
        for p in points:
            p = np.asarray(p, dtype=np.float64)
            duplicate = False
            for q in unique:
                if cls._distance_squared(p, q) <= eps2:
                    duplicate = True
                    break
            if not duplicate:
                unique.append(p)
        return unique

    @staticmethod
    def _order_points_on_plane(points, normal):
        center = np.mean(points, axis=0)
        n = np.asarray(normal, dtype=np.float64)
        n_norm = np.linalg.norm(n)
        if n_norm == 0.0:
            return points
        n = n / n_norm

        axis_candidates = np.eye(3, dtype=np.float64)
        ref = axis_candidates[np.argmin(np.abs(axis_candidates @ n))]

        u = np.cross(n, ref)
        u_norm = np.linalg.norm(u)
        if u_norm == 0.0:
            return points
        u /= u_norm

        v = np.cross(n, u)
        rel = points - center
        angles = np.arctan2(rel @ v, rel @ u)
        return points[np.argsort(angles)]

    @staticmethod
    def _polygon_is_valid(vertices, eps):
        if vertices is None or len(vertices) < 3:
            return False

        verts = np.asarray(vertices, dtype=np.float64)
        base = verts[0]
        eps4 = (eps * eps) ** 2

        # A convex polygon is valid as soon as any pair of vectors from the
        # first vertex spans a non-zero area.  Manual scalar arithmetic is much
        # cheaper here than repeatedly calling numpy.cross on tiny 3D vectors.
        for i in range(1, len(verts) - 1):
            ax = float(verts[i][0] - base[0])
            ay = float(verts[i][1] - base[1])
            az = float(verts[i][2] - base[2])

            for j in range(i + 1, len(verts)):
                bx = float(verts[j][0] - base[0])
                by = float(verts[j][1] - base[1])
                bz = float(verts[j][2] - base[2])

                cx = ay * bz - az * by
                cy = az * bx - ax * bz
                cz = ax * by - ay * bx

                if cx * cx + cy * cy + cz * cz > eps4:
                    return True

        return False

    @staticmethod
    def _collect_vertices(faces):
        arrays = [f.vertices for f in faces if f.vertices is not None and len(f.vertices) > 0]
        if not arrays:
            return np.empty((0, 3), dtype=np.float64)
        return np.vstack(arrays)

    @staticmethod
    def _max_radius_squared(vertices, positive):
        if vertices is None or len(vertices) == 0:
            return float("inf")
        delta = vertices - positive
        return float(np.max(np.einsum("ij,ij->i", delta, delta)))

    @staticmethod
    def _to_volume(positive, faces):
        representative = Point(float(positive[0]), float(positive[1]), float(positive[2]))
        volume_faces = []

        for face in faces:
            if face.vertices is None or len(face.vertices) < 3:
                continue

            plane = Plane(
                float(face.normal[0]),
                float(face.normal[1]),
                float(face.normal[2]),
                float(face.offset),
            )
            vertices = [
                Point(float(v[0]), float(v[1]), float(v[2]))
                for v in face.vertices
            ]

            volume_faces.append(
                Face(
                    p=plane,
                    vertex=vertices,
                    infinity=False,
                    source_index=face.source_index,
                    is_domain_boundary=face.is_domain_boundary,
                )
            )

        return Volume(representative=representative, faces=volume_faces)

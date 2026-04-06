import math

from Source.geometry.Point import Point
from Source.geometry.Vector import Vector
from Source.geometry.Plane import Plane


class GeometryTools:
    # Small numerical tolerance used to avoid unstable divisions and comparisons.
    SMALL_NUM = 1e-9

    @staticmethod
    def dot(u, v):
        """Return the dot product of two 3D vectors."""
        return u.a * v.a + u.b * v.b + u.c * v.c

    @staticmethod
    def plus(v, p):
        """Translate a point by a vector and return the resulting point."""
        return Point(v.a + p.x, v.b + p.y, v.c + p.z)

    @staticmethod
    def minus(v, p):
        """Subtract a point coordinates from a vector-like object and return a point."""
        return Point(v.a - p.x, v.b - p.y, v.c - p.z)

    @staticmethod
    def scalar_product(v, s):
        """Scale a vector by a scalar factor."""
        return Vector(v.a * s, v.b * s, v.c * s)

    @staticmethod
    def cross_product(v, u):
        """Return the 3D cross product of two vectors."""
        return Vector(
            v.b * u.c - v.c * u.b,
            v.c * u.a - v.a * u.c,
            v.a * u.b - v.b * u.a
        )

    @staticmethod
    def intersect2_planes(p1, p2):
        """Placeholder for the intersection of two planes."""
        return None

    @staticmethod
    def is_same_direction(v, u, eps=1e-6):
        """
        Check whether two vectors point in the same direction within a tolerance.
        Returns False for degenerate vectors.
        """
        mod_v = GeometryTools.module(v)
        mod_u = GeometryTools.module(u)
        if mod_v <= eps or mod_u <= eps:
            return False

        alpha = GeometryTools.dot(v, u) / (mod_v * mod_u)
        return alpha > 1.0 - eps

    @staticmethod
    def module(v):
        """Return the Euclidean norm of a 3D vector."""
        return math.sqrt(v.a**2 + v.b**2 + v.c**2)

    @staticmethod
    def euclidean_distance(point1, point2):
        """Return the Euclidean distance between two 3D points."""
        p1 = point1.get_double_point()
        p2 = point2.get_double_point()
        dc = [p1[i] - p2[i] for i in range(len(p1))]
        return math.sqrt(sum(dc_i**2 for dc_i in dc))

    @staticmethod
    def common_face(f1, f2):
        """
        Return True if two face collections share at least one geometrically equal plane.
        """
        for fi in f1:
            for fj in f2:
                if fi.getPlane().isEqual(fj.getPlane()):
                    return True
        return False

    @staticmethod
    def perpendicular_point_plane(hyperplane, point1):
        """
        Return the orthogonal projection of a point onto a plane.
        Returns None if the plane normal is degenerate.
        """
        denom = 0.0
        num = 0.0
        p1 = point1.get_double_point()
        plane = hyperplane.getPlane()

        for i in range(len(p1)):
            denom += plane[i] * plane[i]

        if denom == 0:
            return None

        num = -plane[-1]
        for i in range(len(p1)):
            num -= plane[i] * p1[i]

        t = num / denom
        return Point(
            p1[0] + plane[0] * t,
            p1[1] + plane[1] * t,
            p1[2] + plane[2] * t
        )

    @staticmethod
    def distance_point_plane(m, p):
        """Return the perpendicular distance from a point to a plane."""
        return abs(p.x * m.A + p.y * m.B + p.z * m.C + m.D) / math.sqrt(m.A**2 + m.B**2 + m.C**2)

    @staticmethod
    def is_inside(region, xyz):
        """Delegate inside-test to the region/volume implementation."""
        return region.isInside(xyz)

    @staticmethod
    def check_in_face(xyz, c, eps=1e-6):
        """
        Return True if the point lies on any face plane of the given volume,
        within the provided tolerance.
        """
        for face in c.getFaces():
            p = face.getPlane()
            if abs(p.evaluatePoint(xyz)) <= eps:
                return True
        return False

    @staticmethod
    def intersection_with_volume(v, p1, p2, eps=1e-9):
        """
        Intersect the ray starting at p1 and going through p2 with the closest
        face plane of the volume. Returns the nearest valid intersection point,
        or None if no forward intersection exists.
        """
        min_t = float('inf')
        p_result = None

        x0, y0, z0 = p1.x, p1.y, p1.z
        dx = p2.x - p1.x
        dy = p2.y - p1.y
        dz = p2.z - p1.z

        for face in v.getFaces():
            plane = face.getPlane()
            A, B, C, D = plane.A, plane.B, plane.C, plane.D

            denom = A * dx + B * dy + C * dz
            if abs(denom) <= eps:
                continue

            t = -(A * x0 + B * y0 + C * z0 + D) / denom

            # Ignore intersections behind the ray origin or too close to it.
            if t < eps:
                continue

            if t < min_t:
                min_t = t
                p_result = Point(x0 + t * dx, y0 + t * dy, z0 + t * dz)

        return p_result

    @staticmethod
    def intersection_plane_rect(hyperplane, point0, point1):
        """
        Intersect the line defined by point0 -> point1 with a plane.
        Returns None if the line is parallel to the plane.
        """
        denom = 0.0
        num = 0.0
        p0 = point0.get_double_point()
        p1 = point1.get_double_point()
        plane = hyperplane.getPlane()

        for i in range(len(p1)):
            denom += plane[i] * (p1[i] - p0[i])

        if denom == 0:
            return None

        num = -hyperplane.D
        for i in range(len(p1)):
            num -= plane[i] * p0[i]

        result = GeometryTools.point_at_rect(num / denom, p0, p1)
        return Point(result[0], result[1], result[2])

    @staticmethod
    def point_at_rect(t, p0, p1):
        """Return the point on the segment/line interpolation p0 + t * (p1 - p0)."""
        return [(p1[i] - p0[i]) * t + p0[i] for i in range(len(p0))]

    @staticmethod
    def module_double(v):
        """Return the Euclidean norm of a 3-component numeric sequence."""
        return math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)

    @staticmethod
    def check_planes(h1, h2):
        """Check exact coefficient equality between two planes."""
        return h1.A == h2.A and h1.B == h2.B and h1.C == h2.C and h1.D == h2.D

    @staticmethod
    def parallel_plane(p1, p2, alpha):
        """
        Build a plane parallel to the direction defined by two points and offset
        by a scaled distance. Returns None for unstable configurations.
        """
        n = [p2.x - p1.x, p2.y - p1.y, p2.z - p1.z]
        d = alpha * GeometryTools.module_double(n)

        if abs(n[0]) < GeometryTools.SMALL_NUM:
            return None

        x = d / math.sqrt(1 + n[1]**2 / n[0]**2 + n[2]**2 / n[0]**2)
        p = Point(x, x * n[1] / n[0], x * n[2] / n[0])

        return Plane(n[0], n[1], n[2], n[0] * p.x + n[1] * p.y + n[2] * p.z)

    @staticmethod
    def parallel_planes(p, dist):
        """
        Return the two planes parallel to a given plane at a signed offset distance.
        """
        n = p.getNormal()
        mod = GeometryTools.module(n)
        return [
            Plane(n.a, n.b, n.c, p.D + dist * mod),
            Plane(n.a, n.b, n.c, p.D - dist * mod)
        ]

    @staticmethod
    def mid_point(p1, p2):
        """Return the midpoint between two 3D points."""
        return Point(
            (p1.x + p2.x) / 2.0,
            (p1.y + p2.y) / 2.0,
            (p1.z + p2.z) / 2.0
        )

    @staticmethod
    def perpendicular_plane(p1, p2, mid):
        """
        Build the plane perpendicular to the segment p1-p2 and passing through mid.
        Returns None if the segment is degenerate.
        """
        A = p1.x - p2.x
        B = p1.y - p2.y
        C = p1.z - p2.z

        total = max(abs(A), max(abs(B), abs(C)))
        if total <= GeometryTools.SMALL_NUM:
            return None

        A /= total
        B /= total
        C /= total

        D = -((A * mid.x) + (B * mid.y) + (C * mid.z))
        return Plane(A, B, C, D)

    @staticmethod
    def equidistant_plane_two_points(p1, p2):
        """
        Return the plane formed by all points equidistant from p1 and p2.
        """
        A = p1.x - p2.x
        B = p1.y - p2.y
        C = p1.z - p2.z

        D = ((p2.x**2 - p1.x**2) + (p2.y**2 - p1.y**2) + (p2.z**2 - p1.z**2)) / 2.0
        return Plane(A, B, C, D)

    # ---------------------------
    # Utilities for clipping / reconstruction
    # ---------------------------

    @staticmethod
    def determinant3(a11, a12, a13, a21, a22, a23, a31, a32, a33):
        """Return the determinant of a 3x3 matrix."""
        return (
            a11 * (a22 * a33 - a23 * a32)
            - a12 * (a21 * a33 - a23 * a31)
            + a13 * (a21 * a32 - a22 * a31)
        )

    @staticmethod
    def intersect3_planes(p1, p2, p3, eps=1e-9):
        """
        Compute the unique intersection point of three planes.
        Returns None when the system is singular or nearly singular.
        """
        A1, B1, C1, D1 = p1.A, p1.B, p1.C, p1.D
        A2, B2, C2, D2 = p2.A, p2.B, p2.C, p2.D
        A3, B3, C3, D3 = p3.A, p3.B, p3.C, p3.D

        det = GeometryTools.determinant3(
            A1, B1, C1,
            A2, B2, C2,
            A3, B3, C3,
        )

        if abs(det) <= eps:
            return None

        dx = GeometryTools.determinant3(
            -D1, B1, C1,
            -D2, B2, C2,
            -D3, B3, C3,
        )
        dy = GeometryTools.determinant3(
            A1, -D1, C1,
            A2, -D2, C2,
            A3, -D3, C3,
        )
        dz = GeometryTools.determinant3(
            A1, B1, -D1,
            A2, B2, -D2,
            A3, B3, -D3,
        )

        return Point(dx / det, dy / det, dz / det)

    @staticmethod
    def point_satisfies_volume(volume, point, eps=1e-7):
        """
        Check whether a point satisfies all half-space constraints of a volume.
        """
        for face in volume.getFaces():
            plane = face.getPlane()
            s_rep = plane.evaluatePoint(volume.getRepresentative())
            s_p = plane.evaluatePoint(point)

            if s_rep * s_p < -eps:
                return False
        return True

    @staticmethod
    def unique_points(points, eps=1e-7):
        """
        Remove duplicate points using Euclidean distance and a tolerance threshold.
        """
        unique = []
        for p in points:
            exists = False
            for q in unique:
                if GeometryTools.euclidean_distance(p, q) <= eps:
                    exists = True
                    break
            if not exists:
                unique.append(p)
        return unique

    @staticmethod
    def face_basis_from_plane(plane):
        """
        Build a local orthonormal 2D basis on a plane for vertex ordering.
        Returns (None, None) if the plane normal is degenerate.
        """
        n = plane.getNormal()
        nmod = GeometryTools.module(n)
        if nmod <= GeometryTools.SMALL_NUM:
            return None, None

        nx = n.a / nmod

        # Choose a reference vector that is not parallel to the normal.
        if abs(nx) < 0.9:
            ref = Vector(1.0, 0.0, 0.0)
        else:
            ref = Vector(0.0, 1.0, 0.0)

        u = GeometryTools.cross_product(n, ref)
        umod = GeometryTools.module(u)
        if umod <= GeometryTools.SMALL_NUM:
            ref = Vector(0.0, 0.0, 1.0)
            u = GeometryTools.cross_product(n, ref)
            umod = GeometryTools.module(u)
            if umod <= GeometryTools.SMALL_NUM:
                return None, None

        u = Vector(u.a / umod, u.b / umod, u.c / umod)
        v = GeometryTools.cross_product(n, u)
        vmod = GeometryTools.module(v)
        if vmod <= GeometryTools.SMALL_NUM:
            return None, None

        v = Vector(v.a / vmod, v.b / vmod, v.c / vmod)
        return u, v

    @staticmethod
    def order_face_points(points, plane):
        """
        Order coplanar face vertices around their centroid using a local 2D basis.
        """
        if len(points) <= 2:
            return points[:]

        cx = sum(p.x for p in points) / len(points)
        cy = sum(p.y for p in points) / len(points)
        cz = sum(p.z for p in points) / len(points)
        center = Point(cx, cy, cz)

        u, v = GeometryTools.face_basis_from_plane(plane)
        if u is None or v is None:
            return points[:]

        def angle_of(p):
            dx = p.x - center.x
            dy = p.y - center.y
            dz = p.z - center.z

            pu = dx * u.a + dy * u.b + dz * u.c
            pv = dx * v.a + dy * v.b + dz * v.c
            return math.atan2(pv, pu)

        return sorted(points, key=angle_of)

    @staticmethod
    def rebuild_face_vertices(volume, eps=1e-7):
        """
        Rebuild each face polygon by collecting valid triple-plane intersections
        and ordering the resulting coplanar vertices.
        """
        faces = volume.getFaces()

        for i, face_i in enumerate(faces):
            plane_i = face_i.getPlane()
            pts = []

            for j, face_j in enumerate(faces):
                if j == i:
                    continue
                plane_j = face_j.getPlane()

                for k, face_k in enumerate(faces):
                    if k <= j or k == i:
                        continue
                    plane_k = face_k.getPlane()

                    p = GeometryTools.intersect3_planes(plane_i, plane_j, plane_k, eps=eps)
                    if p is None:
                        continue

                    if not GeometryTools.point_satisfies_volume(volume, p, eps=eps):
                        continue

                    # Keep only points that lie on the current face plane.
                    if abs(plane_i.evaluatePoint(p)) > eps * 10:
                        continue

                    pts.append(p)

            pts = GeometryTools.unique_points(pts, eps=eps)

            if len(pts) >= 3:
                pts = GeometryTools.order_face_points(pts, plane_i)
                face_i.setArrayVertex(pts)
                face_i.clearInfinity()
            else:
                face_i.setArrayVertex(None)
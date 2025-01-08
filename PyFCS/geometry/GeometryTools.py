import math
from typing import List

from PyFCS.geometry.Point import Point
from PyFCS.geometry.Vector import Vector
from PyFCS.geometry.Plane import Plane


class GeometryTools:
    SMALL_NUM = 0.000000001  # anything that avoids division overflow

    @staticmethod
    def dot(u, v):
        return u.a * v.a + u.b * v.b + u.c * v.c

    @staticmethod
    def plus(v, p):
        return Point(v.a + p.x, v.b + p.y, v.c + p.z)

    @staticmethod
    def minus(v, p):
        return Point(v.a - p.x, v.b - p.y, v.c - p.z)

    @staticmethod
    def scalar_product(v, s):
        return Vector(v.a * s, v.b * s, v.c * s)

    @staticmethod
    def cross_product(v, u):
        return Vector(v.b * u.c - v.c * u.b, v.c * u.a - v.a * u.c, v.b * u.a - v.a * u.b)

    @staticmethod
    def intersect2_planes(p1, p2):
        return None  # Implement your logic for intersecting two planes

    @staticmethod
    def is_same_direction(v, u):
        alpha = GeometryTools.dot(v, u) / (GeometryTools.module(v) * GeometryTools.module(u))
        return 1 - GeometryTools.SMALL_NUM < alpha < 1 + GeometryTools.SMALL_NUM

    @staticmethod
    def module(v):
        return math.sqrt(v.a**2 + v.b**2 + v.c**2)

    @staticmethod
    def euclidean_distance(point1, point2):
        p1 = point1.get_double_point()
        p2 = point2.get_double_point()
        dc = [p1[i] - p2[i] for i in range(len(p1))]
        dist = math.sqrt(sum(dc_i**2 for dc_i in dc))
        return dist

    @staticmethod
    def common_face(f1, f2):
        common = False
        for i in range(len(f1)):
            fi = f1[i]
            for j in range(len(f2)):
                fj = f2[j]
                if fi.plane == fj.plane:
                    common = True
        return common

    @staticmethod
    def perpendicular_point_plane(hyperplane, point1):
        denom = 0
        num = 0
        p1 = point1.get_double_point()
        plane = hyperplane.get_plane()

        for i in range(len(p1)):
            denom += plane[i] * plane[i]

        if denom == 0:
            return None
        else:
            num = -plane[-1]
            for i in range(len(p1)):
                num -= plane[i] * p1[i]
            t = num / denom
            return Point(p1[0] + plane[0] * t, p1[1] + plane[1] * t, p1[2] + plane[2] * t)

    @staticmethod
    def distance_point_plane(m, p):
        return abs(p.x * m.A + p.y * m.B + p.z * m.C + m.D) / math.sqrt(m.A**2 + m.B**2 + m.C**2)

    @staticmethod
    def is_inside(region, xyz):
        return region.is_inside(xyz)

    @staticmethod
    def check_in_face(xyz, c):
        in_face = False
        for i in range(len(c.faces)):
            p = c.faces[i].plane
            eval_result = p.evaluate_point(c.representative) * p.evaluate_point(xyz)

            if -1 * GeometryTools.SMALL_NUM < eval_result < GeometryTools.SMALL_NUM:
                in_face = True
        return in_face

    @staticmethod
    def intersection_with_volume(v, p1, p2):
        min_dist = float('inf')
        p_plane_k = None
        dir_vector = Vector.from_points(p1, p2)

        for j in range(len(v.faces)):
            plane = v.faces[j].p
            pk = GeometryTools.intersection_plane_rect(plane, p1, p2)
            if pk:
                dist_pk = GeometryTools.euclidean_distance(p1, pk)
                if GeometryTools.is_same_direction(dir_vector, Vector.from_points(p1, pk)) and dist_pk < min_dist:
                    min_dist = dist_pk
                    p_plane_k = pk

        return p_plane_k


    @staticmethod
    def intersection_plane_rect(hyperplane, point0, point1):
        denom = 0
        num = 0
        p0 = point0.get_double_point()
        p1 = point1.get_double_point()
        plane = hyperplane.getPlane()

        for i in range(len(p1)):
            denom += plane[i] * (p1[i] - p0[i])

        if denom == 0:
            return None
        else:
            num = hyperplane.D * -1
            for i in range(len(p1)):
                num -= plane[i] * p0[i]
            result = GeometryTools.point_at_rect(num / denom, p0, p1)
            return Point(result[0], result[1], result[2])

    @staticmethod
    def point_at_rect(t, p0, p1):
        return [(p1[i] - p0[i]) * t + p0[i] for i in range(len(p0))]

    @staticmethod
    def module_double(v):
        return math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)

    @staticmethod
    def check_planes(h1, h2):
        return h1.A == h2.A and h1.B == h2.B and h1.C == h2.C and h1.D == h2.D

    @staticmethod
    def parallel_plane(p1, p2, alpha):
        n = [p2.x - p1.x, p2.y - p1.y, p2.z - p1.z]
        d = alpha * GeometryTools.module_double(n)
        x = d / math.sqrt(1 + n[1]**2 / n[0]**2 + n[2]**2 / n[0]**2)
        p = Point(x, x * n[1] / n[0], x * n[2] / n[0])
        return Plane(n[0], n[1], n[2], n[0] * p.x + n[1] * p.y + n[2] * p.z)

    @staticmethod
    def parallel_planes(p, dist):
        n = p.getNormal()
        mod = GeometryTools.module(n)
        mu = [Plane(n.a, n.b, n.c, p.D + dist * mod), Plane(n.a, n.b, n.c, p.D - dist * mod)]
        return mu

    @staticmethod
    def mid_point(p1, p2):
        return Point((p1.x + p2.x) / 2.0, (p1.y + p2.y) / 2.0, (p1.z + p2.z) / 2.0)

    @staticmethod
    def perpendicular_plane(p1, p2, mid):
        A = p1.x - p2.x
        B = p1.y - p2.y
        C = p1.z - p2.z

        total = max(abs(A), max(abs(B), abs(C)))
        A /= total
        B /= total
        C /= total

        D = (A * mid.x) + (B * mid.y) + (C * mid.z) * -1.0

        return Plane(A, B, C, D)

    @staticmethod
    def equidistant_plane_two_points(p1, p2):
        A = p1.x - p2.x
        B = p1.y - p2.y
        C = p1.z - p2.z

        D = ((p2.x**2 - p1.x**2) + (p2.y**2 - p1.y**2) + (p2.z**2 - p1.z**2)) / 2.0

        return Plane(A, B, C, D)
    




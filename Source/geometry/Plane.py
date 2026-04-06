from Source.geometry.Vector import Vector
from Source.geometry.Point import Point


class Plane:
    def __init__(self, A: float, B: float, C: float, D: float):
        self.A = float(A)
        self.B = float(B)
        self.C = float(C)
        self.D = float(D)
        self.n = Vector(self.A, self.B, self.C)
        self.p = None

    @classmethod
    def from_array(cls, values):
        return cls(values[0], values[1], values[2], values[3])

    @classmethod
    def from_plane(cls, plane: 'Plane'):
        return cls(plane.A, plane.B, plane.C, plane.D)

    @classmethod
    def from_normal_point(cls, normal: Vector, p: Point):
        A = normal.a
        B = normal.b
        C = normal.c
        D = -1.0 * (p.x * A + p.y * B + p.z * C)
        obj = cls(A, B, C, D)
        obj.n = normal
        obj.p = p
        return obj

    def copy(self):
        return Plane(self.A, self.B, self.C, self.D)

    def evaluatePoint(self, xyz: Point) -> float:
        return xyz.x * self.A + xyz.y * self.B + xyz.z * self.C + self.D

    def getPlane(self):
        return [self.A, self.B, self.C, self.D]

    def getNormal(self) -> Vector:
        if self.n is None:
            return Vector(self.A, self.B, self.C)
        return self.n

    def getA(self) -> float:
        return self.A

    def getB(self) -> float:
        return self.B

    def getC(self) -> float:
        return self.C

    def getD(self) -> float:
        return self.D

    def normalized_tuple(self, eps=1e-12):
        norm = (self.A ** 2 + self.B ** 2 + self.C ** 2) ** 0.5
        if norm <= eps:
            return (0.0, 0.0, 0.0, 0.0)

        a = self.A / norm
        b = self.B / norm
        c = self.C / norm
        d = self.D / norm

        if (
            a < -eps or
            (abs(a) <= eps and b < -eps) or
            (abs(a) <= eps and abs(b) <= eps and c < -eps)
        ):
            a, b, c, d = -a, -b, -c, -d

        return (
            round(a, 12),
            round(b, 12),
            round(c, 12),
            round(d, 12),
        )

    def isEqual(self, plane: 'Plane', eps=1e-12) -> bool:
        return self.normalized_tuple(eps) == plane.normalized_tuple(eps)
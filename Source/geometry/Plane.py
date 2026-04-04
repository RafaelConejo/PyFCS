from Source.geometry.Vector import Vector
from Source.geometry.Point import Point

class Plane:
    def __init__(self, A: float, B: float, C: float, D: float):
        self.A = A
        self.B = B
        self.C = C
        self.D = D
        self.n = Vector(A, B, C)
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

    def evaluatePoint(self, xyz: Point) -> float:
        return xyz.x * self.A + xyz.y * self.B + xyz.z * self.C + self.D

    def getPlane(self):
        return [self.A, self.B, self.C, self.D]

    def isEqual(self, plane: 'Plane') -> bool:
        return self.A == plane.A and self.B == plane.B and self.C == plane.C and self.D == plane.D

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
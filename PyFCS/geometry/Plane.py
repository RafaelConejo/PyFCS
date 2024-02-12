from PyFCS.geometry.Vector import Vector
from PyFCS.geometry.Point import Point
import numpy as np

class Plane:
    def __init__(self, A: float, B: float, C: float, D: float):
        self.A = A
        self.B = B
        self.C = C
        self.D = D
        self.n = Vector(A, B, C)
        self.p = None

    @classmethod
    def from_point_and_normal(cls, point: Point, normal: Vector):
        A, B, C = normal.get_a(), normal.get_b(), normal.get_c()
        D = -(A * point.get_x() + B * point.get_y() + C * point.get_z())
        return cls(A, B, C, D)

    def evaluate_point(self, xyz):
        return xyz.get_x() * self.A + xyz.get_y() * self.B + xyz.get_z() * self.C + self.D

    def get_plane(self):
        return [self.A, self.B, self.C, self.D]

    def is_equal(self, plane):
        return self.A == plane.A and self.B == plane.B and self.C == plane.C and self.D == plane.D

    def get_normal(self):
        if self.n is None:
            return Vector(self.A, self.B, self.C)
        else:
            return self.n

    def get_A(self):
        return self.A

    def get_B(self):
        return self.B

    def get_C(self):
        return self.C

    def get_D(self):
        return self.D


    def distance_to_point(self, point):
        """
        Calcula la distancia perpendicular entre el plano y un punto.
        """
        if not isinstance(point, Point):
            raise ValueError("El argumento debe ser una instancia de la clase Point.")

        # Usa la fórmula de distancia entre un punto y un plano
        numerator = abs(self.A * point.get_x() + self.B * point.get_y() + self.C * point.get_z() + self.D)
        denominator = np.sqrt(self.A**2 + self.B**2 + self.C**2)

        return numerator / denominator
from geometry.Vector import Vector
class Plane:
    def __init__(self, A: float, B: float, C: float, D: float):
        self.A = A
        self.B = B
        self.C = C
        self.D = D
        self.n = Vector(A, B, C)
        self.p = None

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

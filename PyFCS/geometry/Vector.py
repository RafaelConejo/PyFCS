from PyFCS.geometry.Point import Point
import numpy as np

class Vector:
    def __init__(self, a=0, b=0, c=0):
        self.a = a
        self.b = b
        self.c = c

    @classmethod
    def from_points(cls, p1:Point, p2:Point):
        return cls(p2.get_x() - p1.get_x(), p2.get_y() - p1.get_y(), p2.get_z() - p1.get_z())

    @classmethod
    def from_array(cls, p):
        return cls(p[0], p[1], p[2])

    def get_a(self):
        return self.a

    def get_b(self):
        return self.b

    def get_c(self):
        return self.c

    def get_point(self):
        return [self.a, self.b, self.c]

    def is_equal(self, other_vector):
        return self.a == other_vector.get_a() and self.b == other_vector.get_b() and self.c == other_vector.get_c()

    def to_array(self):
            return np.array([self.a, self.b, self.c])
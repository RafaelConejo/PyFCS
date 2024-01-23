from geometry.Point import Point
from typing import List

class Vector:
    def __init__(self, a: float = 0, b: float = 0, c: float = 0):
        self.a = a
        self.b = b
        self.c = c

    def __init__(self, p1: Point, p2: Point):
        self.a = p2.get_x() - p1.get_x()
        self.b = p2.get_y() - p1.get_y()
        self.c = p2.get_z() - p1.get_z()

    def __init__(self, p: List[float]):
        self.a = p[0]
        self.b = p[1]
        self.c = p[2]

    def __init__(self, a: float, b: float, c: float):
        self.a = a
        self.b = b
        self.c = c

    def get_a(self):
        return self.a

    def get_b(self):
        return self.b

    def get_c(self):
        return self.c

    def get_point(self):
        return [self.a, self.b, self.c]

    def is_equal(self, p):
        return p.get_a() == self.a and p.get_b() == self.b and p.get_c() == self.c

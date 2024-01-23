from typing import List
from geometry.Point import Point
from geometry.Plane import Plane

class Face:
    def __init__(self, p: Plane, vertex: List[Point] = None, infinity: bool = False):
        self.p = p
        self.vertex = vertex if vertex is not None else []
        self.infinity = infinity

    def add_vertex(self, v: Point):
        if self.vertex is None:
            self.vertex = []
        self.vertex.append(v)

    def evaluate_point(self, xyz: Point):
        return self.p.get_A() * xyz.get_x() + self.p.get_B() * xyz.get_y() + self.p.get_C() * xyz.get_z() + self.p.get_D()

    def get_plane(self):
        return self.p

    def set_plane(self, plane: Plane):
        self.p = plane

    def get_array_vertex(self):
        return self.vertex

    def set_array_vertex(self, v: List[Point]):
        self.vertex = v

    def get_vertex(self, index: int):
        return self.vertex[index]

    def get_last_vertex(self):
        return self.vertex[-1]

    def is_infinity(self):
        return self.infinity

    def set_infinity(self):
        self.infinity = True

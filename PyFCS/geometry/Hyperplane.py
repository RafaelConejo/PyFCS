from PyFCS.geometry.Point import Point
from PyFCS.geometry.Plane import Plane

class Hyperplane(Plane):
    def __init__(self, A, B, C, D, p1=None, p2=None, index1=None, index2=None, in_value=True):
        super().__init__(A, B, C, D)
        self.point1 = p1
        self.point2 = p2
        self.index1 = index1
        self.index2 = index2
        self.in_value = in_value

    @classmethod
    def from_array(cls, plane, p1=None, p2=None, index1=None, index2=None, in_value=True):
        return cls(plane[0], plane[1], plane[2], plane[3], p1, p2, index1, index2, in_value)

    @classmethod
    def from_plane(cls, plane, p1=None, p2=None, index1=None, index2=None, in_value=True):
        return cls(plane.A, plane.B, plane.C, plane.D, p1, p2, index1, index2, in_value)
    
    @classmethod
    def from_list(cls, plane, in_value=True):
        return cls(plane[0], plane[1], plane[2], plane[3], in_value=in_value)


    def get_point1(self):
        return self.point1

    def get_point2(self):
        return self.point2

    def get_in(self):
        return self.in_value

    def get_index1(self):
        return self.index1

    def get_index2(self):
        return self.index2

    def set_point1(self, p1):
        self.point1 = p1

    def set_point2(self, p2):
        self.point2 = p2

    def set_index1(self, index1):
        self.index1 = index1

    def set_index2(self, index2):
        self.index2 = index2

    def set_in(self, in_value):
        self.in_value = in_value
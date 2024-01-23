from geometry.Point import Point
from geometry.Plane import Plane

class Hyperplane(Plane):
    def __init__(self, A, B, C, D, point1=None, point2=None, index1=None, index2=None, in_flag=True):
        super().__init__(A, B, C, D)
        self.point1 = point1
        self.point2 = point2
        self.index1 = index1
        self.index2 = index2
        self.in_flag = in_flag

    def set_point1(self, point1):
        self.point1 = point1

    def set_point2(self, point2):
        self.point2 = point2

    def set_index1(self, index1):
        self.index1 = index1

    def set_index2(self, index2):
        self.index2 = index2

    def set_in_flag(self, in_flag):
        self.in_flag = in_flag

# Ejemplo de uso
# hyperplane = Hyperplane(A=1, B=2, C=3, D=4, point1=Point(1, 2, 3), point2=Point(4, 5, 6), index1=0, index2=1, in_flag=True)
from typing import List
from PyFCS.geometry.Vector import Vector
from PyFCS.geometry.Point import Point

class Plane:
    def __init__(self, A: float, B: float, C: float, D: float):
        self.A = A
        self.B = B
        self.C = C
        self.D = D
        self.n = Vector(A, B, C)
        self.p = None
    
    def evaluatePoint(self, xyz: Point) -> float:
        return xyz.get_x() * self.A + xyz.get_y() * self.B + xyz.get_z() * self.C + self.D
    
    def getPlane(self) -> List[float]:
        return [self.A, self.B, self.C, self.D]
    
    def isEqual(self, plane: 'Plane') -> bool:
        return (self.A == plane.A) and (self.B == plane.B) and (self.C == plane.C) and (self.D == plane.D)
    
    def getNormal(self) -> Vector:
        if self.n is None:
            return [self.A, self.B, self.C]
        else:
            return self.n
    
    def getA(self) -> float:
        return self.A
    
    def getB(self) -> float:
        return self.B
    
    def getC(self) -> float:
        return self.C
    
    def getD(self) -> float:
        return self.D

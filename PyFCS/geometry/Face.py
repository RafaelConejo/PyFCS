from typing import List
from PyFCS.geometry.Point import Point
from PyFCS.geometry.Plane import Plane
from PyFCS.geometry.Vector import Vector

class Face:
    def __init__(self, p: Plane, vertex: List[Point] = None, bounded: bool = False):
        self.p = p
        self.vertex = vertex 
        self.bounded = bounded
    
    def addVertex(self, v: Point):
        if self.vertex is None:
            self.vertex = []
        self.vertex.append(v)
    
    def evaluatePoint(self, xyz: Point) -> float:
        return self.p.evaluatePoint(xyz)
    
    def getPlane(self) -> Plane:
        return self.p
    
    def setPlane(self, plane: Plane):
        self.p = plane
    
    def getArrayVertex(self) -> List[Point]:
        return self.vertex
    
    def setArrayVertex(self, v: List[Point]):
        self.vertex = v
    
    def getVertex(self, index: int) -> Point:
        return self.vertex[index]
    
    def getLastVertex(self) -> Point:
        return self.vertex[-1]
    
    def isBounded(self) -> bool:
        return self.bounded
    
    def setBounded(self):
        self.bounded = True

from typing import List
from Source.geometry.Point import Point
from Source.geometry.Plane import Plane


class Face:
    def __init__(self, p: Plane, vertex: List[Point] = None, infinity: bool = False, is_false_boundary: bool = False, source_index: int = None):
        self.p = p
        if isinstance(vertex, bool):
            infinity = vertex
            vertex = None

        self.vertex = vertex[:] if vertex is not None else None
        self.infinity = infinity

        # Metadata extra
        self.is_false_boundary = is_false_boundary
        self.source_index = source_index

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

    def isInfinity(self) -> bool:
        return self.infinity

    def setInfinity(self):
        self.infinity = True

    def isFalseBoundary(self) -> bool:
        return self.is_false_boundary

    def setFalseBoundary(self, value: bool):
        self.is_false_boundary = value

    def getSourceIndex(self):
        return self.source_index

    def setSourceIndex(self, index: int):
        self.source_index = index

    def copy(self):
        copied_vertices = None
        if self.vertex is not None:
            copied_vertices = [Point(v.x, v.y, v.z) for v in self.vertex]

        return Face(
            p=Plane(self.p.A, self.p.B, self.p.C, self.p.D),
            vertex=copied_vertices,
            infinity=self.infinity,
            is_false_boundary=self.is_false_boundary,
            source_index=self.source_index,
        )
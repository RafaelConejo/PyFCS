from Source.geometry.GeometryTools import GeometryTools
from Source.geometry.Face import Face
from Source.geometry.Point import Point

class Volume:
    def __init__(self, representative: Point, faces=None):
        self.faces = faces if faces is not None else []
        self.representative = representative

    def getFaces(self):
        return self.faces

    def getRepresentative(self):
        return self.representative

    def setRepresentative(self, representative: Point):
        self.representative = representative

    def isInFace(self, xyz: Point, eps=GeometryTools.SMALL_NUM):
        for face in self.faces:
            plane = face.getPlane()
            if abs(plane.evaluatePoint(xyz)) <= eps:
                return True
        return False

    def isInside(self, xyz: Point, eps=GeometryTools.SMALL_NUM):
        for face in self.faces:
            plane = face.getPlane()
            s_rep = plane.evaluatePoint(self.representative)
            s_xyz = plane.evaluatePoint(xyz)

            if s_rep * s_xyz < -eps:
                return False
        return True

    def addFace(self, face: Face):
        self.faces.append(face)

    def getFace(self, index: int) -> Face:
        return self.faces[index]

    def clear(self):
        self.faces.clear()
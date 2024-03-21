from PyFCS.geometry.GeometryTools import GeometryTools
from PyFCS.geometry.Face import Face
from PyFCS.geometry.Point import Point

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
    
    def isInFace(self, xyz: Point):
        for face in self.faces:
            plane = face.getPlane()
            eval_value = plane.evaluatePoint(self.representative) * plane.evaluatePoint(xyz)
            if -1 * GeometryTools.SMALL_NUM < eval_value < GeometryTools.SMALL_NUM:
                return True
        return False
    
    def isInside(self, xyz: Point):
        for face in self.faces:
            eval_value = face.evaluatePoint(self.representative) * face.evaluatePoint(xyz)
            if eval_value < -1.0 * GeometryTools.SMALL_NUM:
                return False
        return True
    
    def addFace(self, face: Face):
        self.faces.append(face)
    
    def getFace(self, index: int) -> Face:
        return self.faces[index]
    
    def clear(self):
        self.faces.clear()


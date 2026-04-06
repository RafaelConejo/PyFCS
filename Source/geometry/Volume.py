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

    def addFaces(self, faces):
        for face in faces:
            self.addFace(face)

    def getFace(self, index: int) -> Face:
        return self.faces[index]

    def clear(self):
        self.faces.clear()

    def copy(self):
        return Volume(
            representative=Point(
                self.representative.x,
                self.representative.y,
                self.representative.z,
            ),
            faces=[face.copy() for face in self.faces],
        )

    def finite_faces(self):
        return [face for face in self.faces if not face.isInfinity()]

    def infinite_faces(self):
        return [face for face in self.faces if face.isInfinity()]

    def has_infinite_faces(self):
        return any(face.isInfinity() for face in self.faces)

    def remove_infinite_faces(self):
        self.faces = [face for face in self.faces if not face.isInfinity()]

    def add_domain_faces_from_volume(self, domain_volume):
        for face in domain_volume.getFaces():
            copied = face.copy()
            copied.setDomainBoundary(True)
            copied.clearInfinity()
            self.addFace(copied)

    def deduplicate_planes(self, eps=1e-12):
        unique = []
        seen = set()

        for face in self.faces:
            key = face.getPlane().normalized_tuple(eps)
            if key in seen:
                continue
            seen.add(key)
            unique.append(face)

        self.faces = unique
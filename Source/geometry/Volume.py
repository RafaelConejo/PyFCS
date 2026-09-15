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
        """Return True when *xyz* lies inside or on the boundary of the volume.

        The representative normally determines the interior side of every face.
        For the rare case in which the representative lies exactly on a face
        (for example, a prototype located on the CIELAB domain boundary), the
        interior side is inferred from another vertex of the same polyhedron.
        """
        if not self.faces:
            return False

        for face in self.faces:
            plane = face.getPlane()
            s_rep = plane.evaluatePoint(self.representative)
            s_xyz = plane.evaluatePoint(xyz)

            if abs(s_rep) > eps:
                if s_rep * s_xyz < -eps:
                    return False
                continue

            # Degenerate orientation case: the representative is on this face.
            # Infer the interior half-space from any polyhedron vertex that is
            # clearly not coplanar with the current face. This fallback is only
            # used for boundary representatives, so it does not affect the hot
            # membership path for ordinary prototypes.
            interior_sign = 0.0
            for other_face in self.faces:
                vertices = other_face.getArrayVertex()
                if not vertices:
                    continue

                for vertex in vertices:
                    s_vertex = plane.evaluatePoint(vertex)
                    if abs(s_vertex) > eps:
                        interior_sign = 1.0 if s_vertex > 0.0 else -1.0
                        break

                if interior_sign != 0.0:
                    break

            # If every known vertex is coplanar, this face cannot provide a
            # reliable half-space constraint, so leave the decision to the
            # remaining faces.
            if interior_sign == 0.0:
                continue

            if interior_sign * s_xyz < -eps:
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
from geometry.GeometryTools import GeometryTools

class Volume:
    def __init__(self, representative=None, faces=None):
        self.faces = faces if faces is not None else []
        self.representative = representative

    def get_faces(self):
        return self.faces

    def get_representative(self):
        return self.representative

    def set_representative(self, representative):
        self.representative = representative

    def is_in_face(self, xyz):
        in_face = False
        for i in range(len(self.get_faces())):
            p = self.get_faces()[i].get_plane()
            eval_result = p.evaluate_point(self.get_representative()) * p.evaluate_point(xyz)

            if -1.0 * GeometryTools.SMALL_NUM < eval_result < GeometryTools.SMALL_NUM:
                in_face = True

        return in_face

    def is_inside(self, xyz):
        in_volume = True

        for i in range(len(self.get_faces())):
            p = self.get_faces()[i]
            eval_result = p.evaluate_point(self.get_representative()) * p.evaluate_point(xyz)

            if eval_result < GeometryTools.SMALL_NUM * -1.0:
                in_volume = False

        return in_volume

    def add_face(self, face):
        self.faces.append(face)

    def get_face(self, index):
        return self.faces[index]

    def clear(self):
        self.faces.clear()

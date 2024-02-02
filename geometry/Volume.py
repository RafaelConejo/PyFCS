from geometry.GeometryTools import GeometryTools
from geometry.Point import Point

class Volume:
    def __init__(self, representative:Point, faces=None):
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

            # Create a Point instance from the NumPy array
            xyz_point = Point(xyz.get_x(), xyz.get_y(), xyz.get_z())

            eval_result = p.evaluate_point(self.get_representative()) * p.evaluate_point(xyz_point)

            if eval_result < GeometryTools.SMALL_NUM * -1.0:
                in_volume = False

        return in_volume

    def add_face(self, face):
        self.faces.append(face)

    def get_face(self, index):
        return self.faces[index]

    def clear(self):
        self.faces.clear()

    def compute_volume(self):
        # Implementa el cálculo del volumen utilizando las caras y el representante
        # Aquí puedes usar algún método de integración o aproximación para calcular el volumen

        # Ejemplo básico: calcula el volumen como el producto del área de cada cara por la distancia al representante
        total_volume = 0
        for face in self.faces:
            area = face.compute_area()  # Necesitarás implementar este método en la clase Face
            distance_to_representative = face.p.distance_to_point(self.representative)  # Necesitarás implementar esto en la clase Plane
            total_volume += area * distance_to_representative

        return total_volume

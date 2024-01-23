from geometry.Volume import Volume
from geometry.Point import Point
from geometry.Face import Face
from geometry.Hyperplane import Hyperplane

class ReferenceDomain:
    def __init__(self, c1, c2, c3):
        self.comp1 = c1
        self.comp2 = c2
        self.comp3 = c3
        self.reference = [self.comp1, self.comp2, self.comp3]
        self.dimension = 3
        self.volume = self.create_volume()

    def create_volume(self):
        num_components = 3
        comp = 0
        num_planes = num_components * 2
        num_variables = num_components + 1

        cube = Volume(Point((self.comp1[1] - self.comp1[0]) / 2.0,
                            (self.comp2[1] - self.comp2[0]) / 2.0,
                            (self.comp3[1] - self.comp3[0]) / 2.0))

        for i in range(num_planes):
            plane = [1 if j != comp else 0 for j in range(num_variables - 1)]

            if i % 2 == 0:
                plane.append(self.reference[comp][0])
            else:
                plane.append(self.reference[comp][1] * -1)
                comp += 1

            cube.add_face(Face(Hyperplane(plane, False), False))

        return cube

    def get_domain(self, dimension):
        if dimension == 0:
            return self.comp1
        elif dimension == 1:
            return self.comp2
        elif dimension == 2:
            return self.comp3
        else:
            return None

    def get_min(self, dimension):
        return self.get_domain(dimension)[0]

    def get_max(self, dimension):
        return self.get_domain(dimension)[1]

    def get_volume(self):
        return self.volume

    def domain_transform(self, x, a, b, c, d):
        return (((x - a) / (b - a)) * (d - c)) + c

    def transform(self, x, d):
        return Point(
            self.domain_transform(x.get_x(), d.comp1[0], d.comp1[1], self.comp1[0], self.comp1[1]),
            self.domain_transform(x.get_y(), d.comp2[0], d.comp2[1], self.comp2[0], self.comp2[1]),
            self.domain_transform(x.get_z(), d.comp3[0], d.comp3[1], self.comp3[0], self.comp3[1])
        )

    def transform_default(self, x):
        return self.transform(x, ReferenceDomain([0, 1], [0, 1], [0, 1]))

    def get_dimension(self):
        return self.dimension

    def is_inside(self, p):
        return (
            self.get_min(0) <= p.get_x() <= self.get_max(0) and
            self.get_min(1) <= p.get_y() <= self.get_max(1) and
            self.get_min(2) <= p.get_z() <= self.get_max(2)
        )

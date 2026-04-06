from Source.geometry.Volume import Volume
from Source.geometry.Point import Point
from Source.geometry.Face import Face
from Source.geometry.Plane import Plane


class ReferenceDomain:
    def __init__(self, c1min, c1max, c2min, c2max, c3min, c3max):
        self.comp1 = [c1min, c1max]
        self.comp2 = [c2min, c2max]
        self.comp3 = [c3min, c3max]

        self.dimension = 3
        self.reference = [self.comp1, self.comp2, self.comp3]
        self.volume = self.create_volume()

    @staticmethod
    def default_voronoi_reference_domain():
        return ReferenceDomain(0, 100, -128, 128, -128, 128)

    def get_domain(self, dimension):
        return self.comp1 if dimension == 0 else (self.comp2 if dimension == 1 else self.comp3)

    def get_min(self, dimension):
        return self.get_domain(dimension)[0]

    def get_max(self, dimension):
        return self.get_domain(dimension)[1]

    def get_volume(self):
        return self.volume

    def create_volume(self):
        c1min, c1max = self.comp1
        c2min, c2max = self.comp2
        c3min, c3max = self.comp3

        cube = Volume(
            Point(
                (c1min + c1max) / 2.0,
                (c2min + c2max) / 2.0,
                (c3min + c3max) / 2.0,
            )
        )

        # x >= c1min  ->  x - c1min >= 0
        cube.addFace(Face(Plane(1.0, 0.0, 0.0, -c1min), infinity=False, is_domain_boundary=True))

        # x <= c1max  -> -x + c1max >= 0
        cube.addFace(Face(Plane(-1.0, 0.0, 0.0, c1max), infinity=False, is_domain_boundary=True))

        # y >= c2min
        cube.addFace(Face(Plane(0.0, 1.0, 0.0, -c2min), infinity=False, is_domain_boundary=True))

        # y <= c2max
        cube.addFace(Face(Plane(0.0, -1.0, 0.0, c2max), infinity=False, is_domain_boundary=True))

        # z >= c3min
        cube.addFace(Face(Plane(0.0, 0.0, 1.0, -c3min), infinity=False, is_domain_boundary=True))

        # z <= c3max
        cube.addFace(Face(Plane(0.0, 0.0, -1.0, c3max), infinity=False, is_domain_boundary=True))

        return cube

    def domain_transform(self, x, a, b, c, d):
        return ((((x - a) / (b - a)) * (d - c)) + c)

    def transform(self, x, d):
        return Point(
            self.domain_transform(x.get_x(), d.comp1[0], d.comp1[1], self.comp1[0], self.comp1[1]),
            self.domain_transform(x.get_y(), d.comp2[0], d.comp2[1], self.comp2[0], self.comp2[1]),
            self.domain_transform(x.get_z(), d.comp3[0], d.comp3[1], self.comp3[0], self.comp3[1])
        )

    def transform_default_domain(self, x):
        return self.transform(x, ReferenceDomain(0, 1, 0, 1, 0, 1))

    def get_dimension(self):
        return self.dimension

    def is_inside(self, p):
        return (
            self.get_min(0) <= p.get_x() <= self.get_max(0) and
            self.get_min(1) <= p.get_y() <= self.get_max(1) and
            self.get_min(2) <= p.get_z() <= self.get_max(2)
        )
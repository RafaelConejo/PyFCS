from Source.geometry.Volume import Volume
from Source.geometry.Point import Point
from Source.geometry.Face import Face
from Source.geometry.Plane import Plane


class ReferenceDomain:
    """
    Axis-aligned 3D reference domain used throughout PyFCS.

    The default CIELAB bounds are defined here once so geometry, validation,
    visualization, and UI helpers all share the same limits.
    """

    DEFAULT_L_MIN = 0.0
    DEFAULT_L_MAX = 100.0
    DEFAULT_A_MIN = -128.0
    DEFAULT_A_MAX = 128.0
    DEFAULT_B_MIN = -128.0
    DEFAULT_B_MAX = 128.0

    def __init__(self, c1min, c1max, c2min, c2max, c3min, c3max):
        self.comp1 = [c1min, c1max]
        self.comp2 = [c2min, c2max]
        self.comp3 = [c3min, c3max]

        self.dimension = 3
        self.reference = [self.comp1, self.comp2, self.comp3]
        self.volume = self.create_volume()

    @classmethod
    def default_voronoi_reference_domain(cls):
        return cls(
            cls.DEFAULT_L_MIN,
            cls.DEFAULT_L_MAX,
            cls.DEFAULT_A_MIN,
            cls.DEFAULT_A_MAX,
            cls.DEFAULT_B_MIN,
            cls.DEFAULT_B_MAX,
        )

    @classmethod
    def is_valid_lab_values(cls, L, a, b, eps=0.0):
        return (
            cls.DEFAULT_L_MIN - eps <= float(L) <= cls.DEFAULT_L_MAX + eps
            and cls.DEFAULT_A_MIN - eps <= float(a) <= cls.DEFAULT_A_MAX + eps
            and cls.DEFAULT_B_MIN - eps <= float(b) <= cls.DEFAULT_B_MAX + eps
        )

    def contains_coordinates(self, coordinates, eps=0.0):
        try:
            x, y, z = coordinates
        except Exception:
            return False

        return (
            self.comp1[0] - eps <= float(x) <= self.comp1[1] + eps
            and self.comp2[0] - eps <= float(y) <= self.comp2[1] + eps
            and self.comp3[0] - eps <= float(z) <= self.comp3[1] + eps
        )

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
        return self.contains_coordinates((p.get_x(), p.get_y(), p.get_z()))

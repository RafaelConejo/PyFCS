from PyFCS.geometry.Volume import Volume
from PyFCS.geometry.Point import Point
from PyFCS.geometry.Face import Face
from PyFCS.geometry.Hyperplane import Hyperplane

class ReferenceDomain:
    # def __init__(self, c1=None, c2=None, c3=None):
    #     self.comp1 = c1 if c1 is not None else [0, 0]
    #     self.comp2 = c2 if c2 is not None else [0, 0]
    #     self.comp3 = c3 if c3 is not None else [0, 0]
        
    #     self.reference = [self.comp1, self.comp2, self.comp3]
        
    #     self.dimension = 3
    #     self.volume = self.create_volume()

    def __init__(self, c1min, c1max, c2min, c2max, c3min, c3max):
        # Inicialización de los componentes con los límites dados
        self.comp1 = [c1min, c1max]
        self.comp2 = [c2min, c2max]
        self.comp3 = [c3min, c3max]
        
        # Asignar los componentes a la referencia
        self.dimension = 3
        self.reference = [self.comp1, self.comp2, self.comp3]
        
        # Crear el volumen
        self.volume = self.create_volume()

    @staticmethod
    def default_voronoi_reference_domain():
        # Asumiendo que los rangos típicos de LAB son aproximadamente [0, 100] para L, [-128, 128] para A, y [-128, 128] para B.
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
        num_components = 3
        comp = 0
        num_planes = num_components * 2
        num_variables = num_components + 1

        cube = Volume(Point((self.comp1[1] - self.comp1[0]) / 2.0, (self.comp2[1] - self.comp2[0]) / 2.0, (self.comp3[1] - self.comp3[0]) / 2.0))

        for i in range(num_planes):
            plane = [0.0] * num_variables
            j = 0

            for j in range(num_variables - 1):
                if j == comp:
                    plane[j] = 1.0

            if i % 2 == 0:
                plane[j] = self.reference[comp][0]
            else:
                plane[j] = self.reference[comp][1] * -1
                comp += 1

            cube.addFace(Face(Hyperplane.from_list(plane, in_value=False), False))

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
        return (self.get_min(0) <= p.get_x() <= self.get_max(0) and
                self.get_min(1) <= p.get_y() <= self.get_max(1) and
                self.get_min(2) <= p.get_z() <= self.get_max(2))




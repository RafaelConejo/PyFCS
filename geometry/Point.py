
class Point:
    def __init__(self, x: float = 0, y: float = 0, z: float = 0):
        self.x = x
        self.y = y
        self.z = z

    def set_x(self, x):
        self.x = x

    def set_y(self, y):
        self.y = y

    def set_z(self, z):
        self.z = z

    def get_x(self):
        return self.x

    def get_y(self):
        return self.y

    def get_z(self):
        return self.z

    def get_component(self, index):
        if index == 0:
            return self.x
        elif index == 1:
            return self.y
        elif index == 2:
            return self.z
        else:
            return 0

    def get_double_point(self):
        return [self.x, self.y, self.z]

    def get_float_point(self):
        return [float(self.x), float(self.y), float(self.z)]

    def get_float_round_point(self):
        return [int(self.x), int(self.y), int(self.z)]

    def is_equal(self, p):
        return p.get_x() == self.x and p.get_y() == self.y and p.get_z() == self.z

    def is_equal_with_reference(self, p, ref, epsilon):
        return (
            abs(p.get_x() - self.x) / ref.get_max(0) < epsilon
            and abs(p.get_y() - self.y) / ref.get_max(1) < epsilon
            and abs(p.get_z() - self.z) / ref.get_max(2) < epsilon
        )

    # def is_equal_with_epsilon(self, p, epsilon):
    #     return GeometryTools.euclidean_distance(self, p) < epsilon

    def __str__(self):
        return "[" + str(self.x) + ", " + str(self.y) + ", " + str(self.z) + "]"

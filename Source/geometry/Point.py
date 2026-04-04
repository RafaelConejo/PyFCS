class Point:
    def __init__(self, x=0.0, y=None, z=None):
        if y is None and z is None and isinstance(x, (list, tuple)):
            self.x = x[0]
            self.y = x[1]
            self.z = x[2]
        else:
            self.x = x
            self.y = 0.0 if y is None else y
            self.z = 0.0 if z is None else z

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

    def is_equal_with_epsilon(self, p, epsilon):
        dx = self.x - p.get_x()
        dy = self.y - p.get_y()
        dz = self.z - p.get_z()
        return (dx * dx + dy * dy + dz * dz) ** 0.5 < epsilon

    def __str__(self):
        return f"[{self.x}, {self.y}, {self.z}]"
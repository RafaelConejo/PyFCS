

class ReferenceDomain:
    def __init__(self, min_l, max_l, min_a, max_a, min_b, max_b):
        self.domain = [[min_l, max_l], [min_a, max_a], [min_b, max_b]]

    def get_domain(self, dimension):
        return self.domain[dimension]

    @staticmethod
    def default_voronoi_reference_domain():
        # Asumiendo que los rangos típicos de LAB son aproximadamente [0, 100] para L, [-128, 128] para A, y [-128, 128] para B.
        return ReferenceDomain(0.0, 100.0, -128.0, 128.0, -128.0, 128.0)

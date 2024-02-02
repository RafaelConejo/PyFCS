from typing import List
import numpy as np
from geometry.Point import Point
from geometry.Plane import Plane
from geometry.Vector import Vector

class Face:
    def __init__(self, p: Plane, vertex: List[Point] = None, infinity: bool = False):
        self.p = p
        self.vertex = vertex 
        self.infinity = infinity

    @classmethod
    def from_voronoi_region(cls, voronoi, region_index):
        # Get the vertices of the Voronoi region
        region_vertices = [voronoi.vertices[i] for i in voronoi.regions[region_index]]

        # Assume the normal vector of the plane points outward
        normal_vector = Vector.from_array(np.cross(region_vertices[1] - region_vertices[0], region_vertices[2] - region_vertices[0]))

        # Create a Plane instance using the first three vertices of the region
        plane = Plane.from_point_and_normal(Point(region_vertices[0][0], region_vertices[0][1], region_vertices[0][2]), normal_vector)

        # Create a Face instance using the vertices and the created plane
        face = cls(p=plane)
        face.set_array_vertex(region_vertices)

        return face

    def add_vertex(self, v: Point):
        if self.vertex is None:
            self.vertex = []
        self.vertex.append(v)

    def evaluate_point(self, xyz: Point):
        if not isinstance(self.p, Plane):
            raise ValueError("El plano 'p' no está definido para esta cara.")
        else:
            return self.p.evaluate_point(xyz)

    def get_plane(self):
        return self.p

    def set_plane(self, plane: Plane):
        self.p = plane

    def get_array_vertex(self):
        return self.vertex

    def set_array_vertex(self, v: List[Point]):
        self.vertex = v

    def get_vertex(self, index: int):
        return self.vertex[index]

    def get_last_vertex(self):
        return self.vertex[-1]

    def is_infinity(self):
        return self.infinity

    def set_infinity(self):
        self.infinity = True

    def compute_area(self):
        if self.vertex is None or len(self.vertex) < 3:
            raise ValueError("La cara no tiene suficientes vértices para calcular el área.")

        total_area = 0

        # Subdividir el polígono en triángulos y sumar las áreas de cada triángulo
        for i in range(1, len(self.vertex) - 1):
            A, B, C = self.vertex[0], self.vertex[i], self.vertex[i + 1]

            # Calcular el área del triángulo ABC
            area_triangle = self.calculate_triangle_area(A, B, C)

            total_area += area_triangle

        return total_area
    

    @staticmethod
    def calculate_triangle_area(A, B, C):
        # Calcula el vector AB
        vector_AB = [B[0] - A[0], B[1] - A[1], B[2] - A[2]]

        # Calcula el vector AC
        vector_AC = [C[0] - A[0], C[1] - A[1], C[1] - A[1]]

        # Calcula el producto cruz entre AB y AC
        cross_product = [
            vector_AB[1] * vector_AC[2] - vector_AB[2] * vector_AC[1],
            vector_AB[2] * vector_AC[0] - vector_AB[0] * vector_AC[2],
            vector_AB[0] * vector_AC[1] - vector_AB[1] * vector_AC[0]
        ]

        # Calcula la magnitud del producto cruz y divide por 2 para obtener el área
        area = 0.5 * (cross_product[0]**2 + cross_product[1]**2 + cross_product[2]**2)**0.5

        return area
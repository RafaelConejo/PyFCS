from scipy.spatial import Voronoi, voronoi_plot_2d
from scipy.spatial import ConvexHull
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from typing import List

### my libraries ###
# from PyFCS.geometry.Plane import Plane
from PyFCS.geometry.Point import Point
from PyFCS.geometry.GeometryTools import GeometryTools
from PyFCS.geometry.Face import Face
from PyFCS.geometry.Volume import Volume
from PyFCS.geometry.Vector import Vector

from matplotlib.collections import LineCollection
from matplotlib.collections import PolyCollection
from matplotlib.patches import Polygon
from scipy.interpolate import interp1d

class Plane:
    def __init__(self, A, B, C):
        self.A = A
        self.B = B
        self.C = C

    def getPlane(self) -> List[float]:
        return [self.A, self.B, self.C]

class Prototype:
    def __init__(self, label, positive, negatives):
        self.label = label
        self.positive = positive
        self.negatives = negatives

        # Create Voronoi volume
        self.voronoi_volume = self.create_voronoi_volume()


    def calculate_plane(self, vertices):
        # Calcular el vector normal al plano
        v1 = vertices[1] - vertices[0]
        v2 = vertices[2] - vertices[0]
        normal = np.cross(v1, v2)
        normal /= np.linalg.norm(normal)
        
        # Calcular la distancia desde el origen al plano
        distance = -np.dot(normal, vertices[0])
        
        # Coeficientes del plano en la forma ax + by + cz + d = 0
        A, B, C = normal
        D = distance
        
        return Plane(A, B, C, D)



    # Calcula el plano para un segmento infinito
    def create_voronoi_volume(self):
        points = np.array([[0, 0], [0, 1.5], [0, 2], [1, 0], [1, 1], [1, 2], [2, 0], [2, 1], [2, 2]])
        vor = Voronoi(points, qhull_options='Fi Fo p Fv')

        first_point_volumes = []  # Lista para almacenar los volúmenes del primer punto

        for i, point in enumerate(vor.points):
            if i == 0:  # Solo calcular los volúmenes del primer punto
                center = vor.points.mean(axis=0)
                ptp_bound = np.ptp(vor.points, axis=0)

                finite_planes = []
                infinite_planes = []
                for pointidx, simplex in zip(vor.ridge_points, vor.ridge_vertices):
                    simplex = np.asarray(simplex)
                    if np.all(simplex >= 0):
                        finite_planes.append(vor.vertices[simplex])
                    else:
                        i = simplex[simplex >= 0][0]  # finite end Voronoi vertex

                        t = vor.points[pointidx[1]] - vor.points[pointidx[0]]  # tangent
                        t /= np.linalg.norm(t)
                        n = np.array([-t[1], t[0]])  # normal

                        midpoint = vor.points[pointidx].mean(axis=0)
                        direction = np.sign(np.dot(midpoint - center, n)) * n
                        if (vor.furthest_site):
                            direction = -direction
                        aspect_factor = abs(ptp_bound.max() / ptp_bound.min())
                        far_point = vor.vertices[i] + direction * ptp_bound.max() * aspect_factor

                        # Crear el plano que representa el segmento infinito y añadirlo a la lista de planos
                        infinite_planes.append([vor.vertices[i], far_point])

                # Almacenar información de las celdas Voronoi en volumes
                for region_indices in vor.regions:
                    vertices = [vor.vertices[idx] for idx in region_indices]
                    volume_obj = Volume(representative=Point(*vor.points[i]))

                    # Agregar los planos finitos a las caras del volumen
                    for plane_points in finite_planes:
                        vertices = [point for point in plane_points]
                        if len(plane_points) >= 2:  # Verifica que haya al menos dos puntos para definir un segmento de línea
                            # Calcula los coeficientes de la ecuación del plano Ax + By + C = 0
                            A = plane_points[1][1] - plane_points[0][1]
                            B = plane_points[0][0] - plane_points[1][0]
                            C = -(A * plane_points[0][0] + B * plane_points[0][1])
                            plane = Plane(A, B, C)
                            volume_obj.addFace(Face(p=plane, vertex=vertices, bounded=True))

                    # Agregar los planos infinitos a las caras del volumen
                    for line_points in infinite_planes:
                        # Creamos un plano a partir de los dos puntos que definen la línea
                        A = line_points[1][1] - line_points[0][1]
                        B = line_points[0][0] - line_points[1][0]
                        C = -(A * line_points[0][0] + B * line_points[0][1])
                        plane = Plane(A, B, C)
                        
                        # Creamos la cara con el plano asociado y los vértices
                        vertices = [point for point in line_points]
                        volume_obj.addFace(Face(p=plane, vertex=vertices, bounded=False))

                    first_point_volumes.append(volume_obj)





                    self.plot_voronoi_planes(volume_obj, points)








        





        # voronoi_proj = Voronoi(points[:, :2], qhull_options='Fi Fo p Fv')

        # # Visualization code
        # plt.figure(figsize=(8, 8))

        # # Plot Voronoi diagram
        # voronoi_plot_2d(voronoi_proj, show_vertices=False, line_colors='gray', line_width=2, line_alpha=0.6, point_size=10)

        # # Plot points used to generate Voronoi diagram
        # plt.scatter(points[:, 0], points[:, 1], c='red', marker='o', label='Centroids')

        # # Highlight positive centroid
        # plt.scatter(self.positive[0], self.positive[1], c='blue', marker='*', s=200, label='Positive Centroid')

        # plt.title('Voronoi Diagram')
        # plt.xlabel('X-axis')
        # plt.ylabel('Y-axis')
        # plt.legend()
        # plt.show()





        # self.plot_voronoi_volume_2d(voronoi_volume)
        # plt.close('all')


        # return voronoi_volume

        
    @staticmethod
    def intersection_plane_line(hyperplane, point0, point1):
        # Convertir los puntos a coordenadas 2D
        p0 = point0.get_double_point()[:2]
        p1 = point1.get_double_point()[:2]
        
        # Obtener los coeficientes del plano
        plane = hyperplane.getPlane()
        
        # Calcular el denominador
        denom = sum(plane[i] * (p1[i] - p0[i]) for i in range(len(p1)))
        
        # Verificar si la línea es paralela al plano
        if denom == 0:
            return None
        else:
            # Calcular el numerador
            num = -hyperplane.C
            for i in range(len(p1)):
                num -= plane[i] * p0[i]
            
            # Calcular el punto de intersección
            x = (num / denom) * (p1[0] - p0[0]) + p0[0]
            y = (num / denom) * (p1[1] - p0[1]) + p0[1]
            
            return [x, y]

    def plot_voronoi_planes(self, volume, points):
        fig, ax = plt.subplots()
        ax.set_xlim(-1, 3)
        ax.set_ylim(-1, 3)

        # Lista para almacenar los segmentos de los planos finitos
        finite_segments = []

        # Trazar los segmentos de los planos finitos
        for face in volume.getFaces():
            if face.bounded:
                x_values = [face.getVertex(0)[0], face.getVertex(1)[0]]
                y_values = [face.getVertex(0)[1], face.getVertex(1)[1]]
                finite_segments.append((x_values, y_values))
                ax.plot(x_values, y_values, color='blue')

        # Trazar los segmentos de los planos infinitos
        for face in volume.getFaces():
            if not face.bounded:
                A, B, C = face.p.getPlane()
                
                # Manejar caso de pendiente infinita (plano vertical)
                if B == 0:
                    x_intersect = -C / A
                    y_min, y_max = ax.get_ylim()
                    ax.plot([x_intersect, x_intersect], [y_min, y_max], color='blue')
                else:
                    x_values = [-1, 3]
                    y_values = [(-C - A * x) / B for x in x_values]

                    # Verificar si el segmento del plano infinito se superpone con algún segmento finito
                    intersect = False
                    for seg_x, seg_y in finite_segments:
                        for i in range(len(seg_x) - 1):
                            if min(seg_x[i], seg_x[i + 1]) <= min(x_values) <= max(seg_x[i], seg_x[i + 1]) or \
                            min(seg_x[i], seg_x[i + 1]) <= max(x_values) <= max(seg_x[i], seg_x[i + 1]):
                                intersect = True
                                break
                        if intersect:
                            break

                    # Si no se superpone, trazar el segmento del plano infinito
                    if not intersect:
                        ax.plot(x_values, y_values, color='blue')

        plt.plot(points[:, 0], points[:, 1], 'ro')  # Puntos en rojo

        # Configurar límites y relación de aspecto
        ax.set_aspect('equal', adjustable='box')

        plt.show()






















        # center = voronoi.points.mean(axis=0)
        # ptp_bound = np.ptp(voronoi.points, axis=0)

        # finite_segments = []
        # infinite_segments = []
        # for pointidx, simplex in zip(voronoi.ridge_points, voronoi.ridge_vertices):
        #     simplex = np.asarray(simplex)
        #     if np.all(simplex >= 0):
        #         finite_segments.append(voronoi.vertices[simplex])
        #     else:
        #         i = simplex[simplex >= 0][0]  # finite end Voronoi vertex

        #         t = voronoi.points[pointidx[1]] - voronoi.points[pointidx[0]]  # tangent
        #         t /= np.linalg.norm(t)
        #         n = np.array([-t[1], t[0]])  # normal

        #         midpoint = voronoi.points[pointidx].mean(axis=0)
        #         direction = np.sign(np.dot(midpoint - center, n)) * n
        #         if (voronoi.furthest_site):
        #             direction = -direction
        #         aspect_factor = abs(ptp_bound.max() / ptp_bound.min())
        #         far_point = voronoi.vertices[i] + direction * ptp_bound.max() * aspect_factor

        #         infinite_segments.append([voronoi.vertices[i], far_point])

        # # Almacenar información de las celdas Voronoi en volumes
        # for i, region_indices in enumerate(voronoi.regions):
        #     if -1 not in region_indices and len(region_indices) > 0:
        #         vertices = [voronoi.vertices[idx] for idx in region_indices]
        #         volume_obj = Volume(representative=Point(*voronoi.points[i]))
        #         volume_obj.addFace(Face(Plane(A=0, B=0, C=0, D=0), vertex=vertices, bounded=True))
        #         volumes.append(volume_obj)

        # # Plotear las celdas finitas usando PolyCollection
        # polys = [volume.getFace(0).getArrayVertex() for volume in volumes]
        # poly_collection = PolyCollection(polys, edgecolors='black', facecolors='none')
        # plt.gca().add_collection(poly_collection)

        # # Plotear los segmentos infinitos
        # for segment in infinite_segments:
        #     plt.plot([segment[0][0], segment[1][0]], [segment[0][1], segment[1][1]], 'k--')

        # # Plotear los puntos
        # plt.plot(points[:, 0], points[:, 1], 'ko')  # Puntos negros

        # plt.xlim(points[:, 0].min() - 1, points[:, 0].max() + 1)
        # plt.ylim(points[:, 1].min() - 1, points[:, 1].max() + 1)
        # plt.gca().set_aspect('equal', adjustable='box')
        # plt.show()





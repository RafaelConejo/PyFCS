from scipy.spatial import Voronoi, voronoi_plot_2d
from scipy.spatial import ConvexHull
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from typing import List

### my libraries ###
from PyFCS.geometry.Plane import Plane
from PyFCS.geometry.Point import Point
from PyFCS.geometry.GeometryTools import GeometryTools
from PyFCS.geometry.Face import Face
from PyFCS.geometry.Volume import Volume
from PyFCS.geometry.Vector import Vector

from matplotlib.collections import LineCollection
from matplotlib.collections import PolyCollection



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
        points = np.array([[0, 0], [0, 1], [0, 2], [1, 0], [1, 1], [1, 2], [2, 0], [2, 1], [2, 2]])
        voronoi = Voronoi(points, qhull_options='Fi Fo p Fv')

        volumes = []

        # Calcular el centro y la distancia máxima de los puntos
        center = voronoi.points.mean(axis=0)
        ptp_bound = np.ptp(voronoi.points, axis=0)

        finite_segments = []
        infinite_planes = []

        for pointidx, simplex in zip(voronoi.ridge_points, voronoi.ridge_vertices):
            simplex = np.asarray(simplex)
            if np.any(simplex < 0):
                i = simplex[simplex >= 0][0]  # finite end Voronoi vertex

                t = voronoi.points[pointidx[1]] - voronoi.points[pointidx[0]]  # tangent
                t /= np.linalg.norm(t)
                n = np.array([-t[1], t[0]])  # normal

                midpoint = voronoi.points[pointidx].mean(axis=0)
                direction = np.sign(np.dot(midpoint - center, n)) * n
                if (voronoi.furthest_site):
                    direction = -direction
                aspect_factor = abs(ptp_bound.max() / ptp_bound.min())
                far_point = voronoi.vertices[i] + direction * ptp_bound.max() * aspect_factor

                # Crear el plano que representa el segmento infinito y añadirlo a la lista de planos
                infinite_planes.append([voronoi.vertices[i], far_point])

        # Almacenar información de las celdas Voronoi en volumes
        for i, region_indices in enumerate(voronoi.regions):
            if -1 not in region_indices and len(region_indices) > 0:
                vertices = [voronoi.vertices[idx] for idx in region_indices]
                volume_obj = Volume(representative=Point(*voronoi.points[i]))

                # Agregar la cara finita
                volume_obj.addFace(Face(Plane(A=0, B=0, C=0, D=0), vertex=vertices, bounded=True))

                # Agregar las caras infinitas (si las hay)
                for plane in infinite_planes:
                    volume_obj.addFace(Face(Plane(A=plane[0][0], B=plane[0][1], C=plane[1][0], D=plane[1][1]), vertex=vertices, bounded=False))

                volumes.append(volume_obj)

        # Plotear las celdas finitas usando PolyCollection
        polys = [volume.getFace(0).getArrayVertex() for volume in volumes]
        poly_collection = PolyCollection(polys, edgecolors='black', facecolors='none')
        plt.gca().add_collection(poly_collection)

        # Plotear los puntos
        plt.plot(points[:, 0], points[:, 1], 'ro')  # Puntos negros

        plt.xlim(points[:, 0].min() - 1, points[:, 0].max() + 1)
        plt.ylim(points[:, 1].min() - 1, points[:, 1].max() + 1)
        plt.gca().set_aspect('equal', adjustable='box')
        plt.show()








        





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

        



    # def plot_voronoi_volume_2d(self, voronoi_volume):
    #     fig, ax = plt.subplots()

    #     # Dibujar las regiones Voronoi
    #     for face in voronoi_volume.faces:
    #         vertices = np.array(face.vertex)
    #         ax.fill(vertices[:, 0], vertices[:, 1], edgecolor='b', alpha=0.5)

    #     # Dibujar el punto representativo
    #     representative = voronoi_volume.representative
    #     ax.plot(representative.x, representative.y, 'ro')

    #     ax.set_aspect('equal', 'box')
    #     plt.show()






















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





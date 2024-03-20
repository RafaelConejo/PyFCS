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
        points = np.array([[0, 0], [0, 1.5], [0, 2.4], [1, 0], [1, 1], [1, 2], [2.8, 0], [2, 1], [2, 2.7]])
        vor = Voronoi(points, qhull_options='Fi Fo p Fv')

        volumes = []

        # Calcular el centro y la distancia máxima de los puntos
        center = points.mean(axis=0)
        ptp_bound = np.ptp(points, axis=0)

        finite_planes = [[] for _ in range(len(points))]  # Almacenar planos finitos para cada punto
        infinite_planes = [[] for _ in range(len(points))]  # Almacenar planos infinitos para cada punto

        for pointidx, simplex in zip(vor.ridge_points, vor.ridge_vertices):
            simplex = np.asarray(simplex)
            if np.all(simplex >= 0):
                finite_planes[pointidx[0]].append(vor.vertices[simplex])
                finite_planes[pointidx[1]].append(vor.vertices[simplex])
            else:
                i = simplex[simplex >= 0][0]  # finite end Voronoi vertex

                t = points[pointidx[1]] - points[pointidx[0]]  # tangent
                t /= np.linalg.norm(t)
                n = np.array([-t[1], t[0]])  # normal

                midpoint = points[pointidx].mean(axis=0)
                direction = np.sign(np.dot(midpoint - center, n)) * n
                aspect_factor = abs(ptp_bound.max() / ptp_bound.min())
                far_point = vor.vertices[i] + direction * ptp_bound.max() * aspect_factor

                # Almacenar planos infinitos asociados a cada punto
                infinite_planes[pointidx[0]].append([vor.vertices[i], far_point])
                infinite_planes[pointidx[1]].append([vor.vertices[i], far_point])

        # Almacenar información de las celdas Voronoi en volumes
        for i, region_indices in enumerate(vor.regions):
            vertices = [vor.vertices[idx] for idx in region_indices if idx != -1]  # Eliminar el índice -1 (celdas sin región)
            volume_obj = Volume(representative=points[i])

            # Agregar los planos finitos al punto correspondiente
            for plane_points in finite_planes[i]:
                vertices = [point for point in plane_points]
                if len(plane_points) >= 2:  # Verifica que haya al menos dos puntos para definir un segmento de línea
                    # Calcula los coeficientes de la ecuación del plano Ax + By + C = 0
                    A = plane_points[1][1] - plane_points[0][1]
                    B = plane_points[0][0] - plane_points[1][0]
                    C = -(A * plane_points[0][0] + B * plane_points[0][1])
                    plane = Plane(A, B, C)
                    volume_obj.addFace(Face(p=plane, vertex=vertices, bounded=True))

            # Agregar los planos infinitos al punto correspondiente
            for line_points in infinite_planes[i]:
                # Creamos un plano a partir de los dos puntos que definen la línea
                A = line_points[1][1] - line_points[0][1]
                B = line_points[0][0] - line_points[1][0]
                C = -(A * line_points[0][0] + B * line_points[0][1])
                plane = Plane(A, B, C)
                
                # Creamos la cara con el plano asociado y los vértices
                vertices = [point for point in line_points]
                volume_obj.addFace(Face(p=plane, vertex=vertices, bounded=False))

            volumes.append(volume_obj)








        # self.plot_voronoi_planes(volumes, points)
            
        self.plot_all_volumes(volumes)









        





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

        


    def plot_voronoi_planes(self, volumes, points):
        fig, ax = plt.subplots()
        ax.set_xlim(-1, 3)
        ax.set_ylim(-1, 3)

        # Lista para almacenar los segmentos de los planos finitos
        finite_segments = []

        # Trazar los segmentos de los planos finitos
        for volume in volumes:
            for face in volume.getFaces():
                if face.bounded:
                    x_values = [face.getVertex(0)[0], face.getVertex(1)[0]]
                    y_values = [face.getVertex(0)[1], face.getVertex(1)[1]]
                    finite_segments.append((x_values, y_values))
                    ax.plot(x_values, y_values, color='blue')

        # Trazar los segmentos de los planos infinitos
        for volume in volumes:
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








    def plot_volumes(self,volumes):
        for volume in volumes:
            point = volume.representative
            finite_planes = []
            infinite_planes = []

            for face in volume.faces:
                if face.bounded:
                    finite_planes.append(face.vertex)
                else:
                    infinite_planes.append(face.vertex)

            plt.figure()

            # Plot finite planes
            for plane_points in finite_planes:
                if len(plane_points) >= 2:
                    plane_points = np.array(plane_points)
                    plt.plot(plane_points[:, 0], plane_points[:, 1], color='b')

            # Plot infinite planes
            for line_points in infinite_planes:
                line_points = np.array(line_points)
                plt.plot(line_points[:, 0], line_points[:, 1], color='r')

            # Plot the point of interest
            plt.scatter(point[0], point[1], color='g', marker='o', s=100)

            plt.xlabel('X')
            plt.ylabel('Y')
            plt.grid(True)
            plt.axis('equal')  # Ensure equal aspect ratio
            plt.title(f"Point: {point}")

        plt.show()



    def plot_all_volumes(self, volumes):
        plt.figure()

        for volume in volumes:
            point = volume.representative
            finite_planes = []
            infinite_planes = []

            for face in volume.faces:
                if face.bounded:
                    finite_planes.append(face.vertex)
                else:
                    infinite_planes.append(face.vertex)

            # Plot finite planes
            for plane_points in finite_planes:
                if len(plane_points) >= 2:
                    plane_points = np.array(plane_points)
                    plt.plot(plane_points[:, 0], plane_points[:, 1], color='b')

            # Plot infinite planes
            for line_points in infinite_planes:
                line_points = np.array(line_points)
                plt.plot(line_points[:, 0], line_points[:, 1], color='r')

            # Plot the point of interest
            plt.scatter(point[0], point[1], color='g', marker='o', s=100)

        plt.xlabel('X')
        plt.ylabel('Y')
        plt.grid(True)
        plt.axis('equal')  # Ensure equal aspect ratio
        plt.title("All Points and their Respective Planes")
        plt.show()







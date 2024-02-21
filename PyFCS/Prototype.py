from scipy.spatial import Voronoi, voronoi_plot_2d
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



    def is_clockwise(self,vertices):
        """Verifica si los vértices están en orden de las agujas del reloj."""
        area = 0
        for i in range(len(vertices)):
            x1, y1 = vertices[i][0], vertices[i][1]
            x2, y2 = vertices[(i + 1) % len(vertices)][0], vertices[(i + 1) % len(vertices)][1]
            area += (x2 - x1) * (y2 + y1)
        return area >= 0



    def create_voronoi_volume(self):
        points = np.vstack((self.positive, self.negatives))
        voronoi = Voronoi(points, qhull_options='Fi Fo p Fv')

        # Convertir los vértices de Voronoi a instancias de Face
        faces = []
        # Dentro del bucle para crear caras
        for indices in voronoi.regions:
            if not indices or -1 in indices:  # Ignorar regiones vacías o regiones externas
                continue
            vertices = [voronoi.vertices[i] for i in indices]
            
            # Verificar si los vértices están en orden de las agujas del reloj
            if not self.is_clockwise(vertices):
                # Si los vértices no están en orden de las agujas del reloj, invertir el orden
                vertices.reverse()
            
            # Calcular el plano que contiene la cara
            plane = self.calculate_plane(vertices)
            
            # Crear una instancia de Face con el plano y los vértices
            face = Face(plane, vertices, bounded=True)
            faces.append(face)


        # Inicializar tu objeto Volume con las instancias de Face
        representative = Point(*self.positive)
        voronoi_volume = Volume(representative)
        for face in faces:
            voronoi_volume.addFace(face)


        





        # voronoi_proj = Voronoi(points[:, :2], qhull_options='Fi Fo p Fv')

        # # Visualization code
        # plt.figure(figsize=(8, 8))

        # # Plot Voronoi diagram
        # voronoi_plot_2d(voronoi_proj, show_vertices=False, line_colors='gray', line_width=2, line_alpha=0.6, point_size=10)

        # # Plot points used to generate Voronoi diagram
        # plt.scatter(points[:, 0], points[:, 1], c='red', marker='o', label='Centroids')

        # # Highlight positive centroid
        # plt.scatter(positive_centroid[0], positive_centroid[1], c='blue', marker='*', s=200, label='Positive Centroid')

        # plt.title('Voronoi Diagram')
        # plt.xlabel('X-axis')
        # plt.ylabel('Y-axis')
        # plt.legend()
        # plt.show()





        self.visualize_voronoi_2d(voronoi_volume)
        plt.close('all')


        return voronoi_volume

        




    def visualize_volume(self, volume):
        fig = plt.figure(figsize=(10, 8))
        ax = fig.add_subplot(111, projection='3d')

        # Plot each face
        for face in volume.faces:
            vertices = face.vertex
            # Desempaqueta las coordenadas x, y, z de cada vértice
            x, y, z = zip(*vertices)
            # Completa el polígono cerrando la cara
            x = list(x) + [x[0]]
            y = list(y) + [y[0]]
            z = list(z) + [z[0]]
            ax.plot(x, y, z, 'gray')

        # Plot representative point
        representative = volume.representative
        ax.scatter(representative.x, representative.y, representative.z, c='blue', marker='*', s=200, label='Positive Centroid')

        ax.set_xlabel('X-axis')
        ax.set_ylabel('Y-axis')
        ax.set_zlabel('Z-axis')
        ax.set_title('3D Volume Visualization')
        ax.legend()
        
        plt.show()




    def visualize_voronoi_2d(self, volume):
        if volume is not None:
            # Extract information from the Volume object
            faces = volume.faces
            representative = volume.representative

            # Visualization code
            fig, ax = plt.subplots(figsize=(8, 8))

            # Plot Voronoi diagram
            for face in faces:
                vertices = face.vertex
                if vertices is not None and len(vertices) >= 3:
                    polygon = vertices
                    ax.plot([point[0] for point in polygon], [point[1] for point in polygon], 'gray', linewidth=2, alpha=0.6)

            # Plot positive centroid
            ax.scatter(representative.x, representative.y, c='blue', marker='*', s=200, label='Positive Centroid')

            # Plot vertices used to generate the Voronoi diagram
            points = [(point[0], point[1]) for face in faces for point in face.vertex if point is not None]
            if points:
                points = np.array(points)
                ax.scatter(points[:, 0], points[:, 1], c='red', marker='o', label='Centroids')

            ax.set_title('Voronoi Diagram')
            ax.set_xlabel('X-axis')
            ax.set_ylabel('Y-axis')
            ax.legend()
            plt.show()
        else:
            print("No valid Voronoi regions found.")


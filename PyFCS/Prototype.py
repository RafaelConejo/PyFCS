from scipy.spatial import Voronoi, voronoi_plot_2d
from scipy.spatial import ConvexHull
import numpy as np
import os
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
from matplotlib.patches import Polygon
from scipy.interpolate import interp1d
import subprocess


class Prototype:
    def __init__(self, label, positive, negatives):
        self.label = label
        self.positive = positive
        self.negatives = negatives

        # Create Voronoi volume
        vor = self.run_qvoronoi()
        self.voronoi_volume = self.read_from_voronoi_file()


    def run_qvoronoi(self):
        try:
            # Obtén los puntos concatenados
            points = np.vstack((self.positive, self.negatives))

            # Obtén la dimensión y el número de puntos
            dimension = points.shape[1]  # Dimensiones de los puntos
            num_points = points.shape[0]  # Número de puntos

            # Formatea los datos de entrada
            input_data = f"{dimension}\n{num_points}\n"  # Agrega dimensión y número de puntos
            input_data += "\n".join(" ".join(map(str, point)) for point in points)  # Agrega las coordenadas de los puntos

            # Ejecuta qvoronoi.exe con los datos de entrada formateados
            command = f"qvoronoi.exe Fi Fo p Fv"
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            output, error = process.communicate(input=input_data)

            if process.returncode != 0:
                print(f"Error al ejecutar qvoronoi.exe: {error}")
                return None

            # Guarda la salida en un archivo temporal
            temp_output_file = "temp_voronoi_output.txt"
            with open(temp_output_file, 'w') as f:
                f.write(output)

            # Lee el resultado desde el archivo temporal y lo devuelve como un array de numpy
            with open(temp_output_file, 'r') as f:
                voronoi_result = f.read()

            return voronoi_result

        except Exception as e:
            print(f"Error en la ejecución: {e}")
            return None
        



    def read_from_voronoi_file(self):
        volumes = []
        file_path = "temp_voronoi_output.txt"
        points = np.vstack((self.positive, self.negatives))

        with open(file_path, 'r') as file:
            lines = file.readlines()

            num_colors = len(points)
            faces = [[None] * num_colors for _ in range(num_colors)]

            # Lee las regiones de Voronoi acotadas
            num_planes = int(lines[0])
            for i in range(1, num_planes + 1):
                line = lines[i]
                parts = line.split()
                index1 = int(parts[1])
                index2 = int(parts[2])
                plane_params = [float(part) for part in parts[3:]]
                plane = Plane(*plane_params)
                faces[index1][index2] = Face(plane)

            # Lee las regiones de Voronoi no acotadas
            num_unbounded_planes = int(lines[num_planes + 1])
            for i in range(num_planes + 2, num_planes + num_unbounded_planes + 2):
                line = lines[i]
                parts = line.split()
                index1 = int(parts[1])
                index2 = int(parts[2])
                plane_params = [float(part) for part in parts[3:]]
                plane = Plane(*plane_params)
                faces[index1][index2] = Face(plane, infinity=True)

            # Lee las coordenadas de los vértices
            num_dimensions = int(lines[num_planes + num_unbounded_planes + 2])
            num_vertices = int(lines[num_planes + num_unbounded_planes + 3])
            vertices = []
            for i in range(num_planes + num_unbounded_planes + 4, num_planes + num_unbounded_planes + num_vertices + 4):
                line = lines[i]
                parts = line.split()
                coords = [float(part) for part in parts]
                vertex = coords
                vertices.append(vertex)

            # Lee los vértices para cada cara
            num_faces = int(lines[num_planes + num_unbounded_planes + num_vertices + 4])
            for i in range(num_planes + num_unbounded_planes + num_vertices + 5,
                        num_planes + num_unbounded_planes + num_vertices + num_faces + 5):
                line = lines[i]
                parts = line.split()
                index1 = int(parts[1])
                index2 = int(parts[2])
                face = faces[index1][index2]
                for part in parts[3:]:
                    vertex_index = int(part)
                    if vertex_index == 0:
                        face.setInfinity()
                    else:
                        face.addVertex(vertices[vertex_index - 1])


            volumes = []
            for point in points:
                volume = Volume(Point(*point))
                volumes.append(volume)
            # Agregar caras a cada color difuso
            for i in range(num_colors):
                for j in range(num_colors):
                    if faces[i][j] is not None:
                        volumes[i].addFace(faces[i][j])
                        volumes[j].addFace(faces[i][j])

        # self.plot_3d(volumes[0])
        return volumes[0]



    def plot_2d(self, volume):
        # Creamos una figura
        fig, ax = plt.subplots()

        # Dibujamos solo los bordes de las caras del volumen
        for face in volume.getFaces():
            # Obtenemos el plano de separación de la cara
            plane = face.getPlane()
            # Obtenemos las coordenadas x, y de los puntos que forman el borde de la cara
            x_values = []
            y_values = []
            for i in np.linspace(-10, 10, 100):  # Ajusta el rango según tus necesidades
                if plane.getC() != 0:
                    x = i
                    y = (-plane.getA() * x - plane.getD()) / plane.getC()
                else:
                    y = i
                    x = (-plane.getC() * y - plane.getD()) / plane.getA()
                x_values.append(x)
                y_values.append(y)
            # Dibujamos el borde de la cara
            ax.plot(x_values, y_values, color='black', linewidth=1)

        # Obtenemos las coordenadas del representante del volumen y lo marcamos en el gráfico
        representative = volume.getRepresentative()
        rep_x, rep_y = representative.get_x(), representative.get_y()
        ax.scatter(rep_x, rep_y, color='red', marker='o')

        # Configuramos etiquetas de ejes
        ax.set_xlabel('X')
        ax.set_ylabel('Y')

        # Mostramos el gráfico
        plt.show()




    def plot_3d_all(self, volumes):
        # Crear una figura 3D
        fig = plt.figure()
        ax = fig.add_subplot(111, projection='3d')

        # Definir una paleta de colores
        colors = plt.cm.viridis(np.linspace(0, 1, len(volumes)))

        # Iterar sobre cada volumen y dibujar sus caras con un color diferente
        for volume, color in zip(volumes, colors):
            for face in volume.getFaces():
                # Obtener los vértices de la cara
                vertices = [vertex for vertex in face.getArrayVertex()]
                # Agregar el primer vértice al final para cerrar la cara
                vertices.append(vertices[0])
                # Convertir la lista de vértices en un array de NumPy para trazar
                vertices = np.array(vertices)
                # Extraer las coordenadas x, y, z de los vértices
                x = vertices[:, 0]
                y = vertices[:, 1]
                z = vertices[:, 2]
                # Tracer la cara con el color correspondiente
                ax.plot(x, y, z, color=color)

            # Obtener las coordenadas del representante del volumen
            representative = volume.getRepresentative()
            rep_x, rep_y, rep_z = representative.get_x(), representative.get_y(), representative.get_z()
            # Tracer el representante como un marcador con el color correspondiente al volumen
            ax.scatter(rep_x, rep_y, rep_z, color=color, marker='o')

        # Configurar etiquetas de ejes
        ax.set_xlabel('X')
        ax.set_ylabel('Y')
        ax.set_zlabel('Z')

        # Mostrar el gráfico
        plt.show()


    def plot_3d(self, volume):
        # Crear una figura 3D
        fig = plt.figure()
        ax = fig.add_subplot(111, projection='3d')


        # Iterar sobre las caras del volumen y dibujarlas con un color específico
        for face in volume.getFaces():
            # Obtener los vértices de la cara
            vertices = [vertex for vertex in face.getArrayVertex()]
            # Agregar el primer vértice al final para cerrar la cara
            vertices.append(vertices[0])
            # Convertir la lista de vértices en un array de NumPy para trazar
            vertices = np.array(vertices)
            # Extraer las coordenadas x, y, z de los vértices
            x = vertices[:, 0]
            y = vertices[:, 1]
            z = vertices[:, 2]
            # Tracer la cara con el color correspondiente
            ax.plot(x, y, z)

        # Obtener las coordenadas del representante del volumen
        representative = volume.getRepresentative()
        rep_x, rep_y, rep_z = representative.get_x(), representative.get_y(), representative.get_z()
        # Tracer el representante como un marcador con el mismo color del volumen
        ax.scatter(rep_x, rep_y, rep_z, marker='o')

        # Configurar etiquetas de ejes
        ax.set_xlabel('X')
        ax.set_ylabel('Y')
        ax.set_zlabel('Z')

        # Mostrar el gráfico
        plt.show()



        



















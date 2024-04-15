import numpy as np
import matplotlib.pyplot as plt

class Visual_tools:
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


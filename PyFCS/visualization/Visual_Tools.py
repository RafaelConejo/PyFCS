import numpy as np
import matplotlib.pyplot as plt

class Visual_tools:



    @staticmethod
    def plot_3d_all(volumes):
        fig = plt.figure()
        ax = fig.add_subplot(111, projection='3d')

        cmap = plt.get_cmap('viridis')
        colors = [cmap(i) for i in np.linspace(0, 1, len(volumes))]

        # Ajusta los límites del gráfico
        ax.set_xlim([0, 100])
        ax.set_ylim([-180, 180])
        ax.set_zlim([-180, 180])

        for i, volume in enumerate(volumes):
            # Iteramos sobre las caras del volumen actual
            for face in volume.voronoi_volume.faces:
                # Extraemos los puntos de la cara y los convertimos en un arreglo numpy
                puntos = np.array([point for point in face.getArrayVertex()])
                # Cerramos el ciclo de la cara
                puntos = np.append(puntos, [puntos[0]], axis=0)

                # Extraemos las coordenadas x, y, z de los puntos
                x = puntos[:, 0]
                y = puntos[:, 1]
                z = puntos[:, 2]


                # Filtra los puntos para que estén dentro de los límites del gráfico
                mask = (x >= ax.get_xlim()[0]) & (x <= ax.get_xlim()[1]) & \
                    (y >= ax.get_ylim()[0]) & (y <= ax.get_ylim()[1]) & \
                    (z >= ax.get_zlim()[0]) & (z <= ax.get_zlim()[1])

                x_filtered = x[mask]
                y_filtered = y[mask]
                z_filtered = z[mask]

                # Verifica que haya al menos dos puntos después del filtrado
                if len(x_filtered) > 1 and len(y_filtered) > 1 and len(z_filtered) > 1:
                    ax.plot(x_filtered, y_filtered, z_filtered, color=colors[i])


        # Etiqueta de los ejes
        ax.set_xlabel('L*')
        ax.set_ylabel('a*')
        ax.set_zlabel('b*')

        plt.show()


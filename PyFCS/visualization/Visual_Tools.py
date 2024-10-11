import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

class Visual_tools:



    @staticmethod
    def plot_3d_all(volumes):
        fig = plt.figure()
        ax = fig.add_subplot(111, projection='3d')

        cmap = plt.get_cmap('tab20')
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




    @staticmethod
    def plot_prototype(prototype):
            fig = plt.figure()
            ax = fig.add_subplot(111, projection='3d')

            # 1. Puntos negativos
            negatives = np.array(prototype.negatives)
            ax.scatter(negatives[:, 0], negatives[:, 1], negatives[:, 2], color='red', marker='o', label='Negatives')

            # 2. Punto positivo (representante)
            positive = np.array(prototype.positive)
            ax.scatter(positive[0], positive[1], positive[2], color='green', marker='^', s=100, label='Positive')

            # 3. Volumen de Voronoi (Caras)
            faces = prototype.voronoi_volume.faces  # Cada cara contiene sus vértices
            for face in faces:
                vertices = np.array(face.vertex)

                if face.infinity:  # Si la cara es infinita
                    # Representación de caras infinitas (e.g., líneas discontinuas, semitransparentes)
                    if len(vertices) >= 3:
                        # Si hay al menos 3 vértices, trazamos la cara como superficie
                        ax.plot_trisurf(vertices[:, 0], vertices[:, 1], vertices[:, 2], color='orange', alpha=0.1, linewidth=0.5, edgecolor='r', linestyle='--', label="Infinite Face")
                    elif len(vertices) == 2:
                        # Si solo hay 2 vértices, trazamos una línea
                        ax.plot([vertices[0, 0], vertices[1, 0]],
                                [vertices[0, 1], vertices[1, 1]],
                                [vertices[0, 2], vertices[1, 2]],
                                color='orange', alpha=0.5, linestyle='--')
                    else:
                        print("Warning: Cara infinita sin vértices visibles.")
                else:
                    # Caras finitas normales
                    poly3d = Poly3DCollection([vertices], facecolors='cyan', edgecolors='blue', linewidths=1, alpha=0.5)
                    ax.add_collection3d(poly3d)

            # Etiquetas de los ejes
            ax.set_xlabel('X')
            ax.set_ylabel('Y')
            ax.set_zlabel('Z')

            # Ajustar límites de los ejes para visualizar mejor la extensión de las caras infinitas
            ax.set_xlim(min(positive[0], np.min(negatives[:, 0])),
                        max(positive[0], np.max(negatives[:, 0])))
            ax.set_ylim(min(positive[1], np.min(negatives[:, 1])),
                        max(positive[1], np.max(negatives[:, 1])))
            ax.set_zlim(min(positive[2], np.min(negatives[:, 2])),
                        max(positive[2], np.max(negatives[:, 2])))


            # Mostrar la leyenda
            ax.legend()

            # Mostrar el gráfico
            plt.show()


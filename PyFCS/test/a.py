import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

def parse_voronoi_output(voronoi_data):
    lines = voronoi_data.strip().split('\n')
    index = 0

    # Número de planos
    num_planes = int(lines[index])
    index += 1
    
    planes = []
    
    # Datos de los planos acotados
    for _ in range(num_planes):
        data = list(map(float, lines[index].split()))
        planes.append((int(data[0]), int(data[1]), int(data[2]), data[3:]))
        index += 1
    
    # Número de planos no acotados
    num_unbounded_planes = int(lines[index])
    index += 1
    
    unbounded_planes = []
    
    # Datos de los planos no acotados
    for _ in range(num_unbounded_planes):
        data = list(map(float, lines[index].split()))
        unbounded_planes.append((int(data[0]), int(data[1]), int(data[2]), data[3:]))
        index += 1

    # Número de vértices
    index += 1
    num_vertices = int(lines[index])
    index += 1
    
    vertices = []
    
    # Coordenadas de los vértices
    for _ in range(num_vertices):
        vertex = list(map(float, lines[index].split()))
        vertices.append(vertex)
        index += 1

    # Número de caras
    num_faces = int(lines[index])
    index += 1
    
    faces = []
    
    # Datos de las caras
    for _ in range(num_faces):
        data = list(map(int, lines[index].split()))
        faces.append(data[1:])  # Solo guardamos los índices
        index += 1
    
    return planes, unbounded_planes, np.array(vertices), faces

def plot_voronoi(planes, unbounded_planes, vertices, faces):
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')

    # Plotear los planos acotados
    for face in faces:
        poly_vertices = np.array([vertices[i] for i in face])
        if len(poly_vertices) >= 3:
            poly = Poly3DCollection([poly_vertices], facecolors='cyan', edgecolors='blue', alpha=0.3)
            ax.add_collection3d(poly)

    # Ajustar límites del gráfico
    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_zlabel('Z')

    ax.set_xlim([np.min(vertices[:, 0]), np.max(vertices[:, 0])])
    ax.set_ylim([np.min(vertices[:, 1]), np.max(vertices[:, 1])])
    ax.set_zlim([np.min(vertices[:, 2]), np.max(vertices[:, 2])])

    plt.show()

# Ejemplo de uso
voronoi_data = """2
6 0 5 0.9998755631771802 -0.005417370717690073 0.01481587849653435 -50.41024814040305 
6 1 3 -0.0553408367348301 -0.9746691826056278 -0.2166965072823419 23.78785272516235 
8
6 0 4 0.6017936511122267 0.15323117505442 -0.7838141415364087 -35.8296084846947 
6 0 1 0.4396730452411237 0.7374511038628788 0.5126923860365185 -46.20405061583637 
6 0 3 0.6062289530399001 -0.6788407889665393 0.4143206967210699 -29.14923807848237 
6 1 5 0.5755516099894611 -0.6798477704446589 -0.4544748103690299 -7.030296959878661 
6 1 2 0.4709014703234406 -0.769732634883044 0.4310028724303679 -29.62893294932423 
6 2 3 -0.5297515870689304 -0.4853929949375478 -0.6955263449097431 59.09362228931 
6 3 5 0.8241191252714686 0.4898518186425709 -0.284381544996076 -42.5843944739126 
6 4 5 0.6965533763923798 -0.1406305769613724 0.7035882564823599 -30.31727388431419 
3
5
50.60088918196007 32.79793189739947 -0.4499140442569214 
50.15408639479594 16.29598063891459 23.66947928068118 
1.65839157054036 6.750601543052333 78.98822585843465 
54.9720444727208 13.85359255349999 33.42455375761684 
50.51330004595159 -2.337449724342349 -7.385928731596866 
10
5 0 4 1 5 0
6 0 1 1 2 3 0
5 0 5 1 2 5
6 0 3 2 5 0 3
6 1 5 1 2 4 0
5 1 2 0 3 4
5 1 3 2 3 4
5 2 3 3 0 4
6 3 5 2 5 0 4
5 4 5 1 5 0"""

planes, unbounded_planes, vertices, faces = parse_voronoi_output(voronoi_data)
plot_voronoi(planes, unbounded_planes, vertices, faces)

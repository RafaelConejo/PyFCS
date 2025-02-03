from PyFCS.input_output.Input import Input
from PyFCS.geometry.Face import Face
from PyFCS.geometry.Plane import Plane
from PyFCS.geometry.Vector import Vector
from PyFCS.geometry.Volume import Volume

from PyFCS import Prototype, FuzzyColorSpace

from skimage import color
import numpy as np

class InputFCS(Input):

    def write_file(self, file_path):
        pass

    
    def read_file(self, file_path):
        try:
            with open(file_path, 'r') as file:
                lines = iter(file.readlines())

                fcs_name = next(lines).strip().split(" ", 1)[1]  # @name
                cs = next(lines).strip().split(" ", 1)[1]  # @colorSpace
                num_colors = int(next(lines).strip().split(" ", 1)[1])  # @numberOfColors

                # Read Colors and values
                colors = []
                for _ in range(num_colors):
                    parts = next(lines).strip().split()
                    color_name, L, A, B = parts[0], float(parts[1]), float(parts[2]), float(parts[3])
                    colors.append((color_name, L, A, B))

                # Create color_data struct
                color_data = {}
                for i in range(num_colors):
                    color_name, L, A, B = colors[i]
                    
                    positive_prototype = np.array([L, A, B])

                    negative_prototypes = []
                    for j in range(num_colors):
                        if i != j:  
                            _, L_neg, A_neg, B_neg = colors[j]
                            negative_prototypes.append([L_neg, A_neg, B_neg])
                    negative_prototypes = np.array(negative_prototypes)

                    color_data[color_name] = {
                        'Color': [L, A, B],
                        'positive_prototype': positive_prototype,
                        'negative_prototypes': negative_prototypes
                    }

                # Read Core, alpha-cut and support
                faces = []
                for line in lines:
                    line = line.strip()

                    if line == "@core":
                        i = 0
                        next(lines)
                        cores = []
                        while True:
                            line = next(lines).strip()

                            if line.startswith("@volume"):
                                negatives = [color[1:] for idx, color in enumerate(colors) if idx != i]
                                voronoi_volume = Volume(colors[i][0], faces)

                                cores.append(Prototype(colors[i][0], colors[i][1:], negatives, voronoi_volume, True))
                                
                                faces = []
                                i += 1

                            elif line.startswith("@voronoi"):
                                break

                            else:
                                plane_data = line.split()
                                if not plane_data: break

                                # Create Plane
                                plane_values = list(map(float, plane_data[:4]))
                                plane = Plane(*plane_values)
                                infinity = plane_data[4].lower()

                                # Get Vertex
                                num_vertex = int(next(lines).strip())
                                vertex = [Vector.from_array(list(map(float, next(lines).strip().split()))) 
                                            for _ in range(num_vertex)]
                                
                                # Create Face
                                faces.append(Face(plane, vertex, infinity))

                        
                        i = 0
                        next(lines)
                        prototypes = []
                        while True:
                            line = next(lines).strip()

                            if line.startswith("@volume"):
                                negatives = [color[1:] for idx, color in enumerate(colors) if idx != i]
                                voronoi_volume = Volume(colors[i][0], faces)

                                prototypes.append(Prototype(colors[i][0], colors[i][1:], negatives, voronoi_volume, True))
                                
                                faces = []
                                i += 1
                            
                            elif line.startswith("@support"):
                                break

                            else:
                                plane_data = line.split()
                                if not plane_data: break

                                # Create Plane
                                plane_values = list(map(float, plane_data[:4]))
                                plane = Plane(*plane_values)
                                infinity = plane_data[4].lower()

                                # Get Vertex
                                num_vertex = int(next(lines).strip())
                                vertex = [Vector.from_array(list(map(float, next(lines).strip().split()))) 
                                            for _ in range(num_vertex)]
                                
                                # Create Face
                                faces.append(Face(plane, vertex, infinity))


                        i = 0
                        next(lines)
                        supports = []
                        while True:
                            try:
                                line = next(lines).strip()
                            except StopIteration:
                                break 

                            if line.startswith("@volume"):
                                negatives = [color[1:] for idx, color in enumerate(colors) if idx != i]
                                voronoi_volume = Volume(colors[i][0], faces)

                                supports.append(Prototype(colors[i][0], colors[i][1:], negatives, voronoi_volume, True))
                                
                                faces = []
                                i += 1

                            else:
                                plane_data = line.split()
                                if not plane_data: break

                                # Create Plane
                                plane_values = list(map(float, plane_data[:4]))
                                plane = Plane(*plane_values)
                                infinity = plane_data[4].lower()

                                # Get Vertex
                                num_vertex = int(next(lines).strip())
                                vertex = [Vector.from_array(list(map(float, next(lines).strip().split()))) 
                                            for _ in range(num_vertex)]
                                
                                # Create Face
                                faces.append(Face(plane, vertex, infinity))

                return color_data, FuzzyColorSpace(fcs_name, prototypes, cores, supports)            
                                

        except (ValueError, IndexError, KeyError) as e:
            raise ValueError(f"Error reading .fcs file: {str(e)}")
        



    
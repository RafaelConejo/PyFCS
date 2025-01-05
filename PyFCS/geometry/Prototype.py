import numpy as np
from typing import List
import subprocess

### my libraries ###
from PyFCS.geometry.Plane import Plane
from PyFCS.geometry.Point import Point
from PyFCS.geometry.Face import Face
from PyFCS.geometry.Volume import Volume
from PyFCS.colorspace.ReferenceDomain import ReferenceDomain


class Prototype:
    false_negatives = [
            (0, -128, -128), (0, -128, 127), (0, 127, -128), (0, 127, 127), 
            (100, -128, -128), (100, -128, 127), (100, 127, -128), (100, 127, 127),
            (0, -128, -0.5), (0, 127, -0.5), (100, -128, -0.5), (100, 127, -0.5),
            (0, -0.5, -128), (0, -0.5, 127), (100, -0.5, -128), (100, -0.5, 127),
            (50, -128, -128), (50, -128, 127), (50, 127, -128), (50, 127, 127),
            (50, -128, -0.5), (50, 127, -0.5), (50, -0.5, -128), (50, -0.5, 127),
            (0, -0.5, -0.5), (100, -0.5, -0.5)
        ]
    

    def __init__(self, label, positive, negatives, voronoi_volume=None, add_false=False):
        self.label = label
        self.positive = positive
        self.negatives = negatives
        self.add_false = add_false
        
        if add_false:
            self.negatives = np.vstack((self.negatives, Prototype.false_negatives))

        if voronoi_volume is not None:
            self.voronoi_volume = voronoi_volume
        else:
            # Create Voronoi volume
            self.run_qvoronoi()
            self.voronoi_volume = self.read_from_voronoi_file()


    @staticmethod
    def get_falseNegatives():
        return Prototype.false_negatives


    def run_qvoronoi(self):
        """
        Run qvoronoi.exe to calculate Voronoi volumes for positive and negative points.

        Returns:
            str: File path of the temporary Voronoi output file.
        """
        try:
            # Get concatenated points
            points = np.vstack((self.positive, self.negatives))

            # Get dimension and number of points
            dimension = points.shape[1]  # Dimensions of points
            num_points = points.shape[0]  # Number of points

            # Format input data
            input_data = f"{dimension}\n{num_points}\n"  # Add dimension and number of points
            input_data += "\n".join(" ".join(map(str, point)) for point in points)  # Add coordinates of points

            # Run qvoronoi.exe with formatted input data
            command = f"PyFCS\\external\\qvoronoi.exe Fi Fo p Fv"
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            output, error = process.communicate(input=input_data)

            if process.returncode != 0:
                print(f"Error running qvoronoi.exe: {error}")
                return None

            # Save output to a temporary file
            temp_output_file = "PyFCS\\external\\temp\\temp_voronoi_output.txt"
            with open(temp_output_file, 'w') as f:
                f.write(output)


        except Exception as e:
            print(f"Error in execution: {e}")
        



    def read_from_voronoi_file(self):
        """
        Read Voronoi volumes from a file.

        Returns:
            list: List of Voronoi volumes.
        """
        volumes = []
        file_path = "PyFCS\\external\\temp\\temp_voronoi_output.txt"
        points = np.vstack((self.positive, self.negatives))

        with open(file_path, 'r') as file:
            lines = file.readlines()

            num_colors = len(points)
            faces = [[None] * num_colors for _ in range(num_colors)]

            cont = 0

            # Read bounded Voronoi regions
            num_planes = int(lines[0])
            cont += 1
            for i in range(1, num_planes + cont):
                line = lines[i]
                parts = line.split()
                index1 = int(parts[1])
                index2 = int(parts[2])
                plane_params = [float(part) for part in parts[3:]]
                plane = Plane(*plane_params)
                faces[index1][index2] = Face(plane, infinity=False)  # Bounded faces

            # Read unbounded Voronoi regions
            num_unbounded_planes = int(lines[num_planes + cont])
            cont += 1
            for i in range(num_planes + cont, num_planes + num_unbounded_planes + cont):
                line = lines[i]
                parts = line.split()
                index1 = int(parts[1])
                index2 = int(parts[2])
                plane_params = [float(part) for part in parts[3:]]
                plane = Plane(*plane_params)
                faces[index1][index2] = Face(plane, infinity=True)   # Unbounded faces (go to infinity)

            # Read vertex coordinates
            num_dimensions = int(lines[num_planes + num_unbounded_planes + cont])
            cont += 1
            num_vertices = int(lines[num_planes + num_unbounded_planes + cont])
            cont += 1
            vertices = []
            for i in range(num_planes + num_unbounded_planes + cont, num_planes + num_unbounded_planes + num_vertices + cont):
                line = lines[i]
                parts = line.split()
                coords = [float(part) for part in parts]
                vertex = coords
                vertices.append(vertex)

            # Read vertices for each face
            num_faces = int(lines[num_planes + num_unbounded_planes + num_vertices + cont])
            cont += 1
            for i in range(num_planes + num_unbounded_planes + num_vertices + cont,
                            num_planes + num_unbounded_planes + num_vertices + num_faces + cont):
                line = lines[i]
                parts = line.split()
                index1 = int(parts[1])
                index2 = int(parts[2])
                face = faces[index1][index2]

                # Assign vertices or infinity for each face
                for j in range(3, int(parts[0]) + 1):
                    vertex_index = int(parts[j])
                    if vertex_index == 0:
                        face.setInfinity()  # Mark as infinite if vertex_index is 0
                    else:
                        face.addVertex(vertices[vertex_index - 1])  # Add vertex to the face


            volumes = []
            for point in points:
                volume = Volume(Point(*point))
                volumes.append(volume)
                
            # Add faces to each fuzzy color
            for i in range(num_colors):
                for j in range(num_colors):
                    if faces[i][j] is not None:
                        volumes[i].addFace(faces[i][j])
                        volumes[j].addFace(faces[i][j])

        return volumes[0]

        



















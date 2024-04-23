import numpy as np
from typing import List
import subprocess

### my libraries ###
from PyFCS.geometry.Plane import Plane
from PyFCS.geometry.Point import Point
from PyFCS.geometry.Face import Face
from PyFCS.geometry.Volume import Volume


class Prototype:
    def __init__(self, label, positive, negatives):
        self.label = label
        self.positive = positive
        self.negatives = negatives

        # Create Voronoi volume
        self.run_qvoronoi()
        self.voronoi_volume = self.read_from_voronoi_file()


    def run_qvoronoi(self):
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
            command = f"qvoronoi.exe Fi Fo p Fv"
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            output, error = process.communicate(input=input_data)

            if process.returncode != 0:
                print(f"Error running qvoronoi.exe: {error}")
                return None

            # Save output to a temporary file
            temp_output_file = "temp\\temp_voronoi_output.txt"
            with open(temp_output_file, 'w') as f:
                f.write(output)


        except Exception as e:
            print(f"Error in execution: {e}")
        



    def read_from_voronoi_file(self):
        volumes = []
        file_path = "temp\\temp_voronoi_output.txt"
        points = np.vstack((self.positive, self.negatives))

        with open(file_path, 'r') as file:
            lines = file.readlines()

            num_colors = len(points)
            faces = [[None] * num_colors for _ in range(num_colors)]

            # Read bounded Voronoi regions
            num_planes = int(lines[0])
            for i in range(1, num_planes + 1):
                line = lines[i]
                parts = line.split()
                index1 = int(parts[1])
                index2 = int(parts[2])
                plane_params = [float(part) for part in parts[3:]]
                plane = Plane(*plane_params)
                faces[index1][index2] = Face(plane)

            # Read unbounded Voronoi regions
            num_unbounded_planes = int(lines[num_planes + 1])
            for i in range(num_planes + 2, num_planes + num_unbounded_planes + 2):
                line = lines[i]
                parts = line.split()
                index1 = int(parts[1])
                index2 = int(parts[2])
                plane_params = [float(part) for part in parts[3:]]
                plane = Plane(*plane_params)
                faces[index1][index2] = Face(plane, infinity=True)

            # Read vertex coordinates
            num_dimensions = int(lines[num_planes + num_unbounded_planes + 2])
            num_vertices = int(lines[num_planes + num_unbounded_planes + 3])
            vertices = []
            for i in range(num_planes + num_unbounded_planes + 4, num_planes + num_unbounded_planes + num_vertices + 4):
                line = lines[i]
                parts = line.split()
                coords = [float(part) for part in parts]
                vertex = coords
                vertices.append(vertex)

            # Read vertices for each face
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
            # Add faces to each diffuse color
            for i in range(num_colors):
                for j in range(num_colors):
                    if faces[i][j] is not None:
                        volumes[i].addFace(faces[i][j])
                        volumes[j].addFace(faces[i][j])

        # self.plot_3d(volumes[0])
        return volumes[0]

        



















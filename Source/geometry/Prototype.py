import numpy as np
import subprocess
import os

# from pyhull import qvoronoi

### my libraries ###
from Source.geometry.Plane import Plane
from Source.geometry.Point import Point
from Source.geometry.Face import Face
from Source.geometry.Volume import Volume


class Prototype:
    false_negatives = [
        (-5, -140, -140), (-5, -140, 140), (-5, 140, -140), (-5, 140, 140),
        (105, -140, -140), (105, -140, 140), (105, 140, -140), (105, 140, 140),
    ]

    def __init__(self, label, positive, negatives, voronoi_volume=None, add_false=False):
        self.label = label
        self.positive = np.asarray(positive, dtype=float)
        self.negatives = np.asarray(negatives, dtype=float)
        self.add_false = add_false
        self.voronoi_output = None

        if add_false:
            self.negatives = np.vstack((self.negatives, Prototype.false_negatives))

        if voronoi_volume is not None:
            self.voronoi_volume = voronoi_volume
        else:
            ok = self.run_qvoronoi()
            if not ok:
                raise RuntimeError("Error running qvoronoi")
            self.voronoi_volume = self.read_from_voronoi_file()

    @staticmethod
    def get_falseNegatives():
        return Prototype.false_negatives

    def run_qvoronoi(self):
        try:
            points = np.vstack((self.positive, self.negatives))
            dimension = points.shape[1]
            num_points = points.shape[0]

            input_data = f"{dimension}\n{num_points}\n"
            input_data += "\n".join(" ".join(map(str, point)) for point in points)

            command = [r"Source\external\qvoronoi.exe", "Fi", "Fo", "p", "Fv"]
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stdin=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            output, error = process.communicate(input=input_data)

            if process.returncode != 0:
                print(f"Error running qvoronoi.exe: {error}")
                return False

            self.voronoi_output = output

            temp_output_file = os.path.join("Source", "external", "temp", "temp_voronoi_output.txt")
            with open(temp_output_file, "w") as f:
                f.write(output)

            return True

        except Exception as e:
            print(f"Error in execution: {e}")
            return False

    def read_from_voronoi_file(self):
        file_path = os.path.join("Source", "external", "temp", "temp_voronoi_output.txt")
        points = np.vstack((self.positive, self.negatives))

        with open(file_path, "r") as file:
            lines = file.readlines()

        num_colors = len(points)
        faces = [[None] * num_colors for _ in range(num_colors)]
        cont = 0

        num_planes = int(lines[0].strip())
        cont += 1
        for i in range(1, num_planes + cont):
            parts = lines[i].split()
            index1 = int(parts[1])
            index2 = int(parts[2])
            plane = Plane(*[float(part) for part in parts[3:]])
            faces[index1][index2] = Face(plane, infinity=False)

        num_unbounded_planes = int(lines[num_planes + cont].strip())
        cont += 1
        for i in range(num_planes + cont, num_planes + num_unbounded_planes + cont):
            parts = lines[i].split()
            index1 = int(parts[1])
            index2 = int(parts[2])
            plane = Plane(*[float(part) for part in parts[3:]])
            faces[index1][index2] = Face(plane, infinity=True)

        num_dimensions = int(lines[num_planes + num_unbounded_planes + cont].strip())
        cont += 1
        num_vertices = int(lines[num_planes + num_unbounded_planes + cont].strip())
        cont += 1

        vertices = []
        for i in range(num_planes + num_unbounded_planes + cont,
                       num_planes + num_unbounded_planes + num_vertices + cont):
            coords = [float(part) for part in lines[i].split()]
            vertices.append(Point(*coords))

        num_faces = int(lines[num_planes + num_unbounded_planes + num_vertices + cont].strip())
        cont += 1
        for i in range(num_planes + num_unbounded_planes + num_vertices + cont,
                       num_planes + num_unbounded_planes + num_vertices + num_faces + cont):
            parts = lines[i].split()
            index1 = int(parts[1])
            index2 = int(parts[2])
            face = faces[index1][index2]

            for j in range(3, int(parts[0]) + 1):
                vertex_index = int(parts[j])
                if vertex_index == 0:
                    face.setInfinity()
                else:
                    face.addVertex(vertices[vertex_index - 1])

        volumes = [Volume(Point(*point)) for point in points]

        for i in range(num_colors):
            for j in range(num_colors):
                if faces[i][j] is not None:
                    volumes[i].addFace(faces[i][j])
                    volumes[j].addFace(faces[i][j])

        return volumes[0]















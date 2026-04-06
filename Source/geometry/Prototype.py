import numpy as np
import subprocess
import os

from Source.geometry.Plane import Plane
from Source.geometry.Point import Point
from Source.geometry.Face import Face
from Source.geometry.Volume import Volume
from Source.geometry.GeometryTools import GeometryTools
from Source.colorspace.ReferenceDomain import ReferenceDomain


class Prototype:
    def __init__(self, label, positive, negatives, voronoi_volume=None):
        self.label = label
        self.positive = np.asarray(positive, dtype=float)
        self.negatives = np.asarray(negatives, dtype=float)
        self.voronoi_output = None

        # New always-direct Voronoi construction approach.
        # Kept here for reference.
        # if voronoi_volume is not None:
        #     self.voronoi_volume = voronoi_volume
        # else:
        #     self.voronoi_volume = self.build_volume_voronoi(
        #         self.positive,
        #         self.negatives
        #     )

        # Reuse a precomputed Voronoi volume when provided.
        if voronoi_volume is not None:
            self.voronoi_volume = voronoi_volume
        else:
            total_points = 1 + len(self.negatives)

            # For small point sets, the direct half-space construction is more robust
            # and avoids qvoronoi failures with insufficient or degenerate inputs.
            # For larger sets, qvoronoi is much faster.
            if total_points < 10:
                self.voronoi_volume = self.build_volume_small(
                    self.positive,
                    self.negatives
                )
            else:
                ok = self.run_qvoronoi()
                if not ok:
                    raise RuntimeError("Error running qvoronoi")

                # Read the raw Voronoi cell and then clip it to the reference domain.
                raw_volume = self.read_from_voronoi_file()
                domain_volume = ReferenceDomain.default_voronoi_reference_domain().get_volume()

                self.voronoi_volume = self._clip_volume_to_domain(
                    raw_volume,
                    domain_volume
                )

    @staticmethod
    def _clip_volume_to_domain(volume, domain_volume, eps=1e-7):
        """
        Close a possibly open Voronoi volume by adding the domain faces
        and rebuilding the valid vertices.
        """
        # Work on a copy to avoid mutating the original input volume.
        clipped = volume.copy()

        # Add the reference domain boundaries so the cell becomes bounded.
        clipped.add_domain_faces_from_volume(domain_volume)

        # Remove duplicate planes before rebuilding geometry.
        clipped.deduplicate_planes()

        # Recompute face vertices from the full set of planes.
        GeometryTools.rebuild_face_vertices(clipped, eps=eps)

        # Keep only valid polygonal faces.
        valid_faces = []
        for face in clipped.getFaces():
            verts = face.getArrayVertex()
            if verts is not None and len(verts) >= 3:
                face.clearInfinity()
                valid_faces.append(face)

        return Volume(clipped.getRepresentative(), valid_faces)

    @staticmethod
    def build_volume_voronoi(positive, negatives, eps=1e-7):
        """
        Build the Voronoi cell of one prototype directly from pairwise bisector planes
        against all real negatives, then clip it with the reference domain.
        """
        rep = Point(*positive)
        volume = Volume(rep)

        # If there are no negatives, the whole domain belongs to this prototype.
        if negatives is None or len(negatives) == 0:
            domain = ReferenceDomain.default_voronoi_reference_domain().get_volume().copy()
            domain.setRepresentative(rep)

            # Rebuild vertices for the copied domain.
            GeometryTools.rebuild_face_vertices(domain, eps=eps)

            # Keep only faces with at least three valid vertices.
            valid_faces = []
            for face in domain.getFaces():
                verts = face.getArrayVertex()
                if verts is not None and len(verts) >= 3:
                    face.clearInfinity()
                    valid_faces.append(face)

            return Volume(rep, valid_faces)

        # Add one bisector plane per negative prototype.
        for idx, neg in enumerate(negatives):
            neg_point = Point(*neg)
            plane = GeometryTools.equidistant_plane_two_points(rep, neg_point)

            volume.addFace(
                Face(
                    plane,
                    vertex=None,
                    infinity=True,
                    source_index=idx + 1,
                )
            )

        # Clip the open cell with the LAB reference domain.
        domain_volume = ReferenceDomain.default_voronoi_reference_domain().get_volume()
        return Prototype._clip_volume_to_domain(volume, domain_volume, eps=eps)

    def run_qvoronoi(self):
        try:
            # Stack the positive prototype first, followed by all negatives.
            points = np.vstack((self.positive, self.negatives))
            dimension = points.shape[1]
            num_points = points.shape[0]

            # Build qvoronoi input format:
            # first dimension, then number of points, then coordinates.
            input_data = f"{dimension}\n{num_points}\n"
            input_data += "\n".join(" ".join(map(str, point)) for point in points)

            # Execute qvoronoi requesting incidence/facet/point/vertex information.
            command = [r"Source\external\qvoronoi.exe", "Fi", "Fo", "p", "Fv"]
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stdin=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            output, error = process.communicate(input=input_data)

            # Abort on execution failure.
            if process.returncode != 0:
                print(f"Error running qvoronoi.exe: {error}")
                return False

            self.voronoi_output = output

            # Persist output temporarily for the parser.
            temp_output_file = os.path.join(
                "Source", "external", "temp", "temp_voronoi_output.txt"
            )
            with open(temp_output_file, "w") as f:
                f.write(output)

            return True

        except Exception as e:
            print(f"Error in execution: {e}")
            return False

    def read_from_voronoi_file(self):
        # Read the temporary qvoronoi output file.
        file_path = os.path.join("Source", "external", "temp", "temp_voronoi_output.txt")
        points = np.vstack((self.positive, self.negatives))

        with open(file_path, "r") as file:
            lines = file.readlines()

        num_colors = len(points)

        # faces[i][j] stores the separating face between site i and site j.
        faces = [[None] * num_colors for _ in range(num_colors)]
        cont = 0

        # Read bounded planes.
        num_planes = int(lines[0].strip())
        cont += 1
        for i in range(1, num_planes + cont):
            parts = lines[i].split()
            index1 = int(parts[1])
            index2 = int(parts[2])
            plane = Plane(*[float(part) for part in parts[3:]])

            faces[index1][index2] = Face(
                plane,
                infinity=False,
                source_index=index2,
            )

        # Read unbounded planes.
        num_unbounded_planes = int(lines[num_planes + cont].strip())
        cont += 1
        for i in range(num_planes + cont, num_planes + num_unbounded_planes + cont):
            parts = lines[i].split()
            index1 = int(parts[1])
            index2 = int(parts[2])
            plane = Plane(*[float(part) for part in parts[3:]])

            faces[index1][index2] = Face(
                plane,
                infinity=True,
                source_index=index2,
            )

        # Read dimension and vertex count.
        num_dimensions = int(lines[num_planes + num_unbounded_planes + cont].strip())
        cont += 1
        num_vertices = int(lines[num_planes + num_unbounded_planes + cont].strip())
        cont += 1

        # Read vertex coordinates.
        vertices = []
        for i in range(
            num_planes + num_unbounded_planes + cont,
            num_planes + num_unbounded_planes + num_vertices + cont
        ):
            coords = [float(part) for part in lines[i].split()]
            vertices.append(Point(*coords))

        # Read face-to-vertex incidence.
        num_faces = int(lines[num_planes + num_unbounded_planes + num_vertices + cont].strip())
        cont += 1
        for i in range(
            num_planes + num_unbounded_planes + num_vertices + cont,
            num_planes + num_unbounded_planes + num_vertices + num_faces + cont
        ):
            parts = lines[i].split()
            index1 = int(parts[1])
            index2 = int(parts[2])
            face = faces[index1][index2]

            # Vertex index 0 indicates that the face is unbounded.
            for j in range(3, int(parts[0]) + 1):
                vertex_index = int(parts[j])
                if vertex_index == 0:
                    face.setInfinity()
                else:
                    face.addVertex(vertices[vertex_index - 1])

        # Build one volume per site.
        volumes = [Volume(Point(*point)) for point in points]

        # Each separating face belongs to both adjacent volumes.
        for i in range(num_colors):
            for j in range(num_colors):
                if faces[i][j] is not None:
                    volumes[i].addFace(faces[i][j])
                    volumes[j].addFace(faces[i][j])

        # Return the Voronoi cell corresponding to the positive prototype.
        return volumes[0]
from Source.input_output.Input import Input
from Source.geometry.Face import Face
from Source.geometry.Plane import Plane
from Source.geometry.Volume import Volume
from Source.geometry.Point import Point

from Source.geometry.Prototype import Prototype
from Source.fuzzy.FuzzyColorSpace import FuzzyColorSpace
from Source.interface.modules.UtilsTools import get_base_path

import numpy as np
import shlex
import re
import os

class InputFCS(Input):

    def write_file(self, name, selected_colors_lab, progress_callback=None):
        # Step 1 & 2: Create Prototype objects
        prototypes = [
            Prototype(
                label=color_name,
                positive=lab_value,
                negatives=[lab for other_name, lab in selected_colors_lab.items() if other_name != color_name]
            )
            for color_name, lab_value in selected_colors_lab.items()
        ]

        # Step 3: Create the fuzzy color space
        fuzzy_color_space = FuzzyColorSpace(space_name=name, prototypes=prototypes)

        cores_planes = self.extract_planes_and_vertex(getattr(fuzzy_color_space, "cores", None) or [])
        voronoi_planes = self.extract_planes_and_vertex(getattr(fuzzy_color_space, "prototypes", None) or [])
        supports_planes = self.extract_planes_and_vertex(getattr(fuzzy_color_space, "supports", None) or [])

        # Evitar None por seguridad
        cores_planes = cores_planes or []
        voronoi_planes = voronoi_planes or []
        supports_planes = supports_planes or []

        save_path = os.path.join(get_base_path(), "fuzzy_color_spaces")
        os.makedirs(save_path, exist_ok=True)
        file_path = os.path.join(save_path, f"{name}.fcs")

        def safe_vertices(vertices):
            """Return a clean list of 3D vertices, never None."""
            if vertices is None:
                return []
            clean = []
            for v in vertices:
                if v is None:
                    continue
                if isinstance(v, (list, tuple)) and len(v) >= 3:
                    clean.append(v)
            return clean

        def count_plane_lines(block):
            """
            Count approximate output lines for a plane block returned by
            extract_planes_and_vertex():
                [label:str, plane, num_vertex, vertices, plane, num_vertex, vertices, ..., label:str, ...]
            """
            if not block:
                return 0

            total = 0
            i = 0
            while i < len(block):
                item = block[i]

                # color label separator
                if isinstance(item, str):
                    i += 1
                    continue

                # must have plane + num + vertices
                if i + 2 >= len(block):
                    break

                vertices = safe_vertices(block[i + 2])

                # 1 line plane + 1 line num_vertex + N vertex lines
                total += 2 + len(vertices)
                i += 3

            return total

        # Total Lines for Loading
        total_lines = (
            3 +  # @name, @colorSpaceLAB, @numberOfColors
            len(selected_colors_lab) +  # each color
            sum(1 for x in cores_planes if isinstance(x, str)) + count_plane_lines(cores_planes) +
            sum(1 for x in voronoi_planes if isinstance(x, str)) + count_plane_lines(voronoi_planes) +
            sum(1 for x in supports_planes if isinstance(x, str)) + count_plane_lines(supports_planes)
        )

        current_line = 0  # written lines counter

        with open(file_path, "w") as file:
            file.write(f"@name {name}\n")
            current_line += 1
            if progress_callback:
                progress_callback(current_line, total_lines)

            file.write("@colorSpaceLAB\n")
            current_line += 1
            if progress_callback:
                progress_callback(current_line, total_lines)

            file.write(f"@numberOfColors {len(prototypes)}\n")
            current_line += 1
            if progress_callback:
                progress_callback(current_line, total_lines)

            for color_name, lab_value in selected_colors_lab.items():
                safe_name = str(color_name).replace('"', '\\"')
                file.write(f"\"{safe_name}\" {lab_value[0]} {lab_value[1]} {lab_value[2]}\n")
                current_line += 1
                if progress_callback:
                    progress_callback(current_line, total_lines)

            c = vol = s = 0

            while cores_planes or voronoi_planes or supports_planes:
                if cores_planes:
                    file.write("@core\n")
                    current_line += 1
                    if progress_callback:
                        progress_callback(current_line, total_lines)

                    c += 1
                    while c < len(cores_planes) and not isinstance(cores_planes[c], str):
                        if c + 2 >= len(cores_planes):
                            break

                        plane = cores_planes[c]
                        vertices = safe_vertices(cores_planes[c + 2])

                        plane_str = "\t".join(map(str, plane))
                        num_vertex = len(vertices)

                        file.write(f"{plane_str}\n")
                        current_line += 1
                        if progress_callback:
                            progress_callback(current_line, total_lines)

                        file.write(f"{num_vertex}\n")
                        current_line += 1
                        if progress_callback:
                            progress_callback(current_line, total_lines)

                        for v in vertices:
                            file.write(f"{v[0]} {v[1]} {v[2]}\n")
                            current_line += 1
                            if progress_callback:
                                progress_callback(current_line, total_lines)

                        c += 3

                    del cores_planes[:c]
                    c = 0

                if voronoi_planes:
                    file.write("@voronoi\n")
                    current_line += 1
                    if progress_callback:
                        progress_callback(current_line, total_lines)

                    vol += 1
                    while vol < len(voronoi_planes) and not isinstance(voronoi_planes[vol], str):
                        if vol + 2 >= len(voronoi_planes):
                            break

                        plane = voronoi_planes[vol]
                        vertices = safe_vertices(voronoi_planes[vol + 2])

                        plane_str = "\t".join(map(str, plane))
                        num_vertex = len(vertices)

                        file.write(f"{plane_str}\n")
                        current_line += 1
                        if progress_callback:
                            progress_callback(current_line, total_lines)

                        file.write(f"{num_vertex}\n")
                        current_line += 1
                        if progress_callback:
                            progress_callback(current_line, total_lines)

                        for v in vertices:
                            file.write(f"{v[0]} {v[1]} {v[2]}\n")
                            current_line += 1
                            if progress_callback:
                                progress_callback(current_line, total_lines)

                        vol += 3

                    del voronoi_planes[:vol]
                    vol = 0

                if supports_planes:
                    file.write("@support\n")
                    current_line += 1
                    if progress_callback:
                        progress_callback(current_line, total_lines)

                    s += 1
                    while s < len(supports_planes) and not isinstance(supports_planes[s], str):
                        if s + 2 >= len(supports_planes):
                            break

                        plane = supports_planes[s]
                        vertices = safe_vertices(supports_planes[s + 2])

                        plane_str = "\t".join(map(str, plane))
                        num_vertex = len(vertices)

                        file.write(f"{plane_str}\n")
                        current_line += 1
                        if progress_callback:
                            progress_callback(current_line, total_lines)

                        file.write(f"{num_vertex}\n")
                        current_line += 1
                        if progress_callback:
                            progress_callback(current_line, total_lines)

                        for v in vertices:
                            file.write(f"{v[0]} {v[1]} {v[2]}\n")
                            current_line += 1
                            if progress_callback:
                                progress_callback(current_line, total_lines)

                        s += 3

                    del supports_planes[:s]
                    s = 0


    
    def _parse_point_line(self, line):
        vals = list(map(float, line.strip().split()))
        return Point(*vals)

    def read_file(self, file_path):
        try:
            with open(file_path, 'r') as file:
                lines = iter(file.readlines())

                fcs_name = None
                cs = None
                num_colors = None

                for line in lines:
                    if fcs_name is None:
                        match = re.search(r'^@name\s*(.+)\s*$', line)
                        if match:
                            fcs_name = match.group(1).strip()

                    if cs is None:
                        match = re.search(r'^@colorSpace(?:LAB)?\s*(.*)\s*$', line)
                        if match:
                            cs = match.group(1).strip() or "LAB"

                    if num_colors is None:
                        match = re.search(r'^@numberOfColors\s*(\d+)\s*$', line)
                        if match:
                            num_colors = int(match.group(1))

                    if fcs_name and cs and num_colors is not None:
                        break

                colors = []
                for _ in range(num_colors):
                    raw = next(lines).strip()
                    parts = shlex.split(raw)
                    if len(parts) != 4:
                        raise ValueError(f"Invalid color line (expected 4 tokens): {raw}")

                    color_name = parts[0]
                    L, A, B = map(float, parts[1:])
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
                cores = []
                prototypes = []
                supports = []

                i = 0
                line = next(lines)
                while True:
                    try:
                        line = line.strip()

                        if line == "@core":
                            line = next(lines)
                            while True:
                                plane_data = line.split()
                                if not plane_data:
                                    break

                                # Create Plane
                                plane_values = list(map(float, plane_data[:4]))
                                plane = Plane(*plane_values)
                                infinity = plane_data[4].lower() == "true"

                                # Get Vertex
                                num_vertex = int(next(lines).strip())
                                vertex = [self._parse_point_line(next(lines)) for _ in range(num_vertex)]

                                # Create Face
                                faces.append(Face(plane, vertex, infinity))

                                line = next(lines).strip()
                                if line.startswith("@voronoi"):
                                    negatives = [color[1:] for idx, color in enumerate(colors) if idx != i]
                                    voronoi_volume = Volume(Point(*colors[i][1:]), faces)

                                    cores.append(Prototype(colors[i][0], colors[i][1:], negatives, voronoi_volume))

                                    faces = []
                                    break

                            line = next(lines)
                            while True:
                                plane_data = line.split()
                                if not plane_data:
                                    break

                                # Create Plane
                                plane_values = list(map(float, plane_data[:4]))
                                plane = Plane(*plane_values)
                                infinity = plane_data[4].lower() == "true"

                                # Get Vertex
                                num_vertex = int(next(lines).strip())
                                vertex = [self._parse_point_line(next(lines)) for _ in range(num_vertex)]

                                # Create Face
                                faces.append(Face(plane, vertex, infinity))

                                line = next(lines).strip()
                                if line.startswith("@support"):
                                    voronoi_volume = Volume(Point(*colors[i][1:]), faces)

                                    prototypes.append(Prototype(colors[i][0], colors[i][1:], negatives, voronoi_volume))

                                    faces = []
                                    break

                            line = next(lines)
                            while True:
                                plane_data = line.split()
                                if not plane_data:
                                    break

                                # Create Plane
                                plane_values = list(map(float, plane_data[:4]))
                                plane = Plane(*plane_values)
                                infinity = plane_data[4].lower() == "true"

                                # Get Vertex
                                num_vertex = int(next(lines).strip())
                                vertex = [self._parse_point_line(next(lines)) for _ in range(num_vertex)]

                                # Create Face
                                faces.append(Face(plane, vertex, infinity))

                                line = next(lines).strip()
                                if line.startswith("@core"):
                                    voronoi_volume = Volume(Point(*colors[i][1:]), faces)
                                    supports.append(Prototype(colors[i][0], colors[i][1:], negatives, voronoi_volume))

                                    faces = []
                                    i += 1  # Activate Next Color
                                    break

                    except StopIteration:
                        voronoi_volume = Volume(Point(*colors[i][1:]), faces)
                        supports.append(Prototype(colors[i][0], colors[i][1:], negatives, voronoi_volume))
                        break

                return color_data, FuzzyColorSpace(fcs_name, prototypes, cores, supports)

        except (ValueError, IndexError, KeyError) as e:
            raise ValueError(f"Error reading .fcs file: {str(e)}")

            



    def extract_planes_and_vertex(self, prototypes):
        data = []

        if not prototypes:
            return data

        for prototype in prototypes:
            if prototype is None:
                continue

            data.append(getattr(prototype, "label", "Unknown"))

            volume = getattr(prototype, "voronoi_volume", None)
            if volume is None:
                continue

            faces = getattr(volume, "faces", None) or []
            for face in faces:
                if face is None:
                    continue

                plane = getattr(face, "p", None)
                infinity = getattr(face, "infinity", None)
                vertex = getattr(face, "vertex", None) or []

                if not plane:
                    continue

                A = getattr(plane, "A", None)
                B = getattr(plane, "B", None)
                C = getattr(plane, "C", None)
                D = getattr(plane, "D", None)

                if None in (A, B, C, D):
                    continue

                vertex_coords = []
                for v in vertex:
                    if v is None:
                        continue

                    if hasattr(v, "x") and hasattr(v, "y") and hasattr(v, "z"):
                        vertex_coords.append((v.x, v.y, v.z))
                    elif isinstance(v, (list, tuple)) and len(v) >= 3:
                        vertex_coords.append((v[0], v[1], v[2]))

                data.append((A, B, C, D, infinity))
                data.append(len(vertex_coords))
                data.append(vertex_coords)

        return data
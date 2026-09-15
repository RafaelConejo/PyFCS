from Source.input_output.Input import Input
from Source.geometry.Face import Face
from Source.geometry.Plane import Plane
from Source.geometry.Volume import Volume
from Source.geometry.Point import Point

from Source.geometry.Prototype import Prototype
from Source.geometry.Voronoi import Voronoi
from Source.fuzzy.FuzzyColorSpace import FuzzyColorSpace
from Source.interface.modules.UtilsTools import get_base_path

import numpy as np
import tempfile
import shlex
import re
import os

class InputFCS(Input):

    def write_file(self, name, selected_colors_lab, progress_callback=None, return_fuzzy_space=False):
        # Step 1 & 2: Build the complete Voronoi diagram once, then create
        # Prototype objects reusing the corresponding precomputed Volume.
        color_items = list(selected_colors_lab.items())
        labels = [str(color_name) for color_name, _ in color_items]

        if not labels:
            raise ValueError("A fuzzy color space must contain at least one color.")

        self._validate_unique_labels(labels, max_chars=24)
        points = np.asarray([lab_value for _, lab_value in color_items], dtype=float)

        volumes = Voronoi.build_diagram(points)

        prototypes = [
            Prototype(
                label=color_name,
                positive=points[i],
                voronoi_volume=volumes[i],
            )
            for i, color_name in enumerate(labels)
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
        temp_file_path = None

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
            3 +
            len(selected_colors_lab) +
            sum(1 for x in cores_planes if isinstance(x, str)) + count_plane_lines(cores_planes) +
            sum(1 for x in voronoi_planes if isinstance(x, str)) + count_plane_lines(voronoi_planes) +
            sum(1 for x in supports_planes if isinstance(x, str)) + count_plane_lines(supports_planes)
        )

        current_line = 0
        last_reported_percent = -1

        def report_progress(force=False):
            """Report progress at most once per integer percentage point."""
            nonlocal last_reported_percent

            if not progress_callback or total_lines <= 0:
                return

            if force:
                percent = 100
                reported_line = total_lines
            else:
                percent = int((current_line * 100) / total_lines)
                percent = max(0, min(100, percent))
                reported_line = current_line

            if percent == last_reported_percent:
                return

            last_reported_percent = percent
            progress_callback(reported_line, total_lines)

        try:
            fd, temp_file_path = tempfile.mkstemp(
                prefix=f".{name}_",
                suffix=".fcs.tmp",
                dir=save_path
            )
            os.close(fd)

            with open(temp_file_path, "w", encoding="utf-8", newline="\n") as file:
                file.write(f"@name {name}\n")
                current_line += 1
                report_progress()

                file.write("@colorSpaceLAB\n")
                current_line += 1
                report_progress()

                file.write(f"@numberOfColors {len(prototypes)}\n")
                current_line += 1
                report_progress()

                for color_name, lab_value in selected_colors_lab.items():
                    safe_name = str(color_name).replace('"', '\\"')
                    file.write(f"\"{safe_name}\" {lab_value[0]} {lab_value[1]} {lab_value[2]}\n")
                    current_line += 1
                    report_progress()

                c = vol = s = 0

                while cores_planes or voronoi_planes or supports_planes:
                    if cores_planes:
                        file.write("@core\n")
                        current_line += 1
                        report_progress()

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
                            report_progress()

                            file.write(f"{num_vertex}\n")
                            current_line += 1
                            report_progress()

                            for v in vertices:
                                file.write(f"{v[0]} {v[1]} {v[2]}\n")
                                current_line += 1
                                report_progress()

                            c += 3

                        del cores_planes[:c]
                        c = 0

                    if voronoi_planes:
                        file.write("@voronoi\n")
                        current_line += 1
                        report_progress()

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
                            report_progress()

                            file.write(f"{num_vertex}\n")
                            current_line += 1
                            report_progress()

                            for v in vertices:
                                file.write(f"{v[0]} {v[1]} {v[2]}\n")
                                current_line += 1
                                report_progress()

                            vol += 3

                        del voronoi_planes[:vol]
                        vol = 0

                    if supports_planes:
                        file.write("@support\n")
                        current_line += 1
                        report_progress()

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
                            report_progress()

                            file.write(f"{num_vertex}\n")
                            current_line += 1
                            report_progress()

                            for v in vertices:
                                file.write(f"{v[0]} {v[1]} {v[2]}\n")
                                current_line += 1
                                report_progress()

                            s += 3

                        del supports_planes[:s]
                        s = 0

                report_progress(force=True)
                file.flush()
                os.fsync(file.fileno())

            os.replace(temp_file_path, file_path)
            if return_fuzzy_space:
                return file_path, fuzzy_color_space
            return file_path

        except Exception:
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except OSError:
                    pass
            raise

    
    def _parse_point_line(self, line):
        vals = list(map(float, line.strip().split()))
        if len(vals) != 3:
            raise ValueError(
                f"Invalid vertex line (expected 3 coordinates): {line.strip()}"
            )
        return Point(*vals)

    @staticmethod
    def _validate_unique_labels(labels, max_chars=24):
        seen = set()
        duplicates = set()
        for label in labels:
            if label in seen:
                duplicates.add(label)
            else:
                seen.add(label)

        if duplicates:
            duplicates = sorted(duplicates)
            raise ValueError(
                "Duplicated color labels were found in the FCS file: "
                + ", ".join(duplicates)
            )

        too_long = [label for label in labels if len(label) > max_chars]
        if too_long:
            raise ValueError(
                f"Color labels may contain at most {max_chars} characters. "
                f"Invalid label: '{too_long[0]}'."
            )

    def _read_volume_section(self, lines, index, marker, representative):
        """Read one @core/@voronoi/@support block and return (Volume, new_index)."""
        total = len(lines)

        while index < total and not lines[index].strip():
            index += 1

        if index >= total:
            raise ValueError(f"Missing {marker} section.")

        found_marker = lines[index].strip()
        if found_marker != marker:
            raise ValueError(
                f"Expected {marker} section, but found '{found_marker or '<blank>'}'."
            )

        index += 1
        faces = []

        while index < total:
            line = lines[index].strip()

            if not line:
                index += 1
                continue

            if line.startswith("@"):
                break

            plane_data = line.split()
            if len(plane_data) < 5:
                raise ValueError(
                    f"Invalid plane definition in {marker}: '{line}'."
                )

            try:
                plane_values = [float(value) for value in plane_data[:4]]
            except ValueError as exc:
                raise ValueError(
                    f"Invalid numeric plane definition in {marker}: '{line}'."
                ) from exc

            infinity_token = plane_data[4].strip().lower()
            if infinity_token not in {"true", "false"}:
                raise ValueError(
                    f"Invalid infinity flag in {marker}: '{plane_data[4]}'."
                )

            plane = Plane(*plane_values)
            infinity = infinity_token == "true"
            index += 1

            if index >= total:
                raise ValueError(
                    f"Unexpected end of file while reading vertex count in {marker}."
                )

            try:
                num_vertex = int(lines[index].strip())
            except ValueError as exc:
                raise ValueError(
                    f"Invalid vertex count in {marker}: '{lines[index].strip()}'."
                ) from exc

            if num_vertex < 0:
                raise ValueError(
                    f"Invalid negative vertex count in {marker}: {num_vertex}."
                )

            index += 1
            vertices = []

            for _ in range(num_vertex):
                if index >= total:
                    raise ValueError(
                        f"Unexpected end of file while reading vertices in {marker}."
                    )
                vertices.append(self._parse_point_line(lines[index]))
                index += 1

            faces.append(Face(plane, vertices, infinity))

        return Volume(representative, faces), index

    def read_file(self, file_path):
        """Read and validate a PyFCS .fcs file."""
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                lines = file.readlines()

            fcs_name = None
            cs = None
            num_colors = None
            data_start = None

            for index, line in enumerate(lines):
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

                if fcs_name is not None and cs is not None and num_colors is not None:
                    data_start = index + 1
                    break

            if fcs_name is None:
                raise ValueError("Missing @name field.")
            if cs is None:
                raise ValueError("Missing @colorSpaceLAB field.")
            if num_colors is None:
                raise ValueError("Missing @numberOfColors field.")
            if num_colors <= 0:
                raise ValueError("@numberOfColors must be greater than zero.")
            if data_start is None:
                raise ValueError("Invalid FCS header.")

            colors = []
            index = data_start

            for color_index in range(num_colors):
                while index < len(lines) and not lines[index].strip():
                    index += 1

                if index >= len(lines):
                    raise ValueError(
                        f"Unexpected end of file while reading color {color_index + 1} of {num_colors}."
                    )

                raw = lines[index].strip()
                index += 1

                try:
                    parts = shlex.split(raw)
                except ValueError as exc:
                    raise ValueError(f"Invalid quoted color line: {raw}") from exc

                if len(parts) != 4:
                    raise ValueError(
                        f"Invalid color line (expected label + 3 LAB values): {raw}"
                    )

                color_name = parts[0]
                try:
                    L, A, B = map(float, parts[1:])
                except ValueError as exc:
                    raise ValueError(f"Invalid LAB values in color line: {raw}") from exc

                colors.append((color_name, L, A, B))

            labels = [item[0] for item in colors]
            self._validate_unique_labels(labels, max_chars=24)

            color_data = {
                color_name: {
                    "Color": [L, A, B],
                    "positive_prototype": np.array([L, A, B], dtype=float),
                }
                for color_name, L, A, B in colors
            }

            cores = []
            prototypes = []
            supports = []

            for color_name, L, A, B in colors:
                representative = Point(L, A, B)

                core_volume, index = self._read_volume_section(
                    lines, index, "@core", representative
                )
                voronoi_volume, index = self._read_volume_section(
                    lines, index, "@voronoi", representative
                )
                support_volume, index = self._read_volume_section(
                    lines, index, "@support", representative
                )

                positive = (L, A, B)
                cores.append(
                    Prototype(
                        label=color_name,
                        positive=positive,
                        voronoi_volume=core_volume,
                    )
                )
                prototypes.append(
                    Prototype(
                        label=color_name,
                        positive=positive,
                        voronoi_volume=voronoi_volume,
                    )
                )
                supports.append(
                    Prototype(
                        label=color_name,
                        positive=positive,
                        voronoi_volume=support_volume,
                    )
                )

            trailing = [line.strip() for line in lines[index:] if line.strip()]
            if trailing:
                raise ValueError(
                    f"Unexpected content after the last support section: '{trailing[0]}'."
                )

            if not (
                len(cores) == len(prototypes) == len(supports) == num_colors
            ):
                raise ValueError(
                    "Incomplete FCS geometry: the number of core, Voronoi and support "
                    "blocks does not match @numberOfColors."
                )

            return color_data, FuzzyColorSpace(
                fcs_name,
                prototypes,
                cores,
                supports,
            )

        except (ValueError, IndexError, KeyError, TypeError, StopIteration, OSError) as exc:
            message = str(exc).strip() or "The file is incomplete or malformed."
            raise ValueError(f"Error reading .fcs file: {message}") from exc


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
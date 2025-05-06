from PyFCS.input_output.Input import Input
from PyFCS.geometry.Face import Face
from PyFCS.geometry.Plane import Plane
from PyFCS.geometry.Vector import Vector
from PyFCS.geometry.Volume import Volume
from PyFCS.geometry.Point import Point

from PyFCS import Prototype, FuzzyColorSpace

from skimage import color
import numpy as np
import re
import os

class InputFCS(Input):

    def write_file(self, name, selected_colors_lab, progress_callback=None):
        # Step 1 & 2: Create Prototype objects
        prototypes = [
            Prototype(
                label=color_name,
                positive=lab_value,
                negatives=[lab for other_name, lab in selected_colors_lab.items() if other_name != color_name],
                add_false=True
            )
            for color_name, lab_value in selected_colors_lab.items()
        ]

        # Step 3: Create the fuzzy color space
        fuzzy_color_space = FuzzyColorSpace(space_name=name, prototypes=prototypes)

        cores_planes = self.extract_planes_and_vertex(getattr(fuzzy_color_space, "cores", []))
        voronoi_planes = self.extract_planes_and_vertex(getattr(fuzzy_color_space, "prototypes", []))
        supports_planes = self.extract_planes_and_vertex(getattr(fuzzy_color_space, "supports", []))

        save_path = os.path.join(os.getcwd(), "fuzzy_color_spaces")
        os.makedirs(save_path, exist_ok=True)
        file_path = os.path.join(save_path, f"{name}.fcs")

        # Total Lines for Loading
        total_lines = (
            3 +  # @name, @colorSpaceLAB, @numberOfColors
            len(selected_colors_lab) +  # Cada color
            (len(cores_planes) // 3) * 3 + len(cores_planes) // 3 +  # @core y sus datos
            (len(voronoi_planes) // 3) * 3 + len(voronoi_planes) // 3 +  # @voronoi y sus datos
            (len(supports_planes) // 3) * 3 + len(supports_planes) // 3   # @support y sus datos
        )

        current_line = 0  # Contador de líneas escritas

        with open(file_path, "w") as file:
            file.write("@name" + f"{name}\n")
            current_line += 1
            if progress_callback:
                progress_callback(current_line, total_lines)

            file.write("@colorSpaceLAB " + "\n")
            current_line += 1
            if progress_callback:
                progress_callback(current_line, total_lines)

            file.write("@numberOfColors" + f"{len(prototypes)}\n")
            current_line += 1
            if progress_callback:
                progress_callback(current_line, total_lines)

            for color_name, lab_value in selected_colors_lab.items():
                file.write(f"{color_name} {lab_value[0]} {lab_value[1]} {lab_value[2]}\n")
                current_line += 1
                if progress_callback:
                    progress_callback(current_line, total_lines)

            c = vol = s = 0
            while c < len(cores_planes) and vol < len(voronoi_planes) and s < len(supports_planes):
                if cores_planes:
                    file.write("@core\n")
                    current_line += 1
                    if progress_callback:
                        progress_callback(current_line, total_lines)
                        
                    c += 1
                    while c < len(cores_planes) and not isinstance(cores_planes[c], str):
                        plane_str = "\t".join(map(str, cores_planes[c]))
                        num_vertex = str(cores_planes[c + 1])
                        vertices_str = "\n".join(" ".join(map(str, v)) for v in cores_planes[c + 2])
                        
                        file.write(f"{plane_str}\n")
                        current_line += 1
                        if progress_callback:
                            progress_callback(current_line, total_lines)

                        file.write(f"{num_vertex}\n")
                        current_line += 1
                        if progress_callback:
                            progress_callback(current_line, total_lines)

                        file.write(f"{vertices_str}\n")
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
                        plane_str = "\t".join(map(str, voronoi_planes[vol]))
                        num_vertex = str(voronoi_planes[vol + 1])
                        vertices_str = "\n".join(" ".join(map(str, v)) for v in voronoi_planes[vol + 2])

                        file.write(f"{plane_str}\n")
                        current_line += 1
                        if progress_callback:
                            progress_callback(current_line, total_lines)

                        file.write(f"{num_vertex}\n")
                        current_line += 1
                        if progress_callback:
                            progress_callback(current_line, total_lines)

                        file.write(f"{vertices_str}\n")
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
                        plane_str = "\t".join(map(str, supports_planes[s]))
                        num_vertex = str(supports_planes[s + 1])
                        vertices_str = "\n".join(" ".join(map(str, v)) for v in supports_planes[s + 2])

                        file.write(f"{plane_str}\n")
                        current_line += 1
                        if progress_callback:
                            progress_callback(current_line, total_lines)

                        file.write(f"{num_vertex}\n")
                        current_line += 1
                        if progress_callback:
                            progress_callback(current_line, total_lines)

                        file.write(f"{vertices_str}\n")
                        current_line += 1
                        if progress_callback:
                            progress_callback(current_line, total_lines)

                        s += 3
                    del supports_planes[:s]
                    s = 0

    
    def read_file(self, file_path):
        try:
            with open(file_path, 'r') as file:
                lines = iter(file.readlines())

                fcs_name = None
                cs = None
                num_colors = None

                for line in lines:
                    if fcs_name is None:
                        match = re.search(r'@name(\w+)', line)
                        if match:
                            fcs_name = match.group(1)

                    if cs is None:
                        match = re.search(r'@colorSpace(\w+)', line)
                        if match:
                            cs = match.group(1)

                    if num_colors is None:
                        match = re.search(r'@numberOfColors(\w+)', line)
                        if match:
                            num_colors = int(match.group(1))

                    # If find all
                    if fcs_name and cs and num_colors is not None:
                        break

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
                                if not plane_data: break

                                # Create Plane
                                plane_values = list(map(float, plane_data[:4]))
                                plane = Plane(*plane_values)
                                infinity = plane_data[4].lower() == "true"

                                # Get Vertex
                                num_vertex = int(next(lines).strip())
                                vertex = [Point(*map(float, next(lines).strip().split())) for _ in range(num_vertex)]
                                
                                # Create Face
                                faces.append(Face(plane, vertex, infinity))
                            
                                line = next(lines).strip()
                                if line.startswith("@voronoi"):
                                    negatives = [color[1:] for idx, color in enumerate(colors) if idx != i]
                                    voronoi_volume = Volume(Point(*colors[i][1:]), faces)

                                    cores.append(Prototype(colors[i][0], colors[i][1:], negatives, voronoi_volume, True))
                                    
                                    faces = []
                                    break


                            line = next(lines)
                            while True: 
                                plane_data = line.split()
                                if not plane_data: break

                                # Create Plane
                                plane_values = list(map(float, plane_data[:4]))
                                plane = Plane(*plane_values)
                                infinity = plane_data[4].lower() == "true"

                                # Get Vertex
                                num_vertex = int(next(lines).strip())
                                vertex = [Point(*map(float, next(lines).strip().split())) for _ in range(num_vertex)]
                                
                                # Create Face
                                faces.append(Face(plane, vertex, infinity))
                            
                                line = next(lines).strip()
                                if line.startswith("@support"):
                                    voronoi_volume = Volume(Point(*colors[i][1:]), faces)

                                    prototypes.append(Prototype(colors[i][0], colors[i][1:], negatives, voronoi_volume, True))
                                    
                                    faces = []
                                    break

                                    
                            line = next(lines)
                            while True: 
                                plane_data = line.split()
                                if not plane_data: break

                                # Create Plane
                                plane_values = list(map(float, plane_data[:4]))
                                plane = Plane(*plane_values)
                                infinity = plane_data[4].lower() == "true"

                                # Get Vertex
                                num_vertex = int(next(lines).strip())
                                vertex = [Point(*map(float, next(lines).strip().split())) for _ in range(num_vertex)]
                                
                                # Create Face
                                faces.append(Face(plane, vertex, infinity))
                            
                                line = next(lines).strip()
                                if line.startswith("@core"):
                                    voronoi_volume = Volume(Point(*colors[i][1:]), faces)
                                    supports.append(Prototype(colors[i][0], colors[i][1:], negatives, voronoi_volume, True))
                                    
                                    faces = []
                                    i += 1      # Activate Next Color
                                    break

                    except StopIteration:
                        voronoi_volume = Volume(Point(*colors[i][1:]), faces)
                        supports.append(Prototype(colors[i][0], colors[i][1:], negatives, voronoi_volume, True))
                        break

                return color_data, FuzzyColorSpace(fcs_name, prototypes, cores, supports)            
                                

        except (ValueError, IndexError, KeyError) as e:
            raise ValueError(f"Error reading .fcs file: {str(e)}")
        



    def extract_planes_and_vertex(self, prototypes):
        data = []
        
        for prototype in prototypes:
            data.append(prototype.label)
            for face in getattr(prototype.voronoi_volume, "faces", []):  
                plane = getattr(face, "p", None)  
                infinity = getattr(face, "infinity", None)
                vertex = getattr(face, "vertex", [])  
                
                if plane:
                    A = getattr(plane, "A", None)
                    B = getattr(plane, "B", None)
                    C = getattr(plane, "C", None)
                    D = getattr(plane, "D", None)
                    
                    if None not in (A, B, C, D):
                        # Extrae las coordenadas de los vértices si existen
                        vertex_coords = [(v.x, v.y, v.z) if hasattr(v, 'x') else tuple(v) for v in vertex]
                        data.append((A, B, C, D, infinity))
                        data.append(len(vertex_coords))
                        data.append(vertex_coords)
        
        return data

    
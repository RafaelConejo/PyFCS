from Source.input_output.Input import Input
from Source.geometry.Face import Face
from Source.geometry.Plane import Plane
from Source.geometry.Volume import Volume
from Source.geometry.Point import Point

from Source.geometry.Prototype import Prototype
from Source.geometry.Voronoi import Voronoi
from Source.fuzzy.FuzzyColorSpaceBuilder import FuzzyColorSpaceBuilder, lab_to_rgb_model_checked
from Source.colorspace.ReferenceDomain import ReferenceDomain
from Source.fuzzy.FuzzyColorSpace import FuzzyColorSpace
from Source.interface.modules.UtilsTools import get_base_path, validate_color_space_name

import numpy as np
import tempfile
import shlex
import re
import os

class InputFCS(Input):

    def write_file(self, name, selected_colors_lab, progress_callback=None,
                   return_fuzzy_space=False, *, color_space="LAB",
                   reference_domain=None, lambda1=0.5, lambda2=1.5,
                   disjoint=True, covering=True, samples=27,
                   negative_prototypes=None, description=None, tconorm="bounded_sum",
                   model_points=None):
        """Build and atomically save the full space, with backwards-compatible blocks.

        Input colors are CIELAB from the existing creation/UI tools; geometry
        and serialized representatives use the chosen LAB or 0..255 RGB model.
        ``negative_prototypes`` is a dict keyed by LABEL and containing LAB
        coordinate triples, or labels of other categories.
        """
        name = validate_color_space_name(name)
        tconorm = str(tconorm).strip().lower()
        if tconorm not in ("bounded_sum", "max"):
            raise ValueError("tConorm must be 'bounded_sum' or 'max'.")
        if not hasattr(selected_colors_lab, "items"):
            raise ValueError("Color prototypes must be a mapping of names to coordinates.")
        items = list(selected_colors_lab.items())
        labels = [str(label) for label, _ in items]
        if any(not label.strip() for label in labels):
            raise ValueError("Every color must have a non-empty label.")
        self._validate_unique_labels(labels)
        if len(items) < 2:
            raise ValueError("At least two colors are required.")
        color_space = str(color_space).upper()
        domain = reference_domain or ReferenceDomain.for_color_space(color_space)
        points_lab = {}
        for label, value in items:
            try:
                xyz = np.asarray(value, dtype=float).reshape(-1)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid coordinates for '{label}'.") from exc
            if xyz.size != 3 or not np.all(np.isfinite(xyz)):
                raise ValueError(f"'{label}' must contain exactly three finite LAB coordinates.")
            points_lab[label] = xyz

        def as_model(x):
            xyz = np.asarray(x, dtype=float).reshape(3)
            if color_space == "LAB":
                return xyz
            return lab_to_rgb_model_checked(xyz.reshape(1, 3))[0]

        native_model_points = dict(model_points or {})
        unknown_model_labels = set(native_model_points) - set(points_lab)
        if unknown_model_labels:
            raise ValueError("Unknown names in the native-model prototype data: "
                             + ", ".join(sorted(unknown_model_labels)))
        # Preserve loaded/native RGB coordinates (including fractional channels)
        # exactly when a category was not edited. Newly edited colors still
        # follow the regular CIELAB-to-model conversion path.
        model_points = {}
        for label, lab in points_lab.items():
            if label in native_model_points:
                coords = np.asarray(native_model_points[label], dtype=float).reshape(-1)
                if coords.size != 3 or not np.all(np.isfinite(coords)):
                    raise ValueError(f"Invalid native model coordinates for '{label}'.")
                model_points[label] = coords.copy()
            else:
                model_points[label] = as_model(lab)
        negatives_model = {}
        for label, seq in (negative_prototypes or {}).items():
            negatives_model[label] = [model_points[item] if isinstance(item,str) and item in model_points
                                       else as_model(item) for item in seq]

        space = FuzzyColorSpaceBuilder.build(
            name, model_points, color_space=color_space, reference_domain=domain,
            lambda1=float(lambda1), lambda2=float(lambda2), disjoint=disjoint,
            covering=covering, samples=int(samples),
            negative_prototypes=negatives_model, description=description)

        # Until multiple-positive membership is implemented, each category
        # still contains one atomic fuzzy color.  The new on-disk layout is
        # already compatible with later multi-granule extensions.
        space.tconorm = tconorm

        folder = os.path.join(get_base_path(), "fuzzy_color_spaces")
        os.makedirs(folder, exist_ok=True)
        dest = os.path.join(folder, name + ".fcs")
        tmp = None

        def coords(p):
            return " ".join(format(float(v), ".17g") for v in p)

        # Format for PyFCS 2.0: explicit granule count per category.
        # The current geometry engine still writes ONE granule per category.
        content = [
            "################################################################################",
            "#",
            "# PyFCS - Python Fuzzy Color Software",
            "# FUZZY COLOR SPACE FILE",
            "#",
            "# General information:",
            "#   @name                       Fuzzy color space name",
            "#   @description                Space typology",
            "#   @colorSpace                 Color space (LAB or RGB)",
            "#   @reference                  Domain: min1 max1 min2 max2 min3 max3",
            "#",
            "# Geometry parameters:",
            "#   @lambda1                    Core scaling factor",
            "#   @lambda2                    Support scaling factor",
            "#",
            "# Space configuration:",
            "#   @disjoint                   Disjoint categories (true/false)",
            "#   @covering                   Domain covering (true/false)",
            "#   @samples                    Grid samples for non-covering spaces",
            "#   @tConorm                    Granule union (bounded_sum or max)",
            "#",
            "# Color definitions:",
            "#   @numberOfColors             Number of color categories",
            "#   \"label\" n                  Category name and number of granules",
            "#   X Y Z                       Positive prototype (one per granule)",
            "#   @numberOfNegatives          Explicit negatives per category",
            "#   @numberOfAuxiliaryNegatives Auxiliary sampling negatives",
            "#",
            "# Geometry (for each granule, in category and granule order):",
            "#   @core                       Core volume",
            "#   @voronoi                    Voronoi volume (0.5-cut)",
            "#   @support                    Support volume",
            "#                               Faces, planes and vertices are stored",
            "#",
            "# Created by RafaConejo",
            "#",
            "################################################################################",
            f"@name {name}",
            f"@description{space.description}",
            f"@colorSpace{color_space}",
            "@reference " + coords(domain.bounds),
            f"@lambda1 {space.lambda1:.17g}",
            f"@lambda2 {space.lambda2:.17g}",
            f"@disjoint {str(space.disjoint).lower()}",
            f"@covering {str(space.covering).lower()}",
            f"@samples {space.samples}",
            f"@tConorm {tconorm}",
            f"@numberOfColors {len(items)}",
        ]
        for label, p in model_points.items():
            label_quoted = '"' + label.replace('\\', '\\\\').replace('"', '\\"') + '"'
            content.append(f"{label_quoted} 1")
            content.append(coords(p))

        auxiliary = {tuple(row) for row in space.auxiliary_negatives}
        # Store only the *real* per-category negatives; the sampled points
        # are written once and reattached to each category at load time.
        for label in labels:
            real = [q for q in space.negative_prototypes.get(label, [])
                    if tuple(q) not in auxiliary]
            label_quoted = '"' + label.replace('\\','\\\\').replace('"', '\\"') + '"'
            content.append(f"@numberOfNegatives {label_quoted} {len(real)}")
            content.extend(coords(p) for p in real)
        content.append(f"@numberOfAuxiliaryNegatives {len(space.auxiliary_negatives)}")
        content.extend(coords(row) for row in space.auxiliary_negatives)

        for i in range(len(space.prototypes)):
            for marker, block in (("@core",space.cores[i]),
                                  ("@voronoi",space.prototypes[i]),
                                  ("@support",space.supports[i])):
                content.append(marker)
                for face in block.voronoi_volume.getFaces():
                    pl = face.getPlane()
                    content.append(coords((pl.A,pl.B,pl.C,pl.D)) + " " + str(bool(face.infinity)).lower())
                    vertices = face.getArrayVertex() or []
                    content.append(str(len(vertices)))
                    content.extend(coords((v.x,v.y,v.z)) for v in vertices)
        try:
            fd,tmp = tempfile.mkstemp(dir=folder, prefix="."+name+"_",suffix=".fcs.tmp")
            with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as handle:
                total = len(content)
                for j, row in enumerate(content,1):
                    handle.write(row+"\n")
                    if progress_callback and (j % 100 == 0 or j == total):
                        progress_callback(j,total)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp,dest)
        except Exception:
            if tmp and os.path.isfile(tmp):
                os.unlink(tmp)
            raise
        return (dest,space) if return_fuzzy_space else dest

    @staticmethod
    def _valid_plane_data(values):
        """Non-throwing validity check, usable by GUI import checks and tests."""
        try:
            coords = np.asarray(values, dtype=float)
            return (coords.shape == (4,) and np.all(np.isfinite(coords))
                    and np.linalg.norm(coords[:3]) > 1e-14)
        except (TypeError, ValueError):
            return False

    def _parse_point_line(self, line):
        vals = list(map(float, line.strip().split()))
        if len(vals) != 3 or not np.all(np.isfinite(vals)):
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
            if not self._valid_plane_data(plane_values):
                raise ValueError(f"Invalid or degenerate plane in {marker}: '{line}'.")

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

    @staticmethod
    def _jfcs_header_value(line, marker):
        """JFCS writes metadata without a space after @key."""
        if not line.startswith(marker):
            raise ValueError(f"Expected JFCS header {marker}.")
        return line[len(marker):].strip()

    def _read_jfcs_atomic(self, lines):
        """Load Soto/JFCS checked atomic Voronoi FCS files losslessly.

        Unlike a PyFCS file, JFCS stores color metadata, a face count and
        then a core/Voronoi/support triplet *for every face*. Do not rebuild
        the geometry: the original faces are already serialized.
        """
        from skimage import color as skcolor

        headers = {}
        index = 0
        fields = (
            "name", "description", "fuzzyColorSpaceType", "crispColorSpaceType",
            "reference", "lambda1", "lambda2", "partition", "disjoint",
            "covering", "samples", "numberOfColors",
        )
        while index < len(lines):
            line = lines[index]
            match = next((key for key in fields if line.startswith("@" + key)), None)
            if match is None:
                raise ValueError(f"Unexpected JFCS header: {line!r}")
            if match in headers:
                raise ValueError(f"Duplicate JFCS header: @{match}")
            headers[match] = self._jfcs_header_value(line, "@" + match)
            index += 1
            if match == "numberOfColors":
                break

        if "numberOfColors" not in headers:
            raise ValueError("Missing JFCS @numberOfColors.")
        required = ("name", "crispColorSpaceType", "reference", "lambda1", "lambda2")
        missing = [field for field in required if field not in headers or not headers[field]]
        if missing:
            raise ValueError("Missing JFCS field(s): " + ", ".join(missing))

        color_count = int(headers["numberOfColors"])
        if not 1 <= color_count <= 10000:
            raise ValueError("Invalid JFCS color count.")
        # java.awt.color.ColorSpace: CS_sRGB=1000, TYPE_RGB=5, TYPE_Lab=1.
        jmr_type = int(headers["crispColorSpaceType"])
        if jmr_type in (1000, 5):
            color_space = "RGB"
        elif jmr_type == 1:
            color_space = "LAB"
        else:
            raise ValueError(
                f"Unsupported JFCS crisp color space type {jmr_type} "
                "(currently supported: sRGB/RGB and LAB)."
            )
        domain = ReferenceDomain.from_bounds(headers["reference"].split())
        lambda1 = float(headers["lambda1"])
        lambda2 = float(headers["lambda2"])
        if not (np.isfinite(lambda1) and np.isfinite(lambda2)):
            raise ValueError("JFCS scaling parameters must be finite.")
        if not (0 <= lambda1 <= 1 and 1 <= lambda2 <= 2):
            raise ValueError("Invalid JFCS lambda parameters.")

        def parse_bool(key, default):
            value = headers.get(key, default).strip().lower()
            if value not in ("true", "false"):
                raise ValueError(f"Invalid JFCS @{key} value: {value!r}.")
            return value == "true"

        disjoint = parse_bool("disjoint", "true")
        covering = parse_bool("covering", "true")
        if "partition" in headers and parse_bool("partition", "false") != (disjoint and covering):
            raise ValueError("Inconsistent JFCS partition/disjoint/covering fields.")
        samples = int(headers.get("samples", "0"))
        if samples < 0:
            raise ValueError("JFCS samples must not be negative.")

        colors = []
        negatives = {}
        auxiliary = []
        cores, prototypes, supports = [], [], []
        for color_number in range(color_count):
            if index >= len(lines):
                raise ValueError(f"Incomplete JFCS color #{color_number + 1}.")
            # Java writes tab-delimited labels without quoting them. Some
            # ISCC-NBS color labels contain spaces, so split from the right.
            raw_row = lines[index]; index += 1
            parts = raw_row.rsplit(None, 4)
            if len(parts) != 5 or parts[-1].lower() not in ("true", "false"):
                parts = raw_row.rsplit(None, 3)  # older JFCS without boolean
            if len(parts) not in (4, 5):
                raise ValueError(f"Invalid JFCS representative row for color #{color_number + 1}.")
            label = parts[0].strip('"').strip()
            if not label:
                raise ValueError("JFCS color labels must not be empty.")
            xyz = np.asarray([float(v) for v in parts[1:4]], dtype=float)
            if not np.all(np.isfinite(xyz)) or not domain.contains_coordinates(xyz, eps=1e-6):
                raise ValueError(f"JFCS color {label!r} is outside its reference domain.")
            if len(parts) == 5 and parts[4].lower() not in ("true", "false"):
                raise ValueError(f"Invalid JFCS auxiliary flag for {label!r}.")
            is_auxiliary = len(parts) == 5 and parts[4].lower() == "true"
            if index >= len(lines):
                raise ValueError(f"Missing JFCS negative count for {label!r}.")
            neg_count = int(self._jfcs_header_value(lines[index], "@numberOfNegatives"))
            index += 1
            if not 0 <= neg_count <= 100000:
                raise ValueError("Invalid JFCS negative count.")
            if index + neg_count > len(lines):
                raise ValueError("Truncated JFCS negative list.")
            neg = []
            for _ in range(neg_count):
                values = tuple(map(float, lines[index].split())); index += 1
                if len(values) != 3 or not np.all(np.isfinite(values)):
                    raise ValueError("Invalid JFCS negative prototype.")
                neg.append(values)
            if index >= len(lines):
                raise ValueError(f"Missing JFCS face count for {label!r}.")
            n_faces = int(lines[index]); index += 1
            if not 0 <= n_faces <= 100000:
                raise ValueError("Invalid JFCS face count.")

            representative = Point(*xyz)
            faces = {"@core": [], "@voronoi": [], "@support": []}
            for _ in range(n_faces):
                for marker in ("@core", "@voronoi", "@support"):
                    if index >= len(lines) or lines[index] != marker:
                        raise ValueError(f"Missing JFCS {marker} face for {label!r}.")
                    index += 1
                    if index >= len(lines):
                        raise ValueError(f"Missing JFCS plane following {marker}.")
                    plane_row = lines[index].split(); index += 1
                    if len(plane_row) != 5 or plane_row[4].lower() not in ("true", "false"):
                        raise ValueError(f"Invalid JFCS plane in {marker} for {label!r}.")
                    coeffs = [float(value) for value in plane_row[:4]]
                    if not np.all(np.isfinite(coeffs)):
                        raise ValueError(f"Non-finite JFCS plane in {marker}.")
                    if index >= len(lines):
                        raise ValueError(f"Missing JFCS vertex count in {marker}.")
                    n_vertices = int(lines[index]); index += 1
                    if n_vertices < 0 or index + n_vertices > len(lines):
                        raise ValueError(f"Invalid JFCS vertex count in {marker}.")
                    vertices = []
                    for _ in range(n_vertices):
                        vertex = self._parse_point_line(lines[index]); index += 1
                        if not np.all(np.isfinite((vertex.x, vertex.y, vertex.z))):
                            raise ValueError(f"Non-finite JFCS vertex in {marker}.")
                        vertices.append(vertex)
                    faces[marker].append(Face(Plane(*coeffs), vertices, plane_row[4].lower()=="true"))

            if is_auxiliary:
                auxiliary.append(tuple(xyz))
                continue
            if label in negatives:
                raise ValueError(f"Duplicated JFCS color label: {label!r}.")
            colors.append((label, xyz))
            negatives[label] = neg
            cores.append(Prototype(label, xyz, Volume(representative, faces["@core"])))
            prototypes.append(Prototype(label, xyz, Volume(representative, faces["@voronoi"])))
            supports.append(Prototype(label, xyz, Volume(representative, faces["@support"])))

        if index != len(lines):
            raise ValueError(f"Unexpected content after the last JFCS color (line {index + 1}).")
        if not colors:
            raise ValueError("The JFCS file contains no named colors.")
        labels = [label for label, _ in colors]
        self._validate_unique_labels(labels, max_chars=128)

        color_data = {}
        for label, xyz in colors:
            if color_space == "RGB":
                lab = skcolor.rgb2lab((xyz / 255.0).reshape(1, 1, 3))[0, 0]
            else:
                lab = xyz
            color_data[label] = {
                "Color": list(map(float, lab)),
                "positive_prototype": np.asarray(lab, dtype=float),
                "fcs_original_label": label,
            }
        space = FuzzyColorSpace(
            headers["name"], prototypes, cores, supports,
            color_space=color_space, reference_domain=domain,
            lambda1=lambda1, lambda2=lambda2,
            disjoint=disjoint, covering=covering, samples=samples,
            negative_prototypes=negatives,
            auxiliary_negatives=auxiliary,
            description=headers.get("description"),
        )
        # Useful when editing/resaving: JFCS may store its sampling points
        # implicitly in the face geometry rather than as listed negatives.
        space.source_file_format = "JFCS_ATOMIC"
        space.jfcs_crisp_color_space_type = jmr_type
        return color_data, space

    def read_file(self, file_path):
        """Load JFCS atomic, PyFCS legacy, and new single-granule FCS files."""
        from skimage import color as skcolor
        try:
            with open(file_path,"r",encoding="utf-8") as source:
                # Ignore explanatory comments in either file generation.
                lines = [s.strip() for s in source if s.strip() and not s.lstrip().startswith("#")]
            # Original JFCS uses compact @keys and interleaved per-face blocks.
            # Keep this reader independent from the native PyFCS format.
            if any(row.startswith("@crispColorSpaceType") for row in lines[:18]):
                return self._read_jfcs_atomic(lines)
            header={}
            index=0
            while index<len(lines) and not lines[index].startswith("@numberOfColors"):
                line=lines[index]
                if line.startswith("@"):
                    if line.startswith("@description"):
                        header["description"] = line[len("@description"):].strip()
                    elif line.upper().startswith("@COLORSPACELAB"):
                        header["colorSpace"]="LAB"
                    elif line.upper().startswith("@COLORSPACERGB"):
                        header["colorSpace"]="RGB"
                    else:
                        parts=line[1:].split(None,1)
                        if len(parts)==2:
                            header[parts[0]]=parts[1]
                index+=1
            if index>=len(lines):
                raise ValueError("Missing @numberOfColors header.")
            count=int(lines[index].split(None,1)[1]);index+=1
            if count<=0:
                raise ValueError("@numberOfColors must be positive.")
            name=header.get("name")
            if not name:
                raise ValueError("Missing @name.")
            mode=header.get("colorSpace", "LAB").upper()
            if mode not in ("LAB","RGB"):
                raise ValueError("Unsupported geometry color space.")
            def boolean(key, default):
                value=header.get(key,str(default)).strip().lower()
                if value not in ("true","false"):
                    raise ValueError("Invalid boolean @"+key)
                return value=="true"
            disjoint=boolean("disjoint",True)
            covering=boolean("covering",True)
            domain=ReferenceDomain.from_bounds([float(x) for x in header["reference"].split()]) if "reference" in header else ReferenceDomain.for_color_space(mode)
            lambda1=float(header.get("lambda1","0.5"))
            lambda2=float(header.get("lambda2","1.5"))
            samples=int(header.get("samples","0"))
            tconorm=header.get("tConorm", "bounded_sum").strip().lower()
            if tconorm not in ("bounded_sum", "max"):
                raise ValueError("Unsupported @tConorm: " + tconorm)
            if not (0 <= lambda1 < 1 and 1 < lambda2 <= 2):
                raise ValueError("Invalid lambda parameters.")
            colors = []
            # PyFCS older:  "Pink" L a b
            # PyFCS 2.0:   "Pink" 1  /  L a b (next line)
            # Keep the original JFCS parser above fully independent.
            for _ in range(count):
                if index >= len(lines):
                    raise ValueError("Incomplete color list.")
                row = shlex.split(lines[index])
                index += 1
                if len(row) == 4:
                    label = row[0]
                    coordinates = row[1:]
                elif len(row) == 2:
                    label = row[0]
                    try:
                        n_granules = int(row[1])
                    except ValueError as exc:
                        raise ValueError(f"Invalid granule count for '{label}'.") from exc
                    if n_granules < 1:
                        raise ValueError(f"'{label}' needs at least one granule.")
                    if n_granules > 1:
                        raise ValueError(
                            f"'{label}' declares {n_granules} granules, but the "
                            "granular membership engine has not been implemented yet. "
                            "This FCS cannot be loaded safely by this version."
                        )
                    if index >= len(lines):
                        raise ValueError(f"Missing prototype coordinates for '{label}'.")
                    coordinates = lines[index].split()
                    index += 1
                else:
                    raise ValueError("Invalid color representative row: " + lines[index-1])
                if len(coordinates) != 3:
                    raise ValueError(f"'{label}' must have three prototype coordinates.")
                xyz = np.asarray([float(value) for value in coordinates], dtype=float)
                if not np.all(np.isfinite(xyz)):
                    raise ValueError(f"Non-finite prototype coordinates for '{label}'.")
                colors.append((label, xyz))
            labels=[x[0] for x in colors]
            self._validate_unique_labels(labels)
            points=np.asarray([x[1] for x in colors])
            Voronoi._validate_points_in_domain(points,domain,Voronoi.DEFAULT_EPS)
            negatives={}
            auxiliaries=[]
            while index < len(lines) and lines[index].startswith(("@numberOfNegatives", "@numberOfAuxiliaryNegatives")):
                line=lines[index]
                if line.startswith("@numberOfNegatives"):
                    parts=shlex.split(line)
                    if len(parts)!=3:
                        raise ValueError("Invalid @numberOfNegatives header.")
                    _,label,n=parts
                    if label not in labels or label in negatives:
                        raise ValueError("Invalid/duplicate negative list label: "+label)
                    count_negative = int(n)
                    if count_negative < 0 or index + 1 + count_negative > len(lines):
                        raise ValueError(f"Invalid negative count for '{label}'.")
                    index += 1
                    neg = []
                    for _ in range(count_negative):
                        vals = np.asarray(self._parse_point_line(lines[index]).get_double_point(), dtype=float)
                        neg.append(tuple(vals))
                        index += 1
                    negatives[label] = neg
                else:
                    parts=line.split()
                    if len(parts)!=2:
                        raise ValueError("Invalid auxiliary count.")
                    count_auxiliary = int(parts[1])
                    if count_auxiliary < 0 or index + 1 + count_auxiliary > len(lines):
                        raise ValueError("Invalid auxiliary negative count.")
                    index += 1
                    for _ in range(count_auxiliary):
                        vals = self._parse_point_line(lines[index]).get_double_point()
                        auxiliaries.append(tuple(vals))
                        index += 1

            # Historical FCS files have no negative metadata. Reconstruct
            # partition negatives from every OTHER positive site.
            if not negatives:
                negatives={label:[tuple(points[j]) for j in range(count) if j!=i]
                           for i,label in enumerate(labels)}
            if auxiliaries:
                negatives={label:list(negatives.get(label,[]))+list(auxiliaries)
                           for label in labels}

            cores=[];prototypes=[];supports=[]
            for label,xyz in colors:
                point=Point(*xyz)
                sections=[]
                for marker in ("@core","@voronoi","@support"):
                    volume,index=self._read_volume_section(lines,index,marker,point)
                    sections.append(Prototype(label=label,positive=xyz,voronoi_volume=volume))
                cores.append(sections[0]);prototypes.append(sections[1]);supports.append(sections[2])
            if index!=len(lines):
                raise ValueError("Unexpected data after the last volume.")
            # Domain caps are persisted as regular planes by legacy/native
            # PyFCS files. Re-identify the six canonical box planes on read;
            # JFCS files use a separate reader and must remain untouched.
            domain_planes = [face.getPlane() for face in domain.get_volume().getFaces()]
            for category in (cores, prototypes, supports):
                for proto in category:
                    for face in proto.voronoi_volume.getFaces():
                        if any(face.getPlane().isEqual(boundary, eps=1e-8)
                               for boundary in domain_planes):
                            face.setDomainBoundary(True)

            if mode=="LAB":
                labs=[np.asarray(xyz,dtype=float) for _,xyz in colors]
            else:
                labs=[skcolor.rgb2lab((np.clip(xyz,0,255)/255.0).reshape(1,1,3))[0,0]
                      for _,xyz in colors]
            # UI and CIEDE metrics always receive CIELAB representatives.
            color_data={label:{"Color":list(map(float,lab)),
                               "positive_prototype":np.asarray(lab,dtype=float),
                               "fcs_original_label":label}
                        for (label,_),lab in zip(colors,labs)}
            space=FuzzyColorSpace(name,prototypes,cores,supports,
                color_space=mode,reference_domain=domain,
                lambda1=lambda1,lambda2=lambda2,disjoint=disjoint,
                covering=covering,samples=samples,negative_prototypes=negatives,
                auxiliary_negatives=auxiliaries,
                description=header.get("description"))
            # Stored for forward compatibility; one-granule membership is
            # identical under MAX and BOUNDED_SUM.
            space.tconorm = tconorm
            return color_data,space
        except (ValueError,IndexError,KeyError,TypeError,OSError) as exc:
            raise ValueError("Error reading .fcs file: "+str(exc)) from exc

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
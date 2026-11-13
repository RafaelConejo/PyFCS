"""PyFCS JSON v1 persistence: full geometry, atomic and granular FCS.

The native schema is intentionally small and stable::

    format_version
    metadata: {name, geometry_input_sha256}
    model: {color_space, reference_domain, construction, categories}
    geometry: {granules: {label: {core, voronoi, support}}}

Membership operators (MAX/BOUNDED_SUM) are intentionally NOT persisted.
Geometry is always loaded from the saved planes/faces; Voronoi is never
rerun by read_file().
"""

import hashlib
import json
import os
import tempfile

import numpy as np
from skimage import color as skcolor

from Source.colorspace.ReferenceDomain import ReferenceDomain
from Source.fuzzy.FuzzyColorSpace import FuzzyColorSpace
from Source.fuzzy.GranularFuzzyColor import GranularFuzzyColor
from Source.fuzzy.GranularFuzzyColorSpace import GranularFuzzyColorSpace
from Source.fuzzy.FuzzyColorSpaceBuilder import FuzzyColorSpaceBuilder, lab_to_rgb_model_checked
from Source.geometry.Face import Face
from Source.geometry.Plane import Plane
from Source.geometry.Point import Point
from Source.geometry.Prototype import Prototype
from Source.geometry.Volume import Volume
from Source.geometry.Voronoi import Voronoi
from Source.input_output.Input import Input
from Source.interface.modules.UtilsTools import get_base_path, validate_color_space_name


class InputJSON(Input):
    FORMAT_VERSION = 1

    @staticmethod
    def _triple(value, what):
        try:
            data = np.asarray(value, dtype=float).reshape(-1)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{what} must contain three numeric coordinates.") from exc
        if data.shape != (3,) or not np.all(np.isfinite(data)):
            raise ValueError(f"{what} must contain three finite coordinates.")
        return [float(x) for x in data]

    @staticmethod
    def _numeric(value, what):
        if isinstance(value, bool):
            raise ValueError(f"{what} must be a finite number, not a boolean.")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{what} must be a finite number.") from exc
        if not np.isfinite(number):
            raise ValueError(f"{what} must be finite.")
        return number

    @classmethod
    def _point_list(cls, values, what):
        if not isinstance(values, list):
            raise ValueError(f"{what} must be a list of coordinate triples.")
        return [cls._triple(point, f"{what}[{i}]") for i, point in enumerate(values)]

    @staticmethod
    def _label(value, what):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{what} must be a non-empty string.")
        return value

    @staticmethod
    def _canonical_points(points):
        """Float-normalized and order-independent, without precision loss."""
        return sorted([[float(c) for c in p] for p in points])

    @classmethod
    def geometry_inputs(cls, model):
        """Return the geometry-relevant *canonical* inputs for hash creation.

        Labels, category order, per-category display metadata, and membership
        settings are deliberately excluded. For non-disjoint construction the
        explicit negative list is tied to the relevant site's coordinates.
        """
        construction = model["construction"]
        disjoint = construction["disjoint"]
        sites = []
        for category in model["categories"]:
            negatives = [] if disjoint else cls._canonical_points(category["negatives"])
            siblings = [cls._triple(g["prototype"], "prototype")
                        for g in category["granules"]]
            for granule in category["granules"]:
                item = {"prototype": cls._triple(granule["prototype"], "prototype")}
                if not disjoint:
                    item["negatives"] = negatives
                    # Sibling positives limit the cell, but are not semantic
                    # negatives. They matter for the hash only when present.
                    if len(siblings) > 1:
                        item["siblings"] = cls._canonical_points(
                            p for p in siblings if p != item["prototype"])
                sites.append(item)
        sites.sort(key=lambda entry: (entry["prototype"], entry.get("negatives", [])))
        return {
            "color_space": model["color_space"],
            "reference_domain": [list(map(float, row)) for row in model["reference_domain"]],
            "construction": {
                "method": construction["method"],
                "lambda1": float(construction["lambda1"]),
                "lambda2": float(construction["lambda2"]),
                "disjoint": disjoint,
                "covering": construction["covering"],
                "aux_negatives": cls._canonical_points(construction["aux_negatives"]),
            },
            "sites": sites,
        }

    @classmethod
    def geometry_input_sha256(cls, model):
        canonical = json.dumps(
            cls.geometry_inputs(model), sort_keys=True,
            separators=(",", ":"), ensure_ascii=False, allow_nan=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def _volume_to_data(cls, prototype):
        faces = []
        for face in prototype.voronoi_volume.getFaces():
            plane = face.getPlane()
            vertices = face.getArrayVertex()
            faces.append({
                "plane": [float(plane.A), float(plane.B), float(plane.C), float(plane.D)],
                "vertices": None if vertices is None else [
                    [float(v.x), float(v.y), float(v.z)] for v in vertices
                ],
                "infinity": bool(face.isInfinity()),
                "domain_boundary": bool(face.isDomainBoundary()),
            })
        return {"faces": faces}

    @classmethod
    def _volume_from_data(cls, payload, label, representative, kind):
        if not isinstance(payload, dict) or not isinstance(payload.get("faces"), list):
            raise ValueError(f"Invalid {kind} faces for granule '{label}'.")
        if not payload["faces"]:
            raise ValueError(f"Empty {kind} geometry for granule '{label}'.")
        faces = []
        for i, entry in enumerate(payload["faces"]):
            location = f"{label}/{kind}/face {i}"
            if not isinstance(entry, dict):
                raise ValueError(f"Invalid face in {location}.")
            coefficients = entry.get("plane")
            if not isinstance(coefficients, list) or len(coefficients) != 4:
                raise ValueError(f"Invalid plane in {location}.")
            coeffs = [cls._numeric(v, f"{location} plane") for v in coefficients]
            if np.linalg.norm(coeffs[:3]) <= 1e-14:
                raise ValueError(f"Degenerate plane in {location}.")
            infinite = entry.get("infinity")
            boundary = entry.get("domain_boundary")
            if type(infinite) is not bool or type(boundary) is not bool:
                raise ValueError(f"Missing/invalid geometry flags in {location}.")
            raw_vertices = entry.get("vertices")
            if raw_vertices is None:
                vertices = None
            else:
                values = cls._point_list(raw_vertices, f"{location} vertices")
                if values and len(values) < 3:
                    raise ValueError(f"Incomplete polygon vertices in {location}.")
                vertices = [Point(*coords) for coords in values]
                # Validate each polygon against its *own* plane. Do not reject
                # existing support polygons merely for extending outside the
                # LAB/RGB reference domain (the geometry engine permits that).
                norm = np.linalg.norm(coeffs[:3])
                for coords in values:
                    residual = abs(float(np.dot(coeffs[:3], coords) + coeffs[3]))
                    if residual > 1e-7 * norm * max(1.0, np.linalg.norm(coords)):
                        raise ValueError(f"Vertex is not coplanar in {location}.")
            faces.append(Face(Plane(*coeffs), vertices, infinite,
                              is_domain_boundary=boundary))
        return Volume(Point(*representative), faces)

    @classmethod
    def _validate_model(cls, model):
        if not isinstance(model, dict):
            raise ValueError("Missing or invalid 'model' block.")
        mode = model.get("color_space")
        if mode not in ("LAB", "RGB"):
            raise ValueError("model.color_space must be LAB or RGB.")
        raw_domain = model.get("reference_domain")
        if not isinstance(raw_domain, list) or len(raw_domain) != 3:
            raise ValueError("model.reference_domain must contain three [min, max] pairs.")
        pairs = []
        for i, row in enumerate(raw_domain):
            if not isinstance(row, list) or len(row) != 2:
                raise ValueError(f"Invalid reference_domain pair #{i + 1}.")
            pairs.append([cls._numeric(c, "reference_domain") for c in row])
        domain = ReferenceDomain.from_bounds([v for pair in pairs for v in pair])

        config = model.get("construction")
        if not isinstance(config, dict) or config.get("method") != "voronoi":
            raise ValueError("model.construction.method must be 'voronoi'.")
        l1 = cls._numeric(config.get("lambda1"), "lambda1")
        l2 = cls._numeric(config.get("lambda2"), "lambda2")
        if not (0 <= l1 < 1 and 1 < l2 <= 2):
            raise ValueError("Require 0 <= lambda1 < 1 and 1 < lambda2 <= 2.")
        disjoint = config.get("disjoint")
        covering = config.get("covering")
        if type(disjoint) is not bool or type(covering) is not bool:
            raise ValueError("disjoint and covering must be JSON booleans.")
        if disjoint and not (1 <= l1 + l2 <= 2 + 1e-10):
            raise ValueError("Disjoint spaces require 1 <= lambda1 + lambda2 <= 2.")
        auxiliary = cls._point_list(config.get("aux_negatives"), "aux_negatives")
        if covering and auxiliary:
            raise ValueError("Covering spaces cannot have auxiliary negatives.")
        if not covering and not auxiliary:
            raise ValueError("Non-covering spaces must specify their auxiliary negatives.")

        categories = model.get("categories")
        if not isinstance(categories, list) or len(categories) < 2:
            raise ValueError("model.categories must contain at least two categories.")
        seen_categories, seen_granules, entries = set(), set(), []
        for cat in categories:
            if not isinstance(cat, dict):
                raise ValueError("Invalid category entry.")
            label = cls._label(cat.get("label"), "Category label")
            if len(label) > 24:
                raise ValueError(f"Category label '{label}' exceeds 24 characters.")
            if label in seen_categories:
                raise ValueError(f"Duplicated category label '{label}'.")
            seen_categories.add(label)
            negatives = cls._point_list(cat.get("negatives"), f"{label} negatives")
            if disjoint and negatives:
                raise ValueError(f"Disjoint category '{label}' must store negatives as [].")
            granules = cat.get("granules")
            if not isinstance(granules, list) or not granules:
                raise ValueError(f"Category '{label}' must contain at least one granule.")
            for granule in granules:
                if not isinstance(granule, dict):
                    raise ValueError(f"Invalid granule in category '{label}'.")
                glabel = cls._label(granule.get("label"), "Granule label")
                if glabel in seen_granules:
                    raise ValueError(f"Duplicated granule label '{glabel}'.")
                seen_granules.add(glabel)
                xyz = cls._triple(granule.get("prototype"), f"Prototype '{glabel}'")
                if not domain.contains_coordinates(xyz, eps=1e-6):
                    raise ValueError(f"Prototype '{glabel}' is outside the reference domain.")
                entries.append((label, glabel, xyz, negatives))
        if len(entries) < 2:
            raise ValueError("At least two positive prototypes are required.")
        points = np.asarray([e[2] for e in entries], dtype=float)
        Voronoi._validate_no_duplicate_points(points, Voronoi.DEFAULT_MERGE_EPS)
        if not disjoint:
            owners = [label for label, _, _, _ in entries]
            for category in categories:
                label = category["label"]
                for q in category["negatives"]:
                    if any(np.linalg.norm(np.asarray(q) - site) < Voronoi.DEFAULT_MERGE_EPS
                           and owner == label
                           for owner, site in zip(owners, points)):
                        raise ValueError(f"Category '{label}' cannot use its own granule as negative.")
        if not disjoint and covering:
            for category in categories:
                for q in category["negatives"]:
                    if not any(np.linalg.norm(np.asarray(q) - site) < Voronoi.DEFAULT_MERGE_EPS
                               for site in points):
                        raise ValueError(
                            "Covering non-disjoint spaces require negatives "
                            "drawn from real positive prototypes."
                        )
        return mode, domain, config, auxiliary, entries

    @classmethod
    def serialize_space(cls, space):
        """Convert an already-built atomic/granular FCS to the agreed JSON v1.

        All category/granule geometry is serialized without rebuilding Voronoi.
        """
        if isinstance(space, GranularFuzzyColorSpace):
            return cls._serialize_granular_space(space)
        if len(space.prototypes) != len(space.cores) or len(space.prototypes) != len(space.supports):
            raise ValueError("Inconsistent number of prototype/core/support volumes.")
        auxiliary = cls._canonical_points(getattr(space, "auxiliary_negatives", []))
        aux_set = {tuple(p) for p in auxiliary}
        categories = []
        geometries = {}
        for proto, core, support in zip(space.prototypes, space.cores, space.supports):
            label = cls._label(proto.label, "Color label")
            if label in geometries:
                raise ValueError(f"Duplicated color label '{label}'.")
            if space.disjoint:
                negatives = []
            else:
                negatives = [
                    cls._triple(p, f"Negatives for '{label}'")
                    for p in space.negative_prototypes.get(label, [])
                    if tuple(float(v) for v in p) not in aux_set
                ]
            categories.append({
                "label": label,
                "negatives": negatives,
                "granules": [{"label": label, "prototype": cls._triple(proto.positive, label)}],
            })
            geometries[label] = {
                "core": cls._volume_to_data(core),
                "voronoi": cls._volume_to_data(proto),
                "support": cls._volume_to_data(support),
            }
        bounds = space.reference_domain.bounds
        model = {
            "color_space": space.color_space,
            "reference_domain": [[bounds[i], bounds[i + 1]] for i in (0, 2, 4)],
            "construction": {
                "method": "voronoi",
                "lambda1": float(space.lambda1),
                "lambda2": float(space.lambda2),
                "disjoint": bool(space.disjoint),
                "covering": bool(space.covering),
                "aux_negatives": auxiliary,
            },
            "categories": categories,
        }
        return {
            "format_version": cls.FORMAT_VERSION,
            "metadata": {
                "name": space.space_name,
                "geometry_input_sha256": cls.geometry_input_sha256(model),
            },
            "model": model,
            "geometry": {"granules": geometries},
        }

    @classmethod
    def _serialize_granular_space(cls, space):
        auxiliary = cls._canonical_points(getattr(space, "auxiliary_negatives", []))
        aux_set = {tuple(p) for p in auxiliary}
        geometries = {}
        categories = []
        for category in space.categories:
            label = cls._label(category.label, "Category label")
            negatives = [] if space.disjoint else [
                cls._triple(p, f"Negatives for '{label}'")
                for p in space.negative_prototypes.get(label, [])
                if tuple(float(v) for v in p) not in aux_set
            ]
            granules = []
            for proto, core, support in zip(category.prototypes,
                                            category.cores, category.supports):
                glabel = cls._label(proto.label, "Granule label")
                if glabel in geometries:
                    raise ValueError(f"Duplicate granule label '{glabel}'.")
                granules.append({
                    "label": glabel,
                    "prototype": cls._triple(proto.positive, glabel),
                })
                geometries[glabel] = {
                    "core": cls._volume_to_data(core),
                    "voronoi": cls._volume_to_data(proto),
                    "support": cls._volume_to_data(support),
                }
            categories.append({"label": label, "negatives": negatives,
                               "granules": granules})
        bounds = space.reference_domain.bounds
        model = {
            "color_space": space.color_space,
            "reference_domain": [[bounds[i], bounds[i + 1]] for i in (0, 2, 4)],
            "construction": {
                "method": "voronoi", "lambda1": float(space.lambda1),
                "lambda2": float(space.lambda2), "disjoint": bool(space.disjoint),
                "covering": bool(space.covering), "aux_negatives": auxiliary,
            },
            "categories": categories,
        }
        cls._validate_model(model)
        return {
            "format_version": cls.FORMAT_VERSION,
            "metadata": {
                "name": space.space_name,
                "geometry_input_sha256": cls.geometry_input_sha256(model),
            },
            "model": model,
            "geometry": {"granules": geometries},
        }

    @staticmethod
    def _write_document_atomic(name, document, progress_callback=None):
        encoded = (json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2)
                   + "\n").encode("utf-8")
        folder = os.path.join(get_base_path(), "fuzzy_color_spaces")
        os.makedirs(folder, exist_ok=True)
        destination = os.path.join(folder, name + ".json")
        tmp = None
        try:
            fd, tmp = tempfile.mkstemp(dir=folder, prefix="." + name + "_", suffix=".json.tmp")
            with os.fdopen(fd, "wb") as target:
                total = len(encoded)
                for start in range(0, total, 65536):
                    segment = encoded[start:start + 65536]
                    target.write(segment)
                    if progress_callback:
                        progress_callback(min(start + len(segment), total), total)
                target.flush()
                os.fsync(target.fileno())
            os.replace(tmp, destination)
        finally:
            if tmp is not None and os.path.isfile(tmp):
                os.unlink(tmp)
        return destination

    def save_space(self, space, name=None, progress_callback=None,
                   return_fuzzy_space=False):
        """Persist an already-built atomic or granular space without rebuilding.

        Ideal when no geometric inputs have changed. Metadata and saved
        geometry are validated and regenerated from the same in-memory object.
        """
        filename = validate_color_space_name(name or space.space_name)
        document = self.serialize_space(space)
        document["metadata"]["name"] = filename
        destination = self._write_document_atomic(filename, document, progress_callback)
        return (destination, space) if return_fuzzy_space else destination

    def write_granular_file(self, name, categories, progress_callback=None,
                            return_fuzzy_space=False, *, color_space="LAB",
                            reference_domain=None, lambda1=0.5, lambda2=1.5,
                            disjoint=True, covering=True, samples=27,
                            negative_prototypes=None, auxiliary_negatives=None,
                            tconorm="bounded_sum"):
        """Build and save all granules. Input coordinates are NATIVE model values.

        categories = {category_label: {granule_label: [x,y,z], ...}, ...}
        This API also supports exact auxiliary site preservation on edits.
        """
        name = validate_color_space_name(name)
        space = FuzzyColorSpaceBuilder.build_granular(
            name, categories, color_space=color_space,
            reference_domain=reference_domain, lambda1=lambda1, lambda2=lambda2,
            disjoint=disjoint, covering=covering, samples=samples,
            negative_prototypes=negative_prototypes,
            auxiliary_negatives=auxiliary_negatives, tconorm=tconorm,
        )
        return self.save_space(space, name=name, progress_callback=progress_callback,
                               return_fuzzy_space=return_fuzzy_space)

    def write_file(self, name, selected_colors_lab, progress_callback=None,
                   return_fuzzy_space=False, *, color_space="LAB",
                   reference_domain=None, lambda1=0.5, lambda2=1.5,
                   disjoint=True, covering=True, samples=27,
                   negative_prototypes=None, description=None, tconorm=None,
                   model_points=None):
        """Build a space using the current engine, save native JSON atomically.

        Retains the existing InputFCS GUI call signature. The *runtime*
        tconorm argument is accepted for compatibility but never serialized.
        """
        name = validate_color_space_name(name)
        if not hasattr(selected_colors_lab, "items"):
            raise ValueError("Color prototypes must be a name-to-LAB mapping.")
        selected = list(selected_colors_lab.items())
        if len(selected) < 2:
            raise ValueError("At least two colors are required.")
        if len({str(key) for key, _ in selected}) != len(selected):
            raise ValueError("Duplicate color labels are not allowed.")
        for key, _ in selected:
            self._label(key, "Color label")
            if len(key) > 24:
                raise ValueError(f"Color label '{key}' exceeds 24 characters.")
        color_space = str(color_space).upper()
        if color_space not in ("LAB", "RGB"):
            raise ValueError("color_space must be LAB or RGB.")
        domain = reference_domain or ReferenceDomain.for_color_space(color_space)
        labs = {label: self._triple(value, f"LAB prototype '{label}'")
                for label, value in selected}

        def to_model(point):
            coords = np.asarray(self._triple(point, "LAB negative"), dtype=float)
            return coords if color_space == "LAB" else lab_to_rgb_model_checked(coords.reshape(1, 3))[0]

        native = dict(model_points or {})
        if set(native) - set(labs):
            raise ValueError("Native model_points has unknown color labels.")
        points = {
            label: (np.asarray(self._triple(native[label], f"Native prototype '{label}'"), dtype=float)
                    if label in native else to_model(lab))
            for label, lab in labs.items()
        }
        negmap = {}
        for label, values in (negative_prototypes or {}).items():
            if label not in labs:
                raise ValueError(f"Unknown category in negative prototypes: '{label}'.")
            converted = []
            for value in values:
                if isinstance(value, str):
                    if value not in points:
                        raise ValueError(f"Unknown negative category '{value}'.")
                    converted.append(points[value].copy())
                else:
                    converted.append(to_model(value))
            negmap[label] = converted

        space = FuzzyColorSpaceBuilder.build(
            name, points, color_space=color_space, reference_domain=domain,
            lambda1=float(lambda1), lambda2=float(lambda2),
            disjoint=disjoint, covering=covering,
            samples=int(samples), negative_prototypes=negmap,
            description=description,
        )
        # Runtime-only option. Keeping it out of JSON is intentional.
        if tconorm is not None:
            space.tconorm = tconorm
        return self.save_space(space, name=name, progress_callback=progress_callback,
                               return_fuzzy_space=return_fuzzy_space)

    @staticmethod
    def _distinct_object_pairs(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError(f"Duplicated JSON key '{key}'.")
            obj[key] = value
        return obj

    def read_file(self, file_path):
        """Load atomic or granular JSON v1 without recomputing Voronoi."""
        try:
            with open(file_path, "r", encoding="utf-8") as handle:
                doc = json.load(
                    handle, object_pairs_hook=self._distinct_object_pairs,
                    parse_constant=lambda token: (_ for _ in ()).throw(
                        ValueError(f"Invalid non-finite JSON number: {token}")),
                )
            if not isinstance(doc, dict) or type(doc.get("format_version")) is not int:
                raise ValueError("Missing/invalid JSON format_version.")
            if doc["format_version"] != self.FORMAT_VERSION:
                raise ValueError(
                    f"Unsupported PyFCS JSON format version {doc['format_version']}. "
                    f"Supported: {self.FORMAT_VERSION}."
                )
            meta = doc.get("metadata")
            if not isinstance(meta, dict):
                raise ValueError("Missing/invalid 'metadata' block.")
            name = self._label(meta.get("name"), "metadata.name")
            recorded_hash = meta.get("geometry_input_sha256")
            if not isinstance(recorded_hash, str) or len(recorded_hash) != 64:
                raise ValueError("Missing/invalid metadata.geometry_input_sha256.")
            mode, domain, config, auxiliary, entries = self._validate_model(doc.get("model"))
            expected_hash = self.geometry_input_sha256(doc["model"])
            if recorded_hash.lower() != expected_hash:
                raise ValueError(
                    "The JSON geometry input hash does not match the model. "
                    "Its prototypes/configuration may have been edited without "
                    "rebuilding the saved geometry."
                )
            geometry = doc.get("geometry")
            if not isinstance(geometry, dict) or not isinstance(geometry.get("granules"), dict):
                raise ValueError("Missing/invalid geometry.granules block.")
            blocks = geometry["granules"]
            expected_keys = {glabel for _, glabel, _, _ in entries}
            if set(blocks) != expected_keys:
                raise ValueError(
                    "Geometry keys must match exactly the granule labels in model.categories."
                )
            is_granular = any(
                len(category["granules"]) > 1 or
                category["granules"][0]["label"] != category["label"]
                for category in doc["model"]["categories"]
            )
            colors, category_parts, all_sites = {}, {}, []
            for label, glabel, xyz, _negatives in entries:
                item = blocks[glabel]
                if not isinstance(item, dict):
                    raise ValueError(f"Invalid geometry for granule '{glabel}'.")
                sections = []
                for kind in ("core", "voronoi", "support"):
                    volume = self._volume_from_data(item.get(kind), glabel, xyz, kind)
                    sections.append(Prototype(glabel, xyz, voronoi_volume=volume))
                category_parts.setdefault(label, []).append(sections)
                all_sites.append((label, xyz))
            for label, records in category_parts.items():
                first_xyz = records[0][1].positive
                lab = (np.asarray(first_xyz, dtype=float)
                       if mode == "LAB" else skcolor.rgb2lab(
                           (np.clip(first_xyz, 0, 255) / 255.0).reshape(1, 1, 3))[0, 0])
                colors[label] = {
                    "Color": [float(x) for x in lab],
                    "positive_prototype": np.asarray(lab, dtype=float),
                    "fcs_original_label": label,
                }
                if is_granular:
                    colors[label]["granules"] = [
                        {"label": item[1].label, "prototype": np.asarray(
                            item[1].positive if mode == "LAB" else skcolor.rgb2lab(
                                (np.clip(item[1].positive, 0, 255) / 255.0).reshape(1, 1, 3)
                            )[0, 0], dtype=float)}
                        for item in records
                    ]
            negmap = {}
            for category in doc["model"]["categories"]:
                label = category["label"]
                if config["disjoint"]:
                    own = [tuple(point) for owner, point in all_sites if owner != label]
                else:
                    own = [tuple(p) for p in category["negatives"]]
                own.extend(tuple(p) for p in auxiliary)
                negmap[label] = own
            base_kw = dict(
                color_space=mode, reference_domain=domain,
                lambda1=config["lambda1"], lambda2=config["lambda2"],
                disjoint=config["disjoint"], covering=config["covering"],
                # The sampling count is not stored; the sites themselves are.
                samples=(27 if not config["covering"] else 0),
                negative_prototypes=negmap, auxiliary_negatives=auxiliary,
            )
            if is_granular:
                groups = [GranularFuzzyColor(
                    label,
                    [part[1] for part in records],
                    [part[0] for part in records],
                    [part[2] for part in records],
                ) for label, records in category_parts.items()]
                space = GranularFuzzyColorSpace(name, groups, **base_kw)
            else:
                # Keep existing atomic partition membership and UI unchanged.
                cores = [records[0][0] for records in category_parts.values()]
                protos = [records[0][1] for records in category_parts.values()]
                supports = [records[0][2] for records in category_parts.values()]
                for proto, core, support, label in zip(
                        protos, cores, supports, category_parts):
                    proto.label = core.label = support.label = label
                space = FuzzyColorSpace(name, protos, cores, supports, **base_kw)
            space.source_file_format = "PYFCS_JSON_V1"
            return colors, space
        except (OSError, UnicodeError, ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError(f"Error reading .json color space: {exc}") from exc

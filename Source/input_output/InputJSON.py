"""PyFCS official JSON format_version 1.

Categories are listed first, including semantic aggregates.
Atomic granule prototypes live in their base categories;
Core/Voronoi/Support volumes are stored once in the final geometry mapping.
The previous embedded-geometry layouts remain readable. The file stores traceability metadata but
never uses an atomic/granular type flag to decide its mathematics.

For interchange, this reader also understands the two earlier model/geometry
layouts: a Python construction model with an integrity hash and a Java
reference export with global geometry names. They are detected by shape,
not by a different version number. Java reference files may have ambiguous
category/geometry mappings and are explicitly flagged on import.

MAX / BOUNDED_SUM are runtime options. The JSON reader never regenerates
Voronoi during loading; rebuilding from metadata is permitted only when the
original construction can be determined without guessing.
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
from Source.fuzzy.ColorHierarchy import ColorHierarchy
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
    LEGACY_FORMAT_VERSION = 1

    @staticmethod
    def _triple(value, what):
        try:
            data = np.asarray(value, dtype=float).reshape(-1)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{what} must contain three numeric coordinates.") from exc
        if (data.shape != (3,) or not np.all(np.isfinite(data))
                or (isinstance(value, (list, tuple)) and any(isinstance(v, bool) for v in value))):
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
            with np.errstate(over="ignore", invalid="ignore"):
                norm = np.linalg.norm(coeffs[:3])
            if not np.isfinite(norm) or norm <= 1e-14:
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
                if values and len(values) < 3 and not infinite:
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
    def serialize_space_v1(cls, space):
        """Convert an already-built FCS to historical construction JSON.

        All category/granule geometry is serialized without rebuilding Voronoi.
        """
        if isinstance(space, GranularFuzzyColorSpace):
            if space.hierarchy:
                raise ValueError("The historical construction format cannot store a hierarchy.")
            return cls._serialize_granular_space_v1(space)
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
            "format_version": cls.LEGACY_FORMAT_VERSION,
            "metadata": {
                "name": space.space_name,
                "geometry_input_sha256": cls.geometry_input_sha256(model),
            },
            "model": model,
            "geometry": {"granules": geometries},
        }

    @classmethod
    def _serialize_granular_space_v1(cls, space):
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
            "format_version": cls.LEGACY_FORMAT_VERSION,
            "metadata": {
                "name": space.space_name,
                "geometry_input_sha256": cls.geometry_input_sha256(model),
            },
            "model": model,
            "geometry": {"granules": geometries},
        }

    @classmethod
    def geometry_sha256(cls, document):
        """SHA-256 of JSON v1 geometry and semantic fields (not file metadata).

        Canonicalization is JSON sorted keys, compact separators, UTF-8,
        finite JSON numbers and Python's float formatting. External Java
        exporters MAY omit the hash instead of reproducing that convention.
        If present, it is verified on import for accidental-edit detection.
        """
        fields = ("color_space", "reference_domain", "categories")
        content = {key: document[key] for key in fields}
        if "geometry" in document:
            content["geometry"] = document["geometry"]
        if "hierarchy" in document:
            content["hierarchy"] = document["hierarchy"]
        # Semantic hash stays compatible with early simple v1 drafts, where
        # these construction flags were placed at the document root.
        for flag in ("disjoint", "covering"):
            content[flag] = cls._construction_flag(document, flag)
        params = document.get("metadata", {}).get("construction", {})
        # Optional exact construction inputs are hashed only when present;
        # old files keep their original hash convention.
        if "negative_prototypes" in params or "auxiliary_negatives" in params:
            content["construction_sites"] = {key: params[key] for key in
                ("negative_prototypes", "auxiliary_negatives") if key in params}
        canonical = json.dumps(content, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False, allow_nan=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def serialize_space(cls, space):
        """Serialize complete geometry to the official simple JSON v1.

        Supports atomic spaces as categories with one same-named granule,
        and granular spaces as categories with one or more named granules.
        Construction settings are descriptive metadata; auxiliary coordinates
        are intentionally not duplicated in the exported geometry file.
        """
        if isinstance(space, GranularFuzzyColorSpace):
            groups = ((cat.label, list(zip(cat.prototypes, cat.cores, cat.supports)))
                      for cat in space.categories)
        else:
            if (len(space.prototypes) != len(space.cores) or
                    len(space.prototypes) != len(space.supports)):
                raise ValueError("Inconsistent prototype/core/support counts.")
            groups = ((proto.label, [(proto, core, support)])
                      for proto, core, support in zip(
                          space.prototypes, space.cores, space.supports))
        categories = []
        geometry = {}
        for category_label, records in groups:
            granules = []
            for proto, core, support in records:
                if proto.label in geometry:
                    raise ValueError(f"Duplicated granule label '{proto.label}'.")
                granules.append({"label": proto.label,
                                 "prototype": cls._triple(proto.positive, proto.label)})
                geometry[proto.label] = {
                    "core": cls._volume_to_data(core),
                    "voronoi": cls._volume_to_data(proto),
                    "support": cls._volume_to_data(support),
                }
            categories.append({"label": category_label, "granules": granules})
        for label, members in getattr(space, "hierarchy", {}).items():
            categories.append({"label": label, "members": members})
        bounds = space.reference_domain.bounds
        document = {
            "format_version": cls.FORMAT_VERSION,
            "metadata": {
                "name": space.space_name,
                "construction": {
                    "lambda1": float(space.lambda1),
                    "lambda2": float(space.lambda2),
                    "disjoint": bool(space.disjoint),
                    "covering": bool(space.covering),
                    "samples": int(getattr(space, "samples", 0)),
                    "num_aux_negatives": int(getattr(
                        space, "num_aux_negatives_recorded",
                        len(getattr(space, "auxiliary_negatives", [])),
                    )),
                },
            },
            "color_space": space.color_space,
            "reference_domain": [[float(bounds[i]), float(bounds[i + 1])]
                                 for i in (0, 2, 4)],
            "categories": categories,
            "geometry": geometry,
        }
        params = document["metadata"]["construction"]
        if getattr(space, "geometry_only_import", False):
            document["metadata"]["geometry_only_import"] = True
        else:
            # Store only the sampling resolution and actual count when the
            # deterministic grid can be regenerated exactly. Historical or
            # externally supplied non-standard grids keep their coordinates.
            auxiliary = [cls._triple(p, "Auxiliary negative") for p in space.auxiliary_negatives]
            if not space.covering:
                from Source.fuzzy.FuzzyColorSpaceBuilder import generate_auxiliary_negatives
                try:
                    positives = [g["prototype"] for c in categories for g in c.get("granules", [])]
                    generated = generate_auxiliary_negatives(positives, space.reference_domain, params["samples"])
                    compact = np.array_equal(np.asarray(auxiliary), generated)
                except ValueError:
                    compact = False
                if not compact:
                    params["auxiliary_negatives"] = auxiliary
            if not space.disjoint:
                for cat in categories:
                    if "granules" in cat:
                        cat["negatives"] = [cls._triple(q, "Negative prototype")
                            for q in space.negative_prototypes.get(cat["label"], [])
                            if not any(np.linalg.norm(np.asarray(q)-a) <= Voronoi.DEFAULT_MERGE_EPS for a in auxiliary)]
        # Names are optional display metadata, not geometric construction inputs.
        from Source.interface.modules.UtilsTools import filter_negative_names
        named = filter_negative_names(getattr(space, 'negative_names', {}),
            {c['label']: c.get('negatives', []) for c in categories})
        if named:
            document['metadata']['negative_names'] = [
                {'prototype': list(p), 'label': label} for p,label in sorted(named.items())]
        if getattr(space, "import_warnings", None):
            document["metadata"]["source_warning"] = str(space.import_warnings)
        # Validate structure before publishing; stored faces are validated on read.
        cls._validate_v2_document(cls._expand_split_document(document), check_hash=False)
        document["metadata"]["geometry_sha256"] = cls.geometry_sha256(document)
        return document

    @staticmethod
    def _construction_flag(document, flag):
        """Read definitive metadata flags or prior flat-v1 draft flags.

        Never silently prefer one if a file gives conflicting instructions.
        """
        meta = document.get("metadata", {})
        settings = meta.get("construction", {}) if isinstance(meta, dict) else {}
        setting = settings.get(flag) if isinstance(settings, dict) else None
        legacy = document.get(flag)
        if setting is None and legacy is None:
            raise ValueError(f"Missing metadata.construction.{flag}.")
        if setting is not None and type(setting) is not bool:
            raise ValueError(f"metadata.construction.{flag} must be a JSON boolean.")
        if legacy is not None and type(legacy) is not bool:
            raise ValueError(f"{flag} must be a JSON boolean.")
        if setting is not None and legacy is not None and setting != legacy:
            raise ValueError(f"Conflicting {flag} values in JSON.")
        return setting if setting is not None else legacy

    @classmethod
    def _validate_v2_document(cls, doc, *, check_hash=True):
        if not isinstance(doc, dict):
            raise ValueError("JSON must be an object.")
        metadata = doc.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError("Missing/invalid metadata object.")
        name = cls._label(metadata.get("name"), "metadata.name")
        params = metadata.get("construction", {})
        if not isinstance(params, dict):
            raise ValueError("metadata.construction must be an object.")
        if "lambda1" in params and not (0 <= cls._numeric(params["lambda1"], "lambda1") < 1):
            raise ValueError("Require 0 <= lambda1 < 1.")
        if "lambda2" in params and not (1 < cls._numeric(params["lambda2"], "lambda2") <= 2):
            raise ValueError("Require 1 < lambda2 <= 2.")
        for key in ("samples", "num_aux_negatives"):
            if key in params and (type(params[key]) is not int or params[key] < 0):
                raise ValueError(f"metadata.construction.{key} must be a nonnegative integer.")
        if doc.get("color_space") not in ("LAB", "RGB"):
            raise ValueError("color_space must be LAB or RGB.")
        bounds = doc.get("reference_domain")
        if not isinstance(bounds, list) or len(bounds) != 3:
            raise ValueError("reference_domain must contain three [min, max] pairs.")
        pairs = []
        for i, pair in enumerate(bounds):
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError(f"Invalid reference_domain pair {i + 1}.")
            pairs.extend(cls._numeric(number, "reference_domain") for number in pair)
        domain = ReferenceDomain.from_bounds(pairs)
        for flag in ("disjoint", "covering"):
            cls._construction_flag(doc, flag)
        categories = doc.get("categories")
        if not isinstance(categories, list) or len(categories) < 2:
            raise ValueError("categories must contain at least two categories.")
        seen_cat, seen_site, entries = set(), set(), []
        for category in categories:
            if not isinstance(category, dict):
                raise ValueError("Invalid category object.")
            label = cls._label(category.get("label"), "Category label")
            if len(label) > 24 or label in seen_cat:
                raise ValueError(f"Duplicated or overlong category label '{label}'.")
            seen_cat.add(label)
            sites = category.get("granules")
            if not isinstance(sites, list) or not sites:
                raise ValueError(f"Category '{label}' needs at least one granule.")
            for granule in sites:
                if not isinstance(granule, dict):
                    raise ValueError(f"Invalid granule in category '{label}'.")
                glabel = cls._label(granule.get("label"), "Granule label")
                if glabel in seen_site:
                    raise ValueError(f"Duplicated granule label '{glabel}'.")
                seen_site.add(glabel)
                xyz = cls._triple(granule.get("prototype"), f"Prototype '{glabel}'")
                if not domain.contains_coordinates(xyz, eps=1e-6):
                    raise ValueError(f"Prototype '{glabel}' is outside the reference domain.")
                entries.append((label, glabel, xyz, granule))
        Voronoi._validate_no_duplicate_points(
            np.asarray([record[2] for record in entries], dtype=float),
            Voronoi.DEFAULT_MERGE_EPS,
        )
        if "geometry_only_import" in metadata and type(metadata["geometry_only_import"]) is not bool:
            raise ValueError("geometry_only_import must be boolean.")
        if "auxiliary_negatives" in params:
            aux = cls._point_list(params["auxiliary_negatives"], "Auxiliary negatives")
            if len(aux) != params.get("num_aux_negatives", len(aux)):
                raise ValueError("Auxiliary negative count does not match construction metadata.")
            if cls._construction_flag(doc, "covering") and aux:
                raise ValueError("Covering spaces cannot have auxiliary negatives.")
            if not cls._construction_flag(doc, "covering") and not aux:
                raise ValueError("Non-covering spaces need auxiliary negatives.")
        if "negative_prototypes" in params:
            neg = params["negative_prototypes"]
            if not isinstance(neg, dict) or set(neg) != seen_cat:
                raise ValueError("Negative prototypes must be specified for each base category.")
            for label, vals in neg.items():
                points = cls._point_list(vals, f"Negatives for '{label}'")
                if cls._construction_flag(doc, "disjoint") and points:
                    raise ValueError("Disjoint construction does not need explicit negatives.")
                for point in points:
                    if any(cat == label and np.linalg.norm(np.asarray(point)-xyz) <= Voronoi.DEFAULT_MERGE_EPS
                           for cat, _, xyz, _ in entries):
                        raise ValueError(f"Category '{label}' uses its own positive as a negative.")
        if "hierarchy" in doc:
            # Validate references before constructing any geometry, including cycles.
            from types import SimpleNamespace
            base = [SimpleNamespace(label=c["label"], prototypes=[
                SimpleNamespace(label=g["label"]) for g in c["granules"]])
                for c in categories]
            if not isinstance(doc["hierarchy"], dict):
                raise ValueError("hierarchy must be a JSON object.")
            ColorHierarchy(base, doc["hierarchy"])
        if check_hash and "geometry_sha256" in metadata:
            recorded = metadata["geometry_sha256"]
            if (not isinstance(recorded, str) or len(recorded) != 64 or
                    any(ch not in "0123456789abcdefABCDEF" for ch in recorded)):
                raise ValueError("Invalid metadata.geometry_sha256.")
            if recorded.lower() != cls.geometry_sha256(doc):
                raise ValueError("geometry_sha256 does not match the saved geometry.")
        return name, doc["color_space"], domain, entries

    @classmethod
    def _expand_split_document(cls, doc):
        """Validate the reference layout and adapt to the existing geometry loader.

        No geometry is recalculated. The split hash is checked before adapting;
        embedded-layout hashes are still checked by the original validator.
        """
        from types import SimpleNamespace
        categories, geometry = doc.get("categories"), doc.get("geometry")
        if not isinstance(categories, list) or not isinstance(geometry, dict):
            raise ValueError("Expected a categories list and geometry mapping.")
        if "hierarchy" in doc:
            raise ValueError("Split JSON must declare aggregate members in categories only.")
        meta = doc.get("metadata")
        if not isinstance(meta, dict):
            raise ValueError("Missing/invalid metadata object.")
        if "geometry_sha256" in meta:
            recorded = meta["geometry_sha256"]
            if not isinstance(recorded, str) or recorded.lower() != cls.geometry_sha256(doc):
                raise ValueError("geometry_sha256 does not match the saved geometry.")
        base, nodes, points, first_ids, names, representatives = [], {}, {}, {}, set(), {}
        category_negatives = {}
        for cat in categories:
            if not isinstance(cat, dict):
                raise ValueError("Invalid category object.")
            label = cls._label(cat.get("label"), "Category label")
            if label in names or len(label) > 24:
                raise ValueError(f"Duplicated or overlong category label '{label}'.")
            names.add(label)
            # Legacy split files may carry a redundant representative.
            if "representative" in cat:
                representatives[label] = cls._triple(cat["representative"], f"Representative '{label}'")
            if ("members" in cat) == ("granules" in cat):
                raise ValueError(f"Category '{label}' must define either granules or members.")
            if "members" in cat:
                if "negatives" in cat:
                    raise ValueError("Aggregate categories cannot define geometric negatives.")
                nodes[label] = cat["members"]
                continue
            granules = cat["granules"]
            if not isinstance(granules, list) or not granules:
                raise ValueError(f"Category '{label}' needs at least one granule.")
            embedded = []
            for g in granules:
                if not isinstance(g, dict) or set(g) != {"label", "prototype"}:
                    raise ValueError(f"Invalid granule entry in '{label}'.")
                key = cls._label(g.get("label"), "Granule label")
                if key in points:
                    raise ValueError(f"Duplicated granule label '{key}'.")
                geom = geometry.get(key)
                if not isinstance(geom, dict) or set(geom) != {"core", "voronoi", "support"}:
                    raise ValueError(f"Missing/invalid geometry for granule '{key}'.")
                points[key] = cls._triple(g.get("prototype"), f"Prototype '{key}'")
                embedded.append({**g, **geom})
            first_ids[label] = embedded[0]["label"]
            # Legacy display_rgb is descriptive and never used by the loader.
            base.append({"label": label, "granules": embedded})
            if "negatives" in cat:
                category_negatives[label] = cat["negatives"]
        if set(geometry) != set(points):
            raise ValueError("Geometry contains unreferenced granule IDs.")
        graph = ColorHierarchy([SimpleNamespace(label=c["label"], prototypes=[
            SimpleNamespace(label=g["label"]) for g in c["granules"]]) for c in base], nodes)
        # Validate optional legacy representatives against the deterministic first leaf.
        # It is descriptive, not an additional positive site.
        for label, rep in representatives.items():
            target = label
            while target in nodes:
                kind, child = next(iter(nodes[target][0].items()))
                if kind == "granule":
                    target = child
                    break
                target = child
            else:
                target = first_ids[target]
            if not np.array_equal(rep, points[target]):
                raise ValueError(f"Representative '{label}' must equal its first granule prototype.")
        expanded = {k: v for k, v in doc.items() if k not in ("categories", "geometry")}
        expanded["metadata"] = {k: v for k, v in meta.items() if k != "geometry_sha256"}
        if category_negatives:
            params = dict(meta.get("construction", {}))
            if "negative_prototypes" in params:
                raise ValueError("Negatives cannot be defined in both categories and construction metadata.")
            params["negative_prototypes"] = category_negatives
            expanded["metadata"]["construction"] = params
        expanded["categories"] = base
        if graph:
            expanded["hierarchy"] = graph.to_dict()
        return expanded

    @classmethod
    def _read_v2_document(cls, doc):
        if "geometry" in doc:
            doc = cls._expand_split_document(doc)
        name, mode, domain, entries = cls._validate_v2_document(doc)
        groups = {}
        for cat_label, glabel, xyz, data in entries:
            pieces = []
            for section in ("core", "voronoi", "support"):
                geom = cls._volume_from_data(data.get(section), glabel, xyz, section)
                pieces.append(Prototype(glabel, xyz, voronoi_volume=geom))
            groups.setdefault(cat_label, []).append(pieces)
        inferred_granular = any(
            len(cat["granules"]) > 1 or
            cat["granules"][0]["label"] != cat["label"]
            for cat in doc["categories"]
        )
        # The exchange schema has no distinct space type: a category simply
        # contains one or more granules. Keep the legacy internal class
        # selection for GUI compatibility, based solely on the structure.
        is_granular = inferred_granular or bool(doc.get("hierarchy"))
        colors = {}
        for label, records in groups.items():
            first = records[0][1].positive
            lab = (np.asarray(first, dtype=float) if mode == "LAB" else
                   skcolor.rgb2lab((np.clip(first, 0, 255) / 255.0).reshape(1, 1, 3))[0, 0])
            colors[label] = {
                "Color": [float(n) for n in lab],
                "positive_prototype": np.asarray(lab, dtype=float),
                "fcs_original_label": label,
            }
            if mode == "RGB":
                colors[label]["native_rgb"] = np.asarray(first, dtype=float).copy()
            if is_granular:
                colors[label]["granules"] = [
                    {
                        "label": item[1].label,
                        "prototype": np.asarray(
                            item[1].positive if mode == "LAB" else
                            skcolor.rgb2lab((np.clip(item[1].positive, 0, 255) / 255.0)
                                            .reshape(1, 1, 3))[0, 0], dtype=float),
                        **({"native_rgb": np.asarray(item[1].positive, dtype=float).copy()}
                           if mode == "RGB" else {}),
                    }
                    for item in records
                ]
        # These fields are NOT construction metadata. Do not pretend imported
        # geometry can be rebuilt identically without its original negatives.
        params = doc["metadata"].get("construction", {})
        base = dict(color_space=mode, reference_domain=domain,
                    disjoint=cls._construction_flag(doc, "disjoint"),
                    covering=cls._construction_flag(doc, "covering"),
                    lambda1=float(params.get("lambda1", 0.5)),
                    lambda2=float(params.get("lambda2", 1.5)),
                    samples=int(params.get("samples", 0)),
                    negative_prototypes={}, auxiliary_negatives=[])
        # Exact native construction inputs are optional for historical files.
        aux = params.get("auxiliary_negatives")
        if aux is None and not base["covering"] and params.get("samples", 0) >= 2:
            from Source.fuzzy.FuzzyColorSpaceBuilder import generate_auxiliary_negatives
            try:
                generated = generate_auxiliary_negatives([row[2] for row in entries], domain, params["samples"])
                if len(generated) == params.get("num_aux_negatives"):
                    aux = generated.tolist()
            except ValueError:
                pass
        if aux is None and base["covering"]:
            aux = []
        if aux is not None:
            base["auxiliary_negatives"] = aux
        if base["disjoint"]:
            base["negative_prototypes"] = {label: [row[2] for row in entries if row[0] != label] + list(aux or [])
                                          for label in groups}
        elif "negative_prototypes" in params:
            base["negative_prototypes"] = {label: list(vals) + list(aux or [])
                                          for label, vals in params["negative_prototypes"].items()}
        if is_granular:
            categories = [GranularFuzzyColor(
                label,
                [item[1] for item in records],
                [item[0] for item in records],
                [item[2] for item in records],
            ) for label, records in groups.items()]
            space = GranularFuzzyColorSpace(name, categories, hierarchy=doc.get("hierarchy"), **base)
        else:
            cores = [records[0][0] for records in groups.values()]
            protos = [records[0][1] for records in groups.values()]
            supports = [records[0][2] for records in groups.values()]
            space = FuzzyColorSpace(name, protos, cores, supports, **base)
        from Source.interface.modules.UtilsTools import filter_negative_names
        records = doc['metadata'].get('negative_names', [])
        if not isinstance(records, list): raise ValueError('Invalid negative_names metadata.')
        names = {}
        for record in records:
            if not isinstance(record, dict) or set(record) != {'prototype','label'}:
                raise ValueError('Invalid negative name entry.')
            key = tuple(cls._triple(record['prototype'], 'Named negative'))
            if key in names: raise ValueError('Duplicate named negative coordinates.')
            names[key] = cls._label(record['label'], 'Negative label')
        space.negative_names = filter_negative_names(names, params.get('negative_prototypes', {}))
        space.source_file_format = "PYFCS_JSON_V1"
        space.num_aux_negatives_recorded = int(params.get("num_aux_negatives", 0))
        # A disjoint PyFCS construction can be rebuilt from its complete
        # positives and recorded sampling configuration. An imported space
        # without these values, or a non-disjoint space with unspecified
        # negative choices, remains evaluation-only (never guessed).
        required = {"lambda1", "lambda2", "samples", "num_aux_negatives"}
        can_rebuild = (required.issubset(params) and aux is not None and
                       (base["covering"] or len(aux) > 0) and
                       (base["disjoint"] or "negative_prototypes" in params) and
                       not doc["metadata"].get("source_warning") and
                       not doc["metadata"].get("geometry_only_import", False))
        space.geometry_only_import = not can_rebuild
        if doc["metadata"].get("source_warning"):
            space.import_warnings = str(doc["metadata"]["source_warning"])
        return colors, space

    @staticmethod
    def format_document(document):
        """Pretty JSON with compact numeric vectors, without rounding or changing values."""
        def render(value, depth=0):
            indent = "  " * depth
            child = "  " * (depth + 1)
            if isinstance(value, dict) and value:
                return "{\n" + ",\n".join(
                    child + json.dumps(k, ensure_ascii=False) + ": " + render(v, depth+1)
                    for k, v in value.items()) + "\n" + indent + "}"
            if isinstance(value, list) and value:
                if len(value) <= 4 and all(type(v) in (int, float) for v in value):
                    return json.dumps(value, ensure_ascii=False, allow_nan=False)
                return "[\n" + ",\n".join(child + render(v, depth+1) for v in value) + "\n" + indent + "]"
            return json.dumps(value, ensure_ascii=False, allow_nan=False)
        return render(document) + "\n"

    @staticmethod
    def _write_document_atomic(name, document, progress_callback=None):
        encoded = InputJSON.format_document(document).encode("utf-8")
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
        if (getattr(space, "source_file_format", "") == "JAVA_JSON_REFERENCE"
                and getattr(space, "import_warnings", "")
                and "reused across" in space.import_warnings):
            raise ValueError("This Java JSON shares geometry identifiers across categories. "
                             "It can be inspected, but must be corrected by its exporter "
                             "before it can be saved as an unambiguous PyFCS model.")
        document = self.serialize_space(space)
        document["metadata"]["name"] = filename
        destination = self._write_document_atomic(filename, document, progress_callback)
        return (destination, space) if return_fuzzy_space else destination

    def write_granular_file(self, name, categories, progress_callback=None,
                            return_fuzzy_space=False, *, color_space="LAB",
                            reference_domain=None, lambda1=0.5, lambda2=1.5,
                            disjoint=True, covering=True, samples=27,
                            negative_prototypes=None, auxiliary_negatives=None,
                            tconorm="bounded_sum", hierarchy=None, negative_names=None):
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
            auxiliary_negatives=auxiliary_negatives, tconorm=tconorm, hierarchy=hierarchy,
        )
        space.negative_names = dict(negative_names or {})
        return self.save_space(space, name=name, progress_callback=progress_callback,
                               return_fuzzy_space=return_fuzzy_space)

    def write_file(self, name, selected_colors_lab, progress_callback=None,
                   return_fuzzy_space=False, *, color_space="LAB",
                   reference_domain=None, lambda1=0.5, lambda2=1.5,
                   disjoint=True, covering=True, samples=27,
                   negative_prototypes=None, description=None, tconorm=None,
                   model_points=None, negative_names=None):
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
                elif isinstance(value, dict):
                    if set(value) != {"native"}:
                        raise ValueError("Invalid native negative prototype.")
                    converted.append(np.asarray(self._triple(value["native"], "Native negative"), dtype=float))
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
        space.negative_names = dict(negative_names or {})
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
        """Read official v1, historical PyFCS JSON, or Java reference JSON.

        Older formats are recognized by structure, never by changing the
        official version number or reinterpreting a type discriminator.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as handle:
                doc = json.load(
                    handle, object_pairs_hook=self._distinct_object_pairs,
                    parse_constant=lambda token: (_ for _ in ()).throw(
                        ValueError(f"Invalid non-finite JSON number: {token}")),
                )
            if not isinstance(doc, dict) or type(doc.get("format_version")) is not int:
                raise ValueError("Missing/invalid JSON format_version.")
            if doc["format_version"] != 1:
                raise ValueError("Only JSON format_version 1 is supported.")
            if isinstance(doc.get("categories"), list):
                return self._read_v2_document(doc)
            if isinstance(doc.get("model"), dict) and isinstance(doc.get("geometry"), dict):
                if isinstance(doc["model"].get("categories"), dict):
                    return self._read_java_document(doc)
                if isinstance(doc["model"].get("categories"), list):
                    return self._read_v1_document(doc)
            raise ValueError("Unknown JSON structure: expected categories and geometry.")
        except (OSError, UnicodeError, ValueError, TypeError, KeyError,
                IndexError, AttributeError, OverflowError, RecursionError,
                json.JSONDecodeError, np.linalg.LinAlgError) as exc:
            raise ValueError(f"Error reading .json color space: {exc}") from exc

    @classmethod
    def _recover_java_representative(cls, geometry, label, domain):
        """Recover a Java positive from parallel Core/Voronoi/Support planes.

        For each non-domain face, core = (1-lambda1)*prototype +
        lambda1*Voronoi, so the representative's plane offset is
        D_rep=(D_core-lambda1*D_voronoi)/(1-lambda1).
        This is an inference (Java JSON does not export prototypes).
        """
        l1, l2 = .5, 1.5
        raw = [geometry.get(x, {}).get("faces") for x in ("core", "voronoi", "support")]
        if any(not isinstance(faces, list) or not faces for faces in raw):
            raise ValueError(f"Missing Java Core/Voronoi/Support for '{label}'.")
        if not (len(raw[0]) == len(raw[1]) == len(raw[2])):
            raise ValueError(f"Mismatched Java volume face counts in '{label}'.")
        rows, rhs = [], []
        for core, vor, support in zip(*raw):
            if core.get("domain_boundary") or vor.get("domain_boundary"):
                continue
            c = np.asarray(core.get("plane"), dtype=float)
            v = np.asarray(vor.get("plane"), dtype=float)
            sp = np.asarray(support.get("plane"), dtype=float)
            if any(p.shape != (4,) or not np.all(np.isfinite(p)) for p in (c, v, sp)):
                raise ValueError(f"Invalid Java planes for '{label}'.")
            norms = [np.linalg.norm(p[:3]) for p in (c,v,sp)]
            if min(norms) < 1e-12:
                raise ValueError(f"Degenerate Java plane in '{label}'.")
            c, v, sp = (p / norm for p, norm in zip((c, v, sp), norms))
            # The face arrays are order-aligned in the collaborator's export.
            if max(np.linalg.norm(c[:3]-v[:3]), np.linalg.norm(sp[:3]-v[:3])) > 1e-7:
                raise ValueError(f"Unaligned Java geometry faces for '{label}'.")
            if abs((c[3] - v[3])/(l1-1) - (sp[3]-v[3])/(l2-1)) > 1e-5:
                raise ValueError(f"Inconsistent Java scaling for '{label}'.")
            drep = (c[3] - l1 * v[3]) / (1 - l1)
            rows.append(v[:3])
            rhs.append(-drep)
        if len(rows) < 3:
            raise ValueError(f"Not enough independent Java faces for '{label}'.")
        point, _, rank, _ = np.linalg.lstsq(rows, rhs, rcond=None)
        if rank < 3 or np.max(np.abs(np.asarray(rows) @ point - rhs)) > 1e-5:
            raise ValueError(f"Cannot recover a consistent positive for '{label}'.")
        if not domain.contains_coordinates(point, eps=1e-5):
            raise ValueError(f"Recovered positive outside RGB domain for '{label}'.")
        return point.tolist()

    @classmethod
    def _read_java_document(cls, doc):
        """Open Java's model/geometry reference layout, without Voronoi rebuilding.

        Java's sample exports use shared 'Color N' keys across multiple
        categories. The loader preserves those literal references but warns:
        the original unrecoverable category-specific sites cannot be inferred.
        """
        meta, model, geometries = doc.get("metadata", {}), doc["model"], doc["geometry"]
        name = cls._label(meta.get("name"), "metadata.name")
        mode = model.get("color_space")
        if mode not in ("RGB", "LAB"):
            raise ValueError("Java model color_space must be RGB or LAB.")
        bounds = model.get("reference_domain")
        if not isinstance(bounds, list) or len(bounds) != 3:
            raise ValueError("Invalid Java reference_domain.")
        pairs = []
        for row in bounds:
            if not isinstance(row, list) or len(row) != 2:
                raise ValueError("Invalid Java reference_domain pair.")
            pairs.extend(cls._numeric(x, "Java reference_domain") for x in row)
        domain = ReferenceDomain.from_bounds(pairs)
        refs = model.get("categories")
        if not isinstance(refs, dict) or len(refs) < 2 or not isinstance(geometries, dict):
            raise ValueError("Java model categories/geometry must be mappings.")
        recovered = {}
        for identifier, geometry in geometries.items():
            if not isinstance(geometry, dict):
                raise ValueError(f"Invalid Java geometry '{identifier}'.")
            recovered[identifier] = cls._recover_java_representative(
                geometry, identifier, domain)
        used, categories, color_data = {}, [], {}
        for cat_label, identifiers in refs.items():
            cls._label(cat_label, "Java category label")
            if (not isinstance(identifiers, list) or not identifiers
                    or not all(isinstance(item, str) for item in identifiers)
                    or len(set(identifiers)) != len(identifiers)):
                raise ValueError(f"Empty Java category '{cat_label}'.")
            records = [[], [], []]
            data_granules = []
            for idx, identifier in enumerate(identifiers):
                if identifier not in recovered:
                    raise ValueError(f"Java category '{cat_label}' references missing geometry '{identifier}'.")
                used.setdefault(identifier, set()).add(cat_label)
                # Java keys are not unique granule identifiers; create stable
                # internal names without altering the original geometry.
                glabel = f"{cat_label}:{identifier}"
                point = recovered[identifier]
                for k, section in enumerate(("voronoi", "core", "support")):
                    volume = cls._volume_from_data(geometries[identifier][section],
                                                   glabel, point, section)
                    records[k].append(Prototype(glabel, point, voronoi_volume=volume))
                lab = (np.asarray(point, float) if mode == "LAB" else
                       skcolor.rgb2lab((np.clip(point,0,255)/255).reshape(1,1,3))[0,0])
                data_granules.append({
                    "label": glabel, "prototype": np.asarray(lab, float),
                    **({"native_rgb": np.asarray(point, float)} if mode == "RGB" else {}),
                })
            categories.append(GranularFuzzyColor(cat_label, *records))
            first = data_granules[0]
            color_data[cat_label] = {
                "Color": list(map(float, first["prototype"])),
                "positive_prototype": np.asarray(first["prototype"], float),
                "fcs_original_label": cat_label,
                "granules": data_granules,
                **({"native_rgb": np.asarray(recovered[identifiers[0]], float)}
                   if mode == "RGB" else {}),
            }
        sharing = {name: sorted(cat) for name, cat in used.items() if len(cat)>1}
        # The Java export does not state disjoint/covering/auxiliary settings.
        space = GranularFuzzyColorSpace(name, categories,
                    color_space=mode, reference_domain=domain,
                    disjoint=False, covering=False, lambda1=.5, lambda2=1.5,
                    samples=0, negative_prototypes={}, auxiliary_negatives=[])
        space.geometry_only_import = True
        space.source_file_format = "JAVA_JSON_REFERENCE"
        space.num_aux_negatives_recorded = 0
        warning = ("Imported Java reference geometry only. The file omits original "
                   "positive prototypes and construction parameters; positives were "
                   "inferred from Core/Voronoi/Support assuming lambda1=0.5 and "
                   "lambda2=1.5. The original construction cannot be recreated. ")
        if sharing:
            warning += (f"CAUTION: {len(sharing)} geometry identifiers are reused across "
                        "different categories; this export cannot establish the "
                        "correct original category/granule correspondence. The "
                        "resulting memberships may differ from Java evaluation results.")
        space.import_warnings = warning
        return color_data, space

    def _read_v1_document(self, doc):
        """Historical format with construction model and input-based hash."""
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

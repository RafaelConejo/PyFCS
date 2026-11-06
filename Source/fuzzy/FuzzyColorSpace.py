"""Fuzzy color space with explicit construction-domain and topological metadata.

All existing partition / LAB / default lambda callers use the legacy membership
code unchanged. Non-partition spaces expose raw membership degrees (no
normalization / single-positive promotion). A color sample passed by UI code
is CIELAB unless input_space='RGB' or 'MODEL' is explicitly requested.
"""
import numpy as np
from skimage import color as skcolor
from Source.fuzzy.FuzzyColor import FuzzyColor
from Source.colorspace.ReferenceDomain import ReferenceDomain


class FuzzyColorSpace(FuzzyColor):
    def __init__(self, space_name, prototypes, cores=None, supports=None,
                 improve_geometry=True, *, disjoint=True, covering=True,
                 color_space="LAB", reference_domain=None, lambda1=0.5,
                 lambda2=1.5, samples=0, negative_prototypes=None,
                 auxiliary_negatives=None, description=None):
        self.space_name = space_name
        self.prototypes = list(prototypes)
        self.disjoint = bool(disjoint)
        self.covering = bool(covering)
        self.color_space = str(color_space).upper()
        if self.color_space not in ("LAB", "RGB"):
            raise ValueError("color_space must be LAB or RGB.")
        self.reference_domain = reference_domain or ReferenceDomain.for_color_space(self.color_space)
        self.lambda1, self.lambda2 = float(lambda1), float(lambda2)
        self.samples = int(samples)
        self.negative_prototypes = {
            str(label): [tuple(float(x) for x in p) for p in points]
            for label, points in (negative_prototypes or {}).items()
        }
        self.auxiliary_negatives = [tuple(float(x) for x in p)
                                    for p in (auxiliary_negatives if auxiliary_negatives is not None else [])]
        self.description = description or self.typology_description
        if cores is None and supports is None:
            self.cores, self.supports = FuzzyColor.create_core_support(
                self.prototypes, 0.5, lambda1=self.lambda1, lambda2=self.lambda2)
            # JFCS's optional geometry repair applies to disjoint categories.
            # Never repair a stored/imported geometry on read, and never force
            # disjointness on intentionally overlapping categories.
            if improve_geometry and self.disjoint:
                self.geometry_repairs = FuzzyColor.update_geometry(
                    self.prototypes, self.cores, self.supports,
                    reference_domain=self.reference_domain)
        elif cores is not None and supports is not None:
            self.cores, self.supports = list(cores), list(supports)
        else:
            raise ValueError("Both cores and supports must be provided together.")
        self._precomputed = None

    @property
    def is_partition(self):
        return self.disjoint and self.covering

    @property
    def typology_description(self):
        return ("DISJOINT" if self.disjoint else "NON-DISJOINT") + " and " + ("COVERING" if self.covering else "NON-COVERING")

    def model_from_lab(self, lab):
        vals = np.asarray(lab, dtype=float).reshape(3)
        if self.color_space == "LAB":
            return tuple(vals.tolist())
        with np.errstate(invalid="ignore"):
            rgb = skcolor.lab2rgb(vals.reshape(1, 1, 3))[0, 0] * 255.0
        return tuple(np.clip(rgb, 0, 255).tolist())

    def model_from_rgb(self, rgb):
        vals = np.asarray(rgb, dtype=float).reshape(3)
        if self.color_space == "RGB":
            return tuple(vals.tolist())
        lab = skcolor.rgb2lab((np.clip(vals, 0, 255) / 255.0).reshape(1, 1, 3))[0, 0]
        return tuple(lab.tolist())

    def lab_from_model(self, value):
        v = np.asarray(value, dtype=float).reshape(3)
        if self.color_space == "LAB":
            return tuple(v.tolist())
        lab = skcolor.rgb2lab((np.clip(v, 0, 255) / 255.0).reshape(1, 1, 3))[0, 0]
        return tuple(lab.tolist())

    def _coordinates(self, value, input_space="LAB"):
        mode = str(input_space).upper()
        if mode == "MODEL":
            return tuple(np.asarray(value, dtype=float).reshape(3).tolist())
        if mode == "RGB":
            return self.model_from_rgb(value)
        if mode == "LAB":
            return self.model_from_lab(value)
        raise ValueError("input_space must be LAB, RGB or MODEL.")

    def precompute_pack(self):
        self._precomputed = {
            "domain_volume": self.reference_domain.get_volume(),
            "v_protos": [p.voronoi_volume for p in self.prototypes],
            "v_cores": [c.voronoi_volume for c in self.cores],
            "v_supps": [s.voronoi_volume for s in self.supports],
            "rep": [p.voronoi_volume.getRepresentative() for p in self.prototypes],
        }
        return self._precomputed

    def best_prototype_index_from_lab(self, lab_triplet):
        return self.best_prototype_index(lab_triplet, input_space="LAB")

    def best_prototype_index(self, value, input_space="LAB"):
        if self._precomputed is None:
            self.precompute_pack()
        coordinates = self._coordinates(value, input_space)
        if not self.reference_domain.contains_coordinates(coordinates, eps=1e-9):
            return -1
        return FuzzyColor.get_membership_degree_mapping_all(
            coordinates, self.prototypes, self._precomputed)

    def clear_precompute(self):
        self._precomputed = None

    def calculate_raw_memberships(self, value, input_space="LAB", include_zeros=False):
        if self._precomputed is None:
            self.precompute_pack()
        coordinates = self._coordinates(value, input_space)
        if not self.reference_domain.contains_coordinates(coordinates, eps=1e-9):
            return ({proto.label: 0.0 for proto in self.prototypes}
                    if include_zeros else {})
        output = {}
        for i, proto in enumerate(self.prototypes):
            m = FuzzyColor._raw_membership_for_index(coordinates, i, self._precomputed)
            if m > 0 or include_zeros:
                output[proto.label] = float(m)
        return output

    def calculate_membership(self, new_color, input_space="LAB"):
        if self._precomputed is None:
            self.precompute_pack()
        coordinates = self._coordinates(new_color, input_space)
        if not self.reference_domain.contains_coordinates(coordinates, eps=1e-9):
            return {}
        if self.is_partition:
            # Regression-compatibility: preserve historical partition behavior.
            return FuzzyColor.get_membership_degree(coordinates, self.prototypes, self._precomputed)
        return self.calculate_raw_memberships(coordinates, input_space="MODEL")

    def calculate_membership_for_prototype(self, new_color, idx_proto, input_space="LAB"):
        if idx_proto < 0 or idx_proto >= len(self.prototypes):
            raise IndexError("Prototype index is out of range.")
        if self._precomputed is None:
            self.precompute_pack()
        coordinates = self._coordinates(new_color, input_space)
        if not self.reference_domain.contains_coordinates(coordinates, eps=1e-9):
            return 0.0
        return FuzzyColor._raw_membership_for_index(
            coordinates, idx_proto, self._precomputed)

    def get_cores(self):
        return self.cores

    def get_supports(self):
        return self.supports

    def get_prototypes(self):
        return self.prototypes

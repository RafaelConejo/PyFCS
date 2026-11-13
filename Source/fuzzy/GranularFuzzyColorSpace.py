"""Granular FCS with category-level compatibility and per-granule geometry.

The inherited ``prototypes/cores/supports`` lists contain ONE representative
per category, for legacy GUI and image-palette indexing only. They are not
used for granular membership. The complete atomic geometry is available via
``get_all_prototypes`` and ``get_granules``. No artificial category prototype
is used to determine membership or the winning category.
"""
import numpy as np

from Source.fuzzy.FuzzyColor import FuzzyColor
from Source.fuzzy.FuzzyColorSpace import FuzzyColorSpace
from Source.fuzzy.GranularFuzzyColor import GranularFuzzyColor
from Source.geometry.Prototype import Prototype


class GranularFuzzyColorSpace(FuzzyColorSpace):
    is_granular = True

    def __init__(self, space_name, categories, *, tconorm="bounded_sum",
                 disjoint=True, covering=True, color_space="LAB",
                 reference_domain=None, lambda1=0.5, lambda2=1.5,
                 samples=0, negative_prototypes=None, auxiliary_negatives=None,
                 description=None):
        # The grouped category objects preserve the complete input order.
        self.categories = list(categories)
        if len(self.categories) < 2:
            raise ValueError("A granular color space needs at least two categories.")
        labels = [cat.label for cat in self.categories]
        if len(set(labels)) != len(labels):
            raise ValueError("Duplicate category labels are not allowed.")
        granule_labels = [p.label for cat in self.categories for p in cat.prototypes]
        if len(set(granule_labels)) != len(granule_labels):
            raise ValueError("Granule labels must be unique across the entire space.")

        self._flat_prototypes = [p for cat in self.categories for p in cat.prototypes]
        self._flat_cores = [core for cat in self.categories for core in cat.cores]
        self._flat_supports = [support for cat in self.categories for support in cat.supports]
        self._flat_category_indices = [i for i, cat in enumerate(self.categories)
                                       for _ in cat.prototypes]
        self._category_flat_indices = [[] for _ in self.categories]
        for flat_i, category_i in enumerate(self._flat_category_indices):
            self._category_flat_indices[category_i].append(flat_i)
        self._category_index = {label: i for i, label in enumerate(labels)}
        self._granule_index = {p.label: i for i, p in enumerate(self._flat_prototypes)}

        # Keep the pre-existing GUI contract of one Prototype per color label.
        # Each is a view of the first real granule, never a generated average.
        representatives, cores, supports = [], [], []
        for cat in self.categories:
            representatives.append(Prototype(cat.label, cat.prototypes[0].positive,
                                             voronoi_volume=cat.prototypes[0].voronoi_volume))
            cores.append(Prototype(cat.label, cat.cores[0].positive,
                                   voronoi_volume=cat.cores[0].voronoi_volume))
            supports.append(Prototype(cat.label, cat.supports[0].positive,
                                      voronoi_volume=cat.supports[0].voronoi_volume))
        super().__init__(
            space_name, representatives, cores, supports,
            improve_geometry=False, disjoint=disjoint, covering=covering,
            color_space=color_space, reference_domain=reference_domain,
            lambda1=lambda1, lambda2=lambda2, samples=samples,
            negative_prototypes=negative_prototypes,
            auxiliary_negatives=auxiliary_negatives, description=description,
        )
        self.set_tconorm(tconorm)

    def set_tconorm(self, tconorm):
        operator = str(tconorm).lower().replace("-", "_")
        if operator not in GranularFuzzyColor.OPERATORS:
            raise ValueError("tconorm must be 'max' or 'bounded_sum'.")
        self.tconorm = operator
        return self.tconorm

    def get_all_prototypes(self):
        return self._flat_prototypes

    def get_all_cores(self):
        return self._flat_cores

    def get_all_supports(self):
        return self._flat_supports

    def get_granules(self, category_label):
        return self.categories[self._category_index[category_label]]

    def get_color_labels(self):
        return [cat.label for cat in self.categories]

    def precompute_pack(self):
        self._precomputed = {
            "domain_volume": self.reference_domain.get_volume(),
            "v_protos": [p.voronoi_volume for p in self._flat_prototypes],
            "v_cores": [p.voronoi_volume for p in self._flat_cores],
            "v_supps": [p.voronoi_volume for p in self._flat_supports],
            "rep": [p.voronoi_volume.getRepresentative() for p in self._flat_prototypes],
        }
        return self._precomputed

    def _raw_by_category(self, coordinates):
        if self._precomputed is None:
            self.precompute_pack()
        result = []
        for indices in self._category_flat_indices:
            if self.tconorm == "max":
                best = 0.0
                for i in indices:
                    best = max(best, FuzzyColor._raw_membership_for_index(
                        coordinates, i, self._precomputed))
                    if best >= 1.0:
                        break
                result.append(best)
            else:
                total = 0.0
                for i in indices:
                    total += FuzzyColor._raw_membership_for_index(
                        coordinates, i, self._precomputed)
                    if total >= 1.0:
                        break
                result.append(min(total, 1.0))
        return result

    def calculate_raw_memberships(self, value, input_space="LAB", include_zeros=False):
        coords = self._coordinates(value, input_space)
        if not self.reference_domain.contains_coordinates(coords, eps=1e-9):
            return ({cat.label: 0.0 for cat in self.categories} if include_zeros else {})
        values = self._raw_by_category(coords)
        return {cat.label: float(degree) for cat, degree in zip(self.categories, values)
                if degree > 0.0 or include_zeros}

    def calculate_membership(self, new_color, input_space="LAB"):
        # Never Ruspini-normalize a granular category union: bounded sum and
        # max have different meaningful raw degrees even in covering spaces.
        return self.calculate_raw_memberships(new_color, input_space=input_space)

    def calculate_membership_for_prototype(self, new_color, idx_proto, input_space="LAB"):
        """Backward-compatible name: idx_proto is a *CATEGORY* index."""
        if idx_proto < 0 or idx_proto >= len(self.categories):
            raise IndexError("Category index is out of range.")
        coords = self._coordinates(new_color, input_space)
        if not self.reference_domain.contains_coordinates(coords, eps=1e-9):
            return 0.0
        if self._precomputed is None:
            self.precompute_pack()
        values = (FuzzyColor._raw_membership_for_index(coords, i, self._precomputed)
                  for i in self._category_flat_indices[idx_proto])
        return GranularFuzzyColor.aggregate(values, self.tconorm)

    def calculate_granule_memberships(self, value, input_space="LAB", include_zeros=False):
        """Return {category: {granule_label: raw_degree}} for inspection."""
        coords = self._coordinates(value, input_space)
        if not self.reference_domain.contains_coordinates(coords, eps=1e-9):
            return ({c.label: {p.label: 0.0 for p in c.prototypes}
                     for c in self.categories} if include_zeros else {})
        if self._precomputed is None:
            self.precompute_pack()
        output = {}
        for cat in self.categories:
            vals = {}
            for p in cat.prototypes:
                degree = float(FuzzyColor._raw_membership_for_index(
                    coords, self._granule_index[p.label], self._precomputed))
                if degree > 0.0 or include_zeros:
                    vals[p.label] = degree
            if vals or include_zeros:
                output[cat.label] = vals
        return output

    def best_prototype_index(self, value, input_space="LAB"):
        """Return winning CATEGORY index, never a flattened granule index."""
        coords = self._coordinates(value, input_space)
        if not self.reference_domain.contains_coordinates(coords, eps=1e-9):
            return -1
        scores = self._raw_by_category(coords)
        top = max(scores, default=0.0)
        if top <= 0.0:
            return -1
        # If bounded sum saturates several categories, use the distance to
        # their nearest actual granule, avoiding a fictitious category centroid.
        winners = [i for i, score in enumerate(scores) if abs(score - top) <= 1e-12]
        if len(winners) == 1:
            return winners[0]
        q = np.asarray(coords, dtype=float)
        return min(winners, key=lambda i: (
            min(float(np.dot(p.positive - q, p.positive - q))
                for p in self.categories[i].prototypes), i
        ))

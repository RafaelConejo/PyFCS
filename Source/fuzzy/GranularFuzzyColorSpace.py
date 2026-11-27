"""Granular FCS with category-level compatibility and per-granule geometry.

The inherited ``prototypes/cores/supports`` lists contain ONE representative
per category, for legacy GUI and image-palette indexing only. They are not
used for granular membership. The complete atomic geometry is available via
``get_all_prototypes`` and ``get_granules``. No artificial category prototype
is used to determine membership or the winning category.
"""
import copy
import numpy as np

from Source.fuzzy.ColorHierarchy import ColorHierarchy

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
                 description=None, hierarchy=None):
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
        self._hierarchy = ColorHierarchy(self.categories, hierarchy)

    def set_tconorm(self, tconorm):
        operator = str(tconorm).lower().replace("-", "_")
        if operator not in GranularFuzzyColor.OPERATORS:
            raise ValueError("tconorm must be 'max' or 'bounded_sum'.")
        self.tconorm = operator
        return self.tconorm

    @property
    def hierarchy(self):
        """A defensive copy of the optional semantic graph."""
        return self._hierarchy.to_dict()

    def with_hierarchy(self, nodes):
        """Return a semantic copy sharing existing geometry, without rebuilding it."""
        graph = ColorHierarchy(self.categories, nodes)
        result = copy.copy(self)
        result._hierarchy = graph
        return result

    @classmethod
    def from_flat_space(cls, space):
        """Lift a single-granule-per-category space without constructing geometry."""
        if isinstance(space, cls):
            return space
        result = cls(space.space_name, [GranularFuzzyColor(p.label, [p], [c], [s])
                     for p, c, s in zip(space.prototypes, space.cores, space.supports)],
                     disjoint=space.disjoint, covering=space.covering,
                     color_space=space.color_space, reference_domain=space.reference_domain,
                     lambda1=space.lambda1, lambda2=space.lambda2, samples=space.samples,
                     negative_prototypes=space.negative_prototypes,
                     auxiliary_negatives=space.auxiliary_negatives,
                     description=space.description)
        for attr in ("geometry_only_import", "source_file_format", "import_warnings",
                     "num_aux_negatives_recorded"):
            if hasattr(space, attr):
                setattr(result, attr, getattr(space, attr))
        return result

    def make_hierarchy_view(self, labels, name=None):
        """Create a separate flat evaluation view from non-overlapping nodes.

        This preserves atomic geometry and the runtime t-conorm, and never
        reconstructs Voronoi. Views with repeated leaf occurrences cannot be
        represented by the existing flat GUI and are deliberately rejected.
        """
        labels = list(labels)
        if len(labels) < 2 or len(set(labels)) != len(labels):
            raise ValueError("Select at least two distinct categories for a view.")
        groups, used = [], set()
        for label in labels:
            counts = self._hierarchy.granule_occurrence_counts(label)
            leaves = self._hierarchy.unique_granules(label)
            if any(n != 1 for n in counts.values()) or used.intersection(leaves):
                raise ValueError("Selected categories share granules. Select non-overlapping "
                                 "categories (do not mix parents and their children).")
            used.update(leaves)
            indices = [self._granule_index[g] for g in leaves]
            groups.append(GranularFuzzyColor(label,
                          [self._flat_prototypes[i] for i in indices],
                          [self._flat_cores[i] for i in indices],
                          [self._flat_supports[i] for i in indices]))
        covering = self.covering and used == set(self._granule_index)
        # A singleton partition uses legacy normalization in the flat API;
        # refusing that view prevents silent divergence from raw hierarchical
        # membership. Such categories can be evaluated in the hierarchy dialog.
        if self.disjoint and covering and all(len(c.prototypes) == 1 for c in groups):
            raise ValueError("A complete singleton partition uses legacy normalized memberships. "
                             "Use the base model or the raw hierarchy evaluator instead.")
        result = GranularFuzzyColorSpace(name or self.space_name, groups,
                     tconorm=self.tconorm, disjoint=self.disjoint, covering=covering,
                     color_space=self.color_space, reference_domain=self.reference_domain,
                     lambda1=self.lambda1, lambda2=self.lambda2, samples=self.samples,
                     auxiliary_negatives=self.auxiliary_negatives)
        result.geometry_only_import = True
        result.num_aux_negatives_recorded = getattr(self, "num_aux_negatives_recorded",
                                                    len(self.auxiliary_negatives))
        result.import_warnings = ("Derived semantic view: original atomic geometry is retained. "
                                  "This flat view is not a new geometric construction. "
                                  "Keep the original hierarchical model for editing.")
        return result

    def get_hierarchy_granule_labels(self, label):
        return self._hierarchy.granule_labels(label)

    def get_root_categories(self):
        return self._hierarchy.roots()

    def get_all_category_labels(self):
        return self._hierarchy.category_labels

    def get_category_children(self, label):
        return self._hierarchy.children(label)

    def get_descendant_granules(self, label):
        return tuple(self._flat_prototypes[self._granule_index[g]]
                     for g in self._hierarchy.unique_granules(label))

    def get_categories_at_level(self, level=0):
        return self._hierarchy.categories_at_level(level)

    def calculate_membership_snapshot(self, value, input_space="LAB", tconorm=None):
        """Evaluate each unique geometry once; aggregate every semantic node.

        Raw degrees are intentional. The legacy flat membership API retains
        historical singleton-partition normalization for existing callers.
        """
        coords = self._coordinates(value, input_space)
        if self.reference_domain.contains_coordinates(coords, eps=1e-9):
            if self._precomputed is None:
                self.precompute_pack()
            degrees = {p.label: float(FuzzyColor._raw_membership_for_index(
                coords, i, self._precomputed)) for i, p in enumerate(self._flat_prototypes)}
        else:
            degrees = {p.label: 0.0 for p in self._flat_prototypes}
        values = self._hierarchy.evaluate(degrees, self.tconorm if tconorm is None else tconorm)
        return {"granules": degrees, "categories": {k: float(v) for k, v in values.items()}}

    def calculate_category_membership(self, value, category, input_space="LAB", tconorm=None):
        if category not in self.get_all_category_labels():
            raise ValueError(f"Unknown category '{category}'.")
        return self.calculate_membership_snapshot(value, input_space, tconorm)["categories"][category]

    def get_best_category(self, value, categories=None, input_space="LAB", tconorm=None):
        labels = tuple(self.get_root_categories() if categories is None else categories)
        scores = self.calculate_membership_snapshot(value, input_space, tconorm)["categories"]
        if any(label not in scores for label in labels):
            raise ValueError("Unknown active category.")
        top = max((scores[label] for label in labels), default=0.0)
        if top <= 0.0:
            return None
        q = np.asarray(self._coordinates(value, input_space))
        return min((label for label in labels if abs(scores[label]-top) <= 1e-12),
                   key=lambda label: min(float(np.dot(p.positive-q, p.positive-q))
                                         for p in self.get_descendant_granules(label)))

    def calculate_hierarchy_memberships(self, value, input_space="LAB",
                                        include_zeros=False, tconorm=None):
        values = self.calculate_membership_snapshot(value, input_space, tconorm)["categories"]
        return {name: degree for name, degree in values.items() if include_zeros or degree > 0.0}

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
        # If every category has exactly one granule, the same geometric
        # partition must evaluate identically regardless of which Python
        # wrapper was used to create it. There is no on-disk type marker.
        if self.is_partition and all(len(cat.prototypes) == 1 for cat in self.categories):
            coords = self._coordinates(new_color, input_space)
            if not self.reference_domain.contains_coordinates(coords, eps=1e-9):
                return {}
            if self._precomputed is None:
                self.precompute_pack()
            values = FuzzyColor.get_membership_degree(coords, self._flat_prototypes,
                                                       self._precomputed)
            return {cat.label: values[cat.prototypes[0].label]
                    for cat in self.categories if cat.prototypes[0].label in values}
        # Multiple positives per category retain their actual fuzzy union,
        # with MAX / BOUNDED_SUM selected at evaluation time.
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

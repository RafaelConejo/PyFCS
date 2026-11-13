"""A fuzzy color defined by the t-conorm union of its atomic Voronoi granules.

Each granule has its own positive prototype and Core/Voronoi/Support volumes.
MAX and BOUNDED_SUM are **runtime** operators; they are not file properties.
"""
from Source.fuzzy.FuzzyColor import FuzzyColor


class GranularFuzzyColor:
    OPERATORS = ("max", "bounded_sum")

    def __init__(self, label, prototypes, cores, supports):
        if not isinstance(label, str) or not label.strip():
            raise ValueError("A granular fuzzy color requires a category label.")
        self.label = label
        self.prototypes = list(prototypes)
        self.cores = list(cores)
        self.supports = list(supports)
        if not self.prototypes or not (len(self.prototypes) == len(self.cores) == len(self.supports)):
            raise ValueError(f"Inconsistent granules for category '{label}'.")

    @classmethod
    def aggregate(cls, degrees, tconorm="bounded_sum"):
        """Aggregate raw atomic memberships, preserving the [0,1] range."""
        operator = str(tconorm).lower().replace("-", "_")
        if operator not in cls.OPERATORS:
            raise ValueError("tconorm must be 'max' or 'bounded_sum'.")
        if operator == "max":
            return max(degrees, default=0.0)
        result = 0.0
        for degree in degrees:
            result += float(degree)
            if result >= 1.0:
                return 1.0
        return max(0.0, result)

    def get_all_prototypes(self):
        return [p.positive.copy() for p in self.prototypes]

    def raw_granule_memberships(self, coordinates, flattened_pack, start_index):
        return [FuzzyColor._raw_membership_for_index(
            coordinates, start_index + i, flattened_pack
        ) for i in range(len(self.prototypes))]

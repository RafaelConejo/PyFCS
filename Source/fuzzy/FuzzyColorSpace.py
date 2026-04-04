### my libraries ###
from Source.membership.MembershipFunction import MembershipFunction
from Source.fuzzy.FuzzyColor import FuzzyColor
from Source.colorspace.ReferenceDomain import ReferenceDomain


class FuzzyColorSpace(FuzzyColor):
    def __init__(self, space_name, prototypes, cores=None, supports=None, improve_geometry=True):
        self.space_name = space_name
        self.prototypes = prototypes
        self.function = MembershipFunction()

        scaling_factor = 0.5
        if cores is None and supports is None:
            self.cores, self.supports = FuzzyColor.create_core_support(prototypes, scaling_factor)
        else:
            self.cores = cores
            self.supports = supports

        # if improve_geometry:
        #     FuzzyColor.update_geometry(self.prototypes, self.cores, self.supports)

        self._precomputed = None

    def precompute_pack(self):
        domain_volume = ReferenceDomain.default_voronoi_reference_domain().get_volume()

        v_protos = [p.voronoi_volume for p in self.prototypes]
        v_cores  = [c.voronoi_volume for c in self.cores]
        v_supps  = [s.voronoi_volume for s in self.supports]

        rep = [v.getRepresentative() for v in v_protos]

        self._precomputed = {
            "domain_volume": domain_volume,
            "v_protos": v_protos,
            "v_cores": v_cores,
            "v_supps": v_supps,
            "rep": rep,
        }

        return self._precomputed

    def best_prototype_index_from_lab(self, lab_triplet):
        if self._precomputed is None:
            self.precompute_pack()
        return FuzzyColor.get_best_prototype_index(lab_triplet, self.prototypes, self.function, self._precomputed)

    def clear_precompute(self):
        self._precomputed = None

    def calculate_membership(self, new_color):
        if self._precomputed is None:
            self.precompute_pack()
        return FuzzyColor.get_membership_degree(
            new_color,
            self.prototypes,
            self.function,
            self._precomputed
        )

    def calculate_membership_for_prototype(self, new_color, idx_proto):
        return FuzzyColor.get_membership_degree_for_prototype(
            new_color,
            self.prototypes[idx_proto],
            self.cores[idx_proto],
            self.supports[idx_proto],
            self.function
        )

    def get_cores(self):
        return self.cores

    def get_supports(self):
        return self.supports

    def get_prototypes(self):
        return self.prototypes
### my libraries ###
from PyFCS.membership.MembershipFunction import MembershipFunction

from PyFCS.fuzzy.FuzzyColor import FuzzyColor
from PyFCS.colorspace.ReferenceDomain import ReferenceDomain

class FuzzyColorSpace(FuzzyColor):
    def __init__(self, space_name, prototypes, cores=None, supports=None):
        self.space_name = space_name
        self.prototypes = prototypes
        self.function = MembershipFunction()

        scaling_factor = 0.5
        if cores is None and supports is None:
            self.cores, self.supports = FuzzyColor.create_core_support(prototypes, scaling_factor)
        else:
            self.cores = cores
            self.supports = supports

        # Precompute cache (lazy)
        self._precomputed = None

    def precompute_pack(self):
        """
        Precompute constant geometry structures for fast membership calls.
        Call this once per mapping run (or whenever prototypes/cores/supports change).
        """
        domain_volume = ReferenceDomain.default_voronoi_reference_domain().get_volume()

        v_protos = [p.voronoi_volume for p in self.prototypes]
        v_cores  = [c.voronoi_volume for c in self.cores]
        v_supps  = [s.voronoi_volume for s in self.supports]

        rep_ps = [v.getRepresentative() for v in v_protos]
        rep_cs = [v.getRepresentative() for v in v_cores]
        rep_ss = [v.getRepresentative() for v in v_supps]

        self._precomputed = {
            "domain_volume": domain_volume,
            "v_protos": v_protos,
            "v_cores": v_cores,
            "v_supps": v_supps,
            "rep_ps": rep_ps,
            "rep_cs": rep_cs,
            "rep_ss": rep_ss,
        }

        return self._precomputed

    def clear_precompute(self):
        self._precomputed = None

    def calculate_membership(self, new_color):
        return FuzzyColor.get_membership_degree(
                new_color,
                self.prototypes,
                self.function,
                self._precomputed
            )

    def calculate_membership_for_prototype(self, new_color, idx_proto):
        return FuzzyColor.get_membership_degree_for_prototype(
            new_color, self.prototypes[idx_proto], self.cores[idx_proto], self.supports[idx_proto], self.function
        )

    def get_cores(self):
        return self.cores

    def get_supports(self):
        return self.supports

    def get_prototypes(self):
        return self.prototypes


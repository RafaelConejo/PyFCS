### my libraries ###
from PyFCS.membership.MembershipFunction import MembershipFunction

from PyFCS.fuzzy.FuzzyColor import FuzzyColor

class FuzzyColorSpace(FuzzyColor):
    def __init__(self, space_name, prototypes):
        self.space_name = space_name
        self.prototypes = prototypes
        self.function = MembershipFunction()
        
        scaling_factor = 0.5
        self.cores, self.supports = FuzzyColor.create_core_support(prototypes, scaling_factor)


    def calculate_membership(self, new_color):
        member_degree = FuzzyColor.get_membership_degree(new_color, self.prototypes, self.cores, self.supports, self.function)
        return member_degree

    def calculate_membership_for_prototype(self, new_color, idx_proto):
        member_degree = FuzzyColor.get_membership_degree_for_prototype(new_color, self.prototypes[idx_proto], self.cores[idx_proto], self.supports[idx_proto], self.function)
        return member_degree

### my libraries ###
from PyFCS.membership.MembershipFunction import MembershipFunction

from PyFCS.fuzzy.FuzzyColor import FuzzyColor

class FuzzyColorSpace(FuzzyColor):
    def __init__(self, space_name, prototypes, cores=None, supports=None):
        # Initialize attributes
        self.space_name = space_name
        self.prototypes = prototypes
        self.function = MembershipFunction()

        # Define a scaling factor for the core and support color creation
        scaling_factor = 0.5

        # If no cores or supports are provided, create them using FuzzyColor
        if cores is None and supports is None:
            self.cores, self.supports = FuzzyColor.create_core_support(prototypes, scaling_factor)
        else:
            self.cores = cores
            self.supports = supports


    def calculate_membership(self, new_color):
        member_degree = FuzzyColor.get_membership_degree(new_color, self.prototypes, self.cores, self.supports, self.function)
        return member_degree

    def calculate_membership_for_prototype(self, new_color, idx_proto):
        member_degree = FuzzyColor.get_membership_degree_for_prototype(new_color, self.prototypes[idx_proto], self.cores[idx_proto], self.supports[idx_proto], self.function)
        return member_degree
    
    def get_cores(self):
     return self.cores
    
    def get_supports(self):
     return self.supports
    
    def get_prototypes(self):
     return self.prototypes

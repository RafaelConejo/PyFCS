from abc import ABC, abstractmethod

from PyFCS.membership.MembershipFunction import MembershipFunction
from PyFCS.colorspace.ReferenceDomain import ReferenceDomain

class FuzzyColor(ABC):
    @abstractmethod
    def __init__(self, space_name, prototypes):
        self.function = MembershipFunction()
        self.lab_reference_domain = ReferenceDomain.default_voronoi_reference_domain()
    
    @abstractmethod
    def add_face_to_core_support(self, face, representative, core, support):
        pass
    
    @abstractmethod
    def create_core_support(self, prototypes):
        pass
    
    @abstractmethod
    def get_membership_degree(self, new_point):
        pass

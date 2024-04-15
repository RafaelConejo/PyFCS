from abc import ABC, abstractmethod

class ColorSpace(ABC):
    @abstractmethod
    def convert_to(self):
        pass

    @classmethod
    @abstractmethod
    def convert_from(cls, rgb):
        pass


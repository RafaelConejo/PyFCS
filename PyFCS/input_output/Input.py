from abc import ABC, abstractmethod

class Input(ABC):
    @abstractmethod
    def read_file(self, file_path):
        pass

    @abstractmethod
    def write_file(self, file_path):
        pass










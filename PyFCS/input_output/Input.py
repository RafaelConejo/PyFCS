from abc import ABC, abstractmethod

class Input(ABC):
    @staticmethod
    def instance(ext):
        if ext == '.cns':
            from PyFCS.input_output.InputCNS import InputCNS
            return InputCNS()
        else:
            raise ValueError("Unsupported file format")

    @abstractmethod
    def read_file(self, file_path):
        pass

    @abstractmethod
    def write_file(self, file_path):
        pass










from abc import ABC, abstractmethod

class Input(ABC):
    @staticmethod
    def instance(ext):
        if ext == '.cns':
            from Source.input_output.InputCNS import InputCNS
            return InputCNS()
        elif ext == '.fcs':
            from Source.input_output.InputFCS import InputFCS
            return InputFCS()
        else:
            raise ValueError("Unsupported file format")

    @abstractmethod
    def read_file(self, file_path):
        pass

    @abstractmethod
    def write_file(self, file_path):
        pass










from PyFCS.colorspace.ColorSpace import ColorSpace
from skimage import color

class ColorSpaceRGB(ColorSpace):
    def __init__(self, r, g, b):
        self.r = r
        self.g = g
        self.b = b

    def convert_to(self):
        return self.r, self.g, self.b

    @classmethod
    def convert_from(cls, lab):
        # Conversion from RGB to LAB
        rgb_color = color.lab2rgb(lab)
        return rgb_color
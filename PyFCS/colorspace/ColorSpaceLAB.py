from skimage import color

from PyFCS.colorspace.ColorSpace import ColorSpace

class ColorSpaceLAB(ColorSpace):
    def __init__(self, l, a, b):
        self.l = l
        self.a = a
        self.b = b

    def convert_to(self):
        # Implement conversion from LAB to RGB
        pass

    @classmethod
    def convert_from(cls, rgb):
        # Conversion from RGB to LAB
        lab_color = color.rgb2lab(rgb)
        return lab_color
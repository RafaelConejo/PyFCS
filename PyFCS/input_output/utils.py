import cv2
import numpy as np
import matplotlib.pyplot as plt

from PyFCS.colorspace.ColorSpaceRGB import ColorSpaceRGB
from PyFCS.colorspace.ColorSpaceLAB import ColorSpaceLAB

class Utils:
    @staticmethod
    def image_processing(img_path, IMG_WIDTH, IMG_HEIGHT):
        # Open the image
        image = cv2.imread(img_path)
        image = cv2.resize(image, (IMG_WIDTH, IMG_HEIGHT))
        
        # Convert the image to RGB format
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        
        # Normalize the image
        image = image.astype(np.float32) / 255.0
        
        return image


    @staticmethod
    def add_lab_value():
        try:
            # Prompt the user to enter LAB values
            L = float(input("Enter L value (0-100): "))
            if L < 0 or L > 100:
                raise ValueError("L value must be between 0 and 100.")

            a = float(input("Enter a value (-128-128): "))
            if a < -128 or a > 128:
                raise ValueError("a value must be between -128 and 128.")

            b = float(input("Enter b value (-128-128): "))
            if b < -128 or b > 128:
                raise ValueError("b value must be between -128 and 128.")

            return np.array([L, a, b])

        except ValueError as e:
            print("Error:", e)
            exit(0)


    @staticmethod
    def pick_pixel(image):
        mutable_object = {'click': None, 'lab_pixel': None}

        def onclick(event):
            # print('Coordinates of selected pixel:', event.xdata, event.ydata)
            mutable_object['click'] = (event.xdata, event.ydata)

            # Get the color of the pixel at (y, x) coordinates
            x, y = int(event.xdata), int(event.ydata)
            pixel = image[y, x]
            rgb_pixel = ColorSpaceRGB(pixel[0], pixel[1], pixel[2])
            print('Color of the pixel in RGB:', rgb_pixel.r, rgb_pixel.g, rgb_pixel.b)
            
            lab_pixel = ColorSpaceLAB.convert_from(rgb_pixel.convert_to())
            mutable_object['lab_pixel'] = lab_pixel  

            plt.close()

        fig = plt.figure()
        cid = fig.canvas.mpl_connect('button_press_event', onclick)
        plt.imshow(image)
        plt.show()

        return mutable_object['lab_pixel']

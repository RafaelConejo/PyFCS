import cv2
import numpy as np
import matplotlib.pyplot as plt
from skimage import color

from PyFCS.colorspace.ColorSpaceRGB import ColorSpaceRGB
from PyFCS.colorspace.ColorSpaceLAB import ColorSpaceLAB

class Utils:
    def image_processing(img_path, IMG_WIDTH, IMG_HEIGHT):
        # Abre la imagen
        imagen = cv2.imread(img_path)
        imagen = cv2.resize(imagen, (IMG_WIDTH, IMG_HEIGHT))
        
        # Convierte la imagen a formato RGB
        imagen = cv2.cvtColor(imagen, cv2.COLOR_BGR2RGB)
        
        # Normaliza la imagen
        imagen = imagen.astype(np.float32) / 255.0
        
        return imagen


    def add_lab_value():
        # Solicitar al usuario que ingrese los valores LAB
        L = float(input("Ingrese el valor L (0-100): "))
        a = float(input("Ingrese el valor a (-128-127): "))
        b = float(input("Ingrese el valor b (-128-127): "))
        return np.array([L, a, b])




    def pick_pixel(image):
        mutable_object = {'click': None, 'lab_pixel': None}

        def onclick(event):
            # print('Coordenadas del píxel seleccionado:', event.xdata, event.ydata)
            mutable_object['click'] = (event.xdata, event.ydata)

            # Obtener el color del píxel en las coordenadas (y, x)
            x, y = int(event.xdata), int(event.ydata)
            pixel = image[y, x]
            rgb_pixel = ColorSpaceRGB(pixel[0], pixel[1], pixel[2])
            print('Color del píxel en RGB:', rgb_pixel)
            
            lab_pixel = ColorSpaceLAB.convert_from(rgb_pixel.convert_to())
            mutable_object['lab_pixel'] = lab_pixel  

            plt.close()

        fig = plt.figure()
        cid = fig.canvas.mpl_connect('button_press_event', onclick)
        plt.imshow(image)
        plt.show()

        return mutable_object['lab_pixel']
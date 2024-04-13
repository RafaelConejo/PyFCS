import os
import cv2
import numpy as np
from PIL import Image
from skimage import color
import matplotlib.pyplot as plt

### my libraries ###
from PyFCS import Input, Prototype, FuzzyColorSpace


def add_lab_value():
    # Solicitar al usuario que ingrese los valores LAB
    L = int(input("Ingrese el valor L (0-100): "))
    a = int(input("Ingrese el valor a (-128-127): "))
    b = int(input("Ingrese el valor b (-128-127): "))
    return np.array([L, a, b])




def pick_pixel(image):
    mutable_object = {'click': None, 'lab_pixel': None}

    def onclick(event):
        # print('Coordenadas del píxel seleccionado:', event.xdata, event.ydata)
        mutable_object['click'] = (event.xdata, event.ydata)

        # Obtener el color del píxel en las coordenadas (y, x)
        x, y = int(event.xdata), int(event.ydata)
        rgb_pixel = image[y, x]
        print('Color del píxel en RGB:', rgb_pixel)
        
        lab_pixel = color.rgb2lab(rgb_pixel)
        mutable_object['lab_pixel'] = lab_pixel  

        plt.close()

    fig = plt.figure()
    cid = fig.canvas.mpl_connect('button_press_event', onclick)
    plt.imshow(image)
    plt.show()

    return mutable_object['lab_pixel']






def main():
    IMG_WIDTH = 128
    IMG_HEIGHT = 128
    img_path = ".\\imagen_test\\banana.png"
    image = Input.image_processing(img_path, IMG_WIDTH, IMG_HEIGHT)
    # # Convertir la imagen RGB a CIELAB
    # lab_image = color.rgb2lab(imagen)

    # # Crear una matriz para almacenar los valores LAB
    # matriz_lab = []
    # for y in range(lab_image.shape[0]):
    #     for x in range(lab_image.shape[1]):
    #         if lab_image[y, x, 0] > 0:  # Verificar si el píxel está en la zona dental
    #             lab_values = (lab_image[y, x, 0], lab_image[y, x, 1], lab_image[y, x, 2])
    #             matriz_lab.append(lab_values)
    




    option = input("Seleccione una opción:\n 1. Ingresar valor LAB\n 2. Seleccionar un píxel en una imagen\n")

    if option == "1":
        lab_color = add_lab_value()
        print("Valor LAB ingresado:", lab_color)

    elif option == "2":
        if image is None:
            print("No se pudo cargar la imagen.")
            return
        lab_color = pick_pixel(image)
        print("Valor LAB del píxel seleccionado:", lab_color)

    else:
        print("Opción no válida.")





    # Step 1: Reading the .cns file using the Input class
    actual_dir = os.getcwd()
    color_space_path = os.path.join(actual_dir, 'fuzzy_color_spaces\\ISCC_NBS_BASIC.cns')
    input_class = Input()
    color_data = input_class.read_cns_file(color_space_path)


    # Step 2: Creating Prototype objects for each color
    prototypes = []
    for color_name, color_value in color_data.items():
        # Assume that 'color_value' contains the positive prototype and set of negatives
        positive_prototype = color_value['positive_prototype']
        negative_prototypes = color_value['negative_prototypes']

        # Create a Prototype object for each color
        prototype = Prototype(label=color_name, positive=positive_prototype, negatives=negative_prototypes)
        prototypes.append(prototype)


    # Step 3: Creating the fuzzy color space using the Prototype objects
    fuzzy_color_space = FuzzyColorSpace(space_name='VIBRATIONS', prototypes=prototypes)

    # Step 4: Calculating the membership degree of a Lab color to the fuzzy color space
    # lab_color = [52, -36, 55]  # Example Lab color
    membership_degrees = fuzzy_color_space.calculate_membership(lab_color)

    # Displaying the induced possibility distribution by the fuzzy color space
    print("Possibility distribution for the color:", lab_color)
    for color_name, membership_degree in membership_degrees.items():
        print(f"{membership_degree} / {color_name} + ")


if __name__ == "__main__":
    main()
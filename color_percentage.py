import os


### my libraries ###
from PyFCS import InputCNS, Prototype, FuzzyColorSpace
from PyFCS.input_output.utils import Utils




def main():
    IMG_WIDTH = 128
    IMG_HEIGHT = 128
    img_path = ".\\imagen_test\\cuadro.png"
    image = Utils.image_processing(img_path, IMG_WIDTH, IMG_HEIGHT)

    


    option = input("Seleccione una opción:\n 1. Ingresar valor LAB\n 2. Seleccionar un píxel en una imagen\n")

    if option == "1":
        lab_color = Utils.add_lab_value()
        print("Valor LAB ingresado:", lab_color)

    elif option == "2":
        if image is None:
            print("No se pudo cargar la imagen.")
            return
        lab_color = Utils.pick_pixel(image)
        print("Valor LAB del píxel seleccionado:", lab_color)

    else:
        print("Opción no válida.")



    colorspace_name = 'BRUGUER-WORLD COLORS.cns'
    name_colorspace = os.path.splitext(colorspace_name)[0]
    extension = os.path.splitext(colorspace_name)[1]

    # Step 1: Reading the .cns file using the Input class
    actual_dir = os.getcwd()
    color_space_path = os.path.join(actual_dir, 'fuzzy_color_spaces\\'+colorspace_name)
    input_class = InputCNS()
    color_data = input_class.read_file(color_space_path)


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
    fuzzy_color_space = FuzzyColorSpace(space_name=name_colorspace , prototypes=prototypes)

    # Step 4: Calculating the membership degree of a Lab color to the fuzzy color space
    membership_degrees = fuzzy_color_space.get_membership_degree(lab_color)

    # Displaying the induced possibility distribution by the fuzzy color space
    print("Possibility distribution for the color:", lab_color)
    for color_name, membership_degree in membership_degrees.items():
        print(f"{membership_degree} / {color_name} + ")


if __name__ == "__main__":
    main()
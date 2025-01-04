import os
import sys

# Get the path to the directory containing PyFCS
current_dir = os.path.dirname(__file__)
pyfcs_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))

# Add the PyFCS path to sys.path
sys.path.append(pyfcs_dir)

### my libraries ###
from PyFCS import Input, Prototype, FuzzyColorSpace
from PyFCS.input_output.utils import Utils




def main():
    colorspace_name = 'BRUGUER-WORLD COLORS.cns'

    option = input("Select an option:\n 1. Enter LAB value\n 2. Select a pixel on an image\n")
    if option == "1":
        lab_color = Utils.add_lab_value()
        print("Entered LAB value:", lab_color)

    elif option == "2":
        IMG_WIDTH = 256
        IMG_HEIGHT = 256
        img_path = ".\\imagen_test\\cuadro.png"
        image = Utils.image_processing(img_path, IMG_WIDTH, IMG_HEIGHT)

        if image is None:
            print("Failed to load the image.")
            return
        lab_color = Utils.pick_pixel(image)
        print("LAB value of the selected pixel:", lab_color)

    else:
        print("Invalid option.")


    name_colorspace = os.path.splitext(colorspace_name)[0]
    extension = os.path.splitext(colorspace_name)[1]

    # Step 1: Reading the .cns file using the Input class
    actual_dir = os.getcwd()
    color_space_path = os.path.join(actual_dir, 'fuzzy_color_spaces\\'+colorspace_name)
    input_class = Input.instance(extension)
    color_data = input_class.read_file(color_space_path)


    # Step 2: Creating Prototype objects for each color
    prototypes = []
    for color_name, color_value in color_data.items():
        # Assume that 'color_value' contains the positive prototype and set of negatives
        positive_prototype = color_value['positive_prototype']
        negative_prototypes = color_value['negative_prototypes']

        # Create a Prototype object for each color
        prototype = Prototype(label=color_name, positive=positive_prototype, negatives=negative_prototypes, add_false=True)
        prototypes.append(prototype)


    # Step 3: Creating the fuzzy color space using the Prototype objects
    fuzzy_color_space = FuzzyColorSpace(space_name=name_colorspace , prototypes=prototypes)

    # Step 4: Calculating the membership degree of a Lab color to the fuzzy color space
    membership_degrees = fuzzy_color_space.calculate_membership(lab_color)

    # Displaying the induced possibility distribution by the fuzzy color space
    print("Possibility distribution for the color:", lab_color)
    for color_name, membership_degree in membership_degrees.items():
        print(f"{membership_degree} / {color_name} + ")


if __name__ == "__main__":
    main()
import os
import sys
from skimage import color
import numpy as np
import matplotlib.pyplot as plt

# Get the path to the directory containing PyFCS
current_dir = os.path.dirname(__file__)
pyfcs_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))

# Add the PyFCS path to sys.path
sys.path.append(pyfcs_dir)

### my libraries ###
from PyFCS import Input, Prototype, FuzzyColorSpace
from PyFCS.input_output.utils import Utils




def main():
    colorspace_name = 'VITA-CLASSICAL.cns'
    img_path = ".\\imagen_test\\B4.png"

    IMG_WIDTH = 256
    IMG_HEIGHT = 256
    image = Utils.image_processing(img_path, IMG_WIDTH, IMG_HEIGHT)

    if image is None:
        print("Failed to load the image.")
        return

    lab_image = color.rgb2lab(image)

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
        positive_prototype = color_value['positive_prototype']
        negative_prototypes = color_value['negative_prototypes']

        # Create a Prototype object for each color
        prototype = Prototype(label=color_name, positive=positive_prototype, negatives=negative_prototypes)
        prototypes.append(prototype)


    # Step 3: Creating the fuzzy color space using the Prototype objects
    fuzzy_color_space = FuzzyColorSpace(space_name=name_colorspace , prototypes=prototypes)


    print("Available Prototypes:")
    for i, prototype in enumerate(prototypes):
        print(f"{i + 1}. {prototype.label}")

    selected_option = int(input("Select a prototype by number: "))
    if selected_option < 1 or selected_option > len(prototypes):
        print("Invalid selection.")
        return

    selected_prototype = prototypes[selected_option - 1]
    print(f"Selected Prototype: {selected_prototype.label}")


    # Step 4: Process each Pixel
    grayscale_image = np.zeros((image.shape[0], image.shape[1]), dtype=np.uint8)
    for y in range(image.shape[0]):
        for x in range(image.shape[1]):
            lab_color = lab_image[y, x]
            membership_degree = fuzzy_color_space.calculate_membership_for_prototype(lab_color, selected_option - 1)

            # Scale to grayscale
            grayscale_image[y, x] = int(membership_degree * 255)  


    plt.imshow(grayscale_image, cmap='gray')
    plt.title(f'Processed Image (Prototype: {selected_prototype.label})')
    plt.axis('off')  # Hide axis
    plt.show()


if __name__ == "__main__":
    main()
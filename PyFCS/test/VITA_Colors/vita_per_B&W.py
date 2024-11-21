############################################################################################################################################################################################################
# This code visualizes the regions in an image that exhibit the highest membership degree to specific fuzzy prototypes in white (intensified grayscale). 
# It achieves this by processing a given image using a fuzzy color space derived from defined prototypes.
############################################################################################################################################################################################################

import os
import sys
from skimage import color
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import RadioButtons

# Get the path to the directory containing PyFCS
current_dir = os.path.dirname(__file__)
pyfcs_dir = os.path.abspath(os.path.join(current_dir, '..', '..', '..'))

# Add the PyFCS path to sys.path
sys.path.append(pyfcs_dir)

### my libraries ###
from PyFCS import Input, Prototype, FuzzyColorSpace
from PyFCS.input_output.utils import Utils


def process_image(prototypes, lab_image, fuzzy_color_space, selected_option):
    selected_prototype = prototypes[selected_option]
    print(f"Selected Prototype: {selected_prototype.label}")

    grayscale_image = np.zeros((lab_image.shape[0], lab_image.shape[1]), dtype=np.uint8)
    for y in range(lab_image.shape[0]):
        for x in range(lab_image.shape[1]):
            lab_color = lab_image[y, x]
            membership_degree = fuzzy_color_space.calculate_membership_for_prototype(lab_color, selected_option)

            # Scale to grayscale
            grayscale_image[y, x] = int(membership_degree * 255)  
    
    return grayscale_image


def update(label):
    selected_option = prototype_labels.index(label)
    
    # Clear the current image
    ax.clear()
    
    # Process the image with the selected prototype
    updated_image = process_image(prototypes, lab_image, fuzzy_color_space, selected_option)
    
    # Redraw the image
    ax.imshow(updated_image, cmap='gray')
    ax.set_title(f'Processed Image (Prototype: {prototypes[selected_option].label})')
    ax.axis('off')  # Hide axis again after clearing
    
    # Update the canvas
    fig.canvas.draw_idle()



def main():
    global prototypes, lab_image, fuzzy_color_space, prototype_labels, ax, fig

    var = "m_A1"

    colorspace_name = 'VITA-CLASSICAL-BLACK.cns'
    img_path = os.path.join(".", "imagen_test", f"{var}.png")

    IMG_WIDTH = 103
    IMG_HEIGHT = 103
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
    prototype_labels = []
    for color_name, color_value in color_data.items():
        positive_prototype = color_value['positive_prototype']
        negative_prototypes = color_value['negative_prototypes']

        # Create a Prototype object for each color
        prototype = Prototype(label=color_name, positive=positive_prototype, negatives=negative_prototypes)
        prototypes.append(prototype)
        prototype_labels.append(color_name)

    # Step 3: Creating the fuzzy color space using the Prototype objects
    fuzzy_color_space = FuzzyColorSpace(space_name=name_colorspace, prototypes=prototypes)

    # Create the figure and initial plot
    fig, ax = plt.subplots()
    plt.subplots_adjust(left=0.3, bottom=0.2)
    ax.axis('off')  # Hide axis

    # Initial image display
    initial_prototype = 0
    grayscale_image = process_image(prototypes, lab_image, fuzzy_color_space, initial_prototype)
    ax.imshow(grayscale_image, cmap='gray')
    ax.set_title(f'Processed Image (Prototype: {prototypes[initial_prototype].label})')

    # Create RadioButtons for selecting prototype
    ax_prototype = plt.axes([0.05, 0.3, 0.15, 0.6], facecolor='lightgoldenrodyellow')
    prototype_selector = RadioButtons(ax_prototype, prototype_labels)
    
    # Connect the update function to the radio button
    prototype_selector.on_clicked(update)

    plt.show()

if __name__ == "__main__":
    main()

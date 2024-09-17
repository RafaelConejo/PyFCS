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
    for color_name, color_value in color_data.items():
        positive_prototype = color_value['positive_prototype']
        negative_prototypes = color_value['negative_prototypes']

        # Create a Prototype object for each color
        prototype = Prototype(label=color_name, positive=positive_prototype, negatives=negative_prototypes)
        prototypes.append(prototype)

    # Step 3: Creating the fuzzy color space using the Prototype objects
    fuzzy_color_space = FuzzyColorSpace(space_name=name_colorspace, prototypes=prototypes)

    # Step 4: Define a list of differentiated colors for the prototypes
    color_map = plt.cm.get_cmap('tab20', len(prototypes))  # Use a colormap with distinct colors
    prototype_colors = {prototype.label: color_map(i)[:3] for i, prototype in enumerate(prototypes)}  # Map prototype names to colors
    
    # Assign black to the last prototype
    prototype_colors[prototypes[-1].label] = (0, 0, 0)  # RGB for black

    # Step 5: Process each Pixel
    colorized_image = np.zeros((image.shape[0], image.shape[1], 3), dtype=np.uint8)
    for y in range(image.shape[0]):
        for x in range(image.shape[1]):
            lab_color = lab_image[y, x]

            # Get membership degrees for all prototypes in one call
            membership_degrees = fuzzy_color_space.calculate_membership(lab_color)

            # Find the prototype with the highest membership degree
            max_membership = -1
            best_prototype = None

            for name, degree in membership_degrees.items():
                if degree > max_membership:
                    max_membership = degree
                    best_prototype = next(p for p in prototypes if p.label == name)

            # Convert the best prototype's positive color to RGB and assign it to the pixel
            if best_prototype:
                rgb_color = np.array(prototype_colors[best_prototype.label]) * 255
                colorized_image[y, x] = rgb_color.astype(np.uint8)


    plt.imshow(colorized_image)
    plt.title('Processed Image (Colored by Closest Prototype)')
    plt.axis('off')  # Hide axis

    # Create legend
    handles = [plt.Line2D([0], [0], marker='o', color='w', markerfacecolor=prototype_colors[p.label], markersize=10) for p in prototypes]
    labels = [p.label for p in prototypes]
    plt.legend(handles, labels, loc='upper right', title='Prototypes')

    plt.show()

if __name__ == "__main__":
    main()

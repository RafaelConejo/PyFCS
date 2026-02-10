############################################################################################################################################################################################################
# This code processes dental images to reconstruct their color representation based on a fuzzy color space model. 
# Each pixel in the image is assigned the color of the prototype with the highest membership degree, effectively mapping the image to a predefined set of colors. 
# The reconstructed image is then saved with added visual elements, including dividing lines (splitting the image into a 3x3 grid) and a legend showing the prototypes and their corresponding colors.
# This approach is tailored for dental applications, helping analyze and visualize the distribution of color prototypes in tooth samples.
############################################################################################################################################################################################################

import os
import sys
from skimage import color
import numpy as np
import matplotlib.pyplot as plt

# Get the path to the directory containing PyFCS
current_dir = os.path.dirname(__file__)
pyfcs_dir = os.path.abspath(os.path.join(current_dir, '..', '..', '..'))

# Add the PyFCS path to sys.path
sys.path.append(pyfcs_dir)

### my libraries ###
from Source import Input, Prototype, FuzzyColorSpace
from Source.input_output.utils import Utils

# Function to reconstruct the image and save it with grid lines and legend
def reconstruct_and_save_image_with_legend(colorized_image, prototypes, prototype_colors, img_path):
    # Create the results directory if it does not exist
    results_dir = os.path.join("imagen_test", "VITA_RESULTS")
    os.makedirs(results_dir, exist_ok=True)

    # Path to save the resulting image
    result_image_path = os.path.join(results_dir, os.path.basename(img_path))

    # Create a figure and display the processed image
    fig, ax = plt.subplots()
    ax.imshow(colorized_image)
    plt.title('Processed Tooth ' + os.path.splitext(os.path.basename(img_path))[0])
    plt.axis('off')  # Hide axes

    # Create grid lines to divide the image into 3x3 sections
    img_height, img_width, _ = colorized_image.shape
    height_third = img_height // 3
    width_third = img_width // 3

    # Draw vertical and horizontal lines for the 3x3 grid
    for i in range(1, 3):
        ax.axhline(i * height_third, color='white', linewidth=1)
        ax.axvline(i * width_third, color='white', linewidth=1)

    # Create a legend with the prototypes
    handles = [plt.Line2D([0], [0], marker='o', color='w', markerfacecolor=prototype_colors[p.label], markersize=10)
               for p in prototypes]
    labels = [p.label for p in prototypes]

    # Adjust the legend and place it outside the image
    plt.legend(handles, labels, loc='center left', bbox_to_anchor=(1, 0.5), title='Prototypes')
    plt.tight_layout()

    # Save the complete figure with the legend and grid lines
    plt.savefig(result_image_path, bbox_inches='tight')
    plt.close(fig)
    print(f"Processed image saved at: {result_image_path}")

# Main function to process all images in the directory
def main():
    colorspace_name = 'VITA-CLASSICAL-BLACK-2.cns'
    img_dir = os.path.join(".", "imagen_test", "VITA_CLASSICAL\\")
    IMG_WIDTH = 308
    IMG_HEIGHT = 448

    name_colorspace = os.path.splitext(colorspace_name)[0]
    extension = os.path.splitext(colorspace_name)[1]

    # Read the .cns file using the Input class
    actual_dir = os.getcwd()
    color_space_path = os.path.join(actual_dir, 'fuzzy_color_spaces', colorspace_name)
    input_class = Input.instance(extension)
    color_data = input_class.read_file(color_space_path)

    # Create Prototype objects for each color
    prototypes = []
    for color_name, color_value in color_data.items():
        positive_prototype = color_value['positive_prototype']
        negative_prototypes = color_value['negative_prototypes']
        prototype = Prototype(label=color_name, positive=positive_prototype, negatives=negative_prototypes)
        prototypes.append(prototype)

    # Create the fuzzy color space with the Prototype objects
    fuzzy_color_space = FuzzyColorSpace(space_name=name_colorspace, prototypes=prototypes)

    # Define differentiated colors for the prototypes
    color_map = plt.cm.get_cmap('tab20', len(prototypes))
    prototype_colors = {prototype.label: color_map(i)[:3] for i, prototype in enumerate(prototypes)}
    prototype_colors["BLACK"] = (0, 0, 0)  # RGB for black

    # Process each image in the directory
    for filename in os.listdir(img_dir):
        if filename.endswith(".png"):
            img_path = os.path.join(img_dir, filename)
            image = Utils.image_processing(img_path, IMG_WIDTH, IMG_HEIGHT)

            if image is None:
                print(f"Failed to load the image {filename}.")
                continue

            lab_image = color.rgb2lab(image)
            colorized_image = np.zeros((image.shape[0], image.shape[1], 3), dtype=np.uint8)
            membership_cache = {}

            # Process each pixel in the image
            for y in range(image.shape[0]):
                for x in range(image.shape[1]):
                    lab_color = tuple(lab_image[y, x])

                    # Check if the LAB color has already been processed
                    if lab_color in membership_cache:
                        membership_degrees = membership_cache[lab_color]
                    else:
                        # Calculate membership degrees if not already in the dictionary
                        membership_degrees = fuzzy_color_space.calculate_membership(lab_color)
                        membership_cache[lab_color] = membership_degrees

                    # Find the prototype with the highest membership degree
                    max_membership = -1
                    best_prototype = None

                    for name, degree in membership_degrees.items():
                        if degree > max_membership:
                            max_membership = degree
                            best_prototype = next(p for p in prototypes if p.label == name)

                    # Assign the RGB color of the prototype to the pixel
                    if best_prototype:
                        rgb_color = np.array(prototype_colors[best_prototype.label]) * 255
                        colorized_image[y, x] = rgb_color.astype(np.uint8)

            # Call the function to reconstruct and save the image with legend and grid lines
            reconstruct_and_save_image_with_legend(colorized_image, prototypes, prototype_colors, img_path)

if __name__ == "__main__":
    main()

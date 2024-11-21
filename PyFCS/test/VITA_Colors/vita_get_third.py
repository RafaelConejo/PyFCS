############################################################################################################################################################################################################
# This code processes dental image samples to identify the most dominant color prototypes in three specific vertical sections of the image: the upper third, central third, and lower third. 
# It uses a fuzzy color space model to analyze pixel colors and determine their membership to predefined color prototypes. The main goal is to quantify the presence of color prototypes 
# in these regions to assist in analyzing dental color distributions, such as for shade matching in dentistry.
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
from PyFCS import Input, Prototype, FuzzyColorSpace
from PyFCS.input_output.utils import Utils


#################################################################### FUNTIONS ####################################################################

def process_image(img_path, fuzzy_color_space):
    """
    Process a tooth image by calculating the top 3 prototypes per section (middle third) based on fuzzy membership values.

    Parameters:
    img_path (str): Path to the image to be processed.
    fuzzy_color_space (FuzzyColorSpace): The fuzzy color space object used for calculating membership degrees.

    Returns:
    list: A list of the top 3 prototypes for each region of the image.
    """
    IMG_WIDTH = 308  # Set the desired image width
    IMG_HEIGHT = 448  # Set the desired image height
    image = Utils.image_processing(img_path, IMG_WIDTH, IMG_HEIGHT)  

    if image is None:
        print(f"Failed to load the image {img_path}.")  # Error if image couldn't be loaded
        return None

    lab_image = color.rgb2lab(image)  # Convert the image to LAB color space
    membership_values = np.zeros((image.shape[0], image.shape[1]), dtype=object)  # Store membership values

    membership_cache = {}  # Cache to store membership values for already processed colors
    region_counts = [{}, {}, {}]  # Store membership degree sums for each region

    # Define the boundaries for the 3x3 divisions
    height_third = image.shape[0] // 3
    width_third = image.shape[1] // 3

    # Loop through the image pixels, focusing on the central column of each third
    for y in range(image.shape[0]):
        for x in range(image.shape[1]):
            if width_third <= x < 2 * width_third:  # Only consider the central column
                if y < height_third:
                    region_idx = 0  # Region 1,1
                elif height_third <= y < 2 * height_third:
                    region_idx = 1  # Region 2,2
                elif 2 * height_third <= y < image.shape[0]:
                    region_idx = 2  # Region 3,3
                else:
                    continue  # Skip if not in any defined region

                lab_color = tuple(lab_image[y, x])  # Get the color at the current pixel

                # Check if the color's membership degrees are cached
                if lab_color in membership_cache:
                    membership_degrees = membership_cache[lab_color]  # Use cached values
                else:
                    membership_degrees = fuzzy_color_space.calculate_membership(lab_color)  # Calculate membership
                    membership_cache[lab_color] = membership_degrees  # Cache the result

                membership_values[y, x] = membership_degrees  # Store the membership for the current pixel

                # Add the membership degrees to the corresponding region count
                for name, degree in membership_degrees.items():
                    if name in region_counts[region_idx]:
                        region_counts[region_idx][name] += degree  # Accumulate the degree
                    else:
                        region_counts[region_idx][name] = degree  # Initialize the degree if not present

    # Sort and get the top 3 prototypes for each region
    top_prototypes_per_section = []
    for counts in region_counts:
        sorted_prototypes = sorted(
            {k: v for k, v in counts.items() if k != "BLACK"}.items(),  # Exclude "BLACK" prototype
            key=lambda item: item[1],  # Sort by degree value
            reverse=True  # Sort in descending order
        )
        top_prototypes_per_section.append([proto for proto, _ in sorted_prototypes[:3]])  # Get top 3

    return top_prototypes_per_section  # Return the top prototypes for each section




#################################################################### MAIN ####################################################################

def main():
    """
    Main function to process images in a directory and output the top 3 prototypes for each region.
    """
    colorspace_name = 'VITA-CLASSICAL-BLACK-2.cns'  # Define the name of the fuzzy color space
    img_dir = os.path.join(".", "imagen_test\\VITA_CLASSICAL")  # Define the directory containing images

    name_colorspace = os.path.splitext(colorspace_name)[0]  # Extract name from file
    extension = os.path.splitext(colorspace_name)[1]  # Extract file extension

    actual_dir = os.getcwd()  # Get the current working directory
    color_space_path = os.path.join(actual_dir, 'fuzzy_color_spaces\\' + colorspace_name)  # Define the path to the color space file
    input_class = Input.instance(extension)  # Initialize the Input class
    color_data = input_class.read_file(color_space_path)  # Read the color space data

    prototypes = []  # List to store the prototypes
    for color_name, color_value in color_data.items():  # Iterate over the color space data
        positive_prototype = color_value['positive_prototype']  # Get the positive prototype
        negative_prototypes = color_value['negative_prototypes']  # Get the negative prototypes
        prototype = Prototype(label=color_name, positive=positive_prototype, negatives=negative_prototypes)  # Create prototype
        prototypes.append(prototype)  # Add the prototype to the list

    fuzzy_color_space = FuzzyColorSpace(space_name=name_colorspace, prototypes=prototypes)  # Create a FuzzyColorSpace object
    color_map = plt.cm.get_cmap('tab20', len(prototypes))  # Define a color map for the prototypes
    prototype_colors = {prototype.label: color_map(i)[:3] for i, prototype in enumerate(prototypes)}  # Map prototypes to colors
    prototype_colors["BLACK"] = (0, 0, 0)  # Assign black color to the "BLACK" prototype

    image_top_prototypes = {}  # Dictionary to store the top prototypes for each image
    for filename in os.listdir(img_dir):  # Loop through the images in the directory
        if filename.endswith(".png"):  # Process only PNG files
            img_path = os.path.join(img_dir, filename)  # Get the full path of the image
            top_prototypes = process_image(img_path, prototypes, fuzzy_color_space, prototype_colors)  # Process the image
            if top_prototypes:
                image_top_prototypes[filename] = top_prototypes  # Store the result

    # Print the results
    print("Top 3 prototypes per section for each image:")
    for image_name, top_prototypes in image_top_prototypes.items():
        print(f"{image_name}: {top_prototypes}")  # Output the top prototypes for each image



if __name__ == "__main__":
    main()  

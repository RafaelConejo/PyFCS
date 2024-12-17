############################################################################################################################################################################################################
# This code processes dental image samples to identify the most dominant color prototypes in three specific vertical sections of the image: the upper third, central third, and lower third. 
# It uses a fuzzy color space model to analyze pixel colors and determine their membership to predefined color prototypes. The main goal is to quantify the presence of color prototypes 
# in these regions to assist in analyzing dental color distributions, such as for shade matching in dentistry.
############################################################################################################################################################################################################

import os
import sys
from skimage import color
import pandas as pd
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

import numpy as np
from skimage import color

def process_image(img_path, fuzzy_color_space):
    """
    Process a tooth image by calculating the top 3 prototypes per section (middle third) based on fuzzy membership values.
    The function will also calculate and normalize the degree of membership for each prototype and return the results
    in a format suitable for saving to Excel.
    
    Parameters:
    img_path (str): Path to the image to be processed.
    fuzzy_color_space (FuzzyColorSpace): The fuzzy color space object used for calculating membership degrees.

    Returns:
    dict: A dictionary with region-wise results, including prototypes and their normalized membership percentages.
    """
    IMG_WIDTH = 308  # Set the desired image width
    IMG_HEIGHT = 448  # Set the desired image height
    image = Utils.image_processing(img_path, IMG_WIDTH, IMG_HEIGHT)  

    if image is None:
        print(f"Failed to load the image {img_path}.")  # Error if image couldn't be loaded
        return None

    lab_image = color.rgb2lab(image)  # Convert the image to LAB color space
    membership_cache = {}  # Cache to store membership values for already processed colors
    region_counts = [{}, {}, {}]  # Store membership degree sums for each region

    # Define the boundaries for the 3x3 divisions
    height_third = image.shape[0] // 3
    width_third = image.shape[1] // 3

    # Define a threshold to exclude pixels close to black in the LAB space
    L_THRESHOLD = 20  # L value threshold for detecting black (lower values represent darker pixels)
    AB_THRESHOLD = 10  # a and b value threshold for detecting black (close to 0)

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

                # Create a mask to exclude pixels close to black
                L, a, b = lab_color
                if L < L_THRESHOLD and abs(a) < AB_THRESHOLD and abs(b) < AB_THRESHOLD:
                    continue  # Skip pixel if it's close to black

                # Check if the color's membership degrees are cached
                if lab_color in membership_cache:
                    membership_degrees = membership_cache[lab_color]  # Use cached values
                else:
                    membership_degrees = fuzzy_color_space.calculate_membership(lab_color)  # Calculate membership
                    membership_cache[lab_color] = membership_degrees  # Cache the result

                # Add the membership degrees to the corresponding region count
                for name, degree in membership_degrees.items():
                    if name in region_counts[region_idx]:
                        region_counts[region_idx][name] += degree  # Accumulate the degree
                    else:
                        region_counts[region_idx][name] = degree  # Initialize the degree if not present

    # Store the results in a format suitable for saving to Excel
    region_results = {}
    for region_idx, counts in enumerate(region_counts):
        # Normalize the membership degrees so they sum to 1
        total_degree = sum(counts.values())
        if total_degree > 0:
            normalized_counts = {k: v / total_degree for k, v in counts.items()}

            # Sort the prototypes by degree, excluding "BLACK"
            sorted_prototypes = sorted(
                {k: v for k, v in normalized_counts.items() if k != "BLACK"}.items(),
                key=lambda item: item[1],  # Sort by degree value
                reverse=True  # Sort in descending order
            )

            # Store the top 3 prototypes and their normalized membership percentage
            region_results[["top", "middle", "bottom"][region_idx]] = [
                (proto, round(degree, 3))  # Store the prototype and its percentage
                for proto, degree in sorted_prototypes[:3]
            ]
        else:
            region_results[["top", "middle", "bottom"][region_idx]] = []  # No valid prototypes

    return region_results  # Return the region results with prototypes and their membership percentages






def process_image_2(img_path, fuzzy_color_space):
    """
    Process a tooth image by excluding pixels with the highest membership in "BLACK" from the top and bottom thirds.
    Then calculate the mean LAB values for each section and compute fuzzy membership degrees for those means.

    Parameters:
    img_path (str): Path to the image to be processed.
    fuzzy_color_space (FuzzyColorSpace): The fuzzy color space object used for calculating membership degrees.

    Returns:
    dict: A dictionary with mean LAB values and membership degrees for each region (top, middle, bottom thirds).
    """
    IMG_WIDTH = 308  # Desired image width
    IMG_HEIGHT = 448  # Desired image height
    image = Utils.image_processing(img_path, IMG_WIDTH, IMG_HEIGHT)

    if image is None:
        print(f"Failed to load the image {img_path}.")
        return None

    lab_image = color.rgb2lab(image)  # Convert the image to LAB color space

    # Define the boundaries for the thirds
    height_third = image.shape[0] // 3
    width_third = lab_image.shape[1] // 3
    regions = {
        "top": lab_image[:height_third, width_third:2 * width_third, :],
        "middle": lab_image[height_third:2 * height_third, width_third:2 * width_third, :],
        "bottom": lab_image[2 * height_third:, width_third:2 * width_third, :]
    }

    results = {
        "top": {},
        "middle": {},
        "bottom": {}
    }

    L_THRESHOLD = 20  # L value threshold for detecting black (lower values represent darker pixels)
    AB_THRESHOLD = 10  # a and b value threshold for detecting black (close to 0)
    for region_name, region_pixels in regions.items():
        region_flat = region_pixels.reshape(-1, 3)  # Flatten the LAB values for easier processing

        if region_name == 'top' or region_name == 'bottom':
            # Create a mask to exclude pixels close to black
            L, a, b = region_flat[:, 0], region_flat[:, 1], region_flat[:, 2]

            # Create a mask for pixels where L is low and a, b are near 0 (close to black)
            black_mask = (L < L_THRESHOLD) & (np.abs(a) < AB_THRESHOLD) & (np.abs(b) < AB_THRESHOLD)

            # Filter out pixels that are close to black
            filtered_pixels = region_flat[~black_mask]

            if filtered_pixels.size == 0:
                print(f"Warning: All pixels excluded in {region_name} region due to BLACK dominance.")
                continue

        else:
            filtered_pixels = region_flat


        # Calculate mean LAB for the remaining pixels
        mean_lab = np.mean(filtered_pixels, axis=0)

        # Compute membership degrees for the mean LAB value
        mean_membership = fuzzy_color_space.calculate_membership(tuple(mean_lab))

        # Save the results for this region, and sort them by degree (descending)
        sorted_membership = sorted(
            ((prototype, degree) for prototype, degree in mean_membership.items() if prototype != "BLACK"),
            key=lambda x: x[1],
            reverse=True
        )

        # Save the results for this region
        for prototype, degree in sorted_membership:
            if prototype != "BLACK":  # Exclude the black prototype
                results[region_name][prototype] = round(degree, 3)  # Round to 3 decimals

    return results


def save_to_excel(results, filename="resultados_prototipos.xlsx"):
    """
    Save the processed results to an Excel file in the required table format.
    
    Parameters:
    results (dict): Dictionary with processed results.
    filename (str): Name of the Excel file to save.
    """
    # Create a list to store the rows for the Excel table
    table_data = []

    for image_path, region_results in results.items():
        row = {"Imagen": image_path.split("\\")[-1]}  # Get the image name (filename)
        for region, prototypes in region_results.items():
            # Store the prototype degrees as a dictionary string in the corresponding region column
            row[region] = str(prototypes)

        table_data.append(row)

    # Convert the table data into a DataFrame
    df = pd.DataFrame(table_data)

    # Save to Excel
    df.to_excel(filename, index=False)
    print(f"Results saved to {filename}")



#################################################################### MAIN ####################################################################

def main():
    """
    Main function to process images in a directory and output the top 3 prototypes for each region.
    1. Top 3 prototypes per region based on fuzzy membership values.
    2. Mean LAB and memberships excluding "BLACK".
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


    print("Choose a processing method:")
    print("1. Top 3 prototypes per section (central column)")
    print("2. Mean LAB and memberships excluding 'BLACK'")
    option = int(input("Enter 1 or 2: "))
    if option == 1:
        # Process using the first method (top prototypes per section)
        image_top_prototypes = {}  # Dictionary to store the top prototypes for each image
        for filename in os.listdir(img_dir):  # Loop through the images in the directory
            if filename.endswith(".png"):  # Process only PNG files
                img_path = os.path.join(img_dir, filename)  # Get the full path of the image
                top_prototypes = process_image(img_path, fuzzy_color_space)  # Process the image
                if top_prototypes:
                    image_top_prototypes[filename] = top_prototypes  # Store the result

        # Print the results
        print("Top 3 prototypes per section for each image:")
        for image_name, top_prototypes in image_top_prototypes.items():
            print(f"{image_name}: {top_prototypes}")  # Output the top prototypes for each image

        # Save the results to an Excel file
        save_to_excel(image_top_prototypes, filename="test_results\\results_opt_1.xlsx")

    elif option == 2:
        all_results = {}  # Dictionary to store results
        
        for filename in os.listdir(img_dir):  # Loop through the images in the directory
            if filename.endswith(".png"):  # Process only PNG files
                img_path = os.path.join(img_dir, filename)  # Get the full path of the image
                region_results = process_image_2(img_path, fuzzy_color_space)  # Process the image
                
                if region_results:
                    # Convert the dictionary to a list of tuples, sorted by the membership values (descending order)
                    formatted_results = {}
                    
                    for region, values in region_results.items():
                        # Sort the dictionary by value in descending order and convert to list of tuples
                        sorted_values = sorted(values.items(), key=lambda x: x[1], reverse=True)
                        formatted_results[region] = sorted_values
                    
                    all_results[filename] = formatted_results  # Add the formatted results for this image

        # Save the results to an Excel file
        save_to_excel(all_results, filename="test_results\\results_opt_2.xlsx")

    else:
        print("Invalid option. Please run the program again and choose either 1 or 2.")



if __name__ == "__main__":
    main()  








# The normalization of the membership degrees is performed by dividing each membership degree by the total sum of the degrees in a region.  
# Given a set of membership degrees \( d_1, d_2, \dots, d_n \) for \( n \) prototypes in a region, the total sum \( S \) of the membership degrees is:

# \[
# S = d_1 + d_2 + \dots + d_n
# \]

# Then, the normalized membership degree for prototype \( i \), denoted as \( d_i^{\text{norm}} \), is calculated using the following formula:

# \[
# d_i^{\text{norm}} = \frac{d_i}{S}
# \]

# where:
# - \( d_i^{\text{norm}} \) is the normalized membership degree of prototype \( i \).
# - \( d_i \) is the original membership degree of prototype \( i \).
# - \( S \) is the total sum of the membership degrees of all prototypes in that region.

# \textbf{Process explanation:}

# \textbf{Sum the membership degrees:} All the membership degrees of the prototypes in the region are summed up.

# \[
# S = \sum_{i=1}^{n} d_i
# \]

# where:
# - \( S \) is the total sum of the membership degrees of the prototypes in the region.
# - \( d_i \) is the membership degree of prototype \( i \).
# - \( n \) is the total number of prototypes in the region.

# \textbf{Normalize each membership degree:} Then, for each prototype, its membership degree is divided by this total sum \( S \). This ensures that the normalized membership degrees sum to 1.

# \[
# d_i^{\text{norm}} = \frac{d_i}{S}
# \]

# where:
# - \( d_i^{\text{norm}} \) is the normalized membership degree of prototype \( i \).
# - \( d_i \) is the original membership degree of prototype \( i \).
# - \( S \) is the total sum of the membership degrees of all prototypes in the region.




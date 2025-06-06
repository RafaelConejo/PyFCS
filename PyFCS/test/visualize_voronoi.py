import os
import sys

# Get the path to the directory containing PyFCS
current_dir = os.path.dirname(__file__)
pyfcs_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))

# Add the PyFCS path to sys.path
sys.path.append(pyfcs_dir)

### my libraries ###
from PyFCS import Input, Prototype, Visual_tools, ReferenceDomain


def main():
    colorspace_name = 'BASIC.cns'


    name_colorspace = os.path.splitext(colorspace_name)[0]
    extension = os.path.splitext(colorspace_name)[1]

    # Step 1: Reading the .cns file using the Input class
    actual_dir = os.getcwd()
    color_space_path = os.path.join(actual_dir, 'fuzzy_color_spaces\\'+colorspace_name)
    input_class = Input.instance(extension)
    color_data = input_class.read_file(color_space_path)


    # Create limits prototypes
    volume_limits = ReferenceDomain(0, 100, -128, 127, -128, 127)


    # Step 2: Creating Prototype objects for each color
    prototypes = []
    for color_name, color_value in color_data.items():
        # Assume that 'color_value' contains the positive prototype and set of negatives
        positive_prototype = color_value['positive_prototype']
        negative_prototypes = color_value['negative_prototypes']

        # Create a Prototype object for each color
        prototype = Prototype(label=color_name, positive=positive_prototype, negatives=negative_prototypes, add_false=True)
        prototypes.append(prototype)


    # Step 3: Visualization of the Voronoi Regions
    Visual_tools.plot_all_prototypes(prototypes, volume_limits)
    # Visual_tools.plot_prototype(prototypes[0], volume_limits)


if __name__ == "__main__":
    main()
from PyFCS.input_output.Input import Input

from skimage import color
import numpy as np

class InputCNS(Input):
    def extract_colors(self, color_value):
        # Extract positive prototype
        positive_prototype = np.array(color_value['positive_prototype'])
        
        # Extract negative prototypes
        negative_prototypes = np.array(color_value['negative_prototypes'])
        
        # Normalize RGB values to range [0, 1] and convert from RGB to LAB
        positive_lab = color.rgb2lab(positive_prototype / 255.0)
        negative_lab = [color.rgb2lab(proto / 255.0) for proto in negative_prototypes]
        
        return positive_lab, negative_lab
    
    def read_file(self, file_path):
        color_data = {
            'color_values': [],
            'color_names': []
        }

        try:
            with open(file_path, 'r') as file:
                lines = file.readlines()

                # Find the line containing '@crispColorSpaceType1000'
                start_index = None
                for i, line in enumerate(lines):
                    if '@crispColorSpaceType1000' in line:
                        start_index = i
                        break

                if start_index is None:
                    raise ValueError("Line '@crispColorSpaceType1000' not found in the file.")

                # Extract crisp color space type
                color_data['crisp_color_space_type'] = int(lines[start_index][22:])

                # Extract the following lines (RGB and color labels)
                unique_lines = set()  # Set to track unique lines

                for i in range(start_index + 1, len(lines)):
                    try:
                        line_content = lines[i].strip()
                        if not line_content:
                            continue  # Ignore empty lines

                        if line_content not in unique_lines:
                            unique_lines.add(line_content)  # Add line to unique lines set

                            if '\t' in line_content:
                                # If it contains a tab, we assume it's an RGB line
                                rgb_values = list(map(float, line_content.split()))
                                color_data['color_values'].append({
                                    'RGB': [rgb_values[0], rgb_values[1], rgb_values[2]],
                                    'positive_prototype': None,
                                    'negative_prototypes': []
                                })
                            else:
                                if not any(char.isdigit() for char in line_content):  # Check if the line does not contain digits
                                    color_data['color_names'].append(line_content)

                    except (ValueError, IndexError):
                        raise ValueError(f"Error processing line {i + 1} in the .cns file.")

                # Set the first color as positive prototype and others as negative prototypes
                for idx, color_value in enumerate(color_data['color_values']):
                    color_data['color_values'][idx]['positive_prototype'] = color_value['RGB']
                    # Assign the other colors as negative prototypes
                    color_data['color_values'][idx]['negative_prototypes'] = [color['RGB'] for other_idx, color in enumerate(color_data['color_values']) if other_idx != idx]


        except (ValueError, IndexError, KeyError) as e:
            raise ValueError(f"Error reading .cns file: {str(e)}")


        for idx, color_value in enumerate(color_data['color_values']):
            # Assign the current color as positive prototype and others as negative prototypes
            color_data['color_values'][idx]['positive_prototype'], color_data['color_values'][idx]['negative_prototypes'] = self.extract_colors(color_value)


        color_data_restructured = {}
        for color_value, color_name in zip(color_data['color_values'], color_data['color_names']):
            color_data_restructured[color_name] = {
                'RGB': color_value['RGB'],
                'positive_prototype': color_value['positive_prototype'],
                'negative_prototypes': color_value['negative_prototypes']
            }

        return color_data_restructured
    


    def write_file(self, file_path):
        pass

    
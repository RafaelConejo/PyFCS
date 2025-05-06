from PyFCS.input_output.Input import Input

from skimage import color
import numpy as np

class InputCNS(Input):

    def write_file(self, file_path):
        pass


    def is_number(self, s):
        try:
            float(s)
            return True
        except ValueError:
            return False
            

    def extract_colors(self, color_value, color_space):
        # Extract positive prototype
        positive_prototype = np.array(color_value['positive_prototype'])
        
        # Extract negative prototypes
        negative_prototypes = np.array(color_value['negative_prototypes'])
        
        if color_space == 'RGB':
            # Normalize RGB values to range [0, 1] and convert from RGB to LAB
            positive_prototype = color.rgb2lab(positive_prototype / 255.0)
            aux_negative = negative_prototypes
            negative_prototypes = [color.rgb2lab(proto / 255.0) for proto in aux_negative]
        
        return positive_prototype, negative_prototypes
    
    
    def read_file(self, file_path):
        color_data = {
            'color_values': [],
            'color_names': []
        }

        try:
            with open(file_path, 'r') as file:
                lines = file.readlines()
                lines_2 = lines.copy()

                # Find the line containing '@colorSpace_'
                start_index = None
                color_space = None
                for i, line in enumerate(lines):
                    if '@colorSpace_' in line:
                        start_index = i
                        color_space = line.split('_')[1].strip()
                        break
                
                if color_space is None:
                    color_space = "RGB"
                    for i, line in enumerate(lines):
                        line_stripped = line.strip()
                        if line_stripped.startswith('#') or not line_stripped:
                            continue  # skip comments
                        if '@crispColorSpaceType' in line_stripped:
                            start_index = i 
                            break

                # Extract number of components and number of cases
                num_components = int(lines[start_index + 1].strip())
                num_cases = int(lines[start_index + 2].strip())

                # Extract the prototypes
                unique_lines = set()  # Set to track unique lines

                for i in range(start_index + 3, len(lines)):
                    try:
                        line_content = lines[i].strip()
                        if not line_content:
                            continue  # Ignore empty lines

                        if line_content not in unique_lines:
                            unique_lines.add(line_content)  # Add line to unique lines set

                            color_val = line_content.split()
                            if len(color_val) == num_components and all(self.is_number(c) for c in color_val):
                                color_val = list(map(float, color_val))
                                color_data['color_values'].append({
                                    'Color': [color_val[0], color_val[1], color_val[2]],
                                    'positive_prototype': None,
                                    'negative_prototypes': []
                                })
                            else:
                                color_data['color_names'].append(line_content)

                    except (ValueError, IndexError):
                        raise ValueError(f"Error processing line {i + 1} in the .cns file.")
                
                # Check if the size of color_values and color_names is the same
                if len(color_data['color_values']) != len(color_data['color_names']):
                    raise ValueError("Mismatch between the number of color values and color names.")

                # Set the first color as positive prototype and others as negative prototypes
                for idx, color_value in enumerate(color_data['color_values']):
                    color_data['color_values'][idx]['positive_prototype'] = color_value['Color']
                    # Assign the other colors as negative prototypes
                    color_data['color_values'][idx]['negative_prototypes'] = [color['Color'] for other_idx, color in enumerate(color_data['color_values']) if other_idx != idx]


        except (ValueError, IndexError, KeyError) as e:
            raise ValueError(f"Error reading .cns file: {str(e)}")

        for idx, color_value in enumerate(color_data['color_values']):
            # Assign the current color as positive prototype and others as negative prototypes
            color_data['color_values'][idx]['positive_prototype'], color_data['color_values'][idx]['negative_prototypes'] = self.extract_colors(color_value, color_space)

        color_data_restructured = {}
        for color_value, color_name in zip(color_data['color_values'], color_data['color_names']):
            color_data_restructured[color_name] = {
                'Color': color_value['Color'],
                'positive_prototype': color_value['positive_prototype'],
                'negative_prototypes': color_value['negative_prototypes']
            }

        return color_data_restructured



    
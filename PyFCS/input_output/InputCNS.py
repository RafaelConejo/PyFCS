from PyFCS.input_output.Input import Input

from skimage import color
import numpy as np

class InputCNS(Input):
    def extract_colors(self, color_value):
        # Extraer el prototipo positivo
        positive_prototype = np.array(color_value['positive_prototype'])
        
        # Extraer los prototipos negativos
        negative_prototypes = np.array(color_value['negative_prototypes'])
        
        # Normalizar los valores RGB al rango [0, 1] y convertir de RGB a LAB
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

                # Buscar la línea que contiene '@crispColorSpaceType1000'
                start_index = None
                for i, line in enumerate(lines):
                    if '@crispColorSpaceType1000' in line:
                        start_index = i
                        break

                if start_index is None:
                    raise ValueError("No se encontró la línea '@crispColorSpaceType1000' en el archivo.")

                # Extraer crisp color space type
                color_data['crisp_color_space_type'] = int(lines[start_index][22:])

                # Extraer las líneas siguientes (RGB y etiquetas de color)
                unique_lines = set()  # Conjunto para rastrear líneas únicas

                for i in range(start_index + 1, len(lines)):
                    try:
                        line_content = lines[i].strip()
                        if not line_content:
                            continue  # Ignorar líneas vacías

                        if line_content not in unique_lines:
                            unique_lines.add(line_content)  # Agregar la línea al conjunto de líneas únicas

                            if '\t' in line_content:
                                # Si contiene una tabulación, asumimos que es una línea RGB
                                rgb_values = list(map(float, line_content.split()))
                                color_data['color_values'].append({
                                    'RGB': [rgb_values[0], rgb_values[1], rgb_values[2]],
                                    'positive_prototype': None,
                                    'negative_prototypes': []
                                })
                            else:
                                if not any(char.isdigit() for char in line_content):  # Verificar si la línea no contiene números
                                    color_data['color_names'].append(line_content)

                    except (ValueError, IndexError):
                        raise ValueError(f"Error al procesar la línea {i + 1} en el archivo .cns.")

                # Establecer el primer color como prototipo positivo y los demás como prototipos negativos
                for idx, color_value in enumerate(color_data['color_values']):
                    color_data['color_values'][idx]['positive_prototype'] = color_value['RGB']
                    # Asignar los demás colores como prototipos negativos
                    color_data['color_values'][idx]['negative_prototypes'] = [color['RGB'] for other_idx, color in enumerate(color_data['color_values']) if other_idx != idx]


        except (ValueError, IndexError, KeyError) as e:
            raise ValueError(f"Error al leer el archivo .cns: {str(e)}")


        for idx, color_value in enumerate(color_data['color_values']):
            # Asignar el color actual como prototipo positivo y los otros como prototipos negativos
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

    
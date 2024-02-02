import cv2
import numpy as np



def read_cns_file(file_path):
    color_data = {}

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

            color_data['representative_values'] = []
            color_data['color_name_labels'] = []

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
                            color_data['representative_values'].append({
                                'R': rgb_values[0],
                                'G': rgb_values[1],
                                'B': rgb_values[2]
                            })
                        else:
                            # Si no contiene una tabulación, asumimos que es una etiqueta de color
                            color_data['color_name_labels'].append(line_content)

                except (ValueError, IndexError):
                    raise ValueError(f"Error al procesar la línea {i + 1} en el archivo .cns.")

    except (ValueError, IndexError, KeyError) as e:
        raise ValueError(f"Error al leer el archivo .cns: {str(e)}")

    return color_data




def image_processing(img_path, IMG_WIDTH, IMG_HEIGHT):
    # Abre la imagen
    imagen = cv2.imread(img_path)
    imagen = cv2.resize(imagen, (IMG_WIDTH, IMG_HEIGHT))
    
    # Convierte la imagen a formato RGB
    imagen = cv2.cvtColor(imagen, cv2.COLOR_BGR2RGB)
    
    # Normaliza la imagen
    imagen = imagen.astype(np.float32) / 255.0
    
    return imagen



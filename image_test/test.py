import os
import cv2
import numpy as np

input_folder = r"C:\Users\rafav\Desktop\PYFCS\image_test\VITA_CLASSICAL"
output_folder = os.path.join(input_folder, "transparent_background_safe_v2")
mask_folder = os.path.join(output_folder, "masks")

os.makedirs(output_folder, exist_ok=True)
os.makedirs(mask_folder, exist_ok=True)

valid_ext = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")


def keep_largest_component(mask):
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)

    if num_labels <= 1:
        return mask

    largest_label = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
    return np.where(labels == largest_label, 255, 0).astype(np.uint8)


def segment_tooth_conservative(image_bgr):
    """
    Conservative segmentation for teeth over dark backgrounds.
    Prioritizes avoiding background inclusion over preserving every border pixel.
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    # Threshold seguro: el fondo es negro/gris oscuro, el diente es claro.
    # Puedes subirlo a 45 o 50 si aún entra fondo negro.
    threshold_value = 90
    mask = np.where(gray > threshold_value, 255, 0).astype(np.uint8)

    # Limpiar ruido pequeño
    kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_open)

    # Quedarse solo con el diente principal
    mask = keep_largest_component(mask)

    # Cerrar pequeños huecos internos sin expandir demasiado
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close)

    # Volver a quedarse con el componente principal
    mask = keep_largest_component(mask)

    # Erosión conservadora para quitar borde contaminado con sombra/fondo
    kernel_erode = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.erode(mask, kernel_erode, iterations=1)

    # Máscara dura: alfa solo 0 o 255
    alpha = mask.copy()

    # RGB de los píxeles transparentes en blanco para evitar halos negros en visores
    result_bgr = image_bgr.copy()
    result_bgr[alpha == 0] = [255, 255, 255]

    b, g, r = cv2.split(result_bgr)
    result_bgra = cv2.merge((b, g, r, alpha))

    return result_bgra, mask


for filename in os.listdir(input_folder):
    if not filename.lower().endswith(valid_ext):
        continue

    input_path = os.path.join(input_folder, filename)
    image = cv2.imread(input_path, cv2.IMREAD_COLOR)

    if image is None:
        print(f"No se pudo leer: {filename}")
        continue

    result_bgra, mask = segment_tooth_conservative(image)

    base_name = os.path.splitext(filename)[0]

    output_path = os.path.join(output_folder, base_name + ".png")
    mask_path = os.path.join(mask_folder, base_name + "_mask.png")

    cv2.imwrite(output_path, result_bgra)
    cv2.imwrite(mask_path, mask)

    print(f"Guardado: {output_path}")
    print(f"Máscara:  {mask_path}")

print("\nProceso completado.")
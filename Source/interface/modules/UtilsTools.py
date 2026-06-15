import os
import sys
import numpy as np
from skimage import color
import tkinter as tk
from tkinter import ttk, filedialog
import colorsys

### my libraries ###
from Source.input_output.Input import Input
from Source.geometry.Prototype import Prototype

"""
Utility functions for PyFCS

This module provides a collection of helper functions used across the PyFCS
application. It includes:
- Path resolution that works both for .py execution and frozen .exe builds.
- Color space conversions (RGB, HSV, LAB, sRGB, HEX).
- File selection dialogs and popup window utilities for the GUI.
- Helper routines to process color prototypes and load color data from files.

Overall, this module acts as a shared toolbox for GUI handling, color conversion,
and data preparation.
"""


# ============================================================================================================================================================
#  PATH HELPERS
# ============================================================================================================================================================

def get_base_path():
    """
    Return the base directory of the application.

    Behavior depends on how the application is executed:
    - When running as a .py file -> returns the project root directory.
    - When running as a frozen .exe, e.g. via PyInstaller -> returns the
      directory containing the executable.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)

    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )


# ============================================================================================================================================================
#  SAFE TEXT / NUMBER HELPERS
# ============================================================================================================================================================

def safe_text(value):
    """
    Safely convert any value to stripped text.
    """
    try:
        if value is None:
            return ""
        return str(value).strip()
    except Exception:
        return ""


def is_plain_rgb_integer(text):
    """
    Check if a text represents a plain RGB integer.

    Accepted:
        0, 12, 255, +12

    Rejected:
        a, 1a, 12.5, 12,5, nan, inf, empty
    """
    text = safe_text(text)

    if not text:
        return False

    if text.startswith("+"):
        text = text[1:]

    return text.isdigit()


def is_plain_lab_number(text):
    """
    Check if a text represents a finite LAB number.

    Accepted:
        12
        12.5
        -12.5
        +12.5
        .5
        12.

    Rejected:
        a
        1a
        --
        .
        -.
        nan
        inf
        1e999
    """
    text = safe_text(text)

    if not text:
        return False

    lowered = text.lower()

    if lowered in (
        "nan",
        "+nan",
        "-nan",
        "inf",
        "+inf",
        "-inf",
        "infinity",
        "+infinity",
        "-infinity",
    ):
        return False

    if "e" in lowered:
        return False

    if text.startswith(("+", "-")):
        text = text[1:]

    if not text:
        return False

    if text.count(".") > 1:
        return False

    parts = text.split(".")

    if len(parts) == 1:
        return parts[0].isdigit()

    left, right = parts

    if left == "" and right == "":
        return False

    if left and not left.isdigit():
        return False

    if right and not right.isdigit():
        return False

    return True


def safe_float(text):
    """
    Safely convert text to finite float.
    Returns None if conversion is not possible.
    """
    text = safe_text(text).replace(",", ".")

    if not is_plain_lab_number(text):
        return None

    try:
        value = float(text)
    except Exception:
        return None

    try:
        if not np.isfinite(value):
            return None
    except Exception:
        return None

    return value


# ============================================================================================================================================================
#  VALIDATION HELPERS
# ============================================================================================================================================================

def safe_rgb_tuple(rgb):
    """
    Convert any RGB-like object into a safe integer RGB tuple in [0, 255].
    Raises ValueError if conversion is not possible.
    """
    try:
        if rgb is None:
            raise ValueError("RGB value is None.")

        if len(rgb) != 3:
            raise ValueError("RGB value must contain exactly 3 components.")

        r = float(rgb[0])
        g = float(rgb[1])
        b = float(rgb[2])

        if not np.isfinite(r) or not np.isfinite(g) or not np.isfinite(b):
            raise ValueError("RGB values must be finite.")

        r = int(round(r))
        g = int(round(g))
        b = int(round(b))

        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))

        return (r, g, b)

    except Exception as exc:
        raise ValueError("Invalid RGB tuple.") from exc


def safe_lab_tuple(lab):
    """
    Convert any LAB-like object into a safe finite LAB tuple.
    Raises ValueError if conversion is not possible.
    """
    try:
        if lab is None:
            raise ValueError("LAB value is None.")

        if len(lab) != 3:
            raise ValueError("LAB value must contain exactly 3 components.")

        L = float(lab[0])
        a = float(lab[1])
        b = float(lab[2])

        if not np.isfinite(L) or not np.isfinite(a) or not np.isfinite(b):
            raise ValueError("LAB values must be finite.")

        return (L, a, b)

    except Exception as exc:
        raise ValueError("Invalid LAB tuple.") from exc


def is_valid_rgb(rgb):
    """
    Return True if rgb is a valid RGB tuple in [0, 255].
    """
    try:
        if rgb is None or len(rgb) != 3:
            return False

        for value in rgb:
            value = float(value)

            if not np.isfinite(value):
                return False

            if value < 0 or value > 255:
                return False

        return True

    except Exception:
        return False


def is_valid_lab(lab):
    """
    Return True if lab is a valid LAB tuple in the expected application range.
    """
    try:
        L, a, b = safe_lab_tuple(lab)

        return 0 <= L <= 100 and -128 <= a <= 127 and -128 <= b <= 127

    except Exception:
        return False


def is_valid_hex(hex_value):
    """
    Return True if hex_value is #RRGGBB or RRGGBB.
    """
    try:
        text = safe_text(hex_value).upper()

        if text.startswith("#"):
            text = text[1:]

        if len(text) != 6:
            return False

        allowed = set("0123456789ABCDEF")

        return all(ch in allowed for ch in text)

    except Exception:
        return False


# ============================================================================================================================================================
#  COLOR CONVERSIONS
# ============================================================================================================================================================

def rgb_to_hex(rgb):
    """
    Convert an RGB tuple (0-255) into a hexadecimal color string.

    Parameters
    ----------
    rgb : tuple
        (R, G, B) values in the range [0, 255].

    Returns
    -------
    str
        Hex color string in the form '#rrggbb'.
    """
    r, g, b = safe_rgb_tuple(rgb)

    return "#{:02x}{:02x}{:02x}".format(r, g, b)


def hex_to_rgb(hex_value):
    """
    Convert HEX color to RGB tuple.

    Accepted formats:
        #RRGGBB
        RRGGBB

    Returns
    -------
    tuple
        (R, G, B) values in [0, 255].
    """
    text = safe_text(hex_value).upper()

    if text.startswith("#"):
        text = text[1:]

    if not is_valid_hex(text):
        raise ValueError("HEX value must be #RRGGBB or RRGGBB.")

    return (
        int(text[0:2], 16),
        int(text[2:4], 16),
        int(text[4:6], 16),
    )


def hsv_to_rgb(h, s, v):
    """
    Convert HSV values to RGB.

    Parameters
    ----------
    h, s, v : float
        Hue, saturation, and value components expected in [0, 1].

    Returns
    -------
    tuple
        (R, G, B) values scaled to the range [0, 255].
    """
    r, g, b = colorsys.hsv_to_rgb(h, s, v)

    return (
        int(round(r * 255)),
        int(round(g * 255)),
        int(round(b * 255)),
    )


def lab_to_rgb(lab):
    """
    Convert LAB color values to RGB.

    Parameters
    ----------
    lab : dict or iterable
        Either a dictionary with keys {'L', 'A', 'B'} or an iterable (L, a, b).

    Returns
    -------
    tuple
        (R, G, B) integer values clipped to [0, 255].
    """
    if isinstance(lab, dict):
        lab_array = np.array([[lab["L"], lab["A"], lab["B"]]], dtype=float)
    else:
        lab_array = np.array([lab], dtype=float)

    rgb_float = color.lab2rgb(lab_array)[0]
    rgb_float = np.clip(rgb_float, 0, 1)

    rgb = tuple(int(round(x * 255)) for x in rgb_float)

    return rgb


def srgb_to_lab(r, g, b):
    """
    Convert sRGB values to CIELAB using manual linearization and XYZ conversion.

    Parameters
    ----------
    r, g, b : int
        sRGB channel values in the range [0, 255].

    Returns
    -------
    tuple
        (L, a, b) values in CIELAB space.
    """
    r, g, b = safe_rgb_tuple((r, g, b))

    def inv_gamma(u):
        u = u / 255.0
        return u / 12.92 if u <= 0.04045 else ((u + 0.055) / 1.055) ** 2.4

    R = inv_gamma(r)
    G = inv_gamma(g)
    B = inv_gamma(b)

    # Linear RGB to XYZ, D65
    X = R * 0.4124564 + G * 0.3575761 + B * 0.1804375
    Y = R * 0.2126729 + G * 0.7151522 + B * 0.0721750
    Z = R * 0.0193339 + G * 0.1191920 + B * 0.9503041

    # D65 reference white
    Xn, Yn, Zn = 0.95047, 1.00000, 1.08883

    x = X / Xn
    y = Y / Yn
    z = Z / Zn

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else (7.787 * t + 16 / 116)

    fx, fy, fz = f(x), f(y), f(z)

    L = 116 * fy - 16
    a = 500 * (fx - fy)
    bb = 200 * (fy - fz)

    return (L, a, bb)


def rgb_to_lab(rgb):
    """
    Convert RGB tuple to LAB.
    """
    r, g, b = safe_rgb_tuple(rgb)

    return srgb_to_lab(r, g, b)


def hex_to_lab(hex_value):
    """
    Convert HEX color to LAB.
    """
    r, g, b = hex_to_rgb(hex_value)

    return srgb_to_lab(r, g, b)


def lab_to_hex(lab):
    """
    Convert LAB color to HEX.
    """
    rgb = lab_to_rgb(lab)

    return rgb_to_hex(rgb)





# ============================================================================================================================================================
#  EXTENDED COLOR SPACE DISPLAY HELPERS
# ============================================================================================================================================================

SUPPORTED_COLOR_VALUE_SPACES = [
    "CIELAB",
    "RGB",
    "HEX",
    "CIELUV",
    "LCh",
    "CIE1931",
]


def get_supported_color_value_spaces():
    """
    Return the color value spaces available for GUI display.
    """
    return list(SUPPORTED_COLOR_VALUE_SPACES)


def normalize_color_value_space(color_space):
    """
    Normalize color space names used by the GUI.

    Accepted canonical names:
    - CIELAB
    - RGB
    - HEX
    - CIELUV
    - LCh
    - CIE1931
    """
    text = safe_text(color_space).replace(" ", "").upper()

    aliases = {
        "LAB": "CIELAB",
        "CIELAB": "CIELAB",

        "RGB": "RGB",
        "SRGB": "RGB",

        "HEX": "HEX",

        "LUV": "CIELUV",
        "CIELUV": "CIELUV",

        "LCH": "LCh",
        "CIELCH": "LCh",
        "CIELCHAB": "LCh",

        "CIE1931": "CIE1931",
        "XYZ": "CIE1931",
        "XYY": "CIE1931",
    }

    return aliases.get(text, "CIELAB")


def lab_to_xyz(lab):
    """
    Convert CIELAB to CIE XYZ using skimage.

    Returns
    -------
    tuple
        (X, Y, Z), using the same reference white convention as skimage.
    """
    L, a, b = safe_lab_tuple(lab)

    lab_array = np.array([[L, a, b]], dtype=float)
    xyz = color.lab2xyz(lab_array)[0]

    return tuple(float(v) for v in xyz)


def lab_to_cieluv(lab):
    """
    Convert CIELAB to CIELUV.

    Returns
    -------
    tuple
        (L*, u*, v*)
    """
    xyz = lab_to_xyz(lab)

    xyz_array = np.array([xyz], dtype=float)
    luv = color.xyz2luv(xyz_array)[0]

    return tuple(float(v) for v in luv)


def lab_to_lch(lab):
    """
    Convert CIELAB to cylindrical CIELCh(ab).

    Returns
    -------
    tuple
        (L*, C*, h°)
    """
    L, a, b = safe_lab_tuple(lab)

    lab_array = np.array([[L, a, b]], dtype=float)
    lch = color.lab2lch(lab_array)[0]

    L_value = float(lch[0])
    C_value = float(lch[1])
    h_degrees = float(np.degrees(lch[2]) % 360.0)

    return (L_value, C_value, h_degrees)


def lab_to_cie1931(lab):
    """
    Convert CIELAB to CIE 1931 xyY.

    Returns
    -------
    tuple
        (x, y, Y)

    Notes
    -----
    CIE1931 is displayed as chromaticity coordinates x, y plus luminance Y.
    """
    X, Y, Z = lab_to_xyz(lab)

    denominator = X + Y + Z

    if abs(denominator) < 1e-12:
        return (0.0, 0.0, float(Y))

    x = X / denominator
    y = Y / denominator

    return (float(x), float(y), float(Y))


def lab_to_color_value(lab, color_space="CIELAB"):
    """
    Convert a CIELAB color to the requested display color space.

    Parameters
    ----------
    lab : iterable
        LAB input color.
    color_space : str
        One of: CIELAB, RGB, HEX, CIELUV, LCh, CIE1931.

    Returns
    -------
    tuple or str
        Converted color value.
    """
    space = normalize_color_value_space(color_space)

    if space == "CIELAB":
        return safe_lab_tuple(lab)

    if space == "RGB":
        return safe_rgb_tuple(lab_to_rgb(lab))

    if space == "HEX":
        return rgb_to_hex(lab_to_rgb(lab)).upper()

    if space == "CIELUV":
        return lab_to_cieluv(lab)

    if space == "LCh":
        return lab_to_lch(lab)

    if space == "CIE1931":
        return lab_to_cie1931(lab)

    return safe_lab_tuple(lab)


def format_lab_color_value(lab, color_space="CIELAB"):
    """
    Convert and format a CIELAB color for compact GUI display.
    """
    try:
        space = normalize_color_value_space(color_space)
        value = lab_to_color_value(lab, space)

        if space == "CIELAB":
            L, a, b = value
            return f"L*={L:.2f}, a*={a:.2f}, b*={b:.2f}"

        if space == "RGB":
            r, g, b = value
            return f"{int(r)}, {int(g)}, {int(b)}"

        if space == "HEX":
            return str(value).upper()

        if space == "CIELUV":
            L, u, v = value
            return f"L*={L:.2f}, u*={u:.2f}, v*={v:.2f}"

        if space == "LCh":
            L, C, h = value
            return f"L*={L:.2f}, C*={C:.2f}, h={h:.2f}°"

        if space == "CIE1931":
            x, y, Y = value
            return f"x={x:.4f}, y={y:.4f}, Y={Y:.4f}"

        return "-"

    except Exception:
        return "-"



# ============================================================================================================================================================
#  FILE SELECTION
# ============================================================================================================================================================

def prompt_file_selection(initial_subdir, parent=None):
    """
    Prompt the user to select a file using a file dialog.

    Parameters
    ----------
    initial_subdir : str
        Subdirectory relative to the application base path used as
        the initial directory in the dialog.
    parent : tk widget, optional
        Parent window so the dialog is attached to it.

    Returns
    -------
    str
        Full path to the selected file, or an empty string if cancelled.
    """
    base_path = get_base_path()
    initial_directory = os.path.join(base_path, initial_subdir)

    filetypes = [("All Files", "*.*")]

    return filedialog.askopenfilename(
        title="Select Fuzzy Color Space File",
        initialdir=initial_directory,
        filetypes=filetypes,
        parent=parent
    )


# ============================================================================================================================================================
#  COLOR DATA HELPERS
# ============================================================================================================================================================

def process_prototypes(color_data):
    """
    Create Prototype objects from parsed color data.

    Parameters
    ----------
    color_data : dict
        Dictionary mapping color names to their data, including
        'positive_prototype' and 'negative_prototypes'.

    Returns
    -------
    list
        List of Prototype instances.
    """
    prototypes = []

    for color_name, color_value in color_data.items():
        positive_prototype = color_value["positive_prototype"]
        negative_prototypes = color_value["negative_prototypes"]

        prototype = Prototype(
            label=color_name,
            positive=positive_prototype,
            negatives=negative_prototypes
        )
        prototypes.append(prototype)

    return prototypes


def load_color_data(file_path):
    """
    Load color data from a .cns file and convert LAB values to RGB.

    Parameters
    ----------
    file_path : str
        Path to the .cns file.

    Returns
    -------
    dict
        Dictionary mapping color names to:
        {
            "rgb": (R, G, B),
            "lab": LAB array
        }
    """
    input_class = Input.instance(".cns")
    color_data = input_class.read_file(file_path)

    colors = {}

    for color_name, color_value in color_data.items():
        lab = np.array(color_value["positive_prototype"], dtype=float)
        rgb = lab_to_rgb(lab)

        colors[color_name] = {
            "rgb": rgb,
            "lab": lab
        }

    return colors


# ============================================================================================================================================================
#  POPUP HELPERS
# ============================================================================================================================================================

def create_popup_window(parent, title, width, height, header_text):
    """
    Create a popup window with a header and a scrollable content area.

    Parameters
    ----------
    parent : tk.Widget
        Parent window.
    title : str
        Title of the popup window.
    width : int
        Width of the popup window.
    height : int
        Height of the popup window.
    header_text : str
        Text displayed at the top of the popup.

    Returns
    -------
    (tk.Toplevel, ttk.Frame)
        The popup window and the scrollable frame where content can be added.
    """
    popup = tk.Toplevel(parent)
    popup.title(title)
    popup.geometry(f"{width}x{height}")
    popup.configure(bg="#f5f5f5")

    tk.Label(
        popup,
        text=header_text,
        font=("Helvetica", 14, "bold"),
        bg="#f5f5f5"
    ).pack(pady=15)

    frame_container = ttk.Frame(popup)
    frame_container.pack(pady=10, fill="both", expand=True)

    canvas = tk.Canvas(frame_container, bg="#f5f5f5")
    scrollbar = ttk.Scrollbar(
        frame_container,
        orient="vertical",
        command=canvas.yview
    )
    scrollable_frame = ttk.Frame(canvas)

    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    return popup, scrollable_frame


def create_selection_popup(parent, title, width, height, items):
    """
    Create a popup window containing a listbox for item selection.

    Parameters
    ----------
    parent : tk.Widget
        Parent window.
    title : str
        Title of the popup.
    width : int
        Width of the popup window.
    height : int
        Height of the popup window.
    items : list
        List of items to display in the listbox.

    Returns
    -------
    (tk.Toplevel, tk.Listbox)
        The popup window and the listbox widget.
    """
    popup = tk.Toplevel(parent)
    popup.title(title)
    popup.geometry(f"{width}x{height}")
    popup.resizable(False, False)

    listbox = tk.Listbox(popup, width=40, height=10)

    for item in items:
        listbox.insert(tk.END, item)

    listbox.pack(pady=10)

    popup.transient(parent)
    popup.grab_set()

    return popup, listbox


def handle_image_selection(event, listbox, popup, images_names, callback):
    """
    Handle the selection of an image from a listbox.

    This function:
    - Retrieves the selected filename.
    - Resolves it to the corresponding image ID.
    - Closes the popup window.
    - Calls the provided callback with the selected image ID.
    """
    selected_index = listbox.curselection()

    if not selected_index:
        return

    selected_filename = listbox.get(selected_index)

    selected_img_id = next(
        img_id
        for img_id, fname in images_names.items()
        if os.path.basename(fname) == selected_filename
    )

    popup.destroy()

    callback(selected_img_id)


# ============================================================================================================================================================
#  ALPHA / PIL IMAGE HELPERS
# ============================================================================================================================================================

def _get_alpha_mask_from_pil(pil_img):
    """
    Returns a boolean mask where True means valid visible pixel.
    If the image has no alpha channel, all pixels are valid.
    """
    if pil_img.mode == "RGBA":
        alpha = np.array(pil_img.getchannel("A"))
        return alpha > 0

    return np.ones((pil_img.height, pil_img.width), dtype=bool)


def _pil_rgb_for_processing(pil_img):
    """
    Returns an RGB version for LAB processing.
    Transparent pixels are kept as RGB but will be ignored using the alpha mask.
    """
    return pil_img.convert("RGB")


def _apply_alpha_to_gray_array(gray_array, valid_mask):
    """
    Converts a grayscale array into RGBA, using valid_mask as alpha.
    Transparent pixels get alpha 0.
    """
    gray = gray_array.astype(np.uint8)

    rgba = np.zeros((gray.shape[0], gray.shape[1], 4), dtype=np.uint8)
    rgba[..., 0] = gray
    rgba[..., 1] = gray
    rgba[..., 2] = gray
    rgba[..., 3] = np.where(valid_mask, 255, 0).astype(np.uint8)

    return rgba


def _apply_alpha_to_rgb_array(rgb_array, valid_mask):
    """
    Converts an RGB array into RGBA, using valid_mask as alpha.
    Transparent pixels get alpha 0.
    """
    rgb = rgb_array.astype(np.uint8)

    rgba = np.zeros((rgb.shape[0], rgb.shape[1], 4), dtype=np.uint8)
    rgba[..., :3] = rgb
    rgba[..., 3] = np.where(valid_mask, 255, 0).astype(np.uint8)

    return rgba
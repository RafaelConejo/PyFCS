import os
import sys
import tempfile
import numpy as np
from skimage import color
import tkinter as tk
from tkinter import ttk, filedialog
import colorsys

### my libraries ###
from Source.input_output.Input import Input
from Source.geometry.Prototype import Prototype
from Source.geometry.Voronoi import Voronoi
from Source.colorspace.ReferenceDomain import ReferenceDomain

# ============================================================================================================================================================
#  SHARED CONSTANTS
# ============================================================================================================================================================

MAX_COLOR_NAME_CHARS = 24

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
    Return the writable/application base directory.

    - Source execution: project root.
    - Frozen PyInstaller build: directory containing the executable.

    This function is intentionally different from :func:`get_resource_path`:
    bundled read-only resources in a one-file build live under ``sys._MEIPASS``
    and must not be treated as the normal user/application data directory.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))

    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )


def get_resource_path(relative_path):
    """
    Resolve a PyFCS read-only resource in both source and frozen builds.

    Resolution order
    ----------------
    Source execution
        ``<project root>/<relative_path>``.  This preserves the normal
        ``Source/external`` development layout on Windows, Linux and macOS.

    Frozen PyInstaller execution
        1. ``<executable dir>/<relative_path>`` if it exists.  This is an
           optional external override, useful for development/debug builds.
        2. ``sys._MEIPASS/<relative_path>`` for resources bundled inside the
           executable/app by PyInstaller.

    The external override means a packaged PyFCS can still be run with an
    explicit ``Source/external`` folder if desired, while a normal release can
    remain a true single-file application.
    """
    relative_path = os.path.normpath(str(relative_path))

    if os.path.isabs(relative_path):
        return relative_path

    app_candidate = os.path.join(get_base_path(), relative_path)

    if not getattr(sys, "frozen", False):
        return app_candidate

    # Optional resource override beside the frozen executable.
    if os.path.exists(app_candidate):
        return app_candidate

    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        bundled_candidate = os.path.join(bundle_root, relative_path)
        if os.path.exists(bundled_candidate):
            return bundled_candidate
        # Return the expected bundled location so any later FileNotFoundError
        # clearly points to the missing packaged resource.
        return bundled_candidate

    return app_candidate


def get_runtime_temp_dir(*parts, create=True):
    """
    Return a writable directory for temporary PyFCS runtime files.

    Source execution keeps runtime artifacts under ``Source/external/temp``.
    Frozen builds use the operating system's temp directory so a one-file
    executable never needs an external Source folder.

    Parameters
    ----------
    *parts : str
        Optional path components below the PyFCS runtime-temp root.
    create : bool, optional
        Create the directory immediately. Set to ``False`` when the caller
        only needs the target path and wants to create it lazily on first use.
    """
    if getattr(sys, "frozen", False):
        base_dir = os.path.join(tempfile.gettempdir(), "PyFCS")
    else:
        base_dir = os.path.join(get_base_path(), "Source", "external", "temp")

    path = os.path.join(base_dir, *[str(part) for part in parts if part])
    if create:
        os.makedirs(path, exist_ok=True)
    return path


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
#  COLOR NAME HELPERS
# ============================================================================================================================================================

def make_unique_color_name(base, existing_names):
    """
    Return a unique color name using the PyFCS naming convention.

    Examples
    --------
    Custom Color
    Custom Color 2
    Custom Color 3
    """
    base = str(base or "Color").strip() or "Color"
    existing = set(existing_names or [])

    if base not in existing:
        return base

    index = 2
    while f"{base} {index}" in existing:
        index += 1

    return f"{base} {index}"


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
    """Return True when LAB lies inside the shared PyFCS reference domain."""
    try:
        L, a, b = safe_lab_tuple(lab)
        return ReferenceDomain.is_valid_lab_values(L, a, b)
    except Exception:
        return False


def find_duplicate_lab_name(color_data, lab, atol=Voronoi.DEFAULT_MERGE_EPS):
    """Return the label of an existing numerically identical LAB prototype."""
    target = np.asarray(lab, dtype=np.float64).reshape(-1)
    if target.size != 3:
        return None

    for name, data in (color_data or {}).items():
        values = data.get("positive_prototype", data.get("Color"))
        if values is None:
            continue

        current = np.asarray(values, dtype=np.float64).reshape(-1)
        if current.size != 3:
            continue

        if np.linalg.norm(current - target) <= atol:
            return name

    return None



def find_duplicate_lab_pairs(color_data, atol=Voronoi.DEFAULT_MERGE_EPS):
    """
    Return every pair of LAB prototypes that collide within the Voronoi
    merge tolerance.

    Parameters
    ----------
    color_data : dict
        Mapping from color name to any LAB-like 3-component value.
    atol : float, optional
        Absolute Euclidean tolerance used to consider two Voronoi sites
        coincident. By default this is exactly Voronoi.DEFAULT_MERGE_EPS.

    Returns
    -------
    list
        Tuples ``(name_a, name_b, lab)`` for each colliding pair. ``lab`` is
        a copy of the first prototype position as a NumPy array.
    """
    items = []

    for name, lab in (color_data or {}).items():
        try:
            values = np.asarray(lab, dtype=np.float64).reshape(-1)
        except Exception:
            continue

        if values.size < 3:
            continue

        values = values[:3]
        if not np.all(np.isfinite(values)):
            continue

        items.append((name, values))

    duplicates = []

    for i in range(len(items)):
        name_a, lab_a = items[i]

        for j in range(i + 1, len(items)):
            name_b, lab_b = items[j]

            if np.linalg.norm(lab_a - lab_b) <= float(atol):
                duplicates.append(
                    (name_a, name_b, lab_a.copy())
                )

    return duplicates



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
#  LAB FILTER HELPERS
# ============================================================================================================================================================

_LAB_FILTER_LABELS = {
    "L_min": "L* minimum",
    "L_max": "L* maximum",
    "a_min": "a* minimum",
    "a_max": "a* maximum",
    "b_min": "b* minimum",
    "b_max": "b* maximum",
}


def read_lab_filter_bindings(filter_bindings, strict=False):
    """
    Read the enabled LAB limits stored in Tk variable bindings.

    Parameters
    ----------
    filter_bindings : dict
        Mapping such as:
            {
                "L_min": (enabled_var, value_var),
                "L_max": (enabled_var, value_var),
                ...
            }
    strict : bool, optional
        When True, an invalid enabled value or an inverted min/max range raises
        ValueError. When False, invalid entries are ignored.

    Returns
    -------
    dict
        Active numeric limits keyed by L_min, L_max, a_min, a_max, b_min,
        and b_max.
    """
    values = {}

    for key, pair in (filter_bindings or {}).items():
        try:
            enabled_var, value_var = pair
            enabled = bool(enabled_var.get())
        except Exception:
            if strict:
                raise ValueError(f"Invalid filter binding for {key}.")
            continue

        if not enabled:
            continue

        try:
            raw = str(value_var.get()).strip().replace(",", ".")
            value = float(raw)
            if not np.isfinite(value):
                raise ValueError
        except Exception:
            if strict:
                label = _LAB_FILTER_LABELS.get(key, str(key))
                raise ValueError(f"Enter a valid numeric value for {label}.")
            continue

        values[key] = float(value)

    if strict:
        for component, low_key, high_key in (
            ("L*", "L_min", "L_max"),
            ("a*", "a_min", "a_max"),
            ("b*", "b_min", "b_max"),
        ):
            low = values.get(low_key)
            high = values.get(high_key)

            if low is not None and high is not None and low > high:
                raise ValueError(
                    f"{component} minimum cannot be greater than its maximum."
                )

    return values


def format_lab_filters(filters, prefix=False):
    """
    Format active LAB limits for compact GUI display.
    """
    filters = dict(filters or {})
    parts = []

    if "L_min" in filters:
        parts.append(f"L* ≥ {float(filters['L_min']):.2f}")
    if "L_max" in filters:
        parts.append(f"L* ≤ {float(filters['L_max']):.2f}")
    if "a_min" in filters:
        parts.append(f"a* ≥ {float(filters['a_min']):.2f}")
    if "a_max" in filters:
        parts.append(f"a* ≤ {float(filters['a_max']):.2f}")
    if "b_min" in filters:
        parts.append(f"b* ≥ {float(filters['b_min']):.2f}")
    if "b_max" in filters:
        parts.append(f"b* ≤ {float(filters['b_max']):.2f}")

    if not parts:
        return "No filters applied"

    body = " · ".join(parts)
    return f"Filters: {body}" if prefix else body


def lab_passes_filters(lab, filters):
    """
    Return True when one LAB color satisfies every active limit.
    """
    filters = dict(filters or {})

    if not filters:
        return True

    try:
        L, a, b = safe_lab_tuple(lab)
    except Exception:
        return False

    if "L_min" in filters and L < float(filters["L_min"]):
        return False
    if "L_max" in filters and L > float(filters["L_max"]):
        return False
    if "a_min" in filters and a < float(filters["a_min"]):
        return False
    if "a_max" in filters and a > float(filters["a_max"]):
        return False
    if "b_min" in filters and b < float(filters["b_min"]):
        return False
    if "b_max" in filters and b > float(filters["b_max"]):
        return False

    return True


def mean_rgb_with_lab_filters(rgb_pixels, filters, chunk_size=250000):
    """
    Return the RGB mean of pixels that satisfy the active LAB filters.

    The RGB-to-LAB conversion is vectorized and processed in chunks, avoiding
    one very large temporary LAB array for large ROIs.

    Returns
    -------
    (numpy.ndarray or None, int)
        Mean RGB vector and number of accepted pixels. If no pixel survives
        the active filters, returns ``(None, 0)``.
    """
    try:
        pixels = np.asarray(rgb_pixels, dtype=np.float32).reshape(-1, 3)
    except Exception:
        return None, 0

    total = int(pixels.shape[0])
    if total == 0:
        return None, 0

    finite_mask = np.all(np.isfinite(pixels), axis=1)
    if not np.all(finite_mask):
        pixels = pixels[finite_mask]
        total = int(pixels.shape[0])

        if total == 0:
            return None, 0

    filters = dict(filters or {})

    # Preserve the original fast path when no filtering is enabled.
    if not filters:
        return np.mean(pixels, axis=0), total

    chunk_size = max(1, int(chunk_size))
    rgb_sum = np.zeros(3, dtype=np.float64)
    used_count = 0

    for start in range(0, total, chunk_size):
        chunk = pixels[start:start + chunk_size]

        # skimage expects sRGB values normalized to [0, 1].
        normalized = np.clip(chunk / 255.0, 0.0, 1.0)
        lab_chunk = color.rgb2lab(
            normalized.reshape(-1, 1, 3)
        ).reshape(-1, 3)

        mask = np.ones(lab_chunk.shape[0], dtype=bool)
        L = lab_chunk[:, 0]
        a = lab_chunk[:, 1]
        b = lab_chunk[:, 2]

        if "L_min" in filters:
            mask &= L >= float(filters["L_min"])
        if "L_max" in filters:
            mask &= L <= float(filters["L_max"])
        if "a_min" in filters:
            mask &= a >= float(filters["a_min"])
        if "a_max" in filters:
            mask &= a <= float(filters["a_max"])
        if "b_min" in filters:
            mask &= b >= float(filters["b_min"])
        if "b_max" in filters:
            mask &= b <= float(filters["b_max"])

        if np.any(mask):
            accepted = chunk[mask]
            rgb_sum += np.sum(accepted, axis=0, dtype=np.float64)
            used_count += int(accepted.shape[0])

    if used_count == 0:
        return None, 0

    return rgb_sum / float(used_count), used_count


def open_lab_filters_dialog(
    parent,
    filter_bindings,
    on_apply=None,
    on_close=None,
    warning_callback=None,
    description=None,
    theme=None,
):
    """
    Open the reusable LAB min/max filter dialog.

    The dialog edits temporary values. Active filter bindings are changed only
    when Apply is pressed, so Cancel leaves the current configuration intact.
    """
    theme = dict(theme or {})

    bg = theme.get("bg", "#f5f6f8")
    card_bg = theme.get("card", "#ffffff")
    text_color = theme.get("text", "#1f2937")
    muted = theme.get("muted", "#6b7280")
    blue = theme.get("blue", "#1f4e8c")
    blue_soft = theme.get("blue_soft", "#e8f0fe")

    font = theme.get("font", ("Segoe UI", 9))
    font_bold = theme.get("font_bold", ("Segoe UI", 9, "bold"))
    font_small = theme.get("font_small", ("Segoe UI", 8))
    font_small_bold = theme.get("font_small_bold", ("Segoe UI", 8, "bold"))
    font_section = theme.get("font_section", ("Segoe UI", 10, "bold"))

    required_keys = (
        "L_min", "L_max",
        "a_min", "a_max",
        "b_min", "b_max",
    )

    missing_keys = [key for key in required_keys if key not in (filter_bindings or {})]
    if missing_keys:
        raise ValueError(
            "Missing LAB filter binding(s): " + ", ".join(missing_keys)
        )

    win = tk.Toplevel(parent)
    win.title("LAB Filters")
    win.configure(bg=bg)
    win.resizable(False, False)

    try:
        win.transient(parent)
    except Exception:
        pass

    defaults = {
        "L_min": "0.0",
        "L_max": "100.0",
        "a_min": "-128.0",
        "a_max": "128.0",
        "b_min": "-128.0",
        "b_max": "128.0",
    }

    temp_bindings = {}

    for key in required_keys:
        enabled_var, value_var = filter_bindings[key]
        temp_bindings[key] = (
            tk.BooleanVar(value=bool(enabled_var.get())),
            tk.StringVar(value=str(value_var.get())),
        )

    outer = tk.Frame(win, bg=bg)
    outer.pack(fill="both", expand=True, padx=12, pady=12)

    card = tk.LabelFrame(
        outer,
        text=" LAB Filters ",
        font=font_section,
        bg=card_bg,
        fg=text_color,
        bd=1,
        relief="solid",
        padx=10,
        pady=8,
        labelanchor="nw",
    )
    card.pack(fill="both", expand=True)

    tk.Label(
        card,
        text=description or "Enabled limits apply to LAB-based filtering.",
        font=font_small,
        bg=card_bg,
        fg=muted,
        anchor="w",
        justify="left",
    ).grid(row=0, column=0, columnspan=5, sticky="ew", pady=(0, 7))

    tk.Label(
        card,
        text="Component",
        font=font_small_bold,
        bg=card_bg,
        fg=text_color,
    ).grid(row=1, column=0, sticky="w", padx=(0, 12))

    tk.Label(
        card,
        text="Minimum",
        font=font_small_bold,
        bg=card_bg,
        fg=text_color,
    ).grid(row=1, column=1, columnspan=2, sticky="w")

    tk.Label(
        card,
        text="Maximum",
        font=font_small_bold,
        bg=card_bg,
        fg=text_color,
    ).grid(row=1, column=3, columnspan=2, sticky="w", padx=(12, 0))

    rows = (
        ("L*", "L_min", "L_max"),
        ("a*", "a_min", "a_max"),
        ("b*", "b_min", "b_max"),
    )

    for row_index, (label, min_key, max_key) in enumerate(rows, start=2):
        min_enabled, min_var = temp_bindings[min_key]
        max_enabled, max_var = temp_bindings[max_key]

        tk.Label(
            card,
            text=label,
            font=font_bold,
            bg=card_bg,
            fg=text_color,
            width=5,
            anchor="w",
        ).grid(row=row_index, column=0, sticky="w", pady=3)

        tk.Checkbutton(
            card,
            variable=min_enabled,
            bg=card_bg,
            activebackground=card_bg,
            selectcolor=card_bg,
        ).grid(row=row_index, column=1, sticky="w")

        tk.Entry(
            card,
            textvariable=min_var,
            width=9,
            font=font,
        ).grid(row=row_index, column=2, sticky="w")

        tk.Checkbutton(
            card,
            variable=max_enabled,
            bg=card_bg,
            activebackground=card_bg,
            selectcolor=card_bg,
        ).grid(row=row_index, column=3, sticky="w", padx=(12, 0))

        tk.Entry(
            card,
            textvariable=max_var,
            width=9,
            font=font,
        ).grid(row=row_index, column=4, sticky="w")

    buttons = tk.Frame(card, bg=card_bg)
    buttons.grid(row=5, column=0, columnspan=5, sticky="ew", pady=(10, 0))

    closed = {"value": False}

    def notify_close():
        if closed["value"]:
            return

        closed["value"] = True

        if callable(on_close):
            try:
                on_close()
            except Exception:
                pass

    def close_dialog():
        try:
            win.grab_release()
        except Exception:
            pass

        try:
            if win.winfo_exists():
                win.destroy()
        finally:
            notify_close()

    def show_warning(message):
        if callable(warning_callback):
            try:
                warning_callback("Invalid Filter", message, parent=win)
                return
            except TypeError:
                try:
                    warning_callback("Invalid Filter", message)
                    return
                except Exception:
                    pass
            except Exception:
                pass

    def reset_filters():
        for key, (enabled_var, value_var) in temp_bindings.items():
            enabled_var.set(False)
            value_var.set(defaults[key])

    def apply_filters():
        try:
            active = read_lab_filter_bindings(
                temp_bindings,
                strict=True,
            )
        except ValueError as exc:
            show_warning(str(exc))
            return

        for key, (real_enabled, real_value) in filter_bindings.items():
            temp_enabled, temp_value = temp_bindings[key]
            real_enabled.set(bool(temp_enabled.get()))
            real_value.set(str(temp_value.get()))

        if callable(on_apply):
            try:
                on_apply(active)
            except TypeError:
                on_apply()

        close_dialog()

    tk.Button(
        buttons,
        text="Reset",
        command=reset_filters,
        font=font,
        relief="solid",
        bd=1,
        padx=12,
        pady=4,
    ).pack(side="left")

    tk.Button(
        buttons,
        text="Cancel",
        command=close_dialog,
        font=font,
        relief="solid",
        bd=1,
        padx=12,
        pady=4,
    ).pack(side="right", padx=(8, 0))

    tk.Button(
        buttons,
        text="Apply",
        command=apply_filters,
        font=font_bold,
        bg=blue_soft,
        fg=blue,
        activebackground="#d7e5fb",
        activeforeground=blue,
        relief="solid",
        bd=1,
        padx=14,
        pady=4,
    ).pack(side="right")

    win.protocol("WM_DELETE_WINDOW", close_dialog)
    win.bind("<Escape>", lambda _e: close_dialog())

    win.update_idletasks()
    dialog_w = max(390, win.winfo_reqwidth() + 8)
    dialog_h = max(220, win.winfo_reqheight() + 8)

    try:
        parent.update_idletasks()

        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()

        x = max(0, px + (pw - dialog_w) // 2)
        y = max(0, py + (ph - dialog_h) // 2)

        win.geometry(f"{dialog_w}x{dialog_h}+{x}+{y}")

    except Exception:
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        x = max(0, (sw - dialog_w) // 2)
        y = max(0, (sh - dialog_h) // 2)
        win.geometry(f"{dialog_w}x{dialog_h}+{x}+{y}")

    try:
        win.grab_set()
        win.focus_set()
    except Exception:
        pass

    return win



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

    # A one-file release does not need to ship a writable
    # ``fuzzy_color_spaces`` directory beside the executable.  If the suggested
    # folder does not exist, simply start the dialog from the application
    # directory (or the current working directory as a final fallback).
    if not os.path.isdir(initial_directory):
        initial_directory = base_path if os.path.isdir(base_path) else os.getcwd()

    filetypes = [
        ("PyFCS Color Spaces", "*.fcs *.cns *.FCS *.CNS"),
        ("Fuzzy Color Space", "*.fcs *.FCS"),
        ("Color Name System", "*.cns *.CNS"),
        ("All Files", "*.*"),
    ]

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
    Create all Prototype objects using one optimized bounded Voronoi build.

    The complete color-space point set is sent to Voronoi.build_diagram(),
    which returns one Volume per color in the same order.  This avoids
    rebuilding the same diagram independently for every Prototype.
    """
    if not color_data:
        return []

    items = list(color_data.items())
    labels = [color_name for color_name, _ in items]
    points = np.asarray(
        [color_value["positive_prototype"] for _, color_value in items],
        dtype=float,
    )

    volumes = Voronoi.build_diagram(points)

    prototypes = [
        Prototype(
            label=label,
            positive=points[i],
            voronoi_volume=volumes[i],
        )
        for i, label in enumerate(labels)
    ]

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

def _get_alpha_values_from_pil(pil_img):
    """Return the original per-pixel alpha (uint8), including soft edges."""
    if "A" in pil_img.getbands():
        return np.asarray(pil_img.getchannel("A"), dtype=np.uint8).copy()
    return np.full((pil_img.height, pil_img.width), 255, dtype=np.uint8)


def _get_alpha_mask_from_pil(pil_img):
    """Boolean mask of pixels with nonzero alpha (for LAB processing)."""
    return _get_alpha_values_from_pil(pil_img) > 0


def _pil_rgb_for_processing(pil_img):
    """
    Returns an RGB version for LAB processing.
    Transparent pixels are kept as RGB but will be ignored using the alpha mask.
    """
    return pil_img.convert("RGB")


def _alpha_u8(alpha_or_mask, shape):
    """Convert an alpha map or boolean validity mask into a uint8 alpha map."""
    alpha = np.asarray(alpha_or_mask)
    if alpha.shape != tuple(shape):
        raise ValueError("Alpha mask does not match image dimensions.")
    if alpha.dtype == np.bool_:
        return alpha.astype(np.uint8) * 255
    return np.clip(alpha, 0, 255).astype(np.uint8)


def _apply_alpha_to_gray_array(gray_array, alpha_or_mask):
    """Build an RGBA grayscale image without destroying fractional opacity."""
    gray = np.asarray(gray_array, dtype=np.uint8)
    rgba = np.zeros((gray.shape[0], gray.shape[1], 4), dtype=np.uint8)
    rgba[..., :3] = gray[..., None]
    rgba[..., 3] = _alpha_u8(alpha_or_mask, gray.shape[:2])
    return rgba


def _apply_alpha_to_rgb_array(rgb_array, alpha_or_mask):
    """Build an RGBA RGB image without destroying fractional opacity."""
    rgb = np.asarray(rgb_array, dtype=np.uint8)
    rgba = np.zeros((rgb.shape[0], rgb.shape[1], 4), dtype=np.uint8)
    rgba[..., :3] = rgb[..., :3]
    rgba[..., 3] = _alpha_u8(alpha_or_mask, rgb.shape[:2])
    return rgba
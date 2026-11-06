import os
import sys
import tempfile
import numpy as np
from skimage import color
from skimage import color as skcolor
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import colorsys

# Project modules
from Source.input_output.Input import Input
from Source.geometry.Prototype import Prototype
from Source.geometry.Voronoi import Voronoi
from Source.colorspace.ReferenceDomain import ReferenceDomain

# Shared Constants

MAX_COLOR_NAME_CHARS = 24


def validate_color_space_name(value):
    """Validate a portable, safe FCS filename, returning the clean name."""
    import re
    name = str(value).strip() if value is not None else ""
    if not name:
        raise ValueError("Please enter a name for the fuzzy color space.")
    if len(name) > 100:
        raise ValueError("The color space name must not exceed 100 characters.")
    if name in (".", "..") or name.endswith((".", " ")):
        raise ValueError("The name cannot end in a dot or space.")
    if re.search(r'[<>:"/\\|?*\x00-\x1f]', name):
        raise ValueError("The name contains characters that cannot be used in a file name.")
    if name.split(".", 1)[0].upper() in (
        "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    ):
        raise ValueError("This name is reserved by Windows. Choose another name.")
    return name

# Shared interface accent. Data-driven colors, membership status and RGB
# swatches must NOT use these values: this palette is for UI chrome only.
UI_ACCENT = "#68428F"       # primary buttons, active labels and links
UI_ACCENT_DARK = "#4F3170"  # hovered / prominent text
UI_ACCENT_SOFT = "#F1ECF7"  # subtle selection / quiet button fill
UI_ACCENT_HOVER = "#E6DCF0"
UI_ACCENT_MUTED = "#6A597A" # secondary violet, e.g. the 3D subtitle


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


# Path Helpers

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
    # Packaged resources may be read-only and must not be used for output.
    relative_path = os.path.normpath(str(relative_path))

    if os.path.isabs(relative_path):
        return relative_path

    app_candidate = os.path.join(get_base_path(), relative_path)

    if not getattr(sys, "frozen", False):
        return app_candidate

    # External resources beside the executable take precedence over bundled files.
    if os.path.exists(app_candidate):
        return app_candidate

    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        bundled_candidate = os.path.join(bundle_root, relative_path)
        if os.path.exists(bundled_candidate):
            return bundled_candidate
        # Retain the expected path for a useful missing-resource error.
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


# Safe Text / Number Helpers

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


# Color Name Helpers

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


# Validation Helpers

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


# Color Conversions

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


# LAB Filter Helpers

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
    blue = theme.get("blue", UI_ACCENT)
    blue_soft = theme.get("blue_soft", UI_ACCENT_SOFT)

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
    win.withdraw()
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
        activebackground=UI_ACCENT_HOVER,
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

    win.deiconify()
    try:
        win.grab_set()
        win.focus_set()
    except Exception:
        pass

    return win


# Extended Color Space Display Helpers

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


# File Selection

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

    # The file dialog falls back to the application directory in frozen builds.
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


# Color Data Helpers

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


# Popup Helpers

def _center_auxiliary_popup(popup, parent, width, height):
    """Set final popup geometry before its first visible frame."""
    popup.update_idletasks()
    try:
        parent.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        if pw <= 1 or ph <= 1:
            raise ValueError("Parent size unavailable")
        x = px + (pw - width) // 2
        y = py + (ph - height) // 2
    except (ValueError, tk.TclError, AttributeError):
        x = (popup.winfo_screenwidth() - width) // 2
        y = (popup.winfo_screenheight() - height) // 2
    popup.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")


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
    popup.withdraw()
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

    _center_auxiliary_popup(popup, parent, width, height)
    popup.deiconify()
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
    popup.withdraw()
    popup.title(title)
    popup.geometry(f"{width}x{height}")
    popup.resizable(False, False)

    listbox = tk.Listbox(popup, width=40, height=10)

    for item in items:
        listbox.insert(tk.END, item)

    listbox.pack(pady=10)

    popup.transient(parent)
    _center_auxiliary_popup(popup, parent, width, height)
    popup.deiconify()
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


# Alpha / PIL Image Helpers

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


# -----------------------------------------------------------------------------
# Fuzzy Color Space creation dialog (kept here to avoid a separate GUI module).
# -----------------------------------------------------------------------------

# Matches the neutral PyFCS workspace with the requested subtle purple accents.
BG = "#F4F5F9"
CARD = "#FFFFFF"
TEXT = "#253043"
MUTED = "#677184"
PURPLE = UI_ACCENT
PURPLE_DARK = UI_ACCENT_DARK
PURPLE_PALE = UI_ACCENT_SOFT
PURPLE_HOVER = UI_ACCENT_HOVER
BORDER = "#DCE0E9"
LINE = "#EAECF2"
ROW_SELECTED = "#EFEAF6"

FONT = ("Segoe UI", 9)
FONT_BOLD = ("Segoe UI", 9, "bold")
FONT_TITLE = ("Segoe UI", 12, "bold")
FONT_CAPTION = ("Segoe UI", 8)
FONT_CAPTION_BOLD = ("Segoe UI", 8, "bold")


class ColorSwatchList(tk.Frame):
    """Fast scrollable list drawn on a Canvas: swatch, name and small coordinates."""

    ROW_HEIGHT = 45

    def __init__(self, parent, on_select=None, on_activate=None, height=165):
        super().__init__(parent, bg=CARD, highlightbackground=BORDER,
                         highlightthickness=1, bd=0)
        self.items = []
        self.selected = None
        self.on_select = on_select
        self.on_activate = on_activate

        self.canvas = tk.Canvas(self, height=height, bg=CARD, bd=0,
                                highlightthickness=0, takefocus=1)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._redraw())
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll(1, "units"))
        self.canvas.bind("<Up>", lambda e: self._move_selection(-1))
        self.canvas.bind("<Down>", lambda e: self._move_selection(+1))
        self.canvas.bind("<Return>", self._activate_keyboard)

    def set_items(self, items, selected=None, preserve_scroll=False):
        old_position = self.canvas.yview()[0] if preserve_scroll and self.items else 0
        self.items = list(items)
        labels = {item["name"] for item in self.items}
        self.selected = selected if selected in labels else None
        self._redraw()
        if preserve_scroll and old_position:
            self.canvas.yview_moveto(old_position)
        else:
            self.canvas.yview_moveto(0)

    def set_selected(self, name, notify=False):
        if name not in {item["name"] for item in self.items}:
            name = None
        self.selected = name
        self._redraw()
        if name is not None:
            index = next(i for i, x in enumerate(self.items) if x["name"] == name)
            lo, hi = self.canvas.yview()
            total = max(1, len(self.items) * self.ROW_HEIGHT)
            top, bottom = index * self.ROW_HEIGHT / total, (index + 1) * self.ROW_HEIGHT / total
            visible = hi - lo
            if top < lo:
                self.canvas.yview_moveto(top)
            elif bottom > hi:
                self.canvas.yview_moveto(max(0, bottom - visible))
        if notify and self.on_select:
            self.on_select(self.selected)

    def _redraw(self):
        cnv = self.canvas
        cnv.delete("all")
        width = max(120, cnv.winfo_width())
        height = len(self.items) * self.ROW_HEIGHT
        cnv.configure(scrollregion=(0, 0, width, height))
        if not self.items:
            cnv.create_text(12, 24, text="No colors", anchor="w", fill=MUTED,
                            font=FONT_CAPTION)
            return
        for i, item in enumerate(self.items):
            y = i * self.ROW_HEIGHT
            active = item["name"] == self.selected
            if active:
                cnv.create_rectangle(0, y, width, y + self.ROW_HEIGHT,
                                     fill=ROW_SELECTED, outline="")
                cnv.create_rectangle(0, y, 3, y + self.ROW_HEIGHT,
                                     fill=PURPLE, outline="")
            cnv.create_rectangle(12, y + 12, 34, y + 34,
                                 fill=item["hex"], outline="#CCD1DA", width=1)
            cnv.create_text(44, y + 12, text=item["name"], anchor="nw",
                            fill=TEXT, font=FONT_BOLD if active else FONT)
            cnv.create_text(44, y + 29, text=item["coordinates"], anchor="nw",
                            fill=MUTED, font=("Segoe UI", 7))
            cnv.create_line(10, y + self.ROW_HEIGHT - 1, width - 6,
                            y + self.ROW_HEIGHT - 1, fill=LINE)

    def _on_click(self, event):
        i = int(self.canvas.canvasy(event.y) // self.ROW_HEIGHT)
        if 0 <= i < len(self.items):
            self.canvas.focus_set()
            self.set_selected(self.items[i]["name"], notify=True)

    def _on_double_click(self, event):
        i = int(self.canvas.canvasy(event.y) // self.ROW_HEIGHT)
        if 0 <= i < len(self.items):
            self.set_selected(self.items[i]["name"], notify=True)
            if self.on_activate:
                self.on_activate(self.selected)

    def _on_wheel(self, event):
        if event.delta:
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _move_selection(self, direction):
        if not self.items:
            return "break"
        names = [x["name"] for x in self.items]
        old = names.index(self.selected) if self.selected in names else (0 if direction > 0 else len(names) - 1)
        self.set_selected(names[max(0, min(len(names) - 1, old + direction))], notify=True)
        return "break"

    def _activate_keyboard(self, event=None):
        if self.selected and self.on_activate:
            self.on_activate(self.selected)
        return "break"


class FCSCreationDialog(tk.Toplevel):
    """Choose name, geometry, typology, scalings, bounds and negative colors.

    `on_accept(name, options)` validates model-specific conditions and initiates
    saving. If it raises, the dialog remains open with the input preserved.
    """

    def __init__(self, parent, selected_colors_lab, on_accept, warn=None,
                 initial_color_space="LAB"):
        super().__init__(parent)
        self.withdraw()
        self.title("New Fuzzy Color Space")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(720, 460)
        self.result = False
        self._on_accept = on_accept
        self._warn = warn
        self._building = True
        self._colors = {str(name): np.asarray(lab, dtype=float).reshape(3)
                        for name, lab in selected_colors_lab.items()}
        self.names = list(self._colors)
        self._rgb = {}
        self._swatches = {}
        for name, lab in self._colors.items():
            with np.errstate(invalid="ignore", over="ignore"):
                rgb = np.clip(skcolor.lab2rgb(lab.reshape(1, 1, 3))[0, 0] * 255.0, 0, 255)
            if not np.all(np.isfinite(rgb)):
                rgb = np.array([128, 128, 128], dtype=float)
            self._rgb[name] = rgb
            self._swatches[name] = "#%02X%02X%02X" % tuple(np.rint(rgb).astype(int))

        self.name_var = tk.StringVar()
        # Creating a NEW fuzzy color space always starts in CIELAB.
        # The loaded FCS model is deliberately independent from this default;
        # RGB remains available when explicitly selected by the user.
        self.mode_var = tk.StringVar(value="LAB")
        self.disjoint_var = tk.BooleanVar(value=True)
        self.covering_var = tk.BooleanVar(value=True)
        self.lambda1_var = tk.StringVar(value="0.5")
        self.lambda2_var = tk.StringVar(value="1.5")
        self.samples_var = tk.StringVar(value="27")
        self.typology_var = tk.StringVar(value="PARTITION")
        self.bounds_vars = [tk.StringVar() for _ in range(6)]
        self.negatives = {name: set() for name in self.names}
        self.current_category = self.names[0] if self.names else None
        self.available_choice = None
        self.chosen_choice = None
        self.search_var = tk.StringVar()
        self.selected_search_var = tk.StringVar()

        self._build()
        self._building = False
        self._set_default_bounds()
        self._update_typology()
        self._refresh_categories()
        self._refresh_negative_lists()
        self._fit_window()
        self.deiconify()
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda e: self.cancel())
        self.bind("<Return>", self._enter_key)
        self._initial_focus_id = self.after_idle(self.name_entry.focus_set)

    @staticmethod
    def _info(parent, text=None, textvariable=None, bg=CARD, **opts):
        opts.setdefault("font", FONT_CAPTION)
        return tk.Label(parent, text=text, textvariable=textvariable, bg=bg,
                        fg=MUTED, justify="left", **opts)

    @staticmethod
    def _field(parent, var, width=None):
        return tk.Entry(parent, textvariable=var, font=FONT, bg=CARD, fg=TEXT,
                        insertbackground=PURPLE_DARK, bd=1, relief="solid",
                        highlightbackground=BORDER, highlightcolor=PURPLE,
                        highlightthickness=1, width=width)

    @staticmethod
    def _card(parent, title):
        card = tk.Frame(parent, bg=CARD, highlightbackground=BORDER,
                        highlightthickness=1, bd=0)
        heading = tk.Frame(card, bg=CARD)
        heading.pack(fill="x", padx=14, pady=(10, 5))
        tk.Label(heading, text=title, font=FONT_BOLD, bg=CARD, fg=TEXT).pack(anchor="w")
        return card

    def _build(self):
        # Keep the required name visible, even when the configuration below is scrolled.
        # This prevents the user from reaching Create while the name is off-screen.
        header = tk.Frame(self, bg=CARD, height=125)
        self.header = header
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="Create Fuzzy Color Space", bg=CARD,
                 fg=TEXT, font=FONT_TITLE).pack(anchor="center", padx=21, pady=(9, 0))
        self._info(header, "Configure the model and how its color categories interact.",
                   bg=CARD).pack(anchor="center", padx=21, pady=(2, 5))
        name_row = tk.Frame(header, bg=CARD)
        name_row.pack(anchor="center", pady=(4, 0))
        tk.Label(name_row, text="Name", bg=CARD, fg=TEXT, font=FONT_BOLD).pack(
            side="left", padx=(0, 10))
        self.name_entry = self._field(name_row, self.name_var, width=42)
        self.name_entry.pack(side="left", ipady=4)
        self.name_error = tk.Label(header, text="", bg=CARD,
                                   fg="#B23F52", font=FONT_CAPTION)
        self.name_error.pack(anchor="center", pady=(3, 0))
        self.name_var.trace_add("write", self._name_changed)
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True)
        self.scroll = tk.Canvas(outer, bg=BG, bd=0, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(outer, orient="vertical", command=self.scroll.yview)
        self.scroll.configure(yscrollcommand=self._scroll_feedback)
        self.scrollbar.pack(side="right", fill="y")
        self.scroll.pack(side="left", fill="both", expand=True)
        self.content = tk.Frame(self.scroll, bg=BG)
        self._content_id = self.scroll.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", lambda e: self.scroll.configure(scrollregion=self.scroll.bbox("all")))
        self.scroll.bind("<Configure>", self._center_content)
        self.scroll.bind("<MouseWheel>", self._wheel_outer)
        self.content.bind("<MouseWheel>", self._wheel_outer)

        card_type = self._card(self.content, "Space configuration")
        card_type.pack(fill="x", padx=17, pady=(12, 10))
        geometry_row = tk.Frame(card_type, bg=CARD)
        geometry_row.pack(anchor="center", padx=14, pady=(0, 6))
        tk.Label(geometry_row, text="Geometry", bg=CARD, fg=TEXT, font=FONT).pack(side="left", padx=(0, 15))
        for label in ("LAB", "RGB"):
            tk.Radiobutton(geometry_row, text=label, value=label, variable=self.mode_var,
                           bg=CARD, fg=TEXT, selectcolor=CARD, activebackground=CARD,
                           font=FONT, command=self._geometry_changed).pack(side="left", padx=(0, 18))
        tk.Frame(card_type, bg=LINE, height=1).pack(fill="x", padx=14, pady=(2, 8))
        type_row = tk.Frame(card_type, bg=CARD)
        type_row.pack(anchor="center", padx=14)
        tk.Label(type_row, text="Typology", bg=CARD, fg=TEXT, font=FONT).pack(side="left", padx=(0, 14))
        for title, var in (("Disjoint", self.disjoint_var), ("Covering", self.covering_var)):
            tk.Checkbutton(type_row, text=title, variable=var, bg=CARD, fg=TEXT,
                           activebackground=CARD, selectcolor=CARD,
                           font=FONT, command=self._update_typology).pack(side="left", padx=(0, 18))
        summary = tk.Frame(card_type, bg=CARD)
        summary.pack(fill="x", padx=14, pady=(6, 11))
        tk.Label(summary, textvariable=self.typology_var, bg=CARD, fg=PURPLE_DARK,
                 font=FONT_CAPTION_BOLD).pack(anchor="center", pady=3)

        card_geometry = self._card(self.content, "Geometry parameters")
        card_geometry.pack(fill="x", padx=17, pady=(0, 10))
        self.advanced_visible = False
        self.advanced_toggle = tk.Button(
            card_geometry, text="Edit settings  ▾", command=self._toggle_advanced,
            bg=CARD, fg=PURPLE, font=FONT_CAPTION_BOLD,
            activebackground=CARD, activeforeground=PURPLE_DARK,
            bd=0, relief="flat", cursor="hand2"
        )
        self.advanced_toggle.place(relx=1.0, x=-14, y=9, anchor="ne")
        self.advanced_summary = self._info(card_geometry, "", anchor="w")
        self.advanced_summary.pack(fill="x", padx=14, pady=(0, 11))
        # Like JFCS, expose the sample density as soon as Non-Covering is selected.
        # 27 denotes 3 per axis, not 27 stored auxiliary negatives: an expanded
        # candidate grid is filtered before the geometry is constructed.
        samples_area = tk.Frame(card_geometry, bg=CARD)
        samples_area.pack(fill="x")
        self.samples_box = tk.Frame(samples_area, bg=CARD)
        self.samples_box.pack(anchor="center", pady=(0, 9))
        tk.Label(self.samples_box, text="Samples", bg=CARD, fg=TEXT,
                 font=FONT).pack(side="left", padx=(0, 8))
        self.samples_combo = ttk.Combobox(
            self.samples_box, textvariable=self.samples_var,
            width=7, state="readonly", values=(8, 27, 64, 125, 216, 343, 512),
        )
        self.samples_combo.pack(side="left")
        self.geometry_details = tk.Frame(card_geometry, bg=CARD)
        params = tk.Frame(self.geometry_details, bg=CARD)
        params.pack(anchor="center", padx=14, pady=(0, 3))
        for title, var in (("Core (λ1)", self.lambda1_var), ("Support (λ2)", self.lambda2_var)):
            part = tk.Frame(params, bg=CARD)
            part.pack(side="left", padx=(0, 20))
            tk.Label(part, text=title, bg=CARD, fg=TEXT, font=FONT).pack(side="left", padx=(0, 7))
            field = self._field(part, var, width=7)
            field.pack(side="left", ipady=3)
        self._info(self.geometry_details, "Core: 0 ≤ λ1 < 1  ·  Support: 1 < λ2 ≤ 2",
                   anchor="center").pack(fill="x", padx=14, pady=(4, 9))
        row_bounds_heading = tk.Frame(self.geometry_details, bg=CARD)
        row_bounds_heading.pack(fill="x", padx=14)
        tk.Label(row_bounds_heading, text="Reference bounds", bg=CARD, fg=TEXT,
                 font=FONT_BOLD).pack(side="left")
        tk.Button(row_bounds_heading, text="Reset defaults", bg=CARD, fg=PURPLE,
                  font=FONT_CAPTION, cursor="hand2", relief="flat", bd=0,
                  activebackground=CARD, activeforeground=PURPLE_DARK,
                  command=self._set_default_bounds).pack(side="right")
        grid = tk.Frame(self.geometry_details, bg=CARD)
        grid.pack(fill="x", padx=14, pady=(5, 10))
        self.bounds_labels = []
        for i, var in enumerate(self.bounds_vars):
            slot = tk.Frame(grid, bg=CARD)
            slot.grid(row=0, column=i, padx=(0, 8) if i < 5 else 0, sticky="ew")
            grid.columnconfigure(i, weight=1, uniform="bounds")
            label = tk.Label(slot, text="", bg=CARD, fg=MUTED, font=FONT_CAPTION)
            label.pack(anchor="w")
            self.bounds_labels.append(label)
            self._field(slot, var).pack(fill="x", ipady=4)

        self.neg_card = self._card(self.content, "Negative prototypes by category")
        self._info(self.neg_card,
                   "Select which other colors act as negatives. Unselected categories may overlap.",
                   anchor="center", wraplength=710).pack(fill="x", padx=14, pady=(0, 9))
        neg_layout = tk.Frame(self.neg_card, bg=CARD)
        neg_layout.pack(fill="both", expand=True, padx=14, pady=(0, 11))
        neg_layout.columnconfigure(0, weight=1, minsize=180)
        neg_layout.columnconfigure(1, weight=2, minsize=390)
        categories_frame = tk.Frame(neg_layout, bg=CARD)
        categories_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self._info(categories_frame, "CATEGORIES", font=FONT_CAPTION_BOLD).pack(anchor="w", pady=(0, 5))
        self.categories_list = ColorSwatchList(categories_frame,
                                                on_select=self._select_category,
                                                height=165)
        self.categories_list.pack(fill="both", expand=True)
        right = tk.Frame(neg_layout, bg=CARD)
        right.grid(row=0, column=1, sticky="nsew")
        self._info(right, "NEGATIVES FOR THE SELECTED CATEGORY").pack(anchor="w", pady=(0, 5))
        two_lists = tk.Frame(right, bg=CARD)
        two_lists.pack(fill="both", expand=True)
        two_lists.columnconfigure(0, weight=1)
        two_lists.columnconfigure(1, weight=1)
        available_frame = tk.Frame(two_lists, bg=CARD)
        available_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        selected_frame = tk.Frame(two_lists, bg=CARD)
        selected_frame.grid(row=0, column=1, sticky="nsew")
        tk.Label(available_frame, text="Available colors", bg=CARD,
                 fg=MUTED, font=FONT_CAPTION).pack(anchor="w", pady=(0, 3))
        self.search_entry = self._field(available_frame, self.search_var)
        self.search_entry.pack(fill="x", pady=(0, 5), ipady=2)
        self.available_list = ColorSwatchList(available_frame, height=137,
                                              on_select=self._set_available_choice,
                                              on_activate=lambda _name: self.add_negative())
        self.available_list.pack(fill="both", expand=True)
        tk.Label(selected_frame, text="Selected negatives", bg=CARD,
                 fg=MUTED, font=FONT_CAPTION).pack(anchor="w", pady=(0, 3))
        self.selected_search_entry = self._field(selected_frame, self.selected_search_var)
        self.selected_search_entry.pack(fill="x", pady=(0, 5), ipady=2)
        self.selected_list = ColorSwatchList(selected_frame, height=137,
                                             on_select=self._set_chosen_choice,
                                             on_activate=lambda _name: self.remove_negative())
        self.selected_list.pack(fill="both", expand=True)
        commands = tk.Frame(right, bg=CARD)
        commands.pack(fill="x", pady=(8, 0))
        centered_commands = tk.Frame(commands, bg=CARD)
        centered_commands.pack(anchor="center")
        for label, command in (("Add →", self.add_negative),
                               ("← Remove", self.remove_negative),
                               ("Add all", self.add_all_negatives),
                               ("Clear", self.clear_negatives)):
            tk.Button(centered_commands, text=label, command=command,
                      bg="#F2F3F6", fg=TEXT,
                      activebackground="#E6E8EC", activeforeground=TEXT,
                      bd=0, relief="flat", cursor="hand2",
                      font=FONT_CAPTION, padx=10, pady=5
                      ).pack(side="left", padx=4)
        self.negative_status = self._info(self.neg_card, "")
        self.negative_status.pack(fill="x", padx=14, pady=(0, 10))

        footer = tk.Frame(self, bg=CARD)
        self.footer = footer
        footer.pack(fill="x", side="bottom")
        tk.Frame(footer, bg=BORDER, height=1).pack(fill="x")
        button_row = tk.Frame(footer, bg=CARD)
        button_row.pack(pady=12, anchor="center")
        self.ok_button = tk.Button(button_row, text="Create Color Space", command=self.confirm,
                                   bg=PURPLE, fg="white", font=FONT_BOLD,
                                   activebackground=PURPLE_DARK, activeforeground="white",
                                   relief="flat", bd=0, padx=18, pady=8, cursor="hand2")
        self.ok_button.pack(side="left", padx=(0, 10))
        self.cancel_button = tk.Button(button_row, text="Cancel", command=self.cancel,
                                       bg="#EFF0F4", fg=TEXT, font=FONT,
                                       activebackground="#E4E6EC", relief="flat", bd=0,
                                       padx=18, pady=8, cursor="hand2")
        self.cancel_button.pack(side="left")

        self.search_var.trace_add("write", lambda *_: self._refresh_negative_lists())
        self.selected_search_var.trace_add("write", lambda *_: self._refresh_negative_lists())
        for change_var in (self.lambda1_var, self.lambda2_var, self.samples_var):
            change_var.trace_add("write", lambda *_: self._update_advanced_summary())

    def _center_content(self, event):
        """Center the cards, leaving a sensible width at large DPI / screen sizes."""
        available = max(1, int(event.width))
        width = min(790, max(1, available - 24))
        self.scroll.itemconfigure(self._content_id, width=width)
        self.scroll.coords(self._content_id, max(0, (available - width) // 2), 0)

    def _scroll_feedback(self, first, last):
        self.scrollbar.set(first, last)
        try:
            fits = float(first) <= 0.001 and float(last) >= 0.999
            if fits and self.scrollbar.winfo_manager():
                self.scrollbar.pack_forget()
            elif not fits and not self.scrollbar.winfo_manager():
                self.scrollbar.pack(side="right", fill="y", before=self.scroll)
        except (ValueError, tk.TclError):
            pass

    def _wheel_outer(self, event):
        if event.delta:
            self.scroll.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _toggle_advanced(self):
        self.advanced_visible = not self.advanced_visible
        if self.advanced_visible:
            self.geometry_details.pack(fill="x")
            self.advanced_toggle.configure(text="Hide settings  ▴")
        else:
            self.geometry_details.pack_forget()
            self.advanced_toggle.configure(text="Edit settings  ▾")
        self._fit_window()

    def _update_advanced_summary(self):
        if not hasattr(self, "advanced_summary"):
            return
        info = f"Core λ1 = {self.lambda1_var.get()}  ·  Support λ2 = {self.lambda2_var.get()}"
        if not self.covering_var.get():
            info += f"  ·  Auxiliary samples = {self.samples_var.get()}"
        self.advanced_summary.configure(text=info)

    def _set_default_bounds(self):
        values = (0, 255, 0, 255, 0, 255) if self.mode_var.get() == "RGB" else (0, 100, -128, 128, -128, 128)
        axes = ("R", "G", "B") if self.mode_var.get() == "RGB" else ("L", "a", "b")
        for i, (var, value) in enumerate(zip(self.bounds_vars, values)):
            var.set(str(value))
            self.bounds_labels[i].configure(text=f"{axes[i // 2]} {'min' if i % 2 == 0 else 'max'}")
        self._update_advanced_summary()

    def _geometry_changed(self):
        self._set_default_bounds()
        self._refresh_categories()
        self._refresh_negative_lists()

    def _item(self, name):
        if self.mode_var.get() == "RGB":
            r, g, b = self._rgb[name]
            coordinates = f"R {r:.0f}  G {g:.0f}  B {b:.0f}"
        else:
            l, a, b = self._colors[name]
            coordinates = f"L {l:.1f}  a {a:.1f}  b {b:.1f}"
        return {"name": name, "hex": self._swatches[name], "coordinates": coordinates}

    def _refresh_categories(self):
        self.categories_list.set_items([self._item(name) for name in self.names],
                                       selected=self.current_category, preserve_scroll=True)

    def _select_category(self, name):
        if name and name != self.current_category:
            self.current_category = name
            self.available_choice = None
            self.chosen_choice = None
            self.search_var.set("")
            self.selected_search_var.set("")
            self._refresh_negative_lists()

    def _set_available_choice(self, name):
        self.available_choice = name

    def _set_chosen_choice(self, name):
        self.chosen_choice = name

    def _refresh_negative_lists(self):
        if not hasattr(self, "available_list") or self.current_category is None:
            return
        category = self.current_category
        chosen = self.negatives[category]
        candidates = [x for x in self.names if x != category and x not in chosen]
        needle = self.search_var.get().casefold().strip()
        if needle:
            candidates = [x for x in candidates if needle in x.casefold()]
        existing = [x for x in self.names if x in chosen and x != category]
        selected_needle = self.selected_search_var.get().casefold().strip()
        if selected_needle:
            visible_existing = [x for x in existing if selected_needle in x.casefold()]
        else:
            visible_existing = existing
        self.available_list.set_items([self._item(n) for n in candidates],
                                      selected=self.available_choice, preserve_scroll=True)
        self.selected_list.set_items([self._item(n) for n in visible_existing],
                                     selected=self.chosen_choice, preserve_scroll=True)
        self.negative_status.configure(text=(
            f"{category}: {len(existing)} selected negative(s) · "
            "Double-click a color to add or remove it."
        ))

    def add_negative(self):
        if self.current_category and self.available_list.selected:
            self.negatives[self.current_category].add(self.available_list.selected)
            self.available_choice = None
            self._refresh_negative_lists()

    def remove_negative(self):
        if self.current_category and self.selected_list.selected:
            self.negatives[self.current_category].discard(self.selected_list.selected)
            self.chosen_choice = None
            self._refresh_negative_lists()

    def add_all_negatives(self):
        if self.current_category:
            self.negatives[self.current_category].update(
                x for x in self.names if x != self.current_category)
            self._refresh_negative_lists()

    def clear_negatives(self):
        if self.current_category:
            self.negatives[self.current_category].clear()
            self._refresh_negative_lists()

    def _update_typology(self):
        disjoint, covering = self.disjoint_var.get(), self.covering_var.get()
        typology = ("PARTITION" if disjoint and covering else
                    ("DISJOINT" if disjoint else "NON-DISJOINT") + " and " +
                    ("COVERING" if covering else "NON-COVERING"))
        self.typology_var.set(typology)
        if covering:
            self.samples_box.pack_forget()
        elif not self.samples_box.winfo_manager():
            self.samples_box.pack(anchor="center", pady=(0, 9))
        if disjoint:
            self.neg_card.pack_forget()
        elif not self.neg_card.winfo_manager():
            self.neg_card.pack(fill="x", padx=17, pady=(0, 10))
        self._update_advanced_summary()
        if not self._building:
            self._fit_window()

    def _fit_window(self):
        self.update_idletasks()
        # Keep the dialog compact for partition spaces, while reserving a
        # taller (scrollable) layout for individual negatives.
        w = min(850, max(730, self.winfo_screenwidth() - 90))
        wanted = max(490, self.content.winfo_reqheight() + self.header.winfo_reqheight() + self.footer.winfo_reqheight() + 12)
        h = min(wanted, max(420, self.winfo_screenheight() - 110))
        x = max(0, (self.winfo_screenwidth() - w) // 2)
        y = max(0, (self.winfo_screenheight() - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _name_changed(self, *_):
        if self.name_var.get().strip():
            self.name_error.configure(text="")
            self.name_entry.configure(highlightbackground=BORDER,
                                      highlightcolor=PURPLE)

    def _check_name(self):
        if self.name_var.get().strip():
            return True
        self.name_error.configure(text="Please enter a name for the fuzzy color space.")
        self.name_entry.configure(highlightbackground="#B23F52",
                                  highlightcolor="#B23F52")
        self.name_entry.focus_set()
        return False

    def build_options(self):
        name = validate_color_space_name(self.name_var.get())
        domain = ReferenceDomain.from_bounds([v.get().strip() for v in self.bounds_vars])
        lam1, lam2 = float(self.lambda1_var.get()), float(self.lambda2_var.get())
        disjoint, covering = self.disjoint_var.get(), self.covering_var.get()
        if not (0 <= lam1 < 1 and 1 < lam2 <= 2):
            raise ValueError("Require 0 ≤ λ1 < 1 and 1 < λ2 ≤ 2.")
        if disjoint and not (1 <= lam1 + lam2 <= 2):
            raise ValueError("Disjoint spaces require 1 ≤ λ1 + λ2 ≤ 2.")
        count = int(self.samples_var.get()) if not covering else 0
        if not covering and count not in (8, 27, 64, 125, 216, 343, 512):
            raise ValueError("Select one of the JFCS sampling options: 8, 27, 64, 125, 216, 343 or 512.")
        negative = ({k: [n for n in self.names if n in vals]
                     for k, vals in self.negatives.items()} if not disjoint else None)
        return name, {
            "color_space": self.mode_var.get().upper(),
            "reference_domain": domain,
            "lambda1": lam1, "lambda2": lam2,
            "disjoint": disjoint, "covering": covering,
            "samples": count, "negative_prototypes": negative,
        }

    def _enter_key(self, event):
        # Let Enter activate a color when a swatch list has focus.
        if isinstance(event.widget, tk.Canvas):
            return
        self.confirm()

    def confirm(self):
        if self.result:
            return
        # Normal input validation: show inline feedback instead of raising a
        # ValueError that may interrupt execution when debugging exceptions.
        if not self._check_name():
            return
        try:
            name, options = self.build_options()
            self.ok_button.configure(state="disabled")
            self.update_idletasks()
            # An explicit False means the save did not start (for example,
            # the user declined to overwrite an existing .fcs). Keep editing.
            if self._on_accept(name, options) is False:
                self.ok_button.configure(state="normal")
                return
        except Exception as exc:
            self.ok_button.configure(state="normal")
            if self._warn:
                self._warn("Error", str(exc), parent=self)
            else:
                messagebox.showerror("Invalid space configuration", str(exc), parent=self)
            return
        self.result = True
        self.destroy()

    def cancel(self):
        if not self.result:
            self.result = False
            self.destroy()

    def destroy(self):
        # A very quick Cancel must not leave the initial-focus after_idle job
        # queued against a Tk widget that no longer exists.
        focus_id = getattr(self, "_initial_focus_id", None)
        if focus_id is not None:
            try:
                self.after_cancel(focus_id)
            except tk.TclError:
                pass
            self._initial_focus_id = None
        super().destroy()

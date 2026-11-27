import os
import sys
import tempfile
import numpy as np
from skimage import color
from skimage import color as skcolor
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import colorsys
from PIL import Image, ImageTk

# Project modules
from Source.input_output.Input import Input
from Source.geometry.Prototype import Prototype
from Source.geometry.Voronoi import Voronoi
from Source.colorspace.ReferenceDomain import ReferenceDomain

# Shared Constants

MAX_COLOR_NAME_CHARS = 24  # Granule labels
MAX_CATEGORY_NAME_CHARS = 20  # New/renamed categories (allow room for -gNN)


def check_granule_site(label, lab, existing_sites=(), *,
                       max_name_length=MAX_COLOR_NAME_CHARS):
    """Validate user-entered granule data without raising an exception.

    ``existing_sites`` contains ``(category_label, granule_label, lab)``
    tuples, excluding the site currently being edited. This is the shared
    validation rule for Palette Creation and Add Color Category.

    Returns ``(clean_name, lab_tuple, error_message)``. A normal validation
    failure returns a message, not ValueError, keeping Tk callbacks safe.
    """
    clean_name, error = check_label_name(label, max_length=max_name_length, kind="Granule")
    if error:
        return None, None, error

    try:
        point = np.asarray(lab, dtype=float).reshape(-1)
        if (point.size != 3 or not np.all(np.isfinite(point))
                or not is_valid_lab(point)):
            return None, None, "Enter valid LAB coordinates."
        for category, other_name, other_lab in existing_sites:
            if other_name == clean_name:
                return None, None, f"Granule name '{clean_name}' is already in use."
            other = np.asarray(other_lab, dtype=float).reshape(-1)
            if other.size == 3 and np.all(np.isfinite(other)):
                if np.linalg.norm(point - other) <= Voronoi.DEFAULT_MERGE_EPS:
                    where = f" in '{category}'" if category else ""
                    return None, None, (
                        f"LAB coordinates coincide with '{other_name}'{where}."
                    )
    except (TypeError, ValueError, OverflowError, FloatingPointError):
        return None, None, "Enter valid LAB coordinates."
    return clean_name, tuple(float(x) for x in point), None



def check_label_name(value, *, max_length=MAX_COLOR_NAME_CHARS, kind="Color"):
    """Labels are JSON identifiers, not filenames. Allow printable Unicode."""
    import unicodedata
    raw = str(value) if value is not None else ""
    name = raw.strip()
    if any(unicodedata.category(ch) in ("Cc", "Cf", "Cs", "Zl", "Zp") for ch in raw):
        return name, f"{kind} name must not contain control or invisible characters."
    if not name or len(name) > max_length:
        return name, f"{kind} name must contain 1 to {max_length} characters."
    return name, ""


def check_color_space_name(value):
    """Non-throwing validation for names used as Windows filenames."""
    import re
    name, error = check_label_name(value, max_length=100, kind="Color space")
    if error:
        return name, error
    if name in (".", "..") or name.endswith("."):
        return name, "The name cannot end in a dot."
    if re.search(r'[<>:"/\\|?*]', name):
        return name, "The name contains characters that cannot be used in a file name."
    stem = name.split(".", 1)[0].rstrip().upper()
    if stem in ("CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
                *(f"COM{i}" for i in "123456789¹²³"),
                *(f"LPT{i}" for i in "123456789¹²³")):
        return name, "This name is reserved by Windows. Choose another name."
    return name, ""


def validate_color_space_name(value):
    """Strict API for non-UI callers; UI uses check_color_space_name."""
    name, error = check_color_space_name(value)
    if error:
        raise ValueError(error)
    return name


def preferred_picker_mode(app, explicit=None, *, fallback="RGB"):
    """Choose the initial display mode, independently of stored exact LAB."""
    model = getattr(getattr(app, "fuzzy_color_space", None), "color_space", None)
    mode = str(explicit or model or fallback).upper()
    return mode if mode in ("RGB", "LAB", "HSV", "HSL", "HEX") else fallback


def styled_combobox(parent, **options):
    """Shared compact ttk style; no theme change or event API replacement."""
    style = ttk.Style(parent)
    name = "PyFCS.TCombobox"
    style.configure(name, padding=(7, 4), fieldbackground="#fafbfe",
                    background="#fafbfe", foreground="#1f2937", arrowcolor="#6b7280",
                    bordercolor="#d9dde3", lightcolor="#d9dde3", darkcolor="#d9dde3",
                    relief="flat")
    style.map(name, fieldbackground=[("disabled", "#eef0f3"), ("readonly", "#fafbfe")],
              foreground=[("disabled", "#9ca3af"), ("readonly", "#1f2937")],
              selectbackground=[("readonly", "#fafbfe")],
              selectforeground=[("readonly", "#1f2937")],
              background=[("disabled", "#eef0f3"), ("readonly", "#fafbfe")])
    options["style"] = name
    return ttk.Combobox(parent, **options)


def styled_scrollbar(parent, **options):
    """Consistent slim, flat scrollbar without changing the current theme.

    Use clam drawing elements even on native Windows themes; retain ttk's
    standard thumb dragging, page scrolling and command/set interface.
    """
    style = ttk.Style(parent)
    vertical = str(options.get("orient", "vertical")).lower() == "vertical"
    axis = "Vertical" if vertical else "Horizontal"
    name = f"PyFCS.{axis}.TScrollbar"
    prefix = f"PyFCS.{axis}.Scrollbar"
    trough, thumb = f"{prefix}.trough", f"{prefix}.thumb"
    existing = set(style.element_names())
    for element, source in ((trough, "trough"), (thumb, "thumb")):
        if element not in existing:
            style.element_create(element, "from", "clam", source)
    style.layout(name, [(trough, {"sticky": "nswe", "children": [
        (thumb, {"sticky": "nswe"})]})])
    style.configure(name, background="#C4CAD3", troughcolor="#F1F3F6",
                    bordercolor="#F1F3F6", lightcolor="#C4CAD3", darkcolor="#C4CAD3",
                    arrowsize=11, width=11, sliderlength=24, gripcount=0,
                    borderwidth=0, relief="flat", troughrelief="flat")
    style.map(name, background=[("pressed", "#919BAA"), ("active", "#A6AFBC")],
              lightcolor=[("pressed", "#919BAA"), ("active", "#A6AFBC")],
              darkcolor=[("pressed", "#919BAA"), ("active", "#A6AFBC")])
    options["style"] = name
    return ttk.Scrollbar(parent, **options)


# Shared interface accent. Data-driven colors, membership status and RGB
# swatches must NOT use these values: this palette is for UI chrome only.
UI_ACCENT = "#68428F"       # primary buttons, active labels and links
UI_ACCENT_DARK = "#4F3170"  # hovered / prominent text
UI_ACCENT_SOFT = "#F1ECF7"  # subtle selection / quiet button fill
UI_ACCENT_HOVER = "#E6DCF0"
UI_ACCENT_MUTED = "#6A597A" # secondary violet, e.g. the 3D subtitle

# Restrained shared styles for "add" actions throughout creation/edit dialogs.
# Green denotes a new category; blue denotes importing an external source.
UI_ADD_CATEGORY_BG = "#EDF5EF"
UI_ADD_CATEGORY_FG = "#355F49"
UI_ADD_CATEGORY_HOVER = "#E1EEE4"
UI_ADD_SOURCE_BG = "#EDF3F9"
UI_ADD_SOURCE_FG = "#365D7A"
UI_ADD_SOURCE_HOVER = "#E0EBF6"


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


def unique_import_label(base, occupied, max_length, additional=()):
    """Return a bounded, unique display label for a newly imported item.

    Existing source objects are never renamed. An imported name that exceeds
    the new-workspace limit is shortened, reserving space for `` (2)``, etc.
    Membership in ``occupied`` and ``additional`` is checked using sets;
    repeated imports do not trigger a quadratic scan of existing names.
    """
    label = str(base or "Color").strip() or "Color"
    limit = int(max_length)
    if limit < 5:
        raise ValueError("The maximum label length must be at least five.")
    used = occupied if isinstance(occupied, set) else set(occupied)
    extra = additional if isinstance(additional, set) else set(additional)

    candidate = label[:limit].rstrip()
    if candidate and candidate not in used and candidate not in extra:
        return candidate

    number = 2
    while True:
        suffix = f" ({number})"
        available = limit - len(suffix)
        if available < 1:
            raise ValueError("Too many labels for the configured name limit.")
        stem = label[:available].rstrip() or label[:available]
        candidate = stem + suffix
        if candidate not in used and candidate not in extra:
            return candidate
        number += 1


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



def matching_native_rgb(lab, rgb, *, tolerance=1e-2):
    """Return a precise RGB source only if it created the same displayed LAB.

    Do not turn an arbitrary LAB original into a rounded RGB color. RGB
    coordinates are kept for model creation only when source provenance is
    known or an exact RGB/HEX edit can be verified against the GUI's converter.
    """
    try:
        xyz = np.asarray(rgb, dtype=float).reshape(-1)
        lab_xyz = np.asarray(lab, dtype=float).reshape(-1)
        if xyz.shape != (3,) or lab_xyz.shape != (3,):
            return None
        if not np.all(np.isfinite(xyz)) or np.any((xyz < 0) | (xyz > 255)):
            return None
        if np.linalg.norm(np.asarray(rgb_to_lab(xyz), dtype=float) - lab_xyz) <= tolerance:
            return xyz.copy()
    except (TypeError, ValueError):
        pass
    return None


def prepare_granular_creation_options(selected_categories_lab, options, native_rgb=None):
    """One shared LAB-to-native granular construction path for both creators.

    The selected prototype coordinates are in CIELAB. The geometric model
    (currently LAB or RGB) is chosen by the existing FCSCreationDialog.
    Negatives selected by category expand to ALL granules of that category.
    Geometry remains the responsibility of the FuzzyColorSpaceBuilder.
    """
    from Source.fuzzy.FuzzyColorSpaceBuilder import lab_to_rgb_model_checked
    from Source.geometry.Voronoi import Voronoi

    settings = dict(options)
    mode = str(settings.get('color_space', 'LAB')).upper()
    domain = settings['reference_domain']

    def to_native(lab):
        xyz = np.asarray(lab, dtype=float).reshape(1, 3)
        if mode == 'LAB':
            return xyz[0]
        if mode == 'RGB':
            return lab_to_rgb_model_checked(xyz)[0]
        raise ValueError(f'Unsupported geometric model: {mode}')

    native_sources = native_rgb or {}
    native = {}
    for category, granules in selected_categories_lab.items():
        native[category] = {}
        for label, lab in granules.items():
            source = native_sources.get(category, {}).get(label)
            if mode == 'RGB' and source is not None:
                xyz = np.asarray(source, dtype=float).reshape(-1)
                if xyz.shape != (3,) or not np.all(np.isfinite(xyz)) or np.any((xyz < 0) | (xyz > 255)):
                    raise ValueError(f'Invalid native RGB for {category}/{label}.')
                native[category][label] = xyz.copy()
            else:
                native[category][label] = to_native(lab)
    all_sites = np.asarray(
        [site for granules in native.values() for site in granules.values()],
        dtype=float,
    )
    Voronoi._validate_points_in_domain(all_sites, domain, Voronoi.DEFAULT_EPS)
    Voronoi._validate_no_duplicate_points(all_sites, Voronoi.DEFAULT_MERGE_EPS)

    if settings['disjoint']:
        settings['negative_prototypes'] = None
    else:
        negatives = {}
        for owner, chosen in (settings.get('negative_prototypes') or {}).items():
            points = []
            for other in chosen:
                if isinstance(other, str):
                    if other == owner or other not in native:
                        raise ValueError(f'Invalid negative category: {other}')
                    points.extend(native[other].values())
                elif isinstance(other, dict):
                    if set(other) != {'native'}:
                        raise ValueError('Invalid native negative prototype.')
                    point = np.asarray(other['native'], dtype=float).reshape(3)
                    if not np.all(np.isfinite(point)):
                        raise ValueError('Invalid negative coordinates.')
                    points.append(point)
                else:
                    points.append(to_native(other))
            negatives[owner] = points
        settings['negative_prototypes'] = negatives
    settings['_granular_categories'] = native
    return settings


def mean_lab_with_filters(rgb_pixels, filters=None, chunk_size=100000):
    """Arithmetic CIELAB mean of *individual* visible RGB pixels.

    Each sRGB pixel is converted to CIELAB (D65) before filtering or
    averaging. Processing in bounded chunks limits temporary memory for large
    ROIs. The LAB result is never inferred from a rounded mean RGB value.

    Returns (mean_lab, accepted_count), or (None, 0) for an empty selection.
    """
    pixels = np.asarray(rgb_pixels, dtype=np.float32).reshape(-1, 3)
    filters = dict(filters or {})
    chunk_size = max(1, int(chunk_size))
    sums = np.zeros(3, dtype=np.float64)
    accepted_count = 0
    for offset in range(0, len(pixels), chunk_size):
        block = pixels[offset:offset + chunk_size]
        valid = np.all(np.isfinite(block), axis=1)
        if not np.any(valid):
            continue
        block = np.clip(block[valid] / 255.0, 0.0, 1.0)
        lab = color.rgb2lab(block.reshape(-1, 1, 3)).reshape(-1, 3)
        mask = np.ones(len(lab), dtype=bool)
        for field, channel, minimum in (
            ("L_min", 0, True), ("L_max", 0, False),
            ("a_min", 1, True), ("a_max", 1, False),
            ("b_min", 2, True), ("b_max", 2, False),
        ):
            if field in filters:
                limit = float(filters[field])
                mask &= lab[:, channel] >= limit if minimum else lab[:, channel] <= limit
        if np.any(mask):
            sums += np.sum(lab[mask], axis=0, dtype=np.float64)
            accepted_count += int(np.count_nonzero(mask))
    return (sums / accepted_count, accepted_count) if accepted_count else (None, 0)



def mean_lab_of_pil_roi(image, box, filters=None, max_chunk_pixels=100000):
    """LAB average from an image ROI with bounded temporary memory.

    ``box`` uses PIL's exclusive right/bottom coordinates. Transparent
    pixels are ignored. LAB limits apply to individual visible pixels before
    averaging. Returns (mean_lab, accepted_count, visible_count).
    """
    x0, y0, x1, y1 = (int(v) for v in box)
    x0 = max(0, min(image.width, x0))
    x1 = max(0, min(image.width, x1))
    y0 = max(0, min(image.height, y0))
    y1 = max(0, min(image.height, y1))
    if x1 <= x0 or y1 <= y0:
        return None, 0, 0
    row_count = max(1, int(max_chunk_pixels) // max(1, x1-x0))
    lab_sum = np.zeros(3, dtype=np.float64)
    used = 0
    visible = 0
    for top in range(y0, y1, row_count):
        rgba = np.asarray(image.crop((x0, top, x1, min(y1, top + row_count)))
                          .convert('RGBA'), dtype=np.uint8)
        valid = rgba[..., 3] > 0
        visible += int(np.count_nonzero(valid))
        if not np.any(valid):
            continue
        mean, n = mean_lab_with_filters(rgba[..., :3][valid], filters,
                                        chunk_size=max_chunk_pixels)
        if n:
            lab_sum += mean * n
            used += n
    return (lab_sum / used if used else None), used, visible


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
        ("PyFCS Color Spaces", "*.json *.fcs *.cns *.JSON *.FCS *.CNS"),
        ("PyFCS JSON Color Space", "*.json *.JSON"),
        ("Legacy Fuzzy Color Space", "*.fcs *.FCS"),
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
        raw_native = (np.asarray(color_value["Color"], dtype=float).copy()
                      if str(getattr(input_class, "last_color_space", "LAB")).upper() == "RGB"
                      else None)
        rgb = tuple(safe_rgb_tuple(raw_native)) if raw_native is not None else lab_to_rgb(lab)

        colors[color_name] = {"rgb": rgb, "lab": lab}
        if raw_native is not None:
            colors[color_name]["native_rgb"] = raw_native

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
    scrollbar = styled_scrollbar(
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
    """Return per-pixel alpha, including RGBA and indexed PNG transparency.

    PNG images in mode P (or RGB) can store transparency in the ``transparency``
    metadata rather than an A band. Decode that metadata instead of treating
    those pixels as opaque. The normal PyFCS GUI already converts files to RGBA,
    but mapping helpers can also be used directly with the original PIL image.
    """
    if "A" in pil_img.getbands():
        return np.asarray(pil_img.getchannel("A"), dtype=np.uint8).copy()
    if "transparency" in pil_img.info:
        return np.asarray(pil_img.convert("RGBA").getchannel("A"), dtype=np.uint8).copy()
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
        self.scrollbar = styled_scrollbar(self, orient="vertical", command=self.canvas.yview)
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


def negative_coordinate(value, mode, target):
    """Convert precise negative inputs without quantizing native coordinates."""
    from Source.fuzzy.FuzzyColorSpaceBuilder import lab_to_rgb_model_checked
    mode, target = str(mode).upper(), str(target).upper()
    if mode == 'HEX':
        import re
        value = str(value).strip().lstrip('#')
        if not re.fullmatch(r'[0-9a-fA-F]{6}', value):
            raise ValueError('Enter a six-digit HEX color.')
        value = [int(value[i:i+2],16) for i in (0,2,4)]
        mode = 'RGB'
    elif isinstance(value, str):
        value = value.replace(',', ' ').split()
    point = np.asarray(value, dtype=float).reshape(-1)
    if point.shape != (3,) or not np.all(np.isfinite(point)):
        raise ValueError('Enter three finite coordinates.')
    if mode == 'RGB':
        if np.any((point < 0) | (point > 255)):
            raise ValueError('RGB coordinates must be between 0 and 255.')
        if target == 'LAB':
            point = skcolor.rgb2lab((point/255).reshape(1,1,3))[0,0]
    elif mode == 'LAB':
        if not is_valid_lab(point):
            raise ValueError('Enter valid CIELAB coordinates.')
        if target == 'RGB':
            point = lab_to_rgb_model_checked(point.reshape(1,3))[0]
    else:
        raise ValueError('Unknown coordinate model.')
    return tuple(float(x) for x in point)


def native_negative_sets(categories, values):
    """Validate complete per-category negative sets, without mutating drafts."""
    if set(values) != set(categories):
        raise ValueError('Negative sets must match the geometric categories.')
    result = {}
    for owner, choices in values.items():
        unique = []
        for q in choices:
            point = np.asarray(q, dtype=float).reshape(-1)
            if point.shape != (3,) or not np.all(np.isfinite(point)):
                raise ValueError(f'Invalid negative coordinates in {owner}.')
            if any(np.linalg.norm(point-p) <= Voronoi.DEFAULT_MERGE_EPS
                   for p in categories[owner].values()):
                raise ValueError(f'{owner} cannot use one of its own positives as a negative.')
            if not any(np.linalg.norm(point-p) <= Voronoi.DEFAULT_MERGE_EPS for p in unique):
                unique.append(tuple(float(v) for v in point))
        result[owner] = unique
    return result


def filter_negative_names(names, sets):
    """Keep optional display names only for points still used as negatives."""
    points = {tuple(float(x) for x in q) for values in sets.values() for q in values}
    result = {}
    for q, label in (names or {}).items():
        key = tuple(float(x) for x in q)
        if key in points:
            name, error = check_label_name(label, kind='Negative')
            if error: raise ValueError(error)
            result[key] = name
    return result


class NegativePrototypeDialog(tk.Toplevel):
    """Transactional negative editor shared by creation and Edit FCS.

    Existing positives are selected at granule level. Custom entries retain
    exact native coordinates; only explicitly chosen points become negatives.
    """
    def __init__(self, parent, categories, mode, initial=None, warn=None, app=None, negative_names=None):
        validated = native_negative_sets(categories, initial if initial is not None else
                                         {k: [] for k in categories})
        if not categories:
            raise ValueError('Select at least one category.')
        super().__init__(parent)
        self.withdraw(); self.title('Manage Negative Prototypes')
        self.configure(bg=BG); self.transient(parent)
        self.categories = categories
        self.mode = mode
        self.warn = warn
        self.app = app
        self.result = None
        self.values = validated
        self.negative_names = filter_negative_names(negative_names, validated)
        self.result_names = None
        self.owner = next(iter(categories))
        self._previous_grab = parent.grab_current()
        self.protocol('WM_DELETE_WINDOW', self.cancel)
        self.bind('<Escape>', lambda e: self.cancel())
        header = tk.Frame(self,bg=CARD,highlightbackground=BORDER,highlightthickness=1)
        header.pack(fill='x',padx=14,pady=12)
        tk.Label(header,text='Manage Negative Prototypes',bg=CARD,fg=TEXT,font=FONT_TITLE).pack(pady=(10,2))
        tk.Label(header,text=f'Define geometric competitors for each category · {mode} model',bg=CARD,fg=MUTED,font=FONT_CAPTION).pack(pady=(0,10))
        # Experimental import is intentionally hidden from the normal workflow.
        self.bind('<Control-Shift-I>', self._import_shortcut)
        self.bind('<Control-Shift-i>', self._import_shortcut)
        self.status=tk.StringVar(master=self,value='Select a category and add negative prototypes.')
        content=tk.Frame(self,bg=BG); content.pack(fill='both',expand=True,padx=14)
        for i,w in enumerate((1,2,2)): content.columnconfigure(i,weight=w,uniform='neg')
        content.rowconfigure(0,weight=1)
        frames=[]
        for i,title in enumerate(('Color categories','Available granules','Selected negatives')):
            f=tk.LabelFrame(content,text=title,bg=CARD,fg=TEXT,font=FONT_BOLD,labelanchor='n',padx=6,pady=6)
            f.grid(row=0,column=i,sticky='nsew',padx=(0,8) if i<2 else 0); frames.append(f)
        self.categories_list=ColorSwatchList(frames[0],on_select=self.select_category,height=300)
        self.categories_list.pack(fill='both',expand=True)
        self.query=tk.StringVar(); self.query.trace_add('write',lambda *_: self.refresh())
        search=tk.Frame(frames[1],bg=CARD); search.pack(fill='x',pady=(0,6))
        tk.Label(search,text='Search',bg=CARD,fg=TEXT,font=FONT_BOLD).pack(side='left',padx=(0,7))
        tk.Entry(search,textvariable=self.query,font=FONT,relief='solid',bd=1,width=15).pack(side='left',fill='x',expand=True)
        tk.Button(search,text='Clear',command=lambda:self.query.set(''),bg=CARD,fg=MUTED,relief='flat',padx=4).pack(side='left')
        chosen_intro=tk.Frame(frames[2],bg=CARD); chosen_intro.pack(fill='x',pady=(0,6))
        tk.Label(chosen_intro,text='Negatives for the selected category',bg=CARD,fg=MUTED,font=FONT_CAPTION).place(relx=.5,rely=.5,anchor='center')
        chosen_intro.pack_propagate(False)
        chosen_intro.configure(height=search.winfo_reqheight())
        search.bind('<Configure>',lambda e:chosen_intro.configure(height=e.height))
        self.available=ColorSwatchList(frames[1],height=260,on_activate=lambda _:self.add_selected())
        self.available.pack(fill='both',expand=True)
        self.chosen=ColorSwatchList(frames[2],height=260,on_activate=lambda _:self.remove_selected())
        self.chosen.pack(fill='both',expand=True)
        actions=tk.Frame(frames[1],bg=CARD); actions.pack(fill='x',pady=(8,0))
        add_buttons=[]
        for text,cmd in (('Add granule',self.add_selected),('Add category',self.add_category),('Add all',self.add_all)):
            add_buttons.append(tk.Button(actions,text=text,command=cmd,bg=UI_ACCENT_SOFT,fg=UI_ACCENT,relief='flat',padx=7,pady=4))
        actions.columnconfigure(0,weight=1)
        actions.columnconfigure(4,weight=1)
        def layout_add_buttons(event=None, bar=actions, buttons=add_buttons):
            width = event.width if event is not None else bar.winfo_width()
            narrow = width < sum(b.winfo_reqwidth()+6 for b in buttons)
            if getattr(bar, '_narrow', None) == narrow: return
            bar._narrow = narrow
            for b in buttons: b.grid_forget()
            for i,b in enumerate(buttons):
                b.grid(row=1 if narrow and i==2 else 0,column=1 if narrow and i==2 else i+1,
                       columnspan=3 if narrow and i==2 else 1,padx=3,pady=2)
        actions.bind('<Configure>',layout_add_buttons)
        layout_add_buttons()
        actions=tk.Frame(frames[2],bg=CARD); actions.pack(pady=(8,0))
        tk.Button(actions,text='+ New negative',command=self.choose_color,bg=CARD,fg=UI_ACCENT,font=FONT_BOLD,relief='flat',bd=0,highlightthickness=0,activebackground=UI_ACCENT_SOFT,cursor='hand2',padx=8,pady=4).pack(side='left',padx=3)
        for text,cmd in (('Remove',self.remove_selected),('Remove all',self.clear)):
            tk.Button(actions,text=text,command=cmd,bg=CARD,fg='#B23F52',relief='flat',bd=0,highlightthickness=0,cursor='hand2',padx=5,pady=4).pack(side='left',padx=2)
        info=tk.Frame(self,bg=BG); info.pack(fill='x',padx=14,pady=(8,5))
        # Identical column weights to the three panels; neither a long name
        # nor an error message can move the explanatory label horizontally.
        for i, weight in enumerate((1, 2, 2)):
            info.columnconfigure(i, weight=weight, uniform='neg_info')
        counter = tk.Frame(info, bg=BG, height=32, width=1)
        counter.grid(row=0,column=0,sticky='ew',padx=(0,8))
        counter.pack_propagate(False)
        status_label = tk.Label(counter,textvariable=self.status,bg=BG,fg=PURPLE,font=FONT_CAPTION_BOLD,anchor='center',justify='center')
        status_label.pack(fill='both',expand=True)
        counter.bind('<Configure>', lambda e: status_label.configure(wraplength=max(1,e.width-4)))
        help_frame = tk.Frame(info,bg=BG,height=32,width=1)
        help_frame.grid(row=0,column=1,columnspan=2,sticky='ew')
        help_frame.pack_propagate(False)
        help_label = tk.Label(help_frame,text='Add granule: one prototype · Add category: all its granules · Add all: all other positives.',bg=BG,fg=MUTED,font=FONT_CAPTION,justify='center')
        help_label.pack(fill='both',expand=True)
        help_frame.bind('<Configure>',lambda e:help_label.configure(wraplength=max(1,e.width-8)))

        footer=tk.Frame(self,bg=BG);footer.pack(fill='x',padx=14,pady=(0,12))
        tk.Button(footer,text='Copy negatives to...',command=self.copy_sets,bg=BG,fg=PURPLE,font=FONT_BOLD,relief='flat',padx=7).pack(side='left')
        tk.Button(footer,text='Apply Changes',command=self.accept,bg=PURPLE,fg='white',font=FONT_BOLD,relief='flat',padx=16,pady=7).pack(side='right')
        tk.Button(footer,text='Cancel',command=self.cancel,bg='#E7E9ED',fg=TEXT,relief='flat',padx=16,pady=7).pack(side='right',padx=8)
        self.refresh()
        parent.update_idletasks()
        # Centre on the usable screen instead of the short creation dialog.
        # Reserve room for the Windows title bar and taskbar.
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w=min(1010,sw-40); h=min(650,sh-120)
        x=max(0,(sw-w)//2)
        y=max(0,(sh-70-h)//2)
        self.geometry(f'{w}x{h}+{x}+{y}'); self.minsize(min(760,w),min(480,h)); self.deiconify(); self.grab_set()

    def _item(self, name, p, coordinates=None):
        p=np.asarray(p,dtype=float)
        rgb=p if self.mode=='RGB' else skcolor.lab2rgb(p.reshape(1,1,3))[0,0]*255
        hx='#%02X%02X%02X'%tuple(np.rint(np.clip(rgb,0,255)).astype(int))
        return {'name':name,'hex':hx,'coordinates':coordinates if coordinates is not None else ', '.join(f'{v:.3f}'.rstrip('0').rstrip('.') for v in p)}

    def select_category(self, name):
        if name in self.categories and name!=self.owner:
            self.owner=name; self.refresh()

    def refresh(self):
        if not hasattr(self,'chosen'): return
        self.categories_list.set_items([self._item(k,next(iter(v.values())),f'{len(self.values[k])} negatives') for k,v in self.categories.items()],selected=self.owner,preserve_scroll=True)
        self.available_map={}
        self.available_owners={}
        needle=self.query.get().strip().casefold()
        for k,sites in self.categories.items():
            if k==self.owner: continue
            for g,p in sites.items():
                label=f'{k} / {g}'
                if needle not in label.casefold(): continue
                if label in self.available_map:
                    label=f'{label} [{len(self.available_map)+1}]'

                if any(np.linalg.norm(np.asarray(p)-q)<=Voronoi.DEFAULT_MERGE_EPS for q in self.values[self.owner]): continue
                self.available_map[label]=tuple(p)
                self.available_owners[label]=k
        self.available.set_items([self._item(n,p) for n,p in self.available_map.items()],preserve_scroll=True)
        self.negative_names = filter_negative_names(self.negative_names, self.values)
        self.chosen_map={}
        for i,p in enumerate(self.values[self.owner]):
            name=self.negative_names.get(tuple(p)) or next((f'{k} / {g}' for k,sites in self.categories.items() for g,q in sites.items() if k!=self.owner and np.linalg.norm(np.asarray(q)-p)<=Voronoi.DEFAULT_MERGE_EPS),f'Custom {i+1}')
            original=name
            suffix=2
            while name in self.chosen_map:
                name=f'{original} [{suffix}]'; suffix+=1
            self.chosen_map[name]=p
        self.chosen.set_items([self._item(n,p) for n,p in self.chosen_map.items()],preserve_scroll=True)
        self.status.set(f'{self.owner} · {len(self.values[self.owner])} negatives')

    def _add(self, points):
        try:
            candidate={**self.values,self.owner:self.values[self.owner]+list(points)}
            self.values=native_negative_sets(self.categories,candidate)
            self.refresh();return True
        except (ValueError,TypeError) as exc:
            self.status.set(str(exc));return False

    def add_selected(self):
        if self.available.selected in self.available_map:self._add([self.available_map[self.available.selected]])
    def add_category(self):
        owner=self.available_owners.get(self.available.selected)
        if owner is not None: self._add(self.categories[owner].values())
    def add_all(self):
        """All other positives, not just the current search results."""
        self._add(p for k, sites in self.categories.items() if k != self.owner
                  for p in sites.values())

    def choose_color(self):
        name_var = tk.StringVar(master=self, value='')
        def selected(lab, rgb, _hex, exact_lab, status_var):
            try:
                # Preserve exact LAB input; use exact native RGB integers for
                # RGB/HEX/visual selection instead of a LAB round trip.
                source = 'LAB' if exact_lab else 'RGB'
                point = negative_coordinate(lab if exact_lab else rgb, source, self.mode)
                if any(np.linalg.norm(np.asarray(point)-q)<=Voronoi.DEFAULT_MERGE_EPS
                       for q in self.values[self.owner]):
                    raise ValueError('This negative is already selected.')
                name = name_var.get().strip()
                if name_var.get():
                    name, error = check_label_name(name_var.get(), kind='Negative')
                    if error: raise ValueError(error)
                previous_name = self.negative_names.get(tuple(point))
                if name and previous_name and name != previous_name:
                    raise ValueError(f'This negative is already named {previous_name}. Use that name or leave it blank.')
                if not self._add([point]):
                    status_var.set(self.status.get()); return False
                if name:
                    self.negative_names[tuple(point)] = name
                    self.refresh()
                return True
            except (TypeError, ValueError, OverflowError) as exc:
                status_var.set(str(exc)); return False
        return open_square_color_picker(self.app,self,initial_rgb=(128,128,128),
            on_color_submit=selected, title='Add Negative Prototype',
            initial_mode=self.mode, submit_text='Add negative',
            external_name_var=name_var, name_label='Negative name')

    def _import_shortcut(self, _event=None):
        self.import_sets()
        return 'break' 
    def copy_sets(self):
        """Copy the current negative set to selected geometric categories."""
        source=self.owner
        names=[k for k in self.categories if k!=source]
        if not names:
            self.status.set('No other categories to copy to.'); return
        win=tk.Toplevel(self); win.withdraw(); win.title('Copy negative prototypes')
        win.configure(bg=BG); win.transient(self)
        header=tk.Frame(win,bg=CARD,highlightbackground=BORDER,highlightthickness=1)
        header.pack(fill='x',padx=12,pady=(12,8))
        tk.Label(header,text=f'Copy negatives from {source}',bg=CARD,fg=TEXT,font=FONT_TITLE,wraplength=420,justify='center').pack(padx=10,pady=(12,4))
        tk.Label(header,text='Choose destination categories. Existing negative sets are replaced. Own positives are excluded.',bg=CARD,fg=MUTED,font=FONT_CAPTION,justify='center',wraplength=410).pack(padx=10,pady=(0,12))
        content=tk.LabelFrame(win,text='Color categories',labelanchor='n',bg=CARD,fg=TEXT,font=FONT_BOLD,padx=8,pady=8)
        content.pack(fill='both',expand=True,padx=12,pady=(0,8))
        toolbar=tk.Frame(content,bg=CARD); toolbar.pack(fill='x',pady=(0,6))
        toolbar.columnconfigure(0,weight=1,uniform='copy_margin',minsize=70)
        toolbar.columnconfigure(2,weight=1,uniform='copy_margin',minsize=70)
        query=tk.StringVar(master=win); count=tk.StringVar(master=win)
        search=tk.Frame(toolbar,bg=CARD); search.grid(row=0,column=1)
        tk.Label(search,text='Search',bg=CARD,fg=TEXT,font=FONT_BOLD).pack(side='left',padx=(0,6))
        tk.Entry(search,textvariable=query,font=FONT,width=20,relief='solid',bd=1).pack(side='left')
        tk.Button(search,text='Clear',command=lambda:query.set(''),bg=CARD,fg=MUTED,relief='flat',bd=0,highlightthickness=0,cursor='hand2').pack(side='left')
        tk.Label(toolbar,textvariable=count,bg=CARD,fg=PURPLE,font=FONT_CAPTION).grid(row=0,column=2,sticky='e')
        listing=tk.Frame(content,bg=CARD,highlightbackground=BORDER,highlightthickness=1)
        listing.pack(fill='both',expand=True)
        canvas=tk.Canvas(listing,bg=CARD,highlightthickness=0,bd=0,height=260)
        scroll=styled_scrollbar(listing,orient='vertical',command=canvas.yview)
        scroll.pack(side='right',fill='y'); canvas.pack(side='left',fill='both',expand=True)
        canvas.configure(yscrollcommand=scroll.set)
        inner=tk.Frame(canvas,bg=CARD); item=canvas.create_window(0,0,window=inner,anchor='nw')
        inner.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(item,width=e.width))
        checked={k:tk.BooleanVar(master=win,value=False) for k in names}
        rows={}; status=tk.StringVar(master=win)
        def update_count():
            n=sum(v.get() for v in checked.values()); count.set(f'{n} selected')
            copy_button.configure(state='normal' if n else 'disabled')
            status.set('')
        def toggle(name):
            checked[name].set(not checked[name].get()); update_count()
        def wheel(event):
            if getattr(event,'num',None)==4 or getattr(event,'delta',0)>0: canvas.yview_scroll(-1,'units')
            elif getattr(event,'num',None)==5 or getattr(event,'delta',0)<0: canvas.yview_scroll(1,'units')
            return 'break'
        def bind_wheel(widget):
            for seq in ('<MouseWheel>','<Button-4>','<Button-5>'):widget.bind(seq,wheel)
        bind_wheel(canvas); bind_wheel(inner)
        for name in names:
            row=tk.Frame(inner,bg=CARD); rows[name]=row
            cb=tk.Checkbutton(row,variable=checked[name],command=update_count,bg=CARD,activebackground=CARD,selectcolor=CARD,cursor='hand2',bd=0,highlightthickness=0)
            cb.pack(side='left',padx=(5,3))
            color=self._item(name,next(iter(self.categories[name].values())))['hex']
            swatch=tk.Frame(row,bg=color,width=22,height=22,highlightbackground='#CCD1DA',highlightthickness=1)
            swatch.pack(side='left',padx=(0,8),pady=6)
            label=tk.Label(row,text=name,bg=CARD,fg=TEXT,font=FONT,anchor='w')
            label.pack(side='left',fill='x',expand=True)
            detail=tk.Label(row,text=f'{len(self.values[name])} negatives',bg=CARD,fg=MUTED,font=FONT_CAPTION)
            detail.pack(side='right',padx=8)
            for w in (row,swatch,label,detail):
                w.configure(cursor='hand2'); w.bind('<Button-1>',lambda e,k=name:toggle(k)); bind_wheel(w)
            bind_wheel(cb)
        empty=tk.Label(inner,text='No matching categories.',bg=CARD,fg=MUTED,font=FONT_CAPTION,pady=14)
        def render(*_):
            needle=query.get().strip().casefold()
            for row in rows.values():row.pack_forget()
            empty.pack_forget()
            visible=[k for k in names if needle in k.casefold()]
            for k in visible:rows[k].pack(fill='x',padx=2,pady=1)
            if not visible:empty.pack(fill='x')
            canvas.yview_moveto(0)
        def select_visible():
            needle=query.get().strip().casefold()
            for k,v in checked.items():
                if needle in k.casefold():v.set(True)
            update_count()
        def clear_selection():
            for v in checked.values():v.set(False)
            update_count()
        tools=tk.Frame(content,bg=CARD); tools.pack(side='bottom',pady=(6,0),before=listing)
        tk.Button(tools,text='Select visible',command=select_visible,bg=CARD,fg=PURPLE,relief='flat',bd=0,highlightthickness=0,cursor='hand2').pack(side='left',padx=4)
        tk.Button(tools,text='Clear selection',command=clear_selection,bg=CARD,fg=MUTED,relief='flat',bd=0,highlightthickness=0,cursor='hand2').pack(side='left',padx=4)
        def close():
            win.destroy()
            if self.winfo_exists():self.grab_set();self.focus_set()
        def apply():
            targets=[k for k in names if checked[k].get()]
            if not targets:return
            candidate={**self.values}
            for k in targets:
                candidate[k]=[p for p in self.values[source] if not any(np.linalg.norm(np.asarray(p)-q)<=Voronoi.DEFAULT_MERGE_EPS for q in self.categories[k].values())]
            try:self.values=native_negative_sets(self.categories,candidate)
            except (TypeError,ValueError) as exc:status.set(str(exc));return
            close();self.refresh()
        footer=tk.Frame(win,bg=BG);footer.pack(side='bottom',fill='x',padx=12,pady=(0,12),before=content)
        tk.Label(footer,textvariable=status,bg=BG,fg='#B23F52',font=FONT_CAPTION,wraplength=230,justify='left').pack(side='left',fill='x',expand=True)
        copy_button=tk.Button(footer,text='Copy',command=apply,bg=PURPLE,fg='white',font=FONT_BOLD,relief='flat',padx=16,pady=7)
        copy_button.pack(side='right')
        tk.Button(footer,text='Cancel',command=close,bg='#E7E9ED',fg=TEXT,relief='flat',padx=16,pady=7).pack(side='right',padx=8)
        query.trace_add('write',render); render(); update_count()
        win.protocol('WM_DELETE_WINDOW',close);win.bind('<Escape>',lambda e:close())
        w=min(520,win.winfo_screenwidth()-40);h=min(510,win.winfo_screenheight()-70)
        _center_auxiliary_popup(win,self,w,h);win.minsize(min(480,w),min(360,h))
        win.deiconify();win.grab_set();win.focus_set()
        return win

    def remove_selected(self):
        if self.chosen.selected in self.chosen_map:
            self.values[self.owner].remove(self.chosen_map[self.chosen.selected]);self.refresh()
    def clear(self):self.values[self.owner]=[];self.refresh()
    def import_sets(self):
        import json
        path=filedialog.askopenfilename(parent=self,filetypes=[('JSON files','*.json')])
        if not path:return
        try:
            from Source.input_output.InputJSON import InputJSON
            with open(path,encoding='utf-8-sig') as file:doc=json.load(file,object_pairs_hook=InputJSON._distinct_object_pairs)
            if doc.get('color_space')!=self.mode:raise ValueError('Import must use the current geometric model.')
            raw=doc.get('categories')
            if isinstance(raw,dict):raw={k:v['negatives'] for k,v in raw.items() if k in self.categories}
            elif isinstance(raw,list):raw={c['label']:c['negatives'] for c in raw if 'negatives' in c}
            else:raise ValueError('Expected category negative sets.')
            raw={k:[negative_coordinate(p,self.mode,self.mode) for p in v] for k,v in raw.items()}
            self.values=native_negative_sets(self.categories,raw);self.refresh()
        except (OSError,ValueError,KeyError,TypeError) as exc:self.status.set(f'Import failed: {exc}')
    def accept(self):
        try:
            self.result=native_negative_sets(self.categories,self.values)
            self.result_names=filter_negative_names(self.negative_names,self.result)
        except (ValueError,TypeError) as exc:self.status.set(str(exc));return
        self._close()
    def cancel(self):self.result=None;self._close()
    def _close(self):
        previous=self._previous_grab
        self.destroy()
        if previous is not None and previous.winfo_exists():previous.grab_set();previous.focus_set()


class FCSCreationDialog(tk.Toplevel):
    """Choose name, geometry, typology, scalings, bounds and negative colors.

    `on_accept(name, options)` validates model-specific conditions and initiates
    saving. If it raises, the dialog remains open with the input preserved.
    """

    def __init__(self, parent, selected_colors_lab, on_accept, warn=None,
                 initial_color_space="LAB", initial_name="", selected_categories=None, native_rgb=None, initial_negatives=None, app=None, initial_negative_names=None):
        super().__init__(parent)
        self.withdraw()
        self.title("New Fuzzy Color Space")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(720, 460)
        self.result = False
        self._on_accept = on_accept
        self._warn = warn
        self._app = app
        self._building = True
        self._save_pending = False
        self._colors = {str(name): np.asarray(lab, dtype=float).reshape(3)
                        for name, lab in selected_colors_lab.items()}
        self.names = list(self._colors)
        self._category_sites = selected_categories or {k:{k:v} for k,v in self._colors.items()}
        self._native_rgb_sites = native_rgb or {}
        self._custom_sets = dict(initial_negatives or {})
        self._custom_names = dict(initial_negative_names or {})
        self.negative_mode = tk.StringVar(value='Custom' if self._custom_sets else 'Automatic')
        self._rgb = {}
        self._swatches = {}
        for name, lab in self._colors.items():
            with np.errstate(invalid="ignore", over="ignore"):
                rgb = np.clip(skcolor.lab2rgb(lab.reshape(1, 1, 3))[0, 0] * 255.0, 0, 255)
            if not np.all(np.isfinite(rgb)):
                rgb = np.array([128, 128, 128], dtype=float)
            self._rgb[name] = rgb
            self._swatches[name] = "#%02X%02X%02X" % tuple(np.rint(rgb).astype(int))

        self.name_var = tk.StringVar(value=initial_name)
        # Creating a NEW fuzzy color space always starts in CIELAB.
        # The loaded FCS model is deliberately independent from this default;
        # RGB remains available when explicitly selected by the user.
        self.mode_var = tk.StringVar(value=initial_color_space if initial_color_space in ("LAB", "RGB") else "LAB")
        self.disjoint_var = tk.BooleanVar(value=True)
        self.covering_var = tk.BooleanVar(value=True)
        self.lambda1_var = tk.StringVar(value="0.5")
        self.lambda2_var = tk.StringVar(value="1.5")
        self.samples_var = tk.StringVar(value="27")
        self.typology_var = tk.StringVar(value="PARTITION")
        self.bounds_vars = [tk.StringVar() for _ in range(6)]

        self._build()
        self._building = False
        self._set_default_bounds()
        self._update_typology()
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
        opts.setdefault("justify", "center")
        return tk.Label(parent, text=text, textvariable=textvariable, bg=bg,
                        fg=MUTED, **opts)

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
        tk.Label(heading, text=title, font=FONT_BOLD, bg=CARD, fg=TEXT).pack(anchor="center")
        return card

    def _build(self):
        # Keep the required name visible, even when the configuration below is scrolled.
        # This prevents the user from reaching Create while the name is off-screen.
        header = tk.Frame(self, bg=CARD)
        self.header = header
        header.pack(fill="x")
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
        self.name_error.pack(anchor="center", pady=(3, 8))
        self.name_var.trace_add("write", self._name_changed)
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True)
        self.scroll = tk.Canvas(outer, bg=BG, bd=0, highlightthickness=0)
        self.scrollbar = styled_scrollbar(outer, orient="vertical", command=self.scroll.yview)
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
        self.advanced_summary = self._info(card_geometry, "", anchor="center")
        self.advanced_summary.pack(fill="x", padx=14, pady=(0, 11))
        # Like JFCS, expose the sample density as soon as Non-Covering is selected.
        # 27 denotes 3 per axis, not 27 stored auxiliary negatives: an expanded
        # candidate grid is filtered before the geometry is constructed.
        self.samples_box = tk.Frame(card_geometry, bg=CARD)
        tk.Label(self.samples_box, text="Auxiliary sampling", bg=CARD, fg=TEXT,
                 font=FONT).pack(side="left", padx=(0, 8))
        self.samples_combo = styled_combobox(
            self.samples_box, textvariable=self.samples_var,
            width=7, state="readonly", values=(8, 27, 64, 125, 216, 343, 512),
        )
        self.samples_combo.pack(side="left")
        self.geometry_details = tk.Frame(card_geometry, bg=CARD)
        params = tk.Frame(self.geometry_details, bg=CARD)
        params.pack(anchor="center", padx=14, pady=(3, 3))
        for title, var in (("Core (λ1)", self.lambda1_var), ("Support (λ2)", self.lambda2_var)):
            part = tk.Frame(params, bg=CARD)
            part.pack(side="left", padx=(0, 20))
            tk.Label(part, text=title, bg=CARD, fg=TEXT, font=FONT).pack(side="left", padx=(0, 7))
            field = self._field(part, var, width=7)
            field.configure(justify="center")
            field.pack(side="left", ipady=3)
        self._info(self.geometry_details, "Core: 0 ≤ λ1 < 1  ·  Support: 1 < λ2 ≤ 2",
                   anchor="center").pack(fill="x", padx=14, pady=(4, 9))
        row_bounds_heading = tk.Frame(self.geometry_details, bg=CARD)
        row_bounds_heading.pack(fill="x", padx=14)
        tk.Label(row_bounds_heading, text="Reference bounds", bg=CARD, fg=TEXT,
                 font=FONT_BOLD).pack(anchor="center")
        tk.Button(row_bounds_heading, text="Reset defaults", bg=CARD, fg=PURPLE,
                  font=FONT_CAPTION, cursor="hand2", relief="flat", bd=0,
                  activebackground=CARD, activeforeground=PURPLE_DARK,
                  command=self._set_default_bounds).place(relx=1.0, rely=0.5, anchor="e")
        grid = tk.Frame(self.geometry_details, bg=CARD)
        grid.pack(fill="x", padx=14, pady=(5, 10))
        self.bounds_labels = []
        for i, var in enumerate(self.bounds_vars):
            slot = tk.Frame(grid, bg=CARD)
            slot.grid(row=0, column=i, padx=(0, 8) if i < 5 else 0, sticky="ew")
            grid.columnconfigure(i, weight=1, uniform="bounds")
            label = tk.Label(slot, text="", bg=CARD, fg=MUTED, font=FONT_CAPTION)
            label.pack(anchor="center")
            self.bounds_labels.append(label)
            field = self._field(slot, var, width=8)
            field.configure(justify="center")
            field.pack(fill="x", ipady=3)

        self.neg_card = self._card(self.content, "Negative prototypes")
        self.negative_intro = self._info(self.neg_card,
                   "Negative prototypes define the geometric limits of each category. They do not create new colors.",
                   anchor="center", wraplength=620)
        self.negative_intro.pack(fill="x", padx=14, pady=(0, 8))
        row = tk.Frame(self.neg_card, bg=CARD)
        row.pack(anchor="center", padx=14, pady=(0, 6))
        tk.Label(row, text="Mode", bg=CARD, fg=TEXT, font=FONT_BOLD).pack(side="left", padx=(0, 8))
        self.negative_combo = styled_combobox(row, values=('Automatic','Custom'), textvariable=self.negative_mode, state='readonly',width=14)
        self.negative_combo.pack(side='left')
        self.negative_combo.bind("<<ComboboxSelected>>", self._negative_mode_changed)
        self.manage_button = tk.Button(row,text='Manage negatives...',command=self.manage_negatives,bg=UI_ACCENT_SOFT,fg=PURPLE,relief='flat',font=FONT_BOLD,padx=12,pady=4)
        self.manage_button.pack(side='left', padx=(14, 0))
        self.negative_status = self._info(self.neg_card, '',anchor='center',wraplength=620)
        self.negative_status.pack(fill='x',padx=14,pady=(0,10))

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

        for change_var in (self.lambda1_var, self.lambda2_var, self.samples_var):
            change_var.trace_add("write", lambda *_: self._update_advanced_summary())

    def _center_content(self, event):
        """Center the cards, leaving a sensible width at large DPI / screen sizes."""
        available = max(1, int(event.width))
        width = min(790, max(1, available - 24))
        self.scroll.itemconfigure(self._content_id, width=width)
        self.scroll.coords(self._content_id, max(0, (available - width) // 2), 0)
        wrap = max(240, width - 70)
        if hasattr(self, "negative_status"):
            self.negative_status.configure(wraplength=wrap)
            self.negative_intro.configure(wraplength=wrap)

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
        self._refresh_negative_lists()

    def _native_category_sites(self):
        from Source.fuzzy.FuzzyColorSpaceBuilder import lab_to_rgb_model_checked
        mode=self.mode_var.get()
        result={}
        for category, sites in self._category_sites.items():
            result[category]={}
            for label, lab in sites.items():
                if mode=='LAB': point=lab
                else:
                    point=self._native_rgb_sites.get(category,{}).get(label)
                    if point is None: point=lab_to_rgb_model_checked(np.asarray(lab,dtype=float).reshape(1,3))[0]
                result[category][label]=tuple(float(x) for x in point)
        return result

    def _negative_mode_changed(self, _event=None):
        self._refresh_negative_lists()
        self._fit_window()

    def _refresh_negative_lists(self):
        if not hasattr(self,'negative_status'): return
        custom=self.negative_mode.get()=='Custom'
        self.manage_button.configure(state='normal' if custom else 'disabled')
        sets=self._custom_sets.get(self.mode_var.get())
        if custom:
            text = 'Choose existing granules or define independent negative coordinates for each category.'
            if sets is not None:
                text += f'\n{sum(map(len, sets.values()))} negative assignments configured.'
            if self.covering_var.get():
                text += '\nCoverage is checked before saving.'
        else:
            text = 'Automatic (default): use all positive granules from the other categories as negatives.'
        self.negative_status.configure(text=text)

    def manage_negatives(self):
        try:
            sites=self._native_category_sites(); mode=self.mode_var.get()
            dialog=NegativePrototypeDialog(self,sites,mode,self._custom_sets.get(mode),warn=self._warn,app=self._app,negative_names=self._custom_names.get(mode))
            self.wait_window(dialog)
            if dialog.result is not None:
                self._custom_sets[mode]=dialog.result
                self._custom_names[mode]=dialog.result_names
            self._refresh_negative_lists()
            self._fit_window()
        except (ValueError,TypeError,KeyError,tk.TclError) as exc:
            self.negative_status.configure(text=str(exc))

    def _update_typology(self):
        disjoint, covering = self.disjoint_var.get(), self.covering_var.get()
        typology = ("PARTITION" if disjoint and covering else
                    ("DISJOINT" if disjoint else "NON-DISJOINT") + " and " +
                    ("COVERING" if covering else "NON-COVERING"))
        self.typology_var.set(typology)
        if covering:
            self.samples_box.pack_forget()
        elif not self.samples_box.winfo_manager():
            order = {"before": self.geometry_details} if self.geometry_details.winfo_manager() else {}
            self.samples_box.pack(anchor="center", pady=(0, 9), **order)
        if disjoint:
            self.neg_card.pack_forget()
        elif not self.neg_card.winfo_manager():
            self.neg_card.pack(fill="x", padx=17, pady=(0, 10))
        self._update_advanced_summary()
        self._refresh_negative_lists()
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
        _, error = check_color_space_name(self.name_var.get())
        if not error:
            return True
        self.name_error.configure(text=error)
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
        negative = None
        negative_names = {}
        if not disjoint:
            if self.negative_mode.get() == 'Automatic':
                negative = {k:[n for n in self.names if n!=k] for k in self.names}
            else:
                sets=self._custom_sets.get(self.mode_var.get())
                if sets is None:
                    raise ValueError('Configure custom negatives for the selected geometric model.')
                validated=native_negative_sets(self._native_category_sites(),sets)
                negative={k:[{'native':list(p)} for p in vals] for k,vals in validated.items()}
                negative_names=filter_negative_names(self._custom_names.get(self.mode_var.get()),validated)
        return name, {
            "color_space": self.mode_var.get().upper(),
            "reference_domain": domain,
            "lambda1": lam1, "lambda2": lam2,
            "disjoint": disjoint, "covering": covering,
            "samples": count, "negative_prototypes": negative,
            "negative_names": negative_names,
        }

    def _enter_key(self, event):
        # Let Enter activate a color when a swatch list has focus.
        if isinstance(event.widget, tk.Canvas):
            return
        self.confirm()

    def confirm(self):
        if self.result or self._save_pending:
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
            # the user declined to overwrite an existing .json). Keep editing.
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
        if self._save_pending:
            return
        self.result = True
        self.destroy()

    def begin_save(self):
        self._save_pending = True
        self.ok_button.configure(state='disabled')
        self.cancel_button.configure(state='disabled')

    def on_save_failure(self, message):
        if not self.winfo_exists(): return
        self._save_pending = False
        self.ok_button.configure(state='normal')
        self.cancel_button.configure(state='normal')
        self.negative_status.configure(text=str(message))
        self.deiconify(); self.lift(); self.grab_set()

    def on_save_success(self):
        if not self.winfo_exists(): return
        self._save_pending = False
        self.result = True
        self.destroy()

    def cancel(self):
        if self._save_pending: return
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



# Shared, precise color picker used by both Color Evaluation and palette
# granule creation/editing. The app provides only positioning, warnings and
# legacy callbacks; all widgets and their event state live here.

class _AccentSlider(tk.Canvas):
    """Compact, theme-independent channel slider with keyboard support.

    This deliberately uses Canvas instead of the platform-native
    ttk.Scale: Windows themes render the latter with a bulky trough
    and a gray handle that clash with the rest of PyFCS.
    """

    def __init__(self, master, command):
        super().__init__(
            master, width=175, height=24, bg="#FFFFFF",
            highlightthickness=0, bd=0, takefocus=1, cursor="hand2"
        )
        self._command = command
        self._minimum = 0.0
        self._maximum = 255.0
        self._step = 1.0
        self._value = 0.0
        self.bind("<Configure>", self._paint)
        self.bind("<Button-1>", self._mouse)
        self.bind("<B1-Motion>", self._mouse)
        self.bind("<Left>", lambda _e: self._move(-1))
        self.bind("<Right>", lambda _e: self._move(1))
        self.bind("<Home>", lambda _e: self._change(self._minimum))
        self.bind("<End>", lambda _e: self._change(self._maximum))

    def set_range(self, minimum, maximum, step):
        self._minimum = float(minimum)
        self._maximum = float(maximum)
        self._step = float(step)
        self.set(self._value)

    def set(self, value):
        self._value = max(
            self._minimum, min(self._maximum, float(value))
        )
        self._paint()

    def _paint(self, _event=None):
        w = max(25, self.winfo_width())
        h = max(20, self.winfo_height())
        left, right, cy = 10, w - 10, h / 2
        ratio = ((self._value - self._minimum) /
                 max(1e-12, self._maximum - self._minimum))
        x = left + ratio * (right - left)
        self.delete("all")
        self.create_line(left, cy, right, cy, fill="#E4E7ED",
                         width=5, capstyle="round")
        if x > left + 0.5:
            self.create_line(left, cy, x, cy, fill=UI_ACCENT,
                             width=5, capstyle="round")
        self.create_oval(x - 7, cy - 7, x + 7, cy + 7,
                         fill="#FFFFFF", outline=UI_ACCENT, width=2)

    def _change(self, value):
        value = max(self._minimum, min(self._maximum, float(value)))
        if self._step > 0:
            value = (self._minimum + round(
                (value - self._minimum) / self._step
            ) * self._step)
            value = max(self._minimum, min(self._maximum, value))
        if abs(value - self._value) < 1e-10:
            return "break"
        self.set(value)
        self._command(value)
        return "break"

    def _mouse(self, event):
        self.focus_set()
        right = max(11, self.winfo_width() - 10)
        ratio = max(0.0, min(1.0, (event.x - 10) / (right - 10)))
        return self._change(
            self._minimum + ratio * (self._maximum - self._minimum)
        )

    def _move(self, direction):
        return self._change(self._value + direction * self._step)



def open_square_color_picker(
    app, parent, initial_rgb=(217, 217, 217), on_apply=None,
    *, initial_lab=None, granule_name=None, on_granule_submit=None,
    submit_text=None, title=None, embedded_parent=None,
    compact=False, external_name_var=None, on_change=None,
    initial_empty=False, initial_mode=None, on_color_submit=None, name_label="Granule name",
):
    """Open the shared visual/numeric picker, optionally editing a granule.

    Normal mode retains the old ``on_apply(rgb, hex)`` contract.
    Optional ``on_color_submit(lab, rgb, hex, exact_lab, status_var)``
    is for unnamed colors requiring precise LAB and recoverable validation.
    A False return keeps the popup open.
    Granule mode adds a name and calls
    ``on_granule_submit(name, lab, rgb, hex, dialog, status_var)``.
    Return ``False`` from that callback to keep the dialog open after a
    validation error; all other return values mean success.

    LAB inputs remain exact while the user only changes the name or view
    mode. RGB/HSV/HSL/HEX edits intentionally create a new sRGB-derived LAB.
    """
    from tkinter import ttk
    import re

    ui = sys.modules[__name__]
    bg, card, soft = "#F5F6F8", "#FFFFFF", "#F6F7FA"
    text_color, muted, line_color = "#253044", "#667085", "#DBDFE6"
    accent, accent_soft = ui.UI_ACCENT, ui.UI_ACCENT_SOFT

    # One picker implementation can be hosted in a frame (Add Color Category)
    # or a standalone, modal Toplevel (Edit Granule / Color Evaluation).
    embedded = embedded_parent is not None
    previous_grab = None
    if embedded:
        popup = tk.Frame(embedded_parent, bg=bg)
        popup.pack(fill="both", expand=True)
    else:
        try:
            previous_grab = parent.grab_current()
        except tk.TclError:
            previous_grab = None
        popup = tk.Toplevel(parent)
        popup.withdraw()
    granule_mode = callable(on_granule_submit)
    display_title = title or ("Color Picker" if not granule_mode else "Edit Granule")
    # Normalize legacy callers without changing their public signature.
    for old_title, new_title in (("Add granule", "Add Granule"),
                                 ("Edit granule", "Edit Granule")):
        if display_title.startswith(old_title):
            display_title = new_title + display_title[len(old_title):]
            break
    if not embedded:
        popup.title(display_title)
        popup.configure(bg=bg)
        popup.resizable(False, False)
        popup.transient(parent)
        # Leave enough room for the footer even on scaled Windows displays.
        # The swatch and footer now fit in a shorter standalone window.
        # The embedded category editor keeps its own compact dimensions.
        win_w, win_h = 866, 548 if granule_mode or external_name_var is not None else 510
        try:
            app.center_popup_to_parent(popup, win_w, win_h, parent=parent)
        except Exception:
            if callable(getattr(app, 'center_popup', None)):
                app.center_popup(popup, win_w, win_h)
            else:
                parent.update_idletasks()
                win_w = min(win_w, popup.winfo_screenwidth()-20)
                win_h = min(win_h, popup.winfo_screenheight()-50)
                x = max(0, min(parent.winfo_rootx()+(parent.winfo_width()-win_w)//2, popup.winfo_screenwidth()-win_w))
                y = max(0, min(parent.winfo_rooty()+(parent.winfo_height()-win_h)//2, popup.winfo_screenheight()-win_h))
                popup.geometry(f'{win_w}x{win_h}+{x}+{y}')

    try:
        initial = tuple(ui.safe_rgb_tuple(initial_rgb))
    except (TypeError, ValueError):
        initial = (217, 217, 217)
    exact_initial_lab = None
    if initial_lab is not None:
        try:
            candidate = np.asarray(initial_lab, dtype=float).reshape(3)
            if np.all(np.isfinite(candidate)) and ui.is_valid_lab(candidate):
                exact_initial_lab = tuple(float(x) for x in candidate)
                initial = tuple(ui.safe_rgb_tuple(ui.lab_to_rgb(exact_initial_lab)))
        except (TypeError, ValueError):
            pass
    h, s, v = colorsys.rgb_to_hsv(*(x / 255.0 for x in initial))
    state = {
        "rgb": initial, "h": h, "s": s, "v": v,
        "exact_lab": exact_initial_lab,
        "sv_image": None, "hue_image": None, "updating": False,
        "last_image_hue": None, "display_mode": "RGB", "dirty": False,
        "chosen": not initial_empty,
    }

    sv_w, sv_h, hue_h = ((294, 160, 15) if compact else (382, 205, 17))
    hue_w = sv_w
    root = tk.Frame(popup, bg=bg)
    root.pack(fill="both", expand=True, padx=6 if compact else 15,
              pady=5 if compact else 12)

    if not embedded:
        top = tk.Frame(root, bg=card, highlightbackground=line_color, highlightthickness=1)
        top.pack(fill="x", pady=(0, 10))
        tk.Label(top, text=display_title, bg=card, fg=text_color,
                 font=("Segoe UI", 14, "bold"), anchor="w").pack(
                     side="left", padx=15, pady=11)
        tk.Label(top, text="Visual selection and precise adjustments", bg=card,
                 fg=muted, font=("Segoe UI", 9), anchor="e").pack(
                     side="right", padx=15)

    footer = None
    if not embedded:
        footer = tk.Frame(root, bg=bg)
        footer.pack(side="bottom", fill="x", pady=(8, 0))

    content = tk.Frame(root, bg=bg)
    content.pack(fill="both", expand=True)
    content.grid_columnconfigure(0, weight=1, minsize=319 if compact else 414)
    content.grid_columnconfigure(1, weight=1, minsize=340 if compact else 370)
    content.grid_rowconfigure(0, weight=1)

    visual_card = tk.Frame(content, bg=card, highlightbackground=line_color,
                           highlightthickness=1)
    visual_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
    editor_card = tk.Frame(content, bg=card, highlightbackground=line_color,
                           highlightthickness=1)
    editor_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

    # Keep the entire visual selector centered vertically, not just its title.
    # This also works in the compact embedded picker used by Add Category.
    visual_group = tk.Frame(visual_card, bg=card)
    visual_group.pack(expand=True, anchor="center")
    tk.Label(visual_group, text="Visual Selector", bg=card, fg=text_color,
             font=("Segoe UI", 10, "bold"), anchor="center").pack(
                 fill="x", padx=8 if compact else 13,
                 pady=(7 if compact else 12, 6 if compact else 8))

    sv_canvas = tk.Canvas(visual_group, width=sv_w, height=sv_h,
                          bg="#1f2430", bd=0, highlightthickness=1,
                          highlightbackground=line_color, cursor="crosshair")
    sv_canvas.pack(padx=8 if compact else 13)
    hue_canvas = tk.Canvas(visual_group, width=hue_w, height=hue_h,
                           bg=soft, bd=0, highlightthickness=1,
                           highlightbackground=line_color, cursor="hand2")
    hue_canvas.pack(padx=8 if compact else 13,
                    pady=(8 if compact else 10, 7 if compact else 8))

    tk.Label(visual_group, text="Quick colors", bg=card, fg=muted,
             font=("Segoe UI", 9, "bold"), anchor="center").pack(
                 fill="x", padx=8 if compact else 13,
                 pady=(0, 4 if compact else 6))
    preset_row = tk.Frame(visual_group, bg=card)
    preset_row.pack(anchor="center")
    # Neutrals first, then rainbow order (red through violet and pink).
    preset_colors = (
        ("Black", (0, 0, 0)), ("Gray", (128, 128, 128)),
        ("White", (255, 255, 255)), ("Red", (230, 45, 58)),
        ("Orange", (248, 141, 38)), ("Yellow", (250, 211, 24)),
        ("Green", (39, 172, 108)), ("Cyan", (46, 191, 200)),
        ("Blue", (50, 108, 220)), ("Violet", (144, 77, 181)),
        ("Magenta", (205, 55, 179)), ("Pink", (244, 152, 186)),
    )

    # Right side: optional granule name + editable channel controls.
    granule_name_var = (external_name_var if external_name_var is not None
                        else tk.StringVar(value=str(granule_name or "")))
    name_entry = None
    if granule_mode or external_name_var is not None:
        name_row = tk.Frame(editor_card, bg=card)
        name_row.pack(fill="x", padx=13, pady=(13, 2))
        tk.Label(name_row, text=name_label, bg=card, fg=text_color,
                 font=("Segoe UI", 10, "bold")).pack(side="left", padx=(0, 10))
        name_entry = tk.Entry(name_row, textvariable=granule_name_var,
                              font=("Segoe UI", 10), relief="solid", bd=1)
        name_entry.pack(side="left", fill="x", expand=True)
        name_entry.configure(
            validate="key",
            validatecommand=(popup.register(
                lambda proposed: len(proposed) <= ui.MAX_COLOR_NAME_CHARS), "%P"),
        )

    controls_heading = tk.Frame(editor_card, bg=card)
    controls_heading.pack(fill="x", padx=13,
                          pady=(6 if compact else 12, 5 if compact else 8))
    tk.Label(controls_heading, text="Fine adjustments", bg=card,
             fg=text_color, font=("Segoe UI", 10, "bold")).pack(side="left")
    mode_var = tk.StringVar(value=preferred_picker_mode(
        app if granule_mode else None, initial_mode,
        fallback="LAB" if exact_initial_lab is not None else "RGB"))
    mode_choice = styled_combobox(
        controls_heading, textvariable=mode_var, state="readonly",
        values=("RGB", "HSV", "HSL", "LAB", "HEX"), width=7)
    mode_choice.pack(side="right")

    mode_hint = tk.StringVar(value="Channels 0–255 · exact integers")
    tk.Label(editor_card, textvariable=mode_hint, bg=card, fg=muted,
             font=("Segoe UI", 9), anchor="w").pack(
                 fill="x", padx=13, pady=(0, 7))

    # Keep both numeric and HEX controls in one fixed layout position.
    # Otherwise calling pack() for HEX after the preview has been created
    # places the entry below the preview instead of under Fine adjustments.
    channel_slot = tk.Frame(editor_card, bg=card)
    channel_slot.pack(fill="x", padx=13)
    numeric_area = tk.Frame(channel_slot, bg=card)
    numeric_area.pack(fill="x")
    numeric_vars = [tk.StringVar() for _ in range(3)]
    numeric_labels = []
    numeric_scales = []
    numeric_spins = []

    for i in range(3):
        row = tk.Frame(numeric_area, bg=card)
        row.pack(fill="x", pady=4 if compact else 7)
        label = tk.Label(row, text=("R", "G", "B")[i], bg=card,
                         fg=text_color, font=("Segoe UI", 10, "bold"),
                         width=4, anchor="w")
        label.pack(side="left", padx=(0, 5))
        spin = tk.Spinbox(row, textvariable=numeric_vars[i], from_=0, to=255,
                          increment=1, width=7, justify="center",
                          font=("Segoe UI", 10), relief="solid", bd=1)
        # Reserve the numeric field first; the flexible Canvas slider
        # then consumes the remaining width instead of hiding Spinbox.
        spin.pack(side="right")
        scale = _AccentSlider(
            row, command=lambda value, ix=i: _on_scale(ix, value)
        )
        scale.pack(side="left", fill="x", expand=True, padx=(0, 12))
        numeric_labels.append(label)
        numeric_scales.append(scale)
        numeric_spins.append(spin)

    hex_area = tk.Frame(channel_slot, bg=card)
    hex_input_var = tk.StringVar()

    def _mark_dirty(*_args):
        if not state["updating"]:
            state["dirty"] = True

    for variable in (*numeric_vars, hex_input_var):
        variable.trace_add("write", _mark_dirty)

    tk.Label(hex_area, text="HEX", bg=card, fg=text_color,
             font=("Segoe UI", 10, "bold"), width=5, anchor="w").pack(side="left")
    hex_entry = tk.Entry(hex_area, textvariable=hex_input_var,
                         font=("Consolas", 12), relief="solid", bd=1)
    hex_entry.pack(side="left", fill="x", expand=True, padx=(5, 0))
    tk.Label(editor_card, text="Type a value or adjust the sliders.",
             bg=card, fg=muted, font=("Segoe UI", 9), anchor="w").pack(
                 fill="x", padx=13,
                 pady=(4 if compact else 8, 6 if compact else 12))

    # An achromatic, neutral gray surround lets the two patches be compared
    # without the subtle blue cast of the surrounding application panels.
    # The swatches themselves always share this exact surround.
    comparison_bg = "#EDEDED"
    comparison_border = "#C8C8C8"
    preview_info = tk.Frame(editor_card, bg=comparison_bg,
                            highlightbackground=comparison_border,
                            highlightthickness=1)
    preview_info.pack(fill="x", padx=8 if compact else 13,
                      pady=(0, 5 if compact else 12))
    # All picker contexts already identify this area. One heading-free
    # comparison, shared with Add Color Category, saves substantial height.
    before_after = tk.Frame(preview_info, bg=comparison_bg)
    before_after.pack(fill="x", padx=11, pady=(8, 0))

    if exact_initial_lab is not None:
        # Original and edited patches are equally sized and vertically
        # aligned; otherwise their differing widths bias the comparison.
        for column in (0, 1):
            before_after.grid_columnconfigure(
                column, weight=1, uniform="color_comparison")
        original_group = tk.Frame(before_after, bg=comparison_bg)
        original_group.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        tk.Label(original_group, text="Original", bg=comparison_bg,
                 fg=muted, font=("Segoe UI", 8)).pack(
                     fill="x", pady=(0, 4))
        original_swatch = tk.Frame(
            original_group, bg=ui.rgb_to_hex(initial), height=42,
            highlightbackground=comparison_border, highlightthickness=1)
        original_swatch.pack(fill="x")
        original_swatch.pack_propagate(False)

        current_group = tk.Frame(before_after, bg=comparison_bg)
        current_group.grid(row=0, column=1, sticky="ew", padx=(5, 0))
        tk.Label(current_group, text="Current", bg=comparison_bg,
                 fg=muted, font=("Segoe UI", 8)).pack(
                     fill="x", pady=(0, 4))
        current_swatch = tk.Frame(
            current_group, bg=ui.rgb_to_hex(initial), height=42,
            highlightbackground=comparison_border, highlightthickness=1)
        current_swatch.pack(fill="x")
        current_swatch.pack_propagate(False)
    else:
        current_swatch = tk.Frame(
            before_after, bg=ui.rgb_to_hex(initial), height=42,
            highlightbackground=comparison_border, highlightthickness=1)
        current_swatch.pack(fill="x")
        current_swatch.pack_propagate(False)

    info_hex_var = tk.StringVar()
    info_rgb_var = tk.StringVar()
    info_lab_var = tk.StringVar()
    # Show the color coordinates complementary to the current input mode.
    # Two representations share a centered row; modes without one of these
    # three representations use a compact second row for the third value.
    info_grid = tk.Frame(preview_info, bg=comparison_bg)
    info_grid.pack(anchor="center", pady=(7, 8))
    complement_labels = []
    complement_values = []
    complement_widgets = []
    for _ in range(3):
        caption = tk.StringVar()
        value = tk.StringVar()
        complement_labels.append(caption)
        complement_values.append(value)
        pair = tk.Frame(info_grid, bg=comparison_bg)
        tk.Label(pair, textvariable=caption, bg=comparison_bg, fg=muted,
                 font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 6))
        tk.Label(pair, textvariable=value, bg=comparison_bg,
                 fg=text_color, font=("Consolas", 8)).pack(side="left")
        complement_widgets.append(pair)

    status_var = tk.StringVar(value="Adjust the color visually or enter exact values.")
    if not embedded:
        tk.Label(footer, textvariable=status_var, bg=bg, fg=muted,
                 font=("Segoe UI", 9), anchor="w").pack(
                     side="left", fill="x", expand=True)

    # Image generation: the hue bar stays cached; the SV image is only
    # rebuilt when its hue really changes (never on SV dragging).
    def _hue_image():
        line = np.empty((hue_w, 3), dtype=np.uint8)
        for x in range(hue_w):
            rr, gg, bb = colorsys.hsv_to_rgb(x / (hue_w - 1), 1, 1)
            line[x] = (int(round(255 * rr)), int(round(255 * gg)),
                       int(round(255 * bb)))
        pixels = np.tile(line[np.newaxis, :, :], (hue_h, 1, 1))
        return ImageTk.PhotoImage(Image.fromarray(pixels, "RGB"))

    def _sv_image(hue):
        ss = np.linspace(0, 1, sv_w, dtype=np.float32)[None, :]
        vv = np.linspace(1, 0, sv_h, dtype=np.float32)[:, None]
        position = (hue % 1.0) * 6
        sector = int(position) % 6
        fraction = position - int(position)
        # Broadcast both dimensions for every HSV component.
        val = np.broadcast_to(vv, (sv_h, sv_w))
        low = val * (1 - ss)
        down = val * (1 - fraction * ss)
        up = val * (1 - (1 - fraction) * ss)
        channels = (
            (val, up, low), (down, val, low),
            (low, val, up), (low, down, val),
            (up, low, val), (val, low, down),
        )[sector]
        pixels = np.stack(channels, axis=-1)
        pixels = np.clip(pixels * 255, 0, 255).astype(np.uint8)
        return ImageTk.PhotoImage(Image.fromarray(pixels, "RGB"))

    state["hue_image"] = _hue_image()
    hue_canvas.create_image(0, 0, anchor="nw", image=state["hue_image"])
    state["sv_image"] = _sv_image(state["h"])
    image_id = sv_canvas.create_image(0, 0, anchor="nw", image=state["sv_image"])
    state["last_image_hue"] = state["h"]
    sv_shadow = sv_canvas.create_oval(0, 0, 0, 0, outline="#242835", width=4)
    sv_marker = sv_canvas.create_oval(0, 0, 0, 0, outline="white", width=2)
    hue_marker = hue_canvas.create_rectangle(0, 0, 0, hue_h,
                                              outline="white", width=2)

    def _current_hex():
        return "#{:02X}{:02X}{:02X}".format(*state["rgb"])

    def _normal_values(mode):
        rgb = state["rgb"]
        if mode == "RGB":
            return (("R", "G", "B"), (0, 0, 0), (255, 255, 255), rgb, (1, 1, 1))
        if mode == "HSV":
            return (("H°", "S%", "V%"), (0, 0, 0), (360, 100, 100),
                    (state["h"] * 360, state["s"] * 100, state["v"] * 100),
                    (1, 1, 1))
        if mode == "HSL":
            hh, ll, ss = colorsys.rgb_to_hls(*(v / 255.0 for v in rgb))
            if ss <= 0.000001:
                hh = state["h"]
            return (("H°", "S%", "L%"), (0, 0, 0), (360, 100, 100),
                    (hh * 360, ss * 100, ll * 100), (1, 1, 1))
        lab = (state["exact_lab"] if state["exact_lab"] is not None
               else ui.rgb_to_lab(rgb))
        return (("L*", "a*", "b*"), (0, -128, -128), (100, 128, 128),
                tuple(float(x) for x in lab[:3]), (0.1, 0.1, 0.1))

    def _format_number(number, mode):
        if mode in ("RGB", "HSV", "HSL"):
            return str(int(round(number)))
        # Preserve original precision in LAB; do not silently quantize
        # prototypes on a name-only edit or a change of display mode.
        return f"{float(number):.15g}"

    def _sync_numeric():
        mode = mode_var.get()
        state["updating"] = True
        state["display_mode"] = mode
        try:
            if mode == "HEX":
                numeric_area.pack_forget()
                hex_area.pack(fill="x", pady=7)
                hex_input_var.set(
                    _current_hex() if state["chosen"] or not embedded else "")
                mode_hint.set("Hexadecimal: #RRGGBB")
            else:
                hex_area.pack_forget()
                numeric_area.pack(fill="x")
                labels, lo, hi, values, increments = _normal_values(mode)
                mode_hint.set({
                    "RGB": "Channels 0–255 · exact integers",
                    "HSV": "Hue 0–360° · saturation and value 0–100%",
                    "HSL": "Hue 0–360° · saturation and lightness 0–100%",
                    "LAB": "CIELAB · values displayed in sRGB preview",
                }[mode])
                for i in range(3):
                    numeric_labels[i].configure(text=labels[i])
                    numeric_scales[i].set_range(
                        lo[i], hi[i], increments[i]
                    )
                    numeric_scales[i].set(values[i])
                    numeric_spins[i].configure(from_=lo[i], to=hi[i],
                                               increment=increments[i])
                    numeric_vars[i].set(
                        _format_number(values[i], mode)
                        if state["chosen"] or not embedded else "")
        finally:
            state["updating"] = False
            state["dirty"] = False
        # Show only complementary coordinates in both standalone and embedded
        # pickers, avoiding redundant display of the actively edited mode.
        available = (("HEX", info_hex_var.get()),
                     ("RGB", info_rgb_var.get()),
                     ("CIELAB", info_lab_var.get()))
        excluded = "CIELAB" if mode == "LAB" else mode
        shown = ([item for item in available if item[0] != excluded]
                 if mode in ("RGB", "LAB", "HEX") else list(available))
        for pair in complement_widgets:
            pair.grid_forget()
        for index, (caption, value) in enumerate(shown):
            complement_labels[index].set(caption)
            complement_values[index].set(value if state["chosen"] else "—")
            pair = complement_widgets[index]
            if index == 2:
                pair.grid(row=1, column=0, columnspan=2, padx=8, pady=2)
            else:
                pair.grid(row=0, column=index, padx=8, pady=2)

    def _redraw(regenerate=False):
        # Drawing is local: do not reconstruct widgets when a color changes.
        if regenerate or abs(state["last_image_hue"] - state["h"]) > 1e-7:
            state["sv_image"] = _sv_image(state["h"])
            sv_canvas.itemconfigure(image_id, image=state["sv_image"])
            state["last_image_hue"] = state["h"]
        mx = state["s"] * (sv_w - 1)
        my = (1 - state["v"]) * (sv_h - 1)
        sv_canvas.coords(sv_shadow, mx - 7, my - 7, mx + 7, my + 7)
        sv_canvas.coords(sv_marker, mx - 5, my - 5, mx + 5, my + 5)
        hx = (state["h"] % 1.0) * (hue_w - 1)
        hue_canvas.coords(hue_marker, hx - 3, 0, hx + 3, hue_h)
        current_swatch.configure(bg=_current_hex() if state["chosen"]
                                 else comparison_bg)
        info_hex_var.set(_current_hex())
        info_rgb_var.set(", ".join(str(int(c)) for c in state["rgb"]))
        lab = (state["exact_lab"] if state["exact_lab"] is not None
               else ui.rgb_to_lab(state["rgb"]))
        info_lab_var.set(", ".join(f"{float(x):.1f}" for x in lab[:3]))
        _sync_numeric()
        if callable(on_change):
            try:
                if state["chosen"]:
                    picked_lab = (state["exact_lab"] if state["exact_lab"] is not None
                                  else tuple(float(x) for x in ui.rgb_to_lab(state["rgb"])))
                    on_change(tuple(picked_lab), tuple(state["rgb"]), _current_hex())
                else:
                    on_change(None, None, None)
            except Exception:
                # Never allow an inline UI callback to terminate Tk's event loop.
                import logging
                logging.getLogger(__name__).exception(
                    "Embedded color selection update failed")

    def _apply_rgb(rgb):
        try:
            color = tuple(max(0, min(255, int(round(float(c))))) for c in rgb)
            if len(color) != 3:
                return
        except (TypeError, ValueError):
            return
        h_, s_, v_ = colorsys.rgb_to_hsv(*(c / 255.0 for c in color))
        if s_ <= 1e-9:
            h_ = state["h"]  # keep previous hue for an achromatic color
        state.update(rgb=color, h=h_, s=s_, v=v_, exact_lab=None, chosen=True)
        _redraw()
        status_var.set("Color updated.")

    def _apply_hsv(hue, saturation, value):
        hh, ss, vv = (hue % 1.0), min(1, max(0, saturation)), min(1, max(0, value))
        r, g, b = colorsys.hsv_to_rgb(hh, ss, vv)
        state.update(h=hh, s=ss, v=vv, exact_lab=None, chosen=True,
                     rgb=tuple(max(0, min(255, int(round(c * 255)))) for c in (r, g, b)))
        _redraw()
        status_var.set("Color updated.")

    def _apply_channel_values(values, mode):
        """Apply a fully validated channel tuple as one atomic change."""
        if mode == "RGB":
            _apply_rgb(values)
        elif mode == "HSV":
            _apply_hsv(values[0] / 360.0, values[1] / 100.0,
                       values[2] / 100.0)
        elif mode == "HSL":
            rr, gg, bb = colorsys.hls_to_rgb(
                values[0] / 360.0, values[2] / 100.0,
                values[1] / 100.0
            )
            _apply_rgb((255.0 * rr, 255.0 * gg, 255.0 * bb))
        elif mode == "LAB":
            rgb = tuple(ui.safe_rgb_tuple(ui.lab_to_rgb(values)))
            hh, ss, vv = colorsys.rgb_to_hsv(*(c / 255.0 for c in rgb))
            if ss <= 1e-9:
                hh = state["h"]
            # Update once, without an intermediate rounded-LAB notification.
            state.update(rgb=rgb, h=hh, s=ss, v=vv, chosen=True,
                         exact_lab=tuple(float(x) for x in values))
            _redraw()
            status_var.set(
                "Exact LAB retained; sRGB preview may clip out-of-gamut colors."
            )

    def _read_channels(mode_override=None):
        """Commit only valid values; never raise from a Tk callback."""
        if not state["dirty"]:
            return True
        mode = mode_override or state.get("display_mode", mode_var.get())
        try:
            if mode == "HEX":
                entered = hex_input_var.get().strip()
                if re.fullmatch(r"#?[0-9a-fA-F]{6}", entered) is None:
                    status_var.set("HEX must contain exactly 6 hexadecimal digits.")
                    return False
                value = entered.lstrip("#")
                _apply_rgb(tuple(
                    int(value[i:i + 2], 16) for i in (0, 2, 4)
                ))
                return True

            labels, minimum, maximum, _, _ = _normal_values(mode)
            # In RGB do not accept decimal values, exponent syntax,
            # NaN, infinity or whitespace as integer channel inputs.
            raw = tuple(var.get().strip() for var in numeric_vars)
            if mode == "RGB":
                if any(re.fullmatch(r"[0-9]+", part) is None
                       for part in raw):
                    status_var.set("RGB channels must be whole numbers from 0 to 255.")
                    return False
                values = tuple(float(part) for part in raw)
            else:
                values = tuple(float(part) for part in raw)
            if any(not np.isfinite(x) for x in values):
                status_var.set("Use finite numeric values only.")
                return False
            for label, value, lower, upper in zip(
                labels, values, minimum, maximum
            ):
                if not lower <= value <= upper:
                    status_var.set(
                        f"{label} must be between {lower:g} and {upper:g}."
                    )
                    return False
            _apply_channel_values(values, mode)
            return True
        except (ValueError, TypeError, OverflowError, FloatingPointError):
            status_var.set("Invalid input. Check the channel values.")
            return False

    def _commit_channels(_event=None):
        """Revert invalid edits without affecting the accepted color."""
        if not state["dirty"]:
            return "break"
        # A newly cleared inline form starts empty. Let the user fill R,
        # G and B (or all LAB channels) successively without discarding
        # the first value as soon as its field loses focus.
        if embedded and not state["chosen"]:
            mode = state.get("display_mode", mode_var.get())
            if mode == "HEX" and not hex_input_var.get().strip():
                return "break"
            if mode != "HEX" and any(not item.get().strip()
                                      for item in numeric_vars):
                return "break"
        if not _read_channels():
            reason = status_var.get()
            _sync_numeric()  # Restore the last accepted, precise value.
            status_var.set(f"{reason} Previous color restored.")
        return "break"

    def _on_scale(index, value):
        """Sliders always start from the last *valid* color.

        In particular, an invalid or half-entered Spinbox value cannot
        block dragging a slider or sneak into the next color update.
        """
        if state["updating"]:
            return
        mode = mode_var.get()
        if mode == "HEX":
            return
        try:
            _, minimum, maximum, accepted, increments = _normal_values(mode)
            values = list(accepted)
            step = increments[index]
            changed = max(minimum[index], min(maximum[index], float(value)))
            if step >= 1:
                changed = float(round(changed))
            else:
                changed = round(changed / step) * step
            values[index] = changed
            _apply_channel_values(tuple(values), mode)
        except (ValueError, TypeError, OverflowError, FloatingPointError):
            _sync_numeric()
            status_var.set("Could not apply slider value; previous color retained.")

    # All widget callbacks are guarded. Invalid text is never allowed to
    # propagate ValueError through Tkinter's event loop.
    for spin in numeric_spins:
        spin.configure(command=_commit_channels)
        spin.bind("<Return>", _commit_channels)
        spin.bind("<FocusOut>", _commit_channels)
    hex_entry.bind("<Return>", _commit_channels)
    hex_entry.bind("<FocusOut>", _commit_channels)

    def _on_mode_change(_event=None):
        previous = state.get("display_mode", "RGB")
        valid = True
        if previous != mode_var.get() and state["dirty"]:
            # Display-only mode changes must not roundtrip exact LAB.
            valid = _read_channels(previous)
        reason = status_var.get() if not valid else ""
        _sync_numeric()
        status_var.set(
            f"{reason} Previous color restored." if not valid
            else "Enter a value or adjust the sliders."
        )

    mode_choice.bind("<<ComboboxSelected>>", _on_mode_change)

    def _on_sv(event):
        x = max(0, min(sv_w - 1, event.x))
        y = max(0, min(sv_h - 1, event.y))
        _apply_hsv(state["h"], x / (sv_w - 1), 1 - y / (sv_h - 1))

    def _on_hue(event):
        x = max(0, min(hue_w - 1, event.x))
        _apply_hsv(x / (hue_w - 1), state["s"], state["v"])

    for name, callback in (("<Button-1>", _on_sv), ("<B1-Motion>", _on_sv)):
        sv_canvas.bind(name, callback)
    for name, callback in (("<Button-1>", _on_hue), ("<B1-Motion>", _on_hue)):
        hue_canvas.bind(name, callback)

    for label, rgb in preset_colors:
        color_hex = ui.rgb_to_hex(rgb)
        btn = tk.Button(
            preset_row, width=2, height=1, bg=color_hex,
            activebackground=color_hex, bd=1, relief="solid",
            padx=0, pady=0, highlightthickness=0,
            font=("Segoe UI", 9), cursor="hand2",
            command=lambda color=rgb: _apply_rgb(color))
        btn.pack(side="left", padx=2)
        # A short label on hover; no additional tooltip dependencies.
        btn.bind("<Enter>", lambda _e, text=label: status_var.set(text))
        btn.bind("<Leave>", lambda _e: status_var.set("Adjust the color visually or enter values."))

    def _close_picker():
        try:
            if popup.grab_current() == popup:
                popup.grab_release()
        except tk.TclError:
            pass
        popup.destroy()
        try:
            if previous_grab is not None and previous_grab.winfo_exists():
                previous_grab.grab_set()
                previous_grab.focus_set()
        except tk.TclError:
            pass

    def _validation_warning(message):
        """Report recoverable validation errors without closing the picker."""
        message = str(message or "Please check the granule information.")
        status_var.set(message)
        try:
            app.custom_warning("Invalid Granule", message, parent=popup)
        except (AttributeError, tk.TclError):
            # Keep the inline status usable even in minimal/embedded UIs.
            pass

    def _select():
        # A display-only mode switch must not quantize the chosen color.
        if state["dirty"] and not _read_channels():
            if granule_mode:
                _validation_warning(status_var.get())
            return
        selected = tuple(state["rgb"])
        if granule_mode:
            name, error = check_label_name(granule_name_var.get(), kind="Granule")
            if error:
                _validation_warning(error)
                return
            lab = (state["exact_lab"] if state["exact_lab"] is not None
                   else tuple(float(v) for v in ui.rgb_to_lab(selected)))
            try:
                accepted = on_granule_submit(
                    name, lab, selected, _current_hex(), popup, status_var)
            except Exception as exc:
                # Never leak callback failures through the Tk event loop.
                # Ordinary user validation takes the non-exceptional False path.
                import logging
                logging.getLogger(__name__).exception("Granule save failed")
                _validation_warning(f"Could not save granule: {exc}")
                return
            if accepted is False:
                _validation_warning(status_var.get())
                return
        elif callable(on_color_submit):
            try:
                exact_lab = state['exact_lab'] is not None
                lab = state['exact_lab'] if exact_lab else tuple(float(v) for v in ui.rgb_to_lab(selected))
                if on_color_submit(lab, selected, _current_hex(), exact_lab, status_var) is False:
                    return
            except Exception as exc:
                import logging
                logging.getLogger(__name__).exception('Color submission failed')
                status_var.set(f'Could not apply color: {exc}')
                return
        elif callable(on_apply):
            try:
                on_apply(selected, _current_hex())
            except Exception as exc:
                import logging
                logging.getLogger(__name__).exception("Color selection callback failed")
                status_var.set(f"Could not apply color: {exc}")
                return
        _close_picker()

    if not embedded:
        tk.Button(
            footer, text="Cancel", font=("Segoe UI", 10), bg="#ECEEF2",
            fg=text_color, relief="flat", bd=0, padx=17, pady=8,
            command=_close_picker).pack(side="right", padx=(9, 0))
        tk.Button(
            footer, text=(submit_text or ("Save changes" if granule_mode else "Select color")),
            font=("Segoe UI", 10, "bold"),
            bg=accent, fg="white", activebackground=ui.UI_ACCENT_DARK,
            activeforeground="white", relief="flat", bd=0, padx=18,
            pady=8, command=_select).pack(side="right")
        popup.protocol("WM_DELETE_WINDOW", _close_picker)
        popup.bind("<Escape>", lambda _event: _close_picker())

    _redraw()
    if not embedded:
        popup.deiconify()
        popup.grab_set()
        return popup

    class EmbeddedColorPicker:
        """Small, reusable API for the same editor embedded in a parent."""

        def __init__(self):
            self.frame = popup
            self.mode_var = mode_var
            self.name_entry = name_entry
            self.status_var = status_var

        def get_color(self):
            if state["dirty"] and not _read_channels():
                _commit_channels()
                return None
            if not state["chosen"]:
                return None
            lab = (state["exact_lab"] if state["exact_lab"] is not None
                   else tuple(float(x) for x in ui.rgb_to_lab(state["rgb"])))
            return tuple(lab), tuple(state["rgb"]), _current_hex()

        def set_lab(self, lab, *, mode="LAB"):
            try:
                point = np.asarray(lab, dtype=float).reshape(3)
                if not np.all(np.isfinite(point)) or not ui.is_valid_lab(point):
                    return False
            except (TypeError, ValueError, OverflowError):
                return False
            # Do not convert the saved LAB to an 8-bit value and back.
            rgb = tuple(ui.safe_rgb_tuple(ui.lab_to_rgb(point)))
            hh, ss, vv = colorsys.rgb_to_hsv(*(x / 255.0 for x in rgb))
            if ss <= 1e-9:
                hh = state["h"]
            state.update(rgb=rgb, h=hh, s=ss, v=vv, chosen=True,
                         exact_lab=tuple(float(x) for x in point))
            mode_var.set(mode if mode in ("RGB", "HSV", "HSL", "LAB", "HEX")
                         else "LAB")
            _redraw()
            return True

        def clear(self):
            # The starting neutral color is a visual reference, not a new site.
            rgb = (217, 217, 217)
            hh, ss, vv = colorsys.rgb_to_hsv(*(x / 255.0 for x in rgb))
            state.update(rgb=rgb, h=hh, s=ss, v=vv, chosen=False,
                         exact_lab=None)
            _redraw()

        def select_mode(self, mode):
            if mode not in ("RGB", "HSV", "HSL", "LAB", "HEX"):
                return
            mode_var.set(mode)
            _on_mode_change()

    return EmbeddedColorPicker()



# Palette creation: a category starts with a color; further granules are optional.
# Kept with the shared interface utilities to avoid another UI module.

class CustomCategoryDialog:
    """Build a palette category by adding one or more positive granules.

    The input panel is always the same, whether the category ends up atomic or
    granular. Colors are appended explicitly, and the category is committed
    only when the user presses Create Category. LAB input is never roundtripped
    through an 8-bit RGB preview.
    """

    def __init__(self, palette):
        self.palette = palette
        self.app = palette.app
        self.granules = []  # All granules; no special, implicit first color.
        self._cached_lab = None
        self._cached_rgb = None
        self._pending_refresh = None
        self._scroll_region_after_id = None
        self.name_var = tk.StringVar(value="")
        self.parent_category = getattr(palette, "parent_category", None)
        self.original_child_parent = getattr(palette, "original_child_parent", None)
        self.original_child_var = tk.StringVar(value="")
        self.original_child_entry = None
        # Only the suggested default is derived from the category name.
        # The user can give every granule an independent label.
        self.granule_name_var = tk.StringVar(value="")
        self._suggested_granule_name = ""
        self.status_var = tk.StringVar(value="Enter a name and add the first granule.")
        self.count_var = tk.StringVar(value="0 added")

        self.win = tk.Toplevel(palette.win)
        self.win.withdraw()
        self.win.title("Add subcategory" if self.parent_category is not None else "Add Color Category")
        self.win.configure(bg=palette.BG)
        self.win.resizable(True, True)
        self.win.minsize(760, 470)
        self.win.transient(palette.win)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        # Fit shorter screens too: the content scrolls, not the footer.
        desired_height = min(785, max(470, self.win.winfo_screenheight() - 95))
        try:
            self.app.center_popup_to_parent(
                self.win, 880, desired_height, parent=palette.win)
        except Exception:
            self.win.geometry(f"880x{desired_height}")
        self._build_ui()
        self.name_var.trace_add("write", self._on_name_change)
        self.original_child_var.trace_add("write", lambda *_args: self._update_create_state())
        self.granule_name_var.trace_add(
            "write", lambda *_args: self._update_create_state())
        self.win.bind("<Escape>", lambda _event: self.close())
        self._render_granules()
        self.color_picker.clear()
        self.win.deiconify()
        self.win.grab_set()
        self.name_entry.focus_set()

    def _cancel_local_job(self, name):
        token = getattr(self, name, None)
        if token is not None:
            try:
                self.win.after_cancel(token)
            except tk.TclError:
                pass
            setattr(self, name, None)

    def _schedule_local_job(self, name, callback, delay=None):
        self._cancel_local_job(name)
        def run():
            setattr(self, name, None)
            try:
                if self.win.winfo_exists():
                    callback()
            except tk.TclError:
                pass
        token = self.win.after_idle(run) if delay is None else self.win.after(delay, run)
        setattr(self, name, token)

    def close(self):
        for name in ("_restore_position_id", "_scroll_last_id", "_restore_grab_id"):
            self._cancel_local_job(name)
        if self._scroll_region_after_id is not None:
            try:
                self.win.after_cancel(self._scroll_region_after_id)
            except tk.TclError:
                pass
            self._scroll_region_after_id = None
        if self._pending_refresh is not None:
            try:
                self.win.after_cancel(self._pending_refresh)
            except tk.TclError:
                pass
            self._pending_refresh = None
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    @staticmethod
    def _configure_granule_columns(container):
        """Use the same responsive grid for headers and scrollable rows."""
        widths = (35, 145, 115, 89, 153, 114)
        weights = (0, 3, 2, 1, 3, 1)
        for column, (width, weight) in enumerate(zip(widths, weights)):
            container.grid_columnconfigure(column, minsize=width, weight=weight)

    def _build_ui(self):
        p = self.palette
        root = tk.Frame(self.win, bg=p.BG)
        root.pack(fill="both", expand=True, padx=13, pady=10)

        # Fixed footer; everything above it belongs to ONE vertical scrollable
        # document. This avoids the nested-scroll/clipped-granules problem.
        bottom = tk.Frame(root, bg=p.BG)
        bottom.pack(side="bottom", fill="x", pady=(9, 0))
        tk.Label(bottom, textvariable=self.status_var, font=p.FONT_SMALL,
                 fg=p.MUTED, bg=p.BG, anchor="w", justify="left",
                 wraplength=470).pack(side="left", fill="x", expand=True)
        tk.Button(bottom, text="Cancel", command=self.close,
                  font=p.FONT, relief="solid", bd=1,
                  padx=12, pady=7).pack(side="right", padx=(9, 0))
        self.create_button = tk.Button(
            bottom, text="Create subcategory" if self.parent_category is not None else "Create Category", command=self.create,
            font=p.FONT_BOLD, relief="flat", bd=0, padx=16, pady=8,
            bg=p.BLUE, fg="white", activebackground=UI_ACCENT_DARK,
            activeforeground="white", cursor="hand2", state="disabled"
        )
        self.create_button.pack(side="right")
        self.create_button.configure(bg=p.PANEL, disabledforeground=p.MUTED)

        viewport = tk.Frame(root, bg=p.BG)
        viewport.pack(fill="both", expand=True)
        self.scrollbar = styled_scrollbar(viewport, orient="vertical")
        self.scrollbar.pack(side="right", fill="y")
        self.scroll_canvas = tk.Canvas(
            viewport, bg=p.BG, highlightthickness=0, bd=0,
            yscrollincrement=34,
            yscrollcommand=self.scrollbar.set)
        self.scroll_canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.configure(command=self.scroll_canvas.yview)
        self.scroll_body = tk.Frame(self.scroll_canvas, bg=p.BG)
        self.scroll_item = self.scroll_canvas.create_window(
            (0, 0), window=self.scroll_body, anchor="nw")
        self.scroll_body.bind("<Configure>", self._update_scroll_region)
        self.scroll_canvas.bind("<Configure>", self._resize_scroll_body)
        self.win.bind("<MouseWheel>", self._on_dialog_scroll, add="+")
        self.win.bind("<Button-4>", self._on_dialog_scroll, add="+")
        self.win.bind("<Button-5>", self._on_dialog_scroll, add="+")

        header = tk.Frame(self.scroll_body, bg=p.CARD, highlightbackground=p.BORDER,
                          highlightthickness=1)
        header.pack(fill="x", pady=(0, 8))
        tk.Label(header, text="Add subcategory" if self.parent_category is not None else "Add Color Category", font=("Segoe UI", 14, "bold"),
                 bg=p.CARD, fg=p.TEXT).pack(side="left", padx=(16, 10), pady=11)
        tk.Label(header, text=f"Parent: {self.parent_category}" if self.parent_category is not None else "Define one or more positive granules",
                 font=p.FONT_SMALL, fg=p.MUTED, bg=p.CARD).pack(
                     side="right", padx=(6, 16), pady=11)

        # One compact card for the category name and the color input.
        card = tk.Frame(self.scroll_body, bg=p.CARD, highlightbackground=p.BORDER,
                        highlightthickness=1)
        card.pack(fill="x", pady=(0, 8))
        name_row = tk.Frame(card, bg=p.CARD)
        name_row.pack(fill="x", padx=15, pady=(10, 8))
        tk.Label(name_row, text="New subcategory" if self.parent_category is not None else "Category name", font=p.FONT_BOLD, bg=p.CARD,
                 fg=p.TEXT, width=20 if self.parent_category is not None else 15, anchor="w").pack(side="left")
        category_name_vcmd = (
            self.win.register(lambda proposed: len(proposed) <= MAX_CATEGORY_NAME_CHARS),
            "%P",
        )
        self.name_entry = tk.Entry(
            name_row, textvariable=self.name_var,
            font=("Segoe UI", 10), bd=1, relief="solid",
            validate="key", validatecommand=category_name_vcmd,
        )
        self.name_entry.pack(side="left", fill="x", expand=True)
        if self.original_child_parent is not None:
            row = tk.Frame(card, bg=p.CARD)
            row.pack(fill="x", padx=15, pady=(0, 4))
            tk.Label(row, text="Keep granules in", font=p.FONT_BOLD, bg=p.CARD,
                     fg=p.TEXT, width=20, anchor="w").pack(side="left")
            self.original_child_entry = tk.Entry(row, textvariable=self.original_child_var,
                font=("Segoe UI", 10), bd=1, relief="solid", validate="key",
                validatecommand=category_name_vcmd)
            self.original_child_entry.pack(side="left", fill="x", expand=True)
            tk.Label(card, text=f"Name a subcategory for the current granules of '{self.original_child_parent}'. Their colors stay the same.",
                     font=p.FONT_SMALL, fg=p.MUTED, bg=p.CARD, anchor="w", justify="left",
                     wraplength=600).pack(fill="x", padx=15, pady=(0, 8))

        tk.Frame(card, height=1, bg=p.BORDER).pack(fill="x", padx=15, pady=(0, 7))
        color_heading = tk.Frame(card, bg=p.CARD)
        color_heading.pack(fill="x", padx=15, pady=(0, 6))
        # Center the heading and subtitle as a single, balanced group.
        heading_center = tk.Frame(color_heading, bg=p.CARD)
        heading_center.pack(anchor="center")
        tk.Label(heading_center, text="New Granule", bg=p.CARD, fg=p.TEXT,
                 font=p.FONT_SECTION).pack(side="left")
        tk.Label(heading_center, text="Choose and refine its color", bg=p.CARD,
                 fg=p.MUTED, font=p.FONT_SMALL).pack(side="left", padx=(10, 0))

        # The SAME precise Color Picker powers both this embedded editor and
        # the standalone Add/Edit Granule windows. No second conversion logic.
        picker_host = tk.Frame(card, bg=p.CARD)
        picker_host.pack(fill="x", padx=9, pady=(0, 3))
        self.color_picker = open_square_color_picker(
            self.app, self.win, embedded_parent=picker_host,
            compact=True, external_name_var=self.granule_name_var,
            initial_empty=True, on_change=self._on_picker_change,
            initial_mode=getattr(self.palette, "initial_picker_mode", None),
        )
        self.mode_var = self.color_picker.mode_var
        self.granule_name_entry = self.color_picker.name_entry

        action = tk.Frame(card, bg=p.CARD)
        action.pack(fill="x", padx=15, pady=(0, 8))
        self.add_button = tk.Button(
            action, text="+ Add granule", command=self.add,
            font=p.FONT_SMALL_BOLD, relief="flat", bd=0,
            padx=13, pady=6, bg=p.BLUE, fg="white",
            disabledforeground=p.MUTED,
            activebackground=UI_ACCENT_DARK, activeforeground="white",
            cursor="hand2", state="disabled")
        self.add_button.pack(side="right")

        # Added granules are part of the document, not a second scroll region.
        extras = tk.Frame(self.scroll_body, bg=p.CARD, highlightbackground=p.BORDER,
                          highlightthickness=1)
        extras.pack(fill="x", pady=(0, 6))
        bar = tk.Frame(extras, bg=p.CARD)
        bar.pack(fill="x", padx=12, pady=(8, 6))
        tk.Label(bar, text="Positive granules", bg=p.CARD, fg=p.TEXT,
                 font=p.FONT_SECTION).pack(side="left")
        tk.Label(bar, textvariable=self.count_var, bg=p.CARD, fg=p.MUTED,
                 font=p.FONT_SMALL).pack(side="left", padx=(9, 0))
        tk.Label(bar, text="Added colors", bg=p.CARD,
                 fg=p.MUTED, font=p.FONT_SMALL).pack(side="right")

        headings = tk.Frame(extras, bg=p.PANEL, height=27)
        headings.pack(fill="x", padx=(11, 28))
        headings.pack_propagate(False)
        self._configure_granule_columns(headings)
        for col, text, colspan in (
            (0, "GRANULE", 2), (2, "RGB", 1), (3, "HEX", 1),
            (4, "LAB", 1), (5, "ACTIONS", 1),
        ):
            tk.Label(headings, text=text, font=p.FONT_SMALL_BOLD,
                     bg=p.PANEL, fg=p.MUTED,
                     anchor="w" if col == 0 else "center").grid(
                         row=0, column=col, columnspan=colspan,
                         sticky="nsew", padx=(11, 0) if col == 0 else 0)
        headings.grid_rowconfigure(0, weight=1)

        self.rows = tk.Frame(extras, bg=p.CARD)
        self.rows.pack(fill="x", padx=11, pady=(0, 10))
        self._scroll_region_after_id = self.scroll_canvas.after_idle(self._update_scroll_region)

    def _update_scroll_region(self, _event=None):
        try:
            if self.scroll_canvas.winfo_exists():
                self.scroll_canvas.configure(
                    scrollregion=self.scroll_canvas.bbox("all"))
        except tk.TclError:
            pass

    def _resize_scroll_body(self, event):
        try:
            self.scroll_canvas.itemconfigure(
                self.scroll_item, width=max(1, event.width))
            self._update_scroll_region()
        except tk.TclError:
            pass

    def _on_dialog_scroll(self, event):
        """Scroll the entire editor (Windows, macOS and X11)."""
        if getattr(event, "num", None) == 4:
            steps = -1
        elif getattr(event, "num", None) == 5:
            steps = 1
        else:
            delta = getattr(event, "delta", 0)
            if not delta:
                return "break"
            # Windows uses multiples of 120; macOS often smaller deltas.
            steps = (-max(1, int(round(delta / 120))) if delta > 0
                     else max(1, int(round(-delta / 120))))
        try:
            self.scroll_canvas.yview_scroll(steps, "units")
        except tk.TclError:
            pass
        return "break"

    def _bind_granule_scroll(self, _widget):
        # The Toplevel's bindtag already receives wheel events from all
        # descendants. Adding per-row bindings caused double scrolling.
        return None

    def _on_picker_change(self, lab, rgb, _hex):
        """Receive the precise current value from our embedded picker."""
        self._cached_lab = (tuple(float(v) for v in lab)
                            if lab is not None else None)
        self._cached_rgb = (tuple(safe_rgb_tuple(rgb))
                            if rgb is not None else None)
        if hasattr(self, "add_button"):
            self._update_create_state()

    def _read_primary(self):
        """Commit pending numeric input before creating a granule."""
        color = self.color_picker.get_color()
        if color is None:
            return (False, "Choose a valid color before adding a granule.",
                    None, None, None)
        lab, rgb, hx = color
        return True, "", lab, rgb, hx

    def _original_child_error(self):
        if self.original_child_parent is None:
            return ""
        name, error = check_label_name(self.original_child_var.get(), max_length=MAX_CATEGORY_NAME_CHARS, kind="Subcategory")
        if error:
            return error
        if name == self._current_name() or name in self.palette.colors:
            return "Use two different, unused category names."
        return ""

    def _update_create_state(self, hint=""):
        name, name_error = check_label_name(self.name_var.get(), max_length=MAX_CATEGORY_NAME_CHARS, kind="Category")
        valid_name = not name_error
        unique_name = valid_name and name not in self.palette.colors

        # The buttons have independent semantics: Add needs valid input,
        # Create needs at least one previously added granule.
        granule_name = self.granule_name_var.get().strip()
        valid_granule_name = (
            not check_label_name(self.granule_name_var.get(), kind="Granule")[1] and
            granule_name not in self.palette._used_granule_labels() and
            all(g["label"] != granule_name for g in self.granules)
        )
        duplicate_color = self._duplicate_color_label(self._cached_lab)
        can_add = (
            unique_name and valid_granule_name and
            self._cached_lab is not None and duplicate_color is None
        )
        original_error = self._original_child_error()
        can_create = unique_name and bool(self.granules) and not original_error
        self.add_button.configure(
            state="normal" if can_add else "disabled",
            bg=self.palette.BLUE if can_add else self.palette.PANEL,
        )
        self.create_button.configure(
            state="normal" if can_create else "disabled",
            bg=self.palette.BLUE if can_create else self.palette.PANEL,
        )
        if not valid_name:
            self.status_var.set(name_error)
        elif not unique_name:
            self.status_var.set("This category name is already used.")
        elif original_error:
            self.status_var.set(original_error)
        elif self._cached_lab is not None and duplicate_color is not None:
            self.status_var.set(
                f"Color matches '{duplicate_color}'. Change at least one "
                "coordinate before adding another granule.")
        elif not valid_granule_name:
            self.status_var.set(check_label_name(self.granule_name_var.get(), kind="Granule")[1] or "Enter a unique granule name.")
        elif can_create:
            count = len(self.granules)
            self.status_var.set(
                f"{count} granule{'s' if count != 1 else ''} added. "
                "Add another color or create the category.")
        elif self._cached_lab is None:
            self.status_var.set(hint or "Enter a color and press Add granule.")
        else:
            self.status_var.set("Press Add granule to include this color.")

    def _restore_grab(self):
        try:
            if self.win.winfo_exists():
                self._schedule_local_job("_restore_grab_id", self.win.grab_set)
        except tk.TclError:
            pass

    def _current_name(self):
        return self.name_var.get().strip()

    @staticmethod
    def _automatic_label(category, number):
        suffix = f"-g{number}"
        return f"{category[:MAX_COLOR_NAME_CHARS - len(suffix)]}{suffix}"

    def _next_label(self):
        """Suggest a unique name while keeping monotonic gN numbering.

        A manually named granule still occupies its position (number). That
        position is not recycled by a subsequent custom name.
        """
        name = self._current_name() or "Color"
        used = self.palette._used_granule_labels()
        used.update(item["label"] for item in self.granules)
        if not self.granules:
            return name, 1
        number = max(2, max(g.get("number", 0) for g in self.granules) + 1)
        while self._automatic_label(name, number) in used:
            number += 1
        return self._automatic_label(name, number), number

    def _sync_suggested_granule_name(self, force=False):
        """Refresh a default label without overwriting custom input."""
        current = self.granule_name_var.get().strip()
        proposed, _serial = self._next_label()
        if force or not current or current == self._suggested_granule_name:
            self.granule_name_var.set(proposed)
        self._suggested_granule_name = proposed

    def _on_name_change(self, *_args):
        name = self._current_name()
        for item in self.granules:
            if item.get("automatic_label") and name:
                item["label"] = (name if item["number"] == 1 else
                                 self._automatic_label(name, item["number"]))
        self._sync_suggested_granule_name()
        if self._pending_refresh is not None:
            try:
                self.win.after_cancel(self._pending_refresh)
            except tk.TclError:
                pass
        self._pending_refresh = self.win.after(130, self._render_granules)
        self._update_create_state()

    def _duplicate_color_label(self, lab):
        if lab is None:
            return None
        target = np.asarray(lab, dtype=float)
        for item in self.granules:
            if np.linalg.norm(target - np.asarray(item["lab"], dtype=float)) <= Voronoi.DEFAULT_MERGE_EPS:
                return item["label"]
        for data in self.palette.colors.values():
            for item in data.get("granules", []):
                if np.linalg.norm(target - np.asarray(item["lab"], dtype=float)) <= Voronoi.DEFAULT_MERGE_EPS:
                    return item["label"]
        return None

    def _check_site(self, label, lab, exclude_index=None):
        """Safely validate pending and already-loaded granules."""
        existing = [
            (category, item["label"], item["lab"])
            for category, data in self.palette.colors.items()
            for item in data.get("granules", [])
        ]
        existing.extend(
            ("", item["label"], item["lab"])
            for i, item in enumerate(self.granules) if i != exclude_index
        )
        return check_granule_site(label, lab, existing)

    def _validate_site(self, label, lab, exclude_index=None):
        """Compatibility validator; the UI calls _check_site instead."""
        label, point, error = self._check_site(label, lab, exclude_index)
        if error:
            raise ValueError(error)
        return label, point

    def _clear_color_fields(self):
        """Reset the current picker, not the category name or granule list."""
        self.color_picker.clear()

    def add(self):
        """Append the current RGB/LAB/HEX color to the pending granule list."""
        name, error = check_label_name(self.name_var.get(), max_length=MAX_CATEGORY_NAME_CHARS, kind="Category")
        if error:
            self.status_var.set(error)
            return
        if name in self.palette.colors:
            self.status_var.set(f"Category '{name}' already exists.")
            return
        ok, message, lab, _rgb, _hex = self._read_primary()
        if not ok:
            self.status_var.set(message or "Enter a valid color.")
            return
        try:
            suggested, number = self._next_label()
            requested = self.granule_name_var.get()
            label, point, error = self._check_site(requested, lab)
        except (TypeError, ValueError) as exc:
            # The color parser is already checked, but keep this callback safe.
            self.status_var.set(str(exc))
            return
        if error:
            self.status_var.set(error)
            return
        self.granules.append({
            "label": label, "lab": point, "number": number,
            "native_rgb": matching_native_rgb(point, _rgb),
            "automatic_label": (label == suggested),
        })
        self._render_granules()
        # Wait for geometry propagation before bringing the newest row into view.
        self._schedule_local_job("_scroll_last_id", self._scroll_to_last_granule, delay=30)
        self._sync_suggested_granule_name(force=True)
        self._clear_color_fields()

    def _open_extra_dialog(self, index):
        """Edit a pending granule in the shared precise Color Picker."""
        if not 0 <= index < len(self.granules):
            return
        item = self.granules[index]
        original_label, number, original_lab = (
            item["label"], item["number"], item["lab"])

        def submit(name, lab, _rgb, _hex, _dialog, status_var):
            try:
                clean_name, point, error = self._check_site(
                    name, lab, exclude_index=index)
            except (ValueError, TypeError) as exc:
                status_var.set(str(exc))
                return False
            if error:
                status_var.set(error)
                return False
            self.granules[index] = dict(
                label=clean_name, lab=point, number=number,
                native_rgb=(item.get("native_rgb") if all(abs(a-b) <= 1e-10
                             for a, b in zip(point, item["lab"]))
                             else matching_native_rgb(point, _rgb)),
                automatic_label=(
                    clean_name == original_label and
                    item.get("automatic_label", False)
                ),
            )
            self._render_granules()
            self._update_create_state()
            return True

        dialog = self.app._open_square_color_picker(
            parent=self.win, title="Edit granule",
            granule_name=original_label,
            initial_lab=original_lab, initial_mode=self.mode_var.get(),
            submit_text="Save changes",
            on_granule_submit=submit,
        )
        if dialog is not None:
            dialog.bind(
                "<Destroy>",
                lambda e, target=dialog: self._restore_grab()
                if e.widget is target else None, add="+")

    def use_as_base(self, index):
        """Load the unrounded LAB site into every shared picker control."""
        if not 0 <= index < len(self.granules):
            return
        source = self.granules[index]
        if not self.color_picker.set_lab(source["lab"], mode="LAB"):
            self.status_var.set("Unable to load this granule as a color reference.")
            return
        self._sync_suggested_granule_name(force=True)
        self.status_var.set(
            f"Loaded '{source['label']}' as a starting point. "
            "Adjust its color before adding another granule."
        )

    def edit(self, index):
        self._open_extra_dialog(index)

    def remove(self, index):
        if 0 <= index < len(self.granules):
            self.granules.pop(index)
            self._sync_suggested_granule_name()
            self._render_granules()
            self._update_create_state()

    def _scroll_to_last_granule(self):
        self._update_scroll_region()
        try:
            if self.scroll_canvas.winfo_exists():
                self.scroll_canvas.yview_moveto(1.0)
        except tk.TclError:
            pass

    def _render_granules(self):
        """Redraw only the lower list after add/edit/remove or a rename."""
        if self._pending_refresh is not None:
            try:
                self.win.after_cancel(self._pending_refresh)
            except tk.TclError:
                pass
            self._pending_refresh = None
        try:
            if not self.win.winfo_exists():
                return
        except tk.TclError:
            return

        previous_position = self.scroll_canvas.yview()[0]
        for child in self.rows.winfo_children():
            child.destroy()
        self.count_var.set(f"{len(self.granules)} added")
        p = self.palette
        if not self.granules:
            empty = tk.Label(
                self.rows,
                text="No granules yet. Enter a color above and press + Add granule.",
                font=p.FONT_SMALL, bg=p.CARD, fg=p.MUTED, anchor="center",
                pady=18,
            )
            empty.pack(fill="x")
            self._update_scroll_region()
            return

        for i, item in enumerate(self.granules):
            bg = p.PANEL if i % 2 == 0 else p.CARD
            row = tk.Frame(self.rows, bg=bg, height=39)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)
            self._configure_granule_columns(row)
            row.grid_rowconfigure(0, weight=1)

            rgb = tuple(safe_rgb_tuple(lab_to_rgb(item["lab"])))
            hx = rgb_to_hex(rgb).upper()
            swatch = tk.Canvas(row, width=23, height=23, bg=bg,
                               highlightthickness=0)
            swatch.grid(row=0, column=0, padx=(8, 2), sticky="w")
            swatch.create_rectangle(1, 1, 22, 22, fill=hx, outline=p.BORDER)
            tk.Label(row, text=item["label"], font=p.FONT_BOLD, bg=bg,
                     fg=p.TEXT, anchor="w").grid(
                         row=0, column=1, sticky="nsew", padx=(1, 5))
            for col, text in (
                (2, ", ".join(str(v) for v in rgb)),
                (3, hx),
                (4, ", ".join(f"{x:.2f}" for x in item["lab"])),
            ):
                tk.Label(row, text=text, font=p.FONT_SMALL,
                         fg=p.MUTED, bg=bg, anchor="center").grid(
                             row=0, column=col, sticky="nsew", padx=2)
            actions = tk.Frame(row, bg=bg)
            actions.grid(row=0, column=5, sticky="nsew")
            # Keep the three action controls grouped and centered in the cell.
            actions_group = tk.Frame(actions, bg=bg)
            actions_group.pack(expand=True, anchor="center")
            copy_button = tk.Button(
                actions_group, text="↑", command=lambda ix=i: self.use_as_base(ix),
                font=p.FONT_BOLD, fg=p.BLUE, bg=bg,
                relief="flat", bd=0, cursor="hand2", padx=2)
            copy_button.pack(side="left", padx=(0, 3))
            copy_button.bind(
                "<Enter>", lambda _e: self.status_var.set(
                    "↑ Use this granule's LAB color as a base for a new one."))
            copy_button.bind(
                "<Leave>", lambda _e: self._update_create_state())
            tk.Button(actions_group, text="Edit", command=lambda ix=i: self.edit(ix),
                      font=p.FONT_SMALL_BOLD, fg=p.BLUE, bg=bg,
                      relief="flat", bd=0, cursor="hand2").pack(
                          side="left", padx=(2, 5))
            tk.Button(actions_group, text="×", command=lambda ix=i: self.remove(ix),
                      font=p.FONT_BOLD, fg=p.MUTED, bg=bg,
                      relief="flat", bd=0, cursor="hand2").pack(side="left")
            self._bind_granule_scroll(row)

        def restore_position():
            self._update_scroll_region()
            try:
                if self.scroll_canvas.winfo_exists():
                    self.scroll_canvas.yview_moveto(previous_position)
            except tk.TclError:
                pass
        self._schedule_local_job("_restore_position_id", restore_position)

    def create(self):
        """Commit exactly the granules the user explicitly added."""
        name, error = check_label_name(self.name_var.get(), max_length=MAX_CATEGORY_NAME_CHARS, kind="Category")
        if error:
            self.status_var.set(error)
            return
        if name in self.palette.colors:
            self.status_var.set(f"Category '{name}' already exists.")
            return
        original_error = self._original_child_error()
        if original_error:
            self.status_var.set(original_error)
            if self.original_child_entry is not None:
                self.original_child_entry.focus_set()
            return
        if not self.granules:
            self.status_var.set("Add at least one granule before creating the category.")
            return
        # Preserve all visible labels. The first default is the category
        # name, even when the category has several granules.
        packed = []
        for item in self.granules:
            label = item["label"]
            packed.append({
                "label": label,
                "lab": tuple(float(v) for v in item["lab"]),
                "native_rgb": item.get("native_rgb"),
                "enabled": True,
            })
        for i, item in enumerate(packed):
            label, point, error = self._check_site(
                item["label"], item["lab"], exclude_index=i
            )
            if error:
                self.status_var.set(error)
                return
            item["lab"] = point

        # The editor validates and commits its draft before closing the picker.
        # Other palette creation workflows keep their original behavior.
        commit = getattr(self.palette, "commit_category", None)
        if callable(commit):
            if commit(name, packed, self.original_child_var.get().strip() or None):
                self.close()
            return
        first = packed[0]["lab"]
        rgb = tuple(safe_rgb_tuple(lab_to_rgb(first)))
        self.palette.colors[name] = dict(
            rgb=rgb, lab=first, hex=rgb_to_hex(rgb).upper(),
            granules=packed, custom=True,
        )
        self.palette.color_checks[name] = dict(
            var=tk.BooleanVar(value=True), lab=first, rgb=rgb,
            native_rgb=packed[0].get("native_rgb"),
        )
        if len(packed) > 1:
            self.palette._expanded_categories.add(name)
        self.close()
        if (self.palette.search_var.get().strip()
                and not self.palette._matches_search(name)):
            self.palette.search_var.set("")
            self.palette.win.after(60, self.palette._scroll_to_bottom)
        else:
            self.palette._append_color_rows([name])
            if hasattr(self.palette, '_schedule_idle'):
                self.palette._schedule_idle(self.palette._scroll_to_bottom)
            else:
                self.palette.win.after_idle(self.palette._scroll_to_bottom)

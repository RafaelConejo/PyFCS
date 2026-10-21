import os
import sys
import numpy as np
from skimage import color
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import colorsys
from scipy.spatial import cKDTree

### my libraries ###
from Source.input_output.Input import Input
from Source.geometry.Prototype import Prototype
from Source.geometry.Voronoi import Voronoi
from Source.colorspace.ReferenceDomain import ReferenceDomain

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
    """Return True when LAB lies inside the shared PyFCS reference domain."""
    try:
        L, a, b = safe_lab_tuple(lab)
        return ReferenceDomain.is_valid_lab_values(L, a, b)
    except Exception:
        return False


def find_duplicate_lab_name(color_data, lab, atol=Voronoi.DEFAULT_MERGE_EPS):
    """Return the label of an existing LAB prototype within the Voronoi merge tolerance."""
    target = np.asarray(lab, dtype=np.float64).reshape(-1)
    if target.size != 3 or not np.all(np.isfinite(target)):
        return None

    tolerance = max(0.0, float(atol))

    for name, data in (color_data or {}).items():
        values = data.get("positive_prototype", data.get("Color"))
        if values is None:
            continue

        current = np.asarray(values, dtype=np.float64).reshape(-1)
        if current.size != 3 or not np.all(np.isfinite(current)):
            continue

        if np.linalg.norm(current - target) <= tolerance:
            return name

    return None


def find_duplicate_lab_pairs(named_labs, atol=Voronoi.DEFAULT_MERGE_EPS):
    """
    Return LAB prototype pairs that collide within the shared Voronoi tolerance.

    Parameters
    ----------
    named_labs : mapping or iterable
        Either ``{name: lab}`` or an iterable of ``(name, lab)`` pairs.
    atol : float
        Euclidean LAB tolerance. Defaults to ``Voronoi.DEFAULT_MERGE_EPS`` so
        creation validation uses the same numerical rule as the geometry layer.

    Notes
    -----
    A KD-tree keeps the check close to O(n log n), avoiding the quadratic
    all-pairs loop when automatic detection produces hundreds or thousands of
    candidate colors. Invalid/non-finite LAB entries are ignored here and should
    be reported separately by the caller's normal domain validation.
    """
    if named_labs is None:
        return []

    items = list(named_labs.items()) if hasattr(named_labs, "items") else list(named_labs)
    names = []
    labs = []

    for name, lab in items:
        try:
            arr = np.asarray(lab, dtype=np.float64).reshape(-1)
        except Exception:
            continue

        if arr.size != 3 or not np.all(np.isfinite(arr)):
            continue

        names.append(str(name))
        labs.append(arr[:3])

    if len(labs) < 2:
        return []

    matrix = np.asarray(labs, dtype=np.float64)
    tolerance = max(0.0, float(atol))

    if tolerance == 0.0:
        buckets = {}
        pair_indices = []
        for idx, row in enumerate(matrix):
            key = tuple(float(v) for v in row)
            for previous in buckets.get(key, []):
                pair_indices.append((previous, idx))
            buckets.setdefault(key, []).append(idx)
    else:
        tree = cKDTree(matrix)
        pair_indices = sorted(tree.query_pairs(r=tolerance))

    return [
        (names[i], names[j], matrix[i].copy())
        for i, j in pair_indices
    ]


def make_unique_color_name(requested_name, existing_names=(), ignore_name=None, max_chars=MAX_COLOR_NAME_CHARS):
    """Return a normalized unique color name using the shared ``Name (2)`` style."""
    try:
        max_chars = max(1, int(max_chars))
    except Exception:
        max_chars = MAX_COLOR_NAME_CHARS

    existing = {str(name) for name in (existing_names or ())}
    if ignore_name is not None:
        existing.discard(str(ignore_name))

    base = safe_text(requested_name) or "Color"
    base = base[:max_chars].rstrip() or "Color"[:max_chars]

    if base not in existing:
        return base

    index = 2
    while True:
        suffix = f" ({index})"
        room = max(1, max_chars - len(suffix))
        prefix = base[:room].rstrip() or "C"
        candidate = f"{prefix}{suffix}"
        if candidate not in existing:
            return candidate
        index += 1



# ============================================================================================================================================================
#  SHARED LAB FILTER HELPERS
# ============================================================================================================================================================

LAB_FILTER_DEFAULTS = {
    "L_min": "0.0",
    "L_max": "100.0",
    "a_min": "-128.0",
    "a_max": "128.0",
    "b_min": "-128.0",
    "b_max": "128.0",
}

LAB_FILTER_LABELS = {
    "L_min": "L* minimum",
    "L_max": "L* maximum",
    "a_min": "a* minimum",
    "a_max": "a* maximum",
    "b_min": "b* minimum",
    "b_max": "b* maximum",
}


def read_lab_filter_bindings(filter_bindings, strict=True):
    """
    Read enabled LAB filters from Tk variable bindings.

    Parameters
    ----------
    filter_bindings : dict
        Mapping such as ``{"L_min": (enabled_var, value_var), ...}``.
    strict : bool
        When True, invalid enabled values raise ValueError. When False,
        malformed enabled values are ignored; this is useful for passive UI
        summaries while the user is editing another control.
    """
    values = {}

    for key in LAB_FILTER_DEFAULTS:
        pair = (filter_bindings or {}).get(key)
        if not pair or len(pair) != 2:
            continue

        enabled_var, value_var = pair
        try:
            enabled = bool(enabled_var.get())
        except Exception:
            enabled = False

        if not enabled:
            continue

        try:
            raw = value_var.get()
        except Exception:
            raw = ""

        parsed = safe_float(raw)
        if parsed is None:
            if strict:
                raise ValueError(
                    f"Enter a valid numeric value for {LAB_FILTER_LABELS.get(key, key)}."
                )
            continue

        values[key] = float(parsed)

    for component, low_key, high_key in (
        ("L*", "L_min", "L_max"),
        ("a*", "a_min", "a_max"),
        ("b*", "b_min", "b_max"),
    ):
        low = values.get(low_key)
        high = values.get(high_key)
        if low is not None and high is not None and low > high:
            if strict:
                raise ValueError(f"{component} minimum cannot be greater than its maximum.")
            # Passive reads should not return a contradictory pair.
            values.pop(low_key, None)
            values.pop(high_key, None)

    return values


def format_lab_filters(filters, prefix=True):
    """Return a compact human-readable summary of active LAB limits."""
    filters = filters or {}
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
        return "No filters applied" if prefix else ""

    body = " · ".join(parts)
    return f"Filters: {body}" if prefix else body


def lab_passes_filters(lab, filters):
    """Return True when one LAB triplet satisfies every enabled limit."""
    if not filters:
        return True

    try:
        L, a, b = safe_lab_tuple(lab)
    except Exception:
        return False

    if "L_min" in filters and L < filters["L_min"]:
        return False
    if "L_max" in filters and L > filters["L_max"]:
        return False
    if "a_min" in filters and a < filters["a_min"]:
        return False
    if "a_max" in filters and a > filters["a_max"]:
        return False
    if "b_min" in filters and b < filters["b_min"]:
        return False
    if "b_max" in filters and b > filters["b_max"]:
        return False
    return True


def mean_rgb_with_lab_filters(rgb_pixels, filters=None, chunk_size=250000):
    """
    Compute an RGB mean after applying optional LAB limits pixel-by-pixel.

    The RGB input is expected in [0, 255]. Conversion to CIELAB is vectorized
    in chunks so large ROIs do not require a large temporary LAB image.

    Returns
    -------
    (mean_rgb, used_count)
        ``mean_rgb`` is a float RGB vector or None when no pixels survive.
    """
    pixels = np.asarray(rgb_pixels, dtype=np.float32).reshape(-1, 3)
    total = int(pixels.shape[0])

    if total == 0:
        return None, 0

    filters = dict(filters or {})
    if not filters:
        return np.mean(pixels, axis=0), total

    rgb_sum = np.zeros(3, dtype=np.float64)
    used_count = 0
    chunk_size = max(1, int(chunk_size))

    for start in range(0, total, chunk_size):
        chunk = pixels[start:start + chunk_size]
        lab_chunk = color.rgb2lab(
            (chunk / 255.0).reshape(-1, 1, 3)
        ).reshape(-1, 3)

        mask = np.ones(lab_chunk.shape[0], dtype=bool)
        L = lab_chunk[:, 0]
        a = lab_chunk[:, 1]
        b = lab_chunk[:, 2]

        if "L_min" in filters:
            mask &= L >= filters["L_min"]
        if "L_max" in filters:
            mask &= L <= filters["L_max"]
        if "a_min" in filters:
            mask &= a >= filters["a_min"]
        if "a_max" in filters:
            mask &= a <= filters["a_max"]
        if "b_min" in filters:
            mask &= b >= filters["b_min"]
        if "b_max" in filters:
            mask &= b <= filters["b_max"]

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
    description="Enabled limits apply to manual area averages.",
    title="LAB Filters",
    theme=None,
):
    """
    Open the shared compact LAB Filters dialog used by PyFCS image tools.

    The dialog edits temporary variables. Active bindings are changed only
    after a successful Apply, so Cancel/X always leave the current filters
    untouched.
    """
    theme = dict(theme or {})
    bg = theme.get("bg", "#f5f6f8")
    card = theme.get("card", "#ffffff")
    text_color = theme.get("text", "#1f2937")
    muted = theme.get("muted", "#6b7280")
    blue = theme.get("blue", "#1f4e8c")
    blue_soft = theme.get("blue_soft", "#e8f0fe")
    font = theme.get("font", ("Segoe UI", 9))
    font_bold = theme.get("font_bold", ("Segoe UI", 9, "bold"))
    font_small = theme.get("font_small", ("Segoe UI", 8))
    font_small_bold = theme.get("font_small_bold", ("Segoe UI", 8, "bold"))
    font_section = theme.get("font_section", ("Segoe UI", 10, "bold"))

    win = tk.Toplevel(parent)
    win.title(title)
    win.configure(bg=bg)
    win.resizable(False, False)
    try:
        win.transient(parent)
    except Exception:
        pass

    temp_bindings = {}
    for key, default_value in LAB_FILTER_DEFAULTS.items():
        pair = (filter_bindings or {}).get(key)
        if pair and len(pair) == 2:
            enabled_var, value_var = pair
            try:
                enabled = bool(enabled_var.get())
            except Exception:
                enabled = False
            try:
                value = str(value_var.get())
            except Exception:
                value = default_value
        else:
            enabled = False
            value = default_value

        temp_bindings[key] = (
            tk.BooleanVar(win, value=enabled),
            tk.StringVar(win, value=value),
        )

    outer = tk.Frame(win, bg=bg)
    outer.pack(fill="both", expand=True, padx=12, pady=12)

    panel = tk.LabelFrame(
        outer,
        text=f" {title} ",
        font=font_section,
        bg=card,
        fg=text_color,
        bd=1,
        relief="solid",
        padx=10,
        pady=8,
        labelanchor="nw",
    )
    panel.pack(fill="both", expand=True)

    tk.Label(
        panel,
        text=description,
        font=font_small,
        bg=card,
        fg=muted,
        anchor="w",
        justify="left",
    ).grid(row=0, column=0, columnspan=5, sticky="ew", pady=(0, 7))

    tk.Label(panel, text="Component", font=font_small_bold, bg=card, fg=text_color).grid(
        row=1, column=0, sticky="w", padx=(0, 12)
    )
    tk.Label(panel, text="Minimum", font=font_small_bold, bg=card, fg=text_color).grid(
        row=1, column=1, columnspan=2, sticky="w"
    )
    tk.Label(panel, text="Maximum", font=font_small_bold, bg=card, fg=text_color).grid(
        row=1, column=3, columnspan=2, sticky="w", padx=(12, 0)
    )

    rows = (
        ("L*", "L_min", "L_max"),
        ("a*", "a_min", "a_max"),
        ("b*", "b_min", "b_max"),
    )

    for row_index, (label, min_key, max_key) in enumerate(rows, start=2):
        min_enabled, min_value = temp_bindings[min_key]
        max_enabled, max_value = temp_bindings[max_key]

        tk.Label(
            panel, text=label, font=font_bold, bg=card, fg=text_color,
            width=5, anchor="w"
        ).grid(row=row_index, column=0, sticky="w", pady=3)

        tk.Checkbutton(
            panel, variable=min_enabled, bg=card, activebackground=card,
            selectcolor=card
        ).grid(row=row_index, column=1, sticky="w")
        tk.Entry(panel, textvariable=min_value, width=9, font=font).grid(
            row=row_index, column=2, sticky="w"
        )

        tk.Checkbutton(
            panel, variable=max_enabled, bg=card, activebackground=card,
            selectcolor=card
        ).grid(row=row_index, column=3, sticky="w", padx=(12, 0))
        tk.Entry(panel, textvariable=max_value, width=9, font=font).grid(
            row=row_index, column=4, sticky="w"
        )

    buttons = tk.Frame(panel, bg=card)
    buttons.grid(row=5, column=0, columnspan=5, sticky="ew", pady=(10, 0))

    def _warn(message):
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
        messagebox.showwarning("Invalid Filter", message, parent=win)

    closed = {"done": False}

    def _finish_close():
        if closed["done"]:
            return
        closed["done"] = True
        try:
            if callable(on_close):
                on_close()
        finally:
            try:
                if win.winfo_exists():
                    win.destroy()
            except Exception:
                pass

    def reset_filters():
        for key, default_value in LAB_FILTER_DEFAULTS.items():
            enabled_var, value_var = temp_bindings[key]
            enabled_var.set(False)
            value_var.set(default_value)

    def apply_filters():
        try:
            filters = read_lab_filter_bindings(temp_bindings, strict=True)
        except ValueError as exc:
            _warn(str(exc))
            return

        for key, (target_enabled, target_value) in (filter_bindings or {}).items():
            if key not in temp_bindings:
                continue
            source_enabled, source_value = temp_bindings[key]
            try:
                target_enabled.set(bool(source_enabled.get()))
                target_value.set(str(source_value.get()).strip().replace(",", "."))
            except Exception:
                pass

        # Close the modal dialog before running the caller callback. The
        # callback may need to show its own warning (for example when a ROI has
        # no pixels after filtering), and nested grabs are much safer this way.
        _finish_close()
        if callable(on_apply):
            on_apply(dict(filters))

    tk.Button(
        buttons, text="Reset", command=reset_filters, font=font,
        relief="solid", bd=1, padx=12, pady=4
    ).pack(side="left")

    tk.Button(
        buttons, text="Cancel", command=_finish_close, font=font,
        relief="solid", bd=1, padx=12, pady=4
    ).pack(side="right", padx=(8, 0))

    tk.Button(
        buttons, text="Apply", command=apply_filters, font=font_bold,
        bg=blue_soft, fg=blue, activebackground="#d7e5fb",
        activeforeground=blue, relief="solid", bd=1, padx=14, pady=4
    ).pack(side="right")

    win.protocol("WM_DELETE_WINDOW", _finish_close)
    win.bind("<Escape>", lambda _e: _finish_close())
    win.update_idletasks()

    dialog_w = max(390, win.winfo_reqwidth() + 8)
    dialog_h = max(220, win.winfo_reqheight() + 8)

    try:
        parent.update_idletasks()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = max(1, parent.winfo_width())
        ph = max(1, parent.winfo_height())
        x = px + max(0, (pw - dialog_w) // 2)
        y = py + max(0, (ph - dialog_h) // 2)
        win.geometry(f"{dialog_w}x{dialog_h}+{x}+{y}")
    except Exception:
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        win.geometry(
            f"{dialog_w}x{dialog_h}+{max(0, (sw - dialog_w) // 2)}+{max(0, (sh - dialog_h) // 2)}"
        )

    try:
        win.grab_set()
    except Exception:
        pass
    win.focus_set()
    return win


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
    Convert one 8-bit sRGB color to CIELAB using the same scikit-image
    conversion used by PyFCS image processing.

    Keeping scalar and vectorized image conversion on the same implementation
    avoids small module-dependent numerical differences.
    """
    r, g, b = safe_rgb_tuple((r, g, b))
    rgb01 = np.asarray([[[r, g, b]]], dtype=np.float64) / 255.0
    lab = color.rgb2lab(rgb01)[0, 0]
    return tuple(float(v) for v in lab)


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
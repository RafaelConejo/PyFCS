from tkinter import ttk
import tkinter as tk
import os

### my libraries ###
from Source.input_output.Input import Input
import Source.interface.modules.UtilsTools as UtilsTools

"""
FuzzyColorSpaceManager module

This module provides helper utilities for PyFCS to:
- Load fuzzy color-related files (.cns and .fcs) using the appropriate Input handler.
- Build consistent Tkinter/ttk UI rows to display colors, their LAB values, and a selectable checkbox.

In practice, it acts as a bridge between:
(1) file parsing (delegated to Input.instance(extension))
and
(2) the GUI representation of colors in scrollable lists or selection panels.
"""

class FuzzyColorSpaceManager:
    # Supported file extensions for fuzzy color spaces / color datasets
    SUPPORTED_EXTENSIONS = {'.cns', '.fcs'}

    def __init__(self, root):
        # Reference to the main Tk root (or parent window/controller)
        self.root = root

    @staticmethod
    def load_color_file(filename):
        """
        Load and parse a fuzzy color space or color data file (.cns or .fcs).

        Parameters
        ----------
        filename : str
            Path to the file to be loaded.

        Returns
        -------
        dict
            A dictionary describing the loaded content, containing:
            - type: 'cns' or 'fcs'
            - color_data: parsed colors/metadata
            - fuzzy_color_space: (only for .fcs) the fuzzy color space object/structure

        Raises
        ------
        ValueError
            If the file extension is not supported.
        """
        # Extract and normalize the file extension (e.g., ".CNS" -> ".cns")
        extension = os.path.splitext(filename)[1].lower()

        # Validate extension
        if extension not in FuzzyColorSpaceManager.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file format: {extension}")

        # Get the proper input handler for this extension (factory/singleton pattern)
        input_class = Input.instance(extension)

        # CNS files return only color_data
        if extension == '.cns':
            color_data = input_class.read_file(filename)
            return {'type': 'cns', 'color_data': color_data}

        # FCS files return color_data + fuzzy_color_space
        elif extension == '.fcs':
            color_data, fuzzy_color_space = input_class.read_file(filename)
            return {
                'type': 'fcs',
                'color_data': color_data,
                'fuzzy_color_space': fuzzy_color_space
            }

    def create_color_display_frame(self, parent, color_name, rgb, lab, color_checks):
        """
        Create a UI row to display an existing color with:
        - a color swatch (RGB)
        - the color name (left)
        - LAB values (right)
        - a checkbox (far right) to select/deselect the color

        This layout matches the style used by create_color_display_frame_add().

        Parameters
        ----------
        parent : ttk.Widget
            Container where the row will be added (e.g., a Frame inside a scrollable area).
        color_name : str
            Display name of the color.
        rgb : tuple/list
            RGB values used to render the swatch (expected by UtilsTools.rgb_to_hex()).
        lab : tuple/list
            LAB values (L, A, B) used for display and stored for later actions.
        color_checks : dict
            Dictionary used to store selection state and associated LAB data.
            It will be updated as: color_checks[color_name] = {"var": BooleanVar, "lab": lab}
        """
        # Outer row container
        frame = ttk.Frame(parent)
        frame.pack(fill="x", expand=True, pady=8, padx=20)

        # --- Color swatch (fixed size) ---
        color_box = tk.Label(
            frame,
            bg=UtilsTools.rgb_to_hex(rgb),
            width=5,
            height=2,
            relief="solid",
            bd=1
        )
        color_box.pack(side="left", padx=(10, 10))

        # --- Checkbox (fixed to the far right) ---
        var = tk.BooleanVar()
        color_checks[color_name] = {"var": var, "lab": lab}
        ttk.Checkbutton(frame, variable=var).pack(side="right", padx=(10, 10))

        # --- Middle content (expands) ---
        text_frame = ttk.Frame(frame)
        text_frame.pack(side="left", fill="x", expand=True, padx=20)

        # Color name (left side)
        name_lbl = ttk.Label(text_frame, text=color_name, font=("Helvetica", 11))
        name_lbl.pack(side="left", padx=(0, 20))

        # LAB values (right side)
        lab_values = f"L: {lab[0]:.1f}, A: {lab[1]:.1f}, B: {lab[2]:.1f}"
        lab_lbl = ttk.Label(text_frame, text=lab_values, font=("Helvetica", 10, "italic"))
        lab_lbl.pack(side="right", padx=(20, 0))

    def create_color_display_frame_add(self, parent, color_name, lab, color_checks):
        """
        Create a UI row to display a color being added/previewed where:
        - LAB is always visible (right)
        - name has a fixed maximum width and can be truncated with an ellipsis
          to avoid pushing LAB off-screen
        - checkbox is fixed on the far right
        - swatch is derived from LAB via UtilsTools.lab_to_rgb()

        Parameters
        ----------
        parent : ttk.Widget
            Container where the row will be added.
        color_name : str
            Proposed/display name of the color.
        lab : dict
            LAB dictionary with keys 'L', 'A', 'B' (used for display and stored).
        color_checks : dict
            Dictionary used to store selection state and associated LAB data.
        """
        # Outer row container
        frame = ttk.Frame(parent)
        frame.pack(fill="x", expand=True, pady=8, padx=20)

        # Convert LAB to RGB for the swatch preview
        rgb = UtilsTools.lab_to_rgb(lab)

        # --- Color swatch (fixed size) ---
        color_box = tk.Label(
            frame,
            bg=UtilsTools.rgb_to_hex(rgb),
            width=5,
            height=2,
            relief="solid",
            bd=1
        )
        color_box.pack(side="left", padx=(10, 10))

        # --- Checkbox (fixed to the far right) ---
        var = tk.BooleanVar()
        color_checks[color_name] = {"var": var, "lab": lab}
        ttk.Checkbutton(frame, variable=var).pack(side="right", padx=(10, 10))

        # --- Middle content (expands) ---
        text_frame = ttk.Frame(frame)
        text_frame.pack(side="left", fill="x", expand=True, padx=20)

        # ---- Name (fixed width so it never steals LAB space) ----
        MAX_NAME_CHARS = 10  # "round name" limit for display
        shown_name = color_name
        if len(shown_name) > MAX_NAME_CHARS:
            shown_name = shown_name[:MAX_NAME_CHARS - 1] + "…"

        name_lbl = ttk.Label(
            text_frame,
            text=shown_name,
            font=("Helvetica", 11),
            width=MAX_NAME_CHARS,
            anchor="w"
        )
        name_lbl.pack(side="left", padx=(0, 20))

        # ---- LAB (always visible on the right) ----
        lab_values = f"L: {lab['L']:.1f}, A: {lab['A']:.1f}, B: {lab['B']:.1f}"
        lab_lbl = ttk.Label(text_frame, text=lab_values, font=("Helvetica", 10, "italic"))
        lab_lbl.pack(side="right", padx=(20, 0))

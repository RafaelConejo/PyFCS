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

    def create_color_display_frame(
        self,
        parent,
        color_name,
        rgb,
        lab,
        color_checks,
        selected=False,
        on_toggle=None
    ):
        """
        Create a styled UI row to display a color with:
        - color swatch
        - color name
        - RGB/HEX preview
        - LAB values
        - checkbox

        Parameters
        ----------
        parent : widget
            Parent container.
        color_name : str
            Display name of the color.
        rgb : tuple/list
            RGB values.
        lab : tuple/list or dict
            LAB values.
        color_checks : dict
            Selection state dictionary.
        selected : bool
            Initial checkbox state.
        on_toggle : callable
            Optional callback after checkbox changes.
        """

        def _lab_to_tuple(lab_value):
            if isinstance(lab_value, dict):
                return (
                    float(lab_value.get("L", 0.0)),
                    float(lab_value.get("A", lab_value.get("a", 0.0))),
                    float(lab_value.get("B", lab_value.get("b", 0.0)))
                )

            return (
                float(lab_value[0]),
                float(lab_value[1]),
                float(lab_value[2])
            )

        L, A, B = _lab_to_tuple(lab)

        try:
            rgb_tuple = tuple(int(round(v)) for v in rgb)
            color_hex = UtilsTools.rgb_to_hex(rgb_tuple)
        except Exception:
            rgb_tuple = UtilsTools.lab_to_rgb((L, A, B))
            color_hex = UtilsTools.rgb_to_hex(rgb_tuple)

        # ------------------------------------------------------------------
        # Outer card
        # ------------------------------------------------------------------
        row = tk.Frame(
            parent,
            bg="white",
            bd=1,
            relief="solid",
            highlightthickness=0
        )
        row.pack(fill="x", expand=True, padx=10, pady=6)

        inner = tk.Frame(row, bg="white")
        inner.pack(fill="x", expand=True, padx=10, pady=8)

        # ------------------------------------------------------------------
        # Swatch
        # ------------------------------------------------------------------
        swatch_outer = tk.Frame(
            inner,
            bg="#e6e6e6",
            width=46,
            height=34
        )
        swatch_outer.pack(side="left", padx=(0, 12))
        swatch_outer.pack_propagate(False)

        color_box = tk.Label(
            swatch_outer,
            bg=color_hex,
            relief="solid",
            bd=1
        )
        color_box.pack(fill="both", expand=True, padx=2, pady=2)

        # ------------------------------------------------------------------
        # Text block
        # ------------------------------------------------------------------
        text_block = tk.Frame(inner, bg="white")
        text_block.pack(side="left", fill="x", expand=True)

        MAX_NAME_CHARS = 22
        shown_name = str(color_name)
        if len(shown_name) > MAX_NAME_CHARS:
            shown_name = shown_name[:MAX_NAME_CHARS - 1] + "…"

        name_row = tk.Frame(text_block, bg="white")
        name_row.pack(fill="x")

        tk.Label(
            name_row,
            text=shown_name,
            bg="white",
            fg="#222222",
            font=("Helvetica", 11, "bold"),
            anchor="w"
        ).pack(side="left")

        tk.Label(
            name_row,
            text=color_hex.upper(),
            bg="white",
            fg="#777777",
            font=("Consolas", 9),
            anchor="e"
        ).pack(side="right", padx=(8, 0))

        detail_row = tk.Frame(text_block, bg="white")
        detail_row.pack(fill="x", pady=(4, 0))

        rgb_text = f"RGB: {rgb_tuple[0]}, {rgb_tuple[1]}, {rgb_tuple[2]}"
        lab_text = f"L: {L:.1f}, A: {A:.1f}, B: {B:.1f}"

        tk.Label(
            detail_row,
            text=rgb_text,
            bg="white",
            fg="#666666",
            font=("Helvetica", 9),
            anchor="w"
        ).pack(side="left")

        tk.Label(
            detail_row,
            text=lab_text,
            bg="white",
            fg="#666666",
            font=("Helvetica", 9, "italic"),
            anchor="e"
        ).pack(side="right", padx=(8, 0))

        # ------------------------------------------------------------------
        # Checkbox
        # ------------------------------------------------------------------
        var = tk.BooleanVar(value=bool(selected))

        def _on_check():
            if callable(on_toggle):
                on_toggle()

        color_checks[color_name] = {
            "var": var,
            "lab": (L, A, B)
        }

        check = ttk.Checkbutton(
            inner,
            variable=var,
            command=_on_check
        )
        check.pack(side="right", padx=(12, 0))

        # ------------------------------------------------------------------
        # Optional: click anywhere on row toggles checkbox
        # ------------------------------------------------------------------
        def _toggle_from_row(event=None):
            var.set(not var.get())
            _on_check()

        for widget in (row, inner, swatch_outer, color_box, text_block, name_row, detail_row):
            widget.bind("<Button-1>", _toggle_from_row)

        return row


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

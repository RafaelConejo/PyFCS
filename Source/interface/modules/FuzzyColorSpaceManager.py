from tkinter import ttk
import tkinter as tk
import os
import numpy as np

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
    on_toggle=None,
    editable_name=False,
    on_name_change=None
    ):
        """
        Create a UI row to display a color with:
        - color swatch
        - editable or fixed color name
        - LAB values
        - checkbox

        Parameters
        ----------
        editable_name : bool
            If True, the color name is shown in an Entry.
        on_name_change : callable
            Callback called as:
                final_name = on_name_change(old_name, new_name)
        """
        MAX_NAME_CHARS = 18

        # ------------------------------------------------------------------
        # Normalize LAB
        # ------------------------------------------------------------------
        try:
            if isinstance(lab, dict):
                lab_display = (
                    float(lab.get("L", 0.0)),
                    float(lab.get("A", lab.get("a", 0.0))),
                    float(lab.get("B", lab.get("b", 0.0)))
                )
            else:
                lab_arr = np.array(lab, dtype=float).reshape(-1)
                lab_display = (
                    float(lab_arr[0]),
                    float(lab_arr[1]),
                    float(lab_arr[2])
                )
        except Exception:
            lab_display = (0.0, 0.0, 0.0)

        # ------------------------------------------------------------------
        # Normalize RGB / HEX
        # ------------------------------------------------------------------
        try:
            if hasattr(rgb, "tolist"):
                rgb = rgb.tolist()

            if isinstance(rgb, list) and len(rgb) == 1 and isinstance(rgb[0], (list, tuple, np.ndarray)):
                rgb = rgb[0]

            rgb = tuple(int(v) for v in rgb[:3])
            hex_color = UtilsTools.rgb_to_hex(rgb)
        except Exception:
            rgb = (217, 217, 217)
            hex_color = "#d9d9d9"

        # ------------------------------------------------------------------
        # Outer row/card
        # ------------------------------------------------------------------
        row_card = tk.Frame(
            parent,
            bg="#f4f4f4",
            bd=1,
            relief="solid"
        )
        row_card.pack(fill="x", expand=True, pady=6, padx=12)

        inner = tk.Frame(row_card, bg="#f4f4f4")
        inner.pack(fill="x", padx=10, pady=8)

        # ------------------------------------------------------------------
        # Swatch
        # ------------------------------------------------------------------
        swatch_container = tk.Frame(inner, bg="#f4f4f4", width=54)
        swatch_container.pack(side="left", fill="y")
        swatch_container.pack_propagate(False)

        color_box = tk.Label(
            swatch_container,
            bg=hex_color,
            width=4,
            height=2,
            relief="solid",
            bd=1
        )
        color_box.pack(anchor="center", pady=2)

        # ------------------------------------------------------------------
        # Name + LAB block
        # ------------------------------------------------------------------
        content = tk.Frame(inner, bg="#f4f4f4")
        content.pack(side="left", fill="x", expand=True, padx=(10, 10))

        top_line = tk.Frame(content, bg="#f4f4f4")
        top_line.pack(fill="x")

        current_name = {"value": str(color_name)}

        # ----- Editable name -----
        if editable_name:
            def _validate_name_length(proposed_text):
                try:
                    return len(proposed_text) <= MAX_NAME_CHARS
                except Exception:
                    return False

            vcmd = (parent.register(_validate_name_length), "%P")

            name_var = tk.StringVar(value=str(color_name)[:MAX_NAME_CHARS])

            name_entry = tk.Entry(
                top_line,
                textvariable=name_var,
                font=("Helvetica", 10),
                width=18,
                relief="solid",
                bd=1,
                bg="white",
                validate="key",
                validatecommand=vcmd
            )
            name_entry.pack(side="left", padx=(0, 14), ipady=2)

            def _commit_name(event=None):
                old_name = current_name["value"]

                try:
                    requested_name = name_var.get().strip()
                except Exception:
                    requested_name = old_name

                if len(requested_name) > MAX_NAME_CHARS:
                    requested_name = requested_name[:MAX_NAME_CHARS]

                if callable(on_name_change):
                    final_name = on_name_change(old_name, requested_name)
                else:
                    final_name = requested_name or old_name

                if not final_name:
                    final_name = old_name

                final_name = str(final_name).strip()[:MAX_NAME_CHARS]

                current_name["value"] = final_name
                name_var.set(final_name)

            name_entry.bind("<Return>", _commit_name)
            name_entry.bind("<FocusOut>", _commit_name)

        # ----- Fixed name -----
        else:
            shown_name = str(color_name)
            if len(shown_name) > MAX_NAME_CHARS:
                shown_name = shown_name[:MAX_NAME_CHARS - 1] + "…"

            tk.Label(
                top_line,
                text=shown_name,
                font=("Helvetica", 10, "bold"),
                bg="#f4f4f4",
                fg="#222222",
                anchor="w",
                width=18
            ).pack(side="left", padx=(0, 14))

        # ----- LAB values -----
        lab_text = f"L: {lab_display[0]:.1f}, A: {lab_display[1]:.1f}, B: {lab_display[2]:.1f}"

        tk.Label(
            top_line,
            text=lab_text,
            font=("Helvetica", 10, "italic"),
            bg="#f4f4f4",
            fg="#444444",
            anchor="w"
        ).pack(side="left", fill="x", expand=True)

        # ------------------------------------------------------------------
        # Checkbox block
        # ------------------------------------------------------------------
        var = tk.BooleanVar(value=selected)
        color_checks[color_name] = {"var": var, "lab": lab}

        def _notify_toggle():
            if callable(on_toggle):
                on_toggle()

        check_container = tk.Frame(inner, bg="#f4f4f4", width=34)
        check_container.pack(side="right", fill="y")
        check_container.pack_propagate(False)

        check = tk.Checkbutton(
            check_container,
            variable=var,
            command=_notify_toggle,
            bg="#f4f4f4",
            activebackground="#f4f4f4",
            bd=0,
            highlightthickness=0
        )
        check.pack(anchor="center")
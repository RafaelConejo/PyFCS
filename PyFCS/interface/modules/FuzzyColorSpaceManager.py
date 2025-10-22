from tkinter import ttk
import tkinter as tk
import os

### my libraries ###
from PyFCS import Input
import PyFCS.interface.modules.UtilsTools as UtilsTools

class FuzzyColorSpaceManager:
    SUPPORTED_EXTENSIONS = {'.cns', '.fcs'}

    def __init__(self, root):
        self.root = root

    @staticmethod
    def load_color_file(filename):
        """
        Loads a fuzzy color space or color data file (.cns or .fcs)
        and returns the parsed data.
        """
        extension = os.path.splitext(filename)[1].lower()

        if extension not in FuzzyColorSpaceManager.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file format: {extension}")

        input_class = Input.instance(extension)

        if extension == '.cns':
            color_data = input_class.read_file(filename)
            return {'type': 'cns', 'color_data': color_data}

        elif extension == '.fcs':
            color_data, fuzzy_color_space = input_class.read_file(filename)
            return {
                'type': 'fcs',
                'color_data': color_data,
                'fuzzy_color_space': fuzzy_color_space
            }
    

    def create_color_display_frame(self, parent, color_name, rgb, lab, color_checks):
        """
        Creates a frame for displaying color information, including a color box, labels, and a Checkbutton.
        """
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=8, padx=10)

        # Color box
        color_box = tk.Label(frame, bg=UtilsTools.rgb_to_hex(rgb), width=4, height=2, relief="solid", bd=1)
        color_box.pack(side="left", padx=10)

        # Color name
        tk.Label(
            frame,
            text=color_name,
            font=("Helvetica", 12),
            bg="#f5f5f5"
        ).pack(side="left", padx=10)

        # LAB values
        lab_values = f"L: {lab[0]:.1f}, A: {lab[1]:.1f}, B: {lab[2]:.1f}"
        tk.Label(
            frame,
            text=lab_values,
            font=("Helvetica", 10, "italic"),
            bg="#f5f5f5"
        ).pack(side="left", padx=10)

        # Checkbutton for selection
        var = tk.BooleanVar()
        color_checks[color_name] = {"var": var, "lab": lab}
        ttk.Checkbutton(frame, variable=var).pack(side="right", padx=10)


    def create_color_display_frame_add(self, parent, color_name, lab, color_checks):
        """
        Creates a frame for displaying color information, including labels for the color name, LAB values, and a Checkbutton.
        """
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=8, padx=10)

        rgb = UtilsTools.lab_to_rgb(lab)

        # Color box
        color_box = tk.Label(frame, bg=UtilsTools.rgb_to_hex(rgb), width=4, height=2, relief="solid", bd=1)
        color_box.pack(side="left", padx=10)

        # Color name
        tk.Label(
            frame,
            text=color_name,
            font=("Helvetica", 12),
            bg="#f5f5f5"
        ).pack(side="left", padx=10)

        # LAB values
        lab_values = f"L: {lab['L']:.1f}, A: {lab['A']:.1f}, B: {lab['B']:.1f}"
        tk.Label(
            frame,
            text=lab_values,
            font=("Helvetica", 10, "italic"),
            bg="#f5f5f5"
        ).pack(side="left", padx=10)

        # Checkbutton for selection
        var = tk.BooleanVar()
        color_checks[color_name] = {"var": var, "lab": lab}
        ttk.Checkbutton(frame, variable=var).pack(side="right", padx=10)



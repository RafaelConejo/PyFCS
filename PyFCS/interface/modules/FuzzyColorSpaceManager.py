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
        Creates a frame for displaying color information, including a color box,
        name on the left, LAB on the right, and a Checkbutton on the far right.
        Matches the layout of create_color_display_frame_add.
        """
        frame = ttk.Frame(parent)
        frame.pack(fill="x", expand=True, pady=8, padx=20)

        # Color box (fixed)
        color_box = tk.Label(frame, bg=UtilsTools.rgb_to_hex(rgb), width=5, height=2, relief="solid", bd=1)
        color_box.pack(side="left", padx=(10, 10))

        # Checkbutton (fixed right)
        var = tk.BooleanVar()
        color_checks[color_name] = {"var": var, "lab": lab}
        ttk.Checkbutton(frame, variable=var).pack(side="right", padx=(10, 10))

        # Middle content (expands)
        text_frame = ttk.Frame(frame)
        text_frame.pack(side="left", fill="x", expand=True, padx=20)

        # Name (left)
        name_lbl = ttk.Label(text_frame, text=color_name, font=("Helvetica", 11))
        name_lbl.pack(side="left", padx=(0, 20))

        # LAB (right)
        lab_values = f"L: {lab[0]:.1f}, A: {lab[1]:.1f}, B: {lab[2]:.1f}"
        lab_lbl = ttk.Label(text_frame, text=lab_values, font=("Helvetica", 10, "italic"))
        lab_lbl.pack(side="right", padx=(20, 0))



    def create_color_display_frame_add(self, parent, color_name, lab, color_checks):
        """
        Color row where LAB is always visible.
        The name is width-limited (and can be truncated) to prevent pushing LAB off-screen.
        """
        frame = ttk.Frame(parent)
        frame.pack(fill="x", expand=True, pady=8, padx=20)

        rgb = UtilsTools.lab_to_rgb(lab)

        # Color box (fixed)
        color_box = tk.Label(frame, bg=UtilsTools.rgb_to_hex(rgb), width=5, height=2, relief="solid", bd=1)
        color_box.pack(side="left", padx=(10, 10))

        # Checkbutton (fixed right)
        var = tk.BooleanVar()
        color_checks[color_name] = {"var": var, "lab": lab}
        ttk.Checkbutton(frame, variable=var).pack(side="right", padx=(10, 10))

        # Middle content
        text_frame = ttk.Frame(frame)
        text_frame.pack(side="left", fill="x", expand=True, padx=20)

        # ---- Name (fixed width so it never eats LAB space) ----
        MAX_NAME_CHARS = 10  # round name
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





"""Read-only FCS Data view and transactional granular-aware Modify FCS editor.

Data displays actual model sites, rather than the single-representative legacy
``edit_color_data``. Modify FCS edits a private copy and commits only after a
successful JSON write. The geometric model selector is deliberately extensible.
"""

from collections import OrderedDict
import copy
import re
import tkinter as tk
from tkinter import ttk, messagebox

import numpy as np

from Source.fuzzy.FuzzyColorSpaceBuilder import (
    FuzzyColorSpaceBuilder, lab_to_rgb_model_checked, rebuild_in_color_space,
)
from Source.fuzzy.GranularFuzzyColorSpace import GranularFuzzyColorSpace
from Source.interface.modules import UtilsTools
from Source.interface.modules.PaletteBasedCreationManager import PaletteBasedCreationManager


# The list is a capability registry, not a hard-coded two-state LAB/RGB switch.
# Register the corresponding geometry/conversion implementation before adding
# a future color model here.
GEOMETRIC_MODELS = OrderedDict((
    ("LAB", "CIELAB"),
    ("RGB", "sRGB"),
))

BG = "#f5f6f8"
WHITE = "#ffffff"
PANEL = "#fbfbfc"
BORDER = "#d9dde3"
TEXT = "#1f2937"
MUTED = "#6b7280"
PURPLE = UtilsTools.UI_ACCENT
SOFT_PURPLE = UtilsTools.UI_ACCENT_SOFT
FONT = ("Segoe UI", 9)
BOLD = ("Segoe UI", 9, "bold")
SMALL = ("Segoe UI", 8)


def _rgb(lab):
    return tuple(UtilsTools.safe_rgb_tuple(UtilsTools.lab_to_rgb(lab)))


def _hex(lab):
    return UtilsTools.rgb_to_hex(_rgb(lab)).upper()


def _triple(lab):
    return tuple(float(v) for v in np.asarray(lab, dtype=float).reshape(3))


def extract_categories(space):
    """Return independent LAB-granule lists with stable source IDs."""
    groups = OrderedDict()
    if isinstance(space, GranularFuzzyColorSpace):
        for category in space.categories:
            groups[category.label] = {
                "source": category.label,
                "granules": [
                    {"label": p.label, "lab": _triple(space.lab_from_model(p.positive)),
                     "original_label": p.label}
                    for p in category.prototypes
                ],
            }
    else:
        for p in space.prototypes:
            groups[p.label] = {
                "source": p.label,
                "granules": [{"label": p.label,
                              "lab": _triple(space.lab_from_model(p.positive)),
                              "original_label": p.label}],
            }
    return groups


def validate_draft(categories):
    """Validate all edits without mutating the active model or raising from Tk."""
    if len(categories) < 2:
        return "At least two color categories are required."
    occupied = []
    for category, data in categories.items():
        if not category or len(category) > UtilsTools.MAX_COLOR_NAME_CHARS:
            return "Category names must contain 1 to 24 characters."
        items = data.get("granules", [])
        if not items:
            return f"Category '{category}' must contain at least one granule."
        for item in items:
            _name, _lab, error = UtilsTools.check_granule_site(
                item.get("label"), item.get("lab"), occupied,
                max_name_length=UtilsTools.MAX_COLOR_NAME_CHARS,
            )
            if error:
                return error
            occupied.append((category, item["label"], item["lab"]))
    return ""



def _table_columns(parent):
    """Six aligned Data columns, sized to fit the narrower notebook tab."""
    widths = (
        (187, 6),  # Category or granule name and color swatch
        (53, 1),   # Model component 1: L* / R
        (53, 1),   # Model component 2: a* / G
        (53, 1),   # Model component 3: b* / B
        (39, 0),   # Hover information
        (91, 2),   # Granule count
    )
    parent.grid_rowconfigure(0, weight=1)
    for index, (min_width, weight) in enumerate(widths):
        parent.grid_columnconfigure(index, minsize=min_width, weight=weight)



def _editor_columns(parent):
    """Five-column layout used only by the Edit FCS category table."""
    widths = (
        (268, 5),   # Editable category name and swatch
        (112, 2),   # RGB
        (88, 1),    # HEX
        (165, 3),   # CIELAB
        (151, 2),   # Granule count and actions
    )
    for i, (min_width, weight) in enumerate(widths):
        parent.grid_columnconfigure(i, minsize=min_width, weight=weight)


def _model_value_text(lab, model):
    model = str(model or "LAB").upper()
    if model == "RGB":
        return ", ".join(map(str, _rgb(lab)))
    return ", ".join(f"{value:.2f}" for value in lab)


def _model_component_columns(lab, model):
    """Headings and display values for the three currently supported models."""
    model = str(model or "LAB").upper()

    if model == "RGB":
        return (
            ("R", "G", "B"),
            tuple(str(value) for value in _rgb(lab)),
        )

    if model == "LAB":
        return (
            ("L*", "a*", "b*"),
            tuple(f"{value:.2f}" for value in lab),
        )

    # Adding another geometric model also requires its coordinate converter.
    # Do not silently present unknown coordinates as RGB.
    raise ValueError(f"Unsupported Data color model '{model}'.")



def _info_text(lab):
    rgb_text = ", ".join(map(str, _rgb(lab)))
    lab_text = ", ".join(f"{value:.2f}" for value in lab)
    return f"RGB: {rgb_text}\nHEX: {_hex(lab)}\nCIELAB: {lab_text}"


def _attach_info_tooltip(app, widget, text, *, prefer_left=False):
    def _show(_event=None):
        try:
            if getattr(app, '_data_info_tooltip', None) is not None:
                app._data_info_tooltip.destroy()
        except Exception:
            pass
        popup = tk.Toplevel(widget)
        popup.wm_overrideredirect(True)
        popup.configure(bg=TEXT)
        label = tk.Label(
            popup,
            text=text,
            justify='left',
            anchor='w',
            bg=TEXT,
            fg='white',
            font=SMALL,
            padx=9,
            pady=6,
        )
        label.pack()
        try:
            # Place Edit FCS help to the LEFT of its icon: the editor
            # can sit near the right screen edge. Measure the tooltip first,
            # then clamp its coordinates to the visible desktop area.
            popup.update_idletasks()
            tip_w = popup.winfo_reqwidth()
            tip_h = popup.winfo_reqheight()
            screen_w = widget.winfo_screenwidth()
            screen_h = widget.winfo_screenheight()
            left_x = widget.winfo_rootx() - tip_w - 12
            right_x = widget.winfo_rootx() + widget.winfo_width() + 10
            if prefer_left and left_x >= 8:
                x = left_x
            elif right_x + tip_w <= screen_w - 8:
                x = right_x
            else:
                x = max(8, left_x)
            x = max(8, min(x, max(8, screen_w - tip_w - 8)))
            y = max(8, min(widget.winfo_rooty() - 4,
                           max(8, screen_h - tip_h - 8)))
            popup.geometry(f'+{x}+{y}')
            popup.lift()
        except tk.TclError:
            popup.destroy()
            return
        app._data_info_tooltip = popup

    def _hide(_event=None):
        tooltip = getattr(app, '_data_info_tooltip', None)
        if tooltip is not None:
            try:
                tooltip.destroy()
            except Exception:
                pass
            app._data_info_tooltip = None

    widget.bind('<Enter>', _show, add='+')
    widget.bind('<Leave>', _hide, add='+')
    widget.bind('<Button-1>', _hide, add='+')


def _cell(parent, col, value, *, background=WHITE, color=MUTED,
          font=FONT, justify="center", padx=4):
    label = tk.Label(parent, text=value, bg=background, fg=color, font=font,
                     anchor=justify, justify=("left" if justify == "w" else justify))
    label.grid(row=0, column=col, sticky="nsew", padx=padx)
    return label


def _swatch(parent, lab, size=25, bg=WHITE):
    canvas = tk.Canvas(parent, width=size, height=size, bg=bg,
                       borderwidth=0, highlightthickness=0)
    canvas.create_rectangle(1, 1, size - 1, size - 1,
                            fill=_hex(lab), outline="#979ca6")
    return canvas



def render_data(app):
    """Rebuild the Data view from the real loaded model, never edit state."""
    canvas = app.data_window
    if not canvas.winfo_exists():
        return

    expanded = getattr(app, "_data_expanded_categories", set())
    app._data_expanded_categories = expanded

    for child in canvas.winfo_children():
        child.destroy()

    canvas.delete("all")
    app._data_label_editors = []

    space = (
        getattr(app, "fuzzy_color_space", None)
        if getattr(app, "COLOR_SPACE", False)
        or bool(getattr(app, "color_data", None))
        else None
    )

    if space is None:
        if hasattr(app, "data_header_title"):
            app.data_header_title.configure(
                text="No Fuzzy Color Space Loaded"
            )
        canvas.configure(scrollregion=(0, 0, 0, 0))
        app._update_data_model_summary()
        return

    groups = extract_categories(space)
    model_key = str(
        getattr(space, "color_space", "LAB") or "LAB"
    ).upper()

    # The Data view reflects the loaded geometric model.
    component_headings, _ = _model_component_columns(
        (0.0, 0.0, 0.0), model_key
    )

    app.color_matrix = list(groups)
    app.hex_color = {
        _hex(data["granules"][0]["lab"]): data["granules"][0]["lab"]
        for data in groups.values()
    }

    app.data_header_title.configure(
        text=str(
            getattr(
                space,
                "typology_description",
                "Fuzzy Color Space",
            )
        )
    )

    if hasattr(app, "file_name_entry"):
        name = str(app.file_base_name or "")
        try:
            app.file_name_entry.configure(state="normal")
            app.file_name_entry.delete(0, tk.END)
            app.file_name_entry.insert(0, name)
            app.file_name_entry.configure(
                state="readonly",
                readonlybackground=WHITE,
            )
        except tk.TclError:
            pass

    app._update_data_model_summary()

    content = tk.Frame(canvas, bg=WHITE)
    winid = canvas.create_window(
        (0, 0), window=content, anchor="nw"
    )
    canvas.configure(scrollregion=(0, 0, 0, 0))

    def on_size(event):
        try:
            canvas.itemconfigure(
                winid, width=max(event.width - 2, 1)
            )
            canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        except tk.TclError:
            pass

    canvas.bind("<Configure>", on_size)
    content.bind(
        "<Configure>",
        lambda _e: canvas.configure(
            scrollregion=canvas.bbox("all")
        ),
    )

    # Table heading
    heading = tk.Frame(
        content,
        bg="#f1f3f6",
        height=34,
    )
    heading.pack(fill="x", padx=5, pady=(3, 0))
    heading.pack_propagate(False)
    _table_columns(heading)

    
    columns = ("COLOR CATEGORY", *component_headings, "INFO", "GRANULES")

    for i, name in enumerate(columns):
        # Center channel headings within their columns,
        # keeping the category title left-aligned.
        tk.Label(
            heading,
            text=name,
            bg="#f1f3f6",
            fg=MUTED,
            font=("Segoe UI", 8, "bold"),
            anchor="w" if i == 0 else "center",
            justify="left" if i == 0 else "center",
        ).grid(
            row=0,
            column=i,
            sticky="nsew",
            padx=(10, 3) if i == 0 else 0,
        )


    # One shared wheel binding for all table descendants.
    wheel_tag = "PyFCSDataTableWheel"

    def _scroll_table(event):
        try:
            return app.on_mouse_wheel(event, canvas)
        except (tk.TclError, ValueError):
            return "break"

    for sequence in (
        "<MouseWheel>",
        "<Button-4>",
        "<Button-5>",
    ):
        canvas.bind_class(
            wheel_tag, sequence, _scroll_table
        )

    def _bind_table_children(widget):
        tags = widget.bindtags()
        if wheel_tag not in tags:
            widget.bindtags(
                (tags[0], wheel_tag) + tags[1:]
            )

        for child_widget in widget.winfo_children():
            _bind_table_children(child_widget)

    # Categories
    for i, (category, data) in enumerate(groups.items()):
        n = len(data["granules"])
        bg = WHITE if i % 2 == 0 else PANEL

        wrapper = tk.Frame(content, bg=WHITE)
        wrapper.pack(fill="x", padx=5, pady=2)

        row = tk.Frame(wrapper, bg=bg, height=46)
        row.pack(fill="x")
        row.pack_propagate(False)
        _table_columns(row)

        first = data["granules"][0]["lab"]

        color_cell = tk.Frame(row, bg=bg)
        color_cell.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(10, 4),
        )

        # Label instead of Button:
        # prevents the dotted focus rectangle on Windows.
        arrow = tk.Label(
            color_cell,
            text="▾" if category in expanded else "▸",
            bg=bg,
            fg=PURPLE,
            font=BOLD,
            width=2,
            anchor="center",
            cursor="hand2",
            takefocus=1,
        )
        arrow.pack(side="left")

        _swatch(
            color_cell,
            first,
            bg=bg,
        ).pack(side="left", padx=(5, 10))

        tk.Label(
            color_cell,
            text=category,
            fg=TEXT,
            bg=bg,
            font=BOLD,
            anchor="w",
        ).pack(
            side="left",
            fill="x",
            expand=True,
        )

        _, component_values = _model_component_columns(
            first, model_key
        )

        # Category values are hidden when expanded.
        value_labels = [
            _cell(
                row,
                index + 1,
                "" if category in expanded else value,
                background=bg,
                color=TEXT,
                justify="center",
                padx=3,
            )
            for index, value in enumerate(component_values)
        ]

        count_label = _cell(
            row,
            5,
            f"{n} granule{'s' if n != 1 else ''}",
            background=SOFT_PURPLE if n > 1 else bg,
            color=PURPLE if n > 1 else MUTED,
            font=BOLD if n > 1 else FONT,
        )

        count_label.configure(cursor="hand2")


        info_cell = tk.Frame(row, bg=bg)
        info_cell.grid(
            row=0,
            column=4,
            sticky="nsew",
            padx=(2, 3),
        )

        info_btn = tk.Label(
            info_cell,
            text="ⓘ",
            bg=bg,
            fg=PURPLE,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
        )
        info_btn.pack(expand=True)

        _attach_info_tooltip(
            app,
            info_btn,
            _info_text(first),
        )

        panel = tk.Frame(wrapper, bg=WHITE)

        def toggle(
            name=category,
            block=panel,
            control=arrow,
            summary=tuple(value_labels),
            values=component_values,
        ):
            if name in expanded:
                expanded.remove(name)
                block.pack_forget()
                control.configure(text="▸")

                for label, value in zip(
                    summary, values
                ):
                    label.configure(text=value)

            else:
                expanded.add(name)
                block.pack(fill="x")
                control.configure(text="▾")

                for label in summary:
                    label.configure(text="")

            canvas.configure(
                scrollregion=canvas.bbox("all")
            )

        arrow.bind(
            "<Button-1>",
            lambda _event, fn=toggle: fn(),
        )
        arrow.bind(
            "<Return>",
            lambda _event, fn=toggle: fn(),
        )
        arrow.bind(
            "<space>",
            lambda _event, fn=toggle: fn(),
        )


        # Allow expanding/collapsing by clicking the granule count.
        count_label.bind(
            "<Button-1>",
            lambda _event, fn=toggle: fn(),
        )


        # Granules
        for granule in data["granules"]:
            child = tk.Frame(
                panel,
                bg="#fafbfc",
                height=38,
            )
            child.pack(fill="x")
            child.pack_propagate(False)
            _table_columns(child)

            firstcell = tk.Frame(
                child,
                bg="#fafbfc",
            )
            firstcell.grid(
                row=0,
                column=0,
                sticky="nsew",
                padx=(46, 5),
            )

            tk.Label(
                firstcell,
                text="↳",
                bg="#fafbfc",
                fg="#aab1bd",
                font=SMALL,
            ).pack(side="left")

            _swatch(
                firstcell,
                granule["lab"],
                size=21,
                bg="#fafbfc",
            ).pack(
                side="left",
                padx=(8, 8),
            )

            tk.Label(
                firstcell,
                text=granule["label"],
                bg="#fafbfc",
                fg=TEXT,
                font=FONT,
                anchor="w",
            ).pack(side="left")

            lab = granule["lab"]

            _, granule_values = _model_component_columns(
                lab, model_key
            )

            for index, value in enumerate(
                granule_values
            ):
                _cell(
                    child,
                    index + 1,
                    value,
                    background="#fafbfc",
                    color=TEXT,
                    font=SMALL,
                    padx=3,
                )

            _cell(
                child,
                5,
                "",
                background="#fafbfc",
            )

            child_info = tk.Frame(
                child,
                bg="#fafbfc",
            )
            child_info.grid(
                row=0,
                column=4,
                sticky="nsew",
                padx=(2, 3),
            )

            child_info_btn = tk.Label(
                child_info,
                text="ⓘ",
                bg="#fafbfc",
                fg=PURPLE,
                font=("Segoe UI", 9, "bold"),
                cursor="hand2",
            )
            child_info_btn.pack(expand=True)

            _attach_info_tooltip(
                app,
                child_info_btn,
                _info_text(lab),
            )

        if category in expanded:
            panel.pack(fill="x")

    # Enable mouse-wheel scrolling over all row widgets.
    _bind_table_children(content)

    def _fit_width():
        try:
            if canvas.winfo_exists():
                canvas.itemconfigure(
                    winid,
                    width=max(
                        canvas.winfo_width() - 2,
                        1,
                    ),
                )
                canvas.configure(
                    scrollregion=canvas.bbox("all")
                )
        except tk.TclError:
            pass

    canvas.after_idle(_fit_width)



class _CategoryHost:
    """Small palette-compatible adapter reusing the existing category dialog."""

    def __init__(self, editor):
        self.editor = editor
        self.app = editor.app
        self.win = editor.win
        for attr in ("BG", "CARD", "PANEL", "SOFT", "BORDER", "TEXT", "MUTED",
                     "BLUE", "BLUE_SOFT", "FONT", "FONT_BOLD", "FONT_SMALL",
                     "FONT_SMALL_BOLD", "FONT_SECTION"):
            setattr(self, attr, getattr(PaletteBasedCreationManager, attr))
        self.colors = OrderedDict()
        self.color_checks = {}
        self.search_var = tk.StringVar(value="")
        self._expanded_categories = set()
        for name, data in editor.categories.items():
            lab = data["granules"][0]["lab"]
            self.colors[name] = dict(
                lab=lab, rgb=_rgb(lab), hex=_hex(lab),
                granules=[{"label": g["label"], "lab": g["lab"], "enabled": True}
                          for g in data["granules"]],
            )

    def _used_granule_labels(self):
        return {g["label"] for data in self.colors.values() for g in data["granules"]}

    def _matches_search(self, name):
        return True

    def _scroll_to_bottom(self):
        return None

    def _append_color_rows(self, names):
        for name in names:
            value = self.colors[name]
            self.editor._insert_category(name, value["granules"])


class ModifyFCSDialog:
    """Transactional, granular-aware editor; no writes to the active FCS."""

    def __init__(self, app):
        self.app = app
        self.space = app.fuzzy_color_space
        self.source_id = id(self.space)
        self.categories = extract_categories(self.space)
        self.expanded = set()
        self._renaming = set()
        self._saving = False
        self._editor_rows = OrderedDict()
        self._search_collapsed = set()
        self._search_after_id = None
        self.search_var = tk.StringVar(value="")
        self.search_results_var = tk.StringVar(value="")
        self.win = tk.Toplevel(app.root)
        self.win.withdraw()
        self.win.title("Edit Fuzzy Color Space")
        self.win.configure(bg=BG)
        self.win.minsize(850, 520)
        self.win.transient(app.root)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.app._modify_fcs_dialog = self
        window_width, window_height = 950, 640
        try:
            app.root.update_idletasks()
            screen_w = self.win.winfo_screenwidth()
            screen_h = self.win.winfo_screenheight()
            parent_w = app.root.winfo_width()
            parent_h = app.root.winfo_height()
            if parent_w > 1 and parent_h > 1:
                x = app.root.winfo_rootx() + (parent_w - window_width) // 2
                y = app.root.winfo_rooty() + (parent_h - window_height) // 2 - 40
            else:
                x = (screen_w - window_width) // 2
                y = (screen_h - window_height) // 2 - 40
            # Set coordinates directly: a withdrawn Toplevel reports 0,0
            # on some Tk/window-manager combinations until it is mapped.
            x = max(0, min(x, max(0, screen_w - window_width)))
            y = max(10, min(y, max(10, screen_h - window_height - 35)))
            self.win.geometry(f"{window_width}x{window_height}+{x}+{y}")
        except tk.TclError:
            self.win.geometry(f"{window_width}x{window_height}")
        self.file_var = tk.StringVar(value=str(app.file_base_name))
        self.model_var = tk.StringVar(value=self.space.color_space)
        self.status_var = tk.StringVar(value="Changes remain local until Apply Changes.")
        self._build()
        self.search_var.trace_add("write", self._on_search_changed)
        self.refresh()
        self.win.bind("<Escape>", lambda _event: self.close())
        self.win.deiconify()
        self.win.focus_set()

    def close(self):
        if self._saving:
            return
        
        menu = getattr(self, "_move_menu", None)

        if menu is not None:
            try:
                menu.destroy()
            except tk.TclError:
                pass

            self._move_menu = None

        if self._search_after_id is not None:
            try:
                self.win.after_cancel(self._search_after_id)
            except tk.TclError:
                pass
            self._search_after_id = None
        if getattr(self.app, "_modify_fcs_dialog", None) is self:
            self.app._modify_fcs_dialog = None
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def _warning(self, message, title="Invalid Modification"):
        self.status_var.set(message)
        try:
            self.app.custom_warning(title, message, parent=self.win)
        except (RuntimeError, tk.TclError):
            pass

    def _build(self):
        base = tk.Frame(self.win, bg=BG)
        base.pack(fill="both", expand=True, padx=13, pady=12)
        header = tk.Frame(base, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        header.pack(fill="x", pady=(0, 9))
        tk.Label(header, text="Edit Fuzzy Color Space", font=("Segoe UI", 14, "bold"),
                 bg=WHITE, fg=TEXT).pack(side="left", padx=(17, 10), pady=12)
        tk.Label(header, text="Edit categories, granules and geometric color space",
                 font=SMALL, bg=WHITE, fg=MUTED, anchor="e").pack(
                     side="right", padx=(8, 17), pady=12)

        # One concise row: name and geometric model have equal space.
        # More models can be registered in GEOMETRIC_MODELS without changing
        # the layout or requiring another LAB/RGB-specific switch.
        settings = tk.Frame(base, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        settings.pack(fill="x", pady=(0, 9))
        settings.grid_columnconfigure(0, weight=1, uniform="model_settings")
        settings.grid_columnconfigure(1, weight=1, uniform="model_settings")

        left = tk.Frame(settings, bg=WHITE)
        left.grid(row=0, column=0, sticky="ew", padx=(16, 18), pady=12)
        tk.Label(left, text="Color space name", bg=WHITE, fg=TEXT, font=BOLD,
                 anchor="w").pack(side="left", padx=(0, 12))
        tk.Entry(left, textvariable=self.file_var, font=FONT,
                 relief="solid", bd=1).pack(side="left", fill="x", expand=True)

        right = tk.Frame(settings, bg=WHITE)
        right.grid(row=0, column=1, sticky="ew", padx=(6, 16), pady=12)
        tk.Label(right, text="Geometric model", bg=WHITE, fg=TEXT, font=BOLD,
                 anchor="w").pack(side="left", padx=(0, 10))
        self.model_box = ttk.Combobox(
            right, values=list(GEOMETRIC_MODELS), textvariable=self.model_var,
            state="readonly", width=12)
        self.model_box.pack(side="left", fill="x", expand=True)
        info = tk.Label(right, text="ⓘ", fg=PURPLE, bg=WHITE,
                        font=("Segoe UI", 10, "bold"), cursor="hand2")
        info.pack(side="left", padx=(9, 0))
        _attach_info_tooltip(
            self.app, info,
            "Changing the geometric model reconstructs Core, Voronoi and Support."
            "\nThe conversion will be confirmed when you apply changes.",
            prefer_left=True,
        )

        category_card = tk.Frame(base, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        category_card.pack(fill="both", expand=True)
        toolbar = tk.Frame(category_card, bg=WHITE)
        toolbar.pack(fill="x", padx=13, pady=7)
        self.count = tk.StringVar(value="")
        tk.Label(toolbar, text="Color categories", bg=WHITE, fg=TEXT,
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Label(toolbar, textvariable=self.count, bg=WHITE, fg=MUTED,
                 font=SMALL).pack(side="left", padx=(12, 0))
        tk.Button(toolbar, text="+ Add Color Category", command=self.add_category,
                  bg=UtilsTools.UI_ADD_CATEGORY_BG, fg=UtilsTools.UI_ADD_CATEGORY_FG,
                  activebackground=UtilsTools.UI_ADD_CATEGORY_HOVER,
                  activeforeground=UtilsTools.UI_ADD_CATEGORY_FG,
                  font=BOLD, relief="flat", bd=0, highlightthickness=0,
                  cursor="hand2", padx=12, pady=6).pack(side="right")

        # Filtering affects visibility only: all categories and their granules
        # stay in the draft and are still included in Apply Changes.
        search_bar = tk.Frame(category_card, bg=WHITE)
        # Slightly inset the filter controls to distinguish them visually
        # from the "Color categories" heading and the table header.
        search_bar.pack(fill="x", padx=(27, 16), pady=(3, 9))
        tk.Label(search_bar, text="Search", bg=WHITE, fg=MUTED,
                 font=BOLD).pack(side="left", padx=(0, 10))
        self.search_entry = tk.Entry(
            search_bar, textvariable=self.search_var, font=FONT,
            relief="solid", bd=1, bg=WHITE, fg=TEXT, width=44,
        )
        self.search_entry.pack(side="left", ipady=3)
        tk.Button(search_bar, text="Clear", command=lambda: self.search_var.set(""),
                  bg=PANEL, fg=MUTED, font=FONT, relief="flat", bd=0,
                  cursor="hand2", padx=8, pady=3).pack(side="left", padx=(6, 0))
        tk.Label(search_bar, textvariable=self.search_results_var,
                 bg=WHITE, fg=MUTED, font=SMALL, anchor="e",
                 width=16).pack(side="right", padx=(8, 0))

        canvas_frame = tk.Frame(category_card, bg=WHITE)
        canvas_frame.pack(fill="both", expand=True, padx=13, pady=(0, 9))
        self.canvas = tk.Canvas(canvas_frame, bg=WHITE, highlightthickness=0, bd=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        scroll.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=scroll.set)
        self.inner = tk.Frame(self.canvas, bg=WHITE)
        self.wid = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _e:
                        self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e:
                         self.canvas.itemconfigure(self.wid, width=max(1, e.width - 2)))
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.bind(sequence, self._on_table_wheel)

        footer = tk.Frame(base, bg=BG)
        footer.pack(fill="x", pady=(9, 0))
        tk.Label(footer, textvariable=self.status_var, font=SMALL,
                 fg=MUTED, bg=BG, anchor="w").pack(side="left", fill="x", expand=True)
        tk.Button(footer, text="Cancel", command=self.close,
                  bg="#e8eaed", fg=TEXT, font=FONT, relief="flat",
                  padx=15, pady=9).pack(side="right", padx=(9, 0))
        self.apply_btn = tk.Button(footer, text="Apply Changes", command=self.apply,
                                   bg=PURPLE, fg=WHITE, font=BOLD, relief="flat",
                                   activebackground=UtilsTools.UI_ACCENT_DARK,
                                   cursor="hand2", padx=18, pady=9)
        self.apply_btn.pack(side="right")

    def _on_search_changed(self, *_args):
        """Debounce typing so a large FCS remains responsive while searching."""
        self._search_collapsed.clear()
        if self._search_after_id is not None:
            try:
                self.win.after_cancel(self._search_after_id)
            except tk.TclError:
                pass
        self._search_after_id = self.win.after(75, self._apply_search_filter)

    @staticmethod
    def _search_hits(category, granules, query):
        """Match categories and granules case-insensitively, with multiple words."""
        terms = query.casefold().split()
        if not terms:
            return True, list(range(len(granules)))
        category_text = category.casefold()
        category_match = all(term in category_text for term in terms)
        matched_indices = [
            i for i, item in enumerate(granules)
            if all(term in (category_text + " " + item["label"].casefold())
                   for term in terms)
        ]
        return category_match, matched_indices

    
    def _toggle_editor_category(self, category):
        """Toggle one section in place; filtering still controls search hits."""
        query = self.search_var.get().strip()
        row = self._editor_rows.get(category)

        if row is None:
            return

        category_match, hits = self._search_hits(
            category,
            self.categories[category]["granules"],
            query
        )

        auto_expand = bool(
            query and not category_match and hits
        )

        expanded = category in self.expanded or (
            auto_expand and category not in self._search_collapsed
        )

        if expanded:
            self.expanded.discard(category)

            if query:
                self._search_collapsed.add(category)
        else:
            self._search_collapsed.discard(category)
            self.expanded.add(category)

        if query:
            self._apply_search_filter()
            return

        # Unlike the filter, normal clicks affect only one row.
        # Avoid unpacking/repacking unrelated category widgets.
        is_open = category in self.expanded

        row["toggle"].configure(
            text="▾" if is_open else "▸"
        )

        for label, value in zip(
            row["summary"],
            row["values"]
        ):
            label.configure(
                text="" if is_open else value
            )

        if is_open:
            row["panel"].pack(fill="x")
        else:
            row["panel"].pack_forget()

        self.canvas.configure(
            scrollregion=self.canvas.bbox("all")
        )


    def _apply_search_filter(self):
        """Hide/show existing rows; never reconstruct widgets for each keystroke."""
        self._search_after_id = None
        try:
            if not self.win.winfo_exists():
                return
        except tk.TclError:
            return
        query = self.search_var.get().strip()
        total = len(self.categories)
        visible = 0
        had_scroll = self.canvas.yview()[0] if self.canvas.winfo_exists() else 0.0

        for category, row in self._editor_rows.items():
            granules = self.categories[category]["granules"]
            category_match, hits = self._search_hits(category, granules, query)
            show = not query or category_match or bool(hits)
            row["wrapper"].pack_forget()
            if not show:
                continue
            visible += 1
            row["wrapper"].pack(fill="x", pady=2)
            auto_expand = bool(query and not category_match and hits)
            expanded = category in self.expanded or (
                auto_expand and category not in self._search_collapsed)
            row["toggle"].configure(text="▾" if expanded else "▸")
            for label, value in zip(row["summary"], row["values"]):
                label.configure(text="" if expanded else value)

            row["panel"].pack_forget()
            if expanded:
                # Put granule rows back in the original order, before Add granule.
                # Only matching granules appear for a specific granule search.
                for _, item_row in row["granule_rows"]:
                    item_row.pack_forget()
                for index, item_row in row["granule_rows"]:
                    if not query or category_match or index in hits:
                        item_row.pack(fill="x", before=row["add_row"])
                row["panel"].pack(fill="x")

        self.search_results_var.set(
            f"{visible} of {total} found" if query else ""
        )
        if self._no_search_results is not None:
            self._no_search_results.pack_forget()
            if visible == 0 and query:
                self._no_search_results.pack(fill="x", pady=(18, 10))
        self.inner.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        if query:
            self.canvas.yview_moveto(0.0)
        elif self.canvas.winfo_exists():
            self.canvas.yview_moveto(had_scroll)

    def _on_table_wheel(self, event):
        """Scroll the category table from any row or control (Windows/macOS/Linux)."""
        try:
            if getattr(event, "num", None) == 4:
                steps = -1
            elif getattr(event, "num", None) == 5:
                steps = 1
            else:
                delta = getattr(event, "delta", 0)
                if not delta:
                    return "break"
                steps = -int(delta / 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
            if self.canvas.winfo_exists():
                self.canvas.yview_scroll(steps, "units")
        except tk.TclError:
            pass
        return "break"

    def _bind_table_wheel(self, widget):
        """Bind without bind_all so other PyFCS windows retain their own scroll."""
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            widget.bind(sequence, self._on_table_wheel, add="+")
        for child in widget.winfo_children():
            self._bind_table_wheel(child)

    def _occupied(self, exclude_category=None, exclude_index=None):
        return [
            (category, g["label"], g["lab"])
            for category, data in self.categories.items()
            for index, g in enumerate(data["granules"])
            if not (category == exclude_category and index == exclude_index)
        ]

    def _insert_category(self, name, granules):
        if name in self.categories:
            self._warning(f"Category '{name}' already exists.")
            return
        candidate = copy.deepcopy(self.categories)
        candidate[name] = {
            "source": None,
            "granules": [{"label": item["label"], "lab": _triple(item["lab"]),
                           "original_label": None} for item in granules],
        }
        error = validate_draft(candidate)
        if error:
            self._warning(error)
            return
        self.categories = candidate
        self.expanded.add(name)
        if self.search_var.get().strip():
            self.search_var.set("")
        self.refresh()

    def add_category(self):
        host = _CategoryHost(self)
        UtilsTools.CustomCategoryDialog(host)

    def _next_granule(self, category):
        used = {g["label"] for data in self.categories.values() for g in data["granules"]}
        num = len(self.categories[category]["granules"]) + 1
        while True:
            suffix = f"-g{num}"
            label = f"{category[:UtilsTools.MAX_COLOR_NAME_CHARS-len(suffix)]}{suffix}"
            if label not in used:
                return label
            num += 1

    def _picker(self, category, index=None):
        previous = (copy.deepcopy(self.categories[category]["granules"][index])
                    if index is not None else None)
        def submit(name, lab, _rgb_data, _hex_data, _dialog, status):
            try:
                label, xyz, error = UtilsTools.check_granule_site(
                    name, lab, self._occupied(category, index),
                    max_name_length=UtilsTools.MAX_COLOR_NAME_CHARS,
                )
                if error:
                    status.set(error)
                    return False
                new_list = copy.deepcopy(self.categories)
                sites = new_list[category]["granules"]
                item = {"label": label, "lab": xyz,
                        "original_label": previous["original_label"] if previous else None}
                if index is None:
                    sites.append(item)
                else:
                    sites[index] = item
                problem = validate_draft(new_list)
                if problem:
                    status.set(problem)
                    return False
                self.categories = new_list
                self.expanded.add(category)
                self.refresh()
                return True
            except (TypeError, ValueError, KeyError, tk.TclError) as exc:
                status.set(str(exc))
                return False

        name = previous["label"] if previous else self._next_granule(category)
        self.app._open_square_color_picker(
            parent=self.win,
            title=(f"Edit Granule — {category}" if previous else f"Add Granule — {category}"),
            granule_name=name,
            initial_lab=previous["lab"] if previous else None,
            submit_text="Save changes" if previous else "Add granule",
            on_granule_submit=submit,
        )

    def _rename_category(self, name, variable):
        if name in self._renaming:
            return
        self._renaming.add(name)
        try:
            new = variable.get().strip()
            if new == name:
                return
            if not new or len(new) > UtilsTools.MAX_CATEGORY_NAME_CHARS:
                variable.set(name)
                self._warning(
                    f"Category name must contain 1 to {UtilsTools.MAX_CATEGORY_NAME_CHARS} characters."
                )
                return
            if new in self.categories:
                variable.set(name)
                self._warning(f"Category '{new}' already exists.")
                return
            updated = OrderedDict()
            for key, data in self.categories.items():
                current = copy.deepcopy(data)
                if key == name:
                    # Keep manually assigned granule IDs unchanged.
                    for granule in current["granules"]:
                        label = granule["label"]
                        if label == name:
                            granule["label"] = new
                        elif label.startswith(name + "-g") and label[len(name)+2:].isdigit():
                            suffix = label[len(name):]
                            # Keep generated granule IDs within the 24-char limit.
                            keep = UtilsTools.MAX_COLOR_NAME_CHARS - len(suffix)
                            granule["label"] = new[:max(0, keep)] + suffix
                    updated[new] = current
                else:
                    updated[key] = current
            problem = validate_draft(updated)
            if problem:
                variable.set(name)
                self._warning(problem)
                return
            self.categories = updated
            if name in self.expanded:
                self.expanded.remove(name)
                self.expanded.add(new)
            self.refresh()
        finally:
            self._renaming.discard(name)

    def _remove_category(self, category):
        if len(self.categories) <= 2:
            self._warning("At least two color categories must remain.")
            return
        if not messagebox.askyesno("Remove Category",
                                   f"Remove '{category}' from the modified space?",
                                   parent=self.win):
            return
        del self.categories[category]
        self.expanded.discard(category)
        self.refresh()

    def _remove_granule(self, category, index):
        items = self.categories[category]["granules"]
        if len(items) <= 1:
            self._warning("Every category requires at least one granule.")
            return
        if not messagebox.askyesno("Remove Granule",
                                   f"Remove '{items[index]['label']}'?",
                                   parent=self.win):
            return
        del items[index]
        self.refresh()

    
    def _open_move_menu(self, category, index, widget):
        """Choose a destination category without leaving the FCS editor."""
        items = self.categories.get(category, {}).get("granules", [])
        if not 0 <= index < len(items):
            return

        destinations = [
            name for name in self.categories if name != category
        ]

        if not destinations:
            self._warning(
                "Create another category before moving a granule.",
                "Cannot Move Granule"
            )
            return

        old_menu = getattr(self, "_move_menu", None)
        if old_menu is not None:
            try:
                old_menu.destroy()
            except tk.TclError:
                pass

        menu = tk.Menu(self.win, tearoff=False)
        self._move_menu = menu

        for destination in destinations:
            menu.add_command(
                label=destination,
                command=lambda target=destination:
                    self._move_granule(category, index, target)
            )

        try:
            menu.tk_popup(
                widget.winfo_rootx(),
                widget.winfo_rooty() + widget.winfo_height()
            )
        except tk.TclError:
            pass
        finally:
            try:
                menu.grab_release()
            except tk.TclError:
                pass

    def _move_granule(self, source, index, destination):
        """Move a granule transactionally inside the FCS draft."""
        if (
            source == destination
            or source not in self.categories
            or destination not in self.categories
        ):
            return False

        source_items = self.categories[source]["granules"]

        if not 0 <= index < len(source_items):
            return False

        item = source_items[index]
        is_last = len(source_items) == 1

        if is_last and len(self.categories) <= 2:
            self._warning(
                "At least two color categories must remain. "
                "Add a category before moving this last granule.",
                "Cannot Move Granule"
            )
            return False

        # Prepare the modification without changing the active draft.
        candidate = copy.deepcopy(self.categories)

        moving = candidate[source]["granules"].pop(index)
        candidate[destination]["granules"].append(moving)

        if is_last:
            del candidate[source]

        # Validate the complete result before committing.
        problem = validate_draft(candidate)

        if problem:
            self._warning(problem, "Cannot Move Granule")
            return False

        if is_last:
            confirmed = messagebox.askyesno(
                "Move Last Granule",
                f"Moving '{item['label']}' to '{destination}' "
                f"will remove the empty category '{source}'.\n\n"
                "Continue?",
                parent=self.win,
                icon="warning"
            )

            if not confirmed:
                return False

        self.categories = candidate

        if is_last:
            self.expanded.discard(source)
        else:
            self.expanded.add(source)

        self.expanded.add(destination)

        self.status_var.set(
            f"Granule '{item['label']}' moved from "
            f"'{source}' to '{destination}'. "
            "Apply Changes to save."
        )

        # Make the destination visible after moving.
        if self.search_var.get().strip():
            self.search_var.set("")

        self.refresh()
        return True


    def refresh(self):
        """Redraw the editor rows, preserving scroll and open categories."""
        oldpos = self.canvas.yview()[0]
        for child in self.inner.winfo_children():
            child.destroy()
        self._editor_rows = OrderedDict()
        self._no_search_results = None
        total = sum(len(data["granules"]) for data in self.categories.values())
        self.count.set(f"{len(self.categories)} categories  ·  {total} granules")

        header = tk.Frame(self.inner, bg="#f1f3f6", height=34)
        header.pack(fill="x")
        header.grid_propagate(False)
        header.grid_rowconfigure(0, weight=1)
        _editor_columns(header)
        for i, label in enumerate(("COLOR CATEGORY", "RGB", "HEX", "CIELAB", "ACTIONS")):
            _cell(header, i, label, background="#f1f3f6", color=MUTED,
                  font=("Segoe UI", 8, "bold"), justify="w" if i == 0 else "center")

        for index, (category, data) in enumerate(self.categories.items()):
            bg = WHITE if index % 2 == 0 else PANEL
            wrap = tk.Frame(self.inner, bg=WHITE)
            wrap.pack(fill="x", pady=2)
            row = tk.Frame(wrap, bg=bg, height=45)
            row.pack(fill="x")
            row.grid_propagate(False)
            row.grid_rowconfigure(0, weight=1)
            _editor_columns(row)
            first = data["granules"][0]["lab"]

            cell = tk.Frame(row, bg=bg)
            cell.grid(row=0, column=0, sticky="nsew", padx=(7, 6))
            toggle = tk.Button(
                cell, text="▾" if category in self.expanded else "▸",
                bg=bg, fg=PURPLE, font=BOLD, relief="flat", bd=0,
                width=2, cursor="hand2")
            toggle.pack(side="left")
            _swatch(cell, first, size=25, bg=bg).pack(side="left", padx=(4, 8))
            var = tk.StringVar(value=category)
            inp = tk.Entry(cell, textvariable=var, font=BOLD,
                           relief="solid", bd=1, width=17)
            inp.pack(side="left", fill="x", expand=True)
            inp.bind("<Return>", lambda _e, name=category, v=var:
                     self._rename_category(name, v))
            inp.bind("<FocusOut>", lambda _e, name=category, v=var:
                     self._rename_category(name, v))

            values = (
                ", ".join(map(str, _rgb(first))),
                _hex(first),
                ", ".join(f"{x:.2f}" for x in first),
            )
            summary = [
                _cell(row, j + 1, "" if category in self.expanded else value,
                      background=bg, font=FONT)
                for j, value in enumerate(values)
            ]

            
            actions = tk.Frame(row, bg=bg)
            actions.grid(row=0, column=4, sticky="nsew")
            actions.grid_columnconfigure(0, weight=1)
            actions.grid_rowconfigure(0, weight=1)

            centered_actions = tk.Frame(actions, bg=bg)
            centered_actions.grid(row=0, column=0)

            n = len(data["granules"])

            count_button = tk.Button(
                centered_actions,
                text=f"{n} granule{'s' if n != 1 else ''}",
                command=lambda name=category:
                    self._toggle_editor_category(name),
                bg=SOFT_PURPLE if n > 1 else bg,
                fg=PURPLE if n > 1 else MUTED,
                activebackground=SOFT_PURPLE if n > 1 else bg,
                activeforeground=PURPLE if n > 1 else MUTED,
                font=SMALL,
                relief="flat",
                bd=0,
                highlightthickness=0,
                takefocus=0,
                cursor="hand2",
                padx=4,
                pady=2
            )
            count_button.pack(side="left", padx=(0, 5))

            tk.Button(
                centered_actions,
                text="Remove",
                command=lambda name=category:
                    self._remove_category(name),
                fg="#9b3a3a",
                bg=bg,
                relief="flat",
                bd=0,
                highlightthickness=0,
                takefocus=0,
                font=SMALL,
                cursor="hand2",
                padx=2
            ).pack(side="left")


            panel = tk.Frame(wrap, bg=WHITE)

            toggle.configure(command=lambda name=category:
                             self._toggle_editor_category(name))
            granule_rows = []

            for gi, granule in enumerate(data["granules"]):
                granule_bg = "#fafbfc"
                grow = tk.Frame(panel, bg=granule_bg, height=38)
                grow.pack(fill="x")
                granule_rows.append((gi, grow))
                grow.grid_propagate(False)
                grow.grid_rowconfigure(0, weight=1)
                _editor_columns(grow)
                gcell = tk.Frame(grow, bg=granule_bg)
                gcell.grid(row=0, column=0, sticky="nsew", padx=(50, 5))
                _swatch(gcell, granule["lab"], size=21, bg=granule_bg).pack(
                    side="left", padx=(0, 8))
                tk.Label(gcell, text=granule["label"], bg=granule_bg, fg=TEXT,
                         font=FONT, anchor="w").pack(side="left")
                lab = granule["lab"]
                for j, value in enumerate((
                    ", ".join(map(str, _rgb(lab))),
                    _hex(lab),
                    ", ".join(f"{x:.2f}" for x in lab),
                )):
                    _cell(grow, j + 1, value, background=granule_bg, font=FONT)
                
                child_actions = tk.Frame(grow, bg=granule_bg)
                child_actions.grid(
                    row=0,
                    column=4,
                    sticky="nsew"
                )

                child_actions.grid_columnconfigure(0, weight=1)
                child_actions.grid_rowconfigure(0, weight=1)

                child_controls = tk.Frame(
                    child_actions,
                    bg=granule_bg
                )
                child_controls.grid(row=0, column=0)

                # Edit granule
                tk.Button(
                    child_controls,
                    text="Edit",
                    command=lambda name=category, i=gi:
                        self._picker(name, i),
                    fg=PURPLE,
                    bg=granule_bg,
                    font=FONT,
                    relief="flat",
                    bd=0,
                    highlightthickness=0,
                    cursor="hand2"
                ).pack(side="left", padx=(0, 3))

                # Move granule to another category
                move_btn = tk.Button(
                    child_controls,
                    text="Move",
                    fg=PURPLE,
                    bg=granule_bg,
                    font=FONT,
                    relief="flat",
                    bd=0,
                    highlightthickness=0,
                    cursor="hand2"
                )

                move_btn.configure(
                    command=lambda name=category, i=gi, w=move_btn:
                        self._open_move_menu(name, i, w)
                )
                move_btn.pack(side="left", padx=(0, 3))

                # Remove granule
                tk.Button(
                    child_controls,
                    text="×",
                    command=lambda name=category, i=gi:
                        self._remove_granule(name, i),
                    fg="#9b3a3a",
                    bg=granule_bg,
                    font=BOLD,
                    relief="flat",
                    bd=0,
                    highlightthickness=0,
                    cursor="hand2"
                ).pack(side="left")


            addrow = tk.Frame(panel, bg=WHITE)
            addrow.pack(fill="x", padx=(54, 0), pady=(3, 5))
            tk.Button(
                addrow, text="+ Add granule",
                command=lambda name=category: self._picker(name),
                fg=PURPLE, bg=WHITE, relief="flat", font=BOLD,
                cursor="hand2").pack(side="left")
            self._editor_rows[category] = {
                "wrapper": wrap, "panel": panel, "toggle": toggle,
                "summary": summary, "values": values,
                "granule_rows": granule_rows, "add_row": addrow,
            }
            if category in self.expanded:
                panel.pack(fill="x")

        self._no_search_results = tk.Label(
            self.inner, text="No categories or granules match the search.",
            font=FONT, bg=WHITE, fg=MUTED, pady=12,
        )
        # Canvas widgets do not inherit mouse-wheel events from inner labels.
        self._bind_table_wheel(self.inner)
        self._apply_search_filter()
        self.canvas.after_idle(
            lambda: self.canvas.yview_moveto(oldpos)
            if self.canvas.winfo_exists() else None)

    def _snapshot(self):
        """Build a complete, validated application save request, without mutation."""
        error = validate_draft(self.categories)
        if error:
            raise ValueError(error)
        name = UtilsTools.validate_color_space_name(self.file_var.get())
        target = self.model_var.get().strip().upper()
        if target not in GEOMETRIC_MODELS:
            raise ValueError(f"Unsupported geometric model '{target}'.")
        current_model = self.space.color_space
        stored = OrderedDict()
        pending = {}
        for category, data in self.categories.items():
            first = data["granules"][0]["lab"]
            original = data.get("source")
            row = {"Color": list(first), "positive_prototype": np.asarray(first, dtype=float),
                   "fcs_original_label": original if original else category}
            stored[category] = row
            key = original if original else category
            pending[key] = [
                {"label": g["label"], "prototype_lab": list(g["lab"]),
                 "original_label": g.get("original_label")}
                for g in data["granules"]
            ]
        return name, target, stored, pending

    def apply(self):
        if self._saving:
            return
        if id(self.app.fuzzy_color_space) != self.source_id or not self.app.COLOR_SPACE:
            self._warning("The loaded FCS has changed. Reopen Modify FCS to edit the current model.")
            return
        if self.app._has_any_active_job():
            self._warning("Finish or cancel the active process before applying changes.", "Process Running")
            return
        try:
            name, target, rows, pending = self._snapshot()
            # Legacy atomic remains atomic when each category still has one
            # same-named granule; granular models retain granular semantics.
            granular = isinstance(self.space, GranularFuzzyColorSpace) or any(
                len(data["granules"]) != 1 or data["granules"][0]["label"] != category
                for category, data in self.categories.items()
            )
            color_dict = {category: np.asarray(row["positive_prototype"], dtype=float)
                          for category, row in rows.items()}
            if target != self.space.color_space:
                # Build directly in the destination model. In particular,
                # RGB -> LAB must permit an edited LAB color outside sRGB:
                # rebuilding it through the old RGB model would clip it.
                options = {
                    "_target_model_for_modify": target,
                    "_modified_draft": copy.deepcopy(self.categories),
                    "_original_model": self.space,
                }
            elif granular:
                previous = getattr(self.app, "_pending_granules", {})
                try:
                    self.app._pending_granules = pending
                    options = self.app._granular_save_options(rows)
                finally:
                    self.app._pending_granules = previous
            else:
                options = self.app._options_from_loaded_space(self.space, rows)
            options["_target_model_for_modify"] = target
            options["_from_modify_fcs"] = True
            if target != self.space.color_space and not messagebox.askyesno(
                "Rebuild Geometric Model",
                f"Change the geometric model from {self.space.color_space} to {target}?\n\n"
                "PyFCS will reconstruct all Core, Voronoi and Support volumes. "
                "Membership values may change, and some colors may not be "
                "convertible without gamut clipping. The current FCS will "
                "remain unchanged if reconstruction fails.",
                parent=self.win, icon="warning",
            ):
                return
        except (ValueError, TypeError, KeyError, RuntimeError) as exc:
            self._warning(str(exc))
            return
        self._saving = True
        self.apply_btn.configure(state="disabled")
        # The save worker only reads the deep-copy snapshot. The old model is
        # untouched unless the writer succeeds and commits on Tk's thread.
        try:
            started = self.app.save_json(name, rows, color_dict=color_dict,
                                         apply_after_save=True, options=options)
        except Exception as exc:
            started = False
            self.status_var.set(str(exc))
        if not started:
            self.on_save_failure("The modified FCS was not saved.")
        else:
            self.status_var.set("Building geometry and saving JSON...")

    def on_save_failure(self, message):
        self._saving = False
        if self.win.winfo_exists():
            self.apply_btn.configure(state="normal")
            self.status_var.set(message)
            self.win.deiconify()
            self.win.lift()

    def on_save_success(self):
        self._saving = False
        self.close()


def build_model_from_draft(name, draft, source_space, target_model):
    """Build the edited FCS *once* in the requested destination model.

    Positives/real negatives follow their stable original site references;
    negatives not attached to an existing site are converted from the source
    model. Auxiliary sampling is regenerated in the destination domain.
    This also permits valid out-of-sRGB LAB sites when moving RGB -> LAB.
    """
    from Source.colorspace.ReferenceDomain import ReferenceDomain
    from Source.geometry.Voronoi import Voronoi

    target = str(target_model).upper()
    if target not in GEOMETRIC_MODELS:
        raise ValueError(f"Unsupported geometric model '{target}'.")
    error = validate_draft(draft)
    if error:
        raise ValueError(error)
    originals = (
        {p.label: p for cat in source_space.categories for p in cat.prototypes}
        if isinstance(source_space, GranularFuzzyColorSpace)
        else {p.label: p for p in source_space.prototypes}
    )
    native = OrderedDict()
    by_old_site = {}
    for category, item in draft.items():
        sites = OrderedDict()
        for g in item["granules"]:
            label = g["label"]
            lab = np.asarray(g["lab"], dtype=float).reshape(3)
            old_key = g.get("original_label")
            if target == "LAB":
                xyz = lab.copy()
            elif target == "RGB":
                if (
                    source_space.color_space == "RGB" and old_key in originals
                    and np.linalg.norm(
                        np.asarray(source_space.lab_from_model(originals[old_key].positive)) - lab
                    ) <= 1e-5
                ):
                    xyz = np.asarray(originals[old_key].positive, dtype=float).copy()
                else:
                    xyz = lab_to_rgb_model_checked(lab.reshape(1, 3))[0]
            else:
                # Extend the model registry and its conversion implementation
                # together. Never silently interpret a future model as RGB.
                raise ValueError(f"Model '{target}' has no coordinate converter yet.")
            sites[label] = xyz
            if old_key in originals:
                by_old_site[old_key] = (category, xyz)
        native[category] = sites

    negatives = {}
    auxiliary = np.asarray(getattr(source_space, "auxiliary_negatives", []),
                           dtype=float).reshape(-1, 3)
    if not source_space.disjoint:
        for category, item in draft.items():
            original_category = item.get("source")
            choices = []
            if original_category is not None:
                for coordinate in source_space.negative_prototypes.get(original_category, []):
                    source_xyz = np.asarray(coordinate, dtype=float).reshape(3)
                    if len(auxiliary) and np.any(
                        np.linalg.norm(auxiliary - source_xyz, axis=1)
                        <= Voronoi.DEFAULT_MERGE_EPS
                    ):
                        continue
                    matched = next((
                        key for key, p in originals.items()
                        if np.linalg.norm(np.asarray(p.positive) - source_xyz)
                        <= Voronoi.DEFAULT_MERGE_EPS
                    ), None)
                    if matched is not None:
                        if matched not in by_old_site:
                            raise ValueError(
                                f"'{category}' refers to a deleted negative granule "
                                f"'{matched}'. Review the negative relationships."
                            )
                        matched_category, converted = by_old_site[matched]
                        if matched_category == category:
                            raise ValueError(
                                f"'{category}' cannot use its own granule as a negative."
                            )
                        choices.append(converted)
                    else:
                        lab = source_space.lab_from_model(source_xyz)
                        if target == "LAB":
                            choices.append(np.asarray(lab, dtype=float))
                        elif target == "RGB":
                            choices.append(lab_to_rgb_model_checked(
                                np.asarray(lab, dtype=float).reshape(1, 3))[0])
                        else:
                            raise ValueError(f"Model '{target}' has no negative-site converter yet.")
            negatives[category] = choices

    shared = dict(
        color_space=target,
        reference_domain=ReferenceDomain.for_color_space(target),
        lambda1=source_space.lambda1,
        lambda2=source_space.lambda2,
        disjoint=source_space.disjoint,
        covering=source_space.covering,
        samples=source_space.samples or 27,
        negative_prototypes=negatives if not source_space.disjoint else None,
        description=getattr(source_space, "description", None),
    )
    keep_atomic = (
        not isinstance(source_space, GranularFuzzyColorSpace)
        and all(len(sites) == 1 and next(iter(sites)) == category
                for category, sites in native.items())
    )
    if keep_atomic:
        atomic = {category: next(iter(sites.values()))
                  for category, sites in native.items()}
        return FuzzyColorSpaceBuilder.build(name, atomic, **shared)
    return FuzzyColorSpaceBuilder.build_granular(
        name, native, **shared,
        tconorm=getattr(source_space, "tconorm", "bounded_sum"),
    )


def build_atomic_native(name, color_dict, options):
    """Prepare an atomic model without writing an intermediate JSON file."""
    mode = options.get("color_space", "LAB")
    native = options.get("model_points") or {}
    points = {label: np.asarray(native[label], dtype=float)
              if label in native else
              (np.asarray(lab, dtype=float) if mode == "LAB" else
               lab_to_rgb_model_checked(np.asarray(lab, dtype=float).reshape(1, 3))[0])
              for label, lab in color_dict.items()}
    negatives = {}
    for label, values in (options.get("negative_prototypes") or {}).items():
        negatives[label] = []
        for value in values:
            if isinstance(value, str):
                negatives[label].append(points[value])
            else:
                lab = np.asarray(value, dtype=float).reshape(3)
                negatives[label].append(lab if mode == "LAB" else
                                         lab_to_rgb_model_checked(lab.reshape(1, 3))[0])
    return FuzzyColorSpaceBuilder.build(
        name, points, color_space=mode, reference_domain=options.get("reference_domain"),
        lambda1=options.get("lambda1", 0.5), lambda2=options.get("lambda2", 1.5),
        disjoint=options.get("disjoint", True), covering=options.get("covering", True),
        samples=options.get("samples", 27), negative_prototypes=negatives,
        description=options.get("description"),
    )


def prepare_modified_model(name, color_dict, options, target_model, prebuilt=None,
                           granular_categories=None):
    """Pure model construction and optional conversion for the save worker."""
    if prebuilt is not None:
        prepared = prebuilt
    elif granular_categories is not None:
        prepared = FuzzyColorSpaceBuilder.build_granular(
            name, granular_categories, color_space=options.get("color_space", "LAB"),
            reference_domain=options.get("reference_domain"),
            lambda1=options.get("lambda1", 0.5),
            lambda2=options.get("lambda2", 1.5),
            disjoint=options.get("disjoint", True),
            covering=options.get("covering", True),
            samples=options.get("samples", 27),
            negative_prototypes=options.get("negative_prototypes"),
            auxiliary_negatives=options.get("auxiliary_negatives"),
            tconorm=options.get("tconorm", "bounded_sum"),
        )
    else:
        prepared = build_atomic_native(name, color_dict, options)
    if str(prepared.color_space).upper() != str(target_model).upper():
        prepared = rebuild_in_color_space(prepared, target_model)
    return prepared

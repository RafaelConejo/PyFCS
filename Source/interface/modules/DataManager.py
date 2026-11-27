
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
from types import SimpleNamespace
from Source.fuzzy.ColorHierarchy import ColorHierarchy

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

# UI-only limits for unfolding shared DAG paths (never membership limits).
MAX_EXTRA_TREE_ROWS = 2000
MAX_TREE_DEPTH = 64


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
        _, error = UtilsTools.check_label_name(category, kind="Category")
        if error:
            return error
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



def draft_graph(categories, hierarchy):
    base = [SimpleNamespace(label=label, prototypes=[SimpleNamespace(label=g["label"])
             for g in data["granules"]]) for label, data in categories.items()]
    return ColorHierarchy(base, hierarchy)


def prepare_parent_draft(categories, hierarchy, parent, reserved=(), *, child_name=None):
    """Promote a category only with an explicitly named child for its sites."""
    candidate, nodes = copy.deepcopy(categories), copy.deepcopy(hierarchy)
    if parent in nodes:
        return candidate, nodes, None
    if parent not in candidate:
        raise ValueError(f"Unknown parent category '{parent}'.")
    child, name_error = UtilsTools.check_label_name(child_name, max_length=UtilsTools.MAX_CATEGORY_NAME_CHARS, kind="Subcategory")
    occupied = set(candidate) | set(nodes) | set(reserved)
    if name_error or child in occupied:
        raise ValueError(f"Choose a unique name for the original granules (1 to {UtilsTools.MAX_CATEGORY_NAME_CHARS} characters).")
    candidate = OrderedDict((child if name == parent else name, data)
                            for name, data in candidate.items())
    nodes[parent] = [{"category": child}]
    return candidate, nodes, child


def prune_empty_groups(nodes):
    """Remove empty semantic containers and their incoming edges."""
    while True:
        empty = {name for name, refs in nodes.items() if not refs}
        if not empty:
            return
        for name in empty:
            del nodes[name]
        for name, refs in nodes.items():
            nodes[name] = [ref for ref in refs if ref.get("category") not in empty]


def group_tree_draft(categories, hierarchy, name, refs, parent=None, *, remaining_name=None, validate_sites=True):
    """Move siblings into one group, never create another path to a component.

    A subgroup of a geometric category moves its selected physical sites into
    a new owning child. An explicitly named sibling keeps remaining sites. Existing
    imported DAGs are readable; their shared nodes are not silently migrated.
    """
    candidate, nodes = copy.deepcopy(categories), copy.deepcopy(hierarchy)
    graph = draft_graph(candidate, nodes)
    if UtilsTools.check_label_name(name, kind="Group")[1] or name in candidate or name in nodes or not refs:
        raise ValueError("Choose a unique group name and at least one component.")
    if parent in candidate:
        items = candidate[parent]["granules"]
        chosen = {ref.get("granule") for ref in refs}
        if not chosen or None in chosen or not chosen <= {g["label"] for g in items}:
            raise ValueError("Select only granules belonging to this category.")
        if any(ref.get("granule") in chosen for values in nodes.values() for ref in values):
            raise ValueError("A selected granule is shared in this imported model. Remove its extra reference first.")
        moving = [g for g in items if g["label"] in chosen]
        remaining = [g for g in items if g["label"] not in chosen]
        provenance = candidate[parent].get("source")
        if remaining:
            candidate, nodes, base = prepare_parent_draft(candidate, nodes, parent, reserved=(name,), child_name=remaining_name)
            candidate[base]["granules"] = remaining
            nodes[parent].append({"category": name})
        else:
            del candidate[parent]
            nodes[parent] = [{"category": name}]
        candidate[name] = {"source": provenance, "granules": moving}
    else:
        eligible = list(graph.children(parent)) if parent is not None else [("category", n) for n in graph.roots()]
        chosen = [tuple(ref.items())[0] for ref in refs]
        if any(pair not in eligible or pair[0] != "category" for pair in chosen):
            raise ValueError("Select categories at the same level.")
        if any(sum({"category": target} in children for children in nodes.values()) > (1 if parent else 0)
               for _, target in chosen):
            raise ValueError("A selected category is shared in this imported model. Remove its extra reference first.")
        nodes[name] = [{k: v} for k, v in chosen]
        if parent is not None:
            old = nodes[parent]
            first = next(i for i, ref in enumerate(old) if tuple(ref.items())[0] in chosen)
            nodes[parent] = [ref for ref in old if tuple(ref.items())[0] not in chosen]
            nodes[parent].insert(first, {"category": name})
    if validate_sites:
        error = validate_draft(candidate)
        if error:
            raise ValueError(error)
    draft_graph(candidate, nodes)
    return candidate, nodes


def remap_references(hierarchy, category_names=None, granule_names=None):
    """Rename IDs transactionally, without mutating the original graph."""
    category_names, granule_names = category_names or {}, granule_names or {}
    return {category_names.get(name, name): [
        {kind: (category_names if kind == "category" else granule_names).get(target, target)}
        for ref in refs for kind, target in ref.items()]
        for name, refs in hierarchy.items()}


def hierarchy_rows(categories, hierarchy, expanded, query="", search_collapsed=(), limit_state=None):
    """Visible path occurrences; shared nodes retain their separate paths."""
    graph = draft_graph(categories, hierarchy)
    sites = {g["label"]: g for data in categories.values() for g in data["granules"]}
    terms = query.casefold().split()
    def matches(text):
        return all(term in text.casefold() for term in terms)
    # Compute matching descendant categories once, including a granule search.
    hits = {}
    def subtree_hit(label):
        # Postorder without Python recursion: a deep but valid hierarchy
        # should not fail just because a user enters a search query.
        pending = [(label, False)]
        while pending:
            name, visited = pending.pop()
            if name in hits:
                continue
            children = graph.children(name)
            if visited:
                hits[name] = matches(name) or any(
                    matches(name + " " + child) if kind == "granule" else hits[child]
                    for kind, child in children)
            else:
                pending.append((name, True))
                pending.extend((child, False) for kind, child in children
                               if kind == "category" and child not in hits)
        return hits[label]
    roots = graph.roots()
    stack = [(label, (), False) for label in reversed(roots)]
    budget = MAX_EXTRA_TREE_ROWS
    while stack:
        label, ancestors, inherited = stack.pop()
        full = inherited or bool(terms and matches(label))
        if terms and not full and not subtree_hit(label):
            continue
        path = ancestors + (label,)
        if ancestors and (budget <= 0 or len(path) > MAX_TREE_DEPTH):
            if limit_state is not None:
                limit_state["limited"] = True
            continue
        if ancestors:
            budget -= 1
        refs = graph.children(label)
        granules = [sites[target] for kind, target in refs if kind == "granule"]
        if terms and not full:
            granules = [g for g in granules if matches(label + " " + g["label"])]
        opened = (label in expanded or bool(terms)) and label not in search_collapsed
        yield path, label, graph, sites, granules, opened
        if opened:
            stack.extend((child, path, full) for kind, child in reversed(refs)
                         if kind == "category")


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
        (230, 5),   # Editable category name and swatch
        (105, 2),   # RGB
        (80, 1),    # HEX
        (145, 3),   # CIELAB
        (260, 2),   # Explicit category actions
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

    previous_fit = getattr(app, "_data_fit_id", None)
    if previous_fit is not None:
        try:
            canvas.after_cancel(previous_fit)
        except tk.TclError:
            pass
        app._data_fit_id = None
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

    # The model snapshot is fixed until render_data is explicitly called after
    # loading/editing a space. Expanding a branch must not rebuild this snapshot.
    hierarchy = getattr(space, "hierarchy", {})
    graph = draft_graph(groups, hierarchy) if hierarchy else None
    sites = {g["label"]: g for data in groups.values() for g in data["granules"]}
    roots = tuple(graph.roots()) if graph else tuple(groups)
    root_positions = {name: i for i, name in enumerate(roots)}
    row_cache = {}
    visible_paths = []

    def child_categories(name):
        return tuple(target for kind, target in graph.children(name)
                     if kind == "category") if graph else ()

    def is_last_category(path):
        siblings = child_categories(path[-2]) if len(path) > 1 else roots
        return bool(siblings and path[-1] == siblings[-1])

    tree_limit = {"limited": False}
    tree_notice = tk.Label(content, text="Branch limit reached. Collapse groups to explore other paths.",
                           bg=WHITE, fg=MUTED, font=SMALL, wraplength=320)

    def visible_rows():
        stack = [(name,) for name in reversed(roots)]
        budget = MAX_EXTRA_TREE_ROWS
        while stack:
            path = stack.pop()
            if len(path) > 1:
                if budget <= 0 or len(path) > MAX_TREE_DEPTH:
                    tree_limit["limited"] = True
                    continue
                budget -= 1
            yield path
            if path[-1] in expanded:
                stack.extend(path + (child,) for child in reversed(child_categories(path[-1])))

    def guide(parent, **position):
        line = tk.Frame(parent, bg="#c9bfda", bd=0, highlightthickness=0)
        line.place(**position)
        line.lift()

    # Use actual fixed-height grid rows so swatches have breathing room.
    row_height = 36
    row_mid = row_height // 2
    swatch_size = 25
    def create_row(path):
        category = path[-1]
        data = ( {"granules": [sites[target] for kind, target in graph.children(category)
                                if kind == "granule"]} if graph else groups[category])
        n = len(graph.unique_granules(category)) if graph else len(data["granules"])
        bg = WHITE

        wrapper = tk.Frame(content, bg=WHITE)


        row = tk.Frame(wrapper, bg=bg, height=row_height)
        row.pack(fill="x")
        row.grid_propagate(False)
        _table_columns(row)

        first = (sites[graph.unique_granules(category)[0]]["lab"] if graph else data["granules"][0]["lab"])

        color_cell = tk.Frame(row, bg=bg)
        color_cell.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(10 + 14 * (len(path)-1), 4),
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
            size=swatch_size,
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

        # A composite category does not have a single mathematical prototype.
        if n > 1 or category in hierarchy:
            component_values = ("", "", "")
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
            background=bg,
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
            (f"{n} unique descendant granules" if hierarchy and n > 1 else _info_text(first)),
        )

        panel = tk.Frame(wrapper, bg=WHITE)

        def toggle():
            if category in expanded:
                expanded.discard(category)
            else:
                expanded.add(category)
            sync_rows()
            return "break"

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


        def create_granules():
            # Granules
            for gi, granule in enumerate(data["granules"]):
                child = tk.Frame(
                    panel,
                    bg=WHITE,
                    height=row_height,
                )
                child.pack(fill="x")
                child.grid_propagate(False)
                _table_columns(child)

                firstcell = tk.Frame(
                    child,
                    bg=WHITE,
                )
                firstcell.grid(
                    row=0,
                    column=0,
                    sticky="nsew",
                    padx=(46 + 14 * (len(path)-1), 5),
                )


                _swatch(
                    firstcell,
                    granule["lab"],
                    size=swatch_size,
                    bg=WHITE,
                ).pack(
                    side="left",
                    padx=(8, 8),
                )

                tk.Label(
                    firstcell,
                    text=granule["label"],
                    bg=WHITE,
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
                        background=WHITE,
                        color=TEXT,
                        font=SMALL,
                        padx=3,
                    )

                _cell(
                    child,
                    5,
                    "",
                    background=WHITE,
                )

                child_info = tk.Frame(
                    child,
                    bg=WHITE,
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
                    bg=WHITE,
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

                # Branch to each granule; continue the stem only if more
                # siblings follow (including semantic subcategories).
                x = 20 + 14 * (len(path)-1)
                guide(child, x=x, y=0, width=1,
                      **({"relheight": 1} if gi < len(data["granules"])-1 or child_categories(category) else {"height": row_mid+1}))
                guide(child, x=x, y=row_mid, width=30, height=1)

            _bind_table_children(panel)

        depth = len(path)-1
        for j in range(depth):
            x = 20 + 14*j
            if not is_last_category(path[:j+2]):
                guide(wrapper, x=x, y=0, width=1, relheight=1)
            elif j == depth-1:
                guide(row, x=x, y=0, width=1, height=row_mid+1)
            if j == depth-1:
                guide(row, x=x, y=row_mid, width=14, height=1)
        # Draw the parent's stem on its own row and panel. In a flat
        # space this stem must hide when the panel is collapsed.
        stem = tk.Frame(row, bg="#c9bfda", bd=0, highlightthickness=0)
        x = 20 + depth*14
        record = {"wrapper": wrapper, "panel": panel, "arrow": arrow,
                  "values": component_values, "labels": value_labels,
                  "stem": stem, "stem_x": x, "create_granules": create_granules,
                  "loaded": False, "opened": None}
        _bind_table_children(wrapper)
        return record

    def sync_rows():
        # Only newly visible paths allocate widgets; existing rows stay packed.
        tree_limit["limited"] = False
        tree_notice.pack_forget()
        paths = list(visible_rows())
        wanted = set(paths)
        packed = set(visible_paths)
        for path in visible_paths:
            if path not in wanted:
                row_cache[path]["wrapper"].pack_forget()
                packed.discard(path)
        # Avoid accumulating many hidden branches after successive expansions.
        if len(row_cache) >= len(roots) + MAX_EXTRA_TREE_ROWS:
            for path in tuple(row_cache):
                if path not in wanted:
                    row_cache.pop(path)["wrapper"].destroy()
        for path in paths:
            if path not in row_cache:
                row_cache[path] = create_row(path)
        next_wrapper = None
        for path in reversed(paths):
            record = row_cache[path]
            wrapper = record["wrapper"]
            if path not in packed:
                opts = {"before": next_wrapper} if next_wrapper is not None else {}
                wrapper.pack(fill="x", padx=5,
                             pady=(5 if len(path) == 1 and root_positions[path[0]] else 0, 0), **opts)
            next_wrapper = wrapper
            opened = path[-1] in expanded
            if record["opened"] == opened:
                continue
            record["opened"] = opened
            record["arrow"].configure(text="▾" if opened else "▸")
            for label, value in zip(record["labels"], record["values"]):
                label.configure(text="" if opened else value)
            if opened:
                if not record["loaded"]:
                    record["create_granules"]()
                    record["loaded"] = True
                record["panel"].pack(fill="x")
                record["stem"].place(x=record["stem_x"], y=row_mid+8,
                                     width=1, height=row_height-row_mid-8)
            else:
                record["panel"].pack_forget()
                record["stem"].place_forget()
        visible_paths[:] = paths
        if tree_limit["limited"]:
            tree_notice.pack(fill="x", pady=5)
        # Content Configure maintains the scroll region after geometry settles.

    _bind_table_children(content)
    sync_rows()

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

    # A new Data render can destroy this canvas before the idle event runs.
    # Cancel its callback during destruction to avoid Tcl's asynchronous
    # 'invalid command name ..._fit_width' noise/error on rapid FCS changes.
    fit_id = canvas.after_idle(_fit_width)
    app._data_fit_id = fit_id
    previous_bind = getattr(app, "_data_fit_destroy_binding", None)
    if previous_bind:
        try:
            canvas.unbind("<Destroy>", previous_bind)
        except tk.TclError:
            pass
    def _cancel_pending_fit(event):
        if event.widget is canvas:
            try:
                canvas.after_cancel(fit_id)
            except (tk.TclError, RuntimeError):
                pass
    app._data_fit_destroy_binding = canvas.bind("<Destroy>", _cancel_pending_fit, add="+")



class _CategoryHost:
    """Small palette-compatible adapter reusing the existing category dialog."""

    def __init__(self, editor):
        self.editor = editor
        self.initial_picker_mode = editor.model_var.get()
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

        # Reserve aggregate names in the standard category dialog too. They
        # own no sites, so they don't introduce spurious duplicate coordinates.
        for name in editor.hierarchy:
            self.colors[name] = {"granules": []}

    def _used_granule_labels(self):
        return {g["label"] for data in self.colors.values() for g in data["granules"]}

    def _matches_search(self, name):
        return True

    def _scroll_to_bottom(self):
        return None

    def commit_category(self, name, granules, original_child_name=None):
        return self.editor._insert_category(name, granules, getattr(self, "parent_category", None),
                                            original_child_name=original_child_name)

    def _append_color_rows(self, names):
        for name in names:
            value = self.colors[name]
            self.editor._insert_category(name, value["granules"], getattr(self, "parent_category", None),
                                         original_child_name=getattr(self, "original_child_name", None))


class ModifyFCSDialog:
    """Transactional, granular-aware editor; no writes to the active FCS."""

    def __init__(self, app):
        self.app = app
        self.space = app.fuzzy_color_space
        self.source_id = id(self.space)
        self.categories = extract_categories(self.space)
        self.hierarchy = copy.deepcopy(getattr(self.space, "hierarchy", {}))
        self.geometry_locked = bool(getattr(self.space, "geometry_only_import", False))
        self.expanded = set()
        self._renaming = set()
        self._saving = False
        self._editor_rows = OrderedDict()
        self._search_collapsed = set()
        self._search_after_id = None
        self._restore_scroll_id = None
        self.search_var = tk.StringVar(value="")
        self.search_results_var = tk.StringVar(value="")
        self.win = tk.Toplevel(app.root)
        self.win.withdraw()
        self.win.title("Edit Fuzzy Color Space")
        self.win.configure(bg=BG)
        self.win.minsize(900, 520)
        self.win.transient(app.root)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.app._modify_fcs_dialog = self
        window_width, window_height = 1120, 640
        try:
            app.root.update_idletasks()
            screen_w = self.win.winfo_screenwidth()
            screen_h = self.win.winfo_screenheight()
            window_width = min(window_width, max(900, screen_w - 45))
            window_height = min(window_height, max(520, screen_h - 80))
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
        self._negative_override = None
        self._negative_names_override = None
        self._negative_signature = None
        self._build()
        if self.geometry_locked:
            self.model_box.configure(state="disabled")
            self.status_var.set("Imported geometry: semantic edits only; prototypes are locked.")
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
        self._cancel_restore_scroll()
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
        tk.Label(header, text="Create colors, group existing components and edit granules",
                 font=SMALL, bg=WHITE, fg=MUTED, anchor="e").pack(
                     side="right", padx=(8, 17), pady=12)

        # Compact model selector aligned with the right edge.
        settings = tk.Frame(base, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        settings.pack(fill="x", pady=(0, 9))
        settings.grid_columnconfigure(0, weight=1, uniform="settings_side")
        settings.grid_columnconfigure(1, weight=0)
        settings.grid_columnconfigure(2, weight=1, uniform="settings_side")

        left = tk.Frame(settings, bg=WHITE)
        left.grid(row=0, column=0, sticky="w", padx=16, pady=12)
        tk.Label(left, text="Color space name", bg=WHITE, fg=TEXT, font=BOLD,
                 anchor="w").pack(side="left", padx=(0, 12))
        tk.Entry(left, textvariable=self.file_var, font=FONT, width=28,
                 relief="solid", bd=1).pack(side="left", fill="x", expand=True)

        right = tk.Frame(settings, bg=WHITE)
        right.grid(row=0, column=2, sticky="e", padx=16, pady=12)
        tk.Label(right, text="Geometric model", bg=WHITE, fg=TEXT, font=BOLD,
                 anchor="w").pack(side="left", padx=(0, 10))
        self.model_box = UtilsTools.styled_combobox(
            right, values=list(GEOMETRIC_MODELS), textvariable=self.model_var,
            state="readonly", width=7, font=FONT)
        self.model_box.pack(side="left")
        info = tk.Label(right, text="ⓘ", fg=PURPLE, bg=WHITE,
                        font=("Segoe UI", 10, "bold"), cursor="hand2")
        info.pack(side="left", padx=(9, 0))
        _attach_info_tooltip(
            self.app, info,
            "Changing the geometric model reconstructs Core, Voronoi and Support."
            "\nThe conversion will be confirmed when you apply changes.",
            prefer_left=True,
        )

        if not self.space.disjoint and not self.geometry_locked:
            tk.Button(settings,text="Manage Negative Prototypes...",command=self.manage_negatives,
                      fg=PURPLE,bg=WHITE,activebackground=WHITE,relief="flat",bd=0,
                      font=BOLD,cursor="hand2",padx=8).grid(row=0,column=1,padx=12,pady=8)
        category_card = tk.Frame(base, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        category_card.pack(fill="both", expand=True)
        toolbar = tk.Frame(category_card, bg=WHITE)
        toolbar.pack(fill="x", padx=13, pady=7)
        toolbar.grid_columnconfigure(0, weight=1, uniform="category_side")
        toolbar.grid_columnconfigure(1, weight=0)
        toolbar.grid_columnconfigure(2, weight=1, uniform="category_side")
        category_left = tk.Frame(toolbar, bg=WHITE)
        category_left.grid(row=0, column=0, sticky="w")
        category_right = tk.Frame(toolbar, bg=WHITE)
        category_right.grid(row=0, column=2, sticky="e")
        self.count = tk.StringVar(value="")
        tk.Label(category_left, text="Color categories", bg=WHITE, fg=TEXT,
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Label(category_left, textvariable=self.count, bg=WHITE, fg=MUTED,
                 font=SMALL).pack(side="left", padx=(12, 0))
        tk.Button(category_right, text="+ Add Color Category", command=self.add_category,
                  state="disabled" if self.geometry_locked else "normal",
                  bg=UtilsTools.UI_ADD_CATEGORY_BG, fg=UtilsTools.UI_ADD_CATEGORY_FG,
                  activebackground=UtilsTools.UI_ADD_CATEGORY_HOVER,
                  activeforeground=UtilsTools.UI_ADD_CATEGORY_FG,
                  font=BOLD, relief="flat", bd=0, highlightthickness=0,
                  cursor="hand2", padx=12, pady=6).pack(side="right")
        tk.Button(category_right, text="+ Group", command=self.add_group,
                  fg=PURPLE, bg=WHITE, activebackground=WHITE, activeforeground=PURPLE,
                  relief="flat", bd=0, highlightthickness=0, font=BOLD,
                  cursor="hand2", padx=8, pady=6).pack(side="right", padx=(0, 4))

        # Filtering affects visibility only: all categories and their granules
        # stay in the draft and are still included in Apply Changes.
        # Center the search above its own tree, independently of counts/actions.
        search_lane = tk.Frame(toolbar, bg=WHITE)
        search_lane.grid(row=0, column=1, padx=12, pady=8)
        search_bar = tk.Frame(search_lane, bg=WHITE)
        search_bar.pack(anchor="center")
        tk.Label(search_bar, text="Search", bg=WHITE, fg=TEXT,
                 font=BOLD).pack(side="left", padx=(0, 10))
        self.search_entry = tk.Entry(
            search_bar, textvariable=self.search_var, font=FONT,
            relief="solid", bd=1, bg=WHITE, fg=TEXT, width=23,
        )
        self.search_entry.pack(side="left", ipady=3)
        tk.Button(search_bar, text="Clear", command=lambda: self.search_var.set(""),
                  bg=PANEL, fg=MUTED, font=FONT, relief="flat", bd=0,
                  cursor="hand2", padx=8, pady=3).pack(side="left", padx=(6, 0))
        # Keep the search controls centered even when the result count changes.
        tk.Label(category_left, textvariable=self.search_results_var,
                 bg=WHITE, fg=MUTED, font=SMALL, anchor="w").pack(side="left", padx=(10, 0))

        canvas_frame = tk.Frame(category_card, bg=WHITE)
        canvas_frame.pack(fill="both", expand=True, padx=13, pady=(0, 9))
        canvas_frame.grid_columnconfigure(0, weight=1)
        canvas_frame.grid_rowconfigure(1, weight=1)
        header = tk.Frame(canvas_frame, bg="#f1f3f6", height=30)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_rowconfigure(0, weight=1)
        _editor_columns(header)
        for i, label in enumerate(("COLOR CATEGORY", "RGB", "HEX", "CIELAB", "ACTIONS")):
            _cell(header, i, label, background="#f1f3f6", color=MUTED,
                  font=("Segoe UI", 8, "bold"), justify="w" if i == 0 else "center")
        self.canvas = tk.Canvas(canvas_frame, bg=WHITE, highlightthickness=0, bd=0)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        scroll = UtilsTools.styled_scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        scroll.grid(row=1, column=1, sticky="ns")
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
        """Update visible occurrences without destroying unrelated widgets."""
        query = self.search_var.get().strip()
        if self.hierarchy:
            opened = (category in self.expanded or bool(query)) and category not in self._search_collapsed
        else:
            category_match, hits = self._search_hits(category, self.categories[category]["granules"], query)
            opened = (category in self.expanded or bool(query and not category_match and hits)) and category not in self._search_collapsed
        if opened:
            self.expanded.discard(category)
            if query:
                self._search_collapsed.add(category)
        else:
            self._search_collapsed.discard(category)
            self.expanded.add(category)
        self._sync_editor_rows()

    def _apply_search_filter(self):
        """Filter the existing table, creating only newly visible widgets."""
        self._search_after_id = None
        if not self.win.winfo_exists():
            return
        self._sync_editor_rows()
        if self.search_var.get().strip():
            self.canvas.yview_moveto(0.0)

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

    def _validate_graph(self, categories, hierarchy):
        error = validate_draft(categories)
        if error:
            raise ValueError(error)
        return draft_graph(categories, hierarchy)

    def _commit_draft(self, categories, hierarchy):
        self._validate_graph(categories, hierarchy)
        self.categories, self.hierarchy = categories, hierarchy

    def _geometry_allowed(self):
        if self.geometry_locked:
            self._warning("Original construction sites are unavailable. Only semantic edits are allowed.")
            return False
        return True

    def _choose_members(self, title, choices, callback, selected=(), *,
                        group=False, description=None, required=(), single=False,
                        accept_text="Apply", remaining_parent=None):
        """One centered, searchable dialog; selections survive filtering.

        The callback commits the draft only on success. Required members are
        used when wrapping an existing category in a new parent.
        """
        if not choices:
            self._warning("No eligible components are available.")
            return
        dialog = tk.Toplevel(self.win)
        dialog.withdraw()
        dialog.title(title)
        dialog.transient(self.win)
        dialog.configure(bg=BG)
        dialog.resizable(True, True)
        dialog.minsize(440, 390)
        body = tk.Frame(dialog, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=12)
        card = tk.Frame(body, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="x", pady=(0, 8))
        tk.Label(card, text=title, font=("Segoe UI", 14, "bold"), bg=WHITE, fg=TEXT).pack(anchor="w", padx=14, pady=(10, 2))
        name_var = tk.StringVar(master=dialog)
        name_entry = None
        name_row = tk.Frame(card, bg=WHITE)
        name_row.pack(fill="x", padx=14, pady=(4, 12))
        description_label = tk.Label(name_row, text=description or "Choose the existing components to use.",
                 font=FONT, bg=WHITE, fg=MUTED, justify="left", anchor="w", wraplength=490)
        if group:
            name_fields = tk.Frame(name_row, bg=WHITE)
            name_fields.pack(side="right", padx=(10, 0))
            tk.Label(name_fields, text="Group name", font=BOLD, bg=WHITE, fg=TEXT).pack(side="left", padx=(0, 8))
            name_entry = tk.Entry(name_fields, textvariable=name_var, font=FONT, relief="solid", bd=1, width=18)
            name_entry.pack(side="left", ipady=3)
            # Wrap the description instead of clipping either control at high DPI.
            def fit_description(event):
                width = max(90, event.width - name_fields.winfo_reqwidth() - 12)
                if int(description_label.cget("wraplength")) != width:
                    description_label.configure(wraplength=width)
            name_row.bind("<Configure>", fit_description)
            description_label.configure(wraplength=200)
        description_label.pack(side="left", fill="x", expand=True)
        remaining_var = tk.StringVar(master=dialog)
        remaining_row = None
        if remaining_parent is not None:
            remaining_row = tk.Frame(card, bg=WHITE)
            tk.Label(remaining_row, text="Remaining granules", font=BOLD, bg=WHITE,
                     fg=TEXT).pack(anchor="w")
            tk.Label(remaining_row, text="Name the subcategory for the unselected granules.",
                     font=SMALL, bg=WHITE, fg=MUTED).pack(anchor="w", pady=(2, 4))
            remaining_entry = tk.Entry(remaining_row, textvariable=remaining_var, font=FONT,
                                       relief="solid", bd=1)
            remaining_entry.pack(fill="x", ipady=3)
        content = tk.Frame(body, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        content.pack(fill="both", expand=True)
        toolbar = tk.Frame(content, bg=WHITE)
        toolbar.pack(fill="x", padx=12, pady=(10, 8))
        kinds = {kind for kind, _ in choices}
        heading = "Categories" if kinds <= {"category", "root"} else ("Granules" if kinds == {"granule"} else "Components")
        toolbar.grid_columnconfigure(0, weight=1, uniform="side")
        toolbar.grid_columnconfigure(2, weight=1, uniform="side")
        tk.Label(toolbar, text=heading, bg=WHITE, fg=TEXT, font=BOLD).grid(row=0, column=0, sticky="w")
        count = tk.StringVar(master=dialog)
        tk.Label(toolbar, textvariable=count, bg=WHITE, fg=PURPLE, font=SMALL).grid(row=0, column=2, sticky="e")
        filter_row = tk.Frame(toolbar, bg=WHITE)
        filter_row.grid(row=0, column=1, padx=6)
        query = tk.StringVar(master=dialog)
        tk.Label(filter_row, text="Search", bg=WHITE, fg=MUTED, font=FONT).pack(side="left", padx=(0, 6))
        search = tk.Entry(filter_row, textvariable=query, font=FONT, relief="solid", bd=1, width=15)
        search.pack(side="left", ipady=2)
        kind_var = tk.StringVar(master=dialog, value="Categories" if kinds == {"category", "granule"} else "All")
        if kinds == {"category", "granule"}:
            filters = tk.Frame(content, bg=WHITE)
            filters.pack(anchor="center", pady=(0, 6))
            for label in ("Categories", "Granules", "All"):
                tk.Radiobutton(filters, text=label, value=label, variable=kind_var,
                               indicatoron=False, selectcolor=SOFT_PURPLE,
                               bg=PANEL, fg=PURPLE, activebackground=SOFT_PURPLE,
                               font=SMALL, relief="flat", bd=0, cursor="hand2",
                               padx=6, pady=4).pack(side="left", padx=(0, 2))
        list_frame = tk.Frame(content, bg=WHITE)
        list_frame.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        canvas = tk.Canvas(list_frame, bg=WHITE, highlightbackground=BORDER, highlightthickness=1, bd=0)
        canvas.pack(side="left", fill="both", expand=True)
        scroll = UtilsTools.styled_scrollbar(list_frame, orient="vertical", command=canvas.yview)
        scroll.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scroll.set)
        inner = tk.Frame(canvas, bg=WHITE)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=max(1, e.width-2)))
        graph = draft_graph(self.categories, self.hierarchy)
        sites = {g["label"]: (owner, g) for owner, data in self.categories.items() for g in data["granules"]}
        required = set(required)
        checked = {pair: tk.BooleanVar(master=dialog, value=pair in selected or pair in required) for pair in choices}
        visible = []
        status = tk.StringVar(master=dialog, value="")
        def update_count():
            n = sum(v.get() for v in checked.values())
            count.set(f"{n} selected")
            if remaining_row is not None:
                if 0 < n < len(choices):
                    remaining_row.pack(fill="x", padx=14, pady=(0, 12))
                else:
                    remaining_row.pack_forget()
        def choose_one(pair):
            if single and checked[pair].get():
                for other, v in checked.items():
                    if other != pair: v.set(False)
            update_count()
        def wheel(event):
            n = getattr(event, "num", None)
            d = getattr(event, "delta", 0)
            if n == 4 or d > 0: canvas.yview_scroll(-1, "units")
            elif n == 5 or d < 0: canvas.yview_scroll(1, "units")
            return "break"
        def bind_wheel(w):
            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                w.bind(seq, wheel)
            for child in w.winfo_children(): bind_wheel(child)
        def render(*_):
            for child in inner.winfo_children(): child.destroy()
            visible.clear()
            terms = query.get().casefold().split()
            mode = kind_var.get()
            for kind, section in (("root", "Top level"), ("category", "Categories"), ("granule", "Granules")):
                if mode not in ("All", section): continue
                items = []
                for pair in choices:
                    k, target = pair
                    if k != kind: continue
                    context = target if k in ("category", "root") else target + " " + sites[target][0]
                    if all(term in context.casefold() for term in terms): items.append(pair)
                if not items: continue
                if len(kinds) > 1:
                    tk.Label(inner, text=section.upper(), bg="#f1f3f6", fg=MUTED, font=("Segoe UI", 8, "bold"), anchor="w", padx=8, pady=5).pack(fill="x")
                for i, pair in enumerate(items):
                    k, target = pair
                    visible.append(pair)
                    bg = WHITE
                    row = tk.Frame(inner, bg=bg)
                    row.pack(fill="x", padx=2, pady=1)
                    cb = tk.Checkbutton(row, variable=checked[pair], command=lambda p=pair: choose_one(p),
                                        bg=bg, activebackground=bg, selectcolor=WHITE, cursor="hand2",
                                        state="disabled" if pair in required else "normal")
                    cb.pack(side="left", padx=(5, 2))
                    if k == "root":
                        lab = None
                        detail = "No parent category"
                    elif k == "category":
                        leaves = graph.unique_granules(target)
                        lab = sites[leaves[0]][1]["lab"]
                        detail = f"{len(leaves)} granule{'s' if len(leaves) != 1 else ''}"
                        if target in self.hierarchy: detail = "Group · " + detail
                    else:
                        owner, granule = sites[target]
                        lab = granule["lab"]
                        detail = owner
                    if lab is not None:
                        _swatch(row, lab, size=20, bg=bg).pack(side="left", padx=(0, 8))
                    else:
                        tk.Label(row, text="↥", bg=bg, fg=PURPLE, font=BOLD, width=3).pack(side="left", padx=(0, 8))
                    tk.Label(row, text=target, bg=bg, fg=TEXT, font=FONT, anchor="w").pack(side="left", fill="x", expand=True, pady=6)
                    tk.Label(row, text="Required" if pair in required else detail, bg=bg, fg=MUTED, font=SMALL).pack(side="right", padx=8)
                    if pair not in required:
                        # Clicking the swatch or label is equivalent to the checkbox.
                        def toggle_row(_event, p=pair):
                            checked[p].set(not checked[p].get())
                            choose_one(p)
                        for target_widget in (row, *[w for w in row.winfo_children() if w is not cb]):
                            target_widget.configure(cursor="hand2")
                            target_widget.bind("<Button-1>", toggle_row)
            if not visible:
                tk.Label(inner, text="No matching components.", font=FONT, fg=MUTED, bg=WHITE, pady=18).pack(fill="x")
            bind_wheel(inner)
            canvas.yview_moveto(0)
            update_count()
        def select_visible():
            for pair in visible: checked[pair].set(True)
            update_count()
        def clear():
            for pair, value in checked.items(): value.set(pair in required)
            update_count()
        tools = tk.Frame(content, bg=WHITE)
        tools.pack(side="bottom", fill="x", padx=12, pady=(0, 7), before=list_frame)
        tools_inner = tk.Frame(tools, bg=WHITE)
        tools_inner.pack(anchor="center")
        if not single:
            tk.Button(tools_inner, text="Select visible", command=select_visible, fg=PURPLE, bg=WHITE, relief="flat", font=SMALL, cursor="hand2").pack(side="left", padx=(0, 8))
        tk.Button(tools_inner, text="Clear selection", command=clear, fg=MUTED, bg=WHITE, relief="flat", font=SMALL, cursor="hand2").pack(side="left")
        footer = tk.Frame(body, bg=BG)
        footer.pack(side="bottom", fill="x", pady=(8, 0), before=content)
        tk.Label(footer, textvariable=status, font=SMALL, fg="#9b3a3a", bg=BG, wraplength=300, justify="left").pack(side="left", fill="x", expand=True)
        def accept():
            refs = [{k: t} for (k,t), v in checked.items() if v.get()]
            if not refs or (single and len(refs) != 1):
                status.set("Select exactly one component." if single else "Select at least one component.")
                return
            if group:
                name, name_error = UtilsTools.check_label_name(name_var.get(), kind="Group")
                if name_error:
                    status.set(name_error)
                    name_entry.focus_set()
                    return
                if not name:
                    status.set("Enter a group name.")
                    name_entry.focus_set()
                    return
                limit = UtilsTools.MAX_CATEGORY_NAME_CHARS if remaining_parent is not None else UtilsTools.MAX_COLOR_NAME_CHARS
                if len(name) > limit:
                    status.set(f"Use at most {limit} characters.")
                    name_entry.focus_set()
                    return
                if name in self.categories or name in self.hierarchy:
                    status.set(f"A category named '{name}' already exists.")
                    name_entry.focus_set()
                    return
            remaining_name = None
            if remaining_parent is not None and len(refs) < len(choices):
                remaining_name, name_error = UtilsTools.check_label_name(remaining_var.get(), max_length=UtilsTools.MAX_CATEGORY_NAME_CHARS, kind="Subcategory")
                if name_error:
                    status.set(name_error)
                    remaining_entry.focus_set()
                    return
                if not remaining_name:
                    status.set("Name the subcategory for the remaining granules.")
                    remaining_entry.focus_set()
                    return
                if len(remaining_name) > UtilsTools.MAX_CATEGORY_NAME_CHARS:
                    status.set(f"Use at most {UtilsTools.MAX_CATEGORY_NAME_CHARS} characters.")
                    remaining_entry.focus_set()
                    return
                if remaining_name == name or remaining_name in self.categories or remaining_name in self.hierarchy:
                    status.set("Use two different, unused category names.")
                    remaining_entry.focus_set()
                    return
            try:
                if group:
                    result = (callback(name, refs, remaining_name) if remaining_parent is not None
                              else callback(name, refs))
                else:
                    result = callback(refs)
                if result is False:
                    return
            except (ValueError, KeyError, TypeError) as exc:
                status.set(str(exc)); return
            dialog.destroy()
            self.refresh()
        tk.Button(footer, text=accept_text, command=accept, bg=PURPLE, fg=WHITE,
                  activebackground=UtilsTools.UI_ACCENT_DARK, activeforeground=WHITE, relief="flat", font=BOLD, padx=13, pady=7, cursor="hand2").pack(side="right")
        tk.Button(footer, text="Cancel", command=dialog.destroy, bg="#e8eaee", fg=TEXT, relief="flat", font=FONT, padx=12, pady=7, cursor="hand2").pack(side="right", padx=(0, 7))
        query.trace_add("write", render)
        kind_var.trace_add("write", render)
        render()
        bind_wheel(canvas)
        # Center over the editor, not the entire application or desktop.
        self.win.update_idletasks()
        sw, sh = dialog.winfo_screenwidth(), dialog.winfo_screenheight()
        w, h = min(560, sw-30), min((645 if remaining_parent is not None else 565) if group else 485, sh-80)
        x = max(0, min(self.win.winfo_rootx()+(self.win.winfo_width()-w)//2, sw-w))
        y = max(0, min(self.win.winfo_rooty()+(self.win.winfo_height()-h)//2, sh-h-35))
        dialog.geometry(f"{w}x{h}+{x}+{y}")
        dialog.bind("<Escape>", lambda _e: dialog.destroy())
        dialog.deiconify()
        dialog.wait_visibility()
        dialog.grab_set()
        (name_entry or search).focus_set()
        # Named handles also make Tk regression tests independent of layout.
        dialog.member_vars = checked
        dialog.name_var = name_var
        dialog.search_var = query
        dialog.kind_var = kind_var
        dialog.status_var = status
        dialog.remaining_var = remaining_var
        dialog.remaining_row = remaining_row

    def _member_choices(self, category=None, kind_filter=None, exclude_ancestors_of=None):
        graph = draft_graph(self.categories, self.hierarchy)
        existing = set(graph.children(category)) if category in graph.category_labels else set()
        blocked = {category} if category else set()
        anchor = exclude_ancestors_of or category
        if anchor:
            # A link from anchor to any of its ancestors would create a cycle.
            pending = [anchor]
            while pending:
                child = pending.pop()
                if child not in blocked: blocked.add(child)
                for parent, refs in self.hierarchy.items():
                    if {"category": child} in refs and parent not in blocked:
                        blocked.add(parent); pending.append(parent)
        return [(kind, target) for kind, labels in (
            ("category", graph.category_labels),
            ("granule", tuple(g["label"] for data in self.categories.values() for g in data["granules"])))
            for target in labels if (kind_filter is None or kind == kind_filter)
            and (kind, target) not in existing and not (kind == "category" and target in blocked)]

    def add_group(self, parent=None, initial=None, replace_parent=None):
        container = replace_parent if initial else parent
        graph = draft_graph(self.categories, self.hierarchy)
        if container in self.categories:
            if not self._geometry_allowed(): return
            choices = [("granule", g["label"]) for g in self.categories[container]["granules"]]
        elif container is not None:
            choices = [(k, t) for k, t in graph.children(container) if k == "category"]
        else:
            choices = [("category", n) for n in graph.roots()]
        # A parent/group only groups siblings; shared legacy nodes are ineligible.
        choices = [(k,t) for k,t in choices if k == "granule" or
                   sum({"category": t} in children for children in self.hierarchy.values()) <= (1 if container else 0)]
        if initial and ("category", initial) not in choices:
            self._warning("This category is shared. Remove its extra reference before grouping it.")
            return
        def commit(name, refs, remaining_name=None):
            candidate, nodes = group_tree_draft(self.categories, self.hierarchy, name, refs, container,
                                                 remaining_name=remaining_name)
            self._commit_draft(candidate, nodes)
            self.expanded.add(name)
            if container: self.expanded.add(container)
        title = "Create parent group" if initial else ("Add subgroup" if parent else "Create color group")
        desc = ("Group selected granules into a subcategory."
                if container in self.categories else
                "Group categories at the same level.")
        self._choose_members(title, choices, commit, group=True, description=desc,
                             accept_text="Create group", required=[("category", initial)] if initial else (),
                             remaining_parent=container if container in self.categories else None)

    def _move_to_root(self, parent, target):
        # Compatibility for callers; use the same guarded move as the dialog.
        if self._commit_reference_move(parent, "category", target, None):
            self.refresh()

    def _commit_reference_move(self, parent, kind, target, destination):
        nodes = copy.deepcopy(self.hierarchy)
        ref = {kind: target}
        if parent not in nodes or ref not in nodes[parent]:
            self._warning("This component is no longer in the selected group.")
            return False
        if destination == parent or (destination is None and kind != "category"):
            return False
        # Never implicitly delete an ancestor just because its last child moved.
        if len(nodes[parent]) == 1:
            self._warning(f"'{parent}' would be empty. Delete the group explicitly to move its children up, or add another child first.", "Cannot Move Component")
            return False
        nodes[parent].remove(ref)
        if destination is not None:
            if destination not in nodes or ref in nodes[destination]:
                self._warning("Choose a different valid destination.")
                return False
            nodes[destination].append(ref)
        try:
            old_graph = draft_graph(self.categories, self.hierarchy)
            new_graph = self._validate_graph(self.categories, nodes)
        except ValueError as exc:
            self._warning(str(exc), "Cannot Move Component")
            return False
        affected = []
        for label in old_graph.category_labels:
            before = old_graph.granule_occurrence_counts(label)
            after = new_graph.granule_occurrence_counts(label)
            if before != after:
                affected.append(f"{label}: {sum(before.values())} → {sum(after.values())} granule occurrences")
        dest_text = "top level (no parent)" if destination is None else f"'{destination}'"
        if not messagebox.askyesno("Move component",
                f"Move '{target}' from '{parent}' to {dest_text}?\n\n"
                "Affected categories may have different memberships. No category or prototype is deleted.\n"
                + "\n".join(affected), parent=self.win):
            return False
        self._commit_draft(self.categories, nodes)
        if destination: self.expanded.add(destination)
        self.status_var.set(f"Moved '{target}' to {dest_text}. Apply Changes to save.")
        return True

    def _choose_subcategory_action(self, parent):
        """One entry point for the two ways of creating a child category."""
        dialog = tk.Toplevel(self.win)
        dialog.withdraw()
        dialog.title("Add subcategory")
        dialog.transient(self.win)
        dialog.configure(bg=BG)
        dialog.resizable(False, False)
        body = tk.Frame(dialog, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        body.pack(fill="both", expand=True, padx=12, pady=12)
        tk.Label(body, text="Add subcategory", bg=WHITE, fg=TEXT,
                 font=("Segoe UI", 14, "bold"), anchor="center").pack(fill="x", padx=14, pady=(12, 2))
        tk.Label(body, text=f"Create a child of {parent}.", bg=WHITE, fg=MUTED,
                 font=FONT, anchor="center").pack(fill="x", padx=14, pady=(0, 12))
        def choose(action):
            dialog.destroy()
            action(parent)
        for title, detail, action, enabled in (
            ("Create new color", "Add a new category with its own prototypes.",
             self._add_subcategory, not self.geometry_locked),
            ("Group existing components", "Organize this color's existing children without adding prototypes.",
             lambda name: self.add_group(parent=name), not self.geometry_locked or parent in self.hierarchy),
        ):
            tile = tk.Frame(body, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
            tile.pack(fill="x", padx=14, pady=(0, 8))
            heading = tk.Button(tile, text=title, command=lambda a=action: choose(a),
                                state="normal" if enabled else "disabled", bg=PANEL, fg=PURPLE,
                                activebackground=SOFT_PURPLE, activeforeground=PURPLE, font=BOLD,
                                relief="flat", bd=0, cursor="hand2" if enabled else "arrow", anchor="w")
            heading.pack(fill="x", padx=8, pady=(5, 0))
            description = tk.Label(tile, text=detail, bg=PANEL, fg=MUTED, font=FONT, anchor="w",
                                   justify="left", wraplength=385)
            description.pack(fill="x", padx=12, pady=(0, 8))
            if enabled:
                # The native button retains keyboard activation. Its surrounding
                # padding and description invoke the same action, exactly once.
                for widget in (tile, description):
                    widget.configure(cursor="hand2")
                    widget.bind("<ButtonRelease-1>", lambda _e, a=action: choose(a))

                def paint(hover, t=tile, h=heading, d=description):
                    if t.winfo_exists():
                        color = SOFT_PURPLE if hover else PANEL
                        t.configure(bg=color, highlightbackground=PURPLE if hover else BORDER)
                        h.configure(bg=color)
                        d.configure(bg=color)

                def leave(_event, t=tile, paint_tile=paint):
                    # Crossing between child widgets must not flicker the card.
                    if not t.winfo_exists():
                        return
                    x, y = t.winfo_pointerxy()
                    inside = (t.winfo_rootx() <= x < t.winfo_rootx()+t.winfo_width()
                              and t.winfo_rooty() <= y < t.winfo_rooty()+t.winfo_height())
                    paint_tile(inside)

                for widget in (tile, heading, description):
                    widget.bind("<Enter>", lambda _e, f=paint: f(True), add="+")
                    widget.bind("<Leave>", leave, add="+")
        tk.Button(body, text="Cancel", command=dialog.destroy, bg=WHITE, fg=MUTED,
                  relief="flat", font=FONT, cursor="hand2").pack(anchor="e", padx=14, pady=(2, 10))
        dialog.update_idletasks()
        w, h = max(440, dialog.winfo_reqwidth()), dialog.winfo_reqheight()
        x = max(0, min(self.win.winfo_rootx()+(self.win.winfo_width()-w)//2, dialog.winfo_screenwidth()-w))
        y = max(0, min(self.win.winfo_rooty()+(self.win.winfo_height()-h)//2, dialog.winfo_screenheight()-h-35))
        dialog.geometry(f"{w}x{h}+{x}+{y}")
        dialog.bind("<Escape>", lambda _e: dialog.destroy())
        dialog.deiconify()
        dialog.wait_visibility()
        dialog.grab_set()

    def _add_subcategory(self, parent):
        if parent not in self.categories and parent not in self.hierarchy:
            return
        if not self._geometry_allowed():
            return
        # The existing color picker also collects the name of the child
        # retaining the original sites, without a second modal dialog.
        host = _CategoryHost(self)
        host.parent_category = parent
        host.original_child_parent = parent if parent in self.categories else None
        UtilsTools.CustomCategoryDialog(host)

    def _unlink(self, parent, kind, target):
        refs = self.hierarchy.get(parent, ())
        if {kind: target} not in refs or len(refs) <= 1:
            self._warning("Removing this reference would leave an empty or missing group.")
            return
        if not messagebox.askyesno("Unlink component",
                f"Remove the link from '{parent}' to '{target}'?\n\n"
                "The component and its geometry will remain in the color space.", parent=self.win):
            return
        nodes = copy.deepcopy(self.hierarchy)
        nodes[parent].remove({kind: target})
        prune_empty_groups(nodes)
        try:
            self._commit_draft(self.categories, nodes)
        except ValueError as exc:
            self._warning(str(exc)); return
        self.refresh()

    def _move_reference(self, parent, kind, target):
        if len(self.hierarchy.get(parent, ())) <= 1:
            self._warning(f"'{parent}' would be empty. Delete the group explicitly to move its children up, or add another child first.", "Cannot Move Component")
            return
        blocked = {parent}
        if kind == "category":
            pending = [target]
            while pending:
                node = pending.pop()
                if node in blocked: continue
                blocked.add(node)
                pending.extend(ref["category"] for ref in self.hierarchy.get(node, []) if "category" in ref)
        choices = [("category", name) for name, refs in self.hierarchy.items()
                   if name not in blocked and {kind: target} not in refs]
        if kind == "category" and sum({"category": target} in refs for refs in self.hierarchy.values()) == 1:
            choices.insert(0, ("root", "Top level"))
        def commit(refs):
            dest = refs[0].get("category")
            return self._commit_reference_move(parent, kind, target, dest)
        self._choose_members("Move component", choices, commit,
                             single=True, description="Choose a destination. Moving changes category membership, not prototype coordinates.",
                             accept_text="Move")

    def _occupied(self, exclude_category=None, exclude_index=None):
        return [
            (category, g["label"], g["lab"])
            for category, data in self.categories.items()
            for index, g in enumerate(data["granules"])
            if not (category == exclude_category and index == exclude_index)
        ]

    def _insert_category(self, name, granules, parent=None, *, original_child_name=None):
        if not self._geometry_allowed():
            return False
        name, name_error = UtilsTools.check_label_name(name, max_length=UtilsTools.MAX_CATEGORY_NAME_CHARS, kind="Category")
        if name_error:
            self._warning(name_error)
            return False
        if name in self.categories or name in self.hierarchy:
            self._warning(f"Category '{name}' already exists.")
            return False
        if parent is not None:
            original_child_name, original_error = UtilsTools.check_label_name(original_child_name, max_length=UtilsTools.MAX_CATEGORY_NAME_CHARS, kind="Subcategory")
            if parent not in self.categories and parent not in self.hierarchy:
                self._warning("The parent category no longer exists.")
                return False
            if parent in self.categories and (original_error or original_child_name == name or
                    original_child_name in self.categories or original_child_name in self.hierarchy or
                    len(original_child_name) > UtilsTools.MAX_CATEGORY_NAME_CHARS):
                self._warning("Choose a different name for the existing granules first.")
                return False
            candidate, nodes, base_child = prepare_parent_draft(
                self.categories, self.hierarchy, parent, reserved=(name,), child_name=original_child_name)
        else:
            candidate, nodes, base_child = copy.deepcopy(self.categories), copy.deepcopy(self.hierarchy), None
        candidate[name] = {
            "source": None,
            "granules": [{"label": item["label"], "lab": _triple(item["lab"]),
                           "original_label": None} for item in granules],
        }
        error = validate_draft(candidate)
        if error:
            self._warning(error)
            return False
        if parent is not None:
            nodes[parent].append({"category": name})
        try:
            self._commit_draft(candidate, nodes)
        except ValueError as exc:
            self._warning(str(exc)); return False
        if base_child:
            self.status_var.set(f"Existing granules organized in {base_child}.")
        if parent: self.expanded.add(parent)
        self.expanded.add(name)
        if self.search_var.get().strip():
            self.search_var.set("")
        self.refresh()
        return True

    def add_category(self):
        if not self._geometry_allowed(): return
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
        if not self._geometry_allowed(): return
        if category not in self.categories or (index is not None and not 0 <= index < len(self.categories[category]["granules"])):
            return
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
                nodes = remap_references(self.hierarchy, granule_names={previous["label"]: label} if previous else {})
                self._commit_draft(new_list, nodes)
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
            initial_mode=self.model_var.get(),
            submit_text="Save changes" if previous else "Add granule",
            on_granule_submit=submit,
        )

    def _rename_category(self, name, variable):
        if name in self._renaming or (name not in self.categories and name not in self.hierarchy):
            return False
        limit = 24 if name in self.hierarchy else UtilsTools.MAX_CATEGORY_NAME_CHARS
        new, name_error = UtilsTools.check_label_name(variable.get(), max_length=limit, kind="Category")
        if new == name and not name_error:
            return True
        self._renaming.add(name)
        try:
            if name_error or new in self.categories or new in self.hierarchy:
                variable.set(name)
                self._warning(name_error or f"A category named '{new}' already exists.")
                return False
            updated = OrderedDict()
            renamed_sites = {}
            for key, data in self.categories.items():
                current = copy.deepcopy(data)
                if key == name:
                    for granule in current["granules"]:
                        label = granule["label"]
                        if label == name:
                            granule["label"] = new
                        elif label.startswith(name + "-g") and label[len(name)+2:].isdigit():
                            suffix = label[len(name):]
                            granule["label"] = new[:24-len(suffix)] + suffix
                        if label != granule["label"]:
                            renamed_sites[label] = granule["label"]
                updated[new if key == name else key] = current
            problem = validate_draft(updated)
            if problem:
                variable.set(name)
                self._warning(problem)
                return False
            nodes = remap_references(self.hierarchy, {name: new}, renamed_sites)
            self._commit_draft(updated, nodes)
            if name in self.expanded:
                self.expanded.discard(name); self.expanded.add(new)
            self.refresh()
            return True
        except (ValueError, KeyError, TypeError) as exc:
            variable.set(name); self._warning(str(exc))
            return False
        finally:
            self._renaming.discard(name)

    def _remove_category(self, category):
        if category not in self.categories and category not in self.hierarchy:
            return
        if category not in self.hierarchy and not self._geometry_allowed(): return
        candidate, nodes = copy.deepcopy(self.categories), copy.deepcopy(self.hierarchy)
        parents = [name for name, refs in nodes.items() if {"category": category} in refs]
        if len(parents) > 1:
            self._warning("This imported category has multiple parents. Unlink the extra references first.")
            return
        aggregate = category in nodes
        children = nodes.pop(category) if aggregate else []
        if not aggregate:
            del candidate[category]
        if parents:
            refs = nodes[parents[0]]
            if not children and len(refs) == 1:
                self._warning(f"Deleting '{category}' would leave '{parents[0]}' empty. Delete the parent group explicitly first, or add another child.", "Cannot Delete Category")
                return
            index = refs.index({"category": category})
            refs[index:index+1] = children
        prune_empty_groups(nodes)
        try:
            self._validate_graph(candidate, nodes)
        except ValueError as exc:
            self._warning(f"Cannot delete '{category}': {exc}"); return
        detail = ("Only the group will be deleted. Its categories move up one level; geometry remains."
                  if aggregate else "The category and its own granules will be deleted from the space.")
        if not messagebox.askyesno("Delete Category", f"Delete '{category}'?\n\n{detail}", parent=self.win): return
        self._commit_draft(candidate, nodes)
        self.expanded.discard(category); self.refresh()

    def _remove_granule(self, category, index):
        if not self._geometry_allowed(): return
        if category not in self.categories or not 0 <= index < len(self.categories[category]["granules"]):
            return
        if len(self.categories[category]["granules"]) == 1:
            self._remove_category(category)
            return
        candidate = copy.deepcopy(self.categories)
        label = candidate[category]["granules"].pop(index)["label"]
        try:
            self._validate_graph(candidate, self.hierarchy)
        except ValueError as exc:
            self._warning(f"Cannot delete '{label}': {exc} Remove its references first."); return
        if not messagebox.askyesno("Delete Granule", f"Delete '{label}' from the color space?\n\nIts geometry will be removed when changes are applied.", parent=self.win): return
        self._commit_draft(candidate, self.hierarchy); self.refresh()

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
        if not self._geometry_allowed(): return False
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

        if is_last:
            self._warning("Moving the last granule would empty this color. Move or group the category instead.",
                          "Cannot Move Granule")
            return False

        # Prepare the modification without changing the active draft.
        candidate = copy.deepcopy(self.categories)

        moving = candidate[source]["granules"].pop(index)
        candidate[destination]["granules"].append(moving)

        nodes = copy.deepcopy(self.hierarchy)
        # Validate the complete result before committing.
        try:
            self._validate_graph(candidate, nodes)
        except ValueError as exc:
            self._warning(str(exc), "Cannot Move Granule")
            return False

        if self.hierarchy:
            old_graph = draft_graph(self.categories, self.hierarchy)
            new_graph = draft_graph(candidate, nodes)
            affected = []
            for name in self.hierarchy:
                before = old_graph.granule_occurrence_counts(name)
                after = new_graph.granule_occurrence_counts(name)
                if before != after:
                    affected.append(f"{name}: {sum(before.values())} → {sum(after.values())} granule occurrences")
            detail = ""
            if affected:
                detail += "Affected parent memberships may change:\n" + "\n".join(affected) + "\n"
            confirmed = messagebox.askyesno(
                "Move Granule",
                f"Move '{item['label']}' from '{source}' to '{destination}'?\n\n"
                + detail + "Prototype coordinates stay unchanged.\nContinue?",
                parent=self.win,
                icon="warning"
            )

            if not confirmed:
                return False

        self.categories, self.hierarchy = candidate, nodes

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


    def _cancel_restore_scroll(self):
        if self._restore_scroll_id is not None:
            try:
                self.canvas.after_cancel(self._restore_scroll_id)
            except tk.TclError:
                pass
            self._restore_scroll_id = None

    def refresh(self):
        """Rebuild only after a draft mutation, not a navigation operation."""
        self._cancel_restore_scroll()
        if self._search_after_id is not None:
            try: self.win.after_cancel(self._search_after_id)
            except tk.TclError: pass
        self._search_after_id = None
        oldpos = self.canvas.yview()[0]
        for child in self.inner.winfo_children():
            child.destroy()
        self._editor_rows = OrderedDict()
        self._no_search_results = tk.Label(
            self.inner, text="No categories or granules match the search.",
            font=FONT, bg=WHITE, fg=MUTED, pady=12,
        )
        total = sum(len(data["granules"]) for data in self.categories.values())
        self.count.set(f"{len(self.categories)+len(self.hierarchy)} categories  ·  {total} granules")
        self._sync_editor_rows()
        def restore_scroll():
            self._restore_scroll_id = None
            try:
                if self.canvas.winfo_exists():
                    self.canvas.yview_moveto(oldpos)
            except tk.TclError:
                pass
        self._restore_scroll_id = self.canvas.after_idle(restore_scroll)

    def _visible_editor_rows(self):
        query = self.search_var.get().strip()
        if self.hierarchy:
            yield from hierarchy_rows(self.categories, self.hierarchy, self.expanded,
                                      query, self._search_collapsed, self._tree_limit)
        else:
            for category, data in self.categories.items():
                granules = data["granules"]
                matched, hits = self._search_hits(category, granules, query)
                if query and not (matched or hits):
                    continue
                opened = (category in self.expanded or bool(query and not matched and hits)) and category not in self._search_collapsed
                shown = granules if not query or matched else [granules[i] for i in hits]
                yield (category,), category, None, None, shown, opened

    def _sync_editor_rows(self):
        """Reconcile visible path occurrences; existing unrelated rows stay live.

        Only navigation calls this method. Structural edits call refresh(), so
        cached callbacks and granule indices can never outlive a draft change.
        """
        self._tree_limit = {"limited": False}
        rows = list(self._visible_editor_rows())
        key_for = lambda item: item[0] if self.hierarchy else item[1]
        wanted = {key_for(item) for item in rows}
        self._no_search_results.pack_forget()
        for key in tuple(self._editor_rows):
            if key not in wanted:
                self._editor_rows.pop(key)["wrapper"].destroy()
        # Existing rows keep their relative order across expansion and search.
        # Insert only new rows immediately before the next visible row.
        following = None
        # Visible last sibling per path (filtering and collapsing change this).
        last_child = {item[0][:-1]: item[0] for item in rows}
        for index in range(len(rows)-1, -1, -1):
            item = rows[index]
            key = key_for(item)
            record = self._editor_rows.get(key)
            if record is None:
                record = self._create_editor_row(index, *item)
                options = {"fill": "x"}
                if following is not None:
                    options["before"] = following
                options.setdefault("pady", (0, 2))
                record["wrapper"].pack(**options)
                self._editor_rows[key] = record
            self._update_editor_row(record, *item)
            path = item[0]
            guides = tuple(last_child.get(path[:i]) != path[:i+1] for i in range(1, len(path)))
            self._update_tree_guides(record, path, guides, path in last_child, item[4], item[5])
            following = record["wrapper"]
        self._editor_rows = OrderedDict((key_for(item), self._editor_rows[key_for(item)]) for item in rows)
        query = self.search_var.get().strip()
        if query:
            self.search_results_var.set(f"{len(rows)} rows found" if self.hierarchy else f"{len(rows)} of {len(self.categories)} found")
            if not rows:
                self._no_search_results.pack(fill="x", pady=12)
        else:
            self.search_results_var.set("")
        if self._tree_limit["limited"]:
            self.search_results_var.set("Branch limit reached. Refine search or collapse groups.")
        # <Configure> updates the scrollregion once geometry has settled.

    def _create_editor_row(self, index, path, category, graph, sites, displayed_granules, opened):
        aggregate = category in self.hierarchy
        data = self.categories.get(category, {"granules": displayed_granules})
        depth = len(path)-1
        bg = WHITE
        wrap = tk.Frame(self.inner, bg=WHITE)
        row = tk.Frame(wrap, bg=bg, height=38)
        row.pack(fill="x")
        row.grid_propagate(False)
        row.grid_rowconfigure(0, weight=1)
        _editor_columns(row)
        leaves = graph.unique_granules(category) if graph is not None else ()
        first = sites[leaves[0]]["lab"] if graph is not None else data["granules"][0]["lab"]

        cell = tk.Frame(row, bg=bg)
        cell.grid(row=0, column=0, sticky="nsew", padx=(7+depth*14, 6))
        toggle = tk.Button(
            cell, text="▾" if opened else "▸",
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
        if aggregate or (len(leaves) if graph is not None else len(data["granules"])) > 1:
            values = ("", "", "")
        summary = [
            _cell(row, j + 1, "" if opened else value,
                  background=bg, font=FONT)
            for j, value in enumerate(values)
        ]

        
        actions = tk.Frame(row, bg=bg)
        actions.grid(row=0, column=4, sticky="nsew")
        actions.grid_columnconfigure(0, weight=1)
        actions.grid_rowconfigure(0, weight=1)

        centered_actions = tk.Frame(actions, bg=bg)
        centered_actions.grid(row=0, column=0)

        n = len(leaves) if graph is not None else len(data["granules"])

        count_button = tk.Button(
            centered_actions,
            text=("Group · " if aggregate else "") + f"{n} granule{'s' if n != 1 else ''}",
            command=lambda name=category:
                self._toggle_editor_category(name),
            bg=SOFT_PURPLE if n > 1 or aggregate else bg,
            fg=PURPLE if n > 1 or aggregate else MUTED,
            activebackground=SOFT_PURPLE if n > 1 or aggregate else bg,
            activeforeground=PURPLE if n > 1 or aggregate else MUTED,
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

        category_actions = tk.Frame(centered_actions, bg=bg)
        category_actions.pack(side="left")
        self._pack_category_actions(category_actions, path, category, aggregate, bg)

        panel = tk.Frame(wrap, bg=WHITE)

        toggle.configure(command=lambda name=category:
                         self._toggle_editor_category(name))
        record = {"wrapper": wrap, "row": row, "panel": panel, "toggle": toggle,
                  "summary": summary, "values": values, "opened": None,
                  "granule_rows": None, "visible_granules": None, "add_row": None,
                  "category_actions": category_actions, "singleton": not aggregate and n == 1,
                  "name_var": var, "category": category}
        self._bind_table_wheel(wrap)
        return record

    def _pack_category_actions(self, parent, path, category, aggregate, bg, font=SMALL):
        """Place category actions in either the header or the singleton leaf."""
        # Keep category semantics even when these actions are displayed on its
        # only granule: moving the category must not empty it.
        if len(path) > 1:
            if sum({"category": category} in refs for refs in self.hierarchy.values()) > 1:
                tk.Button(parent, text="Unlink", fg=PURPLE, bg=bg, relief="flat", bd=0,
                          highlightthickness=0, activebackground=bg, activeforeground=PURPLE,
                          font=font, cursor="hand2", padx=4,
                          command=lambda p=path: self._unlink(p[-2], "category", p[-1])).pack(side="left")
            tk.Button(parent, text="Move", fg=PURPLE, bg=bg, relief="flat", bd=0,
                      highlightthickness=0, activebackground=bg, activeforeground=PURPLE,
                      font=font, cursor="hand2", padx=4,
                      command=lambda p=path: self._move_reference(p[-2], "category", p[-1])).pack(side="left")

        tk.Button(parent, text="Delete", fg="#9b3a3a", bg=bg, relief="flat", bd=0,
                  highlightthickness=0, activebackground=bg, activeforeground="#9b3a3a",
                  font=font, cursor="hand2", padx=4,
                  state="normal" if aggregate or not self.geometry_locked else "disabled",
                  command=lambda name=category: self._remove_category(name)).pack(side="left")


    def _update_tree_guides(self, record, path, guides, has_category_children, granules, opened):
        """Draw connectors for visible paths without rebuilding row widgets."""
        visible_granules = tuple(g["label"] for g in granules) if opened else ()
        signature = (guides, bool(has_category_children), visible_granules, opened)
        if record.get("guide_signature") == signature:
            return
        for w in record.get("guide_widgets", ()):
            w.destroy()
        widgets = []
        def line(parent, **place):
            w = tk.Frame(parent, bg="#c9bfda", bd=0, highlightthickness=0)
            w.place(**place)
            w.lift()
            self._bind_table_wheel(w)
            widgets.append(w)
        depth = len(path)-1
        center = 19
        for i, continues in enumerate(guides):
            x = 17 + i*14
            if continues:
                line(record["wrapper"], x=x, y=0, width=1, relheight=1)
            elif i == depth-1:
                line(record["row"], x=x, y=0, width=1, height=center+1)
            if i == depth-1:
                line(record["row"], x=x, y=center, width=11, height=1)
        # Stem from the open parent to its immediate child rows. Finish at the
        # last visible granule unless another category follows.
        if opened and (visible_granules or has_category_children):
            x = 17 + depth*14
            line(record["row"], x=x, y=center+8, width=1, height=center-8)
            if has_category_children:
                line(record["panel"], x=x, y=0, width=1, relheight=1)
            granule_widgets = dict(record["granule_rows"] or ())
            for i, label in enumerate(visible_granules):
                child = granule_widgets[label]
                if not has_category_children:
                    if i == len(visible_granules)-1:
                        line(child, x=x, y=0, width=1, height=20)
                    else:
                        line(child, x=x, y=0, width=1, relheight=1)
                line(child, x=x, y=19, width=29, height=1)
        record["guide_widgets"] = widgets
        record["guide_signature"] = signature

    def _populate_editor_panel(self, record, path, category, graph, sites):
        """Build immediate granules only on first expansion of this row."""
        panel = record["panel"]
        aggregate = category in self.hierarchy
        depth = len(path)-1
        granules = ([sites[target] for kind, target in graph.children(category) if kind == "granule"]
                    if aggregate else self.categories[category]["granules"])
        granule_rows = []

        for gi, granule in enumerate(granules):
            granule_bg = WHITE
            grow = tk.Frame(panel, bg=granule_bg, height=38)
            grow.pack(fill="x", pady=(0, 1))
            granule_rows.append((granule["label"], grow))
            grow.grid_propagate(False)
            grow.grid_rowconfigure(0, weight=1)
            _editor_columns(grow)
            gcell = tk.Frame(grow, bg=granule_bg)
            gcell.grid(row=0, column=0, sticky="nsew", padx=(50+depth*14, 5))
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
            if aggregate:
                tk.Button(child_controls, text="Unlink", fg=PURPLE, bg=granule_bg,
                          relief="flat", bd=0, highlightthickness=0, font=SMALL,
                          activebackground=granule_bg, activeforeground=PURPLE, cursor="hand2",
                          command=lambda name=category, g=granule["label"]: self._unlink(name, "granule", g)).pack(side="left")
                tk.Button(child_controls, text="Move", fg=PURPLE, bg=granule_bg,
                          relief="flat", bd=0, highlightthickness=0, font=SMALL,
                          activebackground=granule_bg, activeforeground=PURPLE, cursor="hand2",
                          command=lambda name=category, g=granule["label"]: self._move_reference(name, "granule", g)).pack(side="left")
                continue
            if self.geometry_locked:
                if len(granules) == 1:
                    self._pack_category_actions(child_controls, path, category, False, granule_bg, font=FONT)
                continue
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

            if len(granules) == 1:
                self._pack_category_actions(child_controls, path, category, False, granule_bg, font=FONT)
                continue

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
            tk.Button(
                child_controls,
                text="Delete",
                command=lambda name=category, i=gi:
                    self._remove_granule(name, i),
                fg="#9b3a3a", bg=granule_bg, font=FONT,
                relief="flat", bd=0, highlightthickness=0, cursor="hand2"
            ).pack(side="left")

        addrow = tk.Frame(panel, bg=WHITE)
        addrow.pack(fill="x", padx=(54+depth*14, 0), pady=(3, 5))
        controls = []
        if not aggregate and not self.geometry_locked:
            controls.append(("+ Add granule", lambda name=category: self._picker(name), "normal"))
        controls.extend((
            ("+ Add subcategory", lambda name=category: self._choose_subcategory_action(name), "normal" if aggregate or not self.geometry_locked else "disabled"),
        ))
        for text, command, state in controls:
            tk.Button(addrow, text=text, command=command, state=state,
                      fg=PURPLE, bg=WHITE, activebackground=WHITE, activeforeground=PURPLE,
                      relief="flat", bd=0, highlightthickness=0,
                      font=BOLD if text == "+ Add granule" else SMALL,
                      cursor="hand2", padx=5, pady=4).pack(side="left", padx=(0, 5))
        record["granule_rows"] = granule_rows
        record["add_row"] = addrow
        # Panel itself was bound when its row was created. Only bind new children.
        for child in panel.winfo_children():
            self._bind_table_wheel(child)

    def _update_editor_row(self, record, path, category, graph, sites, displayed_granules, opened):
        if record["opened"] != opened:
            record["toggle"].configure(text="▾" if opened else "▸")
            for label, value in zip(record["summary"], record["values"]):
                label.configure(text="" if opened else value)
            if opened:
                if record["granule_rows"] is None:
                    self._populate_editor_panel(record, path, category, graph, sites)
                record["panel"].pack(fill="x")
            else:
                record["panel"].pack_forget()
            record["opened"] = opened
        if record["singleton"]:
            actions = record["category_actions"]
            show_header = not (opened and displayed_granules)
            if show_header and not actions.winfo_manager():
                actions.pack(side="left")
            elif not show_header and actions.winfo_manager():
                actions.pack_forget()
        if opened:
            shown = tuple(g["label"] for g in displayed_granules)
            if record["visible_granules"] != shown:
                shown_set = set(shown)
                for label, widget in record["granule_rows"]:
                    if label in shown_set:
                        # Keep relative order even when restoring filtered rows.
                        widget.pack(fill="x", before=record["add_row"])
                    else:
                        widget.pack_forget()
                record["visible_granules"] = shown

    def _snapshot(self):
        """Build a complete, validated application save request, without mutation."""
        self._validate_graph(self.categories, self.hierarchy)
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

    @staticmethod
    def _sites_signature(native, model):
        return (model, tuple((c,tuple((g,tuple(p)) for g,p in sites.items())) for c,sites in native.items()))

    def manage_negatives(self):
        if self._saving or self.geometry_locked or self.space.disjoint: return
        try:
            for record in tuple(self._editor_rows.values()):
                variable, category = record.get('name_var'), record.get('category')
                if variable is not None and variable.get()!=category:
                    if not self._rename_category(category,variable): return
                    break
            target=self.model_var.get()
            native, negatives=draft_construction_sites(self.categories,self.space,target,review=True)
            signature=self._sites_signature(native,target)
            if self._negative_override is not None:
                if signature==self._negative_signature:
                    negatives=self._negative_override
                else:
                    old_model, old_items=self._negative_signature
                    for owner, values in self._negative_override.items():
                        if owner in native:
                            new=[]
                            for q in values:
                                point=UtilsTools.negative_coordinate(q,old_model,target) if old_model!=target else tuple(q)
                                if not any(np.linalg.norm(np.asarray(point)-p)<=UtilsTools.Voronoi.DEFAULT_MERGE_EPS for p in native[owner].values()):new.append(point)
                            negatives[owner]=new
            names = converted_negative_names(self.space, target)
            if self._negative_override is not None:
                old_model = self._negative_signature[0]
                names = {UtilsTools.negative_coordinate(q,old_model,target): label
                         for q,label in (self._negative_names_override or {}).items()}
            dialog=UtilsTools.NegativePrototypeDialog(self.win,native,target,negatives,warn=self.app.custom_warning,app=self.app,negative_names=names)
            self.win.wait_window(dialog)
            if dialog.result is not None:
                self._negative_override=dialog.result
                self._negative_names_override=dialog.result_names
                self._negative_signature=signature
                self.status_var.set('Negative prototype changes remain local until Apply Changes.')
        except (ValueError,TypeError,KeyError,RuntimeError,tk.TclError) as exc:
            self._warning(str(exc),'Negative prototypes')

    def apply(self):
        if self._saving:
            return
        _, name_error = UtilsTools.check_color_space_name(self.file_var.get())
        if name_error:
            self._warning(name_error)
            return
        if id(self.app.fuzzy_color_space) != self.source_id or not self.app.COLOR_SPACE:
            self._warning("The loaded FCS has changed. Reopen Modify FCS to edit the current model.")
            return
        if self.app._has_any_active_job():
            self._warning("Finish or cancel the active process before applying changes.", "Process Running")
            return
        # Windows buttons need not transfer focus away from a name Entry.
        # Commit a pending inline rename before taking the save snapshot.
        for record in tuple(self._editor_rows.values()):
            variable = record.get("name_var")
            category = record.get("category")
            if variable is not None and variable.get() != category:
                if not self._rename_category(category, variable):
                    return
                break  # refresh replaces the row records; only one entry is edited at a time
        problem = validate_draft(self.categories)
        if problem:
            self._warning(problem)
            return
        try:
            name, target, rows, pending = self._snapshot()
            color_dict = {category: np.asarray(row["positive_prototype"], dtype=float)
                          for category, row in rows.items()}
            options = {
                "_target_model_for_modify": target,
                "_modified_draft": copy.deepcopy(self.categories),
                "_modified_hierarchy": copy.deepcopy(self.hierarchy),
                "_original_model": self.space,
                "_from_modify_fcs": True,
            }
            if self._negative_override is not None:
                native,_=draft_construction_sites(self.categories,self.space,target,review=True)
                if self._sites_signature(native,target)!=self._negative_signature:
                    self._warning('Positive prototypes changed. Reopen Negative prototypes to review the assignments.')
                    return
                options['_modified_negatives']=copy.deepcopy(self._negative_override)
                options['_modified_negative_names']=copy.deepcopy(self._negative_names_override)
            if self.geometry_locked and not draft_preserves_geometry(self.categories, self.space, target):
                self._warning("Imported geometry cannot be reconstructed without the original sites.")
                return
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
            self.status_var.set("Saving changes (rebuilding only if needed)...")

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


def draft_preserves_geometry(draft, source_space, target_model):
    """Match unchanged physical sites and construction groups by original IDs."""
    if target_model != source_space.color_space:
        return False
    original = extract_categories(source_space)
    old_sites = {g["label"]: (cat, g) for cat, data in original.items() for g in data["granules"]}
    seen = set()
    for data in draft.values():
        for g in data["granules"]:
            old = g.get("original_label")
            if old not in old_sites or old in seen or not np.array_equal(g["lab"], old_sites[old][1]["lab"]):
                return False
            if not source_space.disjoint and data.get("source") != old_sites[old][0]:
                return False
            seen.add(old)
    # For independent diagrams a refinement of one original owner is also
    # geometry-preserving: former sibling sites become explicit competitors.
    # The per-site provenance test above excludes merges/moves across owners.
    return seen == set(old_sites)


def reuse_draft_geometry(name, draft, source, hierarchy):
    from Source.geometry.Prototype import Prototype
    from Source.fuzzy.GranularFuzzyColor import GranularFuzzyColor
    from Source.fuzzy.FuzzyColorSpace import FuzzyColorSpace
    old = GranularFuzzyColorSpace.from_flat_space(source)
    records = {p.label: (p, c, s) for p, c, s in zip(old.get_all_prototypes(), old.get_all_cores(), old.get_all_supports())}
    groups = []
    negatives = {}
    for label, data in draft.items():
        parts = [[], [], []]
        for g in data["granules"]:
            for dest, proto in zip(parts, records[g["original_label"]]):
                dest.append(Prototype(g["label"], proto.positive.copy(), voronoi_volume=proto.voronoi_volume))
        groups.append(GranularFuzzyColor(label, *parts))
        if source.disjoint:
            own = {g["original_label"] for g in data["granules"]}
            negatives[label] = [tuple(p[0].positive) for key, p in records.items() if key not in own] + list(source.auxiliary_negatives)
        else:
            owner = data.get("source")
            own = {g["original_label"] for g in data["granules"]}
            previous = next((cat for cat in old.categories if cat.label == owner), None)
            sibling_sites = ([] if previous is None else
                             [tuple(p.positive) for p in previous.prototypes if p.label not in own])
            negatives[label] = list(dict.fromkeys(
                [tuple(p) for p in source.negative_prototypes.get(owner, [])] + sibling_sites))
    kwargs = dict(disjoint=source.disjoint, covering=source.covering, color_space=source.color_space,
                  reference_domain=source.reference_domain, lambda1=source.lambda1, lambda2=source.lambda2,
                  samples=source.samples, negative_prototypes=negatives,
                  auxiliary_negatives=source.auxiliary_negatives, description=source.description)
    if not hierarchy and not isinstance(source, GranularFuzzyColorSpace) and all(
            len(c.prototypes)==1 and c.prototypes[0].label==c.label for c in groups):
        result = FuzzyColorSpace(name, [c.prototypes[0] for c in groups], [c.cores[0] for c in groups],
                                 [c.supports[0] for c in groups], improve_geometry=False, **kwargs)
    else:
        result = GranularFuzzyColorSpace(name, groups, hierarchy=hierarchy,
                     tconorm=getattr(source, "tconorm", "bounded_sum"), **kwargs)
    for attr in ("geometry_only_import", "source_file_format", "import_warnings", "num_aux_negatives_recorded"):
        if hasattr(source, attr): setattr(result, attr, getattr(source, attr))
    return result


def draft_construction_sites(draft, source_space, target_model, *, negative_override=None, review=False):
    """Resolve exact destination positives and category negatives for editing."""
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
    if negative_override is not None:
        negatives = UtilsTools.native_negative_sets(native, negative_override)
    elif not source_space.disjoint:
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
                            if not review:
                                raise ValueError(f"'{category}' refers to a deleted negative granule '{matched}'. Review Negative prototypes.")
                        else:
                            matched_category, converted = by_old_site[matched]
                            if matched_category == category:
                                if review: continue
                                raise ValueError(f"'{category}' cannot use its own granule as a negative.")
                            choices.append(converted)
                            continue
                    # Independent coordinates remain exact in the same model.
                    if target == source_space.color_space:
                        choices.append(source_xyz.copy())
                    else:
                        lab = source_space.lab_from_model(source_xyz)
                        if target == "LAB":
                            choices.append(np.asarray(lab, dtype=float))
                        else:
                            choices.append(lab_to_rgb_model_checked(np.asarray(lab,dtype=float).reshape(1,3))[0])
            if original_category is not None and sum(
                    data.get("source") == original_category for data in draft.values()) > 1:
                old_groups = extract_categories(source_space)
                for g in old_groups.get(original_category, {}).get("granules", []):
                    match = by_old_site.get(g["label"])
                    if match is not None and match[0] != category:
                        choices.append(match[1])
            negatives[category] = choices

    return native, negatives


def converted_negative_names(space, target):
    names = getattr(space, 'negative_names', {})
    if target == space.color_space: return dict(names)
    converted = {}
    for q, label in names.items():
        lab = space.lab_from_model(q)
        point = lab if target == 'LAB' else lab_to_rgb_model_checked(np.asarray(lab,dtype=float).reshape(1,3))[0]
        converted[tuple(float(x) for x in point)] = label
    return converted


def build_model_from_draft(name, draft, source_space, target_model, hierarchy=None, negative_override=None, negative_names_override=None):
    """Build the edited FCS *once* in the requested destination model.

    Positives/real negatives follow their stable original site references;
    negatives not attached to an existing site are converted from the source
    model. Auxiliary sampling is regenerated in the destination domain.
    This also permits valid out-of-sRGB LAB sites when moving RGB -> LAB.
    """
    hierarchy = copy.deepcopy(getattr(source_space, "hierarchy", {}) if hierarchy is None else hierarchy)
    def attach_names(result):
        names = (converted_negative_names(source_space, target_model)
                 if negative_names_override is None else negative_names_override)
        result.negative_names = UtilsTools.filter_negative_names(names,result.negative_prototypes)
        return result
    error = validate_draft(draft)
    if error: raise ValueError(error)
    draft_graph(draft, hierarchy)
    if draft_preserves_geometry(draft, source_space, target_model):
        if negative_override is None:
            return attach_names(reuse_draft_geometry(name, draft, source_space, hierarchy))
        native, previous = draft_construction_sites(draft, source_space, target_model)
        before=UtilsTools.native_negative_sets(native,previous)
        after=UtilsTools.native_negative_sets(native,negative_override)
        if all(set(before[k])==set(after[k]) for k in before):
            return attach_names(reuse_draft_geometry(name,draft,source_space,hierarchy))
    if getattr(source_space, "geometry_only_import", False):
        raise ValueError("Cannot reconstruct geometry-only JSON without original construction sites.")
    from Source.colorspace.ReferenceDomain import ReferenceDomain
    target = str(target_model).upper()
    native, negatives = draft_construction_sites(draft, source_space, target, negative_override=negative_override)
    shared = dict(
        color_space=target,
        reference_domain=(source_space.reference_domain if target == source_space.color_space else ReferenceDomain.for_color_space(target)),
        lambda1=source_space.lambda1,
        lambda2=source_space.lambda2,
        disjoint=source_space.disjoint,
        covering=source_space.covering,
        samples=source_space.samples or 27,
        negative_prototypes=negatives if not source_space.disjoint else None,
        description=getattr(source_space, "description", None),
    )
    keep_atomic = (
        not hierarchy and not isinstance(source_space, GranularFuzzyColorSpace)
        and all(len(sites) == 1 and next(iter(sites)) == category
                for category, sites in native.items())
    )
    if keep_atomic:
        atomic = {category: next(iter(sites.values()))
                  for category, sites in native.items()}
        return attach_names(FuzzyColorSpaceBuilder.build(name, atomic, **shared))
    return attach_names(FuzzyColorSpaceBuilder.build_granular(
        name, native, **shared,
        tconorm=getattr(source_space, "tconorm", "bounded_sum"), hierarchy=hierarchy,
    ))


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
            elif isinstance(value,dict):
                if set(value)!={'native'}:raise ValueError('Invalid native negative prototype.')
                negatives[label].append(np.asarray(value['native'],dtype=float).reshape(3))
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

import os
import platform
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import numpy as np

import Source.interface.modules.UtilsTools as UtilsTools


class PaletteBasedCreationManager:
    """
    Single-window palette-based fuzzy color space creation workspace.

    The default source is the ISCC-NBS Basic palette. Additional .cns
    palettes or representative colors from existing .fcs files can be added
    to the same creation workspace.

    Sources are accumulated locally inside this window. Loading a source here
    does not change the Fuzzy Color Space currently loaded in the main PyFCS
    app. A repeated source name is detected and requires user confirmation;
    colliding color names are automatically disambiguated.
    """

    BG = "#f5f6f8"
    CARD = "#ffffff"
    PANEL = "#fbfbfc"
    SOFT = "#f1f3f6"
    BORDER = "#d9dde3"
    TEXT = "#1f2937"
    MUTED = "#6b7280"
    BLUE = "#1f4e8c"
    BLUE_SOFT = "#e8f0fe"
    GREEN = "#1f5f3a"
    GREEN_SOFT = "#e0f2e9"

    FONT = ("Segoe UI", 9)
    FONT_BOLD = ("Segoe UI", 9, "bold")
    FONT_SMALL = ("Segoe UI", 8)
    FONT_SMALL_BOLD = ("Segoe UI", 8, "bold")
    FONT_SECTION = ("Segoe UI", 10, "bold")

    def __init__(self, app):
        self.app = app
        self.root = app.root

        self.default_source_name = "ISCC-NBS Basic"
        self.default_source_path = UtilsTools.get_resource_path(
            os.path.join(
                "fuzzy_color_spaces",
                "cns",
                "ISCC_NBS_BASIC.cns",
            )
        )

        self.current_source_path = self.default_source_path
        self.current_source_name = self.default_source_name

        # Track imported source names within this creation workspace.
        self.loaded_sources = {}

        # Edits remain local until the user creates a new FCS.
        self.colors = {}
        self.color_checks = {}
        self._row_widgets = {}
        # Commit edits from visible name fields before creating the color space.
        self._name_editors = []

        self.win = tk.Toplevel(self.root)
        self.win.title("Palette-Based Color Space Creation")
        self.win.configure(bg=self.BG)
        self.win.minsize(820, 580)
        self.win.protocol("WM_DELETE_WINDOW", self.close)

        try:
            self.win.transient(self.root)
        except Exception:
            pass

        self._configure_window_size()
        self._create_variables()
        self._load_default_source()
        self._build_ui()
        self._refresh_color_list()

        try:
            self.app._register_creation_window(self.win)
        except Exception:
            pass

        self.win.bind("<Escape>", lambda _e: self.close())
        self.win.focus_set()

    # Window / State
    def _configure_window_size(self):
        """Open the palette workspace as a centered resizable window."""
        width = 920
        height = 680

        try:
            self.win.update_idletasks()
            self.app.center_popup(self.win, width, height)
        except Exception:
            try:
                sw = self.win.winfo_screenwidth()
                sh = self.win.winfo_screenheight()
                x = max(0, (sw - width) // 2)
                y = max(0, (sh - height) // 2)
                self.win.geometry(f"{width}x{height}+{x}+{y}")
            except Exception:
                self.win.geometry(f"{width}x{height}")

    def close(self):
        try:
            if self.win.winfo_exists():
                self.win.destroy()
        except Exception:
            pass

        try:
            self.app._palette_based_creation_controller = None
            self.app._palette_based_creation_window = None
        except Exception:
            pass

    def _create_variables(self):
        self.search_var = tk.StringVar(value="")
        self.selected_count_var = tk.StringVar(value="0 of 0 selected")
        self.visible_count_var = tk.StringVar(value="")
        self.source_name_var = tk.StringVar(value="0 sources loaded")

        # Defer search refreshes until the current Tk key event has completed.
        self._search_refresh_after_id = None
        self.search_var.trace_add("write", self._schedule_search_refresh)

    # Data / Color Sources
    def _load_default_source(self):
        """Load the bundled ISCC-NBS Basic palette as the first source."""
        try:
            loaded = UtilsTools.load_color_data(self.default_source_path)
        except Exception as exc:
            self.app.custom_warning(
                "Palette Error",
                f"The predefined palette could not be loaded:\n{exc}",
                parent=self.win,
            )
            loaded = {}

        self._add_source_colors(
            loaded,
            source_name=self.default_source_name,
            source_path=self.default_source_path,
        )

    @staticmethod
    def _source_key(path):
        """
        Identify a color source from its filename, ignoring extension, case
        and cosmetic separators.

        Examples
        --------
        ISCC_NBS_BASIC.cns  -> isccnbsbasic
        ISCC-NBS-BASIC.fcs  -> isccnbsbasic

        This deliberately avoids comparing the colors contained in the files,
        so the check remains essentially constant-time even for large spaces.
        """
        if not path:
            return None

        filename = os.path.basename(str(path))
        stem, _ext = os.path.splitext(filename)
        return re.sub(r"[\s_\-]+", "", stem).casefold()

    def _make_unique_color_name(self, requested_name, ignore_name=None):
        """
        Return a color name that is unique inside this creation workspace.

        Imported collisions are differentiated automatically:
            Red -> Red (2) -> Red (3) ...

        ``ignore_name`` is used when editing an existing row so keeping its
        current name does not count as a collision.
        """
        base = str(requested_name or "Color").strip() or "Color"
        existing = set(self.colors.keys())
        if ignore_name is not None:
            existing.discard(ignore_name)

        if base not in existing:
            return base

        index = 2
        while f"{base} ({index})" in existing:
            index += 1
        return f"{base} ({index})"

    def _update_source_summary(self):
        """Show a compact count of source loads; per-color origins stay hidden."""
        count = sum(len(entries) for entries in self.loaded_sources.values())
        if count == 1:
            self.source_name_var.set("1 source loaded")
        else:
            self.source_name_var.set(f"{count} sources loaded")

    def _add_source_colors(self, loaded_colors, source_name, source_path=None):
        """
        Add a .cns/.fcs source without deleting colors already in the table.

        Existing selections, custom colors and renamed colors are preserved.
        New imported colors start unselected. If a loaded color has the same
        name as an existing one, it receives a safe unique name such as
        ``Red (2)``. Repeated source names are handled by the caller, which
        asks the user whether the source should be loaded again.

        Returns
        -------
        list[str]
            Names of the colors actually added, in insertion order.
        """
        source_key = self._source_key(source_path)
        additions = []

        # Track reserved names across the entire import.
        existing_names = set(self.colors.keys())

        def reserve_unique_name(requested_name):
            base = str(requested_name or "Color").strip() or "Color"

            if base not in existing_names:
                existing_names.add(base)
                return base

            index = 2
            candidate = f"{base} ({index})"
            while candidate in existing_names:
                index += 1
                candidate = f"{base} ({index})"

            existing_names.add(candidate)
            return candidate

        for raw_name, data in (loaded_colors or {}).items():
            normalized = self._normalize_color_data(data)
            if normalized is None:
                continue

            normalized["custom"] = False
            unique_name = reserve_unique_name(raw_name)
            additions.append((unique_name, normalized))

            self.colors[unique_name] = normalized
            self.color_checks[unique_name] = {
                "var": tk.BooleanVar(value=False),
                "lab": normalized["lab"],
                "rgb": normalized["rgb"],
            }

        if not additions:
            raise ValueError("The selected source does not contain valid colors.")

        if source_key:
            self.loaded_sources.setdefault(source_key, []).append(
                str(source_name or "Color Source")
            )

        self.current_source_name = str(source_name or "Color Source")
        self.current_source_path = source_path
        self._update_source_summary()

        return [name for name, _data in additions]

    def _rename_color(self, old_name, requested_name):
        """
        Rename one table color locally while preserving its position/state.

        This edits only the temporary creation workspace. No source .cns/.fcs
        file and no FCS already loaded in the main application is modified.
        """
        if old_name not in self.colors:
            return old_name

        requested = str(requested_name or "").strip()[:40]
        if not requested:
            return old_name

        new_name = self._make_unique_color_name(requested, ignore_name=old_name)
        if new_name == old_name:
            return old_name

        new_colors = {}
        for name, data in self.colors.items():
            new_colors[new_name if name == old_name else name] = data

        new_checks = {}
        for name, data in self.color_checks.items():
            new_checks[new_name if name == old_name else name] = data

        self.colors = new_colors
        self.color_checks = new_checks
        return new_name

    def _commit_color_name(self, old_name, name_var):
        """Commit an editable row name and redraw only when it actually changed."""
        if old_name not in self.colors:
            return

        requested = name_var.get().strip()
        if not requested:
            name_var.set(old_name)
            return

        new_name = self._rename_color(old_name, requested)
        name_var.set(new_name)

        if new_name != old_name:
            self._refresh_color_list()

    def _normalize_color_data(self, data):
        """Normalize several PyFCS color-data shapes into RGB/LAB/HEX."""
        try:
            rgb = None
            color_hex = None

            if isinstance(data, dict):
                if "positive_prototype" in data:
                    lab_source = data["positive_prototype"]
                elif "lab" in data:
                    lab_source = data["lab"]
                elif "Color" in data:
                    lab_source = data["Color"]
                else:
                    return None

                rgb = data.get("rgb")
                color_hex = data.get("hex")
            else:
                lab_source = data

            if isinstance(lab_source, dict):
                lab = (
                    float(lab_source.get("L", 0.0)),
                    float(lab_source.get("A", lab_source.get("a", 0.0))),
                    float(lab_source.get("B", lab_source.get("b", 0.0))),
                )
            else:
                arr = np.asarray(lab_source, dtype=float).reshape(-1)
                if arr.size < 3:
                    return None
                lab = (float(arr[0]), float(arr[1]), float(arr[2]))

            if rgb is None:
                rgb = UtilsTools.lab_to_rgb(lab)

            rgb = tuple(int(round(float(v))) for v in rgb[:3])
            rgb = tuple(max(0, min(255, v)) for v in rgb)

            if not color_hex:
                color_hex = UtilsTools.rgb_to_hex(rgb)

            color_hex = str(color_hex).upper()
            if not color_hex.startswith("#"):
                color_hex = f"#{color_hex}"

            return {
                "rgb": rgb,
                "lab": lab,
                "hex": color_hex,
                "custom": bool(data.get("custom", False)) if isinstance(data, dict) else False,
            }

        except Exception:
            return None

    def _open_color_source(self):
        """
        Add a .cns or .fcs source to the current creation workspace.

        For .fcs files only representative/positive prototypes are used;
        cores, supports and Voronoi geometry are not imported. This operation
        is fully local and does not change the FCS currently loaded in PyFCS.
        """
        base_path = UtilsTools.get_base_path()
        initial_dir = os.path.join(base_path, "fuzzy_color_spaces")
        if not os.path.isdir(initial_dir):
            initial_dir = base_path

        path = filedialog.askopenfilename(
            title="Add Color Source",
            initialdir=initial_dir,
            parent=self.win,
            filetypes=[
                ("PyFCS Color Sources", "*.cns *.fcs *.CNS *.FCS"),
                ("Color Name System", "*.cns *.CNS"),
                ("Fuzzy Color Space", "*.fcs *.FCS"),
                ("All Files", "*.*"),
            ],
        )

        if not path:
            return

        source_key = self._source_key(path)
        if source_key in self.loaded_sources:
            previous_name = self.loaded_sources[source_key][0]
            load_again = messagebox.askyesno(
                "Color Source Already Loaded",
                f"A color source with this name is already loaded:\n"
                f"'{previous_name}'\n\n"
                f"Do you want to load '{os.path.basename(path)}' again?",
                parent=self.win,
            )

            if not load_again:
                return

        try:
            # Imported colors remain local; the active application FCS is unchanged.
            loaded = self.app.fuzzy_manager.load_color_file(path)
            raw_colors = loaded.get("color_data", {})

            added_names = self._add_source_colors(
                raw_colors,
                source_name=os.path.basename(path),
                source_path=path,
            )
            added_count = len(added_names)

            # Append imported rows directly unless an active search requires a refresh.
            if self.search_var.get().strip():
                self.search_var.set("")
                self.win.after(60, self._scroll_to_bottom)
            else:
                self._append_color_rows(added_names)
                self.win.after_idle(self._scroll_to_bottom)

            self.visible_count_var.set(f"{added_count} colors added")

        except Exception as exc:
            self.app.custom_warning(
                "Color Source Error",
                f"The selected color source could not be loaded:\n{exc}",
                parent=self.win,
            )

    # UI
    def _build_ui(self):
        outer = tk.Frame(self.win, bg=self.BG)
        outer.pack(fill="both", expand=True, padx=14, pady=12)

        self._build_header(outer)
        self._build_controls(outer)
        self._build_color_list(outer)
        self._build_footer(outer)

    def _build_header(self, parent):
        header = tk.Frame(parent, bg=self.CARD, bd=1, relief="solid")
        header.pack(fill="x")

        inner = tk.Frame(header, bg=self.CARD)
        inner.pack(fill="x", padx=14, pady=9)

        title_area = tk.Frame(inner, bg=self.CARD)
        title_area.pack(side="left", fill="x", expand=True)

        tk.Label(
            title_area,
            text="Palette-Based Color Space Creation",
            font=("Segoe UI", 14, "bold"),
            bg=self.CARD,
            fg=self.TEXT,
            anchor="w",
        ).pack(anchor="w")

        source_row = tk.Frame(title_area, bg=self.CARD)
        source_row.pack(anchor="w", pady=(2, 0))

        tk.Label(
            source_row,
            text="Sources:",
            font=self.FONT_SMALL_BOLD,
            bg=self.CARD,
            fg=self.TEXT,
        ).pack(side="left")

        tk.Label(
            source_row,
            textvariable=self.source_name_var,
            font=self.FONT_SMALL_BOLD,
            bg=self.CARD,
            fg=self.BLUE,
        ).pack(side="left", padx=(4, 0))

        tk.Label(
            inner,
            text="Build FCS from selected colors",
            font=self.FONT_SMALL,
            bg=self.CARD,
            fg=self.MUTED,
        ).pack(side="right", padx=(16, 2))

    def _build_controls(self, parent):
        card = tk.Frame(parent, bg=self.CARD, bd=1, relief="solid")
        card.pack(fill="x", pady=(10, 8))

        top = tk.Frame(card, bg=self.CARD)
        top.pack(fill="x", padx=12, pady=(10, 7))

        tk.Label(
            top,
            text="Search:",
            font=self.FONT_BOLD,
            bg=self.CARD,
            fg=self.TEXT,
        ).pack(side="left")

        search_entry = tk.Entry(
            top,
            textvariable=self.search_var,
            font=self.FONT,
            relief="solid",
            bd=1,
            width=30,
        )
        search_entry.pack(side="left", fill="x", expand=True, padx=(8, 6))

        tk.Button(
            top,
            text="Clear",
            command=lambda: self.search_var.set(""),
            font=self.FONT_SMALL,
            relief="solid",
            bd=1,
            padx=8,
            pady=2,
            cursor="hand2",
        ).pack(side="left")

        bottom = tk.Frame(card, bg=self.CARD)
        bottom.pack(fill="x", padx=12, pady=(0, 10))

        tk.Button(
            bottom,
            text="Select All",
            command=self._select_all_colors,
            font=self.FONT,
            relief="solid",
            bd=1,
            padx=10,
            pady=3,
            cursor="hand2",
        ).pack(side="left")

        tk.Button(
            bottom,
            text="Deselect All",
            command=self._deselect_all_colors,
            font=self.FONT,
            relief="solid",
            bd=1,
            padx=10,
            pady=3,
            cursor="hand2",
        ).pack(side="left", padx=(6, 0))

        tk.Label(
            bottom,
            textvariable=self.visible_count_var,
            font=self.FONT_SMALL,
            bg=self.CARD,
            fg=self.MUTED,
        ).pack(side="right", padx=(12, 0))

        tk.Label(
            bottom,
            textvariable=self.selected_count_var,
            font=self.FONT_BOLD,
            bg=self.CARD,
            fg=self.BLUE,
        ).pack(side="right")

    def _configure_table_columns(self, widget):
        """Keep the table columns aligned in the header and every color row."""
        widget.columnconfigure(0, weight=1, minsize=270)
        widget.columnconfigure(1, weight=0, minsize=150)
        widget.columnconfigure(2, weight=0, minsize=105)
        widget.columnconfigure(3, weight=0, minsize=215)

    def _build_color_list(self, parent):
        card = tk.LabelFrame(
            parent,
            text=" Available Colors ",
            font=self.FONT_SECTION,
            bg=self.CARD,
            fg=self.TEXT,
            bd=1,
            relief="solid",
            padx=8,
            pady=8,
            labelanchor="nw",
        )
        card.pack(fill="both", expand=True)

        header = tk.Frame(card, bg=self.SOFT, height=30)
        header.pack(fill="x")
        header.pack_propagate(False)
        self._configure_table_columns(header)

        tk.Label(
            header,
            text="Color",
            font=self.FONT_SMALL_BOLD,
            bg=self.SOFT,
            fg=self.TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="nsew", padx=(14, 8))

        tk.Label(
            header,
            text="RGB",
            font=self.FONT_SMALL_BOLD,
            bg=self.SOFT,
            fg=self.MUTED,
            anchor="center",
        ).grid(row=0, column=1, sticky="nsew", padx=6)

        tk.Label(
            header,
            text="HEX",
            font=self.FONT_SMALL_BOLD,
            bg=self.SOFT,
            fg=self.MUTED,
            anchor="center",
        ).grid(row=0, column=2, sticky="nsew", padx=6)

        tk.Label(
            header,
            text="LAB",
            font=self.FONT_SMALL_BOLD,
            bg=self.SOFT,
            fg=self.MUTED,
            anchor="e",
        ).grid(row=0, column=3, sticky="nsew", padx=(6, 14))

        holder = tk.Frame(card, bg=self.CARD)
        holder.pack(fill="both", expand=True, pady=(5, 0))

        self.colors_canvas = tk.Canvas(
            holder,
            bg=self.CARD,
            highlightthickness=0,
            bd=0,
        )
        scrollbar = ttk.Scrollbar(
            holder,
            orient="vertical",
            command=self.colors_canvas.yview,
        )
        self.colors_canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        self.colors_canvas.pack(side="left", fill="both", expand=True)

        self.colors_inner = tk.Frame(self.colors_canvas, bg=self.CARD)
        self.colors_window_id = self.colors_canvas.create_window(
            (0, 0),
            window=self.colors_inner,
            anchor="nw",
        )

        self.colors_inner.bind(
            "<Configure>",
            lambda _e: self.colors_canvas.configure(
                scrollregion=self.colors_canvas.bbox("all")
            ),
        )
        self.colors_canvas.bind(
            "<Configure>",
            lambda e: self.colors_canvas.itemconfigure(
                self.colors_window_id,
                width=max(1, e.width - 3),
            ),
        )

        self.win.bind("<MouseWheel>", self._dispatch_colors_mousewheel, add="+")
        self.win.bind("<Button-4>", self._dispatch_colors_mousewheel, add="+")
        self.win.bind("<Button-5>", self._dispatch_colors_mousewheel, add="+")

    def _build_footer(self, parent):
        footer = tk.Frame(parent, bg=self.BG)
        footer.pack(fill="x", pady=(10, 0))

        tk.Button(
            footer,
            text="+ Add Custom Color",
            command=self._add_custom_color,
            font=self.FONT_BOLD,
            bg="#f8fafc",
            fg=self.TEXT,
            activebackground="#eef2f7",
            relief="solid",
            bd=1,
            padx=12,
            pady=6,
            cursor="hand2",
        ).pack(side="left")

        tk.Button(
            footer,
            text="+ Add Color Source...",
            command=self._open_color_source,
            font=self.FONT_BOLD,
            bg="#f8fafc",
            fg=self.TEXT,
            activebackground="#eef2f7",
            relief="solid",
            bd=1,
            padx=12,
            pady=6,
            cursor="hand2",
        ).pack(side="left", padx=(8, 0))

        tk.Button(
            footer,
            text="Create Color Space",
            command=self._create_color_space,
            font=self.FONT_BOLD,
            bg=self.BLUE_SOFT,
            fg=self.BLUE,
            activebackground="#d7e5fb",
            activeforeground=self.BLUE,
            relief="solid",
            bd=1,
            padx=16,
            pady=6,
            cursor="hand2",
        ).pack(side="right")

    # Color List / Search / Selection
    def _schedule_search_refresh(self, *_args):
        """Refresh the filtered table safely after the current Tk event."""
        if not hasattr(self, "win"):
            return

        previous = getattr(self, "_search_refresh_after_id", None)
        if previous is not None:
            try:
                self.win.after_cancel(previous)
            except Exception:
                pass

        try:
            self._search_refresh_after_id = self.win.after(35, self._apply_search_refresh)
        except Exception:
            self._search_refresh_after_id = None

    def _apply_search_refresh(self):
        self._search_refresh_after_id = None
        try:
            if self.win.winfo_exists():
                self._refresh_color_list()
                self._scroll_to_top()
        except Exception:
            pass

    @staticmethod
    def _search_tokens(value):
        """Normalize free-form search text into case-insensitive tokens."""
        value = str(value or "").lower().strip()
        if not value:
            return []

        # Treat punctuation normally used in RGB/LAB triples as separators, so
        # searches such as "255 0 0" and "255, 0, 0" behave identically.
        value = re.sub(r"[,;:/\\|()\[\]{}]+", " ", value)
        return [token for token in value.split() if token]

    def _matches_search(self, name):
        query_tokens = self._search_tokens(self.search_var.get())
        if not query_tokens:
            return True

        data = self.colors.get(name, {})

        rgb = data.get("rgb", ())
        try:
            rgb_values = [str(int(round(float(v)))) for v in list(rgb)[:3]]
        except Exception:
            rgb_values = []

        lab = data.get("lab", ())
        try:
            lab_values = [f"{float(v):.2f}" for v in list(lab)[:3]]
        except Exception:
            lab_values = []

        color_hex = str(data.get("hex", "") or "").lower()
        hex_without_hash = color_hex.lstrip("#")

        searchable = " ".join(
            [
                str(name).lower(),
                color_hex,
                hex_without_hash,
                " ".join(rgb_values),
                " ".join(lab_values),
            ]
        )

        # All written tokens must be present. This makes multi-part searches
        # useful without requiring exact punctuation or spacing.
        return all(token in searchable for token in query_tokens)

    def _create_color_row(self, name, index):
        """Create one visible color row and register its editable-name state."""
        if name not in self.colors or name not in self.color_checks:
            return None

        data = self.colors[name]
        check_data = self.color_checks[name]

        row_bg = self.CARD if index % 2 == 0 else "#fbfcfd"
        row = tk.Frame(self.colors_inner, bg=row_bg, bd=0)
        row.pack(fill="x", padx=3, pady=1)
        self._configure_table_columns(row)

        # Color column: checkbox + swatch + name
        color_cell = tk.Frame(row, bg=row_bg)
        color_cell.grid(row=0, column=0, sticky="nsew", padx=(4, 8))

        check = tk.Checkbutton(
            color_cell,
            variable=check_data["var"],
            bg=row_bg,
            activebackground=row_bg,
            selectcolor=row_bg,
            command=self._update_counts,
            cursor="hand2",
            bd=0,
            highlightthickness=0,
        )
        check.pack(side="left", padx=(0, 5), pady=5)

        swatch = tk.Canvas(
            color_cell,
            width=28,
            height=28,
            bg=row_bg,
            highlightthickness=0,
            bd=0,
        )
        swatch.pack(side="left", padx=(0, 9), pady=4)
        swatch.create_rectangle(
            2,
            2,
            26,
            26,
            fill=data["hex"],
            outline="#707070",
        )

        name_frame = tk.Frame(color_cell, bg=row_bg)
        name_frame.pack(side="left", fill="x", expand=True)

        name_var = tk.StringVar(value=name)
        name_entry = tk.Entry(
            name_frame,
            textvariable=name_var,
            font=self.FONT_BOLD,
            bg="#ffffff",
            fg=self.TEXT,
            relief="solid",
            bd=1,
            highlightthickness=0,
        )
        name_entry.pack(fill="x")

        name_entry.bind(
            "<Return>",
            lambda _e, old=name, var=name_var: self._commit_color_name(old, var),
        )
        name_entry.bind(
            "<FocusOut>",
            lambda _e, old=name, var=name_var: self._commit_color_name(old, var),
        )
        self._name_editors.append((name, name_var))

        if data.get("custom"):
            tk.Label(
                name_frame,
                text="Custom color",
                font=self.FONT_SMALL,
                bg=row_bg,
                fg=self.BLUE,
                anchor="w",
            ).pack(fill="x", pady=(1, 0))

        # RGB / HEX / LAB columns
        rgb = data["rgb"]
        tk.Label(
            row,
            text=f"{rgb[0]}, {rgb[1]}, {rgb[2]}",
            font=self.FONT,
            bg=row_bg,
            fg=self.MUTED,
            anchor="center",
        ).grid(row=0, column=1, sticky="nsew", padx=6)

        tk.Label(
            row,
            text=data["hex"],
            font=self.FONT,
            bg=row_bg,
            fg=self.MUTED,
            anchor="center",
        ).grid(row=0, column=2, sticky="nsew", padx=6)

        lab = data["lab"]
        tk.Label(
            row,
            text=f"{lab[0]:.2f}, {lab[1]:.2f}, {lab[2]:.2f}",
            font=self.FONT,
            bg=row_bg,
            fg=self.MUTED,
            anchor="e",
        ).grid(row=0, column=3, sticky="nsew", padx=(6, 12))

        self._row_widgets[name] = row
        return row

    def _append_color_rows(self, names):
        """
        Append only newly added visible colors.

        This avoids destroying and rebuilding the complete Tk table after
        adding a custom color or importing another palette/FCS source.
        """
        if not hasattr(self, "colors_inner"):
            return

        names = [
            name
            for name in names
            if name in self.colors
            and name not in self._row_widgets
            and self._matches_search(name)
        ]

        if not names:
            self._update_counts(visible=len(self._row_widgets))
            return

        # Remove the empty-state row before appending a color.
        if not self._row_widgets:
            for child in self.colors_inner.winfo_children():
                child.destroy()
            self._name_editors = []

        start_index = len(self._row_widgets)
        for offset, name in enumerate(names):
            self._create_color_row(name, start_index + offset)

        self._update_counts(visible=len(self._row_widgets))

    def _refresh_color_list(self):
        """
        Fully rebuild the visible list.

        Full rebuilds are kept for operations that genuinely change the whole
        view, such as search filtering or renaming. Normal additions use
        _append_color_rows() instead.
        """
        if not hasattr(self, "colors_inner"):
            return

        for child in self.colors_inner.winfo_children():
            child.destroy()

        self._row_widgets = {}
        self._name_editors = []
        visible_names = [name for name in self.colors if self._matches_search(name)]

        if not visible_names:
            tk.Label(
                self.colors_inner,
                text="No colors match the current search.",
                bg=self.CARD,
                fg=self.MUTED,
                font=self.FONT,
                pady=24,
            ).pack(fill="x")
            self._update_counts(visible=0)
            return

        for index, name in enumerate(visible_names):
            self._create_color_row(name, index)

        self._update_counts(visible=len(visible_names))

    def _update_counts(self, visible=None):
        total = len(self.color_checks)
        selected = 0

        for item in self.color_checks.values():
            try:
                if item["var"].get():
                    selected += 1
            except Exception:
                pass

        self.selected_count_var.set(f"{selected} of {total} selected")

        if visible is None:
            visible = sum(1 for name in self.colors if self._matches_search(name))

        query = self.search_var.get().strip()
        if query:
            self.visible_count_var.set(f"{visible} shown")
        else:
            self.visible_count_var.set("")

    def _select_all_colors(self):
        for item in self.color_checks.values():
            try:
                item["var"].set(True)
            except Exception:
                pass
        self._update_counts()

    def _deselect_all_colors(self):
        for item in self.color_checks.values():
            try:
                item["var"].set(False)
            except Exception:
                pass
        self._update_counts()

    # Custom Color / Create
    def _next_unique_name(self, base):
        return self._make_unique_color_name(base)

    def _add_custom_color(self):
        default_name = self._next_unique_name("Custom Color")

        def on_submit(color_name, sample_lab, sample_rgb, sample_hex, dialog, input_vars):
            clean_name = str(color_name).strip()[:UtilsTools.MAX_COLOR_NAME_CHARS]

            if not clean_name:
                input_vars["status_var"].set("Enter a color name.")
                return

            clean_name = self._make_unique_color_name(clean_name)

            lab_arr = np.asarray(sample_lab, dtype=float).reshape(-1)
            lab = (float(lab_arr[0]), float(lab_arr[1]), float(lab_arr[2]))
            rgb = tuple(int(v) for v in sample_rgb[:3])
            color_hex = str(sample_hex).upper()

            self.colors[clean_name] = {
                "rgb": rgb,
                "lab": lab,
                "hex": color_hex,
                "custom": True,
            }
            self.color_checks[clean_name] = {
                "var": tk.BooleanVar(value=True),
                "lab": lab,
                "rgb": rgb,
            }

            dialog.destroy()

            # Clear the search if it would hide the new color; otherwise append its row.
            if self.search_var.get().strip() and not self._matches_search(clean_name):
                self.search_var.set("")
                self.win.after(60, self._scroll_to_bottom)
            else:
                self._append_color_rows([clean_name])
                self.win.after_idle(self._scroll_to_bottom)

        self.app._open_custom_color_dialog(
            parent=self.win,
            title="Add Custom Color",
            subtitle="Create a palette color from RGB, LAB or HEX",
            submit_text="Add Color",
            require_name=True,
            default_name=default_name,
            on_submit=on_submit,
        )

    def _commit_pending_color_names(self):
        """Commit every visible name editor before validation/creation."""
        pending = list(getattr(self, "_name_editors", []))
        changed = False

        for old_name, name_var in pending:
            if old_name not in self.colors:
                continue

            requested = name_var.get().strip()
            if not requested:
                name_var.set(old_name)
                continue

            new_name = self._rename_color(old_name, requested)
            if new_name != old_name:
                changed = True

        if changed:
            self._refresh_color_list()

    def _create_color_space(self):
        # Save pending name edits before passing colors to FCS creation.
        self._commit_pending_color_names()

        selected = 0
        for item in self.color_checks.values():
            try:
                if item["var"].get():
                    selected += 1
            except Exception:
                pass

        if selected < 2:
            self.app.custom_warning(
                "Not Enough Colors",
                "At least two colors must be selected to create the Color Space.",
                parent=self.win,
            )
            return

        previous_checks = getattr(self.app, "color_checks", None)
        self.app.color_checks = self.color_checks

        try:
            result = self.app.create_color_space(parent=self.win)
        finally:
            if previous_checks is None:
                try:
                    delattr(self.app, "color_checks")
                except Exception:
                    pass
            else:
                self.app.color_checks = previous_checks

        if result:
            self.close()

    def _scroll_to_top(self):
        try:
            self.colors_canvas.update_idletasks()
            self.colors_canvas.yview_moveto(0.0)
        except Exception:
            pass

    def _scroll_to_bottom(self):
        try:
            self.colors_canvas.update_idletasks()
            self.colors_canvas.yview_moveto(1.0)
        except Exception:
            pass

    # Mouse Wheel
    def _dispatch_colors_mousewheel(self, event):
        """Scroll the colors list only when the pointer is over that canvas."""
        try:
            px = self.win.winfo_pointerx()
            py = self.win.winfo_pointery()
            x0 = self.colors_canvas.winfo_rootx()
            y0 = self.colors_canvas.winfo_rooty()
            x1 = x0 + self.colors_canvas.winfo_width()
            y1 = y0 + self.colors_canvas.winfo_height()
            if not (x0 <= px < x1 and y0 <= py < y1):
                return None
        except Exception:
            return None

        if getattr(event, "num", None) == 4:
            return self._on_linux_scroll_up(event)
        if getattr(event, "num", None) == 5:
            return self._on_linux_scroll_down(event)
        return self._on_mousewheel(event)

    def _on_mousewheel(self, event):
        try:
            if platform.system() == "Darwin":
                step = -1 if event.delta > 0 else 1
            else:
                step = int(-1 * (event.delta / 120))
                if step == 0:
                    step = -1 if event.delta > 0 else 1
            self.colors_canvas.yview_scroll(step, "units")
        except Exception:
            pass
        return "break"

    def _on_linux_scroll_up(self, _event):
        self.colors_canvas.yview_scroll(-1, "units")
        return "break"

    def _on_linux_scroll_down(self, _event):
        self.colors_canvas.yview_scroll(1, "units")
        return "break"

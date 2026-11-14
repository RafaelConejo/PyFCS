import os
import platform
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import numpy as np

from Source.geometry.Voronoi import Voronoi
from Source.fuzzy.FuzzyColorSpaceBuilder import lab_to_rgb_model_checked
from Source.interface.modules.GranuleManager import GranuleManager
import Source.interface.modules.UtilsTools as UtilsTools


class PaletteBasedCreationManager:
    """
    Single-window palette-based fuzzy color space creation workspace.

    Each palette row is a category with one or more positive granules. Atomic
    palettes still use the existing creation path; multiple granules activate
    the granular builder without changing the shared creation dialog.

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
    BLUE = UtilsTools.UI_ACCENT
    BLUE_SOFT = UtilsTools.UI_ACCENT_SOFT
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
        self._row_details = {}
        self._expanded_categories = set()
        # Commit edits from visible name fields before creating the color space.
        self._name_editors = []
        # Avoid reentrant Return/FocusOut commits while a warning is modal.
        self._granule_name_commits_in_progress = set()
        # A modal warning must not trigger the same removal twice.
        self._removing_categories = False

        self.win = tk.Toplevel(self.root)
        self.win.withdraw()
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
        self.win.deiconify()
        self.win.focus_set()

    # Window / State
    def _configure_window_size(self):
        """Center over PyFCS, then raise slightly for a balanced position."""
        width, height = 960, 680
        try:
            self.win.update_idletasks()
            self.app.center_popup(self.win, width, height)
            geometry = self.win.geometry()
            match = re.fullmatch(r"\d+x\d+([+-]\d+)([+-]\d+)", geometry)
            if match:
                x, y = int(match.group(1)), int(match.group(2))
                self.win.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y - 50)}")
        except Exception:
            sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
            x = max(0, (sw - width) // 2)
            y = max(0, (sh - height) // 2 - 50)
            self.win.geometry(f"{width}x{height}+{x}+{y}")

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
        """Allocate a unique category name within the 20-character UI limit."""
        existing = set(self.colors)
        if ignore_name is not None:
            existing.discard(ignore_name)
        return UtilsTools.unique_import_label(
            requested_name, existing, UtilsTools.MAX_CATEGORY_NAME_CHARS)

    def _used_granule_labels(self, excluding_category=None):
        return {
            granule["label"]
            for category, data in self.colors.items() if category != excluding_category
            for granule in data.get("granules", [])
        }

    @staticmethod
    def _reserve_granule_label(requested, used):
        """Reserve a unique granule name of at most 24 characters."""
        name = UtilsTools.unique_import_label(
            requested, used, UtilsTools.MAX_COLOR_NAME_CHARS)
        used.add(name)
        return name

    @staticmethod
    def _auto_granule_label(category, index):
        suffix = f"-g{index + 1}"
        return f"{category[:UtilsTools.MAX_COLOR_NAME_CHARS - len(suffix)]}{suffix}"

    def _granule_display_label(self, category, granule, index):
        # Show the actual prototype label. A category named "Pink" starts
        # with granule "Pink"; extra granules become "Pink-g2", etc.
        return granule["label"]

    def _sync_representative(self, category):
        """Show the first *included* prototype where possible."""
        data = self.colors[category]
        granules = data.get("granules", [])
        if not granules:
            return
        enabled = next((g for g in granules if g.get("enabled", True)), granules[0])
        lab = tuple(enabled["lab"])
        rgb = tuple(max(0, min(255, int(round(float(v)))))
                    for v in UtilsTools.lab_to_rgb(lab))
        data.update(lab=lab, rgb=rgb, hex=UtilsTools.rgb_to_hex(rgb).upper())
        data.pop("_search_key_cache", None)
        check = self.color_checks[category]
        check.update(lab=lab, rgb=rgb)

    def _set_category_granules(self, category, entries):
        """Validate first, then commit an edit without raising on user mistakes.

        Returns ``(success, error_message)``. Imported palettes may contain
        coincident LAB sites in *different* categories; those unchanged sites
        are allowed to remain editable. New/modified sites must not introduce
        duplicates. Final Create Color Space checks all selected sites.
        """
        if category not in self.colors or not entries:
            return False, "A palette category must contain at least one granule."

        prior = self.colors[category].get("granules", [])
        old_flags = {g["label"]: g.get("enabled", True) for g in prior}
        prior_coordinates = {
            tuple(float(v) for v in g["lab"])
            for g in prior
        }
        external = [
            (other, g["label"], g["lab"])
            for other, data in self.colors.items() if other != category
            for g in data.get("granules", [])
        ]
        other_names = {g[1] for g in external}
        local_occupied = []
        validated = []

        for entry in entries:
            if not isinstance(entry, dict):
                return False, "Invalid granule data."
            # Always enforce valid color coordinates and no duplicate sites
            # within the edited category, even when other palettes have
            # deliberately been imported with overlapping prototypes.
            label, point, error = UtilsTools.check_granule_site(
                entry.get("label"), entry.get("lab"), local_occupied,
                max_name_length=64,  # Previously imported identifiers.
            )
            if error:
                return False, error
            if label in other_names:
                return False, f"Granule name '{label}' is already in use."

            # A candidate imported from another source can share its LAB with
            # another category. Do not invalidate it when editing *elsewhere*.
            # But prevent a new/changed granule from introducing that overlap.
            if point not in prior_coordinates:
                _, _, error = UtilsTools.check_granule_site(
                    label, point, external, max_name_length=64,
                )
                if error:
                    return False, error

            local_occupied.append((category, label, point))
            validated.append({
                "label": label,
                "lab": point,
                "enabled": bool(entry.get("enabled", old_flags.get(label, True))),
            })

        # Nothing is changed until the full validation succeeds.
        data = self.colors[category]
        data["granules"] = validated
        data.pop("_search_key_cache", None)
        if not any(g["enabled"] for g in validated):
            self.color_checks[category]["var"].set(False)
        self._sync_representative(category)
        self._expanded_categories.add(category)
        self._rebuild_category_granules(category)
        self._refresh_category_summary(category)
        self._update_selection_counter()
        return True, None

    def _open_granules(self, row_data):
        # Resolve by identity: a category may have been renamed by the user.
        for label, data in self.colors.items():
            if data is row_data:
                GranuleManager(self, label).add()
                return

    def _update_selection_counter(self):
        if hasattr(self, "selected_count_var") and hasattr(self, "search_var"):
            self._update_counts(visible=len(getattr(self, "_row_widgets", {})))

    def _on_category_toggle(self, category):
        """Update one category without recreating any table rows."""
        check = self.color_checks[category]["var"]
        if check.get():
            for granule in self.colors[category]["granules"]:
                granule["enabled"] = True
        self._sync_representative(category)
        self._refresh_category_controls(category)
        self._refresh_category_summary(category)
        self._update_selection_counter()

    def _on_granule_toggle(self, category, index, enabled):
        """Include/exclude a site and update only its parent row in place."""
        granules = self.colors[category]["granules"]
        if not 0 <= index < len(granules):
            return
        if enabled and not self.color_checks[category]["var"].get():
            # An unchecked category can be enabled using just one child.
            for child in granules:
                child["enabled"] = False
        granules[index]["enabled"] = bool(enabled)
        self.color_checks[category]["var"].set(any(g.get("enabled", True) for g in granules))
        self._sync_representative(category)
        self._refresh_category_controls(category)
        self._refresh_category_summary(category)
        self._update_selection_counter()

    def _refresh_category_controls(self, category):
        info = self._row_details.get(category)
        if not info:
            return
        checked = bool(self.color_checks[category]["var"].get())
        for index, var in info.get("granule_vars", []):
            if index < len(self.colors[category]["granules"]):
                var.set(checked and self.colors[category]["granules"][index].get("enabled", True))
        self._refresh_category_caption(category)

    def _refresh_category_caption(self, category):
        info = self._row_details.get(category)
        if not info:
            return
        total = len(self.colors[category]["granules"])
        checked = self.color_checks[category]["var"].get()
        active = sum(bool(g.get("enabled", True)) for g in self.colors[category]["granules"]) if checked else 0
        if total > 1:
            count_text = f"{active}/{total} granules"
        else:
            count_text = "1 granule"
        expanded = category in self._expanded_categories
        # The category may acquire its second granule after the row was built:
        # update its badge styling without recreating the entire table.
        multiple = total > 1
        info["button"].configure(
            text=count_text,
            bg=self.BLUE_SOFT if multiple else self.SOFT,
            fg=self.BLUE if multiple else self.MUTED,
            activebackground=self.BLUE_SOFT if multiple else self.SOFT,
            activeforeground=self.BLUE if multiple else self.MUTED,
        )
        swatch = info.get("swatch")
        if swatch:
            canvas, _rectangle, arrow = swatch
            canvas.itemconfigure(arrow, state="normal" if expanded else "hidden")

    def _refresh_category_summary(self, category):
        """Hide duplicate representative values while the granules are visible."""
        info = self._row_details.get(category)
        if not info or "summary" not in info:
            return
        expanded = category in self._expanded_categories
        data = self.colors[category]
        rgb = data["rgb"]
        lab = data["lab"]
        values = {
            "rgb": f"{rgb[0]}, {rgb[1]}, {rgb[2]}",
            "hex": data["hex"],
            "lab": f"{lab[0]:.2f}, {lab[1]:.2f}, {lab[2]:.2f}",
        }
        for key, label in info["summary"].items():
            label.configure(text="" if expanded else values[key])
        swatch = info.get("swatch")
        if swatch:
            canvas, rectangle, _arrow = swatch
            canvas.itemconfigure(rectangle, state="hidden" if expanded else "normal",
                                  fill=data["hex"])

    def _rebuild_category_granules(self, category):
        """Replace at most one expanded subsection after adding/editing a site."""
        info = self._row_details.get(category)
        if not info:
            return
        self._suspend_granule_name_commit = True
        try:
            panel = info.get("panel")
            if panel is not None:
                panel.destroy()
            info["panel"] = None
            info["granule_vars"] = []
            info["granule_name_vars"] = []
            if category in self._expanded_categories:
                panel = self._create_granule_breakdown(info["wrapper"], category,
                                                       self.colors[category])
                info["panel"] = panel
                panel.pack(fill="x", pady=(0, 3))
            self._refresh_category_caption(category)
        finally:
            self._suspend_granule_name_commit = False

    def _commit_granule_name(self, category, index, variable):
        """Commit one inline edit once, even if Return also triggers FocusOut.

        A modal warning takes focus away from the entry. Without this guard,
        that nested FocusOut event can show the same warning a second time.
        """
        if getattr(self, "_suspend_granule_name_commit", False):
            return True
        granules = self.colors.get(category, {}).get("granules", [])
        if not 0 <= index < len(granules):
            return False

        current_name = self._granule_display_label(category, granules[index], index)
        requested = variable.get().strip()
        if requested == current_name:
            return True

        pending = self._granule_name_commits_in_progress
        key = id(variable)
        if key in pending:
            return False
        pending.add(key)
        try:
            # Keep the original name visible before a modal warning steals
            # focus; subsequent FocusOut events now find an unchanged value.
            variable.set(current_name)
            manager = GranuleManager(self, category)
            display = manager.rename(index, requested)
            variable.set(display)
            return display == requested
        except (ValueError, TypeError) as exc:
            variable.set(current_name)
            self.app.custom_warning(
                "Invalid Granule Name", str(exc), parent=self.win)
            return False
        finally:
            pending.discard(key)

    def _update_source_summary(self):
        """Show a compact count of source loads; per-color origins stay hidden."""
        count = sum(len(entries) for entries in self.loaded_sources.values())
        if count == 1:
            self.source_name_var.set("1 source loaded")
        else:
            self.source_name_var.set(f"{count} sources loaded")

    def _add_source_colors(self, loaded_colors, source_name, source_path=None):
        """Import validated palette categories without touching existing rows.

        Only new source entries receive shortened/suffixed names. Importing
        coincident LAB candidates is allowed; Create Color Space checks the
        final selected sites. A batch is staged before modifying table state.
        """
        source_key = self._source_key(source_path)
        used_categories = set(self.colors)
        used_granules = self._used_granule_labels()
        additions = []
        for raw_name, data in (loaded_colors or {}).items():
            normalized = self._normalize_color_data(data)
            if normalized is None:
                continue
            requested = str(raw_name or "Color").strip() or "Color"
            category = UtilsTools.unique_import_label(
                requested, used_categories, UtilsTools.MAX_CATEGORY_NAME_CHARS)
            used_categories.add(category)
            original_granules = normalized["granules"]
            imported = []
            for index, item in enumerate(original_granules):
                raw_label = str(item.get("label") or "").strip()
                if not raw_label or (index == 0 and raw_label == requested):
                    raw_label = category
                elif raw_label.startswith(requested + "-g") and raw_label[len(requested)+2:].isdigit():
                    # Preserve the automatic granule's number under a suffixed
                    # category name, even if the category stem was shortened.
                    suffix = raw_label[len(requested):]
                    raw_label = category[:max(1, UtilsTools.MAX_COLOR_NAME_CHARS-len(suffix))] + suffix
                label = self._reserve_granule_label(raw_label, used_granules)
                imported.append({"label": label, "lab": item["lab"], "enabled": True})
            normalized["custom"] = False
            normalized["granules"] = imported
            additions.append((category, normalized))

        if not additions:
            raise ValueError("The selected source does not contain valid colors.")

        # All normalization/naming work is complete; only now commit the batch.
        for category, normalized in additions:
            self.colors[category] = normalized
            self.color_checks[category] = {
                "var": tk.BooleanVar(master=self.win, value=False),
                "lab": normalized["lab"],
                "rgb": normalized["rgb"],
            }
        if source_key:
            self.loaded_sources.setdefault(source_key, []).append(
                str(source_name or "Color Source"))
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

        requested = str(requested_name or "").strip()
        if not requested or len(requested) > UtilsTools.MAX_CATEGORY_NAME_CHARS:
            return old_name

        new_name = self._make_unique_color_name(requested, ignore_name=old_name)
        if len(new_name) > UtilsTools.MAX_CATEGORY_NAME_CHARS:
            # Reject rather than silently truncate or create colliding IDs.
            return old_name
        if new_name == old_name:
            return old_name

        original = self.colors[old_name]
        original.pop("_search_key_cache", None)
        granules = original.get("granules", [])
        # Reserve manually named granules before assigning automatic names,
        # so renaming a category can never silently duplicate a sibling label.
        # A removed granule can leave gaps (Pink, Pink-g2, Pink-g4).
        # Recognize the numeric suffix rather than assuming index + 1.
        auto_suffixes = []
        for i, g in enumerate(granules):
            label = g["label"]
            suffix = label[len(old_name) + 2:] if label.startswith(old_name + "-g") else ""
            if i == 0 and label == old_name:
                auto_suffixes.append(0)
            elif suffix.isdigit() and int(suffix) >= 1:
                auto_suffixes.append(int(suffix))
            else:
                auto_suffixes.append(None)
        reserved = self._used_granule_labels(excluding_category=old_name)
        reserved.update(g["label"] for g, suffix in zip(granules, auto_suffixes)
                        if suffix is None)
        for granule, suffix in zip(granules, auto_suffixes):
            if suffix is not None:
                requested_label = (new_name if suffix == 0 else
                                   self._auto_granule_label(new_name, suffix - 1))
                granule["label"] = self._reserve_granule_label(
                    requested_label, reserved)

        new_colors = {}
        for name, data in self.colors.items():
            new_colors[new_name if name == old_name else name] = data

        new_checks = {}
        for name, data in self.color_checks.items():
            new_checks[new_name if name == old_name else name] = data

        self.colors = new_colors
        self.color_checks = new_checks
        if old_name in self._expanded_categories:
            self._expanded_categories.remove(old_name)
            self._expanded_categories.add(new_name)
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

            # The JSON reader supplies a full list for granular categories.
            # Legacy CNS/FCS colors simply become a one-granule category.
            raw_granules = data.get("granules") if isinstance(data, dict) else None
            parsed = []
            if raw_granules:
                for granule in raw_granules:
                    coords = np.asarray(granule.get("prototype", granule.get("lab")),
                                        dtype=float).reshape(-1)
                    if coords.shape != (3,) or not np.all(np.isfinite(coords)):
                        return None
                    label = str(granule.get("label", "")).strip()
                    if not label:
                        return None
                    parsed.append({"label": label, "lab": tuple(float(v) for v in coords)})
            else:
                parsed.append({"label": None, "lab": lab})
            return {
                "rgb": rgb,
                "lab": lab,
                "hex": color_hex,
                "granules": parsed,
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
                ("PyFCS Color Sources", "*.json *.cns *.fcs *.JSON *.CNS *.FCS"),
                ("PyFCS JSON Color Space", "*.json *.JSON"),
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
            text="Build FCS from selected categories",
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
        bottom.grid_columnconfigure(0, weight=1, uniform="toolbar")
        bottom.grid_columnconfigure(2, weight=1, uniform="toolbar")

        actions = tk.Frame(bottom, bg=self.CARD)
        actions.grid(row=0, column=1)
        tk.Button(
            actions, text="Select All", command=self._select_all_colors,
            font=self.FONT, relief="solid", bd=1, padx=10, pady=3,
            cursor="hand2",
        ).pack(side="left")
        tk.Button(
            actions, text="Deselect All", command=self._deselect_all_colors,
            font=self.FONT, relief="solid", bd=1, padx=10, pady=3,
            cursor="hand2",
        ).pack(side="left", padx=(8, 0))
        tk.Button(
            actions, text="Remove", command=self._remove_selected_colors,
            font=self.FONT, bg="#FBEDEE", fg="#8F3439",
            activebackground="#F5DCDF", activeforeground="#8F3439",
            relief="solid", bd=1, padx=10, pady=3,
            cursor="hand2",
        ).pack(side="left", padx=(8, 0))

        counters = tk.Frame(bottom, bg=self.CARD)
        counters.grid(row=0, column=2, sticky="e")
        tk.Label(counters, textvariable=self.selected_count_var,
                 font=self.FONT_BOLD, bg=self.CARD, fg=self.BLUE).pack(side="left")
        tk.Label(counters, textvariable=self.visible_count_var,
                 font=self.FONT_SMALL, bg=self.CARD,
                 fg=self.MUTED).pack(side="left", padx=(10, 0))

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
            anchor="center",
        ).grid(row=0, column=3, sticky="nsew", padx=6)

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
        # Header sits outside the scrolling canvas: reserve the scrollbar's
        # width and match the 3px inset of each category row.
        header.pack_configure(padx=(3, scrollbar.winfo_reqwidth() + 6))

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
            text="+ Add Color Category",
            command=self._add_custom_color,
            font=self.FONT_BOLD,
            bg=UtilsTools.UI_ADD_CATEGORY_BG,
            fg=UtilsTools.UI_ADD_CATEGORY_FG,
            activebackground=UtilsTools.UI_ADD_CATEGORY_HOVER,
            activeforeground=UtilsTools.UI_ADD_CATEGORY_FG,
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
            bg=UtilsTools.UI_ADD_SOURCE_BG,
            fg=UtilsTools.UI_ADD_SOURCE_FG,
            activebackground=UtilsTools.UI_ADD_SOURCE_HOVER,
            activeforeground=UtilsTools.UI_ADD_SOURCE_FG,
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
            activebackground=UtilsTools.UI_ACCENT_HOVER,
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
        searchable = data.get("_search_key_cache")
        if searchable is None:
            # RGB conversions are relatively expensive: compute the searchable
            # representation once per category, not on every keystroke or
            # Select All/Deselect All during a filtered search.
            rgb = data.get("rgb", ())
            lab = data.get("lab", ())
            try:
                rgb_values = [str(int(round(float(v)))) for v in list(rgb)[:3]]
            except (TypeError, ValueError, OverflowError):
                rgb_values = []
            try:
                lab_values = [f"{float(v):.2f}" for v in list(lab)[:3]]
            except (TypeError, ValueError, OverflowError):
                lab_values = []
            color_hex = str(data.get("hex", "") or "").lower()
            granule_values = []
            for index, g in enumerate(data.get("granules", [])):
                granule_values.extend((
                    self._granule_display_label(name, g, index),
                    " ".join(f"{float(v):.2f}" for v in g["lab"]),
                    UtilsTools.rgb_to_hex(UtilsTools.lab_to_rgb(g["lab"])),
                ))
            searchable = " ".join((
                str(name), color_hex, color_hex.lstrip("#"),
                " ".join(rgb_values), " ".join(lab_values),
                " ".join(granule_values),
            )).lower()
            data["_search_key_cache"] = searchable

        return all(token in searchable for token in query_tokens)

    def _toggle_category_details(self, row_data):
        """Expand aligned sub-rows, not a boxed panel inside the table."""
        name = next((key for key, value in self.colors.items() if value is row_data), None)
        if name is None:
            return
        info = self._row_details.get(name)
        if not info:
            return
        if name in self._expanded_categories:
            self._expanded_categories.remove(name)
            if info["panel"] is not None:
                info["panel"].pack_forget()
        else:
            self._expanded_categories.add(name)
            if info["panel"] is None:
                info["panel"] = self._create_granule_breakdown(info["wrapper"], name, row_data)
            info["panel"].pack(fill="x", padx=(0, 0), pady=(0, 3))
        self._refresh_category_caption(name)
        self._refresh_category_summary(name)

    def _create_granule_breakdown(self, wrapper, category, data):
        """Inline children sharing the header's Color / RGB / HEX / LAB grid."""
        panel = tk.Frame(wrapper, bg=self.CARD)
        header = tk.Frame(panel, bg=self.CARD)
        header.pack(fill="x", pady=(1, 1))
        tk.Label(header, text="GRANULES", font=self.FONT_SMALL_BOLD,
                 bg=self.CARD, fg=self.MUTED).pack(side="left", padx=(64, 0))
        for i, granule in enumerate(data.get("granules", [])):
            row_bg = self.PANEL if i % 2 == 0 else self.CARD
            row = tk.Frame(panel, bg=row_bg, height=28)
            row.pack(fill="x")
            row.pack_propagate(False)
            self._configure_table_columns(row)
            cell = tk.Frame(row, bg=row_bg)
            cell.grid(row=0, column=0, sticky="nsew", padx=(17, 8))
            tk.Label(cell, text="↳", font=self.FONT_SMALL,
                     bg=row_bg, fg="#b0b7c4").pack(side="left", padx=(3, 4))
            active = bool(self.color_checks[category]["var"].get())
            flag = tk.BooleanVar(value=active and granule.get("enabled", True))
            tk.Checkbutton(
                cell, variable=flag, bg=row_bg, activebackground=row_bg,
                selectcolor=row_bg, bd=0, highlightthickness=0,
                cursor="hand2", command=lambda key=category, ix=i, v=flag:
                    self._on_granule_toggle(key, ix, v.get())
            ).pack(side="left", padx=(0, 3))
            self._row_details[category]["granule_vars"].append((i, flag))
            rgb = tuple(max(0, min(255, int(round(float(v)))))
                        for v in UtilsTools.lab_to_rgb(granule["lab"]))
            sw = tk.Canvas(cell, width=19, height=19, bg=row_bg,
                           highlightthickness=0, bd=0)
            sw.pack(side="left", padx=(0, 8))
            sw.create_rectangle(2, 2, 17, 17, fill=UtilsTools.rgb_to_hex(rgb),
                                outline="#9199a6")
            text = self._granule_display_label(category, granule, i)
            name_var = tk.StringVar(value=text)
            name_entry = tk.Entry(cell, textvariable=name_var, font=self.FONT,
                                  bg=row_bg, fg=self.TEXT, relief="solid", bd=1,
                                  highlightthickness=0, insertbackground=self.TEXT)
            name_entry.pack(side="left", fill="x", expand=True)
            self._row_details[category]["granule_name_vars"].append((i, name_var))
            name_entry.bind("<Return>", lambda _e, key=category, ix=i, v=name_var:
                            self._commit_granule_name(key, ix, v))
            name_entry.bind("<FocusOut>", lambda _e, key=category, ix=i, v=name_var:
                            self._commit_granule_name(key, ix, v))
            # Pack from the right in reverse order: Edit · Move · ×.
            if len(data["granules"]) > 1:
                tk.Button(
                    cell, text="×", font=self.FONT_BOLD,
                    bg=row_bg, fg="#B4474C", activeforeground="#B4474C",
                    relief="flat", bd=0, padx=3, cursor="hand2",
                    command=lambda key=category, ix=i:
                        GranuleManager(self, key).remove(ix),
                ).pack(side="right")
            move_button = tk.Button(
                cell, text="Move", font=self.FONT_SMALL,
                bg=row_bg, fg=self.BLUE, relief="flat", bd=0, padx=3,
                cursor="hand2",
            )
            move_button.configure(command=lambda key=category, ix=i, btn=move_button:
                                  self._open_granule_move_menu(key, ix, btn))
            move_button.pack(side="right")
            tk.Button(
                cell, text="Edit", font=self.FONT_SMALL,
                bg=row_bg, fg=self.BLUE, relief="flat", bd=0, padx=3,
                cursor="hand2", command=lambda key=category, ix=i:
                    GranuleManager(self, key).edit(ix),
            ).pack(side="right")
            tk.Label(row, text=f"{rgb[0]}, {rgb[1]}, {rgb[2]}",
                     bg=row_bg, fg=self.MUTED, font=self.FONT_SMALL,
                     anchor="center").grid(row=0, column=1, sticky="nsew", padx=6)
            tk.Label(row, text=UtilsTools.rgb_to_hex(rgb).upper(),
                     bg=row_bg, fg=self.MUTED, font=self.FONT_SMALL,
                     anchor="center").grid(row=0, column=2, sticky="nsew", padx=6)
            l, a, b = granule["lab"]
            tk.Label(row, text=f"{l:.2f}, {a:.2f}, {b:.2f}",
                     bg=row_bg, fg=self.MUTED, font=self.FONT_SMALL,
                     anchor="center").grid(row=0, column=3, sticky="nsew", padx=6)
        return panel

    def _create_color_row(self, name, index):
        """Build one category row, optionally expanded to show its granules."""
        if name not in self.colors or name not in self.color_checks:
            return None

        data = self.colors[name]
        check_data = self.color_checks[name]
        row_bg = self.CARD if index % 2 == 0 else "#fbfcfd"

        # Each category owns an independent wrapper containing its one-line
        # summary and its collapsible detail panel.
        wrapper = tk.Frame(self.colors_inner, bg=self.CARD)
        wrapper.pack(fill="x", padx=3, pady=1)
        row = tk.Frame(wrapper, bg=row_bg, bd=0)
        row.pack(fill="x")
        self._configure_table_columns(row)

        color_cell = tk.Frame(row, bg=row_bg)
        color_cell.grid(row=0, column=0, sticky="nsew", padx=(2, 8))

        check = tk.Checkbutton(
            color_cell, variable=check_data["var"], bg=row_bg,
            activebackground=row_bg, selectcolor=row_bg,
            command=lambda key=name: self._on_category_toggle(key), cursor="hand2", bd=0,
            highlightthickness=0)
        check.pack(side="left", padx=(0, 4), pady=5)

        swatch = tk.Canvas(color_cell, width=28, height=28, bg=row_bg,
                           highlightthickness=0, bd=0)
        swatch.pack(side="left", padx=(0, 9), pady=4)
        swatch_rectangle = swatch.create_rectangle(2, 2, 26, 26, fill=data["hex"], outline="#707070")
        swatch_arrow = swatch.create_text(14, 14, text="▾", fill=self.BLUE,
                                          font=("Segoe UI", 17, "bold"), state="hidden")
        swatch.configure(cursor="hand2")
        swatch.bind("<Button-1>", lambda _e, item=data: self._toggle_category_details(item))

        name_frame = tk.Frame(color_cell, bg=row_bg)
        name_frame.pack(side="left", fill="x", expand=True)
        name_var = tk.StringVar(value=name)
        name_entry = tk.Entry(name_frame, textvariable=name_var,
                              font=self.FONT_BOLD, bg=self.CARD, fg=self.TEXT,
                              relief="solid", bd=1, highlightthickness=0)
        name_entry.configure(
            validate="key",
            validatecommand=(self.win.register(
                lambda proposed: len(proposed) <= UtilsTools.MAX_CATEGORY_NAME_CHARS
            ), "%P"),
        )
        name_entry.pack(side="left", fill="x", expand=True)

        count = len(data.get("granules", []))
        expanded = name in self._expanded_categories
        # Remove one category, including its granules; do not change others.
        tk.Button(
            name_frame, text="×", font=self.FONT_BOLD,
            bg=row_bg, fg="#B4474C", activeforeground="#B4474C",
            relief="flat", bd=0, padx=3, cursor="hand2",
            command=lambda key=name: self._remove_category(key),
        ).pack(side="right", padx=(2, 0))
        tk.Button(
            name_frame, text="+ Add granule",
            command=lambda key=name: GranuleManager(self, key).add(),
            font=self.FONT_SMALL_BOLD, bg=row_bg, fg=self.BLUE,
            activebackground=row_bg, relief="flat", bd=0,
            padx=5, pady=3, cursor="hand2"
        ).pack(side="right", padx=(5, 0))
        expand_button = tk.Button(
            name_frame,
            text=f"{count} granule{'s' if count != 1 else ''}",
            command=lambda item=data: self._toggle_category_details(item),
            font=self.FONT_SMALL_BOLD,
            bg=self.BLUE_SOFT if count > 1 else self.SOFT,
            fg=self.BLUE if count > 1 else self.MUTED,
            relief="flat", bd=0, padx=7, pady=3, cursor="hand2"
        )
        expand_button.pack(side="right", padx=(6, 0))

        name_entry.bind("<Return>",
                        lambda _e, old=name, var=name_var: self._commit_color_name(old, var))
        name_entry.bind("<FocusOut>",
                        lambda _e, old=name, var=name_var: self._commit_color_name(old, var))
        self._name_editors.append((name, name_var))


        rgb = data["rgb"]
        rgb_label = tk.Label(row, text=f"{rgb[0]}, {rgb[1]}, {rgb[2]}",
                             font=self.FONT, bg=row_bg, fg=self.MUTED, anchor="center")
        rgb_label.grid(row=0, column=1, sticky="nsew", padx=6)
        hex_label = tk.Label(row, text=data["hex"], font=self.FONT, bg=row_bg,
                             fg=self.MUTED, anchor="center")
        hex_label.grid(row=0, column=2, sticky="nsew", padx=6)
        lab = data["lab"]
        lab_label = tk.Label(row, text=f"{lab[0]:.2f}, {lab[1]:.2f}, {lab[2]:.2f}",
                             font=self.FONT, bg=row_bg, fg=self.MUTED, anchor="center")
        lab_label.grid(row=0, column=3, sticky="nsew", padx=6)

        # Build the breakdown lazily; collapsed categories add no granule widgets.
        self._row_widgets[name] = wrapper
        self._row_details[name] = {
            "wrapper": wrapper, "panel": None, "button": expand_button,
            "granule_vars": [],
            "granule_name_vars": [],
            "summary": {"rgb": rgb_label, "hex": hex_label, "lab": lab_label},
            "swatch": (swatch, swatch_rectangle, swatch_arrow),
        }
        self._refresh_category_summary(name)
        if expanded:
            details = self._create_granule_breakdown(wrapper, name, data)
            self._row_details[name]["panel"] = details
            details.pack(fill="x", pady=(0, 3))
        self._refresh_category_caption(name)
        return wrapper

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
            self._update_selection_counter()
            return

        # Remove the empty-state row before appending a color.
        if not self._row_widgets:
            for child in self.colors_inner.winfo_children():
                child.destroy()
            self._name_editors = []
            self._row_details = {}

        start_index = len(self._row_widgets)
        for offset, name in enumerate(names):
            self._create_color_row(name, start_index + offset)

        self._update_selection_counter()

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
        self._row_details = {}
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

    def _bulk_selection_targets(self):
        """Use only current search matches, or the complete palette if unfiltered."""
        search = getattr(self, "search_var", None)
        if search is None:
            return list(self.colors)
        try:
            if not search.get().strip():
                return list(self.colors)
            return [name for name in self.colors if self._matches_search(name)]
        except tk.TclError:
            return list(self.colors)

    def _select_all_colors(self):
        """Select only categories matching the current palette search.

        Without a search this still selects every category. Hidden categories
        retain their prior selection state, including their granule flags.
        """
        matching = self._bulk_selection_targets()
        for name in matching:
            self.color_checks[name]["var"].set(True)
            for granule in self.colors[name]["granules"]:
                granule["enabled"] = True
            self._sync_representative(name)
            self._refresh_category_controls(name)
            self._refresh_category_summary(name)
        self._update_selection_counter()

    def _deselect_all_colors(self):
        """Deselect matching categories, leaving hidden ones unchanged."""
        matching = self._bulk_selection_targets()
        for name in matching:
            self.color_checks[name]["var"].set(False)
            self._refresh_category_controls(name)
            self._refresh_category_summary(name)
        self._update_selection_counter()

    # Custom Color / Create
    def _next_unique_name(self, base):
        return self._make_unique_color_name(base)

    def _add_custom_color(self):
        """Create a category with one or more positive granules in one place."""
        UtilsTools.CustomCategoryDialog(self)

    def _commit_pending_color_names(self):
        """Commit inline category names; abort an action on an invalid edit."""
        pending = list(getattr(self, "_name_editors", []))
        changed = False
        for old_name, name_var in pending:
            if old_name not in self.colors:
                continue
            requested = name_var.get().strip()
            if requested == old_name:
                continue
            if not requested or len(requested) > UtilsTools.MAX_CATEGORY_NAME_CHARS:
                name_var.set(old_name)
                self.app.custom_warning(
                    "Invalid Category Name",
                    f"Category names must contain 1 to {UtilsTools.MAX_CATEGORY_NAME_CHARS} characters.",
                    parent=self.win)
                return False
            new_name = self._rename_color(old_name, requested)
            name_var.set(new_name)
            if new_name == old_name:
                self.app.custom_warning(
                    "Invalid Category Name",
                    f"Unable to rename '{old_name}' to '{requested}'. Check the granule labels.",
                    parent=self.win)
                return False
            changed = True
        if changed:
            self._refresh_color_list()
        return True

    def _commit_pending_granule_names(self):
        """Commit all visible child edits; stop when a name is rejected."""
        for category, info in list(self._row_details.items()):
            for index, variable in list(info.get("granule_name_vars", [])):
                items = self.colors.get(category, {}).get("granules", [])
                if 0 <= index < len(items):
                    shown = self._granule_display_label(category, items[index], index)
                    if variable.get().strip() != shown:
                        if not self._commit_granule_name(category, index, variable):
                            return False
        return True

    def _remove_categories(self, names):
        """Remove palette-local categories, leaving other selections intact.

        This is deliberately a structural update, unlike the lightweight
        checkbox updates in Select All/Deselect All.
        """
        if self._removing_categories:
            return
        names = [name for name in names if name in self.colors]
        if not names:
            self.app.custom_warning(
                "No Categories Selected", "Select at least one category to remove.",
                parent=self.win,
            )
            return
        plural = len(names) != 1
        description = (f"Remove {len(names)} selected categories and all their granules?"
                       if plural else f"Remove category '{names[0]}' and all its granules?")
        self._removing_categories = True
        try:
            if not messagebox.askyesno(
                "Remove Color Categories" if plural else "Remove Color Category",
                description + "\nThis only changes the temporary palette.",
                icon="warning", parent=self.win,
            ):
                return
            for name in names:
                self.colors.pop(name, None)
                self.color_checks.pop(name, None)
                self._expanded_categories.discard(name)
                # Drop the old widget without rebuilding every other category.
                widget = self._row_widgets.pop(name, None)
                self._row_details.pop(name, None)
                if widget is not None:
                    widget.destroy()
            self._name_editors = [entry for entry in self._name_editors
                                  if entry[0] not in names]
            if not self._row_widgets:
                self._refresh_color_list()  # Display the empty/search hint.
            else:
                self._update_selection_counter()
            self.colors_canvas.configure(scrollregion=self.colors_canvas.bbox("all"))
        finally:
            self._removing_categories = False

    def _remove_category(self, category):
        """Remove a category using the red × next to its name."""
        self._remove_categories([category])

    def _remove_selected_colors(self):
        """Remove only selected categories matching the current search."""
        names = [name for name in self._bulk_selection_targets()
                 if self.color_checks[name]["var"].get()]
        self._remove_categories(names)

    def _open_granule_move_menu(self, category, index, widget):
        """Offer all other categories without creating a new dialog."""
        if category not in self.colors or not 0 <= index < len(self.colors[category]["granules"]):
            return
        destinations = [name for name in self.colors if name != category]
        if not destinations:
            self.app.custom_warning(
                "Cannot Move Granule", "Create another color category first.",
                parent=self.win,
            )
            return
        menu = tk.Menu(self.win, tearoff=False)
        for destination in destinations:
            menu.add_command(
                label=destination,
                command=lambda target=destination:
                    self._move_granule(category, index, target),
            )
        try:
            menu.tk_popup(widget.winfo_rootx(),
                          widget.winfo_rooty() + widget.winfo_height())
        finally:
            menu.grab_release()

    def _move_granule(self, source, index, destination):
        """Move a complete prototype without changing its exact LAB or label.

        The target inherits the source site's *effective* selection state.
        Moving the final site deletes the empty source category after consent.
        The final Create validator remains responsible for duplicate-LAB
        candidates, including imports from repeated color sources.
        """
        if source == destination or source not in self.colors or destination not in self.colors:
            return False
        source_items = self.colors[source]["granules"]
        if not 0 <= index < len(source_items):
            return False
        moving = dict(source_items[index])
        if any(item["label"] == moving["label"]
               for item in self.colors[destination]["granules"]):
            self.app.custom_warning(
                "Cannot Move Granule",
                f"Granule '{moving['label']}' already exists in '{destination}'.",
                parent=self.win,
            )
            return False
        if len(source_items) == 1:
            if not messagebox.askyesno(
                "Move Last Granule",
                f"Moving '{moving['label']}' will remove the empty category '{source}'.\n"
                f"Move it to '{destination}'?",
                icon="warning", parent=self.win,
            ):
                return False
        # Commit pending inline renames *before* moving. Otherwise old Tk
        # FocusOut callbacks could be applied to the wrong prototype later.
        if not self._commit_pending_granule_names():
            return False
        if not self._commit_pending_color_names():
            return False
        if source not in self.colors or destination not in self.colors:
            return False
        source_items = self.colors[source]["granules"]
        if not 0 <= index < len(source_items) or source_items[index]["label"] != moving["label"]:
            return False

        source_was_selected = bool(self.color_checks[source]["var"].get())
        destination_was_selected = bool(self.color_checks[destination]["var"].get())
        moved_selected = source_was_selected and bool(moving.get("enabled", True))

        # Prevent activation of unrelated destination sites when moving a
        # selected prototype into a previously deselected category.
        if moved_selected and not destination_was_selected:
            for item in self.colors[destination]["granules"]:
                item["enabled"] = False
        elif destination_was_selected and not moved_selected:
            moving["enabled"] = False

        self.colors[destination]["granules"].append(moving)
        self.colors[destination].pop("_search_key_cache", None)
        if moved_selected:
            self.color_checks[destination]["var"].set(True)

        if len(source_items) == 1:
            del self.colors[source]
            del self.color_checks[source]
            self._expanded_categories.discard(source)
        else:
            del source_items[index]
            if source_was_selected:
                self.color_checks[source]["var"].set(any(
                    item.get("enabled", True) for item in source_items))
            self._sync_representative(source)
        self._sync_representative(destination)
        self._expanded_categories.add(destination)
        # Moving changes two category structures. Rebuild here (not on each
        # selection change), preserving search, open rows and scroll position.
        previous_scroll = self.colors_canvas.yview()[0]
        if self.search_var.get().strip():
            self.search_var.set("")
        self._refresh_color_list()
        self.colors_canvas.after_idle(
            lambda: self.colors_canvas.yview_moveto(previous_scroll)
            if self.colors_canvas.winfo_exists() else None)
        return True

    def _selected_category_granules(self):
        """Return only active granules of selected categories."""
        selected = {}
        for name, check in self.color_checks.items():
            if not check["var"].get():
                continue
            active = {
                item["label"]: np.asarray(item["lab"], dtype=float)
                for item in self.colors[name]["granules"]
                if item.get("enabled", True)
            }
            if active:
                selected[name] = active
        return selected

    def _create_color_space(self):
        # Commit both child and parent names before validation / construction.
        if not self._commit_pending_granule_names():
            return
        if not self._commit_pending_color_names():
            return
        selected = self._selected_category_granules()
        if len(selected) < 2:
            self.app.custom_warning(
                "Not Enough Colors", "Select at least two categories to create the Color Space.",
                parent=self.win,
            )
            return

        sites = {label: lab for granules in selected.values() for label, lab in granules.items()}
        if len(sites) != sum(len(granules) for granules in selected.values()):
            self.app.custom_warning("Duplicate Granules", "Each granule needs a unique label.",
                                    parent=self.win)
            return
        if any(not UtilsTools.is_valid_lab(lab) for lab in sites.values()):
            self.app.custom_warning("Invalid LAB", "One or more granules are outside the CIELAB domain.",
                                    parent=self.win)
            return
        duplicates = UtilsTools.find_duplicate_lab_pairs(sites)
        if duplicates:
            name_a, name_b, _point = duplicates[0]
            self.app.custom_warning("Duplicate LAB", f"Granules '{name_a}' and '{name_b}' "
                                    "have coincident prototypes.", parent=self.win)
            return

        # The normal palette path stays genuinely atomic and keeps its previous
        # creation dialog, validators and execution semantics unchanged.
        is_granular = any(len(granules) > 1 or next(iter(granules)) != category
                          for category, granules in selected.items())
        if not is_granular:
            previous_checks = getattr(self.app, "color_checks", None)
            self.app.color_checks = self.color_checks
            try:
                started = self.app.create_color_space(parent=self.win)
            finally:
                if previous_checks is None:
                    try:
                        delattr(self.app, "color_checks")
                    except AttributeError:
                        pass
                else:
                    self.app.color_checks = previous_checks
            if started:
                self.close()
            return

        representatives = {category: next(iter(granules.values()))
                           for category, granules in selected.items()}

        def on_create(name, options):
            saved_options = UtilsTools.prepare_granular_creation_options(
                selected, options
            )
            return self.app.save_cs(name, representatives, options=saved_options)

        dialog = UtilsTools.FCSCreationDialog(
            self.win, representatives,
            on_accept=on_create, warn=self.app.custom_warning,
        )
        dialog.transient(self.win)
        dialog.grab_set()
        try:
            dialog.lift(self.win)
            dialog.focus_force()
        except Exception:
            pass
        dialog.wait_window()
        if dialog.result:
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

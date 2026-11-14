
"""Palette-local granule actions using PyFCS' shared precise Color Picker.

All edits are temporary until a new fuzzy color space is created. The class
keeps UI responsibilities small: PaletteBasedCreationManager owns the table
and category selection, while this adapter handles add / edit / remove.
"""

from tkinter import messagebox

import Source.interface.modules.UtilsTools as UtilsTools


class GranuleManager:
    """Add, edit or remove positive granules for a palette category."""

    def __init__(self, palette, category_label):
        self.palette = palette
        self.category_label = category_label

    @property
    def granules(self):
        return self.palette.colors[self.category_label]["granules"]

    def _next_label(self):
        used = self.palette._used_granule_labels()
        number = len(self.granules) + 1
        while True:
            proposal = self.palette._auto_granule_label(self.category_label, number - 1)
            if proposal not in used:
                return proposal
            number += 1

    def _check(self, label, lab, exclude_index=None):
        """Return a recoverable validation result for a prospective site.

        A name-only edit of an imported site must not be blocked because that
        site already shares its LAB with a different imported category.
        """
        same_category = [
            (category, item["label"], item["lab"])
            for category, data in self.palette.colors.items()
            if category == self.category_label
            for index, item in enumerate(data.get("granules", []))
            if index != exclude_index
        ]
        cleaned, point, error = UtilsTools.check_granule_site(
            label, lab, same_category,
        )
        if error:
            return cleaned, point, error

        others = [
            (category, item["label"], item["lab"])
            for category, data in self.palette.colors.items()
            if category != self.category_label
            for item in data.get("granules", [])
        ]
        if any(other_name == cleaned for _, other_name, _ in others):
            return None, None, f"Granule name '{cleaned}' is already in use."

        # Preserve a pre-existing imported overlap on a label-only edit.
        if exclude_index is not None and 0 <= exclude_index < len(self.granules):
            old_lab = tuple(float(v) for v in self.granules[exclude_index]["lab"])
            if point == old_lab:
                return cleaned, point, None

        _, _, error = UtilsTools.check_granule_site(cleaned, point, others)
        if error:
            return None, None, error
        return cleaned, point, None

    def _validate(self, label, lab, exclude_index=None):
        """Compatibility validator for non-UI code; UI uses ``_check``."""
        name, point, message = self._check(label, lab, exclude_index)
        if message:
            raise ValueError(message)
        return name, point

    def add(self):
        """Create a granule directly in the shared precise Color Picker."""
        suggested = self._next_label()

        def on_submit(name, lab, _rgb, _hex, _dialog, status_var):
            try:
                label, point, error = self._check(name, lab)
                if error:
                    status_var.set(error)
                    return False
                entries = [dict(item) for item in self.granules]
                entries.append({"label": label, "lab": point, "enabled": True})
                ok, error = self.palette._set_category_granules(self.category_label, entries)
                if not ok:
                    status_var.set(error)
                    return False
            except (ValueError, TypeError) as exc:
                status_var.set(str(exc))
                return False
            return True

        return self.palette.app._open_square_color_picker(
            parent=self.palette.win,
            title=f"Add granule — {self.category_label}",
            granule_name=suggested,
            submit_text="Add granule",
            on_granule_submit=on_submit,
        )

    def edit(self, index):
        """Edit label and exact LAB directly in the shared Color Picker."""
        if not 0 <= index < len(self.granules):
            return
        item = dict(self.granules[index])
        display_label = self.palette._granule_display_label(
            self.category_label, item, index)

        def on_submit(name, lab, _rgb, _hex, _dialog, status_var):
            try:
                label, point, error = self._check(name, lab, exclude_index=index)
                if error:
                    status_var.set(error)
                    return False
                entries = [dict(g) for g in self.granules]
                entries[index] = {
                    "label": label,
                    "lab": point,
                    "enabled": item.get("enabled", True),
                }
                ok, error = self.palette._set_category_granules(self.category_label, entries)
                if not ok:
                    status_var.set(error)
                    return False
            except (ValueError, TypeError) as exc:
                status_var.set(str(exc))
                return False
            return True

        return self.palette.app._open_square_color_picker(
            parent=self.palette.win,
            title=f"Edit granule — {self.category_label}",
            granule_name=display_label,
            initial_lab=item["lab"],
            submit_text="Save changes",
            on_granule_submit=on_submit,
        )

    def rename(self, index, requested):
        """Rename an existing site in place; return the name displayed in Data."""
        if not 0 <= index < len(self.granules):
            raise ValueError("Granule no longer exists.")
        current = self.granules[index]
        shown = self.palette._granule_display_label(self.category_label, current, index)
        requested = str(requested or "").strip()
        if not requested:
            self.palette.app.custom_warning(
                "Invalid Granule Name", "Granule name cannot be empty.",
                parent=self.palette.win)
            return shown
        if requested == shown:
            return shown
        label, _point, error = self._check(requested, current["lab"], exclude_index=index)
        if error:
            # Preserve the actual label; give the table a recoverable warning.
            self.palette.app.custom_warning(
                "Invalid Granule Name", error, parent=self.palette.win)
            return shown
        current["label"] = label
        self.palette.colors[self.category_label].pop("_search_key_cache", None)
        return label

    def remove(self, index):
        if not 0 <= index < len(self.granules):
            return
        if len(self.granules) <= 1:
            self.palette.app.custom_warning(
                "Cannot Remove Granule",
                "Every category must contain at least one granule.",
                parent=self.palette.win,
            )
            return
        granule = self.granules[index]
        if not messagebox.askyesno(
            "Remove Granule",
            f"Remove '{granule['label']}' from '{self.category_label}'?\n"
            "This only changes the temporary palette.",
            parent=self.palette.win,
        ):
            return
        entries = [dict(g) for i, g in enumerate(self.granules) if i != index]
        ok, error = self.palette._set_category_granules(self.category_label, entries)
        if not ok:
            self.palette.app.custom_warning(
                "Cannot Remove Granule", error, parent=self.palette.win)

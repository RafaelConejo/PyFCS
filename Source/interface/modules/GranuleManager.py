
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
        """Non-throwing user validation shared with Add Color Category.

        On failure return ``(None, None, message)`` and keep the picker open.
        The repository may contain imported sites whose labels differ from
        their category name, so always check actual granule identifiers.
        """
        existing = (
            (category, item["label"], item["lab"])
            for category, data in self.palette.colors.items()
            for index, item in enumerate(data.get("granules", []))
            if not (category == self.category_label and index == exclude_index)
        )
        return UtilsTools.check_granule_site(label, lab, existing)

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
                self.palette._set_category_granules(self.category_label, entries)
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
                self.palette._set_category_granules(self.category_label, entries)
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
        try:
            self.palette._set_category_granules(self.category_label, entries)
        except ValueError as exc:
            self.palette.app.custom_warning(
                "Cannot Remove Granule", str(exc), parent=self.palette.win)

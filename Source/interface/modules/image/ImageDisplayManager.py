"""Controller for the Image Display workspace and original-image sampling.

Owns card geometry, viewport state, workspace widgets and image lifecycle.
ColorMappingManager owns mapping jobs and result caches; the application owns shared pixel readouts.
The full-resolution workspace remains a separate controller.
"""
import os
import random
import platform
import numpy as np
import tkinter as tk
from PIL import Image, ImageTk, ImageOps, ImageDraw, ImageFont
from tkinter import Menu, filedialog, messagebox, DISABLED, NORMAL
from Source.interface.modules.common import UtilsTools
from Source.interface.modules.image.ImageWorkspaceManager import ImageWorkspaceManager


class ImageDisplayManager:
    def __init__(self, app):
        self.app = app
        self.root = app.root
        self._full_resolution_workspace_controller = None
        self._image_workspace_layout_mode = "grid"
        self._image_workspace_focus_id = None
        self._image_workspace_active_id = None
        self._image_workspace_focus_return_mode = "grid"
        self._image_workspace_focus_saved_state = None
        self._image_workspace_focus_saved_collapsed = None
        self._image_workspace_callbacks = {}
        self.images = {}
        self.display_pil = {}
        self.image_view_source = {}
        self.image_view_state = {}
        self._image_zoom_hover_window = None
        self._image_zoom_callbacks = {}
        self._image_zoom_mousewheel_bound = False
        # Card data and callback registries have a single owner and exist
        # before the first image is loaded. Widgets are built in build_workspace.
        self.load_images_names = {}
        self.floating_images = {}
        self.original_images = {}
        self.pil_images_original = {}
        self.image_dimensions = {}
        self.original_image_dimensions = {}
        self.floating_window_state = {}
        self._resize_callbacks = {}
        self._pixel_click_callbacks = {}
        self._original_sampling_state = {}
        self._image_view_pan_state = None
        self._image_workspace_move_state = None
        self._image_workspace_reflow_after_id = None
        self._resize_start = None

    def build_workspace(self, main_paned, *, CARD_BG, PANEL_BG, MUTED, TEXT, BLUE_BG,
                        FONT_TITLE, FONT_SMALL, FONT_SMALL_BOLD):
        # Image Display: title, status and workspace actions share
        # ONE compact header, rather than a LabelFrame title + a second toolbar.
        image_area_frame = tk.Frame(main_paned, bg=CARD_BG, padx=10, pady=7)
        image_workspace_bar = tk.Frame(image_area_frame, bg=CARD_BG)
        image_workspace_bar.pack(fill="x", pady=(0, 5))
        # Keep the heading at the left.  A single compact control group is
        # anchored to the right for the Focus/Grid controls.
        image_workspace_bar.grid_columnconfigure(0, weight=1)
        image_workspace_bar.grid_columnconfigure(1, weight=0)

        workspace_heading = tk.Frame(image_workspace_bar, bg=CARD_BG)
        workspace_heading.grid(row=0, column=0, sticky="w")
        tk.Label(
            workspace_heading, text="Image Display", font=FONT_TITLE,
            bg=CARD_BG, fg=TEXT, anchor="w",
        ).pack(anchor="w")
        self.image_workspace_status_var = tk.StringVar(value="0 images")
        tk.Label(
            workspace_heading, textvariable=self.image_workspace_status_var,
            font=FONT_SMALL, bg=CARD_BG, fg=MUTED, anchor="w",
        ).pack(anchor="w", pady=(3, 0))

        workspace_controls = tk.Frame(image_workspace_bar, bg=CARD_BG)
        workspace_controls.grid(row=0, column=1, sticky="e")

        # Keep Focus and Grid side by side.
        workspace_actions = tk.Frame(workspace_controls, bg=CARD_BG)
        workspace_actions.pack(side="left")
        self.image_workspace_focus_button = tk.Button(
            workspace_actions, text="Focus",
            command=self._focus_active_image_workspace_card,
            font=FONT_SMALL_BOLD, bg="#f8fafc", fg=TEXT,
            activebackground=BLUE_BG, relief="solid", bd=1,
            width=6, padx=4, pady=0, cursor="hand2", state="disabled",
        )
        self.image_workspace_focus_button.pack(side="left", padx=(0, 5))
        self.image_workspace_grid_button = tk.Button(
            workspace_actions, text="Grid",
            command=self._arrange_image_workspace_grid,
            font=FONT_SMALL_BOLD, bg="#f8fafc", fg=TEXT,
            activebackground=BLUE_BG, relief="solid", bd=1,
            width=6, padx=4, pady=0, cursor="hand2",
        )
        self.image_workspace_grid_button.pack(side="left")

        image_canvas_shell = tk.Frame(image_area_frame, bg=PANEL_BG)
        image_canvas_shell.pack(fill="both", expand=True)
        image_canvas_shell.grid_rowconfigure(0, weight=1)
        image_canvas_shell.grid_columnconfigure(0, weight=1)

        self.image_canvas = tk.Canvas(
            image_canvas_shell,
            bg=PANEL_BG,
            borderwidth=1,
            relief="solid",
            highlightthickness=0,
            yscrollincrement=24,
        )
        self.image_canvas.grid(row=0, column=0, sticky="nsew")

        self.image_workspace_vscroll = UtilsTools.styled_scrollbar(
            image_canvas_shell,
            orient="vertical",
            command=self.image_canvas.yview,
        )
        self.image_workspace_vscroll.grid(row=0, column=1, sticky="ns")
        self.image_canvas.configure(yscrollcommand=self.image_workspace_vscroll.set)

        # Mapping controls are embedded in the corresponding image card.
        # No separate dock/window is used, so image + mapping controls always
        # move, minimize and stack as one visual unit.
        self.app.image_mapping_dock = None
        self.app.image_mapping_dock_visible = False
        self.app._mapping_all_palette_by_window = {}
        # Palette/display state cannot be shared between duplicate image windows.
        self.app._mapping_all_pack_by_window = {}

        self._image_workspace_focus_id = None
        self._image_workspace_active_id = None
        self._image_workspace_reflow_after_id = None
        self._image_workspace_callbacks = {}

        self.image_canvas.bind(
            "<Configure>",
            lambda _e: self._schedule_image_workspace_reflow(),
            add="+",
        )
        # A queued layout callback must be cancelled when the canvas is
        # destroyed (including an application exit). Otherwise Tk reports
        # 'invalid command name ..._reflow_image_workspace' after close.
        self.image_canvas.bind(
            "<Destroy>",
            lambda event: self._cancel_image_workspace_reflow()
            if event.widget is self.image_canvas else None,
            add="+",
        )
        return image_area_frame


    def _get_best_image_source_pil(self, window_id, prefer_current_view=True, rgb=True):
        """
        Return the best available PIL image source for image tools.

        If prefer_current_view=True:
            Use the current visible source first. This may be Original, Color Mapping,
            or Color Mapping All.

        If prefer_current_view=False:
            Use the real original image first. This is the correct mode for:
            - Image-Based Color Space Creation
            - Manual color picking
            - Automatic color detection
        """
        def _to_pil(obj):
            if isinstance(obj, Image.Image):
                return obj.convert("RGB") if rgb else obj.copy()

            if isinstance(obj, np.ndarray):
                arr = obj

                if arr.dtype != np.uint8:
                    arr = np.clip(arr, 0, 255).astype(np.uint8)

                if arr.ndim == 2:
                    img = Image.fromarray(arr, "L")
                    return img.convert("RGB") if rgb else img

                if arr.ndim == 3:
                    if arr.shape[2] == 4:
                        img = Image.fromarray(arr, "RGBA")
                        return img.convert("RGB") if rgb else img

                    if arr.shape[2] >= 3:
                        img = Image.fromarray(arr[:, :, :3], "RGB")
                        return img.convert("RGB") if rgb else img

            if isinstance(obj, str) and os.path.exists(obj):
                with Image.open(obj) as image_file:
                    img = ImageOps.exif_transpose(image_file)
                    return img.convert("RGB") if rgb else img.copy()

            raise ValueError("Unsupported image format.")

        candidates = []

        if prefer_current_view:
            candidates.append(("image_view_source", getattr(self, "image_view_source", {}).get(window_id)))
            candidates.append(("display_pil", getattr(self, "display_pil", {}).get(window_id)))

        # Original image priority.
        candidates.append(("pil_images_original", getattr(self, "pil_images_original", {}).get(window_id)))

        # Reload from original file path if needed.
        if hasattr(self, "load_images_names") and window_id in self.load_images_names:
            candidates.append(("load_images_names", self.load_images_names.get(window_id)))

        # Last fallback only.
        candidates.append(("images", getattr(self, "images", {}).get(window_id)))

        for _name, obj in candidates:
            if obj is None:
                continue

            try:
                return _to_pil(obj)
            except Exception:
                continue

        raise ValueError(f"No valid image source found for window_id: {window_id}")


    def save_image(self, window_id=None):
        """
        Save the currently displayed image.

        Parameters
        ----------
        window_id : str or None
            When provided (for example from an image card's context menu), save
            that image directly. When omitted, keep the toolbar/menu behavior
            and ask the user which open image should be saved.

        If the target is a Color Mapping All result, a standalone legend image
        is saved beside it using the palette currently displayed.
        """
        if not hasattr(self, "load_images_names") or not self.load_images_names:
            self.app.custom_warning(message="There are currently no images available to save.")
            return

        if self.app._has_any_active_job():
            self.app.custom_warning(
                "Process Running",
                "Finish or cancel the current color mapping process before saving an image."
            )
            return

        def _build_legend_pil(labels, colors, box_size=28, padding=10, row_gap=6):
            """Build a standalone legend image from labels and RGB uint8 colors."""
            font = ImageFont.load_default()
            max_text_w = 0
            for lbl in labels:
                lbl = str(lbl)
                try:
                    bbox = font.getbbox(lbl)
                    max_text_w = max(max_text_w, bbox[2] - bbox[0])
                except Exception:
                    max_text_w = max(max_text_w, len(lbl) * 7)

            width = padding * 2 + box_size + 10 + max_text_w
            height = padding * 2 + len(labels) * (box_size + row_gap) - row_gap
            legend = Image.new("RGB", (max(1, width), max(1, height)), "white")
            draw = ImageDraw.Draw(legend)
            y = padding

            for lbl, col in zip(labels, colors):
                try:
                    r, g, b = int(col[0]), int(col[1]), int(col[2])
                except Exception:
                    r, g, b = 0, 0, 0

                draw.rectangle(
                    [padding, y, padding + box_size, y + box_size],
                    fill=(r, g, b), outline=(0, 0, 0)
                )
                draw.text(
                    (padding + box_size + 10, y + 7),
                    str(lbl), fill="black", font=font
                )
                y += box_size + row_gap

            return legend

        def _get_mapping_all_legend_data(target_window_id):
            """Return the labels and palette that are actually visible now."""
            if getattr(self.app, "window_mapping_mode", {}).get(target_window_id) != "all":
                return None, None

            # Export ALL assigned categories/granules, even when the compact
            # on-screen category group is collapsed or scrolled out of view.
            pack = getattr(self.app, "_mapping_all_pack_by_window", {}).get(target_window_id)
            if pack and "level_palettes" in pack:
                level = pack.get("level", "categories")
                scheme = pack.get("scheme", "original")
                palette = np.asarray(pack["level_palettes"][level][scheme], dtype=np.uint8)
                space = pack.get("mapping_space", self.app.fuzzy_color_space)
                if level == "categories":
                    labels = [str(p.label) for p in space.prototypes]
                elif getattr(space, "is_granular", False):
                    labels = [
                        (f"{cat.label} / {p.label}" if len(cat.prototypes) > 1
                         else str(cat.label))
                        for cat in space.categories
                        for p in cat.prototypes
                    ]
                else:
                    labels = [str(p.label) for p in space.prototypes]
                colors = palette[:len(labels)]
                alpha_values = pack.get("alpha_values")
                unassigned = pack.get("label_map")
                if unassigned is not None and alpha_values is not None:
                    uncovered = (np.asarray(unassigned) < 0) & (np.asarray(alpha_values) > 0)
                    if np.any(uncovered):
                        labels.append("Unassigned (original)")
                        colors = np.vstack([colors, np.asarray([220, 220, 220], dtype=np.uint8)])
                return labels, colors

            # Legacy fallback for a mapping result created before the current
            # per-window pack existed or locked to an older color space.
            panel_info = getattr(self.app, "proto_options", {}).get(target_window_id)
            if isinstance(panel_info, dict) and panel_info.get("kind") == "all":
                rows = list(panel_info.get("rows", []) or [])
                if rows:
                    labels = []
                    colors = []
                    for row in rows:
                        if isinstance(row, dict):
                            if row.get("type") == "group":
                                continue
                            label = row.get("export_name", row.get("name", ""))
                            rgb = row.get("rgb", (0, 0, 0))
                        else:
                            prototype, rgb = row
                            label = getattr(prototype, "label", prototype)
                        labels.append(str(label))
                        try:
                            rgb_values = np.asarray(rgb, dtype=np.uint8).reshape(-1)[:3]
                            if rgb_values.size != 3:
                                raise ValueError("Invalid RGB legend color")
                            colors.append(tuple(int(v) for v in rgb_values))
                        except Exception:
                            colors.append((0, 0, 0))
                    return labels, np.asarray(colors, dtype=np.uint8)

            labels = [p.label for p in getattr(self.app, "prototypes", []) or []]
            if not labels:
                return None, None

            # Fall back to the last palette stored for this window.
            palette = getattr(self.app, "_mapping_all_palette_by_window", {}).get(target_window_id)
            if palette is not None:
                try:
                    palette = np.asarray(palette, dtype=np.uint8)
                    if len(palette) >= len(labels):
                        return labels, palette[:len(labels)]
                except Exception:
                    pass

            # Handle views created before the per-window palette was stored.
            if not hasattr(self.app, "window_image_key") or target_window_id not in self.app.window_image_key:
                return None, None

            image_key = self.app.window_image_key.get(target_window_id)
            color_space_key = getattr(self.app, "file_path", None)
            cache_pack = getattr(self.app, "_mapping_all_pack_by_window", {}).get(target_window_id)
            if not cache_pack:
                return None, None

            palettes = cache_pack.get("palettes")
            scheme = cache_pack.get("scheme")
            if not palettes or not scheme or scheme not in palettes:
                return None, None

            return labels, np.asarray(palettes[scheme], dtype=np.uint8)[:len(labels)]

        def _save_window(target_window_id, parent_to_close=None):
            if target_window_id not in self.load_images_names:
                self.app.custom_warning("Error", "The selected image is no longer open.")
                return

            source_name = os.path.basename(self.load_images_names.get(target_window_id, "image"))
            stem = os.path.splitext(source_name)[0] or "image"
            save_path = filedialog.asksaveasfilename(
                parent=self.app._get_active_dialog_parent(),
                initialfile=f"{stem}.png",
                defaultextension=".png",
                filetypes=[
                    ("PNG files", "*.png"),
                    ("JPEG files", "*.jpg"),
                    ("All Files", "*.*")
                ]
            )
            if not save_path:
                return

            try:
                # Export the full image mode, not the zoomed viewport shown on the canvas.
                img_to_save = getattr(self, "image_view_source", {}).get(target_window_id)
                if img_to_save is None:
                    img_to_save = getattr(self, "display_pil", {}).get(target_window_id)
                if img_to_save is None:
                    self.app.custom_warning("Error", "No displayed image available to save for this window.")
                    return
                img_to_save = img_to_save.copy()
                ext = os.path.splitext(save_path)[1].lower()
                if ext in (".jpg", ".jpeg") and img_to_save.mode in ("RGBA", "LA"):
                    img_to_save = img_to_save.convert("RGB")
                legend_path = None
                legend_img = None
                labels, legend_colors = _get_mapping_all_legend_data(target_window_id)
                if labels is not None and legend_colors is not None:
                    legend_img = _build_legend_pil(labels, legend_colors)
                    base, _ext = os.path.splitext(save_path)
                    legend_path = base + "_legend.png"
                    if os.path.exists(legend_path) and not messagebox.askyesno(
                            "Overwrite Legend",
                            f"Replace the existing legend?\n{legend_path}",
                            parent=self.app._get_active_dialog_parent()):
                        return

                UtilsTools.save_pil_image_atomic(img_to_save, save_path)
                if legend_img is not None:
                    UtilsTools.save_pil_image_atomic(legend_img, legend_path)

                if legend_path:
                    messagebox.showinfo(
                        "Success",
                        f"Image saved successfully at:\n{save_path}\n\nLegend saved at:\n{legend_path}",
                        parent=self.app._get_active_dialog_parent(),
                    )
                elif getattr(self.app, "window_mapping_mode", {}).get(target_window_id) == "all":
                    messagebox.showinfo(
                        "Success",
                        f"Image saved successfully at:\n{save_path}\n\n"
                        "The Mapping All legend could not be reconstructed for export.",
                        parent=self.app._get_active_dialog_parent(),
                    )
                else:
                    messagebox.showinfo(
                        "Success",
                        f"Image saved successfully at:\n{save_path}",
                        parent=self.app._get_active_dialog_parent(),
                    )
            except Exception as exc:
                self.app.custom_warning("Error", f"Failed to save image:\n{exc}")
            finally:
                if parent_to_close is not None:
                    try:
                        parent_to_close.destroy()
                    except Exception:
                        pass

        # Context-menu path: the image is already known, so do not ask again.
        if window_id is not None:
            _save_window(window_id)
            return

        # Toolbar/main-menu path: use a styled image picker instead of the
        # legacy Listbox popup. This makes it clear which current view will be
        # exported and whether Mapping All will also generate a legend file.
        window_ids = list(self.load_images_names.keys())
        parent = self.app._get_active_dialog_parent()

        popup = tk.Toplevel(parent)
        popup.withdraw()
        popup.title("Save Image")
        popup.configure(bg="#eeeeee")
        popup.resizable(False, False)
        popup.transient(parent)

        selected_id = {"value": None}
        row_refs = {}
        thumb_refs = []
        # Keep PhotoImage thumbnails alive after save_image() returns.
        popup._thumb_refs = thumb_refs

        outer = tk.Frame(popup, bg="#eeeeee")
        outer.pack(fill="both", expand=True, padx=12, pady=12)

        panel = tk.Frame(outer, bg="white", bd=1, relief="solid")
        panel.pack(fill="both", expand=True)

        header = tk.Frame(panel, bg="#f6f6f6", height=58)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(
            header,
            text="Save Image",
            font=("Sans", 13, "bold"),
            bg="#f6f6f6",
            fg="#222222",
            anchor="w",
            padx=16,
        ).pack(side="left", fill="y")

        tk.Label(
            header,
            text="Choose an open image to export",
            font=("Sans", 9, "italic"),
            bg="#f6f6f6",
            fg="#666666",
            padx=16,
        ).pack(side="right", fill="y")

        body = tk.Frame(panel, bg="white")
        body.pack(fill="both", expand=True, padx=14, pady=(12, 8))

        list_canvas = tk.Canvas(
            body,
            bg="white",
            highlightthickness=0,
            bd=0,
            width=430,
            height=min(300, max(92, len(window_ids) * 78)),
        )
        list_canvas.pack(side="left", fill="both", expand=True)

        scrollbar = UtilsTools.styled_scrollbar(body, orient="vertical", command=list_canvas.yview)
        scrollbar.pack(side="right", fill="y")
        list_canvas.configure(yscrollcommand=scrollbar.set)

        rows_frame = tk.Frame(list_canvas, bg="white")
        rows_window = list_canvas.create_window((0, 0), window=rows_frame, anchor="nw")

        def _mode_text(wid):
            mode = getattr(self.app, "window_mapping_mode", {}).get(wid)
            if mode == "single":
                return "Color Mapping"
            if mode == "all":
                return "Color Mapping All · legend included"
            return "Original Image"

        def _set_selected(wid):
            if wid not in row_refs:
                return
            selected_id["value"] = wid
            for item_id, refs in row_refs.items():
                chosen = item_id == wid
                refs["frame"].configure(
                    bg="#eef4ff" if chosen else "white",
                    highlightbackground="#6f9ee8" if chosen else "#d9dde3",
                    highlightthickness=1,
                )
                refs["text_frame"].configure(bg="#eef4ff" if chosen else "white")
                refs["name"].configure(bg="#eef4ff" if chosen else "white")
                refs["mode"].configure(bg="#eef4ff" if chosen else "white")
            save_btn.configure(state="normal")

        def _save_selected(_event=None):
            wid = selected_id.get("value")
            if wid is None:
                return
            _save_window(wid, parent_to_close=popup)

        for index, wid in enumerate(window_ids):
            filename = self.load_images_names.get(wid, "image")
            row = tk.Frame(
                rows_frame,
                bg="white",
                bd=0,
                highlightthickness=1,
                highlightbackground="#d9dde3",
                cursor="hand2",
            )
            row.pack(fill="x", padx=1, pady=(0, 7))

            # Thumbnail of exactly the current displayed view.
            pil_thumb = getattr(self, "display_pil", {}).get(wid)
            if pil_thumb is None:
                pil_thumb = getattr(self, "pil_images_original", {}).get(wid)
            if pil_thumb is not None:
                thumb = pil_thumb.convert("RGB").copy()
                thumb.thumbnail((72, 54), Image.Resampling.LANCZOS)
                thumb_bg = Image.new("RGB", (72, 54), "white")
                tx = (72 - thumb.width) // 2
                ty = (54 - thumb.height) // 2
                thumb_bg.paste(thumb, (tx, ty))
                thumb_tk = ImageTk.PhotoImage(thumb_bg)
                thumb_refs.append(thumb_tk)
                thumb_label = tk.Label(row, image=thumb_tk, bg="white", bd=1, relief="solid")
            else:
                thumb_label = tk.Label(row, text="No preview", width=10, height=3, bg="#f5f5f5")
            thumb_label.pack(side="left", padx=8, pady=7)

            text_frame = tk.Frame(row, bg="white")
            text_frame.pack(side="left", fill="both", expand=True, padx=(2, 10), pady=7)

            name_label = tk.Label(
                text_frame,
                text=os.path.basename(filename),
                font=("Sans", 10, "bold"),
                fg="#1f2937",
                bg="white",
                anchor="w",
            )
            name_label.pack(fill="x")

            mode_label = tk.Label(
                text_frame,
                text=_mode_text(wid),
                font=("Sans", 8),
                fg=UtilsTools.UI_ACCENT if getattr(self.app, "window_mapping_mode", {}).get(wid) else "#6b7280",
                bg="white",
                anchor="w",
            )
            mode_label.pack(fill="x", pady=(4, 0))

            row_refs[wid] = {
                "frame": row,
                "text_frame": text_frame,
                "name": name_label,
                "mode": mode_label,
            }

            for widget in (row, thumb_label, text_frame, name_label, mode_label):
                widget.bind("<Button-1>", lambda _e, w=wid: _set_selected(w))
                widget.bind("<Double-Button-1>", lambda _e, w=wid: (_set_selected(w), _save_selected()))

        rows_frame.update_idletasks()
        list_canvas.configure(scrollregion=list_canvas.bbox("all"))
        list_canvas.itemconfigure(rows_window, width=max(1, list_canvas.winfo_reqwidth()))

        def _sync_rows_width(event):
            try:
                list_canvas.itemconfigure(rows_window, width=max(1, event.width - 2))
            except Exception:
                pass
        list_canvas.bind("<Configure>", _sync_rows_width)

        def _wheel_list(event):
            try:
                px = popup.winfo_pointerx()
                py = popup.winfo_pointery()
                x0 = list_canvas.winfo_rootx()
                y0 = list_canvas.winfo_rooty()
                x1 = x0 + list_canvas.winfo_width()
                y1 = y0 + list_canvas.winfo_height()
                if not (x0 <= px < x1 and y0 <= py < y1):
                    return None

                if getattr(event, "num", None) == 4:
                    step = -1
                elif getattr(event, "num", None) == 5:
                    step = 1
                else:
                    delta = int(getattr(event, "delta", 0) or 0)
                    if delta == 0:
                        return None
                    if platform.system() == "Darwin":
                        step = -1 if delta > 0 else 1
                    else:
                        step = int(-delta / 120)
                        if step == 0:
                            step = -1 if delta > 0 else 1
                list_canvas.yview_scroll(step, "units")
                return "break"
            except Exception:
                return None
        popup.bind("<MouseWheel>", _wheel_list, add="+")
        popup.bind("<Button-4>", _wheel_list, add="+")
        popup.bind("<Button-5>", _wheel_list, add="+")

        footer = tk.Frame(panel, bg="white")
        footer.pack(fill="x", padx=14, pady=(0, 12))

        tk.Button(
            footer,
            text="Cancel",
            font=("Helvetica", 9),
            bg="#f2f2f2",
            fg="#333333",
            relief="solid",
            bd=1,
            padx=14,
            pady=4,
            command=popup.destroy,
        ).pack(side="right", padx=(8, 0))

        save_btn = tk.Button(
            footer,
            text="Save Selected",
            font=("Helvetica", 9, "bold"),
            bg=UtilsTools.UI_ACCENT_SOFT,
            fg=UtilsTools.UI_ACCENT,
            activebackground=UtilsTools.UI_ACCENT_HOVER,
            activeforeground=UtilsTools.UI_ACCENT,
            relief="solid",
            bd=1,
            padx=16,
            pady=4,
            state="disabled",
            command=_save_selected,
        )
        save_btn.pack(side="right")

        popup.bind("<Escape>", lambda _e: popup.destroy())
        popup.bind("<Return>", _save_selected)

        popup.update_idletasks()
        dialog_w = 500
        dialog_h = min(440, max(190, popup.winfo_reqheight()))
        try:
            self.app.center_popup_to_parent(popup, dialog_w, dialog_h, parent=parent)
        except Exception:
            self.app.center_popup(popup, dialog_w, dialog_h)

        # Preselect the active card when available; otherwise choose the first.
        initial = getattr(self, "_image_workspace_active_id", None)
        if initial not in window_ids and window_ids:
            initial = window_ids[0]
        if initial is not None:
            _set_selected(initial)
        popup.deiconify()
        popup.grab_set()


    def open_full_resolution_image_workspace(self, window_id=None):
        """Open a maximizable image workspace using the original source pixels."""
        if window_id is None:
            image_ids = list((getattr(self, "load_images_names", None) or {}).keys())
            if not image_ids:
                self.app.custom_warning("Image Workspace", "Open an image first.")
                return
            window_id = getattr(self, "_image_workspace_active_id", None)
            if window_id not in image_ids:
                window_id = image_ids[0]
        controller = getattr(self, "_full_resolution_workspace_controller", None)
        if controller is not None:
            try:
                if controller.win.winfo_exists() and controller.source_window_id == window_id:
                    controller.win.lift()
                    controller.win.focus_force()
                    return
                controller.close()
            except tk.TclError:
                pass
        try:
            self._full_resolution_workspace_controller = ImageWorkspaceManager(self.app, window_id)
        except (ValueError, OSError, tk.TclError) as exc:
            self.app.custom_warning("Image Workspace", f"Could not open the image workspace:\n{exc}")


    def close_all_image(self):
        """
        Closes all floating windows and cleans up associated UI/window resources.

        Important:
        - This does NOT clear the persistent image-result caches.
        - It only removes window-bound state so cached mappings can be reused
        if the same image is opened again during the session.
        """
        # Confirm FIRST. Cancelling this prompt must not close the full-resolution
        # workspace or discard any ongoing analysis.
        if self.app._has_any_active_job():
            confirm = messagebox.askyesno(
                "Processes Running",
                "There are one or more processes currently running.\n\n"
                "Do you want to cancel them and close all images?"
            )
            if not confirm:
                return

        controller = getattr(self, "_full_resolution_workspace_controller", None)
        if controller is not None:
            controller.close()
        if not hasattr(self, "floating_images"):
            return

        for window_id in list(self.floating_images.keys()):
            # Cancel running job linked to the window
            try:
                self.app._cancel_window_job(window_id)
            except Exception:
                pass

            # Remove rectangle / pixel sampling state
            try:
                self._disable_original_rectangle_sampling(window_id)
            except Exception:
                pass

            # Remove all canvas items with this window tag
            try:
                self.image_canvas.delete(window_id)
            except Exception:
                pass

            # Destroy legend/options UI if present
            if hasattr(self.app, "proto_options") and window_id in self.app.proto_options:
                info = self.app.proto_options.get(window_id)
                if info:
                    frame = info.get("frame")
                    canvas_item = info.get("canvas_item")

                    try:
                        if canvas_item:
                            self.image_canvas.delete(canvas_item)
                    except Exception:
                        pass

                    try:
                        if frame and frame.winfo_exists():
                            frame.destroy()
                    except Exception:
                        pass

                del self.app.proto_options[window_id]

            # Remove window-bound state only
            for attr_name in (
                "floating_images",
                "pil_images_original",
                "floating_window_state",
                "images",
                "display_pil",
                "original_images",
                "image_dimensions",
                "original_image_dimensions",
                "_resize_callbacks",
                "_pixel_click_callbacks",
                "current_protos",
                "load_images_names",
                "window_image_key",
                "window_mapping_mode",
                "image_view_source",
                "image_view_state",
                "_image_zoom_callbacks",
                "CAN_APPLY_MAPPING",
                "SHOW_ORIGINAL",
                "modified_image",
                "mapping_locked_until_original",
            ):
                if hasattr(self.app, attr_name):
                    d = getattr(self.app, attr_name)
                    if isinstance(d, dict) and window_id in d:
                        del d[window_id]

            if getattr(self, "_image_zoom_hover_window", None) == window_id:
                self._image_zoom_hover_window = None

        self.app.image_manager.preprocessing_cache.clear()

        # Reset leftover per-window dimension dicts if they still exist
        if hasattr(self, "image_dimensions"):
            self.image_dimensions.clear()
        if hasattr(self, "original_image_dimensions"):
            self.original_image_dimensions.clear()

        self._clear_image_display_selection()
        self._image_workspace_focus_id = None
        self._image_workspace_active_id = None
        self._image_workspace_focus_saved_state = None
        self._image_workspace_focus_saved_collapsed = None
        self._image_workspace_callbacks = {}
        self._image_view_pan_state = None
        try:
            self.app._mapping_all_palette_by_window.clear()
            self.app._mapping_all_pack_by_window.clear()
        except Exception:
            pass
        self._schedule_image_workspace_reflow(delay=0)


    def _image_workspace_window_ids(self):
        """Return live image-window ids in stable opening order."""
        ids = []
        names = getattr(self, "load_images_names", {}) or {}
        states = getattr(self, "floating_window_state", {}) or {}
        for window_id in names.keys():
            if window_id in states and self.app._window_exists(window_id):
                ids.append(window_id)
        return ids


    def _update_image_workspace_status(self):
        ids = self._image_workspace_window_ids()
        count = len(ids)
        focus_id = getattr(self, "_image_workspace_focus_id", None)
        layout_mode = getattr(self, "_image_workspace_layout_mode", "grid")

        image_count = f"{count} image{'s' if count != 1 else ''}"
        if focus_id in ids:
            # Focus is a distinct workspace mode; report the underlying layout
            # too, so it remains clear whether it was manual or automatic.
            previous = getattr(self, "_image_workspace_focus_return_mode", layout_mode)
            origin = "Manual" if previous == "manual" else "Automatic"
            text = f"{image_count} · Focus ({origin})"
        else:
            text = f"{image_count} · {'Manual' if layout_mode == 'manual' else 'Automatic'}"

        try:
            self.image_workspace_status_var.set(text)
        except Exception:
            pass

        try:
            focus_active = focus_id in ids
            self.image_workspace_focus_button.configure(
                state="disabled" if (not count or focus_active) else "normal"
            )
            self.image_workspace_grid_button.configure(
                state="normal" if count else "disabled"
            )
        except Exception:
            pass


    def _cancel_image_workspace_reflow(self):
        """Remove a pending layout task before its owning canvas disappears."""
        pending = getattr(self, "_image_workspace_reflow_after_id", None)
        self._image_workspace_reflow_after_id = None
        if pending is not None:
            try:
                self.image_canvas.after_cancel(pending)
            except (tk.TclError, RuntimeError):
                pass


    def _schedule_image_workspace_reflow(self, delay=35):
        """Debounce workspace layout after resize/open/close/state changes."""
        if not hasattr(self, "image_canvas"):
            return

        previous = getattr(self, "_image_workspace_reflow_after_id", None)
        if previous is not None:
            try:
                self.image_canvas.after_cancel(previous)
            except Exception:
                pass

        try:
            self._image_workspace_reflow_after_id = self.image_canvas.after(
                max(0, int(delay)), self._reflow_image_workspace
            )
        except Exception:
            self._image_workspace_reflow_after_id = None


    def _set_image_workspace_active(self, window_id):
        if window_id not in self._image_workspace_window_ids():
            return
        self._image_workspace_active_id = window_id
        self._focus_floating_window(window_id)
        self._update_image_workspace_status()


    def _arrange_image_workspace_grid(self):
        """Return to automatic non-overlapping card layout."""
        # A layout change invalidates selection coordinates from the previous card geometry.
        self._clear_image_display_selection()

        self._image_workspace_focus_id = None
        self._image_workspace_layout_mode = "grid"
        self._image_workspace_focus_return_mode = "grid"
        self._image_workspace_focus_saved_state = None
        self._image_workspace_focus_saved_collapsed = None
        self._reflow_image_workspace()


    def _set_image_workspace_manual(self):
        """Keep the current geometry but stop automatic card repositioning."""
        if getattr(self, "_image_workspace_focus_id", None) is not None:
            return
        self._image_workspace_layout_mode = "manual"
        self._update_image_workspace_status()


    def _focus_active_image_workspace_card(self):
        ids = self._image_workspace_window_ids()
        if not ids:
            return

        # Focus is an exclusive workspace mode. Once active, Grid is the only
        # supported way back to the multi-image workspace. This avoids running
        # the focus geometry twice and accumulating size/viewport drift.
        if getattr(self, "_image_workspace_focus_id", None) in ids:
            return

        active = getattr(self, "_image_workspace_active_id", None)
        if active not in ids:
            active = ids[0]
        self._set_image_workspace_focus(active)


    def _set_image_workspace_focus(self, window_id=None):
        """Maximize one image card inside Image Display."""
        ids = self._image_workspace_window_ids()
        if window_id is None or window_id not in ids:
            return

        # Do not allow Focus -> Focus. Re-entering this path used to resize the
        # same card repeatedly and could desynchronize the viewport geometry.
        # Grid is deliberately the only exit from Focus mode.
        if getattr(self, "_image_workspace_focus_id", None) is not None:
            return

        # Focus changes both position and displayed dimensions. Any pixel/ROI
        # marker belongs to the old geometry and must not survive the switch.
        self._clear_image_display_selection()

        # Remember the exact manual rectangle so leaving Focus does not destroy
        # a user-positioned/resized layout. Grid layouts can simply be recomputed.
        self._image_workspace_focus_return_mode = getattr(
            self, "_image_workspace_layout_mode", "grid"
        )
        self._image_workspace_focus_saved_state = None
        state = getattr(self, "floating_window_state", {}).get(window_id)
        self._image_workspace_focus_saved_collapsed = bool(
            state.get("collapsed", False)
        ) if state else False

        if self._image_workspace_focus_return_mode == "manual" and state:
            self._image_workspace_focus_saved_state = dict(state)

        # Focus always opens the selected card. The minimize control is hidden
        # while focused, so there is no conflicting collapsed/focus geometry.
        if state:
            state["collapsed"] = False

        self._image_workspace_focus_id = window_id
        self._image_workspace_active_id = window_id
        self._reflow_image_workspace()


    def _toggle_image_workspace_focus(self, window_id):
        """Enter Focus when possible; Grid is the only supported exit."""
        if getattr(self, "_image_workspace_focus_id", None) is not None:
            return
        self._set_image_workspace_focus(window_id)


    def _is_workspace_card_collapsed(self, window_id):
        state = getattr(self, "floating_window_state", {}).get(window_id, {})
        return bool(state.get("collapsed", False))


    def _sync_workspace_card_item_states(self, window_id):
        """Apply collapsed/focus state without changing image data or callbacks."""
        if window_id not in getattr(self, "floating_window_state", {}):
            return

        collapsed = self._is_workspace_card_collapsed(window_id)
        focus_id = getattr(self, "_image_workspace_focus_id", None)
        hidden_by_focus = focus_id is not None and focus_id != window_id

        if hidden_by_focus:
            try:
                self.image_canvas.itemconfigure(window_id, state="hidden")
            except Exception:
                pass
            return

        try:
            self.image_canvas.itemconfigure(window_id, state="normal")
        except Exception:
            pass

        content_state = "hidden" if collapsed else "normal"
        for tag in (
            f"{window_id}_img_item",
            f"{window_id}_click_image",
            f"{window_id}_pct_text",
            f"{window_id}_selection_rect",
            f"{window_id}_legend",
        ):
            try:
                self.image_canvas.itemconfigure(tag, state=content_state)
            except Exception:
                pass

        # Resize is a manual display action. It is available in Grid/Manual view;
        # grabbing it switches to manual layout. Focus View uses the whole panel.
        resize_state = "hidden" if collapsed or focus_id == window_id else "normal"
        try:
            self.image_canvas.itemconfigure(f"{window_id}_resize_handle", state=resize_state)
        except Exception:
            pass

        minimize_state = "hidden" if focus_id == window_id else "normal"
        for tag in (f"{window_id}_minimize_rect", f"{window_id}_minimize_text"):
            try:
                self.image_canvas.itemconfigure(tag, state=minimize_state)
            except Exception:
                pass

        try:
            self.image_canvas.itemconfigure(
                f"{window_id}_minimize_text",
                text="+" if collapsed else "−"
            )
        except Exception:
            pass


    def _set_workspace_card_visibility(self, window_id, visible=True):
        state = "normal" if visible else "hidden"
        try:
            self.image_canvas.itemconfigure(window_id, state=state)
        except Exception:
            pass

        if visible:
            self._sync_workspace_card_item_states(window_id)


    def _workspace_legend_width(self, window_id):
        """Mapping panels are stacked below the image, so they add no side width."""
        return 0


    def _workspace_legend_height(self, window_id):
        """Return a compact content-sized height for the mapping panel."""
        info = getattr(self.app, "proto_options", {}).get(window_id)
        if not isinstance(info, dict):
            return 0

        # Keep the selector visually compact: at most four rows are visible.
        # Larger spaces use the internal scrollbar instead of reserving empty
        # vertical space. Short lists shrink to exactly the rows they contain.
        row_count = len(info.get("rows", []) or [])
        visible_rows = max(1, min(row_count if row_count else 1, 4))
        row_h = 24
        pad_top = 5
        footer_h = 66 if info.get("kind") == "all" or info.get("show_detail") else 40
        bottom_pad = 4
        return pad_top + visible_rows * row_h + footer_h + bottom_pad


    def _workspace_legend_extra_height(self, window_id):
        """Vertical footprint added by a mapping panel stacked below the image."""
        legend_h = self._workspace_legend_height(window_id)
        if legend_h <= 0:
            return 0

        # The normal card already reserves 50 px below the image. The mapping
        # panel begins after the percentage/status line and then needs a small
        # bottom margin, so almost its full height is additional card space.
        return legend_h + 4


    def _toggle_image_card_minimize(self, window_id):
        """Collapse/restore one card while preserving all image/mapping state."""
        if self.app._has_active_job(window_id):
            return

        if getattr(self, "_image_workspace_focus_id", None) == window_id:
            return

        state = getattr(self, "floating_window_state", {}).get(window_id)
        if not state:
            return

        state["collapsed"] = not bool(state.get("collapsed", False))
        self._schedule_image_workspace_reflow(delay=0)


    def _update_manual_workspace_scrollregion(self):
        """Keep manually moved cards reachable through the Image Display scrollbars."""
        try:
            bbox = self.image_canvas.bbox("all")
            canvas_w = max(1, int(self.image_canvas.winfo_width()))
            canvas_h = max(1, int(self.image_canvas.winfo_height()))
            if bbox:
                _x1, _y1, x2, y2 = bbox
                self.image_canvas.configure(
                    scrollregion=(0, 0, max(canvas_w, x2 + 20), max(canvas_h, y2 + 20))
                )
            else:
                self.image_canvas.configure(scrollregion=(0, 0, canvas_w, canvas_h))
        except Exception:
            pass


    def _reflow_image_workspace(self):
        """
        Arrange image cards while preserving all existing image functionality.

        Modes
        -----
        grid:
            Automatic non-overlapping cards.
        manual:
            User positions/resizes cards freely. Pressing Grid restores the
            automatic arrangement.
        focus:
            One card temporarily uses almost the whole Image Display area.
        """
        self._image_workspace_reflow_after_id = None

        # Avoid resizing/repositioning a card while a mapping worker is writing
        # its result. The layout is retried immediately after the job settles.
        try:
            if self.app._has_any_active_job():
                self._schedule_image_workspace_reflow(delay=160)
                return
        except Exception:
            pass

        ids = self._image_workspace_window_ids()
        if not ids:
            try:
                self.image_canvas.configure(scrollregion=(0, 0, 1, 1))
                self.image_canvas.yview_moveto(0.0)
            except Exception:
                pass
            self._image_workspace_focus_id = None
            self._image_workspace_active_id = None
            self._image_workspace_layout_mode = "grid"
            self._update_image_workspace_status()
            return

        if getattr(self, "_image_workspace_active_id", None) not in ids:
            self._image_workspace_active_id = ids[0]

        focus_id = getattr(self, "_image_workspace_focus_id", None)
        if focus_id not in ids:
            focus_id = None
            self._image_workspace_focus_id = None

        try:
            self.image_canvas.update_idletasks()
            canvas_w = max(320, int(self.image_canvas.winfo_width()))
            canvas_h = max(260, int(self.image_canvas.winfo_height()))
        except Exception:
            canvas_w, canvas_h = 620, 520

        outer = 14
        gap_x = 14
        gap_y = 14
        title_pad_x = 24
        card_footer = 50
        collapsed_h = 34

        callbacks = getattr(self, "_image_workspace_callbacks", {})

        # Focus / maximize view
        if focus_id is not None:
            # The main window itself may have been resized while Focus is active.
            # Clear transient selection before recomputing focused geometry.
            self._clear_image_display_selection(focus_id)

            state = self.floating_window_state.get(focus_id)
            if state:
                state["collapsed"] = False

            for wid in ids:
                self._set_workspace_card_visibility(wid, wid == focus_id)

            legend_extra = self._workspace_legend_extra_height(focus_id)
            legend_width = self._workspace_legend_width(focus_id)
            available_w = max(180, canvas_w - (outer * 2))
            available_h = max(160, canvas_h - (outer * 2) - card_footer - legend_extra)

            target_w = min(max(160, available_w - title_pad_x - legend_width), 1100)
            target_h = min(max(140, available_h), 800)

            cb = callbacks.get(focus_id, {})
            resize_cb = cb.get("resize")
            relayout_cb = cb.get("relayout")

            if callable(resize_cb):
                resize_cb(focus_id, target_w, target_h, reset_view=False)

            state = self.floating_window_state.get(focus_id)
            if state:
                state["x"] = outer
                state["y"] = outer

            if callable(relayout_cb):
                relayout_cb(focus_id)

            self._sync_workspace_card_item_states(focus_id)
            content_h = max(
                canvas_h,
                outer * 2
                + (state.get("h", 250) if state else 250)
                + card_footer
                + self._workspace_legend_extra_height(focus_id)
            )
            try:
                self.image_canvas.configure(scrollregion=(0, 0, canvas_w, content_h))
                self.image_canvas.yview_moveto(0.0)
            except Exception:
                pass

            self._image_workspace_active_id = focus_id
            self._focus_floating_window(focus_id)
            self._update_image_workspace_status()
            return

        # Manual layout: preserve exact user geometry.
        if getattr(self, "_image_workspace_layout_mode", "grid") == "manual":
            for wid in ids:
                self._set_workspace_card_visibility(wid, True)
                cb = callbacks.get(wid, {})
                relayout_cb = cb.get("relayout")
                if callable(relayout_cb):
                    relayout_cb(wid)
                self._sync_workspace_card_item_states(wid)

            self._update_manual_workspace_scrollregion()
            self._update_image_workspace_status()
            return

        # Automatic grid
        # Grid may resize/reposition cards after a main-window resize, opening
        # a mapping panel, or returning from Focus. Never leave a selection
        # marker tied to the previous geometry.
        self._clear_image_display_selection()
        self._image_workspace_layout_mode = "grid"
        for wid in ids:
            self._set_workspace_card_visibility(wid, True)

        # Choose the largest useful column count for the image cards. Mapping
        # panels are stacked below their images and therefore add no side width.
        max_panel_w = max((self._workspace_legend_width(wid) for wid in ids), default=0)
        preferred = 3 if canvas_w >= 960 and len(ids) >= 3 else (2 if canvas_w >= 560 and len(ids) >= 2 else 1)
        columns = 1
        for candidate in range(preferred, 0, -1):
            candidate_slot = max(220, int((canvas_w - outer * 2 - gap_x * (candidate - 1)) / candidate))
            if candidate_slot - title_pad_x - 8 - max_panel_w >= 180 or candidate == 1:
                columns = candidate
                break

        slot_w = max(220, int((canvas_w - outer * 2 - gap_x * (columns - 1)) / columns))

        # Row heights adapt to minimized cards and to mapping panels below images.
        row_groups = [ids[i:i + columns] for i in range(0, len(ids), columns)]
        row_heights = []
        for group in row_groups:
            if all(self._is_workspace_card_collapsed(wid) for wid in group):
                row_heights.append(collapsed_h + 8)
            else:
                legend_extra = max(
                    (self._workspace_legend_extra_height(wid) for wid in group),
                    default=0,
                )
                row_heights.append(315 + legend_extra)

        y_offsets = []
        current_y = outer
        for height in row_heights:
            y_offsets.append(current_y)
            current_y += height + gap_y

        for index, wid in enumerate(ids):
            row = index // columns
            col = index % columns
            x = outer + col * (slot_w + gap_x)
            y = y_offsets[row]

            cb = callbacks.get(wid, {})
            resize_cb = cb.get("resize")
            relayout_cb = cb.get("relayout")

            if not self._is_workspace_card_collapsed(wid):
                target_w = max(
                    150,
                    slot_w - title_pad_x - 8 - self._workspace_legend_width(wid)
                )
                target_h = 245
                if callable(resize_cb):
                    resize_cb(wid, target_w, target_h, reset_view=False)

            state = self.floating_window_state.get(wid)
            if state:
                state["x"] = x
                state["y"] = y

            if callable(relayout_cb):
                relayout_cb(wid)
            self._sync_workspace_card_item_states(wid)

        content_h = max(canvas_h, current_y + outer)
        try:
            self.image_canvas.configure(scrollregion=(0, 0, canvas_w, content_h))
        except Exception:
            pass

        self._update_image_workspace_status()


    def open_image(self):
        """Allow the user to open an image in the automatic Image Display workspace."""
        if self.app._has_any_active_job():
            self.app.custom_warning(
                "Process Running",
                "Finish or cancel the current color mapping process before opening a new image."
            )
            return

        initial_directory = os.path.join(UtilsTools.get_base_path(), 'image_test')
        if not os.path.isdir(initial_directory):
            initial_directory = os.path.expanduser("~")

        filetypes = [
            ("Image Files", "*.jpg *.jpeg *.png *.bmp *.gif *.tiff *.tif *.webp *.JPG *.JPEG *.PNG *.BMP *.GIF *.TIFF *.TIF *.WEBP"),
            ("All Files", "*.*")
        ]

        filename = filedialog.askopenfilename(
            title="Select an Image",
            initialdir=initial_directory,
            filetypes=filetypes,
            parent=self.root,
        )

        if filename:
            self.create_floating_window(14, 14, filename)


    def _clear_original_selection_rectangle(self, window_id):
        """
        Remove the current original-image selection rectangle for a floating window
        without disabling rectangle sampling bindings/state.
        """
        if not hasattr(self, "_original_sampling_state"):
            return

        state = self._original_sampling_state.get(window_id)
        if not state:
            return

        rect_id = state.get("rect_id")
        if rect_id is not None:
            try:
                self.image_canvas.delete(rect_id)
            except Exception:
                pass

        state["rect_id"] = None
        state["dragging"] = False
        state["drag_start"] = None


    def _clear_image_display_selection(self, window_id=None, clear_info=True):
        """
        Clear transient pixel/ROI selection state from Image Display.

        Layout changes (Grid, Focus, move, resize) change the canvas geometry,
        therefore a marker drawn before the change must never be kept.
        """
        if window_id is None:
            ids = list(getattr(self, "_original_sampling_state", {}).keys())
        else:
            ids = [window_id]

        for wid in ids:
            try:
                self._clear_original_selection_rectangle(wid)
            except Exception:
                pass

        if not clear_info:
            return

        info = getattr(self.app, "_last_pixel_info", None)
        if info is not None:
            info_id = info.get("image_id") if isinstance(info, dict) else None
            if window_id is None or info_id == window_id:
                self.app._last_pixel_info = None
                frame = getattr(self.app, "lab_value_frame", None)
                if frame is not None:
                    try:
                        if frame.winfo_exists():
                            frame.destroy()
                    except Exception:
                        pass
                for attr in (
                    "lab_value_frame", "coord_value",
                    "lab_value_print", "proto_value_text",
                ):
                    try:
                        delattr(self.app, attr)
                    except Exception:
                        pass


    def _get_image_view_crop_box(self, window_id):
        """Return the visible crop in current view-source coordinates."""
        source = getattr(self, "image_view_source", {}).get(window_id)
        if source is None:
            source = getattr(self, "pil_images_original", {}).get(window_id)
        if source is None:
            return None

        source_w, source_h = source.size
        state = getattr(self, "image_view_state", {}).get(window_id)
        if not state:
            state = {"zoom": 1.0, "cx": source_w / 2.0, "cy": source_h / 2.0}
            self.image_view_state[window_id] = state

        zoom = max(1.0, float(state.get("zoom", 1.0)))
        crop_w = max(1.0, source_w / zoom)
        crop_h = max(1.0, source_h / zoom)
        cx = float(state.get("cx", source_w / 2.0))
        cy = float(state.get("cy", source_h / 2.0))
        left = max(0.0, min(source_w - crop_w, cx - crop_w / 2.0))
        top = max(0.0, min(source_h - crop_h, cy - crop_h / 2.0))
        return left, top, left + crop_w, top + crop_h


    def _canvas_xy_to_view_source(self, window_id, canvas_x, canvas_y):
        """Map canvas coordinates to the currently displayed view source."""
        st = getattr(self, "floating_window_state", {}).get(window_id)
        crop = self._get_image_view_crop_box(window_id)
        if not st or crop is None:
            return None

        img_left = float(st["x"]) + 12.0
        img_top = float(st["y"]) + 44.0
        draw_w = max(1.0, float(st["w"]))
        draw_h = max(1.0, float(st["h"]))
        rel_x = float(canvas_x) - img_left
        rel_y = float(canvas_y) - img_top
        if not (0.0 <= rel_x < draw_w and 0.0 <= rel_y < draw_h):
            return None

        left, top, right, bottom = crop
        source_x = left + (rel_x / draw_w) * (right - left)
        source_y = top + (rel_y / draw_h) * (bottom - top)
        return source_x, source_y, rel_x, rel_y


    def _view_source_xy_to_original(self, window_id, source_x, source_y):
        """Convert coordinates from a mapped/original view source to original pixels."""
        source = getattr(self, "image_view_source", {}).get(window_id)
        original = getattr(self, "pil_images_original", {}).get(window_id)
        if source is None or original is None:
            return None

        sw, sh = source.size
        ow, oh = original.size
        if sw <= 0 or sh <= 0 or ow <= 0 or oh <= 0:
            return None

        # Use normalized position because mapping views may be computed at a
        # display/processing resolution different from the original image.
        ox = (float(source_x) / float(sw)) * float(ow)
        oy = (float(source_y) / float(sh)) * float(oh)
        ox = int(max(0, min(ow - 1, ox)))
        oy = int(max(0, min(oh - 1, oy)))
        return ox, oy


    def _canvas_xy_to_original_image(self, window_id, canvas_x, canvas_y):
        """Map a visible canvas point to the corresponding original-image pixel."""
        point = self._canvas_xy_to_view_source(window_id, canvas_x, canvas_y)
        if point is None:
            return None
        sx, sy, rel_x, rel_y = point
        original = self._view_source_xy_to_original(window_id, sx, sy)
        if original is None:
            return None
        return original[0], original[1], rel_x, rel_y


    def _set_image_zoom_source(self, window_id, pil_source, reset_zoom=True):
        """
        Set the PIL image used by the viewport zoom system.

        This must be called every time the visible image changes:
        - Original Image
        - Color Mapping
        - Color Mapping All
        - Recoloring Color Mapping All
        """
        if pil_source is None:
            return

        if not hasattr(self, "image_view_source"):
            self.image_view_source = {}

        if not hasattr(self, "image_view_state"):
            self.image_view_state = {}

        self.image_view_source[window_id] = pil_source

        if reset_zoom or window_id not in self.image_view_state:
            w, h = pil_source.size
            self.image_view_state[window_id] = {
                "zoom": 1.0,
                "cx": w / 2,
                "cy": h / 2,
            }

        try:
            self.image_canvas.itemconfig(f"{window_id}_pct_text", text="")
        except Exception:
            pass


    def _ensure_image_zoom_mousewheel_binding(self):
        """
        Bind mouse wheel zoom once directly to the image canvas.

        Important:
        - Image zoom is bound directly to image_canvas.
        - Scrollable panels use independent pointer-aware dispatchers, so
          their wheel handling cannot replace or remove this binding.
        """
        if getattr(self, "_image_zoom_mousewheel_bound", False):
            return

        if not hasattr(self, "image_canvas"):
            return

        if not hasattr(self, "_image_zoom_callbacks"):
            self._image_zoom_callbacks = {}

        def _get_window_id_from_current_canvas_item():
            """
            Try to recover the floating window id from the canvas item currently
            under the mouse pointer.
            """
            try:
                current_items = self.image_canvas.find_withtag("current")
                if not current_items:
                    return None

                tags = self.image_canvas.gettags(current_items[0])

                for tag in tags:
                    if (
                        hasattr(self, "floating_window_state")
                        and tag in self.floating_window_state
                    ):
                        return tag

            except Exception:
                pass

            return None

        def _event_is_inside_image(window_id, event):
            """
            Ensure the wheel event happened inside the displayed image area,
            not just somewhere else in the image canvas.
            """
            try:
                if (
                    not hasattr(self, "floating_window_state")
                    or window_id not in self.floating_window_state
                ):
                    return False

                st = self.floating_window_state[window_id]

                IMG_LEFT_PAD = 12
                IMG_TOP_PAD = 44

                img_left = st["x"] + IMG_LEFT_PAD
                img_top = st["y"] + IMG_TOP_PAD
                img_right = img_left + st["w"]
                img_bottom = img_top + st["h"]

                abs_x = self.image_canvas.canvasx(event.x)
                abs_y = self.image_canvas.canvasy(event.y)

                return img_left <= abs_x < img_right and img_top <= abs_y < img_bottom

            except Exception:
                return False

        def _get_legend_target_window():
            """
            Return the image id whose canvas-native mapping legend is currently
            under the mouse pointer. Mapping legends are drawn with normal Canvas
            primitives, so wheel events must be dispatched from the Canvas itself:
            Canvas.tag_bind() does not accept <MouseWheel>.
            """
            try:
                current_items = self.image_canvas.find_withtag("current")
                if not current_items:
                    return None

                tags = self.image_canvas.gettags(current_items[0])
                if "legend" not in tags:
                    return None

                panels = getattr(self.app, "proto_options", {}) or {}
                for tag in tags:
                    if tag in panels:
                        return tag
            except Exception:
                pass

            return None

        def _get_zoom_target_window(event):
            """
            Get the current floating image window that should receive the zoom event.
            Prefer the hover window, but fall back to the canvas current item.
            """
            window_id = getattr(self, "_image_zoom_hover_window", None)

            if not window_id:
                window_id = _get_window_id_from_current_canvas_item()

            if not window_id:
                return None

            if not _event_is_inside_image(window_id, event):
                return None

            return window_id

        def _dispatch_mousewheel(event):
            # Mapping legend scrolling has priority over image zoom whenever the
            # pointer is physically over the legend. This keeps both behaviors on
            # one legal Canvas-level <MouseWheel> binding.
            legend_window = _get_legend_target_window()
            if legend_window:
                delta = -1 if getattr(event, "delta", 0) > 0 else 1
                return self.app._scroll_proto_options(legend_window, delta)

            window_id = _get_zoom_target_window(event)
            if not window_id:
                return None

            callbacks = self._image_zoom_callbacks.get(window_id)
            if not callbacks:
                return None

            callback = callbacks.get("wheel")
            if callback:
                return callback(event)

            return None

        def _dispatch_linux_wheel_up(event):
            legend_window = _get_legend_target_window()
            if legend_window:
                return self.app._scroll_proto_options(legend_window, -1)

            window_id = _get_zoom_target_window(event)
            if not window_id:
                return None

            callbacks = self._image_zoom_callbacks.get(window_id)
            if not callbacks:
                return None

            callback = callbacks.get("linux_up")
            if callback:
                return callback(event)

            return None

        def _dispatch_linux_wheel_down(event):
            legend_window = _get_legend_target_window()
            if legend_window:
                return self.app._scroll_proto_options(legend_window, 1)

            window_id = _get_zoom_target_window(event)
            if not window_id:
                return None

            callbacks = self._image_zoom_callbacks.get(window_id)
            if not callbacks:
                return None

            callback = callbacks.get("linux_down")
            if callback:
                return callback(event)

            return None

        # Bind directly to the image canvas, not globally. Scrollable panels
        # use their own pointer-aware Toplevel dispatcher.
        self.image_canvas.bind("<MouseWheel>", _dispatch_mousewheel, add="+")
        self.image_canvas.bind("<Button-4>", _dispatch_linux_wheel_up, add="+")
        self.image_canvas.bind("<Button-5>", _dispatch_linux_wheel_down, add="+")

        self._image_zoom_mousewheel_bound = True


    def create_floating_window(self, x, y, filename):
        """
        Create an image card inside the automatic Image Display workspace.

        The existing canvas implementation is intentionally preserved so mapping,
        ROI inspection, saving and viewport zoom continue using the same window ids
        and callbacks. Placement and display size are managed automatically to avoid
        overlapping images.

        Cache design:
        - Window UI state is keyed by window_id.
        - Persistent mapping caches are keyed by:
            ((abs_path, mtime, size), color_space_key)
        so cached results survive window close/reopen within the same session.
        """
        if self.app._has_any_active_job():
            self.app.custom_warning(
                "Process Running",
                "Finish or cancel the current color mapping process before opening a new image."
            )
            return

        # Both controllers initialize their registries in __init__.
        self._ensure_image_zoom_mousewheel_binding()

        # Never reuse a card ID while a cancelled worker may still refer to it.
        from uuid import uuid4
        window_id = f"floating_{uuid4().hex}"

        # A malformed, removed or inaccessible file must NOT leave a ghost card
        # in any of the per-window dictionaries. Load and validate first, then
        # register the image and its cache key as one UI operation.
        try:
            before = os.stat(filename)
            with Image.open(filename) as image_file:
                pil_original = ImageOps.exif_transpose(image_file).convert("RGBA")
            after = os.stat(filename)
            if (before.st_mtime_ns, before.st_size, before.st_ino, before.st_ctime_ns) != (after.st_mtime_ns, after.st_size, after.st_ino, after.st_ctime_ns):
                raise ValueError("The image changed while it was being opened. Please reopen it.")
            original_width, original_height = pil_original.size
            if original_width < 1 or original_height < 1:
                raise ValueError("The image has invalid dimensions.")
            image_key = (
                os.path.abspath(filename),
                after.st_mtime_ns,
                after.st_size, after.st_ino, after.st_ctime_ns,
            )
        except (OSError, ValueError, MemoryError, Image.DecompressionBombError) as exc:
            self.app.custom_warning("Open Image", f"Could not open the selected image:\n{exc}")
            return False

        self.load_images_names[window_id] = filename
        self.app.window_image_key[window_id] = image_key
        self.app.CAN_APPLY_MAPPING[window_id] = bool(self.app.COLOR_SPACE)
        self.app.SHOW_ORIGINAL[window_id] = False
        self.pil_images_original[window_id] = pil_original
        self.app.image_manager.preprocessing_cache.register(window_id, pil_original)
        self.original_image_dimensions[window_id] = (original_width, original_height)

        # Initial target size (image area)
        target_w, target_h = 250, 250
        scale = min(target_w / original_width, target_h / original_height)
        new_width = max(1, int(original_width * scale))
        new_height = max(1, int(original_height * scale))

        pil_resized = pil_original.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Store resized display image and dimensions
        self.images[window_id] = pil_resized
        self.image_dimensions[window_id] = (new_width, new_height)

        # Store the currently displayed PIL image (source of truth for saving)
        self.display_pil[window_id] = pil_resized

        # Viewport zoom source and state.
        # Viewport crops never replace the original source image.
        self.image_view_source[window_id] = pil_original
        self.image_view_state[window_id] = {
            "zoom": 1.0,
            "cx": original_width / 2,
            "cy": original_height / 2,
        }


        img_tk = ImageTk.PhotoImage(pil_resized)
        self.floating_images[window_id] = img_tk
        self.original_images[window_id] = img_tk

        # Window paddings
        PAD_X = 24
        PAD_Y = 50
        TITLE_H = 34
        IMG_TOP_PAD = 44
        IMG_LEFT_PAD = 12
        HANDLE_SIZE = 10

        # Save initial window state
        self.floating_window_state[window_id] = {
            "x": x,
            "y": y,
            "w": new_width,
            "h": new_height,
            "collapsed": False,
        }

        # Create canvas items
        self.image_canvas.create_rectangle(
            x, y, x + new_width + PAD_X, y + new_height + PAD_Y,
            outline="#cfd5dd", fill="#ffffff", width=1,
            tags=(window_id, "floating", f"{window_id}_bg")
        )

        self.image_canvas.create_rectangle(
            x, y, x + new_width + PAD_X, y + TITLE_H,
            outline="#cfd5dd", fill="#f1f3f6",
            tags=(window_id, "floating", f"{window_id}_title")
        )

        self.image_canvas.create_text(
            x + 34, y + TITLE_H / 2, anchor="w",
            text=os.path.basename(filename),
            fill="#1f2937", font=("Segoe UI", 9, "bold"),
            tags=(window_id, "floating", f"{window_id}_title_text")
        )

        self.image_canvas.create_rectangle(
            x + new_width + PAD_X - 7, y + 7,
            x + new_width + PAD_X - 27, y + 27,
            outline="#d9dde3", fill="#ffffff",
            tags=(window_id, "floating", f"{window_id}_close_button", f"{window_id}_close_rect")
        )
        self.image_canvas.create_text(
            x + new_width + PAD_X - 17, y + 17,
            text="×", fill="#8a1f1f", font=("Segoe UI", 11, "bold"),
            tags=(window_id, "floating", f"{window_id}_close_button", f"{window_id}_close_text")
        )

        # Keep only the compact minimize control in each card header.
        # Focus remains available from the workspace toolbar / context menu,
        # while manual enlargement is handled by the bottom-right resize grip.

        self.image_canvas.create_rectangle(
            x + new_width + PAD_X - 53, y + 7,
            x + new_width + PAD_X - 33, y + 27,
            outline="#d9dde3", fill="#ffffff",
            tags=(window_id, "floating", f"{window_id}_minimize_button", f"{window_id}_minimize_rect")
        )
        self.image_canvas.create_text(
            x + new_width + PAD_X - 43, y + 17,
            text="−", fill=UtilsTools.UI_ACCENT, font=("Segoe UI", 11, "bold"),
            tags=(window_id, "floating", f"{window_id}_minimize_button", f"{window_id}_minimize_text")
        )

        self.image_canvas.create_text(
            x + 15, y + TITLE_H / 2, text="⋮",
            fill=UtilsTools.UI_ACCENT, font=("Segoe UI", 13, "bold"),
            tags=(window_id, "floating", f"{window_id}_arrow_button", f"{window_id}_arrow_text")
        )

        self.image_canvas.create_image(
            x + IMG_LEFT_PAD, y + IMG_TOP_PAD,
            anchor="nw",
            image=self.floating_images[window_id],
            tags=(window_id, "floating", f"{window_id}_click_image", f"{window_id}_img_item")
        )

        self.image_canvas.create_text(
            x + IMG_LEFT_PAD + new_width / 2,
            y + IMG_TOP_PAD + new_height + 8,
            anchor="n",
            text="",
            fill="#374151",
            font=("Sans", 8),
            tags=(window_id, "floating", f"{window_id}_pct_text")
        )

        hx1 = x + new_width + PAD_X - HANDLE_SIZE - 2
        hy1 = y + new_height + PAD_Y - HANDLE_SIZE - 2
        hx2 = x + new_width + PAD_X - 2
        hy2 = y + new_height + PAD_Y - 2
        self.image_canvas.create_rectangle(
            hx1, hy1, hx2, hy2,
            outline="black", fill="lightgray",
            tags=(window_id, "floating", f"{window_id}_resize_handle")
        )

        # Helpers to relayout + resize
        def _relayout(window_id):
            """Update all canvas item positions based on stored floating window state."""
            st = self.floating_window_state[window_id]
            wx, wy, ww, wh = st["x"], st["y"], st["w"], st["h"]

            collapsed = bool(st.get("collapsed", False))
            legend_h = 0 if collapsed else self._workspace_legend_height(window_id)
            legend_info = getattr(self.app, "proto_options", {}).get(window_id, {})
            legend_w = 0 if collapsed or not isinstance(legend_info, dict) else max(180, int(ww))

            # The mapping panel now sits below the image. Card width therefore
            # remains compact, only growing when a very narrow manually resized
            # image needs the selector's 210 px minimum width.
            base_right = wx + ww + PAD_X
            legend_right = wx + IMG_LEFT_PAD + legend_w + 12 if legend_h else base_right
            card_right = max(base_right, legend_right)

            if collapsed:
                card_bottom = wy + TITLE_H
            elif legend_h:
                # The mapping panel is the final visual element of the card.
                # Use the same dynamic gap as _reposition_proto_options and end
                # the card exactly at the panel border: no white strip below.
                legend_info = getattr(self.app, "proto_options", {}).get(window_id, {})
                panel_gap = int(legend_info.get("gap", 7)) if isinstance(legend_info, dict) else 7
                panel_y = wy + IMG_TOP_PAD + wh + panel_gap
                card_bottom = panel_y + legend_h
            else:
                card_bottom = wy + wh + PAD_Y

            self.image_canvas.coords(f"{window_id}_bg", wx, wy, card_right, card_bottom)
            self.image_canvas.coords(f"{window_id}_title", wx, wy, card_right, wy + TITLE_H)

            self.image_canvas.coords(f"{window_id}_title_text", wx + 34, wy + TITLE_H / 2)
            self.image_canvas.coords(f"{window_id}_arrow_text", wx + 15, wy + TITLE_H / 2)

            self.image_canvas.coords(
                f"{window_id}_close_rect",
                card_right - 7, wy + 7,
                card_right - 27, wy + 27
            )
            self.image_canvas.coords(f"{window_id}_close_text", card_right - 17, wy + 17)

            self.image_canvas.coords(
                f"{window_id}_minimize_rect",
                card_right - 53, wy + 7,
                card_right - 33, wy + 27
            )
            self.image_canvas.coords(f"{window_id}_minimize_text", card_right - 43, wy + 17)

            self.image_canvas.coords(f"{window_id}_img_item", wx + IMG_LEFT_PAD, wy + IMG_TOP_PAD)

            hx1 = wx + ww + PAD_X - HANDLE_SIZE - 2
            hy1 = wy + wh + PAD_Y - HANDLE_SIZE - 2
            hx2 = wx + ww + PAD_X - 2
            hy2 = wy + wh + PAD_Y - 2
            self.image_canvas.coords(f"{window_id}_resize_handle", hx1, hy1, hx2, hy2)

            self.app._reposition_proto_options(window_id)

            # Keep mapping coverage centered under the displayed image.
            # Its position therefore remains correct after Grid/Focus/manual
            # resizing instead of being visually attached to the left edge.
            pct_y = wy + IMG_TOP_PAD + wh + 4
            legend_info = getattr(self.app, "proto_options", {}).get(window_id, {})
            if isinstance(legend_info, dict) and legend_info:
                gap_now = int(legend_info.get("gap", 7))
                if gap_now >= 18:
                    pct_y = wy + IMG_TOP_PAD + wh + 3

            self.image_canvas.coords(
                f"{window_id}_pct_text",
                wx + IMG_LEFT_PAD + ww / 2,
                pct_y,
            )

            self.app._reposition_window_loading(window_id)

            if hasattr(self, "_original_sampling_state") and window_id in self._original_sampling_state:
                state = self._original_sampling_state[window_id]
                state["img_x"] = wx + IMG_LEFT_PAD
                state["img_y"] = wy + IMG_TOP_PAD
                state["draw_w"] = ww
                state["draw_h"] = wh

            self._sync_workspace_card_item_states(window_id)
            self._focus_floating_window(window_id)

        def _update_image_to_size(window_id, target_w, target_h, reset_view=True):
            """
            Resize the floating image window while preserving aspect ratio.

            Important:
            - This changes the window/image display size.
            - Mouse-wheel zoom does NOT call this function anymore.
            - Mouse-wheel zoom only changes the viewport crop.
            """
            source_pil = self.image_view_source.get(
                window_id,
                self.pil_images_original[window_id]
            )

            ow, oh = source_pil.size

            scale = min(target_w / ow, target_h / oh)
            new_w = max(30, int(ow * scale))
            new_h = max(30, int(oh * scale))

            self.floating_window_state[window_id]["w"] = new_w
            self.floating_window_state[window_id]["h"] = new_h
            self.image_dimensions[window_id] = (new_w, new_h)

            if reset_view:
                self.image_view_state[window_id] = {
                    "zoom": 1.0,
                    "cx": ow / 2,
                    "cy": oh / 2,
                }

            _render_image_view(window_id)
            _relayout(window_id)


        # Viewport zoom helpers
        def _clamp(value, min_value, max_value):
            """Clamp value between min_value and max_value."""
            return max(min_value, min(max_value, value))


        def _get_view_crop_box(window_id):
            """Return the visible crop in current view-source coordinates."""
            crop = self._get_image_view_crop_box(window_id)
            if crop is None:
                source_pil = self.image_view_source.get(
                    window_id, self.pil_images_original[window_id]
                )
                return 0.0, 0.0, float(source_pil.size[0]), float(source_pil.size[1])
            return crop


        def _render_image_view(window_id):
            """
            Render the current viewport crop into the existing floating image size.

            This is the key difference:
            - The image item keeps the same width/height.
            - The crop area changes according to zoom and center.
            """
            if window_id not in self.floating_window_state:
                return

            source_pil = self.image_view_source.get(
                window_id,
                self.pil_images_original[window_id]
            )

            st = self.floating_window_state[window_id]
            draw_w = max(1, int(st["w"]))
            draw_h = max(1, int(st["h"]))

            left, top, right, bottom = _get_view_crop_box(window_id)

            crop = source_pil.crop((
                int(round(left)),
                int(round(top)),
                int(round(right)),
                int(round(bottom))
            ))

            pil_view = crop.resize((draw_w, draw_h), Image.Resampling.LANCZOS)

            self.images[window_id] = pil_view
            self.image_dimensions[window_id] = (draw_w, draw_h)
            self.display_pil[window_id] = pil_view

            img_tk = ImageTk.PhotoImage(pil_view)
            self.floating_images[window_id] = img_tk

            self.image_canvas.itemconfig(
                f"{window_id}_img_item",
                image=self.floating_images[window_id]
            )


        def _canvas_point_to_view_source(event, window_id):
            """Map a mouse event to the current view-source coordinates."""
            abs_x = self.image_canvas.canvasx(event.x)
            abs_y = self.image_canvas.canvasy(event.y)
            return self._canvas_xy_to_view_source(window_id, abs_x, abs_y)


        def _canvas_point_to_original_image(event, window_id):
            """Map a mouse event to the real full-resolution original pixel."""
            abs_x = self.image_canvas.canvasx(event.x)
            abs_y = self.image_canvas.canvasy(event.y)
            return self._canvas_xy_to_original_image(window_id, abs_x, abs_y)


        def _apply_zoom(window_id, factor=None, reset=False, event=None):
            """
            Apply zoom to the viewport without changing the floating window size.

            Wheel zoom behavior:
            - The point under the cursor remains under the cursor after zooming.
            - Only the internal crop changes.
            """
            if self.app._has_active_job(window_id):
                return "break"

            try:
                self._clear_original_selection_rectangle(window_id)
            except Exception:
                pass

            source_pil = self.image_view_source.get(
                window_id,
                self.pil_images_original[window_id]
            )
            source_w, source_h = source_pil.size

            if reset:
                self.image_view_state[window_id] = {
                    "zoom": 1.0,
                    "cx": source_w / 2,
                    "cy": source_h / 2,
                }

                _render_image_view(window_id)

                try:
                    self.image_canvas.itemconfig(f"{window_id}_pct_text", text="")
                except Exception:
                    pass

                return "break"

            if factor is None:
                return "break"

            state = self.image_view_state.get(window_id)
            if not state:
                state = {
                    "zoom": 1.0,
                    "cx": source_w / 2,
                    "cy": source_h / 2,
                }
                self.image_view_state[window_id] = state

            point_info = None
            if event is not None:
                point_info = _canvas_point_to_view_source(event, window_id)

            old_zoom = float(state.get("zoom", 1.0))
            new_zoom = _clamp(old_zoom * factor, 1.0, 12.0)

            # If zoom did not change, stop.
            if abs(new_zoom - old_zoom) < 1e-9:
                return "break"

            state["zoom"] = new_zoom

            # If the mouse is over the image, keep that source point under the cursor.
            if point_info is not None:
                source_x, source_y, rel_x, rel_y = point_info

                st = self.floating_window_state[window_id]
                draw_w = max(1, int(st["w"]))
                draw_h = max(1, int(st["h"]))

                crop_w = max(1.0, source_w / new_zoom)
                crop_h = max(1.0, source_h / new_zoom)

                rel_fx = rel_x / draw_w
                rel_fy = rel_y / draw_h

                new_left = source_x - rel_fx * crop_w
                new_top = source_y - rel_fy * crop_h

                new_left = _clamp(new_left, 0, max(0, source_w - crop_w))
                new_top = _clamp(new_top, 0, max(0, source_h - crop_h))

                state["cx"] = new_left + crop_w / 2
                state["cy"] = new_top + crop_h / 2

            _render_image_view(window_id)

            try:
                self.image_canvas.itemconfig(
                    f"{window_id}_pct_text",
                    text=f"Zoom: {new_zoom * 100:.0f}%"
                )
            except Exception:
                pass

            return "break"


        def _zoom_mousewheel(event):
            """Mouse wheel zoom handler for Windows/macOS."""
            if event.delta > 0:
                return _apply_zoom(window_id, factor=1.15, event=event)
            else:
                return _apply_zoom(window_id, factor=1 / 1.15, event=event)


        def _zoom_linux_in(event):
            """Mouse wheel up zoom handler for Linux."""
            return _apply_zoom(window_id, factor=1.15, event=event)


        def _zoom_linux_out(event):
            """Mouse wheel down zoom handler for Linux."""
            return _apply_zoom(window_id, factor=1 / 1.15, event=event)


        def _activate_image_zoom(event):
            """Mark this floating image as the current mouse-wheel zoom target."""
            self._image_zoom_hover_window = window_id
            return None


        def _deactivate_image_zoom(event):
            """Clear the mouse-wheel zoom target when leaving this image."""
            if getattr(self, "_image_zoom_hover_window", None) == window_id:
                self._image_zoom_hover_window = None
            return None

        # Right-drag viewport move
        def _start_view_pan(event):
            """Start moving the zoomed viewport with the right mouse button."""
            if self.app._has_active_job(window_id):
                return "break"

            state = self.image_view_state.get(window_id)
            if not state or float(state.get("zoom", 1.0)) <= 1.000001:
                # At Fit there is no hidden image area to move.
                return "break"

            self._set_image_workspace_active(window_id)
            self._clear_image_display_selection(window_id)

            source_pil = self.image_view_source.get(
                window_id,
                self.pil_images_original.get(window_id)
            )
            if source_pil is None:
                return "break"

            source_w, source_h = source_pil.size
            zoom = max(1.0, float(state.get("zoom", 1.0)))
            crop_w = max(1.0, source_w / zoom)
            crop_h = max(1.0, source_h / zoom)

            self._image_view_pan_state = {
                "window_id": window_id,
                "start_x": self.image_canvas.canvasx(event.x),
                "start_y": self.image_canvas.canvasy(event.y),
                "start_cx": float(state.get("cx", source_w / 2.0)),
                "start_cy": float(state.get("cy", source_h / 2.0)),
                "crop_w": crop_w,
                "crop_h": crop_h,
                "source_w": float(source_w),
                "source_h": float(source_h),
            }

            try:
                self.image_canvas.configure(cursor="fleur")
            except Exception:
                pass

            return "break"

        def _drag_view_pan(event):
            """Move the current zoom crop while right-dragging."""
            pan = getattr(self, "_image_view_pan_state", None)
            if not isinstance(pan, dict) or pan.get("window_id") != window_id:
                return "break"

            state = self.image_view_state.get(window_id)
            st = self.floating_window_state.get(window_id)
            if not state or not st:
                return "break"

            draw_w = max(1.0, float(st.get("w", 1)))
            draw_h = max(1.0, float(st.get("h", 1)))

            current_x = self.image_canvas.canvasx(event.x)
            current_y = self.image_canvas.canvasy(event.y)
            dx = current_x - pan["start_x"]
            dy = current_y - pan["start_y"]

            # Convert displayed-pixel movement to source-image movement.
            # Dragging the image right/down moves the viewport center left/up.
            source_dx = dx * (pan["crop_w"] / draw_w)
            source_dy = dy * (pan["crop_h"] / draw_h)

            half_w = pan["crop_w"] / 2.0
            half_h = pan["crop_h"] / 2.0
            min_cx = half_w
            max_cx = max(half_w, pan["source_w"] - half_w)
            min_cy = half_h
            max_cy = max(half_h, pan["source_h"] - half_h)

            state["cx"] = _clamp(pan["start_cx"] - source_dx, min_cx, max_cx)
            state["cy"] = _clamp(pan["start_cy"] - source_dy, min_cy, max_cy)

            _render_image_view(window_id)
            return "break"

        def _end_view_pan(_event=None):
            """Finish a right-drag viewport move."""
            pan = getattr(self, "_image_view_pan_state", None)
            if isinstance(pan, dict) and pan.get("window_id") == window_id:
                self._image_view_pan_state = None

            try:
                self.image_canvas.configure(cursor="")
            except Exception:
                pass

            return "break"


        # Menu action wrappers
        def _show_original_image_action():
            self._clear_image_display_selection(window_id)
            self.app.show_original_image(window_id)

        def _color_mapping_action():
            self._clear_image_display_selection(window_id)
            self.app.color_mapping(window_id)

        def _color_mapping_all_action():
            self._clear_image_display_selection(window_id)
            self.app.color_mapping_all(window_id)

        # Close window
        def close_window(event):
            """Close an image only after the user accepts cancelling its jobs."""
            controller = getattr(self, "_full_resolution_workspace_controller", None)
            owns_workspace = (controller is not None and not getattr(controller, "_closed", True)
                              and controller.source_window_id == window_id)
            workspace_thread = getattr(controller, "_worker", None) if owns_workspace else None
            workspace_busy = bool(owns_workspace and (
                getattr(controller, "_mapping_busy", False)
                or getattr(controller, "_saving", False)
                or (workspace_thread is not None and workspace_thread.is_alive())))
            card_busy = self.app._has_active_job(window_id)
            if workspace_busy or card_busy:
                confirm = messagebox.askyesno(
                    "Cancel Process",
                    "An operation is still running for this image.\n\n"
                    "Do you want to cancel it and close the image and its workspace?",
                    parent=self.root,
                )
                if not confirm:
                    return "break"
            if card_busy:
                self.app._cancel_window_job(window_id)
            if owns_workspace:
                controller.close()
            self.app.image_manager.preprocessing_cache.discard(window_id)

            try:
                self._disable_original_rectangle_sampling(window_id)
            except Exception:
                pass

            self.image_canvas.delete(window_id)

            for attr_name in (
                "floating_images",
                "pil_images_original",
                "floating_window_state",
                "images",
                "display_pil",
                "original_images",
                "image_dimensions",
                "original_image_dimensions",
                "_resize_callbacks",
                "_pixel_click_callbacks",
                "current_protos",
                "load_images_names",
                "window_image_key",
                "window_mapping_mode",
                "image_view_source",
                "image_view_state",
                "_image_zoom_callbacks",
                "CAN_APPLY_MAPPING",
                "SHOW_ORIGINAL",
                "modified_image",
                "mapping_locked_until_original",
            ):
                if hasattr(self.app, attr_name):
                    d = getattr(self.app, attr_name)
                    if isinstance(d, dict) and window_id in d:
                        del d[window_id]

            if getattr(self, "_image_zoom_hover_window", None) == window_id:
                self._image_zoom_hover_window = None
            pan_state = getattr(self, "_image_view_pan_state", None)
            if isinstance(pan_state, dict) and pan_state.get("window_id") == window_id:
                self._image_view_pan_state = None

            if hasattr(self.app, "proto_options") and window_id in self.app.proto_options:
                info = self.app.proto_options.get(window_id)
                if info:
                    frame = info.get("frame")
                    canvas_item = info.get("canvas_item")

                    try:
                        if canvas_item:
                            self.image_canvas.delete(canvas_item)
                    except Exception:
                        pass

                    try:
                        if frame and frame.winfo_exists():
                            frame.destroy()
                    except Exception:
                        pass

                    del self.app.proto_options[window_id]

            if getattr(self, "_image_workspace_focus_id", None) == window_id:
                self._image_workspace_focus_id = None
                self._image_workspace_focus_saved_state = None
                self._image_workspace_focus_saved_collapsed = None
            try:
                getattr(self.app, "_mapping_all_palette_by_window", {}).pop(window_id, None)
                getattr(self.app, "_mapping_all_pack_by_window", {}).pop(window_id, None)
            except Exception:
                pass

            if getattr(self, "_image_workspace_active_id", None) == window_id:
                remaining = self._image_workspace_window_ids()
                self._image_workspace_active_id = remaining[0] if remaining else None

            try:
                self._image_workspace_callbacks.pop(window_id, None)
            except Exception:
                pass

            self._schedule_image_workspace_reflow()

        # Dropdown menu
        def show_menu_image(event):
            """Display per-image view, mapping, zoom and save actions."""
            if self.app._has_active_job(window_id):
                return "break"

            menu = Menu(self.root, tearoff=0)
            is_focus = getattr(self, "_image_workspace_focus_id", None) == window_id
            current_mode = getattr(self.app, "window_mapping_mode", {}).get(window_id)
            mapping_enabled = bool(getattr(self.app, "COLOR_SPACE", False))

            # Focus is enter-only. While Focus View is active, Grid is the
            # single, predictable way back to the multi-image workspace.
            menu.add_command(
                label="Focus Image",
                state=DISABLED if is_focus else NORMAL,
                command=lambda: self._set_image_workspace_focus(window_id)
            )
            menu.add_command(
                label="Open in Image Workspace (Original Resolution)",
                command=lambda: self.open_full_resolution_image_workspace(window_id)
            )

            menu.add_separator()

            # These three are direct view modes. Mapping computations always
            # use pil_images_original, so changing mode never needs an explicit
            # intermediate return to Original Image.
            menu.add_command(
                label="Original Image",
                state=DISABLED if current_mode is None else NORMAL,
                command=_show_original_image_action
            )
            menu.add_command(
                label="Color Mapping",
                state=DISABLED if (not mapping_enabled or current_mode == "single") else NORMAL,
                command=_color_mapping_action
            )
            old_mapping_locked = bool(
                getattr(self.app, "mapping_locked_until_original", {}).get(window_id, False)
            )
            menu.add_command(
                label="Color Mapping All",
                state=DISABLED if (
                    not mapping_enabled or (current_mode == "all" and not old_mapping_locked)
                ) else NORMAL,
                command=_color_mapping_all_action
            )

            menu.add_separator()

            zoom_menu = Menu(menu, tearoff=0)
            zoom_menu.add_command(
                label="Zoom In",
                command=lambda: _apply_zoom(window_id, factor=1.15)
            )
            zoom_menu.add_command(
                label="Zoom Out",
                command=lambda: _apply_zoom(window_id, factor=1 / 1.15)
            )
            zoom_menu.add_command(
                label="Fit",
                command=lambda: _apply_zoom(window_id, reset=True)
            )
            menu.add_cascade(label="Zoom", menu=zoom_menu)

            menu.add_separator()
            menu.add_command(
                label="Save Image",
                command=lambda: self.save_image(window_id=window_id)
            )

            menu.post(event.x_root, event.y_root)
            return "break"

        # Move window
        def start_move(event):
            if self.app._has_active_job(window_id):
                return "break"
            if getattr(self, "_image_workspace_focus_id", None) is not None:
                return "break"

            self._set_image_workspace_active(window_id)

            self._clear_image_display_selection(window_id)

            mx = self.image_canvas.canvasx(event.x)
            my = self.image_canvas.canvasy(event.y)
            self._image_workspace_move_state = {
                "window_id": window_id,
                "x": mx,
                "y": my,
                "start_x": mx,
                "start_y": my,
                "moved": False,
            }
            return "break"

        def move_window(event):
            if self.app._has_active_job(window_id):
                return "break"

            move_state = getattr(self, "_image_workspace_move_state", None)
            if not isinstance(move_state, dict) or move_state.get("window_id") != window_id:
                return "break"

            mx = self.image_canvas.canvasx(event.x)
            my = self.image_canvas.canvasy(event.y)

            # A simple click/double-click must not turn Grid into Manual. Only
            # an actual drag changes the workspace layout mode.
            if not move_state.get("moved", False):
                total_dx = mx - move_state["start_x"]
                total_dy = my - move_state["start_y"]
                if abs(total_dx) < 3 and abs(total_dy) < 3:
                    return "break"
                self._set_image_workspace_manual()
                move_state["moved"] = True

            dx = mx - move_state["x"]
            dy = my - move_state["y"]

            st = self.floating_window_state[window_id]
            st["x"] = max(6, st["x"] + dx)
            st["y"] = max(6, st["y"] + dy)

            _relayout(window_id)
            self._update_manual_workspace_scrollregion()

            move_state["x"] = mx
            move_state["y"] = my
            return "break"

        def end_move(_event):
            move_state = getattr(self, "_image_workspace_move_state", None)
            if isinstance(move_state, dict) and move_state.get("window_id") == window_id:
                self._image_workspace_move_state = None
            self._update_manual_workspace_scrollregion()
            return "break"

        # Resize window
        def start_resize(event):
            if self.app._has_active_job(window_id):
                return "break"
            if getattr(self, "_image_workspace_focus_id", None) is not None:
                return "break"

            self._set_image_workspace_active(window_id)
            self._set_image_workspace_manual()

            self._clear_image_display_selection(window_id)

            st = self.floating_window_state[window_id]
            self._resize_start = {
                "w": st["w"],
                "h": st["h"],
                "mx": self.image_canvas.canvasx(event.x),
                "my": self.image_canvas.canvasy(event.y)
            }

        def do_resize(event):
            if self.app._has_active_job(window_id):
                return "break"

            if not hasattr(self, "_resize_start") or self._resize_start is None:
                return "break"

            mx = self.image_canvas.canvasx(event.x)
            my = self.image_canvas.canvasy(event.y)

            start = self._resize_start
            dw = mx - start["mx"]
            dh = my - start["my"]

            desired_w = max(30, int(start["w"] + dw))
            desired_h = max(30, int(start["h"] + dh))

            _update_image_to_size(
                window_id,
                desired_w,
                desired_h,
                reset_view=True
            )
            return "break"

        def end_resize(event):
            """
            Finish resizing.

            Important:
            - We do NOT clear persistent caches here.
            - Cache keys already include (width, height), so a resize naturally
            leads to a different cache entry when needed.
            """
            if self.app._has_active_job(window_id):
                return "break"

            self.app._cancel_window_job(window_id)
            self._resize_start = None
            self._update_manual_workspace_scrollregion()

            try:
                self._clear_original_selection_rectangle(window_id)
            except Exception:
                pass

            try:
                self.image_canvas.itemconfig(f"{window_id}_pct_text", text="")
            except Exception:
                pass

            return "break"

        if not hasattr(self, "_resize_callbacks"):
            self._resize_callbacks = {}
        self._resize_callbacks[window_id] = (start_resize, do_resize, end_resize)

        # Pixel picking
        def get_pixel_value(event, window_id=window_id):
            if self.app._has_active_job(window_id):
                return "break"

            self._set_image_workspace_active(window_id)

            point_info = _canvas_point_to_original_image(event, window_id)
            if point_info is None:
                return "break"

            x_original, y_original, _rel_x, _rel_y = point_info

            pil_original = self.pil_images_original[window_id]
            ow, oh = pil_original.size

            x_original = int(_clamp(x_original, 0, ow - 1))
            y_original = int(_clamp(y_original, 0, oh - 1))

            pixel_value = pil_original.getpixel((x_original, y_original))

            # If image has transparency, ignore fully transparent pixels
            if len(pixel_value) == 4:
                r, g, b, a = pixel_value

                if a == 0:
                    return "break"

                pixel_rgb = (r, g, b)
            else:
                pixel_rgb = pixel_value

            pixel_lab = UtilsTools.analysis_rgb_to_lab(pixel_rgb)

            if self.app.COLOR_SPACE:
                self.app.display_pixel_value(
                    x_original,
                    y_original,
                    pixel_lab,
                    is_average=False,
                    image_id=window_id,
                    native_rgb=pixel_rgb
                )

            return "break"

        if not hasattr(self, "_pixel_click_callbacks"):
            self._pixel_click_callbacks = {}
        self._pixel_click_callbacks[window_id] = get_pixel_value

        # Bindings
        # Title drag restores the original ability to move cards. The first drag
        # switches the workspace from automatic Grid to Manual layout. Grid can
        # be pressed at any time to arrange everything again.
        for title_tag in (f"{window_id}_title", f"{window_id}_title_text"):
            self.image_canvas.tag_bind(title_tag, "<Button-1>", start_move)
            self.image_canvas.tag_bind(title_tag, "<B1-Motion>", move_window)
            self.image_canvas.tag_bind(title_tag, "<ButtonRelease-1>", end_move)
            self.image_canvas.tag_bind(
                title_tag,
                "<Double-Button-1>",
                lambda _e, wid=window_id: self._toggle_image_workspace_focus(wid),
            )

        self.image_canvas.tag_bind(f"{window_id}_close_button", "<Button-1>", close_window)
        self.image_canvas.tag_bind(
            f"{window_id}_minimize_button",
            "<Button-1>",
            lambda _e, wid=window_id: self._toggle_image_card_minimize(wid),
        )
        self.image_canvas.tag_bind(f"{window_id}_click_image", "<Button-1>", get_pixel_value)
        self.image_canvas.tag_bind(f"{window_id}_arrow_button", "<Button-1>", show_menu_image)

        # Right-drag moves only the internal zoom viewport. It never moves the
        # image card itself; card movement remains a left-drag on the title bar.
        for button_num in (2, 3):
            self.image_canvas.tag_bind(
                f"{window_id}_click_image", f"<ButtonPress-{button_num}>", _start_view_pan
            )
            self.image_canvas.tag_bind(
                f"{window_id}_click_image", f"<B{button_num}-Motion>", _drag_view_pan
            )
            self.image_canvas.tag_bind(
                f"{window_id}_click_image", f"<ButtonRelease-{button_num}>", _end_view_pan
            )

        # Mouse hover target for wheel zoom.
        # Canvas.tag_bind() does not support <MouseWheel>, so wheel dispatch is
        # bound directly to image_canvas and routed to the hovered image tag.
        self.image_canvas.tag_bind(
            f"{window_id}_click_image",
            "<Enter>",
            _activate_image_zoom
        )

        self.image_canvas.tag_bind(
            f"{window_id}_click_image",
            "<Leave>",
            _deactivate_image_zoom
        )

        self._image_zoom_callbacks[window_id] = {
            "wheel": _zoom_mousewheel,
            "linux_up": _zoom_linux_in,
            "linux_down": _zoom_linux_out,
        }

        self.image_canvas.tag_bind(f"{window_id}_resize_handle", "<Button-1>", start_resize)
        self.image_canvas.tag_bind(f"{window_id}_resize_handle", "<B1-Motion>", do_resize)
        self.image_canvas.tag_bind(f"{window_id}_resize_handle", "<ButtonRelease-1>", end_resize)

        self._image_workspace_callbacks[window_id] = {
            "relayout": _relayout,
            "resize": _update_image_to_size,
        }

        _relayout(window_id)

        try:
            self._enable_original_rectangle_sampling(
                window_id=window_id,
                target_w=new_width,
                target_h=new_height
            )
        except Exception as e:
            print(f"Warning enabling original rectangle sampling for {window_id}: {e}")

        self._set_image_workspace_active(window_id)
        self._schedule_image_workspace_reflow(delay=0)


    def _focus_floating_window(self, window_id):
        """Bring one complete image card, including its mapping panel, to the front."""
        try:
            # All pieces, including the legend, are native Canvas items carrying
            # the same window_id tag, so they really move through one z-order.
            self.image_canvas.tag_raise(window_id)
            self.app._raise_all_loading_panels()
        except Exception:
            pass


    def _enable_original_rectangle_sampling(self, window_id, target_w, target_h):
        """
        Enable click + drag rectangle sampling for the ORIGINAL image shown in a floating window.

        The displayed image is anchored at the same position used in create_floating_window():
            x + 15, y + IMG_TOP_PAD
        so coordinates are mapped back to the original PIL image using the current
        floating window geometry and the current displayed size.
        """
        if not hasattr(self, "_original_sampling_state"):
            self._original_sampling_state = {}

        if not hasattr(self, "floating_window_state") or window_id not in self.floating_window_state:
            return

        if not hasattr(self, "pil_images_original") or window_id not in self.pil_images_original:
            return

        pil_original = self.pil_images_original[window_id]
        full_w, full_h = pil_original.size

        # Read current floating window geometry
        st = self.floating_window_state[window_id]
        wx, wy = st["x"], st["y"]

        # These values must match create_floating_window()
        IMG_LEFT_PAD = 12
        IMG_TOP_PAD = 44

        # Top-left corner of the displayed image inside the main canvas
        img_x = wx + IMG_LEFT_PAD
        img_y = wy + IMG_TOP_PAD

        self._original_sampling_state[window_id] = {
            "dragging": False,
            "drag_start": None,
            "rect_id": None,
            "img_x": img_x,
            "img_y": img_y,
            "draw_w": max(1, int(target_w)),
            "draw_h": max(1, int(target_h)),
            "full_w": full_w,
            "full_h": full_h,
        }

        # Replace the simple click behavior with press-drag-release behavior
        self.image_canvas.tag_bind(
            f"{window_id}_img_item",
            "<ButtonPress-1>",
            lambda e, wid=window_id: self._on_original_mouse_down(e, wid)
        )
        self.image_canvas.tag_bind(
            f"{window_id}_img_item",
            "<B1-Motion>",
            lambda e, wid=window_id: self._on_original_mouse_drag(e, wid)
        )
        self.image_canvas.tag_bind(
            f"{window_id}_img_item",
            "<ButtonRelease-1>",
            lambda e, wid=window_id: self._on_original_mouse_up(e, wid)
        )

        # Keep the fallback tag in sync too
        self.image_canvas.tag_bind(
            f"{window_id}_click_image",
            "<ButtonPress-1>",
            lambda e, wid=window_id: self._on_original_mouse_down(e, wid)
        )
        self.image_canvas.tag_bind(
            f"{window_id}_click_image",
            "<B1-Motion>",
            lambda e, wid=window_id: self._on_original_mouse_drag(e, wid)
        )
        self.image_canvas.tag_bind(
            f"{window_id}_click_image",
            "<ButtonRelease-1>",
            lambda e, wid=window_id: self._on_original_mouse_up(e, wid)
        )


    def _disable_original_rectangle_sampling(self, window_id):
        """
        Disable click/drag sampling for a floating image window and restore simple click picking.

        This is used whenever the displayed content is no longer the original image.
        """
        if hasattr(self, "_original_sampling_state") and window_id in self._original_sampling_state:
            self._clear_original_selection_rectangle(window_id)
            del self._original_sampling_state[window_id]

        # Remove drag-based bindings from both tags
        try:
            self.image_canvas.tag_unbind(f"{window_id}_img_item", "<ButtonPress-1>")
            self.image_canvas.tag_unbind(f"{window_id}_img_item", "<B1-Motion>")
            self.image_canvas.tag_unbind(f"{window_id}_img_item", "<ButtonRelease-1>")
        except Exception:
            pass

        try:
            self.image_canvas.tag_unbind(f"{window_id}_click_image", "<ButtonPress-1>")
            self.image_canvas.tag_unbind(f"{window_id}_click_image", "<B1-Motion>")
            self.image_canvas.tag_unbind(f"{window_id}_click_image", "<ButtonRelease-1>")
        except Exception:
            pass


    def _clip_original_canvas_point_to_image(self, x, y, window_id):
        """
        Clamp a canvas point to the visible bounds of the displayed original image.
        Returns the clipped (x, y) in canvas coordinates.
        """
        if not hasattr(self, "_original_sampling_state") or window_id not in self._original_sampling_state:
            return x, y

        state = self._original_sampling_state[window_id]

        img_x = state["img_x"]
        img_y = state["img_y"]
        draw_w = state["draw_w"]
        draw_h = state["draw_h"]

        clipped_x = max(img_x, min(img_x + draw_w, x))
        clipped_y = max(img_y, min(img_y + draw_h, y))

        return clipped_x, clipped_y


    def _on_original_mouse_down(self, event, window_id):
        """Start rectangle selection on an original floating image."""
        if not hasattr(self, "_original_sampling_state") or window_id not in self._original_sampling_state:
            return

        if self.app._has_active_job(window_id):
            return "break"

        state = self._original_sampling_state[window_id]

        canvas_x = self.image_canvas.canvasx(event.x)
        canvas_y = self.image_canvas.canvasy(event.y)
        start_x, start_y = self._clip_original_canvas_point_to_image(canvas_x, canvas_y, window_id)

        state["dragging"] = True
        state["drag_start"] = (start_x, start_y)

        if state["rect_id"] is not None:
            try:
                self.image_canvas.delete(state["rect_id"])
            except Exception:
                pass
            state["rect_id"] = None

        state["rect_id"] = self.image_canvas.create_rectangle(
            start_x, start_y, start_x, start_y,
            outline="#ff0000",
            width=2,
            tags=(window_id, "floating", f"{window_id}_selection_rect")
        )

        return "break"


    def _on_original_mouse_drag(self, event, window_id):
        """Update the selection rectangle while dragging, clipped to image bounds."""
        if not hasattr(self, "_original_sampling_state") or window_id not in self._original_sampling_state:
            return

        state = self._original_sampling_state[window_id]
        if not state.get("dragging") or state.get("rect_id") is None:
            return

        x0, y0 = state["drag_start"]
        canvas_x = self.image_canvas.canvasx(event.x)
        canvas_y = self.image_canvas.canvasy(event.y)
        x1, y1 = self._clip_original_canvas_point_to_image(canvas_x, canvas_y, window_id)

        self.image_canvas.coords(state["rect_id"], x0, y0, x1, y1)

        return "break"


    def _on_original_mouse_up(self, event, window_id):
        """
        Finish selection on the original image.

        Behavior:
        - Tiny drag: treat it as a single-pixel click.
        - Larger drag: compute the mean CIELAB of visible original pixels.
        """
        if not hasattr(self, "_original_sampling_state") or window_id not in self._original_sampling_state:
            return

        state = self._original_sampling_state[window_id]
        if not state.get("dragging"):
            return

        state["dragging"] = False

        if not hasattr(self, "pil_images_original") or window_id not in self.pil_images_original:
            return

        pil = self.pil_images_original[window_id]

        img_x = state["img_x"]
        img_y = state["img_y"]
        draw_w = state["draw_w"]
        draw_h = state["draw_h"]
        full_w = state["full_w"]
        full_h = state["full_h"]

        x0, y0 = state["drag_start"]
        canvas_x = self.image_canvas.canvasx(event.x)
        canvas_y = self.image_canvas.canvasy(event.y)
        x1, y1 = self._clip_original_canvas_point_to_image(canvas_x, canvas_y, window_id)

        left = min(x0, x1)
        right = max(x0, x1)
        top = min(y0, y1)
        bottom = max(y0, y1)

        # Treat a tiny drag as a normal click. Use the same viewport-aware
        # conversion used by simple pixel picking, so zoom and Canvas scroll
        # cannot change which original pixel is selected.
        if (right - left) < 3 and (bottom - top) < 3:
            point = self._canvas_xy_to_original_image(window_id, canvas_x, canvas_y)
            if point is None:
                return "break"
            full_x, full_y, _rel_x, _rel_y = point

            rgba = pil.crop((full_x, full_y, full_x+1, full_y+1)).convert("RGBA").getpixel((0, 0))
            if rgba[3] == 0:
                self._clear_original_selection_rectangle(window_id)
                return "break"
            r, g, b = rgba[:3]
            pixel_lab = UtilsTools.analysis_rgb_to_lab((r, g, b))

            if self.app.COLOR_SPACE:
                self.app.display_pixel_value(full_x, full_y, pixel_lab, is_average=False, selection_info=None, image_id=window_id, native_rgb=(r, g, b))

            return "break"

        # Convert rectangle from canvas coordinates to image-local coordinates
        left_i = left - img_x
        right_i = right - img_x
        top_i = top - img_y
        bottom_i = bottom - img_y

        # Clip to displayed image bounds
        left_i = max(0, min(draw_w, left_i))
        right_i = max(0, min(draw_w, right_i))
        top_i = max(0, min(draw_h, top_i))
        bottom_i = max(0, min(draw_h, bottom_i))

        if right_i <= left_i or bottom_i <= top_i:
            return "break"

        # Map the displayed rectangle through the CURRENT zoom viewport and
        # then into full-resolution original coordinates. This is the critical
        # step that keeps ROI sampling correct after Grid/Focus/zoom/scroll.
        crop = self._get_image_view_crop_box(window_id)
        source = getattr(self, "image_view_source", {}).get(window_id)
        original = getattr(self, "pil_images_original", {}).get(window_id)
        if crop is None or source is None or original is None:
            return "break"

        crop_left, crop_top, crop_right, crop_bottom = crop
        crop_w = crop_right - crop_left
        crop_h = crop_bottom - crop_top
        sw, sh = source.size
        ow, oh = original.size

        src_left = crop_left + (left_i / draw_w) * crop_w
        src_right = crop_left + (right_i / draw_w) * crop_w
        src_top = crop_top + (top_i / draw_h) * crop_h
        src_bottom = crop_top + (bottom_i / draw_h) * crop_h

        full_left = int((src_left / max(1, sw)) * ow)
        full_right = int(np.ceil((src_right / max(1, sw)) * ow))
        full_top = int((src_top / max(1, sh)) * oh)
        full_bottom = int(np.ceil((src_bottom / max(1, sh)) * oh))

        full_left = max(0, min(full_w - 1, full_left))
        full_right = max(0, min(full_w, full_right))
        full_top = max(0, min(full_h - 1, full_top))
        full_bottom = max(0, min(full_h, full_bottom))

        if full_right <= full_left or full_bottom <= full_top:
            return "break"

        # Compute the mean directly in CIELAB, converting each pixel first.
        pixel_lab, used, visible = UtilsTools.mean_lab_of_pil_roi(
            pil, (full_left, full_top, full_right, full_bottom),
        )
        if pixel_lab is None:
            return "break"
        pixel_lab = tuple(float(v) for v in pixel_lab)
        # RGB represents the LAB mean for screen display only.
        r, g, b = UtilsTools.lab_to_rgb(pixel_lab)

        # Representative coordinates = rectangle center
        cx = (full_left + full_right) // 2
        cy = (full_top + full_bottom) // 2

        selection_info = {
            "type": "roi",
            "x1": full_left,
            "y1": full_top,
            "x2": full_right - 1,
            "y2": full_bottom - 1,
            "width": full_right - full_left,
            "height": full_bottom - full_top,
            "pixels": used,
            "total_pixels": (full_right - full_left) * (full_bottom - full_top),
            "visible_pixels": visible,
            "center_x": cx,
            "center_y": cy,
            "mean_rgb": (r, g, b),
        }

        if self.app.COLOR_SPACE:
            self.app.display_pixel_value(
                cx,
                cy,
                pixel_lab,
                is_average=True,
                selection_info=selection_info,
                image_id=window_id
            )

        return "break"


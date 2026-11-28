"""Controller for single-color and all-color mapping in the image workspace.

Owns mapping result caches, per-card jobs, legend controls and mapping views.
ImageDisplayManager owns source images and card geometry; ColorProcessingEngine
owns preprocessing and membership computation. PyFCSApp coordinates shared
model/operator state and application-wide task exclusion.
"""
import itertools
import threading
import numpy as np
import tkinter as tk
from PIL import Image, ImageTk
from Source.interface.modules.common import UtilsTools
from Source.interface.modules.image.ColorProcessingEngine import (
    general_mapping_space, single_mapping_space, mapping_category_rows, has_mapping_detail,
)


class ColorMappingManager:
    def __init__(self, app):
        self.app = app
        self.root = app.root
        # Create all delegated mapping state before any UI callback can read it.
        # Empty dictionaries are valid from startup, not just after the first card.
        self.SHOW_ORIGINAL = {}
        self.CAN_APPLY_MAPPING = {}
        self.image_jobs = {}
        self._image_job_counter = itertools.count(1)
        self.window_image_key = {}
        self.window_mapping_mode = {}
        self.mapping_locked_until_original = {}
        self.modified_image = {}
        self.current_protos = {}
        self.proto_options = {}
        self.cm_cache_by_image = {}
        self.proto_percentage_cache_by_image = {}
        # Bounded result caches are separate from the 256 MiB preparation LRU.
        # Visible maps keep their own references and cannot be evicted from cards.
        self._result_cache_lock = threading.RLock()
        self._result_cache_max_bytes = 64 * 1024**2  # per cache (single / all)
        self._result_cache_max_entries = 128
        self._mapping_all_pack_by_window = {}
        self._mapping_all_palette_by_window = {}
        self._mapping_all_initial_view = {}
        self._mapping_tconorm_buttons = {}
        # Mapping controls are embedded in cards; there is no separate dock.
        self.image_mapping_dock = None
        self.image_mapping_dock_visible = False

    @staticmethod
    def _cached_result_bytes(value):
        if isinstance(value, np.ndarray):
            return value.nbytes
        if isinstance(value, dict):
            return sum(ColorMappingManager._cached_result_bytes(v) for v in value.values())
        if isinstance(value, (tuple, list)):
            return sum(ColorMappingManager._cached_result_bytes(v) for v in value)
        return 0

    def _lookup_cached_result(self, cache, scope, key):
        """Refresh scope/entry recency without creating empty cache scopes."""
        with self._result_cache_lock:
            entries = cache.get(scope)
            if entries is None or key not in entries:
                return None
            value = entries.pop(key)
            entries[key] = value
            cache[scope] = cache.pop(scope)
            return value

    def _store_cached_result(self, cache, scope, key, value):
        """Bound retained result arrays, including after closing all images.

        Scope-level recency followed by entry recency is deliberately simple:
        the existing public dictionaries and cache keys remain compatible.
        Oversized values are displayed but not retained for later reuse.
        """
        with self._result_cache_lock:
            if self._cached_result_bytes(value) > self._result_cache_max_bytes:
                return
            entries = cache.pop(scope, {})
            entries.pop(key, None)
            entries[key] = value
            cache[scope] = entries
            total = sum(self._cached_result_bytes(v) for group in cache.values() for v in group.values())
            count = sum(len(group) for group in cache.values())
            while cache and (total > self._result_cache_max_bytes or count > self._result_cache_max_entries):
                oldest_scope = next(iter(cache))
                group = cache[oldest_scope]
                if group:
                    removed = group.pop(next(iter(group)))
                    total -= self._cached_result_bytes(removed)
                    count -= 1
                if not group:
                    cache.pop(oldest_scope)

    def _sync_image_mapping_tconorm_buttons(self):
        """Display the single shared operator; atomic spaces cannot aggregate."""
        buttons = getattr(self, "_mapping_tconorm_buttons", {})
        space = getattr(self.app, "fuzzy_color_space", None)
        enabled = bool(getattr(space, "is_granular", False))
        current = getattr(space, "tconorm", "bounded_sum")
        for mode, button in buttons.items():
            active = mode == current
            button.configure(
                state="normal" if enabled else "disabled",
                bg=UtilsTools.UI_ACCENT_SOFT if active else "#f5f5f5",
                fg=UtilsTools.UI_ACCENT_DARK if active else "#535965",
                activebackground=UtilsTools.UI_ACCENT_HOVER if active else "#f5f5f5",
                font=("Segoe UI", 8, "bold" if active else "normal"),
            )
        self.app._sync_color_evaluation_operator()


    def _set_image_mapping_tconorm(self, operator):
        """Change the shared T-conorm and refresh already-displayed mappings."""
        space = getattr(self.app, "fuzzy_color_space", None)
        if not getattr(space, "is_granular", False):
            return
        if operator == space.tconorm:
            return
        if self.app._has_any_active_job():
            self.app.custom_warning("Process Running",
                "Finish or cancel the active process before changing the T-conorm.")
            return
        # Capture the displayed selections BEFORE restoring old mappings.
        snapshots = []
        for wid, mode in list(getattr(self, "window_mapping_mode", {}).items()):
            if mode in ("single", "all"):
                info = getattr(self, "proto_options", {}).get(wid, {})
                snapshots.append((wid, mode, info.get("selection"),
                                  info.get("display_style", "gray"),
                                  info.get("level", "categories"), set(info.get("expanded_categories", ())),
                                  getattr(self, "_mapping_all_pack_by_window", {}).get(wid, {}).get("level", "categories"),
                                  getattr(self, "_mapping_all_pack_by_window", {}).get(wid, {}).get("scheme", "original")))
        controller = getattr(self.app, "_image_inspection_controller", None)
        inspector_open = False
        try:
            inspector_open = bool(controller and controller.win.winfo_exists())
        except Exception:
            pass
        if inspector_open:
            # The inspection controller already handles membership refresh and
            # cache invalidation, so avoid a duplicate invalidation here.
            controller._set_tconorm_choice(operator.upper())
        else:
            self._prepare_open_images_for_color_space_change()
            space.set_tconorm(operator)
            self._invalidate_mapping_caches()
        self._sync_image_mapping_tconorm_buttons()
        if space.tconorm != operator:
            return
        # Reapply existing maps from the original image. A new membership
        # calculation is necessary; palette-only changes remain instantaneous.
        for wid, mode, selection, style, single_level, expanded, level, scheme in snapshots:
            if wid not in getattr(self, "window_image_key", {}):
                continue
            if mode == "all":
                self._mapping_all_initial_view = getattr(self, "_mapping_all_initial_view", {})
                self._mapping_all_initial_view[wid] = (level, scheme)
                self.color_mapping_all(wid)
            elif mode == "single":
                self.color_mapping(wid)
                info = getattr(self, "proto_options", {}).get(wid)
                if isinstance(info, dict):
                    info["display_style"] = style
                    info["level"] = single_level
                    info["expanded_categories"] = expanded
                    self._refresh_single_mapping_rows(wid)
                    self._reposition_proto_options(wid)
                    self._render_proto_options(wid)
                    if selection is not None:
                        self._select_mapping_item(wid, selection)


    def _prepare_open_images_for_color_space_change(self):
        """
        Detach current image mappings from the color space that produced them.

        Single-prototype mappings return to Original immediately. Mapping-All
        views may stay visible, but are explicitly locked as results of the old
        color space until the user chooses a valid view/mapping for the new one.
        """
        if not hasattr(self, "mapping_locked_until_original"):
            self.mapping_locked_until_original = {}

        if not hasattr(self.app, "floating_images") or not self.app.floating_images:
            return

        for window_id in list(self.app.floating_images.keys()):
            mode = getattr(self, "window_mapping_mode", {}).get(window_id)

            if mode == "single":
                try:
                    self.show_original_image(window_id)
                except Exception:
                    pass

            elif mode == "all":
                self.mapping_locked_until_original[window_id] = True
                self.CAN_APPLY_MAPPING[window_id] = False
                try:
                    self.app.image_canvas.itemconfig(f"{window_id}_pct_text", text="")
                except Exception:
                    pass


    def _invalidate_mapping_caches(self):
        """Invalidate all results whose memberships depend on the active FCS."""
        self._sync_image_mapping_tconorm_buttons()
        # Image Inspection also changes the shared operator. Keep the compact
        # readout synchronized whichever window initiated the change.
        self.app._refresh_pixel_info_memberships()
        with self._result_cache_lock:
            self.cm_cache_by_image.clear()
            self.proto_percentage_cache_by_image.clear()
        if hasattr(self, "_mapping_all_pack_by_window"):
            self._mapping_all_pack_by_window.clear()
        controller = getattr(self.app, "_full_resolution_workspace_controller", None)
        if controller is not None:
            try:
                controller.invalidate_model()
            except tk.TclError:
                pass


    def _display_cached_mapping_all(self, window_id):
        """Recolor the selected label map without repeating any fuzzy calculation."""
        pack = getattr(self, "_mapping_all_pack_by_window", {}).get(window_id)
        if not pack:
            return "break"
        level = pack["level"]
        scheme = pack["scheme"]
        palette = pack["level_palettes"][level][scheme]
        label_map = pack["label_maps"][level]
        colored = self.app.image_manager.recolor_label_map(
            label_map, palette, pack.get("alpha_values"))
        if not getattr(pack.get("mapping_space", self.app.fuzzy_color_space), "covering", True):
            # Uncovered regions retain the original image, including alpha.
            map_h, map_w = label_map.shape
            prepared = self._peek_mapping_preprocessing(
                window_id, pack.get("mapping_space", self.app.fuzzy_color_space), (map_w, map_h))
            if prepared is not None:
                source_rgb, alpha = prepared.rgb, prepared.alpha
            else:
                source = self._get_mapping_source_image(window_id, (map_w, map_h))
                source_rgb = np.asarray(UtilsTools._pil_rgb_for_processing(source))
                alpha = UtilsTools._get_alpha_values_from_pil(source)
            missing = (label_map < 0) & (alpha > 0)
            if np.any(missing):
                colored[missing, :3] = source_rgb[missing, :3]
                colored[missing, 3] = alpha[missing]
        pack["label_map"] = label_map  # Compatibility with image export.
        pack["palettes"] = pack["level_palettes"][level]
        self._display_mapping_all_result(window_id, colored, palette)
        return "break"


    def _set_mapping_all_palette(self, window_id, scheme):
        """Switch the Mapping All palette without recomputing category winners."""
        if self._has_active_job(window_id):
            return "break"
        if getattr(self, "mapping_locked_until_original", {}).get(window_id, False):
            self.app.custom_warning("Old Color Space",
                "This Mapping All result belongs to a previous Color Space. Press Original first.")
            return "break"
        pack = getattr(self, "_mapping_all_pack_by_window", {}).get(window_id)
        if not pack or scheme == pack.get("scheme") or scheme not in ("original", "alt"):
            return "break"
        previous = pack.get("scheme", "original")
        pack["scheme"] = scheme
        try:
            return self._display_cached_mapping_all(window_id)
        except Exception as exc:
            pack["scheme"] = previous
            self.app.custom_warning("Mapping Display Error", str(exc))
            return "break"


    def _set_mapping_all_level(self, window_id, level):
        """Switch between aggregated categories and explanatory granules."""
        if self._has_active_job(window_id):
            return "break"
        if getattr(self, "mapping_locked_until_original", {}).get(window_id, False):
            self.app.custom_warning("Old Color Space",
                "This Mapping All result belongs to a previous Color Space. Press Original first.")
            return "break"
        pack = getattr(self, "_mapping_all_pack_by_window", {}).get(window_id)
        if not pack or level == pack.get("level") or level not in ("categories", "granules"):
            return "break"
        old = pack["level"]
        pack["level"] = level
        try:
            return self._display_cached_mapping_all(window_id)
        except Exception as exc:
            pack["level"] = old
            self.app.custom_warning("Mapping Display Error", str(exc))
            return "break"


    def _toggle_mapping_all_palette(self, window_id):
        """Compatibility wrapper for older callbacks using the toggle action."""
        pack = getattr(self, "_mapping_all_pack_by_window", {}).get(window_id)
        if not pack:
            return "break"
        next_scheme = "original" if pack.get("scheme") == "alt" else "alt"
        return self._set_mapping_all_palette(window_id, next_scheme)


    def _ensure_image_jobs(self):
        """Lazy-init job registry used to bind one running process per image/window."""
        if not hasattr(self, "image_jobs"):
            self.image_jobs = {}
        if not hasattr(self, "_image_job_counter"):
            self._image_job_counter = itertools.count(1)


    def _has_active_job(self, window_id):
        """Returns True if there is an active job for this image."""
        self._ensure_image_jobs()
        info = self.image_jobs.get(window_id)
        if not info:
            return False

        th = info.get("thread")
        cancel_event = info.get("cancel_event")
        # A cancellation request does not mean the worker has stopped. Keep
        # the card busy until the thread actually exits to avoid overlapping
        # mapping jobs and reusing data while the old worker winds down.
        return th is not None and th.is_alive()


    def _is_current_job(self, window_id, job_id):
        """Checks whether job_id is still the active job for window_id."""
        self._ensure_image_jobs()
        info = self.image_jobs.get(window_id)
        return bool(info and info.get("job_id") == job_id)


    def _cancel_window_job(self, window_id, cleanup_ui=True):
        """Cancels the active job associated with a floating image/window."""
        self._ensure_image_jobs()
        info = self.image_jobs.get(window_id)
        if not info:
            return

        try:
            info["cancel_event"].set()
        except Exception:
            pass

        # Restore menu state because the image remains in its previous/original state
        try:
            self.CAN_APPLY_MAPPING[window_id] = True
            self.SHOW_ORIGINAL[window_id] = False
        except Exception:
            pass

        if cleanup_ui:
            self._hide_window_loading(window_id)


    def _is_job_cancelled(self, window_id, cancel_event, job_id):
        """Worker-safe cancellation check; never query Tk widgets here.

        Closing/replacing an image sets its cancel_event on the UI thread.
        Checking the job ID also prevents obsolete results from being applied.
        """
        if cancel_event.is_set():
            return True
        info = getattr(self, "image_jobs", {}).get(window_id)
        return info is None or info.get("job_id") != job_id


    def _start_window_job(self, window_id, kind, target):
        """
        Starts a thread-bound job associated with one image/window.
        Only one job can run at a time per window_id.
        """
        self._ensure_image_jobs()

        if self._has_active_job(window_id):
            self.app.custom_warning(
                "Process Running",
                f"A '{self.image_jobs[window_id]['kind']}' process is already running for this image."
            )
            return None

        cancel_event = threading.Event()
        job_id = next(self._image_job_counter)

        self.image_jobs[window_id] = {
            "thread": None,
            "cancel_event": cancel_event,
            "job_id": job_id,
            "kind": kind,
            "loading_widgets": {}
        }

        def runner():
            try:
                target(cancel_event, job_id)
            except Exception as e:
                error_msg = str(e)

                def _ui_error(msg=error_msg):
                    if not cancel_event.is_set() and self._is_current_job(window_id, job_id):
                        self.app.custom_warning("Process Error", f"Unexpected error: {msg}")

                try:
                    self.app.image_canvas.after(0, _ui_error)
                except Exception:
                    pass
            finally:
                def _cleanup():
                    info = self.image_jobs.get(window_id)
                    if info and info.get("job_id") == job_id:
                        self._hide_window_loading(window_id)
                        self.image_jobs.pop(window_id, None)

                try:
                    self.app.image_canvas.after(0, _cleanup)
                except Exception:
                    pass

        th = threading.Thread(target=runner, daemon=True)
        self.image_jobs[window_id]["thread"] = th
        try:
            th.start()
        except RuntimeError as exc:
            self.image_jobs.pop(window_id, None)
            self._hide_window_loading(window_id)
            self.app.custom_warning("Process Error", f"Could not start the processing thread:\n{exc}")
            return None

        return job_id


    def _raise_all_loading_panels(self):
        """
        Keep every visible loading panel above floating windows and legend panels.

        This prevents a running job's loading overlay from disappearing when another
        floating window is moved, focused, or closed.
        """
        self._ensure_image_jobs()

        for window_id, info in self.image_jobs.items():
            widgets = info.get("loading_widgets", {})
            if not widgets:
                continue

            try:
                self.app.image_canvas.tag_raise(f"{window_id}_loading")
            except Exception:
                pass


    def _show_window_loading(self, window_id, text="Processing..."):
        """Creates a canvas-only loading panel linked to a specific floating image/window."""
        self._ensure_image_jobs()

        self._hide_window_loading(window_id)

        if not hasattr(self.app, "floating_window_state") or window_id not in self.app.floating_window_state:
            return

        st = self.app.floating_window_state[window_id]
        wx, wy, ww, wh = st["x"], st["y"], st["w"], st["h"]

        # Place the loading panel on top of the image area
        IMG_LEFT_PAD = 12
        IMG_TOP_PAD = 44

        panel_w = min(170, max(140, ww - 20))
        panel_h = 95

        panel_x = wx + IMG_LEFT_PAD + max(0, (ww - panel_w) // 2)
        panel_y = wy + IMG_TOP_PAD + max(0, (wh - panel_h) // 2)

        tags = (window_id, f"{window_id}_loading", "loading")

        # Background panel
        bg = self.app.image_canvas.create_rectangle(
            panel_x, panel_y, panel_x + panel_w, panel_y + panel_h,
            fill="white", outline="black", width=1,
            tags=tags
        )

        # Title
        title = self.app.image_canvas.create_text(
            panel_x + panel_w / 2,
            panel_y + 20,
            text=text,
            fill="black",
            font=("Sans", 12, "bold"),
            tags=tags
        )

        # Progress text
        progress = self.app.image_canvas.create_text(
            panel_x + panel_w / 2,
            panel_y + 50,
            text="0.0%",
            fill="black",
            font=("Sans", 10),
            tags=(window_id, f"{window_id}_loading", "loading", f"{window_id}_loading_progress")
        )

        # Cancel button background
        btn_w = panel_w - 20
        btn_h = 18
        btn_x1 = panel_x + 10
        btn_y1 = panel_y + panel_h - 28
        btn_x2 = btn_x1 + btn_w
        btn_y2 = btn_y1 + btn_h

        cancel_bg = self.app.image_canvas.create_rectangle(
            btn_x1, btn_y1, btn_x2, btn_y2,
            fill="#e6e6e6", outline="gray",
            tags=(window_id, f"{window_id}_loading", "loading", f"{window_id}_loading_cancel")
        )

        cancel_txt = self.app.image_canvas.create_text(
            (btn_x1 + btn_x2) / 2,
            (btn_y1 + btn_y2) / 2,
            text="Cancel",
            fill="black",
            font=("Sans", 10),
            tags=(window_id, f"{window_id}_loading", "loading", f"{window_id}_loading_cancel")
        )

        # A cancelled Mapping All must not leave the image in an unfinished view mode.
        def _cancel_loading_job(_event=None):
            info = self.image_jobs.get(window_id, {})
            if info.get("kind") == "color_mapping_all":
                self.show_original_image(window_id)
            else:
                self._cancel_window_job(window_id)

        self.app.image_canvas.tag_bind(
            f"{window_id}_loading_cancel",
            "<Button-1>",
            _cancel_loading_job
        )

        if window_id in self.image_jobs:
            self.image_jobs[window_id]["loading_widgets"] = {
                "bg": bg,
                "title": title,
                "progress": progress,
                "cancel_bg": cancel_bg,
                "cancel_txt": cancel_txt,
                "panel_w": panel_w,
                "panel_h": panel_h,
            }

        # Ensure all visible loading panels remain above floating windows
        self._raise_all_loading_panels()


    def _hide_window_loading(self, window_id):
        """Destroys the loading panel associated with one floating image/window."""
        self._ensure_image_jobs()

        info = self.image_jobs.get(window_id)
        if not info:
            return

        try:
            self.app.image_canvas.delete(f"{window_id}_loading")
        except Exception:
            pass

        info["loading_widgets"] = {}


    def _update_window_progress(self, window_id, job_id, current_step, total_steps):
        """Updates the per-window loading progress safely from background threads."""
        if total_steps <= 0:
            return

        pct = (current_step / total_steps) * 100.0

        def _ui():
            if not self._is_current_job(window_id, job_id):
                return

            try:
                self.app.image_canvas.itemconfig(f"{window_id}_loading_progress", text=f"{pct:.1f}%")
            except Exception:
                pass

        try:
            self.app.image_canvas.after(0, _ui)
        except Exception:
            pass


    def _reposition_window_loading(self, window_id):
        """Repositions the loading panel so it stays centered over the image."""
        self._ensure_image_jobs()

        info = self.image_jobs.get(window_id)
        if not info:
            return

        widgets = info.get("loading_widgets", {})
        if not widgets:
            return

        if not hasattr(self.app, "floating_window_state") or window_id not in self.app.floating_window_state:
            return

        st = self.app.floating_window_state[window_id]
        wx, wy, ww, wh = st["x"], st["y"], st["w"], st["h"]

        IMG_LEFT_PAD = 12
        IMG_TOP_PAD = 44

        panel_w = min(170, max(140, ww - 20))
        panel_h = 95

        panel_x = wx + IMG_LEFT_PAD + max(0, (ww - panel_w) // 2)
        panel_y = wy + IMG_TOP_PAD + max(0, (wh - panel_h) // 2)

        btn_w = panel_w - 20
        btn_h = 18
        btn_x1 = panel_x + 10
        btn_y1 = panel_y + panel_h - 28
        btn_x2 = btn_x1 + btn_w
        btn_y2 = btn_y1 + btn_h

        try:
            self.app.image_canvas.coords(
                widgets["bg"],
                panel_x, panel_y, panel_x + panel_w, panel_y + panel_h
            )
            self.app.image_canvas.coords(
                widgets["title"],
                panel_x + panel_w / 2, panel_y + 20
            )
            self.app.image_canvas.coords(
                widgets["progress"],
                panel_x + panel_w / 2, panel_y + 50
            )
            self.app.image_canvas.coords(
                widgets["cancel_bg"],
                btn_x1, btn_y1, btn_x2, btn_y2
            )
            self.app.image_canvas.coords(
                widgets["cancel_txt"],
                (btn_x1 + btn_x2) / 2, (btn_y1 + btn_y2) / 2
            )

            # Keep it visible above other windows
            self.app.image_canvas.tag_raise(f"{window_id}_loading")

        except Exception:
            pass


    def _reposition_proto_options(self, window_id):
        """
        Keep the mapping selector/legend directly BELOW its image.

        The panel is drawn with native Canvas primitives and shares the same
        ``window_id`` tag as the image card, so it moves, minimizes, focuses
        and participates in z-order as part of the same visual object.
        """
        info = getattr(self, "proto_options", {}).get(window_id)
        if not isinstance(info, dict):
            return

        st = getattr(self.app, "floating_window_state", {}).get(window_id)
        if not st:
            return

        wx, wy, ww, wh = st["x"], st["y"], st["w"], st["h"]
        img_left_pad = 12
        img_top_pad = 44

        # Reserve room for the percentage/status line only when it actually
        # contains text. In the neutral Color Mapping state this keeps the
        # selector much closer to the image instead of leaving a blank band.
        pct_text = ""
        try:
            pct_items = self.app.image_canvas.find_withtag(f"{window_id}_pct_text")
            if pct_items:
                pct_text = str(self.app.image_canvas.itemcget(pct_items[0], "text") or "").strip()
        except Exception:
            pct_text = ""

        # Keep the percentage as a compact caption between image and panel.
        # The gap is deliberately small so resizing the image does not create
        # a large white band inside the card.
        panel_gap = 21 if pct_text else 7
        info["gap"] = panel_gap
        panel_y = wy + img_top_pad + wh + panel_gap

        # Keep the selector slightly narrower than the image and centered.
        # The minimum still leaves enough room for normal prototype names.
        available_w = max(150, int(ww) - 24)
        preferred_w = max(145, int(round(float(ww) * 0.74)))
        panel_w = min(285, available_w, preferred_w)
        panel_x = wx + img_left_pad + max(0, (int(ww) - panel_w) // 2)
        panel_h = self.app._workspace_legend_height(window_id)

        old_x = info.get("x")
        old_y = info.get("y")
        old_w = info.get("width")
        old_h = info.get("height")

        # Width/height changes alter text space and the number of visible rows,
        # therefore redraw instead of only translating existing Canvas items.
        if (
            old_x is None
            or old_y is None
            or old_w != panel_w
            or old_h != panel_h
        ):
            info["x"] = panel_x
            info["y"] = panel_y
            info["width"] = panel_w
            info["height"] = panel_h
            self._render_proto_options(window_id)
            return

        dx = panel_x - old_x
        dy = panel_y - old_y
        if dx or dy:
            try:
                self.app.image_canvas.move(f"{window_id}_legend", dx, dy)
            except Exception:
                pass
            info["x"] = panel_x
            info["y"] = panel_y


    def _mapping_source_spec(self, window_id, target_size=None):
        """Return the immutable original and effective processing size."""
        original = (getattr(self.app, "pil_images_original", {}) or {}).get(window_id)
        if original is None:
            raise ValueError("Original image is not available for mapping.")
        if target_size is None:
            target_size = getattr(self.app, "image_dimensions", {}).get(window_id)
        if target_size is None:
            return original, original.size
        try:
            size = (max(1, int(target_size[0])), max(1, int(target_size[1])))
        except Exception:
            size = original.size
        return original, size


    def _get_mapping_source_image(self, window_id, target_size=None):
        """Always derive processing pixels from the original, never the display."""
        original, size = self._mapping_source_spec(window_id, target_size)
        return (original.copy() if original.size == size else
                original.resize(size, Image.Resampling.LANCZOS))


    def _peek_mapping_preprocessing(self, window_id, mapping_space, target_size=None):
        original, size = self._mapping_source_spec(window_id, target_size)
        return self.app.image_manager.peek_prepared_image(
            original, size, mapping_space, owner=window_id)


    def _destroy_proto_options(self, window_id):
        """Destroy and unregister the canvas-native mapping panel for one image."""
        self.proto_options = getattr(self, "proto_options", {})
        self.proto_options.pop(window_id, None)
        try:
            self.app.image_canvas.delete(f"{window_id}_legend")
        except Exception:
            pass


    @staticmethod
    def _legend_display_name(name, max_chars=22):
        text = str(name)
        if len(text) <= max_chars:
            return text
        return text[:max(1, max_chars - 1)] + "…"


    def _mapping_category_rows(self, space, expanded, *, include_granules=True):
        """Keep the old row helper available for callers; use one shared descriptor builder."""
        return mapping_category_rows(space, single_mapping_space(space), expanded,
                                     detailed=include_granules)


    def _refresh_single_mapping_rows(self, window_id):
        info = getattr(self, "proto_options", {}).get(window_id)
        space = getattr(self.app, "fuzzy_color_space", None)
        if not isinstance(info, dict) or info.get("kind") != "single" or space is None:
            return
        view = info.get("mapping_space")
        if view is None:
            view = info["mapping_space"] = single_mapping_space(space)
        info["rows"] = mapping_category_rows(space, view,
            info.setdefault("expanded_categories", set()),
            detailed=info.get("level", "categories") == "granules")


    def _refresh_mapping_all_legend_rows(self, window_id):
        info = getattr(self, "proto_options", {}).get(window_id)
        pack = getattr(self, "_mapping_all_pack_by_window", {}).get(window_id)
        if not isinstance(info, dict) or info.get("kind") != "all" or not pack:
            return
        space = pack.get("mapping_space", self.app.fuzzy_color_space)
        level = pack.get("level", "categories")
        palette = np.asarray(pack["palettes"][pack["scheme"]], dtype=np.uint8)
        detail_palette = np.asarray(pack["level_palettes"]["granules"][pack["scheme"]], dtype=np.uint8)
        rows = []
        expanded = info.setdefault("expanded_categories", set())
        granular = bool(getattr(space, "is_granular", False))
        offset = 0
        for i, proto in enumerate(space.prototypes):
            granules = space.categories[i].prototypes if granular else [proto]
            count = len(granules)
            shades = detail_palette[offset:offset + count]
            if level == "categories":
                # First stripe is the actual category color used in the map.
                swatches = np.vstack([palette[i], shades[1:]]) if count > 1 else shades
                rows.append({"type": "color", "name": proto.label, "count": count,
                             "category": i, "swatches": swatches,
                             "rgb": tuple(int(v) for v in palette[i]),
                             "export_name": proto.label, "expandable": False})
            else:
                if count > 1:
                    rows.append({"type": "group", "name": proto.label,
                                 "category": i, "count": count, "swatches": shades,
                                 "expandable": True})
                if count == 1 or i in expanded:
                    for j, granule in enumerate(granules):
                        rows.append({"type": "color", "name": str(granule.label),
                            "category": i, "indent": count > 1,
                            "rgb": tuple(int(v) for v in palette[offset + j]),
                            "export_name": f"{proto.label} / {granule.label}" if count > 1 else proto.label})
            offset += count
        if np.any((np.asarray(pack["label_map"]) < 0) & (np.asarray(pack["alpha_values"]) > 0)):
            rows.append({"type": "unassigned", "name": "Unassigned (original)",
                         "rgb": (220, 220, 220), "export_name": "Unassigned (original)"})
        info["rows"] = rows
        info["level"] = level


    def _toggle_mapping_legend_category(self, window_id, category_index):
        info = getattr(self, "proto_options", {}).get(window_id)
        if not isinstance(info, dict):
            return "break"
        expanded = info.setdefault("expanded_categories", set())
        if category_index in expanded:
            expanded.discard(category_index)
        else:
            expanded.add(category_index)
        if info.get("kind") == "single":
            self._refresh_single_mapping_rows(window_id)
        else:
            self._refresh_mapping_all_legend_rows(window_id)
        self._reposition_proto_options(window_id)
        self._render_proto_options(window_id)
        self.app._schedule_image_workspace_reflow()
        return "break"


    def _scroll_proto_options(self, window_id, delta):
        info = getattr(self, "proto_options", {}).get(window_id)
        if not isinstance(info, dict):
            return "break"
        total = len(info.get("rows", []))
        visible = max(1, int(info.get("visible_rows", 1)))
        info["scroll_index"] = max(0, min(max(0, total - visible),
                                           int(info.get("scroll_index", 0)) + int(delta)))
        self._render_proto_options(window_id)
        return "break"


    def _set_single_mapping_level(self, window_id, level):
        """Switch the row hierarchy; if a leaf is hidden, select its general parent."""
        if level not in ("categories", "granules") or self._has_active_job(window_id):
            return "break"
        info = getattr(self, "proto_options", {}).get(window_id)
        if not isinstance(info, dict) or info.get("kind") != "single" or level == info.get("level"):
            return "break"
        if getattr(self, "mapping_locked_until_original", {}).get(window_id, False):
            return "break"
        info["level"] = level
        info["scroll_index"] = 0
        self._refresh_single_mapping_rows(window_id)
        selection = info.get("selection")
        if selection is not None and not any(r.get("selection") == selection for r in info["rows"]):
            if level == "categories":
                view = info["mapping_space"]
                category = view.categories[selection[1]]
                leaves = {category.prototypes[selection[2]].label} if selection[0] == "granule" else {p.label for p in category.prototypes}
                candidates = [r for r in info["rows"] if r.get("selection")]
                parent = next((r for r in candidates if r["category"] == selection[1]), None)
                if parent is None:
                    owners = [r for r in candidates if leaves <= {p.label for p in view.categories[r["category"]].prototypes}]
                    parent = owners[0] if len(owners) == 1 else None
                if parent is None:
                    # No unambiguous general parent: restore the original image
                    # instead of silently choosing a different category.
                    info["selection"] = None
                    self.current_protos[window_id].set("")
                    self.show_original_image(window_id)
                    self.color_mapping(window_id)
                    return "break"
                info["selection"] = parent["selection"]
                self.current_protos[window_id].set(parent["name"])
                self.get_proto_percentage(window_id)
        selection = info.get("selection")
        if selection is not None:
            info["scroll_index"] = next((i for i, row in enumerate(info["rows"])
                if row.get("selection") == selection), 0)
        self._reposition_proto_options(window_id)
        self._render_proto_options(window_id)
        self.app._schedule_image_workspace_reflow()
        return "break"


    def _set_single_mapping_style(self, window_id, style):
        """Switch grayscale/weighted RGB without recomputing membership."""
        if style not in ("gray", "color") or self._has_active_job(window_id):
            return "break"
        info = getattr(self, "proto_options", {}).get(window_id)
        if not isinstance(info, dict) or info.get("kind") != "single":
            return "break"
        if info.get("display_style", "gray") == style:
            return "break"
        info["display_style"] = style
        self._render_proto_options(window_id)
        selected = info.get("selection")
        if selected is not None and info.get("displayed_for") == selected:
            gray = getattr(self, "modified_image", {}).get(window_id)
            if isinstance(gray, np.ndarray) and gray.ndim == 2:
                self.display_color_mapping(gray, window_id)
        return "break"


    def _select_mapping_item(self, window_id, selection):
        if selection is None or self._has_active_job(window_id):
            return "break"
        info = getattr(self, "proto_options", {}).get(window_id)
        if not isinstance(info, dict) or info.get("kind") != "single":
            return "break"
        info["selection"] = tuple(selection)
        for row in info.get("rows", []):
            if row.get("selection") == info["selection"]:
                current = getattr(self, "current_protos", {}).get(window_id)
                if current is not None:
                    current.set(row["name"])
                break
        self._render_proto_options(window_id)
        self.get_proto_percentage(window_id)
        return "break"


    def _select_proto_from_legend(self, window_id, color_name):
        """Keep compatibility with the old category-name selection callback."""
        space = getattr(self, "proto_options", {}).get(window_id, {}).get(
            "mapping_space", getattr(self.app, "fuzzy_color_space", None))
        if space is not None:
            for i, proto in enumerate(space.prototypes):
                if str(proto.label) == str(color_name):
                    return self._select_mapping_item(window_id, ("category", i))
        return "break"


    def _jump_proto_options_scroll(self, window_id, event, track_top, track_height):
        info = getattr(self, "proto_options", {}).get(window_id)
        if not isinstance(info, dict):
            return "break"
        visible = max(1, int(info.get("visible_rows", 1)))
        max_offset = max(0, len(info.get("rows", [])) - visible)
        if max_offset <= 0:
            return "break"
        y = float(self.app.image_canvas.canvasy(event.y))
        ratio = max(0.0, min(1.0, (y - float(track_top)) / max(1.0, float(track_height))))
        info["scroll_index"] = int(round(ratio * max_offset))
        self._render_proto_options(window_id)
        return "break"


    def _render_proto_options(self, window_id):
        """Compact native-canvas category/granule selector and Mapping All legend."""
        info = getattr(self, "proto_options", {}).get(window_id)
        st = getattr(self.app, "floating_window_state", {}).get(window_id)
        if not isinstance(info, dict) or not st:
            return
        try:
            self.app.image_canvas.delete(f"{window_id}_legend")
        except Exception:
            pass
        x = float(info.get("x", st["x"] + 12))
        y = float(info.get("y", st["y"] + 44 + st["h"] + info.get("gap", 7)))
        w = int(info.get("width", max(180, int(st.get("w", 250)))))
        h = int(info.get("height", self.app._workspace_legend_height(window_id)))
        kind = info.get("kind", "single")
        rows = list(info.get("rows", []))
        tag = f"{window_id}_legend"
        common = (window_id, "floating", tag, "legend")
        self.app.image_canvas.create_rectangle(x, y, x + w, y + h,
            fill="white", outline="#2f2f2f", width=1, tags=common)
        footer_h = 66 if kind == "all" or info.get("show_detail") else 40
        row_h = 24
        top = y + 5
        bottom = y + h - footer_h - 4
        visible_rows = max(1, int((bottom - top) // row_h))
        info["visible_rows"] = visible_rows
        scroll = max(0, min(int(info.get("scroll_index", 0)),
                            max(0, len(rows) - visible_rows)))
        info["scroll_index"] = scroll
        right = x + w - 15
        expanded = info.get("expanded_categories", set())
        for offset, row in enumerate(rows[scroll:scroll + visible_rows]):
            n = scroll + offset
            y1 = top + offset * row_h
            y2 = y1 + row_h - 3
            cy = (y1 + y2) / 2
            row_tag = f"{tag}_row_{n}"
            selected = kind == "single" and row.get("selection") == info.get("selection")
            self.app.image_canvas.create_rectangle(
                x + 3, y1, right, y2,
                fill=UtilsTools.UI_ACCENT_SOFT if selected else "#ffffff",
                outline="", tags=common + (row_tag,))
            indent = row.get("type") == "granule" or row.get("indent", False)
            depth = min(3, row.get("depth", 1 if indent else 0))
            left = x + 8 + 14 * depth
            if kind == "single":
                self.app.image_canvas.create_oval(left, cy - 4.5, left + 9, cy + 4.5,
                    fill="#ffffff", outline="#60646e", width=1, tags=common + (row_tag,))
                if selected:
                    self.app.image_canvas.create_oval(left + 2.5, cy - 2, left + 6.5, cy + 2,
                        fill=UtilsTools.UI_ACCENT_DARK, outline="", tags=common + (row_tag,))
                left += 13
            if row.get("count", 1) > 1 and len(row.get("swatches", ())) > 1:
                swatches = list(row["swatches"])[:3]
                for index, rgb in enumerate(swatches):
                    rgb = np.asarray(rgb, dtype=int)
                    hx = "#{:02x}{:02x}{:02x}".format(*rgb[:3])
                    x1 = left + index * 5
                    self.app.image_canvas.create_rectangle(x1, cy - 5, x1 + 5, cy + 5,
                        fill=hx, outline="", tags=common + (row_tag,))
                left += 19
            else:
                rgb = np.asarray(row.get("rgb", (210, 210, 210)), dtype=int)
                hx = "#{:02x}{:02x}{:02x}".format(*rgb[:3])
                self.app.image_canvas.create_rectangle(left, cy - 5, left + 11, cy + 5,
                    fill=hx, outline="", tags=common + (row_tag,))
                left += 14
            expandable = row.get("expandable", False)
            count = row.get("count", 1)
            end_reserved = 51 if expandable else (25 if count > 1 else 4)
            available = max(3, int((right - end_reserved - left) // 5.4))
            label = self._legend_display_name(row.get("name", ""), min(24, available))
            self.app.image_canvas.create_text(left, cy, text=label, anchor="w",
                fill=UtilsTools.UI_ACCENT_DARK if selected else "#1f2937",
                font=("Segoe UI", 8, "bold" if selected else "normal"),
                tags=common + (row_tag,))
            if count > 1:
                self.app.image_canvas.create_text(right - (31 if expandable else 6), cy,
                    text=str(count), anchor="e", font=("Segoe UI", 8),
                    fill="#60646e", tags=common + (row_tag,))
            if expandable:
                cat_index = row["category"]
                marker = "▾" if cat_index in expanded else "▸"
                arrow_tag = f"{tag}_expand_{n}"
                self.app.image_canvas.create_text(right - 18, cy,
                    text=marker, anchor="center", font=("Segoe UI", 9, "bold"),
                    fill=UtilsTools.UI_ACCENT_DARK, tags=common + (arrow_tag,))
                self.app.image_canvas.tag_bind(arrow_tag, "<Button-1>",
                    lambda _e, wid=window_id, ci=cat_index:
                    self._toggle_mapping_legend_category(wid, ci))
                if kind == "all":
                    self.app.image_canvas.tag_bind(row_tag, "<Button-1>",
                        lambda _e, wid=window_id, ci=cat_index:
                        self._toggle_mapping_legend_category(wid, ci))
            if kind == "single" and row.get("selection") is not None:
                selection = row["selection"]
                self.app.image_canvas.tag_bind(row_tag, "<Button-1>",
                    lambda _e, wid=window_id, item=selection:
                    self._select_mapping_item(wid, item))
        if len(rows) > visible_rows:
            sx1, sx2 = x + w - 11, x + w - 6
            sy1, sy2 = top + 3, max(top + 21, bottom - 3)
            length = sy2 - sy1
            self.app.image_canvas.create_rectangle(sx1, sy1, sx2, sy2,
                fill="#e7e7e7", outline="#b8b8b8", tags=common)
            fraction = min(1.0, visible_rows / len(rows))
            thumb_h = max(20, length * fraction)
            thumb_y = sy1 + (length - thumb_h) * (
                scroll / max(1, len(rows) - visible_rows))
            self.app.image_canvas.create_rectangle(sx1 - 1, thumb_y,
                sx2 + 1, thumb_y + thumb_h, fill="#888888", outline="#777777",
                tags=common)
            track_tag = f"{tag}_scroll_track"
            # Add an invisible mouse target over the complete track.
            self.app.image_canvas.create_rectangle(sx1 - 2, sy1, sx2 + 2, sy2,
                outline="", fill="", tags=common + (track_tag,))
            self.app.image_canvas.tag_bind(track_tag, "<Button-1>",
                lambda e, wid=window_id, track_y=sy1, track_h=length:
                self._jump_proto_options_scroll(wid, e, track_y, track_h))
        # Segmented controls. Mapping All has two compact rows, each of which
        # recolors an already-computed pair of label maps without membership work.
        def segmented(options, selected_mode, y1, callback):
            y2 = y1 + 24
            half = (w - 14) / len(options)
            for i, (mode, caption) in enumerate(options):
                x1, x2 = x + 7 + i * half, x + 7 + (i + 1) * half
                active = selected_mode == mode
                btag = f"{tag}_button_{y1:.0f}_{mode}"
                self.app.image_canvas.create_rectangle(x1, y1, x2, y2,
                    fill=UtilsTools.UI_ACCENT_SOFT if active else "#f5f5f5",
                    outline=UtilsTools.UI_ACCENT_MUTED if active else "#b8b8b8",
                    tags=common + (btag,))
                self.app.image_canvas.create_text((x1 + x2) / 2, (y1 + y2) / 2,
                    text=caption, fill=UtilsTools.UI_ACCENT_DARK if active else "#333333",
                    font=("Segoe UI", 8, "bold" if active else "normal"),
                    tags=common + (btag,))
                self.app.image_canvas.tag_bind(btag, "<Button-1>",
                    lambda _e, wid=window_id, m=mode: callback(wid, m))
        if kind == "single":
            if info.get("show_detail"):
                segmented((("categories", "General"), ("granules", "Detailed")),
                          info.get("level", "categories"), y + h - 63,
                          self._set_single_mapping_level)
            segmented((("gray", "Grayscale"), ("color", "Color")),
                      info.get("display_style", "gray"), y + h - 34,
                      self._set_single_mapping_style)
        else:
            pack = getattr(self, "_mapping_all_pack_by_window", {}).get(window_id, {})
            segmented((("categories", "General"), ("granules", "Detailed")),
                      pack.get("level", "categories"), y + h - 61,
                      self._set_mapping_all_level)
            segmented((("original", "Original"), ("alt", "Alt. Colors")),
                      pack.get("scheme", "original"), y + h - 32,
                      self._set_mapping_all_palette)
        self.app._sync_workspace_card_item_states(window_id)
        self.app._focus_floating_window(window_id)


    def _create_single_mapping_panel(self, window_id):
        """Create a compact hierarchical selector below the image."""
        self._destroy_proto_options(window_id)
        if not hasattr(self, "current_protos"):
            self.current_protos = {}
        current = self.current_protos.get(window_id)
        if current is None:
            current = tk.StringVar(value="")
            self.current_protos[window_id] = current
        else:
            current.set("")
        try:
            self.app.image_canvas.itemconfig(f"{window_id}_pct_text", text="")
        except Exception:
            pass
        self.proto_options = getattr(self, "proto_options", {})
        space = self.app.fuzzy_color_space
        view = single_mapping_space(space)
        self.proto_options[window_id] = {
            "kind": "single", "rows": [], "selection": None,
            "mapping_space": view, "level": "categories",
            "show_detail": has_mapping_detail(space),
            "expanded_categories": set(range(len(view.prototypes))), "gap": 7, "scroll_index": 0,
            "display_style": "gray", "displayed_for": None,
        }
        self._refresh_single_mapping_rows(window_id)
        self._reposition_proto_options(window_id)
        self.app._sync_workspace_card_item_states(window_id)
        self.app._schedule_image_workspace_reflow(delay=0)


    def _create_mapping_all_panel(self, window_id, palette_uint8):
        """Create the active category/granule Mapping All legend."""
        old = getattr(self, "proto_options", {}).get(window_id, {})
        expanded = set(old.get("expanded_categories", set()))
        scroll = int(old.get("scroll_index", 0))
        self._destroy_proto_options(window_id)
        if old.get("kind") != "all":
            pack = getattr(self, "_mapping_all_pack_by_window", {}).get(window_id, {})
            space = pack.get("mapping_space", self.app.fuzzy_color_space)
            if getattr(space, "is_granular", False):
                expanded = {i for i, cat in enumerate(space.categories)
                            if len(cat.prototypes) > 1}
        self.proto_options = getattr(self, "proto_options", {})
        self.proto_options[window_id] = {
            "kind": "all", "rows": [], "expanded_categories": expanded,
            "gap": 7, "scroll_index": scroll,
        }
        self._refresh_mapping_all_legend_rows(window_id)
        self._reposition_proto_options(window_id)
        self.app._sync_workspace_card_item_states(window_id)
        self.app._schedule_image_workspace_reflow(delay=0)


    def color_mapping(self, window_id):
        """Open Color Mapping directly from Original or Mapping All."""
        if not self.app.image_canvas.find_withtag(window_id):
            self.app.custom_warning("No Window", f"No floating window found with id {window_id}")
            return
        if not getattr(self.app, "COLOR_SPACE", False):
            self.app.custom_warning("No Color Space", "Load a Fuzzy Color Space before applying Color Mapping.")
            return

        previous_mode = getattr(self, "window_mapping_mode", {}).get(window_id)
        locked = getattr(self, "mapping_locked_until_original", {}).get(window_id, False)

        # Color Mapping starts in a neutral state with no prototype selected.
        # If another mapping is currently displayed (including one belonging to
        # an older FCS), restore the original pixels internally first. This is
        # not a user-visible prerequisite; it simply gives the selector a clean
        # starting image while every later calculation still uses the original.
        if previous_mode == "all" or locked:
            self.show_original_image(window_id)

        if not hasattr(self, "window_mapping_mode"):
            self.window_mapping_mode = {}
        self.window_mapping_mode[window_id] = "single"

        try:
            self.app._disable_original_rectangle_sampling(window_id)
        except Exception:
            pass

        self.CAN_APPLY_MAPPING[window_id] = False
        self.SHOW_ORIGINAL[window_id] = True
        self.app._set_image_workspace_active(window_id)
        self._create_single_mapping_panel(window_id)


    def get_proto_percentage(self, window_id):
        """
        Compute/display the prototype coverage mapping for the currently selected prototype.

        UI/job/cache orchestration belongs to this controller.
        Image/membership computation lives in ColorProcessingEngine.
        """
        if getattr(self, "mapping_locked_until_original", {}).get(window_id, False):
            self.app.custom_warning(
                "Restore Original Image",
                "This image belongs to a previous Color Space. Press Original before selecting a prototype."
            )
            return

        if not hasattr(self, "current_protos") or window_id not in self.current_protos:
            self.app.custom_warning("Error", "No prototype selected for this window.")
            return

        if not hasattr(self, "window_image_key") or window_id not in self.window_image_key:
            self.app.custom_warning("Error", "Image cache key not found for this window.")
            return

        info = getattr(self, "proto_options", {}).get(window_id, {})
        choice = info.get("selection")
        if choice is None:
            self.app.custom_warning("Select a Color", "Choose a category or granule first.")
            return
        kind, pos = choice[0], int(choice[1])
        mapping_space = info.get("mapping_space", self.app.fuzzy_color_space)
        mapping_prototypes = mapping_space.prototypes
        if pos < 0 or pos >= len(mapping_prototypes):
            self.app.custom_warning("Invalid Selection", "The selected category no longer exists.")
            return
        granule_index = int(choice[2]) if kind == "granule" else None
        if kind == "granule":
            if not getattr(self.app.fuzzy_color_space, "is_granular", False):
                self.app.custom_warning("Invalid Selection", "This space has no individual granules.")
                return
            cat = mapping_space.categories[pos]
            if not 0 <= granule_index < len(cat.prototypes):
                self.app.custom_warning("Invalid Selection", "The selected granule no longer exists.")
                return
            selected_proto = f"{cat.label} / {cat.prototypes[granule_index].label}"
        else:
            selected_proto = str(mapping_prototypes[pos].label)

        image_key = self.window_image_key[window_id]
        color_space_key = getattr(self.app, "file_path", None)
        cache_scope = (image_key, color_space_key)

        def run_process(cancel_event, job_id):
            try:
                if self._is_job_cancelled(window_id, cancel_event, job_id):
                    return

                if not hasattr(self.app, "images") or window_id not in self.app.images:
                    self.app.image_canvas.after(
                        0,
                        lambda: self.app.custom_warning("Error", "Current image not found for this window.")
                    )
                    return

                original, (w, h) = self._mapping_source_spec(window_id)
                cache_key = (kind, str(mapping_prototypes[pos].label), granule_index, w, h,
                             getattr(mapping_space, "tconorm", None)
                             if kind == "category" else None)
                cached_entry = self._lookup_cached_result(self.proto_percentage_cache_by_image, cache_scope, cache_key)

                if cached_entry is not None:
                    if self._is_job_cancelled(window_id, cancel_event, job_id):
                        return
                    grayscale_image_array = cached_entry["array"]
                    pct = cached_entry["pct"]
                    valid_total = cached_entry["valid_pixels"]
                else:
                    def update_progress(current_step, total_steps):
                        if cancel_event.is_set():
                            raise RuntimeError("__JOB_CANCELLED__")
                        self._update_window_progress(window_id, job_id, current_step, total_steps)

                    prepared = self.app.image_manager.prepare_image(
                        original, (w, h), mapping_space, owner=window_id,
                        cancelled=lambda: self._is_job_cancelled(window_id, cancel_event, job_id))
                    if prepared is None:
                        return
                    valid_mask = prepared.valid_mask
                    mapping_result = self.app.image_manager.get_proto_percentage(
                        prototypes=mapping_prototypes,
                        image=prepared,
                        fuzzy_color_space=mapping_space,
                        selected_option=pos,
                        granule_index=granule_index,
                        progress_callback=update_progress,
                        cancel_callback=lambda: cancel_event.is_set(),
                        return_coverage=True, valid_mask=valid_mask,
                    )

                    if mapping_result is None:
                        return
                    grayscale_image_array, covered_total, valid_total = mapping_result

                    # Force transparent/background pixels to 0 in the grayscale map.
                    if grayscale_image_array.ndim == 2:
                        grayscale_image_array[~valid_mask] = 0

                    if self._is_job_cancelled(window_id, cancel_event, job_id):
                        return

                    pct = 100.0 * covered_total / valid_total if valid_total else 0.0

                    self._store_cached_result(self.proto_percentage_cache_by_image, cache_scope, cache_key, {
                        "array": grayscale_image_array,
                        "pct": pct,
                        "thresh_used": 0.5,
                        "valid_pixels": valid_total,
                        "covered_pixels": covered_total
                    })

                def _ui():
                    if self._is_job_cancelled(window_id, cancel_event, job_id):
                        return

                    self.display_color_mapping(grayscale_image_array, window_id)
                    current_info = getattr(self, "proto_options", {}).get(window_id)
                    if isinstance(current_info, dict) and current_info.get("kind") == "single":
                        current_info["displayed_for"] = choice
                    self.app.image_canvas.itemconfig(
                        f"{window_id}_pct_text",
                        text=(f"{selected_proto}: {pct:.2f}% (μ ≥ 0.5)"
                              if valid_total else f"{selected_proto}: No visible pixels")
                    )

                    # Percentage text changes the compact spacing between image
                    # and selector. Reposition and relayout immediately so the
                    # caption remains centered after Grid/Focus/manual resize.
                    self._reposition_proto_options(window_id)
                    callbacks = getattr(self.app, "_image_workspace_callbacks", {}).get(window_id, {})
                    relayout_cb = callbacks.get("relayout") if isinstance(callbacks, dict) else None
                    if callable(relayout_cb):
                        relayout_cb(window_id)

                    self.app.image_canvas.tag_raise(f"{window_id}_pct_text")

                self.app.image_canvas.after(0, _ui)

            except RuntimeError as e:
                if str(e) != "__JOB_CANCELLED__":
                    error_msg = str(e)
                    self.app.image_canvas.after(
                        0,
                        lambda msg=error_msg: self.app.custom_warning(
                            "Error",
                            f"Error in run_process: {msg}"
                        )
                    )
            except Exception as e:
                error_msg = str(e)
                self.app.image_canvas.after(
                    0,
                    lambda msg=error_msg: self.app.custom_warning(
                        "Error",
                        f"Error in run_process: {msg}"
                    )
                )

        job_id = self._start_window_job(window_id, "proto_percentage", run_process)
        if job_id is not None:
            self._show_window_loading(window_id, "Color Mapping...")


    def display_color_mapping(self, grayscale_image_array, window_id):
        """Display one membership map as grayscale or JFCS-style weighted RGB."""
        try:
            try:
                self.app._disable_original_rectangle_sampling(window_id)
            except Exception:
                pass

            self.modified_image[window_id] = grayscale_image_array

            # Apply the original alpha channel at the mapping resolution.
            source_img = None
            prepared = None
            try:
                map_h, map_w = grayscale_image_array.shape[:2]
                prepared = self._peek_mapping_preprocessing(
                    window_id, self.app.fuzzy_color_space, (map_w, map_h))
                if prepared is not None:
                    alpha_values = prepared.alpha
                else:
                    source_img = self._get_mapping_source_image(window_id, (map_w, map_h))
                    alpha_values = UtilsTools._get_alpha_values_from_pil(source_img)
            except Exception:
                alpha_values = np.full(grayscale_image_array.shape[:2], 255, dtype=np.uint8)

            # Preserve raw grayscale memberships in modified_image/cache.
            # The Color style is a *rendering* of that same result: pixel RGB
            # multiplied by its membership, exactly as in JFCS.
            info = getattr(self, "proto_options", {}).get(window_id, {})
            use_color = (
                isinstance(info, dict)
                and info.get("kind") == "single"
                and info.get("display_style", "gray") == "color"
                and grayscale_image_array.ndim == 2
            )
            if use_color:
                # Convert through PIL so palette (P), grayscale (L) and RGBA
                # originals all produce their actual visible RGB colors.
                if prepared is not None:
                    source_rgb = prepared.rgb
                else:
                    if source_img is None:
                        source_img = self._get_mapping_source_image(window_id, (map_w, map_h))
                    source_rgb = np.asarray(source_img.convert("RGB"), dtype=np.uint8)
                colored = self.app.image_manager.colorize_membership_map(
                    grayscale_image_array, source_rgb
                )
                rgba_array = UtilsTools._apply_alpha_to_rgb_array(colored, alpha_values)
            elif grayscale_image_array.ndim == 2:
                rgba_array = UtilsTools._apply_alpha_to_gray_array(grayscale_image_array, alpha_values)
            else:
                rgba_array = UtilsTools._apply_alpha_to_rgb_array(grayscale_image_array, alpha_values)
            grayscale_image = Image.fromarray(rgba_array.astype(np.uint8), mode="RGBA")

            # Make zoom work over the generated Color Mapping image, not over the original.
            self.app._set_image_zoom_source(window_id, grayscale_image, reset_zoom=True)

            # Resize only for display
            new_width, new_height = self.app.image_dimensions[window_id]
            grayscale_image_display = grayscale_image.resize(
                (new_width, new_height),
                Image.Resampling.LANCZOS
            )

            self.app.images[window_id] = grayscale_image_display
            self.app.display_pil[window_id] = grayscale_image_display

            if hasattr(self.app, "display_pil"):
                self.app.display_pil[window_id] = grayscale_image_display

            img_tk = ImageTk.PhotoImage(grayscale_image_display)
            self.app.floating_images[window_id] = img_tk

            image_items = self.app.image_canvas.find_withtag(f"{window_id}_click_image")
            if image_items:
                self.app.image_canvas.itemconfig(image_items[0], image=img_tk)
            else:
                self.app.custom_warning("Image Error", f"No image found for window_id: {window_id}")

        except Exception as e:
            self.app.custom_warning("Display Error", f"Error displaying the image: {e}")


    def show_original_image(self, window_id):
        """Displays the original image, preserving the current resized dimensions of the floating window."""
        try:
            # Cancel any running process linked to this image before restoring the original
            self._cancel_window_job(window_id)

            if hasattr(self, "window_mapping_mode"):
                self.window_mapping_mode.pop(window_id, None)
            try:
                getattr(self, "_mapping_all_palette_by_window", {}).pop(window_id, None)
                getattr(self, "_mapping_all_pack_by_window", {}).pop(window_id, None)
            except Exception:
                pass

            if hasattr(self, "mapping_locked_until_original"):
                self.mapping_locked_until_original.pop(window_id, None)

            # Hide percentage text when showing original image
            try:
                self.app.image_canvas.itemconfig(f"{window_id}_pct_text", text="")
            except Exception:
                pass

            # Remove the mapping selector/legend from this card.
            try:
                self._destroy_proto_options(window_id)
            except Exception as e:
                self.app.custom_warning("Window Error", f"Error trying to destroy the proto_options panel: {e}")
                return

            # Ensure we have the original PIL image stored
            if not hasattr(self.app, "pil_images_original") or window_id not in self.app.pil_images_original:
                self.app.custom_warning("Not Original Image", f"Original PIL image not found for window_id: {window_id}")
                return

            pil_original = self.app.pil_images_original[window_id]

            # Restore zoom source to the original full-resolution image.
            self.app._set_image_zoom_source(window_id, pil_original, reset_zoom=True)

            # Preserve the current displayed size if the window was resized
            if hasattr(self.app, "image_dimensions") and window_id in self.app.image_dimensions:
                target_w, target_h = self.app.image_dimensions[window_id]
            else:
                target_w, target_h = pil_original.size

            target_w = max(1, int(target_w))
            target_h = max(1, int(target_h))

            # Resize the original image to the current window size
            pil_resized = pil_original.resize((target_w, target_h), Image.Resampling.LANCZOS)

            # Update the current displayed PIL image too
            if hasattr(self.app, "images"):
                self.app.images[window_id] = pil_resized

            # Update the PIL image used as source of truth for saving
            if not hasattr(self.app, "display_pil"):
                self.app.display_pil = {}
            self.app.display_pil[window_id] = pil_resized

            # Create a new PhotoImage with the preserved size
            img_tk = ImageTk.PhotoImage(pil_resized)

            # Keep a reference to avoid garbage collection
            if not hasattr(self.app, "floating_images"):
                self.app.floating_images = {}
            self.app.floating_images[window_id] = img_tk

            # Refresh the cache storing the currently displayed original image
            if not hasattr(self.app, "original_images"):
                self.app.original_images = {}
            self.app.original_images[window_id] = img_tk

            # Find the image item in the canvas
            image_items = self.app.image_canvas.find_withtag(f"{window_id}_img_item")
            if not image_items:
                image_items = self.app.image_canvas.find_withtag(f"{window_id}_click_image")

            if image_items:
                image_id = image_items[0]
                self.app.image_canvas.itemconfig(image_id, image=img_tk)
            else:
                self.app.custom_warning("Image Error", f"No canvas image found for window_id: {window_id}")
                return

            # Reset flags
            self.SHOW_ORIGINAL[window_id] = False
            if self.app.COLOR_SPACE:
                self.CAN_APPLY_MAPPING[window_id] = True

            # Enable rectangle sampling only when the original image is being shown
            try:
                self.app._enable_original_rectangle_sampling(
                    window_id=window_id,
                    target_w=target_w,
                    target_h=target_h
                )
            except Exception as e:
                print(f"Warning enabling original rectangle sampling for {window_id}: {e}")

            # Resynchronize the card without destroying manual move/resize controls.
            try:
                if hasattr(self.app, "floating_window_state") and window_id in self.app.floating_window_state:
                    self.app.floating_window_state[window_id]["w"] = target_w
                    self.app.floating_window_state[window_id]["h"] = target_h
                self.app._sync_workspace_card_item_states(window_id)
                self.app._schedule_image_workspace_reflow()
            except Exception:
                pass

        except Exception as e:
            self.app.custom_warning("Display Error", f"Error displaying the original image: {e}")
            return


    def _display_mapping_all_result(self, window_id, recolored_image, palette_uint8):
        """Display Mapping-All and keep its vertical legend inside the same card."""
        try:
            self.modified_image[window_id] = recolored_image
            if recolored_image.ndim == 3 and recolored_image.shape[-1] == 4:
                pil_to_show = Image.fromarray(recolored_image.astype(np.uint8), mode="RGBA")
            else:
                pil_to_show = Image.fromarray(recolored_image.astype(np.uint8), mode="RGB")

            self.app._set_image_zoom_source(window_id, pil_to_show, reset_zoom=True)
            target_size = getattr(self.app, "image_dimensions", {}).get(window_id)
            if target_size:
                pil_display = pil_to_show.resize(
                    (max(1, int(target_size[0])), max(1, int(target_size[1]))),
                    Image.Resampling.LANCZOS,
                )
            else:
                pil_display = pil_to_show

            self.app.images[window_id] = pil_display
            self.app.display_pil[window_id] = pil_display
            img_tk = ImageTk.PhotoImage(pil_display)
            self.app.floating_images[window_id] = img_tk

            image_items = self.app.image_canvas.find_withtag(f"{window_id}_click_image")
            if not image_items:
                self.app.custom_warning("Image Error", f"No image found for window_id: {window_id}")
                return
            self.app.image_canvas.itemconfig(image_items[0], image=img_tk)

            if not hasattr(self, "_mapping_all_palette_by_window"):
                self._mapping_all_palette_by_window = {}
            self._mapping_all_palette_by_window[window_id] = np.asarray(palette_uint8).copy()

            self._create_mapping_all_panel(window_id, palette_uint8)
            self.app._focus_floating_window(window_id)

        except Exception as exc:
            self.app.custom_warning("Display Error", f"Error displaying the image: {exc}")


    def color_mapping_all(self, window_id):
        """Compute Mapping All directly from any current image view."""
        if not self.app.image_canvas.find_withtag(window_id):
            self.app.custom_warning("No Window", f"No floating window found with id {window_id}")
            return
        if not getattr(self.app, "COLOR_SPACE", False):
            self.app.custom_warning("No Color Space", "Load a Fuzzy Color Space before applying Color Mapping All.")
            return

        # The calculation below always starts from pil_images_original, so an
        # old or different mapping view can be replaced directly. Clear only
        # the old-space display lock; no intermediate Original action is needed.
        try:
            getattr(self, "mapping_locked_until_original", {}).pop(window_id, None)
        except Exception:
            pass

        if not hasattr(self, "window_image_key") or window_id not in self.window_image_key:
            self.app.custom_warning("Error", "Image cache key not found for this window.")
            return
        if not hasattr(self, "window_mapping_mode"):
            self.window_mapping_mode = {}
        self.window_mapping_mode[window_id] = "all"
        initial_view = getattr(self, "_mapping_all_initial_view", {}).pop(
            window_id, ("categories", "original"))
        mapping_space = general_mapping_space(self.app.fuzzy_color_space)
        mapping_prototypes = mapping_space.prototypes

        cache_scope = (self.window_image_key[window_id], getattr(self.app, "file_path", None))
        try:
            self.app._disable_original_rectangle_sampling(window_id)
        except Exception:
            pass
        self.app._sync_workspace_card_item_states(window_id)
        try:
            self.app.image_canvas.itemconfig(f"{window_id}_pct_text", text="")
        except Exception:
            pass
        self.CAN_APPLY_MAPPING[window_id] = False
        self.SHOW_ORIGINAL[window_id] = True
        self._destroy_proto_options(window_id)
        self.app._set_image_workspace_active(window_id)

        def update_progress(job_id, current_step, total_steps):
            if total_steps > 0:
                self._update_window_progress(window_id, job_id, current_step, total_steps)

        def run_process(cancel_event, job_id):
            try:
                if self._is_job_cancelled(window_id, cancel_event, job_id):
                    return
                original, (w, h) = self._mapping_source_spec(window_id)
                proto_labels = tuple(p.label for p in mapping_prototypes)
                flat = (mapping_space.get_all_prototypes()
                        if getattr(mapping_space, "is_granular", False)
                        else mapping_prototypes)
                cache_key = (w, h, proto_labels, tuple(p.label for p in flat),
                             getattr(mapping_space, "tconorm", None))
                maps = self._lookup_cached_result(self.cm_cache_by_image, cache_scope, cache_key)
                prepared = None
                if maps is None:
                    prepared = self.app.image_manager.prepare_image(
                        original, (w, h), mapping_space, owner=window_id,
                        cancelled=lambda: self._is_job_cancelled(window_id, cancel_event, job_id))
                    if prepared is None:
                        return
                    maps = self.app.image_manager.get_category_granule_label_maps(
                        image=prepared, fuzzy_color_space=mapping_space,
                        valid_mask=prepared.valid_mask,
                        progress_callback=lambda current, total: update_progress(job_id, current, total),
                        cancel_callback=lambda: self._is_job_cancelled(window_id, cancel_event, job_id))
                    if maps is None:
                        return
                    if self._is_job_cancelled(window_id, cancel_event, job_id):
                        return
                    self._store_cached_result(self.cm_cache_by_image, cache_scope, cache_key, maps)
                else:
                    prepared = self.app.image_manager.peek_prepared_image(
                        original, (w, h), mapping_space, owner=window_id)
                if self._is_job_cancelled(window_id, cancel_event, job_id):
                    return
                if prepared is not None:
                    alpha_values, valid_mask, source_rgb = prepared.alpha, prepared.valid_mask, prepared.rgb
                else:
                    # A final-map cache hit must not trigger LAB preprocessing.
                    source_img = (original if original.size == (w, h) else
                                  original.resize((w, h), Image.Resampling.LANCZOS))
                    alpha_values = UtilsTools._get_alpha_values_from_pil(source_img)
                    valid_mask = alpha_values > 0
                    source_rgb = np.asarray(UtilsTools._pil_rgb_for_processing(source_img))
                label_maps = {"categories": maps[0], "granules": maps[1]}
                category_original = self.app.image_manager.build_original_palette_uint8(
                    mapping_prototypes, mapping_space.color_space)
                category_alt = self.app.image_manager.build_alt_palette_uint8(mapping_prototypes)
                granule_original = self.app.image_manager.build_original_palette_uint8(
                    flat, mapping_space.color_space)
                granule_alt = self.app.image_manager.build_granule_alt_palette_uint8(
                    mapping_space, category_alt)
                if getattr(mapping_space, "is_granular", False):
                    offset = 0
                    for i, category in enumerate(mapping_space.categories):
                        count = len(category.prototypes)
                        if count == 1:
                            granule_alt[offset] = category_alt[i]
                        offset += count
                level_palettes = {
                    "categories": {"original": category_original, "alt": category_alt},
                    "granules": {"original": granule_original, "alt": granule_alt},
                }
                level, scheme = initial_view
                if level not in label_maps:
                    level = "categories"
                if scheme not in ("original", "alt"):
                    scheme = "original"
                palette = level_palettes[level][scheme]
                label_map = label_maps[level]
                recolored_image = self.app.image_manager.recolor_label_map(
                    label_map, palette, alpha_values)
                if not mapping_space.covering:
                    missing = (label_map < 0) & valid_mask
                    if np.any(missing):
                        recolored_image[missing, :3] = source_rgb[missing, :3]
                        recolored_image[missing, 3] = alpha_values[missing]
                window_pack = {
                    "label_maps": label_maps, "level_palettes": level_palettes,
                    "label_map": label_map, "alpha_values": alpha_values,
                    "palettes": level_palettes[level], "level": level,
                    "scheme": scheme, "cache_key": cache_key,
                    "mapping_space": mapping_space,
                }
                def _ui():
                    if self._is_job_cancelled(window_id, cancel_event, job_id):
                        return
                    self._mapping_all_pack_by_window[window_id] = window_pack
                    self._display_mapping_all_result(window_id, recolored_image, palette)
                self.app.image_canvas.after(0, _ui)
            except RuntimeError as exc:
                if str(exc) != "__JOB_CANCELLED__":
                    msg = str(exc)
                    self.app.image_canvas.after(0, lambda m=msg: self.app.custom_warning("Processing Error", f"Error in color mapping: {m}"))
            except Exception as exc:
                msg = str(exc)
                self.app.image_canvas.after(0, lambda m=msg: self.app.custom_warning("Processing Error", f"Error in color mapping: {m}"))

        job_id = self._start_window_job(window_id, "color_mapping_all", run_process)
        if job_id is not None:
            self._show_window_loading(window_id, "Color Mapping All...")


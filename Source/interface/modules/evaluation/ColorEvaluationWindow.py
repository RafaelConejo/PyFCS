"""Tkinter Color Evaluation controller.

Owns the evaluation window, its comparison state, custom color dialog, image
sampler and graph controls. Numerical evaluation stays in ColorEvaluationManager;
shared thresholds, active model and application-wide coordination stay in PyFCSApp.
"""
import os
import platform
import numpy as np
import tkinter as tk
from tkinter import ttk, filedialog
from PIL import Image, ImageOps, ImageTk

from Source.colorspace.ReferenceDomain import ReferenceDomain
from Source.fuzzy.GranularFuzzyColorSpace import GranularFuzzyColorSpace
from Source.interface.modules.common import UtilsTools
from Source.interface.modules.visualization.VisualManager import VisualManager
from Source.interface.modules.evaluation.ColorEvaluationManager import membership_snapshot, nearest_granule


class ColorEvaluationWindow:
    def __init__(self, app):
        self.app = app
        self.root = app.root
        self._color_evaluation_window = None
        self._color_evaluation_paned = None
        self._color_evaluation_vars = None

    def _apply_color_evaluation_result_style(self, vars_dict, status):
        """Apply the shared threshold result visual style to the Color Evaluation result card."""
        refs = vars_dict.get("analysis_result_refs")
        if not refs:
            return

        self.app._apply_threshold_result_style(refs, status)

    def _update_color_evaluation_result_card(self, vars_dict, title, detail="", summary="", status="neutral"):
        """Update the styled result card used in the Color Evaluation panel."""
        vars_dict["selected_result_var"].set(title)
        vars_dict["selected_detail_var"].set(detail)
        vars_dict["selected_summary_var"].set(summary)

        self._apply_color_evaluation_result_style(vars_dict, status)

    def color_evaluation(self):
        """Open a window to study color spaces and threshold configurations."""
        try:
            if hasattr(self, "_color_evaluation_window") and self._color_evaluation_window is not None:
                if self._color_evaluation_window.winfo_exists():
                    self._color_evaluation_window.lift()
                    self._color_evaluation_window.focus_force()
                    return
        except Exception:
            pass

        self.app._ensure_threshold_settings()

        win = tk.Toplevel(self.root)
        win.withdraw()
        self._color_evaluation_window = win

        win.title("Color Space Evaluation")
        WIN_W, WIN_H = 1080, 760
        win.geometry(f"{WIN_W}x{WIN_H}")
        win.minsize(980, 680)
        win.resizable(True, True)
        win.configure(bg="#f2f2f2")
        win.protocol("WM_DELETE_WINDOW", self._on_close_color_evaluation_window)

        # Fullscreen toggle for this specific Toplevel window
        def toggle_color_evaluation_fullscreen(event=None):
            try:
                current_state = bool(win.attributes("-fullscreen"))
                win.attributes("-fullscreen", not current_state)

                # When leaving fullscreen, restore a normal usable size
                if current_state:
                    win.geometry(f"{WIN_W}x{WIN_H}")
                    win.update_idletasks()
                    try:
                        self.app.center_popup(win, WIN_W, WIN_H)
                    except Exception:
                        pass

            except tk.TclError:
                # Fallback for systems/window managers where -fullscreen is not available
                try:
                    if platform.system() == "Windows":
                        if win.state() == "zoomed":
                            win.state("normal")
                            win.geometry(f"{WIN_W}x{WIN_H}")
                        else:
                            win.state("zoomed")
                    else:
                        screen_width = win.winfo_screenwidth()
                        screen_height = win.winfo_screenheight()
                        win.geometry(f"{screen_width}x{screen_height}+0+0")
                except Exception:
                    pass

        win.bind("<Escape>", toggle_color_evaluation_fullscreen)
        win.bind("<F11>", toggle_color_evaluation_fullscreen)

        self._build_color_evaluation_window(win)
        win.update_idletasks()

        # Prepare a full-size geometry while still hidden. Some window managers
        # only honour -fullscreen once a window is mapped, so its first frame
        # must already match the main window instead of flashing at 1080x760.
        try:
            self.root.update_idletasks()
            root_w, root_h = self.root.winfo_width(), self.root.winfo_height()
            if root_w < 980 or root_h < 680:
                raise ValueError("Main window dimensions unavailable")
            x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
            win.geometry(f"{root_w}x{root_h}+{x}+{y}")
        except (ValueError, tk.TclError):
            sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
            win.geometry(f"{sw}x{sh}+0+0")

        try:
            win.attributes("-fullscreen", True)
        except tk.TclError:
            if platform.system() == "Windows":
                try:
                    win.state("zoomed")
                except tk.TclError:
                    pass

        if platform.system() != "Windows":
            # If fullscreen is unsupported before mapping, size the hidden
            # window to the screen so even the fallback opens without a jump.
            try:
                if not bool(win.attributes("-fullscreen")):
                    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
                    win.geometry(f"{sw}x{sh}+0+0")
            except tk.TclError:
                pass

        win.deiconify()
        # Linux/X11 and some Windows managers may defer fullscreen until map.
        try:
            if not bool(win.attributes("-fullscreen")):
                win.attributes("-fullscreen", True)
        except tk.TclError:
            if platform.system() == "Windows":
                try:
                    win.state("zoomed")
                except tk.TclError:
                    pass
        win.focus_set()
        win.after_idle(self._set_color_evaluation_initial_sash)

    def _on_close_color_evaluation_window(self):
        """Handle manual closing of the Color Evaluation window."""
        try:
            if hasattr(self, "_color_evaluation_window") and self._color_evaluation_window is not None:
                if self._color_evaluation_window.winfo_exists():
                    self._color_evaluation_window.destroy()
        except Exception:
            pass
        finally:
            self._color_evaluation_window = None
            self._color_evaluation_paned = None
            self._color_evaluation_vars = None

    def _set_color_evaluation_initial_sash(self):
        """Set the initial PanedWindow split after the window has its final size."""
        try:
            paned = getattr(self, "_color_evaluation_paned", None)
            if paned is None or not paned.winfo_exists():
                return

            paned.update_idletasks()
            total_w = paned.winfo_width()

            if total_w <= 1:
                return

            sash_x = max(330, min(int(total_w * 0.36), total_w - 540))  # color explorer | analysis
            paned.sash_place(0, sash_x, 1)
        except Exception:
            pass

    def _build_color_evaluation_window(self, win):
        """Build the full Color Evaluation window."""
        vars_dict = self._create_color_evaluation_vars()
        self._color_evaluation_vars = vars_dict

        main = tk.Frame(win, bg="#f2f2f2")
        main.pack(fill="both", expand=True, padx=14, pady=12)

        # Top: Threshold settings
        refs = self.app._build_shared_threshold_panel(
            parent=main,
            vars_dict=vars_dict,
            title="Threshold Configuration",
            variant="summary"
        )

        vars_dict["threshold_panel_refs"] = refs

        # Color Space Data block
        table_panel = tk.Frame(main, bg="#f2f2f2")
        table_panel.pack(fill="both", expand=True, pady=(8, 0))

        # Center the active space identity; keep loading actions on the right.
        header_container = tk.LabelFrame(table_panel, text="Color Space Data",
            labelanchor="n", font=("Segoe UI", 11, "bold"),
            bg="#f8fafc", fg="#1f2937", bd=1, relief="solid")
        header_container.pack(fill="x", pady=(0, 9))

        # Reserve a balancing column when there is enough room to center the
        # identity across the whole header. On smaller windows, center it in
        # the remaining space without overlapping the loading actions.
        header_container.grid_columnconfigure(1, weight=1)
        space_identity = tk.Frame(header_container, bg="#f8fafc")
        space_identity.grid(row=0, column=1, sticky="ew", padx=12, pady=(4, 5))

        summary_row = tk.Frame(space_identity, bg="#f8fafc")
        summary_row.pack(anchor="center")

        tk.Label(
            summary_row,
            text="Color space:",
            font=("Segoe UI", 9, "bold"),
            bg="#f8fafc",
            fg="#6b7280"
        ).pack(side="left", padx=(0, 5))

        tk.Label(
            summary_row,
            textvariable=vars_dict["space_name_var"],
            font=("Segoe UI", 9, "bold"),
            bg="#f8fafc",
            fg=UtilsTools.UI_ACCENT
        ).pack(side="left", padx=(0, 16))

        tk.Label(
            summary_row,
            textvariable=vars_dict["space_items_label_var"],
            font=("Segoe UI", 9, "bold"),
            bg="#f8fafc",
            fg="#6b7280"
        ).pack(side="left", padx=(0, 5))

        tk.Label(
            summary_row,
            textvariable=vars_dict["space_count_var"],
            font=("Segoe UI", 9, "bold"),
            bg="#f8fafc",
            fg="#1f2937"
        ).pack(side="left")

        buttons_row = tk.Frame(header_container, bg="#f8fafc")
        buttons_row.grid(row=0, column=2, sticky="e", padx=(4, 13), pady=(5, 7))

        def _center_space_identity(_event=None):
            width = header_container.winfo_width() - 2
            actions_width = buttons_row.winfo_reqwidth() + 17
            identity_width = summary_row.winfo_reqwidth() + 24
            balance = min(actions_width, max(0, width - actions_width - identity_width))
            if int(header_container.grid_columnconfigure(0, "minsize")) != balance:
                header_container.grid_columnconfigure(0, minsize=balance)

        header_container.bind("<Configure>", _center_space_identity, add="+")
        summary_row.bind("<Configure>", _center_space_identity, add="+")
        buttons_row.bind("<Configure>", _center_space_identity, add="+")

        tk.Button(
            buttons_row,
            text="Use loaded color space",
            command=lambda: self._load_current_color_space_for_evaluation(vars_dict),
            font=("Segoe UI", 9, "bold"),
            bg=UtilsTools.UI_ADD_CATEGORY_BG,
            fg=UtilsTools.UI_ADD_CATEGORY_FG,
            activebackground=UtilsTools.UI_ADD_CATEGORY_HOVER,
            activeforeground=UtilsTools.UI_ADD_CATEGORY_FG,
            relief="solid", bd=1, padx=11, pady=6,
            cursor="hand2",
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            buttons_row,
            text="Load new color space",
            command=lambda: self._load_external_color_space_for_evaluation(vars_dict),
            font=("Segoe UI", 9, "bold"),
            # Palette-Based Creation's shared "Add Color Source" style.
            bg=UtilsTools.UI_ADD_SOURCE_BG,
            fg=UtilsTools.UI_ADD_SOURCE_FG,
            activebackground=UtilsTools.UI_ADD_SOURCE_HOVER,
            activeforeground=UtilsTools.UI_ADD_SOURCE_FG,
            relief="solid", bd=1, padx=11, pady=6,
            cursor="hand2",
        ).pack(side="left")

        # PanedWindow real
        paned = tk.PanedWindow(
            table_panel,
            orient="horizontal",
            sashwidth=10,
            sashrelief="flat",
            bd=0,
            bg="#f2f2f2"
        )
        paned.pack(fill="both", expand=True, pady=(0, 2))

        left_panel = tk.LabelFrame(paned, text="Explore Colors", labelanchor="n",
            font=("Segoe UI", 11, "bold"), bg="white", fg="#1f2937", bd=1, relief="solid")
        right_panel = tk.LabelFrame(paned, text="Color Comparison & Threshold Analysis", labelanchor="n",
            font=("Segoe UI", 11, "bold"), bg="white", fg="#1f2937", bd=1, relief="solid")

        paned.add(left_panel, minsize=315)
        paned.add(right_panel, minsize=520)

        self._color_evaluation_paned = paned

        # Left: searchable category/granule explorer.  All entries are real
        # LAB colors; category headers never stand in for a fictitious centroid.
        explorer_top = tk.Frame(left_panel, bg="white")
        explorer_top.pack(fill="x", padx=11, pady=(8, 8))
        value_header = tk.Frame(explorer_top, bg="white")
        value_header.pack(side="right")
        previous_mode_button = tk.Button(
            value_header, text="◀", font=("Segoe UI", 9), width=2,
            bg="white", fg="#1f2937", relief="solid", bd=1,
            cursor="hand2",
            command=lambda: self._rotate_color_evaluation_table_display_mode(
                vars_dict, direction=-1),
        )
        previous_mode_button.pack(side="left", padx=(0, 5))
        display_mode_combo = UtilsTools.styled_combobox(
            value_header, textvariable=vars_dict["color_display_mode_var"],
            values=UtilsTools.get_supported_color_value_spaces(),
            state="readonly", width=12,
        )
        display_mode_combo.pack(side="left", padx=(0, 5))
        next_mode_button = tk.Button(
            value_header, text="▶", font=("Segoe UI", 9), width=2,
            bg="white", fg="#1f2937", relief="solid", bd=1,
            cursor="hand2",
            command=lambda: self._rotate_color_evaluation_table_display_mode(
                vars_dict, direction=1),
        )
        next_mode_button.pack(side="left")
        display_mode_combo.bind(
            "<<ComboboxSelected>>",
            lambda e: self._refresh_color_evaluation_table_display_mode(vars_dict)
        )
        vars_dict["color_display_navigation"] = (
            previous_mode_button, display_mode_combo, next_mode_button)

        search_holder = tk.Frame(explorer_top, bg="white")
        search_holder.pack(side="left", padx=(0, 8))
        tk.Label(search_holder, text="Search", bg="white", fg="#374151",
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 7))
        tk.Entry(search_holder, textvariable=vars_dict["color_search_var"],
                 font=("Segoe UI", 10), relief="solid", bd=1, width=12,
                 highlightthickness=0).pack(side="left")
        tk.Button(search_holder, text="Clear", command=lambda: vars_dict["color_search_var"].set(""),
                  font=("Segoe UI", 9), fg="#6b7280", bg="white", relief="flat",
                  bd=0, cursor="hand2").pack(side="left", padx=(5, 0))

        def _fit_explorer_controls(event=None):
            narrow = explorer_top.winfo_width() < (search_holder.winfo_reqwidth() + value_header.winfo_reqwidth() + 8)
            if getattr(explorer_top, "_stacked", None) == narrow:
                return
            explorer_top._stacked = narrow
            value_header.pack_forget()
            search_holder.pack_forget()
            if narrow:
                value_header.pack(anchor="center", pady=(0, 4))
                search_holder.pack(anchor="center")
            else:
                value_header.pack(side="right")
                search_holder.pack(side="left", padx=(0, 8))
        explorer_top.bind("<Configure>", _fit_explorer_controls)

        tk.Frame(left_panel, bg="#e5e7eb", height=1).pack(fill="x")
        rows_canvas = tk.Canvas(left_panel, bg="white", highlightthickness=0, bd=0)
        rows_scroll = UtilsTools.styled_scrollbar(left_panel, orient="vertical",
                                    command=rows_canvas.yview)
        rows_inner = tk.Frame(rows_canvas, bg="white")
        rows_inner.bind("<Configure>", lambda e: rows_canvas.configure(
            scrollregion=rows_canvas.bbox("all")))
        inner_window = rows_canvas.create_window((0, 0), window=rows_inner, anchor="nw")
        rows_canvas.bind("<Configure>", lambda e: rows_canvas.itemconfigure(
            inner_window, width=max(1, e.width)))
        rows_canvas.configure(yscrollcommand=rows_scroll.set)
        rows_canvas.pack(side="left", fill="both", expand=True)
        rows_scroll.pack(side="right", fill="y")
        self.app._register_vertical_mousewheel_canvas(rows_canvas)

        # Right panel
        analysis_actions = tk.Frame(right_panel, bg="white")
        analysis_actions.pack(fill="x", padx=14, pady=(8, 5))

        def _run_analysis_action(action_key, callback):
            # Clear is a one-shot action, not a persistent analysis mode.
            self._set_color_evaluation_active_action(
                vars_dict, None if action_key == "clear" else action_key
            )
            callback()

        btn_compare = tk.Button(
            analysis_actions,
            text="Compare with Another Color",
            font=("Segoe UI", 9, "bold"),
            relief="solid", bd=1, padx=8, pady=4,
            cursor="hand2",
            command=lambda: _run_analysis_action(
                "compare",
                lambda: self._enable_color_evaluation_comparison_mode(vars_dict)
            )
        )
        btn_compare.pack(side="left", fill="x", expand=True, padx=(0, 6))

        btn_custom = tk.Button(
            analysis_actions,
            text="Evaluate Custom Color",
            font=("Segoe UI", 9, "bold"),
            relief="solid", bd=1, padx=8, pady=4,
            cursor="hand2",
            command=lambda: _run_analysis_action(
                "custom",
                lambda: self._open_custom_color_input_dialog(vars_dict)
            )
        )
        btn_custom.pack(side="left", fill="x", expand=True, padx=(0, 6))

        btn_sample = tk.Button(
            analysis_actions,
            text="Sample from Image",
            font=("Segoe UI", 9, "bold"),
            relief="solid", bd=1, padx=8, pady=4,
            cursor="hand2",
            command=lambda: _run_analysis_action(
                "sample",
                lambda: self._open_color_evaluation_image_sampler(vars_dict)
            )
        )
        btn_sample.pack(side="left", fill="x", expand=True)

        analysis_extra_actions = tk.Frame(right_panel, bg="white")
        analysis_extra_actions.pack(fill="x", padx=14, pady=(0, 7))

        btn_closest = tk.Button(
            analysis_extra_actions,
            text="Find closest prototype",
            font=("Segoe UI", 9, "bold"),
            relief="solid", bd=1, padx=8, pady=4,
            cursor="hand2",
            command=lambda: _run_analysis_action(
                "closest",
                lambda: self._show_color_evaluation_closest_prototypes(vars_dict)
            )
        )
        btn_closest.pack(side="left", fill="x", expand=True, padx=(0, 6))

        btn_clear = tk.Button(
            analysis_extra_actions,
            text="Clear Comparison",
            font=("Segoe UI", 9, "bold"),
            relief="solid", bd=1, padx=8, pady=4,
            cursor="hand2",
            command=lambda: _run_analysis_action(
                "clear",
                lambda: self._clear_color_evaluation_comparison(vars_dict)
            )
        )
        btn_clear.pack(side="left", fill="x", expand=True)

        vars_dict["closest_action_button"] = btn_closest
        vars_dict["analysis_action_buttons"] = {
            "compare": btn_compare,
            "custom": btn_custom,
            "sample": btn_sample,
            "closest": btn_closest,
            "clear": btn_clear,
        }

        self._set_color_evaluation_active_action(vars_dict, None)

        tk.Label(
            right_panel,
            textvariable=vars_dict["analysis_mode_var"],
            anchor="center",
            justify="center",
            bg="#f5f5f5",
            fg="#555555",
            font=("Segoe UI", 9, "italic"),
            padx=10,
            pady=3
        ).pack(fill="x", padx=14, pady=(0, 7))

        # Scrollable analysis body
        analysis_scroll_container = tk.Frame(right_panel, bg="white")
        analysis_scroll_container.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        analysis_canvas = tk.Canvas(
            analysis_scroll_container,
            bg="white",
            highlightthickness=0,
            bd=0
        )

        analysis_scrollbar = UtilsTools.styled_scrollbar(
            analysis_scroll_container,
            orient="vertical",
            command=analysis_canvas.yview
        )

        analysis_body = tk.Frame(analysis_canvas, bg="white")

        analysis_body_window = analysis_canvas.create_window(
            (0, 0),
            window=analysis_body,
            anchor="nw"
        )

        analysis_canvas.configure(yscrollcommand=analysis_scrollbar.set)

        analysis_canvas.pack(side="left", fill="both", expand=True)
        analysis_scrollbar.pack(side="right", fill="y")

        def _update_analysis_scroll_region(event=None):
            try:
                analysis_canvas.configure(scrollregion=analysis_canvas.bbox("all"))
            except Exception:
                pass

        def _update_analysis_body_width(event=None):
            try:
                canvas_width = analysis_canvas.winfo_width()
                analysis_canvas.itemconfig(analysis_body_window, width=canvas_width)
            except Exception:
                pass

        analysis_body.bind("<Configure>", _update_analysis_scroll_region)
        analysis_canvas.bind("<Configure>", _update_analysis_body_width)

        self.app._register_vertical_mousewheel_canvas(analysis_canvas)

        # Side-by-side visual comparison. Color swatches share a neutral surround;
        # selected/secondary labels and LAB readouts are driven by existing state.
        preview_bg = "#f8fafc"
        preview_border = "#d6dce5"
        preview_text = "#1f2937"
        colors_row = tk.Frame(analysis_body, bg="white")
        colors_row.pack(fill="x", pady=(0, 5))
        colors_row.grid_columnconfigure(0, weight=1, uniform="colors")
        colors_row.grid_columnconfigure(1, weight=0)
        colors_row.grid_columnconfigure(2, weight=1, uniform="colors")

        def _build_comparison_preview(column, heading, name_var, meta_var, lab_var,
                                      initial_hex):
            card = tk.Frame(colors_row, bg=preview_bg, highlightthickness=1,
                            highlightbackground=preview_border)
            card.grid(row=0, column=column, sticky="nsew", padx=3, pady=2)
            tk.Label(card, text=heading, bg=preview_bg, fg="#6b7280",
                     font=("Segoe UI", 9, "bold")).pack(pady=(4, 2))
            swatch = tk.Canvas(card, width=74, height=70, bg=preview_bg,
                               highlightthickness=0, bd=0)
            swatch.pack(anchor="center")
            rect = swatch.create_rectangle(3, 3, 71, 67, fill=initial_hex,
                                            outline="#848b95", width=1)
            tk.Label(card, textvariable=name_var, bg=preview_bg, fg=preview_text,
                     font=("Segoe UI", 10, "bold"), wraplength=200,
                     justify="center").pack(fill="x", padx=6, pady=(2, 0))
            meta_label = tk.Label(
                card, textvariable=meta_var, bg=preview_bg, fg="#687284",
                font=("Segoe UI", 8), wraplength=200, justify="center")
            lab_label = tk.Label(
                card, textvariable=lab_var, bg=preview_bg, fg="#586174",
                font=("Consolas", 8), wraplength=210, justify="center")
            lab_label.pack(fill="x", padx=6, pady=(1, 4))

            def _show_meta_when_available(*_args):
                # An empty caption must not reserve a blank row in atomic spaces.
                if meta_var.get().strip():
                    if not meta_label.winfo_manager():
                        meta_label.pack(before=lab_label, fill="x", padx=6)
                elif meta_label.winfo_manager():
                    meta_label.pack_forget()

            meta_var.trace_add("write", _show_meta_when_available)
            _show_meta_when_available()
            swatch._pyfcs_meta_label = meta_label
            return swatch, rect

        primary_swatch, primary_rect = _build_comparison_preview(
            0, "Selected color", vars_dict["primary_name_var"],
            vars_dict["primary_meta_var"], vars_dict["primary_lab_var"], "#cccccc"
        )
        btn_swap = tk.Button(
            colors_row, text="⇄", font=("Segoe UI", 16, "bold"),
            bg="white", fg=UtilsTools.UI_ACCENT, relief="flat",
            activebackground=UtilsTools.UI_ACCENT_SOFT,
            cursor="hand2", state="disabled",
            command=lambda: self._swap_color_evaluation_rows(vars_dict)
        )
        btn_swap.grid(row=0, column=1, padx=5)
        vars_dict["swap_color_button"] = btn_swap
        secondary_swatch, secondary_rect = _build_comparison_preview(
            2, "Reference color", vars_dict["secondary_name_var"],
            vars_dict["secondary_meta_var"], vars_dict["secondary_lab_var"], "#f0f0f0"
        )

        # The compact Quick Samples strip keeps experiment history separate from
        # the color-space explorer. Each tile can be assigned to Selected or
        # Reference, pinned, or revisited without reopening a dialog.
        quick_outer = tk.Frame(analysis_body, bg="#f8fafc", highlightbackground="#d6dce5", highlightthickness=1)
        quick_header = tk.Frame(quick_outer, bg="#f8fafc")
        quick_header.pack(fill="x", padx=8, pady=(1, 1))
        quick_header.grid_columnconfigure(0, weight=1)
        quick_header.grid_columnconfigure(1, weight=0)
        quick_header.grid_columnconfigure(2, weight=1)

        # Left: section title. Center: target for selected sample. Right: clear.
        quick_title_btn = tk.Button(
            quick_header, text="▾  Quick Samples", font=("Segoe UI", 9, "bold"),
            fg=UtilsTools.UI_ACCENT_DARK, bg="#f8fafc", relief="flat", bd=0, cursor="hand2",
            command=lambda: self._toggle_color_evaluation_quick_samples(vars_dict))
        quick_title_btn.grid(row=0, column=0, sticky="w")
        target_controls = tk.Frame(quick_header, bg="#f8fafc")
        target_controls.grid(row=0, column=1)
        tk.Label(target_controls, text="Add to:", bg="#f8fafc", fg="#697386",
                 font=("Segoe UI", 8)).pack(side="left", padx=(0, 3))
        for value, label in (("A", "Selected"), ("B", "Reference")):
            tk.Radiobutton(target_controls, text=label, value=value,
                           variable=vars_dict["quick_samples_target_var"],
                           bg="#f8fafc", activebackground="#f8fafc",
                           font=("Segoe UI", 8), padx=1).pack(side="left", padx=(0, 1))
        tk.Button(quick_header, text="Clear recent", font=("Segoe UI", 8, "bold"),
                  bg="#f8fafc", fg=UtilsTools.UI_ACCENT, relief="flat", cursor="hand2",
                  activebackground="#f8fafc", activeforeground=UtilsTools.UI_ACCENT_DARK,
                  command=lambda: self._clear_color_evaluation_recent_samples(vars_dict)
                  ).grid(row=0, column=2, sticky="e")
        quick_body = tk.Frame(quick_outer, bg="#f8fafc")
        quick_body.pack(fill="x", padx=6, pady=(0, 1))

        # There is exactly one results card below Quick Samples. Avoid the
        # duplicate red/green status strip that hid the actual analysis.
        quick_canvas = tk.Canvas(quick_body, height=53, bd=0,
                                 highlightthickness=0, bg="#f8fafc")
        quick_scroll = UtilsTools.styled_scrollbar(quick_body, orient="horizontal",
                                     command=quick_canvas.xview)
        quick_tiles = tk.Frame(quick_canvas, bg="#f8fafc")
        quick_canvas.create_window((0, 0), window=quick_tiles, anchor="nw")
        quick_canvas.configure(xscrollcommand=quick_scroll.set)
        quick_canvas.pack(fill="x", expand=True)
        quick_scroll.pack(fill="x")
        quick_empty_label = tk.Label(
            quick_body,
            text="No samples yet. Select a color or use Custom Color / Sample from Image.",
            bg="#f8fafc", fg="#6b7280", font=("Segoe UI", 9),
            anchor="center", justify="center", wraplength=450,
        )
        def _fit_quick_sample_scroll(_event=None):
            quick_canvas.configure(scrollregion=quick_canvas.bbox("all"))
            # Avoid losing a line of space to an unnecessary scrollbar.
            overflowing = quick_tiles.winfo_reqwidth() > quick_canvas.winfo_width() + 2
            if overflowing and not quick_scroll.winfo_manager():
                quick_scroll.pack(fill="x")
            elif not overflowing and quick_scroll.winfo_manager():
                quick_scroll.pack_forget()

        quick_tiles.bind("<Configure>", _fit_quick_sample_scroll)
        quick_canvas.bind("<Configure>", _fit_quick_sample_scroll)
        vars_dict.update({
            "quick_samples_outer": quick_outer,
            "quick_samples_tiles": quick_tiles,
            "quick_samples_canvas": quick_canvas,
            "quick_samples_scroll": quick_scroll,
            "quick_samples_empty_label": quick_empty_label,
            "quick_samples_title_btn": quick_title_btn,
            "quick_samples_body": quick_body,
            "quick_samples_after": colors_row,
        })
        self._render_color_evaluation_quick_samples(vars_dict)

        tk.Frame(analysis_body, bg="#e5e7eb", height=1).pack(fill="x", pady=(2, 3))

        # Results + Membership column
        results_block = tk.Frame(analysis_body, bg="white")
        results_block.pack(fill="both", expand=True)

        results_columns = tk.Frame(results_block, bg="white")
        results_columns.pack(fill="x", expand=False)

        # Fixed right column for Graphs / Membership.
        # Left column takes the remaining width.
        results_columns.grid_columnconfigure(0, weight=1)
        results_columns.grid_columnconfigure(1, weight=0, minsize=200)
        results_columns.grid_rowconfigure(0, weight=1)

        result_left = tk.Frame(results_columns, bg="white")
        result_left.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 8)
        )

        # Right side column: Membership panel + Graph buttons
        # Hidden by default; shown only when a custom/sample color exists.
        # Membership height will be synchronized with the Results card.
        right_side_column = tk.Frame(
            results_columns,
            bg="white"
        )
        right_side_column.grid(
            row=0,
            column=1,
            sticky="new",
            padx=(8, 0)
        )

        # Historical spacer retained only for compatibility (not packed).
        membership_title_spacer = tk.Label(
            right_side_column,
            text="",
            font=("Sans", 10, "bold"),
            anchor="w",
            bg="white"
        )
        # Do not pack here.

        # Membership panel
        membership_right = tk.Frame(
            right_side_column,
            bg="white",
            bd=1,
            relief="solid",
            width=300,
            height=220
        )
        membership_right.pack_propagate(False)

        tk.Label(
            membership_right,
            text="Membership Degrees",
            font=("Sans", 10, "bold"),
            anchor="w",
            bg="white",
            padx=10,
            pady=8
        ).pack(fill="x")

        membership_options = tk.Frame(membership_right, bg="white")
        membership_options.pack(fill="x", padx=8, pady=(0, 4))
        vars_dict["evaluation_operator_var"] = tk.StringVar(value="Bounded Sum")
        tk.Label(membership_options, text="T-conorm", bg="white", fg="#6b7280",
                 font=("Segoe UI", 8, "bold")).pack(side="left")
        operator_combo = UtilsTools.styled_combobox(membership_options,
            textvariable=vars_dict["evaluation_operator_var"], values=("Bounded Sum", "Max"),
            width=11, state="readonly")
        operator_combo.pack(side="right")
        operator_combo.bind("<<ComboboxSelected>>", lambda e: self._change_color_evaluation_operator(vars_dict))
        vars_dict["evaluation_operator_combo"] = operator_combo
        level_row = tk.Frame(membership_right, bg="white")
        level_row.pack(fill="x", padx=8, pady=(0, 4))
        tk.Label(level_row,text="Explore level",bg="white",fg="#6b7280",font=("Segoe UI",8,"bold")).pack(side="left")
        vars_dict["evaluation_level_var"] = tk.StringVar(value="Root categories")
        level_combo = UtilsTools.styled_combobox(level_row,textvariable=vars_dict["evaluation_level_var"],
                        values=("Root categories",),width=14,state="readonly")
        level_combo.pack(side="right")
        level_combo.bind("<<ComboboxSelected>>", lambda e:self._explore_color_evaluation_level(vars_dict))
        vars_dict["evaluation_level_combo"] = level_combo
        vars_dict["evaluation_level_row"] = level_row
        vars_dict["evaluation_show_zeros"] = tk.BooleanVar(value=False)
        tk.Checkbutton(membership_right, text="Show zero memberships", variable=vars_dict["evaluation_show_zeros"],
            command=lambda: self._render_evaluation_membership_tree(vars_dict), bg="white",
            font=("Segoe UI", 8), activebackground="white").pack(anchor="center")
        vars_dict["evaluation_winner_var"] = tk.StringVar(value="")
        tk.Label(membership_right, textvariable=vars_dict["evaluation_winner_var"], bg="white",
                 fg=UtilsTools.UI_ACCENT, font=("Segoe UI", 8, "bold"), wraplength=250,
                 justify="center").pack(fill="x", padx=5, pady=(3, 2))
        vars_dict["evaluation_reference_button"] = tk.Button(membership_right, text="Highest Degree",
            command=lambda: self._use_evaluation_highest_degree(vars_dict), bg=UtilsTools.UI_ACCENT_SOFT,
            fg=UtilsTools.UI_ACCENT, relief="flat", font=("Segoe UI", 8, "bold"), cursor="hand2")
        vars_dict["evaluation_reference_button"].pack(pady=(0, 4))

        membership_list_canvas = tk.Canvas(
            membership_right,
            bg="white",
            highlightthickness=0,
            bd=0
        )

        membership_list_scroll = UtilsTools.styled_scrollbar(
            membership_right,
            orient="vertical",
            command=membership_list_canvas.yview
        )

        membership_list_inner = tk.Frame(
            membership_list_canvas,
            bg="white"
        )

        membership_list_window = membership_list_canvas.create_window(
            (0, 0),
            window=membership_list_inner,
            anchor="nw"
        )

        membership_list_canvas.configure(
            yscrollcommand=membership_list_scroll.set
        )

        def _update_membership_list_scroll_region(event=None):
            try:
                membership_list_canvas.configure(
                    scrollregion=membership_list_canvas.bbox("all")
                )
            except Exception:
                pass

        def _update_membership_list_width(event=None):
            try:
                canvas_width = membership_list_canvas.winfo_width()
                membership_list_canvas.itemconfig(
                    membership_list_window,
                    width=max(canvas_width - 2, 1)
                )
            except Exception:
                pass

        membership_list_inner.bind(
            "<Configure>",
            _update_membership_list_scroll_region
        )

        membership_list_canvas.bind(
            "<Configure>",
            _update_membership_list_width
        )

        membership_list_canvas.pack(
            side="left",
            fill="both",
            expand=True,
            padx=(10, 0),
            pady=(0, 10)
        )

        membership_list_scroll.pack(
            side="right",
            fill="y",
            padx=(0, 8),
            pady=(0, 10)
        )

        self.app._register_vertical_mousewheel_canvas(membership_list_canvas)

        # Full-width horizontal graph toolbar, located beneath Results.
        # Membership stays alongside Results only for custom/sample colors.
        graph_buttons_card = self._create_color_evaluation_graph_buttons_card(
            results_block, vars_dict
        )
        graph_buttons_card.pack(fill="x", pady=(8, 0))
        right_side_column.grid_remove()

        # Show the results card directly, without a redundant "Results" title.
        result_card = tk.Frame(
            result_left,
            bg="#f7f7f7",
            bd=0,
            relief="flat",
            highlightthickness=2,
            highlightbackground="#bdbdbd",
            highlightcolor="#bdbdbd"
        )
        result_card.pack(fill="x", pady=(0, 2))

        result_header = tk.Frame(result_card, bg="#eeeeee")
        result_header.pack(fill="x")

        result_status_dot = tk.Canvas(
            result_header,
            width=18,
            height=18,
            bg="#eeeeee",
            highlightthickness=0,
            bd=0
        )
        result_status_dot.pack(side="left", padx=(10, 6), pady=8)

        result_status_dot_oval = result_status_dot.create_oval(
            3, 3, 15, 15,
            fill="#bdbdbd",
            outline="#bdbdbd"
        )

        result_title_label = tk.Label(
            result_header,
            textvariable=vars_dict["selected_result_var"],
            anchor="w",
            justify="left",
            bg="#eeeeee",
            font=("Sans", 10, "bold"),
            wraplength=300
        )
        result_title_label.pack(side="left", fill="x", expand=True, padx=(0, 6), pady=6)

        # Keep the metric value on the SAME line as the evaluation status.
        # It remains centered within the right half of the results header.
        result_value_label = tk.Label(
            result_header,
            textvariable=vars_dict["selected_detail_var"],
            anchor="center",
            justify="center",
            bg="#eeeeee",
            fg="#666666",
            font=("Segoe UI", 9, "bold"),
            wraplength=230,
        )
        result_value_label.pack(side="left", fill="x", expand=True, padx=(0, 6), pady=6)

        result_body = tk.Frame(result_card, bg="#f7f7f7")
        result_body.pack(fill="x", padx=10, pady=(6, 8))

        result_separator = tk.Frame(result_body, bg="#dddddd", height=1)
        result_separator.pack(fill="x", padx=4, pady=(0, 6))

        result_summary_row = tk.Frame(result_body, bg="#f7f7f7")
        result_summary_row.pack(fill="x")

        result_summary_icon = tk.Canvas(
            result_summary_row,
            width=20,
            height=20,
            bg="#f7f7f7",
            highlightthickness=0,
            bd=0
        )
        result_summary_icon.pack(side="left", padx=(0, 8), anchor="n")

        result_summary_icon_circle = result_summary_icon.create_oval(
            2, 2, 18, 18,
            outline="#666666",
            width=2
        )

        result_summary_icon_text = result_summary_icon.create_text(
            10, 10,
            text="!",
            fill="#666666",
            font=("Sans", 9, "bold")
        )

        result_text_container = tk.Frame(result_summary_row, bg="#f7f7f7")
        result_text_container.pack(side="left", fill="both", expand=True)

        result_summary_label = tk.Label(
            result_text_container,
            textvariable=vars_dict["selected_summary_var"],
            anchor="w",
            justify="left",
            bg="#f7f7f7",
            wraplength=300,
            font=("Consolas", 8)
        )
        result_summary_label.pack(anchor="w", fill="x")

        def _sync_membership_height_with_result(event=None):
            """
            Keep Membership Degree card visually aligned with the Results card.
            Graphs will then appear just below the Results height.
            """
            try:
                result_h = max(result_card.winfo_height(), 340)
                membership_right.configure(height=result_h)
            except Exception:
                pass

        result_card.bind("<Configure>", _sync_membership_height_with_result)
        result_card.after_idle(_sync_membership_height_with_result)

        # Color inspector
        def _create_color_evaluation_inspector_card(parent):
            """
            Create one Color Inspector card.

            Two instances are created:
            - one inside result_left for custom/sample mode;
            - one below results_columns for non-custom modes.
            Both use the same StringVars, so the text stays synchronized.
            """
            inspector_card = tk.Frame(
                parent,
                bg="#fafafa",
                bd=0,
                relief="flat",
                highlightthickness=1,
                highlightbackground="#bdbdbd",
                highlightcolor="#bdbdbd"
            )
            inspector_card.pack(fill="x", pady=(8, 0))

            inspector_header = tk.Frame(inspector_card, bg="#f3f3f3")
            inspector_header.pack(fill="x")

            tk.Label(
                inspector_header,
                textvariable=vars_dict["inspector_title_var"],
                font=("Sans", 9, "bold"),
                anchor="w",
                bg="#f3f3f3",
                padx=10,
                pady=5
            ).pack(side="left", fill="x", expand=True)

            tk.Label(
                inspector_header,
                textvariable=vars_dict["inspector_source_var"],
                font=("Sans", 8, "italic"),
                anchor="e",
                bg="#f3f3f3",
                fg="#666666",
                padx=10
            ).pack(side="right")

            inspector_body = tk.Frame(inspector_card, bg="#fafafa")
            inspector_body.pack(fill="x", padx=10, pady=(8, 8))

            inspector_preview = tk.Canvas(
                inspector_body,
                width=72,
                height=54,
                bg="#fafafa",
                highlightthickness=0,
                bd=0
            )
            inspector_preview.pack(side="left", padx=(0, 12), anchor="n")

            inspector_preview_rect = inspector_preview.create_rectangle(
                8, 8, 64, 46,
                fill="#d9d9d9",
                outline="#555555",
                width=1
            )

            inspector_values = tk.Frame(inspector_body, bg="#fafafa")
            inspector_values.pack(side="left", fill="x", expand=True)
            inspector_values.grid_columnconfigure(0, weight=1, uniform="inspector")
            inspector_values.grid_columnconfigure(1, weight=1, uniform="inspector")

            # First column: LAB, RGB, HEX. Second: CIELUV, LCh, CIE1931.
            # The field labels and values stay together when the inspector is
            # narrower (for example alongside the membership panel).
            for index, (label_text, variable) in enumerate((
                ("CIELAB", vars_dict["inspector_lab_var"]),
                ("RGB", vars_dict["inspector_rgb_var"]),
                ("HEX", vars_dict["inspector_hex_var"]),
                ("CIELUV", vars_dict["inspector_luv_var"]),
                ("LCh", vars_dict["inspector_lch_var"]),
                ("CIE1931", vars_dict["inspector_cie1931_var"]),
            )):
                column, row = divmod(index, 3)
                field = tk.Frame(inspector_values, bg="#fafafa")
                field.grid(row=row, column=column, sticky="new",
                           padx=(0, 9) if column == 0 else (9, 0), pady=(0, 3))
                tk.Label(
                    field, text=label_text, bg="#fafafa", fg="#333333",
                    anchor="w", font=("Segoe UI", 8, "bold"),
                ).pack(side="left", anchor="n", padx=(0, 5))
                value_label = tk.Label(
                    field, textvariable=variable, bg="#fafafa", fg="#222222",
                    anchor="w", justify="left", font=("Consolas", 8),
                    wraplength=230,
                )
                value_label.pack(side="left", fill="x", expand=True)

                def _fit_value_wrap(event, label=value_label, name=label_text):
                    # Keep both columns readable without expanding the inspector
                    # outside the narrow left panel in custom/sample mode.
                    label_width = (61 if name in ("CIELUV", "CIE1931") else 53)
                    label.configure(wraplength=max(72, event.width - label_width - 22))

                field.bind("<Configure>", _fit_value_wrap)

            return inspector_card, inspector_preview, inspector_preview_rect


        # Inspector used in custom/sample mode: left side, below Results.
        left_inspector_card, left_inspector_preview, left_inspector_preview_rect = (
            _create_color_evaluation_inspector_card(result_left)
        )

        # Inspector used in single / prototype-prototype mode:
        # full width below Results + Graphs.
        full_inspector_card, full_inspector_preview, full_inspector_preview_rect = (
            _create_color_evaluation_inspector_card(results_block)
        )

        # Initial mode is single color, so show the full-width inspector.
        left_inspector_card.pack_forget()

        vars_dict["left_inspector_card"] = left_inspector_card
        vars_dict["full_inspector_card"] = full_inspector_card

        vars_dict["inspector_preview"] = left_inspector_preview
        vars_dict["inspector_preview_rect"] = left_inspector_preview_rect

        vars_dict["inspector_previews"] = [
            (left_inspector_preview, left_inspector_preview_rect),
            (full_inspector_preview, full_inspector_preview_rect),
        ]

        # Store references
        vars_dict["analysis_result_refs"] = {
            "results_columns": results_columns,
            "result_left": result_left,

            "left_inspector_card": left_inspector_card,
            "full_inspector_card": full_inspector_card,

            "result_card": result_card,
            "result_header": result_header,
            "result_status_dot": result_status_dot,
            "result_status_dot_oval": result_status_dot_oval,
            "result_title_label": result_title_label,
            "result_body": result_body,
            "result_value_label": result_value_label,
            "value_in_header": True,
            "result_separator": result_separator,
            "result_summary_row": result_summary_row,
            "result_summary_icon": result_summary_icon,
            "result_summary_icon_circle": result_summary_icon_circle,
            "result_summary_icon_text": result_summary_icon_text,
            "result_summary_label": result_summary_label,

            "right_side_column": right_side_column,
            "membership_title_spacer": membership_title_spacer,
            "membership_right": membership_right,
            "membership_list_canvas": membership_list_canvas,
            "membership_list_inner": membership_list_inner,
            "graph_buttons_card": graph_buttons_card,
        }

        def _update_analysis_result_wrap(event=None):
            try:
                result_width = max(result_left.winfo_width() - 24, 200)
                title_wrap = max(result_width - 55, 140)
                summary_wrap = max(result_width - 70, 140)

                result_title_label.config(wraplength=max(120, title_wrap // 2))
                result_value_label.config(wraplength=max(120, result_width // 2 - 35))
                result_summary_label.config(wraplength=summary_wrap)
            except Exception:
                pass

        results_block.bind("<Configure>", _update_analysis_result_wrap)

        vars_dict["rows_canvas"] = rows_canvas
        vars_dict["rows_inner"] = rows_inner
        vars_dict["primary_swatch"] = primary_swatch
        vars_dict["primary_rect"] = primary_rect
        vars_dict["secondary_swatch"] = secondary_swatch
        vars_dict["secondary_rect"] = secondary_rect
        vars_dict["color_row_refs"] = {}
        vars_dict["primary_label"] = None
        vars_dict["secondary_label"] = None
        vars_dict["comparison_mode"] = False

        for widget in (
            refs["metric_family_combo"],
            refs["metric_combo"],
            refs["mode_combo"],
            refs["preset_combo"],
            refs["custom_type_combo"],
        ):
            widget.bind(
                "<<ComboboxSelected>>",
                lambda e: self._refresh_color_evaluation_threshold_ui(vars_dict, refs)
            )

        for widget in (
            refs["single_entry"],
            refs["lower_entry"],
            refs["upper_entry"],
        ):
            widget.bind(
                "<KeyRelease>",
                lambda e: self._refresh_color_evaluation_threshold_ui(vars_dict, refs)
            )

        self._refresh_color_evaluation_threshold_ui(vars_dict, refs)
        self._load_current_color_space_for_evaluation(vars_dict)
        self._update_color_evaluation_graph_buttons(vars_dict)

    def _set_color_evaluation_inspector_layout(self, vars_dict):
        """
        Switch Color Inspector placement depending on the current analysis mode.

        - Single color / prototype-prototype comparison:
            show full-width inspector below Results + Graphs.
        - Custom/sample color:
            show left inspector below Results, next to Membership/Graphs.
        """
        refs = vars_dict.get("analysis_result_refs", {})

        left_inspector_card = refs.get("left_inspector_card") or vars_dict.get("left_inspector_card")
        full_inspector_card = refs.get("full_inspector_card") or vars_dict.get("full_inspector_card")

        has_custom = any(
            vars_dict.get(prefix + "_mode") == "custom"
            and vars_dict.get(prefix + "_custom_lab") is not None
            for prefix in ("primary", "secondary")
        )

        try:
            if has_custom:
                if full_inspector_card is not None:
                    full_inspector_card.pack_forget()

                if (
                    left_inspector_card is not None
                    and not left_inspector_card.winfo_ismapped()
                ):
                    left_inspector_card.pack(fill="x", pady=(8, 0))

            else:
                if left_inspector_card is not None:
                    left_inspector_card.pack_forget()

                if (
                    full_inspector_card is not None
                    and not full_inspector_card.winfo_ismapped()
                ):
                    full_inspector_card.pack(fill="x", pady=(8, 0))

        except Exception:
            pass

    def _get_evaluation_proto_hex(self, vars_dict, label):
        """Return HEX color for a prototype in the Color Evaluation loaded space."""
        refs_map = vars_dict.get("color_row_refs", {})

        if label in refs_map:
            return refs_map[label].get("hex", "#cccccc")

        data_source = vars_dict.get("loaded_space_data") or {}

        try:
            color_value = data_source[label]

            lab = None
            if isinstance(color_value, dict):
                if "positive_prototype" in color_value:
                    lab = color_value["positive_prototype"]
                elif "Color" in color_value:
                    lab = color_value["Color"]

            if lab is None:
                return "#cccccc"

            lab_arr = np.array(lab, dtype=float)
            rgb = UtilsTools.lab_to_rgb(lab_arr)
            return self.app._safe_hex_from_rgb(rgb)

        except Exception:
            return "#cccccc"

    def _evaluation_membership_snapshot(self, vars_dict, sample_lab, sample=None):
        space = vars_dict.get("loaded_fuzzy_color_space")
        if space is None or sample_lab is None:
            vars_dict["evaluation_snapshot_key"] = None
            snapshot = membership_snapshot(None, sample_lab, self.app._get_color_evaluation_manager())
            vars_dict["evaluation_snapshot"] = snapshot
            return snapshot
        native = (sample is not None and sample.get("source") in ("image pixel", "custom RGB")
                  and space.color_space == "RGB")
        value = tuple(sample["rgb"] if native else sample_lab)
        mode = "RGB" if native else "LAB"
        key = (id(space), getattr(space, "tconorm", None), mode, value)
        if vars_dict.get("evaluation_snapshot_key") != key:
            vars_dict["evaluation_snapshot"] = membership_snapshot(space, sample_lab,
                self.app._get_color_evaluation_manager(), input_value=value, input_space=mode)
            vars_dict["evaluation_snapshot_key"] = key
        return vars_dict["evaluation_snapshot"]

    def _sync_color_evaluation_operator(self):
        v = getattr(self, "_color_evaluation_vars", None)
        if not v or "evaluation_operator_combo" not in v:
            return
        space = v.get("loaded_fuzzy_color_space")
        if space is not getattr(self.app, "fuzzy_color_space", None):
            return
        try:
            if not v["evaluation_operator_combo"].winfo_exists():
                return
            operator = getattr(space, "tconorm", None)
            previous = v.get("evaluation_operator_seen")
            v["evaluation_operator_seen"] = operator
            v["evaluation_operator_var"].set("Max" if operator == "max" else "Bounded Sum")
            if previous is not None and previous != operator:
                sample = v.get("evaluation_membership_sample")
                if sample:
                    self._update_color_evaluation_membership_panel(v, sample["lab"], sample=sample)
        except tk.TclError:
            pass

    def _change_color_evaluation_operator(self, v):
        space = v.get("loaded_fuzzy_color_space")
        if not getattr(space, "is_granular", False):
            return
        operator = "max" if v["evaluation_operator_var"].get() == "Max" else "bounded_sum"
        if space is getattr(self.app, "fuzzy_color_space", None):
            self.app._set_image_mapping_tconorm(operator)
        else:
            space.set_tconorm(operator)
        v["evaluation_operator_seen"] = space.tconorm
        v["evaluation_operator_var"].set("Max" if space.tconorm == "max" else "Bounded Sum")
        sample = v.get("evaluation_membership_sample")
        if sample:
            self._update_color_evaluation_membership_panel(v, sample["lab"], sample=sample)

    def _update_color_evaluation_membership_panel(self, vars_dict, sample_lab=None, sample=None):
        refs = vars_dict.get("analysis_result_refs", {})
        panel = refs.get("membership_right")
        if panel is None:
            return
        self._update_color_evaluation_graph_buttons(vars_dict)
        side = refs["right_side_column"]
        if sample_lab is None:
            panel.pack_forget(); side.grid_remove()
            vars_dict["evaluation_membership_sample"] = None
            return
        if sample is None:
            sample = {"lab": tuple(sample_lab)}
        vars_dict["evaluation_membership_sample"] = sample
        side.grid(row=0, column=1, sticky="new", padx=(8, 0))
        if not panel.winfo_manager():
            panel.pack(side="top", fill="x")
        panel.configure(height=max(refs["result_card"].winfo_height(), 340))
        space = vars_dict.get("loaded_fuzzy_color_space")
        op = getattr(space, "tconorm", None)
        vars_dict["evaluation_operator_seen"] = op
        vars_dict["evaluation_operator_var"].set("Max" if op == "max" else "Bounded Sum")
        vars_dict["evaluation_operator_combo"].configure(state="readonly" if op is not None else "disabled")
        snap = self._evaluation_membership_snapshot(vars_dict, sample_lab, sample)
        if vars_dict.get("evaluation_tree_space") is not space or "evaluation_membership_rows" not in vars_dict:
            vars_dict["evaluation_tree_space"] = space
            vars_dict["evaluation_expanded"] = set()
            for child in refs["membership_list_inner"].winfo_children(): child.destroy()
            vars_dict["evaluation_membership_rows"] = {}
            levels = ["Root categories"]
            if space is not None and getattr(space,"is_granular",False):
                previous = space.get_categories_at_level(0)
                for depth in range(1,len(space.get_all_category_labels())+1):
                    current = space.get_categories_at_level(depth)
                    if current == previous: break
                    levels.append(f"Level {depth}"); previous=current
            vars_dict["evaluation_level_var"].set(levels[0])
            vars_dict["evaluation_level_combo"].configure(values=levels,state="readonly" if len(levels)>1 else "disabled")
        winner = snap["winner_label"]
        vars_dict["evaluation_winner_var"].set(
            f"Highest Membership Degree: {winner} · μ = {snap['winner_mu']:.4f}" if winner is not None
            else "No positive membership" if space is not None else "No fuzzy membership data")
        vars_dict["evaluation_reference_button"].configure(state="normal" if winner is not None else "disabled")
        self._render_evaluation_membership_tree(vars_dict)

    def _explore_color_evaluation_level(self, v):
        space = v.get("loaded_fuzzy_color_space")
        if space is None: return
        value = v["evaluation_level_var"].get()
        depth = int(value.split()[-1]) if value.startswith("Level ") else 0
        expanded = set()
        stack = [(('category',label),) for label in space.get_root_categories()]
        while stack:
            path=stack.pop()
            if len(path)>depth: continue
            children=space.get_category_children(path[-1][1])
            if children:
                expanded.add(path)
                stack.extend(path+(r,) for r in children if r[0]=='category')
        v["evaluation_expanded"]=expanded
        self._render_evaluation_membership_tree(v)

    @staticmethod
    def _evaluation_tree_guides(canvas, depth, continuations, more, expanded, expandable, height=28):
        canvas.delete("all")
        depth = min(depth, 12)
        x = depth*13+8; mid = height//2
        # At indentation i, the vertical trunk belongs to the parent of
        # the next ancestor. Continue it when that next ancestor has a
        # following sibling, not when the root itself has a sibling.
        ancestors = continuations[-depth:] if depth else ()
        for index in range(depth):
            prev = index*13+8
            if index == depth-1:
                canvas.create_line(prev, 0, prev, height if more else mid, fill="#c9bfda")
                canvas.create_line(prev, mid, x-4 if expandable else canvas.winfo_reqwidth(), mid, fill="#c9bfda")
            elif index+1 < len(ancestors) and ancestors[index+1]:
                canvas.create_line(prev, 0, prev, height, fill="#c9bfda")
        if expanded:
            canvas.create_line(x, mid+5, x, height, fill="#c9bfda")
        if expandable:
            canvas.create_text(x, mid, text="▾" if expanded else "▸", fill=UtilsTools.UI_ACCENT,
                               font=("Segoe UI", 9, "bold"))

    def _render_evaluation_membership_tree(self, v):
        refs = v.get("analysis_result_refs", {})
        inner = refs.get("membership_list_inner")
        if inner is None: return
        space = v.get("loaded_fuzzy_color_space")
        snap = v.get("evaluation_snapshot") or {}
        controls = v.setdefault("evaluation_membership_rows",{})
        if space is None or not snap.get("categories"):
            for row in controls.values(): row["row"].pack_forget()
            return
        expanded = v.setdefault("evaluation_expanded", set())
        zeros = v["evaluation_show_zeros"].get()
        def degree(ref):
            kind, label = ref
            return snap["categories"][label]["degree"] if kind == "category" else snap["granules"][label]
        def ordered(refs):
            return sorted((r for r in refs if zeros or degree(r)>0),
                          key=lambda r: (-degree(r), r != ("category", snap["winner_label"])))
        def toggle(path):
            current_expanded=v.setdefault("evaluation_expanded",set())
            if path in current_expanded: current_expanded.remove(path)
            else: current_expanded.add(path)
            self._render_evaluation_membership_tree(v)
        roots = ordered(("category", name) for name in space.get_root_categories())
        stack = [((r,), (), False) for r in reversed(roots)]
        desired=[]
        while stack:
            path, guides, more = stack.pop()
            kind, label = path[-1]; cat = kind == "category"
            children = ordered(space.get_category_children(label)) if cat and getattr(space,"is_granular",False) else []
            opened = path in expanded and bool(children)
            ctrl=controls.get(path)
            if ctrl is None:
                row = tk.Frame(inner, bg="white", height=28); row.pack_propagate(False)
                gutter = tk.Canvas(row, width=min(len(path)-1,12)*13+19, height=28, bg="white", bd=0, highlightthickness=0)
                gutter.pack(side="left", fill="y")
                if cat: gutter.bind("<Button-1>", lambda e,p=path: toggle(p))
                granule = space.get_descendant_granules(label)[0].label if cat else label
                tk.Label(row, bg=self._get_evaluation_proto_hex(v,granule), width=2, relief="solid", bd=1).pack(side="left",padx=(1,5))
                value=tk.Label(row,bg="white",font=("Segoe UI",8),anchor="e"); value.pack(side="right",padx=3)
                bar=ttk.Progressbar(row,length=45,maximum=1); bar.pack(side="right",padx=2)
                name = tk.Label(row,text=label,bg="white",font=("Segoe UI",9,"bold" if cat else "normal"),anchor="w",cursor="hand2")
                name.pack(side="left",fill="x",expand=True)
                # Clicking a category uses its closest real granule. Clicking a
                # granule uses exactly that site. The arrow only navigates.
                name.bind("<Button-1>", lambda e,k=kind,n=label:self._use_evaluation_reference(v,k,n))
                ctrl=controls[path]={"row":row,"gutter":gutter,"value":value,"bar":bar,"name":name,"guides":None,"degree":None}
            current=degree(path[-1])
            if ctrl["degree"]!=current:
                ctrl["value"].configure(text=f"μ = {current:.4f}");ctrl["bar"].configure(value=current);ctrl["degree"]=current
            ctrl["name"].configure(fg=UtilsTools.UI_ACCENT if cat and label==snap["winner_label"] else "#243043")
            signature=(guides,more,opened,bool(children))
            if signature!=ctrl["guides"]:
                self._evaluation_tree_guides(ctrl["gutter"],len(path)-1,guides,more,opened,bool(children));ctrl["guides"]=signature
            desired.append(ctrl["row"])
            if opened:
                stack.extend((path+(child,),guides+(more,),idx<len(children)-1)
                             for idx,child in reversed(list(enumerate(children))))
        self._pack_evaluation_rows(inner, desired)

    @staticmethod
    def _pack_evaluation_rows(parent, desired, **options):
        """Update only rows whose position or visibility actually changes."""
        wanted=set(desired)
        for row in parent.pack_slaves():
            if row not in wanted: row.pack_forget()
        packed=parent.pack_slaves()
        for index,row in enumerate(desired):
            if index<len(packed) and packed[index] is row: continue
            if row in packed: packed.remove(row)
            kw={"fill":"x",**options}
            if hasattr(row, "_evaluation_root_gap"):
                kw["pady"] = row._evaluation_root_gap
            if index<len(packed): kw["before"]=packed[index]
            row.pack(**kw); packed.insert(index,row)

    def _use_evaluation_highest_degree(self, v):
        sample=v.get("evaluation_membership_sample")
        if sample is None: return
        snap=self._evaluation_membership_snapshot(v,sample["lab"],sample)
        if snap["winner_label"] is not None:
            self._use_evaluation_reference(v,"category",snap["winner_label"])

    def _use_evaluation_reference(self, v, kind, name):
        sample = v.get("evaluation_membership_sample")
        space = v.get("loaded_fuzzy_color_space")
        if not sample or space is None: return
        if kind=="category":
            candidates = [(p.label, space.lab_from_model(p.positive)) for p in space.get_descendant_granules(name)]
            label = nearest_granule(self.app._get_color_evaluation_manager(), candidates, sample["lab"],
                                    self.app.threshold_settings.get("metric","CIEDE2000"))
        else:
            label=name
        ref = v.get("color_row_refs",{}).get(label)
        if not ref: return
        target = "A" if v.get("evaluation_membership_side", "B") == "B" else "B"
        # External sample is preserved; only the other comparison side is assigned.
        self._set_color_evaluation_side_sample(v,target,self._evaluation_sample_snapshot(label,ref["lab"],ref["rgb"],ref["hex"],"granule",ref.get("category"),label))
        paths=[item["path"] for item in v.get("evaluation_explorer_rows",[]) if item["path"][-1]==("granule",label)]
        if paths:
            path=next((p for p in paths if ("category",name) in p),paths[0])
            v["evaluation_explorer_open"].update(path[:n] for n in range(1,len(path)))
            self._filter_color_evaluation_entries(v)
        self._refresh_color_evaluation_comparison(v)
        self._highlight_color_evaluation_rows(v)

    def _load_color_space_for_evaluation_from_file(self, filename):
        """
        Load a color space file for evaluation purposes without replacing
        the application's main active color space.
        """
        data = self.app.fuzzy_manager.load_color_file(filename)

        result = {
            "file_path": filename,
            "space_name": os.path.splitext(os.path.basename(filename))[0],
            "type": data.get("type"),
            "color_data": data.get("color_data", {}),
            "fuzzy_color_space": None,
            "cores": None,
            "supports": None,
            "prototypes": None,
        }

        if data.get("type") == "fcs":
            fuzzy_cs = data.get("fuzzy_color_space")
            if fuzzy_cs is not None:
                try:
                    fuzzy_cs.precompute_pack()
                except Exception:
                    pass

                result["fuzzy_color_space"] = fuzzy_cs
                result["cores"] = getattr(fuzzy_cs, "cores", None)
                result["supports"] = getattr(fuzzy_cs, "supports", None)
                result["prototypes"] = getattr(fuzzy_cs, "prototypes", None) # Used as 0.5-cut in plots

        return result

    def _get_current_color_space_for_evaluation(self):
        """
        Return the currently active application color space in a format
        suitable for the Color Space Evaluation window.
        """
        data_source = getattr(self.app, "color_data", None)
        if not data_source:
            data_source = getattr(self.app, "edit_color_data", None)

        if not data_source:
            return None

        fuzzy_cs = getattr(self.app, "fuzzy_color_space", None)

        return {
            "file_path": getattr(self.app, "file_path", None),
            "space_name": getattr(self.app, "file_base_name", "Current loaded color space"),
            "type": "fcs" if fuzzy_cs is not None else "cns",
            "color_data": data_source,
            "fuzzy_color_space": fuzzy_cs,
            "cores": getattr(self.app, "cores", None),
            "supports": getattr(self.app, "supports", None),
            "prototypes": getattr(self.app, "prototypes", None),
        }

    def _create_color_evaluation_vars(self):
        """Create and return all Tk variables used by the Color Evaluation window."""
        vars_dict = {
            "space_name_var": tk.StringVar(value="None"),
            "space_count_var": tk.StringVar(value="0"),
            "space_items_label_var": tk.StringVar(value="Prototypes:"),
            "color_search_var": tk.StringVar(value=""),
            "category_rows": [],
            "category_open": {},
            "color_row_order": [],
            "color_display_mode_var": tk.StringVar(value="CIELAB"),

            "analysis_mode_var": tk.StringVar(value="Select a color from the list."),
            "primary_name_var": tk.StringVar(value="None"),
            "secondary_name_var": tk.StringVar(value="None"),
            "primary_meta_var": tk.StringVar(value=""),
            "secondary_meta_var": tk.StringVar(value=""),
            "primary_lab_var": tk.StringVar(value=""),
            "secondary_lab_var": tk.StringVar(value=""),

            "selected_result_var": tk.StringVar(value="Select a prototype from the list."),
            "selected_detail_var": tk.StringVar(value=""),
            "selected_summary_var": tk.StringVar(value=""),

            # Color inspector
            "inspector_title_var": tk.StringVar(value="Color Inspector"),
            "inspector_source_var": tk.StringVar(value="Source: -"),

            "inspector_rgb_var": tk.StringVar(value="-"),
            "inspector_lab_var": tk.StringVar(value="-"),
            "inspector_hex_var": tk.StringVar(value="-"),
            "inspector_luv_var": tk.StringVar(value="-"),
            "inspector_lch_var": tk.StringVar(value="-"),
            "inspector_cie1931_var": tk.StringVar(value="-"),

            "loaded_space_data": None,
            "loaded_space_name": "",
            "loaded_space_type": None,
            "loaded_fuzzy_color_space": None,
            "loaded_cores": None,
            "loaded_supports": None,
            "loaded_prototypes": None,
            "loaded_file_path": None,

            # Comparison state
            "secondary_mode": None,          # None | "row" | "custom"
            "secondary_custom_lab": None,
            "secondary_custom_rgb": None,
            "secondary_custom_hex": None,
            "secondary_custom_name": "Custom Color",

            "analysis_view_mode": "comparison",   # "comparison" | "closest"
            "primary_mode": "row",             # "row" | "custom"
            "primary_custom_lab": None,
            "primary_custom_rgb": None,
            "primary_custom_hex": None,
            "primary_custom_name": "Sample",
            "primary_custom_source": "custom",
            "secondary_custom_source": "custom",
            "quick_samples": [],
            "quick_samples_sequence": 0,
            "quick_samples_target_var": tk.StringVar(value="B"),
            "quick_samples_expanded": True,

            # Last Threshold Analysis action
            "active_analysis_action": None,
            "analysis_action_buttons": {},

            # Closest ranking cache
            "closest_ranking": [],
            "closest_best": None,
            "closest_metric": None,
        }

        return self.app._merge_threshold_vars(vars_dict)

    def _set_color_evaluation_active_action(self, vars_dict, action_key):
        """
        Visually mark the last pressed button in the Threshold Analysis action area.
        """
        vars_dict["active_analysis_action"] = action_key

        buttons = vars_dict.get("analysis_action_buttons", {})

        # Clear is a one-shot action; only persistent analysis modes are highlighted.
        for key, button in buttons.items():
            try:
                is_active = key == action_key and key != "clear"
                button.configure(
                    bg=UtilsTools.UI_ACCENT_SOFT if is_active else "#f8fafc",
                    fg=UtilsTools.UI_ACCENT_DARK if is_active else "#1f2937",
                    activebackground=UtilsTools.UI_ACCENT_HOVER if is_active else UtilsTools.UI_ACCENT_SOFT,
                    activeforeground=UtilsTools.UI_ACCENT_DARK if is_active else UtilsTools.UI_ACCENT,
                    relief="solid",
                    bd=2 if is_active else 1,
                    highlightthickness=0,
                )
            except Exception:
                pass

    def _refresh_color_evaluation_threshold_ui(self, vars_dict, refs):
        """
        Refresh threshold controls, validate inputs, update summary,
        and preserve the active analysis view.
        """
        self.app._refresh_shared_threshold_ui(
            vars_dict=vars_dict,
            refs=refs,
            proto_lab=None,
            sample_lab=None
        )

        # Clear cached ranking because metric or thresholds may have changed.
        vars_dict["closest_ranking"] = []
        vars_dict["closest_best"] = None
        vars_dict["closest_metric"] = None

        if vars_dict.get("analysis_view_mode") == "closest":
            self._show_color_evaluation_closest_prototypes(vars_dict)
        else:
            self._refresh_color_evaluation_comparison(vars_dict)

    def _get_color_evaluation_threshold_description(self):
        """
        Return a compact textual description of the active threshold settings.
        """
        self.app._ensure_threshold_settings()
        manager = self.app._get_color_evaluation_manager()

        return manager.get_threshold_description(
            threshold_settings=self.app.threshold_settings,
            include_metric_description=True
        )

    def _load_current_color_space_for_evaluation(self, vars_dict):
        """Load the currently active color space into the evaluation window."""
        loaded = self._get_current_color_space_for_evaluation()

        if not loaded or not loaded.get("color_data"):
            vars_dict["space_name_var"].set("None")
            vars_dict["space_count_var"].set("0")

            vars_dict["loaded_space_data"] = None
            vars_dict["loaded_space_name"] = ""
            vars_dict["loaded_space_type"] = None
            vars_dict["loaded_fuzzy_color_space"] = None
            vars_dict["loaded_cores"] = None
            vars_dict["loaded_supports"] = None
            vars_dict["loaded_prototypes"] = None
            vars_dict["loaded_file_path"] = None

            self._render_color_evaluation_cards(vars_dict, {})
            return

        vars_dict["loaded_space_data"] = loaded["color_data"]
        vars_dict["loaded_space_name"] = loaded["space_name"]
        vars_dict["loaded_space_type"] = loaded["type"]
        vars_dict["loaded_fuzzy_color_space"] = loaded["fuzzy_color_space"]
        vars_dict["loaded_cores"] = loaded["cores"]
        vars_dict["loaded_supports"] = loaded["supports"]
        vars_dict["loaded_prototypes"] = loaded["prototypes"]
        vars_dict["loaded_file_path"] = loaded["file_path"]

        self._update_color_evaluation_space_summary(vars_dict)
        self._render_color_evaluation_cards(vars_dict, loaded["color_data"])

    def _load_external_color_space_for_evaluation(self, vars_dict):
        """Load another color space from disk for inspection/evaluation only."""
        try:
            if self._color_evaluation_window is not None and self._color_evaluation_window.winfo_exists():
                self._color_evaluation_window.lift()
                self._color_evaluation_window.focus_force()
        except Exception:
            pass

        filename = UtilsTools.prompt_file_selection(
            "fuzzy_color_spaces/",
            parent=self._color_evaluation_window
        )
        if not filename:
            return

        try:
            loaded = self._load_color_space_for_evaluation_from_file(filename)
        except Exception as exc:
            self.app.custom_warning(
                "Color Space Could Not Be Loaded",
                f"The selected file could not be read:\n{exc}",
                parent=getattr(self, "_color_evaluation_window", None)
            )
            return

        if not loaded or not isinstance(loaded.get("color_data"), dict):
            self.app.custom_warning(
                "Invalid Color Space",
                "The selected file contains no valid color-space data.",
                parent=getattr(self, "_color_evaluation_window", None)
            )
            return

        vars_dict["loaded_space_data"] = loaded["color_data"]
        vars_dict["loaded_space_name"] = loaded["space_name"]
        vars_dict["loaded_space_type"] = loaded["type"]
        vars_dict["loaded_fuzzy_color_space"] = loaded["fuzzy_color_space"]
        vars_dict["loaded_cores"] = loaded["cores"]
        vars_dict["loaded_supports"] = loaded["supports"]
        vars_dict["loaded_prototypes"] = loaded["prototypes"]
        vars_dict["loaded_file_path"] = loaded["file_path"]

        self._update_color_evaluation_space_summary(vars_dict)
        self._render_color_evaluation_cards(vars_dict, loaded["color_data"])

    def _calculate_evaluation_memberships(self, vars_dict, sample_lab, sample=None):
        return self._evaluation_membership_snapshot(vars_dict, sample_lab, sample)["memberships"]

    def _update_color_evaluation_space_summary(self, vars_dict):
        data_source = vars_dict.get("loaded_space_data") or {}
        space_name = vars_dict.get("loaded_space_name", "Unnamed color space")
        valid_rows = self._extract_color_space_rows(data_source)
        vars_dict["space_name_var"].set(space_name)
        space = vars_dict.get("loaded_fuzzy_color_space")
        if isinstance(space, GranularFuzzyColorSpace):
            n_granules = sum(len(c.prototypes) for c in space.categories)
            vars_dict["space_items_label_var"].set("")
            n_categories = len(space.get_all_category_labels())
            model = "CIELAB" if space.color_space == "LAB" else space.color_space
            vars_dict["space_count_var"].set(
                f"{n_categories} categor{'y' if n_categories == 1 else 'ies'} · "
                f"{n_granules} granule{'s' if n_granules != 1 else ''} · {model} model")
        else:
            vars_dict["space_items_label_var"].set("Prototypes:")
            vars_dict["space_count_var"].set(str(len(valid_rows)))
        closest_button = vars_dict.get("closest_action_button")
        if closest_button is not None:
            closest_button.configure(text=("Find closest category" if
                isinstance(space, GranularFuzzyColorSpace) else "Find closest prototype"))

    def _extract_color_space_rows(self, data_source):
        """
        Compatibility wrapper. Logic lives in ColorEvaluationManager.
        """
        manager = self.app._get_color_evaluation_manager()
        return manager.extract_color_space_rows(data_source)

    def _set_custom_color_as_evaluation_comparison(self, vars_dict, sample_lab,
                                                    sample_rgb, sample_hex,
                                                    name="Custom Color", source="custom"):
        """Compatibility entry point: a new external color is assigned to B."""
        return self._use_color_evaluation_external_sample(
            vars_dict, name=name, lab=sample_lab, rgb=sample_rgb,
            hex_color=sample_hex, source=source, target="B")

    def _refresh_color_evaluation_table_display_mode(self, vars_dict):
        """
        Refresh the value column of the Color Evaluation table according to
        the selected color space display mode.
        """
        try:
            display_mode = vars_dict["color_display_mode_var"].get()
        except Exception:
            display_mode = "CIELAB"

        for label, refs in list(vars_dict.get("color_row_refs", {}).items()) + vars_dict.get("evaluation_alias_rows", []):
            value_label = refs.get("value_label")
            lab = refs.get("lab")

            if value_label is None or lab is None:
                continue

            try:
                value_label.configure(text=self._format_color_evaluation_value(
                    lab, display_mode, rgb=refs.get("rgb")))
            except Exception:
                value_label.configure(text="-")

        # The two comparison cards use the same display mode as Explore Colors.
        # Updating only the captions avoids recalculating memberships or ΔE.
        self._refresh_color_evaluation_preview_values(vars_dict)

    def _refresh_color_evaluation_preview_values(self, vars_dict):
        """Update both preview captions without changing their source LAB data."""
        mode = vars_dict["color_display_mode_var"].get()
        for side, prefix in (("A", "primary"), ("B", "secondary")):
            sample = self._get_color_evaluation_side_sample(vars_dict, side)
            vars_dict[prefix + "_lab_var"].set(
                self._format_color_evaluation_value(
                    sample["lab"], mode, rgb=sample["rgb"],
                    hex_color=sample["hex"], card=True)
                if sample else ""
            )

    def _rotate_color_evaluation_table_display_mode(self, vars_dict, direction=1):
        """Cycle the displayed color coordinates forward or backward."""
        spaces = UtilsTools.get_supported_color_value_spaces()
        if not spaces:
            return

        try:
            current = UtilsTools.normalize_color_value_space(
                vars_dict["color_display_mode_var"].get()
            )
        except Exception:
            current = "CIELAB"

        if current not in spaces:
            next_space = spaces[0] if direction >= 0 else spaces[-1]
        else:
            next_space = spaces[(spaces.index(current) + (1 if direction >= 0 else -1))
                                % len(spaces)]

        vars_dict["color_display_mode_var"].set(next_space)
        self._refresh_color_evaluation_table_display_mode(vars_dict)

    @staticmethod
    def _color_evaluation_actual_entries(data_source, fuzzy_space):
        """Return selectable real LAB sites, grouped by their model categories.

        Never evaluate a granular category via its legacy representative: a
        category is a fuzzy union and does not have a unique comparison LAB.
        """
        if isinstance(fuzzy_space, GranularFuzzyColorSpace):
            groups = []
            for category in fuzzy_space.categories:
                entries = []
                for proto in category.prototypes:
                    try:
                        lab = np.asarray(fuzzy_space.lab_from_model(proto.positive),
                                         dtype=float).reshape(3)
                        if np.isfinite(lab).all():
                            entries.append((proto.label, lab))
                    except (TypeError, ValueError):
                        continue
                if entries:
                    groups.append((category.label, entries))
            return groups
        groups = []
        if isinstance(data_source, dict):
            for label, value in data_source.items():
                if not isinstance(value, dict):
                    continue
                lab = value.get("positive_prototype", value.get("Color"))
                try:
                    lab = np.asarray(lab, dtype=float).reshape(3)
                    if np.isfinite(lab).all():
                        groups.append((label, [(label, lab)]))
                except (TypeError, ValueError):
                    continue
        return groups

    @staticmethod
    def _color_evaluation_lab_caption(lab):
        try:
            return f"LAB: {float(lab[0]):.2f}, {float(lab[1]):.2f}, {float(lab[2]):.2f}"
        except (TypeError, IndexError, ValueError):
            return ""

    @staticmethod
    def _format_color_evaluation_value(lab, display_mode, *, rgb=None,
                                       hex_color=None, card=False):
        """Format color coordinates consistently in the explorer and previews.

        In particular, keep the RGB of an actual sampled pixel rather than
        converting its stored, full-precision LAB values back into RGB.
        """
        try:
            mode = UtilsTools.normalize_color_value_space(display_mode)
            if mode == "RGB":
                values = (UtilsTools.safe_rgb_tuple(rgb) if rgb is not None else
                          UtilsTools.lab_to_color_value(lab, "RGB"))
                r, g, b = (int(component) for component in values)
                text = f"R={r}, G={g}, B={b}"
                return f"RGB: {text}" if card else text
            if mode == "CIELAB" and card:
                return ColorEvaluationWindow._color_evaluation_lab_caption(lab)
            if mode == "HEX" and hex_color and card:
                return f"HEX: {str(hex_color).upper()}"
            text = UtilsTools.format_lab_color_value(lab, mode)
            if not card:
                return text
            prefix = {"HEX": "HEX", "CIELUV": "LUV", "LCh": "LCh",
                      "CIE1931": "CIE1931"}.get(mode, mode)
            return f"{prefix}: {text}"
        except (TypeError, ValueError, IndexError, OverflowError):
            return ""

    def _highlight_color_evaluation_rows(self, vars_dict):
        """Refresh selection colors in-place without rebuilding entry widgets."""
        primary = vars_dict.get("primary_label")
        secondary = vars_dict.get("secondary_label") if vars_dict.get("secondary_mode") == "row" else None
        for info in vars_dict.get("category_rows", []):
            if info.get("single"):
                selected = info["labels"][0] in (primary, secondary)
                info["header"].configure(bg="#e8f0ff" if selected else "#f1f3f8")
                for child in info["header"].winfo_children():
                    if not isinstance(child, tk.Canvas):
                        try:
                            child.configure(bg="#e8f0ff" if selected else "#f1f3f8")
                            for subchild in child.winfo_children():
                                subchild.configure(bg="#e8f0ff" if selected else "#f1f3f8")
                        except (tk.TclError, ValueError):
                            pass
        for key, refs in list(vars_dict.get("color_row_refs", {}).items()) + vars_dict.get("evaluation_alias_rows", []):
            bg = ("#e9e1ff" if key == primary == secondary else
                  "#e8f0ff" if key == primary else
                  "#f1e8ff" if key == secondary else "white")
            refs["frame"].configure(bg=bg, highlightbackground=(
                UtilsTools.UI_ACCENT if key in (primary, secondary) else "#e5e7eb"))
            refs["content"].configure(bg=bg)
            for widget in refs["widgets"]:
                if widget is refs.get("swatch"):
                    continue
                try:
                    widget.configure(bg=bg)
                except (tk.TclError, ValueError):
                    pass

    def _render_color_evaluation_cards(self, vars_dict, data_source):
        """Build the searchable atomic/granular color explorer.

        Category headings only expand/collapse. A selectable row always refers
        to a real prototype/granule and supports comparisons within a category.
        """
        rows_inner = vars_dict["rows_inner"]
        for child in rows_inner.winfo_children():
            child.destroy()
        vars_dict["color_row_refs"] = {}
        vars_dict["category_rows"] = []
        vars_dict["evaluation_explorer_rows"] = []
        vars_dict["evaluation_alias_rows"] = []
        vars_dict["color_row_order"] = []
        vars_dict["category_open"] = {}
        vars_dict["evaluation_snapshot_key"] = None
        vars_dict["evaluation_snapshot"] = None
        vars_dict["closest_ranking"] = []
        vars_dict["closest_best"] = None
        vars_dict["closest_metric"] = None
        vars_dict["primary_label"] = None
        vars_dict["primary_mode"] = "row"
        vars_dict["primary_custom_lab"] = None
        vars_dict["primary_custom_rgb"] = None
        vars_dict["primary_custom_hex"] = None
        vars_dict["secondary_label"] = None
        vars_dict["comparison_mode"] = False
        vars_dict["analysis_view_mode"] = "comparison"
        vars_dict["secondary_mode"] = None
        vars_dict["secondary_custom_lab"] = None
        vars_dict["secondary_custom_rgb"] = None
        vars_dict["secondary_custom_hex"] = None
        vars_dict["secondary_custom_name"] = "Custom Color"
        self._set_color_evaluation_active_action(vars_dict, None)
        vars_dict["analysis_mode_var"].set("Select a color from the list.")

        space = vars_dict.get("loaded_fuzzy_color_space")
        is_granular = isinstance(space, GranularFuzzyColorSpace)
        groups = self._color_evaluation_actual_entries(data_source, space)
        if not groups:
            tk.Label(rows_inner, text="No color space data available.", bg="white",
                     fg="#6b7280", font=("Segoe UI", 10)).pack(padx=12, pady=16)
            self._clear_color_evaluation_analysis(vars_dict)
            return

        def _select(label):
            if label not in vars_dict["color_row_refs"]:
                return
            if vars_dict.get("comparison_mode"):
                primary = vars_dict.get("primary_label")
                if primary is None and vars_dict.get("primary_mode") != "custom":
                    vars_dict["primary_label"] = label
                    vars_dict["secondary_label"] = None
                    vars_dict["secondary_mode"] = None
                    vars_dict["analysis_mode_var"].set("Choose a reference color to compare.")
                elif label == primary:
                    vars_dict["analysis_mode_var"].set(
                        "Choose a different color or granule for the reference.")
                    return
                else:
                    vars_dict["secondary_label"] = label
                    vars_dict["secondary_mode"] = "row"
                    vars_dict["secondary_custom_lab"] = None
                    vars_dict["secondary_custom_rgb"] = None
                    vars_dict["secondary_custom_hex"] = None
                    vars_dict["analysis_mode_var"].set(
                        "Comparison active. Select another reference or clear comparison.")
            else:
                vars_dict["primary_label"] = label
                vars_dict["primary_mode"] = "row"
                vars_dict["primary_custom_lab"] = None
                vars_dict["secondary_label"] = None
                if vars_dict.get("secondary_mode") == "custom" and vars_dict.get("secondary_custom_lab") is not None:
                    vars_dict["analysis_mode_var"].set(
                        "Custom comparison active. Select another color to compare.")
                else:
                    vars_dict["analysis_mode_var"].set("Single color selected.")
            refs = vars_dict["color_row_refs"][label]
            self._add_color_evaluation_quick_sample(
                vars_dict, name=label, lab=refs["lab"], rgb=refs["rgb"],
                hex_color=refs["hex"], source="granule" if refs.get("category") else "prototype",
                category=refs.get("category"), row_label=label)
            self._refresh_color_evaluation_comparison(vars_dict)
            self._highlight_color_evaluation_rows(vars_dict)

        # A two-line leaf needs its measured text height at the current DPI.
        from tkinter import font as tkfont
        row_height = max(40, tkfont.Font(root=rows_inner, font=("Segoe UI", 10)).metrics("linespace")
                         + tkfont.Font(root=rows_inner, font=("Consolas", 8)).metrics("linespace") + 8)
        swatch_size = 24

        def _make_entry(parent, label, lab, category=None, path=None, guides=(), more=False):
            try:
                rgb = UtilsTools.lab_to_rgb(lab)
                rgb = tuple(max(0, min(255, int(round(v)))) for v in rgb)
            except Exception:
                rgb = (200, 200, 200)
            if is_granular and space.color_space == "RGB":
                rgb = native_rgb[label]
            hex_color = self.app._safe_hex_from_rgb(rgb)
            row = tk.Frame(parent, bg="white", highlightthickness=0 if path else 1,
                           highlightbackground="#e5e7eb", cursor="hand2", height=row_height if path else 1)
            if path:
                row.pack_propagate(False)
            else:
                row.pack(fill="x", padx=8, pady=3)
            content = tk.Frame(row, bg="white", cursor="hand2")
            content.pack(fill="both" if path else "x", expand=bool(path), padx=0 if path else 8, pady=0 if path else 6)
            gutter = None
            if path:
                gutter = tk.Canvas(content,width=min(len(path)-1,12)*13+19,height=row_height,bg="white",bd=0,highlightthickness=0)
                gutter.pack(side="left",fill="y")
            swatch = tk.Canvas(content, width=swatch_size+8, height=row_height, bg="white",
                               highlightthickness=0, bd=0, cursor="hand2")
            swatch.pack(side="left", padx=(0, 7))
            top = (row_height-swatch_size)//2
            swatch.create_rectangle(4, top, 4+swatch_size, top+swatch_size, fill=hex_color,
                                     outline="#9ca3af", width=1)
            details = tk.Frame(content, bg="white", cursor="hand2")
            details.pack(side="left", fill="both", expand=True)
            name = tk.Label(details, text=label, bg="white", fg="#243043",
                            anchor="w", font=("Segoe UI", 10, "normal" if path else "bold"),
                            cursor="hand2")
            name.pack(anchor="w", pady=(3, 0))
            if category and not path:
                subtitle = tk.Label(details, text=f"Granule · {category}",
                                    bg="white", fg="#697386", anchor="w",
                                    font=("Segoe UI", 8), cursor="hand2")
                subtitle.pack(anchor="w", pady=(1, 0))
            else:
                subtitle = None
            value = tk.Label(details, text=self._format_color_evaluation_value(
                lab, vars_dict["color_display_mode_var"].get(), rgb=rgb),
                bg="white", fg="#526074", anchor="w", justify="left",
                wraplength=280, font=("Consolas", 8), cursor="hand2")
            value.pack(anchor="w", fill="x", pady=(1, 0))
            widgets = [content, name, value, details]
            if subtitle is not None:
                widgets.append(subtitle)
            entry_refs = {
                "frame": row, "content": content, "widgets": widgets,
                "lab": lab, "rgb": rgb, "hex": hex_color,
                "swatch": swatch, "value_label": value, "category": category,
                "gutter": gutter,
            }
            row._evaluation_gutter = gutter
            if label not in vars_dict["color_row_refs"]:
                vars_dict["color_row_refs"][label] = entry_refs
                vars_dict["color_row_order"].append(label)
            else:
                vars_dict["evaluation_alias_rows"].append((label,entry_refs))
            for widget in (row, content, swatch, details, name, value):
                widget.bind("<Button-1>", lambda e, key=label: _select(key))
            if subtitle is not None:
                subtitle.bind("<Button-1>", lambda e, key=label: _select(key))
            return row

        if not is_granular:
            for category, entries in groups:
                _make_entry(rows_inner, entries[0][0], entries[0][1])
        else:
            real = {p.label:(cat.label,space.lab_from_model(p.positive)) for cat in space.categories for p in cat.prototypes}
            native_rgb = {p.label:tuple(int(round(x)) for x in p.positive) for p in space.get_all_prototypes()} if space.color_space == "RGB" else {}
            items = vars_dict["evaluation_explorer_rows"]
            opened = vars_dict["evaluation_explorer_open"] = set()
            roots = [("category",label) for label in space.get_root_categories()]
            stack = [((r,),(),False) for r in reversed(roots)]
            def toggle(path):
                if path in opened: opened.remove(path)
                else: opened.add(path)
                self._filter_color_evaluation_entries(vars_dict)
            while stack:
                path,guides,more = stack.pop(); kind,label = path[-1]
                if kind == "granule":
                    category,lab = real[label]
                    row = _make_entry(rows_inner,label,lab,category,path,guides,more)
                    items.append({"path":path,"frame":row,"gutter":row._evaluation_gutter,
                                  "height":row_height,"guides":guides,"more":more})
                    if len(vars_dict["color_row_order"]) == 1: opened.update(path[:n] for n in range(1,len(path)))
                    continue
                descendants = space.get_descendant_granules(label)
                row = tk.Frame(rows_inner,bg="white",height=row_height); row.pack_propagate(False)
                gutter = tk.Canvas(row,width=min(len(path)-1,12)*13+19,height=row_height,bg="white",bd=0,highlightthickness=0)
                gutter.pack(side="left",fill="y")
                first = descendants[0] if descendants else None
                rgb = native_rgb.get(first.label) if first is not None else None
                color = self.app._safe_hex_from_rgb(rgb) if rgb is not None else UtilsTools.lab_to_hex(space.lab_from_model(first.positive)) if first is not None else "#cccccc"
                swatch = tk.Canvas(row, width=swatch_size+8, height=row_height, bg="white", bd=0, highlightthickness=0)
                swatch.pack(side="left", padx=(0, 7))
                top = (row_height-swatch_size)//2
                swatch.create_rectangle(4, top, 4+swatch_size, top+swatch_size, fill=color, outline="#9ca3af")
                title = tk.Label(row,text=label,bg="white",fg="#243043",font=("Segoe UI",10,"bold"),anchor="w",cursor="hand2")
                title.pack(side="left",fill="x",expand=True)
                count=len(descendants)
                tk.Label(row,text=f"{count} granule{'s' if count!=1 else ''}",bg="white",fg=UtilsTools.UI_ACCENT if count>1 else "#6b7280",font=("Segoe UI",8,"bold" if count>1 else "normal")).pack(side="right",padx=7)
                for widget in (row,gutter,title,swatch): widget.bind("<Button-1>",lambda e,p=path:toggle(p))
                items.append({"path":path,"frame":row,"gutter":gutter,"height":row_height,"guides":guides,"more":more})
                children = space.get_category_children(label)
                stack.extend((path+(child,),guides+(more,),idx<len(children)-1) for idx,child in reversed(list(enumerate(children))))
        self._filter_color_evaluation_entries(vars_dict)
        first_label = vars_dict["color_row_order"][0]
        vars_dict["primary_label"] = first_label
        vars_dict["primary_mode"] = "row"
        vars_dict["analysis_mode_var"].set("Single color selected.")
        self._refresh_color_evaluation_comparison(vars_dict)
        self._highlight_color_evaluation_rows(vars_dict)
        # A StringVar trace is recreated with each window; remove an old one
        # when reloading the data so search remains one callback per edit.
        if not vars_dict.get("search_trace_registered"):
            vars_dict["color_search_var"].trace_add(
                "write", lambda *_: self._filter_color_evaluation_entries(vars_dict))
            vars_dict["search_trace_registered"] = True

    def _filter_color_evaluation_entries(self, vars_dict):
        """Filter prebuilt rows, retaining the color-space's original order."""
        query = vars_dict["color_search_var"].get().strip().casefold()
        items = vars_dict.get("evaluation_explorer_rows", [])
        if items:
            opened = vars_dict["evaluation_explorer_open"]
            matches = set()
            if query:
                for item in items:
                    p=item["path"]
                    if any(query in r[1].casefold() for r in p):
                        matches.update(p[:n] for n in range(1,len(p)+1))
            visible = [item for item in items if (item["path"] in matches if query else
                       all(item["path"][:n] in opened for n in range(1,len(item["path"]))))]
            siblings = {}
            for item in visible:
                path = item["path"]
                siblings.setdefault(path[:-1], []).append(path)
            last = {parent: paths[-1] for parent, paths in siblings.items()}
            desired = []
            for item in visible:
                path = item["path"]
                category = path[-1][0] == "category"
                expanded_now = category and bool(siblings.get(path))
                more = len(path)>1 and path != last[path[:-1]]
                guides = tuple(n>1 and path[:n] != last.get(path[:n-1])
                               for n in range(1,len(path)))
                signature = (guides, more, expanded_now, category)
                if item.get("guide_signature") != signature:
                    self._evaluation_tree_guides(item["gutter"],len(path)-1,guides,more,
                                                 expanded_now,category,item["height"])
                    item["guide_signature"] = signature
                row = item["frame"]
                row._evaluation_root_gap = (5, 0) if len(path)==1 else (0, 0)
                desired.append(row)
            self._pack_evaluation_rows(vars_dict["rows_inner"],desired,padx=(5,5))
            return
        category_rows = vars_dict.get("category_rows", [])
        if category_rows:
            # Repack only existing frames in model order, not in the order in
            # which a search query happened to reveal them.
            for info in category_rows:
                info["frame"].pack_forget()
            for info in category_rows:
                category_match = query in info["label"].casefold()
                child_matches = {label for label in info["labels"]
                                 if query in label.casefold()}
                show_group = not query or category_match or bool(child_matches)
                if show_group:
                    info["frame"].pack(fill="x", pady=(2, 0))
                for label in info["labels"]:
                    vars_dict["color_row_refs"][label]["frame"].pack_forget()
                for label in info["labels"]:
                    if not query or category_match or label in child_matches:
                        vars_dict["color_row_refs"][label]["frame"].pack(
                            fill="x", padx=(13, 8), pady=3)
                expanded = bool(info["open"] or (query and show_group))
                if expanded and show_group and not info.get("single"):
                    info["children"].pack(fill="x")
                else:
                    info["children"].pack_forget()
                if not info.get("single"):
                    info["arrow"].configure(text="▾" if expanded else "▸")
        else:
            for label in vars_dict.get("color_row_order", []):
                vars_dict["color_row_refs"][label]["frame"].pack_forget()
            for label in vars_dict.get("color_row_order", []):
                if query in label.casefold():
                    vars_dict["color_row_refs"][label]["frame"].pack(
                        fill="x", padx=(8, 8), pady=3)

    @staticmethod
    def _evaluation_sample_snapshot(name, lab, rgb, hex_color, source="custom",
                                    category=None, row_label=None):
        """Validated, independent copy of an actual LAB color (never a category mean)."""
        lab = tuple(float(value) for value in np.asarray(lab, dtype=float).reshape(3))
        if not np.isfinite(lab).all():
            raise ValueError("Sample LAB coordinates must be finite.")
        rgb = UtilsTools.safe_rgb_tuple(rgb)
        hex_color = str(hex_color).strip()
        if not hex_color.startswith("#") or len(hex_color) != 7:
            hex_color = UtilsTools.rgb_to_hex(rgb)
        return {
            "name": str(name).strip() or "Sample",
            "lab": lab, "rgb": tuple(rgb), "hex": hex_color,
            "source": str(source or "custom"),
            "category": category, "row_label": row_label,
        }

    def _add_color_evaluation_quick_sample(self, vars_dict, name, lab, rgb,
                                           hex_color, source="custom",
                                           category=None, row_label=None):
        """Remember recent colors, preserving original LAB precision and pins."""
        try:
            sample = self._evaluation_sample_snapshot(
                name, lab, rgb, hex_color, source, category, row_label)
        except (TypeError, ValueError, OverflowError):
            return None
        history = vars_dict.setdefault("quick_samples", [])
        signature = (sample["row_label"], sample["source"], sample["name"],
                     tuple(sample["lab"]), tuple(sample["rgb"]))
        existing = next((item for item in history if item.get("signature") == signature), None)
        if existing is not None:
            history.remove(existing)
            history.insert(0, existing)
            item = existing
        else:
            vars_dict["quick_samples_sequence"] = vars_dict.get("quick_samples_sequence", 0) + 1
            item = dict(sample, id=vars_dict["quick_samples_sequence"],
                        pinned=False, signature=signature)
            history.insert(0, item)
        # Keep at most 12 unpinned samples; pinned ones are deliberately retained.
        recent = 0
        for saved in list(history):
            if not saved["pinned"]:
                recent += 1
                if recent > 12:
                    history.remove(saved)
        self._render_color_evaluation_quick_samples(vars_dict)
        return item

    def _render_color_evaluation_quick_samples(self, vars_dict):
        """Update the horizontal thumbnail strip without rebuilding the main UI."""
        outer = vars_dict.get("quick_samples_outer")
        inner = vars_dict.get("quick_samples_tiles")
        if outer is None or inner is None:
            return
        history = vars_dict.get("quick_samples", [])
        # Keep the Quick Samples header visible even before the first sample;
        # otherwise the new workflow looks identical to the previous version.
        if not outer.winfo_manager():
            outer.pack(fill="x", pady=(0, 5), after=vars_dict.get("quick_samples_after"))
        # Widgets are rebuilt only when the actual sample history changes.
        for child in inner.winfo_children():
            child.destroy()
        for item in ([row for row in history if row["pinned"]]
                     + [row for row in history if not row["pinned"]]):
            # Color-only thumbnails: names and precise values are retained in
            # the history and shown when selected, not repeated in the strip.
            tile = tk.Frame(inner, bg="white", highlightthickness=1,
                            highlightbackground="#d7dce5")
            tile.pack(side="left", padx=3, pady=2)
            swatch = tk.Canvas(tile, width=42, height=39, bd=0,
                               highlightthickness=0, bg="white", cursor="hand2")
            swatch.create_rectangle(3, 3, 39, 36, fill=item["hex"],
                                    outline="#7f8793", width=1)
            swatch.pack(side="left", padx=(3, 1), pady=3)
            swatch.bind("<Button-1>",
                        lambda _event, sid=item["id"]:
                        self._select_color_evaluation_quick_sample(vars_dict, sid))
            tk.Button(
                tile, text="★" if item["pinned"] else "☆",
                font=("Segoe UI", 9), relief="flat", bd=0, bg="white",
                fg=UtilsTools.UI_ACCENT if item["pinned"] else "#718096",
                activebackground=UtilsTools.UI_ACCENT_SOFT,
                cursor="hand2", padx=1, pady=0,
                command=lambda sid=item["id"]: self._pin_color_evaluation_sample(vars_dict, sid)
            ).pack(side="left", padx=(0, 2), anchor="n")
        vars_dict["quick_samples_title_btn"].configure(
            text=("▾" if vars_dict.get("quick_samples_expanded", True) else "▸")
            + f"  Quick Samples ({len(history)})")
        body = vars_dict["quick_samples_body"]
        canvas = vars_dict["quick_samples_canvas"]
        scroll = vars_dict["quick_samples_scroll"]
        empty_label = vars_dict["quick_samples_empty_label"]
        if not vars_dict.get("quick_samples_expanded", True):
            body.pack_forget()
            return
        body.pack(fill="x", padx=6, pady=(0, 1))
        if history:
            empty_label.pack_forget()
            canvas.pack(fill="x", expand=True)
            # The canvas resize callback shows horizontal scroll only if needed.
        else:
            canvas.pack_forget()
            scroll.pack_forget()
            empty_label.pack(fill="x", padx=4, pady=(2, 4))

    def _toggle_color_evaluation_quick_samples(self, vars_dict):
        vars_dict["quick_samples_expanded"] = not vars_dict.get("quick_samples_expanded", True)
        self._render_color_evaluation_quick_samples(vars_dict)

    def _pin_color_evaluation_sample(self, vars_dict, sample_id):
        for item in vars_dict.get("quick_samples", []):
            if item["id"] == sample_id:
                item["pinned"] = not item["pinned"]
                break
        self._render_color_evaluation_quick_samples(vars_dict)

    def _clear_color_evaluation_recent_samples(self, vars_dict):
        vars_dict["quick_samples"] = [item for item in vars_dict.get("quick_samples", [])
                                       if item["pinned"]]
        self._render_color_evaluation_quick_samples(vars_dict)

    def _get_color_evaluation_side_sample(self, vars_dict, side):
        """Return an independent sample for A or B, whether a row or an external color."""
        is_a = side == "A"
        mode = vars_dict.get("primary_mode", "row") if is_a else vars_dict.get("secondary_mode")
        prefix = "primary" if is_a else "secondary"
        if mode == "custom":
            lab = vars_dict.get(prefix + "_custom_lab")
            rgb = vars_dict.get(prefix + "_custom_rgb")
            hx = vars_dict.get(prefix + "_custom_hex")
            if lab is None or rgb is None or hx is None:
                return None
            return self._evaluation_sample_snapshot(
                vars_dict.get(prefix + "_custom_name", "Sample"), lab, rgb, hx,
                vars_dict.get(prefix + "_custom_source", "custom"))
        if mode == "row" or (is_a and mode is None):
            label = vars_dict.get(prefix + "_label")
            refs = vars_dict.get("color_row_refs", {}).get(label)
            if refs is not None:
                return self._evaluation_sample_snapshot(
                    label, refs["lab"], refs["rgb"], refs["hex"],
                    "granule" if refs.get("category") else "prototype",
                    refs.get("category"), label)
        return None

    def _set_color_evaluation_side_sample(self, vars_dict, side, sample):
        """Assign A/B without recomputing until both sides are ready."""
        prefix = "primary" if side == "A" else "secondary"
        label = sample.get("row_label") if sample else None
        refs = vars_dict.get("color_row_refs", {}).get(label)
        # After loading another space, old row snapshots become external samples.
        matching_row = bool(refs is not None and np.allclose(
            np.asarray(refs["lab"]), np.asarray(sample["lab"]), rtol=0, atol=1e-7)) if sample else False
        if matching_row:
            vars_dict[prefix + "_mode"] = "row"
            vars_dict[prefix + "_label"] = label
            vars_dict[prefix + "_custom_lab"] = None
            vars_dict[prefix + "_custom_rgb"] = None
            vars_dict[prefix + "_custom_hex"] = None
        elif sample is not None:
            vars_dict[prefix + "_mode"] = "custom"
            vars_dict[prefix + "_label"] = None
            vars_dict[prefix + "_custom_lab"] = sample["lab"]
            vars_dict[prefix + "_custom_rgb"] = sample["rgb"]
            vars_dict[prefix + "_custom_hex"] = sample["hex"]
            vars_dict[prefix + "_custom_name"] = sample["name"]
            vars_dict[prefix + "_custom_source"] = sample["source"]
        elif side == "B":
            vars_dict["secondary_mode"] = None
            vars_dict["secondary_label"] = None
        vars_dict["comparison_mode"] = False
        vars_dict["analysis_view_mode"] = "comparison"
        vars_dict["closest_ranking"] = []
        vars_dict["closest_best"] = None
        vars_dict["closest_metric"] = None

    def _select_color_evaluation_quick_sample(self, vars_dict, sample_id):
        """Immediately compare the selected saved color against the other side."""
        item = next((item for item in vars_dict.get("quick_samples", [])
                     if item["id"] == sample_id), None)
        if item is None:
            return
        history = vars_dict["quick_samples"]
        history.remove(item)
        history.insert(0, item)
        self._render_color_evaluation_quick_samples(vars_dict)
        side = vars_dict["quick_samples_target_var"].get()
        self._set_color_evaluation_side_sample(vars_dict, side, item)
        vars_dict["analysis_mode_var"].set(
            "Comparison active. Select another sample or reference." if
            self._get_color_evaluation_side_sample(vars_dict, "B") else "Sample selected.")
        self._refresh_color_evaluation_comparison(vars_dict)
        self._highlight_color_evaluation_rows(vars_dict)

    def _use_color_evaluation_external_sample(self, vars_dict, *, name, lab,
                                              rgb, hex_color, source="custom", target="B"):
        """Save and use one externally supplied color, leaving its picker open."""
        item = self._add_color_evaluation_quick_sample(
            vars_dict, name=name, lab=lab, rgb=rgb,
            hex_color=hex_color, source=source)
        if item is None:
            self.app.custom_warning("Invalid Sample", "The selected color is not valid.",
                                parent=getattr(self, "_color_evaluation_window", None))
            return False
        self._set_color_evaluation_side_sample(vars_dict, target, item)
        vars_dict["quick_samples_target_var"].set(target)
        vars_dict["analysis_mode_var"].set(
            f"{name} added to {self._get_color_evaluation_target_display_name(target)}. Choose another sample to continue comparing.")
        self._refresh_color_evaluation_comparison(vars_dict)
        self._highlight_color_evaluation_rows(vars_dict)
        return True

    def _get_color_evaluation_target_display_name(self, side):
        """Return the UI display name for a comparison side."""
        return "Selected" if str(side).upper() == "A" else "Reference"

    def _clear_color_evaluation_analysis(self, vars_dict):
        """Reset the analysis panel."""
        vars_dict["primary_name_var"].set("None")
        vars_dict["secondary_name_var"].set("None")
        for key in ("primary_meta_var", "secondary_meta_var", "primary_lab_var", "secondary_lab_var"):
            vars_dict[key].set("")

        vars_dict["primary_swatch"].itemconfig(vars_dict["primary_rect"], fill="#cccccc")
        vars_dict["secondary_swatch"].itemconfig(vars_dict["secondary_rect"], fill="#f0f0f0")

        vars_dict["secondary_mode"] = None
        vars_dict["secondary_custom_lab"] = None
        vars_dict["secondary_custom_rgb"] = None
        vars_dict["secondary_custom_hex"] = None
        vars_dict["secondary_custom_name"] = "Custom Color"

        self._update_color_evaluation_result_card(
            vars_dict=vars_dict,
            title="Select a prototype to evaluate.",
            detail="",
            summary="",
            status="unavailable"
        )

        self._update_color_evaluation_conversion_inspector(vars_dict)
        self._update_color_evaluation_membership_panel(vars_dict, sample_lab=None)

    def _swap_color_evaluation_rows(self, vars_dict):
        """Exchange A and B, including custom/image colors and precise LAB values."""
        first = self._get_color_evaluation_side_sample(vars_dict, "A")
        second = self._get_color_evaluation_side_sample(vars_dict, "B")
        if first is None or second is None:
            return
        self._set_color_evaluation_side_sample(vars_dict, "A", second)
        self._set_color_evaluation_side_sample(vars_dict, "B", first)
        self._refresh_color_evaluation_comparison(vars_dict)
        self._highlight_color_evaluation_rows(vars_dict)

    def _enable_color_evaluation_comparison_mode(self, vars_dict):
        """Enable comparison mode so clicked colors become comparison colors."""
        primary = self._get_color_evaluation_side_sample(vars_dict, "A")

        if primary is None:
            vars_dict["comparison_mode"] = False
            vars_dict["analysis_mode_var"].set("Select a primary color first.")
            return

        vars_dict["comparison_mode"] = True
        vars_dict["analysis_mode_var"].set(
            "Comparison mode enabled. Click another color to compare against the selected one."
        )

    def _clear_color_evaluation_comparison(self, vars_dict, clear_custom=True):
        """Clear the comparison color and return to single-color analysis."""
        vars_dict["analysis_view_mode"] = "comparison"

        vars_dict["comparison_mode"] = False
        vars_dict["secondary_label"] = None
        vars_dict["secondary_mode"] = None

        if clear_custom:
            vars_dict["secondary_custom_lab"] = None
            vars_dict["secondary_custom_rgb"] = None
            vars_dict["secondary_custom_hex"] = None
            vars_dict["secondary_custom_name"] = "Custom Color"

        if self._get_color_evaluation_side_sample(vars_dict, "A") is not None:
            vars_dict["analysis_mode_var"].set("Single color selected.")
        else:
            vars_dict["analysis_mode_var"].set("Select a color from the list.")

        self._refresh_color_evaluation_comparison(vars_dict)

        self._highlight_color_evaluation_rows(vars_dict)

    def _refresh_color_evaluation_comparison(self, vars_dict):
        """Update the analysis from two real LAB samples (rows or external colors)."""
        vars_dict["analysis_view_mode"] = "comparison"
        self._set_color_evaluation_inspector_layout(vars_dict)
        first = self._get_color_evaluation_side_sample(vars_dict, "A")
        second = self._get_color_evaluation_side_sample(vars_dict, "B")
        swap = vars_dict.get("swap_color_button")
        if swap is not None:
            swap.configure(state="normal" if first and second else "disabled")
        if first is None:
            self._clear_color_evaluation_analysis(vars_dict)
            return

        def update_side(side, sample):
            prefix = "primary" if side == "A" else "secondary"
            vars_dict[prefix + "_name_var"].set(sample["name"] if sample else "None")
            vars_dict[prefix + "_meta_var"].set(
                (f"Granule · {sample['category']}" if sample.get("category") else
                 "" if sample.get("row_label") else
                 "Image sample" if sample["source"].startswith("image") else
                 "Custom / saved sample") if sample else "")
            vars_dict[prefix + "_lab_var"].set(
                self._format_color_evaluation_value(
                    sample["lab"], vars_dict["color_display_mode_var"].get(),
                    rgb=sample["rgb"], hex_color=sample["hex"], card=True)
                if sample else "")
            vars_dict[prefix + "_swatch"].itemconfig(
                vars_dict[prefix + "_rect"], fill=sample["hex"] if sample else "#f0f0f0")

        update_side("A", first)
        update_side("B", second)
        active = second if second else first
        self._update_color_evaluation_conversion_inspector(
            vars_dict=vars_dict, lab=active["lab"], rgb=active["rgb"],
            hex_color=active["hex"], name=active["name"], source=active["source"])
        external = next((s for s in (second, first) if s is not None
                         and not s.get("row_label")), None)
        vars_dict["evaluation_membership_side"] = "B" if external is second else "A"
        self._update_color_evaluation_membership_panel(
            vars_dict, sample_lab=external["lab"] if external else None, sample=external)

        if second is None:
            self._update_color_evaluation_result_card(
                vars_dict, title="Single color selected. Comparison not active.",
                detail="", summary=("Select another color, add a custom/image sample, "
                                    "or reuse a color from Quick Samples."),
                status="unavailable")
            self._update_color_evaluation_graph_buttons(vars_dict)
            return

        metric_name = self.app.threshold_settings.get("metric", "CIEDE2000")
        evaluation = self.app.evaluate_color_difference_threshold(
            sample_lab=first["lab"], prototype_lab=second["lab"],
            metric=metric_name, threshold_settings=self.app.threshold_settings)
        metric_value = evaluation.get("metric_value", evaluation.get("delta_e"))
        self._update_color_evaluation_result_card(
            vars_dict, title=evaluation.get("evaluation", "Metric unavailable"),
            detail=(evaluation.get("detail", f"{metric_name} = {metric_value:.3f}")
                    if metric_value is not None else "Unable to compute selected metric"),
            summary=evaluation.get("summary_visual", evaluation.get("summary", "")),
            status=evaluation.get("status", "unavailable"))
        self._update_color_evaluation_graph_buttons(vars_dict)

    def _open_color_evaluation_image_sampler(self, vars_dict):
        """
        Open a compact image sampler for the Color Evaluation window.

        It allows:
        - selecting one loaded image;
        - clicking one pixel;
        - dragging a rectangle to sample the average RGB;
        - sending the sampled color as the custom comparison color.
        """
        # This dialog accepts loaded originals and temporary images alike.
        # It deliberately does not add the latter to the application's image list.
        parent = getattr(self, "_color_evaluation_window", self.root)

        popup = tk.Toplevel(parent)
        popup.withdraw()
        popup.title("Sample Color from Image")
        popup.configure(bg="#eeeeee")
        popup.resizable(True, True)
        popup.transient(parent)

        WIN_W, WIN_H = 660, 710
        popup.minsize(620, 620)

        try:
            self.app.center_popup_to_parent(popup, WIN_W, WIN_H, parent=parent)
        except Exception:
            self.app.center_popup(popup, WIN_W, WIN_H)

        state = {
            "window_id": None,
            "pil_img": None,
            "photo": None,
            "display_w": 560,
            "display_h": 340,
            "scale": 1.0,
            "offset_x": 0,
            "offset_y": 0,
            "view_zoom": 1.0,
            "view_cx": 0.0,
            "view_cy": 0.0,
            "display_img_w": 0,
            "display_img_h": 0,
            "drag_start": None,
            "rect_id": None,
            "sample_rgb": None,
            "sample_lab": None,
            "sample_hex": None,
            "sample_name": "Image Sample",
        }

        # Main shell
        outer = tk.Frame(popup, bg="#eeeeee")
        outer.pack(fill="both", expand=True, padx=12, pady=12)

        panel = tk.Frame(outer, bg="white", bd=1, relief="solid")
        panel.pack(fill="both", expand=True)

        header = tk.Frame(panel, bg="#f6f6f6", height=54)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(
            header,
            text="Sample Color from Image",
            font=("Sans", 13, "bold"),
            bg="#f6f6f6",
            fg="#222222",
            anchor="w",
            padx=16
        ).pack(side="left", fill="y")

        tk.Label(
            header,
            text="Click pixel or drag ROI",
            font=("Sans", 9, "italic"),
            bg="#f6f6f6",
            fg="#666666",
            padx=16
        ).pack(side="right", fill="y")

        body = tk.Frame(panel, bg="white")
        body.pack(fill="both", expand=True, padx=14, pady=10)

        # Image selector
        selector_card = tk.Frame(body, bg="#fafafa", bd=1, relief="solid")
        selector_card.pack(fill="x", pady=(0, 8))

        selector_row = tk.Frame(selector_card, bg="#fafafa")
        selector_row.pack(fill="x", padx=12, pady=8)

        tk.Label(
            selector_row,
            text="Image:",
            bg="#fafafa",
            font=("Sans", 10, "bold")
        ).pack(side="left", padx=(0, 8))

        image_ids = []
        image_names = []
        temp_sources = {}
        for wid, path in (getattr(self.app, "load_images_names", None) or {}).items():
            if not path:
                continue
            image_ids.append(wid)
            image_names.append(f"{os.path.basename(path)} [loaded]")

        selected_image_var = tk.StringVar(value=image_names[0] if image_names else "")
        image_combo = UtilsTools.styled_combobox(
            selector_row, textvariable=selected_image_var,
            state="readonly", values=image_names, width=35)
        image_combo.pack(side="left", fill="x", expand=True)
        open_temp_button = tk.Button(
            selector_row, text="+ Open image...", relief="solid", bd=1,
            bg=UtilsTools.UI_ACCENT_SOFT, fg=UtilsTools.UI_ACCENT_DARK,
            cursor="hand2", font=("Segoe UI", 9, "bold"))
        open_temp_button.pack(side="left", padx=(8, 0))

        # Image preview
        image_card = tk.Frame(body, bg="#fafafa", bd=1, relief="solid")
        image_card.pack(fill="both", expand=True, pady=(0, 8))

        tk.Label(
            image_card,
            text="Image preview",
            bg="#fafafa",
            font=("Sans", 10, "bold"),
            anchor="w",
            padx=12,
            pady=7
        ).pack(fill="x")

        canvas = tk.Canvas(
            image_card,
            width=state["display_w"],
            height=state["display_h"],
            bg="white",
            highlightthickness=0,
            bd=0
        )
        canvas.pack(padx=12, pady=(0, 6))

        tip_var = tk.StringVar(
            value=("Mouse wheel: zoom · Click: pixel · Drag: ROI. "
                   "Open a temporary image if none is loaded.")
        )

        tk.Label(
            image_card,
            textvariable=tip_var,
            bg="#fafafa",
            fg="#666666",
            font=("Sans", 9, "italic"),
            wraplength=570,
            justify="left",
            padx=12,
            pady=0
        ).pack(fill="x", pady=(0, 8))

        # Sampled color panel
        sample_card = tk.Frame(body, bg="#fafafa", bd=1, relief="solid")
        sample_card.pack(fill="x", pady=(0, 0))

        tk.Label(
            sample_card,
            text="Sampled color",
            bg="#fafafa",
            font=("Sans", 10, "bold"),
            anchor="w",
            padx=12,
            pady=7
        ).pack(fill="x")

        sample_row = tk.Frame(sample_card, bg="#fafafa")
        sample_row.pack(fill="x", padx=12, pady=(0, 10))

        values_frame = tk.Frame(sample_row, bg="#fafafa")
        values_frame.pack(side="left", fill="x", expand=True)

        rgb_var = tk.StringVar(value="RGB: -")
        lab_var = tk.StringVar(value="LAB: -")
        hex_var = tk.StringVar(value="HEX: -")

        tk.Label(
            values_frame,
            textvariable=rgb_var,
            bg="#fafafa",
            anchor="w",
            font=("Consolas", 9)
        ).pack(anchor="w")

        tk.Label(
            values_frame,
            textvariable=lab_var,
            bg="#fafafa",
            anchor="w",
            font=("Consolas", 9)
        ).pack(anchor="w", pady=(2, 0))

        tk.Label(
            values_frame,
            textvariable=hex_var,
            bg="#fafafa",
            anchor="w",
            font=("Consolas", 9)
        ).pack(anchor="w", pady=(2, 0))

        preview_canvas = tk.Canvas(
            sample_row,
            width=130,
            height=42,
            bg="#fafafa",
            highlightthickness=0,
            bd=0
        )
        preview_canvas.pack(side="left", padx=(12, 12))

        preview_rect = preview_canvas.create_rectangle(
            8, 7, 122, 35,
            fill="#d9d9d9",
            outline="#555555"
        )

        use_button = ttk.Button(sample_row, text="Add to Reference", state="disabled")
        use_button.pack(side="right", padx=(5, 0))
        add_to_a_button = ttk.Button(sample_row, text="Add to Selected", state="disabled")
        add_to_a_button.pack(side="right")

        # Bottom buttons
        footer = tk.Frame(panel, bg="white")
        footer.pack(fill="x", padx=14, pady=(0, 12))

        tk.Button(
            footer,
            text="Done",
            width=12,
            command=popup.destroy
        ).pack(side="right")

        # Helpers
        def _get_selected_window_id():
            current_name = selected_image_var.get()

            if current_name in image_names:
                return image_ids[image_names.index(current_name)]

            return image_ids[0] if image_ids else None

        def _image_object_to_pil(img_obj):
            """
            Convert different internal image representations to PIL RGBA.
            """
            if isinstance(img_obj, Image.Image):
                return img_obj.convert("RGBA")

            if isinstance(img_obj, np.ndarray):
                arr = img_obj

                if arr.dtype != np.uint8:
                    arr = np.clip(arr, 0, 255).astype(np.uint8)

                if arr.ndim == 2:
                    return Image.fromarray(arr, "L").convert("RGBA")

                if arr.ndim == 3 and arr.shape[2] >= 3:
                    return Image.fromarray(arr[:, :, :4] if arr.shape[2] == 4 else arr[:, :, :3]).convert("RGBA")

            if isinstance(img_obj, str) and os.path.exists(img_obj):
                with Image.open(img_obj) as image_file:
                    return ImageOps.exif_transpose(image_file).convert("RGBA")

            raise ValueError("Unsupported image format.")

        def _clamp(value, min_value, max_value):
            """Clamp a numeric value."""
            return max(min_value, min(max_value, value))


        def _is_point_inside_display(canvas_x, canvas_y):
            """Return True if a canvas coordinate is inside the displayed image area."""
            disp_w = state.get("display_img_w", 0)
            disp_h = state.get("display_img_h", 0)

            if disp_w <= 0 or disp_h <= 0:
                return False

            ox = state["offset_x"]
            oy = state["offset_y"]

            return (
                ox <= canvas_x < ox + disp_w
                and oy <= canvas_y < oy + disp_h
            )


        def _clamp_canvas_point_to_display(canvas_x, canvas_y):
            """Clamp a canvas coordinate to the displayed image area."""
            disp_w = max(1, state.get("display_img_w", 1))
            disp_h = max(1, state.get("display_img_h", 1))

            ox = state["offset_x"]
            oy = state["offset_y"]

            x = _clamp(canvas_x, ox, ox + disp_w - 1)
            y = _clamp(canvas_y, oy, oy + disp_h - 1)

            return x, y


        def _get_view_crop_box():
            """
            Return the current visible crop box in full-image coordinates.

            The canvas/display size stays fixed. Only this crop changes with zoom.
            """
            if state["pil_img"] is None:
                return None

            img_w, img_h = state["pil_img"].size

            zoom = max(1.0, float(state.get("view_zoom", 1.0)))
            cx = float(state.get("view_cx", img_w / 2))
            cy = float(state.get("view_cy", img_h / 2))

            crop_w = max(1.0, img_w / zoom)
            crop_h = max(1.0, img_h / zoom)

            left = cx - crop_w / 2
            top = cy - crop_h / 2

            left = _clamp(left, 0, max(0, img_w - crop_w))
            top = _clamp(top, 0, max(0, img_h - crop_h))

            right = left + crop_w
            bottom = top + crop_h

            return left, top, right, bottom


        def _render_preview():
            """
            Render the current zoom viewport into the fixed preview canvas.
            """
            if state["pil_img"] is None:
                return

            crop_box = _get_view_crop_box()
            if crop_box is None:
                return

            left, top, right, bottom = crop_box

            crop = state["pil_img"].crop((
                int(round(left)),
                int(round(top)),
                int(round(right)),
                int(round(bottom))
            ))

            disp_w = max(1, int(state["display_img_w"]))
            disp_h = max(1, int(state["display_img_h"]))

            resized = crop.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
            state["photo"] = ImageTk.PhotoImage(resized)

            canvas.delete("image")
            canvas.create_image(
                state["offset_x"],
                state["offset_y"],
                image=state["photo"],
                anchor="nw",
                tags=("image",)
            )

            try:
                canvas.tag_lower("image")
            except Exception:
                pass


        def _canvas_to_image_xy(canvas_x, canvas_y):
            """
            Convert canvas coordinates to full-image coordinates,
            taking the current zoom viewport into account.
            """
            if state["pil_img"] is None:
                return None

            disp_w = max(1, state.get("display_img_w", 1))
            disp_h = max(1, state.get("display_img_h", 1))

            canvas_x, canvas_y = _clamp_canvas_point_to_display(canvas_x, canvas_y)

            rel_x = canvas_x - state["offset_x"]
            rel_y = canvas_y - state["offset_y"]

            crop_box = _get_view_crop_box()
            if crop_box is None:
                return None

            left, top, right, bottom = crop_box

            crop_w = right - left
            crop_h = bottom - top

            x = left + (rel_x / disp_w) * crop_w
            y = top + (rel_y / disp_h) * crop_h

            img_w, img_h = state["pil_img"].size

            x = int(_clamp(x, 0, img_w - 1))
            y = int(_clamp(y, 0, img_h - 1))

            return x, y


        def _clear_preview_rectangle():
            """Remove the current ROI rectangle from the preview canvas."""
            if state["rect_id"] is not None:
                try:
                    canvas.delete(state["rect_id"])
                except Exception:
                    pass

            state["rect_id"] = None
            state["drag_start"] = None


        def _apply_preview_zoom(factor=None, reset=False, event=None):
            """
            Apply zoom to the preview without changing the canvas size.

            If the mouse is over the image, the zoom is centered around that point.
            """
            if state["pil_img"] is None:
                return "break"

            img_w, img_h = state["pil_img"].size

            _clear_preview_rectangle()

            if reset:
                state["view_zoom"] = 1.0
                state["view_cx"] = img_w / 2
                state["view_cy"] = img_h / 2
                _render_preview()
                tip_var.set(
                    "Mouse wheel to zoom. Click to sample one pixel, or drag to sample the average color of a region."
                )
                return "break"

            if factor is None:
                return "break"

            old_zoom = float(state.get("view_zoom", 1.0))
            new_zoom = _clamp(old_zoom * factor, 1.0, 16.0)

            if abs(new_zoom - old_zoom) < 1e-9:
                return "break"

            point_info = None
            if event is not None and _is_point_inside_display(event.x, event.y):
                source_xy = _canvas_to_image_xy(event.x, event.y)
                if source_xy is not None:
                    disp_w = max(1, state.get("display_img_w", 1))
                    disp_h = max(1, state.get("display_img_h", 1))

                    rel_x = event.x - state["offset_x"]
                    rel_y = event.y - state["offset_y"]

                    point_info = (
                        source_xy[0],
                        source_xy[1],
                        rel_x / disp_w,
                        rel_y / disp_h
                    )

            state["view_zoom"] = new_zoom

            if point_info is not None:
                source_x, source_y, rel_fx, rel_fy = point_info

                crop_w = max(1.0, img_w / new_zoom)
                crop_h = max(1.0, img_h / new_zoom)

                new_left = source_x - rel_fx * crop_w
                new_top = source_y - rel_fy * crop_h

                new_left = _clamp(new_left, 0, max(0, img_w - crop_w))
                new_top = _clamp(new_top, 0, max(0, img_h - crop_h))

                state["view_cx"] = new_left + crop_w / 2
                state["view_cy"] = new_top + crop_h / 2

            _render_preview()

            tip_var.set(
                f"Zoom: {new_zoom * 100:.0f}%. Click to sample one pixel, or drag to sample an average color."
            )

            return "break"


        def _on_preview_mousewheel(event):
            """Windows/macOS mouse wheel zoom."""
            if event.delta > 0:
                return _apply_preview_zoom(factor=1.15, event=event)
            else:
                return _apply_preview_zoom(factor=1 / 1.15, event=event)


        def _on_preview_linux_zoom_in(event):
            """Linux wheel up zoom."""
            return _apply_preview_zoom(factor=1.15, event=event)


        def _on_preview_linux_zoom_out(event):
            """Linux wheel down zoom."""
            return _apply_preview_zoom(factor=1 / 1.15, event=event)

        def _set_sample_rgb(rgb, source_text="image sample", lab_override=None):
            try:
                rgb = UtilsTools.safe_rgb_tuple(rgb)
                lab = UtilsTools.analysis_rgb_to_lab(rgb) if lab_override is None else lab_override
                lab = UtilsTools.safe_lab_tuple(lab)
                hex_color = UtilsTools.rgb_to_hex(rgb)

                state["sample_rgb"] = rgb
                state["sample_source"] = source_text
                state["sample_lab"] = lab
                state["sample_hex"] = hex_color

                rgb_var.set(f"RGB: {rgb[0]}, {rgb[1]}, {rgb[2]}")
                lab_var.set(f"LAB: {lab[0]:.4f}, {lab[1]:.4f}, {lab[2]:.4f}")
                hex_var.set(f"HEX: {hex_color.upper()}")

                preview_canvas.itemconfig(preview_rect, fill=hex_color)
                use_button.config(state="normal")
                add_to_a_button.config(state="normal")

                self._update_color_evaluation_conversion_inspector(
                    vars_dict=vars_dict,
                    lab=lab,
                    rgb=rgb,
                    hex_color=hex_color,
                    name="Image sample",
                    source=source_text
                )

            except Exception:
                state["sample_rgb"] = None
                state["sample_lab"] = None
                state["sample_hex"] = None

                rgb_var.set("RGB: -")
                lab_var.set("LAB: -")
                hex_var.set("HEX: -")

                preview_canvas.itemconfig(preview_rect, fill="#d9d9d9")
                use_button.config(state="disabled")
                add_to_a_button.config(state="disabled")

        def _clear_sample():
            state["sample_rgb"] = None
            state["sample_lab"] = None
            state["sample_hex"] = None

            rgb_var.set("RGB: -")
            lab_var.set("LAB: -")
            hex_var.set("HEX: -")

            preview_canvas.itemconfig(preview_rect, fill="#d9d9d9")
            use_button.config(state="disabled")
            add_to_a_button.config(state="disabled")


        def _get_best_sampler_source_pil(window_id):
            """
            Return the best available original PIL source for the sampler.

            Important:
            This Color Evaluation sampler should always sample from the real original image,
            not from Color Mapping or Color Mapping All visualizations.
            """
            if window_id in temp_sources:
                return temp_sources[window_id]

            if (
                hasattr(self.app, "pil_images_original")
                and window_id in self.app.pil_images_original
                and self.app.pil_images_original[window_id] is not None
            ):
                return _image_object_to_pil(self.app.pil_images_original[window_id])

            # Reload the original file if the in-memory source is unavailable.
            if (
                hasattr(self.app, "load_images_names")
                and window_id in self.app.load_images_names
                and self.app.load_images_names[window_id]
                and os.path.exists(self.app.load_images_names[window_id])
            ):
                with Image.open(self.app.load_images_names[window_id]) as image_file:
                    return ImageOps.exif_transpose(image_file).convert("RGBA")

            # Retain compatibility with image windows lacking an original PIL reference.
            if (
                hasattr(self.app, "images")
                and window_id in self.app.images
                and self.app.images[window_id] is not None
            ):
                return _image_object_to_pil(self.app.images[window_id])

            raise ValueError("No valid original image source found.")

        def _open_temporary_image():
            base = UtilsTools.get_base_path()
            candidates = (
                os.path.join(base, "test_images"),
                os.path.join(base, "image_test"),
                os.path.join(base, "Source", "test_images"),
                os.path.join(base, "Source", "image_test"),
                base,
            )
            initial_dir = next((p for p in candidates if os.path.isdir(p)), os.getcwd())
            path = filedialog.askopenfilename(
                parent=popup, title="Open temporary image for color sampling",
                initialdir=initial_dir,
                filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp"),
                           ("All files", "*.*")])
            if not path:
                return
            try:
                with Image.open(path) as img:
                    pil_image = ImageOps.exif_transpose(img).convert("RGBA")
            except Exception as exc:
                self.app.custom_warning("Image Error", f"Could not open this image:\n{exc}",
                                    parent=popup)
                return
            key = f"evaluation-temp-{len(temp_sources) + 1}"
            label_base = f"{os.path.basename(path)} [temporary]"
            label = label_base
            suffix = 2
            while label in image_names:
                label = f"{label_base} ({suffix})"
                suffix += 1
            temp_sources[key] = pil_image
            image_ids.append(key)
            image_names.append(label)
            image_combo.configure(values=image_names)
            selected_image_var.set(label)
            _load_selected_image()

        def _load_selected_image(*_):
            window_id = _get_selected_window_id()

            if window_id is None:
                tip_var.set("No image selected. Click '+ Open image...' to sample a temporary image.")
                return

            try:
                pil_img = _get_best_sampler_source_pil(window_id)
            except Exception:
                self.app.custom_warning(
                    "Image Error",
                    "Could not load the selected image.",
                    parent=popup
                )
                return

            state["window_id"] = window_id
            state["pil_img"] = pil_img

            img_w, img_h = pil_img.size
            canvas_w = state["display_w"]
            canvas_h = state["display_h"]

            scale = min(canvas_w / img_w, canvas_h / img_h)
            disp_w = max(1, int(round(img_w * scale)))
            disp_h = max(1, int(round(img_h * scale)))

            state["scale"] = scale
            state["offset_x"] = int((canvas_w - disp_w) / 2)
            state["offset_y"] = int((canvas_h - disp_h) / 2)
            state["display_img_w"] = disp_w
            state["display_img_h"] = disp_h

            # Reset viewport zoom for the newly selected image
            state["view_zoom"] = 1.0
            state["view_cx"] = img_w / 2
            state["view_cy"] = img_h / 2

            canvas.delete("all")
            state["rect_id"] = None
            state["drag_start"] = None

            _render_preview()
            _clear_sample()

            tip_var.set(
                "Mouse wheel to zoom. Click to sample one pixel, or drag to sample the average color of a region."
            )

        def _sample_roi_from_canvas(x1, y1, x2, y2):
            if state["pil_img"] is None:
                return

            p1 = _canvas_to_image_xy(x1, y1)
            p2 = _canvas_to_image_xy(x2, y2)

            if p1 is None or p2 is None:
                return

            ix1, iy1 = p1
            ix2, iy2 = p2

            left = min(ix1, ix2)
            right = max(ix1, ix2)
            top = min(iy1, iy2)
            bottom = max(iy1, iy2)

            source_name = selected_image_var.get().split(" [", 1)[0]
            if abs(right - left) <= 1 and abs(bottom - top) <= 1:
                state["sample_name"] = f"{source_name} ({left}, {top})"
                rgba = state["pil_img"].getpixel((left, top))
                if rgba[3] == 0:
                    _clear_sample()
                    tip_var.set("Transparent pixel · no color sample")
                    return
                _set_sample_rgb(rgba[:3], source_text="image pixel")
                return

            state["sample_name"] = f"{source_name} ROI ({left},{top})–({right},{bottom})"
            mean_lab, count, _ = UtilsTools.mean_lab_of_pil_roi(
                state["pil_img"], (left, top, right + 1, bottom + 1)
            )
            if not count:
                _clear_sample()
                tip_var.set("ROI has no visible pixels")
                return
            rgb = tuple(UtilsTools.lab_to_rgb(mean_lab))
            _set_sample_rgb(rgb, source_text="image ROI LAB average",
                            lab_override=mean_lab)

        def _on_mouse_down(event):
            if state["pil_img"] is None:
                return

            if not _is_point_inside_display(event.x, event.y):
                return

            x, y = _clamp_canvas_point_to_display(event.x, event.y)

            state["drag_start"] = (x, y)

            if state["rect_id"] is not None:
                try:
                    canvas.delete(state["rect_id"])
                except Exception:
                    pass

            state["rect_id"] = canvas.create_rectangle(
                x,
                y,
                x,
                y,
                outline="#ffcc00",
                width=2
            )


        def _on_mouse_drag(event):
            if state["drag_start"] is None or state["rect_id"] is None:
                return

            x0, y0 = state["drag_start"]
            x1, y1 = _clamp_canvas_point_to_display(event.x, event.y)

            canvas.coords(
                state["rect_id"],
                x0,
                y0,
                x1,
                y1
            )


        def _on_mouse_up(event):
            if state["drag_start"] is None:
                return

            x0, y0 = state["drag_start"]
            x1, y1 = _clamp_canvas_point_to_display(event.x, event.y)

            state["drag_start"] = None

            _sample_roi_from_canvas(x0, y0, x1, y1)

        def _use_sampled_color(target="B"):
            if any(state[key] is None for key in ("sample_rgb", "sample_lab", "sample_hex")):
                return
            name = state.get("sample_name", "Image Sample")
            if self._use_color_evaluation_external_sample(
                    vars_dict, name=name, lab=state["sample_lab"],
                    rgb=state["sample_rgb"], hex_color=state["sample_hex"],
                    source=state.get("sample_source", "image"), target=target):
                tip_var.set(f"Sample added to {self._get_color_evaluation_target_display_name(target)}. Continue sampling, or select Done.")

        use_button.configure(command=lambda: _use_sampled_color("B"))
        add_to_a_button.configure(command=lambda: _use_sampled_color("A"))
        open_temp_button.configure(command=_open_temporary_image)

        image_combo.bind("<<ComboboxSelected>>", _load_selected_image)

        canvas.bind("<ButtonPress-1>", _on_mouse_down)
        canvas.bind("<B1-Motion>", _on_mouse_drag)
        canvas.bind("<ButtonRelease-1>", _on_mouse_up)

        # Preview zoom with mouse wheel
        canvas.bind("<MouseWheel>", _on_preview_mousewheel, add="+")
        canvas.bind("<Button-4>", _on_preview_linux_zoom_in, add="+")
        canvas.bind("<Button-5>", _on_preview_linux_zoom_out, add="+")

        canvas.bind("<Double-Button-3>", lambda event: _apply_preview_zoom(reset=True))

        popup.bind("<Escape>", lambda e: popup.destroy())

        _load_selected_image()
        popup.deiconify()
        popup.grab_set()

    def _get_custom_color_input_mode_help(self, mode):
        """
        Compatibility wrapper. Logic lives in ColorEvaluationManager.
        """
        manager = self.app._get_color_evaluation_manager()
        return manager.get_custom_color_input_mode_help(mode)

    def _open_custom_color_input_dialog(self, vars_dict):
        """Use PyFCS's shared visual Color Picker directly for a quick A/B sample."""
        if not vars_dict.get("loaded_space_data"):
            self.app.custom_warning(
                "No Color Space Loaded", "Load a color space before evaluating colors.",
                parent=getattr(self, "_color_evaluation_window", None))
            return
        parent = getattr(self, "_color_evaluation_window", None) or self.root
        target = vars_dict["quick_samples_target_var"].get()
        active = self._get_color_evaluation_side_sample(vars_dict, target)
        initial_rgb = active["rgb"] if active else (217, 217, 217)

        def _add_selected_color(lab, rgb, hex_value, exact_lab, status_var):
            rgb = UtilsTools.safe_rgb_tuple(rgb)
            lab = UtilsTools.safe_lab_tuple(lab if exact_lab else UtilsTools.analysis_rgb_to_lab(rgb))
            accepted = self._use_color_evaluation_external_sample(
                vars_dict, name="Custom Color", lab=lab, rgb=rgb,
                hex_color=hex_value, source="custom LAB" if exact_lab else "custom RGB", target=target)
            if not accepted:
                status_var.set("The selected color could not be added.")
            return accepted

        # LAB entered numerically is authoritative; RGB is only its swatch.
        initial_lab = (active["lab"] if active and active.get("source") in
                       ("custom", "custom LAB", "image ROI LAB average") else None)
        return UtilsTools.open_square_color_picker(
            self.app, parent, initial_rgb=initial_rgb, initial_lab=initial_lab,
            initial_mode="LAB" if initial_lab is not None else None,
            on_color_submit=_add_selected_color,
            submit_text=f"Add to {self._get_color_evaluation_target_display_name(target)}", title="Evaluate Custom Color")

    def _open_custom_color_dialog(
        self,
        parent=None,
        title="Custom Color",
        subtitle="",
        submit_text="OK",
        require_name=False,
        default_name="Custom Color",
        on_submit=None,
        initial_lab=None,
        allow_evaluation_target=False,
        initial_evaluation_target="B",
    ):
        """
        Open a reusable styled dialog to input a custom color in RGB, LAB, or HEX.

        Parameters
        ----------
        parent : tk widget
            Parent window.
        title : str
            Dialog title.
        subtitle : str
            Kept for compatibility with existing callers; the mode selector
            communicates the available color representations.
        submit_text : str
            Text for the submit button.
        require_name : bool
            Whether to request a color name.
        default_name : str
            Initial color name when require_name=True.
        initial_lab : sequence of 3 floats, optional
            Prefill an existing granule with its unrounded LAB coordinates.
        on_submit : callable
            Callback called as:
                on_submit(name, sample_lab, sample_rgb, sample_hex, dialog, input_vars)
        """
        MAX_NAME_CHARS = UtilsTools.MAX_COLOR_NAME_CHARS

        parent = self.app._get_valid_dialog_parent(
            parent or getattr(self, "_color_evaluation_window", self.root)
        )

        dialog = tk.Toplevel(parent)
        dialog.withdraw()
        dialog.title(title)
        dialog.resizable(False, False)
        dialog.configure(bg="#f5f6f8")
        dialog.transient(parent)

        WIN_W = 760
        WIN_H = 420 if require_name else (435 if allow_evaluation_target else 390)

        try:
            if parent is not None and hasattr(parent, "winfo_x"):
                self.app.center_popup_to_parent(dialog, WIN_W, WIN_H, parent=parent)
            else:
                self.app.center_popup(dialog, WIN_W, WIN_H)
        except Exception:
            self.app.center_popup(dialog, WIN_W, WIN_H)

        input_vars = {
            "mode_var": tk.StringVar(value="RGB"),
            "name_var": tk.StringVar(value=str(default_name)[:MAX_NAME_CHARS]),
            "v1_var": tk.StringVar(value=""),
            "v2_var": tk.StringVar(value=""),
            "v3_var": tk.StringVar(value=""),
            "hex_var": tk.StringVar(value=""),
            "status_var": tk.StringVar(value="Enter a color value."),
            "limits_var": tk.StringVar(value=""),
            "example_var": tk.StringVar(value=""),
            "preview_hex_var": tk.StringVar(value="#D9D9D9"),
            "preview_rgb_var": tk.StringVar(value="—"),
            "preview_lab_var": tk.StringVar(value="—"),
            "evaluation_target_var": tk.StringVar(
                value=initial_evaluation_target if initial_evaluation_target in ("A", "B") else "B"),
        }

        state = {"suspend_validation": False, "previous_mode": "RGB"}

        style = ttk.Style(dialog)
        try:
            style.configure("CustomColor.TCombobox", padding=4)
            style.configure("CustomColor.Secondary.TButton", font=("Helvetica", 10), padding=(14, 8))
        except Exception:
            pass

        outer = tk.Frame(dialog, bg="#f5f6f8")
        outer.pack(fill="both", expand=True, padx=14, pady=14)

        panel = tk.Frame(outer, bg="white", highlightbackground="#d9dde3", highlightthickness=1)
        panel.pack(fill="both", expand=True)

        header = tk.Frame(panel, bg="#f6f7f9", height=58)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(
            header, text=title, font=("Sans", 13, "bold"), bg="#f6f7f9",
            fg="#222222", anchor="w", padx=16
        ).pack(side="left", fill="y")

        # The selected input mode already explains which formats are available.
        # Keep `subtitle` in the signature for compatibility with callers,
        # but do not repeat hard-coded mode names in the window header.

        body = tk.Frame(panel, bg="white")
        body.pack(fill="both", expand=True, padx=18, pady=14)
        body.grid_columnconfigure(0, weight=1, minsize=290)
        body.grid_columnconfigure(1, weight=0, minsize=14)
        body.grid_columnconfigure(2, weight=1, minsize=320)

        # Left side: preview and derived values
        left_panel = tk.Frame(body, bg="white")
        left_panel.grid(row=0, column=0, sticky="nsew")

        preview_card = tk.Frame(left_panel, bg="#fafafa", bd=1, relief="solid", width=285, height=255)
        preview_card.pack(fill="both", expand=True)
        preview_card.pack_propagate(False)

        tk.Label(
            preview_card, text="Color preview", bg="#fafafa", fg="#222222",
            font=("Sans", 10, "bold"), anchor="center", pady=8
        ).pack(fill="x")

        preview_canvas = tk.Canvas(
            preview_card, width=240, height=75, bg="#fafafa",
            highlightthickness=0, bd=0
        )
        preview_canvas.pack(fill="x", padx=12, pady=(0, 7))
        preview_rect = preview_canvas.create_rectangle(
            5, 6, 235, 69, fill="#d9d9d9", outline="#8c93a0", width=1
        )

        def _resize_preview(event):
            preview_canvas.coords(preview_rect, 5, 6, max(6, event.width - 5), max(7, event.height - 6))

        preview_canvas.bind("<Configure>", _resize_preview)

        # One centered two-column group: captions beside values, not stacked.
        values_block = tk.Frame(preview_card, bg="#fafafa")
        values_block.pack(anchor="center", pady=(2, 6))
        for row_index, (caption, variable) in enumerate((
            ("HEX", input_vars["preview_hex_var"]),
            ("RGB", input_vars["preview_rgb_var"]),
            ("CIELAB", input_vars["preview_lab_var"]),
        )):
            tk.Label(
                values_block, text=caption, bg="#fafafa", fg="#667085",
                font=("Segoe UI", 9, "bold"), anchor="e", width=7
            ).grid(row=row_index, column=0, sticky="e", padx=(0, 12), pady=4)
            tk.Label(
                values_block, textvariable=variable, bg="#fafafa", fg="#1f2937",
                font=("Consolas", 9), anchor="w", width=22
            ).grid(row=row_index, column=1, sticky="w", pady=4)

        # Separator
        separator = tk.Frame(body, bg="#dddddd", width=1)
        separator.grid(row=0, column=1, sticky="ns", padx=10)

        # Right side: editable fields
        right_panel = tk.Frame(body, bg="white")
        right_panel.grid(row=0, column=2, sticky="nsew")
        right_panel.grid_columnconfigure(1, weight=1)

        current_row = 0
        if require_name:
            tk.Label(right_panel, text="Granule name", bg="white", anchor="w", font=("Sans", 10, "bold")
                     ).grid(row=current_row, column=0, sticky="w", pady=(2, 10), padx=(0, 10))

            def _validate_name_length(proposed_text):
                return len(proposed_text) <= MAX_NAME_CHARS

            name_vcmd = (dialog.register(_validate_name_length), "%P")
            name_entry = tk.Entry(
                right_panel, textvariable=input_vars["name_var"], font=("Sans", 10),
                validate="key", validatecommand=name_vcmd, relief="solid", bd=1
            )
            name_entry.grid(row=current_row, column=1, sticky="ew", pady=(2, 10))
            current_row += 1

        tk.Label(right_panel, text="Input mode", bg="white", anchor="w", font=("Sans", 10, "bold")
                 ).grid(row=current_row, column=0, sticky="w", pady=(2, 10), padx=(0, 10))

        mode_holder = tk.Frame(right_panel, bg="white")
        mode_holder.grid(row=current_row, column=1, sticky="ew", pady=(2, 10))
        mode_holder.grid_columnconfigure(1, weight=1)
        mode_combo = UtilsTools.styled_combobox(
            mode_holder, textvariable=input_vars["mode_var"], state="readonly", width=10,
            values=["RGB", "LAB", "HEX"], style="CustomColor.TCombobox"
        )
        mode_combo.grid(row=0, column=0, sticky="w")
        pick_color_btn = tk.Button(
            mode_holder, text="Pick color...", font=("Segoe UI", 9, "bold"),
            bg=UtilsTools.UI_ACCENT_SOFT, fg=UtilsTools.UI_ACCENT,
            activebackground=UtilsTools.UI_ACCENT_HOVER,
            activeforeground=UtilsTools.UI_ACCENT_DARK,
            relief="flat", bd=0, highlightthickness=0,
            padx=12, pady=5, cursor="hand2",
        )
        pick_color_btn.grid(row=0, column=1, sticky="e")
        current_row += 1

        lbl1 = tk.Label(right_panel, text="R:", bg="white", anchor="w", font=("Sans", 10))
        entry1 = tk.Entry(right_panel, textvariable=input_vars["v1_var"], font=("Sans", 10), relief="solid", bd=1)
        lbl2 = tk.Label(right_panel, text="G:", bg="white", anchor="w", font=("Sans", 10))
        entry2 = tk.Entry(right_panel, textvariable=input_vars["v2_var"], font=("Sans", 10), relief="solid", bd=1)
        lbl3 = tk.Label(right_panel, text="B:", bg="white", anchor="w", font=("Sans", 10))
        entry3 = tk.Entry(right_panel, textvariable=input_vars["v3_var"], font=("Sans", 10), relief="solid", bd=1)
        hex_label = tk.Label(right_panel, text="HEX:", bg="white", anchor="w", font=("Sans", 10))
        hex_entry = tk.Entry(right_panel, textvariable=input_vars["hex_var"], font=("Sans", 10), relief="solid", bd=1)
        input_start_row = current_row

        hint_label = tk.Label(right_panel, textvariable=input_vars["limits_var"], bg="white", fg="#667085",
                              justify="center", anchor="center", wraplength=285, font=("Sans", 9))
        example_label = tk.Label(right_panel, textvariable=input_vars["example_var"], bg="white", fg="#8c8c8c",
                                 justify="center", anchor="center", wraplength=285, font=("Sans", 9, "italic"))

        if allow_evaluation_target:
            target_row = tk.Frame(panel, bg="white")
            target_row.pack(fill="x", padx=16, pady=(0, 5))
            tk.Label(target_row, text="Add color to:", bg="white", fg="#526074",
                     font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 8))
            for target in ("A", "B"):
                tk.Radiobutton(target_row, text=f"Sample {target}", value=target,
                               variable=input_vars["evaluation_target_var"],
                               bg="white", activebackground="white",
                               font=("Segoe UI", 9)).pack(side="left", padx=(0, 14))

        footer = tk.Frame(panel, bg="white")
        footer.pack(fill="x", padx=16, pady=(0, 14))

        status_label = tk.Label(
            footer, textvariable=input_vars["status_var"], bg="white", fg="#8a4f00",
            anchor="w", justify="left", wraplength=390, font=("Sans", 9, "italic")
        )
        status_label.pack(side="left", fill="x", expand=True)

        buttons_frame = tk.Frame(footer, bg="white")
        buttons_frame.pack(side="right")
        btn_cancel = tk.Button(
            buttons_frame, text="Cancel", command=dialog.destroy,
            font=("Segoe UI", 10), bg="#E8E9EC", fg="#263044",
            activebackground="#DDE0E5", relief="flat", bd=0,
            padx=16, pady=8, cursor="hand2",
        )
        btn_cancel.pack(side="left", padx=(0, 8))
        btn_submit = tk.Button(
            buttons_frame, text=submit_text, state="disabled",
            font=("Segoe UI", 10, "bold"),
            bg=UtilsTools.UI_ACCENT_SOFT, fg="white",
            activebackground=UtilsTools.UI_ACCENT_DARK,
            activeforeground="white", disabledforeground="#9b90a5",
            relief="flat", bd=0, highlightthickness=0,
            padx=16, pady=8, cursor="hand2",
        )
        btn_submit.pack(side="left")

        def _set_submit_enabled(enabled):
            btn_submit.configure(
                state="normal" if enabled else "disabled",
                bg=UtilsTools.UI_ACCENT if enabled else UtilsTools.UI_ACCENT_SOFT,
            )

        def _clear_numeric_fields():
            input_vars["v1_var"].set("")
            input_vars["v2_var"].set("")
            input_vars["v3_var"].set("")

        def _clear_hex_field():
            input_vars["hex_var"].set("")

        def _set_status(message, ok=False):
            input_vars["status_var"].set(message)
            status_label.configure(fg="#2d6a2d" if ok else "#8a4f00")

        def _reset_preview():
            preview_canvas.itemconfig(preview_rect, fill="#d9d9d9")
            input_vars["preview_hex_var"].set("#D9D9D9")
            input_vars["preview_rgb_var"].set("—")
            input_vars["preview_lab_var"].set("—")

        def _validate_name():
            if not require_name:
                return True, ""
            name = input_vars["name_var"].get().strip()
            if not name:
                return False, "Enter a color name."
            if len(name) > MAX_NAME_CHARS:
                return False, f"Color name must contain at most {MAX_NAME_CHARS} characters."
            return True, ""

        def _validate_live(*_):
            if state["suspend_validation"]:
                return
            name_ok, name_message = _validate_name()
            if not name_ok:
                _reset_preview()
                _set_status(name_message, ok=False)
                _set_submit_enabled(False)
                return
            mode = input_vars["mode_var"].get().strip().upper()
            ok, message, sample_lab, sample_rgb, _ = self._normalize_custom_color_input(
                input_mode=mode,
                value_1=input_vars["v1_var"].get(),
                value_2=input_vars["v2_var"].get(),
                value_3=input_vars["v3_var"].get(),
                hex_value=input_vars["hex_var"].get()
            )
            if ok and sample_rgb is not None:
                preview_hex = self.app._safe_hex_from_rgb(sample_rgb)
                preview_canvas.itemconfig(preview_rect, fill=preview_hex)
                input_vars["preview_hex_var"].set(preview_hex.upper())
                input_vars["preview_rgb_var"].set(", ".join(str(int(round(float(v)))) for v in sample_rgb[:3]))
                input_vars["preview_lab_var"].set(", ".join(f"{float(v):.2f}" for v in sample_lab[:3]))
                _set_status(message or "Valid color input.", ok=True)
                _set_submit_enabled(True)
            else:
                _reset_preview()
                _set_status(message or "Enter a valid color value.", ok=False)
                _set_submit_enabled(False)

        def _refresh_inputs(*_):
            mode = input_vars["mode_var"].get().strip().upper()
            previous = state.get("previous_mode", "RGB")
            previous_lab = previous_rgb = None
            if previous != mode:
                ok, _, previous_lab, previous_rgb, _ = self._normalize_custom_color_input(
                    input_mode=previous,
                    value_1=input_vars["v1_var"].get(),
                    value_2=input_vars["v2_var"].get(),
                    value_3=input_vars["v3_var"].get(),
                    hex_value=input_vars["hex_var"].get(),
                )
                if not ok:
                    previous_lab = previous_rgb = None
            state["suspend_validation"] = True
            try:
                state["previous_mode"] = mode
                help_data = self._get_custom_color_input_mode_help(mode)
                input_vars["limits_var"].set(help_data["limits"])
                input_vars["example_var"].set(help_data["example"])
                for widget in (lbl1, entry1, lbl2, entry2, lbl3, entry3, hex_label, hex_entry, hint_label, example_label):
                    try:
                        widget.grid_remove()
                    except Exception:
                        pass
                _clear_numeric_fields()
                _clear_hex_field()
                _reset_preview()
                _set_status("Enter a color value.", ok=False)
                _set_submit_enabled(False)
                if mode in ("RGB", "LAB"):
                    lbl1.config(text=f"{help_data['labels'][0]}:")
                    lbl2.config(text=f"{help_data['labels'][1]}:")
                    lbl3.config(text=f"{help_data['labels'][2]}:")
                    lbl1.grid(row=input_start_row, column=0, sticky="w", pady=5, padx=(0, 10))
                    entry1.grid(row=input_start_row, column=1, sticky="ew", pady=5)
                    lbl2.grid(row=input_start_row + 1, column=0, sticky="w", pady=5, padx=(0, 10))
                    entry2.grid(row=input_start_row + 1, column=1, sticky="ew", pady=5)
                    lbl3.grid(row=input_start_row + 2, column=0, sticky="w", pady=5, padx=(0, 10))
                    entry3.grid(row=input_start_row + 2, column=1, sticky="ew", pady=5)
                    dialog.after_idle(entry1.focus_set)
                    next_row = input_start_row + 3
                else:
                    hex_label.grid(row=input_start_row, column=0, sticky="w", pady=5, padx=(0, 10))
                    hex_entry.grid(row=input_start_row, column=1, sticky="ew", pady=5)
                    dialog.after_idle(hex_entry.focus_set)
                    next_row = input_start_row + 1
                hint_label.grid(row=next_row, column=0, columnspan=2, sticky="ew", pady=(12, 2))
                example_label.grid(row=next_row + 1, column=0, columnspan=2, sticky="ew", pady=(0, 2))
                if previous_lab is not None and previous_rgb is not None:
                    if mode == "LAB":
                        for variable, value in zip((input_vars["v1_var"], input_vars["v2_var"], input_vars["v3_var"]), previous_lab):
                            variable.set(f"{float(value):.15g}")
                    elif mode == "RGB":
                        for variable, value in zip((input_vars["v1_var"], input_vars["v2_var"], input_vars["v3_var"]), previous_rgb):
                            variable.set(str(int(round(float(value)))))
                    else:
                        input_vars["hex_var"].set(self.app._safe_hex_from_rgb(previous_rgb).upper())
            finally:
                state["suspend_validation"] = False
                _validate_live()

        def _submit():
            name_ok, name_message = _validate_name()
            if not name_ok:
                _set_status(name_message, ok=False)
                self.app.custom_warning("Invalid Color Name", name_message, parent=dialog)
                return
            ok, message, sample_lab, sample_rgb, sample_hex = self._normalize_custom_color_input(
                input_mode=input_vars["mode_var"].get(),
                value_1=input_vars["v1_var"].get(),
                value_2=input_vars["v2_var"].get(),
                value_3=input_vars["v3_var"].get(),
                hex_value=input_vars["hex_var"].get()
            )
            if not ok:
                _set_status(message, ok=False)
                self.app.custom_warning("Invalid Custom Color", message, parent=dialog)
                return
            color_name = input_vars["name_var"].get().strip() if require_name else default_name
            if callable(on_submit):
                on_submit(color_name, sample_lab, sample_rgb, sample_hex, dialog, input_vars)
            else:
                dialog.destroy()

        def _get_current_rgb_for_picker():
            mode = input_vars["mode_var"].get().strip().upper()
            ok, _, _, sample_rgb, _ = self._normalize_custom_color_input(
                input_mode=mode,
                value_1=input_vars["v1_var"].get(),
                value_2=input_vars["v2_var"].get(),
                value_3=input_vars["v3_var"].get(),
                hex_value=input_vars["hex_var"].get()
            )
            if ok and sample_rgb is not None:
                return sample_rgb
            return (217, 217, 217)

        def _open_picker():
            self._open_square_color_picker(parent=dialog, initial_rgb=_get_current_rgb_for_picker(), on_apply=_apply_picker_result)

        def _apply_picker_result(rgb, hex_value=None):
            state["suspend_validation"] = True
            try:
                self._fill_custom_color_dialog_from_rgb(input_vars, rgb)
            finally:
                state["suspend_validation"] = False
                dialog.after_idle(_validate_live)

        pick_color_btn.configure(command=_open_picker)
        btn_submit.configure(command=_submit)
        mode_combo.bind("<<ComboboxSelected>>", _refresh_inputs)
        for var_name in ("v1_var", "v2_var", "v3_var", "hex_var", "name_var"):
            input_vars[var_name].trace_add("write", _validate_live)
        dialog.bind("<Return>", lambda e: btn_submit.invoke() if str(btn_submit["state"]) == "normal" else None)
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        _refresh_inputs()
        if initial_lab is not None:
            try:
                values = np.asarray(initial_lab, dtype=float).reshape(3)
                input_vars["mode_var"].set("LAB")
                _refresh_inputs()
                for variable, value in zip((input_vars["v1_var"], input_vars["v2_var"], input_vars["v3_var"]), values):
                    variable.set(f"{float(value):.15g}")
                _validate_live()
            except (ValueError, TypeError):
                pass
        dialog.deiconify()
        dialog.grab_set()
        return dialog

    def _submit_custom_color_input(self, vars_dict, input_vars, dialog):
        """Validate the custom color input and use it as comparison color."""
        ok, message, sample_lab, sample_rgb, sample_hex = self._normalize_custom_color_input(
            input_mode=input_vars["mode_var"].get(),
            value_1=input_vars["v1_var"].get(),
            value_2=input_vars["v2_var"].get(),
            value_3=input_vars["v3_var"].get(),
            hex_value=input_vars["hex_var"].get()
        )

        if not ok:
            input_vars["status_var"].set(message)

            self.app.custom_warning(
                "Invalid Custom Color",
                message,
                parent=dialog
            )
            return

        # RGB/HEX evaluation must use the same conversion as image mapping.
        if input_vars["mode_var"].get().strip().upper() in ("RGB", "HEX"):
            sample_lab = UtilsTools.safe_lab_tuple(UtilsTools.analysis_rgb_to_lab(sample_rgb))
        dialog.destroy()

        self._set_custom_color_as_evaluation_comparison(
            vars_dict=vars_dict,
            sample_lab=sample_lab,
            sample_rgb=sample_rgb,
            sample_hex=sample_hex,
            source="custom RGB" if input_vars["mode_var"].get().strip().upper() in ("RGB","HEX") else "custom"
        )

    def _fill_custom_color_dialog_from_rgb(self, input_vars, rgb):
        """
        Fill the reusable custom color dialog from a selected RGB color.

        If current input mode is:
        - RGB: fills R, G, B
        - LAB: converts RGB to LAB and fills L, a, b
        - HEX: fills HEX
        """
        mode = input_vars["mode_var"].get().strip().upper()

        r, g, b = UtilsTools.safe_rgb_tuple(rgb)

        if mode == "RGB":
            input_vars["v1_var"].set(str(r))
            input_vars["v2_var"].set(str(g))
            input_vars["v3_var"].set(str(b))
            input_vars["hex_var"].set("")

        elif mode == "LAB":
            lab = UtilsTools.analysis_rgb_to_lab((r, g, b))
            L, a, b_lab = lab

            input_vars["v1_var"].set(f"{float(L):.2f}")
            input_vars["v2_var"].set(f"{float(a):.2f}")
            input_vars["v3_var"].set(f"{float(b_lab):.2f}")
            input_vars["hex_var"].set("")

        else:
            input_vars["hex_var"].set(UtilsTools.rgb_to_hex((r, g, b)).upper())
            input_vars["v1_var"].set("")
            input_vars["v2_var"].set("")
            input_vars["v3_var"].set("")

    def _open_square_color_picker(
        self, parent, initial_rgb=(217, 217, 217), on_apply=None,
        *, initial_lab=None, granule_name=None, on_granule_submit=None,
        submit_text=None, title=None, initial_mode=None,
    ):
        """Compatibility entry-point; shared UI lives in UtilsTools."""
        return UtilsTools.open_square_color_picker(
            self.app, parent, initial_rgb=initial_rgb, on_apply=on_apply,
            initial_lab=initial_lab, granule_name=granule_name,
            on_granule_submit=on_granule_submit, submit_text=submit_text,
            title=title, initial_mode=initial_mode,
        )

    def _update_color_evaluation_conversion_inspector(
        self,
        vars_dict,
        lab=None,
        rgb=None,
        hex_color=None,
        name="Color",
        source="-"
    ):
        """
        Update the Color Inspector.

        There may be two synchronized inspector cards:
        - left inspector for custom/sample mode;
        - full-width inspector for single/prototype-prototype mode.
        """
        def _set_all_preview_colors(fill_color):
            preview_refs = vars_dict.get("inspector_previews")

            if preview_refs:
                for canvas, rect in preview_refs:
                    try:
                        canvas.itemconfig(rect, fill=fill_color)
                    except Exception:
                        pass
                return

            try:
                vars_dict["inspector_preview"].itemconfig(
                    vars_dict["inspector_preview_rect"],
                    fill=fill_color
                )
            except Exception:
                pass

        def _reset_inspector(source_text="-"):
            vars_dict["inspector_title_var"].set("Color Inspector")
            vars_dict["inspector_source_var"].set(f"Source: {source_text}")

            vars_dict["inspector_lab_var"].set("-")
            vars_dict["inspector_rgb_var"].set("-")
            vars_dict["inspector_hex_var"].set("-")
            vars_dict["inspector_luv_var"].set("-")
            vars_dict["inspector_lch_var"].set("-")
            vars_dict["inspector_cie1931_var"].set("-")

            _set_all_preview_colors("#d9d9d9")

        try:
            if lab is None and rgb is None:
                _reset_inspector("-")
                return

            if lab is None and rgb is not None:
                rgb = UtilsTools.safe_rgb_tuple(rgb)
                lab = UtilsTools.analysis_rgb_to_lab(rgb)

            if rgb is None and lab is not None:
                rgb = UtilsTools.lab_to_rgb(lab)

            rgb = UtilsTools.safe_rgb_tuple(rgb)
            lab = UtilsTools.safe_lab_tuple(lab)

            if hex_color is None:
                hex_color = UtilsTools.rgb_to_hex(rgb)

            hex_color = str(hex_color).upper()

            if not hex_color.startswith("#"):
                hex_color = "#" + hex_color

            display_name = str(name).strip() if name else "Color"
            display_source = str(source).strip() if source else "-"

            vars_dict["inspector_title_var"].set(f"Color Inspector · {display_name}")
            vars_dict["inspector_source_var"].set(f"Source: {display_source}")

            vars_dict["inspector_lab_var"].set(
                UtilsTools.format_lab_color_value(lab, "CIELAB")
            )
            vars_dict["inspector_rgb_var"].set(
                f"{rgb[0]}, {rgb[1]}, {rgb[2]}"
            )
            vars_dict["inspector_hex_var"].set(
                hex_color
            )
            vars_dict["inspector_luv_var"].set(
                UtilsTools.format_lab_color_value(lab, "CIELUV")
            )
            vars_dict["inspector_lch_var"].set(
                UtilsTools.format_lab_color_value(lab, "LCh")
            )
            vars_dict["inspector_cie1931_var"].set(
                UtilsTools.format_lab_color_value(lab, "CIE1931")
            )

            _set_all_preview_colors(hex_color)

        except Exception:
            _reset_inspector("error")

    def _get_active_color_evaluation_sample(self, vars_dict):
        """
        Compatibility wrapper. Logic lives in ColorEvaluationManager.
        """
        manager = self.app._get_color_evaluation_manager()
        return manager.get_active_color_evaluation_sample(vars_dict)

    def _classify_for_active_thresholds(self, metric_value):
        """
        Classify the active scalar metric value using the active threshold configuration.
        """
        manager = self.app._get_color_evaluation_manager()
        result = manager.classify_metric_value(
            value=metric_value,
            threshold_settings=self.app.threshold_settings,
        )
        return result.get("class_label", "Unavailable"), result.get("class_order", 9)

    def _show_color_evaluation_closest_prototypes(self, vars_dict):
        """
        Rank the 7 closest loaded prototypes using the active metric against the active custom color.
        """
        manager = self.app._get_color_evaluation_manager()

        sample = next((row for row in (
            self._get_color_evaluation_side_sample(vars_dict, "B"),
            self._get_color_evaluation_side_sample(vars_dict, "A"))
                       if row is not None and not row.get("row_label")), None)
        sample_lab = sample["lab"] if sample else None
        sample_rgb = sample["rgb"] if sample else None
        sample_hex = sample["hex"] if sample else None
        sample_name = sample["name"] if sample else "Custom Color"

        metric_name = self.app.threshold_settings.get("metric", "CIEDE2000")
        vars_dict["analysis_view_mode"] = "closest"

        if (
            sample is None
            or sample_lab is None
            or sample_rgb is None
            or sample_hex is None
        ):
            self._update_color_evaluation_result_card(
                vars_dict=vars_dict,
                title="Custom color required.",
                detail="",
                summary=(
                    "Use 'Evaluate custom color' or 'Sample from image' first. "
                    "The closest-prototype search only works with a custom color."
                ),
                status="unavailable"
            )
            self._update_color_evaluation_membership_panel(vars_dict, sample_lab=None)
            return

        rows = self._extract_color_space_rows(vars_dict.get("loaded_space_data") or {})

        if not rows:
            self._update_color_evaluation_result_card(
                vars_dict=vars_dict,
                title="No prototypes available.",
                detail="",
                summary="Load a valid color space before using closest-prototype mode.",
                status="unavailable"
            )
            return

        vars_dict["evaluation_membership_side"] = "B" if (self._get_color_evaluation_side_sample(vars_dict,"B") or {}).get("row_label") is None and vars_dict.get("secondary_mode")=="custom" else "A"
        top_7 = manager.rank_closest_prototypes(
            sample_lab=sample_lab,
            color_rows=rows,
            metric=metric_name,
            threshold_settings=self.app.threshold_settings,
            top_n=7,
            fuzzy_color_space=vars_dict.get("loaded_fuzzy_color_space"),
        )

        if not top_7:
            self._update_color_evaluation_result_card(
                vars_dict=vars_dict,
                title="Closest prototype not available.",
                detail="",
                summary="Could not compute color-difference values for the loaded prototypes.",
                status="unavailable"
            )
            return

        best = top_7[0]

        vars_dict["closest_ranking"] = top_7
        vars_dict["closest_best"] = best
        vars_dict["closest_metric"] = metric_name

        summary = manager.format_closest_ranking_summary(
            ranking=top_7,
            metric_name=metric_name,
            threshold_settings=self.app.threshold_settings,
            include_threshold_description=False
        )

        status = manager.status_from_class_order(best.get("class_order", 9))

        self._update_color_evaluation_result_card(
            vars_dict=vars_dict,
            title=(f"Closest category: {best['label']} · {best.get('granule_label', best['label'])}"
                   if isinstance(vars_dict.get("loaded_fuzzy_color_space"), GranularFuzzyColorSpace)
                   else f"Closest prototype: {best['label']}"),
            detail=f"Minimum {metric_name} = {best.get('metric_value', best['delta_e']):.3f}",
            summary=summary,
            status=status
        )

        self._update_color_evaluation_membership_panel(
            vars_dict,
            sample_lab=sample_lab, sample=sample
        )

        self._update_color_evaluation_conversion_inspector(
            vars_dict=vars_dict,
            lab=sample_lab,
            rgb=sample_rgb,
            hex_color=sample_hex,
            name=sample_name,
            source="custom"
        )

    def _normalize_custom_color_input(self, input_mode, value_1="", value_2="", value_3="", hex_value=""):
        """
        Compatibility wrapper. Logic lives in ColorEvaluationManager.
        """
        manager = self.app._get_color_evaluation_manager()

        return manager.normalize_custom_color_input(
            input_mode=input_mode,
            value_1=value_1,
            value_2=value_2,
            value_3=value_3,
            hex_value=hex_value,
            utils_tools=UtilsTools,
        )

    def _get_color_evaluation_volume_limits(self, vars_dict):
        """
        Compatibility wrapper. Logic lives in ColorEvaluationManager.
        """
        manager = self.app._get_color_evaluation_manager()

        space=vars_dict.get("loaded_fuzzy_color_space")
        limits=(ReferenceDomain.default_voronoi_reference_domain()
                if space is not None and space.color_space == "RGB"
                else getattr(self.app, "volume_limits", None))
        return manager.resolve_volume_limits(
            volume_limits=limits,
            fuzzy_color_space=space,
        )

    def _get_color_evaluation_plot_context(
        self,
        vars_dict,
        require_custom=False,
        require_closest=False
    ):
        """
        Build a shared context for all Color Evaluation plots.

        Works with or without custom/sample color.

        Parameters
        ----------
        require_custom : bool
            True when the plot needs a custom/sample color.
        require_closest : bool
            True when the plot needs closest-prototype ranking.
        """
        sample = next((row for row in (
            self._get_color_evaluation_side_sample(vars_dict, "B"),
            self._get_color_evaluation_side_sample(vars_dict, "A"))
                       if row is not None and not row.get("row_label")), None)
        sample_lab = sample["lab"] if sample else None
        sample_rgb = sample["rgb"] if sample else None
        sample_hex = sample["hex"] if sample else None
        has_custom = sample is not None

        if require_custom and not has_custom:
            self.app.custom_warning(
                "Custom Color Required",
                "Use 'Evaluate custom color' or 'Sample from image' first.",
                parent=getattr(self, "_color_evaluation_window", None)
            )
            return None

        data_source = vars_dict.get("loaded_space_data") or {}
        rows = self._extract_color_space_rows(data_source)

        if not rows:
            self.app.custom_warning(
                "No Color Space",
                "Load a valid color space first.",
                parent=getattr(self, "_color_evaluation_window", None)
            )
            return None

        if require_closest:
            if not has_custom:
                self.app.custom_warning(
                    "Custom Color Required",
                    "Closest-prototype plots require a custom or sampled color.",
                    parent=getattr(self, "_color_evaluation_window", None)
                )
                return None

            if not vars_dict.get("closest_ranking"):
                self._show_color_evaluation_closest_prototypes(vars_dict)

        color_data = {}
        hex_color = {}

        loaded_space = vars_dict.get("loaded_fuzzy_color_space")
        display_groups = self._color_evaluation_actual_entries(data_source, loaded_space)
        for _, entries in display_groups:
            for label, lab in entries:
                try:
                    lab_arr = np.asarray(lab, dtype=float).reshape(-1)[:3]
                    color_data[label] = {"positive_prototype": lab_arr}
                    hex_color[UtilsTools.lab_to_hex(lab_arr)] = lab_arr
                except (TypeError, ValueError):
                    continue

        core = vars_dict.get("loaded_cores")
        alpha = vars_dict.get("loaded_prototypes")
        support = vars_dict.get("loaded_supports")
        loaded_space = vars_dict.get("loaded_fuzzy_color_space")
        if isinstance(loaded_space, GranularFuzzyColorSpace):
            core = loaded_space.get_all_cores()
            alpha = loaded_space.get_all_prototypes()
            support = loaded_space.get_all_supports()

        volume_limits = self._get_color_evaluation_volume_limits(vars_dict)

        closest_best = vars_dict.get("closest_best")
        closest_label = None
        closest_lab = None
        closest_hex = None

        if closest_best:
            closest_label = closest_best.get("label")
            if isinstance(loaded_space, GranularFuzzyColorSpace) and closest_best.get("granule_lab") is not None:
                closest_lab = np.asarray(closest_best["granule_lab"], dtype=float)
                closest_label = closest_best.get("granule_label", closest_label)
                closest_hex = UtilsTools.lab_to_hex(closest_lab)

            for label, lab in rows:
                if closest_lab is not None:
                    break
                if str(label) == str(closest_label):
                    closest_lab = np.asarray(lab, dtype=float).reshape(-1)[:3]
                    closest_hex = self._get_evaluation_proto_hex(vars_dict, label)
                    break

        filename = (
            vars_dict.get("loaded_space_name")
            or vars_dict["space_name_var"].get()
            or "Color Space Evaluation"
        )

        metric_name = (
            vars_dict.get("closest_metric")
            or self.app.threshold_settings.get("metric", "CIEDE2000")
        )

        return {
            "filename": filename,
            "color_data": color_data,
            "core": core,
            "alpha": alpha,
            "support": support,
            "volume_limits": volume_limits,
            "hex_color": hex_color,

            "custom_lab": sample_lab if has_custom else None,
            "custom_rgb": sample_rgb if has_custom else None,
            "custom_hex": sample_hex if has_custom else None,

            "closest_label": closest_label,
            "closest_lab": closest_lab,
            "closest_hex": closest_hex,

            "ranking": vars_dict.get("closest_ranking") or [],
            "metric_name": metric_name,
        }

    def _open_color_evaluation_3d_plot(self, vars_dict):
        """
        Open Plotly 3D LAB visualization.
        Works with or without custom/sample color.
        """
        ctx = self._get_color_evaluation_plot_context(
            vars_dict,
            require_custom=False,
            require_closest=False
        )

        if ctx is None:
            return

        space = vars_dict.get("loaded_fuzzy_color_space")
        mode = space.color_space if space is not None else "LAB"
        points = ctx["color_data"]
        hex_points = ctx["hex_color"]
        if isinstance(space, GranularFuzzyColorSpace):
            points = {}
            hex_points = {}
            for category in space.categories:
                for proto in category.prototypes:
                    lab = np.asarray(space.lab_from_model(proto.positive), dtype=float)
                    points[proto.label] = {"positive_prototype": lab}
                    hex_points[UtilsTools.lab_to_hex(lab)] = lab
        custom = ctx.get("custom_lab")
        closest = ctx.get("closest_lab")
        limits = ctx["volume_limits"]
        if mode == "RGB":
            native = {p.label:p.positive for p in (space.get_all_prototypes() if getattr(space,"is_granular",False) else space.prototypes)}
            points = {k:{**v,"positive_prototype":native[k] if k in native else space.model_from_lab(v["positive_prototype"])}
                      for k,v in points.items()}
            hex_points = {self.app._safe_hex_from_rgb(tuple(int(round(x)) for x in xyz)):xyz for xyz in native.values()}
            sample=next((x for x in (self._get_color_evaluation_side_sample(vars_dict,"B"),self._get_color_evaluation_side_sample(vars_dict,"A")) if x and not x.get("row_label")),None)
            custom = (sample["rgb"] if sample and sample.get("source") in ("image pixel","custom RGB") else space.model_from_lab(custom)) if custom is not None else None
            closest = (native[ctx["closest_label"]] if ctx.get("closest_label") in native else space.model_from_lab(closest)) if closest is not None else None
            limits = space.reference_domain
        # Reuse Model 3D's browser tree rather than its old flat Plotly legend.
        color_tree = {"roots": [["granule", name] for name in points], "children": {}}
        granular_categories = None
        if isinstance(space, GranularFuzzyColorSpace):
            color_tree = {"roots": [["category", name] for name in space.get_root_categories()],
                          "children": {name: list(space.get_category_children(name))
                                       for name in space.get_all_category_labels()}}
            granular_categories = {}
            for category in space.categories:
                for proto in category.prototypes:
                    granular_categories[proto.label] = category.label
        fig = VisualManager.plot_more_combined_3D(
            filename=ctx["filename"], color_data=points,
            core=ctx["core"], alpha=ctx["alpha"], support=ctx["support"],
            volume_limits=limits, hex_color=hex_points,
            selected_options=["Representative"],
            custom_lab=custom, custom_hex=ctx.get("custom_hex", "#ff0000"),
            closest_label=ctx.get("closest_label"), closest_lab=closest,
            closest_hex=ctx.get("closest_hex", "#000000"),
            color_space=mode, granule_categories=granular_categories,
        )

        self._show_color_eval_plotly_figure_in_browser(
            fig,
            filename_prefix="color_eval_3d_lab", color_tree=color_tree
        )

    def _open_color_evaluation_ab_plot(self, vars_dict):
        """
        Open 2D a*b* projection.
        Works with or without custom/sample color.
        """
        ctx = self._get_color_evaluation_plot_context(
            vars_dict,
            require_custom=False,
            require_closest=False
        )

        if ctx is None:
            return

        fig = VisualManager.plot_color_evaluation_ab_projection(
            color_data=ctx["color_data"],
            hex_color=ctx["hex_color"],
            custom_lab=ctx["custom_lab"],
            custom_hex=ctx["custom_hex"],
            closest_label=ctx["closest_label"],
            closest_lab=ctx["closest_lab"],
            closest_hex=ctx["closest_hex"],
            filename=ctx["filename"],
        )

        self._show_color_eval_plotly_figure_in_browser(
            fig,
            filename_prefix="color_eval_ab_projection"
        )

    def _open_color_evaluation_lc_plot(self, vars_dict):
        """
        Open L*C* projection.
        Works with or without custom/sample color.
        """
        ctx = self._get_color_evaluation_plot_context(
            vars_dict,
            require_custom=False,
            require_closest=False
        )

        if ctx is None:
            return

        fig = VisualManager.plot_color_evaluation_lc_projection(
            color_data=ctx["color_data"],
            hex_color=ctx["hex_color"],
            custom_lab=ctx["custom_lab"],
            custom_hex=ctx["custom_hex"],
            closest_label=ctx["closest_label"],
            closest_lab=ctx["closest_lab"],
            closest_hex=ctx["closest_hex"],
            filename=ctx["filename"],
        )

        self._show_color_eval_plotly_figure_in_browser(
            fig,
            filename_prefix="color_eval_lc_projection"
        )

    def _open_color_evaluation_lch_plot(self, vars_dict):
        """
        Open polar LCh hue/chroma plot.
        Works with or without custom/sample color.
        """
        ctx = self._get_color_evaluation_plot_context(
            vars_dict,
            require_custom=False,
            require_closest=False
        )

        if ctx is None:
            return

        fig = VisualManager.plot_color_evaluation_lch_polar(
            color_data=ctx["color_data"],
            hex_color=ctx["hex_color"],
            custom_lab=ctx["custom_lab"],
            custom_hex=ctx["custom_hex"],
            closest_label=ctx["closest_label"],
            closest_lab=ctx["closest_lab"],
            closest_hex=ctx["closest_hex"],
            filename=ctx["filename"],
        )

        self._show_color_eval_plotly_figure_in_browser(
            fig,
            filename_prefix="color_eval_lch_polar"
        )

    def _open_color_evaluation_top7_plot(self, vars_dict):
        """
        Open horizontal bar chart with the 7 closest prototypes.
        Requires custom/sample color.
        """
        ctx = self._get_color_evaluation_plot_context(
            vars_dict,
            require_custom=True,
            require_closest=True
        )

        if ctx is None:
            return

        ranking = ctx.get("ranking") or []

        if not ranking:
            self.app.custom_warning(
                "Ranking Not Available",
                "Could not compute the closest prototypes.",
                parent=getattr(self, "_color_evaluation_window", None)
            )
            return

        fig = VisualManager.plot_color_evaluation_top7_bar(
            ranking=ranking,
            metric_name=ctx["metric_name"],
            title=f"Top 7 closest {'root categories' if getattr(vars_dict.get('loaded_fuzzy_color_space'),'is_granular',False) else 'prototypes'} | {ctx['metric_name']}",
            threshold_settings=self.app.threshold_settings,
        )

        self._show_color_eval_plotly_figure_in_browser(
            fig,
            filename_prefix="color_eval_top7"
        )

    def _open_color_evaluation_membership_plot(self, vars_dict):
        """Bar chart for the active external sample, on either side A or B."""
        sample = next((color for color in (
            self._get_color_evaluation_side_sample(vars_dict, "B"),
            self._get_color_evaluation_side_sample(vars_dict, "A"))
                       if color is not None and not color.get("row_label")), None)
        if sample is None:
            self.app.custom_warning("Custom Color Required",
                                "Add a custom or image sample to A or B first.",
                                parent=getattr(self, "_color_evaluation_window", None))
            return
        memberships = self._calculate_evaluation_memberships(vars_dict, sample["lab"], sample)
        if not memberships:
            self.app.custom_warning("Memberships Not Available",
                                "No fuzzy membership data are available for this sample.",
                                parent=getattr(self, "_color_evaluation_window", None))
            return
        fig = VisualManager.plot_color_evaluation_membership_bar(
            memberships=memberships,
            title=f"Root category membership degrees | {sample['name']}", top_n=10)
        self._show_color_eval_plotly_figure_in_browser(
            fig, filename_prefix="color_eval_memberships")

    def _open_color_evaluation_component_plot(self, vars_dict):
        """Graph signed LAB/LCh components between any actual colors A and B."""
        first = self._get_color_evaluation_side_sample(vars_dict, "A")
        second = self._get_color_evaluation_side_sample(vars_dict, "B")
        if first is None or second is None:
            self.app.custom_warning("Comparison Required",
                                "Select both a color A and a color B first.",
                                parent=getattr(self, "_color_evaluation_window", None))
            return
        components = self._calculate_color_evaluation_component_differences(
            first["lab"], second["lab"])
        fig = VisualManager.plot_color_evaluation_component_differences(
            components=components,
            title=f"Component differences | {first['name']} vs {second['name']}")
        self._show_color_eval_plotly_figure_in_browser(
            fig, filename_prefix="color_eval_components")

    def _calculate_color_evaluation_component_differences(self, lab_1, lab_2):
        """
        Compatibility wrapper. Logic lives in ColorEvaluationManager.
        """
        manager = self.app._get_color_evaluation_manager()
        return manager.calculate_visual_component_differences(lab_1, lab_2)

    def _show_color_eval_plotly_figure_in_browser(
        self,
        fig,
        filename_prefix="color_eval_plot", color_tree=None
    ):
        """
        Open a Color Evaluation Plotly figure in the default browser.
        """
        self.app._open_plotly_figure_in_browser(
            fig,
            filename_prefix=filename_prefix, color_tree=color_tree
        )

    def _get_color_evaluation_available_graph_keys(self, vars_dict):
        """
        Return the graph buttons that should be visible according to the current state.
        The state logic lives in ColorEvaluationManager; the GUI only filters by available openers.
        """
        manager = self.app._get_color_evaluation_manager()

        data_source = vars_dict.get("loaded_space_data") or {}
        rows = self._extract_color_space_rows(data_source)

        secondary_mode = vars_dict.get("secondary_mode")
        has_primary = self._get_color_evaluation_side_sample(vars_dict, "A") is not None

        has_custom = any(
            vars_dict.get(prefix + "_mode") == "custom"
            and vars_dict.get(prefix + "_custom_lab") is not None
            for prefix in ("primary", "secondary")
        )
        if secondary_mode is None and has_custom:
            secondary_mode = "custom"

        available = manager.get_color_evaluation_available_graph_keys(
            rows=rows,
            secondary_mode=secondary_mode,
            has_primary=has_primary,
            secondary_label_available=vars_dict.get("secondary_label") is not None,
            has_custom=has_custom,
            has_fuzzy_color_space=vars_dict.get("loaded_fuzzy_color_space") is not None,
        )
        # A single external sample is enough for ranking/memberships, but not
        # for a component-difference graph, which always requires two colors.
        if self._get_color_evaluation_side_sample(vars_dict, "B") is None:
            available = [key for key in available if key != "components"]

        method_map = {
            "3d": "_open_color_evaluation_3d_plot",
            "ab": "_open_color_evaluation_ab_plot",
            "lc": "_open_color_evaluation_lc_plot",
            "lch": "_open_color_evaluation_lch_plot",
            "top7": "_open_color_evaluation_top7_plot",
            "memberships": "_open_color_evaluation_membership_plot",
            "components": "_open_color_evaluation_component_plot",
        }

        return [
            key
            for key in available
            if callable(getattr(self, method_map.get(key, ""), None))
        ]

    def _create_color_evaluation_graph_buttons_card(self, parent, vars_dict):
        """
        Create a compact Graphs card.

        The card is shown in the right-side analysis column.
        The actual buttons are rebuilt dynamically by
        _update_color_evaluation_graph_buttons() so the layout can change:
        - one column for single color / prototype-prototype comparison;
        - two columns for custom/sample color mode.
        """
        graph_buttons_card = tk.Frame(
            parent,
            bg="#fafafa",
            bd=1,
            relief="solid"
        )

        tk.Label(
            graph_buttons_card,
            text="Graphs",
            font=("Sans", 9, "bold"),
            anchor="w",
            bg="#fafafa",
            padx=8,
            pady=4
        ).pack(fill="x")

        graph_buttons_body = tk.Frame(
            graph_buttons_card,
            bg="#fafafa"
        )
        graph_buttons_body.pack(
            fill="x",
            padx=8,
            pady=(0, 8)
        )

        graph_specs = {
            "3d": {
                "text": "3D LAB",
                "command": lambda: self._open_color_evaluation_3d_plot(vars_dict)
            },
            "ab": {
                "text": "a*b*",
                "command": lambda: self._open_color_evaluation_ab_plot(vars_dict)
            },
            "lc": {
                "text": "L*C*",
                "command": lambda: self._open_color_evaluation_lc_plot(vars_dict)
            },
            "lch": {
                "text": "LCh",
                "command": lambda: self._open_color_evaluation_lch_plot(vars_dict)
            },
            "top7": {
                "text": "Top 7",
                "command": lambda: self._open_color_evaluation_top7_plot(vars_dict)
            },
            "memberships": {
                "text": "Memberships",
                "command": lambda: self._open_color_evaluation_membership_plot(vars_dict)
            },
            "components": {
                "text": "Components Δ",
                "command": lambda: self._open_color_evaluation_component_plot(vars_dict)
            },
        }

        graph_buttons_card._pyfcs_graph_body = graph_buttons_body
        graph_buttons_card._pyfcs_graph_specs = graph_specs

        return graph_buttons_card

    def _update_color_evaluation_graph_buttons(self, vars_dict):
        """Display available graphs in a wide, responsive horizontal toolbar."""
        refs = vars_dict.get("analysis_result_refs", {})
        side_card = refs.get("graph_buttons_card")
        results_columns = refs.get("results_columns")
        membership_right = refs.get("membership_right")
        if side_card is None:
            return
        body = getattr(side_card, "_pyfcs_graph_body", None)
        specs = getattr(side_card, "_pyfcs_graph_specs", {})
        if body is None:
            return

        has_custom = any(
            vars_dict.get(prefix + "_mode") == "custom"
            and vars_dict.get(prefix + "_custom_lab") is not None
            for prefix in ("primary", "secondary")
        )
        try:
            if results_columns is not None:
                results_columns.grid_columnconfigure(1, minsize=280 if has_custom else 0,
                                                     weight=0)
            if membership_right is not None:
                membership_right.configure(width=280)
        except tk.TclError:
            pass

        available = self._get_color_evaluation_available_graph_keys(vars_dict)
        for child in body.winfo_children():
            child.destroy()
        if not available:
            side_card.pack_forget()
            return
        if not side_card.winfo_manager():
            side_card.pack(fill="x", pady=(8, 0))

        # 3D LAB / a*b* / L*C* / LCh are always available; additional analyses
        # appear below only when their prerequisites are satisfied.
        ordered = [key for key in ("3d", "ab", "lc", "lch", "top7", "memberships", "components")
                   if key in available and key in specs]
        for offset in range(0, len(ordered), 4):
            row = tk.Frame(body, bg="#fafafa")
            row.pack(fill="x", pady=(0, 5 if offset + 4 < len(ordered) else 0))
            for key in ordered[offset:offset + 4]:
                spec = specs[key]
                tk.Button(
                    row, text=spec["text"], command=spec["command"],
                    font=("Segoe UI", 9), bg="#f8fafc", fg="#253044",
                    relief="solid", bd=1, pady=5, cursor="hand2",
                    activebackground=UtilsTools.UI_ACCENT_SOFT
                ).pack(side="left", fill="x", expand=True, padx=3)


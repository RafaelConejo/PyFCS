
"""Run the complete PyFCS regression suite and save its results.

From the project root:
    python -m Source.test.run_full_suite
    python -m Source.test.run_full_suite --gui

All test_*.py modules are discovered recursively in packages.
Research experiments and manual scripts are not executed. The optional --gui flag
checks the Tkinter creation dialog, Model 3D, Image Display and Color Evaluation controllers; a display is required.
"""

import argparse
import json
import os
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path


# Resolve project and test directories independently of the launch location.
ROOT = Path(__file__).resolve().parents[2]
TESTS = Path(__file__).resolve().parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Use a non-interactive Matplotlib backend unless another is explicitly set.
os.environ.setdefault("MPLBACKEND", "Agg")


class Tee:
    """Write test output to the terminal and log file simultaneously."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for stream in self.streams:
            stream.write(data)
        return len(data)

    def flush(self):
        for stream in self.streams:
            stream.flush()


def optional_gui_smoke():
    """Verify the default settings and configuration of the creation dialog."""
    import tkinter as tk
    from Source.interface.modules.common.UtilsTools import FCSCreationDialog

    # The root window remains hidden; the dialog is closed after validation.
    root = tk.Tk()
    root.withdraw()

    try:
        dialog = FCSCreationDialog(
            root,
            {"Red": (45., 60., 35.), "Blue": (45., 10., -45.)},
            lambda name, options: None,
        )

        try:
            # Check the initial geometry and the non-covering sampling options.
            assert dialog.mode_var.get() == "LAB", "Geometry must start in LAB"
            assert dialog.disjoint_var.get() and dialog.covering_var.get()

            dialog.disjoint_var.set(True)
            dialog.covering_var.set(False)
            dialog._update_typology()

            assert dialog.samples_var.get() == "27", "Non-Covering default must be 27"

            dialog.name_var.set("GlobalGuiTest")
            name, opts = dialog.build_options()

            assert name == "GlobalGuiTest"
            assert opts["disjoint"] and not opts["covering"]
            assert opts["samples"] == 27

        finally:
            if dialog.winfo_exists():
                dialog.cancel()

        root.update_idletasks()

    finally:
        root.destroy()


def optional_model3d_gui_smoke():
    """Exercise the extracted controller through the real desktop widgets."""
    import tempfile
    import time
    import tkinter as tk
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import patch

    from PIL import Image
    from Source.interface.mainInterface import PyFCSApp
    from Source.interface.modules.visualization.Model3DManager import Model3DManager
    from Source.interface.modules.visualization.VisualManager import VisualManager
    from Source.fuzzy.FuzzyColorSpaceBuilder import FuzzyColorSpaceBuilder
    from Source.input_output.InputJSON import InputJSON
    from Source.test.test_core_regressions import PreJavaAuditTests

    root = tk.Tk()
    app = PyFCSApp(root)
    manager = app.model_3d
    errors = []
    root.report_callback_exception = lambda typ, exc, tb: errors.append(repr(exc))
    app.custom_warning = lambda *a, **kw: errors.append(str(a))

    def until(predicate, seconds=20):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            root.update()
            if errors:
                raise AssertionError(errors)
            if predicate():
                return
            time.sleep(.015)
        raise AssertionError("Model 3D GUI operation timed out")

    def load(filename):
        completed = []
        assert app.load_color_space(str(filename), on_success=lambda *a: completed.append(True))
        until(lambda: completed and manager._model_3d_surface_job is None)
        assert manager._last_plot_signature is not None

    def layers(*active):
        for name, var in manager.model_3d_options.items():
            var.set(name in active)
        app.on_option_select()
        until(lambda: manager._model_3d_surface_job is None and manager._last_plot_signature is not None)
        assert manager._last_plot_signature[3] == active or set(manager._last_plot_signature[3]) == set(active)

    try:
        assert isinstance(manager, Model3DManager)
        root.update()
        assert not app.COLOR_SPACE and manager.graph_widget is None
        fixture = ROOT / 'Source/test/cases/java_comparison/fixtures/partition_pyfcs.fcs'
        load(fixture)
        assert manager.selected_alpha
        assert app.fuzzy_color_space.color_space == 'RGB'
        layers('Core')
        ax = manager.ax_3d
        ax.view_init(elev=27, azim=33)
        state = manager._model_3d_view_snapshot(ax)
        layers('Core', 'Support')
        assert manager.ax_3d is ax
        assert manager._model_3d_view_snapshot(ax) == state
        layers()
        layers('Representative', '0.5-cut')
        assert manager._model_3d_view_snapshot(ax) == state
        marker = VisualManager.get_orientation_inset(manager.fig_3d)
        assert marker is not None
        manager._on_model_3d_inset_click(SimpleNamespace(button=1, inaxes=marker))
        assert manager._model_3d_view_snapshot(ax) == manager._model_3d_initial_view
        app.deselect_all_color()
        assert not manager.selected_alpha
        app.select_all_color()
        assert manager.selected_alpha
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            path = folder / 'Hierarchy.json'
            source = FuzzyColorSpaceBuilder.build_granular('Hierarchy', PreJavaAuditTests.RGB,
                color_space='RGB', hierarchy=PreJavaAuditTests.HIERARCHY)
            path.write_text(InputJSON.format_document(InputJSON.serialize_space(source)), encoding='utf-8')
            load(path)
            assert manager.ax_3d is not ax
            assert app.fuzzy_color_space.color_space == 'RGB'
            assert len(manager.selected_alpha) == 4
            assert set(manager._model_3d_roots) == {'Root'}
            root_path = (('category', 'Root'),)
            manager._toggle_model_3d_expanded(root_path)
            assert root_path in manager._model_3d_expanded_categories
            manager._model_3d_search_var.set('blue')
            root.update()
            assert manager._model_3d_active == frozenset(manager.selected_granules)
            manager._model_3d_search_var.set('')
            manager.selected_granules['blue'].set(0)
            manager._toggle_model_3d_granule('blue')
            assert len(manager.selected_alpha) == 3
            assert manager.selected_colors['Root'].get() == -1
            assert manager._model_3d_enabled_counts['Root'] == 3
            assert manager._model_3d_enabled_counts['Cold'] == 1
            app.select_all_color()
            layers('Core')
            signature, selected_volumes, native_mode = manager._threshold_view_signature()
            # Use a small result fixture for the controller test; the real BFS
            # algorithm is covered by the headless threshold regression suite.
            point = tuple(float(v) for v in selected_volumes[0].positive)
            result = {k: {'points': {'Volume_0': [point]}, 'limits': {}}
                      for k in ('PT', 'AT', 'AT_ONLY')}
            with patch.object(app.color_manager, 'filter_points_with_thresholds', return_value=result) as evaluate, \
                    patch.object(app.color_manager, 'create_csv') as write_csv:
                app.get_umbral_points(mode='PT')
                assert app._has_any_active_job()
                deadline = time.monotonic() + 10
                # The worker posts its result via Tk's real mainloop.
                def finish_when_ready():
                    if errors or not manager._threshold_job_running or time.monotonic() >= deadline:
                        root.quit()
                    else:
                        root.after(15, finish_when_ready)
                root.after(15, finish_when_ready)
                root.mainloop()
                assert not errors, errors
                assert not manager._threshold_job_running
                assert not app._has_any_active_job()
                evaluate.assert_called_once_with(selected_volumes, step=0.25, metric='CIEDE2000',
                    color_space=native_mode, pt_threshold=0.8, at_threshold=1.8)
                assert write_csv.call_count == 2
                assert manager._threshold_analysis_cache['signature'] == signature
            for mode in ('PT','AT','BOTH'):
                app.get_umbral_points(mode=mode)
                assert manager._threshold_display_mode == mode
                assert set(manager.filtered_points) == ({'PT','AT_ONLY'} if mode=='BOTH' else {mode})
            # Threshold cache must not survive a different geometric selection.
            layers('Support')
            assert manager.filtered_points == {}
            # Actual interactive figure/HTML creation, without launching a browser.
            with patch.object(app, '_get_temp_plot_dir', return_value=str(folder)), \
                    patch('webbrowser.open_new_tab') as browser:
                manager._on_add_graph_current()
                assert browser.called and list(folder.glob('pyfcs_3d_plot*.html'))
            # The shared operator and pixel-information overlay remain on the app.
            app._set_image_mapping_tconorm('max')
            assert app.fuzzy_color_space.tconorm == 'max'
            p = folder / 'image.png'
            Image.new('RGB',(90,60),(100,40,120)).save(p)
            app.create_floating_window(14,14,str(p)); root.update()
            wid = next(iter(app.pil_images_original))
            app.display_pixel_value(1,1,[50.,10.,-10.],image_id=wid)
            root.update()
            assert app.lab_value_frame.master is manager.Canvas1
            app.close_all_image(); root.update()
            assert not app.pil_images_original
            # Loading another model resets visual and threshold selections.
            lab_path = folder / 'ClassicLAB.json'
            lab_space = FuzzyColorSpaceBuilder.build('ClassicLAB', {'Red': (50., 60., 35.), 'Blue': (40., 10., -55.)}, color_space='LAB')
            lab_path.write_text(InputJSON.format_document(InputJSON.serialize_space(lab_space)), encoding='utf-8')
            load(lab_path)
            assert app.fuzzy_color_space.color_space == 'LAB'
            assert manager._model_3d_search_var.get() == ''
            assert manager._threshold_points_for_current_view() == {}
        assert not errors, errors
    finally:
        root.destroy()


def optional_first_image_gui_smoke():
    """Exercise the reported menu path on a fresh app, including caught exceptions.

    A debugger can stop on AttributeError inside a delegated property even
    when hasattr/getattr catches it. Capture such exceptions explicitly.
    """
    import tempfile
    import tkinter as tk
    from unittest.mock import patch
    from PIL import Image
    from Source.interface.mainInterface import PyFCSApp

    root = tk.Tk()
    app = PyFCSApp(root)
    errors, warnings, delegated_errors = [], [], []
    root.report_callback_exception = lambda typ, exc, tb: errors.append(repr(exc))
    app.custom_warning = lambda *a, **kw: warnings.append((a, kw))
    previous_trace = sys.gettrace()

    def trace(frame, event, arg):
        if (event == 'exception' and frame.f_code.co_name == 'get'
                and frame.f_globals.get('__name__') == PyFCSApp.__module__
                and isinstance(arg[1], AttributeError)):
            delegated_errors.append(str(arg[1]))
        return trace

    def open_from_menu(filename):
        with patch('tkinter.filedialog.askopenfilename', return_value=filename):
            app.open_image()
        root.update()

    try:
        root.update()
        assert not app.COLOR_SPACE
        assert app.window_image_key == {}
        assert not app.load_images_names
        with tempfile.TemporaryDirectory() as td:
            image = Path(td) / 'first.png'
            Image.new('RGBA', (32, 24), (91, 125, 64, 128)).save(image)
            corrupt = Path(td) / 'corrupt.png'
            corrupt.write_bytes(b'not an image')
            sys.settrace(trace)
            try:
                app.close_all_image()
                open_from_menu('')  # Cancel the open-file dialog.
                assert not app.load_images_names
                open_from_menu(str(corrupt))
                assert len(warnings) == 1 and not app.load_images_names
                assert not app.window_image_key
                warnings.clear()
                open_from_menu(str(image))
                assert len(app.load_images_names) == 1
                first = next(iter(app.load_images_names))
                assert first in app.window_image_key
                assert not app.CAN_APPLY_MAPPING[first]
                assert app.pil_images_original[first].size == (32, 24)
                key = app.window_image_key[first]
                open_from_menu(str(image))  # Duplicate filename, independent cards.
                assert len(app.load_images_names) == 2
                assert list(app.window_image_key.values()) == [key, key]
                app.close_all_image()
                root.update()
                assert not app.window_image_key and not app.pil_images_original
                assert not app.floating_images and not app.modified_image
                assert app.image_manager.preprocessing_cache.info()['entries'] == 0
                open_from_menu(str(image))
                assert len(app.window_image_key) == 1
                app.close_all_image()
                root.update()
                assert not app.window_image_key
            finally:
                sys.settrace(previous_trace)
            assert not delegated_errors, delegated_errors
            assert not errors, errors
            assert not warnings, warnings
    finally:
        root.destroy()


def optional_image_display_gui_smoke():
    """Exercise real image cards, mapping interactions, sampling and export."""
    import hashlib
    import tempfile
    import time
    import tkinter as tk
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import patch

    import numpy as np
    from PIL import Image
    from Source.interface.mainInterface import PyFCSApp
    from Source.fuzzy.FuzzyColorSpaceBuilder import FuzzyColorSpaceBuilder
    from Source.input_output.InputJSON import InputJSON
    from Source.test.test_core_regressions import PreJavaAuditTests

    root = tk.Tk()
    app = PyFCSApp(root)
    errors = []
    warnings = []
    results = {}
    root.report_callback_exception = lambda typ, exc, tb: errors.append(repr(exc))
    app.custom_warning = lambda *a, **kw: warnings.append((a, kw))

    def settle(delay=0.12):
        deadline = time.monotonic() + delay
        while time.monotonic() < deadline:
            root.update()
            time.sleep(.005)
        assert not errors, errors

    def wait(predicate, timeout=30):
        deadline = time.monotonic() + timeout
        def poll():
            if errors or predicate() or time.monotonic() >= deadline:
                root.quit()
            else:
                root.after(15, poll)
        root.after(15, poll)
        root.mainloop()
        assert not errors, errors
        assert predicate(), 'Image Display GUI operation timed out'
        settle()

    def digest(name, array):
        a = np.ascontiguousarray(array)
        results[name] = (list(a.shape), str(a.dtype), hashlib.sha256(a.tobytes()).hexdigest())

    def event_at(wid, fx, fy, **extra):
        st = app.floating_window_state[wid]
        canvas = app.image_canvas
        return SimpleNamespace(x=int(st['x'] + 12 + st['w'] * fx - canvas.canvasx(0)),
                               y=int(st['y'] + 44 + st['h'] * fy - canvas.canvasy(0)), **extra)

    def snapshot(name, wid):
        digest(name, np.asarray(app.display_pil[wid]))
        results[name + '_view'] = dict(app.image_view_state[wid])

    def click_tag(wid, suffix):
        canvas = app.image_canvas
        box = canvas.bbox(f'{wid}_{suffix}')
        assert box, suffix
        x = int((box[0]+box[2])/2-canvas.canvasx(0))
        y = int((box[1]+box[3])/2-canvas.canvasy(0))
        canvas.event_generate('<Motion>', x=x, y=y)
        root.update()
        canvas.event_generate('<ButtonPress-1>', x=x, y=y)
        canvas.event_generate('<ButtonRelease-1>', x=x, y=y)
        settle()

    try:
        settle(.25)
        root.attributes('-fullscreen', False)
        root.geometry('1400x900')
        settle(.25)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            space = FuzzyColorSpaceBuilder.build_granular('Hierarchy', PreJavaAuditTests.RGB,
                color_space='RGB', hierarchy=PreJavaAuditTests.HIERARCHY)
            model = folder/'Hierarchy.json'
            model.write_text(InputJSON.format_document(InputJSON.serialize_space(space)), encoding='utf-8')
            completed = []
            assert app.load_color_space(str(model), on_success=lambda *a: completed.append(True))
            wait(lambda: bool(completed) and app.model_3d._model_3d_surface_job is None)
            # A deterministic RGBA gradient and a second independent image.
            yy, xx = np.indices((60, 90))
            a = np.stack(((xx*3+12)%256, (yy*4+10)%256, (xx+yy*2)%256,
                          np.where(xx<5, 0, np.where(xx<20, 128, 255))), axis=-1).astype(np.uint8)
            first = folder/'first.png'; second = folder/'second.png'
            Image.fromarray(a).save(first)
            Image.fromarray(a[:, ::-1]).save(second)
            assert app.create_floating_window(14,14,str(folder/'missing.png')) is False
            assert not app.load_images_names and len(warnings)==1
            warnings.clear()
            app.create_floating_window(14,14,str(first)); settle()
            w1 = next(iter(app.load_images_names))
            app.create_floating_window(14,14,str(second)); settle()
            w2 = next(w for w in app.load_images_names if w!=w1)
            assert app._image_workspace_window_ids()==[w1,w2]
            assert app._image_workspace_active_id==w2
            assert '2 images' in app.image_workspace_status_var.get()
            np.testing.assert_array_equal(np.asarray(app.pil_images_original[w1]), a)
            snapshot('grid_original', w1)
            # Zoom and pan use the real per-card callbacks/Canvas bindings.
            app._image_zoom_callbacks[w1]['wheel'](event_at(w1,.5,.5,delta=120)); settle()
            assert app.image_view_state[w1]['zoom']>1
            assert app.image_view_state[w2]['zoom']==1
            snapshot('zoom', w1)
            event = event_at(w1,.5,.5)
            cv = app.image_canvas
            cv.event_generate('<Motion>', x=event.x, y=event.y); root.update()
            cv.event_generate('<ButtonPress-3>', x=event.x, y=event.y)
            cv.event_generate('<B3-Motion>', x=event.x+10, y=event.y+7)
            cv.event_generate('<ButtonRelease-3>', x=event.x+10, y=event.y+7); settle()
            assert app.image_view_state[w1]['cx']!=results['zoom_view']['cx'], 'pan did not move'
            snapshot('pan', w1)
            # ROI/pixel coordinate conversion is exercised on the zoomed image.
            samples=[]
            with patch.object(app,'display_pixel_value', side_effect=lambda *args,**kw: samples.append((args,kw))):
                point=event_at(w1,.3,.3)
                app._on_original_mouse_down(point,w1); app._on_original_mouse_up(point,w1)
                assert len(samples)==1 and not samples[-1][1]['is_average']
                start,end=event_at(w1,.3,.3),event_at(w1,.7,.7)
                app._on_original_mouse_down(start,w1); app._on_original_mouse_drag(end,w1); app._on_original_mouse_up(end,w1)
                assert len(samples)==2 and samples[-1][1]['is_average']
                assert samples[-1][1]['selection_info']['pixels']>1
                results['pixel']=[samples[0][0][0],samples[0][0][1],list(samples[0][0][2])]
                roi=dict(samples[1][1]['selection_info']); roi['mean_rgb']=list(roi['mean_rgb'])
                results['roi']=roi
                results['roi_lab']=list(samples[1][0][2])
            app._toggle_image_card_minimize(w1); settle()
            assert app._is_workspace_card_collapsed(w1)
            app._toggle_image_card_minimize(w1); settle()
            assert not app._is_workspace_card_collapsed(w1)
            app._set_image_workspace_focus(w1); settle()
            assert app._image_workspace_focus_id==w1
            assert cv.itemcget(f'{w2}_img_item','state')=='hidden'
            snapshot('focus',w1)
            app._arrange_image_workspace_grid(); settle()
            assert app._image_workspace_focus_id is None
            assert cv.itemcget(f'{w2}_img_item','state')!='hidden'
            # Manual resize callbacks retain independent card state.
            start,resize,finish=app._resize_callbacks[w1]
            e=event_at(w1,.9,.9); start(e)
            e2=SimpleNamespace(x=e.x+30,y=e.y+20); resize(e2); finish(e2); settle()
            assert app._image_workspace_layout_mode=='manual'
            snapshot('resized',w1)
            # Real mapping worker, view/legend switching and original restore.
            app.color_mapping(w1)
            app._select_mapping_item(w1,('category',0))
            wait(lambda: not app._has_active_job(w1) and w1 not in app.image_jobs)
            assert app.window_mapping_mode[w1]=='single'
            digest('single_membership',app.modified_image[w1]); snapshot('single',w1)
            app._set_single_mapping_level(w1,'granules'); settle()
            app._set_single_mapping_style(w1,'color'); settle(); snapshot('single_color',w1)
            app.color_mapping_all(w1)
            wait(lambda: not app._has_active_job(w1) and w1 not in app.image_jobs and w1 in app._mapping_all_pack_by_window)
            pack=app._mapping_all_pack_by_window[w1]
            digest('general_labels',pack['label_maps']['categories'])
            digest('detailed_labels',pack['label_maps']['granules'])
            snapshot('all_general',w1)
            with patch.object(app.image_manager, 'get_category_granule_label_maps',
                              side_effect=AssertionError('view change recalculated memberships')) as evaluate:
                app._set_mapping_all_level(w1,'granules'); settle(); snapshot('all_detailed',w1)
                app._set_mapping_all_palette(w1,'alt'); settle(); snapshot('all_alt',w1)
                evaluate.assert_not_called()
            app._set_image_mapping_tconorm('max')
            wait(lambda: not app._has_active_job(w1) and w1 not in app.image_jobs and w1 in app._mapping_all_pack_by_window)
            snapshot('all_max',w1)
            export=folder/'mapping.png'
            with patch('tkinter.filedialog.asksaveasfilename',return_value=str(export)), patch('tkinter.messagebox.showinfo'):
                app.save_image(w1)
            assert export.exists() and (folder/'mapping_legend.png').exists()
            with Image.open(export) as im: digest('export',np.asarray(im))
            with Image.open(folder/'mapping_legend.png') as im: digest('legend',np.asarray(im))
            app.show_original_image(w1); settle(); snapshot('restored',w1)
            assert w1 in app._original_sampling_state
            # A cancelled Mapping All restores Original and rejects a late worker result.
            import threading
            entered = threading.Event()
            def delayed_mapping(*args, **kwargs):
                entered.set()
                deadline = time.monotonic() + 10
                while not kwargs['cancel_callback']() and time.monotonic() < deadline:
                    time.sleep(.005)
                assert kwargs['cancel_callback'](), 'mapping worker was not cancelled'
                return None
            app.cm_cache_by_image.clear()
            with patch.object(app.image_manager, 'get_category_granule_label_maps', side_effect=delayed_mapping):
                app.color_mapping_all(w1)
                wait(lambda: entered.is_set())
                assert app._has_active_job(w1)
                app.show_original_image(w1)
                wait(lambda: w1 not in app.image_jobs)
            assert w1 not in app.window_mapping_mode
            assert w1 not in app._mapping_all_pack_by_window
            assert w1 in app._original_sampling_state
            digest('after_cancel', np.asarray(app.display_pil[w1]))
            assert results.pop('after_cancel') == results['restored']
            # Full-resolution workspace lifecycle and single-card close.
            app.open_full_resolution_image_workspace(w2); settle(.3)
            workspace=app._full_resolution_workspace_controller
            assert workspace.source_window_id==w2 and workspace.win.winfo_exists()
            # Exercise the actual full-resolution mapping worker and export, not just its window.
            from Source.interface.modules.image.ColorProcessingEngine import general_mapping_space
            from Source.interface.modules.image import ImageWorkspaceManager as workspace_module
            workspace.mapping_var.set('All'); workspace._on_mapping_mode_changed()
            workspace._start_processing()
            wait(lambda: workspace.result is not None and not app._has_any_active_job())
            rgba = np.asarray(workspace.original)
            expected = app.image_manager.get_category_granule_label_maps(workspace.original,
                general_mapping_space(app.fuzzy_color_space), rgba[...,3]>0)
            np.testing.assert_array_equal(workspace.result['categories'],expected[0])
            np.testing.assert_array_equal(workspace.result['granules'],expected[1])
            workspace.roi=(5,4,30,25); workspace.scope_var.set('Selected ROI'); workspace._on_scope_changed()
            assert workspace._result_for_current_mode() is None
            workspace._start_processing()
            wait(lambda: workspace._result_for_current_mode() is not None and not app._has_any_active_job())
            assert workspace.result['scope']==workspace.roi
            with patch('tkinter.filedialog.askdirectory',return_value=str(folder)), patch('tkinter.messagebox.showinfo'):
                workspace._save_dialog()
                wait(lambda: not app._has_any_active_job())
            assert (folder/'second_analysis'/'analysis_metadata.json').exists()
            # Close during a live job; model replacement must remain blocked until cleanup exits.
            entered=threading.Event(); release=threading.Event()
            def delayed_workspace(*args, **kwargs):
                entered.set()
                assert release.wait(10), 'test did not release workspace worker'
                assert kwargs['cancelled']()
                return None
            with patch.object(workspace_module, 'compute_full_resolution_mapping', side_effect=delayed_workspace):
                try:
                    workspace._start_processing(); wait(entered.is_set)
                    workspace.close(); settle()
                    assert app._full_resolution_workspace_controller is None
                    assert app._has_any_active_job()
                    assert app.load_color_space(str(model)) is False
                    assert len(warnings)==1; warnings.clear()
                finally:
                    release.set()
                wait(lambda: not app._has_any_active_job())
            # A malformed model cannot replace the currently loaded one.
            active = app.fuzzy_color_space
            invalid = folder/'broken.json'; invalid.write_text('{', encoding='utf-8')
            assert app.load_color_space(str(invalid))
            wait(lambda: not app._has_any_active_job())
            assert app.fuzzy_color_space is active and len(warnings)==1
            warnings.clear()
            # Other windows must still share the active model after the recovery.
            app.open_image_inspection(); settle()
            inspector = app._image_inspection_controller
            assert inspector is not None and inspector.win.winfo_exists()
            inspector.close(); settle()
            app.open_modify_fcs(); settle()
            editor = app._modify_fcs_dialog
            assert editor is not None and editor.win.winfo_exists()
            editor.close(); settle()
            assert app.fuzzy_color_space is active
            app.palette_based_creation(); settle()
            palette = app._palette_based_creation_controller
            assert palette is not None and palette.win.winfo_exists()
            # The supplied Source-only archive does not necessarily ship its palette.
            assert all(a[0]=='Palette Error' for a,_ in warnings), warnings
            warnings.clear(); palette.close(); settle()
            app.image_based_creation(); settle()
            creation = app._image_based_creation_controller
            assert creation is not None and creation.win.winfo_exists()
            creation._sample_pixel(30,10)
            assert creation._current_sample is not None
            creation._run_auto_detection()
            wait(lambda: not app._has_any_active_job())
            assert all(a[0]=='No Colors Detected' for a,_ in warnings), warnings
            warnings.clear()
            entered=threading.Event(); release=threading.Event()
            def delayed_detection(*args, **kwargs):
                entered.set()
                assert release.wait(10)
                return []
            with patch.object(app.image_manager, 'get_fcs_image', side_effect=delayed_detection):
                try:
                    creation._run_auto_detection(); wait(entered.is_set)
                    creation.close(); settle()
                    assert app._image_based_creation_controller is None
                    assert app._has_any_active_job()
                    assert not app._can_start_new_creation()
                    assert len(warnings)==1; warnings.clear()
                finally:
                    release.set()
                wait(lambda: not app._has_any_active_job())
            # A rejected close-all confirmation must preserve both cards.
            with patch.object(app,'_has_any_active_job',return_value=True), patch('tkinter.messagebox.askyesno',return_value=False):
                app.close_all_image()
            assert len(app.load_images_names)==2
            app._arrange_image_workspace_grid(); settle()
            click_tag(w2,'close_button')
            assert app._image_workspace_window_ids()==[w1]
            assert w2 not in app.image_view_state and w2 not in app._image_zoom_callbacks
            app.close_all_image(); settle()
            assert not app.pil_images_original and not app.floating_images
            assert app.image_manager.preprocessing_cache.info()['entries']==0
            assert not warnings, warnings
            assert not errors, errors
        return results
    finally:
        root.destroy()


def optional_color_evaluation_gui_smoke():
    """Exercise the Color Evaluation window, including shared application callbacks."""
    import json, tempfile, time, sys
    from pathlib import Path
    from unittest.mock import patch
    import tkinter as tk
    from tkinter import ttk
    import numpy as np
    from PIL import Image
    from Source.interface.mainInterface import PyFCSApp
    from Source.fuzzy.FuzzyColorSpaceBuilder import FuzzyColorSpaceBuilder
    from Source.input_output.InputJSON import InputJSON
    from Source.test.test_core_regressions import PreJavaAuditTests
    from Source.interface.modules.common import UtilsTools

    root=tk.Tk(); app=PyFCSApp(root); errors=[]; warnings=[]; results={}
    root.report_callback_exception=lambda t,e,b: errors.append(repr(e))
    app.custom_warning=lambda *a,**kw:warnings.append(str(a))
    def settle(delay=.12):
        deadline=time.monotonic()+delay
        while time.monotonic()<deadline:
            root.update(); time.sleep(.005)
        assert not errors,errors
    def load(path):
        complete=[]; assert app.load_color_space(str(path),on_success=lambda *a:complete.append(True))
        deadline=time.monotonic()+20
        while not complete or app.model_3d._model_3d_surface_job is not None:
            settle(.02); assert time.monotonic()<deadline
    def walk(w):
        yield w
        for x in w.winfo_children(): yield from walk(x)
    def button(w, text):
        found=[x for x in walk(w) if isinstance(x, (tk.Button,)) and x.cget('text')==text]
        assert found, (text,[x.cget('text') for x in walk(w) if isinstance(x,tk.Button)])
        return found[0]
    def snap(key,v):
        results[key]={k:v[k].get() for k in ('space_name_var','space_count_var','selected_result_var','selected_detail_var','selected_summary_var','inspector_rgb_var','inspector_lab_var','inspector_hex_var','primary_name_var','secondary_name_var')}
        results[key]['history']=list(v['quick_samples'])
        results[key]['membership']=v.get('evaluation_snapshot')
        results[key]['closest']=v.get('closest_ranking')
        # snapshots copied by JSON serialization (numpy numeric types converted below)
        results[key]=json.loads(json.dumps(results[key],default=lambda x:x.tolist() if hasattr(x,'tolist') else str(x)))
    try:
        settle(); app.color_evaluation(); settle(); assert app._color_evaluation_vars is not None
        app._on_close_color_evaluation_window(); settle(); assert app._color_evaluation_vars is None
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)
            space=FuzzyColorSpaceBuilder.build_granular('Hierarchy',PreJavaAuditTests.RGB,color_space='RGB',hierarchy=PreJavaAuditTests.HIERARCHY)
            f=folder/'Hierarchy.json'; f.write_text(InputJSON.format_document(InputJSON.serialize_space(space)),encoding='utf-8'); load(f)
            app.color_evaluation(); settle(); v=app._color_evaluation_vars; w=app._color_evaluation_window
            assert v['loaded_fuzzy_color_space'] is app.fuzzy_color_space
            app.color_evaluation(); settle(); assert app._color_evaluation_window is w
            snap('initial',v)
            for side,rgb in [('A',(230,35,30)),('B',(45,100,155))]:
                lab=UtilsTools.rgb_to_lab(rgb)
                assert app._use_color_evaluation_external_sample(v,name=side,lab=lab,rgb=rgb,hex_color=UtilsTools.rgb_to_hex(rgb),source='custom RGB',target=side)
                settle(); snap(side,v)
            app._show_color_evaluation_closest_prototypes(v); settle(); snap('closest',v)
            assert v['closest_ranking']
            app._set_image_mapping_tconorm('max'); settle(); snap('max',v)
            assert v['evaluation_operator_var'].get()=='Max'
            app._swap_color_evaluation_rows(v); settle(); snap('swap',v)
            # Pin, clear and reopen are real UI paths, not numerical mocks.
            app._pin_color_evaluation_sample(v,v['quick_samples'][0]['id']); app._clear_color_evaluation_recent_samples(v); settle(); snap('pin',v)
            received=[]
            dialog=app._open_custom_color_dialog(parent=w,initial_lab=(51.234,12.345,-23.456),submit_text='Test submit',on_submit=lambda name,lab,rgb,hx,d,iv:(received.append([name,lab,rgb,hx]),d.destroy()))
            settle(); button(dialog,'Test submit').invoke(); settle(); assert received
            results['custom_dialog']=received
            picker=app._open_square_color_picker(parent=w,initial_rgb=(10,20,30)); settle(); assert picker.winfo_exists(); picker.destroy(); settle()
            # Actual image sampler uses the loaded original.
            img=folder/'image.png'; Image.new('RGB',(90,60),(100,40,120)).save(img)
            app.create_floating_window(14,14,str(img)); settle()
            app._open_color_evaluation_image_sampler(v); settle()
            pop=next(x for x in w.winfo_children() if isinstance(x,tk.Toplevel) and x.title()=='Sample Color from Image')
            cv=max((x for x in walk(pop) if isinstance(x,tk.Canvas)),key=lambda x:x.winfo_width()*x.winfo_height()); x,y=cv.winfo_width()//2,cv.winfo_height()//2
            cv.event_generate('<ButtonPress-1>',x=x,y=y); cv.event_generate('<ButtonRelease-1>',x=x,y=y); settle()
            bs=[b for b in walk(pop) if isinstance(b,(tk.Button,ttk.Button))]
            use=next(b for b in bs if b.cget('text') == 'Add to Reference')
            assert str(use.cget('state'))=='normal',[(b.cget('text'),b.cget('state')) for b in bs]
            use.invoke(); settle(); snap('sampler',v); assert tuple(v['secondary_custom_rgb'])==(100,40,120)
            pop.destroy(); settle()
            # Plot construction is real; intercept browser delivery only.
            figs=[]
            with patch.object(app,'_open_plotly_figure_in_browser',side_effect=lambda fig,**kw:figs.append((fig,kw))):
                app._open_color_evaluation_ab_plot(v); app._open_color_evaluation_3d_plot(v)
            assert len(figs)==2
            results['plots']=[{'traces':len(f.data),'types':[t.type for t in f.data], 'prefix':kw.get('filename_prefix')} for f,kw in figs]
            app._on_close_color_evaluation_window(); settle(); assert app._color_evaluation_vars is None
            app.color_evaluation(); settle(); assert app._color_evaluation_vars is not v; snap('reopened',app._color_evaluation_vars)
            app._on_close_color_evaluation_window(); app.close_all_image(); settle()
        assert not warnings,warnings
        return results
    finally: root.destroy()


def main(argv=None):
    """Discover tests, run optional GUI checks and store a summary report."""
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--gui",
        action="store_true",
        help="Also exercise the real Tkinter FCS creation, Model 3D and Image Display interfaces"
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Show only failures and summary"
    )

    parser.add_argument(
        "--report-dir",
        type=Path,
        default=TESTS / "reports",
        help="Where to save .log and .json results"
    )

    args = parser.parse_args(argv)

    # Run tests from a consistent working directory and create report storage.
    os.chdir(ROOT)
    args.report_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = args.report_dir / f"global_{stamp}.log"
    json_file = args.report_dir / f"global_{stamp}.json"

    started = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()

    with log_file.open("w", encoding="utf-8") as out:
        stream = Tee(sys.stdout, out)

        print(f"PyFCS regression suite | root: {ROOT}", file=stream)
        print(
            "Discovering global and case-specific automated regression tests...",
            file=stream
        )

        # Test modules, including comparison-tool checks, run in one suite.
        suite = unittest.defaultTestLoader.discover(
            start_dir=str(TESTS),
            pattern="test_*.py",
            top_level_dir=str(ROOT)
        )

        result = unittest.TextTestRunner(
            stream=stream,
            verbosity=(1 if args.quiet else 2)
        ).run(suite)

        # GUI checks remain opt-in so the regular suite can run headlessly.
        gui_error = None
        gui_status = "not_requested"

        if args.gui:
            print("\nGUI smoke: FCS creation dialog", file=stream)

            try:
                optional_gui_smoke()
                print("GUI smoke: Model 3D controller", file=stream)
                optional_model3d_gui_smoke()
                print("GUI smoke: First image / delegated state", file=stream)
                optional_first_image_gui_smoke()
                print("GUI smoke: Image Display controller", file=stream)
                optional_image_display_gui_smoke()
                print("GUI smoke: Color Evaluation window", file=stream)
                optional_color_evaluation_gui_smoke()
                gui_status = "passed"
                print("GUI smoke PASSED", file=stream)

            except Exception as exc:
                gui_status = "failed"
                gui_error = f"{type(exc).__name__}: {exc}"
                print(f"GUI smoke FAILED: {gui_error}", file=stream)

        elapsed = round(time.perf_counter() - started, 3)

        # Store both aggregate counts and individual failures for diagnosis.
        report = {
            "kind": "PyFCS global regression",
            "started_utc": started_at,
            "project_root": str(ROOT),
            "python": sys.version,
            "tests_run": result.testsRun,
            "failures": len(result.failures),
            "errors": len(result.errors),
            "skipped": len(result.skipped),
            "expected_failures": len(result.expectedFailures),
            "unexpected_successes": len(result.unexpectedSuccesses),
            "gui": gui_status,
            "gui_error": gui_error,
            "elapsed_seconds": elapsed,
            "passed": result.wasSuccessful() and gui_status != "failed",
            "failure_details": [
                {"test": str(t), "traceback": err}
                for t, err in result.failures
            ],
            "error_details": [
                {"test": str(t), "traceback": err}
                for t, err in result.errors
            ],
            "skipped_details": [
                {"test": str(t), "reason": why}
                for t, why in result.skipped
            ],
        }

        json_file.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        print(
            f"\nSummary: {result.testsRun} tests | "
            f"{len(result.failures)} failures | "
            f"{len(result.errors)} errors | "
            f"{len(result.skipped)} skipped | {elapsed}s",
            file=stream
        )
        print(f"Log: {log_file}", file=stream)
        print(f"JSON: {json_file}", file=stream)

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())

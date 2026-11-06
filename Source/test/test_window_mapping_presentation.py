"""Regression checks for smooth popup presentation and Mapping-All palette controls."""
import ast
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import os
import sys

# Get the path to the directory containing PyFCS
current_dir = os.path.dirname(__file__)
pyfcs_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))

# Add the PyFCS path to sys.path
sys.path.append(pyfcs_dir)

import numpy as np
from PIL import Image

from Source.interface.mainInterface import PyFCSApp
from Source.interface.modules import UtilsTools


class MappingAllPaletteTests(unittest.TestCase):
    @staticmethod
    def _application(covering=True):
        class Stub:
            pass

        app = Stub()
        app._has_active_job = Mock(return_value=False)
        app.mapping_locked_until_original = {}
        app.window_image_key = {'card': 'image.png'}
        app.fuzzy_color_space = SimpleNamespace(covering=covering)
        app.image_manager = SimpleNamespace(recolor_label_map=Mock(
            return_value=np.ones((1, 2, 4), dtype=np.uint8) * 100))
        app._display_mapping_all_result = Mock()
        app.custom_warning = Mock()
        app._mapping_all_pack_by_window = {'card': {
            'scheme': 'alt',
            'label_map': np.array([[0, 1]], dtype=np.int16),
            'alpha_values': np.array([[255, 255]], dtype=np.uint8),
            'palettes': {
                'original': np.array([[10, 20, 30], [40, 50, 60]], dtype=np.uint8),
                'alt': np.array([[100, 110, 120], [150, 160, 170]], dtype=np.uint8),
            },
        }}
        return app

    def test_palette_tabs_reuse_cached_label_map(self):
        app = self._application()
        original = app._mapping_all_pack_by_window['card']['palettes']['original']
        self.assertEqual(PyFCSApp._set_mapping_all_palette(app, 'card', 'original'), 'break')
        self.assertEqual(app._mapping_all_pack_by_window['card']['scheme'], 'original')
        app.image_manager.recolor_label_map.assert_called_once()
        self.assertIs(app.image_manager.recolor_label_map.call_args.args[0],
                      app._mapping_all_pack_by_window['card']['label_map'])
        self.assertIs(app.image_manager.recolor_label_map.call_args.args[1], original)
        app._display_mapping_all_result.assert_called_once()
        # Clicking the selected tab is a no-op, not a second mapping request.
        PyFCSApp._set_mapping_all_palette(app, 'card', 'original')
        app.image_manager.recolor_label_map.assert_called_once()
        # Switching back uses the same label-map, without calling a classifier.
        PyFCSApp._set_mapping_all_palette(app, 'card', 'alt')
        self.assertEqual(app._mapping_all_pack_by_window['card']['scheme'], 'alt')
        self.assertEqual(app.image_manager.recolor_label_map.call_count, 2)

    def test_noncovering_unassigned_pixels_are_preserved(self):
        app = self._application(covering=False)
        pack = app._mapping_all_pack_by_window['card']
        pack['label_map'] = np.array([[-1, 0]], dtype=np.int16)
        image = np.array([[[15, 25, 35, 90], [80, 90, 100, 255]]], dtype=np.uint8)
        app._get_mapping_source_image = lambda _id: Image.fromarray(image, 'RGBA')
        PyFCSApp._set_mapping_all_palette(app, 'card', 'original')
        result = app._display_mapping_all_result.call_args.args[1]
        np.testing.assert_array_equal(result[0, 0], image[0, 0])
        np.testing.assert_array_equal(result[0, 1], [100, 100, 100, 100])

    def test_busy_or_locked_mappings_do_not_change_palette(self):
        app = self._application()
        app._has_active_job.return_value = True
        PyFCSApp._set_mapping_all_palette(app, 'card', 'original')
        self.assertEqual(app._mapping_all_pack_by_window['card']['scheme'], 'alt')
        app._has_active_job.return_value = False
        app.mapping_locked_until_original['card'] = True
        PyFCSApp._set_mapping_all_palette(app, 'card', 'original')
        self.assertEqual(app._mapping_all_pack_by_window['card']['scheme'], 'alt')
        app.image_manager.recolor_label_map.assert_not_called()
        app.custom_warning.assert_called_once()

    def test_palette_tabs_render_with_selected_state(self):
        app = SimpleNamespace()
        canvas = Mock()
        app.image_canvas = canvas
        app.proto_options = {'card': {'kind': 'all', 'rows': [], 'width': 210, 'height': 100,
                                      'x': 5, 'y': 5, 'scroll_index': 0}}
        app.floating_window_state = {'card': {'x': 5, 'y': 5, 'w': 210, 'h': 150}}
        app._mapping_all_pack_by_window = {'card': {'scheme': 'original'}}
        app._workspace_legend_height = lambda wid: 100
        app._sync_workspace_card_item_states = Mock()
        app._focus_floating_window = Mock()
        PyFCSApp._render_proto_options(app, 'card')
        captions = [c.kwargs['text'] for c in canvas.create_text.call_args_list if 'text' in c.kwargs]
        self.assertEqual(captions[-2:], ['Original', 'Alt. Colors'])
        fills = [c.kwargs.get('fill') for c in canvas.create_rectangle.call_args_list]
        self.assertIn(UtilsTools.UI_ACCENT_SOFT, fills)
        self.assertIn('#f5f5f5', fills)
        callback = next(c.args[2] for c in canvas.tag_bind.call_args_list
                        if c.args[0].endswith('_palette_alt'))
        app._set_mapping_all_palette = Mock()
        callback(None)
        app._set_mapping_all_palette.assert_called_once_with('card', 'alt')


class WindowPresentationTests(unittest.TestCase):
    def test_every_explicit_toplevel_is_hidden_before_layout(self):
        root = Path(__file__).resolve().parents[1] / 'interface'
        paths = [root / 'mainInterface.py', *(root / 'modules' / n for n in (
            'UtilsTools.py', 'PaletteBasedCreationManager.py',
            'ImageBasedCreationManager.py', 'ImageInspectionManager.py'))]
        checked = 0
        for path in paths:
            program = ast.parse(path.read_text(encoding='utf-8-sig'))
            for node in ast.walk(program):
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                rhs = node.value
                if not (isinstance(rhs, ast.Call) and isinstance(rhs.func, ast.Attribute)
                        and rhs.func.attr == 'Toplevel'):
                    continue
                target = node.targets[0] if isinstance(node, ast.Assign) else node.target
                if not isinstance(target, (ast.Name, ast.Attribute)):
                    continue
                owning = [x for x in ast.walk(program) if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))
                          and x.lineno <= node.lineno <= x.end_lineno]
                scope = min(owning, key=lambda x: x.end_lineno - x.lineno)
                assignments = [x for x in ast.walk(scope) if isinstance(x, ast.Call)
                               and isinstance(x.func, ast.Attribute)
                               and x.func.attr == 'withdraw' and x.lineno >= node.lineno]
                shows = [x for x in ast.walk(scope) if isinstance(x, ast.Call)
                         and isinstance(x.func, ast.Attribute)
                         and x.func.attr == 'deiconify' and x.lineno >= node.lineno]
                self.assertTrue(assignments, f'{path.name}:{node.lineno} missing withdraw')
                self.assertTrue(shows, f'{path.name}:{node.lineno} missing deiconify')
                checked += 1
        self.assertGreaterEqual(checked, 16)

    def test_center_auxiliary_uses_parent_geometry(self):
        parent = Mock()
        parent.winfo_rootx.return_value = 100
        parent.winfo_rooty.return_value = 80
        parent.winfo_width.return_value = 1000
        parent.winfo_height.return_value = 600
        popup = Mock()
        UtilsTools._center_auxiliary_popup(popup, parent, 400, 200)
        popup.geometry.assert_called_once_with('400x200+400+280')

if __name__ == '__main__':
    unittest.main()

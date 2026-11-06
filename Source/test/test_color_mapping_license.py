"""JFCS-style individual Color Mapping and MIT License regression tests."""
import unittest
from pathlib import Path
from unittest.mock import Mock
import numpy as np

import os
import sys

# Get the path to the directory containing PyFCS
current_dir = os.path.dirname(__file__)
pyfcs_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))

# Add the PyFCS path to sys.path
sys.path.append(pyfcs_dir)


from Source.interface.modules.ImageManager import ImageManager
from Source.interface.mainInterface import PyFCSApp


class ColorMappingLicenseTests(unittest.TestCase):
    def test_color_weighting_matches_jfcs_definition(self):
        rgb = np.array([[[200, 100, 50], [17, 65, 220], [100, 180, 225]]], dtype=np.uint8)
        degrees = np.array([[255, 0, 128]], dtype=np.uint8)
        before = rgb.copy()
        out = ImageManager.colorize_membership_map(degrees, rgb)
        expected = np.array([[[200, 100, 50], [0, 0, 0], [50, 90, 112]]], dtype=np.uint8)
        np.testing.assert_array_equal(out, expected)
        np.testing.assert_array_equal(rgb, before)
        np.testing.assert_array_equal(degrees, np.array([[255, 0, 128]], dtype=np.uint8))

    def test_color_mapping_output_shape(self):
        # Valid input, so VS Code does not stop on an intentional exception.
        rgb = np.ones((2, 3, 3), dtype=np.uint8) * 100
        degrees = np.ones((2, 3), dtype=np.uint8) * 255
        out = ImageManager.colorize_membership_map(degrees, rgb)
        self.assertEqual(out.shape, rgb.shape)
        self.assertEqual(out.dtype, np.uint8)

    def test_color_toggle_reuses_current_map(self):
        class Var:
            def get(self): return 'Pink'
        class Dummy:
            pass
        app = Dummy()
        app._has_active_job = lambda _wid: False
        app.proto_options = {'card': {'kind': 'single', 'display_style': 'gray', 'displayed_for': 'Pink'}}
        app.current_protos = {'card': Var()}
        raw = np.array([[255, 128]], dtype=np.uint8)
        app.modified_image = {'card': raw}
        app._render_proto_options = Mock()
        app.display_color_mapping = Mock()

        self.assertEqual(PyFCSApp._set_single_mapping_style(app, 'card', 'color'), 'break')
        self.assertEqual(app.proto_options['card']['display_style'], 'color')
        app._render_proto_options.assert_called_once_with('card')
        app.display_color_mapping.assert_called_once_with(raw, 'card')

    def test_style_toggle_without_selection_does_not_show_stale_map(self):
        class Var:
            def get(self): return ''
        class Dummy:
            pass
        app = Dummy()
        app._has_active_job = lambda _wid: False
        app.proto_options = {'card': {'kind': 'single', 'display_style': 'gray', 'displayed_for': None}}
        app.current_protos = {'card': Var()}
        app.modified_image = {'card': np.array([[200]], dtype=np.uint8)}
        app._render_proto_options = Mock()
        app.display_color_mapping = Mock()
        PyFCSApp._set_single_mapping_style(app, 'card', 'color')
        app.display_color_mapping.assert_not_called()

    def test_license_text_matches_distributed_license(self):
        license_path = Path(__file__).resolve().parents[2] / 'LICENSE.txt'
        self.assertEqual(PyFCSApp.MIT_LICENSE_TEXT, license_path.read_text(encoding='utf-8'))
        self.assertIn('Copyright (c) 2025 Rafael Vázquez Conejo', PyFCSApp.MIT_LICENSE_TEXT)


if __name__ == '__main__':
    unittest.main()

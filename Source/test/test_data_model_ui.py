"""UI layout and indicator regressions for Data / Model 3D."""
import os
import sys

# Get the path to the directory containing PyFCS
current_dir = os.path.dirname(__file__)
pyfcs_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))
sys.path.append(pyfcs_dir)
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from Source.interface.mainInterface import PyFCSApp

class DataModelLayoutTests(unittest.TestCase):
    def test_indicator_targets_data_tab_and_uses_compact_status(self):
        app = PyFCSApp.__new__(PyFCSApp)
        summary = MagicMock()
        summary.winfo_exists.return_value = True
        button = MagicMock()
        button.winfo_exists.return_value = True
        app.data_model_summary = summary
        app.change_model_button = button
        app.COLOR_SPACE = True
        app.fuzzy_color_space = SimpleNamespace(
            color_space='RGB', typology_description='DISJOINT and NON-COVERING')
        app._model_space_unsaved = True
        app._update_model_space_indicator()
        button.configure.assert_called_once()
        summary.configure.assert_called_with(
            text='DISJOINT and NON-COVERING  ·  RGB model  ·  Unsaved')

    def test_no_model_disables_button(self):
        app = PyFCSApp.__new__(PyFCSApp)
        app.data_model_summary = MagicMock()
        app.data_model_summary.winfo_exists.return_value = True
        app.change_model_button = MagicMock()
        app.change_model_button.winfo_exists.return_value = True
        app.COLOR_SPACE = False
        app.fuzzy_color_space = None
        app._update_model_space_indicator()
        app.data_model_summary.configure.assert_called_with(text='No color space loaded')
        self.assertEqual(app.change_model_button.configure.call_args.kwargs['state'], 'disabled')

if __name__ == '__main__':
    unittest.main()

"""Regression tests for the new PyFCS representative layout.

Run from the directory containing Source/:
    python -m unittest Source.test.test_fcs_granule_layout -v
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Get the path to the directory containing PyFCS
current_dir = os.path.dirname(__file__)
pyfcs_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))

# Add the PyFCS path to sys.path
sys.path.append(pyfcs_dir)

import numpy as np
from Source.input_output.InputFCS import InputFCS


class FCSGranuleLayoutTests(unittest.TestCase):
    COLORS = {
        'Pink': (80.553528466664659, 27.166064650770984, 8.0817175661167084),
        'Red': (41.806524774201215, 66.901730175685685, 46.511884370503267),
        'Blue': (43.653408119948693, 10.626410219330584, -54.357024392178374),
    }

    def test_explicit_one_granule_per_label(self):
        parser = InputFCS()
        with tempfile.TemporaryDirectory() as tmp:
            with patch('Source.input_output.InputFCS.get_base_path', return_value=tmp):
                path, original = parser.write_file('test_explicit_grain', self.COLORS,
                                                    return_fuzzy_space=True)
            content = Path(path).read_text(encoding='utf-8').splitlines()
            self.assertIn('@numberOfColors 3', content)
            self.assertIn('@tConorm bounded_sum', content)
            self.assertFalse(any(row.startswith('@fcsVersion') for row in content))
            start = content.index('@numberOfColors 3') + 1
            for i, (label, expected) in enumerate(self.COLORS.items()):
                self.assertEqual(content[start + 2*i], f'"{label}" 1')
                actual = tuple(map(float, content[start + 2*i + 1].split()))
                self.assertEqual(len(actual), 3)
                np.testing.assert_allclose(actual, expected, rtol=1e-15, atol=1e-12)
            colors, loaded = parser.read_file(path)
            self.assertEqual(list(colors), list(self.COLORS))
            self.assertEqual(loaded.tconorm, 'bounded_sum')
            for i, (_, triple) in enumerate(self.COLORS.items()):
                self.assertAlmostEqual(original.calculate_membership_for_prototype(triple, i),
                                       loaded.calculate_membership_for_prototype(triple, i), places=6)

    def test_max_operator_metadata_is_read_and_written(self):
        parser = InputFCS()
        with tempfile.TemporaryDirectory() as tmp:
            with patch('Source.input_output.InputFCS.get_base_path', return_value=tmp):
                path = parser.write_file('test_max_tconorm', self.COLORS, tconorm='max')
            _, loaded = parser.read_file(path)
            self.assertEqual(loaded.tconorm, 'max')


if __name__ == '__main__':
    unittest.main()

"""Smoke/regression checks for LAB/RGB typology and FCS persistence.

Run from the directory that contains Source/:
    python -m unittest Source.test.test_typologies_rgb -v
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from skimage import color as skcolor


# Get the path to the directory containing PyFCS
current_dir = os.path.dirname(__file__)
pyfcs_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))

# Add the PyFCS path to sys.path
sys.path.append(pyfcs_dir)

from Source import ReferenceDomain
from Source.fuzzy.FuzzyColorSpaceBuilder import FuzzyColorSpaceBuilder
from Source.input_output.InputFCS import InputFCS


class TypologiesAndRGBTests(unittest.TestCase):
    RGB_COLORS = {
        "Red": (255.0, 0.0, 0.0),
        "Green": (0.0, 255.0, 0.0),
        "Blue": (0.0, 0.0, 255.0),
    }

    @classmethod
    def setUpClass(cls):
        cls.rgb = cls.RGB_COLORS
        cls.lab = {
            name: tuple(skcolor.rgb2lab((np.asarray(rgb).reshape(1, 1, 3) / 255.0))[0, 0])
            for name, rgb in cls.rgb.items()
        }

    def test_all_typologies_rgb(self):
        for disjoint in (True, False):
            for covering in (True, False):
                with self.subTest(disjoint=disjoint, covering=covering):
                    neg = {"Red": [self.rgb["Green"]]} if not disjoint else None
                    space = FuzzyColorSpaceBuilder.build(
                        "rgb-test", self.rgb, color_space="RGB", disjoint=disjoint,
                        covering=covering, samples=27, negative_prototypes=neg)
                    self.assertEqual(space.is_partition, disjoint and covering)
                    self.assertEqual(space.reference_domain.bounds, (0,255,0,255,0,255))
                    self.assertEqual(len(space.prototypes), 3)
                    self.assertEqual(space.color_space, "RGB")
                    if not covering:
                        self.assertGreater(len(space.auxiliary_negatives), 0)
                    red_mu = space.calculate_membership_for_prototype(self.rgb["Red"], 0, input_space="RGB")
                    self.assertAlmostEqual(red_mu, 1, places=6)

    def test_rgb_lab_conversion_and_grayscale_input(self):
        space = FuzzyColorSpaceBuilder.build("rgb-test", self.rgb, color_space="RGB")
        for idx, (name, rgb) in enumerate(self.rgb.items()):
            self.assertAlmostEqual(space.calculate_membership_for_prototype(rgb, idx, input_space="RGB"), 1)
            self.assertAlmostEqual(space.calculate_membership_for_prototype(self.lab[name], idx, input_space="LAB"), 1, places=4)

    def test_all_typologies_fcs_roundtrip_both_color_spaces(self):
        writer = InputFCS()
        with tempfile.TemporaryDirectory() as root:
            with patch('Source.input_output.InputFCS.get_base_path', return_value=root):
                for mode in ('LAB', 'RGB'):
                    for disjoint in (True, False):
                        for covering in (True, False):
                            with self.subTest(mode=mode, disjoint=disjoint, covering=covering):
                                name = f"test_{mode}_{disjoint}_{covering}"
                                negative = {"Red": ["Green"]} if not disjoint else None
                                path, original = writer.write_file(
                                    name, self.lab, return_fuzzy_space=True,
                                    color_space=mode, disjoint=disjoint, covering=covering,
                                    samples=27, negative_prototypes=negative)
                                self.assertTrue(os.path.exists(path))
                                with open(path, encoding="utf-8") as stream:
                                    contents = stream.read()
                                self.assertIn("# Created by RafaConejo", contents)
                                self.assertIn("@description", contents)
                                self.assertIn("@reference", contents)
                                _, loaded = writer.read_file(path)
                                self.assertEqual(loaded.color_space, mode)
                                self.assertEqual(loaded.disjoint, disjoint)
                                self.assertEqual(loaded.covering, covering)
                                self.assertEqual(len(loaded.prototypes), 3)
                                for idx, lab in enumerate(self.lab.values()):
                                    a = original.calculate_membership_for_prototype(lab, idx)
                                    b = loaded.calculate_membership_for_prototype(lab, idx)
                                    self.assertAlmostEqual(a, b, places=5)

    def test_legacy_format_without_new_headers(self):
        """The 1.4.x header and volume ordering remain readable."""
        writer = InputFCS()
        with tempfile.TemporaryDirectory() as root:
            with patch('Source.input_output.InputFCS.get_base_path', return_value=root):
                new_path, original = writer.write_file(
                    'historical', self.lab, return_fuzzy_space=True)
                with open(new_path, encoding='utf-8') as stream:
                    rows = stream.read().splitlines()
                head = next(i for i, row in enumerate(rows) if row.startswith('@numberOfColors'))
                geo = next(i for i, row in enumerate(rows) if row == '@core')
                # Convert the new explicit one-granule rows into the historic
                # four-token representative layout to test actual old files.
                representatives = []
                j = head + 1
                for _ in range(len(self.lab)):
                    label = rows[j].strip()
                    self.assertTrue(label.endswith(' 1'))
                    representatives.append(label[:-2] + ' ' + rows[j + 1].strip())
                    j += 2
                legacy = ['@name historical', '@colorSpaceLAB', rows[head]] + representatives + rows[geo:]
                old_path = os.path.join(root, 'old.fcs')
                with open(old_path, 'w', encoding='utf-8') as stream:
                    stream.write('\n'.join(legacy) + '\n')
                _, loaded = writer.read_file(old_path)
                self.assertTrue(loaded.is_partition)
                self.assertEqual(loaded.color_space, 'LAB')
                for sample in [(50,2,-1), (35,20,30), (90,-20,12)]:
                    before = original.calculate_membership(sample)
                    after = loaded.calculate_membership(sample)
                    self.assertEqual(before.keys(), after.keys())
                    for key in before:
                        self.assertAlmostEqual(before[key], after[key], places=7)

    def test_lambda_asymmetric_roundtrip(self):
        writer = InputFCS()
        with tempfile.TemporaryDirectory() as root:
            with patch('Source.input_output.InputFCS.get_base_path', return_value=root):
                path, space = writer.write_file('lambda_test', self.lab,
                    color_space='RGB', lambda1=.35, lambda2=1.45,
                    return_fuzzy_space=True)
                _, restored = writer.read_file(path)
                self.assertAlmostEqual(restored.lambda1,.35)
                self.assertAlmostEqual(restored.lambda2,1.45)
                probe = [80,100,120]
                for idx in range(3):
                    self.assertAlmostEqual(
                        space.calculate_membership_for_prototype(probe,idx,input_space='RGB'),
                        restored.calculate_membership_for_prototype(probe,idx,input_space='RGB'),
                        places=6)

    def test_not_disjoint_retains_multiple_full_memberships(self):
        space = FuzzyColorSpaceBuilder.build(
            'overlapping', self.rgb, color_space='RGB',
            disjoint=False, covering=True,
            negative_prototypes={})
        memberships = space.calculate_membership((127.5,127.5,127.5),input_space='RGB')
        self.assertEqual(set(memberships),set(self.rgb))
        self.assertTrue(all(np.isclose(x,1.0) for x in memberships.values()))


if __name__ == "__main__":
    unittest.main()

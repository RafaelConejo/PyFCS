"""Regression tests: native CNS construction and explicit LAB/RGB FCS rebuilds."""
import os
import sys

# Get the path to the directory containing PyFCS
current_dir = os.path.dirname(__file__)
pyfcs_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))
sys.path.append(pyfcs_dir)
import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import numpy as np
from skimage import color as skcolor

from Source.colorspace.ReferenceDomain import ReferenceDomain
from Source.fuzzy.FuzzyColorSpaceBuilder import (
    FuzzyColorSpaceBuilder, rebuild_in_color_space,
)
from Source.input_output.InputFCS import InputFCS
from Source.interface.mainInterface import PyFCSApp


class ChangeModelSpaceTests(unittest.TestCase):
    COLORS = {'Pink': (254.0, 181.0, 186.0),
              'Red': (210.0, 35.0, 28.0),
              'Blue': (30.0, 76.0, 178.0)}

    def test_conversion_is_not_only_visual_and_original_untouched(self):
        src = FuzzyColorSpaceBuilder.build('original', self.COLORS, color_space='RGB')
        src.tconorm = 'max'
        before = [list(p.positive) for p in src.prototypes]
        dst = rebuild_in_color_space(src, 'LAB')
        self.assertEqual(dst.color_space, 'LAB')
        self.assertEqual(src.color_space, 'RGB')
        self.assertEqual(dst.reference_domain.bounds, ReferenceDomain.for_color_space('LAB').bounds)
        self.assertEqual(dst.tconorm, 'max')
        self.assertEqual(dst.typology_description, src.typology_description)
        self.assertNotEqual([list(p.positive) for p in dst.prototypes], before)
        back = rebuild_in_color_space(dst, 'RGB')
        np.testing.assert_allclose([p.positive for p in back.prototypes], before, atol=1e-6)
        self.assertIs(rebuild_in_color_space(src, 'RGB'), src)

    def test_all_typologies_negatives_lambda_and_auxiliary(self):
        for disjoint in (True, False):
            for covering in (True, False):
                with self.subTest(disjoint=disjoint, covering=covering):
                    choices = {'Pink': [self.COLORS['Red']],
                               'Red': [self.COLORS['Blue']],
                               'Blue': [self.COLORS['Pink']]}
                    src = FuzzyColorSpaceBuilder.build(
                        'topology', self.COLORS, color_space='RGB',
                        lambda1=0.5, lambda2=1.5,
                        disjoint=disjoint, covering=covering, samples=27,
                        negative_prototypes=choices,
                    )
                    dst = rebuild_in_color_space(src, 'LAB')
                    self.assertEqual((dst.disjoint, dst.covering), (disjoint, covering))
                    self.assertEqual((dst.lambda1, dst.lambda2), (src.lambda1, src.lambda2))
                    self.assertEqual([p.label for p in dst.prototypes], list(self.COLORS))
                    if not disjoint:
                        count = 1 + (len(dst.auxiliary_negatives) if not covering else 0)
                        for name in self.COLORS:
                            self.assertEqual(len(dst.negative_prototypes[name]), count)
                    if not covering:
                        self.assertGreater(len(dst.auxiliary_negatives), 0)
                        self.assertEqual(dst.samples, 27)

    def test_non_gamut_lab_preserves_source_model(self):
        values = {'A': (40.0, 100.0, 110.0), 'B': (65.0, 80.0, 100.0)}
        src = FuzzyColorSpaceBuilder.build('invalid_srgb', values, color_space='LAB')
        model_before = [tuple(p.positive) for p in src.prototypes]
        # Non-raising check of the gamut predicate used by the conversion.
        xyz = np.asarray([p.positive for p in src.prototypes], dtype=float)
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            as_rgb = skcolor.lab2rgb(xyz.reshape(1, -1, 3))[0]
        after = skcolor.rgb2lab(as_rgb.reshape(1, -1, 3))[0]
        self.assertGreater(np.max(np.linalg.norm(xyz - after, axis=1)), 0.05)
        self.assertEqual(src.color_space, 'LAB')
        self.assertEqual(model_before, [tuple(p.positive) for p in src.prototypes])

    def test_jfcs_original_can_be_rebuilt_without_modifying_imported_volumes(self):
        filename = Path(__file__).parent / "fixtures" / "JFCS_ISCC_NBS_BASIC.fcs"
        _, original = InputFCS().read_file(str(filename))
        before_faces = [len(p.voronoi_volume.faces) for p in original.prototypes]
        result = rebuild_in_color_space(original, 'LAB')
        self.assertEqual(original.color_space, 'RGB')
        self.assertEqual(result.color_space, 'LAB')
        self.assertEqual((result.disjoint, result.covering), (True, False))
        self.assertEqual([p.label for p in result.prototypes],
                         [p.label for p in original.prototypes])
        self.assertEqual([len(p.voronoi_volume.faces) for p in original.prototypes], before_faces)
        self.assertGreater(len(result.auxiliary_negatives), 0)

    def test_apply_changes_retains_native_rgb_and_category_negatives(self):
        src = FuzzyColorSpaceBuilder.build(
            'named', self.COLORS, color_space='RGB',
            disjoint=False, covering=True,
            negative_prototypes={'Pink': [self.COLORS['Red']],
                                 'Red': [self.COLORS['Blue']]},
        )
        # Exercise the actual editing/options route without opening GUI windows.
        app = PyFCSApp.__new__(PyFCSApp)
        app.color_data = {}
        for proto in src.prototypes:
            lab = src.lab_from_model(proto.positive)
            app.color_data[proto.label] = {
                'Color': list(lab), 'positive_prototype': np.asarray(lab),
                'fcs_original_label': proto.label,
            }
        options = app._options_from_loaded_space(src)
        self.assertEqual(options['color_space'], 'RGB')
        np.testing.assert_allclose(options['model_points']['Pink'], self.COLORS['Pink'])
        self.assertEqual(options['negative_prototypes']['Pink'], ['Red'])
        lab_points = {name: value['positive_prototype'] for name, value in app.color_data.items()}
        with TemporaryDirectory() as folder:
            with patch('Source.input_output.InputFCS.get_base_path', return_value=folder):
                path, saved = InputFCS().write_file('native', lab_points, **options, return_fuzzy_space=True)
            _, loaded = InputFCS().read_file(path)
            self.assertEqual(loaded.color_space, 'RGB')
            np.testing.assert_allclose([p.positive for p in saved.prototypes],
                                       [p.positive for p in src.prototypes], atol=0)
            np.testing.assert_allclose([p.positive for p in loaded.prototypes],
                                       [p.positive for p in src.prototypes], atol=0)
            self.assertEqual(len(saved.negative_prototypes['Pink']), 1)

if __name__ == '__main__':
    unittest.main()

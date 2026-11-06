"""Audited behavior: palette meaning, domain, overlapping cores and image quantization."""
import unittest
import os
import sys

# Get the path to the directory containing PyFCS
current_dir = os.path.dirname(__file__)
pyfcs_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))

# Add the PyFCS path to sys.path
sys.path.append(pyfcs_dir)
from types import SimpleNamespace
import numpy as np
from PIL import Image
from skimage import color as skcolor
from Source.interface.modules.ImageManager import ImageManager
from Source.fuzzy.FuzzyColorSpaceBuilder import FuzzyColorSpaceBuilder
from Source.input_output.InputFCS import InputFCS
from Source.interface.modules.ColorEvaluationManager import ColorEvaluationManager
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch


class AuditedCoreAndPalettes(unittest.TestCase):
    RGB = {"Dark": (32, 32, 32), "Bright": (224, 224, 224), "Mid": (128, 128, 128)}

    def test_ciede2000_standard_reference_and_thresholds(self):
        sample=(50.0,2.6772,-79.7751)
        reference=(50.0,0.0,-82.7485)
        value=ColorEvaluationManager.calculate_metric_value(sample,reference,"CIEDE2000")
        self.assertAlmostEqual(value,2.0425,places=4)
        for metric in ("CIEDE2000","CIE76","CIE94 Graphic Arts",
                       "CIE94 Textiles","CMC 2:1"):
            self.assertAlmostEqual(ColorEvaluationManager.calculate_metric_value(
                sample,sample,metric),0.0,places=6)
        classifier=ColorEvaluationManager.classify_metric_value
        self.assertEqual(classifier(0.8)["status"],"inside")
        self.assertEqual(classifier(1.8)["status"],"warning")
        self.assertEqual(classifier(2.0)["status"],"outside")

    def test_original_palette_is_rgb_geometry(self):
        protos = [SimpleNamespace(label=name, positive=value) for name, value in self.RGB.items()]
        np.testing.assert_array_equal(
            ImageManager.build_original_palette_uint8(protos, "RGB"),
            np.array(list(self.RGB.values()), dtype=np.uint8),
        )

    def test_original_palette_converts_lab_geometry(self):
        rgb = np.array([[245, 45, 62], [25, 177, 75]], dtype=np.float64)
        lab = skcolor.rgb2lab((rgb / 255).reshape(1, 2, 3))[0]
        protos = [SimpleNamespace(label=f"C{i}", positive=lab[i]) for i in range(2)]
        result = ImageManager.build_original_palette_uint8(protos, "LAB").astype(int)
        self.assertLessEqual(np.max(np.abs(result - rgb)), 1)

    def test_original_colors_keep_same_order_when_hex_values_duplicate(self):
        # The Data tab's HEX dictionary would collapse two distinct labels.
        protos = [SimpleNamespace(label=f"C{i}", positive=(255, 0, 0)) for i in range(2)]
        result = ImageManager.build_original_palette_uint8(protos, "RGB")
        self.assertEqual(result.shape, (2, 3))
        np.testing.assert_array_equal(result[0], result[1])

    def test_alt_palette_is_distinct_visualization(self):
        protos = [SimpleNamespace(label=name, positive=value) for name, value in self.RGB.items()]
        original = ImageManager.build_original_palette_uint8(protos, "RGB")
        alternative = ImageManager.build_alt_palette_uint8(protos)
        self.assertEqual(alternative.shape, original.shape)
        self.assertFalse(np.array_equal(alternative, original))

    def test_points_outside_reference_domain_are_unassigned(self):
        for disjoint in (True, False):
            for covering in (True, False):
                with self.subTest(disjoint=disjoint, covering=covering):
                    space = FuzzyColorSpaceBuilder.build(
                        "domain", self.RGB, color_space="RGB", disjoint=disjoint,
                        covering=covering, samples=27,
                    )
                    for outside in ((-1, 32, 32), (256, 224, 224)):
                        self.assertEqual(space.calculate_membership(outside, input_space="RGB"), {})
                        self.assertEqual(space.calculate_raw_memberships(outside, input_space="RGB"), {})
                        self.assertEqual(space.best_prototype_index(outside, input_space="RGB"), -1)
                        for i in range(len(space.prototypes)):
                            self.assertEqual(space.calculate_membership_for_prototype(outside, i, input_space="RGB"), 0)

    def test_overlapping_core_uses_nearest_representative(self):
        # With no selected negatives, every category covers the whole domain.
        space = FuzzyColorSpaceBuilder.build(
            "overlap", self.RGB, color_space="RGB", disjoint=False,
            covering=True, negative_prototypes={},
        )
        self.assertEqual(space.best_prototype_index((220, 220, 220), input_space="RGB"), 1)
        self.assertEqual(space.best_prototype_index((40, 40, 40), input_space="RGB"), 0)

    def test_corrupt_native_fcs_planes_are_detectable_before_geometry_use(self):
        colors = {"A": (35, -20, 25), "B": (75, 20, -20)}
        with TemporaryDirectory() as tmp:
            with patch("Source.input_output.InputFCS.get_base_path", return_value=tmp):
                path = Path(InputFCS().write_file("sample", colors))
            lines = path.read_text(encoding="utf-8").splitlines()
            pos = lines.index("@core") + 1
            parts = lines[pos].split()
            self.assertTrue(InputFCS._valid_plane_data(parts[:4]))
            parts[0] = "nan"
            self.assertFalse(InputFCS._valid_plane_data(parts[:4]))
            parts[0] = "0"
            parts[1:4] = ["0", "0", "1"]
            self.assertFalse(InputFCS._valid_plane_data(parts[:4]))

    def test_partition_geometry_matches_nearest_site(self):
        from Source.geometry.Point import Point
        rng = np.random.default_rng(417)
        for mode in ("LAB", "RGB"):
            samples = ({"A": (20,-55,30), "B": (65,40,-45),
                        "C": (84,-5,70), "D": (43,20,5)} if mode == "LAB" else
                       {"A": (0,0,0), "B": (255,0,0),
                        "C": (0,255,0), "D": (0,0,255)})
            space = FuzzyColorSpaceBuilder.build("nearest", samples, color_space=mode)
            mins = [space.reference_domain.get_min(i) for i in range(3)]
            maxs = [space.reference_domain.get_max(i) for i in range(3)]
            centers = np.asarray(list(samples.values()), dtype=float)
            for xyz in rng.uniform(mins,maxs,(200,3)):
                hits = [i for i,p in enumerate(space.prototypes)
                        if p.voronoi_volume.isInside(Point(*xyz))]
                self.assertEqual(hits,[int(np.argmin(np.linalg.norm(centers-xyz,axis=1)))])

    def test_single_and_all_use_identical_quantization(self):
        mgr = ImageManager()
        image = Image.fromarray(np.array([[[10, 20, 30], [10, 20, 30],
                                           [100, 105, 110]]], dtype=np.uint8))
        for mode in ("RGB", "LAB"):
            fake = SimpleNamespace(color_space=mode)
            a,b,h,w,scale,source = mgr._unique_model_colors(image, fake)
            self.assertEqual((h,w),(1,3))
            self.assertEqual(len(a),2)
            self.assertEqual(b[0],b[1])
            self.assertEqual(source,mode)

if __name__ == '__main__':
    unittest.main()

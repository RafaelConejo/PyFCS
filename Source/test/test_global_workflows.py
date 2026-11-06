
"""Integration tests for the main PyFCS workflows.

Run directly with:
    python -m unittest Source.test.test_global_workflows -v

Temporary files and synthetic images avoid modifying user data. No GUI window
is required. These tests are also included in run_full_suite.py.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image
from skimage import color as skcolor

from Source.fuzzy.FuzzyColorSpaceBuilder import (
    FuzzyColorSpaceBuilder,
    rebuild_in_color_space,
)
from Source.input_output.InputFCS import InputFCS
from Source.input_output.InputCNS import InputCNS
from Source.interface.modules.ImageManager import ImageManager
from Source.interface.modules.VisualManager import VisualManager
from Source.interface.modules.ColorEvaluationManager import ColorEvaluationManager


class GlobalWorkflowsTests(unittest.TestCase):
    """Exercise construction, serialization, mapping and evaluation together."""

    # Distinct, reproducible sRGB colors in gamut, with no duplicated sites.
    RGB = {
        "Dark": (30.0, 45.0, 55.0),
        "Red": (200.0, 40.0, 50.0),
        "Green": (60.0, 185.0, 75.0),
        "Blue": (40.0, 85.0, 205.0),
    }

    @classmethod
    def setUpClass(cls):
        """Prepare LAB coordinates from the shared RGB test palette."""
        coords = np.asarray(
            list(cls.RGB.values()),
            dtype=float
        ).reshape(1, -1, 3) / 255.0

        lab = skcolor.rgb2lab(coords)[0]
        cls.LAB = dict(zip(cls.RGB, [tuple(v) for v in lab]))

    def test_eight_constructions_roundtrip_and_raw_memberships(self):
        """All four typologies x LAB/RGB survive write/read unchanged."""
        writer = InputFCS()

        probes_rgb = np.array([
            [48, 52, 80],
            [100, 95, 125],
            [150, 80, 75],
            [190, 150, 145],
            [70, 205, 105],
        ], dtype=float)

        probes_lab = skcolor.rgb2lab(
            (probes_rgb / 255).reshape(1, -1, 3)
        )[0]

        # Each construction is saved and reopened with the same probe colors.
        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "Source.input_output.InputFCS.get_base_path",
                return_value=tmp
            ):
                for mode in ("LAB", "RGB"):
                    for disjoint in (True, False):
                        for covering in (True, False):
                            with self.subTest(
                                mode=mode,
                                disjoint=disjoint,
                                covering=covering
                            ):
                                # Non-disjoint models use category-specific negatives.
                                neg = (
                                    None
                                    if disjoint
                                    else {"Red": ["Blue"], "Blue": ["Red"]}
                                )

                                model_points = (
                                    self.RGB if mode == "RGB" else None
                                )

                                path, original = writer.write_file(
                                    f"e2e_{mode}_{disjoint}_{covering}",
                                    self.LAB,
                                    color_space=mode,
                                    model_points=model_points,
                                    disjoint=disjoint,
                                    covering=covering,
                                    samples=(0 if covering else 27),
                                    negative_prototypes=neg,
                                    return_fuzzy_space=True,
                                )

                                self.assertTrue(Path(path).is_file())

                                _, loaded = writer.read_file(path)

                                self.assertEqual(
                                    (loaded.disjoint, loaded.covering),
                                    (disjoint, covering)
                                )
                                self.assertEqual(loaded.color_space, mode)
                                self.assertEqual(
                                    [p.label for p in loaded.prototypes],
                                    list(self.RGB)
                                )

                                if not covering:
                                    self.assertGreater(
                                        len(loaded.auxiliary_negatives),
                                        0
                                    )

                                for point in probes_lab:
                                    a = original.calculate_raw_memberships(
                                        point,
                                        input_space="LAB",
                                        include_zeros=True
                                    )
                                    b = loaded.calculate_raw_memberships(
                                        point,
                                        input_space="LAB",
                                        include_zeros=True
                                    )

                                    for label in self.RGB:
                                        self.assertAlmostEqual(
                                            a[label],
                                            b[label],
                                            places=6
                                        )

    def test_rgb_native_image_single_all_and_palette(self):
        """Individual maps, winner map and two palettes share the same RGB model."""
        space = FuzzyColorSpaceBuilder.build(
            "e2e-image",
            self.RGB,
            color_space="RGB"
        )

        manager = ImageManager()

        pixels = np.array([
            [[30, 45, 55], [200, 40, 50], [60, 185, 75]],
            [[40, 85, 205], [200, 40, 50], [30, 45, 55]],
        ], dtype=np.uint8)

        image = Image.fromarray(pixels, "RGB")

        # Validate winner assignment, single-color membership and recoloring.
        winning = manager.get_best_prototype_label_map(image, space)

        self.assertEqual(winning.shape, (2, 3))
        np.testing.assert_array_equal(
            winning,
            [[0, 1, 2], [3, 1, 0]]
        )

        gray = manager.get_proto_percentage(
            space.prototypes,
            image,
            space,
            1
        )

        self.assertEqual(gray.shape, (2, 3))
        self.assertEqual(int(gray[0, 1]), 255)
        self.assertEqual(int(gray[1, 1]), 255)
        self.assertEqual(int(gray[0, 0]), 0)

        mapped = manager.colorize_membership_map(gray, pixels)

        np.testing.assert_array_equal(
            mapped[0, 1],
            pixels[0, 1]
        )
        np.testing.assert_array_equal(
            mapped[0, 0],
            [0, 0, 0]
        )

        # The original palette preserves prototype colors; the alternative does not.
        palette = manager.build_original_palette_uint8(
            space.prototypes,
            "RGB"
        )

        np.testing.assert_array_equal(
            palette,
            np.array(list(self.RGB.values()), dtype=np.uint8)
        )

        alt = manager.build_alt_palette_uint8(space.prototypes)

        self.assertEqual(alt.shape, palette.shape)
        self.assertFalse(np.array_equal(alt, palette))

    def test_change_color_space_is_explicit_and_non_destructive(self):
        """Changing color space rebuilds geometry without mutating the source."""
        space = FuzzyColorSpaceBuilder.build(
            "before",
            self.RGB,
            color_space="RGB"
        )

        original_coords = [
            tuple(p.positive)
            for p in space.prototypes
        ]

        # A rebuilt model must be independent of its original RGB geometry.
        lab = rebuild_in_color_space(space, "LAB")

        self.assertIsNot(lab, space)
        self.assertEqual(space.color_space, "RGB")
        self.assertEqual(lab.color_space, "LAB")

        restored = rebuild_in_color_space(lab, "RGB")

        np.testing.assert_allclose(
            [p.positive for p in restored.prototypes],
            original_coords,
            atol=1e-5
        )

        self.assertEqual(
            original_coords,
            [tuple(p.positive) for p in space.prototypes]
        )

        for p in space.prototypes:
            self.assertAlmostEqual(
                space.calculate_membership_for_prototype(
                    p.positive,
                    space.prototypes.index(p),
                    input_space="MODEL"
                ),
                1.0,
                places=6
            )

    def test_visual_closed_surfaces_and_membership_geometry_unchanged(self):
        """Rendering all solids cannot insert planes into membership volumes."""
        for mode, points in (
            ("RGB", self.RGB),
            ("LAB", self.LAB)
        ):
            with self.subTest(mode=mode):
                space = FuzzyColorSpaceBuilder.build(
                    "visual",
                    points,
                    color_space=mode
                )

                probe = np.asarray(
                    next(iter(points.values())),
                    dtype=float
                )

                # Preparing display polygons must not mutate membership planes.
                before = space.calculate_raw_memberships(
                    probe,
                    input_space="MODEL",
                    include_zeros=True
                )

                counts = [
                    [
                        len(p.voronoi_volume.getFaces())
                        for p in group
                    ]
                    for group in (
                        space.cores,
                        space.prototypes,
                        space.supports
                    )
                ]

                for group in (
                    space.cores,
                    space.prototypes,
                    space.supports
                ):
                    for p in group:
                        polygons = VisualManager._cached_display_polygons(
                            p,
                            space.reference_domain
                        )

                        self.assertTrue(polygons)
                        self.assertTrue(
                            all(len(face) >= 3 for face in polygons)
                        )

                after = space.calculate_raw_memberships(
                    probe,
                    input_space="MODEL",
                    include_zeros=True
                )

                self.assertEqual(before, after)

                self.assertEqual(
                    counts,
                    [
                        [
                            len(p.voronoi_volume.getFaces())
                            for p in group
                        ]
                        for group in (
                            space.cores,
                            space.prototypes,
                            space.supports
                        )
                    ]
                )

    def test_jfcs_compatibility_metrics_and_invalid_input(self):
        """Validate JFCS loading, RGB ranges and CIEDE2000 accuracy."""
        fixture_dir = Path(__file__).resolve().parent / "fixtures"

        # Validate the existing JFCS reference files.
        for filename in ("partition_jfcs.fcs", "noncover_jfcs.fcs"):
            with self.subTest(filename=filename):
                _, space = InputFCS().read_file(str(fixture_dir / filename))

                self.assertTrue(space.prototypes)
                self.assertEqual(space.color_space, "RGB")

                for proto in space.prototypes:
                    self.assertEqual(len(proto.positive), 3)
                    self.assertTrue(np.all(np.isfinite(proto.positive)))

        # Validate RGB input ranges.
        self.assertFalse(InputCNS.rgb_values_within_range([[999, 0, 0]]))
        self.assertTrue(InputCNS.rgb_values_within_range([[255, 0, 0]]))

        # Check CIEDE2000 against a reference value.
        result = ColorEvaluationManager.calculate_metric_value(
            (50., 2.6772, -79.7751),
            (50., 0., -82.7485),
            "CIEDE2000"
        )

        self.assertAlmostEqual(result, 2.0425, places=4)


if __name__ == "__main__":
    unittest.main()

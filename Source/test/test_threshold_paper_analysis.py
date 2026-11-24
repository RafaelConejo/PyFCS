"""Regression tests for the independent PT/AT paper analysis.

Run: python -m unittest Source.test.test_threshold_paper_analysis -v
These tests use a tiny synthetic LAB model, not your unpublished dental JSON.
"""
import csv
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import os
import sys

# Get the path to the directory containing PyFCS
current_dir = os.path.dirname(__file__)
pyfcs_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))

# Add the PyFCS path to sys.path
sys.path.append(pyfcs_dir)

from Source.colorspace.ReferenceDomain import ReferenceDomain
from Source.fuzzy.FuzzyColorSpaceBuilder import FuzzyColorSpaceBuilder
from Source.geometry.Point import Point
from Source.interface.modules.ColorEvaluationManager import ColorEvaluationManager
from Source.test.generate_threshold_method_figures import (
    parse_args as method_parse_args, matching_cached_grids,
    axis_limits_from_at, make_figure,
)
from Source.test.threshold_paper_analysis import (
    analyse_sample, canonical_label, compare_limits, exhaustive_lattice_keys,
    inside_mask, mpl_paper_style, read_limits, sample_uniform_inside, search_grid,
    wilson_interval, parse_args, export_core_ranges, figure_core_perceptual_split,
    figure_membership_facets, figure_3d_regions, figure_fraction,
)


class PaperAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.space = FuzzyColorSpaceBuilder.build(
            "toy_lab", {"A1": (75.0, 1.0, 14.0), "A2": (71.0, 3.0, 19.0)},
            color_space="LAB", reference_domain=ReferenceDomain(68, 82, -6, 8, 5, 27),
            disjoint=True, covering=True, improve_geometry=False,
        )

    def test_mask_matches_volume_geometry(self):
        rng = np.random.default_rng(2)
        q = rng.uniform([68, -6, 5], [82, 8, 27], size=(3000, 3))
        for proto in [self.space.cores[0], self.space.prototypes[0], self.space.supports[0]]:
            actual = inside_mask(proto.voronoi_volume, q)
            expected = np.array([proto.voronoi_volume.isInside(Point(*x)) for x in q])
            self.assertTrue(np.array_equal(actual, expected))

    def test_sample_is_inside_and_core_has_unit_membership(self):
        rng = np.random.default_rng(43)
        q, meta = sample_uniform_inside(self.space.cores[0].voronoi_volume,
                                        self.space.reference_domain, 120, rng)
        self.assertEqual(q.shape, (120, 3))
        self.assertTrue(inside_mask(self.space.cores[0].voronoi_volume, q).all())
        self.assertGreater(meta["acceptance"], 0)
        row, points = analyse_sample(self.space, 0, "core", 120, rng, 0.9)
        self.assertEqual(row["n_high_mu"], 120)
        self.assertTrue(np.all(points.membership_raw == 1.0))
        self.assertEqual(row["n_pt"] + row["n_at"] - row["n_pt"], row["n_at"])

    def test_alpha_memberships_are_bounded(self):
        row, points = analyse_sample(self.space, 0, "alpha", 180,
                                     np.random.default_rng(76), 0.9)
        self.assertTrue(points.membership_raw.between(0.0, 1.0).all())
        self.assertEqual(len(points), 180)
        self.assertLessEqual(row["n_pt"], row["n_at"])

    def test_exhaustive_validation_agrees_with_joint_bfs(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = ColorEvaluationManager(output_dir=tmp)
            data = search_grid(manager, self.space, "core", [0], 0.5, True, 250_000)
        self.assertEqual(len(data), 1)
        self.assertTrue(data[0]["PT_complete"])
        self.assertTrue(data[0]["AT_complete"])
        self.assertGreater(data[0]["bfs_at_n"], data[0]["bfs_pt_n"])

    def test_default_settings_are_all_shades_and_delta005(self):
        args = parse_args([])
        self.assertEqual(args.step, 0.05)
        self.assertEqual(args.layers, ["core", "alpha"])
        self.assertEqual(args.shades, [])
        self.assertEqual(args.space.name, "vita_no_covering_max.json")
        self.assertEqual(args.out.parent, Path(__file__).resolve().parent)
        self.assertEqual(args.out.name, "paper_thresholds_vita_max_delta005")
        self.assertEqual(args.scatter_shades, [])

    def test_dental_grid_step_005_on_small_reference_domain(self):
        """Test the actual requested 0.05 step without a costly large space."""
        mini = FuzzyColorSpaceBuilder.build(
            "mini005", {"A1": (70.10, 0.10, 10.10), "A2": (70.40, 0.40, 10.40)},
            color_space="LAB", reference_domain=ReferenceDomain(70, 70.5, 0, 0.5, 10, 10.5),
            disjoint=True, covering=True, improve_geometry=False,
        )
        with tempfile.TemporaryDirectory() as tmp:
            manager = ColorEvaluationManager(output_dir=tmp)
            results = search_grid(manager, mini, "core", [0], 0.05, False, 200000)
        self.assertEqual(len(results), 1)
        self.assertGreater(results[0]["bfs_at_n"], 0)
        self.assertLessEqual(results[0]["bfs_pt_n"], results[0]["bfs_at_n"])
        self.assertEqual(results[0]["step"], 0.05)

    def test_resume_checkpoint_avoids_repeating_bfs(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = ColorEvaluationManager(output_dir=tmp)
            rng = np.random.default_rng(10)
            first = search_grid(manager, self.space, "core", [0], 0.5,
                                False, 250000, cache_dir=Path(tmp) / "cache",
                                model_sha="synthetic", scatter_rng=rng)
            class FailIfCalled:
                def filter_points_with_thresholds(self, *args, **kwargs):
                    raise AssertionError("Cached BFS must not be repeated")
            saved = search_grid(FailIfCalled(), self.space, "core", [0], 0.5,
                                False, 250000, cache_dir=Path(tmp) / "cache",
                                model_sha="synthetic")
            self.assertEqual(first, saved)
            self.assertTrue((Path(tmp) / "cache" / "core_A1_d0.5.npz").is_file())

    def test_core_ranges_and_article_figures_are_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            manager = ColorEvaluationManager(output_dir=tmp)
            grid = pd.DataFrame(search_grid(manager, self.space, "core", [0,1],
                                            0.5, False, 250000))
            ranges = export_core_ranges(grid, out)
            self.assertEqual(list(ranges.shade), ["A1", "A2"])
            self.assertGreaterEqual(float(ranges.AT_L_max.iloc[0]),
                                    float(ranges.PT_L_max.iloc[0]))
            for target in ("table_core_ranges_PT_AT.csv", "table_core_limits_PT.tex",
                           "table_core_limits_AT.tex"):
                self.assertTrue((out / target).is_file())
            for layer in ("core", "alpha"):
                self.assertIn(layer, ("core", "alpha"))
            samples = []
            summary = []
            for layer in ("core", "alpha"):
                for i in (0,1):
                    row, points = analyse_sample(self.space, i, layer, 120,
                                                 np.random.default_rng(100+i), 0.9)
                    summary.append(row)
                    samples.append(points)
            mpl_paper_style()
            figure_core_perceptual_split(pd.DataFrame(summary), out)
            figure_membership_facets(pd.concat(samples, ignore_index=True), out)
            for name in ("fig_core_pt_at_outside.pdf", "fig_membership_all_16_shades.png"):
                self.assertTrue((out / name).is_file())
            cloud = pd.DataFrame({"shade": ["A1", "A1", "A2", "A2"],
                                  "layer": ["core"] * 4,
                                  "regime": ["PT", "AT_ONLY", "PT", "AT_ONLY"],
                                  "L": [75,76,71,72], "a": [1,1,3,3],
                                  "b": [14,15,19,19]})
            p = {"A1": np.asarray(self.space.prototypes[0].positive),
                 "A2": np.asarray(self.space.prototypes[1].positive)}
            figure_3d_regions(cloud, p, "core", out)
            self.assertTrue((out / "fig_3d_regions_core.pdf").is_file())

    def test_wilson_interval(self):
        lo, hi = wilson_interval(30, 100)
        self.assertLess(lo, 0.3)
        self.assertGreater(hi, 0.3)
        self.assertEqual(wilson_interval(0, 1)[0], 0)

    def test_wilson_extreme_fractions_plot_without_negative_yerr(self):
        """Regression: at 0% the lower Wilson bound must not be > 0 by rounding."""
        n = 8000
        rows = []
        for shade, pt_count, at_count in (("A1", 0, 0), ("A2", n, n)):
            row = {"shade": shade, "layer": "core", "n": n,
                   "pt_fraction": pt_count / n, "at_fraction": at_count / n}
            for prefix, count in (("pt", pt_count), ("at", at_count)):
                low, high = wilson_interval(count, n)
                self.assertLessEqual(low, count / n)
                self.assertGreaterEqual(high, count / n)
                row[f"{prefix}_ci95_low"] = low
                row[f"{prefix}_ci95_high"] = high
            rows.append(row)
        with tempfile.TemporaryDirectory() as tmp:
            mpl_paper_style()
            figure_fraction(pd.DataFrame(rows), Path(tmp))
            self.assertTrue((Path(tmp) / "fig_volume_fraction_core.png").is_file())
            self.assertTrue((Path(tmp) / "fig_volume_fraction_core.pdf").is_file())

    def test_method_figure_settings(self):
        options = method_parse_args([])
        self.assertEqual(options.space.name, "vita_no_covering_max.json")
        self.assertEqual(options.layer, "alpha")
        self.assertEqual(options.step, 0.05)
        self.assertEqual(options.analysis_dir.parent, Path(__file__).resolve().parent)
        self.assertIsNone(options.out)

    def test_method_figures_are_separate_and_use_real_point_coordinates(self):
        cloud = pd.DataFrame({
            "shade": ["A1", "A1", "A2", "A2"],
            "regime": ["PT", "AT_ONLY", "PT", "AT_ONLY"],
            "L": [75, 76, 71, 72], "a": [1, 2, 3, 4],
            "b": [14, 15, 19, 20], "layer": ["alpha"] * 4,
        })
        labels = ["A1", "A2"]
        prototypes = {"A1": np.array([75., 1., 14.]),
                      "A2": np.array([71., 3., 19.])}
        limits = axis_limits_from_at(cloud, prototypes, labels)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            pt = make_figure(cloud, prototypes, labels, "alpha", "PT", limits, folder, dpi=90)
            at = make_figure(cloud, prototypes, labels, "alpha", "AT", limits, folder, dpi=90)
            self.assertEqual({p.name for p in pt}, {"fig_method_alpha_PT.png", "fig_method_alpha_PT.pdf"})
            self.assertEqual({p.name for p in at}, {"fig_method_alpha_AT.png", "fig_method_alpha_AT.pdf"})
            for path in pt + at:
                self.assertTrue(path.is_file(), path)
                self.assertGreater(path.stat().st_size, 1000)
            self.assertFalse(np.array_equal(limits[0], limits[1]))

    def test_method_figure_cache_checks_real_model_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = ColorEvaluationManager(output_dir=tmp)
            cache = Path(tmp) / "_completed_grids"
            search_grid(manager, self.space, "alpha", [0], 0.5, False, 250000,
                        cache_dir=cache, model_sha="toy-good")
            found, reason = matching_cached_grids(cache, "toy-good", "alpha", ["A1"], 0.5)
            self.assertTrue(found, reason)
            found, reason = matching_cached_grids(cache, "toy-bad", "alpha", ["A1"], 0.5)
            self.assertFalse(found)

    def test_max_json_geometry_when_available(self):
        from Source.test.threshold_paper_analysis import load_space
        options = method_parse_args([])
        if not options.space.is_file():
            self.skipTest("The dental JSON is not in this testing environment")
        _, model = load_space(options.space)
        self.assertEqual(model.color_space, "LAB")
        self.assertEqual(len(model.prototypes), 16)
        self.assertFalse(model.covering)
        self.assertTrue(model.disjoint)

    def test_csv_quoted_ranges_and_canonical_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for variant in ("cpt", "cat", "apt", "aat"):
                with (d / (variant + '.csv')).open('w', encoding='utf-8', newline='') as f:
                    w = csv.writer(f, delimiter=';')
                    w.writerow(('Volume', 'L*', 'a*', 'b*'))
                    w.writerow(('A3-5', '"69.34 - 72.09"', '"-1.57 - 0.93"', '"11.52 - 15.27"'))
            self.assertIn('A3.5', read_limits(d / 'cpt.csv'))
            mpl_paper_style()
            df = compare_limits([d / (nm+'.csv') for nm in ('cpt','cat','apt','aat')], d)
            self.assertEqual(len(df), 3)
            self.assertTrue((d / 'fig_compare_core_vs_alpha_limits.pdf').is_file())


if __name__ == "__main__":
    unittest.main()

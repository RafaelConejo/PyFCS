"""Regression tests for the PyFCS/JFCS FCS comparison tool.

An identical-file comparison must report no differences, while incompatible
topologies must be rejected before membership sampling.
"""
import unittest
import contextlib
import io
from pathlib import Path

from Source.input_output.InputFCS import InputFCS
from Source.test.compare_fcs_engines import (
    check_compatible, configuration_differences, geometry_report, compare_region, main,
)

# Reference spaces shared with the other test modules.
FIXTURES = Path(__file__).resolve().parent / "fixtures"


class ComparisonToolRegressionTests(unittest.TestCase):
    def test_identical_file_has_identical_geometry_and_memberships(self):
        """Compare a stored FCS against itself as a zero-difference control."""
        _, same = InputFCS().read_file(str(FIXTURES / "partition_pyfcs.fcs"))
        labels, _ = check_compatible(same, same, 1e-6)
        details = geometry_report(same, same, labels, 1e-5)
        for value in details.values():
            self.assertEqual(value["pyfcs_faces"], value["jfcs_faces"])
            self.assertEqual(value["matching_planes"], value["pyfcs_faces"])
        # Identical inputs must also produce identical sampled memberships.
        out = compare_region(same, same, labels,
                             [0., 0., 0.], [255., 255., 255.],
                             40, 723, 1e-5, 3, "self")
        self.assertEqual(out["raw_different_points"], 0)
        self.assertEqual(out["mapping_winner_changes"], 0)
        self.assertEqual(out["normalized"]["different_points"], 0)

    def test_different_topologies_fail_before_sampling(self):
        """Detect incompatible typologies without deliberately raising an exception."""
        _, partition = InputFCS().read_file(str(FIXTURES / "partition_pyfcs.fcs"))
        _, noncover = InputFCS().read_file(str(FIXTURES / "noncover_pyfcs.fcs"))

        differences = configuration_differences(partition, noncover, 1e-6)
        self.assertTrue(any(item.startswith("typology:") for item in differences))
        self.assertEqual(configuration_differences(partition, partition, 1e-6), [])

        # The command-line tool rejects the same pair without raising an exception.
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()) as error_output:
            exit_code = main([
                "--pyfcs", str(FIXTURES / "partition_pyfcs.fcs"),
                "--jfcs", str(FIXTURES / "noncover_pyfcs.fcs"),
                "--points", "1", "--margins", "0",
            ])
        self.assertEqual(exit_code, 2)
        self.assertIn("COMPARISON NOT VALID", error_output.getvalue())
        self.assertIn("typology", error_output.getvalue())


if __name__ == "__main__":
    unittest.main()

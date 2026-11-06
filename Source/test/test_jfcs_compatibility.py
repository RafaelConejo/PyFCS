"""Compatibility regression fixtures from original JFCS by José Manuel Soto.

Run from the directory containing Source/:
  python -m unittest Source.test.test_jfcs_compatibility -v
"""
import os
import sys

# Get the path to the directory containing PyFCS
current_dir = os.path.dirname(__file__)
pyfcs_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))

# Add the PyFCS path to sys.path
sys.path.append(pyfcs_dir)


import unittest
import tempfile
from pathlib import Path
import numpy as np
from Source.input_output.InputCNS import InputCNS
from Source.input_output.InputFCS import InputFCS

FIXTURES = Path(__file__).parent / "fixtures"


class JFCSCompatibilityTests(unittest.TestCase):
    def test_original_jfcs_cns_header_and_prototypes(self):
        parser = InputCNS()
        colors = parser.read_file(str(FIXTURES / "JFCS_ISCC_NBS_BASIC.cns"))
        self.assertEqual(parser.last_color_space, "RGB")
        self.assertEqual(len(colors), 13)
        self.assertEqual(list(colors), [
            "Pink", "Red", "Orange", "Brown", "Yellow", "Olive",
            "Yellow-Green", "Green", "Blue", "Purple", "White", "Gray", "Black",
        ])
        np.testing.assert_allclose(colors["Pink"]["Color"], (254, 181, 186))
        np.testing.assert_allclose(colors["Black"]["Color"], (7, 7, 7))

    def test_original_jfcs_fcs_per_face_geometry(self):
        colors, space = InputFCS().read_file(str(FIXTURES / "JFCS_ISCC_NBS_BASIC.fcs"))
        self.assertEqual(len(colors), 13)
        self.assertEqual(space.color_space, "RGB")
        self.assertFalse(space.covering)
        self.assertTrue(space.disjoint)
        self.assertEqual(space.description, "DISJOINT and NON-COVERING")
        self.assertEqual(space.reference_domain.bounds, (0.,255.,0.,255.,0.,255.))
        self.assertEqual(space.samples, 216)
        self.assertEqual(space.source_file_format, "JFCS_ATOMIC")
        self.assertEqual(sum(len(proto.voronoi_volume.faces) for proto in space.prototypes),257)
        for i, p in enumerate(space.prototypes):
            self.assertEqual(len(p.voronoi_volume.faces), len(space.cores[i].voronoi_volume.faces))
            self.assertEqual(len(p.voronoi_volume.faces), len(space.supports[i].voronoi_volume.faces))
            self.assertAlmostEqual(space.calculate_membership_for_prototype(
                p.positive, i, input_space="MODEL"), 1., places=6)

    def test_original_jfcs_unquoted_labels_with_spaces(self):
        original = (FIXTURES / "JFCS_ISCC_NBS_BASIC.fcs").read_text(encoding="utf-8")
        modified = original.replace("Pink\t254.0\t181.0\t186.0\tfalse",
                                    "Light Pink\t254.0\t181.0\t186.0\tfalse", 1)
        self.assertNotEqual(original, modified)
        with tempfile.TemporaryDirectory() as folder:
            filepath = Path(folder) / "JFCS_with_spaces.fcs"
            filepath.write_text(modified, encoding="utf-8")
            colors, space = InputFCS().read_file(str(filepath))
            self.assertIn("Light Pink", colors)
            self.assertEqual(space.prototypes[0].label, "Light Pink")

    def test_original_jfcs_cns_and_fcs_coordinates_match(self):
        crisps = InputCNS().read_file(str(FIXTURES / "JFCS_ISCC_NBS_BASIC.cns"))
        _, space = InputFCS().read_file(str(FIXTURES / "JFCS_ISCC_NBS_BASIC.fcs"))
        for p in space.prototypes:
            np.testing.assert_allclose(p.positive, crisps[p.label]["Color"], atol=1e-9)

if __name__ == "__main__":
    unittest.main()

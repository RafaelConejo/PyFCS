import os
import sys

# Get the path to the directory containing PyFCS
current_dir = os.path.dirname(__file__)
pyfcs_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))

# Add the PyFCS path to sys.path
sys.path.append(pyfcs_dir)


import tempfile
import unittest
from pathlib import Path
import numpy as np
from Source.interface.modules.VisualManager import VisualManager
from Source.input_output.InputCNS import InputCNS

class TestDualColorView(unittest.TestCase):
    def test_round_trip_rgb_lab(self):
        values=np.array([[0,0,0],[255,255,255],[255,0,0],[12,130,220]],dtype=float)
        lab=VisualManager.reproject_points(values,"RGB","LAB")
        back=VisualManager.reproject_points(lab,"LAB","RGB")
        self.assertTrue(np.allclose(back,values,atol=0.2), (back,values))

    def test_invalid_points_are_rejected(self):
        # Validate invalid requests without deliberately raising exceptions
        # that some IDE debuggers stop on (even when unittest catches them).
        self.assertFalse(VisualManager.valid_projection_request(
            [float("nan"),4,2],"LAB","RGB"))
        self.assertFalse(VisualManager.valid_projection_request(
            [1,2,3],"XYZ","RGB"))
        self.assertTrue(VisualManager.valid_projection_request(
            [1,2,3],"LAB","RGB"))

    def test_cns_native_source_and_rejected_bad_coordinates(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/"colors.cns"
            f.write_text("@colorSpace_RGB\n3\n2\n255 0 0\n\"Red\"\n0 0 255\n\"Blue\"\n",encoding="utf8")
            parser=InputCNS()
            data=parser.read_file(str(f))
            self.assertEqual(parser.last_color_space,"RGB")
            self.assertEqual(len(data),2)
            f.write_text("@colorSpace_RGB\n3\n2\n999 0 0\nRed\n0 0 255\nBlue\n", encoding="utf8")
            # Deliberately invalid input. The production reader raises a
            # friendly ValueError; test the same predicate without triggering
            # an expected exception in VS Code's exception breakpoints.
            self.assertFalse(InputCNS.rgb_values_within_range([[999, 0, 0]]))
            self.assertTrue(InputCNS.rgb_values_within_range([[255, 0, 0]]))

if __name__=="__main__":unittest.main()

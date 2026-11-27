"""Regression tests for JSON presentation and external evaluation streaming."""
import io
import json
import unittest
import numpy as np
from Source.input_output.InputJSON import InputJSON
from Source.test.cases.java_comparison.compare_java_evaluations import JSONStream, Metrics, validate_batch


class JavaEvaluationToolsTests(unittest.TestCase):
    def test_compact_format_roundtrip(self):
        doc={'negatives': [[91.0,174.0,227.0],[-0.0,1.2345678901234567,2.0]],
             'plane':[0.25,0.5,-1.0,234.00000000001], 'other': {'text':'a [1, 2, 3] café', 'bools':[True,False]}}
        result=InputJSON.format_document(doc)
        self.assertIn('[91.0, 174.0, 227.0]', result)
        self.assertEqual(json.loads(result),doc)
        with self.assertRaises(ValueError):
            InputJSON.format_document({'x':[float('nan'),0,0]})

    def test_stream_across_chunks(self):
        row={'rgb':[92,131,238],'membership':[0.12345678901234567,1]}
        doc={'color_space':'RGB','num_samples':25000,'fuzzy_colors':['A','B'],'samples':[row]*25000}
        s=JSONStream(io.StringIO(json.dumps(doc)))
        self.assertEqual(s.header()['num_samples'],25000)
        self.assertEqual(sum(r==row for r in s.samples()),25000)

    def test_stream_rejects_truncation_and_duplicate_keys(self):
        for malformed in ['{"samples":[{"rgb":[1,2,3]}', '{"samples":[{"rgb":0,"rgb":1}]}', '{"samples":[]}garbage']:
            with self.subTest(malformed=malformed), self.assertRaises(ValueError):
                s=JSONStream(io.StringIO(malformed)); s.header(); list(s.samples())

    def test_metrics_and_range_validation(self):
        rgb,ref=validate_batch([{'rgb':[1,2,3],'membership':[1,0]},{'rgb':[3,2,1],'membership':[0,0]}],2)
        pred=np.array([[1,.5],[0,0]])
        m=Metrics(['A','B'],1e-6); m.update(rgb,ref,pred,0); r=m.result()
        self.assertEqual(r['mae'],.125)
        self.assertEqual(r['samples_all_within_tolerance_fraction'],.5)
        self.assertEqual(r['winner_set_agreement'],1)
        with self.assertRaises(ValueError): validate_batch([{'rgb':[1,2,300],'membership':[0,0]}],2)

if __name__=='__main__': unittest.main()

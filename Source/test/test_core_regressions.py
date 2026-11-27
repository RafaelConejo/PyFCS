"""Regression checks for the pre-Java stability and visualization audit."""
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

from Source.fuzzy.ColorHierarchy import ColorHierarchy
from Source.fuzzy.FuzzyColorSpaceBuilder import FuzzyColorSpaceBuilder
from Source.geometry.Voronoi import Voronoi
from Source.input_output.InputJSON import InputJSON
from Source.interface.modules.VisualManager import VisualManager


def reference_clip(volume, domain):
    """The pre-audit clipping loop, retaining the exact polygon order."""
    eps, merge_eps = Voronoi.DEFAULT_EPS, Voronoi.DEFAULT_MERGE_EPS
    faces = Voronoi._create_domain_faces(domain)
    rep = volume.getRepresentative()
    for face in volume.getFaces():
        if face.isDomainBoundary():
            continue
        plane = face.getPlane()
        normal = np.array([plane.A, plane.B, plane.C], dtype=float)
        offset = float(plane.D)
        length = float(np.linalg.norm(normal))
        if length <= eps:
            continue
        if float(np.dot(normal, [rep.x, rep.y, rep.z]) + offset) < 0:
            normal, offset = -normal, -offset
        normal /= length
        offset /= length
        vertices = Voronoi._collect_vertices(faces)
        if not len(vertices):
            return []
        if np.min(vertices @ normal + offset) >= -eps:
            continue
        faces = Voronoi._clip_polyhedron(faces, normal, offset,
                                        face.getSourceIndex(), eps, merge_eps)
        if not faces:
            return []
    return [np.asarray(f.vertices, dtype=float) for f in faces
            if f.vertices is not None and len(f.vertices) >= 3]


class PreJavaAuditTests(unittest.TestCase):
    RGB = {'Warm': {'red': [230, 30, 30], 'yellow': [220, 210, 30]},
           'Cold': {'blue': [25, 30, 230], 'green': [30, 210, 40]}}
    HIERARCHY = {'A': [{'category': 'Warm'}, {'category': 'Cold'}],
                 'B': [{'category': 'Warm'}, {'granule': 'blue'}],
                 'Root': [{'category': 'A'}, {'category': 'B'}]}

    def test_shared_paths_preserve_multiplicity_and_order(self):
        base = [SimpleNamespace(label=c, prototypes=[SimpleNamespace(label=g) for g in gs])
                for c, gs in self.RGB.items()]
        graph = ColorHierarchy(base, self.HIERARCHY)
        expected = ('red', 'yellow', 'blue', 'green', 'red', 'yellow', 'blue')
        self.assertEqual(graph.granule_labels('Root'), expected)
        self.assertEqual(graph.unique_granules('Root'), tuple(dict.fromkeys(expected)))
        self.assertEqual(graph.granule_occurrence_counts('Root'), Counter(expected))
        degrees = {'red': .15, 'yellow': .05, 'blue': .1, 'green': .05}
        self.assertAlmostEqual(graph.evaluate(degrees, 'bounded_sum')['Root'], .65)
        self.assertAlmostEqual(graph.evaluate(degrees, 'max')['Root'], .15)

    def test_large_shared_dag_no_exponential_materialization(self):
        base = [SimpleNamespace(label=c, prototypes=[SimpleNamespace(label=g) for g in gs])
                for c, gs in self.RGB.items()]
        nodes = {}
        a, b = 'Warm', 'Cold'
        for i in range(35):
            refs = [{'category': a}, {'category': b}]
            a, b = f'A{i}', f'B{i}'
            nodes[a] = refs
            nodes[b] = refs
        graph = ColorHierarchy(base, nodes)
        self.assertEqual(graph.unique_granules(a), ('red', 'yellow', 'blue', 'green'))
        self.assertEqual(graph.granule_occurrence_counts(a)['red'], 2**34)
        with self.assertRaisesRegex(ValueError, 'Too many repeated'):
            graph.granule_labels(a)
        self.assertEqual(graph.evaluate(dict.fromkeys(graph.unique_granules(a), .1), 'max')[a], .1)

    def test_editor_limits_shared_branch_expansion(self):
        from Source.interface.modules.DataManager import hierarchy_rows, MAX_EXTRA_TREE_ROWS
        categories = {c: {"granules": [{"label": g, "lab": xyz} for g, xyz in gs.items()]}
                      for c, gs in self.RGB.items()}
        nodes = {}
        a, b = 'Warm', 'Cold'
        for i in range(20):
            refs = [{'category': a}, {'category': b}]
            a, b = f'A{i}', f'B{i}'
            nodes[a] = refs
            nodes[b] = refs
        state = {}
        rows = list(hierarchy_rows(categories, nodes, (), 'red', (), state))
        self.assertTrue(state['limited'])
        self.assertLessEqual(len(rows), MAX_EXTRA_TREE_ROWS + 2)

    def test_cycle_rejected(self):
        base = [SimpleNamespace(label='Base', prototypes=[SimpleNamespace(label='x')])]
        with self.assertRaisesRegex(ValueError, 'cycle'):
            ColorHierarchy(base, {'A': [{'category': 'B'}], 'B': [{'category': 'A'}]})

    def test_json_roundtrip_hierarchy_and_geometry(self):
        space = FuzzyColorSpaceBuilder.build_granular('Audit', self.RGB,
                    color_space='RGB', hierarchy=self.HIERARCHY)
        with tempfile.TemporaryDirectory() as tmp:
            with patch('Source.input_output.InputJSON.get_base_path', return_value=tmp):
                file = InputJSON().save_space(space)
            before = json.loads(Path(file).read_text(encoding='utf-8'))
            _, loaded = InputJSON().read_file(file)
            after = InputJSON.serialize_space(loaded)
        self.assertEqual(before['metadata']['geometry_sha256'], after['metadata']['geometry_sha256'])
        self.assertEqual(space.hierarchy, loaded.hierarchy)
        for mode in ('max', 'bounded_sum'):
            for point in ([120, 110, 110], [220, 30, 30], [40, 100, 120]):
                old = space.calculate_membership_snapshot(point, 'MODEL', mode)
                new = loaded.calculate_membership_snapshot(point, 'MODEL', mode)
                for key in old:
                    self.assertEqual(old[key].keys(), new[key].keys())
                    for label in old[key]:
                        self.assertAlmostEqual(old[key][label], new[key][label], places=12)
        with self.assertRaisesRegex(ValueError, 'share granules'):
            loaded.make_hierarchy_view(['Root', 'Warm'])

    def test_clipping_exact_in_lab_and_rgb_and_cache_invalidation(self):
        for mode, points in [('RGB', self.RGB), ('LAB', {'Warm': {'red': [50, 60, 40], 'yellow': [80, 5, 65]},
                                                       'Cold': {'blue': [30, 10, -70], 'green': [60, -55, 35]}})]:
            space = FuzzyColorSpaceBuilder.build_granular('Audit', points, color_space=mode)
            for proto in space.get_all_prototypes()+space.get_all_cores()+space.get_all_supports():
                expected = reference_clip(proto.voronoi_volume, space.reference_domain)
                actual = VisualManager._cached_display_polygons(proto, space.reference_domain)
                self.assertEqual(len(expected), len(actual))
                for a,b in zip(expected, actual):
                    np.testing.assert_array_equal(a,b)
                self.assertIs(actual, VisualManager._cached_display_polygons(proto, space.reference_domain))
            proto = space.get_all_prototypes()[0]
            self.assertTrue(VisualManager.has_cached_display_polygons(proto, space.reference_domain))
            face = next(f for f in proto.voronoi_volume.getFaces() if not f.isDomainBoundary())
            face.getPlane().D += .001
            self.assertFalse(VisualManager.has_cached_display_polygons(proto, space.reference_domain))

    def test_model_3d_traces_keep_layer_indices(self):
        space = FuzzyColorSpaceBuilder.build_granular('Audit', self.RGB, color_space='RGB')
        protos = space.get_all_prototypes()
        rows = {p.label: {'positive_prototype': p.positive} for p in protos}
        hexes = {VisualManager._fallback_model_hex(p.positive, 'RGB'): p.positive for p in protos}
        args = ('Audit', rows, space.get_all_cores(), protos, space.get_all_supports(),
                space.reference_domain, hexes, ['Representative', 'Core', '0.5-cut', 'Support'])
        fig = VisualManager.plot_more_combined_3D(*args, color_space='RGB')
        self.assertEqual(len(fig.data), 5*len(protos))
        for menu in fig.layout.updatemenus[:4]:
            button = menu.buttons[0]
            indices = button.args[1]
            self.assertEqual(len(indices), len(protos))
            expected = 'scatter3d' if button.label == 'Representative' else 'mesh3d'
            self.assertTrue(all(fig.data[i].type == expected for i in indices))
        f = Figure(); canvas = FigureCanvasAgg(f); ax = f.add_subplot(111, projection='3d')
        VisualManager.plot_combined_3D(ax, *args, color_space='RGB')
        canvas.draw()
        self.assertIsNotNone(VisualManager.get_orientation_inset(f))

    def test_malformed_json_rejected_as_value_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'invalid.json'
            for invalid in ('{"format_version":1,"format_version":1}',
                            '{"format_version":1,"categories":[],"metadata":null}',
                            '{"format_version":1,"model":{"categories":{}},"geometry":{},"metadata":null}',
                            '{"format_version":1,"categories":[],"x":NaN}'):
                path.write_text(invalid, encoding='utf-8')
                with self.assertRaises(ValueError):
                    InputJSON().read_file(path)
        with self.assertRaises(ValueError):
            InputJSON._triple([True, 1, 2], 'prototype')
        with self.assertRaises(ValueError):
            InputJSON._volume_from_data({'faces':[{'plane':[1e308,1e308,1e308,0],
                  'vertices':None,'infinity':False,'domain_boundary':False}]}, 'bad', [1,2,3], 'core')

if __name__ == '__main__':
    unittest.main()

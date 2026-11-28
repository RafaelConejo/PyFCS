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
from Source.interface.modules.visualization.VisualManager import VisualManager


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
        from Source.interface.modules.data.DataManager import hierarchy_rows, MAX_EXTRA_TREE_ROWS
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

class MappingDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from Source.interface.modules.image.ColorProcessingEngine import ColorProcessingEngine
        cls.manager = ColorProcessingEngine()
        cls.source = FuzzyColorSpaceBuilder.build_granular('Mapping audit', PreJavaAuditTests.RGB,
                        color_space='RGB', hierarchy=PreJavaAuditTests.HIERARCHY)
        cls.rgb = np.array([[[230,30,30], [120,110,110], [25,30,230]],
                            [[40,100,120], [220,210,30], [120,110,110]]], dtype=np.uint8)

    def test_general_detail_aliases_and_flat_geometry(self):
        from Source.interface.modules.image.ColorProcessingEngine import (general_mapping_space,
            single_mapping_space, mapping_category_rows, general_labels)
        flat = self.source.with_hierarchy({})
        aliases = flat.with_hierarchy({'Red alias':[{'granule':'red'}]})
        self.assertIs(general_mapping_space(flat), flat)
        self.assertIs(general_mapping_space(aliases), aliases)
        self.assertEqual(general_labels(aliases), ('Warm','Cold'))
        view = single_mapping_space(aliases)
        general = mapping_category_rows(aliases, view, set(range(3)))
        detailed = mapping_category_rows(aliases, view, set(range(3)), True)
        self.assertEqual([r['name'] for r in general], ['Warm','Cold'])
        self.assertEqual(general[0]['count'],2)
        self.assertEqual(len(general[0]['swatches']),2)
        self.assertFalse(general[0]['expandable'])
        self.assertIn('Red alias', [r['name'] for r in detailed])
        self.assertEqual(sum(r['type']=='granule' for r in detailed),4)
        for op in ('max','bounded_sum'):
            aliases.set_tconorm(op); flat.set_tconorm(op)
            before = self.manager.get_category_granule_label_maps(self.rgb, flat)
            after = self.manager.get_category_granule_label_maps(self.rgb, general_mapping_space(aliases))
            for a,b in zip(before,after): np.testing.assert_array_equal(a,b)
            for ci in range(2):
                a=self.manager.get_proto_percentage(flat.prototypes,self.rgb,flat,ci)
                b=self.manager.get_proto_percentage(view.prototypes,self.rgb,view,ci)
                np.testing.assert_array_equal(a,b)

    def test_nested_categories_and_detailed_granules(self):
        from Source.interface.modules.image.ColorProcessingEngine import (general_mapping_space,
            single_mapping_space, mapping_category_rows)
        source=self.source
        general=general_mapping_space(source)
        single=single_mapping_space(source)
        self.assertEqual(general.labels,('Root',))
        self.assertEqual(single.labels[0],'Root')
        rows=mapping_category_rows(source,single,set(range(len(single.labels))),True)
        self.assertEqual(set(r['name'] for r in rows if r['type']=='category'),set(single.labels))
        self.assertTrue(any(r.get('depth',0)>1 for r in rows))
        for proto in single.get_all_prototypes():
            self.assertIs(proto, next(p for p in source.get_all_prototypes() if p.label==proto.label))
        valid=np.array([[True,True,True],[True,False,True]])
        for op in ('max','bounded_sum'):
            source.set_tconorm(op)
            cat,grain=self.manager.get_category_granule_label_maps(self.rgb,general,valid_mask=valid)
            self.assertEqual(cat[1,1],-1);self.assertEqual(grain[1,1],-1)
            for y,x in np.argwhere(valid):
                snap=source.calculate_membership_snapshot(self.rgb[y,x].tolist(),'RGB')
                winner=source.get_best_category(self.rgb[y,x].tolist(),general.labels,'RGB')
                if winner is None:
                    self.assertEqual(cat[y,x],-1);self.assertEqual(grain[y,x],-1)
                else:
                    self.assertEqual(cat[y,x],0)
                    g=general.get_all_prototypes()[grain[y,x]]
                    self.assertEqual(snap['granules'][g.label],max(snap['granules'][p.label] for p in general.categories[0].prototypes))
            for ci,label in enumerate(single.labels):
                gray=self.manager.get_proto_percentage(single.prototypes,self.rgb,single,ci)
                expected=np.array([source.calculate_category_membership(q.tolist(),label,'RGB') for q in self.rgb.reshape(-1,3)],dtype=np.float32)
                np.testing.assert_array_equal(gray,(expected.reshape(self.rgb.shape[:2])*255).astype(np.uint8))
                gray=self.manager.get_proto_percentage(single.prototypes,self.rgb,single,ci,granule_index=0)
                label=single.categories[ci].prototypes[0].label
                expected=np.array([source.calculate_membership_snapshot(q.tolist(),'RGB')['granules'][label] for q in self.rgb.reshape(-1,3)],dtype=np.float32)
                np.testing.assert_array_equal(gray,(expected.reshape(self.rgb.shape[:2])*255).astype(np.uint8))

    def test_cached_surface_artist_reuse_and_render_equivalence(self):
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
        space=self.source
        rows={p.label:{'positive_prototype':p.positive} for p in space.get_all_prototypes()}
        hexes={VisualManager._fallback_model_hex(p.positive,'RGB'):p.positive for p in space.get_all_prototypes()}
        args=('Audit',rows,space.get_all_cores(),space.get_all_prototypes(),space.get_all_supports(),space.reference_domain,hexes)
        figure=Figure(figsize=(5,4)); canvas=FigureCanvasAgg(figure); ax=figure.add_subplot(111,projection='3d')
        reference=Figure(figsize=(5,4)); ref_canvas=FigureCanvasAgg(reference); ref_ax=reference.add_subplot(111,projection='3d')
        first=None
        for i,layers in enumerate((['Representative','Core'], ['Representative','Support'], ['Representative'], ['Representative','Core'], ['Core','0.5-cut','Support'])):
            VisualManager.plot_combined_3D(ax,*args,layers,color_space='RGB',reuse_surface_collection=True)
            VisualManager.plot_combined_3D(ref_ax,*args,layers,color_space='RGB')
            canvas.draw();ref_canvas.draw()
            np.testing.assert_array_equal(np.asarray(canvas.buffer_rgba()),np.asarray(ref_canvas.buffer_rgba()))
            if i==0: first=ax._pyfcs_surface_artist
            if i==3: self.assertIs(ax._pyfcs_surface_artist,first)
            self.assertLessEqual(len(ax._pyfcs_recent_surfaces),3)
            self.assertEqual(sum(isinstance(x,Poly3DCollection) for x in ax.collections),int(any(x!='Representative' for x in layers)))

class ProcessingOptimizationTests(unittest.TestCase):
    def test_packed_unique_colors_exact(self):
        from PIL import Image
        from Source.interface.modules.image.ColorProcessingEngine import ColorProcessingEngine
        engine = ColorProcessingEngine()
        rng = np.random.default_rng(2026)
        rgb = rng.integers(0, 256, (32, 40, 3), dtype=np.uint8)
        rgb[1] = rgb[0]
        rgba = np.concatenate((rgb, rng.integers(0, 256, (32,40,1), dtype=np.uint8)), axis=-1)
        for image in (rgb, rgba, rgb[:,:,0], Image.fromarray(rgb), Image.fromarray(rgba), Image.fromarray(rgb).convert('P')):
            for mode in ('RGB','LAB'):
                model = engine._pil_to_rgb_uint8(image) if mode == 'RGB' else engine._pil_to_lab_image(image)
                scale = 1.0 if mode == 'RGB' else 100.0
                rows = np.rint(model.reshape(-1,3)*scale).astype(np.int32)
                expected, indices = np.unique(rows, axis=0, return_inverse=True)
                actual, inverse, h,w,q,src = engine._unique_model_colors(image,SimpleNamespace(color_space=mode))
                np.testing.assert_array_equal(actual,expected)
                np.testing.assert_array_equal(inverse,indices)
                self.assertEqual((h,w,q,src),(*model.shape[:2],scale,mode))

    def test_flat_pair_matches_scalar_and_no_duplicate_raw_calls(self):
        from Source.fuzzy.FuzzyColor import FuzzyColor
        from Source.interface.modules.image.ColorProcessingEngine import ColorProcessingEngine
        rng = np.random.default_rng(42)
        engine = ColorProcessingEngine()
        from skimage.color import rgb2lab
        for mode in ('RGB','LAB'):
            points = PreJavaAuditTests.RGB
            if mode == 'LAB':
                points = {k:{g:rgb2lab(np.array(v,dtype=float).reshape(1,1,3)/255)[0,0].tolist() for g,v in group.items()} for k,group in points.items()}
            space = FuzzyColorSpaceBuilder.build_granular('Reuse', points, color_space=mode)
            pack = space.precompute_pack()
            probes = rng.integers(0,256,(100,3)).astype(float)
            if mode == 'LAB':
                probes = rgb2lab(probes.reshape(1,-1,3)/255)[0]
            probes = list(probes)+[p.positive for p in space.get_all_prototypes()]
            for operator in ('max','bounded_sum'):
                space.set_tconorm(operator)
                for q in probes:
                    ci = space.best_prototype_index(q, input_space=mode)
                    expected = (ci,-1)
                    if ci >= 0:
                        ids = space._category_flat_indices[ci]
                        coords = space._coordinates(q,mode)
                        vals = [FuzzyColor._raw_membership_for_index(coords,i,pack) for i in ids]
                        winner = min((j for j,v in enumerate(vals) if abs(v-max(vals))<=1e-12),key=lambda j:(float(np.dot(space.get_all_prototypes()[ids[j]].positive-q,space.get_all_prototypes()[ids[j]].positive-q)),j))
                        expected = (ci,ids[winner])
                    with patch.object(FuzzyColor,'_raw_membership_for_index',wraps=FuzzyColor._raw_membership_for_index) as raw:
                        pair = engine._prepare_flat_winning_pair(space)
                        self.assertEqual(pair(q,mode),expected)
                        calls = [c.args[1] for c in raw.call_args_list]
                        self.assertEqual(len(calls),len(set(calls)))

    def test_semantic_single_map_preserves_dag_multiplicity(self):
        from Source.interface.modules.image.ColorProcessingEngine import single_mapping_space
        from Source.fuzzy.FuzzyColor import FuzzyColor
        source = FuzzyColorSpaceBuilder.build_granular('Subset', PreJavaAuditTests.RGB, color_space='RGB', hierarchy=PreJavaAuditTests.HIERARCHY)
        view = single_mapping_space(source)
        rng = np.random.default_rng(43)
        for op in ('max','bounded_sum'):
            source.set_tconorm(op)
            for ci,label in enumerate(view.labels):
                evaluate = view.prepare_category_evaluator(ci)
                for point in rng.integers(0,256,(80,3)):
                    expected = source.calculate_category_membership(point,label,'RGB')
                    self.assertEqual(evaluate(point,'RGB'),expected)
        label = 'Warm'
        with patch.object(FuzzyColor,'_raw_membership_for_index',wraps=FuzzyColor._raw_membership_for_index) as raw:
            evaluate = view.prepare_category_evaluator(view.labels.index(label))
            evaluate([120,110,110],'RGB')
            self.assertTrue(set(c.args[1] for c in raw.call_args_list) <= {source._granule_index[p.label] for p in source.get_descendant_granules(label)})

    def test_cancelled_mapping(self):
        from Source.interface.modules.image.ColorProcessingEngine import ColorProcessingEngine
        engine = ColorProcessingEngine()
        source = FuzzyColorSpaceBuilder.build_granular('Cancel', PreJavaAuditTests.RGB, color_space='RGB')
        image = np.zeros((2,2,3),dtype=np.uint8)
        self.assertIsNone(engine.get_category_granule_label_maps(image,source,cancel_callback=lambda:True))
        self.assertIsNone(engine.get_proto_percentage(source.prototypes,image,source,0,cancel_callback=lambda:True))



class ImagePreprocessingCacheTests(unittest.TestCase):
    def test_prepared_maps_equal_uncached(self):
        from PIL import Image
        from skimage.color import rgb2lab
        from Source.interface.modules.image.ColorProcessingEngine import (
            ColorProcessingEngine, general_mapping_space, single_mapping_space)
        from Source.interface.modules.common import UtilsTools
        rng = np.random.default_rng(20261127)
        rgba = rng.integers(0,256,(17,23,4),dtype=np.uint8)
        rgba[0,:,3] = 0
        rgba[1,:,3] = 128
        original = Image.fromarray(rgba)
        engine = ColorProcessingEngine()
        engine.preprocessing_cache.register('card', original)
        for mode in ('RGB','LAB'):
            points = PreJavaAuditTests.RGB
            if mode == 'LAB':
                points = {k:{g:rgb2lab(np.array(v,dtype=float).reshape(1,1,3)/255)[0,0].tolist()
                             for g,v in group.items()} for k,group in points.items()}
            space = FuzzyColorSpaceBuilder.build_granular('Prepared', points, color_space=mode,
                       hierarchy=PreJavaAuditTests.HIERARCHY)
            for size in (original.size,(15,11)):
                source = original.copy() if size == original.size else original.resize(size,Image.Resampling.LANCZOS)
                rgb = UtilsTools._pil_rgb_for_processing(source)
                alpha = UtilsTools._get_alpha_values_from_pil(source)
                valid = alpha > 0
                prepared = engine.prepare_image(original,size,space,owner='card')
                np.testing.assert_array_equal(prepared.rgb,np.asarray(rgb))
                np.testing.assert_array_equal(prepared.alpha,alpha)
                np.testing.assert_array_equal(prepared.valid_mask,valid)
                expected = engine._unique_model_colors(rgb,space)
                for a,b in zip(prepared.colors[:2],expected[:2]):
                    np.testing.assert_array_equal(a,b)
                self.assertEqual(prepared.colors[2:],expected[2:])
                for array in (prepared.rgb,prepared.alpha,prepared.valid_mask,*prepared.colors[:2]):
                    self.assertFalse(array.flags.writeable)
                for op in ('max','bounded_sum'):
                    space.set_tconorm(op)
                    view = single_mapping_space(space)
                    self.assertIs(engine.prepare_image(original,size,view,owner='card'),prepared)
                    for ci in (0,len(view.prototypes)-1):
                        for gi in (None,0):
                            before=engine.get_proto_percentage(view.prototypes,rgb,view,ci,granule_index=gi)
                            after=engine.get_proto_percentage(view.prototypes,prepared,view,ci,granule_index=gi)
                            np.testing.assert_array_equal(before,after)
                    view = general_mapping_space(space)
                    before=engine.get_category_granule_label_maps(rgb,view,valid_mask=valid)
                    after=engine.get_category_granule_label_maps(prepared,view,valid_mask=prepared.valid_mask)
                    for a,b in zip(before,after):
                        np.testing.assert_array_equal(a,b)
                    np.testing.assert_array_equal(engine.get_best_prototype_label_map(rgb,view,valid_mask=valid),
                                                  engine.get_best_prototype_label_map(prepared,view,valid_mask=valid))
        self.assertEqual(engine.preprocessing_cache.info()['entries'],4)
        self.assertEqual(engine.preprocessing_cache.info()['misses'],4)
        self.assertEqual(engine.preprocessing_cache.info()['hits'],8)

    def test_reuse_across_categories_operators_and_models(self):
        from PIL import Image
        from Source.interface.modules.image.ColorProcessingEngine import ColorProcessingEngine
        engine = ColorProcessingEngine()
        image = Image.new('RGBA',(23,17),(91,174,227,128))
        engine.preprocessing_cache.register('card',image)
        a = SimpleNamespace(color_space='LAB',tconorm='max')
        b = SimpleNamespace(color_space='LAB',tconorm='bounded_sum')
        with patch.object(engine,'_pil_to_lab_image',wraps=engine._pil_to_lab_image) as convert:
            first = engine.prepare_image(image,(10,12),a,owner='card')
            self.assertIs(engine.prepare_image(image,(10,12),b,owner='card'),first)
            self.assertIs(engine.peek_prepared_image(image,(10,12),b,owner='card'),first)
            self.assertEqual(convert.call_count,1)
            self.assertIsNot(engine.prepare_image(image,(12,10),b,owner='card'),first)
            self.assertEqual(convert.call_count,2)
        rgb = engine.prepare_image(image,(10,12),SimpleNamespace(color_space='RGB'),owner='card')
        self.assertIsNot(rgb,first)
        with self.assertRaises(ValueError):
            engine._unique_model_colors(rgb,a)

    def test_lru_budget_and_oversized_entries(self):
        from PIL import Image
        from Source.interface.modules.image.ColorProcessingEngine import ColorProcessingEngine
        mode=SimpleNamespace(color_space='RGB')
        images=[Image.new('RGBA',(8,8),(i,2,3,255)) for i in range(3)]
        probe=ColorProcessingEngine().prepare_image(images[0],(8,8),mode)
        engine=ColorProcessingEngine(preprocessing_cache_bytes=2*probe.nbytes)
        cache=engine.preprocessing_cache
        for i,image in enumerate(images): cache.register(i,image)
        first=engine.prepare_image(images[0],(8,8),mode,owner=0)
        engine.prepare_image(images[1],(8,8),mode,owner=1)
        self.assertIs(engine.prepare_image(images[0],(8,8),mode,owner=0),first)
        engine.prepare_image(images[2],(8,8),mode,owner=2)
        self.assertIsNone(engine.peek_prepared_image(images[1],(8,8),mode,owner=1))
        self.assertEqual(cache.info()['evictions'],1)
        self.assertLessEqual(cache.info()['bytes'],cache.info()['max_bytes'])
        huge=engine.prepare_image(images[2],(32,32),mode,owner=2)
        self.assertGreater(huge.nbytes,cache.info()['max_bytes'])
        self.assertIsNone(engine.peek_prepared_image(images[2],(32,32),mode,owner=2))
        self.assertEqual(cache.info()['entries'],2)
        cache.discard(0)
        self.assertEqual(cache.info()['entries'],1)
        cache.clear()
        self.assertEqual(cache.info()['bytes'],0)

    def test_source_replacement_cancellation_and_unregistered_input(self):
        from PIL import Image
        from Source.interface.modules.image.ColorProcessingEngine import ColorProcessingEngine
        engine=ColorProcessingEngine()
        mode=SimpleNamespace(color_space='RGB')
        old=Image.new('RGB',(5,5),(1,2,3))
        new=Image.new('RGB',(5,5),(8,9,10))
        cache=engine.preprocessing_cache
        cache.register('card',old)
        a=engine.prepare_image(old,old.size,mode,owner='card')
        cache.register('card',new)
        self.assertIsNone(engine.peek_prepared_image(old,old.size,mode,owner='card'))
        b=engine.prepare_image(new,new.size,mode,owner='card')
        self.assertFalse(np.array_equal(a.rgb,b.rgb))
        cache.discard('card')
        self.assertIsNone(engine.prepare_image(new,new.size,mode,owner='card',cancelled=lambda:True))
        self.assertIsNot(engine.prepare_image(new,new.size,mode,owner='card'),b)
        self.assertEqual(cache.info()['entries'],0)
        cache.register('card',new)
        # Simulate closing a card while its worker prepares its arrays.
        original=engine._unique_model_colors
        def close_during_prepare(*args):
            result=original(*args)
            cache.discard('card')
            return result
        with patch.object(engine,'_unique_model_colors',side_effect=close_during_prepare):
            engine.prepare_image(new,new.size,mode,owner='card')
        self.assertEqual(cache.info()['entries'],0)
        # Cancellation during preparation must not publish the prepared result.
        cache.register('card',new)
        cancelled=iter([False,True])
        self.assertIsNone(engine.prepare_image(new,new.size,mode,owner='card',cancelled=lambda:next(cancelled)))
        self.assertEqual(cache.info()['entries'],0)


class AdaptiveBatchDispatchTests(unittest.TestCase):
    """The adaptive selector must not import or compile Numba on tiny jobs."""

    def test_cold_budget_and_warm_thresholds(self):
        from Source.interface.modules.image.ColorProcessingEngine import ColorProcessingEngine
        module = 'Source.interface.modules.image.ColorProcessingEngine.'
        engine = ColorProcessingEngine(batch_mode='auto')
        large = SimpleNamespace(is_granular=True, get_all_prototypes=lambda: list(range(102)),
                                categories=[SimpleNamespace(prototypes=[1, 2, 3])])
        small = SimpleNamespace(is_granular=True, get_all_prototypes=lambda: list(range(13)),
                                categories=[SimpleNamespace(prototypes=[1])])
        with patch(module + '_BATCH_UNAVAILABLE', False), patch(module + '_BATCH_KERNEL', None):
            self.assertFalse(engine._should_use_batch(large, 1, 'pair'))
            self.assertFalse(engine._should_use_batch(large, 9, 'pair'))
            self.assertEqual(engine._batch_deferred_work, 0)
            self.assertFalse(engine._should_use_batch(large, 512, 'pair'))
            self.assertEqual(engine._batch_deferred_work, 52224)
            self.assertTrue(engine._should_use_batch(large, 512, 'pair'))
            self.assertEqual(engine._batch_deferred_work, 100000)
            self.assertFalse(engine._should_use_batch(large, 13, 'pair'))
            self.assertFalse(engine._should_use_batch(large, 32, 'single', 0, 0))
            # A moderately sized image with thirteen leaves can activate JIT
            # on its first mapping, without waiting for several operations.
            fresh = ColorProcessingEngine(batch_mode='auto')
            self.assertTrue(fresh._should_use_batch(small, 8000, 'pair'))
        with patch(module + '_BATCH_UNAVAILABLE', False), patch(module + '_BATCH_KERNEL', SimpleNamespace(signatures=[])):
            fresh = ColorProcessingEngine(batch_mode='auto')
            self.assertFalse(fresh._should_use_batch(large, 128, 'pair'))
        with patch(module + '_BATCH_UNAVAILABLE', False), patch(module + '_BATCH_KERNEL', SimpleNamespace(signatures=[object()])):
            for model in (small, large):
                for kind, ci, gi in (('pair', None, None), ('best', None, None),
                                    ('single', 0, None), ('single', 0, 0)):
                    with self.subTest(model=len(model.get_all_prototypes()), kind=kind, granule=gi):
                        self.assertFalse(engine._should_use_batch(model, 9, kind, ci, gi))
                        self.assertTrue(engine._should_use_batch(model, 10, kind, ci, gi))
                        self.assertTrue(engine._should_use_batch(model, 13, kind, ci, gi))
            self.assertEqual(engine._batch_deferred_work, 0)
            self.assertFalse(ColorProcessingEngine(batch_mode='scalar')._should_use_batch(large, 4096, 'pair'))
            self.assertTrue(ColorProcessingEngine(batch_mode='batch')._should_use_batch(large, 1, 'pair'))
        with patch(module + '_BATCH_UNAVAILABLE', True):
            self.assertFalse(engine._should_use_batch(large, 100000, 'pair'))

    def test_relevant_semantic_leaves(self):
        from Source.interface.modules.image.ColorProcessingEngine import ColorProcessingEngine, single_mapping_space
        source = FuzzyColorSpaceBuilder.build_granular('DAG dispatch', PreJavaAuditTests.RGB,
                    color_space='RGB', hierarchy=PreJavaAuditTests.HIERARCHY)
        view = single_mapping_space(source)
        count = ColorProcessingEngine._batch_relevant_granules
        self.assertEqual(count(view, 'pair', None, None), len(source.get_all_prototypes()))
        for i, cat in enumerate(view.categories):
            self.assertEqual(count(view, 'single', i, None), len(cat.prototypes))
            self.assertEqual(count(view, 'single', i, 0), 1)


class BatchMappingTests(unittest.TestCase):
    """The optional compiled path must reproduce the scientific core and maps."""

    @classmethod
    def setUpClass(cls):
        from Source.interface.modules.image.ColorProcessingEngine import ColorProcessingEngine, _get_batch_kernel
        if _get_batch_kernel() is None:
            raise unittest.SkipTest('Optional Numba backend unavailable')
        cls.scalar = ColorProcessingEngine(batch_mode='scalar')
        cls.fast = ColorProcessingEngine(batch_mode='batch')
        rng = np.random.default_rng(20261127)
        cls.image = rng.integers(0,256,(33,35,3),dtype=np.uint8)
        cls.image[0,:8] = np.array([[r,g,b] for r in (0,255) for g in (0,255) for b in (0,255)])
        cls.valid = np.ones(cls.image.shape[:2],dtype=bool)
        cls.valid[1,::3] = False

    def check_maps(self, space, single=None):
        before = self.fast.batch_statistics['colors']
        for a,b in zip(self.scalar.get_category_granule_label_maps(self.image,space,self.valid),
                       self.fast.get_category_granule_label_maps(self.image,space,self.valid)):
            np.testing.assert_array_equal(a,b)
        np.testing.assert_array_equal(self.scalar.get_best_prototype_label_map(self.image,space,self.valid),
                                      self.fast.get_best_prototype_label_map(self.image,space,self.valid))
        targets = single if single is not None else [(0,None),(len(space.prototypes)-1,None)]
        for ci,gi in targets:
            a = self.scalar.get_proto_percentage(space.prototypes,self.image,space,ci,granule_index=gi)
            b = self.fast.get_proto_percentage(space.prototypes,self.image,space,ci,granule_index=gi)
            np.testing.assert_array_equal(a,b)
        self.assertGreater(self.fast.batch_statistics['colors'],before)
        self.assertEqual(self.fast.batch_statistics['fallbacks'],0)

    def test_warm_auto_small_image_matches_scalar(self):
        from Source.interface.modules.image.ColorProcessingEngine import ColorProcessingEngine
        from skimage.color import rgb2lab
        rgb = {'Red':[230,30,30], 'Blue':[25,30,230], 'Green':[30,210,40]}
        palette = np.random.default_rng(42).integers(0,256,(13,3),dtype=np.uint8)
        for mode in ('RGB', 'LAB'):
            pts = rgb if mode == 'RGB' else {k:rgb2lab(np.array(v,dtype=float).reshape(1,1,3)/255)[0,0].tolist() for k,v in rgb.items()}
            space = FuzzyColorSpaceBuilder.build('Small dispatch', pts, color_space=mode)
            # Warm the shared compiled dispatcher independently of the auto engine.
            self.fast.get_category_granule_label_maps(palette.reshape(1,13,3), space)
            for n in (1, 9, 10, 13):
                with self.subTest(mode=mode, colors=n):
                    # A repeated palette, not a 10-pixel image: dispatch depends
                    # on the quantized unique colors, not the image dimensions.
                    image = np.tile(palette[:n].reshape(1,n,3), (16,8,1))
                    auto = ColorProcessingEngine(batch_mode='auto')
                    for a,b in zip(self.scalar.get_category_granule_label_maps(image,space),
                                   auto.get_category_granule_label_maps(image,space)):
                        np.testing.assert_array_equal(a,b)
                    expected = n if n >= 10 else 0
                    self.assertEqual(auto.batch_statistics['colors'],expected)
                    np.testing.assert_array_equal(self.scalar.get_best_prototype_label_map(image,space),
                                                  auto.get_best_prototype_label_map(image,space))
                    self.assertEqual(auto.batch_statistics['colors'],2*expected)
                    np.testing.assert_array_equal(self.scalar.get_proto_percentage(space.prototypes,image,space,0),
                                                  auto.get_proto_percentage(space.prototypes,image,space,0))
                    self.assertEqual(auto.batch_statistics['colors'],3*expected)
                    self.assertEqual(auto.batch_statistics['fallbacks'],0)

    def test_atomic_all_typologies_and_color_spaces(self):
        from skimage.color import rgb2lab
        rgb = {'Red':[230,30,30],'Yellow':[220,210,30],
               'Blue':[25,30,230],'Green':[30,210,40]}
        for mode in ('RGB','LAB'):
            pts = rgb if mode=='RGB' else {k:rgb2lab(np.array(v,dtype=float).reshape(1,1,3)/255)[0,0].tolist() for k,v in rgb.items()}
            for disjoint in (True,False):
                for covering in (True,False):
                    with self.subTest(mode=mode,disjoint=disjoint,covering=covering):
                        neg = None if disjoint else {'Red':[pts['Blue']], 'Blue':[pts['Red']]}
                        space = FuzzyColorSpaceBuilder.build('Atomic batch',pts,color_space=mode,
                            disjoint=disjoint,covering=covering,samples=27,negative_prototypes=neg)
                        self.check_maps(space)

    def test_granular_dag_aliases_and_raw_degrees(self):
        from skimage.color import rgb2lab
        from Source.interface.modules.image.ColorProcessingEngine import (_BatchMappingEvaluator,
            _get_batch_kernel, general_mapping_space,single_mapping_space,SemanticMappingView)
        from Source.fuzzy.FuzzyColor import FuzzyColor
        for mode in ('RGB','LAB'):
            pts = PreJavaAuditTests.RGB
            if mode=='LAB':
                pts = {k:{g:rgb2lab(np.array(v,dtype=float).reshape(1,1,3)/255)[0,0].tolist() for g,v in group.items()} for k,group in pts.items()}
            source = FuzzyColorSpaceBuilder.build_granular('DAG batch',pts,color_space=mode,
                        hierarchy=PreJavaAuditTests.HIERARCHY)
            flat=source.with_hierarchy({})
            aliases=source.with_hierarchy({'Red alias':[{'granule':'red'}]})
            for op in ('max','bounded_sum'):
                for space in (flat,source,aliases): space.set_tconorm(op)
                self.check_maps(flat,[(0,None),(1,1)])
                self.check_maps(general_mapping_space(source),[(0,None),(0,2)])
                self.check_maps(single_mapping_space(aliases),[(0,None),(2,None),(2,0)])
                # A nested category plus its own children exercises repeated DAG paths.
                view=SemanticMappingView(source,['Root','A','B'],'test')
                self.check_maps(view,[(0,None),(1,0),(2,None)])
                plan=_BatchMappingEvaluator(view,'pair')
                uniq,_,_,_,scale,_=self.fast._unique_model_colors(self.image,view)
                points=(uniq.astype(np.float32)/scale).astype(np.float64)
                vals,_=plan.raw(points,_get_batch_kernel())
                raw=np.array([[FuzzyColor._raw_membership_for_index(tuple(q.tolist()),i,plan.original_pack)
                               if source.reference_domain.contains_coordinates(q,eps=1e-9) else 0.
                               for i in plan.indices] for q in points])
                np.testing.assert_allclose(vals,raw,atol=1e-12,rtol=0)
                ref=np.array([[source.calculate_membership_snapshot(q,mode)['categories'][label]
                               for label in view.labels] for q in points])
                np.testing.assert_allclose(plan.scores(vals),ref,atol=1e-12,rtol=0)

    def test_boundary_prototypes_and_cancel_after_block(self):
        from Source.interface.modules.image.ColorProcessingEngine import ColorProcessingEngine
        space=FuzzyColorSpaceBuilder.build('Boundary batch',{'Black':[0,0,0],'White':[255,255,255],
            'Red':[255,0,0],'Blue':[0,0,255]},color_space='RGB')
        self.check_maps(space)
        engine=ColorProcessingEngine(batch_mode='batch')
        cancel=[False]
        progress=[]
        def stop(done,total):
            progress.append(done); cancel[0]=True
        big=np.random.default_rng(7).integers(0,256,(100,100,3),dtype=np.uint8)
        self.assertIsNone(engine.get_category_granule_label_maps(big,space,
                            progress_callback=stop,cancel_callback=lambda:cancel[0]))
        self.assertEqual(len(progress),1)
        self.assertFalse(engine._batch_failed)
        self.assertEqual(engine.batch_statistics['fallbacks'],0)

    def test_fallback_without_numba_or_runtime_error(self):
        from Source.interface.modules.image.ColorProcessingEngine import ColorProcessingEngine
        space=FuzzyColorSpaceBuilder.build('Fallback batch',{'Red':[230,30,30],'Blue':[25,30,230]},color_space='RGB')
        expected=self.scalar.get_category_granule_label_maps(self.image,space)
        path='Source.interface.modules.image.ColorProcessingEngine._get_batch_kernel'
        for kernel in (None, lambda *args: (_ for _ in ()).throw(RuntimeError('simulated JIT error'))):
            engine=ColorProcessingEngine(batch_mode='batch')
            with patch(path,return_value=kernel):
                actual=engine.get_category_granule_label_maps(self.image,space)
            for a,b in zip(expected,actual): np.testing.assert_array_equal(a,b)
            self.assertEqual(engine.batch_statistics['fallbacks'],int(kernel is not None))


class InterfacePackageTests(unittest.TestCase):
    """Keep package relocation and application resource paths covered."""

    def test_public_exports_preserve_class_identity(self):
        import Source
        from Source.interface.modules.image.ColorProcessingEngine import ColorProcessingEngine
        from Source.interface.modules.evaluation.ColorEvaluationManager import ColorEvaluationManager
        from Source.interface.modules.creation.FuzzyColorSpaceManager import FuzzyColorSpaceManager
        self.assertIs(Source.ColorProcessingEngine, ColorProcessingEngine)
        self.assertIs(Source.ColorEvaluationManager, ColorEvaluationManager)
        self.assertIs(Source.FuzzyColorSpaceManager, FuzzyColorSpaceManager)
        self.assertIs(Source.VisualManager, VisualManager)

    def test_source_resource_paths(self):
        import sys
        from Source.interface.modules.common import UtilsTools
        project = Path(__file__).resolve().parents[2]
        relative = Path("Source/external/icons/logo.png")
        with patch.object(sys, "frozen", False, create=True):
            self.assertEqual(Path(UtilsTools.get_base_path()), project)
            self.assertEqual(Path(UtilsTools.get_resource_path(relative)), project / relative)
            self.assertTrue((project / relative).is_file())
            self.assertEqual(Path(UtilsTools.get_runtime_temp_dir("package_test", create=False)),
                             project / "Source/external/temp/package_test")

    def test_frozen_resource_paths(self):
        import sys
        from Source.interface.modules.common import UtilsTools
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "app"
            bundle = Path(tmp) / "bundle"
            relative = Path("Source/external/icons/logo.png")
            bundled_resource = bundle / relative
            bundled_resource.parent.mkdir(parents=True)
            bundled_resource.write_bytes(b"bundle")
            app.mkdir()
            with patch.object(sys, "frozen", True, create=True), \
                    patch.object(sys, "executable", str(app / "PyFCS.exe")), \
                    patch.object(sys, "_MEIPASS", str(bundle), create=True):
                self.assertEqual(Path(UtilsTools.get_base_path()), app)
                self.assertEqual(Path(UtilsTools.get_resource_path(relative)), bundled_resource)
                external = app / relative
                external.parent.mkdir(parents=True)
                external.write_bytes(b"override")
                self.assertEqual(Path(UtilsTools.get_resource_path(relative)), external)
                self.assertEqual(Path(UtilsTools.get_runtime_temp_dir("package_test", create=False)),
                                 Path(tempfile.gettempdir()) / "PyFCS/package_test")


class ImageDisplayControllerTests(unittest.TestCase):
    """The app and controller must never diverge into two image states."""

    def test_workspace_compatibility_properties_share_state(self):
        from Source.interface.mainInterface import PyFCSApp
        from Source.interface.modules.image.ImageDisplayManager import ImageDisplayManager
        app = PyFCSApp.__new__(PyFCSApp)
        app.root = object()
        app.image_display = ImageDisplayManager(app)
        manager = app.image_display
        self.assertIs(app.images, manager.images)
        self.assertIs(app.image_view_state, manager.image_view_state)
        self.assertIs(app.pil_images_original, manager.pil_images_original)
        self.assertEqual(app.pil_images_original, {})
        value = {'first': object()}
        app.pil_images_original = value
        self.assertIs(manager.pil_images_original, value)
        manager.pil_images_original = {'second': object()}
        self.assertIs(app.pil_images_original, manager.pil_images_original)
        del app.pil_images_original
        self.assertFalse(hasattr(manager, 'pil_images_original'))
        self.assertFalse(hasattr(app, 'pil_images_original'))
        self.assertNotIn('image_view_state', vars(app))
        manager._image_workspace_layout_mode = 'manual'
        self.assertEqual(app._image_workspace_layout_mode, 'manual')
        app._image_workspace_layout_mode = 'grid'
        self.assertEqual(manager._image_workspace_layout_mode, 'grid')
        other = ImageDisplayManager(app)
        self.assertIsNot(other.image_view_state, manager.image_view_state)

    def test_legacy_entry_points_delegate_to_controller(self):
        from Source.interface.mainInterface import PyFCSApp
        from Source.interface.modules.image.ImageDisplayManager import ImageDisplayManager
        app = PyFCSApp.__new__(PyFCSApp)
        app.root = object()
        app.image_display = ImageDisplayManager(app)
        with patch.object(app.image_display, 'create_floating_window', return_value='result') as create:
            self.assertEqual(app.create_floating_window(14, 14, 'image.png'), 'result')
            create.assert_called_once_with(14, 14, 'image.png')
        with patch.object(app.image_display, 'save_image') as save:
            app.save_image(window_id='card')
            save.assert_called_once_with('card')
        with patch.object(app.image_display, '_schedule_image_workspace_reflow') as reflow:
            app._schedule_image_workspace_reflow(delay=0)
            reflow.assert_called_once_with(0)


class ColorMappingControllerTests(unittest.TestCase):
    """Explicit compatibility API and single ownership of mapping state."""

    def make_app(self):
        from Source.interface.mainInterface import PyFCSApp
        from Source.interface.modules.image.ColorMappingManager import ColorMappingManager
        app = PyFCSApp.__new__(PyFCSApp)
        app.root = object()
        app.color_mapping_manager = ColorMappingManager(app)
        return app

    def test_mapping_state_ownership_and_properties(self):
        app = self.make_app()
        other = self.make_app()
        manager = app.color_mapping_manager
        self.assertIs(app.image_jobs, manager.image_jobs)
        self.assertIsNot(app.image_jobs, other.image_jobs)
        self.assertIs(app.SHOW_ORIGINAL, manager.SHOW_ORIGINAL)
        self.assertIs(app.CAN_APPLY_MAPPING, manager.CAN_APPLY_MAPPING)
        self.assertIs(app.proto_options, manager.proto_options)
        self.assertEqual(app.proto_options, {})
        value = {'first': object()}
        app.proto_options = value
        self.assertIs(manager.proto_options, value)
        manager.proto_options = {'second': object()}
        self.assertIs(app.proto_options, manager.proto_options)
        self.assertNotIn('proto_options', vars(app))
        del app.proto_options
        self.assertFalse(hasattr(manager, 'proto_options'))
        self.assertFalse(hasattr(app, 'proto_options'))
        app.cm_cache_by_image = {'image': {}}
        self.assertIs(app.cm_cache_by_image, manager.cm_cache_by_image)
        self.assertEqual(other.cm_cache_by_image, {})
        self.assertIsNot(app.cm_cache_by_image, other.cm_cache_by_image)

    def test_all_delegated_registries_initialized_before_first_card(self):
        from Source.interface.modules.image.ImageDisplayManager import ImageDisplayManager
        from Source.interface.modules.evaluation.ColorEvaluationWindow import ColorEvaluationWindow
        app, other = self.make_app(), self.make_app()
        for instance in (app, other):
            instance.image_display = ImageDisplayManager(instance)
            instance.color_evaluation_window = ColorEvaluationWindow(instance)
        # Widgets are intentionally constructed later, in build_workspace.
        widget_names = {'image_canvas', 'image_workspace_focus_button',
                        'image_workspace_grid_button', 'image_workspace_status_var',
                        'image_workspace_vscroll'}
        checked = 0
        for name, descriptor in vars(type(app)).items():
            if not isinstance(descriptor, property) or name in widget_names:
                continue
            owner = descriptor.fget.__qualname__.split('.')[0]
            if owner not in ('_mapping_attribute', '_image_display_attribute'):
                continue
            manager = (app.color_mapping_manager if owner == '_mapping_attribute'
                       else app.image_display)
            # Direct access, not hasattr: any missing field must fail the test.
            value = getattr(app, name)
            self.assertIs(value, getattr(manager, name), name)
            self.assertNotIn(name, vars(app))
            if isinstance(value, dict):
                self.assertEqual(value, {}, name)
                self.assertIsNot(value, getattr(other, name), name)
            checked += 1
        self.assertGreaterEqual(checked, 40)
        self.assertEqual(app.window_image_key, {})
        self.assertIsNone(app._color_evaluation_window)
        self.assertIsNone(app._color_evaluation_vars)
        self.assertIsNone(app._color_evaluation_paned)

    def test_mapping_legacy_entry_points(self):
        app = self.make_app()
        manager = app.color_mapping_manager
        with patch.object(manager, 'color_mapping', return_value='result') as call:
            self.assertEqual(app.color_mapping('card'), 'result')
            call.assert_called_once_with('card')
        with patch.object(manager, '_cancel_window_job') as call:
            app._cancel_window_job('card', cleanup_ui=False)
            call.assert_called_once_with('card', False)
        with patch.object(manager, '_mapping_category_rows') as call:
            app._mapping_category_rows('space', set(), include_granules=False)
            call.assert_called_once_with('space', set(), include_granules=False)
        self.assertEqual(app._legend_display_name('abcdef', 4), 'abc…')

    def test_cancelled_and_stale_jobs_remain_guarded(self):
        import threading
        app = self.make_app()
        manager = app.color_mapping_manager
        event = threading.Event()
        worker = SimpleNamespace(is_alive=lambda: True)
        app.image_jobs['card'] = {'job_id': 9, 'cancel_event': event, 'thread': worker}
        self.assertFalse(manager._is_job_cancelled('card', event, 9))
        self.assertTrue(manager._is_job_cancelled('card', event, 8))
        app._cancel_window_job('card', cleanup_ui=False)
        self.assertTrue(event.is_set())
        self.assertTrue(app._has_active_job('card'))
        self.assertTrue(app._is_job_cancelled('card', event, 9))
        self.assertTrue(app.CAN_APPLY_MAPPING['card'])
        self.assertFalse(app.SHOW_ORIGINAL['card'])
        app.image_jobs.clear()
        self.assertTrue(manager._is_job_cancelled('card', threading.Event(), 9))


class ReleaseHardeningTests(unittest.TestCase):
    """Regressions for destructive failures, bounded storage and workspace parity."""

    def test_atomic_image_export_failure_preserves_previous_file(self):
        from PIL import Image
        from Source.interface.modules.common import UtilsTools
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'imagen á.png'
            original = Image.new('RGBA', (9, 7), (10, 20, 30, 40))
            original.save(path)
            before = path.read_bytes()
            replacement = Image.new('RGBA', (9, 7), (100, 120, 130, 140))
            def fail(staged):
                Path(staged).write_bytes(b'partial')
                raise OSError('simulated disk full')
            with patch.object(replacement, 'save', side_effect=fail):
                with self.assertRaises(OSError):
                    UtilsTools.save_pil_image_atomic(replacement, path)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(tmp).iterdir()), [path])
            UtilsTools.save_pil_image_atomic(replacement, path)
            with Image.open(path) as loaded:
                np.testing.assert_array_equal(np.asarray(loaded), np.asarray(replacement))

    def test_model_and_runtime_paths_read_only_and_mac_bundle(self):
        import sys
        from Source.interface.modules.common import UtilsTools as u
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / 'install'; base.mkdir()
            user = Path(tmp) / 'user data'
            with patch.object(u, 'get_user_data_dir', return_value=str(user)), \
                    patch.object(u, 'get_base_path', return_value=str(base)), \
                    patch.object(u, '_writable_directory_target', return_value=False), \
                    patch.object(sys, 'frozen', False, create=True):
                self.assertEqual(Path(u.get_color_space_dir()), user / 'fuzzy_color_spaces')
                self.assertEqual(Path(u.get_runtime_temp_dir('plots')), user / 'temp/plots')
                with patch('Source.input_output.InputJSON.get_base_path', return_value=str(base)):
                    dest = InputJSON._write_document_atomic('model', {'format_version':1})
                self.assertEqual(Path(dest), user / 'fuzzy_color_spaces/model.json')
                self.assertEqual(Path(u.get_color_space_initial_dir()), user / 'fuzzy_color_spaces')
            mac = Path(tmp) / 'PyFCS.app/Contents/MacOS'; mac.mkdir(parents=True)
            with patch.object(sys, 'platform', 'darwin'), patch.object(sys, 'frozen', True, create=True), \
                    patch.object(u, 'get_user_data_dir', return_value=str(user)):
                self.assertEqual(Path(u.get_color_space_dir(mac)), user / 'fuzzy_color_spaces')

    def test_result_cache_memory_and_entry_limits(self):
        from Source.interface.modules.image.ColorMappingManager import ColorMappingManager
        manager = ColorMappingManager(SimpleNamespace(root=None))
        manager._result_cache_max_bytes = 24
        manager._result_cache_max_entries = 2
        cache = manager.cm_cache_by_image
        a = (np.ones(2, np.int32), np.zeros(2, np.int32))
        b = np.ones(8, np.uint8)
        manager._store_cached_result(cache, 'A', 'one', a)
        manager._store_cached_result(cache, 'B', 'one', b)
        self.assertIs(manager._lookup_cached_result(cache, 'A', 'one'), a)
        manager._store_cached_result(cache, 'C', 'one', b)
        self.assertNotIn('B', cache)
        self.assertIn('A', cache)
        self.assertIn('C', cache)
        manager._store_cached_result(cache, 'D', 'huge', np.zeros(25, np.uint8))
        self.assertNotIn('D', cache)
        manager._store_cached_result(cache, 'C', 'two', np.zeros(1, np.uint8))
        self.assertLessEqual(sum(map(len,cache.values())), 2)
        self.assertLessEqual(manager._cached_result_bytes(cache), 24)
        np.testing.assert_array_equal(a[0], np.ones(2,np.int32))

    def test_cancelled_and_failed_tiles_close_memmaps(self):
        from PIL import Image
        from Source.interface.modules.image import ImageWorkspaceManager as w
        space = FuzzyColorSpaceBuilder.build('test', {'R':[230,30,30],'B':[25,30,230]},color_space='RGB')
        source = Image.new('RGBA',(11,9),(230,30,30,255))
        manager = SimpleNamespace(get_category_granule_label_maps=lambda *a, **k: (np.zeros((9,11),np.int32),np.zeros((9,11),np.int32)))
        for mode in ('cancel','allocation_error','mapping_error'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                maps=[]; cancelled=[False]
                def allocate(shape,dtype,directory,name):
                    if mode=='allocation_error' and maps:
                        raise OSError('disk full')
                    arr=np.memmap(Path(directory)/name,dtype=dtype,mode='w+',shape=shape)
                    maps.append(arr);return arr
                def progress(_): cancelled[0]=True
                with patch.object(w,'_allocate_map',side_effect=allocate):
                    if mode=='cancel':
                        self.assertIsNone(w.compute_full_resolution_mapping(source,manager,space,directory=tmp,progress=progress,cancelled=lambda:cancelled[0]))
                    elif mode=='allocation_error':
                        with self.assertRaises(OSError): w.compute_full_resolution_mapping(source,manager,space,directory=tmp)
                    else:
                        with patch.object(manager,'get_category_granule_label_maps',side_effect=ValueError('bad mapping')):
                            with self.assertRaises(ValueError): w.compute_full_resolution_mapping(source,manager,space,directory=tmp)
                self.assertTrue(maps)
                self.assertTrue(all(a._mmap.closed for a in maps))
                for f in Path(tmp).iterdir(): f.unlink()

    def test_tiled_general_and_detailed_maps_match_desktop(self):
        from PIL import Image
        from skimage.color import rgb2lab
        from Source.interface.modules.image import ImageWorkspaceManager as w
        from Source.interface.modules.image.ColorProcessingEngine import ColorProcessingEngine, general_mapping_space, single_mapping_space
        engine=ColorProcessingEngine(batch_mode='scalar')
        rgba=np.random.default_rng(42).integers(0,256,(17,19,4),dtype=np.uint8)
        rgba[::3,:,3]=0
        image=Image.fromarray(rgba)
        for mode in ('RGB','LAB'):
            pts=PreJavaAuditTests.RGB
            if mode=='LAB': pts={k:{g:rgb2lab(np.array(v,dtype=float).reshape(1,1,3)/255)[0,0].tolist() for g,v in group.items()} for k,group in pts.items()}
            source=FuzzyColorSpaceBuilder.build_granular('DAG',pts,color_space=mode,hierarchy=PreJavaAuditTests.HIERARCHY)
            general=general_mapping_space(source); detailed=single_mapping_space(source)
            self.assertEqual([p.label for p in general.prototypes],['Root'])
            for operator in ('max','bounded_sum'):
                source.set_tconorm(operator)
                with tempfile.TemporaryDirectory() as tmp, patch.object(w,'_tile_rows',return_value=3):
                    expected=engine.get_category_granule_label_maps(image,general,rgba[...,3]>0)
                    result=w.compute_full_resolution_mapping(image,engine,general,directory=tmp)
                    np.testing.assert_array_equal(result['categories'],expected[0]);np.testing.assert_array_equal(result['granules'],expected[1])
                    result['palettes']=w.build_mapping_palettes(engine,general)
                    for level,labels in zip(('categories','granules'),expected):
                        actual=np.asarray(w.render_result_tile(image,result,(0,0,*image.size),level=level))
                        desktop=engine.recolor_label_map(labels,result['palettes'][level]['original'],rgba[...,3])
                        # RGB values of fully transparent pixels are invisible; compare visible pixels and alpha.
                        np.testing.assert_array_equal(actual[...,3],desktop[...,3])
                        np.testing.assert_array_equal(actual[actual[...,3]>0],desktop[desktop[...,3]>0])
                    ci=list(detailed.labels).index('B')
                    roi=(2,3,14,15); crop=image.crop(roi)
                    expected_single=engine.get_proto_percentage(detailed.prototypes,crop,detailed,ci)
                    expected_single[np.asarray(crop)[...,3]==0]=0
                    actual=w.compute_full_resolution_mapping(image,engine,detailed,kind='single',selected=(ci,None),scope=roi,directory=tmp)
                    np.testing.assert_array_equal(actual['membership'],expected_single)
                    self.assertEqual(actual['scope'],roi)

    def test_export_directory_cancellation_and_rollback(self):
        from Source.interface.modules.image import ImageWorkspaceManager as w
        import os
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/'target';target.mkdir();(target/'old.txt').write_text('previous')
            staged=root/'staged';staged.mkdir();(staged/'new.txt').write_text('new')
            self.assertFalse(w._publish_export_directory(staged,target,cancelled=lambda:True))
            self.assertTrue((target/'old.txt').exists())
            original_replace=os.replace
            def fail(src,dst):
                if Path(src)==staged: raise OSError('simulated publish failure')
                return original_replace(src,dst)
            with patch.object(w.os,'replace',side_effect=fail):
                with self.assertRaises(OSError):w._publish_export_directory(staged,target)
            self.assertEqual((target/'old.txt').read_text(),'previous')
            self.assertTrue(w._publish_export_directory(staged,target))
            self.assertEqual((target/'new.txt').read_text(),'new')
            self.assertFalse((target/'old.txt').exists())

    def test_selected_roi_cannot_export_previous_roi(self):
        from PIL import Image
        from Source.interface.modules.image.ImageWorkspaceManager import ImageWorkspaceManager
        space=SimpleNamespace(tconorm='max')
        obj=ImageWorkspaceManager.__new__(ImageWorkspaceManager)
        obj._space=lambda:space;obj._model_reference=space;obj._operator='max'
        obj.original=Image.new('RGBA',(10,10));obj.mapping_var=SimpleNamespace(get=lambda:'All')
        obj.result={'kind':'all','scope':(1,1,4,4)};obj.scope_var=SimpleNamespace(get=lambda:'Selected ROI')
        obj.roi=(2,2,5,5);self.assertIsNone(obj._result_for_current_mode())
        obj.roi=(1,1,4,4);self.assertIs(obj._result_for_current_mode(),obj.result)
        obj.scope_var=SimpleNamespace(get=lambda:'Full image');self.assertIsNone(obj._result_for_current_mode())

if __name__ == '__main__':
    unittest.main()

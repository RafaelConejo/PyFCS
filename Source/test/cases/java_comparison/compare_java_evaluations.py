"""Compare external Java RGB memberships with independently rebuilt PyFCS geometry.
Run from project root: python -m Source.test.cases.java_comparison.compare_java_evaluations --limit 10000
Full run: omit --limit. Numba is optional for smoke tests, required for fast mode.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import os
import sys

# Get the path to the directory containing PyFCS
current_dir = os.path.dirname(__file__)
pyfcs_dir = os.path.abspath(os.path.join(current_dir, '..', '..', '..', '..'))

# Add the PyFCS path to sys.path
sys.path.append(pyfcs_dir)

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from Source.input_output.InputJSON import InputJSON
from Source.fuzzy.GranularFuzzyColorSpace import GranularFuzzyColorSpace

DEFAULT = ROOT / 'fuzzy_color_spaces' / 'test'
MODES = ('max', 'bounded_sum')


class JSONStream:
    """Incremental parser for a top-level object with one large samples array.
    Uses the standard JSON decoder; memory is bounded by the chunk and one item.
    Metadata must precede samples (as in the supplied export).
    """
    def __init__(self, handle):
        self.handle, self.buf, self.pos, self.eof = handle, '', 0, False
        self.decoder = json.JSONDecoder(object_pairs_hook=InputJSON._distinct_object_pairs,
                                        parse_constant=self.reject_constant)

    @staticmethod
    def reject_constant(value):
        raise ValueError(f'Invalid JSON constant: {value}')

    def refill(self):
        self.buf = self.buf[self.pos:]
        self.pos = 0
        more = self.handle.read(1 << 20)
        self.buf += more
        self.eof = not more
        if len(self.buf) > (8 << 20):
            raise ValueError('JSON item exceeds 8 MiB or is malformed')

    def peek(self):
        while True:
            while self.pos < len(self.buf) and self.buf[self.pos] in ' \t\r\n':
                self.pos += 1
            if self.pos < len(self.buf):
                return self.buf[self.pos]
            if self.eof:
                return ''
            self.refill()

    def expect(self, char):
        if self.peek() != char:
            raise ValueError(f'Expected {char!r}, found {self.peek()!r}')
        self.pos += 1

    def value(self):
        if not self.peek():
            raise ValueError('Unexpected end of JSON')
        while True:
            try:
                v, end = self.decoder.raw_decode(self.buf, self.pos)
            except json.JSONDecodeError:
                if self.eof:
                    raise
                self.refill()
                continue
            # A number can be split inside a chunk, so require a delimiter.
            if end == len(self.buf) and not self.eof:
                self.refill()
                continue
            if end < len(self.buf) and self.buf[end] not in ',]} \t\r\n:':
                if not self.eof:
                    self.refill()
                    continue
                raise ValueError('Invalid JSON value delimiter')
            self.pos = end
            return v

    def header(self):
        self.expect('{')
        meta = {}
        while True:
            key = self.value()
            if not isinstance(key, str) or key in meta:
                raise ValueError('Invalid or duplicate top-level key')
            self.expect(':')
            if key == 'samples':
                self.expect('[')
                return meta
            meta[key] = self.value()
            self.expect(',')

    def samples(self):
        if self.peek() != ']':
            while True:
                yield self.value()
                if self.peek() == ']':
                    break
                self.expect(',')
        self.expect(']')
        self.expect('}')
        if self.peek():
            raise ValueError('Unexpected content after JSON object')


def pack_geometry(space, labels):
    """Pack actual PyFCS planes, not a reconstruction from Java or its samples."""
    groups = list(space.categories)
    if space.hierarchy or set(labels) != set(c.label for c in groups):
        raise ValueError('This benchmark requires matching, flat granular categories')
    p = space.precompute_pack()
    reps = np.array([v.get_double_point() for v in p['rep']], dtype=np.float64)
    planes, offsets, sides, ray = [], [0], [], []
    for i, rep in enumerate(p['rep']):
        for key in ('v_cores', 'v_protos', 'v_supps'):
            volume = p[key][i]
            for f in volume.getFaces():
                plane = f.getPlane()
                coeff = plane.getPlane()
                side = plane.evaluatePoint(rep)
                if abs(side) <= 1e-9:
                    side = 0.
                    for other in volume.getFaces():
                        for vertex in other.getArrayVertex() or []:
                            s = plane.evaluatePoint(vertex)
                            if abs(s) > 1e-9:
                                side = 1. if s > 0 else -1.
                                break
                        if side:
                            break
                planes.append(coeff)
                sides.append(side)
                ray.append(not f.isDomainBoundary())
            offsets.append(len(planes))
    cat_ids = np.array([labels.index(c.label) for c in groups for _ in c.prototypes], dtype=np.int64)
    return (reps, np.asarray(planes), np.array(offsets, dtype=np.int64),
            np.asarray(sides), np.array(ray, dtype=np.bool_), cat_ids, len(labels))


def make_fast_evaluator(space, labels):
    try:
        from numba import njit, prange
    except ImportError as exc:
        raise SystemExit('Install Numba (python -m pip install numba) or use --engine scalar --limit 100.') from exc
    pack = pack_geometry(space, labels)

    @njit(inline='always', fastmath=False)
    def inside(x, y, z, planes, offsets, sides, index):
        start, end = offsets[index], offsets[index+1]
        if start == end:
            return False
        for k in range(start, end):
            a,b,c,d = planes[k]
            if sides[k] * (x*a + y*b + z*c + d) < -1e-9:
                return False
        return True

    @njit(inline='always', fastmath=False)
    def distance(x,y,z,rx,ry,rz):
        return math.sqrt((x-rx)**2+(y-ry)**2+(z-rz)**2)

    @njit(inline='always', fastmath=False)
    def intersect(rx,ry,rz,dx,dy,dz,planes,offsets,ray,index):
        tmin = np.inf
        for k in range(offsets[index], offsets[index+1]):
            if not ray[k]:
                continue
            a,b,c,d = planes[k]
            denom = a*dx+b*dy+c*dz
            if abs(denom) <= 1e-9:
                continue
            t = -(a*rx+b*ry+c*rz+d)/denom
            if 1e-9 <= t < tmin:
                tmin = t
        if not math.isfinite(tmin):
            return np.inf
        return distance(rx+tmin*dx,ry+tmin*dy,rz+tmin*dz,rx,ry,rz)

    @njit(parallel=True, fastmath=False)
    def kernel(rgb,reps,planes,offsets,sides,ray,cat_ids,ncat):
        out = np.zeros((2,len(rgb),ncat),dtype=np.float64)
        for j in prange(len(rgb)):
            x,y,z = rgb[j]
            for i in range(len(reps)):
                cat = cat_ids[i]
                if out[0,j,cat] == 1. and out[1,j,cat] == 1.:
                    continue
                if not inside(x,y,z,planes,offsets,sides,3*i+2):
                    continue
                if inside(x,y,z,planes,offsets,sides,3*i):
                    value = 1.
                else:
                    rx,ry,rz = reps[i]
                    dx,dy,dz = x-rx,y-ry,z-rz
                    a = intersect(rx,ry,rz,dx,dy,dz,planes,offsets,ray,3*i)
                    b = intersect(rx,ry,rz,dx,dy,dz,planes,offsets,ray,3*i+1)
                    c = intersect(rx,ry,rz,dx,dy,dz,planes,offsets,ray,3*i+2)
                    d = distance(x,y,z,rx,ry,rz)
                    if not (math.isfinite(a) and math.isfinite(b) and math.isfinite(c) and a <= b <= c):
                        continue
                    if d <= a:
                        value = 1.
                    elif d > c:
                        value = 0.
                    elif d <= b:
                        value = ((b-d)+(b-a))/(2*(b-a)) if b != a else 1.
                    else:
                        value = (c-d)/(2*(c-b)) if c != b else 0.
                    value = min(1.,max(0.,value))
                out[0,j,cat] = max(out[0,j,cat],value)
                out[1,j,cat] = min(1.,out[1,j,cat]+value)
        return out
    return lambda rgb: kernel(np.asarray(rgb,dtype=np.float64),*pack)


def scalar(space, labels, rgb):
    result = np.empty((2,len(rgb),len(labels)))
    for i, q in enumerate(rgb):
        for k, op in enumerate(MODES):
            d = space.calculate_hierarchy_memberships(q, input_space='RGB', include_zeros=True,tconorm=op)
            result[k,i] = [d[label] for label in labels]
    return result


def validate_batch(rows, ncat):
    rgb, reference = [], []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Invalid sample object')
        q, m = row['rgb'], row['membership']
        if not isinstance(q,list) or len(q)!=3 or any(type(v) is not int or not 0<=v<=255 for v in q):
            raise ValueError(f'Invalid RGB triplet: {q}')
        if not isinstance(m,list) or len(m)!=ncat or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in m):
            raise ValueError(f'Invalid membership vector at RGB {q}')
        rgb.append(q); reference.append(m)
    return np.asarray(rgb,dtype=np.float64), np.asarray(reference,dtype=np.float64)


class Metrics:
    def __init__(self, labels,tol):
        self.labels, self.tol, self.n = labels,tol,0
        self.abs, self.sq, self.bias, self.maximum = (np.zeros(len(labels)) for _ in range(4))
        self.hits = np.zeros(len(labels),dtype=np.int64)
        self.active, self.active_abs = np.zeros(len(labels),dtype=np.int64), np.zeros(len(labels))
        self.all_ok=self.same_winners=self.overlap_winners=0
        self.worst = None

    def update(self, rgb, ref, pred, offset):
        diff=pred-ref; err=np.abs(diff)
        self.n+=len(rgb); self.abs+=err.sum(0); self.sq+=(diff**2).sum(0); self.bias+=diff.sum(0)
        self.maximum=np.maximum(self.maximum,err.max(0)); self.hits+=(err<=self.tol).sum(0)
        active=(ref>0)|(pred>0); self.active+=active.sum(0); self.active_abs+=(err*active).sum(0)
        self.all_ok+=int(np.all(err<=self.tol,axis=1).sum())
        # Compare sets of tied winners; all-zero vectors have no winner.
        a=(ref>=ref.max(1,keepdims=True)-self.tol)&(ref>0)
        b=(pred>=pred.max(1,keepdims=True)-self.tol)&(pred>0)
        same=np.all(a==b,axis=1); self.same_winners+=int(same.sum())
        self.overlap_winners+=int((np.any(a&b,axis=1)|(~a.any(1)&~b.any(1))).sum())
        i,j=np.unravel_index(err.argmax(),err.shape)
        if self.worst is None or err[i,j]>self.worst['absolute_error']:
            self.worst=dict(sample_index=offset+int(i),rgb=rgb[i].astype(int).tolist(),category=self.labels[j],java=float(ref[i,j]),pyfcs=float(pred[i,j]),absolute_error=float(err[i,j]))

    def result(self):
        n=self.n; k=len(self.labels)
        rows=[dict(category=c,mae=float(self.abs[i]/n),rmse=float(np.sqrt(self.sq[i]/n)),bias=float(self.bias[i]/n),max_error=float(self.maximum[i]),within_tolerance_fraction=float(self.hits[i]/n),active_count=int(self.active[i]),active_mae=float(self.active_abs[i]/self.active[i]) if self.active[i] else None) for i,c in enumerate(self.labels)]
        return dict(mae=float(self.abs.sum()/(n*k)),rmse=float(np.sqrt(self.sq.sum()/(n*k))),max_error=float(self.maximum.max()),membership_within_tolerance_fraction=float(self.hits.sum()/(n*k)),samples_all_within_tolerance_fraction=self.all_ok/n,winner_set_agreement=self.same_winners/n,winner_overlap_agreement=self.overlap_winners/n,worst=self.worst,per_category=rows)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evaluation',type=Path,default=DEFAULT/'evaluation_basic_granular_complete.json')
    p.add_argument('--model',type=Path,default=DEFAULT/'basic_granular_complete_PyFCS.json')
    p.add_argument('--output-dir', type=Path,
               default=Path(__file__).resolve().parent / 'reports')
    p.add_argument('--limit',type=int); p.add_argument('--batch-size',type=int,default=32768)
    p.add_argument('--engine',choices=['fast','scalar'],default='fast'); p.add_argument('--tolerance',type=float,default=1e-6)
    p.add_argument('--verify',type=int,default=256,help='Scalar cross-check on random RGBs, prototypes and initial samples (fast mode)')
    args=p.parse_args()
    if args.batch_size<1 or args.batch_size>1000000 or args.limit is not None and args.limit<1 or not 0<args.tolerance<1 or args.verify<1:
        p.error('Invalid batch size, limit, tolerance or verify count')
    _,space=InputJSON().read_file(str(args.model))
    if not isinstance(space,GranularFuzzyColorSpace) or space.color_space!='RGB' or space.geometry_only_import or list(space.reference_domain.bounds)!=[0,255,0,255,0,255]:
        raise ValueError('Expected independently reconstructed RGB granular PyFCS model on [0,255]^3')
    if space.hierarchy:
        raise ValueError('This test supports flat granular spaces only')
    with args.evaluation.open(encoding='utf-8-sig') as f:
        stream=JSONStream(f); header=stream.header(); labels=header['fuzzy_colors']; declared=header['num_samples']
        if header.get('color_space')!='RGB' or type(declared) is not int or declared<1 or not isinstance(labels,list) or any(not isinstance(c,str) for c in labels) or len(set(labels))!=len(labels) or set(labels)!=set(space.get_color_labels()):
            raise ValueError('Evaluation metadata does not match model')
        metrics=[Metrics(labels,args.tolerance) for _ in MODES]
        evaluator=make_fast_evaluator(space,labels) if args.engine=='fast' else lambda rgb:scalar(space,labels,rgb)
        verify_max=0.
        def check(rgb,pred):
            nonlocal verify_max
            error=float(np.abs(pred-scalar(space,labels,rgb)).max())
            verify_max=max(error,verify_max)
            if error>1e-9:
                raise ValueError(f'Accelerated vs public PyFCS API discrepancy {error}; use scalar or investigate.')
        if args.engine=='fast':
            probes=np.vstack([np.random.default_rng(2026).integers(0,256,(args.verify,3)),[p.positive for p in space.get_all_prototypes()]])
            check(probes,evaluator(probes)); print(f'Fast/scalar initial check: {verify_max:.3g}',flush=True)
        n=0; start=time.perf_counter(); rows=[]; full=True
        def process(rows):
            nonlocal n
            rgb,ref=validate_batch(rows,len(labels)); pred=evaluator(rgb)
            if args.engine=='fast':
                # Verify a deterministic sample from EVERY block against public API.
                idx=np.unique(np.linspace(0,len(rgb)-1,min(3,len(rgb)),dtype=int))
                check(rgb[idx],pred[:,idx])
            for i,m in enumerate(metrics): m.update(rgb,ref,pred[i],n)
            n+=len(rows)
            print(f'{n:,}/{declared:,} samples; {n/max(time.perf_counter()-start,1e-9):,.0f} samples/s',flush=True)
        for row in stream.samples():
            rows.append(row)
            if len(rows)>=args.batch_size or (args.limit is not None and n+len(rows)>=args.limit):
                process(rows); rows=[]
            if args.limit is not None and n>=args.limit:
                full=False; break
        if rows: process(rows)
        if not n or (full and n!=declared) or n>declared: raise ValueError(f'Sample count mismatch: {n} versus {declared}')
    result=dict(model=str(args.model),model_file_sha256=hashlib.sha256(args.model.read_bytes()).hexdigest(),evaluation=str(args.evaluation),seed=header.get('seed'),declared_samples=declared,processed_samples=n,complete_file_validated=full,engine=args.engine,fast_scalar_max_error=verify_max if args.engine=='fast' else None,tolerance=args.tolerance,seconds=time.perf_counter()-start,modes={op:m.result() for op,m in zip(MODES,metrics)})
    args.output_dir.mkdir(parents=True,exist_ok=True)
    suffix='full' if full else f'partial_{n}'
    report=args.output_dir/f'comparison_{suffix}.json'; report.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    with (args.output_dir/f'categories_{suffix}.csv').open('w',newline='',encoding='utf-8') as f:
        rows=[dict(operator=op,**r) for op,m in result['modes'].items() for r in m['per_category']]
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    for op,m in result['modes'].items(): print(op, 'MAE=',m['mae'],'RMSE=',m['rmse'],'max=',m['max_error'],'all matching=',m['samples_all_within_tolerance_fraction'])
    print('Report:',report)

if __name__=='__main__': main()

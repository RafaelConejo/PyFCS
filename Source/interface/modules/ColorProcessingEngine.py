from skimage import color
import matplotlib.pyplot as plt
import math, numpy as np
from sklearn.cluster import DBSCAN
from PIL import Image
from types import SimpleNamespace
from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
import weakref
import os
import logging

# Project modules
from Source.interface.modules import UtilsTools  


"""
Module summary
--------------
This module encapsulates image- and color-related utilities that are independent from the main GUI.

It provides:
    - Generation of a grayscale membership map for a selected prototype by computing fuzzy membership
    values in LAB space (with caching + optional progress reporting).
    - Automatic main-color detection in an image using DBSCAN clustering in LAB space, returning
    representative colors in both LAB and RGB.
"""
@dataclass(frozen=True, eq=False)
class PreparedImage:
    """Immutable arrays derived from a single original image at one resolution.

    Store the quantized bins and inverse indices, not the full floating-point
    LAB image. Alpha is kept separately from RGB to preserve partial opacity.
    """
    rgb: np.ndarray
    alpha: np.ndarray
    valid_mask: np.ndarray
    colors: tuple

    @property
    def nbytes(self):
        return sum(a.nbytes for a in (self.rgb, self.alpha, self.valid_mask,
                                      self.colors[0], self.colors[1]))


class ImagePreprocessingCache:
    """Thread-safe, byte-bounded LRU for explicitly registered image snapshots.

    The application owns the original PIL snapshot and never edits it in place.
    Replacing it requires registration again; unregistered inputs are never
    cached. Tokens prevent late worker results from resurrecting closed cards.
    The budget counts retained NumPy buffers, not active jobs or result caches.
    """
    def __init__(self, max_bytes=256 * 1024**2):
        self.max_bytes = max(0, int(max_bytes))
        self._lock = RLock()
        self._sources = {}
        self._entries = OrderedDict()
        self._bytes = 0
        self._hits = self._misses = self._evictions = 0

    def register(self, owner, original):
        with self._lock:
            self.discard(owner)
            self._sources[owner] = (weakref.ref(original), object())

    def discard(self, owner):
        with self._lock:
            self._sources.pop(owner, None)
            for key in list(self._entries):
                if key[0] == owner:
                    self._bytes -= self._entries.pop(key).nbytes

    def clear(self):
        with self._lock:
            self._sources.clear()
            self._entries.clear()
            self._bytes = 0

    def _key(self, owner, original, size, mode):
        registration = self._sources.get(owner)
        if registration is None or registration[0]() is not original:
            return None
        return (owner, registration[1], tuple(size), mode)

    def peek(self, owner, original, size, mode):
        with self._lock:
            key = self._key(owner, original, size, mode)
            entry = self._entries.get(key)
            if entry is not None:
                self._entries.move_to_end(key)
            return entry

    def get_or_prepare(self, owner, original, size, mode, prepare, cancelled=None):
        if cancelled and cancelled():
            return None
        with self._lock:
            key = self._key(owner, original, size, mode)
            entry = self._entries.get(key)
            if entry is not None:
                self._hits += 1
                self._entries.move_to_end(key)
                return entry
            self._misses += 1
        # Expensive conversion/resize runs outside the lock and outside Tk.
        entry = prepare()
        if cancelled and cancelled():
            return None
        with self._lock:
            if key is not None and key == self._key(owner, original, size, mode):
                existing = self._entries.get(key)
                if existing is not None:
                    self._entries.move_to_end(key)
                    return existing
                if entry.nbytes <= self.max_bytes:
                    while self._entries and self._bytes + entry.nbytes > self.max_bytes:
                        _, old = self._entries.popitem(last=False)
                        self._bytes -= old.nbytes
                        self._evictions += 1
                    self._entries[key] = entry
                    self._bytes += entry.nbytes
        return entry

    def info(self):
        with self._lock:
            return dict(entries=len(self._entries), bytes=self._bytes,
                        max_bytes=self.max_bytes, hits=self._hits,
                        misses=self._misses, evictions=self._evictions)


# Optional compiled backend. Imported/compiled lazily, never at GUI startup.
# The scientific core remains the reference; this is only an execution adapter.
_BATCH_KERNEL = None
_BATCH_UNAVAILABLE = False
_BATCH_LOCK = RLock()


def _get_batch_kernel():
    global _BATCH_KERNEL, _BATCH_UNAVAILABLE
    with _BATCH_LOCK:
        if _BATCH_UNAVAILABLE:
            return None
        if _BATCH_KERNEL is not None:
            return _BATCH_KERNEL
        try:
            from numba import njit, config
            if config.DISABLE_JIT:
                _BATCH_UNAVAILABLE = True
                return None
        except Exception:
            _BATCH_UNAVAILABLE = True
            return None

        @njit(inline='always', fastmath=False)
        def inside(x, y, z, planes, offsets, sides, index):
            if offsets[index] == offsets[index + 1]:
                return False
            for k in range(offsets[index], offsets[index + 1]):
                a, b, c, d = planes[k]
                if sides[k] * (x*a + y*b + z*c + d) < -1e-9:
                    return False
            return True

        @njit(inline='always', fastmath=False)
        def norm(x, y, z):
            return math.sqrt(x*x + y*y + z*z)

        @njit(inline='always', fastmath=False)
        def intersect(rx, ry, rz, dx, dy, dz, planes, offsets, ray, index):
            tmin = np.inf
            for k in range(offsets[index], offsets[index + 1]):
                if not ray[k]:
                    continue
                a, b, c, d = planes[k]
                denom = a*dx + b*dy + c*dz
                if abs(denom) <= 1e-9:
                    continue
                t = -(a*rx + b*ry + c*rz + d) / denom
                if 1e-9 <= t < tmin:
                    tmin = t
            if not math.isfinite(tmin):
                return np.inf
            return norm((rx+tmin*dx)-rx, (ry+tmin*dy)-ry, (rz+tmin*dz)-rz)

        @njit(nogil=True, fastmath=False)
        def kernel(points, reps, planes, offsets, sides, ray, bounds):
            out = np.zeros((len(points), len(reps)), dtype=np.float64)
            cores = np.zeros(out.shape, dtype=np.bool_)
            for j in range(len(points)):
                x, y, z = points[j]
                if not (bounds[0]-1e-9 <= x <= bounds[1]+1e-9 and
                        bounds[2]-1e-9 <= y <= bounds[3]+1e-9 and
                        bounds[4]-1e-9 <= z <= bounds[5]+1e-9):
                    continue
                for i in range(len(reps)):
                    if not inside(x,y,z,planes,offsets,sides,3*i+2):
                        continue
                    if inside(x,y,z,planes,offsets,sides,3*i):
                        out[j,i] = 1.
                        cores[j,i] = True
                        continue
                    rx,ry,rz = reps[i]
                    dx,dy,dz = x-rx,y-ry,z-rz
                    a = intersect(rx,ry,rz,dx,dy,dz,planes,offsets,ray,3*i)
                    b = intersect(rx,ry,rz,dx,dy,dz,planes,offsets,ray,3*i+1)
                    c = intersect(rx,ry,rz,dx,dy,dz,planes,offsets,ray,3*i+2)
                    if not (math.isfinite(a) and math.isfinite(b) and math.isfinite(c)):
                        continue
                    d = norm(dx,dy,dz)
                    # Small denominators and nearly coincident boundaries can
                    # magnify roundoff. Defer those evaluations to the core.
                    guard = 1e-10 * max(1., a,b,c,d)
                    if (abs(b-a) <= 1e-4 * max(1.,a,b,c,d) or
                        abs(c-b) <= 1e-4 * max(1.,a,b,c,d) or
                        abs(d-a) <= guard or abs(d-b) <= guard or abs(d-c) <= guard):
                        out[j,i] = np.nan
                        continue
                    if not a <= b <= c:
                        continue
                    if d <= a:
                        v = 1.
                    elif d > c:
                        v = 0.
                    elif d <= b:
                        v = ((b-d)+(b-a))/(2*(b-a))
                    else:
                        v = (c-d)/(2*(c-b))
                    out[j,i] = min(1.,max(0.,v))
            return out, cores
        _BATCH_KERNEL = kernel
        return kernel


class _BatchMappingEvaluator:
    """Job-local geometry pack and semantic plan, with bounded float64 blocks.

    Never retains a mutable model across jobs. A shared physical granule is
    evaluated once, but its occurrence is preserved in each aggregation node.
    """
    GUARD = 2e-12

    def __init__(self, view, kind, category=None, granule=None):
        from Source.fuzzy.FuzzyColorSpace import FuzzyColorSpace
        from Source.fuzzy.GranularFuzzyColorSpace import GranularFuzzyColorSpace
        self.view = view
        self.semantic = type(view) is SemanticMappingView
        self.space = view.source if self.semantic else view
        if type(self.space) not in (FuzzyColorSpace, GranularFuzzyColorSpace):
            raise ValueError('Unsupported batch model')
        self.atomic = type(self.space) is FuzzyColorSpace
        self.kind = kind
        self.use_max = getattr(self.space, 'tconorm', 'max') == 'max'
        self.category = category
        self.nodes = []
        self.output = []
        if self.space._precomputed is None:
            self.space.precompute_pack()
        self.original_pack = self.space._precomputed
        self.sites = list(self.space.get_prototypes() if self.atomic else self.space.get_all_prototypes())
        self.groups = ([[i] for i in range(len(self.sites))] if self.atomic else
                       [list(g) for g in self.space._category_flat_indices])
        self.group_positions = self.groups
        if self.semantic:
            self.groups = [[self.space._granule_index[p.label] for p in cat.prototypes]
                           for cat in view.categories]
            self.group_positions = [list(range(int(view._offsets[i]), int(view._offsets[i+1])))
                                    for i in range(len(self.groups))]
        if kind == 'single' and granule is not None:
            self.output = [('g', self.groups[category][granule])]
        elif self.semantic and (kind != 'single' or view.labels[category] not in view._legacy_base_indices):
            labels = [view.labels[category]] if kind == 'single' else list(view.labels)
            graph = self.space._hierarchy
            needed = set(labels)
            stack = list(labels)
            while stack:
                for typ, target in graph.children(stack.pop()):
                    if typ == 'category' and target not in needed:
                        needed.add(target); stack.append(target)
            for name in (*graph._base, *graph._order):
                if name in needed:
                    children = [(('g', self.space._granule_index[target]) if typ == 'granule'
                                 else ('c', target)) for typ,target in graph.children(name)]
                    self.nodes.append((name, children))
            self.output = [('c', label) for label in labels]
        elif kind == 'single':
            group = self.groups[category]
            self.nodes = [(0, [('g', i) for i in group])]
            self.output = [('c', 0)]
        else:
            self.nodes = [(j, [('g', i) for i in group]) for j,group in enumerate(self.groups)]
            self.output = [('c', j) for j in range(len(self.groups))]
        selected = ({target for _, children in self.nodes for typ,target in children if typ == 'g'} |
                    {target for typ,target in self.output if typ == 'g'})
        if kind != 'single':
            selected.update(i for group in self.groups for i in group)
        self.indices = sorted(selected)
        self.columns = {i:j for j,i in enumerate(self.indices)}
        self.pack = self._pack()
        # Allow room for raw values, core flags, scores and aggregation scratch.
        self.block_size = max(1, min(2048, (16*1024**2)//(32*max(1,len(self.indices)+len(self.nodes)))))

    def _pack(self):
        p = self.original_pack
        reps, planes, offsets, sides, ray = [], [], [0], [], []
        for i in self.indices:
            reps.append(p['rep'][i].get_double_point())
            for key in ('v_cores','v_protos','v_supps'):
                volume = p[key][i]
                for face in volume.getFaces():
                    plane = face.getPlane()
                    side = plane.evaluatePoint(volume.getRepresentative())
                    if abs(side) <= 1e-9:
                        side = 0.
                        for other in volume.getFaces():
                            for vertex in other.getArrayVertex() or []:
                                v = plane.evaluatePoint(vertex)
                                if abs(v) > 1e-9:
                                    side = 1. if v > 0 else -1.
                                    break
                            if side:
                                break
                    planes.append(plane.getPlane()); sides.append(side)
                    ray.append(not face.isDomainBoundary())
                offsets.append(len(planes))
        pack = (np.asarray(reps,dtype=np.float64).reshape(-1,3),
                np.asarray(planes,dtype=np.float64).reshape(-1,4),
                np.asarray(offsets,dtype=np.int64), np.asarray(sides,dtype=np.float64),
                np.asarray(ray,dtype=np.bool_), np.asarray(self.space.reference_domain.bounds,dtype=np.float64))
        if not all(np.isfinite(a).all() for a in pack):
            raise ValueError('Non-finite batch geometry')
        return pack

    def raw(self, points, kernel):
        from Source.fuzzy.FuzzyColor import FuzzyColor
        values, cores = kernel(points, *self.pack)
        for row,col in np.argwhere(~np.isfinite(values)):
            values[row,col] = FuzzyColor._raw_membership_for_index(
                tuple(points[row].tolist()), self.indices[col], self.original_pack)
        return values, cores

    def scores(self, values):
        results = {}
        def degree(typ, target):
            return values[:,self.columns[target]] if typ == 'g' else results[target]
        for name, children in self.nodes:
            acc = np.zeros(len(values),dtype=np.float64)
            for typ,target in children:
                if self.use_max:
                    np.maximum(acc,degree(typ,target),out=acc)
                else:
                    # Sequential addition, capped at every node, exactly as
                    # GranularFuzzyColor.aggregate (including shared paths).
                    acc += degree(typ,target)
                    np.minimum(acc,1.,out=acc)
            results[name] = acc
        return np.column_stack([degree(typ,target) for typ,target in self.output])

    def evaluate(self, points, kernel, scalar):
        values, cores = self.raw(points, kernel)
        from Source.fuzzy.FuzzyColor import FuzzyColor
        mid = len(points)//2
        q = tuple(points[mid].tolist())
        if self.space.reference_domain.contains_coordinates(q, eps=1e-9):
            for col, i in enumerate(self.indices):
                ref = FuzzyColor._raw_membership_for_index(q,i,self.original_pack)
                if abs(values[mid,col]-ref) > 1e-12:
                    raise ArithmeticError("batch raw membership mismatch")
        if self.kind == 'single':
            scores = self.scores(values)[:,0]
            # Preserve the old float32 -> uint8 conversion even at thresholds.
            lo = (np.clip(scores-self.GUARD,0,1).astype(np.float32)*255).astype(np.uint8)
            hi = (np.clip(scores+self.GUARD,0,1).astype(np.float32)*255).astype(np.uint8)
            for row in np.flatnonzero(lo != hi):
                scores[row] = scalar(tuple(points[row].tolist()))
            return np.clip(scores,0,1).astype(np.float32)
        scores = self.scores(values)
        best = np.argmax(scores,axis=1).astype(np.int32)
        top = scores[np.arange(len(points)),best]
        best[top <= 0.] = -1
        grain = np.full(len(points),-1,dtype=np.int32)
        if self.atomic:
            # Atomic mapping uses strict > outside cores, and nearest actual
            # representative for multiple core hits. Preserve these separately.
            hits = cores.sum(axis=1)
            one = hits == 1
            best[one] = np.argmax(cores[one],axis=1)
            near = (np.abs(scores-top[:,None]) <= self.GUARD).sum(axis=1) > 1
            ambiguous = (hits > 1) | ((hits == 0) & (top > 0) & near)
            grain[:] = best
        else:
            # The core includes ties within 1e-12. Exact ties (particularly
            # saturated SUM values) are common; resolve those using the same
            # nearest-site rule without evaluating their geometry again.
            # Non-exact near ties and nearly equal distances use the scalar API.
            gaps = top[:,None]-scores
            ambiguous = (top > 0) & np.any((gaps>0) & (gaps<=1e-12+self.GUARD),axis=1)
            tied = np.flatnonzero((top>0) & ~ambiguous & ((gaps==0).sum(axis=1)>1))
            if len(tied):
                dists = np.full((len(tied),len(self.groups)),np.inf)
                for i,group in enumerate(self.groups):
                    rows = np.flatnonzero(gaps[tied,i]==0)
                    if len(rows):
                        positions = np.asarray([self.sites[k].positive for k in group])
                        delta = points[tied[rows],None,:]-positions[None,:,:]
                        dists[rows,i] = np.min(np.sum(delta*delta,axis=2),axis=1)
                nearest = np.argmin(dists,axis=1)
                mind = dists[np.arange(len(tied)),nearest]
                ambiguous[tied] |= ((dists-mind[:,None]) <= 1e-8).sum(axis=1)>1
                best[tied] = nearest
            if self.kind == 'best':
                grain[:] = best
            else:
                for i, group in enumerate(self.groups):
                    rows = np.flatnonzero((best==i) & ~ambiguous)
                    if not len(rows):
                        continue
                    v = values[np.ix_(rows,[self.columns[j] for j in group])]
                    local = np.argmax(v,axis=1)
                    maxv = v[np.arange(len(rows)),local]
                    gd = maxv[:,None]-v
                    uncertain = np.any((gd>0)&(gd<=1e-12+self.GUARD),axis=1)
                    tie = np.flatnonzero(~uncertain & ((gd==0).sum(axis=1)>1))
                    if len(tie):
                        positions = np.asarray([self.sites[k].positive for k in group])
                        delta = points[rows[tie],None,:]-positions[None,:,:]
                        dists = np.where(gd[tie]==0,np.sum(delta*delta,axis=2),np.inf)
                        nearest = np.argmin(dists,axis=1)
                        mind = dists[np.arange(len(tie)),nearest]
                        uncertain[tie] |= ((dists-mind[:,None])<=1e-8).sum(axis=1)>1
                        local[tie] = nearest
                    ambiguous[rows] |= uncertain
                    grain[rows] = np.asarray(self.group_positions[i],dtype=np.int32)[local]
        ambiguous |= (top>0) & (top<=self.GUARD)
        for row in np.flatnonzero(ambiguous):
            best[row],grain[row] = scalar(tuple(points[row].tolist()))
        return best,grain


class ColorProcessingEngine:
    def __init__(self, root=None, custom_warning=None, center_popup=None,
                 preprocessing_cache_bytes=256 * 1024**2, batch_mode=None):
        """
        Args:
            root: Optional reference to the main application window.
            custom_warning: Optional callback to display custom warning dialogs/messages.
            center_popup: Optional callback to center popup windows on screen.
        """
        self.root = root
        self.custom_warning = custom_warning
        self.center_popup = center_popup
        self.preprocessing_cache = ImagePreprocessingCache(preprocessing_cache_bytes)
        self.batch_mode = batch_mode or os.environ.get("PYFCS_BATCH_MODE", "auto")
        if self.batch_mode not in ("auto", "scalar", "batch"):
            raise ValueError("batch_mode must be auto, scalar or batch")
        self.batch_statistics = {"blocks": 0, "colors": 0, "fallbacks": 0}
        self._batch_failed = False

    # Simple utilities

    
    @staticmethod
    def _pil_to_rgb_uint8(image):
        """Convert PIL/array images to RGB uint8 without confusing palette indices.

        Pillow knows how to decode indexed (P), gray+alpha (LA), RGB and RGBA
        images correctly. For NumPy arrays, accept the already-expanded RGB(A)
        or grayscale representations used by the public mapping helpers.
        """
        if isinstance(image, Image.Image):
            # RGB is the common path in PyFCS: avoid a redundant full-image copy.
            rgb_image = image if image.mode == "RGB" else image.convert("RGB")
            return np.asarray(rgb_image, dtype=np.uint8)

        img_np = np.asarray(image)
        if img_np.ndim == 2:
            img_np = np.repeat(img_np[..., None], 3, axis=-1)
        elif img_np.ndim == 3 and img_np.shape[-1] >= 3:
            img_np = img_np[..., :3]
        else:
            raise ValueError("Expected an RGB/RGBA or grayscale image array.")
        return np.clip(img_np, 0, 255).astype(np.uint8, copy=False)

    def _pil_to_lab_image(self, image):
        """Convert a PIL image to LAB using skimage, returning an H x W x 3 float array."""
        img_rgb = self._pil_to_rgb_uint8(image)
        img01 = img_rgb.astype(np.float32) / 255.0
        return color.rgb2lab(img01)

    @staticmethod
    def _model_space_name(space):
        return "RGB" if getattr(space, "color_space", "LAB") == "RGB" else "LAB"

    def prepare_image(self, original, target_size, space, *, owner=None, cancelled=None):
        """Resize and prepare a registered original once for mapping operations.

        Raw PIL/array mapping APIs keep their existing uncached behavior. This
        explicit path is for immutable, window-owned source snapshots only.
        """
        size = tuple(target_size)
        mode = self._model_space_name(space)

        def prepare():
            source = (original if original.size == size else
                      original.resize(size, Image.Resampling.LANCZOS))
            alpha = UtilsTools._get_alpha_values_from_pil(source)
            processing = UtilsTools._pil_rgb_for_processing(source)
            rgb = self._pil_to_rgb_uint8(processing)
            valid = alpha > 0
            # Use the same RGB uint8 -> float32 -> LAB conversion as before.
            colors = self._unique_model_colors(processing, space)
            for array in (rgb, alpha, valid, colors[0], colors[1]):
                array.setflags(write=False)
            return PreparedImage(rgb, alpha, valid, colors)

        return self.preprocessing_cache.get_or_prepare(
            owner, original, size, mode, prepare, cancelled)

    def peek_prepared_image(self, original, target_size, space, *, owner=None):
        return self.preprocessing_cache.peek(
            owner, original, target_size, self._model_space_name(space))

    def _unique_model_colors(self, image, fuzzy_color_space):
        """Quantize image colors once and return unique model-space values.

        Shared by single-prototype mapping and Mapping All, preventing the two
        paths from drifting in conversion or quantization behavior.
        """
        rgb_model = self._model_space_name(fuzzy_color_space) == "RGB"
        if isinstance(image, PreparedImage):
            if image.colors[-1] != self._model_space_name(fuzzy_color_space):
                raise ValueError("Prepared image color space does not match the model.")
            return image.colors
        model_image = self._pil_to_rgb_uint8(image) if rgb_model else self._pil_to_lab_image(image)
        height, width = model_image.shape[:2]
        scale = 1.0 if rgb_model else 100.0
        source_space = "RGB" if rgb_model else "LAB"
        # Pack RGB into 24 bits, LAB bins into three unsigned 16-bit fields.
        # Integer ordering preserves the original lexicographic row order.
        if rgb_model:
            pixels = model_image.reshape(-1, 3)
            keys = pixels[:, 0].astype(np.uint32) << 16
            keys |= pixels[:, 1].astype(np.uint32) << 8
            keys |= pixels[:, 2]
            unique_keys, inverse = np.unique(keys, return_inverse=True)
            uniq = np.column_stack((unique_keys >> 16,
                                   (unique_keys >> 8) & 255,
                                   unique_keys & 255)).astype(np.int32)
        else:
            integer_colors = np.rint(model_image.reshape(-1, 3) * scale).astype(np.int32)
            if integer_colors.size and (integer_colors.min() < -32768 or
                                        integer_colors.max() > 32767):
                # Preserve the generic path for unusual/custom conversions.
                uniq, inverse = np.unique(integer_colors, axis=0, return_inverse=True)
            else:
                keys = (integer_colors[:, 0].astype(np.int64) + 32768) << 32
                keys |= (integer_colors[:, 1].astype(np.int64) + 32768) << 16
                keys |= integer_colors[:, 2].astype(np.int64) + 32768
                unique_keys, inverse = np.unique(keys, return_inverse=True)
                uniq = np.column_stack((unique_keys >> 32,
                                       (unique_keys >> 16) & 65535,
                                       unique_keys & 65535)).astype(np.int32) - 32768
        return uniq, inverse, height, width, scale, source_space

    def _batch_mapping(self, space, uniq, scale, source_space, kind, scalar,
                       progress_callback, cancel_callback, category=None, granule=None):
        """Return (handled, result). None result means cancelled.

        Optional backend with per-block scalar cross-checks. On failure, keep
        the original mapping path, rather than returning a partial image.
        """
        if (self.batch_mode == "scalar" or self._batch_failed or not len(uniq) or
                source_space != getattr(space, "color_space", None) or
                (self.batch_mode == "auto" and len(uniq) < 1024)):
            return False, None
        if cancel_callback and cancel_callback():
            return True, None
        try:
            evaluator = _BatchMappingEvaluator(space, kind, category, granule)
        except (ValueError, AttributeError, TypeError, IndexError):
            return False, None
        try:
            kernel = _get_batch_kernel()
            if kernel is None:
                return False, None
            single = kind == "single"
            first = np.empty(len(uniq), dtype=np.float32 if single else np.int32)
            second = None if single else np.empty(len(uniq), dtype=np.int32)
            for start in range(0,len(uniq),evaluator.block_size):
                if cancel_callback and cancel_callback():
                    return True, None
                end = min(start+evaluator.block_size,len(uniq))
                # Critical: match the original float32 division BEFORE float64.
                points = (uniq[start:end].astype(np.float32)/scale).astype(np.float64)
                result = evaluator.evaluate(points,kernel,scalar)
                if cancel_callback and cancel_callback():
                    return True, None
                if getattr(evaluator.space, 'tconorm', 'max') != ('max' if evaluator.use_max else 'bounded_sum'):
                    return True, None  # The UI must launch a new job for the new operator.
                # Deterministic checks of each block against the scalar API.
                for j in sorted({0,len(points)//2,len(points)-1}):
                    expected = scalar(tuple(points[j].tolist()))
                    if single:
                        actual = result[j]
                        expected = np.float32(np.clip(expected,0,1))
                        if actual != expected:
                            # Check the final grayscale byte, not only closeness.
                            if np.uint8(actual* np.float32(255)) != np.uint8(expected*np.float32(255)):
                                raise ArithmeticError("batch membership byte mismatch")
                    elif (int(result[0][j]),int(result[1][j])) != tuple(expected):
                        raise ArithmeticError("batch classification mismatch")
                if single:
                    first[start:end] = result
                else:
                    first[start:end],second[start:end] = result
                self.batch_statistics["blocks"] += 1
                self.batch_statistics["colors"] += end-start
                if progress_callback:
                    progress_callback(end,len(uniq))
                if cancel_callback and cancel_callback():
                    return True, None
            return True, first if single else (first,second)
        except Exception as exc:
            if cancel_callback and cancel_callback():
                return True, None
            # Import/compilation/runtime mismatch must not break the UI.
            # Log once per engine; the scalar implementation is unchanged.
            self._batch_failed = True
            self.batch_statistics["fallbacks"] += 1
            logging.getLogger(__name__).warning("Batch mapping disabled; using scalar engine: %s",exc)
            return False, None

    def get_proto_percentage(
        self,
        prototypes,
        image,
        fuzzy_color_space,
        selected_option,
        progress_callback=None,
        cancel_callback=None,
        granule_index=None,
    ):
        """
        Generate a grayscale membership map for one selected prototype.

        Optimized version:
        - Converts RGB -> LAB once.
        - Quantizes LAB to 0.01.
        - Computes membership only for unique LAB values.
        - Reconstructs the full image using the inverse map.
        """
        if selected_option < 0 or selected_option >= len(prototypes):
            raise ValueError("Selected prototype index is out of range.")
        if granule_index is not None:
            if not getattr(fuzzy_color_space, "is_granular", False):
                raise ValueError("Granule mapping requires a granular color space.")
            category = fuzzy_color_space.categories[selected_option]
            if not 0 <= int(granule_index) < len(category.prototypes):
                raise ValueError("Selected granule index is out of range.")
            granule_index = int(granule_index)

        if cancel_callback and cancel_callback():
            return None

        # Construct/evaluate directly in the space used by the loaded FCS.
        # RGB is encoded as 0..255 channel values; LAB is quantized to 0.01.
        uniq, inv, height, width, scale, source_space = self._unique_model_colors(
            image, fuzzy_color_space
        )

        values_for_uniq = np.empty((uniq.shape[0],), dtype=np.float32)
        total_uniqs = int(uniq.shape[0])

        category_evaluator = None
        if granule_index is None and isinstance(fuzzy_color_space, SemanticMappingView):
            category_evaluator = fuzzy_color_space.prepare_category_evaluator(selected_option)
        def scalar(lab_tuple):
            if category_evaluator is not None:
                value = category_evaluator(lab_tuple, source_space)
            elif granule_index is None:
                value = fuzzy_color_space.calculate_membership_for_prototype(
                    lab_tuple, selected_option, input_space=source_space
                )
            elif getattr(fuzzy_color_space, "is_semantic_mapping_view", False):
                value = fuzzy_color_space.granule_membership(
                    lab_tuple, selected_option, granule_index, input_space=source_space)
            else:
                # The individual raw degree is independent of the T-conorm.
                # Reuse the geometry pack and the same quantized model color.
                from Source.fuzzy.FuzzyColor import FuzzyColor
                coords = fuzzy_color_space._coordinates(lab_tuple, source_space)
                if not fuzzy_color_space.reference_domain.contains_coordinates(coords, eps=1e-9):
                    value = 0.0
                else:
                    if fuzzy_color_space._precomputed is None:
                        fuzzy_color_space.precompute_pack()
                    flat_index = fuzzy_color_space._category_flat_indices[selected_option][granule_index]
                    value = FuzzyColor._raw_membership_for_index(
                        coords, flat_index, fuzzy_color_space._precomputed)
            return float(value)

        handled, batch = self._batch_mapping(
            fuzzy_color_space, uniq, scale, source_space, "single", scalar,
            progress_callback, cancel_callback, selected_option, granule_index)
        if handled:
            if batch is None:
                return None
            values_for_uniq = batch
        else:
            for i in range(total_uniqs):
                if cancel_callback and cancel_callback():
                    return None
                lab_tuple = tuple((uniq[i].astype(np.float32) / scale).tolist())
                values_for_uniq[i] = np.clip(scalar(lab_tuple), 0.0, 1.0)
                if progress_callback and (i % 500 == 0 or i == total_uniqs - 1):
                    if cancel_callback and cancel_callback():
                        return None
                    progress_callback(i + 1, total_uniqs)

        grayscale_image = (
            values_for_uniq[inv]
            .reshape(height, width)
            * 255.0
        ).astype(np.uint8)

        return grayscale_image

    @staticmethod
    def colorize_membership_map(membership_gray, original_rgb):
        """JFCS color mapping: original RGB multiplied by fuzzy membership.

        `membership_gray` is the existing 0..255 grayscale membership map;
        `original_rgb` is an H x W x 3 uint8 RGB array. The output is RGB,
        and the original arrays are never modified. This is NOT prototype
        recoloring (that remains the separate Color Mapping All workflow).
        """
        degrees = np.asarray(membership_gray)
        original = np.asarray(original_rgb)
        if degrees.ndim != 2:
            raise ValueError("The membership map must be a two-dimensional array.")
        if original.ndim != 3 or original.shape[:2] != degrees.shape or original.shape[2] != 3:
            raise ValueError("The original RGB image must match the membership map size.")
        return np.clip(
            original.astype(np.float32) * (degrees.astype(np.float32) / 255.0)[..., None],
            0, 255
        ).astype(np.uint8)

    @staticmethod
    def estimate_proto_coverage(grayscale_image_array, valid_mask):
        """
        Estimate the percentage of valid pixels covered by a prototype membership map.

        Keeps your previous threshold behavior:
        - binary-like maps with 255 use threshold 255
        - continuous maps use threshold 128
        """
        if grayscale_image_array is None:
            return 0.0, 128

        valid_total = int(np.count_nonzero(valid_mask))
        if valid_total == 0:
            return 0.0, 128

        if grayscale_image_array.ndim == 2:
            unique_vals = np.unique(grayscale_image_array)
            if unique_vals.size <= 3 and 255 in unique_vals:
                threshold = 255
            else:
                threshold = 128

            colored = int(np.count_nonzero((grayscale_image_array >= threshold) & valid_mask))
        else:
            threshold = 128
            colored = int(np.count_nonzero(np.any(grayscale_image_array != 0, axis=-1) & valid_mask))

        pct = 100.0 * (colored / valid_total)
        return pct, threshold

    def get_best_prototype_label_map(
        self,
        image,
        fuzzy_color_space,
        valid_mask=None,
        progress_callback=None,
        cancel_callback=None,
    ):
        """
        Compute the best-prototype label map for the full image.

        Returns:
            np.ndarray of shape (H, W), dtype int32.
            Pixels without assignment/background are -1 when valid_mask is supplied.
        """
        if cancel_callback and cancel_callback():
            return None

        if getattr(fuzzy_color_space, "_precomputed", None) is None:
            fuzzy_color_space.precompute_pack()

        # Construct/evaluate directly in the space used by the loaded FCS.
        # RGB is encoded as 0..255 channel values; LAB is quantized to 0.01.
        uniq, inv, height, width, scale, source_space = self._unique_model_colors(
            image, fuzzy_color_space
        )

        best_for_uniq = np.empty((uniq.shape[0],), dtype=np.int32)
        total_uniqs = int(uniq.shape[0])

        def scalar(point):
            best = fuzzy_color_space.best_prototype_index(point,input_space=source_space)
            best = int(best) if best is not None else -1
            return best,best

        handled, batch = self._batch_mapping(
            fuzzy_color_space, uniq, scale, source_space, "best", scalar,
            progress_callback, cancel_callback)
        if handled:
            if batch is None:
                return None
            best_for_uniq = batch[0]
        else:
            for i in range(total_uniqs):
                if cancel_callback and cancel_callback():
                    return None
                lab_tuple = tuple((uniq[i].astype(np.float32) / scale).tolist())
                best_for_uniq[i] = scalar(lab_tuple)[0]
                if progress_callback and (i % 500 == 0 or i == total_uniqs - 1):
                    if cancel_callback and cancel_callback():
                        return None
                    progress_callback(i + 1, total_uniqs)

        label_map = best_for_uniq[inv].reshape(height, width).astype(np.int32)

        if valid_mask is not None:
            if valid_mask.shape != label_map.shape:
                raise ValueError("valid_mask shape does not match the generated label map.")
            label_map[~valid_mask] = -1

        return label_map

    def get_category_granule_label_maps(
        self, image, fuzzy_color_space, valid_mask=None,
        progress_callback=None, cancel_callback=None,
    ):
        """Return (winning_category, winning_granule) image maps.

        Flattened granule indices follow ``get_all_prototypes()``. The winning
        category is ALWAYS chosen first, using the current T-conorm, and the
        winning granule is then chosen only from that category. Atomic spaces
        use one granule per category and therefore return identical maps.
        This processes the quantized unique image colors just once.
        """
        if cancel_callback and cancel_callback():
            return None
        if getattr(fuzzy_color_space, "_precomputed", None) is None:
            fuzzy_color_space.precompute_pack()
        uniq, inverse, height, width, scale, source_space = self._unique_model_colors(
            image, fuzzy_color_space)
        categories = np.full(len(uniq), -1, dtype=np.int32)
        granules = np.full(len(uniq), -1, dtype=np.int32)
        granular = bool(getattr(fuzzy_color_space, "is_granular", False))
        semantic = bool(getattr(fuzzy_color_space, "is_semantic_mapping_view", False))
        from Source.fuzzy.GranularFuzzyColorSpace import GranularFuzzyColorSpace
        reuse_flat = type(fuzzy_color_space) is GranularFuzzyColorSpace
        if reuse_flat:
            winning_pair = self._prepare_flat_winning_pair(fuzzy_color_space)
        if granular and not semantic and not reuse_flat:
            from Source.fuzzy.FuzzyColor import FuzzyColor
            category_indices = fuzzy_color_space._category_flat_indices
            flat_prototypes = fuzzy_color_space.get_all_prototypes()
            pack = fuzzy_color_space._precomputed
        def scalar(point):
            category_result, granule_result = -1, -1
            if semantic:
                return fuzzy_color_space.winning_pair(point, input_space=source_space)
            elif reuse_flat:
                return winning_pair(point, source_space)
            else:
                category_index = fuzzy_color_space.best_prototype_index(
                    point, input_space=source_space)
                if category_index is not None and int(category_index) >= 0:
                    category_index = int(category_index)
                    category_result = category_index
                    if not granular:
                        granule_result = category_index
                    else:
                        coords = fuzzy_color_space._coordinates(point, source_space)
                        available = category_indices[category_index]
                        # This comparison is only among granules of the winning
                        # category, preventing contradictions with Bounded Sum.
                        values = [float(FuzzyColor._raw_membership_for_index(
                            coords, flat_i, pack)) for flat_i in available]
                        maximum = max(values, default=0.0)
                        winners = [j for j, val in enumerate(values)
                                   if abs(val - maximum) <= 1e-12]
                        if winners:
                            query = np.asarray(coords, dtype=float)
                            local_winner = min(winners, key=lambda j: (
                                float(np.dot(flat_prototypes[available[j]].positive - query,
                                             flat_prototypes[available[j]].positive - query)), j))
                            granule_result = available[local_winner]
            return category_result, granule_result

        handled, batch = self._batch_mapping(
            fuzzy_color_space, uniq, scale, source_space, "pair", scalar,
            progress_callback, cancel_callback)
        if handled:
            if batch is None:
                return None
            categories, granules = batch
        else:
            for i, color_bin in enumerate(uniq):
                if cancel_callback and cancel_callback():
                    return None
                point = tuple((color_bin.astype(np.float32) / scale).tolist())
                categories[i], granules[i] = scalar(point)
                if progress_callback and (i % 500 == 0 or i == len(uniq) - 1):
                    if cancel_callback and cancel_callback():
                        return None
                    progress_callback(i + 1, len(uniq))
        categories = categories[inverse].reshape(height, width)
        granules = granules[inverse].reshape(height, width)
        if valid_mask is not None:
            if valid_mask.shape != (height, width):
                raise ValueError("valid_mask shape does not match the generated label maps.")
            categories = categories.copy()
            granules = granules.copy()
            categories[~valid_mask] = -1
            granules[~valid_mask] = -1
        return categories, granules

    @staticmethod
    def _prepare_flat_winning_pair(space):
        """Use each atomic membership at most once per point.

        Preserve the core's category order, saturation and tie tolerance. If
        aggregation stops at 1, complete only the winning category's remaining
        granules for Detailed. No values are retained across different points.
        """
        from Source.fuzzy.FuzzyColor import FuzzyColor
        if space._precomputed is None:
            space.precompute_pack()
        pack = space._precomputed
        groups = space._category_flat_indices
        sites = space.get_all_prototypes()
        raw = FuzzyColor._raw_membership_for_index

        def pair(point, input_space):
            coords = space._coordinates(point, input_space)
            if not space.reference_domain.contains_coordinates(coords, eps=1e-9):
                return -1, -1
            values = [None] * len(sites)
            scores = []
            use_max = space.tconorm == "max"
            for indices in groups:
                score = 0.0
                for i in indices:
                    v = raw(coords, i, pack)
                    values[i] = v
                    score = max(score, v) if use_max else score + v
                    if score >= 1.0:
                        break
                scores.append(score if use_max else min(score, 1.0))
            top = max(scores, default=0.0)
            if top <= 0.0:
                return -1, -1
            winners = [i for i, v in enumerate(scores) if abs(v - top) <= 1e-12]
            q = np.asarray(coords, dtype=float)

            def distance(i):
                delta = sites[i].positive - q
                return float(np.dot(delta, delta))

            category = winners[0] if len(winners) == 1 else min(
                winners, key=lambda i: (min(distance(j) for j in groups[i]), i))
            indices = groups[category]
            for i in indices:
                if values[i] is None:
                    values[i] = raw(coords, i, pack)
            maximum = max(values[i] for i in indices)
            local = min((j for j, i in enumerate(indices)
                         if abs(values[i] - maximum) <= 1e-12),
                        key=lambda j: (distance(indices[j]), j))
            return category, indices[local]

        return pair

    @staticmethod
    def build_granule_alt_palette_uint8(space, category_palette):
        """Category-related distinct shades for a granular Mapping All legend."""
        colors = []
        if not getattr(space, "is_granular", False):
            return np.asarray(category_palette, dtype=np.uint8).copy()
        for ci, cat in enumerate(space.categories):
            base = np.asarray(category_palette[ci], dtype=np.float64)
            count = len(cat.prototypes)
            for gi in range(count):
                # Keep each category's hue family, but reveal its granules.
                ratio = 0.0 if count == 1 else gi / (count - 1)
                if ratio < 0.5:
                    amount = 0.35 * (1.0 - ratio * 2.0)
                    shade = base * (1.0 - amount) + 255.0 * amount
                else:
                    amount = 0.34 * ((ratio - 0.5) * 2.0)
                    shade = base * (1.0 - amount)
                colors.append(np.rint(np.clip(shade, 0, 255)).astype(np.uint8))
        return np.asarray(colors, dtype=np.uint8).reshape(-1, 3)

    @staticmethod
    def build_original_palette_uint8(prototypes, color_space="LAB"):
        """Actual sRGB colors of the stored FCS representatives, in prototype order.

        The saved FCS geometry may be LAB or RGB; its display palette is always
        RGB. Never depend on the Data tab's HEX-keyed dictionary: repeated HEX
        values would silently collapse entries and shift label/color alignment.
        """
        if not prototypes:
            return np.empty((0, 3), dtype=np.uint8)
        coords = np.asarray([p.positive for p in prototypes], dtype=np.float64).reshape(-1, 3)
        if not np.all(np.isfinite(coords)):
            raise ValueError("FCS prototype coordinates must be finite.")
        mode = str(color_space).upper()
        if mode == "RGB":
            rgb255 = coords
        elif mode == "LAB":
            rgb255 = color.lab2rgb(coords.reshape(1, -1, 3)).reshape(-1, 3) * 255.0
        else:
            raise ValueError("FCS color space must be LAB or RGB.")
        return np.rint(np.clip(rgb255, 0.0, 255.0)).astype(np.uint8)

    @staticmethod
    def build_alt_palette_uint8(prototypes, hex_color=None):
        """High-contrast artificial colors to distinguish assigned categories.

        `hex_color` remains optional for backwards-compatible callers, but it
        is intentionally NOT used to construct the alternative palette.
        """
        n = len(prototypes)
        if n == 0:
            return np.empty((0, 3), dtype=np.uint8)

        qualitative_cmaps = ("tab20", "tab20b", "tab20c", "Set3", "Dark2", "Accent")
        palette = []
        for cmap_name in qualitative_cmaps:
            cmap = plt.get_cmap(cmap_name)
            for i in range(cmap.N):
                palette.append(np.rint(np.asarray(cmap(i)[:3]) * 255.0).astype(np.uint8))
                if len(palette) >= n:
                    break
            if len(palette) >= n:
                break
        if len(palette) < n:
            cmap = plt.get_cmap("hsv", n - len(palette))
            for i in range(n - len(palette)):
                palette.append(np.rint(np.asarray(cmap(i)[:3]) * 255.0).astype(np.uint8))
        return np.stack(palette, axis=0)

    @staticmethod
    def recolor_label_map(label_map, palette_uint8, source_alpha=None):
        """
        Convert a label map to an RGBA image using a palette.
        label_map == -1 remains transparent/background.
        """
        h, w = label_map.shape[:2]
        recolored_rgb = np.zeros((h, w, 3), dtype=np.uint8)

        valid_label_mask = (label_map >= 0) & (label_map < len(palette_uint8))
        if np.any(valid_label_mask):
            idx = label_map[valid_label_mask].astype(np.int32)
            recolored_rgb[valid_label_mask] = palette_uint8[idx]

        if source_alpha is not None:
            source_alpha = UtilsTools._alpha_u8(source_alpha, (h, w))
            final_alpha = np.where(valid_label_mask, source_alpha, 0).astype(np.uint8)
        else:
            final_alpha = valid_label_mask
        return UtilsTools._apply_alpha_to_rgb_array(recolored_rgb, final_alpha)


    def get_fcs_image(
        self,
        image,
        threshold=0.5,
        min_samples=160,
        max_pixels=80000,
        max_side=650,
        lab_quantization=1.0,
        max_unique_bins=18000,
    ):
        """
        Detect the main colors in an image using DBSCAN clustering in LAB space.

        Optimized version:
        - Uses a resized copy only for automatic detection.
        - Limits the number of processed pixels to avoid MemoryError.
        - Quantizes LAB values and uses DBSCAN sample_weight to reduce memory usage.
        - Keeps the same output format: [{"rgb": (R,G,B), "lab": (L,A,B)}, ...].

        Parameters
        ----------
        image:
            PIL image or array-like image.
        threshold:
            Detection threshold. Higher threshold means smaller DBSCAN eps.
        min_samples:
            Base DBSCAN min_samples.
        max_pixels:
            Maximum number of pixels used for clustering after resize/sampling.
        max_side:
            Maximum width or height used for automatic detection.
        lab_quantization:
            LAB quantization step. Higher values are faster and more compact.
            Recommended: 0.5 to 2.0. Default 1.0 is a good balance.
        max_unique_bins:
            Upper bound on distinct LAB bins passed to DBSCAN. Only when the
            bound is exceeded is LAB quantization coarsened adaptively. This
            preserves the old result for normal-sized detection problems.
        """
        if image is None:
            return []

        try:
            if isinstance(image, Image.Image):
                # Indexed PNG/GIF images can carry transparency in image.info,
                # even though their bands are only ("P",). Preserve that alpha
                # before the DBSCAN visible-pixel filter below.
                has_alpha = "A" in image.getbands() or "transparency" in image.info
                pil_img = image.convert("RGBA" if has_alpha else "RGB")
            else:
                img_np = np.asarray(image)

                if img_np.dtype != np.uint8:
                    img_np = np.clip(img_np, 0, 255).astype(np.uint8)

                if img_np.ndim == 2:
                    pil_img = Image.fromarray(img_np, mode="L").convert("RGB")
                elif img_np.ndim == 3:
                    if img_np.shape[-1] == 4:
                        pil_img = Image.fromarray(img_np, mode="RGBA")
                    else:
                        pil_img = Image.fromarray(img_np[..., :3], mode="RGB")
                else:
                    return []
        except Exception:
            return []

        original_w, original_h = pil_img.size
        original_pixels = max(1, original_w * original_h)

        scale_by_side = 1.0
        if max_side is not None and max_side > 0:
            scale_by_side = min(1.0, float(max_side) / float(max(original_w, original_h)))

        scale_by_pixels = 1.0
        if max_pixels is not None and max_pixels > 0:
            scale_by_pixels = min(1.0, math.sqrt(float(max_pixels) / float(original_pixels)))

        scale = min(scale_by_side, scale_by_pixels)

        if scale < 1.0:
            new_w = max(1, int(round(original_w * scale)))
            new_h = max(1, int(round(original_h * scale)))

            try:
                resample_filter = Image.Resampling.BOX
            except AttributeError:
                resample_filter = Image.BOX

            pil_img = pil_img.resize((new_w, new_h), resample_filter)

        img_np = np.asarray(pil_img, dtype=np.uint8)

        if img_np.ndim == 2:
            img_np = np.stack([img_np, img_np, img_np], axis=-1)
        elif img_np.ndim == 3 and img_np.shape[-1] == 4:
            # Only visible pixels contribute to the detected color clusters.
            visible = img_np[..., 3] > 0
            img_np = img_np[..., :3][visible]
        elif img_np.ndim == 3 and img_np.shape[-1] > 3:
            img_np = img_np[..., :3]

        if img_np.size == 0:
            return []
        img01 = img_np.astype(np.float32) / 255.0
        lab_img = color.rgb2lab(img01).astype(np.float32, copy=False)

        pixels = lab_img.reshape((-1, 3))
        total_pixels = pixels.shape[0]

        if total_pixels == 0:
            return []

        # Safety pixel cap after resize
        if max_pixels is not None and max_pixels > 0 and total_pixels > max_pixels:
            # Sample uniformly and deterministically for repeatable detection.
            idx = np.linspace(0, total_pixels - 1, int(max_pixels), dtype=np.int64)
            pixels = pixels[idx]
            total_pixels = pixels.shape[0]

        # Quantize LAB and group repeated/similar values
        q = max(0.05, float(lab_quantization))

        lab_q = np.round(pixels / q).astype(np.int32)

        # Cluster weighted LAB bins rather than every image pixel.
        unique_lab_q, counts = np.unique(
            lab_q,
            axis=0,
            return_counts=True
        )

        # DBSCAN neighborhood search can still become expensive when nearly
        # every quantized LAB point is distinct. Bound the input size by
        # adaptively coarsening quantization; small images are unaffected.
        if max_unique_bins is not None and max_unique_bins > 0:
            for _attempt in range(12):
                if len(unique_lab_q) <= int(max_unique_bins):
                    break
                q *= 1.5
                lab_q = np.round(pixels / q).astype(np.int32)
                unique_lab_q, counts = np.unique(
                    lab_q, axis=0, return_counts=True
                )
        unique_pixels = unique_lab_q.astype(np.float32) * q

        if unique_pixels.shape[0] == 0:
            return []

        # DBSCAN on unique LAB values using sample weights
        eps = max(0.05, 1.5 - float(threshold))

        effective_min_samples = max(5, int(min_samples))

        # Limit density requirements for small images.
        effective_min_samples = min(
            effective_min_samples,
            max(5, int(total_pixels * 0.10))
        )

        dbscan = DBSCAN(
            eps=eps,
            min_samples=effective_min_samples
        )

        try:
            labels = dbscan.fit_predict(
                unique_pixels,
                sample_weight=counts
            )
        except MemoryError:
            # Retry with coarser LAB bins if clustering exceeds available memory.
            q = max(q * 2.0, 2.0)
            lab_q = np.round(pixels / q).astype(np.int32)

            unique_lab_q, counts = np.unique(
                lab_q,
                axis=0,
                return_counts=True
            )

            unique_pixels = unique_lab_q.astype(np.float32) * q

            labels = dbscan.fit_predict(
                unique_pixels,
                sample_weight=counts
            )

        colors_found = []

        for label in set(labels):
            if label == -1:
                continue

            mask = labels == label

            if not np.any(mask):
                continue

            cluster_pixels = unique_pixels[mask]
            cluster_weights = counts[mask].astype(np.float32)

            if cluster_pixels.shape[0] == 0:
                continue

            mean_color_lab = np.average(
                cluster_pixels,
                axis=0,
                weights=cluster_weights
            )

            mean_color_rgb = color.lab2rgb([[mean_color_lab]])
            mean_color_rgb = np.clip(mean_color_rgb[0, 0] * 255.0, 0, 255)
            mean_color_rgb = np.round(mean_color_rgb).astype(int)

            colors_found.append({
                "rgb": tuple(int(v) for v in mean_color_rgb),
                "lab": tuple(float(v) for v in mean_color_lab),
                "weight": int(np.sum(cluster_weights))
            })

        # Sort by cluster size, largest colors first
        colors_found.sort(key=lambda item: item.get("weight", 0), reverse=True)

        # Return the public RGB/LAB fields without internal cluster weights.
        return [
            {
                "rgb": item["rgb"],
                "lab": item["lab"]
            }
            for item in colors_found
        ]

# Semantic mapping views (General / Detailed)
# These read-only adapters reuse physical granules and the original hierarchy API.
# Shared DAG paths preserve aggregation multiplicity; geometry is never rebuilt.

def has_mapping_detail(space):
    return bool(getattr(space, "is_granular", False) and
                (space.hierarchy or any(len(c.prototypes) > 1 for c in space.categories)))


def general_labels(space):
    """Use semantic parents, but do not compete with single-granule aliases.

    Brazil-style alias-only exports keep their original four base categories.
    For actual nesting, roots with category children replace their descendants.
    An independent alias-only group with leaves not contained in any primary
    root is retained, so no geometry is lost.
    """
    base = tuple(p.label for p in space.prototypes)
    if not getattr(space, "hierarchy", None):
        return base
    roots = tuple(space.get_root_categories())
    primary = tuple(label for label in roots if label in base or
                    any(kind == "category" for kind, _ in space.get_category_children(label)))
    leaves = [{p.label for p in space.get_descendant_granules(label)} for label in primary]
    return tuple(label for label in roots if label in primary or
                 not any({p.label for p in space.get_descendant_granules(label)} <= group
                         for group in leaves))


def general_mapping_space(space):
    labels = general_labels(space)
    if labels == tuple(p.label for p in space.prototypes):
        return space  # Preserve legacy normalization and exact flat tie-breaking.
    return SemanticMappingView(space, labels, "General")


def single_mapping_space(space):
    if not getattr(space, "hierarchy", None):
        return space
    main = general_labels(space)
    labels = main + tuple(label for label in space.get_all_category_labels() if label not in main)
    return SemanticMappingView(space, labels, "Detailed", preserve_base=(main == tuple(p.label for p in space.prototypes)))


def mapping_category_rows(source, view, expanded, detailed=False):
    """Build compact rows with stable selection indices; expand only visible branches.

    Each root is traversed once per unique semantic node. Other DAG paths are
    still evaluated by the source API, not flattened for membership aggregation.
    Aliases omitted from General remain independently selectable in Detailed.
    """
    granular = bool(getattr(view, "is_granular", False))
    labels = tuple(p.label for p in view.prototypes)
    positions = {label: i for i, label in enumerate(labels)}
    sites = [tuple(c.prototypes) for c in view.categories] if granular else [(p,) for p in view.prototypes]
    flat = [p for group in sites for p in group]
    colors = ColorProcessingEngine.build_original_palette_uint8(flat, view.color_space)
    offsets = np.cumsum([0]+[len(group) for group in sites])
    roots = list(general_labels(source))
    if detailed and getattr(source, "hierarchy", None):
        roots.extend(label for label in source.get_root_categories() if label not in roots)
    rows = []
    # The root rows are always retained, even for very large flat spaces.
    extra_count = 0
    limited = False
    for root in roots:
        seen = set()
        stack = [("category", root, 0, None)]
        while stack:
            kind, label, depth, parent = stack.pop()
            if depth and (extra_count >= 2000 or depth > 64):
                limited = True
                continue
            if kind == "granule":
                ci = positions[parent]
                gi = next(i for i, p in enumerate(sites[ci]) if p.label == label)
                rows.append({"type":"granule", "name":label, "category":ci,
                             "granule":gi, "depth":depth,
                             "rgb":tuple(int(v) for v in colors[offsets[ci]+gi]),
                             "selection":("granule",ci,gi)})
                extra_count += 1
                continue
            # A shared category can appear under two parents. Retain its row
            # under both, but expand its subtree only once per root.
            repeated = label in seen
            seen.add(label)
            ci = positions[label]
            count = len(sites[ci])
            swatches = colors[offsets[ci]:offsets[ci+1]]
            children = tuple(source.get_category_children(label)) if granular else ()
            # Avoid redundant singletons, except explicit category-to-category links.
            expandable = detailed and not repeated and bool(children) and (count > 1 or any(k == "category" for k,_ in children))
            rows.append({"type":"category", "name":label, "category":ci, "depth":depth,
                         "count":count, "swatches":swatches, "rgb":tuple(int(v) for v in swatches[0]),
                         "selection":("category",ci), "expandable":expandable})
            if depth:
                extra_count += 1
            if expandable and ci in expanded:
                stack.extend((k, target, depth+1, label) for k,target in reversed(children))
    if limited:
        rows.append({"type":"notice", "name":"Detail limit reached", "rgb":(180,180,180)})
    return rows


class SemanticMappingView:
    is_granular = True
    is_semantic_mapping_view = True

    def __init__(self, source, labels, name, preserve_base=False):
        self.source = source
        self.mapping_choice = name
        self._legacy_base_indices = ({p.label:i for i,p in enumerate(source.prototypes)} if preserve_base else {})
        self.labels = tuple(labels)
        if not self.labels or len(set(self.labels)) != len(self.labels):
            raise ValueError("A mapping view requires distinct categories.")
        self.categories = [SimpleNamespace(label=label,
                           prototypes=tuple(source.get_descendant_granules(label)))
                           for label in self.labels]
        if any(not cat.prototypes for cat in self.categories):
            raise ValueError("A mapping category has no descendant granules.")
        self.prototypes = [SimpleNamespace(label=cat.label, positive=cat.prototypes[0].positive)
                           for cat in self.categories]
        self._flat = [p for cat in self.categories for p in cat.prototypes]
        self._offsets = np.cumsum([0] + [len(c.prototypes) for c in self.categories])
        self.color_space = source.color_space
        self.reference_domain = source.reference_domain
        self.covering = bool(source.covering and
            {p.label for p in self._flat} == {p.label for p in source.get_all_prototypes()})

    @property
    def tconorm(self):
        return self.source.tconorm

    @property
    def _precomputed(self):
        return self.source._precomputed

    def precompute_pack(self):
        return self.source.precompute_pack()

    def get_prototypes(self):
        return self.prototypes

    def get_all_prototypes(self):
        return self._flat

    def calculate_membership(self, value, input_space="LAB"):
        scores = self.source.calculate_membership_snapshot(value, input_space)["categories"]
        return {label: scores[label] for label in self.labels if scores[label] > 0.0}

    def calculate_membership_for_prototype(self, value, idx_proto, input_space="LAB"):
        label = self.labels[idx_proto]
        if label in self._legacy_base_indices:
            return self.source.calculate_membership_for_prototype(value, self._legacy_base_indices[label], input_space)
        return self.source.calculate_category_membership(value, label, input_space)

    def prepare_category_evaluator(self, idx_proto):
        """Prepare only the requested semantic subgraph for a single map.

        Keep the original child order and aggregation at every node. Shared
        leaves are computed once but contribute through every reference.
        The plan lives only for the current mapping job.
        """
        from Source.fuzzy.FuzzyColor import FuzzyColor
        from Source.fuzzy.GranularFuzzyColor import GranularFuzzyColor
        label = self.labels[idx_proto]
        if label in self._legacy_base_indices:
            base_idx = self._legacy_base_indices[label]
            return lambda value, input_space: self.source.calculate_membership_for_prototype(
                value, base_idx, input_space)
        source = self.source
        order, done = [], set()
        stack = [(label, False)]
        while stack:
            name, expanded = stack.pop()
            if name in done:
                continue
            children = source.get_category_children(name)
            if expanded:
                order.append((name, tuple((kind, source._granule_index[target]
                                          if kind == "granule" else target)
                                         for kind, target in children)))
                done.add(name)
            else:
                stack.append((name, True))
                stack.extend((target, False) for kind, target in reversed(children)
                             if kind == "category" and target not in done)
        if self._precomputed is None:
            self.precompute_pack()
        pack = self._precomputed
        raw = FuzzyColor._raw_membership_for_index
        aggregate = GranularFuzzyColor.aggregate

        def evaluate(value, input_space):
            coords = source._coordinates(value, input_space)
            if not self.reference_domain.contains_coordinates(coords, eps=1e-9):
                return 0.0
            degrees, scores = {}, {}
            def degree(kind, target):
                if kind == "category":
                    return scores[target]
                if target not in degrees:
                    degrees[target] = float(raw(coords, target, pack))
                return degrees[target]
            operator = self.tconorm
            for name, children in order:
                scores[name] = aggregate((degree(kind, target) for kind, target in children), operator)
            return scores[label]

        return evaluate

    def granule_membership(self, value, category, granule, input_space="LAB"):
        from Source.fuzzy.FuzzyColor import FuzzyColor
        coords = self.source._coordinates(value, input_space)
        if not self.reference_domain.contains_coordinates(coords, eps=1e-9):
            return 0.0
        if self._precomputed is None:
            self.precompute_pack()
        label = self.categories[category].prototypes[granule].label
        return FuzzyColor._raw_membership_for_index(coords, self.source._granule_index[label], self._precomputed)

    def winning_pair(self, value, input_space="LAB"):
        snap = self.source.calculate_membership_snapshot(value, input_space)
        scores = [snap["categories"][label] for label in self.labels]
        top = max(scores, default=0.0)
        if top <= 0.0:
            return -1, -1
        q = np.asarray(self.source._coordinates(value, input_space), dtype=float)
        def distance(p):
            delta = p.positive - q
            return float(np.dot(delta, delta))
        category = min((i for i, score in enumerate(scores) if abs(score-top) <= 1e-12),
                       key=lambda i: (min(distance(p) for p in self.categories[i].prototypes), i))
        sites = self.categories[category].prototypes
        values = [snap["granules"][p.label] for p in sites]
        best = max(values)
        local = min((j for j, v in enumerate(values) if abs(v-best) <= 1e-12),
                    key=lambda j: (distance(sites[j]), j))
        return category, int(self._offsets[category] + local)

    def best_prototype_index(self, value, input_space="LAB"):
        return self.winning_pair(value, input_space)[0]

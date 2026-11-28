#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Reproducible PT/AT paper analysis for an ATOMIC PyFCS CIELAB fuzzy space.

Install alongside your code: Source/test/cases/vita_thresholds/threshold_paper_analysis.py
Run from the folder containing Source:

 cd /d C:\Users\rafav\Desktop\PYFCS
 python -m Source.test.cases.vita_thresholds.threshold_paper_analysis

 Default: ALL 16 shades, Core + 0.5-cut, delta = 0.05.
 Uses the supplied VITA Classical MAX CIELAB JSON and writes PDF/PNG/CSV/LaTeX.
 A progress cache resumes completed shade/layer grids automatically.

EXPERIMENT DESIGN
- The existing PyFCS algorithm supplies PT and AT from ONE BFS per prototype.
- A separate uniformly sampled population INSIDE the entire selected fuzzy
  geometry is used to estimate PT/AT fractions and evaluate raw membership.
  Never use the BFS output as the denominator of a volume fraction.
- Main Core limits table is derived from the delta=0.05 PT/AT joint BFS.
- The 0.5-cut is used for membership-versus-deltaE analysis and comparison.
- Output includes numerical CSV, a LaTeX table, provenance and PDF/PNG.
- Completed joint-grid calculations can be resumed without rerunning.
- This tool deliberately REJECTS granular and RGB models in this dental study.

A numerical lattice is not a perceptual resolution in itself. PT=0.8, AT=1.8
are population 50:50 reference thresholds, not per-patient clinical decisions.
"""
from __future__ import annotations
import os
import sys

# Get the path to the directory containing PyFCS
current_dir = os.path.dirname(__file__)
pyfcs_dir = os.path.abspath(os.path.join(current_dir, '..', '..', '..', '..'))

# Add the PyFCS path to sys.path
sys.path.append(pyfcs_dir)

import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Place file in Source/test/cases/vita_thresholds, then imports work regardless of the cwd.
PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib
matplotlib.use("Agg")  # no Tkinter or display needed
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from skimage.color import deltaE_ciede2000

from Source.geometry.GeometryTools import GeometryTools
from Source.geometry.Point import Point
from Source.input_output.Input import Input
from Source.interface.modules.evaluation.ColorEvaluationManager import ColorEvaluationManager

PT = 0.8
AT = 1.8
PALETTE = {"PT": "#258575", "AT_ONLY": "#dc9b32", "OUT": "#b84b56", "INK": "#29384a"}
LAYERS = {"core": "Core", "alpha": "0.5-cut", "support": "Support"}
DEFAULT_SPACE = PROJECT_ROOT / "fuzzy_color_spaces" / "vita_no_covering_max.json"
DEFAULT_OUT = Path(__file__).resolve().parent / "paper_thresholds_vita_max_delta005"
VITA_ORDER = ("A1", "A2", "A3", "A3.5", "A4", "B1", "B2", "B3", "B4",
              "C1", "C2", "C3", "C4", "D2", "D3", "D4")
AXES = ("L", "a", "b")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--space", type=Path, default=DEFAULT_SPACE,
                   help=f"Input CIELAB color-space JSON; default: {DEFAULT_SPACE}")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--layers", nargs="+", choices=LAYERS, default=["core", "alpha"])
    p.add_argument("--step", type=float, default=0.05,
                   help="Single lattice resolution (default: 0.05 CIELAB units)")
    p.add_argument("--samples", type=int, default=8000,
                   help="Number of independent uniform samples INSIDE each shade/layer")
    p.add_argument("--seed", type=int, default=20261121)
    p.add_argument("--shades", nargs="*", default=[], help="Subset of labels; default: all 16")
    p.add_argument("--scatter-shades", nargs="*", default=[],
                   help="Optional shades to plot in scatter; default: all analyzed shades")
    p.add_argument("--high-membership", type=float, default=0.9,
                   help="Definition of high raw membership for one descriptive statistic")
    p.add_argument("--skip-grid", action="store_true", help="Run sampling/figures but skip BFS grid search")
    p.add_argument("--validate-grid", action="store_true",
                   help="Optional exhaustive connectivity audit; can require large resources at step=0.05")
    p.add_argument("--max-grid-nodes", type=int, default=2_000_000)
    p.add_argument("--no-cache", action="store_true", help="Ignore shade/layer grid checkpoints")
    p.add_argument("--core-pt", type=Path, help="Optional earlier Core PT limits CSV")
    p.add_argument("--core-at", type=Path, help="Optional earlier Core AT limits CSV")
    p.add_argument("--alpha-pt", type=Path, help="Optional new 0.5-cut PT limits CSV")
    p.add_argument("--alpha-at", type=Path, help="Optional new 0.5-cut AT limits CSV")
    return p.parse_args(argv)


def canonical_label(label):
    """The GUI uses A3-5 while articles often write A3.5."""
    return str(label).strip().replace("A3-5", "A3.5")


def load_space(path):
    if not path.is_file():
        raise FileNotFoundError(f"Missing color-space file: {path}")
    if path.suffix.lower() not in (".fcs", ".json"):
        raise ValueError("Use a PyFCS .fcs or .json file (not a limits CSV).")
    data, space = Input.instance(path.suffix).read_file(str(path))
    if getattr(space, "color_space", "").upper() != "LAB":
        raise ValueError("This study requires a native LAB geometry. RGB must not be treated as LAB.")
    if not all(hasattr(space, k) for k in ("prototypes", "cores", "supports", "calculate_membership_for_prototype")):
        raise ValueError("This script analyzes atomic shade categories (one prototype per category), not granular models.")
    labels = [canonical_label(p.label) for p in space.prototypes]
    if len(set(labels)) != len(labels):
        raise ValueError("Non-unique canonical shade labels found.")
    return data, space


def volumes_for(space, layer):
    if layer == "core":
        return space.cores
    if layer == "alpha":
        return space.prototypes
    if layer == "support":
        return space.supports
    raise ValueError(layer)


def finite_bounds(volume, domain):
    """Get a safe AABB from polygon vertices; use the reference box if incomplete.

    Only trust stored vertices if ALL faces are finite and have vertices. This
    avoids silently truncating a region with missing/unbounded face geometry.
    """
    faces = volume.getFaces()
    complete = bool(faces) and all(f.getArrayVertex() and not f.isInfinity() for f in faces)
    if complete:
        xyz = np.asarray([[v.x, v.y, v.z] for f in faces for v in f.getArrayVertex()], float)
        lo, hi = xyz.min(axis=0), xyz.max(axis=0)
    else:
        lo = np.asarray(domain.bounds, float).reshape(3, 2)[:, 0]
        hi = np.asarray(domain.bounds, float).reshape(3, 2)[:, 1]
    box = np.asarray(domain.bounds, float).reshape(3, 2)
    lo, hi = np.maximum(lo, box[:, 0]), np.minimum(hi, box[:, 1])
    if not np.all(hi > lo):
        raise ValueError("Empty or degenerate geometric box: verify model geometry.")
    return lo, hi, complete


def inside_mask(volume, xyz):
    """Vectorized counterpart of Volume.isInside(), with exact fallback.

    Rep-on-plane degeneracies use the original geometry engine to maintain
    PyFCS semantics. Numeric tolerance matches GeometryTools.SMALL_NUM.
    """
    xyz = np.asarray(xyz, float).reshape(-1, 3)
    if not volume.getFaces():
        return np.zeros(len(xyz), bool)
    rep = volume.getRepresentative()
    ref = np.array([rep.x, rep.y, rep.z], dtype=float)
    mask = np.ones(len(xyz), bool)
    eps = GeometryTools.SMALL_NUM
    for face in volume.getFaces():
        p = face.getPlane()
        normal = np.array([p.A, p.B, p.C], float)
        side = float(ref @ normal + p.D)
        if abs(side) <= eps:
            return np.array([volume.isInside(Point(*point)) for point in xyz], dtype=bool)
        signed = xyz @ normal + p.D
        # Original uses s_rep * s_xyz < -eps, not s_xyz < -eps.
        mask &= (signed * side >= -eps)
    return mask


def sample_uniform_inside(volume, domain, n, rng):
    """Rejection sample from the axis-aligned bounding box, unbiased IN VOLUME.

    Independent of the BFS and of the membership function; no bias towards PT.
    """
    lo, hi, complete = finite_bounds(volume, domain)
    selected = []
    obtained = 0
    attempted = 0
    max_attempted = max(250_000, n * 1500)
    while obtained < n:
        batch = min(max(4096, (n - obtained) * 5), 40_000)
        q = rng.uniform(lo, hi, size=(batch, 3))
        good = q[inside_mask(volume, q)]
        if len(good):
            good = good[:n - obtained]
            selected.append(good)
            obtained += len(good)
        attempted += batch
        if attempted > max_attempted:
            raise RuntimeError("Uniform rejection sampling is inefficient for this polyhedron. "
                               "Check stored vertices/reference bounds; no biased fallback applied.")
    return np.vstack(selected), {"aabb_from_complete_faces": bool(complete),
                                 "proposals": attempted, "acceptance": n / attempted}


def wilson_interval(k, n, z=1.959963984540054):
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    den = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / den
    spread = z / den * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
    # Floating-point cancellation near k=0 or k=n can otherwise put a
    # Wilson endpoint a few ulps on the wrong side of the observed fraction.
    # That creates a tiny negative error-bar length in Matplotlib.
    return min(p, max(0.0, center - spread)), max(p, min(1.0, center + spread))


def analyse_sample(space, index, layer, n, rng, high_membership):
    group = volumes_for(space, layer)
    q, proposal_meta = sample_uniform_inside(group[index].voronoi_volume,
                                             space.reference_domain, n, rng)
    representative = np.asarray(space.prototypes[index].positive, float)
    distances = np.asarray(deltaE_ciede2000(q, representative.reshape(1, 3)), float)
    # Raw membership for THIS shade, without partition normalization. In the
    # core μ=1 by definition; verify against the PyFCS API on a small subset.
    if layer == "core":
        check = np.linspace(0, len(q) - 1, min(25, len(q)), dtype=int)
        assert all(abs(space.calculate_membership_for_prototype(q[j], index) - 1.0) < 1e-8
                   for j in check), "A sampled core point does not have raw membership 1."
        membership = np.ones(len(q), dtype=float)
    else:
        membership = np.fromiter((space.calculate_membership_for_prototype(x, index)
                                  for x in q), dtype=float, count=len(q))
    if not np.all(np.isfinite(membership)) or np.any((membership < -1e-8) | (membership > 1 + 1e-8)):
        raise ValueError("Invalid raw membership values returned by PyFCS.")
    membership = np.clip(membership, 0, 1)
    pt = distances < PT
    at = distances < AT
    high = membership >= high_membership
    mismatches = high & ~at
    outside = ~at
    out = {
        "shade": canonical_label(space.prototypes[index].label),
        "layer": layer,
        "n": int(n),
        "n_pt": int(pt.sum()), "n_at": int(at.sum()),
        "n_out_at": int(outside.sum()),
        "pt_fraction": float(pt.mean()), "at_fraction": float(at.mean()),
        "out_at_fraction": float(outside.mean()),
        "n_high_mu": int(high.sum()), "n_high_mu_outside_at": int(mismatches.sum()),
        "fraction_high_mu_outside_at_all": float(mismatches.mean()),
        "fraction_outside_at_given_high_mu": float(mismatches.sum() / high.sum()) if high.any() else math.nan,
        "max_de_in_layer": float(distances.max()),
        "max_de_high_mu": float(distances[high].max()) if high.any() else math.nan,
        "min_mu": float(membership.min()), "max_mu": float(membership.max()),
        "aabb_complete": proposal_meta["aabb_from_complete_faces"],
        "proposal_acceptance": proposal_meta["acceptance"],
    }
    for label, cnt in (("pt", out["n_pt"]), ("at", out["n_at"]),
                       ("out_at", out["n_out_at"]),
                       ("high_mu_outside_at_all", out["n_high_mu_outside_at"])):
        low, high_ = wilson_interval(cnt, n)
        out[f"{label}_ci95_low"] = low
        out[f"{label}_ci95_high"] = high_
    dots = pd.DataFrame({"shade": out["shade"], "layer": layer,
                         "L": q[:, 0], "a": q[:, 1], "b": q[:, 2],
                         "deltaE00": distances, "membership_raw": membership,
                         "regime": np.where(pt, "PT", np.where(at, "AT_ONLY", "OUT")),
                         "source": "uniform_volume_sample"})
    return out, dots


def lattice_bounds(seed, volume, domain, step):
    lo, hi, _ = finite_bounds(volume, domain)
    low_i = np.ceil((lo - seed) / step - 1e-9).astype(int)
    high_i = np.floor((hi - seed) / step + 1e-9).astype(int)
    count = high_i - low_i + 1
    if np.any(count <= 0):
        return low_i, high_i, 0
    return low_i, high_i, int(np.prod(count.astype(np.int64)))


def exhaustive_lattice_keys(volume, domain, seed, step, max_nodes):
    """Full enumeration on the SAME seed-anchored lattice used by BFS.

    Rejects too-large grids rather than claiming completeness. Independent of
    BFS because it checks every candidate, including disconnected components.
    """
    low_i, high_i, count = lattice_bounds(seed, volume, domain, step)
    if count > max_nodes:
        raise RuntimeError(f"Full validation requires {count:,} grid nodes; "
                           f"maximum allowed: {max_nodes:,}. Increase --max-grid-nodes if intended.")
    if count == 0:
        return set(), set(), 0
    dims = tuple(int(v) for v in high_i - low_i + 1)
    pt_keys, at_keys = set(), set()
    for start in range(0, count, 100_000):
        flat = np.arange(start, min(count, start + 100_000), dtype=np.int64)
        offsets = np.column_stack(np.unravel_index(flat, dims)) + low_i
        xyz = seed[None, :] + step * offsets
        good = inside_mask(volume, xyz)
        if not good.any():
            continue
        keys = offsets[good]
        xyz = xyz[good]
        de = deltaE_ciede2000(xyz, seed.reshape(1, 3))
        valid = de < AT
        at_keys.update(map(tuple, keys[valid]))
        pt_keys.update(map(tuple, keys[de < PT]))
    return pt_keys, at_keys, count


def search_grid(manager, space, layer, label_indices, step, validate, max_nodes,
                scatter_store=None, scatter_labels=None, scatter_rng=None,
                plot_store=None, cache_dir=None, model_sha=None, use_cache=True):
    """Run the PyFCS paired BFS once per shade/layer with resumable checkpoints.

    The cached arrays are ONLY small plotting subsamples. Limits and counts are
    calculated from the complete visited BFS component, not from those arrays.
    """
    records = []
    if scatter_rng is None:
        scatter_rng = np.random.default_rng(20261121)
    if cache_dir is not None:
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)

    for index in label_indices:
        proto = volumes_for(space, layer)[index]
        label = canonical_label(proto.label)
        seed = np.asarray(space.prototypes[index].positive, float)
        stamp = time.perf_counter()
        cache_file = None
        expected_fingerprint = {
            "cache_version": 2, "model_sha256": model_sha,
            "layer": layer, "shade": label,
            "step": float(step), "PT": PT, "AT": AT,
        }
        cached = False
        if cache_dir is not None:
            cache_file = cache_dir / f"{layer}_{label.replace('.', '_')}_d{step:g}.npz"
        if use_cache and cache_file is not None and cache_file.is_file() and not validate:
            try:
                with np.load(cache_file, allow_pickle=False) as saved:
                    metadata = json.loads(str(saved["metadata"].item()))
                    if metadata == expected_fingerprint:
                        result = json.loads(str(saved["record"].item()))
                        pt_display = np.asarray(saved["pt_display"], float).reshape(-1, 3)
                        at_only_display = np.asarray(saved["at_only_display"], float).reshape(-1, 3)
                        cached = True
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                cached = False

        if not cached:
            both = manager.filter_points_with_thresholds(
                [proto], step=step, metric="CIEDE2000",
                color_space="LAB", pt_threshold=PT, at_threshold=AT
            )
            pt = both["PT"]["points"]["Volume_0"]
            at = both["AT"]["points"]["Volume_0"]
            at_only = both["AT_ONLY"]["points"]["Volume_0"]
            if len(pt) > len(at) or len(pt) + len(at_only) != len(at):
                raise AssertionError("The joint search must satisfy PT ⊆ AT and AT = PT ∪ AT_ONLY")
            result = {
                "shade": label, "layer": layer, "step": float(step),
                "bfs_pt_n": len(pt), "bfs_at_n": len(at),
                "bfs_at_only_n": len(at_only),
                "bfs_seconds": round(time.perf_counter() - stamp, 3),
            }
            for regime, values in (("PT", pt), ("AT", at)):
                xyz = np.asarray(values, float).reshape(-1, 3)
                for j, axis in enumerate(AXES):
                    result[f"{regime}_{axis}_min"] = float(xyz[:, j].min()) if len(xyz) else math.nan
                    result[f"{regime}_{axis}_max"] = float(xyz[:, j].max()) if len(xyz) else math.nan
            if validate:
                expected_pt, expected_at, count = exhaustive_lattice_keys(
                    proto.voronoi_volume, space.reference_domain, seed, step, max_nodes
                )
                result["validation_grid_nodes"] = count
                for regime, expected, points in (("PT", expected_pt, pt), ("AT", expected_at, at)):
                    measured = {tuple(np.rint((np.asarray(x) - seed) / step).astype(int))
                                for x in points}
                    result[f"{regime}_missing_lattice_nodes"] = len(expected - measured)
                    result[f"{regime}_extra_lattice_nodes"] = len(measured - expected)
                    result[f"{regime}_complete"] = expected == measured

            def sample_cloud(pts, max_count=350):
                if not pts:
                    return np.empty((0, 3), dtype=float)
                chosen = scatter_rng.choice(len(pts), min(len(pts), max_count), replace=False)
                return np.asarray([pts[int(j)] for j in chosen], dtype=float).reshape(-1, 3)

            pt_display = sample_cloud(pt)
            at_only_display = sample_cloud(at_only)
            # Free large arrays before analyzing the next shade.
            del both, pt, at, at_only
            if cache_file is not None and not validate:
                tmp = cache_file.with_suffix(".tmp.npz")
                np.savez_compressed(tmp, metadata=json.dumps(expected_fingerprint),
                                    record=json.dumps(result),
                                    pt_display=pt_display,
                                    at_only_display=at_only_display)
                os.replace(tmp, cache_file)

        if plot_store is not None:
            for regime, coords in (("PT", pt_display), ("AT_ONLY", at_only_display)):
                if len(coords):
                    plot_store.append(pd.DataFrame({
                        "shade": label, "layer": layer, "regime": regime,
                        "L": coords[:, 0], "a": coords[:, 1], "b": coords[:, 2],
                    }))

        if (scatter_store is not None and
                label in (scatter_labels or set()) and layer == "alpha"):
            for regime, coords in (("PT", pt_display), ("AT_ONLY", at_only_display)):
                if not len(coords):
                    continue
                de = deltaE_ciede2000(coords, seed.reshape(1, 3))
                mu = np.fromiter((space.calculate_membership_for_prototype(x, index) for x in coords),
                                 dtype=float, count=len(coords))
                scatter_store.append(pd.DataFrame({
                    "shade": label, "layer": layer,
                    "L": coords[:, 0], "a": coords[:, 1], "b": coords[:, 2],
                    "deltaE00": de, "membership_raw": mu, "regime": regime,
                    "source": "threshold_stratified_lattice",
                }))
        records.append(result)
        print(f"  {label:>4s}  {layer:>7s}  δ={step:g}: "
              f"PT={result['bfs_pt_n']:,} AT={result['bfs_at_n']:,}"
              + (" [cached]" if cached else "")
              + (" [grid checked]" if validate else ""), flush=True)
    return records

def mpl_paper_style():
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 9.5, "axes.labelsize": 10.5,
        "axes.titlesize": 12, "axes.spines.top": False,
        "axes.spines.right": False, "axes.linewidth": 0.8,
        "xtick.direction": "out", "ytick.direction": "out",
        "figure.facecolor": "white", "axes.facecolor": "white",
        "pdf.fonttype": 42, "ps.fonttype": 42,
        "savefig.facecolor": "white",
    })


def save_figure(fig, out, stem):
    for fmt in ("pdf", "png"):
        fig.savefig(out / f"{stem}.{fmt}", dpi=350 if fmt == "png" else None,
                    bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)


def figure_membership(scatter, out, max_per_shade=1200):
    """Paper-ready membership versus ΔE figure; data is sampled, NOT synthetic."""
    if scatter.empty:
        return
    rng = np.random.default_rng(0)
    # Compatible with older pandas: no groupby.apply(include_groups=...).
    blocks = []
    for _, group in scatter.groupby("shade", sort=False):
        uniform = group[group.source == "uniform_volume_sample"]
        grid_display = group[group.source == "threshold_stratified_lattice"]
        select = np.sort(rng.choice(len(uniform), min(len(uniform), max_per_shade), replace=False))
        blocks.append(uniform.iloc[select])
        if len(grid_display):
            blocks.append(grid_display)
    frame = pd.concat(blocks, ignore_index=True)
    fig, ax = plt.subplots(figsize=(7.4, 4.8), layout="constrained")
    ax.axvspan(0, PT, color=PALETTE["PT"], alpha=0.09, lw=0)
    ax.axvspan(PT, AT, color=PALETTE["AT_ONLY"], alpha=0.105, lw=0)
    # Show enough of the distribution to make the actual threshold meaningful.
    limit = min(8, max(3.5, float(np.quantile(frame["deltaE00"], 0.96))))
    ax.axvspan(AT, limit, color=PALETTE["OUT"], alpha=0.045, lw=0)
    order = [("OUT", "Outside AT", PALETTE["OUT"]),
             ("AT_ONLY", "AT only", PALETTE["AT_ONLY"]),
             ("PT", "Within PT", PALETTE["PT"])]
    for regime, name, color in order:
        p = frame[frame.regime == regime]
        ax.scatter(p.deltaE00, p.membership_raw, s=8.5, c=color,
                   alpha=0.47, linewidths=0, label=name)
    for threshold, label, color in ((PT, "PT = 0.8", PALETTE["PT"]),
                                    (AT, "AT = 1.8", PALETTE["AT_ONLY"])):
        ax.axvline(threshold, c=color, linewidth=1.3, linestyle="--")
        # Threshold labels are placed once axis limits are known below.
    min_membership = max(0, float(frame.membership_raw.min()) - 0.07)
    min_membership = math.floor(min_membership * 10) / 10
    for threshold, label, color in ((PT, "PT = 0.8", PALETTE["PT"]),
                                    (AT, "AT = 1.8", PALETTE["AT_ONLY"])):
        ax.text(threshold + 0.055, min_membership + 0.02, label,
                rotation=90, color=color, fontsize=8, va="bottom")
    ax.set(xlim=(0, limit), ylim=(min_membership, 1.04),
           xlabel=r"CIEDE2000 difference from reference, $\Delta E_{00}$",
           ylabel=r"Raw fuzzy membership, $\mu_i(q)$")
    ax.set_yticks(np.arange(min_membership, 1.001, 0.1 if min_membership >= 0.3 else 0.2))
    ax.grid(axis="y", color="#a0adb5", alpha=0.24, linewidth=0.6)
    ax.legend(loc="lower right", ncol=1, frameon=False, fontsize=8.6)
    ax.set_title("Fuzzy membership and dental perceptual thresholds", loc="left", pad=12)
    leftout = int((frame.deltaE00 > limit).sum())
    footer = ("Illustrative scatter: uniform whole-volume points and, where present, "
              "threshold-stratified lattice points; marker density is not a frequency estimate.")
    if leftout:
        footer += f" {leftout:,} display points outside x-range."
    fig.text(0.5, -0.045, footer, ha="center", fontsize=7.6, color="#5c6674")
    save_figure(fig, out, "fig_membership_vs_deltaE00")


def figure_fraction(summary, out):
    """Uniform Monte Carlo estimates; never mistakenly label these BFS counts."""
    if summary.empty:
        return
    df = summary.copy()
    # Display one layer at a time, not conflate dissimilar regions.
    for layer in df.layer.unique():
        sub = df[df.layer == layer].reset_index(drop=True)
        x = np.arange(len(sub), dtype=float)
        fig, ax = plt.subplots(figsize=(max(7.6, len(sub) * 0.5), 4.5), layout="constrained")
        w = 0.34
        for value, errprefix, offset, label, color in (
            ("pt_fraction", "pt", -w / 2, "Within PT", PALETTE["PT"]),
            ("at_fraction", "at", w / 2, "Within AT", PALETTE["AT_ONLY"])):
            y = sub[value].to_numpy(float) * 100
            lower = sub[f"{errprefix}_ci95_low"].to_numpy(float) * 100
            upper = sub[f"{errprefix}_ci95_high"].to_numpy(float) * 100
            # The Wilson interval contains the observed proportion mathematically,
            # but subtracting nearly equal floats (especially at 0% or 100%)
            # can produce a negative value of order 1e-15.
            err = np.vstack((np.maximum(0.0, y - lower),
                             np.maximum(0.0, upper - y)))
            ax.bar(x + offset, y, width=w, label=label, color=color, alpha=0.9)
            ax.errorbar(x + offset, y, yerr=err, fmt="none", ecolor=PALETTE["INK"],
                        capsize=2.2, linewidth=0.65, alpha=0.8)
        ax.set_xticks(x, sub.shade, rotation=0)
        ax.set_ylim(bottom=0)
        ax.set_ylabel("Sampled volume fraction (%)")
        ax.set_title(f"Threshold-compliant fractions within {LAYERS[layer]}", loc="left", pad=12)
        ax.legend(frameon=False, ncol=2)
        ax.grid(axis="y", color="#a0adb5", alpha=0.25)
        ax.set_axisbelow(True)
        save_figure(fig, out, f"fig_volume_fraction_{layer}")

def figure_membership_facets(scatter, out, max_per_shade=700):
    """4x4 plot of all sixteen shades: alpha memberships and core μ=1.

    Uniform points and threshold-stratified points are visually sampled;
    this figure must not be used to estimate volume fractions.
    """
    if scatter.empty:
        return
    rng = np.random.default_rng(1208)
    labels = [label for label in VITA_ORDER if label in set(scatter.shade)]
    labels.extend(sorted(set(scatter.shade) - set(labels)))
    ncols = 4
    nrows = int(math.ceil(len(labels) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(12.0, nrows * 2.62),
                             sharex=True, sharey=True, layout="constrained")
    axes = np.atleast_1d(axes).reshape(-1)
    alpha_all = scatter[scatter.layer == "alpha"]
    if not len(alpha_all):
        plt.close(fig)
        return
    xmax = float(min(8.0, max(3.5, np.quantile(alpha_all.deltaE00, 0.97))))
    for ax, label in zip(axes, labels):
        frame = scatter[scatter.shade == label]
        alpha = frame[frame.layer == "alpha"]
        core = frame[(frame.layer == "core") & (frame.source == "uniform_volume_sample")]
        ax.axvspan(0, PT, color=PALETTE["PT"], alpha=0.10, zorder=0)
        ax.axvspan(PT, AT, color=PALETTE["AT_ONLY"], alpha=0.12, zorder=0)
        ax.axvspan(AT, xmax, color=PALETTE["OUT"], alpha=0.05, zorder=0)
        # Avoid a misleading overplot of hundreds of thousands of points.
        for regime, color in (("OUT", PALETTE["OUT"]),
                              ("AT_ONLY", PALETTE["AT_ONLY"]),
                              ("PT", PALETTE["PT"])):
            sub = alpha[alpha.regime == regime]
            uniform = sub[sub.source == "uniform_volume_sample"]
            extra = sub[sub.source == "threshold_stratified_lattice"]
            if len(uniform) > max_per_shade:
                uniform = uniform.iloc[rng.choice(len(uniform), max_per_shade, replace=False)]
            if len(extra) > 100:
                extra = extra.iloc[rng.choice(len(extra), 100, replace=False)]
            shown = pd.concat([uniform, extra], ignore_index=True)
            ax.scatter(shown.deltaE00, shown.membership_raw,
                       s=4.2, color=color, alpha=0.46, linewidths=0, rasterized=True)
        if len(core):
            selected = core
            if len(selected) > 80:
                selected = selected.iloc[rng.choice(len(selected), 80, replace=False)]
            ax.scatter(selected.deltaE00, np.ones(len(selected)), marker="|",
                       color="#202d40", alpha=0.50, s=19,
                       linewidth=0.65, rasterized=True)
        ax.axvline(PT, color=PALETTE["PT"], linestyle="--", linewidth=0.8)
        ax.axvline(AT, color=PALETTE["AT_ONLY"], linestyle="--", linewidth=0.8)
        ax.set_title(label, fontsize=10.2, loc="left", fontweight="bold")
        ax.grid(axis="y", alpha=0.12)
        ax.set_xlim(0, xmax)
        ax.set_ylim(0.47, 1.035)
    for ax in axes[len(labels):]:
        ax.set_visible(False)
    fig.supxlabel(r"Color difference from prototype, $\Delta E_{00}$")
    fig.supylabel(r"Raw fuzzy membership, $\mu_i(q)$")
    fig.suptitle("Membership and perceptual thresholds across VITA Classical shades", fontsize=13)
    fig.text(0.5, -0.018,
             "Colored points: 0.5-cut; dark ticks at membership 1: Core. "
             "Sampling is illustrative, not proportional to the full volumes.",
             fontsize=8, ha="center", color="#5c6674")
    save_figure(fig, out, "fig_membership_all_16_shades")


def figure_core_perceptual_split(summary, out):
    """What fraction of the fully-matching Core meets PT/AT thresholds?"""
    part = summary[summary.layer == "core"].copy()
    if part.empty:
        return
    part["order"] = part.shade.apply(lambda x: VITA_ORDER.index(x) if x in VITA_ORDER else 99)
    part = part.sort_values(["order", "shade"])
    a = part.pt_fraction.to_numpy(float) * 100
    b = (part.at_fraction - part.pt_fraction).to_numpy(float) * 100
    c = (1 - part.at_fraction).to_numpy(float) * 100
    x = np.arange(len(part))
    fig, ax = plt.subplots(figsize=(10.3, 4.6), layout="constrained")
    ax.bar(x, a, color=PALETTE["PT"], label="Within PT")
    ax.bar(x, b, bottom=a, color=PALETTE["AT_ONLY"], label="AT only")
    ax.bar(x, c, bottom=a+b, color=PALETTE["OUT"], label="Outside AT")
    ax.set_xticks(x, part.shade)
    ax.set(xlim=(-0.6, len(part)-0.4), ylim=(0, 100), ylabel="Share of Core volume (%)")
    ax.set_title("Perceptual classification inside fully matching fuzzy cores", loc="left", pad=12)
    ax.grid(axis="y", alpha=0.20)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, ncol=3, bbox_to_anchor=(0, 1.01), loc="lower left")
    fig.text(0.5, -0.018, "Estimated by independent uniform sampling inside each Core; not BFS proportions.",
             fontsize=8, ha="center", color="#5c6674")
    save_figure(fig, out, "fig_core_pt_at_outside")


def figure_3d_regions(cloud, prototypes, layer, out):
    """Side-by-side PT/AT images using a small sample of actual PyFCS grid points."""
    # Explicit import enables the projection with Matplotlib installs where
    # projection auto-registration fails (but mplot3d is still available).
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
    from matplotlib.projections import register_projection
    register_projection(Axes3D)
    if cloud.empty:
        return
    sub = cloud[cloud.layer == layer].copy()
    if sub.empty:
        return
    labels = [x for x in VITA_ORDER if x in set(sub.shade)]
    labels += sorted(set(sub.shade) - set(labels))
    colors = {name: plt.get_cmap("tab20")(i % 20) for i, name in enumerate(labels)}
    fig = plt.figure(figsize=(11.4, 5.0))
    ax_pt = fig.add_subplot(121, projection="3d")
    ax_at = fig.add_subplot(122, projection="3d")
    available = sub[["a", "b", "L"]].to_numpy(float)
    span = np.maximum(np.ptp(available, axis=0), 1e-5)
    pad = np.maximum(span * 0.06, 0.5)
    lower = available.min(axis=0) - pad
    upper = available.max(axis=0) + pad
    for ax, allowed, title in ((ax_pt, {"PT"}, "Perceptibility, PT = 0.8"),
                                (ax_at, {"PT", "AT_ONLY"}, "Acceptability, AT = 1.8")):
        for shade in labels:
            dots = sub[(sub.shade == shade) & sub.regime.isin(allowed)]
            if len(dots):
                ax.scatter(dots.a, dots.b, dots.L, s=2.8, alpha=0.35,
                           color=colors[shade], rasterized=True, depthshade=False)
            if shade in prototypes:
                P = prototypes[shade]
                ax.scatter([P[1]], [P[2]], [P[0]], marker="x", s=20,
                           linewidth=0.8, color=colors[shade], depthshade=False)
        ax.set(xlim=(lower[0], upper[0]), ylim=(lower[1], upper[1]),
               zlim=(lower[2], upper[2]), xlabel=r"$a^*$", ylabel=r"$b^*$", zlabel=r"$L^*$")
        ax.set_title(title, fontsize=10)
        ax.view_init(elev=23, azim=-63)
        ax.set_box_aspect((1, 1, 0.9))
        ax.tick_params(labelsize=7, pad=0)
    from matplotlib.lines import Line2D
    handles = [Line2D([0], [0], color=colors[name], marker="o", linestyle="None",
                      markersize=4.5, label=name) for name in labels]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.01),
               ncol=min(8, len(labels)), fontsize=7.2, frameon=False)
    fig.suptitle(f"VITA Classical — {LAYERS[layer]} threshold-constrained regions", fontsize=12)
    fig.subplots_adjust(left=0.02, right=0.98, bottom=0.14, top=0.91, wspace=0.03)
    save_figure(fig, out, f"fig_3d_regions_{layer}")


def export_core_ranges(grid, out):
    """Export the main manuscript tables from the 0.05-grid Core PT/AT results."""
    core = grid[grid.layer == "core"].copy()
    if core.empty:
        return pd.DataFrame()
    core["order"] = core.shade.apply(lambda x: VITA_ORDER.index(x) if x in VITA_ORDER else 99)
    core = core.sort_values(["order", "shade"])
    columns = ["shade", "step", "bfs_pt_n", "bfs_at_n"]
    for reg in ("PT", "AT"):
        for ax in AXES:
            columns.extend([f"{reg}_{ax}_min", f"{reg}_{ax}_max"])
    result = core[columns].copy()
    result.to_csv(out / "table_core_ranges_PT_AT.csv", index=False, float_format="%.6f")
    grid_step = float(core.step.iloc[0])
    for regime in ("PT", "AT"):
        tex = [
            r"\begin{table}[htbp]",
            r"\centering",
            (r"\caption{CIELAB limits of perceptually admissible regions "
             + ("(perceptibility" if regime == "PT" else "(acceptability")
             + rf" threshold) within the fuzzy cores, computed with $\delta={grid_step:g}$.}}"),
            r"\begin{tabular}{lccc}", r"\toprule",
            r"Shade & $L^*$ (min--max) & $a^*$ (min--max) & $b^*$ (min--max) \\",
            r"\midrule",
        ]
        for _, row in result.iterrows():
            def show(ax):
                lo = row[f"{regime}_{ax}_min"]
                hi = row[f"{regime}_{ax}_max"]
                return f"{lo:.2f}--{hi:.2f}" if np.isfinite(lo) and np.isfinite(hi) else "---"
            tex.append(f"{row.shade} & {show('L')} & {show('a')} & {show('b')} " + r"\\")
        tex += [r"\bottomrule", r"\end{tabular}",
                r"\label{tab:core_limits_" + regime.lower() + "}", r"\end{table}"]
        (out / f"table_core_limits_{regime}.tex").write_text("\n".join(tex)+"\n", encoding="utf-8")
    return result


def figure_convergence(grid, out):
    if grid.empty or grid.step.nunique() < 2:
        return
    for layer in grid.layer.unique():
        subset = grid[grid.layer == layer]
        fig, ax = plt.subplots(figsize=(7.3, 4.4), layout="constrained")
        for shade, sub in subset.groupby("shade", sort=False):
            sub = sub.sort_values("step")
            # Counts scale as 1/delta^3; count*delta^3 is the lattice volume.
            ax.plot(sub.step, sub.bfs_at_n * sub.step ** 3, marker="o", markersize=3.5,
                    linewidth=1.1, label=shade)
        ax.set(xlabel=r"Grid spacing, $\delta$ (CIELAB units)",
               ylabel=r"AT grid-volume proxy, $N_{AT}\delta^3$ (LAB$^3$)")
        ax.set_title(f"Grid convergence – {LAYERS[layer]}", loc="left")
        ax.legend(frameon=False, ncol=4, fontsize=7.5)
        ax.grid(alpha=0.24)
        save_figure(fig, out, f"fig_grid_convergence_{layer}")


def read_limits(path):
    """Read PyFCS's semicolon CSV (even its quote-wrapped interval cells)."""
    result = {}
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            shade = canonical_label(row["Volume"])
            result[shade] = {}
            for axis in ("L*", "a*", "b*"):
                cell = str(row[axis]).strip().strip('"')
                match = re.fullmatch(r"\s*([+-]?\d+(?:\.\d+)?)\s+-\s+([+-]?\d+(?:\.\d+)?)\s*", cell)
                if not match:
                    raise ValueError(f"Unrecognized {axis} interval for {shade}: {cell!r}")
                result[shade][axis] = tuple(map(float, match.groups()))
    return result


def compare_limits(paths, out):
    core_pt, core_at, alpha_pt, alpha_at = [read_limits(p) for p in paths]
    labels = list(core_pt)
    if not (set(core_at) == set(alpha_pt) == set(alpha_at) == set(labels)):
        raise ValueError("The four CSVs must include the same shade names.")
    rows = []
    for shade in labels:
        for axis in ("L*", "a*", "b*"):
            d = {"shade": shade, "axis": axis}
            for layer, threshold, data in (("core", "PT", core_pt), ("core", "AT", core_at),
                                           ("alpha", "PT", alpha_pt), ("alpha", "AT", alpha_at)):
                low, high = data[shade][axis]
                d[f"{layer}_{threshold}_min"] = low
                d[f"{layer}_{threshold}_max"] = high
                d[f"{layer}_{threshold}_width"] = high - low
            rows.append(d)
    df = pd.DataFrame(rows)
    df.to_csv(out / "core_vs_alpha_intervals.csv", index=False, float_format="%.5f")
    # Compact, publication-ready comparison of interval widths, not volumes.
    fig, axes = plt.subplots(1, 3, figsize=(11.5, 4.2), sharey=True, layout="constrained")
    shadenames = labels
    for ax, axis in zip(axes, ("L*", "a*", "b*")):
        d = df[df.axis == axis].set_index("shade").loc[shadenames]
        x = np.arange(len(d))
        ax.plot(x, d.core_AT_width, "o-", lw=1.1, ms=3.3, c="#ac674d", label="Core / AT")
        ax.plot(x, d.alpha_AT_width, "s-", lw=1.1, ms=3.3, c="#d49e3e", label="0.5-cut / AT")
        ax.plot(x, d.core_PT_width, "o--", lw=0.85, ms=3, c="#25656d", label="Core / PT")
        ax.plot(x, d.alpha_PT_width, "s--", lw=0.85, ms=3, c="#4b9b8f", label="0.5-cut / PT")
        ax.set_xticks(x, shadenames, rotation=60, fontsize=7.3)
        ax.set_title(axis)
        ax.grid(axis="y", alpha=0.25)
    axes[0].set_ylabel("CIELAB axis interval width")
    axes[-1].legend(frameon=False, loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=8)
    fig.suptitle("Core versus 0.5-cut: extent of threshold-constrained intervals", fontsize=12)
    save_figure(fig, out, "fig_compare_core_vs_alpha_limits")
    return df


def main(argv=None):
    args = parse_args(argv)
    if args.step <= 0 or not np.isfinite(args.step):
        raise ValueError("--step must be finite and > 0")
    if args.samples <= 0:
        raise ValueError("--samples must be positive")
    if not 0 < args.high_membership <= 1:
        raise ValueError("--high-membership must be in (0,1]")
    if args.space is None or not args.space.is_file():
        raise FileNotFoundError(
            f"Could not find the original PyFCS JSON at:\n  {args.space}\n"
            "Use --space to specify the real file location. A ranges CSV alone is insufficient."
        )
    # Never mix tables/figures from two distinct geometries in one output folder.
    current_sha = hashlib.sha256(args.space.read_bytes()).hexdigest()
    metadata_file = args.out / "analysis_metadata.json"
    if metadata_file.exists():
        existing = json.loads(metadata_file.read_text(encoding="utf-8"))
        old_sha = existing.get("model_sha256")
        if old_sha and old_sha != current_sha:
            raise ValueError(
                "This results folder belongs to a different fuzzy color space. "
                "Choose another --out directory before analyzing the modified geometry."
            )
    args.out.mkdir(parents=True, exist_ok=True)
    mpl_paper_style()
    supplied_csv = [args.core_pt, args.core_at, args.alpha_pt, args.alpha_at]
    if any(supplied_csv):
        if not all(supplied_csv):
            raise ValueError("For optional CSV comparison supply all four paths")
        compare_limits(supplied_csv, args.out)

    _, space = load_space(args.space)
    file_sha = current_sha
    selected = {canonical_label(s) for s in args.shades} if args.shades else None
    index_list = [i for i, p in enumerate(space.prototypes)
                  if selected is None or canonical_label(p.label) in selected]
    if not index_list:
        raise ValueError("No selected VITA Classical shades match the JSON")
    if selected and len(index_list) != len(selected):
        found = {canonical_label(space.prototypes[i].label) for i in index_list}
        raise ValueError(f"Missing shades in model: {sorted(selected - found)}")
    index_list.sort(key=lambda i: (
        VITA_ORDER.index(canonical_label(space.prototypes[i].label))
        if canonical_label(space.prototypes[i].label) in VITA_ORDER else 99,
        canonical_label(space.prototypes[i].label)))
    if not args.shades and len(index_list) != len(VITA_ORDER):
        print(f"Warning: model contains {len(index_list)} categories, expected 16 VITA shades.", flush=True)
    labels = [canonical_label(space.prototypes[i].label) for i in index_list]
    scatter_shades = set(map(canonical_label, args.scatter_shades)) if args.scatter_shades else set(labels)
    if not scatter_shades.intersection(labels):
        raise ValueError("None of the --scatter-shades exist in the model")
    prototypes = {canonical_label(space.prototypes[i].label):
                  np.asarray(space.prototypes[i].positive, float) for i in index_list}
    print(f"Model: {args.space}")
    print(f"Shades: {', '.join(labels)}")
    print(f"Geometry: {', '.join(LAYERS[x] for x in args.layers)}; "
          f"one paired PT/AT search, δ={args.step:g}")
    print(f"Output: {args.out.resolve()}", flush=True)

    # Sampling is independent of the BFS search: its denominators include all
    # positions inside Core or 0.5-cut, including those OUTSIDE AT.
    summary_rows, scatter_frames, grid_rows, cloud_frames = [], [], [], []
    print("\n[1/3] Uniform samples throughout fuzzy geometries", flush=True)
    for layer in dict.fromkeys(args.layers):
        for i in index_list:
            label = canonical_label(space.prototypes[i].label)
            seed = int(hashlib.sha256(f"{args.seed}|{layer}|{label}".encode()).hexdigest()[:15], 16)
            rng = np.random.default_rng(seed)
            t0 = time.perf_counter()
            row, dots = analyse_sample(space, i, layer, args.samples, rng, args.high_membership)
            summary_rows.append(row)
            if label in scatter_shades:
                scatter_frames.append(dots)
            print(f"  {label:>4} {layer:>5}: PT={row['pt_fraction']:.2%}, "
                  f"AT={row['at_fraction']:.2%}, outside AT={row['out_at_fraction']:.2%}, "
                  f"high-mu outside AT={row['n_high_mu_outside_at']}/{row['n_high_mu']} "
                  f"({time.perf_counter()-t0:.1f}s)", flush=True)
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(args.out / "threshold_summary_uniform_sampling.csv",
                   index=False, float_format="%.8g")
    all_dots = pd.concat(scatter_frames, ignore_index=True) if scatter_frames else pd.DataFrame()
    if not all_dots.empty:
        all_dots.to_csv(args.out / "points_membership_deltaE00.csv",
                        index=False, float_format="%.8g")
        figure_membership(all_dots[all_dots.layer == "alpha"], args.out)
        figure_membership_facets(all_dots, args.out)
    figure_fraction(summary, args.out)
    figure_core_perceptual_split(summary, args.out)

    if not args.skip_grid:
        print("\n[2/3] Single paired PT/AT PyFCS BFS at δ=0.05 (or chosen --step)", flush=True)
        manager = ColorEvaluationManager(output_dir=str(args.out))
        checkpoint_dir = args.out / "_completed_grids"
        for layer in dict.fromkeys(args.layers):
            grid_rows.extend(search_grid(
                manager, space, layer, index_list, args.step,
                args.validate_grid, args.max_grid_nodes,
                scatter_store=scatter_frames,
                scatter_labels=scatter_shades,
                scatter_rng=np.random.default_rng(20261121),
                plot_store=cloud_frames,
                cache_dir=checkpoint_dir, model_sha=file_sha,
                use_cache=not args.no_cache,
            ))
            # Persist each complete layer immediately for long runs.
            pd.DataFrame(grid_rows).to_csv(args.out / "threshold_joint_grid_results.csv",
                                           index=False, float_format="%.8g")
        # Add small stratified grid samples to the membership figure without
        # using them as denominators in the volume proportion analysis.
        if scatter_frames:
            all_dots = pd.concat(scatter_frames, ignore_index=True)
            all_dots.to_csv(args.out / "points_membership_deltaE00.csv",
                            index=False, float_format="%.8g")
            figure_membership(all_dots[all_dots.layer == "alpha"], args.out)
            figure_membership_facets(all_dots, args.out)
        grid = pd.DataFrame(grid_rows)
        if "core" in args.layers:
            export_core_ranges(grid, args.out)
        if cloud_frames:
            cloud = pd.concat(cloud_frames, ignore_index=True)
            cloud.to_csv(args.out / "plot_samples_grid_PT_AT.csv", index=False,
                         float_format="%.7g")
            for layer in dict.fromkeys(args.layers):
                figure_3d_regions(cloud, prototypes, layer, args.out)
    else:
        grid = pd.DataFrame()

    print("\n[3/3] Saving provenance", flush=True)
    provenance = {
        "script": "threshold_paper_analysis.py", "version": "2.0.0",
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "model_file": str(args.space.resolve()),
        "model_sha256": file_sha,
        "model_name": space.space_name,
        "native_color_space": space.color_space,
        "non_covering": not space.covering,
        "disjoint": space.disjoint,
        "lambda1": space.lambda1, "lambda2": space.lambda2,
        "prototypes": {k: list(map(float, v)) for k, v in prototypes.items()},
        "shades": labels,
        "layers": list(dict.fromkeys(args.layers)),
        "threshold_operator": "strict <", "PT_00": PT, "AT_00": AT,
        "grid_step": args.step, "grid_enabled": not args.skip_grid,
        "grid_validation": args.validate_grid,
        "sampling": "independent uniform rejection sampling INSIDE each fuzzy polyhedron",
        "samples_per_shade_per_layer": args.samples, "random_seed": args.seed,
        "high_membership_cutoff": args.high_membership,
        "membership_semantics": "raw per-prototype membership from PyFCS",
        "core_ranges": "computed only on Core PT and AT grid points",
        "scatter": "uniform whole-volume and PT/AT-stratified lattice points; illustrative, not prevalence",
        "bfs_limitation": "Only the six-connected component reachable from the seed is guaranteed.",
        "uniform_fractions_limitation": "Monte Carlo estimates, not exact geometric volumes.",
    }
    (args.out / "analysis_metadata.json").write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Completed. Results: {args.out.resolve()}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, FileNotFoundError, RuntimeError, AssertionError) as exc:
        print(f"Analysis failed: {exc}", file=sys.stderr)
        sys.exit(2)

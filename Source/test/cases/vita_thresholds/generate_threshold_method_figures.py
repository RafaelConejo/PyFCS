#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Publication figures PT and AT using the *actual* PyFCS fuzzy geometry.

Install alongside threshold_paper_analysis.py in Source/test/cases/vita_thresholds and run:

    python -m Source.test.cases.vita_thresholds.generate_threshold_method_figures

Input: PYFCS/fuzzy_color_spaces/vita_no_covering_max.json
Output: PYFCS/Source/test/cases/vita_thresholds/paper_thresholds_vita_max_delta005/method_figures/

The figures use the official Input JSON loader, the genuine stored 0.5-cut
Voronoi volumes, and ColorEvaluationManager's single paired PT/AT BFS.
If the primary analysis has already run with the same model SHA and step,
this script REUSES its per-shade caches, without recalculating the BFS.
No approximate membership function, artificial negatives, or new geometry
are created here. Display clouds are stratified SUBSAMPLES of BFS points;
plotting density must not be interpreted as physical volume or prevalence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

from Source.interface.modules.evaluation.ColorEvaluationManager import ColorEvaluationManager
from Source.test.cases.vita_thresholds.threshold_paper_analysis import (
    AT, PT, DEFAULT_OUT, DEFAULT_SPACE, LAYERS, VITA_ORDER,
    canonical_label, load_space, mpl_paper_style, search_grid,
)

# Fixed VITA shade colors, consistent across the two separate figures.
# The palette is for category identification, NOT an RGB conversion from LAB.
SHADE_COLORS = {
    "A1": "#2675AF", "A2": "#88B7DD", "A3": "#E87618", "A3.5": "#F2B15B",
    "A4": "#2E9936", "B1": "#83C875", "B2": "#C93232", "B3": "#ED8280",
    "B4": "#8659AC", "C1": "#BEA0C9", "C2": "#805647", "C3": "#B48B7C",
    "C4": "#C758A9", "D2": "#E5A1C8", "D3": "#686F77", "D4": "#A5AFB6",
}


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--space", type=Path, default=DEFAULT_SPACE,
                   help=f"Real PyFCS model (default: {DEFAULT_SPACE})")
    p.add_argument("--analysis-dir", type=Path, default=DEFAULT_OUT,
                   help="Folder with main-analysis caches; figures will be written below this folder")
    p.add_argument("--out", type=Path, default=None,
                   help="Optional figures-only folder (default: analysis-dir/method_figures)")
    p.add_argument("--layer", choices=("alpha", "core"), default="alpha",
                   help="Geometric region to illustrate (default: alpha = 0.5-cut)")
    p.add_argument("--step", type=float, default=0.05,
                   help="CIELAB lattice spacing (default: 0.05)")
    p.add_argument("--shades", nargs="*", default=[],
                   help="VITA names (default: all 16)")
    p.add_argument("--dpi", type=int, default=400,
                   help="PNG export resolution (default: 400)")
    p.add_argument("--elev", type=float, default=23.0)
    p.add_argument("--azim", type=float, default=-63.0)
    p.add_argument("--no-cache", action="store_true",
                   help="Force genuine PyFCS searches even if cached")
    p.add_argument("--cache-only", action="store_true",
                   help="Do not run expensive searches; require matching cached grids")
    return p.parse_args(argv)


def matching_cached_grids(cache_dir, model_sha, layer, labels, step):
    """Check *all* required cache entries, including their SHA and settings."""
    for shade in labels:
        cache = cache_dir / f"{layer}_{shade.replace('.', '_')}_d{step:g}.npz"
        if not cache.is_file():
            return False, f"Missing cache: {cache}"
        try:
            with np.load(cache, allow_pickle=False) as saved:
                stamp = json.loads(str(saved["metadata"].item()))
                required = {
                    "cache_version": 2, "model_sha256": model_sha,
                    "layer": layer, "shade": shade, "step": float(step),
                    "PT": PT, "AT": AT,
                }
                if stamp != required:
                    return False, f"Different model/step/thresholds: {cache}"
        except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
            return False, f"Invalid cache {cache}: {exc}"
    return True, "All cache entries match the selected model and parameters."


def axis_limits_from_at(cloud, prototypes, labels):
    """The identical plotting limits used for both PT and AT."""
    frames = [cloud[["a", "b", "L"]].to_numpy(dtype=float)] if len(cloud) else []
    frames.extend([np.asarray([prototypes[name][1], prototypes[name][2], prototypes[name][0]], float)[None, :]
                   for name in labels])
    xyz = np.concatenate(frames)
    if not np.all(np.isfinite(xyz)):
        raise ValueError("The search produced non-finite plotting coordinates")
    span = np.maximum(np.ptp(xyz, axis=0), 0.1)
    margin = np.maximum(span * 0.075, [0.6, 0.8, 0.8])
    return xyz.min(axis=0) - margin, xyz.max(axis=0) + margin


def make_figure(cloud, prototypes, labels, layer, regime, limits, out, dpi=400,
                elev=23.0, azim=-63.0):
    """Plot only genuine PyFCS PT points, or the complete PT+AT_ONLY sample.

    PT and AT are output as distinct files using identical axes, colors, and
    camera. The AT panel contains the PT region too; it is NOT just AT_ONLY.
    """
    if regime not in ("PT", "AT"):
        raise ValueError("regime must be PT or AT")
    if dpi < 72:
        raise ValueError("PNG dpi must be >= 72")

    # Registration is explicit for installations with several Matplotlib copies.
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
    from matplotlib.projections import register_projection
    register_projection(Axes3D)

    lower, upper = limits
    mpl_paper_style()
    fig = plt.figure(figsize=(9.2, 7.5), facecolor="white")
    ax = fig.add_axes([0.07, 0.19, 0.87, 0.76], projection="3d")

    allowed = ("PT",) if regime == "PT" else ("PT", "AT_ONLY")
    for shade in labels:
        selected = cloud[(cloud.shade == shade) & cloud.regime.isin(allowed)]
        color = SHADE_COLORS[shade]
        if not selected.empty:
            ax.scatter(selected.a.to_numpy(float), selected.b.to_numpy(float),
                       selected.L.to_numpy(float), color=color, s=5.0,
                       alpha=0.52, rasterized=True, depthshade=False,
                       linewidth=0, zorder=2)
        prototype = prototypes[shade]
        ax.scatter([prototype[1]], [prototype[2]], [prototype[0]],
                   marker="X", s=43, color=color, edgecolor="#293343",
                   linewidth=0.6, depthshade=False, zorder=5)

    ax.set_xlim(float(lower[0]), float(upper[0]))
    ax.set_ylim(float(lower[1]), float(upper[1]))
    ax.set_zlim(float(lower[2]), float(upper[2]))
    ax.set_xlabel(r"$a^*$", labelpad=10, fontsize=12)
    ax.set_ylabel(r"$b^*$", labelpad=10, fontsize=12)
    ax.set_zlabel(r"$L^*$", labelpad=9, fontsize=12)
    ax.tick_params(labelsize=9, pad=1)
    ax.view_init(elev=elev, azim=azim)
    ax.set_box_aspect((1.0, 1.45, 1.15), zoom=0.95)
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.pane.fill = False
        axis.line.set_color("#929daa")
        axis._axinfo["grid"]["color"] = (0.65, 0.69, 0.75, 0.25)
        axis._axinfo["grid"]["linewidth"] = 0.45

    title = (r"Perceptibility ($PT_{00} = 0.8$)" if regime == "PT"
             else r"Acceptability ($AT_{00} = 1.8$)")
    ax.set_title(title, fontsize=14, pad=12)
    handles = [Line2D([], [], color=SHADE_COLORS[name], marker="o", linestyle="",
                      markersize=6.3, label=name) for name in labels]
    fig.legend(handles, labels, loc="lower center", ncol=min(8, len(labels)),
               bbox_to_anchor=(0.5, 0.052), columnspacing=1.6,
               handletextpad=0.5, frameon=False, fontsize=10)

    out.mkdir(parents=True, exist_ok=True)
    stem = f"fig_method_{layer}_{regime}"
    paths = [out / f"{stem}.png", out / f"{stem}.pdf"]
    fig.savefig(paths[0], dpi=dpi, bbox_inches="tight", pad_inches=0.10,
                facecolor="white")
    fig.savefig(paths[1], bbox_inches="tight", pad_inches=0.10,
                facecolor="white")
    plt.close(fig)
    return paths


def main(argv=None):
    args = parse_args(argv)
    args.space = args.space.resolve()
    args.analysis_dir = args.analysis_dir.resolve()
    out = (args.out if args.out is not None else args.analysis_dir / "method_figures").resolve()
    if not args.space.is_file():
        raise FileNotFoundError(f"Could not find the PyFCS color space: {args.space}")
    if not np.isfinite(args.step) or args.step <= 0:
        raise ValueError("--step must be a positive finite number")
    if args.cache_only and args.no_cache:
        raise ValueError("--cache-only and --no-cache are mutually exclusive")
    if args.dpi < 72:
        raise ValueError("--dpi must be at least 72")
    file_sha = hashlib.sha256(args.space.read_bytes()).hexdigest()

    # Prevent figures from silently being mixed with a different-model analysis.
    metadata_path = args.analysis_dir / "analysis_metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        old_sha = metadata.get("model_sha256")
        if old_sha and old_sha != file_sha:
            raise ValueError("Existing analysis folder uses a different JSON geometry. "
                             "Choose another --analysis-dir or rerun the main analysis.")

    _, space = load_space(args.space)
    all_labels = [canonical_label(p.label) for p in space.prototypes]
    if len(all_labels) != 16 or set(all_labels) != set(VITA_ORDER):
        raise ValueError("The model must have exactly the 16 VITA Classical shades")
    chosen = {canonical_label(name) for name in args.shades} if args.shades else set(VITA_ORDER)
    if not chosen.issubset(set(VITA_ORDER)):
        raise ValueError(f"Unknown VITA shade labels: {sorted(chosen - set(VITA_ORDER))}")
    indices = [i for i, p in enumerate(space.prototypes) if canonical_label(p.label) in chosen]
    indices.sort(key=lambda i: VITA_ORDER.index(canonical_label(space.prototypes[i].label)))
    labels = [canonical_label(space.prototypes[i].label) for i in indices]
    prototypes = {name: np.asarray(space.prototypes[index].positive, float)
                  for name, index in zip(labels, indices)}
    cache_dir = args.analysis_dir / "_completed_grids"
    matched, detail = matching_cached_grids(cache_dir, file_sha, args.layer, labels, args.step)
    if args.cache_only and not matched:
        raise FileNotFoundError(detail + "\nRun threshold_paper_analysis.py first, or omit --cache-only")

    print("Model:", args.space, "\nSHA-256:", file_sha)
    print("Layer:", LAYERS[args.layer], "\nShades:", ", ".join(labels),
          "\nGrid step:", args.step, "\nCache:", detail,
          "\nFigures folder:", out, flush=True)
    if not matched:
        print("Missing matching caches: starting actual PyFCS joint PT/AT BFS. ",
              "This can be computationally expensive at 0.05.", flush=True)

    manager = ColorEvaluationManager(output_dir=str(args.analysis_dir))
    clouds = []
    records = search_grid(manager, space, args.layer, indices, args.step,
                          validate=False, max_nodes=2_000_000,
                          plot_store=clouds, cache_dir=cache_dir,
                          model_sha=file_sha, use_cache=not args.no_cache)
    if not clouds:
        raise RuntimeError("No threshold-admissible PyFCS points were returned")
    cloud = pd.concat(clouds, ignore_index=True)
    if any(x not in ("PT", "AT_ONLY") for x in cloud.regime.unique()):
        raise AssertionError("Expected disjoint PT and AT_ONLY plotting samples")

    limits = axis_limits_from_at(cloud, prototypes, labels)
    outputs = {}
    for threshold in ("PT", "AT"):
        paths = make_figure(cloud, prototypes, labels, args.layer,
                            threshold, limits, out, args.dpi, args.elev, args.azim)
        outputs[threshold] = [str(path) for path in paths]
        print(f"{threshold}: {paths[0].name}, {paths[1].name}", flush=True)

    out.mkdir(parents=True, exist_ok=True)
    (out / "method_figures_metadata.json").write_text(json.dumps({
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "model_file": str(args.space), "model_sha256": file_sha,
        "layer": args.layer, "shade_labels": labels,
        "PT_00": PT, "AT_00": AT, "step": args.step,
        "axes_order": ["a*", "b*", "L*"],
        "limits": {"a": [float(limits[0][0]), float(limits[1][0])],
                   "b": [float(limits[0][1]), float(limits[1][1])],
                   "L": [float(limits[0][2]), float(limits[1][2])]},
        "visualization": "actual PyFCS joint PT/AT BFS, cached display subsamples",
        "display_sampling": "small independent stratified PT and AT-only subsamples per shade; NOT representative of volumetric proportions",
        "camera_elev": args.elev, "camera_azim": args.azim,
        "outputs": outputs,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Done. Both figures use identical CIELAB axes and camera.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

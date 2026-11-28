#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Publication figures for VITA Classical PT/AT in *actual* PyFCS geometry.

Place in Source/test/cases/vita_thresholds/generate_results_figures.py and execute, with no flags:
    python -m Source.test.cases.vita_thresholds.generate_results_figures

Outputs PNG ONLY, under
    Source/test/cases/vita_thresholds/paper_thresholds_vita_max_delta005/results_figures/

Crucial: the 3D camera follows PyFCS VisualManager.plot_more_combined_3D:
    scene.camera.eye=(1.55,1.65,1.18), up=(0,0,1), orthographic,
    axis mapping x=a*, y=b*, z=L* (never swap the LAB data).
Matplotlib uses the equivalent elev≈27.5°, azim≈46.8° with orthographic
projection. The enlarged publishing frame keeps chromatic axes relatively
broad to reproduce PyFCS's vertical-looking arrangement of the shades;
all geometry comparison figures use the SAME axis limits.

Geometric surfaces are reconstructed using PyFCS's own
VisualManager.display_polygons_for_volume, not the JSON's unprocessed face
vertices. PT/AT display points are pulled from SHA-verified paired-BFS caches:
these are display subsamples, not all enumerated lattice points.

Publication figures:
    1. All 16 shades, PT vs AT: elegant categorical palette.
    2. All 16 shade volumes, Core vs 0.5-cut: tooth-derived LAB volumes,
       with subtle, non-emphasized reference points in Figure 1 colors.
    3. A3/B2/C3/D4 within 0.5-cut, PT vs AT: dental-tone translucent
       polyhedra, fixed blue PT / orange AT-only, shade labels only.
No PDF. No BFS recalculation. Same camera and same axis limits in each pair.

Requires: the original PyFCS source, numpy, matplotlib, scikit-image.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from datetime import datetime, timezone
import csv

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgba
from matplotlib.lines import Line2D
from mpl_toolkits.mplot3d import proj3d
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
from matplotlib.projections import register_projection
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
from skimage.color import lab2rgb
from scipy.spatial import ConvexHull

register_projection(Axes3D)

from Source.input_output.Input import Input
from Source.interface.modules.visualization.VisualManager import VisualManager

PT, AT, DEFAULT_STEP = 0.8, 1.8, 0.05
SHADE_ORDER = ("A1", "A2", "A3", "A3.5", "A4", "B1", "B2", "B3", "B4",
               "C1", "C2", "C3", "C4", "D2", "D3", "D4")
FOUR_SHADES = ("A3", "B2", "C3", "D4")
# Publication palette: 16 deliberate, moderately saturated hues.
# Used to distinguish categories in Figure 1 and subtly indicate
# their prototypes in Figure 2. Volume colors remain dental.
DISTINCT = {
    "A1": "#43C7B4",   # turquoise
    "A2": "#3F9CB9",   # sea blue
    "A3": "#5FB64B",   # leaf green
    "A3.5": "#A13E37", # oxblood red
    "A4": "#8943C7",   # orchid violet
    "B1": "#3C434A",   # charcoal
    "B2": "#C78C43",   # burnished copper
    "B3": "#7A345A",   # deep plum
    "B4": "#C7BE43",   # warm citron
    "C1": "#3863A3",   # cobalt blue
    "C2": "#2D7A6F",   # evergreen teal
    "C3": "#C761A1",   # berry rose
    "C4": "#C7837C",   # rose clay
    "D2": "#7A5D37",   # walnut
    "D3": "#677A2D",   # moss olive
    "D4": "#818BC7",   # periwinkle
}

# Threshold colors are always the SAME regardless of which dental shade is
# plotted. CIELAB dental colors are used separately for the fuzzy volumes.
PT_COLOR = "#2468B4"  # cobalt blue
AT_ONLY_COLOR = "#DB792D"  # warm amber-orange
PROTOTYPE_COLOR = "#1E252A"  # neutral charcoal/near-black

MODEL_DEFAULT = PROJECT_ROOT / "fuzzy_color_spaces" / "vita_no_covering_max.json"
ANALYSIS_DEFAULT = Path(__file__).resolve().parent / "paper_thresholds_vita_max_delta005"

# PyFCS uses the following Plotly camera. Convert the eye vector to spherical
# Matplotlib elevation and azimuth, rather than guessing negative azimuths.
CAMERA_EYE = np.array([1.55, 1.65, 1.18], dtype=float)
ELEV = math.degrees(math.atan2(CAMERA_EYE[2], np.linalg.norm(CAMERA_EYE[:2])))
AZIM = math.degrees(math.atan2(CAMERA_EYE[1], CAMERA_EYE[0]))

INK = "#27333c"
FACE_BEIGE = "#c0b39b"
AXES_ZOOM = 1.20  # increase panel occupancy; does NOT change data coordinates
EDGE_BEIGE = "#766c5c"


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--space", type=Path, default=MODEL_DEFAULT)
    p.add_argument("--analysis-dir", type=Path, default=ANALYSIS_DEFAULT)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument("--step", type=float, default=DEFAULT_STEP)
    p.add_argument("--view", choices=("zoom", "full"), default="zoom",
                   help="zoom = publication framing, full = exact PyFCS LAB domain")
    p.add_argument("--zoom-factor", type=float, default=AXES_ZOOM,
                   help="Factor de ocupación visual del gráfico (por defecto 1.20)")
    p.add_argument("--include-alt-geometry", action="store_true",
                   help="Genera también una geometría alternativa con la paleta categórica")
    return p.parse_args(argv)


def canon(name):
    return str(name).replace("A3-5", "A3.5").strip()


def load_model(path):
    if not path.is_file():
        raise FileNotFoundError(f"No se encuentra el JSON: {path}")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    _, space = Input.instance(".json").read_file(str(path))
    if getattr(space, "color_space", "").upper() != "LAB":
        raise ValueError("El modelo debe utilizar CIELAB nativo")
    groups = {
        "core": {canon(p.label):p for p in space.cores},
        "alpha": {canon(p.label):p for p in space.prototypes},
    }
    for layer in groups:
        if set(groups[layer]) != set(SHADE_ORDER):
            raise ValueError(f"El modelo no contiene los 16 tonos en {layer}")
    proto = {shade:np.asarray(groups["alpha"][shade].positive, float) for shade in SHADE_ORDER}
    return space, sha, groups, proto


def actual_vita_palette(prototypes):
    """Approximate displayed sRGB shade colors from source VITA CIELAB.

    These are screen-display colors, NOT a colorimetrically calibrated dental
    shade guide. Original LAB values are not changed in the analysis.
    """
    from matplotlib.colors import to_hex
    result = {}
    for shade,lab in prototypes.items():
        rgb = lab2rgb(np.asarray(lab, float).reshape(1,1,3)).reshape(3)
        result[shade] = to_hex(np.clip(rgb,0,1))
    return result


def geometry_faces(space, groups):
    """Render exactly as PyFCS: clip halfspace representation to LAB domain."""
    result = {}
    for layer in ("core", "alpha"):
        result[layer] = {}
        for shade,p in groups[layer].items():
            polys = VisualManager.display_polygons_for_volume(
                p.voronoi_volume, space.reference_domain, include_domain_caps=True)
            result[layer][shade] = [np.asarray(q, dtype=float).reshape(-1,3)
                                    for q in polys if len(q)>=3]
            if not result[layer][shade] or not all(np.isfinite(q).all() for q in result[layer][shade]):
                raise ValueError(f"Geometría visible inválida: {shade} ({layer})")
    return result


def load_bfs_caches(args, model_sha):
    metadata_path = args.analysis_dir / "analysis_metadata.json"
    if not metadata_path.is_file():
        raise FileNotFoundError(f"Faltan metadatos del análisis: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("model_sha256") != model_sha:
        raise ValueError("El espacio JSON es diferente del usado para calcular PT/AT (SHA256)")
    if float(metadata.get("grid_step", -1)) != args.step:
        raise ValueError("El paso delta de las cachés es diferente del solicitado")
    if (float(metadata.get("PT_00", -1)) != PT or
        float(metadata.get("AT_00", -1)) != AT):
        raise ValueError("Los umbrales registrados en el análisis son diferentes")
    cache_root = args.analysis_dir / "_completed_grids"
    clouds = {"core": {}, "alpha": {}}
    for layer in clouds:
        for shade in SHADE_ORDER:
            path = cache_root / f"{layer}_{shade.replace('.', '_')}_d{args.step:g}.npz"
            if not path.is_file():
                raise FileNotFoundError(f"Falta la caché calculada: {path}")
            with np.load(path, allow_pickle=False) as cache:
                info = json.loads(str(cache["metadata"].item()))
                expected = {
                    "cache_version": 2, "model_sha256": model_sha,
                    "layer": layer, "shade": shade, "step": float(args.step),
                    "PT": PT, "AT": AT,
                }
                if info != expected:
                    raise ValueError(f"Caché incompatible con el análisis: {path}")
                cloud = {
                    "PT": np.asarray(cache["pt_display"], float).reshape(-1,3).copy(),
                    "AT_ONLY": np.asarray(cache["at_only_display"], float).reshape(-1,3).copy(),
                }
                if not all(np.isfinite(x).all() for x in cloud.values()):
                    raise ValueError(f"Datos numéricos inválidos en {path}")
                clouds[layer][shade] = cloud
    return clouds


def bounds_lab(arrays, minimum_spans, padding=1.10):
    """Bounds in plotting [a,b,L] order; never swap CIELAB data."""
    data = np.vstack([np.asarray(v,float).reshape(-1,3) for v in arrays if len(v)])[:,[1,2,0]]
    lo, hi = data.min(axis=0),data.max(axis=0)
    ctr = (lo+hi)/2
    span = np.maximum((hi-lo)*padding, np.asarray(minimum_spans,float))
    return ctr-span/2, ctr+span/2


def geometry_bounds(faces, frame):
    if frame=="full":
        return np.array([-128.,-128.,0.]),np.array([128.,128.,100.])
    return bounds_lab([p for layer in ("core","alpha") for shade in SHADE_ORDER
                       for p in faces[layer][shade]],
                      minimum_spans=(60,76,62),padding=1.06)


def ptat_bounds(clouds,prototypes,frame):
    if frame=="full":
        return np.array([-128.,-128.,0.]),np.array([128.,128.,100.])
    arrays=[np.asarray(list(prototypes.values()))]
    for shade in SHADE_ORDER:
        arrays.extend([clouds["alpha"][shade]["PT"],
                       clouds["alpha"][shade]["AT_ONLY"]])
    return bounds_lab(arrays, minimum_spans=(16,30,24),padding=1.10)


def axes_setup(ax,bounds,*,labels=True):
    lo,hi=bounds
    ax.set_xlim(float(lo[0]),float(hi[0]))
    ax.set_ylim(float(lo[1]),float(hi[1]))
    ax.set_zlim(float(lo[2]),float(hi[2]))
    ax.view_init(elev=ELEV,azim=AZIM)
    ax.set_proj_type("ortho")
    ax.set_box_aspect((1,1,1),zoom=AXES_ZOOM)
    if labels:
        ax.set_xlabel(r"$a^*$",labelpad=6)
        ax.set_ylabel(r"$b^*$",labelpad=6)
        # Mantener L* legible y verticalmente situada junto al eje,
        # pero sin la rotación automática de las etiquetas 3D.
        ax.set_zlabel("")
        ax.text2D(-0.137, .52, r"$L^*$", transform=ax.transAxes,
                  rotation=0, ha="center", va="center", fontsize=11,
                  color=INK, clip_on=False)
    ax.tick_params(labelsize=8,pad=0)
    ax.grid(True)
    for dim in (ax.xaxis,ax.yaxis,ax.zaxis):
        dim._axinfo["grid"].update({"linewidth":.45,"color":(0.71,0.74,0.79,.27)})
        dim.pane.set_facecolor((.973,.979,.99,.25))
        dim.pane.set_edgecolor((.85,.87,.90,.33))


def add_volume_mesh(ax, faces, shade_names, color_map, *, alpha):
    # Single face-sorted collection (same approach as PyFCS Matplotlib GUI).
    all_faces,face_colors,edge_colors=[],[],[]
    for shade in shade_names:
        col = color_map[shade]
        for face in faces[shade]:
            all_faces.append(face[:,[1,2,0]])
            face_colors.append(to_rgba(col,alpha))
            edge_colors.append(to_rgba("#6F6453", .38 if alpha >= .20 else .31))
    if all_faces:
        ax.add_collection3d(Poly3DCollection(
            all_faces,facecolors=face_colors,edgecolors=edge_colors,
            linewidths=.33,zsort="average"))


def add_prototypes(ax, prototypes, shades, color_map=None, size=34, *,
                   constant_color=None):
    """Reference markers: use supplied palette, or a constant when requested."""
    pts = np.vstack([prototypes[shade] for shade in shades])
    colors = ([constant_color] * len(shades) if constant_color is not None
              else [color_map[shade] for shade in shades])
    ax.scatter(pts[:, 1], pts[:, 2], pts[:, 0],
               c=colors, s=size, edgecolors="#F7F7F5", linewidths=.65,
               depthshade=False, zorder=12)



def add_prototypes_subtle(ax, prototypes, shades, color_map, marker_size=3.6):
    """Very small category-color dots; no outline or white halo.

    Project only the original LAB coordinates to keep the dots legible behind
    translucent polyhedra, without changing their positions or the camera.
    """
    coords = np.vstack([prototypes[shade] for shade in shades])
    xx, yy, _ = proj3d.proj_transform(
        coords[:, 1], coords[:, 2], coords[:, 0], ax.get_proj())
    for shade, xp, yp in zip(shades, xx, yy):
        dot = Line2D([xp], [yp], linestyle="None", marker="o",
                     markerfacecolor=color_map[shade],
                     markeredgecolor="none", alpha=0.84,
                     markersize=marker_size, transform=ax.transData,
                     zorder=100, clip_on=True)
        ax.add_artist(dot)


def label_selected_prototypes(ax, prototypes, shades):
    """Identify selected dental shades next to each original LAB prototype.
    Markers are not displayed in Figure 3, avoiding extra visual emphasis.
    """
    for shade in shades:
        L, a, b = prototypes[shade]
        ax.text(a + .28, b + .26, L + .30, shade,
                color=PROTOTYPE_COLOR, fontsize=8.8, fontweight="bold",
                ha="left", va="center", zorder=40)


def shade_handles(shades,color_map,size=6.1):
    return [Line2D([0],[0],marker="o",linestyle="None",color="none",
                   markerfacecolor=color_map[shade],markeredgecolor="#444a50",
                   markeredgewidth=.40,markersize=size,label=shade)
            for shade in shades]


def add_threshold_clouds(ax,clouds,shades,palette,*,kind,layer="alpha",size=9):
    for shade in shades:
        pt=clouds[layer][shade]["PT"]
        at=clouds[layer][shade]["AT_ONLY"]
        pts=pt if kind=="PT" else np.vstack((pt,at))
        if len(pts):
            ax.scatter(pts[:,1],pts[:,2],pts[:,0],
                       s=size,c=palette[shade],alpha=.65 if kind=="PT" else .43,
                       depthshade=False,linewidths=0,rasterized=True)


def save(fig,path,dpi):
    path.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(path,dpi=dpi,bbox_inches="tight",pad_inches=.09,
                facecolor="white")
    plt.close(fig)
    print("  [OK]",path.relative_to(path.parents[2]),flush=True)
    return str(path)


def global_volume_one(layer, palette_name, palette, faces,prototypes,bounds,out,dpi):
    fig=plt.figure(figsize=(8.7,7.3),facecolor="white")
    ax=fig.add_subplot(111,projection="3d")
    add_volume_mesh(ax,faces[layer],SHADE_ORDER,palette,
                    alpha=.41 if layer=="core" else .30)
    # Figura 2: geometría en tonos dentales; prototipos con la paleta de Figura 1.
    axes_setup(ax,bounds)
    add_prototypes_subtle(ax,prototypes,SHADE_ORDER,DISTINCT,marker_size=3.6)
    ax.set_title(("Core" if layer=="core" else "0.5-cut")+" — VITA Classical",fontsize=13,pad=10)
    # Figura 2: leyenda por tono, usando los colores de sus prototipos.
    fig.legend(handles=shade_handles(SHADE_ORDER,DISTINCT),
               ncol=8,loc="lower center",bbox_to_anchor=(.5,.015),
               frameon=False,fontsize=8.8,columnspacing=1.4,handletextpad=.3)
    fig.subplots_adjust(left=.05,right=.96,bottom=.13,top=.92)
    return save(fig,out/"global"/f"fig_global_{layer}_{palette_name}.png",dpi)


def global_volume_pair(palette_name,palette,faces,prototypes,bounds,out,dpi):
    fig=plt.figure(figsize=(14.3,7.2),facecolor="white")
    for idx,layer in enumerate(("core","alpha"),1):
        ax=fig.add_subplot(1,2,idx,projection="3d")
        add_volume_mesh(ax,faces[layer],SHADE_ORDER,palette,
                        alpha=.41 if layer=="core" else .30)
        # Misma paleta categórica que los puntos de Figura 1, sin tocar el volumen.
        axes_setup(ax,bounds)
        add_prototypes_subtle(ax,prototypes,SHADE_ORDER,DISTINCT,marker_size=3.6)
        ax.set_title("(a) Core" if layer=="core" else "(b) 0.5-cut",fontsize=12,pad=8)
    # Figura 2: leyenda por tono, usando los colores de sus prototipos.
    fig.legend(handles=shade_handles(SHADE_ORDER,DISTINCT),
               ncol=8,loc="lower center",bbox_to_anchor=(.5,.02),
               frameon=False,fontsize=8.5,columnspacing=1.4,handletextpad=.3)
    fig.subplots_adjust(left=.025,right=.975,bottom=.14,top=.94,wspace=.04)
    return save(fig,out/"global"/f"fig_global_core_vs_alpha_{palette_name}.png",dpi)


def global_pt_at(clouds,prototypes,bounds,out,dpi):
    fig=plt.figure(figsize=(14.3,7.2),facecolor="white")
    for idx,kind in enumerate(("PT","AT"),1):
        ax=fig.add_subplot(1,2,idx,projection="3d")
        add_threshold_clouds(ax,clouds,SHADE_ORDER,DISTINCT,kind=kind,layer="alpha",size=6.3)
        add_prototypes(ax,prototypes,SHADE_ORDER,DISTINCT,size=26)
        axes_setup(ax,bounds)
        ax.set_title((r"(a) Perceptibility ($PT_{00}=0.8$)" if kind=="PT"
                      else r"(b) Acceptability ($AT_{00}=1.8$)"),fontsize=12,pad=10)
    fig.legend(handles=shade_handles(SHADE_ORDER,DISTINCT),
               ncol=8,loc="lower center",bbox_to_anchor=(.5,.02),
               frameon=False,fontsize=8.8,columnspacing=1.4,handletextpad=.3)
    fig.subplots_adjust(left=.025,right=.975,bottom=.15,top=.94,wspace=.035)
    return save(fig,out/"global"/"fig_global_alpha_PT_AT_vertical.png",dpi)


def selected_bounds(faces,frame):
    if frame=="full":
        return np.array([-128.,-128.,0.]),np.array([128.,128.,100.])
    return bounds_lab([p for shade in FOUR_SHADES for p in faces["alpha"][shade]],
                      minimum_spans=(49,31,28),padding=1.09)


def selected_clouds(ax, clouds, kind, size=11):
    """Fixed criterion colors; AT includes the PT subset plus the AT-only shell.

    These are SHA-verified *display subsamples* from the existing joint BFS.
    """
    for shade in FOUR_SHADES:
        pt = clouds["alpha"][shade]["PT"]
        at_only = clouds["alpha"][shade]["AT_ONLY"]
        if kind == "AT" and len(at_only):
            ax.scatter(at_only[:, 1], at_only[:, 2], at_only[:, 0],
                       s=size, color=AT_ONLY_COLOR, alpha=.78,
                       depthshade=False, linewidths=0, rasterized=True)
        if len(pt):
            ax.scatter(pt[:, 1], pt[:, 2], pt[:, 0],
                       s=size * .85, color=PT_COLOR, alpha=.94,
                       depthshade=False, linewidths=0, rasterized=True)


def selected_legend_handles(vita):
    """Tooth-tone volumes and fixed PT/AT colors; shades are text-labeled."""
    return [
        Line2D([0],[0],marker="s",linestyle="None",color="none",
               markerfacecolor=vita[shade],markeredgecolor="#776956",
               markeredgewidth=.6,markersize=8,label=shade+" volume")
        for shade in FOUR_SHADES
    ] + [
        Line2D([0],[0],marker="o",linestyle="None",color="none",
               markerfacecolor=PT_COLOR,markersize=6,label=r"PT ($\Delta E_{00}<0.8$)"),
        Line2D([0],[0],marker="o",linestyle="None",color="none",
               markerfacecolor=AT_ONLY_COLOR,markersize=6,
               label=r"AT only ($0.8\leq\Delta E_{00}<1.8$)"),
    ]


def selected_threshold_one(faces,prototypes,clouds,vita,kind,bounds,out,dpi):
    """One 3D graph with all four dental-color volumes and either PT or AT."""
    fig=plt.figure(figsize=(8.7,7.3),facecolor="white")
    ax=fig.add_subplot(111,projection="3d")
    add_volume_mesh(ax,faces["alpha"],FOUR_SHADES,vita,alpha=.27)
    selected_clouds(ax,clouds,kind,size=10)
    label_selected_prototypes(ax,prototypes,FOUR_SHADES)
    axes_setup(ax,bounds)
    ax.set_title((", ".join(FOUR_SHADES) + " — 0.5-cut / " + kind),fontsize=13,pad=10)
    fig.legend(handles=selected_legend_handles(vita),ncol=4,loc="lower center",
               bbox_to_anchor=(.5,.019),frameon=False,fontsize=8.6,
               columnspacing=1.15,handletextpad=.35)
    fig.subplots_adjust(left=.05,right=.96,bottom=.16,top=.92)
    return save(fig,out/"selected"/f"fig_selected4_alpha_{kind}_vertical.png",dpi)


def selected_threshold_pair(faces,prototypes,clouds,vita,bounds,out,dpi):
    fig=plt.figure(figsize=(14.3,7.2),facecolor="white")
    for idx,kind in enumerate(("PT","AT"),1):
        ax=fig.add_subplot(1,2,idx,projection="3d")
        add_volume_mesh(ax,faces["alpha"],FOUR_SHADES,vita,alpha=.27)
        selected_clouds(ax,clouds,kind,size=8.3)
        label_selected_prototypes(ax,prototypes,FOUR_SHADES)
        axes_setup(ax,bounds)
        ax.set_title("(a) PT (0.8)" if kind=="PT" else "(b) AT (1.8)",fontsize=12,pad=10)
    fig.legend(handles=selected_legend_handles(vita),ncol=7,
               loc="lower center",bbox_to_anchor=(.5,.02),
               frameon=False,fontsize=8.8,columnspacing=1.2,handletextpad=.4)
    fig.subplots_adjust(left=.025,right=.975,bottom=.14,top=.94,wspace=.035)
    return save(fig,out/"selected"/"fig_selected4_alpha_PT_vs_AT_vertical.png",dpi)


def geometry_volume_ranking(faces, out):
    """True 3D polyhedral volumes (CIELAB^3), not sample-point counts.

    The stored space is the authoritative geometry; the vertices here are
    reconstructed from PyFCS's clipped halfspaces, as in the visualizer.
    """
    records = []
    for layer in ("core", "alpha"):
        for shade in SHADE_ORDER:
            pts = np.unique(np.vstack(faces[layer][shade]).round(9), axis=0)
            if len(pts) < 4:
                raise ValueError(f"Degenerate volume: {shade} ({layer})")
            volume = float(ConvexHull(pts).volume)
            family = shade[0]
            records.append({"layer":layer, "shade":shade, "family":family,
                            "volume_CIELAB3":volume})
    path = out / "geometry_volumes_ranking.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    chosen = []
    for family in "ABCD":
        options = [r for r in records if r["layer"] == "alpha" and r["family"] == family]
        best = min(options, key=lambda r: r["volume_CIELAB3"])
        chosen.append(best["shade"])
        print(f"  Familia {family}: {best['shade']} — 0.5-cut {best['volume_CIELAB3']:.1f} LAB³", flush=True)
    if tuple(chosen) != FOUR_SHADES:
        raise ValueError(
            f"La selección por defecto {FOUR_SHADES} no coincide con los menores volúmenes {tuple(chosen)}")
    return records

def main(argv=None):
    args=parse_args(argv)
    global AXES_ZOOM
    if not np.isfinite(args.zoom_factor) or not 0.7 <= args.zoom_factor <= 1.5:
        raise ValueError("--zoom-factor debe estar entre 0.7 y 1.5")
    AXES_ZOOM = float(args.zoom_factor)
    if args.dpi < 100 or not np.isfinite(args.step) or args.step <= 0:
        raise ValueError("--dpi >= 100 y --step > 0")
    args.space=args.space.resolve()
    args.analysis_dir=args.analysis_dir.resolve()
    out=(args.out or args.analysis_dir/"results_figures").resolve()
    print("Cámara PyFCS: elev=%.2f, azim=%.2f, orthographic"%(ELEV,AZIM))
    space,sha,groups,prototypes=load_model(args.space)
    clouds=load_bfs_caches(args,sha)
    faces=geometry_faces(space,groups)
    out.mkdir(parents=True, exist_ok=True)
    print("Volúmenes más pequeños por familia (0.5-cut):", flush=True)
    measured_volumes = geometry_volume_ranking(faces, out)
    vita=actual_vita_palette(prototypes)
    g_bounds=geometry_bounds(faces,args.view)
    p_bounds=ptat_bounds(clouds,prototypes,args.view)
    s_bounds=selected_bounds(faces,args.view)
    print("Global geometry bounds [a,b,L]:",g_bounds)
    print("Selected geometry bounds [a,b,L]:",s_bounds)
    paths=[]
    # Publication figure 2: dental-tone volumes, categorical prototypes (Figure 1).
    for layer in ("core", "alpha"):
        paths.append(global_volume_one(layer,"vita",vita,faces,prototypes,g_bounds,out,args.dpi))
    paths.append(global_volume_pair("vita",vita,faces,prototypes,g_bounds,out,args.dpi))
    # Optional alternative categorical geometry is not part of the main paper.
    if args.include_alt_geometry:
        paths.append(global_volume_pair("distinct",DISTINCT,faces,prototypes,g_bounds,out,args.dpi))
    # Publication figure 1: one new elegant categorical palette for 16 shades.
    paths.append(global_pt_at(clouds,prototypes,p_bounds,out,args.dpi))
    # Publication figure 3: dental-tone geometry, PT blue, AT-only orange,
    # shade labels without explicit prototype markers.
    for kind in ("PT","AT"):
        paths.append(selected_threshold_one(faces,prototypes,clouds,vita,kind,s_bounds,out,args.dpi))
    paths.append(selected_threshold_pair(faces,prototypes,clouds,vita,s_bounds,out,args.dpi))
    out.mkdir(parents=True,exist_ok=True)
    manifest={
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "model_file":str(args.space),"model_sha256":sha,
        "analysis_dir":str(args.analysis_dir),"lattice_step":args.step,
        "thresholds":{"PT":PT,"AT":AT},
        "camera_source":"PyFCS VisualManager.plot_more_combined_3D Plotly camera",
        "camera_eye":CAMERA_EYE.tolist(),"camera_elev":ELEV,"camera_azim":AZIM,
        "projection":"orthographic","axis_order":"x=a*, y=b*, z=L*",
        "view_frame":args.view,
        "visual_zoom_factor": AXES_ZOOM,
        "selected_shades": list(FOUR_SHADES),
        "selection_method": "smallest 0.5-cut polyhedral volume in each VITA family",
        "polyhedral_volumes_CIELAB3": measured_volumes,
        "geometry_global_axis_limits":[g_bounds[0].tolist(),g_bounds[1].tolist()],
        "selected_axis_limits":[s_bounds[0].tolist(),s_bounds[1].tolist()],
        "geometry_method":"VisualManager.display_polygons_for_volume — actual PyFCS clipped halfspaces",
        "vita_palette":"sRGB preview approximated from CIELAB prototypes; not calibrated guide colors",
        "distinct_category_palette":DISTINCT,
        "figure_1_color_semantics":"Different category colors for PT and AT, constant between panels",
        "figure_2_color_semantics":"LAB-derived dental-tone volumes; small unobtrusive prototype points use the Figure 1 category palette",
        "figure_3_color_semantics":"LAB-derived dental-tone volumes, PT=blue, AT-only=orange, text shade labels; no explicit prototype markers",
        "main_manuscript_figures":[
            "global/fig_global_alpha_PT_AT_vertical.png",
            "global/fig_global_core_vs_alpha_vita.png",
            "selected/fig_selected4_alpha_PT_vs_AT_vertical.png",
        ],
        "point_clouds":"SHA-verified 350-point regime subsamples per shade from joint BFS, not frequency/volume estimates",
        "outputs_png":paths,
    }
    (out/"results_figures_metadata.json").write_text(
        json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Complete:",len(paths),"PNG images in",out)
    return 0


if __name__=="__main__":
    raise SystemExit(main())

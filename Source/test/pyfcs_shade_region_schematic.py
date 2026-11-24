"""Conceptual schematic: PT/AT region, FCS region, and their intersection.

Produces PDF and SVG vector figures plus a 450-dpi PNG for preview.
Dependencies: numpy, matplotlib.
Run: python pyfcs_shade_region_schematic.py

IMPORTANT: This figure is a two-dimensional conceptual illustration, NOT
an output from the VITA Classical experiments or an exact CIEDE2000 contour.
"""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Ellipse, Polygon, FancyBboxPatch

# For use in a scientific manuscript: colorblind-friendly, print-friendly colors.
BLUE = "#0072B2"    # Perceptual tolerance region
ORANGE = "#D55E00"  # Fuzzy category region
GREEN = "#009E73"   # Intersection
DARK = "#202632"
BORDER = "#D8DEE6"
BACKGROUND = "#FFFFFF"

# Identical prototype and region geometry across all three panels.
REFERENCE = np.array([-0.05, 0.05])
ELLIPSE_RADII = (1.52, 1.10)
FCS_POLYGON = np.array([
    [-1.14,  0.97],
    [-0.28,  1.50],
    [ 1.18,  1.24],
    [ 1.55,  0.10],
    [ 0.56, -1.32],
    [-1.46, -0.55],
], dtype=float)


def polygon_area(vertices):
    x, y = vertices.T
    return 0.5 * float(np.sum(x * np.roll(y, -1) - y * np.roll(x, -1)))


def convex_polygon_clip(subject, clip_polygon):
    """Sutherland-Hodgman clipping: intersection with convex clip polygon."""
    clip_polygon = np.asarray(clip_polygon, dtype=float)
    if polygon_area(clip_polygon) < 0:
        clip_polygon = clip_polygon[::-1]
    output = list(np.asarray(subject, dtype=float))

    def cross(a, b):
        return a[0] * b[1] - a[1] * b[0]

    for p, q in zip(clip_polygon, np.roll(clip_polygon, -1, axis=0)):
        old = output
        output = []
        if not old:
            break

        def inside(point):
            return cross(q - p, point - p) >= -1e-10

        def crossing(a, b):
            # Intersection of segment a->b with the infinite line p->q.
            ab = b - a
            pq = q - p
            denom = cross(ab, pq)
            if abs(denom) < 1e-14:
                return b.copy()
            t = cross(p - a, pq) / denom
            return a + t * ab

        s = old[-1]
        for e in old:
            s_in, e_in = inside(s), inside(e)
            if e_in:
                if not s_in:
                    output.append(crossing(s, e))
                output.append(e)
            elif s_in:
                output.append(crossing(s, e))
            s = e
    return np.asarray(output)


def make_figure():
    theta = np.linspace(0, 2 * np.pi, 1000, endpoint=False)
    ellipse_points = np.column_stack([
        REFERENCE[0] + ELLIPSE_RADII[0] * np.cos(theta),
        REFERENCE[1] + ELLIPSE_RADII[1] * np.sin(theta),
    ])
    overlap = convex_polygon_clip(ellipse_points, FCS_POLYGON)

    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 11,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
        "savefig.facecolor": BACKGROUND,
    })
    fig, axes = plt.subplots(1, 3, figsize=(12.6, 4.05), dpi=150)
    fig.patch.set_facecolor(BACKGROUND)
    fig.subplots_adjust(left=0.025, right=0.975, top=0.97, bottom=0.05, wspace=0.09)

    panels = [
        ("(a) Perceptual region", r"$\Delta E_{00}(r_i,q)<\tau$"),
        ("(b) Fuzzy color region", r"$\mu_i(q)\geq\alpha$"),
        ("(c) Integrated shade region", r"$\mu_i(q)\geq\alpha,\ \Delta E_{00}(r_i,q)<\tau$"),
    ]

    for index, (ax, (heading, condition)) in enumerate(zip(axes, panels)):
        ax.set_xlim(-2.05, 2.05)
        ax.set_ylim(-2.08, 1.94)
        ax.set_aspect("equal", adjustable="box")
        ax.axis("off")

        # Light, restrained panel frame (no dark-mode card background).
        panel = FancyBboxPatch(
            (0.015, 0.015), 0.97, 0.97,
            boxstyle="round,pad=0.001,rounding_size=0.035",
            transform=ax.transAxes, linewidth=0.8,
            facecolor=BACKGROUND, edgecolor=BORDER,
            zorder=0, clip_on=False,
        )
        ax.add_patch(panel)

        if index == 0:
            ax.add_patch(Ellipse(
                xy=REFERENCE, width=2 * ELLIPSE_RADII[0],
                height=2 * ELLIPSE_RADII[1],
                edgecolor=BLUE, facecolor=BLUE,
                linewidth=2.2, alpha=0.20,
                zorder=1,
            ))
            ax.add_patch(Ellipse(
                xy=REFERENCE, width=2 * ELLIPSE_RADII[0],
                height=2 * ELLIPSE_RADII[1],
                edgecolor=BLUE, facecolor="none", linewidth=2.2, zorder=4,
            ))
        elif index == 1:
            ax.add_patch(Polygon(FCS_POLYGON, closed=True,
                facecolor=ORANGE, edgecolor=ORANGE,
                linewidth=2.2, alpha=0.20, zorder=1))
            ax.add_patch(Polygon(FCS_POLYGON, closed=True,
                facecolor="none", edgecolor=ORANGE, linewidth=2.2, zorder=4))
        else:
            # Show both original sets, but emphasize their exact intersection.
            ax.add_patch(Polygon(FCS_POLYGON, closed=True,
                facecolor=ORANGE, edgecolor="none", alpha=0.14, zorder=1))
            ax.add_patch(Ellipse(
                xy=REFERENCE, width=2 * ELLIPSE_RADII[0],
                height=2 * ELLIPSE_RADII[1],
                facecolor=BLUE, edgecolor="none", alpha=0.13, zorder=2,
            ))
            ax.add_patch(Polygon(overlap, closed=True, facecolor=GREEN,
                edgecolor=GREEN, linewidth=1.9, alpha=0.38, zorder=3))
            ax.add_patch(Polygon(FCS_POLYGON, closed=True,
                facecolor="none", edgecolor=ORANGE, linewidth=2.0, zorder=4))
            ax.add_patch(Ellipse(
                xy=REFERENCE, width=2 * ELLIPSE_RADII[0],
                height=2 * ELLIPSE_RADII[1],
                facecolor="none", edgecolor=BLUE,
                linewidth=2.0, linestyle=(0, (4, 2.5)), zorder=5,
            ))
            ax.add_patch(Polygon(overlap, closed=True,
                facecolor="none", edgecolor=GREEN, linewidth=1.45, zorder=6))

        ax.scatter(*REFERENCE, s=37, color=DARK, zorder=7)
        ax.text(0, -1.52, heading, ha="center", va="center",
                fontsize=11.2, weight="bold", color=DARK, zorder=9)
        ax.text(0, -1.75, condition, ha="center", va="center",
                fontsize=10.7, color=DARK, zorder=9)
    return fig


def main():
    out_dir = Path(__file__).resolve().parent
    fig = make_figure()
    for suffix, kwargs in [
        ("pdf", {}),
        ("svg", {}),
        ("png", {"dpi": 450}),
    ]:
        target = out_dir / f"PyFCS_FCS_PTAT_schematic.{suffix}"
        fig.savefig(target, bbox_inches="tight", pad_inches=0.04, **kwargs)
        print(f"Saved: {target}")
    plt.close(fig)


if __name__ == "__main__":
    main()

"""Construction strategies for atomic Voronoi fuzzy color spaces.

Non-covering sampled negatives follow the Soto construction principle:
grid candidates near/around the domain are filtered against positives.
The implementation is domain-aware (LAB can have negative coordinates)
and uses only cells for real color labels; it does not generate fake labels.
"""
import itertools
import warnings
import numpy as np
from Source.colorspace.ReferenceDomain import ReferenceDomain
from Source.geometry.Prototype import Prototype
from Source.geometry.Voronoi import Voronoi
from Source.fuzzy.FuzzyColorSpace import FuzzyColorSpace
from skimage import color as skcolor



def lab_to_rgb_model_checked(values, *, gamut_tolerance=0.05):
    """Convert LAB triples to native RGB 0..255 without silently clipping gamut.

    Shared by file creation, its GUI validation, and Change Model, so all
    routes apply the same reproducibility rule. Returns an (N, 3) array.
    """
    matrix = np.asarray(values, dtype=float).reshape(-1, 3)
    if not np.all(np.isfinite(matrix)):
        raise ValueError("LAB prototype coordinates must be finite.")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        rgb = skcolor.lab2rgb(matrix.reshape(1, -1, 3))[0]
    rgb255 = np.clip(rgb * 255.0, 0.0, 255.0)
    recovered = skcolor.rgb2lab((rgb255 / 255.0).reshape(1, -1, 3))[0]
    errors = np.linalg.norm(matrix - recovered, axis=1)
    if not np.all(np.isfinite(rgb255)) or not np.all(np.isfinite(errors)):
        raise ValueError("Unable to convert LAB representatives into finite RGB values.")
    count = int(np.count_nonzero(errors > float(gamut_tolerance)))
    if count:
        raise ValueError(
            f"{count} LAB color(s) cannot be reproduced within the sRGB gamut "
            "without clipping. Choose LAB geometry or edit those colors. "
            "The original model was not changed."
        )
    return rgb255


def generate_auxiliary_negatives(positive_points, domain, samples=27):
    """Return regularly sampled negatives not close to real prototypes.

    ``samples`` selects JFCS's nominal sampling resolution (27 => 3 per
    axis). Its expanded grid contains (n+2)^3 candidate sites, including
    domain-exterior sites, before filtering by distance from positives.
    Therefore 27 is NOT the count of stored auxiliary negatives.
    RGB [0,255]^3 reproduces Soto's INTEGER grid-step convention; LAB
    uses domain-relative floating-point sampling, since negative LAB bounds
    cannot be sampled correctly by the original RGB-specific formula.
    """
    total = int(samples)
    n = int(round(total ** (1.0 / 3.0)))
    if n ** 3 != total or not 2 <= n <= 12:
        raise ValueError("@samples must be a perfect cube between 8 and 1728 (e.g., 216).")
    bounds = domain.bounds
    minima = np.array(bounds[::2], dtype=float)
    maxima = np.array(bounds[1::2], dtype=float)
    raw_steps = (maxima - minima) / n
    # Soto's Java code casts RGB grid increments to int before using them.
    is_default_rgb = np.allclose(minima, 0) and np.allclose(maxima, 255)
    grid_steps = np.floor(raw_steps) if is_default_rgb else raw_steps
    points = np.asarray(list(itertools.product(*[
        minima[i] + np.arange(-1, n + 1, dtype=float) * grid_steps[i]
        for i in range(3)
    ])), dtype=float)
    positives = np.asarray(positive_points, dtype=float).reshape(-1, 3)
    radius2 = (2.0 * np.min(raw_steps)) ** 2
    mask = np.ones(len(points), dtype=bool)
    # Bounded memory: do not build an N-grid-by-N-prototype array.
    for p in positives:
        mask &= np.einsum('ij,ij->i', points - p, points - p) > radius2
    return points[mask]


class FuzzyColorSpaceBuilder:
    @staticmethod
    def build(name, selected_points, *, color_space="LAB", reference_domain=None,
              lambda1=0.5, lambda2=1.5, disjoint=True, covering=True,
              samples=27, negative_prototypes=None, description=None,
              improve_geometry=True):
        items = [(str(k), np.asarray(v, dtype=float).reshape(3))
                 for k, v in selected_points.items()]
        if len(items) < 2:
            raise ValueError("At least two positive prototypes are required.")
        labels = [x[0] for x in items]
        if len(set(labels)) != len(labels):
            raise ValueError("Prototype labels must be unique.")
        pts = np.asarray([x[1] for x in items])
        domain = reference_domain or ReferenceDomain.for_color_space(color_space)
        Voronoi._validate_points_in_domain(pts, domain, Voronoi.DEFAULT_EPS)
        Voronoi._validate_no_duplicate_points(pts, Voronoi.DEFAULT_MERGE_EPS)
        if not (0 <= lambda1 < 1 and 1 < lambda2 <= 2):
            raise ValueError("Require 0 <= lambda1 < 1 and 1 < lambda2 <= 2.")
        if disjoint and not (1 <= lambda1 + lambda2 <= 2 + 1e-10):
            raise ValueError("Disjoint spaces require 1 <= lambda1 + lambda2 <= 2.")

        extra = (generate_auxiliary_negatives(pts, domain, samples)
                 if not covering else np.empty((0, 3)))
        if not covering and not len(extra):
            raise ValueError(
                "Auxiliary sampling produced no negative sites. "
                "Increase the sample density or revise the reference domain."
            )
        negmap = {}
        volumes = []
        if disjoint and covering:
            # The original code path, identical order, geometry and validators.
            volumes = Voronoi.build_diagram(pts, reference_domain=domain)
            for i, label in enumerate(labels):
                negmap[label] = [tuple(row) for j,row in enumerate(pts) if i != j]
        elif disjoint:
            competitors = np.vstack([pts, extra])
            for i, (label, p) in enumerate(items):
                others = np.concatenate([competitors[:i],competitors[i+1:]], axis=0)
                volumes.append(Voronoi.build_cell(p, others, reference_domain=domain))
                negmap[label] = [tuple(row) for row in others]
        else:
            source = negative_prototypes or {}
            for label, p in items:
                choices = source.get(label, [])
                negatives = np.asarray(choices, dtype=float).reshape(-1,3)
                # Covering requires negatives to be drawn from REAL positive sites;
                # the UI exposes a subset selector rather than arbitrary points.
                if covering and len(negatives):
                    for q in negatives:
                        if not any(np.linalg.norm(q-z)<Voronoi.DEFAULT_MERGE_EPS for z in pts):
                            raise ValueError("Covering construction accepts only other real representatives as negatives.")
                neg = np.vstack([negatives, extra]) if len(extra) else negatives
                volumes.append(Voronoi.build_cell(p, neg, reference_domain=domain))
                negmap[label] = [tuple(row) for row in neg]

        prototypes = [Prototype(label=label, positive=p, voronoi_volume=v)
                      for (label,p),v in zip(items,volumes)]
        return FuzzyColorSpace(
            space_name=name, prototypes=prototypes, color_space=color_space,
            disjoint=disjoint, covering=covering, reference_domain=domain,
            lambda1=lambda1, lambda2=lambda2, samples=(int(samples) if not covering else 0),
            negative_prototypes=negmap, auxiliary_negatives=extra,
            description=description, improve_geometry=bool(improve_geometry),
        )


# Model conversion is intentionally separate from the display LAB/RGB projection.
# The latter must never change existing volumes or memberships.
def rebuild_in_color_space(space, target_color_space, *, gamut_tolerance=0.05):
    """Build a new atomic FCS in LAB or RGB without mutating ``space``.

    Positives and explicit negatives are converted in a single operation.
    Auxiliary sites are *regenerated* in the new reference domain rather than
    converted: their old positions belong to the old sampling grid.
    The new geometry is constructed from scratch, not reprojected.

    Refuse an LAB -> sRGB conversion that would silently clip a color; this
    would otherwise shift representatives and could make Voronoi degenerate.
    """
    if space is None:
        raise ValueError("Load a fuzzy color space before changing its model.")
    target = str(target_color_space).strip().upper()
    if target not in ("LAB", "RGB"):
        raise ValueError("The model color space must be LAB or RGB.")
    source = str(space.color_space).upper()
    if target == source:
        return space
    if len(space.prototypes) < 2:
        raise ValueError("At least two representatives are needed to rebuild the model.")

    def convert(values):
        matrix = np.asarray(values, dtype=float).reshape(-1, 3)
        if not np.all(np.isfinite(matrix)):
            raise ValueError("The model contains non-finite prototype coordinates.")
        if source == "RGB":
            # No rounding: retain double precision for the converted model.
            if np.any((matrix < -1e-8) | (matrix > 255 + 1e-8)):
                raise ValueError("An RGB prototype is outside the 0..255 domain.")
            converted = skcolor.rgb2lab(np.clip(matrix, 0, 255).reshape(1, -1, 3) / 255.0)[0]
        else:
            converted = lab_to_rgb_model_checked(matrix, gamut_tolerance=gamut_tolerance)
        if not np.all(np.isfinite(converted)):
            raise ValueError("The color model conversion produced invalid coordinates.")
        return converted

    names = [proto.label for proto in space.prototypes]
    old_points = np.asarray([p.positive for p in space.prototypes], dtype=float)
    new_points = convert(old_points)
    points_by_name = dict(zip(names, new_points))
    source_points = dict(zip(names, old_points))
    new_negatives = {}

    # For non-disjoint constructions, honor per-category negative choices.
    # Real negative points matching a positive become *exactly* its converted
    # position. This prevents floating-point drift at shared sites.
    if not space.disjoint:
        auxiliary = np.asarray(getattr(space, "auxiliary_negatives", []), dtype=float).reshape(-1, 3)
        threshold = Voronoi.DEFAULT_MERGE_EPS
        for category in names:
            real_negatives = []
            for item in space.negative_prototypes.get(category, []):
                value = np.asarray(item, dtype=float).reshape(3)
                if len(auxiliary) and np.any(np.linalg.norm(auxiliary - value, axis=1) <= threshold):
                    continue
                matching = [name for name, point in source_points.items()
                            if np.linalg.norm(point - value) <= threshold]
                if matching:
                    # Ignore an accidental self-reference (invalid negative).
                    if matching[0] == category:
                        raise ValueError(f"'{category}' cannot be its own negative.")
                    real_negatives.append(np.asarray(points_by_name[matching[0]], dtype=float))
                else:
                    if space.covering:
                        raise ValueError(
                            f"The negative prototypes of '{category}' are not real color categories. "
                            "The model was not changed."
                        )
                    real_negatives.append(convert([value])[0])
            new_negatives[category] = real_negatives

    # Domain conversion cannot be performed by merely converting its eight
    # corners (a nonlinear mapping of a box is not a box). Use the conventional
    # complete bounds of the target model, and reconstruct every volume.
    new_domain = ReferenceDomain.for_color_space(target)
    rebuilt = FuzzyColorSpaceBuilder.build(
        space.space_name,
        points_by_name,
        color_space=target,
        reference_domain=new_domain,
        lambda1=space.lambda1,
        lambda2=space.lambda2,
        disjoint=space.disjoint,
        covering=space.covering,
        samples=space.samples or 27,
        negative_prototypes=new_negatives if not space.disjoint else None,
        description=space.description,
    )
    rebuilt.tconorm = getattr(space, "tconorm", "bounded_sum")
    rebuilt.precompute_pack()
    return rebuilt

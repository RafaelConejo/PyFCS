import os
import math
from collections import deque
import numpy as np
import pandas as pd

# Project modules
from Source.geometry.Point import Point
from Source.colorspace.ReferenceDomain import ReferenceDomain


def rank_membership_frontier(space, lab, snapshot, level=0, *, input_value=None, input_space="LAB", frontier=None):
    """Rank one semantic frontier, never ancestors against their descendants."""
    if space is None:
        return {"memberships": [], "winner_label": None, "winner_mu": 0.0}
    values = snapshot["categories"]
    labels = space.get_categories_at_level(level) if frontier is None else frontier
    ordered = sorted(((name, values[name]["degree"]) for name in labels),
                     key=lambda item: -item[1])
    winner = ordered[0][0] if ordered and ordered[0][1] > 0 else None
    partition = getattr(space, "_uses_partition_normalization", False)
    if winner is not None and getattr(space, "is_granular", False) and not partition:
        top = ordered[0][1]
        ties = [name for name, degree in ordered if abs(degree-top) <= 1e-12 and degree > 0]
        if len(ties) > 1:
            q = np.asarray(space._coordinates(lab if input_value is None else input_value, input_space))
            winner = min(ties, key=lambda name: min(
                float(np.dot(p.positive-q, p.positive-q))
                for p in space.get_descendant_granules(name)))
        ordered.sort(key=lambda item: (-item[1], item[0] != winner))
    if winner is not None and (partition or not getattr(space, "is_granular", False)):
        top = ordered[0][1]
        if sum(d == top for _, d in ordered) > 1:
            idx = space.best_prototype_index(lab if input_value is None else input_value,
                                             input_space=input_space)
            if idx >= 0 and space.prototypes[idx].label in labels:
                winner = space.prototypes[idx].label
        ordered.sort(key=lambda item: (-item[1], item[0] != winner))
    return {"memberships": ordered, "winner_label": winner,
            "winner_mu": values[winner]["degree"] if winner is not None else 0.0}


def membership_snapshot(space, lab, manager, level=0, *, input_value=None,
                                   input_space="LAB", descendants=None, frontier=None):
    """Effective membership snapshot: partition policy or semantic aggregation."""
    if space is None:
        return {"memberships": [], "categories": {}, "granules": {},
                "winner_label": None, "winner_mu": 0.0}
    if getattr(space, "is_granular", False):
        effective = space.calculate_membership_snapshot(
            lab if input_value is None else input_value, input_space=input_space)
        degrees = effective["granules"]
        values = {name: {"degree": float(degree),
                         "granules": {g: float(degrees[g]) for g in (
                             descendants[name] if descendants is not None else
                             (p.label for p in space.get_descendant_granules(name)))}}
                  for name, degree in effective["categories"].items()}
    else:
        effective = space.calculate_membership_snapshot(
            lab if input_value is None else input_value, input_space=input_space)
        degrees = effective["granules"]
        values = {name: {"degree": degree, "granules": {name: degree}}
                  for name, degree in degrees.items()}
    snapshot = {"categories": values, "granules": degrees}
    snapshot.update(rank_membership_frontier(space, lab, snapshot, level,
                                    input_value=input_value, input_space=input_space, frontier=frontier))
    return snapshot


def nearest_granule(manager, candidates, lab, metric):
    """Use a real descendant, with stable tie order, as the metric reference."""
    best = None
    for label, candidate in candidates:
        try:
            distance = float(manager.calculate_metric_value(lab, candidate, metric))
            if np.isfinite(distance) and (best is None or distance < best[0]):
                best = (distance, label)
        except (TypeError, ValueError, ArithmeticError):
            continue
    return best[1] if best else (candidates[0][0] if candidates else None)


class ColorEvaluationManager:
    """
    Handles color evaluation operations:
    - CSV generation for LAB volume limits.
    - Point filtering inside Voronoi volumes.
    - Color-difference metrics and threshold classification.
    - Color-space row extraction, memberships and closest-prototype ranking.
    """

    METRIC_FAMILIES = {
        "Perceptual ΔE": [
            "CIEDE2000",
            "CIE76",
            "CIE94 Graphic Arts",
            "CIE94 Textiles",
            "CMC 2:1",
        ],
        "LAB components": [
            "|ΔL*|",
            "|Δa*|",
            "|Δb*|",
            "ΔEab",
            "Δab plane",
        ],
        "LCh components": [
            "|ΔL*|",
            "|ΔC*|",
            "|Δh°|",
            "|ΔH*|",
        ],
        "RGB / display": [
            "RGB Euclidean",
            "|ΔR|",
            "|ΔG|",
            "|ΔB|",
        ],
    }

    DEFAULT_THRESHOLD_SETTINGS = {
        "metric_family": "Perceptual ΔE",
        "metric": "CIEDE2000",
        "mode": "default",
        "preset": "pt_at",
        "custom_type": "single",
        "single": "1.800",
        "lower": "0.800",
        "upper": "1.800",
    }

    def __init__(self, output_dir=None):
        # Use the runtime output directory even when the manager is instantiated separately.
        if output_dir is None:
            try:
                import Source.interface.modules.common.UtilsTools as UtilsTools
                output_dir = UtilsTools.get_runtime_temp_dir("threshold_results", create=False)
            except Exception:
                output_dir = os.path.join(os.getcwd(), "threshold_results")

        self.output_dir = os.path.abspath(output_dir)

    # CSV / Volume Filtering
    def create_csv(self, file_base_name, volume_limits, mode=None, color_space="LAB"):
        csv_data = []

        for vol_name, limits in volume_limits.items():
            def fmt(vmin, vmax):
                if vmin is None or vmax is None:
                    return "-"
                return f'"{vmin:.2f} - {vmax:.2f}"'

            labels = ("R", "G", "B") if color_space.upper() == "RGB" else ("L*", "a*", "b*")
            csv_data.append({"Volume": vol_name,
                labels[0]: fmt(limits["L"][0], limits["L"][1]),
                labels[1]: fmt(limits["a"][0], limits["a"][1]),
                labels[2]: fmt(limits["b"][0], limits["b"][1]),
            })

        df = pd.DataFrame(csv_data)
        suffix = f"_{mode}" if mode else ""
        csv_name = f"{os.path.basename(file_base_name)}_limits{suffix}.csv"
        # Create the output directory only when a CSV is written.
        os.makedirs(self.output_dir, exist_ok=True)
        csv_path = os.path.join(self.output_dir, csv_name)
        df.to_csv(csv_path, index=False, encoding="utf-8-sig", sep=";")
        print(f"✅ CSV saved: {csv_name}")
        return csv_path

    @staticmethod
    def _limits_for_threshold_points(points):
        """Axis-aligned limits of a sampled region (not a bounding volume)."""
        if not points:
            return {axis: (None, None) for axis in ("L", "a", "b")}
        xyz = np.asarray(points, dtype=float)
        return {
            axis: (float(xyz[:, index].min()), float(xyz[:, index].max()))
            for index, axis in enumerate(("L", "a", "b"))
        }

    def filter_points_with_thresholds(
        self, selected_volume, step=0.25, metric="CIEDE2000",
        color_space="LAB", pt_threshold=0.8, at_threshold=1.8, *, inclusive=False,
    ):
        """Explore PT and AT with *one* traversal per prototype.

        The AT region is explored by six-neighbour BFS, anchored at each
        positive prototype. Every grid node is evaluated at most once per
        prototype, and each accepted AT node is classified into PT or AT-only
        without recomputing the color difference. The grids use INTEGER
        offsets from the (possibly non-integer) prototype; no cumulative
        floating-point additions or arbitrary 2-decimal rounding occur.

        Important methodological limitation: this returns the six-connected
        component reachable from each prototype, NOT necessarily all valid
        grid points in a disconnected intersection of the fuzzy geometry and
        the perceptual threshold region. The caller must use a separate grid
        validation if exhaustive coverage is required for a publication.

        ``inclusive=True`` uses <=, as in the interactive threshold cards.
        The historical research API defaults to strict < for reproducibility.

        Returns three groups (PT, AT, AT_ONLY). Each group contains a 'points'
        dict keyed by Volume_0, Volume_1, ... and a 'limits' dict keyed by the
        actual prototype label. The AT group contains the PT points as well;
        AT_ONLY and PT form a disjoint partition of AT.
        """
        step = float(step)
        pt_threshold = float(pt_threshold)
        at_threshold = float(at_threshold)
        if not np.isfinite(step) or step <= 0:
            raise ValueError("Grid step must be a finite positive number.")
        if not (np.isfinite(pt_threshold) and np.isfinite(at_threshold)
                and 0 < pt_threshold < at_threshold):
            raise ValueError("Require finite thresholds 0 < PT < AT.")
        space_name = str(color_space).upper()
        if space_name not in ("RGB", "LAB"):
            raise ValueError("Threshold search supports only LAB and RGB spaces.")
        metric = self.normalize_metric_name(metric)
        if space_name == "RGB":
            from skimage import color as skcolor
            step = max(1.0, step)

            def to_lab(xyz):
                rgb = np.asarray(xyz, dtype=float).reshape(1, 1, 3)
                return skcolor.rgb2lab(np.clip(rgb, 0, 255) / 255.0)[0, 0]
        else:
            def to_lab(xyz):
                return xyz

        result = {
            name: {"points": {}, "limits": {}}
            for name in ("PT", "AT", "AT_ONLY")
        }
        directions = ((1, 0, 0), (-1, 0, 0),
                      (0, 1, 0), (0, -1, 0),
                      (0, 0, 1), (0, 0, -1))

        for index, prototype in enumerate(selected_volume):
            seed = np.asarray(prototype.positive, dtype=float).reshape(3)
            if not np.all(np.isfinite(seed)):
                raise ValueError(f"Invalid prototype coordinates: {prototype.label}.")
            reference_lab = to_lab(seed)
            volume = prototype.voronoi_volume
            offsets = deque([(0, 0, 0)])
            seen = {(0, 0, 0)}
            pt_points, at_points, at_only_points = [], [], []

            while offsets:
                offset = offsets.popleft()
                # Offset keys are exact integers, even with a sub-centesimal
                # step. Multiplication from the original seed avoids drift.
                xyz = tuple(float(seed[axis] + step * offset[axis])
                            for axis in range(3))
                if not volume.isInside(Point(*xyz)):
                    continue
                distance = self.calculate_metric_value(
                    to_lab(xyz), reference_lab, metric
                )
                if not np.isfinite(distance) or distance < 0 or distance > at_threshold or (not inclusive and distance == at_threshold):
                    continue

                at_points.append(xyz)
                if distance < pt_threshold or (inclusive and distance == pt_threshold):
                    pt_points.append(xyz)
                else:
                    at_only_points.append(xyz)

                for direction in directions:
                    next_offset = (offset[0] + direction[0],
                                   offset[1] + direction[1],
                                   offset[2] + direction[2])
                    if next_offset not in seen:
                        seen.add(next_offset)
                        offsets.append(next_offset)

            for region, points in (("PT", pt_points), ("AT", at_points),
                                   ("AT_ONLY", at_only_points)):
                result[region]["points"][f"Volume_{index}"] = points
                result[region]["limits"][prototype.label] = (
                    self._limits_for_threshold_points(points)
                )

        return result

    def filter_points_with_threshold(
        self, selected_volume, threshold, step, metric="CIEDE2000",
        color_space="LAB",
    ):
        """Legacy single-threshold API for existing external integrations.

        Kept independent of the dual-threshold API so callers requesting an
        arbitrary threshold other than dental PT/AT get the exact requested
        cutoff, not an approximate substitution.
        """
        threshold = float(threshold)
        if not np.isfinite(threshold) or threshold <= 0:
            raise ValueError("Threshold must be a finite positive number.")
        # The paired algorithm requires PT < AT. Pick a lower auxiliary
        # threshold, then return only the AT set at the requested cutoff.
        result = self.filter_points_with_thresholds(
            selected_volume, step=step, metric=metric,
            color_space=color_space, pt_threshold=threshold / 2.0,
            at_threshold=threshold,
        )
        return result["AT"]["points"], result["AT"]["limits"]

    # Metric Lists / Settings
    @classmethod
    def get_default_threshold_settings(cls):
        return dict(cls.DEFAULT_THRESHOLD_SETTINGS)

    @classmethod
    def get_metric_families(cls):
        return list(cls.METRIC_FAMILIES.keys())

    @classmethod
    def get_metrics_for_family(cls, family):
        family = str(family).strip()
        if family not in cls.METRIC_FAMILIES:
            family = "Perceptual ΔE"
        return list(cls.METRIC_FAMILIES[family])

    @classmethod
    def get_family_for_metric(cls, metric):
        metric = cls.normalize_metric_name(metric)
        for family, metrics in cls.METRIC_FAMILIES.items():
            if metric in metrics:
                return family
        return "Perceptual ΔE"

    @staticmethod
    def normalize_metric_name(metric):
        text = str(metric).strip()
        aliases = {
            "DeltaE2000": "CIEDE2000", "Delta E 2000": "CIEDE2000", "ΔE00": "CIEDE2000", "DE2000": "CIEDE2000",
            "DeltaE76": "CIE76", "ΔE76": "CIE76", "DE76": "CIE76",
            "CIE94": "CIE94 Graphic Arts", "ΔE94": "CIE94 Graphic Arts",
            "CMC": "CMC 2:1", "CMC l:c": "CMC 2:1",
            "dL": "|ΔL*|", "ΔL": "|ΔL*|", "abs dL": "|ΔL*|",
            "dA": "|Δa*|", "Δa": "|Δa*|", "abs da": "|Δa*|",
            "dB": "|Δb*|", "Δb": "|Δb*|", "abs db": "|Δb*|",
            "dC": "|ΔC*|", "ΔC": "|ΔC*|",
            "dh": "|Δh°|", "Δh": "|Δh°|",
            "dH": "|ΔH*|", "ΔH": "|ΔH*|",
        }
        return aliases.get(text, text if text else "CIEDE2000")

    @classmethod
    def normalize_threshold_settings(cls, threshold_settings=None):
        settings = cls.get_default_threshold_settings()
        if isinstance(threshold_settings, dict):
            settings.update(threshold_settings)

        if settings.get("mode") == "known":
            settings["mode"] = "default"

        metric = cls.normalize_metric_name(settings.get("metric", "CIEDE2000"))
        family = settings.get("metric_family", "Perceptual ΔE")
        valid_metrics = cls.get_metrics_for_family(family)

        if metric not in valid_metrics:
            family = cls.get_family_for_metric(metric)
            valid_metrics = cls.get_metrics_for_family(family)

        if metric not in valid_metrics:
            family = "Perceptual ΔE"
            metric = "CIEDE2000"

        settings["metric_family"] = family
        # Keep the metric and threshold family consistent after normalization.
        settings["metric"] = metric
        return settings

    @classmethod
    def get_metric_description(cls, metric):
        metric = cls.normalize_metric_name(metric)
        descriptions = {
            "CIEDE2000": "Perceptual color difference. Recommended default for visual similarity.",
            "CIE76": "Euclidean distance in CIELAB. Simple but less perceptually corrected.",
            "CIE94 Graphic Arts": "CIE94 ΔE using graphic-arts weighting.",
            "CIE94 Textiles": "CIE94 ΔE using textile weighting.",
            "CMC 2:1": "CMC 2:1 color difference. Commonly used for acceptability assessment.",
            "CMC l:c": "CMC l:c color difference. Commonly used for acceptability assessment.",
            "|ΔL*|": "Absolute lightness difference only. Chroma and hue are ignored.",
            "|Δa*|": "Absolute green-red component difference only.",
            "|Δb*|": "Absolute blue-yellow component difference only.",
            "ΔEab": "Euclidean distance in full CIELAB space.",
            "Δab plane": "Euclidean distance only in the a*b* chromatic plane.",
            "|ΔC*|": "Absolute chroma/saturation difference only.",
            "|Δh°|": "Absolute hue-angle difference in degrees.",
            "|ΔH*|": "Perceptual hue difference in LAB units.",
            "RGB Euclidean": "Euclidean distance between approximate 8-bit sRGB display colors derived from LAB. Not perceptually uniform.",
            "|ΔR|": "Absolute red-channel difference of approximate 8-bit sRGB display colors derived from LAB.",
            "|ΔG|": "Absolute green-channel difference of approximate 8-bit sRGB display colors derived from LAB.",
            "|ΔB|": "Absolute blue-channel difference of approximate 8-bit sRGB display colors derived from LAB.",
        }
        return descriptions.get(metric, "Color difference metric.")

    # Threshold Validation / Texts
    @staticmethod
    def parse_positive_threshold(value):
        if value is None:
            return None, "Threshold cannot be empty."
        text = str(value).strip().replace(",", ".")
        if text == "":
            return None, "Threshold cannot be empty."
        if any(ch not in set("0123456789.") for ch in text):
            return None, "Threshold must be a valid number."
        if text.count(".") > 1 or text == ".":
            return None, "Threshold must be a valid number."
        try:
            parsed = float(text)
        except (TypeError, ValueError):
            return None, "Threshold must be a valid number."
        if not np.isfinite(parsed):
            return None, "Threshold must be a finite number."
        if parsed <= 0:
            return None, "Threshold must be greater than 0."
        return parsed, None

    @classmethod
    def validate_custom_range(cls, lower_value, upper_value):
        lower, err_lower = cls.parse_positive_threshold(lower_value)
        if err_lower:
            return None, None, f"Lower threshold: {err_lower}"
        upper, err_upper = cls.parse_positive_threshold(upper_value)
        if err_upper:
            return None, None, f"Upper threshold: {err_upper}"
        if lower >= upper:
            return None, None, "Lower thr. must be smaller than upper thr."
        return lower, upper, None

    @classmethod
    def get_threshold_summary_parts(cls, threshold_settings=None):
        settings = cls.normalize_threshold_settings(threshold_settings)
        title = f"{settings['metric_family']} / {settings['metric']}"
        mode = settings.get("mode", "default")

        if mode == "default":
            if settings["metric"] != "CIEDE2000":
                return (title, "Preset not calibrated for this metric", "Select Custom thresholds")
            preset = settings.get("preset", "pt_at")
            if preset == "pt":
                return title, "Preset: Perceptibility Threshold", "PT = 0.800"
            if preset == "at":
                return title, "Preset: Acceptability Threshold", "AT = 1.800"
            return title, "Preset: Perceptibility + Acceptability", "PT = 0.800 | AT = 1.800"

        if mode == "custom":
            custom_type = settings.get("custom_type", "single")
            if custom_type == "single":
                parsed, err = cls.parse_positive_threshold(settings.get("single"))
                return title, "Configuration: Single threshold", "Invalid threshold value." if err else f"Threshold = {parsed:.3f}"
            lower, upper, err = cls.validate_custom_range(settings.get("lower"), settings.get("upper"))
            return title, "Configuration: Lower and upper thresholds", "Invalid threshold range." if err else f"Lower = {lower:.3f} | Upper = {upper:.3f}"

        return title, "", ""

    @classmethod
    def get_threshold_description(cls, threshold_settings=None, include_metric_description=True):
        settings = cls.normalize_threshold_settings(threshold_settings)
        metric_note = cls.get_metric_description(settings["metric"]) if include_metric_description else ""
        title, detail, extra = cls.get_threshold_summary_parts(settings)
        base = f"Metric: {title}\nThresholds -> {detail} | {extra}"
        return f"{base}\n{metric_note}" if metric_note else base

    # Color Conversion / Components
    @staticmethod
    def _safe_lab_array(lab):
        arr = np.asarray(lab, dtype=float).reshape(-1)
        if arr.shape[0] < 3:
            raise ValueError("LAB value must have at least 3 components.")
        arr = arr[:3]
        if not np.all(np.isfinite(arr)):
            raise ValueError("LAB values must be finite.")
        return arr

    @staticmethod
    def signed_hue_angle_difference(h1, h2):
        return float((h1 - h2 + 180.0) % 360.0 - 180.0)

    @staticmethod
    def lab_to_rgb_approx(lab):
        L, a, b = ColorEvaluationManager._safe_lab_array(lab)
        Xn, Yn, Zn = 0.95047, 1.00000, 1.08883
        fy = (L + 16.0) / 116.0
        fx = fy + (a / 500.0)
        fz = fy - (b / 200.0)

        def finv(t):
            t3 = t ** 3
            return t3 if t3 > 0.008856 else (t - 16.0 / 116.0) / 7.787

        X, Y, Z = Xn * finv(fx), Yn * finv(fy), Zn * finv(fz)
        R =  3.2404542 * X - 1.5371385 * Y - 0.4985314 * Z
        G = -0.9692660 * X + 1.8760108 * Y + 0.0415560 * Z
        B =  0.0556434 * X - 0.2040259 * Y + 1.0572252 * Z

        def gamma(u):
            u = max(0.0, min(1.0, float(u)))
            return 12.92 * u if u <= 0.0031308 else 1.055 * (u ** (1.0 / 2.4)) - 0.055

        return tuple(max(0, min(255, int(round(gamma(v) * 255.0)))) for v in (R, G, B))
    

    @staticmethod
    def _ciede2000_weighted_terms(lab1, lab2, kL=1.0, kC=1.0, kH=1.0):
        """Signed normalized terms and C/H cross-term of the CIEDE2000 metric."""
        L1, a1, b1 = ColorEvaluationManager._safe_lab_array(lab1).tolist()
        L2, a2, b2 = ColorEvaluationManager._safe_lab_array(lab2).tolist()
        if not all(math.isfinite(k) and k > 0 for k in (kL, kC, kH)):
            raise ValueError("CIEDE2000 weights must be positive and finite.")
        c = (math.hypot(a1, b1) + math.hypot(a2, b2)) / 2
        g = .5 * (1 - math.sqrt(c**7 / (c**7 + 25.0**7)))
        a1, a2 = (1 + g)*a1, (1 + g)*a2
        c1, c2 = math.hypot(a1,b1), math.hypot(a2,b2)
        h1, h2 = math.degrees(math.atan2(b1,a1)) % 360, math.degrees(math.atan2(b2,a2)) % 360
        dh = h2 - h1
        if c1*c2 == 0:
            dh, hm = 0., h1+h2
        else:
            if dh > 180: dh -= 360
            elif dh < -180: dh += 360
            if abs(h1-h2) <= 180: hm = (h1+h2)/2
            elif h1+h2 < 360: hm = (h1+h2+360)/2
            else: hm = (h1+h2-360)/2
        cm, lm = (c1+c2)/2, (L1+L2)/2
        rad = math.radians
        t = 1 - .17*math.cos(rad(hm-30)) + .24*math.cos(rad(2*hm)) + .32*math.cos(rad(3*hm+6)) - .20*math.cos(rad(4*hm-63))
        sl = 1 + .015*(lm-50)**2/math.sqrt(20+(lm-50)**2)
        sc, sh = 1+.045*cm, 1+.015*cm*t
        rt = -2*math.sqrt(cm**7/(cm**7+25.0**7))*math.sin(rad(60*math.exp(-((hm-275)/25)**2)))
        return ((L2-L1)/(sl*kL), (c2-c1)/(sc*kC),
                2*math.sqrt(c1*c2)*math.sin(rad(dh/2))/(sh*kH), rt)

    @staticmethod
    def ciede2000_coordinate_contribution(sample_lab, prototype_lab, kL=1.0, kC=1.0, kH=1.0):
        """Nonnegative squared contributions in symmetric transformed L/C/H axes.

        The C/H cross-term prevents a unique allocation to pure chroma/hue.
        Apply the positive symmetric square root of [[1, RT/2],[RT/2,1]]
        to the signed normalized C/H pair. The resulting squared norm is
        exactly Delta E00 squared. Percentages describe these transformed
        axes, not independent perceptual causal contributions.
        """
        l, c, h, rt = ColorEvaluationManager._ciede2000_weighted_terms(
            sample_lab, prototype_lab, kL, kC, kH)
        plus, minus = math.sqrt(1+rt/2), math.sqrt(1-rt/2)
        a, b = (plus+minus)/2, (plus-minus)/2
        parts = (l*l, (a*c+b*h)**2, (b*c+a*h)**2)
        total = sum(parts)
        distance = math.sqrt(total)
        pct = tuple(100*p/total if total else 0. for p in parts)
        return dict(L_percent=pct[0], C_percent=pct[1], H_percent=pct[2],
                    L_value=pct[0]*distance/100, C_value=pct[1]*distance/100,
                    H_value=pct[2]*distance/100, DE00_coordinate=distance)

    @staticmethod
    def calculate_component_differences(sample_lab, prototype_lab):
        L1, a1, b1 = ColorEvaluationManager._safe_lab_array(sample_lab)
        L2, a2, b2 = ColorEvaluationManager._safe_lab_array(prototype_lab)
        dL, da, db = float(L1 - L2), float(a1 - a2), float(b1 - b2)
        # Report conventional CIELCh components; CIEDE2000 uses separate primed values.
        C1 = float(np.hypot(a1, b1))
        C2 = float(np.hypot(a2, b2))
        dC = C1 - C2
        h1 = float(np.degrees(np.arctan2(b1, a1)) % 360.0)
        h2 = float(np.degrees(np.arctan2(b2, a2)) % 360.0)
        dh = ColorEvaluationManager.signed_hue_angle_difference(h1, h2)
        if C1 < 1e-12 or C2 < 1e-12:
            # Hue of a neutral sample is undefined: report zero contribution.
            dh = 0.0
        dH = float(2.0 * np.sqrt(C1 * C2) * np.sin(np.radians(dh / 2.0)))

        # Retain primed components separately for CIEDE2000-specific analysis.
        C_avg = (C1 + C2) / 2.0
        G = 0.5 * (1.0 - np.sqrt(C_avg**7 / (C_avg**7 + 25.0**7)))
        a1p, a2p = (1.0 + G) * a1, (1.0 + G) * a2
        C1p, C2p = float(np.hypot(a1p, b1)), float(np.hypot(a2p, b2))
        h1p = float(np.degrees(np.arctan2(b1, a1p)) % 360.0)
        h2p = float(np.degrees(np.arctan2(b2, a2p)) % 360.0)
        dhp = ColorEvaluationManager.signed_hue_angle_difference(h1p, h2p)
        if C1p < 1e-12 or C2p < 1e-12:
            dhp = 0.0
        dHp = float(2.0 * np.sqrt(C1p * C2p) * np.sin(np.radians(dhp / 2.0)))
        delta_e_ab = float(np.sqrt(dL ** 2 + da ** 2 + db ** 2))
        delta_ab_plane = float(np.sqrt(da ** 2 + db ** 2))
        rgb1 = ColorEvaluationManager.lab_to_rgb_approx((L1, a1, b1))
        rgb2 = ColorEvaluationManager.lab_to_rgb_approx((L2, a2, b2))
        dR, dG, dB = float(rgb1[0] - rgb2[0]), float(rgb1[1] - rgb2[1]), float(rgb1[2] - rgb2[2])
        rgb_euclidean = float(np.sqrt(dR ** 2 + dG ** 2 + dB ** 2))

        return {
            "ΔL*": dL, "Δa*": da, "Δb*": db,
            "|ΔL*|": abs(dL), "|Δa*|": abs(da), "|Δb*|": abs(db),
            "C1": C1, "C2": C2, "ΔC*": dC, "|ΔC*|": abs(dC),
            "h1°": h1, "h2°": h2, "Δh°": dh, "|Δh°|": abs(dh),
            "ΔH*": dH, "|ΔH*|": abs(dH),
            "C1'": C1p, "C2'": C2p, "ΔC'": C1p - C2p,
            "h1'°": h1p, "h2'°": h2p, "Δh'°": dhp, "ΔH'": dHp,
            "ΔEab": delta_e_ab, "Δab plane": delta_ab_plane,

            "RGB1": rgb1, "RGB2": rgb2,
            "ΔR": dR, "ΔG": dG, "ΔB": dB,
            "|ΔR|": abs(dR), "|ΔG|": abs(dG), "|ΔB|": abs(dB),
            "RGB Euclidean": rgb_euclidean,
        }


    # Metric Computation
    @staticmethod
    def delta_e_ciede2000(lab1, lab2):
        l, c, h, rt = ColorEvaluationManager._ciede2000_weighted_terms(lab1, lab2)
        return math.sqrt(max(0., l*l+c*c+h*h+rt*c*h))

    @staticmethod
    def delta_e_cie76(lab1, lab2):
        return float(np.linalg.norm(ColorEvaluationManager._safe_lab_array(lab1) - ColorEvaluationManager._safe_lab_array(lab2)))

    @staticmethod
    def delta_e_cie94(lab1, lab2, application="graphic arts"):
        L1, a1, b1 = ColorEvaluationManager._safe_lab_array(lab1)
        L2, a2, b2 = ColorEvaluationManager._safe_lab_array(lab2)
        if str(application).lower().strip() == "textiles":
            kL, K1, K2 = 2.0, 0.048, 0.014
        else:
            kL, K1, K2 = 1.0, 0.045, 0.015
        C1, C2 = np.sqrt(a1 ** 2 + b1 ** 2), np.sqrt(a2 ** 2 + b2 ** 2)
        dL, dC = L1 - L2, C1 - C2
        da, db = a1 - a2, b1 - b2
        dH = np.sqrt(max(0.0, da ** 2 + db ** 2 - dC ** 2))
        SL, SC, SH = 1.0, 1.0 + K1 * C1, 1.0 + K2 * C1
        return float(np.sqrt((dL / (kL * SL)) ** 2 + (dC / SC) ** 2 + (dH / SH) ** 2))

    @staticmethod
    def delta_e_cmc(lab1, lab2, lightness=2.0, chroma=1.0):
        L1, a1, b1 = ColorEvaluationManager._safe_lab_array(lab1)
        L2, a2, b2 = ColorEvaluationManager._safe_lab_array(lab2)
        C1, C2 = np.sqrt(a1 ** 2 + b1 ** 2), np.sqrt(a2 ** 2 + b2 ** 2)
        dL, dC = L1 - L2, C1 - C2
        da, db = a1 - a2, b1 - b2
        dH = np.sqrt(max(0.0, da ** 2 + db ** 2 - dC ** 2))
        h1 = np.degrees(np.arctan2(b1, a1)) % 360.0
        T = 0.56 + abs(0.2 * np.cos(np.radians(h1 + 168.0))) if 164.0 <= h1 <= 345.0 else 0.36 + abs(0.4 * np.cos(np.radians(h1 + 35.0)))
        F = np.sqrt((C1 ** 4) / (C1 ** 4 + 1900.0)) if C1 > 0 else 0.0
        SL = 0.511 if L1 < 16.0 else (0.040975 * L1) / (1.0 + 0.01765 * L1)
        SC = 0.638 + (0.0638 * C1) / (1.0 + 0.0131 * C1)
        SH = SC * (F * T + 1.0 - F)
        return float(np.sqrt((dL / (lightness * SL)) ** 2 + (dC / (chroma * SC)) ** 2 + (dH / SH) ** 2))

    @classmethod
    def calculate_metric_value(cls, sample_lab, prototype_lab, metric="CIEDE2000"):
        metric = cls.normalize_metric_name(metric)
        if metric == "CIEDE2000":
            return float(cls.delta_e_ciede2000(sample_lab, prototype_lab))
        if metric == "CIE76":
            return float(cls.delta_e_cie76(sample_lab, prototype_lab))
        # For asymmetric metrics, the prototype must be the reference color.
        if metric == "CIE94 Graphic Arts":
            return float(cls.delta_e_cie94(prototype_lab, sample_lab, application="graphic arts"))
        if metric == "CIE94 Textiles":
            return float(cls.delta_e_cie94(prototype_lab, sample_lab, application="textiles"))
        if metric in ("CMC 2:1", "CMC l:c"):
            return float(cls.delta_e_cmc(prototype_lab, sample_lab, lightness=2.0, chroma=1.0))
        components = cls.calculate_component_differences(sample_lab, prototype_lab)
        if metric in components:
            return float(components[metric])
        return float(cls.delta_e_ciede2000(sample_lab, prototype_lab))

    @classmethod
    def format_metric_value(cls, value, metric):
        metric = cls.normalize_metric_name(metric)
        if value is None:
            return f"{metric}: -"
        if metric in ("|ΔR|", "|ΔG|", "|ΔB|"):
            return f"{metric} = {value:.0f}"
        if metric == "RGB Euclidean":
            return f"{metric} = {value:.2f}"
        if metric == "|Δh°|":
            return f"{metric} = {value:.2f}°"
        return f"{metric} = {value:.3f}"

    @classmethod
    def format_component_summary(cls, sample_lab, prototype_lab, metric="CIEDE2000"):
        metric = cls.normalize_metric_name(metric)
        c = cls.calculate_component_differences(sample_lab, prototype_lab)

        lab_line = (
            f"ΔL* = {c['ΔL*']:+.3f} | "
            f"Δa* = {c['Δa*']:+.3f} | "
            f"Δb* = {c['Δb*']:+.3f}"
        )

        lch_line = (
            f"ΔC* = {c['ΔC*']:+.3f} | "
            f"Δh° = {c['Δh°']:+.3f}° | "
            f"ΔH* = {c['ΔH*']:+.3f}"
        )

        rgb_line = (
            f"RGB display Δ = ({c['ΔR']:+.0f}, {c['ΔG']:+.0f}, {c['ΔB']:+.0f})"
        )

        lines = ["\nComponent breakdown:"]

        if metric == "CIEDE2000":
            lines.append(lab_line)
            lines.append(lch_line)

            de00_contribution = cls.ciede2000_coordinate_contribution(
                sample_lab,
                prototype_lab
            )

            lines.append(rgb_line)

            lines.append(
                "\nΔE00² transformed L/C/H contribution (%) = "
                f"{de00_contribution['L_percent']:.1f} / "
                f"{de00_contribution['C_percent']:.1f} / "
                f"{de00_contribution['H_percent']:.1f}"
            )


        elif metric in ("CIE76", "ΔEab"):
            lines.append(lab_line)
            lines.append(f"ΔEab = {c['ΔEab']:.3f}")
            lines.append(rgb_line)

        elif metric == "Δab plane":
            lines.append(
                f"Δa* = {c['Δa*']:+.3f} | "
                f"Δb* = {c['Δb*']:+.3f} | "
                f"Δab = {c['Δab plane']:.3f}"
            )
            lines.append(rgb_line)

        elif metric in ("|ΔL*|", "|Δa*|", "|Δb*|"):
            lines.append(lab_line)
            lines.append(rgb_line)

        elif metric in ("|ΔC*|", "|Δh°|", "|ΔH*|"):
            lines.append(lch_line)
            lines.append(rgb_line)

        elif metric in ("CIE94 Graphic Arts", "CIE94 Textiles", "CMC 2:1", "CMC l:c"):
            lines.append(lab_line)
            lines.append(lch_line)
            lines.append(rgb_line)

        elif metric in ("RGB Euclidean", "|ΔR|", "|ΔG|", "|ΔB|"):
            lines.append(rgb_line)

        else:
            lines.append(lab_line)
            lines.append(lch_line)
            lines.append(rgb_line)

        return "\n".join(lines)

    # Evaluation / Classification
    @classmethod
    def _classify_metric_value(cls, value, threshold_settings):
        if value is None or not np.isfinite(value) or value < 0:
            return {"status": "unavailable", "label": "Unavailable", "order": 9}
        settings = cls.normalize_threshold_settings(threshold_settings)
        mode = settings.get("mode", "default")

        if mode == "default":
            # PT/AT presets apply only to CIEDE2000; other metrics need custom limits.
            if settings["metric"] != "CIEDE2000":
                return {"status": "unavailable", "label": "Custom threshold required", "order": 9}
            preset = settings.get("preset", "pt_at")
            pt, at = 0.8, 1.8
            if preset == "pt":
                return {"status": "inside", "label": "Inside PT", "order": 0} if value <= pt else {"status": "outside", "label": "Outside PT", "order": 2}
            if preset == "at":
                return {"status": "inside", "label": "Inside AT", "order": 0} if value <= at else {"status": "outside", "label": "Outside AT", "order": 2}
            if value <= pt:
                return {"status": "inside", "label": "PT match", "order": 0}
            if value <= at:
                return {"status": "warning", "label": "AT match", "order": 1}
            return {"status": "outside", "label": "Different", "order": 2}

        if mode == "custom":
            custom_type = settings.get("custom_type", "single")
            if custom_type == "single":
                threshold, err = cls.parse_positive_threshold(settings.get("single"))
                if err:
                    return {"status": "unavailable", "label": "Invalid threshold", "order": 9}
                return {"status": "inside", "label": "Inside threshold", "order": 0} if value <= threshold else {"status": "outside", "label": "Outside threshold", "order": 2}
            lower, upper, err = cls.validate_custom_range(settings.get("lower"), settings.get("upper"))
            if err:
                return {"status": "unavailable", "label": "Invalid threshold", "order": 9}
            if value <= lower:
                return {"status": "inside", "label": "Inside lower threshold", "order": 0}
            if value <= upper:
                return {"status": "warning", "label": "Inside upper threshold", "order": 1}
            return {"status": "outside", "label": "Outside upper threshold", "order": 2}

        return {"status": "unavailable", "label": "Unavailable", "order": 9}


    @classmethod
    def evaluate_color_difference_threshold(cls, sample_lab, prototype_lab, metric="CIEDE2000", threshold_settings=None):
        try:
            settings = cls.normalize_threshold_settings(threshold_settings)
            metric = cls.normalize_metric_name(metric or settings.get("metric", "CIEDE2000"))
            settings["metric"] = metric  # Classify using the effective metric, not the stored default.
            value = cls.calculate_metric_value(sample_lab, prototype_lab, metric)
            classification = cls._classify_metric_value(value, settings)
            detail = cls.format_metric_value(value, metric)
            summary = (
                f"{classification['label']} using {metric}.\n"
                f"{cls.format_component_summary(sample_lab, prototype_lab, metric)}"
            )
            return {
                "delta_e": value,
                "metric_value": value,
                "metric": metric,
                "metric_label": metric,
                "detail": detail,
                "evaluation": classification["label"],
                "summary": summary,
                "summary_visual": summary,
                "status": classification["status"],
                "class_label": classification["label"],
                "class_order": classification["order"],
                "components": cls.calculate_component_differences(sample_lab, prototype_lab),
            }
        except Exception as exc:
            return {
                "delta_e": None,
                "metric_value": None,
                "metric": metric,
                "metric_label": metric,
                "detail": "",
                "evaluation": "Metric not available",
                "summary": f"Could not compute the selected metric.\n{exc}",
                "summary_visual": f"Could not compute the selected metric.\n{exc}",
                "status": "unavailable",
                "class_label": "Unavailable",
                "class_order": 9,
                "components": {},
            }

    # Color Space / Membership / Ranking Helpers
    @staticmethod
    def extract_color_space_rows(data_source):
        rows = []
        if not isinstance(data_source, dict):
            return rows
        for color_name, color_value in data_source.items():
            if not isinstance(color_value, dict):
                continue
            lab = color_value.get("positive_prototype", color_value.get("Color"))
            if lab is None:
                continue
            try:
                lab_arr = np.asarray(lab, dtype=float).reshape(-1)
                if lab_arr.shape[0] >= 3:
                    rows.append((color_name, lab_arr[:3]))
            except Exception:
                continue
        return rows

    @staticmethod
    def calculate_memberships(fuzzy_color_space, sample_lab):
        if fuzzy_color_space is None:
            return []
        try:
            membership_degrees = fuzzy_color_space.calculate_membership(sample_lab)
        except Exception:
            return []
        if not membership_degrees:
            return []
        return sorted(membership_degrees.items(), key=lambda kv: kv[1], reverse=True)

    @classmethod
    def rank_closest_prototypes(cls, sample_lab, color_rows, metric="CIEDE2000",
                                threshold_settings=None, top_n=7,
                                fuzzy_color_space=None):
        """Rank CATEGORIES by the closest real granule under the chosen ΔE metric.

        Atomic spaces keep their existing single-prototype behavior. For a
        granular category the distance is min_j ΔE(sample, prototype_j): a
        category has no mathematical central prototype to compare against.
        This *metric* ranking is separate from fuzzy membership aggregation.
        """
        settings = cls.normalize_threshold_settings(threshold_settings)
        metric = cls.normalize_metric_name(metric or settings.get("metric", "CIEDE2000"))
        space = fuzzy_color_space
        groups = {}
        if getattr(space, "is_granular", False):
            for label in space.get_root_categories():
                groups[label] = [(p.label, np.asarray(space.lab_from_model(p.positive), dtype=float))
                                 for p in space.get_descendant_granules(label)]
            color_rows = [(label, candidates[0][1]) for label, candidates in groups.items() if candidates]
        settings["metric"] = metric
        ranking = []
        distances = {}
        for label, proto_lab in color_rows:
            candidates = groups.get(label, [(label, proto_lab)])
            winner = None
            for granule_label, candidate in candidates:
                try:
                    key = tuple(float(v) for v in candidate)
                    if key not in distances:
                        distances[key] = float(cls.calculate_metric_value(sample_lab, candidate, metric))
                    value = distances[key]
                    if not np.isfinite(value) or value < 0:
                        continue
                    if winner is None or value < winner["metric_value"]:
                        winner = {"label": label, "granule_label": granule_label,
                                  "granule_lab": np.asarray(candidate, dtype=float),
                                  "delta_e": value, "metric_value": value}
                except (TypeError, ValueError, ArithmeticError):
                    continue
            if winner is not None:
                classification = cls._classify_metric_value(winner["metric_value"], settings)
                winner.update(class_label=classification["label"], class_order=classification["order"],
                              status=classification["status"],
                              detail=cls.format_metric_value(winner["metric_value"], metric))
                ranking.append(winner)
        ranking.sort(key=lambda item: item["metric_value"])
        return ranking[:top_n]
    

    @staticmethod
    def status_from_class_order(class_order):
        """
        Convert a threshold class order or class label into a visual status used by the GUI.

        Returns
        -------
        str
            One of: inside, warning, outside, unavailable.
        """
        if isinstance(class_order, str):
            text = class_order.strip().lower()

            inside_labels = {
                "inside",
                "inside pt",
                "inside at",
                "inside threshold",
                "inside lower",
                "pt match",
                "below pt",
                "below at",
                "within perceptibility threshold",
                "within acceptability threshold",
            }

            warning_labels = {
                "warning",
                "at match",
                "inside upper",
                "between",
                "between pt at",
                "between_custom",
            }

            outside_labels = {
                "outside",
                "different",
                "outside pt",
                "outside at",
                "outside threshold",
                "outside upper",
                "above pt",
                "above at",
            }

            if text in inside_labels:
                return "inside"

            if text in warning_labels:
                return "warning"

            if text in outside_labels:
                return "outside"

            return "unavailable"

        try:
            class_order = int(class_order)
        except Exception:
            return "unavailable"

        if class_order == 0:
            return "inside"

        if class_order == 1:
            return "warning"

        if class_order == 2:
            return "outside"

        return "unavailable"
    

    @classmethod
    def format_closest_ranking_summary(
        cls,
        ranking,
        metric_name="CIEDE2000",
        threshold_settings=None,
        include_threshold_description=True,
        include_metric_description=False
    ):
        """
        Format the closest-prototype ranking as a monospaced aligned table.

        The column widths are computed dynamically so that metrics with short
        names such as |ΔL*| and longer names such as RGB Euclidean remain aligned.
        """
        if not ranking:
            return "No closest-prototype ranking available."

        metric_name = cls.normalize_metric_name(metric_name)

        def _format_value(value, metric):
            try:
                value = float(value)
            except Exception:
                return "-"

            if metric in ("|ΔR|", "|ΔG|", "|ΔB|"):
                return f"{value:.0f}"

            if metric == "RGB Euclidean":
                return f"{value:.2f}"

            if metric == "|Δh°|":
                return f"{value:.2f}"

            return f"{value:.3f}"

        def _safe_text(value, default="-"):
            text = str(value).strip()
            return text if text else default

        granular_ranking = any(
            item.get("granule_label") and item.get("granule_label") != item.get("label")
            for item in ranking
        )
        label_header = "Category / nearest granule" if granular_ranking else "Prototype"
        rows = []

        for index, item in enumerate(ranking, start=1):
            label = _safe_text(item.get("label", "-"))
            if granular_ranking:
                label = f"{label} / {_safe_text(item.get('granule_label', label))}"
            metric_value = item.get("metric_value", item.get("delta_e"))
            metric_text = _format_value(metric_value, metric_name)
            status = _safe_text(item.get("class_label", item.get("status", "-")))

            rows.append({
                "index": index,
                "label": label,
                "metric_text": metric_text,
                "status": status,
            })

        index_w = max(len("#"), len(str(len(rows))))
        prototype_w = max(
            len(label_header),
            min(max(len(row["label"]) for row in rows), 36)
        )
        metric_w = max(
            len(metric_name),
            max(len(row["metric_text"]) for row in rows),
            9
        )
        status_w = max(
            len("Status"),
            max(len(row["status"]) for row in rows),
            8
        )

        def _truncate(text, width):
            text = str(text)

            if len(text) <= width:
                return text

            if width <= 1:
                return text[:width]

            return text[:width - 1] + "…"

        title = (f"{len(rows)} closest categories (nearest real granule) by {metric_name}:"
                 if granular_ranking else
                 f"{len(rows)} closest prototypes by {metric_name}:")

        header = (
            f"{'#':>{index_w}}  "
            f"{label_header:<{prototype_w}}  "
            f"{metric_name:>{metric_w}}  "
            f"{'Status':<{status_w}}"
        )

        separator = (
            f"{'-' * index_w}  "
            f"{'-' * prototype_w}  "
            f"{'-' * metric_w}  "
            f"{'-' * status_w}"
        )

        table_lines = [title, "", header, separator]

        for row in rows:
            label = _truncate(row["label"], prototype_w)

            table_lines.append(
                f"{row['index']:>{index_w}}  "
                f"{label:<{prototype_w}}  "
                f"{row['metric_text']:>{metric_w}}  "
                f"{row['status']:<{status_w}}"
            )

        summary = "\n".join(table_lines)

        if include_threshold_description and threshold_settings is not None:
            try:
                threshold_text = cls.get_threshold_description(
                    threshold_settings=threshold_settings,
                    include_metric_description=include_metric_description
                )

                if threshold_text:
                    summary += "\n\n" + threshold_text

            except Exception:
                pass

        return summary

    # Gui-Independent Color Evaluation Helpers
    @classmethod
    def get_threshold_display_maps(cls):
        """Return display maps used by threshold UIs."""
        preset_display_map = {
            "pt": "Perceptibility Threshold",
            "at": "Acceptability Threshold",
            "pt_at": "Perceptibility + Acceptability",
        }
        custom_type_display_map = {
            "single": "Single threshold",
            "lower_upper": "Lower and upper thresholds",
        }
        return preset_display_map, custom_type_display_map

    @classmethod
    def get_threshold_reverse_maps(cls):
        """Return reverse display maps used by threshold UIs."""
        preset_display_map, custom_type_display_map = cls.get_threshold_display_maps()
        return (
            {v: k for k, v in preset_display_map.items()},
            {v: k for k, v in custom_type_display_map.items()},
        )

    @classmethod
    def build_threshold_settings_from_ui_values(
        cls,
        metric_family,
        metric,
        mode,
        preset_display,
        custom_type_display,
        single_value,
        lower_value,
        upper_value,
        base_settings=None,
    ):
        """
        Build normalized threshold settings from raw UI values.

        The GUI still owns Tk variables, but this method owns the translation
        between display labels and internal configuration keys.
        """
        settings = cls.get_default_threshold_settings()

        if isinstance(base_settings, dict):
            settings.update(base_settings)

        preset_reverse_map, custom_type_reverse_map = cls.get_threshold_reverse_maps()

        mode_value = str(mode).strip().lower()
        if mode_value == "known":
            mode_value = "default"

        single_text = str(single_value).strip() if single_value is not None else ""
        lower_text = str(lower_value).strip() if lower_value is not None else ""
        upper_text = str(upper_value).strip() if upper_value is not None else ""

        settings["metric_family"] = str(metric_family).strip()
        settings["metric"] = str(metric).strip()
        settings["mode"] = mode_value
        settings["preset"] = preset_reverse_map.get(str(preset_display).strip(), "pt_at")
        settings["custom_type"] = custom_type_reverse_map.get(str(custom_type_display).strip(), "single")
        settings["single"] = single_text if single_text != "" else None
        settings["lower"] = lower_text if lower_text != "" else None
        settings["upper"] = upper_text if upper_text != "" else None

        return cls.normalize_threshold_settings(settings)

    @classmethod
    def classify_metric_value(cls, value, threshold_settings=None):
        """Public wrapper around threshold classification for a scalar metric value."""
        return cls._classify_metric_value(value=value, threshold_settings=threshold_settings)

    @staticmethod
    def get_custom_color_input_mode_help(mode):
        """Return labels, limits and examples for a custom color input mode."""
        mode = str(mode).strip().upper()

        if mode == "RGB":
            return {
                "labels": ("R", "G", "B"),
                "limits": "Valid range: R, G, B ∈ [0, 255] (integers)",
                "example": "Example: 120, 85, 200",
            }

        if mode == "LAB":
            return {
                "labels": ("L", "a", "b"),
                "limits": "Valid range:L ∈ [0, 100], \na ∈ [-128, 128], b ∈ [-128, 128]",
                "example": "Example: 54.2, 18.5, -32.1",
            }

        return {
            "labels": ("HEX", "", ""),
            "limits": "Valid format: #RRGGBB or RRGGBB",
            "example": "Example: #7A4FD9",
        }

    @staticmethod
    def normalize_custom_color_input(
        input_mode,
        value_1="",
        value_2="",
        value_3="",
        hex_value="",
        utils_tools=None,
    ):
        """
        Normalize and validate a user-entered color into LAB, RGB, and HEX.

        Parameters
        ----------
        utils_tools : module/object
            Utility provider used by the GUI. Passing it keeps the exact same
            conversion behavior as the existing interface.

        Returns
        -------
        tuple
            (ok, message, sample_lab, sample_rgb, sample_hex)
        """
        if utils_tools is None:
            return False, "Color conversion utilities are not available.", None, None, None

        try:
            mode = str(input_mode).strip().upper()
        except Exception:
            return False, "Unsupported input mode.", None, None, None

        if mode == "RGB":
            try:
                t1 = utils_tools.safe_text(value_1)
                t2 = utils_tools.safe_text(value_2)
                t3 = utils_tools.safe_text(value_3)

                if not t1 or not t2 or not t3:
                    return False, "Enter all RGB values.", None, None, None

                if (
                    not utils_tools.is_plain_rgb_integer(t1)
                    or not utils_tools.is_plain_rgb_integer(t2)
                    or not utils_tools.is_plain_rgb_integer(t3)
                ):
                    return False, "RGB values must be valid integers.", None, None, None

                sample_rgb = (int(t1), int(t2), int(t3))

                if not utils_tools.is_valid_rgb(sample_rgb):
                    return False, "RGB values must be between 0 and 255.", None, None, None

                sample_lab = utils_tools.analysis_rgb_to_lab(sample_rgb)
                sample_lab = utils_tools.safe_lab_tuple(sample_lab)
                sample_hex = utils_tools.rgb_to_hex(sample_rgb)

                return True, "Valid RGB color.", sample_lab, sample_rgb, sample_hex

            except Exception:
                return False, "Invalid RGB color input.", None, None, None

        if mode == "LAB":
            try:
                t1 = utils_tools.safe_text(value_1).replace(",", ".")
                t2 = utils_tools.safe_text(value_2).replace(",", ".")
                t3 = utils_tools.safe_text(value_3).replace(",", ".")

                if not t1 or not t2 or not t3:
                    return False, "Enter all LAB values.", None, None, None

                L = utils_tools.safe_float(t1)
                a = utils_tools.safe_float(t2)
                b = utils_tools.safe_float(t3)

                if L is None or a is None or b is None:
                    return False, "LAB values must be valid numbers.", None, None, None

                sample_lab = (float(L), float(a), float(b))

                if not utils_tools.is_valid_lab(sample_lab):
                    return False, "LAB values must be within L [0,100], a [-128,128], b [-128,128].", None, None, None

                sample_rgb = utils_tools.lab_to_rgb(sample_lab)
                sample_rgb = utils_tools.safe_rgb_tuple(sample_rgb)
                sample_hex = utils_tools.rgb_to_hex(sample_rgb)

                return True, "Valid LAB color.", sample_lab, sample_rgb, sample_hex

            except Exception:
                return False, "Invalid LAB color input.", None, None, None

        if mode == "HEX":
            try:
                hex_text = utils_tools.safe_text(hex_value).upper()

                if not hex_text:
                    return False, "Enter a HEX value.", None, None, None

                if not utils_tools.is_valid_hex(hex_text):
                    return False, "HEX value must be #RRGGBB or RRGGBB.", None, None, None

                sample_rgb = utils_tools.hex_to_rgb(hex_text)
                sample_lab = utils_tools.analysis_rgb_to_lab(sample_rgb)
                sample_lab = utils_tools.safe_lab_tuple(sample_lab)
                sample_hex = utils_tools.rgb_to_hex(sample_rgb)

                return True, "Valid HEX color.", sample_lab, sample_rgb, sample_hex

            except Exception:
                return False, "Invalid HEX color input.", None, None, None

        return False, "Unsupported input mode.", None, None, None

    @staticmethod
    def resolve_volume_limits(volume_limits=None, fuzzy_color_space=None):
        """
        Return volume limits for LAB plots.

        Priority:
        1. Explicit application volume limits.
        2. Loaded fuzzy color space volume_limits / limits / domain.
        3. Default LAB domain.
        """
        if volume_limits is not None:
            return volume_limits

        if fuzzy_color_space is not None:
            for attr_name in ("volume_limits", "limits", "domain"):
                try:
                    candidate = getattr(fuzzy_color_space, attr_name, None)
                    if candidate is not None:
                        return candidate
                except Exception:
                    pass

        return ReferenceDomain.default_voronoi_reference_domain()

    @staticmethod
    def get_active_color_evaluation_sample(vars_dict):
        """Return a real sample for graphs and membership-based analysis.

        Prefer an external image/custom sample on B, then one on A; fall back
        to the selected real row.  Neither category averages nor synthetic
        representatives are introduced by this selection.
        """
        try:
            for prefix in ("secondary", "primary"):
                if (vars_dict.get(prefix + "_mode") == "custom"
                        and vars_dict.get(prefix + "_custom_lab") is not None
                        and vars_dict.get(prefix + "_custom_rgb") is not None):
                    return {
                        "name": vars_dict.get(prefix + "_custom_name", "Sample"),
                        "lab": vars_dict[prefix + "_custom_lab"],
                        "rgb": vars_dict[prefix + "_custom_rgb"],
                        "hex": vars_dict.get(prefix + "_custom_hex"),
                        "source": vars_dict.get(prefix + "_custom_source", "custom"),
                    }
            primary_label = vars_dict.get("primary_label")
            refs = vars_dict.get("color_row_refs", {}).get(primary_label)
            if refs is not None:
                return {
                    "name": primary_label,
                    "lab": refs.get("lab"),
                    "rgb": refs.get("rgb"),
                    "hex": refs.get("hex"),
                    "source": "granule" if refs.get("category") else "prototype",
                }
        except (TypeError, ValueError, KeyError):
            pass
        return None

    @staticmethod
    def calculate_visual_component_differences(lab_1, lab_2):
        """
        Calculate signed component differences between two LAB colors.

        Returns the keys expected by VisualManager.plot_color_evaluation_component_differences:
        ΔL*, Δa*, Δb*, ΔC*, Δh°, ΔH*.
        """
        lab_1 = np.asarray(lab_1, dtype=float).reshape(-1)[:3]
        lab_2 = np.asarray(lab_2, dtype=float).reshape(-1)[:3]

        L1, a1, b1 = lab_1
        L2, a2, b2 = lab_2

        dL = float(L2 - L1)
        da = float(a2 - a1)
        db = float(b2 - b1)

        C1 = float(np.sqrt(a1 ** 2 + b1 ** 2))
        C2 = float(np.sqrt(a2 ** 2 + b2 ** 2))
        dC = float(C2 - C1)

        h1 = float(np.degrees(np.arctan2(b1, a1)) % 360.0)
        h2 = float(np.degrees(np.arctan2(b2, a2)) % 360.0)

        dh = h2 - h1

        if dh > 180:
            dh -= 360
        elif dh < -180:
            dh += 360

        dEab_sq = da ** 2 + db ** 2
        dH_sq = max(0.0, dEab_sq - dC ** 2)
        dH = float(np.sign(dh) * np.sqrt(dH_sq))

        return {
            "ΔL*": dL,
            "Δa*": da,
            "Δb*": db,
            "ΔC*": dC,
            "Δh°": float(dh),
            "ΔH*": dH,
        }

    @staticmethod
    def get_color_evaluation_available_graph_keys(
        rows,
        secondary_mode=None,
        has_primary=False,
        secondary_label_available=False,
        has_custom=False,
        has_fuzzy_color_space=False,
    ):
        """
        Return graph keys that are logically available for the current state.

        The GUI can still filter these keys by checking whether each opener method exists.
        """
        if not rows:
            return []

        available = ["3d", "ab", "lc", "lch"]

        has_row_comparison = bool(
            secondary_mode == "row"
            and has_primary
            and secondary_label_available
        )

        if has_row_comparison:
            available.append("components")

        if has_custom:
            available.append("top7")

            if has_fuzzy_color_space:
                available.append("memberships")

            if has_primary:
                available.append("components")

        return available


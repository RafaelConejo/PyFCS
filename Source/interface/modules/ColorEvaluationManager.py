import os
import heapq
import numpy as np
import pandas as pd
from scipy.spatial import distance

### my libraries ###
from Source.geometry.Point import Point


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
            "CMC l:c",
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

    def __init__(self, output_dir="test_results/Color_Evaluation"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    # ============================================================================================================================================================
    #  CSV / VOLUME FILTERING
    # ============================================================================================================================================================
    def create_csv(self, file_base_name, volume_limits, mode=None):
        csv_data = []

        for vol_name, limits in volume_limits.items():
            def fmt(vmin, vmax):
                if vmin is None or vmax is None:
                    return "-"
                return f'"{vmin:.2f} - {vmax:.2f}"'

            csv_data.append({
                "Volume": vol_name,
                "L*": fmt(limits["L"][0], limits["L"][1]),
                "a*": fmt(limits["a"][0], limits["a"][1]),
                "b*": fmt(limits["b"][0], limits["b"][1]),
            })

        df = pd.DataFrame(csv_data)
        suffix = f"_{mode}" if mode else ""
        csv_name = f"{os.path.basename(file_base_name)}_limits{suffix}.csv"
        csv_path = os.path.join(self.output_dir, csv_name)
        df.to_csv(csv_path, index=False, encoding="utf-8-sig", sep=";")
        print(f"✅ CSV saved: {csv_name}")
        return csv_path

    def filter_points_with_threshold(self, selected_volume, threshold, step, metric="CIEDE2000"):
        """
        Original behavior is preserved by default with CIEDE2000.
        You can now pass another scalar metric if needed.
        """
        filtered_points = {}
        volume_limits = {}
        metric = self.normalize_metric_name(metric)

        for idx, prototype in enumerate(selected_volume):
            positive = np.array(prototype.positive, dtype=float)
            points_within_threshold = []
            heap = [(0, tuple(np.round(positive, 2)))]
            visited = set()
            consecutive_failures = 0
            max_failures = 10

            while heap:
                _, point = heapq.heappop(heap)
                if point in visited:
                    continue
                visited.add(point)

                try:
                    metric_value = self.calculate_metric_value(point, positive, metric)
                except Exception:
                    metric_value = np.inf

                if 0 < metric_value < threshold and prototype.voronoi_volume.isInside(Point(*point)):
                    points_within_threshold.append(point)
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1

                if consecutive_failures > max_failures:
                    break

                for axis in range(3):
                    for sign in (-1, 1):
                        neighbor = list(point)
                        neighbor[axis] = np.round(neighbor[axis] + sign * step, 2)
                        neighbor = tuple(neighbor)
                        if prototype.voronoi_volume.isInside(Point(*neighbor)):
                            heapq.heappush(heap, (distance.euclidean(neighbor, positive), neighbor))

            filtered_points[f"Volume_{idx}"] = points_within_threshold

            if points_within_threshold:
                pts = np.array(points_within_threshold)
                volume_limits[prototype.label] = {
                    "L": (np.min(pts[:, 0]), np.max(pts[:, 0])),
                    "a": (np.min(pts[:, 1]), np.max(pts[:, 1])),
                    "b": (np.min(pts[:, 2]), np.max(pts[:, 2])),
                }
            else:
                volume_limits[prototype.label] = {
                    "L": (None, None),
                    "a": (None, None),
                    "b": (None, None),
                }

        return filtered_points, volume_limits

    # ============================================================================================================================================================
    #  METRIC LISTS / SETTINGS
    # ============================================================================================================================================================
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
            "CMC": "CMC l:c", "CMC 2:1": "CMC l:c",
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
            "CMC l:c": "CMC l:c color difference. Commonly used for acceptability assessment.",
            "|ΔL*|": "Absolute lightness difference only. Chroma and hue are ignored.",
            "|Δa*|": "Absolute green-red component difference only.",
            "|Δb*|": "Absolute blue-yellow component difference only.",
            "ΔEab": "Euclidean distance in full CIELAB space.",
            "Δab plane": "Euclidean distance only in the a*b* chromatic plane.",
            "|ΔC*|": "Absolute chroma/saturation difference only.",
            "|Δh°|": "Absolute hue-angle difference in degrees.",
            "|ΔH*|": "Perceptual hue difference in LAB units.",
            "RGB Euclidean": "Euclidean distance in RGB display space. Not perceptually uniform.",
            "|ΔR|": "Absolute red-channel difference only.",
            "|ΔG|": "Absolute green-channel difference only.",
            "|ΔB|": "Absolute blue-channel difference only.",
        }
        return descriptions.get(metric, "Color difference metric.")

    # ============================================================================================================================================================
    #  THRESHOLD VALIDATION / TEXTS
    # ============================================================================================================================================================
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

    # ============================================================================================================================================================
    #  COLOR CONVERSION / COMPONENTS
    # ============================================================================================================================================================
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
    def calculate_component_differences(sample_lab, prototype_lab):
        L1, a1, b1 = ColorEvaluationManager._safe_lab_array(sample_lab)
        L2, a2, b2 = ColorEvaluationManager._safe_lab_array(prototype_lab)
        dL, da, db = float(L1 - L2), float(a1 - a2), float(b1 - b2)
        C1, C2 = float(np.sqrt(a1 ** 2 + b1 ** 2)), float(np.sqrt(a2 ** 2 + b2 ** 2))
        dC = float(C1 - C2)
        h1 = float(np.degrees(np.arctan2(b1, a1)) % 360.0)
        h2 = float(np.degrees(np.arctan2(b2, a2)) % 360.0)
        dh = ColorEvaluationManager.signed_hue_angle_difference(h1, h2)
        dH = float(2.0 * np.sqrt(max(C1 * C2, 0.0)) * np.sin(np.radians(dh / 2.0)))
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
            "ΔEab": delta_e_ab, "Δab plane": delta_ab_plane,
            "RGB1": rgb1, "RGB2": rgb2,
            "ΔR": dR, "ΔG": dG, "ΔB": dB,
            "|ΔR|": abs(dR), "|ΔG|": abs(dG), "|ΔB|": abs(dB),
            "RGB Euclidean": rgb_euclidean,
        }

    # ============================================================================================================================================================
    #  METRIC COMPUTATION
    # ============================================================================================================================================================
    @staticmethod
    def delta_e_ciede2000(lab1, lab2):
        L1, a1, b1 = lab1
        L2, a2, b2 = lab2
        C1, C2 = np.sqrt(a1 ** 2 + b1 ** 2), np.sqrt(a2 ** 2 + b2 ** 2)
        C_avg = (C1 + C2) / 2
        G = 0.5 * (1 - np.sqrt((C_avg ** 7) / (C_avg ** 7 + 25 ** 7)))
        a1p, a2p = (1 + G) * a1, (1 + G) * a2
        C1p, C2p = np.sqrt(a1p ** 2 + b1 ** 2), np.sqrt(a2p ** 2 + b2 ** 2)
        h1p, h2p = np.degrees(np.arctan2(b1, a1p)) % 360, np.degrees(np.arctan2(b2, a2p)) % 360
        dL, dC = L2 - L1, C2p - C1p
        dh = h2p - h1p
        if abs(dh) > 180:
            dh -= 360 * np.sign(dh)
        dH = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dh / 2))
        Lavg, Cavgp = (L1 + L2) / 2, (C1p + C2p) / 2
        if C1p * C2p == 0:
            Havg = h1p + h2p
        elif abs(h1p - h2p) > 180:
            Havg = (h1p + h2p + 360) / 2
        else:
            Havg = (h1p + h2p) / 2
        T = 1 - 0.17 * np.cos(np.radians(Havg - 30)) + 0.24 * np.cos(np.radians(2 * Havg)) + 0.32 * np.cos(np.radians(3 * Havg + 6)) - 0.20 * np.cos(np.radians(4 * Havg - 63))
        SL = 1 + ((0.015 * (Lavg - 50) ** 2) / np.sqrt(20 + (Lavg - 50) ** 2))
        SC = 1 + 0.045 * Cavgp
        SH = 1 + 0.015 * Cavgp * T
        dtheta = 30 * np.exp(-((Havg - 275) / 25) ** 2)
        RC = 2 * np.sqrt((Cavgp ** 7) / (Cavgp ** 7 + 25 ** 7))
        RT = -RC * np.sin(np.radians(2 * dtheta))
        return float(np.sqrt((dL / SL) ** 2 + (dC / SC) ** 2 + (dH / SH) ** 2 + RT * (dC / SC) * (dH / SH)))

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
        if metric == "CIE94 Graphic Arts":
            return float(cls.delta_e_cie94(sample_lab, prototype_lab, application="graphic arts"))
        if metric == "CIE94 Textiles":
            return float(cls.delta_e_cie94(sample_lab, prototype_lab, application="textiles"))
        if metric == "CMC l:c":
            return float(cls.delta_e_cmc(sample_lab, prototype_lab, lightness=2.0, chroma=1.0))
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
    def format_component_summary(cls, sample_lab, prototype_lab):
        c = cls.calculate_component_differences(sample_lab, prototype_lab)
        return (
            "Component breakdown:\n"
            f"ΔL* = {c['ΔL*']:+.3f} | Δa* = {c['Δa*']:+.3f} | Δb* = {c['Δb*']:+.3f}\n"
            f"ΔC* = {c['ΔC*']:+.3f} | Δh° = {c['Δh°']:+.3f}° | ΔH* = {c['ΔH*']:+.3f}\n"
            f"RGB Δ = ({c['ΔR']:+.0f}, {c['ΔG']:+.0f}, {c['ΔB']:+.0f})"
        )

    # ============================================================================================================================================================
    #  EVALUATION / CLASSIFICATION
    # ============================================================================================================================================================
    @classmethod
    def _classify_metric_value(cls, value, threshold_settings):
        if value is None:
            return {"status": "unavailable", "label": "Unavailable", "order": 9}
        settings = cls.normalize_threshold_settings(threshold_settings)
        mode = settings.get("mode", "default")

        if mode == "default":
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
            value = cls.calculate_metric_value(sample_lab, prototype_lab, metric)
            classification = cls._classify_metric_value(value, settings)
            detail = cls.format_metric_value(value, metric)
            summary = (
                f"{classification['label']} using {metric}.\n"
                f"{cls.format_component_summary(sample_lab, prototype_lab)}"
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

    # ============================================================================================================================================================
    #  COLOR SPACE / MEMBERSHIP / RANKING HELPERS
    # ============================================================================================================================================================
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
    def rank_closest_prototypes(cls, sample_lab, color_rows, metric="CIEDE2000", threshold_settings=None, top_n=7):
        settings = cls.normalize_threshold_settings(threshold_settings)
        metric = cls.normalize_metric_name(metric or settings.get("metric", "CIEDE2000"))
        ranking = []
        for label, proto_lab in color_rows:
            try:
                evaluation = cls.evaluate_color_difference_threshold(sample_lab, proto_lab, metric, settings)
                metric_value = evaluation.get("metric_value", evaluation.get("delta_e"))
                if metric_value is None:
                    continue
                ranking.append({
                    "label": label,
                    "delta_e": float(metric_value),       # kept for existing plots
                    "metric_value": float(metric_value),
                    "class_label": evaluation.get("class_label", "Unavailable"),
                    "class_order": evaluation.get("class_order", 9),
                    "status": evaluation.get("status", "unavailable"),
                    "detail": evaluation.get("detail", ""),
                })
            except Exception:
                continue
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

        rows = []

        for index, item in enumerate(ranking, start=1):
            label = _safe_text(item.get("label", "-"))
            metric_value = item.get("metric_value", item.get("delta_e"))
            metric_text = _format_value(metric_value, metric_name)
            status = _safe_text(item.get("class_label", item.get("status", "-")))

            rows.append({
                "index": index,
                "label": label,
                "metric_text": metric_text,
                "status": status,
            })

        # Dynamic widths
        index_w = max(len("#"), len(str(len(rows))))
        prototype_w = max(
            len("Prototype"),
            min(max(len(row["label"]) for row in rows), 26)
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

        title = f"{len(rows)} closest prototypes by {metric_name}:"

        header = (
            f"{'#':>{index_w}}  "
            f"{'Prototype':<{prototype_w}}  "
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

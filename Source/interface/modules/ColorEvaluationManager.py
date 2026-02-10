import os
import heapq
import numpy as np
import pandas as pd
from scipy.spatial import distance

### my libraries ###
from Source.geometry.Point import Point

"""
ColorEvaluationManager module

This module groups together utility routines used during *color volume evaluation* in PyFCS.
It supports:
- Creating CSV reports with per-volume LAB min/max limits.
- Exploring and filtering points inside Voronoi volumes using a ΔE00 (CIEDE2000) threshold,
  prioritizing points closest to each positive prototype.
- Computing color difference using the CIEDE2000 formula (ΔE00).

In short: it helps you sample valid LAB points within each prototype volume, summarize the
resulting ranges, and export those limits for analysis/reporting.
"""

class ColorEvaluationManager:
    """
    Handles color evaluation operations such as threshold filtering,
    CSV generation, and 3D visualization preparation.
    """

    def __init__(self, output_dir="test_results/Color_Evaluation"):
        # Output directory where evaluation artifacts (e.g., CSV files) will be saved
        self.output_dir = output_dir

        # Ensure the output directory exists
        os.makedirs(self.output_dir, exist_ok=True)

    def create_csv(self, file_base_name, volume_limits, mode=None):
        """
        Create a CSV file containing the min–max LAB limits for each volume.

        Parameters
        ----------
        file_base_name : str
            A base name used to build the CSV filename (only the basename is used).
        volume_limits : dict
            Dictionary mapping volume name/label -> {'L':(min,max), 'a':(min,max), 'b':(min,max)}.
            Values can be (None, None) if no points were found for that volume.
        mode : str or None
            Optional suffix to add to the filename (e.g., "strict", "loose", etc.).

        Returns
        -------
        str
            Full path to the saved CSV file.
        """
        csv_data = []

        # Build row-based data for the CSV
        for vol_name, limits in volume_limits.items():

            # Local formatter for "min - max" (or "-" if missing)
            def fmt(vmin, vmax):
                if vmin is None or vmax is None:
                    return "-"
                return f'"{vmin:.2f} - {vmax:.2f}"'

            # Append a row for this volume
            csv_data.append({
                "Volume": vol_name,
                "L*": fmt(limits["L"][0], limits["L"][1]),
                "a*": fmt(limits["a"][0], limits["a"][1]),
                "b*": fmt(limits["b"][0], limits["b"][1]),
            })

        # Convert to DataFrame for easy export
        df = pd.DataFrame(csv_data)

        # Optional suffix based on mode
        suffix = f"_{mode}" if mode else ""

        # Construct output filename and path
        csv_name = f"{os.path.basename(file_base_name)}_limits{suffix}.csv"
        csv_path = os.path.join(self.output_dir, csv_name)

        # Save as semicolon-separated CSV (common in some European locales)
        df.to_csv(csv_path, index=False, encoding="utf-8-sig", sep=";")
        print(f"✅ CSV saved: {csv_name}")

        return csv_path

    def filter_points_with_threshold(self, selected_volume, threshold, step):
        """
        Filter points inside Voronoi volumes using a ΔE00 threshold, prioritizing
        points closest to each prototype's positive center.

        The algorithm performs a best-first exploration (min-heap) that expands from
        the positive prototype in 6 orthogonal directions (±L, ±a, ±b), collecting
        points that:
          - are inside the Voronoi volume
          - have 0 < ΔE00 < threshold relative to the positive prototype

        It also computes per-volume min/max limits in L, a, b from the accepted points.

        Parameters
        ----------
        selected_volume : list
            List of prototype objects. Each prototype is expected to provide:
              - prototype.positive (LAB-like iterable)
              - prototype.label (name/label for reporting)
              - prototype.voronoi_volume.isInside(Point(...)) method
        threshold : float
            Maximum ΔE00 allowed for a point to be accepted.
        step : float
            Step size for exploring neighbor points in LAB space.

        Returns
        -------
        (dict, dict)
            filtered_points:
                dict mapping 'Volume_i' -> list of accepted LAB tuples (rounded to 2 decimals)
            volume_limits:
                dict mapping prototype.label -> {'L':(min,max), 'a':(min,max), 'b':(min,max)}
                If no points were accepted, each component is (None, None).
        """
        filtered_points = {}
        volume_limits = {}

        # Iterate each prototype / volume
        for idx, prototype in enumerate(selected_volume):
            positive = np.array(prototype.positive)

            # Accepted points for this volume
            points_within_threshold = []

            # Min-heap initialized at the positive prototype (rounded to avoid float drift)
            heap = [(0, tuple(np.round(positive, 2)))]

            # Track visited points to prevent re-processing
            visited = set()

            # Early-stop heuristic: stop after too many consecutive rejects
            consecutive_failures = 0
            max_failures = 10

            while heap:
                _, point = heapq.heappop(heap)

                # Skip already-visited nodes
                if point in visited:
                    continue
                visited.add(point)

                # Compute ΔE00 to the positive prototype
                delta_e = self.delta_e_ciede2000(positive, point)

                # Accept if inside volume and within threshold (excluding identical point)
                if 0 < delta_e < threshold and prototype.voronoi_volume.isInside(Point(*point)):
                    points_within_threshold.append(point)
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1

                # If we keep failing, stop exploring this volume
                if consecutive_failures > max_failures:
                    break

                # Expand in 6 orthogonal directions (± per axis)
                for axis in range(3):
                    for sign in (-1, 1):
                        neighbor = list(point)
                        neighbor[axis] = np.round(neighbor[axis] + sign * step, 2)
                        neighbor = tuple(neighbor)

                        # Only push neighbors that are still inside the volume
                        if prototype.voronoi_volume.isInside(Point(*neighbor)):
                            # Priority is Euclidean distance to positive -> explore closer points first
                            heapq.heappush(
                                heap,
                                (distance.euclidean(neighbor, positive), neighbor)
                            )

            # Store accepted points for this volume index
            filtered_points[f'Volume_{idx}'] = points_within_threshold

            # Compute min/max LAB limits if any points exist
            if points_within_threshold:
                pts = np.array(points_within_threshold)
                volume_limits[prototype.label] = {
                    'L': (np.min(pts[:, 0]), np.max(pts[:, 0])),
                    'a': (np.min(pts[:, 1]), np.max(pts[:, 1])),
                    'b': (np.min(pts[:, 2]), np.max(pts[:, 2])),
                }
            else:
                # No valid points found -> mark as missing
                volume_limits[prototype.label] = {
                    'L': (None, None),
                    'a': (None, None),
                    'b': (None, None),
                }

        return filtered_points, volume_limits

    @staticmethod
    def delta_e_ciede2000(lab1, lab2):
        """
        Compute the CIEDE2000 (ΔE00) color difference between two CIELAB colors.

        Parameters
        ----------
        lab1 : iterable
            (L, a, b) for the first color.
        lab2 : iterable
            (L, a, b) for the second color.

        Returns
        -------
        float
            The CIEDE2000 color difference (ΔE00).
        """
        L1, a1, b1 = lab1
        L2, a2, b2 = lab2

        # --- Step 1: Compute chroma C* and average chroma ---
        C1 = np.sqrt(a1**2 + b1**2)
        C2 = np.sqrt(a2**2 + b2**2)
        C_avg = (C1 + C2) / 2

        # --- Step 2: Compute G factor and adjusted a' values ---
        G = 0.5 * (1 - np.sqrt((C_avg**7) / (C_avg**7 + 25**7)))
        a1_prime = (1 + G) * a1
        a2_prime = (1 + G) * a2

        # --- Step 3: Compute adjusted chroma C' ---
        C1_prime = np.sqrt(a1_prime**2 + b1**2)
        C2_prime = np.sqrt(a2_prime**2 + b2**2)

        # --- Step 4: Compute hue angles h' (in degrees, normalized to [0, 360)) ---
        h1_prime = np.degrees(np.arctan2(b1, a1_prime)) % 360
        h2_prime = np.degrees(np.arctan2(b2, a2_prime)) % 360

        # --- Step 5: Compute ΔL' and ΔC' ---
        delta_L = L2 - L1
        delta_C = C2_prime - C1_prime

        # --- Step 6: Compute ΔH' via Δh ---
        delta_h = h2_prime - h1_prime
        if abs(delta_h) > 180:
            delta_h -= 360 * np.sign(delta_h)
        delta_H = 2 * np.sqrt(C1_prime * C2_prime) * np.sin(np.radians(delta_h / 2))

        # --- Step 7: Compute averages used by weighting functions ---
        L_avg = (L1 + L2) / 2
        C_avg_prime = (C1_prime + C2_prime) / 2

        # Average hue angle H_avg (careful with wrap-around)
        if C1_prime * C2_prime == 0:
            H_avg = h1_prime + h2_prime
        else:
            if abs(h1_prime - h2_prime) > 180:
                H_avg = (h1_prime + h2_prime + 360) / 2
            else:
                H_avg = (h1_prime + h2_prime) / 2

        # --- Step 8: Weighting function T ---
        T = (
            1
            - 0.17 * np.cos(np.radians(H_avg - 30))
            + 0.24 * np.cos(np.radians(2 * H_avg))
            + 0.32 * np.cos(np.radians(3 * H_avg + 6))
            - 0.20 * np.cos(np.radians(4 * H_avg - 63))
        )

        # --- Step 9: Compute SL, SC, SH ---
        SL = 1 + ((0.015 * (L_avg - 50) ** 2) / np.sqrt(20 + (L_avg - 50) ** 2))
        SC = 1 + 0.045 * C_avg_prime
        SH = 1 + 0.015 * C_avg_prime * T

        # --- Step 10: Rotation term RT ---
        delta_theta = 30 * np.exp(-((H_avg - 275) / 25) ** 2)
        RC = 2 * np.sqrt((C_avg_prime ** 7) / (C_avg_prime ** 7 + 25 ** 7))
        RT = -RC * np.sin(np.radians(2 * delta_theta))

        # --- Step 11: Final ΔE00 ---
        delta_E = np.sqrt(
            (delta_L / SL) ** 2 +
            (delta_C / SC) ** 2 +
            (delta_H / SH) ** 2 +
            RT * (delta_C / SC) * (delta_H / SH)
        )

        return delta_E

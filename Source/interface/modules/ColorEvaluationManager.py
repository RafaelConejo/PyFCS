import os
import heapq
import numpy as np
import pandas as pd
from scipy.spatial import distance

### my libraries ###
from Source.geometry.Point import Point

class ColorEvaluationManager:
    """
    Handles color evaluation operations such as threshold filtering,
    CSV generation, and 3D visualization preparation.
    """

    def __init__(self, output_dir="test_results/Color_Evaluation"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        
    
    def create_csv(self, file_base_name, volume_limits, mode=None):
        """
        Creates a CSV file containing the min–max limits for each volume.
        """
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


    def filter_points_with_threshold(self, selected_volume, threshold, step):
        """
        Filters points inside Voronoi volumes, prioritizing those closest 
        to the positive prototype. Returns both the filtered points and 
        the min–max limits for each volume.
        """
        filtered_points = {}
        volume_limits = {}

        for idx, prototype in enumerate(selected_volume):
            positive = np.array(prototype.positive)
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

                delta_e = self.delta_e_ciede2000(positive, point)
                if 0 < delta_e < threshold and prototype.voronoi_volume.isInside(Point(*point)):
                    points_within_threshold.append(point)
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1

                if consecutive_failures > max_failures:
                    break

                # Expand in 6 orthogonal directions
                for axis in range(3):
                    for sign in (-1, 1):
                        neighbor = list(point)
                        neighbor[axis] = np.round(neighbor[axis] + sign * step, 2)
                        neighbor = tuple(neighbor)
                        if prototype.voronoi_volume.isInside(Point(*neighbor)):
                            heapq.heappush(heap, (distance.euclidean(neighbor, positive), neighbor))

            filtered_points[f'Volume_{idx}'] = points_within_threshold

            # Compute limits if points exist
            if points_within_threshold:
                pts = np.array(points_within_threshold)
                volume_limits[prototype.label] = {
                    'L': (np.min(pts[:, 0]), np.max(pts[:, 0])),
                    'a': (np.min(pts[:, 1]), np.max(pts[:, 1])),
                    'b': (np.min(pts[:, 2]), np.max(pts[:, 2])),
                }
            else:
                volume_limits[prototype.label] = {
                    'L': (None, None),
                    'a': (None, None),
                    'b': (None, None),
                }

        return filtered_points, volume_limits


    @staticmethod
    def delta_e_ciede2000(lab1, lab2):
        """
        Implementation of the CIEDE2000 formula to calculate color difference 
        between two colors in the Lab color space.

        Parameters:
        - lab1: Tuple or list with (L, a, b) values for the first color.
        - lab2: Tuple or list with (L, a, b) values for the second color.

        Returns:
        - delta_E: The color difference according to CIEDE2000.
        """
        L1, a1, b1 = lab1
        L2, a2, b2 = lab2

        # Step 1: Compute C*
        C1 = np.sqrt(a1**2 + b1**2)
        C2 = np.sqrt(a2**2 + b2**2)
        
        # Average chroma
        C_avg = (C1 + C2) / 2
        
        # G factor
        G = 0.5 * (1 - np.sqrt((C_avg**7) / (C_avg**7 + 25**7)))
        
        # Adjusted a'
        a1_prime = (1 + G) * a1
        a2_prime = (1 + G) * a2

        # New C'
        C1_prime = np.sqrt(a1_prime**2 + b1**2)
        C2_prime = np.sqrt(a2_prime**2 + b2**2)

        # Step 2: Compute h'
        h1_prime = np.degrees(np.arctan2(b1, a1_prime)) % 360
        h2_prime = np.degrees(np.arctan2(b2, a2_prime)) % 360

        # Step 3: Color differences
        delta_L = L2 - L1
        delta_C = C2_prime - C1_prime

        # Compute delta_h
        delta_h = h2_prime - h1_prime
        if abs(delta_h) > 180:
            delta_h -= 360 * np.sign(delta_h)
        delta_H = 2 * np.sqrt(C1_prime * C2_prime) * np.sin(np.radians(delta_h / 2))

        # Averages for CIEDE2000
        L_avg = (L1 + L2) / 2
        C_avg_prime = (C1_prime + C2_prime) / 2

        # Compute H_avg
        if C1_prime * C2_prime == 0:
            H_avg = h1_prime + h2_prime
        else:
            if abs(h1_prime - h2_prime) > 180:
                H_avg = (h1_prime + h2_prime + 360) / 2
            else:
                H_avg = (h1_prime + h2_prime) / 2

        # Weighting functions
        T = (1 - 0.17 * np.cos(np.radians(H_avg - 30)) +
            0.24 * np.cos(np.radians(2 * H_avg)) +
            0.32 * np.cos(np.radians(3 * H_avg + 6)) -
            0.20 * np.cos(np.radians(4 * H_avg - 63)))

        # Adjustment factors SL, SC, SH
        SL = 1 + ((0.015 * (L_avg - 50) ** 2) / np.sqrt(20 + (L_avg - 50) ** 2))
        SC = 1 + 0.045 * C_avg_prime
        SH = 1 + 0.015 * C_avg_prime * T

        # Rotation factor
        delta_theta = 30 * np.exp(-((H_avg - 275) / 25) ** 2)
        RC = 2 * np.sqrt((C_avg_prime ** 7) / (C_avg_prime ** 7 + 25 ** 7))
        RT = -RC * np.sin(np.radians(2 * delta_theta))

        # Final Delta E 2000 calculation
        delta_E = np.sqrt(
            (delta_L / SL) ** 2 +
            (delta_C / SC) ** 2 +
            (delta_H / SH) ** 2 +
            RT * (delta_C / SC) * (delta_H / SH)
        )

        return delta_E


from skimage import color
import matplotlib.pyplot as plt
import math, numpy as np
from sklearn.cluster import DBSCAN
from PIL import Image

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
class ImageManager:
    def __init__(self, root=None, custom_warning=None, center_popup=None):
        """
        Args:
            root: Optional reference to the main application window.
            custom_warning: Optional callback to display custom warning dialogs/messages.
            center_popup: Optional callback to center popup windows on screen.
        """
        self.root = root
        self.custom_warning = custom_warning
        self.center_popup = center_popup

    # Simple utilities

    
    @staticmethod
    def _pil_to_rgb_uint8(image):
        """Return a uint8 RGB NumPy array from a PIL image, safely handling grayscale/RGBA images."""
        img_np = np.asarray(image)

        if img_np.ndim == 2:
            img_np = np.stack([img_np, img_np, img_np], axis=-1)
        elif img_np.shape[-1] == 4:
            img_np = img_np[..., :3]
        elif img_np.shape[-1] > 3:
            img_np = img_np[..., :3]

        return img_np.astype(np.uint8, copy=False)

    def _pil_to_lab_image(self, image):
        """Convert a PIL image to LAB using skimage, returning an H x W x 3 float array."""
        img_rgb = self._pil_to_rgb_uint8(image)
        img01 = img_rgb.astype(np.float32) / 255.0
        return color.rgb2lab(img01)

    def _unique_model_colors(self, image, fuzzy_color_space):
        """Quantize image colors once and return unique model-space values.

        Shared by single-prototype mapping and Mapping All, preventing the two
        paths from drifting in conversion or quantization behavior.
        """
        rgb_model = getattr(fuzzy_color_space, "color_space", "LAB") == "RGB"
        model_image = self._pil_to_rgb_uint8(image) if rgb_model else self._pil_to_lab_image(image)
        height, width = model_image.shape[:2]
        scale = 1.0 if rgb_model else 100.0
        source_space = "RGB" if rgb_model else "LAB"
        integer_colors = np.rint(model_image.reshape(-1, 3) * scale).astype(np.int32)
        uniq, inverse = np.unique(integer_colors, axis=0, return_inverse=True)
        return uniq, inverse, height, width, scale, source_space

    def get_proto_percentage(
        self,
        prototypes,
        image,
        fuzzy_color_space,
        selected_option,
        progress_callback=None,
        cancel_callback=None,
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

        if cancel_callback and cancel_callback():
            return None

        # Construct/evaluate directly in the space used by the loaded FCS.
        # RGB is encoded as 0..255 channel values; LAB is quantized to 0.01.
        uniq, inv, height, width, scale, source_space = self._unique_model_colors(
            image, fuzzy_color_space
        )

        values_for_uniq = np.empty((uniq.shape[0],), dtype=np.float32)
        total_uniqs = int(uniq.shape[0])

        for i in range(total_uniqs):
            if cancel_callback and cancel_callback():
                return None

            lab_tuple = tuple((uniq[i].astype(np.float32) / scale).tolist())
            value = fuzzy_color_space.calculate_membership_for_prototype(
                lab_tuple, selected_option, input_space=source_space
            )
            values_for_uniq[i] = np.clip(float(value), 0.0, 1.0)

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

        fuzzy_color_space.precompute_pack()

        # Construct/evaluate directly in the space used by the loaded FCS.
        # RGB is encoded as 0..255 channel values; LAB is quantized to 0.01.
        uniq, inv, height, width, scale, source_space = self._unique_model_colors(
            image, fuzzy_color_space
        )

        best_for_uniq = np.empty((uniq.shape[0],), dtype=np.int32)
        total_uniqs = int(uniq.shape[0])

        for i in range(total_uniqs):
            if cancel_callback and cancel_callback():
                return None

            lab_tuple = tuple((uniq[i].astype(np.float32) / scale).tolist())
            best_idx = fuzzy_color_space.best_prototype_index(lab_tuple, input_space=source_space)
            best_for_uniq[i] = int(best_idx) if best_idx is not None else -1

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
                pil_img = image.convert("RGBA") if "A" in image.getbands() else image.convert("RGB")
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

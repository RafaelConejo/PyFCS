from Source.input_output.Input import Input
from skimage import color
import numpy as np


class InputCNS(Input):

    def write_file(self, file_path):
        raise NotImplementedError(
            "InputCNS is read-only. Use InputFCS to export the edited color space as .fcs."
        )

    @staticmethod
    def is_number(value):
        try:
            float(value)
            return True
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _convert_to_lab(values, color_space):
        """
        Convert the complete prototype matrix to CIELAB once.

        Parameters
        ----------
        values : array-like, shape (N, 3)
            Original CNS prototype coordinates.

        color_space : str
            Color space declared by the CNS file.

        Returns
        -------
        np.ndarray, shape (N, 3)
            Prototype coordinates in CIELAB.
        """
        values = np.asarray(
            values,
            dtype=np.float64
        )

        if values.size == 0:
            return np.empty(
                (0, 3),
                dtype=np.float64
            )

        values = values.reshape(-1, 3)

        if str(color_space).upper() == "RGB":
            return np.asarray(
                color.rgb2lab(
                    values / 255.0
                ),
                dtype=np.float64
            )

        # LAB CNS files already contain the coordinates
        # required internally by PyFCS.
        return values.copy()

    def read_file(self, file_path):
        """
        Read a .cns crisp color space.

        All prototype coordinates are converted to CIELAB once.
        Voronoi construction works directly from the complete matrix of
        positive prototypes, so redundant per-color negative lists are no
        longer stored.
        """

        try:
            with open(
                file_path,
                "r",
                encoding="utf-8"
            ) as file:
                lines = file.readlines()

            start_index = None
            color_space = None

            # ---------------------------------------------------------
            # Locate color-space declaration
            # ---------------------------------------------------------

            for i, line in enumerate(lines):
                stripped = line.strip()

                if "@colorSpace_" in stripped:
                    start_index = i
                    color_space = (
                        stripped
                        .split("_", 1)[1]
                        .strip()
                    )
                    break

            # Legacy CNS format
            if color_space is None:
                color_space = "RGB"

                for i, line in enumerate(lines):
                    stripped = line.strip()

                    if not stripped or stripped.startswith("#"):
                        continue

                    if "@crispColorSpaceType" in stripped:
                        start_index = i
                        break

            if start_index is None:
                raise ValueError(
                    "Could not locate color space definition in the .cns file."
                )

            # ---------------------------------------------------------
            # Header
            # ---------------------------------------------------------

            try:
                num_components = int(
                    lines[start_index + 1].strip()
                )

                num_cases = int(
                    lines[start_index + 2].strip()
                )

            except (IndexError, ValueError) as exc:
                raise ValueError(
                    "Invalid CNS header."
                ) from exc

            if num_components != 3:
                raise ValueError(
                    f"PyFCS requires 3 color components, "
                    f"but the CNS file declares {num_components}."
                )

            # ---------------------------------------------------------
            # Parse coordinates and names
            # ---------------------------------------------------------

            raw_colors = []
            color_names = []

            unique_lines = set()

            for line_number in range(
                start_index + 3,
                len(lines)
            ):
                line_content = lines[
                    line_number
                ].strip()

                if not line_content:
                    continue

                # Preserve current PyFCS behaviour:
                # repeated identical CNS lines are ignored.
                if line_content in unique_lines:
                    continue

                unique_lines.add(line_content)

                parts = line_content.split()

                is_coordinate = (
                    len(parts) == num_components
                    and all(
                        self.is_number(value)
                        for value in parts
                    )
                )

                if is_coordinate:
                    raw_colors.append(
                        [
                            float(parts[0]),
                            float(parts[1]),
                            float(parts[2]),
                        ]
                    )

                else:
                    name = line_content

                    if (
                        len(name) >= 2
                        and (
                            (
                                name.startswith('"')
                                and name.endswith('"')
                            )
                            or
                            (
                                name.startswith("'")
                                and name.endswith("'")
                            )
                        )
                    ):
                        name = name[1:-1]

                    color_names.append(name)

            # ---------------------------------------------------------
            # Validation
            # ---------------------------------------------------------

            if len(raw_colors) != len(color_names):
                raise ValueError(
                    "Mismatch between the number of color values "
                    "and color names."
                )

            if num_cases != len(raw_colors):
                raise ValueError(
                    f"The CNS header declares {num_cases} colors, "
                    f"but {len(raw_colors)} valid colors were found."
                )

            if not raw_colors:
                return {}

            # ---------------------------------------------------------
            # Convert ALL colors to LAB only once
            # ---------------------------------------------------------

            raw_matrix = np.asarray(
                raw_colors,
                dtype=np.float64
            )

            lab_matrix = self._convert_to_lab(
                raw_matrix,
                color_space
            )

            # ---------------------------------------------------------
            # Build PyFCS structure
            # ---------------------------------------------------------

            color_data = {}

            for i, color_name in enumerate(color_names):
                color_data[color_name] = {
                    "Color": raw_matrix[i].tolist(),
                    "positive_prototype": lab_matrix[i].copy(),
                }

            return color_data

        except (
            ValueError,
            IndexError,
            KeyError
        ) as exc:
            raise ValueError(
                f"Error reading .cns file: {exc}"
            ) from exc
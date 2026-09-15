import numpy as np

from Source.geometry.Voronoi import Voronoi


class Prototype:
    """
    Crisp prototype plus its already-built Voronoi volume.

    In the normal PyFCS path, Voronoi.build_diagram() constructs every cell in
    one coordinated operation and injects the resulting Volume here.  The
    ``competitors`` argument is kept only for isolated/specialized construction
    of a single Prototype.
    """

    def __init__(self, label, positive, voronoi_volume=None, competitors=None):
        self.label = label
        self.positive = np.asarray(positive, dtype=float)

        if voronoi_volume is not None:
            self.voronoi_volume = voronoi_volume
            return

        if competitors is None:
            raise ValueError(
                "Prototype requires either a precomputed voronoi_volume "
                "or competitor prototypes."
            )

        self.voronoi_volume = Voronoi.build_cell(
            positive=self.positive,
            negatives=competitors,
        )

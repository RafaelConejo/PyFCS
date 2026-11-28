# Interface modules

The interface is grouped by responsibility. The folders are Python packages; their `__init__.py` files do not eagerly import managers.

| Package | Responsibility |
| --- | --- |
| [creation](creation/README.md) | Create fuzzy color spaces from palettes, images and construction options. |
| [data](data/README.md) | Edit and validate categories, granules, prototypes and hierarchies. |
| [image](image/README.md) | Image preparation, mapping computation, inspection and full-resolution processing. |
| [evaluation](evaluation/README.md) | Individual color evaluation, membership and color-difference analysis. |
| [visualization](visualization/README.md) | Geometric and chromatic visualization. |
| [common](common/README.md) | Shared utilities, dialogs and resource paths. |

Use explicit package imports, for example:

```python
from Source.interface.modules.image.ColorProcessingEngine import ColorProcessingEngine
from Source.interface.modules.visualization.VisualManager import VisualManager
from Source.interface.modules.common import UtilsTools
```


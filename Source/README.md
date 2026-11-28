# Image processing and analysis

This package contains the shared computational engine and dedicated image workspaces.

| File | Responsibility |
| --- | --- |
| `ColorProcessingEngine.py` | Image preprocessing and quantization; bounded LRU preparation cache; scalar and optional Numba batch evaluation; adaptive backend selection; membership and category/granule label maps; General/Detailed mapping helpers. |
| `ImageDisplayManager.py` | Desktop image canvas and cards, open/save/close, Grid/Focus/manual layout, zoom/pan, original-image pixel and ROI sampling, and full-resolution workspace lifecycle. |
| `ColorMappingManager.py` | Desktop Color Mapping and Mapping All, General/Detailed selectors and legends, grayscale/color and palette rendering, cancellation/progress, result caches, original-view restoration and operator refresh. |
| `ImageInspectionManager.py` | Pixel and ROI inspection, membership displays, selected/reference color comparison and image analysis UI. |
| `ImageWorkspaceManager.py` | Full-resolution image workspace, tiled mapping, ROI handling, visualization and export. |

`ColorProcessingEngine.py` is the shared computation service. Keep the existing scalar fallback and numerical safeguards for the optional compiled backend. `ColorMappingManager` owns per-card mapping state, while `ImageDisplayManager` owns the original images, canvas and viewport state. The application owns the active fuzzy model and coordinates shared readouts and application-wide task exclusion. Legacy application methods and attributes forward to their respective controllers, so consumers share the same dictionaries and widgets without duplicate image or result storage.

The full-resolution workspace remains a separate controller and continues to use the existing processing engine. The refactor does not alter membership calculation, label-map generation or the cache policy.

# Image processing and analysis

This package contains the shared computational engine and dedicated image workspaces.

| File | Responsibility |
| --- | --- |
| `ColorProcessingEngine.py` | Image preprocessing and quantization; bounded LRU preparation cache; scalar and optional Numba batch evaluation; adaptive backend selection; membership and category/granule label maps; General/Detailed mapping helpers. |
| `ImageDisplayManager.py` | Desktop image canvas and cards, open/save/close, Grid/Focus/manual layout, zoom/pan, original-image pixel and ROI sampling, and full-resolution workspace lifecycle. |
| `ColorMappingManager.py` | Desktop Color Mapping and Mapping All, General/Detailed selectors and legends, grayscale/color and palette rendering, cancellation/progress, result caches, original-view restoration and operator refresh. |
| `ImageInspectionManager.py` | Pixel and ROI inspection, membership displays, selected/reference color comparison and image analysis UI. |
| `ImageWorkspaceManager.py` | Full-resolution image workspace, tiled mapping, ROI handling, visualization and export. |
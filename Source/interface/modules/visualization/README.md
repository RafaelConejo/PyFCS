# Visualization

The visualization package separates the desktop controller from the renderer.

- `Model3DManager.py`: owns the Tkinter Model 3D tab, layer controls (Representative, Core, 0.5-cut and Support), semantic category/granule selection, search, camera state and orientation marker, background surface preparation, PT/AT overlays and the Interactive View action. It receives the application instance and uses its active fuzzy color space, shared T-conorm controls, dialogs and browser-export service. It does not construct or redefine membership geometry.
- `VisualManager.py`: rendering and plotting utilities for fuzzy color spaces, prototypes and volumes, including geometric projection, clipping, cached surfaces, Matplotlib collections and Plotly figures/HTML.
# PyFCS desktop interface

This package contains the Tkinter desktop application. It uses the scientific library in `Source/colorspace`, `Source/geometry`, `Source/fuzzy`, `Source/membership` and `Source/input_output` without changing the mathematical definitions of fuzzy colors.

- `mainInterface.py`: application entry point (`start_up`) and `PyFCSApp`; main window, menus, shared state and orchestration of the managers. Model 3D is owned by `modules/visualization/Model3DManager.py`; the Image Display workspace is owned by `modules/image/ImageDisplayManager.py`; desktop mapping is owned by `modules/image/ColorMappingManager.py`; the Color Evaluation window is owned by `modules/evaluation/ColorEvaluationWindow.py`.
- `modules/`: feature-specific managers and shared services; see its [README](modules/README.md).

From the project root:

```bash
python -m Source.interface.mainInterface
python -m Source.test.run_full_suite --gui
```
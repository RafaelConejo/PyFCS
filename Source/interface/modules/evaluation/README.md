# Color evaluation

`ColorEvaluationManager.py` contains color evaluation and comparison logic: membership snapshots and ranking, nearest granule selection, color-difference calculations and perceptual/acceptability threshold analysis. It is also used by image inspection and the dental research scripts.

`ColorEvaluationWindow.py` owns the Tkinter Color Evaluation window, comparison controls, sample history, custom color selection, image sampling and plots. It uses the existing numerical manager and application services; it does not implement a second membership algorithm.
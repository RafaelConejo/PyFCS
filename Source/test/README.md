# PyFCS test suite

Run commands from the project root (the directory containing `Source`).

## Global regression suite

```bash
python -m Source.test.run_full_suite
python -m Source.test.run_full_suite --gui
```

The runner discovers `test_*.py` recursively, including the small automated
regression tests inside the case packages. It does **not** run full research
experiments, interactive tools or the 10-million-sample Java comparison.
`--gui` requires a graphical display. Global logs and JSON reports are saved
in `Source/test/reports/` by default.

- `test_global_workflows.py`: integration tests for construction, FCS I/O,
  native RGB processing, color-space rebuilds, visualization and metrics.
- `test_core_regressions.py`: general stability tests from the pre-Java audit
  (hierarchies, JSON, 3D geometry, clipping and visualization).

## Specific cases

### `cases/java_comparison/`

- `compare_java_evaluations.py`: compares external Java memberships against
  an independently built PyFCS JSON model; supports streaming and fast/scalar
  evaluation. The data directory is still `<project>/fuzzy_color_spaces/test/`.
- `compare_fcs_engines.py`: legacy FCS geometry comparison; both geometries
  are evaluated by PyFCS, not by the Java evaluator. Reference FCS pairs are
  in `fixtures/` and its reports are in `reports/`.
- `test_java_evaluation_tools.py` and `test_comparison_tool.py`: regression tests.

```bash
python -m Source.test.cases.java_comparison.compare_java_evaluations --limit 10000
python -m Source.test.cases.java_comparison.compare_java_evaluations
python -m Source.test.cases.java_comparison.compare_fcs_engines --demo
python -m unittest discover -s Source/test/cases/java_comparison -t . -v
```

The evaluation script expects `evaluation_basic_granular_complete.json` and
`basic_granular_complete_PyFCS.json` in `fuzzy_color_spaces/test/` by default,
and writes `comparison_results/` there. Numba is needed for fast evaluation.
The large Java evaluation file is not part of this test-folder archive.

### `cases/vita_thresholds/`

- `threshold_paper_analysis.py`: primary VITA PT/AT analysis and resumable BFS.
- `generate_threshold_method_figures.py`: methodological figures using real geometry.
- `generate_results_figures.py`: publication results figures.
- `pyfcs_shade_region_schematic.py`: conceptual illustration, not an experiment.
- `test_threshold_paper_analysis.py`: automated synthetic-model regressions.
- `paper_thresholds_vita_max_delta005/`: original results, figures, tables and
  `_completed_grids/` checkpoints. Existing files are preserved byte-for-byte.
  The scripts now use this relocated folder as their default results directory.
  Historical metadata and reports retain their original recorded paths.

```bash
python -m Source.test.cases.vita_thresholds.threshold_paper_analysis
python -m Source.test.cases.vita_thresholds.generate_threshold_method_figures
python -m Source.test.cases.vita_thresholds.generate_results_figures
python -m Source.test.cases.vita_thresholds.pyfcs_shade_region_schematic
python -m unittest Source.test.cases.vita_thresholds.test_threshold_paper_analysis -v
```

The default study model remains `fuzzy_color_spaces/vita_no_covering_max.json`.
These experiments can be expensive; run them explicitly when needed.

### `cases/vita_images_legacy/`

Historical manual dental image tools: vertical-third analysis (`vita_get_third`),
white-intensity membership maps (`vita_per_B&W.py`), recoloring a single image
(`vita_recolor`) and batch recoloring with legends (`vita_recolor_all`).
Their project-root import bootstrap was adjusted; their older data paths,
algorithms and interactive workflows were otherwise preserved. They were not
validated or migrated to the new hierarchical image-processing API.

### `cases/manual_color/`

`color_percentage.py`: interactive LAB input/pixel sampling and membership
inspection, separate from automated tests. Legacy paths and algorithms retained.

## Migration

Replace the previous `Source/test/` directory, rather than overlaying it:
otherwise the moved modules may remain as stale duplicates. Back up any files
added locally since the supplied archive before replacing. The archive only
contains `test/`; application code and `fuzzy_color_spaces/` are not modified.
The previous audit's corrected global workflow test and missing eight core
regression tests were restored from the previously delivered patch.

# Common interface utilities

`UtilsTools.py` contains shared helpers for resource and writable-data paths, color conversions, names and prototype validation, common widgets, dialogs, creation settings and image/UI support.

- `get_base_path()`: project root during source execution; executable directory in a frozen build.
- `get_resource_path()`: source resources or frozen external/bundled resources (external override first).
- `get_runtime_temp_dir()`: writable runtime storage, separate from bundled read-only resources.


# Fuzzy color space creation

This package manages the application workflows for creating fuzzy color spaces. Actual geometric construction is delegated to the scientific model and I/O modules.

| File | Responsibility |
| --- | --- |
| `FuzzyColorSpaceManager.py` | Coordinates construction and saving of fuzzy spaces using the available creation options and progress callbacks. |
| `PaletteBasedCreationManager.py` | Palette-based creation UI, color selection and editing, imported color lists, category/group organization and construction options. |
| `ImageBasedCreationManager.py` | Image-based selection of representative colors and creation of spaces; shares creation helpers with the palette workflow. |
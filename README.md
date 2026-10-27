# PyFCS — Python Fuzzy Color Software

**PyFCS** is an open-source Python framework and desktop application for the **creation, visualization, analysis, and application of Fuzzy Color Spaces (FCS)**.

Instead of assigning colors to rigid categories, PyFCS models color terms as fuzzy sets in **CIELAB space**, allowing gradual transitions between neighboring color categories and providing membership degrees that better reflect perceptual ambiguity.

PyFCS builds on previous work developed in the Java **JFCS** library and combines fuzzy logic, conceptual spaces, computational geometry, image processing, and interactive visualization in a single Python environment.


---

## Overview

PyFCS can be used to:

- create fuzzy color spaces from reference palettes or image data;
- load and edit existing `.fcs` and `.cns` color spaces;
- visualize fuzzy-color geometry in 3D;
- inspect pixels and image regions in CIELAB space;
- compute fuzzy membership degrees;
- apply single-color and full-image fuzzy color mappings;
- evaluate color differences using configurable metrics and thresholds;
- export processed images and mapping legends;
- work interactively with multiple images in the same workspace.

The graphical interface is designed for **Windows, Linux, and macOS** when executed from source. A standalone **Windows one-file executable** can also be generated with PyInstaller.

---

## Main Features

### Fuzzy Color Space Creation

PyFCS provides two complementary creation workflows.

#### Palette-Based Creation

Build a new FCS from:

- the default **ISCC-NBS Basic** palette;
- additional `.cns` palettes;
- representative colors imported from existing `.fcs` files;
- manually defined custom colors.

The creation workspace supports:

- accumulation of multiple color sources;
- editable color names;
- RGB, HEX, and CIELAB visualization;
- search and selection tools;
- duplicate source detection;
- automatic disambiguation of repeated labels;
- protection against coincident CIELAB prototypes before Voronoi construction.

#### Image-Based Creation

Create a fuzzy color space directly from images using:

- single-pixel sampling;
- rectangular ROI sampling;
- automatic color detection;
- optional **LAB Filters**;
- custom colors;
- editable detected-color names.

Images can come from the main PyFCS workspace or can be opened locally for the creation session.

---

## Image Display Workspace

Each loaded image is displayed as an independent card with:

- **Grid** layout for automatic organization;
- **Focus** mode for detailed inspection;
- manual drag and resize;
- minimize and close controls;
- mouse-wheel zoom centered on the cursor;
- right-drag / middle-drag panning while zoomed;
- viewport-aware pixel and ROI coordinates.

The workspace keeps image interaction consistent even after resizing, zooming, Grid/Focus transitions, or scrolling.

---

## Color Mapping

### Single Color Mapping

Select one fuzzy prototype and visualize its membership distribution across the image.

PyFCS also reports the percentage associated with the selected mapping.

### Color Mapping All

Each valid image pixel is assigned to the fuzzy prototype with the highest membership degree for visualization. However, the complete membership distribution across all fuzzy prototypes is preserved for every pixel, allowing the full fuzzy information to be inspected and analyzed.

The mapped image includes an integrated legend and supports switching between visualization palettes using **Alt. Colors**.

When exported, Mapping All produces:

```text
result.png
result_legend.png
```

The legend always corresponds to the palette currently shown in the interface.

---

## Image Inspection

**Image Inspection** provides a dedicated workspace for detailed image analysis against the active fuzzy color space.

It supports:

- pixel inspection;
- ROI mean-color inspection;
- Inspect and Live interaction modes;
- CIELAB, RGB, and HEX information;
- fuzzy membership distributions;
- automatic identification of the **Close Prototype**;
- configurable color-difference comparison;
- pinned samples for later restoration and comparison;
- independent zoom and viewport state for each image.

Local temporary images can be opened directly in Image Inspection without adding them to the main Image Display.

---

## Color Difference Evaluation

PyFCS includes a dedicated module for quantitative color comparison.

Available workflows include:

- prototype vs. prototype;
- prototype vs. custom color;
- prototype vs. image sample;
- closest-prototype ranking;
- membership analysis;
- graphical comparison tools.

Supported metric families include perceptual and component-based color differences, with configurable threshold modes.

The default perceptual workflow uses **CIEDE2000**.

PyFCS also provides visualization of:

- **PT — Perceptibility Threshold**
- **AT — Acceptability Threshold**

Generated threshold CSV files are stored as runtime output rather than as repository data.

---

## 3D Visualization

The active fuzzy color space can be explored in CIELAB coordinates using:

- Representative colors;
- Core regions;
- `0.5-cut` volumes;
- Support regions.

Individual colors can be selected independently or displayed together.

An **Interactive Figure** can also be opened for free rotation, zoom, and closer inspection.

---

## Data Editing

The **Data** tab provides editable access to the active FCS.

Users can:

- rename colors;
- inspect representative values;
- add new colors;
- delete colors;
- apply changes directly to the current `.fcs`.

Changes rebuild the fuzzy geometry and invalidate incompatible image-mapping caches so that new mappings are always recomputed from the original image.

---

## Screenshots

A complete illustrated guide is available in the [`PyFCS_GUI_Manual`](PyFCS_GUI_Manual/) directory.

The manual documents the interface step by step, including:

- every toolbar action;
- Palette-Based Creation;
- Image-Based Creation;
- LAB Filters;
- Model 3D;
- Data editing;
- Grid and Focus;
- Color Mapping;
- Image Inspection;
- Color Evaluation;
- threshold visualization;
- image export.

---

# Installation

## Option 1 — Windows Standalone Executable

For normal Windows use, the simplest option is the standalone release executable.

1. Open the **Releases** section of the repository.
2. Download `PyFCS.exe`.
3. Run the executable.

The current one-file build embeds the required GUI icons and the default ISCC-NBS Basic palette, so `Source/` and `fuzzy_color_spaces/` do not need to be distributed next to the executable.

Runtime files such as temporary plots and threshold CSV files are created in the system temporary directory.

---

## Option 2 — Run from Source

### Requirements

- Python **3.9 or newer**
- Python **3.10 recommended**
- `pip`
- Tkinter support
- project dependencies listed in:

```text
Source/external/requirements.txt
```

Clone the repository:

```bash
git clone https://github.com/RafaelConejo/PyFCS.git
cd PyFCS
```

Install the dependencies:

```bash
pip install -r Source/external/requirements.txt
```

Launch PyFCS:

```bash
python Source/interface/mainInterface.py
```

---

## Windows

From PowerShell, CMD, Anaconda Prompt, or another configured Python environment:

```bat
pip install -r Source\external\requirements.txt
python Source\interface\mainInterface.py
```

---

## Linux

If the repository includes the Linux setup helper:

```bash
chmod +x Source/external/setup_pyfcs_linux.sh
Source/external/setup_pyfcs_linux.sh
```

Alternatively, install the dependencies manually and run:

```bash
pip install -r Source/external/requirements.txt
python Source/interface/mainInterface.py
```

Depending on the Linux distribution, Tkinter may need to be installed through the system package manager.

---

## macOS

If the repository includes the macOS setup helper:

```bash
chmod +x Source/external/setup_pyfcs_mac.sh
Source/external/setup_pyfcs_mac.sh
```

Alternatively:

```bash
pip install -r Source/external/requirements.txt
python Source/interface/mainInterface.py
```

A Python distribution with working Tk support is required.

> PyInstaller applications must be built on the target operating system. A Windows `.exe` cannot be used as a native macOS application; macOS builds should be generated on macOS.

---

# Building the Windows Executable

The repository includes [`PyFCS.spec`](PyFCS.spec), which defines the official one-file PyInstaller build.

Activate the desired build environment and run from the repository root:

```bat
pyinstaller --noconfirm --clean PyFCS.spec
```

The executable is generated at:

```text
dist/
└── PyFCS.exe
```

The build embeds:

```text
Source/external/icons/
fuzzy_color_spaces/cns/ISCC_NBS_BASIC.cns
```

The resulting executable can therefore be tested in an otherwise empty folder.

### Resource resolution

PyFCS supports both source execution and frozen applications:

- when running from source, resources are loaded from the repository;
- when frozen, embedded resources are loaded from the PyInstaller bundle;
- optional external resources can still override embedded ones when present.

This keeps local development convenient while allowing standalone distribution.

---

# Runtime Files

Generated runtime files are intentionally kept outside the tracked project data.

When running from source:

```text
Source/external/temp/
├── plots/
└── threshold_results/
```

When running as a one-file executable, equivalent temporary directories are created inside the operating system temporary folder.

These files are not required to run PyFCS and should not be committed to the repository.

---

# Repository Structure

A simplified repository layout is:

```text
PyFCS/
├── Source/
│   ├── colorspace/
│   ├── fuzzy/
│   ├── geometry/
│   ├── input_output/
│   ├── interface/
│   │   ├── mainInterface.py
│   │   └── modules/
│   └── external/
│       ├── icons/
│       └── requirements.txt
│
├── fuzzy_color_spaces/
│   └── cns/
│       └── ISCC_NBS_BASIC.cns
│
├── image_test/
├── PyFCS_GUI_Manual/
├── PyFCS.spec
├── LICENSE.txt
└── README.md
```

---

# Main GUI Modules

The desktop interface is organized through specialized managers:

```text
ImageManager
FuzzyColorSpaceManager
ColorEvaluationManager
ImageInspectionManager
ImageBasedCreationManager
PaletteBasedCreationManager
VisualManager
```

`mainInterface.py` coordinates the application while the managers isolate image processing, creation workflows, evaluation, inspection, and visualization responsibilities.

---

# Supported Color-Space Files

PyFCS supports:

### `.cns`

Color Name System / palette data.

A `.cns` file can be:

- loaded into the main application;
- used as a source in Palette-Based Creation.

### `.fcs`

Complete PyFCS Fuzzy Color Space.

An `.fcs` file stores the data required to reconstruct the fuzzy color model, including representative colors and fuzzy geometric information.

---

# Typical Workflow

A common PyFCS workflow is:

1. **Load or create a Fuzzy Color Space**
2. **Inspect it in Model 3D**
3. **Edit representatives if necessary**
4. **Open one or more images**
5. **Use Grid or Focus to organize the workspace**
6. **Inspect pixels or ROIs**
7. **Apply Color Mapping or Color Mapping All**
8. **Use Image Inspection for detailed membership analysis**
9. **Run Color Evaluation when quantitative comparison is required**
10. **Export the resulting images and legends**

---

# Documentation

A detailed user manual is maintained in:

```text
PyFCS_GUI_Manual/
```

It includes theoretical background, installation notes, interface descriptions, screenshots, and step-by-step workflows.

---

# License

See [`LICENSE.txt`](LICENSE.txt) for the license terms of the project.

---

# Author

**Rafael Vázquez Conejo**

PyFCS is developed as an open-source scientific tool for fuzzy color modeling, color analysis, and image-based applications.

---

# Contact

For questions, technical support, or research-related contact:

**rafaconejo@ugr.es**

Project repository:

https://github.com/RafaelConejo/PyFCS

# PyFCS: A Python library to create and manipulate Fuzzy Color Spaces
PyFCS is a Python library that introduces fuzzy color spaces for a more realistic and flexible representation of color, overcoming the limitations of traditional methods. It is based on the previous work of the Java library JFCS and utilizes fuzzy logic and conceptual space theory, leveraging Python's strengths for data and image analysis.


## PyFCS GUI
**PyFCS GUI** is a graphical user interface developed as an extension of the open-source PyFCS library. It enables the creation, visualization, and application of fuzzy color spaces derived from either color palettes or image data. This tool combines interactive 3D exploration, advanced color mapping, and reusable export features, making it useful for perceptual analysis, artistic exploration, and scientific research.

The GUI enhances usability by offering a practical way to apply fuzzy color models, grounded in fuzzy logic and conceptual space theory, building upon previous developments like the JFCS Java library.

A detailed manual explaining all options, functionalities, and usage fundamentals of the interface is available in the **PyFCS_GUI_Manual** directory.

### 🔧 How to Use

If no modifications to the source code are needed, follow these steps for a quick installation:

#### 📦 1. Download the Project

Access the project repository on GitHub and download the library using the **"Clone or Download"** button, or from the **Releases** section by downloading the `.zip` file.

Extract the contents of the `.zip` file to a preferred local folder.

#### 🐍 2. Make Sure Python is Installed

Ensure you have **Python 3.9 or higher** installed, along with **pip**. You can also use a virtual environment manager like [Anaconda](https://www.anaconda.com/).

If `pip` is not available, you can install it manually with:

  ```bash
  python -m ensurepip --upgrade
  ```

#### </> 3. Open a terminal, navigate to the root directory of the project, and install the required dependencies:

  - **🪟 Windows**
    ```bash
    pip install -r PyFCS\external\requirements.txt

    # Once the dependencies are installed, launch the main interface structure by executing:
    python PyFCS\visualization\basic_structure.py
    ```

  - **🐧 Linux**
    ```bash
    python3 -m venv venv_pyfcs
    source venv_pyfcs/bin/activate
    python3 -m pip install -r PyFCS/external/requirements.txt

    # Install system dependencies (required manually)
    sudo apt install python3.12-tk
    python3 -m pip install PyQtWebEngine

    # Launch the interface
    python3 PyFCS/visualization/basic_structure.py
    ```

    These steps ensure full compatibility with features such as Tkinter-based dialogs and enhanced Qt-based rendering on Linux systems.

  - **🍎 macOS**
    ```bash
    python3 -m venv venv_pyfcs
    source venv_pyfcs/bin/activate
    python3 -m pip install -r PyFCS/external/requirements.txt

    # (If needed) Install Tkinter via Homebrew
    brew install python-tk

    # Launch the interface
    python3 PyFCS/visualization/basic_structure.py
    ```



---

### 📬 Contact & Support
For support or questions, feel free to contact: rafaconejo@ugr.es

# PyFCS: A Python library to create and manipulate Fuzzy Color Spaces
PyFCS is a Python library that introduces fuzzy color spaces for a more realistic and flexible representation of color, overcoming the limitations of traditional methods. It is based on the previous work of the Java library JFCS and utilizes fuzzy logic and conceptual space theory, leveraging Python's strengths for data and image analysis.

### How to use (CLI Mode)
If no modifications to the source code are needed, follow these steps for a quick installation:

1. Access the project repository on GitHub and download the library using the \textbf{"Clone or Download"} option, or from the releases section by downloading the \texttt{.zip} file.
2. Extract the contents of the \texttt{.zip} file to a preferred local folder.
3. Open a terminal (CMD or PowerShell), navigate to the project’s root directory, and run the following command to install the required dependencies:
```
pip install -r PyFCS\external\requirements.txt
```
4. Now it's possible to use one of the different test programs located in the test directory. Here's an example of usage, _color_percentage_ is just an example of the test programs; it can be run with all the files present in that test directory:
```
python PyFCS\test\color_percentage.py
```


## PyFCS GUI
**PyFCS GUI** is a graphical user interface developed as an extension of the open-source PyFCS library. It enables the creation, visualization, and application of fuzzy color spaces derived from either color palettes or image data. This tool combines interactive 3D exploration, advanced color mapping, and reusable export features, making it useful for perceptual analysis, artistic exploration, and scientific research.

The GUI enhances usability by offering a practical way to apply fuzzy color models, grounded in fuzzy logic and conceptual space theory, building upon previous developments like the JFCS Java library.

A detailed manual explaining all options, functionalities, and usage fundamentals of the interface is available in the **PyFCS_GUI_Manual** directory.

### 🔧 How to Use
If no modifications to the source code are needed, follow these steps for a quick installation on **Windows**:

1. Access the project repository on GitHub and download the library using the **"Clone or Download"** button, or from the **Releases** section by downloading the `.zip` file.
2. Extract the contents of the `.zip` file to a preferred local folder.
3. Make sure you have **Python 3.9 or higher** installed, along with **pip** (or use an environment manager like [Anaconda](https://www.anaconda.com/)).
   - To install pip manually (if not already available), you can run:
     ```bash
     python -m ensurepip --upgrade
     ```
4. Open a terminal (CMD or PowerShell), navigate to the root directory of the project, and install the required dependencies:
   ```bash
   pip install -r PyFCS\external\requirements.txt
   ```
5. Once the dependencies are installed, launch the main interface structure by executing:
    ```bash
    python PyFCS\visualization\basic_structure.py
    ```

###🐧 Additional Notes for Linux Users
If you're using Linux, make sure to install system-level dependencies required by the GUI before running the program. These are not Python packages and must be installed separately:
   ```bash
   sudo apt update
   sudo apt install python3.12-tk
   pip install PyQtWebEngine
   ```
These steps ensure full compatibility with features such as Tkinter-based dialogs and enhanced Qt-based rendering on Linux systems.

---

### 📬 Contact & Support
For support or questions, feel free to contact: rafaconejo@ugr.es

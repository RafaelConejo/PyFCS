# PyFCS: A Python library to create and manipulate Fuzzy Color Spaces
PyFCS is a Python library that introduces fuzzy color spaces for a more realistic and flexible representation of color, overcoming the limitations of traditional methods. It is based on the previous work of the Java library JFCS and utilizes fuzzy logic and conceptual space theory, leveraging Python's strengths for data and image analysis.


## PyFCS GUI
**PyFCS GUI** is a graphical user interface developed as an extension of the open-source PyFCS library. It enables the creation, visualization, and application of fuzzy color spaces derived from either color palettes or image data. This tool combines interactive 3D exploration, advanced color mapping, and reusable export features, making it useful for perceptual analysis, artistic exploration, and scientific research.

The GUI enhances usability by offering a practical way to apply fuzzy color models, grounded in fuzzy logic and conceptual space theory, building upon previous developments like the JFCS Java library.

A detailed manual explaining all options, functionalities, and usage fundamentals of the interface is available in the **PyFCS_GUI_Manual** directory.

### 🔧 How to Use

If you don't need to modify the source code, follow the steps below for a quick installation based on your operating system.

---

#### 📥 1. Download the Project

Download the repository from GitHub using the **"Clone or Download"** button or from the **Releases** section as a `.zip` file.  
Extract the contents to a local folder of your choice.

---

### 💻 Installation by Operating System

---

#### 🪟 Windows

Make sure you have **Python 3.9 or higher** installed, along with **pip**.

If `pip` is missing, you can install it with:

```bash
python -m ensurepip --upgrade
```

Then, install the required Python dependencies and launch the interface:

```bash
pip install -r PyFCS\external\requirements.txt

python PyFCS\visualization\basic_structure.py
```

---

#### 🐧 Linux

```bash
# Make the setup script executable (only once)
chmod +x ./PyFCS/external/setup_pyfcs_linux.sh

# Run the setup script
./PyFCS/external/setup_pyfcs_linux.sh
```

After the setup completes, launch the interface with:

```bash
python3 PyFCS/visualization/basic_structure.py
```

> 💡 The script creates a virtual environment, installs Python dependencies, and handles system packages like `tkinter`.

---

#### 🍎 macOS

```bash
# Make the setup script executable (only once)
chmod +x ./PyFCS/external/setup_pyfcs_mac.sh

# Run the setup script
./PyFCS/external/setup_pyfcs_mac.sh
```

After the setup completes, launch the interface with:

```bash
python PyFCS/visualization/basic_structure.py
```

> 💡 This script uses Homebrew to install Python (if needed), ensures `tkinter` works, and configures everything automatically.




---

### 📬 Contact & Support
For support or questions, feel free to contact: rafaconejo@ugr.es

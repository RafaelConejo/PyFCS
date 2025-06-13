#!/bin/bash

LOGFILE="setup_pyfcs.log"
exec > >(tee "$LOGFILE") 2>&1

echo "🚀 Starting automatic setup for PyFCS environment (clean mode with log)..."

# 1. Check if Python is installed via Homebrew
if ! brew list python &> /dev/null; then
    echo "🔧 Installing the latest version of Python via Homebrew..."
    brew install python
else
    echo "✅ Python is already installed via Homebrew."
fi

# 2. Get the path to the latest installed version of Python
PYTHON_PATH="$(brew --prefix python)/bin/python3"
echo "🐍 Using Python: $($PYTHON_PATH --version)"
echo "📍 Python location: $PYTHON_PATH"

# 3. Check that tkinter works
echo "🔎 Checking tkinter (please close the window by clicking 'Quit' to continue)..."
$PYTHON_PATH -c "import tkinter; tkinter._test()" || {
    echo "❌ tkinter is not working properly. Aborting."
    exit 1
}

# 4. Remove virtual environment if it already exists
if [ -d "venv_pyfcs" ]; then
    echo "🧹 Removing previous virtual environment..."
    rm -rf venv_pyfcs
fi

# 5. Create new virtual environment
echo "🧱 Creating virtual environment 'venv_pyfcs'..."
$PYTHON_PATH -m venv venv_pyfcs

# 6. Activate virtual environment
echo "⚙️ Activating virtual environment..."
source venv_pyfcs/bin/activate

# 7. Install requirements
if [ -f "PyFCS/external/requirements.txt" ]; then
    echo "📦 Installing requirements from requirements.txt..."
    pip install --upgrade pip
    pip install -r PyFCS/external/requirements.txt
else
    echo "❌ PyFCS/external/requirements.txt not found"
    exit 1
fi

# 8. Launch application
echo "🚀 Launching PyFCS..."
python PyFCS/visualization/basic_structure.py

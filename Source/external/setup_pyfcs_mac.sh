#!/usr/bin/env bash
set -euo pipefail

# Resolve all paths from the location of this script.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"
VENV_DIR="$PROJECT_ROOT/venv_pyfcs"
LOGFILE="$PROJECT_ROOT/setup_pyfcs.log"

exec > >(tee "$LOGFILE") 2>&1

echo "Starting PyFCS setup on macOS..."

if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew is required: https://brew.sh/" >&2
    exit 1
fi

# Initialize the Homebrew environment on Apple Silicon and Intel Macs.
eval "$(brew shellenv)"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Installing Python 3 with Homebrew..."
    brew install python
fi

PYTHON_PATH="$(command -v python3)"
echo "Using Python: $($PYTHON_PATH --version)"

# Homebrew may provide tkinter as a separate package.
if ! "$PYTHON_PATH" -c 'import tkinter' >/dev/null 2>&1; then
    PYTHON_VERSION="$(
        "$PYTHON_PATH" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
    )"

    echo "Tkinter is not available for Python $PYTHON_VERSION." >&2
    echo "Install a compatible python-tk package (e.g. brew install python-tk@$PYTHON_VERSION) and rerun." >&2
    exit 1
fi

if [[ ! -f "$REQUIREMENTS" ]]; then
    echo "Requirements file not found: $REQUIREMENTS" >&2
    exit 1
fi

# Reuse an existing environment; remove it manually for a clean reinstall.
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    echo "Creating virtual environment: $VENV_DIR"
    "$PYTHON_PATH" -m venv "$VENV_DIR"
fi

VENV_PYTHON="$VENV_DIR/bin/python"

"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -r "$REQUIREMENTS"

# Module execution keeps Source.* imports valid.
echo "Launching PyFCS..."
cd "$PROJECT_ROOT"

"$VENV_PYTHON" -m Source.interface.mainInterface

#!/usr/bin/env bash
set -euo pipefail

# Resolve all paths from the location of this script.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"
VENV_DIR="$PROJECT_ROOT/venv_pyfcs"
LOGFILE="$PROJECT_ROOT/setup_pyfcs.log"

exec > >(tee "$LOGFILE") 2>&1

echo "Starting PyFCS setup on Linux..."

if ! command -v python3 >/dev/null 2>&1; then
    echo "Installing Python 3..."
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv python3-pip
fi

PYTHON_PATH="$(command -v python3)"
echo "Using Python: $($PYTHON_PATH --version)"

# Tkinter must be available to the system Python used to create the venv.
if ! "$PYTHON_PATH" -c 'import tkinter' >/dev/null 2>&1; then
    echo "Installing Tkinter..."
    sudo apt-get update
    sudo apt-get install -y python3-tk
    "$PYTHON_PATH" -c 'import tkinter'
fi

if [[ ! -f "$REQUIREMENTS" ]]; then
    echo "Requirements file not found: $REQUIREMENTS" >&2
    exit 1
fi

# Reuse an existing environment; recreate it manually if needed.
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    echo "Creating virtual environment: $VENV_DIR"

    "$PYTHON_PATH" -m venv "$VENV_DIR" || {
        echo "Python venv is unavailable. On Debian/Ubuntu, install python3-venv." >&2
        exit 1
    }
fi

VENV_PYTHON="$VENV_DIR/bin/python"

"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -r "$REQUIREMENTS"

# Module execution keeps Source.* imports valid.
echo "Launching PyFCS..."
cd "$PROJECT_ROOT"

"$VENV_PYTHON" -m Source.interface.mainInterface

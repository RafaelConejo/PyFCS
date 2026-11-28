#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"
VENV_DIR="${PYFCS_VENV_DIR:-$PROJECT_ROOT/venv_pyfcs}"

# Preserve the setup log where possible, but a read-only install must not
# prevent setup with a writable external virtual environment.
LOGFILE="$PROJECT_ROOT/setup_pyfcs.log"
if ( : >> "$LOGFILE" ) 2>/dev/null; then
    exec > >(tee -a "$LOGFILE") 2>&1
else
    echo "Setup log is not writable; continuing with terminal output." >&2
fi
echo "Starting PyFCS setup..."

# Homebrew is optional: python.org installations with Tk work too.
# On a fresh shell, locate Homebrew on Apple Silicon or Intel if present.
if ! command -v brew >/dev/null 2>&1; then
    for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
        if [[ -x "$candidate" ]]; then
            eval "$("$candidate" shellenv)"
            break
        fi
    done
fi

# Explicit interpreter selection is useful when several Python versions are installed.
PYTHON_PATH="${PYFCS_PYTHON:-$(command -v python3 || true)}"
if [[ -z "$PYTHON_PATH" ]]; then
    echo "Python 3 is required. Install Python 3 with Tk support first." >&2
    exit 1
fi
if ! "$PYTHON_PATH" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
    echo "Use Python 3.10 or later (3.10–3.13 recommended)." >&2
    exit 1
fi
if ! "$PYTHON_PATH" -c 'import tkinter' >/dev/null 2>&1; then
    echo "The selected Python has no Tkinter support. Install the matching Tk package and retry." >&2
    echo "Linux (Debian/Ubuntu): sudo apt install python3-tk python3-venv" >&2
    echo "macOS: use python.org Python with Tk, or brew install python-tk@<major.minor>." >&2
    exit 1
fi
if [[ ! -f "$REQUIREMENTS" ]]; then
    echo "Requirements file not found: $REQUIREMENTS" >&2
    exit 1
fi
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    "$PYTHON_PATH" -m venv "$VENV_DIR" || {
        echo "Could not create the virtual environment. Check the Python venv package and directory permissions." >&2
        exit 1
    }
fi
VENV_PYTHON="$VENV_DIR/bin/python"
if ! "$VENV_PYTHON" -c 'import sys, tkinter; sys.exit(sys.version_info < (3,10))'; then
    echo "Existing venv is incompatible. Move or remove $VENV_DIR, then rerun this script." >&2
    exit 1
fi
"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -r "$REQUIREMENTS"
# Optional acceleration: failure to install it must not prevent use of PyFCS.
if [[ "${PYFCS_SKIP_NUMBA:-0}" != 1 ]]; then
    if ! "$VENV_PYTHON" -m pip install numba; then
        echo "Numba installation failed; PyFCS will use the scalar backend." >&2
    fi
fi
"$VENV_PYTHON" -m pip check
"$VENV_PYTHON" -c 'import numpy, scipy, matplotlib, tkinter, skimage, PIL, sklearn, plotly, pandas, cv2; print("PyFCS dependencies imported successfully.")'
if [[ "${PYFCS_SETUP_ONLY:-0}" == 1 ]]; then
    exit 0
fi
cd "$PROJECT_ROOT"
exec "$VENV_PYTHON" -m Source.interface.mainInterface

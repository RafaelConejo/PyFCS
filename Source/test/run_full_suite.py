
"""Run the complete PyFCS regression suite and save its results.

From the project root:
    python -m Source.test.run_full_suite
    python -m Source.test.run_full_suite --gui

All test_*.py modules are discovered automatically. The optional --gui flag
checks the Tkinter FCS creation dialog and requires a graphical display.
"""

import argparse
import json
import os
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path


# Resolve project and test directories independently of the launch location.
ROOT = Path(__file__).resolve().parents[2]
TESTS = Path(__file__).resolve().parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Use a non-interactive Matplotlib backend unless another is explicitly set.
os.environ.setdefault("MPLBACKEND", "Agg")


class Tee:
    """Write test output to the terminal and log file simultaneously."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for stream in self.streams:
            stream.write(data)
        return len(data)

    def flush(self):
        for stream in self.streams:
            stream.flush()


def optional_gui_smoke():
    """Verify the default settings and configuration of the creation dialog."""
    import tkinter as tk
    from Source.interface.modules.UtilsTools import FCSCreationDialog

    # The root window remains hidden; the dialog is closed after validation.
    root = tk.Tk()
    root.withdraw()

    try:
        dialog = FCSCreationDialog(
            root,
            {"Red": (45., 60., 35.), "Blue": (45., 10., -45.)},
            lambda name, options: None,
        )

        try:
            # Check the initial geometry and the non-covering sampling options.
            assert dialog.mode_var.get() == "LAB", "Geometry must start in LAB"
            assert dialog.disjoint_var.get() and dialog.covering_var.get()

            dialog.disjoint_var.set(True)
            dialog.covering_var.set(False)
            dialog._update_typology()

            assert dialog.samples_var.get() == "27", "Non-Covering default must be 27"

            dialog.name_var.set("GlobalGuiTest")
            name, opts = dialog.build_options()

            assert name == "GlobalGuiTest"
            assert opts["disjoint"] and not opts["covering"]
            assert opts["samples"] == 27

        finally:
            if dialog.winfo_exists():
                dialog.cancel()

        root.update_idletasks()

    finally:
        root.destroy()


def main(argv=None):
    """Discover tests, run optional GUI checks and store a summary report."""
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--gui",
        action="store_true",
        help="Also exercise the real Tkinter FCS creation window"
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Show only failures and summary"
    )

    parser.add_argument(
        "--report-dir",
        type=Path,
        default=TESTS / "test_reports",
        help="Where to save .log and .json results"
    )

    args = parser.parse_args(argv)

    # Run tests from a consistent working directory and create report storage.
    os.chdir(ROOT)
    args.report_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = args.report_dir / f"global_{stamp}.log"
    json_file = args.report_dir / f"global_{stamp}.json"

    started = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()

    with log_file.open("w", encoding="utf-8") as out:
        stream = Tee(sys.stdout, out)

        print(f"PyFCS regression suite | root: {ROOT}", file=stream)
        print(
            "Discovering Source/test/test_*.py (including global workflows)...",
            file=stream
        )

        # Test modules, including comparison-tool checks, run in one suite.
        suite = unittest.defaultTestLoader.discover(
            start_dir=str(TESTS),
            pattern="test_*.py"
        )

        result = unittest.TextTestRunner(
            stream=stream,
            verbosity=(1 if args.quiet else 2)
        ).run(suite)

        # GUI checks remain opt-in so the regular suite can run headlessly.
        gui_error = None
        gui_status = "not_requested"

        if args.gui:
            print("\nGUI smoke: FCS creation dialog", file=stream)

            try:
                optional_gui_smoke()
                gui_status = "passed"
                print("GUI smoke PASSED", file=stream)

            except Exception as exc:
                gui_status = "failed"
                gui_error = f"{type(exc).__name__}: {exc}"
                print(f"GUI smoke FAILED: {gui_error}", file=stream)

        elapsed = round(time.perf_counter() - started, 3)

        # Store both aggregate counts and individual failures for diagnosis.
        report = {
            "kind": "PyFCS global regression",
            "started_utc": started_at,
            "project_root": str(ROOT),
            "python": sys.version,
            "tests_run": result.testsRun,
            "failures": len(result.failures),
            "errors": len(result.errors),
            "skipped": len(result.skipped),
            "expected_failures": len(result.expectedFailures),
            "unexpected_successes": len(result.unexpectedSuccesses),
            "gui": gui_status,
            "gui_error": gui_error,
            "elapsed_seconds": elapsed,
            "passed": result.wasSuccessful() and gui_status != "failed",
            "failure_details": [
                {"test": str(t), "traceback": err}
                for t, err in result.failures
            ],
            "error_details": [
                {"test": str(t), "traceback": err}
                for t, err in result.errors
            ],
            "skipped_details": [
                {"test": str(t), "reason": why}
                for t, why in result.skipped
            ],
        }

        json_file.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        print(
            f"\nSummary: {result.testsRun} tests | "
            f"{len(result.failures)} failures | "
            f"{len(result.errors)} errors | "
            f"{len(result.skipped)} skipped | {elapsed}s",
            file=stream
        )
        print(f"Log: {log_file}", file=stream)
        print(f"JSON: {json_file}", file=stream)

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())

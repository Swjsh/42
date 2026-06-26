"""Full analysis pipeline after v2 backtest (ORB + VIX).

Run after drive_native_backtest_v2.py completes.
Produces: ORB check, per-instrument analysis, config comparison, concentration check.

Usage:
    python backtest/futures/run_full_analysis.py
"""
from __future__ import annotations
import subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
scripts = [
    ("ORB check — MNQ",       ["python", "backtest/futures/check_orb.py", "--inst", "MNQ"]),
    ("ORB check — MES",       ["python", "backtest/futures/check_orb.py", "--inst", "MES"]),
    ("Analyze — MNQ",         ["python", "backtest/futures/analyze_native.py", "--inst", "MNQ"]),
    ("Analyze — MES",         ["python", "backtest/futures/analyze_native.py", "--inst", "MES"]),
    ("Compare configs — MNQ", ["python", "backtest/futures/compare_configs.py", "--inst", "MNQ"]),
    ("Compare configs — MES", ["python", "backtest/futures/compare_configs.py", "--inst", "MES"]),
    ("Concentration check",   ["python", "backtest/futures/concentration_check.py"]),
    ("Pytest suite",          ["python", "-m", "pytest", "backtest/futures/test_futures.py", "-v", "--tb=short"]),
]

if __name__ == "__main__":
    ok = True
    for label, cmd in scripts:
        print(f"\n{'='*60}\n>>> {label}\n{'='*60}")
        result = subprocess.run(cmd, cwd=str(REPO), capture_output=False)
        if result.returncode != 0:
            print(f"  [FAIL] {label} returned {result.returncode}")
            ok = False
        else:
            print(f"  [OK]")
    print("\n" + ("All steps passed" if ok else "SOME STEPS FAILED") + "\n")
    sys.exit(0 if ok else 1)

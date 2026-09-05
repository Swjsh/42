"""guard_test.py -- guard for the tickers-theta-budget-cadence package. SCAFFOLD -- fill in real
assertions before this package is usable; main() intentionally returns 1 (RED) until
you do, so an unfinished scaffold can never be mistaken for a passing guard.

Packet row: tickers-theta-budget-cadence.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]


def test_scaffold_not_yet_implemented() -> None:
    raise AssertionError(
        "tickers-theta-budget-cadence/guard_test.py is still the K2 scaffold -- replace this with real "
        "assertions (organ absence + ledger-stops-growing, per the goal's DONE-WHEN) "
        "before this package can be applied."
    )


def main() -> int:
    try:
        test_scaffold_not_yet_implemented()
        print("[PASS] test_scaffold_not_yet_implemented")
        return 0
    except AssertionError as exc:
        print(f"[FAIL] test_scaffold_not_yet_implemented -- {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

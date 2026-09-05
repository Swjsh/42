"""test_right_tail_1min_fail_open_2026_09_05.py -- GOAL-OPRA-1MIN-COVERAGE-2026-09-05 O4.

Guard: a missing 1-min OPRA pair must be LOGGED (via the returned `resolution_1min_fallback`
/ `reason` fields), never a crash, for both `right_tail_waves._price_wave` (called by
`right_tail_capture.py` daily) and `gate_net_cost_walk._walk_entry`.

RED-PROOF: `test_price_wave_1min_missing_pair_never_raises` calls `_price_wave` with a
contract/date this repo's `backtest/data/highres/` cache does not have (a date far outside
the goal's fetched window) -- if `_load_1min_cache_readonly`'s cache-miss branch were ever
changed to raise instead of returning None, this test would fail with an exception instead
of a clean assertion failure, which is exactly the crash this guard exists to catch.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "backtest", REPO / "backtest" / "lib", REPO / "backtest" / "tools",
           REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from lib.right_tail_waves import _price_wave  # noqa: E402
from _option_bars_1min_cache import load_1min_cache_readonly  # noqa: E402

MISSING_DATE = "2026-01-05"  # winter, well outside this project's summer OPRA cache


def test_load_1min_cache_readonly_returns_none_not_raises_on_miss():
    result = load_1min_cache_readonly("SPY260105C00500000", MISSING_DATE)
    assert result is None


def test_price_wave_1min_missing_pair_never_raises():
    result = _price_wave(MISSING_DATE, "bull", 500.0, f"{MISSING_DATE}T09:56:00", resolution="1min")
    assert result["computed"] is False
    assert result["resolution_1min_fallback"] is True
    assert result["resolution_used"] == "5min"
    assert "reason" in result


def test_price_wave_5min_default_unaffected_by_1min_plumbing():
    """Default resolution ('5min') must not even attempt the 1-min lookup -- same fail-open
    reason string as before O3, no new resolution_1min_fallback=True noise on the default
    path."""
    result = _price_wave(MISSING_DATE, "bull", 500.0, f"{MISSING_DATE}T09:56:00")
    assert result["computed"] is False
    assert result["resolution_used"] == "5min"
    assert result["resolution_1min_fallback"] is False

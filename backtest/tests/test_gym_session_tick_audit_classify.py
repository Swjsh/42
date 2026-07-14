"""Tests for autoresearch.gym_session._classify_tick_audit's non-vacuity guard.

Root incident (2026-07-14, strategy/candidates/_validator-inbox/2026-07-14-tick-audit-
zero-count-bug.md): heartbeat_tick_audit.py parsed a dead legacy log format and always
returned 0/0 counts. `_classify_tick_audit`'s old `if critical == 0: GREEN` check could
not distinguish "0 ticks captured, source dead" from "N ticks captured, 0 CRITICAL among
them" -- a day the engine ran 772+ real decisions rendered byte-identical to a genuinely
clean day. These tests guard the fix: total==0 or live==0 must classify MISSING, never
GREEN, independent of whatever upstream producer wrote the JSON.
"""

from __future__ import annotations

from autoresearch.gym_session import _classify_tick_audit


def test_all_zero_counts_is_missing_not_green():
    # The exact shape heartbeat-tick-audit-2026-07-13.json had before the fix.
    data = {
        "total_ticks": 0,
        "live_trading_ticks": 0,
        "counts": {
            "ALIGNED": 0, "MISALIGNED-BENIGN": 0, "MISALIGNED-CRITICAL": 0,
            "STALE_PAUSED": 0, "NO_DATA": 0, "NO_BAR": 0,
        },
        "headline": "0 of 0 live-trading ticks (0%) were MISALIGNED-CRITICAL",
        "log_path": None,
    }
    result = _classify_tick_audit(data)
    assert result.verdict == "MISSING"
    assert "0 ticks" in result.summary or "no source data" in result.summary.lower()


def test_zero_live_but_nonzero_no_data_is_missing_not_green():
    # total > 0 (all NO_DATA, e.g. fleet-only rows with no spy claim) but live == 0 --
    # still can't compute a real misalignment rate, must not read as clean.
    data = {
        "counts": {
            "ALIGNED": 0, "MISALIGNED-BENIGN": 0, "MISALIGNED-CRITICAL": 0,
            "STALE_PAUSED": 0, "NO_DATA": 50, "NO_BAR": 0,
        },
    }
    result = _classify_tick_audit(data)
    assert result.verdict == "MISSING"


def test_genuine_clean_day_is_green():
    # A real clean day: N live ticks classified, zero CRITICAL among them.
    data = {
        "counts": {
            "ALIGNED": 274, "MISALIGNED-BENIGN": 105, "MISALIGNED-CRITICAL": 0,
            "STALE_PAUSED": 0, "NO_DATA": 516, "NO_BAR": 1,
        },
    }
    result = _classify_tick_audit(data)
    assert result.verdict == "GREEN"
    assert result.evidence["live_ticks"] == 379


def test_real_critical_ticks_still_escalate():
    data = {
        "counts": {
            "ALIGNED": 10, "MISALIGNED-BENIGN": 2, "MISALIGNED-CRITICAL": 3,
            "STALE_PAUSED": 0, "NO_DATA": 0, "NO_BAR": 0,
        },
        "critical_ticks": [{"decision": "ENTER_BEAR"}],
    }
    result = _classify_tick_audit(data)
    assert result.verdict == "RED"


def test_data_is_none_still_missing():
    assert _classify_tick_audit(None).verdict == "MISSING"


def test_guard_is_independent_of_upstream_status_field():
    # Even if the upstream producer forgets to set (or mis-sets) its own "status" field,
    # the aggregator must re-derive MISSING from the raw counts itself -- belt AND braces.
    data = {
        "status": "OK",  # deliberately wrong/stale -- must not be trusted
        "counts": {
            "ALIGNED": 0, "MISALIGNED-BENIGN": 0, "MISALIGNED-CRITICAL": 0,
            "STALE_PAUSED": 0, "NO_DATA": 0, "NO_BAR": 0,
        },
    }
    result = _classify_tick_audit(data)
    assert result.verdict == "MISSING"

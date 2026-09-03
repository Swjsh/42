"""Fixture test for backtest/tools/fleet_stale_signal_skip_extract.py
(FLEET-STALE-SIGNAL-SKIPS-STRUCTURE-STOP verify, 2026-09-03).

The real automation/state/fleet/<arm>/decisions.jsonl files contain zero in-window
signal_stale ticks (both real occurrences are 2026-06-24/26, both flat=true) -- so this
fixture is what actually exercises the open-position and join logic the extractor claims to
implement. Read-only: writes nothing outside pytest's tmp_path.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import fleet_stale_signal_skip_extract as mod  # noqa: E402


def test_parse_stale_age_sec():
    assert mod.parse_stale_age_sec("signal_stale_421s") == 421
    assert mod.parse_stale_age_sec("signal_stale_1452s") == 1452
    assert mod.parse_stale_age_sec("ok") is None
    assert mod.parse_stale_age_sec("no_signal_file") is None
    assert mod.parse_stale_age_sec("signal_unreadable: boom") is None
    assert mod.parse_stale_age_sec(None) is None


def test_is_unreadable():
    assert mod.is_unreadable("signal_unreadable: Expecting value") is True
    assert mod.is_unreadable("signal_stale_500s") is False
    assert mod.is_unreadable("ok") is False


def _row(ts, status, flat):
    return {"ts_et": ts, "signal_status": status, "flat": flat}


def test_classify_counts_open_vs_flat_separately():
    rows = [
        _row("2026-08-25T10:00:00-04:00", "ok", False),
        _row("2026-08-25T10:01:00-04:00", "signal_stale_500s", True),   # stale, FLAT -> no harm
        _row("2026-08-25T10:02:00-04:00", "signal_stale_600s", False),  # stale, OPEN -> counts
        _row("2026-08-25T10:03:00-04:00", "signal_unreadable: x", False),  # distinct mechanism
        _row("2026-08-26T09:00:00-04:00", "signal_stale_700s", False),  # different day
    ]
    cls = mod.classify_arm_window(rows, "2026-08-25", "2026-08-26")
    d0 = cls["per_day"]["2026-08-25"]
    assert d0["total_ticks"] == 4
    assert d0["stale_ticks"] == 2
    assert d0["stale_with_open_position"] == 1
    assert d0["unreadable_ticks"] == 1
    assert d0["unreadable_with_open_position"] == 1
    d1 = cls["per_day"]["2026-08-26"]
    assert d1["stale_with_open_position"] == 1
    assert sorted(cls["stale_age_sec_all"]) == [500, 600, 700]
    assert len(cls["stale_with_open_position_ticks"]) == 2


def test_classify_window_excludes_out_of_range_dates():
    rows = [_row("2026-07-01T10:00:00-04:00", "signal_stale_500s", False)]
    cls = mod.classify_arm_window(rows, "2026-08-25", "2026-09-02")
    assert cls["per_day"] == {}
    assert cls["stale_age_sec_all"] == []


def test_join_finds_delayed_exit_when_stale_open_tick_precedes():
    stale_open_ticks = [
        {"date": "2026-08-25", "ts_et": "2026-08-25T13:20:00-04:00", "age_sec": 500}
    ]
    trades = [
        {
            "arm": "risky-1",
            "date": "2026-08-25",
            "exit_reason": "structure_stop",
            "exit_ts_et": "2026-08-25T13:27:07.790721",
            "symbol": "SPY260825C00765000",
            "pnl_dollars": -100.0,
        },
        {  # different arm -> excluded
            "arm": "safe-3",
            "date": "2026-08-25",
            "exit_reason": "structure_stop",
            "exit_ts_et": "2026-08-25T13:27:06.584802",
            "symbol": "SPY260825C00765000",
            "pnl_dollars": -60.0,
        },
        {  # not a structure_stop -> excluded
            "arm": "risky-1",
            "date": "2026-08-25",
            "exit_reason": "premium_stop",
            "exit_ts_et": "2026-08-25T13:30:00",
            "symbol": "SPY260825C00766000",
            "pnl_dollars": -50.0,
        },
    ]
    out = mod.join_structure_stop_exits(
        trades, "risky-1", "2026-08-25", "2026-09-02", stale_open_ticks
    )
    assert len(out) == 1
    assert out[0]["preceded_by_stale_skip"] is True
    assert out[0]["earliest_preceding_stale_tick"] == "2026-08-25T13:20:00-04:00"


def test_join_no_match_when_stale_tick_is_after_exit():
    stale_open_ticks = [
        {"date": "2026-08-25", "ts_et": "2026-08-25T14:00:00-04:00", "age_sec": 500}
    ]
    trades = [
        {
            "arm": "risky-1",
            "date": "2026-08-25",
            "exit_reason": "structure_stop",
            "exit_ts_et": "2026-08-25T13:27:07.790721",
            "symbol": "SPY260825C00765000",
            "pnl_dollars": -100.0,
        }
    ]
    out = mod.join_structure_stop_exits(
        trades, "risky-1", "2026-08-25", "2026-09-02", stale_open_ticks
    )
    assert len(out) == 1
    assert out[0]["preceded_by_stale_skip"] is False


def test_run_end_to_end_against_real_repo_window_never_fired(tmp_path):
    """Sanity-checks run() against the REAL repo files for the report's window -- this
    documents (does not merely assert-into-a-corner) that the shipped 2026-08-25..2026-09-02
    window has zero stale-with-open-position ticks on any of the 4 fleet_rest arms, matching
    the report's NEVER-FIRED finding."""
    result = mod.run(["safe-1", "safe-3", "risky-1", "risky-3"], "2026-08-25", "2026-09-02")
    for arm, data in result["arms"].items():
        assert data["total_stale_with_open_position"] == 0, arm
        assert data["classification"] == "NEVER-FIRED", arm
        assert data["structure_stop_exits_delayed_by_stale_skip"] == []

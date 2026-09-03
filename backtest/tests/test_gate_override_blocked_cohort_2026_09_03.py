"""
Fixture test for backtest/tools/gate_override_blocked_cohort.py
(queue item SAFE3-RISKY1-GATE-RETEST-EXTEND, 2026-09-03 extension pass).

Exercises the pure matching/dedup logic on small synthetic data -- does NOT
read the live 96MB automation/state/core-decisions.jsonl or fleet decisions
ledgers, so it stays fast and independent of production state.
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import gate_override_blocked_cohort as goc  # noqa: E402


def test_parse_ts_handles_both_offset_and_naive_formats():
    assert goc.parse_ts("2026-06-21T21:53:32.493267-04:00") == datetime(2026, 6, 21, 21, 53, 32, 493267)
    assert goc.parse_ts("2026-06-25T13:48:17") == datetime(2026, 6, 25, 13, 48, 17)


def test_group_into_episodes_collapses_consecutive_same_signal_ticks():
    ticks = [
        {"arm_id": "safe-3", "dt": datetime(2026, 8, 4, 9, 46), "date": "2026-08-04",
         "side": "C", "setup": "VWAP_CONTINUATION", "reason": "gate: 1 triggers < 2"},
        {"arm_id": "safe-3", "dt": datetime(2026, 8, 4, 9, 47), "date": "2026-08-04",
         "side": "C", "setup": "VWAP_CONTINUATION", "reason": "gate: 1 triggers < 2"},
        # a gap > GAP_MIN (10min) starts a new episode
        {"arm_id": "safe-3", "dt": datetime(2026, 8, 4, 10, 5), "date": "2026-08-04",
         "side": "C", "setup": "VWAP_CONTINUATION", "reason": "gate: 1 triggers < 2"},
        # different side -> always a new episode even with no time gap
        {"arm_id": "safe-3", "dt": datetime(2026, 8, 4, 10, 5), "date": "2026-08-04",
         "side": "P", "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON", "reason": "gate: 1 triggers < 2"},
    ]
    episodes = goc.group_into_episodes(ticks)
    assert len(episodes) == 3
    assert episodes[0]["n_ticks"] == 2
    assert episodes[1]["n_ticks"] == 1
    assert episodes[2]["side"] == "P"


def test_find_nearest_trade_picks_closest_same_day_round_trip_within_tolerance():
    trades_idx = {
        ("2026-08-11", "bold-2", "SPY260811P00771000"): [
            {"entry_ts_et": "2026-08-11T13:32:01.316225", "pnl_dollars": -145.0},
            {"entry_ts_et": "2026-08-11T14:07:47.082933", "pnl_dollars": 297.0},
        ]
    }
    near_first = goc.find_nearest_trade(
        trades_idx, "2026-08-11", "bold-2", "SPY260811P00771000",
        datetime(2026, 8, 11, 13, 31, 5),
    )
    assert near_first["pnl_dollars"] == -145.0

    near_second = goc.find_nearest_trade(
        trades_idx, "2026-08-11", "bold-2", "SPY260811P00771000",
        datetime(2026, 8, 11, 14, 7, 5),
    )
    assert near_second["pnl_dollars"] == 297.0


def test_find_nearest_trade_returns_none_outside_tolerance():
    trades_idx = {
        ("2026-08-11", "bold-2", "SPY260811P00771000"): [
            {"entry_ts_et": "2026-08-11T13:32:01.316225", "pnl_dollars": -145.0},
        ]
    }
    result = goc.find_nearest_trade(
        trades_idx, "2026-08-11", "bold-2", "SPY260811P00771000",
        datetime(2026, 8, 11, 14, 0, 0),  # 28 min away, tol default is 5 min
    )
    assert result is None


def test_find_nearest_trade_returns_none_when_symbol_absent():
    assert goc.find_nearest_trade({}, "2026-08-11", "bold-2", "SPY260811P00771000",
                                   datetime(2026, 8, 11, 13, 32)) is None

"""Guard tests for elite_bull_postfix_requal_2026_07_31.py (pure functions only).

Pins the FROZEN prereg semantics (analysis/recommendations/elite-bull-requal-prereg-2026-07-31.json):
dedupe clustering, the E1/E2/E3/F1 exclusion ladder, sequential-hold one-position-at-a-time,
fleet FIFO round trips, fill->cluster mapping, and the frozen 3-branch verdict rule.
RED-proofed 2026-07-31 (see the requal .md's guard section for the mutation run).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest" / "tools"))

from elite_bull_postfix_requal_2026_07_31 import (  # noqa: E402
    classify_exclusion,
    dedupe_into_events,
    fifo_round_trips,
    grade_verdict,
    map_fill_to_cluster,
    merge_cross_account,
    sequential_hold,
)


def _row(ts, action="SKIP_ELITE_BULL_LEVEL_RECLAIM", account="safe", **kw):
    return {"ts_et": ts, "action": action, "account": account, "spy": 745.0, **kw}


# --------------------------------------------------------------------------- dedupe
def test_dedupe_clusters_at_5min_gap():
    rows = [_row("2026-07-31T12:10:03"), _row("2026-07-31T12:14:03"),
            _row("2026-07-31T12:20:04"), _row("2026-07-31T13:15:03")]
    events = dedupe_into_events(rows)
    # 12:10+12:14 chain (4min), 12:14->12:20 = 6min gap -> new event; 13:15 separate
    assert len(events) == 3
    assert events[0]["n_ticks"] == 2
    assert events[0]["first_ts"] == "2026-07-31T12:10:03"


# --------------------------------------------------------------------------- exclusions
def test_e1_cross_account_stale_trigger_excludes():
    ev = dedupe_into_events([_row("2026-07-31T09:31:05")])[0]
    other = [_row("2026-07-31T09:31:50", action="SKIP_STALE_TRIGGER", account="bold")]
    status, reason = classify_exclusion(ev, other)
    assert status == "E1"
    assert "SKIP_STALE_TRIGGER" in reason


def test_e2_prior_day_trigger_bar_excludes():
    ev = dedupe_into_events(
        [_row("2026-07-31T09:32:03", trigger_bar_et="2026-07-30T15:55:00-04:00")])[0]
    status, _ = classify_exclusion(ev, [])
    assert status == "E2"


def test_e3_after_1500_excludes_but_1459_keeps():
    late = dedupe_into_events([_row("2026-07-31T15:05:03")])[0]
    ok = dedupe_into_events([_row("2026-07-31T14:59:59")])[0]
    assert classify_exclusion(late, [])[0] == "E3"
    assert classify_exclusion(ok, [])[0] == "KEPT"


def test_e3_exact_1500_boundary_excluded():
    # entry_no_trade_after_et is [09:35, 15:00) -- a tick AT 15:00:00 sharp is already late
    ev = dedupe_into_events([_row("2026-07-31T15:00:00")])[0]
    assert classify_exclusion(ev, [])[0] == "E3"


def test_f1_open_adjacent_flags_not_excludes():
    ev = dedupe_into_events(
        [_row("2026-07-31T09:36:03", trigger_bar_et="2026-07-31T09:30:00-04:00")])[0]
    assert classify_exclusion(ev, [])[0] == "F1"


# --------------------------------------------------------------------------- distinct setups
def test_merge_cross_account_same_signal_counts_once():
    safe = [{"first_ts": "2026-07-31T12:10:03"}]
    bold = [{"first_ts": "2026-07-31T12:10:04"}]
    assert merge_cross_account(safe, bold) == 1
    bold2 = [{"first_ts": "2026-07-31T13:30:04"}]
    assert merge_cross_account(safe, bold2) == 2


# --------------------------------------------------------------------------- sequential hold
def test_sequential_hold_consumes_overlapping_events():
    replays = [
        {"entry_ts_et": "2026-07-31T12:15:00", "exit_time_et": "2026-07-31T13:25:00", "pnl": 10.0},
        {"entry_ts_et": "2026-07-31T13:20:00", "exit_time_et": "2026-07-31T13:40:00", "pnl": -5.0},
        {"entry_ts_et": "2026-07-31T13:30:00", "exit_time_et": "2026-07-31T14:00:00", "pnl": 7.0},
    ]
    kept = sequential_hold(replays)
    # 13:20 falls inside 12:15->13:25 hold -> consumed; 13:30 is after 13:25 -> kept
    assert [k["entry_ts_et"] for k in kept] == ["2026-07-31T12:15:00", "2026-07-31T13:30:00"]


def test_sequential_hold_boundary_equal_ts_is_consumed():
    replays = [
        {"entry_ts_et": "2026-07-31T12:15:00", "exit_time_et": "2026-07-31T13:25:00", "pnl": 1.0},
        {"entry_ts_et": "2026-07-31T13:25:00", "exit_time_et": "2026-07-31T13:45:00", "pnl": 1.0},
    ]
    assert len(sequential_hold(replays)) == 1  # exit tick itself cannot double as entry tick


# --------------------------------------------------------------------------- fleet FIFO
def test_fifo_round_trip_partial_sells_one_episode():
    fills = [
        {"arm": "risky-3", "symbol": "SPY260731C00746000", "date_et": "2026-07-31",
         "ts_et": "2026-07-31T12:19:03", "side": "buy", "qty": 5, "price": 0.33},
        {"arm": "risky-3", "symbol": "SPY260731C00746000", "date_et": "2026-07-31",
         "ts_et": "2026-07-31T12:34:04", "side": "sell", "qty": 3, "price": 0.65},
        {"arm": "risky-3", "symbol": "SPY260731C00746000", "date_et": "2026-07-31",
         "ts_et": "2026-07-31T12:43:03", "side": "sell", "qty": 2, "price": 0.48},
    ]
    eps = fifo_round_trips(fills)
    assert len(eps) == 1
    # 3*(0.65)+2*(0.48) - 5*0.33 = 1.95+0.96-1.65 = 1.26 -> $126.00
    assert eps[0]["pnl"] == 126.00
    assert eps[0]["entry_ts_et"] == "2026-07-31T12:19:03"
    assert eps[0]["exit_ts_et"] == "2026-07-31T12:43:03"


def test_fifo_unresolved_open_position_disclosed_not_dropped():
    fills = [{"arm": "safe-3", "symbol": "SPY260731C00747000", "date_et": "2026-07-31",
              "ts_et": "2026-07-31T12:31:03", "side": "buy", "qty": 3, "price": 0.30}]
    eps = fifo_round_trips(fills)
    assert len(eps) == 1
    assert eps[0]["pnl"] is None
    assert eps[0]["unresolved_open_qty"] == 3


# --------------------------------------------------------------------------- mapping
def test_map_fill_within_15min_maps_nearest_outside_none():
    clusters = [{"first_ts": "2026-07-31T12:10:03"}, {"first_ts": "2026-07-31T12:20:04"}]
    assert map_fill_to_cluster("2026-07-31T12:19:03", clusters) == "2026-07-31T12:20:04"
    assert map_fill_to_cluster("2026-07-31T12:50:00", clusters) is None


# --------------------------------------------------------------------------- frozen verdict
def test_verdict_a_requires_both_positive():
    assert grade_verdict(primary_total=50.0, primary_n=4, fleet_net=120.0) == "a"


def test_verdict_c_requires_both_negative():
    assert grade_verdict(primary_total=-200.0, primary_n=4, fleet_net=-50.0) == "c"


def test_verdict_b_on_mixed_signs_or_empty():
    assert grade_verdict(primary_total=-10.0, primary_n=4, fleet_net=100.0) == "b"
    assert grade_verdict(primary_total=10.0, primary_n=4, fleet_net=-100.0) == "b"
    assert grade_verdict(primary_total=0.0, primary_n=0, fleet_net=500.0) == "b"

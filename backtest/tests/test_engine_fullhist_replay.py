"""Guard for backtest/tools/engine_fullhist_replay.py (full-history engine walkthrough,
analysis/recommendations/engine-fullhist-replay-2026-07-23.json, J directive 2026-07-22:
"every day we have needs a walkthrough on the engine -- max days of data and testing").

Load-bearing invariants this guard pins:

  1. EXIT-SHAPE-PARITY GUARD (the trap the task brief named): the script must derive P&L from
     the REAL `strategies.py#RIBBON_RIDE.exit.to_dict()` shape (profit_lock_mode="trailing",
     stop_mode="structure"), NEVER from `simulate_trade_real`'s params.json-top-level-keys
     shape (profit_lock_mode="fixed") -- SIM-EXIT-SHAPE-PARITY-AUDIT (queue.md) is exactly the
     class of silent regression this guards against.
  2. RIBBON ALIGNMENT: `ribbon_tick_df_for` must return a frame the SAME length as its input
     option-bar frame (walk_exit_manager indexes it positionally) and must be a backward
     (no-lookahead) as-of join.
  3. DATA INTEGRITY: the merged full-history SPY/VIX CSVs this script depends on must exist,
     cover through 2026-07-22, and be chronologically monotonic (guards
     backtest/tools/merge_extend_data_20260722.py's own monotonicity assertion staying true on
     disk, not just at merge-time).
  4. ANCHOR REPRODUCTION (fast, single-day): 2026-07-21's one known-good core_safe entry
     (14:58 P748 TRENDLINE, ribbon_flip_back exit, ~$0 P&L) must keep reproducing at the
     strike+side+tier level. This is the ONE anchor day that PASSED trade-level fidelity in
     the 2026-07-23 run (2026-07-17 did NOT -- see the scorecard's sanity_anchors block for the
     documented, disclosed entry-level divergence between the batch level/trendline detector
     and live's curated+memory-merged key-levels.json feed; that gap is NOT expected to close
     via this guard, it is a scope limitation of orchestrator.run_backtest itself).

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_engine_fullhist_replay.py -q
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
for _p in (REPO, BACKTEST, BACKTEST / "tools", FLEET_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import engine_fullhist_replay as efr  # noqa: E402
import strategies as fleet_strategies  # noqa: E402

DATA_AVAILABLE = efr.SPY_FILE.exists() and efr.VIX_FILE.exists()
pytestmark = pytest.mark.skipif(
    not DATA_AVAILABLE,
    reason=f"merged full-history data not present ({efr.SPY_FILE.name})")


def test_correct_exit_shape_is_the_real_live_shape_not_the_known_wrong_one():
    shape = efr.correct_shape_for_doc()
    live_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    assert shape == live_shape
    # The WRONG shape (simulate_trade_real / params.json top-level keys) uses "fixed" +
    # a premium/percent stop; the REAL live shape trades a chandelier trail off a structure
    # stop. A future edit that silently swaps back to the wrong shape must fail this test.
    assert shape["profit_lock_mode"] == "trailing"
    assert shape["stop_mode"] == "structure"
    assert shape["profit_lock_mode"] != "fixed"


def test_ribbon_tick_df_alignment_and_no_lookahead():
    opt_df = pd.DataFrame({
        "timestamp_et": pd.to_datetime([
            "2026-07-17 13:01:00", "2026-07-17 13:03:00", "2026-07-17 13:07:00",
        ]),
        "open": [1.0, 1.1, 1.2], "high": [1.0, 1.1, 1.2], "low": [1.0, 1.1, 1.2],
        "close": [1.0, 1.1, 1.2],
    })
    ribbon_lookup = pd.DataFrame({
        "timestamp_et": pd.to_datetime([
            "2026-07-17 13:00:00", "2026-07-17 13:05:00", "2026-07-17 13:10:00",
        ]),
        "stack": ["BEAR", "BULL", "BULL"],
    })
    out = efr.ribbon_tick_df_for(opt_df, ribbon_lookup)
    assert len(out) == len(opt_df)
    # 13:01 -> most recent ribbon bar at/before it is 13:00 (BEAR); 13:03 -> still 13:00 (BEAR,
    # NOT 13:05's BULL -- that would be lookahead); 13:07 -> 13:05 (BULL).
    assert list(out["stack"]) == ["BEAR", "BEAR", "BULL"]


def test_merged_data_files_cover_full_window_and_are_monotonic():
    spy_df = pd.read_csv(efr.SPY_FILE)
    spy_df["timestamp_et"] = pd.to_datetime(spy_df["timestamp_et"])
    assert spy_df["timestamp_et"].min().date() <= dt.date(2025, 1, 2)
    assert spy_df["timestamp_et"].max().date() >= dt.date(2026, 7, 22)
    ts_utc = pd.to_datetime(spy_df["timestamp_et"], utc=True)
    assert (ts_utc.diff().dt.total_seconds().dropna() >= 0).all(), (
        "merged SPY file is not chronologically monotonic -- merge_extend_data_20260722.py's "
        "own assertion should have caught this at merge time")


def test_match_entries_rejects_time_distant_strike_side_collision():
    """L250 (ZERO-FOR-TWELVE-POSTMORTEM follow-up, 2026-07-25): the original inline matcher
    paired on strike+side ALONE (no time bound, first-hit-wins) and silently reported a live
    11:40 fill "matched" to a replay 13:55 entry -- 2h15m apart, a genuinely different signal
    that happened to share strike+side. That false-positive match hid the true entry-count gap
    (replay produced only 2/4 live entries that day) behind an apparent partial-pass. This pins
    the FIXED behavior: a same-strike+side replay entry more than time_tol_minutes away must be
    reported as unmatched (and surfaced as an extra, unexplained replay entry), never silently
    accepted as the same trade."""
    expected = [("11:40", 745, "P", "ELITE", -102.0), ("13:01", 746, "P", "TRENDLINE", 241.0)]
    replayed = [
        {"time_et": "13:15", "side": "P", "tier": "TRENDLINE", "symbol": "SPY260717P00746000",
         "dollar_pnl": -54.6},
        {"time_et": "13:55", "side": "P", "tier": "SUPER", "symbol": "SPY260717P00745000",
         "dollar_pnl": 459.0},
    ]
    out = efr.match_entries_by_strike_side_time(expected, replayed)
    # 13:01 -> 13:15 is a genuine 14-minute near-miss: matched.
    assert out["n_matched_by_strike_side"] == 1
    matched_times = {(m["expected_time"], m["replay_time"]) for m in out["matched"]}
    assert ("13:01", "13:15") in matched_times
    # 11:40 -> 13:55 is 2h15m apart: must NOT be silently accepted as a match.
    assert any(u["expected_time"] == "11:40" for u in out["unmatched_expected_live_entries"])
    # the 13:55 replay entry must surface as an unexplained extra, not get absorbed into the
    # 11:40 expected-entry's match.
    assert any(r_["time_et"] == "13:55" for r_ in out["extra_replay_entries_not_in_live"])


def test_match_entries_still_matches_exact_same_bar():
    """Anti-vacuity: a same-time, same-strike, same-side replay entry still matches (the fix
    must not turn every match into a reject)."""
    expected = [("14:58", 748, "P", "TRENDLINE", 0.0)]
    replayed = [{"time_et": "14:58", "side": "P", "tier": "TRENDLINE",
                 "symbol": "SPY260721P00748000", "dollar_pnl": -12.0}]
    out = efr.match_entries_by_strike_side_time(expected, replayed)
    assert out["n_matched_by_strike_side"] == 1
    assert out["extra_replay_entries_not_in_live"] == []
    assert out["unmatched_expected_live_entries"] == []


def test_per_archetype_days_matches_headline_and_flags_underpowered():
    """WS6 regime library first-consumer wiring (2026-08-01): build_per_archetype_days must
    (a) reconcile exactly to the input series' own n/sum (no day dropped or double-counted),
    (b) use the real committed library (known dates: 2026-07-31=V-reversal, 2025-04-03=
    gap-go -- see test_regime_library_guards.py's landmark pins), and (c) flag a thin
    archetype as underpowered using the OP-11 evidence_n floor, not silently pass it off as
    equally reliable as a well-populated one."""
    day_series = pd.Series({
        "2026-07-31": 145.0,     # V-reversal
        "2025-04-03": -60.0,     # gap-go
        "2025-04-04": 10.0,      # gap-go (2nd day, same archetype)
    })
    out = efr.build_per_archetype_days(day_series, evidence_floor=2)
    assert out["V-reversal"]["n"] == 1
    assert out["V-reversal"]["total"] == 145.0
    assert out["V-reversal"]["underpowered"] is True     # n=1 < floor=2
    assert out["gap-go"]["n"] == 2
    assert out["gap-go"]["total"] == pytest.approx(-50.0)
    assert out["gap-go"]["underpowered"] is False         # n=2 >= floor=2
    # reconciliation: the "ALL" summary row (per_archetype_rows' own convention) must equal
    # the input series' own n/sum exactly -- no day silently dropped or double-counted.
    assert out["ALL"]["n"] == len(day_series)
    assert out["ALL"]["total"] == pytest.approx(float(day_series.sum()))
    non_all = [v for k, v in out.items() if k != "ALL"]
    assert sum(v["n"] for v in non_all) == len(day_series)
    assert sum(v["total"] for v in non_all) == pytest.approx(float(day_series.sum()))


def test_per_archetype_days_untagged_date_is_loud_not_dropped():
    """A date the regime library has never heard of (outside its window) must land in the
    explicit UNTAGGED bucket -- never silently absorbed into a real archetype and never
    silently dropped from the total (C7)."""
    day_series = pd.Series({"2026-07-31": 100.0, "1999-01-04": -25.0})
    out = efr.build_per_archetype_days(day_series)
    assert out[efr.UNTAGGED]["n"] == 1
    assert out[efr.UNTAGGED]["total"] == -25.0
    assert out["ALL"]["n"] == 2


def test_per_archetype_trades_reconciles_to_full_population_and_flags_thin_cells():
    """TRADE-level cut: n_trades/total_pnl must sum EXACTLY back to the full trades frame
    (every trade attributed to exactly one archetype bucket), win_rate is per-bucket (not
    globally diluted), and a 1-trade archetype is flagged underpowered."""
    df = pd.DataFrame({
        "date": ["2026-07-31", "2025-04-03", "2025-04-04", "2025-04-04"],
        "dollar_pnl": [145.0, -60.0, 10.0, 30.0],
    })
    out = efr.build_per_archetype_trades(df, evidence_floor=2)
    assert out["V-reversal"]["n_trades"] == 1
    assert out["V-reversal"]["win_rate"] == 1.0
    assert out["V-reversal"]["underpowered"] is True
    assert out["gap-go"]["n_trades"] == 3
    assert out["gap-go"]["total_pnl"] == pytest.approx(-20.0)
    assert out["gap-go"]["win_rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert out["gap-go"]["underpowered"] is False
    assert sum(v["n_trades"] for v in out.values()) == len(df)
    assert sum(v["total_pnl"] for v in out.values()) == pytest.approx(float(df["dollar_pnl"].sum()))
    # the function must tag df in place with an 'archetype' column (documented behavior)
    assert "archetype" in df.columns


@pytest.mark.slow
def test_anchor_2026_07_21_quiet_day_reproduces_at_trade_level():
    """Single-day run (fast, ~seconds) -- the one anchor day that passed full-history trade-
    level fidelity. Regressing this would mean either the entry-gate cascade or the exit-shape
    correction broke, not just the (disclosed, expected) level/trendline data-source gap."""
    spy_df = pd.read_csv(efr.SPY_FILE)
    vix_df = pd.read_csv(efr.VIX_FILE)
    spy_df["timestamp_et"] = pd.to_datetime(spy_df["timestamp_et"])

    from lib.orchestrator import run_backtest
    r = run_backtest(spy_df, vix_df, start_date=dt.date(2026, 7, 21), end_date=dt.date(2026, 7, 21),
                      **efr.SAFE_BASE_LIVE)
    assert len(r.trades) == 1, f"expected exactly 1 entry on the 2026-07-21 quiet day, got {len(r.trades)}"
    t = r.trades[0]
    assert t.side == "P"
    assert int(t.strike) == 748
    assert "trendline_rejection" in t.triggers_fired

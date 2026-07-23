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

"""Guards for PAIRED-RIBBON-AB-2026-08-01's two load-bearing mechanisms.

1. EXIT SUPPRESSION: walk_exit_manager(ribbon_tick_df=None) must make ribbon_flip_back
   structurally unreachable while leaving every other exit stage live -- the study's whole
   treatment rests on this being true (plan_exit_actions consumes the flag at exactly its
   two exit-trigger sites, exit_manager.py:430+483).
2. COHORT PREDICATE: the static-level-tied classification that decides WHICH trades get
   the suppressed walk (prereg cohort_definition -- bull filters.py:1265 set, bear 1723 set
   minus trendline_rejection, plus fhh_level_rejection).

RED-proofed 2026-08-01 (mutations run before this file was committed):
  - mutant A: hand the "suppressed" walk the ribbon frame anyway -> test 2 FAILS
    (exit_reason ribbon_flip_back).
  - mutant B: add trendline_rejection to LEVEL_TIED_TRIGGERS -> test 4 FAILS.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

BACKTEST = Path(__file__).resolve().parents[1]
for _p in (str(BACKTEST), str(BACKTEST / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from paired_ribbon_ab_2026_08_01 import LEVEL_TIED_TRIGGERS, is_level_anchored  # noqa: E402


def _mk_walk_inputs(n: int = 8):
    ts0 = dt.datetime(2026, 7, 1, 10, 0)
    opt = pd.DataFrame({
        "timestamp_et": [ts0 + dt.timedelta(minutes=5 * i) for i in range(n)],
        "open": [1.00] * n, "high": [1.02] * n, "low": [0.98] * n, "close": [1.00] * n,
    })
    ribbon = pd.DataFrame({"timestamp_et": opt["timestamp_et"], "stack": ["BULL"] * n})
    spy = pd.DataFrame({
        "timestamp_et": [ts0 - dt.timedelta(minutes=5)] + list(opt["timestamp_et"]),
        "close": [100.0] * (n + 1),
    })
    shape = {"premium_stop_pct": -0.50, "tp1_premium_pct": 9.9, "tp1_qty_fraction": 0.667,
             "profit_lock_mode": "trailing", "runner_target_pct": 99.0}
    kw = dict(symbol="SPY260701P00100000", side="P", entry_time_et=ts0, entry_premium=1.0,
              qty=3, exit_shape=shape, structure_stop_enabled=False, trigger_level=None,
              strategy="ribbon_ride", time_stop_et=dt.time(15, 40),
              opt_df=opt, five_min_spy_df=spy)
    return kw, ribbon


def test_ribbon_walk_exits_ribbon_flip_back():
    """Baseline: with the ribbon feed attached and the stack against the position from the
    first managed bar, the walk exits ribbon_flip_back (proves the synthetic setup would
    trigger the exit -- without this, the suppression test below could pass vacuously)."""
    kw, ribbon = _mk_walk_inputs()
    res = walk_exit_manager(ribbon_tick_df=ribbon, **kw)
    assert res.exit_reason == "ribbon_flip_back", res.exit_reason


def test_suppressed_walk_never_ribbon_exits():
    """ribbon_tick_df=None on the SAME entry/bars: ribbon_flip_back unreachable; position
    resolves by another stage (here: data exhausts, disclosed force-close)."""
    kw, _ = _mk_walk_inputs()
    res = walk_exit_manager(ribbon_tick_df=None, **kw)
    assert "ribbon" not in (res.exit_reason or ""), res.exit_reason
    assert res.exit_reason == "data_exhausted_force_close", res.exit_reason


def test_suppressed_walk_other_exits_still_live():
    """Suppression must remove ONLY the ribbon exit: a catastrophe-cap touch still exits
    on the premium stop with the ribbon feed absent."""
    kw, _ = _mk_walk_inputs()
    opt = kw["opt_df"].copy()
    opt.loc[3:, ["open", "high", "low", "close"]] = 0.40  # below 0.50 catastrophe stop
    kw["opt_df"] = opt
    res = walk_exit_manager(ribbon_tick_df=None, **kw)
    assert res.exit_reason.startswith("premium_stop"), res.exit_reason


def test_level_anchored_predicate_matches_prereg():
    """Cohort membership exactly as frozen: static-level triggers in, trendline-only and
    ribbon-only OUT."""
    assert is_level_anchored(["level_reclaim"])
    assert is_level_anchored(["level_rejection", "ribbon_flip"])
    assert is_level_anchored(["fhh_level_rejection"])
    assert is_level_anchored(["confluence"])
    assert is_level_anchored(["sequence_reclaim"])
    assert is_level_anchored(["sequence_rejection", "trendline_rejection"])
    assert not is_level_anchored(["trendline_rejection"])
    assert not is_level_anchored(["trendline_rejection", "ribbon_flip"])
    assert not is_level_anchored(["ribbon_flip"])
    assert not is_level_anchored([])
    assert not is_level_anchored(None)
    assert "trendline_rejection" not in LEVEL_TIED_TRIGGERS

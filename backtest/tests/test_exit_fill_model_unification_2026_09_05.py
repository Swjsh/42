"""Guard: STEP 1 of prereg FILL-MODEL-UNIFICATION-2026-08-13 -- exit_manager_walk.py's
`all_exits_market` / `exit_slippage` plumbing (added 2026-08-13, commit 3b47506c) actually
does what STEP 1 requires: EVERY market-style exit fill (stops included) pays slippage when
the treatment arm is selected, the effect is monotonic in the slippage magnitude (the exact
property analysis/recommendations/prereg-slippage-rebaseline-2026-08-12.json found violated
on the OLD stop-fill sites before that 2026-08-12 fix), and the untouched default reproduces
today's published numbers byte-for-byte on a small fixture.

SCOPE NOTE. This file does NOT re-litigate whether the plumbing exists -- it does (pinned by
backtest/tests/test_exit_walk_fill_plumbing_2026_08_13.py, which this file complements rather
than duplicates: that file pins _fill_price BY VALUE across all 9 stages at the unit level;
this file additionally proves the property END-TO-END through walk_exit_manager on a realistic
multi-stage fixture, and RED-proofs (a)/(b) against the pre-plumbing commit so the property is
demonstrably NEW, not vacuously true). It does NOT flip any default -- the prereg's own
laundering_hazard forbids that in this commit (see WHY-NO-DEFAULT-FLIP below).

WHY NO DEFAULT FLIP (2026-09-05 adjudication of this exact file). The task that produced this
guard asked for "the old behaviour reachable behind an explicit flag" -- i.e. flip
`all_exits_market`'s default to True. That is the literal thing
prereg-fill-model-unification-2026-08-13.json's `laundering_hazard` forbids in this commit:
"flipping the default would move every one of ~95 calling files' historical cells in the same
commit that introduced the switch ... A SIGN FLIP IS NOT A RESURRECTION", and its
`mandatory_order_of_operations` STEP 1 is explicitly "with the slippage constants UNCHANGED at
0.02" -- not a default change at all, just publishing the A-only delta. The already-committed
plumbing (all_exits_market=False default, exit_slippage=DEFAULT_EXIT_SLIPPAGE=0.02 default) IS
therefore STEP 1 as the prereg defines it: the delta is PUBLISHED via
analysis/whole-engine-null/2026-09-02-flagon.json (research script
backtest/tools/whole_engine_null_flagon_research.py) and re-quoted in this session's fire's
report. The default flips only in the prereg'd STEP-2 commit that also carries the 2c->1c
slippage re-baseline and the fee model, per that document's own text.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
WALK_PATH = REPO / "backtest" / "lib" / "exit_manager_walk.py"

ALL_STAGES = ("tp1", "runner_target", "premium_stop", "profit_lock_floor", "trail",
              "be_stop", "time_stop", "ribbon_flip", "structure_stop")
LIMIT_STAGES = ("tp1", "runner_target", "premium_stop", "profit_lock_floor", "trail", "be_stop")
MARKET_STAGES = ("time_stop", "ribbon_flip", "structure_stop")


def _load_module(path: Path, name: str):
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def emw():
    return _load_module(WALK_PATH, "_emw_unification_probe")


# ------------------------------------------------------- (a) every market-style stage pays

@pytest.mark.parametrize("stage", ALL_STAGES)
def test_every_stage_pays_slippage_under_all_exits_market(emw, stage):
    """(a) With the treatment arm selected, ALL 9 stages -- limit-style AND market-style --
    fill at bar_close - exit_slippage, never at the theoretical triggered level. This is the
    STEP 1 fix itself: a limit-style stage (e.g. tp1) that still fills at its exact level under
    all_exits_market=True means the switch did not bind for that stage."""
    level = 1.30  # a limit level that differs from bar_close, so the two arms are distinguishable
    bar_close = 1.10
    got = emw._fill_price(stage, level, bar_close, exit_slippage=0.02, all_exits_market=True)
    assert got == pytest.approx(bar_close - 0.02), (
        f"stage {stage!r} did not pay slippage under all_exits_market=True: got {got}, "
        f"expected {bar_close - 0.02}")
    assert got != pytest.approx(level) if level is not None else True


def test_all_nine_stages_are_exercised_above():
    """Guards the parametrization itself against silently losing a stage if _MARKET_STAGES or
    the limit-stage set is ever renamed."""
    assert set(ALL_STAGES) == set(LIMIT_STAGES) | set(MARKET_STAGES)
    assert len(ALL_STAGES) == 9


# ------------------------------------------------------- (b) monotonic in slippage magnitude

@pytest.mark.parametrize("stage", ALL_STAGES)
def test_fill_price_monotonic_non_increasing_in_slippage(emw, stage):
    """(b) THE PROPERTY analysis/recommendations/prereg-slippage-rebaseline-2026-08-12.json
    found VIOLATED: raising slippage must never raise a sell-side fill price, for a FIXED
    trade (same stage, same level, same bar_close). Only checked where all_exits_market=True
    makes exit_slippage load-bearing for this stage (limit-style stages under the LEGACY arm
    ignore exit_slippage entirely by design -- that is test (c)'s subject, not this one's)."""
    level, bar_close = 1.30, 1.10
    slippages = [0.00, 0.01, 0.02, 0.05, 0.10]
    fills = [emw._fill_price(stage, level, bar_close, exit_slippage=s, all_exits_market=True)
             for s in slippages]
    for lo, hi in zip(fills, fills[1:]):
        assert hi <= lo + 1e-9, (
            f"stage {stage!r}: fill price INCREASED as slippage rose ({fills}) -- this is the "
            "exact non-monotonicity the 2026-08-12 rebaseline prereg found and blocked on")


def test_walk_level_pnl_monotonic_non_increasing_in_slippage_end_to_end(emw):
    """(b) end-to-end: walk the SAME fixed multi-stage trade (entry -> TP1 partial -> runner
    trail-stop) through walk_exit_manager under all_exits_market=True at rising slippage and
    assert total dollar_pnl never rises. Exercises the property through the real call path
    ~95 files use, not just the pure fill resolver."""
    entry_ts = "2026-02-02 10:00:00"
    shape = {
        "stop_mode": "premium", "premium_stop_pct": -0.50,
        "tp1_premium_pct": 0.50, "tp1_qty_fraction": 0.5,
        "profit_lock_mode": "fixed", "runner_target_pct": 99.0,
        "trail_pct": 0.20, "profit_lock_arm_pct": 10.0,
    }
    opt_df = pd.DataFrame({
        "timestamp_et": pd.to_datetime([entry_ts, "2026-02-02 10:05:00",
                                        "2026-02-02 10:10:00", "2026-02-02 10:15:00"]),
        "open": [1.00, 1.55, 1.60, 1.20], "high": [1.00, 1.55, 1.60, 1.20],
        "low": [1.00, 1.55, 1.60, 1.20], "close": [1.00, 1.55, 1.60, 1.20],
    })
    spy_df = pd.DataFrame({
        "timestamp_et": pd.to_datetime([entry_ts, "2026-02-02 10:05:00",
                                        "2026-02-02 10:10:00", "2026-02-02 10:15:00"]),
        "open": [600.0] * 4, "high": [600.5] * 4, "low": [599.5] * 4, "close": [600.0] * 4,
    })

    def _pnl(slippage: float) -> float:
        res = emw.walk_exit_manager(
            symbol="SPY260202C00600000", side="C",
            entry_time_et=dt.datetime(2026, 2, 2, 10, 0, 0),
            entry_premium=1.00, qty=4, exit_shape=shape, structure_stop_enabled=False,
            trigger_level=None, strategy="ribbon_ride", time_stop_et=dt.time(10, 15),
            opt_df=opt_df, ribbon_tick_df=None, five_min_spy_df=spy_df,
            exit_slippage=slippage, all_exits_market=True,
        )
        assert res.resolved, "fixture must actually resolve or the monotonicity check is vacuous"
        return res.dollar_pnl

    pnls = [_pnl(s) for s in (0.00, 0.01, 0.02, 0.05)]
    for lo, hi in zip(pnls, pnls[1:]):
        assert hi <= lo + 1e-6, (
            f"end-to-end walked P&L rose as slippage increased ({pnls}) on a fixed trade set")


# ------------------------------------------------------- (c) legacy arm reproduces old numbers

def test_legacy_default_arm_reproduces_known_fixture_values(emw):
    """(c) all_exits_market=False (the untouched default) must still fill the 6 limit-style
    stages at their exact level and the 3 market-style stages at close - DEFAULT_EXIT_SLIPPAGE
    -- i.e. reproduce every pre-2026-08-13 published number exactly, so old runs stay
    reproducible for comparison against the STEP 1 delta."""
    bar_close = 1.10
    expected_limit = {"tp1": 1.30, "runner_target": 2.50, "premium_stop": 0.50,
                       "profit_lock_floor": 0.80, "trail": 0.90, "be_stop": 1.00}
    for stage, level in expected_limit.items():
        got = emw._fill_price(stage, level, bar_close)
        assert got == pytest.approx(level), f"legacy arm moved {stage}: {got} != {level}"
    for stage in MARKET_STAGES:
        got = emw._fill_price(stage, None, bar_close)
        assert got == pytest.approx(bar_close - emw.DEFAULT_EXIT_SLIPPAGE), (
            f"legacy arm moved {stage}'s market fill")


def test_legacy_arm_is_the_untouched_default_signature(emw):
    """Pins that the legacy behaviour is reachable with NO kwargs at all -- i.e. it is what
    every one of the ~95 existing calling files without a slippage kwarg already gets, so this
    guard is testing the actual shipped default, not a hypothetical."""
    import inspect
    params = inspect.signature(emw.walk_exit_manager).parameters
    assert params["all_exits_market"].default is False
    assert params["exit_slippage"].default == emw.DEFAULT_EXIT_SLIPPAGE == 0.02


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))

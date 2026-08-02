"""Guard tests for the OPTION-BAR-RESOLUTION-BIAS-2026-08-02 source fix:
  1. backtest/lib/option_pricing_real.py -- load_contract_bars gains an explicit, logged
     `resolution` kwarg (default "5min", unchanged behavior) + a new
     assert_intraday_stop_fidelity() guard function.
  2. backtest/lib/exit_manager_walk.py -- walk_exit_manager gains OPTIONAL
     opt_df_resolution/allow_5min kwargs wired to that guard.

Both changes are additive/backward-compatible by construction (new keyword-only params with
safe defaults; every one of the ~250 existing load_contract_bars call sites and ~7 existing
walk_exit_manager call sites passes none of the new kwargs -- verified via
`grep -rn "load_contract_bars("` across the repo before writing this fix, zero hits with a
second argument). These tests exist so a future edit that weakens or removes the guard fails
loudly instead of silently reintroducing the silent-5-min-default defect.

Run: cd backtest && ../backtest/.venv/Scripts/python.exe -m pytest tests/test_option_bar_resolution_1min_guards_2026_08_02.py -q
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "lib"))

from lib.option_pricing_real import (  # noqa: E402
    NATIVE_RESOLUTION,
    assert_intraday_stop_fidelity,
    load_contract_bars,
)
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402

KNOWN_SYMBOL = "SPY260709C00750000"  # confirmed present in backtest/data/options/


# ---------------------------------------------------------------------------------------------
# 1) load_contract_bars -- backward compatibility + explicit resolution validation
# ---------------------------------------------------------------------------------------------
def test_native_resolution_is_5min():
    assert NATIVE_RESOLUTION == "5min"


def test_load_contract_bars_default_call_unchanged():
    """The ~250 existing callers pass ONLY `symbol` -- this must still return the exact same
    DataFrame shape/content it always has (regression pin, not just 'doesn't crash')."""
    df_default = load_contract_bars(KNOWN_SYMBOL)
    df_explicit = load_contract_bars(KNOWN_SYMBOL, resolution="5min")
    assert df_default is not None
    assert list(df_default.columns) == ["timestamp_et", "open", "high", "low", "close",
                                        "volume", "vwap", "trade_count"]
    # explicit resolution="5min" must be byte-identical to the default (same in-process cache
    # entry, same disk source) -- proves the new kwarg changes NOTHING about the data path.
    pd.testing.assert_frame_equal(df_default, df_explicit)


def test_load_contract_bars_unknown_symbol_still_returns_none():
    assert load_contract_bars("SPY990101C00999000") is None


def test_load_contract_bars_rejects_non_5min_resolution():
    """This function has never served anything but the 5-min disk cache -- asking it for
    another resolution must fail loudly (NotImplementedError), never silently return 5-min
    data mislabeled as something else."""
    with pytest.raises(NotImplementedError):
        load_contract_bars(KNOWN_SYMBOL, resolution="1min")


# ---------------------------------------------------------------------------------------------
# 2) assert_intraday_stop_fidelity -- the opt-in guard
# ---------------------------------------------------------------------------------------------
def test_guard_raises_on_5min_without_optin():
    with pytest.raises(ValueError, match="OPTION-BAR-RESOLUTION-BIAS"):
        assert_intraday_stop_fidelity("5min", allow_5min=False)


def test_guard_silent_on_5min_with_optin():
    assert_intraday_stop_fidelity("5min", allow_5min=True) is None  # must not raise


def test_guard_silent_on_1min_regardless_of_optin():
    assert_intraday_stop_fidelity("1min", allow_5min=False) is None
    assert_intraday_stop_fidelity("1min", allow_5min=True) is None


# ---------------------------------------------------------------------------------------------
# 3) walk_exit_manager -- opt_df_resolution/allow_5min wiring, backward compatibility
# ---------------------------------------------------------------------------------------------
def _tiny_opt_df() -> pd.DataFrame:
    """Minimal 2-bar opt_df -- enough for walk_exit_manager to run its entry-bar lookup and
    exit cleanly via data_exhausted_force_close (the guard fires, if it fires, BEFORE any bar
    is touched -- these tests only need the call to reach or not reach that point)."""
    return pd.DataFrame({
        "timestamp_et": [dt.datetime(2026, 7, 9, 9, 35), dt.datetime(2026, 7, 9, 9, 36)],
        "open": [1.0, 1.0], "high": [1.0, 1.0], "low": [1.0, 1.0], "close": [1.0, 1.0],
    })


def _minimal_shape() -> dict:
    return {"premium_stop_pct": -0.5, "tp1_premium_pct": 1.0, "tp1_qty_fraction": 0.667,
            "profit_lock_mode": "trailing", "trail_pct": 0.15, "runner_target_pct": 9.9}


def _call_walk(**overrides):
    kwargs = dict(
        symbol="x", side="P", entry_time_et=dt.datetime(2026, 7, 9, 9, 34),
        entry_premium=1.0, qty=1, exit_shape=_minimal_shape(),
        structure_stop_enabled=False, trigger_level=None, strategy="RIBBON_RIDE",
        time_stop_et=dt.time(15, 50), opt_df=_tiny_opt_df(), ribbon_tick_df=None,
        five_min_spy_df=_tiny_opt_df(),
    )
    kwargs.update(overrides)
    return walk_exit_manager(**kwargs)


def test_walk_exit_manager_default_omits_resolution_kwargs_unchanged():
    """Every pre-existing call site never passes opt_df_resolution -- confirms the default
    (None) is a true no-op: the walk runs to completion, no ValueError."""
    result = _call_walk()
    assert result.resolved is True or result.exit_reason == "data_exhausted_force_close"


def test_walk_exit_manager_5min_without_optin_raises():
    with pytest.raises(ValueError, match="OPTION-BAR-RESOLUTION-BIAS"):
        _call_walk(opt_df_resolution="5min", allow_5min=False)


def test_walk_exit_manager_5min_with_optin_runs():
    result = _call_walk(opt_df_resolution="5min", allow_5min=True)
    assert result.resolved is True or result.exit_reason == "data_exhausted_force_close"


def test_walk_exit_manager_1min_declared_never_raises():
    result = _call_walk(opt_df_resolution="1min", allow_5min=False)
    assert result.resolved is True or result.exit_reason == "data_exhausted_force_close"


# ---------------------------------------------------------------------------------------------
# 4) Regression pins on Step 1's persisted measurement (guards against silent drift on re-run)
# ---------------------------------------------------------------------------------------------
STEP1_JSON = REPO / "analysis" / "recommendations" / "option-bar-resolution-bias-2026-08-02.json"


@pytest.mark.skipif(not STEP1_JSON.exists(), reason="Step 1 output not generated in this checkout")
def test_step1_bias_is_one_directional():
    """The core, most load-bearing claim of the whole investigation: 5-min NEVER invents a
    phantom stop (n_stop_only_at_5min == 0) -- it only MISSES real ones. If this ever flips
    to nonzero on a re-run, the 'systematically flatters' framing (not just 'adds noise') no
    longer holds and every downstream verdict in this investigation needs re-review."""
    d = json.loads(STEP1_JSON.read_text(encoding="utf-8"))
    assert d["n_stop_only_at_5min"] == 0
    assert d["n_stop_only_at_1min"] >= 1
    assert d["gap_5min_minus_1min"] > 0  # 5-min total > 1-min total = 5-min flatters


@pytest.mark.skipif(not STEP1_JSON.exists(), reason="Step 1 output not generated in this checkout")
def test_step1_known_signal_present():
    """SPY260709C00750000 -- the exact contract named in the task brief -- must appear in the
    stop-only-at-1min cohort (cross-check against the independently-computed level-target-exit
    lane's own root-cause finding on the same symbol)."""
    d = json.loads(STEP1_JSON.read_text(encoding="utf-8"))
    symbols = {r["symbol"] for r in d["stop_only_at_1min_detail"]}
    assert "SPY260709C00750000" in symbols

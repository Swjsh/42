"""GUARD (T-W2, HANDOFF-2026-07-11-CONFIRM-AND-WIRE, ground rule 13): profit_lock_mode /
profit_lock_trail_pct / time_stop_minutes_before_close must reach the simulator when a grind
sweeps them through ``strategy_space_grind.run_cell`` -- as EXPLICIT run_backtest kwargs, never
through gate_patch/params_overrides.

THE SCAR THIS RE-PROOFS (Fable review, 2026-07-08 late): the old mass_grind.py set
profit_lock_mode inside gate_patch (-> params_overrides). ``_params_to_kwargs`` NEVER
translates any profit_lock_* field (test_profit_lock_not_in_baseline.py, L156 -- intentional:
mapping the chandelier into the params->baseline path would bias every future baseline
negative). Consequence: 181/181 fixed-vs-trailing P4 pairs came out BYTE-IDENTICAL -- the
entire P5 survivor universe never tested trailing at all.

THE FIX (this file guards it): ``run_cell`` now accepts profit_lock_mode /
profit_lock_trail_pct / time_stop_minutes_before_close and forwards them as explicit
run_backtest kwargs (the SAME pattern already used for premium_stop_pct -- belt-and-suspenders,
bypassing the L156-guarded params_overrides path entirely). This guard does NOT touch, weaken,
or duplicate test_profit_lock_not_in_baseline.py -- that guard must stay green; run both.

RED-PROOF (verified manually this session, not left in the repo):
  reverting run_cell's profit_lock_mode/profit_lock_trail_pct kwargs (dropping the last three
  lines of its run_backtest(...) call) makes every cell in this file fall back to run_backtest's
  defaults (mode="fixed", trail_pct=0.0) regardless of what run_cell's caller passed -> the
  vary-and-assert tests below RED (fixed/trailing books collapse to identical PnL) and the
  neighbor-differs test REDs too. Restoring the kwargs makes all tests pass again.

Run:  cd backtest && .venv/Scripts/python.exe -m pytest tests/test_lock_trail_kwargs_wired.py -q
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

os.environ.setdefault("GAMMA_RISK_GATE_ASSERT", "0")
os.environ.setdefault("GAMMA_ENGINE_SCORE_ASSERT", "0")

_REPO = Path(__file__).resolve().parents[1]
_ROOT = _REPO.parent
for _p in (str(_REPO), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import json  # noqa: E402

from autoresearch.runner import load_data  # noqa: E402
from autoresearch.strategy_space_grind import run_cell  # noqa: E402

# Smoke window: one quarter, real-fills coverage confirmed (data-coverage.json spans
# 2025-01-02..2026-07-08 as of T-W1). Fast (~9s/cell) and has enough trade volume to be
# non-vacuous -- NOT the full 2025-01-01..2026-06-18 grind window (that's minutes/cell).
_SMOKE_START = dt.date(2026, 1, 1)
_SMOKE_END = dt.date(2026, 3, 31)

_PARAMS_PATH = _ROOT / "automation" / "state" / "params.json"


def _load_smoke_data():
    return load_data(_SMOKE_START, _SMOKE_END)


def _base_params() -> dict:
    return json.loads(_PARAMS_PATH.read_text(encoding="utf-8-sig"))


def _pnl_signature(trades) -> tuple:
    return tuple(round(float(t.dollar_pnl), 4) for t in trades)


def _run(spy, vix, params, *, profit_lock_mode: str, profit_lock_trail_pct: float,
         time_stop_minutes_before_close: int = 10):
    trades = run_cell(
        spy, vix, params, strike_offset=-2, gate_patch={}, stop_pct=-0.50,
        profit_lock_mode=profit_lock_mode, profit_lock_trail_pct=profit_lock_trail_pct,
        time_stop_minutes_before_close=time_stop_minutes_before_close,
    )
    assert trades, "smoke window produced zero trades -- guard would be vacuous"
    return trades


def test_trail_pct_value_varies_the_book():
    """The core vary-and-assert (ground rule 13): trail 0.10 vs 0.30 must differ."""
    spy, vix = _load_smoke_data()
    params = _base_params()
    t10 = _run(spy, vix, params, profit_lock_mode="trailing", profit_lock_trail_pct=0.10)
    t30 = _run(spy, vix, params, profit_lock_mode="trailing", profit_lock_trail_pct=0.30)
    assert _pnl_signature(t10) != _pnl_signature(t30), (
        "trail_pct=0.10 vs 0.30 produced IDENTICAL books -- profit_lock_trail_pct is not "
        "reaching the simulator through run_cell (the T-W2 dead-knob regression)"
    )


def test_fixed_vs_trailing_mode_varies_the_book():
    """profit_lock_mode itself ('fixed' vs 'trailing') must also bind."""
    spy, vix = _load_smoke_data()
    params = _base_params()
    fixed = _run(spy, vix, params, profit_lock_mode="fixed", profit_lock_trail_pct=0.0)
    trailing = _run(spy, vix, params, profit_lock_mode="trailing", profit_lock_trail_pct=0.20)
    assert _pnl_signature(fixed) != _pnl_signature(trailing), (
        "fixed vs trailing(0.20) produced IDENTICAL books -- profit_lock_mode is not "
        "reaching the simulator through run_cell (the exact T5-scar regression: "
        "181/181 fixed-vs-trailing P4 pairs were byte-identical)"
    )


def test_time_stop_minutes_before_close_varies_the_book():
    """The third T-W2 knob (ground rule 13 lists lock/trail/time-exit together)."""
    spy, vix = _load_smoke_data()
    params = _base_params()
    default_ts = _run(spy, vix, params, profit_lock_mode="fixed", profit_lock_trail_pct=0.0,
                       time_stop_minutes_before_close=10)
    early_ts = _run(spy, vix, params, profit_lock_mode="fixed", profit_lock_trail_pct=0.0,
                    time_stop_minutes_before_close=180)  # forces flat at 13:00 ET
    assert _pnl_signature(default_ts) != _pnl_signature(early_ts), (
        "time_stop_minutes_before_close=10 vs 180 produced IDENTICAL books -- the time-exit "
        "kwarg is not reaching the simulator through run_cell"
    )


def test_params_to_kwargs_guard_untouched():
    """This fix must NOT weaken L156 -- profit_lock_* must still be absent from
    _params_to_kwargs's output. Re-import and re-assert here (belt-and-suspenders on top of
    test_profit_lock_not_in_baseline.py, which is the canonical owner of this assertion)."""
    from lib.orchestrator import _params_to_kwargs

    overrides = {
        "premium_stop_pct": -0.08,
        "profit_lock_mode": "trailing",
        "profit_lock_trail_pct": 0.42,
    }
    kwargs = _params_to_kwargs(overrides)
    leaked = sorted(k for k in kwargs if "profit_lock" in k)
    assert not leaked, (
        f"T-W2 must fix the dead knob WITHOUT touching _params_to_kwargs (L156) -- "
        f"found leaked keys {leaked}. The fix belongs in run_cell's explicit kwargs, not here."
    )

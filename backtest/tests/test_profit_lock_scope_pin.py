"""PIN: simulate_trade_real's profit-lock arms PRE-TP1 on the WHOLE position.

THE SCOPE MISMATCH THIS PINS (found 2026-07-09 building the vwap entry/exit matrix):
simulator_real:540-584 runs the profit-lock ratchet EVERY bar with no tp1_filled check,
and the ratcheted `runner_stop_premium` IS the pre-TP1 exit-ALL stop (sim:644). The live
decision core (automation/state/fleet/exit_manager.plan_exit_actions) only armed the lock
at/after TP1 -- so every ratified scorecard produced through this simulator with
profit_lock_threshold_pct>0 (vwapcont-exit-parity.json 2026-07-02, vwapcont-exit-ab-ship-
gate.json 2026-07-07 -- BASE_SHAPE pins thr=0.05) credited pre-TP1 breakeven scratches the
live machine could not take.

RESOLUTION (2026-07-09): exit_manager gained an EXPRESSIBLE `profit_lock_arm_scope` field
("post_tp1" default = legacy live behavior; "full" = this simulator's semantics), armed by
NO live shape; exit-shape ratification numbers come from exit_manager replay.

WHY A PIN AND NOT A FIX: the two machines' semantics are now a DOCUMENTED, guarded pair.
  * this file REDs if someone silently TP1-gates the simulator's lock (which would silently
    re-base every historical sim study), and
  * automation/state/fleet/test_exit_manager.py::test_pre_tp1_lock_* REDs if someone
    silently changes the live core's default scope.
Converging the two is allowed ONLY as a conscious, scorecard-backed decision -- change the
respective pin in the SAME commit and say why (C14-class cross-machine guard).

Synthetic put contract monkeypatched into the disk loader (mirrors
test_chandelier_regime.py's harness). No disk, no OPRA.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from lib import simulator_real as sr
from lib.simulator_real import simulate_trade_real

_DATE = dt.date(2025, 3, 3)  # arbitrary weekday; no real data touched
_N = 20


def _spy_frame(n: int) -> pd.DataFrame:
    rows = []
    t = dt.datetime.combine(_DATE, dt.time(9, 30))
    for _ in range(n):
        rows.append({"timestamp_et": pd.Timestamp(t), "open": 600.0, "high": 600.05,
                     "low": 599.95, "close": 600.0, "volume": 1_000_000})
        t += dt.timedelta(minutes=5)
    df = pd.DataFrame(rows)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    return df


def _opt_frame(premiums: list[float]) -> pd.DataFrame:
    rows = []
    t = dt.datetime.combine(_DATE, dt.time(9, 30))
    for p in premiums:
        rows.append({"timestamp_et": pd.Timestamp(t), "open": p, "high": p,
                     "low": p, "close": p, "volume": 5000, "vwap": p, "trade_count": 50})
        t += dt.timedelta(minutes=5)
    df = pd.DataFrame(rows)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    return df


def _flat_ribbon(n: int) -> pd.DataFrame:
    # side P's flip-back needs a BULL stack; keep BEAR so ribbon exits never fire.
    return pd.DataFrame({"fast": [600.0] * n, "pivot": [600.0] * n, "slow": [600.0] * n,
                         "stack": ["BEAR"] * n, "spread_cents": [5.0] * n})


@pytest.fixture
def patch_loader(monkeypatch):
    def _install(opt_df: pd.DataFrame):
        monkeypatch.setattr(sr, "load_contract_bars", lambda symbol: opt_df)
    return _install


# Entry at idx 2 -> fill on the NEXT 5m bar (opt index 3, premium 1.00). The path then
# touches +6% (>= the +5% arm), pulls back through entry, and keeps falling:
#   idx:      0    1    2    3(entry) 4     5     6     7    8+
_PREMIUMS = [1.0, 1.0, 1.0, 1.00,    1.06, 1.02, 0.99, 0.90] + [0.85] * (_N - 8)


def _run(patch_installer, **kwargs):
    spy = _spy_frame(_N)
    ribbon = _flat_ribbon(_N)
    patch_installer(_opt_frame(_PREMIUMS))
    bar = spy.iloc[2]
    base = dict(
        entry_bar_idx=2, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
        rejection_level=10_000.0, triggers_fired=["t"], side="P", qty=3, setup="UNIT",
        premium_stop_pct=-0.06, strike_offset=0, use_tiered_exits=False,
        entry_slippage=0.0, exit_slippage=0.0,
    )
    base.update(kwargs)
    return simulate_trade_real(**base)


def test_sim_lock_arms_pre_tp1_and_scratches_the_whole_position(patch_loader):
    """thr=0.05/offset=0 (the exact vwap ship-gate BASE_SHAPE lock): the +6% touch arms a
    BE floor on ALL units BEFORE any TP1 (TP1 fallback +30% = 1.30, never reached), and the
    pullback exits the whole position at entry -> pnl EXACTLY 0.0. The scratch reuses the
    EXIT_ALL_PREMIUM_STOP label (disclosed: the label does not distinguish the lock floor)."""
    fill = _run(patch_loader, profit_lock_threshold_pct=0.05,
                profit_lock_stop_offset_pct=0.0, profit_lock_mode="fixed")
    assert fill is not None
    assert fill.entry_premium == 1.00
    assert fill.exit_reason.name == "EXIT_ALL_PREMIUM_STOP"
    assert fill.runner_exit_premium == 1.00      # the ratcheted BE floor, NOT 0.94
    assert fill.dollar_pnl == 0.0                # the breakeven scratch live never had


def test_sim_without_lock_takes_the_full_stop_on_the_same_path(patch_loader):
    """Same path, thr=0 (lock off): the pullback bar (0.99) is a HOLD and the position
    rides to the -6% stop -> -$18 on 3 contracts. This is what the LIVE default
    (post_tp1 scope) does on this path -- the divergence the 2026-07-09 finding measured."""
    fill = _run(patch_loader, profit_lock_threshold_pct=0.0,
                profit_lock_stop_offset_pct=0.0, profit_lock_mode="fixed")
    assert fill is not None
    assert fill.exit_reason.name == "EXIT_ALL_PREMIUM_STOP"
    assert fill.runner_exit_premium == pytest.approx(0.94)  # the original -6% stop
    assert fill.dollar_pnl == pytest.approx(-18.0)          # (0.94 - 1.00) * 3 * 100

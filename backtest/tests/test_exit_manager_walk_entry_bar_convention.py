"""Pins the entry-bar eligibility convention ruled on 2026-07-25.

RULING (markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md): a position placed on tick N is
NOT exit-checked until tick N+1, because the live tick manages exits BEFORE evaluating a new entry
(heartbeat_core.py:975-987, armed in prod via run-heartbeat-core.ps1:12). So the entry bar's own
quote must never resolve the position.

WHY THIS FILE EXISTS: this one convention explained 91.1% of a $39.71/trade parity gap between
replay engines (EXIT-ENGINE-PARITY-RESIDUAL). `exit_manager_walk.py:167` implements it as a strict
`>`; a future refactor relaxing that to `>=` would silently reintroduce the gap across every
replay-based study at once. These tests fail if that happens.

NOTE ON FIXTURE DESIGN: walk_exit_manager POINT-SAMPLES `bar["open"]` as both best and worst
(exit_manager_walk.py:181-187) -- it deliberately does NOT read bar high/low, because the live
actuator reads a single NBBO snapshot per tick. So the trap bar here is built on `open`, not `low`.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest" / "lib"))

import pandas as pd  # noqa: E402

import exit_manager_walk as emw  # noqa: E402

ENTRY_TS = "2026-01-01 12:00:00"
ENTRY_PREMIUM = 1.00
# premium_stop_pct -0.50 on a $1.00 entry -> runner stop at $0.50.
STOP_TRIPPING_OPEN = 0.10   # far below the stop: resolves instantly IF the bar is evaluated
BENIGN_OPEN = 1.00          # at entry: triggers nothing

# TP1 / runner / profit-lock deliberately set unreachable so `premium_stop` is the ONLY stage
# this fixture can produce -- the test then reads purely as "did the entry bar get evaluated".
SHAPE = {
    "stop_mode": "premium",
    "premium_stop_pct": -0.50,
    "tp1_premium_pct": 50.0,
    "tp1_qty_fraction": 0.667,
    "profit_lock_mode": "fixed",
    "runner_target_pct": 99.0,
    "trail_pct": 0.125,
    "profit_lock_arm_pct": 50.0,
}


def _opt_df(opens: list[tuple[str, float]]) -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp_et": pd.to_datetime([t for t, _ in opens]),
        "open": [o for _, o in opens],
        "high": [o for _, o in opens],
        "low": [o for _, o in opens],
        "close": [o for _, o in opens],
    })


def _spy_df() -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp_et": pd.to_datetime([ENTRY_TS, "2026-01-01 12:05:00", "2026-01-01 12:10:00"]),
        "open": [600.0] * 3, "high": [600.5] * 3, "low": [599.5] * 3, "close": [600.0] * 3,
    })


def _walk(opt_df: pd.DataFrame) -> emw.WalkResult:
    return emw.walk_exit_manager(
        symbol="SPY260101P00600000", side="P",
        entry_time_et=dt.datetime(2026, 1, 1, 12, 0, 0),
        entry_premium=ENTRY_PREMIUM, qty=3,
        exit_shape=SHAPE, structure_stop_enabled=False, trigger_level=None,
        strategy="ribbon_ride", time_stop_et=dt.time(15, 40),
        opt_df=opt_df, ribbon_tick_df=None, five_min_spy_df=_spy_df(),
    )


# --------------------------------------------------------------------- THE regression this pins
def test_entry_bar_own_quote_never_resolves_the_position():
    """A stop-tripping quote ON the entry bar must be ignored -- it precedes the position."""
    res = _walk(_opt_df([
        (ENTRY_TS, STOP_TRIPPING_OPEN),          # the trap: would stop out instantly if evaluated
        ("2026-01-01 12:05:00", BENIGN_OPEN),
        ("2026-01-01 12:10:00", BENIGN_OPEN),
    ]))
    assert "premium_stop" not in res.exit_reason, (
        f"entry bar was evaluated -- got {res.exit_reason!r}. exit_manager_walk.py:167 must stay "
        "a STRICT '>' (see markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md)")
    assert res.n_ticks_walked == 2, "only the two bars strictly after entry may be walked"


def test_positive_control_same_quote_one_bar_later_DOES_stop():
    """Guards against a vacuous test: the fixture must be capable of stopping out at all."""
    res = _walk(_opt_df([
        (ENTRY_TS, BENIGN_OPEN),
        ("2026-01-01 12:05:00", STOP_TRIPPING_OPEN),   # same quote, one bar later
        ("2026-01-01 12:10:00", BENIGN_OPEN),
    ]))
    assert "premium_stop" in res.exit_reason, (
        "fixture cannot produce a stop at all -- the sibling test would be vacuous")
    assert res.resolved is True


def test_exit_never_timestamped_at_the_entry_bar():
    """Even when it does resolve, resolution can never be stamped on the entry bar itself."""
    res = _walk(_opt_df([
        (ENTRY_TS, STOP_TRIPPING_OPEN),
        ("2026-01-01 12:05:00", STOP_TRIPPING_OPEN),
        ("2026-01-01 12:10:00", BENIGN_OPEN),
    ]))
    assert res.resolved is True
    assert pd.Timestamp(res.exit_time_et) > pd.Timestamp(ENTRY_TS)


def test_single_bar_day_cannot_resolve():
    """If the entry bar is the ONLY bar, there is no eligible tick -- must not invent one."""
    res = _walk(_opt_df([(ENTRY_TS, STOP_TRIPPING_OPEN)]))
    assert res.exit_reason == "no_bars_after_entry"
    assert res.n_ticks_walked == 0
    assert res.dollar_pnl == 0.0

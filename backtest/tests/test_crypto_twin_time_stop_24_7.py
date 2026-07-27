"""Pins TWIN-TIMESTOP: SPY's 15:50 EOD flatten must never apply to a 24/7 crypto position.

THE DEFECT (measured 2026-07-26): `manage_positions` called `em.plan_exit_actions` WITHOUT
`time_stop_et`, so exit_manager's SPY default of 15:50 ET silently won. That check is
`now_et >= time_stop_et` (exit_manager.py:357) -- not a single daily boundary but TRUE for
every tick from 15:50 ET until ET midnight. On a 24/7 instrument the twin therefore spent
~8h10m of every day (~34% of ticks) opening a position and force-closing it on the next tick.

Evidence it was real, not theoretical: 6 of the twin's first 8 organic round trips exited on
"time_stop_15:50" between 21:13 and 22:38 ET with ~5-minute holds. Every one lost.

BTC has no session close, so duration is bounded by max_hold_hours instead.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

import exit_manager as em  # noqa: E402

import crypto_twin_core as ctc  # noqa: E402

# The window that used to be a dead zone: after SPY's close, before ET midnight.
DEAD_ZONE = [dt.time(15, 50), dt.time(18, 0), dt.time(21, 13), dt.time(22, 38), dt.time(23, 59)]


def _state():
    return em.ExitState.from_entry(
        symbol="BTC/USD", side="C", entry_premium=65000.0, qty=3,
        exit_shape={"stop_mode": "premium", "premium_stop_pct": -0.50,
                    "tp1_premium_pct": 50.0, "tp1_qty_fraction": 0.667,
                    "profit_lock_mode": "fixed", "runner_target_pct": 99.0,
                    "trail_pct": 0.125, "profit_lock_arm_pct": 50.0},
        strategy="ribbon_ride", trigger_level=None, structure_stop_enabled=False)


def _plan(now_et: dt.time, time_stop_et: dt.time):
    """Neutral quote: nothing but the time stop could possibly close this position."""
    return em.plan_exit_actions(_state(), best_premium=65000.0, worst_premium=65000.0,
                                open_qty=3, now_et=now_et, ribbon_flip_back=False,
                                last_closed_5m_close=None, time_stop_et=time_stop_et)


def _fired(dec) -> bool:
    return any(getattr(a, "stage", "") == "time_stop" for a in dec.actions)


# ------------------------------------------------------------------ the config itself
def test_twin_config_disables_the_wall_clock_time_stop():
    cfg = ctc.TwinConfig()
    assert cfg.wall_clock_time_stop_et == dt.time(23, 59, 59, 999999), (
        "the 24/7 sentinel was changed -- SPY's 15:50 EOD flatten must not govern BTC")


# ------------------------------------------------------------------ behaviour, both ways
def test_no_time_stop_anywhere_in_the_former_dead_zone():
    cfg = ctc.TwinConfig()
    for t in DEAD_ZONE:
        assert not _fired(_plan(t, cfg.wall_clock_time_stop_et)), (
            f"time_stop fired at {t} ET -- this is the ~34%-of-day force-close bug")


def test_positive_control_the_spy_default_DOES_fire_there():
    """Anti-vacuity: prove the dead zone is real under the old (omitted-arg) behaviour."""
    for t in DEAD_ZONE:
        assert _fired(_plan(t, em.TIME_STOP_ET)), (
            f"expected SPY's 15:50 default to force-close at {t} ET")


def test_the_bug_was_an_omitted_argument_not_a_wrong_value():
    """Calling without time_stop_et falls back to SPY's 15:50 -- the original defect."""
    dec = em.plan_exit_actions(_state(), best_premium=65000.0, worst_premium=65000.0,
                               open_qty=3, now_et=dt.time(21, 13), ribbon_flip_back=False,
                               last_closed_5m_close=None)
    assert _fired(dec), "if this stops firing, exit_manager's default changed -- re-audit"


def test_max_hold_remains_the_real_duration_bound():
    """Removing the wall clock must not remove ALL duration bounding."""
    assert ctc.TwinConfig().max_hold_hours > 0

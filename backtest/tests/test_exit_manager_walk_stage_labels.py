"""EXITMGR-STAGE-LABEL-CONFLATION guard (2026-07-23) -- exit_manager_walk.py side.

exit_manager.py's plan_exit_actions now emits a distinct "profit_lock_floor" stage
(previously hardcoded "premium_stop" even when the pre-TP1 profit-lock floor, not the
static catastrophe cap, fired). exit_manager_walk.py directly consumes `a.stage` in
`_stage_fill_level` to pick a fill price for the live-parity bar walk. This pins that the
NEW stage name still resolves to the SAME limit-style fill level as "premium_stop" (both
are the same `runner_stop` check -- only the journal label split), and is NOT accidentally
treated as a market-fill stage. A regression that forgets to extend `_stage_fill_level`
(or `_MARKET_STAGES`) when a new stage name is introduced REDs here instead of silently
changing simulated fill prices for every future profit-lock-floor exit.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "automation" / "state" / "fleet"))

import exit_manager as em  # noqa: E402
from exit_manager_walk import _MARKET_STAGES, _stage_fill_level  # noqa: E402


def _state(runner_stop):
    return em.ExitState(
        symbol="SPY260723C00740000", side="C", entry_premium=1.00,
        total_qty=5, tp1_qty=4, runner_qty=1,
        premium_stop_pct=-0.20, tp1_premium_pct=0.30, profit_lock_mode="trailing",
        runner_stop_premium=runner_stop,
    )


def test_profit_lock_floor_is_not_a_market_stage():
    assert "profit_lock_floor" not in _MARKET_STAGES
    assert "premium_stop" not in _MARKET_STAGES


def test_profit_lock_floor_fills_at_same_level_as_premium_stop():
    state_in = _state(runner_stop=1.00)  # BE floor, e.g. arm+ratchet already applied
    state_after = state_in
    level_cap = _stage_fill_level("premium_stop", state_in, state_after)
    level_floor = _stage_fill_level("profit_lock_floor", state_in, state_after)
    assert level_cap == level_floor == 1.00


def test_premium_stop_falls_back_to_entry_derived_level_when_runner_stop_unset():
    state_in = _state(runner_stop=None)
    level = _stage_fill_level("profit_lock_floor", state_in, state_in)
    assert level == 1.00 * (1.0 + state_in.premium_stop_pct)

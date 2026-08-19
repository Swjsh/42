"""Guards for weekly/lib/kill_switch.py -- Rule 5 re-derived for a multi-day lane.

Loaded by explicit file path (not package import), matching the existing backtest/tests
convention (see test_book_exposure_2026_08_18.py) -- pins the exact module under test
regardless of how pytest resolves package roots.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load(name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


ks = _load("weekly_kill_switch_under_test", "weekly/lib/kill_switch.py")


def _params(**risk_overrides) -> dict:
    risk = {
        "max_concurrent_positions": 2,
        "correlation_gate": {"deny_abs_r_gte": 0.70, "lookback_days": 60, "fail_mode": "closed"},
        "per_trade_risk_cap_pct": 0.30,
        "min_contracts": 3,
        "daily_loss_kill_switch_pct": 0.30,
        "kill_switch_semantics": "blocks_new_entries_only",
    }
    risk.update(risk_overrides)
    return {"risk": risk, "exits": {"catastrophe_stop_pct": -50.0}}


SOD_EQUITY = 5000.0  # floor at 30% = -$1,500


# --- daily kill switch: realized-only trip ------------------------------------------------

def test_trips_on_realized_loss_at_or_past_the_floor() -> None:
    r = ks.evaluate_daily_kill_switch(
        realized_pnl_today=-1600.0, start_of_day_equity=SOD_EQUITY,
        unrealized_pnl_today=0.0, params=_params(),
    )
    assert r["kill_switch_tripped"] is True
    assert r["code"] == ks.CODE_KILL_TRIPPED
    assert r["action"] == ks.ACTION_BLOCK_NEW_ENTRIES_ONLY


def test_allows_when_realized_loss_is_under_the_floor() -> None:
    r = ks.evaluate_daily_kill_switch(
        realized_pnl_today=-800.0, start_of_day_equity=SOD_EQUITY,
        unrealized_pnl_today=0.0, params=_params(),
    )
    assert r["kill_switch_tripped"] is False
    assert r["code"] == ks.CODE_OK
    assert r["action"] == ks.ACTION_NONE


def test_boundary_is_inclusive_at_exactly_the_floor() -> None:
    r = ks.evaluate_daily_kill_switch(
        realized_pnl_today=-1500.0, start_of_day_equity=SOD_EQUITY,  # exactly -30%
        unrealized_pnl_today=0.0, params=_params(),
    )
    assert r["kill_switch_tripped"] is True


def test_does_not_trip_on_unrealized_only_drawdown() -> None:
    """THE LOAD-BEARING DESIGN DECISION (RED-proofed). A huge UNREALIZED swing on an open
    multi-day position must never trip the daily kill switch on its own -- only REALIZED
    P&L does. Realized P&L here is flat/positive; unrealized is catastrophic. Must NOT trip."""
    r = ks.evaluate_daily_kill_switch(
        realized_pnl_today=50.0, start_of_day_equity=SOD_EQUITY,
        unrealized_pnl_today=-4000.0,  # far past what would trip on equity alone
        params=_params(),
    )
    assert r["kill_switch_tripped"] is False, (
        "unrealized-only drawdown must never trip the daily kill switch -- "
        f"got tripped=True on realized=+50, unrealized=-4000: {r}"
    )
    assert r["action"] == ks.ACTION_NONE
    # Unrealized is REPORTED (visibility is the product) even though it didn't trip anything.
    assert r["unrealized_pnl_today_reported_only"] == pytest.approx(-4000.0)


def test_unrealized_is_always_reported_even_when_realized_also_trips() -> None:
    r = ks.evaluate_daily_kill_switch(
        realized_pnl_today=-1600.0, start_of_day_equity=SOD_EQUITY,
        unrealized_pnl_today=+900.0,  # position recovering -- must not mask the trip
        params=_params(),
    )
    assert r["kill_switch_tripped"] is True
    assert r["unrealized_pnl_today_reported_only"] == pytest.approx(900.0)


def test_kill_switch_blocks_entries_but_never_returns_a_close_or_liquidate_action() -> None:
    """The other half of the load-bearing decision: tripped or not, this module's `action`
    is ALWAYS one of exactly two values, and no close/liquidate directive is ever present."""
    tripped = ks.evaluate_daily_kill_switch(
        realized_pnl_today=-1600.0, start_of_day_equity=SOD_EQUITY,
        unrealized_pnl_today=-4000.0, params=_params(),
    )
    clean = ks.evaluate_daily_kill_switch(
        realized_pnl_today=0.0, start_of_day_equity=SOD_EQUITY,
        unrealized_pnl_today=-4000.0, params=_params(),
    )
    for r in (tripped, clean):
        assert r["action"] in (ks.ACTION_NONE, ks.ACTION_BLOCK_NEW_ENTRIES_ONLY)
        forbidden_keys = {"close_position", "close_positions", "liquidate", "cancel_order", "force_close"}
        assert not (set(r.keys()) & forbidden_keys), f"unexpected close/liquidate key in result: {r}"
        assert "close" not in str(r["action"]).lower()
        assert "liquidat" not in str(r["action"]).lower()
    assert tripped["action"] == ks.ACTION_BLOCK_NEW_ENTRIES_ONLY
    assert clean["action"] == ks.ACTION_NONE


def test_fails_closed_on_unreadable_realized_pnl() -> None:
    r = ks.evaluate_daily_kill_switch(
        realized_pnl_today=None, start_of_day_equity=SOD_EQUITY,
        unrealized_pnl_today=0.0, params=_params(),
    )
    assert r["kill_switch_tripped"] is True
    assert r["action"] == ks.ACTION_BLOCK_NEW_ENTRIES_ONLY
    assert r["code"] == ks.CODE_UNREADABLE_INPUT, "data-unavailable must be distinguishable from a genuine trip"


def test_fails_closed_on_missing_params_key() -> None:
    bad_params = _params()
    del bad_params["risk"]["daily_loss_kill_switch_pct"]
    r = ks.evaluate_daily_kill_switch(
        realized_pnl_today=0.0, start_of_day_equity=SOD_EQUITY,
        unrealized_pnl_today=0.0, params=bad_params,
    )
    assert r["kill_switch_tripped"] is True
    assert r["code"] == ks.CODE_UNREADABLE_INPUT


def test_refuses_to_silently_run_an_unsupported_semantics() -> None:
    bad_params = _params(kill_switch_semantics="force_close_on_trip")
    r = ks.evaluate_daily_kill_switch(
        realized_pnl_today=0.0, start_of_day_equity=SOD_EQUITY,
        unrealized_pnl_today=0.0, params=bad_params,
    )
    # Still fails closed (blocks), never silently does what the bad config asked.
    assert r["action"] == ks.ACTION_BLOCK_NEW_ENTRIES_ONLY
    assert r["code"] == ks.CODE_UNREADABLE_INPUT
    assert "force_close_on_trip" in r["reason"]


def test_never_a_bare_bool() -> None:
    r = ks.evaluate_daily_kill_switch(
        realized_pnl_today=0.0, start_of_day_equity=SOD_EQUITY,
        unrealized_pnl_today=0.0, params=_params(),
    )
    assert isinstance(r, dict) and "code" in r and "reason" in r and "action" in r


# --- position-inception-baseline catastrophe check ------------------------------------------

def test_position_catastrophe_breaches_from_its_own_entry() -> None:
    r = ks.check_position_catastrophe("GLD", entry_premium=2.00, current_premium=0.90, params=_params())
    assert r["breached"] is True
    assert r["pct_move_from_own_entry"] == pytest.approx(-55.0)


def test_position_catastrophe_does_not_breach_within_the_floor() -> None:
    r = ks.check_position_catastrophe("GLD", entry_premium=2.00, current_premium=1.10, params=_params())
    assert r["breached"] is False
    assert r["pct_move_from_own_entry"] == pytest.approx(-45.0)


def test_position_catastrophe_boundary_is_inclusive() -> None:
    r = ks.check_position_catastrophe("GLD", entry_premium=2.00, current_premium=1.00, params=_params())  # exactly -50%
    assert r["breached"] is True


def test_position_catastrophe_signature_has_no_start_of_day_baseline() -> None:
    """Structural pin: the function signature itself proves the baseline is the position's
    OWN entry, not start-of-day equity -- there is no start_of_day parameter to pass."""
    import inspect
    params_list = list(inspect.signature(ks.check_position_catastrophe).parameters)
    assert "start_of_day_equity" not in params_list
    assert "entry_premium" in params_list


def test_position_catastrophe_fails_closed_on_missing_params() -> None:
    bad_params = _params()
    del bad_params["exits"]["catastrophe_stop_pct"]
    r = ks.check_position_catastrophe("GLD", entry_premium=2.00, current_premium=0.10, params=bad_params)
    assert r["breached"] is None
    assert r["code"] == ks.CODE_UNREADABLE_INPUT


def test_position_catastrophe_never_a_bare_bool() -> None:
    r = ks.check_position_catastrophe("GLD", entry_premium=2.00, current_premium=1.10, params=_params())
    assert isinstance(r, dict) and "code" in r and "reason" in r


# --- structural guard: Stage A is shadow-only -- no order-placement or force-close call ----------

def test_kill_switch_module_never_places_cancels_closes_or_liquidates() -> None:
    src = (REPO / "weekly" / "lib" / "kill_switch.py").read_text(encoding="utf-8")
    forbidden = [
        "place_option_order", "place_stock_order", "place_crypto_order", "place_order(",
        "cancel_order", "cancel_all_orders", "close_position(", "close_all_positions",
        "replace_order_by_id", "mcp__alpaca", "liquidate(",
    ]
    hits = [f for f in forbidden if f in src]
    assert not hits, f"kill_switch.py must never place/cancel/close/liquidate -- found: {hits}"


def test_assert_never_force_closes_anchor_exists_and_is_callable() -> None:
    assert ks._assert_never_force_closes_positions() is None

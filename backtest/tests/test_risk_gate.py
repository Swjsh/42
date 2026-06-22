"""Tests for the consolidated risk gate (backtest/lib/risk_gate.py).

This is risk code — the suite is deliberately exhaustive on two fronts:
  1. Every Deny code fires on its specific trigger, and a clean order Allows.
  2. FAIL-CLOSED: every unreadable input (None / NaN / unparseable / out-of-
     domain) produces UNREADABLE_INPUT, never a silent Allow.

Plus: per-account kill-switch isolation (Safe halt != Bold halt), immutability
of the returned decisions, and the OP-32 invariant that this module can never
lock out a human session.

Run:  cd backtest && python -m pytest tests/test_risk_gate.py -q
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.risk_gate import (  # noqa: E402
    Allow,
    Deny,
    RiskDecision,
    check_order,
    order_affordable,
    max_affordable_qty,
    CODE_ALLOW,
    CODE_KILL_SWITCH,
    CODE_RISK_CAP,
    CODE_MAX_PREMIUM_TIER,
    CODE_MIN_CONTRACTS,
    CODE_PDT,
    CODE_FIRST_ENTRY_LOCK,
    CODE_NOT_FLAT,
    CODE_UNREADABLE_INPUT,
)


# --- representative params for each account (mirrors params.json values) -----

SAFE_PARAMS = {
    "per_trade_risk_cap_pct": 0.30,
    "daily_loss_kill_switch_pct": 0.30,
    "min_contracts": 3,
    "first_entry_after_stop_blocked": True,
    "v15_max_premium_pct_of_account": [
        {"equity_min": 0, "equity_max": 2000, "max_pct": 0.4},
        {"equity_min": 2000, "equity_max": 10000, "max_pct": 0.3},
        {"equity_min": 10000, "equity_max": 25000, "max_pct": 0.25},
        {"equity_min": 25000, "equity_max": 999999999, "max_pct": 0.2},
    ],
}

BOLD_PARAMS = {
    "per_trade_risk_cap_pct": 0.50,
    "daily_loss_kill_switch_pct": 0.50,
    "min_contracts": 5,
    "first_entry_after_stop_blocked": True,
    # Bold params.json has no v15_max_premium table; omit it -> tier gate inert.
}

SETUP = "BEARISH_REJECTION_RIDE_THE_RIBBON"


def _clean_safe(**overrides) -> RiskDecision:
    """A known-clean Safe order; override one field per test to trip a rule.

    Baseline: $2,000 equity, 3 contracts @ $1.00 = $300 notional.
    $300 < 30% risk cap ($600) and < 40% tier cap ($800) -> Allow.
    """
    kwargs = dict(
        account="Gamma-Safe-2",
        equity=2000.0,
        start_of_day_equity=2000.0,
        proposed_qty=3,
        premium=1.00,
        setup_name=SETUP,
        current_position_status="flat",
        day_trades_used_5d=0,
        kill_switch_tripped=False,
        prior_stops_today=[],
        params=SAFE_PARAMS,
    )
    kwargs.update(overrides)
    return check_order(kwargs.pop("account"), **kwargs)


# =============================================================================
# 1. Clean order Allows
# =============================================================================

def test_clean_safe_order_allows():
    d = _clean_safe()
    assert isinstance(d, Allow)
    assert d.allowed is True
    assert d.code == CODE_ALLOW
    assert bool(d) is True  # `if decision:` truthiness


def test_clean_bold_order_allows():
    # Bold: $1,673 equity, 5 contracts @ $1.00 = $500 < 50% cap ($836).
    d = check_order(
        "Gamma-Risky-2",
        equity=1673.0,
        start_of_day_equity=1673.0,
        proposed_qty=5,
        premium=1.00,
        setup_name=SETUP,
        current_position_status="flat",
        day_trades_used_5d=0,
        kill_switch_tripped=False,
        prior_stops_today=[],
        params=BOLD_PARAMS,
    )
    assert isinstance(d, Allow), d.reason


def test_flat_synonyms_all_allow():
    for status in ("flat", "FLAT", "none", "", None, "no_position", {"qty": 0}):
        d = _clean_safe(current_position_status=status)
        assert isinstance(d, Allow), f"status={status!r} should be flat -> {d.reason}"


# =============================================================================
# 2. Each Deny reason fires on its trigger
# =============================================================================

def test_kill_switch_latch_denies():
    d = _clean_safe(kill_switch_tripped=True)
    assert isinstance(d, Deny)
    assert d.code == CODE_KILL_SWITCH
    assert d.allowed is False
    assert bool(d) is False


def test_kill_switch_drawdown_denies():
    # Safe -30%: SoD $2,000 -> floor $1,400. Equity at $1,399 trips it.
    d = _clean_safe(equity=1399.0, start_of_day_equity=2000.0)
    assert isinstance(d, Deny)
    assert d.code == CODE_KILL_SWITCH


def test_kill_switch_exactly_at_floor_denies():
    # Boundary: equity == floor is a trip (<=).
    d = _clean_safe(equity=1400.0, start_of_day_equity=2000.0)
    assert isinstance(d, Deny)
    assert d.code == CODE_KILL_SWITCH


def test_just_above_kill_floor_allows():
    # $1,401 > floor $1,400, and 3@$1 = $300 still within $1,401*0.30 cap.
    d = _clean_safe(equity=1401.0, start_of_day_equity=2000.0)
    assert isinstance(d, Allow), d.reason


def test_pdt_denies_under_25k():
    d = _clean_safe(day_trades_used_5d=3)
    assert isinstance(d, Deny)
    assert d.code == CODE_PDT


def test_pdt_inert_at_or_above_25k():
    # >=25K margin accounts are exempt from PDT. Use bigger order to stay valid.
    d = _clean_safe(
        equity=30000.0, start_of_day_equity=30000.0, day_trades_used_5d=9,
        proposed_qty=3, premium=1.00,
    )
    assert isinstance(d, Allow), d.reason


def test_pdt_two_daytrades_allows():
    # Only the 4th (>=3 used) is blocked; 2 used is fine.
    d = _clean_safe(day_trades_used_5d=2)
    assert isinstance(d, Allow), d.reason


def test_not_flat_denies():
    d = _clean_safe(current_position_status="long_2_contracts")
    assert isinstance(d, Deny)
    assert d.code == CODE_NOT_FLAT


def test_not_flat_open_mapping_denies():
    d = _clean_safe(current_position_status={"qty": 2, "status": "open"})
    assert isinstance(d, Deny)
    assert d.code == CODE_NOT_FLAT


def test_first_entry_lock_denies_when_setup_stopped():
    d = _clean_safe(prior_stops_today=[SETUP])
    assert isinstance(d, Deny)
    assert d.code == CODE_FIRST_ENTRY_LOCK


def test_first_entry_lock_allows_different_setup():
    d = _clean_safe(prior_stops_today=["SOME_OTHER_SETUP"])
    assert isinstance(d, Allow), d.reason


def test_first_entry_lock_disabled_by_param():
    params = dict(SAFE_PARAMS, first_entry_after_stop_blocked=False)
    d = _clean_safe(prior_stops_today=[SETUP], params=params)
    assert isinstance(d, Allow), d.reason


def test_min_contracts_denies():
    d = _clean_safe(proposed_qty=2)
    assert isinstance(d, Deny)
    assert d.code == CODE_MIN_CONTRACTS


def test_min_contracts_bold_floor_is_five():
    # Bold min_contracts=5; a 4-lot is below the floor.
    d = check_order(
        "Gamma-Risky-2",
        equity=1673.0, start_of_day_equity=1673.0, proposed_qty=4, premium=1.00,
        setup_name=SETUP, current_position_status="flat", day_trades_used_5d=0,
        kill_switch_tripped=False, prior_stops_today=[], params=BOLD_PARAMS,
    )
    assert isinstance(d, Deny)
    assert d.code == CODE_MIN_CONTRACTS


def test_risk_cap_denies():
    # 30 contracts @ $1.00 = $3,000 notional > 30% of $2,000 ($600).
    # min_contracts passes (30>=3); risk cap is what bites. tier present but
    # risk cap is checked first.
    d = _clean_safe(proposed_qty=30, premium=1.00)
    assert isinstance(d, Deny)
    assert d.code == CODE_RISK_CAP


def test_max_premium_tier_denies_when_tighter_than_risk_cap():
    # Construct a case where notional is BELOW the risk cap but ABOVE the v15
    # tier cap, so the distinct MAX_PREMIUM_TIER code fires.
    # Use a params variant whose tier (0.20) is tighter than risk cap (0.30).
    params = dict(
        SAFE_PARAMS,
        per_trade_risk_cap_pct=0.50,  # loosen blanket cap -> $1,000
        v15_max_premium_pct_of_account=[
            {"equity_min": 0, "equity_max": 999999999, "max_pct": 0.20},  # $400
        ],
    )
    # 5 @ $1.50 = $750: under risk cap ($1,000) but over tier cap ($400).
    d = _clean_safe(proposed_qty=5, premium=1.50, params=params)
    assert isinstance(d, Deny)
    assert d.code == CODE_MAX_PREMIUM_TIER


def test_oversized_bold_replays_2026_06_15_incident():
    # The exact live incident: Bold 5 x $2.06 = $1,030 on a $1,122 account (92%).
    # Must DENY (risk cap = 50% = $561).
    d = check_order(
        "Gamma-Risky-2",
        equity=1122.0, start_of_day_equity=1122.0, proposed_qty=5, premium=2.06,
        setup_name=SETUP, current_position_status="flat", day_trades_used_5d=0,
        kill_switch_tripped=False, prior_stops_today=[], params=BOLD_PARAMS,
    )
    assert isinstance(d, Deny)
    assert d.code == CODE_RISK_CAP


# =============================================================================
# 3. FAIL CLOSED — every unreadable input denies with UNREADABLE_INPUT
# =============================================================================

@pytest.mark.parametrize(
    "field,bad",
    [
        ("equity", None),
        ("equity", float("nan")),
        ("equity", "not_a_number"),
        ("equity", 0.0),          # non-positive equity is nonsensical
        ("equity", -100.0),
        ("equity", float("inf")),
        ("start_of_day_equity", None),
        ("start_of_day_equity", float("nan")),
        ("start_of_day_equity", 0.0),
        ("premium", None),
        ("premium", float("nan")),
        ("premium", "abc"),
        ("premium", 0.0),         # non-positive premium
        ("premium", -1.0),
        ("proposed_qty", None),
        ("proposed_qty", float("nan")),
        ("proposed_qty", 2.5),    # fractional contracts
        ("proposed_qty", 0),      # zero contracts
        ("proposed_qty", -3),
        ("day_trades_used_5d", None),
        ("day_trades_used_5d", float("nan")),
        ("day_trades_used_5d", -1),
        ("day_trades_used_5d", 1.5),
        ("setup_name", None),
        ("setup_name", ""),
        ("setup_name", "   "),
        ("setup_name", 123),
        ("kill_switch_tripped", None),   # ambiguous halt state
        ("kill_switch_tripped", "yes"),  # must be a real bool
        ("kill_switch_tripped", 1),
        ("prior_stops_today", 42),       # not iterable
        ("prior_stops_today", "ONE_SETUP"),  # bare string is ambiguous
    ],
)
def test_fail_closed_on_unreadable_input(field, bad):
    d = _clean_safe(**{field: bad})
    assert isinstance(d, Deny), f"{field}={bad!r} should fail closed, got Allow"
    assert d.code == CODE_UNREADABLE_INPUT, (
        f"{field}={bad!r} should be UNREADABLE_INPUT, got {d.code}"
    )


def test_fail_closed_on_none_params():
    d = _clean_safe(params=None)
    assert isinstance(d, Deny)
    assert d.code == CODE_UNREADABLE_INPUT


def test_fail_closed_on_missing_required_param():
    for key in ("per_trade_risk_cap_pct", "daily_loss_kill_switch_pct", "min_contracts"):
        params = {k: v for k, v in SAFE_PARAMS.items() if k != key}
        d = _clean_safe(params=params)
        assert isinstance(d, Deny), f"missing {key} should fail closed"
        assert d.code == CODE_UNREADABLE_INPUT


def test_fail_closed_on_nan_param_value():
    params = dict(SAFE_PARAMS, per_trade_risk_cap_pct=float("nan"))
    d = _clean_safe(params=params)
    assert isinstance(d, Deny)
    assert d.code == CODE_UNREADABLE_INPUT


def test_fail_closed_on_malformed_premium_tier():
    # A tier row with a NaN max_pct, and equity that would land in it.
    params = dict(
        SAFE_PARAMS,
        v15_max_premium_pct_of_account=[
            {"equity_min": 0, "equity_max": 999999999, "max_pct": float("nan")},
        ],
    )
    d = _clean_safe(params=params)
    assert isinstance(d, Deny)
    assert d.code == CODE_UNREADABLE_INPUT


def test_fail_closed_on_uncovered_equity_tier():
    # Table present but no tier covers the equity -> uncertainty on a hard gate.
    params = dict(
        SAFE_PARAMS,
        v15_max_premium_pct_of_account=[
            {"equity_min": 0, "equity_max": 1000, "max_pct": 0.4},
        ],
    )
    d = _clean_safe(equity=2000.0, start_of_day_equity=2000.0, params=params)
    assert isinstance(d, Deny)
    assert d.code == CODE_UNREADABLE_INPUT


# =============================================================================
# 4. Per-account kill-switch isolation (Safe halt != Bold halt)
# =============================================================================

def test_kill_switch_isolation_safe_tripped_bold_unaffected():
    # Same drawdown %: -35% from SoD.
    #   Safe (-30% kill): TRIPS.   Bold (-50% kill): does NOT trip.
    safe = check_order(
        "Gamma-Safe-2",
        equity=1300.0, start_of_day_equity=2000.0, proposed_qty=3, premium=1.00,
        setup_name=SETUP, current_position_status="flat", day_trades_used_5d=0,
        kill_switch_tripped=False, prior_stops_today=[], params=SAFE_PARAMS,
    )
    bold = check_order(
        "Gamma-Risky-2",
        equity=1300.0, start_of_day_equity=2000.0, proposed_qty=5, premium=1.00,
        setup_name=SETUP, current_position_status="flat", day_trades_used_5d=0,
        kill_switch_tripped=False, prior_stops_today=[], params=BOLD_PARAMS,
    )
    assert isinstance(safe, Deny) and safe.code == CODE_KILL_SWITCH
    assert isinstance(bold, Allow), bold.reason


def test_kill_switch_isolation_bold_threshold_deeper():
    # -45% drawdown: Safe (-30%) trips, Bold (-50%) still alive.
    safe = check_order(
        "Gamma-Safe-2",
        equity=1100.0, start_of_day_equity=2000.0, proposed_qty=3, premium=1.00,
        setup_name=SETUP, current_position_status="flat", day_trades_used_5d=0,
        kill_switch_tripped=False, prior_stops_today=[], params=SAFE_PARAMS,
    )
    bold = check_order(
        "Gamma-Risky-2",
        equity=1100.0, start_of_day_equity=2000.0, proposed_qty=5, premium=1.00,
        setup_name=SETUP, current_position_status="flat", day_trades_used_5d=0,
        kill_switch_tripped=False, prior_stops_today=[], params=BOLD_PARAMS,
    )
    assert isinstance(safe, Deny) and safe.code == CODE_KILL_SWITCH
    assert isinstance(bold, Allow), bold.reason


# =============================================================================
# 5. Evaluation order — the most-severe applicable rule wins
# =============================================================================

def test_kill_switch_precedes_sizing():
    # Oversized order AND kill switch tripped -> KILL_SWITCH reported (halt
    # beats sizing; no point sizing a halted account).
    d = _clean_safe(kill_switch_tripped=True, proposed_qty=50)
    assert d.code == CODE_KILL_SWITCH


def test_not_flat_precedes_min_contracts():
    d = _clean_safe(current_position_status="open", proposed_qty=1)
    assert d.code == CODE_NOT_FLAT


def test_unreadable_precedes_everything():
    # Bad equity AND kill switch tripped -> UNREADABLE wins (safety first).
    d = _clean_safe(equity=None, kill_switch_tripped=True)
    assert d.code == CODE_UNREADABLE_INPUT


# =============================================================================
# 6. Immutability — decisions are frozen, inputs are not mutated
# =============================================================================

def test_decision_is_frozen():
    d = _clean_safe()
    with pytest.raises(Exception):
        d.allowed = False  # frozen dataclass -> FrozenInstanceError


def test_inputs_not_mutated():
    params = dict(SAFE_PARAMS)
    stops = [SETUP]
    params_before = dict(params)
    stops_before = list(stops)
    check_order(
        "Gamma-Safe-2",
        equity=2000.0, start_of_day_equity=2000.0, proposed_qty=3, premium=1.00,
        setup_name="OTHER", current_position_status="flat", day_trades_used_5d=0,
        kill_switch_tripped=False, prior_stops_today=stops, params=params,
    )
    assert params == params_before, "check_order mutated params"
    assert stops == stops_before, "check_order mutated prior_stops_today"


# =============================================================================
# 7. OP-32 invariant — gates ORDERS, never SESSIONS (fails open for the human)
# =============================================================================

def test_module_cannot_lock_out_human():
    """The risk gate must never import a capability that can stop a process or
    session. Order control fails closed; operator control fails open. We assert
    the dangerous modules are simply absent from risk_gate's namespace."""
    from lib import risk_gate

    for forbidden in ("os", "subprocess", "signal", "sys", "psutil"):
        assert not hasattr(risk_gate, forbidden), (
            f"risk_gate imports '{forbidden}' — it must not be able to touch "
            "processes/sessions (OP-32: order control fails closed, operator "
            "control fails open)."
        )
    # The named invariant anchor exists and is side-effect free.
    assert risk_gate._assert_never_locks_human() is None


def test_source_has_no_process_control_calls():
    """Belt-and-suspenders: the source text must not call process/session kills."""
    src = (BACKTEST / "lib" / "risk_gate.py").read_text(encoding="utf-8")
    for needle in ("subprocess.", "os.kill", "os.system", "signal.", "sys.exit", "._exit("):
        assert needle not in src, (
            f"risk_gate.py contains '{needle}' — order control must never reach "
            "for process/session control (OP-32 scar)."
        )


# =============================================================================
# WP-10 — cap-aware affordability helpers (L180 / C11 / C14).
#
# order_affordable / max_affordable_qty expose the SAME per-order sizing math as
# check_order so the real-fills simulator can decline orders the live gate would
# deny. The load-bearing test is the GRID CROSS-CHECK: the two implementations
# must agree on every cell so they can never silently diverge (the dead-knob /
# divergence trap C14). Plus fail-closed on unreadable input.
# =============================================================================

# Sizing-gate-relevant fields only (premium-cap helpers ignore kill/PDT/flat etc).
_GRID_PARAMS = [SAFE_PARAMS, BOLD_PARAMS]
_GRID_EQUITY = [1000.0, 2000.0, 5000.0, 12000.0, 30000.0]
_GRID_PREMIUM = [0.20, 0.50, 1.00, 2.49, 4.00, 8.00]
_GRID_QTY = [3, 5, 10, 20]


def _sizing_only_check(*, equity, premium, qty, params):
    """check_order with every NON-sizing gate forced clean, so the only thing that
    can deny is MIN_CONTRACTS / RISK_CAP / MAX_PREMIUM_TIER — the exact subset the
    affordability helpers model."""
    return check_order(
        "Grid",
        equity=equity,
        start_of_day_equity=equity,   # no drawdown -> kill switch inert
        proposed_qty=qty,
        premium=premium,
        setup_name=SETUP,
        current_position_status="flat",
        day_trades_used_5d=0,
        kill_switch_tripped=False,
        prior_stops_today=[],
        params=params,
    )


def test_order_affordable_matches_check_order_on_grid():
    """order_affordable(...) is True IFF check_order (sizing gates only) Allows —
    on every (params, equity, premium, qty) cell. Binds the two cap implementations
    so they cannot diverge."""
    checked = 0
    for params in _GRID_PARAMS:
        for equity in _GRID_EQUITY:
            for premium in _GRID_PREMIUM:
                for qty in _GRID_QTY:
                    gate = _sizing_only_check(
                        equity=equity, premium=premium, qty=qty, params=params
                    )
                    afford = order_affordable(
                        equity=equity, premium=premium, qty=qty, params=params
                    )
                    assert afford == isinstance(gate, Allow), (
                        f"divergence at params.min={params['min_contracts']} "
                        f"eq={equity} prem={premium} qty={qty}: "
                        f"order_affordable={afford} but check_order={gate.code}"
                    )
                    checked += 1
    assert checked == len(_GRID_PARAMS) * len(_GRID_EQUITY) * len(_GRID_PREMIUM) * len(_GRID_QTY)


def test_max_affordable_qty_is_the_largest_allowed_qty():
    """max_affordable_qty is the boundary: that qty is affordable and qty+1 is not
    (when >0); when 0, even min_contracts is unaffordable."""
    for params in _GRID_PARAMS:
        for equity in _GRID_EQUITY:
            for premium in _GRID_PREMIUM:
                m = max_affordable_qty(equity=equity, premium=premium, params=params)
                if m == 0:
                    # min_contracts itself must be unaffordable per check_order.
                    gate = _sizing_only_check(
                        equity=equity,
                        premium=premium,
                        qty=params["min_contracts"],
                        params=params,
                    )
                    assert isinstance(gate, Deny)
                    assert gate.code in (CODE_RISK_CAP, CODE_MAX_PREMIUM_TIER)
                else:
                    assert m >= params["min_contracts"]
                    assert order_affordable(
                        equity=equity, premium=premium, qty=m, params=params
                    )
                    assert not order_affordable(
                        equity=equity, premium=premium, qty=m + 1, params=params
                    )


def test_l180_wp8_doubler_is_correctly_blocked_at_safe_2k():
    """The exact L180 near-miss: a 1DTE-ATM 'doubler' at qty3 whose per-contract
    premium puts notional over Safe's $600 cap MUST be unaffordable, and qty2 must
    fail the min-contracts floor too (no auto-reduce)."""
    # $2.49 * 3 * 100 = $747 > $600 (30% of $2,000) -> blocked.
    assert not order_affordable(equity=2000.0, premium=2.49, qty=3, params=SAFE_PARAMS)
    # qty2 is below min_contracts (3) -> unaffordable regardless of notional.
    assert not order_affordable(equity=2000.0, premium=2.49, qty=2, params=SAFE_PARAMS)
    # No affordable qty exists at this premium/equity.
    assert max_affordable_qty(equity=2000.0, premium=2.49, params=SAFE_PARAMS) == 0
    # A cheap ATM 0DTE at qty3 ($1.35*3*100=$405 < $600) IS affordable -> the lever,
    # not the setup, is what blocked the doubler.
    assert order_affordable(equity=2000.0, premium=1.35, qty=3, params=SAFE_PARAMS)


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(equity=None, premium=1.0, qty=3, params=SAFE_PARAMS),
        dict(equity=float("nan"), premium=1.0, qty=3, params=SAFE_PARAMS),
        dict(equity=-100.0, premium=1.0, qty=3, params=SAFE_PARAMS),
        dict(equity=2000.0, premium=None, qty=3, params=SAFE_PARAMS),
        dict(equity=2000.0, premium=0.0, qty=3, params=SAFE_PARAMS),
        dict(equity=2000.0, premium=1.0, qty=3.5, params=SAFE_PARAMS),
        dict(equity=2000.0, premium=1.0, qty=3, params=None),
        dict(equity=2000.0, premium=1.0, qty=3, params={"per_trade_risk_cap_pct": 0.3}),  # no min_contracts
    ],
)
def test_order_affordable_fails_closed(kwargs):
    """Any unreadable input -> not affordable (never a silent True)."""
    assert order_affordable(**kwargs) is False


def test_affordability_fails_closed_when_equity_outside_every_tier():
    """SAFE_PARAMS tier table tops out at $999,999,999; an equity above it is not
    covered -> uncertainty about a hard gate -> unaffordable (mirrors check_order's
    deny on an unresolvable tier)."""
    assert max_affordable_qty(equity=2_000_000_000.0, premium=1.0, params=SAFE_PARAMS) == 0
    assert not order_affordable(
        equity=2_000_000_000.0, premium=1.0, qty=3, params=SAFE_PARAMS
    )

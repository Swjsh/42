"""Tests for the multi-symbol lane's sizing + risk layer
(multi/lib/sizing.py, multi/lib/risk.py).

Mirrors backtest/tests/test_risk_gate.py's discipline:
  1. Every Deny/deny code fires on its specific trigger, and a clean input Allows.
  2. FAIL-CLOSED: every unreadable/malformed input denies, never a silent allow.
  3. The kill switch never force-closes anything and reacts to REALIZED loss
     only (never a bare equity dip that could be all unrealized).
  4. Strike selection NEVER returns a strike that isn't in the live listed chain
     — the core fix for crypto/lib/strike_selection.py's SPY-only $1-strike
     assumption.

Run:  backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_multi_sizing_risk.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from multi.lib import sizing  # noqa: E402
from multi.lib import risk  # noqa: E402


# --- representative params (shape mirrors automation/state/multi/params.json) ---

PARAMS = {
    "entry": {
        "min_dte_at_entry": 3,
        "max_concurrent_symbols": 3,
    },
    "risk": {
        "per_trade_risk_cap_pct": 0.20,
        "min_contracts": 3,
        "max_concurrent_positions": 3,
        "daily_loss_kill_switch_pct": 0.25,
        "correlation_gate": {"deny_abs_r_gte": 0.75, "lookback_days": 60, "fail_mode": "closed"},
        "max_positions_per_sector": 1,
    },
    "universe": {
        "mega_tech": ["AAPL", "MSFT", "NVDA"],
        "financials": ["JPM", "BAC"],
        "high_beta": ["PLTR", "COIN"],
    },
}


def _mk_position(symbol, qty, premium_entry, **extra):
    d = {"symbol": symbol, "qty": qty, "premium_entry": premium_entry}
    d.update(extra)
    return d


# =============================================================================
# 1. sizing.committed_notional — the capital-already-committed accounting
# =============================================================================

def test_committed_notional_empty_book_is_zero():
    assert sizing.committed_notional(None) == 0.0
    assert sizing.committed_notional([]) == 0.0


def test_committed_notional_sums_entry_premium_times_qty_times_100():
    positions = [
        _mk_position("AAPL", 3, 1.50),
        _mk_position("MSFT", 5, 0.80),
    ]
    # 3*1.50*100 + 5*0.80*100 = 450 + 400 = 850
    assert sizing.committed_notional(positions) == pytest.approx(850.0)


@pytest.mark.parametrize(
    "bad_position,needle",
    [
        ({"qty": 3, "premium_entry": 1.0}, "symbol"),  # missing symbol
        ({"symbol": "AAPL", "premium_entry": 1.0}, "qty"),  # missing qty
        ({"symbol": "AAPL", "qty": 3}, "premium_entry"),  # missing premium_entry
        ({"symbol": "AAPL", "qty": "not-a-number", "premium_entry": 1.0}, "qty"),
        ({"symbol": "AAPL", "qty": 3, "premium_entry": float("nan")}, "premium_entry"),
        ({"symbol": "AAPL", "qty": -3, "premium_entry": 1.0}, "qty"),
        ({"symbol": "AAPL", "qty": 3, "premium_entry": -1.0}, "premium_entry"),
        ("not-a-mapping-at-all", "mapping"),
    ],
)
def test_committed_notional_RED_PROOF_raises_on_malformed_position(bad_position, needle):
    """RED-PROOF (explicit task requirement): a malformed open position MUST NOT
    be silently treated as $0 committed — that understates exposure and
    overstates affordability, the exact fail-OPEN direction that over-commits
    capital. This must raise, never return a smaller-than-true sum."""
    good = _mk_position("MSFT", 2, 1.0)
    with pytest.raises(sizing.MalformedPositionError) as exc_info:
        sizing.committed_notional([good, bad_position])
    assert needle in str(exc_info.value).lower() or needle in str(exc_info.value)


# =============================================================================
# 2. sizing.size_entry — contracts sizing (RISK_CAP, MIN_CONTRACTS, committed capital)
# =============================================================================

def test_size_entry_allows_clean_order_within_cap():
    # equity 10,000 * 20% = $2,000 cap. premium $1.00 -> per-contract $100.
    # max affordable = 20 contracts, well above min_contracts=3.
    result = sizing.size_entry(
        symbol="AAPL", equity=10_000, premium=1.00, params=PARAMS, open_positions=None,
    )
    assert result.allowed
    assert result.code == sizing.CODE_ALLOW
    assert result.contracts == 20


def test_size_entry_denies_below_min_contracts():
    # equity 1,000 * 20% = $200 cap. premium $5.00 -> per-contract $500.
    # max affordable = 0 contracts < min_contracts 3.
    result = sizing.size_entry(
        symbol="AAPL", equity=1_000, premium=5.00, params=PARAMS, open_positions=None,
    )
    assert not result.allowed
    assert result.code == sizing.CODE_MIN_CONTRACTS
    assert result.contracts == 0


def test_size_entry_nets_out_capital_already_committed_by_open_positions():
    # equity 10,000. per-trade cap = $2,000. But committed = $9,500 already
    # (e.g. one large multi-day position), leaving only $500 available.
    open_positions = [_mk_position("MSFT", 19, 5.00)]  # 19*5*100 = 9,500
    result = sizing.size_entry(
        symbol="AAPL", equity=10_000, premium=1.00, params=PARAMS,
        open_positions=open_positions,
    )
    # effective cap = min(2000, 10000-9500=500) = 500 -> 5 contracts @ $100 each.
    assert result.allowed
    assert result.contracts == 5
    assert result.committed_notional == pytest.approx(9_500.0)
    assert result.available_notional == pytest.approx(500.0)


def test_size_entry_denies_when_no_capital_remains():
    open_positions = [_mk_position("MSFT", 20, 5.00)]  # 20*5*100 = 10,000 == full equity
    result = sizing.size_entry(
        symbol="AAPL", equity=10_000, premium=1.00, params=PARAMS,
        open_positions=open_positions,
    )
    assert not result.allowed
    assert result.code == sizing.CODE_NO_CAPITAL_REMAINING


def test_size_entry_RED_PROOF_fails_closed_on_malformed_open_position():
    """RED-PROOF (explicit task requirement): size_entry must DENY (contracts=0)
    when an open position cannot be read, never silently size as if that
    position committed $0."""
    malformed = [_mk_position("MSFT", 5, 1.0), {"symbol": "GOOGL", "qty": None, "premium_entry": 2.0}]
    result = sizing.size_entry(
        symbol="AAPL", equity=10_000, premium=1.00, params=PARAMS,
        open_positions=malformed,
    )
    assert not result.allowed
    assert result.code == sizing.CODE_UNREADABLE_POSITION
    assert result.contracts == 0


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(symbol=None, equity=10_000, premium=1.0, params=PARAMS),
        dict(symbol="", equity=10_000, premium=1.0, params=PARAMS),
        dict(symbol="AAPL", equity=None, premium=1.0, params=PARAMS),
        dict(symbol="AAPL", equity=float("nan"), premium=1.0, params=PARAMS),
        dict(symbol="AAPL", equity=-100, premium=1.0, params=PARAMS),
        dict(symbol="AAPL", equity=10_000, premium=None, params=PARAMS),
        dict(symbol="AAPL", equity=10_000, premium=0, params=PARAMS),
        dict(symbol="AAPL", equity=10_000, premium=1.0, params=None),
        dict(symbol="AAPL", equity=10_000, premium=1.0, params={"risk": {}}),
    ],
)
def test_size_entry_fails_closed_on_unreadable_input(kwargs):
    result = sizing.size_entry(open_positions=None, **kwargs)
    assert not result.allowed
    assert result.code in (sizing.CODE_UNREADABLE_INPUT,)


# =============================================================================
# 3. sizing.select_strike — LIVE LISTED CHAIN ONLY (the core SPY-coupling fix)
# =============================================================================

def test_select_strike_RED_PROOF_never_returns_a_rounded_spot_value_not_in_chain():
    """RED-PROOF (explicit task requirement). Realistic non-$1 chain: strikes at
    $2.50 intervals. spot=187.30 -> crypto/lib/strike_selection.atm_strike would
    return int(round(187.30)) == 187, which is NOT one of these listed strikes.
    select_strike must pick a strike that IS listed, and must never return 187.
    """
    chain = [180.0, 182.5, 185.0, 187.5, 190.0, 192.5, 195.0]
    spot = 187.30
    naive_rounded_spot = int(round(spot))  # 187 -- NOT in the chain
    assert naive_rounded_spot not in chain

    result = sizing.select_strike(
        symbol="XYZ", spot=spot, side="C", available_strikes=chain, tier_offset=0,
    )
    assert result.ok
    assert result.strike in chain
    assert result.strike != naive_rounded_spot
    # Nearest listed strike to 187.30 is 187.5.
    assert result.strike == 187.5


def test_select_strike_anchor_is_nearest_listed_strike_low_price_half_dollar_rungs():
    # Low-priced name, $0.50 rungs.
    chain = [8.0, 8.5, 9.0, 9.5, 10.0]
    result = sizing.select_strike(symbol="LOW", spot=9.2, side="P", available_strikes=chain)
    assert result.ok
    assert result.strike in chain
    assert result.strike == 9.0  # nearest to 9.2


def test_select_strike_tier_offset_walks_the_listed_index_itm_otm():
    chain = [180.0, 182.5, 185.0, 187.5, 190.0, 192.5, 195.0]
    spot = 187.30  # anchor -> 187.5 (index 3)

    # Calls: ITM = strike < spot -> positive offset walks index DOWN (toward lower/ITM).
    call_itm1 = sizing.select_strike(symbol="XYZ", spot=spot, side="C",
                                      available_strikes=chain, tier_offset=1)
    assert call_itm1.ok and call_itm1.strike == 185.0
    assert sizing.moneyness(strike=call_itm1.strike, spot=spot, side="C") == "ITM"

    # Puts: ITM = strike > spot -> positive offset walks index UP (toward higher/ITM).
    put_itm1 = sizing.select_strike(symbol="XYZ", spot=spot, side="P",
                                     available_strikes=chain, tier_offset=1)
    assert put_itm1.ok and put_itm1.strike == 190.0
    assert sizing.moneyness(strike=put_itm1.strike, spot=spot, side="P") == "ITM"


def test_select_strike_offset_walking_off_chain_denies():
    chain = [180.0, 182.5, 185.0]
    result = sizing.select_strike(symbol="XYZ", spot=180.0, side="C",
                                   available_strikes=chain, tier_offset=10)
    assert not result.ok
    assert result.code == sizing.CODE_NO_LISTED_STRIKE


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(symbol=None, spot=100, side="C", available_strikes=[100, 105]),
        dict(symbol="X", spot=100, side="Z", available_strikes=[100, 105]),
        dict(symbol="X", spot=None, side="C", available_strikes=[100, 105]),
        dict(symbol="X", spot=100, side="C", available_strikes=None),
        dict(symbol="X", spot=100, side="C", available_strikes=[]),
        dict(symbol="X", spot=100, side="C", available_strikes=["not-a-number", "also-bad"]),
    ],
)
def test_select_strike_fails_closed_on_unreadable_input(kwargs):
    result = sizing.select_strike(**kwargs, tier_offset=0)
    assert not result.ok


def test_moneyness_classification():
    assert sizing.moneyness(strike=95, spot=100, side="C") == "ITM"
    assert sizing.moneyness(strike=105, spot=100, side="C") == "OTM"
    assert sizing.moneyness(strike=105, spot=100, side="P") == "ITM"
    assert sizing.moneyness(strike=95, spot=100, side="P") == "OTM"
    assert sizing.moneyness(strike=100, spot=100, side="C") == "ATM"


# =============================================================================
# 4. risk.check_kill_switch — REALIZED loss only, never force-closes
# =============================================================================

def test_kill_switch_allows_when_realized_pnl_positive():
    decision = risk.check_kill_switch(
        account="multi-1", start_of_day_equity=10_000, realized_pnl_today=150.0,
        kill_switch_tripped=False, params=PARAMS,
    )
    assert decision.allowed


def test_kill_switch_trips_on_realized_loss_at_threshold():
    # 25% of 10,000 = 2,500 floor. realized -2,500 -> trip.
    decision = risk.check_kill_switch(
        account="multi-1", start_of_day_equity=10_000, realized_pnl_today=-2_500.0,
        kill_switch_tripped=False, params=PARAMS,
    )
    assert not decision.allowed
    assert decision.code == risk.CODE_KILL_SWITCH


def test_kill_switch_RED_PROOF_does_not_trip_on_unrealized_only_drawdown():
    """RED-PROOF (explicit task requirement). This function does not even
    accept a live/mark equity figure -- only realized_pnl_today -- so it is
    STRUCTURALLY unable to react to unrealized mark-to-market swings on
    standing multi-day positions. A large realized GAIN alongside what would
    have been a huge unrealized loss (were equity read) must still Allow."""
    decision = risk.check_kill_switch(
        account="multi-1", start_of_day_equity=10_000,
        realized_pnl_today=10.0,  # tiny realized gain; any unrealized swing is invisible here
        kill_switch_tripped=False, params=PARAMS,
    )
    assert decision.allowed, (
        "kill switch must not react to anything but realized_pnl_today -- "
        "an unrealized-only drawdown must never trip it"
    )
    # And the function signature itself has no equity/mark-to-market parameter
    # at all -- structurally cannot read a live equity swing.
    import inspect
    sig = inspect.signature(risk.check_kill_switch)
    assert "equity" not in sig.parameters or "start_of_day_equity" in sig.parameters
    assert "current_equity" not in sig.parameters
    assert "live_equity" not in sig.parameters
    assert "mark_equity" not in sig.parameters


def test_kill_switch_sticky_latch():
    decision = risk.check_kill_switch(
        account="multi-1", start_of_day_equity=10_000, realized_pnl_today=0.0,
        kill_switch_tripped=True, params=PARAMS,
    )
    assert not decision.allowed
    assert decision.code == risk.CODE_KILL_SWITCH


def test_kill_switch_never_emits_a_close_or_liquidate_action():
    """The Deny result must never carry a close/liquidate instruction -- a trip
    blocks NEW ENTRIES only. Inspect every RiskDecision field across a battery
    of trip scenarios for forbidden verbs."""
    forbidden = ("close_position", "liquidate", "force_close", "cancel_position", "flatten")
    scenarios = [
        dict(realized_pnl_today=-5_000.0, kill_switch_tripped=False),
        dict(realized_pnl_today=0.0, kill_switch_tripped=True),
        dict(realized_pnl_today=-2_500.0, kill_switch_tripped=False),
    ]
    for kw in scenarios:
        decision = risk.check_kill_switch(
            account="multi-1", start_of_day_equity=10_000, params=PARAMS, **kw,
        )
        blob = f"{decision.code} {decision.reason}".lower()
        for word in forbidden:
            assert word not in blob, f"kill switch decision leaked a close verb: {word!r} in {blob!r}"


def test_module_risk_cannot_force_close_or_place_orders():
    """Mirrors test_risk_gate.py's OP-32 invariant test: risk.py must not import
    anything capable of touching a broker or a process/session."""
    for forbidden in ("os", "subprocess", "signal", "sys"):
        assert not hasattr(risk, forbidden), (
            f"risk.py imports {forbidden!r} -- an admission gate must never be "
            f"able to touch processes/sessions/orders."
        )
    assert risk._assert_never_force_closes() is None

    src = (REPO / "multi" / "lib" / "risk.py").read_text(encoding="utf-8")
    for needle in ("subprocess.", "os.kill", "os.system", "close_position(",
                   "cancel_order(", "place_option_order(", "requests.", "urlopen("):
        assert needle not in src, f"risk.py source contains {needle!r} -- must stay a pure gate"


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(account="a", start_of_day_equity=None, realized_pnl_today=0, kill_switch_tripped=False, params=PARAMS),
        dict(account="a", start_of_day_equity=10_000, realized_pnl_today=None, kill_switch_tripped=False, params=PARAMS),
        dict(account="a", start_of_day_equity=10_000, realized_pnl_today=0, kill_switch_tripped=None, params=PARAMS),
        dict(account="a", start_of_day_equity=10_000, realized_pnl_today=0, kill_switch_tripped="yes", params=PARAMS),
        dict(account="a", start_of_day_equity=10_000, realized_pnl_today=0, kill_switch_tripped=False, params=None),
        dict(account="a", start_of_day_equity=-1, realized_pnl_today=0, kill_switch_tripped=False, params=PARAMS),
        dict(account="a", start_of_day_equity=10_000, realized_pnl_today=0, kill_switch_tripped=False, params={"risk": {}}),
    ],
)
def test_kill_switch_fails_closed_on_unreadable_input(kwargs):
    decision = risk.check_kill_switch(**kwargs)
    assert not decision.allowed
    assert decision.code == risk.CODE_UNREADABLE_INPUT


# =============================================================================
# 5. risk.check_sector_cap
# =============================================================================

def test_sector_cap_allows_when_under_cap():
    decision = risk.check_sector_cap(symbol="AAPL", open_positions=[], params=PARAMS)
    assert decision.allowed


def test_sector_cap_denies_when_sector_already_at_cap():
    # max_positions_per_sector=1; MSFT (mega_tech) already open -> AAPL (mega_tech) denied.
    open_positions = [_mk_position("MSFT", 3, 1.0)]
    decision = risk.check_sector_cap(symbol="AAPL", open_positions=open_positions, params=PARAMS)
    assert not decision.allowed
    assert decision.code == risk.CODE_SECTOR_CAP


def test_sector_cap_allows_different_sector():
    open_positions = [_mk_position("JPM", 3, 1.0)]  # financials
    decision = risk.check_sector_cap(symbol="AAPL", open_positions=open_positions, params=PARAMS)  # mega_tech
    assert decision.allowed


def test_sector_cap_fails_closed_on_unknown_symbol_sector():
    decision = risk.check_sector_cap(symbol="ZZZZ_UNKNOWN", open_positions=[], params=PARAMS)
    assert not decision.allowed
    assert decision.code == risk.CODE_UNREADABLE_INPUT


def test_sector_cap_fails_closed_on_malformed_open_position():
    decision = risk.check_sector_cap(
        symbol="AAPL", open_positions=[{"qty": 3, "premium_entry": 1.0}], params=PARAMS,
    )
    assert not decision.allowed
    assert decision.code == risk.CODE_UNREADABLE_POSITION


# =============================================================================
# 6. risk.check_correlation_gate
# =============================================================================

def test_correlation_gate_allows_empty_book():
    decision = risk.check_correlation_gate(
        symbol="AAPL", open_positions=[], correlations={}, params=PARAMS,
    )
    assert decision.allowed


def test_correlation_gate_denies_on_high_correlation():
    open_positions = [_mk_position("MSFT", 3, 1.0)]
    correlations = {"AAPL": {"MSFT": 0.90}}
    decision = risk.check_correlation_gate(
        symbol="AAPL", open_positions=open_positions, correlations=correlations, params=PARAMS,
    )
    assert not decision.allowed
    assert decision.code == risk.CODE_CORRELATION


def test_correlation_gate_allows_low_correlation():
    open_positions = [_mk_position("MSFT", 3, 1.0)]
    correlations = {"AAPL": {"MSFT": 0.10}}
    decision = risk.check_correlation_gate(
        symbol="AAPL", open_positions=open_positions, correlations=correlations, params=PARAMS,
    )
    assert decision.allowed


def test_correlation_gate_symmetric_lookup():
    open_positions = [_mk_position("MSFT", 3, 1.0)]
    correlations = {"MSFT": {"AAPL": 0.90}}  # reverse ordering
    decision = risk.check_correlation_gate(
        symbol="AAPL", open_positions=open_positions, correlations=correlations, params=PARAMS,
    )
    assert not decision.allowed
    assert decision.code == risk.CODE_CORRELATION


def test_correlation_gate_RED_PROOF_fails_closed_on_missing_data():
    """RED-PROOF: an open position exists but NO correlation reading is
    available for the pair -> must DENY, never silently allow."""
    open_positions = [_mk_position("MSFT", 3, 1.0)]
    decision = risk.check_correlation_gate(
        symbol="AAPL", open_positions=open_positions, correlations=None, params=PARAMS,
    )
    assert not decision.allowed
    assert decision.code == risk.CODE_UNREADABLE_INPUT

    decision2 = risk.check_correlation_gate(
        symbol="AAPL", open_positions=open_positions,
        correlations={"AAPL": {}}, params=PARAMS,  # present but missing MSFT entry
    )
    assert not decision2.allowed
    assert decision2.code == risk.CODE_UNREADABLE_INPUT


# =============================================================================
# 7. risk.check_concurrency_admission
# =============================================================================

def test_concurrency_denies_at_max_positions():
    open_positions = [_mk_position(s, 3, 1.0) for s in ("AAPL", "MSFT", "NVDA")]
    decision = risk.check_concurrency_admission(symbol="JPM", open_positions=open_positions, params=PARAMS)
    assert not decision.allowed
    assert decision.code == risk.CODE_MAX_CONCURRENT_POSITIONS


def test_concurrency_denies_at_max_symbols_even_if_positions_room():
    params = dict(PARAMS)
    params["risk"] = dict(PARAMS["risk"], max_concurrent_positions=99)
    params["entry"] = dict(PARAMS["entry"], max_concurrent_symbols=2)
    open_positions = [_mk_position("AAPL", 3, 1.0), _mk_position("MSFT", 3, 1.0)]
    decision = risk.check_concurrency_admission(symbol="NVDA", open_positions=open_positions, params=params)
    assert not decision.allowed
    assert decision.code == risk.CODE_MAX_CONCURRENT_SYMBOLS


def test_concurrency_allows_add_to_existing_symbol_without_growing_symbol_count():
    params = dict(PARAMS)
    params["risk"] = dict(PARAMS["risk"], max_concurrent_positions=99)
    params["entry"] = dict(PARAMS["entry"], max_concurrent_symbols=2)
    open_positions = [_mk_position("AAPL", 3, 1.0), _mk_position("MSFT", 3, 1.0)]
    decision = risk.check_concurrency_admission(symbol="AAPL", open_positions=open_positions, params=params)
    assert decision.allowed


# =============================================================================
# 8. risk.evaluate_admission — orchestrator ordering
# =============================================================================

def test_evaluate_admission_allows_clean_entry():
    decision = risk.evaluate_admission(
        account="multi-1", symbol="AAPL", start_of_day_equity=10_000,
        realized_pnl_today=0.0, kill_switch_tripped=False,
        open_positions=[], correlations={}, params=PARAMS,
    )
    assert decision.allowed


def test_evaluate_admission_kill_switch_outranks_sector_cap():
    open_positions = [_mk_position("MSFT", 3, 1.0)]  # would also fail sector cap for AAPL
    decision = risk.evaluate_admission(
        account="multi-1", symbol="AAPL", start_of_day_equity=10_000,
        realized_pnl_today=-3_000.0,  # trips kill switch (25% of 10k = 2.5k floor)
        kill_switch_tripped=False,
        open_positions=open_positions, correlations={}, params=PARAMS,
    )
    assert not decision.allowed
    assert decision.code == risk.CODE_KILL_SWITCH

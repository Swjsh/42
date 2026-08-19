"""Guards for weekly/lib/conflict.py -- the weekly-1 concurrency, correlation, and
capital-commitment gates (multi-day multi-symbol basket, r=0.846 "one bet in five sizes"
scar). Loaded by explicit file path (not package import) to match the existing
backtest/tests convention (see test_book_exposure_2026_08_18.py) -- pins the exact module
under test regardless of how pytest resolves package roots.
"""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load(name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


conflict = _load("weekly_conflict_under_test", "weekly/lib/conflict.py")


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


# --- synthetic price series (deterministic -- fixed seeds, no network) ---------------------

def _returns(n: int, seed: int) -> list:
    rng = random.Random(seed)
    return [rng.gauss(0, 0.012) for _ in range(n)]


def _prices_from_returns(returns: list, start: float = 100.0) -> list:
    prices = [start]
    for r in returns:
        prices.append(prices[-1] * (1.0 + r))
    return prices


def _blend(base_returns: list, rho: float, noise_seed: int) -> list:
    rng = random.Random(noise_seed)
    noise = [rng.gauss(0, 0.012) for _ in range(len(base_returns))]
    k = math.sqrt(max(0.0, 1.0 - rho * rho))
    return [rho * b + k * nz for b, nz in zip(base_returns, noise)]


_N = 45
_BASE_RETURNS = _returns(_N, seed=1)
BASE_PRICES = _prices_from_returns(_BASE_RETURNS)          # stands in for the OPEN symbol
HIGH_CORR_PRICES = _prices_from_returns(_blend(_BASE_RETURNS, 0.85, noise_seed=2))
LOW_CORR_PRICES = _prices_from_returns(_blend(_BASE_RETURNS, 0.20, noise_seed=3))

# Sanity-lock the fixtures themselves -- if these ever drift the tests below would be
# testing the wrong thing silently, so pin the measured r of the raw fixtures once here.
_measured_high = conflict._pearson_r(
    conflict._daily_returns(BASE_PRICES), conflict._daily_returns(HIGH_CORR_PRICES)
)
_measured_low = conflict._pearson_r(
    conflict._daily_returns(BASE_PRICES), conflict._daily_returns(LOW_CORR_PRICES)
)
assert _measured_high >= 0.70, f"fixture drift: HIGH_CORR_PRICES measured r={_measured_high}"
assert abs(_measured_low) < 0.70, f"fixture drift: LOW_CORR_PRICES measured r={_measured_low}"


def _fetcher(series_map: dict):
    def _fetch(symbol: str, lookback_days: int):
        return series_map.get(symbol)
    return _fetch


# --- 1. concurrency --------------------------------------------------------------------------

def test_concurrency_allows_under_the_cap() -> None:
    r = conflict.check_concurrency({"GLD": {"qty": 3, "premium": 2.0}}, _params())
    assert r["allowed"] is True
    assert r["code"] == conflict.CODE_OK


def test_concurrency_denies_the_third_position() -> None:
    open_positions = {
        "GLD": {"qty": 3, "premium": 2.0},
        "QQQ": {"qty": 3, "premium": 1.5},
    }
    r = conflict.check_concurrency(open_positions, _params())
    assert r["allowed"] is False
    assert r["code"] == conflict.CODE_CONCURRENCY_CAP
    assert "2" in r["reason"] and "cap" in r["reason"].lower()


def test_concurrency_fails_closed_on_missing_params_key() -> None:
    bad_params = _params()
    del bad_params["risk"]["max_concurrent_positions"]
    r = conflict.check_concurrency({}, bad_params)
    assert r["allowed"] is False
    assert r["code"] == conflict.CODE_UNREADABLE_PARAMS


def test_concurrency_never_a_bare_bool() -> None:
    r = conflict.check_concurrency({}, _params())
    assert isinstance(r, dict) and "code" in r and "reason" in r


# --- 2. correlation ----------------------------------------------------------------------------

def test_correlation_allows_when_book_is_empty() -> None:
    r = conflict.check_correlation("GLD", [], _params(), price_fetcher=_fetcher({}))
    assert r["allowed"] is True


def test_correlation_denies_a_highly_correlated_second_entry() -> None:
    fetch = _fetcher({"QQQ": BASE_PRICES, "NVDA": HIGH_CORR_PRICES})
    r = conflict.check_correlation("NVDA", ["QQQ"], _params(), price_fetcher=fetch)
    assert r["allowed"] is False, r
    assert r["code"] == conflict.CODE_CORRELATION_DENY
    assert abs(r["correlations"]["QQQ"]) >= 0.70
    assert "QQQ" in r["reason"] and "0.70" in r["reason"]


def test_correlation_allows_a_weakly_correlated_second_entry() -> None:
    fetch = _fetcher({"QQQ": BASE_PRICES, "GLD": LOW_CORR_PRICES})
    r = conflict.check_correlation("GLD", ["QQQ"], _params(), price_fetcher=fetch)
    assert r["allowed"] is True, r
    assert abs(r["correlations"]["QQQ"]) < 0.70


def test_correlation_fails_closed_when_open_symbol_data_is_missing() -> None:
    """THE FAIL-CLOSED GUARD (RED-proofed). Candidate has good data; the OPEN position's
    data is unavailable (fetcher returns None) -- this must DENY, never silently skip the
    comparison and allow."""
    fetch = _fetcher({"NVDA": HIGH_CORR_PRICES})  # "QQQ" deliberately absent
    r = conflict.check_correlation("NVDA", ["QQQ"], _params(), price_fetcher=fetch)
    assert r["allowed"] is False, "missing correlation data must DENY, not silently allow"
    assert r["code"] == conflict.CODE_CORRELATION_DATA_UNAVAILABLE
    assert "insufficient" in r["reason"].lower() or "fail-closed" in r["reason"].lower()
    assert "QQQ" in r["reason"]


def test_correlation_fails_closed_when_candidate_data_is_missing() -> None:
    fetch = _fetcher({"QQQ": BASE_PRICES})  # candidate symbol absent
    r = conflict.check_correlation("NVDA", ["QQQ"], _params(), price_fetcher=fetch)
    assert r["allowed"] is False
    assert r["code"] == conflict.CODE_CORRELATION_DATA_UNAVAILABLE


def test_correlation_fails_closed_on_too_few_samples() -> None:
    fetch = _fetcher({"QQQ": BASE_PRICES, "NVDA": HIGH_CORR_PRICES[:5]})  # under MIN_CORRELATION_SAMPLES
    r = conflict.check_correlation("NVDA", ["QQQ"], _params(), price_fetcher=fetch)
    assert r["allowed"] is False
    assert r["code"] == conflict.CODE_CORRELATION_DATA_UNAVAILABLE


def test_correlation_never_a_bare_bool() -> None:
    fetch = _fetcher({"QQQ": BASE_PRICES, "NVDA": HIGH_CORR_PRICES})
    r = conflict.check_correlation("NVDA", ["QQQ"], _params(), price_fetcher=fetch)
    assert isinstance(r, dict) and "code" in r and "reason" in r


# --- 3. capital commitment ----------------------------------------------------------------------

def test_capital_commitment_allows_when_it_fits() -> None:
    r = conflict.check_capital_commitment(
        "GLD", candidate_premium=4.0, equity=5000.0, open_positions={}, params=_params()
    )
    assert r["allowed"] is True
    # min_contracts(3) * 4.0 * 100 = $1200 <= min(cap 30%=$1500, available $5000)
    assert r["min_required_notional"] == pytest.approx(1200.0)


def test_capital_commitment_denies_when_premium_too_rich_for_the_cap() -> None:
    r = conflict.check_capital_commitment(
        "GLD", candidate_premium=6.0, equity=5000.0, open_positions={}, params=_params()
    )
    assert r["allowed"] is False
    assert r["code"] == conflict.CODE_CAPITAL_COMMITMENT_DENY
    # 3 * 6.0 * 100 = $1800 > $1500 cap (30% of 5000)
    assert r["min_required_notional"] == pytest.approx(1800.0)


def test_capital_commitment_accounts_for_capital_already_tied_up() -> None:
    """THE POINT OF THIS GATE: an order that would fit in isolation must be denied once
    an already-open multi-day position has eaten the available capital."""
    open_positions = {"QQQ": {"qty": 5, "premium": 7.0}}  # $3,500 already committed
    params = _params()
    # In isolation (no open positions) this order fits: 3 * 4.0 * 100 = $1200 <= $1500 cap.
    isolated = conflict.check_capital_commitment(
        "GLD", candidate_premium=4.0, equity=5000.0, open_positions={}, params=params
    )
    assert isolated["allowed"] is True
    # With $3,500 already committed, available capital is only $1,500 -- BUT the per-trade
    # cap (30% = $1500) still nominally covers it UNLESS available capital is tighter.
    # Push it further: commit enough that available capital undercuts the per-trade cap.
    open_positions_heavy = {"QQQ": {"qty": 5, "premium": 9.0}}  # $4,500 committed
    r = conflict.check_capital_commitment(
        "GLD", candidate_premium=4.0, equity=5000.0, open_positions=open_positions_heavy, params=params
    )
    assert r["allowed"] is False, r
    assert r["committed_notional"] == pytest.approx(4500.0)
    assert r["available_capital"] == pytest.approx(500.0)


def test_capital_commitment_fails_closed_on_missing_params() -> None:
    bad_params = _params()
    del bad_params["risk"]["per_trade_risk_cap_pct"]
    r = conflict.check_capital_commitment(
        "GLD", candidate_premium=4.0, equity=5000.0, open_positions={}, params=bad_params
    )
    assert r["allowed"] is False
    assert r["code"] == conflict.CODE_UNREADABLE_PARAMS


def test_capital_commitment_never_a_bare_bool() -> None:
    r = conflict.check_capital_commitment(
        "GLD", candidate_premium=4.0, equity=5000.0, open_positions={}, params=_params()
    )
    assert isinstance(r, dict) and "code" in r and "reason" in r


# --- orchestrator ------------------------------------------------------------------------------

def test_evaluate_first_denial_wins_concurrency_before_correlation() -> None:
    open_positions = {
        "GLD": {"qty": 3, "premium": 2.0},
        "QQQ": {"qty": 3, "premium": 1.5},
    }
    r = conflict.evaluate(
        "NVDA", candidate_premium=4.0, equity=5000.0,
        open_positions=open_positions, params=_params(),
        price_fetcher=_fetcher({}),  # would fail-closed on correlation if it got that far
    )
    assert r["allowed"] is False
    assert r["code"] == conflict.CODE_CONCURRENCY_CAP


def test_evaluate_allows_a_clean_candidate() -> None:
    open_positions = {"QQQ": {"qty": 3, "premium": 1.5}}
    fetch = _fetcher({"QQQ": BASE_PRICES, "GLD": LOW_CORR_PRICES})
    r = conflict.evaluate(
        "GLD", candidate_premium=4.0, equity=5000.0,
        open_positions=open_positions, params=_params(), price_fetcher=fetch,
    )
    assert r["allowed"] is True, r


# --- structural guard: Stage A is shadow-only -- no order-placement call anywhere ----------------

def test_conflict_module_never_places_cancels_or_modifies_orders() -> None:
    src = (REPO / "weekly" / "lib" / "conflict.py").read_text(encoding="utf-8")
    forbidden = [
        "place_option_order", "place_stock_order", "place_crypto_order", "place_order(",
        "cancel_order", "cancel_all_orders", "close_position(", "close_all_positions",
        "replace_order_by_id", "mcp__alpaca",
    ]
    hits = [f for f in forbidden if f in src]
    assert not hits, f"conflict.py must never place/cancel/modify orders -- found: {hits}"


# --- code-review fix, 2026-08-18: malformed open positions must FAIL CLOSED ------------------
# A skipped malformed entry contributed $0 to committed capital, understating exposure and
# overstating affordability -- fail-open in the one direction that can over-commit the account.

def _cc_params():
    return {"risk": {"per_trade_risk_cap_pct": 0.30, "min_contracts": 3}}


@pytest.mark.parametrize(
    "bad_positions,label",
    [
        ({"GLD": "not-a-mapping"}, "non-mapping position"),
        ({"GLD": {"qty": "abc", "premium": 2.0}}, "unreadable qty"),
        ({"GLD": {"qty": 3, "premium": None}}, "unreadable premium"),
        ({"GLD": {}}, "missing qty/premium"),
    ],
)
def test_capital_commitment_fails_closed_on_unreadable_position(bad_positions, label):
    from weekly.lib import conflict

    res = conflict.check_capital_commitment(
        candidate_symbol="QQQ",
        candidate_premium=2.0,
        equity=5000.0,
        open_positions=bad_positions,
        params=_cc_params(),
    )
    assert res["allowed"] is False, f"{label} was ALLOWED -- must fail closed"
    assert res["code"] == conflict.CODE_UNREADABLE_PARAMS, (
        f"{label} denied with {res['code']}, expected {conflict.CODE_UNREADABLE_PARAMS}"
    )


def test_capital_commitment_still_allows_a_clean_affordable_entry():
    """The fail-closed change must not deny well-formed, affordable entries."""
    from weekly.lib import conflict

    res = conflict.check_capital_commitment(
        candidate_symbol="QQQ",
        candidate_premium=2.0,
        equity=5000.0,
        open_positions={"GLD": {"qty": 3, "premium": 1.0}},
        params=_cc_params(),
    )
    assert res["allowed"] is True, res
    assert res["committed_notional"] == 300.0

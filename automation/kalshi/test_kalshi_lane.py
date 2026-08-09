#!/usr/bin/env python3
"""Guards for the Kalshi lane. Network-free -- a FakeClient stands in for the API.

Every test here pins an invariant that, if it silently broke, would either place a
trade we did not intend or size one wrongly. Per project doctrine these are the
graduated guards: they must RED on regression, not merely pass today.

Run:  python -m pytest automation/kalshi/test_kalshi_lane.py -q
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from kalshi_client import KalshiClient, fee_dollars  # noqa: E402
import kalshi_signal_map as sm  # noqa: E402
import kalshi_tick as tick  # noqa: E402


# --------------------------------------------------------------- fake client
class FakeClient:
    """Deterministic stand-in. `book` maps ticker -> (yes_bid, yes_ask, bid_sz, ask_sz)."""

    def __init__(self, markets: list[dict], book: dict[str, tuple]):
        self._markets, self._book = markets, book
        self.placed: list[dict] = []

    def markets(self, series_ticker=None, limit=1000, **_):
        return [m for m in self._markets if m["ticker"].startswith(series_ticker or "")]

    def orderbook(self, ticker, depth=10):
        yb, ya, bs, asz = self._book[ticker]
        return {"yes": [(yb, bs)], "no": [(round(1 - ya, 4), asz)]}

    best_prices = staticmethod(KalshiClient.best_prices)

    def place_order(self, **kw):
        self.placed.append(kw)
        return {"order": {"order_id": "fake-1", "status": "resting"}}


def mk_market(ticker: str, bid: float, ask: float) -> dict:
    return {"ticker": ticker, "event_ticker": ticker,
            "yes_bid_dollars": f"{bid:.4f}", "yes_ask_dollars": f"{ask:.4f}"}


BASE_PARAMS = {
    "arm": "kalshi-1", "series_preference": ["TEST"],
    "max_spread_cents": 5.0, "min_depth_contracts": 50,
    "target_prob_lo": 0.35, "target_prob_hi": 0.65,
    "max_stake_dollars": 8.0, "min_contracts": 5,
    "max_concurrent_positions": 1, "daily_loss_cap_dollars": 3.0,
    "min_signal_score": 6, "order_style": "join_touch", "time_in_force": "",
}


def sig(action: str, score: int = 8) -> dict:
    leg = {"passed": True, "score": score, "setup_name": "TEST_SETUP"}
    return {"production_action": action, "spot": 773.0,
            "bull": leg if action == "ENTER_BULL" else {"score": 0},
            "bear": leg if action == "ENTER_BEAR" else {"score": 0},
            "written_at": "2026-08-09T18:00:00-04:00"}


# ------------------------------------------------------------------ fee math
def test_fee_formula_matches_published_rates():
    # maker = 25% of taker; ceiling applies to the ORDER TOTAL.
    assert fee_dollars(100, 0.50, maker=False) == pytest.approx(1.76, abs=0.01)
    assert fee_dollars(100, 0.50, maker=True) == pytest.approx(0.44, abs=0.01)
    # fee is symmetric around 0.50 and vanishes at the extremes
    assert fee_dollars(100, 0.20, maker=True) == fee_dollars(100, 0.80, maker=True)
    assert fee_dollars(100, 0.95, maker=True) < fee_dollars(100, 0.50, maker=True)


def test_small_orders_pay_the_ceiling_surcharge():
    """1-contract orders cost meaningfully more per contract -- min_contracts exists for this."""
    assert fee_dollars(1, 0.50, maker=False) / 1 > fee_dollars(500, 0.50, maker=False) / 500


# --------------------------------------------------------------- direction
def test_bull_buys_yes_and_bear_buys_no_on_the_same_ladder():
    ms = [mk_market("TEST-A", 0.49, 0.51)]
    fc = FakeClient(ms, {"TEST-A": (0.49, 0.51, 500, 500)})
    bull = sm.decide(fc, BASE_PARAMS, sig("ENTER_BULL"))
    bear = sm.decide(fc, BASE_PARAMS, sig("ENTER_BEAR"))
    assert bull.take and bull.side == "yes"
    assert bear.take and bear.side == "no"
    assert bull.ticker == bear.ticker, "both directions must express on ONE ladder"


def test_hold_never_trades():
    fc = FakeClient([mk_market("TEST-A", 0.49, 0.51)], {"TEST-A": (0.49, 0.51, 500, 500)})
    assert sm.decide(fc, BASE_PARAMS, sig("HOLD")).take is False


def test_score_below_gate_is_refused():
    fc = FakeClient([mk_market("TEST-A", 0.49, 0.51)], {"TEST-A": (0.49, 0.51, 500, 500)})
    d = sm.decide(fc, BASE_PARAMS, sig("ENTER_BULL", score=3))
    assert d.take is False and "score" in d.reason


# -------------------------------------------------------------------- gates
def test_wide_spread_is_refused():
    """C3 ported: wide books bleed. 10c spread must never trade at a 5c gate."""
    fc = FakeClient([mk_market("TEST-A", 0.45, 0.55)], {"TEST-A": (0.45, 0.55, 500, 500)})
    d = sm.decide(fc, BASE_PARAMS, sig("ENTER_BULL"))
    assert d.take is False


def test_thin_depth_is_refused():
    fc = FakeClient([mk_market("TEST-A", 0.49, 0.51)], {"TEST-A": (0.49, 0.51, 10, 10)})
    d = sm.decide(fc, BASE_PARAMS, sig("ENTER_BULL"))
    assert d.take is False


def test_out_of_band_price_is_refused():
    """A 0.95 contract is a near-certainty, not a directional expression."""
    fc = FakeClient([mk_market("TEST-A", 0.94, 0.95)], {"TEST-A": (0.94, 0.95, 500, 500)})
    assert sm.decide(fc, BASE_PARAMS, sig("ENTER_BULL")).take is False


# ------------------------------------------------------------------- sizing
def test_stake_never_exceeds_cap():
    fc = FakeClient([mk_market("TEST-A", 0.49, 0.51)], {"TEST-A": (0.49, 0.51, 5000, 5000)})
    d = sm.decide(fc, BASE_PARAMS, sig("ENTER_BULL"))
    assert d.take and d.stake_dollars <= BASE_PARAMS["max_stake_dollars"]


def test_size_never_exceeds_resting_depth():
    """Never size past the liquidity actually on the book."""
    p = dict(BASE_PARAMS, min_depth_contracts=5, max_stake_dollars=500.0)
    fc = FakeClient([mk_market("TEST-A", 0.49, 0.51)], {"TEST-A": (0.49, 0.51, 60, 60)})
    d = sm.decide(fc, p, sig("ENTER_BULL"))
    assert d.take and d.contracts <= 60


def test_breakeven_is_above_entry_price():
    """Fees must always push breakeven ABOVE what we paid -- never below."""
    fc = FakeClient([mk_market("TEST-A", 0.49, 0.51)], {"TEST-A": (0.49, 0.51, 500, 500)})
    d = sm.decide(fc, BASE_PARAMS, sig("ENTER_BULL"))
    assert d.take and d.breakeven_prob > d.limit_price_cents / 100.0


# ------------------------------------------------------------ safety posture
def test_client_exposes_no_market_order_path():
    """Taking the spread costs 5-6x the maker fee. There must be no way to do it by accident."""
    src = (HERE / "kalshi_client.py").read_text()
    assert '"type": "limit"' in src, "order body must hardcode limit"
    # The invariant is about the ORDER TYPE, not the word 'market' (which legitimately
    # appears in market-data paths like /markets and market_positions).
    for forbidden in ('"type": "market"', "'type': 'market'", '"type":"market"'):
        assert forbidden not in src, f"market-order type present: {forbidden}"
    # And the order body must never take type from a caller-supplied variable.
    assert '"type": type' not in src and '"type": order_type' not in src


def test_place_order_rejects_bad_inputs():
    c = KalshiClient()
    for kw in (
        dict(side="maybe", action="buy", count=1, limit_price_cents=50),
        dict(side="yes", action="hodl", count=1, limit_price_cents=50),
        dict(side="yes", action="buy", count=1, limit_price_cents=0),
        dict(side="yes", action="buy", count=1, limit_price_cents=100),
        dict(side="yes", action="buy", count=0, limit_price_cents=50),
    ):
        with pytest.raises(ValueError):
            c.place_order(ticker="T", client_order_id="x", **kw)


def test_shadow_is_default_without_env():
    os.environ.pop(tick.ARM_ENV, None)
    assert tick.is_armed() is False


def test_arm_requires_exact_flag():
    for bad in ("", "0", "true", "yes", "TRUE", " 1 x"):
        os.environ[tick.ARM_ENV] = bad
        assert tick.is_armed() is False, f"{bad!r} must not arm the lane"
    os.environ[tick.ARM_ENV] = "1"
    assert tick.is_armed() is True
    os.environ.pop(tick.ARM_ENV, None)


def test_stale_signal_age_is_computed():
    assert tick.signal_age_minutes({"written_at": "2026-08-09T18:00:00-04:00"}) > 0
    assert tick.signal_age_minutes({"written_at": "garbage"}) is None
    assert tick.signal_age_minutes({}) is None


def test_parlay_series_are_filtered_out():
    """KXMVE* parlays flood every listing and compound fee+spread per leg."""
    from kalshi_client import PARLAY_PREFIX
    assert PARLAY_PREFIX == "KXMVE"
    src = (HERE / "kalshi_client.py").read_text()
    assert "drop_parlays" in src


def test_params_file_is_valid_and_conservative():
    p = json.loads((HERE / "params.json").read_text())
    assert p["max_stake_dollars"] <= 10, "seed account is $10 -- stake cap must respect it"
    assert p["max_spread_cents"] <= 5
    assert p["min_signal_score"] >= 6
    assert p["max_concurrent_positions"] == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))

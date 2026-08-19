"""Guards for backtest/lib/option_iv_solve.py.

The load-bearing property is ROUND-TRIP CONSISTENCY: price a contract at a known vol, solve
the vol back from that price, and recover the input. If that breaks, every delta-matched
strike the expiry experiment selects is wrong in a way no downstream statistic can detect.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest" / "lib"))

import option_iv_solve as ivs  # noqa: E402


@pytest.mark.parametrize("vol", [0.08, 0.15, 0.22, 0.40, 0.85])
@pytest.mark.parametrize("right", ["C", "P"])
@pytest.mark.parametrize("moneyness", [0.90, 1.00, 1.08])
def test_iv_round_trips_the_vol_it_was_priced_at(vol, right, moneyness):
    spot, t = 700.0, 5 / 365.0
    strike = round(spot * moneyness, 2)
    price = ivs.bs_price(spot, strike, t, vol, right)
    vega = ivs.bs_vega(spot, strike, t, vol, right)
    try:
        solved = ivs.implied_vol(price, spot, strike, t, right)
    except ivs.OptionMathError as e:
        # A refusal is only acceptable where IV is genuinely unidentifiable. Assert the
        # solver refused for the RIGHT reason rather than treating any error as fine.
        # Three legitimate refusals, all meaning "this price carries no vol information":
        #   UNIDENTIFIABLE  -- vega dead zone
        #   no-arbitrage    -- price pinned at intrinsic (deep ITM, zero time value left)
        #   price must be>0 -- premium underflowed to zero (deep OTM at low vol/short DTE)
        msg = str(e)
        assert any(k in msg for k in ("UNIDENTIFIABLE", "no-arbitrage", "price must be > 0")), msg
        assert vega < 1.0, (
            f"solver refused at vega={vega:.3f}, which is NOT a dead zone -- it is "
            f"declining to solve a contract it should be able to solve"
        )
        return
    assert vega >= ivs._MIN_VEGA_IDENTIFIABLE
    assert solved == pytest.approx(vol, rel=1e-3), (
        f"IV round-trip failed: priced at {vol}, solved {solved} (vega {vega:.3f})"
    )


def test_put_call_parity_holds():
    spot, strike, t, vol, r = 700.0, 700.0, 30 / 365.0, 0.20, 0.036
    c = ivs.bs_price(spot, strike, t, vol, "C", rate=r)
    p = ivs.bs_price(spot, strike, t, vol, "P", rate=r)
    assert (c - p) == pytest.approx(spot - strike * math.exp(-r * t), abs=1e-6)


def test_atm_delta_is_near_half_and_deep_itm_near_one():
    spot, t, vol = 700.0, 7 / 365.0, 0.20
    assert abs(ivs.bs_delta(spot, 700.0, t, vol, "C")) == pytest.approx(0.5, abs=0.06)
    assert abs(ivs.bs_delta(spot, 500.0, t, vol, "C")) > 0.97
    assert abs(ivs.bs_delta(spot, 900.0, t, vol, "C")) < 0.03
    # Put deltas are negative by convention.
    assert ivs.bs_delta(spot, 700.0, t, vol, "P") < 0


def test_impossible_quotes_raise_rather_than_fabricating_a_vol():
    spot, strike, t = 700.0, 700.0, 5 / 365.0
    # Below intrinsic for a deep ITM call = arbitrage-violating.
    with pytest.raises(ivs.OptionMathError, match="no-arbitrage band"):
        ivs.implied_vol(1.0, spot, 500.0, t, "C")
    # Above the underlying = impossible for a call.
    with pytest.raises(ivs.OptionMathError, match="no-arbitrage band"):
        ivs.implied_vol(spot * 1.5, spot, strike, t, "C")
    with pytest.raises(ivs.OptionMathError):
        ivs.implied_vol(0.0, spot, strike, t, "C")


def test_expired_contract_refuses_to_price():
    with pytest.raises(ivs.OptionMathError, match="t_years must be > 0"):
        ivs.bs_price(700.0, 700.0, 0.0, 0.2, "C")


def test_delta_differs_by_dte_which_is_why_matching_must_be_on_delta():
    """The prereg's core reason for delta-matching: same strike, different DTE, different delta."""
    spot, strike, vol = 700.0, 715.0, 0.20
    short = abs(ivs.bs_delta(spot, strike, 3 / 365.0, vol, "C"))
    long_ = abs(ivs.bs_delta(spot, strike, 30 / 365.0, vol, "C"))
    assert long_ > short * 1.5, (
        f"same strike gave near-identical deltas at 3DTE ({short:.3f}) and 30DTE ({long_:.3f}); "
        f"if that were true, strike-matching would be equivalent and the prereg's "
        f"delta-matching requirement would be pointless"
    )


def test_pick_delta_matched_selects_nearest_and_skips_unsolvable():
    spot, t = 700.0, 7 / 365.0
    cands = []
    for k in (660.0, 690.0, 700.0, 710.0, 740.0):
        cands.append({"strike": k, "price": ivs.bs_price(spot, k, t, 0.20, "C")})
    cands.append({"strike": 705.0, "price": 999.0})  # impossible -> must be skipped

    got = ivs.pick_delta_matched(cands, 0.50, spot=spot, t_years=t, right="C")
    assert got is not None
    assert got["candidates_skipped_unsolvable"] == 1, "the impossible quote was not skipped"
    assert abs(abs(got["delta"]) - 0.50) < 0.06
    assert got["strike"] == 700.0, f"expected the ATM strike, got {got['strike']}"


def test_pick_delta_matched_returns_none_when_nothing_solves():
    got = ivs.pick_delta_matched(
        [{"strike": 700.0, "price": 99999.0}], 0.50, spot=700.0, t_years=0.02, right="C"
    )
    assert got is None, "unsolvable-only input must yield None, never a fabricated pick"

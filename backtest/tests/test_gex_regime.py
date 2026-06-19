"""Unit tests for lib.engine.gex_regime — the dealer-GEX regime tag (Game Plan 1B).

Pure-function tests on SYNTHETIC chains: no network, no data files. Pins
  * the GEX_strike formula (gamma*OI*100*spot^2*0.01, calls +, puts -),
  * net-sign -> regime mapping (long_gamma_pin / short_gamma_trend / flat),
  * zero-gamma flip detection + interpolation,
  * call/put wall identification,
  * input validation (bad spot, empty chain) and the OCC-symbol adapter.

Run:  cd backtest && python -m pytest tests/test_gex_regime.py -q
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

from lib.engine.gex_regime import (  # noqa: E402
    CONTRACT_MULTIPLIER,
    GammaContract,
    GexRegime,
    assess_backtest_feasibility,
    compute_gex_regime,
    from_alpaca_snapshot,
    net_gex_at,
    _parse_occ_symbol,
    _strike_gex,
)


# ── formula ──────────────────────────────────────────────────────────────────
def test_strike_gex_call_positive_matches_formula():
    spot = 600.0
    c = GammaContract(strike=600.0, option_type="call", gamma=0.05, open_interest=1000)
    expected = 0.05 * 1000 * CONTRACT_MULTIPLIER * (spot ** 2) * 0.01 * 1.0
    assert _strike_gex(c, spot) == pytest.approx(expected)
    assert _strike_gex(c, spot) > 0  # calls add positive dealer gamma


def test_strike_gex_put_is_negative():
    spot = 600.0
    p = GammaContract(strike=600.0, option_type="put", gamma=0.05, open_interest=1000)
    assert _strike_gex(p, spot) < 0
    # symmetric magnitude to the same-params call (only the sign flips)
    c = GammaContract(strike=600.0, option_type="call", gamma=0.05, open_interest=1000)
    assert _strike_gex(p, spot) == pytest.approx(-_strike_gex(c, spot))


def test_net_gex_sums_signed_contributions():
    spot = 600.0
    chain = [
        GammaContract(600.0, "call", 0.05, 2000),  # +
        GammaContract(600.0, "put", 0.05, 1000),   # - (half the call notional)
    ]
    net = net_gex_at(chain, spot)
    one = _strike_gex(GammaContract(600.0, "call", 0.05, 1000), spot)
    assert net == pytest.approx(one)  # 2*one (call) + (-one) (put) == one


# ── regime classification ────────────────────────────────────────────────────
def test_net_long_gamma_is_pin_regime():
    spot = 600.0
    chain = [
        GammaContract(600.0, "call", 0.05, 5000),
        GammaContract(600.0, "put", 0.05, 1000),
    ]
    r = compute_gex_regime(chain, spot)
    assert r.net_gex > 0
    assert r.net_gex_sign == "long"
    assert r.regime == "long_gamma_pin"
    assert isinstance(r, GexRegime)


def test_net_short_gamma_is_trend_regime():
    spot = 600.0
    chain = [
        GammaContract(600.0, "call", 0.05, 1000),
        GammaContract(600.0, "put", 0.05, 5000),  # puts dominate -> net short
    ]
    r = compute_gex_regime(chain, spot)
    assert r.net_gex < 0
    assert r.net_gex_sign == "short"
    assert r.regime == "short_gamma_trend"


def test_balanced_chain_is_flat():
    spot = 600.0
    chain = [
        GammaContract(600.0, "call", 0.05, 1000),
        GammaContract(600.0, "put", 0.05, 1000),
    ]
    r = compute_gex_regime(chain, spot)
    assert r.net_gex == pytest.approx(0.0)
    assert r.net_gex_sign == "flat"
    assert r.regime == "flat"


# ── zero-gamma flip ──────────────────────────────────────────────────────────
def test_zero_gamma_flip_found_between_call_and_put_clusters():
    """Calls concentrated above spot, puts below: net GEX should flip sign within
    the search band, so a flip level is reported (not None)."""
    spot = 600.0
    chain = [
        # Put wall below — dominates dollar gamma at low spots.
        GammaContract(580.0, "put", 0.06, 8000),
        # Call wall above — dominates at higher spots.
        GammaContract(620.0, "call", 0.06, 8000),
        # A little balanced OI at the money.
        GammaContract(600.0, "call", 0.04, 1000),
        GammaContract(600.0, "put", 0.04, 1000),
    ]
    r = compute_gex_regime(chain, spot, flip_search_pct=0.08)
    # With equal gamma*OI on the call wall and put wall, the spot^2 weighting makes
    # net GEX rise with spot; the curve crosses zero somewhere in the band.
    assert r.zero_gamma_flip is not None
    assert r.spot * 0.92 <= r.zero_gamma_flip <= r.spot * 1.08


def test_no_flip_when_all_one_sign():
    """An all-call chain is positive everywhere -> no zero crossing -> flip is None."""
    spot = 600.0
    chain = [
        GammaContract(600.0, "call", 0.05, 1000),
        GammaContract(610.0, "call", 0.05, 1000),
    ]
    r = compute_gex_regime(chain, spot)
    assert r.net_gex > 0
    assert r.zero_gamma_flip is None


# ── walls ────────────────────────────────────────────────────────────────────
def test_call_and_put_walls_pick_largest_notional_strike():
    spot = 600.0
    chain = [
        GammaContract(605.0, "call", 0.05, 1000),
        GammaContract(610.0, "call", 0.05, 9000),   # biggest call gamma -> call wall
        GammaContract(595.0, "put", 0.05, 1000),
        GammaContract(590.0, "put", 0.05, 7000),    # biggest put gamma -> put wall
    ]
    r = compute_gex_regime(chain, spot)
    assert r.call_wall is not None and r.call_wall.strike == 610.0
    assert r.put_wall is not None and r.put_wall.strike == 590.0
    assert r.call_wall.gex_notional > 0


def test_walls_none_when_side_absent():
    spot = 600.0
    chain = [GammaContract(600.0, "call", 0.05, 1000)]
    r = compute_gex_regime(chain, spot)
    assert r.call_wall is not None
    assert r.put_wall is None  # no puts in the chain


# ── input validation ─────────────────────────────────────────────────────────
def test_bad_spot_raises():
    chain = [GammaContract(600.0, "call", 0.05, 1000)]
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            compute_gex_regime(chain, bad)


def test_empty_or_unusable_chain_raises():
    with pytest.raises(ValueError):
        compute_gex_regime([], 600.0)
    # OI<=0 and non-finite gamma rows are all dropped -> unusable -> raises.
    junk = [
        GammaContract(600.0, "call", 0.05, 0),         # OI 0
        GammaContract(600.0, "put", float("nan"), 100),  # bad gamma
        GammaContract(600.0, "spread", 0.05, 100),     # bad type
    ]
    with pytest.raises(ValueError):
        compute_gex_regime(junk, 600.0)


def test_unusable_rows_are_filtered_but_good_rows_survive():
    spot = 600.0
    chain = [
        GammaContract(600.0, "call", 0.05, 1000),   # good
        GammaContract(600.0, "put", 0.05, 0),        # dropped (OI 0)
        GammaContract(600.0, "xxx", 0.05, 1000),     # dropped (bad type)
    ]
    r = compute_gex_regime(chain, spot)
    assert r.n_contracts == 1
    assert r.net_gex > 0  # only the call survived


# ── to_dict / JSON-friendliness ──────────────────────────────────────────────
def test_to_dict_round_trips_keys():
    spot = 600.0
    chain = [
        GammaContract(610.0, "call", 0.05, 2000),
        GammaContract(590.0, "put", 0.05, 3000),
    ]
    d = compute_gex_regime(chain, spot).to_dict()
    for k in ("net_gex", "net_gex_sign", "regime", "zero_gamma_flip",
              "call_wall", "put_wall", "spot", "n_contracts"):
        assert k in d
    # walls serialise to nested dicts (or None), never the dataclass.
    assert d["put_wall"] is None or isinstance(d["put_wall"], dict)


# ── OCC symbol parsing + Alpaca adapter ──────────────────────────────────────
def test_parse_occ_symbol():
    assert _parse_occ_symbol("SPY260501P00721000") == ("put", 721.0)
    assert _parse_occ_symbol("SPY260501C00580000") == ("call", 580.0)
    assert _parse_occ_symbol("SPY260501C00585500") == ("call", 585.5)
    assert _parse_occ_symbol("NOTANOPTION") is None


def test_from_alpaca_snapshot_parses_chain():
    # Mimic the get_option_snapshot shape: symbol -> {greeks:{gamma}, open_interest}.
    snap = {
        "snapshots": {
            "SPY260501C00721000": {"greeks": {"gamma": 0.04}, "open_interest": 1200},
            "SPY260501P00721000": {"greeks": {"gamma": 0.04}, "open_interest": 3400},
            "SPY260501C00999000": {"greeks": {}, "open_interest": 10},  # no gamma -> skip
        }
    }
    contracts = from_alpaca_snapshot(snap)
    assert len(contracts) == 2
    types = sorted(c.option_type for c in contracts)
    assert types == ["call", "put"]
    # And it flows into compute_gex_regime: puts dominate -> short gamma.
    r = compute_gex_regime(contracts, spot=721.0)
    assert r.net_gex < 0 and r.regime == "short_gamma_trend"


# ── feasibility honesty ──────────────────────────────────────────────────────
def test_backtest_feasibility_is_honest_no():
    f = assess_backtest_feasibility()
    assert f["can_backtest_now"] is False
    assert "OPEN INTEREST" in f["reason"] or "open interest" in f["reason"].lower()
    assert "LIVE" in f["position"]

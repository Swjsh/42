"""Unit + parity tests for the multi-leg credit simulator.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_simulator_credit.py -v
"""
from __future__ import annotations

import datetime as dt

import pytest

from lib.multileg_structures import (
    Leg, build_legs, band_strikes, legs_in_band, max_loss_per_contract,
)
from lib import simulator_credit as sc


# ──────────────────────────────────────────────────────────────────────────
# Structure builder unit tests
# ──────────────────────────────────────────────────────────────────────────

def test_pcs_legs():
    legs = build_legs(750.0, "PCS", short_offset=3, wing_width=2)
    assert legs == [Leg(747, "P", -1), Leg(745, "P", +1)]


def test_ccs_legs():
    legs = build_legs(750.0, "CCS", short_offset=3, wing_width=2)
    assert legs == [Leg(753, "C", -1), Leg(755, "C", +1)]


def test_ic_legs_symmetric():
    legs = build_legs(750.0, "IC", short_offset=3, wing_width=2)
    assert legs == [
        Leg(747, "P", -1), Leg(745, "P", +1),
        Leg(753, "C", -1), Leg(755, "C", +1),
    ]


def test_ib_legs_atm_shorts():
    # Iron fly: both shorts at ATM, wings $2 out.
    legs = build_legs(750.0, "IB", short_offset=0, wing_width=2)
    assert legs == [
        Leg(750, "P", -1), Leg(748, "P", +1),
        Leg(750, "C", -1), Leg(752, "C", +1),
    ]


def test_bwic_asymmetric():
    legs = build_legs(750.0, "BWIC", short_offset=2, wing_width=2,
                      call_short_offset=4, call_wing_width=3)
    assert legs == [
        Leg(748, "P", -1), Leg(746, "P", +1),
        Leg(754, "C", -1), Leg(757, "C", +1),
    ]


def test_builder_rejects_bad_wing():
    with pytest.raises(ValueError):
        build_legs(750.0, "PCS", short_offset=3, wing_width=0)


def test_max_loss_formula():
    # $5-wide condor, $1.50 credit -> (5-1.5)*100 = $350/contract.
    assert max_loss_per_contract(5, 1.50) == 350.0


def test_band_strikes_width():
    band = band_strikes(750.0, half_width=5)
    assert band == set(range(745, 756))
    assert len(band) == 11


def test_legs_in_band_skip():
    # A $4 short + $3 wing on the put side reaches 743 — outside an 11-wide band? band is
    # 745..755 for spot 750. 743 is OUTSIDE -> not in band.
    legs = build_legs(750.0, "PCS", short_offset=4, wing_width=3)  # short 746, long 743
    assert legs_in_band(legs, 750.0) is False
    legs2 = build_legs(750.0, "PCS", short_offset=2, wing_width=2)  # short 748, long 746
    assert legs_in_band(legs2, 750.0) is True


# ──────────────────────────────────────────────────────────────────────────
# Engine tests with a synthetic in-memory cache (monkeypatched loader)
# ──────────────────────────────────────────────────────────────────────────

def _mk_bars(timestamps, opens, highs, lows, closes):
    import pandas as pd
    return pd.DataFrame({
        "timestamp_et": pd.to_datetime(timestamps),
        "open": opens, "high": highs, "low": lows, "close": closes,
        "volume": [100] * len(opens), "vwap": opens, "trade_count": [10] * len(opens),
    })


@pytest.fixture
def fake_cache(monkeypatch):
    """Map option_symbol -> synthetic DataFrame. Test sets _DB[sym] = df."""
    db: dict = {}

    def fake_load(symbol):
        return db.get(symbol)

    monkeypatch.setattr(sc, "load_contract_bars", fake_load)
    return db


def _ts(date, *hhmm):
    base = []
    for h, m in hhmm:
        base.append(dt.datetime(date.year, date.month, date.day, h, m))
    return base


def test_credit_sign_positive(fake_cache):
    """Net credit must be positive for a PCS (short bid > long ask)."""
    date = dt.date(2026, 6, 18)
    spot = 750.0
    legs = build_legs(spot, "PCS", short_offset=3, wing_width=2)  # short 747P, long 745P
    times = _ts(date, (9, 40), (9, 45), (9, 50), (15, 50))
    # short put 747: opens at 2.00 ; long put 745: opens at 1.00 -> credit ~ (2-1)*100=100
    fake_cache[sc.option_symbol(date, 747, "P")] = _mk_bars(
        times, [2.00, 1.50, 1.20, 0.50], [2.0, 1.6, 1.3, 0.6], [1.4, 1.1, 0.9, 0.3], [1.5, 1.2, 1.0, 0.40])
    fake_cache[sc.option_symbol(date, 745, "P")] = _mk_bars(
        times, [1.00, 0.70, 0.50, 0.20], [1.0, 0.8, 0.6, 0.3], [0.6, 0.4, 0.3, 0.1], [0.70, 0.50, 0.40, 0.15])
    f = sc.simulate_credit_trade(date, legs, dt.datetime(date.year, 6, 18, 9, 40), spot,
                                 wing_width=2, structure_name="PCS",
                                 pt_frac=0.5, stop_mult=2.0, commission_per_contract=0.0)
    assert not f.skipped, f.skip_reason
    # entry on 9:45 bar (next after 9:40 decision): short bid=1.5-0.02, long ask=0.7+0.02
    assert f.net_credit > 0


def test_both_shorts_expire_otm_nets_credit(fake_cache):
    """Sanity: IC where both shorts decay toward 0 by EOD nets ~ +credit (minus costs)."""
    date = dt.date(2026, 6, 18)
    spot = 750.0
    legs = build_legs(spot, "IC", short_offset=3, wing_width=2)  # 747P/745P + 753C/755C
    times = _ts(date, (9, 40), (9, 45), (15, 50))
    # All premiums decay to near-zero by 15:50 (both sides finish OTM).
    fake_cache[sc.option_symbol(date, 747, "P")] = _mk_bars(times, [2.0, 1.5, 0.05], [2.0, 1.6, 0.08], [1.4, 1.1, 0.02], [1.5, 0.9, 0.05])
    fake_cache[sc.option_symbol(date, 745, "P")] = _mk_bars(times, [1.0, 0.6, 0.02], [1.0, 0.7, 0.03], [0.6, 0.4, 0.01], [0.7, 0.4, 0.02])
    fake_cache[sc.option_symbol(date, 753, "C")] = _mk_bars(times, [2.0, 1.4, 0.05], [2.0, 1.5, 0.07], [1.4, 1.0, 0.02], [1.5, 0.9, 0.05])
    fake_cache[sc.option_symbol(date, 755, "C")] = _mk_bars(times, [1.0, 0.6, 0.02], [1.0, 0.7, 0.03], [0.6, 0.4, 0.01], [0.7, 0.4, 0.02])
    # No PT/stop should fire if pt very high & stop disabled -> hold to EOD, mark to close.
    f = sc.simulate_credit_trade(date, legs, dt.datetime(2026, 6, 18, 9, 40), spot,
                                 wing_width=2, structure_name="IC",
                                 pt_frac=99.0, stop_mult=None, commission_per_contract=0.0)
    assert not f.skipped, f.skip_reason
    assert f.exit_reason == "EOD"
    # Entry credit ~ (short bid - long ask) both sides; at EOD shorts ~0.05 long ~0.02:
    # we keep almost all the credit. Realized must be POSITIVE and close to net_credit.
    assert f.realized_pnl > 0
    assert f.realized_pnl > 0.5 * f.net_credit


def test_breached_spread_loses_near_max(fake_cache):
    """A PCS fully breached (spot crashes through long strike) loses ~ -(width-credit)."""
    date = dt.date(2026, 6, 18)
    spot = 750.0
    legs = build_legs(spot, "PCS", short_offset=2, wing_width=2)  # short 748P, long 746P
    times = _ts(date, (9, 40), (9, 45), (15, 50))
    # Crash: both puts deep ITM at EOD. width=2 -> short~ (748-740)=8? keep within band sense:
    # short 748 premium balloons to ~5.0, long 746 to ~3.0 by EOD; difference -> near width.
    fake_cache[sc.option_symbol(date, 748, "P")] = _mk_bars(times, [1.5, 2.0, 8.0], [1.6, 9.0, 9.0], [1.4, 1.9, 7.5], [1.55, 8.5, 8.0])
    fake_cache[sc.option_symbol(date, 746, "P")] = _mk_bars(times, [0.8, 1.2, 6.0], [0.9, 7.0, 7.0], [0.7, 1.1, 5.5], [0.85, 6.5, 6.0])
    f = sc.simulate_credit_trade(date, legs, dt.datetime(2026, 6, 18, 9, 40), spot,
                                 wing_width=2, structure_name="PCS",
                                 pt_frac=99.0, stop_mult=None, commission_per_contract=0.0)
    assert not f.skipped, f.skip_reason
    # Loss should be negative and within (i.e. not worse than) the defined max loss.
    assert f.realized_pnl < 0
    assert f.realized_pnl >= -f.max_loss_defined - 5.0  # tiny tolerance for slippage


def test_stop_before_pt_same_bar(fake_cache):
    """If a bar would trigger BOTH stop and PT, STOP wins (conservative)."""
    date = dt.date(2026, 6, 18)
    spot = 750.0
    legs = build_legs(spot, "PCS", short_offset=3, wing_width=2)
    times = _ts(date, (9, 40), (9, 45), (9, 50))
    # Set premiums so that at 9:50 the short has ballooned (loss): open_pnl <= -2*credit.
    fake_cache[sc.option_symbol(date, 747, "P")] = _mk_bars(times, [2.0, 1.5, 5.0], [2.0, 1.6, 5.0], [1.4, 1.1, 4.5], [1.5, 1.2, 5.0])
    fake_cache[sc.option_symbol(date, 745, "P")] = _mk_bars(times, [1.0, 0.7, 2.0], [1.0, 0.8, 2.0], [0.6, 0.4, 1.8], [0.7, 0.5, 2.0])
    f = sc.simulate_credit_trade(date, legs, dt.datetime(2026, 6, 18, 9, 40), spot,
                                 wing_width=2, structure_name="PCS",
                                 pt_frac=0.5, stop_mult=2.0, commission_per_contract=0.0)
    assert not f.skipped, f.skip_reason
    assert f.exit_reason == "STOP"


def test_no_look_ahead_entry_after_decision(fake_cache):
    """Entry fill must be strictly AFTER the decision time."""
    date = dt.date(2026, 6, 18)
    spot = 750.0
    legs = build_legs(spot, "PCS", short_offset=3, wing_width=2)
    times = _ts(date, (9, 40), (9, 45), (15, 50))
    fake_cache[sc.option_symbol(date, 747, "P")] = _mk_bars(times, [2.0, 1.5, 0.1], [2.0, 1.6, 0.1], [1.4, 1.1, 0.05], [1.5, 1.2, 0.08])
    fake_cache[sc.option_symbol(date, 745, "P")] = _mk_bars(times, [1.0, 0.7, 0.05], [1.0, 0.8, 0.06], [0.6, 0.4, 0.02], [0.7, 0.5, 0.04])
    decision = dt.datetime(2026, 6, 18, 9, 40)
    f = sc.simulate_credit_trade(date, legs, decision, spot, wing_width=2,
                                 structure_name="PCS", commission_per_contract=0.0)
    assert not f.skipped, f.skip_reason
    assert f.entry_time_et > decision


def test_skip_when_strike_missing(fake_cache):
    """A required strike outside the band (no CSV) returns a SKIPPED record, not a crash."""
    date = dt.date(2026, 6, 18)
    spot = 750.0
    legs = build_legs(spot, "PCS", short_offset=3, wing_width=2)  # needs 747P + 745P
    # Only the short leg is in the fake cache; the wing is missing.
    times = _ts(date, (9, 40), (9, 45))
    fake_cache[sc.option_symbol(date, 747, "P")] = _mk_bars(times, [2.0, 1.5], [2.0, 1.6], [1.4, 1.1], [1.5, 1.2])
    f = sc.simulate_credit_trade(date, legs, dt.datetime(2026, 6, 18, 9, 40), spot,
                                 wing_width=2, structure_name="PCS")
    assert f.skipped
    assert "missing_cache" in f.skip_reason


def test_parity_naked_short_sign_flip(fake_cache):
    """Parity (abstract): a 'spread' with NO long leg = a naked short whose P&L is the
    SIGN-FLIP of the long-premium path a buyer would realize on the same contract.
    Buyer pnl (entry->exit, per share) = (exit - entry). Seller = -(exit-entry).
    Here we run a single short leg and check the sign flips vs a hand-computed buyer path.
    """
    date = dt.date(2026, 6, 18)
    spot = 750.0
    short_only = [Leg(747, "P", -1)]
    times = _ts(date, (9, 40), (9, 45), (15, 50))
    # premium falls 1.5 -> 0.5 by EOD: BUYER would lose ~ (0.5-1.5)=-1.0/share; SELLER gains.
    fake_cache[sc.option_symbol(date, 747, "P")] = _mk_bars(times, [2.0, 1.5, 0.5], [2.0, 1.6, 0.6], [1.4, 1.1, 0.4], [1.5, 1.2, 0.5])
    f = sc.simulate_credit_trade(date, short_only, dt.datetime(2026, 6, 18, 9, 40), spot,
                                 wing_width=999, structure_name="NAKED",
                                 pt_frac=99.0, stop_mult=None,
                                 entry_slippage=0.0, exit_slippage=0.0, commission_per_contract=0.0)
    assert not f.skipped, f.skip_reason
    # entry fill = 9:45 open 1.5 (bid, no slip); exit = 15:50 close 0.5 (ask, no slip).
    # seller pnl = (entry - exit)*100 = (1.5-0.5)*100 = +100. Buyer would be -100. Sign flips.
    assert abs(f.realized_pnl - 100.0) < 1e-6


def test_expiry_intrinsic_settlement():
    """settle_expiry_intrinsic: both shorts OTM at close -> keep full credit."""
    legs = build_legs(750.0, "IC", short_offset=3, wing_width=2)  # 747P/745P 753C/755C
    net_credit = 120.0
    # SPY closes at 750 -> all strikes OTM -> intrinsic 0 -> keep credit minus commission.
    pnl = sc.settle_expiry_intrinsic(legs, net_credit, spot_close=750.0, contracts=1,
                                     commission_per_contract=0.0)
    assert abs(pnl - 120.0) < 1e-6
    # SPY crashes to 744 -> put side breached: short 747 owes 3, long 745 collects 1 ->
    # net intrinsic owed = (3-1)*100 = 200. pnl = 120 - 200 = -80.
    pnl2 = sc.settle_expiry_intrinsic(legs, net_credit, spot_close=744.0, contracts=1,
                                      commission_per_contract=0.0)
    assert abs(pnl2 - (-80.0)) < 1e-6

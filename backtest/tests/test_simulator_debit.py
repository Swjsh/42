"""Unit + sanity tests for the multi-leg DEBIT-vertical simulator.

A DEBIT vertical = BUY near strike + SELL further-OTM strike (same side); net debit
PAID at entry; max gain = (width - debit); max loss = debit. These tests pin the two
anchor cases the task requires (fully-ITM nets ~+(width-debit); fully-OTM nets ~-debit),
plus no-look-ahead, the credit-skip guard, intraday PT/STOP, and expiry settlement.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_simulator_debit.py -v
"""
from __future__ import annotations

import datetime as dt

import pytest

from lib.multileg_structures import Leg
from lib import simulator_debit as sd
from lib import simulator_credit as sc  # shared loader / monkeypatch point


# ──────────────────────────────────────────────────────────────────────────
# Leg builder unit tests
# ──────────────────────────────────────────────────────────────────────────

def test_debit_call_vertical_legs():
    # Bullish: BUY ATM call, SELL $2-OTM call.
    legs = sd.build_debit_vertical(750.0, "C", near_offset=0, width=2)
    assert legs == [Leg(750, "C", +1), Leg(752, "C", -1)]


def test_debit_put_vertical_legs():
    # Bearish: BUY ATM put, SELL $2-OTM put.
    legs = sd.build_debit_vertical(750.0, "P", near_offset=0, width=2)
    assert legs == [Leg(750, "P", +1), Leg(748, "P", -1)]


def test_debit_itm_long_leg():
    # near_offset -1 => long leg ITM by $1 (call long strike below ATM).
    legs = sd.build_debit_vertical(750.0, "C", near_offset=-1, width=2)
    assert legs == [Leg(749, "C", +1), Leg(751, "C", -1)]


def test_builder_rejects_bad_width():
    with pytest.raises(ValueError):
        sd.build_debit_vertical(750.0, "C", near_offset=0, width=0)


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
    """Map option_symbol -> synthetic DataFrame. Patches the SHARED loader the debit
    sim reaches through simulator_credit.load_contract_bars."""
    db: dict = {}

    def fake_load(symbol):
        return db.get(symbol)

    monkeypatch.setattr(sc, "load_contract_bars", fake_load)
    return db


def _ts(date, *hhmm):
    return [dt.datetime(date.year, date.month, date.day, h, m) for h, m in hhmm]


def test_debit_sign_positive(fake_cache):
    """Net entry must be a positive DEBIT (long ask > short bid)."""
    date = dt.date(2026, 6, 18)
    spot = 750.0
    legs = sd.build_debit_vertical(spot, "C", near_offset=0, width=2)  # long 750C, short 752C
    times = _ts(date, (9, 40), (9, 45), (15, 50))
    # long 750C opens 2.00 (we pay ask), short 752C opens 1.00 (we collect bid)
    fake_cache[sc.option_symbol(date, 750, "C")] = _mk_bars(
        times, [2.00, 2.10, 0.0], [2.1, 2.2, 0.1], [1.9, 2.0, 0.0], [2.05, 2.15, 0.0])
    fake_cache[sc.option_symbol(date, 752, "C")] = _mk_bars(
        times, [1.00, 1.05, 0.0], [1.1, 1.1, 0.05], [0.9, 1.0, 0.0], [1.02, 1.07, 0.0])
    f = sd.simulate_debit_trade(date, legs, dt.datetime(2026, 6, 18, 9, 40), spot,
                                width=2, pt_frac=None, stop_frac=None,
                                commission_per_contract=0.0)
    assert not f.skipped, f.skip_reason
    assert f.net_debit > 0
    # debit ~ (long_ask 2.10+.02) - (short_bid 1.05-.02) ~ (2.12 - 1.03) = 1.09 -> ~109
    assert 100 < f.net_debit < 120
    assert f.max_loss_defined == pytest.approx(f.net_debit)


def test_fully_itm_nets_width_minus_debit(fake_cache):
    """ANCHOR: a debit call spread fully ITM at EOD nets ~ +(width - debit)*100."""
    date = dt.date(2026, 6, 18)
    spot = 750.0
    legs = sd.build_debit_vertical(spot, "C", near_offset=0, width=2)  # long 750C, short 752C
    times = _ts(date, (9, 40), (9, 45), (15, 50))
    # SPY rips to ~755 by EOD: both calls deep ITM. long 750C close ~5.0, short 752C ~3.0.
    # Spread value at EOD = 5.0 - 3.0 = 2.0 = the full width. P&L = width - debit.
    fake_cache[sc.option_symbol(date, 750, "C")] = _mk_bars(
        times, [2.00, 2.05, 5.0], [2.1, 5.1, 5.1], [1.9, 2.0, 4.9], [2.02, 2.05, 5.0])
    fake_cache[sc.option_symbol(date, 752, "C")] = _mk_bars(
        times, [1.00, 1.02, 3.0], [1.1, 3.1, 3.1], [0.9, 1.0, 2.9], [1.01, 1.02, 3.0])
    f = sd.simulate_debit_trade(date, legs, dt.datetime(2026, 6, 18, 9, 40), spot,
                                width=2, pt_frac=None, stop_frac=None,  # ride to EOD
                                entry_slippage=0.0, exit_slippage=0.0,
                                commission_per_contract=0.0)
    assert not f.skipped, f.skip_reason
    assert f.exit_reason == "EOD"
    # entry debit = long 2.05 - short 1.02 = 1.03 -> 103. EOD spread = 5.0-3.0=2.0 -> 200.
    # realized = (200 - 103) = +97 ~= (width 2.0 - debit 1.03)*100 = +97.
    assert f.net_debit == pytest.approx(103.0, abs=0.5)
    assert f.realized_pnl == pytest.approx(97.0, abs=1.0)
    assert f.realized_pnl > 0
    # bounded by the defined max gain (width - debit)
    assert f.realized_pnl <= f.max_gain_defined + 1e-6


def test_fully_otm_nets_minus_debit(fake_cache):
    """ANCHOR: a debit call spread fully OTM (both legs expire worthless) nets ~ -debit."""
    date = dt.date(2026, 6, 18)
    spot = 750.0
    legs = sd.build_debit_vertical(spot, "C", near_offset=0, width=2)  # long 750C, short 752C
    times = _ts(date, (9, 40), (9, 45), (15, 50))
    # SPY fades; both calls decay to ~0 by EOD. Spread value -> 0 -> lose the whole debit.
    fake_cache[sc.option_symbol(date, 750, "C")] = _mk_bars(
        times, [2.00, 2.02, 0.02], [2.1, 2.1, 0.05], [1.9, 1.0, 0.01], [2.01, 1.50, 0.02])
    fake_cache[sc.option_symbol(date, 752, "C")] = _mk_bars(
        times, [1.00, 1.01, 0.01], [1.1, 1.1, 0.02], [0.9, 0.5, 0.0], [1.00, 0.70, 0.01])
    f = sd.simulate_debit_trade(date, legs, dt.datetime(2026, 6, 18, 9, 40), spot,
                                width=2, pt_frac=None, stop_frac=None,  # ride to EOD
                                entry_slippage=0.0, exit_slippage=0.0,
                                commission_per_contract=0.0)
    assert not f.skipped, f.skip_reason
    assert f.exit_reason == "EOD"
    # entry debit = 2.02 - 1.01 = 1.01 -> 101. EOD spread = 0.02-0.01=0.01 -> 1. loss ~ -100.
    assert f.net_debit == pytest.approx(101.0, abs=0.5)
    assert f.realized_pnl == pytest.approx(-100.0, abs=1.5)
    assert f.realized_pnl < 0
    # never worse than the defined max loss (the debit paid)
    assert f.realized_pnl >= -f.max_loss_defined - 1e-6


def test_credit_pricing_skips(fake_cache):
    """Defensive: if the geometry prices to a CREDIT (short bid > long ask), SKIP."""
    date = dt.date(2026, 6, 18)
    spot = 750.0
    legs = sd.build_debit_vertical(spot, "C", near_offset=0, width=2)
    times = _ts(date, (9, 40), (9, 45), (15, 50))
    # Inverted: long opens CHEAPER than short -> net credit -> must skip.
    fake_cache[sc.option_symbol(date, 750, "C")] = _mk_bars(
        times, [1.00, 1.00, 0.0], [1.1, 1.1, 0.0], [0.9, 0.9, 0.0], [1.0, 1.0, 0.0])
    fake_cache[sc.option_symbol(date, 752, "C")] = _mk_bars(
        times, [2.00, 2.00, 0.0], [2.1, 2.1, 0.0], [1.9, 1.9, 0.0], [2.0, 2.0, 0.0])
    f = sd.simulate_debit_trade(date, legs, dt.datetime(2026, 6, 18, 9, 40), spot,
                                width=2, commission_per_contract=0.0)
    assert f.skipped
    assert "non_debit" in f.skip_reason


def test_pt_fires(fake_cache):
    """Intraday PT: open_pnl >= pt_frac*debit -> close at PT."""
    date = dt.date(2026, 6, 18)
    spot = 750.0
    legs = sd.build_debit_vertical(spot, "C", near_offset=0, width=3)
    times = _ts(date, (9, 40), (9, 45), (9, 50), (15, 50))
    # debit ~1.0. By 9:50 spread doubles -> open_pnl ~ +1.0*debit -> PT at pt_frac=1.0.
    fake_cache[sc.option_symbol(date, 750, "C")] = _mk_bars(
        times, [2.0, 2.0, 4.0, 0.5], [2.1, 2.1, 4.2, 0.6], [1.9, 1.9, 3.8, 0.4], [2.0, 2.0, 4.0, 0.5])
    fake_cache[sc.option_symbol(date, 753, "C")] = _mk_bars(
        times, [1.0, 1.0, 2.0, 0.2], [1.1, 1.1, 2.1, 0.3], [0.9, 0.9, 1.9, 0.1], [1.0, 1.0, 2.0, 0.2])
    f = sd.simulate_debit_trade(date, legs, dt.datetime(2026, 6, 18, 9, 40), spot,
                                width=3, pt_frac=1.0, stop_frac=None,
                                entry_slippage=0.0, exit_slippage=0.0,
                                commission_per_contract=0.0)
    assert not f.skipped, f.skip_reason
    assert f.exit_reason == "PT"
    assert f.realized_pnl > 0


def test_stop_fires(fake_cache):
    """Intraday STOP: open_pnl <= -stop_frac*debit -> close at STOP."""
    date = dt.date(2026, 6, 18)
    spot = 750.0
    legs = sd.build_debit_vertical(spot, "C", near_offset=0, width=3)
    times = _ts(date, (9, 40), (9, 45), (9, 50), (15, 50))
    # spread halves by 9:50 -> open_pnl ~ -0.5*debit -> STOP at stop_frac=0.5.
    fake_cache[sc.option_symbol(date, 750, "C")] = _mk_bars(
        times, [2.0, 2.0, 1.3, 1.0], [2.1, 2.1, 1.4, 1.1], [1.9, 1.9, 1.2, 0.9], [2.0, 2.0, 1.3, 1.0])
    fake_cache[sc.option_symbol(date, 753, "C")] = _mk_bars(
        times, [1.0, 1.0, 0.8, 0.7], [1.1, 1.1, 0.9, 0.8], [0.9, 0.9, 0.7, 0.6], [1.0, 1.0, 0.8, 0.7])
    f = sd.simulate_debit_trade(date, legs, dt.datetime(2026, 6, 18, 9, 40), spot,
                                width=3, pt_frac=None, stop_frac=0.5,
                                entry_slippage=0.0, exit_slippage=0.0,
                                commission_per_contract=0.0)
    assert not f.skipped, f.skip_reason
    assert f.exit_reason == "STOP"
    assert f.realized_pnl < 0


def test_no_look_ahead_entry_after_decision(fake_cache):
    """Entry fill must be strictly AFTER the decision time."""
    date = dt.date(2026, 6, 18)
    spot = 750.0
    legs = sd.build_debit_vertical(spot, "C", near_offset=0, width=2)
    times = _ts(date, (9, 40), (9, 45), (15, 50))
    fake_cache[sc.option_symbol(date, 750, "C")] = _mk_bars(
        times, [2.0, 2.0, 3.0], [2.1, 2.1, 3.1], [1.9, 1.9, 2.9], [2.0, 2.0, 3.0])
    fake_cache[sc.option_symbol(date, 752, "C")] = _mk_bars(
        times, [1.0, 1.0, 1.5], [1.1, 1.1, 1.6], [0.9, 0.9, 1.4], [1.0, 1.0, 1.5])
    decision = dt.datetime(2026, 6, 18, 9, 40)
    f = sd.simulate_debit_trade(date, legs, decision, spot, width=2,
                                commission_per_contract=0.0)
    assert not f.skipped, f.skip_reason
    assert f.entry_time_et > decision


def test_skip_when_strike_missing(fake_cache):
    """A required strike with no CSV returns a SKIPPED record, not a crash."""
    date = dt.date(2026, 6, 18)
    spot = 750.0
    legs = sd.build_debit_vertical(spot, "C", near_offset=0, width=2)  # needs 750C + 752C
    times = _ts(date, (9, 40), (9, 45))
    fake_cache[sc.option_symbol(date, 750, "C")] = _mk_bars(
        times, [2.0, 2.0], [2.1, 2.1], [1.9, 1.9], [2.0, 2.0])  # short leg missing
    f = sd.simulate_debit_trade(date, legs, dt.datetime(2026, 6, 18, 9, 40), spot, width=2)
    assert f.skipped
    assert "missing_cache" in f.skip_reason


# ──────────────────────────────────────────────────────────────────────────
# Expiry-intrinsic settlement
# ──────────────────────────────────────────────────────────────────────────

def test_expiry_intrinsic_fully_itm():
    """ANCHOR: debit call spread fully ITM at expiry -> +(width - debit)."""
    legs = sd.build_debit_vertical(750.0, "C", near_offset=0, width=2)  # long 750C, short 752C
    net_debit = 100.0  # paid $1.00/share
    # SPY closes 755 -> long 750C intrinsic 5, short 752C intrinsic 3.
    # net intrinsic collected = (+1*5 - 1*3)*100 = 200. pnl = 200 - 100 = +100 = width-debit.
    pnl = sd.settle_expiry_intrinsic(legs, net_debit, spot_close=755.0,
                                     commission_per_contract=0.0)
    assert pnl == pytest.approx(100.0)


def test_expiry_intrinsic_fully_otm():
    """ANCHOR: debit call spread fully OTM at expiry -> -debit."""
    legs = sd.build_debit_vertical(750.0, "C", near_offset=0, width=2)
    net_debit = 100.0
    # SPY closes 745 -> both calls worthless -> net intrinsic 0 -> pnl = -debit = -100.
    pnl = sd.settle_expiry_intrinsic(legs, net_debit, spot_close=745.0,
                                     commission_per_contract=0.0)
    assert pnl == pytest.approx(-100.0)


def test_expiry_intrinsic_put_spread_itm():
    """Bearish debit put spread fully ITM at expiry -> +(width - debit)."""
    legs = sd.build_debit_vertical(750.0, "P", near_offset=0, width=2)  # long 750P, short 748P
    net_debit = 100.0
    # SPY closes 745 -> long 750P intrinsic 5, short 748P intrinsic 3.
    # net intrinsic = (+1*5 - 1*3)*100 = 200. pnl = 200 - 100 = +100.
    pnl = sd.settle_expiry_intrinsic(legs, net_debit, spot_close=745.0,
                                     commission_per_contract=0.0)
    assert pnl == pytest.approx(100.0)

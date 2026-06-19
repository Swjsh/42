"""Unit tests for the Webull history miner — symbol parsing + FIFO reconstruction.

These lock the load-bearing logic: OCC symbol parse, price/time parse, and the
FIFO round-trip matcher (partial fills, scaling in/out, 0DTE tag, expired-
worthless handling). Pure-Python, no I/O.
"""
from __future__ import annotations

import datetime as dt

import pytest

from autoresearch.webull_history_miner import (
    Fill,
    ParsedSymbol,
    parse_price,
    parse_symbol,
    parse_filled_time,
    reconstruct_round_trips,
)


# --------------------------------------------------------------------------- #
# symbol parsing
# --------------------------------------------------------------------------- #
def test_parse_symbol_spxw_call():
    p = parse_symbol("SPXW230920C04480000")
    assert p == ParsedSymbol("SPXW", dt.date(2023, 9, 20), "C", 4480.0, True)


def test_parse_symbol_spy_put():
    p = parse_symbol("SPY230710P00442000")
    assert p.underlier == "SPY"
    assert p.right == "P"
    assert p.strike == 442.0
    assert p.is_spx_family is True


def test_parse_symbol_non_family():
    p = parse_symbol("TSLA220218C00900000")
    assert p.underlier == "TSLA"
    assert p.is_spx_family is False
    assert p.strike == 900.0


def test_parse_symbol_xsp_is_family():
    p = parse_symbol("XSP221027C00388000")
    assert p.is_spx_family is True
    assert p.strike == 388.0


def test_parse_symbol_garbage_returns_none():
    assert parse_symbol("NOTASYMBOL") is None
    assert parse_symbol("") is None


# --------------------------------------------------------------------------- #
# price / time parsing
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("raw,expected", [
    ("@1.55", 1.55), ("1.55", 1.55), ("0.020", 0.02),
    ("@0.900", 0.9), ("", None), ("nan", None), (None, None),
])
def test_parse_price(raw, expected):
    assert parse_price(raw) == expected


def test_parse_filled_time_strips_tz():
    got = parse_filled_time("10/03/2023 12:36:56 EDT")
    assert got == dt.datetime(2023, 10, 3, 12, 36, 56)


def test_parse_filled_time_est():
    got = parse_filled_time("12/31/2021 10:50:57 EST")
    assert got == dt.datetime(2021, 12, 31, 10, 50, 57)


def test_parse_filled_time_blank():
    assert parse_filled_time("") is None
    assert parse_filled_time(None) is None


# --------------------------------------------------------------------------- #
# FIFO reconstruction
# --------------------------------------------------------------------------- #
def _f(symbol, side, qty, price, hh, mm):
    p = parse_symbol(symbol)
    return Fill(symbol=symbol, side=side, qty=qty, price=price,
                filled_time=dt.datetime(2023, 9, 20, hh, mm, 0), parsed=p)


def test_simple_roundtrip_win():
    fills = [
        _f("SPXW230920C04480000", "Buy", 2, 4.90, 9, 47),
        _f("SPXW230920C04480000", "Sell", 2, 3.30, 10, 14),
    ]
    trips, anomalies = reconstruct_round_trips(fills)
    assert anomalies == []
    assert len(trips) == 1
    t = trips[0]
    assert t.qty == 2
    assert t.entry_px == 4.90
    assert t.exit_px == 3.30
    # (3.30 - 4.90) * 2 * 100 = -320
    assert t.pnl == pytest.approx(-320.0)
    assert t.is_win is False
    assert t.bias == "bull"
    assert t.is_0dte is True  # expiry 2023-09-20 == fill date


def test_scaling_in_weighted_entry():
    # Two buys at different prices, one sell closes all 4 -> weighted entry.
    fills = [
        _f("SPXW230920P04195000", "Buy", 2, 5.00, 9, 50),
        _f("SPXW230920P04195000", "Buy", 2, 3.00, 10, 5),
        _f("SPXW230920P04195000", "Sell", 4, 6.00, 10, 30),
    ]
    trips, anomalies = reconstruct_round_trips(fills)
    assert anomalies == []
    assert len(trips) == 1
    t = trips[0]
    assert t.qty == 4
    assert t.entry_px == pytest.approx(4.0)  # (5*2 + 3*2)/4
    assert t.n_entry_fills == 2
    # (6 - 4) * 4 * 100 = 800
    assert t.pnl == pytest.approx(800.0)
    assert t.bias == "bear"


def test_scaling_out_two_sells_two_trips():
    # One buy of 4, two partial sells -> two round-trips, FIFO same entry px.
    fills = [
        _f("SPXW230920C04480000", "Buy", 4, 2.00, 9, 50),
        _f("SPXW230920C04480000", "Sell", 1, 4.00, 10, 0),
        _f("SPXW230920C04480000", "Sell", 3, 1.00, 10, 30),
    ]
    trips, _ = reconstruct_round_trips(fills)
    assert len(trips) == 2
    win, loss = trips[0], trips[1]
    assert win.qty == 1 and win.entry_px == 2.0 and win.exit_px == 4.0
    assert win.pnl == pytest.approx(200.0)
    assert loss.qty == 3 and loss.entry_px == 2.0 and loss.exit_px == 1.0
    assert loss.pnl == pytest.approx(-300.0)


def test_partial_fill_overflow_sell_logs_anomaly():
    # Sell more than was ever bought -> matched up to held, overflow anomaly.
    fills = [
        _f("SPXW230920C04480000", "Buy", 1, 2.00, 9, 50),
        _f("SPXW230920C04480000", "Sell", 3, 4.00, 10, 0),
    ]
    trips, anomalies = reconstruct_round_trips(fills)
    assert len(trips) == 1
    assert trips[0].qty == 1
    assert any(a["type"] == "sell_overflow" for a in anomalies)


def test_unclosed_0dte_expires_worthless():
    # 0DTE buy with no sell -> expired worthless, full premium loss.
    fills = [_f("SPXW230920C04480000", "Buy", 2, 1.50, 14, 0)]
    trips, _ = reconstruct_round_trips(fills)
    assert len(trips) == 1
    t = trips[0]
    assert t.status == "expired_worthless"
    assert t.pnl == pytest.approx(-300.0)  # -1.50 * 2 * 100
    assert t.exit_px == 0.0


def test_unclosed_longer_dated_marked_unclosed_no_pnl():
    # Longer-dated buy (expiry != fill date) with no sell -> unclosed, pnl 0.
    p = parse_symbol("SPXW231003P04200000")  # expiry 10/03
    f = Fill("SPXW231003P04200000", "Buy", 1, 0.90,
             dt.datetime(2023, 10, 2, 12, 0), p)  # filled 10/02
    trips, _ = reconstruct_round_trips([f])
    assert len(trips) == 1
    assert trips[0].status == "unclosed"
    assert trips[0].pnl == 0.0
    assert trips[0].is_0dte is False


def test_sell_without_open_is_anomaly_not_trade():
    fills = [_f("SPXW230920C04480000", "Sell", 1, 4.00, 10, 0)]
    trips, anomalies = reconstruct_round_trips(fills)
    assert trips == []
    assert anomalies and anomalies[0]["type"] == "sell_without_open"

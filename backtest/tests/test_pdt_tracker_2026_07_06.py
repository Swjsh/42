"""Guard for pdt_tracker.py -- Rule 7 (PDT) real day-trade counting.

Regression: circuit-breaker.json's day_trades_used_5d was a hardcoded 0, written
once at premarket and never incremented -- confirmed via the 2026-07-06 full-day
audit (8 same-day Safe round trips, zero PDT tracking; risk_gate.check_order's
`day_trades_i >= PDT_DAY_TRADE_LIMIT` can never trip against a value that never
moves off 0). This computes the real count from Alpaca's own fill history.

Also pins the two bugs the first draft of this module had, caught by running it
against Safe's REAL fill history before trusting it (see pdt_tracker.py's
module docstring): crypto round-trips (the nightly dress-rehearsal's $10 BTC
test) miscounted as day trades, and a UTC-vs-ET date-boundary bug that reads
"tomorrow" any time after 20:00 ET.
"""
from __future__ import annotations

import importlib
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "setup" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


@pytest.fixture()
def pdt():
    return importlib.import_module("pdt_tracker")


def _fill(symbol: str, side: str, ts: str, fill_id: str = "1") -> dict:
    return {"id": fill_id, "activity_type": "FILL", "symbol": symbol, "side": side,
            "transaction_time": ts}


# ---- trailing_business_days (as_of is ET-naive) ----

def test_trailing_business_days_excludes_weekends(pdt):
    # Monday 2026-07-06 -- trailing 5 business days should skip the weekend
    # (07-04 Sat / 07-05 Sun) and land on 06-29..07-03.
    as_of_et = datetime(2026, 7, 6, 10, 0)  # naive ET
    days = pdt.trailing_business_days(as_of_et, n=5)
    assert len(days) == 5
    assert all(d.weekday() < 5 for d in days)
    assert date(2026, 7, 4) not in days  # Saturday
    assert date(2026, 7, 5) not in days  # Sunday


# ---- compute_day_trades_used_5d (as_of is ET-naive; fill timestamps are UTC) ----

def test_same_day_round_trip_counts_as_one_day_trade(pdt):
    as_of_et = datetime(2026, 7, 6, 15, 0)
    acts = [
        _fill("SPY260706C00751000", "buy", "2026-07-06T18:21:33Z"),   # 14:21 ET
        _fill("SPY260706C00751000", "sell", "2026-07-06T18:34:27Z"),  # 14:34 ET
    ]
    assert pdt.compute_day_trades_used_5d(acts, as_of_et) == 1


def test_buy_and_sell_on_different_days_is_not_a_day_trade(pdt):
    as_of_et = datetime(2026, 7, 6, 15, 0)
    acts = [
        _fill("SPY260706C00751000", "buy", "2026-07-03T18:00:00Z"),
        _fill("SPY260706C00751000", "sell", "2026-07-06T18:00:00Z"),
    ]
    assert pdt.compute_day_trades_used_5d(acts, as_of_et) == 0


def test_multiple_round_trips_same_symbol_same_day_still_count_as_one(pdt):
    # FINRA rule: day-trading the SAME security multiple times in one day is
    # still exactly ONE day trade, not one per round trip.
    as_of_et = datetime(2026, 7, 6, 15, 0)
    acts = [
        _fill("SPY260706C00751000", "buy", "2026-07-06T17:11:36Z"),
        _fill("SPY260706C00751000", "sell", "2026-07-06T17:13:28Z"),
        _fill("SPY260706C00751000", "buy", "2026-07-06T17:13:40Z"),
        _fill("SPY260706C00751000", "sell", "2026-07-06T17:18:28Z"),
    ]
    assert pdt.compute_day_trades_used_5d(acts, as_of_et) == 1


def test_todays_real_shape_two_symbols_is_two_day_trades(pdt):
    # Mirrors 2026-07-06's ACTUAL Safe-account trading: repeated round trips on
    # SPY...751000C and SPY...750000P -- two distinct symbols traded same-day ->
    # exactly 2 day trades, regardless of how many round trips per symbol.
    as_of_et = datetime(2026, 7, 6, 15, 0)
    acts = [
        _fill("SPY260706C00751000", "buy", "2026-07-06T17:11:36Z"),
        _fill("SPY260706C00751000", "sell", "2026-07-06T17:13:28Z"),
        _fill("SPY260706C00751000", "buy", "2026-07-06T17:13:40Z"),
        _fill("SPY260706C00751000", "sell", "2026-07-06T17:18:28Z"),
        _fill("SPY260706P00750000", "buy", "2026-07-06T17:36:34Z"),
        _fill("SPY260706P00750000", "sell", "2026-07-06T17:37:28Z"),
        _fill("SPY260706C00751000", "buy", "2026-07-06T18:21:33Z"),
        _fill("SPY260706C00751000", "sell", "2026-07-06T18:34:27Z"),
    ]
    assert pdt.compute_day_trades_used_5d(acts, as_of_et) == 2


def test_round_trip_outside_the_5_business_day_window_does_not_count(pdt):
    as_of_et = datetime(2026, 7, 6, 15, 0)
    acts = [
        _fill("SPY260625C00700000", "buy", "2026-06-15T15:00:00Z"),
        _fill("SPY260625C00700000", "sell", "2026-06-15T15:30:00Z"),
    ]
    assert pdt.compute_day_trades_used_5d(acts, as_of_et) == 0


def test_non_fill_or_malformed_rows_are_ignored_not_fatal(pdt):
    as_of_et = datetime(2026, 7, 6, 15, 0)
    acts = [
        {"activity_type": "FEE", "net_amount": "-0.06"},  # no symbol/side -- must be skipped
        "not-a-dict",
        {"symbol": "X", "side": "buy", "transaction_time": "not-a-timestamp"},
        _fill("SPY260706C00751000", "buy", "2026-07-06T18:21:33Z"),
        _fill("SPY260706C00751000", "sell", "2026-07-06T18:34:27Z"),
    ]
    assert pdt.compute_day_trades_used_5d(acts, as_of_et) == 1


def test_empty_activities_is_zero(pdt):
    as_of_et = datetime(2026, 7, 6, 15, 0)
    assert pdt.compute_day_trades_used_5d([], as_of_et) == 0
    assert pdt.compute_day_trades_used_5d(None, as_of_et) == 0


# ---- bug #1 (caught live, 2026-07-06): crypto must NOT count toward PDT ----

def test_crypto_round_trip_never_counts_as_a_day_trade(pdt):
    # This is the exact shape of the nightly Gamma_DressRehearsal $10 BTC
    # round-trip test -- PDT does not apply to crypto at all.
    as_of_et = datetime(2026, 7, 6, 15, 0)
    acts = [
        _fill("BTC/USD", "buy", "2026-07-06T13:43:36Z"),
        _fill("BTC/USD", "sell", "2026-07-06T13:43:37Z"),
        _fill("UNI/USD", "buy", "2026-07-01T01:50:32Z"),
        _fill("UNI/USD", "sell", "2026-07-01T01:45:47Z"),
    ]
    assert pdt.compute_day_trades_used_5d(acts, as_of_et) == 0


def test_crypto_and_equity_same_day_only_equity_counts(pdt):
    as_of_et = datetime(2026, 7, 6, 15, 0)
    acts = [
        _fill("BTC/USD", "buy", "2026-07-06T13:43:36Z"),
        _fill("BTC/USD", "sell", "2026-07-06T13:43:37Z"),
        _fill("SPY260706C00751000", "buy", "2026-07-06T18:21:33Z"),
        _fill("SPY260706C00751000", "sell", "2026-07-06T18:34:27Z"),
    ]
    assert pdt.compute_day_trades_used_5d(acts, as_of_et) == 1


# ---- bug #2 (caught live, 2026-07-06): ET boundary, not UTC ----

def test_late_evening_utc_does_not_roll_the_trading_day_forward(pdt):
    # 2026-07-06 23:50 ET is still 2026-07-07 03:50 UTC -- a fill at 22:00 ET
    # (2026-07-07 02:00 UTC) must still land on the 07-06 ET trading day, not
    # get pushed to 07-07 by a naive UTC .date() read (the exact bug this
    # module shipped with before it was checked against real data).
    as_of_utc = datetime(2026, 7, 7, 3, 50, tzinfo=timezone.utc)  # 23:50 ET on 07-06
    acts = [
        _fill("SPY260706C00751000", "buy", "2026-07-07T02:00:00Z"),   # 22:00 ET 07-06
        _fill("SPY260706C00751000", "sell", "2026-07-07T02:30:00Z"),  # 22:30 ET 07-06
    ]
    from et_clock import et_now
    as_of_et = et_now(as_of_utc)
    assert as_of_et.date() == date(2026, 7, 6), "sanity: et_now must read 07-06, not 07-07"
    assert pdt.compute_day_trades_used_5d(acts, as_of_et) == 1


# ---- fetch_day_trades_used_5d (fail-open + real ET conversion) ----

def test_fetch_fail_open_on_network_error(pdt, monkeypatch):
    def _boom(*a, **k):
        raise OSError("Connection refused")
    monkeypatch.setattr(pdt.urllib.request, "urlopen", _boom)
    creds = {"base_url": "https://paper-api.alpaca.markets", "key": "x", "secret": "y"}
    assert pdt.fetch_day_trades_used_5d(creds) == 0


def test_fetch_fail_open_on_malformed_response(pdt, monkeypatch):
    class _FakeResp:
        def read(self):
            return b"not json"
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(pdt.urllib.request, "urlopen", lambda *a, **k: _FakeResp())
    creds = {"base_url": "https://paper-api.alpaca.markets", "key": "x", "secret": "y"}
    assert pdt.fetch_day_trades_used_5d(creds) == 0


def test_fetch_paginates_and_computes(pdt, monkeypatch):
    page1 = [_fill("SPY260706C00751000", "buy", "2026-07-06T18:21:33Z", fill_id=f"a{i}") for i in range(100)]
    page2 = [_fill("SPY260706C00751000", "sell", "2026-07-06T18:34:27Z", fill_id="b1")]
    calls = {"n": 0}

    class _FakeResp:
        def __init__(self, payload):
            self._payload = payload
        def read(self):
            import json as _j
            return _j.dumps(self._payload).encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def _fake_urlopen(req, timeout=10):
        calls["n"] += 1
        return _FakeResp(page1 if calls["n"] == 1 else page2)

    monkeypatch.setattr(pdt.urllib.request, "urlopen", _fake_urlopen)
    creds = {"base_url": "https://paper-api.alpaca.markets", "key": "x", "secret": "y"}
    as_of_utc = datetime(2026, 7, 6, 19, 0, tzinfo=timezone.utc)
    result = pdt.fetch_day_trades_used_5d(creds, as_of_utc)
    assert calls["n"] == 2, "must page past the first 100-row page"
    assert result == 1


# ---- wiring: heartbeat_core actually uses the live tracker, not the stale JSON ----

def test_heartbeat_core_execute_calls_pdt_tracker():
    import inspect
    sys.path.insert(0, str(_SCRIPTS))
    hc = importlib.import_module("heartbeat_core")
    src = inspect.getsource(hc._execute)
    assert "pdt_tracker" in src
    assert "fetch_day_trades_used_5d" in src

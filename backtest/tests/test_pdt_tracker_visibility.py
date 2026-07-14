"""Guard for pdt_tracker.py's PDT VISIBILITY extension (2026-07-14) --
compute_day_trades_detail / next_rolloff_date / fetch_day_trades_detail.

Motivation: analysis/daily-brief/2026-07-13-FULL-AUDIT.md #2 -- core Safe was
silently PDT-blocked ALL DAY on a day-trade count it INHERITED from an account
repoint (commit 61cfca0), found by a manual review, not an instrument. These
functions exist so a monitoring surface (self_check.py / firm_brief.py) can
show "N/limit used, rolls off <date>" and, critically, an HONEST UNKNOWN on a
fetch error instead of a silently-fabricated 0 (the trading-critical
fetch_day_trades_used_5d intentionally fails open to 0 -- this is a SEPARATE,
additive path that must not repeat that contract for a glance surface).

Also pins that the refactor of compute_day_trades_used_5d into a thin wrapper
over compute_day_trades_detail is byte-identical (test_pdt_tracker_2026_07_06.py
already covers this end-to-end; this file adds the NEW surface only, per the
"many small files" convention -- it does not duplicate that suite)."""
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


# ---- compute_day_trades_detail ----

def test_detail_count_matches_wrapper_two_symbols_two_dates(pdt):
    as_of_et = datetime(2026, 7, 13, 15, 0)
    acts = [
        _fill("SPY260709C1", "buy", "2026-07-09T17:00:00Z"),
        _fill("SPY260709C1", "sell", "2026-07-09T17:30:00Z"),
        _fill("SPY260710P1", "buy", "2026-07-10T17:00:00Z"),
        _fill("SPY260710P1", "sell", "2026-07-10T17:30:00Z"),
    ]
    detail = pdt.compute_day_trades_detail(acts, as_of_et)
    assert detail["count"] == 2
    assert detail["dates"] == ["2026-07-09", "2026-07-10"]
    assert detail["count"] == pdt.compute_day_trades_used_5d(acts, as_of_et)


def test_detail_two_symbols_same_date_count_is_two_dates_is_one(pdt):
    """Regression: an earlier draft deduped 'dates' and used len(dates) as the count,
    which collapsed 2 distinct-symbol day-trades on the SAME date down to 1 -- caught
    by test_pdt_tracker_2026_07_06.py::test_todays_real_shape_two_symbols_is_two_day_trades
    when this module's own refactor first shipped. count must stay per-(symbol,date)
    pair; dates must stay deduped."""
    as_of_et = datetime(2026, 7, 6, 15, 0)
    acts = [
        _fill("SPY260706C00751000", "buy", "2026-07-06T17:11:36Z"),
        _fill("SPY260706C00751000", "sell", "2026-07-06T17:13:28Z"),
        _fill("SPY260706P00750000", "buy", "2026-07-06T17:36:34Z"),
        _fill("SPY260706P00750000", "sell", "2026-07-06T17:37:28Z"),
    ]
    detail = pdt.compute_day_trades_detail(acts, as_of_et)
    assert detail["count"] == 2, "two distinct symbols day-traded same date = 2 day trades"
    assert detail["dates"] == ["2026-07-06"], "but only one distinct DATE"


def test_detail_empty_activities(pdt):
    as_of_et = datetime(2026, 7, 6, 15, 0)
    detail = pdt.compute_day_trades_detail([], as_of_et)
    assert detail == {"count": 0, "dates": []}


# ---- next_rolloff_date ----

def test_rolloff_none_when_no_qualifying_dates(pdt):
    assert pdt.next_rolloff_date([], datetime(2026, 7, 14, 11, 0)) is None


def test_rolloff_is_earliest_date_plus_six_business_days(pdt):
    # 2026-07-09 is a Thursday. +6 business days: 07-10(Fri,1) -> 07-13(Mon,2) ->
    # 07-14(Tue,3) -> 07-15(Wed,4) -> 07-16(Thu,5) -> 07-17(Fri,6).
    result = pdt.next_rolloff_date(["2026-07-09"], datetime(2026, 7, 13, 11, 0))
    assert result == "2026-07-17"


def test_rolloff_uses_the_earliest_of_multiple_dates(pdt):
    result = pdt.next_rolloff_date(["2026-07-10", "2026-07-09"], datetime(2026, 7, 13, 11, 0))
    assert result == "2026-07-17", "must use the EARLIEST date, not list order or the latest"


def test_rolloff_result_is_actually_excluded_from_the_window(pdt):
    """BITE: verify the claimed rolloff date genuinely drops the source date out of
    trailing_business_days' window, and the day BEFORE it still includes it."""
    d = "2026-07-09"
    rolloff = pdt.next_rolloff_date([d], datetime(2026, 7, 13, 11, 0))
    rolloff_dt = datetime.fromisoformat(rolloff)
    window_on_rolloff = pdt.trailing_business_days(rolloff_dt, 5)
    window_on_rolloff.add(rolloff_dt.date())
    assert date.fromisoformat(d) not in window_on_rolloff, "must be excluded ON the rolloff date"

    day_before = rolloff_dt - __import__("datetime").timedelta(days=1)
    while day_before.weekday() >= 5:
        day_before -= __import__("datetime").timedelta(days=1)
    window_before = pdt.trailing_business_days(day_before, 5)
    window_before.add(day_before.date())
    assert date.fromisoformat(d) in window_before, "must still be included the business day before"


# ---- fetch_day_trades_detail: honest UNKNOWN, never a fabricated 0 ----

def test_fetch_detail_propagates_network_error_as_unknown(pdt, monkeypatch):
    def _boom(*a, **k):
        raise OSError("Connection refused")
    monkeypatch.setattr(pdt.urllib.request, "urlopen", _boom)
    creds = {"base_url": "https://paper-api.alpaca.markets", "key": "x", "secret": "y"}
    result = pdt.fetch_day_trades_detail(creds)
    assert result["ok"] is False
    assert "count" not in result, "an error must NEVER carry a fabricated count"
    assert "OSError" in result["error"]


def test_fetch_detail_propagates_malformed_response_as_unknown(pdt, monkeypatch):
    class _FakeResp:
        def read(self):
            return b"not json"
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(pdt.urllib.request, "urlopen", lambda *a, **k: _FakeResp())
    creds = {"base_url": "https://paper-api.alpaca.markets", "key": "x", "secret": "y"}
    result = pdt.fetch_day_trades_detail(creds)
    assert result["ok"] is False


def test_fetch_detail_happy_path_computes_count_and_rolloff(pdt, monkeypatch):
    page = [
        _fill("SPY260709C1", "buy", "2026-07-09T17:00:00Z", fill_id="a"),
        _fill("SPY260709C1", "sell", "2026-07-09T17:30:00Z", fill_id="b"),
    ]

    class _FakeResp:
        def __init__(self, payload):
            self._payload = payload
        def read(self):
            import json as _j
            return _j.dumps(self._payload).encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    calls = {"n": 0}

    def _fake_urlopen(req, timeout=10):
        calls["n"] += 1
        return _FakeResp(page if calls["n"] == 1 else [])

    monkeypatch.setattr(pdt.urllib.request, "urlopen", _fake_urlopen)
    creds = {"base_url": "https://paper-api.alpaca.markets", "key": "x", "secret": "y"}
    as_of_utc = datetime(2026, 7, 13, 19, 0, tzinfo=timezone.utc)
    result = pdt.fetch_day_trades_detail(creds, as_of_utc)
    assert result["ok"] is True
    assert result["count"] == 1
    assert result["dates"] == ["2026-07-09"]
    assert result["rolloff_date"] == "2026-07-17"


# ---- fetch_day_trades_used_5d (the TRADING gate) is untouched by this extension ----

def test_trading_gate_still_fails_open_to_zero(pdt, monkeypatch):
    def _boom(*a, **k):
        raise OSError("Connection refused")
    monkeypatch.setattr(pdt.urllib.request, "urlopen", _boom)
    creds = {"base_url": "https://paper-api.alpaca.markets", "key": "x", "secret": "y"}
    assert pdt.fetch_day_trades_used_5d(creds) == 0, \
        "the risk_gate-consumed trading path must keep its fail-open-to-0 contract"

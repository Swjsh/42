"""Tests for backtest/tools/fetch_sip_tape.py — signing logic + pagination/caching.

NEVER hits the network: all Alpaca HTTP calls are mocked via monkeypatching
`fetch_sip_tape._request_with_retry`. Credential resolution is also stubbed so
these tests do not depend on `.mcp.json` contents.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

_HERE = Path(__file__).resolve().parent
_TOOLS_DIR = _HERE.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import fetch_sip_tape as fst  # noqa: E402


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    """Redirect the on-disk cache root to a tmp dir so tests never touch the
    real backtest/data/sip_tape/ cache and never leak state between tests."""
    cache_root = tmp_path / "sip_tape"
    monkeypatch.setattr(fst, "CACHE_ROOT", cache_root)
    return cache_root


@pytest.fixture(autouse=True)
def _stub_creds(monkeypatch):
    monkeypatch.setattr(
        fst,
        "resolve_alpaca_creds",
        lambda server="alpaca": fst.__dict__.setdefault(
            "_FakeCreds", type("C", (), {"key": "FAKEKEY", "secret": "FAKESECRET"})
        )(),
    )


def _trade(t: str, p: float, s: int, i: int = 1) -> dict:
    return {"t": t, "p": p, "s": s, "x": "V", "c": ["@"], "i": i, "z": "C"}


def _quote(t: str, bp: float, bs: int, ap: float, asz: int) -> dict:
    return {"t": t, "bp": bp, "bs": bs, "ap": ap, "as": asz, "bx": "V", "ax": "V", "c": [], "z": "C"}


# ---------------------------------------------------------------------------
# timestamp precision
# ---------------------------------------------------------------------------


def test_parse_ns_timestamp_preserves_nanosecond_precision():
    ns = fst._parse_ns_timestamp("2026-09-04T14:30:00.123456789Z")
    # exact epoch-ns value; a float round-trip would lose the low digits
    expected = int(
        datetime(2026, 9, 4, 14, 30, 0, tzinfo=timezone.utc).timestamp()
    ) * 1_000_000_000 + 123456789
    assert ns == expected


def test_parse_ns_timestamp_handles_no_fraction():
    ns = fst._parse_ns_timestamp("2026-09-04T14:30:00Z")
    expected = int(datetime(2026, 9, 4, 14, 30, 0, tzinfo=timezone.utc).timestamp()) * 1_000_000_000
    assert ns == expected


# ---------------------------------------------------------------------------
# pagination + caching (mocked HTTP)
# ---------------------------------------------------------------------------


def test_fetch_tape_follows_pagination_to_completion(monkeypatch):
    pages = [
        {"trades": [_trade("2026-09-04T14:30:00.000000001Z", 500.0, 10, i=1)],
         "next_page_token": "tok1"},
        {"trades": [_trade("2026-09-04T14:30:00.000000002Z", 500.1, 20, i=2)],
         "next_page_token": None},
    ]
    calls = []

    def fake_request(url, params, headers):
        calls.append(dict(params))
        return pages[len(calls) - 1]

    monkeypatch.setattr(fst, "_request_with_retry", fake_request)

    start = datetime(2026, 9, 4, 14, 30, tzinfo=timezone.utc)
    end = datetime(2026, 9, 4, 14, 35, tzinfo=timezone.utc)
    df = fst.fetch_trades("SPY", start, end)

    assert len(calls) == 2
    assert "page_token" not in calls[0]
    assert calls[1]["page_token"] == "tok1"
    assert len(df) == 2
    assert list(df["size"]) == [10, 20]


def test_fetch_tape_raises_loudly_on_truncated_pagination(monkeypatch):
    """If next_page_token never goes away before the request cap, raise instead
    of silently returning a partial tape."""
    monkeypatch.setattr(fst, "MAX_REQUESTS_PER_CALL", 3)

    def fake_request(url, params, headers):
        return {"trades": [_trade("2026-09-04T14:30:00Z", 500.0, 1)], "next_page_token": "more"}

    monkeypatch.setattr(fst, "_request_with_retry", fake_request)

    start = datetime(2026, 9, 4, 14, 30, tzinfo=timezone.utc)
    end = datetime(2026, 9, 4, 14, 35, tzinfo=timezone.utc)
    with pytest.raises(fst.TapeFetchError, match="MAX_REQUESTS_PER_CALL"):
        fst.fetch_trades("SPY", start, end)


def test_fetch_tape_second_call_served_from_cache_zero_api_calls(monkeypatch):
    call_count = {"n": 0}

    def fake_request(url, params, headers):
        call_count["n"] += 1
        return {"trades": [_trade("2026-09-04T14:30:00Z", 500.0, 5)], "next_page_token": None}

    monkeypatch.setattr(fst, "_request_with_retry", fake_request)

    start = datetime(2026, 9, 4, 14, 30, tzinfo=timezone.utc)
    end = datetime(2026, 9, 4, 14, 35, tzinfo=timezone.utc)

    df1 = fst.fetch_trades("SPY", start, end)
    assert call_count["n"] == 1

    df2 = fst.fetch_trades("SPY", start, end)
    assert call_count["n"] == 1  # no new API calls
    pd.testing.assert_frame_equal(df1.reset_index(drop=True), df2.reset_index(drop=True))


def test_fetch_tape_cache_path_uses_parquet_when_pyarrow_available():
    if not fst._HAVE_PYARROW:
        pytest.skip("pyarrow not installed in this environment")
    start = datetime(2026, 9, 4, 14, 30, tzinfo=timezone.utc)
    end = datetime(2026, 9, 4, 14, 35, tzinfo=timezone.utc)
    path = fst._cache_path("SPY", "trades", "sip", start, end)
    assert path.suffix == ".parquet"


def test_different_windows_use_different_cache_keys(monkeypatch):
    call_count = {"n": 0}

    def fake_request(url, params, headers):
        call_count["n"] += 1
        return {"trades": [_trade("2026-09-04T14:30:00Z", 500.0, 5)], "next_page_token": None}

    monkeypatch.setattr(fst, "_request_with_retry", fake_request)

    fst.fetch_trades(
        "SPY",
        datetime(2026, 9, 4, 14, 30, tzinfo=timezone.utc),
        datetime(2026, 9, 4, 14, 35, tzinfo=timezone.utc),
    )
    fst.fetch_trades(
        "SPY",
        datetime(2026, 9, 4, 15, 30, tzinfo=timezone.utc),
        datetime(2026, 9, 4, 15, 35, tzinfo=timezone.utc),
    )
    assert call_count["n"] == 2  # distinct windows are not cache hits for each other


def test_retryable_status_retries_then_succeeds(monkeypatch):
    """_request_with_retry itself: 429 then 200 should succeed without raising."""
    responses = []

    class FakeResp:
        def __init__(self, status_code, payload=None, text=""):
            self.status_code = status_code
            self._payload = payload or {}
            self.text = text

        def json(self):
            return self._payload

    call_count = {"n": 0}

    def fake_get(url, params, headers, timeout):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return FakeResp(429, text="rate limited")
        return FakeResp(200, payload={"trades": [], "next_page_token": None})

    monkeypatch.setattr(fst.requests, "get", fake_get)
    monkeypatch.setattr(fst.time, "sleep", lambda s: None)

    body = fst._request_with_retry("http://x", {}, {})
    assert body == {"trades": [], "next_page_token": None}
    assert call_count["n"] == 2


def test_non_retryable_status_raises_immediately(monkeypatch):
    class FakeResp:
        status_code = 401
        text = "unauthorized"

        def json(self):
            return {}

    monkeypatch.setattr(fst.requests, "get", lambda *a, **k: FakeResp())
    with pytest.raises(fst.TapeFetchError, match="401"):
        fst._request_with_retry("http://x", {}, {})


# ---------------------------------------------------------------------------
# Lee-Ready signing
# ---------------------------------------------------------------------------


def test_sign_trades_price_above_mid_is_buyer_initiated():
    trades = fst._trades_to_frame([_trade("2026-09-04T14:30:00.5Z", 500.10, 10)])
    quotes = fst._quotes_to_frame([_quote("2026-09-04T14:30:00.0Z", 499.95, 1, 500.05, 1)])
    signed = fst.sign_trades(trades, quotes)
    assert signed["sign"].iloc[0] == 1
    assert signed["signed_size"].iloc[0] == 10


def test_sign_trades_price_below_mid_is_seller_initiated():
    trades = fst._trades_to_frame([_trade("2026-09-04T14:30:00.5Z", 499.90, 10)])
    quotes = fst._quotes_to_frame([_quote("2026-09-04T14:30:00.0Z", 499.95, 1, 500.05, 1)])
    signed = fst.sign_trades(trades, quotes)
    assert signed["sign"].iloc[0] == -1
    assert signed["signed_size"].iloc[0] == -10


def test_sign_trades_uses_quote_at_or_before_trade_never_future_quote():
    trades = fst._trades_to_frame([_trade("2026-09-04T14:30:00.5Z", 500.00, 10)])
    quotes = fst._quotes_to_frame(
        [
            _quote("2026-09-04T14:30:00.0Z", 499.90, 1, 500.10, 1),  # mid=500.00, at/before -> used
            _quote("2026-09-04T14:31:00.0Z", 499.00, 1, 499.10, 1),  # after trade -> must be ignored
        ]
    )
    signed = fst.sign_trades(trades, quotes)
    assert signed["mid"].iloc[0] == pytest.approx(500.00)


def test_sign_trades_midpoint_tie_falls_back_to_tick_rule_uptick():
    trades = fst._trades_to_frame(
        [
            _trade("2026-09-04T14:30:00.0Z", 499.00, 10, i=1),  # establishes prev_price, no quote
            _trade("2026-09-04T14:30:01.0Z", 500.00, 10, i=2),  # ties the mid -> tick rule: uptick
        ]
    )
    quotes = fst._quotes_to_frame([_quote("2026-09-04T14:29:59.0Z", 499.95, 1, 500.05, 1)])
    signed = fst.sign_trades(trades, quotes)
    assert signed["sign"].iloc[1] == 1  # 500.00 == mid, but price rose vs prev trade -> uptick


def test_sign_trades_midpoint_tie_falls_back_to_tick_rule_downtick():
    trades = fst._trades_to_frame(
        [
            _trade("2026-09-04T14:30:00.0Z", 501.00, 10, i=1),
            _trade("2026-09-04T14:30:01.0Z", 500.00, 10, i=2),  # ties mid, price fell -> downtick
        ]
    )
    quotes = fst._quotes_to_frame([_quote("2026-09-04T14:29:59.0Z", 499.95, 1, 500.05, 1)])
    signed = fst.sign_trades(trades, quotes)
    assert signed["sign"].iloc[1] == -1


def test_sign_trades_zero_tick_carries_forward_previous_sign():
    trades = fst._trades_to_frame(
        [
            _trade("2026-09-04T14:30:00.0Z", 501.00, 10, i=1),  # ties mid at first (no prior) -> tick rule -> 0 (no prev price)
            _trade("2026-09-04T14:30:01.0Z", 502.00, 10, i=2),  # above mid explicitly -> +1
            _trade("2026-09-04T14:30:02.0Z", 500.00, 10, i=3),  # ties mid, same price as... use zero tick
        ]
    )
    quotes = fst._quotes_to_frame([_quote("2026-09-04T14:29:59.0Z", 499.95, 1, 500.05, 1)])
    signed = fst.sign_trades(trades, quotes)
    # trade 2 is unambiguously +1 (502 > mid 500)
    assert signed["sign"].iloc[1] == 1


def test_sign_trades_no_prevailing_quote_and_first_trade_is_unsigned_zero():
    trades = fst._trades_to_frame([_trade("2026-09-04T14:30:00.0Z", 500.00, 10)])
    quotes = fst._quotes_to_frame([])
    signed = fst.sign_trades(trades, quotes)
    assert signed["sign"].iloc[0] == 0
    assert signed["signed_size"].iloc[0] == 0


def test_sign_trades_empty_trades_returns_empty_frame_with_expected_columns():
    trades = fst._trades_to_frame([])
    quotes = fst._quotes_to_frame([])
    signed = fst.sign_trades(trades, quotes)
    assert signed.empty
    assert {"mid", "sign", "signed_size"}.issubset(signed.columns)


def test_sign_trades_does_not_mutate_input_frames():
    trades = fst._trades_to_frame([_trade("2026-09-04T14:30:00.5Z", 500.10, 10)])
    quotes = fst._quotes_to_frame([_quote("2026-09-04T14:30:00.0Z", 499.95, 1, 500.05, 1)])
    trades_cols_before = list(trades.columns)
    fst.sign_trades(trades, quotes)
    assert list(trades.columns) == trades_cols_before  # unchanged (immutability convention)


def test_sign_trades_signed_size_matches_sign_times_size():
    trades = fst._trades_to_frame(
        [
            _trade("2026-09-04T14:30:00.5Z", 500.10, 7, i=1),
            _trade("2026-09-04T14:30:01.5Z", 499.90, 3, i=2),
        ]
    )
    quotes = fst._quotes_to_frame([_quote("2026-09-04T14:30:00.0Z", 499.95, 1, 500.05, 1)])
    signed = fst.sign_trades(trades, quotes)
    assert (signed["signed_size"] == signed["sign"] * signed["size"]).all()

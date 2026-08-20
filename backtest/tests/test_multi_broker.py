"""Tests for multi/lib/broker.py and multi/lib/positions.py -- the multi-symbol lane's
broker/execution layer.

SCOPE. This lane's account (PA38EG1JTFBT) is SHARED with the live crypto twin
(setup/scripts/crypto_twin_broker.py, BTC/USD every ~60s, ARMED right now). The single most
important thing these tests prove is that this module cannot see, count, or close that
position -- see test_crypto_safety_* below, which is the RED-PROOF target for this file.

No network calls anywhere in this file: every test either exercises pure logic (the OCC-shape
predicate, construction-time ValueErrors) or monkeypatches broker._request, broker's module-
level functions, or injects a `params` dict directly (broker.py's submission functions accept
`params=` precisely so tests never need to touch a real params.json or monkeypatch file I/O).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from multi.lib import broker  # noqa: E402
from multi.lib import creds as creds_mod  # noqa: E402
from multi.lib import positions as positions_mod  # noqa: E402


def _creds() -> creds_mod.MultiCreds:
    return creds_mod.MultiCreds(
        key="TESTKEY", secret="TESTSECRET", base_url="https://paper-api.alpaca.markets",
        account_number="PA38EG1JTFBT", source="test-fixture",
    )


# --- OCC-shape predicate: 3-char AND 4-char roots (the original's fixed-offset bug) --------
@pytest.mark.parametrize("symbol,expected_root", [
    ("SPY260622C00745000", "SPY"),
    ("QQQ260622P00380000", "QQQ"),
    ("GLD260622C00180000", "GLD"),
    ("NVDA260622C00500000", "NVDA"),
    ("AAPL260622C00190000", "AAPL"),
    ("TSLA260622P00250000", "TSLA"),
])
def test_is_occ_option_symbol_true_for_3_and_4_char_roots(symbol, expected_root):
    assert positions_mod.is_occ_option_symbol(symbol) is True
    assert positions_mod.occ_root(symbol) == expected_root


def test_occ_root_is_root_length_agnostic_not_a_fixed_offset():
    """The original fleet_broker check (`startswith("SPY") and len(...) >= 15`) implicitly
    assumes callers know the root length up front. A naive symbol[:3] fixed-offset rewrite
    would mis-split a 4-char root (NVDA260622C00500000[:3] == "NVD", wrong). occ_root() must
    get this right because it derives the split point from the FIXED-WIDTH tail, not the
    front."""
    assert positions_mod.occ_root("NVDA260622C00500000") == "NVDA"
    assert positions_mod.occ_root("NVDA260622C00500000") != "NVD"
    assert positions_mod.occ_root("SPY260622C00745000") == "SPY"


@pytest.mark.parametrize("symbol", [
    "BTCUSD", "BTC/USD", "ETHUSD", "", "SPY", "SPY260622",
    "SPY260622X00745000",  # invalid right (X, not C/P)
    "SPY26062C00745000",   # 5-digit date, not 6
    "SPY260622C0074500",   # 7-digit strike, not 8
    "spy260622c00745000",  # lowercase -- OCC symbols are uppercase
])
def test_is_occ_option_symbol_false_for_non_option_shapes(symbol):
    assert positions_mod.is_occ_option_symbol(symbol) is False
    assert positions_mod.occ_root(symbol) is None


# --- crypto safety: the RED-PROOF target -----------------------------------------------
_BTC_POSITION = {"symbol": "BTCUSD", "asset_class": "crypto", "qty": "2.5"}
# qty is deliberately >= 1 so it survives close_all_equity_options's `abs(int(float(qty)))`
# truncation -- a dust qty like 0.002 would incidentally skip BTCUSD via the qty<1 guard even
# if the OCC-shape filter were broken, which would make the crypto-safety proof meaningless.
_OPT_1 = {"symbol": "SPY260622C00745000", "asset_class": "us_option", "qty": "2"}
_OPT_2 = {"symbol": "NVDA260622C00500000", "asset_class": "us_option", "qty": "3"}
_MIXED_POSITIONS = [_BTC_POSITION, _OPT_1, _OPT_2]


def test_crypto_safety_equity_option_positions_excludes_btc_and_keeps_both_options():
    """positions.py level: a BTCUSD position mixed with two real OCC option positions (one
    3-char root, one 4-char root) -- the filter must return EXACTLY the two options."""
    out = positions_mod.equity_option_positions(_MIXED_POSITIONS)
    symbols = {p["symbol"] for p in out}
    assert symbols == {"SPY260622C00745000", "NVDA260622C00500000"}
    assert "BTCUSD" not in symbols
    assert len(out) == 2


def test_crypto_safety_close_all_equity_options_never_targets_btc(monkeypatch):
    """RED-PROOF TARGET. broker.py level, end to end: given a positions fixture containing
    BTCUSD alongside two OCC option positions, close_all_equity_options(armed=True) must
    submit market-sell orders for ONLY the two options and never construct or send anything
    referencing BTCUSD. This is the guard preventing this lane from liquidating the live
    crypto twin's position."""
    monkeypatch.setattr(broker, "get_positions", lambda creds: list(_MIXED_POSITIONS))

    submitted_symbols = []

    def fake_request(creds, endpoint, method="GET", data=None, timeout=15):
        if method == "POST" and endpoint == "orders":
            submitted_symbols.append(data["symbol"])
            return {"id": f"ord-{data['symbol']}", "status": "accepted"}
        raise AssertionError(f"unexpected _request call: {method} {endpoint}")

    monkeypatch.setattr(broker, "_request", fake_request)

    result = broker.close_all_equity_options(
        _creds(), armed=True, params={"shadow_only": False},
    )

    assert "BTCUSD" not in submitted_symbols
    assert set(submitted_symbols) == {"SPY260622C00745000", "NVDA260622C00500000"}
    assert set(result["closed"]) == {"SPY260622C00745000", "NVDA260622C00500000"}
    assert result["errors"] == []


def test_crypto_safety_close_all_shadow_preview_never_lists_btc(monkeypatch):
    """Even the armed=False shadow preview (would_close) must never mention BTCUSD -- the
    candidate list itself is already OCC-filtered before the armed check runs."""
    monkeypatch.setattr(broker, "get_positions", lambda creds: list(_MIXED_POSITIONS))
    result = broker.close_all_equity_options(_creds(), armed=False)
    assert result["_shadow"] is True
    assert "BTCUSD" not in result["would_close"]
    assert set(result["would_close"]) == {"SPY260622C00745000", "NVDA260622C00500000"}


def test_crypto_safety_market_sell_refuses_btc_symbol_directly():
    """Second independent layer: market_sell() itself refuses a non-OCC symbol even if some
    future caller passed BTCUSD directly (bypassing equity_option_positions entirely)."""
    with pytest.raises(ValueError, match="non-OCC-shaped"):
        broker.market_sell(_creds(), symbol="BTCUSD", qty=1, armed=True, params={"shadow_only": False})


def test_crypto_safety_get_position_qty_refuses_btc_symbol():
    with pytest.raises(ValueError, match="non-OCC-shaped"):
        broker.get_position_qty(_creds(), "BTCUSD")


# --- shadow-phase interlock: submission raises while shadow_only is true ------------------
def test_place_bracket_shadow_preview_when_not_armed():
    """armed=False (default): order is constructed but no network call is made."""
    order = broker.place_bracket(
        _creds(), symbol="SPY260622C00745000", qty=2, limit_price=1.50,
        take_profit_price=2.25, stop_price=0.75,
    )
    assert order["_shadow"] is True
    assert order["armed"] is False
    assert order["would_submit"]["symbol"] == "SPY260622C00745000"
    assert order["would_submit"]["order_class"] == "bracket"


def test_place_bracket_raises_shadow_mode_error_when_armed_and_shadow_only_true(monkeypatch):
    monkeypatch.setattr(
        broker, "_request",
        lambda *a, **k: pytest.fail("must never reach the network while shadow_only=true"),
    )
    with pytest.raises(broker.ShadowModeError, match="shadow_only=true"):
        broker.place_bracket(
            _creds(), symbol="SPY260622C00745000", qty=2, limit_price=1.50,
            take_profit_price=2.25, stop_price=0.75,
            armed=True, params={"shadow_only": True},
        )


def test_market_sell_raises_shadow_mode_error_when_armed_and_shadow_only_true(monkeypatch):
    monkeypatch.setattr(
        broker, "_request",
        lambda *a, **k: pytest.fail("must never reach the network while shadow_only=true"),
    )
    with pytest.raises(broker.ShadowModeError):
        broker.market_sell(
            _creds(), symbol="SPY260622C00745000", qty=1,
            armed=True, params={"shadow_only": True},
        )


def test_place_bracket_submits_when_armed_and_shadow_only_false(monkeypatch):
    """The interlock only blocks while shadow_only is true -- once it's explicitly flipped
    false AND armed=True is passed, the order really does reach _request."""
    captured = {}

    def fake_request(creds, endpoint, method="GET", data=None, timeout=15):
        captured["endpoint"] = endpoint
        captured["method"] = method
        captured["data"] = data
        return {"id": "ord-1", "status": "accepted"}

    monkeypatch.setattr(broker, "_request", fake_request)
    res = broker.place_bracket(
        _creds(), symbol="SPY260622C00745000", qty=2, limit_price=1.50,
        take_profit_price=2.25, stop_price=0.75,
        armed=True, params={"shadow_only": False},
    )
    assert res["status"] == "accepted"
    assert captured["method"] == "POST"
    assert captured["data"]["order_class"] == "bracket"


def test_place_bracket_oto_fallback_on_bracket_rejection(monkeypatch):
    """Parity with fleet_broker.place_bracket: a rejected bracket retries as an oto (no TP
    leg) rather than failing outright."""
    calls = []

    def fake_request(creds, endpoint, method="GET", data=None, timeout=15):
        calls.append(data.get("order_class") if data else None)
        if data and data.get("order_class") == "bracket":
            return {"_error": "complex orders not supported for options trading", "_status": 422}
        return {"id": "ord-oto", "status": "accepted"}

    monkeypatch.setattr(broker, "_request", fake_request)
    res = broker.place_bracket(
        _creds(), symbol="SPY260622C00745000", qty=1, limit_price=1.0,
        take_profit_price=1.5, stop_price=0.5, armed=True, params={"shadow_only": False},
    )
    assert res.get("_oto_fallback") is True
    assert calls == ["bracket", "oto"]


# --- construction-time guards (always enforced, regardless of armed) ----------------------
def test_place_bracket_refuses_non_occ_symbol():
    with pytest.raises(ValueError, match="non-OCC-shaped"):
        broker.place_bracket(
            _creds(), symbol="NOTANOPTION", qty=1, limit_price=1.0,
            take_profit_price=1.5, stop_price=0.5,
        )


def test_place_bracket_refuses_null_stop():
    with pytest.raises(ValueError, match="naked long"):
        broker.place_bracket(
            _creds(), symbol="SPY260622C00745000", qty=1, limit_price=1.0,
            take_profit_price=1.5, stop_price=0,
        )


def test_market_sell_refuses_non_occ_symbol():
    with pytest.raises(ValueError, match="non-OCC-shaped"):
        broker.market_sell(_creds(), symbol="NOTANOPTION", qty=1, armed=False)


# --- fail-loud on API errors: no silent empty-list "flat" reads ---------------------------
def test_get_positions_raises_broker_api_error_on_simulated_http_failure(monkeypatch):
    monkeypatch.setattr(
        broker, "_request",
        lambda *a, **k: {"_error": "HTTP Error 500: Internal Server Error", "_status": 500},
    )
    with pytest.raises(broker.BrokerAPIError, match="500"):
        broker.get_positions(_creds())


def test_get_orders_raises_broker_api_error_on_simulated_http_failure(monkeypatch):
    monkeypatch.setattr(
        broker, "_request",
        lambda *a, **k: {"_error": "Connection timed out"},
    )
    with pytest.raises(broker.BrokerAPIError, match="Connection timed out"):
        broker.get_orders(_creds())


def test_equity_option_positions_propagates_broker_api_error_never_reads_as_flat(monkeypatch):
    """The crypto-safety read itself must fail loud too -- a broken /v2/positions read must
    never be silently reported as 'zero option positions' (which would look identical to a
    correctly flat/closed lane)."""
    monkeypatch.setattr(
        broker, "_request",
        lambda *a, **k: {"_error": "boom", "_status": 503},
    )
    with pytest.raises(broker.BrokerAPIError):
        broker.equity_option_positions(_creds())


def test_get_account_raises_broker_api_error_on_failure(monkeypatch):
    monkeypatch.setattr(broker, "_request", lambda *a, **k: {"_error": "boom"})
    with pytest.raises(broker.BrokerAPIError):
        broker.get_account(_creds())


# --- retry tolerance for the documented list-lag (flat-check must not fail on one blip) ---
def test_is_flat_equity_options_retries_transient_failure_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def flaky_get_positions(creds):
        calls["n"] += 1
        if calls["n"] < 2:
            raise broker.BrokerAPIError("transient")
        return []

    monkeypatch.setattr(broker, "get_positions", flaky_get_positions)
    assert broker.is_flat_equity_options(_creds(), retries=2, retry_sleep=0) is True
    assert calls["n"] == 2


def test_is_flat_equity_options_reraises_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr(
        broker, "get_positions",
        lambda creds: (_ for _ in ()).throw(broker.BrokerAPIError("still broken")),
    )
    with pytest.raises(broker.BrokerAPIError, match="still broken"):
        broker.is_flat_equity_options(_creds(), retries=2, retry_sleep=0)


def test_is_flat_equity_options_true_on_clean_empty_read_no_retry_needed(monkeypatch):
    calls = {"n": 0}

    def clean_get_positions(creds):
        calls["n"] += 1
        return []

    monkeypatch.setattr(broker, "get_positions", clean_get_positions)
    assert broker.is_flat_equity_options(_creds(), retries=2, retry_sleep=0) is True
    assert calls["n"] == 1  # a clean read never retries


# --- universe_roots: the optional params-driven allowlist narrowing -----------------------
def test_universe_roots_flattens_categories_and_skips_underscore_metadata():
    params = {
        "universe": {
            "_doc": "not a ticker list",
            "index_etf": ["SPY", "QQQ"],
            "mega_tech": ["AAPL", "NVDA"],
        }
    }
    assert broker.universe_roots(params) == {"SPY", "QQQ", "AAPL", "NVDA"}


def test_equity_option_positions_allowed_roots_narrows_universe():
    positions = [_OPT_1, _OPT_2]  # SPY + NVDA
    out = positions_mod.equity_option_positions(positions, allowed_roots=["SPY"])
    assert [p["symbol"] for p in out] == ["SPY260622C00745000"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

"""Tests for setup/scripts/crypto_twin_broker.py -- the crypto REST client itself.

Complements test_crypto_twin_core.py's integration coverage (which mocks this module
entirely) with unit coverage of THIS module's own contracts: creds loading/error paths,
the WATCH-gated order refusal logic (mirrors fleet_broker.place_bracket's safety rails),
and the fractional-qty position read that fleet_broker.get_position_qty cannot provide
(the whole reason this module doesn't just reuse fleet_broker for everything).

No network calls -- every test either exercises pure refusal logic or monkeypatches
crypto_twin_broker's own HTTP-boundary functions (_request / _fb._request).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

import crypto_twin_broker as ctb  # noqa: E402
from _broker_request_stub import broker_list_stub  # shared L294 contract


# --- creds loading ----------------------------------------------------------------------
def test_load_creds_raises_clear_error_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(ctb, "TWIN_SECRETS_PATH", tmp_path / "secrets.json")
    monkeypatch.setattr(ctb, "TWIN_SECRETS_EXAMPLE", tmp_path / "secrets.json.example")
    with pytest.raises(FileNotFoundError, match="secrets.json"):
        ctb.load_creds()


def test_load_creds_reads_twin_account(tmp_path, monkeypatch):
    p = tmp_path / "secrets.json"
    p.write_text(json.dumps({"accounts": {"twin": {"key": "K", "secret": "S",
                                                    "base_url": "https://paper-api.alpaca.markets"}}}))
    monkeypatch.setattr(ctb, "TWIN_SECRETS_PATH", p)
    creds = ctb.load_creds()
    assert creds["twin"] == {"key": "K", "secret": "S", "base_url": "https://paper-api.alpaca.markets"}


def test_get_twin_creds_raises_keyerror_when_no_twin_entry(tmp_path, monkeypatch):
    p = tmp_path / "secrets.json"
    p.write_text(json.dumps({"accounts": {"someone_else": {"key": "K", "secret": "S"}}}))
    monkeypatch.setattr(ctb, "TWIN_SECRETS_PATH", p)
    with pytest.raises(KeyError):
        ctb.get_twin_creds()


# --- sell-qty FLOOR guard (2026-07-15, TWIN-B3 first passive rep) -------------------------
# Caught LIVE: a fee-shaved position of 0.002396399 BTC round()ed UP to 0.0023964 on the
# SELL_ALL -> Alpaca 403 "insufficient balance" -> the exit silently failed. Sells must
# FLOOR to 8dp (never request more than the broker holds); buys keep plain rounding.
def test_sell_qty_floors_never_rounds_up(monkeypatch):
    captured = {}

    def _fake_request(creds, endpoint, method="GET", data=None, timeout=15):

        _lst = broker_list_stub(endpoint, method)

        if _lst is not None:

            return _lst  # collection endpoints must be LIST-shaped
        captured.update(data or {})
        return {"id": "x", "status": "accepted"}
    monkeypatch.setattr(ctb._fb, "_request", _fake_request)
    res = ctb.place_crypto_order({"key": "K", "secret": "S", "base_url": "u"}, side="sell",
                                 qty=0.002396399, live=True)
    assert not res.get("_error")
    assert captured["qty"] == "0.00239639"  # floored -- NOT "0.0023964"


def test_buy_qty_keeps_plain_rounding(monkeypatch):
    captured = {}

    def _fake_request(creds, endpoint, method="GET", data=None, timeout=15):

        _lst = broker_list_stub(endpoint, method)

        if _lst is not None:

            return _lst  # collection endpoints must be LIST-shaped
        captured.update(data or {})
        return {"id": "x", "status": "accepted"}
    monkeypatch.setattr(ctb._fb, "_request", _fake_request)
    ctb.place_crypto_order({"key": "K", "secret": "S", "base_url": "u"}, side="buy",
                           qty=0.0024, live=True)
    assert captured["qty"] == "0.0024"


def test_sell_qty_dust_that_floors_to_zero_is_refused(monkeypatch):
    monkeypatch.setattr(ctb._fb, "_request",
                        lambda *a, **k: pytest.fail("must refuse before any request"))
    res = ctb.place_crypto_order({"key": "K", "secret": "S", "base_url": "u"}, side="sell",
                                 qty=0.000000001, live=True)
    assert res.get("_refused")


# --- crypto-approval check (2026-07-11, added after confirming via Alpaca's docs +live ----
# account reads that crypto shares an account's EXISTING approval state -- see
# https://docs.alpaca.markets/us/docs/crypto-trading-1 -- rather than requiring a dedicated
# account type. A configured-but-unapproved account must fail LOUD and distinctly from a
# missing-account error, or J ends up debugging the wrong problem after creating the account.
def _twin_secrets(tmp_path, monkeypatch):
    p = tmp_path / "secrets.json"
    p.write_text(json.dumps({"accounts": {"twin": {"key": "K", "secret": "S",
                                                    "base_url": "https://paper-api.alpaca.markets"}}}))
    monkeypatch.setattr(ctb, "TWIN_SECRETS_PATH", p)
    return p


def test_get_twin_creds_raises_when_crypto_not_active(tmp_path, monkeypatch):
    _twin_secrets(tmp_path, monkeypatch)
    monkeypatch.setattr(ctb, "get_account", lambda creds: {"crypto_status": "INACTIVE"})
    with pytest.raises(ctb.CryptoNotApprovedError, match="INACTIVE"):
        ctb.get_twin_creds()


def test_get_twin_creds_raises_when_crypto_status_missing(tmp_path, monkeypatch):
    """A malformed/unexpected account payload (no crypto_status key at all) must fail
    the SAME way as an explicit INACTIVE -- never silently treated as approved."""
    _twin_secrets(tmp_path, monkeypatch)
    monkeypatch.setattr(ctb, "get_account", lambda creds: {})
    with pytest.raises(ctb.CryptoNotApprovedError):
        ctb.get_twin_creds()


def test_get_twin_creds_succeeds_when_crypto_active(tmp_path, monkeypatch):
    _twin_secrets(tmp_path, monkeypatch)
    monkeypatch.setattr(ctb, "get_account", lambda creds: {"crypto_status": "ACTIVE"})
    creds = ctb.get_twin_creds()
    assert creds["key"] == "K"


def test_get_twin_creds_skips_network_call_when_verify_disabled(tmp_path, monkeypatch):
    """verify_crypto_status=False must never call get_account -- the escape hatch for
    contexts that cannot make a network call (e.g. a pure unit test elsewhere)."""
    _twin_secrets(tmp_path, monkeypatch)
    def _boom(creds):
        raise AssertionError("get_account must not be called when verify_crypto_status=False")
    monkeypatch.setattr(ctb, "get_account", _boom)
    creds = ctb.get_twin_creds(verify_crypto_status=False)
    assert creds["key"] == "K"


def test_best_effort_market_data_creds_falls_back_to_mcp_json(tmp_path, monkeypatch):
    missing = tmp_path / "secrets.json"
    monkeypatch.setattr(ctb, "TWIN_SECRETS_PATH", missing)
    mcp = tmp_path / ".mcp.json"
    mcp.write_text(json.dumps({"mcpServers": {"alpaca": {"env": {
        "ALPACA_API_KEY": "AK", "ALPACA_SECRET_KEY": "AS"}}}}))
    monkeypatch.setattr(ctb, "MCP_JSON", mcp)
    creds = ctb._best_effort_market_data_creds()
    assert creds == {"key": "AK", "secret": "AS", "base_url": "https://paper-api.alpaca.markets"}


def test_best_effort_market_data_creds_none_when_nothing_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(ctb, "TWIN_SECRETS_PATH", tmp_path / "secrets.json")
    monkeypatch.setattr(ctb, "MCP_JSON", tmp_path / "nope.json")
    assert ctb._best_effort_market_data_creds() is None


# --- order refusal logic (WATCH-gated, mirrors fleet_broker.place_bracket) --------------
_CREDS = {"key": "k", "secret": "s", "base_url": "https://paper-api.alpaca.markets"}


def test_place_crypto_order_refuses_without_live():
    res = ctb.place_crypto_order(_CREDS, side="buy", notional=200.0, live=False)
    assert res == {"_skipped": "live flag is False -- place_crypto_order refused (WATCH mode)"}


def test_place_crypto_order_refuses_invalid_side():
    res = ctb.place_crypto_order(_CREDS, side="sideways", notional=200.0, live=True)
    assert "_refused" in res


def test_place_crypto_order_refuses_both_notional_and_qty():
    res = ctb.place_crypto_order(_CREDS, side="buy", notional=200.0, qty=0.01, live=True)
    assert "_refused" in res


def test_place_crypto_order_refuses_neither_notional_nor_qty():
    res = ctb.place_crypto_order(_CREDS, side="buy", live=True)
    assert "_refused" in res


def test_place_crypto_order_uses_gtc_time_in_force(monkeypatch):
    """Crypto rejects time_in_force="day" (no trading-day boundary) -- must always be gtc."""
    captured = {}

    def fake_request(creds, endpoint, method="GET", data=None, timeout=15):

        _lst = broker_list_stub(endpoint, method)

        if _lst is not None:

            return _lst  # collection endpoints must be LIST-shaped
        captured["data"] = data
        return {"id": "o1", "status": "accepted"}

    monkeypatch.setattr(ctb._fb, "_request", fake_request)
    ctb.place_crypto_order(_CREDS, side="buy", notional=200.0, live=True)
    assert captured["data"]["time_in_force"] == "gtc"
    assert captured["data"]["notional"] == "200.0"


def test_market_sell_crypto_refuses_without_live():
    res = ctb.market_sell_crypto(_CREDS, symbol="BTC/USD", qty=0.001, live=False)
    assert res.get("_skipped")


def test_close_all_crypto_noop_when_already_flat(monkeypatch):
    monkeypatch.setattr(ctb, "get_crypto_position_qty", lambda creds, symbol=ctb.CRYPTO_SYMBOL_DEFAULT: 0.0)
    res = ctb.close_all_crypto(_CREDS, live=True)
    assert res.get("_skipped") == "already flat"


# --- fractional qty (the reason this module can't reuse fleet_broker.get_position_qty) --
def test_get_crypto_position_qty_preserves_fraction(monkeypatch):
    def fake_get_positions(creds):
        return [{"symbol": "BTC/USD", "qty": "0.00312500"}]
    monkeypatch.setattr(ctb, "get_positions", fake_get_positions)
    qty = ctb.get_crypto_position_qty(_CREDS, "BTC/USD")
    assert qty == pytest.approx(0.003125)
    assert qty != 0  # the exact bug fleet_broker.get_position_qty's int(float(...)) would introduce


def test_get_crypto_position_qty_zero_when_flat(monkeypatch):
    monkeypatch.setattr(ctb, "get_positions", lambda creds: [])
    assert ctb.get_crypto_position_qty(_CREDS, "BTC/USD") == 0.0


# --- generic REST plumbing really is reused verbatim from fleet_broker ------------------
def test_reused_functions_are_the_exact_fleet_broker_objects():
    import fleet_broker as fb
    assert ctb.get_account is fb.get_account
    assert ctb.get_positions is fb.get_positions
    assert ctb.get_order is fb.get_order
    assert ctb.poll_fill is fb.poll_fill
    assert ctb.cancel_order is fb.cancel_order


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

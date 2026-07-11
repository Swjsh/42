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

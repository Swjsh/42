"""Guard: the fleet live order path must place the options entry SIMPLE-FIRST.

HISTORY:
  * 2026-06-28 MONEY-PATH FIX: Alpaca rejects BOTH bracket and oto for options (error
    42210000). _place_live gained place_bracket(simple_fallback=True) so the third
    attempt was a plain limit -- but that ladder still ate 2 GUARANTEED 422s
    (bracket_err + oto_err) on every single entry.
  * FIX2 (2026-07-01): _place_live now places the marketable simple limit DIRECTLY --
    ONE POST, no order_class, no bracket/oto attempt at all. TP/stop stay engine-managed
    (register_entry + ea.manage_tick runs FIRST each cycle, enforcing premium/target/time
    stops via the per-tick worst<=stop check) -- the exact C2 condition.

This RED-on-regression test pins: (a) exactly ONE order POST, (b) that POST is a plain
limit (no order_class / take_profit / stop_loss keys), (c) an accepted order registers
with the exit_manager, (d) a broker error -> placed=False and NO exit registration.
"""
from __future__ import annotations

import datetime as _dt
from types import SimpleNamespace

import fleet_live as fl

_CREDS = {"key": "k", "secret": "s", "base_url": "https://paper-api.example.invalid"}


def _stub_quotes(monkeypatch, mid=1.00, entry_px=1.08):
    monkeypatch.setattr(fl.fb, "get_option_mid", lambda creds, symbol: mid)
    monkeypatch.setattr(fl.fb, "marketable_limit_price",
                        lambda creds, symbol, side="buy", buffer=0.03: entry_px)
    monkeypatch.setattr(fl.fb, "open_buy_orders", lambda creds, symbol: [])
    monkeypatch.setattr(fl.fb, "cancel_order", lambda *a, **k: {})


def test_place_live_simple_first_single_plain_limit(monkeypatch):
    """The load-bearing assertion: _place_live makes exactly ONE order POST, it is a plain
    marketable limit (NO bracket/oto/order_class), and the fill registers with the
    exit_manager (no orphan, no stopless naked long)."""
    posts: list = []

    def fake_request(creds, endpoint, method="GET", data=None, timeout=15):
        posts.append({"endpoint": endpoint, "method": method, "data": data})
        return {"id": "fake-order", "status": "accepted"}

    registered: dict = {}

    def fake_register_entry(arm_id, **kw):
        registered["arm_id"] = arm_id
        registered.update(kw)

    _stub_quotes(monkeypatch)
    monkeypatch.setattr(fl.fb, "_request", fake_request)
    monkeypatch.setattr(fl.ea, "register_entry", fake_register_entry)

    decision = SimpleNamespace(side="P", strike=600, qty=3, setup_name="VWAP_CONTINUATION")
    arm = {"id": "risky-test"}
    exit_shape = {"tp1_premium_pct": 0.30, "premium_stop_pct": -0.08,
                  "tp1_qty_fraction": 0.667, "profit_lock_mode": "trailing"}
    now = _dt.datetime(2026, 6, 29, 10, 0)

    res = fl._place_live(_CREDS, arm, decision, exit_shape, {"tick_id": 1}, {}, now)

    assert len(posts) == 1, f"expected exactly ONE order POST, got {posts}"
    order = posts[0]
    assert order["endpoint"] == "orders" and order["method"] == "POST"
    data = order["data"]
    # simple-FIRST: NO complex-order fields anywhere (the 2 guaranteed 422s are gone)
    assert "order_class" not in data, "bracket/oto attempt detected -- FIX2 regression"
    assert "take_profit" not in data and "stop_loss" not in data
    assert data["type"] == "limit" and data["side"] == "buy"
    assert data["limit_price"] == "1.08", "entry must be the MARKETABLE price (ask+buffer)"
    assert res["placed"] is True
    assert res["broker"].get("_simple_first") is True
    assert registered.get("arm_id") == "risky-test", \
        "an accepted fill MUST register with the exit_manager (C2: tick-managed stop)"


def test_broker_error_strands_no_exit_state(monkeypatch):
    """Characterize the failure mode being guarded: a broker _error -> placed=False and
    register_entry is NEVER called (no orphan exit state for an unplaced order)."""
    _stub_quotes(monkeypatch)
    monkeypatch.setattr(fl.fb, "_request",
                        lambda *a, **k: {"_error": "HTTP 500", "_status": 500})
    called = {"n": 0}
    monkeypatch.setattr(fl.ea, "register_entry",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))

    decision = SimpleNamespace(side="P", strike=600, qty=3, setup_name="VWAP_CONTINUATION")
    now = _dt.datetime(2026, 6, 29, 10, 0)
    res = fl._place_live(_CREDS, {"id": "x"}, decision, {}, {"tick_id": 1}, {}, now)

    assert res["placed"] is False
    assert called["n"] == 0  # no fill -> no exit registration


def test_place_live_skip_late_entry_no_broker_touch(monkeypatch):
    """FIX1: at/after the entry ceiling _place_live returns SKIP_LATE_ENTRY and touches
    NOTHING on the broker (no quote fetch, no order POST)."""
    def _boom(*a, **k):
        raise AssertionError("broker must not be touched after the entry ceiling")
    monkeypatch.setattr(fl.fb, "get_option_mid", _boom)
    monkeypatch.setattr(fl.fb, "marketable_limit_price", _boom)
    monkeypatch.setattr(fl.fb, "_request", _boom)

    decision = SimpleNamespace(side="P", strike=600, qty=3, setup_name="VWAP_CONTINUATION")
    late = _dt.datetime(2026, 6, 29, 15, 52)
    res = fl._place_live(_CREDS, {"id": "safe-1"}, decision, {}, {"tick_id": 1},
                         {"entry_no_trade_after_et": "15:00"}, late)
    assert res["placed"] is False and res["reason"] == "SKIP_LATE_ENTRY"

    # 14:00 with the same params is BEFORE the ceiling -> the ceiling itself must not block
    assert fl._past_entry_ceiling({"entry_no_trade_after_et": "15:00"},
                                  _dt.datetime(2026, 6, 29, 14, 0)) is False

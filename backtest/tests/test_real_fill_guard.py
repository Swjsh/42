"""G-REAL-FILL (#15, 2026-06-30): the money-path fill primitives.

The 2026-06-30 audit found the rig had filled 0 orders ever: entries were priced limit @ mid
(rarely crosses on 0DTE) and `placed` meant "broker accepted the POST", not "filled". These
guards pin the fix primitives in fleet_broker:
  - marketable_limit_price crosses the spread (ask+buffer for a buy) so the order actually fills
  - poll_fill only reports filled=True on a real terminal fill (not an accepted-but-new order)
so a future edit can't silently revert to mid-pricing or accepted==filled.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1].parent
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))
import fleet_broker as fb  # noqa: E402


def test_marketable_limit_crosses_ask(monkeypatch) -> None:
    monkeypatch.setattr(fb, "get_option_quote_hilo", lambda c, s: (1.40, 1.20))  # (ask, bid)
    assert fb.marketable_limit_price({}, "SPY...", side="buy", buffer=0.03) == 1.43  # ask+buffer
    assert fb.marketable_limit_price({}, "SPY...", side="buy", buffer=0.0) == 1.40   # >= ask (crosses)


def test_marketable_limit_none_on_no_quote(monkeypatch) -> None:
    monkeypatch.setattr(fb, "get_option_quote_hilo", lambda c, s: None)
    assert fb.marketable_limit_price({}, "SPY...", side="buy") is None  # HOLD, never blind-price


def test_poll_fill_accepted_but_new_is_not_filled(monkeypatch) -> None:
    # An accepted order sitting at status=new/filled_qty=0 must NOT count as placed (the bug).
    monkeypatch.setattr(fb, "get_order", lambda c, oid: {"status": "new", "filled_qty": "0"})
    r = fb.poll_fill({}, "oid", attempts=1, sleep_sec=0)
    assert r["filled"] is False


def test_poll_fill_real_fill_is_placed(monkeypatch) -> None:
    monkeypatch.setattr(fb, "get_order", lambda c, oid:
                        {"status": "filled", "filled_qty": "3", "filled_avg_price": "1.25"})
    r = fb.poll_fill({}, "oid", attempts=1, sleep_sec=0)
    assert r["filled"] is True and r["filled_qty"] == 3 and r["filled_avg_price"] == 1.25


def test_callers_price_marketable_not_mid() -> None:
    """The two live placement paths must place at the marketable entry_px, not mid, and the
    additive primitives must exist (regression guard for the whole #15 fix)."""
    for fn in ("marketable_limit_price", "poll_fill", "cancel_order", "open_buy_orders", "get_order"):
        assert hasattr(fb, fn), f"fleet_broker must expose {fn}"
    fl = (REPO / "automation" / "state" / "fleet" / "fleet_live.py").read_text(encoding="utf-8")
    hc = (REPO / "setup" / "scripts" / "heartbeat_core.py").read_text(encoding="utf-8")
    for src, name in ((fl, "fleet_live"), (hc, "heartbeat_core")):
        assert "marketable_limit_price" in src, f"{name} must price the entry marketable"
        # The POST payload must carry entry_px as the limit price. Both call styles count:
        # kwarg style (limit_price=entry_px) or dict-payload style ("limit_price": str(...entry_px...)).
        kwarg_style = "limit_price=entry_px" in src
        payload_style = '"limit_price": str(round(float(entry_px)' in src
        assert kwarg_style or payload_style, f"{name} must place at entry_px (not mid)"

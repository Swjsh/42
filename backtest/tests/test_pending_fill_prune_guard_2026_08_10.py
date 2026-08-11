"""Guards for the PENDING-FILL PRUNE GUARD (2026-08-10, the risky-1 -$440 put).

The incident these pin (quoted from risky-1's decisions.jsonl):
  09:52:05  ENTER_BEAR placed, limit 1.14, broker status pending_new
  09:53:04  exit_pass: FLAT_SUSPECT_HOLD flat_reads 1/2   (qty=0 -- order still working)
  09:54:05  exit_pass: FLAT_PRUNED flat_reads 2           (exit state DELETED)
  09:54:49  the order FILLS, 5x SPY260810P00773000 @ 1.08
  09:55+    position open, exit_pass [] every tick -- unmanaged, premium stop 1.05 never
            fires, rides 1.08 -> 0.20 to the 15:45 EOD sweep. -$440.

Root cause in one sentence: the D5 flat-prune counted the PENDING-ORDER window's genuine
qty=0 reads as lifecycle-closed evidence -- it checks positions but never open orders.

What must never rot:
  1. THE INCIDENT: qty=0 x N ticks with an open BUY order working must never prune.
  2. D5 unchanged when no order is working: 2 consecutive flat reads still prune.
  3. Order-query error fails CLOSED (state held), mirroring the position-query rule.
  4. A broker double WITHOUT the primitive keeps today's exact D5 behaviour (compat).
  5. A confirmed prune leaves a durable receipt in prune-log.jsonl (the STATUS.md line
     lost a read-modify-write race today; the append-only sidecar must not).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FLEET = REPO / "automation" / "state" / "fleet"
if str(FLEET) not in sys.path:
    sys.path.insert(0, str(FLEET))

import exit_actuator as ea  # noqa: E402
import strategies as st  # noqa: E402

ARM = "pytest-pending-fill-guard"


class BrokerDouble:
    """Minimal broker: qty=0 always; open-buy-orders behaviour is the test variable."""

    def __init__(self, *, pending: list | None, order_query_ok: bool = True):
        self._pending = pending or []
        self._ok = order_query_ok

    def symbol_position_qty_checked(self, creds, symbol):
        return 0, True

    def get_position_qty(self, creds, symbol):
        return 0

    def open_buy_orders_checked(self, creds, symbol):
        return self._pending, self._ok

    def get_option_quote_hilo(self, creds, symbol):  # pragma: no cover - flat path only
        return (1.0, 1.0)


class BrokerDoubleNoPrimitive:
    """A double WITHOUT open_buy_orders_checked -- exercises the getattr compat path."""
    def symbol_position_qty_checked(self, creds, symbol):
        return 0, True

    def get_position_qty(self, creds, symbol):
        return 0

    def get_option_quote_hilo(self, creds, symbol):  # pragma: no cover
        return (1.0, 1.0)


@pytest.fixture()
def registered(tmp_path, monkeypatch):
    """A fresh arm dir with one registered put, mirroring 09:52:06 exactly."""
    monkeypatch.setattr(ea, "FLEET_DIR", tmp_path)
    monkeypatch.setattr(ea, "STATUS_MD", tmp_path / "STATUS.md")
    shape = st.by_name("ribbon_ride").exit.to_dict()
    shape.update(stop_mode="premium", premium_stop_pct=-0.06, tp1_premium_pct=0.5)
    ea.register_entry(ARM, symbol="SPY260810P00773000", side="P", entry_premium=1.14,
                      qty=5, exit_shape=shape, strategy="VWAP_CONTINUATION",
                      trigger_level=None, structure_stop_enabled=False)
    assert ea.load_states(ARM), "fixture must start registered"
    return tmp_path


def _tick(broker):
    return ea.manage_tick(ARM, creds={}, live=False, broker=broker)


def test_incident_pending_order_never_prunes(registered):
    """qty=0 on 4 straight ticks WITH an open buy order -> state survives every tick."""
    b = BrokerDouble(pending=[{"id": "3bce5f28", "status": "pending_new"}])
    for i in range(4):
        rows = _tick(b)
        assert rows and rows[0]["action"] == "PENDING_FILL_HOLD", (i, rows)
    assert ea.load_states(ARM), "exit state was pruned during the pending-fill window"


def test_d5_still_prunes_when_no_order_working(registered):
    """No open order + 2 consecutive flat reads -> FLAT_PRUNED exactly as D5 shipped it."""
    b = BrokerDouble(pending=[])
    r1 = _tick(b)
    assert r1[0]["action"] == "FLAT_SUSPECT_HOLD"
    r2 = _tick(b)
    assert r2[0]["action"] == "FLAT_PRUNED"
    assert not ea.load_states(ARM)


def test_order_query_error_fails_closed(registered):
    """Open-order query error -> HOLD, state kept, streak NOT advanced."""
    bad = BrokerDouble(pending=[], order_query_ok=False)
    for _ in range(3):
        rows = _tick(bad)
        assert rows[0]["action"] == "HOLD"
    assert ea.load_states(ARM)
    # and once the query recovers with no order working, D5 counts from zero
    ok = BrokerDouble(pending=[])
    assert _tick(ok)[0]["action"] == "FLAT_SUSPECT_HOLD"
    assert _tick(ok)[0]["action"] == "FLAT_PRUNED"


def test_double_without_primitive_keeps_d5_behaviour(registered):
    """Compat: a broker double lacking open_buy_orders_checked runs today's exact D5 path."""
    b = BrokerDoubleNoPrimitive()
    assert _tick(b)[0]["action"] == "FLAT_SUSPECT_HOLD"
    assert _tick(b)[0]["action"] == "FLAT_PRUNED"


def test_confirmed_prune_writes_durable_receipt(registered):
    """prune-log.jsonl gets one append-only line per confirmed prune (STATUS.md lost
    today's line to a concurrent-writer race; the sidecar is the auditable record)."""
    b = BrokerDouble(pending=[])
    _tick(b)
    _tick(b)
    log = registered / ARM / "prune-log.jsonl"
    assert log.exists(), "no durable prune receipt written"
    row = json.loads(log.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert row["symbol"] == "SPY260810P00773000"
    assert row["flat_reads"] == 2


def test_pending_window_resets_streak(registered):
    """A flat read, THEN the order appears (window), then order gone: the earlier read
    must not count -- the streak restarts at 1, not 2."""
    no_order = BrokerDouble(pending=[])
    assert _tick(no_order)[0]["action"] == "FLAT_SUSPECT_HOLD"          # read 1
    working = BrokerDouble(pending=[{"id": "x"}])
    assert _tick(working)[0]["action"] == "PENDING_FILL_HOLD"           # resets
    assert _tick(no_order)[0]["action"] == "FLAT_SUSPECT_HOLD"          # read 1 again
    assert ea.load_states(ARM)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))

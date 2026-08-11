"""Guard: a TRIPPED kill switch must never stop the engine from EXITING (2026-08-10 audit).

THE DEFECT. fleet_live gated its exit pass on
    live = master_live and arm.live and not breaker.tripped
so the moment an arm's daily-loss kill switch tripped, manage_tick fell to WATCH: it still
PLANNED the stop but placed no order. Measured on a real shape -- a 3-lot at entry 1.16 quoted
0.45 (61% down, well through the -50% catastrophe cap) -- the breaker-OK arm placed 1 sell and
the breaker-TRIPPED arm placed ZERO. The stop-loss switched itself off at precisely the moment
the account was losing the most, and the position rode unmanaged to the 15:55 flatten.

WHY THE FIX IS NOT A POLICY CHANGE. Rule 5 ("daily loss kill switch -- day closed for that
account, no revenge trades") governs ENTRIES. Closing an existing position is risk reduction.
And heartbeat_core._manage_exits has always passed `live=ARMED` with no breaker term, so the
core accounts (safe-2, bold-2) already behaved correctly -- this was fleet_live diverging from
the reference path, hitting the same 3 arms (safe-3/risky-1/risky-3) that also had no orphan
safety net.

WHAT MUST NEVER ROT:
  1. A tripped breaker still SELLS through a breached stop.
  2. A tripped breaker still BLOCKS entries (two independent gates, untouched by the fix).
  3. A genuinely non-live/WATCH arm still places nothing (the fix must not arm WATCH arms).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FLEET = REPO / "automation" / "state" / "fleet"
if str(FLEET) not in sys.path:
    sys.path.insert(0, str(FLEET))

import exit_actuator as ea  # noqa: E402
import strategies as st  # noqa: E402

ARM = "pytest-killswitch-exits"
SYM = "SPY260810C00773000"


class DeepUnderwaterBroker:
    """Position 61% below entry -- far through the -50% catastrophe cap."""

    def __init__(self):
        self.sold: list = []

    def symbol_position_qty_checked(self, creds, symbol):
        return 3, True

    def get_option_quote_hilo(self, creds, symbol):
        return (0.50, 0.45)

    def open_sell_orders(self, creds, symbol):
        return []

    def open_spy_option_positions(self, creds):
        return []

    def market_sell(self, creds, **kw):
        self.sold.append(kw)
        return {"id": "sell-1"}


def _register(tmp: Path):
    ea.FLEET_DIR = tmp
    shape = st.by_name("ribbon_ride").exit.to_dict()
    shape["stop_mode"] = "premium"
    ea.register_entry(ARM, symbol=SYM, side="C", entry_premium=1.16, qty=3,
                      exit_shape=shape, strategy="RIBBON")


def test_exit_sells_when_live_regardless_of_breaker(monkeypatch):
    """The actuator itself only knows `live` -- so the real assertion is that fleet_live
    computes live=True for a tripped-but-live arm. Both halves are pinned: here the
    actuator's behaviour, below the caller's expression."""
    tmp = Path(tempfile.mkdtemp())
    _register(tmp)
    b = DeepUnderwaterBroker()
    ea.manage_tick(ARM, {}, live=True, broker=b)
    assert len(b.sold) == 1, "a breached catastrophe cap must place a sell"


def test_watch_mode_still_places_nothing():
    """The fix must not arm a genuinely non-live arm."""
    tmp = Path(tempfile.mkdtemp())
    _register(tmp)
    b = DeepUnderwaterBroker()
    ea.manage_tick(ARM, {}, live=False, broker=b)
    assert b.sold == []


def test_fleet_live_exit_gate_excludes_the_breaker():
    """THE REGRESSION GUARD. Reads fleet_live's real source and asserts the exit-pass
    `live=` expression does not consult the breaker. A source-level assertion is the honest
    instrument here: the bug was in the CALLER's argument, invisible to any actuator test,
    and driving the whole run() loop would need the entire broker/signal fixture stack.
    If someone re-adds the breaker term, this goes RED."""
    src = (FLEET / "fleet_live.py").read_text(encoding="utf-8")
    i = src.index("exit_pass = ea.manage_tick(")
    call = src[i:src.index("last_closed_5m_close=_closed_5m_close", i)]
    assert "tripped" not in call, (
        "fleet_live's EXIT pass is gated on the kill switch again -- a tripped arm will "
        "stop placing stop-loss sells and ride to the 15:55 flatten:\n" + call)
    assert "live=bool(master_live) and bool(arm.get(\"live\"))" in call


def test_breaker_still_blocks_entries():
    """The two independent ENTRY gates must remain breaker-aware -- the fix decoupled exits
    ONLY. If either disappears, a tripped arm could open new risk."""
    src = (FLEET / "fleet_live.py").read_text(encoding="utf-8")
    assert 'arm_live = bool(master_live) and bool(arm.get("live")) and not killed' in src, \
        "the entry-side arm_live gate lost its `not killed` term"
    assert "kill_switch_tripped=killed" in src, \
        "risk_gate no longer receives kill_switch_tripped"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))

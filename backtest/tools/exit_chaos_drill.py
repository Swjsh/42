#!/usr/bin/env python
"""exit_chaos_drill.py -- "we're in a trade and the stop is breached. What has to go wrong
for us NOT to get out?"

J, 2026-08-10 night: "if we get into a trade, if we get into a stop loss, are we gonna be able
to get out if x, y, and z happens?" Guard tests answer "does the happy path work". This
answers the adversarial question: it drives the REAL `exit_actuator.manage_tick` against
brokers engineered to misbehave, one failure mode per scenario, and reports whether the
position is FLAT by the end.

Every scenario starts identically: 3 lots, entry 1.16, quote collapsed to 0.45 -- 61% down,
far through the -50% catastrophe cap. A correct engine sells on the first tick it can.

VERDICTS
  ESCAPED   -- a sell was placed. The engine got out.
  TRAPPED   -- no sell after every tick. Requires the 15:55 EOD flatten to save us, which is
               a separate scheduled task (fleet_eod.close_all_spy_options) and therefore a
               single point of failure for the whole day.
  BY-DESIGN -- no sell, and that is correct (WATCH mode, or a sell already resting).

Read TRAPPED rows as open risk, not as failures of this script. $0, no network, no LLM.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FLEET = REPO / "automation" / "state" / "fleet"
if str(FLEET) not in sys.path:
    sys.path.insert(0, str(FLEET))

import exit_actuator as ea  # noqa: E402
import strategies as st  # noqa: E402

SYM = "SPY260810C00773000"
ARM = "chaos"
ENTRY, QTY = 1.16, 3


class Broker:
    """Baseline healthy broker; each scenario subclasses/overrides one behaviour."""

    def __init__(self):
        self.sold: list = []
        self.qty = QTY
        self.tick = 0

    def symbol_position_qty_checked(self, creds, symbol):
        return self.qty, True

    def get_position_qty(self, creds, symbol):
        return self.qty

    def get_option_quote_hilo(self, creds, symbol):
        return (0.50, 0.45)          # deep through the cap

    def open_sell_orders(self, creds, symbol):
        return []

    def open_buy_orders_checked(self, creds, symbol):
        return [], True

    def open_spy_option_positions(self, creds):
        return []

    def market_sell(self, creds, **kw):
        self.sold.append(kw)
        self.qty = 0
        return {"id": f"s{len(self.sold)}"}


class QuoteDead(Broker):
    """The option quote feed returns nothing -- the engine is blind to the stop."""
    def get_option_quote_hilo(self, creds, symbol):
        return None


class SellRejectedOnce(Broker):
    """First sell is rejected by the broker; later ticks are healthy."""
    def market_sell(self, creds, **kw):
        self.tick += 1
        if self.tick == 1:
            return {"_error": "422 rejected"}
        return super().market_sell(creds, **kw)


class SellAlwaysRejected(Broker):
    def market_sell(self, creds, **kw):
        return {"_error": "422 rejected every time"}


class PositionQueryErrors(Broker):
    """Broker cannot report the position -- must fail CLOSED (hold state), not prune."""
    def symbol_position_qty_checked(self, creds, symbol):
        return 0, False


class SellAlreadyResting(Broker):
    """A prior tick's sell is still working -- stacking another would double-sell."""
    def open_sell_orders(self, creds, symbol):
        return [{"id": "resting-1", "status": "new"}]


class PartialFill(Broker):
    """Sell fills only 2 of 3; a lot remains and must still be managed next tick."""
    def market_sell(self, creds, **kw):
        self.sold.append(kw)
        self.qty = 1
        return {"id": "partial"}


class QuoteDeadThenRecovers(Broker):
    def get_option_quote_hilo(self, creds, symbol):
        self.tick += 1
        return None if self.tick <= 3 else (0.50, 0.45)


SCENARIOS = [
    ("healthy baseline", Broker, True, "control -- must escape on tick 1"),
    ("option quote feed DEAD", QuoteDead, True, "engine is blind: no quote, no stop check"),
    ("quote dead 3 ticks then back", QuoteDeadThenRecovers, True, "transient feed outage"),
    ("sell REJECTED once", SellRejectedOnce, True, "must retry on the next tick"),
    ("sell rejected EVERY tick", SellAlwaysRejected, True, "broker refuses; nothing we can do"),
    ("position query ERRORS", PositionQueryErrors, True, "must hold state, never prune"),
    ("a sell is already RESTING", SellAlreadyResting, True, "must NOT stack a duplicate"),
    ("partial fill (2 of 3)", PartialFill, True, "remainder must stay managed"),
    ("WATCH mode (arm not live)", Broker, False, "must place nothing"),
]


def run_one(cls, live: bool, ticks: int = 5) -> dict:
    ea.FLEET_DIR = Path(tempfile.mkdtemp())
    shape = st.by_name("ribbon_ride").exit.to_dict()
    shape["stop_mode"] = "premium"
    ea.register_entry(ARM, symbol=SYM, side="C", entry_premium=ENTRY, qty=QTY,
                      exit_shape=shape, strategy="RIBBON")
    b = cls()
    actions: list = []
    for _ in range(ticks):
        rows = ea.manage_tick(ARM, {}, live=live, broker=b)
        for r in rows:
            if r.get("action"):
                actions.append(r["action"])
            for e in (r.get("executed") or []):
                actions.append(f"{e.get('kind')}/{e.get('stage')}"
                               f"{'' if e.get('placed') else '(NOT PLACED)'}")
    still_tracked = SYM in ea.load_states(ARM)
    return {"sells": len(b.sold), "final_qty": b.qty, "tracked": still_tracked,
            "actions": actions[:4]}


def main() -> int:
    print(f"{'scenario':32s} {'sells':>5s} {'qty':>4s} {'tracked':>8s}  verdict")
    print("-" * 108)
    trapped = 0
    for name, cls, live, note in SCENARIOS:
        r = run_one(cls, live)
        if not live:
            verdict = "BY-DESIGN (WATCH places nothing)" if r["sells"] == 0 else "BUG: WATCH SOLD"
        elif cls is SellAlreadyResting:
            verdict = ("BY-DESIGN (no duplicate stacked)" if r["sells"] == 0
                       else "BUG: stacked a duplicate sell")
        elif r["sells"] > 0:
            verdict = "ESCAPED"
        else:
            verdict = "TRAPPED -- only the 15:55 EOD flatten saves this"
            trapped += 1
        print(f"{name:32s} {r['sells']:>5d} {r['final_qty']:>4d} {str(r['tracked']):>8s}  "
              f"{verdict}")
        print(f"{'':32s} {'':5s} {'':4s} {'':8s}  note: {note}; first actions={r['actions']}")
    print("-" * 108)
    print(f"TRAPPED scenarios: {trapped}. Each one is a day where the stop does not fire and "
          f"the ONLY backstop is the 15:55 EOD flatten task.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

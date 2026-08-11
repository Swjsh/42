#!/usr/bin/env python
"""verify_pending_fill_guard_live.py -- prove the pending-fill prune guard against the REAL
broker, not a test double.

WHY (J, 2026-08-10 night): "how do we validate this is gonna work? Can you simulate trades
somehow without writing your own code that'll pass because you wrote it to pass?"

The 2026-08-10 risky-1 incident cost $440 because a WORKING BUY ORDER read as "flat" and the
position's exit state was pruned 44 seconds before the fill. Tonight's fix consults
`fleet_broker.open_buy_orders_checked` before counting a flat read. Every test of that fix so
far uses a BrokerDouble I wrote -- which proves my double behaves as I imagined, and proves
nothing about Alpaca. The load-bearing unknown is REAL API semantics: does
`GET /v2/orders?status=open` actually return an unfilled resting order? If it returns [], the
guard is inert and the bug ships again on the next slow fill.

Options are closed overnight, so this probes with CRYPTO -- same broker, same REST API, same
`fleet_broker` primitives, trading 24/7. What it exercises is the ORDER-VISIBILITY semantics
and the real `exit_actuator.manage_tick` code path; the asset class is irrelevant to both.

WHAT IT DOES (paper only, self-cleaning):
  1. Places ONE minimum-size BUY limit at HALF market on a paper arm, so it rests unfilled.
  2. Asserts `open_buy_orders_checked` returns it (the primitive the fix depends on).
  3. Registers a scratch ExitState for that symbol and runs the REAL `manage_tick` against the
     REAL broker twice -- under the OLD behaviour that is exactly the 2-read sequence that
     pruned risky-1. It must emit PENDING_FILL_HOLD both times and KEEP the state.
  4. Cancels the order and deletes the scratch state, in a finally block, always.

Exit 0 = the guard is real. Non-zero = it is inert and tomorrow is exposed; the message says
which step failed. $0, no LLM.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FLEET = REPO / "automation" / "state" / "fleet"
if str(FLEET) not in sys.path:
    sys.path.insert(0, str(FLEET))

import exit_actuator as ea  # noqa: E402
import fleet_broker as fb  # noqa: E402
import strategies as st  # noqa: E402

PROBE_ARM = "risky-1"         # the arm that actually suffered the bug. Flat overnight; the
                              # resting order is $10 notional at HALF market so it cannot
                              # fill, is cancelled in the finally block, and is a crypto
                              # symbol the SPY options engine never touches.
                              # (safe-1 was the first choice -- its key returns 401, dead.)
SCRATCH_ARM = "_probe-pending-fill"
SYMBOL = "BTC/USD"
MIN_COST_BASIS = 11.0         # broker rejects < $10 cost basis (40310000);
                              # qty is derived from the limit so this is the
                              # SMALLEST order the venue will accept


def fail(msg: str) -> int:
    print(f"[probe] FAIL: {msg}")
    return 1


def _crypto_price(creds: dict, symbol: str) -> "float | None":
    """Latest crypto price from data.alpaca.markets (a different host from the trading API
    that fleet_broker._request is pinned to). Quote midpoint, falling back to the last bar."""
    import urllib.parse
    import urllib.request

    hdr = {"APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]}
    qs = urllib.parse.urlencode({"symbols": symbol})
    for path, outer, field in (("latest/quotes", "quotes", "ap"),
                               ("latest/bars", "bars", "c")):
        url = f"https://data.alpaca.markets/v1beta3/crypto/us/{path}?{qs}"
        try:
            req = urllib.request.Request(url, headers=hdr)
            with urllib.request.urlopen(req, timeout=15) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"[probe] {path} fetch failed: {type(e).__name__}: {e}")
            continue
        val = ((payload.get(outer) or {}).get(symbol) or {}).get(field)
        if val:
            return float(val)
    return None


def main() -> int:
    creds_all = fb.load_creds()
    if PROBE_ARM not in creds_all:
        return fail(f"no creds for {PROBE_ARM} in secrets.json")
    creds = creds_all[PROBE_ARM]

    # Crypto market data lives on data.alpaca.markets, NOT the trading host fb._request pins.
    px = _crypto_price(creds, SYMBOL)
    if not px:
        return fail(f"could not read a {SYMBOL} price")
    limit = round(float(px) * 0.50, 2)   # 50% below market -> rests, cannot fill
    qty = f"{MIN_COST_BASIS / limit:.9f}"
    print(f"[probe] {SYMBOL} ~{float(px):,.2f} -> resting BUY limit {limit:,.2f} qty {qty} "
          f"(${float(qty) * limit:.2f} cost basis)")

    order_id = None
    scratch_dir = FLEET / SCRATCH_ARM
    try:
        res = fb._request(creds, "orders", method="POST", data={
            "symbol": SYMBOL, "qty": qty, "side": "buy", "type": "limit",
            "limit_price": str(limit), "time_in_force": "gtc"})
        if not isinstance(res, dict) or res.get("_error") or not res.get("id"):
            return fail(f"order rejected: {res!r}")
        order_id = res["id"]
        print(f"[probe] placed {order_id} status={res.get('status')}")

        # STEP 2 -- the primitive the whole fix rests on
        found, ok = [], False
        for attempt in range(6):
            time.sleep(1.0)
            found, ok = fb.open_buy_orders_checked(creds, SYMBOL)
            if ok and found:
                break
        if not ok:
            return fail("open_buy_orders_checked reported query failure (ok=False)")
        if not found:
            return fail("open_buy_orders_checked returned [] for a RESTING UNFILLED ORDER -- "
                        "the pending-fill guard is INERT and the risky-1 bug can recur")
        print(f"[probe] STEP 2 OK: open_buy_orders_checked sees {len(found)} working order(s) "
              f"(status={found[0].get('status')})")

        # STEP 3 -- the REAL manage_tick, twice: the exact sequence that pruned risky-1
        if scratch_dir.exists():
            shutil.rmtree(scratch_dir)
        shape = st.by_name("ribbon_ride").exit.to_dict()
        shape.update(stop_mode="premium", premium_stop_pct=-0.50)
        ea.register_entry(SCRATCH_ARM, symbol=SYMBOL, side="C", entry_premium=float(px),
                          qty=1, exit_shape=shape, strategy="PROBE",
                          trigger_level=None, structure_stop_enabled=False)
        actions = []
        for i in (1, 2):
            rows = ea.manage_tick(SCRATCH_ARM, creds, live=False)
            act = (rows[0].get("action") if rows else "NO_ROW")
            actions.append(act)
            print(f"[probe] manage_tick #{i}: {act}")
        if actions != ["PENDING_FILL_HOLD", "PENDING_FILL_HOLD"]:
            return fail(f"expected PENDING_FILL_HOLD twice, got {actions} -- under the old "
                        "code this is where risky-1's exit state was deleted")
        if not ea.load_states(SCRATCH_ARM):
            return fail("exit state was pruned despite a working order -- guard did not hold")
        print("[probe] STEP 3 OK: exit state SURVIVED two broker-flat reads with an order working")

        print("\n[probe] PASS -- the pending-fill guard is real against the live Alpaca API.")
        return 0
    finally:
        if order_id:
            try:
                fb.cancel_order(creds, order_id, live=True)
                print(f"[probe] cleanup: cancelled {order_id}")
            except Exception as e:  # noqa: BLE001
                print(f"[probe] !! CLEANUP FAILED, cancel {order_id} by hand: {e}")
        if scratch_dir.exists():
            shutil.rmtree(scratch_dir, ignore_errors=True)
            print("[probe] cleanup: scratch arm removed")
        # Cancellation is ASYNC -- the first read after cancel_order still shows the order
        # (pending_cancel). Poll instead of single-shotting, or every clean run cries wolf.
        left: list = []
        for _ in range(8):
            left, ok_q = fb.open_buy_orders_checked(creds, SYMBOL)
            if ok_q and not left:
                print(f"[probe] cleanup verify: 0 {SYMBOL} buy orders open -- clean")
                break
            time.sleep(2.0)
        else:
            print(f"[probe] !! cleanup verify: {len(left)} {SYMBOL} buy order(s) STILL OPEN "
                  f"after 16s -- cancel by hand: {[o.get('id') for o in left]}")


if __name__ == "__main__":
    raise SystemExit(main())

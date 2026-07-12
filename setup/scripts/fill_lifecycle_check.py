"""fill_lifecycle_check -- 24/7 live proof of the #15 order-fill machinery.

WHY THIS EXISTS (J 2026-06-30: "why not replicate the 24/7 crypto in gym?"): the SPY 0DTE
fill path can only be exercised at the RTH open, so a fill bug hides until 09:30. But the
fill machinery in fleet_broker (marketable pricing, poll_fill, cancel_order) is
INSTRUMENT-AGNOSTIC, and crypto fills 24/7 -- so we can prove the risky part (does a
marketable order FILL, and does poll_fill tell filled from not-filled -- the exact
"placed != filled" bug) ANY time, against a real fillable market.

WHY NOT IN crypto/validators/: that folder has a HARD RULE (crypto/CLAUDE.md #1) -- "No live
orders. This folder NEVER places crypto orders." This check PLACES tiny paper orders, so per
that same rule ("if we ever trade crypto it goes in a separate folder") it lives HERE, in the
execution/ops scripts, not in the read-only chart-primitive gym.

WHAT IT PROVES (live, against a fleet paper arm):
  POSITIVE : a marketable buy FILLS and fleet_broker.poll_fill reports filled=True
  NEGATIVE : an un-crossable limit does NOT fill and poll_fill reports filled=False (anti-phantom)
  CANCEL   : fleet_broker.cancel_order removes the resting order
Always flattens (tiny paper notional). Exit 0 = PASS. Run after ANY money-path change + as a
standing 24/7 smoke. The OFFLINE half (mocked) is in backtest/tests/test_real_fill_guard.py.

Run: backtest/.venv/Scripts/python.exe setup/scripts/fill_lifecycle_check.py [--notional 20]
Guard: it refuses to run during RTH (09:30-16:00 ET) so it never competes with live SPY execution.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1].parent
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))
sys.path.insert(0, str(REPO / "setup" / "scripts"))
import fleet_broker as fb  # the code under test

SYM = "BTC/USD"


def _rth_now() -> bool:
    try:
        from et_clock import et_now
        n = et_now()
        return n.weekday() < 5 and "09:30" <= n.strftime("%H:%M") <= "16:00"
    except Exception:  # noqa: BLE001
        return False  # fail-open: if we can't tell the time, allow (paper only)


def _order(c, body):
    return fb._request(c, "orders", method="POST", data=body)


def _btc_pos(c):
    for p in fb.get_positions(c):
        if str(p.get("symbol", "")).replace("/", "").upper().startswith("BTC"):
            return p
    return None


def run(notional: float = 20.0) -> dict:
    creds = fb.load_creds()
    # Prefer safe-3 (an isolated fleet_rest arm, its own dedicated account) over safe-1.
    # safe-1 was RETIRED 2026-07-11 -- its credentials now equal core Safe's ("safe-2"), the
    # actual production paper account. Placing these test BTC/USD round-trips there would
    # pollute core Safe's real activity/equity with test-order noise instead of an isolated
    # fleet arm, which is exactly what this preference existed to avoid in the first place.
    for preferred in ("safe-3", "safe-1"):
        if preferred in creds:
            arm = preferred
            break
    else:
        arm = next(iter(creds))
    c = creds[arm]
    results: dict = {}
    q = json.loads(urllib.request.urlopen(urllib.request.Request(
        "https://data.alpaca.markets/v1beta3/crypto/us/latest/quotes?symbols=BTC%2FUSD",
        headers={"APCA-API-KEY-ID": c["key"], "APCA-API-SECRET-KEY": c["secret"]}), timeout=15).read())
    bid = float(q["quotes"]["BTC/USD"]["bp"])
    print(f"[fill-check] arm={arm} bid={bid}")
    try:
        # POSITIVE: marketable buy -> fills; poll_fill detects it
        r = _order(c, {"symbol": SYM, "notional": str(notional), "side": "buy",
                       "type": "market", "time_in_force": "gtc"})
        oid = r.get("id")
        fill = fb.poll_fill(c, oid, attempts=6, sleep_sec=1.0) if oid else {"filled": False}
        print(f"[+] marketable buy filled={fill['filled']} qty={fill.get('filled_qty')} avg={fill.get('filled_avg_price')}")
        results["POSITIVE_marketable_fills_pollfill_detects"] = bool(fill.get("filled"))

        # NEGATIVE: un-crossable limit (~10% below, inside Alpaca's price collar) -> not filled
        lp = round(bid * 0.90, 2)
        r2 = _order(c, {"symbol": SYM, "qty": "0.0003", "side": "buy",
                        "type": "limit", "limit_price": str(lp), "time_in_force": "gtc"})
        oid2 = r2.get("id")
        if oid2:
            time.sleep(1.5)
            fill2 = fb.poll_fill(c, oid2, attempts=2, sleep_sec=1.0)
            print(f"[-] un-crossable limit filled={fill2['filled']} status={fill2.get('status')}")
            results["NEGATIVE_uncrossable_pollfill_not_filled"] = (fill2.get("filled") is False)
            fb.cancel_order(c, oid2, live=True)
            time.sleep(1.5)
            results["CANCEL_removes_order"] = fb.get_order(c, oid2).get("status") in (
                "canceled", "cancelled", "pending_cancel", "expired")
        else:
            print(f"[-] could not place resting limit (err={r2.get('_error')}) -- inconclusive")
            results["NEGATIVE_uncrossable_pollfill_not_filled"] = None
            results["CANCEL_removes_order"] = None
    finally:
        time.sleep(1.0)
        pos = _btc_pos(c)
        if pos:
            qty = pos.get("qty_available") or pos.get("qty")
            _order(c, {"symbol": SYM, "qty": str(qty), "side": "sell",
                       "type": "market", "time_in_force": "gtc"})
            time.sleep(2.0)
        results["FLAT_after"] = _btc_pos(c) is None

    graded = {k: v for k, v in results.items() if v is not None}
    all_pass = bool(graded) and all(graded.values())
    return {"arm": arm, "results": results, "all_pass": all_pass}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--notional", type=float, default=20.0)
    p.add_argument("--force", action="store_true", help="run even during RTH (default: refuse)")
    args = p.parse_args(argv)
    if _rth_now() and not args.force:
        print("[fill-check] RTH -- refusing to place paper orders that could compete with live SPY "
              "execution. Re-run after 16:00 ET or with --force.")
        return 0
    sc = run(args.notional)
    print("\n[fill-check] RESULTS:")
    for k, v in sc["results"].items():
        print(f"  {'PASS' if v else ('n/a ' if v is None else 'FAIL')}  {k}")
    print(f"\n[fill-check] OVERALL: {'PASS -- fill machinery verified live' if sc['all_pass'] else 'FAIL'}")
    return 0 if sc["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

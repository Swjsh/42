"""_canary_option_order_types_2026_08_02.py -- ONE-SHOT, REPRODUCIBLE diagnostic.

Built for RESTING-ORDER-EXIT-FEASIBILITY-2026-08-02 (analysis/deep-research/). Answers,
LIVE (not from docs, which turned out to be wrong -- see report): which order `type`
values does Alpaca's PAPER options endpoint actually accept for a single-leg option
order? mcp__alpaca__fetch_alpaca_doc("us/options-trading-overview") states options
support ONLY "Market and limit order types" -- this script proved that claim FALSE for
`stop`/`stop_limit` (both ACCEPTED live) and TRUE for `trailing_stop` (REJECTED,
"invalid order type for options trading", code 42210000).

Every accepted order is CANCELLED IMMEDIATELY -- never leaves anything resting. Read-only
with respect to fleet_broker.py (imports load_creds() only, never edited -- DO-NOT-TOUCH
this session per RESTING-ORDER-EXIT-FEASIBILITY task scope). No secret is ever printed --
only status/order-id/error-body, which are Alpaca's own generic response fields.

Re-run any time (e.g. once market is open, to extend this with a genuine sell-to-close
test against a real position -- impossible on the Sunday this was first run, see report
disclosure). Idempotent: places nothing that survives the run.

Canary symbol: SPY put ~$90-100 OTM at whatever the nearest 0DTE-ish expiry is (the
2026-08-02 run used SPY260803P00650000, close $0.01 -- SPY was trading mid-$740s that
week). qty=1 throughout. BUY-side tests isolate order_type validation cleanly (no
sell-to-open "uncovered contract" confound); a small SELL-to-open differential probe is
included separately to show stop/stop_limit clear type-validation and fail LATER at
business-logic layers (proving they are not just accepted-and-ignored), while
trailing_stop fails at the SAME shallow type-check layer on both sides.
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FLEET_DIR = REPO / "automation" / "state" / "fleet"
sys.path.insert(0, str(FLEET_DIR))

import fleet_broker  # noqa: E402  -- READ-ONLY usage: load_creds()/get_account()/get_positions() only

ARM = "safe-1"
SYMBOL = "SPY260803P00650000"


def _req(creds, endpoint, method="GET", data=None):
    url = f"{creds['base_url']}/v2/{endpoint.lstrip('/')}"
    headers = {
        "APCA-API-KEY-ID": creds["key"],
        "APCA-API-SECRET-KEY": creds["secret"],
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            txt = resp.read().decode("utf-8")
            return resp.status, (json.loads(txt) if txt else {})
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8"))
        except Exception:
            err = {"raw": str(e)}
        return e.code, err
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        return None, {"_network_error": str(e)}


def try_order(creds, label, payload):
    print(f"\n--- {label} ---")
    print("payload:", json.dumps(payload))
    status, body = _req(creds, "orders", method="POST", data=payload)
    print(f"HTTP {status}: {json.dumps(body)}")
    oid = body.get("id") if isinstance(body, dict) else None
    accepted = oid is not None and "code" not in body
    if accepted:
        print(f"ACCEPTED -- order id {oid}, status={body.get('status')}. Cancelling now...")
        cstatus, cbody = _req(creds, f"orders/{oid}", method="DELETE")
        print(f"cancel HTTP {cstatus}: {json.dumps(cbody) if cbody else '(empty body = success)'}")
    return {"label": label, "http_status": status, "response": body, "accepted": accepted, "order_id": oid}


def main() -> int:
    creds_all = fleet_broker.load_creds()
    if ARM not in creds_all:
        print(f"ARM '{ARM}' not in secrets.json; available arms: {list(creds_all.keys())}")
        return 1
    creds = creds_all[ARM]

    acct = fleet_broker.get_account(creds)
    print(f"account status={acct.get('status')} equity={acct.get('equity')}")
    _, open_before = _req(creds, f"orders?status=open&symbols={SYMBOL}")
    print(f"baseline open orders for {SYMBOL}: {open_before}")

    results = []
    # BUY-side: isolates order_type validation (no uncovered-short confound).
    results.append(try_order(creds, "BUY type=stop", {
        "symbol": SYMBOL, "qty": "1", "side": "buy", "type": "stop",
        "stop_price": "0.02", "time_in_force": "day"}))
    results.append(try_order(creds, "BUY type=stop_limit", {
        "symbol": SYMBOL, "qty": "1", "side": "buy", "type": "stop_limit",
        "stop_price": "0.02", "limit_price": "0.03", "time_in_force": "day"}))
    results.append(try_order(creds, "BUY type=trailing_stop (trail_price)", {
        "symbol": SYMBOL, "qty": "1", "side": "buy", "type": "trailing_stop",
        "trail_price": "0.01", "time_in_force": "day"}))
    results.append(try_order(creds, "BUY type=trailing_stop (trail_percent)", {
        "symbol": SYMBOL, "qty": "1", "side": "buy", "type": "trailing_stop",
        "trail_percent": "5", "time_in_force": "day"}))
    results.append(try_order(creds, "BUY type=limit (positive control)", {
        "symbol": SYMBOL, "qty": "1", "side": "buy", "type": "limit",
        "limit_price": "0.01", "time_in_force": "day"}))

    # SELL-to-open differential probe: shows WHERE in the pipeline each type fails.
    for typ, extra in [("stop", {"stop_price": "0.02"}),
                        ("stop_limit", {"stop_price": "0.02", "limit_price": "0.03"}),
                        ("trailing_stop", {"trail_price": "0.01"})]:
        results.append(try_order(creds, f"SELL-to-open type={typ} (differential probe)",
                                  {"symbol": SYMBOL, "qty": "1", "side": "sell", "type": typ,
                                   "time_in_force": "day", **extra}))

    _, open_after = _req(creds, f"orders?status=open&symbols={SYMBOL}")
    print(f"\nfinal open orders for {SYMBOL}: {open_after}")
    positions = fleet_broker.get_positions(creds)
    pos_match = [p for p in positions if p.get("symbol") == SYMBOL]
    print(f"final position in {SYMBOL}: {pos_match if pos_match else 'NONE (flat, as expected)'}")

    out = {"arm": ARM, "symbol": SYMBOL, "results": results,
           "final_open_orders_for_symbol": open_after, "final_position_for_symbol": pos_match}
    out_path = REPO / "analysis" / "deep-research" / "_canary_option_order_types_2026_08_02.result.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""atomic_bracket_guard -- post-Claude-exit naked-position + orphan-parent detector.

Per OP-25 ENGINE-BENEFIT AUTONOMY PRINCIPLE: this is a safety primitive that
detects rule-3 violations (no defined stop on a filled entry) caused by mid-MCP
timeouts. NEVER places orders. Only:
    (a) CANCELs unfilled orphan parent orders (cleanup, not trading)
    (b) Writes alerts to STATUS.md + automation/state/atomic-bracket-guard-{date}.jsonl
    (c) Returns exit code 0 = clean, 1 = naked position detected (operator must act)

The 2026-05-18 09:48 ET Bold incident: heartbeat tick timed out mid-MCP, leaving
a SPY 740C parent order placed without stop legs. This script would have caught it
and either canceled the unfilled parent OR surfaced a RED STATUS.md alert if it
had already filled (= naked filled position = J's rule 3 violation that needs
manual review or auto-flatten via Gamma_EodFlatten).

Runs both accounts (Safe + Bold) in one pass — checks each independently.

CLI:
    python setup/scripts/atomic_bracket_guard.py
    python setup/scripts/atomic_bracket_guard.py --account safe
    python setup/scripts/atomic_bracket_guard.py --account bold
    python setup/scripts/atomic_bracket_guard.py --dry-run     # don't cancel, just report
    python setup/scripts/atomic_bracket_guard.py --silent      # JSON only, no stdout
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import urllib.request
import urllib.error


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ET_TZ = timezone(timedelta(hours=-4))

# Live paper Alpaca creds load from the GITIGNORED project-root .mcp.json (the same
# file Claude Code loads the MCP servers from) -- NOT hard-coded. This guarantees the
# guard's keys can never drift from what the engine actually trades with, and keeps
# secrets out of committed source. 2026-06-21 readiness audit C1/P0-1: a hard-coded
# RETIRED Safe-1 key (PKGZIUWD...) made this guard return HTTP 401 on every Safe run,
# silently disabling the naked-order safety net on the live Safe account. See
# setup/scripts/alpaca_keys.py. Fail-loud: a missing key raises here (the wrapper logs
# it) rather than letting the guard run on stale creds.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from alpaca_keys import load_account_keys  # noqa: E402

ACCOUNT_KEYS: dict[str, tuple[str, str]] = load_account_keys()
ALPACA_BASE = "https://paper-api.alpaca.markets/v2"


def _request(endpoint: str, key: str, secret: str, method: str = "GET",
             data: dict | None = None, timeout: int = 10) -> dict | list | None:
    """Minimal REST client to avoid Alpaca SDK dependency."""
    url = f"{ALPACA_BASE}/{endpoint.lstrip('/')}"
    headers = {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
        except Exception:
            err_body = {"raw": str(e)}
        return {"_error": str(e), "_status": e.code, "_body": err_body}
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        return {"_error": str(e)}


def _is_spy_option(symbol: str) -> bool:
    """OPRA symbol format: SPY{YYMMDD}{C|P}{strike*1000:08d}, e.g. SPY260518C00740000."""
    return symbol.startswith("SPY") and len(symbol) >= 15 and symbol[9] in ("C", "P")


def _option_direction(symbol: str) -> str:
    """Returns 'long_call', 'long_put', or 'unknown'. Assumes long-only (no shorts)."""
    if not _is_spy_option(symbol):
        return "unknown"
    return {"C": "long_call", "P": "long_put"}.get(symbol[9], "unknown")


def audit_account(account_label: str, *, dry_run: bool = False) -> dict:
    """Run the audit for one account. Returns a structured report dict."""
    key, secret = ACCOUNT_KEYS[account_label]
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Pull positions
    positions = _request("positions", key, secret)
    if isinstance(positions, dict) and positions.get("_error"):
        return {
            "account": account_label,
            "ok": False,
            "error": f"positions fetch failed: {positions.get('_error')}",
            "checked_at_utc": now_iso,
        }
    if not isinstance(positions, list):
        positions = []

    # 2. Pull open orders
    orders = _request("orders?status=open&nested=true&limit=200", key, secret)
    if isinstance(orders, dict) and orders.get("_error"):
        return {
            "account": account_label,
            "ok": False,
            "error": f"orders fetch failed: {orders.get('_error')}",
            "checked_at_utc": now_iso,
        }
    if not isinstance(orders, list):
        orders = []

    # 3. Filter to SPY options only
    spy_positions = [p for p in positions if _is_spy_option(p.get("symbol", ""))]
    spy_orders = [o for o in orders if _is_spy_option(o.get("symbol", ""))]

    # 4. Identify "stop_loss" legs for each position symbol.
    # A bracket/oto produces nested legs. Walk all open orders, collect those whose
    # `order_type == "stop"` OR `stop_price is not None` AND match the position symbol.
    def _is_stop_order(o: dict) -> bool:
        if o.get("order_type") in ("stop", "stop_limit"):
            return True
        # Some MCP responses set stop_price without order_type=stop on the bracket leg
        if o.get("stop_price") and o.get("type") in ("stop", "stop_limit"):
            return True
        return False

    # Flatten nested legs (Alpaca returns legs under "legs" for bracket parents)
    def _all_legs(orders_list: list[dict]) -> list[dict]:
        flat: list[dict] = []
        for o in orders_list:
            flat.append(o)
            if isinstance(o.get("legs"), list):
                flat.extend(o["legs"])
        return flat

    all_orders_flat = _all_legs(spy_orders)
    stop_orders_by_symbol: dict[str, list[dict]] = {}
    for o in all_orders_flat:
        if _is_stop_order(o):
            sym = o.get("symbol", "")
            stop_orders_by_symbol.setdefault(sym, []).append(o)

    # 5. Check 1: NAKED FILLED POSITIONS (no open stop order)
    naked_positions: list[dict] = []
    for pos in spy_positions:
        sym = pos.get("symbol", "")
        qty = abs(int(float(pos.get("qty", 0))))
        if qty == 0:
            continue
        stops = stop_orders_by_symbol.get(sym, [])
        if not stops:
            naked_positions.append({
                "symbol": sym,
                "qty": qty,
                "side": pos.get("side"),
                "avg_entry_price": pos.get("avg_entry_price"),
                "current_price": pos.get("current_price"),
                "unrealized_pl": pos.get("unrealized_pl"),
                "direction": _option_direction(sym),
                "severity": "RED",
                "reason": "no open stop order found for filled option position (Rule 3 violation)",
            })

    # 6. Check 2: ORPHAN PARENT ORDERS (placed but no stop sibling AND not filled yet)
    orphan_parents: list[dict] = []
    canceled: list[dict] = []
    for o in spy_orders:
        # Only inspect TOP-LEVEL parent orders (not legs)
        # Identify "parent without sibling stop". This happens when `order_class="bracket"`
        # was attempted, fell back to `oto`, or was placed as `simple` due to MCP partial.
        order_class = o.get("order_class")
        legs = o.get("legs") or []
        has_stop_leg = any(_is_stop_order(leg) for leg in legs)
        status = o.get("status", "")
        # Already-filled parent without sibling stop = naked filled, covered by check 1
        # We care about unfilled-or-partially-filled parents that lack a stop sibling
        if status in ("filled", "canceled", "expired", "rejected"):
            continue
        # Check: if parent is a buy_to_open AND no stop leg exists AND no separate stop order targets this symbol
        side = o.get("side", "")
        symbol = o.get("symbol", "")
        external_stops = stop_orders_by_symbol.get(symbol, [])
        # External stops EXCLUDE this order's own legs
        external_stops_excluding_own = [s for s in external_stops if s.get("id") != o.get("id")
                                         and (s.get("parent_id") != o.get("id"))]
        if side == "buy" and not has_stop_leg and not external_stops_excluding_own:
            entry = {
                "order_id": o.get("id"),
                "symbol": symbol,
                "qty": o.get("qty"),
                "side": side,
                "status": status,
                "order_class": order_class,
                "submitted_at": o.get("submitted_at"),
                "limit_price": o.get("limit_price"),
                "severity": "AMBER",
                "reason": "open parent order with no stop leg / sibling stop",
            }
            orphan_parents.append(entry)
            if not dry_run:
                cancel_resp = _request(f"orders/{o['id']}", key, secret, method="DELETE", timeout=10)
                entry["canceled"] = (cancel_resp is None or not (isinstance(cancel_resp, dict) and cancel_resp.get("_error")))
                if entry["canceled"]:
                    canceled.append(entry)

    return {
        "account": account_label,
        "ok": True,
        "checked_at_utc": now_iso,
        "positions_checked": len(spy_positions),
        "open_orders_checked": len(spy_orders),
        "naked_positions": naked_positions,
        "orphan_parents": orphan_parents,
        "orphan_parents_canceled": canceled,
        "dry_run": dry_run,
    }


def _persist(reports: list[dict]) -> Path:
    """Append a single combined JSONL row + return path."""
    today = datetime.now(ET_TZ).date().isoformat()
    state_dir = PROJECT_ROOT / "automation" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    out = state_dir / f"atomic-bracket-guard-{today}.jsonl"
    record = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "reports": reports,
    }
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")
    return out


def _alert_status_md(reports: list[dict]) -> None:
    """Append a RED line to STATUS.md if any naked positions detected."""
    naked_total = sum(len(r.get("naked_positions", [])) for r in reports)
    if naked_total == 0:
        return
    status_path = PROJECT_ROOT / "automation" / "overnight" / "STATUS.md"
    if not status_path.exists():
        return
    now_et = datetime.now(ET_TZ).strftime("%Y-%m-%d %H:%M ET")
    details = []
    for r in reports:
        for np in r.get("naked_positions", []):
            details.append(f"{r['account']}:{np['symbol']} qty={np['qty']} entry={np.get('avg_entry_price')}")
    line = f"- [{now_et}] RED: atomic-bracket-guard found {naked_total} naked SPY 0DTE option position(s) [{', '.join(details)}]"
    with status_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", choices=["safe", "bold", "both"], default="both")
    parser.add_argument("--dry-run", action="store_true", help="Don't cancel orphans, just report")
    parser.add_argument("--silent", action="store_true", help="JSON only, no human stdout")
    args = parser.parse_args()

    targets = ["safe", "bold"] if args.account == "both" else [args.account]
    reports = [audit_account(a, dry_run=args.dry_run) for a in targets]

    out_path = _persist(reports)
    _alert_status_md(reports)

    naked_count = sum(len(r.get("naked_positions", [])) for r in reports)
    orphan_count = sum(len(r.get("orphan_parents", [])) for r in reports)
    canceled_count = sum(len(r.get("orphan_parents_canceled", [])) for r in reports)
    errors = [r for r in reports if not r.get("ok", False)]

    if args.silent:
        print(json.dumps({"naked": naked_count, "orphans": orphan_count,
                          "canceled": canceled_count, "errors": len(errors),
                          "path": str(out_path)}))
    else:
        print(f"=== ATOMIC BRACKET GUARD @ {datetime.now(timezone.utc).isoformat()} ===")
        for r in reports:
            if not r.get("ok"):
                print(f"  {r['account']:5s}: ERROR — {r.get('error')}")
                continue
            print(f"  {r['account']:5s}: positions={r['positions_checked']}  "
                  f"orders={r['open_orders_checked']}  "
                  f"naked={len(r['naked_positions'])}  "
                  f"orphans={len(r['orphan_parents'])}  "
                  f"canceled={len(r['orphan_parents_canceled'])}")
            for np in r["naked_positions"]:
                print(f"    RED: {np['symbol']} qty={np['qty']} entry={np['avg_entry_price']} "
                      f"unrealized={np.get('unrealized_pl')}")
            for op in r["orphan_parents"]:
                print(f"    AMBER: parent {op['order_id'][:8]} sym={op['symbol']} "
                      f"qty={op['qty']} class={op['order_class']} "
                      f"{'CANCELED' if op.get('canceled') else 'kept (dry-run)' if args.dry_run else 'CANCEL_FAILED'}")
        print(f"  state: {out_path}")

    # Exit 1 if there's a RED (naked filled position needing operator action)
    # Orphan cancellation is informational only — exit 0 if those were the only issue
    return 1 if naked_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())

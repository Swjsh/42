"""trade_today_watcher.py -- the standing "did the engine trade today" instrument (OP-33e).

J's #1 recurring question is "did it trade / did it fill." Answering it ad-hoc is the anti-pattern;
this is the standing surface that retires it. The SOURCE OF TRUTH for engine trades is Alpaca
get_orders, NOT decisions.jsonl (ENTER rows historically skipped the ledger -- wake-protocol
2026-05-13). This queries every account's Alpaca orders for TODAY's SPY-OPTION orders (excluding
J's manual crypto), splits them into FILLED vs PLACED-NOT-FILLED (the placement->fill gap), writes
a glanceable automation/state/trade-today.json, and LOUD-pings J once per new fill (flagged
FIRST ENGINE FILL EVER if it's the first). Dedup by order id. Notify-only, fail-open, $0.

Scheduled every ~2 min during RTH -> J is TOLD the moment the engine fills, without asking.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))
sys.path.insert(0, str(REPO / "setup" / "scripts"))
import fleet_broker as fb  # noqa: E402
from et_clock import et_today_str  # noqa: E402

STATE = REPO / "automation" / "state"
OUTBOX = STATE / "discord-outbox.jsonl"
TRADE_TODAY = STATE / "trade-today.json"
PINGED = STATE / "trade-today-pinged.json"
LIFETIME = STATE / "engine-lifetime-fills.json"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _is_spy_option(sym) -> bool:
    return isinstance(sym, str) and sym.startswith("SPY") and len(sym) >= 15


def classify_orders(orders) -> "tuple[list[dict], list[dict]]":
    """PURE: split today's SPY-OPTION orders into (filled, placed_not_filled). Crypto/stock and
    non-SPY are ignored. Filled = filled_qty>0 AND filled_avg_price>0. Testable (no network)."""
    filled: list[dict] = []
    unfilled: list[dict] = []
    for o in orders or []:
        sym = o.get("symbol", "")
        if not _is_spy_option(sym):
            continue
        try:
            fq = float(o.get("filled_qty") or 0)
            fp = float(o.get("filled_avg_price") or 0)
        except (TypeError, ValueError):
            fq = fp = 0.0
        rec = {"id": o.get("id"), "symbol": sym, "qty": fq, "price": fp,
               "side": o.get("side"), "status": o.get("status"), "filled_at": o.get("filled_at")}
        (filled if (fq > 0 and fp > 0) else unfilled).append(rec)
    return filled, unfilled


def _fetch_orders(creds: dict) -> list:
    try:
        ep = f"orders?status=all&after={et_today_str()}T00:00:00Z&limit=100"
        res = fb._request(creds, ep, method="GET")
        return res if isinstance(res, list) else []
    except Exception:
        return []


def main() -> int:
    creds_all = fb.load_creds()
    pinged = {}
    if PINGED.exists():
        try:
            pinged = json.loads(PINGED.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pinged = {}
    ever_filled = False
    if LIFETIME.exists():
        try:
            ever_filled = bool(json.loads(LIFETIME.read_text(encoding="utf-8")).get("ever_filled"))
        except (OSError, ValueError):
            ever_filled = False

    all_filled: list[dict] = []
    all_unfilled: list[dict] = []
    new: list[dict] = []
    for arm, creds in creds_all.items():
        f, u = classify_orders(_fetch_orders(creds))
        for x in f + u:
            x["arm"] = arm
        all_filled += f
        all_unfilled += u
        for x in f:
            if x["id"] and x["id"] not in pinged:
                new.append(x)
                pinged[x["id"]] = _now()

    TRADE_TODAY.write_text(json.dumps({
        "date": et_today_str(), "checked_at": _now(),
        "spy_fills_today": len(all_filled), "placed_not_filled_today": len(all_unfilled),
        "ever_filled": ever_filled or bool(new),
        "fills": all_filled, "unfilled": all_unfilled}, indent=2), encoding="utf-8")

    for x in new:
        first = "  <<< FIRST ENGINE FILL EVER!" if not ever_filled else ""
        msg = (f"ENGINE TRADE [{x['arm']}]: {x['symbol']} x{int(x['qty'])} @ ${x['price']:.2f} "
               f"{x.get('side')} ({x.get('filled_at', '')}){first}")
        with OUTBOX.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"content": "[TRADE] " + msg, "source": "trade_today_watcher",
                                 "queued_at": _now()}) + "\n")
        print("PINGED J:", msg)
        ever_filled = True

    if new and not LIFETIME.exists():
        LIFETIME.write_text(json.dumps({"ever_filled": True, "first_fill_at": _now()}), encoding="utf-8")
    PINGED.write_text(json.dumps(pinged), encoding="utf-8")
    print(f"[trade_today_watcher] SPY today: {len(all_filled)} FILLED, "
          f"{len(all_unfilled)} placed-not-filled; {len(new)} new ping(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

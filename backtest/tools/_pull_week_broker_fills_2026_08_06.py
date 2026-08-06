"""READ-ONLY puller: broker /v2/orders for 2026-08-04 / 2026-08-05 / 2026-08-06, all 5 fleet
arms, EVERY SPY option order (no strike filter -- LEVER-CATCAP needs the whole book of each
day, including the 2026-08-05 P00772000 put that stopped_then_paid_2026_08_04.py's 08-05
cross-check excluded because it hardcoded side="C").

fleet_broker.load_creds() takes NO arguments. GET only -- no placement, no mutation.
Writes a JSON cache to backtest/data/ for lever_catcap_2026_08_06.py to consume.

Run: backtest/.venv/Scripts/python.exe backtest/tools/_pull_week_broker_fills_2026_08_06.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))
import fleet_broker as fb  # noqa: E402

OUT = REPO / "backtest" / "data" / "_week_orders_2026_08_06.json"
ARMS = ["safe-2", "bold-2", "safe-3", "risky-1", "risky-3"]
DATES = ["2026-08-04", "2026-08-05", "2026-08-06"]
# SPY 0DTE OCC prefix for each date: SPY + YYMMDD
PREFIX = {d: "SPY" + d[2:4] + d[5:7] + d[8:10] for d in DATES}


def next_day(date_iso: str) -> str:
    import datetime as dt
    d = dt.date.fromisoformat(date_iso) + dt.timedelta(days=1)
    return d.isoformat()


def main() -> None:
    creds_all = fb.load_creds()
    out: dict = {}
    for date_iso in DATES:
        out[date_iso] = {}
        for arm in ARMS:
            creds = creds_all.get(arm)
            if not creds:
                out[date_iso][arm] = {"_error": "no creds"}
                continue
            params = (
                f"status=all&after={date_iso}T00:00:00-04:00"
                f"&until={next_day(date_iso)}T00:00:00-04:00"
                "&limit=500&direction=asc&nested=false"
            )
            res = fb._request(creds, f"orders?{params}", method="GET")
            if isinstance(res, dict) and res.get("_error"):
                out[date_iso][arm] = {"_error": res}
                continue
            rows = []
            for o in res if isinstance(res, list) else []:
                sym = str(o.get("symbol", ""))
                if not sym.startswith(PREFIX[date_iso]):
                    continue  # 0DTE SPY options for THIS date only
                if str(o.get("status")) != "filled":
                    continue
                rows.append({
                    "symbol": sym, "side": o.get("side"),
                    "filled_qty": o.get("filled_qty"),
                    "filled_avg_price": o.get("filled_avg_price"),
                    "status": o.get("status"), "order_type": o.get("type"),
                    "filled_at": o.get("filled_at"), "id": o.get("id"),
                })
            out[date_iso][arm] = {"n_orders_total": len(res) if isinstance(res, list) else None,
                                  "rows": rows}
            print(f"{date_iso} {arm}: {len(rows)} filled 0DTE SPY option orders", file=sys.stderr)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()

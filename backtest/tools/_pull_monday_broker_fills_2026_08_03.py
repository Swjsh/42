"""READ-ONLY puller: broker /v2/orders for 2026-08-03 (Monday), all 5 fleet arms, every
filled SPY 0DTE option order. Extends the catcap week book (_week_orders_2026_08_06.json,
which covers 08-04..06) to the FULL 4-session week the TP1-REACHABILITY lane mandates.

Same conventions as _pull_week_broker_fills_2026_08_06.py (the validated sibling):
fleet_broker.load_creds() takes NO arguments. GET only -- no placement, no mutation.

Run: backtest/.venv/Scripts/python.exe backtest/tools/_pull_monday_broker_fills_2026_08_03.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))
import fleet_broker as fb  # noqa: E402

OUT = REPO / "backtest" / "data" / "_week_orders_2026_08_03.json"
ARMS = ["safe-2", "bold-2", "safe-3", "risky-1", "risky-3"]
DATE = "2026-08-03"
PREFIX = "SPY" + DATE[2:4] + DATE[5:7] + DATE[8:10]


def main() -> None:
    creds_all = fb.load_creds()
    nxt = (dt.date.fromisoformat(DATE) + dt.timedelta(days=1)).isoformat()
    out: dict = {DATE: {}}
    for arm in ARMS:
        creds = creds_all.get(arm)
        if not creds:
            out[DATE][arm] = {"_error": "no creds"}
            continue
        params = (
            f"status=all&after={DATE}T00:00:00-04:00"
            f"&until={nxt}T00:00:00-04:00"
            "&limit=500&direction=asc&nested=false"
        )
        res = fb._request(creds, f"orders?{params}", method="GET")
        if isinstance(res, dict) and res.get("_error"):
            out[DATE][arm] = {"_error": res}
            continue
        rows = []
        for o in res if isinstance(res, list) else []:
            sym = str(o.get("symbol", ""))
            if not sym.startswith(PREFIX):
                continue
            if str(o.get("status")) != "filled":
                continue
            rows.append({
                "symbol": sym, "side": o.get("side"),
                "filled_qty": o.get("filled_qty"),
                "filled_avg_price": o.get("filled_avg_price"),
                "status": o.get("status"), "order_type": o.get("type"),
                "filled_at": o.get("filled_at"), "id": o.get("id"),
            })
        out[DATE][arm] = {"n_orders_total": len(res) if isinstance(res, list) else None,
                          "rows": rows}
        print(f"{DATE} {arm}: {len(rows)} filled 0DTE SPY option orders", file=sys.stderr)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()

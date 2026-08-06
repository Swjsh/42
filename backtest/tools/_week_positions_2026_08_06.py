"""Position builder for LEVER-CATCAP-2026-08-06 (prereg-lever-catcap-2026-08-06.json).

Turns the raw broker order rows from _pull_week_broker_fills_2026_08_06.py into ROUND-TRIP
POSITIONS, per arm per date, sequentially: a BUY opens a position; subsequent SELLs on the same
symbol reduce it until flat. Each position carries its real exit legs so the CONTROL cell can
reproduce history EXACTLY BY CONSTRUCTION (never by an approximate re-walk).

Strategy + trigger_level attribution comes from each arm's OWN decisions.jsonl, never guessed.

Importable (no side effects at import). Read-only.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
ORDERS = REPO / "backtest" / "data" / "_week_orders_2026_08_06.json"
FLEET_STATE = REPO / "automation" / "state" / "fleet"

ARMS = ["safe-2", "bold-2", "safe-3", "risky-1", "risky-3"]


def _et(iso_utc: str) -> dt.datetime:
    """Broker filled_at is UTC (Z). The whole 2026-08-04..06 window is EDT -> ET = UTC-4."""
    s = iso_utc.replace("Z", "+00:00")
    d = dt.datetime.fromisoformat(s)
    if d.tzinfo is not None:
        d = d.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return d - dt.timedelta(hours=4)


def build_positions(orders_json: Optional[dict] = None) -> dict:
    """-> {date_iso: {arm: [position, ...]}}, each position sequential and flat-closed."""
    data = orders_json if orders_json is not None else json.loads(ORDERS.read_text(encoding="utf-8"))
    out: dict = {}
    for date_iso, arms in data.items():
        out[date_iso] = {}
        for arm in ARMS:
            blob = arms.get(arm) or {}
            rows = blob.get("rows") or []
            rows = sorted(rows, key=lambda r: (r["filled_at"], r["id"]))
            positions: list[dict] = []
            open_pos: Optional[dict] = None
            for r in rows:
                qty = int(float(r["filled_qty"]))
                px = float(r["filled_avg_price"])
                ts = _et(r["filled_at"])
                if qty <= 0:
                    continue
                if r["side"] == "buy":
                    if open_pos is not None and open_pos["symbol"] == r["symbol"]:
                        # add-on to an open position: this repo forbids adding (Rule 4); if it
                        # ever appears, surface it loudly rather than silently averaging.
                        open_pos["adds"].append((ts.strftime("%H:%M:%S"), px, qty))
                        continue
                    if open_pos is not None:
                        # a new symbol while still open -> two concurrent positions. Never
                        # observed on these arms; flagged, not silently merged.
                        open_pos["overlap_flag"] = True
                        positions.append(open_pos)
                    open_pos = {
                        "arm": arm, "date": date_iso, "symbol": r["symbol"],
                        "side": "P" if "P00" in r["symbol"] else "C",
                        "entry_et": ts.strftime("%H:%M:%S"), "premium": px, "qty": qty,
                        "exit_legs": [], "adds": [], "overlap_flag": False,
                    }
                else:  # sell
                    if open_pos is None:
                        continue
                    open_pos["exit_legs"].append((ts.strftime("%H:%M:%S"), px, qty))
                    filled = sum(q for _, _, q in open_pos["exit_legs"])
                    if filled >= open_pos["qty"]:
                        positions.append(open_pos)
                        open_pos = None
            if open_pos is not None:
                positions.append(open_pos)
            for p in positions:
                p["realized_pnl"] = round(
                    sum((px - p["premium"]) * q * 100.0 for _, px, q in p["exit_legs"]), 2)
            out[date_iso][arm] = positions
    return out


def attach_strategy(positions: dict) -> dict:
    """Attach strategy + trigger_level from each arm's OWN decisions.jsonl fill records."""
    idx: dict[tuple, dict] = {}
    for arm in ARMS:
        f = FLEET_STATE / arm / "decisions.jsonl"
        if not f.exists():
            f = FLEET_STATE / "decisions" / f"{arm}.jsonl"
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            sym = d.get("symbol") or d.get("contract") or (d.get("order") or {}).get("symbol")
            if not sym:
                continue
            strat = d.get("strategy") or d.get("setup_strategy")
            tl = d.get("trigger_level")
            if strat is None and tl is None:
                continue
            ts = str(d.get("ts") or d.get("timestamp_et") or "")
            key = (arm, str(sym), ts[:10])
            prev = idx.get(key)
            if prev is None or (prev.get("trigger_level") is None and tl is not None):
                idx[key] = {"strategy": strat, "trigger_level": tl, "ts": ts}
    for date_iso, arms in positions.items():
        for arm, plist in arms.items():
            for p in plist:
                hit = idx.get((arm, p["symbol"], date_iso))
                p["strategy"] = (hit or {}).get("strategy")
                p["trigger_level"] = (hit or {}).get("trigger_level")
    return positions


if __name__ == "__main__":
    pos = attach_strategy(build_positions())
    for date_iso in sorted(pos):
        tot = 0.0
        n = 0
        for arm in ARMS:
            for p in pos[date_iso][arm]:
                tot += p["realized_pnl"]
                n += 1
        print(f"{date_iso}: n={n} positions  realized=${tot:,.2f}")
        for arm in ARMS:
            a = sum(p["realized_pnl"] for p in pos[date_iso][arm])
            if pos[date_iso][arm]:
                print(f"    {arm:8s} n={len(pos[date_iso][arm]):2d} ${a:,.2f}"
                      f"  strat={sorted({str(p.get('strategy')) for p in pos[date_iso][arm]})}"
                      f"  tl_missing={sum(1 for p in pos[date_iso][arm] if p.get('trigger_level') is None)}")

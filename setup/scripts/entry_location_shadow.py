"""Entry-location SHADOW counter -- record where every live entry sat in the day's range.

WHY THIS EXISTS. The ENTRY-LOCATION-GATE study (2026-08-14) returned a NULL against its
pre-registered metric, and the bull side came back NOT-RUN at n=29 -- the largest cell gated 21
trades against a n>=30 floor. That is a DATA shortage, not an analysis failure: no cleverness
fixes n=29. The engine meanwhile has NO location feature at all (the 2026-08-14 loser and the
2026-08-13 winner were byte-identical on every logged field at entry), so nothing accumulates
unless something records it.

This records it. Every live entry gets its causal location features appended to a shadow
ledger; a tally reports how far each cell is from decidable. It ARMS NOTHING and VETOES
NOTHING -- it is the measure-forward half of the study's own conclusion, and it also closes the
unmet half of prereg G3 (the 2026-08-13 winner / 2026-08-14 loser anchors fall outside the
replay window and get scored here the moment they are in-population).

CAUSALITY (C6). Features come from bars STRICTLY BEFORE the entry bar, entry price is the entry
bar's open -- byte-identical definitions to entry_location_gate_2026_08_14.features(), imported
rather than re-implemented so the shadow population and the study population can never drift
apart (the single most likely way this becomes unusable later).

Read-only w.r.t. trading state. Idempotent per (date, arm, symbol, entry_time). Exit 0 always.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
OUT_DIR = REPO / "analysis" / "entry-quality"
LEDGER = OUT_DIR / "entry-location-shadow.jsonl"
TALLY = STATE / "entry-location-shadow-tally.json"

sys.path.insert(0, str(REPO / "backtest" / "autoresearch"))
sys.path.insert(0, str(REPO / "setup" / "scripts"))

# Import the STUDY's own feature function -- never a second implementation (drift-proof).
from entry_location_gate_2026_08_14 import (  # noqa: E402
    MIN_CELL_N, PROX_BANDS, RUN_BANDS, features, gated,
)

try:
    from et_clock import et_now  # noqa: E402
except Exception:  # noqa: BLE001
    et_now = None

ARMS = ("safe-2", "safe-3", "bold-2", "risky-1", "risky-3")


def _creds() -> dict:
    try:
        return json.loads((STATE / "fleet" / "secrets.json").read_text(encoding="utf-8"))["accounts"]
    except (OSError, ValueError, KeyError):
        return {}


def _get(url: str, cred: dict, timeout: int = 25) -> Any:
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": cred["key"], "APCA-API-SECRET-KEY": cred["secret"]})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def spy_bars(cred: dict, date: str) -> list[dict]:
    """5m RTH bars for `date`, in the study's bar shape."""
    url = (f"https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe=5Min"
           f"&start={date}T13:30:00Z&end={date}T20:05:00Z&limit=200&feed=iex")
    out = []
    for b in _get(url, cred).get("bars", []):
        hh = int(b["t"][11:13]) - 4          # UTC -> ET (feed is UTC; ET offset per et_frame)
        out.append({"t": f"{hh:02d}:{b['t'][14:16]}", "o": b["o"], "h": b["h"],
                    "l": b["l"], "c": b["c"]})
    return sorted(out, key=lambda b: b["t"])


def round_trips(cred: dict, date: str) -> list[dict]:
    """FIFO-matched SPY option round trips for one arm/day (buys matched to sells)."""
    # DATE BOUNDING (bug caught 2026-08-14 before any conclusion was drawn from it):
    # `after=` is a LOWER bound only -- querying 2026-08-13 returned 08-14's fills too, and they
    # were appended under date=2026-08-13. Detected by reading the output against a known fact
    # (08-13's entries were at 09:51, yet 09:46 rows appeared) rather than by trusting the
    # query. Same class as the OPRA endpoint's unbounded-range trap. The API's `until` is not
    # relied on either: every fill is re-checked against the requested ET date locally, so a
    # server-side range quirk cannot contaminate the ledger again.
    url = (f"https://paper-api.alpaca.markets/v2/orders?status=all"
           f"&after={date}T00:00:00Z&until={date}T23:59:59Z&limit=200")

    def _et_date(iso: str) -> str:
        import datetime as dt
        from zoneinfo import ZoneInfo
        return (dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
                .astimezone(ZoneInfo("America/New_York")).date().isoformat())

    fills = [o for o in _get(url, cred)
             if o["symbol"].startswith("SPY") and float(o.get("filled_qty") or 0) > 0
             and o.get("filled_at") and _et_date(o["filled_at"]) == date]
    fills.sort(key=lambda o: o.get("filled_at") or "")
    books: dict[str, dict] = defaultdict(lambda: {"lots": []})
    trips = []
    for f in fills:
        sym, q, px = f["symbol"], int(float(f["filled_qty"])), float(f["filled_avg_price"])
        if f["side"] == "buy":
            books[sym]["lots"].append({"q": q, "rem": q, "px": px, "t": f["filled_at"], "exits": []})
        else:
            need = q
            for lot in books[sym]["lots"]:
                if lot["rem"] <= 0 or need <= 0:
                    continue
                take = min(lot["rem"], need)
                lot["rem"] -= take
                need -= take
                lot["exits"].append((take, px))
    for sym, bk in books.items():
        for lot in bk["lots"]:
            if not lot["exits"]:
                continue
            proc = sum(t * p for t, p in lot["exits"])
            trips.append({
                "symbol": sym, "side": "P" if "P00" in sym else "C",
                "qty": lot["q"], "entry_px_premium": lot["px"],
                "entry_time_et": f"{int(lot['t'][11:13]) - 4:02d}:{lot['t'][14:16]}",
                "dollar_pnl": round((proc - lot["q"] * lot["px"]) * 100, 2),
            })
    return trips


def _bar_aligned(hhmm: str) -> str:
    h, m = int(hhmm[:2]), int(hhmm[3:5])
    return f"{h:02d}:{(m // 5) * 5:02d}"


def collect(date: str) -> list[dict]:
    creds = _creds()
    if not creds:
        return []
    ref = creds.get("safe-2") or next(iter(creds.values()))
    today = spy_bars(ref, date)
    # prior trading day: walk back up to 5 calendar days until bars exist
    import datetime as dt
    prior = None
    d0 = dt.date.fromisoformat(date)
    for back in range(1, 6):
        cand = (d0 - dt.timedelta(days=back)).isoformat()
        pb = spy_bars(ref, cand)
        if pb:
            prior = pb
            break
    rows = []
    for arm in ARMS:
        if arm not in creds:
            continue
        try:
            trips = round_trips(creds[arm], date)
        except Exception as e:  # noqa: BLE001 -- one arm's broker error must not lose the rest
            rows.append({"date": date, "arm": arm, "error": f"{type(e).__name__}"})
            continue
        for t in trips:
            f = features(today, prior, _bar_aligned(t["entry_time_et"]))
            if f is None:
                rows.append({"date": date, "arm": arm, "symbol": t["symbol"],
                             "entry_time_et": t["entry_time_et"],
                             "skipped": "no causal features (too few prior bars / range < 0.25)"})
                continue
            near = f["dist_from_high_frac"] if t["side"] == "C" else f["dist_from_low_frac"]
            rows.append({
                "date": date, "arm": arm, "symbol": t["symbol"], "side": t["side"],
                "entry_time_et": t["entry_time_et"], "qty": t["qty"],
                "dollar_pnl": t["dollar_pnl"],
                "dist_from_extreme_frac": round(near, 4),
                "range_pts": round(f["range_pts"], 2),
                "prior_day_run_pts": None if f["prior_day_run_pts"] is None else round(f["prior_day_run_pts"], 2),
                "n_prior_bars": f["n_prior_bars"],
                "cells_gated": [f"prox<={p:.2f}" for p in PROX_BANDS
                                if gated(t["side"], f, p, None)],
            })
    return rows


def append(rows: list[dict]) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    seen = set()
    if LEDGER.exists():
        for line in LEDGER.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            seen.add((r.get("date"), r.get("arm"), r.get("symbol"), r.get("entry_time_et")))
    added = 0
    with LEDGER.open("a", encoding="utf-8") as f:
        for r in rows:
            k = (r.get("date"), r.get("arm"), r.get("symbol"), r.get("entry_time_et"))
            if k in seen:
                continue
            f.write(json.dumps(r) + "\n")
            seen.add(k)
            added += 1
    return added


def tally() -> dict:
    rows = []
    if LEDGER.exists():
        for line in LEDGER.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("dist_from_extreme_frac") is not None:
                rows.append(r)
    out: dict[str, Any] = {
        "_doc": ("Shadow-only. Records entry location; arms nothing. Cells become DECIDABLE at "
                 f"n>={MIN_CELL_N} gated, matching the study's floor."),
        "study": "analysis/recommendations/ENTRY-LOCATION-GATE-2026-08-14.md",
        "n_rows": len(rows), "cells": {},
    }
    for side in ("C", "P"):
        srows = [r for r in rows if r.get("side") == side]
        for p in PROX_BANDS:
            key = f"{side}|prox<={p:.2f}"
            g = [r for r in srows if f"prox<={p:.2f}" in (r.get("cells_gated") or [])]
            out["cells"][key] = {
                "n_gated": len(g), "n_side_total": len(srows),
                "needed_for_decidable": max(0, MIN_CELL_N - len(g)),
                "decidable": len(g) >= MIN_CELL_N,
                "gated_pnl": round(sum(r["dollar_pnl"] for r in g), 2),
                "gated_win_rate": (round(sum(1 for r in g if r["dollar_pnl"] > 0) / len(g), 4)
                                   if g else None),
            }
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    date = sys.argv[1] if len(sys.argv) > 1 else (
        et_now().strftime("%Y-%m-%d") if et_now else None)
    if not date:
        print("no date and no et_clock -- pass YYYY-MM-DD")
        return 0
    try:
        rows = collect(date)
        added = append(rows)
    except Exception as e:  # noqa: BLE001 -- a shadow counter must never break its caller
        print(f"collect failed ({type(e).__name__}: {e}) -- tally unchanged")
        added = 0
    t = tally()
    TALLY.write_text(json.dumps(t, indent=2), encoding="utf-8")
    print(f"entry-location shadow: {date} -> +{added} row(s), ledger n={t['n_rows']}")
    for k, v in t["cells"].items():
        state = "DECIDABLE" if v["decidable"] else f"needs {v['needed_for_decidable']} more"
        wr = f"{v['gated_win_rate']:.1%}" if v["gated_win_rate"] is not None else "-"
        print(f"   {k:<20} gated={v['n_gated']:<3} ({state})  pnl=${v['gated_pnl']:<9} wr={wr}")
    print(f"\nwrote {TALLY.relative_to(REPO).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
"""trailing_pnl.py -- THE STANDING ANSWER TO "HOW HAVE WE BEEN DOING?"

WHY THIS EXISTS (J, 2026-08-27): asked "we made money today, but why did we lose the
last couple days -- is it the market or the engine?" Answering it required hand-rolling
a 14-day FIFO at the prompt, because `day_summary.py` is SINGLE-DAY by construction and
nothing else emits a per-arm trend. OP-33(e): a question that needs a hand-rolled script
is a MISSING INSTRUMENT, not a query. This is the instrument.

SCOPE -- what this answers that day_summary.py cannot:
  * per-day x per-arm realized P&L across a trailing window
  * the green/red day ASYMMETRY (avg win day vs avg loss day) -- the number that decides
    whether "big days make up for bad days" is a plan or a trap
  * SAT-OUT days (engine placed nothing) separated from TRADED-AND-LOST days, so a quiet
    tape is never mistaken for a bleeding engine
  * concentration: how much of the window's net lives in the top-decile closes (this
    engine's edge is a RIGHT TAIL -- see LESSONS C3/C30 and the 2026-08-18 finding)

REUSE, NOT A SECOND FIFO (C14): round trips come from `fleet.fills_fifo.mine_real_arm_fills`
-- the ONE reconstructor, which already carries the same-day-re-entry flush fix. Do not
add a local FIFO here; if the counting rule changes it changes THERE.

STDLIB ONLY. $0. Read-only: never places, cancels, or writes engine state.

MEASUREMENT ONLY. Nothing here gates a trade or edits params.
"""
from __future__ import annotations

import argparse
import datetime
import json
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]          # anchor to __file__ (C9), never cwd
sys.path.insert(0, str(REPO / "automation" / "state"))

from fleet.fills_fifo import mine_real_arm_fills     # noqa: E402  the ONE reconstructor

ACCOUNTS = REPO / "automation" / "state" / "fleet" / "accounts.json"
CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"
OUT = REPO / "automation" / "state" / "trailing-pnl.json"


def active_arms() -> list[str]:
    """Real-fills arms only. A sim/shadow arm's P&L is NEVER book evidence."""
    doc = json.loads(ACCOUNTS.read_text(encoding="utf-8"))
    return [a["id"] for a in doc.get("arms", [])
            if a.get("status") == "active" and a.get("fidelity") == "real_fills"]


def placements_by_day() -> Counter:
    """PLACED actions per ET day -- distinguishes 'sat out' from 'traded and lost'."""
    placed: Counter = Counter()
    if not CORE_DECISIONS.exists():
        return placed
    with CORE_DECISIONS.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue          # a malformed row is skipped, never counted as zero
            ts = row.get("ts_et") or ""
            if len(ts) >= 10 and row.get("action") == "PLACED":
                placed[ts[:10]] += 1
    return placed


def build(days: int) -> dict:
    arms = active_arms()
    if not arms:
        raise SystemExit("FAIL: no active real_fills arms in accounts.json -- refusing to "
                         "report a book number off an empty roster.")

    trips = {a: mine_real_arm_fills(a) for a in arms}
    cell: dict = defaultdict(float)
    per_day_closes: dict = defaultdict(list)
    for arm, rows in trips.items():
        for t in rows:
            cell[(t["date"], arm)] += t["real_pnl"]
            per_day_closes[t["date"]].append(t["real_pnl"])

    all_days = sorted(per_day_closes)
    if not all_days:
        raise SystemExit("FAIL: zero closed round trips in the ledger -- nothing to report.")
    window = all_days[-days:]
    placed = placements_by_day()

    rows = []
    for d in window:
        closes = per_day_closes[d]
        rows.append({
            "date": d,
            "net": round(sum(closes), 2),
            "by_arm": {a: round(cell[(d, a)], 2) for a in arms if (d, a) in cell},
            "n_closes": len(closes),
            "n_placed": placed.get(d, 0),
            "win_rate": round(sum(1 for c in closes if c > 0) / len(closes), 3),
            # A day the engine never entered is a DECISION, not a drawdown (J 2026-08-12:
            # "sitting out is a valid day"). Flag it so a quiet tape reads as quiet.
            "sat_out": placed.get(d, 0) == 0,
        })

    green = [r for r in rows if r["net"] > 0]
    red = [r for r in rows if r["net"] < 0]
    closes = [c for d in window for c in per_day_closes[d]]
    closes_sorted = sorted(closes)
    k = max(1, len(closes_sorted) // 10)
    top_decile = closes_sorted[-k:]
    net = sum(closes)
    avg_green = st.mean([r["net"] for r in green]) if green else None
    avg_red = st.mean([r["net"] for r in red]) if red else None

    return {
        "schema": "trailing-pnl-v1",
        "generated_at_et": datetime.datetime.now().isoformat(timespec="seconds"),
        "window": {"from": window[0], "to": window[-1], "sessions": len(window)},
        "arms": arms,
        "net": round(net, 2),
        "n_closes": len(closes),
        "win_rate": round(sum(1 for c in closes if c > 0) / len(closes), 3) if closes else None,
        "asymmetry": {
            "green_days": len(green),
            "red_days": len(red),
            "avg_green_day": round(avg_green, 2) if avg_green is not None else None,
            "avg_red_day": round(avg_red, 2) if avg_red is not None else None,
            # >1.0 means the average losing day is BIGGER than the average winning day --
            # the state in which "big days make up for it" is arithmetically false.
            "red_over_green": (round(abs(avg_red) / avg_green, 2)
                               if avg_green and avg_red else None),
        },
        "concentration": {
            "top_decile_closes": k,
            "top_decile_pnl": round(sum(top_decile), 2),
            "net_without_top_decile": round(net - sum(top_decile), 2),
            "note": "edge is a RIGHT TAIL -- see how little survives removing the top decile",
        },
        "sat_out_days": [r["date"] for r in rows if r["sat_out"]],
        "days": rows,
    }


def render(rep: dict) -> str:
    arms = rep["arms"]
    out = [f"TRAILING P&L  {rep['window']['from']} -> {rep['window']['to']}  "
           f"({rep['window']['sessions']} sessions, real fills)", ""]
    out.append(f"{'DATE':<12}" + "".join(f"{a:>10}" for a in arms)
               + f"{'BOOK':>10}{'n':>5}{'WR':>7}  flag")
    for r in rep["days"]:
        line = f"{r['date']:<12}"
        for a in arms:
            v = r["by_arm"].get(a)
            line += f"{v:>10,.0f}" if v is not None else f"{'-':>10}"
        flag = "SAT OUT" if r["sat_out"] else ""
        out.append(line + f"{r['net']:>10,.0f}{r['n_closes']:>5}"
                          f"{r['win_rate'] * 100:>6.0f}%  {flag}")
    a = rep["asymmetry"]
    c = rep["concentration"]
    out += ["",
            f"NET ${rep['net']:,.0f} over {rep['n_closes']} closes  "
            f"WR {rep['win_rate'] * 100:.0f}%",
            f"green {a['green_days']}d avg ${a['avg_green_day']:,.0f}  |  "
            f"red {a['red_days']}d avg ${a['avg_red_day']:,.0f}  |  "
            f"red/green {a['red_over_green']}x",
            f"top decile ({c['top_decile_closes']} closes) = ${c['top_decile_pnl']:,.0f}  "
            f"-- net without them ${c['net_without_top_decile']:,.0f}"]
    if rep["sat_out_days"]:
        out.append(f"sat out (engine placed nothing): {', '.join(rep['sat_out_days'])}")
    if a["red_over_green"] and a["red_over_green"] > 1.0:
        out += ["",
                "*** ASYMMETRY INVERTED: the average LOSING day is bigger than the average "
                "WINNING day. Bigger winners cannot fix this; smaller losers can."]
    return "\n".join(out)


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description="Trailing per-day per-arm realized P&L.")
    ap.add_argument("--days", type=int, default=14, help="trailing sessions (default 14)")
    ap.add_argument("--json", action="store_true", help="emit the report as JSON")
    ap.add_argument("--write", action="store_true",
                    help="also write automation/state/trailing-pnl.json")
    args = ap.parse_args(argv)

    rep = build(args.days)
    print(json.dumps(rep, indent=2) if args.json else render(rep))
    if args.write:
        OUT.write_text(json.dumps(rep, indent=2), encoding="utf-8")
        print(f"\nwrote {OUT.relative_to(REPO)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

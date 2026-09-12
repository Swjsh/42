"""Trigger-anchor level-class read (ratifying instrument for
analysis/recommendations/prereg-trigger-anchor-level-class-2026-09-11.md).

Joins every fill in journal/trades.csv (all arms) to the core ENTER tick fired within
+-2 minutes of its entry time in automation/state/core-decisions.jsonl, takes that tick's
conviction.matched_level_label as the trigger anchor, and prints signals / legs / P&L per
anchor CLASS. One table. No side effects. Run on demand:

    backtest/.venv/Scripts/python.exe backtest/tools/trigger_anchor_class_read.py \
        --since 2026-09-14 --until 2026-09-28

Classes: SWING (INTRADAY_SWING_*), STRUCT (PRIOR_DAY_* / INTRADAY_PMH|PML|RTH_*),
SHELF (SHELF_*), MEMORY (MEMORY_*), NONE (no named level; ribbon-only rejection).
A "signal" is one (date, 3-minute entry slot) across all arms; legs are CSV rows.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "automation" / "state" / "core-decisions.jsonl"
TRADES = REPO / "journal" / "trades.csv"


def _cls(label: str | None) -> str:
    if not label:
        return "NONE"
    if label.startswith("INTRADAY_SWING"):
        return "SWING"
    if label.startswith("PRIOR_DAY") or label.startswith("INTRADAY_"):
        return "STRUCT"
    if label.startswith("SHELF"):
        return "SHELF"
    if label.startswith("MEMORY"):
        return "MEMORY"
    return "OTHER"


def _enter_ticks(since: str, until: str) -> dict[tuple[str, str], str | None]:
    out: dict[tuple[str, str], str | None] = {}
    with LEDGER.open(encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            head = line[:60]
            if '"ts_et": "' not in head and '"ts_et":"' not in head:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = str(row.get("ts_et", ""))
            day = ts[:10]
            if day < since or day > until or not str(row.get("verdict", "")).startswith("ENTER"):
                continue
            conv = row.get("conviction") or {}
            label = conv.get("matched_level_label") if isinstance(conv, dict) else None
            out.setdefault((day, ts[11:16]), label)
    return out


def read(since: str, until: str) -> dict:
    ticks = _enter_ticks(since, until)
    per_class = collections.defaultdict(lambda: {"legs": 0, "wins": 0, "pnl": 0.0,
                                                  "signals": collections.defaultdict(float)})
    unmatched = 0
    with TRADES.open(encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            day = row["date"]
            if day < since or day > until:
                continue
            try:
                t0 = datetime.strptime(row["time_entry"][:5], "%H:%M")
                pnl = float(row["dollar_pnl"] or 0)
            except ValueError:
                continue
            hit = None
            for off in (0, -1, 1, 2, -2):
                key = (day, (t0 + timedelta(minutes=off)).strftime("%H:%M"))
                if key in ticks:
                    hit = ticks[key]
                    break
            if hit is None and not any((day, (t0 + timedelta(minutes=o)).strftime("%H:%M")) in ticks
                                       for o in (0, -1, 1, 2, -2)):
                unmatched += 1
                continue
            bucket = per_class[_cls(hit)]
            bucket["legs"] += 1
            bucket["wins"] += pnl > 0
            bucket["pnl"] += pnl
            slot = f"{day} {(t0.hour * 60 + t0.minute) // 3}"
            bucket["signals"][slot] += pnl
    return {"since": since, "until": until, "unmatched_legs": unmatched,
            "classes": {k: {"signals": len(v["signals"]), "legs": v["legs"], "wins": v["wins"],
                            "pnl": round(v["pnl"], 2),
                            "signal_pnls": sorted(round(x) for x in v["signals"].values())}
                        for k, v in per_class.items()}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True)
    ap.add_argument("--until", default="2099-12-31")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    res = read(args.since, args.until)
    if args.json:
        print(json.dumps(res, indent=1))
        return 0
    print(f"trigger-anchor class read {res['since']}..{res['until']}  (unmatched legs: {res['unmatched_legs']})")
    print(f"{'class':8s} {'signals':>7s} {'legs':>5s} {'WR%':>5s} {'P&L':>9s}  signal P&Ls (sorted)")
    for name, c in sorted(res["classes"].items(), key=lambda kv: kv[1]["pnl"]):
        wr = (c["wins"] / c["legs"] * 100) if c["legs"] else 0
        print(f"{name:8s} {c['signals']:7d} {c['legs']:5d} {wr:5.0f} {c['pnl']:+9.0f}  {c['signal_pnls']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

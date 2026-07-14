"""Ad hoc artifact-hunt on the ONE PASS cell from trendline_fade_battery.py
(F3_fade_low_volume::body::resistance(fade-of-bullish)). NOT part of the frozen pipeline --
does not change any variant/threshold/null definition, just re-derives per-trade rows for
sub-window stability + date-concentration checks before this cell gets reported as ship-ready.
Read-only reuse of trendline_fade_battery.py's own functions.
"""
from __future__ import annotations
import datetime as dt
import json
import sys
from pathlib import Path
from collections import defaultdict

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import trendline_fade_battery as fb  # noqa: E402

DS_PATH = REPO / "analysis" / "trendlines" / "break-dataset.jsonl"

print("loading records...")
records = []
with DS_PATH.open(encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line:
            records.append(json.loads(line))

print("loading day bars...")
day_bars_by_date = fb.load_all_day_bars()

episodes_by_variant = fb.build_episodes(records, day_bars_by_date)
eps = [e for e in episodes_by_variant["F3_fade_low_volume"] if e.family == "body" and e.kind == "resistance"]
print(f"n episodes for cell: {len(eps)}")

trades = []
for ep in eps:
    r = fb.replay_episode(ep)
    if r is not None:
        trades.append(r)

print(f"n trades replayed: {len(trades)}")

# Monthly buckets
by_month = defaultdict(list)
for t in trades:
    ym = t["date"][:7]
    by_month[ym].append(t["pnl"])

print("\n=== Monthly expectancy (n, total, mean) ===")
for ym in sorted(by_month.keys()):
    pnls = by_month[ym]
    print(f"{ym}: n={len(pnls):4d} total={sum(pnls):>12,.0f} mean={sum(pnls)/len(pnls):>8.2f}")

# Quarterly buckets
def quarter(ym):
    y, m = ym.split("-")
    q = (int(m) - 1) // 3 + 1
    return f"{y}-Q{q}"

by_q = defaultdict(list)
for t in trades:
    by_q[quarter(t["date"][:7])].append(t["pnl"])

print("\n=== Quarterly expectancy ===")
for q in sorted(by_q.keys()):
    pnls = by_q[q]
    print(f"{q}: n={len(pnls):4d} total={sum(pnls):>12,.0f} mean={sum(pnls)/len(pnls):>8.2f}")

# Date concentration
by_date = defaultdict(list)
for t in trades:
    by_date[t["date"]].append(t["pnl"])
date_totals = [(d, sum(p)) for d, p in by_date.items()]
date_totals.sort(key=lambda x: -x[1])
total_pnl = sum(t["pnl"] for t in trades)
print(f"\n=== Date concentration === total_pnl={total_pnl:,.0f} n_unique_dates={len(by_date)} of {len(trades)} trades")
top10 = date_totals[:10]
print("Top 10 days by pnl:")
for d, p in top10:
    print(f"  {d}: {p:>10,.0f} pnl ({100.0*p/total_pnl:.1f}% of total), n_trades={len(by_date[d])}")
top10_sum = sum(p for _, p in top10)
print(f"Top 10 days = {100.0*top10_sum/total_pnl:.1f}% of total pnl")

# OOS-only sub-window check (2026-01-01+)
oos_trades = [t for t in trades if t["date"] >= "2026-01-01"]
oos_by_month = defaultdict(list)
for t in oos_trades:
    oos_by_month[t["date"][:7]].append(t["pnl"])
print(f"\n=== OOS-only monthly (n_oos={len(oos_trades)}) ===")
n_pos_months = 0
n_months = 0
for ym in sorted(oos_by_month.keys()):
    pnls = oos_by_month[ym]
    mean = sum(pnls)/len(pnls)
    n_months += 1
    if mean > 0:
        n_pos_months += 1
    print(f"{ym}: n={len(pnls):4d} total={sum(pnls):>12,.0f} mean={mean:>8.2f}")
print(f"\npositive months in OOS: {n_pos_months}/{n_months}")

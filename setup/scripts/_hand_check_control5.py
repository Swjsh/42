"""One-off hand-check (C6): recompute PREREG-TIGHT-LADDER-2026-08-28 Control #5
(-$400/arm/day realized stop) directly from journal/trades.csv, independent of the
prereg's own prose numbers. Method: group trades.csv rows by (date, account_id,
time_entry) into one 'entry' (so TP1+runner legs count once, matching the prereg's
own stated grouping), sum dollar_pnl per entry, then walk each (date, account_id) in
time_entry order accumulating a running realized total; once the running total (BEFORE
the current entry) is <= -400, every subsequent entry that day/arm is 'blocked'.
Window: 2026-08-01..2026-09-04 inclusive, matching the prereg's stated replay window.
"""
import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CSV = REPO / "journal" / "trades.csv"

START = "2026-08-01"
END = "2026-09-04"

rows = []
with CSV.open(encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        d = r.get("date", "")
        if not (START <= d <= END):
            continue
        try:
            pnl = float(r.get("dollar_pnl") or 0)
        except ValueError:
            pnl = 0.0
        rows.append((d, r.get("account_id", ""), r.get("time_entry", ""), pnl))

# group into entries
entries = {}
for d, acct, t_entry, pnl in rows:
    key = (d, acct, t_entry)
    entries.setdefault(key, 0.0)
    entries[key] += pnl

# order entries per (date, acct) by time_entry
by_arm_day = {}
for (d, acct, t_entry), pnl in entries.items():
    by_arm_day.setdefault((d, acct), []).append((t_entry, pnl))

blocked = []
for (d, acct), lst in by_arm_day.items():
    lst.sort(key=lambda x: x[0])
    running = 0.0
    for t_entry, pnl in lst:
        if running <= -400:
            blocked.append((d, acct, t_entry, pnl))
        running += pnl

n = len(blocked)
net = sum(b[3] for b in blocked)
winners = [b for b in blocked if b[3] > 0]
losers = [b for b in blocked if b[3] < 0]
fire_days = sorted(set(b[0] for b in blocked))

print(f"n_blocked_entries={n}")
print(f"net_pnl_of_blocked_entries={round(net, 2)}")
print(f"winners={len(winners)} sum={round(sum(b[3] for b in winners), 2)}")
print(f"losers={len(losers)} sum={round(sum(b[3] for b in losers), 2)}")
print(f"fire_days={fire_days}")
for b in blocked:
    print(" ", b)

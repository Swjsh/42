"""Hunt for a real ~$3,000 loss event in J's actual WeBull money history (2021-06..2023-10)."""
import csv
import datetime as dt
from collections import defaultdict

rows = list(csv.DictReader(open("analysis/j-webull/trades-normalized.csv", encoding="utf-8")))
cl = [r for r in rows if r["closed"] == "True" and r["pnl"] not in ("", "None")]

for label, rs in (("ALL underliers", cl),
                  ("SPX/SPY family", [r for r in cl if r["is_family"] == "True"])):
    d = defaultdict(float)
    for r in rs:
        d[r["entry_ts_et"][:10]] += float(r["pnl"])
    ds = sorted(d.items())
    dates = [dt.date.fromisoformat(k) for k, _ in ds]
    vals = [v for _, v in ds]
    print(f"=== {label} | {len(ds)} active days | net ${sum(vals):,.0f} ===")
    # rolling CALENDAR windows (what a person means by "the month I lost $3K")
    for win_days in (7, 14, 30, 60, 90):
        worst, wi, wj = 0.0, None, None
        for i in range(len(ds)):
            j = i
            s = 0.0
            while j < len(ds) and (dates[j] - dates[i]).days < win_days:
                s += vals[j]
                j += 1
            if s < worst:
                worst, wi, wj = s, i, j - 1
        print(f"  worst rolling {win_days:>2}-CALENDAR-day loss: ${worst:>10,.2f}  "
              f"({ds[wi][0]} -> {ds[wj][0]})")
    # closest single stretch to exactly -3000
    best_gap, bg = 1e9, None
    for i in range(len(ds)):
        s = 0.0
        for j in range(i, len(ds)):
            s += vals[j]
            g = abs(s - (-3000))
            if g < best_gap:
                best_gap, bg = g, (ds[i][0], ds[j][0], s, j - i + 1)
    print(f"  closest contiguous stretch to exactly -$3,000: ${bg[2]:,.2f} "
          f"({bg[0]} -> {bg[1]}, {bg[3]} active days)")
    print()

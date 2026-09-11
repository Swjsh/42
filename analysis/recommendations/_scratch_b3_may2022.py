import csv
from collections import defaultdict

rows = list(csv.DictReader(open("analysis/j-webull/trades-normalized.csv", encoding="utf-8")))
cl = [r for r in rows if r["closed"] == "True" and r["pnl"] not in ("", "None")]
win = [r for r in cl if "2022-05-11" <= r["entry_ts_et"][:10] <= "2022-05-17"]
print(f"=== J's worst 7-day real-money stretch: 2022-05-11..2022-05-17 ===")
print(f"trades={len(win)}  net=${sum(float(r['pnl']) for r in win):,.2f}")
sc = sum(1 for r in win if r["scaled_in"] == "True")
print(f"scaled-in (averaged-down) episodes: {sc}/{len(win)}")
print(f"total premium at risk: ${sum(float(r['premium_at_risk']) for r in win):,.2f}")
qs = defaultdict(lambda: [0, 0.0])
for r in win:
    b = r["size_band"]
    qs[b][0] += 1
    qs[b][1] += float(r["pnl"])
for b, (n, p) in sorted(qs.items()):
    print(f"   size band {b:>5}: n={n:>2}  pnl=${p:>9,.2f}")
print()
for r in sorted(win, key=lambda r: float(r["pnl"])):
    print(f"  {r['entry_ts_et'][:16]} {r['underlying']:6s} {r['strike']:>8s}{r['right']} "
          f"qty={r['qty']:>2s} scaled={r['scaled_in']:5s} risk=${float(r['premium_at_risk']):>8,.0f} "
          f"pnl=${float(r['pnl']):>9,.2f} ret={float(r['ret_pct']):>7.1f}% hold={float(r['hold_min']):>6.1f}m")
print()
# June 2022 month
jun = [r for r in cl if r["entry_ts_et"][:7] == "2022-06"]
print(f"=== 2022-06 (worst calendar month) === trades={len(jun)} net=${sum(float(r['pnl']) for r in jun):,.2f} "
      f"scaled_in={sum(1 for r in jun if r['scaled_in']=='True')}")

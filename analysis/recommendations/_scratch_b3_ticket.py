import json
import statistics as st

rows = [json.loads(l) for l in open("analysis/trades-enriched.jsonl", encoding="utf-8") if l.strip()]
ACT = ("safe-2", "bold-2", "safe-3", "risky-1", "risky-3")
d = [r for r in rows if not r.get("_meta") and r["arm"] in ACT]
px = sorted(float(r["entry_px"]) for r in d if r.get("entry_px"))
q = [float(r["qty"]) for r in d]
print(f"ENTRY PREMIUM PER CONTRACT (n={len(px)}): min={px[0]:.2f} p10={px[int(.1*len(px))]:.2f} "
      f"p25={px[int(.25*len(px))]:.2f} median={st.median(px):.2f} p75={px[int(.75*len(px))]:.2f} "
      f"p90={px[int(.9*len(px))]:.2f} max={px[-1]:.2f}")
print(f"QTY: min={min(q):.0f} median={st.median(q):.0f} max={max(q):.0f}")
print()
for pct in (10, 25, 50, 75, 90):
    p = px[int(pct / 100 * len(px)) - 1]
    print(f"  p{pct} premium {p:.2f} -> ticket x3 contracts = ${p*300:,.0f} | x1 = ${p*100:,.0f}")
print()
aug = [r for r in d if "2026-08-03" <= r["date"] <= "2026-08-27"]
apx = sorted(float(r["entry_px"]) for r in aug if r.get("entry_px"))
print(f"AUGUST entry premium: n={len(apx)} median={st.median(apx):.2f} "
      f"p25={apx[int(.25*len(apx))]:.2f} p75={apx[int(.75*len(apx))]:.2f}")
ac = sorted(float(r["cost_dollars"]) for r in aug if r.get("cost_dollars"))
print(f"AUGUST ticket $: min={ac[0]:.0f} p25={ac[int(.25*len(ac))]:.0f} median={st.median(ac):.0f} "
      f"p75={ac[int(.75*len(ac))]:.0f} p90={ac[int(.9*len(ac))]:.0f} max={ac[-1]:.0f}")
print()
# how many arms took the SAME direction on the same day (correlation -> book concentration)
from collections import defaultdict
byday = defaultdict(lambda: defaultdict(set))
for r in aug:
    byday[r["date"]][r["right"]].add(r["arm"])
same = 0
for dt, sides in sorted(byday.items()):
    arms = set().union(*sides.values())
    dom = max(len(v) for v in sides.values())
    if dom >= 3:
        same += 1
    print(f"  {dt}: arms={len(arms)} sides={ {k: sorted(v) for k, v in sides.items()} }")
print(f"\ndays where >=3 arms took the SAME side: {same} of {len(byday)}")

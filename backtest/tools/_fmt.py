import json
from pathlib import Path
ABT = Path(r"C:\Users\jackw\Desktop\42\analysis\backtests")
L = []
spl = json.loads((ABT/"_stop_pl_candidate.json").read_text())
L.append("STOP_PL (production entry, missed/4 + OOS, per-contract):")
for r in spl["rows"]:
    m, o = r["missed"], r["oos"]
    L.append(f"  -{int(r['stop']*100):>2}% {r['pl']:>5} | missed {m['green']}/4 {m['totpc']:+7.1f} | OOS {o['green']}/{o['days_traded']} {o['totpc']:+7.1f} worst {o['worst_pc']:+6.1f} n{o['n']}")
L.append(f"  oos_days={spl['oos_days']}")
anc = json.loads((ABT/"_anchor_v0.json").read_text())
L.append("\nANCHOR (production entry wider stop on bear-put book):")
for k,v in anc.items():
    cap = ('+'+str(v['cap_504'])) if v.get('cap_504') else 'MISS'
    L.append(f"  {k:>12} | 5/04 {cap:>6} | book {v['totpc']:+7.1f} | worst {v['worst_pc']:+6.1f} | n{v['n']}")
txt="\n".join(L)
(ABT/"_fmt.txt").write_text(txt,encoding="utf-8")
print(txt)

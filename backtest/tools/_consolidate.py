"""Read EVERY computed JSON dump that exists and print the honest consolidated truth.
No hand-typed numbers; if a dump is missing, say so. One call, cascade-safe."""
import json
from pathlib import Path
ABT = Path(r"C:\Users\jackw\Desktop\42\analysis\backtests")
out = ["==== CONSOLIDATED TRUTH (from computed JSON dumps) ===="]

def load(name):
    p = ABT / name
    if not p.exists():
        out.append(f"\n[{name}] MISSING")
        return None
    try:
        return json.loads(p.read_text())
    except Exception as e:
        out.append(f"\n[{name}] UNREADABLE: {e}")
        return None

mx = load("_sniper_matrix.json")
if mx:
    out.append("\n[matrix] configs that reach 4/4 GREEN on the missed week:")
    if mx.get("winners"):
        for w in mx["winners"]:
            out.append(f"  {w['variant']} {w['strike']} {w['pl']} -> min stop -{int(w['stop']*100)}% "
                       f"| week {w['week_totpc']:+.1f}/c | worst {w['worst_pc']}/c | n={w['n']}")
    else:
        out.append("  NONE")
    out.append(f"  -> D1 sniper present in winners? "
               f"{any(w['variant'].startswith('D1') for w in mx.get('winners', []))}")
    out.append(f"  anchor checks: {json.dumps(mx.get('anchor', {}), default=str)}")

oos = load("_sniper_oos.json")
if oos:
    out.append("\n[oos] per-config over OOS days:")
    for k in ("V0_8", "V0_50", "D1_20"):
        v = oos.get(k, {})
        out.append(f"  {k}: green {v.get('green')}/{v.get('days')} | {v.get('totpc')}/c | n={v.get('n')}")
    out.append(f"  oos_days={oos.get('oos_days')} signals={oos.get('signals')}")

rob = load("_d1_robustness.json")
if rob:
    out.append(f"\n[d1_robustness] verdict={rob.get('verdict')} | "
               f"missed 4/4 cells {rob.get('missed_plateau_cells')}/{rob.get('total_cells')} | "
               f"oos+ cells {rob.get('oos_positive_cells')}/{rob.get('oos_total_cells')}")

spl = load("_stop_pl_candidate.json")
if spl:
    out.append("\n[stop_pl_candidate] production-entry stop x PL (missed + OOS):")
    for r in spl.get("rows", []):
        m, o = r["missed"], r["oos"]
        out.append(f"  -{int(r['stop']*100)}% {r['pl']}: missed {m['green']}/4 {m['totpc']:+.1f}/c | "
                   f"OOS {o['green']}/{o['days_traded']} {o['totpc']:+.1f}/c worst {o['worst_pc']}")
    out.append(f"  oos_days={spl.get('oos_days')}")

anc = load("_anchor_v0.json")
if anc:
    out.append("\n[anchor_v0] production-entry wider-stop on bear anchor book:")
    for k, v in anc.items():
        out.append(f"  {k}: 5/04={v.get('cap_504')} book={v.get('totpc')}/c worst={v.get('worst_pc')}/c n={v.get('n')}")

txt = "\n".join(out)
(ABT / "_CONSOLIDATED.txt").write_text(txt, encoding="utf-8")
print(txt)

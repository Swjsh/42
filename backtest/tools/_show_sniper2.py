"""Emit a clean, glitch-resistant digest of BOTH the missed-week and anchor results
from the experiment's JSON, plus the anchor cross-check section parsed from the md."""
from pathlib import Path
import json

A = Path(r"C:\Users\jackw\Desktop\42\analysis")
res = json.loads((A / "backtests" / "_sniper_results.json").read_text(encoding="utf-8"))

# Missed-week (these keys are profile||variant from the missed-week run; the anchor
# run overwrites _sniper_results.json with anchor keys on the second run? No — the
# JSON is written ONCE at the end with the missed-week `res`. Anchor results live only
# in the md. So parse the md for the anchor cross-check table.)
md = (A / "sniper-entry-experiment-2026-05-31.md").read_text(encoding="utf-8")

out = []
out.append("==== MISSED-WEEK: ranked (days-green, total/contract) ====")
rows = []
for k, v in res.items():
    p, var = k.split("||")
    rows.append((v.get("days_plus", 0), v.get("total", 0.0), p, var, v.get("n", 0), v.get("per_day", {})))
rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
for dp, tot, p, var, n, pdd in rows[:10]:
    days = " ".join(f"{d[5:]}:{pdd.get(d,0):+.0f}" for d in ["2026-05-26","2026-05-27","2026-05-28","2026-05-29"])
    out.append(f"  {dp}/4  {tot:+8.1f}/c  n={n:<2}  {p} / {var}   [{days}]")

out.append("")
out.append("==== ANCHOR CROSS-CHECK (parsed from md) ====")
grab = False
for line in md.splitlines():
    if "Cross-check: missed-week-winning combos" in line:
        grab = True
    if grab:
        out.append("  " + line)
    if grab and line.strip().startswith("**Read:**"):
        break

# Also pull the anchor variant matrix verdict lines (V_pullback rows) for context
out.append("")
out.append("==== ANCHOR per-variant (V_pullback + V0 rows, parsed) ====")
for line in md.splitlines():
    if line.startswith("| V_pullback |") or line.startswith("| V0_baseline |"):
        out.append("  " + line)

txt = "\n".join(out)
(A / "backtests" / "_sniper_digest2.txt").write_text(txt, encoding="utf-8")
print("wrote _sniper_digest2.txt;", len(md.splitlines()), "md lines;", len(res), "missed-week combos")

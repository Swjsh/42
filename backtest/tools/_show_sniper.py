"""Re-emit the sniper experiment results as a clean flat text file + a compact
JSON digest, so the (glitchy) Read layer has a fresh artifact to show. Read-only
on the result files."""
from pathlib import Path
import json

A = Path(r"C:\Users\jackw\Desktop\42\analysis")
md = (A / "sniper-entry-experiment-2026-05-31.md").read_text(encoding="utf-8")
res = json.loads((A / "backtests" / "_sniper_results.json").read_text(encoding="utf-8"))

# Compact digest: for each (profile||variant), days_plus + total + n
rows = []
for k, v in res.items():
    prof, var = k.split("||")
    rows.append((v.get("days_plus", 0), v.get("total", 0.0), prof, var, v.get("n", 0),
                 v.get("per_day", {})))
rows.sort(key=lambda r: (r[0], r[1]), reverse=True)

out = ["==== SNIPER EXPERIMENT DIGEST (sorted: days-green, then total/contract) ===="]
out.append(f"{'days+':>5} {'total/c':>9} {'n':>3}  profile / variant")
for dp, tot, prof, var, n, pd_ in rows:
    out.append(f"{dp:>3}/4 {tot:>+9.1f} {n:>3}  {prof} / {var}")
out.append("")
out.append("==== PER-DAY for the TOP 6 combos ====")
for dp, tot, prof, var, n, pd_ in rows[:6]:
    days = " ".join(f"{d[5:]}:{pd_.get(d,0):+.0f}" for d in
                    ["2026-05-26", "2026-05-27", "2026-05-28", "2026-05-29"])
    out.append(f"  [{prof} / {var}]  {days}  (total {tot:+.1f}/c, n={n})")
out.append("")
out.append("==== FULL MARKDOWN REPORT (verbatim from disk) ====")
out.append(md)

txt = "\n".join(out)
(A / "backtests" / "_sniper_digest.txt").write_text(txt, encoding="utf-8")
print("LINES_IN_MD:", len(md.splitlines()))
print("N_COMBOS:", len(res))
print("wrote _sniper_digest.txt")

"""Print the two J-edge runs' totals + anchor capture, plainly, to a flat file.
Glitch-proof: pure computed values, one number per line."""
from pathlib import Path
import pandas as pd
A = Path(r"C:\Users\jackw\Desktop\42\analysis\backtests")
out = []
for tag, d in [("RUN_A_filter8_active", "jedge_nonregression_2026-05-31"),
               ("RUN_B_filter8_off", "jedge_nonreg_nofilter8_2026-05-31")]:
    p = A / d / "trades.csv"
    if not p.exists():
        out.append(f"{tag}: MISSING"); continue
    df = pd.read_csv(p); df["date"] = df["date"].astype(str)
    out.append(f"== {tag} ({d}) ==")
    out.append(f"  n_trades={len(df)}  total_pnl={df['dollar_pnl'].sum():+.0f}")
    for dd in ["2026-04-29", "2026-05-01", "2026-05-04"]:
        win = df[(df.date == dd) & (df.dollar_pnl > 0)]
        out.append(f"  {dd} winner_captured={len(win) > 0}  "
                   f"day_net={df[df.date == dd]['dollar_pnl'].sum():+.0f}  "
                   f"n_on_day={len(df[df.date == dd])}")
    # bullish vs bearish in window
    out.append(f"  calls={int((df.c_or_p=='C').sum())} puts={int((df.c_or_p=='P').sum())}")
txt = "\n".join(out)
(A / "_jedge_facts.txt").write_text(txt, encoding="utf-8")
print(txt)

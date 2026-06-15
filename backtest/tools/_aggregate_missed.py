"""Read the three missed-week result dirs' trades.csv and emit ONE clean
comparison (base / safe / bold). Avoids cross-turn render garbling by computing
truth in-process and writing a single text artifact."""
from __future__ import annotations
import pandas as pd
from pathlib import Path

A = Path(r"C:\Users\jackw\Desktop\42\analysis\backtests")
RUNS = {
    "BASE (run.py, no PL)": A / "missed_week_2026-05-26_29" / "trades.csv",
    "SAFE (ATM,+30%,PLtrail)": A / "missed_week_safe" / "trades.csv",
    "BOLD (ITM2,+75%,PLtrail)": A / "missed_week_bold" / "trades.csv",
}
out = []
MISSED = ["2026-05-26", "2026-05-27", "2026-05-28", "2026-05-29"]
for name, p in RUNS.items():
    out.append("=" * 72)
    out.append(name + f"   [{p.parent.name}]")
    out.append("=" * 72)
    if not p.exists():
        out.append("  MISSING")
        continue
    df = pd.read_csv(p)
    if "dollar_pnl" not in df.columns or len(df) == 0:
        out.append("  no trades")
        continue
    df["date"] = df["date"].astype(str)
    for _, r in df.iterrows():
        out.append(
            f"  {r['date']} {r['time_entry'][:5]}  {int(r['strike'])}{r['c_or_p']} "
            f"x{int(r['qty'])} @${float(r['entry_px']):.2f}  "
            f"PnL ${float(r['dollar_pnl']):+.0f}  {r['exit_reason']}"
        )
    total = df["dollar_pnl"].sum()
    nw = int((df["dollar_pnl"] > 0).sum())
    nl = int((df["dollar_pnl"] < 0).sum())
    per_day = df.groupby("date")["dollar_pnl"].sum()
    out.append("  " + "-" * 60)
    out.append("  per-day: " + ", ".join(f"{d}:${v:+.0f}" for d, v in per_day.items()))
    out.append(f"  TOTAL ${total:+.0f}  ({nw}W/{nl}L, n={len(df)})")
    # missed-days-only (exclude warmup 05-19..22)
    md = df[df["date"].isin(MISSED)]
    out.append(f"  MISSED-DAYS-ONLY ${md['dollar_pnl'].sum():+.0f} "
               f"({int((md['dollar_pnl']>0).sum())}W/{int((md['dollar_pnl']<0).sum())}L, n={len(md)})")
    # ex-05-26 (the one big winner) to expose the counter-trend bleed
    ex = md[md["date"] != "2026-05-26"]
    out.append(f"  EX-05/26 (27+28+29) ${ex['dollar_pnl'].sum():+.0f} "
               f"({int((ex['dollar_pnl']>0).sum())}W/{int((ex['dollar_pnl']<0).sum())}L, n={len(ex)})")
    out.append("")

txt = "\n".join(out)
(A / "_missed_week_comparison.txt").write_text(txt, encoding="utf-8")
print(txt)

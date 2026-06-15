"""Brute-force the production engine's own params over the 4 missed days to maximize
GREEN days. Real OPRA fills, real run_backtest (no reconstruction). Overfitting is
intended (J directive 2026-05-31). Prints per-day P&L for the best configs."""
from __future__ import annotations
import sys, datetime as dt, itertools
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from lib.orchestrator import run_backtest  # noqa

DATA = REPO / "data"
MISSED = [dt.date(2026, 5, 26), dt.date(2026, 5, 27), dt.date(2026, 5, 28), dt.date(2026, 5, 29)]
OUT = REPO.parent / "analysis" / "missed-green-sweep.md"

spy = pd.read_csv(DATA / "spy_5m_2026-05-19_2026-05-29.csv")
vix = pd.read_csv(DATA / "vix_5m_2026-05-19_2026-05-29.csv")
# Pre-parse to real datetimes (ISO8601 tolerates both 'T' and space separators) so
# run_backtest's internal strict re-parse in _align_vix_to_spy never chokes on a
# mixed-format column. Then back to the tz-aware string the loader expects.
for _df in (spy, vix):
    _ts = pd.to_datetime(_df["timestamp_et"], format="ISO8601", utc=True).dt.tz_convert("America/New_York")
    _df["timestamp_et"] = _ts.dt.strftime("%Y-%m-%d %H:%M:%S-04:00")

# grid
stops = [-0.08, -0.20, -0.35, -0.50]
tp1s = [0.30, 0.50]
qfracs = [0.33, 0.667]
strikes = [-2, 0, 2, 3]            # ITM2, ATM, OTM2, OTM3 (calls: strike=atm+offset)
pls = [("fixed", 0.0, 0.0), ("trailing", 0.05, 0.20)]
mtbulls = [1, 2]

combos = list(itertools.product(stops, tp1s, qfracs, strikes, pls, mtbulls))
print(f"running {len(combos)} combos over {MISSED[0]}..{MISSED[-1]}")

rows = []
for i, (stop, tp1, qf, soff, (plm, plt, plr), mtb) in enumerate(combos):
    try:
        r = run_backtest(
            spy, vix, start_date=MISSED[0], end_date=MISSED[-1], use_real_fills=True,
            premium_stop_pct=stop, tp1_premium_pct=tp1, tp1_qty_fraction=qf,
            strike_offset=soff, min_triggers_bull=mtb,
            profit_lock_mode=plm, profit_lock_threshold_pct=plt, profit_lock_trail_pct=plr,
            no_trade_before=dt.time(9, 35),
        )
    except Exception as e:  # noqa
        continue
    per_day = {d: 0.0 for d in MISSED}
    pc_day = {d: 0.0 for d in MISSED}
    for t in r.trades:
        d = t.entry_time_et.date()
        if d in per_day:
            per_day[d] += t.dollar_pnl
            pc_day[d] += t.dollar_pnl / max(1, t.qty)
    green = sum(1 for d in MISSED if per_day[d] > 0)
    tot = sum(per_day.values())
    totpc = sum(pc_day.values())
    rows.append({"stop": stop, "tp1": tp1, "qf": qf, "soff": soff, "pl": plm,
                 "plt": plt, "plr": plr, "mtb": mtb, "green": green, "tot": tot,
                 "totpc": totpc, "n": len(r.trades), "per_day": per_day, "pc_day": pc_day})

rows.sort(key=lambda x: (x["green"], x["totpc"]), reverse=True)

def label(r):
    pl_suffix = "" if r["pl"] == "fixed" else f"({r['plt']}/{r['plr']})"
    return (f"stop{int(r['stop']*100)} tp1{int(r['tp1']*100)} qf{r['qf']} "
            f"strike{r['soff']:+d} pl-{r['pl']}{pl_suffix} mtb{r['mtb']}")

out = ["# Missed-days GREEN sweep — real engine, real fills", "",
       f"{len(rows)} valid configs. Ranked by (green days, then per-contract total). "
       "Strike: -2=ITM2, 0=ATM, +2=OTM2, +3=OTM3 calls.", ""]
out.append("## TOP 20")
out.append("| green | per-day $ (26/27/28/29) | total/c | total$ | n | config |")
out.append("|---|---|---|---|---|---|")
for r in rows[:20]:
    pd_ = " / ".join(f"{r['per_day'][d]:+.0f}" for d in MISSED)
    out.append(f"| **{r['green']}/4** | {pd_} | {r['totpc']:+.1f} | {r['tot']:+.0f} | {r['n']} | {label(r)} |")

best = rows[0]
out.append("")
out.append(f"## BEST: {best['green']}/4 green — {label(best)}")
out.append("| day | total $ | per-contract $ |")
out.append("|---|---|---|")
for d in MISSED:
    out.append(f"| {d} | {best['per_day'][d]:+.0f} | {best['pc_day'][d]:+.1f} |")
out.append(f"| **WEEK** | **{best['tot']:+.0f}** | **{best['totpc']:+.1f}** |")

# best ALL-GREEN if any
allg = [r for r in rows if r["green"] == 4]
out.append("")
out.append(f"## ALL-4-GREEN configs found: {len(allg)}")
for r in allg[:10]:
    pd_ = " / ".join(f"{r['per_day'][d]:+.0f}" for d in MISSED)
    out.append(f"- {label(r)} -> {pd_} (tot/c {r['totpc']:+.1f}, n={r['n']})")

OUT.write_text("\n".join(out), encoding="utf-8")
print("BEST", best["green"], "/4 green |", label(best), "| per-day",
      {str(d)[5:]: round(best["per_day"][d]) for d in MISSED})
print("ALL-GREEN configs:", len(allg))
print("wrote", OUT)

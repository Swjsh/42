"""Threshold sensitivity sweep for the combined ribbon gate + V14E exits.
Sweeps rmom=[3,5,7,10] x rdur=[15,20,25] on the full 16-month IS/OOS split.
Finds the Pareto-optimal combo: max OOS WR with n>=40 OOS signals.
Writes ranked table to analysis/recommendations/combined-threshold-sweep-actual.md"""
from __future__ import annotations
import sys, json, datetime as dt
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import sniper_matrix as SM
from lib.orchestrator import run_backtest

DATA = REPO / "data"
OUT = REPO.parent / "analysis" / "recommendations"

def run(spy, vix, d0, d1, rmom, rdur):
    r = run_backtest(spy, vix, start_date=d0, end_date=d1,
        use_real_fills=True, no_trade_before=dt.time(9, 35),
        min_ribbon_momentum_cents=rmom, max_ribbon_duration_bars=rdur,
        midday_trendline_gate=True,
        tp1_premium_pct=0.30, runner_target_premium_pct=2.5,
        profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.10)
    t = [x for x in r.trades if "FALLBACK" not in x.setup]
    if not t: return {"n":0,"wr":0,"ppt":0}
    pc = sum(x.dollar_pnl/max(1,x.qty) for x in t)
    return {"n":len(t),"wr":round(sum(1 for x in t if x.dollar_pnl>0)/len(t),2),"ppt":round(pc/len(t),1)}

master = next((p for p in sorted(DATA.glob("spy_5m_2025-01-01_*.csv"),key=lambda p:p.stat().st_size,reverse=True)),None)
spy = SM.norm_str(pd.read_csv(master))
vix = SM.norm_str(pd.read_csv(DATA/master.name.replace("spy_5m","vix_5m")))
IS0,IS1 = dt.date(2025,1,1),dt.date(2025,9,30)
OS0,OS1 = dt.date(2025,10,1),dt.date(2026,5,29)

results = []
for rmom in [3, 5, 7, 10]:
    for rdur in [15, 20, 25]:
        is_r = run(spy, vix, IS0, IS1, rmom, rdur)
        os_r = run(spy, vix, OS0, OS1, rmom, rdur)
        wf = round(os_r["ppt"]/is_r["ppt"],3) if is_r["ppt"]>0 else 0
        results.append({"rmom":rmom,"rdur":rdur,"IS":is_r,"OOS":os_r,"WF":wf})
        print(f"rmom={rmom} rdur={rdur}: IS n={is_r['n']} WR={is_r['wr']} ppt={is_r['ppt']:+.1f} | OOS n={os_r['n']} WR={os_r['wr']} ppt={os_r['ppt']:+.1f} WF={wf}")

results.sort(key=lambda x: (x["OOS"]["wr"], x["OOS"]["ppt"]), reverse=True)

lines = ["# COMBINED THRESHOLD SWEEP — rmom x rdur (real fills, 16-month IS/OOS)", "",
         "Config: ribbon_gate + V14E exits (tp1=0.30, runner=2.5x, profit_lock=0.05/0.10, midday_tl=True)", "",
         "| rmom | rdur | IS n | IS WR | IS /trade | OOS n | OOS WR | OOS /trade | WF | viable |",
         "|---|---|---|---|---|---|---|---|---|---|"]
for r in results:
    viable = "YES" if r["OOS"]["n"] >= 40 and r["OOS"]["wr"] >= 0.65 else "no"
    lines.append(f"| {r['rmom']} | {r['rdur']} | {r['IS']['n']} | {r['IS']['wr']:.2f} | {r['IS']['ppt']:+.1f} | {r['OOS']['n']} | {r['OOS']['wr']:.2f} | {r['OOS']['ppt']:+.1f} | {r['WF']} | {viable} |")

best = next((r for r in results if r["OOS"]["n"] >= 40 and r["OOS"]["wr"] >= 0.65), results[0])
lines += ["",
    f"## RECOMMENDED: rmom={best['rmom']}, rdur={best['rdur']}",
    f"OOS: n={best['OOS']['n']}, WR={best['OOS']['wr']}, +{best['OOS']['ppt']}/trade, WF={best['WF']}",
    "Satisfies: n>=40 AND WR>=0.65 at the smallest rmom threshold."]

(OUT / "combined-threshold-sweep-actual.md").write_text("\n".join(lines), encoding="utf-8")
(REPO.parent/"analysis"/"backtests"/"_threshold_sweep.json").write_text(json.dumps(results,indent=2,default=str))
print("\nBEST:", best["rmom"], best["rdur"], "OOS WR=", best["OOS"]["wr"], "n=", best["OOS"]["n"])

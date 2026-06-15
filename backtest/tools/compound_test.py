"""V14E exits + RIBBON_GATE entries compound test.
Runs all 4 combos on full 16-month IS/OOS split. Writes result JSON."""
from __future__ import annotations
import sys, json, datetime as dt
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import sniper_matrix as SM
from lib.orchestrator import run_backtest

DATA = REPO / "data"

def run(spy, vix, d0, d1, rmom, rdur, mid, tp1, runner, pl_thr, pl_off):
    return run_backtest(spy, vix, start_date=d0, end_date=d1,
        use_real_fills=True, no_trade_before=dt.time(9, 35),
        min_ribbon_momentum_cents=rmom, max_ribbon_duration_bars=rdur,
        midday_trendline_gate=mid,
        tp1_premium_pct=tp1, runner_target_premium_pct=runner,
        profit_lock_threshold_pct=pl_thr, profit_lock_stop_offset_pct=pl_off)

def stat(trades):
    t = [x for x in trades if "FALLBACK" not in x.setup]
    if not t: return {"n":0,"wr":0,"ppt":0}
    pc = sum(x.dollar_pnl/max(1,x.qty) for x in t)
    return {"n":len(t),"wr":round(sum(1 for x in t if x.dollar_pnl>0)/len(t),2),"ppt":round(pc/len(t),1)}

master = next((p for p in sorted(DATA.glob("spy_5m_2025-01-01_*.csv"),
               key=lambda p:p.stat().st_size,reverse=True)),None)
spy = SM.norm_str(pd.read_csv(master))
vix = SM.norm_str(pd.read_csv(DATA/master.name.replace("spy_5m","vix_5m")))

IS0,IS1 = dt.date(2025,1,1),dt.date(2025,9,30)
OS0,OS1 = dt.date(2025,10,1),dt.date(2026,5,29)

configs = [
    ("BASE (no gates, v15 exits)",         None,None,False, 0.30,3.0,0.0,0.0),
    ("RIBBON_GATE only",                    5.0, 20,True,  0.30,3.0,0.0,0.0),
    ("V14E exits only",                    None,None,False, 0.30,2.5,0.05,0.10),
    ("RIBBON_GATE + V14E exits (BOTH)",    5.0, 20,True,  0.30,2.5,0.05,0.10),
]

results = {}
for name,rmom,rdur,mid,tp1,runner,plthr,ploff in configs:
    print(f"Running {name}...")
    is_r = stat(run(spy,vix,IS0,IS1,rmom,rdur,mid,tp1,runner,plthr,ploff).trades)
    os_r = stat(run(spy,vix,OS0,OS1,rmom,rdur,mid,tp1,runner,plthr,ploff).trades)
    wf = round(os_r["ppt"]/is_r["ppt"],3) if is_r["ppt"]>0 else 0
    results[name] = {"IS":is_r,"OOS":os_r,"WF":wf}
    print(f"  IS {is_r} OOS {os_r} WF={wf}")

(REPO.parent/"analysis"/"backtests"/"_compound_test.json").write_text(json.dumps(results,indent=2))
print("\nCOMPOUND RESULTS:")
for name,r in results.items():
    print(f"  {name:<35} OOS WR={r['OOS']['wr']:.2f} ppt={r['OOS']['ppt']:+.1f} WF={r['WF']}")
print("wrote _compound_test.json")

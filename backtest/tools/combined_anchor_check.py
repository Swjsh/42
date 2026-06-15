"""Anchor validation for the COMBINED config (ribbon gate + V14E exits).
Runs the full anchor suite 2026-04-27..05-07 filter-8-off.
Reports which J winners fire and which J losers are suppressed."""
from __future__ import annotations
import sys, json, datetime as dt
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import sniper_matrix as SM
from lib.orchestrator import run_backtest

DATA = REPO / "data"

def run_anchor(spy, vix, rmom, rdur):
    r = run_backtest(spy, vix, start_date=dt.date(2026,4,27), end_date=dt.date(2026,5,7),
        use_real_fills=True, no_trade_before=dt.time(9,35), disable_filters=[8],
        min_ribbon_momentum_cents=rmom, max_ribbon_duration_bars=rdur,
        midday_trendline_gate=True,
        tp1_premium_pct=0.30, runner_target_premium_pct=2.5,
        profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.10)
    t = [x for x in r.trades if "FALLBACK" not in x.setup]
    return t

master = next((p for p in sorted(DATA.glob("spy_5m_2025-01-01_*.csv"),key=lambda p:p.stat().st_size,reverse=True)),None)
spy = SM.norm_str(pd.read_csv(master))
vix = SM.norm_str(pd.read_csv(DATA/master.name.replace("spy_5m","vix_5m")))

J_ANCHORS = {
    "2026-04-29": {"label":"4/29 winner (+$342)", "want":"CAPTURED"},
    "2026-05-01": {"label":"5/01 winner (+$470)", "want":"CAPTURED"},
    "2026-05-04": {"label":"5/04 winner (+$730)", "want":"CAPTURED"},
    "2026-05-05": {"label":"5/05 loser (-$260)",  "want":"SKIPPED"},
    "2026-05-06": {"label":"5/06 loser (-$300)",  "want":"SKIPPED"},
    "2026-05-07": {"label":"5/07 loser (-$165)",  "want":"SKIPPED"},
}

print("Running combined anchor check...")
for rmom, rdur in [(5,20), (3,20), (7,20), (5,15)]:
    trades = run_anchor(spy, vix, rmom, rdur)
    by_date = {}
    for t in trades:
        d = t.entry_time_et.date().isoformat()
        if d not in by_date: by_date[d] = []
        by_date[d].append(round(t.dollar_pnl/max(1,t.qty),1))

    results = {}
    for date, info in J_ANCHORS.items():
        pnl_list = by_date.get(date, [])
        won = any(p > 0 for p in pnl_list)
        captured = won if info["want"]=="CAPTURED" else (not pnl_list or not any(p<-20 for p in pnl_list))
        results[date] = {"pnl":pnl_list,"captured":captured,"verdict":"PASS" if captured else "FAIL"}

    passes = sum(1 for v in results.values() if v["verdict"]=="PASS")
    total_pc = sum(sum(v["pnl"]) for v in results.values())
    print(f"\nrmom={rmom} rdur={rdur}: {passes}/6 anchors PASS, anchor total={total_pc:+.1f}/c")
    for date, v in results.items():
        icon = "OK" if v["verdict"]=="PASS" else "XX"
        print(f"  {icon} {J_ANCHORS[date]['label']:30} pnl={v['pnl']} -> {v['verdict']}")

    if passes >= 5 and rmom == 5:
        print("\n** COMBINED (rmom=5, rdur=20, midday_tl, V14E exits): ANCHOR PASS -> RATIFICATION_READY **")

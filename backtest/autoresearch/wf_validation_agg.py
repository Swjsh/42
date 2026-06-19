"""Walk-forward validation of all 7 AGG production gates across 6 expanding-IS folds.

Method: IS always starts 2025-01-02, expands through each fold end.
OOS = rolling 2-month window. Gate value = full_all_gates minus gate_disabled per fold.
Stable = passes OOS_delta>0 in >=4/6 folds.
"""
import sys, datetime as dt, json
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
import pandas as pd
from lib.orchestrator import run_backtest

spy = pd.read_csv("backtest/data/spy_5m_2025-01-01_2026-06-16.csv")
vix = pd.read_csv("backtest/data/vix_5m_2025-01-01_2026-06-16.csv")

def pnl(r): return sum(t.dollar_pnl for t in r.trades)
def n(r):   return len(r.trades)
def wr(r):  return round(sum(1 for t in r.trades if t.dollar_pnl > 0) / max(n(r), 1), 3)

AGG_ALL = dict(
    use_real_fills=True, no_trade_before=dt.time(9, 35), no_trade_window=None,
    premium_stop_pct=-0.07, premium_stop_pct_bear=-0.07, premium_stop_pct_bull=-0.05,
    tp1_premium_pct=0.75, tp1_qty_fraction=0.667, runner_target_premium_pct=5.0,
    time_stop_minutes_before_close=20, per_trade_risk_cap_pct=0.50,
    block_level_rejection=True, block_elite_bull=True, block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=18.0, entry_bar_body_pct_min=0.0, vix_bear_hard_cap=None,
    min_triggers_bear=1, min_triggers_bull=1, profit_lock_threshold_pct=0.05,
    profit_lock_mode="trailing", profit_lock_trail_pct=0.20, initial_equity=1673.0,
    strike_offset=-2, block_conf_lvl_rec_afternoon=True,
    block_conf_lvl_rej_midday_afternoon=True, require_bearish_fill_bar=True,
    block_bull_morning_agg=True, midday_trendline_gate=True,
)

GATES = [
    ("midday_trendline_gate",         {"midday_trendline_gate": False}),
    ("block_level_rejection",         {"block_level_rejection": False}),
    ("block_elite_bull",              {"block_elite_bull": False}),
    ("block_conf_lvl_rec_afternoon",  {"block_conf_lvl_rec_afternoon": False}),
    ("block_conf_lvl_rej_midday_afo", {"block_conf_lvl_rej_midday_afternoon": False}),
    ("require_bearish_fill_bar",      {"require_bearish_fill_bar": False}),
    ("block_bull_morning_agg",        {"block_bull_morning_agg": False}),
]

START = dt.date(2025, 1, 2)
FOLDS = [
    (dt.date(2025, 6, 30), dt.date(2025, 7, 1),  dt.date(2025, 8, 29)),
    (dt.date(2025, 8, 29), dt.date(2025, 9, 1),  dt.date(2025, 10, 31)),
    (dt.date(2025, 10, 31), dt.date(2025, 11, 3), dt.date(2025, 12, 31)),
    (dt.date(2025, 12, 31), dt.date(2026, 1, 2),  dt.date(2026, 2, 27)),
    (dt.date(2026, 2, 27),  dt.date(2026, 3, 2),  dt.date(2026, 4, 30)),
    (dt.date(2026, 4, 30),  dt.date(2026, 5, 8),  dt.date(2026, 6, 16)),
]

print("AGG Walk-forward validation — 6 folds x 7 gates")
results = {g: [] for g, _ in GATES}
fold_summary = []

for fi, (is_end, oos_s, oos_e) in enumerate(FOLDS):
    print(f"  Fold {fi+1}: IS {START}..{is_end}  OOS {oos_s}..{oos_e}", flush=True)
    r_full_is  = run_backtest(spy, vix, start_date=START, end_date=is_end,  **AGG_ALL)
    r_full_oos = run_backtest(spy, vix, start_date=oos_s,  end_date=oos_e,  **AGG_ALL)
    fold_summary.append({"fold": fi+1, "is_pnl": pnl(r_full_is), "oos_pnl": pnl(r_full_oos),
                          "is_n": n(r_full_is), "oos_n": n(r_full_oos)})
    for gname, override in GATES:
        params_no = {**AGG_ALL, **override}
        r_base_is  = run_backtest(spy, vix, start_date=START, end_date=is_end,  **params_no)
        r_base_oos = run_backtest(spy, vix, start_date=oos_s,  end_date=oos_e,  **params_no)
        results[gname].append({
            "fold": fi+1, "is_end": str(is_end), "oos_end": str(oos_e),
            "is_delta": pnl(r_full_is) - pnl(r_base_is),
            "oos_delta": pnl(r_full_oos) - pnl(r_base_oos),
            "full_oos_n": n(r_full_oos), "base_oos_n": n(r_base_oos),
        })
    print(f"    IS n={n(r_full_is)} pnl={pnl(r_full_is):+.0f}  OOS n={n(r_full_oos)} pnl={pnl(r_full_oos):+.0f}", flush=True)

print()
print("=" * 80)
print("WALK-FORWARD VALIDATION SCORECARD — AGG GATES")
print("IS expands from 2025-01-02. OOS = 2-month rolling window.")
print("PASS fold if OOS_delta > 0. WF_stable = passes >= 4/6 folds.")
print("=" * 80)
print()

scorecard = {}
for gname, _ in GATES:
    fdata = results[gname]
    oos_passes = sum(1 for f in fdata if f["oos_delta"] > 0)
    is_passes  = sum(1 for f in fdata if f["is_delta"] > 0)
    tot_is  = sum(f["is_delta"]  for f in fdata)
    tot_oos = sum(f["oos_delta"] for f in fdata)
    stable = oos_passes >= 4
    scorecard[gname] = {"oos_passes": oos_passes, "is_passes": is_passes,
                        "total_is_delta": round(tot_is), "total_oos_delta": round(tot_oos),
                        "wf_stable": stable, "folds": fdata}
    print(f"Gate: {gname}")
    print(f"  IS passes: {is_passes}/6  OOS passes: {oos_passes}/6  WF_stable: {'YES' if stable else 'NO-REVIEW'}")
    print(f"  Total IS delta: {tot_is:+.0f}  Total OOS delta: {tot_oos:+.0f}")
    print(f"  {'Fold':<5} {'IS_end':<13} {'OOS_end':<13} {'IS_delta':>10} {'OOS_delta':>10} {'OOS'}")
    for f in fdata:
        flag = "PASS" if f["oos_delta"] > 0 else "FAIL"
        print(f"  {f['fold']:<5} {f['is_end']:<13} {f['oos_end']:<13} {f['is_delta']:>10.0f} {f['oos_delta']:>10.0f} {flag}")
    print()

print("SUMMARY:")
for gname, _ in GATES:
    d = scorecard[gname]
    s = "STABLE" if d["wf_stable"] else "REVIEW"
    print(f"  {gname:<35} OOS_passes={d['oos_passes']}/6  total_oos_delta={d['total_oos_delta']:+.0f}  [{s}]")

print()
print("Full-gate P&L by fold:")
for f in fold_summary:
    print(f"  Fold {f['fold']}: IS pnl={f['is_pnl']:+.0f} n={f['is_n']}  OOS pnl={f['oos_pnl']:+.0f} n={f['oos_n']}")

out_path = "analysis/recommendations/wf_validation_agg.json"
with open(out_path, "w") as fh:
    json.dump({"account": "AGG", "method": "expanding-IS 6-fold WF", "gates": scorecard,
               "fold_summary": fold_summary}, fh, indent=2)
print(f"\nScorecard written to {out_path}")

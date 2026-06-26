"""SAFE bear premium stop sweep.

Current: premium_stop_pct_bear=-0.10 (10%).
AGG was tightened from -0.10 to -0.07 with WF=0.725 (ratified 2026-06-17).
Hypothesis: SAFE may benefit from similar tightening, but OTM-2 options
behave differently from AGG's ITM-2 (wider premium swings -> may need more room).

Sweep: [-0.07, -0.08, -0.09, -0.10 (baseline)]

Security: read-only (except scorecard). No Alpaca calls.
"""
from __future__ import annotations
import sys, json, datetime as dt
from pathlib import Path
from collections import Counter, defaultdict

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from lib.orchestrator import run_backtest  # noqa
from sniper_matrix import norm_str  # noqa

DATA = REPO / "data"
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "safe_bear_stop_sweep.json"

IS_CUTOFF  = dt.date(2026, 2, 27)
MDATES_SET = {dt.date(2026,5,26), dt.date(2026,5,27), dt.date(2026,5,28), dt.date(2026,5,29)}
ANCHOR_WINNERS = {dt.date(2026,4,29), dt.date(2026,5,1), dt.date(2026,5,4)}

SW_SPLITS = [
    ("SW1_2025H1",  dt.date(2025,1,2),  dt.date(2025,6,30)),
    ("SW2_2025H2",  dt.date(2025,7,1),  dt.date(2025,12,31)),
    ("SW3_early26", dt.date(2026,1,2),  dt.date(2026,2,26)),
]

SAFE_BASE = dict(
    use_real_fills=True,
    strike_offset=-2,
    # premium_stop_pct_bear swept below
    premium_stop_pct_bull=-0.08,
    tp1_premium_pct=0.50,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.5,
    f9_vol_mult=0.7,
    min_triggers_bear=1,
    min_triggers_bull=2,
    no_trade_before=dt.time(9, 35),
    no_trade_window=(dt.time(11, 30), dt.time(12, 0)),
    block_level_rejection=True,
    block_conf_lvl_rec_afternoon=True,
    midday_trendline_gate=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.3,
    enable_bullish=True,
    params_overrides={
        "vix_bear_threshold": 17.3,
        "vix_bull_hard_cap": 18.0,
    },
)

BASELINE = -0.10
THRESHOLDS = [-0.07, -0.08, -0.09, -0.10]


def stats(trades):
    if not trades:
        return {"n": 0, "wr": 0.0, "avg": 0.0, "total": 0.0}
    pnls = [t.dollar_pnl for t in trades]
    return {"n": len(trades), "wr": round(sum(p > 0 for p in pnls) / len(pnls), 3),
            "avg": round(sum(pnls) / len(pnls), 1), "total": round(sum(pnls), 1)}


def sw_hurt(is_trades, base_is_pnl):
    hurt = 0
    for _name, sw_start, sw_end in SW_SPLITS:
        sw_pnl = sum(t.dollar_pnl for t in is_trades
                     if sw_start <= t.entry_time_et.date() <= sw_end)
        if sw_pnl < 0:
            hurt += 1
    return hurt


def load_data():
    spy_path = sorted(DATA.glob("spy_5m_2025-01-01_*.csv"),
                      key=lambda p: p.stat().st_size, reverse=True)[0]
    vix_path = DATA / spy_path.name.replace("spy_5m", "vix_5m")
    spy_df = pd.read_csv(spy_path)
    vix_df = pd.read_csv(vix_path)
    from sniper_matrix import norm_str  # noqa
    return norm_str(spy_df), norm_str(vix_df)


def main():
    print("=" * 70)
    print("SAFE BEAR PREMIUM STOP SWEEP")
    print(f"Thresholds: {THRESHOLDS}  Baseline: {BASELINE}")
    print("=" * 70)

    spy_df, vix_df = load_data()
    c = Counter(f.name[3:9] for f in (DATA/"options").glob("SPY*.csv"))
    all_fill = sorted({dt.datetime.strptime(k,"%y%m%d").date() for k,v in c.items() if v>=8})
    spy_dates = set(pd.to_datetime(spy_df["timestamp_et"].str[:10]).dt.date)
    is_days  = [d for d in all_fill if d < IS_CUTOFF  and d not in MDATES_SET]
    oos_days = [d for d in all_fill if d >= IS_CUTOFF and d not in MDATES_SET and d in spy_dates]
    print(f"IS: {len(is_days)} days | OOS: {len(oos_days)} days\n")

    print("Running baseline (stop=-0.10)...")
    base_kw = dict(SAFE_BASE, premium_stop_pct_bear=BASELINE)
    base_is  = run_backtest(spy_df, vix_df, start_date=is_days[0],  end_date=is_days[-1],  **base_kw)
    base_oos = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1], **base_kw)
    base_is_s  = stats(base_is.trades)
    base_oos_s = stats(base_oos.trades)
    base_is_pnl  = base_is_s["total"]
    base_oos_pnl = base_oos_s["total"]
    base_anchor  = sum(t.dollar_pnl for t in base_oos.trades
                       if t.entry_time_et.date() in ANCHOR_WINNERS)
    print(f"Baseline IS: n={base_is_s['n']} {base_is_pnl:+.0f} | OOS: n={base_oos_s['n']} {base_oos_pnl:+.0f}")
    print(f"Baseline OOS anchor: {base_anchor:+.0f}\n")

    print(f"  {'stop':>6} {'IS_n':>5} {'IS_tot':>9} {'IS_WR':>6} {'IS_D':>7}"
          f" {'OOS_n':>6} {'OOS_tot':>9} {'OOS_WR':>7} {'OOS_D':>8}"
          f" {'WF':>7} {'SW':>4} {'G5':>4} {'PASS':>4}")
    print(f"  {'-'*115}")

    results = []
    for stop in THRESHOLDS:
        if stop == BASELINE:
            s, so = base_is_s, base_oos_s
            print(f"  {stop:>6.2f} {s['n']:>5} {s['total']:>+9.0f} {s['wr']:>6.1%} {'--':>7}"
                  f" {so['n']:>6} {so['total']:>+9.0f} {so['wr']:>7.1%} {'--':>8}"
                  f" {'--':>7} {'--':>4} {'--':>4} {'BASE':>4}")
            results.append({"stop": stop, "is": s, "oos": so,
                             "is_delta": 0.0, "oos_delta": 0.0, "verdict": "BASELINE"})
            continue

        kw = dict(SAFE_BASE, premium_stop_pct_bear=stop)
        r_is  = run_backtest(spy_df, vix_df, start_date=is_days[0],  end_date=is_days[-1],  **kw)
        r_oos = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1], **kw)
        s   = stats(r_is.trades)
        so  = stats(r_oos.trades)
        is_d  = round(s["total"]  - base_is_pnl,  1)
        oos_d = round(so["total"] - base_oos_pnl, 1)

        wf = None
        if is_d != 0 and s["n"] > 0 and so["n"] > 0:
            per_is  = is_d / s["n"]
            per_oos = oos_d / so["n"]
            if per_is != 0:
                wf = round(per_oos / per_is, 3)

        sw_h = sw_hurt(r_is.trades, base_is_pnl)
        curr_anchor = sum(t.dollar_pnl for t in r_oos.trades
                          if t.entry_time_et.date() in ANCHOR_WINNERS)
        anchor_tol = abs(base_anchor) * 0.10
        g5 = curr_anchor >= base_anchor - anchor_tol

        g1 = is_d >= 0
        g2 = oos_d > 0
        g3 = wf is not None and wf >= 0.70
        g4 = sw_h <= 1
        passed = g1 and g2 and g3 and g4 and g5
        wf_str = f"{wf:.3f}" if wf is not None else "N/A"

        print(f"  {stop:>6.2f} {s['n']:>5} {s['total']:>+9.0f} {s['wr']:>6.1%} {is_d:>+7.0f}"
              f" {so['n']:>6} {so['total']:>+9.0f} {so['wr']:>7.1%} {oos_d:>+8.0f}"
              f" {wf_str:>7} {sw_h:>4} {'Y' if g5 else 'N':>4} {'Y' if passed else 'N':>4}")

        results.append({
            "stop": stop, "is": s, "oos": so,
            "is_delta": is_d, "oos_delta": oos_d,
            "wf_norm": wf, "sw_hurt": sw_h, "anchor_ok": g5,
            "gates": {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5, "all": passed},
        })

    passing = [r for r in results if r.get("gates", {}).get("all")]
    best = max(passing, key=lambda r: r["oos_delta"]) if passing else None

    print(f"\n{'='*70}")
    print("VERDICT")
    print(f"{'='*70}")
    if best:
        print(f"  RATIFY premium_stop_pct_bear = {best['stop']:.2f}")
        print(f"  IS_delta={best['is_delta']:+.0f}  OOS_delta={best['oos_delta']:+.0f}  "
              f"WF={best['wf_norm']}  SW={best['sw_hurt']}")
    else:
        print("  REJECT - no candidate cleared all OP-22 gates.")
        best_oos = max((r for r in results if r.get("gates") is not None),
                       key=lambda r: r["oos_delta"], default=None)
        if best_oos:
            print(f"  Best OOS: stop={best_oos['stop']:.2f} OOS_D={best_oos['oos_delta']:+.0f} "
                  f"gates={best_oos['gates']}")

    scorecard = {
        "task": "safe-bear-stop-sweep",
        "rule_id": "safe_premium_stop_pct_bear",
        "description": "SAFE premium_stop_pct_bear sweep [-0.07, -0.08, -0.09, -0.10]",
        "baseline_stop": BASELINE,
        "thresholds_tested": THRESHOLDS,
        "sweep_results": results,
        "best": best,
        "auto_ratify": best is not None,
        "ratify_value": best["stop"] if best else None,
        "verdict": "RATIFY" if best else "REJECT",
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(scorecard, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")
    print("SAFE BEAR STOP SWEEP COMPLETE.")


if __name__ == "__main__":
    raise SystemExit(main())

"""AGG vix_bear_threshold sweep v2.

Corrects agg_vix_bear_threshold_sweep.py which used 15.0 as baseline
instead of the current production value of 17.3.

This version uses a full engine re-run with each threshold value, with
17.3 as the baseline. Tests: 17.5, 18.0.

Motivation: OOS deep dive shows VIX [17-18) bears WR=0%, total=-415 on 4 trades.
Maybe raising from 17.3 to 17.5 or 18.0 cleans these up.

Security: read-only (except output). No Alpaca calls.
"""
from __future__ import annotations
import sys, json, datetime as dt
from pathlib import Path
from collections import Counter

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from lib.orchestrator import run_backtest  # noqa
from sniper_matrix import norm_str  # noqa

DATA = REPO / "data"
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "agg_vix_bear_threshold_v2.json"

IS_CUTOFF  = dt.date(2026, 2, 27)
MDATES_SET = {dt.date(2026,5,26), dt.date(2026,5,27), dt.date(2026,5,28), dt.date(2026,5,29)}
ANCHOR_WINNERS = {dt.date(2026,4,29), dt.date(2026,5,1), dt.date(2026,5,4)}

SW_SPLITS = [
    ("SW1_2025H1",  dt.date(2025,1,2),  dt.date(2025,6,30)),
    ("SW2_2025H2",  dt.date(2025,7,1),  dt.date(2025,12,31)),
    ("SW3_early26", dt.date(2026,1,2),  dt.date(2026,2,26)),
]

# AGG production params (block_elite_bull_vix_high=18.0 active from prior ratification)
AGG_PARAMS_BASE = dict(
    use_real_fills=True, strike_offset=2,
    premium_stop_pct_bear=-0.07, premium_stop_pct_bull=-0.08,
    tp1_premium_pct=0.75, tp1_qty_fraction=0.50,
    runner_target_premium_pct=2.5, f9_vol_mult=0.7,
    min_triggers_bear=1, min_triggers_bull=2,
    no_trade_before=dt.time(9, 35), no_trade_window=(dt.time(11, 30), dt.time(12, 0)),
    block_level_rejection=True, block_conf_lvl_rec_afternoon=True,
    midday_trendline_gate=True, block_elite_bull=True,
    block_elite_bull_vix_low=15.0, block_elite_bull_vix_high=18.0,
    time_stop_minutes_before_close=20, per_trade_risk_cap_pct=0.5, enable_bullish=True,
    # params_overrides set per candidate below
)

BASELINE_VBT = 17.3
THRESHOLDS = [17.3, 17.5, 18.0, 18.5]


def stats(ts):
    if not ts:
        return {"n": 0, "wr": 0.0, "avg": 0.0, "total": 0.0}
    pnls = [t.dollar_pnl for t in ts]
    return {
        "n": len(ts),
        "wr": round(sum(p > 0 for p in pnls) / len(ts), 3),
        "avg": round(sum(pnls) / len(ts), 1),
        "total": round(sum(pnls), 1),
    }


def main():
    print("=" * 70)
    print("AGG vix_bear_threshold SWEEP v2 (baseline=17.3)")
    print(f"Thresholds: {THRESHOLDS}")
    print("=" * 70)

    spy_path = sorted(DATA.glob("spy_5m_2025-01-01_*.csv"),
                      key=lambda p: p.stat().st_size, reverse=True)[0]
    vix_path = DATA / spy_path.name.replace("spy_5m", "vix_5m")
    spy_df = norm_str(pd.read_csv(spy_path))
    vix_df = norm_str(pd.read_csv(vix_path))
    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    all_fill = sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})
    spy_dates = set(pd.to_datetime(spy_df["timestamp_et"].str[:10]).dt.date)
    is_days  = [d for d in all_fill if d < IS_CUTOFF and d not in MDATES_SET]
    oos_days = [d for d in all_fill if d >= IS_CUTOFF and d not in MDATES_SET and d in spy_dates]
    print(f"IS: {len(is_days)} days | OOS: {len(oos_days)} days\n")

    print(f"Running baseline (vix_bear_threshold={BASELINE_VBT})...")
    b_kw = dict(AGG_PARAMS_BASE, params_overrides={"vix_bear_threshold": BASELINE_VBT, "vix_bull_hard_cap": 18.0})
    b_is  = run_backtest(spy_df, vix_df, start_date=is_days[0],  end_date=is_days[-1],  **b_kw)
    b_oos = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1], **b_kw)
    bs = stats(b_is.trades); bso = stats(b_oos.trades)
    b_pnl_is = bs["total"]; b_pnl_oos = bso["total"]
    b_anchor = sum(t.dollar_pnl for t in b_oos.trades if t.entry_time_et.date() in ANCHOR_WINNERS)
    print(f"Baseline IS:  n={bs['n']} WR={bs['wr']:.1%} total={b_pnl_is:+.0f}")
    print(f"Baseline OOS: n={bso['n']} WR={bso['wr']:.1%} total={b_pnl_oos:+.0f}")
    print(f"Baseline anchor (4/29, 5/1, 5/4): {b_anchor:+.0f}\n")

    # Show OOS bear VIX breakdown at baseline
    print("Baseline OOS bears by VIX bucket:")
    oos_bears = [t for t in b_oos.trades if t.side == "P"]
    for label, vlo, vhi in [("[17.3-17.5)", 17.3, 17.5), ("[17.5-18)", 17.5, 18),
                              ("[18-20)", 18, 20), ("[20-22)", 20, 22), ("[22+)", 22, 999)]:
        ts = [t for t in oos_bears if vlo <= t.entry_vix < vhi]
        if ts:
            s = stats(ts)
            print(f"  VIX {label:<12} n={s['n']:2} WR={s['wr']:.1%} avg={s['avg']:+.0f} total={s['total']:+.0f}")
    print()

    print(f"  {'vbt':>5} {'IS_n':>5} {'IS_tot':>9} {'IS_D':>8} "
          f"{'OOS_n':>6} {'OOS_tot':>9} {'OOS_D':>8} {'WF':>8} {'SW':>4} {'G5':>4} {'PASS':>4}")
    print("  " + "-" * 95)

    results = []
    for vbt in THRESHOLDS:
        kw = dict(AGG_PARAMS_BASE, params_overrides={"vix_bear_threshold": vbt, "vix_bull_hard_cap": 18.0})
        r_is  = run_backtest(spy_df, vix_df, start_date=is_days[0],  end_date=is_days[-1],  **kw)
        r_oos = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1], **kw)
        s   = stats(r_is.trades)
        so  = stats(r_oos.trades)
        is_d  = round(s["total"]  - b_pnl_is,  1)
        oos_d = round(so["total"] - b_pnl_oos, 1)

        if vbt == BASELINE_VBT:
            print(f"  {vbt:>5.1f} {s['n']:>5} {s['total']:>+9.0f} {'--':>8} "
                  f"{so['n']:>6} {so['total']:>+9.0f} {'--':>8} {'--':>8} {'--':>4} {'--':>4} {'BASE':>4}")
            results.append({"vbt": vbt, "is": s, "oos": so, "verdict": "BASELINE"})
            continue

        wf = None
        if is_d != 0 and s["n"] > 0 and so["n"] > 0:
            per_is  = is_d / s["n"]
            per_oos = oos_d / so["n"]
            if per_is != 0:
                wf = round(per_oos / per_is, 3)

        sw_h = 0
        for _name, sw_start, sw_end in SW_SPLITS:
            sw_pnl = sum(t.dollar_pnl for t in r_is.trades if sw_start <= t.entry_time_et.date() <= sw_end)
            if sw_pnl < 0:
                sw_h += 1

        curr_anchor = sum(t.dollar_pnl for t in r_oos.trades if t.entry_time_et.date() in ANCHOR_WINNERS)
        anchor_tol = abs(b_anchor) * 0.10
        g5 = curr_anchor >= b_anchor - anchor_tol if b_anchor != 0 else curr_anchor >= 0

        g1 = is_d >= 0
        g2 = oos_d > 0
        g3 = wf is not None and wf >= 0.70
        g4 = sw_h <= 1
        passed = g1 and g2 and g3 and g4 and g5
        wf_str = f"{wf:.3f}" if wf is not None else "N/A"

        print(f"  {vbt:>5.1f} {s['n']:>5} {s['total']:>+9.0f} {is_d:>+8.0f} "
              f"{so['n']:>6} {so['total']:>+9.0f} {oos_d:>+8.0f} "
              f"{wf_str:>8} {sw_h:>4} {'Y' if g5 else 'N':>4} {'Y' if passed else 'N':>4}")
        print(f"       G-checks: G1={g1} G2={g2} G3={g3} G4={g4} G5={g5}  anchor={curr_anchor:+.0f}/{b_anchor:+.0f}")
        # What was removed from OOS bears?
        removed_oos = [t for t in b_oos.trades if t.side == "P" and t.entry_vix < vbt]
        if removed_oos:
            rs = stats(removed_oos)
            print(f"       OOS bears removed: n={rs['n']} total={rs['total']:+.0f} WR={rs['wr']:.1%}")
        added_oos = [t for t in r_oos.trades if t.side == "P" and t not in b_oos.trades]
        if added_oos:
            print(f"       OOS bears added: n={len(added_oos)}")

        results.append({
            "vbt": vbt, "is": s, "oos": so,
            "is_delta": is_d, "oos_delta": oos_d,
            "wf_norm": wf, "sw_hurt": sw_h, "anchor_ok": g5,
            "gates": {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5, "all": passed},
        })

    passing = [r for r in results if r.get("gates", {}).get("all")]
    best = max(passing, key=lambda r: r["oos_delta"]) if passing else None

    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)
    if best:
        print(f"  RATIFY vix_bear_threshold = {best['vbt']}")
        print(f"  IS_delta={best['is_delta']:+.0f}  OOS_delta={best['oos_delta']:+.0f}  WF={best['wf_norm']}  SW={best['sw_hurt']}")
    else:
        print("  REJECT - no candidate cleared all OP-22 gates.")
        best_oos = max((r for r in results if r.get("gates") is not None),
                       key=lambda r: r["oos_delta"], default=None)
        if best_oos:
            print(f"  Best OOS: vbt={best_oos['vbt']} OOS_D={best_oos['oos_delta']:+.0f} gates={best_oos['gates']}")

    out = {
        "task": "agg-vix-bear-threshold-v2",
        "rule_id": "agg_vix_bear_threshold",
        "description": f"AGG vix_bear_threshold sweep from 17.3 baseline, testing {THRESHOLDS}",
        "baseline_value": BASELINE_VBT,
        "sweep_results": results,
        "best": best,
        "auto_ratify": best is not None,
        "ratify_value": best["vbt"] if best else None,
        "verdict": "RATIFY" if best else "REJECT",
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")
    print("AGG VIX BEAR THRESHOLD V2 COMPLETE.")


if __name__ == "__main__":
    raise SystemExit(main())

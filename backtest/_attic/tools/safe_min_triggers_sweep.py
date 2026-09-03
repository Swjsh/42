"""SAFE min_triggers_bear sweep.

Observation from OOS loser dissection: 12/15 OOS premium stops are single-trigger
TRENDLINE_REJECTION bear entries. Current: min_triggers_bear=1 (any trigger fires).
Hypothesis: requiring min_triggers_bear=2 eliminates single-trigger bear noise.

Sweep: min_triggers_bear in [1 (baseline), 2]

Security: read-only (except output). No Alpaca calls.
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
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "safe_min_triggers_sweep.json"

IS_CUTOFF  = dt.date(2026, 2, 27)
MDATES_SET = {dt.date(2026,5,26), dt.date(2026,5,27), dt.date(2026,5,28), dt.date(2026,5,29)}
ANCHOR_WINNERS = {dt.date(2026,4,29), dt.date(2026,5,1), dt.date(2026,5,4)}

SW_SPLITS = [
    ("SW1_2025H1",  dt.date(2025,1,2),  dt.date(2025,6,30)),
    ("SW2_2025H2",  dt.date(2025,7,1),  dt.date(2025,12,31)),
    ("SW3_early26", dt.date(2026,1,2),  dt.date(2026,2,26)),
]

SAFE_BASE = dict(
    use_real_fills=True, strike_offset=-2,
    premium_stop_pct_bear=-0.10, premium_stop_pct_bull=-0.08,
    tp1_premium_pct=0.50, tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.5, f9_vol_mult=0.7,
    # min_triggers_bear swept below
    min_triggers_bull=2,
    no_trade_before=dt.time(9, 35), no_trade_window=(dt.time(11, 30), dt.time(12, 0)),
    block_level_rejection=True, block_conf_lvl_rec_afternoon=True,
    midday_trendline_gate=True, block_elite_bull=True,
    block_elite_bull_vix_low=15.0, block_elite_bull_vix_high=17.5,
    time_stop_minutes_before_close=20, per_trade_risk_cap_pct=0.3, enable_bullish=True,
    params_overrides={"vix_bear_threshold": 17.3, "vix_bull_hard_cap": 18.0},
)


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


def exit_counts(trades):
    ct = {}
    for t in trades:
        k = str(t.exit_reason).split(".")[-1]
        ct[k] = ct.get(k, 0) + 1
    return ct


def quality_tier(t):
    trig = set(t.triggers_fired or [])
    if ("confluence" in trig and "ribbon_flip" in trig) or len(trig) >= 3:
        return "SUPER"
    elif "confluence" in trig or "sequence_rejection" in trig or "sequence_reclaim" in trig:
        return "ELITE"
    elif "level_rejection" in trig or "level_reclaim" in trig:
        return "LEVEL"
    elif "trendline_rejection" in trig:
        return "TRENDLINE"
    return "BASE"


def main():
    print("=" * 70)
    print("SAFE min_triggers_bear SWEEP")
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

    print("Running baseline (min_triggers_bear=1)...")
    b_kw = dict(SAFE_BASE, min_triggers_bear=1)
    b_is  = run_backtest(spy_df, vix_df, start_date=is_days[0],  end_date=is_days[-1],  **b_kw)
    b_oos = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1], **b_kw)
    bs = stats(b_is.trades); bso = stats(b_oos.trades)
    b_pnl_is = bs["total"]; b_pnl_oos = bso["total"]
    b_anchor = sum(t.dollar_pnl for t in b_oos.trades if t.entry_time_et.date() in ANCHOR_WINNERS)
    print(f"Baseline IS: n={bs['n']} WR={bs['wr']:.1%} total={b_pnl_is:+.0f}")
    print(f"Baseline OOS: n={bso['n']} WR={bso['wr']:.1%} total={b_pnl_oos:+.0f}")
    print(f"Baseline anchor: {b_anchor:+.0f}")

    # Show baseline bear vs bull split
    b_bears_oos = [t for t in b_oos.trades if t.side == "P"]
    b_bulls_oos = [t for t in b_oos.trades if t.side == "C"]
    print(f"Baseline OOS bears: n={len(b_bears_oos)} total={sum(t.dollar_pnl for t in b_bears_oos):+.0f}")
    print(f"Baseline OOS bulls: n={len(b_bulls_oos)} total={sum(t.dollar_pnl for t in b_bulls_oos):+.0f}")

    # Show IS single-trigger bear breakdown
    b_bears_is = [t for t in b_is.trades if t.side == "P"]
    single_trig_bears_is = [t for t in b_bears_is if len(t.triggers_fired or []) == 1]
    multi_trig_bears_is  = [t for t in b_bears_is if len(t.triggers_fired or []) >= 2]
    ss = stats(single_trig_bears_is); ms = stats(multi_trig_bears_is)
    print(f"\nIS bear breakdown by trigger count:")
    print(f"  Single-trigger: n={ss['n']} WR={ss['wr']:.1%} avg={ss['avg']:+.0f} total={ss['total']:+.0f}")
    print(f"  Multi-trigger:  n={ms['n']} WR={ms['wr']:.1%} avg={ms['avg']:+.0f} total={ms['total']:+.0f}")

    # Show OOS single-trigger bear breakdown
    b_bears_oos_s = [t for t in b_bears_oos if len(t.triggers_fired or []) == 1]
    b_bears_oos_m = [t for t in b_bears_oos if len(t.triggers_fired or []) >= 2]
    sso = stats(b_bears_oos_s); mso = stats(b_bears_oos_m)
    print(f"OOS bear breakdown by trigger count:")
    print(f"  Single-trigger: n={sso['n']} WR={sso['wr']:.1%} avg={sso['avg']:+.0f} total={sso['total']:+.0f}")
    print(f"  Multi-trigger:  n={mso['n']} WR={mso['wr']:.1%} avg={mso['avg']:+.0f} total={mso['total']:+.0f}")

    print(f"\n  {'mtb':>4} {'IS_n':>5} {'IS_tot':>9} {'IS_WR':>6} {'IS_D':>8} "
          f"{'OOS_n':>6} {'OOS_tot':>9} {'OOS_WR':>7} {'OOS_D':>8} {'WF':>8} {'SW':>4} {'PASS':>4}")
    print("  " + "-" * 90)

    results = []
    for mtb in [1, 2, 3]:
        if mtb == 1:
            s, so = bs, bso
            print(f"  {mtb:>4} {s['n']:>5} {s['total']:>+9.0f} {s['wr']:>6.1%} {'--':>8} "
                  f"{so['n']:>6} {so['total']:>+9.0f} {so['wr']:>7.1%} {'--':>8} {'--':>8} {'--':>4} {'BASE':>4}")
            results.append({"mtb": mtb, "verdict": "BASELINE"})
            continue

        kw = dict(SAFE_BASE, min_triggers_bear=mtb)
        r_is  = run_backtest(spy_df, vix_df, start_date=is_days[0],  end_date=is_days[-1],  **kw)
        r_oos = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1], **kw)
        s   = stats(r_is.trades)
        so  = stats(r_oos.trades)
        is_d  = round(s["total"]  - b_pnl_is,  1)
        oos_d = round(so["total"] - b_pnl_oos, 1)

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

        print(f"  {mtb:>4} {s['n']:>5} {s['total']:>+9.0f} {s['wr']:>6.1%} {is_d:>+8.0f} "
              f"{so['n']:>6} {so['total']:>+9.0f} {so['wr']:>7.1%} {oos_d:>+8.0f} "
              f"{wf_str:>8} {sw_h:>4} {'Y' if passed else 'N':>4}")

        bears_oos = [t for t in r_oos.trades if t.side == "P"]
        bulls_oos = [t for t in r_oos.trades if t.side == "C"]
        print(f"       OOS bears: {len(bears_oos)} total={sum(t.dollar_pnl for t in bears_oos):+.0f} | "
              f"OOS bulls: {len(bulls_oos)} total={sum(t.dollar_pnl for t in bulls_oos):+.0f}")
        print(f"       OOS exits: {exit_counts(r_oos.trades)}")
        print(f"       G-checks: G1={g1} G2={g2} G3={g3} G4={g4} G5={g5}  anchor={curr_anchor:+.0f}/{b_anchor:+.0f}")

        # Show what was filtered out on OOS
        removed_oos = [t for t in b_oos.trades if t.side == "P" and len(t.triggers_fired or []) < mtb]
        if removed_oos:
            print(f"       Removed OOS bears: n={len(removed_oos)} total={sum(t.dollar_pnl for t in removed_oos):+.0f}")
            for t in removed_oos[:5]:
                trig = "+".join(sorted(t.triggers_fired or []))
                print(f"         {t.entry_time_et.date()} {t.entry_time_et.strftime('%H:%M')} "
                      f"vix={t.entry_vix:.1f} pnl={t.dollar_pnl:+.0f}  [{trig}]")

        results.append({
            "mtb": mtb, "is": s, "oos": so,
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
        print(f"  RATIFY min_triggers_bear = {best['mtb']}")
        print(f"  IS_delta={best['is_delta']:+.0f}  OOS_delta={best['oos_delta']:+.0f}  WF={best['wf_norm']}  SW={best['sw_hurt']}")
    else:
        print("  REJECT - no candidate cleared all OP-22 gates.")
        best_oos = max((r for r in results if r.get("gates") is not None),
                       key=lambda r: r["oos_delta"], default=None)
        if best_oos:
            print(f"  Best OOS: mtb={best_oos['mtb']} OOS_D={best_oos['oos_delta']:+.0f} gates={best_oos['gates']}")

    out = {
        "task": "safe-min-triggers-bear-sweep",
        "rule_id": "safe_min_triggers_bear",
        "description": "SAFE min_triggers_bear sweep [1 (baseline), 2, 3]",
        "baseline_value": 1,
        "sweep_results": results,
        "best": best,
        "auto_ratify": best is not None,
        "ratify_value": best["mtb"] if best else None,
        "verdict": "RATIFY" if best else "REJECT",
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")
    print("SAFE MIN TRIGGERS SWEEP COMPLETE.")


if __name__ == "__main__":
    raise SystemExit(main())

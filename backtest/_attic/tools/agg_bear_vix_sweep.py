"""AGG (Gamma-Bold) bear VIX threshold sweep.

AGG bear diagnostic (2026-06-18): IS n=37 WR=29.7% total=+$1551, OOS n=10 WR=20% total=-$81.
OOS bears are net NEGATIVE. SAFE bears use vix_bear_threshold=17.3 and win ~50%.
AGG bears use vix_bear_threshold=15.0 — low-VIX bears may be the losing subset.

Hypothesis: AGG bears in VIX 15-17 are low-conviction (weak momentum, range-bound price).
Raising the threshold filters low-VIX bears that are structural losers.

This script sweeps vix_bear_threshold=[15.0, 16.0, 16.5, 17.0, 17.3, 17.5, 18.0].
OP-22 gates applied at each threshold. Best candidate ratified if all 5 gates pass.
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
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "agg_bear_vix_sweep.json"

IS_CUTOFF = dt.date(2026, 2, 27)
MDATES    = {dt.date(2026,5,26), dt.date(2026,5,27), dt.date(2026,5,28), dt.date(2026,5,29)}
ANCHOR_W  = {dt.date(2026,4,29), dt.date(2026,5,1), dt.date(2026,5,4)}
SW_SPLITS = [
    ("SW1_2025H1", dt.date(2025,1,2),  dt.date(2025,6,30)),
    ("SW2_2025H2", dt.date(2025,7,1),  dt.date(2025,12,31)),
    ("SW3_early26",dt.date(2026,1,2),  dt.date(2026,2,26)),
]

# AGG baseline — all current live gates
AGG_BASE = dict(
    use_real_fills=True, strike_offset=2,
    premium_stop_pct_bear=-0.07, premium_stop_pct_bull=-0.05,
    tp1_premium_pct=0.75, tp1_qty_fraction=0.667,
    runner_target_premium_pct=5.0, f9_vol_mult=0.7,
    min_triggers_bear=1, min_triggers_bull=1,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True, block_level_rejection=True,
    block_conf_lvl_rec_afternoon=True, block_conf_lvl_rej_midday_afternoon=True,
    block_elite_bull=True, block_elite_bull_vix_low=15.0, block_elite_bull_vix_high=18.0,
    require_bearish_fill_bar=True,
    time_stop_minutes_before_close=20, per_trade_risk_cap_pct=0.5, enable_bullish=True,
    params_overrides={"vix_bear_threshold": 15.0, "vix_bull_hard_cap": 30.0},
)

THRESHOLDS = [15.0, 16.0, 16.5, 17.0, 17.3, 17.5, 18.0]


def naive(ts):
    return ts.replace(tzinfo=None) if ts.tzinfo else ts


def stats(ts):
    if not ts:
        return {"n": 0, "wr": 0.0, "avg": 0.0, "total": 0.0}
    pnls = [t.dollar_pnl for t in ts]
    return {"n": len(ts), "wr": round(sum(p > 0 for p in pnls) / len(ts), 3),
            "avg": round(sum(pnls) / len(ts), 1), "total": round(sum(pnls), 1)}


def bear_only(trades):
    return [t for t in trades if hasattr(t, "side") and t.side == "P" or
            (hasattr(t, "symbol") and "P" in str(getattr(t, "option_type", "")))]


def run_with_vix(spy_df, vix_df, days, threshold):
    kw = {k: v for k, v in AGG_BASE.items()}
    kw["params_overrides"] = {"vix_bear_threshold": threshold, "vix_bull_hard_cap": 30.0}
    return run_backtest(spy_df, vix_df, start_date=days[0], end_date=days[-1], **kw)


def main():
    print("=" * 70)
    print("AGG BEAR VIX THRESHOLD SWEEP")
    print("=" * 70)

    spy_path = sorted(DATA.glob("spy_5m_2025-01-01_*.csv"),
                      key=lambda p: p.stat().st_size, reverse=True)[0]
    vix_path = DATA / spy_path.name.replace("spy_5m", "vix_5m")
    spy_df = norm_str(pd.read_csv(spy_path))
    vix_df = norm_str(pd.read_csv(vix_path))

    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    all_fill = sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})
    spy_dates = set(pd.to_datetime(spy_df["timestamp_et"].str[:10]).dt.date)
    is_days  = [d for d in all_fill if d < IS_CUTOFF and d not in MDATES]
    oos_days = [d for d in all_fill if d >= IS_CUTOFF and d not in MDATES and d in spy_dates]
    print(f"IS: {len(is_days)} days | OOS: {len(oos_days)} days")
    print(f"Sweeping vix_bear_threshold: {THRESHOLDS}")

    # Run baseline (threshold=15.0)
    print(f"\nRunning baseline (threshold=15.0)...")
    r_ib = run_with_vix(spy_df, vix_df, is_days, 15.0)
    r_ob = run_with_vix(spy_df, vix_df, oos_days, 15.0)
    s_ib = stats(r_ib.trades)
    s_ob = stats(r_ob.trades)
    print(f"BASELINE: IS n={s_ib['n']} WR={s_ib['wr']:.1%} total={s_ib['total']:+.0f}  "
          f"OOS n={s_ob['n']} WR={s_ob['wr']:.1%} total={s_ob['total']:+.0f}")

    results = []
    best_gate_pass = None
    best_score = -999999

    for thr in THRESHOLDS[1:]:  # skip baseline 15.0
        print(f"\nRunning threshold={thr}...")
        r_ic = run_with_vix(spy_df, vix_df, is_days, thr)
        r_oc = run_with_vix(spy_df, vix_df, oos_days, thr)
        s_ic = stats(r_ic.trades)
        s_oc = stats(r_oc.trades)

        n_rem_is  = s_ib["n"] - s_ic["n"]
        n_rem_oos = s_ob["n"] - s_oc["n"]
        is_d  = round(s_ic["total"] - s_ib["total"], 1)
        oos_d = round(s_oc["total"] - s_ob["total"], 1)

        per_is  = is_d  / n_rem_is  if n_rem_is  > 0 else None
        per_oos = oos_d / n_rem_oos if n_rem_oos > 0 else None
        wf = round(per_oos / per_is, 3) if (per_is and per_oos and per_is != 0) else None

        # SW check (IS only)
        sw_hurt = 0
        sw_rows = []
        for lbl, sw_s, sw_e in SW_SPLITS:
            b_sw = sum(t.dollar_pnl for t in r_ib.trades if sw_s <= naive(t.entry_time_et).date() <= sw_e)
            c_sw = sum(t.dollar_pnl for t in r_ic.trades if sw_s <= naive(t.entry_time_et).date() <= sw_e)
            hurt = c_sw < b_sw
            if hurt:
                sw_hurt += 1
            sw_rows.append({"label": lbl, "baseline": round(b_sw,1), "candidate": round(c_sw,1),
                            "delta": round(c_sw-b_sw,1), "hurt": hurt})

        # Anchor check (OOS only)
        b_anch = sum(t.dollar_pnl for t in r_ob.trades if naive(t.entry_time_et).date() in ANCHOR_W)
        c_anch = sum(t.dollar_pnl for t in r_oc.trades if naive(t.entry_time_et).date() in ANCHOR_W)
        tol = abs(b_anch) * 0.10 if b_anch != 0 else 0
        g5 = c_anch >= b_anch - tol if b_anch != 0 else c_anch >= 0

        g1 = is_d >= 0
        g2 = oos_d > 0
        g3 = wf is not None and wf >= 0.70
        g4 = sw_hurt <= 1
        passed = g1 and g2 and g3 and g4 and g5

        wf_str = f"{wf:.3f}" if wf is not None else "N/A"
        failed = [f"G{i+1}" for i, g in enumerate([g1, g2, g3, g4, g5]) if not g]
        verdict = "RATIFY" if passed else f"REJECT ({', '.join(failed)})"

        print(f"  thr={thr}: IS n={s_ic['n']} WR={s_ic['wr']:.1%} total={s_ic['total']:+.0f}  "
              f"OOS n={s_oc['n']} WR={s_oc['wr']:.1%} total={s_oc['total']:+.0f}  "
              f"delta IS={is_d:+.0f} OOS={oos_d:+.0f}  WF={wf_str}  SW_hurt={sw_hurt}  -> {verdict}")

        row = {
            "threshold": thr,
            "is": s_ic, "oos": s_oc,
            "n_rem_is": n_rem_is, "n_rem_oos": n_rem_oos,
            "is_delta": is_d, "oos_delta": oos_d,
            "wf": wf, "sw_hurt": sw_hurt, "sw_rows": sw_rows,
            "anchor_baseline": b_anch, "anchor_candidate": c_anch,
            "gates": {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5, "all": passed},
            "verdict": "RATIFY" if passed else "REJECT",
        }
        results.append(row)

        if passed:
            # Score by OOS total as primary (we want best OOS improvement)
            score = oos_d
            if score > best_score:
                best_score = score
                best_gate_pass = row

    print("\n" + "=" * 70)
    if best_gate_pass:
        t = best_gate_pass["threshold"]
        print(f"BEST CANDIDATE: threshold={t}")
        print(f"  IS n={best_gate_pass['is']['n']} total={best_gate_pass['is']['total']:+.0f}  "
              f"OOS n={best_gate_pass['oos']['n']} total={best_gate_pass['oos']['total']:+.0f}")
        print(f"  delta IS={best_gate_pass['is_delta']:+.0f}  OOS={best_gate_pass['oos_delta']:+.0f}")
        print(f"  WF={best_gate_pass['wf']:.3f}  SW_hurt={best_gate_pass['sw_hurt']}")
        print(f"  VERDICT: RATIFY (all 5 OP-22 gates pass)")
    else:
        print("No candidate passed all 5 OP-22 gates.")
        print("All thresholds REJECTED.")

    out = {
        "task": "agg-bear-vix-threshold-sweep",
        "account": "Gamma-Bold (AGG)",
        "baseline_threshold": 15.0,
        "baseline_is": s_ib,
        "baseline_oos": s_ob,
        "sweep_results": results,
        "best_candidate": best_gate_pass,
        "verdict": "RATIFY" if best_gate_pass else "REJECT",
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")


if __name__ == "__main__":
    raise SystemExit(main())

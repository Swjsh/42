"""AGG tp1_premium_pct sweep.

Current: tp1_premium_pct=0.75 (TP1 fires when premium reaches 1.75x entry).
77% OOS premium stop rate suggests TP1 at +75% may be too high a bar.
Hypothesis: lowering TP1 to 50% or 60% converts more premium stops to
TP1+runner exits, improving OOS total P&L.

Sweep: [0.40, 0.50, 0.60, 0.75]
tp1_qty_fraction stays at 0.667 (2/3 off at TP1, 1/3 runner).
All other AGG prod params fixed (block_elite_bull_vix_high=18.0 applied).

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
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "agg_tp1_threshold_sweep.json"

IS_CUTOFF  = dt.date(2026, 2, 27)
MDATES_SET = {dt.date(2026,5,26), dt.date(2026,5,27), dt.date(2026,5,28), dt.date(2026,5,29)}
ANCHOR_WINNERS = {dt.date(2026,4,29), dt.date(2026,5,1), dt.date(2026,5,4)}

SW_SPLITS = [
    ("SW1_2025H1",  dt.date(2025,1,2),  dt.date(2025,6,30)),
    ("SW2_2025H2",  dt.date(2025,7,1),  dt.date(2025,12,31)),
    ("SW3_early26", dt.date(2026,1,2),  dt.date(2026,2,26)),
]

AGG_BASE = dict(
    use_real_fills=True, strike_offset=-2,
    premium_stop_pct_bear=-0.07, premium_stop_pct_bull=-0.05,
    # tp1_premium_pct swept below
    tp1_qty_fraction=0.667, runner_target_premium_pct=5.0,
    f9_vol_mult=0.7, min_triggers_bear=1, min_triggers_bull=1,
    no_trade_before=dt.time(9, 35), no_trade_window=None,
    block_level_rejection=True, block_conf_lvl_rec_afternoon=True,
    block_conf_lvl_rej_midday_afternoon=True, midday_trendline_gate=True,
    block_elite_bull=True, block_elite_bull_vix_low=15.0, block_elite_bull_vix_high=18.0,
    require_bearish_fill_bar=True, time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.5, enable_bullish=True,
    params_overrides={"vix_bear_threshold": 15.0},
)

BASELINE = 0.75
THRESHOLDS = [0.40, 0.50, 0.60, 0.75]


def get_fill_days():
    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    return sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})


def load_data():
    spy_path = sorted(DATA.glob("spy_5m_2025-01-01_*.csv"),
                      key=lambda p: p.stat().st_size, reverse=True)[0]
    vix_path = DATA / spy_path.name.replace("spy_5m", "vix_5m")
    spy_df = norm_str(pd.read_csv(spy_path))
    vix_df = norm_str(pd.read_csv(vix_path))
    return spy_df, vix_df


def stats(trades):
    if not trades:
        return {"n": 0, "wr": 0.0, "avg": 0.0, "total": 0.0}
    pnls = [t.dollar_pnl for t in trades]
    return {"n": len(trades), "wr": round(sum(p > 0 for p in pnls) / len(pnls), 3),
            "avg": round(sum(pnls) / len(pnls), 1),
            "total": round(sum(pnls), 1)}


def exit_breakdown(trades):
    counts = defaultdict(int)
    for t in trades:
        counts[str(t.exit_reason).split(".")[-1]] += 1
    total = len(trades)
    return {k: {"n": v, "pct": round(v/total, 3)} for k, v in sorted(counts.items(), key=lambda x: -x[1])}


def sw_hurt(sw_splits, is_trades, base_is_pnl):
    hurt = 0
    for _name, sw_start, sw_end in sw_splits:
        sw = [t for t in is_trades if sw_start <= t.entry_time_et.date() <= sw_end]
        sw_pnl = sum(t.dollar_pnl for t in sw)
        if sw_pnl < 0:
            hurt += 1
    return hurt


def main():
    print("=" * 70)
    print("AGG TP1_PREMIUM_PCT SWEEP")
    print(f"Thresholds: {THRESHOLDS}  Baseline: {BASELINE}")
    print("=" * 70)

    spy_df, vix_df = load_data()
    all_fill_days = get_fill_days()
    spy_dates = set(pd.to_datetime(spy_df["timestamp_et"].str[:10]).dt.date)
    is_days  = [d for d in all_fill_days if d < IS_CUTOFF  and d not in MDATES_SET]
    oos_days = [d for d in all_fill_days if d >= IS_CUTOFF and d not in MDATES_SET and d in spy_dates]
    print(f"IS: {len(is_days)} days ({is_days[0]} -> {is_days[-1]})")
    print(f"OOS: {len(oos_days)} days ({oos_days[0]} -> {oos_days[-1]})")

    print("\n[1] Running baseline (tp1=0.75)...")
    base_kw = dict(AGG_BASE, tp1_premium_pct=BASELINE)
    base_is_r  = run_backtest(spy_df, vix_df, start_date=is_days[0],  end_date=is_days[-1],  **base_kw)
    base_oos_r = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1], **base_kw)
    base_is_s  = stats(base_is_r.trades)
    base_oos_s = stats(base_oos_r.trades)
    base_is_pnl  = base_is_s["total"]
    base_oos_pnl = base_oos_s["total"]
    base_anchor  = sum(t.dollar_pnl for t in base_oos_r.trades
                       if t.entry_time_et.date() in ANCHOR_WINNERS)
    print(f"  Baseline: IS n={base_is_s['n']} {base_is_pnl:+.0f} | OOS n={base_oos_s['n']} {base_oos_pnl:+.0f}")

    print("\nBaseline IS exit breakdown:")
    for k, v in exit_breakdown(base_is_r.trades).items():
        print(f"  {k:<35} n={v['n']:3} ({v['pct']:4.0%})")

    print("\nBaseline OOS exit breakdown:")
    for k, v in exit_breakdown(base_oos_r.trades).items():
        print(f"  {k:<35} n={v['n']:3} ({v['pct']:4.0%})")

    print("\n[2] Sweeping tp1_premium_pct...")
    print(f"\n  {'tp1':>5} {'IS_n':>5} {'IS_tot':>9} {'IS_WR':>6} {'IS_D':>7}"
          f"{'OOS_n':>6} {'OOS_tot':>9} {'OOS_WR':>7} {'OOS_D':>8}"
          f"{'WF':>7} {'SW':>4} {'G5':>4} {'PASS':>4}")
    print(f"  {'-'*110}")

    results = []
    for tp1 in THRESHOLDS:
        if tp1 == BASELINE:
            s = base_is_s
            so = base_oos_s
            print(f"  {tp1:>5.2f} {s['n']:>5} {s['total']:>+9.0f} {s['wr']:>6.1%} {'--':>7}"
                  f"{so['n']:>6} {so['total']:>+9.0f} {so['wr']:>7.1%} {'--':>8}"
                  f"{'--':>7} {'--':>4} {'--':>4} {'BASE':>4}")
            results.append({"tp1": tp1, "is": s, "oos": so,
                             "is_delta": 0.0, "oos_delta": 0.0, "wf_norm": None,
                             "sw_hurt": 0, "anchor_ok": True, "verdict": "BASELINE"})
            continue

        kw = dict(AGG_BASE, tp1_premium_pct=tp1)
        r_is  = run_backtest(spy_df, vix_df, start_date=is_days[0],  end_date=is_days[-1],  **kw)
        r_oos = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1], **kw)
        s   = stats(r_is.trades)
        so  = stats(r_oos.trades)
        is_d  = round(s["total"]  - base_is_pnl,  1)
        oos_d = round(so["total"] - base_oos_pnl, 1)

        wf = None
        if is_d != 0 and s["n"] > 0:
            per_is  = is_d  / s["n"]
            per_oos = oos_d / so["n"]
            if per_is != 0:
                wf = round(per_oos / per_is, 3)

        sw_h = sw_hurt(SW_SPLITS, r_is.trades, base_is_pnl)
        curr_anchor = sum(t.dollar_pnl for t in r_oos.trades
                          if t.entry_time_et.date() in ANCHOR_WINNERS)
        # G5: allow 10% tolerance. Correct for negative base_anchor.
        anchor_tolerance = abs(base_anchor) * 0.10
        g5 = curr_anchor >= base_anchor - anchor_tolerance

        g1 = is_d >= 0
        g2 = oos_d > 0
        g3 = wf is not None and wf >= 0.70
        g4 = sw_h <= 1
        all_pass = g1 and g2 and g3 and g4 and g5
        wf_str = f"{wf:.3f}" if wf is not None else "N/A"

        print(f"  {tp1:>5.2f} {s['n']:>5} {s['total']:>+9.0f} {s['wr']:>6.1%} {is_d:>+7.0f}"
              f"{so['n']:>6} {so['total']:>+9.0f} {so['wr']:>7.1%} {oos_d:>+8.0f}"
              f"{wf_str:>7} {sw_h:>4} {'Y' if g5 else 'N':>4} {'Y' if all_pass else 'N':>4}")

        results.append({
            "tp1": tp1, "is": s, "oos": so,
            "is_delta": is_d, "oos_delta": oos_d,
            "wf_norm": wf, "sw_hurt": sw_h, "anchor_ok": g5,
            "gates": {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5, "all": all_pass},
            "exit_is":  exit_breakdown(r_is.trades),
            "exit_oos": exit_breakdown(r_oos.trades),
        })

    passing = [r for r in results if r.get("gates", {}).get("all")]
    best = max(passing, key=lambda r: r["oos_delta"]) if passing else None

    print(f"\n{'='*70}")
    print("VERDICT")
    print(f"{'='*70}")
    if best:
        print(f"  RATIFY tp1_premium_pct = {best['tp1']:.2f}")
        print(f"  IS_delta={best['is_delta']:+.0f}  OOS_delta={best['oos_delta']:+.0f}  "
              f"WF={best['wf_norm']}  SW={best['sw_hurt']}")
    else:
        print("  REJECT - no candidate cleared all OP-22 gates.")
        best_oos = max([r for r in results if r.get("gates") is not None],
                       key=lambda r: r["oos_delta"], default=None)
        if best_oos:
            print(f"  Best OOS: tp1={best_oos['tp1']:.2f} OOS_D={best_oos['oos_delta']:+.0f} "
                  f"gates={best_oos['gates']}")

    scorecard = {
        "task": "agg-tp1-threshold-sweep",
        "rule_id": "agg_tp1_premium_pct",
        "description": "AGG tp1_premium_pct sweep to find optimal first-take-profit threshold",
        "baseline_tp1": BASELINE,
        "thresholds_tested": THRESHOLDS,
        "is_date_range": [str(is_days[0]), str(is_days[-1])],
        "oos_date_range": [str(oos_days[0]), str(oos_days[-1])],
        "sweep_results": results,
        "best": best,
        "auto_ratify": best is not None,
        "ratify_value": best["tp1"] if best else None,
        "verdict": "RATIFY" if best else "REJECT",
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(scorecard, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")
    print("TP1 SWEEP COMPLETE.")


if __name__ == "__main__":
    raise SystemExit(main())

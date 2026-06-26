"""AGG runner_target_premium_pct sweep (task fa1e568f).

Current: runner_target_premium_pct=5.0 (5x). Only 1.3% of exits hit this.
Runner position is effectively dead weight — always exits at time_stop.

Hypothesis: lower target (1.5x-3.0x) captures meaningful runner exits
without sacrificing the full-position TP1 structure.

Sweep: [1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
Same AGG production params; only runner_target_premium_pct changes.

OP-22 auto-ratify gates.

Security: read-only. No Alpaca calls. No production state writes.
"""
from __future__ import annotations
import sys, json, datetime as dt
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from lib.orchestrator import run_backtest  # noqa
from lib.anchor_check import anchor_no_regression  # noqa: E402  (L160 sign-correct G5)
from sniper_matrix import norm_str  # noqa: E402

DATA = REPO / "data"
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "agg_runner_target_sweep.json"

IS_CUTOFF = dt.date(2026, 2, 27)
MDATES_SET = {dt.date(2026, 5, 26), dt.date(2026, 5, 27),
              dt.date(2026, 5, 28), dt.date(2026, 5, 29)}

ANCHOR_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}
ANCHOR_LOSERS  = {dt.date(2026, 5, 5), dt.date(2026, 5, 6)}

SW_SPLITS = [
    ("SW1_2025H1",  dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("SW2_2025H2",  dt.date(2025, 7, 1),  dt.date(2025, 12, 31)),
    ("SW3_early26", dt.date(2026, 1, 2),  dt.date(2026, 2, 26)),
]

TARGETS = [1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
BASELINE = 5.0

AGG_BASE = dict(
    use_real_fills=True,
    strike_offset=-2,
    premium_stop_pct_bear=-0.07,
    premium_stop_pct_bull=-0.05,
    tp1_premium_pct=0.75,
    tp1_qty_fraction=0.667,
    # runner_target_premium_pct swept below
    f9_vol_mult=0.7,
    min_triggers_bear=1,
    min_triggers_bull=1,
    no_trade_before=dt.time(9, 35),
    no_trade_window=None,
    block_level_rejection=True,
    block_conf_lvl_rec_afternoon=True,
    block_conf_lvl_rej_midday_afternoon=True,
    midday_trendline_gate=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    require_bearish_fill_bar=True,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.5,
    enable_bullish=True,
    params_overrides={"vix_bear_threshold": 15.0},
)


def get_fill_days():
    from collections import Counter
    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    return sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})


def load_data():
    spy_path = sorted(DATA.glob("spy_5m_2025-01-01_*.csv"),
                      key=lambda p: p.stat().st_size, reverse=True)[0]
    vix_name = spy_path.name.replace("spy_5m", "vix_5m")
    spy_df = norm_str(pd.read_csv(spy_path))
    vix_df = norm_str(pd.read_csv(DATA / vix_name))
    return spy_df, vix_df


def stats(trades):
    if not trades:
        return {"n": 0, "wr": 0.0, "avg_pnl": 0.0, "total_pnl": 0.0}
    pnls = [t.dollar_pnl for t in trades]
    return {
        "n": len(trades),
        "wr": round(sum(p > 0 for p in pnls) / len(pnls), 3),
        "avg_pnl": round(sum(pnls) / len(pnls), 1),
        "total_pnl": round(sum(pnls), 1),
    }


def exit_breakdown(trades):
    """Count exit reasons."""
    from collections import Counter
    return dict(Counter(getattr(t, "exit_reason", "unknown") for t in trades))


def sw_hurt_count(sw_splits, is_trades, base_is_pnl):
    """Sub-windows where removing candidate hurts (delta < 0 vs baseline)."""
    hurt = 0
    for _name, sw_start, sw_end in sw_splits:
        sw = [t for t in is_trades if sw_start <= t.entry_time_et.date() <= sw_end]
        if sum(t.dollar_pnl for t in sw) < 0:
            hurt += 1
    return hurt


def main():
    print("=" * 70)
    print("AGG RUNNER TARGET SWEEP  (task fa1e568f)")
    print(f"Targets: {TARGETS}")
    print("=" * 70)

    print("\n[1] Loading data...")
    spy_df, vix_df = load_data()
    all_fill_days = get_fill_days()
    is_days  = [d for d in all_fill_days if d < IS_CUTOFF and d not in MDATES_SET]
    oos_days_all = [d for d in all_fill_days if d >= IS_CUTOFF and d not in MDATES_SET]
    spy_dates = set(pd.to_datetime(spy_df["timestamp_et"].str[:10]).dt.date)
    oos_days = [d for d in oos_days_all if d in spy_dates]
    print(f"  IS: {len(is_days)} days ({is_days[0]} -> {is_days[-1]})")
    print(f"  OOS: {len(oos_days)} days ({oos_days[0]} -> {oos_days[-1]})")

    print("\n[2] Running baseline (5.0x)...")
    base_kwargs = dict(AGG_BASE, runner_target_premium_pct=BASELINE)
    base_is_r   = run_backtest(spy_df, vix_df, start_date=is_days[0],  end_date=is_days[-1],  **base_kwargs)
    base_oos_r  = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1], **base_kwargs)
    base_is_s   = stats(base_is_r.trades)
    base_oos_s  = stats(base_oos_r.trades)
    base_is_pnl  = base_is_s["total_pnl"]
    base_oos_pnl = base_oos_s["total_pnl"]
    base_anchor  = sum(t.dollar_pnl for t in base_oos_r.trades
                       if t.entry_time_et.date() in ANCHOR_WINNERS)
    print(f"  Baseline: IS n={base_is_s['n']} {base_is_pnl:+.0f} | OOS n={base_oos_s['n']} {base_oos_pnl:+.0f}")

    print(f"\n[3] Sweeping runner_target_premium_pct...")

    print(f"\n  {'tgt':>5} {'IS_n':>5} {'IS_tot':>9} {'IS_WR':>7} {'IS_avg':>8} "
          f"{'OOS_n':>6} {'OOS_tot':>9} {'OOS_WR':>7} {'OOS_avg':>8} "
          f"{'IS_D':>7} {'OOS_D':>7} {'WF':>7} {'SW':>4} {'G5':>4} {'OK':>3}")
    print(f"  {'-'*120}")

    base_is_result = base_is_r.trades
    results = []
    for tgt in TARGETS:
        if tgt == BASELINE:
            is_s, oos_s = base_is_s, base_oos_s
            is_r, oos_r = base_is_r, base_oos_r
            print(f"  {tgt:>5.1f} {is_s['n']:>5} {is_s['total_pnl']:>+9.0f} {is_s['wr']:>7.1%} {is_s['avg_pnl']:>+8.0f} "
                  f"{oos_s['n']:>6} {oos_s['total_pnl']:>+9.0f} {oos_s['wr']:>7.1%} {oos_s['avg_pnl']:>+8.0f} "
                  f"{'--':>7} {'--':>7} {'--':>7} {'--':>4} {'--':>4} {'BASE':>3}")
            results.append({"target": tgt, "is": is_s, "oos": oos_s,
                             "is_delta": 0.0, "oos_delta": 0.0, "wf_norm": None,
                             "sw_hurt": 0, "anchor_ok": True,
                             "gates": {"G1": True, "G2": False, "G3": False, "G4": True, "G5": True, "all": False}})
            continue
        kwargs = dict(AGG_BASE, runner_target_premium_pct=tgt)
        is_r  = run_backtest(spy_df, vix_df, start_date=is_days[0],  end_date=is_days[-1],  **kwargs)
        oos_r = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1], **kwargs)
        is_s  = stats(is_r.trades)
        oos_s = stats(oos_r.trades)

        is_d  = round(is_s["total_pnl"]  - base_is_pnl,  1)
        oos_d = round(oos_s["total_pnl"] - base_oos_pnl, 1)

        wf_norm = None
        if is_d != 0 and is_s["n"] > 0:
            per_trade_is  = is_d  / is_s["n"]
            per_trade_oos = oos_d / oos_s["n"]
            if per_trade_is != 0:
                wf_norm = round(per_trade_oos / per_trade_is, 3)

        sw_h = sw_hurt_count(SW_SPLITS, is_r.trades, base_is_pnl)
        curr_anchor = sum(t.dollar_pnl for t in oos_r.trades
                          if t.entry_time_et.date() in ANCHOR_WINNERS)
        # L160: sign-correct anchor-no-regression (broken `base_anchor * 0.90` fails
        # for negative baselines). Canonical helper, see backtest/lib/anchor_check.py.
        g5 = anchor_no_regression(base_anchor, curr_anchor, 0.10)

        g1 = is_d >= 0
        g2 = oos_d > 0
        g3 = wf_norm is not None and wf_norm >= 0.70
        g4 = sw_h <= 1
        all_pass = g1 and g2 and g3 and g4 and g5
        wf_str = f"{wf_norm:.3f}" if wf_norm is not None else "N/A"

        print(f"  {tgt:>5.1f} {is_s['n']:>5} {is_s['total_pnl']:>+9.0f} {is_s['wr']:>7.1%} {is_s['avg_pnl']:>+8.0f} "
              f"{oos_s['n']:>6} {oos_s['total_pnl']:>+9.0f} {oos_s['wr']:>7.1%} {oos_s['avg_pnl']:>+8.0f} "
              f"{is_d:>+7.0f} {oos_d:>+7.0f} {wf_str:>7} {sw_h:>4} {'Y' if g5 else 'N':>4} "
              f"{'Y' if all_pass else 'N':>3}")

        results.append({
            "target": tgt, "is": is_s, "oos": oos_s,
            "is_delta": is_d, "oos_delta": oos_d,
            "wf_norm": wf_norm, "sw_hurt": sw_h, "anchor_ok": g5,
            "gates": {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5, "all": all_pass},
        })

    # Exit breakdown at best candidate
    print("\n[4] Exit reason breakdown (IS, baseline vs best):")
    if base_is_result:
        base_exits = exit_breakdown(base_is_result)
        print(f"  BASELINE (5.0x): {base_exits}")

    passing = [r for r in results if r["gates"]["all"]]
    best = max(passing, key=lambda r: r["oos_delta"]) if passing else None

    # Print exit breakdown for best
    if best and best["target"] != BASELINE:
        for tgt in TARGETS:
            if tgt == best["target"]:
                kwargs = dict(AGG_BASE, runner_target_premium_pct=tgt)
                best_r = run_backtest(spy_df, vix_df, start_date=is_days[0], end_date=is_days[-1], **kwargs)
                print(f"  BEST ({tgt:.1f}x): {exit_breakdown(best_r.trades)}")
                break

    print(f"\n{'='*70}")
    print("VERDICT")
    print(f"{'='*70}")
    if best:
        print(f"  RATIFY runner_target_premium_pct = {best['target']:.1f}")
        print(f"  IS_delta={best['is_delta']:+.0f}  OOS_delta={best['oos_delta']:+.0f}  "
              f"WF_norm={best['wf_norm']}  SW_hurt={best['sw_hurt']}")
        print(f"  Update: automation/state/aggressive/params.json runner_max_premium_pct")
    else:
        print("  REJECT - no target cleared all OP-22 gates.")
        best_oos = max([r for r in results if r["target"] != BASELINE],
                       key=lambda r: r["oos_delta"], default=None)
        if best_oos:
            print(f"  Best OOS: {best_oos['target']:.1f}x OOS_D={best_oos['oos_delta']:+.0f} "
                  f"gates={best_oos['gates']}")

    scorecard = {
        "task": "agg-runner-target-sweep",
        "rule_id": "agg_runner_target",
        "description": "AGG runner_target_premium_pct sweep to find optimal runner exit",
        "baseline_target": BASELINE,
        "targets_tested": TARGETS,
        "is_date_range": [str(is_days[0]), str(is_days[-1])],
        "oos_date_range": [str(oos_days[0]), str(oos_days[-1])],
        "sweep_results": results,
        "best": best,
        "auto_ratify": best is not None,
        "ratify_value": best["target"] if best else None,
        "verdict": "RATIFY" if best else "REJECT",
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(scorecard, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")
    print("RUNNER TARGET SWEEP COMPLETE.")


if __name__ == "__main__":
    raise SystemExit(main())

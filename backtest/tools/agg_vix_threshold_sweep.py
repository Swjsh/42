"""AGG VIX bear threshold sweep.

Task agg-vix-*: Sweep VIX_BEAR_THRESHOLD for AGG [15.0..18.0].
Bear filter 8: blocks entry when VIX <= threshold (bear only allowed when VIX > threshold).
Current AGG prod: threshold=15.0.

Hypothesis: raising threshold to 16-17 eliminates low-VIX chop entries
(trades where VIX is marginally above 15 but not genuinely elevated) without
losing the high-VIX bear trades that have edge.

Method:
  1. Run IS (287-day standard split) and OOS (last 60 days) for each threshold.
  2. Report N, WR, avg_pnl, total, edge_capture, WF_norm.
  3. Check OP-22 gates: IS/OOS positive, WF>=0.70, SW_hurt<=1, anchor no-regression.
  4. Auto-ratify if all 5 gates pass.

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
from sniper_matrix import norm_str  # noqa: E402

DATA = REPO / "data"
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "agg_vix_threshold_sweep.json"

# Standard IS/OOS split (287 IS / last 60 OOS fill days)
IS_CUTOFF = dt.date(2026, 2, 27)
MDATES_SET = {dt.date(2026, 5, 26), dt.date(2026, 5, 27),
              dt.date(2026, 5, 28), dt.date(2026, 5, 29)}

# J's anchor trades
ANCHOR_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}
ANCHOR_LOSERS  = {dt.date(2026, 5, 5), dt.date(2026, 5, 6)}
ANCHOR_DAYS    = ANCHOR_WINNERS | ANCHOR_LOSERS

# IS sub-windows for stability check
SW_SPLITS = [
    ("SW1_2025H1",  dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("SW2_2025H2",  dt.date(2025, 7, 1),  dt.date(2025, 12, 31)),
    ("SW3_early26", dt.date(2026, 1, 2),  dt.date(2026, 2, 26)),
]

# Sweep candidates
VIX_THRESHOLDS = [15.0, 15.5, 16.0, 16.5, 17.0, 17.3, 17.5, 18.0]

# AGG production params (except vix_bear_threshold which is swept)
AGG_BASE = dict(
    use_real_fills=True,
    strike_offset=-2,
    premium_stop_pct_bear=-0.07,
    premium_stop_pct_bull=-0.05,
    tp1_premium_pct=0.75,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=5.0,
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
)


def get_fill_days():
    c = {}
    for f in (DATA / "options").glob("SPY*.csv"):
        day = f.name[3:9]
        c[day] = c.get(day, 0) + 1
    return sorted({
        dt.datetime.strptime(k, "%y%m%d").date()
        for k, v in c.items() if v >= 8
    })


def load_spy_vix():
    spy_path = sorted(DATA.glob("spy_5m_2025-01-01_*.csv"),
                      key=lambda p: p.stat().st_size, reverse=True)[0]
    vix_name = spy_path.name.replace("spy_5m", "vix_5m")
    spy_df = norm_str(pd.read_csv(spy_path))
    vix_df = norm_str(pd.read_csv(DATA / vix_name))
    print(f"  SPY: {spy_path.name}")
    return spy_df, vix_df


def stats(trades):
    if not trades:
        return {"n": 0, "wr": 0.0, "avg_pnl": 0.0, "total_pnl": 0.0}
    n = len(trades)
    pnls = [t.dollar_pnl for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    return {
        "n": n,
        "wr": round(wins / n, 3),
        "avg_pnl": round(sum(pnls) / n, 1),
        "total_pnl": round(sum(pnls), 1),
    }


def edge_capture(anchor_winners, anchor_losers, trades):
    """OP-16 edge capture: sum P&L on winner days - losses on loser days."""
    win_pnl = sum(t.dollar_pnl for t in trades if t.entry_time_et.date() in anchor_winners)
    lose_pnl = sum(max(0, -t.dollar_pnl) for t in trades if t.entry_time_et.date() in anchor_losers)
    return win_pnl - lose_pnl


def sw_hurt(sw_splits, is_trades):
    """Count IS sub-windows with negative total P&L (absolute floor check)."""
    hurt = 0
    for _name, sw_start, sw_end in sw_splits:
        sw_trades = [t for t in is_trades if sw_start <= t.entry_time_et.date() <= sw_end]
        if sum(t.dollar_pnl for t in sw_trades) < 0:
            hurt += 1
    return hurt


def main():
    print("=" * 70)
    print("AGG VIX BEAR THRESHOLD SWEEP")
    print("=" * 70)

    print("\n[1] Loading data...")
    spy_df, vix_df = load_spy_vix()

    all_fill_days = get_fill_days()
    is_days = [d for d in all_fill_days if d < IS_CUTOFF and d not in MDATES_SET]
    oos_days = [d for d in all_fill_days if d >= IS_CUTOFF and d not in MDATES_SET]
    spy_dates = set(pd.to_datetime(spy_df["timestamp_et"].str[:10]).dt.date)
    oos_days = [d for d in oos_days if d in spy_dates]

    print(f"  IS: {len(is_days)} days ({is_days[0]} to {is_days[-1]})")
    print(f"  OOS: {len(oos_days)} days ({oos_days[0]} to {oos_days[-1]})")

    # Baseline: vix_threshold=15.0 (current prod)
    print("\n[2] Running baseline (vix_threshold=15.0)...")
    base_kwargs = dict(AGG_BASE, params_overrides={"vix_bear_threshold": 15.0})
    base_is = run_backtest(spy_df, vix_df, start_date=is_days[0], end_date=is_days[-1], **base_kwargs)
    base_oos = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1], **base_kwargs)
    base_is_pnl = sum(t.dollar_pnl for t in base_is.trades)
    base_oos_pnl = sum(t.dollar_pnl for t in base_oos.trades)
    print(f"  IS n={len(base_is.trades)} total={base_is_pnl:+.0f} | OOS n={len(base_oos.trades)} total={base_oos_pnl:+.0f}")

    print("\n[3] Sweeping VIX thresholds...")
    print(f"\n  {'thresh':>7} {'IS_n':>5} {'IS_tot':>8} {'IS_WR':>6} {'IS_avg':>7} "
          f"{'OOS_n':>6} {'OOS_tot':>8} {'OOS_WR':>7} {'OOS_avg':>8} "
          f"{'IS_Δ':>7} {'OOS_Δ':>7} {'WF':>6} {'SW_hurt':>8} {'EC':>8} {'GATES':>8}")
    print(f"  {'-'*130}")

    results = []
    for thresh in VIX_THRESHOLDS:
        kwargs = dict(AGG_BASE, params_overrides={"vix_bear_threshold": thresh})
        is_result  = run_backtest(spy_df, vix_df, start_date=is_days[0], end_date=is_days[-1],  **kwargs)
        oos_result = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1], **kwargs)

        is_s  = stats(is_result.trades)
        oos_s = stats(oos_result.trades)
        is_pnl  = is_s["total_pnl"]
        oos_pnl = oos_s["total_pnl"]
        is_delta  = is_pnl  - base_is_pnl
        oos_delta = oos_pnl - base_oos_pnl

        # WF_norm: (OOS_delta/n_removed_OOS) / (IS_delta/n_removed_IS)
        n_removed_is  = len(base_is.trades)  - is_s["n"]
        n_removed_oos = len(base_oos.trades) - oos_s["n"]

        if is_delta != 0 and n_removed_is != 0:
            is_per_removed  = is_delta  / max(1, n_removed_is)
            oos_per_removed = oos_delta / max(1, n_removed_oos) if n_removed_oos != 0 else oos_delta
            wf_norm = round(oos_per_removed / is_per_removed, 3) if is_per_removed != 0 else None
        else:
            wf_norm = None

        sw_h = sw_hurt(SW_SPLITS, is_result.trades)
        ec   = round(edge_capture(ANCHOR_WINNERS, ANCHOR_LOSERS, oos_result.trades), 0)

        # OP-22 gate check
        gate1 = is_delta >= 0     # IS non-regression
        gate2 = oos_delta >= 0    # OOS positive
        gate3 = wf_norm is not None and wf_norm >= 0.70
        gate4 = sw_h <= 1
        # Gate 5: anchor no-regression: anchor-winner OOS P&L not worse than baseline
        base_anchor_pnl = sum(t.dollar_pnl for t in base_oos.trades if t.entry_time_et.date() in ANCHOR_WINNERS)
        curr_anchor_pnl = sum(t.dollar_pnl for t in oos_result.trades if t.entry_time_et.date() in ANCHOR_WINNERS)
        gate5 = curr_anchor_pnl >= base_anchor_pnl * 0.90  # 10% tolerance
        gates_pass = gate1 and gate2 and gate3 and gate4 and gate5
        gates_str = ("ALL✓" if gates_pass else
                     f"{'G1' if not gate1 else ''}{'G2' if not gate2 else ''}{'G3' if not gate3 else ''}"
                     f"{'G4' if not gate4 else ''}{'G5' if not gate5 else ''}")

        print(f"  {thresh:>7.1f} {is_s['n']:>5} {is_pnl:>+8.0f} {is_s['wr']:>6.1%} {is_s['avg_pnl']:>+7.0f} "
              f"{oos_s['n']:>6} {oos_pnl:>+8.0f} {oos_s['wr']:>7.1%} {oos_s['avg_pnl']:>+8.0f} "
              f"{is_delta:>+7.0f} {oos_delta:>+7.0f} {str(wf_norm) if wf_norm else 'N/A':>6} "
              f"{sw_h:>8} {ec:>+8.0f} {gates_str:>8}")

        results.append({
            "vix_threshold": thresh,
            "is": is_s,
            "oos": oos_s,
            "is_delta": round(is_delta, 1),
            "oos_delta": round(oos_delta, 1),
            "wf_norm": wf_norm,
            "sw_hurt": sw_h,
            "edge_capture_oos": float(ec),
            "gates": {"G1_is_nonneg": gate1, "G2_oos_pos": gate2,
                      "G3_wf": gate3, "G4_sw": gate4, "G5_anchor": gate5,
                      "all_pass": gates_pass},
        })

    # Anchor day P&L breakdown for best candidate
    print("\n[4] Anchor day breakdown (OOS):")
    for r in results:
        if r["gates"]["all_pass"]:
            print(f"  thresh={r['vix_threshold']:.1f} passes all OP-22 gates!")

    # Best candidate: max OOS P&L among gate-passing, else max OOS among all
    passing = [r for r in results if r["gates"]["all_pass"]]
    best = max(passing, key=lambda r: r["oos"]["total_pnl"]) if passing else \
           max(results, key=lambda r: r["oos"]["total_pnl"])

    print(f"\n[5] Best candidate: thresh={best['vix_threshold']} "
          f"(IS Δ={best['is_delta']:+.0f}, OOS Δ={best['oos_delta']:+.0f}, "
          f"WF={best['wf_norm']}, SW_hurt={best['sw_hurt']})")

    # Verdict
    verdict = "RATIFY" if best["gates"]["all_pass"] else "REJECT"
    print(f"\nVERDICT: {verdict}")
    if best["gates"]["all_pass"]:
        print(f"  → Set aggressive/params.json vix_entry_thresholds.bear_min_exclusive_and_rising = {best['vix_threshold']}")

    scorecard = {
        "task": "agg-vix-threshold-sweep",
        "rule_id": "agg_vix_threshold_sweep",
        "description": "AGG VIX_BEAR_THRESHOLD sweep to find optimal min-VIX for bear entries",
        "baseline_thresh": 15.0,
        "baseline_is_pnl": round(base_is_pnl, 1),
        "baseline_oos_pnl": round(base_oos_pnl, 1),
        "is_days": len(is_days),
        "oos_days": len(oos_days),
        "sweep_results": results,
        "best_candidate": best,
        "verdict": verdict,
        "auto_ratify": best["gates"]["all_pass"],
        "ratify_value": best["vix_threshold"] if best["gates"]["all_pass"] else None,
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(scorecard, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")
    print("AGG VIX THRESHOLD SWEEP COMPLETE.")


if __name__ == "__main__":
    raise SystemExit(main())

"""AGG VIX bear threshold sweep v2 — uses t.entry_vix (real entry-bar VIX).

The previous sweep (agg_vix_bear_threshold_sweep.py) was broken: the post-hoc
CSV lookup returned None for most trades, so no trades were ever filtered.
Fix: TradeFill.entry_vix is already populated by the engine with the real VIX
at the entry bar. Use that directly — no CSV lookup needed.

Method: run engine ONCE per period at baseline (threshold=15.0).
Then post-filter by t.entry_vix for each candidate threshold. O(8) instead of O(8*runs).

OP-22 auto-ratify gates:
  G1: IS_delta >= 0        (no IS regression)
  G2: OOS_delta > 0        (OOS improvement)
  G3: WF_norm >= 0.70      (improvement generalizes)
  G4: SW_hurt <= 1         (stable across sub-windows)
  G5: anchor no-regression (J anchor winners preserved)

Security: read-only. No Alpaca calls. No production state writes.
"""
from __future__ import annotations
import sys, json, datetime as dt
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from lib.orchestrator import run_backtest  # noqa
from sniper_matrix import norm_str  # noqa: E402

DATA = REPO / "data"
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "agg_vix_threshold_sweep.json"

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

THRESHOLDS = [15.0, 15.5, 16.0, 16.5, 17.0, 17.3, 17.5, 18.0]
BASELINE = 15.0

AGG_KWARGS = dict(
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
    params_overrides={"vix_bear_threshold": BASELINE},
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


def run_period(spy_df, vix_df, start, end, label):
    print(f"  [{label}] {start} -> {end} ...", end=" ", flush=True)
    r = run_backtest(spy_df, vix_df, start_date=start, end_date=end, **AGG_KWARGS)
    print(f"n={len(r.trades)} total={sum(t.dollar_pnl for t in r.trades):+.0f}")
    return r.trades


def apply_threshold(trades, threshold):
    """Post-hoc: remove bear trades that would have been blocked at this threshold."""
    return [t for t in trades
            if t.side != "P" or (t.entry_vix is not None and t.entry_vix > threshold)]


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


def sw_hurt_count(sw_splits, all_is_trades, threshold):
    hurt = 0
    for _name, sw_start, sw_end in sw_splits:
        sw_base = [t for t in all_is_trades if sw_start <= t.entry_time_et.date() <= sw_end]
        sw_thr  = apply_threshold(sw_base, threshold)
        # hurt if blocked trades cost us money (removing them reduces P&L)
        base_pnl = sum(t.dollar_pnl for t in sw_base)
        thr_pnl  = sum(t.dollar_pnl for t in sw_thr)
        if thr_pnl < base_pnl:
            hurt += 1
    return hurt


def main():
    print("=" * 72)
    print("AGG VIX BEAR THRESHOLD SWEEP v2  (t.entry_vix post-hoc method)")
    print("=" * 72)

    print("\n[1] Loading data...")
    spy_df, vix_df = load_data()

    all_fill_days = get_fill_days()
    is_days  = [d for d in all_fill_days if d < IS_CUTOFF and d not in MDATES_SET]
    oos_days_all = [d for d in all_fill_days if d >= IS_CUTOFF and d not in MDATES_SET]
    spy_dates = set(pd.to_datetime(spy_df["timestamp_et"].str[:10]).dt.date)
    oos_days = [d for d in oos_days_all if d in spy_dates]

    print(f"  IS:  {len(is_days)} days ({is_days[0]} -> {is_days[-1]})")
    print(f"  OOS: {len(oos_days)} days ({oos_days[0]} -> {oos_days[-1]})")

    print("\n[2] Running baseline engine (once per period, threshold=15.0)...")
    is_trades  = run_period(spy_df, vix_df, is_days[0],  is_days[-1],  "IS")
    oos_trades = run_period(spy_df, vix_df, oos_days[0], oos_days[-1], "OOS")

    # VIX distribution for bear trades (entry_vix)
    bear_is  = [t for t in is_trades  if t.side == "P"]
    bear_oos = [t for t in oos_trades if t.side == "P"]

    print(f"\n[3] IS bear trade entry_vix distribution (n={len(bear_is)}):")
    for lo, hi in [(0, 15), (15, 16), (16, 17), (17, 18), (18, 20), (20, 30), (30, 99)]:
        bkt = [t for t in bear_is if lo <= t.entry_vix < hi]
        if bkt:
            wr = sum(t.dollar_pnl > 0 for t in bkt) / len(bkt)
            print(f"  VIX [{lo:2.0f}-{hi:2.0f}): n={len(bkt):3} WR={wr:5.1%} "
                  f"total={sum(t.dollar_pnl for t in bkt):+8.0f}")

    print(f"\n[4] OOS bear trade entry_vix distribution (n={len(bear_oos)}):")
    for lo, hi in [(0, 15), (15, 16), (16, 17), (17, 18), (18, 20), (20, 30), (30, 99)]:
        bkt = [t for t in bear_oos if lo <= t.entry_vix < hi]
        if bkt:
            wr = sum(t.dollar_pnl > 0 for t in bkt) / len(bkt)
            print(f"  VIX [{lo:2.0f}-{hi:2.0f}): n={len(bkt):3} WR={wr:5.1%} "
                  f"total={sum(t.dollar_pnl for t in bkt):+8.0f}")

    base_is_stat  = stats(is_trades)
    base_oos_stat = stats(oos_trades)
    base_anchor_pnl = sum(t.dollar_pnl for t in oos_trades
                          if t.entry_time_et.date() in ANCHOR_WINNERS)

    print(f"\n[5] Threshold sweep:")
    print(f"\n  {'thr':>5} {'IS_n':>5} {'IS_tot':>8} {'IS_WR':>6} {'IS_D':>7}"
          f"{'OOS_n':>5} {'OOS_tot':>8} {'OOS_WR':>6} {'OOS_D':>8}"
          f"{'WF':>7} {'SW':>4} {'G5':>4} {'PASS?':>6}")
    print(f"  {'-'*110}")

    results = []
    for thr in THRESHOLDS:
        is_t  = apply_threshold(is_trades, thr)
        oos_t = apply_threshold(oos_trades, thr)
        is_s  = stats(is_t)
        oos_s = stats(oos_t)
        is_d  = round(is_s["total_pnl"] - base_is_stat["total_pnl"], 1)
        oos_d = round(oos_s["total_pnl"] - base_oos_stat["total_pnl"], 1)
        n_rem_is  = base_is_stat["n"]  - is_s["n"]
        n_rem_oos = base_oos_stat["n"] - oos_s["n"]

        wf_norm = None
        if n_rem_is > 0 and is_d != 0 and n_rem_oos > 0:
            per_is  = is_d  / n_rem_is
            per_oos = oos_d / n_rem_oos
            if per_is != 0:
                wf_norm = round(per_oos / per_is, 3)

        sw_h = sw_hurt_count(SW_SPLITS, is_trades, thr)
        curr_anchor = sum(t.dollar_pnl for t in oos_t
                          if t.entry_time_et.date() in ANCHOR_WINNERS)
        g5 = curr_anchor >= base_anchor_pnl * 0.90

        g1 = is_d >= 0
        g2 = oos_d > 0
        g3 = wf_norm is not None and wf_norm >= 0.70
        g4 = sw_h <= 1
        all_pass = g1 and g2 and g3 and g4 and g5
        wf_str = f"{wf_norm:.3f}" if wf_norm is not None else "N/A"
        flag = "Y" if all_pass else ""

        print(f"  {thr:>5.1f} {is_s['n']:>5} {is_s['total_pnl']:>+8.0f} {is_s['wr']:>6.1%} {is_d:>+7.0f} "
              f"{oos_s['n']:>5} {oos_s['total_pnl']:>+8.0f} {oos_s['wr']:>6.1%} {oos_d:>+8.0f} "
              f"{wf_str:>7} {sw_h:>4} {'Y' if g5 else 'N':>4} {flag:>6}")

        results.append({
            "vix_threshold": thr,
            "is": is_s, "oos": oos_s,
            "is_delta": is_d, "oos_delta": oos_d,
            "n_removed_is": n_rem_is, "n_removed_oos": n_rem_oos,
            "wf_norm": wf_norm, "sw_hurt": sw_h,
            "anchor_ok": g5,
            "gates": {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5, "all": all_pass},
        })

    # Best candidate
    passing = [r for r in results if r["gates"]["all"] and r["vix_threshold"] != BASELINE]
    best = max(passing, key=lambda r: r["oos_delta"]) if passing else None

    print(f"\n{'='*72}")
    print("VERDICT")
    print(f"{'='*72}")
    if best:
        print(f"  RATIFY vix_bear_threshold = {best['vix_threshold']:.1f}")
        print(f"  IS_delta={best['is_delta']:+.0f}  OOS_delta={best['oos_delta']:+.0f}  "
              f"WF_norm={best['wf_norm']}  SW_hurt={best['sw_hurt']}")
        print(f"  Update: automation/state/aggressive/params.json")
        print(f"    vix_entry_thresholds.bear_min_exclusive_and_rising -> {best['vix_threshold']:.1f}")
    else:
        print("  REJECT - no candidate cleared all OP-22 gates.")
        # Print gate failures for best OOS
        best_oos = max([r for r in results if r["vix_threshold"] != BASELINE],
                       key=lambda r: r["oos_delta"], default=None)
        if best_oos:
            print(f"  Best by OOS: thr={best_oos['vix_threshold']:.1f} "
                  f"OOS_D={best_oos['oos_delta']:+.0f} gates={best_oos['gates']}")

    scorecard = {
        "task": "agg-vix-threshold-sweep-v2",
        "rule_id": "agg_vix_threshold_sweep",
        "method": "post-hoc filter on t.entry_vix (real entry-bar VIX, no CSV lookup)",
        "baseline_threshold": BASELINE,
        "baseline_is": base_is_stat,
        "baseline_oos": base_oos_stat,
        "is_date_range": [str(is_days[0]), str(is_days[-1])],
        "oos_date_range": [str(oos_days[0]), str(oos_days[-1])],
        "sweep_results": results,
        "best": {"threshold": best["vix_threshold"], **best} if best else None,
        "auto_ratify": best is not None,
        "ratify_value": best["vix_threshold"] if best else None,
        "verdict": "RATIFY" if best else "REJECT",
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(scorecard, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")
    print("SWEEP COMPLETE.")


if __name__ == "__main__":
    raise SystemExit(main())

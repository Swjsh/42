"""
LEVEL_QUALITY_STRATIFICATION (task 0305fa60)
Classify IS/OOS TL-only trades by distance from rejection_level.
Hypothesis: trades entering >1.50 away from level (overshoot) have lower WR.
Buckets: 0-0.50, 0.50-1.50, 1.50+
NO code changes.
"""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest"))

import pandas as pd
from lib.orchestrator import run_backtest

MASTER_SPY = ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
MASTER_VIX = ROOT / "backtest" / "data" / "vix_5m_2025-01-01_2026-06-16.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 6, 16)

SAFE_BASE = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    midday_trendline_gate_start_minutes=690,
    tp1_qty_fraction=0.667,
    tp1_premium_pct=0.50,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    params_overrides={"vix_bull_max": 18.0},
)

BUCKETS = [
    ("tight (0-0.50)",   0.0,  0.50),
    ("mid (0.50-1.50)",  0.50, 1.50),
    ("overshoot (1.50+)", 1.50, 999.0),
]


def has_level_trigger(t) -> bool:
    """Trade has at least one named-level trigger (level_rejection or level_reclaim)."""
    if not t.triggers_fired:
        return False
    return any(
        "level_rejection" in tr.lower() or "level_reclaim" in tr.lower()
        for tr in t.triggers_fired
    )


def has_rejection_level(t) -> bool:
    """Trade has a valid rejection_level (not None or 0)."""
    return t.rejection_level is not None and t.rejection_level != 0 and t.rejection_level < 999


def level_distance(t) -> float:
    """Distance between entry_spot and rejection_level (abs). 999 = no level."""
    if not has_rejection_level(t):
        return 999.0
    return abs(t.entry_spot - t.rejection_level)


def bucket(dist) -> str:
    for label, lo, hi in BUCKETS:
        if lo <= dist < hi:
            return label
    return "overshoot (1.50+)"


def analyze(trades, label):
    # Trades with a named level set (rejection_level is populated)
    level_trades = [t for t in trades if has_rejection_level(t)]
    # TL-only trades (no named-level trigger) — these won't have rejection_level set
    tl_only = [t for t in trades if not has_level_trigger(t)]
    all_n = len(level_trades)

    print(f"\n{'='*60}")
    print(f"  {label} — trades WITH named rejection_level")
    print(f"{'='*60}")
    print(f"  Level trades: {all_n} / {len(trades)} total")
    print(f"  TL-only (no level trigger, excluded): {len(tl_only)}")
    if all_n == 0:
        print("  (no level trades)")
        return

    # Override 'tl_trades' alias for rest of function
    tl_trades = level_trades
    all_n = len(tl_trades)

    if all_n == 0:
        print("  (no TL-only trades)")
        return

    print(f"\n  {'Bucket':<25}  {'n':>4}  {'WR':>6}  {'avg_pnl':>9}  {'total_pnl':>10}  {'loss_pct':>8}")
    print(f"  {'-'*25}  {'----':>4}  {'------':>6}  {'---------':>9}  {'----------':>10}  {'--------':>8}")

    all_dists = [level_distance(t) for t in tl_trades]
    for bucket_label, lo, hi in BUCKETS:
        grp = [t for t in tl_trades if lo <= level_distance(t) < hi]
        if not grp:
            print(f"  {bucket_label:<25}  {'0':>4}  {'---':>6}  {'---':>9}  {'---':>10}  {'---':>8}")
            continue
        winners = [t for t in grp if t.dollar_pnl >= 0]
        wr = len(winners) / len(grp) * 100
        avg_pnl = sum(t.dollar_pnl for t in grp) / len(grp)
        total_pnl = sum(t.dollar_pnl for t in grp)
        losers = [t for t in grp if t.dollar_pnl < 0]
        loss_pct = len(losers) / len(grp) * 100
        print(f"  {bucket_label:<25}  {len(grp):>4}  {wr:>5.1f}%  {avg_pnl:>+9.0f}  {total_pnl:>+10,.0f}  {loss_pct:>7.1f}%")

    # Also print all level trades for context
    print(f"\n  All level trades: n={all_n}  WR={len([t for t in tl_trades if t.dollar_pnl>=0])/all_n*100:.1f}%  avg={sum(t.dollar_pnl for t in tl_trades)/all_n:+.0f}  total={sum(t.dollar_pnl for t in tl_trades):+,.0f}")

    # Distance statistics
    valid_dists = [d for d in all_dists if d < 999]
    if valid_dists:
        import statistics
        print(f"  Distance stats: min={min(valid_dists):.2f}  median={statistics.median(valid_dists):.2f}  max={max(valid_dists):.2f}  mean={sum(valid_dists)/len(valid_dists):.2f}")

    # Proposed filter: if overshoot (1.50+) has clearly lower WR, estimate impact
    overshoot = [t for t in tl_trades if level_distance(t) >= 1.50]
    non_overshoot = [t for t in tl_trades if level_distance(t) < 1.50]
    if overshoot and non_overshoot:
        print(f"\n  Gate proposal: block overshoot (dist>=1.50)")
        os_wr = len([t for t in overshoot if t.dollar_pnl >= 0]) / len(overshoot) * 100
        nos_wr = len([t for t in non_overshoot if t.dollar_pnl >= 0]) / len(non_overshoot) * 100
        os_pnl = sum(t.dollar_pnl for t in overshoot)
        nos_pnl = sum(t.dollar_pnl for t in non_overshoot)
        print(f"    overshoot    n={len(overshoot):3d}  WR={os_wr:.1f}%  total={os_pnl:+,.0f}")
        print(f"    non-overshoot n={len(non_overshoot):3d}  WR={nos_wr:.1f}%  total={nos_pnl:+,.0f}")
        pnl_delta = nos_pnl - (os_pnl + nos_pnl)  # removing overshoot = -os_pnl
        print(f"    Blocking overshoot would change total by: {-os_pnl:+,.0f}")
        if os_pnl < -100:
            print(f"    -> Overshoot DRAGS total. Filter would ADD {-os_pnl:+,.0f}")
        elif os_pnl > 100:
            print(f"    -> Overshoot HELPS total. Filter would LOSE {os_pnl:+,.0f} — NOT recommended")
        else:
            print(f"    -> Overshoot near breakeven. Insufficient signal.")


def main():
    print("Loading data...")
    spy_df = pd.read_csv(MASTER_SPY)
    vix_df = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy_df)} rows  VIX {len(vix_df)} rows")

    print("\nRunning IS...")
    r_is = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, **SAFE_BASE)
    print(f"  IS trades: {len(r_is.trades)}")

    print("\nRunning OOS...")
    r_oos = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, **SAFE_BASE)
    print(f"  OOS trades: {len(r_oos.trades)}")

    # Show trigger composition to verify TL-only detection
    print("\nTrigger composition sample:")
    from collections import Counter
    all_t = r_is.trades + r_oos.trades
    trigger_sets = Counter(tuple(sorted(t.triggers_fired or [])) for t in all_t)
    for combo, cnt in trigger_sets.most_common(8):
        print(f"  {list(combo)}: n={cnt}")

    analyze(r_is.trades, "IS")
    analyze(r_oos.trades, "OOS")

    print("\nDONE.")


if __name__ == "__main__":
    main()

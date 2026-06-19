"""
Trendline Age Analysis -- tests kitchen's TRENDLINE_AGE_FILTER hypothesis.

Hypothesis: BEARISH_REJECTION trades where the confirming trendline's MOST RECENT
pivot was formed recently (< 20 bars ago) have higher WR than those with stale
pivots (40+ bars ago).

Method:
1. Run IS backtest to get all BEARISH_REJECTION trendline_rejection trades.
2. For each trade's signal bar, re-run the pivot-finding algorithm to extract
   the most recent pivot's position.
3. Compute "most_recent_pivot_age" = bars between newest pivot and signal bar.
4. Bucket by age and report WR/avg P&L.
5. Test candidate gate: require most_recent_pivot_age <= THRESHOLD.

Note: This is a POST-HOC analysis. Any gate must be validated with IS/OOS/WF
before ratification.
"""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest"))

import pandas as pd
import numpy as np
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
    premium_stop_pct_bear=-0.10,
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

LOOKBACK_BARS = 60
MIN_SWINGS = 3
MIN_BAR_SEPARATION = 10


def find_trendline_pivots(prior_bars: pd.DataFrame, bar_idx: int):
    """
    Replicate the pivot-finding algorithm from detect_trendline_rejection_bearish.
    Returns list of (absolute_bar_idx, high_value) or None if no trendline.
    """
    start = max(0, bar_idx - LOOKBACK_BARS)
    window = prior_bars.iloc[start:bar_idx]
    if len(window) < MIN_SWINGS * 5:
        return None

    highs = window["high"].values
    pivots = []
    search_start = 0
    for _ in range(MIN_SWINGS):
        if search_start >= len(highs):
            break
        sub_highs = highs[search_start:]
        if len(sub_highs) == 0:
            break
        rel_pos = int(sub_highs.argmax())
        pos = search_start + rel_pos
        val = float(highs[pos])
        if pivots and val >= pivots[-1][1]:
            return None  # not descending
        pivots.append((start + pos, val))  # absolute bar index
        search_start = pos + MIN_BAR_SEPARATION

    if len(pivots) < MIN_SWINGS:
        return None
    return pivots


def build_spy_ts_index(spy_df: pd.DataFrame) -> dict:
    """Map timestamp_et string (minute precision) -> row index."""
    ts_col = "timestamp_et" if "timestamp_et" in spy_df.columns else "datetime"
    idx = {}
    for i, row in spy_df.iterrows():
        ts = str(row[ts_col])[:16]
        idx[ts] = i
    return idx


def main():
    print("Loading data...")
    spy_df = pd.read_csv(MASTER_SPY)
    vix_df = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy_df)} rows  VIX {len(vix_df)} rows")

    print("Building timestamp index...")
    ts_idx = build_spy_ts_index(spy_df)

    print("Running IS backtest...")
    result = run_backtest(
        spy_df, vix_df,
        start_date=IS_START, end_date=IS_END,
        **SAFE_BASE,
    )
    is_trades = result.trades
    print(f"IS total: n={len(is_trades)}")

    print("Running OOS backtest...")
    oos_result = run_backtest(
        spy_df, vix_df,
        start_date=OOS_START, end_date=OOS_END,
        **SAFE_BASE,
    )
    oos_trades = oos_result.trades
    print(f"OOS total: n={len(oos_trades)}")

    # Analyze trendline age for each trade
    def analyze_trades(trades, label):
        print(f"\n=== {label} ({len(trades)} total trades) ===")
        print(f"  Mapping entry timestamps to signal bars (fill_bar-1 per L127)...")

        records = []
        no_bar_found = 0
        for t in trades:
            # Per L127: t.entry_time_et is the FILL bar (N+1) timestamp.
            # Signal bar (N) = one DataFrame row earlier.
            entry_ts = str(t.entry_time_et)[:16]
            fill_idx = ts_idx.get(entry_ts)
            if fill_idx is None:
                no_bar_found += 1
                continue

            signal_idx = fill_idx - 1  # signal bar is one row before fill bar
            if signal_idx < LOOKBACK_BARS + 5:
                continue

            prior_bars = spy_df.iloc[:signal_idx]
            pivots = find_trendline_pivots(prior_bars, signal_idx)

            if pivots is None:
                # No descending trendline at this bar — trade was level_rejection only
                most_recent_age = None
            else:
                most_recent_pivot_abs_idx = pivots[-1][0]
                most_recent_age = signal_idx - most_recent_pivot_abs_idx

            records.append({
                "entry_ts": entry_ts,
                "pnl": t.dollar_pnl,
                "win": t.dollar_pnl > 0,
                "most_recent_age": most_recent_age,
            })

        if no_bar_found:
            print(f"  WARNING: {no_bar_found} trades had no matching SPY bar (timestamp mismatch)")

        # Filter to trades where trendline was found
        tl_records = [r for r in records if r["most_recent_age"] is not None]
        no_tl_records = [r for r in records if r["most_recent_age"] is None]
        print(f"  Trendline found: {len(tl_records)}/{len(records)} trades")
        print(f"  No trendline (level_rejection or missing data): {len(no_tl_records)}")

        if not tl_records:
            print("  No trendline trades to analyze.")
            return

        ages = [r["most_recent_age"] for r in tl_records]
        print(f"  Age distribution: min={min(ages)}, max={max(ages)}, median={np.median(ages):.0f}")

        # Bucket by age
        buckets = [(0, 10), (10, 20), (20, 30), (30, 40), (40, 60), (60, 999)]
        print(f"\n  {'Age Bucket':>15}  {'N':>5}  {'WR%':>6}  {'Avg P&L':>9}  {'Total P&L':>11}")
        print(f"  {'-'*60}")
        for lo, hi in buckets:
            bucket = [r for r in tl_records if lo <= r["most_recent_age"] < hi]
            if not bucket:
                continue
            n = len(bucket)
            wr = sum(1 for r in bucket if r["win"]) / n
            avg_pnl = sum(r["pnl"] for r in bucket) / n
            total_pnl = sum(r["pnl"] for r in bucket)
            label_s = f"{lo}-{hi if hi < 999 else '+'} bars"
            print(f"  {label_s:>15}  {n:>5}  {wr:>6.1%}  {avg_pnl:>+9,.0f}  {total_pnl:>+11,.0f}")

        # Gate analysis
        print(f"\n  Gate analysis (require most_recent_age <= THRESHOLD):")
        print(f"  {'Threshold':>12}  {'N_keep':>7}  {'N_skip':>7}  {'PnL_keep':>10}  {'PnL_skip':>10}  {'WR_keep':>8}")
        for threshold in [10, 15, 20, 25, 30, 40]:
            keep = [r for r in tl_records if r["most_recent_age"] <= threshold]
            skip = [r for r in tl_records if r["most_recent_age"] > threshold]
            if not keep or not skip:
                continue
            wr_keep = sum(1 for r in keep if r["win"]) / len(keep)
            pnl_keep = sum(r["pnl"] for r in keep)
            pnl_skip = sum(r["pnl"] for r in skip)
            print(f"  age<={threshold:>2} bars  {len(keep):>7}  {len(skip):>7}  {pnl_keep:>+10,.0f}  {pnl_skip:>+10,.0f}  {wr_keep:>8.1%}")

    analyze_trades(is_trades, "IS")
    analyze_trades(oos_trades, "OOS")

    print("\n\nDONE. Interpret: IS gate should keep high P&L, skip losers. OOS must be validated.")


if __name__ == "__main__":
    main()

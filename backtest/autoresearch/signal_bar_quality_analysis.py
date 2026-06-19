"""
Signal bar body/wick quality analysis.
Tests kitchen hypothesis: signal bars with high body_pct (strong momentum candle)
predict winning BEARISH_REJECTION trades.

Metrics per signal bar:
  body_pct = abs(close - open) / (high - low) * 100  [% of range that is body]
  upper_wick_pct = (high - max(open, close)) / (high - low) * 100
  is_bearish_body = close < open  [signal bar should be red for BEARISH_REJECTION]
  range_dollars = high - low

Post-hoc analysis. Gate candidates require IS/OOS/WF validation.
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


def build_ts_index(spy_df):
    ts_col = "timestamp_et" if "timestamp_et" in spy_df.columns else "datetime"
    return {str(row[ts_col])[:16]: i for i, row in spy_df.iterrows()}


def get_signal_bar(spy_df, ts_idx, fill_ts_str):
    fill_idx = ts_idx.get(fill_ts_str[:16])
    if fill_idx is None or fill_idx < 2:
        return None
    return spy_df.iloc[fill_idx - 1]  # signal bar is one row before fill bar (L127)


def bar_metrics(bar):
    o, h, l, c = float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])
    rng = h - l
    if rng < 0.01:
        return None
    body = abs(c - o)
    body_pct = body / rng * 100
    upper_wick = (h - max(o, c)) / rng * 100
    lower_wick = (min(o, c) - l) / rng * 100
    return {
        "body_pct": body_pct,
        "upper_wick_pct": upper_wick,
        "lower_wick_pct": lower_wick,
        "range_dollars": rng,
        "is_bearish_body": c < o,
    }


def analyze(trades, spy_df, ts_idx, label):
    print(f"\n=== {label} (n={len(trades)}) ===")

    records = []
    for t in trades:
        entry_ts = str(t.entry_time_et)[:16]
        bar = get_signal_bar(spy_df, ts_idx, entry_ts)
        if bar is None:
            continue
        m = bar_metrics(bar)
        if m is None:
            continue
        m["pnl"] = t.dollar_pnl
        m["win"] = t.dollar_pnl > 0
        records.append(m)

    print(f"  Matched {len(records)}/{len(trades)} trades to signal bars")
    if not records:
        return

    # Body pct distribution
    bp = [r["body_pct"] for r in records]
    wins = [r for r in records if r["win"]]
    losses = [r for r in records if not r["win"]]
    print(f"  body_pct: median={np.median(bp):.1f}%, min={min(bp):.1f}%, max={max(bp):.1f}%")
    print(f"  Winners body_pct median: {np.median([r['body_pct'] for r in wins]):.1f}%  (n={len(wins)})")
    print(f"  Losers  body_pct median: {np.median([r['body_pct'] for r in losses]):.1f}%  (n={len(losses)})")

    # Bearish body rate
    bear_body = sum(1 for r in records if r["is_bearish_body"])
    print(f"  Signal bar bearish (close<open): {bear_body}/{len(records)} ({bear_body/len(records):.1%})")
    bear_wr = sum(1 for r in records if r["is_bearish_body"] and r["win"]) / max(1, bear_body)
    bull_body_n = len(records) - bear_body
    bull_wr = sum(1 for r in records if not r["is_bearish_body"] and r["win"]) / max(1, bull_body_n)
    print(f"  WR bearish body: {bear_wr:.1%}  WR bullish body: {bull_wr:.1%}")

    # Bucket by body_pct
    buckets = [(0, 25), (25, 40), (40, 55), (55, 70), (70, 100)]
    print(f"\n  {'Body%':>10}  {'N':>5}  {'WR%':>6}  {'Avg P&L':>9}  {'Total P&L':>11}")
    print(f"  {'-'*50}")
    for lo, hi in buckets:
        b = [r for r in records if lo <= r["body_pct"] < hi]
        if not b:
            continue
        wr = sum(1 for r in b if r["win"]) / len(b)
        avg_pnl = sum(r["pnl"] for r in b) / len(b)
        tot_pnl = sum(r["pnl"] for r in b)
        print(f"  {lo:>3}-{hi:>3}%       {len(b):>5}  {wr:>6.1%}  {avg_pnl:>+9,.0f}  {tot_pnl:>+11,.0f}")

    # Gate analysis: require body_pct >= threshold
    print(f"\n  Gate (require body_pct >= threshold):")
    print(f"  {'Threshold':>12}  {'N_keep':>7}  {'N_skip':>7}  {'PnL_keep':>10}  {'PnL_skip':>10}  {'WR_keep':>8}")
    for thr in [30, 40, 50, 60, 70]:
        keep = [r for r in records if r["body_pct"] >= thr]
        skip = [r for r in records if r["body_pct"] < thr]
        if not keep or not skip:
            continue
        wr = sum(1 for r in keep if r["win"]) / len(keep)
        print(f"  body>={thr:>2}%     {len(keep):>7}  {len(skip):>7}  {sum(r['pnl'] for r in keep):>+10,.0f}  {sum(r['pnl'] for r in skip):>+10,.0f}  {wr:>8.1%}")

    # Range analysis
    rng = [r["range_dollars"] for r in records]
    print(f"\n  Range $: median={np.median(rng):.2f}, min={min(rng):.2f}, max={max(rng):.2f}")
    for lo, hi in [(0, 0.30), (0.30, 0.50), (0.50, 0.75), (0.75, 1.00), (1.00, 999)]:
        b = [r for r in records if lo <= r["range_dollars"] < hi]
        if not b:
            continue
        wr = sum(1 for r in b if r["win"]) / len(b)
        avg = sum(r["pnl"] for r in b) / len(b)
        hi_str = f"{hi:.2f}" if hi < 999 else "+"
        print(f"  range ${lo:.2f}-${hi_str}: N={len(b)}  WR={wr:.1%}  avg={avg:+,.0f}")


def main():
    print("Loading data...")
    spy_df = pd.read_csv(MASTER_SPY)
    vix_df = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy_df)} rows  VIX {len(vix_df)} rows")
    ts_idx = {str(row["timestamp_et" if "timestamp_et" in spy_df.columns else "datetime"])[:16]: i
              for i, row in spy_df.iterrows()}

    print("Running IS backtest...")
    r_is = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, **SAFE_BASE)
    print(f"IS total: n={len(r_is.trades)}")

    print("Running OOS backtest...")
    r_oos = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, **SAFE_BASE)
    print(f"OOS total: n={len(r_oos.trades)}")

    analyze(r_is.trades, spy_df, ts_idx, "IS")
    analyze(r_oos.trades, spy_df, ts_idx, "OOS")

    print("\n\nDONE. High body_pct = strong momentum signal bar. Check if it predicts wins.")


if __name__ == "__main__":
    main()

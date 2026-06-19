"""
Entry Bar Quality Gate Analysis.

Hypothesis: trades with a strong entry bar (high body_pct = ratio of candle body
to total range) have better follow-through and higher WR.

For bear entries: want strong bearish body (close < open, high body_pct)
For bull entries: want strong bullish body (close > open, high body_pct)

Additional signals:
- upper_wick_pct: upper wick / range (bear = want small upper wick = clean rejection)
- lower_wick_pct: lower wick / range (bull = want small lower wick)

Tests:
1. WR by body_pct quartile (does Q4 body_pct outperform Q1?)
2. Direction-filtered body_pct (only bearish body for bear entries)
3. Gate test: Q3+Q4 vs Q1+Q2 — is there a WR lift >= 5pp AND n_gate >= 20?
"""
import datetime as dt
import sys
from pathlib import Path
from statistics import mean, stdev

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

# Safe production baseline (post-Rank36)
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


def build_spy_index(spy_df: pd.DataFrame) -> dict:
    """Build {timestamp_str_truncated_to_min: row} index for fast entry bar lookup."""
    idx = {}
    for _, row in spy_df.iterrows():
        ts = str(row["timestamp_et"])[:16]  # "YYYY-MM-DD HH:MM"
        idx[ts] = row
    return idx


def entry_bar_metrics(entry_time_et: dt.datetime, spy_idx: dict) -> dict | None:
    """Look up entry bar and compute body/wick metrics. Returns None if bar not found."""
    ts_key = entry_time_et.strftime("%Y-%m-%d %H:%M")
    row = spy_idx.get(ts_key)
    if row is None:
        return None
    o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
    rng = h - l
    if rng < 0.001:
        return None
    body = abs(c - o)
    upper_wick = h - max(c, o)
    lower_wick = min(c, o) - l
    return {
        "body_pct": body / rng * 100,
        "upper_wick_pct": upper_wick / rng * 100,
        "lower_wick_pct": lower_wick / rng * 100,
        "is_bearish_body": c < o,
        "is_bullish_body": c > o,
        "open": o, "high": h, "low": l, "close": c,
    }


def quartile_analysis(values_with_wr: list[tuple[float, bool]]) -> None:
    """Print WR by body_pct quartile."""
    if len(values_with_wr) < 8:
        print("    (insufficient sample for quartile analysis)")
        return
    sorted_v = sorted(values_with_wr, key=lambda x: x[0])
    n = len(sorted_v)
    q25 = sorted_v[n // 4][0]
    q50 = sorted_v[n // 2][0]
    q75 = sorted_v[3 * n // 4][0]

    bins = [
        ("Q1(<25%)", [v for v in sorted_v if v[0] <= q25]),
        (f"Q2(25-50%)", [v for v in sorted_v if q25 < v[0] <= q50]),
        (f"Q3(50-75%)", [v for v in sorted_v if q50 < v[0] <= q75]),
        ("Q4(>75%)", [v for v in sorted_v if v[0] > q75]),
    ]
    for label, grp in bins:
        if not grp:
            continue
        wr = sum(1 for _, w in grp if w) / len(grp)
        avg_body = mean(v for v, _ in grp)
        print(f"    {label:14s}  n={len(grp):3d}  WR={wr:.1%}  avg_body={avg_body:.1f}%")

    # Gate test: top half vs bottom half
    top_half = [v for v in sorted_v if v[0] > q50]
    bot_half = [v for v in sorted_v if v[0] <= q50]
    if top_half and bot_half:
        wr_top = sum(1 for _, w in top_half if w) / len(top_half)
        wr_bot = sum(1 for _, w in bot_half if w) / len(bot_half)
        lift = (wr_top - wr_bot) * 100
        print(f"    Top-half WR={wr_top:.1%} vs Bot-half WR={wr_bot:.1%}  lift={lift:+.1f}pp  n_top={len(top_half)}")
        if lift >= 5.0 and len(top_half) >= 20:
            print(f"    *** GATE CANDIDATE: top-half body_pct gate (threshold={q50:.1f}%) lift={lift:+.1f}pp n={len(top_half)} ***")


def main():
    print("Loading data...")
    spy_df = pd.read_csv(MASTER_SPY)
    vix_df = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy_df)} rows  VIX {len(vix_df)} rows")

    print("Building SPY bar index...")
    spy_idx = build_spy_index(spy_df)

    for window_name, start, end in [("IS", IS_START, IS_END), ("OOS", OOS_START, OOS_END)]:
        print(f"\n=== {window_name} ({start} to {end}) ===")
        result = run_backtest(spy_df, vix_df, start_date=start, end_date=end, **SAFE_BASE)
        trades = result.trades

        by_setup: dict[str, list] = {}
        missing_bars = 0
        for t in trades:
            metrics = entry_bar_metrics(t.entry_time_et, spy_idx)
            if metrics is None:
                missing_bars += 1
                continue
            setup = t.setup or "UNKNOWN"
            if setup not in by_setup:
                by_setup[setup] = []
            is_win = t.dollar_pnl > 0
            by_setup[setup].append((metrics, is_win, t))

        print(f"  Total trades: {len(trades)}  Missing bars: {missing_bars}")

        for setup, rows in sorted(by_setup.items()):
            print(f"\n  Setup: {setup}  n={len(rows)}")
            if len(rows) < 4:
                print("    (too few trades to analyze)")
                continue

            all_body = [(r["body_pct"], w) for r, w, _ in rows]
            all_upper = [(r["upper_wick_pct"], w) for r, w, _ in rows]

            print(f"  === body_pct quartile analysis ===")
            quartile_analysis(all_body)

            print(f"  === upper_wick_pct quartile analysis ===")
            quartile_analysis(all_upper)

            # Direction-filtered: bearish body only for bear setups
            bear_rows = [(r["body_pct"], w) for r, w, _ in rows if r["is_bearish_body"]]
            bull_rows = [(r["body_pct"], w) for r, w, _ in rows if r["is_bullish_body"]]
            if bear_rows:
                pct_bear = len(bear_rows) / len(rows)
                wr_bear = sum(1 for _, w in bear_rows if w) / len(bear_rows)
                wr_bull_body = sum(1 for _, w in bull_rows if w) / len(bull_rows) if bull_rows else float("nan")
                print(f"  Direction split: {pct_bear:.0%} bearish body  WR(bearish_body)={wr_bear:.1%} n={len(bear_rows)}  WR(bullish_body)={wr_bull_body:.1%} n={len(bull_rows)}")


if __name__ == "__main__":
    main()

"""
Bearish Streak Quality Analysis for BEARISH_REJECTION trades.

Hypothesis (Kitchen 2026-06-17): consecutive bearish bars before entry discriminate
winners from losers. Winners have stronger downside momentum INTO the entry bar.

Metric: count of consecutive bars with close < open in the 5 bars preceding the
signal bar (bars at idx-5, idx-4, idx-3, idx-2, idx-1).

This is a pure post-hoc analysis — no orchestrator changes needed. If streak>=N
discriminates meaningfully (>15pp WR gap), implement as a gate in orchestrator.

Context: Safe account post-Rank36 baseline (IS n=130, OOS n=21).
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


def build_spy_ts_index(spy_df: pd.DataFrame) -> dict:
    """Map timestamp_et string[:16] -> row index in spy_df."""
    idx = {}
    for i, row in spy_df.iterrows():
        ts = str(row["timestamp_et"])[:16]
        idx[ts] = i
    return idx


def consecutive_bearish_streak(spy_df: pd.DataFrame, bar_idx: int, lookback: int = 5) -> int:
    """Count consecutive bearish bars (close < open) ending at bar_idx - 1."""
    streak = 0
    for offset in range(1, lookback + 1):
        i = bar_idx - offset
        if i < 0:
            break
        row = spy_df.iloc[i]
        if float(row["close"]) < float(row["open"]):
            streak += 1
        else:
            break
    return streak


def analyze_streak_bucket(trades: list, spy_df: pd.DataFrame, spy_idx: dict, label: str):
    """Analyze WR/P&L grouped by bearish streak count."""
    print(f"\n=== {label} (n={len(trades)}) ===")

    by_streak: dict[int, list] = {}
    for t in trades:
        ts_key = t.entry_time_et.strftime("%Y-%m-%d %H:%M") if hasattr(t.entry_time_et, 'strftime') else str(t.entry_time_et)[:16]
        # entry_time_et is the FILL bar — signal bar is one bar earlier
        fill_bar_idx = spy_idx.get(ts_key)
        if fill_bar_idx is None:
            continue
        signal_bar_idx = fill_bar_idx - 1  # signal at idx, fill at idx+1
        streak = consecutive_bearish_streak(spy_df, signal_bar_idx, lookback=5)
        by_streak.setdefault(streak, []).append(t)

    print(f"\n{'Streak':>6}  {'N':>5}  {'WR%':>6}  {'Avg P&L':>9}  {'Total P&L':>11}  {'Signal'}")
    print("-" * 60)
    cumulative_keep_pnl = 0.0
    cumulative_skip_pnl = 0.0

    for streak_val in sorted(by_streak.keys()):
        group = by_streak[streak_val]
        n = len(group)
        wins = sum(1 for t in group if t.dollar_pnl > 0)
        total_pnl = sum(t.dollar_pnl for t in group)
        wr = wins / n if n else 0.0
        avg_pnl = total_pnl / n if n else 0.0
        note = " <-- likely noise" if n < 5 else ""
        print(f"  {streak_val:>4}  {n:>5}  {wr:>6.1%}  {avg_pnl:>+9.0f}  {total_pnl:>+11.0f}{note}")

    # Gate analysis: require streak >= 1, 2, 3
    print(f"\n  Gate analysis (require streak >= N):")
    print(f"  {'Gate':>12}  {'N_keep':>6}  {'N_skip':>6}  {'PnL_keep':>10}  {'PnL_skip':>10}  {'WR_keep':>8}")
    for gate in [1, 2, 3]:
        keeps = [t for streak_val, g in by_streak.items() for t in g if streak_val >= gate]
        skips = [t for streak_val, g in by_streak.items() for t in g if streak_val < gate]
        pnl_keep = sum(t.dollar_pnl for t in keeps)
        pnl_skip = sum(t.dollar_pnl for t in skips)
        wr_keep = sum(1 for t in keeps if t.dollar_pnl > 0) / len(keeps) if keeps else 0.0
        print(f"  streak>={gate:<6}  {len(keeps):>6}  {len(skips):>6}  {pnl_keep:>+10.0f}  {pnl_skip:>+10.0f}  {wr_keep:>8.1%}")


def main():
    print("Loading data...")
    spy_df = pd.read_csv(MASTER_SPY)
    vix_df = pd.read_csv(MASTER_VIX)
    spy_df = spy_df.reset_index(drop=True)
    print(f"SPY {len(spy_df)} rows  VIX {len(vix_df)} rows")

    print("Building SPY timestamp index...")
    spy_idx = build_spy_ts_index(spy_df)

    print("Running IS backtest...")
    r_is = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, **SAFE_BASE)
    # Filter to BEARISH_REJECTION + PUT trades only
    is_bear = [t for t in r_is.trades if getattr(t, 'option_type', 'P') == 'P']
    print(f"IS total: n={len(r_is.trades)}, BEAR-PUT: n={len(is_bear)}")

    print("Running OOS backtest...")
    r_oos = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, **SAFE_BASE)
    oos_bear = [t for t in r_oos.trades if getattr(t, 'option_type', 'P') == 'P']
    print(f"OOS total: n={len(r_oos.trades)}, BEAR-PUT: n={len(oos_bear)}")

    analyze_streak_bucket(is_bear, spy_df, spy_idx, "IS BEARISH (PUT) trades")
    analyze_streak_bucket(oos_bear, spy_df, spy_idx, "OOS BEARISH (PUT) trades")

    # Volume ratio analysis (entry bar volume vs 30-bar avg)
    print("\n\n=== VOLUME RATIO ANALYSIS (IS BEAR trades) ===")
    print("Volume ratio = entry bar volume / avg volume of prior 30 bars")
    vol_data = []
    for t in is_bear:
        ts_key = t.entry_time_et.strftime("%Y-%m-%d %H:%M") if hasattr(t.entry_time_et, 'strftime') else str(t.entry_time_et)[:16]
        fill_bar_idx = spy_idx.get(ts_key)
        if fill_bar_idx is None or fill_bar_idx < 31:
            continue
        signal_bar_idx = fill_bar_idx - 1
        if signal_bar_idx < 30:
            continue
        signal_row = spy_df.iloc[signal_bar_idx]
        prior_rows = spy_df.iloc[signal_bar_idx - 30:signal_bar_idx]
        vol_signal = float(signal_row.get("volume", 0) or 0)
        vol_avg = prior_rows["volume"].astype(float).mean()
        if vol_avg == 0:
            continue
        vol_ratio = vol_signal / vol_avg
        vol_data.append((vol_ratio, t.dollar_pnl, t.dollar_pnl > 0))

    if vol_data:
        # Sort by vol_ratio and split into quartiles
        vol_data.sort(key=lambda x: x[0])
        q = len(vol_data) // 4
        for qi, (qlabel, subset) in enumerate([
            ("Q1 (lowest vol)", vol_data[:q]),
            ("Q2", vol_data[q:2*q]),
            ("Q3", vol_data[2*q:3*q]),
            ("Q4 (highest vol)", vol_data[3*q:]),
        ]):
            if not subset:
                continue
            n = len(subset)
            wins = sum(1 for _, _, w in subset if w)
            total = sum(p for _, p, _ in subset)
            wr = wins / n
            avg_ratio = sum(r for r, _, _ in subset) / n
            print(f"  {qlabel:<20}: n={n:>3}  WR={wr:.1%}  avg_P&L={total/n:>+7.0f}  avg_vol_ratio={avg_ratio:.2f}")

        # Gate analysis
        print("\n  Volume gate (require vol_ratio >= X):")
        for thresh in [0.8, 1.0, 1.2, 1.5]:
            keeps = [(r, p, w) for r, p, w in vol_data if r >= thresh]
            skips = [(r, p, w) for r, p, w in vol_data if r < thresh]
            if not keeps:
                continue
            pnl_k = sum(p for _, p, _ in keeps)
            wr_k = sum(1 for _, _, w in keeps if w) / len(keeps)
            pnl_s = sum(p for _, p, _ in skips)
            print(f"    vol>={thresh:.1f}: keep n={len(keeps):>3} P&L={pnl_k:>+8.0f} WR={wr_k:.1%}  |  skip n={len(skips):>3} P&L={pnl_s:>+8.0f}")


if __name__ == "__main__":
    main()

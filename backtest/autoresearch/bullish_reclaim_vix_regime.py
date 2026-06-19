"""
BULLISH_RECLAIM VIX Character Analysis.

Hypothesis (from context-15 decomposition):
  Q3-2025 BULLISH_RECLAIM (WR=26%, avg=+$318) coincides with VIX declining
  from the August 2025 spike back toward normal.
  Q1-2025 BULLISH_RECLAIM (WR=0%, avg=-$56) is in a flat/low VIX environment.
  OOS-May-2026 (WR=50%, avg=+$817) is post-tariff recovery = VIX declining.

Discriminator: `prior_day_vix < prior_5d_avg_vix` (VIX declining from recent high)
= post-spike mean-reversion context, where a failed breakdown reclaim has conviction.

This is analogous to L73 SNIPER VIX character — BUT the direction is OPPOSITE:
  SNIPER needs ESCALATING VIX (fear rising).
  BULLISH_RECLAIM needs DECLINING VIX (fear easing, trapped shorts covering).

Test: split IS BULLISH_RECLAIM fills by VIX character.
If pattern holds: declining VIX = better WR; flat/escalating = loser bin.
"""
import datetime as dt
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest"))

import pandas as pd
from lib.orchestrator import run_backtest

MASTER_SPY = ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
MASTER_VIX = ROOT / "backtest" / "data" / "vix_5m_2025-01-01_2026-06-16.csv"

_SPY_DF: pd.DataFrame = None
_VIX_DF: pd.DataFrame = None


def _load_data():
    global _SPY_DF, _VIX_DF
    if _SPY_DF is None:
        _SPY_DF = pd.read_csv(MASTER_SPY)
        _VIX_DF = pd.read_csv(MASTER_VIX)
        print(f"SPY {len(_SPY_DF)} rows  VIX {len(_VIX_DF)} rows")


IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 6, 16)

BASE_KWARGS = dict(
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

VIX_LOOKBACK_DAYS = 5


def build_daily_vix(vix_path: Path) -> pd.Series:
    """Extract daily closing VIX from 5-minute VIX bars (last bar of each day)."""
    vix_df = pd.read_csv(vix_path)
    # Extract date as string prefix (handles mixed-tz timestamps safely)
    vix_df["date"] = vix_df["timestamp_et"].str[:10]
    daily_close = (
        vix_df.sort_values("timestamp_et")
        .groupby("date")["close"]
        .last()
    )
    return daily_close


def prior_day_vix(entry_date: dt.date, daily_vix: pd.Series) -> float:
    prior = entry_date - dt.timedelta(days=1)
    # Walk back to find last trading day with data (index is "YYYY-MM-DD" strings)
    for _ in range(5):
        key = prior.isoformat()
        if key in daily_vix.index:
            return float(daily_vix[key])
        prior -= dt.timedelta(days=1)
    return float("nan")


def rolling_5d_avg_vix(entry_date: dt.date, daily_vix: pd.Series) -> float:
    """5-day average of closing VIX using the 5 trading days before entry_date."""
    prior = entry_date - dt.timedelta(days=1)
    values = []
    checked = 0
    while len(values) < VIX_LOOKBACK_DAYS and checked < 20:
        key = prior.isoformat()
        if key in daily_vix.index:
            values.append(float(daily_vix[key]))
        prior -= dt.timedelta(days=1)
        checked += 1
    return mean(values) if values else float("nan")


def vix_character(entry_date: dt.date, daily_vix: pd.Series) -> str:
    """
    Returns:
      'declining' — prior day VIX < 5-day avg VIX (fear easing)
      'escalating' — prior day VIX > 5-day avg VIX (fear rising)
      'flat' — within deadband
    """
    pdv = prior_day_vix(entry_date, daily_vix)
    avg5 = rolling_5d_avg_vix(entry_date, daily_vix)
    if any(v != v for v in [pdv, avg5]):  # NaN check
        return "unknown"
    diff = pdv - avg5
    if diff < -0.50:
        return "declining"
    if diff > 0.50:
        return "escalating"
    return "flat"


def analyze_window(label: str, start: dt.date, end: dt.date, daily_vix: pd.Series):
    _load_data()
    result = run_backtest(
        _SPY_DF,
        _VIX_DF,
        start_date=start,
        end_date=end,
        **BASE_KWARGS,
    )
    fills = result.trades

    bull = [t for t in fills if "BULLISH" in t.setup]
    bear = [t for t in fills if "BEARISH" in t.setup]

    print(f"\n=== {label} ({start}..{end}) ===")
    print(f"Total fills: {len(fills)}  BULLISH_RECLAIM: {len(bull)}  BEARISH_REJECTION: {len(bear)}")

    if not bull:
        print("No BULLISH_RECLAIM trades — skip.")
        return

    # Split by VIX character
    by_char: dict[str, list] = {"declining": [], "flat": [], "escalating": [], "unknown": []}
    for t in bull:
        edate = t.entry_time_et.date() if hasattr(t, "entry_time_et") and t.entry_time_et else None
        if edate is None:
            by_char["unknown"].append(t)
        else:
            char = vix_character(edate, daily_vix)
            by_char[char].append(t)

    def wr(trades):
        return sum(1 for t in trades if t.dollar_pnl > 0) / len(trades) if trades else 0

    print(f"\nBULLISH_RECLAIM by VIX character (deadband: +-$0.50):")
    print(f"{'Character':<14} {'n':>4} {'WR':>6} {'avg$':>8} {'total$':>10}")
    total_n = 0
    for char in ["declining", "flat", "escalating", "unknown"]:
        trades = by_char[char]
        if not trades:
            continue
        total_n += len(trades)
        avg = mean(t.dollar_pnl for t in trades)
        tot = sum(t.dollar_pnl for t in trades)
        print(f"  {char:<12} {len(trades):>4} {wr(trades):>6.1%} {avg:>8.1f} {tot:>10.1f}")

    # Overall summary
    all_wr = wr(bull)
    print(f"\n  {'TOTAL':<12} {len(bull):>4} {all_wr:>6.1%} "
          f"{mean(t.dollar_pnl for t in bull):>8.1f} "
          f"{sum(t.dollar_pnl for t in bull):>10.1f}")

    # Quarter breakdown
    print(f"\nBULLISH_RECLAIM by quarter:")
    quarters: dict[str, list] = {}
    for t in bull:
        edate = t.entry_time_et.date() if hasattr(t, "entry_time_et") and t.entry_time_et else None
        if edate:
            q = f"{edate.year}-Q{(edate.month - 1) // 3 + 1}"
        else:
            q = "unknown"
        quarters.setdefault(q, []).append(t)

    for q in sorted(quarters):
        trades = quarters[q]
        avg = mean(t.dollar_pnl for t in trades)
        tot = sum(t.dollar_pnl for t in trades)

        # Map each trade's VIX character
        chars = []
        for t in trades:
            edate = t.entry_time_et.date() if hasattr(t, "entry_time_et") and t.entry_time_et else None
            chars.append(vix_character(edate, daily_vix) if edate else "?")
        char_summary = ",".join(sorted(set(chars)))
        print(f"  {q:<10} n={len(trades):>3}  WR={wr(trades):.1%}  avg=${avg:.1f}  "
              f"chars=[{char_summary}]")


def main():
    print("Loading daily VIX data...")
    daily_vix = build_daily_vix(Path(MASTER_VIX))
    print(f"Daily VIX: {len(daily_vix)} days, {daily_vix.index[0]}..{daily_vix.index[-1]}")

    analyze_window("IS", IS_START, IS_END, daily_vix)
    analyze_window("OOS", OOS_START, OOS_END, daily_vix)

    # Gate proposal check
    print("\n=== VIX CHARACTER GATE VERDICT ===")
    print("If IS: declining WR >> flat/escalating WR (>=10pp edge)")
    print("  AND OOS: declining WR better than flat/escalating")
    print("  THEN: gate candidate (block BULLISH_RECLAIM in flat/escalating VIX)")
    print()
    print("Counter-risk: L93 — don't cross-contaminate regime gates between setups.")
    print("If declining n_is < 15: INSUFFICIENT EVIDENCE (advisory only).")


if __name__ == "__main__":
    main()

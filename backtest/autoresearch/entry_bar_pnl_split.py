"""
Entry Bar Direction P&L Impact Analysis.

Follows up on entry_bar_quality.py findings:
- BEARISH_REJECTION bearish-body WR=41.3% (n=46) vs bullish-body WR=3.4% (n=29)

This script quantifies the P&L impact of blocking bullish-body BEARISH_REJECTION entries.
No orchestrator changes needed -- uses trade-level dollar_pnl directly.

Gate proposal: require_bearish_entry_bar (close < open at entry bar) for BEARISH_REJECTION setups.
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

SUBWINDOWS = [
    ("W1_2025H1",  dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2_2025Q3",  dt.date(2025, 7, 1),  dt.date(2025, 9, 30)),
    ("W3_2025Q4",  dt.date(2025, 10, 1), dt.date(2025, 12, 31)),
    ("W4_2026H1",  dt.date(2026, 1, 2),  dt.date(2026, 5, 7)),
]

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

BEAR_SETUPS = {"BEARISH_REJECTION_RIDE_THE_RIBBON", "BEARISH_REJECTION_RIDE_THE_RIBBON::BS_FALLBACK"}


def build_spy_index(spy_df: pd.DataFrame) -> dict:
    idx = {}
    for _, row in spy_df.iterrows():
        ts = str(row["timestamp_et"])[:16]
        idx[ts] = row
    return idx


def is_bearish_bar(entry_time_et: dt.datetime, spy_idx: dict) -> bool | None:
    ts_key = entry_time_et.strftime("%Y-%m-%d %H:%M")
    row = spy_idx.get(ts_key)
    if row is None:
        return None
    return float(row["close"]) < float(row["open"])


def analyze_pnl_split(name: str, start: dt.date, end: dt.date, spy_df: pd.DataFrame, vix_df: pd.DataFrame, spy_idx: dict):
    result = run_backtest(spy_df, vix_df, start_date=start, end_date=end, **SAFE_BASE)
    trades = result.trades
    total_pnl = sum(t.dollar_pnl for t in trades)

    bearish_body_pnl = []
    bullish_body_pnl = []
    unknown = []

    for t in trades:
        setup = t.setup or ""
        if not any(s in setup for s in ("BEARISH_REJECTION",)):
            continue
        direction = is_bearish_bar(t.entry_time_et, spy_idx)
        if direction is None:
            unknown.append(t.dollar_pnl)
        elif direction:
            bearish_body_pnl.append(t.dollar_pnl)
        else:
            bullish_body_pnl.append(t.dollar_pnl)

    print(f"\n=== {name} ({start} to {end}) ===")
    print(f"  Total trades: {len(trades)}  Total P&L: ${total_pnl:+,.0f}")
    print(f"\n  BEARISH_REJECTION subgroup:")
    print(f"    Bearish body (gate=KEEP): n={len(bearish_body_pnl)}"
          f"  P&L=${sum(bearish_body_pnl):+,.0f}"
          f"  WR={sum(1 for x in bearish_body_pnl if x > 0)/max(1,len(bearish_body_pnl)):.1%}"
          f"  avg=${sum(bearish_body_pnl)/max(1,len(bearish_body_pnl)):+.0f}")
    print(f"    Bullish body (gate=BLOCK): n={len(bullish_body_pnl)}"
          f"  P&L=${sum(bullish_body_pnl):+,.0f}"
          f"  WR={sum(1 for x in bullish_body_pnl if x > 0)/max(1,len(bullish_body_pnl)):.1%}"
          f"  avg=${sum(bullish_body_pnl)/max(1,len(bullish_body_pnl)):+.0f}")
    print(f"    Unknown bar: n={len(unknown)}  P&L=${sum(unknown):+,.0f}")
    if bullish_body_pnl:
        blocked_pnl = sum(bullish_body_pnl)
        print(f"\n  *** GATE IMPACT: blocking bullish-body trades removes ${blocked_pnl:+,.0f} P&L from total")
        print(f"      Candidate delta = ${-blocked_pnl:+,.0f} (negative blocked P&L = improvement)")

    return {
        "total_n": len(trades), "total_pnl": total_pnl,
        "bearish_n": len(bearish_body_pnl), "bearish_pnl": sum(bearish_body_pnl),
        "bullish_n": len(bullish_body_pnl), "bullish_pnl": sum(bullish_body_pnl),
    }


def main():
    print("Loading data...")
    spy_df = pd.read_csv(MASTER_SPY)
    vix_df = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy_df)} rows  VIX {len(vix_df)} rows")
    spy_idx = build_spy_index(spy_df)

    is_res = analyze_pnl_split("IS", IS_START, IS_END, spy_df, vix_df, spy_idx)
    oos_res = analyze_pnl_split("OOS", OOS_START, OOS_END, spy_df, vix_df, spy_idx)

    print("\n=== SUB-WINDOW ANALYSIS ===")
    for wname, ws, we in SUBWINDOWS:
        sw_res = analyze_pnl_split(wname, ws, we, spy_df, vix_df, spy_idx)

    print("\n=== SUMMARY ===")
    is_delta = -is_res["bullish_pnl"]
    oos_delta = -oos_res["bullish_pnl"]
    print(f"  IS delta (blocking bullish body): ${is_delta:+,.0f}  n_affected={is_res['bullish_n']}")
    print(f"  OOS delta (blocking bullish body): ${oos_delta:+,.0f}  n_affected={oos_res['bullish_n']}")

    n_is = is_res["total_n"] - is_res["bullish_n"]
    n_oos = oos_res["total_n"] - oos_res["bullish_n"]
    if is_delta != 0 and n_is > 0 and n_oos > 0:
        wf = (oos_delta / n_oos) / (is_delta / n_is)
        print(f"  WF_norm = {wf:.3f}  (gate: >= 0.70)")
        if oos_delta > 0 and wf >= 0.70:
            print("  *** GATE CANDIDATE: OOS_positive AND WF >= 0.70 ***")
        else:
            print(f"  VERDICT: {'OOS_NEG' if oos_delta <= 0 else 'WF_FAIL'}")


if __name__ == "__main__":
    main()

"""
Fill Bar Direction Gate Full Backtest (replaces dead-knob entry_bar_direction_gate.py).

Corrected hypothesis: BEARISH_REJECTION entries where the FILL BAR (N+1, not signal bar N)
is BULLISH have WR=3.4% avg=-$39 (n=29 IS). Blocking them removes losers.

Root cause of prior dead knob: signal bars are ALWAYS bearish by construction
(BEARISH_REJECTION requires the bar to close below the rejection level), so the
original gate (checking signal bar N) was a structural invariant — 0 bars blocked.

This script uses require_bearish_fill_bar=True which checks spy_df.iloc[idx+1] direction.

IMPORTANT: This is a LOOK-AHEAD gate (fill bar N+1 cannot be known at signal bar N close
time in production). The result is the UPPER BOUND of gain from a one-bar confirmation
delay strategy. True production impact requires simulating actual N+2 fill prices.

Gate threshold: OOS_positive AND WF_norm >= 0.70 AND SW_hurt <= 1
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

ANCHOR_DATES = [
    dt.date(2025, 4, 29), dt.date(2025, 5, 1), dt.date(2025, 5, 4),
    dt.date(2025, 5, 5),  dt.date(2025, 5, 6), dt.date(2025, 5, 7),
]
ANCHOR_WINNERS = {dt.date(2025, 4, 29), dt.date(2025, 5, 1), dt.date(2025, 5, 4)}

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


def run(gate_on: bool, start: dt.date, end: dt.date, spy_df, vix_df):
    result = run_backtest(
        spy_df, vix_df,
        start_date=start, end_date=end,
        require_bearish_fill_bar=gate_on,
        **SAFE_BASE,
    )
    trades = result.trades
    pnl = sum(t.dollar_pnl for t in trades)
    n = len(trades)
    wr = sum(1 for t in trades if t.dollar_pnl > 0) / n if n else 0.0
    return n, pnl, wr, trades


def wf_norm(is_d, n_is, oos_d, n_oos):
    if not (n_is and n_oos and is_d != 0):
        return float("nan")
    return (oos_d / n_oos) / (is_d / n_is)


def main():
    print("Loading data...")
    spy_df = pd.read_csv(MASTER_SPY)
    vix_df = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy_df)} rows  VIX {len(vix_df)} rows")

    print("\nRunning IS baseline...")
    base_is_n, base_is_pnl, base_is_wr, base_is_trades = run(False, IS_START, IS_END, spy_df, vix_df)
    print(f"  IS baseline: n={base_is_n}  pnl=${base_is_pnl:+,.0f}  WR={base_is_wr:.1%}")

    print("Running IS gate...")
    gate_is_n, gate_is_pnl, gate_is_wr, gate_is_trades = run(True, IS_START, IS_END, spy_df, vix_df)
    print(f"  IS gate:     n={gate_is_n}  pnl=${gate_is_pnl:+,.0f}  WR={gate_is_wr:.1%}")

    print("\nRunning OOS baseline...")
    base_oos_n, base_oos_pnl, base_oos_wr, base_oos_trades = run(False, OOS_START, OOS_END, spy_df, vix_df)
    print(f"  OOS baseline: n={base_oos_n}  pnl=${base_oos_pnl:+,.0f}  WR={base_oos_wr:.1%}")

    print("Running OOS gate...")
    gate_oos_n, gate_oos_pnl, gate_oos_wr, gate_oos_trades = run(True, OOS_START, OOS_END, spy_df, vix_df)
    print(f"  OOS gate:     n={gate_oos_n}  pnl=${gate_oos_pnl:+,.0f}  WR={gate_oos_wr:.1%}")

    is_delta = gate_is_pnl - base_is_pnl
    oos_delta = gate_oos_pnl - base_oos_pnl
    n_blocked_is = base_is_n - gate_is_n
    n_blocked_oos = base_oos_n - gate_oos_n
    wf = wf_norm(is_delta, gate_is_n, oos_delta, gate_oos_n)

    print(f"\n  IS delta:  ${is_delta:+,.0f}  (n_blocked={n_blocked_is})")
    print(f"  OOS delta: ${oos_delta:+,.0f}  (n_blocked={n_blocked_oos})")
    print(f"  WF_norm:   {wf:.3f}  (gate: >= 0.70)" if wf == wf else f"  WF_norm:   nan  (gate: >= 0.70)")

    print("\n  SUB-WINDOW ANALYSIS:")
    sw_hurt = 0
    for wname, ws, we in SUBWINDOWS:
        base_sw = run(False, ws, we, spy_df, vix_df)
        gate_sw = run(True, ws, we, spy_df, vix_df)
        sw_delta = gate_sw[1] - base_sw[1]
        direction = "HELP" if sw_delta > 50 else "HURT" if sw_delta < -50 else "FLAT"
        if direction == "HURT":
            sw_hurt += 1
        print(f"    {wname}: base=${base_sw[1]:+,.0f} gate=${gate_sw[1]:+,.0f} delta=${sw_delta:+,.0f} {direction}")

    print(f"\n  SW_hurt = {sw_hurt}/4  (gate: <= 1)")

    print("\n  ANCHOR DAY CHECK:")
    def by_date(trades):
        d = {}
        for t in trades:
            date = t.entry_time_et.date()
            d.setdefault(date, []).append(t)
        return d

    base_d = by_date(base_is_trades)
    gate_d = by_date(gate_is_trades)
    any_regression = False
    for date in ANCHOR_DATES:
        base_pnl = sum(t.dollar_pnl for t in base_d.get(date, []))
        gate_pnl = sum(t.dollar_pnl for t in gate_d.get(date, []))
        delta = gate_pnl - base_pnl
        kind = "W" if date in ANCHOR_WINNERS else "L"
        ok = True
        if date in ANCHOR_WINNERS and gate_pnl < base_pnl and abs(delta) > 50:
            ok = False
            any_regression = True
        flag = "" if ok else " *** REGRESSION ***"
        print(f"    {date} [{kind}] base=${base_pnl:+,.0f}  gate=${gate_pnl:+,.0f}  delta=${delta:+,.0f}{flag}")
    anchor_ok = not any_regression
    print(f"  Anchor no-regression: {'PASS' if anchor_ok else 'FAIL'}")

    oos_pos = oos_delta > 0
    wf_pass = (wf == wf) and wf >= 0.70
    sw_pass = sw_hurt <= 1

    print(f"\n=== VERDICT ===")
    print(f"  OOS positive: {'PASS' if oos_pos else 'FAIL'}")
    wf_str = f"{wf:.3f}" if wf == wf else "nan"
    print(f"  WF >= 0.70:   {'PASS' if wf_pass else 'FAIL'} ({wf_str})")
    print(f"  SW_hurt <= 1: {'PASS' if sw_pass else 'FAIL'} ({sw_hurt}/4)")
    print(f"  Anchor OK:    {'PASS' if anchor_ok else 'FAIL'}")
    print(f"  n_blocked IS: {n_blocked_is}  (expected ~29 from post-hoc analysis)")
    print(f"  n_blocked OOS: {n_blocked_oos}  (expected ~1)")
    print(f"\n  NOTE: LOOK-AHEAD gate — checks fill bar (N+1) which is unknown at signal time.")
    print(f"  Production would require one-bar confirmation delay (enter at N+2).")

    if oos_pos and wf_pass and sw_pass and anchor_ok:
        print(f"\n  *** ALL GATES PASS — LOOK-AHEAD UPPER BOUND CONFIRMED ***")
        print(f"  Next: implement proper one-bar delay backtest to get true production P&L.")
    else:
        print(f"\n  NOT RATIFIABLE")


if __name__ == "__main__":
    main()

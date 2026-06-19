"""
No-trade-after sweep: block entries after a specified ET time.
Tests kitchen's BEARISH_REVERSAL_LATE_ENTRY_GATE hypothesis with full IS/OOS data.

Uses no_trade_window=(cutoff, dt.time(23, 59)) to block entries after cutoff.
Baseline: no_trade_window=None (no afternoon block).
Sweep: block after [14:00, 14:30, 15:00, 15:15, 15:30, 15:40].

Motivation: time stop at 15:40. Entries after 15:30 have at most 10 minutes.
Late entries may be noise that degrades strategy P&L.
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
    ("W1_2025H1", dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2_2025Q3", dt.date(2025, 7, 1),  dt.date(2025, 9, 30)),
    ("W3_2025Q4", dt.date(2025, 10, 1), dt.date(2025, 12, 31)),
    ("W4_2026H1", dt.date(2026, 1, 1),  dt.date(2026, 5, 7)),
]

SAFE_BASE = dict(
    use_real_fills=True,
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

# Cutoffs to test: no entry after this time
CUTOFFS = [
    dt.time(14, 0),
    dt.time(14, 30),
    dt.time(15, 0),
    dt.time(15, 15),
    dt.time(15, 30),
    dt.time(15, 40),
]

ANCHOR_DATES = {
    dt.date(2025, 4, 29): True,
    dt.date(2025, 5, 1):  True,
    dt.date(2025, 5, 4):  True,
    dt.date(2025, 5, 5):  False,
    dt.date(2025, 5, 6):  False,
}


def compute_anchor_pnl(trades, anchor_dates):
    by_date = {}
    for t in trades:
        d = t.entry_time_et.date() if hasattr(t.entry_time_et, 'date') else t.entry_time_et
        by_date.setdefault(d, []).append(t.dollar_pnl)
    return {d: sum(by_date.get(d, [0])) for d in anchor_dates}


def run_with_cutoff(spy_df, vix_df, cutoff, start, end):
    p = dict(SAFE_BASE)
    if cutoff is None:
        p["no_trade_window"] = None
    else:
        p["no_trade_window"] = (cutoff, dt.time(23, 59))
    return run_backtest(spy_df, vix_df, start_date=start, end_date=end, **p)


def wf_norm(is_d, is_n, oos_d, oos_n):
    if is_n == 0 or oos_n == 0 or is_d == 0:
        return float("nan")
    return (oos_d / oos_n) / (is_d / is_n)


def main():
    print("Loading data...")
    spy_df = pd.read_csv(MASTER_SPY)
    vix_df = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy_df)} rows  VIX {len(vix_df)} rows")

    print("\nBaseline (no_trade_window=None)...")
    b_is  = run_with_cutoff(spy_df, vix_df, None, IS_START, IS_END)
    b_oos = run_with_cutoff(spy_df, vix_df, None, OOS_START, OOS_END)
    b_is_pnl  = sum(t.dollar_pnl for t in b_is.trades)
    b_oos_pnl = sum(t.dollar_pnl for t in b_oos.trades)
    b_is_n  = len(b_is.trades)
    b_oos_n = len(b_oos.trades)
    print(f"  IS  n={b_is_n}  pnl={b_is_pnl:+,.0f}  WR={sum(1 for t in b_is.trades if t.dollar_pnl>0)/max(1,b_is_n):.1%}")
    print(f"  OOS n={b_oos_n}  pnl={b_oos_pnl:+,.0f}  WR={sum(1 for t in b_oos.trades if t.dollar_pnl>0)/max(1,b_oos_n):.1%}")
    b_anchors = compute_anchor_pnl(b_is.trades, ANCHOR_DATES)

    # Show time-of-day distribution at baseline
    print("\n  IS entry time distribution:")
    by_hour = {}
    for t in b_is.trades:
        h = t.entry_time_et.hour if hasattr(t.entry_time_et, 'hour') else int(str(t.entry_time_et)[11:13])
        by_hour[h] = by_hour.get(h, 0) + 1
    for h in sorted(by_hour):
        bar = "#" * by_hour[h]
        print(f"    {h:02d}:xx  {by_hour[h]:>3}  {bar}")

    print("\n  IS entries by 30-min bucket:")
    buckets = [(h, m) for h in range(9, 16) for m in (0, 30)]
    for h, m in buckets:
        lo = dt.time(h, m)
        hi_m = m + 30
        hi_h = h
        if hi_m >= 60:
            hi_m -= 60
            hi_h += 1
        if hi_h >= 16:
            break
        hi = dt.time(hi_h, hi_m)
        n = sum(1 for t in b_is.trades
                if hasattr(t.entry_time_et, 'hour') and lo <= dt.time(t.entry_time_et.hour, t.entry_time_et.minute) < hi)
        pnl = sum(t.dollar_pnl for t in b_is.trades
                  if hasattr(t.entry_time_et, 'hour') and lo <= dt.time(t.entry_time_et.hour, t.entry_time_et.minute) < hi)
        wr = sum(1 for t in b_is.trades
                 if hasattr(t.entry_time_et, 'hour') and lo <= dt.time(t.entry_time_et.hour, t.entry_time_et.minute) < hi and t.dollar_pnl > 0) / max(1, n)
        if n > 0:
            print(f"    {h:02d}:{m:02d}-{hi_h:02d}:{hi_m:02d}  N={n:>3}  pnl={pnl:>+8,.0f}  WR={wr:.0%}")

    hdr = f"{'Cutoff':>8}  {'IS_n':>5}  {'IS_pnl':>9}  {'IS_d':>8}  {'OOS_n':>5}  {'OOS_pnl':>9}  {'OOS_d':>8}  {'WF':>7}  {'SW_hurt':>7}  {'VERDICT'}"
    sep = "-" * 110
    print(f"\n{hdr}\n{sep}")

    for cutoff in CUTOFFS:
        r_is  = run_with_cutoff(spy_df, vix_df, cutoff, IS_START, IS_END)
        r_oos = run_with_cutoff(spy_df, vix_df, cutoff, OOS_START, OOS_END)
        is_pnl  = sum(t.dollar_pnl for t in r_is.trades)
        oos_pnl = sum(t.dollar_pnl for t in r_oos.trades)
        is_n  = len(r_is.trades)
        oos_n = len(r_oos.trades)
        is_d  = is_pnl  - b_is_pnl
        oos_d = oos_pnl - b_oos_pnl

        wf = wf_norm(is_d, is_n, oos_d, oos_n)

        sw_hurt = 0
        sw_parts = []
        for sw_name, sw_s, sw_e in SUBWINDOWS:
            p = dict(SAFE_BASE)
            p["no_trade_window"] = (cutoff, dt.time(23, 59))
            cand_sw = run_backtest(spy_df, vix_df, start_date=sw_s, end_date=sw_e, **p)
            p2 = dict(SAFE_BASE); p2["no_trade_window"] = None
            base_sw = run_backtest(spy_df, vix_df, start_date=sw_s, end_date=sw_e, **p2)
            delta = sum(t.dollar_pnl for t in cand_sw.trades) - sum(t.dollar_pnl for t in base_sw.trades)
            tag = "HELP" if delta >= -50 else "HURT"
            if delta < -50:
                sw_hurt += 1
            sw_parts.append(f"{sw_name}:{tag}({delta:+,.0f})")

        verdict = ""
        if oos_d < 0:
            verdict = "OOS_NEG"
        elif is_d == 0 and oos_d == 0:
            verdict = "NO_CHANGE"
        elif wf < 0.70:
            verdict = "OOS_POS_WF_FAIL"
        elif sw_hurt > 1:
            verdict = "WF_PASS_SW_FAIL"
        else:
            c_anchors = compute_anchor_pnl(r_is.trades, ANCHOR_DATES)
            anchor_ok = all(c_anchors.get(d, 0) >= b_anchors.get(d, 0) - 50 for d in ANCHOR_DATES)
            verdict = "RATIFIABLE" if anchor_ok else "ANCHOR_FAIL"

        cutoff_str = cutoff.strftime("%H:%M")
        print(f"{cutoff_str:>8}  {is_n:>5}  {is_pnl:>+9,.0f}  {is_d:>+8,.0f}  {oos_n:>5}  {oos_pnl:>+9,.0f}  {oos_d:>+8,.0f}  {wf:>7.3f}  {sw_hurt:>7}  {verdict}")
        print(f"         SW: {' | '.join(sw_parts)}")

    print("\nDONE.")


if __name__ == "__main__":
    main()

"""
AGG TIME DISTRIBUTION AUDIT (2026-06-17)

Mirror of safe_time_distribution_audit.py for AGG account (ITM-2 strikes).
AGG baseline includes all 3 enforced gates (ENFORCED-2, ENFORCED-3 + midday_trendline).

Question: Which 30-min windows are structurally bad for AGG?
Candidates already gated:
  - ENFORCED-2: conf+lvl_rec afternoon (14:00-15:55 blocked)
  - ENFORCED-3: conf+lvl_rej midday+afternoon (11:30-15:55 blocked)
Remaining question: what time windows do non-gated setups fire in, and are any of them bad?

Security: read-only, no Alpaca calls, no production writes.
"""
from __future__ import annotations
import sys, datetime as dt, pathlib, collections

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR = ROOT / "backtest" / "data"
SPY_FILE = DATA_DIR / "spy_5m_2025-01-01_2026-06-16.csv"
VIX_FILE = DATA_DIR / "vix_5m_2025-01-01_2026-06-16.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 6, 16)

# 30-min windows covering market hours 09:35-15:55
WINDOWS = [
    ("09:35-10:00", dt.time(9, 35),  dt.time(10, 0)),
    ("10:00-10:30", dt.time(10, 0),  dt.time(10, 30)),
    ("10:30-11:00", dt.time(10, 30), dt.time(11, 0)),
    ("11:00-11:30", dt.time(11, 0),  dt.time(11, 30)),
    ("11:30-12:00", dt.time(11, 30), dt.time(12, 0)),
    ("12:00-12:30", dt.time(12, 0),  dt.time(12, 30)),
    ("12:30-13:00", dt.time(12, 30), dt.time(13, 0)),
    ("13:00-13:30", dt.time(13, 0),  dt.time(13, 30)),
    ("13:30-14:00", dt.time(13, 30), dt.time(14, 0)),
    ("14:00-14:30", dt.time(14, 0),  dt.time(14, 30)),
    ("14:30-15:00", dt.time(14, 30), dt.time(15, 0)),
    ("15:00-15:30", dt.time(15, 0),  dt.time(15, 30)),
    ("15:30-15:55", dt.time(15, 30), dt.time(15, 55)),
]

# AGG production params — all 3 enforced gates active
AGG_KW = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    premium_stop_pct_bear=-0.07,
    tp1_premium_pct=0.75,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=5.0,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.50,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    block_conf_lvl_rec_afternoon=True,
    block_conf_lvl_rej_midday_afternoon=True,
)
AGG_OVR = {"vix_bull_max": 30.0, "vix_bear_threshold": 15.0, "strike_offset_itm": 2}


def _entry_time(t):
    et = t.entry_time_et
    return (et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et).time()


def _in_window(t_time, w_start, w_end):
    return w_start <= t_time < w_end


def _analyze(trades, label):
    print(f"\n  {label}: n={len(trades)} total pnl={sum(t.dollar_pnl for t in trades):+,.0f}")
    print(f"  {'Window':<16} {'n':>4} {'avg':>8} {'stop%':>7} {'total':>9}")
    print(f"  {'-'*50}")
    bad_windows = []
    good_windows = []
    for w_label, w_start, w_end in WINDOWS:
        in_w = [t for t in trades if _in_window(_entry_time(t), w_start, w_end)]
        if not in_w:
            continue
        n = len(in_w)
        total = sum(t.dollar_pnl for t in in_w)
        avg = total / n
        stops = sum(1 for t in in_w if t.dollar_pnl < 0)
        stop_pct = stops / n * 100
        flag = ""
        if avg < -30 and n >= 3:
            flag = " [BAD]"
            bad_windows.append((w_label, n, avg))
        if avg > 100 and n >= 2:
            flag = " [WIN]"
            good_windows.append((w_label, n, avg))
        print(f"  {w_label:<16} {n:>4} {avg:>8.0f} {stop_pct:>6.1f}% {total:>9,.0f}{flag}")
    return bad_windows, good_windows


if __name__ == "__main__":
    print("Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("\nRunning AGG IS backtest (all 3 enforced gates)...")
    r_is  = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END,
                         params_overrides=dict(AGG_OVR), **AGG_KW)
    print(f"IS: n={len(r_is.trades)} pnl={sum(t.dollar_pnl for t in r_is.trades):+,.0f}")

    print("\nRunning AGG OOS backtest (all 3 enforced gates)...")
    r_oos = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END,
                         params_overrides=dict(AGG_OVR), **AGG_KW)
    print(f"OOS: n={len(r_oos.trades)} pnl={sum(t.dollar_pnl for t in r_oos.trades):+,.0f}")

    print("\n" + "="*60)
    print("AGG TIME DISTRIBUTION (by entry_time_et)")
    print("="*60)

    bad_is, good_is   = _analyze(r_is.trades,  "IS  (2025-01-02 to 2026-05-07)")
    bad_oos, good_oos = _analyze(r_oos.trades, "OOS (2026-05-08 to 2026-06-16)")

    print("\n" + "="*60)
    print("LOSS CONCENTRATION (IS avg<-$30, n>=3):")
    for w, n, avg in bad_is:
        oos_match = [x for x in bad_oos if x[0] == w]
        oos_note = f"OOS avg={oos_match[0][1]:+.0f}" if oos_match else "OOS n=0 (no data)"
        c22_flag = "(C22 INVERSION)" if oos_match and oos_match[0][2] > 0 else "(STRUCTURAL - both bad)"
        print(f"  IS {w}: n={n} avg={avg:+.0f} | {oos_note} {c22_flag}")

    print("\nGAIN CONCENTRATION (IS avg>+$100, n>=2):")
    for w, n, avg in good_is:
        oos_match = [x for x in good_oos if x[0] == w]
        oos_note = f"OOS avg={oos_match[0][2]:+.0f}" if oos_match else "OOS n=0"
        print(f"  IS {w}: n={n} avg={avg:+.0f} | {oos_note}")

    print("\nOOS BAD WINDOWS (OOS avg<-$100, n>=1):")
    for w, n, avg in bad_oos:
        is_match = [x for x in bad_is if x[0] == w]
        is_note = f"IS avg={is_match[0][2]:+.0f}" if is_match else "IS avg>=0 (C22 INVERSION)"
        print(f"  OOS {w}: n={n} avg={avg:+.0f} | {is_note}")

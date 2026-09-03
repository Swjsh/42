"""
AGG POST-ENFORCED-5 TIME DISTRIBUTION AUDIT (2026-06-17)

Baseline: ALL 5 AGG ENFORCED gates active:
  ENFORCED-2: block conf+lvl_rec afternoon (14:00-15:55)
  ENFORCED-3: block conf+lvl_rej midday+afternoon (11:30-15:55)
  ENFORCED-4 equivalent: midday_trendline_gate=True
  ENFORCED-5: require_bearish_fill_bar=True (LOOK-AHEAD: idx+1 bearish close)

Question: After ENFORCED-5 removes bullish-fill-bar trades, which 30-min windows
still have structural loss clusters in the remaining n~79 IS trades?

Goal: find no_trade_window candidates for AGG that DON'T have the C22-block problem.
Structural windows (both IS and OOS bad) = safe to gate.
C22-inverted windows (IS bad, OOS good) = skip (block_level_rejection pattern).

Security: read-only, no Alpaca calls, no production writes.
"""
from __future__ import annotations
import sys, json, datetime as dt, pathlib, collections

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

IS_SUBWINDOWS = [
    ("W1 Jan-Jun 2025", dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2 Jul-Dec 2025", dt.date(2025, 7, 1),  dt.date(2025, 12, 31)),
    ("W3 Jan-Mar 2026", dt.date(2026, 1, 2),  dt.date(2026, 3, 31)),
    ("W4 Apr-May 2026", dt.date(2026, 4, 1),  dt.date(2026, 5, 7)),
]

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

# AGG ENFORCED-5 baseline (all 5 enforced gates)
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
    require_bearish_fill_bar=True,   # ENFORCED-5
)
AGG_OVR = {"vix_bull_max": 30.0, "vix_bear_threshold": 15.0, "strike_offset_itm": 2}


def _entry_time(t):
    et = t.entry_time_et
    return (et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et).time()


def _in_window(t_time, w_start, w_end):
    return w_start <= t_time < w_end


def _pnl(trades):
    return sum(t.dollar_pnl for t in trades)


def _analyze(trades, label):
    print(f"\n  {label}: n={len(trades)} total pnl={_pnl(trades):+,.0f}")
    print(f"  {'Window':<16} {'n':>4} {'avg':>8} {'stop%':>7} {'total':>9}")
    print(f"  {'-'*55}")
    bad_windows = []
    good_windows = []
    for w_label, w_start, w_end in WINDOWS:
        in_w = [t for t in trades if _in_window(_entry_time(t), w_start, w_end)]
        if not in_w:
            continue
        n = len(in_w)
        total = _pnl(in_w)
        avg = total / n
        stops = sum(1 for t in in_w if t.dollar_pnl < 0)
        stop_pct = stops / n * 100
        flag = ""
        if avg < -30 and n >= 2:
            flag = " [BAD]"
            bad_windows.append((w_label, n, avg, total))
        elif avg > 80 and n >= 2:
            flag = " [WIN]"
            good_windows.append((w_label, n, avg, total))
        print(f"  {w_label:<16} {n:>4} {avg:>+8.0f} {stop_pct:>6.1f}% {total:>+9,.0f}{flag}")
    return bad_windows, good_windows


if __name__ == "__main__":
    print("Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("\nRunning AGG IS (ENFORCED-5 baseline: all 5 gates)...")
    r_is  = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END,
                         params_overrides=dict(AGG_OVR), **AGG_KW)

    print("\nRunning AGG OOS (ENFORCED-5 baseline: all 5 gates)...")
    r_oos = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END,
                         params_overrides=dict(AGG_OVR), **AGG_KW)

    print(f"\nBaseline confirmed: IS n={len(r_is.trades)} pnl={_pnl(r_is.trades):+,.0f}")
    print(f"                    OOS n={len(r_oos.trades)} pnl={_pnl(r_oos.trades):+,.0f}")

    print("\n" + "=" * 65)
    print("AGG TIME DISTRIBUTION (post-ENFORCED-5 fill bar gate)")
    print("=" * 65)

    bad_is,  good_is  = _analyze(r_is.trades,  "IS  (2025-01-02 to 2026-05-07)")
    bad_oos, good_oos = _analyze(r_oos.trades, "OOS (2026-05-08 to 2026-06-16)")

    print("\n" + "=" * 65)
    print("LOSS CONCENTRATION ANALYSIS:")
    print("IS windows with avg < -$30, n >= 2:")
    for w, n, avg, total in bad_is:
        oos_match = [(x[0], x[1], x[2]) for x in bad_oos if x[0] == w]
        oos_good  = [(x[0], x[1], x[2]) for x in good_oos if x[0] == w]
        if oos_match:
            tag = "(STRUCTURAL - both bad)"
        elif oos_good:
            tag = "(C22 INVERSION - OOS good, DO NOT GATE)"
        else:
            oos_note = "OOS n=0 (no data - monitor Q3 2026)"
            tag = oos_note
        oos_display = f"OOS avg={oos_match[0][2]:+.0f}(n={oos_match[0][1]})" if oos_match else (
            f"OOS avg={oos_good[0][2]:+.0f}(n={oos_good[0][1]})" if oos_good else "OOS n=0"
        )
        print(f"  IS {w}: n={n} avg={avg:+.0f} total={total:+,.0f} | {oos_display} {tag}")

    print("\nOOS windows with avg < -$100, n >= 1 (reverse C22 check):")
    for w, n, avg, total in bad_oos:
        is_match = [(x[0], x[1], x[2]) for x in bad_is if x[0] == w]
        is_good  = [(x[0], x[1], x[2]) for x in good_is if x[0] == w]
        if is_match:
            tag = "(STRUCTURAL - both bad)"
        elif is_good:
            tag = "(C22 INVERSION - IS good, skipping would HURT IS)"
        else:
            is_note = "IS avg>=0 (PROBABLY C22 INVERSION)"
            tag = is_note
        is_display = f"IS avg={is_match[0][2]:+.0f}" if is_match else (
            f"IS avg={is_good[0][2]:+.0f}" if is_good else "IS n=0"
        )
        print(f"  OOS {w}: n={n} avg={avg:+.0f} total={total:+,.0f} | {is_display} {tag}")

    print("\nIS GAIN WINDOWS (potential must-trade zones, avg > +$80, n >= 2):")
    for w, n, avg, total in good_is:
        oos_match = [(x[0], x[1], x[2]) for x in good_oos if x[0] == w]
        oos_note = f"OOS avg={oos_match[0][2]:+.0f}" if oos_match else "OOS n=0"
        print(f"  IS {w}: n={n} avg={avg:+.0f} total={total:+,.0f} | {oos_note}")

    # Sub-window breakdown to check C22 structure in the remaining trades
    print("\n" + "=" * 65)
    print("ENFORCED-5 BASELINE SUB-WINDOW CONFIRMATION:")
    for sw_label, sw_start, sw_end in IS_SUBWINDOWS:
        r_sw = run_backtest(spy_df, vix_df, start_date=sw_start, end_date=sw_end,
                            params_overrides=dict(AGG_OVR), **AGG_KW)
        n = len(r_sw.trades)
        p = _pnl(r_sw.trades)
        wr = sum(1 for t in r_sw.trades if t.dollar_pnl > 0) / max(n, 1)
        print(f"  {sw_label}: n={n} pnl={p:+,.0f} WR={wr:.2%}")

    print("\nDone. Check output for no_trade_window candidates.")

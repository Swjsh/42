"""
FALSE_TRIGGER_FINGERPRINT (task 652266df)
OOS SUPER-class (3+ triggers) losers: do they all share max_favorable within 2% of entry?
IS parallel: identify IS 3+ trigger trades where max_favorable < entry+5%.
VIX and time-of-day patterns. Confirmation bar (first bar closes bearish) impact estimate.
NO production changes.
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


def n_triggers(t) -> int:
    return len(t.triggers_fired) if t.triggers_fired else 0


def is_no_move(t) -> bool:
    """max_favorable within 2% of entry_premium (never moved favorably)."""
    if t.entry_premium <= 0:
        return False
    return t.max_favorable_premium <= t.entry_premium * 1.02


def is_tiny_move(t) -> bool:
    """max_favorable < entry_premium * 1.05 (never moved >5% favorably)."""
    if t.entry_premium <= 0:
        return False
    return t.max_favorable_premium < t.entry_premium * 1.05


def time_bucket(t) -> str:
    h = t.entry_time_et.hour
    m = t.entry_time_et.minute
    minutes = h * 60 + m
    if minutes < 10 * 60:
        return "09:35-09:59"
    elif minutes < 11 * 60:
        return "10:00-10:59"
    elif minutes < 12 * 60:
        return "11:00-11:59"
    elif minutes < 13 * 60:
        return "12:00-12:59"
    else:
        return "13:00+"


def vix_bucket(t) -> str:
    v = t.entry_vix
    if v < 15:
        return "<15"
    elif v < 18:
        return "15-18"
    elif v < 22:
        return "18-22"
    else:
        return "22+"


def analyze_super_class(trades, label):
    all_t = [t for t in trades if n_triggers(t) >= 3]
    losers = [t for t in all_t if t.dollar_pnl < 0]
    no_move_losers = [t for t in losers if is_no_move(t)]
    tiny_move_losers = [t for t in losers if is_tiny_move(t)]

    print(f"\n{'='*60}")
    print(f"  {label} — SUPER-CLASS (3+ triggers)")
    print(f"{'='*60}")
    print(f"  Total 3+ trigger trades: {len(all_t)}")
    if len(all_t) == 0:
        print("  (no data)")
        return

    winners = [t for t in all_t if t.dollar_pnl >= 0]
    wr = len(winners) / len(all_t) * 100
    avg_pnl = sum(t.dollar_pnl for t in all_t) / len(all_t)
    print(f"  WR: {wr:.1f}%  Avg P&L: {avg_pnl:+.0f}")
    print(f"  Losers: {len(losers)}")
    if losers:
        pct_no_move = len(no_move_losers) / len(losers) * 100
        pct_tiny = len(tiny_move_losers) / len(losers) * 100
        print(f"  Losers with max_favorable <= entry+2%: {len(no_move_losers)} ({pct_no_move:.0f}%)")
        print(f"  Losers with max_favorable < entry+5%:  {len(tiny_move_losers)} ({pct_tiny:.0f}%)")

    # VIX pattern on no-move losers
    if no_move_losers:
        print(f"\n  VIX breakdown (no-move losers, max_fav<=entry+2%):")
        vix_counts = {}
        for t in no_move_losers:
            b = vix_bucket(t)
            vix_counts[b] = vix_counts.get(b, 0) + 1
        for b in ["<15", "15-18", "18-22", "22+"]:
            if b in vix_counts:
                print(f"    VIX {b}: n={vix_counts[b]}")

        print(f"\n  Time-of-day breakdown (no-move losers):")
        time_counts = {}
        for t in no_move_losers:
            b = time_bucket(t)
            time_counts[b] = time_counts.get(b, 0) + 1
        for b in ["09:35-09:59", "10:00-10:59", "11:00-11:59", "12:00-12:59", "13:00+"]:
            if b in time_counts:
                print(f"    {b}: n={time_counts[b]}")

    # Trigger composition breakdown on losers
    if losers:
        trigger_counter = {}
        for t in losers:
            key = tuple(sorted(t.triggers_fired or []))
            trigger_counter[key] = trigger_counter.get(key, 0) + 1
        print(f"\n  Top trigger combos (losers):")
        for combo, cnt in sorted(trigger_counter.items(), key=lambda x: -x[1])[:5]:
            print(f"    {list(combo)}: n={cnt}")

    # Confirmation bar: does first bar (N+2 in our system = exit bar 1) close bearish?
    # We don't track bar-by-bar, but max_adverse/max_favorable gives a proxy:
    # If max_favorable <= entry+2% AND max_adverse < entry*0.90 → hit stop immediately
    print(f"\n  False-start fingerprint (hit stop within first 2 bars):")
    immediate_stop = [t for t in losers if t.max_favorable_premium <= t.entry_premium * 1.02]
    if losers:
        print(f"    {len(immediate_stop)}/{len(losers)} losers never cleared entry+2% -> FALSE TRIGGER fingerprint")


def analyze_is_comparison(is_trades):
    all_super = [t for t in is_trades if n_triggers(t) >= 3]
    all_other = [t for t in is_trades if n_triggers(t) < 3]

    print(f"\n{'='*60}")
    print(f"  IS COMPARISON: 3+ triggers vs <3 triggers")
    print(f"{'='*60}")

    for label, group in [("3+ triggers (SUPER)", all_super), ("<3 triggers (STANDARD)", all_other)]:
        if not group:
            continue
        winners = [t for t in group if t.dollar_pnl >= 0]
        wr = len(winners) / len(group) * 100
        avg_pnl = sum(t.dollar_pnl for t in group) / len(group)
        tiny = [t for t in group if t.dollar_pnl < 0 and is_tiny_move(t)]
        pct_tiny = len(tiny) / max(len([t for t in group if t.dollar_pnl < 0]), 1) * 100
        print(f"  {label}: n={len(group)}  WR={wr:.1f}%  avg={avg_pnl:+.0f}")
        print(f"    Losers with <5% favorable move: {len(tiny)} ({pct_tiny:.0f}% of losers)")


def main():
    print("Loading data...")
    spy_df = pd.read_csv(MASTER_SPY)
    vix_df = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy_df)} rows  VIX {len(vix_df)} rows")

    print("\nRunning IS...")
    r_is = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, **SAFE_BASE)
    print(f"  IS trades: {len(r_is.trades)}")

    print("\nRunning OOS...")
    r_oos = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, **SAFE_BASE)
    print(f"  OOS trades: {len(r_oos.trades)}")

    analyze_super_class(r_is.trades, "IS")
    analyze_super_class(r_oos.trades, "OOS")
    analyze_is_comparison(r_is.trades)

    # Summary of 3+ trigger trades overall
    print(f"\n{'='*60}")
    print("  OVERALL 3+ trigger P&L")
    print(f"{'='*60}")
    for label, trades in [("IS", r_is.trades), ("OOS", r_oos.trades)]:
        super_t = [t for t in trades if n_triggers(t) >= 3]
        if super_t:
            total_pnl = sum(t.dollar_pnl for t in super_t)
            wr = len([t for t in super_t if t.dollar_pnl >= 0]) / len(super_t) * 100
            print(f"  {label}: n={len(super_t)}  total_pnl={total_pnl:+,.0f}  WR={wr:.1f}%")

    print("\nDONE.")


if __name__ == "__main__":
    main()

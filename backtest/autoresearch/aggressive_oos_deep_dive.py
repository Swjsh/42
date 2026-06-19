"""
AGGRESSIVE_TP1_OOS_DEEP_DIVE (1b82872a)

Detailed per-trade audit of Aggressive account OOS trades (2026-05-08 to 2026-06-16).
Questions:
  (1) What are the 3 biggest wins? Why did they work?
  (2) What are the 3 biggest losses? What pattern?
  (3) Trigger composition across OOS — TL-only vs confluence vs level_reclaim
  (4) Time-of-day distribution — where are profits concentrated?
  (5) VIX bucket — where does Aggressive beat/lose?
  (6) Exit reason distribution — TP1/runner/stop/time
  (7) Quality tier distribution (ELITE vs STANDARD)

Security: read-only. No Alpaca calls. Free-tier only.
"""
from __future__ import annotations
import sys
import json
import datetime as dt
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR = ROOT / "backtest" / "data"
SPY_FILE = DATA_DIR / "spy_5m_2025-01-01_2026-06-16.csv"
VIX_FILE = DATA_DIR / "vix_5m_2025-01-01_2026-06-16.csv"

OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 6, 16)

# Aggressive production params (post-Rank35)
AGG_BASE_KWARGS = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=False,
    premium_stop_pct_bear=-0.07,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=5.0,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.50,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    tp1_premium_pct=0.75,                 # C14 fix: must match production (default is 0.30)
    params_overrides={"vix_bear_threshold": 15.0, "vix_bull_max": 30.0},
)

AGG_BASE_KW = {k: v for k, v in AGG_BASE_KWARGS.items() if k != "params_overrides"}
AGG_OVERRIDES = {"vix_bear_threshold": 15.0, "vix_bull_max": 30.0}


def _date(t):
    et = t.entry_time_et
    d = et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et
    return d.date()


def _entry_et(t):
    et = t.entry_time_et
    if getattr(et, "tzinfo", None):
        et = et.replace(tzinfo=None)
    return et


def _triggers(t):
    trigs = getattr(t, "triggers_fired", [])
    if isinstance(trigs, str):
        try:
            trigs = json.loads(trigs)
        except Exception:
            trigs = [trigs]
    return trigs


def _trigger_label(t):
    trigs = _triggers(t)
    if not trigs:
        return "unknown"
    if trigs == ["trendline_rejection"]:
        return "TL-only"
    if "confluence" in trigs:
        return "confluence"
    if "level_reclaim" in trigs:
        return "level_reclaim"
    if "level_rejection" in trigs:
        return "level_rejection"
    if "ribbon_flip" in trigs:
        return "ribbon_flip"
    return "+".join(sorted(trigs))


def _time_bucket(t):
    et = _entry_et(t)
    m = et.hour * 60 + et.minute
    if m < 10 * 60 + 30:
        return "09:35-10:30"
    if m < 11 * 60 + 30:
        return "10:30-11:30"
    if m < 14 * 60:
        return "11:30-14:00"
    return "14:00+"


def _vix_bucket(vix):
    if vix is None:
        return "unknown"
    if vix < 17:
        return "<17"
    if vix < 20:
        return "17-20"
    if vix < 25:
        return "20-25"
    return "25+"


def _bucket_stats(trades):
    if not trades:
        return {"n": 0, "WR": 0.0, "avg": 0.0, "total": 0.0}
    n = len(trades)
    wins = sum(1 for t in trades if t.dollar_pnl > 0)
    total = sum(t.dollar_pnl for t in trades)
    return {"n": n, "WR": wins / n, "avg": total / n, "total": total}


if __name__ == "__main__":
    print("=" * 90)
    print(f"AGGRESSIVE OOS DEEP DIVE: {OOS_START} to {OOS_END}")
    print("=" * 90)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    result = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, params_overrides=AGG_OVERRIDES, **AGG_BASE_KW)
    trades = result.trades

    total_pnl = sum(t.dollar_pnl for t in trades)
    wins = [t for t in trades if t.dollar_pnl > 0]
    losses = [t for t in trades if t.dollar_pnl <= 0]
    wr = len(wins) / len(trades) if trades else 0.0

    print(f"\nOVERALL: n={len(trades)}  WR={wr:.1%}  total_pnl={total_pnl:+.0f}  avg={total_pnl/len(trades):+.0f}/trade")

    # Per-trade table
    print(f"\n{'Date':12}  {'Time':8}  {'Side':4}  {'VIX':5}  {'Triggers':30}  {'Hold':5}  {'Exit':12}  {'P&L':>8}")
    print("-" * 100)
    for t in sorted(trades, key=_date):
        d = _date(t)
        et = _entry_et(t)
        side = getattr(t, "side", "?")
        vix = getattr(t, "entry_vix", None)
        vix_s = f"{vix:.1f}" if vix else "?"
        trig_s = _trigger_label(t)
        hold = f"{t.hold_minutes:.0f}m" if t.hold_minutes else "?"
        exit_r = getattr(t, "exit_reason", "?") or "?"
        print(f"{str(d):12}  {str(et.time()):8}  {str(side):4}  {vix_s:5}  {trig_s:30}  {hold:5}  {str(exit_r):12}  {t.dollar_pnl:>+8.0f}")

    # Top 3 wins
    print(f"\n{'='*60}")
    print("TOP 3 WINS")
    print(f"{'='*60}")
    for i, t in enumerate(sorted(wins, key=lambda x: -x.dollar_pnl)[:3], 1):
        d = _date(t)
        et = _entry_et(t)
        vix = getattr(t, "entry_vix", None)
        print(f"\n  #{i}: {d} {et.time()} | pnl={t.dollar_pnl:+.0f} | triggers={_triggers(t)}")
        vix_s = f"{vix:.1f}" if vix is not None else "?"
        tp1_p = t.tp1_premium
        runner_p = t.runner_exit_premium
        tp1_s = f"{tp1_p:.2f}" if tp1_p is not None else "N/A"
        runner_s = f"{runner_p:.2f}" if runner_p is not None else "N/A"
        print(f"     VIX={vix_s}  side={getattr(t,'side','?')}  hold={t.hold_minutes:.0f}m  exit={getattr(t,'exit_reason','?')}")
        print(f"     entry_premium={t.entry_premium:.2f}  tp1_premium={tp1_s}  runner_premium={runner_s}")

    # Top 3 losses
    print(f"\n{'='*60}")
    print("TOP 3 LOSSES")
    print(f"{'='*60}")
    for i, t in enumerate(sorted(losses, key=lambda x: x.dollar_pnl)[:3], 1):
        d = _date(t)
        et = _entry_et(t)
        vix = getattr(t, "entry_vix", None)
        print(f"\n  #{i}: {d} {et.time()} | pnl={t.dollar_pnl:+.0f} | triggers={_triggers(t)}")
        vix_s2 = f"{vix:.1f}" if vix is not None else "?"
        max_adv = getattr(t, "max_adverse_premium", None)
        max_fav = getattr(t, "max_favorable_premium", None)
        adv_s = f"{max_adv:.2f}" if max_adv is not None else "N/A"
        fav_s = f"{max_fav:.2f}" if max_fav is not None else "N/A"
        print(f"     VIX={vix_s2}  side={getattr(t,'side','?')}  hold={t.hold_minutes:.0f}m  exit={getattr(t,'exit_reason','?')}")
        print(f"     entry_premium={t.entry_premium:.2f}  max_adv={adv_s}  max_fav={fav_s}")

    # Trigger composition
    print(f"\n{'='*60}")
    print("TRIGGER COMPOSITION")
    print(f"{'='*60}")
    by_trig = {}
    for t in trades:
        k = _trigger_label(t)
        by_trig.setdefault(k, []).append(t)
    print(f"  {'Trigger':32}  {'n':>4}  {'WR':>6}  {'avg':>8}  {'total':>9}")
    print("  " + "-" * 65)
    for k, ts in sorted(by_trig.items(), key=lambda x: -sum(t.dollar_pnl for t in x[1])):
        s = _bucket_stats(ts)
        print(f"  {k:32}  {s['n']:>4}  {s['WR']:>6.1%}  {s['avg']:>+8.0f}  {s['total']:>+9.0f}")

    # Time-of-day
    print(f"\n{'='*60}")
    print("TIME-OF-DAY BREAKDOWN")
    print(f"{'='*60}")
    by_time = {}
    for t in trades:
        k = _time_bucket(t)
        by_time.setdefault(k, []).append(t)
    print(f"  {'Bucket':20}  {'n':>4}  {'WR':>6}  {'avg':>8}  {'total':>9}")
    print("  " + "-" * 55)
    for k in ["09:35-10:30", "10:30-11:30", "11:30-14:00", "14:00+"]:
        ts = by_time.get(k, [])
        s = _bucket_stats(ts)
        print(f"  {k:20}  {s['n']:>4}  {s['WR']:>6.1%}  {s['avg']:>+8.0f}  {s['total']:>+9.0f}")

    # VIX breakdown
    print(f"\n{'='*60}")
    print("VIX BUCKET BREAKDOWN")
    print(f"{'='*60}")
    by_vix = {}
    for t in trades:
        k = _vix_bucket(getattr(t, "entry_vix", None))
        by_vix.setdefault(k, []).append(t)
    print(f"  {'VIX':10}  {'n':>4}  {'WR':>6}  {'avg':>8}  {'total':>9}")
    print("  " + "-" * 45)
    for k in ["<17", "17-20", "20-25", "25+"]:
        ts = by_vix.get(k, [])
        s = _bucket_stats(ts)
        print(f"  {k:10}  {s['n']:>4}  {s['WR']:>6.1%}  {s['avg']:>+8.0f}  {s['total']:>+9.0f}")

    # Exit reason
    print(f"\n{'='*60}")
    print("EXIT REASON BREAKDOWN")
    print(f"{'='*60}")
    by_exit = {}
    for t in trades:
        k = str(getattr(t, "exit_reason", "?") or "?")
        by_exit.setdefault(k, []).append(t)
    print(f"  {'Exit':20}  {'n':>4}  {'WR':>6}  {'avg':>8}  {'total':>9}")
    print("  " + "-" * 55)
    for k, ts in sorted(by_exit.items(), key=lambda x: -sum(t.dollar_pnl for t in x[1])):
        s = _bucket_stats(ts)
        print(f"  {k:20}  {s['n']:>4}  {s['WR']:>6.1%}  {s['avg']:>+8.0f}  {s['total']:>+9.0f}")

    print("\nANALYSIS COMPLETE.")

"""
Diagnostic: VIX distribution of ELITE+level_reclaim (BULL) trades.
IS + OOS separately, to find a VIX threshold that preserves OOS entries
while still blocking the IS losers.

Key question: if OOS ELITE bull entries are at VIX >= T, then gate
  "block ELITE bull ONLY when VIX < T" has zero OOS impact.
"""
import sys
import datetime as dt
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR  = ROOT / "backtest" / "data"
SPY_FILE  = DATA_DIR / "spy_5m_2025-01-01_2026-06-16.csv"
VIX_FILE  = DATA_DIR / "vix_5m_2025-01-01_2026-06-16.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 6, 16)

BASE = dict(
    use_real_fills=True,
    premium_stop_pct_bear=-0.10,
    premium_stop_pct_bull=-0.08,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    midday_trendline_gate=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
)


def get_entry_date(t):
    et = t.entry_time_et
    return et.date() if hasattr(et, "date") else dt.date.fromisoformat(str(et)[:10])


def get_quality(t):
    tf = set(t.triggers_fired or [])
    has_conf = "confluence" in tf
    has_rf   = "ribbon_flip" in tf
    has_lvl  = any(x in tf for x in ["level_rejection", "level_reclaim"])
    has_seq  = "sequence_rejection" in tf
    if (has_conf and has_rf) or len(tf) >= 3:
        return "SUPER"
    if has_conf or has_seq:
        return "ELITE"
    if has_lvl:
        return "LEVEL"
    return "TRENDLINE"


def vix_bucket(v):
    if v < 15: return "<15"
    if v < 17: return "15-17"
    if v < 20: return "17-20"
    if v < 25: return "20-25"
    if v < 30: return "25-30"
    return "30+"


def analyze(trades, label):
    elite_bull = [t for t in trades
                  if get_quality(t) == "ELITE"
                  and hasattr(t, "triggers_fired")
                  and "level_reclaim" in (t.triggers_fired or [])]

    if not elite_bull:
        print(f"  [{label}] No ELITE+level_reclaim trades found")
        return

    print(f"\n  [{label}] ELITE+level_reclaim (BULL) n={len(elite_bull)}, "
          f"pnl={sum(t.dollar_pnl for t in elite_bull):+,.0f}, "
          f"WR={sum(1 for t in elite_bull if t.dollar_pnl>0)/len(elite_bull):.1%}")

    by_vix = defaultdict(list)
    for t in elite_bull:
        b = vix_bucket(t.entry_vix if hasattr(t, "entry_vix") else 0)
        by_vix[b].append(t)

    print(f"  VIX distribution:")
    for bucket in ["<15", "15-17", "17-20", "20-25", "25-30", "30+"]:
        ts = by_vix.get(bucket, [])
        if not ts: continue
        pnl = sum(t.dollar_pnl for t in ts)
        wr  = sum(1 for t in ts if t.dollar_pnl > 0) / len(ts)
        avg = pnl / len(ts)
        print(f"    VIX {bucket:8s}  n={len(ts):4d}  pnl={pnl:+7,.0f}  WR={wr:.1%}  avg={avg:+.0f}/trade")

    # By time of day
    print(f"  Time distribution:")
    tod = defaultdict(list)
    for t in elite_bull:
        et = t.entry_time_et
        h = et.hour if hasattr(et, "hour") else int(str(et)[11:13])
        slot = f"{h:02d}xx"
        tod[slot].append(t)
    for slot in sorted(tod.keys()):
        ts = tod[slot]
        pnl = sum(t.dollar_pnl for t in ts)
        print(f"    {slot}  n={len(ts):4d}  pnl={pnl:+7,.0f}")


def main():
    print("Loading data...")
    spy = pd.read_csv(SPY_FILE)
    vix = pd.read_csv(VIX_FILE)

    print("Running IS baseline...")
    is_r = run_backtest(spy, vix, start_date=IS_START, end_date=IS_END, **BASE)

    print("Running OOS baseline...")
    oos_r = run_backtest(spy, vix, start_date=OOS_START, end_date=OOS_END, **BASE)

    analyze(is_r.trades, "IS  2025-01-02 to 2026-05-07")
    analyze(oos_r.trades, "OOS 2026-05-08 to 2026-06-16")

    # Also check what the "skipped" decisions look like — need vix from decisions
    # Check OOS decisions that would be skipped by BLOCK_ELITE_BULL
    print("\n  OOS ELITE+level_reclaim trade details (what the gate would block):")
    elite_bull_oos = [t for t in oos_r.trades
                      if get_quality(t) == "ELITE"
                      and hasattr(t, "triggers_fired")
                      and "level_reclaim" in (t.triggers_fired or [])]
    for t in sorted(elite_bull_oos, key=lambda x: str(x.entry_time_et)):
        d = get_entry_date(t)
        et = t.entry_time_et
        vix_val = t.entry_vix if hasattr(t, "entry_vix") else 0
        print(f"    {d}  {str(et)[11:16]}  VIX={vix_val:5.1f}  pnl={t.dollar_pnl:+7.0f}  "
              f"triggers={t.triggers_fired}")


if __name__ == "__main__":
    main()

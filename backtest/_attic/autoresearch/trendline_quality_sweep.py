"""
TRENDLINE-only entry quality discrimination.
Current baseline: n=64, pnl=-$100, WR=29.7% (breakeven drag).

Question: what discriminates profitable from unprofitable TRENDLINE-only entries?
Checks: VIX bucket, time-of-day, ribbon spread, day-of-week.

TRENDLINE-only = no level_rejection/level_reclaim AND no confluence AND no sequence_rejection.
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
SPY_FILE  = DATA_DIR / "spy_5m_2025-01-01_2026-05-22.csv"
VIX_FILE  = DATA_DIR / "vix_5m_2025-01-01_2026-05-22.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)

PROD = dict(
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


def breakdown(trades, key_fn, label):
    groups = defaultdict(lambda: {"n": 0, "pnl": 0, "wins": 0})
    for t in trades:
        k = key_fn(t)
        groups[k]["n"] += 1
        groups[k]["pnl"] += t.dollar_pnl
        if t.dollar_pnl > 0:
            groups[k]["wins"] += 1
    print(f"\n  Breakdown by {label}:")
    for k in sorted(groups.keys()):
        d = groups[k]
        n = d["n"]
        wr = d["wins"] / n
        avg = d["pnl"] / n
        tag = " *** " if wr >= 0.45 else ""
        print(f"    {str(k):<18s}  n={n:3d}  pnl={d['pnl']:+7,.0f}  WR={wr:.1%}  avg={avg:+6,.0f}{tag}")


def main():
    print("Loading data...")
    spy = pd.read_csv(SPY_FILE)
    vix = pd.read_csv(VIX_FILE)

    print("Running IS with CURRENT PRODUCTION PARAMS...")
    is_r = run_backtest(spy, vix, start_date=IS_START, end_date=IS_END, **PROD)

    trendline = [t for t in is_r.trades if get_quality(t) == "TRENDLINE"]
    print(f"\nTRENDLINE-only IS trades: n={len(trendline)}, "
          f"pnl={sum(t.dollar_pnl for t in trendline):+,.0f}, "
          f"WR={sum(1 for t in trendline if t.dollar_pnl > 0)/len(trendline):.1%}")

    # VIX bucket
    def vix_bucket(t):
        v = t.entry_vix
        if v < 15:   return "VIX<15"
        if v < 17:   return "VIX 15-17"
        if v < 19:   return "VIX 17-19"
        if v < 21:   return "VIX 19-21"
        if v < 25:   return "VIX 21-25"
        return           "VIX 25+"

    breakdown(trendline, vix_bucket, "VIX bucket")

    # Time of day
    def tod_bucket(t):
        et = t.entry_time_et
        if hasattr(et, "time"):
            h, m = et.hour, et.minute
        else:
            parts = str(et)[11:16].split(":")
            h, m = int(parts[0]), int(parts[1])
        if h < 10:  return "09:35-09:59"
        if h < 11:  return "10:00-10:59"
        if h < 12:  return "11:00-11:59"
        if h < 13:  return "12:00-12:59"
        if h < 14:  return "13:00-13:59"
        return          "14:00+"

    breakdown(trendline, tod_bucket, "time of day")

    # Year-quarter
    def yrq(t):
        et = t.entry_time_et
        if hasattr(et, "date"):
            d = et.date()
        else:
            d = dt.date.fromisoformat(str(et)[:10])
        q = (d.month - 1) // 3 + 1
        return f"{d.year}-Q{q}"

    breakdown(trendline, yrq, "year-quarter")

    # Is the first trade of the day for this setup?
    from collections import Counter
    date_counts: Counter = Counter()
    for t in is_r.trades:
        et = t.entry_time_et
        d = et.date() if hasattr(et, "date") else dt.date.fromisoformat(str(et)[:10])
        date_counts[d] += 1

    def is_first_on_day(t):
        et = t.entry_time_et
        d = et.date() if hasattr(et, "date") else dt.date.fromisoformat(str(et)[:10])
        # Is this a re-entry day (multiple trades same day)?
        all_same_day = [x for x in is_r.trades
                        if (x.entry_time_et.date() if hasattr(x.entry_time_et, "date")
                            else dt.date.fromisoformat(str(x.entry_time_et)[:10])) == d]
        return "ONLY" if len(all_same_day) == 1 else "RE-ENTRY"

    breakdown(trendline, is_first_on_day, "entry type (ONLY vs RE-ENTRY)")

    # Trigger combos
    def trig_combo(t):
        return "+".join(sorted(t.triggers_fired or []))

    breakdown(trendline, trig_combo, "trigger combination")

    # Gate candidates: VIX 15-17 block
    vix_cut = [t for t in trendline if t.entry_vix >= 17.0]
    n_cut = len(vix_cut)
    pnl_cut = sum(t.dollar_pnl for t in vix_cut)
    wr_cut = sum(1 for t in vix_cut if t.dollar_pnl > 0) / n_cut if n_cut else 0
    print(f"\n  Gate candidate: TRENDLINE only when VIX >= 17.0:")
    print(f"    n={n_cut}, pnl={pnl_cut:+,.0f}, WR={wr_cut:.1%}")

    # Time gate: trendline only when time not 11:00-14:00
    time_gate = [t for t in trendline
                 if not (11 <= (t.entry_time_et.hour if hasattr(t.entry_time_et, "hour")
                                else int(str(t.entry_time_et)[11:13])) < 14)]
    n_tg = len(time_gate)
    pnl_tg = sum(t.dollar_pnl for t in time_gate)
    wr_tg = sum(1 for t in time_gate if t.dollar_pnl > 0) / n_tg if n_tg else 0
    print(f"\n  Gate candidate: TRENDLINE only OUTSIDE 11:00-14:00 (morning+afternoon only):")
    print(f"    n={n_tg}, pnl={pnl_tg:+,.0f}, WR={wr_tg:.1%}")

    print("\n[ANALYSIS COMPLETE]")


if __name__ == "__main__":
    main()

"""
ELITE-tier entry quality discrimination.
Current baseline: n=125, pnl=+$2,892, WR=20%.

ELITE = has confluence OR has sequence_rejection (without SUPER triggers).
SUPER = (confluence AND ribbon_flip) OR len(triggers) >= 3.

Goal: find sub-features that predict profitable vs losing ELITE entries.
"""
import sys
import datetime as dt
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR = ROOT / "backtest" / "data"
SPY_FILE = DATA_DIR / "spy_5m_2025-01-01_2026-05-22.csv"
VIX_FILE = DATA_DIR / "vix_5m_2025-01-01_2026-05-22.csv"

IS_START = dt.date(2025, 1, 2)
IS_END   = dt.date(2026, 5, 7)

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
    print(f"\n  By {label}:")
    for k in sorted(groups.keys()):
        d = groups[k]
        n = d["n"]
        wr = d["wins"] / n
        avg = d["pnl"] / n
        flag = " *** KEEP" if (wr >= 0.45 and avg > 20) else (" *** HIGH-AVG" if avg > 100 else "")
        print(f"    {str(k):<22s}  n={n:3d}  pnl={d['pnl']:+8,.0f}  WR={wr:.1%}  avg={avg:+7,.0f}{flag}")


def main():
    print("Loading data...")
    spy = pd.read_csv(SPY_FILE)
    vix = pd.read_csv(VIX_FILE)

    print("Running IS with production params...")
    r = run_backtest(spy, vix, start_date=IS_START, end_date=IS_END, **PROD)

    elite = [t for t in r.trades if get_quality(t) == "ELITE"]
    n_e   = len(elite)
    pnl_e = sum(t.dollar_pnl for t in elite)
    wr_e  = sum(1 for t in elite if t.dollar_pnl > 0) / n_e if n_e else 0
    print(f"\nELITE IS: n={n_e}, pnl={pnl_e:+,.0f}, WR={wr_e:.1%}")

    # Sub-type: confluence vs sequence_rejection
    def subtype(t):
        tf = set(t.triggers_fired or [])
        if "confluence" in tf and "sequence_rejection" in tf:
            return "both"
        if "confluence" in tf:
            return "confluence_only"
        return "sequence_rejection_only"

    breakdown(elite, subtype, "sub-type (confluence vs sequence_rejection)")

    # Direction: CALL vs PUT
    def direction(t):
        return getattr(t, "direction", None) or getattr(t, "winning_side", None) or "?"

    breakdown(elite, direction, "direction (C/P)")

    # VIX bucket
    def vix_bucket(t):
        v = t.entry_vix
        if v < 15:   return "VIX<15"
        if v < 17:   return "VIX 15-17"
        if v < 19:   return "VIX 17-19"
        if v < 21:   return "VIX 19-21"
        if v < 25:   return "VIX 21-25"
        return           "VIX 25+"

    breakdown(elite, vix_bucket, "VIX bucket")

    # Time of day
    def tod(t):
        et = t.entry_time_et
        h = et.hour if hasattr(et, "hour") else int(str(et)[11:13])
        if h < 10:  return "09:35-09:59"
        if h < 11:  return "10:00-10:59"
        if h < 12:  return "11:00-11:59"
        if h < 13:  return "12:00-12:59"
        if h < 14:  return "13:00-13:59"
        return          "14:00+"

    breakdown(elite, tod, "time of day")

    # Quarter
    def yrq(t):
        et = t.entry_time_et
        d = et.date() if hasattr(et, "date") else dt.date.fromisoformat(str(et)[:10])
        q = (d.month - 1) // 3 + 1
        return f"{d.year}-Q{q}"

    breakdown(elite, yrq, "year-quarter")

    # Trigger combo
    def trig_combo(t):
        return "+".join(sorted(t.triggers_fired or []))

    breakdown(elite, trig_combo, "trigger combo")

    # Sub-type × direction
    def subtype_dir(t):
        tf = set(t.triggers_fired or [])
        s = "conf" if "confluence" in tf else "seq"
        d = direction(t) or "?"
        return f"{s}×{d}"

    breakdown(elite, subtype_dir, "sub-type × direction")

    # Gate candidate: confluence_only trades with VIX >= 19
    conf_hi_vix = [t for t in elite
                   if "confluence" in (t.triggers_fired or [])
                   and "sequence_rejection" not in (t.triggers_fired or [])
                   and t.entry_vix >= 19.0]
    if conf_hi_vix:
        pnl_c = sum(t.dollar_pnl for t in conf_hi_vix)
        wr_c  = sum(1 for t in conf_hi_vix if t.dollar_pnl > 0) / len(conf_hi_vix)
        print(f"\n  Gate candidate — confluence_only, VIX>=19: n={len(conf_hi_vix)}, pnl={pnl_c:+,.0f}, WR={wr_c:.1%}")

    # Gate candidate: sequence_rejection-only trades in morning
    seq_morn = [t for t in elite
                if "sequence_rejection" in (t.triggers_fired or [])
                and "confluence" not in (t.triggers_fired or [])
                and (t.entry_time_et.hour if hasattr(t.entry_time_et, "hour")
                     else int(str(t.entry_time_et)[11:13])) < 11]
    if seq_morn:
        pnl_s = sum(t.dollar_pnl for t in seq_morn)
        wr_s  = sum(1 for t in seq_morn if t.dollar_pnl > 0) / len(seq_morn)
        print(f"\n  Gate candidate — sequence_rejection morning (< 11:00): n={len(seq_morn)}, pnl={pnl_s:+,.0f}, WR={wr_s:.1%}")

    print("\n[ANALYSIS COMPLETE]")


if __name__ == "__main__":
    main()

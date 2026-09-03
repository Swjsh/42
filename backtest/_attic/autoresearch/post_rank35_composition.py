"""
Post-Rank35 baseline composition analysis.

Production baseline (all deployed gates through Rank 35):
  block_level_rejection=True
  premium_stop_pct_bear=-0.10
  block_elite_bull=True (VIX 15-17.5)
  vix_bull_max=18.0
  tp1_qty_fraction=0.667
  time_stop_minutes_before_close=20
  midday_trendline_gate=True
  no_trade_before=09:35

Goal: break down the 128 IS and 21 OOS trades by trigger, tier, VIX, and time
to identify what remains and where the next improvement opportunity lies.
"""
import datetime as dt
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest"))

import pandas as pd
from lib.orchestrator import run_backtest

MASTER_SPY = ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
MASTER_VIX = ROOT / "backtest" / "data" / "vix_5m_2025-01-01_2026-06-16.csv"

IS_S = dt.date(2025, 1, 2)
IS_E = dt.date(2026, 5, 7)
OOS_S = dt.date(2026, 5, 8)
OOS_E = dt.date(2026, 6, 16)

PROD_KWARGS = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    premium_stop_pct_bear=-0.10,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    params_overrides={"vix_bull_max": 18.0},
)


def vix_bucket(v):
    if v is None or v == 0:
        return "unknown"
    v = float(v)
    if v < 15:
        return "<15"
    elif v < 17:
        return "15-17"
    elif v < 18:
        return "17-18"
    elif v < 20:
        return "18-20"
    elif v < 22:
        return "20-22"
    elif v < 25:
        return "22-25"
    elif v < 30:
        return "25-30"
    else:
        return "30+"


def time_bucket(t):
    if t is None:
        return "unknown"
    h = t.hour
    m = t.minute
    if h == 9:
        return "09:3x"
    elif h == 10:
        return "10:xx"
    elif h == 11:
        return "11:xx"
    elif h == 12:
        return "12:xx"
    elif h == 13:
        return "13:xx"
    else:
        return "14:xx+"


def get_trigger_key(t):
    triggers = sorted(getattr(t, "triggers_fired", None) or [])
    return "+".join(triggers) if triggers else "unknown"


def get_quality_tier(t):
    return getattr(t, "quality_tier", None) or "?"


def get_side(t):
    return getattr(t, "side", "?")


def get_exit_type(t):
    return getattr(t, "exit_reason", None) or getattr(t, "exit_type", None) or "?"


def summarize(trades, label):
    if not trades:
        print(f"\n{label}: n=0")
        return

    total_pnl = sum(t.dollar_pnl for t in trades)
    wins = sum(1 for t in trades if t.dollar_pnl > 0)
    wr = wins / len(trades)
    avg = total_pnl / len(trades)

    print(f"\n{'='*70}")
    print(f"  {label}: n={len(trades)} pnl={total_pnl:+.0f} avg={avg:+.0f} WR={wr:.0%}")
    print(f"{'='*70}")

    # By side
    bears = [t for t in trades if get_side(t) == "P"]
    bulls = [t for t in trades if get_side(t) == "C"]
    print(f"\n  By side:")
    if bears:
        bp = sum(t.dollar_pnl for t in bears)
        bwr = sum(1 for t in bears if t.dollar_pnl > 0) / len(bears)
        print(f"    BEAR (PUT): n={len(bears):3d} pnl={bp:+.0f} avg={bp/len(bears):+.0f} WR={bwr:.0%}")
    if bulls:
        bp = sum(t.dollar_pnl for t in bulls)
        bwr = sum(1 for t in bulls if t.dollar_pnl > 0) / len(bulls)
        print(f"    BULL (CALL): n={len(bulls):3d} pnl={bp:+.0f} avg={bp/len(bulls):+.0f} WR={bwr:.0%}")

    # By quality tier
    tier_data = defaultdict(list)
    for t in trades:
        tier_data[get_quality_tier(t)].append(t)
    print(f"\n  By quality tier:")
    for tier in ["SUPER", "ELITE", "TRENDLINE", "LEVEL", "?"]:
        ts = tier_data.get(tier, [])
        if not ts:
            continue
        p = sum(t.dollar_pnl for t in ts)
        w = sum(1 for t in ts if t.dollar_pnl > 0) / len(ts)
        print(f"    {tier:<12}: n={len(ts):3d} pnl={p:+.0f} avg={p/len(ts):+.0f} WR={w:.0%}")

    # By trigger key
    trig_data = defaultdict(list)
    for t in trades:
        trig_data[get_trigger_key(t)].append(t)
    sorted_trigs = sorted(trig_data.items(), key=lambda x: -sum(tt.dollar_pnl for tt in x[1]))
    print(f"\n  By trigger set (top 15 by P&L):")
    print(f"    {'trigger':<55} {'n':>4} {'pnl':>8} {'avg':>7} {'WR':>6}")
    print(f"    {'-'*55} {'-'*4} {'-'*8} {'-'*7} {'-'*6}")
    for key, ts in sorted_trigs[:15]:
        p = sum(t.dollar_pnl for t in ts)
        w = sum(1 for t in ts if t.dollar_pnl > 0) / len(ts)
        print(f"    {key:<55} {len(ts):>4} {p:>+8.0f} {p/len(ts):>+7.0f} {w:>6.0%}")

    # By VIX bucket
    vix_data = defaultdict(list)
    for t in trades:
        vix_data[vix_bucket(getattr(t, "entry_vix", None))].append(t)
    print(f"\n  By VIX bucket:")
    for bkt in ["<15", "15-17", "17-18", "18-20", "20-22", "22-25", "25-30", "30+", "unknown"]:
        ts = vix_data.get(bkt, [])
        if not ts:
            continue
        p = sum(t.dollar_pnl for t in ts)
        w = sum(1 for t in ts if t.dollar_pnl > 0) / len(ts)
        print(f"    VIX {bkt:<7}: n={len(ts):3d} pnl={p:+.0f} avg={p/len(ts):+.0f} WR={w:.0%}")

    # By time bucket
    time_data = defaultdict(list)
    for t in trades:
        te = getattr(t, "entry_time_et", None)
        time_data[time_bucket(te)].append(t)
    print(f"\n  By time of day:")
    for bkt in ["09:3x", "10:xx", "11:xx", "12:xx", "13:xx", "14:xx+"]:
        ts = time_data.get(bkt, [])
        if not ts:
            continue
        p = sum(t.dollar_pnl for t in ts)
        w = sum(1 for t in ts if t.dollar_pnl > 0) / len(ts)
        print(f"    {bkt}: n={len(ts):3d} pnl={p:+.0f} avg={p/len(ts):+.0f} WR={w:.0%}")

    # By exit type
    exit_data = defaultdict(list)
    for t in trades:
        exit_data[get_exit_type(t)].append(t)
    print(f"\n  By exit type:")
    for exit_t, ts in sorted(exit_data.items(), key=lambda x: -len(x[1])):
        p = sum(t.dollar_pnl for t in ts)
        print(f"    {exit_t:<25}: n={len(ts):3d} pnl={p:+.0f}")

    # Tier x side cross-tab
    print(f"\n  Tier x side (bear/bull split):")
    for tier in ["SUPER", "ELITE", "TRENDLINE", "LEVEL"]:
        ts_tier = tier_data.get(tier, [])
        if not ts_tier:
            continue
        bears_t = [t for t in ts_tier if get_side(t) == "P"]
        bulls_t = [t for t in ts_tier if get_side(t) == "C"]
        if bears_t:
            bp = sum(t.dollar_pnl for t in bears_t)
            bwr = sum(1 for t in bears_t if t.dollar_pnl > 0) / len(bears_t)
            print(f"    {tier} BEAR: n={len(bears_t):3d} pnl={bp:+.0f} avg={bp/len(bears_t):+.0f} WR={bwr:.0%}")
        if bulls_t:
            bp = sum(t.dollar_pnl for t in bulls_t)
            bwr = sum(1 for t in bulls_t if t.dollar_pnl > 0) / len(bulls_t)
            print(f"    {tier} BULL: n={len(bulls_t):3d} pnl={bp:+.0f} avg={bp/len(bulls_t):+.0f} WR={bwr:.0%}")


def main():
    print("Loading data...")
    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy)} rows, VIX {len(vix)} rows")

    print("\nRunning IS backtest (post-Rank35 production baseline)...")
    is_r = run_backtest(spy, vix, start_date=IS_S, end_date=IS_E, **PROD_KWARGS)
    print(f"IS complete: n={len(is_r.trades)}")

    print("\nRunning OOS backtest...")
    oos_r = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **PROD_KWARGS)
    print(f"OOS complete: n={len(oos_r.trades)}")

    summarize(is_r.trades, "IN-SAMPLE (Post-Rank35)")
    summarize(oos_r.trades, "OUT-OF-SAMPLE (Post-Rank35)")

    # IS vs OOS trigger comparison
    print(f"\n{'='*70}")
    print("  IS vs OOS TRIGGER COMPARISON")
    print(f"{'='*70}")

    is_by_trig = defaultdict(list)
    oos_by_trig = defaultdict(list)
    for t in is_r.trades:
        is_by_trig[get_trigger_key(t)].append(t)
    for t in oos_r.trades:
        oos_by_trig[get_trigger_key(t)].append(t)

    all_keys = set(is_by_trig.keys()) | set(oos_by_trig.keys())
    rows = []
    for key in all_keys:
        is_ts = is_by_trig.get(key, [])
        oos_ts = oos_by_trig.get(key, [])
        is_pnl = sum(t.dollar_pnl for t in is_ts)
        oos_pnl = sum(t.dollar_pnl for t in oos_ts)
        is_wr = sum(1 for t in is_ts if t.dollar_pnl > 0) / len(is_ts) if is_ts else 0
        oos_wr = sum(1 for t in oos_ts if t.dollar_pnl > 0) / len(oos_ts) if oos_ts else 0
        note = ""
        if is_pnl < 0 and oos_pnl > 0:
            note = "  IS loses, OOS wins! (C22?)"
        elif is_pnl > 0 and oos_pnl < 0:
            note = "  IS wins, OOS loses"
        rows.append((key, len(is_ts), is_pnl, is_wr, len(oos_ts), oos_pnl, oos_wr, note))

    rows.sort(key=lambda x: -(x[1] + x[4]))
    print(f"\n  {'trigger':<50} {'IS_n':>5} {'IS_pnl':>8} {'IS_WR':>6}  {'OOS_n':>5} {'OOS_pnl':>8} {'OOS_WR':>6}")
    print(f"  {'-'*50} {'-'*5} {'-'*8} {'-'*6}  {'-'*5} {'-'*8} {'-'*6}")
    for row in rows:
        key, in_, ip, iwr, on, op, owr, note = row
        print(f"  {key:<50} {in_:>5} {ip:>+8.0f} {iwr:>6.0%}  {on:>5} {op:>+8.0f} {owr:>6.0%}{note}")

    # Bear trendline deep-dive
    tl_is = [t for t in is_r.trades if "trendline_rejection" in (getattr(t, "triggers_fired", None) or []) and get_side(t) == "P"]
    tl_oos = [t for t in oos_r.trades if "trendline_rejection" in (getattr(t, "triggers_fired", None) or []) and get_side(t) == "P"]
    print(f"\n{'='*70}")
    print(f"  BEAR TRENDLINE ENTRIES (remaining drag analysis)")
    print(f"{'='*70}")
    if tl_is:
        tp = sum(t.dollar_pnl for t in tl_is)
        twr = sum(1 for t in tl_is if t.dollar_pnl > 0) / len(tl_is)
        print(f"  IS: n={len(tl_is)} pnl={tp:+.0f} avg={tp/len(tl_is):+.0f} WR={twr:.0%}")
        # VIX breakdown
        vix_d = defaultdict(list)
        for t in tl_is:
            vix_d[vix_bucket(getattr(t, "entry_vix", None))].append(t)
        print(f"  IS TL by VIX:")
        for bkt in ["<15", "15-17", "17-18", "18-20", "20-22", "22-25", "25-30", "30+"]:
            ts = vix_d.get(bkt, [])
            if not ts:
                continue
            p = sum(t.dollar_pnl for t in ts)
            w = sum(1 for t in ts if t.dollar_pnl > 0) / len(ts)
            print(f"    VIX {bkt}: n={len(ts)} pnl={p:+.0f} WR={w:.0%}")
        # Time breakdown
        time_d = defaultdict(list)
        for t in tl_is:
            time_d[time_bucket(getattr(t, "entry_time_et", None))].append(t)
        print(f"  IS TL by time:")
        for bkt in ["09:3x", "10:xx", "11:xx", "12:xx", "13:xx", "14:xx+"]:
            ts = time_d.get(bkt, [])
            if not ts:
                continue
            p = sum(t.dollar_pnl for t in ts)
            w = sum(1 for t in ts if t.dollar_pnl > 0) / len(ts)
            print(f"    {bkt}: n={len(ts)} pnl={p:+.0f} WR={w:.0%}")

    if tl_oos:
        tp = sum(t.dollar_pnl for t in tl_oos)
        print(f"  OOS: n={len(tl_oos)} pnl={tp:+.0f}")
    else:
        print(f"  OOS: n=0 (no TL bear entries)")

    print("\nComposition analysis complete.")


if __name__ == "__main__":
    main()

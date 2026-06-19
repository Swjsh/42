"""
OOS check: do LEVEL trades in VIX 20-30 also lose in OOS?
If yes, a level_vix_max=20 gate is a strong candidate.
"""
import sys
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR  = ROOT / "backtest" / "data"
SPY_FILE  = DATA_DIR / "spy_5m_2025-01-01_2026-05-22.csv"
VIX_FILE  = DATA_DIR / "vix_5m_2025-01-01_2026-05-22.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 5, 22)

BASE = dict(
    use_real_fills=True,
    premium_stop_pct_bear=-0.20,
    premium_stop_pct_bull=-0.08,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    midday_trendline_gate=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    per_trade_risk_cap_pct=0.30,
)

J_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}


def classify_tier(triggers):
    full = [x.lower() for x in triggers]
    has_confluence = any("confluence" in x for x in full)
    has_ribbon_flip = any("ribbon_flip" in x for x in full)
    has_sequence = any("sequence_rejection" in x for x in full)
    has_level = any(x in ("level_rejection", "level_reclaim") for x in full)
    has_trendline = any("trendline_rejection" in x for x in full)
    n = len(triggers)
    if n >= 3 and has_confluence and has_ribbon_flip:
        return "SUPER"
    elif n >= 2 and (has_confluence or has_sequence):
        return "ELITE"
    elif has_level:
        return "LEVEL"
    elif has_trendline:
        return "TRENDLINE"
    else:
        return "BASE"


def vix_bucket(vix):
    if vix < 17.30:
        return "A(<17.3)"
    elif vix < 20:
        return "B(17-20)"
    elif vix < 30:
        return "C(20-30)"
    else:
        return "D(30+)"


def analyse(trades, label):
    print(f"\n{'='*68}")
    print(f"{label}  n={len(trades)}")
    print(f"{'='*68}")

    level_trades = [t for t in trades if classify_tier(t.triggers_fired) == "LEVEL"]
    non_level = [t for t in trades if classify_tier(t.triggers_fired) != "LEVEL"]

    nl_pnl  = sum(t.dollar_pnl for t in non_level)
    lv_pnl  = sum(t.dollar_pnl for t in level_trades)
    all_pnl = sum(t.dollar_pnl for t in trades)

    print(f"  ALL trades:        n={len(trades):4d}  pnl={all_pnl:+,.0f}")
    print(f"  LEVEL trades:      n={len(level_trades):4d}  pnl={lv_pnl:+,.0f}")
    print(f"  non-LEVEL trades:  n={len(non_level):4d}  pnl={nl_pnl:+,.0f}")

    if not level_trades:
        return

    print(f"\n  LEVEL by VIX bucket:")
    vb = {}
    for t in level_trades:
        b = vix_bucket(t.entry_vix)
        if b not in vb:
            vb[b] = {"n": 0, "pnl": 0.0, "wins": 0, "trades": []}
        vb[b]["n"] += 1
        vb[b]["pnl"] += t.dollar_pnl
        if t.dollar_pnl > 0:
            vb[b]["wins"] += 1
        vb[b]["trades"].append(t)

    for b in sorted(vb.keys()):
        s = vb[b]
        wr = s["wins"] / s["n"] * 100
        avg = s["pnl"] / s["n"]
        print(f"    {b:12s}  n={s['n']:3d}  WR={wr:4.1f}%  total={s['pnl']:+,.0f}  avg={avg:+.0f}")
        for t in s["trades"][:3]:
            d = t.entry_time_et.date() if hasattr(t.entry_time_et, 'date') else str(t.entry_time_et)[:10]
            print(f"       -> {d}  VIX={t.entry_vix:.2f}  pnl={t.dollar_pnl:+.0f}  trigs={t.triggers_fired}")

    # Simulate: block C bucket (VIX 20-30)
    keep = [t for t in trades if not (classify_tier(t.triggers_fired) == "LEVEL" and 20 <= t.entry_vix < 30)]
    blocked = [t for t in trades if classify_tier(t.triggers_fired) == "LEVEL" and 20 <= t.entry_vix < 30]
    keep_pnl = sum(t.dollar_pnl for t in keep)
    block_pnl = sum(t.dollar_pnl for t in blocked)
    delta = keep_pnl - all_pnl

    print(f"\n  SIMULATE block VIX-20-30 LEVEL trades:")
    print(f"    Blocked: n={len(blocked)}  pnl_removed={block_pnl:+,.0f}")
    print(f"    Remaining: n={len(keep)}  pnl={keep_pnl:+,.0f}")
    print(f"    Delta vs baseline: {delta:+,.0f}")

    # Also check J anchor days
    print(f"\n  J anchor days (LEVEL trades only):")
    for j_day in sorted(J_WINNERS):
        j_trades = [t for t in level_trades
                    if hasattr(t.entry_time_et, 'date') and t.entry_time_et.date() == j_day]
        if j_trades:
            pnl = sum(t.dollar_pnl for t in j_trades)
            vix_vals = [f"{t.entry_vix:.1f}" for t in j_trades]
            print(f"    {j_day}  n={len(j_trades)}  pnl={pnl:+.0f}  vix={vix_vals}")
        else:
            print(f"    {j_day}  no LEVEL trades")


def main():
    print("Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("Running IS backtest...")
    is_result = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, **BASE)

    print("Running OOS backtest...")
    oos_result = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, **BASE)

    analyse(is_result.trades, "IS  (2025-01-02 to 2026-05-07)")
    analyse(oos_result.trades, "OOS (2026-05-08 to 2026-05-22)")

    # Compute WF for the proposed gate (blocking VIX 20-30 LEVEL trades)
    is_all_pnl  = sum(t.dollar_pnl for t in is_result.trades)
    oos_all_pnl = sum(t.dollar_pnl for t in oos_result.trades)

    is_blocked  = [t for t in is_result.trades
                   if classify_tier(t.triggers_fired) == "LEVEL" and 20 <= t.entry_vix < 30]
    oos_blocked = [t for t in oos_result.trades
                   if classify_tier(t.triggers_fired) == "LEVEL" and 20 <= t.entry_vix < 30]

    is_keep_pnl  = sum(t.dollar_pnl for t in is_result.trades if t not in set(is_blocked))
    oos_keep_pnl = sum(t.dollar_pnl for t in oos_result.trades if t not in set(oos_blocked))

    n_is_base  = len(is_result.trades)
    n_oos_base = len(oos_result.trades)
    n_is_cand  = n_is_base - len(is_blocked)
    n_oos_cand = n_oos_base - len(oos_blocked)

    is_delta  = is_keep_pnl - is_all_pnl
    oos_delta = oos_keep_pnl - oos_all_pnl

    print(f"\n{'='*68}")
    print("PROPOSED GATE: block LEVEL trades when VIX in [20, 30)")
    print(f"{'='*68}")
    print(f"  IS:  baseline n={n_is_base} pnl={is_all_pnl:+,.0f}  cand n={n_is_cand} pnl={is_keep_pnl:+,.0f}  delta={is_delta:+,.0f}")
    print(f"  OOS: baseline n={n_oos_base} pnl={oos_all_pnl:+,.0f}  cand n={n_oos_cand} pnl={oos_keep_pnl:+,.0f}  delta={oos_delta:+,.0f}")

    if is_delta != 0 and n_is_base > 0 and n_oos_base > 0:
        wf = (oos_delta / n_oos_base) / (is_delta / n_is_base)
        print(f"  WF_norm = ({oos_delta}/{n_oos_base}) / ({is_delta}/{n_is_base}) = {wf:.3f}")
    else:
        print(f"  WF_norm = N/A (IS delta={is_delta})")

    # Anchor check
    print(f"\n  J anchor check (LEVEL VIX-20-30 blocked):")
    for j_day in sorted(J_WINNERS):
        is_j_block = [t for t in is_blocked
                      if hasattr(t.entry_time_et, 'date') and t.entry_time_et.date() == j_day]
        delta = sum(t.dollar_pnl for t in is_j_block)
        if is_j_block:
            print(f"    {j_day}  blocked n={len(is_j_block)}  delta={delta:+.0f}  {'HURT' if delta > 0 else 'OK'}")
        else:
            print(f"    {j_day}  nothing blocked  OK")

    print("\n[ANALYSIS COMPLETE]")


if __name__ == "__main__":
    main()

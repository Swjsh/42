"""
Engine-level sweep: block_level_rejection gate via proper run_backtest parameter.
Unlike level_rejection_gate_sweep.py (post-hoc), this simulation correctly handles
quality-lock cascade effects (blocked trades don't consume the LEVEL lock slot).
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

J_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}

IS_SUB_WINDOWS = [
    ("W1", dt.date(2025,  1,  2), dt.date(2025,  6, 30)),
    ("W2", dt.date(2025,  7,  1), dt.date(2025, 12, 31)),
    ("W3", dt.date(2026,  1,  1), dt.date(2026,  3, 31)),
    ("W4", dt.date(2026,  4,  1), dt.date(2026,  5,  7)),
]

OOS_ROLLING = [
    ("OOS_W1", dt.date(2026, 5,  8), dt.date(2026, 5, 14)),
    ("OOS_W2", dt.date(2026, 5, 15), dt.date(2026, 5, 22)),
]

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


def get_entry_date(t):
    et = t.entry_time_et
    if hasattr(et, 'date'):
        return et.date()
    return dt.date.fromisoformat(str(et)[:10])


def pnl_window(trades, start, end):
    in_w = [t for t in trades if start <= get_entry_date(t) <= end]
    return sum(t.dollar_pnl for t in in_w)


def main():
    print("Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("Running BASE backtests...")
    is_base  = run_backtest(spy_df, vix_df, start_date=IS_START,  end_date=IS_END,  **BASE)
    oos_base = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, **BASE)

    print("Running CANDIDATE backtests (block_level_rejection=True)...")
    is_cand  = run_backtest(spy_df, vix_df, start_date=IS_START,  end_date=IS_END,
                             **BASE, block_level_rejection=True)
    oos_cand = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END,
                             **BASE, block_level_rejection=True)

    n_is_base  = len(is_base.trades)
    n_oos_base = len(oos_base.trades)
    n_is_cand  = len(is_cand.trades)
    n_oos_cand = len(oos_cand.trades)

    is_base_pnl  = sum(t.dollar_pnl for t in is_base.trades)
    oos_base_pnl = sum(t.dollar_pnl for t in oos_base.trades)
    is_cand_pnl  = sum(t.dollar_pnl for t in is_cand.trades)
    oos_cand_pnl = sum(t.dollar_pnl for t in oos_cand.trades)

    is_delta  = is_cand_pnl  - is_base_pnl
    oos_delta = oos_cand_pnl - oos_base_pnl

    print(f"\n{'='*72}")
    print("ENGINE SWEEP: block_level_rejection=True")
    print(f"{'='*72}")
    print(f"  IS:  base n={n_is_base:4d} pnl={is_base_pnl:+,.0f}  "
          f"cand n={n_is_cand:4d} pnl={is_cand_pnl:+,.0f}  delta={is_delta:+,.0f}")
    print(f"  OOS: base n={n_oos_base:4d} pnl={oos_base_pnl:+,.0f}  "
          f"cand n={n_oos_cand:4d} pnl={oos_cand_pnl:+,.0f}  delta={oos_delta:+,.0f}")

    if is_delta != 0 and n_is_base > 0 and n_oos_base > 0:
        wf = (oos_delta / n_oos_base) / (is_delta / n_is_base)
        print(f"  WF_norm = {wf:.3f}  ({'PASS' if wf >= 0.70 and oos_delta > 0 else 'FAIL'})")
    else:
        print(f"  WF_norm = N/A (IS_delta={is_delta})")

    # Anchor check
    print(f"\n  J anchor check:")
    anchor_ok = True
    for j_day in sorted(J_WINNERS):
        base_pnl = pnl_window(is_base.trades, j_day, j_day)
        cand_pnl = pnl_window(is_cand.trades, j_day, j_day)
        delta = cand_pnl - base_pnl
        status = "OK" if delta >= 0 else "HURT"
        if delta < 0:
            anchor_ok = False
        print(f"    {j_day}  base={base_pnl:+,.0f}  cand={cand_pnl:+,.0f}  delta={delta:+,.0f}  {status}")

    # IS Sub-windows
    print(f"\n  IS Sub-window stability:")
    n_hurt = 0
    for name, sw_s, sw_e in IS_SUB_WINDOWS:
        base_pnl = pnl_window(is_base.trades, sw_s, sw_e)
        cand_pnl = pnl_window(is_cand.trades, sw_s, sw_e)
        delta = cand_pnl - base_pnl
        status = "HURT" if delta < -200 else "OK"
        if status == "HURT":
            n_hurt += 1
        print(f"    {name}  base={base_pnl:+,.0f}  cand={cand_pnl:+,.0f}  delta={delta:+,.0f}  {status}")

    # OOS rolling
    print(f"\n  OOS Rolling windows (delta>=0 = PASS):")
    n_pass = 0
    for name, w_s, w_e in OOS_ROLLING:
        base_pnl = pnl_window(oos_base.trades, w_s, w_e)
        cand_pnl = pnl_window(oos_cand.trades, w_s, w_e)
        delta = cand_pnl - base_pnl
        status = "PASS" if delta >= 0 else "FAIL"
        if status == "PASS":
            n_pass += 1
        print(f"    {name}  base={base_pnl:+,.0f}  cand={cand_pnl:+,.0f}  delta={delta:+,.0f}  {status}")

    oos_ok         = oos_delta > 0
    wf_val         = (oos_delta / n_oos_base) / (is_delta / n_is_base) if is_delta != 0 else 0
    wf_ok          = oos_ok and wf_val >= 0.70
    rolling_ok     = n_pass == len(OOS_ROLLING)  # all non-negative

    print(f"\n{'='*72}")
    print("FINAL VERDICT (engine-level, cascade effects included)")
    print(f"{'='*72}")
    print(f"  OOS positive:         {oos_ok}  ({oos_delta:+,.0f})")
    print(f"  WF >= 0.70:           {wf_ok}  ({wf_val:.3f})")
    print(f"  anchor_no_regression: {anchor_ok}")
    print(f"  sub_window_stable:    {n_hurt == 0}  ({n_hurt} HURT)")
    print(f"  OOS_rolling (all>=0): {rolling_ok}  ({n_pass}/{len(OOS_ROLLING)} non-neg)")

    all_pass = oos_ok and wf_ok and anchor_ok and n_hurt == 0 and rolling_ok
    print(f"\n  CANDIDATE STATUS: {'RATIFY' if all_pass else 'INVESTIGATE'}")
    if not all_pass:
        fails = []
        if not oos_ok: fails.append("OOS_negative")
        if not wf_ok: fails.append(f"WF_low({wf_val:.3f})")
        if not anchor_ok: fails.append("anchor_regression")
        if n_hurt > 0: fails.append(f"{n_hurt}_IS_HURT")
        if not rolling_ok: fails.append(f"rolling_{n_pass}/{len(OOS_ROLLING)}")
        print(f"  Failed: {', '.join(fails)}")

    print("\n[ANALYSIS COMPLETE]")


if __name__ == "__main__":
    main()

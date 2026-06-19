"""
A/B scorecard: vix_bull_max=18.0 (VIX_BULL_HARD_CAP lowered from 22.0 to 18.0).

Prior C14 batch-8 result (old baseline, 2-week OOS):
  IS_delta=+$1,253, OOS_delta=+$219, WF=2.846, anchor OK.
  Sub-window sweep was "running" but result never logged. C14 closed as "sole RATIFY=tighter stop."

This script re-validates with:
- Extended OOS: May 8 - Jun 16 (n=26 vs old n=12)
- Corrected baseline: includes block_level_rejection + block_elite_bull_vix15_17.5 + tighter_stop

Mechanism: blocks CALL (BULL) entries when VIX is in 18-22 zone.
Production default: vix_bull_max=22.0 (VIX_BULL_HARD_CAP).
"""
import sys
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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

IS_SUB_WINDOWS = [
    ("W1-2025H1", dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2-2025H2", dt.date(2025, 7, 1),  dt.date(2025, 12, 31)),
    ("W3-Q12026", dt.date(2026, 1, 1),  dt.date(2026, 3, 31)),
    ("W4-Apr26",  dt.date(2026, 4, 1),  dt.date(2026, 5,  7)),
]
J_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}

# Current production baseline (all deployed gates)
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
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
)

# Candidate: lower VIX BULL hard cap from 22.0 to 18.0
# vix_bull_max is a filter constant — must go through params_overrides
CAND_OVERRIDES = {"vix_bull_max": 18.0}


def get_entry_date(t):
    et = t.entry_time_et
    return et.date() if hasattr(et, "date") else dt.date.fromisoformat(str(et)[:10])


def pnl_window(trades, s, e):
    return sum(t.dollar_pnl for t in trades if s <= get_entry_date(t) <= e)


def pnl_on_date(trades, d):
    return sum(t.dollar_pnl for t in trades if get_entry_date(t) == d)


def main():
    print("Loading extended data (Jan 2025 - Jun 2026)...")
    spy = pd.read_csv(SPY_FILE)
    vix = pd.read_csv(VIX_FILE)

    print("Running IS BASE + CANDIDATE...")
    is_b = run_backtest(spy, vix, start_date=IS_START, end_date=IS_END, **BASE)
    is_c = run_backtest(spy, vix, start_date=IS_START, end_date=IS_END,
                        params_overrides=CAND_OVERRIDES, **BASE)

    print("Running OOS BASE + CANDIDATE...")
    oos_b = run_backtest(spy, vix, start_date=OOS_START, end_date=OOS_END, **BASE)
    oos_c = run_backtest(spy, vix, start_date=OOS_START, end_date=OOS_END,
                         params_overrides=CAND_OVERRIDES, **BASE)

    is_bp  = sum(t.dollar_pnl for t in is_b.trades)
    is_cp  = sum(t.dollar_pnl for t in is_c.trades)
    oos_bp = sum(t.dollar_pnl for t in oos_b.trades)
    oos_cp = sum(t.dollar_pnl for t in oos_c.trades)

    n_is_b  = len(is_b.trades)
    n_oos_b = len(oos_b.trades)

    is_delta  = is_cp - is_bp
    oos_delta = oos_cp - oos_bp

    print(f"\n{'='*72}")
    print("vix_bull_max=18.0 — A/B Scorecard (extended OOS, corrected baseline)")
    print(f"{'='*72}")
    print(f"  Gate: lower VIX BULL hard cap from 22.0 to 18.0 (blocks BULL when VIX 18-22)")
    print(f"  Baseline: block_level_rejection + block_elite_bull_vix15_17.5 + tighter_stop")
    print(f"  IS:  base n={n_is_b} pnl={is_bp:+,.0f}  cand n={len(is_c.trades)} pnl={is_cp:+,.0f}  delta={is_delta:+,.0f}")
    print(f"  OOS: base n={n_oos_b} pnl={oos_bp:+,.0f}  cand n={len(oos_c.trades)} pnl={oos_cp:+,.0f}  delta={oos_delta:+,.0f}")

    n_is_blocked  = n_is_b - len(is_c.trades)
    n_oos_blocked = n_oos_b - len(oos_c.trades)
    print(f"  Blocks: IS n={n_is_blocked}, OOS n={n_oos_blocked}")

    if is_delta != 0 and n_is_b > 0 and n_oos_b > 0:
        wf = (oos_delta / n_oos_b) / (is_delta / n_is_b)
        wf_ok = wf >= 0.70 and oos_delta > 0
        print(f"\n  WF_norm = {wf:.3f}  ({'PASS' if wf_ok else 'FAIL'})")
    else:
        wf, wf_ok = 0.0, False
        print(f"\n  WF_norm = N/A (IS delta=0)")

    # IS sub-window breakdown
    print(f"\n  IS sub-windows:")
    hurt = 0
    for name, s, e in IS_SUB_WINDOWS:
        bp = pnl_window(is_b.trades, s, e)
        cp = pnl_window(is_c.trades, s, e)
        d  = cp - bp
        flag = "HURT" if d < -50 else ("HELP" if d > 50 else "FLAT")
        if flag == "HURT": hurt += 1
        print(f"    {name:<14s}  base={bp:+8,.0f}  cand={cp:+8,.0f}  delta={d:+7,.0f}  {flag}")

    # J anchor days
    print(f"\n  J anchor winners (4/29, 5/01, 5/04):")
    anchor_hurt = False
    for d in sorted(J_WINNERS):
        bp = pnl_on_date(is_b.trades, d)
        cp = pnl_on_date(is_c.trades, d)
        delta = cp - bp
        if delta < -50: anchor_hurt = True
        print(f"    {d}  base={bp:+8,.0f}  cand={cp:+8,.0f}  delta={delta:+7,.0f}  {'HURT' if delta < -50 else 'OK'}")

    # OOS trade detail
    oos_blocked = [d for d in oos_c.decisions
                   if d.get("action", "").startswith("SKIP") and d not in oos_b.decisions]
    # Show OOS diff
    oos_base_dates = {str(t.entry_time_et)[:10]: t.dollar_pnl for t in oos_b.trades}
    oos_cand_dates = {str(t.entry_time_et)[:10]: t.dollar_pnl for t in oos_c.trades}
    missing_in_cand = [(k, v) for k, v in sorted(oos_base_dates.items()) if k not in oos_cand_dates]
    if missing_in_cand:
        print(f"\n  OOS trades REMOVED by gate:")
        for date_str, pnl in missing_in_cand:
            print(f"    {date_str}  pnl={pnl:+,.0f}")

    # Verdict
    print(f"\n{'='*72}")
    print("RATIFICATION VERDICT:")
    oos_pos = oos_delta > 0
    sw_ok   = hurt <= 1
    anch_ok = not anchor_hurt

    print(f"  OOS positive:         {'YES' if oos_pos else 'NO'}  (delta={oos_delta:+,.0f})")
    print(f"  WF >= 0.70:           {'YES' if wf_ok else 'NO'}  (wf={wf:.3f})")
    print(f"  Sub-windows stable:   {'YES' if sw_ok else 'NO'}  ({hurt}/4 hurt)")
    print(f"  Anchor no-regression: {'YES' if anch_ok else 'NO'}")

    if oos_pos and wf_ok and sw_ok and anch_ok:
        print("\n  >>> AUTO-RATIFY: all hard gates passed.")
    elif oos_pos and sw_ok and anch_ok and not wf_ok:
        print(f"\n  >>> NEAR-PASS: OOS positive + sub-windows stable + anchor OK. WF={wf:.3f} fails 0.70.")
        if n_oos_blocked <= 5:
            print("  >>> n_oos_blocked small — per-trade WF analysis may clarify.")
    else:
        print(f"\n  >>> HOLD: gates failed (OOS={oos_pos}, WF={wf_ok}, SW={sw_ok}, anch={anch_ok})")
    print('='*72)


if __name__ == "__main__":
    main()

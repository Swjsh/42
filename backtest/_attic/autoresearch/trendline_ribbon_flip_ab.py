"""
A/B scorecard: TRENDLINE_RIBBON_FLIP_REQUIRED gate.

Hypothesis: Pure trendline_rejection without ribbon_flip is a loser (IS n=58, WR=27.6%, avg=-$34).
            ribbon_flip+trendline_rejection is a winner (IS n=6, WR=50%, avg=+$312).
Gate: block TRENDLINE entries where neither ribbon_flip_bearish nor ribbon_flip_bullish fired.

Required for ratification:
- OOS positive
- WF_norm >= 0.70
- Sub-window stable (0/4 HURT)
- Anchor no-regression (4/29, 5/01, 5/04)
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

IS_SUB_WINDOWS = [
    ("W1-2025H1", dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2-2025H2", dt.date(2025, 7, 1),  dt.date(2025, 12, 31)),
    ("W3-Q12026", dt.date(2026, 1, 1),  dt.date(2026, 3, 31)),
    ("W4-Apr26",  dt.date(2026, 4, 1),  dt.date(2026, 5,  7)),
]
J_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}
J_LOSERS  = {dt.date(2026, 5, 5), dt.date(2026, 5, 6), dt.date(2026, 5, 7)}

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
CAND = dict(**BASE, trendline_requires_ribbon_flip=True)


def get_entry_date(t):
    et = t.entry_time_et
    return et.date() if hasattr(et, "date") else dt.date.fromisoformat(str(et)[:10])


def pnl_on_date(trades, d):
    return sum(t.dollar_pnl for t in trades if get_entry_date(t) == d)


def pnl_window(trades, s, e):
    return sum(t.dollar_pnl for t in trades if s <= get_entry_date(t) <= e)


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


def main():
    print("Loading data...")
    spy = pd.read_csv(SPY_FILE)
    vix = pd.read_csv(VIX_FILE)

    print("Running IS BASE + CANDIDATE...")
    is_b = run_backtest(spy, vix, start_date=IS_START, end_date=IS_END, **BASE)
    is_c = run_backtest(spy, vix, start_date=IS_START, end_date=IS_END, **CAND)

    print("Running OOS BASE + CANDIDATE...")
    oos_b = run_backtest(spy, vix, start_date=OOS_START, end_date=OOS_END, **BASE)
    oos_c = run_backtest(spy, vix, start_date=OOS_START, end_date=OOS_END, **CAND)

    is_bp  = sum(t.dollar_pnl for t in is_b.trades)
    is_cp  = sum(t.dollar_pnl for t in is_c.trades)
    oos_bp = sum(t.dollar_pnl for t in oos_b.trades)
    oos_cp = sum(t.dollar_pnl for t in oos_c.trades)

    is_delta  = is_cp  - is_bp
    oos_delta = oos_cp - oos_bp
    n_is_b    = len(is_b.trades)
    n_oos_b   = len(oos_b.trades)

    print(f"\n{'='*72}")
    print("TRENDLINE_RIBBON_FLIP_REQUIRED — A/B Scorecard")
    print(f"{'='*72}")
    print(f"  IS:  base n={n_is_b:4d} pnl={is_bp:+8,.0f}  "
          f"cand n={len(is_c.trades):4d} pnl={is_cp:+8,.0f}  delta={is_delta:+,.0f}")
    print(f"  OOS: base n={n_oos_b:4d} pnl={oos_bp:+8,.0f}  "
          f"cand n={len(oos_c.trades):4d} pnl={oos_cp:+8,.0f}  delta={oos_delta:+,.0f}")

    if is_delta != 0 and n_is_b > 0 and n_oos_b > 0:
        wf = (oos_delta / n_oos_b) / (is_delta / n_is_b)
        status = "PASS" if wf >= 0.70 and oos_delta > 0 else "FAIL"
        print(f"\n  WF_norm = {wf:.3f}  ({status})")
    else:
        print(f"\n  WF_norm = N/A (IS_delta={is_delta})")
        status = "INERT"

    # Sub-window stability
    print(f"\n  IS sub-windows:")
    hurt = 0
    for name, s, e in IS_SUB_WINDOWS:
        bp = pnl_window(is_b.trades, s, e)
        cp = pnl_window(is_c.trades, s, e)
        d  = cp - bp
        flag = "HURT" if d < -50 else ("HELP" if d > 50 else "FLAT")
        if flag == "HURT": hurt += 1
        print(f"    {name:<14s}  base={bp:+8,.0f}  cand={cp:+8,.0f}  delta={d:+7,.0f}  {flag}")
    print(f"  Sub-window hurt: {hurt}/4  ({'OK' if hurt == 0 else 'WARN'})")

    # J anchor days
    print(f"\n  J anchor winners (4/29, 5/01, 5/04):")
    anchor_hurt = False
    for d in sorted(J_WINNERS):
        bp = pnl_on_date(is_b.trades, d)
        cp = pnl_on_date(is_c.trades, d)
        delta = cp - bp
        if delta < -50: anchor_hurt = True
        print(f"    {d}  base={bp:+8,.0f}  cand={cp:+8,.0f}  delta={delta:+7,.0f}  {'HURT' if delta < -50 else 'OK'}")

    print(f"\n  J anchor losers (5/05-5/07):")
    for d in sorted(J_LOSERS):
        bp = pnl_on_date(oos_b.trades, d)
        cp = pnl_on_date(oos_c.trades, d)
        delta = cp - bp
        print(f"    {d}  base={bp:+8,.0f}  cand={cp:+8,.0f}  delta={delta:+7,.0f}")

    # What was removed / kept
    tl_base = [t for t in is_b.trades if get_quality(t) == "TRENDLINE"]
    tl_cand = [t for t in is_c.trades if get_quality(t) == "TRENDLINE"]
    print(f"\n  IS TRENDLINE trades: base={len(tl_base)}, cand={len(tl_cand)}")
    print(f"    base pnl={sum(t.dollar_pnl for t in tl_base):+,.0f}  "
          f"cand pnl={sum(t.dollar_pnl for t in tl_cand):+,.0f}")
    if tl_cand:
        wr = sum(1 for t in tl_cand if t.dollar_pnl > 0) / len(tl_cand)
        print(f"    cand WR={wr:.1%}  avg={sum(t.dollar_pnl for t in tl_cand)/len(tl_cand):+,.0f}/trade")

    # SKIP events in candidate OOS
    skips = [d for d in oos_c.decisions if d.get("action") == "SKIP_TRENDLINE_NO_RIBBON_FLIP"]
    print(f"\n  OOS SKIP_TRENDLINE_NO_RIBBON_FLIP events: n={len(skips)}")

    # Ratification verdict
    print(f"\n{'='*72}")
    print("RATIFICATION VERDICT:")
    oos_pos   = oos_delta > 0
    wf_ok     = status == "PASS"
    sw_ok     = hurt == 0
    anch_ok   = not anchor_hurt
    n_ok      = len(is_b.trades) >= 15

    print(f"  OOS positive:       {'YES' if oos_pos   else 'NO'}  (delta={oos_delta:+,.0f})")
    print(f"  WF >= 0.70:         {'YES' if wf_ok     else 'NO'}")
    print(f"  Sub-windows stable: {'YES' if sw_ok     else 'NO'}  ({hurt}/4 hurt)")
    print(f"  Anchor no-regression: {'YES' if anch_ok else 'NO'}")
    print(f"  evidence n >= 15:   {'YES' if n_ok      else 'NO'}  (IS_base n={n_is_b})")

    if oos_pos and wf_ok and sw_ok and anch_ok:
        print("\n  >>> AUTO-RATIFY: all hard gates passed. Ship to params.json.")
    else:
        print("\n  >>> HOLD: not all gates passed. Do not ratify.")
    print('='*72)


if __name__ == "__main__":
    main()

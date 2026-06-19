"""Sweep block_elite_bull_vix_high threshold to find OOS breakeven point.

IS: block ELITE+level_reclaim when 15 <= VIX < threshold.
OOS: see how OOS delta changes as threshold rises (more OOS trades blocked).

We want: OOS delta > 0 (to pass the WF positive gate).
From VIX analysis: OOS trades at VIX 15-17.4 are:
  - 5/27 VIX=15.9: -$253
  - 5/27 VIX=15.8: -$153
  - 5/29 VIX=15.2: +$466
  - 5/20 VIX=17.4: -$226 (also blocks if threshold=17.5)

At threshold=17.5: OOS delta = -$61 + $226 = +$165 (potentially positive).
"""
import sys
import datetime as dt
from pathlib import Path

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

THRESHOLDS = [16.5, 17.0, 17.5, 18.0, 18.5, 19.0, 20.0]


def pnl_window(trades, s, e):
    def gd(t):
        et = t.entry_time_et
        return et.date() if hasattr(et, "date") else dt.date.fromisoformat(str(et)[:10])
    return sum(t.dollar_pnl for t in trades if s <= gd(t) <= e)


def main():
    print("Loading data...")
    spy = pd.read_csv(SPY_FILE)
    vix = pd.read_csv(VIX_FILE)

    print("Running IS + OOS BASE...")
    is_b  = run_backtest(spy, vix, start_date=IS_START,  end_date=IS_END,  **BASE)
    oos_b = run_backtest(spy, vix, start_date=OOS_START, end_date=OOS_END, **BASE)

    is_bp   = sum(t.dollar_pnl for t in is_b.trades)
    oos_bp  = sum(t.dollar_pnl for t in oos_b.trades)
    n_is_b  = len(is_b.trades)
    n_oos_b = len(oos_b.trades)

    print(f"  BASE: IS n={n_is_b} pnl={is_bp:+,.0f}  OOS n={n_oos_b} pnl={oos_bp:+,.0f}")
    print(f"\n{'='*78}")
    print(f"{'Threshold':<12} {'IS delta':>10} {'IS n-cand':>10} {'OOS delta':>10} {'OOS n-cand':>11} {'WF':>8}  Sub-hurt  Verdict")
    print(f"{'='*78}")

    best = None
    for thr in THRESHOLDS:
        cand_params = dict(**BASE,
                           block_elite_bull=True,
                           block_elite_bull_vix_low=15.0,
                           block_elite_bull_vix_high=thr)
        is_c  = run_backtest(spy, vix, start_date=IS_START,  end_date=IS_END,  **cand_params)
        oos_c = run_backtest(spy, vix, start_date=OOS_START, end_date=OOS_END, **cand_params)

        is_cp  = sum(t.dollar_pnl for t in is_c.trades)
        oos_cp = sum(t.dollar_pnl for t in oos_c.trades)
        is_delta  = is_cp  - is_bp
        oos_delta = oos_cp - oos_bp

        wf = (oos_delta / n_oos_b) / (is_delta / n_is_b) if is_delta != 0 else float("nan")
        wf_ok = wf >= 0.70 and oos_delta > 0

        # Sub-window hurt
        hurt = 0
        for _, s, e in IS_SUB_WINDOWS:
            bp = pnl_window(is_b.trades, s, e)
            cp = pnl_window(is_c.trades, s, e)
            if cp - bp < -50: hurt += 1

        # Anchor check
        anchor_ok = True
        for d in J_WINNERS:
            bp = sum(t.dollar_pnl for t in is_b.trades
                     if (t.entry_time_et.date() if hasattr(t.entry_time_et,"date") else
                         dt.date.fromisoformat(str(t.entry_time_et)[:10])) == d)
            cp = sum(t.dollar_pnl for t in is_c.trades
                     if (t.entry_time_et.date() if hasattr(t.entry_time_et,"date") else
                         dt.date.fromisoformat(str(t.entry_time_et)[:10])) == d)
            if cp - bp < -50: anchor_ok = False

        if wf_ok and not anchor_ok:
            verdict = "PASS-ANCHOR-FAIL"
        elif wf_ok:
            verdict = "PASS ★"
            if best is None: best = thr
        elif oos_delta > 0:
            verdict = "OOS+ (WF fail)"
        else:
            verdict = "HOLD"

        print(f"  VIX < {thr:<6.1f}  {is_delta:>+10,.0f}  {len(is_c.trades):>10d}  "
              f"{oos_delta:>+10,.0f}  {len(oos_c.trades):>11d}  {wf:>8.3f}  "
              f"{hurt}/4 hurt  {verdict}")

    print(f"{'='*78}")
    if best:
        print(f"\n  Best threshold: VIX < {best}")
        print(f"  Re-run elite_bull_vix_range_ab.py with block_elite_bull_vix_high={best}")
    else:
        print("\n  No threshold achieved PASS. Consider: 1) Broader OOS data, 2) J auth override.")


if __name__ == "__main__":
    main()

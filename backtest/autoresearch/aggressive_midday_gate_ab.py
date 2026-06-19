"""
Aggressive account: midday_trendline_gate A/B.

SAFE has midday_trendline_gate=True (blocks TL-only 11:30-14:00 ET).
Aggressive has no midday gate in production.

Q: Would adding midday_trendline_gate to Aggressive improve its IS/OOS P&L?

Aggressive baseline: bear_thresh=15.0, bull_cap=30.0, no midday gate.
This script tests both options and reports IS/OOS/sub-window.
"""
import datetime as dt
import sys
from pathlib import Path

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

# Aggressive baseline (no midday gate)
AGG_NO_MIDDAY = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=False,
    premium_stop_pct_bear=-0.10,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=5.0,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.50,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    params_overrides={"vix_bull_max": 30.0, "vix_bear_threshold": 15.0},
)

# Aggressive with midday gate
AGG_WITH_MIDDAY = dict(AGG_NO_MIDDAY)
AGG_WITH_MIDDAY["midday_trendline_gate"] = True


def run_ab():
    print("Loading data...")
    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy)} rows, VIX {len(vix)} rows")

    is_base = run_backtest(spy, vix, start_date=IS_S, end_date=IS_E, **AGG_NO_MIDDAY)
    is_cand = run_backtest(spy, vix, start_date=IS_S, end_date=IS_E, **AGG_WITH_MIDDAY)
    oos_base = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **AGG_NO_MIDDAY)
    oos_cand = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **AGG_WITH_MIDDAY)

    is_base_pnl = sum(t.dollar_pnl for t in is_base.trades)
    is_cand_pnl = sum(t.dollar_pnl for t in is_cand.trades)
    oos_base_pnl = sum(t.dollar_pnl for t in oos_base.trades)
    oos_cand_pnl = sum(t.dollar_pnl for t in oos_cand.trades)

    is_delta = is_cand_pnl - is_base_pnl
    oos_delta = oos_cand_pnl - oos_base_pnl
    n_is = len(is_base.trades)
    n_oos = len(oos_base.trades)
    n_is_removed = n_is - len(is_cand.trades)
    n_oos_removed = n_oos - len(oos_cand.trades)

    print(f"\n=== AGGRESSIVE MIDDAY_TRENDLINE_GATE A/B ===")
    print(f"  BASE (no gate):  IS n={n_is} pnl={is_base_pnl:+.0f} | OOS n={n_oos} pnl={oos_base_pnl:+.0f}")
    print(f"  CAND (with gate): IS n={len(is_cand.trades)} pnl={is_cand_pnl:+.0f} | OOS n={len(oos_cand.trades)} pnl={oos_cand_pnl:+.0f}")
    print(f"  IS:  delta={is_delta:+.0f} (removed={n_is_removed})")
    print(f"  OOS: delta={oos_delta:+.0f} (removed={n_oos_removed})")

    wf = None
    if is_delta != 0 and n_is_removed > 0 and n_oos_removed > 0:
        wf = (oos_delta / n_oos) / (is_delta / n_is)
        print(f"  WF_norm={wf:.3f} (gate=0.70)")
    elif n_oos_removed == 0:
        print(f"  WARNING: n_oos_removed=0 (OOS unaffected)")

    windows = [
        ("W1_2025H1", dt.date(2025, 1, 2), dt.date(2025, 6, 30)),
        ("W2_2025H2", dt.date(2025, 7, 1), dt.date(2025, 12, 31)),
        ("W3_Q12026", dt.date(2026, 1, 2), dt.date(2026, 3, 31)),
        ("W4_Apr26",  dt.date(2026, 4, 1), dt.date(2026, 5, 7)),
    ]
    hurt = 0
    print(f"\n  IS sub-windows:")
    for name, ws, we in windows:
        sw_base = run_backtest(spy, vix, start_date=ws, end_date=we, **AGG_NO_MIDDAY)
        sw_cand = run_backtest(spy, vix, start_date=ws, end_date=we, **AGG_WITH_MIDDAY)
        sw_delta = sum(t.dollar_pnl for t in sw_cand.trades) - sum(t.dollar_pnl for t in sw_base.trades)
        sw_removed = len(sw_base.trades) - len(sw_cand.trades)
        verdict = "HELP" if sw_delta > 0 else "FLAT" if sw_delta == 0 else "HURT"
        if verdict == "HURT":
            hurt += 1
        print(f"    {name}: removed={sw_removed} delta={sw_delta:+.0f} -> {verdict}")
    print(f"  SW hurt: {hurt}/4 (gate: <=1)")

    oos_pos = oos_delta > 0
    sw_ok = hurt <= 1
    print(f"\n  VERDICT: IS_positive={is_delta>0} OOS_positive={oos_pos} SW_ok={sw_ok}")
    if is_delta > 0 and oos_pos and sw_ok:
        print(f"  -> CANDIDATE: add midday_trendline_gate to Aggressive")
    elif is_delta > 0 and not oos_pos:
        print(f"  -> REJECT: IS improves but OOS degrades (C22 regime flip)")
    else:
        print(f"  -> REJECT or INCONCLUSIVE")


if __name__ == "__main__":
    run_ab()

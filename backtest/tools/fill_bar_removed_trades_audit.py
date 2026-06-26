"""Audit: what does require_bearish_fill_bar REMOVE under the CURRENT engine?

Run gate OFF vs ON, find the bear trades present in OFF but absent in ON (the gate
removed them), and report their P&L distribution under the managed ITM exit. If the
removed set is net-positive, the gate is now suppressing winners (UNBLOCK signal).
If net-negative, the gate still earns its keep (KEEP signal). Per-trade economics +
sign-stability decide it, not WR (WR is a theta trap — C4/L166).
"""
from __future__ import annotations
import sys, datetime as dt, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR = ROOT / "backtest" / "data"
spy_df = pd.read_csv(DATA_DIR / "spy_5m_2025-01-01_2026-06-18.csv")
vix_df = pd.read_csv(DATA_DIR / "vix_5m_2026-05-08_2026-06-16.csv") if False else pd.read_csv(DATA_DIR / "vix_5m_2025-01-01_2026-06-16.csv")

KW = dict(
    use_real_fills=True, strike_offset=-2, midday_trendline_gate=True,
    premium_stop_pct_bear=-0.07, premium_stop_pct_bull=-0.05,
    tp1_qty_fraction=0.667, tp1_premium_pct=0.75, runner_target_premium_pct=5.0,
    time_stop_minutes_before_close=20, per_trade_risk_cap_pct=0.50,
    block_level_rejection=True, block_elite_bull=True,
    block_elite_bull_vix_low=15.0, block_elite_bull_vix_high=17.5,
    profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.05,
    profit_lock_mode="trailing", profit_lock_trail_pct=0.15,
)
OVR = {"vix_bear_threshold": 15.0, "vix_bull_max": 30.0}


def key(t):
    et = t.entry_time_et
    et = et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et
    return (et, t.side, round(getattr(t, "strike", 0) or 0, 1))


def run(start, end, gate):
    kw = dict(KW); kw["require_bearish_fill_bar"] = gate
    return run_backtest(spy_df, vix_df, start_date=start, end_date=end,
                        params_overrides=dict(OVR), **kw).trades


for lbl, s, e in [("IS", dt.date(2025,1,2), dt.date(2026,5,7)),
                  ("OOS", dt.date(2026,5,8), dt.date(2026,6,18))]:
    off = run(s, e, False)
    on = run(s, e, True)
    on_keys = {key(t) for t in on}
    removed = [t for t in off if key(t) not in on_keys and t.side == "P"]
    rp = [t.dollar_pnl for t in removed]
    if rp:
        wins = [p for p in rp if p > 0]
        losses = [p for p in rp if p <= 0]
        print(f"\n=== {lbl}: gate removed {len(removed)} bear trades ===")
        print(f"  removed total P&L: {sum(rp):+,.0f}  avg/trade: {sum(rp)/len(rp):+.0f}")
        print(f"  removed wins:   n={len(wins):3} total={sum(wins):+,.0f}")
        print(f"  removed losses: n={len(losses):3} total={sum(losses):+,.0f}")
        print(f"  --> gate removing this set {'COSTS money (suppresses winners)' if sum(rp) > 0 else 'SAVES money (kills losers)'}")
    else:
        print(f"\n=== {lbl}: gate removed 0 bear trades ===")

"""Compare real_fills vs BS model P&L to identify which matches CONTEXT-92."""
import sys, datetime as dt
sys.path.insert(0, "backtest")
import pandas as pd
from lib.orchestrator import run_backtest

spy = pd.read_csv("backtest/data/spy_5m_2025-01-01_2026-06-16.csv")
vix = pd.read_csv("backtest/data/vix_5m_2025-01-01_2026-06-16.csv")

# Common gates — what should match IS n=89 total=+24512 from CONTEXT-92
COMMON = dict(
    no_trade_before=dt.time(9,35), no_trade_window=None,
    midday_trendline_gate=True, premium_stop_pct_bear=-0.10,
    tp1_premium_pct=0.50, tp1_qty_fraction=0.667, runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20, per_trade_risk_cap_pct=0.30,
    block_level_rejection=True, block_elite_bull=True,
    block_elite_bull_vix_low=15.0, block_elite_bull_vix_high=17.5,
    entry_bar_body_pct_min=0.20, vix_bear_hard_cap=23.0,
    min_triggers_bear=1, min_triggers_bull=2,
    profit_lock_threshold_pct=0.05, profit_lock_mode="trailing", profit_lock_trail_pct=0.20,
)

IS_S = dt.date(2025, 1, 2)
IS_E = dt.date(2026, 5, 7)

print("Target from CONTEXT-92: IS n=89 total=+24512")
print("=" * 70)

for label, extra in [
    ("real_fills=True", {"use_real_fills": True}),
    ("real_fills=False (BS)", {"use_real_fills": False}),
    ("real_fills=True + no block_elite_bull", {"use_real_fills": True, "block_elite_bull": False}),
    ("real_fills=True + no block_level_reject", {"use_real_fills": True, "block_level_rejection": False}),
]:
    kw = dict(COMMON, **extra)
    r = run_backtest(spy, vix, start_date=IS_S, end_date=IS_E, **kw)
    n = len(r.trades)
    tot = sum(t.dollar_pnl for t in r.trades)
    bears = sum(1 for t in r.trades if t.side == "P")
    bulls = sum(1 for t in r.trades if t.side == "C")
    match = "*** MATCH n ***" if n == 89 else ("close-n" if abs(n-89) <= 3 else "")
    match2 = "*** MATCH PNL ***" if abs(tot-24512) < 1000 else ""
    print(f"  {label:50s} n={n:3d}({bears}B+{bulls}C) total={tot:+.0f}  {match} {match2}")

"""Determine the correct IS/OOS split that matches CONTEXT-92 IS n=89 total=+24512."""
import sys, datetime as dt
sys.path.insert(0, "backtest")
import pandas as pd
from lib.orchestrator import run_backtest

spy = pd.read_csv("backtest/data/spy_5m_2025-01-01_2026-06-16.csv")
vix = pd.read_csv("backtest/data/vix_5m_2025-01-01_2026-06-16.csv")

KW = dict(
    use_real_fills=True, no_trade_before=dt.time(9,35), no_trade_window=None,
    midday_trendline_gate=True, premium_stop_pct_bear=-0.10,
    tp1_premium_pct=0.50, tp1_qty_fraction=0.667, runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20, per_trade_risk_cap_pct=0.30,
    block_level_rejection=True, block_elite_bull=True,
    block_elite_bull_vix_low=15.0, block_elite_bull_vix_high=17.5,
    entry_bar_body_pct_min=0.20, vix_bear_hard_cap=23.0,
    min_triggers_bear=1, min_triggers_bull=2,
    profit_lock_threshold_pct=0.05, profit_lock_mode="trailing", profit_lock_trail_pct=0.20,
)

splits = [
    ("IS=2025-01-02 to 2026-02-26  OOS=2026-02-27 to 2026-05-22",
     dt.date(2025,1,2), dt.date(2026,2,26), dt.date(2026,2,27), dt.date(2026,5,22)),
    ("IS=2025-01-02 to 2026-05-07  OOS=2026-05-08 to 2026-05-22",
     dt.date(2025,1,2), dt.date(2026,5,7), dt.date(2026,5,8), dt.date(2026,5,22)),
    ("IS=2025-01-02 to 2026-04-30  OOS=2026-05-01 to 2026-05-22",
     dt.date(2025,1,2), dt.date(2026,4,30), dt.date(2026,5,1), dt.date(2026,5,22)),
    ("IS=2025-01-02 to 2026-05-22  (IS only)",
     dt.date(2025,1,2), dt.date(2026,5,22), None, None),
]

print("Searching for IS n=89 total=+24512 (from CONTEXT-92 scorecard)")
print("=" * 90)
for label, is_s, is_e, oos_s, oos_e in splits:
    r = run_backtest(spy, vix, start_date=is_s, end_date=is_e, **KW)
    n_is = len(r.trades)
    tot_is = sum(t.dollar_pnl for t in r.trades)
    bears_is = sum(1 for t in r.trades if t.side == "P")
    bulls_is = sum(1 for t in r.trades if t.side == "C")
    if oos_s:
        ro = run_backtest(spy, vix, start_date=oos_s, end_date=oos_e, **KW)
        n_oos = len(ro.trades)
        tot_oos = sum(t.dollar_pnl for t in ro.trades)
    else:
        n_oos = tot_oos = 0
    match = "*** MATCH ***" if n_is == 89 else ("close" if abs(n_is-89) <= 3 else "")
    print(f"  {label}")
    print(f"    IS: n={n_is}({bears_is}B+{bulls_is}C) total={tot_is:+.0f}  OOS: n={n_oos} total={tot_oos:+.0f}  {match}")

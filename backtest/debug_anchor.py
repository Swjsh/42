import sys, datetime as dt
sys.path.insert(0, "backtest")
import pandas as pd
from lib.orchestrator import run_backtest

spy = pd.read_csv("backtest/data/spy_5m_2025-01-01_2026-06-16.csv")
vix = pd.read_csv("backtest/data/vix_5m_2025-01-01_2026-06-16.csv")

r = run_backtest(spy, vix,
    start_date=dt.date(2026, 4, 27), end_date=dt.date(2026, 5, 6),
    use_real_fills=True, no_trade_before=dt.time(9,35), no_trade_window=None,
    midday_trendline_gate=True, premium_stop_pct_bear=-0.10,
    tp1_premium_pct=0.50, tp1_qty_fraction=0.667, runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20, per_trade_risk_cap_pct=0.30,
    block_level_rejection=True, block_elite_bull=True,
    block_elite_bull_vix_low=15.0, block_elite_bull_vix_high=17.5,
    entry_bar_body_pct_min=0.20, vix_bear_hard_cap=23.0,
    min_triggers_bear=1, min_triggers_bull=2,
    profit_lock_threshold_pct=0.05, profit_lock_mode="trailing", profit_lock_trail_pct=0.20,
    params_overrides={"vix_bull_max": 18.0})
print("Trades in anchor window:", len(r.trades))
for t in r.trades:
    print("  {} {} pnl={:+.0f} entry=${:.2f}".format(
        t.entry_time_et.date(), t.side, t.dollar_pnl, t.entry_premium))

print()
# Also run full OOS with same config
r2 = run_backtest(spy, vix,
    start_date=dt.date(2026, 2, 27), end_date=dt.date(2026, 5, 22),
    use_real_fills=True, no_trade_before=dt.time(9,35), no_trade_window=None,
    midday_trendline_gate=True, premium_stop_pct_bear=-0.10,
    tp1_premium_pct=0.50, tp1_qty_fraction=0.667, runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20, per_trade_risk_cap_pct=0.30,
    block_level_rejection=True, block_elite_bull=True,
    block_elite_bull_vix_low=15.0, block_elite_bull_vix_high=17.5,
    entry_bar_body_pct_min=0.20, vix_bear_hard_cap=23.0,
    min_triggers_bear=1, min_triggers_bull=2,
    profit_lock_threshold_pct=0.05, profit_lock_mode="trailing", profit_lock_trail_pct=0.20,
    params_overrides={"vix_bull_max": 18.0})
print("Full OOS trades:", len(r2.trades))
total = sum(t.dollar_pnl for t in r2.trades)
wins = sum(1 for t in r2.trades if t.dollar_pnl > 0)
print("OOS total={:+.0f}  WR={:.1%}".format(total, wins/len(r2.trades) if r2.trades else 0))
anchor_dates = {dt.date(2026,4,29), dt.date(2026,5,1), dt.date(2026,5,4)}
for t in r2.trades:
    d = t.entry_time_et.date()
    if d in anchor_dates:
        print("  ANCHOR {} {} pnl={:+.0f}".format(d, t.side, t.dollar_pnl))

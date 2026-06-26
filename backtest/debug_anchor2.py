"""Find what blocks anchor trades on 2026-04-29, 2026-05-01, 2026-05-04."""
import sys, datetime as dt
sys.path.insert(0, "backtest")
import pandas as pd
from lib.orchestrator import run_backtest

spy = pd.read_csv("backtest/data/spy_5m_2025-01-01_2026-06-16.csv")
vix = pd.read_csv("backtest/data/vix_5m_2025-01-01_2026-06-16.csv")
WINDOW = dict(start_date=dt.date(2026, 4, 27), end_date=dt.date(2026, 5, 6))
ANCHOR = {dt.date(2026,4,29), dt.date(2026,5,1), dt.date(2026,5,4)}

BASE = dict(
    use_real_fills=True, no_trade_before=dt.time(9,35), no_trade_window=None,
    midday_trendline_gate=True, premium_stop_pct_bear=-0.10,
    tp1_premium_pct=0.50, tp1_qty_fraction=0.667, runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20, per_trade_risk_cap_pct=0.30,
    min_triggers_bear=1, min_triggers_bull=2,
    profit_lock_threshold_pct=0.05, profit_lock_mode="trailing", profit_lock_trail_pct=0.20,
    params_overrides={"vix_bull_max": 18.0},
)


def run_check(label, extra=None):
    kw = dict(BASE)
    if extra:
        kw.update(extra)
    r = run_backtest(spy, vix, **WINDOW, **kw)
    anchor_trades = [t for t in r.trades if t.entry_time_et.date() in ANCHOR]
    print("  {:50s} total_trades={:3d}  anchor_trades={:3d}  anchor_pnl={:+.0f}".format(
        label, len(r.trades), len(anchor_trades),
        sum(t.dollar_pnl for t in anchor_trades)))


print("=== Anchor trade gate isolation (2026-04-27 to 2026-05-06) ===")
run_check("No extra gates", {})
run_check("+ block_level_rejection=True", {"block_level_rejection": True})
run_check("+ block_elite_bull=True(15-17.5)", {"block_level_rejection": True,
    "block_elite_bull": True, "block_elite_bull_vix_low": 15.0, "block_elite_bull_vix_high": 17.5})
run_check("+ entry_bar_body_pct_min=0.20", {"block_level_rejection": True,
    "block_elite_bull": True, "block_elite_bull_vix_low": 15.0, "block_elite_bull_vix_high": 17.5,
    "entry_bar_body_pct_min": 0.20})
run_check("+ vix_bear_hard_cap=23.0", {"block_level_rejection": True,
    "block_elite_bull": True, "block_elite_bull_vix_low": 15.0, "block_elite_bull_vix_high": 17.5,
    "entry_bar_body_pct_min": 0.20, "vix_bear_hard_cap": 23.0})
print()
print("Decisions log for 2026-04-29 (no gates):")
kw = dict(BASE)
r = run_backtest(spy, vix, **WINDOW, **kw)
for d in r.decisions:
    ts = d.get("timestamp_et", "")
    if hasattr(ts, "date") and ts.date() == dt.date(2026, 4, 29):
        print("  {:30s} passed={} blockers={} triggers={} action={}".format(
            str(ts)[:25], d.get("passed"),
            d.get("blockers", []), d.get("triggers_fired", []),
            d.get("action", "")))

"""
Sub-window P&L breakdown of the CORRECT baseline.

Shows which calendar periods within the IS window are profitable.
Identifies the regime conditions where BEARISH_REVERSAL has edge.

Run: python backtest/autoresearch/sweep_sub_windows.py
"""
import sys
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest"))

import pandas as pd
from lib.orchestrator import run_backtest

SPY = ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-05-22.csv"
VIX = ROOT / "backtest" / "data" / "vix_5m_2025-01-01_2026-05-22.csv"

spy = pd.read_csv(str(SPY))
vix = pd.read_csv(str(VIX))

CORRECT = dict(
    use_real_fills=True, no_trade_window=None, no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True, premium_stop_pct_bear=-0.20,
    premium_stop_pct_bull=-0.08, per_trade_risk_cap_pct=0.30,
    tp1_qty_fraction=0.667, runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
)


def run_window(label, start, end):
    r = run_backtest(spy, vix, start_date=start, end_date=end, **CORRECT)
    pnl = sum(t.dollar_pnl for t in r.trades if t.dollar_pnl is not None)
    wins = [t for t in r.trades if (t.dollar_pnl or 0) > 0]
    losses = [t for t in r.trades if (t.dollar_pnl or 0) < 0]
    wr = len(wins) / len(r.trades) if r.trades else 0
    avg_w = sum(t.dollar_pnl for t in wins) / len(wins) if wins else 0
    avg_l = sum(t.dollar_pnl for t in losses) / len(losses) if losses else 0
    return len(r.trades), pnl, wr, avg_w, avg_l


windows = [
    ("IS Full   2025-01 to 2026-04", dt.date(2025, 1, 1),  dt.date(2026, 4, 30)),
    ("IS Q1-25  2025-01 to 2025-03", dt.date(2025, 1, 1),  dt.date(2025, 3, 31)),
    ("IS Q2-25  2025-04 to 2025-06", dt.date(2025, 4, 1),  dt.date(2025, 6, 30)),
    ("IS Q3-25  2025-07 to 2025-09", dt.date(2025, 7, 1),  dt.date(2025, 9, 30)),
    ("IS Q4-25  2025-10 to 2025-12", dt.date(2025, 10, 1), dt.date(2025, 12, 31)),
    ("IS JanApr 2026-01 to 2026-04", dt.date(2026, 1, 1),  dt.date(2026, 4, 30)),
    ("OOS Full  2026-05-08 to 05-22", dt.date(2026, 5, 8),  dt.date(2026, 5, 22)),
    # Monthly breakdown for recent period
    ("Jan 2026",  dt.date(2026, 1, 1),  dt.date(2026, 1, 31)),
    ("Feb 2026",  dt.date(2026, 2, 1),  dt.date(2026, 2, 28)),
    ("Mar 2026",  dt.date(2026, 3, 1),  dt.date(2026, 3, 31)),
    ("Apr 2026",  dt.date(2026, 4, 1),  dt.date(2026, 4, 30)),
    # Tariff-shock month (IS partial)
    ("TariffShock 2026-04-07 to 04-30", dt.date(2026, 4, 7),  dt.date(2026, 4, 30)),
]

print("=" * 100)
print(f"  {'Window':<40} {'n':>5} {'P&L':>10} {'WR':>7} {'Avg_W':>8} {'Avg_L':>8} {'Verdict':>10}")
print("=" * 100)

for label, start, end in windows:
    n, pnl, wr, avg_w, avg_l = run_window(label, start, end)
    verdict = "POSITIVE" if pnl > 0 else "NEGATIVE"
    print(f"  {label:<40} {n:>5} {pnl:>10.2f} {wr:>7.1%} {avg_w:>8.2f} {avg_l:>8.2f} {verdict:>10}")

print("=" * 100)
print()
print("Note: VIX context matters. OOS window (May 8-22) was high-VIX tariff-shock period.")
print("Look for quarters where WR and avg_W both positive — those are the regime windows.")
print("Done.")

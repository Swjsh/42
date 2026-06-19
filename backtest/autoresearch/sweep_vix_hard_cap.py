"""
L114: VIX hard-cap sweep for BEAR entries.

Hypothesis: blocking BEAR entries when VIX > cap removes April 2026 Liberation Day
losses (VIX 40-52) while preserving OOS (May 2026 VIX 20-35) and Q3-25 recovery wins.

Sub-window analysis found:
  - Apr 2026: n=22, -$6,189 (Liberation Day tariff shock, VIX escalating to 52)
  - OOS May-26: n=17, +$4,747 (VIX declining from 35 to 20, post-shock recovery)
  - Q3-25: n=60, +$4,446 (BoJ carry-trade recovery, VIX declining from 65 to 20)

VIX_HARD_CAP_BEAR=999 = no cap = production default (backward compatible).
Lower values block entries when VIX > threshold.

Run: python backtest/autoresearch/sweep_vix_hard_cap.py
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

IS_START  = dt.date(2025, 1, 1)
IS_END    = dt.date(2026, 4, 30)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 5, 22)

CORRECT = dict(
    use_real_fills=True, no_trade_window=None, no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True, premium_stop_pct_bear=-0.20,
    premium_stop_pct_bull=-0.08, per_trade_risk_cap_pct=0.30,
    tp1_qty_fraction=0.667, runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
)


def run_pair(label, cap):
    """cap=vix_hard_cap_bear float. Passed via params_overrides (module-level constant path)."""
    overrides = {"vix_hard_cap_bear": cap}
    ri = run_backtest(spy, vix, start_date=IS_START,  end_date=IS_END,  params_overrides=overrides, **CORRECT)
    ro = run_backtest(spy, vix, start_date=OOS_START, end_date=OOS_END, params_overrides=overrides, **CORRECT)
    ip = sum(t.dollar_pnl for t in ri.trades if t.dollar_pnl is not None)
    op = sum(t.dollar_pnl for t in ro.trades if t.dollar_pnl is not None)
    return len(ri.trades), ip, len(ro.trades), op


print("Loading BASELINE...")
b_is_n, b_is_pnl, b_oos_n, b_oos_pnl = run_pair("baseline", cap=999.0)
print(f"BASELINE: IS n={b_is_n}, pnl=${b_is_pnl:.2f} | OOS n={b_oos_n}, pnl=${b_oos_pnl:.2f}")
print()

print("=== VIX_HARD_CAP_BEAR SWEEP (IS+OOS) ===")
print(f"  {'cap':<8} {'IS_n':>6} {'IS_pnl':>10} {'IS_d':>9} {'OOS_n':>6} {'OOS_pnl':>10} {'OOS_d':>9} {'WF':>7} {'verdict':>12}")

# Cap candidates: 999=off, 50, 45, 40, 35, 30
for cap in [999.0, 50.0, 45.0, 40.0, 35.0, 30.0]:
    in_, ip, on_, op = run_pair(f"cap={cap}", cap=cap)
    id_ = ip - b_is_pnl
    od_ = op - b_oos_pnl
    wf = (od_ / id_) if abs(id_) > 0.01 else float('nan')
    prod = " <--prod" if cap == 999.0 else ""
    pass_fail = "WF-PASS" if (wf >= 0.70 and od_ > 0) else ("OOS-HURT" if od_ < -50 else "INCONCLUSIVE")
    print(f"  {cap:<8.0f} {in_:>6} {ip:>10.2f} {id_:>+9.2f} {on_:>6} {op:>10.2f} {od_:>+9.2f} {wf:>7.3f} {pass_fail:>12}{prod}")

print()
print("Note: Apr 2026 tariff shock (Liberation Day VIX=52) = -$6,189 in 22 IS trades.")
print("Note: OOS May 8-22 2026 (VIX 20-35, declining) = +$4,747 in 17 trades.")
print("Note: Q3-25 (BoJ recovery, VIX declining 65->20) = +$4,446 in 60 IS trades.")
print("Goal: block Apr 2026 extremes WITHOUT hurting OOS (WF >= 0.70, OOS_d > 0).")
print()

# Sub-period deep-dive for the winning cap threshold
print("=== SUB-PERIOD BREAKDOWN for selected caps ===")
sub_windows = [
    ("IS-Q1-25", dt.date(2025, 1, 1),  dt.date(2025, 3, 31)),
    ("IS-Q3-25", dt.date(2025, 7, 1),  dt.date(2025, 9, 30)),
    ("IS-Q4-25", dt.date(2025, 10, 1), dt.date(2025, 12, 31)),
    ("IS-Feb26", dt.date(2026, 2, 1),  dt.date(2026, 2, 28)),
    ("IS-Mar26", dt.date(2026, 3, 1),  dt.date(2026, 3, 31)),
    ("IS-Apr26", dt.date(2026, 4, 1),  dt.date(2026, 4, 30)),
    ("OOS-May26",dt.date(2026, 5, 8),  dt.date(2026, 5, 22)),
]
print(f"\n  {'window':<12} {'cap':>6} {'n':>5} {'P&L':>10} {'WR':>7}")
for cap in [999.0, 45.0, 35.0]:
    overrides = {"vix_hard_cap_bear": cap}
    for label, start, end in sub_windows:
        r = run_backtest(spy, vix, start_date=start, end_date=end, params_overrides=overrides, **CORRECT)
        pnl = sum(t.dollar_pnl for t in r.trades if t.dollar_pnl is not None)
        wins = [t for t in r.trades if (t.dollar_pnl or 0) > 0]
        wr = len(wins) / len(r.trades) if r.trades else 0
        print(f"  {label:<12} {cap:>6.0f} {len(r.trades):>5} {pnl:>10.2f} {wr:>7.1%}")
    print()

print("Done.")

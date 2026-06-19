"""
L115: Multi-day VIX declining required for BEAR entries.

Hypothesis (L93 recommendation): BEARISH_REVERSAL fires best in VIX-DECLINING recovery regimes
(Q3-25 BoJ crash recovery, Feb-26 DeepSeek recovery, OOS May-26 Liberation Day recovery).
April 2026 tariff shock losses (-$6,189) occur during VIX-ESCALATING period (17->52 over ~10 days).

New filter: When VIX_DECLINING_REQUIRED_BEAR=True, block BEAR entries if vix_now > vix_5d_ma
(current VIX above 5-day rolling daily-close average = escalating multi-day trend).

VIX_DECLINING_REQUIRED_BEAR=False (default) = production behavior unchanged.
VIX_DECLINING_REQUIRED_BEAR=True = block when vix_now > vix_5d_ma (escalating regime).

Run: python backtest/autoresearch/sweep_vix_declining_bear.py
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


def run_pair(label, declining_required):
    """declining_required: bool. Passed via params_overrides."""
    overrides = {"vix_declining_required_bear": declining_required}
    ri = run_backtest(spy, vix, start_date=IS_START, end_date=IS_END,
                      params_overrides=overrides, **CORRECT)
    ro = run_backtest(spy, vix, start_date=OOS_START, end_date=OOS_END,
                      params_overrides=overrides, **CORRECT)
    ip = sum(t.dollar_pnl for t in ri.trades if t.dollar_pnl is not None)
    op = sum(t.dollar_pnl for t in ro.trades if t.dollar_pnl is not None)
    return len(ri.trades), ip, len(ro.trades), op


print("Loading BASELINE (declining_required=False)...")
b_is_n, b_is_pnl, b_oos_n, b_oos_pnl = run_pair("baseline", declining_required=False)
print(f"BASELINE: IS n={b_is_n}, pnl=${b_is_pnl:.2f} | OOS n={b_oos_n}, pnl=${b_oos_pnl:.2f}")
print()

print("=== VIX_DECLINING_REQUIRED_BEAR SWEEP ===")
print(f"  {'setting':<26} {'IS_n':>6} {'IS_pnl':>10} {'IS_d':>9} {'OOS_n':>6} {'OOS_pnl':>10} {'OOS_d':>9} {'WF':>7} {'verdict':>12}")

for val in [False, True]:
    in_, ip, on_, op = run_pair(str(val), val)
    id_ = ip - b_is_pnl
    od_ = op - b_oos_pnl
    wf = (od_ / id_) if abs(id_) > 0.01 else float('nan')
    prod = " <--prod" if not val else ""
    pass_fail = "WF-PASS" if (wf >= 0.70 and od_ > 0) else ("OOS-HURT" if od_ < -50 else "INCONCLUSIVE")
    print(f"  vix_declining_required={val!s:<8} {in_:>6} {ip:>10.2f} {id_:>+9.2f} {on_:>6} {op:>10.2f} {od_:>+9.2f} {wf:>7.3f} {pass_fail:>12}{prod}")

print()
print("Sub-window breakdown (True vs False):")
sub_windows = [
    ("IS-Q1-25", dt.date(2025, 1, 1),  dt.date(2025, 3, 31)),
    ("IS-Q3-25", dt.date(2025, 7, 1),  dt.date(2025, 9, 30)),
    ("IS-Q4-25", dt.date(2025, 10, 1), dt.date(2025, 12, 31)),
    ("IS-Feb26", dt.date(2026, 2, 1),  dt.date(2026, 2, 28)),
    ("IS-Mar26", dt.date(2026, 3, 1),  dt.date(2026, 3, 31)),
    ("IS-Apr26", dt.date(2026, 4, 1),  dt.date(2026, 4, 30)),
    ("OOS-May26",dt.date(2026, 5, 8),  dt.date(2026, 5, 22)),
]
print(f"\n  {'window':<12} {'declining':>10} {'n':>5} {'P&L':>10} {'WR':>7}")
for val in [False, True]:
    overrides = {"vix_declining_required_bear": val}
    for label, start, end in sub_windows:
        r = run_backtest(spy, vix, start_date=start, end_date=end,
                         params_overrides=overrides, **CORRECT)
        pnl = sum(t.dollar_pnl for t in r.trades if t.dollar_pnl is not None)
        wins = [t for t in r.trades if (t.dollar_pnl or 0) > 0]
        wr = len(wins) / len(r.trades) if r.trades else 0
        print(f"  {label:<12} {str(val):>10} {len(r.trades):>5} {pnl:>10.2f} {wr:>7.1%}")
    print()

print("Done.")
print()
print("Key: Apr-26 = Liberation Day tariff shock (VIX escalating 17->52)")
print("Key: Q3-25 / Feb-26 / OOS-May26 = recovery regimes (VIX declining)")
print("Goal: Apr-26 trades REMOVED by True, Q3-25/Feb-26/OOS trades PRESERVED")

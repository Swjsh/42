"""
Sweep ribbon_flip_price_confirm IS+OOS.

ribbon_flip_price_confirm=True: only exit on ribbon flip-back if SPY has also
moved past entry_spot (for puts: close >= entry_spot; for calls: close <= entry_spot).

Hypothesis: prevents premature exits when ribbon flips to opposite stack during
noise but price is still in favor. Root cause of 5/01 J anchor: ribbon flipped
BULL at 13:45 (10 min into the trade) while SPY was still below 722.81 entry —
engine exited flat at +$3, J held to +$470.

Also sweeps level_stop_buffer_dollars to confirm L113 fix is live.

Run: python backtest/autoresearch/sweep_ribbon_flip_confirm.py
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

IS_S, IS_E = dt.date(2025, 1, 1), dt.date(2026, 4, 30)
OOS_S, OOS_E = dt.date(2026, 5, 8), dt.date(2026, 5, 22)

CORRECT = dict(
    use_real_fills=True, no_trade_window=None, no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True, premium_stop_pct_bear=-0.20,
    premium_stop_pct_bull=-0.08, per_trade_risk_cap_pct=0.30,
    tp1_qty_fraction=0.667, runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
)

def run_pair(label, **kwargs):
    r_is  = run_backtest(spy, vix, start_date=IS_S,  end_date=IS_E,  **CORRECT, **kwargs)
    r_oos = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **CORRECT, **kwargs)
    is_pnl  = sum(t.dollar_pnl for t in r_is.trades  if t.dollar_pnl is not None)
    oos_pnl = sum(t.dollar_pnl for t in r_oos.trades if t.dollar_pnl is not None)
    return len(r_is.trades), is_pnl, len(r_oos.trades), oos_pnl

print("Loading BASELINE...")
bn_is, b_is_pnl, bn_oos, b_oos_pnl = run_pair("baseline")
print(f"BASELINE: IS n={bn_is}, pnl=${b_is_pnl:.2f} | OOS n={bn_oos}, pnl=${b_oos_pnl:.2f}")
print()

# === ribbon_flip_price_confirm sweep ===
print("=== RIBBON_FLIP_PRICE_CONFIRM SWEEP (IS+OOS) ===")
print(f"  {'config':<35} {'IS_n':>6} {'IS_pnl':>10} {'IS_d':>9} {'OOS_n':>6} {'OOS_pnl':>10} {'OOS_d':>9} {'WF':>7}")

cases = [
    ("False (baseline)", dict()),
    ("True", dict(ribbon_flip_price_confirm=True)),
]

for label, kwargs in cases:
    in_, ip, on_, op = run_pair(label, **kwargs)
    id_ = ip - b_is_pnl; od_ = op - b_oos_pnl
    wf = (od_ / id_) if abs(id_) > 0.01 else float('nan')
    prod = " <--prod" if not kwargs else ""
    print(f"  {label:<35} {in_:>6} {ip:>10.2f} {id_:>+9.2f} {on_:>6} {op:>10.2f} {od_:>+9.2f} {wf:>7.3f}{prod}")

print()

# === level_stop_buffer_dollars sweep (L113 verification) ===
print("=== LEVEL_STOP_BUFFER_DOLLARS SWEEP (L113 verification) ===")
print(f"  {'buf':<10} {'IS_n':>6} {'IS_pnl':>10} {'IS_d':>9} {'OOS_n':>6} {'OOS_pnl':>10} {'OOS_d':>9} {'WF':>7}")

for buf in [0.10, 0.25, 0.50, 0.75, 1.00]:
    in_, ip, on_, op = run_pair(f"buf={buf}", level_stop_buffer_dollars=buf)
    id_ = ip - b_is_pnl; od_ = op - b_oos_pnl
    wf = (od_ / id_) if abs(id_) > 0.01 else float('nan')
    prod = " <--prod" if buf == 0.50 else ""
    print(f"  {buf:<10} {in_:>6} {ip:>10.2f} {id_:>+9.2f} {on_:>6} {op:>10.2f} {od_:>+9.2f} {wf:>7.3f}{prod}")

print()

# === min_premium_for_level_tiers sweep ===
print("=== MIN_PREMIUM_FOR_LEVEL_TIERS SWEEP (IS+OOS) ===")
print(f"  {'premium':<10} {'IS_n':>6} {'IS_pnl':>10} {'IS_d':>9} {'OOS_n':>6} {'OOS_pnl':>10} {'OOS_d':>9} {'WF':>7}")

for prem in [0.10, 0.25, 0.50, 0.75, 1.00]:
    in_, ip, on_, op = run_pair(f"prem={prem}", min_premium_for_level_tiers=prem)
    id_ = ip - b_is_pnl; od_ = op - b_oos_pnl
    wf = (od_ / id_) if abs(id_) > 0.01 else float('nan')
    prod = " <--prod" if prem == 0.50 else ""
    print(f"  {prem:<10} {in_:>6} {ip:>10.2f} {id_:>+9.2f} {on_:>6} {op:>10.2f} {od_:>+9.2f} {wf:>7.3f}{prod}")

print()
print("Done.")

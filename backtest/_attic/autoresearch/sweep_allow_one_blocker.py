"""
Sweep allow_one_blocker + vix_soft_mode IS+OOS.

allow_one_blocker=True: setup can pass with up to 1 non-structural blocker
  (filters 6/7/8/9 are slack slots; 1/2/3/4/5 are structural-required).
  Rationale: catches J-quality setups that have marginal ribbon spread or
  marginal VIX on high-conviction days.

vix_soft_mode=True: filter 8 (VIX gate) becomes a -1 score modifier instead
  of a hard blocker. Allows falling-VIX environments to still produce setups.

Also sweeps allow_one_blocker_min_spread_cents to find the right guard.

Run: python backtest/autoresearch/sweep_allow_one_blocker.py
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

def run(label, **kwargs):
    r_is  = run_backtest(spy, vix, start_date=IS_S,  end_date=IS_E,  **CORRECT, **kwargs)
    r_oos = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **CORRECT, **kwargs)
    is_pnl  = sum(t.dollar_pnl for t in r_is.trades  if t.dollar_pnl is not None)
    oos_pnl = sum(t.dollar_pnl for t in r_oos.trades if t.dollar_pnl is not None)
    return len(r_is.trades), is_pnl, len(r_oos.trades), oos_pnl

print("Loading BASELINE...")
bn_is, b_is_pnl, bn_oos, b_oos_pnl = run("BASELINE")
print(f"BASELINE: IS n={bn_is}, pnl=${b_is_pnl:.2f} | OOS n={bn_oos}, pnl=${b_oos_pnl:.2f}")
print()

# === allow_one_blocker sweep ===
print("=== ALLOW_ONE_BLOCKER SWEEP (IS+OOS) ===")
print(f"  {'config':<40} {'IS_n':>6} {'IS_pnl':>10} {'IS_d':>9} {'OOS_n':>6} {'OOS_pnl':>10} {'OOS_d':>9} {'WF':>7}")

cases = [
    ("OFF (baseline)", dict()),
    ("allow_one_blocker=True", dict(allow_one_blocker=True)),
    ("allow_one_blocker=True, min_spread=20", dict(allow_one_blocker=True, allow_one_blocker_min_spread_cents=20)),
    ("allow_one_blocker=True, min_spread=25", dict(allow_one_blocker=True, allow_one_blocker_min_spread_cents=25)),
    ("allow_one_blocker=True, min_spread=30", dict(allow_one_blocker=True, allow_one_blocker_min_spread_cents=30)),
]

for label, kwargs in cases:
    in_, ip, on_, op = run(label, **kwargs)
    id_ = ip - b_is_pnl
    od_ = op - b_oos_pnl
    wf = (od_ / id_) if abs(id_) > 0.01 else float('nan')
    prod = " <--prod" if not kwargs else ""
    print(f"  {label:<40} {in_:>6} {ip:>10.2f} {id_:>+9.2f} {on_:>6} {op:>10.2f} {od_:>+9.2f} {wf:>7.3f}{prod}")

print()

# === vix_soft_mode sweep ===
print("=== VIX_SOFT_MODE SWEEP (IS+OOS) ===")
print(f"  {'config':<40} {'IS_n':>6} {'IS_pnl':>10} {'IS_d':>9} {'OOS_n':>6} {'OOS_pnl':>10} {'OOS_d':>9} {'WF':>7}")

cases2 = [
    ("OFF (baseline)", dict()),
    ("vix_soft_mode=True", dict(vix_soft_mode=True)),
]

for label, kwargs in cases2:
    in_, ip, on_, op = run(label, **kwargs)
    id_ = ip - b_is_pnl
    od_ = op - b_oos_pnl
    wf = (od_ / id_) if abs(id_) > 0.01 else float('nan')
    prod = " <--prod" if not kwargs else ""
    print(f"  {label:<40} {in_:>6} {ip:>10.2f} {id_:>+9.2f} {on_:>6} {op:>10.2f} {od_:>+9.2f} {wf:>7.3f}{prod}")

print()

# === allow_one_blocker + vix_soft_mode combined ===
print("=== COMBINED: allow_one_blocker=True + vix_soft_mode=True ===")
in_, ip, on_, op = run("combined", allow_one_blocker=True, vix_soft_mode=True)
id_ = ip - b_is_pnl; od_ = op - b_oos_pnl
wf = (od_ / id_) if abs(id_) > 0.01 else float('nan')
print(f"  allow_one_blocker+vix_soft: IS n={in_}, pnl=${ip:.2f} (d={id_:+.2f}) | OOS n={on_}, pnl=${op:.2f} (d={od_:+.2f}) WF={wf:.3f}")

# === sweep_blocker_enabled ===
print()
print("=== SWEEP_BLOCKER_ENABLED (IS+OOS) ===")
in_, ip, on_, op = run("sweep_blocker_enabled=True", sweep_blocker_enabled=True)
id_ = ip - b_is_pnl; od_ = op - b_oos_pnl
wf = (od_ / id_) if abs(id_) > 0.01 else float('nan')
print(f"  sweep_blocker=True: IS n={in_}, pnl=${ip:.2f} (d={id_:+.2f}) | OOS n={on_}, pnl=${op:.2f} (d={od_:+.2f}) WF={wf:.3f}")

print()
print("Done.")

"""Quick calibration: run 4 v14_enhanced combos sequentially to measure
actual wide_pnl and set appropriate floors.

Each combo ~60s → total ~4 min.
"""
import datetime as dt
import json
import sys
import time
from pathlib import Path

REPO = Path("C:/Users/jackw/Desktop/42/backtest")
sys.path.insert(0, str(REPO))

from autoresearch import runner as _runner

params_path = Path("C:/Users/jackw/Desktop/42/automation/state/params.json")

WIDE_START = dt.date(2025, 1, 1)
WIDE_END = dt.date(2026, 5, 22)

LOCKED = {
    "strike_offset_bear": 0,
    "min_triggers_bear": 1,
    "premium_stop_pct_bear": -0.20,
    "tp1_qty_fraction": 0.5,
}

# 4 combos from extremes of the sweep grid
CALIBRATION_COMBOS = [
    # (no_trade_before, profit_lock, tp1, runner, label)
    ("09:35", 0.0,  0.30, 1.5, "early_gate_tight"),
    ("09:35", 0.10, 0.75, 2.0, "early_gate_with_lock"),
    ("10:00", 0.0,  0.50, 2.0, "10am_gate_base"),
    ("10:00", 0.20, 1.00, 2.5, "10am_gate_wide"),
]

print("Running 4 v14_enhanced calibration combos (sequential)...")
print()
print(f"{'Label':<30}  {'wide_pnl':>10}  {'n_trades':>9}  {'wr':>6}  {'elapsed':>8}")
print("-" * 70)

pnls = []
t_start = time.perf_counter()

for no_trade_before, pl_threshold, tp1, runner_target, label in CALIBRATION_COMBOS:
    params = json.loads(params_path.read_text(encoding="utf-8-sig"))
    params.update(LOCKED)
    params.update({
        "no_trade_before": no_trade_before,
        "profit_lock_threshold_pct": pl_threshold,
        "profit_lock_stop_offset_pct": 0.05,
        "tp1_premium_pct": tp1,
        "runner_target_premium_pct": runner_target,
    })
    t0 = time.perf_counter()
    spy_w, vix_w = _runner.load_data(WIDE_START, WIDE_END)
    res, m = _runner.run_with_params(params, WIDE_START, WIDE_END, spy_w, vix_w)
    elapsed = time.perf_counter() - t0
    wide_pnl = round(m.total_pnl, 2)
    n_trades = m.n_trades
    wr = round(m.n_winners / m.n_trades, 3) if m.n_trades else 0
    print(f"{label:<30}  ${wide_pnl:>9.2f}  {n_trades:>9}  {wr:>6.3f}  {elapsed:>7.1f}s")
    pnls.append(wide_pnl)

t_total = time.perf_counter() - t_start
print("-" * 70)
print(f"Min: ${min(pnls):.0f}  Max: ${max(pnls):.0f}  Median: ${sorted(pnls)[len(pnls)//2]:.0f}")
print()
print(f"Total wall time: {t_total:.1f}s")
print()
print("FLOOR RECOMMENDATION:")
for floor in [1000, 1500, 2000, 3000, 5000]:
    passing = sum(1 for p in pnls if p >= floor)
    print(f"  floor=${floor:>5}: {passing}/{len(pnls)} combos pass")

"""Quick benchmark of one v14_enhanced combo to diagnose performance."""
import datetime as dt
import json
import sys
import time
from pathlib import Path

REPO = Path("C:/Users/jackw/Desktop/42/backtest")
sys.path.insert(0, str(REPO))

params_path = Path("C:/Users/jackw/Desktop/42/automation/state/params.json")
params = json.loads(params_path.read_text(encoding="utf-8-sig"))

# Typical v14_enhanced combo
LOCKED_OVERRIDES = {
    "strike_offset_bear": 0,
    "min_triggers_bear": 1,
    "premium_stop_pct_bear": -0.20,
    "tp1_qty_fraction": 0.5,
}
combo = dict(LOCKED_OVERRIDES)
combo.update({
    "no_trade_before": "09:35",
    "profit_lock_threshold_pct": 0.05,
    "profit_lock_stop_offset_pct": 0.05,
    "tp1_premium_pct": 0.50,
    "runner_target_premium_pct": 2.0,
})
params.update(combo)

from autoresearch import runner as _runner

# J-days benchmark (5 days)
print("=== J-days benchmark ===")
t0 = time.perf_counter()
all_dates = ["2026-04-29", "2026-05-01", "2026-05-04", "2026-05-05", "2026-05-07"]
min_d = dt.date.fromisoformat(min(all_dates))
max_d = dt.date.fromisoformat(max(all_dates))
spy_j, vix_j = _runner.load_data(min_d, max_d)
for d_str in all_dates:
    d = dt.date.fromisoformat(d_str)
    _, m = _runner.run_with_params(params, d, d, spy_j, vix_j)
    print(f"  {d_str}: n_trades={m.n_trades} pnl=${m.total_pnl:.2f}")
t1 = time.perf_counter()
print(f"J-days elapsed: {t1 - t0:.1f}s")
print()

# Wide window benchmark (just time it, don't run full -- estimate from 1 month)
print("=== Wide window benchmark (1-month sample) ===")
t2 = time.perf_counter()
WIDE_START = dt.date(2025, 1, 1)
WIDE_SAMPLE_END = dt.date(2025, 2, 28)  # 2 months sample
spy_w, vix_w = _runner.load_data(WIDE_START, WIDE_SAMPLE_END)
res, m_wide = _runner.run_with_params(params, WIDE_START, WIDE_SAMPLE_END, spy_w, vix_w)
t3 = time.perf_counter()
sample_elapsed = t3 - t2
total_months = (dt.date(2026, 5, 22) - dt.date(2025, 1, 1)).days / 30.44
sample_months = (WIDE_SAMPLE_END - WIDE_START).days / 30.44
projected_full = sample_elapsed * (total_months / sample_months)
print(f"  Sample ({sample_months:.1f} months): {sample_elapsed:.1f}s, trades={m_wide.n_trades}, pnl=${m_wide.total_pnl:.2f}")
print(f"  Projected full ({total_months:.1f} months): {projected_full:.0f}s = {projected_full/60:.1f} min")
print()
print(f"  VERDICT: full wide window will take ~{projected_full:.0f}s per combo")
if projected_full > 300:
    print("  WARNING: >5 min per combo -- need caching or batch optimization")

"""
CONSEQUENCE-lens stress test for G4-DESIGNATION-ACCURACY's verify-2 pass.
Reuses fleetgates_bypass-cohort-pnl.py's own join machinery (no reimplementation) to
get safe-3's raw cohort_A_bypass (leak) trade list, then removes the top-3 dollar
contributors (winning trades) and recomputes total_pnl, to test whether the "the fix
would cost real dollars" framing survives concentration-stripping.

Read-only. No writes to automation/state/**. Writes only to analysis/deep-research/2026-09-03-money/
(via a separate call, not this file) -- this script's own output goes to stdout only, matching
the read-only stress-test nature of a verify pass.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD_PATH = ROOT / "backtest" / "tools" / "fleetgates_bypass-cohort-pnl.py"

spec = importlib.util.spec_from_file_location("fleetgates_bypass_cohort_pnl", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules["fleetgates_bypass_cohort_pnl"] = mod
spec.loader.exec_module(mod)

core_idx, n_core_total, n_core_indexed = mod.build_core_index()
mae_meta, mae_lut = mod.load_mae_mfe()
cycles = mod.build_fill_cycles_from_ledger()
from collections import defaultdict
cycles_by_key = defaultdict(list)
for c in cycles:
    cycles_by_key[(c["arm"], c["date"], c["symbol"])].append(c)

trades, n_entry, n_joined, n_joined_fallback, n_reentry = mod.join_arm("safe-3", core_idx, mae_lut, cycles_by_key)

cohort_a = [t for t in trades if t.get("cohort") == "A_BYPASS" and t.get("matched")]
print(f"safe-3 cohort_A_bypass matched trades: n={len(cohort_a)}")

pnls = [(t["date"], t["symbol"], t.get("realized_pnl")) for t in cohort_a]
pnls_sorted = sorted(pnls, key=lambda x: (x[2] if x[2] is not None else 0), reverse=True)
print("\nAll cohort_A_bypass trades, sorted by pnl descending:")
for date, sym, pnl in pnls_sorted:
    print(f"  {date} {sym}: {pnl}")

total_pnl = sum(p for (_, _, p) in pnls if p is not None)
print(f"\ntotal_pnl (all {len(cohort_a)} trades): {total_pnl}")

# Remove top-3 dollar contributors (the 3 biggest winning trades)
top3 = pnls_sorted[:3]
top3_sum = sum(p for (_, _, p) in top3 if p is not None)
remaining = pnls_sorted[3:]
remaining_sum = sum(p for (_, _, p) in remaining if p is not None)
print(f"\ntop-3 contributors: {top3} (sum={top3_sum})")
print(f"remaining {len(remaining)} trades after removing top-3: total_pnl = {remaining_sum}")
print(f"sign flip from removing top-3: {'YES' if (total_pnl > 0) != (remaining_sum > 0) else 'NO'}")

# Also drop-best-DAY (not just best trade) for cross-check against the JSON's own
# drop_best_day_total_pnl=-188.0 figure
by_day = defaultdict(float)
for date, sym, pnl in pnls:
    if pnl is not None:
        by_day[date] += pnl
best_day = max(by_day, key=lambda d: by_day[d])
drop_best_day_total = total_pnl - by_day[best_day]
print(f"\nby-day totals: {dict(by_day)}")
print(f"best_day={best_day} pnl={by_day[best_day]}")
print(f"drop_best_day_total_pnl = {drop_best_day_total} (report's JSON claims -188.0)")

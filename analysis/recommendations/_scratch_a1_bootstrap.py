"""
A1 day-level bootstrap of Profit Factor under cost/slippage adjustment.
Reuses per-trade fee calc from _scratch_a1_cost_rebuild.py's logic (duplicated
inline to stay a standalone script). Read-only; writes only under analysis/.
"""
import json
import math
import random

RATES = {
    "occ_per_contract": 0.025,
    "orf_per_contract": 0.015,
    "taf_per_contract_sell": 0.00329,
    "sec_rate_per_dollar_sell": 2.0600000000000003e-05,
    "cat_per_arm_day": 0.01,
}

def ceil_cents(x):
    return math.ceil(round(x * 100, 6)) / 100.0

def fee_ex_cat(qty, exit_px):
    sell_proceeds = exit_px * qty * 100.0
    occ = 2 * ceil_cents(RATES["occ_per_contract"] * qty)
    orf = 2 * ceil_cents(RATES["orf_per_contract"] * qty)
    taf = ceil_cents(RATES["taf_per_contract_sell"] * qty)
    sec = ceil_cents(RATES["sec_rate_per_dollar_sell"] * sell_proceeds)
    return occ + orf + taf + sec

rows = []
with open("analysis/trades-enriched.jsonl", encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        if r.get("_meta"):
            continue
        rows.append(r)

AUG_LO, AUG_HI = "2026-08-01", "2026-08-27"
aug = [r for r in rows if AUG_LO <= r["date"] <= AUG_HI]

# CAT fee: $0.01 per (arm, date) with at least one trade that day -- allocate
# evenly across that arm-day's trades so per-trade adjusted pnl sums correctly.
from collections import defaultdict
arm_day_counts = defaultdict(int)
for r in aug:
    arm_day_counts[(r["arm"], r["date"])] += 1

def adjusted_pnl(r, slip_cents):
    fee = fee_ex_cat(r["qty"], r["exit_px_avg"])
    cat_share = RATES["cat_per_arm_day"] / arm_day_counts[(r["arm"], r["date"])]
    slip = (slip_cents / 100.0) * r["qty"]
    return r["pnl_dollars"] - fee - cat_share - slip

def daily_pnls(pnl_fn):
    by_day = defaultdict(float)
    for r in aug:
        by_day[r["date"]] += pnl_fn(r)
    return by_day  # dict date -> pnl

def profit_factor(day_pnls_values):
    gains = sum(v for v in day_pnls_values if v > 0)
    losses = -sum(v for v in day_pnls_values if v < 0)
    if losses == 0:
        return float("inf") if gains > 0 else float("nan")
    return gains / losses

def bootstrap_pf(day_pnls_values, n_boot=20000, seed=42):
    rng = random.Random(seed)
    n = len(day_pnls_values)
    pfs = []
    for _ in range(n_boot):
        sample = [day_pnls_values[rng.randrange(n)] for _ in range(n)]
        pf = profit_factor(sample)
        if pf == pf and pf != float("inf"):  # exclude nan; keep inf out too (rare all-win resample)
            pfs.append(pf)
    pfs.sort()
    if not pfs:
        return None
    lo_idx = int(0.025 * len(pfs))
    hi_idx = int(0.975 * len(pfs))
    p_le_1 = sum(1 for p in pfs if p <= 1.0) / len(pfs)
    return {
        "n_boot_valid": len(pfs),
        "pf_point": profit_factor(day_pnls_values),
        "ci_2.5": round(pfs[lo_idx], 3),
        "ci_97.5": round(pfs[hi_idx], 3),
        "P(PF<=1.0)": round(p_le_1, 3),
    }

results = {}
for label, fn in [
    ("as_traded", lambda r: r["pnl_dollars"]),
    ("fees_only_0c_slip", lambda r: adjusted_pnl(r, 0)),
    ("fees_plus_2c_slip", lambda r: adjusted_pnl(r, 2)),
    ("fees_plus_5c_slip", lambda r: adjusted_pnl(r, 5)),
]:
    by_day = daily_pnls(fn)
    vals = list(by_day.values())
    total = sum(vals)
    res = bootstrap_pf(vals)
    res["n_days"] = len(vals)
    res["total_pnl"] = round(total, 2)
    results[label] = res
    print(label, json.dumps(res, indent=2))

out_path = "analysis/recommendations/A1-bootstrap-cost-adjusted-2026-08-28.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump({
        "_doc": "Day-level bootstrap of Profit Factor for August 2026 (2026-08-01..2026-08-27, "
                "5 active arms, 19 trading days), at increasing cost realism: as-traded (paper) "
                "-> +regulatory fees only -> +2c/contract exit slippage -> +5c/contract exit "
                "slippage. 20000 resamples with replacement over trading DAYS (not trades) to "
                "respect within-day trade correlation. Methodology: percentile bootstrap, "
                "gains/losses summed at the day level.",
        "generated_et": "2026-08-28",
        "window": [AUG_LO, AUG_HI],
        "results": results,
    }, f, indent=2)
print("WROTE", out_path)

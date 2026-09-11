"""
A1 cost-rebuild scratch script (read-only analysis; writes only to analysis/).
Rebuilds true cost model per trade from analysis/trades-enriched.jsonl,
applying OCC/ORF/TAF/SEC/CAT per analysis/recommendations/cost-model.json rates,
plus an exit-side slippage sweep (0/1/2/3/5 cents/contract).

Fee rounding rule verified against cost-model.json's existing per-row 'fees'
objects: EACH fee component (occ_entry, occ_exit, orf_entry, orf_exit,
taf_exit, sec_exit) is individually rounded UP to the next whole cent before
summing. CAT is $0.01 per (arm, trading-day), not per trade.
"""
import json
import math
from collections import defaultdict, Counter

RATES = {
    "occ_per_contract": 0.025,
    "orf_per_contract": 0.015,
    "taf_per_contract_sell": 0.00329,
    "sec_rate_per_dollar_sell": 2.0600000000000003e-05,
    "cat_per_arm_day": 0.01,
}

def ceil_cents(x):
    return math.ceil(round(x * 100, 6)) / 100.0

def compute_fees(qty, entry_px, exit_px):
    sell_proceeds = exit_px * qty * 100.0
    occ_entry = ceil_cents(RATES["occ_per_contract"] * qty)
    occ_exit = ceil_cents(RATES["occ_per_contract"] * qty)
    orf_entry = ceil_cents(RATES["orf_per_contract"] * qty)
    orf_exit = ceil_cents(RATES["orf_per_contract"] * qty)
    taf_exit = ceil_cents(RATES["taf_per_contract_sell"] * qty)
    sec_exit = ceil_cents(RATES["sec_rate_per_dollar_sell"] * sell_proceeds)
    total = occ_entry + occ_exit + orf_entry + orf_exit + taf_exit + sec_exit
    return total

rows = []
with open("analysis/trades-enriched.jsonl", encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        if r.get("_meta"):
            continue
        rows.append(r)

for r in rows:
    r["fee_ex_cat"] = compute_fees(r["qty"], r["entry_px"], r["exit_px_avg"])

def slice_rows(rows, lo=None, hi=None):
    out = []
    for r in rows:
        if lo and r["date"] < lo:
            continue
        if hi and r["date"] > hi:
            continue
        out.append(r)
    return out

AUG_LO, AUG_HI = "2026-08-01", "2026-08-27"
aug_rows = slice_rows(rows, AUG_LO, AUG_HI)
full_rows = rows  # 2026-06-26 .. 2026-08-27

SLIP_SCENARIOS = [0, 1, 2, 3, 5]

def summarize(subset, label):
    out = {"label": label, "n_round_trips": len(subset)}
    as_traded = sum(r["pnl_dollars"] for r in subset)
    fee_ex_cat_sum = sum(r["fee_ex_cat"] for r in subset)
    arm_days = set((r["arm"], r["date"]) for r in subset)
    cat_total = round(len(arm_days) * RATES["cat_per_arm_day"], 2)
    total_qty = sum(r["qty"] for r in subset)
    out["as_traded_pnl"] = round(as_traded, 2)
    out["fee_ex_cat_total"] = round(fee_ex_cat_sum, 2)
    out["cat_total"] = cat_total
    out["fee_total"] = round(fee_ex_cat_sum + cat_total, 2)
    out["net_at_zero_slippage"] = round(as_traded - fee_ex_cat_sum - cat_total, 2)
    out["total_exit_contracts"] = total_qty
    scenarios = {}
    for c in SLIP_SCENARIOS:
        slip_dollars = (c / 100.0) * total_qty
        net = as_traded - fee_ex_cat_sum - cat_total - slip_dollars
        scenarios[f"{c}c"] = round(net, 2)
    out["scenarios"] = scenarios
    # exact linear breakeven slippage in cents/contract (net_at_zero_slippage / total_qty * 100)
    if total_qty > 0:
        out["breakeven_slippage_cents_per_contract"] = round(
            (out["net_at_zero_slippage"] / total_qty) * 100, 3
        )
    else:
        out["breakeven_slippage_cents_per_contract"] = None
    return out

print("=" * 70)
print("AUGUST 2026 (2026-08-01 .. 2026-08-27), 5 active arms")
print("=" * 70)
book_aug = summarize(aug_rows, "AUGUST BOOK (5 arms)")
print(json.dumps(book_aug, indent=2))

per_arm_aug = {}
for arm in sorted(set(r["arm"] for r in aug_rows)):
    sub = [r for r in aug_rows if r["arm"] == arm]
    per_arm_aug[arm] = summarize(sub, arm)
print(json.dumps(per_arm_aug, indent=2))

print("=" * 70)
print("FULL HISTORY (2026-06-26 .. 2026-08-27), all arms incl retired safe-1")
print("=" * 70)
book_full = summarize(full_rows, "FULL HISTORY BOOK (all arms)")
print(json.dumps(book_full, indent=2))

per_arm_full = {}
for arm in sorted(set(r["arm"] for r in full_rows)):
    sub = [r for r in full_rows if r["arm"] == arm]
    per_arm_full[arm] = summarize(sub, arm)
print(json.dumps(per_arm_full, indent=2))

# Right tail: exit_reason == "tp1+trail" in August
print("=" * 70)
print("RIGHT TAIL (August, exit_reason == 'tp1+trail')")
print("=" * 70)
tail = [r for r in aug_rows if r.get("exit_reason") == "tp1+trail"]
rest = [r for r in aug_rows if r.get("exit_reason") != "tp1+trail"]
tail_summary = summarize(tail, "tail (tp1+trail)")
rest_summary = summarize(rest, "rest")
print(json.dumps(tail_summary, indent=2))
print(json.dumps(rest_summary, indent=2))

# Save full dump to a JSON file for downstream use (day-level bootstrap script)
out_path = "analysis/recommendations/A1-cost-rebuild-2026-08-28.json"
dump = {
    "_doc": "A1 task: cost-model rebuild from trades-enriched.jsonl with OCC/ORF/TAF/SEC/CAT "
            "fees (cost-model.json rates, ceil-to-cent per component) + exit-side slippage sweep "
            "(0/1/2/3/5c/contract, applied once per exiting contract). Breakeven = per-book linear "
            "solve for net=0. Read-only analysis; source ledger analysis/trades-enriched.jsonl "
            "(canonical, built 2026-08-27) cross-checked n_round_trips against automation/state/fills-ledger.jsonl.",
    "generated_et": "2026-08-28",
    "rates_used": RATES,
    "august_2026": {"window": [AUG_LO, AUG_HI], "book": book_aug, "per_arm": per_arm_aug,
                     "right_tail_tp1_trail": tail_summary, "rest_ex_tail": rest_summary},
    "full_history": {"window": ["2026-06-26", "2026-08-27"], "book": book_full, "per_arm": per_arm_full},
}
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(dump, f, indent=2)
print("WROTE", out_path)

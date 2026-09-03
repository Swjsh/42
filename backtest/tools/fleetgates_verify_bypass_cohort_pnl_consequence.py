"""
SCRATCH / read-only verification tool. CONSEQUENCE lens on G3 (fleet-gates-bypass-cohort-pnl).
Re-derives the same joined trade records as fleetgates_bypass-cohort-pnl.py (imported directly,
not re-implemented) and asks: does the headline dollar effect survive removing its top-3
dollar contributors? Read-only on the whole repo except its own output file (argv[1]).
"""
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "backtest/tools/fleetgates_bypass-cohort-pnl.py"

spec = importlib.util.spec_from_file_location("fleetgates_bypass_cohort_pnl", SRC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

FLEET_ARMS = mod.FLEET_ARMS


def build_all():
    core_idx, n_core_total, n_core_indexed = mod.build_core_index()
    mae_meta, mae_lut = mod.load_mae_mfe()
    cycles = mod.build_fill_cycles_from_ledger()
    cbk = defaultdict(list)
    for c in cycles:
        cbk[(c["arm"], c["date"], c["symbol"])].append(c)
    all_joined = {}
    for arm in FLEET_ARMS:
        rows, n_entry, n_joined, n_joined_fallback, n_skip = mod.join_arm(
            arm, core_idx, mae_lut, cbk)
        all_joined[arm] = rows
    return all_joined


def matched_pnl_trades(trades):
    return [t for t in trades if t.get("matched") and t.get("realized_pnl") is not None]


def remove_top_n(trades, n=3):
    mt = matched_pnl_trades(trades)
    by_pnl_desc = sorted(mt, key=lambda t: t["realized_pnl"], reverse=True)
    removed_top_winners = by_pnl_desc[:n]
    remaining_after_winners = by_pnl_desc[n:]
    by_abs_desc = sorted(mt, key=lambda t: abs(t["realized_pnl"]), reverse=True)
    removed_top_abs = by_abs_desc[:n]
    remaining_after_abs = by_abs_desc[n:]
    return {
        "removed_top3_winners": removed_top_winners,
        "remaining_after_removing_top3_winners": remaining_after_winners,
        "removed_top3_abs": removed_top_abs,
        "remaining_after_removing_top3_abs": remaining_after_abs,
    }


def summarize(trades):
    total = round(sum(t["realized_pnl"] for t in trades), 2)
    n = len(trades)
    wins = [t["realized_pnl"] for t in trades if t["realized_pnl"] > 0]
    losses = [t["realized_pnl"] for t in trades if t["realized_pnl"] < 0]
    wr = round(len(wins) / (len(wins) + len(losses)), 4) if (wins or losses) else None
    pf = round(sum(wins) / abs(sum(losses)), 3) if losses and sum(losses) != 0 else (
        "inf" if wins and not losses else None)
    return {"n": n, "total_pnl": total, "wr": wr, "pf": pf}


def trade_brief(t):
    return {
        "arm": t["arm"], "date": t["date"], "symbol": t["symbol"],
        "pnl": t["realized_pnl"], "cohort": t["cohort"],
        "safe_verdict": t.get("safe_verdict"), "bold_verdict": t.get("bold_verdict"),
    }


def main():
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        ROOT / "analysis/deep-research/2026-09-03-money/verify-fleet-gates-bypass-cohort-pnl-2.json")

    all_joined = build_all()

    report = {}

    # 1. safe-3 cohort A (the headline +$752 claim)
    safe3_a = [t for t in all_joined["safe-3"] if t["cohort"] == "A_BYPASS"]
    safe3_a_m = matched_pnl_trades(safe3_a)
    cuts = remove_top_n(safe3_a, n=3)
    report["safe3_cohort_A"] = {
        "full": summarize(safe3_a_m),
        "all_trades_sorted_desc": [trade_brief(t) for t in sorted(
            safe3_a_m, key=lambda t: t["realized_pnl"], reverse=True)],
        "removed_top3_winners": [trade_brief(t) for t in cuts["removed_top3_winners"]],
        "after_removing_top3_winners": summarize(cuts["remaining_after_removing_top3_winners"]),
    }

    # 2. Population cohort A (all 4 arms, +$33 claim)
    pop_a = []
    for arm in FLEET_ARMS:
        pop_a += [t for t in all_joined[arm] if t["cohort"] == "A_BYPASS"]
    pop_a_m = matched_pnl_trades(pop_a)
    cuts_pop = remove_top_n(pop_a, n=3)
    report["population_cohort_A"] = {
        "full": summarize(pop_a_m),
        "all_trades_sorted_desc": [trade_brief(t) for t in sorted(
            pop_a_m, key=lambda t: t["realized_pnl"], reverse=True)],
        "removed_top3_winners": [trade_brief(t) for t in cuts_pop["removed_top3_winners"]],
        "after_removing_top3_winners": summarize(cuts_pop["remaining_after_removing_top3_winners"]),
        "removed_top3_abs": [trade_brief(t) for t in cuts_pop["removed_top3_abs"]],
        "after_removing_top3_abs": summarize(cuts_pop["remaining_after_removing_top3_abs"]),
    }

    # 3. Population cohort B (control, -$1325 claim) -- also check top-3 LOSER concentration
    pop_b = []
    for arm in FLEET_ARMS:
        pop_b += [t for t in all_joined[arm] if t["cohort"] == "B_BOTH_PASSED"]
    pop_b_m = matched_pnl_trades(pop_b)
    by_loss_desc = sorted(pop_b_m, key=lambda t: t["realized_pnl"])
    removed_top3_losers_b = by_loss_desc[:3]
    remaining_b = by_loss_desc[3:]
    report["population_cohort_B_top3_losers"] = {
        "full": summarize(pop_b_m),
        "removed_top3_losers": [trade_brief(t) for t in removed_top3_losers_b],
        "after_removing_top3_losers": summarize(remaining_b),
    }

    # 4. Candidate (a): safe-3 + safe-1 cohort A removed set (+$752 headline change)
    cand_a_removed = []
    for arm in ["safe-3", "safe-1"]:
        cand_a_removed += [t for t in all_joined[arm] if t["cohort"] == "A_BYPASS"]
    cand_a_m = matched_pnl_trades(cand_a_removed)
    cuts_cand_a = remove_top_n(cand_a_removed, n=3)
    report["candidate_a_removed_set"] = {
        "full": summarize(cand_a_m),
        "removed_top3_winners": [trade_brief(t) for t in cuts_cand_a["removed_top3_winners"]],
        "after_removing_top3_winners": summarize(cuts_cand_a["remaining_after_removing_top3_winners"]),
    }

    # 5. Candidate (b): full removed set (safe-role A + risky-role mirror C) (+$1323 headline)
    safe_role_arms = ["safe-3", "safe-1"]
    risky_role_arms = ["risky-1", "risky-3"]
    removed_safe_role = []
    for arm in safe_role_arms:
        removed_safe_role += [t for t in all_joined[arm] if t["cohort"] == "A_BYPASS"]

    def bold_gated_safe_passed(t):
        return (t["cohort"] == "C_OTHER" and t.get("safe_verdict") == t.get("want_verdict")
                and t.get("bold_verdict") != t.get("want_verdict"))

    removed_risky_role = []
    for arm in risky_role_arms:
        removed_risky_role += [t for t in all_joined[arm] if bold_gated_safe_passed(t)]
    cand_b_removed = removed_safe_role + removed_risky_role
    cand_b_m = matched_pnl_trades(cand_b_removed)
    cuts_cand_b = remove_top_n(cand_b_removed, n=3)
    remaining_after_top3 = cuts_cand_b["remaining_after_removing_top3_winners"]
    remaining_after_top3_and_0806 = [t for t in remaining_after_top3 if t["date"] != "2026-08-06"]
    report["candidate_b_removed_set"] = {
        "full": summarize(cand_b_m),
        "all_trades_sorted_desc": [trade_brief(t) for t in sorted(
            cand_b_m, key=lambda t: t["realized_pnl"], reverse=True)],
        "removed_top3_winners": [trade_brief(t) for t in cuts_cand_b["removed_top3_winners"]],
        "after_removing_top3_winners": summarize(remaining_after_top3),
        "after_removing_top3_winners_AND_dropping_0806": summarize(remaining_after_top3_and_0806),
    }

    # 6. safe-3 September cohort A (+$802 claim, n=4)
    safe3_sept_a = [t for t in safe3_a if t["date"] >= "2026-09-01"]
    safe3_sept_a_m = matched_pnl_trades(safe3_sept_a)
    report["safe3_september_cohort_A"] = {
        "full": summarize(safe3_sept_a_m),
        "all_trades": [trade_brief(t) for t in sorted(
            safe3_sept_a_m, key=lambda t: t["realized_pnl"], reverse=True)],
        "note": "n=4 total -- 'top-3' removes 3 of 4 trades, near-total; reported for completeness "
                "but not a meaningful stress test at this n.",
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"WROTE {out_path}")
    print(json.dumps({k: v.get("full") if isinstance(v, dict) else None for k, v in report.items()}, indent=2))


if __name__ == "__main__":
    main()

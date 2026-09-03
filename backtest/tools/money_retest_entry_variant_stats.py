"""money_retest_entry_variant_stats.py -- stats pass over
retest-entry-variant-walked.json: WR/PF, bootstrap CI, regime/arm splits, concentration,
missed-winner count, big-winner-day check. Read-only. Companion to
money_retest_entry_variant.py (H10 RETEST ENTRY study).
"""
from __future__ import annotations

import json
import random
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "analysis" / "deep-research" / "2026-09-03-money"
WALKED_PATH = OUT_DIR / "retest-entry-variant-walked.json"

BIG_WINNER_DAYS = ["2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"]
SAFE2_TRUSTED = {"safe-2"}  # only arm clearing walker magnitude-fidelity PASS

random.seed(20260903)


def wr(pnls):
    n = len(pnls)
    if n == 0:
        return None
    return sum(1 for p in pnls if p > 0) / n


def pf(pnls):
    wins = sum(p for p in pnls if p > 0)
    losses = -sum(p for p in pnls if p < 0)
    if losses == 0:
        return float("inf") if wins > 0 else None
    return wins / losses


def bootstrap_ci_mean(vals, n_resamples=5000):
    if not vals:
        return (None, None, None)
    n = len(vals)
    means = []
    for _ in range(n_resamples):
        sample = [vals[random.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int(0.025 * n_resamples)]
    hi = means[int(0.975 * n_resamples) - 1]
    point = sum(vals) / n
    return (point, lo, hi)


def concentration_top3(pnls_with_id):
    total = sum(p for _, p in pnls_with_id)
    top3 = sorted(pnls_with_id, key=lambda x: -x[1])[:3]
    top3_sum = sum(p for _, p in top3)
    frac = None if total == 0 else top3_sum / total
    return top3, frac, total


def main():
    rows = json.loads(WALKED_PATH.read_text(encoding="utf-8"))
    comparable = [r for r in rows if r["retest_outcome"] in ("confirmed", "invalidated", "timeout")]
    excluded_data_gap = [r for r in rows if r["retest_outcome"] not in ("confirmed", "invalidated", "timeout")]

    n = len(comparable)
    actual_pnls = [r["actual_walk_pnl"] for r in comparable]
    retest_pnls = [r["retest_walk_pnl"] for r in comparable]  # 0.0 for no-trade rows already
    diffs = [rt - ac for rt, ac in zip(retest_pnls, actual_pnls)]

    taken = [r for r in comparable if r["retest_outcome"] == "confirmed"]
    not_taken = [r for r in comparable if r["retest_outcome"] != "confirmed"]

    result = {
        "n_total_raw_entries": len(rows),
        "n_excluded_data_gap": len(excluded_data_gap),
        "excluded_data_gap_detail": [
            {"arm": r["arm"], "date": r["date"], "symbol": r["symbol"], "ts_et": r["ts_et"],
             "reason": r["retest_outcome"], "actual_walk_pnl": r["actual_walk_pnl"]}
            for r in excluded_data_gap
        ],
        "n_comparable": n,
        "n_confirmed_retest_taken": len(taken),
        "n_not_taken": len(not_taken),
        "n_invalidated": sum(1 for r in comparable if r["retest_outcome"] == "invalidated"),
        "n_timeout": sum(1 for r in comparable if r["retest_outcome"] == "timeout"),

        "actual_total_pnl": round(sum(actual_pnls), 2),
        "retest_total_pnl": round(sum(retest_pnls), 2),
        "actual_wr": wr(actual_pnls),
        "actual_pf": pf(actual_pnls),
        "retest_wr_of_taken": wr([r["retest_walk_pnl"] for r in taken]),
        "retest_pf_of_taken": pf([r["retest_walk_pnl"] for r in taken]),
        "retest_taken_total_pnl": round(sum(r["retest_walk_pnl"] for r in taken), 2),
        "actual_pnl_of_taken_subset": round(sum(r["actual_walk_pnl"] for r in taken), 2),
        "actual_pnl_of_not_taken_subset": round(sum(r["actual_walk_pnl"] for r in not_taken), 2),
    }

    result["bootstrap_mean_actual_pnl_per_trade"] = bootstrap_ci_mean(actual_pnls)
    result["bootstrap_mean_retest_pnl_per_trade"] = bootstrap_ci_mean(retest_pnls)
    result["bootstrap_mean_diff_per_trade"] = bootstrap_ci_mean(diffs)

    # Missed winners: not-taken rows where the ACTUAL trade was a winner.
    missed_winners = [r for r in not_taken if r["actual_walk_pnl"] > 0]
    result["n_missed_winners"] = len(missed_winners)
    result["missed_winners_actual_pnl_sum"] = round(sum(r["actual_walk_pnl"] for r in missed_winners), 2)
    result["missed_winners_detail"] = [
        {"arm": r["arm"], "date": r["date"], "symbol": r["symbol"], "setup": r["setup"],
         "actual_walk_pnl": r["actual_walk_pnl"], "retest_outcome": r["retest_outcome"]}
        for r in sorted(missed_winners, key=lambda x: -x["actual_walk_pnl"])
    ]

    # Saved losers: not-taken rows where the ACTUAL trade was a loser (retest "saved" this loss).
    saved_losers = [r for r in not_taken if r["actual_walk_pnl"] < 0]
    result["n_saved_losers"] = len(saved_losers)
    result["saved_losers_actual_pnl_sum"] = round(sum(r["actual_walk_pnl"] for r in saved_losers), 2)

    # New losers taken by retest that the ORIGINAL breakout would have avoided (both taken, both compared)
    both_taken = taken  # retest only ever adds a trade when a breakout trade already existed
    flips_to_loss = [r for r in both_taken if r["actual_walk_pnl"] > 0 and r["retest_walk_pnl"] <= 0]
    flips_to_win = [r for r in both_taken if r["actual_walk_pnl"] <= 0 and r["retest_walk_pnl"] > 0]
    result["n_taken_flip_win_to_loss"] = len(flips_to_win and flips_to_loss) if False else len(flips_to_loss)
    result["n_taken_flip_loss_to_win"] = len(flips_to_win)

    # Concentration: top-3 trade dollars as fraction of each side's total.
    actual_ids = [(f"{r['arm']}|{r['date']}|{r['symbol']}", r["actual_walk_pnl"]) for r in comparable]
    retest_ids = [(f"{r['arm']}|{r['date']}|{r['symbol']}", r["retest_walk_pnl"]) for r in comparable]
    a_top3, a_frac, a_total = concentration_top3(actual_ids)
    r_top3, r_frac, r_total = concentration_top3(retest_ids)
    result["concentration"] = {
        "actual_top3": [{"id": i, "pnl": round(p, 2)} for i, p in a_top3],
        "actual_top3_frac_of_total": a_frac,
        "retest_top3": [{"id": i, "pnl": round(p, 2)} for i, p in r_top3],
        "retest_top3_frac_of_total": r_frac,
    }

    # Per-arm split
    by_arm = {}
    for arm in sorted(set(r["arm"] for r in comparable)):
        sub = [r for r in comparable if r["arm"] == arm]
        sub_taken = [r for r in sub if r["retest_outcome"] == "confirmed"]
        by_arm[arm] = {
            "n": len(sub),
            "n_confirmed": len(sub_taken),
            "actual_total": round(sum(r["actual_walk_pnl"] for r in sub), 2),
            "retest_total": round(sum(r["retest_walk_pnl"] for r in sub), 2),
            "actual_wr": wr([r["actual_walk_pnl"] for r in sub]),
            "retest_wr_of_taken": wr([r["retest_walk_pnl"] for r in sub_taken]),
            "fidelity": "safe-2 PASS (magnitude-trusted)" if arm in SAFE2_TRUSTED else "SIGN-ONLY (walker FAILs magnitude for this arm)",
        }
    result["by_arm"] = by_arm

    # Regime split by VIX (only entries with a known vix -- core arms + fleet rows sharing a
    # core_tick_id with a core-decisions row)
    def vix_bucket(v):
        if v is None:
            return "unknown"
        if v < 15:
            return "<15"
        if v <= 17:
            return "15-17"
        return ">17"

    by_regime = {}
    for r in comparable:
        b = vix_bucket(r.get("vix"))
        by_regime.setdefault(b, []).append(r)
    result["by_vix_regime"] = {
        b: {
            "n": len(rs),
            "actual_total": round(sum(x["actual_walk_pnl"] for x in rs), 2),
            "retest_total": round(sum(x["retest_walk_pnl"] for x in rs), 2),
            "n_confirmed": sum(1 for x in rs if x["retest_outcome"] == "confirmed"),
        }
        for b, rs in by_regime.items()
    }

    # Big-winner-day check
    by_day = {}
    for d in BIG_WINNER_DAYS:
        sub = [r for r in comparable if r["date"] == d]
        sub_all_incl_gap = [r for r in rows if r["date"] == d]
        sub_taken = [r for r in sub if r["retest_outcome"] == "confirmed"]
        by_day[d] = {
            "n_entries": len(sub_all_incl_gap),
            "n_comparable": len(sub),
            "n_confirmed_by_retest": len(sub_taken),
            "actual_total_pnl": round(sum(r["actual_walk_pnl"] for r in sub_all_incl_gap), 2),
            "retest_total_pnl": round(sum(r["retest_walk_pnl"] for r in sub), 2),
            "would_have_blocked_the_day": len(sub_taken) == 0 and len(sub_all_incl_gap) > 0,
        }
    result["big_winner_days"] = by_day

    out_path = OUT_DIR / "retest-entry-variant-stats.json"
    out_path.write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    print(json.dumps(result, indent=1, default=str))
    print("\nwrote", out_path)


if __name__ == "__main__":
    main()

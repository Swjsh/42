"""
swarm_v4_base_scale.py
Retrograde simulation of confidence formula v4 (base multiplier reduction) on 65-day data.

The v3 retrograde showed: formula penalties alone don't improve ECE because demoted days
migrate between buckets at the same accuracy. The base multiplier (x75) is systematically
~20-25pp too high. This script tests x55 vs x60 vs x65 to find the optimal base.

Does NOT re-run any replays. Uses existing swarm_output.json files + aggregate.json.

Outputs: analysis/swarm-tuning/v4_base_scale_simulation.json
"""

import json
import pathlib
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parents[3]
AGG_PATH = ROOT / "analysis" / "swarm-benchmark" / "aggregate.json"
REPLAY_DIR = ROOT / "analysis" / "swarm-benchmark"
OUT_PATH = ROOT / "analysis" / "swarm-tuning" / "v4_base_scale_simulation.json"

CONF_BUCKETS = [
    (0,   39,  "low"),
    (40,  59,  "medium"),
    (60,  74,  "high"),
    (75,  89,  "very_high"),
    (90, 100,  "max"),
]

# ──────────────────────────────────────────────────────────────────────────────
# Re-derive the base v2 formula output for each day from swarm_output.json
# We can't perfectly reverse-engineer the formula, but we CAN approximate it:
# v2_conf = weighted_score * 75 + adjustments
# So: v4_conf = weighted_score * NEW_MULT + same_adjustments
# Adjustment delta = v2_conf - weighted_score * 75
# v4_conf = v2_conf - weighted_score * 75 + weighted_score * NEW_MULT
#         = v2_conf + weighted_score * (NEW_MULT - 75)
# ──────────────────────────────────────────────────────────────────────────────

def compute_ece(days: list) -> dict:
    buckets = {}
    for lo, hi, name in CONF_BUCKETS:
        subset = [d for d in days if lo <= d["conf"] <= hi]
        n = len(subset)
        if n == 0:
            buckets[name] = {"n": 0, "accuracy_pct": None, "expected_pct": None, "gap_pp": None}
            continue
        accuracy = sum(1 for d in subset if d["correct"]) / n
        expected = sum(d["conf"] for d in subset) / (100.0 * n)
        buckets[name] = {
            "n": n,
            "accuracy_pct": round(accuracy * 100, 1),
            "expected_pct": round(expected * 100, 1),
            "gap_pp": round(accuracy * 100 - expected * 100, 1),
        }
    total_n = sum(b["n"] for b in buckets.values())
    ece = 0.0
    for b in buckets.values():
        if b["n"] == 0 or b["accuracy_pct"] is None:
            continue
        ece += (b["n"] / total_n) * abs(b["accuracy_pct"] - b["expected_pct"])
    return {"ece_pct": round(ece, 2), "buckets": buckets, "n_tradeable": total_n}


def simulate_base_scale(per_day_data: list, new_mult: float) -> list:
    """
    For each tradeable day, estimate v4_conf = v2_conf + weighted_score * (new_mult - 75).
    Then apply same hard gates as v3 (4/4 agreement for conf >= 80, UNTESTED -15, etc.)
    Clamp to [10, 95].
    """
    results = []
    for r in per_day_data:
        if r.get("direction_grade") == "ABSTAIN_ACTUAL":
            results.append({**r, "v4_conf": None, "note": "abstain"})
            continue

        v2_conf = r["v2_conf"]
        weighted_score = r.get("weighted_score", None)
        specialist_agreement = r.get("specialist_agreement", None)
        battle_grade = r.get("battle_grade", "")
        consensus_strength = r.get("consensus_strength", "")

        if weighted_score is None or specialist_agreement is None:
            results.append({**r, "v4_conf": v2_conf, "note": "no_weighted_score"})
            continue

        # Reconstruct the formula delta
        # v2_conf ~= weighted_score * 75 + adjustments
        # So adjustments ~= v2_conf - weighted_score * 75
        # v4_conf = weighted_score * new_mult + adjustments
        #         = v2_conf + weighted_score * (new_mult - 75)
        adjustments_approx = v2_conf - weighted_score * 75.0
        v4_conf_raw = weighted_score * new_mult + adjustments_approx

        # Apply UNTESTED -15 penalty (same as v3, if not already baked into adjustments)
        # Note: in v3, the UNTESTED -15 was applied. Here we need to check if the original
        # v2 had the penalty or not. Since v2 did NOT have UNTESTED penalty, we add it fresh.
        if battle_grade == "UNTESTED":
            v4_conf_raw -= 15

        # Apply 3/4 agreement adjustment
        # v2 gave +3 for 3/4 agree. We keep that removed (same as v3).
        if specialist_agreement == 3:
            v4_conf_raw -= 3  # remove v2's +3 bonus

        # Hard gate: conf >= 80 requires 4/4 + strong (same as v3)
        if v4_conf_raw >= 80 and not (specialist_agreement == 4 and consensus_strength == "strong"):
            v4_conf_raw = 76

        v4_conf = int(max(10, min(95, round(v4_conf_raw))))
        delta = v4_conf - v2_conf

        results.append({
            **r,
            "v4_conf": v4_conf,
            "v4_delta": delta,
            "v4_weighted_score_contrib": round(weighted_score * new_mult, 1),
            "note": "ok"
        })
    return results


def main():
    agg = json.loads(AGG_PATH.read_text(encoding="utf-8"))
    per_day = agg["per_day"]

    # Build enriched per_day with weighted_score + specialist_agreement from replay files
    enriched = []
    for entry in per_day:
        date = entry["date"]
        row = {
            "date": date,
            "v2_conf": entry["swarm_conf"],
            "battle_grade": entry.get("battle_grade", ""),
            "direction_grade": entry["direction_grade"],
            "correct": (entry["direction_grade"] == "CORRECT"),
        }

        # Try to read weighted_scores and vote_counts from replay
        replay_path = REPLAY_DIR / f"replay-{date}-0600" / "swarm_output.json"
        if replay_path.exists():
            so = json.loads(replay_path.read_text(encoding="utf-8"))
            ws = so.get("weighted_scores", {})
            bias = so.get("consensus_bias", "")
            row["weighted_score"] = ws.get(bias, 0.0)
            vc = so.get("vote_counts", {})
            row["specialist_agreement"] = max(vc.get("bullish", 0), vc.get("bearish", 0))
            row["consensus_strength"] = so.get("consensus_strength", "")
        else:
            row["weighted_score"] = None
            row["specialist_agreement"] = None
            row["consensus_strength"] = ""

        enriched.append(row)

    # Test multiple base multipliers
    multipliers = [55, 58, 60, 62, 65, 68, 70, 75]
    mult_results = {}

    print(f"\n{'='*80}")
    print(f"  SWARM FORMULA v4 BASE-SCALE SIMULATION")
    print(f"  Testing base multipliers: {multipliers}")
    print(f"{'='*80}")
    print(f"\n  {'Mult':>6}  {'ECE%':>6}  {'Days>=80':>9}  {'Days=95':>8}  {'vhigh_acc%':>11}  {'vhigh_gap':>10}")
    print(f"  {'-'*6}  {'-'*6}  {'-'*9}  {'-'*8}  {'-'*11}  {'-'*10}")

    for mult in multipliers:
        sim = simulate_base_scale(enriched, float(mult))
        tradeable = [r for r in sim if r.get("v4_conf") is not None and r["direction_grade"] != "ABSTAIN_ACTUAL"]
        ece_data = [{"conf": r["v4_conf"], "correct": r["correct"]} for r in tradeable]
        ece = compute_ece(ece_data)
        days_80plus = sum(1 for r in tradeable if r["v4_conf"] >= 80)
        days_95 = sum(1 for r in tradeable if r["v4_conf"] >= 95)
        vh = ece["buckets"]["very_high"]
        vh_acc = vh["accuracy_pct"] if vh["n"] > 0 else "n/a"
        vh_gap = vh["gap_pp"] if vh["n"] > 0 else "n/a"
        mult_results[mult] = {
            "ece_pct": ece["ece_pct"],
            "buckets": ece["buckets"],
            "days_conf80plus": days_80plus,
            "days_conf95": days_95,
            "pct_conf80plus": round(days_80plus / len(tradeable) * 100, 1),
            "pct_conf95": round(days_95 / len(tradeable) * 100, 1),
        }
        tag = " <-- current v2/v3" if mult == 75 else ("" if mult != 60 else " <-- proposed v4")
        print(f"  {mult:>6}  {ece['ece_pct']:>6.2f}  {days_80plus:>9} ({days_80plus/len(tradeable)*100:.0f}%)  "
              f"{days_95:>8}  {str(vh_acc):>11}  {str(vh_gap):>10}{tag}")

    # Best mult by ECE
    best_mult = min(mult_results, key=lambda m: mult_results[m]["ece_pct"])
    best_ece = mult_results[best_mult]["ece_pct"]

    print(f"\n  Best multiplier by ECE: x{best_mult} (ECE={best_ece:.2f}%)")
    print(f"\n  Detailed bucket breakdown for x{best_mult}:")
    sim_best = simulate_base_scale(enriched, float(best_mult))
    tradeable_best = [r for r in sim_best if r.get("v4_conf") is not None and r["direction_grade"] != "ABSTAIN_ACTUAL"]
    ece_best = compute_ece([{"conf": r["v4_conf"], "correct": r["correct"]} for r in tradeable_best])
    for lo, hi, name in CONF_BUCKETS:
        b = ece_best["buckets"][name]
        if b["n"] == 0:
            print(f"    {name:<12}   0 days")
        else:
            print(f"    {name:<12}  {b['n']:>3} days  acc={b['accuracy_pct']:>5.1f}%  exp={b['expected_pct']:>5.1f}%  gap={b['gap_pp']:>+6.1f}pp")

    print(f"\n{'='*80}\n")

    # Write output
    summary = {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"),
        "n_days_total": len(per_day),
        "n_tradeable": len([r for r in enriched if r["direction_grade"] != "ABSTAIN_ACTUAL"]),
        "multipliers_tested": multipliers,
        "v2_current_ece_pct": 21.67,
        "best_multiplier": best_mult,
        "best_multiplier_ece_pct": best_ece,
        "ece_improvement_vs_v2": round(21.67 - best_ece, 2),
        "per_multiplier_results": mult_results,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"  Written: {OUT_PATH}")


if __name__ == "__main__":
    main()

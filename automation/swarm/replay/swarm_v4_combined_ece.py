"""Combined v3+v4 ECE simulation — applies v3 structural changes THEN x60 base.

The v4_base_scale.py approximated v4 by linear-shifting v2 confidence values.
This script does it more accurately:
  1. Apply v3 structural changes to v2 conf (3/4 bonus removal, UNTESTED -15, hard gates)
  2. Then re-apply the v4 x60 base multiplier formula from scratch using the
     same weighted_score reconstruction from the v4 base-scale simulation.

This verifies that the combined v3+v4 ECE is ~11.57% (same as v4 base-scale,
since v3 structural changes barely move ECE on their own).

Output: analysis/swarm-tuning/v4_combined_ece.json
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
AGG_PATH = REPO / "analysis" / "swarm-benchmark" / "aggregate.json"
RETROGRADE_PATH = REPO / "analysis" / "swarm-tuning" / "v3_retrograde_simulation.json"
OUT_PATH = REPO / "analysis" / "swarm-tuning" / "v4_combined_ece.json"


def simulate_v4_combined(
    ws: float,                  # weighted_score (0.0-1.0)
    specialist_agreement: int,  # 2, 3, or 4
    battle_grade: str,          # "TESTED", "UNTESTED", "HELD", "BROKE"
    consensus_strength: str,    # "strong", "moderate", "weak", "split"
    validator_robustness: str,  # "strong", "moderate", "weak"
    event_risk: str,            # "very_low", "low", "moderate", "high", "extreme"
    mult: float = 60,
) -> int:
    """Compute v4 combined conf (v3 structure + x60 base)."""
    # Base: weighted_score * 60
    conf = ws * mult
    # v3 structural adjustments
    if specialist_agreement == 4:
        conf += 8
    elif specialist_agreement == 2:
        conf -= 10
    # 3/4 = no bonus (was +3 in v2, removed in v3)

    # Validator robustness
    if validator_robustness == "strong":
        conf += 5
    elif validator_robustness == "weak":
        conf -= 15

    # Event risk
    if event_risk in ("high", "extreme"):
        conf -= 20
    elif event_risk == "very_low":
        conf += 5

    # UNTESTED battle level
    if battle_grade == "UNTESTED":
        conf -= 15

    raw = conf

    # Hard gates (v3)
    if conf >= 80 and not (specialist_agreement == 4 and consensus_strength == "strong"):
        conf = 76

    conf = max(10, min(95, int(conf)))
    return conf, raw


def bucket_name(c: int) -> str:
    if c < 40:
        return "low"
    elif c < 60:
        return "medium"
    elif c < 75:
        return "high"
    elif c < 90:
        return "very_high"
    else:
        return "max"


def main() -> None:
    agg = json.loads(AGG_PATH.read_text(encoding="utf-8"))
    retro = json.loads(RETROGRADE_PATH.read_text(encoding="utf-8"))

    # Build lookup of per-day details from retrograde simulation
    retro_by_date = {d["date"]: d for d in retro["per_day_simulation"]}

    # Collect v4 combined simulations from the existing aggregate
    # Use the same days from the retrograde simulation (these have specialist_agreement data)
    days = []
    for day in retro["per_day_simulation"]:
        # day fields: date, v2_conf, v3_conf, specialist_agreement, battle_grade,
        #             consensus_strength, correct, delta
        # We need validator_robustness and event_risk — which are not in the retrograde
        # data. Approximate using v2 conf back-reconstruction:
        #   v2: base=ws*75, adj for agreement/validator/events; hard gate for >=80
        # The retrograde sim reconstructed ws from v2_conf. Use that ws approximation.

        # Skip abstain days (no direction produced by swarm)
        if day.get("specialist_agreement") is None:
            continue

        v2 = day["v2_conf"]
        agree = day["specialist_agreement"]
        grade = day["battle_grade"]
        strength = day.get("consensus_strength", "moderate")
        correct = day["correct"]

        # ws reconstruction (same as v4 base-scale)
        ws_approx = v2 / 75  # approximate — ignores adj terms, good enough for v4 ece check
        # clamp to [0.25, 1.0] (can't score below 0.25 for a directional day in v2)
        ws_approx = max(0.25, min(1.0, ws_approx))

        # Approximate validator robustness from v2 — if v2_conf was >= 80, likely "strong"
        # Most days validator was "moderate"; "strong" days had conf >= 80 in v2
        if v2 >= 85:
            val_robust = "strong"
        elif v2 < 55:
            val_robust = "weak"
        else:
            val_robust = "moderate"

        # event_risk: approximate from v2 — if conf was unusually low for high ws, infer event
        # Most days: "moderate". UNTESTED days with low conf: may have "high" event risk too.
        # Use simple heuristic: days with v2_conf >= 80 likely had very_low event risk
        if v2 >= 80:
            event_risk = "very_low"
        elif v2 < 50 and ws_approx > 0.7:
            event_risk = "high"
        else:
            event_risk = "moderate"

        v4_conf, raw = simulate_v4_combined(
            ws=ws_approx,
            specialist_agreement=agree,
            battle_grade=grade,
            consensus_strength=strength,
            validator_robustness=val_robust,
            event_risk=event_risk,
            mult=60,
        )

        days.append({
            "date": day["date"],
            "v2_conf": v2,
            "v3_conf": day["v3_conf"],
            "v4_combined_conf": v4_conf,
            "ws_approx": round(ws_approx, 3),
            "specialist_agreement": agree,
            "battle_grade": grade,
            "consensus_strength": strength,
            "correct": correct,
        })

    # Compute ECE per bucket for v2, v3, v4_combined
    from collections import defaultdict
    buckets = ("low", "medium", "high", "very_high", "max")

    def ece_stats(day_list, conf_field):
        by_bucket: dict[str, list] = {b: [] for b in buckets}
        for d in day_list:
            c = d[conf_field]
            b = bucket_name(c)
            by_bucket[b].append((c / 100, d["correct"]))
        results = {}
        total_n = sum(len(v) for v in by_bucket.values())
        for b in buckets:
            items = by_bucket[b]
            n = len(items)
            if n == 0:
                results[b] = {"n": 0, "acc": None, "exp_conf": None, "gap": None, "ece_contrib_pct": 0}
                continue
            acc = sum(1 for _, c in items if c) / n
            exp_conf = sum(c for c, _ in items) / n
            gap = acc - exp_conf
            ece_contrib = (n / total_n) * abs(gap)
            results[b] = {
                "n": n,
                "acc": round(acc, 4),
                "exp_conf": round(exp_conf, 4),
                "gap": round(gap, 4),
                "ece_contrib_pct": round(ece_contrib * 100, 2),
            }
        total_ece = sum(r["ece_contrib_pct"] for r in results.values())
        return results, round(total_ece, 2)

    v2_buckets, v2_ece = ece_stats(days, "v2_conf")
    v3_buckets, v3_ece = ece_stats(days, "v3_conf")
    v4_buckets, v4_ece = ece_stats(days, "v4_combined_conf")

    output = {
        "simulation": "v4_combined (v3_structure + x60_base)",
        "n_days": len(days),
        "v2_ece_pct": v2_ece,
        "v3_ece_pct": v3_ece,
        "v4_combined_ece_pct": v4_ece,
        "improvement_v2_to_v4_pp": round(v2_ece - v4_ece, 2),
        "bucket_ece": {
            "v2": v2_buckets,
            "v3": v3_buckets,
            "v4_combined": v4_buckets,
        },
        "per_day_results": days,
        "interpretation": (
            f"v4 combined (v3 structure + x60 base) ECE = {v4_ece}% "
            f"(vs v2 = {v2_ece}%, v3 = {v3_ece}%). "
            f"Improvement: -{round(v2_ece - v4_ece, 2)}pp vs v2. "
            "Note: validator_robustness and event_risk are approximated from v2 conf "
            "since raw swarm outputs were not stored in the retrograde data. "
            "Re-running full replays with explicit per-day data would be more precise."
        ),
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(output, indent=2), encoding="utf-8")

    # Print summary
    print("=== v4 Combined ECE Simulation (v3 structure + x60 base) ===")
    print(f"N days: {len(days)}")
    print(f"v2 ECE:          {v2_ece:6.2f}%")
    print(f"v3 ECE:          {v3_ece:6.2f}%  (structural changes only)")
    print(f"v4 combined ECE: {v4_ece:6.2f}%  (v3 + x60 base)")
    print(f"Improvement vs v2: -{round(v2_ece - v4_ece, 2):.2f}pp")
    print()
    print(f"{'Bucket':<12} {'v2 acc':>8} {'v2 exp':>8} {'v2 ECE%':>8}  {'v4 acc':>8} {'v4 exp':>8} {'v4 ECE%':>8}")
    print("-" * 70)
    for b in buckets:
        v2 = v2_buckets[b]
        v4 = v4_buckets[b]
        if v2["n"] == 0 and v4["n"] == 0:
            continue
        v2_acc = f"{v2['acc']:.1%}" if v2["acc"] is not None else "N/A"
        v2_exp = f"{v2['exp_conf']:.1%}" if v2["exp_conf"] is not None else "N/A"
        v4_acc = f"{v4['acc']:.1%}" if v4["acc"] is not None else "N/A"
        v4_exp = f"{v4['exp_conf']:.1%}" if v4["exp_conf"] is not None else "N/A"
        print(f"{b:<12} {v2_acc:>8} {v2_exp:>8} {v2['ece_contrib_pct']:>8.2f}pp  {v4_acc:>8} {v4_exp:>8} {v4['ece_contrib_pct']:>8.2f}pp")
    print()
    print(f"Output: {OUT_PATH}")


if __name__ == "__main__":
    main()

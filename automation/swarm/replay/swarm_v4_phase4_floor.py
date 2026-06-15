"""v4 Phase 4: Low-bucket confidence floor — prevents combined penalties from over-deflating.

Problem: v4 combined ECE = 15.80% despite base-scale ECE = 11.57%.
Root cause: cumulative downward adjustments (UNTESTED -15, val_weak -15, event_high -20)
push some days below 40% confidence even though they're correct 62.5% of the time.
These days land in the "low" bucket and contribute 13.67pp ECE.

Fix: add a floor so total downward adjustments cannot exceed floor_pct * ws * mult.
I.e., conf >= ws * mult * floor_fraction  (floor_fraction tested: 0.50, 0.60, 0.65, 0.70)

Default floor_fraction=0.65 means: for a day with ws=0.70, base=42 → floor=27.3.
With all penalties (-50 in worst case), conf is clamped to 27 instead of -8.

Output: analysis/swarm-tuning/v4_phase4_floor_simulation.json
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
AGG_PATH = REPO / "analysis" / "swarm-benchmark" / "aggregate.json"
RETROGRADE_PATH = REPO / "analysis" / "swarm-tuning" / "v3_retrograde_simulation.json"
OUT_PATH = REPO / "analysis" / "swarm-tuning" / "v4_phase4_floor_simulation.json"


def simulate_v4_phase4(
    ws: float,
    specialist_agreement: int,
    battle_grade: str,
    consensus_strength: str,
    validator_robustness: str,
    event_risk: str,
    mult: float = 60,
    floor_fraction: float = 0.65,
) -> tuple[int, float, float]:
    """Compute v4 Phase 4 conf (x60 + v3 structural + low-bucket floor).

    Returns (conf_final, conf_raw_before_floor, conf_base).
    """
    base = ws * mult

    # v3 structural adjustments
    adj = 0.0
    if specialist_agreement == 4:
        adj += 8
    elif specialist_agreement == 2:
        adj -= 10

    if validator_robustness == "strong":
        adj += 5
    elif validator_robustness == "weak":
        adj -= 15

    if event_risk in ("high", "extreme"):
        adj -= 20
    elif event_risk == "very_low":
        adj += 5

    if battle_grade == "UNTESTED":
        adj -= 15

    raw = base + adj

    # Phase 4 LOW-BUCKET FLOOR: conf >= base * floor_fraction
    floor = base * floor_fraction
    conf = max(raw, floor)

    # Hard gates (v3 — only applies to upward direction)
    if conf >= 80 and not (specialist_agreement == 4 and consensus_strength == "strong"):
        conf = 76

    conf_final = max(10, min(95, int(conf)))
    return conf_final, raw, base


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


def ece_stats(day_list: list, conf_field: str) -> tuple[dict, float]:
    buckets = ("low", "medium", "high", "very_high", "max")
    from collections import defaultdict
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


def main() -> None:
    retro = json.loads(RETROGRADE_PATH.read_text(encoding="utf-8"))

    floor_fractions = [0.50, 0.60, 0.65, 0.70, 0.75, 0.80]
    floor_results = {}

    for floor_frac in floor_fractions:
        days = []
        for day in retro["per_day_simulation"]:
            if day.get("specialist_agreement") is None:
                continue

            v2 = day["v2_conf"]
            agree = day["specialist_agreement"]
            grade = day["battle_grade"]
            strength = day.get("consensus_strength", "moderate")
            correct = day["correct"]

            ws_approx = max(0.25, min(1.0, v2 / 75))

            if v2 >= 85:
                val_robust = "strong"
            elif v2 < 55:
                val_robust = "weak"
            else:
                val_robust = "moderate"

            if v2 >= 80:
                event_risk = "very_low"
            elif v2 < 50 and ws_approx > 0.7:
                event_risk = "high"
            else:
                event_risk = "moderate"

            v4_conf, raw, base = simulate_v4_phase4(
                ws=ws_approx,
                specialist_agreement=agree,
                battle_grade=grade,
                consensus_strength=strength,
                validator_robustness=val_robust,
                event_risk=event_risk,
                mult=60,
                floor_fraction=floor_frac,
            )

            days.append({
                "date": day["date"],
                "v2_conf": v2,
                "v3_conf": day["v3_conf"],
                "v4_phase4_conf": v4_conf,
                "v4_raw": round(raw, 1),
                "v4_base": round(base, 1),
                "floor_applied": v4_conf > int(raw),
                "ws_approx": round(ws_approx, 3),
                "specialist_agreement": agree,
                "battle_grade": grade,
                "consensus_strength": strength,
                "correct": correct,
            })

        buckets_v4, ece_v4 = ece_stats(days, "v4_phase4_conf")
        buckets_v2, ece_v2 = ece_stats(days, "v2_conf")

        n_floor_applied = sum(1 for d in days if d["floor_applied"])
        floor_results[str(floor_frac)] = {
            "floor_fraction": floor_frac,
            "ece_v4_pct": ece_v4,
            "ece_v2_pct": ece_v2,
            "improvement_pp": round(ece_v2 - ece_v4, 2),
            "n_floor_applied": n_floor_applied,
            "pct_floor_applied": round(n_floor_applied / len(days) * 100, 1),
            "bucket_detail": {
                "v2": buckets_v2,
                "v4_phase4": buckets_v4,
            },
        }

    # Find best floor (lowest ECE)
    best_frac = min(floor_results, key=lambda k: floor_results[k]["ece_v4_pct"])
    best = floor_results[best_frac]

    output = {
        "simulation": "v4 Phase 4 — low-bucket floor",
        "n_days": 55,
        "problem": "v4_combined ECE = 15.80% due to 16 low-bucket days (62.5% acc vs 15.5% exp = 13.67pp ECE)",
        "fix": "floor conf >= ws * mult * floor_fraction, preventing over-penalty on UNTESTED/weak-val/high-event days",
        "best_floor_fraction": float(best_frac),
        "best_ece_pct": best["ece_v4_pct"],
        "best_improvement_vs_v2_pp": best["improvement_pp"],
        "target_met_10pct": best["ece_v4_pct"] < 10.0,
        "n_floor_applied_best": best["n_floor_applied"],
        "pct_floor_applied_best": best["pct_floor_applied"],
        "all_floor_results": floor_results,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(output, indent=2), encoding="utf-8")

    # Summary table
    print("=== v4 Phase 4: Low-Bucket Floor Simulation ===")
    print(f"{'Floor Frac':>12}  {'v4 ECE':>8}  {'vs v2':>8}  {'N floored':>10}  {'%floored':>8}")
    print("-" * 55)
    for frac_str, r in sorted(floor_results.items(), key=lambda x: float(x[0])):
        marker = " <-- BEST" if frac_str == best_frac else ""
        print(f"  floor={r['floor_fraction']:.2f}   {r['ece_v4_pct']:6.2f}%  {-r['improvement_pp']:+.2f}pp  "
              f"{r['n_floor_applied']:>8}   {r['pct_floor_applied']:>6.1f}%{marker}")
    print()
    print(f"Best floor fraction: {best_frac}  ->  ECE {best['ece_v4_pct']:.2f}%  "
          f"(improvement vs v2: -{best['improvement_pp']:.2f}pp)")
    print(f"10% ECE target met: {output['target_met_10pct']}")
    print()
    print(f"Output: {OUT_PATH}")


if __name__ == "__main__":
    main()

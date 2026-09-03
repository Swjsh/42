"""
swarm_v6_simulation.py — Retrograde simulation: v5 vs v6 weight formula.

v5 weights: technical=0.35, macro=0.30, level_thesis=0.25, internals=0.10
v6 weights: technical=0.40, macro=0.40, level_thesis=0.10, internals=0.10
v6 also adds: internals_dissent_penalty=-10

Computes ECE (Expected Calibration Error) for both, picks winner, reports.

Per OP-28: swarm formula calibration is engine improvement. Implement winner same session.

Output: analysis/swarm-v6-simulation-{date}.json
"""

import json
import math
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
REPLAY_BASE = ROOT / "analysis" / "swarm-benchmark"
AGGREGATE_PATH = ROOT / "analysis" / "swarm-benchmark" / "aggregate.json"


# -------------------------------------------------------------------------
# Weight configs
# -------------------------------------------------------------------------

WEIGHTS_V5 = {
    "technical": 0.35,
    "macro": 0.30,
    "level_thesis": 0.25,
    "internals": 0.10,
}

WEIGHTS_V6 = {
    "technical": 0.40,
    "macro": 0.40,
    "level_thesis": 0.10,
    "internals": 0.10,
}


# -------------------------------------------------------------------------
# Loaders
# -------------------------------------------------------------------------

def _load_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_day_data() -> list[dict]:
    """Load all replay data, cross-referenced with aggregate outcomes."""
    aggregate = _load_json(AGGREGATE_PATH)
    if not aggregate:
        print("ERROR: aggregate.json not found", file=sys.stderr)
        sys.exit(1)

    per_day_lookup = {e["date"]: e for e in aggregate.get("per_day", [])}

    days = []
    for replay_dir in sorted(REPLAY_BASE.iterdir()):
        if not replay_dir.is_dir() or not replay_dir.name.startswith("replay-"):
            continue
        parts = replay_dir.name.split("-")
        if len(parts) < 5:
            continue
        date_str = f"{parts[1]}-{parts[2]}-{parts[3]}"

        swarm = _load_json(replay_dir / "swarm_output.json")
        macro_out = _load_json(replay_dir / "macro_output.json")
        validator_out = _load_json(replay_dir / "validator_output.json")

        if not swarm:
            continue

        agg = per_day_lookup.get(date_str)
        if not agg:
            continue

        summaries = swarm.get("agent_summaries", {})
        votes = {}
        for agent in ("technical", "macro", "level_thesis", "internals"):
            s = summaries.get(agent, {})
            b = s.get("bias", "no_data")
            if b == "no_data":
                b = "no_trade"  # treat missing as abstain for weighting
            votes[agent] = b

        # Extract adjustments needed for formula replication
        battle_grade = agg.get("battle_grade", "UNTESTED")
        event_risk = "normal"
        if macro_out:
            event_risk = macro_out.get("event_risk", "normal")
        validator_robustness = "moderate"
        if validator_out:
            validator_robustness = validator_out.get("consensus_robustness", "moderate")

        consensus_bias = swarm.get("consensus_bias", "no_trade")
        recorded_conf = swarm.get("swarm_confidence", 0)
        direction_grade = agg.get("direction_grade", "")

        days.append({
            "date": date_str,
            "votes": votes,
            "consensus_bias": consensus_bias,
            "recorded_conf": recorded_conf,
            "battle_grade": battle_grade,
            "event_risk": event_risk,
            "validator_robustness": validator_robustness,
            "direction_grade": direction_grade,
            "actual_bias": agg.get("actual_bias", ""),
        })

    return sorted(days, key=lambda d: d["date"])


# -------------------------------------------------------------------------
# Formula simulator
# -------------------------------------------------------------------------

def compute_conf(
    votes: dict[str, str],
    consensus_bias: str,
    battle_grade: str,
    event_risk: str,
    validator_robustness: str,
    weights: dict[str, float],
    add_internals_dissent_penalty: bool = False,
) -> int:
    """Simulate the Step 5 formula with given weights."""
    if consensus_bias == "no_trade":
        return 0

    # Step 2: weighted_score
    ws_bull = sum(w for a, w in weights.items() if votes.get(a) == "bullish")
    ws_bear = sum(w for a, w in weights.items() if votes.get(a) == "bearish")

    if consensus_bias == "bullish":
        ws = ws_bull
    else:
        ws = ws_bear

    # Step 5a: base
    raw = ws * 60.0

    # Specialist agreement count
    agree_count = sum(
        1 for a in ("technical", "macro", "level_thesis", "internals")
        if votes.get(a) == consensus_bias
    )

    if agree_count == 4:
        raw += 8
    elif agree_count == 2:
        raw -= 10

    # Validator robustness
    if validator_robustness == "strong":
        raw += 5
    elif validator_robustness == "weak":
        raw -= 15

    # Event risk
    if event_risk in ("high", "extreme"):
        raw -= 20
    elif event_risk == "very_low":
        raw += 5

    # Battle grade (v5 values)
    if battle_grade == "UNTESTED":
        raw -= 25
    elif battle_grade == "HELD":
        raw -= 20

    # v6 addition: internals dissent penalty
    if add_internals_dissent_penalty:
        internals_vote = votes.get("internals", "no_trade")
        if internals_vote not in ("no_trade",) and internals_vote != consensus_bias:
            raw -= 10

    # Step 5b: NO_TRADE gate
    if raw < 40:
        return 0

    # Step 5c: hard gates
    if raw >= 80:
        if agree_count < 4:
            raw = min(raw, 76)
    if raw >= 90:
        if not (agree_count == 4 and validator_robustness == "strong"
                and event_risk not in ("high", "extreme")):
            raw = min(raw, 88)

    # Cap
    conf = max(10, min(95, int(round(raw))))
    return conf


# -------------------------------------------------------------------------
# ECE calculation
# -------------------------------------------------------------------------

def compute_ece(records: list[dict], conf_key: str, n_bins: int = 5) -> float:
    """
    Expected Calibration Error (lower is better).
    conf_key: key in each record dict for predicted confidence (0-100).
    Grade outcome: CORRECT=1, WRONG=0, ABSTAIN=excluded.
    """
    eligible = [
        r for r in records
        if r["direction_grade"] in ("CORRECT", "WRONG")
        and r.get(conf_key, 0) > 0  # exclude no_trade (conf=0)
    ]
    if not eligible:
        return float("nan")

    bin_width = 100 / n_bins
    bins: list[list[dict]] = [[] for _ in range(n_bins)]
    for r in eligible:
        c = r[conf_key]
        idx = min(int(c / bin_width), n_bins - 1)
        bins[idx].append(r)

    ece = 0.0
    total = len(eligible)
    for b in bins:
        if not b:
            continue
        avg_conf = sum(r[conf_key] for r in b) / len(b) / 100.0
        accuracy = sum(1 for r in b if r["direction_grade"] == "CORRECT") / len(b)
        ece += (len(b) / total) * abs(avg_conf - accuracy)

    return round(ece * 100, 2)  # as percentage


def compute_wr_by_band(records: list[dict], conf_key: str) -> dict:
    eligible = [
        r for r in records
        if r["direction_grade"] in ("CORRECT", "WRONG")
        and r.get(conf_key, 0) > 0
    ]
    bands = {"40_59": (40, 60), "60_79": (60, 80), "80_94": (80, 95)}
    result = {}
    for label, (lo, hi) in bands.items():
        b = [r for r in eligible if lo <= r[conf_key] < hi]
        n = len(b)
        wr = sum(1 for r in b if r["direction_grade"] == "CORRECT") / n * 100 if n else float("nan")
        result[label] = {"n": n, "wr_pct": round(wr, 1)}
    return result


def abstain_rate(records: list[dict], conf_key: str) -> float:
    graded = [r for r in records if r["direction_grade"] in ("CORRECT", "WRONG", "ABSTAIN_ACTUAL")]
    no_trade = sum(1 for r in graded if r.get(conf_key, 0) == 0)
    return round(no_trade / len(graded) * 100, 1) if graded else 0.0


# -------------------------------------------------------------------------
# Main
# -------------------------------------------------------------------------

def main() -> None:
    print("Loading replay data...")
    days = load_day_data()
    print(f"  {len(days)} days loaded")

    # Simulate both formulas
    for d in days:
        d["conf_v5"] = compute_conf(
            votes=d["votes"],
            consensus_bias=d["consensus_bias"],
            battle_grade=d["battle_grade"],
            event_risk=d["event_risk"],
            validator_robustness=d["validator_robustness"],
            weights=WEIGHTS_V5,
            add_internals_dissent_penalty=False,
        )
        d["conf_v6"] = compute_conf(
            votes=d["votes"],
            consensus_bias=d["consensus_bias"],
            battle_grade=d["battle_grade"],
            event_risk=d["event_risk"],
            validator_robustness=d["validator_robustness"],
            weights=WEIGHTS_V6,
            add_internals_dissent_penalty=True,
        )

    # ECE
    ece_v5 = compute_ece(days, "conf_v5")
    ece_v6 = compute_ece(days, "conf_v6")

    # WR by band
    wr_v5 = compute_wr_by_band(days, "conf_v5")
    wr_v6 = compute_wr_by_band(days, "conf_v6")

    # Abstain rates
    abstain_v5 = abstain_rate(days, "conf_v5")
    abstain_v6 = abstain_rate(days, "conf_v6")

    # Days where formula diverges
    diverge = [
        {
            "date": d["date"],
            "grade": d["direction_grade"],
            "consensus": d["consensus_bias"],
            "conf_v5": d["conf_v5"],
            "conf_v6": d["conf_v6"],
            "delta": d["conf_v6"] - d["conf_v5"],
        }
        for d in days
        if d["conf_v5"] != d["conf_v6"]
    ]
    diverge_wrong = [d for d in diverge if d["grade"] == "WRONG"]
    diverge_correct = [d for d in diverge if d["grade"] == "CORRECT"]

    # Cases where v6 correctly de-risked a wrong day (conf drops from high to low/notrade)
    v6_derisked = [
        d for d in diverge_wrong
        if d["delta"] < -5  # v6 lower by >5 pts on a wrong day
    ]
    # Cases where v6 incorrectly lowered conf on a correct day
    v6_hurt = [
        d for d in diverge_correct
        if d["delta"] < -5
    ]

    winner = "v6" if ece_v6 < ece_v5 else "v5"

    print(f"\n--- FORMULA COMPARISON ---")
    print(f"  ECE v5: {ece_v5}%  |  ECE v6: {ece_v6}%  |  Winner: {winner}")
    print(f"  Abstain rate: v5={abstain_v5}%  v6={abstain_v6}%")
    print(f"\n  WR by confidence band:")
    for band in ("40_59", "60_79", "80_94"):
        v5b = wr_v5.get(band, {})
        v6b = wr_v6.get(band, {})
        print(f"    [{band}] v5: n={v5b.get('n')} WR={v5b.get('wr_pct')}%  |  "
              f"v6: n={v6b.get('n')} WR={v6b.get('wr_pct')}%")

    print(f"\n  Divergent days: {len(diverge)} total")
    print(f"    {len(diverge_wrong)} wrong days  |  {len(diverge_correct)} correct days")
    print(f"    v6 correctly de-risked: {len(v6_derisked)} wrong days (conf dropped >5 pts)")
    print(f"    v6 incorrectly de-risked: {len(v6_hurt)} correct days (conf dropped >5 pts)")

    if diverge:
        print(f"\n  Sample divergent days (wrong):")
        for d in diverge_wrong[:5]:
            print(f"    {d['date']}: v5={d['conf_v5']} v6={d['conf_v6']} delta={d['delta']:+d}")
        print(f"\n  Sample divergent days (correct):")
        for d in diverge_correct[:5]:
            print(f"    {d['date']}: v5={d['conf_v5']} v6={d['conf_v6']} delta={d['delta']:+d}")

    # Output
    from datetime import date
    today = date.today().isoformat()
    output = {
        "generated_at": today,
        "n_days": len(days),
        "weights": {
            "v5": WEIGHTS_V5,
            "v6": WEIGHTS_V6,
        },
        "ece_pct": {"v5": ece_v5, "v6": ece_v6},
        "winner": winner,
        "improvement_pp": round(ece_v5 - ece_v6, 2),
        "abstain_rate_pct": {"v5": abstain_v5, "v6": abstain_v6},
        "wr_by_band": {"v5": wr_v5, "v6": wr_v6},
        "divergent_days": {
            "total": len(diverge),
            "wrong_days": diverge_wrong,
            "v6_derisked_wrong": len(v6_derisked),
            "v6_hurt_correct": len(v6_hurt),
        },
        "recommendation": (
            f"IMPLEMENT v6: ECE {ece_v5}% -> {ece_v6}% ({ece_v5-ece_v6:+.2f}pp). "
            f"v6 correctly de-risks {len(v6_derisked)} wrong days vs hurting {len(v6_hurt)} correct days."
        ) if ece_v6 < ece_v5 else (
            f"KEEP v5: ECE {ece_v5}% is already better than v6 ({ece_v6}%). "
            f"The weight redistribution does not improve calibration on this dataset."
        )
    }

    out_path = ROOT / "analysis" / f"swarm-v6-simulation-{today}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"\nOutput: {out_path}")
    print(f"Recommendation: {output['recommendation']}")


if __name__ == "__main__":
    main()

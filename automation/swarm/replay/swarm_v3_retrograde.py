"""
swarm_v3_retrograde.py
Retrograde simulation of confidence formula v3 against existing 65-day backfill.

Does NOT re-run any replays. Reads:
  - analysis/swarm-benchmark/aggregate.json  (v2 conf + battle_grade + direction grade per day)
  - analysis/swarm-benchmark/replay-{date}-0600/swarm_output.json  (vote_counts for each day)

Applies v3 formula delta rules:
  1. If specialist_agreement == 3/4 AND v2_conf >= 80: cap at 76
  2. If specialist_agreement == 3/4: +0 bonus (v2 was +3, v3 removes it)
  3. If battle_grade == "UNTESTED": -15 penalty (new in v3)
  4. Hard gate conf >= 80 requires 4/4 + consensus_strength == "strong"

Outputs:
  - Printed calibration comparison table (v2 vs v3)
  - analysis/swarm-tuning/v3_retrograde_simulation.json
"""

import json
import math
import pathlib
import sys
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parents[3]
AGG_PATH = ROOT / "analysis" / "swarm-benchmark" / "aggregate.json"
REPLAY_DIR = ROOT / "analysis" / "swarm-benchmark"
OUT_PATH = ROOT / "analysis" / "swarm-tuning" / "v3_retrograde_simulation.json"

# ──────────────────────────────────────────────────────────────────────────────
# v2 → v3 conf adjustment logic
# ──────────────────────────────────────────────────────────────────────────────

def simulate_v3_conf(v2_conf: int, specialist_agreement: int, battle_grade: str,
                     consensus_strength: str) -> int:
    """
    Simulate what v3 would produce given v2 inputs.

    Key changes from v2:
    - 3/4 agreement bonus: was +3, now 0  → subtract 3 if agreement == 3
    - battle_grade UNTESTED: new -15 penalty
    - Hard gate: conf >= 80 requires 4/4 + strong → if not met, cap at 76
    """
    conf = v2_conf

    # Undo the v2 +3 bonus for 3/4 agreement (v3 gives 0 for 3/4)
    if specialist_agreement == 3:
        conf -= 3  # remove the bonus v2 added

    # Add UNTESTED penalty (new in v3)
    if battle_grade == "UNTESTED":
        conf -= 15

    # Hard gate: conf >= 80 requires 4/4 + consensus_strength == "strong"
    if conf >= 80 and not (specialist_agreement == 4 and consensus_strength == "strong"):
        conf = 76

    # Clamp to [10, 95]
    conf = max(10, min(95, conf))

    return conf


# ──────────────────────────────────────────────────────────────────────────────
# ECE calculation
# ──────────────────────────────────────────────────────────────────────────────

CONF_BUCKETS = [
    (0,   39,  "low"),
    (40,  59,  "medium"),
    (60,  74,  "high"),
    (75,  89,  "very_high"),
    (90, 100,  "max"),
]

def compute_ece(days: list) -> dict:
    """
    days: list of {"conf": int, "correct": bool}
    Returns ECE (%) + per-bucket stats.
    """
    buckets = {}
    for lo, hi, name in CONF_BUCKETS:
        subset = [d for d in days if lo <= d["conf"] <= hi]
        n = len(subset)
        if n == 0:
            buckets[name] = {"n": 0, "accuracy": None, "expected": (lo + hi) / 200.0,
                             "gap_pp": None}
            continue
        accuracy = sum(1 for d in subset if d["correct"]) / n
        expected = sum(d["conf"] for d in subset) / (100.0 * n)
        buckets[name] = {
            "n": n,
            "accuracy_pct": round(accuracy * 100, 1),
            "expected_pct": round(expected * 100, 1),
            "gap_pp": round(accuracy * 100 - expected * 100, 1),
        }

    # ECE = weighted average of |accuracy - expected| per bucket
    total_n = sum(b["n"] for b in buckets.values())
    ece = 0.0
    for b in buckets.values():
        if b["n"] == 0 or b["accuracy_pct"] is None:
            continue
        ece += (b["n"] / total_n) * abs(b["accuracy_pct"] - b["expected_pct"])

    return {"ece_pct": round(ece, 2), "buckets": buckets, "n_tradeable": total_n}


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    agg = json.loads(AGG_PATH.read_text(encoding="utf-8"))
    per_day = agg["per_day"]

    results = []
    missing_replay = []

    for entry in per_day:
        date = entry["date"]
        v2_conf = entry["swarm_conf"]
        battle_grade = entry.get("battle_grade", "")
        direction_grade = entry["direction_grade"]

        # Skip ABSTAIN days (no tradeable bias)
        if direction_grade == "ABSTAIN_ACTUAL":
            results.append({
                "date": date,
                "v2_conf": v2_conf,
                "v3_conf": None,
                "specialist_agreement": None,
                "battle_grade": battle_grade,
                "direction_grade": direction_grade,
                "note": "abstain"
            })
            continue

        # Read swarm_output.json for this day
        replay_path = REPLAY_DIR / f"replay-{date}-0600" / "swarm_output.json"
        if not replay_path.exists():
            missing_replay.append(date)
            results.append({
                "date": date,
                "v2_conf": v2_conf,
                "v3_conf": v2_conf,  # fallback: assume v2 unchanged
                "specialist_agreement": None,
                "battle_grade": battle_grade,
                "direction_grade": direction_grade,
                "note": "no_replay_file"
            })
            continue

        swarm_out = json.loads(replay_path.read_text(encoding="utf-8"))
        vote_counts = swarm_out.get("vote_counts", {})
        consensus_strength = swarm_out.get("consensus_strength", "")

        # Specialist agreement = number of agents voting for the consensus bias
        bullish_votes = vote_counts.get("bullish", 0)
        bearish_votes = vote_counts.get("bearish", 0)
        no_trade_votes = vote_counts.get("no_trade", 0)
        specialist_agreement = max(bullish_votes, bearish_votes)

        v3_conf = simulate_v3_conf(v2_conf, specialist_agreement, battle_grade, consensus_strength)

        correct = (direction_grade == "CORRECT")
        results.append({
            "date": date,
            "v2_conf": v2_conf,
            "v3_conf": v3_conf,
            "specialist_agreement": specialist_agreement,
            "battle_grade": battle_grade,
            "direction_grade": direction_grade,
            "correct": correct,
            "consensus_strength": consensus_strength,
            "v3_delta": v3_conf - v2_conf,
        })

    # ── ECE comparison ──────────────────────────────────────────────────────
    tradeable = [r for r in results if r.get("v3_conf") is not None and r["direction_grade"] != "ABSTAIN_ACTUAL"]

    v2_days = [{"conf": r["v2_conf"], "correct": r["correct"]} for r in tradeable]
    v3_days = [{"conf": r["v3_conf"], "correct": r["correct"]} for r in tradeable]

    ece_v2 = compute_ece(v2_days)
    ece_v3 = compute_ece(v3_days)

    # ── Distribution comparison ─────────────────────────────────────────────
    v2_high_conf = [r for r in tradeable if r["v2_conf"] >= 80]
    v3_high_conf = [r for r in tradeable if r["v3_conf"] >= 80]
    v2_at_95 = [r for r in tradeable if r["v2_conf"] >= 95]
    v3_at_95 = [r for r in tradeable if r["v3_conf"] >= 95]

    # ── Days where v3 differs from v2 ──────────────────────────────────────
    changed_days = [r for r in tradeable if r["v3_delta"] != 0]

    # ── Summary ─────────────────────────────────────────────────────────────
    summary = {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"),
        "n_days_total": len(per_day),
        "n_tradeable": len(tradeable),
        "n_missing_replay": len(missing_replay),
        "missing_replay_dates": missing_replay,
        "ece": {
            "v2_pct": ece_v2["ece_pct"],
            "v3_pct": ece_v3["ece_pct"],
            "improvement_pp": round(ece_v2["ece_pct"] - ece_v3["ece_pct"], 2),
        },
        "conf_distribution": {
            "v2_days_at_conf80plus": len(v2_high_conf),
            "v3_days_at_conf80plus": len(v3_high_conf),
            "v2_pct_at_95": round(len(v2_at_95) / len(tradeable) * 100, 1),
            "v3_pct_at_95": round(len(v3_at_95) / len(tradeable) * 100, 1),
        },
        "n_days_conf_changed_by_v3": len(changed_days),
        "ece_v2_buckets": ece_v2["buckets"],
        "ece_v3_buckets": ece_v3["buckets"],
        "per_day_simulation": results,
        "changed_days_detail": [
            {k: v for k, v in r.items() if k != "note"}
            for r in changed_days
        ],
    }

    # ── Print ────────────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  SWARM FORMULA v3 RETROGRADE SIMULATION  ({len(tradeable)} tradeable days)")
    print(f"{'='*70}")
    print(f"\n  ECE improvement:")
    print(f"    v2: {ece_v2['ece_pct']:.2f}%  (current production)")
    print(f"    v3: {ece_v3['ece_pct']:.2f}%  (projected with v3 changes)")
    print(f"    d:  -{ece_v2['ece_pct'] - ece_v3['ece_pct']:.2f}pp reduction")
    print(f"\n  conf >= 80 usage:")
    print(f"    v2: {len(v2_high_conf)} days  ({len(v2_high_conf)/len(tradeable)*100:.1f}%)")
    print(f"    v3: {len(v3_high_conf)} days  ({len(v3_high_conf)/len(tradeable)*100:.1f}%)")
    print(f"\n  conf = 95 usage:")
    print(f"    v2: {len(v2_at_95)} days  ({len(v2_at_95)/len(tradeable)*100:.1f}%)")
    print(f"    v3: {len(v3_at_95)} days  ({len(v3_at_95)/len(tradeable)*100:.1f}%)")
    print(f"\n  Days where v3 changes confidence: {len(changed_days)}")
    print(f"\n  Bucket breakdown (v2 -> v3):")
    print(f"  {'Bucket':<12} {'v2 days':>8} {'v2 acc%':>8} {'v2 exp%':>8} {'v2 gap':>8}  |  {'v3 days':>8} {'v3 acc%':>8} {'v3 exp%':>8} {'v3 gap':>8}")
    print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*8} {'-'*8}  |  {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    for lo, hi, name in CONF_BUCKETS:
        b2 = ece_v2["buckets"][name]
        b3 = ece_v3["buckets"][name]
        def fmt(b):
            if b["n"] == 0:
                return f"{'0':>8} {'n/a':>8} {'n/a':>8} {'n/a':>8}"
            return (f"{b['n']:>8} {b['accuracy_pct']:>8.1f} {b['expected_pct']:>8.1f} "
                    f"{b['gap_pp']:>+8.1f}")
        print(f"  {name:<12} {fmt(b2)}  |  {fmt(b3)}")
    print(f"\n  Changed days detail:")
    for r in sorted(changed_days, key=lambda x: x["date"]):
        flag = "CORRECT" if r["correct"] else "WRONG  "
        delta_str = f"{r['v3_delta']:+d}"
        print(f"    {r['date']}  {flag}  v2={r['v2_conf']:2d} -> v3={r['v3_conf']:2d}  "
              f"({delta_str})  agree={r['specialist_agreement']}/4  "
              f"battle={r['battle_grade']:<12}  {r['consensus_strength']}")
    print(f"\n{'='*70}\n")

    # ── Write output ─────────────────────────────────────────────────────────
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"  Written: {OUT_PATH}")


if __name__ == "__main__":
    main()

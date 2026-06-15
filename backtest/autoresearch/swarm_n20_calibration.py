"""
swarm_n20_calibration.py — UNTESTED/HELD battle-grade penalty calibration
=========================================================================
Runs after the N20 gate is met (≥20 tradeable UNTESTED days in aggregate.json).

Purpose
-------
The v5 swarm formula applies these empirical penalties to raw confidence:
  UNTESTED battle_grade: -25   (empirical accuracy 44.4%, implied conf = 40)
  HELD     battle_grade: -20   (empirical accuracy 50.0%, implied conf = 45)
  BROKE / TESTED_MIXED:   0   (empirical accuracy 77-86%)

This script re-measures actual WR for each battle_grade bucket, computes
Expected Calibration Error (ECE), and recommends updated penalties if the
observed accuracy has drifted > DRIFT_THRESHOLD from the 65-day baseline.

Usage
-----
    python backtest/autoresearch/swarm_n20_calibration.py
    python backtest/autoresearch/swarm_n20_calibration.py --min-n 20

Outputs
-------
  analysis/swarm-tuning/n20-calibration-{date}.json   — machine-readable
  analysis/swarm-tuning/n20-calibration-{date}.md     — human summary
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import date as _date
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
AGGREGATE_JSON = ROOT / "analysis" / "swarm-benchmark" / "aggregate.json"
OUT_DIR = ROOT / "analysis" / "swarm-tuning"

# ---------------------------------------------------------------------------
# Constants from v5 formula
# ---------------------------------------------------------------------------
V5_PENALTIES: dict[str, int] = {
    "UNTESTED": -15,   # v5.1 update (was -25; calibrated 2026-05-20)
    "HELD": -20,
    "BROKE": 0,
    "TESTED_MIXED": 0,
}

# "Base confidence before battle-grade adjustment" in a typical swarm day
# (used for implied confidence calculation: implied = 65 + penalty)
V5_TYPICAL_BASE: int = 65

# If observed WR differs from implied confidence by more than this, recommend update
DRIFT_THRESHOLD: float = 5.0   # percentage points

# Minimum N to report a bucket's accuracy (below this → NOT ENOUGH DATA)
MIN_BUCKET_N: int = 5

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
class DayRecord(NamedTuple):
    date: str
    swarm_bias: str
    swarm_conf: int
    actual_bias: str
    actual_move: float
    direction_grade: str
    battle_grade: str


def _load_days(path: Path) -> list[DayRecord]:
    with open(path, encoding="utf-8") as fh:
        agg = json.load(fh)
    days = []
    for d in agg.get("per_day", []):
        days.append(DayRecord(
            date=d.get("date", ""),
            swarm_bias=d.get("swarm_bias", ""),
            swarm_conf=int(d.get("swarm_conf", 0)),
            actual_bias=d.get("actual_bias", ""),
            actual_move=float(d.get("actual_move", 0.0)),
            direction_grade=d.get("direction_grade", ""),
            battle_grade=d.get("battle_grade", ""),
        ))
    return days


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------
def _tradeable(day: DayRecord) -> bool:
    return day.direction_grade in ("CORRECT", "WRONG")


def _correct(day: DayRecord) -> bool:
    return day.direction_grade == "CORRECT"


def _bucket_stats(days: list[DayRecord]) -> dict[str, dict]:
    """Per-battle_grade: n, n_correct, wr_pct, implied_conf, mean_actual_conf.

    Two drift measures are reported:
    - drift_pp (base-65 drift): wr_pct - (V5_TYPICAL_BASE + penalty).
      Valid for UNTESTED/HELD where specialists may disagree → actual base ≈ 65.
      NOT reliable for BROKE/TESTED_MIXED where all-4-agree bonus inflates the
      actual formula output above 65.
    - drift_actual_pp: wr_pct - mean_actual_conf (uses real swarm_conf from output).
      Corrects for the base-65 assumption — directly measures whether the formula's
      final output confidence matches the observed win rate.
      This is the calibration measure to use for BROKE/TESTED_MIXED (N20 gate met).
    """
    buckets: dict[str, list[DayRecord]] = defaultdict(list)
    for d in days:
        if _tradeable(d):
            buckets[d.battle_grade].append(d)

    out = {}
    for grade, ds in sorted(buckets.items()):
        n = len(ds)
        n_correct = sum(1 for d in ds if _correct(d))
        wr_pct = 100.0 * n_correct / n if n > 0 else float("nan")
        penalty = V5_PENALTIES.get(grade, 0)
        implied_conf = V5_TYPICAL_BASE + penalty
        mean_actual = sum(d.swarm_conf for d in ds) / n if n > 0 else float("nan")
        enough = n >= MIN_BUCKET_N
        out[grade] = {
            "n": n,
            "n_correct": n_correct,
            "wr_pct": round(wr_pct, 1),
            "v5_penalty": penalty,
            "v5_implied_conf": implied_conf,
            # base-65 drift (legacy — reliable for UNTESTED/HELD, NOT for BROKE/TESTED_MIXED):
            "drift_pp": round(wr_pct - implied_conf, 1) if enough else None,
            # actual-conf drift (corrects for base-65 assumption, valid for all grades):
            "mean_actual_conf": round(mean_actual, 1) if enough else None,
            "drift_actual_pp": round(wr_pct - mean_actual, 1) if enough else None,
        }
    return out


def _ece_on_tradeable(days: list[DayRecord], n_bins: int = 5) -> float:
    """Expected Calibration Error — mean |conf - accuracy| weighted by bin size."""
    tradeable = [d for d in days if _tradeable(d)]
    if not tradeable:
        return float("nan")

    # Sort by swarm_conf, split into n_bins equal-ish buckets
    tradeable.sort(key=lambda d: d.swarm_conf)
    bin_size = math.ceil(len(tradeable) / n_bins)
    ece = 0.0
    total = len(tradeable)

    for i in range(0, total, bin_size):
        chunk = tradeable[i : i + bin_size]
        if not chunk:
            continue
        avg_conf = sum(d.swarm_conf for d in chunk) / len(chunk) / 100.0  # 0-1 scale
        wr = sum(1 for d in chunk if _correct(d)) / len(chunk)
        ece += abs(avg_conf - wr) * len(chunk) / total

    return round(ece * 100, 2)  # return as pct


def _recommend_penalty(grade: str, stats: dict) -> str | None:
    """Return a recommended penalty update if drift > threshold, else None.

    For BROKE and TESTED_MIXED: use drift_actual_pp (actual formula output vs WR)
    instead of drift_pp (base-65 implied vs WR) — the base-65 assumption is invalid
    for high-specialist-agreement grades where the formula naturally outputs > 65.

    For UNTESTED and HELD: use drift_pp (base-65 implied) per the N20-gate calibration
    model (these grades see more specialist disagreement, actual base ≈ 65).
    """
    # Pick the right drift measure per grade
    use_actual_drift = grade in ("BROKE", "TESTED_MIXED")
    drift_key = "drift_actual_pp" if use_actual_drift else "drift_pp"

    if stats.get(drift_key) is None:
        return None
    drift = stats[drift_key]
    if abs(drift) <= DRIFT_THRESHOLD:
        return None  # penalty is well-calibrated

    if use_actual_drift:
        # Recommend a formula adjustment: add a penalty/boost so that
        # actual_conf + adjustment ≈ observed WR.
        # adjustment = WR - mean_actual_conf (positive = boost, negative = penalty)
        mean_conf = stats.get("mean_actual_conf", V5_TYPICAL_BASE)
        adjustment = round(stats["wr_pct"] - mean_conf)
        adjustment_rounded = round(adjustment / 5) * 5
        current = V5_PENALTIES.get(grade, 0)
        new_penalty = current + adjustment_rounded
        return (
            f"current_adjustment={current} -> recommend {new_penalty} "
            f"(drift_actual={drift:+.1f}pp, "
            f"mean_actual_conf={stats['mean_actual_conf']:.1f}% vs WR={stats['wr_pct']}%)"
            f"  [NOTE: base-65 assumption invalid for {grade} — use actual-conf drift]"
        )
    else:
        # Legacy base-65 path for UNTESTED/HELD
        new_implied = round(stats["wr_pct"])
        new_penalty = new_implied - V5_TYPICAL_BASE
        new_penalty_rounded = round(new_penalty / 5) * 5
        return f"{V5_PENALTIES.get(grade, 0)} -> {new_penalty_rounded} (drift={drift:+.1f}pp, observed WR={stats['wr_pct']}%)"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run(min_n: int = 20) -> dict:
    days = _load_days(AGGREGATE_JSON)
    tradeable = [d for d in days if _tradeable(d)]
    untested_tradeable = [d for d in tradeable if d.battle_grade == "UNTESTED"]

    print(f"[n20-cal] Loaded {len(days)} graded days from aggregate.json")
    print(f"[n20-cal] Tradeable days (CORRECT|WRONG): {len(tradeable)}")
    print(f"[n20-cal] UNTESTED tradeable: {len(untested_tradeable)}")

    if len(untested_tradeable) < min_n:
        print(f"[n20-cal] N20 gate NOT met ({len(untested_tradeable)} < {min_n}). Calibration deferred.")
        return {
            "gate_met": False,
            "n_untested_tradeable": len(untested_tradeable),
            "min_n": min_n,
        }

    print(f"[n20-cal] N20 gate MET ({len(untested_tradeable)} >= {min_n}). Running calibration.")

    bucket_stats = _bucket_stats(days)
    ece = _ece_on_tradeable(days)
    ece_untested = _ece_on_tradeable(untested_tradeable)

    recommendations: dict[str, str] = {}
    for grade, stats in bucket_stats.items():
        rec = _recommend_penalty(grade, stats)
        if rec:
            recommendations[grade] = rec

    verdict = "CALIBRATION_VALID" if not recommendations else "PENALTY_UPDATE_RECOMMENDED"

    result = {
        "gate_met": True,
        "n_untested_tradeable": len(untested_tradeable),
        "n_tradeable_total": len(tradeable),
        "n_days_total": len(days),
        "ece_all_tradeable_pct": ece,
        "ece_untested_only_pct": ece_untested,
        "drift_threshold_pp": DRIFT_THRESHOLD,
        "bucket_stats": bucket_stats,
        "recommendations": recommendations,
        "verdict": verdict,
        "v5_penalties_current": V5_PENALTIES,
    }

    # Print per-bucket summary (two drift views)
    print("\n[n20-cal] Per-battle_grade calibration (base-65 drift | actual-conf drift):")
    print(f"  {'Grade':<15} {'N':>4} {'WR%':>6} {'Implied65':>9} {'Drift65':>8}"
          f" {'ActConf':>8} {'DriftAct':>9}  Rec")
    for grade, stats in sorted(bucket_stats.items()):
        rec = recommendations.get(grade, "OK")
        drift65 = f"{stats['drift_pp']:+.1f}pp" if stats["drift_pp"] is not None else "N<5"
        act_conf = f"{stats['mean_actual_conf']:.1f}" if stats.get("mean_actual_conf") is not None else "N<5"
        drift_act = f"{stats['drift_actual_pp']:+.1f}pp" if stats.get("drift_actual_pp") is not None else "N<5"
        print(f"  {grade:<15} {stats['n']:>4} {stats['wr_pct']:>6.1f} {stats['v5_implied_conf']:>9}"
              f" {drift65:>8} {act_conf:>8} {drift_act:>9}  {rec}")
    print(f"  {'':15}  (base-65 drift = WR - implied_conf)  (actual drift = WR - mean_formula_output)")

    print(f"\n[n20-cal] ECE (all tradeable): {ece}%")
    print(f"[n20-cal] ECE (UNTESTED only):  {ece_untested}%")
    print(f"\n[n20-cal] Verdict: {verdict}")
    if recommendations:
        print("[n20-cal] Recommended penalty updates:")
        for grade, rec in recommendations.items():
            note = ""
            if grade in ("BROKE", "TESTED_MIXED"):
                note = "  [caveat: base-conf not fixed at 65 on high-vote days; needs retrograde sim]"
            print(f"  {grade}: {rec}{note}")
        print()
        print("[n20-cal] NOTE: BROKE/TESTED_MIXED drift may be an artifact of the fixed-base-65")
        print("         assumption. On those days specialists vote higher, so raw base > 65.")
        print("         Use swarm_factor_regression.py + retrograde sim to validate before")
        print("         modifying synthesis_agent.md Step 5 for those buckets.")
        print()
        print("[n20-cal] PRIMARY N20 GATE FINDING:")
        for grade in ("UNTESTED", "HELD"):
            if grade in bucket_stats:
                s = bucket_stats[grade]
                status = "CALIBRATED" if grade not in recommendations else "UPDATE-NEEDED"
                print(f"  {grade}: N={s['n']}, WR={s['wr_pct']}%, implied={s['v5_implied_conf']}, drift={s['drift_pp']:+.1f}pp -> {status}")
    else:
        print("[n20-cal] All penalties within drift tolerance — no changes needed.")

    return result


def _write_outputs(result: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    today = _date.today().isoformat()
    json_path = OUT_DIR / f"n20-calibration-{today}.json"
    md_path = OUT_DIR / f"n20-calibration-{today}.md"

    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    print(f"\n[n20-cal] JSON -> {json_path}")

    # Build markdown
    lines = [
        f"# Swarm N20 Calibration Report — {today}",
        "",
        "## Gate Status",
        f"- **N_untested_tradeable:** {result['n_untested_tradeable']}",
        f"- **Gate threshold:** {result.get('min_n', 20)}",
        f"- **Gate met:** {'YES' if result['gate_met'] else 'NO'}",
        "",
    ]

    if result["gate_met"]:
        lines += [
            "## Calibration Metrics",
            f"| Metric | Value |",
            f"|---|---|",
            f"| ECE (all tradeable days) | {result['ece_all_tradeable_pct']}% |",
            f"| ECE (UNTESTED days only) | {result['ece_untested_only_pct']}% |",
            f"| Drift threshold | ±{result['drift_threshold_pp']}pp |",
            "",
            "## Per-Bucket Accuracy",
            "| Battle Grade | N | WR% | Implied65 | Drift(65) | ActConf | Drift(Actual) | Recommendation |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for grade, stats in sorted(result["bucket_stats"].items()):
            drift65 = f"{stats['drift_pp']:+.1f}pp" if stats["drift_pp"] is not None else "N<5"
            act_conf = f"{stats['mean_actual_conf']:.1f}" if stats.get("mean_actual_conf") is not None else "N<5"
            drift_act = f"{stats['drift_actual_pp']:+.1f}pp" if stats.get("drift_actual_pp") is not None else "N<5"
            rec = result["recommendations"].get(grade, "✅ OK")
            lines.append(
                f"| {grade} | {stats['n']} | {stats['wr_pct']}% | {stats['v5_implied_conf']}"
                f" | {drift65} | {act_conf} | {drift_act} | {rec} |"
            )
        lines += [
            "",
            "> **Drift(65):** WR% minus base-65-implied confidence. Valid for UNTESTED/HELD.",
            "> **Drift(Actual):** WR% minus mean formula output. Corrects for base-65 assumption on",
            "> BROKE/TESTED_MIXED (where 4/4-agree bonus inflates base above 65). Use this measure",
            "> to diagnose whether formula needs a penalty/boost for high-agreement battle grades.",
        ]
        lines += [
            "",
            "## Verdict",
            f"**{result['verdict']}**",
            "",
        ]

        if result["recommendations"]:
            lines += [
                "## Required Updates to `synthesis_agent.md` Step 5",
                "```",
            ]
            for grade, rec in result["recommendations"].items():
                lines.append(f"battle_grade == '{grade}': {rec}")
            lines += ["```", ""]

        lines += [
            "## Method",
            "- Filtered `analysis/swarm-benchmark/aggregate.json` to tradeable days",
            "  (direction_grade in CORRECT|WRONG).",
            "- Grouped by battle_grade, computed observed WR per bucket.",
            "- v5 implied confidence = 65 (typical base) + penalty.",
            "- Drift = observed WR − v5 implied confidence.",
            "- Penalty update recommended when |drift| > 5pp and bucket N ≥ 5.",
            "- ECE = mean |avg_conf − WR| weighted by bin size (5 equal bins).",
        ]

    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"[n20-cal] MD  -> {md_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Swarm N20 penalty calibration")
    parser.add_argument("--min-n", type=int, default=20,
                        help="Minimum UNTESTED tradeable days for gate (default: 20)")
    parser.add_argument("--no-write", action="store_true",
                        help="Print only, do not write output files")
    args = parser.parse_args()

    result = run(min_n=args.min_n)
    if not args.no_write:
        _write_outputs(result)
    sys.exit(0 if result.get("gate_met") else 1)

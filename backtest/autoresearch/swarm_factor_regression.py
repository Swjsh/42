"""
swarm_factor_regression.py — Per-factor regression on swarm replay data.

Goal: identify which of the 5 specialist inputs (technical, macro, level_thesis,
internals, validator confidence) actually predict next-bar direction. Find which
confidence bands are over-calibrated vs under-calibrated.

Output: analysis/swarm-factor-regression-{date}.json + summary printed to stdout.

Usage:
    python backtest/autoresearch/swarm_factor_regression.py
"""

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
REPLAY_BASE = ROOT / "analysis" / "swarm-benchmark"
AGGREGATE_PATH = ROOT / "analysis" / "swarm-benchmark" / "aggregate.json"
OUTPUT_DIR = ROOT / "analysis"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class DayRecord:
    date: str
    # swarm overall
    swarm_bias: str           # bullish / bearish
    swarm_conf: int           # 0-100
    # per-factor confidence (0.0-1.0), None if not available
    technical_conf: Optional[float]
    technical_bias: Optional[str]
    macro_conf: Optional[float]
    macro_bias: Optional[str]
    level_conf: Optional[float]
    level_bias: Optional[str]
    internals_conf: Optional[float]
    internals_bias: Optional[str]
    # validator doesn't give a numeric confidence in the same way
    # but the validator_output.json does have a confidence field
    validator_conf: Optional[float]
    # outcome
    direction_grade: str      # CORRECT / WRONG / ABSTAIN_ACTUAL / ABSTAIN_SWARM
    actual_move: float
    actual_bias: str          # bullish / bearish / no_trade


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_all_records() -> list[DayRecord]:
    aggregate = _load_json(AGGREGATE_PATH)
    if not aggregate:
        print("ERROR: aggregate.json not found", file=sys.stderr)
        sys.exit(1)

    # Build lookup: date -> per_day entry
    per_day_lookup: dict[str, dict] = {}
    for entry in aggregate.get("per_day", []):
        per_day_lookup[entry["date"]] = entry

    records: list[DayRecord] = []

    for replay_dir in sorted(REPLAY_BASE.iterdir()):
        if not replay_dir.is_dir() or not replay_dir.name.startswith("replay-"):
            continue

        # Extract date from dir name: replay-2026-02-09-0600
        parts = replay_dir.name.split("-")
        if len(parts) < 5:
            continue
        date_str = f"{parts[1]}-{parts[2]}-{parts[3]}"

        swarm = _load_json(replay_dir / "swarm_output.json")
        if not swarm:
            continue

        validator_out = _load_json(replay_dir / "validator_output.json")

        # Per-factor from agent_summaries
        summaries = swarm.get("agent_summaries", {})

        def _conf(agent: str) -> Optional[float]:
            s = summaries.get(agent, {})
            c = s.get("confidence")
            if c is None or c == 0.0 and s.get("bias") == "no_data":
                return None
            return float(c)

        def _bias(agent: str) -> Optional[str]:
            s = summaries.get(agent, {})
            b = s.get("bias")
            if b in (None, "no_data"):
                return None
            return b

        validator_conf: Optional[float] = None
        if validator_out:
            vc = validator_out.get("confidence")
            if vc is not None:
                validator_conf = float(vc)

        # Outcome from aggregate
        agg_entry = per_day_lookup.get(date_str)
        if not agg_entry:
            # Day is in replay but not in aggregate (future or missing grade)
            continue

        records.append(DayRecord(
            date=date_str,
            swarm_bias=swarm.get("consensus_bias", ""),
            swarm_conf=swarm.get("swarm_confidence", 0),
            technical_conf=_conf("technical"),
            technical_bias=_bias("technical"),
            macro_conf=_conf("macro"),
            macro_bias=_bias("macro"),
            level_conf=_conf("level_thesis"),
            level_bias=_bias("level_thesis"),
            internals_conf=_conf("internals"),
            internals_bias=_bias("internals"),
            validator_conf=validator_conf,
            direction_grade=agg_entry.get("direction_grade", ""),
            actual_move=agg_entry.get("actual_move", 0.0),
            actual_bias=agg_entry.get("actual_bias", ""),
        ))

    return sorted(records, key=lambda r: r.date)


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def grade_to_outcome(grade: str) -> Optional[int]:
    """Return 1 (correct), 0 (wrong), None (abstain)."""
    if grade == "CORRECT":
        return 1
    if grade == "WRONG":
        return 0
    return None  # ABSTAIN


def _win_rate(outcomes: list[int]) -> float:
    if not outcomes:
        return float("nan")
    return sum(outcomes) / len(outcomes) * 100.0


def _mean(values: list[float]) -> float:
    if not values:
        return float("nan")
    return sum(values) / len(values)


def _pearson(xs: list[float], ys: list[float]) -> float:
    """Simple Pearson r correlation."""
    n = len(xs)
    if n < 2:
        return float("nan")
    mx, my = _mean(xs), _mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs)
    dy = sum((y - my) ** 2 for y in ys)
    denom = (dx * dy) ** 0.5
    if denom == 0:
        return float("nan")
    return num / denom


def analyze_factor(
    records: list[DayRecord],
    conf_getter,     # callable: record -> Optional[float]
    bias_getter,     # callable: record -> Optional[str]
    name: str,
) -> dict:
    """Full analysis for one specialist factor."""

    # Only include records where factor has data and swarm has a direction
    eligible = [
        r for r in records
        if conf_getter(r) is not None
        and grade_to_outcome(r.direction_grade) is not None
    ]

    if not eligible:
        return {"factor": name, "n": 0, "error": "no_data"}

    # --- Agreement with swarm consensus ---
    agreement_n = sum(
        1 for r in eligible
        if bias_getter(r) is not None and bias_getter(r) == r.swarm_bias
    )
    agreement_rate = agreement_n / len(eligible) * 100

    # --- Factor-level win rate (when factor agreed with swarm) ---
    agreed = [r for r in eligible if bias_getter(r) == r.swarm_bias]
    disagreed = [r for r in eligible if bias_getter(r) is not None and bias_getter(r) != r.swarm_bias]

    agreed_outcomes = [grade_to_outcome(r.direction_grade) for r in agreed]
    agreed_outcomes = [o for o in agreed_outcomes if o is not None]

    disagreed_outcomes = [grade_to_outcome(r.direction_grade) for r in disagreed]
    disagreed_outcomes = [o for o in disagreed_outcomes if o is not None]

    wr_when_agreed = _win_rate(agreed_outcomes)
    wr_when_disagreed = _win_rate(disagreed_outcomes)

    # --- Confidence vs correctness correlation ---
    confs = [conf_getter(r) for r in eligible]
    outcomes = [grade_to_outcome(r.direction_grade) for r in eligible]
    corr = _pearson(confs, outcomes)

    # --- Confidence band analysis ---
    bands = {
        "lt50": (0.0, 0.50),
        "50_60": (0.50, 0.60),
        "60_70": (0.60, 0.70),
        "70_80": (0.70, 0.80),
        "80_90": (0.80, 0.90),
        "ge90": (0.90, 1.01),
    }
    band_stats: dict[str, dict] = {}
    for label, (lo, hi) in bands.items():
        band_records = [r for r in eligible if lo <= conf_getter(r) < hi]
        band_outcomes = [grade_to_outcome(r.direction_grade) for r in band_records]
        band_outcomes_clean = [o for o in band_outcomes if o is not None]
        band_stats[label] = {
            "n": len(band_records),
            "wr_pct": round(_win_rate(band_outcomes_clean), 1),
            "avg_move": round(_mean([abs(r.actual_move) for r in band_records]), 2),
        }

    # --- When this factor is the SOLE dissenter ---
    sole_dissent_correct = []
    for r in eligible:
        if bias_getter(r) is None or bias_getter(r) == r.swarm_bias:
            continue
        # Count how many other agents agreed with the swarm
        # (approximation — we can't easily count all agents per record here;
        # use vote_counts which isn't stored per-record... skip this for now)

    return {
        "factor": name,
        "n": len(eligible),
        "agreement_rate_pct": round(agreement_rate, 1),
        "wr_when_agreed_pct": round(wr_when_agreed, 1),
        "wr_when_disagreed_pct": round(wr_when_disagreed, 1) if disagreed_outcomes else None,
        "n_disagreed": len(disagreed_outcomes),
        "conf_outcome_pearson_r": round(corr, 3),
        "avg_confidence": round(_mean(confs), 3),
        "confidence_bands": band_stats,
    }


def analyze_swarm_confidence_bands(records: list[DayRecord]) -> dict:
    """Overall swarm_conf band analysis (the headline calibration check)."""
    eligible = [r for r in records if grade_to_outcome(r.direction_grade) is not None]

    bands = {
        "lt50_abstain": (0, 50),
        "50_60": (50, 60),
        "60_70": (60, 70),
        "70_80": (70, 80),
        "80_90": (80, 90),
        "ge90": (90, 101),
    }
    result: dict[str, dict] = {}
    for label, (lo, hi) in bands.items():
        band_r = [r for r in eligible if lo <= r.swarm_conf < hi]
        outcomes = [grade_to_outcome(r.direction_grade) for r in band_r]
        clean = [o for o in outcomes if o is not None]
        dates = [r.date for r in band_r]
        result[label] = {
            "n": len(band_r),
            "wr_pct": round(_win_rate(clean), 1),
            "avg_move_abs": round(_mean([abs(r.actual_move) for r in band_r]), 2),
            "dates": dates,
        }
    return result


def find_best_predictor_combo(records: list[DayRecord]) -> dict:
    """
    Simple logistic-regression-equivalent: check which factor(s)
    most reduce error when the swarm is WRONG.

    Strategy: for each WRONG day, look at which factor(s) had the opposite bias
    (i.e., dissented from the losing consensus). Those factors are early-warning.
    """
    wrong_days = [r for r in records if r.direction_grade == "WRONG"]

    factor_dissent: dict[str, int] = {
        "technical": 0,
        "macro": 0,
        "level_thesis": 0,
        "internals": 0,
    }
    factor_getters = {
        "technical": lambda r: r.technical_bias,
        "macro": lambda r: r.macro_bias,
        "level_thesis": lambda r: r.level_bias,
        "internals": lambda r: r.internals_bias,
    }

    for r in wrong_days:
        for fname, getter in factor_getters.items():
            b = getter(r)
            if b is not None and b != r.swarm_bias and b not in ("no_trade",):
                factor_dissent[fname] += 1

    n_wrong = len(wrong_days)
    dissent_rates = {
        k: {
            "n_dissented_on_wrong_days": v,
            "dissent_rate_pct": round(v / n_wrong * 100, 1) if n_wrong else 0.0,
        }
        for k, v in factor_dissent.items()
    }

    # Also: which factor, when it agrees with the swarm, most improves WR
    return {
        "n_wrong_days": n_wrong,
        "factor_dissent_on_wrong_days": dissent_rates,
        "interpretation": (
            "A factor with high dissent-rate-pct on wrong days is a leading counter-signal "
            "— when it disagrees with the swarm, the swarm is more often wrong. "
            "This factor should have its weight INCREASED in the synthesis formula."
        ),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("Loading all replay records...")
    records = load_all_records()
    print(f"  Loaded {len(records)} records with per-factor data")

    # Overall swarm calibration
    swarm_bands = analyze_swarm_confidence_bands(records)

    # Per-factor analysis
    factors = [
        ("technical",    lambda r: r.technical_conf,  lambda r: r.technical_bias),
        ("macro",        lambda r: r.macro_conf,       lambda r: r.macro_bias),
        ("level_thesis", lambda r: r.level_conf,       lambda r: r.level_bias),
        ("internals",    lambda r: r.internals_conf,   lambda r: r.internals_bias),
    ]
    factor_results = []
    for name, cg, bg in factors:
        res = analyze_factor(records, cg, bg, name)
        factor_results.append(res)
        print(f"\n  [{name}] n={res['n']} | agree_rate={res.get('agreement_rate_pct')}% "
              f"| WR_agreed={res.get('wr_when_agreed_pct')}% "
              f"| WR_disagreed={res.get('wr_when_disagreed_pct')}% "
              f"| pearson_r={res.get('conf_outcome_pearson_r')}")
        bands = res.get("confidence_bands", {})
        for b, s in bands.items():
            if s["n"] > 0:
                print(f"    {b}: n={s['n']} WR={s['wr_pct']}%")

    predictor_combo = find_best_predictor_combo(records)

    # Print swarm bands
    print("\n--- SWARM OVERALL CONFIDENCE BANDS ---")
    for label, s in swarm_bands.items():
        print(f"  [{label}] n={s['n']} WR={s['wr_pct']}% avg_move={s['avg_move_abs']}")

    # Build output
    from datetime import date
    today = date.today().isoformat()
    output = {
        "generated_at": today,
        "n_records": len(records),
        "swarm_confidence_bands": swarm_bands,
        "per_factor": factor_results,
        "wrong_day_dissent_analysis": predictor_combo,
        "findings": [],  # populated below
    }

    # Generate findings
    findings = []

    # Finding 1: swarm confidence calibration
    band_60_70 = swarm_bands.get("60_70", {})
    band_ge90 = swarm_bands.get("ge90", {})
    if band_60_70.get("n", 0) > 0 and band_ge90.get("n", 0) > 0:
        wr_60_70 = band_60_70["wr_pct"]
        wr_ge90 = band_ge90["wr_pct"]
        findings.append({
            "id": "F1_OVERCONFIDENCE",
            "title": "Swarm overconfidence at high end",
            "observation": f"60-70 band WR={wr_60_70}% vs ≥90 band WR={wr_ge90}% (n={band_ge90['n']})",
            "delta_pp": round(wr_60_70 - wr_ge90, 1),
            "recommendation": (
                "High swarm_conf (≥90) is NOT more accurate. "
                "Apply a 15-point cap reduction on the ≥90 tier "
                "or require 4-of-4 specialist agreement before awarding ≥90."
            ) if wr_ge90 < wr_60_70 else "High-conf tier is working — no change needed."
        })

    # Finding 2: best factor by pearson_r
    scored = [(r["factor"], r.get("conf_outcome_pearson_r", 0) or 0) for r in factor_results]
    scored.sort(key=lambda x: x[1], reverse=True)
    findings.append({
        "id": "F2_BEST_PREDICTOR",
        "title": "Most predictive individual factor by Pearson r",
        "ranking": scored,
        "recommendation": (
            f"Increase synthesis weight for '{scored[0][0]}' (r={scored[0][1]:.3f}). "
            f"De-emphasize '{scored[-1][0]}' (r={scored[-1][1]:.3f}) — weakest linear signal."
        )
    })

    # Finding 3: internals dissent analysis
    internals_dissent = predictor_combo["factor_dissent_on_wrong_days"].get("internals", {})
    findings.append({
        "id": "F3_INTERNALS_DISSENT",
        "title": "Internals dissent as early warning on wrong days",
        "dissent_rate_on_wrong_days_pct": internals_dissent.get("dissent_rate_pct"),
        "n_wrong": predictor_combo["n_wrong_days"],
        "recommendation": (
            "If internals dissent rate on wrong days > 40%, "
            "treat internals no_trade/opposite vote as a veto: reduce swarm_conf by 20 points."
        )
    })

    output["findings"] = findings

    # Write output
    out_path = OUTPUT_DIR / f"swarm-factor-regression-{today}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"\nOutput written to: {out_path}")

    # Print summary findings
    print("\n=== FINDINGS ===")
    for f_item in findings:
        print(f"\n[{f_item['id']}] {f_item['title']}")
        for k, v in f_item.items():
            if k not in ("id", "title"):
                print(f"  {k}: {v}")


if __name__ == "__main__":
    main()

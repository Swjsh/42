"""
SWARM-CONFIDENCE-CALIBRATION
Analyzes the relationship between swarm_confidence score and actual accuracy.
Reads all graded replay dirs + aggregate.json, computes calibration curves,
and surfaces actionable recommendations for the synthesis agent.

Usage:
    python automation/swarm/replay/swarm_confidence_calibration.py
    python automation/swarm/replay/swarm_confidence_calibration.py --output-dir analysis/swarm-benchmark
"""

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BENCHMARK_DIR = ROOT / "analysis" / "swarm-benchmark"


# ── data loading ────────────────────────────────────────────────────────────

def load_per_day_records() -> list[dict]:
    """
    Load per-day grade records from aggregate.json (populated by grader_replay.py).
    Falls back to scanning individual replay dirs if aggregate is incomplete.
    """
    agg_path = BENCHMARK_DIR / "aggregate.json"
    if agg_path.exists():
        agg = json.loads(agg_path.read_text())
        per_day = agg.get("per_day", [])
        if per_day:
            return per_day

    # Fallback: scan individual replay dirs
    records = []
    for d in sorted(BENCHMARK_DIR.iterdir()):
        if not d.is_dir() or not d.name.startswith("replay-"):
            continue
        grade_file = d / "grade.json"
        if not grade_file.exists():
            continue
        try:
            g = json.loads(grade_file.read_text())
            swarm = g.get("swarm", {})
            grades = g.get("grades", {})
            direction = grades.get("direction", {})
            records.append({
                "date": g.get("date"),
                "swarm_bias": swarm.get("consensus_bias"),
                "swarm_conf": swarm.get("swarm_confidence", 50),
                "actual_bias": g.get("actual", {}).get("actual_bias"),
                "actual_move": g.get("actual", {}).get("move_dollars", 0.0),
                "direction_grade": direction.get("grade", "UNKNOWN"),
            })
        except Exception as e:
            print(f"  Warning: could not parse {grade_file}: {e}", file=sys.stderr)

    return sorted(records, key=lambda r: r.get("date", ""))


# ── calibration analysis ─────────────────────────────────────────────────────

def compute_calibration(records: list[dict]) -> dict:
    """
    Computes:
    - Overall direction accuracy
    - Per-confidence-bucket accuracy (sorted by conf value)
    - Confidence inflation metric (how often max conf is used)
    - Calibration error (ECE — Expected Calibration Error)
    - Actionable thresholds for trading signal sizing
    """
    # Filter to tradeable records (exclude ABSTAIN_ACTUAL)
    tradeable = [r for r in records if r["direction_grade"] != "ABSTAIN_ACTUAL"]
    correct = [r for r in tradeable if r["direction_grade"] == "CORRECT"]
    wrong = [r for r in tradeable if r["direction_grade"] == "WRONG"]

    overall_n = len(tradeable)
    overall_accuracy = len(correct) / overall_n if overall_n else 0.0

    # --- confidence value distribution ---
    conf_values = [r["swarm_conf"] for r in tradeable]
    conf_counts = defaultdict(int)
    for v in conf_values:
        conf_counts[v] += 1

    max_conf = max(conf_values) if conf_values else 95
    conf_inflation_pct = (conf_counts[max_conf] / overall_n * 100) if overall_n else 0.0

    # --- per-bucket accuracy ---
    # Buckets: [0-39], [40-59], [60-74], [75-89], [90-100]
    bucket_defs = [
        ("low (0-39)", 0, 39),
        ("medium (40-59)", 40, 59),
        ("high (60-74)", 60, 74),
        ("very_high (75-89)", 75, 89),
        ("max (90-100)", 90, 100),
    ]
    buckets = []
    for label, lo, hi in bucket_defs:
        bucket_recs = [r for r in tradeable if lo <= r["swarm_conf"] <= hi]
        n = len(bucket_recs)
        n_correct = sum(1 for r in bucket_recs if r["direction_grade"] == "CORRECT")
        accuracy = n_correct / n if n else None
        mid_conf = (lo + hi) / 2 / 100  # expected accuracy if well-calibrated
        buckets.append({
            "label": label,
            "conf_range": [lo, hi],
            "n_days": n,
            "n_correct": n_correct,
            "accuracy_pct": round(accuracy * 100, 1) if accuracy is not None else None,
            "expected_pct": round(mid_conf * 100, 1),
            "calibration_gap": round((accuracy - mid_conf) * 100, 1) if accuracy is not None else None,
        })

    # --- ECE (Expected Calibration Error) ---
    ece = 0.0
    for b in buckets:
        if b["n_days"] > 0 and b["accuracy_pct"] is not None:
            mid = (b["conf_range"][0] + b["conf_range"][1]) / 2 / 100
            acc = b["accuracy_pct"] / 100
            weight = b["n_days"] / overall_n
            ece += weight * abs(acc - mid)
    ece_pct = round(ece * 100, 2)

    # --- per confidence VALUE analysis (fine-grained) ---
    by_conf = defaultdict(lambda: {"n": 0, "correct": 0, "wrong": 0})
    for r in tradeable:
        c = r["swarm_conf"]
        by_conf[c]["n"] += 1
        if r["direction_grade"] == "CORRECT":
            by_conf[c]["correct"] += 1
        else:
            by_conf[c]["wrong"] += 1

    per_conf_value = []
    for conf_val in sorted(by_conf.keys()):
        d = by_conf[conf_val]
        acc = d["correct"] / d["n"] if d["n"] else None
        per_conf_value.append({
            "conf": conf_val,
            "n": d["n"],
            "correct": d["correct"],
            "wrong": d["wrong"],
            "accuracy_pct": round(acc * 100, 1) if acc is not None else None,
            "expected_pct": conf_val,
        })

    # --- trading signal recommendations ---
    # What conf threshold to use for position sizing?
    # Find highest-conf bucket with accuracy > 65%
    recs = []
    for pv in reversed(per_conf_value):
        if pv["n"] >= 2 and pv["accuracy_pct"] is not None and pv["accuracy_pct"] >= 65:
            recs.append({
                "conf_threshold": pv["conf"],
                "observed_accuracy_pct": pv["accuracy_pct"],
                "n_qualifying_days": pv["n"],
                "recommendation": "use_as_strong_signal",
            })
            break  # first (highest) qualifying

    # --- direction bias check ---
    bull_count = sum(1 for r in tradeable if r["swarm_bias"] == "bullish")
    bear_count = sum(1 for r in tradeable if r["swarm_bias"] == "bearish")
    bull_correct = sum(1 for r in tradeable if r["swarm_bias"] == "bullish" and r["direction_grade"] == "CORRECT")
    bear_correct = sum(1 for r in tradeable if r["swarm_bias"] == "bearish" and r["direction_grade"] == "CORRECT")

    return {
        "n_days_total": len(records),
        "n_days_tradeable": overall_n,
        "n_days_abstain": len(records) - overall_n,
        "overall_accuracy_pct": round(overall_accuracy * 100, 1),
        "expected_calibration_error_pct": ece_pct,
        "confidence_inflation": {
            "max_conf_value": max_conf,
            "days_at_max_conf": conf_counts[max_conf],
            "pct_days_at_max_conf": round(conf_inflation_pct, 1),
            "interpretation": (
                "SEVERE inflation (>50% of days)" if conf_inflation_pct > 50 else
                "moderate inflation (25-50%)" if conf_inflation_pct > 25 else
                "mild inflation (<25%)"
            ),
        },
        "buckets": buckets,
        "per_conf_value": per_conf_value,
        "direction_bias": {
            "bullish_days": bull_count,
            "bullish_accuracy_pct": round(bull_correct / bull_count * 100, 1) if bull_count else None,
            "bearish_days": bear_count,
            "bearish_accuracy_pct": round(bear_correct / bear_count * 100, 1) if bear_count else None,
        },
        "signal_thresholds": recs,
        "conf_distribution": dict(sorted(conf_counts.items())),
    }


# ── report generation ────────────────────────────────────────────────────────

def generate_markdown_report(records: list[dict], calib: dict, output_path: Path) -> str:
    """Generate a human-readable calibration report."""
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ")
    lines = [
        "# SWARM Confidence Calibration Report",
        "",
        f"> Generated: {now} | N={calib['n_days_total']} days graded",
        f"> ECE: {calib['expected_calibration_error_pct']}% | Overall accuracy: {calib['overall_accuracy_pct']}%",
        "",
        "---",
        "",
        "## Summary",
        "",
        f"- **Days graded:** {calib['n_days_total']} ({calib['n_days_tradeable']} tradeable, {calib['n_days_abstain']} abstain/choppy)",
        f"- **Overall direction accuracy:** {calib['overall_accuracy_pct']}%",
        f"- **Expected Calibration Error (ECE):** {calib['expected_calibration_error_pct']}%",
        f"  - ECE < 5% = well-calibrated | ECE 5-15% = moderate miscalibration | ECE > 15% = severe",
        "",
        "## Confidence Inflation",
        "",
    ]

    ci = calib["confidence_inflation"]
    lines += [
        f"- **Max conf value used:** {ci['max_conf_value']}",
        f"- **Days at max conf:** {ci['days_at_max_conf']} ({ci['pct_days_at_max_conf']}% of all days)",
        f"- **Interpretation:** {ci['interpretation']}",
        "",
        "The synthesis agent assigns maximum confidence on too many days. A well-calibrated",
        "model should reserve max confidence for rare, very-clear-signal days (<15% of days).",
        "",
        "**Fix:** In `automation/swarm/prompts/synthesis_agent.md`, add explicit scoring guidance:",
        "- conf=95: all 4 specialists agree + macro confirms + no dissent from validator",
        "- conf=75: 3 of 4 agree + macro neutral",
        "- conf=50: 2 of 4 agree OR meaningful dissent",
        "- conf=25: majority split OR macro contradicts technicals",
        "",
    ]

    # Per-conf-value table
    lines += [
        "## Per-Confidence-Value Accuracy",
        "",
        "| swarm_conf | Days | Correct | Wrong | Actual % | Expected % | Gap |",
        "|------------|------|---------|-------|----------|------------|-----|",
    ]
    for pv in calib["per_conf_value"]:
        acc = f"{pv['accuracy_pct']}%" if pv["accuracy_pct"] is not None else "—"
        gap = f"{pv['accuracy_pct'] - pv['expected_pct']:+.1f}%" if pv["accuracy_pct"] is not None else "—"
        lines.append(
            f"| {pv['conf']} | {pv['n']} | {pv['correct']} | {pv['wrong']} "
            f"| {acc} | {pv['expected_pct']}% | {gap} |"
        )

    lines += [
        "",
        "## Bucket Analysis",
        "",
        "| Bucket | Days | Accuracy | Expected | Gap |",
        "|--------|------|----------|----------|-----|",
    ]
    for b in calib["buckets"]:
        acc = f"{b['accuracy_pct']}%" if b["accuracy_pct"] is not None else "n/a"
        gap = f"{b['calibration_gap']:+.1f}%" if b["calibration_gap"] is not None else "n/a"
        lines.append(
            f"| {b['label']} | {b['n_days']} | {acc} | {b['expected_pct']}% | {gap} |"
        )

    db = calib["direction_bias"]
    lines += [
        "",
        "## Direction Bias",
        "",
        f"- Bullish days: {db['bullish_days']} → accuracy: {db['bullish_accuracy_pct']}%",
        f"- Bearish days: {db['bearish_days']} → accuracy: {db['bearish_accuracy_pct']}%",
        "",
    ]

    # Signal thresholds
    lines += ["## Signal Thresholds (trading recommendations)", ""]
    if calib["signal_thresholds"]:
        for t in calib["signal_thresholds"]:
            lines.append(
                f"- **conf >= {t['conf_threshold']}:** observed {t['observed_accuracy_pct']}% accuracy "
                f"({t['n_qualifying_days']} days) → {t['recommendation'].replace('_', ' ')}"
            )
    else:
        lines.append("- No confidence level shows consistently >65% accuracy yet (need more days)")

    lines += [
        "",
        "## Actionable Synthesis Agent Prompt Updates",
        "",
        "Based on this calibration, the synthesis agent's confidence rubric needs tightening.",
        "File: `automation/swarm/prompts/synthesis_agent.md`",
        "",
        "**Current problem:** swarm assigns conf=95 on too many days; actual accuracy on",
        f"those days is only ~{next((pv['accuracy_pct'] for pv in calib['per_conf_value'] if pv['conf'] == ci['max_conf_value']), '?')}%.",
        "",
        "**Proposed rubric update (add to synthesis prompt):**",
        "",
        "```",
        "CONFIDENCE CALIBRATION RULES (mandatory):",
        "- conf >= 90: ALL of the following must be true:",
        "  * 4/4 specialists agree on direction",
        "  * Macro calendar: no event within 24h (or event is in-line with direction)",
        "  * Validator's devil-advocate found NO structural flaw",
        "  * Technical agent shows EMA ribbon + VWAP + level ALL aligned",
        "  * Reserve this level for <15% of days",
        "- conf 70-89: 3 of 4 specialists agree, macro neutral or aligned",
        "- conf 50-69: 2 of 4 agree OR one meaningful structural concern",
        "- conf 25-49: Mixed signals or clear structural risk",
        "- conf < 25: Use only for near-certain fades or no-trade bias",
        "```",
        "",
        f"*Report generated {now}. Re-run after mega-batch completes (~60+ days) for stable estimates.*",
    ]

    md = "\n".join(lines)
    output_path.write_text(md, encoding="utf-8")
    return md


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SWARM confidence calibration analysis")
    parser.add_argument("--output-dir", default=str(BENCHMARK_DIR), help="Directory for output files")
    parser.add_argument("--quiet", action="store_true", help="Suppress console output")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load records
    records = load_per_day_records()
    if not records:
        print("ERROR: No graded records found. Run swarm_backfill_batch.py first.", file=sys.stderr)
        sys.exit(1)

    if not args.quiet:
        print(f"Loaded {len(records)} graded days")

    # Compute calibration
    calib = compute_calibration(records)
    calib["generated_at"] = datetime.utcnow().isoformat()
    calib["source_days"] = [r.get("date") for r in records]

    # Write JSON
    json_path = out_dir / "calibration-report.json"
    json_path.write_text(json.dumps(calib, indent=2), encoding="utf-8")

    # Write markdown
    md_path = out_dir / "calibration-report.md"
    md = generate_markdown_report(records, calib, md_path)

    if not args.quiet:
        print(f"\n=== CALIBRATION SUMMARY ===")
        print(f"Days graded (tradeable): {calib['n_days_tradeable']}")
        print(f"Overall accuracy: {calib['overall_accuracy_pct']}%")
        print(f"ECE: {calib['expected_calibration_error_pct']}%")
        ci = calib["confidence_inflation"]
        print(f"Confidence inflation: {ci['pct_days_at_max_conf']}% of days at max conf={ci['max_conf_value']}")
        print(f"\nPer-conf accuracy:")
        for pv in calib["per_conf_value"]:
            bar = "=" * (pv["correct"] if pv["correct"] else 0)
            acc = f"{pv['accuracy_pct']}%" if pv["accuracy_pct"] is not None else "n/a"
            expected = f"expected {pv['expected_pct']}%"
            print(f"  conf={pv['conf']:3d}: {pv['n']:2d} days | acc={acc:6s} | {expected} | [{bar}]")
        print(f"\nDirection bias:")
        db = calib["direction_bias"]
        print(f"  Bullish: {db['bullish_days']} days, {db['bullish_accuracy_pct']}% accuracy")
        print(f"  Bearish: {db['bearish_days']} days, {db['bearish_accuracy_pct']}% accuracy")
        print(f"\nOutput: {json_path}")
        print(f"        {md_path}")

    return calib


if __name__ == "__main__":
    main()

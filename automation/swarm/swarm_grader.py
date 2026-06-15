"""
Gamma Swarm Grader — EOD accuracy tracking for the swarm hypothesis engine.

Called by EOD summary pipeline to grade the swarm's daily consensus against
what actually happened. Writes per-day records to analysis/swarm-scorecard.jsonl
and aggregates to analysis/swarm-scorecard.json.

Usage:
    python automation/swarm/swarm_grader.py --date YYYY-MM-DD --actual-bias bullish|bearish|no_trade

The actual_bias argument is derived from EOD summary (did SPY close up or down
meaningfully from the 09:30 open? up > $1.00 = bullish, down > $1.00 = bearish).
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

WORK_DIR = Path(__file__).parent.parent.parent.resolve()
SWARM_DIR = Path(__file__).parent.resolve()
SCORECARD_JSONL = WORK_DIR / "analysis" / "swarm-scorecard.jsonl"
SCORECARD_AGG = WORK_DIR / "analysis" / "swarm-scorecard.json"


def load_swarm_output_for_date(date_str: str) -> dict | None:
    """Load swarm_output.json for a given date (checks generated_at field)."""
    path = SWARM_DIR / "state" / "swarm_output.json"
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        # Verify it's from the right date
        generated_at = data.get("generated_at", "")
        if date_str in generated_at:
            return data
        return None
    except Exception:
        return None


def load_today_bias_for_date(date_str: str) -> dict | None:
    """Load today-bias.json to get the single-agent premarket bias."""
    path = WORK_DIR / "automation" / "state" / "today-bias.json"
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("date") == date_str:
            return data
        return None
    except Exception:
        return None


def grade_bias(consensus: str, actual: str) -> str:
    """Grade swarm consensus against actual direction."""
    if consensus == actual:
        return "CORRECT"
    if consensus == "no_trade":
        return "ABSTAIN"
    if actual == "no_trade":
        return "ABSTAIN_ACTUAL"
    return "WRONG"


def append_scorecard_record(record: dict) -> None:
    """Append one day's grade to the JSONL history."""
    SCORECARD_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with open(SCORECARD_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def rebuild_aggregate() -> None:
    """Rebuild analysis/swarm-scorecard.json from the JSONL history."""
    if not SCORECARD_JSONL.exists():
        return

    records = []
    with open(SCORECARD_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass

    if not records:
        return

    # Overall stats
    graded = [r for r in records if r.get("swarm_grade") not in ("ABSTAIN", "ABSTAIN_ACTUAL", "NO_DATA")]
    n_graded = len(graded)
    n_correct = sum(1 for r in graded if r.get("swarm_grade") == "CORRECT")
    n_wrong = sum(1 for r in graded if r.get("swarm_grade") == "WRONG")

    # Per-agent accuracy (agents that dissented from the consensus)
    agent_votes = {"technical": [], "macro": [], "level_thesis": [], "internals": []}
    for r in records:
        actual = r.get("actual_bias")
        vote_map = r.get("swarm_vote_map", {})
        for agent_name in agent_votes:
            # Find which way this agent voted
            agent_bias = None
            for bias_dir, agents_list in vote_map.items():
                if agent_name in (agents_list or []):
                    agent_bias = bias_dir
                    break
            if agent_bias is not None and actual not in ("no_trade", None):
                agent_votes[agent_name].append(agent_bias == actual)

    agent_accuracy = {}
    for agent_name, results in agent_votes.items():
        if results:
            agent_accuracy[agent_name] = {
                "n_graded": len(results),
                "n_correct": sum(results),
                "accuracy_pct": round(sum(results) / len(results) * 100, 1),
            }

    # Confidence correlation: high-confidence days vs accuracy
    high_conf = [r for r in graded if r.get("swarm_confidence", 0) >= 70]
    low_conf = [r for r in graded if r.get("swarm_confidence", 0) < 50]
    high_conf_acc = (sum(1 for r in high_conf if r.get("swarm_grade") == "CORRECT") / len(high_conf) * 100) if high_conf else None
    low_conf_acc = (sum(1 for r in low_conf if r.get("swarm_grade") == "CORRECT") / len(low_conf) * 100) if low_conf else None

    # Agreement rate: swarm vs premarket
    agreements = [r for r in records if r.get("swarm_vs_premarket") == "agree"]
    disagreements = [r for r in records if r.get("swarm_vs_premarket") == "disagree"]
    agree_correct = sum(1 for r in agreements if r.get("swarm_grade") == "CORRECT")
    disagree_swarm_correct = sum(1 for r in disagreements if r.get("swarm_grade") == "CORRECT")
    disagree_premarket_correct = sum(1 for r in disagreements if r.get("premarket_grade") == "CORRECT")

    agg = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "n_trading_days": len(records),
        "n_graded": n_graded,
        "swarm_overall": {
            "n_correct": n_correct,
            "n_wrong": n_wrong,
            "accuracy_pct": round(n_correct / n_graded * 100, 1) if n_graded else None,
        },
        "agent_accuracy": agent_accuracy,
        "confidence_calibration": {
            "high_conf_days": len(high_conf),
            "high_conf_accuracy_pct": round(high_conf_acc, 1) if high_conf_acc is not None else None,
            "low_conf_days": len(low_conf),
            "low_conf_accuracy_pct": round(low_conf_acc, 1) if low_conf_acc is not None else None,
        },
        "swarm_vs_premarket": {
            "n_agree_days": len(agreements),
            "n_disagree_days": len(disagreements),
            "on_agree_days_accuracy_pct": round(agree_correct / len(agreements) * 100, 1) if agreements else None,
            "on_disagree_swarm_accuracy_pct": round(disagree_swarm_correct / len(disagreements) * 100, 1) if disagreements else None,
            "on_disagree_premarket_accuracy_pct": round(disagree_premarket_correct / len(disagreements) * 100, 1) if disagreements else None,
        },
        "phase2_eligibility": {
            "min_days_required": 20,
            "days_available": n_graded,
            "ready_for_prompt_evolution": n_graded >= 20,
            "worst_agent": min(agent_accuracy, key=lambda k: agent_accuracy[k]["accuracy_pct"]) if agent_accuracy else None,
        },
        "recent_records": records[-5:],
    }

    with open(SCORECARD_AGG, "w", encoding="utf-8") as f:
        json.dump(agg, f, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Grade swarm prediction vs actual outcome")
    parser.add_argument("--date", required=True, help="Date to grade (YYYY-MM-DD)")
    parser.add_argument("--actual-bias", required=True,
                        choices=["bullish", "bearish", "no_trade"],
                        help="Actual SPY direction: bullish (close > open + $1), bearish, or no_trade")
    args = parser.parse_args()

    date_str = args.date
    actual_bias = args.actual_bias

    print(f"[swarm_grader] grading {date_str} actual_bias={actual_bias}")

    swarm = load_swarm_output_for_date(date_str)
    today_bias = load_today_bias_for_date(date_str)

    if swarm is None or swarm.get("status") == "failed":
        record = {
            "date": date_str,
            "swarm_grade": "NO_DATA",
            "premarket_grade": "NO_DATA",
            "actual_bias": actual_bias,
            "reason": "swarm_output.json missing or failed for this date",
        }
        append_scorecard_record(record)
        rebuild_aggregate()
        print(f"[swarm_grader] NO_DATA: swarm output unavailable for {date_str}")
        return 0

    consensus = swarm.get("consensus_bias", "no_trade")
    swarm_confidence = swarm.get("swarm_confidence", 0)
    swarm_vote_map = swarm.get("vote_map", {})
    swarm_strength = swarm.get("consensus_strength", "unknown")

    swarm_grade = grade_bias(consensus, actual_bias)

    # Grade single-agent premarket too (for comparison)
    premarket_bias = today_bias.get("bias") if today_bias else None
    premarket_grade = grade_bias(premarket_bias, actual_bias) if premarket_bias else "NO_DATA"

    # Agreement between swarm and premarket
    swarm_context = today_bias.get("swarm_context", {}) if today_bias else {}
    swarm_vs_premarket = swarm_context.get("agreement_with_premarket", "unknown")

    record = {
        "date": date_str,
        "actual_bias": actual_bias,
        "swarm_consensus": consensus,
        "swarm_confidence": swarm_confidence,
        "swarm_strength": swarm_strength,
        "swarm_grade": swarm_grade,
        "swarm_vote_map": swarm_vote_map,
        "premarket_bias": premarket_bias,
        "premarket_grade": premarket_grade,
        "swarm_vs_premarket": swarm_vs_premarket,
        "dissent_was_active": swarm.get("dissent_flag", {}).get("active", False),
        "graded_at": datetime.now(timezone.utc).isoformat(),
    }

    append_scorecard_record(record)
    rebuild_aggregate()

    print(f"[swarm_grader] GRADED: swarm={consensus}({swarm_confidence}%) → {swarm_grade} | premarket={premarket_bias} → {premarket_grade}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

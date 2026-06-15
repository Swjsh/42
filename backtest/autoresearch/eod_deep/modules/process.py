"""Process module — journal/decision/trade documentation completeness.

Phase 2.7 (2026-05-14): switched from absolute thresholds to MATERIAL RATIO.
Per J's feedback "% of material vs raw count" — grades should be % of
premarket predictions (we made 5 → graded 5 → 100% coverage = full pts),
NOT some arbitrary "≥3 grades = max" threshold that hurts low-prediction days.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..schema import CategoryScore
from ..ingest import IngestedData


def _count_premarket_predictions() -> int:
    """Read today-bias.json to count how many falsifiable predictions were made.

    Returns 0 if file missing or unreadable. Material denominator for grades_pts.
    """
    try:
        REPO = Path(__file__).resolve().parent.parent.parent.parent.parent
        bias_path = REPO / "automation" / "state" / "today-bias.json"
        if not bias_path.exists():
            return 0
        bias = json.loads(bias_path.read_text(encoding="utf-8"))
        preds = bias.get("falsifiable_predictions", []) or bias.get("predictions", [])
        return len(preds)
    except Exception:
        return 0


def analyze_process(data: IngestedData, trades) -> CategoryScore:
    """Score 0-100 based on documentation quality (material ratio metric).

    Weights:
      30 pts — journal markdown has ≥3 sections (bias / levels / trades or skipped)
      25 pts — trades.csv rows match number of actual trades (ratio)
      25 pts — decisions.jsonl coverage per trade (≥8 decisions/trade if traded)
      20 pts — hypothesis grades / premarket predictions ratio (% coverage)
    """
    journal_md = data.journal_md or ""
    section_count = sum(1 for marker in [
        "## Pre-Market", "## Key Levels", "## Trades",
        "## Setups Skipped", "## End-of-Day", "## Daily Review",
    ] if marker in journal_md)

    journal_pts = 30 if section_count >= 5 else (
        25 if section_count >= 4 else (
        20 if section_count >= 3 else (
        10 if section_count >= 2 else 0)))

    # Trades.csv: ratio of csv rows to actual trades (already material)
    trades_csv_pts = 0
    if trades:
        if len(data.trades_csv_rows) >= len(trades):
            trades_csv_pts = 25
        elif len(data.trades_csv_rows) > 0:
            trades_csv_pts = round(25 * len(data.trades_csv_rows) / len(trades))
        else:
            trades_csv_pts = 0
    else:
        trades_csv_pts = 25  # no trades, no requirement

    # Decisions.jsonl: switch from absolute count to material per-trade ratio.
    # If traded: ≥8 decisions per trade = full pts (typical: pre-trade thesis,
    # entry, ≥3 management ticks, ≥2 exit decisions, post-trade reflection).
    # If not traded: still need ≥5 decisions to show heartbeat ran + reasoned.
    decisions_count = len(data.decisions_today)
    n_trades = len(trades) if trades else 0
    if n_trades > 0:
        decisions_per_trade = decisions_count / n_trades
        if decisions_per_trade >= 8:
            decisions_pts = 25
        elif decisions_per_trade >= 5:
            decisions_pts = 20
        elif decisions_per_trade >= 3:
            decisions_pts = 15
        elif decisions_per_trade >= 1:
            decisions_pts = 8
        else:
            decisions_pts = 0
    else:
        # No trade day: need decisions to confirm engine ran + reasoned about skips
        if decisions_count >= 30:
            decisions_pts = 25
        elif decisions_count >= 15:
            decisions_pts = 20
        elif decisions_count >= 5:
            decisions_pts = 12
        elif decisions_count >= 1:
            decisions_pts = 5
        else:
            decisions_pts = 0

    # Hypothesis grades: switch from absolute "≥3" to MATERIAL RATIO.
    # 100% coverage of premarket predictions = full pts. Below 100% scaled.
    grades_count = len(data.hypothesis_grades_today)
    n_predictions = _count_premarket_predictions()
    if n_predictions > 0:
        coverage_pct = min(1.0, grades_count / n_predictions)
        grades_pts = round(20 * coverage_pct)
    else:
        # No premarket predictions made → can't ding for missing grades
        # but ANY grades earn partial credit (anomaly detection)
        grades_pts = 20 if grades_count >= 1 else 15

    score = journal_pts + trades_csv_pts + decisions_pts + grades_pts

    gaps = []
    if journal_pts < 30:
        gaps.append(f"journal sections {section_count}/6")
    if trades_csv_pts < 25:
        gaps.append(f"trades.csv rows {len(data.trades_csv_rows)}/{n_trades}")
    if decisions_pts < 25:
        if n_trades > 0:
            ratio = decisions_count / n_trades
            gaps.append(f"decisions/trade {ratio:.1f} (target ≥8)")
        else:
            gaps.append(f"decisions.jsonl entries {decisions_count} (target ≥15 no-trade days)")
    if grades_pts < 20:
        if n_predictions > 0:
            coverage = grades_count / n_predictions * 100
            gaps.append(f"hypothesis grade coverage {coverage:.0f}% ({grades_count}/{n_predictions} predictions)")
        else:
            gaps.append(f"hypothesis grades {grades_count} (no premarket predictions found)")

    narrative_parts = [f"Process score {score}/100."]
    narrative_parts.append(f"Journal: {section_count}/6 sections, {len(journal_md)}B.")
    narrative_parts.append(f"Trades.csv: {len(data.trades_csv_rows)} rows for {n_trades} trades.")
    if n_trades > 0:
        narrative_parts.append(f"Decisions: {decisions_count} ({decisions_count/n_trades:.1f}/trade, target ≥8).")
    else:
        narrative_parts.append(f"Decisions.jsonl: {decisions_count} entries.")
    if n_predictions > 0:
        cov = grades_count / n_predictions * 100
        narrative_parts.append(f"Hypothesis coverage: {grades_count}/{n_predictions} predictions ({cov:.0f}%).")
    else:
        narrative_parts.append(f"Hypothesis grades: {grades_count} (no premarket predictions).")
    if gaps:
        narrative_parts.append(f"Gaps: {' / '.join(gaps)}")

    return CategoryScore(
        score=float(score),
        evidence={
            "phase": "2.7",
            "section_count": section_count,
            "trades_csv_rows": len(data.trades_csv_rows),
            "trades_actual": n_trades,
            "decisions_count": decisions_count,
            "decisions_per_trade": (decisions_count / n_trades) if n_trades > 0 else None,
            "grades_count": grades_count,
            "premarket_predictions": n_predictions,
            "grade_coverage_pct": (grades_count / n_predictions * 100) if n_predictions > 0 else None,
            "weights": {
                "journal": journal_pts, "trades_csv": trades_csv_pts,
                "decisions": decisions_pts, "grades": grades_pts,
            },
            "gaps": gaps,
        },
        narrative=" ".join(narrative_parts),
        actions=[],
    )

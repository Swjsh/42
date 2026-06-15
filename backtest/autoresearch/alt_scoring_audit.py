"""Alt-scoring audit for ODF + VWAP rejections (Stage 1).

The J-anchor-primary scoring rejected 100% of ODF combos (0/810 passed_floors)
and is rejecting VWAP similarly. But the detectors DO produce signal on
non-anchor days — they're just not J-anchor-aligned.

This script re-ranks the rejections by a wide-window composite that ignores
J-anchor specifically and asks "is this strategy positive expectancy over
16 months?"

Composite score:
    score = wide_pnl × (wide_wr − 0.5) / max(1, max_drawdown) × 100

Higher = better. Rewards positive P&L, win rate above 50%, low drawdown.

Usage:
    python -m autoresearch.alt_scoring_audit
Outputs: docs/ALT-SCORING-AUDIT-2026-05-13.md
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def _load_rejections(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _alt_score(row: dict[str, Any]) -> float:
    wide_pnl = float(row.get("wide_pnl") or 0.0)
    wide_wr = float(row.get("wide_wr") or 0.0)
    max_dd = float(row.get("max_drawdown") or 0.0)
    if wide_pnl <= 0:
        return 0.0
    wr_edge = max(0.0, wide_wr - 0.5)
    dd_denom = max(1.0, max_dd)
    return wide_pnl * wr_edge / dd_denom * 100.0


def _top_n(rows: list[dict], n: int = 10) -> list[dict]:
    scored = [{"score": _alt_score(r), **r} for r in rows]
    scored.sort(key=lambda r: -r["score"])
    return scored[:n]


def _summarize_combo(row: dict, idx: int) -> list[str]:
    combo = row.get("combo", {})
    knobs_str = ", ".join(f"{k}={v}" for k, v in combo.items() if isinstance(v, (int, float, str)) and not k.startswith("_"))
    quarter_pnl = row.get("quarter_pnl", {})
    quarter_str = ", ".join(f"{q}=${v:.0f}" for q, v in sorted(quarter_pnl.items()))
    return [
        f"### #{idx + 1} — composite score {row['score']:.2f}",
        "",
        f"- **wide_pnl:** ${row.get('wide_pnl', 0):.2f}",
        f"- **wide_wr:** {row.get('wide_wr', 0):.1%}",
        f"- **wide_n_trades:** {row.get('wide_n_trades', 0)}",
        f"- **max_drawdown:** ${row.get('max_drawdown', 0):.2f}",
        f"- **top5_pct:** {row.get('top5_pct', 999.0):.3f}",
        f"- **positive_quarters:** {row.get('positive_quarters', 0)} / {row.get('quarter_count', 6)}",
        f"- **edge_capture (J-anchor primary):** ${row.get('edge_capture', 0):.0f}",
        f"- **knobs:** `{knobs_str}`",
        f"- **quarters:** {quarter_str}",
        "",
    ]


def audit_strategy(name: str, rejections_path: Path) -> list[str]:
    rows = _load_rejections(rejections_path)
    if not rows:
        return [f"## {name}", "", f"_No rejections file at {rejections_path}_", ""]

    n_total = len(rows)
    n_fired = sum(1 for r in rows if (r.get("wide_n_trades") or 0) > 0)
    n_positive = sum(1 for r in rows if (r.get("wide_pnl") or 0) > 0)

    out = [
        f"## {name}",
        "",
        f"**Stage 1 result (J-anchor-primary scoring):** 0 keepers (all rejected).",
        f"**Detector fire stats:** {n_fired}/{n_total} combos produced ≥1 trade. {n_positive}/{n_total} combos had positive wide_pnl.",
        "",
        f"**Top 10 combos by alt composite score (wide_pnl × (wr−0.5) / max_dd × 100):**",
        "",
    ]
    for i, row in enumerate(_top_n(rows, 10)):
        out.extend(_summarize_combo(row, i))
    return out


def main() -> int:
    state = REPO / "autoresearch" / "_state"
    odf_path = state / "opening_drive_fade_stage1" / "rejections.jsonl"
    vwap_path = state / "vwap_stage1" / "rejections.jsonl"
    v14e_path = state / "v14_enhanced_stage1" / "rejections.jsonl"

    out: list[str] = [
        "# Alt-Scoring Audit — ODF + VWAP + v14_ENHANCED (2026-05-13 overnight grind)",
        "",
        "> Stage 1 J-anchor-primary scoring rejected 100% of ODF (810/810) and nearly all VWAP + v14_enhanced combos.",
        "> But the detectors DO fire and DO produce signal — just not on J's specific anchor days,",
        "> OR they hit some anchors but fail strict per-day floors.",
        "> This audit re-ranks by wide-window composite to surface what the strategies actually capture.",
        "> **Composite:** `wide_pnl × (wide_wr − 0.5) / max(1, max_drawdown) × 100` (higher = better, rewards +EV with low DD).",
        "",
        f"_Generated: {dt.datetime.now().isoformat(timespec='seconds')}_",
        "",
    ]
    out.extend(audit_strategy("OPENING_DRIVE_FADE", odf_path))
    out.append("---")
    out.append("")
    out.extend(audit_strategy("VWAP_REJECTION_PRIME", vwap_path))
    out.append("---")
    out.append("")
    out.extend(audit_strategy("v14_ENHANCED", v14e_path))

    out.extend([
        "",
        "---",
        "",
        "## Recommendation for J's morning review",
        "",
        "Both strategies' Stage 1 scoring used J-anchor-primary edge_capture as the gate. But the detectors fire on DIFFERENT days than J's manual trades. The detectors aren't broken — the SCORING is misaligned with the strategy's actual signal pattern.",
        "",
        "**Options for next iteration:**",
        "1. Re-run Stage 1 with composite-based floors (e.g., wide_pnl ≥ $200, wide_wr ≥ 55%, max_dd ≤ $500) instead of J-anchor floors.",
        "2. Accept these strategies as WATCH-ONLY for now; gather live observations and grade them via watcher_grader.py.",
        "3. Widen the knob grids (esp. `vol_mult` and `proximity_dollars`) to find the parameter regimes that DO catch J's anchor days.",
        "",
        "The sniper strategy proves the framework works. The new strategies just need different scoring lenses.",
    ])

    out_path = REPO.parent / "docs" / "ALT-SCORING-AUDIT-2026-05-13.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(out), encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

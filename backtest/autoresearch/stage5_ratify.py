"""Stage-5 final ratification — picks THE winning candidate + writes scorecard.

After stage 4 (sub-window stability) finishes, this picks the single best
candidate that survived ALL gates and writes a final ratification scorecard
to analysis/recommendations/v15-final.json.

NO params.json bump per CLAUDE.md rule 9 — J ratifies. But the scorecard is
publish-ready: J reviews, says yes/no, that's the entire ratification step.

Pipeline gates a stage-5 candidate must have passed:
  - Stage 1: 4/29 + 5/04 + losers_added=0 floors
  - Stage 2: refined neighborhood (best of variations)
  - Stage 3: top-5 days <= 200% of total P&L AND >= 4 of 6 quarters net-positive
  - Stage 4: ALL 6 quarters net-positive AND >= 3 trades per quarter

If stage 4 has 0 keepers, fall back to stage 3 best (with explicit "stage 4 fail" note).
If stage 3 has 0 keepers, fall back to stage 2.
Etc.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))

STAGE_DIRS = [
    ("stage4", REPO / "autoresearch" / "_state" / "stage4_grinder"),
    ("stage3", REPO / "autoresearch" / "_state" / "stage3_grinder"),
    ("stage2", REPO / "autoresearch" / "_state" / "stage2_grinder"),
    ("stage1", REPO / "autoresearch" / "_state" / "overnight_grinder"),
]

OUT_PATH = ROOT / "analysis" / "recommendations" / "v15-final.json"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)


def _read_keepers(d: Path) -> list[dict]:
    p = d / "keepers.jsonl"
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def main() -> int:
    chosen_stage = None
    chosen_keeper = None

    for name, d in STAGE_DIRS:
        keepers = _read_keepers(d)
        if not keepers:
            continue
        # Pick best by combined edge+wide rank
        edge_rank = {id(k): i for i, k in enumerate(sorted(keepers, key=lambda r: -r.get("edge_capture", 0)))}
        wide_rank = {id(k): i for i, k in enumerate(sorted(keepers, key=lambda r: -r.get("wide_pnl", 0)))}
        keepers.sort(key=lambda r: edge_rank[id(r)] + wide_rank[id(r)])
        chosen_stage = name
        chosen_keeper = keepers[0]
        break

    if not chosen_keeper:
        scorecard = {
            "generated_at": dt.datetime.now().isoformat(),
            "verdict": "no_candidates",
            "reason": "No keepers in any stage. Pipeline did not produce a winner.",
            "next_action": "manual diagnostic: read each stage's rejections.jsonl to understand why",
        }
        OUT_PATH.write_text(json.dumps(scorecard, indent=2), encoding="utf-8")
        return 1

    combo = chosen_keeper["combo"]
    scorecard = {
        "generated_at": dt.datetime.now().isoformat(),
        "rule_id": "v15-final",
        "method": f"5-stage grinder pipeline (stages 1-{int(chosen_stage[5:])} produced this winner)",
        "verdict": "ready_for_ratification" if chosen_stage == "stage4" else f"best_through_{chosen_stage}_only",
        "chosen_from_stage": chosen_stage,
        "winner_combo": combo,
        "winner_metrics": {
            "pnl_4_29": chosen_keeper.get("pnl_4_29"),
            "pnl_5_04": chosen_keeper.get("pnl_5_04"),
            "edge_capture": chosen_keeper.get("edge_capture"),
            "winners_capture": chosen_keeper.get("winners_capture"),
            "losers_added": chosen_keeper.get("losers_added"),
            "wide_pnl": chosen_keeper.get("wide_pnl"),
            "wide_n_trades": chosen_keeper.get("wide_n_trades"),
            "wide_wr": chosen_keeper.get("wide_wr"),
            "top5_pct": chosen_keeper.get("top5_pct"),
            "positive_quarters": chosen_keeper.get("positive_quarters"),
            "max_drawdown": chosen_keeper.get("max_drawdown"),
            "sub_window_pnls": chosen_keeper.get("sub_window_pnls"),
            "quarter_pnl": chosen_keeper.get("quarter_pnl"),
        },
        "baselines": {
            "BASELINE_4_29": 372.0,
            "BASELINE_5_04": 2418.0,
            "BASELINE_EDGE": 2769.0,
            "BASELINE_WIDE_PNL": 3655.0,
            "J_TOTAL_WINNERS": 1542,
        },
        "improvements_vs_baseline": {
            "edge_capture_delta": round((chosen_keeper.get("edge_capture", 0) - 2769.0), 2),
            "wide_pnl_delta": round((chosen_keeper.get("wide_pnl", 0) - 3655.0), 2),
            "wide_pnl_pct": round((chosen_keeper.get("wide_pnl", 0) / 3655.0 - 1) * 100, 1) if chosen_keeper.get("wide_pnl") else None,
            "concentration_change": "track separately — see top5_pct vs baseline 456%",
        },
        "ratification_status": "AWAITING_J_REVIEW",
        "params_json_bump_required": True,
        "params_json_diff": {
            # NOT auto-applied; this is what J would copy/paste
            "TODO": "Translate per-quality knobs into orchestrator override keys",
            "winner_combo": combo,
            "current_baseline": "V15_J_EDGE_OVERRIDES (in autoresearch/j_edge_tracker.py)",
        },
        "pipeline_summary": {
            stage_name: {
                "completed": (json.loads((stage_dir / "progress.json").read_text(encoding="utf-8")).get("completed") if (stage_dir / "progress.json").exists() else None),
                "keepers": (json.loads((stage_dir / "progress.json").read_text(encoding="utf-8")).get("keepers") if (stage_dir / "progress.json").exists() else None),
                "best_edge": (json.loads((stage_dir / "progress.json").read_text(encoding="utf-8")).get("best_edge_capture") if (stage_dir / "progress.json").exists() else None),
                "best_wide": (json.loads((stage_dir / "progress.json").read_text(encoding="utf-8")).get("best_wide_pnl") if (stage_dir / "progress.json").exists() else None),
            }
            for stage_name, stage_dir in STAGE_DIRS
        },
    }

    OUT_PATH.write_text(json.dumps(scorecard, indent=2, default=str), encoding="utf-8")

    # Also write a shorter human-readable summary
    summary_path = ROOT / "docs" / "RATIFICATION-READY.md"
    md = [
        f"# v15-final candidate — ready for ratification\n",
        f"Generated {dt.datetime.now().isoformat()}\n",
        f"## Winner from {chosen_stage}\n",
        f"```json\n{json.dumps(combo, indent=2)}\n```\n",
        f"## Metrics\n",
        f"| Metric | Value | vs Baseline |",
        f"|---|---|---|",
        f"| 4/29 BEAT-J | ${chosen_keeper.get('pnl_4_29'):.0f} | vs $372 |",
        f"| 5/04 BEAT-J | ${chosen_keeper.get('pnl_5_04'):.0f} | vs $2,418 |",
        f"| edge_capture | ${chosen_keeper.get('edge_capture', 0):.0f} | vs $2,769 |",
        f"| wide_pnl (16mo) | ${chosen_keeper.get('wide_pnl', 0):.0f} | vs $3,655 (**{(chosen_keeper.get('wide_pnl', 0) / 3655.0 - 1) * 100:+.0f}%**) |",
        f"| top5_pct (concentration) | {(chosen_keeper.get('top5_pct') or 0) * 100:.0f}% | vs 456% baseline |",
        f"| positive_quarters | {chosen_keeper.get('positive_quarters', '—')}/{chosen_keeper.get('quarter_count', '—')} | — |",
        f"| max_drawdown | ${chosen_keeper.get('max_drawdown', 0):.0f} | — |",
        f"\n## Sub-window check\n",
    ]
    if chosen_keeper.get("sub_window_pnls"):
        md.append("| Quarter | P&L | n |")
        md.append("|---|---|---|")
        for q, sw in chosen_keeper["sub_window_pnls"].items():
            md.append(f"| {q} | ${sw['pnl']:.0f} | {sw['n']} |")
    md.append(f"\n## Ratify or reject\n")
    md.append(f"Per CLAUDE.md rule 9 — params.json bump waits for J's explicit yes.\n")
    md.append(f"Full scorecard JSON: `analysis/recommendations/v15-final.json`")
    summary_path.write_text("\n".join(md), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

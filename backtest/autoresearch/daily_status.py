"""Daily status report — runs at 08:00 ET via scheduled task.

Aggregates state from all grinder stages (1, 2, 3, ...) and writes a
concise report to:
  - automation/state/research-queue.json    (for next session pickup)
  - docs/STATUS-{date}.md                    (human-readable morning brief)

Per CLAUDE.md OP 18: this is the autonomous status mechanism. No user prompt
required — scheduled task fires daily at 08:00 ET.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
STATE_DIR = ROOT / "automation" / "state"
DOCS_DIR = ROOT / "docs"
STATE_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DIR.mkdir(parents=True, exist_ok=True)

QUEUE_FILE = STATE_DIR / "research-queue.json"

STAGE_DIRS = {
    "stage1": REPO / "autoresearch" / "_state" / "overnight_grinder",
    "stage2": REPO / "autoresearch" / "_state" / "stage2_grinder",
    "stage3": REPO / "autoresearch" / "_state" / "stage3_grinder",
    "stage4": REPO / "autoresearch" / "_state" / "stage4_grinder",
    "stage5": REPO / "autoresearch" / "_state" / "stage5_grinder",
    "bullish": REPO / "autoresearch" / "_state" / "bullish_grinder",
}


def _read_progress(stage_dir: Path) -> dict:
    p = stage_dir / "progress.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_keepers(stage_dir: Path) -> list[dict]:
    p = stage_dir / "keepers.jsonl"
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


def _stage_summary(name: str, stage_dir: Path) -> dict:
    progress = _read_progress(stage_dir)
    keepers = _read_keepers(stage_dir)
    if not progress and not keepers:
        return {"stage": name, "state": "not_started"}

    # Best by edge_capture
    best_edge = max(keepers, key=lambda r: r.get("edge_capture", 0)) if keepers else None
    best_wide = max(keepers, key=lambda r: r.get("wide_pnl", 0)) if keepers else None

    return {
        "stage": name,
        "state": progress.get("status", "unknown"),
        "completed": progress.get("completed", 0),
        "total": progress.get("total_combos", 0),
        "passed_floors": progress.get("passed_floors", 0),
        "rejected": progress.get("rejected", 0),
        "keepers": progress.get("keepers", 0),
        "best_edge_capture": progress.get("best_edge_capture"),
        "best_wide_pnl": progress.get("best_wide_pnl"),
        "best_top5_pct": progress.get("best_top5_pct"),
        "best_positive_quarters": progress.get("best_positive_quarters"),
        "started_at": progress.get("started_at"),
        "deadline_at": progress.get("deadline_at"),
        "completed_at": progress.get("completed_at"),
        "best_edge_combo": best_edge["combo"] if best_edge else None,
        "best_wide_combo": best_wide["combo"] if best_wide else None,
    }


def main() -> int:
    now = dt.datetime.now()
    today = now.date()

    stages = {name: _stage_summary(name, d) for name, d in STAGE_DIRS.items()}

    # What is the next action? Build a "decision queue" entry for the next session
    next_action = "all_done"
    for name in ["stage1", "stage2", "stage3", "stage4", "stage5"]:
        s = stages[name]
        if s["state"] == "not_started":
            next_action = f"launch_{name}"
            break
        if s["state"] == "running":
            next_action = f"wait_for_{name}"
            break
        if s["state"] in ("completed", "deadline_reached"):
            continue
        next_action = f"check_{name}"
        break

    queue = {
        "generated_at": now.isoformat(),
        "next_action": next_action,
        "stages": stages,
    }
    QUEUE_FILE.write_text(json.dumps(queue, indent=2, default=str), encoding="utf-8")

    # Markdown report
    md = [f"# Research status — {today.isoformat()} {now.strftime('%H:%M')} ET\n"]
    md.append(f"**Next action:** `{next_action}`\n")
    md.append("## Pipeline state\n")
    md.append("| Stage | State | Progress | Keepers | Best edge | Best wide_pnl | Best top5% | Best Q+ |")
    md.append("|---|---|---|---|---|---|---|---|")
    for name, s in stages.items():
        if s["state"] == "not_started":
            md.append(f"| {name} | not_started | — | — | — | — | — | — |")
            continue
        prog = f"{s.get('completed', 0)}/{s.get('total', 0)}"
        keepers = s.get("keepers", 0)
        edge = f"${s['best_edge_capture']:.0f}" if s.get("best_edge_capture") else "—"
        wide = f"${s['best_wide_pnl']:.0f}" if s.get("best_wide_pnl") else "—"
        top5 = f"{s['best_top5_pct']*100:.0f}%" if s.get("best_top5_pct") else "—"
        qplus = str(s.get("best_positive_quarters") or "—")
        md.append(f"| {name} | {s['state']} | {prog} | {keepers} | {edge} | {wide} | {top5} | {qplus} |")

    # Best overall combo (combined rank across all stages)
    all_keepers = []
    for name, d in STAGE_DIRS.items():
        for k in _read_keepers(d):
            k["_stage"] = name
            all_keepers.append(k)

    if all_keepers:
        # Combined rank
        edge_rank = {id(r): i for i, r in enumerate(sorted(all_keepers, key=lambda r: -r.get("edge_capture", 0)))}
        wide_rank = {id(r): i for i, r in enumerate(sorted(all_keepers, key=lambda r: -r.get("wide_pnl", 0)))}
        all_keepers.sort(key=lambda r: edge_rank[id(r)] + wide_rank[id(r)])
        md.append("\n## Top 5 candidates (combined rank across all stages)\n")
        md.append("| Stage | edge | 4/29 | 5/04 | wide_pnl | top5% | Q+ | combo |")
        md.append("|---|---|---|---|---|---|---|---|")
        for k in all_keepers[:5]:
            c = k["combo"]
            top5 = f"{k.get('top5_pct', 0)*100:.0f}%" if k.get("top5_pct") is not None else "—"
            qplus = f"{k.get('positive_quarters', '—')}/{k.get('quarter_count', '—')}"
            md.append(
                f"| {k['_stage']} | ${k['edge_capture']:.0f} | ${k['pnl_4_29']:.0f} | ${k['pnl_5_04']:.0f} "
                f"| ${k['wide_pnl']:.0f} | {top5} | {qplus} | "
                f"super_stop={c['super_stop']} super_tp1={c['super_tp1']} runner={c['runner_target']} "
                f"lvl_qty={c['level_qty']} lvl_stop={c['level_stop']} lvl_tp1={c['level_tp1']} trend_stop={c['trendline_stop']} |"
            )

    md.append(f"\n## What I am doing next\n")
    if next_action.startswith("wait_for_"):
        s = next_action.replace("wait_for_", "")
        md.append(f"- {s} is grinding. Hourly monitor watches it.")
        md.append(f"- When it finishes, monitor auto-launches the next stage.")
    elif next_action.startswith("launch_"):
        md.append(f"- Need to launch {next_action.replace('launch_','')}. Monitor will do this on next tick.")
    elif next_action == "all_done":
        md.append(f"- All stages 1-5 finished. Final ratification scorecard ready.")
        md.append(f"- ACTION FOR J: review top candidates above, ratify or reject.")
    md.append("")

    report_path = DOCS_DIR / f"STATUS-{today.isoformat()}.md"
    report_path.write_text("\n".join(md), encoding="utf-8")

    # Also overwrite the latest STATUS.md so dashboard can always read it
    latest = DOCS_DIR / "STATUS.md"
    latest.write_text("\n".join(md), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""CHEF-CANDIDATES-CONSOLIDATION-SWEEP (queue.md, filed 2026-07-22 night).

One-time triage of strategy/candidates/ — 1619 top-level .md files (verified
2026-07-22, far more than the "100+" the parent CHEF-FOCUS-FILTER item
estimated). Per OP-22 ("a 371st untriaged candidate is debt, not progress"):
for each candidate file, decide level-family vs not, stale vs not, has
traction (LEADERBOARD/inbox reference) vs not, and move the archive-eligible
ones under strategy/candidates/_archive/<batch>/ — MOVE, never delete.

Run in batches (200-300 files/fire) across several conductor/chef fires —
this module processes exactly one batch per invocation, oldest-first, and
skips anything already archived. $0 pure-Python — no LLM calls.

Usage:
    python backtest/tools/chef_candidates_consolidation_sweep.py --dry-run
    python backtest/tools/chef_candidates_consolidation_sweep.py --batch-size 250 --apply
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

CANDIDATES_DIR = Path(__file__).resolve().parents[2] / "strategy" / "candidates"
ARCHIVE_ROOT = CANDIDATES_DIR / "_archive"
LEADERBOARD_FILES = ["_LEADERBOARD.md", "_LEADERBOARD-pending.md"]
INBOX_DIRS = ["_chef-inbox", "_validator-inbox", "_lesson-inbox", "_skill-inbox"]
CHEF_LOG = CANDIDATES_DIR / "_chef-log.jsonl"

FILENAME_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")

# Same family-recognition vocabulary as setup/scripts/task_scorer.py's
# LEVEL_FAMILY_RE — kept as a literal copy (not an import) so this one-time
# tool has zero runtime coupling to the live scorer module. Any drift between
# the two is intentionally caught by test_consolidation_sweep_matches_scorer_vocab.
LEVEL_FAMILY_RE = re.compile(
    r"\blevel[\s-]*(?:reject|rejection|reclaim|interaction|touch|flip|retest|break)"
    r"|reject(?:ion)?\s+at\s+(?:\w+\s+){0,3}level"
    r"|\breclaim(?:s|ed|ing)?\b"
    r"|flip[\s-]*retest"
    r"|range[\s-]*ping[\s-]*pong"
    r"|break[\s-]*(?:and[\s-]*)?retest"
    r"|s\s*/\s*r\s+flip"
    r"|\bribbon\b"
    r"|\bvwap\b"
    r"|\bkey[\s-]*level\b"
    r"|\bsupport\b|\bresistance\b",
    re.IGNORECASE,
)

TAG_RE = re.compile(r"^\s*level_family\s*:\s*(true|false)\s*$", re.IGNORECASE | re.MULTILINE)


@dataclass(frozen=True)
class Disposition:
    path: Path
    filename_date: "date | None"
    level_family: bool
    reason: str
    has_traction: bool
    stale: bool
    archive: bool


def _parse_filename_date(name: str) -> "date | None":
    m = FILENAME_DATE_RE.match(name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


def _load_traction_names(candidates_dir: Path) -> set[str]:
    """Filenames referenced by the LEADERBOARD or any live inbox — 'has traction'."""
    names: set[str] = set()
    for fname in LEADERBOARD_FILES:
        p = candidates_dir / fname
        if p.exists():
            text = p.read_text(encoding="utf-8", errors="ignore")
            names.update(re.findall(r"([\w.\-]+\.md)", text))
    for inbox in INBOX_DIRS:
        d = candidates_dir / inbox
        if d.is_dir():
            for f in d.glob("*.md"):
                text = f.read_text(encoding="utf-8", errors="ignore")
                names.update(re.findall(r"([\w.\-]+\.md)", text))
    return names


def classify(path: Path, today: date, traction_names: set[str]) -> Disposition:
    fdate = _parse_filename_date(path.name)
    stale = fdate is not None and (today - fdate) > timedelta(days=30)

    text = path.read_text(encoding="utf-8", errors="ignore")[:4000]
    tag_match = TAG_RE.search(text)
    if tag_match:
        level_family = tag_match.group(1).lower() == "true"
        reason = f"tagged level_family:{tag_match.group(1).lower()}"
    else:
        # Predates CHEF-FOCUS-FILTER's tag — infer from filename + first heading.
        heading = ""
        for line in text.splitlines()[:5]:
            if line.strip().startswith("#"):
                heading = line
                break
        probe = f"{path.stem} {heading}"
        level_family = bool(LEVEL_FAMILY_RE.search(probe))
        reason = f"inferred from title (no tag): {'matched' if level_family else 'no match'}"

    has_traction = path.name in traction_names

    # Conservative "when in doubt KEEP" per _archive/README.md's own stated policy.
    archive = stale and not level_family and not has_traction

    return Disposition(
        path=path,
        filename_date=fdate,
        level_family=level_family,
        reason=reason,
        has_traction=has_traction,
        stale=stale,
        archive=archive,
    )


def list_candidates(candidates_dir: Path) -> list[Path]:
    return sorted(
        p for p in candidates_dir.glob("*.md") if p.is_file()
    )


def run_batch(
    candidates_dir: Path = CANDIDATES_DIR,
    batch_size: int = 250,
    apply: bool = False,
    today: "date | None" = None,
) -> dict:
    today = today or date.today()
    traction_names = _load_traction_names(candidates_dir)
    all_candidates = list_candidates(candidates_dir)

    dispositions = [classify(p, today, traction_names) for p in all_candidates]
    eligible = [d for d in dispositions if d.archive]
    batch = eligible[:batch_size]

    batch_folder = candidates_dir / "_archive" / f"sweep-{today.isoformat()}"
    moved: list[str] = []
    if apply and batch:
        batch_folder.mkdir(parents=True, exist_ok=True)
        for d in batch:
            dest = batch_folder / d.path.name
            shutil.move(str(d.path), str(dest))
            moved.append(d.path.name)

    summary = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "total_candidates_scanned": len(all_candidates),
        "eligible_total": len(eligible),
        "batch_size_requested": batch_size,
        "batch_processed": len(batch),
        "applied": apply,
        "batch_folder": str(batch_folder.relative_to(candidates_dir)) if (apply and batch) else None,
        "moved_files": moved,
        "remaining_eligible_after_batch": max(0, len(eligible) - len(batch)),
        "kept_level_family": sum(1 for d in dispositions if d.level_family),
        "kept_traction": sum(1 for d in dispositions if d.has_traction and not d.level_family),
        "kept_not_stale": sum(1 for d in dispositions if not d.stale and not d.level_family and not d.has_traction),
    }
    return summary


def append_chef_log(summary: dict, work_item: str) -> None:
    entry = {
        "started_at": summary["run_at"],
        "finished_at": summary["run_at"],
        "work_item": work_item,
        "candidate_written": None,
        "verdict": "archived-consolidation-sweep",
        "note": (
            f"batch archived {summary['batch_processed']} of "
            f"{summary['eligible_total']} eligible ({summary['total_candidates_scanned']} scanned); "
            f"{summary['remaining_eligible_after_batch']} still eligible for next batch; "
            f"kept={summary['kept_level_family']} level-family, "
            f"{summary['kept_traction']} traction, {summary['kept_not_stale']} not-yet-stale."
        ),
        "batch_folder": summary["batch_folder"],
        "moved_files": summary["moved_files"],
        "cost_usd": 0.0,
    }
    with CHEF_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch-size", type=int, default=250)
    ap.add_argument("--apply", action="store_true", help="Actually move files (default: dry-run)")
    ap.add_argument("--dry-run", action="store_true", help="Explicit dry-run (default behavior)")
    args = ap.parse_args()

    apply = args.apply and not args.dry_run
    summary = run_batch(batch_size=args.batch_size, apply=apply)
    print(json.dumps(summary, indent=2))
    if apply and summary["batch_processed"] > 0:
        append_chef_log(summary, "CHEF-CANDIDATES-CONSOLIDATION-SWEEP batch")


if __name__ == "__main__":
    main()

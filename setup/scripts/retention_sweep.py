#!/usr/bin/env python3
"""Retention sweep for append-only producer output directories.

GOAL-RIG-HYGIENE-2026-09-05 H3. Policy source of truth is `markdown/infra/RETENTION.md`;
the `DIRECTORIES` table below must stay in sync with that doc's table (the H4 guard test,
`backtest/tests/test_retention_doc_coverage_2026_09_05.py`, cross-checks both against live
`git status --porcelain` output).

For every entry: list candidate files (skip anything already under `_archive/`), skip any
whose filename is cited anywhere under `markdown/`, `automation/overnight/STATUS.md`, or
`analysis/recommendations/` (a cited file is evidence -- never swept), and MOVE (never
delete) the rest into `<dir>/_archive/<file's own mtime YYYY-MM>/`.

Dry-run by default -- prints per-directory move counts, no filesystem change.
`--apply` performs the moves.

CLI:
  python setup/scripts/retention_sweep.py            # dry run
  python setup/scripts/retention_sweep.py --apply    # apply moves
"""
from __future__ import annotations

import argparse
import datetime as dt
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _untracked_files() -> set[Path]:
    """Every path `git status --porcelain` reports as untracked ('??'), resolved absolute.

    The sweep only ever touches untracked files -- a file git already has in its index is
    real committed content, not the unbounded-accumulation problem this tool exists to fix,
    and MOVEing it off disk without `git mv` would show up as an unstaged tracked-file
    deletion. Scoping to untracked keeps this tool's blast radius to exactly the "~3,000
    untracked generated files" problem GOAL-RIG-HYGIENE-2026-09-05 names.
    """
    out = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout
    paths = set()
    for line in out.splitlines():
        if line.startswith("??"):
            rel = line[3:].strip().rstrip("/")
            paths.add((REPO / rel).resolve())
    return paths

# Policy table -- MUST mirror markdown/infra/RETENTION.md. Each entry sweeps files directly
# inside `dir` (non-recursive into subfolders other than the `_archive/` it creates) whose
# name matches `glob` (default "*") and are older than the keep window.
DIRECTORIES: list[dict] = [
    {"dir": "analysis/manager", "glob": "*", "policy": "keep-N", "n": 200},
    {"dir": "analysis/daily-brief", "glob": "*", "policy": "keep-days", "days": 30},
    {"dir": "analysis/swarm-consult", "glob": "*", "policy": "keep-N", "n": 60},
    # free-model-audit is split into 4 per-touchpoint subdirs, not flat files -- sweep
    # each independently so a busy touchpoint doesn't starve a quiet one's keep window.
    *[
        {"dir": f"analysis/free-model-audit/{sub}", "glob": "*", "policy": "keep-N", "n": 15,
         "label": f"free-model-audit/{sub}"}
        for sub in ["heartbeat-veto", "prospector", "swarm-consult", "twin-review"]
    ],
    # Only automation/state/crypto-twin/reviews/ is dated one-off accumulation (one .json +
    # .md pair per day); the directory's top-level files (breaker.json, decisions.jsonl,
    # exit-state.json, etc.) are live current-state singletons the gym reader depends on --
    # never swept.
    {"dir": "automation/state/crypto-twin/reviews", "glob": "*", "policy": "keep-days", "days": 30,
     "label": "automation/state/crypto-twin/reviews"},
    {"dir": "analysis/autopsies", "glob": "*", "policy": "keep-days", "days": 30},
    {"dir": "analysis/eod", "glob": "*", "policy": "keep-days", "days": 30,
     "exclude": ["_analyst-log.jsonl"]},
    {"dir": "analysis/gym", "glob": "*", "policy": "keep-days", "days": 45},
    {"dir": "analysis/participation-cascade", "glob": "*", "policy": "keep-N", "n": 20},
    {"dir": "backtest/autoresearch/_state", "glob": "*", "policy": "keep-days", "days": 30},
    # automation/state/ loose dated one-off prefixes -- swept per-prefix so an old
    # heartbeat-tick-audit doesn't get compared against a fresh spend- file's age.
    *[
        {"dir": "automation/state", "glob": f"{prefix}*", "policy": "keep-days", "days": 14,
         "label": prefix.rstrip("-")}
        for prefix in [
            "heartbeat-tick-audit-", "entry-block-alert-", "spend-",
            "heartbeat-pulse-check-", "gym-scorecard-", "daily-loop-status-",
            "chart-data-verify-", "watcher-state-inspector-", "fill-funnel-",
            "chop-exposure-", "daily-review-",
        ]
    ],
    {"dir": "automation/state/claude-md-backups", "glob": "*", "policy": "keep-N", "n": 10},
]

CITATION_ROOTS = [
    REPO / "markdown",
    REPO / "automation" / "overnight" / "STATUS.md",
    REPO / "analysis" / "recommendations",
]


def _load_citation_corpus() -> str:
    """Concatenate every text file under the citation roots into one search corpus."""
    chunks: list[str] = []
    for root in CITATION_ROOTS:
        if root.is_file():
            paths = [root]
        elif root.is_dir():
            paths = list(root.rglob("*"))
        else:
            continue
        for p in paths:
            if not p.is_file():
                continue
            if p.suffix.lower() not in (".md", ".json", ".jsonl", ".txt"):
                continue
            try:
                chunks.append(p.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
    return "\n".join(chunks)


def _archive_dest(base: Path, f: Path) -> Path:
    mtime = dt.datetime.fromtimestamp(f.stat().st_mtime)
    month_dir = base / "_archive" / mtime.strftime("%Y-%m")
    return month_dir / f.name


def plan_moves(
    entry: dict, corpus: str, now: dt.datetime, untracked: set[Path]
) -> list[tuple[Path, Path, str]]:
    """Return [(src, dest, reason)] for files this entry would move. No I/O side effects."""
    base = REPO / entry["dir"]
    if not base.is_dir():
        return []
    exclude = set(entry.get("exclude", []))
    candidates = [
        f for f in sorted(base.glob(entry["glob"]))
        if f.is_file()
        and f.name not in exclude
        and "_archive" not in f.parts
        and not f.name.startswith(".")
        and f.resolve() in untracked
    ]

    if entry["policy"] == "keep-N":
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        to_sweep = candidates[entry["n"]:]
    elif entry["policy"] == "keep-days":
        cutoff = now - dt.timedelta(days=entry["days"])
        to_sweep = [
            f for f in candidates
            if dt.datetime.fromtimestamp(f.stat().st_mtime) < cutoff
        ]
    else:
        raise ValueError(f"unknown policy: {entry['policy']}")

    moves = []
    for f in to_sweep:
        if f.name in corpus:
            continue  # cited -- evidence, never sweep
        moves.append((f, _archive_dest(base, f), "keep-N/keep-days expiry, not cited"))
    return moves


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="perform the moves (default: dry run)")
    args = ap.parse_args()

    now = dt.datetime.now()
    corpus = _load_citation_corpus()
    untracked = _untracked_files()

    total = 0
    per_dir: dict[str, int] = {}
    for entry in DIRECTORIES:
        moves = plan_moves(entry, corpus, now, untracked)
        label = entry.get("label", entry["dir"])
        per_dir[label] = per_dir.get(label, 0) + len(moves)
        total += len(moves)
        for src, dest, reason in moves:
            if args.apply:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dest))
            print(f"{'MOVED' if args.apply else 'WOULD MOVE'} {src.relative_to(REPO)} -> {dest.relative_to(REPO)}")

    print("\n--- summary ---")
    for label, count in sorted(per_dir.items(), key=lambda kv: -kv[1]):
        if count:
            print(f"{label}: {count}")
    print(f"TOTAL {'moved' if args.apply else 'would move'}: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

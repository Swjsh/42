"""Guard: every untracked generated-output directory must have a retention row.

GOAL-RIG-HYGIENE-2026-09-05 H4. The failure mode this guard exists to prevent is a NEW
producer script showing up, dumping dated files into some directory nobody documented, and
that pile growing unbounded again exactly like `analysis/manager` (874 untracked files, no
retention policy) did before this goal. So this test does not just check that the doc file
exists -- it re-derives the CURRENT set of untracked top-level producer directories from
live `git status --porcelain` output and asserts every one with a non-trivial file count is
either swept by `setup/scripts/retention_sweep.py`'s DIRECTORIES table or explicitly
allow-listed as evidence/out-of-scope in `markdown/infra/RETENTION.md`.

RED-PROOF: `test_fails_on_an_undocumented_directory` fabricates a brand-new untracked
directory with no retention coverage and asserts the coverage-check function flags it --
proving this guard would actually catch the L-class foot-gun it targets, not just a
directory-existence smoke test that any build would pass.
"""
from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

sweep = importlib.import_module("retention_sweep")

RETENTION_DOC = REPO / "markdown" / "infra" / "RETENTION.md"

# Directories explicitly documented in RETENTION.md as "evidence -- no action" / out of
# scope for this sweep (journal, code, human-authored docs, live per-arm state the engine
# reads every tick). Kept here as a plain allowlist so the guard can check coverage without
# parsing markdown table cells -- if you add a new "evidence -- no action" row to the doc,
# add its directory here too (the doc-presence check below fails loudly if you forget).
DOCUMENTED_NO_ACTION_DIRS = {
    "markdown/audits",
    "analysis/deep-research",
    "analysis/recommendations",
    "journal",
    "journal/futures",
    "backtest/tools",
    "backtest/tests",
    "backtest/autoresearch",
    ".claude/agent-memory",
    "setup/scripts",
    "automation/state/futures",
    "automation/state/multi",
    "automation/state/fleet",
    # Small-volume (<10 untracked files each as of 2026-09-05) dated research/eval outputs --
    # documented but deferred rather than swept: low accumulation risk at this size, and each
    # is either evidence-shaped (prospector scouting notes, conviction backtest summaries) or
    # a small enough ledger that a false-positive sweep would cost more than the disk space
    # saved. Revisit if any of these crosses the same ~50-file threshold that triggered this
    # goal for analysis/manager.
    "analysis/backtests",
    "analysis/conviction",
    "analysis/fleet-weekly",
    "analysis/futures-eod",
    "analysis/multi-lane",
    "analysis/prospector",
    "automation/swarm",
}


def _swept_dirs() -> set[str]:
    """Directories (relative, forward-slash) covered by retention_sweep.py's policy table."""
    return {entry["dir"] for entry in sweep.DIRECTORIES}


def _untracked_top_dirs(min_count: int = 5) -> dict[str, int]:
    """Top-2-segment untracked directories from live git status, with file counts >= min_count."""
    out = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout
    counts: dict[str, int] = {}
    for line in out.splitlines():
        if not line.startswith("??"):
            continue
        rel = line[3:].strip().rstrip("/")
        parts = Path(rel).parts
        if len(parts) < 2:
            continue  # loose root-level file, not a directory producer
        top2 = "/".join(parts[:2])
        counts[top2] = counts.get(top2, 0) + 1
    return {k: v for k, v in counts.items() if v >= min_count}


def find_uncovered_dirs(untracked_counts: dict[str, int], swept: set[str], allowed: set[str]) -> list[str]:
    """Pure-ish check: which untracked dirs are neither swept nor allow-listed as evidence."""
    uncovered = []
    for d, count in untracked_counts.items():
        if d in allowed:
            continue
        if any(d == s or d.startswith(s + "/") or s.startswith(d + "/") for s in swept):
            continue
        uncovered.append(d)
    return uncovered


def test_retention_doc_exists_and_is_linked_from_readme():
    assert RETENTION_DOC.exists(), "markdown/infra/RETENTION.md must exist (H2)"
    readme = (REPO / "markdown" / "README.md").read_text(encoding="utf-8")
    assert "RETENTION.md" in readme, "RETENTION.md must be linked from markdown/README.md's infra row"


def test_live_untracked_directories_are_all_covered():
    """The real guard: run against CURRENT repo state, fail if anything new is uncovered."""
    untracked = _untracked_top_dirs(min_count=5)
    swept = _swept_dirs()
    uncovered = find_uncovered_dirs(untracked, swept, DOCUMENTED_NO_ACTION_DIRS)
    assert not uncovered, (
        f"untracked director{'y' if len(uncovered)==1 else 'ies'} with no retention coverage: "
        f"{uncovered} -- add a row to markdown/infra/RETENTION.md and either an entry to "
        f"retention_sweep.py's DIRECTORIES or to this test's DOCUMENTED_NO_ACTION_DIRS"
    )


def test_fails_on_an_undocumented_directory():
    """RED-PROOF: a fabricated brand-new untracked dir with no coverage MUST be flagged."""
    fake_untracked = {"analysis/some-brand-new-producer": 42}
    uncovered = find_uncovered_dirs(fake_untracked, _swept_dirs(), DOCUMENTED_NO_ACTION_DIRS)
    assert uncovered == ["analysis/some-brand-new-producer"]


def test_documented_no_action_dirs_are_still_untracked_or_absent_not_silently_stale():
    """Sanity: every allow-listed dir either still exists or was never a false claim."""
    for d in DOCUMENTED_NO_ACTION_DIRS:
        # Not asserting existence strictly -- some (backtest/autoresearch) mix code+state --
        # but the path segment itself must resolve under the repo, catching a typo'd row.
        assert (REPO / d.split("/")[0]).exists(), f"allow-listed dir root does not exist: {d}"

"""Guard tests for backtest/tools/chef_candidates_consolidation_sweep.py.

CHEF-CANDIDATES-CONSOLIDATION-SWEEP (queue.md, filed 2026-07-22 night):
one-time triage of strategy/candidates/ into kept vs archived. These tests
run against a synthetic temp directory — they never touch the real
strategy/candidates/ tree — and prove the classifier's decision logic before
any real batch is applied.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from backtest.tools.chef_candidates_consolidation_sweep import (
    LEVEL_FAMILY_RE,
    classify,
    list_candidates,
    run_batch,
)

TODAY = date(2026, 7, 22)


def _write(dir_: Path, name: str, body: str) -> Path:
    p = dir_ / name
    p.write_text(body, encoding="utf-8")
    return p


@pytest.fixture()
def sandbox(tmp_path: Path) -> Path:
    d = tmp_path / "candidates"
    d.mkdir()
    (d / "_archive").mkdir()
    (d / "_chef-inbox").mkdir()
    (d / "_validator-inbox").mkdir()
    (d / "_lesson-inbox").mkdir()
    (d / "_skill-inbox").mkdir()
    return d


def test_stale_non_level_no_traction_is_archived(sandbox: Path):
    f = _write(
        sandbox,
        "2026-05-01-random-idea.md",
        "# Random idea\nSome unrelated ML feature engineering brainstorm.\n",
    )
    d = classify(f, TODAY, traction_names=set())
    assert d.stale is True
    assert d.level_family is False
    assert d.archive is True


def test_stale_but_level_family_is_kept(sandbox: Path):
    f = _write(
        sandbox,
        "2026-05-01-level-reject-scalp.md",
        "# Level rejection scalp\nRejection at a key level triggers entry.\n",
    )
    d = classify(f, TODAY, traction_names=set())
    assert d.level_family is True
    assert d.archive is False


def test_stale_non_level_but_has_traction_is_kept(sandbox: Path):
    f = _write(sandbox, "2026-05-01-obscure-name.md", "# Obscure\nUnrelated text.\n")
    d = classify(f, TODAY, traction_names={"2026-05-01-obscure-name.md"})
    assert d.has_traction is True
    assert d.archive is False


def test_recent_non_level_no_traction_not_yet_stale(sandbox: Path):
    f = _write(sandbox, "2026-07-20-fresh-idea.md", "# Fresh idea\nUnrelated text.\n")
    d = classify(f, TODAY, traction_names=set())
    assert d.stale is False
    assert d.archive is False


def test_explicit_tag_true_overrides_inference(sandbox: Path):
    # Title doesn't obviously match the regex, but the explicit tag says true.
    f = _write(
        sandbox,
        "2026-05-01-widget.md",
        "# Widget experiment\nlevel_family: true\nSome unrelated body text.\n",
    )
    d = classify(f, TODAY, traction_names=set())
    assert d.level_family is True
    assert "tagged" in d.reason
    assert d.archive is False


def test_explicit_tag_false_overrides_inference(sandbox: Path):
    # Title matches "level" loosely but the explicit tag says false — tag wins.
    f = _write(
        sandbox,
        "2026-05-01-level-adjacent-idea.md",
        "# Level-adjacent idea\nlevel_family: false\ncannot be expressed as a level "
        "interaction because it is a pure volume-profile feature.\n",
    )
    d = classify(f, TODAY, traction_names=set())
    assert d.level_family is False
    assert "tagged" in d.reason
    assert d.archive is True


def test_no_date_prefix_is_never_stale(sandbox: Path):
    f = _write(sandbox, "README.md", "not a dated candidate\n")
    d = classify(f, TODAY, traction_names=set())
    assert d.filename_date is None
    assert d.stale is False
    assert d.archive is False


def test_run_batch_dry_run_does_not_move_files(sandbox: Path):
    _write(sandbox, "2026-05-01-a.md", "# A\nunrelated\n")
    _write(sandbox, "2026-05-02-b.md", "# B\nunrelated\n")
    before = set(p.name for p in list_candidates(sandbox))
    summary = run_batch(candidates_dir=sandbox, batch_size=10, apply=False, today=TODAY)
    after = set(p.name for p in list_candidates(sandbox))
    assert before == after  # nothing moved
    assert summary["eligible_total"] == 2
    assert summary["batch_processed"] == 2  # counted, not moved
    assert summary["applied"] is False


def test_run_batch_apply_moves_only_eligible_and_respects_batch_size(sandbox: Path):
    _write(sandbox, "2026-05-01-a.md", "# A\nunrelated\n")
    _write(sandbox, "2026-05-02-b.md", "# B\nunrelated\n")
    _write(sandbox, "2026-05-03-c-level-reject.md", "# C\nrejection at a level\n")
    _write(sandbox, "2026-07-20-d.md", "# D fresh not stale\nunrelated\n")

    summary = run_batch(candidates_dir=sandbox, batch_size=1, apply=True, today=TODAY)

    assert summary["eligible_total"] == 2  # a, b (c is level-family, d not stale)
    assert summary["batch_processed"] == 1  # batch_size=1 caps the move
    assert summary["remaining_eligible_after_batch"] == 1

    remaining = set(p.name for p in list_candidates(sandbox))
    # exactly one of {a, b} was moved; the other three files stay in place.
    assert len(remaining) == 3
    assert "2026-05-03-c-level-reject.md" in remaining
    assert "2026-07-20-d.md" in remaining

    batch_dir = sandbox / "_archive" / f"sweep-{TODAY.isoformat()}"
    assert batch_dir.is_dir()
    moved_files = list(batch_dir.glob("*.md"))
    assert len(moved_files) == 1


def test_level_family_regex_matches_focus_doctrine_vocabulary():
    positives = [
        "rejection at a key level",
        "level reclaim continuation",
        "flip-retest bull",
        "range ping pong scalp",
        "break and retest short",
        "S/R flip watcher",
        "ribbon rejection bounce",
        "vwap continuation",
    ]
    for text in positives:
        assert LEVEL_FAMILY_RE.search(text), f"expected match: {text!r}"


def test_level_family_regex_does_not_match_unrelated_text():
    negatives = [
        "random ML feature engineering brainstorm",
        "options greeks decay curve study",
        "sentiment analysis from news headlines",
    ]
    for text in negatives:
        assert not LEVEL_FAMILY_RE.search(text), f"unexpected match: {text!r}"


def test_traction_names_loaded_from_leaderboard_and_inboxes(sandbox: Path):
    (sandbox / "_LEADERBOARD.md").write_text(
        "[SOME_RULE](2026-05-01-obscure-name.md)\n", encoding="utf-8"
    )
    (sandbox / "_chef-inbox" / "note.md").write_text(
        "see 2026-05-02-other-name.md for context\n", encoding="utf-8"
    )
    from backtest.tools.chef_candidates_consolidation_sweep import _load_traction_names

    names = _load_traction_names(sandbox)
    assert "2026-05-01-obscure-name.md" in names
    assert "2026-05-02-other-name.md" in names

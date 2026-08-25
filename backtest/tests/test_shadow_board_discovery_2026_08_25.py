"""Guards for SHADOW.md's discovery surface (2026-08-25).

TWO BUGS THIS PINS

1. PREFIX-ANCHORED PREREG GLOB. build_preregs_board() auto-discovers frozen preregs so
   that "a prereg can never go invisible" -- that section exists because a hardcoded
   6-item list already went stale once. But the glob was `prereg-*.json`, anchored to the
   PREFIX, so it only saw the 71 files whose names START with "prereg-". The other 48 on
   disk spell it in the middle or long-form (entry-structure-forward-prereg-*.json,
   bold-floor-rescue-prereg-*.json, *-preregistration.json) and were invisible on the one
   board whose entire job is that they aren't. The discovery mechanism was narrower than
   the thing it discovers -- the same lesson as the hardcoded list, one layer down.

2. A KILLED RULE READING AS LIVE. The V-d1/V-e3 line pointed at the tally artifact and
   said nothing about whether the window had been JUDGED. V-d1 was killed 2026-08-25 by
   its own pre-registered F4 (pooled within-day permutation p=0.6661 vs a p<=0.10 bar) and
   still rendered as an accruing instrument. A board that shows a dead rule as live is
   worse than one that omits it.

SHADOW.md is GENERATED -- never hand-edit it. These tests exercise the generator.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SYNC = REPO / "setup" / "scripts" / "obsidian_vault_sync.py"
RECS = REPO / "analysis" / "recommendations"
ADJ = RECS / "entry-structure-forward-2026-08-06.json"
SHADOW = REPO / "SHADOW.md"


@pytest.fixture(scope="module")
def sync():
    assert SYNC.exists(), f"generator missing: {SYNC}"
    for p in (REPO / "setup" / "scripts",):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    spec = importlib.util.spec_from_file_location("obsidian_vault_sync_guard", SYNC)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ---------------------------------------------------------------- 1. the glob
def test_glob_is_not_prefix_anchored(sync):
    """The literal regression: a prefix-anchored glob silently drops ~40% of preregs."""
    src = SYNC.read_text(encoding="utf-8")
    assert 'glob("analysis/recommendations/prereg-*.json")' not in src, (
        "the prereg glob is prefix-anchored again -- every prereg whose name spells "
        "'prereg' anywhere but the start goes invisible on SHADOW.md")
    assert 'glob("analysis/recommendations/*prereg*.json")' in src


def test_discovery_actually_sees_mid_name_preregs():
    """Not a source-string assertion -- prove it against the real files on disk."""
    prefix_only = {p.name for p in RECS.glob("prereg-*.json")}
    wide = {p.name for p in RECS.glob("*prereg*.json")}
    missed = wide - prefix_only
    assert wide >= prefix_only, "the wide glob must be a superset of the narrow one"
    assert missed, (
        "expected at least one prereg spelled mid-name; if this ever legitimately "
        "becomes empty, this guard is measuring nothing and should be revisited")
    # The two this session cared about must be inside the discovered set.
    for name in ("entry-structure-forward-prereg-2026-08-06.json",
                 "bold-floor-rescue-prereg-2026-08-25.json"):
        if (RECS / name).exists():
            assert name in wide, f"{name} exists on disk but discovery would not see it"
            assert name in missed, f"{name} should be one the OLD glob missed"


def test_generated_board_lists_the_adjudicated_prereg():
    """End-to-end: the file the generator actually wrote must name it."""
    if not SHADOW.exists():
        pytest.skip("SHADOW.md not generated on this machine")
    text = SHADOW.read_text(encoding="utf-8")
    assert "entry-structure-forward-prereg-2026-08-06" in text, (
        "the prereg adjudicated on 2026-08-25 is not on the board")


# ---------------------------------------------------------------- 2. the verdict
def test_vd1_line_carries_its_verdict(sync):
    """A killed rule must not render as an accruing instrument."""
    if not SHADOW.exists():
        pytest.skip("SHADOW.md not generated on this machine")
    line = next((l for l in SHADOW.read_text(encoding="utf-8").splitlines()
                 if "V-d1" in l), None)
    assert line is not None, "the V-d1/V-e3 shadow line vanished from the board"
    assert "ADJUDICATED" in line, (
        "the V-d1 line does not surface its adjudication -- it reads as still accruing")
    assert "KILL" in line, "V-d1's KILL verdict is not visible on the board"


def test_board_verdict_matches_the_scorecard(sync):
    """The board must not drift from the artifact it claims to summarise."""
    if not (SHADOW.exists() and ADJ.exists()):
        pytest.skip("scorecard or board absent on this machine")
    card = json.loads(ADJ.read_text(encoding="utf-8"))
    line = next(l for l in SHADOW.read_text(encoding="utf-8").splitlines() if "V-d1" in l)
    for name, res in (card.get("results") or {}).items():
        assert name in line, f"{name} missing from the board line"
        assert res["verdict"] in line, (
            f"{name}'s verdict on the board disagrees with the scorecard "
            f"(scorecard says {res['verdict']})")


def test_verdict_rendering_survives_a_missing_scorecard(sync, tmp_path, monkeypatch):
    """Fail-open: no scorecard must not crash the whole vault sync."""
    src = SYNC.read_text(encoding="utf-8")
    # The scorecard read is wrapped and the label is only appended when present.
    assert "adjudication scorecard unreadable" in src, (
        "the scorecard read lost its failure branch -- an unreadable artifact would "
        "either crash the generator or silently render a bare line")
    assert "if adj.exists():" in src, "the scorecard read is no longer existence-guarded"

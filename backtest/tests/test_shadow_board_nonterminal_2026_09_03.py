"""Guard for the SHADOW-BOARD-NONTERMINAL fix (2026-09-03).

THE BUG (found by test_shadow_board_discovery_2026_08_25.py::
test_generated_board_lists_the_adjudicated_prereg going RED on the 2026-09-03 full-suite
run): build_preregs_board() sorted `analysis/recommendations/*prereg*.json` by mtime and
printed only the first 25. That is a SECOND, subtler version of the exact bug the 2026-08-25
test file already pinned once (prefix-anchored glob hiding preregs) -- a recency cap on the
board whose whole job is "every frozen prereg at one glance" hides exactly what it exists to
show. Tonight's status reconciliations bumped enough OTHER files' mtimes to push
entry-structure-forward-prereg-2026-08-06.json (FROZEN_PREREG_FORWARD, adjudicated
2026-08-25) off the top-25 window.

THE FIX: classify by STATUS instead of capping by recency. TERMINAL_STATUS_RE /
PENDING_STATUS_RE / _status_field / _age_days are imported from prereg_hygiene.py (not
copied) -- that module already enumerated the full status vocabulary from all 128 real
prereg files on disk. Every non-terminal prereg is listed, uncapped; only preregs whose
status carries an EXPLICIT terminal token collapse into one summary line.

SHADOW.md is GENERATED -- never hand-edit it. These tests exercise the generator directly
against a synthetic fixture (30 pending + 10 terminal preregs) so they don't depend on
whatever happens to be on disk today.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SYNC = REPO / "setup" / "scripts" / "obsidian_vault_sync.py"
HYGIENE = REPO / "setup" / "scripts" / "prereg_hygiene.py"


@pytest.fixture(scope="module")
def sync():
    assert SYNC.exists(), f"generator missing: {SYNC}"
    scripts_dir = REPO / "setup" / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    spec = importlib.util.spec_from_file_location("obsidian_vault_sync_nonterminal_guard", SYNC)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def hygiene():
    scripts_dir = REPO / "setup" / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    spec = importlib.util.spec_from_file_location("prereg_hygiene_nonterminal_guard", HYGIENE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# A limited vocabulary, repeated -- matches the real corpus (a handful of distinct status
# strings shared across many files, not 40 unique sentences).
_PENDING_STATUSES = [
    "FROZEN_PREREG_FORWARD",
    "PARKED -- BLOCKED ON J SIGN-OFF",
    "FROZEN_PENDING_RUN",
    "PRE-REGISTERED",
]
_TERMINAL_STATUSES = [
    "RUN_COMPLETE -- KILL",
    "KILLED",
    "SUPERSEDED",
    # Contains the substring FROZEN -- must still classify TERMINAL (TERMINAL_STATUS_RE
    # must win over PENDING_STATUS_RE on conflict, per prereg_hygiene's own docstring).
    "RETIRED_UNRUNNABLE_AS_FROZEN -- not a verdict on the hypothesis",
]


def _make_fixture(base: Path, n_pending: int = 30, n_terminal: int = 10) -> tuple[list[str], list[str]]:
    """Writes n_pending + n_terminal prereg json files under base/analysis/recommendations.

    Mtimes are staggered so that a NAIVE "sort by mtime, take top 25" board (the old,
    buggy implementation) would keep every terminal file and only the 15 most-recent
    pending files -- dropping 15 of the 30 pending ones. This is not a hypothetical: it is
    the literal shape of the 2026-09-03 production bug (status reconciliations bumping
    mtimes on files unrelated to the one that needed to stay visible).
    """
    recs = base / "analysis" / "recommendations"
    recs.mkdir(parents=True, exist_ok=True)
    now = time.time()
    pending_ids: list[str] = []
    terminal_ids: list[str] = []

    for i in range(n_pending):
        pid = f"pending-fixture-{i:03d}"
        pending_ids.append(pid)
        status = _PENDING_STATUSES[i % len(_PENDING_STATUSES)]
        data = {
            "prereg_id": pid,
            "status": status,
            "frozen_at_et": f"2026-08-{(i % 28) + 1:02d}T09:00:00",
        }
        p = recs / f"{pid}-prereg.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        # oldest mtime among ALL 40 files -- the old top-25-by-mtime cap drops these first.
        os.utime(p, (now - 100 - i, now - 100 - i))

    for i in range(n_terminal):
        pid = f"terminal-fixture-{i:03d}"
        terminal_ids.append(pid)
        status = _TERMINAL_STATUSES[i % len(_TERMINAL_STATUSES)]
        data = {
            "prereg_id": pid,
            "status": status,
            "frozen_at_et": f"2026-07-{(i % 28) + 1:02d}T09:00:00",
        }
        p = recs / f"{pid}-prereg.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        # newest mtimes -- these are exactly what pushed the real prereg off the board.
        os.utime(p, (now - i, now - i))

    return pending_ids, terminal_ids


@pytest.fixture
def fixture_repo(tmp_path, monkeypatch, sync):
    pending_ids, terminal_ids = _make_fixture(tmp_path)
    monkeypatch.setattr(sync, "REPO", tmp_path)
    text = sync.build_preregs_board("test-stamp")
    return text, pending_ids, terminal_ids


# --------------------------------------------------------------- 1. every pending is listed
def test_all_pending_listed_regardless_of_mtime(fixture_repo):
    """The literal regression: the old mtime-desc top-25 cap would drop 15 of these 30."""
    text, pending_ids, _terminal_ids = fixture_repo
    missing = [pid for pid in pending_ids if f"`{pid}`" not in text]
    assert not missing, (
        f"{len(missing)}/{len(pending_ids)} non-terminal preregs missing from the board "
        f"despite an explicit pending status -- the recency cap is back: {missing[:5]}")


# --------------------------------------------------------------- 2. terminal collapse
def test_terminal_preregs_collapsed_with_count(fixture_repo):
    text, _pending_ids, terminal_ids = fixture_repo
    assert f"terminal ({len(terminal_ids)}" in text or f"{len(terminal_ids)} terminal prereg" in text, (
        "terminal count is not surfaced on the board")
    # Only the 5 most recent terminal ids should be individually named -- the rest must be
    # summarised by count, never silently dropped without a trace.
    named = [pid for pid in terminal_ids if f"`{pid}`" in text]
    assert 0 < len(named) <= 5, (
        f"expected at most 5 terminal preregs individually named, found {len(named)}: {named}")
    assert f"+{len(terminal_ids) - len(named)} more" in text or len(terminal_ids) <= 5, (
        "the uncollapsed remainder of terminal preregs is not accounted for")


def test_terminal_status_wins_over_frozen_substring(fixture_repo):
    """RETIRED_UNRUNNABLE_AS_FROZEN contains the substring FROZEN but must classify TERMINAL."""
    text, pending_ids, terminal_ids = fixture_repo
    retired_ids = [pid for i, pid in enumerate(terminal_ids)
                   if _TERMINAL_STATUSES[i % len(_TERMINAL_STATUSES)].startswith("RETIRED")]
    assert retired_ids, "fixture must include at least one RETIRED_UNRUNNABLE_AS_FROZEN case"
    for pid in retired_ids:
        assert f"`{pid}`" not in text.split("## Frozen preregs — terminal")[0].split(
            "## Frozen preregs — auto-discovered")[1], (
            f"{pid} (RETIRED_UNRUNNABLE_AS_FROZEN) leaked into the non-terminal list")


# --------------------------------------------------------------- 3. status token on each row
def test_status_token_present_on_nonterminal_rows(fixture_repo):
    text, pending_ids, _terminal_ids = fixture_repo
    for status in _PENDING_STATUSES:
        assert f"`{status}`" in text, f"status token {status!r} never rendered on the board"


# --------------------------------------------------------------- 4. vocabulary is IMPORTED, not copied
def test_status_regexes_are_the_same_object_as_prereg_hygiene(sync, hygiene):
    """Identity check -- proves the board reuses prereg_hygiene's compiled regex objects
    rather than a hand-copied duplicate that could silently drift out of sync."""
    # Identity is checked against the module object the generator ACTUALLY imported
    # (sys.modules["prereg_hygiene"]); the file-loaded `hygiene` fixture is a separate
    # module object by construction, so it is compared by PATTERN (drift check). In the
    # full suite another test populates sys.modules["prereg_hygiene"] first, which made
    # the old `is hygiene.X` form order-dependent (GuardsFull 2026-09-03 05:52 ET).
    live = sys.modules["prereg_hygiene"]
    assert sync.PENDING_STATUS_RE is live.PENDING_STATUS_RE, (
        "PENDING_STATUS_RE was copied, not imported from prereg_hygiene")
    assert sync.TERMINAL_STATUS_RE is live.TERMINAL_STATUS_RE, (
        "TERMINAL_STATUS_RE was copied, not imported from prereg_hygiene")
    assert sync.PENDING_STATUS_RE.pattern == hygiene.PENDING_STATUS_RE.pattern
    assert sync.TERMINAL_STATUS_RE.pattern == hygiene.TERMINAL_STATUS_RE.pattern


def test_source_imports_from_prereg_hygiene():
    src = SYNC.read_text(encoding="utf-8")
    assert "from prereg_hygiene import" in src, (
        "build_preregs_board's status vocabulary must be imported from prereg_hygiene.py, "
        "never hand-copied")


# --------------------------------------------------------------- 5. grouped mode when > 60
def test_grouped_when_nonterminal_exceeds_60(tmp_path, monkeypatch, sync):
    pending_ids, terminal_ids = _make_fixture(tmp_path, n_pending=70, n_terminal=5)
    monkeypatch.setattr(sync, "REPO", tmp_path)
    text = sync.build_preregs_board("test-stamp")
    missing = [pid for pid in pending_ids if f"`{pid}`" not in text]
    assert not missing, (
        f"grouped mode dropped {len(missing)} non-terminal preregs -- 'never truncate "
        f"silently' violated: {missing[:5]}")
    for status in _PENDING_STATUSES:
        assert f"### `{status}`" in text, f"grouped mode missing a heading for {status!r}"


# --------------------------------------------------------------- 6. HOME.md / MAP.md isolation
def test_home_and_map_builders_do_not_reference_the_new_prereg_symbols(sync):
    """Static isolation guard: build_home/build_map must not read the status-vocabulary
    symbols this fix introduced, so a change scoped to build_preregs_board cannot alter
    HOME.md/MAP.md output. The real byte-identical check is the before/after file hash
    comparison run manually alongside `python setup/scripts/obsidian_vault_sync.py`."""
    src = SYNC.read_text(encoding="utf-8")
    home_start = src.index("def build_home(")
    home_end = src.index("\ndef ", home_start + 1)
    home_src = src[home_start:home_end]
    map_start = src.index("def build_map(")
    map_end = src.index("\ndef ", map_start + 1)
    map_src = src[map_start:map_end]
    for sym in ("PENDING_STATUS_RE", "TERMINAL_STATUS_RE", "_prereg_status_field", "_prereg_age_days"):
        assert sym not in home_src, f"build_home unexpectedly references {sym}"
        assert sym not in map_src, f"build_map unexpectedly references {sym}"

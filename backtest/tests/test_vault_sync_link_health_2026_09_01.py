"""Guard for the vault link-health resolver (W4, 2026-09-01).

MAP.md reported 58 "broken wikilinks", almost all of the shape
SHADOW.md -> [[analysis/recommendations/<prereg>]] where the target exists on disk as
<prereg>.json (a prereg receipt), not <prereg>.md. `_visible_md()` indexes only *.md files
and the old resolver in `build_link_health()` only ever probed `target + ".md"`, so every
extensionless link to a real .json artifact was misreported as dangling.

This pins `_resolve_wikilink_target()`: it must accept an extensionless target that exists
as .md OR .json OR exactly as written on disk, while STILL flagging a target that resolves
to nothing anywhere as genuinely broken (the fix must not silently launder real breakage).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "setup" / "scripts" / "obsidian_vault_sync.py"


def _load():
    spec = importlib.util.spec_from_file_location("obsidian_vault_sync_lh", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["obsidian_vault_sync_lh"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load()


def test_extensionless_target_resolves_to_existing_json(mod, tmp_path):
    """[[analysis/recommendations/foo-prereg]] must resolve when foo-prereg.json exists."""
    (tmp_path / "analysis" / "recommendations").mkdir(parents=True)
    (tmp_path / "analysis" / "recommendations" / "foo-prereg.json").write_text("{}")
    resolved = mod._resolve_wikilink_target(
        "analysis/recommendations/foo-prereg", relset=set(), by_stem={}, repo=tmp_path,
    )
    assert resolved == "analysis/recommendations/foo-prereg.json"


def test_extensionless_target_still_prefers_md_when_both_exist(mod, tmp_path):
    """A real markdown note with the same stem wins over a same-named .json artifact."""
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "topic.json").write_text("{}")
    relset = {"notes/topic.md"}
    resolved = mod._resolve_wikilink_target(
        "notes/topic", relset=relset, by_stem={}, repo=tmp_path,
    )
    assert resolved == "notes/topic.md"


def test_target_matching_nothing_stays_broken(mod, tmp_path):
    """A target with no .md, no .json, and no on-disk file anywhere is genuinely broken."""
    resolved = mod._resolve_wikilink_target(
        "analysis/recommendations/does-not-exist-anywhere",
        relset=set(), by_stem={}, repo=tmp_path,
    )
    assert resolved is None


def test_explicit_extension_target_resolves_exactly(mod, tmp_path):
    """A target written with its own extension (e.g. a .png) resolves as-is when present."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "diagram.png").write_text("x")
    resolved = mod._resolve_wikilink_target(
        "assets/diagram.png", relset=set(), by_stem={}, repo=tmp_path,
    )
    assert resolved == "assets/diagram.png"


def test_build_link_health_no_longer_flags_json_preregs(mod, tmp_path, monkeypatch):
    """End-to-end: a SHADOW-style note linking a .json prereg reports zero broken links."""
    monkeypatch.setattr(mod, "REPO", tmp_path)
    (tmp_path / "analysis" / "recommendations").mkdir(parents=True)
    (tmp_path / "analysis" / "recommendations" / "some-prereg-2026-08-28.json").write_text("{}")
    shadow = tmp_path / "SHADOW.md"
    shadow.write_text(
        "See [[analysis/recommendations/some-prereg-2026-08-28]] for the prereg.\n"
    )
    health = mod.build_link_health([shadow])
    assert health["broken"] == [], f"expected no broken links, got {health['broken']}"

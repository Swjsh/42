"""Guards for setup/scripts/obsidian_vault_sync.py (Obsidian reading surface, 2026-08-09).

The two properties that actually matter and would silently rot:

1. NON-DESTRUCTIVE. The daily note is written by Gamma_Premarket (bias, levels, hypothesis) and
   sometimes by J. This script must only ever touch (a) the frontmatter keys it owns and (b) the
   region between the GAMMA-EOD markers. If a refactor makes it clobber the premarket section or
   a human's notes, that is silent data loss on a file nobody re-reads until they need it.

2. IDEMPOTENT. It runs on a schedule; running twice must not append a second EOD block or
   duplicate frontmatter keys. Append-on-every-run is the classic failure for marker-delimited
   generators and it degrades slowly enough that nobody notices for weeks.

Also pinned: fail-open (a broker outage must degrade to a stated line, never raise) and that the
frontmatter carries the Bases-queryable keys -- Obsidian Bases reads ONLY note properties, so if
those keys stop being emitted every downstream .base view silently empties.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "setup" / "scripts" / "obsidian_vault_sync.py"


def _load():
    spec = importlib.util.spec_from_file_location("obsidian_vault_sync", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["obsidian_vault_sync"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_script_exists():
    assert SCRIPT.exists(), f"missing {SCRIPT}"


def test_frontmatter_upsert_preserves_foreign_keys():
    """A key we do NOT own must survive verbatim."""
    m = _load()
    body = "---\nauthor: jack\nmood: focused\n---\n# 2026-08-07\n\nhand-written notes\n"
    out = m.upsert_frontmatter(body, {"date": "2026-08-07", "pnl_book": "-2692.06"})
    assert "author: jack" in out
    assert "mood: focused" in out
    assert "date: 2026-08-07" in out
    assert "hand-written notes" in out


def test_frontmatter_upsert_is_idempotent():
    """Running twice must not duplicate the keys we own."""
    m = _load()
    body = "# 2026-08-07\n\nbody\n"
    once = m.upsert_frontmatter(body, {"date": "2026-08-07", "pnl_book": "1.00"})
    twice = m.upsert_frontmatter(once, {"date": "2026-08-07", "pnl_book": "1.00"})
    assert twice.count("date: 2026-08-07") == 1, "frontmatter key duplicated on re-run"
    assert twice.count("pnl_book:") == 1
    assert twice.count("---") == 2, "a second frontmatter fence was emitted"


def test_frontmatter_upsert_updates_owned_key_rather_than_appending():
    m = _load()
    body = m.upsert_frontmatter("# d\n", {"pnl_book": "1.00"})
    updated = m.upsert_frontmatter(body, {"pnl_book": "-2692.06"})
    assert "pnl_book: -2692.06" in updated
    assert "pnl_book: 1.00" not in updated


def test_eod_markers_are_distinct_and_present():
    m = _load()
    assert m.EOD_BEGIN != m.EOD_END
    assert "GAMMA-EOD:BEGIN" in m.EOD_BEGIN
    assert "GAMMA-EOD:END" in m.EOD_END


def test_eod_block_replacement_does_not_touch_surrounding_text(tmp_path, monkeypatch):
    """The premarket section above and any human text below must survive a regeneration."""
    m = _load()
    monkeypatch.setattr(m, "JOURNAL", tmp_path)
    monkeypatch.setattr(m, "fills_for", lambda d: {})
    monkeypatch.setattr(m, "engine_view", lambda d: {"ticks": 0, "verdicts": {}, "last": None})
    snap = {"ok": True, "arms": {a: {"equity": 1.0, "day": 0.0, "positions": [], "error": None}
                                 for a in m.ARMS}, "total_day": 0.0, "error": None}

    note = tmp_path / "2026-08-07.md"
    note.write_text(
        "# 2026-08-07 — Premarket\n\n- **Bias:** bearish\n\n"
        f"{m.EOD_BEGIN}\nSTALE CONTENT\n{m.EOD_END}\n\n## My own notes\nkeep me\n",
        encoding="utf-8",
    )
    m.write_daily("2026-08-07", "stamp", snap)
    out = note.read_text(encoding="utf-8")

    assert "**Bias:** bearish" in out, "premarket section was destroyed"
    assert "## My own notes\nkeep me" in out, "human-written trailing section was destroyed"
    assert "STALE CONTENT" not in out, "stale generated block was not replaced"
    assert out.count(m.EOD_BEGIN) == 1, "duplicate EOD block appended"


def test_write_daily_twice_is_idempotent(tmp_path, monkeypatch):
    m = _load()
    monkeypatch.setattr(m, "JOURNAL", tmp_path)
    monkeypatch.setattr(m, "fills_for", lambda d: {})
    monkeypatch.setattr(m, "engine_view", lambda d: {"ticks": 0, "verdicts": {}, "last": None})
    snap = {"ok": True, "arms": {a: {"equity": 1.0, "day": 0.0, "positions": [], "error": None}
                                 for a in m.ARMS}, "total_day": 0.0, "error": None}
    m.write_daily("2026-08-07", "s1", snap)
    first = (tmp_path / "2026-08-07.md").read_text(encoding="utf-8")
    m.write_daily("2026-08-07", "s1", snap)
    second = (tmp_path / "2026-08-07.md").read_text(encoding="utf-8")
    assert first == second, "second identical run changed the file"
    assert second.count(m.EOD_BEGIN) == 1


def test_daily_note_emits_bases_queryable_properties(tmp_path, monkeypatch):
    """Obsidian Bases reads ONLY frontmatter -- losing these keys silently empties every view."""
    m = _load()
    monkeypatch.setattr(m, "JOURNAL", tmp_path)
    monkeypatch.setattr(m, "fills_for", lambda d: {})
    monkeypatch.setattr(m, "engine_view", lambda d: {"ticks": 5, "verdicts": {"HOLD": 5}, "last": {}})
    snap = {"ok": True, "arms": {a: {"equity": 1.0, "day": -3.0, "positions": [], "error": None}
                                 for a in m.ARMS}, "total_day": -15.0, "error": None}
    m.write_daily("2026-08-07", "stamp", snap)
    out = (tmp_path / "2026-08-07.md").read_text(encoding="utf-8")
    for key in ("date:", "pnl_book:", "legs:", "engine_ticks:", "flat_at_write:"):
        assert key in out, f"Bases property {key!r} missing from daily note frontmatter"
    for arm in m.ARMS:
        assert f"pnl_{arm.replace('-', '')}:" in out, f"per-arm property for {arm} missing"


def test_broker_failure_fails_open_not_raises():
    """A broker outage must degrade the report, never raise into the caller (C7)."""
    m = _load()
    out = m.render_positions_table({"ok": False, "error": "creds unavailable", "arms": {},
                                    "total_day": 0.0})
    assert any("unavailable" in ln for ln in out)


def test_home_renders_with_a_dead_broker(tmp_path, monkeypatch):
    m = _load()
    monkeypatch.setattr(m, "engine_view", lambda d: {"ticks": 0, "verdicts": {}, "last": None})
    monkeypatch.setattr(m, "STATE", tmp_path)  # no key-levels/bias -> must not crash
    html = m.build_home("2026-08-07", "stamp", False, {"ok": False, "error": "boom",
                                                       "arms": {}, "total_day": 0.0})
    assert "Gamma — HOME" in html
    assert "unavailable" in html


def test_wikilink_regex_handles_table_escaped_pipe():
    """[[x\\|alias]] is correct Obsidian syntax inside tables -- the target must not keep the
    backslash (the first checker run reported its own HOME.md week-table as 7 broken links)."""
    m = _load()
    hit = m.WIKILINK_RE.search("| [[journal/2026-08-09\\|2026-08-09]] |")
    assert hit is not None
    target = hit.group(1).strip().rstrip("\\")
    assert target == "journal/2026-08-09", f"escaped pipe leaked into target: {target!r}"


def test_link_health_resolves_frontmatter_aliases(tmp_path, monkeypatch):
    """Memory notes are linked by their name: slug, not filename -- resolution must honor it
    exactly as Obsidian honors aliases, or the mirror reports 50+ false broken links."""
    m = _load()
    a = tmp_path / "feedback_some_thing_2026.md"
    a.write_text('---\nname: some-thing\n---\nbody\n', encoding="utf-8")
    b = tmp_path / "linker.md"
    b.write_text("see [[some-thing]]\n", encoding="utf-8")
    monkeypatch.setattr(m, "REPO", tmp_path)
    health = m.build_link_health([a, b])
    assert health["broken"] == [], f"alias not resolved: {health['broken']}"


def test_visible_md_ignore_is_root_anchored(tmp_path, monkeypatch):
    """Match-anywhere exclusion once hid markdown/doctrine/ (Lessons-Learned!) because the
    legacy ROOT folder 'doctrine/' was excluded. Semantics must be root-anchored, like
    Obsidian's own userIgnoreFilters."""
    m = _load()
    (tmp_path / "doctrine").mkdir()
    (tmp_path / "doctrine" / "legacy.md").write_text("x", encoding="utf-8")
    (tmp_path / "markdown" / "doctrine").mkdir(parents=True)
    (tmp_path / "markdown" / "doctrine" / "LESSONS.md").write_text("x", encoding="utf-8")
    cfg = tmp_path / "app.json"
    cfg.write_text('{"userIgnoreFilters": ["doctrine/"]}', encoding="utf-8")
    monkeypatch.setattr(m, "REPO", tmp_path)
    visible = {str(p.relative_to(tmp_path)).replace("\\", "/") for p in m._visible_md(cfg)}
    assert "doctrine/legacy.md" not in visible, "root doctrine/ should be hidden"
    assert "markdown/doctrine/LESSONS.md" in visible, (
        "markdown/doctrine was hidden by a match-anywhere rule -- Lessons-Learned invisible"
    )


def test_folder_hub_respects_vault_visibility(tmp_path, monkeypatch):
    """A hub that links into EXCLUDED folders manufactures broken links instead of curing
    orphans -- first run of the recursive markdown hub produced 70+ this way."""
    m = _load()
    (tmp_path / "docs" / "sub").mkdir(parents=True)
    shown = tmp_path / "docs" / "shown.md"
    shown.write_text("x", encoding="utf-8")
    hidden = tmp_path / "docs" / "sub" / "hidden.md"
    hidden.write_text("x", encoding="utf-8")
    monkeypatch.setattr(m, "REPO", tmp_path)
    out = m.build_folder_index(Path("docs"), "T", "stamp", recursive=True,
                               visible={"docs/shown.md"})
    assert "docs/shown" in out
    assert "hidden" not in out, "hub linked a vault-hidden file -> broken link factory"


def test_ssr_shadow_round_trips_read_producer_key(tmp_path, monkeypatch):
    """ssr_shadow.py (the producer) writes 'n_round_trips' to ssr-shadow-progress.json, NOT
    'n_closed_round_trips'. render_other_lanes() must read the real key -- reading the wrong
    one silently renders '0 round trips' on HOME.md forever even as the ledger accrues real
    trips (regression: 17 round trips on disk, 0 shown on HOME, 2026-08-23)."""
    m = _load()
    state = tmp_path / "automation" / "state"
    (state / "futures").mkdir(parents=True)
    import json
    (state / "futures" / "ssr-shadow-progress.json").write_text(
        json.dumps({"n_round_trips": 17, "total_pnl_usd": 27335.69}), encoding="utf-8")
    monkeypatch.setattr(m, "STATE", state)
    out = "\n".join(m.render_other_lanes())
    assert "17 round trips" in out, f"SSR shadow round-trip count not rendered from producer key:\n{out}"
    assert "0 round trips" not in out


def test_memory_mirror_is_gitignored():
    """PUBLIC repo: the memory mirror carries J's preferences and must never be pushable."""
    gi = (REPO / ".gitignore").read_text(encoding="utf-8", errors="replace")
    assert "memory-mirror/" in gi, "memory-mirror/ not gitignored -- public-repo leak surface"


def test_obsidian_blobs_are_gitignored():
    """Repo is PUBLIC: the 4.4MB vendored plugin JS and conversation-id state must never be pushed."""
    gi = (REPO / ".gitignore").read_text(encoding="utf-8", errors="replace")
    for pat in (".obsidian/workspace.json", ".obsidian/plugins/*/main.js",
                ".obsidian/plugins/*/data.json"):
        assert pat in gi, f"{pat} not gitignored -- public-repo leak surface"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))

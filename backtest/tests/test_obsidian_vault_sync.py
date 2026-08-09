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


def test_obsidian_blobs_are_gitignored():
    """Repo is PUBLIC: the 4.4MB vendored plugin JS and conversation-id state must never be pushed."""
    gi = (REPO / ".gitignore").read_text(encoding="utf-8", errors="replace")
    for pat in (".obsidian/workspace.json", ".obsidian/plugins/*/main.js",
                ".obsidian/plugins/*/data.json"):
        assert pat in gi, f"{pat} not gitignored -- public-repo leak surface"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))

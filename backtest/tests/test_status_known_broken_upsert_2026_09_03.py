"""Guard: status_known_broken.upsert() -- the shared de-duplicating writer for
STATUS.md's '## Known broken' section.

THE BUG (found live 2026-09-03T00:55 ET): several producers each APPEND one line
per fire and never clear or de-duplicate. The live STATUS.md carried 8
`ROSTER-LIVENESS: ...` lines (all the same recurring condition, 2026-09-02T05:37Z
through 16:40Z) and 5 `MCP_AUDIT_*` lines (4 YELLOW + a newer RED), one of which
read "All MCP servers healthy" sitting in the same broken list as three stale
copies of itself. This file pins the fix: a shared upsert() that strips every
prior line for a marker before writing (or clearing) the newest reading, so
exactly one line survives per marker, ever, bounded to the pinned section only.

Tests operate exclusively on tmp copies -- never the live STATUS.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import status_known_broken as skb  # noqa: E402

MARKER = "## Known broken"


def _seed(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "STATUS.md"
    p.write_text(MARKER + "\n\n" + body, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Dedup: writing a marker strips every prior line for that marker
# ---------------------------------------------------------------------------

def test_dedupe_keeps_exactly_one_line_for_the_marker(tmp_path):
    body = (
        "- [2026-09-02T14:14+00:00] ROSTER-LIVENESS: 1 lane(s) permanently DEAD: p::m.\n"
        "- [2026-09-02T15:07+00:00] ROSTER-LIVENESS: 1 lane(s) permanently DEAD: p::m.\n"
        "- [2026-09-02T16:40+00:00] ROSTER-LIVENESS: 1 lane(s) permanently DEAD: p::m.\n"
    )
    p = _seed(tmp_path, body)
    newest = "- [2026-09-02T17:00+00:00] ROSTER-LIVENESS: 1 lane(s) permanently DEAD: p::m."
    changed = skb.upsert("ROSTER-LIVENESS:", newest, status_path=p)
    assert changed is True
    out = p.read_text(encoding="utf-8")
    assert out.count("ROSTER-LIVENESS:") == 1, "must collapse to exactly one line"
    assert "17:00+00:00" in out, "the surviving line must be the newest one written"
    assert "14:14" not in out and "15:07" not in out and "16:40" not in out


def test_dedupe_matches_any_suffix_of_a_shared_prefix_marker(tmp_path):
    """MCP_AUDIT_YELLOW / MCP_AUDIT_RED / MCP_AUDIT_GREEN must all collapse under
    the single marker 'MCP_AUDIT_' -- they are readings of the same probe."""
    body = (
        "- [2026-09-02T06:23:50-04:00] MCP_AUDIT_YELLOW: Alpaca MCP servers not yet available.\n"
        "- [2026-09-02T07:48:41-04:00] MCP_AUDIT_YELLOW: endpoints returning 404.\n"
        "- [2026-09-03T00:03:45 ET] MCP_AUDIT_RED: Alpaca Safe and Bold both 401.\n"
    )
    p = _seed(tmp_path, body)
    newest = "- [2026-09-03T01:00:00 ET] MCP_AUDIT_RED: still 401, unresolved."
    changed = skb.upsert("MCP_AUDIT_", newest, status_path=p)
    assert changed is True
    out = p.read_text(encoding="utf-8")
    assert out.count("MCP_AUDIT_") == 1
    assert "still 401, unresolved" in out


# ---------------------------------------------------------------------------
# Green clears
# ---------------------------------------------------------------------------

def test_green_line_none_clears_the_marker(tmp_path):
    body = "- [2026-09-02T23:50:00-04:00] MCP_AUDIT_YELLOW: All MCP servers healthy.\n"
    p = _seed(tmp_path, body)
    changed = skb.upsert("MCP_AUDIT_", None, status_path=p)
    assert changed is True
    out = p.read_text(encoding="utf-8")
    assert "MCP_AUDIT_" not in out


def test_clearing_an_absent_marker_is_a_true_noop(tmp_path):
    body = "- [2026-09-02T16:40+00:00] ROSTER-LIVENESS: 1 lane(s) permanently DEAD: p::m.\n"
    p = _seed(tmp_path, body)
    before = p.read_bytes()
    changed = skb.upsert("MCP_AUDIT_", None, status_path=p)
    assert changed is False
    assert p.read_bytes() == before


# ---------------------------------------------------------------------------
# Other markers untouched
# ---------------------------------------------------------------------------

def test_other_markers_in_the_section_are_untouched(tmp_path):
    body = (
        "- [2026-09-02T16:40+00:00] ROSTER-LIVENESS: 1 lane(s) permanently DEAD: p::m.\n"
        "- [2026-09-02T23:50:00-04:00] MCP_AUDIT_YELLOW: All MCP servers healthy.\n"
        "- [2026-09-02T00:05 ET] TWIN-GAUNTLET-GAP: unrelated finding.\n"
    )
    p = _seed(tmp_path, body)
    skb.upsert("MCP_AUDIT_", None, status_path=p)
    out = p.read_text(encoding="utf-8")
    assert "ROSTER-LIVENESS: 1 lane(s)" in out
    assert "TWIN-GAUNTLET-GAP: unrelated finding" in out
    assert "MCP_AUDIT_" not in out


# ---------------------------------------------------------------------------
# Lines outside the section are untouched; heading/preamble byte-identical
# ---------------------------------------------------------------------------

def test_content_outside_the_section_is_byte_identical(tmp_path):
    prefix = "## [2026-09-02T10:00 ET] a dated entry\n- some prose\n\n"
    body = "- [2026-09-02T16:40+00:00] ROSTER-LIVENESS: 1 lane(s) permanently DEAD: p::m.\n"
    suffix = "\n## Other section\ncontent that must survive\n"
    p = tmp_path / "STATUS.md"
    # section sits BELOW a dated entry (like the live file's actual shape) and is
    # followed by another '## ' heading -- body bounds must stop there.
    p.write_text(prefix + MARKER + "\n\n" + body + suffix, encoding="utf-8")

    newest = "- [2026-09-02T17:00+00:00] ROSTER-LIVENESS: 1 lane(s) permanently DEAD: p::m."
    skb.upsert("ROSTER-LIVENESS:", newest, status_path=p)
    out = p.read_text(encoding="utf-8")

    assert out.startswith(prefix), "text before the section must be untouched"
    assert out.endswith(suffix), "text after the section (next '## ' heading) must be untouched"
    assert MARKER in out
    assert out.count(MARKER) == 1


def test_heading_and_preamble_note_survive_byte_identical(tmp_path):
    note = ("> **This section is the PREAMBLE.**\n"
           "> Prepend new dated entries BELOW this block.\n")
    body = "- [2026-09-02T14:14+00:00] ROSTER-LIVENESS: 1 lane(s) permanently DEAD: p::m.\n\n" + note
    p = _seed(tmp_path, body)
    skb.upsert("ROSTER-LIVENESS:", "- [2026-09-02T17:00+00:00] ROSTER-LIVENESS: dead: p::m.",
              status_path=p)
    out = p.read_text(encoding="utf-8")
    assert out.startswith(MARKER + "\n\n")
    assert note in out, "preamble note text must be preserved verbatim"


# ---------------------------------------------------------------------------
# Decoy prose containing the heading substring must never be mistaken for the
# real pinned section (writer-side twin of status_retention.py's
# _is_pinned_heading_line fix -- found live 2026-09-03, self-audit gap #3:
# "the producer... has no test... regression will return").
# ---------------------------------------------------------------------------

def test_decoy_prose_line_before_the_real_section_is_not_mistaken_for_it(tmp_path):
    """A prose line mid-sentence containing the literal substring '## Known
    broken' (e.g. this project's own STATUS entries discussing the bug) sits
    BEFORE the real heading. `str.index()` (a plain substring search) matches
    the decoy first and would insert the new line there, orphaned above the
    real section where the next lookup can never find it again. Reproduced
    live: this exact shape wrote a fresh upsert() line above the real heading
    instead of into it."""
    decoy = "discussion: the '## Known broken' section had drifted before.\n\n"
    body = "- [2026-09-02T16:40+00:00] ROSTER-LIVENESS: 1 lane(s) permanently DEAD: p::m.\n"
    p = tmp_path / "STATUS.md"
    p.write_text("# heading\n" + decoy + MARKER + "\n\n" + body, encoding="utf-8")

    changed = skb.upsert("NEWMARKER:", "- [ts] NEWMARKER: hello", status_path=p)
    assert changed is True
    out = p.read_text(encoding="utf-8")

    # Exact-line match for the REAL heading -- out.index(MARKER) is exactly the
    # naive substring search under test and would find the DECOY (which also
    # contains the substring) first, making the ordering assertion tautological.
    lines = out.splitlines()
    real_heading_line_no = next(i for i, ln in enumerate(lines) if ln.rstrip() == MARKER)
    new_line_no = next(i for i, ln in enumerate(lines) if "NEWMARKER: hello" in ln)
    assert new_line_no > real_heading_line_no, (
        "the new line must land AFTER the real heading, not orphaned above it "
        "next to the decoy"
    )
    heading_line_count = sum(1 for ln in lines if ln.rstrip() == MARKER)
    assert heading_line_count == 1, (
        "decoy substring (mid-sentence, not its own line) must not be treated as "
        "a second real heading"
    )
    assert decoy.strip() in out, "the decoy prose itself must survive untouched"


def test_missing_real_heading_with_only_a_decoy_present_is_recreated(tmp_path):
    """If ONLY a decoy substring exists (no real heading line anywhere), the
    naive `MARKER_HEADING not in norm` check would wrongly conclude the
    section already exists (substring match) and skip recreating it --
    `_known_broken_body_bounds` would then raise on the same decoy. Must
    detect 'no REAL heading line' and recreate at the top, same as the
    truly-absent case."""
    decoy = "note: '## Known broken' was discussed here once.\n"
    p = tmp_path / "STATUS.md"
    p.write_text("# heading\n" + decoy, encoding="utf-8")

    changed = skb.upsert("NEWMARKER:", "- [ts] NEWMARKER: hello", status_path=p)
    assert changed is True
    out = p.read_text(encoding="utf-8")
    assert out.startswith(MARKER), "real heading must be recreated at the top"
    heading_line_count = sum(1 for ln in out.splitlines() if ln.rstrip() == MARKER)
    assert heading_line_count == 1, "exactly one real (exact-line) heading, the decoy is prose only"
    assert "NEWMARKER: hello" in out
    assert decoy.strip() in out, "the decoy prose itself must survive untouched"


# ---------------------------------------------------------------------------
# Missing section recreated at top
# ---------------------------------------------------------------------------

def test_missing_section_is_recreated_at_the_top(tmp_path):
    p = tmp_path / "STATUS.md"
    p.write_text("## Something else\n\ncontent here\n", encoding="utf-8")
    changed = skb.upsert("ROSTER-LIVENESS:", "- [2026-09-02T17:00+00:00] ROSTER-LIVENESS: dead.",
                         status_path=p)
    assert changed is True
    out = p.read_text(encoding="utf-8")
    assert out.startswith(MARKER)
    assert "## Something else" in out
    assert "content here" in out
    assert "ROSTER-LIVENESS: dead." in out


def test_a_marker_line_past_the_next_heading_is_history_not_touched(tmp_path):
    """A ROSTER-LIVENESS line that has already rolled into an older dated '## ['
    entry (below the next '## ' heading) is history -- FULL-SUITE-RED-LINE-
    OUTLIVES-GREEN's exact reasoning, generalized. body_end must stop at the
    next heading, or an old archived-style copy gets silently eaten/rewritten."""
    body = "- [2026-09-02T16:40+00:00] ROSTER-LIVENESS: 1 lane(s) permanently DEAD: p::m.\n"
    old_entry = (
        "## [2026-08-01T09:00 ET] an old dated entry\n"
        "- [2026-08-01T09:00+00:00] ROSTER-LIVENESS: this is HISTORY, not live.\n"
    )
    p = tmp_path / "STATUS.md"
    p.write_text(MARKER + "\n\n" + body + old_entry, encoding="utf-8")

    skb.upsert("ROSTER-LIVENESS:", None, status_path=p)  # clear the live one
    out = p.read_text(encoding="utf-8")
    assert "this is HISTORY, not live." in out, "a line past the next heading must survive untouched"
    assert "1 lane(s) permanently DEAD: p::m." not in out, "the live section's line must be cleared"


def test_missing_status_file_fails_soft(tmp_path):
    missing = tmp_path / "nope.md"
    assert skb.upsert("ROSTER-LIVENESS:", "- [ts] ROSTER-LIVENESS: x", status_path=missing) is False


# ---------------------------------------------------------------------------
# CRLF preserved
# ---------------------------------------------------------------------------

def test_crlf_convention_is_preserved(tmp_path):
    body = "- [2026-09-02T14:14+00:00] ROSTER-LIVENESS: 1 lane(s) permanently DEAD: p::m.\r\n"
    raw = (MARKER + "\r\n\r\n" + body).encode("utf-8")
    p = tmp_path / "STATUS.md"
    p.write_bytes(raw)
    skb.upsert("ROSTER-LIVENESS:", "- [2026-09-02T17:00+00:00] ROSTER-LIVENESS: dead: p::m.",
              status_path=p)
    out_bytes = p.read_bytes()
    assert b"\r\n" in out_bytes
    assert b"\n" not in out_bytes.replace(b"\r\n", b""), "no bare LF must be introduced"
    out = out_bytes.decode("utf-8")
    assert out.count("ROSTER-LIVENESS:") == 1


def test_lf_convention_is_preserved(tmp_path):
    body = "- [2026-09-02T14:14+00:00] ROSTER-LIVENESS: 1 lane(s) permanently DEAD: p::m.\n"
    raw = (MARKER + "\n\n" + body).encode("utf-8")
    p = tmp_path / "STATUS.md"
    p.write_bytes(raw)
    skb.upsert("ROSTER-LIVENESS:", "- [2026-09-02T17:00+00:00] ROSTER-LIVENESS: dead: p::m.",
              status_path=p)
    out_bytes = p.read_bytes()
    assert b"\r\n" not in out_bytes, "no CRLF must be introduced into an LF file"


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

def test_cli_line_and_clear(tmp_path, capsys):
    p = tmp_path / "STATUS.md"
    p.write_text(MARKER + "\n\n", encoding="utf-8")
    rc = skb.main(["--marker", "MCP_AUDIT_", "--line",
                  "- [2026-09-03T01:00:00 ET] MCP_AUDIT_RED: still down",
                  "--status-path", str(p)])
    assert rc == 0
    assert "MCP_AUDIT_RED: still down" in p.read_text(encoding="utf-8")

    rc2 = skb.main(["--marker", "MCP_AUDIT_", "--clear", "--status-path", str(p)])
    assert rc2 == 0
    assert "MCP_AUDIT_" not in p.read_text(encoding="utf-8")


def test_cli_rejects_line_and_clear_together(tmp_path):
    p = tmp_path / "STATUS.md"
    p.write_text(MARKER + "\n\n", encoding="utf-8")
    rc = skb.main(["--marker", "X", "--line", "y", "--clear", "--status-path", str(p)])
    assert rc == 2

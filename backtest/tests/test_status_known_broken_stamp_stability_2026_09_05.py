"""Guard (H1, GOAL-RIG-SIGNAL-HYGIENE-2026-09-05): status_known_broken.upsert() must keep
the EXISTING [stamp] when the section is already collapsed to exactly one line for a
marker and the incoming payload (the text after the marker tag) is byte-identical to the
existing one.

THE BUG this pins: engine_health.py re-stamps its RTH-TICK-GAP Known-broken line every
5-min tick with a fresh checked_at_utc even when the underlying finding is unchanged.
conductor_wake_watch.py::scan_known_broken keyed "new entry" on the newest [timestamp]
token, so a re-stamped-but-unchanged line looked like a fresh event every tick and woke
the conductor every 180 min on nothing (live evidence: "EVENT (known-broken) but
DEBOUNCED" x30 the morning of 2026-09-05).

Pre-fix behaviour (what this test proves RED against): upsert() unconditionally stripped
the existing marker line(s) and inserted the new one, so an unchanged finding's stamp
always advanced and `changed` was always True.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import status_known_broken as skb  # noqa: E402

MARKER = "## Known broken"


def _seed(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "STATUS.md"
    p.write_text(MARKER + "\n\n" + body, encoding="utf-8")
    return p


def test_unchanged_payload_keeps_the_existing_stamp(tmp_path):
    """The steady-state case: exactly one existing line for the marker, and the new
    finding's payload is byte-identical -- must be a true no-op (changed is False, the
    old stamp survives untouched)."""
    body = "- [2026-09-05T09:22:00Z] RTH-TICK-GAP: gap detected 09:15-09:20, 3 missing bars.\n"
    p = _seed(tmp_path, body)
    before = p.read_text(encoding="utf-8")

    new_line = "- [2026-09-05T09:27:00Z] RTH-TICK-GAP: gap detected 09:15-09:20, 3 missing bars."
    changed = skb.upsert("RTH-TICK-GAP:", new_line, status_path=p)

    assert changed is False, "unchanged payload must be a true no-op"
    after = p.read_text(encoding="utf-8")
    assert after == before, "file bytes must be untouched -- the old stamp must survive"
    assert "09:22:00Z" in after
    assert "09:27:00Z" not in after


def test_changed_payload_still_writes_a_fresh_stamp(tmp_path):
    """Discriminator: a genuinely DIFFERENT finding must still upsert normally (proves
    this isn't a blanket no-op that would hide a real new event)."""
    body = "- [2026-09-05T09:22:00Z] RTH-TICK-GAP: gap detected 09:15-09:20, 3 missing bars.\n"
    p = _seed(tmp_path, body)

    new_line = "- [2026-09-05T09:27:00Z] RTH-TICK-GAP: gap detected 09:40-09:45, 5 missing bars."
    changed = skb.upsert("RTH-TICK-GAP:", new_line, status_path=p)

    assert changed is True
    after = p.read_text(encoding="utf-8")
    assert "09:27:00Z" in after
    assert "09:22:00Z" not in after
    assert after.count("RTH-TICK-GAP:") == 1


def test_repeated_unchanged_upserts_never_advance_the_stamp(tmp_path):
    """Simulates 5 consecutive engine_health ticks with the same finding: the stamp must
    stay pinned to the FIRST write across all of them."""
    p = _seed(tmp_path, "")
    first = "- [2026-09-05T09:00:00Z] RTH-TICK-GAP: gap detected 09:00-09:05, 2 missing bars."
    assert skb.upsert("RTH-TICK-GAP:", first, status_path=p) is True

    for minute in (5, 10, 15, 20):
        restamped = f"- [2026-09-05T09:{minute:02d}:00Z] RTH-TICK-GAP: gap detected 09:00-09:05, 2 missing bars."
        changed = skb.upsert("RTH-TICK-GAP:", restamped, status_path=p)
        assert changed is False, f"tick at :{minute:02d} re-stamped an unchanged finding"

    out = p.read_text(encoding="utf-8")
    assert "09:00:00Z" in out
    assert out.count("RTH-TICK-GAP:") == 1

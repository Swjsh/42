"""Guard: the live/backtest parity verdict reaches J's brief (2026-08-12).

WHY. Building parity_check.py and leaving it unscheduled would have been the exact disease it
exists to diagnose -- tonight already produced two instances of an instrument that existed but was
invisible: bg_status.py (built 2026-08-06 to retire "is anything running?", never committed, blind
to Agent-tool work) and the Discord bridge (alive, heartbeat green, 1,837 messages undelivered).
C35: built + tested != shipped until it lands on the surface J actually reads.

Gamma_FirmBrief is a registered task that fires and writes automation/state/firm-brief.md, so
folding the line in there means it renders on every fire with no new scheduled task -- OP-22,
append to the existing surface rather than building a parallel one.

PINNED HERE:
  * The section exists and is wired into the brief body, not just defined.
  * It is computed LIVE, never read from a cached state file. A cached parity verdict would grow
    its own staleness failure mode -- which is the same bug class parity_check exists to catch.
  * It FAILS OPEN. A brief that dies because one section could not compute is worse than a brief
    that says so; the whole daily report must not hinge on this line.
  * When something is UNCLASSIFIED it says so AND names the largest one, so the line is
    actionable rather than merely alarming.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import firm_brief as fb  # noqa: E402

SRC = (SCRIPTS / "firm_brief.py").read_text(encoding="utf-8")


def test_the_section_is_actually_wired_into_the_brief_body():
    """Defining the renderer but never calling it is the classic half-ship."""
    body = SRC.split("def build_brief")[-1] if "def build_brief" in SRC else SRC
    assert "render_parity_lines()" in body, (
        "render_parity_lines is defined but never called -- the section would never render")
    assert '"## Live/backtest parity"' in SRC


def test_it_renders_real_content_against_the_live_ledger():
    lines = fb.render_parity_lines()
    assert lines, "parity section rendered empty"
    joined = " ".join(lines)
    assert any(v in joined for v in ("RED", "AMBER", "GREEN")), (
        f"no verdict in the parity line: {lines}")
    assert "could not compute" not in joined, f"parity section is erroring: {lines}"


def test_unclassified_actions_are_named_not_just_counted():
    """An alarm that does not say what to look at gets ignored."""
    lines = fb.render_parity_lines()
    joined = " ".join(lines)
    if "UNCLASSIFIED" in joined:
        assert "Largest:" in joined, f"unclassified count with no exemplar: {lines}"
        assert "parity-registry.json" in joined, "the line must name where to fix it"


def test_it_is_computed_live_not_read_from_a_cached_state_file():
    """A cached parity verdict acquires a staleness failure mode -- precisely the class of bug
    parity_check exists to catch. It must recompute from the ledger every time."""
    block = SRC.split("def render_parity_lines")[1].split("\ndef ")[0]
    assert "_harvest_live_actions" in block, "no longer recomputes from the live ledger"
    assert "load_json" not in block, (
        "the parity section now reads a cached state file -- it must recompute, or it can go "
        "stale and report a parity verdict that no longer describes the engine")


def test_it_fails_open(monkeypatch):
    """One broken section must never take the whole daily brief down."""
    import parity_check as pcheck

    def _boom(*a, **k):
        raise RuntimeError("ledger exploded")
    monkeypatch.setattr(pcheck, "_harvest_live_actions", _boom)
    lines = fb.render_parity_lines()
    assert lines and "could not compute" in " ".join(lines), (
        f"parity section did not fail open: {lines}")


def test_the_section_reaches_the_written_artifact():
    """End-to-end: the file Gamma_FirmBrief actually produces, not just the renderer."""
    brief = REPO / "automation" / "state" / "firm-brief.md"
    if not brief.exists():
        pytest.skip("firm-brief.md not generated yet in this environment")
    text = brief.read_text(encoding="utf-8", errors="replace")
    assert "## Live/backtest parity" in text, (
        "the parity section is missing from the generated brief -- it renders but does not ship")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))

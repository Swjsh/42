"""Guard: gamma_glance.py -- J's 2-minute REAL-state glance view (OP-33c) must import,
run, and print a verified entries-today line.

This guard exists because the 2026-06-30 disease was visibility-by-exit-code: a wrapper
goes green while the money path is dead. gamma_glance is the human's antidote, so the
guard asserts it actually PRODUCES the load-bearing facts (an entries-today line + the
GREEN/RED tag vocabulary), not merely that it returns 0.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
sys.path.insert(0, str(SCRIPTS))


def test_gamma_glance_imports():
    import gamma_glance  # noqa: F401

    assert hasattr(gamma_glance, "build")
    assert hasattr(gamma_glance, "main")


def test_gamma_glance_builds_and_prints_entries_line():
    import gamma_glance

    text = gamma_glance.build()
    assert isinstance(text, str) and text.strip(), "build() produced empty output"
    lower = text.lower()

    # the load-bearing line J glances at: how many real entries today
    assert "entries-today" in lower, "missing entries-today line"
    # the fill-path truth (the audit's core finding: never filled a real trade).
    # 2026-07-01: the old fills-today block read the dead fleet/decisions/ dir and
    # showed 0 fills while 4 fleet round trips happened; replaced by the FUNNEL
    # block (fill_funnel.py: ticks->sig->ENTER->attempt->accept->fill->exit).
    assert "funnel" in lower, "missing FUNNEL block (fill-path truth)"
    assert "accept->fill->exit" in lower, "missing funnel stage header (fill-path truth)"
    # ASCII-only [GREEN]/[RED] tags (no emoji -- Windows cp1252 safe)
    assert ("[green]" in lower) or ("[red]" in lower), "missing GREEN/RED tag vocabulary"
    # must be pure ASCII so it never cp1252-crashes a PS 5.1 console (the em-dash class)
    text.encode("ascii")


def test_gamma_glance_main_returns_zero(capsys):
    import gamma_glance

    rc = gamma_glance.main()
    assert rc == 0
    captured = capsys.readouterr().out.lower()
    assert "entries-today" in captured, "main() did not print the entries-today line"

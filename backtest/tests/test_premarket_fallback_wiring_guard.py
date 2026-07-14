"""A5 wiring guard -- permanent regression test.

Companion to test_premarket_deliverable_gate_guard.py (which locks in the OP-33
deliverable checks). This file locks in the NEW piece added 2026-07-14
(analysis/deep-research/2026-07-14-premarket-reliability.md): once the LLM step is
confirmed to have failed, run-premarket.ps1 must invoke
premarket_deterministic_fallback.py and, if (and only if) it produced a genuinely
fresh degraded bias, report that OUTCOME distinctly from a true full-day BROKEN
miss -- never silently reclassify a degraded fallback write as a real VERIFIED LLM
pass, and never let a fallback failure escape detection either.

Guard class: HARD -- if this wiring disappears, the fallback script can exist and
be perfectly correct while the wrapper never calls it (or calls it and ignores the
result), and the LLM-failure gap A5 exists to close silently reopens.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PREMARKET_PS1 = REPO / "setup" / "scripts" / "run-premarket.ps1"
SELF_CHECK_PY = REPO / "setup" / "scripts" / "self_check.py"
FALLBACK_PY = REPO / "setup" / "scripts" / "premarket_deterministic_fallback.py"


@pytest.fixture(scope="module")
def ps1_text() -> str:
    assert PREMARKET_PS1.exists(), f"missing {PREMARKET_PS1}"
    return PREMARKET_PS1.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def self_check_text() -> str:
    assert SELF_CHECK_PY.exists(), f"missing {SELF_CHECK_PY}"
    return SELF_CHECK_PY.read_text(encoding="utf-8")


def test_fallback_script_exists():
    assert FALLBACK_PY.exists(), "premarket_deterministic_fallback.py must exist for the wrapper to invoke"


def test_wrapper_invokes_fallback_only_after_deliverable_failure(ps1_text: str):
    """The fallback invocation must live INSIDE the deliverableMsg failure branch,
    not as an unconditional every-run call (it must never override a real LLM pass)."""
    assert "premarket_deterministic_fallback.py" in ps1_text
    # The invocation text must appear strictly AFTER the "if ($null -ne $deliverableMsg)"
    # branch opens, i.e. it is nested inside the failure path.
    gate_idx = ps1_text.index("if ($null -ne $deliverableMsg)")
    fb_idx = ps1_text.index("premarket_deterministic_fallback.py")
    assert fb_idx > gate_idx, "fallback must be invoked INSIDE the LLM-failure branch, not unconditionally"


def test_wrapper_verifies_degraded_marker_before_trusting_fallback(ps1_text: str):
    """Must not just assume the fallback worked -- must re-read the file and check
    the SAME three markers the fallback contractually writes."""
    for marker in ("degraded", "deterministic_fallback", "$todayEt"):
        assert marker in ps1_text


def test_wrapper_distinguishes_degraded_from_broken_in_status_md(ps1_text: str):
    """STATUS.md must carry a DIFFERENT heading for fallback-covered vs still-broken
    (spec point 4: 'distinguish stale from degraded-fresh') -- a diffing human or
    self_check must never see the two conflated under the same '### BROKEN' banner."""
    assert "### BROKEN: premarket" in ps1_text
    assert "### DEGRADED: premarket" in ps1_text
    assert ps1_text.index("### BROKEN: premarket") != ps1_text.index("### DEGRADED: premarket")


def test_original_broken_path_and_loud_failure_preserved(ps1_text: str):
    """A5 must be purely ADDITIVE -- the pre-existing silent-failure detection
    (insight #17b guard) must still be fully intact."""
    assert "PREMARKET SILENT FAILURE" in ps1_text
    assert "$exit = 3" in ps1_text
    assert "STATUS.md" in ps1_text


def test_self_check_distinguishes_degraded_fresh(self_check_text: str):
    assert "deterministic_fallback" in self_check_text
    assert "PREMARKET DEGRADED" in self_check_text
    # Must still check date-freshness FIRST -- degraded classification only applies
    # to an ALREADY-fresh-dated file, never in place of the stale-date check.
    assert "PREMARKET STALE" in self_check_text


def test_self_check_degraded_message_never_classifies_as_broken():
    """Runtime check (not just text-grep): feed the exact PREMARKET DEGRADED message
    shape through self_check's own BROKEN-vs-DEGRADED classifier and assert it lands
    as DEGRADED, never BROKEN -- a degraded-but-fresh bias must never trip a hard
    scheduler failure page."""
    import sys
    sys.path.insert(0, str(REPO / "setup" / "scripts"))
    import self_check as sc  # noqa: PLC0415

    msg = ("PREMARKET DEGRADED: today-bias.json is fresh-dated but LLM-authored "
           "narrative failed this morning -- running on the deterministic fallback's "
           "mechanical bias only (no chart/ribbon/trendline read, zero falsifiable_predictions).")
    assert sc._problem_is_broken(msg) is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

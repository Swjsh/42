"""Premarket deliverable-gate guard -- permanent regression test (insight #17b).

ROOT CAUSE (2026-06-30): run-premarket.ps1's verify-gate checked ONLY that
today-bias.json's `.date == today`. But BOTH refresh_levels_intraday AND a
manual hand-rebuild stamp today's date, so the gate went GREEN even when the
premarket LLM "produced NO bias" (the 06-30 silent failure). The gate must
verify the DELIVERABLE was authored THIS run, not merely that the date is fresh.

This guard asserts run-premarket.ps1 still contains the three deliverable
checks so the date-only regression can never silently return:
  (a) updated_by must NOT contain "interactive"/"rebuilt"/"by hand"/"by_hand".
  (b) falsifiable_predictions must be a non-empty array.
  (c) bias_note length must be > 80.

Guard class: HARD -- if these disappear, a silent LLM failure goes GREEN and the
engine opens the day on a stale/hand-stamped bias.
"""
from __future__ import annotations

from pathlib import Path

import pytest

PREMARKET_PS1 = (
    Path(__file__).resolve().parents[2] / "setup" / "scripts" / "run-premarket.ps1"
)


@pytest.fixture(scope="module")
def script_text() -> str:
    assert PREMARKET_PS1.exists(), f"missing {PREMARKET_PS1}"
    return PREMARKET_PS1.read_text(encoding="utf-8")


def test_updated_by_not_interactive_check_present(script_text: str) -> None:
    """The gate must reject a non-LLM hand-rebuild author."""
    lc = script_text.lower()
    # The banned-author list must enumerate all four hand-rebuild markers.
    for marker in ("interactive", "rebuilt", "by hand", "by_hand"):
        assert marker in lc, f"updated_by banned-author marker '{marker}' missing from gate"
    # And it must actually inspect updated_by to do so.
    assert "updated_by" in lc, "gate does not reference today-bias.updated_by"


def test_predictions_non_empty_check_present(script_text: str) -> None:
    """The gate must require falsifiable_predictions to be a non-empty array."""
    assert (
        "falsifiable_predictions" in script_text
    ), "gate does not reference falsifiable_predictions"
    # The emptiness comparison (< 1) must be present.
    assert "-lt 1" in script_text, "gate does not assert predictions count >= 1"


def test_bias_note_length_check_present(script_text: str) -> None:
    """The gate must reject a stub bias_note (length <= 80)."""
    assert "bias_note" in script_text, "gate does not reference bias_note"
    assert "80" in script_text, "gate does not assert bias_note length > 80"


def test_loud_failure_path_preserved(script_text: str) -> None:
    """A miss must still force the loud non-zero exit + STATUS.md BROKEN path."""
    assert "PREMARKET SILENT FAILURE" in script_text
    assert "$exit = 3" in script_text
    assert "STATUS.md" in script_text or "STATUS" in script_text

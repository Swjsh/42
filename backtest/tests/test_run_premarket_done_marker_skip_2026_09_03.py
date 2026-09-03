"""Guard: run-premarket.ps1 has a done-marker skip before the LLM step.

ROOT CAUSE THIS PINS (GAMMA-PREMARKET-SELF-HEAL-WINDOW, MED, 2026-09-03).
Gamma_Premarket was the last remaining trading-critical single-daily-fire producer with
NO Task Scheduler self-heal Repetition window (`setup/install-premarket.ps1`, this same
change, adds PT15M/PT30M -- the same remedy already shipped for Gamma_MacroCalendar /
Gamma_EarningsCalendar / Gamma_FuturesEod2 / Gamma_PremarketReadiness /
Gamma_Tp1R50ForwardShadow). But `setup/scripts/run-premarket.ps1` was NOT idempotent
across separate invocations before this fix:
  - `Invoke-PremarketAttempt` spends a fresh $3 LLM budget call every time it runs.
  - `automation/prompts/premarket.md` Step 4 fully REWRITES `today-bias.json` (not a
    merge).
  - Step 6 CREATEs `journal/{today}.md` -- a full overwrite, not an append.
An unconditional retry fire at 08:45 (the new self-heal window) after a clean 08:30
success would waste LLM budget and could stomp the good bias/journal with a second,
possibly different, LLM pass.

THE FIX: a done-marker skip at the top of the script (before the stale-process reap /
daily-loss-guard rearm / LLM step) -- if `today-bias.json` is already dated today AND its
file mtime (converted to ET) is >= 08:00 ET, premarket already ran this session; log and
exit 0 instead of re-running. This only short-circuits a REDUNDANT repeat fire -- a fire
following a genuine miss (no fresh today-bias.json yet, or one from a stale date/time)
falls through and runs normally, which is the self-heal window's actual job. The check is
wrapped fail-open (any error falls through to a normal run) so a broken check can never be
the reason a real miss stays unrecovered.

Guard class: HARD -- if this skip disappears (or moves after the LLM step, or loses its
fail-open wrapper, or loses the exit 0), the self-heal Repetition window added in
`setup/install-premarket.ps1` turns from a safety net into a bug: every missed-fire retry
audit would incorrectly conclude the window is safe when it is actually re-running an
already-successful morning.

Pure static text-parsing test, matching the house convention already used for
`run-premarket.ps1`'s deliverable gate (see `test_premarket_deliverable_gate_guard.py`) --
no PowerShell execution required, runs anywhere, fast, deterministic.
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


def test_done_marker_skip_present(script_text: str) -> None:
    """The skip-log marker and the exit 0 short-circuit must both be present."""
    assert "SKIP already-done" in script_text, (
        "done-marker skip log message missing -- a redundant self-heal re-fire would no "
        "longer be distinguishable from a genuine retry in the task log"
    )
    assert "exit 0" in script_text, "done-marker skip path must exit 0 (not just log)"


def test_done_marker_checks_date_and_time_threshold(script_text: str) -> None:
    """The gate must compare today-bias.json's date to today ET AND its write time to an
    08:00 ET threshold -- date-only would let a stale hand-edited file from yesterday's
    late-run block a legitimate retry; time-only would skip a run that predates today."""
    assert "today-bias.json" in script_text
    assert "$existingBias.date -eq $todayEtCheck" in script_text, (
        "done-marker does not compare today-bias.json's own .date field to today ET"
    )
    assert "$eightAmEt" in script_text and "08" in script_text, (
        "done-marker does not gate on an 08:00 ET write-time threshold"
    )
    assert "LastWriteTimeUtc" in script_text, (
        "done-marker does not inspect the file's actual write time (mtime), so it cannot "
        "tell 'ran this morning' from 'ran yesterday, date field somehow still matched'"
    )


def test_done_marker_is_fail_open(script_text: str) -> None:
    """A broken check must fall through to a normal run, never block a genuine miss from
    self-healing -- the whole point of the retry window."""
    marker_idx = script_text.index("SKIP already-done")
    # Walk backward to the nearest 'try {' before the marker and confirm a 'catch' with a
    # fail-open comment follows the guard block (best-effort static check, not a full
    # PowerShell parse).
    preceding = script_text[:marker_idx]
    assert "try {" in preceding, "done-marker skip is not wrapped in a try block"
    following = script_text[marker_idx:]
    catch_idx = following.index("} catch {")
    catch_block = following[catch_idx: catch_idx + 300]
    assert "fail-open" in catch_block.lower(), (
        "done-marker's catch block does not document/behave as fail-open -- continuing "
        "with a normal run"
    )


def test_done_marker_runs_before_llm_step(script_text: str) -> None:
    """The skip must short-circuit BEFORE Invoke-PremarketAttempt spends any LLM budget --
    placing it after would defeat the entire point (budget already spent by the time the
    check could matter)."""
    marker_idx = script_text.index("SKIP already-done")
    llm_idx = script_text.index("Invoke-PremarketAttempt -AttemptNum 1")
    assert marker_idx < llm_idx, (
        "done-marker skip appears AFTER the LLM step is invoked -- it must run first to "
        "actually save the redundant budget call"
    )


def test_done_marker_runs_before_journal_seed_and_bias_rewrite(script_text: str) -> None:
    """Confirms the ordering claim in the module docstring: the skip must precede
    everything premarket.md's non-idempotent steps (today-bias.json rewrite, journal
    seed) are reached through -- i.e. before the reap/rearm preamble too, so a redundant
    fire does the least possible work before bailing."""
    marker_idx = script_text.index("SKIP already-done")
    reap_idx = script_text.index("Stop-StaleClaudeProcesses -StaleAfterMinutes 5")
    assert marker_idx < reap_idx, (
        "done-marker skip should run at the very top of the script (before the stale-"
        "process reap / daily-loss-guard rearm preamble), not interleaved after other "
        "work has already started"
    )

"""Regression guard: Gamma_MacroCalendar + Gamma_EarningsCalendar's daily-once triggers
must carry a bounded repetition window, so a single missed Windows Task Scheduler fire
self-heals without depending on external detection (self_check.py / conductor).

THE BUG THIS GUARDS (found live, 2026-08-25 conductor fire). Gamma_MacroCalendar's single
05:45 MT daily trigger silently did not fire: `Get-ScheduledTaskInfo` showed
`LastRunTime` stuck on the PRIOR day, `NumberOfMissedRuns=1`, `NextRunTime` already
advanced past today entirely -- despite the box being continuously awake (run-cmd-hidden
log shows other same-cadence tasks, e.g. window_leak_detector_keepalive, firing every
~2-5 min right through the trigger window with no gap), on AC power (no battery present,
so `DisallowStartIfOnBatteries` cannot be the cause), and `StartWhenAvailable=True` set on
the task. Microsoft-Windows-TaskScheduler/Operational is disabled on this box (confirmed:
`wevtutil gl` -> `enabled: false`; enabling it from a non-elevated shell fails with
"Access is denied") so there is no forensic trail for WHY Windows dropped one weekly-daily
trigger occurrence. This is a DIFFERENT mechanism from L229 (wscript fire-and-forget
masking a real non-zero exit code while LastTaskResult stays 0) -- here Windows itself
correctly recorded the miss (NumberOfMissedRuns=1), it just never caught up. This is also
a RE-VIOLATION of the SAME producer's 2026-07-15 miss
(test_self_check_macro_calendar_freshness.py's docstring: an overnight Windows-Update
reboot cut the interactive logon session through the same 05:45-06:00 MT window) --
two independent root causes, same single-fire vulnerability, same consumer deadline
(Gamma_Premarket 08:30 ET). A twice-hit class is a missing guardrail (OP-25): detection
via self_check.py already existed both times; what was missing is SELF-HEALING.

Fix: `-Weekly` trigger keeps its single 05:45/05:50 primary fire, but now also carries a
15-min-interval / 30-min-duration repetition window (mirrors Gamma_TvWatchdog's re-check
cadence) -- so a single missed occurrence gets up to 2 more chances within 30 min, all
comfortably before Gamma_Premarket's 08:30 ET read. Both producers are cheap (~1-2s) and
idempotent (a fresh re-run just no-ops), so the extra fires change nothing on a normal day.

Static source-parse only (same precedent as test_install_script_relay_wiring_drift.py /
test_earnings_calendar_install_wiring_2026_08_24.py) -- no live Task Scheduler query, so
this test runs anywhere, not just on the production box.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]

_TARGETS = [
    ("macro_calendar", _REPO / "setup" / "scripts" / "install-macro-calendar.ps1", "05:45"),
    ("earnings_calendar", _REPO / "setup" / "scripts" / "install-earnings-calendar.ps1", "05:50"),
]


def _source(path: Path) -> str:
    assert path.exists(), f"missing: {path}"
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("name,path,at_time", _TARGETS, ids=[t[0] for t in _TARGETS])
def test_install_script_exists(name, path, at_time):
    assert path.exists()


@pytest.mark.parametrize("name,path,at_time", _TARGETS, ids=[t[0] for t in _TARGETS])
def test_weekly_trigger_carries_a_repetition_window(name, path, at_time):
    """The primary -Weekly trigger must have its .Repetition populated via the documented
    'steal from a throwaway -Once trigger' PowerShell workaround (direct property
    assignment on a -Weekly trigger's null Repetition CIM instance throws
    PropertyNotFound -- this is not a stylistic choice, it's the only way that works)."""
    src = _source(path)

    assert re.search(r"New-ScheduledTaskTrigger\s+-Weekly\b", src), (
        f"{name}: expected a -Weekly primary trigger, found none"
    )

    repetition_assign = re.search(
        r"\$trigger\.Repetition\s*=\s*\(New-ScheduledTaskTrigger\s+-Once\b[^\n]*\)\.Repetition",
        src,
    )
    assert repetition_assign, (
        f"{name}: no `$trigger.Repetition = (New-ScheduledTaskTrigger -Once ...).Repetition` "
        "assignment found -- this is the exact regression this guard exists to catch "
        "(a single-fire daily trigger with no self-heal window; see this test's module "
        "docstring for the live 2026-08-25 incident)"
    )

    repetition_line = repetition_assign.group(0)
    assert "-RepetitionInterval" in repetition_line and "-RepetitionDuration" in repetition_line, (
        f"{name}: the -Once donor trigger must specify both -RepetitionInterval and "
        "-RepetitionDuration"
    )


@pytest.mark.parametrize("name,path,at_time", _TARGETS, ids=[t[0] for t in _TARGETS])
def test_repetition_window_is_bounded_and_shorter_than_premarket_gap(name, path, at_time):
    """The repetition duration must be well inside the gap to Gamma_Premarket (08:30 ET) --
    a self-heal window that runs right up to (or past) the consumer's own read time defeats
    the purpose. Both producers fire at 05:45/05:50 MT (=07:45/07:50 ET); Premarket reads
    at 08:30 ET, a ~40-45 min gap. Duration must leave at least 10 min of margin."""
    src = _source(path)

    duration_match = re.search(r"-RepetitionDuration\s*\(New-TimeSpan\s+-Minutes\s+(\d+)\)", src)
    assert duration_match, f"{name}: could not find -RepetitionDuration (New-TimeSpan -Minutes N)"
    duration_min = int(duration_match.group(1))

    at_hh, at_mm = (int(x) for x in at_time.split(":"))
    fire_minutes_after_0530_mt = (at_hh - 5) * 60 + at_mm  # minutes past 05:00 MT
    premarket_minutes_after_0530_mt = (8 - 5) * 60 + 30 - fire_minutes_after_0530_mt + 15
    # premarket is 08:30 ET = 06:30 MT; gap from this task's primary fire to premarket read
    gap_min = (6 * 60 + 30) - (at_hh * 60 + at_mm)

    assert 0 < duration_min <= gap_min - 10, (
        f"{name}: repetition duration {duration_min}m leaves less than 10m margin before "
        f"Gamma_Premarket's 08:30 ET read (gap from {at_time} MT primary fire to 06:30 MT "
        f"Premarket-equivalent is {gap_min}m) -- tighten the duration"
    )


def test_synthetic_regression_is_caught_by_the_pattern():
    """Vacuity check: a single-fire trigger with no repetition assignment at all must fail
    the guard above, proving it is not a rubber stamp."""
    broken_src = (
        '$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,'
        'Wednesday,Thursday,Friday -At "05:45"\n'
        '$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit '
        '(New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew -StartWhenAvailable\n'
    )
    repetition_assign = re.search(
        r"\$trigger\.Repetition\s*=\s*\(New-ScheduledTaskTrigger\s+-Once\b[^\n]*\)\.Repetition",
        broken_src,
    )
    assert repetition_assign is None, (
        "vacuity check itself is broken -- the known-broken (pre-fix) fixture should NOT "
        "match the repetition-assignment pattern"
    )

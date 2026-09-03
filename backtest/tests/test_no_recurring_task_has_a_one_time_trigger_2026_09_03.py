"""Guard: no Gamma_* task documented as recurring carries a genuinely one-shot trigger.

THE BUG CLASS (queue.md SINGLE-FIRE-TRIGGER-BLANKET-AUDIT, filed 2026-08-26)
-----------------------------------------------------------------------------
Three producers hit the identical shape inside 2 days: ``Gamma_MacroCalendar``,
``Gamma_EarningsCalendar`` (2026-08-25), then ``Gamma_FuturesEod2`` (2026-08-26). Each
was CORRECTLY registered with a recurring ``-Weekly`` (Mon-Fri) trigger, yet Windows
Task Scheduler silently failed to fire the single daily instance on one occasion
(``LastRunTime`` stuck a day behind, ``NumberOfMissedRuns=1``, ``NextRunTime`` already
advanced past the missed day) -- ``StartWhenAvailable=True`` did NOT catch it up, and
Microsoft-Windows-TaskScheduler/Operational is disabled on this box (access-denied to
enable non-elevated) so there is no forensic trail for WHY. The fix shipped on all 3:
a bounded self-heal repetition window (every 15 min for 30 min after the primary
fire) so a single missed trigger self-heals within 30 min instead of staying dark
until the next scheduled day.

This is the SAME failure family (project_scheduled_task_onetime_trigger_dark) as the
even more literal historical bug this guard's name refers to: a task registered with a
bare ``-Once`` trigger and NO repetition at all fires exactly once, ever, then goes
permanently dark -- every other field (``NextRunTime``, ``State``) can still look
healthy. ``evaluate_trigger_health``'s existing ``NON_REPEATING_TRIGGER`` flag
(``setup/scripts/audit_scheduled_tasks.py``) only catches this for cadences documented
in the "every N min/h" shape (``_documented_repeat_minutes``); a task documented with a
single-fire-per-day cadence like "08:20 ET weekdays" is invisible to that check because
``_documented_repeat_minutes`` returns ``None`` for it and the evaluator skips ahead.
THIS guard closes that specific gap: for every task documented in SCHEDULED-TASKS.md's
``## Active`` table (any cadence shape), assert no ENABLED live trigger is a bare
``TimeTrigger`` with no ``repetition_interval`` -- the literal "fires once, dies
forever" shape, independent of whether the doc's cadence string matches "every N min".

2026-09-03 BLANKET AUDIT -- LIVE FINDINGS PINNED
-------------------------------------------------
Live-enumerated via ``Get-ScheduledTask`` + ``Get-ScheduledTaskInfo`` against all 177
``Gamma_*`` trigger rows (some tasks carry >1 trigger). 21 triggers were CimClass
``MSFT_TaskTimeTrigger`` ("Once" idiom) -- the intentional high-frequency-keepalive
pattern (``-Once -At <boundary> -RepetitionInterval <N min> -RepetitionDuration
P3650D``, i.e. repeats every N minutes for ~10 years = effectively forever), NOT the
one-shot-dies bug, because every one of them carries a non-empty
``repetition_interval``:

    Gamma_ConductorWake, Gamma_CryptoTwin, Gamma_DashboardKeepalive,
    Gamma_EngineStressSwarm, Gamma_FuturesHealth, Gamma_FuturesHeartbeat (Disabled),
    Gamma_Heartbeat_Aggressive (Disabled), Gamma_Home, Gamma_LevelRefresh,
    Gamma_LiveShadowValidator, Gamma_ManagerOverseer (Disabled), Gamma_Prospector,
    Gamma_QuietMode, Gamma_QuoteRecorderKeepalive, Gamma_SelfCheck,
    Gamma_TaskStateGuard, Gamma_TwinSentinel, Gamma_UnattendedHealth,
    Gamma_WindowLeakDetectorKeepalive, Gamma_WindowLeakHookKeepalive,
    Gamma_XspSpreadRecorder

Zero tasks tonight carried a genuinely bare one-shot trigger (TimeTrigger with an
EMPTY ``repetition_interval``) on an Active-documented task. This guard pins that
invariant so a future install script that drops the ``.Repetition`` assignment (the
exact PowerShell footgun documented in every ``install-*-calendar.ps1`` header --
``-Weekly``/``-Daily`` triggers come back with a null ``.Repetition`` CIM instance that
must be stolen from a throwaway ``-Once`` trigger, or a straight ``-Once`` registration
with no repetition params at all) gets caught at test time instead of by a stale-file
incident days later.

Also does the registry-doc cross-check the queue item asked for: every task documented
Active must actually exist in the live registry (a documented-but-unregistered task is
a different, already-covered drift class -- ``ORPHAN_TASK``/``STALE_REGISTRY_ENTRY`` in
``audit_scheduled_tasks.py`` -- but this guard still asserts non-trivial overlap so an
empty/broken live scan cannot silently pass as "no bad triggers found").

FAIL-OPEN / FAIL-CLOSED: MONITORING-only, $0 (pure PowerShell enumeration + file
parsing, no LLM, no network). Skips (never fails) off-Windows or when the live
PowerShell helper returns nothing, mirroring
``test_scheduled_task_triggers_live.py::test_live_registry_has_no_scheduled_task_drift``
exactly -- a broken checker must never masquerade as a clean scan, so an EMPTY live
result is a skip with a stated reason, not a silent pass.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "setup" / "scripts"))

import audit_scheduled_tasks as A  # noqa: E402


def _one_shot_no_repetition_flags(registry_text: str, tasks: list[dict]) -> list[dict]:
    """PURE. For every task documented Active, flag any ENABLED live trigger that is a
    bare TimeTrigger with no repetition_interval -- the genuine one-shot-dies-forever
    shape. Kept separate from ``A.evaluate_trigger_health`` (which only checks the
    "every N min" cadence shape) so this specific gap has its own RED-proofed unit."""
    active_rows = A._parse_active_rows(registry_text)  # noqa: SLF001
    exempt = A._intentionally_disabled(registry_text)  # noqa: SLF001
    by_name = {t["name"]: t for t in tasks}
    flags: list[dict] = []

    for name in sorted(active_rows):
        if name in exempt:
            continue
        task = by_name.get(name)
        if task is None:
            continue  # a different drift class already covers unregistered-but-documented
        if task.get("state") == "Disabled":
            continue  # a disabled task's trigger shape is moot until re-enabled

        for trig in task.get("triggers") or []:
            if not trig.get("enabled", True):
                continue
            ttype = (trig.get("type") or "").strip()
            rep = trig.get("repetition_interval")
            if ttype == "TimeTrigger" and not rep:
                flags.append({
                    "flag": "ONE_SHOT_TRIGGER_NO_REPETITION",
                    "task": name,
                    "note": (f"documented cadence {active_rows[name]['cadence']!r} but the "
                             f"live trigger is a bare TimeTrigger with no repetition_interval "
                             f"-- fires exactly once (StartBoundary {trig.get('start_boundary')!r}) "
                             f"and then never again. Re-register with a -Daily/-Weekly trigger "
                             f"(or a -Once trigger with -RepetitionInterval/-RepetitionDuration "
                             f"stolen onto it, the documented install-*-calendar.ps1 idiom)."),
                })
    return flags


@pytest.mark.slow
def test_live_registry_has_no_one_shot_only_trigger():
    """The real instrument: run the check against the LIVE Windows task registry."""
    if sys.platform != "win32":
        pytest.skip("live Task Scheduler check is Windows-only")

    cwd = os.getcwd()
    os.chdir(_REPO)
    try:
        registry_text = A.REGISTRY_PATH.read_text(encoding="utf-8")
        tasks = A._registered_tasks()  # noqa: SLF001
    finally:
        os.chdir(cwd)

    if not tasks:
        pytest.skip("0 tasks returned by the live PowerShell helper -- treat as "
                     "unavailable, never as a clean scan (fail-open per house rule)")

    active_rows = A._parse_active_rows(registry_text)  # noqa: SLF001
    live_names = {t["name"] for t in tasks}
    documented_and_live = set(active_rows) & live_names
    assert documented_and_live, (
        "0 overlap between SCHEDULED-TASKS.md's Active table and the live registry -- "
        "registry-doc cross-check failure, the scan or the doc parse is broken, not a "
        "clean result"
    )

    flags = _one_shot_no_repetition_flags(registry_text, tasks)
    if flags:
        detail = "\n".join(f"  [{f['flag']}] {f['task']}: {f['note']}" for f in flags)
        pytest.fail(
            f"{len(flags)} one-shot-no-repetition trigger(s) on a documented-recurring "
            f"task:\n{detail}\n\nThis is the exact class that silently killed "
            f"Gamma_MacroCalendar/Gamma_EarningsCalendar/Gamma_FuturesEod2's single "
            f"daily fire in 2026-08. Re-register with a recurring trigger."
        )


# ── pure fixture tests (RED-proof without touching the live box) ─────────────
def _registry(*rows: str) -> str:
    head = "# Registry\n\n## Active tasks (current production)\n\n| Task | Cadence | Cost/fire | Why |\n|---|---|---|---|\n"
    return head + "\n".join(rows) + "\n"


def _row(name: str, cadence: str, why: str = "does a thing", cost: str = "$0") -> str:
    return f"| `{name}` | {cadence} | {cost} | {why} |"


def _task(name: str, state: str = "Ready", triggers: list[dict] | None = None) -> dict:
    return {"name": name, "state": state, "triggers": triggers or []}


def _trig(ttype: str, rep_interval: str | None = None, start: str = "2026-01-01T05:00:00-06:00",
          enabled: bool = True) -> dict:
    return {
        "type": ttype,
        "start_boundary": start,
        "repetition_interval": rep_interval,
        "enabled": enabled,
    }


def test_true_one_shot_daily_cadence_flags():
    """The exact original bug: a daily-cadence task registered with a bare -Once
    trigger and NO repetition -- fires once, dies forever."""
    reg = _registry(_row("Gamma_Foo", "08:20 ET weekdays"))
    tasks = [_task("Gamma_Foo", triggers=[_trig("TimeTrigger", rep_interval=None)])]
    flags = _one_shot_no_repetition_flags(reg, tasks)
    assert len(flags) == 1
    assert flags[0]["flag"] == "ONE_SHOT_TRIGGER_NO_REPETITION"
    assert flags[0]["task"] == "Gamma_Foo"


def test_once_trigger_with_infinite_repetition_does_not_flag():
    """The intentional keepalive idiom (-Once + -RepetitionInterval + P3650D duration)
    must NOT be flagged -- it repeats forever, it never dies."""
    reg = _registry(_row("Gamma_Bar", "every 5 min, 24/7"))
    tasks = [_task("Gamma_Bar", triggers=[_trig("TimeTrigger", rep_interval="PT5M")])]
    assert _one_shot_no_repetition_flags(reg, tasks) == []


def test_weekly_trigger_never_flags_this_check():
    """A CalendarTrigger (Daily/Weekly) is inherently recurring at the OS level --
    this specific check only targets bare TimeTrigger, never Calendar triggers (those
    are the class the self-heal-repetition fix targets, a separate concern)."""
    reg = _registry(_row("Gamma_Baz", "09:00 ET weekdays"))
    tasks = [_task("Gamma_Baz", triggers=[_trig("WeeklyTrigger", rep_interval=None)])]
    assert _one_shot_no_repetition_flags(reg, tasks) == []


def test_disabled_task_never_flags():
    """A Disabled task's trigger shape is moot -- it isn't firing at all right now,
    and a different check (DISABLED_BUT_DOCUMENTED_ACTIVE) already owns that gap."""
    reg = _registry(_row("Gamma_Qux", "08:20 ET weekdays"))
    tasks = [_task("Gamma_Qux", state="Disabled",
                    triggers=[_trig("TimeTrigger", rep_interval=None)])]
    assert _one_shot_no_repetition_flags(reg, tasks) == []


def test_intentionally_disabled_annotation_is_exempt():
    reg = _registry(_row(
        "Gamma_Quux", "08:20 ET weekdays",
        why="retired legacy path -- DISABLED intentionally, do not re-enable",
    ))
    tasks = [_task("Gamma_Quux", triggers=[_trig("TimeTrigger", rep_interval=None)])]
    assert _one_shot_no_repetition_flags(reg, tasks) == []


def test_undocumented_task_is_not_this_checks_problem():
    """A task with a bad trigger but NOT in the Active table is a different drift
    class (ORPHAN_TASK) -- this check only scores documented-Active names."""
    reg = _registry(_row("Gamma_Known", "08:20 ET weekdays"))
    tasks = [
        _task("Gamma_Known", triggers=[_trig("WeeklyTrigger")]),
        _task("Gamma_Unlisted", triggers=[_trig("TimeTrigger", rep_interval=None)]),
    ]
    assert _one_shot_no_repetition_flags(reg, tasks) == []


def test_multiple_triggers_only_flags_when_all_offending_present():
    """A task with a good recurring trigger PLUS a stray dead one-shot trigger still
    gets flagged -- every enabled trigger is checked independently."""
    reg = _registry(_row("Gamma_Multi", "08:20 ET weekdays"))
    tasks = [_task("Gamma_Multi", triggers=[
        _trig("WeeklyTrigger", rep_interval=None),
        _trig("TimeTrigger", rep_interval=None),
    ])]
    flags = _one_shot_no_repetition_flags(reg, tasks)
    assert len(flags) == 1
    assert flags[0]["task"] == "Gamma_Multi"


def test_disabled_enabled_flag_on_trigger_itself_is_respected():
    """A disabled INDIVIDUAL trigger (not the task) must not be scored."""
    reg = _registry(_row("Gamma_Split", "08:20 ET weekdays"))
    tasks = [_task("Gamma_Split", triggers=[
        _trig("TimeTrigger", rep_interval=None, enabled=False),
    ])]
    assert _one_shot_no_repetition_flags(reg, tasks) == []

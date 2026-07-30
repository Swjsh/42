"""Guard: a Gamma_* task can never again go SILENTLY dark.

THE INCIDENT THIS GUARDS (2026-07-30, "levels blindness")
---------------------------------------------------------
The engine ran 772 ticks (386/account) with ``levels_active == []`` on every single
row. Root cause chain:

  * ``Gamma_LevelRefresh`` -- the 5-min intraday key-level refresher -- was
    ``State=Disabled``. It last ran 2026-07-29 22:43 ET and never fired again.
  * ``automation/state/key-levels.json`` therefore froze at 2026-07-29; every level
    in it carried ``expires_at`` 2026-07-29.
  * ``heartbeat_core._read_levels`` correctly dropped the expired levels -> ``([], [])``.
    The READ was right. The DATA was stale.
  * With no levels, ``detect_level_rejection`` cannot fire, so the engine silently fell
    through to trendline_rejection-only entries -- the cohort measured at -$1,830 / WR
    .19 over 124 trades. At 11:31-11:46 ET it produced 11 ENTER_BEAR verdicts at SPY
    734.885, the LOW of the day; SPY then rallied to 741.6. Only RISK_DENY_RISK_CAP /
    RISK_DENY_PDT stopped the fills -- luck, not design.
  * ``Gamma_PremarketReadiness`` -- the gate BUILT to catch a stale/empty level set --
    was ALSO Disabled and did not run.

48 further tasks documented ``## Active`` were in the same state (49 total, of which 41
carried no intentional-disable annotation). ``audit_scheduled_tasks.py`` ran and reported
2 unrelated ``SILENT_TASK`` flags -- because every per-task check sat below this line in
``audit()``::

    if state == "Disabled":
        continue

Disabling a task did not make it FAIL a check; it removed the task from checking. Silence
read as health (C7). The triggers themselves were never malformed -- which is exactly why
a trigger-only investigation would have found nothing.

WHAT THIS FILE ASSERTS
----------------------
``audit_scheduled_tasks.evaluate_trigger_health()`` is a PURE function (registry text +
task dicts in, flags out). The fixture tests below RED-proof each detector against
hand-built task registries -- including the historical one-shot-trigger-goes-dark shape
(``project_scheduled_task_onetime_trigger_dark``) -- without touching the live box. The
final test runs the same evaluator against the REAL Windows task registry and requires
zero drift.

FAIL-OPEN / FAIL-CLOSED: this is MONITORING, so it fails open with respect to trading --
a broken checker here cannot block an entry. It fails LOUD with respect to CI: drift is a
test failure, never a warning. The live test is marked ``slow`` (it shells out to
PowerShell, ~3-6s) so the per-edit hook and the <2s curated commit gate stay fast; it runs
under ``Gamma_GuardsNightly`` (``-m slow``) and on demand.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "setup" / "scripts"))

import audit_scheduled_tasks as A  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────────
def _registry(*rows: str) -> str:
    """Build a minimal SCHEDULED-TASKS.md with an '## Active' table."""
    head = "# Registry\n\n## Active tasks (current production)\n\n| Task | Cadence | Cost/fire | Why |\n|---|---|---|---|\n"
    return head + "\n".join(rows) + "\n"


def _row(name: str, cadence: str, why: str = "does a thing", cost: str = "$0") -> str:
    return f"| `{name}` | {cadence} | {cost} | {why} |"


def _task(name: str, state: str = "Ready", triggers: list[dict] | None = None) -> dict:
    return {
        "name": name,
        "state": state,
        "execute": "wscript.exe",
        "arguments": "//nologo run_exe_hidden.vbs pythonw.exe x.py",
        "last_run": "2026-07-30T08:00:00.0000000-06:00",
        "last_result": 0,
        "next_run": "2026-07-30T08:05:00.0000000-06:00",
        "triggers": triggers if triggers is not None else [],
    }


def _trig(interval: str | None = None, duration: str | None = None,
          ttype: str = "TimeTrigger", enabled: bool = True) -> dict:
    return {
        "type": ttype,
        "start_boundary": "2026-06-29T08:23:35-06:00",
        "repetition_interval": interval,
        "repetition_duration": duration,
        "days_of_week": None,
        "enabled": enabled,
    }


def _flags_of(kind: str, flags: list[dict]) -> list[str]:
    return [f["task"] for f in flags if f["flag"] == kind]


# ── duration / cadence parsing ───────────────────────────────────────────────
@pytest.mark.parametrize("value,expected", [
    ("PT5M", 5.0),
    ("PT1M", 1.0),
    ("PT2H", 120.0),
    ("PT6H25M", 385.0),
    ("P3650D", 3650 * 1440.0),
    ("PT23H59M", 1439.0),
    ("", None),
    (None, None),
    ("garbage", None),
])
def test_iso_duration_minutes(value, expected):
    assert A._iso_duration_minutes(value) == expected


@pytest.mark.parametrize("cadence,expected", [
    ("every 5 min, 24/7", 5),
    ("every 10 min, 09:32-16:00 ET wd", 10),
    ("every 2 min, 09:30-16:00 ET wd", 2),
    ("every 2h, every day", 120),
    ("relaunch-check every 30 min, 09:25-16:00 ET weekdays", 30),
    # NOT repeating cadences -- must return None so they are never told to repeat
    ("08:35/09:30/12:00/15:50 ET weekdays", None),
    ("09:00 ET weekdays (07:00 MT)", None),
    ("daily 21:30 ET (19:30 MT)", None),
    ("weekly, Sunday 03:00 ET (01:00 MT)", None),
])
def test_documented_repeat_minutes(cadence, expected):
    assert A._documented_repeat_minutes(cadence) == expected


# ── DISABLED_BUT_DOCUMENTED_ACTIVE (the 2026-07-30 flag) ─────────────────────
def test_flags_documented_active_task_that_is_disabled():
    """THE incident shape: registry says Active, Task Scheduler says Disabled."""
    reg = _registry(_row("Gamma_LevelRefresh", "every 5 min, 24/7"))
    tasks = [_task("Gamma_LevelRefresh", state="Disabled",
                   triggers=[_trig("PT5M", "P3650D")])]
    flags = A.evaluate_trigger_health(reg, tasks)
    assert _flags_of("DISABLED_BUT_DOCUMENTED_ACTIVE", flags) == ["Gamma_LevelRefresh"], (
        "a documented-Active task sitting Disabled must be flagged -- this is exactly "
        "what went unreported on 2026-07-30 and left the engine blind for a full session"
    )


def test_enabled_task_is_not_flagged_as_disabled():
    reg = _registry(_row("Gamma_LevelRefresh", "every 5 min, 24/7"))
    tasks = [_task("Gamma_LevelRefresh", state="Ready", triggers=[_trig("PT5M", "P3650D")])]
    assert A.evaluate_trigger_health(reg, tasks) == []


def test_does_not_flag_annotated_intentional_disable():
    """A row that documents its own pause is an ACKNOWLEDGED off-switch, not drift.

    Without this exemption the flag fires 8 permanent false positives on this repo's
    real registry (retired LLM heartbeats, the J-paused conductor family) -- and a
    monitor that is always red is a monitor nobody reads.
    """
    reg = _registry(
        _row("Gamma_Heartbeat", "every 3 min, 09:30-15:55 ET",
             why="~~THE engine.~~ **RETIRED 2026-06-25 -> DISABLED.** superseded by core"),
        _row("Gamma_Drive", "ONE daily fire 20:00 ET",
             why="nightly driver. **⚠ DISABLED as of 2026-07-08 (T10 drift-fix).**"),
        _row("Gamma_FuturesHeartbeat", "every 3 min, 09:30-15:55 ET weekdays",
             why="**DISABLED** -- shares Max plan rate-limit pool"),
    )
    tasks = [
        _task("Gamma_Heartbeat", state="Disabled", triggers=[_trig("PT3M")]),
        _task("Gamma_Drive", state="Disabled"),
        _task("Gamma_FuturesHeartbeat", state="Disabled", triggers=[_trig("PT3M")]),
    ]
    assert A.evaluate_trigger_health(reg, tasks) == []


# ── NON_REPEATING_TRIGGER (the one-shot-goes-dark shape) ─────────────────────
def test_flags_one_shot_trigger_on_a_repeating_cadence():
    """project_scheduled_task_onetime_trigger_dark: fires once, then never again.

    Every other field still looks healthy -- state Ready, last_run recent, next_run in
    the future -- which is why only the TRIGGER SHAPE can catch it.
    """
    reg = _registry(_row("Gamma_LevelRefresh", "every 5 min, 24/7"))
    tasks = [_task("Gamma_LevelRefresh", state="Ready",
                   triggers=[_trig(interval=None)])]  # one-shot: no repetition
    flags = A.evaluate_trigger_health(reg, tasks)
    assert _flags_of("NON_REPEATING_TRIGGER", flags) == ["Gamma_LevelRefresh"]


def test_flags_task_with_no_triggers_at_all_on_repeating_cadence():
    reg = _registry(_row("Gamma_TradeToday", "every 2 min, 09:30-16:00 ET wd"))
    tasks = [_task("Gamma_TradeToday", state="Ready", triggers=[])]
    assert _flags_of("NON_REPEATING_TRIGGER", A.evaluate_trigger_health(reg, tasks)) == [
        "Gamma_TradeToday"]


def test_disabled_repetition_does_not_count_as_repeating():
    reg = _registry(_row("Gamma_LevelRefresh", "every 5 min, 24/7"))
    tasks = [_task("Gamma_LevelRefresh", state="Ready",
                   triggers=[_trig("PT5M", "P3650D", enabled=False)])]
    assert _flags_of("NON_REPEATING_TRIGGER", A.evaluate_trigger_health(reg, tasks)) == [
        "Gamma_LevelRefresh"]


def test_accepts_a_correctly_shaped_repeating_trigger():
    reg = _registry(_row("Gamma_LevelRefresh", "every 5 min, 24/7"))
    tasks = [_task("Gamma_LevelRefresh", state="Ready",
                   triggers=[_trig("PT5M", "P3650D")])]
    assert A.evaluate_trigger_health(reg, tasks) == []


def test_repetition_on_any_one_trigger_satisfies_the_cadence():
    """Gamma_BrokerFills' real shape: a repeating RTH trigger + a separate one-shot EOD fire."""
    reg = _registry(_row("Gamma_BrokerFills",
                         "every 10 min, 09:00-16:00 ET wd + one 16:05 ET EOD fire"))
    tasks = [_task("Gamma_BrokerFills", state="Ready", triggers=[
        _trig("PT10M", "PT7H", ttype="WeeklyTrigger"),
        _trig(None, None, ttype="WeeklyTrigger"),
    ])]
    assert A.evaluate_trigger_health(reg, tasks) == []


def test_discrete_multi_fire_cadence_is_not_required_to_repeat():
    """Gamma_KeyLevelsSnapshot fires at 4 fixed clock times via 4 one-shot triggers.

    That is CORRECT design. Flagging it would train everyone to ignore the flag.
    """
    reg = _registry(_row("Gamma_KeyLevelsSnapshot", "08:35/09:30/12:00/15:50 ET weekdays"))
    tasks = [_task("Gamma_KeyLevelsSnapshot", state="Ready",
                   triggers=[_trig(None, None, ttype="WeeklyTrigger") for _ in range(4)])]
    assert A.evaluate_trigger_health(reg, tasks) == []


# ── REPETITION_INTERVAL_MISMATCH ─────────────────────────────────────────────
def test_flags_repetition_far_slower_than_documented():
    reg = _registry(_row("Gamma_LevelRefresh", "every 5 min, 24/7"))
    tasks = [_task("Gamma_LevelRefresh", state="Ready",
                   triggers=[_trig("PT1H", "P3650D")])]
    assert _flags_of("REPETITION_INTERVAL_MISMATCH", A.evaluate_trigger_health(reg, tasks)) == [
        "Gamma_LevelRefresh"]


def test_faster_than_documented_is_not_flagged():
    """Running MORE often than documented is not a blindness risk -- don't cry wolf."""
    reg = _registry(_row("Gamma_LevelRefresh", "every 5 min, 24/7"))
    tasks = [_task("Gamma_LevelRefresh", state="Ready", triggers=[_trig("PT1M", "P3650D")])]
    assert A.evaluate_trigger_health(reg, tasks) == []


# ── LIVE registry ────────────────────────────────────────────────────────────
@pytest.mark.slow
def test_live_registry_has_no_scheduled_task_drift():
    """The real instrument: run the evaluator against the LIVE Windows task registry.

    This is the assertion that would have screamed on the morning of 2026-07-30.
    """
    if sys.platform != "win32":
        pytest.skip("live Task Scheduler check is Windows-only")

    import os
    cwd = os.getcwd()
    os.chdir(_REPO)
    try:
        registry_text = A.REGISTRY_PATH.read_text(encoding="utf-8")
        tasks = A._registered_tasks()
    finally:
        os.chdir(cwd)

    # Empty scan must never read as clean (the 2026-07-14 structural-guard lesson).
    assert tasks, "0 tasks returned -- PowerShell helper failure, NOT a clean scan"
    assert any(t.get("triggers") for t in tasks), (
        "no task reported any trigger -- _list-gamma-tasks-json.ps1 stopped emitting "
        "trigger data, which would make every trigger-shape check silently vacuous"
    )

    flags = A.evaluate_trigger_health(registry_text, tasks)
    if flags:
        detail = "\n".join(f"  [{f['flag']}] {f['task']}: {f['note']}" for f in flags)
        pytest.fail(
            f"{len(flags)} scheduled-task drift flag(s) against the live registry:\n{detail}\n\n"
            "Either re-enable/re-register the task, or annotate its SCHEDULED-TASKS.md row "
            "if the pause is deliberate."
        )

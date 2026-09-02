"""Guard: quiet mode must never permanently starve a scheduled task.

THE INCIDENT (2026-08-26). Quiet Mode shipped 2026-08-24 with a 16:00->08:00 ET
blackout. It disabled 111 Gamma tasks each evening and restored them each morning
-- correctly, by its own logic. But 68 of those tasks have their ONLY trigger
INSIDE that window: the whole EOD pipeline (16:00-17:45), the nightly guard suite
(00:30), the GitHub secrets audit (23:00), unattended-health itself (02:02).
Each was disabled before its trigger fired and re-enabled after, every night.
They never ran again, and nothing noticed for two nights, because the watcher that
would have noticed (Gamma_UnattendedHealth, 02:02 ET) was in the starved set.

A blackout window plus a task that only fires inside it equals a task that is
silently dead. That is the invariant this file pins -- behaviourally, by asking
the LIVE Task Scheduler what is registered, never by trusting a doc or a list.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "setup" / "scripts"))

quiet_mode = pytest.importorskip("quiet_mode")

# This box runs Mountain time; Task Scheduler reports triggers in LOCAL time.
# ET = local + 2 (see CLAUDE.md -- the Ohio->Colorado scar). Never zoneinfo.
LOCAL_TO_ET_OFFSET_HOURS = 2

_PS_ENUMERATE = r"""
$rows = @()
Get-ScheduledTask -TaskName 'Gamma_*' | Where-Object { $_.State -ne 'Disabled' } | ForEach-Object {
  $name = $_.TaskName
  foreach ($t in $_.Triggers) {
    $interval = ''
    $duration = ''
    if ($t.Repetition) { $interval = $t.Repetition.Interval; $duration = $t.Repetition.Duration }
    $rows += [pscustomobject]@{
      Name = $name; Start = $t.StartBoundary; Interval = $interval; Duration = $duration
    }
  }
}
$rows | ConvertTo-Json -Depth 3
"""


def _live_triggers() -> dict[str, list[dict]]:
    out = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _PS_ENUMERATE],
        capture_output=True, text=True, timeout=180,
    )
    if out.returncode != 0:
        pytest.skip(f"Task Scheduler not enumerable here: {out.stderr.strip()[:200]}")
    raw = out.stdout.strip()
    if not raw:
        pytest.skip("no Gamma tasks registered on this box")
    rows = json.loads(raw)
    if isinstance(rows, dict):
        rows = [rows]
    by_task: dict[str, list[dict]] = {}
    for row in rows:
        by_task.setdefault(row["Name"], []).append(row)
    return by_task


def _iso8601_minutes(value: str | None) -> int | None:
    """PT30M / PT4H / P1D / PT23H59M -> minutes. None when absent or unparseable."""
    if not value:
        return None
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?", value.strip())
    if not m:
        return None
    days, hours, mins = (int(g) if g else 0 for g in m.groups())
    total = days * 1440 + hours * 60 + mins
    return total or None


def _fire_hours_et(trigger: dict) -> set[int] | None:
    """Every ET hour this trigger can fire in. None = unparseable (treated as safe)."""
    start = trigger.get("Start") or ""
    m = re.search(r"T(\d{2}):(\d{2})", start)
    if not m:
        return None  # non-time trigger (logon/boot/event) -- not a clock-window risk
    start_et = (int(m.group(1)) + LOCAL_TO_ET_OFFSET_HOURS) % 24
    start_min = int(m.group(2))

    interval = _iso8601_minutes(trigger.get("Interval"))
    if interval is None:
        return {start_et}

    duration = _iso8601_minutes(trigger.get("Duration")) or 1440
    duration = min(duration, 1440)  # a >24h repetition covers every hour anyway

    hours: set[int] = set()
    offset = 0
    while offset <= duration:
        hours.add((start_et + (start_min + offset) // 60) % 24)
        offset += interval
        if len(hours) == 24:
            break
    return hours


def _quiet_hours() -> dict[str, set[int]]:
    """The hours the blackout covers, asked of the real predicate, not a constant."""
    import datetime as dt

    from et_clock import ET_TZ as ET

    weekday = {h for h in range(24)
               if quiet_mode.in_quiet_window(dt.datetime(2026, 8, 24, h, 30, tzinfo=ET))}
    weekend = {h for h in range(24)
               if quiet_mode.in_quiet_window(dt.datetime(2026, 8, 29, h, 30, tzinfo=ET))}
    return {"weekday": weekday, "weekend": weekend}


def _starved() -> list[tuple[str, list[int]]]:
    quiet = _quiet_hours()
    # A task starves only if it is blacked out on EVERY day it could fire. A weekday
    # trigger is judged against weekday quiet hours; the weekend set is the stricter
    # one, so a task safe on a weekday is never starved outright.
    blackout = quiet["weekday"]
    starved: list[tuple[str, list[int]]] = []
    for name, triggers in _live_triggers().items():
        if name in quiet_mode.ESSENTIAL:
            continue
        reachable: set[int] = set()
        unparseable = False
        for trig in triggers:
            hours = _fire_hours_et(trig)
            if hours is None:
                unparseable = True
                break
            reachable |= hours
        if unparseable or not reachable:
            continue
        if reachable and reachable <= blackout:
            starved.append((name, sorted(reachable)))
    return sorted(starved)


def test_quiet_window_leaves_a_maintenance_band():
    """A blackout with no loud band cannot host any nightly work at all."""
    quiet = _quiet_hours()
    loud_weekday = set(range(24)) - quiet["weekday"]
    loud_weekend = set(range(24)) - quiet["weekend"]
    assert loud_weekday, "weekday blackout covers all 24h -- nothing could ever run"
    assert loud_weekend, "weekend blackout covers all 24h -- nightly work dies on weekends"
    # The band must be big enough to hold a real maintenance pass, not a token hour.
    assert len(loud_weekend) >= 6, (
        f"weekend loud band is only {len(loud_weekend)}h -- too small for the "
        "nightly guard/audit chain"
    )


def test_essential_set_covers_the_trading_chain():
    """Quiet mode must never be able to black out a market day."""
    must_survive = {
        "Gamma_HeartbeatCore", "Gamma_SightBeacon", "Gamma_LaunchTV", "Gamma_TvWatchdog",
        "Gamma_Premarket", "Gamma_EodFlatten", "Gamma_EodFlatten_Aggressive",
        "Gamma_EodFlattenCore", "Gamma_QuietMode",
    }
    missing = sorted(must_survive - quiet_mode.ESSENTIAL)
    assert not missing, f"trading-chain tasks not exempt from the blackout: {missing}"


def test_essential_set_covers_the_futures_trading_chain():
    """Quiet mode must never black out the futures market's own open.

    CME equity-index futures trade Sunday 18:00 ET -> Friday 17:00 ET (daily
    17:00-18:00 ET maintenance break). Quiet mode's own bands put Sunday
    18:00-23:00 ET inside the weekend-quiet band (WEEKEND_RESEARCH_END_HOUR),
    and weekday 18:00-23:00 ET is quiet too -- both are live GLOBEX time. The
    SPY chain is exempted by name "so a market day is never lost to quiet
    mode"; the futures chain needs the identical exemption on the identical
    rationale, or a session-open event during those hours is silently lost to
    whichever futures producer would need to react to it.
    """
    must_survive = {
        "Gamma_FuturesTrader", "Gamma_FuturesBrokerLane", "Gamma_FuturesMirror",
    }
    missing = sorted(must_survive - quiet_mode.ESSENTIAL)
    assert not missing, f"futures trading-chain tasks not exempt from the blackout: {missing}"

    # The exemption is only safe because these tasks never flash a window -- assert the
    # comment's claim against the real thing checked, not memory: quiet mode's own
    # exemption doctrine (module docstring) is popups/CPU, and ESSENTIAL already carries
    # other network-bound, $0, hidden-spawn tasks (Gamma_SightBeacon, Gamma_HeartbeatCore)
    # as precedent -- this test intentionally does not re-derive that from Task Scheduler
    # (the sibling starvation test below already does live enumeration) to stay fast and
    # offline-safe.


def test_no_registered_task_is_starved_by_the_quiet_window():
    """THE regression guard. Every enabled task must have a reachable fire time."""
    starved = _starved()
    assert not starved, (
        "These tasks can ONLY fire inside the quiet blackout, so they will be "
        "disabled before every trigger and re-enabled after it -- silently dead:\n"
        + "\n".join(f"  {n:34s} fires at ET hour(s) {h}" for n, h in starved)
        + "\n\nFix by re-timing the trigger into a loud band (23:00-08:00 ET), "
          "or by adding the task to quiet_mode.ESSENTIAL if it must survive the blackout."
    )


def test_essential_set_covers_the_blackout_reporter():
    """A monitor its own subject can switch off is not a monitor.

    THIS module's presence hold is what made Gamma_GuardsFull -- the ~11,400-test
    regression suite, the rig's main safety net -- dark from 2026-08-31 to 2026-09-02.
    Quiet mode disables ~120 tasks for J's evening and holds past its 23:00 ET clock while
    a fullscreen app is foreground; a trigger inside a hold is skipped, and because the task
    was *Disabled* rather than merely unavailable, Windows' StartWhenAvailable cannot
    recover the fire. Nothing noticed for 48 hours, because every existing surface reads
    State/LastTaskResult -- neither of which moves when a task never starts.

    Gamma_TaskStaleness reads the two fields that do (LastRunTime, NumberOfMissedRuns) and
    names this hold as the cause. Leaving it disable-able would mean the first thing a long
    blackout silences is the alarm about the blackout -- the same self-silencing shape as
    the prereg-hygiene orphan-proxy bug found the night before, where filing the
    adjudication drove the flagged count 6 -> 0 with nothing resolved.

    Safe to exempt because it is report-only: $0, pure stdlib, and it never enables,
    disables, starts or kills anything (pinned separately by
    test_scheduled_task_staleness_2026_09_02.py::test_module_has_no_write_side_effects_on_import).
    """
    assert "Gamma_TaskStaleness" in quiet_mode.ESSENTIAL, (
        "the instrument that reports what the blackout disabled must survive the blackout"
    )

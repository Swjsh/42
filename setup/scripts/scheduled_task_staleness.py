"""scheduled_task_staleness.py -- did each scheduled task ACTUALLY RUN, or does it merely
look healthy?

WHY THIS EXISTS (2026-09-02). `Gamma_GuardsFull` -- the full ~11,400-test regression suite,
the rig's main safety net -- produced no verdict between 2026-08-31 and 2026-09-02, and
EVERY existing surface reported it healthy the whole time:

    State           : Ready          <- task_state_guard.py checks exactly this
    LastTaskResult  : 0              <- ...and this
    LastRunTime     : 8/31 07:31     <- nothing read this
    NumberOfMissedRuns : 2           <- nothing read this either

`task_state_guard.py` verifies a pinned task is ENABLED and its last result was 0. Neither
field moves when a task simply never starts, so a task can go dark indefinitely while every
dashboard stays green. That is the same shape as the two silent futures outages of August
(fillsim ghost-order deadlock, 15 sessions; broker-lane transport failures, 0/8 armed
orders) -- the digests graded GREEN throughout both.

THE ROOT CAUSE IT WAS BUILT FROM (proven 2026-09-02 by a 7/7 differential, not assumed):
quiet mode disables ~120 Gamma tasks to protect J's evening, and holds the blackout PAST
the 23:00 ET clock while a fullscreen app is in the foreground. A task whose trigger falls
inside a hold is skipped -- and because the task was *Disabled* rather than merely
unavailable, Windows' `StartWhenAvailable` cannot recover it. Nothing re-runs it. Evidence,
2026-09-01 (all times ET, from quiet-mode.log and each task's own trigger):

    23:02-23:22  QUIET HELD (SparkingZERO fullscreen, then linger)
    23:05  Gamma_FuturesBrokerProbe  -> MISSED   (inside hold)
    23:15  Gamma_GuardsFull          -> MISSED   (inside hold)
    23:22  QUIET OFF: re-enabled=120/120
    23:30  Gamma_SpendSummary        -> RAN      (outside hold)
    23:40  Gamma_OosCheck            -> RAN      (outside hold)
    23:58  Gamma_LicenseMonitor      -> RAN      (outside hold)
    00:07-00:42  QUIET HELD again (r5apex_dx12)
    00:30  Gamma_GuardsNightly       -> MISSED   (inside hold)
    01:00  Gamma_GateExpiryCheck     -> RAN      (outside hold)

Seven tasks, seven correct predictions from one rule. So this reporter does two things:
flag the staleness, and NAME that cause when the evidence supports it -- an alarm that
explains itself is acted on; one that does not gets muted.

DESIGN RULES (each one is a scar):
  * NO_DATA / UNKNOWN is NEVER ranked better than GREEN. A task we could not read is not a
    passing task. (Ranking NO_DATA at 0 would grade a box with no scheduler at all as a
    clean pass -- the same C7 defect found in first_live_day_review.py the same night.)
  * A DISABLED task is reported as DISABLED, not RED. Quiet mode disables scores of tasks
    every evening BY DESIGN; alarming on that cries wolf nightly and gets the whole
    instrument ignored -- which is precisely how the outages above survived.
  * Tolerance is DERIVED from each task's own trigger cadence, never hardcoded. A 5-minute
    repeater and a weekly Sunday task cannot share a staleness bar.
  * Report only. This never enables, disables, starts, or kills anything.
  * Fail-open everywhere: an unreadable input degrades that row to UNKNOWN and the run
    still produces a file.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "automation" / "state"
QUIET_LOG = STATE_DIR / "quiet-mode.log"
OUT_FILE = STATE_DIR / "scheduled-task-staleness.json"

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

try:  # pragma: no cover - trivial import shim
    ET = dt.timezone(dt.timedelta(hours=-4))  # replaced below by the real zone if available
    from zoneinfo import ZoneInfo

    ET = ZoneInfo("America/New_York")  # type: ignore[assignment]
except Exception:  # noqa: BLE001 -- a fixed-offset ET is better than crashing
    pass


# --------------------------------------------------------------------------------------
# Verdict ordering. Deliberately explicit: UNKNOWN sits ABOVE green, because "we could not
# tell" is a finding, not a pass. DISABLED is its own bucket and never escalates.
# --------------------------------------------------------------------------------------
SEVERITY = {"GREEN": 0, "DISABLED": 0, "UNKNOWN": 1, "YELLOW": 1, "RED": 2}


def worst(verdicts: list[str]) -> str:
    """Worse-wins over SEVERITY. Empty input is UNKNOWN, never GREEN -- a run that
    classified nothing has not verified anything."""
    if not verdicts:
        return "UNKNOWN"
    return max(verdicts, key=lambda v: (SEVERITY.get(v, 1), v))


# --------------------------------------------------------------------------------------
# Impure boundary: the single PowerShell round-trip. This is what a test mocks.
# --------------------------------------------------------------------------------------

_PS_QUERY = r"""
$out = @()
foreach ($t in (Get-ScheduledTask | Where-Object { $_.TaskName -like 'Gamma*' })) {
  $i = Get-ScheduledTaskInfo -TaskName $t.TaskName -ErrorAction SilentlyContinue
  $trig = $t.Triggers | Select-Object -First 1
  $rep = $null
  $dur = $null
  if ($trig -and $trig.Repetition -and $trig.Repetition.Interval) {
    $rep = $trig.Repetition.Interval
    $dur = $trig.Repetition.Duration
  }
  $kind = if ($trig) { $trig.CimClass.CimClassName } else { 'NONE' }
  $out += [pscustomobject]@{
    name        = $t.TaskName
    state       = [string]$t.State
    lastRun     = if ($i -and $i.LastRunTime) { $i.LastRunTime.ToString('o') } else { $null }
    nextRun     = if ($i -and $i.NextRunTime) { $i.NextRunTime.ToString('o') } else { $null }
    lastResult  = if ($i) { $i.LastTaskResult } else { $null }
    missedRuns  = if ($i) { $i.NumberOfMissedRuns } else { $null }
    triggerKind = [string]$kind
    startBound  = if ($trig) { [string]$trig.StartBoundary } else { $null }
    repeat      = [string]$rep
    repeatFor   = [string]$dur
  }
}
$out | ConvertTo-Json -Depth 4 -Compress
"""


def query_tasks(timeout: int = 120) -> Optional[list[dict]]:
    """One PowerShell round-trip for every Gamma_* task.

    Returns None (NOT []) on a total query failure, so the caller can tell "the scheduler
    query broke" from "there are genuinely no Gamma tasks" -- conflating those would report
    a healthy-looking empty run on a box whose Task Scheduler is unreachable.
    """
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", _PS_QUERY],
            capture_output=True, text=True, timeout=timeout,
            creationflags=_CREATE_NO_WINDOW,
        )
    except Exception:  # noqa: BLE001 -- fail-open
        return None
    raw = (proc.stdout or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return None
    return [r for r in data if isinstance(r, dict) and r.get("name")]


# --------------------------------------------------------------------------------------
# Cadence -> tolerance. Derived per task, never a global constant.
# --------------------------------------------------------------------------------------

_ISO_DUR = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


def parse_iso_duration_minutes(value: Optional[str]) -> Optional[float]:
    """'PT5M' -> 5.0, 'PT1H15M' -> 75.0, 'P1D' -> 1440.0. None on anything unparseable --
    callers must treat None as 'no repetition known', never as zero."""
    if not value or not isinstance(value, str):
        return None
    m = _ISO_DUR.match(value.strip())
    if not m:
        return None
    parts = {k: int(v) for k, v in m.groupdict(default="0").items()}
    total = parts["days"] * 1440 + parts["hours"] * 60 + parts["minutes"] + parts["seconds"] / 60.0
    return total or None


def tolerance_minutes(row: dict) -> tuple[float, str]:
    """How long may this task go without running before that is a finding?

    Returns (minutes, basis) -- the basis string is carried into the report so a reader can
    see WHY a bar was applied rather than having to trust a bare number.
    """
    rep = parse_iso_duration_minutes(row.get("repeat"))
    if rep:
        window = parse_iso_duration_minutes(row.get("repeatFor"))
        if window:
            # A BOUNDED repeater (e.g. every 20m for 40m, or every 2m for 6h26m) is really a
            # DAILY task with a burst inside it. Judging it on 4 intervals flags it RED for
            # the 23 hours a day it is idle BY DESIGN -- which is how a monitor earns being
            # muted. Verified against the live box 2026-09-02: Gamma_RosterLiveness (PT20M
            # for PT40M, last run 21.2h earlier) was RED under the interval bar and is GREEN
            # under this one, while a genuine two-day outage still clears the bar.
            tol = 1440.0 + window + max(rep * 4, 30.0)
            return tol, (f"repeats every {rep:g}m for {window:g}m, then idle by design "
                         f"(bar = 24h + window + slack)")
        # An UNBOUNDED repeater ticks all day, so it self-heals on its next tick and only a
        # sustained gap matters.
        return max(rep * 4, 30.0), f"repeating every {rep:g}m (bar = 4 intervals, min 30m)"

    kind = (row.get("triggerKind") or "").lower()
    if "weekly" in kind:
        # 7 days + 2 days slack: one skipped week is a finding, a late Sunday is not.
        return 9 * 1440.0, "weekly trigger (bar = 9 days)"
    if "daily" in kind:
        # 36h catches ONE missed nightly fire. Two missed nights is what went unnoticed
        # for 48 hours on 2026-08-31; 48h+ bars would have stayed silent through it.
        return 36 * 60.0, "daily trigger (bar = 36h -- one missed fire)"
    if "logon" in kind or "boot" in kind or "registration" in kind:
        return 30 * 1440.0, "logon/boot trigger (bar = 30 days, informational only)"
    if kind in ("", "none"):
        return 0.0, "no trigger found"
    return 7 * 1440.0, f"unrecognised trigger '{row.get('triggerKind')}' (bar = 7 days)"


def _parse_dt(value: Optional[str]) -> Optional[dt.datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
    return parsed


# Windows reports LastRunTime as 1999-11-30T00:00:00 for a task that has NEVER run. Read
# literally that is a 26-year staleness, and the first cut of this script duly graded two
# freshly-registered tasks RED with "last ran 234553.6h ago" -- a confident, precise, wrong
# number. Never-run and long-dark are different findings and must not render alike.
NEVER_RAN_SENTINEL_YEAR = 1999


def is_never_ran(stamp: Optional[dt.datetime]) -> bool:
    return stamp is not None and stamp.year <= NEVER_RAN_SENTINEL_YEAR


# --------------------------------------------------------------------------------------
# Quiet-hold attribution -- turns "task X is stale" into "task X is stale BECAUSE".
# --------------------------------------------------------------------------------------

_QUIET_LINE = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2}T[\d:.]+[+-]\d{2}:\d{2})\s+(?P<msg>.*)$")


def parse_quiet_holds(log_text: Optional[str], lookback_days: int = 7,
                      now: Optional[dt.datetime] = None) -> list[tuple[dt.datetime, dt.datetime]]:
    """Reconstruct [hold_start, hold_end) intervals from quiet-mode.log.

    A hold OPENS on the first 'QUIET HELD past the clock' after any 'QUIET OFF', and CLOSES
    on the next 'QUIET OFF'. An unterminated trailing hold is closed at `now` -- the
    blackout is, by definition, still running.

    Returns [] on missing/unreadable input. [] means 'no attribution available', which the
    caller must NOT render as 'quiet mode was not involved'.
    """
    if not log_text:
        return []
    now = now or dt.datetime.now(ET)
    floor = now - dt.timedelta(days=lookback_days)

    holds: list[tuple[dt.datetime, dt.datetime]] = []
    open_at: Optional[dt.datetime] = None
    for line in log_text.splitlines():
        m = _QUIET_LINE.match(line.strip())
        if not m:
            continue
        ts = _parse_dt(m.group("ts"))
        if ts is None or ts < floor:
            continue
        msg = m.group("msg")
        if "QUIET HELD past the clock" in msg:
            if open_at is None:
                open_at = ts
        elif "QUIET OFF" in msg:
            if open_at is not None:
                holds.append((open_at, ts))
                open_at = None
    if open_at is not None:
        holds.append((open_at, now))
    return holds


def scheduled_times_in_window(start_boundary: Optional[str], window_start: dt.datetime,
                              window_end: dt.datetime) -> list[dt.datetime]:
    """Every daily occurrence of `start_boundary`'s time-of-day inside the window.

    Only daily cadence is projected: it is the cadence that actually loses runs to a hold,
    and guessing a weekly/monthly recurrence from one boundary would manufacture false
    attributions. Returns [] on an unparseable boundary.
    """
    anchor = _parse_dt(start_boundary)
    if anchor is None or window_end <= window_start:
        return []
    out: list[dt.datetime] = []
    day = window_start.astimezone(anchor.tzinfo).date()
    last = window_end.astimezone(anchor.tzinfo).date()
    while day <= last:
        occ = dt.datetime.combine(day, anchor.timetz())
        if window_start <= occ <= window_end:
            out.append(occ)
        day += dt.timedelta(days=1)
    return out


def attribute_quiet_hold(row: dict, holds: list[tuple[dt.datetime, dt.datetime]],
                         now: Optional[dt.datetime] = None) -> Optional[str]:
    """Did this task's own trigger time land inside a recorded quiet hold? Returns a
    human-readable reason, or None when the evidence does not support the claim.

    Deliberately conservative: no holds parsed -> None (never 'quiet mode was innocent'),
    non-daily trigger -> None, boundary unreadable -> None.
    """
    if not holds:
        return None
    if "daily" not in (row.get("triggerKind") or "").lower():
        return None
    now = now or dt.datetime.now(ET)
    window_start = min(h[0] for h in holds)
    occurrences = scheduled_times_in_window(row.get("startBound"), window_start, now)
    hits = [occ for occ in occurrences
            if any(h_start <= occ <= h_end for h_start, h_end in holds)]
    if not hits:
        return None
    when = ", ".join(o.astimezone(ET).strftime("%m-%d %H:%M ET") for o in hits[-3:])
    return (f"{len(hits)} scheduled start(s) fell inside a quiet-mode hold ({when}) -- "
            "a task disabled at its trigger is skipped, and StartWhenAvailable cannot "
            "recover a fire missed while Disabled")


# --------------------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------------------

def classify_task(row: dict, now: Optional[dt.datetime] = None,
                  holds: Optional[list[tuple[dt.datetime, dt.datetime]]] = None) -> dict:
    """One task -> {name, verdict, reason, ...}. Never raises."""
    now = now or dt.datetime.now(ET)
    name = str(row.get("name") or "?")
    state = str(row.get("state") or "").strip()
    missed = row.get("missedRuns")
    tol, basis = tolerance_minutes(row)
    last_run = _parse_dt(row.get("lastRun"))
    never_ran = is_never_ran(last_run)
    if never_ran:
        last_run = None

    result = {
        "name": name,
        "state": state,
        "missed_runs": missed if isinstance(missed, int) else None,
        "last_run": last_run.astimezone(ET).isoformat() if last_run else None,
        "tolerance_minutes": tol,
        "tolerance_basis": basis,
        "stale_minutes": None,
        "cause": None,
    }

    # A Disabled task is a deliberate state, not an outage. Quiet mode disables ~120 tasks
    # every evening; alarming here would make the instrument noise on every single run.
    if state.lower() in ("disabled", "1"):
        result.update(verdict="DISABLED",
                      reason="task is Disabled -- deliberate state (quiet mode disables "
                             "scores of tasks nightly); not counted as an outage")
        return result

    if last_run is not None:
        result["stale_minutes"] = round((now - last_run).total_seconds() / 60.0, 1)

    # NumberOfMissedRuns is the scheduler's OWN answer and is what exposed this failure
    # class. It leads. LastRunTime staleness is the corroborating read.
    if isinstance(missed, int) and missed >= 1:
        verdict = "RED" if missed >= 2 else "YELLOW"
        reason = (f"Windows recorded {missed} missed scheduled start(s) -- the task did not "
                  f"run when its trigger fired (State={state or '?'}, so nothing about "
                  "enabled-ness or last exit code would show this)")
        cause = attribute_quiet_hold(row, holds or [], now)
        if cause:
            reason += f". LIKELY CAUSE: {cause}"
            result["cause"] = "quiet_mode_hold"
        result.update(verdict=verdict, reason=reason)
        return result

    if last_run is None:
        detail = ("Windows reports the never-ran sentinel (1999-11-30)"
                  if never_ran else "no LastRunTime recorded")
        nxt = _parse_dt(row.get("nextRun"))
        when = f"; next scheduled {nxt.astimezone(ET):%m-%d %H:%M ET}" if nxt else ""
        result.update(verdict="UNKNOWN",
                      reason=f"this task has NEVER run -- {detail}{when}. Expected for a "
                             "freshly registered task; an outage if it has been registered "
                             "for days (never reported as healthy either way)")
        return result

    if tol <= 0:
        result.update(verdict="UNKNOWN",
                      reason="no trigger found on this task -- nothing will ever start it "
                             "on a schedule")
        return result

    stale = result["stale_minutes"] or 0.0
    if stale > tol * 2:
        result.update(verdict="RED",
                      reason=f"last ran {stale/60:.1f}h ago, more than double its bar "
                             f"({tol/60:.1f}h; {basis})")
    elif stale > tol:
        result.update(verdict="YELLOW",
                      reason=f"last ran {stale/60:.1f}h ago, past its bar "
                             f"({tol/60:.1f}h; {basis})")
    else:
        result.update(verdict="GREEN",
                      reason=f"last ran {stale/60:.1f}h ago, inside its bar "
                             f"({tol/60:.1f}h; {basis})")
    return result


def build_report(rows: Optional[list[dict]], now: Optional[dt.datetime] = None,
                 quiet_log_text: Optional[str] = None) -> dict:
    """Full report. `rows is None` (query failure) is UNKNOWN, never GREEN."""
    now = now or dt.datetime.now(ET)
    stamp = now.astimezone(ET).strftime("%Y-%m-%d %H:%M:%S ET")

    if rows is None:
        return {
            "generated_at_et": stamp,
            "verdict": "UNKNOWN",
            "reason": "the scheduler query itself failed -- no task could be evaluated",
            "counts": {}, "tasks": [], "findings": [],
        }

    holds = parse_quiet_holds(quiet_log_text, now=now)
    tasks = [classify_task(r, now=now, holds=holds) for r in rows]

    counts: dict[str, int] = {}
    for t in tasks:
        counts[t["verdict"]] = counts.get(t["verdict"], 0) + 1

    gating = [t["verdict"] for t in tasks if t["verdict"] != "DISABLED"]
    verdict = worst(gating) if gating else "UNKNOWN"

    findings = sorted(
        (t for t in tasks if t["verdict"] in ("RED", "YELLOW", "UNKNOWN")),
        key=lambda t: (-SEVERITY.get(t["verdict"], 1), -(t.get("stale_minutes") or 0)),
    )
    return {
        "generated_at_et": stamp,
        "verdict": verdict,
        "reason": (f"{counts.get('RED', 0)} RED / {counts.get('YELLOW', 0)} YELLOW / "
                   f"{counts.get('UNKNOWN', 0)} UNKNOWN across "
                   f"{len(gating)} enabled task(s); {counts.get('DISABLED', 0)} disabled "
                   "(not counted -- quiet mode disables by design)"),
        "quiet_holds_parsed": len(holds),
        "counts": counts,
        "findings": findings,
        "tasks": sorted(tasks, key=lambda t: t["name"]),
    }


def write_report(report: dict, out_path: Path = OUT_FILE) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2)
    payload.encode("utf-8")  # pre-flight: never truncate an existing file on an encode error
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(out_path)
    return out_path


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true", help="print the full report to stdout")
    ap.add_argument("--no-write", action="store_true", help="do not write the state file")
    args = ap.parse_args(argv)

    rows = query_tasks()
    quiet_text = None
    try:
        if QUIET_LOG.exists():
            quiet_text = QUIET_LOG.read_text(encoding="utf-8", errors="replace")
    except OSError:
        quiet_text = None

    report = build_report(rows, quiet_log_text=quiet_text)
    if not args.no_write:
        write_report(report)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"[{report['generated_at_et']}] {report['verdict']}: {report['reason']}")
        for f in report["findings"][:12]:
            print(f"  {f['verdict']:<7} {f['name']:<34} {f['reason']}")
    return 0  # fail-open: a monitor that can break the caller is worse than no monitor


if __name__ == "__main__":
    sys.exit(main())

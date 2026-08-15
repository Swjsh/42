"""unattended_health -- ONE traffic light per unattended unit, with a memory.

WHY THIS EXISTS (J 2026-08-09)
------------------------------
    "we need to find, consolidate, and document all running processes, audits,
     pipelines, etc, anything unattended, then turn it into a nice tile on the
     app that is red or green or yellow ... i want to know if things break when
     they go down now days after the facts"

The rig runs ~124 registered Windows tasks and 6 long-lived daemons.  Three
partial instruments already existed and NONE of them answered that question:

  * ``audit_scheduled_tasks.py``  -- registry-vs-reality BOOKKEEPING for Gamma_*
    tasks.  Says a task is undocumented; says nothing about whether the pipeline
    it belongs to still produces anything.
  * ``state_freshness_audit.py``  -- 17 files on the LIVE DECISION PATH.  Blind
    to research, audit, comms and infra units entirely.
  * ``engine_health.py``          -- the live trading path only, and it is itself
    one of the unattended things that can die.

And all three are STATELESS: each run reports NOW.  An outage that started on
Tuesday and self-healed on Thursday left no trace anywhere, which is precisely
the "days after the fact" hole J named.

WHAT THIS ADDS
--------------
1. A UNIT abstraction (``automation/state/unattended-registry.json``): a pipeline
   / audit / daemon / engine, its member tasks, its output-freshness contracts,
   its daemons -- and a mandatory ``breaks`` sentence naming what silently
   degrades while it is down.  A traffic light with no consequence attached is
   just decoration.
2. THREE INDEPENDENT AXES per unit, worst-wins:
     a. TASK liveness  -- disabled / never-run / nonzero exit / hasn't fired
        within its own trigger's cadence (weekend- and window-aware).
     b. ARTIFACT freshness -- delegated verbatim to
        ``state_freshness_audit.evaluate_entry`` so a contract is never
        copy-pasted (L294).  Manifest-owned paths are referenced BY PATH, so the
        contract keeps living in exactly one file.
     c. DAEMON liveness -- pid file exists AND that pid is a live process.
   A unit can pass (a) and fail (b): the task fires on schedule and writes
   yesterday's payload.  That is the failure class no task-liveness check sees.
3. MEMORY.  Every status TRANSITION is appended to
   ``automation/state/unattended-events.jsonl`` and each unit carries
   ``since`` / ``last_green_at`` / ``down_minutes`` in the snapshot.  A unit that
   went dark on Tuesday still reads "RED for 3d 4h" on Sunday.
4. AN ANTI-ROT COVERAGE DIFF.  Every live ``Gamma_*`` task claimed by no unit
   surfaces in the ``unregistered`` bubble; every registry task missing from Task
   Scheduler reddens its own unit.  A monitor whose SCOPE rots is L292 -- this
   one cannot silently narrow, because the scope is computed against live truth
   on every run rather than declared once.

FAIL-OPEN CONTRACT
------------------
MONITORING fails open.  This module NEVER gates an entry and NEVER raises into
its caller: an unreadable registry, a dead PowerShell enumeration or a malformed
snapshot degrades that piece to ``UNKNOWN`` and the run still writes a payload.
A broken monitor must never be able to look like a broken rig, and must never be
able to take anything else down with it.

Pure Python + one PowerShell enumeration.  No LLM, no network -- $0/run.

USAGE
-----
    python setup/scripts/unattended_health.py            # human table
    python setup/scripts/unattended_health.py --json     # machine payload
    python setup/scripts/unattended_health.py --no-write # evaluate, write nothing

Writes:  automation/state/unattended-health.json   (snapshot)
         automation/state/unattended-events.jsonl  (transitions, capped)
Reads:   automation/state/unattended-registry.json
         automation/state/state-freshness-manifest.json
Guard:   backtest/tests/test_unattended_health.py
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO / "setup" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

REGISTRY = REPO / "automation" / "state" / "unattended-registry.json"
MANIFEST = REPO / "automation" / "state" / "state-freshness-manifest.json"
SNAPSHOT = REPO / "automation" / "state" / "unattended-health.json"
EVENTS = REPO / "automation" / "state" / "unattended-events.jsonl"

# OP-22: every append-only producer carries a retention cap.
EVENTS_MAX_LINES = 5000

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

STATUS_RANK = {"GREEN": 0, "OFF": 1, "UNKNOWN": 2, "YELLOW": 3, "RED": 4}
_BY_CRIT = {"critical": "RED", "high": "RED", "medium": "YELLOW", "low": "YELLOW"}

# How many cadences of silence before a task is called dead. Frequent tasks are
# noisy (a keepalive can skip a beat), so they get 3; daily/weekly ones get 2,
# which tolerates EXACTLY ONE missed run -- a weekly task that skips two weeks
# must not hide behind a multiplier sized for a 1-minute keepalive.
_MULT_SUBDAILY = 3.0
_MULT_DAILY_PLUS = 2.0

# Task Scheduler sentinels. 267011 = SCHED_S_TASK_HAS_NOT_RUN, 267009 = currently
# running, 267014 = terminated by user. Only 0 and "running" are unambiguously OK.
_RESULT_NEVER_RUN = 267011
_RESULT_RUNNING = 267009
_NEVER_RUN_SENTINEL_YEAR = 1999


# ---------------------------------------------------------------------------
# Clock -- ET only. This box runs Mountain time; a naive local read shifts every
# date by 2h and silently mis-scores every weekday/weekend gate below.
# ---------------------------------------------------------------------------

def _et_now() -> datetime:
    from et_clock import et_now  # noqa: PLC0415 -- deferred so a broken import is catchable
    return et_now().replace(tzinfo=None)


def _et_offset_hours(now_et: datetime) -> int:
    """ET-minus-LOCAL offset AT `now_et`, so mtimes/naive locals convert across DST.

    Derived from the two zones' own UTC offsets on that date -- NEVER by
    differencing `now_et` against the live wall clock. The wall-clock form was
    only correct when `now_et` happened to BE now: it silently redefined
    "timezone offset" as "how far in the past the caller's clock is", so a
    frozen fixture clock 5.8 days back returned -140 "hours" and shifted every
    converted timestamp by ~6 days -- turning 2-hour-old tasks into 5.9-day
    outages. `evaluate_task` documents itself as pure given (task, now_et);
    this is what makes that claim true.
    """
    from et_clock import et_offset_hours  # noqa: PLC0415 -- deferred, matches _et_now
    et_from_utc = et_offset_hours(now_et.replace(tzinfo=timezone.utc))
    local = now_et.astimezone().utcoffset()
    if local is None:  # no local tz resolvable -- treat local AS ET rather than guess
        return 0
    return et_from_utc - round(local.total_seconds() / 3600.0)


# ---------------------------------------------------------------------------
# Trigger shape -> "longest legitimate gap between two runs"
# ---------------------------------------------------------------------------

_DUR_RE = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


def parse_iso_duration_minutes(value: Optional[str]) -> Optional[float]:
    """'PT5M' -> 5.0, 'P1D' -> 1440.0. None/unparseable -> None (never raises)."""
    if not value or not isinstance(value, str):
        return None
    m = _DUR_RE.match(value.strip())
    if not m:
        return None
    parts = {k: float(v) for k, v in m.groupdict(default="0").items()}
    total = parts["days"] * 1440 + parts["hours"] * 60 + parts["minutes"] + parts["seconds"] / 60
    return total or None


def _dow_bit(day: datetime) -> int:
    """Windows DaysOfWeek bitmask bit for a date (1=Sun, 2=Mon, ... 64=Sat)."""
    return 1 << ((day.weekday() + 1) % 7)


_DOW_NAME_BITS = {
    "sunday": 1, "monday": 2, "tuesday": 4, "wednesday": 8,
    "thursday": 16, "friday": 32, "saturday": 64,
}


def _dow_mask_value(dow: Any) -> int:
    """Normalise a trigger's DaysOfWeek to a Windows bitmask. Never raises.

    The live enumerator (`_list-gamma-tasks-json.ps1`) casts `[int]$tr.DaysOfWeek`,
    so today this is always an int or null. It is normalised anyway because a bare
    `int(dow)` raises TypeError on a list -- and a crash inside the health monitor
    takes down the surface whose whole job is noticing that things are down (C7).
    Accepts: 62 | "62" | ["Monday", "Friday"] | [2, 32] | "Monday".
    """
    if isinstance(dow, bool) or dow is None:
        return 0
    if isinstance(dow, (int, float)):
        return int(dow)
    if isinstance(dow, str):
        name = _DOW_NAME_BITS.get(dow.strip().lower())
        if name is not None:
            return name
        try:
            return int(dow.strip())
        except ValueError:
            return 0
    if isinstance(dow, (list, tuple, set, frozenset)):
        mask = 0
        for item in dow:
            mask |= _dow_mask_value(item)
        return mask
    return 0


def _scheduled_days_mask(triggers: list[dict]) -> Optional[int]:
    """Union of DaysOfWeek across enabled triggers, or None when unrestricted.

    A task whose only trigger is Mon-Fri is LEGITIMATELY silent all weekend; one
    with a plain daily trigger fires every day even if its script self-gates on
    weekends (last_run still advances). Honouring the live mask -- rather than
    assuming 'trading things are weekday things' -- is what keeps Monday morning
    from being a wall of false REDs.
    """
    mask = 0
    saw_unrestricted = False
    for t in triggers:
        if not t.get("enabled", True):
            continue
        bits = _dow_mask_value(t.get("days_of_week"))
        if bits:
            mask |= bits
        else:
            saw_unrestricted = True
    if saw_unrestricted or not mask:
        return None
    return mask


def expected_gap_minutes(triggers: list[dict]) -> tuple[Optional[float], str]:
    """Longest legitimate gap between two fires, from the LIVE trigger shape.

    Returns (minutes, why). None means "no cadence contract" -- a one-shot or a
    boot/logon trigger, which cannot be scored on silence.

    A repetition whose duration is under a day (e.g. PT1M repeating for PT6H30M
    of RTH) does NOT mean the task may only ever be 1 minute quiet: it re-arms
    daily, so the honest budget is 24h, not the interval. Scoring those on the
    interval is how an overnight monitor turns into a nightly false alarm.
    """
    best: Optional[float] = None
    why = "no cadence contract (one-shot / boot / logon trigger)"
    for t in triggers:
        if not t.get("enabled", True):
            continue
        ttype = str(t.get("type") or "")
        interval = parse_iso_duration_minutes(t.get("repetition_interval"))
        duration = parse_iso_duration_minutes(t.get("repetition_duration"))
        cadence: Optional[float] = None
        label = ""
        if interval:
            if duration is not None and duration < 1440:
                cadence, label = 1440.0, f"repeats every {interval:.0f}m within a {duration:.0f}m daily window"
            else:
                cadence, label = interval, f"repeats every {interval:.0f}m"
        elif "Daily" in ttype:
            cadence, label = 1440.0, "daily trigger"
        elif "Weekly" in ttype:
            # A WeeklyTrigger carrying a DaysOfWeek mask is NOT a 7-day cadence --
            # most of this rig's "weekly" triggers are Mon-Fri (mask 62), i.e. a
            # DAILY task that skips weekends. Score it daily and let the mask's
            # unscheduled-day slack absorb the skipped days; scoring it at 10080m
            # would give a Mon-Fri task a three-week licence to be dead.
            if _dow_mask_value(t.get("days_of_week")):
                cadence, label = 1440.0, "fires on its scheduled weekdays"
            else:
                cadence, label = 10080.0, "weekly trigger"
        elif "Monthly" in ttype:
            cadence, label = 44640.0, "monthly trigger"
        if cadence is not None and (best is None or cadence < best):
            best, why = cadence, label
    return best, why


def _earliest_start(triggers: list[dict]) -> Optional[datetime]:
    """Earliest enabled trigger start boundary -- the point from which a task
    COULD have fired. A task registered/rewritten an hour ago has not 'never run'
    in any meaningful sense, and Task Scheduler's own RegistrationInfo.Date is
    null on every task in this rig, so the start boundary is the usable clock."""
    stamps = [_parse_ts(t.get("start_boundary")) for t in triggers if t.get("enabled", True)]
    real = [s for s in stamps if s is not None]
    return min(real) if real else None


def _budget_minutes(cadence: float, slack: float) -> float:
    mult = _MULT_SUBDAILY if cadence < 1440 else _MULT_DAILY_PLUS
    return cadence * mult + slack


def unscheduled_days_between(start: datetime, end: datetime, mask: Optional[int]) -> int:
    """Whole calendar days in (start, end] that the DaysOfWeek mask excludes."""
    if not mask:
        return 0
    n, day = 0, (start + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    while day <= end and n < 400:  # bounded: never loop on a garbage timestamp
        if not (_dow_bit(day) & mask):
            n += 1
        day += timedelta(days=1)
    return n


# ---------------------------------------------------------------------------
# Live task enumeration
# ---------------------------------------------------------------------------

def _powershell(script: str) -> str:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-Command", script],
        capture_output=True, text=True, check=False, creationflags=_CREATE_NO_WINDOW,
    ).stdout


def live_tasks() -> tuple[list[dict], Optional[str]]:
    """(tasks, error). Reuses audit_scheduled_tasks' enumerator so there is ONE
    task-enumeration path in the repo, not two that drift (L294)."""
    try:
        from audit_scheduled_tasks import _registered_tasks  # noqa: PLC0415
        return _registered_tasks(), None
    except Exception as e:  # noqa: BLE001 -- monitoring fails open
        return [], f"task enumeration failed: {type(e).__name__}: {e}"


def _parse_ts(value: Any) -> Optional[datetime]:
    """Parse Task Scheduler's ISO stamps to naive LOCAL time. The 1999-11-30
    sentinel ('never ran') is returned as None -- it is not a timestamp."""
    if not isinstance(value, str) or len(value) < 10:
        return None
    txt = value.strip().replace("Z", "")
    txt = re.sub(r"[+-]\d{2}:\d{2}$", "", txt)
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(txt[:26] if "." in txt else txt, fmt)
        except ValueError:
            continue
        return None if dt.year <= _NEVER_RUN_SENTINEL_YEAR else dt
    return None


# ---------------------------------------------------------------------------
# Axis A -- task liveness
# ---------------------------------------------------------------------------

def evaluate_task(task: dict, unit_crit: str, now_et: datetime,
                  expect_disabled: dict) -> dict:
    """Score ONE Windows task. Pure apart from its inputs, so the guard can drive
    it with synthetic task dicts and a frozen clock."""
    name = task.get("name", "?")
    state = str(task.get("state") or "Unknown")
    fail = _BY_CRIT.get(unit_crit, "YELLOW")
    out = {"name": name, "state": state, "status": "GREEN", "detail": ""}

    if state == "Disabled":
        if name in expect_disabled:
            out["status"] = "OFF"
            out["detail"] = f"off by design -- {expect_disabled[name]}"
        else:
            out["status"] = fail
            out["detail"] = ("DISABLED in Task Scheduler with no documented reason "
                             "-- add it to the unit's expect_disabled if intentional")
        return out

    triggers = task.get("triggers") or []
    cadence, why = expected_gap_minutes(triggers)
    last_run = _parse_ts(task.get("last_run"))
    result = task.get("last_result")

    if not any(t.get("enabled", True) for t in triggers):
        out["status"] = fail
        out["detail"] = "every trigger is DISABLED -- the task will never fire again"
        return out

    offset = _et_offset_hours(now_et)
    mask = _scheduled_days_mask(triggers)

    if last_run is None:
        # NEVER RUN. Score the silence from the earliest point it COULD have run
        # (start boundary), not from epoch -- otherwise the 2026-08-07 task-rebuild
        # wave reads as 12 chronic outages when it is really 12 tasks waiting for
        # Monday. Within budget it is still YELLOW, never GREEN: "not yet proven
        # broken" and "proven working" must not render the same. It self-clears on
        # the first real fire.
        start = _earliest_start(triggers)
        nxt = _parse_ts(task.get("next_run"))
        nxt_txt = f"; next fire {nxt:%a %Y-%m-%d %H:%M}" if nxt else ""
        if start is None or cadence is None:
            out["status"] = fail
            out["detail"] = f"HAS NEVER RUN ({why}){nxt_txt}"
            return out
        start_et = start + timedelta(hours=offset)
        gap = (now_et - start_et).total_seconds() / 60.0
        slack = unscheduled_days_between(start_et, now_et, mask) * 1440.0
        budget = _budget_minutes(cadence, slack)
        if gap > budget:
            out["status"] = fail
            out["detail"] = (f"HAS NEVER RUN in the {_dur(gap)} since its trigger started "
                             f"{start_et:%Y-%m-%d %H:%M} -- {why}, budget {_dur(budget)}{nxt_txt}")
        else:
            out["status"] = "YELLOW"
            out["detail"] = (f"no fire yet -- trigger started {start_et:%Y-%m-%d %H:%M} "
                             f"({_dur(gap)} ago, still inside its {_dur(budget)} budget){nxt_txt}")
        return out

    if cadence is None:
        out["status"] = "GREEN"
        out["detail"] = f"last run {last_run:%Y-%m-%d %H:%M} ({why} -- silence is not scoreable)"
        return out

    # Compare in ET so the weekday mask and the timestamps share one frame.
    last_run_et = last_run + timedelta(hours=offset)
    gap_min = (now_et - last_run_et).total_seconds() / 60.0
    slack = unscheduled_days_between(last_run_et, now_et, mask) * 1440.0
    budget = _budget_minutes(cadence, slack)

    if gap_min > budget:
        out["status"] = fail
        out["detail"] = (f"HAS NOT FIRED in {_dur(gap_min)} -- {why}, budget {_dur(budget)}"
                         + (f" (incl. {_dur(slack)} of unscheduled days)" if slack else ""))
        return out

    if result not in (0, None, _RESULT_RUNNING, _RESULT_NEVER_RUN):
        out["status"] = fail
        out["detail"] = (f"last run {_dur(gap_min)} ago EXITED {result} "
                         f"(0x{result & 0xFFFFFFFF:08X})")
        return out

    out["detail"] = f"last run {_dur(gap_min)} ago ({why})"
    return out


def _dur(minutes: Optional[float]) -> str:
    if minutes is None:
        return "-"
    if minutes < 90:
        return f"{minutes:.0f}m"
    if minutes < 2880:
        return f"{minutes / 60:.1f}h"
    return f"{minutes / 1440:.1f}d"


# ---------------------------------------------------------------------------
# Axis C -- daemon liveness
# ---------------------------------------------------------------------------

def _pid_alive(pid: int) -> Optional[bool]:
    """True/False, or None when the check itself could not run (-> UNKNOWN, never
    a RED: 'I could not look' must not be reported as 'it is dead')."""
    try:
        raw = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
                             capture_output=True, text=True, check=False,
                             creationflags=_CREATE_NO_WINDOW).stdout
    except OSError:
        return None
    return f'"{pid}"' in raw


def _read_pid(path: Path) -> Optional[int]:
    """Accepts every pid-file shape this repo writes: a bare pid, 'pid|iso', or a
    JSON object with a 'pid' key."""
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    if raw.startswith("{"):
        try:
            return int(json.loads(raw).get("pid"))
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
    head = raw.split("|", 1)[0].strip()
    try:
        return int(head)
    except ValueError:
        return None


def evaluate_daemon(spec: dict, unit_crit: str, repo: Path = REPO) -> dict:
    name = spec.get("name", "?")
    fail = _BY_CRIT.get(unit_crit, "YELLOW")
    out = {"name": name, "status": "GREEN", "detail": ""}
    pid_file = repo / str(spec.get("pid_file", ""))
    if not pid_file.exists():
        out["status"] = fail
        out["detail"] = f"no pid file at {spec.get('pid_file')}"
        return out
    pid = _read_pid(pid_file)
    if pid is None:
        out["status"] = "UNKNOWN"
        out["detail"] = "pid file unreadable / unparseable"
        return out
    alive = _pid_alive(pid)
    if alive is None:
        out["status"] = "UNKNOWN"
        out["detail"] = f"pid {pid} -- liveness check unavailable"
    elif alive:
        out["detail"] = f"pid {pid} alive"
    else:
        out["status"] = fail
        out["detail"] = f"pid {pid} is DEAD (stale pid file)"
    return out


# ---------------------------------------------------------------------------
# Unit evaluation
# ---------------------------------------------------------------------------

def _manifest_index(path: Path = MANIFEST) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(e.get("path")): e for e in (raw.get("entries") or [])
            if isinstance(e, dict) and e.get("path")}


def evaluate_unit(unit: dict, tasks_by_name: dict, manifest: dict, now_et: datetime,
                  holidays: set, repo: Path = REPO) -> dict:
    """Fuse the three axes into one bubble. Worst axis wins; OFF never masks a RED
    and a RED anywhere is never averaged away."""
    from state_freshness_audit import evaluate_entry  # noqa: PLC0415

    crit = str(unit.get("criticality", "medium")).lower()
    expect_disabled = unit.get("expect_disabled") or {}
    out = {
        "id": unit.get("id"),
        "name": unit.get("name"),
        "group": unit.get("group", "INFRA"),
        "criticality": crit,
        "what": unit.get("what"),
        "breaks": unit.get("breaks"),
        "status": "GREEN",
        "tasks": [],
        "artifacts": [],
        "daemons": [],
        "problems": [],
    }

    for name in list(unit.get("tasks") or []) + list(expect_disabled):
        task = tasks_by_name.get(name)
        if task is None:
            out["tasks"].append({
                "name": name, "state": "MISSING", "status": _BY_CRIT.get(crit, "YELLOW"),
                "detail": "documented in the registry but NOT registered in Task Scheduler",
            })
            continue
        out["tasks"].append(evaluate_task(task, crit, now_et, expect_disabled))

    for art in unit.get("artifacts") or []:
        entry = manifest.get(art) if isinstance(art, str) else art
        if entry is None:
            out["artifacts"].append({
                "path": art, "status": "UNKNOWN",
                "detail": f"{art} referenced by this unit but absent from the freshness manifest",
            })
            continue
        res = evaluate_entry(entry, now_et, holidays, repo)
        out["artifacts"].append({
            "path": res["path"], "status": res["status"],
            "detail": "; ".join(res["reasons"]) or
                      (f"fresh (age {_dur(res['age_min'])}" +
                       (f", stamp {res['stamp']}" if res.get("stamp") else "") + ")"),
        })

    for spec in unit.get("daemons") or []:
        out["daemons"].append(evaluate_daemon(spec, crit, repo))

    # Worst-axis-wins, but OFF is EXCLUDED from the fold. A retired member
    # (Gamma_Heartbeat, superseded 2026-06-25) must not drag its healthy unit out
    # of GREEN -- the first pass did exactly that and rendered the live trading
    # engine as "off" while it was running fine.
    for axis in ("tasks", "artifacts", "daemons"):
        for row in out[axis]:
            if row["status"] == "OFF":
                continue
            if STATUS_RANK[row["status"]] > STATUS_RANK[out["status"]]:
                out["status"] = row["status"]
            if row["status"] in ("RED", "YELLOW", "UNKNOWN"):
                out["problems"].append(f"{row.get('name') or row.get('path')}: {row['detail']}")

    # A unit whose every member is off-by-design is OFF, not GREEN: "nothing is
    # running here" and "everything here is healthy" must never render the same.
    members = out["tasks"] + out["artifacts"] + out["daemons"]
    if members and all(m["status"] == "OFF" for m in members):
        out["status"] = "OFF"
    return out


# ---------------------------------------------------------------------------
# Memory -- transitions, down_since, last_green_at
# ---------------------------------------------------------------------------

def _load_prev_snapshot(path: Path = SNAPSHOT) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {u["id"]: u for u in (raw.get("units") or []) if isinstance(u, dict) and u.get("id")}


def _last_transition_from_events(unit_id: str, path: Path = EVENTS) -> Optional[dict]:
    """Fallback source for `since` when the snapshot is missing or malformed.

    L283: 'carry the field forward' is a convention, not a contract -- one bad
    write and every down_since silently resets to now, which would make an old
    outage look brand new. The ledger is the durable second source.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("id") == unit_id:
            return ev
    return None


def apply_memory(units: list[dict], now_et: datetime, prev: dict) -> list[dict]:
    """Attach since / last_green_at / down_minutes and return the transitions."""
    stamp = now_et.strftime("%Y-%m-%d %H:%M:%S")
    transitions: list[dict] = []
    for u in units:
        before = prev.get(u["id"]) or {}
        old_status = before.get("status")
        if old_status == u["status"]:
            since = before.get("since") or stamp
        else:
            since = stamp
            # A unit seen for the FIRST time only gets an event if it is already
            # unhealthy. Otherwise a fresh snapshot would spam 63 "birth" rows --
            # but a first-run RED that later heals must not produce a GREEN
            # transition out of a state the ledger never recorded.
            if old_status is not None or u["status"] != "GREEN":
                transitions.append({
                    "ts_et": stamp, "id": u["id"], "name": u["name"],
                    "from": old_status or "(first seen)", "to": u["status"],
                    "group": u["group"], "criticality": u["criticality"],
                    "detail": "; ".join(u["problems"][:3]) or "recovered",
                    "breaks": u.get("breaks"),
                })
        if old_status is None and not before:
            ev = _last_transition_from_events(u["id"])
            if ev and ev.get("to") == u["status"] and ev.get("ts_et"):
                since = ev["ts_et"]

        u["since"] = since
        u["last_green_at"] = stamp if u["status"] == "GREEN" else before.get("last_green_at")
        try:
            u["down_minutes"] = round(
                (now_et - datetime.strptime(since, "%Y-%m-%d %H:%M:%S")).total_seconds() / 60, 1
            ) if u["status"] in ("RED", "YELLOW") else 0.0
        except (ValueError, TypeError):
            u["down_minutes"] = 0.0
        u["down_for"] = _dur(u["down_minutes"]) if u["down_minutes"] else ""
    return transitions


def append_events(transitions: list[dict], path: Path = EVENTS,
                  cap: int = EVENTS_MAX_LINES) -> None:
    if not transitions:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            for ev in transitions:
                fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > cap:  # OP-22 retention: hitting the cap prunes, never grows forever
            path.write_text("\n".join(lines[-cap:]) + "\n", encoding="utf-8")
    except OSError:
        pass  # monitoring fails open: a ledger we cannot write must not kill the run


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------

def audit(registry_path: Path = REGISTRY, manifest_path: Path = MANIFEST,
          repo: Path = REPO, now_et: Optional[datetime] = None,
          write: bool = True) -> dict:
    """Run the whole audit. NEVER raises."""
    try:
        now = now_et or _et_now()
        stamp = now.strftime("%Y-%m-%d %H:%M:%S")
        try:
            reg = json.loads(registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            return {"verdict": "UNKNOWN", "checked_at_et": stamp, "units": [],
                    "reason": f"registry unreadable: {type(e).__name__}: {e}"}

        tasks, task_err = live_tasks()
        tasks_by_name = {t.get("name"): t for t in tasks if t.get("name")}
        manifest = _manifest_index(manifest_path)
        try:
            from state_freshness_audit import _holidays  # noqa: PLC0415
            holidays = _holidays()
        except Exception:  # noqa: BLE001
            holidays = set()

        declared = list(reg.get("units") or []) + list(reg.get("external_units") or [])
        units = [evaluate_unit(u, tasks_by_name, manifest, now, holidays, repo)
                 for u in declared]

        # --- anti-rot coverage diff (L292): scope is computed, never declared ---
        claimed = {n for u in declared
                   for n in list(u.get("tasks") or []) + list(u.get("expect_disabled") or {})}
        unclaimed = sorted(n for n in tasks_by_name if n not in claimed)
        cov = {
            "id": "unregistered", "name": "Uncovered tasks", "group": "INFRA",
            "criticality": "low",
            "what": "Live scheduled tasks that no registry unit claims.",
            "breaks": "An unclaimed task is UNMONITORED -- it can die without reddening any bubble.",
            "status": "YELLOW" if unclaimed else "GREEN",
            "tasks": [{"name": n, "state": tasks_by_name[n].get("state", "?"),
                       "status": "YELLOW", "detail": "claimed by no unit in unattended-registry.json"}
                      for n in unclaimed],
            "artifacts": [], "daemons": [],
            "problems": [f"{n}: unclaimed" for n in unclaimed],
        }
        if task_err:
            cov.update(status="UNKNOWN", problems=[task_err])
        units.append(cov)

        prev = _load_prev_snapshot(SNAPSHOT) if write else {}
        transitions = apply_memory(units, now, prev)

        verdict = "GREEN"
        for u in units:
            if STATUS_RANK[u["status"]] > STATUS_RANK[verdict]:
                verdict = u["status"]
        counts: dict[str, int] = {}
        for u in units:
            counts[u["status"]] = counts.get(u["status"], 0) + 1

        payload = {
            "checked_at_et": stamp,
            "verdict": verdict,
            "counts": counts,
            "n_units": len(units),
            "n_tasks_live": len(tasks_by_name),
            "n_tasks_unclaimed": len(unclaimed),
            "task_enumeration_error": task_err,
            "transitions_this_run": transitions,
            "units": units,
        }
        if write:
            append_events(transitions)
            try:
                SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
                SNAPSHOT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            except OSError:
                pass
        return payload
    except Exception as e:  # noqa: BLE001 -- monitoring MUST fail open
        return {"verdict": "UNKNOWN", "checked_at_et": None, "units": [],
                "reason": f"audit failed open: {type(e).__name__}: {e}"}


_MARK = {"GREEN": "OK  ", "YELLOW": "WARN", "RED": "RED ", "OFF": "off ", "UNKNOWN": "??  "}


def _render(rep: dict) -> str:
    lines = [f"UNATTENDED HEALTH -- {rep['verdict']}"]
    if rep.get("reason"):
        lines.append(f"  reason: {rep['reason']}")
    if rep.get("checked_at_et"):
        lines.append(f"  {rep['checked_at_et']} ET | {rep.get('n_units', 0)} units | "
                     f"{rep.get('n_tasks_live', 0)} live tasks | "
                     + " ".join(f"{k}={v}" for k, v in sorted((rep.get("counts") or {}).items())))
    group = None
    for u in sorted(rep.get("units", []), key=lambda x: (x["group"], x["id"])):
        if u["group"] != group:
            group, _ = u["group"], lines.append(f"\n  == {u['group']} ==")
        down = f"  [{u['down_for']}]" if u.get("down_for") else ""
        lines.append(f"  [{_MARK[u['status']]}] {u['name']:<26}{down}")
        if u["status"] in ("RED", "YELLOW", "UNKNOWN"):
            for p in u["problems"][:4]:
                lines.append(f"           - {p}")
            if u.get("breaks") and u["status"] == "RED":
                lines.append(f"           ! BREAKS: {u['breaks']}")
    if rep.get("transitions_this_run"):
        lines.append("\n  TRANSITIONS THIS RUN:")
        for t in rep["transitions_this_run"]:
            lines.append(f"    {t['name']}: {t['from']} -> {t['to']}  ({t['detail'][:90]})")
    return "\n".join(lines)


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="One traffic light per unattended unit.")
    ap.add_argument("--json", action="store_true", help="emit the machine payload")
    ap.add_argument("--no-write", action="store_true", help="evaluate without writing state")
    args = ap.parse_args(argv)
    rep = audit(write=not args.no_write)
    print(json.dumps(rep, indent=2) if args.json else _render(rep))
    return 1 if rep["verdict"] == "RED" else 0


if __name__ == "__main__":
    sys.exit(main())

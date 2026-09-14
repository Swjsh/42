#!/usr/bin/env python
"""company_audit.py -- deterministic, $0 "company audit" instrument (GOAL-GAMMA-STATION-
2026-09-13 item (22), J 00:0x ET: "after you build the world test it out by making sure all
agents work, have goals, are smart, and work autonomously as a real company would with
employees").

For each persona in automation/state/station/company-roster.json (the curated config --
objective/kpi/cadence/tasks/deliverable/goal_ref/quiz, one row per employee), computes four
independent, evidence-quoting PASS/WARN/FAIL checks:

  WORKS       -- its scheduled task(s) exist, are enabled, and ran within their cadence
                 window (Get-ScheduledTask / Get-ScheduledTaskInfo via
                 audit_scheduled_tasks.py's own `_registered_tasks()`, itself a FIXED-argv
                 PowerShell helper -- see setup/scripts/_list-gamma-tasks-json.ps1); AND its
                 deliverable file/glob advanced within that same window.
  HAS_GOAL    -- the roster's `objective` is asserted to be a LITERAL substring of the
                 persona's own agent .md file (this is the "quote, don't invent" instruction
                 enforced mechanically, not just promised), `kpi` is non-empty, and
                 `goal_ref` (if not "none") names a real file under automation/state/goals/.
  IS_SMART    -- a ground-truth check (one function per persona, dispatched by
                 `ground_truth.kind`) grades the persona's LATEST real output against a
                 deterministic source of truth (no LLM), combined with a one-question role
                 quiz run against the local brain (Ollama /api/chat -- same request/grading
                 shape as station_brain_quiz.py: a system prompt + one user prompt, graded by
                 regex/substring `checks`, never by a second LLM). The quiz is skipped
                 (SKIPPED, not FAIL) under --no-llm, when automation/state/station/mode.json
                 reads "gaming", or when nvidia-smi reports >50% GPU utilization -- this
                 script must never contend with J's game or the Station loop for the GPU.
  AUTONOMOUS  -- the most recent registered task fired with LastTaskResult==0 (the scheduler,
                 not a human, ran it) and the deliverable's mtime correlates with that
                 task's own LastRunTime (proving the deliverable came FROM that scheduled
                 fire, not a manual/interactive run at some other time).

Never raises on a missing file or a broken ground-truth read: every check is wrapped so a
missing path becomes `{"verdict": "FAIL", "evidence": "..."}", never an exception -- a
persona with nothing behind it still gets audited, it just fails loudly, which is the
entire point of an instrument built to name ghosts.

Writes automation/state/station/company-audit.json ({ts_et, personas:[...], summary:{...}})
and prints a table + a per-persona evidence dump. Stdlib only. Runtime capped at ~3 minutes
(RUNTIME_BUDGET_S) so a slow/hung quiz call can never make this instrument itself a bad
employee -- remaining quizzes are marked SKIPPED once the budget is spent, never blocked on.

Usage:
    python setup/scripts/company_audit.py                 # quiz on the local brain if allowed
    python setup/scripts/company_audit.py --no-llm         # evidence-only, no Ollama calls
    python setup/scripts/company_audit.py --model qwen3:14b
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

REPO = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from et_clock import et_now, et_offset_hours  # noqa: E402
import macro_calendar  # noqa: E402 -- load_holidays / is_trading_day (already-working producer)
import station_board  # noqa: E402 -- read_json_or_none / atomic_write_text (shared, stdlib-only)
import audit_scheduled_tasks as _ast  # noqa: E402 -- _registered_tasks(): the FIXED-argv PS helper

GPU_BUSY_PCT = 50.0
RUNTIME_BUDGET_S = 165  # cap ~3 min total; leaves margin for the enumeration + writes
OLLAMA = os.environ.get("OLLAMA_HOST_URL", "http://localhost:11434")
QUIZ_SYSTEM = ("You are being graded on Project Gamma role knowledge. Answer precisely and "
               "briefly. Follow the requested reply format exactly; no preamble.")
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Verdict combination order -- FAIL is worst, SKIPPED never drags a combination down.
_RANK = {"PASS": 0, "SKIPPED": 0, "WARN": 1, "FAIL": 2}


def _worse(a: str, b: str) -> str:
    return a if _RANK[a] >= _RANK[b] else b


# --------------------------------------------------------------------------- #
# Path helpers -- FUNCTIONS, not module-level constants, so a test can
# monkeypatch the module-level `REPO` and every path below re-derives from it
# (a plain `X_PATH = REPO / "..."` constant would freeze the OLD REPO value at
# import time and silently ignore a test's monkeypatch).
# --------------------------------------------------------------------------- #

def _roster_path() -> Path:
    return REPO / "automation" / "state" / "station" / "company-roster.json"


def _out_path() -> Path:
    return REPO / "automation" / "state" / "station" / "company-audit.json"


def _mode_path() -> Path:
    return REPO / "automation" / "state" / "station" / "mode.json"


def _station_config_path() -> Path:
    return REPO / "automation" / "state" / "station" / "config.json"


def _calendar_path() -> Path:
    return REPO / "automation" / "state" / "calendar.json"


# --------------------------------------------------------------------------- #
# Generic fail-open readers
# --------------------------------------------------------------------------- #

def _read_json(path: Path) -> Optional[dict]:
    return station_board.read_json_or_none(path)


def _read_jsonl_rows(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _mtime_utc(path: Path) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def _parse_iso_aware(ts: Any) -> Optional[datetime]:
    """Task Scheduler emits .NET 'o'-format timestamps, which can carry 7-digit
    (100ns-tick) fractional seconds -- one more digit than Python's fromisoformat
    accepts pre-3.11. Truncate rather than raise. A bare/naive result is treated as
    UTC (every caller here only ever hands this real ISO strings with offsets or
    already-UTC epoch-derived strings). The Task Scheduler '1999' sentinel for
    "never ran" (see audit_scheduled_tasks.py's own _last_run_age_hours) reads as
    None, same as a missing value."""
    if not ts or not isinstance(ts, str):
        return None
    s = ts.strip().replace("Z", "+00:00")
    if not s:
        return None
    m = re.match(r"^(.*\.\d{6})\d+([+-]\d{2}:\d{2})?$", s)
    if m:
        s = m.group(1) + (m.group(2) or "")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if dt.year < 2000:
        return None
    return dt


def _fmt_td(td: Optional[timedelta]) -> str:
    if td is None:
        return "?"
    total_min = td.total_seconds() / 60
    if total_min < 0:
        return "0m"
    if total_min < 60:
        return f"{total_min:.0f}m"
    hours = total_min / 60
    if hours < 48:
        return f"{hours:.1f}h"
    return f"{hours / 24:.1f}d"


def _parse_ts_et_to_utc(ts: Any) -> Optional[datetime]:
    """Parses this project's 'YYYY-MM-DD HH:MM:SS ET' stamp convention (station_loop.py,
    hypothesis_scorer.py, sector_rows.py all write rows this way) into a UTC-aware
    datetime. None on any parse failure -- never a guess. Same DST-safe trick
    _gt_manager_loop_ledger_cites_number already used inline (et_offset_hours at the
    naive instant, since a raw ET wall-clock string carries no explicit UTC offset of
    its own) -- pulled out here as a shared helper since the two 2026-09-14
    company-roster ground-truth checks below (chef_verdict_rows, coach_sectors_fresh)
    both need it too."""
    if not ts or not isinstance(ts, str):
        return None
    try:
        naive_et = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S ET")
    except ValueError:
        return None
    offset = et_offset_hours(naive_et.replace(tzinfo=timezone.utc))
    return (naive_et - timedelta(hours=offset)).replace(tzinfo=timezone.utc)


def _deliverable_mtime(persona: dict) -> Optional[datetime]:
    d = persona["deliverable"]
    base = REPO / d["path"]
    try:
        if d.get("glob"):
            if not base.is_dir():
                return None
            files = [f for f in base.glob(d["glob"]) if f.is_file()]
            if not files:
                return None
            best = max(f.stat().st_mtime for f in files)
        else:
            if not base.exists():
                return None
            best = base.stat().st_mtime
        return datetime.fromtimestamp(best, tz=timezone.utc)
    except OSError:
        return None


def _deliverable_label(persona: dict) -> str:
    d = persona["deliverable"]
    return d["path"] + (f"/{d['glob']}" if d.get("glob") else "")


# --------------------------------------------------------------------------- #
# Trading-calendar: last trading day (reuses macro_calendar's already-working
# holiday reader rather than a second copy of US market holidays).
# --------------------------------------------------------------------------- #

def _last_trading_day(now_utc: datetime) -> str:
    """The most recent trading day whose session should already be COMPLETE.

    Today only counts once its session is plausibly over (after the 16:00 ET close) --
    otherwise this always resolves to the prior session. Without this guard, a run at
    00:24 ET on a brand-new Monday would treat Monday itself as "the last trading day"
    (it IS a weekday) and grade every persona against an empty day nobody has worked yet
    -- exactly the false-FAIL this audit exists to avoid manufacturing."""
    holidays = macro_calendar.load_holidays(_calendar_path())
    now_et = et_now(now_utc=now_utc)
    d = now_et.date()
    if now_et.hour < 16:
        d -= timedelta(days=1)
    for _ in range(10):
        ds = d.strftime("%Y-%m-%d")
        if macro_calendar.is_trading_day(ds, holidays):
            return ds
        d -= timedelta(days=1)
    return now_et.strftime("%Y-%m-%d")  # defensive fallback, should not hit


# --------------------------------------------------------------------------- #
# Task Scheduler enumeration -- reuses audit_scheduled_tasks.py's own FIXED-argv
# PowerShell helper verbatim rather than a second Get-ScheduledTask caller.
# --------------------------------------------------------------------------- #

def _registered_tasks_map() -> tuple[dict[str, dict], Optional[str]]:
    try:
        tasks = _ast._registered_tasks()
        return {t["name"]: t for t in tasks}, None
    except Exception as exc:  # noqa: BLE001 -- enumeration failure must never crash the audit
        return {}, f"{type(exc).__name__}: {exc}"


_EVERY_RE = re.compile(r"every\s+(\d+)\s*(min|minute|minutes|h|hr|hour|hours)\b", re.I)
_RTH_RANGE_RE = re.compile(r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})\s*ET", re.I)

# Per-TASK cadence, distinct from the roster's per-PERSONA `cadence` prose. Coach owns
# four tasks under one blended sentence ("06:00 ET daily ... + every 30 min ... + every
# 5 min ... + 17:30 ET daily") -- parsing that one string can't tell a once-daily task
# from a 30-min repeater, and applying the tightest match (30 min) to all four made the
# once-daily ones false-FAIL every night between their fires. Keyed on the task name so
# it is correct regardless of which persona(s) reference it. A name absent here falls
# back to the owning persona's own `cadence` field (true for every single-task persona).
_TASK_CADENCE: dict[str, str] = {
    "Gamma_ScoutPremarket": "05:30 ET weekdays",
    "Gamma_HeartbeatCore": "every 1 min, 09:30-15:55 ET weekdays",
    "Gamma_AnalystEodReview": "16:45 ET weekdays",
    "Gamma_Conductor": "every 8 h",  # 3 fixed daily fires ~4.5-7h apart, 7 days/week
    "Gamma_CryptoDaily": "06:00 ET daily",
    "Gamma_CryptoRegression": "every 30 min, 24/7",
    "Gamma_CryptoGrinderKeepalive": "every 5 min, 24/7",
    "Gamma_SelfAudit": "17:30 ET daily",
    "Gamma_TreasurerWeekly": "Sun 16:00 ET",
    "Gamma_Station": "every 30 min, 24/7",
}


def _task_cadence_text(task_name: str, persona_cadence: str) -> str:
    return _TASK_CADENCE.get(task_name, persona_cadence)


def _in_weekend_gap(now_et: datetime) -> bool:
    """Sat/Sun any time, or Monday before 09:00 ET -- the same weekend-silence
    allowance audit_scheduled_tasks.py's own SILENT_TASK check grants weekday-only
    tasks (its own comment: 'Max legitimate gap = ~62h ... allow 70h')."""
    wd = now_et.weekday()
    return wd >= 5 or (wd == 0 and now_et.hour < 9)


def _cadence_window(cadence: str, now_et: datetime) -> timedelta:
    """A generous freshness window derived from a task's own cadence prose (see
    _task_cadence_text -- per TASK, not the blended per-persona sentence).

    Sub-daily ('every N min/h') -> 3x the interval, floored at 15 min. When that
    repeater also carries an explicit 'HH:MM-HH:MM ET' range (Pilot's HeartbeatCore:
    it only repeats 09:30-15:55 ET weekdays), the tight window applies ONLY while
    `now_et` is actually inside that range on a weekday -- outside it, being silent
    is expected, so this relaxes to the daily 30h/70h window below instead of
    reporting a market-closed engine as stale every single evening.

    Weekly ('Sun'/'Weekly') -> 8 days. Everything else (a single daily/weekday HH:MM
    ET fire) -> 30h, widened to 70h across the weekend gap -- audit_scheduled_tasks.py
    uses the identical 70h number for the identical reason."""
    cad = cadence or ""
    m = _EVERY_RE.search(cad)
    if m:
        n = int(m.group(1))
        mins = n * 60 if m.group(2).lower().startswith(("h", "hr", "hour")) else n
        tight = timedelta(minutes=max(mins * 3, 15))
        rng = _RTH_RANGE_RE.search(cad)
        if rng:
            sh, sm, eh, em = (int(x) for x in rng.groups())
            in_window = now_et.weekday() < 5 and (sh, sm) <= (now_et.hour, now_et.minute) < (eh, em)
            if not in_window:
                return timedelta(hours=70) if _in_weekend_gap(now_et) else timedelta(hours=30)
        return tight
    if re.search(r"\bSun\b|\bWeekly\b|\bweekly\b", cad):
        return timedelta(days=8)
    return timedelta(hours=70) if _in_weekend_gap(now_et) else timedelta(hours=30)


# --------------------------------------------------------------------------- #
# WORKS
# --------------------------------------------------------------------------- #

def check_works(persona: dict, tasks_by_name: dict, tasks_err: Optional[str], now: datetime) -> dict:
    lines: list[str] = []
    verdict = "PASS"
    if tasks_err:
        lines.append(f"Task Scheduler enumeration failed this run ({tasks_err}) -- task evidence unavailable")
        verdict = "WARN"

    names = persona.get("tasks") or []
    now_et = et_now(now_utc=now)
    last_window_seen: Optional[timedelta] = None  # for the deliverable check below
    if not names:
        lines.append("no tasks[] configured for this persona")
        verdict = "FAIL"

    for name in names:
        window = _cadence_window(_task_cadence_text(name, persona.get("cadence", "")), now_et)
        last_window_seen = window if last_window_seen is None else max(last_window_seen, window)
        t = tasks_by_name.get(name)
        if t is None:
            lines.append(f"{name}: NOT FOUND in Task Scheduler")
            verdict = _worse(verdict, "FAIL")
            continue
        state = t.get("state")
        last_run = _parse_iso_aware(t.get("last_run"))
        last_result = t.get("last_result")
        if state == "Disabled":
            lines.append(f"{name}: state=Disabled")
            verdict = _worse(verdict, "FAIL")
            continue
        if last_run is None:
            lines.append(f"{name}: state={state}, LastRunTime never set (never fired)")
            verdict = _worse(verdict, "WARN")
            continue
        age = now - last_run
        result_ok = last_result in (0, "0")
        lines.append(f"{name}: state={state} last_run={_fmt_td(age)} ago (cadence window {_fmt_td(window)}) "
                     f"LastTaskResult={last_result}")
        if age > window:
            verdict = _worse(verdict, "WARN")
        if not result_ok:
            verdict = _worse(verdict, "WARN")

    if not persona.get("dedicated_task", True):
        lines.append("NOTE: no dedicated Task Scheduler entry owned by this persona -- cadence cannot be "
                      "independently verified from the scheduler alone; capped at WARN even if the umbrella "
                      "task above is healthy")
        verdict = _worse(verdict, "WARN")

    deliverable_window = max(last_window_seen or timedelta(hours=2), timedelta(hours=2))
    mtime = _deliverable_mtime(persona)
    label = _deliverable_label(persona)
    if mtime is None:
        lines.append(f"deliverable MISSING: {label}")
        verdict = "FAIL"
    else:
        age = now - mtime
        lines.append(f"deliverable {label}: last advanced {_fmt_td(age)} ago (window {_fmt_td(deliverable_window)})")
        if age > deliverable_window:
            verdict = _worse(verdict, "WARN")

    return {"verdict": verdict, "evidence": " | ".join(lines)}


# --------------------------------------------------------------------------- #
# HAS_GOAL
# --------------------------------------------------------------------------- #

def check_has_goal(persona: dict) -> dict:
    role_path = REPO / persona["role_file"]
    if not role_path.exists():
        return {"verdict": "FAIL", "evidence": f"missing role_file {persona['role_file']}"}
    try:
        text = role_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"verdict": "FAIL", "evidence": f"could not read role_file: {exc}"}

    objective = persona.get("objective") or ""
    kpi = persona.get("kpi") or ""
    if not objective or objective not in text:
        return {"verdict": "FAIL",
                "evidence": f"objective is NOT a literal substring of {persona['role_file']} -- quoting "
                            f"requirement violated, or the source file has drifted since the roster was authored"}
    if not kpi.strip():
        return {"verdict": "FAIL", "evidence": "kpi field is empty"}

    goal_ref = persona.get("goal_ref") or "none"
    if goal_ref == "none":
        return {"verdict": "PASS",
                "evidence": f"objective verified verbatim in {persona['role_file']}; kpi present; "
                            f"goal_ref=none (standing production doctrine, not tied to a dated ladder item)"}
    goal_file = REPO / "automation" / "state" / "goals" / f"{goal_ref}.md"
    if not goal_file.exists():
        return {"verdict": "WARN",
                "evidence": f"objective verified verbatim; kpi present; goal_ref={goal_ref} but "
                            f"automation/state/goals/{goal_ref}.md does not exist"}
    return {"verdict": "PASS",
            "evidence": f"objective verified verbatim in {persona['role_file']}; kpi present; "
                        f"goal_ref={goal_ref} -> file exists"}


# --------------------------------------------------------------------------- #
# IS_SMART -- ground-truth checks (one function per `ground_truth.kind`)
# --------------------------------------------------------------------------- #

def _gt_scout_before_open(gt: dict, now: datetime, ltd: str) -> dict:
    out_path = REPO / gt["output_path"]
    if not out_path.exists():
        return {"verdict": "FAIL", "evidence": f"missing {gt['output_path']}"}
    data = _read_json(out_path)
    if data is None:
        return {"verdict": "FAIL", "evidence": f"unreadable/unparseable {gt['output_path']}"}
    mt = _mtime_utc(out_path)
    mt_et = et_now(now_utc=mt)
    for_date = data.get("for_session_date")
    date_match = for_date == ltd or mt_et.strftime("%Y-%m-%d") == ltd
    dh, dm, _ds = (int(x) for x in gt["deadline_et"].split(":"))
    before_deadline = (mt_et.hour, mt_et.minute) <= (dh, dm)

    log_rows = _read_jsonl_rows(REPO / gt["log_path"])
    log_row = next((r for r in reversed(log_rows) if r.get("for_session_date") == ltd), None)

    evidence = (f"scout_output.json for_session_date={for_date!r} mtime_et={mt_et.strftime('%Y-%m-%d %H:%M:%S')} "
                f"(last trading day={ltd}, deadline {gt['deadline_et']} ET) | scout-log row for {ltd}: "
                + (f"found (cost_usd={log_row.get('cost_usd')})" if log_row else "NOT FOUND"))

    if not date_match:
        return {"verdict": "FAIL", "evidence": evidence + " -- output is not dated to the last trading day"}
    if not before_deadline:
        return {"verdict": "WARN", "evidence": evidence + f" -- fired AFTER its {gt['deadline_et']} ET deadline"}
    return {"verdict": "PASS", "evidence": evidence}


def _gt_pilot_decisions_and_rule_breaks(gt: dict, now: datetime, ltd: str) -> dict:
    rows = _read_jsonl_rows(REPO / gt["decisions_path"])
    today_rows = [r for r in rows if r.get("date") == ltd]
    n = len(today_rows)
    min_rows = gt.get("min_rows", 10)

    rb_rows = _read_jsonl_rows(REPO / gt["rule_breaks_path"])
    breaks_today = [r for r in rb_rows if r.get("date") == ltd]

    audit_path = REPO / gt["rule_break_audit_path"]
    audit_age_days: Optional[float] = None
    if audit_path.exists() and _read_json(audit_path) is not None:
        mt = _mtime_utc(audit_path)
        if mt is not None:
            audit_age_days = (now - mt).total_seconds() / 86400

    evidence = (f"core-decisions.jsonl: {n} row(s) dated {ltd} (min {min_rows}) | "
                f"rule-breaks.jsonl: {len(breaks_today)} break row(s) dated {ltd} | "
                f"rule-break-audit.json: " + (f"last ran {audit_age_days:.1f}d ago" if audit_age_days is not None
                                               else "MISSING/unreadable"))

    if n == 0:
        return {"verdict": "FAIL", "evidence": evidence + " -- no decisions logged for the last trading day"}
    if breaks_today:
        return {"verdict": "FAIL", "evidence": evidence + " -- a real rule break is on record for this date"}

    verdict = "PASS" if n >= min_rows else "WARN"
    freshness_limit = gt.get("audit_freshness_days", 3)
    if audit_age_days is None or audit_age_days > freshness_limit:
        verdict = _worse(verdict, "WARN")
        evidence += (" -- 0 breaks on record is UNVERIFIED, not proven clean: rule_break_audit.py's own module "
                     "docstring warns an abandoned ledger silently reads as '0 breaks -> PASS'")
    return {"verdict": verdict, "evidence": evidence}


_TOTAL_ROW_RE = re.compile(r"^\|\s*\*\*TOTAL\*\*\s*\|(.+)$", re.MULTILINE)


def _gt_analyst_trade_count_reconcile(gt: dict, now: datetime, ltd: str) -> dict:
    eod_path = REPO / gt["eod_dir"] / f"{ltd}.md"
    if not eod_path.exists():
        return {"verdict": "FAIL", "evidence": f"missing {gt['eod_dir']}/{ltd}.md for the last trading day ({ltd})"}
    try:
        text = eod_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"verdict": "FAIL", "evidence": f"could not read {eod_path}: {exc}"}

    m = _TOTAL_ROW_RE.search(text)
    accepted: Optional[int] = None
    if m:
        cols = [c.strip() for c in m.group(1).split("|")]
        # QUANT header order: ticks | signals | ENTER | rule-blocked | attempted | accepted | filled | exited
        if len(cols) >= 6:
            try:
                accepted = int(cols[5].replace(",", ""))
            except ValueError:
                accepted = None

    csv_path = REPO / gt["trades_csv"]
    order_ids: set[str] = set()
    raw_rows = 0
    if csv_path.exists():
        try:
            with csv_path.open(encoding="utf-8-sig", newline="") as fh:
                for row in csv.DictReader(fh):
                    if row.get("date") != ltd:
                        continue
                    raw_rows += 1
                    oid = None
                    try:
                        blob = json.loads(row.get("archetype_match_json") or "{}")
                        oid = blob.get("entry_order_id")
                    except ValueError:
                        oid = None
                    order_ids.add(oid or f"__unkeyed_row_{raw_rows}")
        except OSError:
            pass

    log_rows = _read_jsonl_rows(REPO / gt["log_path"])
    log_row = next((r for r in reversed(log_rows) if r.get("for_date") == ltd), None)

    evidence = (f"analysis/eod/{ltd}.md QUANT TOTAL accepted={accepted} vs journal/trades.csv "
                f"{len(order_ids)} distinct entry_order_id ({raw_rows} raw rows) on {ltd} | "
                f"_analyst-log.jsonl row for {ltd}: "
                + (f"found (trades_audited={log_row.get('trades_audited')})" if log_row
                   else "NOT FOUND -- own fire-log gap"))

    if accepted is None:
        return {"verdict": "WARN", "evidence": evidence + " -- could not parse a QUANT TOTAL row from the digest"}

    if accepted == len(order_ids):
        verdict = "PASS"
    else:
        verdict = "WARN"
        evidence += (" -- MISMATCH (trades.csv can carry >1 row per fill on partial/TP1+runner legs, so a "
                     "mismatch alone is not proof of a broken pipeline; needs a human look)")
    if log_row is None:
        verdict = _worse(verdict, "WARN")
    return {"verdict": verdict, "evidence": evidence}


def _gt_chef_candidates_change(gt: dict, now: datetime, ltd: str) -> dict:
    within = timedelta(days=gt.get("within_days", 14))

    lb_path = REPO / gt["leaderboard_path"]
    lb_age = (now - _mtime_utc(lb_path)) if lb_path.exists() else None

    newest_candidate_age: Optional[timedelta] = None
    cand_dir = REPO / gt["candidates_dir"]
    if cand_dir.is_dir():
        for f in cand_dir.glob("*.md"):
            if f.name.startswith("_") or not f.is_file():
                continue
            age = now - _mtime_utc(f)
            if newest_candidate_age is None or age < newest_candidate_age:
                newest_candidate_age = age

    log_path = REPO / gt["log_path"]
    log_age = (now - _mtime_utc(log_path)) if log_path.exists() else None

    evidence = (f"_LEADERBOARD.md age={_fmt_td(lb_age)} | newest non-archived candidate file age="
                f"{_fmt_td(newest_candidate_age)} | _chef-log.jsonl (Chef's own fire log) age={_fmt_td(log_age)} "
                f"(window {within.days}d)")

    file_fresh = (lb_age is not None and lb_age <= within) or \
                 (newest_candidate_age is not None and newest_candidate_age <= within)
    log_fresh = log_age is not None and log_age <= within

    if not file_fresh:
        return {"verdict": "FAIL", "evidence": evidence + " -- no candidates/leaderboard change within the cadence window"}
    if not log_fresh:
        return {"verdict": "WARN",
                "evidence": evidence + " -- files changed recently but Chef's OWN fire log did not; the recent "
                            "change was likely written by a different process (e.g. a goal-adjudication pass), "
                            "not a genuine Chef research fire"}
    return {"verdict": "PASS", "evidence": evidence}


def _gt_coach_drift_within_cadence(gt: dict, now: datetime, ltd: str) -> dict:
    drift_path = REPO / gt["drift_path"]
    if not drift_path.exists():
        return {"verdict": "FAIL", "evidence": f"missing {gt['drift_path']}"}
    data = _read_json(drift_path) or {}
    age = now - _mtime_utc(drift_path)
    within = timedelta(hours=gt.get("within_hours", 30))

    log_path = REPO / gt["log_path"]
    log_age = (now - _mtime_utc(log_path)) if log_path.exists() else None
    log_within = timedelta(days=gt.get("log_within_days", 3))

    evidence = (f"drift_report.json overall_health={data.get('overall_health')!r} age={_fmt_td(age)} "
                f"(window {_fmt_td(within)}) | coach-log.jsonl (Coach's own snapshot log) age={_fmt_td(log_age)} "
                f"(window {log_within.days}d)")

    if age > within:
        return {"verdict": "FAIL", "evidence": evidence + " -- drift report stale beyond its cadence"}

    verdict = "PASS"
    if log_age is None or log_age > log_within:
        verdict = "WARN"
        evidence += (" -- the deterministic gym/drift pipeline is fresh, but Coach's OWN fire log has not been "
                     "appended in-window; the persona's own accountability trail is dead even though the "
                     "underlying automation is alive")
    return {"verdict": verdict, "evidence": evidence}


def _gt_treasurer_weekly_review(gt: dict, now: datetime, ltd: str) -> dict:
    within = timedelta(days=gt.get("within_days", 8))
    treasury_dir = REPO / gt["treasury_dir"]
    newest_age: Optional[timedelta] = None
    newest_name: Optional[str] = None
    if treasury_dir.is_dir():
        for f in treasury_dir.glob("20*.md"):
            if not f.is_file():
                continue
            age = now - _mtime_utc(f)
            if newest_age is None or age < newest_age:
                newest_age, newest_name = age, f.name

    log_exists = (REPO / gt["log_path"]).exists()
    draft_exists = (REPO / gt["draft_path"]).exists()

    evidence = (f"analysis/treasury/*.md newest={newest_name!r} age={_fmt_td(newest_age)} (window {within.days}d) "
                f"| _treasurer-log.jsonl exists={log_exists} | draft-params-changes.md exists={draft_exists}")

    if newest_age is None:
        return {"verdict": "FAIL", "evidence": evidence + " -- Treasurer has never produced a dated report in this repo"}
    if newest_age > within:
        return {"verdict": "FAIL", "evidence": evidence + " -- newest report is older than the review window"}
    if not log_exists:
        return {"verdict": "WARN", "evidence": evidence + " -- report exists but the fire log is missing"}
    return {"verdict": "PASS", "evidence": evidence}


_NUM_RE = re.compile(r"-?\$?\d[\d,]*\.?\d*%?")


def _extract_numeric_tokens(text: str, min_len: int = 3) -> set[str]:
    """Numeric substrings worth citation-matching. Excludes a bare 4-digit 2000-2099
    token (a calendar year, not a fact) -- nearly every file in this repo mentions the
    current year somewhere, so matching on it alone would make the brief-cites-a-real-
    number check trivially satisfiable without ever grounding an actual figure."""
    out: set[str] = set()
    for m in _NUM_RE.finditer(text or ""):
        tok = m.group(0).strip("$%").replace(",", "")
        digits = tok.replace(".", "").replace("-", "")
        if len(digits) < min_len:
            continue
        if re.fullmatch(r"20\d{2}", tok):
            continue
        out.add(tok)
    return out


def _gt_manager_loop_ledger_cites_number(gt: dict, now: datetime, ltd: str) -> dict:
    within = timedelta(hours=gt.get("within_hours", 24))
    ledger_rows = _read_jsonl_rows(REPO / gt["ledger_path"])
    ok_rows = []
    for r in ledger_rows:
        ts = r.get("ts_et")
        if not ts:
            continue
        try:
            naive_et = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S ET")
        except ValueError:
            continue
        # Same trick et_clock.ET_TZ.utcoffset() uses for a naive-ET wall clock: approximate
        # the instant as UTC first to look up the DST offset, then apply it for real.
        offset = et_offset_hours(naive_et.replace(tzinfo=timezone.utc))
        dt_utc = (naive_et - timedelta(hours=offset)).replace(tzinfo=timezone.utc)
        if now - dt_utc <= within and r.get("status") == "ok":
            ok_rows.append(r)

    brief_path = REPO / gt["brief_path"]
    brief_text = ""
    if brief_path.exists():
        try:
            brief_text = brief_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            brief_text = ""
    brief_nums = _extract_numeric_tokens(brief_text)

    truth_nums: set[str] = set()
    autopsy_dir = REPO / gt["autopsy_dir"]
    if autopsy_dir.is_dir():
        jsonl_files = sorted((f for f in autopsy_dir.glob("*.jsonl") if f.is_file()),
                              key=lambda f: f.stat().st_mtime, reverse=True)
        for f in jsonl_files[:1]:
            for row in _read_jsonl_rows(f):
                truth_nums |= _extract_numeric_tokens(json.dumps(row))
    trades_path = REPO / gt["trades_csv"]
    if trades_path.exists():
        try:
            with trades_path.open(encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.DictReader(fh))[-50:]
            for row in rows:
                truth_nums |= _extract_numeric_tokens(",".join(str(v) for v in row.values()))
        except OSError:
            pass

    cited = brief_nums & truth_nums
    evidence = (f"loop-ledger.jsonl: {len(ok_rows)} status=ok row(s) in the last {_fmt_td(within)} | "
                f"station-brief.md cites {len(brief_nums)} numeric token(s) (string-match heuristic, min 3 digits), "
                f"{len(cited)} also appear in the latest autopsy/trades.csv"
                + (f" (e.g. {sorted(cited)[:5]})" if cited else ""))

    if not ok_rows:
        return {"verdict": "FAIL", "evidence": evidence + " -- no successful loop fire in the window"}
    if not brief_text:
        return {"verdict": "WARN", "evidence": evidence + " -- station-brief.md missing/empty"}
    if not cited:
        return {"verdict": "WARN",
                "evidence": evidence + " -- brief cites no number traceable to real ledgers (may be generic prose)"}
    return {"verdict": "PASS", "evidence": evidence}


def _gt_chef_verdict_rows(gt: dict, now: datetime, ltd: str) -> dict:
    """2026-09-14 company-roster re-point: Chef owns the Station idea-loop's verdict
    pass (hypothesis_scorer via station_board.score_testing_cards, run every
    Gamma_Station fire). PASS requires BOTH: the newest station-verdicts.jsonl row is
    <= max_age_min old, AND every ideas-board.json card with status=='testing' has at
    least one verdict row (by card_id). WARN covers 'rows exist but stale' or 'a
    testing card has no row yet' -- either alone is a real gap, not a ghost. FAIL is
    reserved for the verdicts file itself being missing or carrying zero rows (nothing
    to grade Chef's freshness against at all)."""
    verdicts_path = REPO / gt["verdicts_path"]
    if not verdicts_path.exists():
        return {"verdict": "FAIL", "evidence": f"missing {gt['verdicts_path']}"}
    rows = _read_jsonl_rows(verdicts_path)
    if not rows:
        return {"verdict": "FAIL", "evidence": f"{gt['verdicts_path']} exists but carries 0 parseable rows"}

    newest_ts = max((r.get("ts_et") for r in rows if r.get("ts_et")), default=None)
    newest_dt = _parse_ts_et_to_utc(newest_ts) if newest_ts else None
    max_age = timedelta(minutes=gt.get("max_age_min", 60))
    age = (now - newest_dt) if newest_dt is not None else None
    fresh = age is not None and age <= max_age

    scored_ids = {r.get("card_id") for r in rows if r.get("card_id")}
    board = _read_json(REPO / gt["board_path"])
    board_readable = isinstance(board, list)
    testing_cards = [c for c in board if isinstance(c, dict) and c.get("status") == "testing"] if board_readable else []
    missing_coverage = [c.get("id") for c in testing_cards if c.get("id") not in scored_ids]

    evidence = (f"{gt['verdicts_path']}: {len(rows)} row(s), newest ts_et={newest_ts!r} age={_fmt_td(age)} "
               f"(window {_fmt_td(max_age)}) | {gt['board_path']}: " +
               (f"{len(testing_cards)} testing card(s), {len(missing_coverage)} without a verdict row"
                if board_readable else "UNREADABLE -- cannot verify testing-card coverage"))

    if not board_readable:
        return {"verdict": "WARN", "evidence": evidence}
    if age is None:
        return {"verdict": "WARN", "evidence": evidence + " -- newest row has no parseable ts_et"}
    if fresh and not missing_coverage:
        return {"verdict": "PASS", "evidence": evidence}
    reasons = []
    if not fresh:
        reasons.append("newest verdict row is stale")
    if missing_coverage:
        reasons.append(f"{len(missing_coverage)} testing card(s) have no verdict row")
    return {"verdict": "WARN", "evidence": evidence + " -- " + "; ".join(reasons)}


def _gt_coach_sectors_fresh(gt: dict, now: datetime, ltd: str) -> dict:
    """2026-09-14 company-roster re-point: Coach owns sectors.json (the per-lane health
    table + task-health snapshot, written every Gamma_Station fire regardless of
    yield/ok/error). PASS <= max_age_min old, WARN when stale or the ts_et is missing/
    unparseable, FAIL when the file itself is missing or unparseable. The evidence
    string always carries the file's own summary_line so a WARN/FAIL reads with the
    same headline a human would see in the ticker."""
    sectors_path = REPO / gt["path"]
    if not sectors_path.exists():
        return {"verdict": "FAIL", "evidence": f"missing {gt['path']}"}
    doc = _read_json(sectors_path)
    if not isinstance(doc, dict):
        return {"verdict": "FAIL", "evidence": f"{gt['path']} exists but is unreadable/unparseable"}

    summary_line = doc.get("summary_line", "?")
    ts_et = doc.get("ts_et")
    dt = _parse_ts_et_to_utc(ts_et) if ts_et else None
    max_age = timedelta(minutes=gt.get("max_age_min", 60))
    age = (now - dt) if dt is not None else None
    fresh = age is not None and age <= max_age

    evidence = f"sectors.json ts_et={ts_et!r} age={_fmt_td(age)} (window {_fmt_td(max_age)}) | {summary_line}"
    if dt is None:
        return {"verdict": "WARN", "evidence": evidence + " -- ts_et missing or unparseable"}
    if fresh:
        return {"verdict": "PASS", "evidence": evidence}
    return {"verdict": "WARN", "evidence": evidence + " -- stale"}


GROUND_TRUTH_CHECKS: dict[str, Callable[[dict, datetime, str], dict]] = {
    "scout_before_open": _gt_scout_before_open,
    "pilot_decisions_and_rule_breaks": _gt_pilot_decisions_and_rule_breaks,
    "analyst_trade_count_reconcile": _gt_analyst_trade_count_reconcile,
    "chef_candidates_change": _gt_chef_candidates_change,
    "coach_drift_within_cadence": _gt_coach_drift_within_cadence,
    "treasurer_weekly_review": _gt_treasurer_weekly_review,
    "manager_loop_ledger_cites_number": _gt_manager_loop_ledger_cites_number,
    "chef_verdict_rows": _gt_chef_verdict_rows,
    "coach_sectors_fresh": _gt_coach_sectors_fresh,
}


# --------------------------------------------------------------------------- #
# IS_SMART -- role quiz (local brain, Ollama /api/chat -- station_brain_quiz.py's
# own request/grading shape, kept as an independent copy so this script has no
# import-time dependency on that module's CLI/argparse surface).
# --------------------------------------------------------------------------- #

def _gpu_util_pct() -> Optional[float]:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, creationflags=_CREATE_NO_WINDOW,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        return float(out.stdout.strip().splitlines()[0].strip())
    except Exception:  # noqa: BLE001 -- a busy-detector that can't tell must fail OPEN (allow)
        return None


def _quiz_model() -> str:
    cfg = _read_json(_station_config_path()) or {}
    return cfg.get("model", "gamma-planner-fast")


def _llm_allowed(no_llm: bool) -> tuple[bool, str]:
    if no_llm:
        return False, "--no-llm"
    mode = (_read_json(_mode_path()) or {}).get("mode")
    if mode == "gaming":
        return False, "automation/state/station/mode.json mode=gaming"
    util = _gpu_util_pct()
    if util is not None and util > GPU_BUSY_PCT:
        return False, f"nvidia-smi GPU util {util:.0f}% > {GPU_BUSY_PCT:.0f}%"
    return True, f"mode={mode!r} gpu_util={util}"


def _chat(model: str, prompt: str, timeout_s: int = 40) -> dict:
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": QUIZ_SYSTEM}, {"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "options": {"num_ctx": 8192, "num_predict": 220, "temperature": 0.2},
    }
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=json.dumps(payload).encode("utf-8"),
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _quiz_check_passes(answer: str, checks: list[dict]) -> bool:
    for c in checks or []:
        val = c.get("value", "")
        if c.get("type") == "regex":
            if not re.search(val, answer, re.I):
                return False
        elif val.lower() not in answer.lower():
            return False
    return True


def run_quiz(persona: dict, allowed: bool, reason: str, model: str, deadline: float) -> dict:
    quiz = persona.get("quiz") or {}
    if not quiz:
        return {"asked": False, "verdict": "SKIPPED", "note": "no quiz configured"}
    if not allowed:
        return {"asked": False, "verdict": "SKIPPED", "note": f"LLM quiz skipped: {reason}"}
    if time.monotonic() > deadline:
        return {"asked": False, "verdict": "SKIPPED", "note": "runtime budget exhausted"}

    t0 = time.monotonic()
    try:
        r = _chat(model, quiz["prompt"])
    except Exception as exc:  # noqa: BLE001 -- a failed call is a wrong answer, not a crash
        return {"asked": True, "id": quiz.get("id"), "model": model, "verdict": "FAIL",
                "answer": f"ERROR {exc!r}"[:400], "wall_s": round(time.monotonic() - t0, 1)}

    answer = ((r.get("message") or {}).get("content") or "").strip()
    passed = _quiz_check_passes(answer, quiz.get("checks", []))
    return {
        "asked": True, "id": quiz.get("id"), "model": model,
        "verdict": "PASS" if passed else "FAIL",
        "answer": answer[:500],
        "wall_s": round(time.monotonic() - t0, 1),
    }


def check_is_smart(persona: dict, now: datetime, ltd: str, allowed: bool, reason: str,
                    model: str, deadline: float) -> dict:
    gt = persona.get("ground_truth") or {}
    kind = gt.get("kind")
    fn = GROUND_TRUTH_CHECKS.get(kind)
    if fn is None:
        gt_result = {"verdict": "FAIL", "evidence": f"no ground-truth check registered for kind={kind!r}"}
    else:
        try:
            gt_result = fn(gt, now, ltd)
        except Exception as exc:  # noqa: BLE001 -- a broken ground-truth read is a FAIL, not a crash
            gt_result = {"verdict": "FAIL", "evidence": f"ground-truth check raised {type(exc).__name__}: {exc}"}

    quiz_result = run_quiz(persona, allowed, reason, model, deadline)
    verdict = gt_result["verdict"]
    if quiz_result["verdict"] != "SKIPPED":
        verdict = _worse(verdict, quiz_result["verdict"])

    evidence = gt_result["evidence"]
    if quiz_result.get("asked"):
        evidence += f" | quiz[{quiz_result.get('id')}]={quiz_result['verdict']}: {quiz_result.get('answer', '')[:160]!r}"
    else:
        evidence += f" | quiz: {quiz_result.get('note')}"

    return {"verdict": verdict, "evidence": evidence, "ground_truth": gt_result, "quiz": quiz_result}


# --------------------------------------------------------------------------- #
# AUTONOMOUS
# --------------------------------------------------------------------------- #

def check_autonomous(persona: dict, tasks_by_name: dict, now: datetime) -> dict:
    names = persona.get("tasks") or []
    if not names:
        return {"verdict": "WARN",
                "evidence": "no dedicated task to correlate against -- cannot independently prove "
                            "scheduler-vs-human provenance"}

    lines = []
    best: Optional[tuple[datetime, str, Any]] = None
    for name in names:
        t = tasks_by_name.get(name)
        if t is None:
            lines.append(f"{name}: not registered")
            continue
        last_run = _parse_iso_aware(t.get("last_run"))
        last_result = t.get("last_result")
        lines.append(f"{name}: LastTaskResult={last_result} LastRunTime="
                      f"{last_run.isoformat() if last_run else 'never'}")
        if last_run is not None and (best is None or last_run > best[0]):
            best = (last_run, name, last_result)

    if best is None:
        return {"verdict": "FAIL", "evidence": " | ".join(lines) + " -- no task has ever fired (no LastRunTime on record)"}

    last_run, name, last_result = best
    result_ok = last_result in (0, "0")
    evidence = " | ".join(lines)

    mtime = _deliverable_mtime(persona)
    if mtime is None:
        verdict = "WARN" if result_ok else "FAIL"
        return {"verdict": verdict,
                "evidence": evidence + " -- deliverable missing, cannot correlate its timestamp to the scheduled run"}

    correlation_min = abs((mtime - last_run).total_seconds()) / 60
    evidence += f" | deliverable mtime is {correlation_min:.0f} min from {name}'s own LastRunTime"

    if not result_ok:
        return {"verdict": "WARN", "evidence": evidence + f" -- most recent scheduled run exited non-zero ({last_result})"}
    if correlation_min > 180:
        return {"verdict": "WARN",
                "evidence": evidence + " -- deliverable's timestamp is far from any registered run; may have "
                            "been produced by a manual/interactive invocation instead of the scheduler"}
    return {"verdict": "PASS",
            "evidence": evidence + " -- the scheduler (not a human) produced the most recent deliverable, and the run exited cleanly"}


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def run_persona_audit(persona: dict, tasks_by_name: dict, tasks_err: Optional[str], now: datetime,
                       ltd: str, allowed: bool, reason: str, model: str, deadline: float) -> dict:
    def _safe(fn: Callable[..., dict], *a: Any) -> dict:
        try:
            return fn(*a)
        except Exception as exc:  # noqa: BLE001 -- an axis check must NEVER crash the whole audit
            return {"verdict": "FAIL", "evidence": f"internal error: {type(exc).__name__}: {exc}"}

    works = _safe(check_works, persona, tasks_by_name, tasks_err, now)
    has_goal = _safe(check_has_goal, persona)
    is_smart = _safe(check_is_smart, persona, now, ltd, allowed, reason, model, deadline)
    autonomous = _safe(check_autonomous, persona, tasks_by_name, now)

    overall = "PASS"
    for c in (works, has_goal, is_smart, autonomous):
        overall = _worse(overall, c["verdict"])

    return {
        "name": persona["name"],
        "role_file": persona["role_file"],
        "objective": persona["objective"],
        "kpi": persona["kpi"],
        "cadence": persona["cadence"],
        "tasks": persona.get("tasks", []),
        "deliverable": _deliverable_label(persona),
        "goal_ref": persona.get("goal_ref", "none"),
        "verdict": overall,
        "checks": {
            "works": {"verdict": works["verdict"], "evidence": works["evidence"]},
            "has_goal": {"verdict": has_goal["verdict"], "evidence": has_goal["evidence"]},
            "is_smart": {"verdict": is_smart["verdict"], "evidence": is_smart["evidence"]},
            "autonomous": {"verdict": autonomous["verdict"], "evidence": autonomous["evidence"]},
        },
        "quiz": is_smart.get("quiz"),
    }


def _print_table(results: list[dict], summary: dict) -> None:
    header = f"{'PERSONA':<18}{'WORKS':<9}{'GOAL':<9}{'SMART':<9}{'AUTONOMOUS':<12}{'OVERALL':<8}"
    print()
    print(header)
    print("-" * len(header))
    for r in results:
        c = r["checks"]
        print(f"{r['name']:<18}{c['works']['verdict']:<9}{c['has_goal']['verdict']:<9}"
              f"{c['is_smart']['verdict']:<9}{c['autonomous']['verdict']:<12}{r['verdict']:<8}")
    print("-" * len(header))
    print(f"TOTAL: {summary['pass']} PASS / {summary['warn']} WARN / {summary['fail']} FAIL "
          f"(of {summary['total']} personas)")
    print()
    for r in results:
        print(f"--- {r['name']} :: {r['verdict']} ---")
        for axis in ("works", "has_goal", "is_smart", "autonomous"):
            print(f"  [{axis.upper():10s} {r['checks'][axis]['verdict']:5s}] {r['checks'][axis]['evidence']}")
        print()


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Deterministic per-employee audit: works / has_goal / "
                                              "is_smart / autonomous, evidence-quoted, $0.")
    ap.add_argument("--no-llm", action="store_true", help="skip the role quiz entirely (evidence-only run)")
    ap.add_argument("--model", default=None, help="override the quiz model (default: station config.json 'model')")
    args = ap.parse_args(argv)

    t_start = time.monotonic()
    deadline = t_start + RUNTIME_BUDGET_S

    roster = _read_json(_roster_path())
    if not roster or not isinstance(roster.get("personas"), list):
        print(f"[company_audit] FATAL: could not load/parse {_roster_path()}")
        return 1

    now = datetime.now(timezone.utc)
    ltd = _last_trading_day(now)
    tasks_by_name, tasks_err = _registered_tasks_map()
    model = args.model or _quiz_model()
    allowed, reason = _llm_allowed(args.no_llm)

    print(f"[company_audit] ts_et={et_now(now_utc=now).strftime('%Y-%m-%d %H:%M:%S')} last_trading_day={ltd} "
          f"llm={'ON model=' + model if allowed else 'OFF (' + reason + ')'} "
          f"scheduled_tasks_enumerated={len(tasks_by_name)}"
          + (f" (enumeration error: {tasks_err})" if tasks_err else ""))

    results = [run_persona_audit(p, tasks_by_name, tasks_err, now, ltd, allowed, reason, model, deadline)
               for p in roster["personas"]]

    summary = {"pass": 0, "warn": 0, "fail": 0, "total": len(results)}
    for r in results:
        summary[r["verdict"].lower()] += 1

    out = {
        "ts_et": et_now(now_utc=now).strftime("%Y-%m-%d %H:%M:%S ET"),
        "last_trading_day": ltd,
        "llm_used": allowed,
        "llm_model": model if allowed else None,
        "llm_skip_reason": None if allowed else reason,
        "scheduled_tasks_enumeration_error": tasks_err,
        "runtime_s": round(time.monotonic() - t_start, 1),
        "personas": results,
        "summary": summary,
    }
    station_board.atomic_write_text(_out_path(), json.dumps(out, indent=2, ensure_ascii=False))

    _print_table(results, summary)
    print(f"[company_audit] wrote {_out_path()} in {out['runtime_s']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())

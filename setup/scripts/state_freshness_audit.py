"""state_freshness_audit -- the SILENT-PRODUCER-DEATH detector.

WHY THIS EXISTS (2026-07-30 blind-engine incident, sibling audit)
----------------------------------------------------------------
On 2026-07-30 the engine ran 772 ticks with ``levels_active == []`` on 386 of 386
safe rows.  Root cause was NOT the engine: ``Gamma_LevelRefresh`` was DISABLED in
Windows Task Scheduler, so ``automation/state/key-levels.json`` had not been
rewritten since 2026-07-29 22:43 ET.  Every level inside it carried
``expires_at: 2026-07-29``; ``heartbeat_core._read_levels`` correctly dropped all
of them and returned ``([], [])``.  The engine then fell through to
trendline-only entries -- its statistically worst cohort (-$1,830 / WR .19 over
124 trades, ``analysis/deep-research/PNL-ATTRIBUTION-2026-07-28``) -- and at
11:31-11:46 ET produced 11 ENTER_BEAR verdicts at the LOW OF THE DAY.

The shape of that failure is the point:  **a data PRODUCER stopped writing while
every CONSUMER carried on happily.**  Nothing in the rig noticed, because the two
instruments that should have:

  * ``engine_health.check_level_feed`` -- age-only, and short-circuits to GREEN
    whenever ``market_open`` is False.  At 18:46 ET it reported GREEN on a file
    that was 1,199 minutes stale.
  * ``audit_scheduled_tasks.py`` -- its SILENT_TASK loop begins with
    ``if state == "Disabled": continue``, so a task that is documented ACTIVE in
    SCHEDULED-TASKS.md but DISABLED in Task Scheduler is silent BY CONSTRUCTION.

This module checks the CONSEQUENCE (a stale file on disk) rather than any single
cause.  It therefore also catches producers that still fire but write nothing,
write garbage, or write yesterday's payload -- failure modes no task-liveness
check can see.

TWO INDEPENDENT AXES
--------------------
1. ``max_age_min``   -- wall-clock age, evaluated ONLY while the producer's own
   ``window_et`` is open (a 5-min producer is legitimately quiet overnight).
2. ``date_field``    -- the file's own internal session stamp must not be OLDER
   than the expected trading session.  This axis is DELIBERATELY NOT suppressed
   outside market hours: a file stamped 2026-07-29 at 18:46 ET on Thursday
   2026-07-30 is stale, full stop.  Axis 2 is what ``check_level_feed`` lacked
   and is what makes tonight's outage visible tonight.

FAIL-OPEN CONTRACT (house rule: MONITORING fails open, ENTRY fails closed)
-------------------------------------------------------------------------
This is a MONITORING instrument.  It reports; it NEVER gates an entry and NEVER
raises into its caller.  An unreadable/missing/malformed manifest returns verdict
``UNKNOWN`` with an empty entry list -- never an exception, never a RED that
could be mistaken for evidence.  ``audit()`` catches ``Exception`` at its own
boundary for the same reason.

Pure Python, no network, no LLM -- $0/run.

USAGE
-----
    python setup/scripts/state_freshness_audit.py            # human table
    python setup/scripts/state_freshness_audit.py --json     # machine payload
    python setup/scripts/state_freshness_audit.py --manifest <path>

Exit code is 0 on GREEN/YELLOW/UNKNOWN and 1 on RED, so a shell caller can gate
on it -- but the engine_health wiring uses ``audit()`` directly and treats the
whole check as NON-CRITICAL (degrades the fused verdict to YELLOW at worst).

Manifest: automation/state/state-freshness-manifest.json
Guard:    backtest/tests/test_state_freshness_audit.py
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

DEFAULT_MANIFEST = REPO / "automation" / "state" / "state-freshness-manifest.json"

# Criticality -> the status a genuine staleness produces.  "info" entries are
# reported but never escalate; they exist so an unmonitored file is at least
# VISIBLE in the table instead of absent from it.
_STALE_STATUS = {"critical": "RED", "high": "RED", "medium": "YELLOW", "low": "YELLOW",
                 "info": "GREEN"}
_MISSING_STATUS = {"critical": "RED", "high": "RED", "medium": "YELLOW", "low": "YELLOW",
                   "info": "GREEN"}

_STATUS_RANK = {"GREEN": 0, "UNKNOWN": 1, "YELLOW": 2, "RED": 3}


# ---------------------------------------------------------------------------
# Clock  (ET only -- this box runs Mountain time; NEVER use naive local dates)
# ---------------------------------------------------------------------------

def _et_now() -> datetime:
    """Naive ET wall-clock via the canonical DST-aware et_clock.  Fail-open to
    naive local time is NOT acceptable here (it would silently shift dates by 2h
    on this Mountain-time rig), so an et_clock import failure propagates to
    audit()'s own try/except and surfaces as UNKNOWN."""
    from et_clock import et_now  # noqa: PLC0415 -- deferred so a broken import is catchable
    return et_now().replace(tzinfo=None)


def _et_minus_local_hours(now_et: datetime) -> int:
    """ET-minus-LOCAL offset AT `now_et`, for converting a naive LOCAL mtime into ET.

    Derived from the two zones' own UTC offsets on that date, so it is a property of the
    DATE and not of when this happens to run. Never differences `now_et` against the live
    wall clock -- see the call site for what that cost. Fail-open to 0 (treat local AS ET)
    rather than guess, matching this module's notify-only posture.
    """
    from datetime import timezone  # noqa: PLC0415
    try:
        from et_clock import et_offset_hours  # noqa: PLC0415
        et_from_utc = et_offset_hours(now_et.replace(tzinfo=timezone.utc))
        local = now_et.astimezone().utcoffset()
        if local is None:
            return 0
        return et_from_utc - round(local.total_seconds() / 3600.0)
    except Exception:  # noqa: BLE001 -- a monitor must not die on a clock import
        return 0


def _holidays() -> set:
    """US market holidays, reusing engine_health's cached loader.  Fail-open to an
    EMPTY set: on a holiday with no holiday data we would expect today's session
    and could emit a false RED -- acceptable for a notify-only monitor, and far
    safer than the inverse (suppressing a real outage)."""
    try:
        from engine_health import _load_holidays  # noqa: PLC0415
        return set(_load_holidays() or ())
    except Exception:  # noqa: BLE001 -- monitoring fails open
        return set()


def _is_session_day(d: datetime, holidays: set) -> bool:
    return d.weekday() < 5 and d.strftime("%Y-%m-%d") not in holidays


def expected_session_date(now_et: datetime, ready_after: str, holidays: set) -> str:
    """The session date a producer's output should be stamped with, right now.

    Before ``ready_after`` on a session day (or on any non-session day) the
    producer has not yet run for today, so the expected stamp is the PREVIOUS
    session's date.  From ``ready_after`` onward it is today's date.  This is what
    keeps the date axis quiet at 07:00 ET and loud at 18:46 ET.
    """
    try:
        hh, mm = (int(x) for x in str(ready_after).split(":", 1))
    except (TypeError, ValueError):
        hh, mm = 9, 35
    today_is_session = _is_session_day(now_et, holidays)
    if today_is_session and (now_et.hour, now_et.minute) >= (hh, mm):
        return now_et.strftime("%Y-%m-%d")
    d = now_et - timedelta(days=1)
    for _ in range(10):  # bounded walk-back; 10 covers any holiday cluster
        if _is_session_day(d, holidays):
            return d.strftime("%Y-%m-%d")
        d -= timedelta(days=1)
    return (now_et - timedelta(days=1)).strftime("%Y-%m-%d")


def _in_window(now_et: datetime, window: Optional[list], weekdays_only: bool,
               holidays: set) -> bool:
    """Is the producer's own duty window open right now?  ``window`` None => 24/7."""
    if weekdays_only and not _is_session_day(now_et, holidays):
        return False
    if not window:
        return True
    try:
        start, end = str(window[0]), str(window[1])
        cur = now_et.strftime("%H:%M")
        return start <= cur <= end
    except (TypeError, ValueError, IndexError):
        return True  # unparseable window -> assume open (fail toward MORE checking)


# ---------------------------------------------------------------------------
# Payload reading
# ---------------------------------------------------------------------------

def _dig(obj: Any, dotted: str) -> Any:
    cur = obj
    for part in str(dotted).split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _load_payload(path: Path) -> tuple[Optional[Any], Optional[str]]:
    """Return (payload, error).  For .jsonl the LAST non-blank line is the payload
    -- an append-only ledger's freshness lives in its newest row, not its file
    header."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        return None, f"unreadable ({type(e).__name__})"
    if path.suffix == ".jsonl":
        lines = [ln for ln in raw.splitlines() if ln.strip()]
        if not lines:
            return None, "empty ledger"
        raw = lines[-1]
    try:
        return json.loads(raw), None
    except json.JSONDecodeError as e:
        return None, f"malformed json (line {e.lineno})"


def _stamp_date(value: Any) -> Optional[str]:
    """First 10 chars of a date/timestamp value, if they look like YYYY-MM-DD."""
    if not isinstance(value, str) or len(value) < 10:
        return None
    head = value[:10]
    try:
        datetime.strptime(head, "%Y-%m-%d")
    except ValueError:
        return None
    return head


def _stamp_datetime(value: Any) -> Optional[datetime]:
    """Parse a naive ET datetime out of the common stamp shapes this repo writes
    ('YYYY-MM-DDTHH:MM:SS', 'YYYY-MM-DD HH:MM:SS', either with or without a
    trailing offset).  The offset is DISCARDED, not honoured: producers here write
    ET wall-clock with a literal '-04:00' suffix that is wrong half the year on
    this DST/Mountain rig (see engine_health.check_level_feed's note)."""
    if not isinstance(value, str) or len(value) < 19:
        return None
    head = value[:19].replace(" ", "T")
    try:
        return datetime.strptime(head, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Per-entry evaluation
# ---------------------------------------------------------------------------

def evaluate_entry(entry: dict, now_et: datetime, holidays: set,
                   repo: Path = REPO) -> dict:
    """Evaluate ONE manifest entry.  Pure apart from the single file read, so the
    guard test can drive it with a temp dir and a frozen clock."""
    rel = str(entry.get("path", "?"))
    crit = str(entry.get("criticality", "medium")).lower()
    if crit not in _STALE_STATUS:
        crit = "medium"
    out = {
        "path": rel,
        "criticality": crit,
        "writer": entry.get("writer"),
        "task": entry.get("task"),
        "status": "GREEN",
        "reasons": [],
        "age_min": None,
        "stamp": None,
        "expected_session": None,
        "window_open": None,
    }

    path = repo / rel
    if not path.exists():
        out["status"] = _MISSING_STATUS[crit]
        out["reasons"].append(f"{rel} MISSING")
        return out

    payload, err = _load_payload(path)
    if payload is None:
        # Unreadable/malformed is a MONITOR-side ambiguity, not proof of staleness:
        # report UNKNOWN rather than a RED that would be mistaken for evidence.
        out["status"] = "UNKNOWN"
        out["reasons"].append(f"{rel} {err}")
        return out

    ready_after = str(entry.get("date_expected_after_et") or "09:35")
    expected = expected_session_date(now_et, ready_after, holidays)
    out["expected_session"] = expected

    # --- axis 2: internal session stamp (NOT market-hours suppressed) ---------
    date_field = entry.get("date_field")
    stamp_dt = None
    if date_field:
        raw = _dig(payload, date_field)
        stamp = _stamp_date(raw)
        stamp_dt = _stamp_datetime(raw)
        out["stamp"] = stamp or (raw if isinstance(raw, str) else None)
        if stamp is None:
            out["status"] = "UNKNOWN"
            out["reasons"].append(f"{rel} date_field {date_field!r} unparseable ({raw!r})")
            return out
        if stamp < expected:
            out["status"] = _STALE_STATUS[crit]
            out["reasons"].append(
                f"{rel} STALE BY SESSION: {date_field}={stamp} but expected {expected} "
                f"(writer {entry.get('writer') or '?'} / task {entry.get('task') or '?'} "
                f"is not writing)")
            return out

    # --- axis 1: wall-clock age, only while the producer's window is open ------
    window_open = _in_window(now_et, entry.get("window_et"),
                             bool(entry.get("weekdays_only")), holidays)
    out["window_open"] = window_open
    max_age = entry.get("max_age_min")
    if max_age is None:
        return out

    # Prefer the file's own stamp over mtime: mtime moves on any touch/copy, the
    # stamp only moves when the producer actually recomputed.
    if stamp_dt is not None:
        age_min = (now_et - stamp_dt).total_seconds() / 60.0
    else:
        try:
            mtime_local = datetime.fromtimestamp(path.stat().st_mtime)
        except OSError as e:
            out["status"] = "UNKNOWN"
            out["reasons"].append(f"{rel} stat failed ({type(e).__name__})")
            return out
        # mtime is LOCAL (Mountain); convert to ET by the offset the two zones ACTUALLY
        # had on that date, not by differencing now_et against the wall clock.
        #
        # FIXED 2026-08-15 (identical defect to unattended_health.py:126, same session):
        # `round((now_et - datetime.now())/3600)` is only an offset when now_et IS now. Under
        # an injected clock it becomes the distance from today -- and because it ROUNDS to
        # whole hours, the sub-hour remainder leaks straight into age_min as a phantom age.
        # Measured with the guard's fixed PREMARKET clock: a -388.69h difference rounds to
        # -389, leaving 18.5 minutes of pure rounding artifact, which drifts minute-by-minute
        # and crossed the 20m budget for part of every hour -- a genuinely flaky guard whose
        # flakiness was a real impurity in the producer, not test noise.
        # Live behaviour is unchanged (now_et IS now there, so both forms give +2).
        offset_h = _et_minus_local_hours(now_et)
        age_min = (now_et - (mtime_local + timedelta(hours=offset_h))).total_seconds() / 60.0
    out["age_min"] = round(age_min, 1)

    if not window_open:
        return out  # legitimately quiet: producer's duty window is closed
    if age_min > float(max_age):
        out["status"] = _STALE_STATUS[crit]
        out["reasons"].append(
            f"{rel} STALE BY AGE: {age_min:.1f}m > {max_age}m budget while its window "
            f"{entry.get('window_et') or '24/7'} is OPEN "
            f"(writer {entry.get('writer') or '?'} / task {entry.get('task') or '?'})")
    return out


# ---------------------------------------------------------------------------
# Manifest + top-level audit
# ---------------------------------------------------------------------------

def load_manifest(path: Path) -> tuple[list, Optional[str]]:
    """(entries, error).  NEVER raises -- an unreadable manifest is the caller's
    UNKNOWN, not its crash."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as e:
        return [], f"manifest unreadable: {type(e).__name__}"
    except json.JSONDecodeError as e:
        return [], f"manifest malformed json: line {e.lineno}"
    entries = raw.get("entries") if isinstance(raw, dict) else raw
    if not isinstance(entries, list):
        return [], "manifest has no 'entries' list"
    return [e for e in entries if isinstance(e, dict) and e.get("path")], None


def audit(manifest_path: Path = DEFAULT_MANIFEST, repo: Path = REPO,
          now_et: Optional[datetime] = None) -> dict:
    """Run the whole audit.  NEVER raises: any unexpected failure degrades to
    verdict UNKNOWN so a broken monitor can never take the caller down with it."""
    try:
        entries, merr = load_manifest(manifest_path)
        if merr:
            return {"verdict": "UNKNOWN", "reason": merr, "checked_at_et": None,
                    "entries": [], "reds": [], "yellows": [], "unknowns": []}
        now = now_et or _et_now()
        holidays = _holidays()
        results = [evaluate_entry(e, now, holidays, repo) for e in entries]
        verdict = "GREEN"
        for r in results:
            if _STATUS_RANK[r["status"]] > _STATUS_RANK[verdict]:
                verdict = r["status"]
        return {
            "verdict": verdict,
            "reason": None,
            "checked_at_et": now.strftime("%Y-%m-%d %H:%M:%S"),
            "manifest": str(manifest_path),
            "n_entries": len(results),
            "entries": results,
            "reds": [m for r in results if r["status"] == "RED" for m in r["reasons"]],
            "yellows": [m for r in results if r["status"] == "YELLOW" for m in r["reasons"]],
            "unknowns": [m for r in results if r["status"] == "UNKNOWN" for m in r["reasons"]],
        }
    except Exception as e:  # noqa: BLE001 -- monitoring MUST fail open
        return {"verdict": "UNKNOWN", "reason": f"audit failed open: {type(e).__name__}: {e}",
                "checked_at_et": None, "entries": [], "reds": [], "yellows": [],
                "unknowns": []}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_MARK = {"GREEN": "OK  ", "YELLOW": "WARN", "RED": "RED ", "UNKNOWN": "??  "}


def _render(rep: dict) -> str:
    lines = [f"STATE FRESHNESS AUDIT -- {rep['verdict']}"]
    if rep.get("reason"):
        lines.append(f"  reason: {rep['reason']}")
    if rep.get("checked_at_et"):
        lines.append(f"  checked_at_et: {rep['checked_at_et']}  "
                     f"({rep.get('n_entries', 0)} entries)")
    lines.append("")
    width = max([len(e["path"]) for e in rep["entries"]] or [4])
    for e in rep["entries"]:
        age = f"{e['age_min']:.0f}m" if e["age_min"] is not None else "-"
        lines.append(f"  [{_MARK[e['status']]}] {e['path']:<{width}}  "
                     f"crit={e['criticality']:<8} stamp={e['stamp'] or '-':<12} age={age}")
    for bucket, label in (("reds", "RED"), ("yellows", "YELLOW"), ("unknowns", "UNKNOWN")):
        if rep.get(bucket):
            lines.append("")
            for m in rep[bucket]:
                lines.append(f"  {label}: {m}")
    return "\n".join(lines)


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="Audit freshness of live-path state files.")
    ap.add_argument("--json", action="store_true", help="emit the machine payload")
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    args = ap.parse_args(argv)
    rep = audit(Path(args.manifest))
    print(json.dumps(rep, indent=2) if args.json else _render(rep))
    return 1 if rep["verdict"] == "RED" else 0


if __name__ == "__main__":
    sys.exit(main())

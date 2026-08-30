"""whats_changed.py -- the WHAT-CHANGED digest for Project Gamma.

MISSING-INSTRUMENT FIX (J, 2026-08-29): "Every time you come back you ask me."
Per CLAUDE.md judgment-guards, a repeated question is a missing instrument,
not a query to keep answering by hand. This script IS the instrument: run it
bare and it reports everything that happened since a stored last-seen marker.

MARKER SEMANTICS (the one rule that matters): looking never clears the
digest. `automation/state/whats-changed-marker.json` only advances when the
caller passes `--seen` -- a bare run, an import, or the cockpit reading the
emitted JSON are all read-only with respect to the marker. This is the
opposite of "mark read on open" precisely because the repeated-question
pattern this fixes was J re-asking because there was NO durable record to
re-read -- a self-clearing digest reproduces the same hole with extra steps.

COVERS (each section: a count + the most significant few by name):
  - git commits since the marker (subject line only, never the full body)
  - action cards fired: manager-escalations.json (the escalation ledger) +
    conductor-outcomes.jsonl (the ask/fire ledger, which already records an
    outcome note per fire -- see conductor_outcome.py)
  - goals opened / advanced / closed (automation/state/goals/ +
    active-goal.json)
  - new automation/overnight/STATUS.md '## Known broken' entries
  - scheduled-task failures, from unattended-health.json, ONLY when that
    health surface was itself refreshed after the marker (a stale health
    file would otherwise misreport its last-known state as "new")
  - conductor_outcome.py's own rolling autonomy-metric.json, if readable

STATED ASSUMPTIONS (judgment-guards: assumptions get named, not buried):
  1. Goal state changes are inferred from filesystem mtime + whether a goal
     file's id matches the CURRENT active-goal.json id, not from replaying
     git history of active-goal.json's content. A goal file touched since
     the marker that still IS the active goal counts as "advanced"; one
     touched since the marker that is NOT the active goal counts as
     "closed" (superseded/archived). This is a heuristic, not a state
     machine -- documented here so nobody mistakes it for one.
  2. STATUS.md timestamps are mixed-tz by legacy convention (some carry an
     explicit UTC offset, some are bare "self-check" timestamps of
     undocumented tz). A naive timestamp is treated as UTC for comparison
     purposes. This makes entries within a few hours of the marker boundary
     only approximately ordered -- acceptable for a "what changed" overview,
     not a trading gate.
  3. `## Known broken` has no clean closing heading in practice (a `## Kitchen`
     heading is interleaved mid-section by another writer) -- verified
     2026-08-29 against the live file. So this reads from the heading to EOF
     rather than to the next `## ` line, which would silently drop entries
     appended after that interleaved heading.

RULE (OP-33 -- visibility is the product): an empty digest still SAYS
"nothing changed since <marker>" in the headline. A blank/omitted section is
indistinguishable from a broken one, so `build_digest()` always returns every
section key, count 0 where nothing fired.

Usage:
    python setup/scripts/whats_changed.py             # report only, marker untouched
    python setup/scripts/whats_changed.py --seen       # report, THEN advance the marker to now
    python setup/scripts/whats_changed.py --json       # machine-readable stdout instead of prose

Always writes automation/state/whats-changed.json (the cockpit's read source
-- see gamma_home.py's "What changed since I last looked?" answer card).
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
STATE = REPO / "automation" / "state"

MARKER_FILE = STATE / "whats-changed-marker.json"
OUT_FILE = STATE / "whats-changed.json"

GOALS_DIR = STATE / "goals"
ACTIVE_GOAL_FILE = STATE / "active-goal.json"
STATUS_MD = REPO / "automation" / "overnight" / "STATUS.md"
MANAGER_ESCALATIONS = STATE / "manager-escalations.json"
CONDUCTOR_OUTCOMES = STATE / "conductor-outcomes.jsonl"
UNATTENDED_HEALTH = STATE / "unattended-health.json"
AUTONOMY_METRIC = STATE / "autonomy-metric.json"

DEFAULT_FIRST_RUN_HOURS = 24.0   # first-run / corrupt-marker fallback window
TOP_N = 5                        # "the most significant few by name" per section

# OP-27 L41 / C8: never let a headless (pythonw) scheduled task flash a conhost window.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_BRACKET_TS = re.compile(r"^-\s*\[([^\]]+)\]\s*(.*)$")
_HEADER_TS = re.compile(r"^###\s*(BROKEN|DEGRADED):\s*self-check\s+(\S+)")
_KB_HEADING = re.compile(r"^## Known broken\s*$", re.MULTILINE)
_LOOSE_TS = re.compile(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(:\d{2})?")


# --------------------------------------------------------------------- utils

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _clip(s: Any, cap: int = 160) -> str:
    s = "" if s is None else str(s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) <= cap:
        return s
    return s[:cap].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _rel(p: Path) -> str:
    try:
        return p.relative_to(REPO).as_posix()
    except ValueError:
        return str(p)


def _parse_iso(s: Any) -> Optional[datetime]:
    """Best-effort ISO-ish timestamp parser. Naive timestamps are assumed UTC
    (see module docstring assumption #2)."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if not s:
        return None
    cand = s[:-1] + "+00:00" if s.endswith("Z") else s
    dt = None
    try:
        dt = datetime.fromisoformat(cand)
    except ValueError:
        m = _LOOSE_TS.search(s)
        if m:
            date_part, hm, sec = m.group(1), m.group(2), m.group(3) or ":00"
            try:
                dt = datetime.fromisoformat("%sT%s%s" % (date_part, hm, sec))
            except ValueError:
                dt = None
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            try:
                dt = datetime.fromisoformat(s + "T00:00:00")
            except ValueError:
                dt = None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _read_json(path: Path):
    """Return (data, ok)."""
    try:
        return json.loads(path.read_text(encoding="utf-8")), True
    except (OSError, ValueError):
        return None, False


def _read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    rows = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return rows


# -------------------------------------------------------------------- marker

def read_marker() -> dict:
    """Return {"since": datetime|None, "status": "ok"|"missing"|"corrupt", "raw": dict|None}.

    Never raises. A missing file and an unparseable/malformed one both fall
    back to the default lookback window, but are reported with a distinct
    status so the caller (and the tests) can tell "never tracked before"
    apart from "the marker file broke".
    """
    if not MARKER_FILE.exists():
        return {"since": None, "status": "missing", "raw": None}
    raw, ok = _read_json(MARKER_FILE)
    if not ok or not isinstance(raw, dict) or "since_iso" not in raw:
        return {"since": None, "status": "corrupt", "raw": raw if ok else None}
    since = _parse_iso(raw.get("since_iso"))
    if since is None:
        return {"since": None, "status": "corrupt", "raw": raw}
    return {"since": since, "status": "ok", "raw": raw}


def write_marker(now: datetime) -> None:
    """Advance the marker to `now`. ONLY called from main() when --seen is passed."""
    MARKER_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "since_iso": now.astimezone(timezone.utc).isoformat(),
        "written_at_local": datetime.now().isoformat(),
    }
    MARKER_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ------------------------------------------------------------------- sources

def git_commits_since(since: Optional[datetime]) -> list:
    """Subject-line-only commit list, newest first. Empty (not an error) if
    `since` is None, git is unavailable, or REPO isn't a git checkout."""
    if since is None:
        return []
    try:
        r = subprocess.run(
            ["git", "log", "--since=%s" % since.isoformat(), "--format=%H\x1f%cI\x1f%s"],
            cwd=str(REPO), capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace", creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if r.returncode != 0:
        return []
    commits = []
    for line in r.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f")
        if len(parts) != 3:
            continue
        sha, date_iso, subject = parts
        commits.append({"sha": sha[:10], "date": date_iso, "subject": _clip(subject, 200)})
    return commits


def escalations_since(since: Optional[datetime]) -> list:
    """manager-escalations.json: a dict keyed by hash, each row carrying
    count/reason/detail/last_ts. This IS the escalation ledger."""
    if since is None:
        return []
    data, ok = _read_json(MANAGER_ESCALATIONS)
    if not ok or not isinstance(data, dict):
        return []
    out = []
    for key, row in data.items():
        if not isinstance(row, dict):
            continue
        last = _parse_iso(row.get("last_ts"))
        if last is not None and last > since:
            out.append({
                "id": key,
                "reason": row.get("reason"),
                "count": row.get("count"),
                "detail": _clip(row.get("detail")),
                "last_ts": row.get("last_ts"),
            })
    out.sort(key=lambda r: (r.get("count") or 0), reverse=True)
    return out


def conductor_outcomes_since(since: Optional[datetime]) -> list:
    """conductor-outcomes.jsonl: one row per fire, already carrying an
    outcome note -- this IS "action cards fired ... with outcome"."""
    if since is None:
        return []
    out = []
    for row in _read_jsonl(CONDUCTOR_OUTCOMES):
        fired = _parse_iso(row.get("fired_at"))
        if fired is not None and fired > since:
            out.append({
                "task_id": row.get("task_id"),
                "fired_at": row.get("fired_at"),
                "outcome": _clip(row.get("note")),
                "items_drained": row.get("items_drained"),
                "regressions": row.get("regressions"),
            })
    out.sort(key=lambda r: r.get("fired_at") or "", reverse=True)
    return out


def _last_touched(path: Path) -> Optional[datetime]:
    """Last-modification time for `path`, preferring git's committer date
    (survives checkouts/clones/branch-switches, which stomp filesystem mtimes
    for every file at once and would otherwise make goals_since() falsely
    report every goal as freshly touched right after a checkout) and falling
    back to filesystem mtime only when git has no answer (untracked file, or
    REPO isn't a git checkout at all -- e.g. in a unit test fixture)."""
    try:
        r = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", str(path)],
            cwd=str(REPO), capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace", creationflags=NO_WINDOW,
        )
        if r.returncode == 0 and r.stdout.strip():
            dt = _parse_iso(r.stdout.strip())
            if dt is not None:
                return dt
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def goals_since(since: Optional[datetime]) -> dict:
    """opened / advanced / closed, per the heuristic in the module docstring
    (assumption #1)."""
    result = {"opened": [], "advanced": [], "closed": []}
    if since is None:
        return result

    active_id = None
    active, ok = _read_json(ACTIVE_GOAL_FILE)
    if ok and isinstance(active, dict):
        active_id = active.get("id")
        opened_at = _parse_iso(active.get("opened_at_et"))
        if opened_at is not None and opened_at > since:
            result["opened"].append({
                "id": active_id,
                "opened_at_et": active.get("opened_at_et"),
                "file": active.get("file"),
            })

    if not GOALS_DIR.exists():
        return result

    for f in sorted(GOALS_DIR.glob("GOAL-*.md")):
        touched = _last_touched(f)
        if touched is None or touched <= since:
            continue
        goal_id = f.stem
        if goal_id == active_id:
            if not any(o["id"] == active_id for o in result["opened"]):
                result["advanced"].append({"id": goal_id, "touched_at": touched.isoformat()})
        else:
            result["closed"].append({"id": goal_id, "touched_at": touched.isoformat()})
    return result


def status_known_broken_since(since: Optional[datetime]) -> list:
    """New `## Known broken` entries since `since`. Reads from the heading to
    EOF -- see module docstring assumption #3 for why."""
    if since is None or not STATUS_MD.exists():
        return []
    try:
        text = STATUS_MD.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    m = _KB_HEADING.search(text)
    if not m:
        return []
    section = text[m.end():]

    entries = []
    for line in section.splitlines():
        line = line.rstrip()
        if not line.strip():
            continue
        bm = _BRACKET_TS.match(line)
        if bm:
            ts_raw = bm.group(1)
            ts = _parse_iso(ts_raw)
            if ts is not None and ts > since:
                entries.append({"ts": ts_raw, "text": _clip(bm.group(2))})
            continue
        hm = _HEADER_TS.match(line)
        if hm:
            ts_raw = hm.group(2)
            ts = _parse_iso(ts_raw)
            if ts is not None and ts > since:
                entries.append({"ts": ts_raw, "text": _clip(line.lstrip("# ").strip())})
    entries.sort(key=lambda e: e["ts"], reverse=True)
    return entries


def scheduled_task_failures(since: Optional[datetime]) -> dict:
    """Non-GREEN/OFF units from unattended-health.json -- ONLY reported when
    that health surface's own `checked_at_et` is newer than the marker, so a
    stale snapshot never gets misreported as a fresh failure."""
    data, ok = _read_json(UNATTENDED_HEALTH)
    if not ok or not isinstance(data, dict):
        return {"checked_at": None, "fresh": False, "units": []}
    checked_raw = data.get("checked_at_et")
    checked = _parse_iso(checked_raw)
    fresh = bool(since is not None and checked is not None and checked > since)
    units = []
    if fresh:
        for u in data.get("units", []) or []:
            if not isinstance(u, dict):
                continue
            status = str(u.get("status", "")).upper()
            if status not in ("GREEN", "OFF"):
                units.append({"id": u.get("id"), "name": u.get("name"), "status": status})
    return {"checked_at": checked_raw, "fresh": fresh, "units": units}


def conductor_metric() -> Optional[dict]:
    """conductor_outcome.py's rolling scorecard, if readable. Not gated on
    `since` -- it's already a rolling window metric, not an event log."""
    data, ok = _read_json(AUTONOMY_METRIC)
    return data if ok and isinstance(data, dict) else None


# ------------------------------------------------------------------- digest

def build_digest(now: Optional[datetime] = None) -> dict:
    """Pure report: reads state, never writes the marker. Safe to call as
    often as wanted (e.g. every cockpit page build) without ever clearing
    the digest -- only main()'s --seen path calls write_marker()."""
    now = now or _now_utc()
    marker = read_marker()
    marker_status = marker["status"]
    since = marker["since"]
    used_default_window = since is None
    if since is None:
        since = now - timedelta(hours=DEFAULT_FIRST_RUN_HOURS)

    commits = git_commits_since(since)
    escalations = escalations_since(since)
    outcomes = conductor_outcomes_since(since)
    goals = goals_since(since)
    known_broken = status_known_broken_since(since)
    task_failures = scheduled_task_failures(since)
    metric = conductor_metric()

    goals_count = len(goals["opened"]) + len(goals["advanced"]) + len(goals["closed"])
    total_changes = (
        len(commits) + len(escalations) + len(outcomes) + goals_count
        + len(known_broken) + len(task_failures["units"])
    )

    since_label = (marker["raw"] or {}).get("since_iso") if marker["raw"] else None
    if not since_label:
        since_label = "no stored marker -- showing last %gh" % DEFAULT_FIRST_RUN_HOURS

    headline = ("nothing changed since %s" % since_label if total_changes == 0
                else "%d change(s) since %s" % (total_changes, since_label))

    return {
        "generated_at": now.isoformat(),
        "marker_status": marker_status,
        "since": since.isoformat(),
        "since_label": since_label,
        "used_default_window": used_default_window,
        "default_window_hours": DEFAULT_FIRST_RUN_HOURS,
        "total_changes": total_changes,
        "headline": headline,
        "sections": {
            "commits": {"count": len(commits), "top": commits[:TOP_N]},
            "action_cards": {
                "count": len(escalations) + len(outcomes),
                "escalations": escalations[:TOP_N],
                "fired_outcomes": outcomes[:TOP_N],
            },
            "goals": {
                "count": goals_count,
                "opened": goals["opened"][:TOP_N],
                "advanced": goals["advanced"][:TOP_N],
                "closed": goals["closed"][:TOP_N],
            },
            "known_broken": {"count": len(known_broken), "top": known_broken[:TOP_N]},
            "scheduled_task_failures": {
                "count": len(task_failures["units"]),
                "fresh": task_failures["fresh"],
                "checked_at": task_failures["checked_at"],
                "top": task_failures["units"][:TOP_N],
            },
            "conductor_metric": metric,
        },
        "sources": {
            "commits": "git log",
            "action_cards": [_rel(MANAGER_ESCALATIONS), _rel(CONDUCTOR_OUTCOMES)],
            "goals": [_rel(GOALS_DIR), _rel(ACTIVE_GOAL_FILE)],
            "known_broken": _rel(STATUS_MD),
            "scheduled_task_failures": _rel(UNATTENDED_HEALTH),
            "conductor_metric": _rel(AUTONOMY_METRIC),
        },
    }


def render_human(payload: dict) -> str:
    lines = [payload["headline"]]
    if payload["marker_status"] != "ok":
        why = ("no stored marker yet" if payload["marker_status"] == "missing"
               else "marker file unreadable/corrupt -- treating as first run")
        lines.append("  (marker: %s -- %s)" % (payload["marker_status"], why))
    if payload["total_changes"] == 0:
        return "\n".join(lines)

    s = payload["sections"]

    if s["commits"]["count"]:
        lines.append("")
        lines.append("COMMITS (%d):" % s["commits"]["count"])
        for c in s["commits"]["top"]:
            lines.append("  %s %s" % (c["sha"], c["subject"]))

    if s["action_cards"]["count"]:
        lines.append("")
        lines.append("ACTION CARDS / ESCALATIONS (%d):" % s["action_cards"]["count"])
        for e in s["action_cards"]["escalations"]:
            lines.append("  [escalation x%s] %s -- %s" % (e.get("count"), e.get("reason"), e.get("detail")))
        for o in s["action_cards"]["fired_outcomes"]:
            lines.append("  [fired] %s -- %s" % (o.get("task_id"), o.get("outcome")))

    if s["goals"]["count"]:
        lines.append("")
        lines.append("GOALS (%d):" % s["goals"]["count"])
        for g in s["goals"]["opened"]:
            lines.append("  opened: %s" % g["id"])
        for g in s["goals"]["advanced"]:
            lines.append("  advanced: %s" % g["id"])
        for g in s["goals"]["closed"]:
            lines.append("  closed: %s" % g["id"])

    if s["known_broken"]["count"]:
        lines.append("")
        lines.append("STATUS.md KNOWN BROKEN (%d new):" % s["known_broken"]["count"])
        for k in s["known_broken"]["top"]:
            lines.append("  [%s] %s" % (k["ts"], k["text"]))

    if s["scheduled_task_failures"]["count"]:
        lines.append("")
        lines.append("SCHEDULED-TASK FAILURES (%d, health checked %s):" % (
            s["scheduled_task_failures"]["count"], s["scheduled_task_failures"]["checked_at"]))
        for u in s["scheduled_task_failures"]["top"]:
            lines.append("  [%s] %s" % (u.get("status"), u.get("name")))

    if s["conductor_metric"]:
        lines.append("")
        lines.append("conductor autonomy-metric.json: %s" % _clip(json.dumps(s["conductor_metric"]), 200))

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="WHAT-CHANGED digest for Project Gamma.")
    ap.add_argument("--seen", action="store_true",
                     help="after reporting, advance the marker to now (looking alone never does this)")
    ap.add_argument("--json", action="store_true", help="print the digest JSON instead of the human summary")
    a = ap.parse_args()

    now = _now_utc()
    payload = build_digest(now=now)

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if a.json:
        print(json.dumps(payload, indent=2))
    else:
        print(render_human(payload))

    if a.seen:
        write_marker(now)
        print("\n(marker advanced to %s)" % now.isoformat(), file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""learning_ledger.py -- deterministic, $0 roll-up of "what Gamma learned" recently.

WHY THIS EXISTS (filed 2026-09-03): the research machinery runs constantly -- Kitchen
completing thousands of tasks, dozens of preregs filed, hundreds of shadow rows appended,
100+ commits/day -- but nothing rolled it up into a single "what did Gamma learn" surface,
so J experienced Gamma as idle even on a loud night. This module is the pure-stdlib
counting layer; the home-page builder (a separate Sonnet lane, gamma_home.py) imports it
lazily with a fallback to reading the JSON output directly -- so the PUBLIC CONTRACT below
must not change shape without updating that consumer too.

PUBLIC CONTRACT (do not rename/remove without checking gamma_home.py's import):
    DEFAULT_OUT = REPO / "automation" / "state" / "learning-ledger.json"
    build(now_et: datetime | None = None) -> dict
    write(d: dict, path: Path | None = None) -> Path
    load(path: Path | None = None) -> dict | None
    CLI: python setup/scripts/learning_ledger.py [--json] [--out PATH] [--now ISO]

Every source is read fail-soft (C7: silent success is failure -- so failures are LOUD in
the `errors` dict, never a silently-dropped 0). A missing/unparsable source records the
literal string "NO DATA" for that count key plus a reason in `errors`; a present-but-empty
source (file exists, zero rows/files match the window) legitimately counts as 0. build()
never raises -- a garbage repo state degrades every source to NO DATA, it does not crash
the caller.

No LLM calls anywhere in this module. $0.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

# ---------------------------------------------------------------- paths (C9: anchor to __file__)
REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from et_clock import et_now, et_offset_hours  # noqa: E402

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # no conhost flash (OP-27 L41)

DEFAULT_OUT = REPO / "automation" / "state" / "learning-ledger.json"

# Sources -- module-level so tests can monkeypatch each independently onto a tmp_path.
COOK_QUEUE_FILE = REPO / "automation" / "state" / "cook-queue.jsonl"
KITCHEN_STATUS_FILE = REPO / "automation" / "state" / "kitchen-status.json"
CANDIDATES_DIR = REPO / "strategy" / "candidates"
ANALYSIS_DIR = CANDIDATES_DIR / "_analysis"
RECOMMENDATIONS_DIR = REPO / "analysis" / "recommendations"
ENTRY_QUALITY_SHADOW_FILE = REPO / "analysis" / "entry-quality" / "shadow-tally.jsonl"
LADDER_SHADOW_FILE = REPO / "analysis" / "arm-ladder" / "ladder-rung-shadow-ledger.jsonl"
PROD_SHADOW_FILE = REPO / "analysis" / "prod-shadow" / "ledger.jsonl"
SHADOW_SUMMARY_FILE = REPO / "analysis" / "entry-quality" / "shadow-summary.json"
CONDUCTOR_OUTCOMES_FILE = REPO / "automation" / "state" / "conductor-outcomes.jsonl"
SELF_AUDIT_GAP_LOG = REPO / "analysis" / "self-audit" / "gap-log.jsonl"
STUDY_CURRICULUM_FILE = REPO / "markdown" / "doctrine" / "STUDY-CURRICULUM.md"
LESSONS_FILE = REPO / "markdown" / "doctrine" / "LESSONS-LEARNED.md"

TERMINAL_STATUSES = (
    "SHIP-CANDIDATE", "SHIP", "KILL", "EXTEND", "NULL", "PASS", "FAIL", "RETIRED", "CLOSED",
)
# Map a matched terminal keyword onto the allowed latest_verdicts `kind` literal.
_TERMINAL_TO_KIND = {
    "SHIP-CANDIDATE": "SHIP", "SHIP": "SHIP", "KILL": "KILL", "EXTEND": "EXTEND",
    "NULL": "NULL", "PASS": "PASS", "FAIL": "FAIL", "RETIRED": "KILL", "CLOSED": "KILL",
}
VERDICT_KINDS = {"KILL", "EXTEND", "SHIP", "NULL", "SHADOW", "KEEPER", "PASS", "FAIL", "NO-LIFT"}

_FILENAME_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_KEEPER_RE = re.compile(r"(\d+)\s*keepers?\b", re.IGNORECASE)
_STUDY_TABLE_ROW_RE = re.compile(
    r"^\|\s*(?P<name>[^|]+?)\s*\|\s*(?P<slug>[A-Za-z0-9_]+)\s*\|\s*(?P<sources>\d+)\s*\|"
    r"\s*(?P<last>never|\d{4}-\d{2}-\d{2})\s*\|\s*(?P<status>[^|]+?)\s*\|\s*$"
)
_LESSON_HEADING_RE = re.compile(r"^##\s+L(\d+)\s+--\s+(\d{4}-\d{2}-\d{2}):", re.MULTILINE)

# Verdict-kind inference for free-text notes (kitchen-status / conductor-outcomes).
# Order matters -- first match wins (NO-LIFT before the generic FAIL/NULL checks).
_VERDICT_TEXT_CHECKS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"no[-\s]?lift", re.IGNORECASE), "NO-LIFT"),
    (re.compile(r"\bkill(ed)?\b", re.IGNORECASE), "KILL"),
    (re.compile(r"\d+\s*keepers?\b", re.IGNORECASE), "KEEPER"),
    (re.compile(r"\bnull\b", re.IGNORECASE), "NULL"),
    (re.compile(r"\bship(ped)?\b", re.IGNORECASE), "SHIP"),
    (re.compile(r"\bextend(ed)?\b", re.IGNORECASE), "EXTEND"),
    (re.compile(r"\bshadow\b", re.IGNORECASE), "SHADOW"),
    (re.compile(r"\bpass(ed)?\b", re.IGNORECASE), "PASS"),
    (re.compile(r"\bfail(ed)?\b", re.IGNORECASE), "FAIL"),
]

# Free-text sources (kitchen task descriptions, conductor notes) are PROSE, not status
# fields: "orders failed to fill" is a task description, not a FAIL verdict, and "12677
# passed" is a test count, not a PASS. Only tokens that are unambiguous verdicts in this
# repo's vocabulary count there (2026-09-03 fix, caught on the first real run).
_STRONG_VERDICT_CHECKS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"no[-\s]?lift", re.IGNORECASE), "NO-LIFT"),
    (re.compile(r"\bNO[-\s]?SHIP\b"), "FAIL"),
    (re.compile(r"\bkill(ed)?\b", re.IGNORECASE), "KILL"),
    (re.compile(r"\d+\s*keepers?\b", re.IGNORECASE), "KEEPER"),
    (re.compile(r"\bnull\b", re.IGNORECASE), "NULL"),
    (re.compile(r"\bverdict\b.{0,20}\b(pass|passed|green)\b", re.IGNORECASE), "PASS"),
    (re.compile(r"\bverdict\b.{0,20}\b(fail|failed|red)\b", re.IGNORECASE), "FAIL"),
]

Window = tuple[date, date]


# ---------------------------------------------------------------- generic helpers

def _rel(p: Path) -> str:
    """Repo-relative posix path for a `sources`/`source` field. Falls back to str(p) for
    paths outside REPO (tests monkeypatch sources onto tmp_path)."""
    try:
        return p.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return p.as_posix()


def _to_et_date(ts: Any) -> Optional[date]:
    """Parse a date-only ('YYYY-MM-DD') or ISO-datetime string into an ET calendar date.
    Aware datetimes are converted via et_now(now_utc=...); naive datetimes are treated as
    already-ET (matches the ts_et naming convention used across this repo's ledgers).
    Returns None on anything unparsable -- callers treat that row as unmatched, not an error.
    """
    if not isinstance(ts, str) or not ts.strip():
        return None
    s = ts.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        try:
            return date.fromisoformat(s)
        except ValueError:
            return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = et_now(now_utc=dt.astimezone(timezone.utc))
    return dt.date()


def _read_jsonl(path: Path) -> Optional[list[dict]]:
    """One parsed JSON object per non-blank line. None if the file does not exist.
    Malformed individual lines are skipped (fail soft per-line, not per-file)."""
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    rows: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _in_window(d: Optional[date], window: Window) -> bool:
    if d is None:
        return False
    lo, hi = window
    return lo <= d <= hi


def _trunc(s: str, n: int = 200) -> str:
    s = s.strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _windows(now_et: datetime) -> tuple[Window, Window]:
    today = now_et.date()
    return (today, today), (today - timedelta(days=6), today)


# ---------------------------------------------------------------- per-source counters
# Each returns (count_today, count_7d) and RAISES on a missing/unreadable source -- the
# caller (build()) catches that and records "NO DATA" + the reason. A present source that
# simply has zero matches returns (0, 0), which is a valid measurement, not a failure.

def _count_kitchen_tasks_completed(w_today: Window, w_7d: Window) -> tuple[int, int]:
    rows = _read_jsonl(COOK_QUEUE_FILE)
    if rows is None:
        raise FileNotFoundError(f"{_rel(COOK_QUEUE_FILE)} not found")

    def getter(r: dict) -> Optional[date]:
        if r.get("event") != "complete":
            return None
        return _to_et_date(r.get("ts"))

    dates = [getter(r) for r in rows]
    return (
        sum(1 for d in dates if _in_window(d, w_today)),
        sum(1 for d in dates if _in_window(d, w_7d)),
    )


def _dated_analysis_files() -> list[tuple[date, Path]]:
    if not ANALYSIS_DIR.exists():
        raise FileNotFoundError(f"{_rel(ANALYSIS_DIR)} not found")
    out: list[tuple[date, Path]] = []
    for p in sorted(ANALYSIS_DIR.iterdir()):
        if not p.is_file():
            continue
        m = _FILENAME_DATE_RE.match(p.name)
        if not m:
            continue
        try:
            out.append((date.fromisoformat(m.group(1)), p))
        except ValueError:
            continue
    return out


def _count_kitchen_analyses(w_today: Window, w_7d: Window) -> tuple[int, int]:
    files = _dated_analysis_files()
    return (
        sum(1 for d, _p in files if _in_window(d, w_today)),
        sum(1 for d, _p in files if _in_window(d, w_7d)),
    )


def _count_kitchen_keepers(w_today: Window, w_7d: Window) -> tuple[int, int]:
    files = _dated_analysis_files()

    def is_keeper(p: Path) -> bool:
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        m = _KEEPER_RE.search(txt)
        return bool(m and int(m.group(1)) > 0)

    keeper_dates = [d for d, p in files if is_keeper(p)]
    return (
        sum(1 for d in keeper_dates if _in_window(d, w_today)),
        sum(1 for d in keeper_dates if _in_window(d, w_7d)),
    )


def _prereg_files() -> list[tuple[Path, list[date], Optional[dict]]]:
    """(path, [candidate 'filed' dates from filename+JSON fields], parsed JSON or None)."""
    if not RECOMMENDATIONS_DIR.exists():
        raise FileNotFoundError(f"{_rel(RECOMMENDATIONS_DIR)} not found")
    out: list[tuple[Path, list[date], Optional[dict]]] = []
    for p in sorted(RECOMMENDATIONS_DIR.glob("prereg-*.json")):
        dates: list[date] = []
        m = _FILENAME_DATE_RE.search(p.name)
        if m:
            try:
                dates.append(date.fromisoformat(m.group(1)))
            except ValueError:
                pass
        obj: Optional[dict] = None
        try:
            parsed = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            if isinstance(parsed, dict):
                obj = parsed
        except (OSError, json.JSONDecodeError):
            obj = None
        if obj is not None:
            for k in ("filed_at", "registered_at"):
                if k in obj:
                    d = _to_et_date(obj.get(k))
                    if d:
                        dates.append(d)
        out.append((p, dates, obj))
    return out


def _count_preregs_filed(w_today: Window, w_7d: Window) -> tuple[int, int]:
    files = _prereg_files()
    return (
        sum(1 for _p, dates, _o in files if any(_in_window(d, w_today) for d in dates)),
        sum(1 for _p, dates, _o in files if any(_in_window(d, w_7d) for d in dates)),
    )


def _prereg_adjudication_date(p: Path, obj: dict) -> Optional[date]:
    for k in ("status_at", "adjudicated_at", "updated_at", "frozen_at"):
        if k in obj:
            d = _to_et_date(obj.get(k))
            if d:
                return d
    try:
        mtime_utc = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None
    return et_now(now_utc=mtime_utc).date()


_NO_SHIP_RE = re.compile(r"\bNO[-\s]?SHIP\b")


def _prereg_terminal_kind(status: Any) -> Optional[str]:
    if not isinstance(status, str):
        return None
    status_up = status.upper()
    # Negation guard first: "NO-SHIP"/"NO SHIP" means it did NOT ship -- a bare substring
    # scan for "SHIP" would misread this as a SHIP verdict (seen in real data: prereg-
    # ladder-vwap-2026-08-11's "RUN_COMPLETE -- NO-SHIP -- all 4 gates FAIL").
    if _NO_SHIP_RE.search(status_up):
        return "FAIL"
    # A frozen/not-run prereg is a MEASUREMENT deferred to the 10-30 menu, not a verdict --
    # "FROZEN -- NOT RUN as a shipping decision" rendered as SHIP on the first live page
    # (2026-09-03). Skip it entirely; it will score once its status carries a real verdict.
    if "FROZEN" in status_up or "NOT RUN" in status_up or "NOT_RUN" in status_up:
        return None
    for kw in TERMINAL_STATUSES:
        if kw in status_up:
            return kw
    return None


def _count_preregs_adjudicated(w_today: Window, w_7d: Window) -> tuple[int, int]:
    files = _prereg_files()
    adj_dates: list[date] = []
    for p, _dates, obj in files:
        if obj is None:
            continue
        kw = _prereg_terminal_kind(obj.get("status"))
        if kw is None:
            continue
        d = _prereg_adjudication_date(p, obj)
        if d:
            adj_dates.append(d)
    return (
        sum(1 for d in adj_dates if _in_window(d, w_today)),
        sum(1 for d in adj_dates if _in_window(d, w_7d)),
    )


def _shadow_ledger_files() -> list[Path]:
    fixed = [ENTRY_QUALITY_SHADOW_FILE, LADDER_SHADOW_FILE, PROD_SHADOW_FILE]
    glob_files = (
        sorted(RECOMMENDATIONS_DIR.glob("*-shadow-ledger.jsonl"))
        if RECOMMENDATIONS_DIR.exists() else []
    )
    return fixed + list(glob_files)


def _row_date(r: dict) -> Optional[date]:
    if "date" in r:
        d = _to_et_date(r.get("date"))
        if d:
            return d
    for k in ("ts_et", "tallied_at", "entry_ts_et", "fired_at"):
        if k in r:
            d = _to_et_date(r.get(k))
            if d:
                return d
    return None


def _count_shadow_rows(w_today: Window, w_7d: Window) -> tuple[int, int]:
    all_paths = _shadow_ledger_files()
    present = [p for p in all_paths if p.exists()]
    if not present:
        raise FileNotFoundError("no shadow ledger sources found (checked "
                                 + ", ".join(_rel(p) for p in all_paths) + ")")
    n_today = 0
    n_7d = 0
    for p in present:
        rows = _read_jsonl(p) or []
        for r in rows:
            d = _row_date(r)
            if _in_window(d, w_today):
                n_today += 1
            if _in_window(d, w_7d):
                n_7d += 1
    return n_today, n_7d


def _count_candidates_filed(w_today: Window, w_7d: Window) -> tuple[int, int]:
    if not CANDIDATES_DIR.exists():
        raise FileNotFoundError(f"{_rel(CANDIDATES_DIR)} not found")
    files = [p for p in CANDIDATES_DIR.glob("*.md") if not p.name.startswith("_")]
    dates: list[date] = []
    for p in files:
        m = _FILENAME_DATE_RE.match(p.name)
        if m:
            try:
                dates.append(date.fromisoformat(m.group(1)))
            except ValueError:
                continue
    return (
        sum(1 for d in dates if _in_window(d, w_today)),
        sum(1 for d in dates if _in_window(d, w_7d)),
    )


def _conductor_rows() -> list[dict]:
    rows = _read_jsonl(CONDUCTOR_OUTCOMES_FILE)
    if rows is None:
        raise FileNotFoundError(f"{_rel(CONDUCTOR_OUTCOMES_FILE)} not found")
    return rows


def _count_conductor(w_today: Window, w_7d: Window) -> tuple[tuple[int, int], tuple[int, int]]:
    rows = _conductor_rows()
    dated = [(_to_et_date(r.get("fired_at")), r) for r in rows]
    fires_today = sum(1 for d, _r in dated if _in_window(d, w_today))
    fires_7d = sum(1 for d, _r in dated if _in_window(d, w_7d))
    drained_today = sum(
        int(r.get("items_drained") or 0) for d, r in dated if _in_window(d, w_today)
    )
    drained_7d = sum(
        int(r.get("items_drained") or 0) for d, r in dated if _in_window(d, w_7d)
    )
    return (fires_today, fires_7d), (drained_today, drained_7d)


def _count_self_audit_gaps(w_today: Window, w_7d: Window) -> tuple[int, int]:
    rows = _read_jsonl(SELF_AUDIT_GAP_LOG)
    if rows is None:
        raise FileNotFoundError(f"{_rel(SELF_AUDIT_GAP_LOG)} not found")
    dates = [_to_et_date(r.get("ts_et")) for r in rows]
    return (
        sum(1 for d in dates if _in_window(d, w_today)),
        sum(1 for d in dates if _in_window(d, w_7d)),
    )


def _study_topic_dates() -> list[date]:
    if not STUDY_CURRICULUM_FILE.exists():
        raise FileNotFoundError(f"{_rel(STUDY_CURRICULUM_FILE)} not found")
    text = STUDY_CURRICULUM_FILE.read_text(encoding="utf-8", errors="replace")
    dates: list[date] = []
    any_row = False
    for line in text.splitlines():
        m = _STUDY_TABLE_ROW_RE.match(line)
        if not m:
            continue
        any_row = True
        last = m.group("last")
        if last != "never":
            try:
                dates.append(date.fromisoformat(last))
            except ValueError:
                continue
    if not any_row:
        raise ValueError(f"no topic rows parsed from {_rel(STUDY_CURRICULUM_FILE)} "
                          "-- table format may have changed")
    return dates


def _count_study_topics(w_today: Window, w_7d: Window) -> tuple[int, int]:
    dates = _study_topic_dates()
    return (
        sum(1 for d in dates if _in_window(d, w_today)),
        sum(1 for d in dates if _in_window(d, w_7d)),
    )


def _lesson_dates() -> list[date]:
    if not LESSONS_FILE.exists():
        raise FileNotFoundError(f"{_rel(LESSONS_FILE)} not found")
    text = LESSONS_FILE.read_text(encoding="utf-8", errors="replace")
    matches = list(_LESSON_HEADING_RE.finditer(text))
    if not matches:
        raise ValueError(f"no 'L### -- YYYY-MM-DD:' headings parsed from {_rel(LESSONS_FILE)} "
                          "-- heading format may have changed")
    dates = []
    for m in matches:
        try:
            dates.append(date.fromisoformat(m.group(2)))
        except ValueError:
            continue
    return dates


def _count_lessons_added(w_today: Window, w_7d: Window) -> tuple[int, int]:
    dates = _lesson_dates()
    return (
        sum(1 for d in dates if _in_window(d, w_today)),
        sum(1 for d in dates if _in_window(d, w_7d)),
    )


def _git_since_str(window_start: date) -> str:
    """A --since timestamp git will read as ET midnight, regardless of the box's local TZ
    (which is Mountain, not ET -- L (TZ-SYSTEMIC) means an unqualified --since string would
    silently use the wrong offset)."""
    probe_utc = datetime(window_start.year, window_start.month, window_start.day, 12,
                          tzinfo=timezone.utc)
    offset_hours = et_offset_hours(probe_utc)  # -4 (EDT) or -5 (EST), DST-aware
    sign = "-" if offset_hours < 0 else "+"
    return (f"{window_start.year:04d}-{window_start.month:02d}-{window_start.day:02d}"
            f"T00:00:00{sign}{abs(offset_hours):02d}:00")


def _git_commit_count(window_start: date) -> int:
    since = _git_since_str(window_start)
    result = subprocess.run(
        ["git", "log", f"--since={since}", "--oneline"],
        cwd=str(REPO), capture_output=True, text=True, timeout=20,
        creationflags=_CREATE_NO_WINDOW,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git log failed (exit {result.returncode}): "
                            f"{result.stderr.strip()[:200]}")
    return sum(1 for line in result.stdout.splitlines() if line.strip())


def _count_commits(w_today: Window, w_7d: Window) -> tuple[int, int]:
    return _git_commit_count(w_today[0]), _git_commit_count(w_7d[0])


# ---------------------------------------------------------------- latest_verdicts

def _verdicts_from_preregs() -> list[dict]:
    out = []
    for p, _dates, obj in _prereg_files():
        if obj is None:
            continue
        status = obj.get("status")
        kw = _prereg_terminal_kind(status)
        if kw is None:
            continue
        d = _prereg_adjudication_date(p, obj)
        out.append({
            "at_et": d.isoformat() if d else "",
            "kind": _TERMINAL_TO_KIND.get(kw, "KILL"),
            "subject": str(obj.get("study") or p.stem),
            "text": _trunc(str(status)),
            "source": _rel(p),
        })
    return out


def _infer_verdict_kind(text: str) -> Optional[str]:
    for pat, kind in _VERDICT_TEXT_CHECKS:
        if pat.search(text):
            return kind
    return None


def _infer_strong_verdict_kind(text: str) -> Optional[str]:
    """Verdict kind for PROSE sources -- only unambiguous tokens (_STRONG_VERDICT_CHECKS)."""
    for pat, kind in _STRONG_VERDICT_CHECKS:
        if pat.search(text):
            return kind
    return None


def _to_et_iso(ts: Any) -> str:
    """ISO timestamp re-expressed in ET (minute precision). Aware/UTC input is converted;
    naive input is returned as-is (the repo's ts_et convention); junk is returned as-is."""
    if not isinstance(ts, str) or not ts.strip():
        return ""
    s = ts.strip()
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return s
    if dt.tzinfo is None:
        return s
    return et_now(now_utc=dt.astimezone(timezone.utc)).strftime("%Y-%m-%dT%H:%M ET")


def _verdicts_from_kitchen_status() -> list[dict]:
    if not KITCHEN_STATUS_FILE.exists():
        return []
    try:
        d = json.loads(KITCHEN_STATUS_FILE.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return []
    out = []
    for task in d.get("recent_completed_top_10", []) or []:
        if not isinstance(task, dict):
            continue
        text = str(task.get("task", ""))
        kind = _infer_strong_verdict_kind(text)
        if kind is None:
            continue
        # subject = what the task WAS (task_id is an opaque hash on this ledger)
        subject = re.sub(r"\s+", " ", text).strip()[:70]
        out.append({
            "at_et": _to_et_iso(task.get("completed_at", "")),
            "kind": kind,
            "subject": subject,
            "text": _trunc(text),
            "source": _rel(KITCHEN_STATUS_FILE),
        })
    return out


def _verdicts_from_conductor() -> list[dict]:
    try:
        rows = _conductor_rows()
    except FileNotFoundError:
        return []
    out = []
    for r in rows:
        note = str(r.get("note", ""))
        kind = _infer_strong_verdict_kind(note)
        if kind is None:
            continue
        out.append({
            "at_et": _to_et_iso(r.get("fired_at", "")),
            "kind": kind,
            "subject": str(r.get("task_id", "")),
            "text": _trunc(note),
            "source": _rel(CONDUCTOR_OUTCOMES_FILE),
        })
    return out


def _verdict_sort_key(entry: dict) -> datetime:
    ts = entry.get("at_et", "")
    if not ts:
        return datetime.min
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", ts):
            return datetime.fromisoformat(ts + "T00:00:00")
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError:
        return datetime.min


def _build_latest_verdicts() -> list[dict]:
    all_verdicts = (
        _verdicts_from_preregs() + _verdicts_from_kitchen_status() + _verdicts_from_conductor()
    )
    all_verdicts.sort(key=_verdict_sort_key, reverse=True)
    return all_verdicts[:12]


# ---------------------------------------------------------------- public contract

_COUNTERS: dict[str, Callable[[Window, Window], tuple[int, int]]] = {
    "kitchen_tasks_completed": _count_kitchen_tasks_completed,
    "kitchen_analyses": _count_kitchen_analyses,
    "kitchen_keepers": _count_kitchen_keepers,
    "preregs_filed": _count_preregs_filed,
    "preregs_adjudicated": _count_preregs_adjudicated,
    "shadow_rows": _count_shadow_rows,
    "candidates_filed": _count_candidates_filed,
    "self_audit_gaps": _count_self_audit_gaps,
    "study_topics": _count_study_topics,
    "lessons_added": _count_lessons_added,
    "commits": _count_commits,
}

_SOURCES: dict[str, str] = {
    "kitchen_tasks_completed": "automation/state/cook-queue.jsonl",
    "kitchen_analyses": "strategy/candidates/_analysis/*.md",
    "kitchen_keepers": "strategy/candidates/_analysis/*.md",
    "preregs_filed": "analysis/recommendations/prereg-*.json",
    "preregs_adjudicated": "analysis/recommendations/prereg-*.json",
    "shadow_rows": ("analysis/entry-quality/shadow-tally.jsonl, "
                     "analysis/arm-ladder/ladder-rung-shadow-ledger.jsonl, "
                     "analysis/prod-shadow/ledger.jsonl, "
                     "analysis/recommendations/*-shadow-ledger.jsonl"),
    "candidates_filed": "strategy/candidates/*.md",
    "conductor_fires": "automation/state/conductor-outcomes.jsonl",
    "conductor_drained": "automation/state/conductor-outcomes.jsonl",
    "commits": "git log --oneline (this repo, current branch, HEAD)",
    "self_audit_gaps": "analysis/self-audit/gap-log.jsonl",
    "study_topics": "markdown/doctrine/STUDY-CURRICULUM.md",
    "lessons_added": "markdown/doctrine/LESSONS-LEARNED.md",
}

_METHODS: dict[str, str] = {
    "kitchen_tasks_completed": "count of {event:complete} lines in cook-queue.jsonl whose ts "
                                "(UTC ISO) converts to an ET date inside the window",
    "kitchen_analyses": "count of _analysis/*.md files whose filename YYYY-MM-DD prefix falls "
                         "in the window",
    "kitchen_keepers": "of those dated files, count whose text matches a positive count before "
                        "'keeper(s)' (regex (\\d+)\\s*keepers?, first match's number > 0)",
    "preregs_filed": "count of prereg-*.json whose filename date OR filed_at/registered_at "
                      "field falls in the window (either qualifies)",
    "preregs_adjudicated": "of those files, count whose status field contains a terminal "
                            "keyword (KILL/EXTEND/SHIP[-CANDIDATE]/NULL/PASS/FAIL/RETIRED/"
                            "CLOSED), dated by status_at/adjudicated_at/updated_at/frozen_at "
                            "else file mtime",
    "shadow_rows": "sum of jsonl rows across the 3 fixed shadow ledgers + "
                   "recommendations/*-shadow-ledger.jsonl whose date (or ts_et/tallied_at/"
                   "entry_ts_et/fired_at) falls in the window; a missing individual file "
                   "contributes 0, only ALL-missing raises NO DATA",
    "candidates_filed": "count of top-level strategy/candidates/*.md (non-'_'-prefixed) whose "
                         "filename YYYY-MM-DD prefix falls in the window",
    "conductor_fires": "count of conductor-outcomes.jsonl rows whose fired_at falls in the "
                        "window",
    "conductor_drained": "sum of items_drained across those same in-window rows",
    "commits": "len(git log --since=<window start, midnight ET, DST-correct offset> --oneline) "
               "on the current branch; git failure -> NO DATA",
    "self_audit_gaps": "count of gap-log.jsonl rows whose ts_et falls in the window",
    "study_topics": "count of STUDY-CURRICULUM.md table rows whose 'Last Studied (ET)' date "
                     "falls in the window (excludes 'never')",
    "lessons_added": "count of '## L### -- YYYY-MM-DD:' headings in LESSONS-LEARNED.md whose "
                      "date falls in the window",
    "latest_verdicts": "merges terminal prereg statuses, kitchen-status.json "
                        "recent_completed_top_10 keyword hits, and conductor-outcomes.jsonl "
                        "note keyword hits, newest-first by at_et, capped at 12. "
                        "shadow-summary.json was inspected but carries only F-gate progress "
                        "booleans (no explicit status/verdict field) so it is NOT used as a "
                        "verdict source here.",
}


def build(now_et: Optional[datetime] = None) -> dict:
    """Build the learning ledger dict. Never raises -- every source failure degrades that
    source to 'NO DATA' + an `errors` entry, it never aborts the whole build."""
    if now_et is None:
        now_et = et_now()
    w_today, w_7d = _windows(now_et)

    counts_today: dict[str, Any] = {}
    counts_7d: dict[str, Any] = {}
    errors: dict[str, str] = {}

    for key, fn in _COUNTERS.items():
        try:
            today_val, week_val = fn(w_today, w_7d)
        except Exception as e:  # noqa: BLE001 -- fail-soft-per-source is the whole point
            errors[key] = f"{type(e).__name__}: {e}"
            counts_today[key] = "NO DATA"
            counts_7d[key] = "NO DATA"
        else:
            counts_today[key] = today_val
            counts_7d[key] = week_val

    # conductor_fires / conductor_drained share one source read.
    try:
        (fires_today, fires_7d), (drained_today, drained_7d) = _count_conductor(w_today, w_7d)
    except Exception as e:  # noqa: BLE001
        errors["conductor_fires"] = f"{type(e).__name__}: {e}"
        errors["conductor_drained"] = f"{type(e).__name__}: {e}"
        counts_today["conductor_fires"] = "NO DATA"
        counts_7d["conductor_fires"] = "NO DATA"
        counts_today["conductor_drained"] = "NO DATA"
        counts_7d["conductor_drained"] = "NO DATA"
    else:
        counts_today["conductor_fires"] = fires_today
        counts_7d["conductor_fires"] = fires_7d
        counts_today["conductor_drained"] = drained_today
        counts_7d["conductor_drained"] = drained_7d

    try:
        latest_verdicts = _build_latest_verdicts()
    except Exception as e:  # noqa: BLE001 -- verdicts are best-effort, never fatal
        errors["latest_verdicts"] = f"{type(e).__name__}: {e}"
        latest_verdicts = []

    return {
        "generated_at_et": now_et.isoformat(),
        "today_et": now_et.strftime("%Y-%m-%d"),
        "windows": {"today": counts_today, "7d": counts_7d},
        "sources": dict(_SOURCES),
        "methods": dict(_METHODS),
        "latest_verdicts": latest_verdicts,
        "errors": errors,
    }


def write(d: dict, path: Optional[Path] = None) -> Path:
    path = path or DEFAULT_OUT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    return path


def load(path: Optional[Path] = None) -> Optional[dict]:
    path = path or DEFAULT_OUT
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------- CLI

def _parse_now(now_arg: Optional[str]) -> Optional[datetime]:
    if not now_arg:
        return None
    dt = datetime.fromisoformat(now_arg)
    if dt.tzinfo is not None:
        dt = et_now(now_utc=dt.astimezone(timezone.utc))
    return dt


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print the full JSON to stdout")
    parser.add_argument("--out", type=Path, default=None, help="override DEFAULT_OUT")
    parser.add_argument("--now", type=str, default=None,
                         help="ISO datetime override (naive=ET, aware=converted to ET)")
    args = parser.parse_args(argv)

    now_et = _parse_now(args.now)
    d = build(now_et=now_et)
    out_path = write(d, args.out)

    if args.json:
        print(json.dumps(d, indent=1, ensure_ascii=False))
    else:
        wt = d["windows"]["today"]
        w7 = d["windows"]["7d"]
        n_err = len(d.get("errors", {}))
        print(
            f"learning-ledger {d['today_et']} ET | "
            f"today: tasks={wt.get('kitchen_tasks_completed')} "
            f"candidates={wt.get('candidates_filed')} commits={wt.get('commits')} | "
            f"7d: tasks={w7.get('kitchen_tasks_completed')} "
            f"preregs_filed={w7.get('preregs_filed')} "
            f"preregs_adjudicated={w7.get('preregs_adjudicated')} "
            f"shadow_rows={w7.get('shadow_rows')} commits={w7.get('commits')} | "
            f"verdicts={len(d.get('latest_verdicts', []))} errors={n_err} | "
            f"wrote {out_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

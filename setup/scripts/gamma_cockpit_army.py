"""gamma_cockpit_army.py - the Army view's data layer: who's alive, who's

working, who talked to whom.

WHY (2026-08-29, spec: scratchpad/SPEC.md secs 1-3): J wants to SEE the
orchestrator and the army -- boxes, with a coloured pulse travelling box-to-box
as messages are sent. This module builds payload["army"] purely from what is
already on disk:
  * session roster  ~/.claude/sessions/<pid>.json         (liveness = PID check)
  * worker roster    ~/.claude/projects/<slug>/<sid>/subagents/**/agent-<id>.jsonl
                      (+ sibling .meta.json)
  * pulse tail        automation/state/hooks/pulse.jsonl    (sends only -- see
                       setup/hooks/pulse.py's honesty constraint, carried
                       through to payload["army"]["legend"] verbatim)

STALE-FILE TRAP (verified in the build spec's own research): a session
registration file outlives the process it names. 22 files existed for 9 live
sessions at audit time. So liveness here is a PID check
(`_pid_alive`), never file existence, and on any check FAILURE we report NOT
alive -- a false "session is gone" is a cosmetic miss, a false "session is
alive" fabricates presence, which is the worse failure for a presence view.

SCOPE: this only enumerates sessions this box's own `~/.claude/sessions`
registry knows about. `ListAgents` also surfaces cloud / Remote Control
sessions with no local file -- deliberately out of scope here (no filesystem
tap exists for them); the payload carries an explicit note so the UI never
implies completeness it doesn't have.

Nothing here computes a trading metric or touches trading state -- this is
presence telemetry only. Every failure degrades to an empty list; this module
must never be the reason the cockpit page fails to build.
"""
from __future__ import annotations

import ctypes
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SESSIONS_DIR = Path.home() / ".claude" / "sessions"
PROJECTS_DIR = Path.home() / ".claude" / "projects"
PULSE_JSONL = REPO / "automation" / "state" / "hooks" / "pulse.jsonl"

# Caps keep the payload (and the SVG it drives) bounded regardless of how many
# sessions/workers/pulses are on disk -- an unbounded army view is a slow page,
# not a useful one. Overflow counts are still reported so nothing is silently
# dropped without a trace.
MAX_SESSION_NODES = 12
MAX_WORKERS_PER_SESSION = 8
MAX_PULSE_ROWS = 60

# A worker whose agent-*.jsonl hasn't been touched in this long reads as
# idle/finished, never "dead" -- there is no "agent finished" marker on disk
# (spec sec 2c), only file mtime recency. Mid-band of the spec's 60-120s window.
WORKER_ACTIVE_S = 90.0

# A session dot reads "just talked" (ok) only if a pulse row named it within
# this window; otherwise "alive but quiet" (warn) or "process gone" (bad).
SESSION_RECENT_S = 300.0

# Bound the read when hunting a session's human title -- these transcripts run
# tens of MB; the title record is always near the tail, so read only that.
TITLE_TAIL_BYTES = 200_000

_TITLE_RE_CUSTOM = re.compile(r'"customTitle":"((?:[^"\\]|\\.)*)"')
_TITLE_RE_AI = re.compile(r'"aiTitle":"((?:[^"\\]|\\.)*)"')


def _clip(s, cap: int = 140) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    if len(s) <= cap:
        return s
    cut = s[:cap].rsplit(" ", 1)[0].rstrip(",;:")
    return (cut or s[:cap]) + "…"


def _unescape_json_str(s: str) -> str:
    """A regex-captured JSON string body still carries \\" / \\n escapes."""
    try:
        return json.loads('"' + s + '"')
    except ValueError:
        return s


def _pid_alive(pid) -> bool:
    """True only if a live process currently holds this PID.

    Windows-only check via OpenProcess (no psutil in this venv). PID reuse by
    an unrelated process is a known false-positive this simple check cannot
    rule out -- acceptable, because the failure mode this function exists to
    prevent (a stale file read as a live session) is far more common in
    practice than a same-tick PID recycle. Any check FAILURE reports False:
    a presence view that fabricates a session is worse than one that
    under-reports by a beat.
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
        except Exception:
            return False
    try:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    except Exception:
        return False


def _slug_for(cwd: str) -> str:
    """Mirrors the client's own slugging: `~/.claude/projects/<slug>/`."""
    return re.sub(r"[^A-Za-z0-9]", "-", cwd or "")


def _age_h(p: Path):
    try:
        return (dt.datetime.now() - dt.datetime.fromtimestamp(p.stat().st_mtime)).total_seconds() / 3600.0
    except OSError:
        return None


def _load_sessions() -> list[dict]:
    """Every `~/.claude/sessions/<pid>.json`. NEVER reads the sibling `.key`
    credential file -- the glob below only matches `*.json`, and pulse.py's own
    docstring names exposing that file as the one hard boundary in this build."""
    out: list[dict] = []
    try:
        files = sorted(SESSIONS_DIR.glob("*.json"))
    except OSError:
        return out
    for f in files:
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(raw, dict):
            continue
        sid = raw.get("sessionId") or ""
        if not sid:
            continue
        started_ms = raw.get("startedAt")
        started_iso = ""
        try:
            if started_ms:
                started_iso = dt.datetime.fromtimestamp(float(started_ms) / 1000.0).isoformat(timespec="seconds")
        except (TypeError, ValueError, OSError):
            started_iso = ""
        out.append({
            "session_id": sid,
            "pid": raw.get("pid"),
            "name": raw.get("name") or sid[:8],
            "kind": raw.get("kind") or "",
            "entrypoint": raw.get("entrypoint") or "",
            "version": raw.get("version") or "",
            "cwd": raw.get("cwd") or "",
            "started_at": started_ms,
            "started_at_iso": started_iso,
            "alive": _pid_alive(raw.get("pid")),
        })
    return out


def _session_title(slug: str, session_id: str) -> str:
    """Human title, preferring an explicit `customTitle` over the derived
    `aiTitle` (same precedence the client's own tab title uses). Bounded read
    from the tail; on any failure this degrades to "", never a raised error --
    the transcript JSONL format is documented internal and version-unstable."""
    if not slug:
        return ""
    path = PROJECTS_DIR / slug / f"{session_id}.jsonl"
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            if size > TITLE_TAIL_BYTES:
                fh.seek(-TITLE_TAIL_BYTES, os.SEEK_END)
            raw = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    m = _TITLE_RE_CUSTOM.findall(raw)
    if m:
        return _clip(_unescape_json_str(m[-1]))
    m = _TITLE_RE_AI.findall(raw)
    if m:
        return _clip(_unescape_json_str(m[-1]))
    return ""


def _first_user_text(jsonl_path: Path) -> str:
    """A worker's task label = the first user message of its own transcript
    (spec sec 2c). Reads only the first line -- that record IS the task, so a
    full-file scan is unnecessary work every poll would otherwise pay for."""
    try:
        with jsonl_path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return ""
    try:
        rec = json.loads(first)
    except ValueError:
        return ""
    if not isinstance(rec, dict):
        return ""
    content = ((rec.get("message") or {}) if isinstance(rec.get("message"), dict) else {}).get("content")
    if isinstance(content, str):
        return _clip(content, 180)
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                return _clip(str(block["text"]), 180)
    return ""


def _worker_row(path: Path, session_id: str) -> dict | None:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    stem = path.stem  # "agent-<id>" (Path.stem strips only the .jsonl suffix)
    agent_id = stem[len("agent-"):] if stem.startswith("agent-") else stem
    meta_path = path.with_name(stem + ".meta.json")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    age_s = max(0.0, dt.datetime.now().timestamp() - mtime)
    task = _first_user_text(path)
    return {
        "agent_id": agent_id,
        "session_id": session_id,
        # workflow fan-outs nest under subagents/workflows/wf_<id>/; direct
        # Agent-tool spawns sit right under subagents/. Empty string when flat.
        "workflow_id": path.parent.name if path.parent.name.startswith("wf_") else "",
        "agent_type": meta.get("agentType") or "",
        "model": meta.get("model") or "",
        "task": task or (meta.get("agentType") or ""),  # degrade to type, never blank
        "last_write": dt.datetime.fromtimestamp(mtime).isoformat(timespec="seconds"),
        "active": age_s <= WORKER_ACTIVE_S,
    }


def _worker_rows_for_session(slug: str, session_id: str) -> list[dict]:
    if not slug:
        return []
    base = PROJECTS_DIR / slug / session_id / "subagents"
    if not base.is_dir():
        return []
    try:
        files = list(base.rglob("agent-*.jsonl"))
    except OSError:
        return []
    rows = [r for r in (_worker_row(p, session_id) for p in files) if r]
    rows.sort(key=lambda r: r["last_write"], reverse=True)
    return rows


def _scan_pulse_file() -> list[dict]:
    """The whole ring (pulse.py caps it at ~2000 rows, so this is cheap) in
    on-disk order, oldest first. One malformed line never drops the tail."""
    try:
        text = PULSE_JSONL.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    rows: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _pick_orchestrator(sessions: list[dict], pulse_rows: list[dict]) -> str | None:
    """The session with the most recent 'spawn' row, else the newest-started
    session (preferring one still alive)."""
    known = {s["session_id"] for s in sessions}
    for row in reversed(pulse_rows):  # rows are chronological; walk newest-first
        if row.get("event") == "spawn" and row.get("session_id") in known:
            return row["session_id"]
    pool = [s for s in sessions if s["alive"]] or sessions
    if not pool:
        return None
    return max(pool, key=lambda s: s.get("started_at") or 0)["session_id"]


def build_army() -> dict:
    sessions = _load_sessions()
    pulse_rows = _scan_pulse_file()
    orchestrator_sid = _pick_orchestrator(sessions, pulse_rows)

    # last activity per session, for the "recently talked" (ok) vs "alive but
    # quiet" (warn) dot distinction the UI draws -- computed once here so the
    # UI never has to re-scan the pulse tail itself.
    last_seen: dict[str, str] = {}
    for row in pulse_rows:
        sid = row.get("session_id")
        ts = row.get("ts")
        if sid and ts:
            last_seen[sid] = ts  # rows are chronological -> last write wins

    ordered = sorted(
        sessions,
        key=lambda s: (s["session_id"] != orchestrator_sid, not s["alive"], -(s.get("started_at") or 0)),
    )
    visible = ordered[:MAX_SESSION_NODES]
    overflow = max(0, len(ordered) - len(visible))

    now_iso = dt.datetime.now().isoformat(timespec="seconds")
    session_out: list[dict] = []
    worker_out: list[dict] = []
    for s in visible:
        slug = _slug_for(s["cwd"])
        title = _session_title(slug, s["session_id"])
        workers = _worker_rows_for_session(slug, s["session_id"])
        seen = last_seen.get(s["session_id"])
        recent = False
        if seen:
            try:
                recent = (dt.datetime.fromisoformat(now_iso) - dt.datetime.fromisoformat(seen)).total_seconds() <= SESSION_RECENT_S
            except ValueError:
                recent = False
        session_out.append({
            "session_id": s["session_id"],
            "name": s["name"],
            "kind": s["kind"],
            "entrypoint": s["entrypoint"],
            "version": s["version"],
            "pid": s["pid"],
            "cwd": s["cwd"],
            "started_at": s["started_at_iso"],
            "alive": s["alive"],
            "recent_activity": recent,
            "title": title,
            "is_orchestrator": s["session_id"] == orchestrator_sid,
            "worker_count": len(workers),
            "worker_overflow": max(0, len(workers) - MAX_WORKERS_PER_SESSION),
        })
        worker_out.extend(workers[:MAX_WORKERS_PER_SESSION])

    orchestrator = next((s for s in session_out if s["is_orchestrator"]), None)

    pulses = [
        {
            "ts": r.get("ts", ""),
            "event": r.get("event", ""),
            "session_id": r.get("session_id", ""),
            "agent_id": r.get("agent_id", ""),
            "to": r.get("to", ""),
            "detail": r.get("detail", ""),
        }
        for r in pulse_rows[-MAX_PULSE_ROWS:]
    ]

    return {
        "orchestrator": orchestrator,
        "sessions": session_out,
        "workers": worker_out,
        "session_overflow": overflow,
        "pulses": pulses,
        # NON-NEGOTIABLE HONESTY (pulse.py's own contract, carried through):
        # this is SENDS, never confirmed deliveries.
        "legend": ("Pulses show messages SENT, not delivered — a held, expired, refused, or "
                   "queue-full send still animates here; there is no receive-side confirmation."),
        "scope_note": ("Local sessions on this box's ~/.claude/sessions registry only — cloud "
                       "and Remote Control sessions have no local file and are not enumerated."),
        "source": {
            "sessions": {"path": "~/.claude/sessions/*.json", "ok": bool(sessions),
                         "age_h": _age_h(SESSIONS_DIR) if SESSIONS_DIR.exists() else None},
            "pulse": {"path": (PULSE_JSONL.relative_to(REPO).as_posix()
                                if str(PULSE_JSONL).startswith(str(REPO)) else str(PULSE_JSONL)),
                      "age_h": _age_h(PULSE_JSONL), "ok": PULSE_JSONL.exists()},
        },
    }

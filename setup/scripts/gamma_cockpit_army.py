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
import time
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

# Same bound for context-usage: the last assistant message's usage object is
# always near the tail (verified 2026-08-29 against 10 live transcripts:
# furthest hit was 10.4KB from EOF), so a wide-margin tail read is still tiny
# next to files that run tens of MB, and never touches the whole file.
CONTEXT_TAIL_BYTES = 400_000

# ---------------------------------------------------------------------------
# Per-session context-usage bar (spec: J wants a real-time "how full is this
# window" bar on every Army-view session card).
#
# TOKEN COUNT: the transcript records a `usage` object on every assistant
# message (`message.usage`: input_tokens, cache_creation_input_tokens,
# cache_read_input_tokens, output_tokens, ...). `input_tokens` ALONE is not
# a context-fullness proxy -- it is only the newly-uncached slice of that
# turn's prompt (observed as low single digits on a warm cache in every
# sampled transcript). The actual size of the context window as of the last
# turn is the full prompt sent that turn: input_tokens +
# cache_creation_input_tokens + cache_read_input_tokens. output_tokens is
# deliberately excluded -- it is the reply being generated, not context
# already occupied as of that request.
#
# DENOMINATOR: NOT the raw model context window. Auto-compaction fires at
# `autoCompactWindow` (global default 800_000, ~/.claude/settings.json;
# project-local .claude/settings.json can override per session's cwd, same
# override precedence the client itself uses) -- THAT is the number the bar
# means, per spec: the raw window (1M for the `opus[1m]` alias configured
# here, and for every current-generation model per the claude-api skill's
# model cache -- unverified via a live Models-API call in this session) would
# under-report how close a session is to actually compacting.
#
# HONESTY: context_source is the literal string "unknown" whenever either
# half (token count or limit) could not be resolved. A fabricated percentage
# on a bar is worse than an absent bar -- never guess a number here.
CONTEXT_UNKNOWN = "unknown"
GLOBAL_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"


def _read_tail_text(path: Path, cap: int) -> tuple[str, bool] | None:
    """(text, truncated) for the last `cap` bytes of `path`, decoded
    leniently. `truncated` is True only when the file was actually larger
    than `cap` (a real seek happened, so the first line may be a partial
    record cut mid-line) -- False means the whole file was read and every
    line is intact. None on any I/O failure (missing file, permission
    error) -- callers treat that as "unknown"."""
    try:
        size = path.stat().st_size
        truncated = size > cap
        with path.open("rb") as fh:
            if truncated:
                fh.seek(-cap, os.SEEK_END)
            raw = fh.read()
    except OSError:
        return None
    return raw.decode("utf-8", errors="replace"), truncated


def _last_context_tokens(slug: str, session_id: str) -> tuple[int | None, str]:
    """(tokens, reason). tokens is None when unresolvable -- caller maps that
    to context_source="unknown" rather than ever emitting a guessed number."""
    if not slug:
        return None, "no_cwd"
    path = PROJECTS_DIR / slug / f"{session_id}.jsonl"
    result = _read_tail_text(path, CONTEXT_TAIL_BYTES)
    if result is None:
        return None, "transcript_unreadable"
    text, truncated = result
    lines = text.split("\n")
    if truncated and len(lines) > 1:
        lines = lines[1:]  # first line is a partial record cut mid-line by the seek
    last_tokens: int | None = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue  # corrupt/truncated line -- skip, never abort the scan
        if not isinstance(rec, dict) or rec.get("type") != "assistant":
            continue
        message = rec.get("message")
        if not isinstance(message, dict):
            continue
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        try:
            inp = int(usage.get("input_tokens") or 0)
            cwrite = int(usage.get("cache_creation_input_tokens") or 0)
            cread = int(usage.get("cache_read_input_tokens") or 0)
        except (TypeError, ValueError):
            continue
        last_tokens = inp + cwrite + cread  # rows are chronological -> last write wins
    if last_tokens is None:
        return None, "no_usage_in_tail"
    return last_tokens, "transcript_tail"


def _auto_compact_window_for(cwd: str, cache: dict) -> tuple[int | None, str]:
    """autoCompactWindow with the client's own override precedence: a
    project-local .claude/settings.json beats the global one. `cache` is a
    plain dict the caller owns for the duration of one build_army() call --
    settings files are small, but there is no reason to re-stat/re-parse them
    once per visible session when they're the same handful of files."""
    key = cwd or ""
    if key in cache:
        return cache[key]
    candidates = []
    if cwd:
        candidates.append((Path(cwd) / ".claude" / "settings.json", "project"))
    candidates.append((GLOBAL_SETTINGS_PATH, "global"))
    result: tuple[int | None, str] = (None, "settings_unreadable")
    for path, origin in candidates:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(raw, dict):
            continue
        val = raw.get("autoCompactWindow")
        if isinstance(val, (int, float)) and val > 0:
            result = (int(val), origin)
            break
    cache[key] = result
    return result


def _context_usage(slug: str, session_id: str, cwd: str, cache: dict) -> dict:
    """Returns the four context-bar fields for one session dict. Never
    raises; degrades to the unknown state on any failure of either half."""
    tokens, tok_reason = _last_context_tokens(slug, session_id)
    limit, limit_reason = _auto_compact_window_for(cwd, cache)
    if tokens is None or limit is None:
        return {
            "context_tokens": 0,
            "context_limit": 0,
            "context_pct": 0.0,
            "context_source": CONTEXT_UNKNOWN,
        }
    pct = max(0.0, min(100.0, round((tokens / limit) * 100.0, 1)))
    return {
        "context_tokens": tokens,
        "context_limit": limit,
        "context_pct": pct,
        "context_source": f"{tok_reason}+{limit_reason}_autoCompactWindow",
    }


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


# --------------------------------------------------------------------------------------
# ACTIVITY, not aliveness. J, 2026-08-29: "i dont have any claude windows open besides this
# one they are just old chats."
#
# He was right and the view was wrong. Every one of the 10 registry PIDs resolves to a live
# process named `claude`, because Claude Desktop leaves a CLI process running per chat long
# after the chat is closed. So "the process exists" was never evidence that J has a window
# open -- it only proves the app has not reaped it yet.
#
# The honest signal is the transcript mtime. Measured on this box at the moment of the
# complaint: this session 0.0 min, then 8.7 / 42 / 56 min, then 310 min, then four sessions
# between 22 and 50 HOURS stale. A view that presents a 50-hour-old chat identically to the
# window you are typing in is not a presence view.
# --------------------------------------------------------------------------------------
ACTIVE_MINUTES = 5      # writing right now -- this is a window in use
IDLE_MINUTES = 120      # touched this session-ish; worth showing, visually quieter


def _last_write_minutes(slug: str, session_id: str) -> float | None:
    """Minutes since the session transcript was last written, or None if unreadable."""
    if not slug or not session_id:
        return None
    try:
        path = PROJECTS_DIR / slug / f"{session_id}.jsonl"
        if not path.is_file():
            return None
        return max(0.0, (time.time() - path.stat().st_mtime) / 60.0)
    except OSError:
        return None


def _activity_of(minutes: float | None) -> str:
    """active | idle | stale | unknown. Unknown never masquerades as active."""
    if minutes is None:
        return "unknown"
    if minutes <= ACTIVE_MINUTES:
        return "active"
    if minutes <= IDLE_MINUTES:
        return "idle"
    return "stale"


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


def _first_user_text(jsonl_path: Path, cap: int = 180) -> str:
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
        return _clip(content, cap)
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                return _clip(str(block["text"]), cap)
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
        # The Agent tool's own one-line `description` ("Mine dashboard craft techniques").
        # It was being dropped on the floor while the cockpit rendered 180 chars of shared
        # prompt preamble instead -- the single best label available, ignored.
        "description": _clip(meta.get("description") or "", 90),
        "task": task or (meta.get("agentType") or ""),  # degrade to type, never blank
        # Kept only long enough to strip boilerplate shared with siblings; dropped
        # before shipping so the page never carries it. Must exceed the shared
        # header a workflow fan-out prepends (~2.6KB in the run this was built
        # against) or the common prefix eats the whole string and there is nothing
        # distinguishing left to find. The first line is read in full regardless,
        # so a larger cap costs no extra I/O.
        "_task_full": _first_user_text(path, 6000),
        "last_write": dt.datetime.fromtimestamp(mtime).isoformat(timespec="seconds"),
        "active": age_s <= WORKER_ACTIVE_S,
    }


def _skip_data_prefix(text: str) -> str:
    """Drop a leading `LABEL:` header and any JSON blob handed to the agent as input.

    A later-phase workflow agent is often prompted with the previous phase's findings
    first, so its prompt OPENS with data rather than instruction and the card rendered
    `AUTOPSY: [ { "summary": ...` as the agent's purpose. That blob is the agent's
    input, never its job. Bounded to four peels so a pathological prompt cannot spin,
    and if a blob never closes inside what was read we stop rather than guess.
    """
    t = text
    for _ in range(4):
        t = t.lstrip()
        header = re.match(r"^[A-Z][A-Z0-9 _\-]{2,40}:\s*", t)
        if header:
            t = t[header.end():]
            continue
        if t[:1] not in "[{":
            break
        depth, in_str, esc, end = 0, False, False, -1
        for i, ch in enumerate(t):
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end < 0:
            break
        t = t[end + 1:]
    return re.sub(r"\s+", " ", t).strip(" .,:;-—")


def _derive_purposes(workers: list[dict]) -> None:
    """Give every worker a `purpose`: one short line saying what THIS agent is for.

    Three sources, best first:
      1. the Agent tool's own `description` ("Mine dashboard craft techniques") --
         written by whoever spawned it, for exactly this job;
      2. for a workflow fan-out, the part of the prompt that DIFFERS from its
         siblings. Workflow subagents share a large context header, so the first
         180 chars of every sibling's prompt were byte-identical boilerplate and
         the cockpit rendered the same "REPO: C:\\Users\\jackw\\Desktop\\42 ..."
         on every row -- the anonymous-grey-circle problem in text form. Stripping
         the longest common prefix leaves precisely the distinguishing instruction;
      3. the plain first line of the prompt, when neither applies.

    Never invents: if nothing distinguishing survives, purpose stays the raw task.
    """
    # NEAREST sibling, not all siblings. A prefix common to EVERY agent in the group is
    # usually empty, because one workflow's phases have different prompt shapes: an
    # early phase opens "Worker task in repo C:\\..." while a later one is handed the
    # previous phase's findings and opens "AUTOPSY: [{...". The universal prefix across
    # those is ~0 characters, so nothing was stripped and the JSON blob went to screen.
    # Comparing each agent against its single closest sibling strips whatever boilerplate
    # THAT pair actually shares, which is the thing that makes them look alike.
    candidates = [w for w in workers if not w.get("description")]
    for w in candidates:
        mine = w.get("_task_full") or ""
        if not mine:
            continue
        best = 0
        for other in candidates:
            if other is w or other["session_id"] != w["session_id"]:
                continue
            theirs = other.get("_task_full") or ""
            n = 0
            for a, b in zip(mine, theirs):
                if a != b:
                    break
                n += 1
            best = max(best, n)
        rest = mine
        if best >= 60:
            # cut back to a word boundary so a purpose never opens mid-word
            rest = mine[len(mine[:best].rsplit(" ", 1)[0]):]
        rest = _skip_data_prefix(rest)
        if len(rest) >= 24:
            w["_distinct"] = rest
    for w in workers:
        # Last resort still gets the header/blob peel: when several agents were given
        # a genuinely identical prompt there IS nothing distinguishing to find, and
        # repeating that fact is honest -- but it should start at the instruction
        # rather than at "REPO: C:\Users\...".
        w["purpose"] = _clip(
            w.get("description")
            or w.get("_distinct")
            or _skip_data_prefix(w.get("_task_full") or w.get("task") or "")
            or w.get("task")
            or "",
            130,
        )
        w.pop("_task_full", None)
        w.pop("_distinct", None)


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
    # Purposes are derived across the WHOLE set, not per row: a workflow sibling's
    # distinguishing text is only knowable by comparison with its siblings.
    _derive_purposes(rows)
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
        key=lambda s: (s["session_id"] != orchestrator_sid, not s["alive"], -(s.get("started_at") or 0)),  # noqa: E501
    )
    visible = ordered[:MAX_SESSION_NODES]
    overflow = max(0, len(ordered) - len(visible))

    now_iso = dt.datetime.now().isoformat(timespec="seconds")
    session_out: list[dict] = []
    worker_out: list[dict] = []
    settings_cache: dict = {}  # autoCompactWindow lookups, scoped to this one build
    for s in visible:
        slug = _slug_for(s["cwd"])
        title = _session_title(slug, s["session_id"])
        workers = _worker_rows_for_session(slug, s["session_id"])
        context = _context_usage(slug, s["session_id"], s["cwd"], settings_cache)
        last_write_min = _last_write_minutes(slug, s["session_id"])
        activity = _activity_of(last_write_min)
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
            # RUNNING RIGHT NOW vs ever-spawned. Without this split the cockpit drew a
            # standing army that had evaporated: 42-c9 rendered "8 workers +43" with five
            # solid dots while every one of its 51 subagents had finished 9.3h earlier
            # (verified 2026-08-30). worker_count is a HISTORY total; only worker_active
            # is a claim about the present, and any "N workers" phrasing on the page must
            # be sourced from this field.
            "worker_active": sum(1 for w in workers if w.get("active")),
            "context_tokens": context["context_tokens"],
            "context_limit": context["context_limit"],
            "context_pct": context["context_pct"],
            "context_source": context["context_source"],
            "last_write_min": None if last_write_min is None else round(last_write_min, 1),
            "activity": activity,
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
        # When this snapshot was taken, as a UNIX epoch -- the SAME clock as
        # worker.last_write, so the page can age itself. The existing built_at_et is an
        # ET wall-clock STRING and this box runs Mountain time, so Date.parse() on it is
        # two hours wrong; a page opened from file:// used it to keep claiming "running
        # right now" about a world that had moved on. A present-tense claim needs a
        # comparable clock or it is not a claim, it is a guess.
        "generated_epoch": int(time.time()),
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
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

"""gamma_autonomy.py -- is Gamma actually awake, and what does it think it should do?

WHY (J, 2026-08-30): "where is the autonomy, how do we have gamma be alive and on the
page and give it the ability to do actions like choose recc action cards, theorize
whats next".

The autonomy is REAL -- 48 commits landed unattended last night -- but none of it
reached any surface, so from the page it looked like nothing was happening. This
module is the read-only status of the autonomous loop, so the app can show it.

WHAT IT REFUSES TO DO: decide anything, fire anything, or change any state. It reads.
Consequence stays behind autofire_cards.py, which owns its own guards (dry-run
default, RTH refusal, halt flag, quiet mode, per-run and per-day caps). A status
surface that could also act would be the fastest way to turn a glance into an
accident.

THE HONESTY THAT MATTERS MOST HERE: `autofire.ever_fired` is False today. The
capability J is asking about -- Gamma choosing an action card by itself -- is built,
configured with --live on weekdays, and has never executed once. Reporting the loop
as "on" because the machinery exists would be the exact lie this project keeps
guarding against.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
# Fixed to THIS file's own location, never to the (test-monkeypatchable) REPO
# above -- a test that points REPO at a tmp_path to isolate the goal-file read
# must not also lose the real doctrine.py off sys.path.
_HOOKS_DIR = Path(__file__).resolve().parents[1] / "hooks"

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _ever_fired(path: Path) -> bool:
    """Did this ledger EVER record a fire? A whole-file question, answered by streaming.

    The caller only holds the last 40 rows, which is right for "what happened lately"
    and wrong for "has this never fired" -- 41 consecutive refusals would have flipped
    the answer. Streamed line by line so an append-only ledger cannot cost memory.
    """
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"fired"' in line:
                    return True
    except OSError:
        return False
    return False


def _read_jsonl(path: Path, tail: int = 40) -> list:
    try:
        # errors="replace": a torn write landing mid-multibyte-sequence raises
        # UnicodeDecodeError, which is a ValueError and NOT caught by OSError -- it
        # took the whole autonomy slice down rather than dropping one line. The two
        # sibling modules already read this way.
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-tail:]
    except (OSError, ValueError):
        return []
    out = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue          # a torn line is skipped, never guessed at
    return out


def _task_states(names: list[str]) -> dict:
    """Scheduled-task state, straight from schtasks -- the registry is the truth.

    A task can exist, be correctly written, and still never fire; only the OS knows.
    Any failure here degrades to unknown rather than to a cheerful default.
    """
    out = {}
    for n in names:
        try:
            p = subprocess.run(
                ["schtasks", "/query", "/tn", n, "/fo", "list", "/v"],
                capture_output=True, text=True, timeout=20,
                creationflags=_CREATE_NO_WINDOW,
            )
            if p.returncode != 0:
                out[n] = {"known": False}
                continue
            row = {"known": True}
            for line in p.stdout.splitlines():
                if ":" not in line:
                    continue
                k, v = line.split(":", 1)
                k, v = k.strip().lower(), v.strip()
                if k == "scheduled task state":
                    row["state"] = v
                elif k == "last run time":
                    row["last_run"] = v
                elif k == "last result":
                    row["last_result"] = v
                elif k == "next run time":
                    row["next_run"] = v
                elif k == "schedule type":
                    row["schedule"] = v
            # 267011 (0x41303) is Windows for "the task has never run" -- it reads
            # like an error code and is not one, so it is translated here rather
            # than shown raw on a page.
            row["never_run"] = str(row.get("last_result", "")).strip() == "267011"
            out[n] = row
        except Exception:
            out[n] = {"known": False}
    return out


def _next_loud(quiet_window: str, now: dt.datetime) -> str | None:
    """When the quiet window ends, parsed from the window string the muter itself
    wrote. Returns None rather than guessing if the shape is not what we expect."""
    import re
    m = re.search(r"LOUD[^0-9]*(\d{2}):(\d{2})", quiet_window or "")
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    nxt = now.replace(hour=h, minute=mi, second=0, microsecond=0)
    if nxt <= now:
        nxt += dt.timedelta(days=1)
    return nxt.isoformat(timespec="minutes")


_H2 = re.compile(r"^\s*##\s+(.*?)\s*$")
_QUEUE_ITEM = re.compile(r"^-\s*\[( |x|~|B-J|B)\]\s*(.*)$")
_BULLET = re.compile(r"^-\s*(.*)$")
_QUEUE_STATE = {" ": "todo", "x": "done", "~": "wip", "B": "blocked", "B-J": "blocked_j"}


def _humanize_goal_title(goal_id: str | None) -> str:
    """GOAL-GAMMA-AUTONOMY-2026-09-03 -> "Gamma autonomy". Date is dropped here --
    it already lives in the id, and the page renders it separately in a dim span
    so the title reads as a phrase, not an identifier."""
    s = str(goal_id or "").strip()
    s = re.sub(r"^GOAL-", "", s)
    s = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", s)
    words = [w for w in s.split("-") if w]
    if not words:
        return str(goal_id or "")
    out = " ".join(w.lower() for w in words)
    return out[0].upper() + out[1:]


def _goal_sections(text: str) -> dict:
    """Split a goal .md on its literal `## ` headings into {HEADING_UPPER: [lines]}."""
    sections: dict = {}
    cur = None
    for line in text.splitlines():
        m = _H2.match(line)
        if m:
            cur = m.group(1).strip().upper()
            sections[cur] = []
            continue
        if cur is not None:
            sections[cur].append(line)
    return sections


_MD_NOISE = re.compile(r"\*\*|__|`")


def _plain(s: str) -> str:
    """Strip markdown emphasis/code markers for the glass: `**bold**` and backticks are
    author conventions in the goal file, and they rendered verbatim on the first live
    screenshot (2026-09-03). Content is untouched; only the markers go."""
    return _MD_NOISE.sub("", s)


def _fold_bullets(lines: list[str], cap: int = 400) -> list[str]:
    """Top-level `- ` bullets (unindented, column 0), with indented continuation
    lines folded into the bullet above them. Matching against the RAW line (not
    a stripped copy) is load-bearing: a stripped indented continuation that
    itself starts with "-" (a nested sub-bullet) must not be mistaken for a new
    top-level item."""
    out: list[str] = []
    for line in lines:
        m = _BULLET.match(line)
        if m:
            out.append(m.group(1).strip())
        elif out and line.strip():
            out[-1] = (out[-1] + " " + line.strip()).strip()
    return [_plain(re.sub(r"\s+", " ", o))[:cap] for o in out if o.strip()]


def _fold_queue(lines: list[str]) -> list[dict]:
    """QUEUE items: `- [x] text` at column 0 starts a new item; anything else
    non-blank folds into the PREVIOUS item's text (multi-line continuations
    under one bullet, e.g. the `+ ...` sub-lines under A1 in the live goal)."""
    items: list[dict] = []
    for line in lines:
        m = _QUEUE_ITEM.match(line)
        if m:
            items.append({"state": _QUEUE_STATE.get(m.group(1), "todo"), "text": m.group(2).strip()})
        elif items and line.strip():
            items[-1]["text"] = (items[-1]["text"] + " " + line.strip()).strip()
    for it in items:
        it["text"] = _plain(re.sub(r"\s+", " ", it["text"]))[:400]
    return items


def _goal_verbatim(text: str) -> str | None:
    """The blockquote (`> ...` lines) directly under the H1, before any `## ` heading."""
    lines: list[str] = []
    started = False
    for line in text.splitlines():
        if _H2.match(line):
            break
        s = line.strip()
        if s.startswith(">"):
            started = True
            lines.append(s.lstrip(">").strip())
        elif started and not s:
            break
    if not lines:
        return None
    joined = re.sub(r"\s+", " ", " ".join(lines)).strip()
    joined = joined.replace("**", "").replace("*", "")
    return joined[:300] or None


def _goal_block(now: dt.datetime, goal_ptr: dict) -> dict:
    """Everything the Autonomy view needs about the active goal, or an honest
    all-None shape when there is none. Never raises -- a parse failure degrades
    to active:false rather than losing the whole autonomy panel."""
    empty = {
        "active": False, "id": None, "file": None, "opened_at_et": None,
        "expires_at_et": None, "days_left": None, "closed_reason": goal_ptr.get("closed_reason"),
        "title": None, "verbatim": None, "done_when": [], "queue": [], "progress_log": [],
        "honest_state": None, "next_item": None, "source": None,
    }
    if not goal_ptr.get("active") or not goal_ptr.get("file"):
        return empty
    gfile = goal_ptr["file"]
    path = REPO / gfile
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return empty
    try:
        sections = _goal_sections(text)
        done_when = _fold_bullets(sections.get("DONE-WHEN", []))
        queue = _fold_queue(sections.get("QUEUE", []))
        progress_log = _fold_bullets(sections.get("PROGRESS LOG", []))[-6:]
        honest_lines = [l for l in sections.get("HONEST STATE", []) if l.strip()]
        honest_state = _plain(re.sub(r"\s+", " ", " ".join(honest_lines))).strip()[:400] or None
        verbatim = _goal_verbatim(text)

        expires = goal_ptr.get("expires_at_et")
        days_left = None
        if expires:
            try:
                raw = str(expires).strip()
                exp = (dt.datetime.strptime(raw, "%Y-%m-%d") if len(raw) == 10
                       else dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None))
                days_left = (exp.date() - now.date()).days
            except Exception:
                days_left = None

        next_item = None
        try:
            sys.path.insert(0, str(_HOOKS_DIR))
            import doctrine as D
            next_item = D.goal_next_open_item(text)
        except Exception:
            next_item = None

        gid = goal_ptr.get("id")
        return {
            "active": True,
            "id": gid,
            "file": gfile,
            "opened_at_et": goal_ptr.get("opened_at_et"),
            "expires_at_et": expires,
            "days_left": days_left,
            "closed_reason": goal_ptr.get("closed_reason"),
            "title": _humanize_goal_title(gid),
            "verbatim": verbatim,
            "done_when": done_when,
            "queue": queue,
            "progress_log": progress_log,
            "honest_state": honest_state,
            "next_item": next_item,
            "source": Path(gfile).as_posix() if gfile else None,
        }
    except Exception:
        return empty


def build(now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now()

    quiet = _read_json(STATE / "quiet-mode.json") or {}
    budget = _read_json(STATE / "conductor-budget-status.json") or {}
    watcher = _read_json(STATE / "watcher-report.json") or {}
    goal_ptr = _read_json(STATE / "active-goal.json") or {}

    fire_rows = _read_jsonl(STATE / "autofire-ledger.jsonl")
    today = now.strftime("%Y-%m-%d")
    fired_today = [r for r in fire_rows
                   if r.get("date_et") == today and r.get("decision") == "fired"]
    # "has never fired" is a claim about the WHOLE ledger, and fire_rows is only the
    # last 40 lines -- so 41 refusals in a row would have reported a card-firer that
    # had fired many times as one that never had. Scan the file for the claim.
    ever_fired = _ever_fired(STATE / "autofire-ledger.jsonl") or any(
        r.get("decision") == "fired" for r in fire_rows)

    outcomes = _read_jsonl(STATE / "conductor-outcomes.jsonl", tail=12)

    tasks = _task_states([
        "Gamma_AutofireCards", "Gamma_Watcher", "Gamma_Conductor",
        "Gamma_KitchenDaemonKeepalive", "Gamma_GoalAutopilot", "Gamma_Home",
    ])

    # What it would do next: the goal's own top open item is the conductor's
    # STAGE-1 pick, so it IS the next move rather than a guess about one.
    next_move = None
    gfile = goal_ptr.get("file")
    if goal_ptr.get("active") and gfile:
        try:
            sys.path.insert(0, str(_HOOKS_DIR))
            import doctrine as D
            item = D.goal_next_open_item((REPO / gfile).read_text(encoding="utf-8"))
            if item:
                next_move = {"kind": "goal", "goal": goal_ptr.get("id"), "text": item[:300]}
        except Exception:
            next_move = None

    quiet_active = bool(quiet.get("quiet_active"))

    # THE GOAL. J's own words: "we have an entire 'goal' dashboard and nothing is
    # driving it". This is that dashboard's data -- parsed from the same .md file
    # goal_next_open_item already reads, never re-derived from a second source.
    goal = _goal_block(now, goal_ptr)

    # THE AUTOPILOT. Written by goal_autopilot.py (a sibling builder's module,
    # A1 on this same goal) -- absent until that lands, and absence must read as
    # "not wired yet", never as a crash here.
    autopilot = _read_json(STATE / "goal-autopilot.json")

    # THE RESEARCH ENGINES. Kitchen + prospector liveness, each degrading to None
    # (never a fabricated zero) when its own state file is missing.
    kitchen = None
    kraw = _read_json(STATE / "kitchen-status.json")
    if kraw:
        qs = (kraw.get("queue_summary") or {}).get("by_status") or {}
        recent = kraw.get("recent_completed_top_10") or []
        kitchen = {
            "alive": kraw.get("daemon_alive"),
            "idle": kraw.get("idle"),
            "current_task_id": kraw.get("current_task_id"),
            "updated_at_et": kraw.get("updated_at_et"),
            "pending": qs.get("pending"),
            "completed": qs.get("completed"),
            "cost_today": kraw.get("today_cost_usd_paid_tier"),
            "cost_cap": kraw.get("today_cost_cap_usd"),
            "recent": [
                {"task": str(x.get("task") or "")[:160], "completed_at": x.get("completed_at")}
                for x in recent[:5]
            ],
        }
    prospector = None
    praw = _read_json(REPO / "analysis" / "prospector" / "state.json")
    if praw:
        prospector = {
            "last_run_et": praw.get("last_run_et"),
            "fires_total": praw.get("fires_total"),
            "ideas_total": praw.get("ideas_total"),
            "promoted_total": praw.get("promoted_total"),
            "folded_total": praw.get("folded_total"),
        }

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "awake": not quiet_active,
        "quiet": {
            "active": quiet_active,
            "window": quiet.get("quiet_window_et"),
            "held_down": quiet.get("total_held_down"),
            "next_loud": _next_loud(str(quiet.get("quiet_window_et") or ""), now),
            "updated_at": quiet.get("updated_at"),
        },
        "watcher": {
            "checked_at": watcher.get("checked_at"),
            "ok": watcher.get("ok"),
            "drive": watcher.get("drive"),
            "findings": [
                {"rule": f.get("rule"), "severity": f.get("severity"),
                 "message": str(f.get("message") or "")[:220]}
                for f in (watcher.get("findings") or [])[:5]
            ],
        },
        "autofire": {
            # THE HEADLINE. Built, configured --live on weekdays, never once executed.
            "ever_fired": ever_fired,
            "fired_today": len(fired_today),
            "last": (fire_rows[-1] if fire_rows else None),
            "task": tasks.get("Gamma_AutofireCards", {}),
        },
        "tasks": tasks,
        "recent_fires": [
            {"at": o.get("fired_at"), "task": o.get("task_id"),
             "drained": o.get("items_drained"), "lessons": o.get("lessons_shipped"),
             "regressions": o.get("regressions"), "note": str(o.get("note") or "")[:200]}
            for o in reversed(outcomes[-6:])
        ],
        # THE GOVERNOR. Without this the panel says "resting" and leaves the
        #    reason to the imagination -- and the reason is the whole answer. It
        #    stopped because it hit its own fire-count cap, having spent a small
        #    fraction of its money cap; that is a throttle doing its job, not a
        #    failure, and the two look identical from the outside.
        "budget": {
            "verdict": budget.get("verdict"),
            "reason": budget.get("reason"),
            "fires_used": budget.get("slots_used"),
            "fires_cap": budget.get("max_fires"),
            "spent_usd": budget.get("corrected_usd"),
            "cap_usd": budget.get("daily_cap_usd"),
            "checked_at": budget.get("checked_at_utc"),
        },
        "next_move": next_move,
        "goal": goal,
        "autopilot": autopilot,
        "engines": {"kitchen": kitchen, "prospector": prospector},
    }


def main() -> int:
    print(json.dumps(build(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

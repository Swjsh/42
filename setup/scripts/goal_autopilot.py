"""goal_autopilot.py -- Gamma opens and drives its own goals (no LLM decides which one).

WHY THIS EXISTS (GOAL-GAMMA-AUTONOMY-2026-09-03, task A1, J directive 2026-09-03
17:41 ET: "your /goal is gamma autonomy"). The durable-goal mechanism already has
TWO consumers wired for free -- `setup/hooks/doctrine.py::goal_next_open_item` /
`goal_expired` feed `conductor.md` STAGE 1 clause 2a (routes each fire to the goal's
top open item) and the Stop hook's `_check_goal_continuation` (keeps one session
going a few extra turns) -- but the ONE producer, `.claude/skills/gamma-goal/
SKILL.md`, is `disable-model-invocation: true`. Only J can open a goal by typing
`/gamma-goal open`, so the pointer sat `active:false` from 2026-08-30 to
2026-09-03 and every conductor fire fell through to tier-3 janitorial work.

This script is the producer that does NOT need J: a pure, deterministic walk down
`automation/state/goals/LADDER.md` (authored by Claude sessions or J -- THAT is
where judgment enters, not here). No LLM decides which goal opens next; this file
only enforces the schema and flips checkboxes.

ALGORITHM (`ensure`):
  1. RTH gate. During market hours (Mon-Fri 09:30-15:55 ET) this is a pure no-op --
     zero file writes, not even the status/log files -- so a 30-min scheduled fire
     can never collide with the trading engine.
  2. If `active-goal.json` is active, unexpired, and its goal file still has an
     open `- [ ]` QUEUE item -> noop (the common case; this is what most fires do).
     If instead every remaining item is `[~]` (wip, owned by a running session)
     -> ALSO noop ("no assignable item" is not "finished" -- see goal_is_terminal;
     this was the 2026-09-04 01:19 ET bug: closing a goal out from under three
     in-progress items because none of them was a bare `- [ ] `).
  3. Otherwise CLOSE the active goal (if one exists) -- reached only when EVERY
     QUEUE item's marker is terminal (`x`/`B`/`B-J`), or the goal expired, or its
     file went missing: append a PROGRESS LOG line +
     a HONEST STATE paragraph to the goal file, set active-goal.json inactive,
     flip its LADDER.md marker `[~]` -> `[x]`, flip its queue.md row's
     `status:in_progress` -> `status:done`/`status:expired` IN PLACE (one line).
  4. Then OPEN the first eligible queued (`[ ]`) LADDER.md entry in order: an
     entry is eligible only if its goal file exists AND has both a `## DONE-WHEN`
     heading and a `## QUEUE` section with >=1 bare `- [ ] ` item -- anything
     else is skipped with a logged reason, never opened. Opening writes
     active-goal.json, flips the ladder marker `[ ]` -> `[~]`, ensures exactly
     one queue.md row exists for it, and appends one PROGRESS LOG line.
  5. If nothing is eligible -> action "ladder_empty" (b), which is what the
     Autonomy dashboard tab turns red on.

FAIL OPEN, ALWAYS (per OP-25 / this project's Stop-hook doctrine): any exception
anywhere in this script is caught, logged as one line, recorded in the status
file's "error" field, and the process still exits 0 -- unless `--strict` is passed
(tests only). A goal-scheduling bug must never become a reason the conductor, or
any other fire, stops running.

SAFETY: writes ONLY under automation/state/ (active-goal.json, goals/LADDER.md,
goals/GOAL-*.md PROGRESS LOG/HONEST STATE appends, goal-autopilot.json/.jsonl)
and automation/overnight/queue.md (one row, in place). Never edits a goal file's
QUEUE items themselves -- only appends to PROGRESS LOG / HONEST STATE. Never
touches anything in `doctrine.FROZEN_TRADING_PATH`. No subprocess, no network,
no broker calls, no LLM calls -- pure stdlib file IO.

CLI:
    python goal_autopilot.py ensure [--dry-run] [--now ISO] [--repo PATH] [--strict]
    python goal_autopilot.py status [--json]
    python goal_autopilot.py close-if-terminal [--dry-run] [--now ISO] [--repo PATH]

Reused, not re-derived: `setup/hooks/doctrine.py::goal_next_open_item` /
`goal_expired` (the exact parsers the conductor + Stop hook already trust) and
`setup/scripts/et_clock.py::et_now` (the DST-aware ET clock -- NEVER Bash TZ,
this box runs Mountain time).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent          # setup/scripts
_DEFAULT_REPO = Path(__file__).resolve().parents[2]  # repo root

# et_clock.py lives right next to this file.
sys.path.insert(0, str(_HERE))
from et_clock import et_now  # noqa: E402

# doctrine.py's parsers are reused verbatim -- these are the SAME functions the
# conductor and the Stop hook already trust. Its location is fixed relative to
# THIS file (setup/scripts/.. -> setup/hooks), independent of any --repo override
# used by tests (tests point --repo at a throwaway tree of STATE files only; the
# real doctrine.py always ships beside the real setup/hooks).
sys.path.insert(0, str(_HERE.parent / "hooks"))
import doctrine as D  # noqa: E402

DEFAULT_MAX_CONTINUATIONS = 3
DEFAULT_EXPIRES_DAYS = 14

_LADDER_LINE = re.compile(
    r"^-\s*\[([ x~])\]\s*(GOAL-\S+?)\s*::\s*(.*?)\s*::\s*file:\s*(\S+)\s*::\s*expires_days:(\d+)"
    r"(?:\s*::\s*not_before:(\d{4}-\d{2}-\d{2}))?\s*$"
)
_HEADING_LINE = re.compile(r"^\s*#{1,6}\s+(.*)$")

LADDER_HEADER = """# LADDER.md -- the goal-autopilot's ordered queue of durable Gamma goals

> Producer: `setup/scripts/goal_autopilot.py` (task A1, GOAL-GAMMA-AUTONOMY-2026-09-03).
> This is the ONE place judgment enters the autonomy loop -- the autopilot itself is
> a deterministic walker, never an LLM choosing between entries. Order = priority:
> the autopilot always opens the FIRST eligible `[ ]` line, top to bottom.
>
> Line grammar (ONE line per entry, grep-able, no continuation prose):
>   `- [ ] GOAL-<ID> :: <one line> :: file: automation/state/goals/GOAL-<ID>.md :: expires_days:14`
>   optional trailing ` :: not_before:YYYY-MM-DD` -- the entry is NOT eligible before that ET
>   calendar date (skipped, logged), so a goal whose evidence cannot exist yet (e.g. "the
>   first live fires on Tuesday") never becomes the active goal early and never burns a
>   conductor fire recording "not yet" (added 2026-09-05 after exactly that happened).
>
> Markers: `[ ]` queued (not yet opened) -- `[~]` active (this IS today's
> active-goal.json pointer) -- `[x]` done/closed (its DONE-WHEN was met, or it was
> closed expired/terminal; the goal file + its PROGRESS LOG/HONEST STATE remain the
> permanent audit trail, never deleted).
>
> Eligibility (checked at open time, never assumed from this line alone): the
> entry's `file:` must exist AND contain both a `## DONE-WHEN` heading and a
> `## QUEUE` section with at least one bare `- [ ] ` item. An entry that fails
> this check is SKIPPED (logged in goal-autopilot.json/.jsonl) and never opened --
> the autopilot walks past it to the next `[ ]` line rather than opening a goal
> with nothing left to do.
>
> Author new entries by appending a line (Claude sessions or J). Never delete a
> `[x]` line -- it is the ladder's own history.

"""


# ============================================================================
# Small pure helpers -- exercised directly by tests, no IO.
# ============================================================================

def is_market_hours_et(now_et: dt.datetime) -> bool:
    """Mon-Fri 09:30 <= ET < 15:55 -- same window as et_clock.is_market_hours,
    applied to an already-resolved ET datetime (so `--now` tests are deterministic
    without needing to fabricate a matching UTC instant)."""
    if now_et.weekday() >= 5:
        return False
    hhmm = now_et.hour * 100 + now_et.minute
    return 930 <= hhmm < 1555


def parse_ladder(text: str) -> list[dict]:
    """Every LADDER.md entry, in file order. Non-matching lines (headers,
    blank lines, prose) are silently skipped -- this is a permissive line
    scanner, not a strict-format validator (the header comment above documents
    the format for humans; this just extracts what matches)."""
    out = []
    for i, line in enumerate(text.splitlines()):
        m = _LADDER_LINE.match(line)
        if not m:
            continue
        marker, goal_id, desc, file_rel, expires_days, not_before = m.groups()
        out.append({
            "line_index": i,
            "marker": marker,
            "id": goal_id,
            "desc": desc,
            "file": file_rel,
            "expires_days": int(expires_days),
            "not_before": not_before,
        })
    return out


_QUEUE_MARKER_LINE = re.compile(r"^-\s*\[(x| |~|B|B-J)\]")


def queue_markers(goal_md: Optional[str]) -> list[str]:
    """Every QUEUE item marker, in file order, from the literal `## QUEUE`
    section only (scanning stops at the next `## ` heading). Distinct from
    `doctrine.goal_next_open_item`, which only reports bare `[ ]` items --
    this collects ALL markers so `goal_is_terminal` can tell "nothing
    assignable right now" ([~] wip owned by a running session) apart from
    "nothing left to do, ever" (every item closed or blocked)."""
    markers: list[str] = []
    in_queue = False
    for line in (goal_md or "").splitlines():
        if line.startswith("## "):
            in_queue = line[3:].strip().upper().startswith("QUEUE")
            continue
        if not in_queue:
            continue
        m = _QUEUE_MARKER_LINE.match(line)
        if m:
            markers.append(m.group(1))
    return markers


def goal_is_terminal(goal_md: Optional[str]) -> bool:
    """True only when EVERY QUEUE item's marker is `x`/`B`/`B-J` -- i.e.
    there is nothing left to do, ever, not even a wip item some other
    session owns. A `[~]` (in-progress) or a bare `[ ]` (open, just not
    handed out to THIS fire) both keep the goal OPEN. An empty QUEUE (no
    recognized markers at all) is NOT terminal -- that is a schema
    violation to skip past, never a false "done".

    Root cause this replaces (BUG found live 2026-09-04 01:19 ET): the old
    close-if-terminal path treated "doctrine.goal_next_open_item returned
    None" as "finished", but that function deliberately skips `[~]` items
    too (a fire must never steal a wip item) -- so a goal with three `[~]`
    rows and zero bare `[ ]` rows looked "fully terminal" and got closed out
    from under the session that owned them. "No assignable item" is not the
    same claim as "no open item"; this function answers the second question.
    """
    markers = queue_markers(goal_md)
    if not markers:
        return False
    return all(m in ("x", "B", "B-J") for m in markers)


def not_before_blocks(entry: dict, now_et: dt.datetime) -> Optional[str]:
    """Reason string when the ladder entry's `not_before:` date has not arrived (ET
    calendar date compare), else None. A malformed date never blocks (fail-open, C7)."""
    raw = entry.get("not_before")
    if not raw:
        return None
    try:
        gate = dt.date.fromisoformat(str(raw))
    except ValueError:
        return None
    if now_et.date() < gate:
        return f"not before {gate.isoformat()} (today {now_et.date().isoformat()})"
    return None


def goal_file_eligible(text: Optional[str]) -> tuple[bool, str, Optional[str]]:
    """(eligible, reason, next_open_item). `text` is None when the file is
    missing. Eligible requires BOTH a `## DONE-WHEN` heading present AND a
    `## QUEUE` section with >=1 bare `- [ ] ` item (goal_next_open_item
    returning non-None IS that check -- reused, not re-derived)."""
    if text is None:
        return False, "missing file", None
    has_done_when = any(
        (h := _HEADING_LINE.match(line)) and h.group(1).strip().upper().startswith("DONE-WHEN")
        for line in text.splitlines()
    )
    item = D.goal_next_open_item(text)
    if not has_done_when:
        return False, "missing ## DONE-WHEN section", None
    if not item:
        return False, "no ## QUEUE section or no bare '- [ ] ' item", None
    return True, "ok", item


def flip_ladder_marker(text: str, goal_id: str, new_marker: str) -> str:
    """Replace the `[X]` marker on the ONE ladder line for goal_id. No-op
    (returns text unchanged) if the id isn't found -- callers check the return
    value against the input to detect a miss."""
    out_lines = []
    changed = False
    for line in text.splitlines():
        m = _LADDER_LINE.match(line)
        if m and m.group(2) == goal_id and not changed:
            tail = f" :: not_before:{m.group(6)}" if m.group(6) else ""
            out_lines.append(f"- [{new_marker}] {m.group(2)} :: {m.group(3)} :: file: {m.group(4)} :: expires_days:{m.group(5)}{tail}")
            changed = True
        else:
            out_lines.append(line)
    result = "\n".join(out_lines)
    if text.endswith("\n") and not result.endswith("\n"):
        result += "\n"
    return result


def append_under_heading(text: str, heading_prefix: str, new_block: str) -> str:
    """Insert `new_block` as the LAST content of the section whose heading's
    normalized text starts with `heading_prefix` (case-insensitive) -- i.e.
    right before the NEXT heading, or at EOF if it's the last section. If the
    heading isn't found at all, appends a new section at EOF (defensive; every
    goal file built to schema always has both PROGRESS LOG and HONEST STATE)."""
    lines = text.splitlines()
    start = None
    end = len(lines)
    for i, line in enumerate(lines):
        h = _HEADING_LINE.match(line)
        if h:
            name = h.group(1).strip().upper()
            if start is None and name.startswith(heading_prefix.upper()):
                start = i
                continue
            if start is not None:
                end = i
                break
    if start is None:
        # Defensive fallback -- schema violation, but never crash over it.
        tail = text if text.endswith("\n") else text + "\n"
        return tail + f"\n## {heading_prefix}\n{new_block}\n"
    insertion = lines[:end]
    # Trim trailing blank lines inside the section so the appended block
    # doesn't accumulate a growing gap on repeated runs.
    while insertion and insertion[-1].strip() == "" and len(insertion) > start + 1:
        insertion.pop()
    insertion.append(new_block)
    rest = lines[end:]
    result = "\n".join(insertion + rest)
    if text.endswith("\n"):
        result += "\n"
    return result


_QUEUE_ROW_STATUS = re.compile(r"status:\S+")


def flip_queue_row_status(text: str, goal_id: str, new_status: str) -> tuple[str, bool]:
    """Replace the LAST `status:<...>` token on the ONE queue.md line naming
    `goal_id`, in place -- matches task_scorer.py's `_extract_field_last`
    "last match on the line wins" scan, and never adds a second `status:`
    field (queue.md rows for a goal are single-line by the skill's own
    grammar). Returns (new_text, found)."""
    out_lines = []
    found = False
    needle = f"{goal_id} ("
    for line in text.splitlines():
        if not found and needle in line and line.lstrip().startswith("- ["):
            matches = list(_QUEUE_ROW_STATUS.finditer(line))
            if matches:
                last = matches[-1]
                line = line[: last.start()] + f"status:{new_status}" + line[last.end():]
                found = True
        out_lines.append(line)
    result = "\n".join(out_lines)
    if text.endswith("\n"):
        result += "\n"
    return result, found


def ensure_queue_row(text: str, goal_id: str, row_line: str) -> tuple[str, bool]:
    """Insert `row_line` under `## Active backlog`, right after the heading's
    own leading blockquote (`> `) lines, UNLESS a row for `goal_id` already
    exists anywhere in the file. Returns (new_text, inserted)."""
    if f"{goal_id} (" in text:
        return text, False
    lines = text.splitlines()
    heading_idx = None
    for i, line in enumerate(lines):
        h = _HEADING_LINE.match(line)
        if h and h.group(1).strip().upper().startswith("ACTIVE BACKLOG"):
            heading_idx = i
            break
    if heading_idx is None:
        # Defensive: no such heading -- append one at EOF rather than silently
        # dropping the row (should not happen; queue.md always has this section).
        tail = text if text.endswith("\n") else text + "\n"
        return tail + f"\n## Active backlog\n{row_line}\n", True
    insert_at = heading_idx + 1
    while insert_at < len(lines) and lines[insert_at].lstrip().startswith(">"):
        insert_at += 1
    new_lines = lines[:insert_at] + [row_line] + lines[insert_at:]
    result = "\n".join(new_lines)
    if text.endswith("\n"):
        result += "\n"
    return result, True


def queue_row_grammar(goal_id: str, one_line: str, file_rel: str) -> str:
    return f"- [ ] {goal_id} (HIGH, goal) :: {one_line} -- file: {file_rel} :: depends:none :: status:in_progress"


# ============================================================================
# IO layer -- everything below touches disk. Paths are all derived from `repo`
# so tests can point this at a throwaway tmp_path tree.
# ============================================================================

class Paths:
    def __init__(self, repo: Path):
        self.repo = repo
        self.state = repo / "automation" / "state"
        self.goals_dir = self.state / "goals"
        self.ladder = self.goals_dir / "LADDER.md"
        self.active_goal = self.state / "active-goal.json"
        self.queue_md = repo / "automation" / "overnight" / "queue.md"
        self.status_json = self.state / "goal-autopilot.json"
        self.log_jsonl = self.state / "goal-autopilot.jsonl"


def _read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path) -> Optional[dict]:
    txt = _read_text(path)
    if txt is None:
        return None
    try:
        obj = json.loads(txt)
    except (ValueError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


def _write_json(path: Path, obj: dict) -> None:
    _atomic_write(path, json.dumps(obj, indent=2, sort_keys=False) + "\n")


def _iso(now_et: dt.datetime) -> str:
    return now_et.strftime("%Y-%m-%dT%H:%M:%S")


def _human(now_et: dt.datetime) -> str:
    return now_et.strftime("%Y-%m-%d %H:%M ET")


class Autopilot:
    """One `ensure`/`close-if-terminal`/`status` run. Every disk write is
    gated on `self.write` so --dry-run only ever computes and prints the plan."""

    def __init__(self, paths: Paths, now_et: dt.datetime, write: bool):
        self.p = paths
        self.now_et = now_et
        self.write = write
        self.events: list[str] = []

    # -- reads -----------------------------------------------------------
    def _read_active_goal(self) -> Optional[dict]:
        return _read_json(self.p.active_goal)

    def _read_goal_text(self, file_rel: str) -> Optional[str]:
        return _read_text(self.p.repo / file_rel)

    def _read_ladder(self) -> str:
        txt = _read_text(self.p.ladder)
        return txt if txt is not None else ""

    # -- close -------------------------------------------------------------
    def _close(self, active: dict, reason: str) -> str:
        goal_id = str(active.get("id") or "")
        file_rel = str(active.get("file") or "")
        ts = _human(self.now_et)
        progress_line = f"- {ts} — closed by goal_autopilot: {reason}"
        honest_para = f"AUTOPILOT CLOSE {ts}: {reason}"
        goal_text = self._read_goal_text(file_rel) if file_rel else None
        if goal_text is not None:
            new_text = append_under_heading(goal_text, "PROGRESS LOG", progress_line)
            new_text = append_under_heading(new_text, "HONEST STATE", honest_para)
            if self.write:
                _atomic_write(self.p.repo / file_rel, new_text)

        new_active = dict(active)
        new_active["active"] = False
        new_active["closed_at_et"] = ts
        new_active["closed_reason"] = reason
        if self.write:
            _write_json(self.p.active_goal, new_active)

        ladder_text = self._read_ladder()
        flipped = flip_ladder_marker(ladder_text, goal_id, "x")
        if self.write and flipped != ladder_text:
            _atomic_write(self.p.ladder, flipped)

        q_status = "expired" if reason == "expired" else "done"
        queue_text = _read_text(self.p.queue_md)
        if queue_text is not None:
            new_queue, found = flip_queue_row_status(queue_text, goal_id, q_status)
            if self.write and found:
                _atomic_write(self.p.queue_md, new_queue)
            if not found:
                self.events.append(f"WARN: no queue.md row found for {goal_id} to flip")
        self.events.append(f"closed {goal_id}: {reason}")
        return goal_id

    # -- open --------------------------------------------------------------
    def _open_next(self) -> Optional[dict]:
        ladder_text = self._read_ladder()
        entries = parse_ladder(ladder_text)
        for entry in entries:
            if entry["marker"] != " ":
                continue
            goal_text = self._read_goal_text(entry["file"])
            eligible, reason, item = goal_file_eligible(goal_text)
            gated = not_before_blocks(entry, self.now_et)
            if eligible and gated:
                eligible, reason = False, gated
            if not eligible:
                self.events.append(f"skipped {entry['id']}: {reason}")
                continue

            ts_iso = _iso(self.now_et)
            expires_date = (self.now_et.date() + dt.timedelta(days=entry["expires_days"])).isoformat()
            new_active = {
                "id": entry["id"],
                "active": True,
                "opened_at_et": ts_iso,
                "expires_at_et": expires_date,
                "file": entry["file"],
                "queue_id": entry["id"],
                "max_continuations_per_session": DEFAULT_MAX_CONTINUATIONS,
                "last_next_item": None,
            }
            if self.write:
                _write_json(self.p.active_goal, new_active)

            new_ladder = flip_ladder_marker(ladder_text, entry["id"], "~")
            if self.write and new_ladder != ladder_text:
                _atomic_write(self.p.ladder, new_ladder)

            progress_line = f"- {_human(self.now_et)} — opened by goal_autopilot"
            new_goal_text = append_under_heading(goal_text, "PROGRESS LOG", progress_line)
            if self.write:
                _atomic_write(self.p.repo / entry["file"], new_goal_text)

            queue_text = _read_text(self.p.queue_md)
            if queue_text is not None:
                row = queue_row_grammar(entry["id"], entry["desc"], entry["file"])
                new_queue, inserted = ensure_queue_row(queue_text, entry["id"], row)
                if self.write and inserted:
                    _atomic_write(self.p.queue_md, new_queue)

            self.events.append(f"opened {entry['id']}")
            return {"id": entry["id"], "item": item}
        return None

    def ladder_status(self) -> list[dict]:
        ladder_text = self._read_ladder()
        entries = parse_ladder(ladder_text)
        out = []
        state_name = {" ": "queued", "~": "active", "x": "done"}
        for entry in entries:
            goal_text = self._read_goal_text(entry["file"])
            eligible, reason, _item = goal_file_eligible(goal_text)
            gated = not_before_blocks(entry, self.now_et)
            if eligible and gated:
                eligible, reason = False, gated
            out.append({
                "id": entry["id"],
                "state": state_name.get(entry["marker"], "unknown"),
                "eligible": eligible,
                "why": reason,
            })
        return out

    # -- top level -----------------------------------------------------------
    def ensure(self) -> dict:
        active = self._read_active_goal()
        closed_id = None
        opened_id = None
        opened_item = None
        action = "noop"
        reason = ""
        # True whenever there is no CURRENTLY-good active goal after this block --
        # i.e. we should attempt to open the next ladder entry. Starts True: a
        # missing/inactive active-goal.json means "nothing active", not "noop".
        attempt_open = True

        if active and active.get("active") is True:
            file_rel = str(active.get("file") or "")
            text = self._read_goal_text(file_rel) if file_rel else None
            expired = D.goal_expired(active.get("expires_at_et"), self.now_et)
            item = D.goal_next_open_item(text) if text is not None else None
            if not expired and item:
                action = "noop"
                opened_item = item
                reason = "active goal has an open item"
                attempt_open = False
            elif not expired and text is not None and not goal_is_terminal(text):
                # Nothing bare-open to hand a NEW fire, but the goal is not
                # finished -- at least one QUEUE item is still `[~]` (wip,
                # owned by a running session). Must noop, not close: closing
                # here is exactly the 2026-09-04 01:19 ET bug.
                action = "noop"
                opened_item = None
                reason = "active goal has in-progress items (no assignable item)"
                attempt_open = False
            else:
                if expired:
                    close_reason = "expired"
                elif text is None:
                    close_reason = "goal file missing"
                else:
                    close_reason = "queue fully terminal (no bare '- [ ] ' item left)"
                closed_id = self._close(active, close_reason)
                action = "closed"
                reason = close_reason
                active = None
                attempt_open = True

        if attempt_open:
            opened = self._open_next()
            if opened:
                opened_id = opened["id"]
                opened_item = opened["item"]
                action = "closed_opened" if closed_id else "opened"
                reason = reason or "opened next eligible ladder entry"
            else:
                action = "closed_ladder_empty" if closed_id else "ladder_empty"
                reason = "no eligible queued ladder entry" if not closed_id else reason

        active_goal_id = opened_id or (active.get("id") if active else None)
        result = {
            "checked_at_et": _human(self.now_et),
            "action": action,
            "reason": reason,
            "active_goal_id": active_goal_id,
            "next_item": opened_item,
            "ladder": self.ladder_status(),
            "last_opened": None,
            "last_closed": None,
            "error": None,
            "closed_id": closed_id,
            "opened_id": opened_id,
        }
        return result

    def close_if_terminal(self) -> dict:
        active = self._read_active_goal()
        if not (active and active.get("active") is True):
            return {
                "checked_at_et": _human(self.now_et), "action": "noop",
                "reason": "no active goal", "active_goal_id": None, "next_item": None,
                "ladder": self.ladder_status(), "last_opened": None, "last_closed": None,
                "error": None, "closed_id": None, "opened_id": None,
            }
        file_rel = str(active.get("file") or "")
        text = self._read_goal_text(file_rel) if file_rel else None
        expired = D.goal_expired(active.get("expires_at_et"), self.now_et)
        item = D.goal_next_open_item(text) if text is not None else None
        if not expired and item:
            return {
                "checked_at_et": _human(self.now_et), "action": "noop",
                "reason": "active goal has an open item", "active_goal_id": active.get("id"),
                "next_item": item, "ladder": self.ladder_status(),
                "last_opened": None, "last_closed": None, "error": None,
                "closed_id": None, "opened_id": None,
            }
        if not expired and text is not None and not goal_is_terminal(text):
            return {
                "checked_at_et": _human(self.now_et), "action": "noop",
                "reason": "active goal has in-progress items (no assignable item)",
                "active_goal_id": active.get("id"), "next_item": None,
                "ladder": self.ladder_status(), "last_opened": None, "last_closed": None,
                "error": None, "closed_id": None, "opened_id": None,
            }
        close_reason = "expired" if expired else ("goal file missing" if text is None else "queue fully terminal (no bare '- [ ] ' item left)")
        closed_id = self._close(active, close_reason)
        return {
            "checked_at_et": _human(self.now_et), "action": "closed",
            "reason": close_reason, "active_goal_id": None, "next_item": None,
            "ladder": self.ladder_status(), "last_opened": None, "last_closed": closed_id,
            "error": None, "closed_id": closed_id, "opened_id": None,
        }


def _merge_last_opened_closed(paths: Paths, result: dict, write: bool) -> dict:
    """last_opened/last_closed persist across runs (most fires are noop) --
    carry forward the prior status.json's values unless THIS run produced a
    fresh open/close event."""
    prev = _read_json(paths.status_json) or {}
    result["last_opened"] = result.get("opened_id") or prev.get("last_opened")
    result["last_closed"] = result.get("closed_id") or prev.get("last_closed")
    result.pop("closed_id", None)
    result.pop("opened_id", None)
    return result


def _write_status_and_log(paths: Paths, result: dict, write: bool) -> None:
    if not write:
        return
    _write_json(paths.status_json, result)
    paths.state.mkdir(parents=True, exist_ok=True)
    row = {
        "ts_et": result["checked_at_et"], "action": result["action"],
        "reason": result["reason"], "active_goal_id": result["active_goal_id"],
    }
    with paths.log_jsonl.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def cmd_ensure(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve() if args.repo else _DEFAULT_REPO
    paths = Paths(repo)
    now_et = _resolve_now(args)

    if is_market_hours_et(now_et):
        print("skip_rth")
        return 0

    try:
        ap = Autopilot(paths, now_et, write=not args.dry_run)
        result = ap.ensure()
        result = _merge_last_opened_closed(paths, result, write=not args.dry_run)
        _write_status_and_log(paths, result, write=not args.dry_run)
        print(f"{result['action']}: {result['reason']}")
        if args.dry_run:
            print("(dry-run -- no files written)")
            for ev in ap.events:
                print(f"  would: {ev}")
        return 0
    except Exception as exc:  # noqa: BLE001 -- fail-open is the whole point
        msg = f"error: {exc}"
        print(msg)
        if args.strict:
            raise
        try:
            _write_json(paths.status_json, {
                "checked_at_et": _human(now_et), "action": "error", "reason": str(exc),
                "active_goal_id": None, "next_item": None, "ladder": [],
                "last_opened": None, "last_closed": None, "error": str(exc),
            })
        except Exception:
            pass
        return 0


def cmd_close_if_terminal(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve() if args.repo else _DEFAULT_REPO
    paths = Paths(repo)
    now_et = _resolve_now(args)
    try:
        ap = Autopilot(paths, now_et, write=not args.dry_run)
        result = ap.close_if_terminal()
        result = _merge_last_opened_closed(paths, result, write=not args.dry_run)
        _write_status_and_log(paths, result, write=not args.dry_run)
        print(f"{result['action']}: {result['reason']}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}")
        if args.strict:
            raise
        return 0


def cmd_status(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve() if args.repo else _DEFAULT_REPO
    paths = Paths(repo)
    status = _read_json(paths.status_json)
    if status is None:
        status = {"error": "NO DATA -- goal-autopilot.json has not been written yet"}
    if args.json:
        print(json.dumps(status, indent=2))
    else:
        print(f"action: {status.get('action')}  reason: {status.get('reason')}")
        print(f"active_goal_id: {status.get('active_goal_id')}  next_item: {status.get('next_item')}")
        for row in status.get("ladder", []):
            print(f"  {row.get('id')}: {row.get('state')} eligible={row.get('eligible')} ({row.get('why')})")
    return 0


def _resolve_now(args: argparse.Namespace) -> dt.datetime:
    if args.now:
        raw = args.now
        try:
            return dt.datetime.fromisoformat(raw)
        except ValueError as exc:
            raise ValueError(f"--now must be an ISO datetime, got {raw!r}") from exc
    return et_now()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", nargs="?", default="ensure",
                        choices=["ensure", "status", "close-if-terminal"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--now", default=None, help="ISO ET datetime override (tests only)")
    parser.add_argument("--repo", default=None, help="Repo root override (tests only)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true",
                        help="Re-raise instead of failing open (tests only)")
    args = parser.parse_args(argv)

    if args.command == "ensure":
        return cmd_ensure(args)
    if args.command == "close-if-terminal":
        return cmd_close_if_terminal(args)
    return cmd_status(args)


if __name__ == "__main__":
    raise SystemExit(main())

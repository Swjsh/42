"""Discord responder -- the async approve/revoke bus + away-from-keyboard Q&A.

Runs after-hours via Gamma_DiscordResponder (wire-don't-auto-enable). Two jobs:

  1. APPROVE/REVOKE BUS (primary):
     The Conductor (Gamma_Conductor) stages doctrine/params/order proposals it is
     NOT allowed to auto-apply (reward-hacking guard) as rows in
     `automation/state/conductor-proposals.jsonl` and pings J via the outbox.
     J replies "ship <proposal_id>" / "shelve <proposal_id>" (or thumbs-up/down +
     the id) from his phone. This responder consumes those inbox replies, flips the
     proposal row status -> approved / shelved, appends an audit row to
     `automation/state/conductor-approvals.jsonl`, and acks J in one line.
     It does NOT itself edit params/heartbeat/CLAUDE.md or place orders -- approval
     is recorded; applying the trading-surface change stays a J-gated step. The
     responder is the *bus*, not the actuator.

  2. FREE-FORM Q&A (secondary): a non-approval message from J gets a concise
     `claude --print` reply (Haiku, cheap) so J can ask "status?" while away.

Flow each tick:
  - AFTER-HOURS GATE first (L54): if market is open (weekday 09:30-15:55 ET) we do
    NOT spawn any Claude model -- a market-hours responder fan-out competes with
    Gamma_Heartbeat on the shared Max rate-limit pool. Approval parsing is pure
    Python ($0) so we STILL process ship/shelve commands during RTH; only the
    LLM-backed free-form Q&A is deferred until after-hours.
  - Read discord-inbox.jsonl, find messages newer than the watermark, from J.
  - For each: try to parse an approve/revoke command (pure Python). If it matches a
    pending proposal, resolve it. Otherwise (after-hours only) answer via Haiku.
  - Update the watermark.

Per CLAUDE.md OP-18 / OP-25 (autonomous, async-approver model) + L54 (rate-limit
pool discipline). FAIL-OPEN: this responder never blocks or kills J's session.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import re
import shutil
import subprocess
import sys
from datetime import timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE_DIR = REPO / "automation" / "state"
INBOX = STATE_DIR / "discord-inbox.jsonl"
OUTBOX = STATE_DIR / "discord-outbox.jsonl"
WATERMARK = STATE_DIR / ".discord-responder-watermark.json"
LOGFILE = STATE_DIR / "logs" / "discord-responder.log"
QUEUE = STATE_DIR / "research-queue.json"
CFG = STATE_DIR / ".discord-config.json"
PROPOSALS = STATE_DIR / "conductor-proposals.jsonl"
APPROVALS = STATE_DIR / "conductor-approvals.jsonl"

LOGFILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(LOGFILE),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


# ---------------------------------------------------------------------------
# ET / market-hours gate (copied from engine_health.py convention -- system
# Python on this host lacks tzdata, so we compute the US offset by hand). L54:
# never spawn a market-hours LLM that starves Gamma_Heartbeat.
# ---------------------------------------------------------------------------

def _et_offset_hours(dt_utc: dt.datetime) -> int:
    """EDT (UTC-4) 2nd Sun Mar 02:00 .. 1st Sun Nov 02:00 local; EST (UTC-5) else."""
    y = dt_utc.year
    march = dt.datetime(y, 3, 1, tzinfo=timezone.utc)
    days_to_sun = (6 - march.weekday()) % 7
    dst_start = (march + timedelta(days=days_to_sun + 7)).replace(hour=7)
    nov = dt.datetime(y, 11, 1, tzinfo=timezone.utc)
    days_to_sun = (6 - nov.weekday()) % 7
    dst_end = (nov + timedelta(days=days_to_sun)).replace(hour=6)
    return -4 if (dst_start <= dt_utc < dst_end) else -5


def _et_now() -> dt.datetime:
    now_utc = dt.datetime.now(timezone.utc)
    return (now_utc + timedelta(hours=_et_offset_hours(now_utc))).replace(tzinfo=None)


def _load_holidays() -> set:
    cal = STATE_DIR / "calendar.json"
    try:
        data = json.loads(cal.read_text(encoding="utf-8"))
        return {str(d) for d in data.get("holidays", [])}
    except Exception:
        return set()


def market_is_open(et: dt.datetime | None = None) -> bool:
    """True during RTH: Mon-Fri, 09:30 <= ET < 15:55, not a known holiday."""
    et = et or _et_now()
    if et.weekday() >= 5:
        return False
    if et.strftime("%Y-%m-%d") in _load_holidays():
        return False
    hhmm = et.hour * 100 + et.minute
    return 930 <= hhmm < 1555


# ---------------------------------------------------------------------------
# Watermark / config / inbox / outbox
# ---------------------------------------------------------------------------

def _load_watermark() -> str:
    if not WATERMARK.exists():
        return ""
    try:
        return json.loads(WATERMARK.read_text(encoding="utf-8")).get("last_msg_id", "")
    except Exception:
        return ""


def _save_watermark(msg_id: str) -> None:
    WATERMARK.write_text(json.dumps({"last_msg_id": msg_id}), encoding="utf-8")


def _load_user_id() -> str:
    if not CFG.exists():
        return ""
    try:
        return json.loads(CFG.read_text(encoding="utf-8-sig")).get("user_id", "")
    except Exception:
        return ""


def _read_inbox() -> list[dict]:
    if not INBOX.exists():
        return []
    rows = []
    for line in INBOX.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def _queue_outbox(content: str, mention_user_id: str) -> None:
    prefix = f"<@{mention_user_id}> " if mention_user_id else ""
    row = {
        "queued_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "content": prefix + content,
    }
    with OUTBOX.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


# ---------------------------------------------------------------------------
# Approve / revoke protocol (pure Python -- $0, runs even during RTH)
# ---------------------------------------------------------------------------

# A proposal id looks like "gp-2026-06-18-001" (conductor-issued). We accept any
# token of the shape <letters>-<digits/-dashes> so the conductor can evolve the
# scheme; the id MUST match a pending row to act.
_PROPOSAL_ID_RE = re.compile(r"\b([a-zA-Z]{1,6}-[0-9][0-9A-Za-z\-]{4,})\b")

# Intent vocab. Two flavors:
#  * WORD verbs matched on WORD BOUNDARIES (\b...\b) so they don't collide with
#    characters inside a proposal id or a date (the "-1 inside gp-...-18-001" bug).
#  * REACTION tokens (emoji / :shortcode: / +1 / -1) matched literally, but ONLY
#    AFTER any recognized proposal id has been stripped from the text, so "+1"/"-1"
#    can't false-match digits inside an id.
_SHIP_WORDS = ("ship", "approve", "approved", "go", "yes", "ok", "okay", "yep")
_SHELVE_WORDS = ("shelve", "shelf", "reject", "rejected", "drop", "skip", "kill", "nope")
# REVERT verbs -- J's one-tap off-switch for an already-APPLIED autonomous change.
_REVERT_WORDS = ("revert", "undo", "rollback")
# Reactions are matched literally on the id-stripped text. We deliberately do NOT
# include bare "+1"/"-1" (they collide with digits/dashes inside ids and dates);
# the unicode thumbs + :shortcode: forms cover Discord reactions unambiguously.
_SHIP_REACTIONS = ("\U0001F44D", ":thumbsup:", ":+1:")
_SHELVE_REACTIONS = ("\U0001F44E", ":thumbsdown:", ":-1:")
_WORD_RE = re.compile(r"[a-z][a-z']*")


def _read_proposals() -> list[dict]:
    if not PROPOSALS.exists():
        return []
    rows = []
    for line in PROPOSALS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def _rewrite_proposals(rows: list[dict]) -> None:
    """Atomic rewrite of the proposals ledger (status flips are in-place edits)."""
    tmp = PROPOSALS.with_suffix(PROPOSALS.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    tmp.replace(PROPOSALS)


def _append_approval(row: dict) -> None:
    with APPROVALS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _pending_by_id(rows: list[dict]) -> dict[str, dict]:
    return {r.get("proposal_id"): r for r in rows if r.get("status") == "pending"}


def _classify_command(text: str) -> str | None:
    """Return 'ship' | 'shelve' | None for the intent in a message (case-insensitive).

    Robust against proposal-id collisions: any recognized proposal id (e.g.
    gp-2026-06-18-001) is stripped BEFORE matching, and word-verbs are matched on
    word boundaries -- so "ship gp-2026-06-18-001" is unambiguously 'ship' even
    though the id contains the substring "-1". Returns None on ambiguity (both
    intents present) or no intent.
    """
    low = text.lower()
    stripped = _PROPOSAL_ID_RE.sub(" ", low)  # remove ids so reactions can't false-match
    words = set(_WORD_RE.findall(stripped))
    has_ship = bool(words & set(_SHIP_WORDS)) or any(r in stripped for r in _SHIP_REACTIONS)
    has_shelve = bool(words & set(_SHELVE_WORDS)) or any(r in stripped for r in _SHELVE_REACTIONS)
    if has_ship and not has_shelve:
        return "ship"
    if has_shelve and not has_ship:
        return "shelve"
    # Ambiguous or neither -> not a command.
    return None


def _try_resolve_proposal(content: str, user_id: str) -> bool:
    """If `content` is an approve/revoke command targeting a pending proposal,
    resolve it (flip status, append audit row, ack J) and return True. Else False.

    Resolution rules (conservative -- never act on ambiguity):
      * The message must contain a proposal id that matches a PENDING row, AND a
        clear ship/shelve intent. A bare "ship" with no id, or an id with no clear
        verb, is NOT acted on (we don't guess which proposal).
      * Exactly one pending proposal + a bare ship/shelve verb -> act on that one
        (common case: J replies "ship" to the only open ask).
    """
    rows = _read_proposals()
    pending = _pending_by_id(rows)
    if not pending:
        return False

    intent = _classify_command(content)
    if intent is None:
        return False

    # Find a referenced id that matches a pending proposal.
    target_id = None
    for m in _PROPOSAL_ID_RE.finditer(content):
        cand = m.group(1)
        if cand in pending:
            target_id = cand
            break
    # Bare verb + exactly one open proposal -> unambiguous.
    if target_id is None and len(pending) == 1:
        target_id = next(iter(pending))
    if target_id is None:
        return False  # verb but ambiguous id -> let it fall through to Q&A/no-op

    new_status = "approved" if intent == "ship" else "shelved"
    for r in rows:
        if r.get("proposal_id") == target_id and r.get("status") == "pending":
            r["status"] = new_status
            r["resolved_at"] = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
            r["resolved_by"] = user_id or "j"
            break
    _rewrite_proposals(rows)

    target = pending[target_id]
    _append_approval({
        "resolved_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "proposal_id": target_id,
        "decision": new_status,
        "title": target.get("title", ""),
        "kind": target.get("kind", ""),
        "draft_path": target.get("draft_path", ""),
        "by": user_id or "j",
    })
    logging.info("proposal %s -> %s", target_id, new_status)

    if new_status == "approved":
        ack = (
            f"{target_id} approved \U0001F7E2 ({target.get('title','')}). "
            f"AutoApply will apply + commit it after-hours (safety-gated, snapshot-backed; "
            f"structured edits only). Reply 'revert {target_id}' any time to undo."
        )
    else:
        ack = f"{target_id} shelved. ({target.get('title','')}). Dropped, no change. Next."
    _queue_outbox(ack, user_id)
    return True


def _applied_by_id(rows: list[dict]) -> dict[str, dict]:
    return {r.get("proposal_id"): r for r in rows if r.get("status") == "applied"}


def _try_revert(content: str, user_id: str) -> bool:
    """If `content` is a 'revert <id>' command targeting an APPLIED proposal, hand it to
    the actuator (which restores the pre-apply snapshot + commits the revert) and ack J.
    J's explicit off-switch -- allowed any time (an undo is a safety action, not a new
    mid-session change). Pure dispatch; the actuator does the git work. Returns True if handled."""
    low = content.lower()
    stripped = _PROPOSAL_ID_RE.sub(" ", low)
    words = set(_WORD_RE.findall(stripped))
    if not (words & set(_REVERT_WORDS)):
        return False
    rows = _read_proposals()
    applied = _applied_by_id(rows)
    if not applied:
        return False
    target_id = None
    for m in _PROPOSAL_ID_RE.finditer(content):
        if m.group(1) in applied:
            target_id = m.group(1)
            break
    if target_id is None and len(applied) == 1:
        target_id = next(iter(applied))
    if target_id is None:
        return False  # revert verb but ambiguous id -> don't guess

    actuator = REPO / "setup" / "scripts" / "autonomy_actuator.py"
    try:
        res = subprocess.run(
            [sys.executable, str(actuator), "revert", target_id],
            capture_output=True, text=True, timeout=120, cwd=str(REPO),
        )
        ok = res.returncode == 0
        last = ((res.stdout or "") + (res.stderr or "")).strip().splitlines()
        tail = last[-1] if last else ""
        msg = (f"{target_id} reverted ↩ -- restored to the pre-apply state + committed."
               if ok else f"{target_id} revert FAILED: {tail[:160]}")
    except Exception as exc:
        msg = f"{target_id} revert error: {exc}"
    _queue_outbox(msg, user_id)
    logging.info("revert %s ok-dispatch", target_id)
    return True


# ---------------------------------------------------------------------------
# Correction capture -- inline self-learning parity with the terminal hook
# (setup/hook-detect-correction.ps1). J's Discord corrections ("stop doing X",
# "that's wrong", "do it this way") are appended to the SAME skill-learning queue
# the terminal hook writes, so skill-author Stage 0 triages terminal + Discord
# corrections uniformly. Pure Python ($0), fail-open, runs even during RTH (no
# LLM). CAPTURE-ONLY -- all judgment + Rule-9 routing happen in skill-author.
# ---------------------------------------------------------------------------

CORRECTION_QUEUE = REPO / "strategy" / "candidates" / "_skill-inbox" / "_correction-queue.jsonl"
SKILLS_DIR = REPO / ".claude" / "skills"

# Same high-precision phrases as the PowerShell hook (low false-positive set).
_CORRECTION_PATTERNS = [
    r"stop doing", r"quit doing", r"stop trying to", r"stop being",
    r"don'?t do that", r"don'?t ever", r"never do that", r"never say that",
    r"you('?re| are) wrong", r"that'?s wrong", r"that'?s incorrect",
    r"you got (that|it) wrong", r"do it this way", r"do this instead",
    r"instead of (doing|that)", r"you should(n'?t| not) have", r"you should have",
    r"that'?s not what i", r"not what i asked", r"i (told|said) you",
    r"next time,? (don'?t|do)",
]
_CORRECTION_RE = [re.compile(p) for p in _CORRECTION_PATTERNS]
# Trading jargon stripped BEFORE matching ("stop loss" is not a correction).
_JARGON_RE = re.compile(r"stop[\s\-]?loss|stop(ped)?\s+out|stop[\s\-]?out")
# Rule-9 live-doctrine denylist tags (capture-only; skill-author enforces the gate).
_CORRECTION_DENYLIST = (
    "heartbeat-pulse-check", "heartbeat-decision-trace", "pin-chain-verify",
    "heartbeat", "params", "risk_gate", "kill switch", "kill-switch",
)


def _detect_correction(text: str) -> str | None:
    """Return the matched correction phrase, or None. Jargon-excluded, low false-positive."""
    scan = _JARGON_RE.sub("", text.lower())
    for rx in _CORRECTION_RE:
        m = rx.search(scan)
        if m:
            return m.group(0)
    return None


def _skills_named(low: str) -> list[str]:
    """Coarse attribution: which skill dir names appear in the message (skill-author refines)."""
    out: list[str] = []
    if SKILLS_DIR.exists():
        for d in SKILLS_DIR.iterdir():
            if d.is_dir() and d.name.lower() in low:
                out.append(d.name)
    return out


def _capture_correction(content: str) -> bool:
    """If J's Discord message is a correction, append it to the skill-learning queue.
    Pure Python ($0), fail-open. Returns True if captured. Does NOT consume the message
    (the caller still processes revert/approve/Q&A normally)."""
    matched = _detect_correction(content)
    if not matched:
        return False
    h = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    try:
        existing = CORRECTION_QUEUE.read_text(encoding="utf-8").splitlines() if CORRECTION_QUEUE.exists() else []
    except Exception:
        existing = []
    if existing and h in existing[-1]:
        return False  # dedup vs the last queued line
    low = content.lower()
    snippet = content if len(content) <= 1200 else content[:1200] + " [truncated]"
    entry = {
        "ts": dt.datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "source": "discord",
        "hash": h,
        "matched_phrase": matched,
        "prompt": snippet,
        "skills_named": _skills_named(low),
        "denylist_hit": any(d in low for d in _CORRECTION_DENYLIST),
        "processed": False,
    }
    CORRECTION_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    with CORRECTION_QUEUE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    try:  # retention cap (OP-22): keep last 500 lines
        all_lines = CORRECTION_QUEUE.read_text(encoding="utf-8").splitlines()
        if len(all_lines) > 500:
            CORRECTION_QUEUE.write_text("\n".join(all_lines[-500:]) + "\n", encoding="utf-8")
    except Exception:
        pass
    logging.info("correction captured (discord): %s", matched)
    return True


# ---------------------------------------------------------------------------
# Free-form Q&A (LLM-backed; after-hours only)
# ---------------------------------------------------------------------------

def _build_prompt(user_msg: str) -> str:
    queue_blob = ""
    if QUEUE.exists():
        try:
            q = json.loads(QUEUE.read_text(encoding="utf-8"))
            queue_blob = json.dumps({
                "next_action": q.get("next_action"),
                "stages": {k: {"state": v.get("state"), "completed": v.get("completed"),
                               "total": v.get("total"), "keepers": v.get("keepers")}
                           for k, v in q.get("stages", {}).items()},
            }, indent=2)
        except Exception:
            queue_blob = "(research-queue.json unreadable)"

    # Surface any pending proposals so a "status?" answer mentions what's awaiting J.
    pending = [r for r in _read_proposals() if r.get("status") == "pending"]
    pending_blob = json.dumps(
        [{"id": r.get("proposal_id"), "title": r.get("title")} for r in pending], indent=2
    ) if pending else "(none)"

    return f"""You are Gamma, the user's autonomous 0DTE trading research partner, replying to J on Discord while he is away. Voice = sharp operator (see automation/presence/SOUL.md): terse, confident, signal over noise, no chatbot filler.

Current grinder/research state:
{queue_blob}

Pending proposals awaiting J's ship/shelve:
{pending_blob}

J just sent:
"{user_msg}"

Reply CONCISELY (under 1200 chars -- Discord). Direct answer, then what you ARE doing (not "should I"). If he is asking status, summarize state + any pending proposals (he resolves a proposal by replying "ship <id>" or "shelve <id>"). End with the next concrete step. Per OP-18: no "let me know if", no "your call", no hedging."""


def _resolve_claude_exe() -> str:
    """Resolve the claude executable absolutely. The Task Scheduler -> wscript ->
    pythonw chain runs with a minimal PATH that does NOT include the npm global bin,
    so a bare "claude" raised FileNotFoundError -- the "[claude CLI not found on
    PATH]" bug surfaced on the responder's first live fire (2026-06-20). Prefer the
    real .exe (CreateProcess-friendly; a .cmd shim can't be run by subprocess without
    a shell) at the same absolute path the PowerShell tasks use (_shared.ps1
    $ClaudeExe), then fall back to PATH lookup, then the .cmd shim, then bare name."""
    exe = Path.home() / "AppData/Roaming/npm/node_modules/@anthropic-ai/claude-code/bin/claude.exe"
    if exe.exists():
        return str(exe)
    found = shutil.which("claude")
    if found:
        return found
    cmd = Path.home() / "AppData/Roaming/npm/claude.cmd"
    if cmd.exists():
        return str(cmd)
    return "claude"


def _invoke_claude(prompt: str) -> str:
    """Run claude --print on Haiku (cheap). Returns stdout, or an error string."""
    try:
        _flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW (L41)
        result = subprocess.run(
            [
                _resolve_claude_exe(), "--print",
                "--model", "haiku",
                "--max-budget-usd", "0.15",
                "--effort", "low",
                "--output-format", "text",
                "--permission-mode", "bypassPermissions",
                prompt,
            ],
            capture_output=True, text=True, timeout=180,
            cwd=str(REPO),
            creationflags=_flags,
        )
        if result.returncode != 0:
            return f"[claude --print exit {result.returncode}] {result.stderr[:500]}"
        return result.stdout.strip() or "[claude returned empty output]"
    except subprocess.TimeoutExpired:
        return "[claude --print timed out after 180s]"
    except FileNotFoundError:
        return "[claude CLI not found -- checked npm global bin + PATH]"
    except Exception as exc:
        return f"[invoke error: {exc}]"


# ---------------------------------------------------------------------------
# Main tick
# ---------------------------------------------------------------------------

def main() -> int:
    user_id = _load_user_id()
    last_id = _load_watermark()
    inbox = _read_inbox()

    # Find unprocessed messages from J (skip messages older than watermark).
    new_msgs = []
    if not last_id:
        if inbox:
            new_msgs = [inbox[-1]]  # first run: only the latest, don't reply to history
    else:
        seen = False
        for row in inbox:
            if row.get("discord_msg_id") == last_id:
                seen = True
                continue
            if seen:
                new_msgs.append(row)

    if not new_msgs:
        logging.info("no new messages")
        return 0

    if user_id:
        new_msgs = [m for m in new_msgs if m.get("author_id") == user_id]
    if not new_msgs:
        logging.info("new messages but none from J")
        if inbox:
            _save_watermark(inbox[-1].get("discord_msg_id", ""))
        return 0

    mkt_open = market_is_open()

    # Usage cap (OP-3): gate the LLM path only. Approval parsing is free.
    sys.path.insert(0, str(REPO / "backtest"))
    try:
        from autoresearch.usage_tracker import check_and_record, get_snapshot
    except Exception as e:
        check_and_record = None
        get_snapshot = None
        logging.error(f"usage_tracker import failed: {e}")

    for msg in new_msgs:
        content = msg.get("content", "").strip()
        if not content:
            _save_watermark(msg.get("discord_msg_id", ""))
            continue
        logging.info("processing: %s", content[:80])

        # 0a) CAPTURE J'S CORRECTION (pure Python, $0, even during RTH) -- parity with
        # the terminal hook so Discord corrections aren't lost. Non-consuming side
        # effect: we still revert/approve/answer below regardless.
        try:
            _capture_correction(content)
        except Exception as e:
            logging.exception("correction-capture error: %s", e)

        # 0) REVERT (J's off-switch) -- dispatch to the actuator; works any time.
        try:
            if _try_revert(content, user_id):
                _save_watermark(msg["discord_msg_id"])
                continue
        except Exception as e:
            logging.exception("revert parse error: %s", e)

        # 1) APPROVE/REVOKE first -- pure Python, $0, works even during RTH.
        try:
            if _try_resolve_proposal(content, user_id):
                _save_watermark(msg["discord_msg_id"])
                continue
        except Exception as e:
            logging.exception("approve/revoke parse error: %s", e)
            # fall through -- never let a parse bug eat the message silently

        # 2) FREE-FORM Q&A -- LLM-backed, AFTER-HOURS ONLY (L54).
        if mkt_open:
            # Don't spawn a market-hours model (would starve heartbeat). Defer:
            # do NOT advance the watermark so this message is answered after close.
            logging.info("market open -- deferring LLM reply for: %s", content[:60])
            # Ack once so J isn't left hanging, but cheaply (no model).
            _queue_outbox(
                "Got it -- market's open so I'm staying off the shared rate-limit pool "
                "(heartbeat priority). I'll answer right after the close. "
                "(Approve/revoke commands like 'ship <id>' work now.)",
                user_id,
            )
            _save_watermark(msg["discord_msg_id"])
            continue

        if check_and_record is not None:
            allowed, reason = check_and_record("discord-responder", reason=content[:60])
            if not allowed:
                snap = get_snapshot() if get_snapshot else {}
                _queue_outbox(
                    f"usage cap hit: {reason}. today ~${snap.get('today_est_cost_usd', 0):.2f}. "
                    f"will resume when within cap. (ship/shelve still work.)",
                    user_id,
                )
                logging.warning("REFUSED (cap): %s", reason)
                _save_watermark(msg["discord_msg_id"])
                continue

        prompt = _build_prompt(content)
        response = _invoke_claude(prompt)
        if len(response) > 1900:
            response = response[:1850] + "\n... (truncated)"
        _queue_outbox(response, user_id)
        _save_watermark(msg["discord_msg_id"])
        logging.info("queued response (%d chars)", len(response))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Discord responder — polls inbox for new user messages, invokes claude --print, replies via outbox.

Runs every 5 minutes via Gamma_DiscordResponder scheduled task.

Flow:
  1. Read discord-inbox.jsonl, find messages newer than last-processed watermark
  2. For each new message from J (filter by author_id), build a context prompt
  3. Invoke `claude --print` with the prompt, capture stdout
  4. Queue the response to discord-outbox.jsonl (bridge sends it)
  5. Update watermark

Per CLAUDE.md OP 18 (truly autonomous research mode): J can message me Discord
while away, I respond without him needing to open Claude Code.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE_DIR = REPO / "automation" / "state"
INBOX = STATE_DIR / "discord-inbox.jsonl"
OUTBOX = STATE_DIR / "discord-outbox.jsonl"
WATERMARK = STATE_DIR / ".discord-responder-watermark.json"
LOGFILE = STATE_DIR / "logs" / "discord-responder.log"
QUEUE = STATE_DIR / "research-queue.json"
CFG = STATE_DIR / ".discord-config.json"

LOGFILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(LOGFILE),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


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


def _build_prompt(user_msg: str) -> str:
    """Build a context-rich prompt for claude --print."""
    queue_blob = ""
    if QUEUE.exists():
        try:
            q = json.loads(QUEUE.read_text(encoding="utf-8"))
            queue_blob = json.dumps({
                "next_action": q.get("next_action"),
                "stages": {k: {"state": v.get("state"), "completed": v.get("completed"),
                               "total": v.get("total"), "keepers": v.get("keepers"),
                               "best_edge_capture": v.get("best_edge_capture"),
                               "best_wide_pnl": v.get("best_wide_pnl"),
                               "best_top5_pct": v.get("best_top5_pct"),
                               "best_positive_quarters": v.get("best_positive_quarters")}
                           for k, v in q.get("stages", {}).items()},
            }, indent=2)
        except Exception:
            queue_blob = "(research-queue.json unreadable)"

    return f"""You are Gamma, the user's autonomous trading research partner. He is messaging you via Discord while away from his computer.

Read CLAUDE.md operating principles first (especially OP 18 + OP 19 — truly autonomous research mode and self-healing pipeline).

Current grinder pipeline state:
{queue_blob}

The user just sent this Discord message:
"{user_msg}"

Respond CONCISELY (under 1500 chars — Discord limit). Include:
1. Direct answer to his question/request
2. What you ARE doing about it (or already did) — not "should I"
3. When the next status update will fire and what triggers it

If the message asks for status, report the grinder pipeline state above + next event timing.
If the message asks you to do something, do it (write code, launch a stage, edit doctrine), then report what you did.
If the message is conversational, acknowledge concisely.

DO NOT use chatbot phrases ("let me know if", "your call", "want me to also..." — see OP 18). End every reply with what you're doing next."""


def _invoke_claude(prompt: str) -> str:
    """Run claude --print with the prompt. Returns stdout, or error string."""
    try:
        # CREATE_NO_WINDOW = 0x08000000 — OP-27 L41.
        _flags = 0x08000000 if sys.platform == "win32" else 0
        result = subprocess.run(
            [
                "claude", "--print",
                "--model", "sonnet",
                "--max-budget-usd", "0.50",
                "--effort", "medium",
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
        return "[claude CLI not found on PATH]"
    except Exception as exc:
        return f"[invoke error: {exc}]"


def main() -> int:
    user_id = _load_user_id()
    last_id = _load_watermark()
    inbox = _read_inbox()

    # Find unprocessed messages from J (skip messages older than watermark)
    new_msgs = []
    if not last_id:
        # First run: only process the LATEST message (don't reply to history)
        if inbox:
            new_msgs = [inbox[-1]]
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

    # Filter to messages from J (his author_id from config)
    if user_id:
        new_msgs = [m for m in new_msgs if m.get("author_id") == user_id]

    if not new_msgs:
        logging.info("new messages but none from J")
        # Still bump watermark to last seen
        if inbox:
            _save_watermark(inbox[-1].get("discord_msg_id", ""))
        return 0

    # Wire usage cap (CLAUDE.md OP 3): refuse claude --print if over cap
    sys.path.insert(0, str(REPO / "backtest"))
    try:
        from autoresearch.usage_tracker import check_and_record, get_snapshot
    except Exception as e:
        check_and_record = None
        logging.error(f"usage_tracker import failed: {e}")

    for msg in new_msgs:
        content = msg.get("content", "").strip()
        if not content:
            continue
        logging.info(f"processing: {content[:80]}")

        if check_and_record is not None:
            allowed, reason = check_and_record("discord-responder", reason=content[:60])
            if not allowed:
                snap = get_snapshot()
                bypass_reply = (
                    f"⚠️ usage cap hit: {reason}\n"
                    f"today: {snap.get('today_count', '?')} invocations, "
                    f"~${snap.get('today_est_cost_usd', 0):.2f}\n"
                    f"will resume when within cap. message preserved in inbox."
                )
                _queue_outbox(bypass_reply, user_id)
                logging.warning(f"REFUSED: {reason}")
                # DO NOT update watermark — message will be retried next tick when cap clears
                # But to prevent infinite retry of same message, mark as "rate_limited" in a side file
                rate_limited_file = STATE_DIR / ".discord-responder-rate-limited.json"
                rl = {}
                if rate_limited_file.exists():
                    try:
                        rl = json.loads(rate_limited_file.read_text(encoding="utf-8"))
                    except Exception:
                        rl = {}
                rl[msg["discord_msg_id"]] = dt.datetime.utcnow().isoformat()
                rate_limited_file.write_text(json.dumps(rl), encoding="utf-8")
                # bump watermark anyway so we don't reprocess on next tick
                _save_watermark(msg["discord_msg_id"])
                continue

        prompt = _build_prompt(content)
        response = _invoke_claude(prompt)
        # Truncate to Discord limit (2000 char hard, leave room for mention)
        if len(response) > 1900:
            response = response[:1850] + "\n... (truncated)"
        _queue_outbox(response, user_id)
        _save_watermark(msg["discord_msg_id"])
        logging.info(f"queued response ({len(response)} chars)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

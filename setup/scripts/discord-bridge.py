"""Persistent Discord <-> Gamma bridge.

Runs forever. Two responsibilities:

1. INBOX: poll Discord channel for new messages from the user, append each to
   `automation/state/discord-inbox.jsonl` so heartbeat / dashboard can read them.
2. OUTBOX: watch `automation/state/discord-outbox.jsonl` for new lines (written
   by Gamma's heartbeat / EOD / weekly-review etc.), send each as a Discord
   message.

JSONL formats:

    inbox row:
      {"received_at": "<ISO>", "discord_msg_id": "...", "author": "<name>",
       "content": "<text>", "channel_id": "..."}

    outbox row:
      {"queued_at": "<ISO>", "content": "<text>", "channel_id": "..." (optional, defaults to config)}

Idempotency: bridge tracks last-sent outbox line in a watermark file so it
doesn't double-send if it crashes mid-line. Tracks last-seen inbox message id
similarly.

Config: automation/state/.discord-config.json
Watermarks: automation/state/.discord-bridge-watermarks.json
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT ============================================================
# When launched via pythonw.exe (no console), Windows 11's default-terminal setting
# (Windows Terminal) will allocate a visible WT tab the first time the process writes
# to stdout/stderr. Redirect stdio to log files BEFORE logging.basicConfig() runs.
# See CLAUDE.md OP 27 L38 + 2026-05-16 evening foot-gun.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower() == "pythonw.exe":
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "discord-bridge.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "discord-bridge.stderr.log", "a", buffering=1, encoding="utf-8")
# ========================================================================================

import datetime as dt
import json
import logging
import sys
import time
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[2]
STATE_DIR = REPO / "automation" / "state"
CFG_PATH = STATE_DIR / ".discord-config.json"
INBOX_PATH = STATE_DIR / "discord-inbox.jsonl"
OUTBOX_PATH = STATE_DIR / "discord-outbox.jsonl"
WATERMARK_PATH = STATE_DIR / ".discord-bridge-watermarks.json"
PID_PATH = STATE_DIR / "discord-bridge.pid"

POLL_INTERVAL_SEC = 15
API = "https://discord.com/api/v10"
HEARTBEAT_PATH = STATE_DIR / "discord-bridge-heartbeat.json"  # written each tick for frozen-bridge detection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


def load_config() -> dict:
    # Use utf-8-sig to tolerate BOM that PowerShell Out-File adds.
    # Reset BOM-corrupted file gracefully if present.
    return json.loads(CFG_PATH.read_text(encoding="utf-8-sig"))


def load_watermarks() -> dict:
    if WATERMARK_PATH.exists():
        try:
            return json.loads(WATERMARK_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"last_inbox_msg_id": None, "last_outbox_line_no": 0}


def save_watermarks(wm: dict) -> None:
    tmp = WATERMARK_PATH.with_suffix(WATERMARK_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(wm, indent=2), encoding="utf-8")
    tmp.replace(WATERMARK_PATH)


def write_pid() -> None:
    PID_PATH.write_text(f"{__import__('os').getpid()}|{now_iso()}", encoding="utf-8")


def cleanup_pid() -> None:
    try:
        PID_PATH.unlink()
    except FileNotFoundError:
        pass


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bot {token}", "Content-Type": "application/json"}


def poll_inbox(config: dict, wm: dict) -> int:
    """Fetch new messages from configured channel, append to inbox JSONL.
    Returns count of new messages found.
    """
    channel_id = config.get("channel_id")
    if not channel_id:
        return 0
    token = config["bot_token"]
    bot_user_id = config.get("bot_user_id")  # populated on first run

    params = {"limit": 50}
    after = wm.get("last_inbox_msg_id")
    if after:
        params["after"] = after

    try:
        r = requests.get(
            f"{API}/channels/{channel_id}/messages",
            headers=auth_headers(token),
            params=params,
            timeout=15,
        )
    except requests.RequestException as e:
        logger.warning("inbox poll network error: %s", e)
        return 0
    if r.status_code != 200:
        logger.warning("inbox poll http %d: %s", r.status_code, r.text[:200])
        return 0

    msgs = r.json()
    if not msgs:
        return 0

    # Discord returns newest-first; we want oldest-first for chronological append.
    msgs.sort(key=lambda m: int(m["id"]))

    new_count = 0
    last_id = wm.get("last_inbox_msg_id")
    for m in msgs:
        # Skip our own bot's messages.
        if bot_user_id and m["author"]["id"] == bot_user_id:
            last_id = m["id"]
            continue
        row = {
            "received_at": now_iso(),
            "discord_msg_id": m["id"],
            "author": m["author"]["username"],
            "author_id": m["author"]["id"],
            "content": m.get("content", ""),
            "channel_id": channel_id,
        }
        with INBOX_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        new_count += 1
        last_id = m["id"]
        logger.info("inbox <- %s: %s", row["author"], row["content"][:80])

    if last_id != wm.get("last_inbox_msg_id"):
        wm["last_inbox_msg_id"] = last_id
        save_watermarks(wm)
    return new_count


def drain_outbox(config: dict, wm: dict) -> int:
    """Send any new lines in outbox JSONL since last_outbox_line_no.
    Returns count of messages sent.

    SAFETY: J explicitly requested "do not message swjsh vault, only HQ".
    We hard-pin the channel_id to config.channel_id and IGNORE any per-row
    channel_id override. To send to a different channel, edit the config.
    """
    if not OUTBOX_PATH.exists():
        return 0
    token = config["bot_token"]
    default_channel = config.get("channel_id")
    HQ_ONLY_CHANNEL = default_channel  # always use config channel, refuse overrides

    sent = 0
    last_line_no = wm.get("last_outbox_line_no", 0)
    with OUTBOX_PATH.open(encoding="utf-8") as f:
        lines = f.readlines()

    if last_line_no >= len(lines):
        return 0

    for i in range(last_line_no, len(lines)):
        raw = lines[i].strip()
        if not raw:
            wm["last_outbox_line_no"] = i + 1
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("outbox line %d malformed, skipping", i)
            wm["last_outbox_line_no"] = i + 1
            continue

        # HQ-only safety: ignore per-row channel_id overrides.
        channel_id = HQ_ONLY_CHANNEL
        if row.get("channel_id") and row["channel_id"] != HQ_ONLY_CHANNEL:
            logger.warning(
                "outbox line %d requested channel %s -- IGNORED, sending to HQ only",
                i, row["channel_id"],
            )
        if not channel_id:
            logger.warning("outbox line %d has no channel_id and no default; skipping", i)
            wm["last_outbox_line_no"] = i + 1
            continue
        content = row.get("content", "").strip()
        if not content:
            wm["last_outbox_line_no"] = i + 1
            continue

        # Discord max 2000 chars; truncate.
        if len(content) > 1900:
            content = content[:1900] + "...[truncated]"

        try:
            r = requests.post(
                f"{API}/channels/{channel_id}/messages",
                headers=auth_headers(token),
                json={"content": content},
                timeout=15,
            )
        except requests.RequestException as e:
            logger.error("outbox send network error: %s -- will retry next tick", e)
            return sent  # don't advance watermark; retry this line later
        if r.status_code in (200, 201):
            sent += 1
            wm["last_outbox_line_no"] = i + 1
            save_watermarks(wm)
            logger.info("outbox -> %s (%d chars)", channel_id, len(content))
        elif r.status_code == 429:
            # Rate limited.
            retry_after = float(r.headers.get("Retry-After", "5"))
            logger.warning("rate limited; sleeping %.1fs", retry_after)
            time.sleep(retry_after)
            return sent  # retry this line on next iteration
        else:
            logger.error("outbox http %d: %s -- skipping line %d", r.status_code, r.text[:200], i)
            wm["last_outbox_line_no"] = i + 1
            save_watermarks(wm)

    return sent


def main() -> int:
    write_pid()
    logger.info("Discord bridge starting (poll=%ds)", POLL_INTERVAL_SEC)

    try:
        config = load_config()
    except Exception as e:
        logger.error("could not load config: %s", e)
        return 1

    if not config.get("channel_id"):
        logger.error("no channel_id in config -- run discord-test.py first")
        return 1

    # Discover bot user id once (so we can skip self-messages in inbox).
    if not config.get("bot_user_id"):
        token = config["bot_token"]
        r = requests.get(f"{API}/users/@me", headers=auth_headers(token), timeout=15)
        if r.status_code == 200:
            config["bot_user_id"] = r.json()["id"]
            CFG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
            logger.info("discovered bot_user_id=%s", config["bot_user_id"])

    wm = load_watermarks()
    logger.info(
        "watermarks: last_inbox_msg_id=%s last_outbox_line=%d",
        wm.get("last_inbox_msg_id"), wm.get("last_outbox_line_no", 0),
    )

    consecutive_errors = 0
    try:
        while True:
            try:
                in_count = poll_inbox(config, wm)
                out_count = drain_outbox(config, wm)
                if in_count or out_count:
                    logger.info("tick: inbox=%d outbox=%d", in_count, out_count)
                consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                logger.exception("tick error #%d: %s", consecutive_errors, e)
                if consecutive_errors >= 5:
                    logger.error("5 consecutive errors -- backing off to 60s")
                    time.sleep(60)
                    consecutive_errors = 0
            # DISCORD-FROZEN-DETECTION: write last_tick_at each loop iteration.
            # Watchdog can check this file; if > 5 min stale, bridge is frozen (alive but not polling).
            try:
                HEARTBEAT_PATH.write_text(
                    json.dumps({"last_tick_at": now_iso(), "consecutive_errors": consecutive_errors}),
                    encoding="utf-8",
                )
            except Exception:
                pass  # never let heartbeat write block the main loop
            time.sleep(POLL_INTERVAL_SEC)
    except KeyboardInterrupt:
        logger.info("Discord bridge stopped (KeyboardInterrupt)")
    finally:
        cleanup_pid()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

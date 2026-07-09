"""open_bell_status.py -- the OPEN-BELL status push (OP-33e).

J's recurring "is it running today?" question, answered ONCE, unprompted, right after
the open. Composes a single short Discord message from EXISTING state only (no new
producers, read-only):

  1. engine-health verdict            <- automation/state/engine-health.json
  2. kill-switch armed + RE-ARMED-TODAY (both accounts) <- both circuit-breaker.json files
  3. tick freshness                   <- newest ts_et in automation/state/core-decisions.jsonl
  4. fills so far                     <- automation/state/trade-today.json

Delivery reuses the EXISTING Discord outbox + mention pattern from
trade_today_watcher.py (the SAME channel that already delivers fill pings) -- no new
delivery path, no new channel.

Idempotent: writes automation/state/open-bell-pinged.json {"date": ...} and refuses to
double-send on a second call the same ET day (matches the scheduled task's own
MultipleInstances=IgnoreNew, but also protects a manual re-run).

FAIL-OPEN ALWAYS: this is a read-only, notify-only observer. It places NO order, arms
NOTHING, touches NO params/doctrine/breaker files, and can NEVER block J or trade-halt.
Any internal error degrades to a benign skip; main() always returns 0.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))
from et_clock import et_now, et_today_str  # noqa: E402

STATE = REPO / "automation" / "state"
AGG = STATE / "aggressive"
OUTBOX = STATE / "discord-outbox.jsonl"
PINGED_FILE = STATE / "open-bell-pinged.json"
DISCORD_CFG = STATE / ".discord-config.json"

ENGINE_HEALTH_PATH = STATE / "engine-health.json"
SAFE_BREAKER_PATH = STATE / "circuit-breaker.json"
BOLD_BREAKER_PATH = AGG / "circuit-breaker.json"
CORE_DECISIONS_PATH = STATE / "core-decisions.jsonl"
TRADE_TODAY_PATH = STATE / "trade-today.json"

# Per-account breaker date-field (mirrors daily_loss_guard.py ACCOUNTS / engine_health.py
# BREAKER_DATE_FIELD -- the C9 symmetry trap: the two breakers use divergent field names).
BREAKER_DATE_FIELD = {"safe": "last_reset", "bold": "session_id"}

_VERDICT_EMOJI = {"GREEN": "\U0001f7e2", "YELLOW": "\U0001f7e1", "RED": "\U0001f534"}


# --------------------------------------------------------------------------- #
# Fail-open readers (isolated IO -- every one degrades to None/[] on any error,
# never raises; rail-2 pattern used throughout this codebase's notify-only observers).
# --------------------------------------------------------------------------- #

def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001 -- fail-open: missing/garbled -> None
        return None


def _newest_jsonl_row(path: Path, max_bytes: int = 131072) -> Optional[dict]:
    """Best-effort newest parseable JSON object in the file's tail. None on any failure
    (missing file, unreadable, no parseable line) -- never raises."""
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            tail = f.read().decode("utf-8", errors="replace").splitlines()
    except Exception:  # noqa: BLE001
        return None
    for raw in reversed(tail):
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            return row
    return None


def _load_user_mention() -> str:
    """Same fail-open pattern as trade_today_watcher.py / discord-watcher.py
    _load_user_mention() -- read the configured Discord user id so the ping actually
    triggers a phone push (a bare un-mentioned post may not, per the 2026-07-08 T3 fix)."""
    try:
        cfg = json.loads(DISCORD_CFG.read_text(encoding="utf-8-sig"))
        uid = cfg.get("user_id")
        return f"<@{uid}> " if uid else ""
    except Exception:  # noqa: BLE001
        return ""


# --------------------------------------------------------------------------- #
# PURE composition (no IO, no clock -- fully unit-testable from fixture dicts).
# --------------------------------------------------------------------------- #

def _breaker_summary(breaker: Optional[dict], date_field: str, today: str) -> str:
    """'armed+re-armed-today YES' / 'armed, re-armed-today NO' / 'TRIPPED' / 'unknown'."""
    if breaker is None:
        return "unknown (breaker file unreadable)"
    tripped = bool(breaker.get("tripped"))
    raw_date = breaker.get(date_field)
    bdate = str(raw_date)[:10] if raw_date else None
    rearmed_today = "YES" if bdate == today else "NO"
    if tripped:
        reason = breaker.get("tripped_reason") or breaker.get("trip_reason") or "unspecified"
        return f"TRIPPED ({reason})"
    return f"armed, re-armed-today {rearmed_today}"


def compose_message(
    *,
    today: str,
    now_et_str: str,
    engine_health: Optional[dict],
    safe_breaker: Optional[dict],
    bold_breaker: Optional[dict],
    newest_tick: Optional[dict],
    now_et_minutes: Optional[float],
    trade_today: Optional[dict],
) -> str:
    """PURE: build the message body (no mention prefix -- caller prepends that). Every
    input is an already-loaded dict/None so this is testable from plain fixtures."""
    lines: list[str] = []

    verdict = (engine_health or {}).get("verdict") or "UNKNOWN"
    emoji = _VERDICT_EMOJI.get(verdict, "⚪")
    lines.append(f"{emoji} OPEN-BELL STATUS {today} {now_et_str} ET -- engine: {verdict}")

    lines.append(
        "Kill-switches: Safe " + _breaker_summary(safe_breaker, BREAKER_DATE_FIELD["safe"], today)
        + " | Bold " + _breaker_summary(bold_breaker, BREAKER_DATE_FIELD["bold"], today)
    )

    if newest_tick is None:
        lines.append("Ticks: no core-decisions.jsonl row found (engine may not have ticked yet)")
    else:
        ts = str(newest_tick.get("ts_et", "?"))
        acct = newest_tick.get("account", "?")
        if now_et_minutes is not None:
            lines.append(f"Ticks: last {acct} tick {ts[11:19] if len(ts) >= 19 else ts} ({now_et_minutes:.1f}m ago)")
        else:
            lines.append(f"Ticks: last {acct} tick {ts}")

    if trade_today is None:
        lines.append("Fills: unknown (trade-today.json unreadable)")
    else:
        filled = trade_today.get("spy_fills_today", 0)
        unfilled = trade_today.get("placed_not_filled_today", 0)
        if not filled and not unfilled:
            lines.append("Fills: none yet")
        else:
            lines.append(f"Fills: {filled} filled, {unfilled} placed-not-filled")

    content = "\n".join(lines)
    if len(content) > 1900:
        content = content[:1880] + "...[truncated]"
    return content


# --------------------------------------------------------------------------- #
# Idempotency (per-ET-day, matches trade_today_watcher.py's PINGED-file convention).
# --------------------------------------------------------------------------- #

def already_sent_today(today: str) -> bool:
    data = _read_json(PINGED_FILE)
    return bool(data and data.get("date") == today)


def mark_sent(today: str, now_iso: str) -> None:
    try:
        PINGED_FILE.write_text(json.dumps({"date": today, "queued_at": now_iso}), encoding="utf-8")
    except OSError:
        pass  # fail-open: a write failure just risks a duplicate send tomorrow, never crashes


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> int:
    try:
        now_et = et_now()
        today = et_today_str()
        now_et_str = now_et.strftime("%H:%M")

        if already_sent_today(today):
            print(f"[open_bell_status] already sent for {today} -- skip (idempotent)")
            return 0

        engine_health = _read_json(ENGINE_HEALTH_PATH)
        safe_breaker = _read_json(SAFE_BREAKER_PATH)
        bold_breaker = _read_json(BOLD_BREAKER_PATH)
        newest_tick = _newest_jsonl_row(CORE_DECISIONS_PATH)
        trade_today = _read_json(TRADE_TODAY_PATH)

        now_et_minutes: Optional[float] = None
        if newest_tick is not None:
            ts = str(newest_tick.get("ts_et", ""))
            try:
                from datetime import datetime
                dt = datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")
                now_et_minutes = (now_et - dt).total_seconds() / 60.0
            except ValueError:
                now_et_minutes = None

        body = compose_message(
            today=today, now_et_str=now_et_str, engine_health=engine_health,
            safe_breaker=safe_breaker, bold_breaker=bold_breaker,
            newest_tick=newest_tick, now_et_minutes=now_et_minutes,
            trade_today=trade_today,
        )
        mention = _load_user_mention()
        content = mention + body

        now_iso = now_et.isoformat()
        try:
            with OUTBOX.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"content": content, "source": "open_bell_status",
                                      "queued_at": now_iso}, ensure_ascii=False) + "\n")
        except Exception as e:  # noqa: BLE001 -- never let a delivery failure crash the script
            print(f"[open_bell_status] outbox append failed (fail-open): {e}", file=sys.stderr)
            return 0

        mark_sent(today, now_iso)
        print(f"[open_bell_status] PINGED J for {today}:\n{body}")
        return 0
    except Exception as e:  # noqa: BLE001 -- fail-open: never break the scheduled chain
        print(f"[open_bell_status] benign-skip ({type(e).__name__}: {e})", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())

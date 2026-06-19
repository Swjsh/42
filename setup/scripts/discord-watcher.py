"""Persistent watcher: polls Gamma trade state and pings J on key trade moments.

Re-pointed 2026-06-17 from the old v15/weekend-research events to the LIVE trade
lifecycle, per J's "proactive presence" direction. Voice = Sharp operator
(automation/presence/SOUL.md). Cadence = key moments only.

Per account (Safe + Bold) it tails the decision ledger and fires on:
  ENTER_BULL/ENTER_BEAR/ENTER -> entry      EXIT_TP1[_PARTIAL] -> TP1/scale
  EXIT_RUNNER -> runner closed              EXIT_STOP -> stopped
  EXIT_TIME/EXIT_ALL -> flat by close       circuit-breaker .tripped -> kill-switch
HOLD*/SKIP_*/ERROR_* are noise and are skipped.

Writes one outbox row per event; the bridge sends it within 15s.
Idempotent: each ledger is tailed by line count (watermark in
.discord-watcher-state.json) so a restart never re-fires old events.

Run: python setup/scripts/discord-watcher.py
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT ============================================================
# Under pythonw.exe (no console) Windows 11 would allocate a visible Terminal tab on the
# first stdout/stderr write. Redirect to log files BEFORE logging configures. (OP-27 L38)
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower() == "pythonw.exe":
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "discord-watcher.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "discord-watcher.stderr.log", "a", buffering=1, encoding="utf-8")
# ========================================================================================

import datetime as dt
import json
import logging
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE_DIR = REPO / "automation" / "state"
OUTBOX_PATH = STATE_DIR / "discord-outbox.jsonl"
WATCHER_STATE_PATH = STATE_DIR / ".discord-watcher-state.json"
PID_PATH = STATE_DIR / "discord-watcher.pid"
CFG_PATH = STATE_DIR / ".discord-config.json"

POLL_INTERVAL_SEC = 30

# Per-account wiring: (ledger, [position files, first existing wins], circuit-breaker, label)
ACCOUNTS = {
    "safe": {
        "ledger": STATE_DIR / "decisions.jsonl",
        "position": [STATE_DIR / "current-position-safe.json", STATE_DIR / "current-position.json"],
        "cb": STATE_DIR / "circuit-breaker.json",
        "label": "Safe",
    },
    "bold": {
        "ledger": STATE_DIR / "aggressive" / "decisions.jsonl",
        "position": [STATE_DIR / "current-position-bold.json"],
        "cb": STATE_DIR / "aggressive" / "circuit-breaker.json",
        "label": "Bold",
    },
}

ENTER_ACTIONS = {"ENTER_BULL", "ENTER_BEAR", "ENTER"}
TP1_ACTIONS = {"EXIT_TP1", "EXIT_TP1_PARTIAL"}
RUNNER_ACTIONS = {"EXIT_RUNNER"}
STOP_ACTIONS = {"EXIT_STOP"}
TIME_ACTIONS = {"EXIT_TIME", "EXIT_ALL"}
NOTIFY_ACTIONS = ENTER_ACTIONS | TP1_ACTIONS | RUNNER_ACTIONS | STOP_ACTIONS | TIME_ACTIONS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


def _load_user_mention() -> str:
    try:
        cfg = json.loads(CFG_PATH.read_text(encoding="utf-8-sig"))  # BOM-tolerant
        uid = cfg.get("user_id")
        return f"<@{uid}> " if uid else ""
    except Exception:
        return ""


def queue_message(content: str, mention: bool = True) -> None:
    """Append one row to the outbox. Bridge sends within 15s. @mention J by default."""
    prefix = _load_user_mention() if mention else ""
    row = {"queued_at": now_iso(), "content": prefix + content}
    with OUTBOX_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    logger.info("queued: %s", (prefix + content)[:90])


def load_state() -> dict:
    if WATCHER_STATE_PATH.exists():
        try:
            return json.loads(WATCHER_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(s: dict) -> None:
    tmp = WATCHER_STATE_PATH.with_suffix(WATCHER_STATE_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(s, indent=2), encoding="utf-8")
    tmp.replace(WATCHER_STATE_PATH)


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def _read_position(acct: dict) -> dict:
    for p in acct["position"]:
        d = _read_json(p)
        if d and d.get("status"):  # only a live (non-null) position is useful for detail
            return d
    return {}


def _num(v):
    try:
        return f"{float(v):g}"
    except (TypeError, ValueError):
        return None


def compose_trade_message(row: dict, pos: dict, label: str) -> str | None:
    """Sharp-operator voiced message for a notify-worthy decision row, or None to skip."""
    action = row.get("action", "")
    tag = f" ({label})" if label != "Safe" else ""  # Bold gets tagged; Safe is the default voice

    if action in ENTER_ACTIONS:
        cp = "C" if action == "ENTER_BULL" else ("P" if action == "ENTER_BEAR" else "")
        arrow = "\U0001F4C8" if cp == "C" else ("\U0001F4C9" if cp == "P" else "")
        strike = pos.get("strike")
        qty = pos.get("qty") or pos.get("contracts")
        entry = _num(pos.get("entry_price") or pos.get("mid"))
        stop = _num(pos.get("stop_price"))
        setup = row.get("setup_name") or pos.get("setup_name") or "setup"
        if strike and qty:
            head = f"In{tag}: SPY {strike}{cp} ×{qty}"
            if entry:
                head += f" @ {entry}"
            if stop:
                head += f", stop {stop}"
            return f"{head}. {setup}. {arrow}".strip()
        spy = _num(row.get("spy"))
        tail = f" @ {spy}" if spy else ""
        return f"In{tag}: SPY {cp} ({setup}){tail}. {arrow}".strip()

    if action in TP1_ACTIONS:
        pnl = _num(pos.get("tp1_pnl") or row.get("pnl"))
        extra = f" +${pnl}" if pnl and not str(pnl).startswith("-") else ""
        return f"TP1 hit{tag}{extra}. Runner armed, stop→BE. House money now."

    if action in RUNNER_ACTIONS:
        pnl = _num(row.get("pnl") or pos.get("runner_pnl"))
        if pnl:
            sign = "" if str(pnl).startswith("-") else "+"
            fire = " \U0001F525" if not str(pnl).startswith("-") else ""
            return f"Runner closed{tag} {sign}${pnl}.{fire}".strip()
        return f"Runner closed{tag}. Flat."

    if action in STOP_ACTIONS:
        strike = pos.get("strike")
        what = f" on the {strike}" if strike else ""
        return f"Stopped{tag}{what}. Clean exit, no drama. Next."

    if action in TIME_ACTIONS:
        return f"Flat by close{tag}. Day's done."

    return None


def scan_ledger(acct_key: str, acct: dict, state: dict) -> list[str]:
    """Tail the account's decision ledger by line count; return messages for new
    notify-worthy rows. Baselines on first sight so a restart never backfills."""
    ledger = acct["ledger"]
    if not ledger.exists():
        return []
    lines = ledger.read_text(encoding="utf-8").splitlines()
    key = f"{acct_key}_last_line"
    if key not in state:  # first run: snapshot, never fire on history
        state[key] = len(lines)
        logger.info("%s ledger baseline at %d lines (no backfill)", acct_key, len(lines))
        return []

    last = state[key]
    msgs: list[str] = []
    if last < len(lines):
        pos = _read_position(acct)
        for i in range(last, len(lines)):
            raw = lines[i].strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if row.get("action") in NOTIFY_ACTIONS:
                m = compose_trade_message(row, pos, acct["label"])
                if m:
                    msgs.append(m)
    state[key] = len(lines)
    return msgs


def scan_circuit_breaker(acct_key: str, acct: dict, state: dict) -> list[str]:
    """Fire once when the breaker trips; reset the latch when it clears (next day)."""
    cb = _read_json(acct["cb"])
    if not cb:
        return []
    tripped = bool(cb.get("tripped"))
    seen_key = f"{acct_key}_cb_tripped_seen"
    if tripped and not state.get(seen_key):
        state[seen_key] = True
        equity = cb.get("current_equity") or cb.get("equity_current") or 0
        start = cb.get("starting_equity_today") or cb.get("equity_start_of_day") or 0
        try:
            pnl = float(equity) - float(start)
            pnlstr = f" -${abs(pnl):,.0f}" if pnl < 0 else f" ${pnl:,.0f}"
        except (TypeError, ValueError):
            pnlstr = ""
        return [f"\U0001F534 Kill-switch {acct['label']}:{pnlstr}, day's done. Flat by close. No re-entry."]
    if not tripped and state.get(seen_key):
        state[seen_key] = False  # re-arm latch for the next session
    return []


def write_pid() -> None:
    PID_PATH.write_text(f"{_os.getpid()}|{now_iso()}", encoding="utf-8")


def cleanup_pid() -> None:
    try:
        PID_PATH.unlink()
    except FileNotFoundError:
        pass


def tick(state: dict) -> None:
    for acct_key, acct in ACCOUNTS.items():
        for m in scan_ledger(acct_key, acct, state):
            queue_message(m)
        for m in scan_circuit_breaker(acct_key, acct, state):
            queue_message(m)
    save_state(state)


def main() -> int:
    write_pid()
    logger.info("Discord trade-watcher starting (poll=%ds)", POLL_INTERVAL_SEC)
    state = load_state()
    consecutive_errors = 0
    try:
        while True:
            try:
                tick(state)
                consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                logger.exception("watcher tick error #%d", consecutive_errors)
                if consecutive_errors >= 5:
                    queue_message(f"⚠ discord-watcher hit {consecutive_errors} errors. Last: {e}")
                    time.sleep(120)
                    consecutive_errors = 0
            time.sleep(POLL_INTERVAL_SEC)
    except KeyboardInterrupt:
        logger.info("Discord trade-watcher stopped (KeyboardInterrupt)")
    finally:
        cleanup_pid()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

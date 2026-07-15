"""j_intent_journal -- journaling (Rule 8) + fail-closed alerting for
j_intent_executor.py.

Split out of j_intent_executor.py to keep that file under the project's
<800-line guideline (coding-style: "many small files > few large files"; this
module is a self-contained "reporting" concern -- writing to journal/*.md,
journal/trades.csv, and automation/state/discord-outbox.jsonl -- with no
dependency on the trading-decision logic itself).

Two responsibilities:
  1. Journal writer (CLAUDE.md Rule 8: "if it's not in the journal, it didn't
     happen") -- append_journal_note (a dated markdown line) + append_trade_row
     / build_entry_trade_row (journal/trades.csv, header read dynamically so a
     future column change can never silently misalign).
  2. Fail-closed alerting -- alert_discord appends to the SAME
     discord-outbox.jsonl every other daemon in this repo uses (byte-identical
     {content, source, queued_at} shape, e.g. ccr_keepalive.py), rate-limited
     per `key` so a stuck retry loop alerts once per window instead of
     spamming every 15s poll tick.
"""
from __future__ import annotations

import csv as _csv
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE = PROJECT_ROOT / "automation" / "state"
JOURNAL_DIR = PROJECT_ROOT / "journal"
DISCORD_OUTBOX = STATE / "discord-outbox.jsonl"
ALERT_THROTTLE_PATH = STATE / "j-intent-alert-throttle.json"

ALERT_RETHROTTLE_SEC = 300  # re-alert an unresolved failure at most every 5 min


# ============================================================ journal notes
def _today_journal_path(now_et: datetime) -> Path:
    return JOURNAL_DIR / f"{now_et.strftime('%Y-%m-%d')}.md"


def append_journal_note(now_et: datetime, text: str) -> None:
    """Append one line under a '## J-Intent Executor' heading in today's
    journal (Rule 8). Creates the heading once per day; never overwrites
    existing journal content."""
    path = _today_journal_path(now_et)
    heading = "## J-Intent Executor"
    line = f"- **{now_et.strftime('%H:%M:%S')} ET:** {text}\n"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {now_et.strftime('%Y-%m-%d')} -- Trading Journal\n\n{heading}\n\n{line}",
                        encoding="utf-8")
        return
    text_all = path.read_text(encoding="utf-8")
    if heading in text_all:
        idx = text_all.index(heading) + len(heading)
        nl = text_all.find("\n", idx)
        insert_at = nl + 1 if nl != -1 else len(text_all)
        new_text = text_all[:insert_at] + line + text_all[insert_at:]
    else:
        new_text = text_all.rstrip("\n") + f"\n\n{heading}\n\n{line}"
    path.write_text(new_text, encoding="utf-8")


# ============================================================ trades.csv
_TRADES_CSV_HEADER_CACHE: Optional[list[str]] = None


def _trades_csv_header(path: Path) -> list[str]:
    global _TRADES_CSV_HEADER_CACHE
    if _TRADES_CSV_HEADER_CACHE is not None:
        return _TRADES_CSV_HEADER_CACHE
    with path.open("r", encoding="utf-8-sig") as f:
        header = f.readline().strip()
    _TRADES_CSV_HEADER_CACHE = header.split(",")
    return _TRADES_CSV_HEADER_CACHE


def append_trade_row(row: dict, *, account: str, csv_path: Optional[Path] = None) -> Path:
    """Append ONE row to journal/trades.csv (Safe) or journal/trades-aggressive.
    csv (Bold), matching the EXISTING header exactly (read dynamically, never
    hardcoded, so a future header change cannot silently misalign columns).
    Unknown/blank fields are left empty -- matches the file's own convention
    (existing rows leave most analytics-only columns blank)."""
    if csv_path is None:
        csv_path = JOURNAL_DIR / ("trades.csv" if account == "safe" else "trades-aggressive.csv")
    header = _trades_csv_header(csv_path)
    with csv_path.open("a", encoding="utf-8", newline="") as f:
        w = _csv.writer(f)
        w.writerow([row.get(col, "") for col in header])
    return csv_path


def build_entry_trade_row(intent: dict, *, symbol: str, qty: int, entry_px: float,
                          equity_pre: float, now_et: datetime, stop_px: float,
                          target_px: float, dollar_risk: float,
                          chart_stop_level: Optional[float]) -> dict:
    """Populate the KNOWN fields at entry time (Rule 8: pre-trade thesis
    before order). Exit-side fields are left blank -- this row records the
    ENTRY; a future exit-side finalize pass (out of scope for this build) can
    append the matching close details once one is needed live."""
    return {
        "date": now_et.strftime("%Y-%m-%d"),
        "time_entry": now_et.strftime("%H:%M:%S"),
        "setup": f"J_INTENT_{intent.get('trigger', {}).get('type', '')}",
        "contract": symbol,
        "dte": "0",
        "strike": str(chart_stop_level or ""),
        "c_or_p": intent["side"],
        "qty": str(qty),
        "entry_px": f"{entry_px:.4f}",
        "premium_paid": f"{entry_px * qty * 100:.2f}",
        "stop_px": f"{stop_px:.4f}" if stop_px else "",
        "target_px": f"{target_px:.4f}" if target_px else "",
        "dollar_risk": f"{dollar_risk:.2f}" if dollar_risk else "",
        "pct_risk_of_acct": f"{(dollar_risk / equity_pre):.2%}" if equity_pre else "",
        "account_equity_pre": f"{equity_pre:.2f}",
        "followed_rules": "Y",
        "gamma_recommended": "N",
        "j_override": "Y",
        "notes_short": f"J-called intent {intent.get('id', '')}",
        "account_id": intent["account"],
    }


# ============================================================ alerting ====
def _load_throttle() -> dict:
    if not ALERT_THROTTLE_PATH.exists():
        return {}
    try:
        return json.loads(ALERT_THROTTLE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_throttle(data: dict) -> None:
    try:
        ALERT_THROTTLE_PATH.parent.mkdir(parents=True, exist_ok=True)
        ALERT_THROTTLE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def alert_discord(key: str, message: str, *, now_et: datetime,
                  min_interval_sec: int = ALERT_RETHROTTLE_SEC) -> bool:
    """Fail-CLOSED alert on an order error: append to discord-outbox.jsonl
    (same {content, source, queued_at} shape every other daemon in this repo
    uses -- e.g. ccr_keepalive.py), rate-limited per `key` so a stuck exit
    retrying every 15s alerts once every `min_interval_sec`, never spams.
    Returns True iff an alert was actually written this call."""
    throttle = _load_throttle()
    last = throttle.get(key)
    if last:
        try:
            last_dt = datetime.strptime(last, "%Y-%m-%dT%H:%M:%S")
            if (now_et - last_dt).total_seconds() < min_interval_sec:
                return False
        except ValueError:
            pass
    DISCORD_OUTBOX.parent.mkdir(parents=True, exist_ok=True)
    with DISCORD_OUTBOX.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "content": f"@here [j_intent_executor] {message}",
            "source": "j_intent_executor",
            "queued_at": now_et.strftime("%Y-%m-%dT%H:%M:%S"),
        }) + "\n")
    throttle[key] = now_et.strftime("%Y-%m-%dT%H:%M:%S")
    _save_throttle(throttle)
    return True

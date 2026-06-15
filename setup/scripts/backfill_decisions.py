"""One-time backfill: parse heartbeat log HB# lines, append rows to decisions.jsonl.

Used 2026-05-07 EOD because the lean heartbeat prompt rewrite at 12:11 ET dropped
the decisions.jsonl write entirely. 104 ticks fired without logging. This recovers
the data from the heartbeat log lines so weekly review and learning loop have it.

Usage: python setup/scripts/backfill_decisions.py
"""

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LOG = REPO / "automation" / "state" / "logs" / "heartbeat-2026-05-07.log"
DECISIONS = REPO / "automation" / "state" / "decisions.jsonl"

# HB# line format:
# HB#{n} {hh:mm} {ACTION} | spy={x} ribbon={spread}c({stack}) vix={x}({dir}) bear={n}/10 bull={n}/11 htf={15m_stack} | {reason}
# Some variations: htf=null, htf=- , vix=N/A
HB_PATTERN = re.compile(
    r"^HB#(?P<hbnum>\S+)\s+(?P<time>\d{2}:\d{2})\s+(?P<action>\S+)\s+\|\s+"
    r"spy=(?P<spy>\S+)\s+ribbon=(?P<spread>\S+?)c\((?P<stack>\S+?)\)\s+"
    r"vix=(?P<vix>\S+?)\((?P<vixdir>\S+?)\)\s+"
    r"bear=(?P<bear>\d+)/10\s+bull=(?P<bull>\d+)/11"
    r"(?:\s+htf=(?P<htf>\S+))?\s*\|\s*(?P<reason>.+)$"
)


def tod_bucket(time_str: str) -> str:
    h, m = map(int, time_str.split(":"))
    t = h * 60 + m
    if t < 615:  # before 10:15
        return "OPEN_DRIVE"
    if t < 690:  # before 11:30
        return "MORNING"
    if t < 840:  # before 14:00
        return "MIDDAY"
    if t < 915:  # before 15:15
        return "AFTERNOON"
    return "POWER_HOUR"


def safe_float(v: str, default=None):
    try:
        return float(v.rstrip("?"))
    except Exception:
        return default


def safe_int(v: str, default=None):
    try:
        return int(v)
    except Exception:
        return default


def parse_existing_keys() -> set:
    """Return set of (date, time_et) tuples already in decisions.jsonl to dedupe."""
    keys = set()
    if not DECISIONS.exists():
        return keys
    for line in DECISIONS.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            keys.add((row.get("date"), row.get("time_et")))
        except json.JSONDecodeError:
            continue
    return keys


def main():
    if not LOG.exists():
        print(f"missing log: {LOG}")
        return 1

    existing = parse_existing_keys()
    print(f"existing rows in decisions.jsonl: {len(existing)}")

    # Find next tick_id
    next_tick = 1
    if DECISIONS.exists():
        for line in DECISIONS.read_text().splitlines():
            try:
                row = json.loads(line)
                next_tick = max(next_tick, int(row.get("tick_id", 0)) + 1)
            except Exception:
                continue
    print(f"starting tick_id: {next_tick}")

    new_rows = []
    for line in LOG.read_text().splitlines():
        m = HB_PATTERN.match(line.strip())
        if not m:
            continue

        time_et = m.group("time")
        action = m.group("action")
        date = "2026-05-07"

        if (date, time_et) in existing:
            continue  # already logged

        # Determine if this row should be written:
        # - Any non-HOLD action (ENTER_*, EXIT_*, SKIP_*, HOLD_DEV, ALERT, ERROR_*, PAUSED, TRIPPED)
        # - OR any HOLD that the heartbeat prompt would have flagged as worth logging
        # For backfill, log all non-HOLD-without-dev rows.
        if action == "HOLD" and "dev" not in line.lower() and "alert" not in line.lower():
            # Plain HOLD with no developing setup - skip per heartbeat rule
            # But for forensic record we capture HOLD_DEV/HOLD/etc when score > threshold
            bear = safe_int(m.group("bear"), 0)
            bull = safe_int(m.group("bull"), 0)
            if bear < 7 and bull < 8:
                continue  # noise, skip

        spy = safe_float(m.group("spy"))
        spread = safe_float(m.group("spread"))
        stack = m.group("stack").upper()
        vix = safe_float(m.group("vix"))
        vix_dir = m.group("vixdir").lower()
        bear = safe_int(m.group("bear"), 0)
        bull = safe_int(m.group("bull"), 0)
        htf_stack = (m.group("htf") or "null").upper()
        reason = m.group("reason").strip()

        # IV regime from VIX
        iv_regime = "MID"
        if vix and vix < 15:
            iv_regime = "LOW"
        elif vix and vix > 22:
            iv_regime = "HIGH"

        trigger_fired = action.startswith(("ENTER_", "EXIT_")) or "trigger" in reason.lower() or "rejection" in reason.lower()

        # Approximate bull/bear blockers from action+score (we don't have full filter_state from log)
        bear_blocked = []
        bull_blocked = []
        if "filter_8" in reason or "vix" in reason.lower() and ("flat" in reason.lower() or "falling" in reason.lower() or "below 17.30" in reason.lower()):
            bear_blocked.append(8)
        if "filter_9" in reason or "body" in reason.lower() or "volume" in reason.lower() and "below" in reason.lower():
            bear_blocked.append(9)
        if "filter_10" in reason or "htf" in reason.lower() and "bull" in reason.lower():
            bear_blocked.append(10)
        if "spread" in reason.lower() and ("<" in reason or "below" in reason.lower()):
            if stack == "BEAR":
                bull_blocked.append(6)
            else:
                bear_blocked.append(6)
        if "FOMC" in reason or "blackout" in reason.lower() or "skip_news" in action.lower():
            bear_blocked.append(2)
            bull_blocked.append(2)

        row = {
            "tick_id": next_tick,
            "date": date,
            "time_et": time_et,
            "action": action,
            "position_status": "open" if action.startswith("EXIT_") else (None if action != "ENTER_BULL" and action != "ENTER_BEAR" else "pending_fill"),
            "bull_score": bull,
            "bear_score": bear,
            "filter_state": {"bear_blocked": bear_blocked, "bull_blocked": bull_blocked},
            "spy": spy,
            "vix": vix,
            "vix_dir": vix_dir,
            "ribbon_stack": stack,
            "ribbon_spread_cents": spread,
            "htf_15m_stack": htf_stack,
            "iv_regime": iv_regime,
            "tod_bucket": tod_bucket(time_et),
            "trigger_fired_this_tick": trigger_fired,
            "decision_grade": None,
            "reason": reason,
            "_backfilled": True,
        }
        new_rows.append(row)
        next_tick += 1

    print(f"new rows to append: {len(new_rows)}")

    with DECISIONS.open("a", encoding="utf-8") as f:
        for row in new_rows:
            f.write(json.dumps(row) + "\n")

    print(f"appended. final row count: {next_tick - 1}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

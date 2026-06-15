"""heartbeat_pulse_check — Python port of setup/scripts/heartbeat-pulse-check.ps1.

Checks whether Gamma_Heartbeat fired on schedule during a given trading day by
reading the heartbeat log file and measuring gaps between consecutive FIRE lines.

Per .claude/skills/heartbeat-pulse-check/SKILL.md — this is the Python equivalent
that gym_session.py's _maybe_rerun_stale() can call to self-heal a missing
pulse-check output file.

OUTPUTS:
    automation/state/heartbeat-pulse-check-{date}.json

VERDICT criteria:
    GREEN  — all gaps <= 6 min during 09:30-15:55 ET
    YELLOW — 1+ gaps 6-15 min (transient throttle / startup delay is OK)
    RED    — any gap > 15 min, OR zero market-hour fires
    NOT_APPLICABLE — no log file found (weekend / market closed / log not written yet)

CLI:
    python -m autoresearch.heartbeat_pulse_check [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# OP-27 L41 — CREATE_NO_WINDOW for any subprocess spawns
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

ROOT = Path(__file__).resolve().parent.parent.parent
STATE_DIR = ROOT / "automation" / "state"
LOG_DIR = STATE_DIR / "logs"

# Regex for FIRE lines: "2026-05-19 09:35:02 ET FIRE mode=BASE idx=0 ..."
FIRE_RX = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) ET FIRE mode=\S+ idx=(\d+)")

MARKET_START = (9, 30)   # 09:30 ET
MARKET_END   = (15, 55)  # 15:55 ET — heartbeat last expected fire


def _is_weekend(date_str: str) -> bool:
    return datetime.strptime(date_str, "%Y-%m-%d").weekday() >= 5


def _parse_fires(log_path: Path, date_str: str) -> list[datetime]:
    """Extract all FIRE timestamps for the given date during RTH."""
    fires: list[datetime] = []
    if not log_path.exists():
        return fires
    start_hm = MARKET_START
    end_hm = MARKET_END
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = FIRE_RX.match(line.rstrip("\n"))
                if not m:
                    continue
                if m.group(1) != date_str:
                    continue
                fire_dt = datetime.strptime(
                    f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M:%S"
                )
                h, mi = fire_dt.hour, fire_dt.minute
                in_window = (
                    (h, mi) >= start_hm and
                    (h < end_hm[0] or (h == end_hm[0] and mi <= end_hm[1]))
                )
                if in_window:
                    fires.append(fire_dt)
    except OSError:
        pass
    return sorted(fires)


def run_check(date_str: str) -> dict:
    """Run the pulse check for date_str. Returns the summary dict."""
    log_path = LOG_DIR / f"heartbeat-{date_str}.log"

    if _is_weekend(date_str):
        return {
            "skill": "heartbeat-pulse-check",
            "run_at": datetime.now(timezone.utc).isoformat(),
            "target_date": date_str,
            "verdict": "NOT_APPLICABLE",
            "reason": "weekend-no-fires-expected",
            "fire_count_total": 0,
            "market_fire_count": 0,
            "max_gap_minutes": 0.0,
            "gaps_over_15_min": 0,
            "gaps_6_to_15_min": 0,
            "heal_action": "no-op",
            "sample_gaps": [],
        }

    if not log_path.exists():
        return {
            "skill": "heartbeat-pulse-check",
            "run_at": datetime.now(timezone.utc).isoformat(),
            "target_date": date_str,
            "verdict": "NOT_APPLICABLE",
            "reason": f"no-heartbeat-log-found:{log_path.name}",
            "fire_count_total": 0,
            "market_fire_count": 0,
            "max_gap_minutes": 0.0,
            "gaps_over_15_min": 0,
            "gaps_6_to_15_min": 0,
            "heal_action": "no-op",
            "sample_gaps": [],
        }

    fires = _parse_fires(log_path, date_str)
    market_fire_count = len(fires)

    if market_fire_count == 0:
        return {
            "skill": "heartbeat-pulse-check",
            "run_at": datetime.now(timezone.utc).isoformat(),
            "target_date": date_str,
            "verdict": "RED",
            "reason": "zero-market-hour-fires",
            "fire_count_total": 0,
            "market_fire_count": 0,
            "max_gap_minutes": 0.0,
            "gaps_over_15_min": 0,
            "gaps_6_to_15_min": 0,
            "heal_action": "no-op",
            "sample_gaps": [],
        }

    # Compute gaps
    gaps: list[float] = []
    sample_gaps: list[dict] = []
    for i in range(1, len(fires)):
        gap_min = (fires[i] - fires[i - 1]).total_seconds() / 60.0
        gaps.append(gap_min)
        if gap_min > 4.0:  # only collect notable gaps
            sample_gaps.append({
                "from": fires[i - 1].strftime("%H:%M:%S"),
                "to": fires[i].strftime("%H:%M:%S"),
                "gap_min": round(gap_min, 2),
            })

    max_gap = max(gaps) if gaps else 0.0
    gaps_over_15 = sum(1 for g in gaps if g > 15.0)
    gaps_6_to_15 = sum(1 for g in gaps if 6.0 < g <= 15.0)

    if gaps_over_15 > 0:
        verdict = "RED"
        reason = f"{gaps_over_15}-gaps-over-15-min"
    elif gaps_6_to_15 > 0:
        verdict = "YELLOW"
        reason = f"{gaps_6_to_15}-gaps-6-to-15-min"
    else:
        verdict = "GREEN"
        reason = f"all-gaps-ok-max={max_gap:.1f}min"

    return {
        "skill": "heartbeat-pulse-check",
        "run_at": datetime.now(timezone.utc).isoformat(),
        "target_date": date_str,
        "verdict": verdict,
        "reason": reason,
        "fire_count_total": market_fire_count,
        "market_fire_count": market_fire_count,
        "max_gap_minutes": round(max_gap, 2),
        "gaps_over_15_min": gaps_over_15,
        "gaps_6_to_15_min": gaps_6_to_15,
        "heal_action": "no-op",
        "sample_gaps": sample_gaps[:10],  # cap at 10
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--date", default=None,
                   help="YYYY-MM-DD (default: today ET)")
    args = p.parse_args(argv)

    if args.date is None:
        et_offset = timedelta(hours=-4)
        args.date = (datetime.now(timezone.utc) + et_offset).strftime("%Y-%m-%d")

    result = run_check(args.date)

    out_path = STATE_DIR / f"heartbeat-pulse-check-{args.date}.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    verdict = result["verdict"]
    print(f"=== heartbeat-pulse-check {args.date} ===")
    print(f"Verdict: {verdict}")
    print(f"Reason: {result['reason']}")
    print(f"Market fires: {result['market_fire_count']}")
    print(f"Max gap: {result['max_gap_minutes']} min")
    if result["sample_gaps"]:
        print(f"Notable gaps: {result['sample_gaps']}")
    print(f"Wrote: {out_path}")

    return 0 if verdict in ("GREEN", "YELLOW", "NOT_APPLICABLE") else 1


if __name__ == "__main__":
    sys.exit(main())

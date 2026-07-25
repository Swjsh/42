"""engine_liveness_check.py -- did the engine actually RUN on a day the market was open?

WHY THIS EXISTS (2026-07-24 incident, found 07-25):
On Friday 2026-07-24 the machine was off. All ~94 scheduled tasks stopped together and resumed
Saturday. `core-decisions.jsonl` recorded **0 ticks** for the day (every other trading day: 772-792).
Nothing reported it. `engine-health.json` still said GREEN 13/13 -- because every one of its checks
degrades to "(market closed -- quiet OK)" when it sees no activity, so **a dead engine and a closed
market are indistinguishable to it**. The watchdog also runs on the box it watches, so a box-level
outage can never self-report.

This module is the missing assertion: on a weekday the market was open, absence of ticks is a
FAULT, not quiet. It is pure Python, $0, no LLM, no broker, and it never raises -- callers
(daily_brief.py's EOD lead-line, self_check.py) treat a thrown exception as worse than useless, so
every failure path degrades to UNKNOWN rather than crashing the caller (C7).

Scope honesty: this cannot page J while the box is off (nothing on the box can). It makes the
NEXT run loud -- the EOD brief leads with the alarm, self-check goes DEGRADED with a real reason,
and the missed day is named. True off-box paging is a separate, still-unbuilt piece.

CLI:
  python setup/scripts/engine_liveness_check.py            # today
  python setup/scripts/engine_liveness_check.py --date 2026-07-24
  python setup/scripts/engine_liveness_check.py --lookback 7   # scan recent weekdays
Exit codes: 0 = RAN or NOT_APPLICABLE (weekend/holiday), 3 = DID_NOT_RUN, 4 = UNKNOWN.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"

# A live RTH session writes ~770-790 ticks (1/min, both accounts). Anything under this floor on an
# open weekday means the engine was absent for most of the session -- not a slow day, a dead one.
# Deliberately low: a late start or an early stop should NOT cry wolf; total/near-total absence should.
MIN_RTH_TICKS = 60

STATUS_RAN = "RAN"
STATUS_DID_NOT_RUN = "DID_NOT_RUN"
STATUS_PARTIAL = "PARTIAL"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"
STATUS_UNKNOWN = "UNKNOWN"

_EXIT = {STATUS_RAN: 0, STATUS_NOT_APPLICABLE: 0, STATUS_PARTIAL: 0,
         STATUS_DID_NOT_RUN: 3, STATUS_UNKNOWN: 4}


def _is_weekday(day: dt.date) -> bool:
    return day.weekday() < 5


def _tick_count(day: str, path: Optional[Path] = None) -> Optional[int]:
    """Count decision rows stamped with `day`. None if the ledger is unreadable (-> UNKNOWN).

    Substring prefilter before json.loads (mirrors fill_funnel._read_jsonl_day) -- the ledger is
    ~23MB and this runs inside a brief that must stay fast.
    """
    p = path or CORE_DECISIONS
    try:
        n = 0
        with open(p, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if day not in line:
                    continue
                try:
                    row = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if isinstance(row, dict) and str(row.get("ts_et", "")).startswith(day):
                    n += 1
        return n
    except OSError:
        return None


def check_day(day: str, path: Optional[Path] = None, min_ticks: int = MIN_RTH_TICKS) -> dict:
    """Liveness verdict for one ET date (YYYY-MM-DD). Never raises."""
    try:
        d = dt.date.fromisoformat(day)
    except (ValueError, TypeError):
        return {"date": day, "status": STATUS_UNKNOWN, "ticks": None,
                "reason": f"unparseable date {day!r}"}

    if not _is_weekday(d):
        return {"date": day, "status": STATUS_NOT_APPLICABLE, "ticks": None,
                "reason": "weekend -- market closed, absence is expected"}

    ticks = _tick_count(day, path)
    if ticks is None:
        return {"date": day, "status": STATUS_UNKNOWN, "ticks": None,
                "reason": "decision ledger unreadable"}
    if ticks == 0:
        # NB: a market holiday also lands here. Holidays are rare and a loud false alarm on one is
        # far cheaper than a silent miss on a real outage -- fail toward noticing.
        return {"date": day, "status": STATUS_DID_NOT_RUN, "ticks": 0,
                "reason": "weekday with ZERO engine ticks -- engine did not run "
                          "(or the market was closed for a holiday)"}
    if ticks < min_ticks:
        return {"date": day, "status": STATUS_PARTIAL, "ticks": ticks,
                "reason": f"only {ticks} ticks (< {min_ticks}) -- engine ran for part of the session"}
    return {"date": day, "status": STATUS_RAN, "ticks": ticks, "reason": f"{ticks} ticks"}


def alarm_line(result: dict) -> Optional[str]:
    """One spoken/printable line for the EOD brief, or None when nothing is wrong."""
    st = result.get("status")
    if st == STATUS_DID_NOT_RUN:
        return (f"Alarm. The engine did not run at all on {result['date']}. "
                "Zero ticks on a weekday. Check whether the machine was off.")
    if st == STATUS_PARTIAL:
        return (f"Heads up. The engine only logged {result['ticks']} ticks on {result['date']} -- "
                "it was down for part of the session.")
    if st == STATUS_UNKNOWN:
        return f"I could not verify whether the engine ran on {result['date']}."
    return None


def scan_recent(lookback_days: int, today: Optional[dt.date] = None,
                path: Optional[Path] = None) -> list:
    """Verdicts for the last `lookback_days` calendar days, newest first (weekends included so the
    caller can see them classified NOT_APPLICABLE rather than silently skipped)."""
    end = today or dt.date.today()
    return [check_day((end - dt.timedelta(days=i)).isoformat(), path)
            for i in range(lookback_days)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", default=None, help="ET date YYYY-MM-DD (default: today ET)")
    ap.add_argument("--lookback", type=int, default=0, help="scan the last N days instead")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    a = ap.parse_args(argv)

    if a.lookback:
        rows = scan_recent(a.lookback)
        if a.json:
            print(json.dumps(rows, indent=2))
        else:
            for r in rows:
                print(f"  {r['date']}  {r['status']:<16} ticks={r['ticks']}  {r['reason']}")
        worst = max((_EXIT.get(r["status"], 4) for r in rows), default=0)
        return 0 if worst == 0 else worst

    if a.date:
        day = a.date
    else:
        try:
            sys.path.insert(0, str(REPO / "setup" / "scripts"))
            from et_clock import et_today_str  # noqa: PLC0415 -- optional dep, fail-open below
            day = et_today_str()
        except Exception:  # noqa: BLE001 -- never let a clock import break the check
            day = dt.date.today().isoformat()

    res = check_day(day)
    print(json.dumps(res, indent=2) if a.json
          else f"{res['date']}  {res['status']}  ticks={res['ticks']}  {res['reason']}")
    return _EXIT.get(res["status"], 4)


if __name__ == "__main__":
    raise SystemExit(main())

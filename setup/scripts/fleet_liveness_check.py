"""fleet_liveness_check.py -- did every ENABLED fleet arm actually tick today?

WHY THIS EXISTS (same-mistake-TWICE, filed 2026-07-27 as FLEET-LIVENESS-IN-ENGINE-HEALTH):
J caught a 2-of-6 fleet-account review on 2026-06-25, and caught it AGAIN on 2026-07-27. A
memory note existed after the first incident and did not prevent the second -- per the global
CLAUDE.md rule ("same mistake twice = system failure, not model failure: encode the correction
as a rule, guard, hook, or skill"), the fix has to be structural, not a reminder.

The blind spot is a SECOND EXECUTION PATH (L244's shape): `check_engine_core` / `check_heartbeat`
in engine_health.py watch the two `mcp_heartbeat` accounts (safe-2/bold-2) via loop-state and log
activity. The other active fleet arms (safe-3, risky-1, risky-3 as of 2026-07-31) trade through
`fleet_broker` REST via `fleet_executor.py` -- a completely different code path that writes to
`automation/state/fleet/<arm_id>/decisions.jsonl` and is invisible to every mcp_heartbeat-scoped
check. "MCP is up" or "the core engines are ticking" structurally cannot prove these arms are
alive.

Mirrors `engine_liveness_check.py`'s day-not-moment pattern exactly: asks whether each watched
arm recorded >=1 decision row dated `day`, is NOT market_open-suppressed (that suppression is
what let 2026-07-24's full-day outage read GREEN 13/13), and is meant to be evaluated after the
session closes (callers should gate on >=16:05 ET, same as check_session_ran).

Only arms with status=='active' AND execution=='fleet_rest' are watched -- frozen/retired
(safe-1)/dormant/pending_build (mes-*) arms are not expected to tick, and mcp_heartbeat arms are
already covered by the existing per-heartbeat checks (double-flagging the same underlying fact
under two different check names would just be noise).

Pure stdlib, $0, never raises -- every failure path degrades to UNKNOWN (C7: fail loud in the
verdict, never crash the caller).

CLI:
  python setup/scripts/fleet_liveness_check.py
  python setup/scripts/fleet_liveness_check.py --date 2026-07-27
Exit codes: 0 = ALL_TICKED / NOT_APPLICABLE, 3 = SOME_SILENT, 4 = UNKNOWN.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
FLEET_DIR = REPO / "automation" / "state" / "fleet"
ACCOUNTS_PATH = FLEET_DIR / "accounts.json"

STATUS_ALL_TICKED = "ALL_TICKED"
STATUS_SOME_SILENT = "SOME_SILENT"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"
STATUS_UNKNOWN = "UNKNOWN"

_EXIT = {STATUS_ALL_TICKED: 0, STATUS_NOT_APPLICABLE: 0,
         STATUS_SOME_SILENT: 3, STATUS_UNKNOWN: 4}


def _is_weekday(day: dt.date) -> bool:
    return day.weekday() < 5


def _watched_arms(accounts: dict) -> list:
    """Arms this check is responsible for: status==active AND execution=='fleet_rest'.

    mcp_heartbeat arms (safe-2/bold-2) are already watched by check_engine_core/check_heartbeat
    in engine_health.py -- excluding them avoids double-flagging the same underlying liveness
    fact under two different check names. Frozen/retired/dormant/pending_build arms are not
    expected to tick at all.
    """
    out = []
    for arm in accounts.get("arms", []):
        if arm.get("status") != "active":
            continue
        if arm.get("execution") != "fleet_rest":
            continue
        out.append(arm)
    return out


def _ticked_today(arm_id: str, day: str) -> Optional[bool]:
    """True/False if `arm_id`'s decisions.jsonl has >=1 row dated `day`; None if unreadable.

    Substring prefilter before json.loads (mirrors engine_liveness_check._tick_count / the
    fill_funnel pattern) -- cheap even against a multi-thousand-row ledger.
    """
    path = FLEET_DIR / arm_id / "decisions.jsonl"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if day not in line:
                    continue
                try:
                    row = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if isinstance(row, dict) and str(row.get("ts_et", "")).startswith(day):
                    return True
        return False
    except OSError:
        return None


def check_day(day: str, accounts_path: Optional[Path] = None) -> dict:
    """Fleet-wide liveness verdict for one ET date (YYYY-MM-DD). Never raises."""
    try:
        d = dt.date.fromisoformat(day)
    except (ValueError, TypeError):
        return {"date": day, "status": STATUS_UNKNOWN, "silent_arms": [], "checked_arms": [],
                "unknown_arms": [], "reason": f"unparseable date {day!r}"}

    if not _is_weekday(d):
        return {"date": day, "status": STATUS_NOT_APPLICABLE, "silent_arms": [],
                "checked_arms": [], "unknown_arms": [],
                "reason": "weekend -- market closed, absence is expected"}

    try:
        accounts = json.loads((accounts_path or ACCOUNTS_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {"date": day, "status": STATUS_UNKNOWN, "silent_arms": [], "checked_arms": [],
                "unknown_arms": [], "reason": f"accounts.json unreadable ({type(e).__name__})"}

    watched = _watched_arms(accounts)
    checked_ids = [a.get("id", "?") for a in watched]
    if not checked_ids:
        return {"date": day, "status": STATUS_UNKNOWN, "silent_arms": [], "checked_arms": [],
                "unknown_arms": [], "reason": "no active fleet_rest arms found in accounts.json"}

    silent = []
    unknown_arms = []
    for arm_id in checked_ids:
        result = _ticked_today(arm_id, day)
        if result is None:
            unknown_arms.append(arm_id)
        elif result is False:
            silent.append(arm_id)

    if silent:
        return {"date": day, "status": STATUS_SOME_SILENT, "silent_arms": silent,
                "checked_arms": checked_ids, "unknown_arms": unknown_arms,
                "reason": f"{len(silent)}/{len(checked_ids)} fleet arm(s) recorded ZERO "
                          f"decisions today: {silent}"}
    if len(unknown_arms) == len(checked_ids):
        return {"date": day, "status": STATUS_UNKNOWN, "silent_arms": [],
                "checked_arms": checked_ids, "unknown_arms": unknown_arms,
                "reason": f"all {len(checked_ids)} watched arm ledger(s) unreadable"}
    note = f" ({len(unknown_arms)} unreadable, not flagged as silent)" if unknown_arms else ""
    return {"date": day, "status": STATUS_ALL_TICKED, "silent_arms": [],
            "checked_arms": checked_ids, "unknown_arms": unknown_arms,
            "reason": f"all {len(checked_ids) - len(unknown_arms)}/{len(checked_ids)} "
                      f"readable fleet arm(s) ticked today{note}"}


def alarm_line(result: dict) -> Optional[str]:
    """One spoken/printable line for the EOD brief, or None when nothing is wrong."""
    st = result.get("status")
    if st == STATUS_SOME_SILENT:
        return (f"Alarm. {len(result['silent_arms'])} fleet arm(s) recorded zero decisions on "
                f"{result['date']}: {result['silent_arms']}. Check fleet_executor liveness.")
    if st == STATUS_UNKNOWN:
        return f"I could not verify fleet-arm liveness on {result['date']}."
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", default=None, help="ET date YYYY-MM-DD (default: today ET)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    a = ap.parse_args(argv)

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
          else f"{res['date']}  {res['status']}  checked={res['checked_arms']}  {res['reason']}")
    return _EXIT.get(res["status"], 4)


if __name__ == "__main__":
    raise SystemExit(main())

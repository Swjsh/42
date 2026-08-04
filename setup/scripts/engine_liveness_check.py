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
from typing import Optional, Tuple

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

# --- CONTENT ALARMS (2026-08-03, PIPELINE-CHAIN-MAP silent-link closure) ---------------------
# A row-count liveness check is CONTENT-BLIND: a day of 772 armed ticks that are all
# SKIP_NO_DATA (feed dead inside a running process), all blind (key-levels.json dead), all
# vix=0.0 (yfinance outage -- which silently makes the bear VIX-floor gate unreachable AND
# leaves the bull VIX-cap wide open, a WRONG-BEHAVIOR failure, not just a no-trade one), or
# peppered with broker-infra failures on its entry attempts, reads RAN and alarms nothing.
# These tallies close that class ADDITIVELY: status/exit-code semantics are UNTOUCHED
# (fail-open -- a content alarm is a loud line on a RAN day, never a fake outage), the alarms
# ride the existing `reason` string (so every consumer that prints reason surfaces them for
# free: engine_health.check_session_ran, daily_brief's EOD lead, the CLI) plus structured
# `content` / `content_alarms` keys for machine readers. Thresholds are deliberately
# dominance-level (not one-off): a single bad tick is routine; a third of the session is a
# wall. Guard: backtest/tests/test_liveness_content_alarms_2026_08_03.py.
CONTENT_DOMINANCE_FRAC = 0.30   # >30% of armed ticks = a wall, not noise
INFRA_FAIL_MIN = 3              # >=3 entry attempts dying on infra = systemic, not a blip
_NO_DATA_VERDICTS = {"SKIP_NO_DATA", "SKIP_BAD_INPUT"}
_INFRA_EXEC_STATUSES = {"NO_CREDS", "EQUITY_FETCH_FAIL", "PLACE_FAIL", "NO_PREMIUM",
                        "SKIP_ORDER_QUERY_ERROR", "SKIP_POST_CANCEL_QUERY_ERROR",
                        "SKIP_POST_CANCEL_POSITION_QUERY_ERROR"}

_EXIT = {STATUS_RAN: 0, STATUS_NOT_APPLICABLE: 0, STATUS_PARTIAL: 0,
         STATUS_DID_NOT_RUN: 3, STATUS_UNKNOWN: 4}


def _is_weekday(day: dt.date) -> bool:
    return day.weekday() < 5


def _tick_count(day: str, path: Optional[Path] = None) -> Optional[Tuple[int, int]]:
    """(armed_ticks, diagnostic_ticks) for `day`. None if the ledger is unreadable (-> UNKNOWN).

    ARMED-ONLY IS THE LIVENESS SIGNAL (2026-08-01). The ledger also receives off-hours
    diagnostic / gym-harness calls carrying `armed: false` -- 309 of 19,625 rows repo-wide,
    and 148 on 2026-06-25 alone. Those prove a python process ran; they do NOT prove the
    ARMED RTH engine ran, which is the only thing this alarm exists to assert. Counting them
    would let a genuinely dead weekday that happened to catch a large diagnostic sweep read
    RAN and alarm nothing -- the exact silent-miss class this module was built for after the
    2026-07-24 outage. Verified when this changed: no weekday's verdict moves today (all
    current diagnostic-heavy days also have a full 758-772 armed ticks); this closes a LATENT
    hole, it did not fix a live misread. Same `armed is True` convention as
    gate_expiry_check.py and monday_verify.py.

    Diagnostic rows are still COUNTED and REPORTED so a human reading a DID_NOT_RUN sees
    "0 armed / 148 diagnostic" rather than a bare zero that looks like a missing file.

    Substring prefilter before json.loads (mirrors fill_funnel._read_jsonl_day) -- the ledger is
    ~23MB and this runs inside a brief that must stay fast.
    """
    p = path or CORE_DECISIONS
    try:
        armed = diagnostic = 0
        # CONTENT ALARMS (2026-08-03): tallied in the SAME single pass (the ledger is ~23MB
        # and this runs inside a brief that must stay fast) -- armed rows only, matching the
        # liveness signal itself. Each tally is guarded on the field EXISTING so pre-schema
        # rows can never inflate a count (consumers must treat missing as "older row shape").
        content = {"no_data": 0, "blind": 0, "vix_zero": 0, "infra_fail": 0}
        with open(p, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if day not in line:
                    continue
                try:
                    row = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if isinstance(row, dict) and str(row.get("ts_et", "")).startswith(day):
                    if row.get("armed") is True:
                        armed += 1
                        if str(row.get("verdict", "")) in _NO_DATA_VERDICTS:
                            content["no_data"] += 1
                        if row.get("blind") is True:
                            content["blind"] += 1
                        _vix = row.get("vix")
                        if isinstance(_vix, (int, float)) and float(_vix) == 0.0:
                            content["vix_zero"] += 1
                        _exec = row.get("exec")
                        if (isinstance(_exec, dict)
                                and str(_exec.get("status", "")) in _INFRA_EXEC_STATUSES):
                            content["infra_fail"] += 1
                    else:
                        diagnostic += 1
        return armed, diagnostic, content
    except OSError:
        return None


def _content_alarms(ticks: int, content: dict) -> list:
    """Named alarm strings for a day whose ARMED rows are dominated by a silent-failure
    shape. Empty list on a healthy day, on ticks==0 (liveness itself already alarms), and on
    any malformed input (fail-open: this must never invent an alarm or raise)."""
    try:
        if not ticks or not isinstance(content, dict):
            return []
        alarms = []
        if content.get("no_data", 0) / ticks > CONTENT_DOMINANCE_FRAC:
            alarms.append(f"FEED_DEAD_INSIDE_RUNNING_ENGINE: {content['no_data']}/{ticks} "
                          "armed ticks were SKIP_NO_DATA/SKIP_BAD_INPUT (bars feed or "
                          "engine_cli dead while the process ticked)")
        if content.get("blind", 0) / ticks > CONTENT_DOMINANCE_FRAC:
            alarms.append(f"BLIND: {content['blind']}/{ticks} armed ticks had empty "
                          "levels_active (key-levels.json stale/unrefreshed -- check "
                          "Gamma_LevelRefresh)")
        if content.get("vix_zero", 0) / ticks > CONTENT_DOMINANCE_FRAC:
            alarms.append(f"VIX_FEED_DEAD: {content['vix_zero']}/{ticks} armed ticks carried "
                          "vix=0.0 (the _fetch_vix fallback) -- bear VIX-floor gate silently "
                          "unreachable AND bull VIX-cap silently open; wrong-behavior, not "
                          "just no-trade")
        if content.get("infra_fail", 0) >= INFRA_FAIL_MIN:
            alarms.append(f"BROKER_INFRA_FAILURES: {content['infra_fail']} entry attempts "
                          "died on creds/equity/quote/placement errors "
                          f"({sorted(_INFRA_EXEC_STATUSES)} class)")
        return alarms
    except Exception:  # noqa: BLE001 -- alarm derivation must never crash the caller
        return []


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

    counts = _tick_count(day, path)
    if counts is None:
        return {"date": day, "status": STATUS_UNKNOWN, "ticks": None, "diagnostic_ticks": None,
                "reason": "decision ledger unreadable"}
    ticks, diagnostic, content = counts
    # Surfaced on every verdict so a bare 0 is never confused with a missing/!empty ledger.
    diag_note = f" ({diagnostic} unarmed diagnostic rows present)" if diagnostic else ""
    if ticks == 0:
        # NB: a market holiday also lands here. Holidays are rare and a loud false alarm on one is
        # far cheaper than a silent miss on a real outage -- fail toward noticing.
        return {"date": day, "status": STATUS_DID_NOT_RUN, "ticks": 0,
                "diagnostic_ticks": diagnostic,
                "reason": "weekday with ZERO armed engine ticks -- engine did not run "
                          f"(or the market was closed for a holiday){diag_note}"}
    # CONTENT ALARMS (2026-08-03): folded into `reason` so every consumer that prints reason
    # surfaces them for free; ALSO structured keys for machine readers. Status/exit code are
    # deliberately UNTOUCHED (fail-open): a content-degraded day still RAN.
    alarms = _content_alarms(ticks, content)
    alarm_note = f"; CONTENT ALARMS: {' | '.join(alarms)}" if alarms else ""
    if ticks < min_ticks:
        return {"date": day, "status": STATUS_PARTIAL, "ticks": ticks,
                "diagnostic_ticks": diagnostic,
                "content": content, "content_alarms": alarms,
                "reason": f"only {ticks} armed ticks (< {min_ticks}) -- engine ran for part "
                          f"of the session{diag_note}{alarm_note}"}
    return {"date": day, "status": STATUS_RAN, "ticks": ticks, "diagnostic_ticks": diagnostic,
            "content": content, "content_alarms": alarms,
            "reason": f"{ticks} armed ticks{diag_note}{alarm_note}"}


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
    # CONTENT ALARMS (2026-08-03): a day that RAN but was dominated by a silent-failure shape
    # still gets a spoken line -- that is the entire point of the content pass (a dead feed
    # inside a running process must not read as quiet health).
    alarms = result.get("content_alarms") or []
    if alarms:
        return (f"Heads up. The engine ran on {result['date']} but the ledger content is "
                f"degraded: {'; '.join(alarms)}")
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

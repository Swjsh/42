"""first_live_day_review.py -- mechanical, repeatable replacement for the manual
"09-02 16:30 ET first-live-day review (Opus, 20 min)" box in
markdown/planning/OPUS-WORK-ORDER-2026-09.md #1.

WHY THIS EXISTS: that work-order item is a checklist a human has to remember to run and
read by hand. Section 5's own cadence rule says recurring work becomes a $0 script. This
is that script -- it reads the same state files the manual review would have, applies the
same pass/fail logic, and never gets skipped because someone forgot or ran out of the
20 minutes.

THE CHECKS (see the work order + this file's own docstrings on each function):
  1. dms_cadence            -- did Gamma_DeadMansSwitch fire on its ~2min cadence
                                09:32-15:58 ET? Any gap > 4 minutes is enumerated (a
                                missed fire is the thing that matters, not the total).
  2. dms_verdicts            -- every DMS row should be LIVE_NO_ACTION/STALE_BUT_FLAT.
                                FLATTENED/ERROR/NO_CREDS/READ_FAILED are all failures (the
                                work order's own text only names FLATTENED/ERROR --
                                NO_CREDS and READ_FAILED are silent-failure modes a DMS
                                that can't read the broker is not a DMS). DMS_DRY /
                                DRY_RUN_WOULD_FLATTEN are flagged separately as "not
                                actually armed".
  3. engine_health           -- escalation_flags + duplicate_ticks GREEN in
                                engine-health.json.
  4. eod_flatten_aggressive  -- did Gamma_EodFlatten_Aggressive (the LLM defense-in-depth
                                flattener) reach the broker at 15:55? The Core Python
                                flattener (eod_flatten.py, Gamma_EodFlattenCore, 15:52 ET)
                                is PRIMARY -- the LLM flatteners defer to it -- so this
                                check reports the Core's bold-2 outcome as authoritative
                                and the LLM log's own outcome as a named, loud, secondary
                                finding (it has failed 2 days running as of 2026-09-01;
                                see the quoted log in this repo's session notes).
  5. conductor_picks         -- ADVISORY/heuristic only (STATUS.md prose, not a structured
                                ledger): did any overnight conductor fire in the window
                                before this review's RTH start pick a GATE-BLOCKING queue
                                item over something lower-priority while one was open?
                                Never gates the overall verdict -- textual signal only.
  6. fleet_kill_switch       -- Rule 5 (-30% Safe / -50% Bold... here -30%/-50% per each
                                fleet arm's own daily_loss_limit_pct) is NOT latched on
                                fleet arms yet (built on unmerged branch
                                safety-bundle-2026-09-29). For each ACTIVE fleet_rest arm
                                (accounts.json, execution=='fleet_rest', status=='active'
                                -- excludes the two core mcp_heartbeat arms, which DO have
                                daily_loss_guard.py wired), reports the day's minimum
                                observed equity (from that arm's own decisions.jsonl
                                'equity' field) as a % draw from starting_equity_today, and
                                the headroom left before the account's own
                                daily_loss_limit_pct floor.
  7. guards_full             -- did Gamma_GuardsFull (setup/guard_runner_full.py) produce
                                a verdict recently? Expected steady-state failure count is
                                0, lowered from 4 on 2026-09-02 ON EVIDENCE: a full run at
                                11:09 ET that day returned 11739 passed / 0 failed / rc=0,
                                so the four tolerated failures (3x cheap_contract_qty_boost
                                stale fixtures + 1 order-dependent test_graduated_guards.py
                                case) were all repaired, not merely re-baselined. Any other
                                count, or no verdict at all, is flagged.

DESIGN RULE (OP-33 / C7 -- a check that could not run is NOT a pass): every loader in this
file returns None on a missing/unreadable file, and every check function treats None (or
an empty row list standing in for "nothing was ever written") as a FAILURE with an
explicit reason, never as a silent GREEN. This mirrors the documented guard_runner_full.py
scar this repo has already been burned by once: a report that goes nowhere manufactures
the belief something was watching. The one deliberate exception is the fleet-equity check
(#6), which can legitimately have NO DATA YET before the market opens -- that reports its
own 'NO_DATA' status (distinct from both PASS and FAIL, mirroring monday_verify.py's
NOT_EXERCISED convention) rather than being coerced into either.

READ-ONLY. Places no order, mutates no trading state, writes only its own artifact
(analysis/first-live-day/<date>.{json,md}) and stdout. Never touches STATUS.md, never
touches params*.json, never edits any frozen/gitignored config file.

CLI:
    backtest\\.venv\\Scripts\\python.exe setup\\scripts\\first_live_day_review.py [--date YYYY-MM-DD]

Default date = today's ET date (et_clock.et_today_str() -- NEVER Bash TZ, this box runs
Mountain Time and `TZ=America/New_York date` returns UTC here).

Guard: backtest/tests/test_first_live_day_review_2026_09_02.py.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

# ---- path setup (mirrors dead_mans_switch.py / eod_flatten.py pattern) -------------------
_SCRIPTS = Path(__file__).resolve().parent
_REPO = _SCRIPTS.parents[1]
for _p in ("setup/scripts",):
    _pp = str(_REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

from et_clock import et_now, et_today_str  # noqa: E402 (from setup/scripts)

# ---- module-level path constants (redirectable by tests, mirrors dms.py's fake_env) ------
DMS_LOG_DIR = _REPO / "automation" / "state" / "logs"
DMS_STATE_PATH = _REPO / "automation" / "state" / "dead-mans-switch.json"
ENGINE_HEALTH_PATH = _REPO / "automation" / "state" / "engine-health.json"
GUARDS_FULL_PATH = _REPO / "automation" / "state" / "guard-watch-full.json"
ACCOUNTS_PATH = _REPO / "automation" / "state" / "fleet" / "accounts.json"
FLEET_DIR = _REPO / "automation" / "state" / "fleet"
EOD_LOG_DIR = _REPO / "automation" / "state" / "logs"
STATUS_MD_PATH = _REPO / "automation" / "overnight" / "STATUS.md"
QUEUE_MD_PATH = _REPO / "automation" / "overnight" / "queue.md"
OUT_DIR = _REPO / "analysis" / "first-live-day"
# FIRST-LIVE-DAY-REVIEW-RUN-LOG (queue.md 2026-09-02): write_outputs() below writes ONE
# artifact per review_date, so a later invocation on the same date silently overwrites an
# earlier one -- happened live 2026-09-02, where a direct 23:37 ET run overwrote the
# 16:30 ET scheduled fire's own output with no record either run had happened.
# append_run_log() (below) writes `<OUT_DIR>/runs.jsonl` -- a permanent, append-only log
# of EVERY invocation, never touched by write_outputs() -- so "did today's fire produce a
# verdict" never again has to be answered by inference. Computed from OUT_DIR at call
# time (not a separate module constant) so it stays redirectable the same way every other
# path here is, e.g. by tests monkeypatching OUT_DIR.

# ---- config (from dead_mans_switch.py -- kept in sync, not re-derived by guesswork) -------
RTH_START = (9, 32)
RTH_END = (15, 58)
DMS_CADENCE_MIN = 2
GAP_THRESHOLD_MIN = 4          # a gap this big or bigger is enumerated by name
SAME_FIRE_CLUSTER_S = 90       # rows within this many seconds are the SAME fire (multi-arm)

# NOT_YET status config (FIRST-LIVE-DAY-REVIEW-CANNOT-TELL-NOT-YET-FROM-FAILED, queue.md
# 2026-09-02): each day-scoped check below declares the ET time on the REVIEW DATE after
# which missing evidence (0 rows / no confirmed flatten) is treated as a real failure. Before
# that time, missing evidence grades NOT_YET instead of RED -- ranked with NO_DATA/ADVISORY
# (never GREEN, never RED; see combine_verdict) so a manual mid-morning run, or an early
# scheduled fire, stops crying "RED" about a session that has not reached that checkpoint
# yet. `check_fleet_kill_switch_proximity` already had the right idea (its own NO_DATA
# "before the open this is expected" state) -- this generalizes the same idea, uniformly, to
# the two checks that were still reporting RED for "too early".
DMS_CADENCE_NOT_YET_AFTER = (9, 35)     # DMS's first scheduled fire is 09:32 -- one cadence
                                         # interval (2min) of slack before 0 rows is real.
DMS_VERDICTS_NOT_YET_AFTER = RTH_START  # (9, 32) -- DMS's own first expected tick.
EOD_FLATTEN_NOT_YET_AFTER = (15, 56)    # Core sweep (Gamma_EodFlattenCore) fires 15:52; a
                                         # minute of slack before "no row yet" is real.

DMS_GOOD_ACTIONS = {"LIVE_NO_ACTION", "STALE_BUT_FLAT"}
DMS_BAD_ACTIONS = {"FLATTENED", "ERROR", "NO_CREDS", "READ_FAILED", "DRY_RUN_WOULD_FLATTEN"}
# DRY_RUN_WOULD_FLATTEN is in BOTH camps: the underlying condition (stale + open position)
# is itself the bad thing DMS exists to catch, dry mode or not -- so it counts as a bad row
# AND (below) as a not-really-armed row.

# Known-failure tolerance. 4 -> 0 on 2026-09-02, ON EVIDENCE.
#
# A tolerance that outlives its reason is a laundering mechanism: at 4 this check reported
# GREEN for any FOUR failures, including four brand-new real ones -- the exact "fresh-looking
# count" the 16:30 review exists not to launder. The four it was sized for were three
# cheap-contract-boost fixtures predating the 2026-08-29 tight-ladder ceiling plus one other,
# all repaired in fb34ca92.
#
# It was NOT lowered when those were fixed, deliberately: the full suite had not been observed
# green, and setting 0 on an unverified suite risks a permanently-YELLOW check -- the same
# disease inverted. That premise is now discharged. The 2026-09-02 11:09 ET run came back
# **11,739 passed / 0 failed / 11 skipped, rc=0** after all seven failures were repaired
# (4 prereg status assertions, 1 clock-dependent quiet-mode test, 1 Kalshi lane caught up,
# 1 sys.modules leak between test files).
#
# 0 means "any failure is worth a human look", which is the only defensible value once the
# known set is empty. If a future run is legitimately expected to carry known failures, raise
# this ONLY with the specific test names written down beside it -- a bare number is how it
# went stale the first time.
GUARDS_FULL_EXPECTED_FAILED = 0
GUARDS_FULL_STALE_DAYS = 2      # >= this many days old -> flagged stale (nightly cadence
                                 # naturally puts a healthy run 0-1 days behind each morning)

# A REHEARSAL IS NOT EVIDENCE OF A FLATTEN (2026-09-02). "DRY_RUN" was in this set, and
# nothing filtered `dry: true` rows, so a drill row satisfied the one check standing between
# an unflattened 0DTE position and an overnight hold. Caught live: an early-close flatten
# REHEARSAL at 06:14 ET wrote four `dry:true / outcome:NOOP` rows stamped 12:45 ET into the
# production ledger, and at 11:12 ET -- with the real 15:52 sweep still hours away -- the
# review already read "Core flatten confirmed flat for bold-2 (NOOP)" and graded the day
# GREEN. Every genuine production row since 2026-08-21 is `dry: False` at 15:52, so
# excluding rehearsals costs no real evidence.
EOD_CORE_GOOD_OUTCOMES = {"NOOP", "SUCCESS"}
EOD_AGG_FAIL_MARKERS = ("ABORTED", "KILL_SWITCH_SET", "TIMEOUT_KILL", "MCP_UNREACHABLE",
                         "exit=1", "exit=124")
EOD_AGG_OK_MARKER = "END tick exit=0"


# ============================================================================
# small generic I/O helpers -- every one returns None on any failure, NEVER raises,
# NEVER silently substitutes a fake-plausible value (C7 / judgment-guards failure-honesty).
# ============================================================================

def read_json(path: Path) -> Optional[dict]:
    try:
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return None
        return json.loads(text)
    except (OSError, ValueError):
        return None


def read_jsonl(path: Path) -> list[dict]:
    """Returns [] on a missing/empty/unreadable file. Callers must treat [] as 'nothing
    was ever recorded' -- NOT as a passing/clean result -- this is the load-bearing
    distinction the whole review depends on (see module docstring's design rule)."""
    out: list[dict] = []
    try:
        if not path.exists():
            return out
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue
    except OSError:
        return []
    return out


def read_text(path: Path) -> Optional[str]:
    try:
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def jsonl_rows_for_date(rows: list[dict], review_date: str, ts_field: str = "ts_et") -> list[dict]:
    """Filters rows whose ts_field starts with review_date (YYYY-MM-DD). Tolerates both
    naive ('2026-09-02 09:32:00 ET') and ISO-offset ('2026-09-02T09:32:00-04:00')
    timestamp shapes -- only the first 10 chars are compared, and both shapes put the date
    there."""
    out = []
    for r in rows:
        ts = r.get(ts_field)
        if isinstance(ts, str) and ts[:10] == review_date:
            out.append(r)
    return out


# ============================================================================
# check 1+2: dead-man's switch cadence + verdicts
# ============================================================================

def _parse_dms_ts(ts: Any) -> Optional[datetime]:
    """DMS rows stamp ts as 'YYYY-MM-DD HH:MM:SS ET' (dead_mans_switch.py's _et_ts()).
    Returns None (never raises) on any other shape."""
    if not isinstance(ts, str):
        return None
    try:
        return datetime.strptime(ts.replace(" ET", ""), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def expected_dms_fire_count(rth_start: tuple = RTH_START, rth_end: tuple = RTH_END,
                             cadence_min: int = DMS_CADENCE_MIN) -> int:
    """Computed, never hardcoded (194 is the answer on a normal 09:32-15:58 day, but this
    must recompute it so a window change is never silently stale)."""
    start_min = rth_start[0] * 60 + rth_start[1]
    end_min = rth_end[0] * 60 + rth_end[1]
    total_min = end_min - start_min
    if total_min < 0:
        return 0
    return (total_min // cadence_min) + 1  # inclusive of the first fire at rth_start


def cluster_fire_times(timestamps: list[datetime],
                        same_fire_window_s: int = SAME_FIRE_CLUSTER_S) -> list[datetime]:
    """One DMS 'fire' writes one row PER ARM in quick succession (sub-second to a few
    seconds apart); DIFFERENT fires are ~120s apart. Clusters rows into fires by treating
    consecutive timestamps closer than same_fire_window_s as the SAME fire, and returns one
    representative time (the first row) per cluster, sorted."""
    if not timestamps:
        return []
    ordered = sorted(timestamps)
    clusters: list[datetime] = [ordered[0]]
    for ts in ordered[1:]:
        if (ts - clusters[-1]).total_seconds() > same_fire_window_s:
            clusters.append(ts)
        # else: same fire as the cluster's representative time -- skip
    return clusters


def _not_yet_before(review_date: Optional[str], after: tuple,
                     now: "datetime | None" = None) -> Optional[str]:
    """Returns 'HH:MM ET on <review_date>' when `now` is still before that cutoff time ON
    review_date (evidence not expected yet), else None (the cutoff has passed -- missing
    evidence is a real finding, not a timing artifact). Returns None whenever review_date is
    unknown/malformed (can't judge time without a date to anchor it) -- callers then fall
    back to the pre-existing RED behavior, never silently invent a NOT_YET.

    `now` follows check_dms_cadence's own established convention (INJECTED for
    determinism; defaults to the wall clock) rather than a new one."""
    if review_date is None:
        return None
    try:
        y, m, d = (int(x) for x in review_date.split("-"))
        cutoff = datetime(y, m, d, after[0], after[1])
    except (ValueError, TypeError):
        return None
    at = now if now is not None else datetime.now()
    if at < cutoff:
        return f"{after[0]:02d}:{after[1]:02d} ET on {review_date}"
    return None


def check_dms_cadence(rows: list[dict], review_date: str,
                       rth_start: tuple = RTH_START, rth_end: tuple = RTH_END,
                       cadence_min: int = DMS_CADENCE_MIN,
                       gap_threshold_min: int = GAP_THRESHOLD_MIN,
                       now: "datetime | None" = None) -> dict:
    """Did Gamma_DeadMansSwitch fire on cadence? Enumerates any gap > gap_threshold_min,
    including a leading gap (window start -> first fire) and trailing gap (last fire ->
    window end) -- a switch that stopped firing after lunch shows no BETWEEN-fire gap
    unless the tail is checked too."""
    expected = expected_dms_fire_count(rth_start, rth_end, cadence_min)
    if not rows:
        not_yet = _not_yet_before(review_date, DMS_CADENCE_NOT_YET_AFTER, now)
        if not_yet is not None:
            return {
                "status": "NOT_YET",
                "reason": f"no DMS rows yet -- evidence expected after {not_yet}",
                "expected_fires": expected,
                "actual_fires": 0,
                "gaps": [],
            }
        return {
            "status": "RED",
            "reason": "never fired -- 0 rows in the dead-man's-switch log for this date",
            "expected_fires": expected,
            "actual_fires": 0,
            "gaps": [],
        }

    times = [t for t in (_parse_dms_ts(r.get("ts")) for r in rows) if t is not None]
    if not times:
        return {
            "status": "RED",
            "reason": "rows present but none had a parseable 'ts' -- treated as never fired",
            "expected_fires": expected,
            "actual_fires": 0,
            "gaps": [],
        }

    all_fires = cluster_fire_times(times)
    date_ref = all_fires[0].replace(hour=0, minute=0, second=0, microsecond=0)
    window_start = date_ref.replace(hour=rth_start[0], minute=rth_start[1])
    window_end = date_ref.replace(hour=rth_end[0], minute=rth_end[1])

    # ONLY FIRES INSIDE THE TASK'S OWN WINDOW ARE CADENCE EVENTS (2026-09-02).
    # Gamma_DeadMansSwitch is scheduled 09:32-15:58 ET. A row outside that window is a
    # manual or rehearsal run -- and the DMS gained an explicit out-of-hours DRY rehearsal
    # path the day before this check first ran, so such rows exist by design. Counting them
    # as cadence events invents a gap between the rehearsal and the first real fire: a
    # 06:10 pre-flight produced a bogus "201.8 min between-fires gap" and turned the whole
    # review RED on the DMS's first production day. Excluded-and-counted, never dropped
    # silently.
    fires = [f for f in all_fires if window_start <= f <= window_end]
    out_of_window = len(all_fires) - len(fires)
    if not fires:
        return {
            "status": "RED",
            "reason": (f"no fire landed inside the {rth_start[0]:02d}:{rth_start[1]:02d}-"
                       f"{rth_end[0]:02d}:{rth_end[1]:02d} window "
                       f"({out_of_window} out-of-window row(s) ignored)"),
            "expected_fires": expected, "actual_fires": 0,
            "out_of_window_fires": out_of_window, "gaps": [],
        }

    gaps: list[dict] = []

    def _maybe_gap(a: datetime, b: datetime, label: str) -> None:
        gap_min = (b - a).total_seconds() / 60.0
        if gap_min > gap_threshold_min:
            gaps.append({"from": a.strftime("%H:%M:%S"), "to": b.strftime("%H:%M:%S"),
                         "gap_min": round(gap_min, 1), "kind": label})

    _maybe_gap(window_start, fires[0], "startup")
    for a, b in zip(fires, fires[1:]):
        _maybe_gap(a, b, "between-fires")

    # The TRAILING gap is only meaningful once the window has actually closed. This review
    # is scheduled for 16:30 ET, after 15:58, so in production it always is -- but a mid-day
    # re-run would otherwise report the entire remaining session as a "gap" (a 10:47 run
    # produced a bogus 312-minute trailing gap). Judge the tail only when there IS a tail.
    # `now` is INJECTED so this stays deterministic. Defaulting to the wall clock and
    # leaving it at that is the same time-dependence that made
    # test_gaming_outside_the_research_band_still_blacks_out pass only outside market hours.
    at = now or datetime.now()
    window_closed = at >= window_end
    if window_closed:
        _maybe_gap(fires[-1], window_end, "trailing")

    status = "RED" if gaps else "GREEN"
    reason = (f"{len(gaps)} gap(s) > {gap_threshold_min}min found" if gaps
              else "fired on cadence, no gap exceeded the threshold")
    if not window_closed:
        reason += " (window still open -- trailing gap not judged yet)"
    if out_of_window:
        reason += f"; {out_of_window} out-of-window row(s) ignored (rehearsal/manual)"
    return {
        "status": status,
        "reason": reason,
        "expected_fires": expected,
        "actual_fires": len(fires),
        "out_of_window_fires": out_of_window,
        "window_closed": window_closed,
        "gaps": gaps,
    }


def _split_by_window(rows: list[dict], rth_start: tuple = RTH_START,
                     rth_end: tuple = RTH_END) -> "tuple[list, list]":
    """(in_window, out_of_window) by each row's `ts`. Unparseable ts counts as IN-window --
    fail toward scrutiny, never toward silently discarding a row we could not read."""
    inw, out = [], []
    for r in rows:
        t = _parse_dms_ts(r.get("ts"))
        if t is None:
            inw.append(r)
            continue
        start = t.replace(hour=rth_start[0], minute=rth_start[1], second=0, microsecond=0)
        end = t.replace(hour=rth_end[0], minute=rth_end[1], second=0, microsecond=0)
        (inw if start <= t <= end else out).append(r)
    return inw, out


def check_dms_verdicts(rows: list[dict], rth_start: tuple = RTH_START,
                        rth_end: tuple = RTH_END, review_date: Optional[str] = None,
                        now: "datetime | None" = None) -> dict:
    """Every row's `action` should be LIVE_NO_ACTION or STALE_BUT_FLAT. Anything in
    DMS_BAD_ACTIONS is a failure (work order text only calls out FLATTENED/ERROR --
    NO_CREDS and READ_FAILED are added here per this task's own instruction: a DMS that
    cannot read the broker is not a DMS). A `dry: true` row (or a DRY_RUN_WOULD_FLATTEN
    action) is flagged separately as 'not actually armed', regardless of whether it also
    counts as bad.

    `review_date`/`now` are optional (default None): when both are supplied and `now`
    precedes DMS_VERDICTS_NOT_YET_AFTER on review_date, a 0-rows-inside-the-window result
    grades NOT_YET instead of RED (see module NOT_YET config). Omitting review_date keeps
    the original RED-always behavior -- there is no date to judge "too early" against."""
    # OUT-OF-WINDOW ROWS ARE REHEARSALS, NOT PRODUCTION FIRES (2026-09-02). The DMS gained
    # an out-of-hours DRY rehearsal path the day before this check first ran, precisely so a
    # safety instrument could be exercised before trusting it in production. Counting those
    # rows here reports "the DMS was NOT armed" about fires that were never meant to be:
    # a 06:10 pre-flight (4 rows, one per arm) turned this YELLOW on the switch's first
    # production day, while every real fire from 09:32 onward was armed. Excluded and
    # COUNTED -- the disclosure stays in the reason string.
    rows, out_rows = _split_by_window(rows, rth_start, rth_end)
    n_out = len(out_rows)
    if not rows:
        not_yet = _not_yet_before(review_date, DMS_VERDICTS_NOT_YET_AFTER, now)
        if not_yet is not None:
            return {"status": "NOT_YET",
                    "reason": (f"no DMS rows yet inside the window -- evidence expected "
                               f"after {not_yet}"
                               + (f" ({n_out} out-of-window rehearsal row(s) ignored)" if n_out else "")),
                    "bad_rows": [], "not_armed_rows": [], "per_arm_actions": {},
                    "out_of_window_rows": n_out}
        return {"status": "RED",
                "reason": ("never fired inside the window -- 0 rows to verify"
                           + (f" ({n_out} out-of-window rehearsal row(s) ignored)" if n_out else "")),
                "bad_rows": [], "not_armed_rows": [], "per_arm_actions": {},
                "out_of_window_rows": n_out}

    bad_rows: list[dict] = []
    not_armed_rows: list[dict] = []
    per_arm_actions: dict[str, list[str]] = {}

    for r in rows:
        arm = r.get("arm", "?")
        action = r.get("action")
        per_arm_actions.setdefault(arm, []).append(action)

        if r.get("dry") is True or action == "DRY_RUN_WOULD_FLATTEN":
            not_armed_rows.append({"arm": arm, "ts": r.get("ts"), "action": action})

        if action in DMS_BAD_ACTIONS:
            bad_rows.append({"arm": arm, "ts": r.get("ts"), "action": action})
        elif action not in DMS_GOOD_ACTIONS:
            # unknown/unexpected vocabulary -- fail loud rather than silently accept it
            bad_rows.append({"arm": arm, "ts": r.get("ts"), "action": action,
                              "note": "unrecognized action -- not in the documented vocabulary"})

    if bad_rows:
        status = "RED"
        reason = f"{len(bad_rows)} bad row(s): " + ", ".join(
            sorted({f"{b['action']}" for b in bad_rows}))
    elif not_armed_rows:
        status = "YELLOW"
        reason = (f"{len(not_armed_rows)} row(s) ran in DRY mode -- DMS was NOT actually "
                  f"armed for those fires")
    else:
        status = "GREEN"
        reason = "every row LIVE_NO_ACTION/STALE_BUT_FLAT, none in dry mode"

    if n_out:
        reason += f"; {n_out} out-of-window rehearsal row(s) ignored"

    return {"status": status, "reason": reason, "bad_rows": bad_rows,
            "not_armed_rows": not_armed_rows, "per_arm_actions": per_arm_actions,
            "out_of_window_rows": n_out}


# ============================================================================
# check 3: engine_health.py's escalation_flags + duplicate_ticks
# ============================================================================

def check_engine_health(engine_health: Optional[dict]) -> dict:
    if engine_health is None:
        return {"status": "RED", "reason": "engine-health.json missing/unreadable",
                "escalation_flags": None, "duplicate_ticks": None}

    by_name = {c.get("name"): c for c in engine_health.get("checks", []) if isinstance(c, dict)}
    watched = ("escalation_flags", "duplicate_ticks")
    sub = {}
    worst = "GREEN"
    order = {"GREEN": 0, "YELLOW": 1, "RED": 2}
    missing = []
    for name in watched:
        c = by_name.get(name)
        if c is None:
            sub[name] = None
            missing.append(name)
            worst = "RED"
            continue
        st = str(c.get("status", "RED")).upper()
        sub[name] = {"status": st, "detail": c.get("detail")}
        if order.get(st, 2) > order.get(worst, 0):
            worst = st

    if missing:
        reason = f"check(s) not found in engine-health.json: {', '.join(missing)}"
    else:
        bad = [n for n in watched if sub[n]["status"] != "GREEN"]
        reason = (f"{', '.join(bad)} not GREEN" if bad else "escalation_flags + duplicate_ticks both GREEN")

    return {"status": worst, "reason": reason, "escalation_flags": sub.get("escalation_flags"),
            "duplicate_ticks": sub.get("duplicate_ticks")}


# ============================================================================
# check 4: EOD flatten -- Core (primary) + Aggressive LLM (secondary/loud)
# ============================================================================

def check_eod_flatten_aggressive(core_rows_for_date: list[dict],
                                  agg_log_text: Optional[str],
                                  arm: str = "bold-2",
                                  review_date: Optional[str] = None,
                                  now: "datetime | None" = None) -> dict:
    """Core (eod_flatten.py, Gamma_EodFlattenCore, 15:52 ET) is PRIMARY -- it covers
    bold-2 in the same sweep as every other active arm. Gamma_EodFlatten_Aggressive (the
    LLM defense-in-depth flattener, 15:55 ET) is checked too and reported LOUDLY if it
    failed, but a Core success is what actually protects the account, so it alone drives
    this check's pass/fail status.

    `review_date`/`now` are optional (default None): when both are supplied and `now`
    precedes EOD_FLATTEN_NOT_YET_AFTER on review_date, a MISSING/MISSING_ONLY_REHEARSALS
    result (no real Core row yet) grades NOT_YET instead of RED. A real row that FAILED
    (READ_FAILED, DRY_RUN outcome, etc.) is never reclassified this way -- that is genuine
    evidence of a problem, not an absence of evidence."""
    all_arm_rows = [r for r in core_rows_for_date if r.get("arm") == arm]
    # Rehearsal rows are excluded from evidence but COUNTED, so the reason can say why a
    # populated-looking ledger produced no verdict. Silently dropping them would reproduce
    # the original failure in a quieter form: a ledger with four rows in it reading MISSING
    # with no explanation is a report an operator argues with instead of acting on.
    def _is_rehearsal(r: dict) -> bool:
        return r.get("dry") is True or r.get("outcome") == "DRY_RUN"

    core_arm_rows = [r for r in all_arm_rows if not _is_rehearsal(r)]
    n_reh = len(all_arm_rows) - len(core_arm_rows)
    if not core_arm_rows:
        core_result = "MISSING_ONLY_REHEARSALS" if n_reh else "MISSING"
        core_ok = False
    else:
        # last row for the arm this date (retries can write more than one)
        outcome = core_arm_rows[-1].get("outcome")
        core_result = outcome
        core_ok = outcome in EOD_CORE_GOOD_OUTCOMES

    agg_status = "UNKNOWN"
    agg_evidence: list[str] = []
    if agg_log_text is None:
        agg_status = "NO_LOG"
    else:
        found_fail = [m for m in EOD_AGG_FAIL_MARKERS if m in agg_log_text]
        found_ok = EOD_AGG_OK_MARKER in agg_log_text
        if found_fail:
            agg_status = "FAILED"
            agg_evidence = found_fail
        elif found_ok:
            agg_status = "OK"
        else:
            agg_status = "INCONCLUSIVE"

    _reh = (f" [{n_reh} DRY-RUN rehearsal row(s) present and IGNORED -- a rehearsal "
            f"flattens nothing]" if n_reh else "")
    if not core_ok:
        not_yet = (_not_yet_before(review_date, EOD_FLATTEN_NOT_YET_AFTER, now)
                   if core_result in ("MISSING", "MISSING_ONLY_REHEARSALS") else None)
        if not_yet is not None:
            status = "NOT_YET"
            reason = (f"no Core flatten evidence yet for {arm} (outcome={core_result}) -- "
                      f"evidence expected after {not_yet}{_reh}")
        else:
            status = "RED"
            reason = f"Core flatten did not confirm flat for {arm}: outcome={core_result}{_reh}"
    elif agg_status == "FAILED":
        status = "YELLOW"
        reason = (f"Core flatten OK ({core_result}) so {arm} is confirmed flat, but "
                  f"Gamma_EodFlatten_Aggressive (LLM) itself FAILED "
                  f"(evidence: {', '.join(agg_evidence)}) -- named per work-order 3rd-day-"
                  f"of-concern instruction")
    else:
        status = "GREEN"
        reason = f"Core flatten confirmed flat for {arm} ({core_result}){_reh}"

    return {"status": status, "reason": reason, "core_outcome": core_result,
            "core_confirmed_flat": core_ok, "agg_llm_status": agg_status,
            "agg_llm_evidence": agg_evidence, "rehearsal_rows_ignored": n_reh}


# ============================================================================
# check 5: conductor picks -- ADVISORY ONLY (textual/heuristic, never gates the verdict)
# ============================================================================

_STATUS_HEADER_RE = re.compile(
    r"^## \[(?P<date>\d{4}-\d{2}-\d{2})T(?P<hh>\d{2}):(?P<mm>\d{2})(?::\d{2})? ET\]"
    r"(?P<rest>.*)$")
# Conductor fires are written as top-level BULLETS in the live STATUS.md
# ("- [2026-09-02T06:27 ET] conductor: OK -- ..."), not as "## [" headings. Until
# 2026-09-02 only the heading form was split, so overnight_fires_checked was 0 on a night
# with a real in-window fire and the check could only ever say "cannot verify" (C7: an
# instrument that cannot observe its subject is not an instrument). The bullet must be
# un-indented and carry the same "T..:.. ET]" stamp -- ROSTER-LIVENESS / FULL-SUITE lines
# use other stamp shapes and are deliberately NOT entry boundaries.
_STATUS_BULLET_RE = re.compile(
    r"^- \[(?P<date>\d{4}-\d{2}-\d{2})T(?P<hh>\d{2}):(?P<mm>\d{2})(?::\d{2})? ET\]"
    r"(?P<rest>.*)$")

_QUEUE_OPEN_GATE_BLOCKING_RE = re.compile(
    r"^- \[ \] (?P<name>[A-Z0-9][A-Z0-9\-]*)[^\n]*GATE-BLOCKING", re.MULTILINE)


def _split_status_entries(status_md_text: str) -> list[tuple[Optional[datetime], str, str]]:
    """Splits STATUS.md (newest-first, '## [' entry-boundary convention -- see
    status_retention.py) into (timestamp_or_None, header_rest, body) tuples."""
    lines = status_md_text.splitlines()
    entries: list[tuple[Optional[datetime], str, str]] = []
    cur_header: Optional[str] = None
    cur_ts: Optional[datetime] = None
    cur_body: list[str] = []
    for line in lines:
        m = _STATUS_HEADER_RE.match(line) or _STATUS_BULLET_RE.match(line)
        if m:
            if cur_header is not None:
                entries.append((cur_ts, cur_header, "\n".join(cur_body)))
            cur_header = m.group("rest")
            try:
                cur_ts = datetime(int(m.group("date")[:4]), int(m.group("date")[5:7]),
                                   int(m.group("date")[8:10]), int(m.group("hh")), int(m.group("mm")))
            except ValueError:
                cur_ts = None
            cur_body = []
        else:
            cur_body.append(line)
    if cur_header is not None:
        entries.append((cur_ts, cur_header, "\n".join(cur_body)))
    return entries


def check_conductor_picks(status_md_text: Optional[str], queue_md_text: Optional[str],
                           review_date: str, rth_start: tuple = RTH_START) -> dict:
    """ADVISORY. STATUS.md is human-authored prose, not a structured ledger -- this cannot
    be a hard pass/fail the way the other checks are. It reports what it can verify
    mechanically (which queue items are tagged GATE-BLOCKING and still open, which
    overnight conductor fires ran before this review's RTH start, and whether each such
    fire's own text mentions GATE-BLOCKING) and is explicit that it is a heuristic, never
    contributing to the overall RED/YELLOW verdict."""
    result: dict = {"status": "ADVISORY", "open_gate_blocking_items": [],
                     "overnight_fires_checked": 0, "fires_missing_gate_blocking_mention": [],
                     "reason": ""}

    if queue_md_text is None:
        result["reason"] = "queue.md unreadable -- cannot determine open GATE-BLOCKING items"
        return result
    if status_md_text is None:
        result["reason"] = "STATUS.md unreadable -- cannot check overnight conductor picks"
        return result

    open_items = [m.group("name") for m in _QUEUE_OPEN_GATE_BLOCKING_RE.finditer(queue_md_text)]
    result["open_gate_blocking_items"] = open_items

    year, month, day = (int(x) for x in review_date.split("-"))
    review_dt = datetime(year, month, day)
    window_start = review_dt - timedelta(days=1)  # overnight starts the evening before
    window_end = review_dt.replace(hour=rth_start[0], minute=rth_start[1])

    entries = _split_status_entries(status_md_text)
    overnight_conductor = [
        (ts, header, body) for ts, header, body in entries
        if ts is not None and "conductor:" in header and window_start <= ts <= window_end
    ]
    result["overnight_fires_checked"] = len(overnight_conductor)

    if not open_items:
        result["reason"] = "no open GATE-BLOCKING queue item in this window -- nothing to check"
        return result

    if not overnight_conductor:
        result["reason"] = (f"{len(open_items)} open GATE-BLOCKING item(s) but no overnight "
                            f"conductor fire found in the window to check against -- "
                            f"cannot verify")
        return result

    missing = []
    for ts, header, body in overnight_conductor:
        if "GATE-BLOCKING" not in body and "GATE-BLOCKING" not in header:
            missing.append(ts.strftime("%Y-%m-%dT%H:%M"))
    result["fires_missing_gate_blocking_mention"] = missing
    if missing:
        result["reason"] = (f"{len(missing)}/{len(overnight_conductor)} overnight fire(s) made "
                            f"no mention of GATE-BLOCKING while {len(open_items)} item(s) were "
                            f"open -- worth a human look, not asserted as a miss")
    else:
        result["reason"] = (f"all {len(overnight_conductor)} overnight fire(s) mention "
                            f"GATE-BLOCKING while {len(open_items)} item(s) were open")
    return result


# ============================================================================
# check 6: fleet kill-switch proximity (Rule 5 not latched on fleet arms yet)
# ============================================================================

def active_fleet_rest_arms(accounts: Optional[dict]) -> Optional[list[str]]:
    """Active fleet_rest arm ids from accounts.json (execution=='fleet_rest' AND
    status=='active') -- derived fresh every run, never hardcoded, so a roster change
    (e.g. risky-3 being retired) is picked up automatically instead of silently going
    stale (same discipline as eod_flatten.py's own _active_arms()). Returns None (not [])
    when accounts.json itself could not be read, so callers can tell 'derived an empty
    roster' apart from 'could not derive a roster at all'."""
    if accounts is None:
        return None
    out = []
    for arm in accounts.get("arms", []):
        if arm.get("execution") == "fleet_rest" and str(arm.get("status")).lower() == "active":
            aid = arm.get("id") or arm.get("arm_id")
            if aid:
                out.append(str(aid))
    return out


def min_equity_for_date(decisions_rows: list[dict], review_date: str) -> Optional[float]:
    day_rows = jsonl_rows_for_date(decisions_rows, review_date)
    equities = [r.get("equity") for r in day_rows if isinstance(r.get("equity"), (int, float))]
    if not equities:
        return None
    return min(equities)


def check_fleet_kill_switch_proximity(arms: Optional[list[str]],
                                       breaker_by_arm: dict[str, Optional[dict]],
                                       min_equity_by_arm: dict[str, Optional[float]]) -> dict:
    """Per fleet arm: min observed equity today as a % draw from starting_equity_today,
    and headroom left before that arm's own daily_loss_limit_pct floor. Rule 5 is not
    mechanically latched on these arms (unmerged branch safety-bundle-2026-09-29), so
    circuit-breaker.json#tripped cannot be trusted alone -- this check computes the draw
    independently off the arm's own decisions.jsonl equity series."""
    if arms is None:
        return {"status": "RED", "reason": "could not derive the active fleet arm roster "
                                            "(accounts.json unreadable)", "arms": {}}
    if not arms:
        return {"status": "GREEN", "reason": "no active fleet_rest arms", "arms": {}}

    per_arm: dict[str, dict] = {}
    worst = "GREEN"
    # NO_DATA IS NOT GREEN. This review runs at 16:30 ET, AFTER a full session -- an arm
    # with zero equity rows for the day did not tick, which is a finding, not a pass. The
    # same rule the DMS checks already follow ("a check that could not run is not a pass",
    # the guard_runner_full scar) has to apply here too or absence silently reads as health.
    order = {"GREEN": 0, "NO_DATA": 1, "YELLOW": 1, "RED": 2}
    for arm in arms:
        breaker = breaker_by_arm.get(arm)
        min_eq = min_equity_by_arm.get(arm)
        if breaker is None:
            per_arm[arm] = {"status": "RED", "reason": "circuit-breaker.json unreadable"}
            worst = "RED"
            continue
        start_eq = breaker.get("starting_equity_today")
        floor_pct = breaker.get("daily_loss_limit_pct")
        tripped = bool(breaker.get("tripped"))
        if not isinstance(start_eq, (int, float)) or start_eq <= 0:
            per_arm[arm] = {"status": "RED", "reason": "starting_equity_today missing/invalid",
                            "tripped": tripped}
            worst = "RED"
            continue
        if min_eq is None:
            per_arm[arm] = {"status": "NO_DATA",
                            "reason": "NO DATA -- no decisions.jsonl equity rows for this "
                                      "date (before the open this is expected; at 16:30 ET "
                                      "it means the arm never ticked)",
                            "starting_equity_today": start_eq, "tripped": tripped}
            if order.get("NO_DATA", 2) > order.get(worst, 0):
                worst = "NO_DATA"
            continue

        draw_pct = (start_eq - min_eq) / start_eq * 100.0
        floor_pct_val = (floor_pct or 0.0) * 100.0
        headroom_pct = floor_pct_val - draw_pct
        breached = draw_pct >= floor_pct_val
        if breached:
            st = "RED"
        elif headroom_pct < 5.0:
            st = "YELLOW"
        else:
            st = "GREEN"
        per_arm[arm] = {
            "status": st,
            "starting_equity_today": start_eq,
            "min_equity_today": min_eq,
            "draw_pct": round(draw_pct, 2),
            "floor_pct": round(floor_pct_val, 2),
            "headroom_pct": round(headroom_pct, 2),
            "tripped": tripped,
            "reason": ("BREACHED the loss floor" if breached else
                      f"{headroom_pct:.1f}pp headroom left before the {floor_pct_val:.0f}% floor"),
        }
        if order.get(st, 2) > order.get(worst, 0):
            worst = st

    reason = "; ".join(f"{a}: {per_arm[a]['reason']}" for a in arms)
    return {"status": worst, "reason": reason, "arms": per_arm}


# ============================================================================
# check 7: Gamma_GuardsFull verdict freshness + expected-failure-count
# ============================================================================

def _parse_loose_et_date(s: Any) -> Optional[str]:
    """Extracts just the YYYY-MM-DD prefix from a loosely-formatted ET timestamp string
    ('2026-08-31 09:55 ET' or similar). Returns None on anything else."""
    if not isinstance(s, str):
        return None
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else None


def _guards_full_failed_count(state: dict) -> Optional[int]:
    """guard_runner_full.py's REAL write schema nests the count under state['counts']
    ['failed'] (verified live against automation/state/guard-watch-full.json this session
    -- there is no top-level 'failed' key). A bare state['failed'] is accepted too as a
    forward-compatible fallback, but the nested form is authoritative."""
    counts = state.get("counts")
    if isinstance(counts, dict) and "failed" in counts:
        return counts.get("failed")
    if "failed" in state:
        return state.get("failed")
    return None


def check_guards_full(state: Optional[dict], review_date: str,
                       expected_failed: int = GUARDS_FULL_EXPECTED_FAILED,
                       stale_days: int = GUARDS_FULL_STALE_DAYS) -> dict:
    failed = _guards_full_failed_count(state) if state is not None else None
    if state is None or failed is None:
        return {"status": "RED", "reason": "no verdict produced (guard-watch-full.json "
                                            "missing/unreadable/malformed)",
                "failed": None, "expected_failed": expected_failed, "stale": None}

    at_date = _parse_loose_et_date(state.get("at"))
    stale = None
    if at_date is not None:
        try:
            y, m, d = (int(x) for x in review_date.split("-"))
            ay, am, ad = (int(x) for x in at_date.split("-"))
            days_old = (datetime(y, m, d) - datetime(ay, am, ad)).days
            stale = days_old >= stale_days
        except ValueError:
            stale = None
    else:
        stale = True  # unparseable date -- treat as unreliable/stale

    deviates = failed != expected_failed
    # STALENESS LEADS THE SENTENCE (2026-09-02). The `stale` flag was already computed and
    # stored, but the human-facing reason mentioned only the count -- so an operator reading
    # the one-line summary would conclude there are N real failures today, when in fact the
    # verdict is days old and the count describes a run that already happened. A stale
    # verdict makes its own count meaningless, so say that FIRST.
    _age = f" (verdict is from {at_date}, STALE)" if stale else ""
    if stale:
        status = "YELLOW" if not deviates else "YELLOW"
        reason = (f"STALE VERDICT{(' from ' + str(at_date)) if at_date else ''} -- "
                  f"Gamma_GuardsFull has not produced a fresh result, so its "
                  f"failed={failed} describes an older run, not today"
                  + (f"; expected {expected_failed}" if deviates else ""))
    elif deviates:
        status = "YELLOW"
        # NAME THE VERDICT'S TIMESTAMP, ALWAYS (2026-09-02). Staleness here is measured in
        # DAYS, so a verdict from 04:52 ET reads as "today" at a 16:30 review and its count
        # is presented as current -- when in fact Gamma_GuardsFull fires ~04:29 ET and next
        # runs at 23:15 ET, i.e. AFTER this review. Every same-day verdict this check ever
        # sees is ~12h old by design, so flagging that as stale would make the check
        # permanently yellow (the alarm nobody reads). Printing the time instead is
        # information, not an alarm, and it is what stops a reader assuming "now".
        reason = (f"failed count deviates from expected {expected_failed}: got {failed} "
                  f"[verdict recorded {state.get('at') or 'at an unknown time'}; "
                  f"Gamma_GuardsFull next runs 23:15 ET, after this review]{_age}")
    elif stale:
        status = "YELLOW"
        reason = f"verdict is stale (dated {at_date}, review date {review_date})"
    else:
        status = "GREEN"
        reason = (f"failed count matches expected steady-state ({expected_failed}) "
                  f"[verdict recorded {state.get('at') or 'at an unknown time'}]")

    return {"status": status, "reason": reason, "failed": failed,
            "expected_failed": expected_failed, "stale": stale, "at": state.get("at")}


# ============================================================================
# aggregation
# ============================================================================

# NO_DATA IS NOT GREEN -- HERE TOO. check_fleet_kill_switch_proximity's own inner order was
# corrected to rank NO_DATA above GREEN on 2026-09-02, and this aggregator one function later
# was left contradicting it: a gating check returning NO_DATA did not escalate, so a run where
# EVERY gating check came back NO_DATA (every state file missing -- i.e. the box died) returned
# GREEN. Reachable, not theoretical: fleet_kill_switch returned NO_DATA in the real
# analysis/first-live-day/2026-09-02.json. ADVISORY stays at 0 because conductor_picks is
# excluded from gating by design; absence is not.
_SEVERITY_ORDER = {"GREEN": 0, "ADVISORY": 0, "NOT_YET": 0, "NO_DATA": 1, "YELLOW": 1, "RED": 2}
_GATING_CHECKS = ("dms_cadence", "dms_verdicts", "engine_health", "eod_flatten_aggressive",
                  "fleet_kill_switch", "guards_full")  # conductor_picks is advisory-only


def combine_verdict(checks: dict[str, dict]) -> tuple[str, list[str]]:
    """Worse-wins across the GATING checks only. conductor_picks is explicitly excluded --
    it is heuristic/textual and documented as advisory, never a pass/fail input.

    A gating check that is ABSENT from `checks` counts as NO_DATA, never as a skip: if
    run_review failed to produce one, the day was not fully reviewed, and silently omitting
    it from the worst-wins fold is the same GREEN-by-absence bug as ranking NO_DATA at 0.

    NOT_YET (FIRST-LIVE-DAY-REVIEW-CANNOT-TELL-NOT-YET-FROM-FAILED, queue.md 2026-09-02):
    a check reporting NOT_YET is EXCLUDED from `failing` and never escalates `worst` -- it is
    not a failure, it is a session that has not reached that check's own checkpoint yet. But
    it must not be laundered into a silent, indistinguishable GREEN either: when every other
    gating check is clean (worst would read GREEN) and at least one NOT_YET is outstanding,
    the returned verdict string becomes 'INCOMPLETE (n not yet)' instead of 'GREEN' -- so a
    reader never mistakes "nothing has failed so far" for "the day was fully reviewed". A
    real YELLOW/RED/NO_DATA elsewhere still wins outright (NOT_YET never masks a real
    problem, and a real problem is never softened to INCOMPLETE).
    """
    worst = "GREEN"
    failing = []
    not_yet_count = 0
    for name in _GATING_CHECKS:
        c = checks.get(name)
        if c is None:
            c = {"status": "NO_DATA", "reason": "check did not run"}
        st = c.get("status", "RED")
        if st == "NOT_YET":
            not_yet_count += 1
            continue
        if _SEVERITY_ORDER.get(st, 2) > 0:
            failing.append(f"{name}:{st}")
        if _SEVERITY_ORDER.get(st, 2) > _SEVERITY_ORDER.get(worst, 0):
            worst = st
    if worst == "GREEN" and not_yet_count:
        worst = f"INCOMPLETE ({not_yet_count} not yet)"
    return worst, failing


# ============================================================================
# orchestration
# ============================================================================

def run_review(review_date: Optional[str] = None) -> dict:
    if review_date is None:
        review_date = et_today_str()

    # ONE now_et, threaded into every time-aware check below (NOT_YET's `now` param included
    # -- see DMS_CADENCE_NOT_YET_AFTER / DMS_VERDICTS_NOT_YET_AFTER / EOD_FLATTEN_NOT_YET_
    # AFTER). Previously each check that consulted a clock fell back to its own default
    # (bare `datetime.now()`, the box's SYSTEM/Mountain time, not ET -- this box runs 2h
    # behind ET) rather than sharing this one real ET reading; a single shared value also
    # guarantees every NOT_YET/RED boundary in one report is judged at the same instant.
    now_et = et_now()
    generated_at = now_et.strftime("%Y-%m-%d %H:%M:%S ET")

    # ---- load everything (all via the redirectable module-level path constants) ----
    dms_rows_all = read_jsonl(DMS_LOG_DIR / f"dead-mans-switch-{review_date}.jsonl")
    dms_rows = jsonl_rows_for_date(dms_rows_all, review_date, ts_field="ts") \
        if dms_rows_all else dms_rows_all
    # dead_mans_switch.py's _et_ts() has no ISO 'T' -- ts starts with the date either way,
    # but the file is already date-scoped by filename, so this second filter is a no-op
    # safety net for a misnamed/concatenated log rather than the primary mechanism.

    engine_health = read_json(ENGINE_HEALTH_PATH)
    guards_full_state = read_json(GUARDS_FULL_PATH)
    accounts = read_json(ACCOUNTS_PATH)

    core_eod_rows = jsonl_rows_for_date(
        read_jsonl(EOD_LOG_DIR / f"eod-flatten-{review_date}.jsonl"), review_date,
        ts_field="ts")
    agg_eod_log = read_text(EOD_LOG_DIR / f"eod-flatten-aggressive-{review_date}.log")

    status_md_text = read_text(STATUS_MD_PATH)
    queue_md_text = read_text(QUEUE_MD_PATH)

    fleet_arms = active_fleet_rest_arms(accounts)
    breaker_by_arm: dict[str, Optional[dict]] = {}
    min_equity_by_arm: dict[str, Optional[float]] = {}
    for arm in (fleet_arms or []):
        breaker_by_arm[arm] = read_json(FLEET_DIR / arm / "circuit-breaker.json")
        rows = read_jsonl(FLEET_DIR / arm / "decisions.jsonl")
        min_equity_by_arm[arm] = min_equity_for_date(rows, review_date)

    # ---- run every check ----
    checks = {
        "dms_cadence": check_dms_cadence(dms_rows, review_date, now=now_et),
        "dms_verdicts": check_dms_verdicts(dms_rows, review_date=review_date, now=now_et),
        "engine_health": check_engine_health(engine_health),
        "eod_flatten_aggressive": check_eod_flatten_aggressive(
            core_eod_rows, agg_eod_log, review_date=review_date, now=now_et),
        "conductor_picks": check_conductor_picks(status_md_text, queue_md_text, review_date),
        "fleet_kill_switch": check_fleet_kill_switch_proximity(
            fleet_arms, breaker_by_arm, min_equity_by_arm),
        "guards_full": check_guards_full(guards_full_state, review_date),
    }

    verdict, failing = combine_verdict(checks)

    report = {
        "review_date": review_date,
        "generated_at_et": generated_at,
        "verdict": verdict,
        "failing_checks": failing,
        "checks": checks,
        "notes": [
            "conductor_picks is ADVISORY/heuristic (STATUS.md prose) -- never contributes "
            "to the overall verdict above.",
            "fleet_kill_switch NO_DATA is expected before the market opens or on a day "
            "with no fleet-arm ticks yet -- not treated as a failure.",
            "NOT_YET (dms_cadence/dms_verdicts/eod_flatten_aggressive) means the session "
            "has not reached that check's own evidence checkpoint yet -- not a failure, "
            "and never contributes to failing_checks -- but the top-line verdict reads "
            "INCOMPLETE (n not yet) rather than GREEN while any is outstanding, so a run "
            "before the close is never mistaken for a fully reviewed day.",
        ],
    }
    return report


def _fmt_check_line(name: str, c: dict) -> str:
    return f"- **{name}**: {c.get('status')} -- {c.get('reason', '')}"


# ============================================================================
# run log (FIRST-LIVE-DAY-REVIEW-RUN-LOG, queue.md 2026-09-02)
# ============================================================================

def _parent_process_image_name() -> Optional[str]:
    """Best-effort lowercase basename of the IMMEDIATE parent process's executable.
    Windows-only, stdlib ctypes -- psutil is NOT a dependency here (confirmed absent
    from both the backtest venv and the system Python313 interpreter the scheduled
    task itself runs under: a new dependency could silently break under the one
    launcher this needs to detect). Returns None on any failure (non-Windows, access
    denied, parent already gone) -- callers treat that as 'unknown', never crash
    (C7 fail-open)."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, os.getppid())
        if not handle:
            return None
        try:
            buf = ctypes.create_unicode_buffer(260)
            size = wintypes.DWORD(260)
            ok = kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
            if not ok:
                return None
            return Path(buf.value).name.lower()
        finally:
            kernel32.CloseHandle(handle)
    except Exception:  # noqa: BLE001 -- detection is best-effort, never fatal
        return None


def detect_invoker(parent_image_name: Optional[str] = None) -> str:
    """'task' when launched via the scheduler's hidden pythonw chain
    (run_exe_hidden.vbs -> pythonw run_cmd_hidden.py -> pythonw
    first_live_day_review.py -- verified live 2026-09-02 via
    `Get-ScheduledTask Gamma_FirstLiveDayReview`'s registered Action), 'direct'
    otherwise, 'unknown' if parent detection itself failed.

    WHY THE PARENT PROCESS IMAGE NAME, NOT AN ENV VAR: the live task Action passes
    no `--env` at all today (checked live, not assumed) -- an env-var detector would
    misclassify every task fire as 'direct' until someone remembered to add one, and
    a scheduled task's Action is not something this repo re-registers lightly. Every
    scheduled/hidden launch in this codebase already runs its target under
    `pythonw.exe` (C8 doctrine: headless Windows spawn = system-pythonw +
    CREATE_NO_WINDOW) while every direct/manual/Claude-session invocation of this
    script uses the interactive console `python.exe` (see the task instructions for
    this exact fix: "Run the real script once (`python setup/scripts/
    first_live_day_review.py --date ...`)"). So the immediate parent's image
    basename is a fact already true on every past and future task fire, with no
    second edit needed anywhere else."""
    img = parent_image_name if parent_image_name is not None else _parent_process_image_name()
    if img is None:
        return "unknown"
    return "task" if img == "pythonw.exe" else "direct"


def append_run_log(report: dict, argv: list[str], invoker: str) -> None:
    """Append ONE row to `analysis/first-live-day/runs.jsonl` for EVERY invocation --
    see RUNS_LOG_PATH's docstring / FIRST-LIVE-DAY-REVIEW-RUN-LOG. This file is
    APPEND-ONLY and never touched by write_outputs()'s per-date overwrite, so a
    later ad-hoc run can no longer erase evidence that an earlier one happened.

    Fail-open (C7): this function only ever APPENDS -- it never reads back or
    parses the existing file, so a malformed/corrupt runs.jsonl cannot make this
    function crash. The write itself is still wrapped: a permissions error or a
    missing/unwritable directory must not take down the review that already ran
    successfully and already wrote its per-date JSON/MD."""
    row = {
        "generated_at_et": report.get("generated_at_et"),
        "review_date": report.get("review_date"),
        "verdict": report.get("verdict"),
        "failing_checks": report.get("failing_checks", []),
        "argv": list(argv),
        "invoker": invoker,
    }
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        with (OUT_DIR / "runs.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError as exc:  # noqa: BLE001 -- never let the log write sink the review
        print(f"first_live_day_review: FAILED to append runs.jsonl ({exc})", file=sys.stderr)


def write_outputs(report: dict) -> tuple[Path, Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    date = report["review_date"]
    json_path = OUT_DIR / f"{date}.json"
    md_path = OUT_DIR / f"{date}.md"

    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    lines = [
        f"# First-live-day review -- {date}",
        "",
        f"Generated {report['generated_at_et']}",
        "",
        f"## Verdict: {report['verdict']}"
        + (f" -- {', '.join(report['failing_checks'])}" if report["failing_checks"] else ""),
        "",
        "## Checks",
    ]
    for name in ("dms_cadence", "dms_verdicts", "engine_health", "eod_flatten_aggressive",
                 "fleet_kill_switch", "guards_full", "conductor_picks"):
        c = report["checks"].get(name)
        if c is None:
            continue
        lines.append(_fmt_check_line(name, c))
    lines += ["", "## Notes"]
    for n in report["notes"]:
        lines.append(f"- {n}")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def print_summary(report: dict) -> None:
    print(f"FIRST-LIVE-DAY-REVIEW {report['review_date']} :: verdict={report['verdict']}"
          + (f" :: failing={','.join(report['failing_checks'])}" if report["failing_checks"] else ""))
    for name in ("dms_cadence", "dms_verdicts", "engine_health", "eod_flatten_aggressive",
                 "fleet_kill_switch", "guards_full", "conductor_picks"):
        c = report["checks"].get(name)
        if c is None:
            continue
        print(f"  {name}: {c.get('status')} -- {c.get('reason', '')}")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    ap.add_argument("--date", type=str, default=None,
                     help="Review date YYYY-MM-DD (default: today's ET date)")
    args = ap.parse_args(argv)
    real_argv = list(argv) if argv is not None else list(sys.argv[1:])

    report = run_review(args.date)
    write_outputs(report)
    append_run_log(report, real_argv, detect_invoker())
    print_summary(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""conductor_outcome.py — per-fire outcome metric for the autonomous conductor.

Phase 4 of the autonomy plan. The conductor (`automation/prompts/conductor.md`)
fires once per wake, picks ONE bounded task, and ships or flags it. Until now
"always-improving" was *asserted* in prose (OP-22) but never *measured*: there was
no structured record of what each fire actually accomplished, so net improvement
across fires could not be computed.

This module closes that gap with two pure-stdlib functions + a thin CLI:

  1. record(...)  -> appends one JSON line to conductor-outcomes.jsonl (best-effort,
     never throws — a failure to journal must never crash a conductor fire).
     Each row also snapshots the TRADING FUNCTION funnel from the ledgers
     (enters / orders_accepted / fills / distinct_setups_traded — 2026-07-01
     re-aim: the metric measured artifacts only, so the loop optimized for
     tests/lessons while the rig never traded).
  2. compute_metric(window) -> folds the last N outcome rows into a rolling
     net-improvement scorecard written to autonomy-metric.json. The trend
     weights FUNCTION (fills > accepted orders > enters) over artifact count.

The metric is deliberately simple and explainable (see compute_metric docstring
for the net_improvement formula + thrash heuristic). It is a *signal* for J and the
conductor, not a reward function the conductor optimizes against.

STDLIB ONLY. Anchor everything to the repo root via __file__ so it is correct no
matter the cwd of the scheduled task that invokes it.

CLI:
  python setup/scripts/conductor_outcome.py record --task-id X --cost 1.50 \
      --drained 1 --added 0 --lessons 1 --tests-delta 7 --regressions 0 --note "..."
  python setup/scripts/conductor_outcome.py metric [--window N]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --- Path anchoring (cwd-independent) ---------------------------------------
# setup/scripts/conductor_outcome.py -> parents[2] == repo root.
REPO = Path(__file__).resolve().parents[2]
STATE_DIR = REPO / "automation" / "state"
OUTCOMES_FILE = STATE_DIR / "conductor-outcomes.jsonl"
METRIC_FILE = STATE_DIR / "autonomy-metric.json"
# Trading-function ledgers (2026-07-01 re-aim: the metric measured artifacts
# only — drained/lessons/tests — so a fire adding 41 tests scored like one that
# made an order fill. These are the ground-truth function sources.)
DECISIONS_FILE = STATE_DIR / "core-decisions.jsonl"
FLEET_DIR = STATE_DIR / "fleet"
TRADES_CSV = REPO / "journal" / "trades.csv"

DEFAULT_WINDOW = 20

# --- Zero-enter day grading (AUTONOMY-METRIC-ZERO-ENTERS-08-31, 2026-09-03) --
# `_trend()` used to label ANY zero-enter day "regressing" without asking
# whether the zero was a doctrine-sanctioned gate refusal (feedback_
# sitting_out_is_a_valid_day_2026_08_12) rather than a funnel miss. 2026-08-31
# replay (analysis/deep-research/BEAR-08-31-NO-TRIGGER-REPLAY.md): all 55
# bear-score>=9 ticks that day were refused by blocker 8 (the ratified VIX
# floor gate) -- a sanctioned sit-out, not a defect. The defect was the METRIC.
#
# ZERO_ENTER_SCORE_THRESHOLD: what counts as a "high-score tick" worth grading.
# core-decisions.jsonl rows carry NO per-row threshold field (verified
# 2026-09-03 via a full key survey of a day's rows -- bear_score/bull_score
# are the only score fields present, no companion threshold key). So this is
# hardcoded to 9, matching the ALREADY-RATIFIED convention self_check.py's
# check_engine_tradeability uses for its identical "ENGINE NOT ENTERING
# (bear): ... scored bear>=9 but no trigger fired" check -- not invented here.
ZERO_ENTER_SCORE_THRESHOLD = 9
# ZERO_ENTER_MIN_RTH_TICKS: minimum ticks recorded that day before a
# fully-gate-refused zero-enter day is confidently graded SAT_OUT_GATED (a
# half day / early outage shouldn't be read as a confirmed full-session
# gated sit-out). Below this, _grade_zero_enter_day returns None (ungraded)
# and the trend computation leaves that day alone.
ZERO_ENTER_MIN_RTH_TICKS = 100

# Numeric outcome fields and their defaults (strings default to "").
_NUMERIC_FIELDS = (
    "cost_usd",
    "items_drained",
    "items_added",
    "lessons_shipped",
    "tests_delta",
    "regressions",
)

# Trading-function snapshot fields (per fire, from the ledgers).
_FUNCTION_FIELDS = (
    "enters_last_trading_day",
    "orders_accepted",
    "fills",
    "distinct_setups_traded",
    "extra_exec_orders_accepted",
)


def _utc_now_iso() -> str:
    """Current UTC time as an ISO8601 string (seconds precision, 'Z' suffix)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# --- trading-function snapshot ------------------------------------------------
def _iter_jsonl_reversed(path: Path):
    """Yield parsed dict rows from a .jsonl file, newest line first.

    Robust to missing/torn files: unreadable file yields nothing, a malformed
    line is skipped. Never raises.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, OSError):
        return
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            yield obj


def trading_function_snapshot(
    *,
    decisions_file: Path | None = None,
    fleet_dir: Path | None = None,
    trades_csv: Path | None = None,
) -> dict[str, Any]:
    """Snapshot the LAST TRADING DAY's function funnel from the ledgers.

    Sources (all best-effort, never raises):
      - core-decisions.jsonl: ENTER verdicts + broker-accepted orders
        (``exec.status == "PLACED"``) for both core accounts.
      - fleet/*/decisions.jsonl: fleet-arm ENTER actions + accepted placements
        (``placement.placed is True``).
      - journal/trades.csv: filled round-trips journaled for that day.

    "Last trading day" = the newest ``ts_et`` date in core-decisions.jsonl
    (falling back to the newest fleet date when the core ledger is empty).
    Returns zeros + ``trading_day: ""`` when no ledger is readable — a missing
    funnel must never crash a conductor fire.
    """
    dec_path = decisions_file or DECISIONS_FILE
    fl_dir = fleet_dir or FLEET_DIR
    csv_path = trades_csv or TRADES_CSV

    snap: dict[str, Any] = {
        "trading_day": "",
        "enters_last_trading_day": 0,
        "orders_accepted": 0,
        "fills": 0,
        "distinct_setups_traded": 0,
        "extra_exec_orders_accepted": 0,
    }
    setups: set[str] = set()
    try:
        # 1) Core ledger — establishes the canonical last trading day.
        day = ""
        for row in _iter_jsonl_reversed(dec_path):
            ts = str(row.get("ts_et", "") or "")
            if len(ts) < 10:
                continue
            if not day:
                day = ts[:10]
            if ts[:10] != day:
                break  # chronological file — older day reached, stop
            if str(row.get("verdict", "") or "").startswith("ENTER"):
                snap["enters_last_trading_day"] += 1
            ex = row.get("exec") or {}
            if isinstance(ex, dict) and ex.get("status") == "PLACED":
                snap["orders_accepted"] += 1
                if ex.get("setup"):
                    setups.add(str(ex["setup"]))
            # SECONDARY-SETUP VISIBILITY (2026-07-23, mirrors the 2026-07-22
            # fill_funnel.py fix): a core row can also carry an `extra_exec`
            # list — non-primary setups (vwap_continuation, bollinger_squeeze,
            # vix_regime_dayside...) routed + placed through _route_extra_setups,
            # a path separate from the primary verdict/exec ENTER pipeline this
            # loop otherwise tracks. Before this fix a day with 0 primary ENTERs
            # but several extra_exec PLACED orders read as "0 orders_accepted"
            # here even though fill_funnel.py's own funnel (which WAS fixed)
            # showed GREEN with real fills — 3 straight conductor fires
            # (2026-07-23 06:42/07:42/08:12 ET) flagged the resulting metric
            # mismatch as "worth a dedicated look" against 2026-07-22's ledger,
            # which had 2 real extra_exec PLACED+filled orders this loop was
            # silently blind to. Kept as a SEPARATE additive field (not folded
            # into orders_accepted) so the primary-pipeline signal stays
            # uncontaminated — same scoping decision fill_funnel.py already made.
            for exr in (row.get("extra_exec") or []):
                if isinstance(exr, dict) and exr.get("action") == "PLACED":
                    snap["extra_exec_orders_accepted"] += 1
                    if exr.get("setup"):
                        setups.add(str(exr["setup"]))

        # 2) Fleet ledgers (same day only; establish day if core was empty).
        try:
            fleet_files = sorted(fl_dir.glob("*/decisions.jsonl"))
        except OSError:
            fleet_files = []
        for fpath in fleet_files:
            for row in _iter_jsonl_reversed(fpath):
                ts = str(row.get("ts_et", "") or "")
                if len(ts) < 10:
                    continue
                if not day:
                    day = ts[:10]
                if ts[:10] != day:
                    break
                if str(row.get("action", "") or "").startswith("ENTER"):
                    snap["enters_last_trading_day"] += 1
                pl = row.get("placement") or {}
                if isinstance(pl, dict) and pl.get("placed") is True:
                    snap["orders_accepted"] += 1
                    if row.get("setup_name"):
                        setups.add(str(row["setup_name"]))

        # 3) Fills journal (round-trips recorded for that day).
        if day:
            try:
                for line in csv_path.read_text(encoding="utf-8").splitlines():
                    if line.startswith(day + ","):
                        snap["fills"] += 1
                        parts = line.split(",")
                        if len(parts) > 3 and parts[3]:
                            setups.add(parts[3])
            except (FileNotFoundError, OSError):
                pass

        snap["trading_day"] = day
        snap["distinct_setups_traded"] = len(setups)
    except Exception:
        # Any surprise -> return whatever was accumulated; never raise.
        pass
    return snap


# --- zero-enter day grading --------------------------------------------------
def _row_day(r: dict[str, Any]) -> str:
    """A row's calendar day, preferring the explicit ``date`` field but
    falling back to ``ts_et[:10]`` when ``date`` is absent.

    ROOT-CAUSE FIX (2026-09-05, GOAL-RIGHT-TAIL-CAPTURE): heartbeat_core.py's
    ``_log()`` only started injecting a ``date`` key on 2026-08-25 (DEFECT-A
    fix) -- every row written before that date carries ``ts_et`` only. A
    reader that filters strictly on ``r.get("date")`` (the previous body of
    `_decisions_for_day` below) therefore silently returns ZERO rows for any
    day before 2026-08-26, even though the file holds the row on disk --
    exactly the "LATENT trap" heartbeat_core.py's own fix docstring warned
    about ("no live consumer currently does this ... closes a LATENT trap
    before it bites"). `right_tail_waves.py._core_decisions_has_date()` was
    that trap being sprung: it read core-decisions.jsonl's min ``date`` field
    as 2026-08-26 and treated every earlier day (including the 2026-08-04
    fixture day, which has 776 real ts_et rows) as having no core-decisions
    coverage at all, routing it into FLEET_FALLBACK mode instead of the
    correct CORE_SCORE mode. This is a field-presence bug, not a truncated
    read -- `_iter_jsonl_reversed` already loads the whole file into memory.
    Guard: `backtest/tests/test_right_tail_waves.py`."""
    d = str(r.get("date", "") or "")
    if d:
        return d
    ts = str(r.get("ts_et", "") or "")
    return ts[:10] if len(ts) >= 10 else ""


def _decisions_for_day(day: str, decisions_file: Path) -> list[dict[str, Any]]:
    """All core-decisions.jsonl rows (both accounts) whose calendar day
    (``date`` field, or ``ts_et[:10]`` when ``date`` is absent -- see
    `_row_day`) equals ``day``. Best-effort; a missing/unreadable file or
    empty day yields []."""
    if not day:
        return []
    return [
        r for r in _iter_jsonl_reversed(decisions_file)
        if _row_day(r) == day
    ]


def _grade_zero_enter_day(
    trading_day: str,
    *,
    decisions_file: Path | None = None,
    score_threshold: int = ZERO_ENTER_SCORE_THRESHOLD,
    min_rth_ticks: int = ZERO_ENTER_MIN_RTH_TICKS,
) -> dict[str, Any] | None:
    """Grade a trading day that recorded 0 enters.

    Three possible grades:
      SAT_OUT_GATED — >= min_rth_ticks RTH ticks, >= 1 high-score tick
        (bear_score or bull_score >= score_threshold), and EVERY such tick
        carries at least one blocker id in its side's ``*_blockers`` field.
        Neutral: a ratified gate refused a real setup — sanctioned sit-out.
      QUIET — 0 high-score ticks all day. Neutral: no high-conviction setup
        ever appeared, nothing was refused.
      regressing — >= 1 high-score tick with NO blocker recorded on its side.
        A funnel miss: the setup scored, no trigger/gate explains the silence.

    Returns None when there is nothing to grade (no ledger rows for that day)
    or when a fully-gate-refused day has fewer than min_rth_ticks ticks (too
    short a session to confidently call a full-session gated sit-out). Callers
    MUST treat None as "leave this day out of the grading decision" — never as
    a fourth grade in its own right.
    """
    dec_path = decisions_file or DECISIONS_FILE
    if not trading_day:
        return None
    rows = _decisions_for_day(trading_day, dec_path)
    ticks = len(rows)
    high: list[tuple[str, dict[str, Any]]] = []
    for r in rows:
        if _num(r, "bear_score") >= score_threshold:
            high.append(("bear", r))
        if _num(r, "bull_score") >= score_threshold:
            high.append(("bull", r))

    if not high:
        if ticks == 0:
            return None  # no ledger rows for this day at all -- nothing to grade
        return {
            "trading_day": trading_day,
            "grade": "QUIET",
            "ticks": ticks,
            "high_score_ticks": 0,
            "reason": (
                f"{ticks} RTH ticks, 0 enters, 0 ticks scored >= {score_threshold} "
                f"-- no high-conviction setup all day"
            ),
        }

    unblocked = 0
    blocker_counts: dict[Any, int] = {}
    for side, r in high:
        blockers = r.get(f"{side}_blockers") or []
        if not blockers:
            unblocked += 1
        else:
            for b in blockers:
                blocker_counts[b] = blocker_counts.get(b, 0) + 1

    if unblocked:
        return {
            "trading_day": trading_day,
            "grade": "regressing",
            "ticks": ticks,
            "high_score_ticks": len(high),
            "reason": (
                f"{unblocked} of {len(high)} ticks scored >= {score_threshold} with NO "
                f"gate blocker recorded (0 enters, {ticks} RTH ticks) -- possible funnel miss"
            ),
        }

    if ticks < min_rth_ticks:
        return None  # every high-score tick was gate-refused, but too few ticks
        # this session to confidently call it a full-session gated sit-out.

    dominant, cnt = max(blocker_counts.items(), key=lambda kv: kv[1])
    return {
        "trading_day": trading_day,
        "grade": "SAT_OUT_GATED",
        "ticks": ticks,
        "high_score_ticks": len(high),
        "reason": (
            f"blocker {dominant} refused {cnt}/{len(high)} ticks scored >= {score_threshold} "
            f"(0 enters, {ticks} RTH ticks) -- a ratified gate, not a funnel miss"
        ),
    }


def _filtered_for_trend(
    rows: list[dict[str, Any]], decisions_file: Path | None
) -> list[dict[str, Any]]:
    """Drop rows whose snapshot is a graded-NEUTRAL (SAT_OUT_GATED/QUIET)
    zero-enter day before averaging function score for the trend comparison.

    A doctrine-sanctioned sit-out or a genuinely quiet day carries no function
    SIGNAL either way (see _grade_zero_enter_day) — it must not drag a half's
    average down and read as "regressing" (AUTONOMY-METRIC-ZERO-ENTERS-08-31).
    A zero-enter day that grades "regressing" (funnel miss) or is ungraded
    (None — no ledger rows for that day, or a fully-gate-refused day too short
    to confidently call, e.g. in tests with no fixture file) is left in —
    those ARE real signal (or at least not proven neutral).

    Can return []. A half that ends up EMPTY (every row in it graded neutral)
    is not backfilled with the raw zero-score rows here — that would silently
    defeat the whole point of this fix by putting a neutral day's 0.0 straight
    back into the average. _trend() is responsible for treating an empty
    result as "no function signal from this half" rather than "score 0".
    """
    grade_cache: dict[str, dict[str, Any] | None] = {}
    keep: list[dict[str, Any]] = []
    for r in rows:
        if _num(r, "enters_last_trading_day") == 0:
            day = str(r.get("trading_day", "") or "")
            if day:
                if day not in grade_cache:
                    grade_cache[day] = _grade_zero_enter_day(day, decisions_file=decisions_file)
                grade = grade_cache[day]
                if grade is not None and grade["grade"] in ("SAT_OUT_GATED", "QUIET"):
                    continue  # neutral -- excluded from the function-score trend comparison
        keep.append(r)
    return keep


# --- 1) RECORD ---------------------------------------------------------------
def record(
    task_id: str = "",
    *,
    cost_usd: float = 0.0,
    items_drained: int = 0,
    items_added: int = 0,
    lessons_shipped: int = 0,
    tests_delta: int = 0,
    regressions: int = 0,
    note: str = "",
    fired_at: str | None = None,
    outcomes_file: Path | None = None,
    function_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Append one structured fire-outcome row to conductor-outcomes.jsonl.

    Best-effort and NEVER throws: a failure to journal an outcome must never crash
    a conductor fire. On any error we swallow it (returning None) rather than
    propagate. Missing dirs/file are created on demand.

    Each row also snapshots the TRADING FUNCTION funnel from the ledgers
    (enters / orders_accepted / fills / distinct_setups_traded for the last
    trading day) so the metric can weight function over artifact count.
    Pass ``function_snapshot`` to override (tests / backfill).

    Returns the row dict that was written, or None if the append failed.
    """
    path = outcomes_file or OUTCOMES_FILE
    snap = (
        function_snapshot
        if function_snapshot is not None
        else trading_function_snapshot()
    )
    row: dict[str, Any] = {
        "fired_at": fired_at or _utc_now_iso(),
        "task_id": str(task_id or ""),
        "cost_usd": float(cost_usd or 0.0),
        "items_drained": int(items_drained or 0),
        "items_added": int(items_added or 0),
        "lessons_shipped": int(lessons_shipped or 0),
        "tests_delta": int(tests_delta or 0),
        "regressions": int(regressions or 0),
        "note": str(note or ""),
        "trading_day": str(snap.get("trading_day", "") or ""),
        "enters_last_trading_day": int(snap.get("enters_last_trading_day", 0) or 0),
        "orders_accepted": int(snap.get("orders_accepted", 0) or 0),
        "extra_exec_orders_accepted": int(snap.get("extra_exec_orders_accepted", 0) or 0),
        "fills": int(snap.get("fills", 0) or 0),
        "distinct_setups_traded": int(snap.get("distinct_setups_traded", 0) or 0),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        return row
    except Exception:
        # Journaling is non-critical — never let it take down the caller.
        return None


# --- helpers for COMPUTE -----------------------------------------------------
def _read_outcomes(path: Path) -> list[dict[str, Any]]:
    """Read all well-formed outcome rows. Robust to missing/empty/torn files.

    A torn (truncated/partial) final line — or any malformed line — is skipped
    silently rather than raising. Returns rows in file (chronological) order.
    """
    rows: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return rows
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue  # torn / malformed line — skip
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _num(row: dict[str, Any], key: str) -> float:
    """Coerce a row field to a number, treating missing/garbage as 0."""
    try:
        return float(row.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _net_improvement(rows: list[dict[str, Any]]) -> int:
    """net_improvement = sum(items_drained) - sum(regressions) - thrash_penalty.

    thrash_penalty heuristic (kept deliberately simple + explainable):
      A "thrash" is a fire that undid prior progress. We count, per fire (in
      chronological order), +1 of penalty when EITHER:
        (a) the fire reports regressions > 0  (it broke something), OR
        (b) the fire RE-ADDS a task_id that an EARLIER fire had drained
            (items_added > 0 on a task that was previously cleared — i.e. churn:
             work that came back after being marked done).
      The two conditions are OR'd but counted at most once per fire, so a single
      bad fire contributes at most 1 to the penalty. This rewards monotonic
      progress (drain and stay drained) and penalizes churn/breakage without
      letting one fire dominate the metric.
    """
    drained_total = 0
    regressions_total = 0
    thrash = 0
    seen_drained_task_ids: set[str] = set()

    for row in rows:
        d = int(_num(row, "items_drained"))
        a = int(_num(row, "items_added"))
        r = int(_num(row, "regressions"))
        tid = str(row.get("task_id", "") or "")

        drained_total += d
        regressions_total += r

        readded = a > 0 and tid != "" and tid in seen_drained_task_ids
        if r > 0 or readded:
            thrash += 1

        # Record this fire's drained task AFTER the re-add check, so a fire that
        # both drains and re-adds the same id is not flagged against itself.
        if d > 0 and tid != "":
            seen_drained_task_ids.add(tid)

    return int(drained_total - regressions_total - thrash)


def _fire_function_score(row: dict[str, Any]) -> float:
    """Weighted trading-function score of one fire's ledger snapshot.

    fills are the goal (x3), broker-accepted orders prove the placement path
    (x2), ENTER verdicts prove reachability (x1). Rows without the snapshot
    fields (pre-2026-07-01) score 0.
    """
    return (
        3.0 * _num(row, "fills")
        + 2.0 * _num(row, "orders_accepted")
        + 2.0 * _num(row, "extra_exec_orders_accepted")
        + 1.0 * _num(row, "enters_last_trading_day")
    )


def _avg_function_score(rows: list[dict[str, Any]]) -> float:
    """MEAN per-fire function score (not sum — several same-night fires snapshot
    the SAME trading day; summing would reward firing more, not trading more)."""
    if not rows:
        return 0.0
    return round(sum(_fire_function_score(r) for r in rows) / len(rows), 4)


def _reconcile_function_fields(
    all_rows: list[dict[str, Any]], rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Backfill-lag correction: replace each row's function fields with the
    MAX seen for that row's ``trading_day`` across the full outcome history.

    Why this exists (2026-08-11, VERIFY-2026-08-10-ZERO-FILLS-DESPITE-ACCEPTED-
    ORDERS follow-up): each row is a POINT-IN-TIME snapshot taken when that fire
    called record(). ``fleet_journal_bridge.py`` backfills journal/trades.csv
    from broker-truth (pnl-statement.json) on its own separate schedule, well
    after the trading day ends — so any conductor fire that snapshots BEFORE
    that backfill lands (e.g. an early-evening fire) correctly captures
    ``fills: 0`` for a day that traded fine. Live-verified 2026-08-11: 3
    consecutive fires (22:40/00:50/01:55 ET) all stored ``fills: 0`` for
    2026-08-10, while `fill_funnel.py --date 2026-08-10` (broker-truth) showed
    GREEN with 6 real fills, and re-running `trading_function_snapshot()` live
    (after the backfill caught up) returned `fills: 11`. Nothing was ever
    trading-broken; the METRIC was reading a stale snapshot.

    fills/orders_accepted/enters_last_trading_day/distinct_setups_traded are
    all monotonically non-decreasing as a day's ledgers get backfilled (the
    session is over; nothing un-fills), so taking the running max per
    trading_day is a safe, non-mutating reconciliation at the READ layer only
    — the stored rows on disk are never rewritten (append-only ledger intact).
    A row with an empty/missing ``trading_day`` is left untouched (nothing to
    key the reconciliation on).
    """
    best: dict[str, dict[str, float]] = {}
    for r in all_rows:
        day = str(r.get("trading_day", "") or "")
        if not day:
            continue
        slot = best.setdefault(day, {f: 0.0 for f in _FUNCTION_FIELDS})
        for f in _FUNCTION_FIELDS:
            slot[f] = max(slot[f], _num(r, f))

    reconciled: list[dict[str, Any]] = []
    for r in rows:
        day = str(r.get("trading_day", "") or "")
        if not day or day not in best:
            reconciled.append(r)
            continue
        merged = dict(r)
        merged.update(best[day])
        reconciled.append(merged)
    return reconciled


def _trend(rows: list[dict[str, Any]], *, decisions_file: Path | None = None) -> str:
    """Compare the recent half vs the older half of the window — FUNCTION FIRST.

    2026-07-01 re-aim: the trend used to compare artifact net_improvement only,
    so a fire adding 41 tests scored like one that made an order fill. Now the
    halves are compared on the trading-function score (fills/orders/enters from
    the ledgers) FIRST; artifact net_improvement only breaks a function tie
    (which is also the exact legacy behavior for pre-snapshot rows, all 0.0).

    2026-09-03 (AUTONOMY-METRIC-ZERO-ENTERS-08-31): before averaging each half,
    rows whose trading_day grades SAT_OUT_GATED or QUIET (see
    _grade_zero_enter_day) are excluded via _filtered_for_trend — a
    doctrine-sanctioned sit-out or a genuinely quiet day is neutral, not a
    regression signal. If excluding those rows empties a half entirely (every
    row in it was a neutral zero-enter day), that half is NOT scored as 0.0 —
    doing so would silently readmit the exact bug this fix closes. Instead its
    function score is tied to the OTHER half's, so a wholly-neutral half never
    manufactures "improving" or "regressing" on its own; the comparison falls
    through to the net_improvement tiebreak below (or to "flat" if both halves
    are wholly neutral).

    Returns "improving" | "flat" | "regressing". With fewer than 2 rows there is
    no basis for a trend -> "flat".
    """
    n = len(rows)
    if n < 2:
        return "flat"
    mid = n // 2
    older = rows[:mid]
    recent = rows[mid:]
    older_kept = _filtered_for_trend(older, decisions_file)
    recent_kept = _filtered_for_trend(recent, decisions_file)
    if not older_kept and not recent_kept:
        older_fn = recent_fn = 0.0
    elif not older_kept:
        recent_fn = _avg_function_score(recent_kept)
        older_fn = recent_fn  # wholly-neutral half ties, never regresses/improves alone
    elif not recent_kept:
        older_fn = _avg_function_score(older_kept)
        recent_fn = older_fn
    else:
        older_fn = _avg_function_score(older_kept)
        recent_fn = _avg_function_score(recent_kept)
    if recent_fn > older_fn:
        return "improving"
    if recent_fn < older_fn:
        return "regressing"
    older_ni = _net_improvement(older)
    recent_ni = _net_improvement(recent)
    if recent_ni > older_ni:
        return "improving"
    if recent_ni < older_ni:
        return "regressing"
    return "flat"


# --- 2) COMPUTE --------------------------------------------------------------
def compute_metric(
    window: int = DEFAULT_WINDOW,
    *,
    outcomes_file: Path | None = None,
    metric_file: Path | None = None,
    decisions_file: Path | None = None,
    write: bool = True,
) -> dict[str, Any]:
    """Fold the last `window` outcome rows into a rolling net-improvement metric.

    Robust to a missing/empty/torn outcomes file -> all-zero metric, trend "flat".
    Writes the result to autonomy-metric.json (unless write=False) and returns it.

    ``decisions_file`` overrides core-decisions.jsonl for zero-enter day grading
    (tests / backfill); defaults to the module-level DECISIONS_FILE.
    """
    out_path = outcomes_file or OUTCOMES_FILE
    met_path = metric_file or METRIC_FILE
    window = max(1, int(window or DEFAULT_WINDOW))

    all_rows = _read_outcomes(out_path)
    rows = all_rows[-window:]  # last N (chronological order preserved)
    # Backfill-lag correction (function fields only) — see
    # _reconcile_function_fields docstring. Does not affect cost/drained/
    # regressions/net_improvement, which are genuinely per-fire, not per-day.
    fn_rows = _reconcile_function_fields(all_rows, rows)

    total_cost = round(sum(_num(r, "cost_usd") for r in rows), 4)
    total_drained = int(sum(_num(r, "items_drained") for r in rows))
    total_regressions = int(sum(_num(r, "regressions") for r in rows))
    fires_counted = len(rows)
    cost_per_drained = round(total_cost / max(1, total_drained), 4)

    latest_snap = fn_rows[-1] if fn_rows else {}
    # AUTONOMY-METRIC-ZERO-ENTERS-08-31 (2026-09-03): grade the latest snapshot's
    # trading day when it recorded 0 enters, so J can see WHY the trend didn't
    # move without cross-referencing core-decisions.jsonl by hand. None when
    # enters>0, no ledger rows for that day, or the day is too short to grade.
    zero_enter_day_grade: dict[str, Any] | None = None
    if latest_snap and int(_num(latest_snap, "enters_last_trading_day")) == 0:
        zero_enter_day_grade = _grade_zero_enter_day(
            str(latest_snap.get("trading_day", "") or ""), decisions_file=decisions_file
        )
    metric: dict[str, Any] = {
        "computed_at": _utc_now_iso(),
        "window": window,
        "net_improvement": _net_improvement(rows),
        "total_drained": total_drained,
        "total_regressions": total_regressions,
        "total_cost_usd": total_cost,
        "cost_per_drained_usd": cost_per_drained,
        "fires_counted": fires_counted,
        # Trading function (the point of the rig — weighted above artifacts).
        # fn_rows (not rows) so a same-day backfill-lag snapshot doesn't fake
        # a regression — see _reconcile_function_fields.
        "function_score_avg": _avg_function_score(fn_rows),
        "function_latest": {
            "trading_day": str(latest_snap.get("trading_day", "") or ""),
            "enters_last_trading_day": int(_num(latest_snap, "enters_last_trading_day")),
            "orders_accepted": int(_num(latest_snap, "orders_accepted")),
            "extra_exec_orders_accepted": int(_num(latest_snap, "extra_exec_orders_accepted")),
            "fills": int(_num(latest_snap, "fills")),
            "distinct_setups_traded": int(_num(latest_snap, "distinct_setups_traded")),
        },
        "trend": _trend(fn_rows, decisions_file=decisions_file),
        "zero_enter_day_grade": zero_enter_day_grade,
    }

    if write:
        try:
            met_path.parent.mkdir(parents=True, exist_ok=True)
            met_path.write_text(json.dumps(metric, indent=2) + "\n", encoding="utf-8")
        except Exception:
            # Writing the metric is best-effort too; still return it to the caller.
            pass

    return metric


# --- CLI ---------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="conductor_outcome",
        description="Record per-fire conductor outcomes and compute the rolling "
        "net-improvement autonomy metric.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    rec = sub.add_parser("record", help="Append one fire-outcome row.")
    rec.add_argument("--task-id", default="", help="Task id this fire worked on.")
    rec.add_argument("--cost", type=float, default=0.0, help="USD spent this fire.")
    rec.add_argument("--drained", type=int, default=0, help="Queue items cleared.")
    rec.add_argument("--added", type=int, default=0, help="Queue items added.")
    rec.add_argument("--lessons", type=int, default=0, help="Lessons shipped.")
    rec.add_argument("--tests-delta", type=int, default=0, help="Net new tests.")
    rec.add_argument("--regressions", type=int, default=0, help="Regressions caused.")
    rec.add_argument("--note", default="", help="Free-form note.")
    rec.add_argument("--fired-at", default=None, help="ISO8601 override (default now).")

    met = sub.add_parser("metric", help="Compute + write autonomy-metric.json.")
    met.add_argument(
        "--window", type=int, default=DEFAULT_WINDOW, help="Rows to fold (default 20)."
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.cmd == "record":
        row = record(
            task_id=args.task_id,
            cost_usd=args.cost,
            items_drained=args.drained,
            items_added=args.added,
            lessons_shipped=args.lessons,
            tests_delta=args.tests_delta,
            regressions=args.regressions,
            note=args.note,
            fired_at=args.fired_at,
        )
        if row is None:
            print("record: FAILED to append outcome (swallowed, non-fatal)", file=sys.stderr)
            return 1
        print(json.dumps(row))
        return 0

    if args.cmd == "metric":
        metric = compute_metric(window=args.window)
        print(json.dumps(metric, indent=2))
        return 0

    return 2  # unreachable: subparser is required


if __name__ == "__main__":
    raise SystemExit(main())

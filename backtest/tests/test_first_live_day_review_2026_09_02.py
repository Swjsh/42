"""Guards for setup/scripts/first_live_day_review.py -- the mechanical replacement for the
work order's "09-02 16:30 ET first-live-day review (Opus, 20 min)" manual checklist
(markdown/planning/OPUS-WORK-ORDER-2026-09.md #1).

All tests are pure-function or use synthetic fixtures under tmp_path (monkeypatching the
module's redirectable path constants, mirroring test_dead_mans_switch_2026_09_01.py's
fake_env fixture). No network, no reads of the real automation/state/.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

_spec = importlib.util.spec_from_file_location(
    "first_live_day_review_g", SCRIPTS / "first_live_day_review.py")
flr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(flr)  # type: ignore[union-attr]


REVIEW_DATE = "2026-09-02"


# --------------------------------------------------------------------------------------- #
# helpers to build synthetic DMS rows
# --------------------------------------------------------------------------------------- #

def _dms_row(ts: str, arm: str, action: str, dry: bool = False) -> dict:
    return {"arm": arm, "ts": ts, "dry": dry, "action": action, "liveness_min": 1.0, "stale": False}


def _clean_day_rows(n_fires: int = 194, arms=("safe-2", "bold-2", "safe-3")) -> list[dict]:
    """Builds a full, gap-free day of DMS rows: n_fires fires, 2 minutes apart, starting
    09:32:00, each fire writing one row per arm a few seconds apart (mirrors the real
    per-arm sequential logging inside check_arm)."""
    rows = []
    start = datetime(2026, 9, 2, 9, 32, 0)
    for i in range(n_fires):
        fire_time = start.replace() + __import__("datetime").timedelta(minutes=2 * i)
        for j, arm in enumerate(arms):
            ts = (fire_time + __import__("datetime").timedelta(seconds=j)).strftime(
                "%Y-%m-%d %H:%M:%S ET")
            rows.append(_dms_row(ts, arm, "LIVE_NO_ACTION"))
    return rows


# ============================================================================
# expected_dms_fire_count / cluster_fire_times
# ============================================================================

def test_expected_dms_fire_count_matches_documented_194():
    assert flr.expected_dms_fire_count() == 194


def test_cluster_fire_times_groups_same_fire_multi_arm_rows():
    from datetime import datetime as dt, timedelta
    base = dt(2026, 9, 2, 9, 32, 0)
    times = [base, base + timedelta(seconds=1), base + timedelta(seconds=2),
             base + timedelta(minutes=2), base + timedelta(minutes=2, seconds=1)]
    fires = flr.cluster_fire_times(times)
    assert len(fires) == 2
    assert fires[0] == base
    assert fires[1] == base + timedelta(minutes=2)


# ============================================================================
# check 1: DMS cadence
# ============================================================================

def test_dms_cadence_clean_day_is_green():
    rows = _clean_day_rows()
    result = flr.check_dms_cadence(rows, REVIEW_DATE)
    assert result["status"] == "GREEN"
    assert result["expected_fires"] == 194
    assert result["actual_fires"] == 194
    assert result["gaps"] == []


def test_dms_cadence_missing_log_is_red_never_fired():
    result = flr.check_dms_cadence([], REVIEW_DATE)
    assert result["status"] == "RED"
    assert "never fired" in result["reason"]
    assert result["actual_fires"] == 0
    assert result["expected_fires"] == 194


def test_dms_cadence_gap_is_enumerated():
    """Drop every fire between 10:00 and 10:20 (a real ~20min hole) and confirm the gap
    shows up by name, not just as a lower total count."""
    rows = _clean_day_rows()
    kept = []
    for r in rows:
        ts = flr._parse_dms_ts(r["ts"])
        if ts is not None and datetime(2026, 9, 2, 10, 0) < ts < datetime(2026, 9, 2, 10, 20):
            continue
        kept.append(r)
    result = flr.check_dms_cadence(kept, REVIEW_DATE)
    assert result["status"] == "RED"
    between = [g for g in result["gaps"] if g["kind"] == "between-fires"]
    assert len(between) == 1
    assert between[0]["gap_min"] > 18  # ~20min hole, threshold is 4min
    assert between[0]["from"] == "10:00:00"


def test_dms_cadence_trailing_gap_caught_even_with_no_between_fire_gap():
    """A switch that fired cleanly all morning then stopped after 13:00 shows NO
    between-fire gap (every fire it DID make was on cadence) unless the window's tail is
    also checked against the last fire."""
    rows = [r for r in _clean_day_rows()
            if flr._parse_dms_ts(r["ts"]) <= datetime(2026, 9, 2, 13, 0, 30)]
    # Evaluate AFTER the window closes -- the trailing gap is only a finding once there is
    # a tail. At 10:47 "stopped after 13:00" and "has not reached 13:00 yet" are the same
    # observation, so the review's own 16:30 fire time is what this must be judged at.
    result = flr.check_dms_cadence(rows, REVIEW_DATE,
                                   now=datetime(2026, 9, 2, 16, 30))
    assert result["status"] == "RED"
    trailing = [g for g in result["gaps"] if g["kind"] == "trailing"]
    assert len(trailing) == 1
    assert trailing[0]["gap_min"] > 100


# ============================================================================
# check 2: DMS verdicts
# ============================================================================

def test_dms_verdicts_clean_day_is_green():
    rows = _clean_day_rows(n_fires=5)
    result = flr.check_dms_verdicts(rows)
    assert result["status"] == "GREEN"
    assert result["bad_rows"] == []


def test_dms_verdicts_flattened_row_is_red():
    rows = _clean_day_rows(n_fires=5)
    rows.append(_dms_row("2026-09-02 12:00:00 ET", "safe-3", "FLATTENED"))
    result = flr.check_dms_verdicts(rows)
    assert result["status"] == "RED"
    assert any(b["action"] == "FLATTENED" for b in result["bad_rows"])


@pytest.mark.parametrize("bad_action", ["ERROR", "NO_CREDS", "READ_FAILED"])
def test_dms_verdicts_error_no_creds_read_failed_are_all_red(bad_action):
    """The work-order text only names FLATTENED/ERROR as failures -- this task explicitly
    adds NO_CREDS and READ_FAILED (a DMS that cannot read the broker is not a DMS)."""
    rows = _clean_day_rows(n_fires=5)
    rows.append(_dms_row("2026-09-02 12:00:00 ET", "risky-1", bad_action))
    result = flr.check_dms_verdicts(rows)
    assert result["status"] == "RED", f"{bad_action} must be treated as a failure"
    assert any(b["action"] == bad_action for b in result["bad_rows"])


def test_dms_verdicts_dry_run_flags_not_armed_not_red():
    rows = [_dms_row("2026-09-02 09:32:00 ET", "safe-2", "LIVE_NO_ACTION", dry=True)
            for _ in range(3)]
    result = flr.check_dms_verdicts(rows)
    assert result["status"] == "YELLOW"
    assert "DRY mode" in result["reason"]
    assert len(result["not_armed_rows"]) == 3


def test_dms_verdicts_dry_run_would_flatten_is_bad_and_not_armed():
    rows = [_dms_row("2026-09-02 12:00:00 ET", "bold-2", "DRY_RUN_WOULD_FLATTEN", dry=True)]
    result = flr.check_dms_verdicts(rows)
    assert result["status"] == "RED"
    assert len(result["not_armed_rows"]) == 1


def test_dms_verdicts_empty_is_red_never_fired():
    result = flr.check_dms_verdicts([])
    assert result["status"] == "RED"
    assert "never fired" in result["reason"]


def test_dms_verdicts_unknown_action_fails_loud():
    rows = [_dms_row("2026-09-02 09:32:00 ET", "safe-2", "SOMETHING_NEW_AND_UNDOCUMENTED")]
    result = flr.check_dms_verdicts(rows)
    assert result["status"] == "RED"


# ============================================================================
# check 3: engine_health
# ============================================================================

def test_engine_health_green():
    eh = {"checks": [{"name": "escalation_flags", "status": "GREEN"},
                      {"name": "duplicate_ticks", "status": "GREEN"}]}
    result = flr.check_engine_health(eh)
    assert result["status"] == "GREEN"


def test_engine_health_missing_file_is_red():
    result = flr.check_engine_health(None)
    assert result["status"] == "RED"


def test_engine_health_check_not_present_is_red():
    eh = {"checks": [{"name": "escalation_flags", "status": "GREEN"}]}  # duplicate_ticks absent
    result = flr.check_engine_health(eh)
    assert result["status"] == "RED"
    assert "duplicate_ticks" in result["reason"]


def test_engine_health_red_subcheck_propagates():
    eh = {"checks": [{"name": "escalation_flags", "status": "RED", "detail": "unresolved flag"},
                      {"name": "duplicate_ticks", "status": "GREEN"}]}
    result = flr.check_engine_health(eh)
    assert result["status"] == "RED"


# ============================================================================
# check 4: eod flatten aggressive
# ============================================================================

REAL_FAIL_LOG_EXCERPT_2026_09_01 = (
    "2026-09-01 15:55:02 ET FIRE et=15:55:02\n"
    "2026-09-01 15:55:05 ET === START tick (timeout=120s effort=low budget=2 model=sonnet freeMB=47315) ===\n"
    "2026-09-01 15:55:XX ET MCP_UNREACHABLE mcp__alpaca_aggressive__ never resolved after 6 ToolSearch retries (~5min), 2nd consecutive day (also 2026-08-31)\n"
    "2026-09-01 15:55:XX ET AGG_EOD_FLATTEN_ABORTED reason=alpaca_aggressive_unreachable local_state=flat(unverified)\n"
    "2026-09-01 15:55:XX ET KILL_SWITCH_SET reason=\"AGG EOD flatten failed - manual intervention required\" repeat_count=2\n"
    "2026-09-01 15:55:XX ET === END tick exit=1 (kill-switch, needs J to verify Bold flat via broker) ===\n"
    "2026-09-01 15:57:11 ET TIMEOUT after 120s - killing root pid=7220 plus 12 descendants\n"
    "TIMEOUT_KILL: claude --print exceeded 120s wall clock. Tree-killed 9 processes (root=7220). Self-heal triggered.\n"
    "2026-09-01 15:57:13 ET === END tick exit=124 (timeout) ===\n"
)


def test_eod_flatten_core_good_agg_ok_is_green():
    core_rows = [{"arm": "bold-2", "outcome": "NOOP", "ts": "2026-09-02 15:52:01 ET"}]
    result = flr.check_eod_flatten_aggressive(core_rows, "=== END tick exit=0 ===")
    assert result["status"] == "GREEN"
    assert result["core_confirmed_flat"] is True


def test_eod_flatten_core_missing_is_red():
    result = flr.check_eod_flatten_aggressive([], "=== END tick exit=0 ===")
    assert result["status"] == "RED"
    assert result["core_outcome"] == "MISSING"


def test_eod_flatten_core_read_failed_is_red():
    core_rows = [{"arm": "bold-2", "outcome": "READ_FAILED", "ts": "2026-09-02 15:52:01 ET"}]
    result = flr.check_eod_flatten_aggressive(core_rows, None)
    assert result["status"] == "RED"


def test_eod_flatten_core_ok_agg_failed_real_log_is_yellow_named_loud():
    """Reproduces the REAL 2026-09-01 failure signature (quoted verbatim from
    automation/state/logs/eod-flatten-aggressive-2026-09-01.log) -- Core covering bold-2
    keeps the account safe, but the LLM flattener's own failure must still surface loudly,
    not be swallowed because Core succeeded."""
    core_rows = [{"arm": "bold-2", "outcome": "NOOP", "ts": "2026-09-01 15:52:01 ET"}]
    result = flr.check_eod_flatten_aggressive(core_rows, REAL_FAIL_LOG_EXCERPT_2026_09_01)
    assert result["status"] == "YELLOW"
    assert result["agg_llm_status"] == "FAILED"
    assert "MCP_UNREACHABLE" in result["agg_llm_evidence"]


def test_eod_flatten_agg_log_missing_does_not_block_core_pass():
    core_rows = [{"arm": "bold-2", "outcome": "SUCCESS", "ts": "2026-09-02 15:52:01 ET"}]
    result = flr.check_eod_flatten_aggressive(core_rows, None)
    assert result["status"] == "GREEN"
    assert result["agg_llm_status"] == "NO_LOG"


# --------------------------------------------------------------------------------------- #
# A REHEARSAL IS NOT A FLATTEN (added 2026-09-02, caught in production, not in review).
#
# THE SCAR, verbatim from automation/state/logs/eod-flatten-2026-09-02.jsonl. An early-close
# flatten REHEARSAL ran at 06:14 ET with an injected clock and wrote four rows stamped
# "2026-09-02 12:45:00 ET" carrying `"dry": true, "outcome": "NOOP"` into the PRODUCTION
# ledger. At 11:12 ET -- with the real 15:52 sweep still four hours in the future and the
# actual 16:00 close confirmed by the broker calendar -- run_review() reported
# "Core flatten confirmed flat for bold-2 (NOOP)" and graded the whole day GREEN.
#
# WHY IT MATTERS MORE THAN A COSMETIC MISREPORT: this check is the only thing standing
# between an unflattened 0DTE position and an overnight hold. The failure mode it must
# catch is "the 15:52 sweep did not run". A leftover drill row makes that exact case report
# green, so the instrument is loudest precisely when it is wrong.
#
# TWO INDEPENDENT DEFECTS, both fixed, both pinned below:
#   1. "DRY_RUN" was a member of EOD_CORE_GOOD_OUTCOMES -- a dry run flattens nothing.
#   2. Nothing filtered `dry: true`, so a NOOP rehearsal row was read as production evidence.
# Either alone reproduces the false green, so each gets its own test.
# --------------------------------------------------------------------------------------- #

REAL_REHEARSAL_ROWS_2026_09_02 = [
    {"arm": "bold-2", "ts": "2026-09-02 12:45:00 ET", "dry": True, "reason": "EARLY_CLOSE",
     "outcome": "NOOP", "closed": [], "errors": [], "remaining": 0},
]


def test_dry_rehearsal_row_alone_is_not_a_confirmed_flatten():
    """THE production case. Four such rows existed today and graded the day GREEN."""
    result = flr.check_eod_flatten_aggressive(REAL_REHEARSAL_ROWS_2026_09_02,
                                              "=== END tick exit=0 ===")
    assert result["status"] == "RED", (
        f"a dry-run rehearsal was accepted as proof the account was flattened: {result}"
    )
    assert result["core_confirmed_flat"] is False
    assert result["core_outcome"] == "MISSING_ONLY_REHEARSALS"


def test_the_ignored_rehearsals_are_named_not_silently_dropped():
    """A ledger holding rows that reads MISSING with no explanation is a report an operator
    argues with instead of acting on. The count must appear in the human-facing reason."""
    result = flr.check_eod_flatten_aggressive(REAL_REHEARSAL_ROWS_2026_09_02, None)
    assert result["rehearsal_rows_ignored"] == 1
    assert "rehearsal" in result["reason"].lower(), result["reason"]


def test_dry_run_outcome_is_not_a_good_outcome():
    """Defect 1 in isolation: even a row NOT marked `dry` cannot pass on outcome DRY_RUN."""
    assert "DRY_RUN" not in flr.EOD_CORE_GOOD_OUTCOMES
    result = flr.check_eod_flatten_aggressive(
        [{"arm": "bold-2", "outcome": "DRY_RUN", "ts": "2026-09-02 15:52:01 ET"}], None)
    assert result["status"] == "RED", result


def test_a_real_flatten_still_passes_when_a_rehearsal_also_ran_that_day():
    """The other direction, and the reason this fix is safe to ship: a drill earlier in the
    day must not RED a day whose real 15:52 sweep genuinely confirmed flat. Every production
    row since 2026-08-21 carries `dry: False`, so live evidence survives the filter."""
    rows = REAL_REHEARSAL_ROWS_2026_09_02 + [
        {"arm": "bold-2", "outcome": "NOOP", "dry": False, "ts": "2026-09-02 15:52:01 ET"},
    ]
    result = flr.check_eod_flatten_aggressive(rows, "=== END tick exit=0 ===")
    assert result["status"] == "GREEN", result
    assert result["rehearsal_rows_ignored"] == 1
    assert "rehearsal" in result["reason"].lower()


def test_rehearsal_filter_does_not_mask_a_real_failure_that_came_after_it():
    """Ordering matters: the LAST live row wins, and a rehearsal must not shift which row
    that is. A drill followed by a genuinely failed sweep stays RED."""
    rows = REAL_REHEARSAL_ROWS_2026_09_02 + [
        {"arm": "bold-2", "outcome": "READ_FAILED", "dry": False, "ts": "2026-09-02 15:52:01 ET"},
    ]
    result = flr.check_eod_flatten_aggressive(rows, None)
    assert result["status"] == "RED"
    assert result["core_outcome"] == "READ_FAILED", result


# ============================================================================
# check 6: fleet kill-switch proximity
# ============================================================================

def test_fleet_kill_switch_no_data_before_market_open():
    result = flr.check_fleet_kill_switch_proximity(
        ["safe-3"], {"safe-3": {"starting_equity_today": 5000.0, "daily_loss_limit_pct": 0.3,
                                 "tripped": False}},
        {"safe-3": None})
    # ASSERTION CHANGED 2026-09-02, deliberately, with reasoning -- not weakened.
    # It previously read `== "GREEN"  # NO_DATA does not gate`. The INTENT is right (an
    # arm with no rows should not hard-FAIL a pre-market run) but the assertion conflated
    # "does not gate" with "reports healthy". Absence must never render as GREEN: this
    # review is built to run at 16:30 ET, after a full session, where zero equity rows
    # means the arm never ticked. NO_DATA is the honest third state -- it surfaces without
    # claiming health, and RED stays reserved for a measured breach.
    assert result["status"] != "GREEN", "absence must not render as health"
    assert result["status"] == "NO_DATA"
    assert result["arms"]["safe-3"]["status"] == "NO_DATA"


def test_fleet_kill_switch_breach_is_red_even_if_not_tripped():
    """The whole point of this check: Rule 5 is NOT latched on fleet arms, so
    circuit-breaker.json#tripped can read false even after a real breach."""
    result = flr.check_fleet_kill_switch_proximity(
        ["safe-3"],
        {"safe-3": {"starting_equity_today": 5000.0, "daily_loss_limit_pct": 0.3, "tripped": False}},
        {"safe-3": 3400.0})  # -32% draw, floor is -30%
    assert result["status"] == "RED"
    assert result["arms"]["safe-3"]["tripped"] is False
    assert result["arms"]["safe-3"]["status"] == "RED"


def test_fleet_kill_switch_close_to_floor_is_yellow():
    result = flr.check_fleet_kill_switch_proximity(
        ["risky-1"],
        {"risky-1": {"starting_equity_today": 6000.0, "daily_loss_limit_pct": 0.5, "tripped": False}},
        {"risky-1": 3060.0})  # -49% draw, floor -50%, headroom 1pp
    assert result["status"] == "YELLOW"


def test_fleet_kill_switch_accounts_unreadable_is_red():
    result = flr.check_fleet_kill_switch_proximity(None, {}, {})
    assert result["status"] == "RED"


def test_fleet_kill_switch_no_active_arms_is_green():
    result = flr.check_fleet_kill_switch_proximity([], {}, {})
    assert result["status"] == "GREEN"


def test_active_fleet_rest_arms_excludes_core_and_retired():
    accounts = {"arms": [
        {"id": "safe-3", "execution": "fleet_rest", "status": "active"},
        {"id": "safe-2", "execution": "mcp_heartbeat", "status": "active"},
        {"id": "risky-3", "execution": "fleet_rest", "status": "retired"},
        {"id": "risky-1", "execution": "fleet_rest", "status": "active"},
    ]}
    arms = flr.active_fleet_rest_arms(accounts)
    assert set(arms) == {"safe-3", "risky-1"}


def test_active_fleet_rest_arms_none_on_unreadable():
    assert flr.active_fleet_rest_arms(None) is None


def test_min_equity_for_date_filters_by_date_and_ignores_nulls():
    rows = [
        {"ts_et": "2026-09-01T15:50:00-0400", "equity": 5000.0},
        {"ts_et": "2026-09-02T09:33:00-0400", "equity": 4900.0},
        {"ts_et": "2026-09-02T10:00:00-0400", "equity": 4700.0},
        {"ts_et": "2026-09-02T10:05:00-0400", "equity": None},
    ]
    assert flr.min_equity_for_date(rows, "2026-09-02") == 4700.0
    assert flr.min_equity_for_date(rows, "2026-09-03") is None


# ============================================================================
# check 7: Gamma_GuardsFull
# ============================================================================

def test_guards_full_clean_run_is_not_flagged():
    """Uses the REAL guard_runner_full.py write schema (counts.failed nested, no top-level
    'failed' key -- confirmed live against automation/state/guard-watch-full.json).

    BASELINE CHANGED 4 -> 0 on 2026-09-02. This test previously asserted that FOUR failures
    were fine, because four guards were known-stale. They were repaired (fb34ca92) and the
    full suite then came back 11,739 passed / 0 failed, so the tolerance no longer describes
    anything -- and at 4 this check would report GREEN for any four failures, including four
    brand-new real ones."""
    state = {"status": "green", "at": "2026-09-02 11:09 ET",
             "counts": {"passed": 11739, "failed": 0, "skipped": 11}, "returncode": 0}
    result = flr.check_guards_full(state, REVIEW_DATE)
    assert result["status"] == "GREEN"


def test_guards_full_four_failures_is_NOW_flagged():
    """The teeth the old baseline removed: four failures must no longer pass silently."""
    state = {"status": "red", "at": "2026-09-02 11:09 ET",
             "counts": {"passed": 11097, "failed": 4, "skipped": 11}, "returncode": 1}
    result = flr.check_guards_full(state, REVIEW_DATE)
    assert result["status"] == "YELLOW", (
        "four failures went unflagged -- the stale known-failure tolerance is back"
    )


def test_guards_full_five_failures_is_flagged():
    state = {"status": "red", "at": "2026-09-01 23:20 ET",
             "counts": {"passed": 11096, "failed": 5, "skipped": 11}, "returncode": 1}
    result = flr.check_guards_full(state, REVIEW_DATE)
    assert result["status"] == "YELLOW"
    # This state is FRESH (dated the day before the review); the point here is that a
    # count of 5 deviates from the expected 4. Assert semantics, not the reason's prose.
    assert result["failed"] == 5 and result["expected_failed"] == 0
    assert result["failed"] != result["expected_failed"]
    assert not result["stale"], "2026-09-01 vs a 2026-09-02 review is not stale"


def test_guards_full_top_level_failed_key_still_accepted_as_fallback():
    """Forward-compat fallback: a bare top-level 'failed' (not the real current schema, but
    accepted in case the writer's shape ever changes back) is still read correctly."""
    state = {"status": "green", "at": "2026-09-01 23:20 ET", "failed": 0}
    result = flr.check_guards_full(state, REVIEW_DATE)
    assert result["status"] == "GREEN"
    assert result["failed"] == 0, "the top-level 'failed' key was not read"


def test_guards_full_zero_verdict_is_flagged():
    """No verdict at all (missing/unreadable state file) must be RED, not a bare pass."""
    result = flr.check_guards_full(None, REVIEW_DATE)
    assert result["status"] == "RED"
    assert "no verdict" in result["reason"]


def test_guards_full_missing_failed_key_is_flagged():
    result = flr.check_guards_full({"status": "unknown"}, REVIEW_DATE)
    assert result["status"] == "RED"


def test_guards_full_correct_count_but_stale_is_flagged():
    """Reproduces the real state: failed=4 would be the expected steady-state, but the
    file is dated 2026-08-31 while the review is for 2026-09-02 -- 2 days stale."""
    state = {"status": "red", "at": "2026-08-31 09:55 ET",
             "counts": {"passed": 11097, "failed": 4, "skipped": 11}, "returncode": 1}
    result = flr.check_guards_full(state, REVIEW_DATE)
    assert result["status"] == "YELLOW"
    # Assert SEMANTICS, not prose. This originally read `"stale" in reason` and broke on
    # a capitalisation change alone -- the same copy-drift class that left
    # test_entry_block_watch asserting a phrase the composer had deliberately dropped.
    assert result["stale"] is True
    assert "stale" in result["reason"].lower()


def test_guards_full_real_current_state_is_flagged_deviates_and_stale():
    """The ACTUAL guard-watch-full.json content read live this session (cat'd from
    automation/state/guard-watch-full.json): failed=8 nested under counts (no top-level
    'failed' key at all), dated 2026-08-31 (stale vs a 2026-09-02 review)."""
    state = {"status": "red", "at": "2026-08-31 09:55 ET",
             "counts": {"passed": 11097, "failed": 8, "skipped": 11},
             "failed_names": [
                 "tests/test_cheap_contract_qty_boost_2026_08_03.py::test_boost_fires_below_threshold",
                 "tests/test_cheap_contract_qty_boost_2026_08_03.py::test_threshold_is_strictly_below[0.49-10]",
                 "tests/test_cheap_contract_qty_boost_2026_08_03.py::test_boost_never_shrinks_a_larger_plan",
                 "tests/test_graduated_guards.py::test_free_model_cost_estimate_is_zero",
                 "tests/test_quiet_mode_weekend_research_2026_08_30.py::TestPresenceDowngrade::test_gaming_outside_the_research_band_still_blacks_out",
                 "tests/test_trades_enriched.py::test_real_tape_2026_08_27_and_august_totals",
                 "tests/test_trades_enriched.py::test_real_tape_verification_passes",
                 "tests/test_trades_enriched.py::test_both_bases_reproduce_august_1744",
             ],
             "returncode": 1}
    result = flr.check_guards_full(state, REVIEW_DATE)
    assert result["status"] == "YELLOW"
    # Semantics, not wording. The real 2026-08-31 state is BOTH stale and deviating,
    # and staleness leads the sentence because a stale verdict makes its own count
    # meaningless -- an operator must not read "failed=8" as "8 real failures today".
    assert result["stale"] is True
    assert result["failed"] != result["expected_failed"]
    assert "stale" in result["reason"].lower()
    assert str(result["expected_failed"]) in result["reason"]


def test_guards_full_no_top_level_failed_key_and_no_counts_is_red():
    """A state dict with neither a nested counts.failed nor a top-level failed key (e.g. a
    timeout write: {'status':'timeout','at':...}) must be RED, not silently coerced."""
    result = flr.check_guards_full({"status": "timeout", "at": "2026-09-01 23:20 ET"}, REVIEW_DATE)
    assert result["status"] == "RED"


# ============================================================================
# check 5: conductor picks (advisory)
# ============================================================================

def test_conductor_picks_no_open_items_is_advisory_noop():
    result = flr.check_conductor_picks(
        "## [2026-09-01T23:00 ET] conductor: OK -- did stuff\nbody text\n",
        "- [x] SOME-DONE-ITEM (HIGH, GATE-BLOCKING, filed) :: done\n",
        REVIEW_DATE)
    assert result["status"] == "ADVISORY"
    assert result["open_gate_blocking_items"] == []


def test_conductor_picks_open_item_mentioned_is_fine():
    status_md = ("## [2026-09-01T23:00 ET] conductor: OK -- picked GATE-BLOCKING item\n"
                 "considered GATE-BLOCKING tier first\n")
    queue_md = "- [ ] SOME-OPEN-ITEM (HIGH, GATE-BLOCKING, filed) :: depends:none :: status:open\n"
    result = flr.check_conductor_picks(status_md, queue_md, REVIEW_DATE)
    assert result["open_gate_blocking_items"] == ["SOME-OPEN-ITEM"]
    assert result["fires_missing_gate_blocking_mention"] == []


def test_conductor_picks_never_gates_overall_verdict():
    checks = {
        "dms_cadence": {"status": "GREEN"},
        "dms_verdicts": {"status": "GREEN"},
        "engine_health": {"status": "GREEN"},
        "eod_flatten_aggressive": {"status": "GREEN"},
        "fleet_kill_switch": {"status": "GREEN"},
        "guards_full": {"status": "GREEN"},
        "conductor_picks": {"status": "ADVISORY"},
    }
    verdict, failing = flr.combine_verdict(checks)
    assert verdict == "GREEN"
    assert failing == []


# ============================================================================
# combine_verdict worst-wins
# ============================================================================

def test_combine_verdict_worst_wins_and_names_failing_checks():
    checks = {
        "dms_cadence": {"status": "GREEN"},
        "dms_verdicts": {"status": "RED"},
        "engine_health": {"status": "YELLOW"},
        "eod_flatten_aggressive": {"status": "GREEN"},
        "fleet_kill_switch": {"status": "GREEN"},
        "guards_full": {"status": "GREEN"},
        "conductor_picks": {"status": "ADVISORY"},
    }
    verdict, failing = flr.combine_verdict(checks)
    assert verdict == "RED"
    assert "dms_verdicts:RED" in failing
    assert "engine_health:YELLOW" in failing


# ============================================================================
# full-pipeline integration: empty real state (the structural dry run this task itself
# demanded be proven) -- monkeypatches every path constant into an EMPTY tmp_path tree.
# ============================================================================

@pytest.fixture()
def empty_state_env(tmp_path, monkeypatch):
    monkeypatch.setattr(flr, "DMS_LOG_DIR", tmp_path / "automation" / "state" / "logs")
    monkeypatch.setattr(flr, "DMS_STATE_PATH", tmp_path / "automation" / "state" / "dead-mans-switch.json")
    monkeypatch.setattr(flr, "ENGINE_HEALTH_PATH", tmp_path / "automation" / "state" / "engine-health.json")
    monkeypatch.setattr(flr, "GUARDS_FULL_PATH", tmp_path / "automation" / "state" / "guard-watch-full.json")
    monkeypatch.setattr(flr, "ACCOUNTS_PATH", tmp_path / "automation" / "state" / "fleet" / "accounts.json")
    monkeypatch.setattr(flr, "FLEET_DIR", tmp_path / "automation" / "state" / "fleet")
    monkeypatch.setattr(flr, "EOD_LOG_DIR", tmp_path / "automation" / "state" / "logs")
    monkeypatch.setattr(flr, "STATUS_MD_PATH", tmp_path / "automation" / "overnight" / "STATUS.md")
    monkeypatch.setattr(flr, "QUEUE_MD_PATH", tmp_path / "automation" / "overnight" / "queue.md")
    monkeypatch.setattr(flr, "OUT_DIR", tmp_path / "analysis" / "first-live-day")
    return tmp_path


def test_run_review_on_completely_empty_state_is_red_never_fired(empty_state_env):
    """This is the exact scenario the task demanded be proven structurally: an empty real
    state (nothing has run yet -- market not open) must return RED 'never fired', never a
    GREEN-by-absence."""
    report = flr.run_review(REVIEW_DATE)
    assert report["verdict"] == "RED"
    assert "dms_cadence:RED" in report["failing_checks"]
    assert "dms_verdicts:RED" in report["failing_checks"]
    assert report["checks"]["dms_cadence"]["reason"].startswith("never fired")
    # startswith, matching the dms_cadence assertion two lines up. The property under test
    # is "RED, never fired" -- never green-by-absence -- not the exact wording. The message
    # gained "inside the window" on 2026-09-02 when the checks started excluding
    # out-of-window rehearsal rows, which is strictly more informative.
    assert report["checks"]["dms_verdicts"]["reason"].startswith("never fired")
    assert "0 rows to verify" in report["checks"]["dms_verdicts"]["reason"]
    # engine_health / guards_full / eod_flatten / fleet_kill_switch all missing -> also RED,
    # EXCEPT fleet_kill_switch which reports GREEN with 0 arms when accounts.json is simply
    # absent-but-empty-derived is NOT the case here -- accounts.json is missing entirely, so
    # active_fleet_rest_arms returns None -> RED.
    assert report["checks"]["engine_health"]["status"] == "RED"
    assert report["checks"]["guards_full"]["status"] == "RED"
    assert report["checks"]["fleet_kill_switch"]["status"] == "RED"
    assert report["checks"]["eod_flatten_aggressive"]["status"] == "RED"


def test_run_review_writes_json_and_md_outputs(empty_state_env, tmp_path):
    report = flr.run_review(REVIEW_DATE)
    json_path, md_path = flr.write_outputs(report)
    assert json_path.exists()
    assert md_path.exists()
    on_disk = json.loads(json_path.read_text(encoding="utf-8"))
    assert on_disk["verdict"] == "RED"
    assert on_disk["review_date"] == REVIEW_DATE
    md_text = md_path.read_text(encoding="utf-8")
    assert "# First-live-day review -- 2026-09-02" in md_text
    assert "## Verdict: RED" in md_text


def test_run_review_clean_day_end_to_end_is_green(empty_state_env, tmp_path):
    """Populates a fully healthy synthetic day and confirms the pipeline reports GREEN --
    the positive-path mirror of the empty-state RED test above."""
    logs_dir = tmp_path / "automation" / "state" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    dms_path = logs_dir / f"dead-mans-switch-{REVIEW_DATE}.jsonl"
    with dms_path.open("w", encoding="utf-8") as f:
        for row in _clean_day_rows(n_fires=194, arms=("safe-2", "bold-2")):
            f.write(json.dumps(row) + "\n")

    eh_path = tmp_path / "automation" / "state" / "engine-health.json"
    eh_path.write_text(json.dumps({"checks": [
        {"name": "escalation_flags", "status": "GREEN"},
        {"name": "duplicate_ticks", "status": "GREEN"},
    ]}), encoding="utf-8")

    # A CLEAN DAY MEANS A CLEAN SUITE (fixture corrected 2026-09-02 with the tolerance move
    # 4 -> 0). This fixture previously wrote status=red / failed=4 / returncode=1 and still
    # expected the day to grade GREEN, because the old tolerance treated 4 failures as
    # steady state. check_guards_full reads only `failed` and `at`, so the red status and
    # non-zero returncode were never consulted -- an incoherent fixture that happened not to
    # matter. Left as-is it would start lying the moment the check learns to read either
    # field, so the whole record is made internally consistent rather than just the count.
    gf_path = tmp_path / "automation" / "state" / "guard-watch-full.json"
    gf_path.write_text(json.dumps({"status": "green", "at": f"{REVIEW_DATE} 23:20 ET",
                                    "counts": {"passed": 11739, "failed": 0, "skipped": 11},
                                    "returncode": 0}), encoding="utf-8")

    fleet_dir = tmp_path / "automation" / "state" / "fleet"
    accounts_path = fleet_dir / "accounts.json"
    accounts_path.parent.mkdir(parents=True, exist_ok=True)
    accounts_path.write_text(json.dumps({"arms": [
        {"id": "safe-3", "execution": "fleet_rest", "status": "active"},
    ]}), encoding="utf-8")
    (fleet_dir / "safe-3").mkdir(parents=True, exist_ok=True)
    (fleet_dir / "safe-3" / "circuit-breaker.json").write_text(json.dumps({
        "starting_equity_today": 5000.0, "daily_loss_limit_pct": 0.3, "tripped": False,
    }), encoding="utf-8")
    with (fleet_dir / "safe-3" / "decisions.jsonl").open("w", encoding="utf-8") as f:
        f.write(json.dumps({"ts_et": f"{REVIEW_DATE}T10:00:00-0400", "equity": 4990.0}) + "\n")

    core_eod_path = logs_dir / f"eod-flatten-{REVIEW_DATE}.jsonl"
    with core_eod_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"arm": "bold-2", "outcome": "NOOP",
                             "ts": f"{REVIEW_DATE} 15:52:01 ET"}) + "\n")
    agg_log_path = logs_dir / f"eod-flatten-aggressive-{REVIEW_DATE}.log"
    agg_log_path.write_text(f"{REVIEW_DATE} 15:55:05 ET === END tick exit=0 ===\n",
                             encoding="utf-8")

    overnight_dir = tmp_path / "automation" / "overnight"
    overnight_dir.mkdir(parents=True, exist_ok=True)
    (overnight_dir / "STATUS.md").write_text("## [2026-09-01T23:00 ET] conductor: OK\nno open items\n",
                                              encoding="utf-8")
    (overnight_dir / "queue.md").write_text("- [x] DONE-ITEM (GATE-BLOCKING) :: status:done\n",
                                             encoding="utf-8")

    report = flr.run_review(REVIEW_DATE)
    assert report["verdict"] == "GREEN", report["failing_checks"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))


# --------------------------------------------------------------------------------------- #
# NO_DATA IS NOT GREEN (added 2026-09-02 on review). The fleet proximity check originally
# ranked NO_DATA equal to GREEN and did not update the aggregate, so an arm that never
# ticked reported as healthy. That is the guard_runner_full scar -- a report that goes
# nowhere manufactures the belief something is watching -- reappearing in a new instrument.
# --------------------------------------------------------------------------------------- #
def test_fleet_proximity_no_data_does_not_read_as_green():
    out = flr.check_fleet_kill_switch_proximity(
        ["safe-3"],
        {"safe-3": {"starting_equity_today": 5000.0, "daily_loss_limit_pct": 0.30,
                    "tripped": False}},
        {"safe-3": None},          # no equity rows at all
    )
    assert out["status"] != "GREEN", (
        "an arm with no equity rows for the day must NOT report GREEN -- absence is not health")
    assert out["arms"]["safe-3"]["status"] == "NO_DATA"
    assert "NO DATA" in out["reason"]


def test_fleet_proximity_no_data_does_not_mask_a_real_breach():
    """Worst-wins must still surface a RED on another arm."""
    out = flr.check_fleet_kill_switch_proximity(
        ["safe-3", "risky-1"],
        {"safe-3": {"starting_equity_today": 5000.0, "daily_loss_limit_pct": 0.30, "tripped": False},
         "risky-1": {"starting_equity_today": 5000.0, "daily_loss_limit_pct": 0.30, "tripped": False}},
        {"safe-3": None, "risky-1": 3000.0},   # risky-1 drew -40%, past the -30% floor
    )
    assert out["status"] == "RED"
    assert out["arms"]["risky-1"]["status"] == "RED"


def test_fleet_proximity_still_green_when_every_arm_has_healthy_data():
    out = flr.check_fleet_kill_switch_proximity(
        ["safe-3"],
        {"safe-3": {"starting_equity_today": 5000.0, "daily_loss_limit_pct": 0.30, "tripped": False}},
        {"safe-3": 4900.0},        # -2% draw, 28pp headroom
    )
    assert out["status"] == "GREEN", "a genuinely healthy arm must still read GREEN"


# ============================================================================
# NO_DATA IS NOT GREEN -- AT THE OUTER AGGREGATOR TOO (added 2026-09-02, second pass).
# The inner fleet-proximity order was corrected earlier the same night; combine_verdict one
# function later was left ranking NO_DATA at 0, so absence still read as health at the level
# that actually produces the day's verdict. Found by reading the real 02:15 ET artifact,
# where fleet_kill_switch had genuinely returned NO_DATA.
# ============================================================================

def test_no_data_gating_check_escalates_the_overall_verdict():
    checks = {
        "dms_cadence": {"status": "GREEN"},
        "dms_verdicts": {"status": "GREEN"},
        "engine_health": {"status": "GREEN"},
        "eod_flatten_aggressive": {"status": "GREEN"},
        "fleet_kill_switch": {"status": "NO_DATA"},
        "guards_full": {"status": "GREEN"},
        "conductor_picks": {"status": "ADVISORY"},
    }
    verdict, failing = flr.combine_verdict(checks)
    assert verdict == "NO_DATA", "a gating check with no data must not read as a clean pass"
    assert "fleet_kill_switch:NO_DATA" in failing


def test_all_no_data_is_not_green():
    """Every state file missing -- the box died -- must never grade as a clean day."""
    checks = {name: {"status": "NO_DATA"} for name in flr._GATING_CHECKS}
    verdict, failing = flr.combine_verdict(checks)
    assert verdict != "GREEN"
    assert len(failing) == len(flr._GATING_CHECKS)


def test_a_missing_gating_check_is_no_data_not_a_skip():
    """An absent check means the day was not fully reviewed. Silently dropping it from the
    worst-wins fold is the same GREEN-by-absence bug in a different costume."""
    checks = {
        "dms_cadence": {"status": "GREEN"},
        "dms_verdicts": {"status": "GREEN"},
        "engine_health": {"status": "GREEN"},
        "eod_flatten_aggressive": {"status": "GREEN"},
        "guards_full": {"status": "GREEN"},
        # fleet_kill_switch deliberately absent
    }
    verdict, failing = flr.combine_verdict(checks)
    assert verdict == "NO_DATA"
    assert "fleet_kill_switch:NO_DATA" in failing


def test_red_still_outranks_no_data():
    checks = {name: {"status": "NO_DATA"} for name in flr._GATING_CHECKS}
    checks["dms_verdicts"] = {"status": "RED"}
    verdict, _ = flr.combine_verdict(checks)
    assert verdict == "RED"


def test_advisory_still_never_gates():
    """The fix must not sweep up conductor_picks: it is excluded BY DESIGN, which is a
    different thing from absence."""
    checks = {name: {"status": "GREEN"} for name in flr._GATING_CHECKS}
    checks["conductor_picks"] = {"status": "ADVISORY"}
    verdict, failing = flr.combine_verdict(checks)
    assert verdict == "GREEN"
    assert failing == []


# ============================================================================
# Out-of-window rehearsal rows (added 2026-09-02)
#
# The DMS gained an out-of-hours DRY rehearsal path so a safety instrument could be
# exercised before being trusted in production. On its FIRST production day a 06:10
# pre-flight (4 rows, one per arm) made this review report RED on cadence (a bogus 201.8-min
# "between-fires" gap from the rehearsal to the 09:32 first real fire) and YELLOW on verdicts
# ("DMS was NOT armed"), while every real fire from 09:32 onward was armed and on cadence.
# A review that cannot tell a rehearsal from a production fire cannot be trusted to grade the
# day it exists to grade.
# ============================================================================

def _fire(ts: str, arm: str = "safe-2", action: str = "LIVE_NO_ACTION", dry: bool = False):
    return {"ts": f"2026-09-02 {ts} ET", "arm": arm, "action": action, "dry": dry}


def test_cadence_ignores_an_out_of_window_rehearsal_fire():
    """The literal 2026-09-02 defect: a 06:10 rehearsal must not create a gap to 09:32."""
    rows = [_fire("06:10:11", dry=True)] + [
        _fire(f"{h:02d}:{m:02d}:01")
        for h in range(9, 16) for m in range(0, 60, 2)
        # stop at 15:56 -- fires land at :01 seconds, so a 15:58:01 fire would sit one
        # second PAST the 15:58 window end and be (correctly) counted out-of-window,
        # which would make this test's out_of_window_fires assertion about the wrong row.
        if (h, m) >= (9, 32) and (h, m) <= (15, 56)
    ]
    r = flr.check_dms_cadence(rows, REVIEW_DATE, now=datetime(2026, 9, 2, 16, 30))
    assert r["out_of_window_fires"] == 1, "the 06:10 rehearsal was not excluded"
    assert not [g for g in r["gaps"] if g["kind"] == "between-fires"], (
        f"a rehearsal fire invented a between-fires gap: {r['gaps']}"
    )
    assert r["status"] == "GREEN"
    assert "out-of-window" in r["reason"], "exclusion must be DISCLOSED, not silent"


def test_trailing_gap_is_not_judged_while_the_window_is_still_open():
    """Judged at 10:47 the whole remaining session reads as a 312-minute 'gap'. Before the
    window closes, 'stopped firing' and 'has not got there yet' are the same observation."""
    rows = [_fire(f"{h:02d}:{m:02d}:01") for h in (9, 10) for m in range(0, 60, 2)
            if (h, m) >= (9, 32)]
    open_now = flr.check_dms_cadence(rows, REVIEW_DATE, now=datetime(2026, 9, 2, 10, 47))
    assert open_now["window_closed"] is False
    assert not [g for g in open_now["gaps"] if g["kind"] == "trailing"]
    assert open_now["status"] == "GREEN"
    # ...but once it HAS closed, the same rows are a real trailing gap.
    closed = flr.check_dms_cadence(rows, REVIEW_DATE, now=datetime(2026, 9, 2, 16, 30))
    assert closed["window_closed"] is True
    assert [g for g in closed["gaps"] if g["kind"] == "trailing"], (
        "after the window closes a switch that stopped at 10:58 MUST show a trailing gap"
    )
    assert closed["status"] == "RED"


def test_verdicts_ignore_out_of_window_dry_rehearsal_rows():
    rows = [_fire("06:10:11", arm=a, action="STALE_BUT_FLAT", dry=True)
            for a in ("safe-2", "bold-2", "safe-3", "risky-1")]
    rows += [_fire("09:32:01"), _fire("09:34:01")]
    r = flr.check_dms_verdicts(rows)
    assert r["out_of_window_rows"] == 4
    assert r["not_armed_rows"] == [], "rehearsal rows were counted as unarmed production fires"
    assert r["status"] == "GREEN"
    assert "out-of-window" in r["reason"], "exclusion must be DISCLOSED"


def test_an_IN_window_dry_row_is_still_flagged_not_armed():
    """The narrowing must not become a loophole: a DRY fire DURING the session means the
    switch genuinely was not armed, and that is the finding the check exists for."""
    r = flr.check_dms_verdicts([_fire("09:32:01", dry=True), _fire("09:34:01")])
    assert r["status"] == "YELLOW"
    assert len(r["not_armed_rows"]) == 1
    assert r["out_of_window_rows"] == 0


def test_an_unparseable_timestamp_counts_as_in_window():
    """Fail toward scrutiny. A row we cannot place in time must not be silently discarded as
    'probably a rehearsal' -- that would be a way to make findings disappear."""
    inw, out = flr._split_by_window([{"ts": "not-a-timestamp", "arm": "safe-2",
                                      "action": "READ_FAILED"}])
    assert len(inw) == 1 and len(out) == 0
    r = flr.check_dms_verdicts([{"ts": "not-a-timestamp", "arm": "safe-2",
                                 "action": "READ_FAILED"}])
    assert r["status"] == "RED", "an unreadable-broker row must still fail the check"


# ============================================================================
# check 5 (cont.): conductor entries are BULLETS in the live STATUS.md, not headings
# (found 2026-09-02 23:50 ET closing the first-live-day box: the real file carries
# "- [2026-09-02T06:27 ET] conductor: OK -- ..." while the parser only split on "## [",
# so overnight_fires_checked was 0 on a night with a conductor fire in-window and the
# check could never say anything but "cannot verify")
# ============================================================================

def test_conductor_picks_finds_bullet_form_conductor_entries():
    status_md = (
        "## [2026-09-02T16:15 ET] NOT_EXERCISED -- monday_verify\n"
        "some body\n"
        "- [2026-09-02T06:27 ET] conductor: OK -- self-audit organ fixed -- REVOKE surface\n"
        "  body of the bullet, mentions GATE-BLOCKING tier first\n"
        "- [2026-09-01T23:59+00:00] ROSTER-LIVENESS: not a conductor line\n"
    )
    queue_md = "- [ ] SOME-OPEN-ITEM (HIGH, GATE-BLOCKING, filed) :: status:open\n"
    result = flr.check_conductor_picks(status_md, queue_md, "2026-09-02")
    assert result["overnight_fires_checked"] == 1, result
    assert result["fires_missing_gate_blocking_mention"] == []
    assert "cannot verify" not in result["reason"]


def test_conductor_picks_bullet_form_missing_mention_is_named():
    status_md = (
        "- [2026-09-02T06:27 ET] conductor: OK -- did something unrelated\n"
        "  body with no mention of the tag\n"
        "- [2026-09-02T16:16 ET] conductor: OK -- after the open, must be excluded\n"
        "  GATE-BLOCKING mentioned here but outside the overnight window\n"
    )
    queue_md = "- [ ] SOME-OPEN-ITEM (HIGH, GATE-BLOCKING, filed) :: status:open\n"
    result = flr.check_conductor_picks(status_md, queue_md, "2026-09-02")
    assert result["overnight_fires_checked"] == 1, result
    assert result["fires_missing_gate_blocking_mention"] == ["2026-09-02T06:27"]


# ============================================================================
# FIRST-LIVE-DAY-REVIEW-RUN-LOG (queue.md 2026-09-02)
#
# write_outputs() writes ONE artifact per review_date, so a later ad-hoc invocation
# silently overwrites an earlier one -- happened live 2026-09-02, where a direct
# 23:37 ET run overwrote the 16:30 ET scheduled fire's own output with no record
# either run had happened. append_run_log() writes a permanent, append-only row to
# analysis/first-live-day/runs.jsonl on EVERY run instead.
# ============================================================================

def test_detect_invoker_pythonw_parent_is_task():
    assert flr.detect_invoker("pythonw.exe") == "task"


def test_detect_invoker_console_python_parent_is_direct():
    assert flr.detect_invoker("python.exe") == "direct"
    assert flr.detect_invoker("bash.exe") == "direct"
    assert flr.detect_invoker("cmd.exe") == "direct"


def test_detect_invoker_unknown_when_parent_detection_fails(monkeypatch):
    """Detection itself can fail (non-Windows, access denied, parent already gone) --
    that must read as 'unknown', never crash and never default to either real answer."""
    monkeypatch.setattr(flr, "_parent_process_image_name", lambda: None)
    assert flr.detect_invoker() == "unknown"


def test_append_run_log_second_run_appends_not_overwrites(empty_state_env):
    """THE bug in one assertion: two runs on the same date must leave TWO rows, not
    one row overwritten by the second (which is exactly what write_outputs() does to
    the per-date JSON/MD -- this file must behave differently)."""
    report1 = {"generated_at_et": "2026-09-02 16:30:00 ET", "review_date": "2026-09-02",
               "verdict": "GREEN", "failing_checks": []}
    report2 = {"generated_at_et": "2026-09-02 23:37:00 ET", "review_date": "2026-09-02",
               "verdict": "GREEN", "failing_checks": []}
    flr.append_run_log(report1, ["--date", "2026-09-02"], "task")
    flr.append_run_log(report2, ["--date", "2026-09-02"], "direct")

    runs_path = flr.OUT_DIR / "runs.jsonl"
    lines = runs_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2, f"expected 2 rows, got {len(lines)}: {lines}"
    row1, row2 = (json.loads(l) for l in lines)
    assert row1["generated_at_et"] == "2026-09-02 16:30:00 ET"
    assert row1["invoker"] == "task"
    assert row2["generated_at_et"] == "2026-09-02 23:37:00 ET"
    assert row2["invoker"] == "direct"


def test_append_run_log_row_shape(empty_state_env):
    report = {"generated_at_et": "2026-09-02 16:30:00 ET", "review_date": "2026-09-02",
              "verdict": "RED", "failing_checks": ["dms_cadence:RED"]}
    flr.append_run_log(report, ["--date", "2026-09-02"], "task")
    row = json.loads((flr.OUT_DIR / "runs.jsonl").read_text(encoding="utf-8").strip())
    assert row == {
        "generated_at_et": "2026-09-02 16:30:00 ET",
        "review_date": "2026-09-02",
        "verdict": "RED",
        "failing_checks": ["dms_cadence:RED"],
        "argv": ["--date", "2026-09-02"],
        "invoker": "task",
    }


def test_append_run_log_malformed_existing_file_does_not_crash(empty_state_env):
    """Fail-open (C7): append_run_log() only ever APPENDS, never reads/parses the
    existing file back -- a malformed prior row must not stop a new one landing."""
    flr.OUT_DIR.mkdir(parents=True, exist_ok=True)
    (flr.OUT_DIR / "runs.jsonl").write_text("{not valid json at all\n", encoding="utf-8")
    report = {"generated_at_et": "2026-09-02 16:30:00 ET", "review_date": "2026-09-02",
              "verdict": "GREEN", "failing_checks": []}
    flr.append_run_log(report, [], "task")  # must not raise

    lines = (flr.OUT_DIR / "runs.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert lines[0] == "{not valid json at all", "the malformed row was destroyed, not preserved"
    assert json.loads(lines[1])["verdict"] == "GREEN", "the new row did not land"


def test_append_run_log_write_failure_does_not_raise(empty_state_env, monkeypatch):
    """A permissions/OSError on the write itself must be swallowed (logged to stderr),
    never propagated into the caller -- the review already ran and already wrote its
    per-date JSON/MD; this log is best-effort on top of that."""
    def _boom(*a, **k):
        raise OSError("simulated disk failure")
    monkeypatch.setattr(flr.Path, "mkdir", _boom)
    report = {"generated_at_et": "2026-09-02 16:30:00 ET", "review_date": "2026-09-02",
              "verdict": "GREEN", "failing_checks": []}
    flr.append_run_log(report, [], "task")  # must not raise


def test_main_appends_a_run_log_row(empty_state_env):
    """End-to-end: a real main() invocation must leave a runs.jsonl row behind, on top
    of (never instead of) the existing per-date JSON/MD write."""
    flr.main(["--date", "2026-09-02"])
    runs_path = flr.OUT_DIR / "runs.jsonl"
    assert runs_path.exists(), "main() did not append a run-log row"
    row = json.loads(runs_path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert row["review_date"] == "2026-09-02"
    assert row["argv"] == ["--date", "2026-09-02"]
    assert row["invoker"] in ("task", "direct", "unknown")
    assert (flr.OUT_DIR / "2026-09-02.json").exists(), "write_outputs' own artifact regressed"

    # A second invocation must APPEND, not overwrite -- the whole point of this file.
    flr.main(["--date", "2026-09-02"])
    lines = runs_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2, f"main() invoked twice must leave 2 run-log rows, got {len(lines)}"

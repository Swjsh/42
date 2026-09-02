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
    result = flr.check_dms_cadence(rows, REVIEW_DATE)
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

def test_guards_full_four_failures_fresh_not_flagged():
    """Uses the REAL guard_runner_full.py write schema (counts.failed nested, no top-level
    'failed' key -- confirmed live against automation/state/guard-watch-full.json)."""
    state = {"status": "red", "at": "2026-09-01 23:20 ET",
             "counts": {"passed": 11097, "failed": 4, "skipped": 11}, "returncode": 1}
    result = flr.check_guards_full(state, REVIEW_DATE)
    assert result["status"] == "GREEN"


def test_guards_full_five_failures_is_flagged():
    state = {"status": "red", "at": "2026-09-01 23:20 ET",
             "counts": {"passed": 11096, "failed": 5, "skipped": 11}, "returncode": 1}
    result = flr.check_guards_full(state, REVIEW_DATE)
    assert result["status"] == "YELLOW"
    # This state is FRESH (dated the day before the review); the point here is that a
    # count of 5 deviates from the expected 4. Assert semantics, not the reason's prose.
    assert result["failed"] == 5 and result["expected_failed"] == 4
    assert result["failed"] != result["expected_failed"]
    assert not result["stale"], "2026-09-01 vs a 2026-09-02 review is not stale"


def test_guards_full_top_level_failed_key_still_accepted_as_fallback():
    """Forward-compat fallback: a bare top-level 'failed' (not the real current schema, but
    accepted in case the writer's shape ever changes back) is still read correctly."""
    state = {"status": "red", "at": "2026-09-01 23:20 ET", "failed": 4}
    result = flr.check_guards_full(state, REVIEW_DATE)
    assert result["status"] == "GREEN"


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
    assert report["checks"]["dms_verdicts"]["reason"] == "never fired -- 0 rows to verify"
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

    gf_path = tmp_path / "automation" / "state" / "guard-watch-full.json"
    gf_path.write_text(json.dumps({"status": "red", "at": f"{REVIEW_DATE} 23:20 ET",
                                    "counts": {"passed": 11097, "failed": 4, "skipped": 11},
                                    "returncode": 1}), encoding="utf-8")

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

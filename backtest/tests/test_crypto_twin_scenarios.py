"""Tests for setup/scripts/crypto_twin_scenarios.py -- B1b: the scenario scheduler /
path-coverage battery.

Covers: the branch registry shape (tier + expected_stage for all 9 branches, including
the 3 SIM-tier bear placeholders queued for TWIN-B1.5), path-coverage.json load/save +
UTC-day rollover, branch selection priority (incident-retry-first, least-covered,
daily-cap), the pure outcome extractor + grader (including the "ribbon_flip"/"time_stop"
always-acceptable exception), scenario-scoped config overrides (param-freeze: NEVER
mutates/persists into the caller's TwinConfig), and the full run_scenario_tick
integration (one-scenario-at-a-time, breaker/organic-position skip, GREEN grading via a
real forced lifecycle through the REAL exit_manager, INCIDENT grading + incidents.jsonl,
ORGANIC_SIGNAL passive marking, staleness timeout, and the RESTART_OPEN_POSITION branch's
"a fresh TwinConfig object still finds and manages the position" property).

Mirrors test_crypto_twin_core.py's _twin_cfg(tmp_path) isolation convention + its
_FakeBroker fixture shape (kept local, not imported, per this codebase's per-file
self-containment convention for test fixtures) so every test runs fully isolated from
the real automation/state/crypto-twin/ ledger.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", "automation/state/fleet", ""):
    sys.path.insert(0, str(REPO / _p) if _p else str(REPO))

import crypto_twin_core as ctc  # noqa: E402
import crypto_twin_scenarios as cts  # noqa: E402
import exit_manager as em  # noqa: E402


def _twin_cfg(tmp_path: Path, **overrides) -> ctc.TwinConfig:
    state_dir = tmp_path / "automation" / "state" / "crypto-twin"
    return ctc.TwinConfig(state_dir=state_dir, **overrides)


def _raw_bar(ts: datetime, o: float, h: float, l: float, c: float, v: float = 1.0) -> dict:
    return {"t": ts.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": o, "h": h, "l": l, "c": c, "v": v}


def _flat_bars(now: datetime, price: float = 64000.0, n: int = 80) -> list[dict]:
    """A quiet, ribbon-warmup-satisfying bar history around `price` -- no organic
    ENTER should fire off this alone (used whenever a test wants ONLY the forced path
    to place an entry, never an organic one racing it)."""
    return [_raw_bar(now - timedelta(minutes=5 * i), price, price + 1, price - 1, price, 1.0)
           for i in range(n, 0, -1)]


# ============================================================================
# Fake broker (local, mirrors test_crypto_twin_core.py's _FakeBroker shape)
# ============================================================================
class _FakeBroker:
    def __init__(self):
        self.orders = []
        self.sells = []
        self.closes = []
        self.position_qty = 0.0
        self.quote = None  # (ask, bid)

    def place_crypto_order(self, creds, *, symbol, side, notional=None, qty=None,
                           order_type="market", limit_price=None, live):
        self.orders.append({"symbol": symbol, "side": side, "notional": notional, "qty": qty, "live": live})
        if qty:
            self.position_qty = qty
        return {"id": f"order-{len(self.orders)}", "status": "accepted"}

    def poll_fill(self, creds, order_id, attempts=4, sleep_sec=1.5):
        return {"filled": True, "status": "filled", "filled_qty": self.position_qty,
               "filled_avg_price": self._last_entry_price, "order": {}}

    def get_crypto_position_qty(self, creds, symbol="BTC/USD"):
        return self.position_qty

    def get_crypto_quote_hilo(self, symbol="BTC/USD", creds=None):
        return self.quote

    def market_sell_crypto(self, creds, *, symbol, qty, live):
        self.sells.append({"symbol": symbol, "qty": qty, "live": live})
        return {"id": f"sell-{len(self.sells)}", "status": "accepted"}

    def close_all_crypto(self, creds, *, symbol="BTC/USD", live):
        self.closes.append({"symbol": symbol, "live": live})
        self.position_qty = 0.0
        return {"id": f"close-{len(self.closes)}", "status": "accepted"}

    _last_entry_price = 64000.0


@pytest.fixture
def fake_broker(monkeypatch):
    fb = _FakeBroker()
    monkeypatch.setattr(ctc.broker, "place_crypto_order", fb.place_crypto_order)
    monkeypatch.setattr(ctc.broker, "poll_fill", fb.poll_fill)
    monkeypatch.setattr(ctc.broker, "get_crypto_position_qty", fb.get_crypto_position_qty)
    monkeypatch.setattr(ctc.broker, "get_crypto_quote_hilo", fb.get_crypto_quote_hilo)
    monkeypatch.setattr(ctc.broker, "market_sell_crypto", fb.market_sell_crypto)
    monkeypatch.setattr(ctc.broker, "close_all_crypto", fb.close_all_crypto)
    return fb


_CREDS = {"key": "k", "secret": "s", "base_url": "https://paper-api.alpaca.markets"}


@pytest.fixture(autouse=True)
def _stub_account(monkeypatch):
    """Every scenario test needs a working creds/account path (mirrors run_tick's own
    creds try/except) -- stub it once so individual tests don't repeat this."""
    monkeypatch.setattr(ctc.broker, "get_twin_creds", lambda verify_crypto_status=True: _CREDS)
    monkeypatch.setattr(ctc.broker, "get_account", lambda creds: {"equity": 10000.0})


# ============================================================================
# Branch registry shape
# ============================================================================
def test_branch_registry_has_six_live_and_three_sim_branches():
    live = [n for n, m in cts.BRANCH_REGISTRY.items() if m["tier"] == "LIVE"]
    sim = [n for n, m in cts.BRANCH_REGISTRY.items() if m["tier"] == "SIM"]
    assert set(live) == {"ENTRY_TP1_TRAIL", "ENTRY_STRUCTURE_STOP", "ENTRY_CAT_CAP",
                         "ENTRY_MAX_HOLD", "RESTART_OPEN_POSITION", "ORGANIC_SIGNAL"}
    assert set(sim) == {"ENTRY_TP1_TRAIL_BEAR", "ENTRY_STRUCTURE_STOP_BEAR", "ENTRY_CAT_CAP_BEAR"}


def test_forced_live_branches_excludes_organic_signal_and_sim_tier():
    assert "ORGANIC_SIGNAL" not in cts.FORCED_LIVE_BRANCHES
    assert not any(b.endswith("_BEAR") for b in cts.FORCED_LIVE_BRANCHES)
    assert len(cts.FORCED_LIVE_BRANCHES) == 5


def test_every_branch_has_a_tier_and_expected_stage_key():
    for name, meta in cts.BRANCH_REGISTRY.items():
        assert meta["tier"] in ("LIVE", "SIM")
        assert "expected_stage" in meta  # may be None (ORGANIC_SIGNAL) or "ANY" -- key must exist


def test_sim_branches_are_bear_mirrors_of_live_branches_by_expected_stage():
    """Coordinator schema amendment 2026-07-11: the 3 SIM branches must mirror 3 of the
    LIVE branches' expected stages (same mechanism, opposite side) -- a cheap structural
    guard that the naming isn't arbitrary."""
    assert cts.BRANCH_REGISTRY["ENTRY_TP1_TRAIL_BEAR"]["expected_stage"] == \
        cts.BRANCH_REGISTRY["ENTRY_TP1_TRAIL"]["expected_stage"]
    assert cts.BRANCH_REGISTRY["ENTRY_STRUCTURE_STOP_BEAR"]["expected_stage"] == \
        cts.BRANCH_REGISTRY["ENTRY_STRUCTURE_STOP"]["expected_stage"]
    assert cts.BRANCH_REGISTRY["ENTRY_CAT_CAP_BEAR"]["expected_stage"] == \
        cts.BRANCH_REGISTRY["ENTRY_CAT_CAP"]["expected_stage"]


# ============================================================================
# path-coverage.json: default record / fresh doc / day-rollover
# ============================================================================
def test_default_branch_record_sim_tier_is_not_yet_covered():
    rec = cts._default_branch_record({"tier": "SIM"})
    assert rec["status"] == "NOT_YET_COVERED"
    assert rec["count_today"] == 0


def test_default_branch_record_live_tier_is_pending():
    rec = cts._default_branch_record({"tier": "LIVE"})
    assert rec["status"] == "PENDING"


def test_fresh_coverage_has_every_registry_branch():
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    doc = cts._fresh_coverage(now)
    assert doc["date_utc"] == "2026-07-11"
    assert set(doc["branches"].keys()) == set(cts.BRANCH_REGISTRY.keys())
    assert doc["branches"]["ENTRY_TP1_TRAIL_BEAR"]["status"] == "NOT_YET_COVERED"
    assert doc["branches"]["ENTRY_TP1_TRAIL_BEAR"]["tier"] == "SIM"


def test_load_coverage_missing_file_returns_fresh(tmp_path):
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    doc = cts._load_coverage(tmp_path / "nope.json", now_utc=now)
    assert doc["date_utc"] == "2026-07-11"
    assert len(doc["branches"]) == len(cts.BRANCH_REGISTRY)


def test_load_coverage_same_day_round_trips(tmp_path):
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    p = tmp_path / "path-coverage.json"
    doc = cts._load_coverage(p, now_utc=now)
    doc = cts._mark_exercise_result(doc, "ENTRY_MAX_HOLD", now, "GREEN", "GREEN")
    cts._save_coverage(p, doc)
    reloaded = cts._load_coverage(p, now_utc=now + timedelta(minutes=5))
    assert reloaded["branches"]["ENTRY_MAX_HOLD"]["status"] == "GREEN"
    assert reloaded["branches"]["ENTRY_MAX_HOLD"]["count_today"] == 1


def test_load_coverage_new_utc_day_resets_count_but_keeps_history(tmp_path):
    day1 = datetime(2026, 7, 11, 23, 0, tzinfo=timezone.utc)
    p = tmp_path / "path-coverage.json"
    doc = cts._load_coverage(p, now_utc=day1)
    doc = cts._mark_exercise_result(doc, "ENTRY_MAX_HOLD", day1, "GREEN", "GREEN")
    cts._save_coverage(p, doc)

    day2 = datetime(2026, 7, 12, 0, 5, tzinfo=timezone.utc)  # new UTC day
    reloaded = cts._load_coverage(p, now_utc=day2)
    rec = reloaded["branches"]["ENTRY_MAX_HOLD"]
    assert reloaded["date_utc"] == "2026-07-12"
    assert rec["count_today"] == 0            # reset for the new day's coverage question
    assert rec["status"] == "PENDING"          # "did it run TODAY" resets
    assert rec["last_result"] == "GREEN"       # history retained -- never erased by a day boundary
    assert rec["last_exercised_utc"] is not None


def test_mark_exercise_touch_then_result_is_in_progress_then_terminal(tmp_path):
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    doc = cts._fresh_coverage(now)
    doc = cts._mark_exercise_touch(doc, "ENTRY_CAT_CAP", now)
    assert doc["branches"]["ENTRY_CAT_CAP"]["status"] == "IN_PROGRESS"
    assert doc["branches"]["ENTRY_CAT_CAP"]["count_today"] == 0  # not yet graded
    doc = cts._mark_exercise_result(doc, "ENTRY_CAT_CAP", now + timedelta(minutes=1), "INCIDENT", "boom")
    assert doc["branches"]["ENTRY_CAT_CAP"]["status"] == "INCIDENT"
    assert doc["branches"]["ENTRY_CAT_CAP"]["last_result"] == "boom"
    assert doc["branches"]["ENTRY_CAT_CAP"]["count_today"] == 1


# ============================================================================
# Branch selection priority
# ============================================================================
def test_pick_next_branch_never_returns_organic_signal_or_sim_tier():
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    doc = cts._fresh_coverage(now)
    picked = cts._pick_next_branch(doc, today="2026-07-11")
    assert picked in cts.FORCED_LIVE_BRANCHES


def test_pick_next_branch_prioritizes_incident_over_never_covered(tmp_path):
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    doc = cts._fresh_coverage(now)
    doc = cts._mark_exercise_result(doc, "ENTRY_CAT_CAP", now, "INCIDENT", "boom")
    picked = cts._pick_next_branch(doc, today="2026-07-11")
    assert picked == "ENTRY_CAT_CAP"  # the failure gets retried before any never-covered branch


def test_pick_next_branch_skips_already_green_branches(tmp_path):
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    doc = cts._fresh_coverage(now)
    for b in cts.FORCED_LIVE_BRANCHES[:-1]:
        doc = cts._mark_exercise_result(doc, b, now, "GREEN", "GREEN")
    picked = cts._pick_next_branch(doc, today="2026-07-11")
    assert picked == cts.FORCED_LIVE_BRANCHES[-1]


def test_pick_next_branch_none_when_everything_green(tmp_path):
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    doc = cts._fresh_coverage(now)
    for b in cts.FORCED_LIVE_BRANCHES:
        doc = cts._mark_exercise_result(doc, b, now, "GREEN", "GREEN")
    assert cts._pick_next_branch(doc, today="2026-07-11") is None


def test_pick_next_branch_none_when_daily_cap_reached(tmp_path):
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    doc = cts._fresh_coverage(now)
    # 6 completed reps spread across branches (not all green -- cap is global, not per-branch)
    for i in range(cts.MAX_SCENARIO_ENTRIES_PER_DAY):
        b = cts.FORCED_LIVE_BRANCHES[i % len(cts.FORCED_LIVE_BRANCHES)]
        doc = cts._mark_exercise_result(doc, b, now, "INCIDENT", "retry me")
    assert sum(doc["branches"][b]["count_today"] for b in cts.FORCED_LIVE_BRANCHES) == \
        cts.MAX_SCENARIO_ENTRIES_PER_DAY
    assert cts._pick_next_branch(doc, today="2026-07-11") is None


# ============================================================================
# _build_scenario_cfg -- PARAM-FREEZE (vary-and-assert): never mutates/persists into
# the caller's TwinConfig or the module-level TwinConfig() default.
# ============================================================================
def test_build_scenario_cfg_never_mutates_caller_cfg(tmp_path):
    base = _twin_cfg(tmp_path)
    original_shape = dict(base.exit_shape)
    for branch in cts.FORCED_LIVE_BRANCHES:
        scenario_cfg, _offset = cts._build_scenario_cfg(branch, base)
        assert scenario_cfg is not base
        assert scenario_cfg.exit_shape is not base.exit_shape
    assert base.exit_shape == original_shape  # caller's cfg is byte-identical after every branch


def test_build_scenario_cfg_never_leaks_into_fresh_twinconfig_default():
    """The default TwinConfig().exit_shape (a field(default_factory=...) lambda) must be
    completely unaffected by any scenario override having ever been built -- proves the
    override is a plain in-memory dataclasses.replace, never a global/class-level
    mutation (the param-freeze rule, TWIN-PROGRAM.md 'Design decisions')."""
    fresh_before = ctc.TwinConfig().exit_shape
    base = ctc.TwinConfig()
    for branch in cts.FORCED_LIVE_BRANCHES:
        cts._build_scenario_cfg(branch, base)
    fresh_after = ctc.TwinConfig().exit_shape
    assert fresh_after == fresh_before
    assert fresh_after == {
        "stop_mode": "structure", "premium_stop_pct": -0.03, "tp1_premium_pct": 0.015,
        "tp1_qty_fraction": 0.667, "profit_lock_mode": "trailing", "trail_pct": 0.01,
        "profit_lock_arm_pct": 0.005, "runner_target_pct": 0.03,
    }


def test_build_scenario_cfg_max_hold_overrides_max_hold_hours_only_for_that_branch(tmp_path):
    base = _twin_cfg(tmp_path)
    scenario_cfg, _offset = cts._build_scenario_cfg("ENTRY_MAX_HOLD", base)
    assert scenario_cfg.max_hold_hours == pytest.approx(20.0 / 60.0)
    assert base.max_hold_hours == 6.0  # untouched


def test_build_scenario_cfg_structure_stop_returns_a_positive_offset(tmp_path):
    base = _twin_cfg(tmp_path)
    scenario_cfg, offset = cts._build_scenario_cfg("ENTRY_STRUCTURE_STOP", base)
    assert offset is not None and offset > 0
    assert scenario_cfg.exit_shape["stop_mode"] == "structure"


def test_build_scenario_cfg_unknown_branch_raises():
    with pytest.raises(ValueError):
        cts._build_scenario_cfg("NOT_A_REAL_BRANCH", ctc.TwinConfig())


# ============================================================================
# _extract_terminal_stage -- pure outcome extraction from a manage_positions() result
# ============================================================================
def test_extract_terminal_stage_max_hold_flatten():
    exit_pass = [{"symbol": "BTC/USD", "action": "MAX_HOLD_FLATTEN"}]
    closed, stage = cts._extract_terminal_stage(exit_pass, "BTC/USD")
    assert closed is True and stage == "MAX_HOLD_FLATTEN"


def test_extract_terminal_stage_flat_pruned_is_unexpected():
    exit_pass = [{"symbol": "BTC/USD", "action": "FLAT_PRUNED"}]
    closed, stage = cts._extract_terminal_stage(exit_pass, "BTC/USD")
    assert closed is True and stage == "FLAT_PRUNED_UNEXPECTED"


def test_extract_terminal_stage_sell_all_stage():
    exit_pass = [{"symbol": "BTC/USD", "actions": [{"kind": "SELL_ALL", "stage": "trail"}]}]
    closed, stage = cts._extract_terminal_stage(exit_pass, "BTC/USD")
    assert closed is True and stage == "trail"


def test_extract_terminal_stage_no_exit_is_not_closed():
    exit_pass = [{"symbol": "BTC/USD", "actions": []}]
    closed, stage = cts._extract_terminal_stage(exit_pass, "BTC/USD")
    assert closed is False and stage is None


def test_extract_terminal_stage_no_matching_symbol():
    exit_pass = [{"symbol": "ETH/USD", "actions": [{"kind": "SELL_ALL", "stage": "trail"}]}]
    closed, stage = cts._extract_terminal_stage(exit_pass, "BTC/USD")
    assert closed is False and stage is None


# ============================================================================
# _grade -- the GREEN/INCIDENT verdict, incl. the always-acceptable exception
# ============================================================================
def test_grade_expected_stage_match_is_green():
    verdict, detail = cts._grade("ENTRY_CAT_CAP", "premium_stop")
    assert verdict == "GREEN"


def test_grade_wrong_stage_is_incident():
    verdict, detail = cts._grade("ENTRY_CAT_CAP", "trail")
    assert verdict == "INCIDENT"
    assert "ENTRY_CAT_CAP" in detail and "trail" in detail


@pytest.mark.parametrize("branch", ["ENTRY_TP1_TRAIL", "ENTRY_STRUCTURE_STOP", "ENTRY_CAT_CAP",
                                    "ENTRY_MAX_HOLD", "RESTART_OPEN_POSITION"])
@pytest.mark.parametrize("stage", ["ribbon_flip", "time_stop"])
def test_grade_ribbon_flip_and_time_stop_always_green(branch, stage):
    """A genuinely-live, independent exit condition preempting the designed stage is
    NOT a mechanism bug -- see module docstring's GRADING section."""
    verdict, detail = cts._grade(branch, stage)
    assert verdict == "GREEN"
    assert "not a mechanism bug" in detail


def test_grade_restart_any_accepts_any_recognized_stage():
    verdict, _ = cts._grade("RESTART_OPEN_POSITION", "premium_stop")
    assert verdict == "GREEN"


def test_grade_restart_any_rejects_flat_pruned():
    verdict, detail = cts._grade("RESTART_OPEN_POSITION", "FLAT_PRUNED_UNEXPECTED")
    assert verdict == "INCIDENT"
    assert "vanished" in detail


# ============================================================================
# run_scenario_tick -- full integration (real exit_manager, mocked broker)
# ============================================================================
def _paths(cfg: ctc.TwinConfig) -> dict:
    return {"coverage_path": cfg.state_dir / "path-coverage.json",
           "scenario_state_path": cfg.state_dir / "scenario-state.json"}


def test_run_scenario_tick_forces_a_branch_on_a_fresh_account(tmp_path, fake_broker):
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    result = cts.run_scenario_tick(cfg, live=True, now_utc=now, raw_bars=_flat_bars(now), **_paths(cfg))
    assert result["bookkeeping_error"] is None
    assert result["scheduler_decision"]["forced_branch"] in cts.FORCED_LIVE_BRANCHES
    assert result["row"]["action"] == "ENTERED"
    assert result["row"]["scenario"] == result["scheduler_decision"]["forced_branch"]
    scenario_state = json.loads((cfg.state_dir / "scenario-state.json").read_text())
    assert scenario_state["active_branch"] == result["scheduler_decision"]["forced_branch"]


# --- force_branch (MANUAL/VERIFICATION ONLY -- mirrors run_tick's force_entry) ----------
def test_run_scenario_tick_force_branch_overrides_selection(tmp_path, fake_broker):
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    result = cts.run_scenario_tick(cfg, live=True, now_utc=now, raw_bars=_flat_bars(now),
                                   force_branch="ENTRY_MAX_HOLD", **_paths(cfg))
    assert result["scheduler_decision"]["forced_branch"] == "ENTRY_MAX_HOLD"
    assert result["row"]["scenario"] == "ENTRY_MAX_HOLD"


def test_run_scenario_tick_force_branch_still_respects_one_at_a_time(tmp_path, fake_broker):
    """force_branch overrides WHICH branch gets picked, never WHETHER forcing is safe --
    an already-in-flight scenario still blocks it."""
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    r1 = cts.run_scenario_tick(cfg, live=True, now_utc=now, raw_bars=_flat_bars(now),
                               force_branch="ENTRY_TP1_TRAIL", **_paths(cfg))
    assert r1["scheduler_decision"]["forced_branch"] == "ENTRY_TP1_TRAIL"

    fake_broker.quote = (64100.0, 64050.0)
    now2 = now + timedelta(minutes=5)
    r2 = cts.run_scenario_tick(cfg, live=True, now_utc=now2, raw_bars=_flat_bars(now2),
                               force_branch="ENTRY_MAX_HOLD", **_paths(cfg))
    assert r2["scheduler_decision"]["forced_branch"] is None
    assert "already in flight" in r2["scheduler_decision"]["reason_no_force"]
    assert len(fake_broker.orders) == 1  # the second force_branch request never placed


def test_run_scenario_tick_one_at_a_time_no_second_force_while_active(tmp_path, fake_broker):
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    r1 = cts.run_scenario_tick(cfg, live=True, now_utc=now, raw_bars=_flat_bars(now), **_paths(cfg))
    first_branch = r1["scheduler_decision"]["forced_branch"]
    assert first_branch is not None

    # tick 2: quote inert, position still open -- must NOT force a second branch
    fake_broker.quote = (64100.0, 64050.0)
    now2 = now + timedelta(minutes=5)
    r2 = cts.run_scenario_tick(cfg, live=True, now_utc=now2, raw_bars=_flat_bars(now2), **_paths(cfg))
    assert r2["scheduler_decision"]["forced_branch"] is None
    assert "already in flight" in r2["scheduler_decision"]["reason_no_force"]
    assert len(fake_broker.orders) == 1  # no second entry placed


def test_run_scenario_tick_skips_when_organic_position_already_open(tmp_path, fake_broker):
    cfg = _twin_cfg(tmp_path)
    fake_broker.position_qty = ctc.entry_qty_btc(cfg)
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    # an ORGANIC position (no scenario tag) is already open
    ctc.place_entry(cfg, creds=_CREDS, side="bull", price=64000.0, trigger_level=None, live=True,
                    now_utc=now)
    fake_broker.quote = (64100.0, 64050.0)
    result = cts.run_scenario_tick(cfg, live=True, now_utc=now + timedelta(minutes=5),
                                   raw_bars=_flat_bars(now), **_paths(cfg))
    assert result["scheduler_decision"]["forced_branch"] is None
    assert "already open" in result["scheduler_decision"]["reason_no_force"]
    assert len(fake_broker.orders) == 1  # only the organic entry -- scheduler placed nothing


def test_run_scenario_tick_skips_when_breaker_tripped(tmp_path, fake_broker):
    cfg = _twin_cfg(tmp_path, starting_equity=2000.0, daily_loss_kill_switch_pct=0.30)
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    state = ctc.load_breaker(cfg, now_utc=now, current_equity=2000.0)
    state = ctc.ks_tick(state, 1300.0)  # -35% -- trips
    ctc.save_breaker(cfg, state, now_utc=now, current_equity=1300.0)
    result = cts.run_scenario_tick(cfg, live=True, now_utc=now, raw_bars=_flat_bars(now), **_paths(cfg))
    assert result["scheduler_decision"]["forced_branch"] is None
    assert "breaker tripped" in result["scheduler_decision"]["reason_no_force"]
    assert not fake_broker.orders


def test_run_scenario_tick_respects_daily_cap(tmp_path, fake_broker):
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    coverage_path, scenario_state_path = cfg.state_dir / "path-coverage.json", cfg.state_dir / "scenario-state.json"
    doc = cts._fresh_coverage(now)
    for i in range(cts.MAX_SCENARIO_ENTRIES_PER_DAY):
        b = cts.FORCED_LIVE_BRANCHES[i % len(cts.FORCED_LIVE_BRANCHES)]
        doc = cts._mark_exercise_result(doc, b, now, "INCIDENT", "retry me")
    cts._save_coverage(coverage_path, doc)
    result = cts.run_scenario_tick(cfg, live=True, now_utc=now, raw_bars=_flat_bars(now),
                                   coverage_path=coverage_path, scenario_state_path=scenario_state_path)
    assert result["scheduler_decision"]["forced_branch"] is None
    assert "cap" in result["scheduler_decision"]["reason_no_force"]
    assert not fake_broker.orders


def test_run_scenario_tick_max_hold_reaches_expected_stage_green(tmp_path, fake_broker, monkeypatch):
    """Force ENTRY_MAX_HOLD deterministically (monkeypatch _pick_next_branch so the
    fixed 20-minute override is exercised without depending on selection order), drive
    it past 20 minutes, and confirm the branch grades GREEN via the real
    manage_positions/exit_manager MAX_HOLD_FLATTEN path."""
    monkeypatch.setattr(cts, "_pick_next_branch", lambda coverage, *, today: "ENTRY_MAX_HOLD")
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    paths = _paths(cfg)
    r1 = cts.run_scenario_tick(cfg, live=True, now_utc=now, raw_bars=_flat_bars(now), **paths)
    assert r1["scheduler_decision"]["forced_branch"] == "ENTRY_MAX_HOLD"
    assert r1["row"]["action"] == "ENTERED"

    fake_broker.quote = (64010.0, 64000.0)  # inert -- must not tp1/premium-stop before max_hold
    now2 = now + timedelta(minutes=21)  # past the 20-min override
    r2 = cts.run_scenario_tick(cfg, live=True, now_utc=now2, raw_bars=_flat_bars(now2), **paths)
    assert r2["row"]["exit_pass"][0]["action"] == "MAX_HOLD_FLATTEN"

    coverage = json.loads((cfg.state_dir / "path-coverage.json").read_text())
    rec = coverage["branches"]["ENTRY_MAX_HOLD"]
    assert rec["status"] == "GREEN"
    assert rec["last_result"] == "GREEN"
    assert rec["count_today"] == 1
    scenario_state = json.loads((cfg.state_dir / "scenario-state.json").read_text())
    assert scenario_state == {}  # slot released
    incidents_path = cfg.state_dir / "incidents.jsonl"
    assert not incidents_path.exists()  # a clean GREEN never writes an incident


def test_run_scenario_tick_cat_cap_reaches_expected_stage_green(tmp_path, fake_broker, monkeypatch):
    monkeypatch.setattr(cts, "_pick_next_branch", lambda coverage, *, today: "ENTRY_CAT_CAP")
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    paths = _paths(cfg)
    r1 = cts.run_scenario_tick(cfg, live=True, now_utc=now, raw_bars=_flat_bars(now), **paths)
    assert r1["scheduler_decision"]["forced_branch"] == "ENTRY_CAT_CAP"
    entry_price = ctc._load_positions(cfg)["BTC/USD"]["exit_state"]["entry_premium"]

    # premium_stop_pct override is -0.0025 -- push worst just past that
    fake_broker.quote = (entry_price * 0.999, entry_price * 0.997)
    now2 = now + timedelta(minutes=5)
    r2 = cts.run_scenario_tick(cfg, live=True, now_utc=now2, raw_bars=_flat_bars(now2), **paths)
    assert r2["row"]["exit_pass"][0]["actions"][0]["stage"] == "premium_stop"

    coverage = json.loads((cfg.state_dir / "path-coverage.json").read_text())
    assert coverage["branches"]["ENTRY_CAT_CAP"]["status"] == "GREEN"


def test_run_scenario_tick_wrong_stage_is_incident_and_logged(tmp_path, fake_broker, monkeypatch):
    """Force ENTRY_CAT_CAP (expects premium_stop) but drive the SAME position to close
    via MAX_HOLD instead (simulated by widening now_utc past the DEFAULT 6h max_hold --
    ENTRY_CAT_CAP's own override never touches max_hold_hours) -- this is a genuine
    mismatch (not one of the always-acceptable stages), so it MUST grade INCIDENT and
    append a full-context row to incidents.jsonl (the ROI ledger)."""
    monkeypatch.setattr(cts, "_pick_next_branch", lambda coverage, *, today: "ENTRY_CAT_CAP")
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    paths = _paths(cfg)
    r1 = cts.run_scenario_tick(cfg, live=True, now_utc=now, raw_bars=_flat_bars(now), **paths)
    assert r1["scheduler_decision"]["forced_branch"] == "ENTRY_CAT_CAP"

    fake_broker.quote = (64010.0, 64000.0)  # inert -- never crosses the -0.25% cap
    now2 = now + timedelta(hours=6, minutes=1)  # past the DEFAULT 6h max_hold_hours
    r2 = cts.run_scenario_tick(cfg, live=True, now_utc=now2, raw_bars=_flat_bars(now2), **paths)
    assert r2["row"]["exit_pass"][0]["action"] == "MAX_HOLD_FLATTEN"

    coverage = json.loads((cfg.state_dir / "path-coverage.json").read_text())
    rec = coverage["branches"]["ENTRY_CAT_CAP"]
    assert rec["status"] == "INCIDENT"
    assert "expected stage 'premium_stop'" in rec["last_result"]

    incidents_path = cfg.state_dir / "incidents.jsonl"
    assert incidents_path.exists()
    rows = [json.loads(l) for l in incidents_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["branch"] == "ENTRY_CAT_CAP"
    assert "MAX_HOLD_FLATTEN" in rows[0]["detail"]
    # the tick's OWN top-level action legitimately reads "HOLD" here (the position was
    # already closed+pruned by manage_positions before run_tick's entry-scoring section
    # runs, and this tick's organic verdict is HOLD -- see run_tick's action-derivation)
    # -- the real mechanism is in the nested exit_pass, which the incident carries in full.
    assert rows[0]["exit_pass"][0]["action"] == "MAX_HOLD_FLATTEN"


def test_run_scenario_tick_stale_scenario_becomes_incident(tmp_path, fake_broker, monkeypatch):
    monkeypatch.setattr(cts, "_pick_next_branch", lambda coverage, *, today: "ENTRY_TP1_TRAIL")
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    paths = _paths(cfg)
    cts.run_scenario_tick(cfg, live=True, now_utc=now, raw_bars=_flat_bars(now), **paths)

    # position never closes (broker keeps reporting it open, quote perfectly inert) --
    # jump past SCENARIO_STALE_HOURS entirely via the scheduler's own staleness guard.
    fake_broker.quote = (64000.5, 64000.4)
    later = now + timedelta(hours=cts.SCENARIO_STALE_HOURS + 0.5)
    result = cts.run_scenario_tick(cfg, live=True, now_utc=later, raw_bars=_flat_bars(later), **paths)
    coverage = json.loads((cfg.state_dir / "path-coverage.json").read_text())
    rec = coverage["branches"]["ENTRY_TP1_TRAIL"]
    assert rec["status"] == "INCIDENT"
    assert "timed out" in rec["last_result"]
    scenario_state = json.loads((cfg.state_dir / "scenario-state.json").read_text())
    assert scenario_state == {}  # slot released even on a timeout


def test_run_scenario_tick_organic_signal_marked_green_passively(tmp_path, fake_broker, monkeypatch):
    """An UNFORCED tick whose own organic ribbon+level verdict enters for real must
    mark ORGANIC_SIGNAL GREEN -- simulated here by monkeypatching sig.evaluate (the
    scoring stage crypto_twin_core.run_tick calls when NOT forced) to hand back a
    ready-made ENTER_BULL verdict, since crafting real bars that organically trigger
    the ribbon+level scorer is exactly the kind of brittle-fixture problem this
    scheduler exists to avoid depending on."""
    import crypto_twin_signal as sig
    forced_verdict = sig.TwinVerdict("ENTER_BULL", "bull", "TEST_ORGANIC", triggers=["test"],
                                     reason="test organic entry", trigger_level_exact=63500.0,
                                     ribbon_stack="BULL", ribbon_spread=1.0, stack_bars=3)
    monkeypatch.setattr(sig, "evaluate", lambda bars, levels: forced_verdict)
    # force the scheduler to decide NOT to force anything (daily cap already hit) so this
    # tick runs organically and the patched verdict is free to enter.
    monkeypatch.setattr(cts, "_pick_next_branch", lambda coverage, *, today: None)

    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    result = cts.run_scenario_tick(cfg, live=True, now_utc=now, raw_bars=_flat_bars(now), **_paths(cfg))
    assert result["scheduler_decision"]["forced_branch"] is None
    assert result["row"]["action"] == "ENTERED"
    assert result["row"]["scenario"] is None  # organic -- no scenario tag on the position

    coverage = json.loads((cfg.state_dir / "path-coverage.json").read_text())
    rec = coverage["branches"]["ORGANIC_SIGNAL"]
    assert rec["status"] == "GREEN"
    assert rec["count_today"] == 1


def test_run_scenario_tick_restart_open_position_fresh_config_still_manages_it(tmp_path, fake_broker, monkeypatch):
    """RESTART_OPEN_POSITION's actual mechanism-under-test: place an entry with cfg #1,
    then manage it via a BRAND NEW TwinConfig object (cfg #2 -- same state_dir, but not
    the same Python object, simulating 'a fresh process reloaded state from disk') and
    confirm it is still correctly found + closed. Every real 5-min tick already IS a
    fresh process (crypto_twin_health.py's own module docstring), so this test makes
    that property explicit and deterministic rather than incidental."""
    monkeypatch.setattr(cts, "_pick_next_branch", lambda coverage, *, today: "RESTART_OPEN_POSITION")
    cfg1 = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    paths = _paths(cfg1)
    r1 = cts.run_scenario_tick(cfg1, live=True, now_utc=now, raw_bars=_flat_bars(now), **paths)
    assert r1["scheduler_decision"]["forced_branch"] == "RESTART_OPEN_POSITION"
    entry_price = ctc._load_positions(cfg1)["BTC/USD"]["exit_state"]["entry_premium"]

    cfg2 = _twin_cfg(tmp_path)  # a DIFFERENT TwinConfig instance, same on-disk state_dir
    assert cfg2 is not cfg1
    fake_broker.quote = (entry_price * 0.999, entry_price * 0.997)  # crosses the -0.25% cap
    now2 = now + timedelta(minutes=5)
    r2 = cts.run_scenario_tick(cfg2, live=True, now_utc=now2, raw_bars=_flat_bars(now2), **paths)
    assert r2["row"]["exit_pass"][0]["actions"][0]["kind"] == "SELL_ALL"

    coverage = json.loads((cfg1.state_dir / "path-coverage.json").read_text())
    assert coverage["branches"]["RESTART_OPEN_POSITION"]["status"] == "GREEN"
    assert "BTC/USD" not in ctc._load_positions(cfg2)  # correctly closed via the fresh config


def test_run_scenario_tick_bookkeeping_error_does_not_break_the_row(tmp_path, fake_broker, monkeypatch):
    """A corrupted path-coverage.json must degrade the bookkeeping step only -- the
    tick's own row (already logged by the inner run_tick call) must still come back
    intact, never masked by a bookkeeping failure."""
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    coverage_path = cfg.state_dir / "path-coverage.json"
    coverage_path.parent.mkdir(parents=True, exist_ok=True)

    def _boom(path, coverage):
        raise RuntimeError("simulated coverage write failure")
    monkeypatch.setattr(cts, "_save_coverage", _boom)

    result = cts.run_scenario_tick(cfg, live=True, now_utc=now, raw_bars=_flat_bars(now),
                                   coverage_path=coverage_path,
                                   scenario_state_path=cfg.state_dir / "scenario-state.json")
    assert result["bookkeeping_error"] is not None
    assert "simulated coverage write failure" in result["bookkeeping_error"]
    assert result["row"] is not None
    assert result["row"]["action"] in ("ENTERED", "HOLD")  # the tick itself still completed


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

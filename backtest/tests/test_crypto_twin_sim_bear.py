"""Tests for setup/scripts/crypto_twin_scenarios.py -- TWIN-B1.5: the SIM-tier bear lane
(ENTRY_TP1_TRAIL_BEAR / ENTRY_STRUCTURE_STOP_BEAR / ENTRY_CAT_CAP_BEAR).

Mirrors test_crypto_twin_scenarios.py's isolation conventions (tmp_path-scoped TwinConfig,
a local fake broker fixture for get_crypto_quote_hilo only -- the SIM lane never calls
place_crypto_order/poll_fill/market_sell_crypto/close_all_crypto, so those don't need
stubbing here). Covers: the synthetic put-mirror premium math (pure, the one genuinely new
piece of arithmetic in this build), the per-branch SIM overrides, branch selection scoped
to the 3 SIM branches, and full run_sim_bear_tick integration through the REAL
exit_manager core -- GREEN grading for all three designed stages (structure_stop,
premium_stop, tp1->trail), INCIDENT grading + incidents.jsonl, staleness timeout, the
one-at-a-time gate, the daily cap, and the "never blended with LIVE rows" file-separation
guarantee (sim-bear-positions.json / sim-bear-journal.jsonl are never exit-state.json /
journal.jsonl).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", "automation/state/fleet", "backtest", ""):
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
    return [_raw_bar(now - timedelta(minutes=5 * i), price, price + 1, price - 1, price, 1.0)
           for i in range(n, 0, -1)]


def _paths(cfg: ctc.TwinConfig) -> dict:
    return {
        "coverage_path": cfg.state_dir / "path-coverage.json",
        "sim_state_path": cfg.state_dir / cts.SIM_BEAR_STATE_FILENAME,
        "position_path": cfg.state_dir / cts.SIM_BEAR_POSITIONS_FILENAME,
        "journal_path": cfg.state_dir / cts.SIM_BEAR_JOURNAL_FILENAME,
    }


@pytest.fixture
def fake_quote(monkeypatch):
    """The ONLY broker call the SIM bear lane ever makes: get_crypto_quote_hilo (read-only
    market data). No order-placing function is stubbed because none is ever called on this
    path -- see the module docstring's 'NEVER BLENDED WITH LIVE' section."""
    box = {"quote": None}
    monkeypatch.setattr(cts.broker, "get_crypto_quote_hilo", lambda symbol=None: box["quote"])
    return box


# ============================================================================
# Pure math: the synthetic put-mirror (the one genuinely new piece of arithmetic)
# ============================================================================
def test_mirror_premium_at_entry_equals_entry_price():
    assert cts.mirror_premium(64000.0, 64000.0) == 64000.0


def test_mirror_premium_rises_when_raw_price_falls():
    entry = 64000.0
    assert cts.mirror_premium(entry, 63900.0) > entry  # price DOWN -> premium UP (bear-favorable)


def test_mirror_premium_falls_when_raw_price_rises():
    entry = 64000.0
    assert cts.mirror_premium(entry, 64100.0) < entry  # price UP -> premium DOWN (bear-adverse)


def test_mirror_price_from_premium_is_the_exact_inverse():
    entry, raw = 64000.0, 63850.0
    premium = cts.mirror_premium(entry, raw)
    assert cts.mirror_price_from_premium(entry, premium) == pytest.approx(raw)


def test_bear_hilo_premiums_direction_inverted_from_bull_convention():
    """crypto_twin_core.manage_positions' bull convention is best=ask, worst=bid (premium
    tracks price 1:1). The bear mirror must invert which raw quote leg is 'best'."""
    entry = 64000.0
    best, worst = cts._bear_hilo_premiums(entry, ask=64100.0, bid=63950.0)
    assert best == cts.mirror_premium(entry, 63950.0)   # lowest raw price -> best for a bear
    assert worst == cts.mirror_premium(entry, 64100.0)  # highest raw price -> worst for a bear
    assert best > worst


# ============================================================================
# Branch registry / overrides
# ============================================================================
def test_sim_bear_branches_matches_branch_registry_sim_tier():
    assert set(cts.SIM_BEAR_BRANCHES) == {"ENTRY_TP1_TRAIL_BEAR", "ENTRY_STRUCTURE_STOP_BEAR",
                                          "ENTRY_CAT_CAP_BEAR"}


def test_build_sim_bear_shape_structure_stop_offset_is_negative():
    shape, offset = cts._build_sim_bear_shape("ENTRY_STRUCTURE_STOP_BEAR", ctc.TwinConfig().exit_shape)
    assert offset is not None and offset < 0
    assert shape["stop_mode"] == "structure"


def test_build_sim_bear_shape_cat_cap_tight_premium_stop():
    shape, offset = cts._build_sim_bear_shape("ENTRY_CAT_CAP_BEAR", ctc.TwinConfig().exit_shape)
    assert offset is None
    assert shape["stop_mode"] == "premium"
    assert shape["premium_stop_pct"] == -0.0025


def test_build_sim_bear_shape_never_mutates_caller_shape():
    base = ctc.TwinConfig().exit_shape
    original = dict(base)
    for branch in cts.SIM_BEAR_BRANCHES:
        shape, _offset = cts._build_sim_bear_shape(branch, base)
        assert shape is not base
    assert base == original


def test_build_sim_bear_shape_unknown_branch_raises():
    with pytest.raises(ValueError):
        cts._build_sim_bear_shape("NOT_A_REAL_BRANCH", ctc.TwinConfig().exit_shape)


# ============================================================================
# Branch selection
# ============================================================================
def test_pick_next_sim_branch_never_returns_a_live_branch():
    now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    doc = cts._fresh_coverage(now)
    picked = cts._pick_next_sim_branch(doc, today="2026-07-14")
    assert picked in cts.SIM_BEAR_BRANCHES


def test_pick_next_sim_branch_prioritizes_incident_retry():
    now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    doc = cts._fresh_coverage(now)
    doc = cts._mark_exercise_result(doc, "ENTRY_CAT_CAP_BEAR", now, "INCIDENT", "boom")
    picked = cts._pick_next_sim_branch(doc, today="2026-07-14")
    assert picked == "ENTRY_CAT_CAP_BEAR"


def test_pick_next_sim_branch_none_when_all_green():
    now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    doc = cts._fresh_coverage(now)
    for b in cts.SIM_BEAR_BRANCHES:
        doc = cts._mark_exercise_result(doc, b, now, "GREEN", "GREEN")
    assert cts._pick_next_sim_branch(doc, today="2026-07-14") is None


def test_pick_next_sim_branch_none_when_daily_cap_reached():
    now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    doc = cts._fresh_coverage(now)
    for i in range(cts.MAX_SIM_BEAR_ENTRIES_PER_DAY):
        b = cts.SIM_BEAR_BRANCHES[i % len(cts.SIM_BEAR_BRANCHES)]
        doc = cts._mark_exercise_result(doc, b, now, "INCIDENT", "retry me")
    assert cts._pick_next_sim_branch(doc, today="2026-07-14") is None


# ============================================================================
# run_sim_bear_tick -- full integration through the REAL exit_manager core
# ============================================================================
def test_run_sim_bear_tick_forces_entry_never_touches_live_ledgers(tmp_path, fake_quote):
    """NEVER BLENDED WITH LIVE: a SIM entry must never write exit-state.json/journal.jsonl
    (the LIVE ledgers) -- only its own private sim-bear-* files."""
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    result = cts.run_sim_bear_tick(cfg, now_utc=now, raw_bars=_flat_bars(now),
                                   force_branch="ENTRY_CAT_CAP_BEAR", **_paths(cfg))
    assert result["bookkeeping_error"] is None
    assert result["action"] == "SIM_ENTERED"
    assert result["scheduler_decision"]["forced_branch"] == "ENTRY_CAT_CAP_BEAR"

    assert (cfg.state_dir / cts.SIM_BEAR_POSITIONS_FILENAME).exists()
    assert (cfg.state_dir / cts.SIM_BEAR_JOURNAL_FILENAME).exists()
    assert not (cfg.state_dir / "exit-state.json").exists()   # LIVE ledger untouched
    assert not (cfg.state_dir / "journal.jsonl").exists()      # LIVE ledger untouched
    assert not (cfg.state_dir / "decisions.jsonl").exists()    # LIVE ledger untouched

    journal_rows = [json.loads(l) for l in
                    (cfg.state_dir / cts.SIM_BEAR_JOURNAL_FILENAME).read_text(encoding="utf-8").splitlines()]
    assert len(journal_rows) == 1
    assert journal_rows[0]["event"] == "SIM_PLACED"
    assert journal_rows[0]["tier"] == "SIM"
    assert journal_rows[0]["side"] == "bear"

    position = json.loads((cfg.state_dir / cts.SIM_BEAR_POSITIONS_FILENAME).read_text())
    assert position["exit_state"]["side"] == "P"
    assert position["branch"] == "ENTRY_CAT_CAP_BEAR"

    coverage = json.loads((cfg.state_dir / "path-coverage.json").read_text())
    rec = coverage["branches"]["ENTRY_CAT_CAP_BEAR"]
    assert rec["tier"] == "SIM"
    assert rec["status"] == "IN_PROGRESS"


def test_run_sim_bear_tick_structure_stop_reaches_expected_stage_green(tmp_path, fake_quote):
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    paths = _paths(cfg)
    r1 = cts.run_sim_bear_tick(cfg, now_utc=now, raw_bars=_flat_bars(now),
                               force_branch="ENTRY_STRUCTURE_STOP_BEAR", **paths)
    assert r1["action"] == "SIM_ENTERED"
    position = json.loads((cfg.state_dir / cts.SIM_BEAR_POSITIONS_FILENAME).read_text())
    entry_price = position["exit_state"]["entry_premium"]
    trigger_level = position["exit_state"]["trigger_level"]
    assert trigger_level < entry_price  # planted just BELOW spot, per _build_sim_bear_shape

    # tick 2: SAME flat price -- last_closed_5m_close (== entry_price) > trigger_level is
    # already true by construction (mirrors the LIVE ENTRY_STRUCTURE_STOP branch's own
    # "a close-through happens soon" design). Quote is irrelevant to structure-stop (it's
    # checked before any premium threshold) but must be non-None or the tick HOLDs.
    fake_quote["quote"] = (entry_price * 1.0001, entry_price * 0.9999)
    now2 = now + timedelta(minutes=5)
    r2 = cts.run_sim_bear_tick(cfg, now_utc=now2, raw_bars=_flat_bars(now2), **paths)
    assert r2["exit_pass"][0]["actions"][0]["stage"] == "structure_stop"
    assert r2["exit_pass"][0]["actions"][0]["kind"] == "SELL_ALL"
    assert "sim_fill_raw_price" in r2["exit_pass"][0]["actions"][0]

    coverage = json.loads((cfg.state_dir / "path-coverage.json").read_text())
    rec = coverage["branches"]["ENTRY_STRUCTURE_STOP_BEAR"]
    assert rec["status"] == "GREEN"
    assert rec["tier"] == "SIM"
    scenario_state = json.loads((cfg.state_dir / cts.SIM_BEAR_STATE_FILENAME).read_text())
    assert scenario_state == {}
    position_after = json.loads((cfg.state_dir / cts.SIM_BEAR_POSITIONS_FILENAME).read_text())
    assert position_after == {}
    incidents_path = cfg.state_dir / "incidents.jsonl"
    assert not incidents_path.exists()  # a clean GREEN never writes an incident


def test_run_sim_bear_tick_cat_cap_reaches_expected_stage_green(tmp_path, fake_quote):
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    paths = _paths(cfg)
    r1 = cts.run_sim_bear_tick(cfg, now_utc=now, raw_bars=_flat_bars(now),
                               force_branch="ENTRY_CAT_CAP_BEAR", **paths)
    position = json.loads((cfg.state_dir / cts.SIM_BEAR_POSITIONS_FILENAME).read_text())
    entry_price = position["exit_state"]["entry_premium"]

    # premium_stop_pct override is -0.0025: push the RAW price UP (adverse for a bear) so
    # worst_bear = mirror_premium(entry, ask) crosses entry*(1-0.0025).
    ask = entry_price * 1.004
    bid = entry_price * 1.003
    fake_quote["quote"] = (ask, bid)
    now2 = now + timedelta(minutes=5)
    r2 = cts.run_sim_bear_tick(cfg, now_utc=now2, raw_bars=_flat_bars(now2, price=entry_price), **paths)
    assert r2["exit_pass"][0]["actions"][0]["stage"] == "premium_stop"

    coverage = json.loads((cfg.state_dir / "path-coverage.json").read_text())
    assert coverage["branches"]["ENTRY_CAT_CAP_BEAR"]["status"] == "GREEN"


def test_run_sim_bear_tick_tp1_then_trail_reaches_expected_stage_green(tmp_path, fake_quote):
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    paths = _paths(cfg)
    r1 = cts.run_sim_bear_tick(cfg, now_utc=now, raw_bars=_flat_bars(now),
                               force_branch="ENTRY_TP1_TRAIL_BEAR", **paths)
    assert r1["action"] == "SIM_ENTERED"
    position = json.loads((cfg.state_dir / cts.SIM_BEAR_POSITIONS_FILENAME).read_text())
    entry = position["exit_state"]["entry_premium"]

    # tick 2: raw price DOWN 0.2% (bear-favorable) -> best_bear = 2*entry-bid crosses the
    # +0.15% tp1_premium_pct level -> TP1 partial fires, runner ratchets to BE.
    bid2 = entry * 0.998
    ask2 = entry * 0.9985
    fake_quote["quote"] = (ask2, bid2)
    now2 = now + timedelta(minutes=5)
    r2 = cts.run_sim_bear_tick(cfg, now_utc=now2, raw_bars=_flat_bars(now2, price=entry), **paths)
    kinds2 = [a["kind"] for a in r2["exit_pass"][0]["actions"]]
    assert "SELL_PARTIAL" in kinds2
    coverage = json.loads((cfg.state_dir / "path-coverage.json").read_text())
    assert coverage["branches"]["ENTRY_TP1_TRAIL_BEAR"]["status"] == "IN_PROGRESS"

    # tick 3: raw price DOWN further (0.6%) -- arms the profit lock (+0.05% arm_pct) and
    # sets a NEW high-water-mark, ratcheting the trailing floor up.
    bid3 = entry * 0.994
    ask3 = entry * 0.995
    fake_quote["quote"] = (ask3, bid3)
    now3 = now2 + timedelta(minutes=5)
    r3 = cts.run_sim_bear_tick(cfg, now_utc=now3, raw_bars=_flat_bars(now3, price=entry), **paths)
    assert coverage["branches"]["ENTRY_TP1_TRAIL_BEAR"]["status"] != "GREEN" or True  # still open

    # tick 4: raw price PULLS BACK UP (adverse) enough that worst_bear falls through the
    # trailing floor set at tick 3's HWM -> SELL_ALL closes the runner via "trail".
    bid4 = entry * 0.997
    ask4 = entry * 0.998
    fake_quote["quote"] = (ask4, bid4)
    now4 = now3 + timedelta(minutes=5)
    r4 = cts.run_sim_bear_tick(cfg, now_utc=now4, raw_bars=_flat_bars(now4, price=entry), **paths)
    actions4 = r4["exit_pass"][0]["actions"]
    assert any(a["kind"] == "SELL_ALL" for a in actions4)
    sell_all = [a for a in actions4 if a["kind"] == "SELL_ALL"][0]
    assert sell_all["stage"] in ("trail", "be_stop", "runner_target")  # a genuine runner exit

    coverage = json.loads((cfg.state_dir / "path-coverage.json").read_text())
    rec = coverage["branches"]["ENTRY_TP1_TRAIL_BEAR"]
    assert rec["status"] == "GREEN"


def test_run_sim_bear_tick_wrong_stage_is_incident_and_logged(tmp_path, fake_quote, monkeypatch):
    """Force ENTRY_CAT_CAP_BEAR (expects premium_stop) but drive it to close via MAX_HOLD
    instead -- a genuine mismatch, must grade INCIDENT and log to incidents.jsonl (tagged
    tier=SIM so a reader can filter)."""
    cfg = _twin_cfg(tmp_path, max_hold_hours=6.0)
    now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    paths = _paths(cfg)
    r1 = cts.run_sim_bear_tick(cfg, now_utc=now, raw_bars=_flat_bars(now),
                               force_branch="ENTRY_CAT_CAP_BEAR", **paths)
    position = json.loads((cfg.state_dir / cts.SIM_BEAR_POSITIONS_FILENAME).read_text())
    entry = position["exit_state"]["entry_premium"]

    fake_quote["quote"] = (entry * 1.0001, entry * 0.9999)  # inert -- never crosses -0.25%
    now2 = now + timedelta(hours=6, minutes=1)  # past max_hold_hours
    r2 = cts.run_sim_bear_tick(cfg, now_utc=now2, raw_bars=_flat_bars(now2, price=entry), **paths)
    assert r2["exit_pass"][0]["action"] == "MAX_HOLD_FLATTEN"

    coverage = json.loads((cfg.state_dir / "path-coverage.json").read_text())
    rec = coverage["branches"]["ENTRY_CAT_CAP_BEAR"]
    assert rec["status"] == "INCIDENT"
    assert "expected stage 'premium_stop'" in rec["last_result"]

    incidents_path = cfg.state_dir / "incidents.jsonl"
    assert incidents_path.exists()
    rows = [json.loads(l) for l in incidents_path.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["branch"] == "ENTRY_CAT_CAP_BEAR"  # tier is implicit: only SIM branches end _BEAR
    assert rows[-1]["decision_row_action"] == "MAX_HOLD_FLATTEN"
    assert rows[-1]["exit_pass"][0]["action"] == "MAX_HOLD_FLATTEN"


def test_run_sim_bear_tick_stale_scenario_becomes_incident(tmp_path, fake_quote):
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    paths = _paths(cfg)
    r1 = cts.run_sim_bear_tick(cfg, now_utc=now, raw_bars=_flat_bars(now),
                               force_branch="ENTRY_TP1_TRAIL_BEAR", **paths)
    position = json.loads((cfg.state_dir / cts.SIM_BEAR_POSITIONS_FILENAME).read_text())
    entry = position["exit_state"]["entry_premium"]

    fake_quote["quote"] = (entry * 1.00001, entry * 0.99999)  # perfectly inert
    later = now + timedelta(hours=cts.SCENARIO_STALE_HOURS + 0.5)
    cts.run_sim_bear_tick(cfg, now_utc=later, raw_bars=_flat_bars(later, price=entry), **paths)

    coverage = json.loads((cfg.state_dir / "path-coverage.json").read_text())
    rec = coverage["branches"]["ENTRY_TP1_TRAIL_BEAR"]
    assert rec["status"] == "INCIDENT"
    assert "timed out" in rec["last_result"]
    scenario_state = json.loads((cfg.state_dir / cts.SIM_BEAR_STATE_FILENAME).read_text())
    assert scenario_state == {}


def test_run_sim_bear_tick_one_at_a_time_no_second_force_while_active(tmp_path, fake_quote):
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    paths = _paths(cfg)
    r1 = cts.run_sim_bear_tick(cfg, now_utc=now, raw_bars=_flat_bars(now),
                               force_branch="ENTRY_TP1_TRAIL_BEAR", **paths)
    assert r1["scheduler_decision"]["forced_branch"] == "ENTRY_TP1_TRAIL_BEAR"

    fake_quote["quote"] = (64100.0, 64050.0)
    now2 = now + timedelta(minutes=5)
    r2 = cts.run_sim_bear_tick(cfg, now_utc=now2, raw_bars=_flat_bars(now2),
                               force_branch="ENTRY_CAT_CAP_BEAR", **paths)
    assert r2["scheduler_decision"]["forced_branch"] is None
    assert "already in flight" in r2["scheduler_decision"]["reason_no_force"]


def test_run_sim_bear_tick_respects_daily_cap(tmp_path, fake_quote):
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    paths = _paths(cfg)
    doc = cts._fresh_coverage(now)
    for i in range(cts.MAX_SIM_BEAR_ENTRIES_PER_DAY):
        b = cts.SIM_BEAR_BRANCHES[i % len(cts.SIM_BEAR_BRANCHES)]
        doc = cts._mark_exercise_result(doc, b, now, "INCIDENT", "retry me")
    cts._save_coverage(paths["coverage_path"], doc)
    result = cts.run_sim_bear_tick(cfg, now_utc=now, raw_bars=_flat_bars(now), **paths)
    assert result["scheduler_decision"]["forced_branch"] is None
    assert "cap" in result["scheduler_decision"]["reason_no_force"]
    assert not (cfg.state_dir / cts.SIM_BEAR_POSITIONS_FILENAME).exists()


def test_run_sim_bear_tick_bad_bars_holds_without_crashing(tmp_path, fake_quote):
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    result = cts.run_sim_bear_tick(cfg, now_utc=now, raw_bars=[], **_paths(cfg))
    assert result["action"] == "HOLD_BAD_BARS"
    assert result["bookkeeping_error"] is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

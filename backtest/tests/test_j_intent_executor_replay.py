"""ACCEPTANCE GATE + guard tests for j_intent_executor (automation/overnight/
queue.md ## J-INTENT-EXECUTOR).

MANDATORY ACCEPTANCE GATE (before ANY live arm of this daemon): replay J's
REAL 2026-07-15 752P trade from REAL recorded 5m SPY bars (backtest/tests/
fixtures/spy_5m_2026-07-15_j_intent_752p.csv -- 78 bars, the full RTH session,
fetched from Alpaca's IEX data feed and verified byte-for-byte against
journal/2026-07-15.md's stated OHLC for both the trigger bar and the exit
bar). The replay MUST:
  (a) trigger on the bar that CLOSES 13:15 ET (o=752.09 h=752.255 l=751.78
      c=751.785 -- started 13:10, per Alpaca's bar-start convention; see
      j_intent_logic.py's BAR-CLOSE CONVENTION docstring section)
  (b) NOT trigger on any earlier bar
  (c) exit-signal chart-stop on the bar that CLOSES 13:20 ET (c=752.405)

Plus the unit tests the queue item names explicitly: stale-bar immunity (the
exact bug today's hand-written watcher hit), the invalidation path,
timeout/expiry, kill-switch-tripped refusal (risk_gate), and double-entry
refusal when the broker is not flat -- plus the "default state = no-op"
guard (an empty/all-terminal intents store must place NOTHING).

Run:
  backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_j_intent_executor_replay.py -v
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
_SCRIPTS = ROOT / "setup" / "scripts"
for _p in (str(_SCRIPTS), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import j_intent_logic as jl  # noqa: E402
import j_intent_executor as je  # noqa: E402
import exit_manager as em  # noqa: E402

FIXTURE_CSV = HERE / "fixtures" / "spy_5m_2026-07-15_j_intent_752p.csv"

# J's REAL 2026-07-15 intent, as pre-registered in journal/2026-07-15.md's
# 12:55 ET PRE-TRADE THESIS. armed at 12:56 ET (Claude writes the intent
# within J's <60s target of the 12:55 thesis).
REAL_INTENT: dict = {
    "id": "j-intent-20260715-125600-put",
    "created_et": "2026-07-15T12:56:00",
    "account": "safe",
    "side": "P",
    "trigger": {
        "type": "level_reject_confirmed_close",
        "tag_level": 752.00,
        "confirm_close_below": 751.94,
        "require_red_bar": True,
    },
    "invalidation": {"close_above": 752.45},
    "expiry_et": "15:00:00",
    "sizing": {"qty": 3},
    "exits": {
        "tp1_pct": 0.30,
        "tp1_fraction": 0.8,
        "chart_stop": {"close_above": 752.26},
        "catastrophe_pct": -0.50,
        "chandelier": {"arm_pct": 0.05, "trail_pct": 0.15},
        "runner_target_mult": 2.5,
        "time_stop_et": "15:40:00",
    },
    "status": "armed",
}

FULL_PARAMS = {
    "per_trade_risk_cap_pct": 0.30,
    "daily_loss_kill_switch_pct": 0.30,
    "min_contracts": 3,
    "pdt_gate_mode": "cash_settlement",
    "max_same_day_roundtrips": 5,
}


def _base_ctx(**overrides) -> dict:
    ctx = {
        "ok": True,
        "equity": 1746.75,
        "sod_equity": 1746.75,
        "broker_flat": True,
        "kill_switch_tripped": False,
        "settled_cash_available": 1746.75,
        "same_day_entries_used": 0,
        "day_trades_used_5d": 1,
        "ledger_path": HERE / "_unused_ledger.json",
        "today_et": "2026-07-15",
    }
    ctx.update(overrides)
    return ctx


# ============================================================ ACCEPTANCE GATE
class TestAcceptanceGate20260715:
    def test_fixture_matches_journal_exactly(self):
        """Sanity: the committed fixture's two load-bearing bars byte-match
        journal/2026-07-15.md's stated OHLC before trusting any assertion
        built on top of them."""
        bars = jl.load_bars_csv(FIXTURE_CSV)
        trigger_bar = next(b for b in bars if b.start_et == datetime(2026, 7, 15, 13, 10, 0))
        exit_bar = next(b for b in bars if b.start_et == datetime(2026, 7, 15, 13, 15, 0))
        assert (trigger_bar.open, trigger_bar.high, trigger_bar.low, trigger_bar.close) == (
            752.09, 752.255, 751.78, 751.785)
        assert exit_bar.close == 752.405
        assert trigger_bar.close_et == datetime(2026, 7, 15, 13, 15, 0)
        assert exit_bar.close_et == datetime(2026, 7, 15, 13, 20, 0)

    def test_replay_triggers_exits_exactly_as_specified(self):
        bars = jl.load_bars_csv(FIXTURE_CSV)
        armed_at = jl.parse_et(REAL_INTENT["created_et"])
        result = jl.replay_intent_over_bars(
            REAL_INTENT, bars, armed_at,
            structure_stop_hit_fn=em._structure_stop_hit,  # THE live exit_manager primitive -- zero drift
        )
        # (a) triggers on the bar that closes 13:15 ET
        assert result.triggered_at == datetime(2026, 7, 15, 13, 15, 0)
        # (b) NOT triggered on any earlier bar
        early_hits = [t for t in result.trace if t.trigger_hit and t.bar_close_et < result.triggered_at]
        assert early_hits == [], f"unexpected early trigger(s): {early_hits}"
        # (c) exit-signal chart-stop on the bar that closes 13:20 ET
        assert result.exit_signal_at == datetime(2026, 7, 15, 13, 20, 0)
        assert result.status == jl.STATUS_EXITED

    def test_stale_bars_before_arming_were_never_evaluated(self):
        """Every bar closing at/before 12:56 ET (armed_at) -- i.e. all of the
        morning session -- must be marked stale in the trace, proving the
        ARMED_AT guard actually ran across the real pre-arm data, not just an
        empty window."""
        bars = jl.load_bars_csv(FIXTURE_CSV)
        armed_at = jl.parse_et(REAL_INTENT["created_et"])
        result = jl.replay_intent_over_bars(REAL_INTENT, bars, armed_at,
                                            structure_stop_hit_fn=em._structure_stop_hit)
        pre_arm_bars = [b for b in bars if b.close_et <= armed_at]
        assert len(pre_arm_bars) >= 20, "fixture should cover a full morning session"
        stale_closes = {t.bar_close_et for t in result.trace if t.stale}
        for b in pre_arm_bars:
            assert b.close_et in stale_closes, f"bar closing {b.close_et} should have been marked stale"


# ============================================================ stale-bar guard
def test_stale_bar_immunity_synthetic():
    """The EXACT bug class the queue names: a bar that CLOSED before arming
    must never fire a trigger, even when its own OHLC would otherwise match
    the trigger condition perfectly. Proven two ways: (1) the bar DOES match
    evaluate_trigger in isolation (so the test is meaningful, not vacuous),
    (2) replay_intent_over_bars still never triggers on it."""
    armed_at = datetime(2026, 7, 15, 12, 56, 0)
    stale_bar = jl.Bar(start_et=datetime(2026, 7, 15, 12, 46, 0),  # closes 12:51, BEFORE armed_at
                       open=752.20, high=752.30, low=751.80, close=751.85)
    fresh_nonfiring_bar = jl.Bar(start_et=datetime(2026, 7, 15, 13, 10, 0),
                                 open=752.00, high=752.05, low=751.98, close=752.02)

    assert jl.evaluate_trigger(REAL_INTENT["trigger"], stale_bar) is True, \
        "fixture bug: the stale bar must itself match the trigger pattern for this test to prove anything"
    assert jl.is_bar_stale(stale_bar.close_et, armed_at) is True

    result = jl.replay_intent_over_bars(REAL_INTENT, [stale_bar, fresh_nonfiring_bar], armed_at)
    assert result.triggered_at is None
    assert result.trace[0].stale is True
    assert result.trace[0].trigger_hit is False


def test_bar_closing_exactly_at_armed_at_is_stale():
    """Boundary: a bar closing in the SAME instant as arming counts as
    pre-existing knowledge (strict <=), not fresh evidence."""
    armed_at = datetime(2026, 7, 15, 12, 56, 0)
    assert jl.is_bar_stale(datetime(2026, 7, 15, 12, 56, 0), armed_at) is True
    assert jl.is_bar_stale(datetime(2026, 7, 15, 12, 56, 1), armed_at) is False


# ============================================================ invalidation
def test_invalidation_path_stands_down_before_any_trigger():
    armed_at = datetime(2026, 7, 15, 12, 56, 0)
    reclaim_bar = jl.Bar(start_et=datetime(2026, 7, 15, 13, 0, 0),  # closes 13:05
                         open=752.10, high=752.60, low=752.05, close=752.50)  # > 752.45 invalidation
    would_be_trigger_bar = jl.Bar(start_et=datetime(2026, 7, 15, 13, 10, 0),
                                  open=752.09, high=752.26, low=751.78, close=751.79)
    result = jl.replay_intent_over_bars(REAL_INTENT, [reclaim_bar, would_be_trigger_bar], armed_at)
    assert result.status == jl.STATUS_INVALIDATED
    assert result.invalidated_at == datetime(2026, 7, 15, 13, 5, 0)
    assert result.triggered_at is None, "invalidation is terminal -- must never also trigger on a later bar"


# ============================================================ expiry
def test_expiry_with_no_signal_ever():
    armed_at = datetime(2026, 7, 15, 12, 56, 0)
    expiry_et = jl.combine_today(armed_at, REAL_INTENT["expiry_et"])  # 15:00:00
    quiet_bar = jl.Bar(start_et=datetime(2026, 7, 15, 13, 0, 0),
                       open=752.00, high=752.02, low=751.98, close=752.00)
    past_expiry_bar = jl.Bar(start_et=datetime(2026, 7, 15, 15, 0, 0),  # closes 15:05, past 15:00 expiry
                             open=752.00, high=752.02, low=751.98, close=752.00)
    result = jl.replay_intent_over_bars(REAL_INTENT, [quiet_bar, past_expiry_bar], armed_at,
                                        expiry_et=expiry_et)
    assert result.status == jl.STATUS_EXPIRED
    assert result.triggered_at is None
    assert result.invalidated_at is None


# ============================================================ risk_gate wiring
def test_kill_switch_tripped_refuses_entry():
    ctx = _base_ctx(kill_switch_tripped=True)
    decision = je.decide_entry(REAL_INTENT, ctx=ctx, symbol="SPY260715P00752000",
                               mid=0.80, params=FULL_PARAMS)
    assert decision["allow"] is False
    assert decision["code"] == "KILL_SWITCH"


def test_kill_switch_tripped_never_places_an_order(monkeypatch):
    """Integration-level proof: when risk_gate denies, the order-placement
    function is NEVER called -- not just that decide_entry returns deny."""
    monkeypatch.setattr(je, "gather_entry_context", lambda account, creds: _base_ctx(kill_switch_tripped=True))
    monkeypatch.setattr(je.fb, "get_option_mid", lambda creds, symbol: 0.80)
    monkeypatch.setattr(je, "resolve_symbol", lambda intent, spy, eq: "SPY260715P00752000")

    def _boom(*a, **k):
        raise AssertionError("place_entry must never be called when risk_gate denies")
    monkeypatch.setattr(je, "place_entry", _boom)
    monkeypatch.setattr(je, "load_params", lambda account: FULL_PARAMS)

    bar = jl.Bar(start_et=datetime(2026, 7, 15, 13, 10, 0), open=752.09, high=752.255,
                low=751.78, close=751.785)
    data = {"intents": [REAL_INTENT]}
    new_data = je._execute_trigger(data, REAL_INTENT, bar=bar,
                                   now_et=datetime(2026, 7, 15, 13, 16, 0),
                                   creds={"key": "x", "secret": "y", "base_url": "z"},
                                   params=FULL_PARAMS)
    updated = next(i for i in new_data["intents"] if i["id"] == REAL_INTENT["id"])
    assert updated["status"] == jl.STATUS_INVALIDATED
    assert updated["_risk_gate_deny_code"] == "KILL_SWITCH"


# ============================================================ double-entry (C11)
def test_broker_not_flat_refuses_entry():
    ctx = _base_ctx(broker_flat=False)
    decision = je.decide_entry(REAL_INTENT, ctx=ctx, symbol="SPY260715P00752000",
                               mid=0.80, params=FULL_PARAMS)
    assert decision["allow"] is False
    assert decision["code"] == "NOT_FLAT"


def test_broker_not_flat_never_places_a_second_order(monkeypatch):
    monkeypatch.setattr(je, "gather_entry_context", lambda account, creds: _base_ctx(broker_flat=False))
    monkeypatch.setattr(je.fb, "get_option_mid", lambda creds, symbol: 0.80)
    monkeypatch.setattr(je, "resolve_symbol", lambda intent, spy, eq: "SPY260715P00752000")

    def _boom(*a, **k):
        raise AssertionError("place_entry must never be called on a double-entry attempt")
    monkeypatch.setattr(je, "place_entry", _boom)
    monkeypatch.setattr(je, "load_params", lambda account: FULL_PARAMS)

    bar = jl.Bar(start_et=datetime(2026, 7, 15, 13, 10, 0), open=752.09, high=752.255,
                low=751.78, close=751.785)
    data = {"intents": [REAL_INTENT]}
    new_data = je._execute_trigger(data, REAL_INTENT, bar=bar,
                                   now_et=datetime(2026, 7, 15, 13, 16, 0),
                                   creds={"key": "x", "secret": "y", "base_url": "z"},
                                   params=FULL_PARAMS)
    updated = next(i for i in new_data["intents"] if i["id"] == REAL_INTENT["id"])
    assert updated["status"] == jl.STATUS_INVALIDATED
    assert updated["_risk_gate_deny_code"] == "NOT_FLAT"


# ============================================================ default no-op
def test_default_empty_intents_is_pure_noop(tmp_path, monkeypatch):
    """The core safety contract: with an empty j-intents.json, poll_once must
    touch NO broker/network primitive whatsoever."""
    path = tmp_path / "j-intents.json"
    path.write_text(json.dumps({"intents": []}), encoding="utf-8")

    def _boom(*a, **k):
        raise AssertionError("no broker/network call should happen with an empty intents store")
    monkeypatch.setattr(je.fb, "get_account", _boom)
    monkeypatch.setattr(je.fb, "is_flat_spy_options", _boom)
    monkeypatch.setattr(je, "load_creds", _boom)
    monkeypatch.setattr(je, "fetch_latest_completed_bars", _boom)

    data = je.poll_once(now_et=datetime(2026, 7, 15, 13, 0, 0), path=path)
    assert data == {"intents": []}


def test_all_terminal_intents_is_also_a_noop(tmp_path, monkeypatch):
    """A store containing only RESOLVED intents (exited/invalidated/expired)
    must be equally inert -- terminal status is a hard stop, not a re-arm."""
    resolved = [
        {**REAL_INTENT, "id": "a", "status": jl.STATUS_EXITED},
        {**REAL_INTENT, "id": "b", "status": jl.STATUS_INVALIDATED},
        {**REAL_INTENT, "id": "c", "status": jl.STATUS_EXPIRED},
    ]
    path = tmp_path / "j-intents.json"
    path.write_text(json.dumps({"intents": resolved}), encoding="utf-8")

    def _boom(*a, **k):
        raise AssertionError("no broker/network call should happen with only terminal intents")
    monkeypatch.setattr(je.fb, "get_account", _boom)
    monkeypatch.setattr(je, "load_creds", _boom)
    monkeypatch.setattr(je, "fetch_latest_completed_bars", _boom)

    data = je.poll_once(now_et=datetime(2026, 7, 15, 13, 0, 0), path=path)
    statuses = {it["id"]: it["status"] for it in data["intents"]}
    assert statuses == {"a": jl.STATUS_EXITED, "b": jl.STATUS_INVALIDATED, "c": jl.STATUS_EXPIRED}


def test_armed_intent_with_no_signal_yet_places_nothing(monkeypatch):
    """The common per-tick case: an armed intent whose latest bar neither
    triggers nor invalidates must place zero orders and stay armed."""
    quiet_bar = jl.Bar(start_et=datetime(2026, 7, 15, 13, 0, 0),
                       open=752.00, high=752.02, low=751.98, close=752.00)
    monkeypatch.setattr(je, "load_creds", lambda account: {"key": "x", "secret": "y", "base_url": "z"})
    monkeypatch.setattr(je, "load_params", lambda account: FULL_PARAMS)
    monkeypatch.setattr(je, "fetch_latest_completed_bars", lambda creds, **k: [quiet_bar])

    def _boom(*a, **k):
        raise AssertionError("no entry-context/placement call should happen without a trigger")
    monkeypatch.setattr(je, "gather_entry_context", _boom)
    monkeypatch.setattr(je, "place_entry", _boom)

    data = {"intents": [dict(REAL_INTENT)]}
    new_data = je.process_armed_intent(data, REAL_INTENT, now_et=datetime(2026, 7, 15, 13, 1, 0))
    updated = next(i for i in new_data["intents"] if i["id"] == REAL_INTENT["id"])
    assert updated["status"] == jl.STATUS_ARMED


# ============================================================ schema validation
def test_validate_intent_accepts_the_real_intent():
    assert jl.validate_intent(REAL_INTENT) is None


@pytest.mark.parametrize("bad_patch,expect_substr", [
    ({"account": "risky"}, "account"),
    ({"side": "X"}, "side"),
    ({"trigger": {"type": "not_a_real_type"}}, "trigger.type"),
    ({"status": "made_up"}, "status"),
])
def test_validate_intent_rejects_malformed(bad_patch, expect_substr):
    bad = {**REAL_INTENT, **bad_patch}
    err = jl.validate_intent(bad)
    assert err is not None
    assert expect_substr in err



# ============================================================ concurrency guard
def test_daemon_lock_refuses_a_second_concurrent_instance(tmp_path, monkeypatch):
    """Two --daemon instances racing on the SAME j-intents.json is a real
    double-order risk (C11/Rule-4) -- acquire_daemon_lock must refuse a
    second instance while a fresh lock is held."""
    lock = tmp_path / "j-intent-executor.lock"
    monkeypatch.setattr(je, "LOCK_PATH", lock)
    now1 = datetime(2026, 7, 15, 13, 0, 0)
    assert je.acquire_daemon_lock(now1) is True
    assert lock.exists()
    # a second instance 5s later must be refused -- the lock is fresh
    now2 = datetime(2026, 7, 15, 13, 0, 5)
    assert je.acquire_daemon_lock(now2) is False


def test_daemon_lock_reclaims_a_stale_lock(tmp_path, monkeypatch):
    """A lock left behind by a crashed/finished process (untouched for
    LOCK_STALE_SEC) must be safely reclaimable -- a permanently-stuck lock
    would silently disable the whole executor forever."""
    lock = tmp_path / "j-intent-executor.lock"
    monkeypatch.setattr(je, "LOCK_PATH", lock)
    now1 = datetime(2026, 7, 15, 13, 0, 0)
    assert je.acquire_daemon_lock(now1) is True
    # simulate staleness by backdating the file's mtime well past LOCK_STALE_SEC
    stale_ts = now1.timestamp() - (je.LOCK_STALE_SEC + 30)
    os.utime(lock, (stale_ts, stale_ts))
    now2 = now1  # "now" for the second acquirer -- the lock is what's stale, not the clock
    assert je.acquire_daemon_lock(now2) is True


def test_daemon_lock_release_frees_it_for_the_next_instance(tmp_path, monkeypatch):
    lock = tmp_path / "j-intent-executor.lock"
    monkeypatch.setattr(je, "LOCK_PATH", lock)
    now1 = datetime(2026, 7, 15, 13, 0, 0)
    assert je.acquire_daemon_lock(now1) is True
    je.release_daemon_lock()
    assert not lock.exists()
    assert je.acquire_daemon_lock(now1) is True


def test_malformed_intent_is_invalidated_not_silently_skipped(tmp_path, monkeypatch):
    """poll_once must never just skip a structurally-broken intent -- it gets
    marked INVALIDATED (with the reason recorded) so a schema mistake is
    visible in the store, not silently inert forever."""
    bad = {**REAL_INTENT, "side": "X"}
    path = tmp_path / "j-intents.json"
    path.write_text(json.dumps({"intents": [bad]}), encoding="utf-8")

    def _boom(*a, **k):
        raise AssertionError("a malformed intent must never reach entry-context gathering")
    monkeypatch.setattr(je, "load_creds", _boom)
    monkeypatch.setattr(je, "gather_entry_context", _boom)
    monkeypatch.setattr(je, "fetch_latest_completed_bars", _boom)

    data = je.poll_once(now_et=datetime(2026, 7, 15, 13, 1, 0), path=path)
    updated = next(i for i in data["intents"] if i["id"] == bad["id"])
    assert updated["status"] == jl.STATUS_INVALIDATED
    assert "side" in updated["_validation_error"]

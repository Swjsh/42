"""Guard for preopen_readiness -- the pre-open readiness verifier.

Locks the foot-gun that motivated it: the readiness audit MUST verify the LIVE
engine (Gamma_HeartbeatCore) + the never-blind eye (Gamma_SightBeacon), and MUST
NOT treat the retired LLM heartbeat (Gamma_Heartbeat, retired 2026-06-25) as the
live heartbeat. Bite-tested non-vacuous.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "setup" / "scripts" / "preopen_readiness.py"
_spec = importlib.util.spec_from_file_location("preopen_readiness", _SCRIPT)
por = importlib.util.module_from_spec(_spec)
sys.modules["preopen_readiness"] = por  # needed for @dataclass(frozen=True) resolution
_spec.loader.exec_module(por)  # type: ignore


# ---- the load-bearing anti-staleness ratchet ----

def test_live_chain_references_heartbeat_core_not_retired():
    names = [s["name"] for s in por.LIVE_CHAIN]
    assert "Gamma_HeartbeatCore" in names, "must verify the LIVE engine"
    assert "Gamma_SightBeacon" in names, "must verify the never-blind eye"
    # The retired LLM heartbeats must NOT be in the live chain (they are not the engine).
    assert "Gamma_Heartbeat" not in names
    assert "Gamma_Heartbeat_Aggressive" not in names
    assert por.RETIRED_HEARTBEATS == ("Gamma_Heartbeat", "Gamma_Heartbeat_Aggressive")


def test_engine_and_flatten_are_critical():
    crit = {s["name"] for s in por.LIVE_CHAIN if s["critical"]}
    assert {"Gamma_HeartbeatCore", "Gamma_SightBeacon",
            "Gamma_EodFlatten", "Gamma_EodFlatten_Aggressive"} <= crit


# ---- assess_task_chain ----

def _all_ready():
    return {s["name"]: {"state": "Ready", "last_result": 0} for s in por.LIVE_CHAIN}


def test_full_ready_chain_is_green():
    checks = por.assess_task_chain(_all_ready())
    assert all(c.status == "GREEN" for c in checks)
    assert por.fuse(checks) == "GREEN"


def test_missing_heartbeat_core_reds_the_verdict():
    states = _all_ready()
    del states["Gamma_HeartbeatCore"]  # bite: the engine isn't registered
    checks = por.assess_task_chain(states)
    hb = next(c for c in checks if c.name == "Gamma_HeartbeatCore")
    assert hb.status == "RED" and hb.critical
    assert por.fuse(checks) == "RED"


def test_missing_noncritical_task_is_yellow_not_red():
    states = _all_ready()
    del states["Gamma_TvWatchdog"]  # non-critical
    checks = por.assess_task_chain(states)
    assert por.fuse(checks) == "YELLOW"


def test_disabled_task_is_yellow():
    states = _all_ready()
    states["Gamma_HeartbeatCore"] = {"state": "Disabled", "last_result": 0}
    checks = por.assess_task_chain(states)
    hb = next(c for c in checks if c.name == "Gamma_HeartbeatCore")
    assert hb.status == "YELLOW"


# ---- assess_broker ----

def _good_acct(alias="safe"):
    return {alias: {"status": "ACTIVE", "trading_blocked": False, "account_blocked": False,
                    "options_trading_level": 3, "daytrade_count": 0,
                    "pattern_day_trader": False, "equity": "1762.69"}}


def test_healthy_account_is_green():
    checks = por.assess_broker(_good_acct())
    assert all(c.status == "GREEN" for c in checks)


def test_blocked_account_is_red():
    acct = _good_acct()
    acct["safe"]["account_blocked"] = True
    checks = por.assess_broker(acct)
    assert checks[0].status == "RED" and checks[0].critical


def test_low_options_level_is_red():
    acct = _good_acct()
    acct["safe"]["options_trading_level"] = 1  # cannot buy long options
    checks = por.assess_broker(acct)
    assert checks[0].status == "RED"


def test_pdt_no_headroom_is_yellow_not_red():
    acct = _good_acct()
    acct["safe"].update({"pattern_day_trader": True, "daytrade_count": 3, "equity": "1762"})
    checks = por.assess_broker(acct)
    assert checks[0].status == "YELLOW" and not checks[0].critical


def test_auth_failure_is_red():
    checks = por.assess_broker({"safe": {"_error": "401 unauthorized"}})
    assert checks[0].status == "RED" and checks[0].critical


def test_no_snapshots_is_red():
    checks = por.assess_broker({})
    assert checks[0].status == "RED"


# ---- fuse + build_report ----

def test_fuse_priority():
    assert por.fuse([por.Check("a", "GREEN", "", True)]) == "GREEN"
    assert por.fuse([por.Check("a", "YELLOW", "", False)]) == "YELLOW"
    assert por.fuse([por.Check("a", "RED", "", False)]) == "YELLOW"  # non-critical red
    assert por.fuse([por.Check("a", "RED", "", True)]) == "RED"      # critical red


def test_build_report_shape_green():
    rep = por.build_report("2026-06-29 05:48:00", _all_ready(), _good_acct())
    assert rep["verdict"] == "GREEN"
    assert rep["reds"] == []
    assert rep["checked_at_et"] == "2026-06-29 05:48:00"
    assert len(rep["checks"]) == len(por.LIVE_CHAIN) + 1


def test_build_report_reds_listed():
    states = _all_ready()
    del states["Gamma_HeartbeatCore"]
    rep = por.build_report("t", states, _good_acct())
    assert rep["verdict"] == "RED"
    assert "Gamma_HeartbeatCore" in rep["reds"]


def test_fetchers_fail_open(monkeypatch):
    # A scheduler/broker failure must degrade to {}, never raise (rail-2 fail-open).
    monkeypatch.setattr(por.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    assert por.fetch_task_states() == {}


# ---- transition-only J-ping (the WIRE-PREOPEN-READINESS-SCHEDULE addition) ----

def _red_report():
    """A report carrying one critical RED check (a transition source)."""
    states = _all_ready()
    del states["Gamma_HeartbeatCore"]
    return por.build_report("t", states, _good_acct())


def test_build_report_has_red_checks_key():
    # red_checks is the idempotency key the alerter reads -- it must always exist.
    rep = por.build_report("t", _all_ready(), _good_acct())
    assert rep["red_checks"] == []
    rep2 = _red_report()
    assert "Gamma_HeartbeatCore" in rep2["red_checks"]


def test_alert_fires_on_new_red(tmp_path, monkeypatch):
    outbox = tmp_path / "discord-outbox.jsonl"
    monkeypatch.setattr(por, "OUTBOX", outbox)
    rep = _red_report()
    assert por.maybe_alert(rep, prior_reds=set(), queued_at_utc="2026-06-29T12:25:00Z") is True
    lines = outbox.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    import json as _j
    row = _j.loads(lines[0])
    assert "Gamma_HeartbeatCore" in row["content"]
    assert row["content"].startswith(por.J_MENTION)
    assert row["queued_at"] == "2026-06-29T12:25:00Z"


def test_alert_idempotent_on_same_red(tmp_path, monkeypatch):
    # Same red carried over from the prior run -> NO re-ping (alert-fatigue guard).
    outbox = tmp_path / "discord-outbox.jsonl"
    monkeypatch.setattr(por, "OUTBOX", outbox)
    rep = _red_report()
    assert por.maybe_alert(rep, prior_reds={"Gamma_HeartbeatCore"}, queued_at_utc="t") is False
    assert not outbox.exists()


def test_alert_silent_on_green(tmp_path, monkeypatch):
    outbox = tmp_path / "discord-outbox.jsonl"
    monkeypatch.setattr(por, "OUTBOX", outbox)
    rep = por.build_report("t", _all_ready(), _good_acct())
    assert por.maybe_alert(rep, prior_reds=set(), queued_at_utc="t") is False
    assert not outbox.exists()


def test_alert_bite_neutering_prior_reds_would_double_ping(tmp_path, monkeypatch):
    # Non-vacuous: prove the idempotency key actually bites. With the SAME prior reds
    # the alert is suppressed; flip prior to empty and the identical report DOES ping.
    outbox = tmp_path / "discord-outbox.jsonl"
    monkeypatch.setattr(por, "OUTBOX", outbox)
    rep = _red_report()
    assert por.maybe_alert(rep, prior_reds={"Gamma_HeartbeatCore"}, queued_at_utc="t") is False
    assert por.maybe_alert(rep, prior_reds=set(), queued_at_utc="t") is True


def test_alert_fail_open_on_outbox_error(monkeypatch):
    # An un-writable outbox must NOT raise (rail-2): notify-only can never crash the verifier.
    def _boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(por.Path, "open", _boom)
    rep = _red_report()
    assert por.maybe_alert(rep, prior_reds=set(), queued_at_utc="t") is False


def test_prior_reds_fail_open_on_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(por, "OUT_PATH", tmp_path / "does-not-exist.json")
    assert por._prior_reds() == set()

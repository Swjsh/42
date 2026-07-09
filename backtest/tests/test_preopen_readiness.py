"""Guard for preopen_readiness -- the pre-open readiness verifier.

Locks the foot-gun that motivated it: the readiness audit MUST verify the LIVE
engine (Gamma_HeartbeatCore) + the never-blind eye (Gamma_SightBeacon), and MUST
NOT treat the retired LLM heartbeat (Gamma_Heartbeat, retired 2026-06-25) as the
live heartbeat. Bite-tested non-vacuous.
"""
from __future__ import annotations

import importlib.util
import json
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


def _cdp_up():
    return {"reachable": True, "detail": "CDP responding on :9222"}


def _cdp_down():
    return {"reachable": False, "detail": "CDP unreachable on :9222: TimeoutError: timed out"}


def _good_eod_sources():
    """A clean prior fire for all 3 EOD-flatten tasks -- isolates OTHER checks under test
    from the new eod_reality:* checks (same role as _good_acct()/_cdp_up())."""
    llm_ok_log = (
        "2026-07-08 15:55:03 ET FIRE et=15:55:01\n"
        "2026-07-08 15:55:04 ET === START tick (timeout=120s effort=low budget=1 model=sonnet) ===\n"
        "2026-07-08 15:55:20 ET === END tick exit=0 ===\n"
    )
    return {
        "Gamma_EodFlatten": {"date": "2026-07-08", "text": llm_ok_log},
        "Gamma_EodFlatten_Aggressive": {"date": "2026-07-08", "text": llm_ok_log},
        "Gamma_EodFlattenCore": {"date": "2026-07-08", "rows": [
            {"arm": "safe-2", "outcome": "NOOP"},
            {"arm": "bold-2", "outcome": "NOOP"},
        ]},
    }


def test_build_report_shape_green():
    rep = por.build_report("2026-06-29 05:48:00", _all_ready(), _good_acct(), _cdp_up(), _good_eod_sources())
    assert rep["verdict"] == "GREEN"
    assert rep["reds"] == []
    assert rep["checked_at_et"] == "2026-06-29 05:48:00"
    # + broker + tv_cdp + one eod_reality check per EOD_FLATTEN_REALITY_TASKS
    assert len(rep["checks"]) == len(por.LIVE_CHAIN) + 2 + len(por.EOD_FLATTEN_REALITY_TASKS)


def test_build_report_reds_listed():
    states = _all_ready()
    del states["Gamma_HeartbeatCore"]
    rep = por.build_report("t", states, _good_acct(), _cdp_up(), _good_eod_sources())
    assert rep["verdict"] == "RED"
    assert "Gamma_HeartbeatCore" in rep["reds"]


def test_build_report_defaults_cdp_info_to_down_not_a_crash():
    # No 4th/5th arg at all -- must not raise, and must not silently claim CDP/eod-flatten fine.
    rep = por.build_report("t", _all_ready(), _good_acct())
    assert rep["verdict"] == "RED"
    assert "tv_cdp" in rep["reds"]


def test_build_report_defaults_eod_flatten_sources_to_red_not_green():
    # No 5th arg -- must default toward RED ("unverified"), never silently credit success.
    rep = por.build_report("t", _all_ready(), _good_acct(), _cdp_up())
    assert rep["verdict"] == "RED"
    assert any(r.startswith("eod_reality:") for r in rep["reds"])


# ---- assess_tv_cdp / fetch_tv_cdp (the 2026-07-06 fix) ----

def test_cdp_reachable_is_green_and_critical():
    checks = por.assess_tv_cdp(_cdp_up())
    assert len(checks) == 1
    assert checks[0].status == "GREEN" and checks[0].critical

def test_cdp_unreachable_is_red_and_critical():
    checks = por.assess_tv_cdp(_cdp_down())
    assert checks[0].status == "RED" and checks[0].critical

def test_cdp_unreachable_reds_the_fused_verdict():
    checks = por.assess_task_chain(_all_ready()) + por.assess_broker(_good_acct()) + por.assess_tv_cdp(_cdp_down())
    assert por.fuse(checks) == "RED"

def test_fetch_tv_cdp_fail_open_on_connection_error(monkeypatch):
    # No TV/CDP listening at all -- must degrade to reachable=False, never raise.
    def _boom(*a, **k):
        raise OSError("Connection refused")
    import urllib.request as _ur
    monkeypatch.setattr(_ur, "urlopen", _boom)
    info = por.fetch_tv_cdp()
    assert info["reachable"] is False
    assert "unreachable" in info["detail"].lower()

def test_fetch_tv_cdp_true_when_reachable(monkeypatch):
    class _FakeResp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
    import urllib.request as _ur
    monkeypatch.setattr(_ur, "urlopen", lambda *a, **k: _FakeResp())
    info = por.fetch_tv_cdp()
    assert info["reachable"] is True


def test_fetchers_fail_open(monkeypatch):
    # A scheduler/broker failure must degrade to {}, never raise (rail-2 fail-open).
    monkeypatch.setattr(por.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    assert por.fetch_task_states() == {}


# ---- transition-only J-ping (the WIRE-PREOPEN-READINESS-SCHEDULE addition) ----

def _red_report():
    """A report carrying exactly one critical RED check (a transition source).
    CDP + eod-flatten sources explicitly healthy so they don't add unrelated reds here."""
    states = _all_ready()
    del states["Gamma_HeartbeatCore"]
    return por.build_report("t", states, _good_acct(), _cdp_up(), _good_eod_sources())


def test_build_report_has_red_checks_key():
    # red_checks is the idempotency key the alerter reads -- it must always exist.
    rep = por.build_report("t", _all_ready(), _good_acct(), _cdp_up(), _good_eod_sources())
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
    rep = por.build_report("t", _all_ready(), _good_acct(), _cdp_up(), _good_eod_sources())
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


# ---- assess_eod_flatten_reality / fetch_eod_flatten_reality (2026-07-09 fix) ----
# Bite target: 2026-07-08's real Gamma_EodFlatten/_Aggressive fires exited 1
# ("Exceeded USD budget (1)") while Get-ScheduledTaskInfo reported LastTaskResult=0.
# These tests prove the NEW reader catches that masked failure from the log tail alone.

def test_eod_reality_green_on_all_good_sources():
    checks = por.assess_eod_flatten_reality(_good_eod_sources())
    assert len(checks) == len(por.EOD_FLATTEN_REALITY_TASKS)
    assert all(c.status == "GREEN" and c.critical for c in checks)
    assert por.fuse(checks) == "GREEN"


def test_eod_reality_red_on_masked_exit_one():
    """The EXACT 2026-07-08 bug: real log says exit=1, but nothing about the input dict
    claims LastTaskResult -- if this test is green, the masking is defeated."""
    masked_log = (
        "2026-07-08 15:55:03 ET FIRE et=15:55:01\n"
        "2026-07-08 15:55:04 ET === START tick (timeout=120s effort=low budget=1 model=sonnet) ===\n"
        "Error: Exceeded USD budget (1)\n"
        "2026-07-08 15:55:40 ET === END tick exit=1 ===\n"
    )
    sources = {
        "Gamma_EodFlatten": {"date": "2026-07-08", "text": masked_log},
        "Gamma_EodFlatten_Aggressive": {"date": "2026-07-08", "text": masked_log},
        "Gamma_EodFlattenCore": {"date": "2026-07-08", "rows": [
            {"arm": "safe-2", "outcome": "NOOP"}, {"arm": "bold-2", "outcome": "NOOP"},
        ]},
    }
    checks = por.assess_eod_flatten_reality(sources)
    llm = [c for c in checks if c.name in ("eod_reality:Gamma_EodFlatten", "eod_reality:Gamma_EodFlatten_Aggressive")]
    assert len(llm) == 2
    assert all(c.status == "RED" and c.critical for c in llm)
    assert all("REAL exit=1" in c.detail for c in llm)
    assert por.fuse(checks) == "RED"


def test_eod_reality_red_on_missing_fire():
    # No sources at all -- e.g. a fresh install before its first fire -- must RED, not GREEN.
    checks = por.assess_eod_flatten_reality({})
    assert len(checks) == len(por.EOD_FLATTEN_REALITY_TASKS)
    assert all(c.status == "RED" and c.critical for c in checks)
    assert all("no fire found" in c.detail for c in checks)
    assert por.fuse(checks) == "RED"


def test_eod_reality_red_on_core_bad_outcome():
    sources = dict(_good_eod_sources())
    sources["Gamma_EodFlattenCore"] = {"date": "2026-07-08", "rows": [
        {"arm": "safe-2", "outcome": "PARTIAL_FILL_ESCALATION"},
        {"arm": "bold-2", "outcome": "NOOP"},
    ]}
    checks = por.assess_eod_flatten_reality(sources)
    core = next(c for c in checks if c.name == "eod_reality:Gamma_EodFlattenCore")
    assert core.status == "RED" and core.critical
    assert "PARTIAL_FILL_ESCALATION" in core.detail
    assert "safe-2" in core.detail


def test_eod_reality_red_on_core_no_rows_parsed():
    sources = dict(_good_eod_sources())
    sources["Gamma_EodFlattenCore"] = {"date": "2026-07-08", "rows": []}
    checks = por.assess_eod_flatten_reality(sources)
    core = next(c for c in checks if c.name == "eod_reality:Gamma_EodFlattenCore")
    assert core.status == "RED"


def test_eod_reality_red_on_llm_log_with_no_end_marker():
    # A fire that started (FIRE/START logged) but never reached END -- e.g. process killed
    # mid-tick -- must RED, not silently pass just because SOME text was found.
    sources = dict(_good_eod_sources())
    sources["Gamma_EodFlatten"] = {"date": "2026-07-08", "text": "2026-07-08 15:55:03 ET FIRE et=15:55:01\n"}
    checks = por.assess_eod_flatten_reality(sources)
    llm = next(c for c in checks if c.name == "eod_reality:Gamma_EodFlatten")
    assert llm.status == "RED"
    assert "no END-tick marker" in llm.detail


def test_build_report_reds_on_masked_exit_end_to_end():
    """Full end-to-end: build_report with a masked-exit log input REDs the whole verdict,
    even though task_states/broker/cdp are all otherwise perfectly healthy."""
    masked_log = "2026-07-08 15:55:40 ET === END tick exit=1 ===\n"
    sources = {
        "Gamma_EodFlatten": {"date": "2026-07-08", "text": masked_log},
        "Gamma_EodFlatten_Aggressive": {"date": "2026-07-08", "text": masked_log},
        "Gamma_EodFlattenCore": {"date": "2026-07-08", "rows": [
            {"arm": "safe-2", "outcome": "NOOP"}, {"arm": "bold-2", "outcome": "NOOP"},
        ]},
    }
    rep = por.build_report("t", _all_ready(), _good_acct(), _cdp_up(), sources)
    assert rep["verdict"] == "RED"
    assert "eod_reality:Gamma_EodFlatten" in rep["reds"]
    assert "eod_reality:Gamma_EodFlatten_Aggressive" in rep["reds"]


def test_latest_dated_file_picks_the_newest(tmp_path):
    (tmp_path / "eod-flatten-2026-07-01.log").write_text("old", encoding="utf-8")
    (tmp_path / "eod-flatten-2026-07-08.log").write_text("new", encoding="utf-8")
    found = por._latest_dated_file(tmp_path, "eod-flatten-[0-9]*.log", r"eod-flatten-(\d{4}-\d{2}-\d{2})\.log")
    assert found is not None
    path, date = found
    assert date == "2026-07-08"
    assert path.read_text(encoding="utf-8") == "new"


def test_latest_dated_file_none_when_no_match(tmp_path):
    assert por._latest_dated_file(tmp_path, "eod-flatten-[0-9]*.log", r"eod-flatten-(\d{4}-\d{2}-\d{2})\.log") is None


def test_fetch_eod_flatten_reality_reads_real_tmp_files(tmp_path, monkeypatch):
    """Bite test: write real files in the exact on-disk convention (separate LLM .log for
    safe/aggressive + eod_flatten.py's .jsonl for Core) and confirm the fetcher parses all 3
    without any mocking of the parsing logic itself."""
    monkeypatch.setattr(por, "LOG_DIR", tmp_path)
    (tmp_path / "eod-flatten-2026-07-08.log").write_text(
        "2026-07-08 15:55:04 ET === START tick ===\n2026-07-08 15:55:20 ET === END tick exit=0 ===\n",
        encoding="utf-8",
    )
    (tmp_path / "eod-flatten-aggressive-2026-07-08.log").write_text(
        "2026-07-08 15:55:04 ET === START tick ===\n2026-07-08 15:55:20 ET === END tick exit=0 ===\n",
        encoding="utf-8",
    )
    (tmp_path / "eod-flatten-2026-07-08.jsonl").write_text(
        json.dumps({"arm": "safe-2", "outcome": "NOOP"}) + "\n"
        + json.dumps({"arm": "bold-2", "outcome": "NOOP"}) + "\n",
        encoding="utf-8",
    )

    out = por.fetch_eod_flatten_reality()
    assert out["Gamma_EodFlatten"]["date"] == "2026-07-08"
    assert "exit=0" in out["Gamma_EodFlatten"]["text"]
    assert out["Gamma_EodFlatten_Aggressive"]["date"] == "2026-07-08"
    assert {r["arm"] for r in out["Gamma_EodFlattenCore"]["rows"]} == {"safe-2", "bold-2"}

    checks = por.assess_eod_flatten_reality(out)
    assert all(c.status == "GREEN" for c in checks)


def test_fetch_eod_flatten_reality_fail_open_on_missing_dir(monkeypatch, tmp_path):
    # A log dir that doesn't exist at all must degrade to {}, never raise (rail-2).
    monkeypatch.setattr(por, "LOG_DIR", tmp_path / "does-not-exist")
    assert por.fetch_eod_flatten_reality() == {}


def test_fetch_eod_flatten_reality_drops_stale_entries(tmp_path, monkeypatch):
    """A log file that exists but is far older than EOD_FLATTEN_MAX_AGE_DAYS must be
    treated as 'no fire' (dropped), not credited as a recent success."""
    monkeypatch.setattr(por, "LOG_DIR", tmp_path)
    (tmp_path / "eod-flatten-2020-01-01.log").write_text(
        "2020-01-01 15:55:20 ET === END tick exit=0 ===\n", encoding="utf-8",
    )
    out = por.fetch_eod_flatten_reality()
    assert "Gamma_EodFlatten" not in out

"""Guard for task_state_guard.py -- closes self-healing blind spot (a) from the
2026-08-08 Lane B audit: NOTHING previously verified a scheduled task's Enabled state
(task_health_et.ps1 explicitly `Where-Object { $_.State -ne 'Disabled' }`s them OUT).

Mirrors test_preopen_readiness.py's module-loading + injectable-state-dict conventions.
Query/enable are mocked throughout (per the task's own directive) -- no real
subprocess/schtasks calls in this suite; the module's own docstring records a live
end-to-end self-test against a disposable scheduled task (created, disabled, repaired,
re-verified, deleted) run manually this session as additional evidence beyond these
unit tests.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "setup" / "scripts" / "task_state_guard.py"
_spec = importlib.util.spec_from_file_location("task_state_guard", _SCRIPT)
tsg = importlib.util.module_from_spec(_spec)
sys.modules["task_state_guard"] = tsg
_spec.loader.exec_module(tsg)  # type: ignore


# ---- the pinned list itself ----

def test_pinned_list_covers_the_audit_named_tasks():
    names = set(tsg.CRITICAL_NAMES)
    audit_named = {
        "Gamma_HeartbeatCore", "Gamma_SightBeacon", "Gamma_EodFlatten",
        "Gamma_EodFlatten_Aggressive", "Gamma_Premarket", "Gamma_LaunchTV",
        "Gamma_TvWatchdog", "Gamma_Conductor", "Gamma_ConductorWake",
        "Gamma_DashboardKeepalive",
    }
    assert audit_named <= names


def test_pinned_list_has_no_duplicates():
    assert len(tsg.CRITICAL_NAMES) == len(set(tsg.CRITICAL_NAMES))


def test_every_pinned_task_has_a_tier_and_role():
    for spec in tsg.CRITICAL_TASKS:
        assert spec["tier"] in ("trading", "autonomy")
        assert spec["role"]


# ---- classify_tasks (pure) ----

def _states_all_ready(names):
    return {n: {"found": True, "state": "Ready", "last_result": 0} for n in names}


def test_all_ready_is_clean_green():
    pinned = tsg.CRITICAL_TASKS
    states = _states_all_ready(tsg.CRITICAL_NAMES)
    rows = tsg.classify_tasks(pinned, states)
    assert tsg._verdict(rows) == "GREEN"
    assert tsg._problems(rows) == []


def test_disabled_task_detected_and_marked_for_repair_when_not_dry_run():
    pinned = [{"name": "Gamma_HeartbeatCore", "tier": "trading", "role": "engine"}]
    states = {"Gamma_HeartbeatCore": {"found": True, "state": "Disabled", "last_result": 0}}
    # repair_results says the (mocked) enable succeeded
    rows = tsg.classify_tasks(pinned, states, repair_results={"Gamma_HeartbeatCore": True})
    assert rows[0]["action"] == "re-enabled"
    assert rows[0]["severity"] == "warning"
    assert tsg._verdict(rows) == "YELLOW"


def test_disabled_task_re_enable_failure_stays_critical():
    pinned = [{"name": "Gamma_HeartbeatCore", "tier": "trading", "role": "engine"}]
    states = {"Gamma_HeartbeatCore": {"found": True, "state": "Disabled", "last_result": 0}}
    rows = tsg.classify_tasks(pinned, states, repair_results={"Gamma_HeartbeatCore": False})
    assert rows[0]["action"] == "re-enable-failed"
    assert rows[0]["severity"] == "critical"
    assert tsg._verdict(rows) == "RED"


def test_disabled_task_under_dry_run_never_marked_repaired():
    pinned = [{"name": "Gamma_HeartbeatCore", "tier": "trading", "role": "engine"}]
    states = {"Gamma_HeartbeatCore": {"found": True, "state": "Disabled", "last_result": 0}}
    rows = tsg.classify_tasks(pinned, states, repair_results={}, dry_run=True)
    assert rows[0]["action"] == "would-re-enable(dry-run)"
    assert rows[0]["severity"] == "critical"


def test_missing_task_is_critical_never_silently_ok():
    pinned = [{"name": "Gamma_DashboardKeepalive", "tier": "autonomy", "role": "dashboard"}]
    states = {"Gamma_DashboardKeepalive": {"found": False, "state": "MISSING", "last_result": None}}
    rows = tsg.classify_tasks(pinned, states)
    assert rows[0]["severity"] == "critical"
    assert "MISSING" in rows[0]["note"]
    assert tsg._verdict(rows) == "RED"


def test_missing_task_absent_from_states_dict_still_flagged():
    """A name PowerShell never echoed a line for at all (not even MISSING) must still
    surface as critical -- classify_tasks must not treat 'no entry' as 'fine'."""
    pinned = [{"name": "Gamma_Conductor", "tier": "autonomy", "role": "conductor"}]
    rows = tsg.classify_tasks(pinned, states={})
    assert rows[0]["severity"] == "critical"
    assert rows[0]["state"] == "MISSING"


def test_nonzero_last_result_recorded_as_warning_not_escalated_to_critical():
    pinned = [{"name": "Gamma_SightBeacon", "tier": "trading", "role": "beacon"}]
    states = {"Gamma_SightBeacon": {"found": True, "state": "Ready", "last_result": 1}}
    rows = tsg.classify_tasks(pinned, states)
    assert rows[0]["severity"] == "warning"
    assert "LastTaskResult=1" in rows[0]["note"]
    assert tsg._verdict(rows) == "YELLOW"


def test_zero_last_result_is_not_a_problem():
    pinned = [{"name": "Gamma_SightBeacon", "tier": "trading", "role": "beacon"}]
    states = {"Gamma_SightBeacon": {"found": True, "state": "Ready", "last_result": 0}}
    rows = tsg.classify_tasks(pinned, states)
    assert rows[0]["severity"] == "ok"


# ---- run() orchestration: query/enable layer mocked, per the task directive ----

def test_run_clean_pass_writes_no_outbox_row(tmp_path):
    out = tmp_path / "out.json"
    outbox = tmp_path / "outbox.jsonl"
    last = tmp_path / "last.json"
    pinned = [{"name": "Gamma_HeartbeatCore", "tier": "trading", "role": "engine"}]

    def query_fn(names):
        return _states_all_ready(names)

    def enable_fn(names):  # pragma: no cover -- must never be called on a clean pass
        raise AssertionError("enable_fn must not be called when nothing is disabled")

    r = tsg.run(dry_run=False, query_fn=query_fn, enable_fn=enable_fn,
                out_path=out, outbox_path=outbox, last_path=last, pinned=pinned)
    assert r["verdict"] == "GREEN"
    assert out.exists()
    assert not outbox.exists(), "clean pass must never write an outbox row"


def test_run_disabled_task_gets_repaired_and_reflected_in_output(tmp_path):
    out = tmp_path / "out.json"
    outbox = tmp_path / "outbox.jsonl"
    last = tmp_path / "last.json"
    pinned = [{"name": "Gamma_HeartbeatCore", "tier": "trading", "role": "engine"}]

    calls = {"query": 0}

    def query_fn(names):
        calls["query"] += 1
        if calls["query"] == 1:
            return {"Gamma_HeartbeatCore": {"found": True, "state": "Disabled", "last_result": 0}}
        # verification re-query after the (mocked) repair
        return {"Gamma_HeartbeatCore": {"found": True, "state": "Ready", "last_result": 0}}

    def enable_fn(names):
        return {n: True for n in names}

    r = tsg.run(dry_run=False, query_fn=query_fn, enable_fn=enable_fn,
                out_path=out, outbox_path=outbox, last_path=last, pinned=pinned)
    assert r["verdict"] == "YELLOW"
    assert r["repairs"] == ["Gamma_HeartbeatCore"]
    assert r["tasks"][0]["action"] == "re-enabled"
    assert r["tasks"][0]["state"] == "Ready", "displayed state must reflect the VERIFIED post-repair state"
    assert outbox.exists(), "a real repair must produce an outbox row"
    row = json.loads(outbox.read_text(encoding="utf-8").splitlines()[0])
    assert row["source"] == "task_state_guard"
    assert "re-enabled" in row["message"]


def test_run_repeated_unchanged_problem_does_not_spam_outbox(tmp_path):
    """Same DISABLED-and-unrepairable problem two fires in a row -> only ONE outbox row
    (mirrors self_check.py's own dedup-on-unchanged-signature idiom)."""
    out = tmp_path / "out.json"
    outbox = tmp_path / "outbox.jsonl"
    last = tmp_path / "last.json"
    pinned = [{"name": "Gamma_DashboardKeepalive", "tier": "autonomy", "role": "dashboard"}]

    def query_fn(names):
        return {"Gamma_DashboardKeepalive": {"found": False, "state": "MISSING", "last_result": None}}

    def enable_fn(names):  # pragma: no cover -- nothing to enable for a MISSING task
        raise AssertionError("enable_fn must not be called for a MISSING task")

    r1 = tsg.run(dry_run=False, query_fn=query_fn, enable_fn=enable_fn,
                 out_path=out, outbox_path=outbox, last_path=last, pinned=pinned)
    r2 = tsg.run(dry_run=False, query_fn=query_fn, enable_fn=enable_fn,
                 out_path=out, outbox_path=outbox, last_path=last, pinned=pinned)
    assert r1["verdict"] == "RED" and r2["verdict"] == "RED"
    lines = outbox.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1, "unchanged problem signature across fires must collapse to ONE outbox row"


def test_run_fails_open_on_query_exception(tmp_path):
    out = tmp_path / "out.json"
    outbox = tmp_path / "outbox.jsonl"
    last = tmp_path / "last.json"
    pinned = [{"name": "Gamma_HeartbeatCore", "tier": "trading", "role": "engine"}]

    def query_fn(names):
        raise RuntimeError("powershell.exe not found")

    def enable_fn(names):  # pragma: no cover
        raise AssertionError("enable_fn must not be called after a query exception")

    r = tsg.run(dry_run=False, query_fn=query_fn, enable_fn=enable_fn,
                out_path=out, outbox_path=outbox, last_path=last, pinned=pinned)
    # run() itself never raises -- caught by the outermost fail-open net.
    assert r["verdict"] == "GUARD_ERROR"
    assert out.exists()
    assert not outbox.exists()


def test_run_fails_open_when_query_returns_none(tmp_path):
    """query_task_states()'s own documented contract: None means the query itself broke
    (distinct from every task genuinely being missing) -> QUERY_FAILED, no action taken."""
    out = tmp_path / "out.json"
    outbox = tmp_path / "outbox.jsonl"
    last = tmp_path / "last.json"
    pinned = [{"name": "Gamma_HeartbeatCore", "tier": "trading", "role": "engine"}]

    def query_fn(names):
        return None

    def enable_fn(names):  # pragma: no cover
        raise AssertionError("enable_fn must not be called when the query returned None")

    r = tsg.run(dry_run=False, query_fn=query_fn, enable_fn=enable_fn,
                out_path=out, outbox_path=outbox, last_path=last, pinned=pinned)
    assert r["verdict"] == "QUERY_FAILED"
    assert not outbox.exists()


def test_run_dry_run_never_calls_enable_fn(tmp_path):
    out = tmp_path / "out.json"
    outbox = tmp_path / "outbox.jsonl"
    last = tmp_path / "last.json"
    pinned = [{"name": "Gamma_HeartbeatCore", "tier": "trading", "role": "engine"}]

    def query_fn(names):
        return {"Gamma_HeartbeatCore": {"found": True, "state": "Disabled", "last_result": 0}}

    def enable_fn(names):  # pragma: no cover -- dry-run must never repair
        raise AssertionError("enable_fn must not be called under --dry-run")

    r = tsg.run(dry_run=True, query_fn=query_fn, enable_fn=enable_fn,
                out_path=out, outbox_path=outbox, last_path=last, pinned=pinned)
    assert r["dry_run"] is True
    assert r["tasks"][0]["action"] == "would-re-enable(dry-run)"
    assert r["repairs"] == []


def test_run_dry_run_writes_output_file_but_the_scheduler_itself_is_untouched(tmp_path):
    """--dry-run still writes its own status JSON (so the pulse/status surface has
    something to read) -- 'writes nothing' means no repair action + no outbox spam, not
    a fully silent run."""
    out = tmp_path / "out.json"
    outbox = tmp_path / "outbox.jsonl"
    last = tmp_path / "last.json"
    pinned = [{"name": "Gamma_HeartbeatCore", "tier": "trading", "role": "engine"}]

    def query_fn(names):
        return _states_all_ready(names)

    def enable_fn(names):  # pragma: no cover
        raise AssertionError("enable_fn must not be called on a clean dry-run pass")

    r = tsg.run(dry_run=True, query_fn=query_fn, enable_fn=enable_fn,
                out_path=out, outbox_path=outbox, last_path=last, pinned=pinned)
    assert r["verdict"] == "GREEN"
    assert out.exists()
    assert not outbox.exists()


def test_main_always_returns_zero_even_on_guard_error(monkeypatch, tmp_path):
    """This script must never itself become a masked-exit source -- exit 0 always."""
    def boom_query(names):
        raise RuntimeError("boom")
    monkeypatch.setattr(tsg, "query_task_states", boom_query)
    monkeypatch.setattr(tsg, "OUT_PATH", tmp_path / "out.json")
    monkeypatch.setattr(tsg, "LAST_PATH", tmp_path / "last.json")
    rc = tsg.main([])
    assert rc == 0

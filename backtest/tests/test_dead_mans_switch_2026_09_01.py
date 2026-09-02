"""Guards for setup/scripts/dead_mans_switch.py -- the independent watchdog that closes the
go-live gate's operational criterion 2 last named gap ("heal-engine.ps1 restarts dead
processes but does not flatten open positions; exit_actuator.py's orphan-position adoption
only reconciles once the SAME process resumes ticking -- it is not an INDEPENDENT watchdog").

Named `test_dead_mans_switch_open_position_on_process_death_flattens` deliberately, so
go_live_gate.py's own guard-discovery (kill/watchdog/process-death/independent-flatten
pattern search) finds it and flips that operational sub-check from NO TEST FOUND to PASS.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

_spec = importlib.util.spec_from_file_location("dead_mans_switch_g", SCRIPTS / "dead_mans_switch.py")
dms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dms)  # type: ignore[union-attr]


# --------------------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------------------- #
class FakeBroker:
    """Stand-in for the fleet_broker MODULE (load_creds + checked-read + close primitives).
    Records calls so tests can assert exact fire counts."""

    def __init__(self, positions=None, read_ok=True, close_remaining=0, creds=None):
        self._positions = positions if positions is not None else []
        self._read_ok = read_ok
        self._close_remaining = close_remaining
        self.close_calls = []
        self.read_calls = 0
        self._creds = creds if creds is not None else {
            "safe-2": {"key": "k", "secret": "s", "base_url": "https://x"},
            "bold-2": {"key": "k", "secret": "s", "base_url": "https://x"},
            "safe-3": {"key": "k", "secret": "s", "base_url": "https://x"},
        }

    def load_creds(self):
        return dict(self._creds)

    def open_spy_option_positions_checked(self, creds):
        self.read_calls += 1
        return (list(self._positions), self._read_ok)

    def close_all_spy_options(self, creds, *, live, arm=None, reason=None):
        self.close_calls.append({"live": live, "arm": arm, "reason": reason})
        closed = [p["symbol"] for p in self._positions]
        # simulate a successful close -- subsequent reads report flat
        self._positions = []
        return {"closed": closed, "errors": [], "remaining": self._close_remaining}


@pytest.fixture()
def fake_env(tmp_path, monkeypatch):
    """Isolates every path dms.py touches into tmp_path, and stubs the roster to two core
    arms + one fleet arm so a test can control liveness precisely without real ledgers."""
    monkeypatch.setattr(dms, "_REPO", tmp_path)
    monkeypatch.setattr(dms, "CORE_DECISIONS_PATH", tmp_path / "automation" / "state" / "core-decisions.jsonl")
    monkeypatch.setattr(dms, "FLEET_DIR", tmp_path / "automation" / "state" / "fleet")
    monkeypatch.setattr(dms, "STATE_PATH", tmp_path / "automation" / "state" / "dead-mans-switch.json")
    monkeypatch.setattr(dms, "STATUS_MD", tmp_path / "automation" / "overnight" / "STATUS.md")
    monkeypatch.setattr(dms, "LOG_DIR", tmp_path / "automation" / "state" / "logs")
    dms.LOG_DIR.mkdir(parents=True, exist_ok=True)
    dms.CORE_DECISIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    dms.FLEET_DIR.mkdir(parents=True, exist_ok=True)

    class _FakeEodFlatten:
        @staticmethod
        def _active_arms():
            return ["safe-2", "bold-2", "safe-3"]

    monkeypatch.setattr(dms, "_eod_flatten", _FakeEodFlatten)
    return tmp_path


def _write_core_row(tmp_path: Path, account: str, ts_et: str) -> None:
    p = tmp_path / "automation" / "state" / "core-decisions.jsonl"
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts_et": ts_et, "account": account}) + "\n")


def _write_fleet_row(tmp_path: Path, arm: str, ts_et: str) -> None:
    d = tmp_path / "automation" / "state" / "fleet" / arm
    d.mkdir(parents=True, exist_ok=True)
    with (d / "decisions.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts_et": ts_et, "arm_id": arm}) + "\n")


RTH_ET = datetime(2026, 9, 1, 12, 0, 0)  # Tuesday, well inside 09:32-15:58 ET
RTH_UTC = RTH_ET.replace(tzinfo=timezone(timedelta(hours=-4))).astimezone(timezone.utc)
# EDT (UTC-4) is in effect on 2026-09-01 -- keeps the fleet ledger's aware-offset age math and
# the core ledger's naive-ET age math describing the SAME instant in every test below.


def _pin_clock(monkeypatch, et=RTH_ET, utc=RTH_UTC) -> None:
    monkeypatch.setattr(dms, "et_now", lambda: et)
    monkeypatch.setattr(dms, "_utc_now", lambda: utc)


# --------------------------------------------------------------------------------------- #
# 1. RTH gate
# --------------------------------------------------------------------------------------- #
def test_rth_gate_blocks_off_hours() -> None:
    weekend = datetime(2026, 9, 5, 12, 0, 0)  # Saturday
    assert weekend.weekday() >= 5
    assert dms.is_rth(weekend) is False

    before_open = datetime(2026, 9, 1, 9, 0, 0)
    assert dms.is_rth(before_open) is False

    after_close = datetime(2026, 9, 1, 16, 30, 0)
    assert dms.is_rth(after_close) is False

    assert dms.is_rth(RTH_ET) is True


def test_main_exits_0_and_does_nothing_off_rth(fake_env, monkeypatch) -> None:
    monkeypatch.setattr(dms, "et_now", lambda: datetime(2026, 9, 5, 12, 0, 0))  # Saturday
    fb = FakeBroker(positions=[{"symbol": "SPY260901C00760000", "qty": "3"}])
    monkeypatch.setattr(dms, "fleet_broker", fb)
    rc = dms.main()
    assert rc == 0
    assert fb.read_calls == 0, "off-RTH must never touch the broker"
    assert not dms.STATE_PATH.exists(), "off-RTH must not even write a snapshot"


# --------------------------------------------------------------------------------------- #
# 2. THE NAMED GUARD -- go_live_gate.py's discovery target.
#    Simulated process death (stale ledger rows) + a fake broker reporting an open position
#    -> flatten is called EXACTLY ONCE for the dead arm.
# --------------------------------------------------------------------------------------- #
def test_dead_mans_switch_open_position_on_process_death_flattens(fake_env, monkeypatch) -> None:
    tmp_path = fake_env
    stale_ts = (RTH_ET - timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M:%S")
    fresh_ts = (RTH_ET - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S")

    # safe-2 (core): DEAD -- last row 45 minutes ago (> STALE_MIN=10).
    _write_core_row(tmp_path, "safe", stale_ts)
    # bold-2 (core): LIVE -- last row 1 minute ago.
    _write_core_row(tmp_path, "bold", fresh_ts)
    # safe-3 (fleet): not written at all -> None liveness -> treated as maximally stale.

    fb = FakeBroker(positions=[{"symbol": "SPY260901C00760000", "qty": "3"}], read_ok=True)
    monkeypatch.setattr(dms, "fleet_broker", fb)
    _pin_clock(monkeypatch)

    rc = dms.main()
    assert rc == 0

    # safe-2 and safe-3 are both stale-with-open-position -> exactly TWO flattens fired
    # (one per stale+open arm), never a single blanket close and never one per LIVE arm.
    fired_arms = [c["arm"] for c in fb.close_calls]
    assert fired_arms.count("safe-2") == 1, f"expected exactly one flatten for safe-2, got calls={fb.close_calls}"
    assert "bold-2" not in fired_arms, "bold-2 is LIVE -- must never be flattened"

    report = json.loads(dms.STATE_PATH.read_text(encoding="utf-8"))
    assert report["per_arm"]["safe-2"]["action"] == "FLATTENED"
    assert report["per_arm"]["bold-2"]["action"] == "LIVE_NO_ACTION"

    status_txt = (tmp_path / "automation" / "overnight" / "STATUS.md").read_text(encoding="utf-8")
    assert "DEAD-MANS-SWITCH FIRED" in status_txt
    assert "safe-2" in status_txt


# --------------------------------------------------------------------------------------- #
# 3. Live engine -> no action, no flatten call at all.
# --------------------------------------------------------------------------------------- #
def test_live_engine_takes_no_action(fake_env, monkeypatch) -> None:
    tmp_path = fake_env
    fresh_ts = (RTH_ET - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%S")
    _write_core_row(tmp_path, "safe", fresh_ts)
    _write_core_row(tmp_path, "bold", fresh_ts)
    _write_fleet_row(tmp_path, "safe-3", (RTH_ET - timedelta(minutes=2)).isoformat() + "-04:00")

    fb = FakeBroker(positions=[{"symbol": "SPY260901C00760000", "qty": "3"}])
    monkeypatch.setattr(dms, "fleet_broker", fb)
    _pin_clock(monkeypatch)

    rc = dms.main()
    assert rc == 0
    assert fb.close_calls == [], "a live engine must never be flattened"
    report = json.loads(dms.STATE_PATH.read_text(encoding="utf-8"))
    for arm in ("safe-2", "bold-2", "safe-3"):
        assert report["per_arm"][arm]["action"] == "LIVE_NO_ACTION"
    assert not (tmp_path / "automation" / "overnight" / "STATUS.md").exists()


# --------------------------------------------------------------------------------------- #
# 4. Stale + broker read FAILURE -> no action, RED line logged, never guesses.
# --------------------------------------------------------------------------------------- #
def test_stale_with_broker_read_failure_takes_no_action_and_logs_red(fake_env, monkeypatch) -> None:
    tmp_path = fake_env
    stale_ts = (RTH_ET - timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M:%S")
    _write_core_row(tmp_path, "safe", stale_ts)
    _write_core_row(tmp_path, "bold", stale_ts)

    fb = FakeBroker(positions=[{"symbol": "SPY260901C00760000", "qty": "3"}], read_ok=False)
    monkeypatch.setattr(dms, "fleet_broker", fb)
    _pin_clock(monkeypatch)

    rc = dms.main()
    assert rc == 0
    assert fb.close_calls == [], "an unreadable broker state must NEVER be flattened -- fail-closed on the action"

    report = json.loads(dms.STATE_PATH.read_text(encoding="utf-8"))
    assert report["per_arm"]["safe-2"]["action"] == "READ_FAILED"

    log_path, _ = dms._log_paths()
    log_text = log_path.read_text(encoding="utf-8")
    assert "DMS_RED" in log_text
    assert "CANNOT confirm" in log_text


# --------------------------------------------------------------------------------------- #
# 5. Stale but already flat -> no flatten call (nothing to close).
# --------------------------------------------------------------------------------------- #
def test_stale_but_flat_takes_no_action(fake_env, monkeypatch) -> None:
    tmp_path = fake_env
    stale_ts = (RTH_ET - timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M:%S")
    _write_core_row(tmp_path, "safe", stale_ts)
    _write_core_row(tmp_path, "bold", stale_ts)

    fb = FakeBroker(positions=[], read_ok=True)  # flat
    monkeypatch.setattr(dms, "fleet_broker", fb)
    _pin_clock(monkeypatch)

    rc = dms.main()
    assert rc == 0
    assert fb.close_calls == []
    report = json.loads(dms.STATE_PATH.read_text(encoding="utf-8"))
    assert report["per_arm"]["safe-2"]["action"] == "STALE_BUT_FLAT"


# --------------------------------------------------------------------------------------- #
# 6. Fail-open on exception: a crash anywhere inside check_arm must never propagate, and
#    main() must still return 0 and still process the other arms.
# --------------------------------------------------------------------------------------- #
def test_fail_open_on_exception_never_raises_and_processes_other_arms(fake_env, monkeypatch) -> None:
    tmp_path = fake_env
    stale_ts = (RTH_ET - timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M:%S")
    _write_core_row(tmp_path, "safe", stale_ts)
    _write_core_row(tmp_path, "bold", stale_ts)

    class ExplodingBroker(FakeBroker):
        def open_spy_option_positions_checked(self, creds):
            raise RuntimeError("simulated broker meltdown")

    fb = ExplodingBroker()
    monkeypatch.setattr(dms, "fleet_broker", fb)
    _pin_clock(monkeypatch)

    rc = dms.main()  # must not raise
    assert rc == 0
    report = json.loads(dms.STATE_PATH.read_text(encoding="utf-8"))
    assert report["per_arm"]["safe-2"]["action"] == "ERROR"
    assert report["per_arm"]["bold-2"]["action"] == "ERROR", "one arm's exception must not stop the sweep over the others"


def test_main_never_raises_even_when_et_now_is_broken(fake_env, monkeypatch) -> None:
    def _boom():
        raise RuntimeError("clock is broken")
    monkeypatch.setattr(dms, "et_now", _boom)
    assert dms.main() == 0  # must not raise


# --------------------------------------------------------------------------------------- #
# 7. Liveness math -- unit-level, no I/O mocking needed beyond file writes.
# --------------------------------------------------------------------------------------- #
def test_core_liveness_minutes_computes_age(fake_env) -> None:
    tmp_path = fake_env
    ts = (RTH_ET - timedelta(minutes=7)).strftime("%Y-%m-%dT%H:%M:%S")
    _write_core_row(tmp_path, "safe", ts)
    age = dms.core_liveness_minutes("safe", RTH_ET)
    assert age is not None
    assert 6.9 <= age <= 7.1


def test_core_liveness_minutes_none_when_no_data(fake_env) -> None:
    assert dms.core_liveness_minutes("safe", RTH_ET) is None


def test_fleet_liveness_minutes_computes_age_from_aware_timestamp(fake_env) -> None:
    tmp_path = fake_env
    now_utc = datetime.now(timezone.utc)
    ts_aware = (now_utc - timedelta(minutes=12)).astimezone(
        timezone(timedelta(hours=-4))).isoformat()
    _write_fleet_row(tmp_path, "safe-3", ts_aware)
    age = dms.fleet_liveness_minutes("safe-3", now_utc)
    assert age is not None
    assert 11.5 <= age <= 12.5


# --------------------------------------------------------------------------------------- #
# 8. go_live_gate.py discovery: statically verify the wiring WITHOUT calling
#    operational_criterion() -- that function subprocess-invokes pytest on every file named
#    in GUARD_TESTS, including this one, so calling it from INSIDE a pytest run of this same
#    file would recursively re-run this whole suite inside itself (verified live: hangs to
#    the 180s subprocess timeout). The actual end-to-end PASS is confirmed by running
#    `go_live_gate.py` directly as a script (see task report), never from within this suite.
# --------------------------------------------------------------------------------------- #
def test_go_live_gate_guard_tests_dict_points_at_this_file() -> None:
    gate_spec = importlib.util.spec_from_file_location(
        "go_live_gate_g", REPO / "setup" / "scripts" / "go_live_gate.py")
    gate = importlib.util.module_from_spec(gate_spec)
    gate_spec.loader.exec_module(gate)  # type: ignore[union-attr]
    rel = gate.GUARD_TESTS.get("dead_mans_switch_open_position_on_process_death")
    assert rel == "backtest/tests/test_dead_mans_switch_2026_09_01.py", rel
    assert (REPO / rel).exists()


def test_go_live_gate_no_longer_hardcodes_the_gap() -> None:
    """RED-PROOF TARGET for the wiring itself: the old permanent 'NO TEST FOUND' block for
    this exact key must be gone, or a real PASS from GUARD_TESTS would be silently overwritten
    by the stale hardcoded FAIL that used to run after it in `operational_criterion`."""
    src = (REPO / "setup" / "scripts" / "go_live_gate.py").read_text(encoding="utf-8")
    assert "NO TEST FOUND" not in src, (
        "the old hardcoded dead-man's-switch gap block is back -- it would overwrite the real "
        "GUARD_TESTS result for dead_mans_switch_open_position_on_process_death"
    )

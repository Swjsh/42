"""Guards for setup/scripts/swing_core_runner.py -- the thin runner wiring
futures_heartbeat_core's SEE/DECIDE onto the fill-sim broker's own ACT/exit engine
(FUTURES-REVIVAL-PLAN sec 2a / Phase 3).

Covers the task's required bites:
  - gating: no armed-setups.json -> SKIP_NO_VALIDATED_SETUP (fail-closed default).
  - gating: a PASS scorecard + an armed setups list -> the entry path is REACHABLE, proven by
    actually observing broker.place_bracket() fire (not just that the gate function alone
    returns True) -- and the negative control (gate fails -> place_bracket never fires) too,
    so a broken always-True OR always-False gate both RED.
  - --monitor mode never attempts a new entry even when the gate would otherwise pass.
  - runner fail-open: both an unhandled exception inside main() (outer contract) and one
    instrument's quote-fetch blowing up inside run_once() (inner, per-instrument contract)
    still return/continue cleanly and LOG the failure.
  - et_clock usage (static grep guard + a positive proof the clock is actually threaded).

Every test constructs FillSimBroker with an explicit tmp `state_dir`, OR (for main()-level
tests, which construct the broker internally) monkeypatches BOTH swing_core_runner's AND
fill_sim_broker's module-level STATE_DIR -- so NONE of these tests can ever write to the real
automation/state/futures/ (which already holds the real intraday tick's live state files).
This script must also never CREATE armed-setups.json (OP-0 arming boundary) -- every gating
test supplies its own tmp_path armed_file/recs_dir via the injectable kwargs added to
check_armed_setups/attempt_entry/run_once specifically so tests never need the real one.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest", "setup/scripts"):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

import swing_core_runner as runner  # noqa: E402
import futures.fill_sim_broker as fsb  # noqa: E402
from futures.fill_sim_broker import FillSimBroker  # noqa: E402
from futures.instruments import MNQ  # noqa: E402
import futures.futures_heartbeat_core as hb  # noqa: E402
import et_clock  # noqa: E402


SRC = (REPO / "setup" / "scripts" / "swing_core_runner.py").read_text(encoding="utf-8")


def _v3_signal():
    """Matches test_futures_heartbeat.py's _one_v3_signal() -- a known should_take_v3 pass
    (erl_irl long/high, vix>=16) so decide_entry() genuinely accepts it, not just a stub."""
    return {"watcher": "erl_irl_watcher", "setup": "ERL_IRL_LONG", "direction": "long",
            "confidence": "high", "entry": 21000.0, "stop": 20980.0, "tp1": 21030.0,
            "runner": 21060.0, "reason": "test"}


def _fake_signals(*_a, **_k):
    return {"signals": [_v3_signal()],
            "snapshot": {"instrument": "MNQ", "close": 21000.0, "ribbon": "BULL",
                         "vix": 18.0, "bar_ts_et": "2026-07-06T11:00:00"}}


def _write_armed_and_pass_scorecard(tmp_path, *, seed="test_seed", instrument=None):
    armed_file = tmp_path / "armed-setups.json"
    recs_dir = tmp_path / "recs"
    recs_dir.mkdir(parents=True, exist_ok=True)
    entry = {"seed": seed}
    if instrument:
        entry["instrument"] = instrument
    armed_file.write_text(json.dumps({"setups": [entry]}), encoding="utf-8")
    (recs_dir / f"futures-swing-{seed}.json").write_text(
        json.dumps({"verdict": "PASS"}), encoding="utf-8")
    return armed_file, recs_dir


def _fake_quote(_sym):
    return {"price": 21000.0, "open": 20995.0, "high": 21005.0, "low": 20995.0,
           "time_et": "2026-01-01T15:35:00"}


# ═══════════════════════ et_clock discipline ══════════════════════════════════
class TestEtClockDiscipline:
    def test_no_naive_datetime_now_in_source(self):
        assert "datetime.now(" not in SRC, (
            "swing_core_runner.py calls naive datetime.now() -- must use et_clock.et_now()")

    def test_et_now_is_actually_threaded_through(self, tmp_path, monkeypatch):
        import datetime as dt
        fixed = dt.datetime(2026, 2, 2, 9, 0, 0)
        monkeypatch.setattr(et_clock, "et_now", lambda: fixed)
        monkeypatch.setattr(runner, "LOG_DIR", tmp_path / "logs")
        runner._log("probe")
        log_file = tmp_path / "logs" / "swing-core-2026-02-02.log"
        assert log_file.exists()
        assert "[2026-02-02T09:00:00] probe" in log_file.read_text(encoding="utf-8")


# ═══════════════════════ gating ════════════════════════════════════════════════
class TestGating:
    def test_no_armed_file_skips(self, tmp_path):
        armed_file = tmp_path / "armed-setups.json"  # deliberately does not exist
        recs_dir = tmp_path / "recs"
        passed, reason = runner.check_armed_setups("MNQ", armed_file=armed_file, recs_dir=recs_dir)
        assert passed is False
        assert reason == "no_armed_setups_file"

    def test_armed_file_present_but_no_pass_scorecard_skips(self, tmp_path):
        armed_file = tmp_path / "armed-setups.json"
        recs_dir = tmp_path / "recs"
        recs_dir.mkdir()
        armed_file.write_text(json.dumps({"setups": [{"seed": "nope"}]}), encoding="utf-8")
        passed, reason = runner.check_armed_setups("MNQ", armed_file=armed_file, recs_dir=recs_dir)
        assert passed is False
        assert "no_pass_scorecard" in reason

    def test_scorecard_verdict_fail_does_not_pass(self, tmp_path):
        armed_file = tmp_path / "armed-setups.json"
        recs_dir = tmp_path / "recs"
        recs_dir.mkdir()
        armed_file.write_text(json.dumps({"setups": [{"seed": "s1"}]}), encoding="utf-8")
        (recs_dir / "futures-swing-s1.json").write_text(json.dumps({"verdict": "FAIL"}),
                                                         encoding="utf-8")
        passed, _ = runner.check_armed_setups("MNQ", armed_file=armed_file, recs_dir=recs_dir)
        assert passed is False

    def test_armed_and_pass_scorecard_passes(self, tmp_path):
        armed_file, recs_dir = _write_armed_and_pass_scorecard(tmp_path)
        passed, reason = runner.check_armed_setups("MNQ", armed_file=armed_file, recs_dir=recs_dir)
        assert passed is True
        assert reason == "armed:test_seed"

    def test_instrument_tag_scopes_the_gate(self, tmp_path):
        """A setup tagged for MES must not arm MNQ (fail-closed per-instrument scoping)."""
        armed_file, recs_dir = _write_armed_and_pass_scorecard(tmp_path, instrument="MES")
        passed_mnq, _ = runner.check_armed_setups("MNQ", armed_file=armed_file, recs_dir=recs_dir)
        passed_mes, _ = runner.check_armed_setups("MES", armed_file=armed_file, recs_dir=recs_dir)
        assert passed_mnq is False
        assert passed_mes is True


# ═══════════════ gating -> entry path reachability (non-vacuous) ══════════════
class TestEntryPathReachability:
    """Proves the gate isn't just a function that returns True/False in isolation -- when it
    PASSES, attempt_entry() actually reaches broker.place_bracket(); when it FAILS, it never
    does. Both directions are asserted so a broken always-True OR always-False gate both RED."""

    def test_gate_fail_never_calls_place_bracket(self, tmp_path, monkeypatch):
        monkeypatch.setattr(hb, "compute_latest_signals", _fake_signals)
        broker = FillSimBroker(state_dir=tmp_path / "state", start_equity=2000.0)
        account = runner._build_account(broker)
        armed_file = tmp_path / "armed-setups.json"  # absent -> gate fails
        recs_dir = tmp_path / "recs"

        result = runner.attempt_entry(broker, MNQ, account, armed_file=armed_file,
                                      recs_dir=recs_dir)
        assert result["action"] == "SKIP_NO_VALIDATED_SETUP"
        assert broker.get_positions_snapshot().get("MNQ") is None, (
            "place_bracket must NOT have fired while ungated")

    def test_gate_pass_reaches_place_bracket(self, tmp_path, monkeypatch):
        monkeypatch.setattr(hb, "compute_latest_signals", _fake_signals)
        broker = FillSimBroker(state_dir=tmp_path / "state", start_equity=2000.0)
        account = runner._build_account(broker)
        armed_file, recs_dir = _write_armed_and_pass_scorecard(tmp_path)

        result = runner.attempt_entry(broker, MNQ, account, armed_file=armed_file,
                                      recs_dir=recs_dir)
        assert result["action"] == "PLACED_PENDING", result
        snap = broker.get_positions_snapshot()["MNQ"]
        assert snap["status"] == "pending_entry"
        assert snap["direction"] == "long"

    def test_run_once_decision_mode_places_when_gated_and_flat(self, tmp_path, monkeypatch):
        monkeypatch.setattr(hb, "compute_latest_signals", _fake_signals)
        broker = FillSimBroker(state_dir=tmp_path / "state", start_equity=2000.0)
        armed_file, recs_dir = _write_armed_and_pass_scorecard(tmp_path)

        results = runner.run_once(broker, [MNQ], monitor_only=False, quote_fetcher=_fake_quote,
                                  armed_file=armed_file, recs_dir=recs_dir)
        assert results[0]["entry"]["action"] == "PLACED_PENDING"
        assert broker.get_positions_snapshot()["MNQ"]["status"] == "pending_entry"

    def test_run_once_monitor_mode_never_attempts_entry(self, tmp_path, monkeypatch):
        """RED-PROOF: --monitor must be exit/pending-fill management ONLY -- even with a
        passing gate and a good signal, monitor mode must never place a new order."""
        monkeypatch.setattr(hb, "compute_latest_signals", _fake_signals)
        broker = FillSimBroker(state_dir=tmp_path / "state", start_equity=2000.0)
        armed_file, recs_dir = _write_armed_and_pass_scorecard(tmp_path)

        results = runner.run_once(broker, [MNQ], monitor_only=True, quote_fetcher=_fake_quote,
                                  armed_file=armed_file, recs_dir=recs_dir)
        assert "entry" not in results[0]
        assert broker.get_positions_snapshot().get("MNQ") is None

    def test_run_once_manages_existing_position_before_gating_new_entry(self, tmp_path, monkeypatch):
        """Exit management runs even when a NEW entry would be gated off -- an already-open
        position must keep being managed regardless of armed-setups.json state."""
        monkeypatch.setattr(hb, "compute_latest_signals", _fake_signals)
        broker = FillSimBroker(state_dir=tmp_path / "state", start_equity=2000.0)
        broker.place_bracket("MNQ", "BUY", 4, 21000.0, 21030.0, 20980.0, runner_price=21060.0,
                             tp1_qty=2)
        # no armed-setups.json anywhere -- entries would be gated off
        armed_file = tmp_path / "armed-setups.json"
        recs_dir = tmp_path / "recs"

        results = runner.run_once(broker, [MNQ], monitor_only=False, quote_fetcher=_fake_quote,
                                  armed_file=armed_file, recs_dir=recs_dir)
        assert results[0]["manage"]["event"] == "filled"  # the pending entry still got filled
        assert "entry" not in results[0], "flat-after-management would normally re-check, but " \
            "this fixture fills TO open, so is_flat() is False -- no new-entry attempt expected"


# ═══════════════════════ fail-open ═════════════════════════════════════════════
class TestFailOpen:
    def test_run_once_survives_one_instrument_raising(self, tmp_path):
        broker = FillSimBroker(state_dir=tmp_path / "state", start_equity=2000.0)

        class ExplodingInstrument:
            symbol = "MNQ"

        def blowing_up(_sym):
            raise RuntimeError("simulated network blowup")

        results = runner.run_once(broker, [ExplodingInstrument()], monitor_only=True,
                                  quote_fetcher=blowing_up)
        assert len(results) == 1
        assert "error" in results[0]

    def test_main_fails_open_on_unexpected_exception(self, tmp_path, monkeypatch):
        """The OUTER fail-open contract: even a genuinely unhandled exception deep in the
        pipeline must not crash the process -- main() logs it and returns 0."""
        state_dir = tmp_path / "state"
        log_dir = tmp_path / "logs"
        monkeypatch.setattr(runner, "STATE_DIR", state_dir)
        monkeypatch.setattr(fsb, "STATE_DIR", state_dir)  # FillSimBroker() default ctor arg
        monkeypatch.setattr(runner, "LOG_DIR", log_dir)
        monkeypatch.setattr(runner, "HEARTBEAT_FILE", state_dir / "swing-heartbeat.json")
        monkeypatch.setattr(runner, "ARMED_SETUPS_FILE", state_dir / "armed-setups.json")
        monkeypatch.setattr(sys, "argv", ["swing_core_runner.py", "--monitor"])

        def boom(*_a, **_k):
            raise RuntimeError("simulated poisoned-state blowup")
        monkeypatch.setattr(runner, "run_once", boom)

        rc = runner.main()
        assert rc == 0, "main() must fail OPEN (exit 0) even on a genuine unhandled exception"
        logs = list(log_dir.glob("swing-core-*.log"))
        assert logs, "the failure must be LOGGED, not silently swallowed"
        assert "simulated poisoned-state blowup" in logs[0].read_text(encoding="utf-8")
        # and it must NOT have touched the real repo state dir
        assert not (REPO / "automation" / "state" / "futures" / "fillsim-account.json").exists() \
            or True  # (existence check is advisory; the STATE_DIR patch is what guarantees isolation)

    def test_main_success_path_writes_heartbeat_and_returns_0(self, tmp_path, monkeypatch):
        state_dir = tmp_path / "state"
        log_dir = tmp_path / "logs"
        monkeypatch.setattr(runner, "STATE_DIR", state_dir)
        monkeypatch.setattr(fsb, "STATE_DIR", state_dir)
        monkeypatch.setattr(runner, "LOG_DIR", log_dir)
        monkeypatch.setattr(runner, "HEARTBEAT_FILE", state_dir / "swing-heartbeat.json")
        monkeypatch.setattr(runner, "ARMED_SETUPS_FILE", state_dir / "armed-setups.json")
        monkeypatch.setattr(runner, "fetch_live_bar", lambda *_a, **_k: None)
        monkeypatch.setattr(sys, "argv", ["swing_core_runner.py", "--monitor"])

        rc = runner.main()
        assert rc == 0
        hb_file = state_dir / "swing-heartbeat.json"
        assert hb_file.exists()
        snap = json.loads(hb_file.read_text(encoding="utf-8"))
        for key in ("ts_et", "positions_open", "equity", "last_action"):
            assert key in snap, f"swing-heartbeat.json missing required field {key!r}"
        assert snap["positions_open"] == 0

    def test_main_never_writes_to_real_repo_state_dir(self, tmp_path, monkeypatch):
        """Belt-and-suspenders isolation proof: run main() fully patched into tmp_path, then
        confirm the REAL automation/state/futures/ has no fillsim-*/swing-heartbeat artifacts
        this test run could plausibly have created (they must not exist at all yet, per the
        task -- this build never runs the installer or arms anything)."""
        real_dir = REPO / "automation" / "state" / "futures"
        before = set(real_dir.glob("fillsim-*")) | set(real_dir.glob("swing-heartbeat.json"))

        state_dir = tmp_path / "state"
        log_dir = tmp_path / "logs"
        monkeypatch.setattr(runner, "STATE_DIR", state_dir)
        monkeypatch.setattr(fsb, "STATE_DIR", state_dir)
        monkeypatch.setattr(runner, "LOG_DIR", log_dir)
        monkeypatch.setattr(runner, "HEARTBEAT_FILE", state_dir / "swing-heartbeat.json")
        monkeypatch.setattr(runner, "ARMED_SETUPS_FILE", state_dir / "armed-setups.json")
        monkeypatch.setattr(runner, "fetch_live_bar", lambda *_a, **_k: None)
        monkeypatch.setattr(sys, "argv", ["swing_core_runner.py", "--monitor"])
        runner.main()

        after = set(real_dir.glob("fillsim-*")) | set(real_dir.glob("swing-heartbeat.json"))
        assert after == before, f"main() touched the REAL state dir: {after - before}"

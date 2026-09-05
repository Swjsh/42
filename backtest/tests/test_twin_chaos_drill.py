"""Tests for setup/scripts/twin_chaos_drill.py (TWIN-B4, resilience ledger).

Every test here is offline/deterministic ($0, no network, no real broker) --
mirrors test_crypto_twin_core.py's own tmp_path + monkeypatched-broker convention.
Covers the assert/restore logic each drill's real (network-touching) orchestrator
wraps: classify_recovery's decision table, inject/restore-state round-trips,
force_flatten_position, build_tripped_breaker_doc + verify_gate's real
load_breaker->kill_switch.tick->risk_gate chain, and detect_stale_feed's real
run_tick(raw_bars=...) staleness path. Live drills (drill_process_kill's real
subprocess-kill + real broker calls) get one fully-mocked orchestration test proving
the wiring, plus their sub-pieces tested directly above.

ISOLATION (load-bearing, root-caused live 2026-07-15): every `drill_*()` call below
passes an explicit `ledger_path=tmp_path/...` override. The FIRST version of this test
file omitted that and silently wrote real test rows into the production
automation/state/crypto-twin/resilience-ledger.jsonl on every offline pytest run
(cfg's state_dir was tmp_path-isolated, but append_resilience_row's ledger_path defaulted
to the real LEDGER_PATH regardless of cfg) -- caught by inspecting the real ledger after
the FIRST intentional live run tonight and finding fake-broker-shaped rows
("$65,000.00", "no twin creds") interleaved with the genuine ones. Fixed by threading
`ledger_path` through every drill_* function (resolved inside the body, not a bound
default -- see twin_chaos_drill.py's force_flatten_position docstring for the same class
of bug). NEVER remove a `ledger_path=` kwarg from a `drill_*()` call in this file.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", "automation/state/fleet", ""):
    sys.path.insert(0, str(REPO / _p) if _p else str(REPO))

import crypto_twin_core as ctc  # noqa: E402
import exit_manager as em  # noqa: E402
import twin_chaos_drill as tcd  # noqa: E402


def _twin_cfg(tmp_path: Path, **overrides) -> ctc.TwinConfig:
    state_dir = tmp_path / "automation" / "state" / "crypto-twin"
    return ctc.TwinConfig(state_dir=state_dir, **overrides)


_CREDS = {"key": "k", "secret": "s", "base_url": "https://paper-api.alpaca.markets"}


class _FakeBroker:
    """Same shape as test_crypto_twin_core.py's _FakeBroker (reused in spirit, not
    imported -- production test modules don't import each other's fixtures)."""

    def __init__(self):
        self.orders = []
        self.sells = []
        self.closes = []
        self.position_qty = 0.0
        self.quote = (65000.0, 64950.0)

    def get_twin_creds(self, *, verify_crypto_status: bool = True):
        return _CREDS

    def fetch_crypto_bars(self, symbol="BTC/USD", *, granularity_seconds=300, limit=200, creds=None):
        now = datetime.now(timezone.utc)
        return [tcd._raw_bar(now - timedelta(minutes=5 * i), 65000.0, 65010.0, 64990.0, 65000.0)
               for i in range(60, 0, -1)]

    def place_crypto_order(self, creds, *, symbol, side, notional=None, qty=None,
                           order_type="market", limit_price=None, live):
        self.orders.append({"symbol": symbol, "side": side, "qty": qty, "live": live})
        return {"id": "test-order-1", "status": "accepted"}

    def poll_fill(self, creds, order_id, attempts=4, sleep_sec=1.5):
        return {"filled": True, "status": "filled", "filled_qty": self.position_qty,
               "filled_avg_price": 65000.0, "order": {}}

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


@pytest.fixture
def fake_broker(monkeypatch):
    fb = _FakeBroker()
    for name in ("get_twin_creds", "fetch_crypto_bars", "place_crypto_order", "poll_fill",
                "get_crypto_position_qty", "get_crypto_quote_hilo", "market_sell_crypto",
                "close_all_crypto"):
        monkeypatch.setattr(tcd.broker, name, getattr(fb, name))
    return fb


# ============================================================================
# classify_recovery -- the drill 1 decision table (pure, every branch)
# ============================================================================
def test_classify_recovery_consistent_position():
    verdict, path = tcd.classify_recovery(disk_position={"x": 1}, broker_qty=0.002, state_file_valid=True)
    assert (verdict, path) == ("RECOVERED", "STATE_CONSISTENT_WITH_BROKER")


def test_classify_recovery_closed_cleanly():
    verdict, path = tcd.classify_recovery(disk_position=None, broker_qty=0.0, state_file_valid=True)
    assert (verdict, path) == ("RECOVERED", "POSITION_CLOSED_CLEANLY")


def test_classify_recovery_broker_flat_pending_prune():
    verdict, path = tcd.classify_recovery(disk_position={"x": 1}, broker_qty=0.0, state_file_valid=True)
    assert (verdict, path) == ("RECOVERED", "BROKER_FLAT_PENDING_PRUNE")


def test_classify_recovery_orphaned_position_is_an_incident():
    verdict, path = tcd.classify_recovery(disk_position=None, broker_qty=0.002, state_file_valid=True)
    assert (verdict, path) == ("INCIDENT", "ORPHANED_POSITION_NO_RECORD")


def test_classify_recovery_corrupt_state_file_is_an_incident_regardless_of_broker():
    verdict, path = tcd.classify_recovery(disk_position={"x": 1}, broker_qty=0.002, state_file_valid=False)
    assert (verdict, path) == ("INCIDENT", "STATE_FILE_CORRUPTED_ON_KILL")


def test_classify_recovery_dust_below_epsilon_is_not_an_incident():
    """2026-09-05 RESILIENCE-LEDGER-DUST-RECONCILIATION: 9e-09 BTC is the exact float-
    noise magnitude two real 2026-08-16/08-23 drill reps left behind after a full
    sell-to-flat -- it must classify as closed-cleanly, not ORPHANED_POSITION_NO_RECORD."""
    verdict, path = tcd.classify_recovery(disk_position=None, broker_qty=9e-9, state_file_valid=True)
    assert (verdict, path) == ("RECOVERED", "POSITION_CLOSED_CLEANLY")


def test_classify_recovery_real_qty_above_epsilon_is_still_an_incident():
    """The dust floor must not swallow a genuine orphan -- 0.002 BTC (a real unit-sized
    qty, same value the pre-existing consistent-position test uses) stays an INCIDENT."""
    verdict, path = tcd.classify_recovery(disk_position=None, broker_qty=0.002, state_file_valid=True)
    assert (verdict, path) == ("INCIDENT", "ORPHANED_POSITION_NO_RECORD")
    assert 0.002 > tcd.ctc.DUST_EPSILON_BTC  # sanity: the fixture value really is above the floor


# ============================================================================
# ledger writer
# ============================================================================
def test_append_resilience_row_writes_jsonl(tmp_path):
    ledger = tmp_path / "resilience-ledger.jsonl"
    row = tcd._ledger_row("stale_feed", injected_at="2026-07-15T00:00:00+00:00",
                          recovered=True, recovery_path="N/A", notes="ok")
    tcd.append_resilience_row(row, ledger_path=ledger)
    tcd.append_resilience_row(row, ledger_path=ledger)
    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    parsed = json.loads(lines[0])
    assert parsed["drill"] == "stale_feed"
    assert parsed["recovered"] is True
    assert set(parsed) == {"drill", "injected_at", "observed_at", "recovered", "recovery_path",
                           "notes", "evidence"}


# ============================================================================
# atomic write + inject/restore state round-trip (drill 2's core)
# ============================================================================
def test_atomic_write_text_creates_file(tmp_path):
    p = tmp_path / "sub" / "f.json"
    tcd._atomic_write_text(p, '{"a": 1}')
    assert p.read_text(encoding="utf-8") == '{"a": 1}'


def test_inject_corrupt_state_snapshots_and_overwrites(tmp_path):
    p = tmp_path / "exit-state.json"
    p.write_text('{"BTC/USD": {"fake": true}}', encoding="utf-8")
    original = tcd.inject_corrupt_state(p)
    assert original == '{"BTC/USD": {"fake": true}}'
    assert p.read_text(encoding="utf-8").startswith("{not valid json")
    with pytest.raises(json.JSONDecodeError):
        json.loads(p.read_text(encoding="utf-8"))


def test_inject_corrupt_state_missing_file_snapshots_empty_string(tmp_path):
    p = tmp_path / "exit-state.json"
    original = tcd.inject_corrupt_state(p)
    assert original == ""
    assert p.exists()


def test_restore_state_round_trips_exact_bytes(tmp_path):
    p = tmp_path / "exit-state.json"
    original = tcd.inject_corrupt_state(p)  # missing -> "" snapshot, malformed written
    tcd.restore_state(p, original)
    assert p.read_text(encoding="utf-8") == "{}"  # empty-string snapshot restores to {}


def test_restore_state_round_trips_real_original_content(tmp_path):
    p = tmp_path / "exit-state.json"
    p.write_text('{"BTC/USD": {"real": "record"}}', encoding="utf-8")
    original = tcd.inject_corrupt_state(p)
    tcd.restore_state(p, original)
    assert p.read_text(encoding="utf-8") == '{"BTC/USD": {"real": "record"}}'


def test_check_fail_safe_load_true_on_missing_file(tmp_path):
    cfg = _twin_cfg(tmp_path)
    assert tcd.check_fail_safe_load(cfg) is True


def test_check_fail_safe_load_true_on_malformed_json(tmp_path):
    cfg = _twin_cfg(tmp_path)
    (cfg.state_dir / "exit-state.json").parent.mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / "exit-state.json").write_text("{not valid json", encoding="utf-8")
    assert tcd.check_fail_safe_load(cfg) is True  # fail-open, never raises


def test_check_fail_safe_load_reflects_valid_content(tmp_path):
    cfg = _twin_cfg(tmp_path)
    (cfg.state_dir / "exit-state.json").parent.mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / "exit-state.json").write_text('{"BTC/USD": {"x": 1}}', encoding="utf-8")
    assert tcd.check_fail_safe_load(cfg) is False  # a REAL position -- correctly NOT {}


def test_drill_corrupt_state_no_account_restores_exact_bytes_and_never_crashes(tmp_path, monkeypatch, fake_broker):
    """No-creds branch (forces live=False downstream) -- still fully exercises fail-open
    load + one real tick + byte-exact restore, entirely offline via fake_broker."""
    cfg = _twin_cfg(tmp_path)
    monkeypatch.setattr(tcd.broker, "get_twin_creds", lambda **kw: (_ for _ in ()).throw(FileNotFoundError("no twin creds")))
    (cfg.state_dir).mkdir(parents=True, exist_ok=True)
    original_text = '{"BTC/USD": {"real": "record"}}'
    (cfg.state_dir / "exit-state.json").write_text(original_text, encoding="utf-8")

    row = tcd.drill_corrupt_state(cfg, ledger_path=tmp_path / "resilience-ledger.jsonl")

    assert row["drill"] == "corrupt_state_file"
    assert row["recovered"] is True
    assert (cfg.state_dir / "exit-state.json").read_text(encoding="utf-8") == original_text
    assert row["evidence"]["fail_safe_ok"] is True
    assert row["evidence"]["tick_error"] is None


# ============================================================================
# force_flatten_position (drill 1's restore step)
# ============================================================================
def _seed_open_position(cfg, *, entry_premium=65000.0):
    st = em.ExitState.from_entry(symbol=cfg.symbol, side="C", entry_premium=entry_premium,
                                 qty=cfg.units_per_entry, exit_shape=cfg.exit_shape,
                                 strategy="test", trigger_level=None, structure_stop_enabled=True)
    positions = {cfg.symbol: {"exit_state": st.to_dict(),
                              "entered_at_utc": datetime.now(timezone.utc).isoformat(),
                              "side": "bull", "order_id": "seed", "scenario": "TEST_SEED"}}
    ctc._save_positions(cfg, positions)


def test_force_flatten_position_closes_and_journals(tmp_path, fake_broker):
    cfg = _twin_cfg(tmp_path)
    _seed_open_position(cfg)
    fake_broker.position_qty = ctc.entry_qty_btc(cfg)

    res = tcd.force_flatten_position(cfg, _CREDS)

    assert res is not None
    assert fake_broker.closes == [{"symbol": cfg.symbol, "live": True}]
    assert ctc.get_open_position(cfg) is None
    journal = (cfg.state_dir / "journal.jsonl").read_text(encoding="utf-8")
    assert '"reason": "chaos_drill_restore"' in journal


def test_force_flatten_position_noop_when_already_flat(tmp_path, fake_broker):
    cfg = _twin_cfg(tmp_path)
    res = tcd.force_flatten_position(cfg, _CREDS)
    assert res is None
    assert not fake_broker.closes
    assert not (cfg.state_dir / "journal.jsonl").exists()


def test_force_flatten_position_uses_injected_close_fn(tmp_path):
    cfg = _twin_cfg(tmp_path)
    _seed_open_position(cfg)
    calls = []

    def fake_close(creds, *, symbol, live):
        calls.append((symbol, live))
        return {"id": "injected-close", "status": "accepted"}

    res = tcd.force_flatten_position(cfg, _CREDS, close_fn=fake_close)
    assert res == {"id": "injected-close", "status": "accepted"}
    assert calls == [(cfg.symbol, True)]
    assert ctc.get_open_position(cfg) is None


# ============================================================================
# detect_stale_feed / drill_stale_feed (drill 3) -- fully offline, raw_bars injected
# ============================================================================
def test_detect_stale_feed_flags_a_stale_bar(tmp_path):
    # TWIN-TS-UTC-DRIFT-PRODUCER (2026-09-03 root cause): this test used to construct a
    # BARE ctc.TwinConfig(), whose state_dir defaults to the REAL production TWIN_DIR
    # (automation/state/crypto-twin/). run_tick(live=False) still calls log_decision on
    # every tick regardless of `live` -- the old inline comment's "never writes" was
    # wrong about that -- so every run of this test appended a real HOLD_BAD_BARS row to
    # the PRODUCTION decisions.jsonl carrying this test's hardcoded now=2026-07-15T04:00
    # as ts_utc (ts_et stayed fresh via et_now()'s real wall clock), exactly matching the
    # frozen-ts_utc rows queue.md's TWIN-TS-UTC-DRIFT-PRODUCER tracked from 2026-07-15
    # through 2026-09-03 -- reproduced live this session (28469 -> 28470 lines, new row
    # byte-identical to the historical pattern). Fixed by isolating state_dir via
    # _twin_cfg(tmp_path), matching every other test in this file.
    now = datetime(2026, 7, 15, 4, 0, tzinfo=timezone.utc)
    cfg = _twin_cfg(tmp_path)
    detected, row = tcd.detect_stale_feed(cfg, now_utc=now, stale_hours=3.0)
    assert detected is True
    assert row["action"] == "HOLD_BAD_BARS"
    # Regression guard: prove the row landed in the ISOLATED decisions.jsonl, never the
    # real production path (mirrors the isolation assertion drill_stale_feed's own
    # end-to-end test already makes for resilience-ledger.jsonl below).
    assert (cfg.state_dir / "decisions.jsonl").exists()
    assert cfg.state_dir != ctc.TWIN_DIR


def test_detect_stale_feed_never_places_an_order(tmp_path):
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 15, 4, 0, tzinfo=timezone.utc)
    detected, row = tcd.detect_stale_feed(cfg, now_utc=now, stale_hours=3.0)
    assert detected is True
    journal_path = cfg.state_dir / "journal.jsonl"
    assert not journal_path.exists() or '"event": "PLACED"' not in journal_path.read_text(encoding="utf-8")


def test_drill_stale_feed_end_to_end_offline(tmp_path):
    cfg = _twin_cfg(tmp_path)
    ledger = tmp_path / "resilience-ledger.jsonl"
    row = tcd.drill_stale_feed(cfg, ledger_path=ledger)
    assert row["drill"] == "stale_feed"
    assert row["recovered"] is True
    assert row["evidence"]["action"] == "HOLD_BAD_BARS"
    assert row["evidence"]["placed_before"] == row["evidence"]["placed_after"] == 0
    # Isolation guarantee: the row landed in the INJECTED ledger, never the real
    # production path (LEDGER_PATH must stay untouched by any offline test run --
    # see this module's own header docstring, root-caused live 2026-07-15).
    assert ledger.exists()
    assert json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])["drill"] == "stale_feed"
    assert ledger != tcd.LEDGER_PATH


# ============================================================================
# build_tripped_breaker_doc + verify_gate (drill 4) -- fully offline, no network
# ============================================================================
def test_build_tripped_breaker_doc_no_original_uses_starting_equity():
    cfg = ctc.TwinConfig(starting_equity=2000.0, daily_loss_kill_switch_pct=0.30)
    now = datetime(2026, 7, 15, 4, 0, tzinfo=timezone.utc)
    doc = tcd.build_tripped_breaker_doc(None, cfg, now)
    assert doc["tripped"] is True
    assert doc["start_of_day_equity"] == 2000.0
    assert doc["current_equity"] == 2000.0  # healthy -- isolates the LATCH, not a real drawdown
    assert doc["tripped_at_equity"] == pytest.approx(1400.0)


def test_build_tripped_breaker_doc_carries_forward_same_day_sod():
    cfg = ctc.TwinConfig(starting_equity=2000.0, daily_loss_kill_switch_pct=0.30)
    now = datetime(2026, 7, 15, 4, 0, tzinfo=timezone.utc)
    original = {"utc_date": "2026-07-15", "start_of_day_equity": 9975.71, "tripped": False}
    doc = tcd.build_tripped_breaker_doc(original, cfg, now)
    assert doc["start_of_day_equity"] == 9975.71


def test_build_tripped_breaker_doc_ignores_stale_day_original():
    cfg = ctc.TwinConfig(starting_equity=2000.0, daily_loss_kill_switch_pct=0.30)
    now = datetime(2026, 7, 15, 4, 0, tzinfo=timezone.utc)
    original = {"utc_date": "2026-07-14", "start_of_day_equity": 9975.71, "tripped": False}
    doc = tcd.build_tripped_breaker_doc(original, cfg, now)
    assert doc["start_of_day_equity"] == 2000.0  # yesterday's SOD is stale -> fresh default


def test_verify_gate_blocks_when_breaker_json_is_tripped(tmp_path):
    cfg = _twin_cfg(tmp_path, starting_equity=2000.0, daily_loss_kill_switch_pct=0.30)
    now = datetime(2026, 7, 15, 4, 0, tzinfo=timezone.utc)
    tripped_doc = tcd.build_tripped_breaker_doc(None, cfg, now)
    (cfg.state_dir).mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / "breaker.json").write_text(json.dumps(tripped_doc), encoding="utf-8")

    blocked, evidence = tcd.verify_gate(cfg, now_utc=now)

    assert blocked is True
    assert evidence["risk_gate_code"] == "KILL_SWITCH"
    assert evidence["ticked_tripped"] is True


def test_verify_gate_allows_when_breaker_json_is_untripped(tmp_path):
    cfg = _twin_cfg(tmp_path, starting_equity=2000.0, daily_loss_kill_switch_pct=0.30)
    now = datetime(2026, 7, 15, 4, 0, tzinfo=timezone.utc)
    (cfg.state_dir).mkdir(parents=True, exist_ok=True)
    untripped = {"utc_date": "2026-07-15", "account_id": cfg.account_label,
                "start_of_day_equity": 2000.0, "current_equity": 2000.0,
                "threshold_pct": 0.30, "tripped": False, "tripped_at_equity": None,
                "min_equity_seen": 2000.0}
    (cfg.state_dir / "breaker.json").write_text(json.dumps(untripped), encoding="utf-8")

    blocked, evidence = tcd.verify_gate(cfg, now_utc=now)

    assert blocked is False
    assert evidence["risk_gate_code"] == "ALLOW"


def test_drill_breaker_trip_restores_original_bytes_exactly_and_recovers(tmp_path):
    cfg = _twin_cfg(tmp_path, starting_equity=2000.0, daily_loss_kill_switch_pct=0.30)
    (cfg.state_dir).mkdir(parents=True, exist_ok=True)
    original = {"utc_date": "2026-07-15", "account_id": cfg.account_label,
               "start_of_day_equity": 2000.0, "current_equity": 1987.5,
               "threshold_pct": 0.30, "tripped": False, "tripped_at_equity": None,
               "min_equity_seen": 1987.5}
    original_text = json.dumps(original, indent=2)
    breaker_path = cfg.state_dir / "breaker.json"
    breaker_path.write_text(original_text, encoding="utf-8")

    row = tcd.drill_breaker_trip(cfg, ledger_path=tmp_path / "resilience-ledger.jsonl")

    assert row["drill"] == "breaker_mid_trip"
    assert row["recovered"] is True
    assert breaker_path.read_text(encoding="utf-8") == original_text
    assert row["evidence"]["halt_check"]["risk_gate_code"] == "KILL_SWITCH"
    assert row["evidence"]["rearm_check"]["risk_gate_code"] == "ALLOW"


def test_drill_breaker_trip_from_fresh_account_still_restores_and_recovers(tmp_path):
    """No pre-existing breaker.json at all (first-ever run) -- inject_corrupt_state's
    sibling 'missing file' edge case, exercised here via drill_breaker_trip directly."""
    cfg = _twin_cfg(tmp_path, starting_equity=2000.0, daily_loss_kill_switch_pct=0.30)
    row = tcd.drill_breaker_trip(cfg, ledger_path=tmp_path / "resilience-ledger.jsonl")
    assert row["recovered"] is True
    assert not (cfg.state_dir / "breaker.json").exists() or True  # restore_state writes "{}" back when nothing existed
    breaker_path = cfg.state_dir / "breaker.json"
    assert breaker_path.exists()
    assert breaker_path.read_text(encoding="utf-8") == "{}"


# ============================================================================
# drill_process_kill -- fully mocked orchestration (real subprocess creation avoided
# via injectable popen_fn; real broker avoided via fake_broker)
# ============================================================================
class _FakeKilledProcess:
    """Simulates: launched, ran past the drill's `kill_after_sec` timeout (never
    exited on its own), forcefully killed."""

    def __init__(self, *a, **kw):
        self.killed = False
        self._waits = 0

    def wait(self, timeout=None):
        self._waits += 1
        if self._waits == 1:
            raise subprocess.TimeoutExpired(cmd="crypto_twin_health.py", timeout=timeout)
        return 0

    def kill(self):
        self.killed = True


def test_drill_process_kill_full_orchestration_recovers_and_restores(tmp_path, monkeypatch, fake_broker):
    cfg = _twin_cfg(tmp_path)
    monkeypatch.setattr(tcd, "cth", tcd.cth)  # sanity: module attr exists

    def fake_popen(cmd, **kw):
        return _FakeKilledProcess()

    row = tcd.drill_process_kill(cfg, kill_after_sec=0.01, popen_fn=fake_popen,
                                 ledger_path=tmp_path / "resilience-ledger.jsonl")

    assert row["drill"] == "process_kill_mid_position"
    assert row["evidence"]["killed_before_completion"] is True
    assert row["recovered"] is True
    assert row["recovery_path"] in ("STATE_CONSISTENT_WITH_BROKER", "POSITION_CLOSED_CLEANLY",
                                    "BROKER_FLAT_PENDING_PRUNE")
    # RESTORE guarantee: the drill must never leave a real position open.
    assert ctc.get_open_position(cfg) is None
    assert fake_broker.position_qty == 0.0


def test_drill_process_kill_skips_when_already_open(tmp_path, fake_broker):
    cfg = _twin_cfg(tmp_path)
    _seed_open_position(cfg)
    row = tcd.drill_process_kill(cfg, ledger_path=tmp_path / "resilience-ledger.jsonl")
    assert row["recovered"] is None
    assert row["recovery_path"] == "SKIPPED_POSITION_ALREADY_OPEN"
    # Precondition drill must NEVER touch a pre-existing position.
    assert ctc.get_open_position(cfg) is not None

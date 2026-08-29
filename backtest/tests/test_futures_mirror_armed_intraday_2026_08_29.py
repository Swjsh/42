"""Guards for the 2026-08-29 futures_mirror_shadow.py armed-leg risk fix.

WHY THIS EXISTS: the ARMED leg (MIRROR_ARMED=1, the live scheduled task's --armed flag)
inherited this module's 2-SESSION shadow horizon with no flatten path of its own -- entry +
TP1 + stop were placed as GTC broker orders on the real Tastytrade sandbox and simply left to
ride past the CME settlement/maintenance stop if neither filled by session end. Per
markdown/futures/MARGIN-LEVERAGE-RISK.md, holding a real futures position past that cutoff
snaps the full overnight margin back and can trigger auto-liquidation on this $2K account.
The fix makes the armed leg INTRADAY-ONLY (flatten via FuturesRiskRails.must_flatten, refuse
new entries in the maintenance-BLOCK window) while the would-be shadow ledger's ORIGINAL
2-session spec stays untouched -- these guards pin both halves of that split, plus the
`armed_spec` label that keeps the two ledgers from ever being conflated.

All broker interaction is faked (no network, no real orders); all file writes land under
tmp_path via the existing `_isolate_state` autouse fixture in test_futures_mirror_shadow.py's
sibling pattern (redeclared here since this is its own test module).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest", "setup/scripts"):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

import futures_mirror_shadow as fms  # noqa: E402

# Thursday (Mon-Thu are CME maintenance days) -- reuses the same calendar date as the
# pre-existing armed-execution tests in test_futures_mirror_shadow.py for consistency.
THU = dt.date(2026, 8, 20)
assert THU.weekday() == 3  # Thursday -- sanity-pin the fixture date itself

FLATTEN_WINDOW_ET = dt.datetime.combine(THU, dt.time(16, 55))   # 5m to 17:00 -> inside the
                                                                  # 10m MINUTES_BEFORE_
                                                                  # MAINTENANCE_FLATTEN window
BLOCK_ONLY_ET = dt.datetime.combine(THU, dt.time(16, 35))        # 25m to 17:00 -> inside the
                                                                  # 30m BLOCK window but
                                                                  # outside the 10m flatten one
NORMAL_ET = dt.datetime.combine(THU, dt.time(10, 0))              # well outside both windows


@pytest.fixture(autouse=True)
def _isolate_state(monkeypatch, tmp_path):
    """Same isolation shape as test_futures_mirror_shadow.py's own fixture -- redirect every
    state path this module writes to a tmp dir, and hard-reset the two env vars the armed
    leg reads/sets so no test can leak MIRROR_ARMED/FUTURES_ARMED into another test."""
    state_dir = tmp_path / "futures"
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(fms, "STATE_DIR", state_dir)
    monkeypatch.setattr(fms, "LOG_DIR", log_dir)
    monkeypatch.setattr(fms, "WATERMARK_FILE", state_dir / "mirror-shadow-state.json")
    monkeypatch.setattr(fms, "POSITIONS_FILE", state_dir / "mirror-positions.json")
    monkeypatch.setattr(fms, "WOULD_BE_FILE", state_dir / "mirror-would-be.jsonl")
    monkeypatch.setattr(fms, "CALENDAR_FILE", tmp_path / "does-not-exist-calendar.json")
    monkeypatch.setattr(fms, "CORE_LEDGER", tmp_path / "does-not-exist-core-decisions.jsonl")
    monkeypatch.setattr(fms, "BROKER_ORDERS_FILE", state_dir / "mirror-broker-orders.jsonl")
    monkeypatch.delenv("MIRROR_ARMED", raising=False)
    monkeypatch.delenv("FUTURES_ARMED", raising=False)


def _write_decisions(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _enter_row(ts_et: str, arm_id: str, action: str = "ENTER_BEAR", side: str = "P",
              setup_name: str = "BEARISH_REJECTION_RIDE_THE_RIBBON") -> dict:
    return {"tick_id": None, "ts_et": ts_et, "arm_id": arm_id, "action": action,
           "side": side, "setup_name": setup_name, "strike": 731, "qty": 4}


def _sig_and_pos(direction="long", now_et=NORMAL_ET, ref_suffix="10:00"):
    sig = {"signal_ref": f"{direction}|2026-08-20T{ref_suffix}", "direction": direction,
          "source_arms": ["safe-1"], "setup_name": "TEST"}
    pos = fms.open_mirror_position(sig, entry_price=6000.0, atr=5.0, now_et=now_et)
    return sig, pos


class _FakeBroker:
    """Duck-typed TastytradeBroker stand-in covering both the entry path (connect/is_flat/
    get_account_equity/place_bracket) and the flatten path (get_positions/cancel_all/
    close_position) this fix adds."""

    def __init__(self, *, connected=True, flat=True, equity=2000.0,
                position: dict | None = None, raise_on_close: bool = False):
        self._connected = connected
        self._flat = flat
        self._equity = equity
        self._position = position   # e.g. {"symbol": "MESZ9", "qty": 2, "avg_cost": 6000.0}
        self._raise_on_close = raise_on_close
        self.bracket_calls: list[tuple] = []
        self.cancel_all_calls: list[str] = []
        self.close_position_calls: list[tuple] = []

    def connect(self):
        return self._connected

    def is_flat(self, instrument):
        return self._flat

    def get_account_equity(self):
        return self._equity

    def get_positions(self):
        return [self._position] if self._position else []

    def cancel_all(self, instrument):
        self.cancel_all_calls.append(instrument)
        return True

    def close_position(self, instrument, qty, side, price):
        if self._raise_on_close:
            raise RuntimeError("simulated broker close failure")
        self.close_position_calls.append((instrument, qty, side, price))
        return True

    def place_bracket(self, instrument, side, qty, entry_price, tp1_price, stop_price,
                      runner_price=None, tp1_qty=None):
        self.bracket_calls.append((instrument, side, qty, entry_price, tp1_price, stop_price))
        return ["order-1", "order-2", "order-3"]


# ═══════════════════════ 1. flatten fires inside the flatten window ═══════════════════════
class TestArmedMaintenanceFlatten:
    def test_open_position_inside_flatten_window_is_closed_and_logged(self, monkeypatch):
        fake = _FakeBroker(connected=True, flat=False,
                          position={"symbol": "MESZ9", "qty": 2, "avg_cost": 6000.0})
        monkeypatch.setenv("MIRROR_ARMED", "1")
        import futures.futures_trader_core as ftc
        monkeypatch.setattr(ftc, "make_broker", lambda backend: fake)

        row = fms._broker_maintenance_flatten(FLATTEN_WINDOW_ET, quote_fetcher=lambda: 5990.0)

        assert row is not None
        assert row["action"] == "ARMED_MAINTENANCE_FLATTEN"
        assert row["armed_spec"] == fms.ARMED_SPEC
        assert fake.cancel_all_calls == [fms.ARM_INSTRUMENT]
        assert len(fake.close_position_calls) == 1
        instrument, qty, side, price = fake.close_position_calls[0]
        assert instrument == fms.ARM_INSTRUMENT
        assert qty == 2
        assert side == "SELL"          # long 2 -> closing side is SELL
        assert price == 5990.0
        # journaled to the BROKER ledger, never the shadow ledger
        assert fms.BROKER_ORDERS_FILE.exists()
        rows = [json.loads(l) for l in
               fms.BROKER_ORDERS_FILE.read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 1
        assert rows[0]["action"] == "ARMED_MAINTENANCE_FLATTEN"
        assert rows[0]["armed_spec"] == "intraday_only_v1"
        assert not fms.WOULD_BE_FILE.exists()

    def test_flat_broker_inside_flatten_window_is_a_silent_noop(self, monkeypatch):
        """Nothing to flatten -> no event, no row (a no-op is not evidence worth logging)."""
        fake = _FakeBroker(connected=True, flat=True)
        monkeypatch.setenv("MIRROR_ARMED", "1")
        import futures.futures_trader_core as ftc
        monkeypatch.setattr(ftc, "make_broker", lambda backend: fake)

        row = fms._broker_maintenance_flatten(FLATTEN_WINDOW_ET)

        assert row is None
        assert not fms.BROKER_ORDERS_FILE.exists()
        assert fake.close_position_calls == []

    def test_not_armed_is_a_noop(self, monkeypatch):
        """MIRROR_ARMED unset -- zero behavior change, zero broker calls."""
        fake = _FakeBroker(connected=True, flat=False,
                          position={"symbol": "MESZ9", "qty": 1, "avg_cost": 6000.0})
        import futures.futures_trader_core as ftc
        monkeypatch.setattr(ftc, "make_broker", lambda backend: fake)

        row = fms._broker_maintenance_flatten(FLATTEN_WINDOW_ET)

        assert row is None
        assert fake.close_position_calls == []
        assert not fms.BROKER_ORDERS_FILE.exists()


# ═══════════════════════ 2. new entries refused inside the BLOCK window ═══════════════════
class TestArmedEntryBlockedNearMaintenance:
    def test_new_entry_refused_inside_block_window_no_bracket_placed(self, monkeypatch):
        fake = _FakeBroker(connected=True, flat=True, equity=2000.0)
        monkeypatch.setenv("MIRROR_ARMED", "1")
        import futures.futures_trader_core as ftc
        monkeypatch.setattr(ftc, "make_broker", lambda backend: fake)

        sig, pos = _sig_and_pos("long", now_et=BLOCK_ONLY_ET, ref_suffix="16:35")
        result = fms._broker_execute_entry(sig, pos, BLOCK_ONLY_ET)

        assert result["placed"] is False
        assert result["skipped"] == "session_window"   # rails.check_session_window's rail name
        assert result["armed_spec"] == fms.ARMED_SPEC
        assert fake.bracket_calls == []

    def test_flatten_check_itself_does_not_place_a_new_entry(self, monkeypatch):
        """The flatten function is entry-blind by construction -- it never calls
        place_bracket regardless of window, proving Task 1 and Task 2 are properly separated
        (flatten only ever closes; it never opens)."""
        fake = _FakeBroker(connected=True, flat=False,
                          position={"symbol": "MESZ9", "qty": 1, "avg_cost": 6000.0})
        monkeypatch.setenv("MIRROR_ARMED", "1")
        import futures.futures_trader_core as ftc
        monkeypatch.setattr(ftc, "make_broker", lambda backend: fake)

        fms._broker_maintenance_flatten(BLOCK_ONLY_ET, quote_fetcher=lambda: 6000.0)

        assert fake.bracket_calls == []


# ═══════════════════════ 3. normal-window entries are unaffected (no regression) ══════════
class TestNormalWindowEntryUnaffected:
    def test_entry_outside_both_windows_still_places_bracket(self, monkeypatch):
        fake = _FakeBroker(connected=True, flat=True, equity=2000.0)
        monkeypatch.setenv("MIRROR_ARMED", "1")
        import futures.futures_trader_core as ftc
        monkeypatch.setattr(ftc, "make_broker", lambda backend: fake)

        sig, pos = _sig_and_pos("long", now_et=NORMAL_ET, ref_suffix="10:00")
        result = fms._broker_execute_entry(sig, pos, NORMAL_ET)

        assert result["placed"] is True
        assert result["armed_spec"] == fms.ARMED_SPEC
        assert len(fake.bracket_calls) == 1

    def test_flatten_check_is_a_noop_outside_maintenance_window(self, monkeypatch):
        fake = _FakeBroker(connected=True, flat=False,
                          position={"symbol": "MESZ9", "qty": 1, "avg_cost": 6000.0})
        monkeypatch.setenv("MIRROR_ARMED", "1")
        import futures.futures_trader_core as ftc
        monkeypatch.setattr(ftc, "make_broker", lambda backend: fake)

        row = fms._broker_maintenance_flatten(NORMAL_ET)

        assert row is None
        assert fake.close_position_calls == []

    def test_run_once_full_poll_unaffected_outside_maintenance_window(self, tmp_path, monkeypatch):
        """Integration: run_once() at a normal RTH-adjacent time still opens shadow + broker
        rows exactly as before this fix -- the new flatten step is a true no-op here."""
        fake = _FakeBroker(connected=True, flat=True, equity=2000.0)
        monkeypatch.setenv("MIRROR_ARMED", "1")
        import futures.futures_trader_core as ftc
        monkeypatch.setattr(ftc, "make_broker", lambda backend: fake)

        p = tmp_path / "safe-1" / "decisions.jsonl"
        _write_decisions(p, [_enter_row("2026-06-01T10:05:00-04:00", "safe-1")])
        fms.run_once(now_et=dt.datetime(2026, 8, 20, 10, 0, 0),
                    quote_fetcher=lambda: 6000.0, atr_fetcher=lambda: 5.0, fleet_files=[p])

        _write_decisions(p, [_enter_row("2026-08-20T10:00:00-04:00", "safe-1")])
        summary = fms.run_once(now_et=dt.datetime(2026, 8, 20, 10, 5, 0),
                               quote_fetcher=lambda: 6000.0, atr_fetcher=lambda: 5.0,
                               fleet_files=[p])

        assert summary["opened"] == 1
        assert summary["errors"] == []
        assert len(fake.bracket_calls) == 1
        assert fake.close_position_calls == []


# ═══════════════════════ 4. every armed row carries armed_spec ═══════════════════════════
class TestArmedSpecLabel:
    def test_placed_row_carries_armed_spec(self, monkeypatch):
        fake = _FakeBroker(connected=True, flat=True, equity=2000.0)
        monkeypatch.setenv("MIRROR_ARMED", "1")
        import futures.futures_trader_core as ftc
        monkeypatch.setattr(ftc, "make_broker", lambda backend: fake)
        sig, pos = _sig_and_pos()
        result = fms._broker_execute_entry(sig, pos, NORMAL_ET)
        assert result["armed_spec"] == "intraday_only_v1"

    def test_no_stack_skip_row_carries_armed_spec(self, monkeypatch):
        fake = _FakeBroker(connected=True, flat=False, equity=2000.0)
        monkeypatch.setenv("MIRROR_ARMED", "1")
        import futures.futures_trader_core as ftc
        monkeypatch.setattr(ftc, "make_broker", lambda backend: fake)
        sig, pos = _sig_and_pos()
        result = fms._broker_execute_entry(sig, pos, NORMAL_ET)
        assert result["skipped"] == "position_open_no_stack"
        assert result["armed_spec"] == fms.ARMED_SPEC

    def test_broker_construction_error_row_carries_armed_spec(self, monkeypatch):
        monkeypatch.setenv("MIRROR_ARMED", "1")
        import futures.futures_trader_core as ftc

        def _boom(backend):
            raise RuntimeError("simulated broker construction failure")

        monkeypatch.setattr(ftc, "make_broker", _boom)
        sig, pos = _sig_and_pos()
        result = fms._broker_execute_entry(sig, pos, NORMAL_ET)
        assert "error" in result
        assert result["armed_spec"] == fms.ARMED_SPEC

    def test_flatten_row_carries_armed_spec(self, monkeypatch):
        fake = _FakeBroker(connected=True, flat=False,
                          position={"symbol": "MESZ9", "qty": 1, "avg_cost": 6000.0})
        monkeypatch.setenv("MIRROR_ARMED", "1")
        import futures.futures_trader_core as ftc
        monkeypatch.setattr(ftc, "make_broker", lambda backend: fake)
        row = fms._broker_maintenance_flatten(FLATTEN_WINDOW_ET, quote_fetcher=lambda: 6000.0)
        assert row["armed_spec"] == fms.ARMED_SPEC


# ═══════════════════════ 5. broker failure during flatten is logged, never raised ═════════
class TestFlattenFailsOpen:
    def test_close_position_exception_is_logged_not_raised(self, monkeypatch):
        fake = _FakeBroker(connected=True, flat=False,
                          position={"symbol": "MESZ9", "qty": 2, "avg_cost": 6000.0},
                          raise_on_close=True)
        monkeypatch.setenv("MIRROR_ARMED", "1")
        import futures.futures_trader_core as ftc
        monkeypatch.setattr(ftc, "make_broker", lambda backend: fake)

        row = fms._broker_maintenance_flatten(FLATTEN_WINDOW_ET, quote_fetcher=lambda: 6000.0)

        assert row is not None
        assert "error" in row
        assert "simulated broker close failure" in row["error"]
        assert row["armed_spec"] == fms.ARMED_SPEC
        # still journaled -- a failure must be logged, never silently dropped
        rows = [json.loads(l) for l in
               fms.BROKER_ORDERS_FILE.read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 1 and "error" in rows[0]

    def test_run_once_survives_a_flatten_exception(self, monkeypatch, tmp_path):
        """The poll itself must never crash even when the flatten sub-step raises internally
        (belt-and-braces outer catch in run_once around _broker_maintenance_flatten)."""
        fake = _FakeBroker(connected=True, flat=False,
                          position={"symbol": "MESZ9", "qty": 1, "avg_cost": 6000.0},
                          raise_on_close=True)
        monkeypatch.setenv("MIRROR_ARMED", "1")
        import futures.futures_trader_core as ftc
        monkeypatch.setattr(ftc, "make_broker", lambda backend: fake)

        summary = fms.run_once(now_et=FLATTEN_WINDOW_ET, quote_fetcher=lambda: 6000.0,
                               atr_fetcher=lambda: 5.0, fleet_files=[])
        # run_once must complete and return a summary dict -- never raise.
        assert isinstance(summary, dict)


# ═══════════════════════ 6. the would-be shadow path is untouched (anti-corruption) ═══════
class TestShadowLedgerUntouchedByArmedFlatten:
    def test_shadow_2session_deadline_unchanged_by_armed_flatten_addition(self):
        """Pure sanity pin, no broker/env involved at all: the shadow position's own deadline
        math (2-session horizon) is computed exactly as it always was -- this fix touches
        NOTHING in open_mirror_position/decide_mirror_exit."""
        sig = {"signal_ref": "long|2026-08-20T10:00", "direction": "long",
              "source_arms": ["safe-1"], "setup_name": "TEST"}
        pos = fms.open_mirror_position(sig, entry_price=6000.0, atr=5.0, now_et=NORMAL_ET)
        deadline = dt.datetime.strptime(pos["deadline_et"], "%Y-%m-%dT%H:%M:%S")
        # next trading day (Friday 2026-08-21) at 15:55 ET -- unchanged 2-session spec.
        assert deadline.date() == dt.date(2026, 8, 21)
        assert deadline.time() == fms.DEADLINE_TIME_ET

    def test_armed_flatten_never_writes_the_would_be_ledger(self, monkeypatch):
        fake = _FakeBroker(connected=True, flat=False,
                          position={"symbol": "MESZ9", "qty": 2, "avg_cost": 6000.0})
        monkeypatch.setenv("MIRROR_ARMED", "1")
        import futures.futures_trader_core as ftc
        monkeypatch.setattr(ftc, "make_broker", lambda backend: fake)

        fms._broker_maintenance_flatten(FLATTEN_WINDOW_ET, quote_fetcher=lambda: 6000.0)

        assert not fms.WOULD_BE_FILE.exists()

    def test_run_once_shadow_row_count_unaffected_by_flatten_step(self, monkeypatch, tmp_path):
        """Full poll: an in-flight shadow position's own tp1/stop/time-flat handling (its
        2-session spec) proceeds identically whether or not MIRROR_ARMED triggers a broker
        flatten this same poll -- the two ledgers evolve completely independently."""
        fake = _FakeBroker(connected=True, flat=False,
                          position={"symbol": "MESZ9", "qty": 1, "avg_cost": 6000.0})
        monkeypatch.setenv("MIRROR_ARMED", "1")
        import futures.futures_trader_core as ftc
        monkeypatch.setattr(ftc, "make_broker", lambda backend: fake)

        p = tmp_path / "safe-1" / "decisions.jsonl"
        _write_decisions(p, [_enter_row("2026-06-01T10:05:00-04:00", "safe-1")])
        fms.run_once(now_et=dt.datetime(2026, 8, 20, 10, 0, 0),
                    quote_fetcher=lambda: 6000.0, atr_fetcher=lambda: 5.0, fleet_files=[p])

        _write_decisions(p, [_enter_row("2026-08-20T10:00:00-04:00", "safe-1")])
        summary = fms.run_once(now_et=FLATTEN_WINDOW_ET,
                               quote_fetcher=lambda: 6000.0, atr_fetcher=lambda: 5.0,
                               fleet_files=[p])
        # the shadow ledger keeps recording regardless of the armed flatten firing this poll
        assert fms.WOULD_BE_FILE.exists()
        assert summary["errors"] == []

"""Guard tests for FUTURES-BROKER-OCO-AND-FLATTEN-CANCEL (filed 2026-09-03, kill-type risk
reduction on the futures SANDBOX lane -- NOT under the SPY freeze).

Root cause recap (see `futures_broker_reconciler.py`'s module docstring + the queue item's
DONE note for the full evidence trail, `automation/state/futures/trader-broker/
anomalies.jsonl` for the 8 real anomaly fills that motivated this):

  1. `TastytradeBroker.place_bracket` submits TP1 and stop as two INDEPENDENT GTC orders
     with no OCO link -- on the 2026-09-02 entry BOTH filled, leaving a stray long 1.
  2. The FLATTEN branch (`futures_trader_core.run_tick` step 4) called `close_position()`
     directly, never `cancel_all()` first -- 5 extra contracts cascade-filled at flatten
     time on 2026-09-01 and 2026-09-02 from resting bracket legs that were never cancelled.

Every test in this file exercises a FAKE/mock broker -- no network, no real broker, no
order placement. `CME is open right now` per the task brief; nothing here calls a live
broker.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest", "setup/scripts"):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

from futures import futures_trader_core as core  # noqa: E402
from futures import futures_broker_reconciler as rec  # noqa: E402
from futures import futures_journal as fj  # noqa: E402
from futures.futures_risk_rails import FuturesRiskRails, RiskVerdict  # noqa: E402
from futures.instruments import get as get_instrument  # noqa: E402

import futures_health as fh  # noqa: E402

RTH_WED = dt.datetime(2026, 8, 12, 11, 0)  # a real weekday RTH tick, same constant the
                                            # existing test_futures_trader_core.py uses
ONE_BAR = pd.DataFrame({"open": [7700.0], "high": [7702.0], "low": [7698.0],
                        "close": [7700.0]})


def _paths(tmp_path):
    return {"dir": tmp_path, "ledger": tmp_path / "decisions.jsonl",
            "last_tick": tmp_path / "last-tick.json", "loop_state": tmp_path / "loop-state.json",
            "heartbeat": tmp_path / "heartbeat.json"}


def _fill(order_id, action, qty, price, filled_at_iso, fill_id):
    return {"order_id": order_id, "order_type": "Filled", "symbol": "/MESU6",
            "action": action, "qty": qty, "fill_price": price,
            "filled_at": filled_at_iso, "fill_id": fill_id}


ENTRY = {"side": "SELL", "qty": 1, "entry": 7681.5, "stop": 7690.0, "tp1": 7680.0,
        "runner": None, "stop_points": 8.5, "risk_usd": 42.5, "setup": "OPEN_REJECTION",
        "watcher": "shotgun_scalper_watcher", "confidence": "high", "direction": "short"}

LEG_IDS = {"entry": 1435171, "tp1": 1435172, "stop": 1435173, "runner": None}


def _record_open(tmp_path, entry=None, order_ids=(1435171, 1435172, 1435173),
                 leg_ids=None, entry_time_et="2026-09-02T11:15:01"):
    paths = _paths(tmp_path)
    rec.record_open_entry(paths, symbol="MES", entry=dict(entry or ENTRY),
                          order_ids=list(order_ids),
                          leg_ids=dict(leg_ids if leg_ids is not None else LEG_IDS),
                          now_et=dt.datetime.fromisoformat(entry_time_et))
    return paths


# ── (A) flatten cancel-confirm sweep ────────────────────────────────────────────

class FakeCancelBroker:
    """Exposes exactly the surface `_cancel_and_confirm_clear` touches. `working_sequence`
    is consumed one value per `get_working_orders()` call, in order; the last value repeats
    once exhausted -- lets a test simulate "still working for N polls, then clears" or
    "never clears"."""

    def __init__(self, working_sequence=([],), raise_on_cancel=False):
        self._seq = list(working_sequence)
        self._idx = 0
        self.raise_on_cancel = raise_on_cancel
        self.call_log: list[str] = []

    def cancel_all(self, symbol):
        self.call_log.append("cancel_all")
        if self.raise_on_cancel:
            raise RuntimeError("sandbox 502")
        return True

    def get_working_orders(self, symbol):
        self.call_log.append("get_working_orders")
        idx = min(self._idx, len(self._seq) - 1)
        val = self._seq[idx]
        self._idx += 1
        return val


class TestCancelAndConfirmClear:
    def test_clears_immediately_returns_true(self, tmp_path):
        broker = FakeCancelBroker(working_sequence=([],))
        paths = _paths(tmp_path)
        out = core._cancel_and_confirm_clear(broker, "MES", RTH_WED, paths)
        assert out is True
        assert broker.call_log[0] == "cancel_all", "must cancel BEFORE confirming clear"

    def test_clears_after_a_couple_polls_returns_true(self, tmp_path):
        broker = FakeCancelBroker(working_sequence=(
            [{"order_id": 1}], [{"order_id": 1}], []))
        paths = _paths(tmp_path)
        out = core._cancel_and_confirm_clear(broker, "MES", RTH_WED, paths)
        assert out is True
        assert broker.call_log.count("get_working_orders") == 3

    def test_orders_that_refuse_to_clear_return_false_and_log_loudly(self, tmp_path):
        broker = FakeCancelBroker(working_sequence=([{"order_id": 99}],))  # never clears
        paths = _paths(tmp_path)
        out = core._cancel_and_confirm_clear(broker, "MES", RTH_WED, paths)
        assert out is False
        assert broker.call_log.count("get_working_orders") == core.FLATTEN_CANCEL_MAX_POLLS
        anomalies = (tmp_path / "anomalies.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(anomalies) == 1
        row = json.loads(anomalies[0])
        assert row["event"] == "flatten_cancel_incomplete"
        assert row["symbol"] == "MES"

    def test_broker_without_get_working_orders_returns_none_but_still_cancels(self, tmp_path):
        class NoConfirmBroker:
            def cancel_all(self, symbol):
                return True
        broker = NoConfirmBroker()
        paths = _paths(tmp_path)
        out = core._cancel_and_confirm_clear(broker, "MES", RTH_WED, paths)
        assert out is None
        assert not (tmp_path / "anomalies.jsonl").exists()

    def test_a_failed_cancel_call_never_raises_and_is_logged(self, tmp_path):
        broker = FakeCancelBroker(working_sequence=([],), raise_on_cancel=True)
        paths = _paths(tmp_path)
        out = core._cancel_and_confirm_clear(broker, "MES", RTH_WED, paths)  # must not raise
        assert out is True  # cancel_all() blew up, but get_working_orders still confirms clear
        anomalies = (tmp_path / "anomalies.jsonl").read_text(encoding="utf-8").splitlines()
        assert json.loads(anomalies[0])["event"] == "flatten_cancel_error"


# ── (A) full run_tick FLATTEN integration ────────────────────────────────────────

class FlattenTickBroker:
    """Exposes exactly what `run_tick`'s FLATTEN branch (step 4) touches -- the same
    duck-typed surface as TastytradeBroker (no `process_quote`, matching the real broker
    lane), plus `get_recent_fills` returning [] so `reconcile_broker_exits` is a clean
    no-op and does not interfere with this test's own assertions."""

    def __init__(self, working_sequence=([],)):
        self._seq = list(working_sequence)
        self._idx = 0
        self.call_log: list[str] = []

    def connect(self):
        return True

    def is_flat(self, symbol):
        return False

    def get_positions(self):
        return [{"symbol": "/MESU6", "qty": 2}]

    def cancel_all(self, symbol):
        self.call_log.append("cancel_all")
        return True

    def get_working_orders(self, symbol):
        self.call_log.append("get_working_orders")
        idx = min(self._idx, len(self._seq) - 1)
        val = self._seq[idx]
        self._idx += 1
        return val

    def close_position(self, symbol, qty, side, price):
        self.call_log.append("close_position")
        return True

    def get_recent_fills(self, symbol, since_et=None, days_back=3):
        return []


def _forced_flatten_rails():
    rails = FuturesRiskRails()
    rails.must_flatten = lambda now_et: RiskVerdict(True, "test_forced_flatten", "TIME_STOP")
    return rails


class TestFlattenIntegration:
    def test_flatten_cancels_before_close(self, tmp_path, monkeypatch):
        monkeypatch.setattr(core, "STATE_DIR", tmp_path)
        monkeypatch.setattr(core, "LEDGER", tmp_path / "decisions.jsonl")
        monkeypatch.setattr(core, "LAST_TICK", tmp_path / "last-tick.json")
        monkeypatch.setattr(core, "HEARTBEAT", tmp_path / "heartbeat.json")
        broker = FlattenTickBroker(working_sequence=([],))
        rec_row = core.run_tick("MES", broker=broker, rails=_forced_flatten_rails(),
                                now_et=RTH_WED, bars=ONE_BAR, refresh=False,
                                freshness_override="GREEN", backend="fillsim")
        assert rec_row["action"] == "FLATTEN"
        assert rec_row["flatten_orders_cleared"] is True
        order = [c for c in broker.call_log if c in ("cancel_all", "close_position")]
        assert order == ["cancel_all", "close_position"], (
            f"cancel_all must run BEFORE close_position -- got {order}")

    def test_flatten_with_orders_that_refuse_to_clear_still_closes_and_logs_loudly(
            self, tmp_path, monkeypatch):
        monkeypatch.setattr(core, "STATE_DIR", tmp_path)
        monkeypatch.setattr(core, "LEDGER", tmp_path / "decisions.jsonl")
        monkeypatch.setattr(core, "LAST_TICK", tmp_path / "last-tick.json")
        monkeypatch.setattr(core, "HEARTBEAT", tmp_path / "heartbeat.json")
        broker = FlattenTickBroker(working_sequence=([{"order_id": 7}],))  # never clears
        rec_row = core.run_tick("MES", broker=broker, rails=_forced_flatten_rails(),
                                now_et=RTH_WED, bars=ONE_BAR, refresh=False,
                                freshness_override="GREEN", backend="fillsim")
        assert rec_row["action"] == "FLATTEN", "must still flatten -- never leave a known " \
            "non-flat account further exposed while waiting on an unconfirmed cancel"
        assert rec_row["flatten_orders_cleared"] is False
        assert "close_position" in broker.call_log, "close_position must still run"
        anomalies_path = tmp_path / "anomalies.jsonl"
        assert anomalies_path.exists(), "an incomplete flatten sweep must log LOUDLY"
        row = json.loads(anomalies_path.read_text(encoding="utf-8").splitlines()[0])
        assert row["event"] == "flatten_cancel_incomplete"


# ── (B) sibling-cancel on the reconciler ─────────────────────────────────────────

class FakeSiblingBroker:
    """Adds `cancel_order` + `is_flat` + `get_working_orders` to the reconciler-test
    FakeBroker surface (see test_futures_broker_exit_reconciler_2026_09_03.py) -- the
    duck-typed contract `reconcile_broker_exits`'s sibling-cancel and post-exit assertion
    now read."""

    def __init__(self, fills, is_flat_after=True, working_after=()):
        self._fills = fills
        self.cancelled_ids: list = []
        self._is_flat_after = is_flat_after
        self._working_after = list(working_after)

    def get_recent_fills(self, symbol, since_et=None, days_back=3):
        return list(self._fills)

    def cancel_order(self, order_id):
        self.cancelled_ids.append(order_id)
        return True

    def is_flat(self, symbol):
        return self._is_flat_after

    def get_working_orders(self, symbol):
        return list(self._working_after)


class TestSiblingCancel:
    def test_sibling_cancelled_on_tp1_fill(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fj, "TRADES_CSV", tmp_path / "trades.csv")
        monkeypatch.setattr(fj, "JOURNAL_DIR", tmp_path)
        paths = _record_open(tmp_path)
        broker = FakeSiblingBroker([
            _fill(1435172, "BUY", 1.0, 7680.0, "2026-09-02T15:45:34.073000+00:00", "496"),
        ])
        inst = get_instrument("MES")
        rec.reconcile_broker_exits(broker, inst, paths, dt.datetime(2026, 9, 2, 16),
                                   point_value=5.0, backend_name="TastytradeBroker")
        assert broker.cancelled_ids == [1435173], "the STOP leg (the sibling of tp1) " \
            "must be cancelled, and nothing else"
        open_entry = json.loads(rec.open_entry_path(paths).read_text(encoding="utf-8")) \
            if rec.open_entry_path(paths).exists() else None
        # entry qty 1 == tp1 fill qty 1 -> fully closed -> tracker cleared. Confirm via the
        # anomaly row instead, which survives regardless of tracker lifecycle.
        anomalies = [json.loads(r) for r in
                    (tmp_path / "anomalies.jsonl").read_text(encoding="utf-8").splitlines()]
        sib = [a for a in anomalies if a["event"] == "sibling_leg_cancelled"]
        assert len(sib) == 1
        assert sib[0]["filled_leg"] == "tp1"
        assert sib[0]["cancelled_leg"] == "stop"
        assert sib[0]["cancelled_order_id"] == 1435173

    def test_sibling_cancelled_on_stop_fill(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fj, "TRADES_CSV", tmp_path / "trades.csv")
        monkeypatch.setattr(fj, "JOURNAL_DIR", tmp_path)
        paths = _record_open(tmp_path)
        broker = FakeSiblingBroker([
            _fill(1435173, "BUY", 1.0, 7690.0, "2026-09-02T15:28:07.095000+00:00", "495"),
        ])
        inst = get_instrument("MES")
        rec.reconcile_broker_exits(broker, inst, paths, dt.datetime(2026, 9, 2, 16),
                                   point_value=5.0, backend_name="TastytradeBroker")
        assert broker.cancelled_ids == [1435172], "the TP1 leg (the sibling of stop) " \
            "must be cancelled"

    def test_sibling_cancel_fires_at_most_once_per_entry(self, tmp_path, monkeypatch):
        """A partial TP1 fill on a multi-contract entry must not re-cancel an already-
        cancelled sibling on the next tick's reconciliation pass."""
        monkeypatch.setattr(fj, "TRADES_CSV", tmp_path / "trades.csv")
        monkeypatch.setattr(fj, "JOURNAL_DIR", tmp_path)
        entry = dict(ENTRY, qty=2)
        paths = _record_open(tmp_path, entry=entry)
        broker = FakeSiblingBroker([
            _fill(1435172, "BUY", 1.0, 7680.0, "2026-09-02T15:45:34.073000+00:00", "496"),
        ])
        inst = get_instrument("MES")
        # Tick 1: partial TP1 fill -- sibling cancelled once.
        rec.reconcile_broker_exits(broker, inst, paths, dt.datetime(2026, 9, 2, 16),
                                   point_value=5.0, backend_name="TastytradeBroker")
        assert broker.cancelled_ids == [1435173]
        # Tick 2: nothing new to reconcile (same fills, already journaled) -- must not
        # cancel again.
        rec.reconcile_broker_exits(broker, inst, paths, dt.datetime(2026, 9, 2, 16, 1),
                                   point_value=5.0, backend_name="TastytradeBroker")
        assert broker.cancelled_ids == [1435173], "must fire at most once per entry"

    def test_no_leg_ids_disables_the_safety_net_without_erroring(self, tmp_path, monkeypatch):
        """An entry recorded before this fix shipped (or by a broker with no labeled leg
        map) has no leg_ids -- the reconciler must still journal correctly, just without
        the sibling-cancel safety net."""
        monkeypatch.setattr(fj, "TRADES_CSV", tmp_path / "trades.csv")
        monkeypatch.setattr(fj, "JOURNAL_DIR", tmp_path)
        paths = _record_open(tmp_path, leg_ids={})
        broker = FakeSiblingBroker([
            _fill(1435172, "BUY", 1.0, 7680.0, "2026-09-02T15:45:34.073000+00:00", "496"),
        ])
        inst = get_instrument("MES")
        out = rec.reconcile_broker_exits(broker, inst, paths, dt.datetime(2026, 9, 2, 16),
                                         point_value=5.0, backend_name="TastytradeBroker")
        assert len(out) == 1
        assert broker.cancelled_ids == []


class TestPostExitAssertion:
    def test_no_stray_position_after_a_clean_exit_logs_nothing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fj, "TRADES_CSV", tmp_path / "trades.csv")
        monkeypatch.setattr(fj, "JOURNAL_DIR", tmp_path)
        paths = _record_open(tmp_path)
        broker = FakeSiblingBroker([
            _fill(1435172, "BUY", 1.0, 7680.0, "2026-09-02T15:45:34.073000+00:00", "496"),
        ], is_flat_after=True, working_after=[])
        inst = get_instrument("MES")
        rec.reconcile_broker_exits(broker, inst, paths, dt.datetime(2026, 9, 2, 16),
                                   point_value=5.0, backend_name="TastytradeBroker")
        anomalies = [json.loads(r) for r in
                    (tmp_path / "anomalies.jsonl").read_text(encoding="utf-8").splitlines()]
        assert not any(a["event"] == "post_exit_not_flat" for a in anomalies)

    def test_a_broker_still_not_flat_after_the_journaled_close_is_flagged_red(
            self, tmp_path, monkeypatch):
        """The exact FUTURES-BROKER-OCO-AND-FLATTEN-CANCEL scenario: this entry journals
        as fully closed, but the broker STILL shows a working order (the resting sibling
        somehow survived the cancel) -- must be logged loudly, not silently."""
        monkeypatch.setattr(fj, "TRADES_CSV", tmp_path / "trades.csv")
        monkeypatch.setattr(fj, "JOURNAL_DIR", tmp_path)
        paths = _record_open(tmp_path)
        broker = FakeSiblingBroker([
            _fill(1435172, "BUY", 1.0, 7680.0, "2026-09-02T15:45:34.073000+00:00", "496"),
        ], is_flat_after=False, working_after=[{"order_id": 1435173}])
        inst = get_instrument("MES")
        rec.reconcile_broker_exits(broker, inst, paths, dt.datetime(2026, 9, 2, 16),
                                   point_value=5.0, backend_name="TastytradeBroker")
        anomalies = [json.loads(r) for r in
                    (tmp_path / "anomalies.jsonl").read_text(encoding="utf-8").splitlines()]
        hits = [a for a in anomalies if a["event"] == "post_exit_not_flat"]
        assert len(hits) == 1
        assert hits[0]["broker_not_flat"] is True
        assert hits[0]["working_orders"] == [{"order_id": 1435173}]


class TestReplayThe0902DoubleFillSequence:
    """Replays the REAL 2026-09-02 anomaly sequence from anomalies.jsonl (entry order_ids
    1435171/1435172/1435173: stop 1435173 filled at 15:28:07, tp1 1435172 filled at
    15:45:34, the second fill that this whole fix exists to prevent). With sibling-cancel
    wired, the FIRST fill (stop) must trigger a cancel of the tp1 leg -- so a broker that
    actually honored that cancel would never have produced the second fill at all."""

    def test_first_fill_triggers_sibling_cancel_of_the_leg_that_produced_the_anomaly(
            self, tmp_path, monkeypatch):
        monkeypatch.setattr(fj, "TRADES_CSV", tmp_path / "trades.csv")
        monkeypatch.setattr(fj, "JOURNAL_DIR", tmp_path)
        entry = dict(ENTRY, stop=7690.0, tp1=7680.0)
        paths = _record_open(tmp_path, entry=entry,
                             order_ids=(1435171, 1435172, 1435173),
                             leg_ids={"entry": 1435171, "tp1": 1435172, "stop": 1435173,
                                      "runner": None},
                             entry_time_et="2026-09-02T11:15:01")
        # Only the FIRST real fill is visible this tick -- exactly what a live tick sees
        # before the second (anomalous) fill has happened yet.
        broker = FakeSiblingBroker([
            _fill(1435173, "BUY", 1.0, 7690.0, "2026-09-02T15:28:07.095000+00:00", "495"),
        ])
        inst = get_instrument("MES")
        rec.reconcile_broker_exits(broker, inst, paths, dt.datetime(2026, 9, 2, 15, 30),
                                   point_value=5.0, backend_name="TastytradeBroker")
        assert broker.cancelled_ids == [1435172], (
            "the tp1 leg (order 1435172 -- the SAME order id that produced the real "
            "unattributed_closing_fill anomaly at 15:45:34 in production) must be "
            "cancelled the instant the stop fill is seen, before it has a chance to fill")


# ── futures_health.py::check_no_stray_exposure ───────────────────────────────────

NOW = dt.datetime(2026, 9, 3, 2, 0, 0)


def _write_anomalies(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


class TestNoStrayExposureHealthCheck:
    def test_no_file_is_green(self, tmp_path):
        result = fh.check_no_stray_exposure(NOW, anomalies_path=tmp_path / "nope.jsonl")
        assert result["status"] == "GREEN"

    def test_unattributed_closing_fill_is_red(self, tmp_path):
        p = tmp_path / "anomalies.jsonl"
        _write_anomalies(p, [{"at_et": "2026-09-02T15:45:34", "event":
                             "unattributed_closing_fill", "symbol": "MES"}])
        result = fh.check_no_stray_exposure(NOW, anomalies_path=p)
        assert result["status"] == "RED"

    def test_flatten_cancel_incomplete_is_red(self, tmp_path):
        p = tmp_path / "anomalies.jsonl"
        _write_anomalies(p, [{"at_et": "2026-09-02T20:00:00", "event":
                             "flatten_cancel_incomplete", "symbol": "MES"}])
        result = fh.check_no_stray_exposure(NOW, anomalies_path=p)
        assert result["status"] == "RED"

    def test_post_exit_not_flat_is_red(self, tmp_path):
        p = tmp_path / "anomalies.jsonl"
        _write_anomalies(p, [{"at_et": "2026-09-02T20:00:00", "event":
                             "post_exit_not_flat", "symbol": "MES"}])
        result = fh.check_no_stray_exposure(NOW, anomalies_path=p)
        assert result["status"] == "RED"

    def test_sibling_leg_cancelled_alone_is_not_red(self, tmp_path):
        """The safety net WORKING is informational, not a failure."""
        p = tmp_path / "anomalies.jsonl"
        _write_anomalies(p, [{"at_et": "2026-09-02T15:45:34", "event":
                             "sibling_leg_cancelled", "symbol": "MES"}])
        result = fh.check_no_stray_exposure(NOW, anomalies_path=p)
        assert result["status"] == "GREEN"

    def test_wired_into_build_report(self, tmp_path):
        names = [c["name"] for c in fh.build_report(NOW)["checks"]]
        assert "no_stray_exposure" in names


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

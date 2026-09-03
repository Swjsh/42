"""Guard tests for FUTURES-BROKER-LANE-NEVER-LOGS-EXITS (filed 2026-09-03).

Covers `backtest/futures/futures_broker_reconciler.py` (the new writer) and
`setup/scripts/futures_health.py::check_broker_exit_pairing` (the new RED guard).

Root cause recap (see the module docstring in futures_broker_reconciler.py for the full
evidence trail): TastytradeBroker has neither `process_quote` nor `get_positions_snapshot`,
so `futures_trader_core.run_tick`'s existing exit-detection path (built for FillSimBroker)
never fires for the real-broker lane, and the FLATTEN branch never journaled either. This
suite exercises the new reconciler in isolation with a FAKE broker exposing only
`get_recent_fills` -- no network, no real broker, no order placement.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest", "setup/scripts"):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

from futures import futures_broker_reconciler as rec  # noqa: E402
from futures import futures_journal as fj  # noqa: E402
from futures.instruments import get as get_instrument  # noqa: E402

import futures_health as fh  # noqa: E402


class FakeBroker:
    """Exposes exactly the surface reconcile_broker_exits touches -- get_recent_fills only,
    matching the real duck-typed contract TastytradeBroker now implements."""

    def __init__(self, fills: list[dict]):
        self._fills = fills

    def get_recent_fills(self, symbol, since_et=None, days_back=3):
        return list(self._fills)


def _fill(order_id, action, qty, price, filled_at_iso, fill_id):
    return {"order_id": order_id, "order_type": "Filled", "symbol": "/MESU6",
            "action": action, "qty": qty, "fill_price": price,
            "filled_at": filled_at_iso, "fill_id": fill_id}


def _paths(tmp_path):
    return {"dir": tmp_path, "ledger": tmp_path / "decisions.jsonl",
            "last_tick": tmp_path / "last-tick.json", "loop_state": tmp_path / "loop-state.json",
            "heartbeat": tmp_path / "heartbeat.json"}


ENTRY = {"side": "SELL", "qty": 1, "entry": 7688.75, "stop": 7704.05, "tp1": 7685.5,
        "runner": None, "stop_points": 15.3, "risk_usd": 76.5, "setup": "OPEN_REJECTION",
        "watcher": "shotgun_scalper_watcher", "confidence": "high", "direction": "short"}


def _record_open(tmp_path, entry=ENTRY, order_ids=(1428293, 1428296),
                 entry_time_et="2026-08-31T09:45:01"):
    paths = _paths(tmp_path)
    rec.record_open_entry(paths, symbol="MES", entry=dict(entry), order_ids=list(order_ids),
                          now_et=dt.datetime.fromisoformat(entry_time_et))
    return paths


class TestCleanRoundTrip:
    def test_a_single_closing_fill_is_journaled_as_broker_and_clears_open_entry(
            self, tmp_path, monkeypatch):
        monkeypatch.setattr(fj, "TRADES_CSV", tmp_path / "trades.csv")
        monkeypatch.setattr(fj, "JOURNAL_DIR", tmp_path)
        paths = _record_open(tmp_path)
        broker = FakeBroker([
            _fill(1428296, "BUY", 1.0, 7685.5, "2026-08-31T13:46:44.541000+00:00", "204"),
        ])
        inst = get_instrument("MES")
        out = rec.reconcile_broker_exits(broker, inst, paths,
                                         dt.datetime(2026, 8, 31, 10), point_value=5.0,
                                         backend_name="TastytradeBroker")
        assert len(out) == 1
        assert out[0]["pnl"] == 16.25  # (7688.75 - 7685.5) * 1 * 5
        rows = fj.read_trades(fills="BROKER")
        assert len(rows) == 1
        assert rows[0]["exit_reason"] == "TP1_FULL"
        assert rows[0]["fills"] == "BROKER"
        assert "fill_id=204" in rows[0]["notes"]
        assert not rec.open_entry_path(paths).exists(), "closed entry must clear its tracker"

    def test_idempotent_a_second_call_journals_nothing_new(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fj, "TRADES_CSV", tmp_path / "trades.csv")
        monkeypatch.setattr(fj, "JOURNAL_DIR", tmp_path)
        paths = _record_open(tmp_path)
        broker = FakeBroker([
            _fill(1428296, "BUY", 1.0, 7685.5, "2026-08-31T13:46:44.541000+00:00", "204"),
        ])
        inst = get_instrument("MES")
        rec.reconcile_broker_exits(broker, inst, paths, dt.datetime(2026, 8, 31, 10),
                                   point_value=5.0, backend_name="TastytradeBroker")
        # open-entry.json is gone now -- a real second tick would have nothing to reconcile,
        # exactly like the live no-stacking gate intends. Re-seed it to prove the FILL
        # ITSELF (not just the missing tracker) is what makes the second call a no-op.
        _record_open(tmp_path)
        out2 = rec.reconcile_broker_exits(broker, inst, paths, dt.datetime(2026, 8, 31, 10),
                                          point_value=5.0, backend_name="TastytradeBroker")
        assert out2 == []
        rows = fj.read_trades(fills="BROKER")
        assert len(rows) == 1, "the same fill_id must never be journaled twice"

    def test_entry_price_prefers_the_real_broker_fill_over_the_signal_target(
            self, tmp_path, monkeypatch):
        """Regression for the bug caught live 2026-09-03: a limit order can fill THROUGH
        its requested price. Using the signal's target instead of the real fill produced a
        wrong P&L (-$86.25 instead of the real -$67.50) on the first backfill pass."""
        monkeypatch.setattr(fj, "TRADES_CSV", tmp_path / "trades.csv")
        monkeypatch.setattr(fj, "JOURNAL_DIR", tmp_path)
        entry = dict(ENTRY, entry=7682.0, tp1=None, stop=7694.3)  # signal wanted 7682.0
        paths = _record_open(tmp_path, entry=entry, order_ids=(1429073, 1429074),
                             entry_time_et="2026-08-31T15:00:01")
        broker = FakeBroker([
            _fill(1429073, "SELL", 1.0, 7685.75, "2026-08-31T19:00:11.562000+00:00", "327"),
            _fill(1429210, "BUY", 1.0, 7699.25, "2026-08-31T20:00:07.753000+00:00", "344"),
        ])
        inst = get_instrument("MES")
        rec.reconcile_broker_exits(broker, inst, paths, dt.datetime(2026, 8, 31, 21),
                                   point_value=5.0, backend_name="TastytradeBroker")
        rows = fj.read_trades(fills="BROKER")
        assert rows[0]["entry_px"] == "7685.75"  # the REAL fill, not the 7682.0 signal target
        assert rows[0]["dollar_pnl"] == "-67.5"
        assert "signal_entry_px=7682.0" in rows[0]["notes"], "the override must be disclosed"


class TestOverflowAndBounding:
    def test_a_closing_fill_beyond_entry_qty_is_an_anomaly_not_a_fabricated_trade(
            self, tmp_path, monkeypatch):
        """Regression for the live 2026-09-02 double-fill: TP1 and STOP are independent
        GTC orders (no OCO), so both can fill. The SECOND closing-side fill must never be
        forced into a fabricated second round trip against an entry that already closed."""
        monkeypatch.setattr(fj, "TRADES_CSV", tmp_path / "trades.csv")
        monkeypatch.setattr(fj, "JOURNAL_DIR", tmp_path)
        entry = dict(ENTRY, entry=7681.5, stop=7690.0, tp1=7680.0)
        paths = _record_open(tmp_path, entry=entry, order_ids=(1435171, 1435172, 1435173),
                             entry_time_et="2026-09-02T11:15:01")
        broker = FakeBroker([
            _fill(1435173, "BUY", 1.0, 7690.0, "2026-09-02T15:28:07.095000+00:00", "495"),
            _fill(1435172, "BUY", 1.0, 7680.0, "2026-09-02T15:45:34.073000+00:00", "496"),
        ])
        inst = get_instrument("MES")
        rec.reconcile_broker_exits(broker, inst, paths, dt.datetime(2026, 9, 2, 16),
                                   point_value=5.0, backend_name="TastytradeBroker")
        rows = fj.read_trades(fills="BROKER")
        assert len(rows) == 1, "only the FIRST closing fill may be counted as the round trip"
        assert rows[0]["exit_reason"] == "FULL_STOP"
        anomalies = (paths["dir"] / "anomalies.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(anomalies) == 1
        anomaly = json.loads(anomalies[0])
        assert anomaly["event"] == "unattributed_closing_fill"
        assert anomaly["fill"]["fill_id"] == "496"

    def test_until_et_bounds_an_earlier_entrys_search_from_a_laters_fill(
            self, tmp_path, monkeypatch):
        """Regression for the backfill-script bug caught live 2026-09-03: without an upper
        bound, entry 1's reconciliation swept entry 2's real closing fill into an
        'anomaly' and permanently marked it journaled, starving entry 2 of its own close."""
        monkeypatch.setattr(fj, "TRADES_CSV", tmp_path / "trades.csv")
        monkeypatch.setattr(fj, "JOURNAL_DIR", tmp_path)
        paths = _record_open(tmp_path)  # entry 1, order_ids (1428293, 1428296)
        broker = FakeBroker([
            _fill(1428296, "BUY", 1.0, 7685.5, "2026-08-31T13:46:44.541000+00:00", "204"),
            # A LATER entry's real close -- must be invisible to entry 1's window.
            _fill(1429210, "BUY", 1.0, 7699.25, "2026-08-31T20:00:07.753000+00:00", "344"),
        ])
        inst = get_instrument("MES")
        until = dt.datetime(2026, 8, 31, 15, 0, 1)  # entry 2's own ts_et
        rec.reconcile_broker_exits(broker, inst, paths, dt.datetime(2026, 8, 31, 21),
                                   point_value=5.0, backend_name="TastytradeBroker",
                                   until_et=until)
        assert not (paths["dir"] / "anomalies.jsonl").exists(), (
            "the later fill must not even be SEEN by this entry's reconciliation, "
            "let alone consumed as a false anomaly")
        seen = json.loads((paths["dir"] / "journaled-fills.json").read_text(encoding="utf-8"))
        assert "344" not in seen, "must remain available for entry 2 to claim"


class TestNoOpPaths:
    def test_no_open_entry_file_is_a_silent_noop(self, tmp_path):
        paths = _paths(tmp_path)
        broker = FakeBroker([_fill(1, "BUY", 1.0, 100.0, "2026-08-31T13:46:44+00:00", "1")])
        inst = get_instrument("MES")
        assert rec.reconcile_broker_exits(broker, inst, paths, dt.datetime(2026, 8, 31),
                                          point_value=5.0, backend_name="x") == []

    def test_broker_without_get_recent_fills_is_a_silent_noop(self, tmp_path):
        paths = _record_open(tmp_path)

        class NoFillsBroker:
            pass

        inst = get_instrument("MES")
        assert rec.reconcile_broker_exits(NoFillsBroker(), inst, paths, dt.datetime(2026, 8, 31),
                                          point_value=5.0, backend_name="x") == []

    def test_same_side_fills_are_never_treated_as_a_close(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fj, "TRADES_CSV", tmp_path / "trades.csv")
        monkeypatch.setattr(fj, "JOURNAL_DIR", tmp_path)
        paths = _record_open(tmp_path)  # entry side SELL
        broker = FakeBroker([
            _fill(1428293, "SELL", 1.0, 7688.75, "2026-08-31T13:45:10.921000+00:00", "203"),
        ])
        inst = get_instrument("MES")
        out = rec.reconcile_broker_exits(broker, inst, paths, dt.datetime(2026, 8, 31, 10),
                                         point_value=5.0, backend_name="TastytradeBroker")
        assert out == []
        assert rec.open_entry_path(paths).exists(), "an entry-side fill must not close anything"


# ---------------------------------------------------------------------------
# futures_health.py::check_broker_exit_pairing
# ---------------------------------------------------------------------------
NOW = dt.datetime(2026, 9, 3, 2, 0, 0)


def _write_jsonl(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _write_trades_csv(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fj.TRADE_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fj.TRADE_COLUMNS})


class TestBrokerExitPairingHealthCheck:
    def test_no_enter_rows_is_green(self, tmp_path):
        d = tmp_path / "decisions.jsonl"
        _write_jsonl(d, [{"ts_et": "2026-09-02T09:30:01", "action": "HOLD"}])
        result = fh.check_broker_exit_pairing(NOW, decisions_path=d)
        assert result["status"] == "GREEN"

    def test_orphaned_enter_with_no_journaled_exit_is_red(self, tmp_path):
        d = tmp_path / "decisions.jsonl"
        t = tmp_path / "trades.csv"
        _write_jsonl(d, [{"ts_et": "2026-08-31T09:45:01", "action": "ENTER",
                          "order_ids": [1428293, 1428296]}])
        _write_trades_csv(t, [])  # nothing ever journaled -- the exact original bug
        result = fh.check_broker_exit_pairing(NOW, decisions_path=d, trades_csv_path=t,
                                              open_entry_path=tmp_path / "open-entry.json")
        assert result["status"] == "RED"
        assert "1 ENTER" in result["detail"]
        assert "1428293" in result["detail"]

    def test_enter_with_a_journaled_broker_exit_is_green(self, tmp_path):
        d = tmp_path / "decisions.jsonl"
        t = tmp_path / "trades.csv"
        _write_jsonl(d, [{"ts_et": "2026-08-31T09:45:01", "action": "ENTER",
                          "order_ids": [1428293, 1428296]}])
        _write_trades_csv(t, [{
            "fills": "BROKER", "notes": "broker_order_ids=entry:[1428293, 1428296],exit:1428296",
        }])
        result = fh.check_broker_exit_pairing(NOW, decisions_path=d, trades_csv_path=t,
                                              open_entry_path=tmp_path / "open-entry.json")
        assert result["status"] == "GREEN"

    def test_a_genuinely_still_open_and_tracked_position_is_not_red(self, tmp_path):
        d = tmp_path / "decisions.jsonl"
        t = tmp_path / "trades.csv"
        o = tmp_path / "open-entry.json"
        _write_jsonl(d, [{"ts_et": "2026-09-02T15:55:01", "action": "ENTER",
                          "order_ids": [9001, 9002]}])
        _write_trades_csv(t, [])
        o.write_text(json.dumps({"order_ids": [9001, 9002],
                                 "entry_time_et": "2026-09-02T15:55:01"}), encoding="utf-8")
        result = fh.check_broker_exit_pairing(NOW, decisions_path=d, trades_csv_path=t,
                                              open_entry_path=o)
        assert result["status"] == "GREEN"

    def test_a_stale_open_entry_past_its_own_session_is_red(self, tmp_path):
        d = tmp_path / "decisions.jsonl"
        t = tmp_path / "trades.csv"
        o = tmp_path / "open-entry.json"
        _write_jsonl(d, [{"ts_et": "2026-08-30T09:45:01", "action": "ENTER",
                          "order_ids": [9001, 9002]}])
        _write_trades_csv(t, [])
        o.write_text(json.dumps({"order_ids": [9001, 9002],
                                 "entry_time_et": "2026-08-30T09:45:01"}), encoding="utf-8")
        result = fh.check_broker_exit_pairing(NOW, decisions_path=d, trades_csv_path=t,
                                              open_entry_path=o)
        assert result["status"] == "RED"
        assert "stuck past its own session" in result["detail"]

    def test_missing_decisions_file_is_unknown_not_a_false_green(self, tmp_path):
        result = fh.check_broker_exit_pairing(NOW, decisions_path=tmp_path / "nope.jsonl")
        assert result["status"] == "UNKNOWN"

    def test_wired_into_build_report(self, tmp_path, monkeypatch):
        """The new check must actually run as part of the fused verdict, not just exist."""
        names = [c["name"] for c in fh.build_report(NOW)["checks"]]
        assert "broker_exit_pairing" in names

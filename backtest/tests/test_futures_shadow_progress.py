"""Guards for setup/scripts/futures_shadow_progress.py (2026-07-14, FUTURES-MIRROR-SHADOW
arming-bar tracker -- queue.md item #5, J directive 'make sure you trade futures today too').

Covers: round-trip counting/aggregation from a fixture would-be-trades ledger (partial TP1 +
final leg summed per signal_ref, open positions excluded), the null-computation gate (never
fetches/computes below the 20-round-trip floor), the buy-and-hold null math against an
injected bar_lookup, fail-open on a missing/corrupt ledger, and the atomic-write round-trip.
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
import futures_shadow_progress as fsp  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_state(monkeypatch, tmp_path):
    """Same isolation contract as test_futures_mirror_shadow.py -- guards must never touch
    real automation/state/futures/*."""
    state_dir = tmp_path / "futures"
    monkeypatch.setattr(fms, "STATE_DIR", state_dir)
    monkeypatch.setattr(fms, "WOULD_BE_FILE", state_dir / "mirror-would-be.jsonl")


def _write_ledger(rows: list[dict]) -> None:
    fms.WOULD_BE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(fms.WOULD_BE_FILE, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _filled(ref: str, direction: str, entry: float, ts: str, setup: str = "X",
           arms: "list[str] | None" = None) -> dict:
    return {"ts_et": ts, "signal_ref": ref, "direction": direction, "entry": entry,
           "event": fms.EV_FILLED, "pnl_usd_mes": 0.0, "qty_open_after": fms.ENTRY_QTY,
           "setup_name": setup, "source_arms": arms or ["safe-1"]}


def _stopped(ref: str, direction: str, entry: float, pnl: float, ts: str) -> dict:
    return {"ts_et": ts, "signal_ref": ref, "direction": direction, "entry": entry,
           "event": fms.EV_STOPPED, "pnl_usd_mes": pnl, "qty_open_after": 0}


def _tp1(ref: str, direction: str, entry: float, pnl: float, ts: str, remaining: int = 1) -> dict:
    return {"ts_et": ts, "signal_ref": ref, "direction": direction, "entry": entry,
           "event": fms.EV_TP1, "pnl_usd_mes": pnl, "qty_open_after": remaining}


def _time_flat(ref: str, direction: str, entry: float, pnl: float, ts: str) -> dict:
    return {"ts_et": ts, "signal_ref": ref, "direction": direction, "entry": entry,
           "event": fms.EV_TIME_FLAT, "pnl_usd_mes": pnl, "qty_open_after": 0}


# ═══════════════════════ load_would_be_rows ═════════════════════════════════════
class TestLoadWouldBeRows:
    def test_missing_file_returns_empty(self):
        assert fsp.load_would_be_rows() == []

    def test_skips_doc_header(self):
        _write_ledger([{"_doc": "header text"}, _filled("a", "long", 6000.0, "t")])
        rows = fsp.load_would_be_rows()
        assert len(rows) == 1
        assert rows[0]["signal_ref"] == "a"

    def test_skips_malformed_line(self):
        fms.WOULD_BE_FILE.parent.mkdir(parents=True, exist_ok=True)
        fms.WOULD_BE_FILE.write_text(
            '{"_doc": "x"}\n{not json\n' + json.dumps(_filled("a", "long", 6000.0, "t")) + "\n",
            encoding="utf-8")
        rows = fsp.load_would_be_rows()
        assert len(rows) == 1


# ═══════════════════════ round-trip aggregation ═════════════════════════════════
class TestComputeRoundTrips:
    def test_open_signal_not_counted(self):
        rows = [_filled("a", "long", 6000.0, "2026-07-09T10:06:00")]
        assert fsp.compute_round_trips(rows) == []

    def test_stopped_pre_tp1_is_one_round_trip(self):
        rows = [
            _filled("a", "long", 6000.0, "2026-07-09T10:06:00"),
            _stopped("a", "long", 6000.0, -30.0, "2026-07-09T10:20:00"),
        ]
        trips = fsp.compute_round_trips(rows)
        assert len(trips) == 1
        assert trips[0]["total_pnl_usd"] == pytest.approx(-30.0)
        assert trips[0]["direction"] == "long"
        assert trips[0]["entry"] == 6000.0

    def test_tp1_then_stopped_sums_both_legs(self):
        """A partial TP1 leg (qty_open_after > 0, not yet a closing event) plus the final
        trailing-stop leg (qty_open_after == 0) must sum into ONE round trip's total_pnl_usd
        -- the load-bearing 'counted per signal_ref not per row' rule."""
        rows = [
            _filled("a", "long", 6000.0, "2026-07-09T10:06:00"),
            _tp1("a", "long", 6000.0, 15.0, "2026-07-09T10:20:00", remaining=1),
            _stopped("a", "long", 6000.0, 10.0, "2026-07-09T10:40:00"),
        ]
        trips = fsp.compute_round_trips(rows)
        assert len(trips) == 1
        assert trips[0]["total_pnl_usd"] == pytest.approx(25.0)

    def test_time_flat_counts_as_closing(self):
        rows = [
            _filled("a", "short", 6000.0, "2026-07-09T10:06:00"),
            _time_flat("a", "short", 6000.0, -5.0, "2026-07-10T15:55:00"),
        ]
        trips = fsp.compute_round_trips(rows)
        assert len(trips) == 1

    def test_multiple_signal_refs_isolated(self):
        rows = [
            _filled("a", "long", 6000.0, "2026-07-09T10:06:00"),
            _stopped("a", "long", 6000.0, -30.0, "2026-07-09T10:20:00"),
            _filled("b", "short", 6010.0, "2026-07-09T11:06:00"),
            _stopped("b", "short", 6010.0, 40.0, "2026-07-09T11:20:00"),
        ]
        trips = fsp.compute_round_trips(rows)
        assert {t["signal_ref"] for t in trips} == {"a", "b"}

    def test_ignores_placed_row_in_pnl_sum(self):
        """A 'placed' row always carries pnl_usd_mes=0.0 -- included harmlessly in the sum,
        but must not be mistaken for a closing event."""
        rows = [
            {"ts_et": "t0", "signal_ref": "a", "direction": "long", "entry": 6000.0,
             "event": fms.EV_PLACED, "pnl_usd_mes": 0.0, "qty_open_after": fms.ENTRY_QTY},
            _filled("a", "long", 6000.0, "t1"),
            _stopped("a", "long", 6000.0, -12.0, "t2"),
        ]
        trips = fsp.compute_round_trips(rows)
        assert trips[0]["total_pnl_usd"] == pytest.approx(-12.0)


# ═══════════════════════ progress computation + null gate ═══════════════════════
class TestComputeProgress:
    def test_zero_round_trips_reports_untested_null(self):
        progress = fsp.compute_progress([], now_et=dt.datetime(2026, 7, 9, 16, 0, 0))
        assert progress["n_round_trips"] == 0
        assert progress["positive_expectancy"] is False
        assert progress["null_check"]["evaluated"] is False
        assert "< 20" in progress["null_check"]["reason"]
        assert progress["arming_bar"]["armable"] is False

    def test_positive_expectancy_true_when_total_positive(self):
        rows = [
            _filled("a", "long", 6000.0, "2026-07-09T10:06:00"),
            _stopped("a", "long", 6000.0, 50.0, "2026-07-09T10:20:00"),
        ]
        progress = fsp.compute_progress(rows, now_et=dt.datetime(2026, 7, 9, 16, 0, 0))
        assert progress["n_round_trips"] == 1
        assert progress["total_pnl_usd"] == pytest.approx(50.0)
        assert progress["positive_expectancy"] is True

    def test_null_never_computed_below_20_even_with_bar_lookup_supplied(self):
        """Task instruction: 'compute the null when n>=20, not before' -- literal, not just
        the RESULT: even if a caller supplies a working bar_lookup, it must never be invoked
        below the floor."""
        calls = []

        def _lookup(ts):
            calls.append(ts)
            return 6100.0

        rows = [
            _filled("a", "long", 6000.0, "2026-07-09T10:06:00"),
            _stopped("a", "long", 6000.0, 50.0, "2026-07-09T10:20:00"),
        ]
        progress = fsp.compute_progress(rows, bar_lookup=_lookup,
                                        now_et=dt.datetime(2026, 7, 9, 16, 0, 0))
        assert progress["null_check"]["evaluated"] is False
        assert calls == []   # never invoked -- the floor gate happens before any lookup call

    def _make_20_round_trips(self, pnl_each: float) -> list[dict]:
        rows = []
        for i in range(20):
            ref = f"sig-{i}"
            ts = f"2026-07-09T{10 + (i % 5):02d}:00:00"
            rows.append(_filled(ref, "long", 6000.0 + i, ts))
            rows.append(_stopped(ref, "long", 6000.0 + i, pnl_each, ts))
        return rows

    def test_null_computed_at_exactly_20_round_trips(self):
        rows = self._make_20_round_trips(pnl_each=10.0)
        progress = fsp.compute_progress(rows, bar_lookup=lambda ts: 6000.0,
                                        now_et=dt.datetime(2026, 7, 9, 16, 0, 0))
        assert progress["n_round_trips"] == 20
        assert progress["null_check"]["evaluated"] is True
        assert progress["null_check"]["coverage"] == "20/20"

    def test_beats_null_true_when_mirror_beats_flat_hold(self):
        rows = self._make_20_round_trips(pnl_each=100.0)
        # null bar_lookup returns the SAME price as entry -> every null trip is a scratch
        # (0 pts) minus commission -> negative null total; the real mirror (+100/trip) beats it.
        progress = fsp.compute_progress(
            rows, bar_lookup=lambda ts: 6000.0, now_et=dt.datetime(2026, 7, 9, 16, 0, 0))
        assert progress["arming_bar"]["beats_null"] is True

    def test_beats_null_false_when_null_wins(self):
        rows = self._make_20_round_trips(pnl_each=1.0)
        # null bar_lookup returns a huge favorable move for every long entry.
        progress = fsp.compute_progress(
            rows, bar_lookup=lambda ts: 9000.0, now_et=dt.datetime(2026, 7, 9, 16, 0, 0))
        assert progress["arming_bar"]["beats_null"] is False
        assert progress["arming_bar"]["armable"] is False

    def test_null_unavailable_for_all_trips_degrades_honestly(self):
        rows = self._make_20_round_trips(pnl_each=10.0)
        progress = fsp.compute_progress(
            rows, bar_lookup=lambda ts: None, now_et=dt.datetime(2026, 7, 9, 16, 0, 0))
        assert progress["null_check"]["evaluated"] is False
        assert progress["arming_bar"]["beats_null"] is None
        assert progress["arming_bar"]["armable"] is False   # never armable on unknown null

    def test_partial_null_coverage_disclosed(self):
        rows = self._make_20_round_trips(pnl_each=10.0)
        calls = {"n": 0}

        def _lookup(ts):
            calls["n"] += 1
            return None if calls["n"] <= 5 else 6000.0

        progress = fsp.compute_progress(rows, bar_lookup=_lookup,
                                        now_et=dt.datetime(2026, 7, 9, 16, 0, 0))
        assert progress["null_check"]["evaluated"] is True
        assert progress["null_check"]["unavailable"] == 5
        assert progress["null_check"]["coverage"] == "15/20"

    def test_armable_requires_all_three_conditions(self):
        """20 round trips + positive expectancy + beats_null=True -- change any ONE and
        armable must flip false."""
        rows = self._make_20_round_trips(pnl_each=100.0)
        progress = fsp.compute_progress(rows, bar_lookup=lambda ts: 6000.0,
                                        now_et=dt.datetime(2026, 7, 9, 16, 0, 0))
        assert progress["arming_bar"] == {
            "round_trips_needed": 20, "round_trips_have": 20,
            "expectancy_positive": True, "beats_null": True, "armable": True,
        }


# ═══════════════════════ buy-hold null math ══════════════════════════════════════
class TestComputeBuyholdNull:
    def test_long_null_pnl_matches_direction(self):
        trip = {"signal_ref": "a", "direction": "long", "entry": 6000.0,
               "entry_ts_et": "2026-07-09T10:06:00"}
        # deadline = next_trading_day(2026-07-09) = 2026-07-10 at DEADLINE_TIME_ET
        null_pnl = fsp.compute_buyhold_null(trip, lambda ts: 6050.0, entry_qty=2)
        expected = 50.0 * 5.0 * 2 - 1.24 * 2   # (exit-entry) * point_value * qty - commission*qty
        assert null_pnl == pytest.approx(expected)

    def test_short_null_pnl_inverts_sign(self):
        trip = {"signal_ref": "a", "direction": "short", "entry": 6000.0,
               "entry_ts_et": "2026-07-09T10:06:00"}
        null_pnl = fsp.compute_buyhold_null(trip, lambda ts: 5950.0, entry_qty=2)
        expected = 50.0 * 5.0 * 2 - 1.24 * 2
        assert null_pnl == pytest.approx(expected)

    def test_unavailable_lookup_returns_none(self):
        trip = {"signal_ref": "a", "direction": "long", "entry": 6000.0,
               "entry_ts_et": "2026-07-09T10:06:00"}
        assert fsp.compute_buyhold_null(trip, lambda ts: None, entry_qty=2) is None

    def test_missing_entry_fields_returns_none(self):
        trip = {"signal_ref": "a", "direction": "long", "entry_ts_et": "2026-07-09T10:06:00"}
        assert fsp.compute_buyhold_null(trip, lambda ts: 6050.0, entry_qty=2) is None

    def test_deadline_matches_next_trading_day_convention(self):
        """The deadline passed to bar_lookup must equal fms.next_trading_day(entry_date) at
        fms.DEADLINE_TIME_ET -- exactly reproducing open_mirror_position()'s own deadline
        without re-storing it in the ledger row."""
        seen = {}

        def _lookup(ts):
            seen["ts"] = ts
            return 6000.0

        trip = {"signal_ref": "a", "direction": "long", "entry": 6000.0,
               "entry_ts_et": "2026-07-10T10:06:00"}   # a Friday
        fsp.compute_buyhold_null(trip, _lookup, entry_qty=2)
        expected = dt.datetime.combine(fms.next_trading_day(dt.date(2026, 7, 10)),
                                       fms.DEADLINE_TIME_ET)
        assert seen["ts"] == expected
        assert expected.date() == dt.date(2026, 7, 13)   # Friday -> Monday


# ═══════════════════════ write_progress + main() fail-open ══════════════════════
class TestWriteProgressAndMain:
    def test_write_progress_atomic_round_trip(self, tmp_path):
        progress = {"n_round_trips": 5, "total_pnl_usd": 12.5}
        out = fsp.write_progress(progress, tmp_path / "shadow-progress.json")
        raw = json.loads(out.read_text(encoding="utf-8"))
        assert raw["n_round_trips"] == 5

    def test_progress_file_path_resolves_against_current_state_dir(self):
        """_progress_file() must read fms.STATE_DIR at CALL time, not bind it at import time
        -- otherwise a test's monkeypatch of fms.STATE_DIR would be silently ignored."""
        assert fsp._progress_file() == fms.STATE_DIR / "shadow-progress.json"

    def test_main_fail_open_on_missing_ledger_never_raises(self):
        assert fsp.main() == 0
        out = fsp._progress_file()
        assert out.exists()
        raw = json.loads(out.read_text(encoding="utf-8"))
        assert raw["n_round_trips"] == 0

    def test_main_never_calls_yfinance_below_20_round_trips(self, monkeypatch):
        """Regression guard for the network-call gate: below the floor, _default_bar_lookup_
        factory must never even be constructed (no yfinance import triggered)."""
        def _boom():
            raise AssertionError("must not be called below the 20-round-trip floor")

        monkeypatch.setattr(fsp, "_default_bar_lookup_factory", _boom)
        rows = [
            _filled("a", "long", 6000.0, "2026-07-09T10:06:00"),
            _stopped("a", "long", 6000.0, 50.0, "2026-07-09T10:20:00"),
        ]
        _write_ledger(rows)
        assert fsp.main() == 0   # would raise via the monkeypatched boom if the gate broke

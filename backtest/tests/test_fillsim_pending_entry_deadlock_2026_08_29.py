"""Guards for the 2026-08-29 pending_entry deadlock in fill_sim_broker.py + futures_eod.py.

THE BUG (diagnosed 2026-08-29, not re-derived here -- see the task/handoff for full
evidence): fill_sim_broker.is_flat() only recognized status=="open" while place_bracket()
refused a new order on status in ("pending_entry", "open"). A resting limit entry that
never filled (2026-08-14T10:50:04, MES short @ 7815.75, no expiry) therefore made every
subsequent tick believe it was FLAT, look for a new signal, clear every risk rail, and
then have place_bracket() silently refuse the placement anyway -- 60 ENTER_REFUSED rows,
0 fills, 15 sessions (2026-08-14 -> 2026-08-29), and futures_eod.py graded every one of
those sessions GREEN because nothing before this fix ever graded a refusal.

THE FIX has two parts and this file's classes mirror them:
  1. is_flat() and place_bracket() now consult ONE shared predicate
     (fill_sim_broker._is_active_position) so they can never disagree again, PLUS a
     pending_entry now expires (at the earlier of PENDING_ENTRY_MAX_AGE_MINUTES or the
     MINUTES_BEFORE_MAINTENANCE_FLATTEN cutoff) so the lane actually unsticks, not just
     correctly reports itself stuck forever.
  2. futures_eod.build() now grades a REFUSED-despite-cleared-rails session as YELLOW
     (single session) or RED (>= REFUSAL_RED_SESSIONS consecutive sessions sharing the
     same refusal reason) -- while an honest zero-signal quiet day still grades GREEN
     (sitting out is valid doctrine, J 2026-08-12; refusal is the failure signal, not
     absence of trades).

Every fill_sim_broker test here uses state_dir=tmp_path -- none of them ever touch real
automation/state/futures/. Every futures_eod test monkeypatches its ledger readers --
none of them touch the real decisions.jsonl / would-be-trades.jsonl either.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "setup" / "scripts"))

from futures.fill_sim_broker import (  # noqa: E402
    FillSimBroker, EV_PENDING_ENTRY_EXPIRED, PENDING_ENTRY_MAX_AGE_MINUTES,
)
from futures.futures_risk_rails import MINUTES_BEFORE_MAINTENANCE_FLATTEN  # noqa: E402


def _read_wbt(broker) -> list[dict]:
    if not broker.would_be_file.exists():
        return []
    return [json.loads(line) for line in
            broker.would_be_file.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_position(broker: FillSimBroker, instrument: str, row: dict | None) -> None:
    """Write the raw positions.json directly -- lets a test construct any status/shape
    (including ones no public API path produces, e.g. open+qty_open==0) without relying
    on private broker methods."""
    broker.positions_file.write_text(json.dumps({instrument: row}), encoding="utf-8")


# ═══════════════════ 1. is_flat() must treat pending_entry as NOT flat ════════════════
class TestIsFlatTreatsPendingAsNotFlat:
    def test_pending_entry_row_makes_is_flat_false(self, tmp_path):
        """RED-PROOF: pre-fix, is_flat() returned True here -- the bug itself."""
        broker = FillSimBroker(state_dir=tmp_path, start_equity=2000.0)
        broker.place_bracket("MES", "SELL", 1, 7815.75, 7815.0, 7826.1, runner_price=7810.75)
        assert broker.is_flat("MES") is False


# ═══════ 2. is_flat() and place_bracket() must AGREE for every status value ═══════════
_STATUS_TABLE = [
    ("no_position", None, True),
    ("pending_entry", {
        "status": "pending_entry", "instrument": "MES", "direction": "short", "side": "SELL",
        "qty": 1, "entry": 7815.75, "stop": 7826.1, "tp1": 7815.0, "runner": 7810.75,
        "tp1_qty": 1, "order_id": "FILLSIM-MES-BRK-x",
        "placed_time_et": "2026-08-14T10:50:04",
    }, False),
    ("open_with_qty_open", {
        "status": "open", "instrument": "MES", "direction": "long", "entry": 7800.0,
        "stop": 7790.0, "tp1": 7810.0, "runner": None, "qty_total": 2, "qty_open": 2,
        "tp1_qty": 1, "tp1_filled": False, "entry_time_et": "2026-08-14T10:00:00",
        "order_id": "FILLSIM-MES-BRK-y",
    }, False),
    ("open_zero_qty_open", {
        # Defensive/edge shape: an "open" row with nothing left open must NOT occupy the
        # slot -- matches is_flat()'s pre-existing qty_open>0 check on the "open" branch.
        "status": "open", "instrument": "MES", "direction": "long", "entry": 7800.0,
        "stop": 7790.0, "tp1": 7810.0, "runner": None, "qty_total": 2, "qty_open": 0,
        "tp1_qty": 1, "tp1_filled": True, "entry_time_et": "2026-08-14T10:00:00",
        "order_id": "FILLSIM-MES-BRK-z",
    }, True),
]


@pytest.mark.parametrize("label,row,expected_flat", _STATUS_TABLE)
def test_is_flat_and_place_bracket_agree_for_every_status(tmp_path, label, row, expected_flat):
    """Table-driven so the two can never drift apart again: for EVERY status shape this
    file's own code produces, is_flat()'s answer and place_bracket()'s refusal decision
    must be two views of the exact same fact."""
    broker = FillSimBroker(state_dir=tmp_path, start_equity=2000.0)
    if row is not None:
        _write_position(broker, "MES", row)

    assert broker.is_flat("MES") is expected_flat, label

    ids = broker.place_bracket("MES", "BUY", 1, 100.0, 110.0, 90.0)
    if expected_flat:
        assert ids, f"{label}: is_flat() said FLAT but place_bracket() refused anyway"
    else:
        assert ids == [], f"{label}: is_flat() said NOT FLAT but place_bracket() placed anyway"


# ═══════════════════ 3 + 4. expiry after max age -- clears + can re-enter + logs ══════
class TestMaxAgeExpiry:
    _PLACED = dt.datetime(2026, 8, 14, 10, 50, 4)
    _ROW = {
        "status": "pending_entry", "instrument": "MES", "direction": "short", "side": "SELL",
        "qty": 1, "entry": 7815.75, "stop": 7826.1, "tp1": 7815.0, "runner": 7810.75,
        "tp1_qty": 1, "order_id": "FILLSIM-MES-BRK-c6177bb6",
        "placed_time_et": _PLACED.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    def _broker(self, tmp_path) -> FillSimBroker:
        broker = FillSimBroker(state_dir=tmp_path, start_equity=2000.0)
        _write_position(broker, "MES", dict(self._ROW))
        return broker

    def test_still_fresh_before_max_age_does_not_expire(self, tmp_path):
        """RED-PROOF companion: proves the expiry check is actually AGE-gated, not just
        firing unconditionally on every process_quote() call."""
        broker = self._broker(tmp_path)
        still_fresh = self._PLACED + dt.timedelta(minutes=PENDING_ENTRY_MAX_AGE_MINUTES - 5)
        r = broker.process_quote("MES", 7800.0, quote_time_et=still_fresh)  # 7800 < entry: no touch
        assert r["event"] == "noop"
        assert broker.is_flat("MES") is False
        assert broker.get_positions_snapshot()["MES"]["status"] == "pending_entry"

    def test_stale_pending_entry_expires_and_lane_can_enter_again(self, tmp_path):
        broker = self._broker(tmp_path)
        stale = self._PLACED + dt.timedelta(minutes=PENDING_ENTRY_MAX_AGE_MINUTES + 5)

        r = broker.process_quote("MES", 7800.0, quote_time_et=stale)
        assert r["event"] == EV_PENDING_ENTRY_EXPIRED
        assert r["reason"] == "max_age"

        assert broker.get_positions_snapshot().get("MES") is None, "ghost order must be cleared"
        assert broker.is_flat("MES") is True, "the lane must read genuinely flat after expiry"

        ids = broker.place_bracket("MES", "BUY", 1, 7700.0, 7720.0, 7690.0)
        assert ids, "THE point of Task 1b: a new order must succeed once the stale one expired"

    def test_expiry_emits_an_explicit_greppable_event_with_age_and_original_price(self, tmp_path):
        broker = self._broker(tmp_path)
        stale = self._PLACED + dt.timedelta(minutes=PENDING_ENTRY_MAX_AGE_MINUTES + 10)

        ret = broker.process_quote("MES", 7815.75, quote_time_et=stale)

        events = _read_wbt(broker)
        assert [e["event"] for e in events] == [EV_PENDING_ENTRY_EXPIRED], (
            "expiry must write its OWN event -- silence is what let the real order sit "
            "for 15 sessions with nothing ever recorded about why it never cleared")
        logged = events[0]
        for d in (logged, ret):
            assert d["reason"] == "max_age"
            assert d["original_entry_price"] == 7815.75
            assert d["order_id"] == "FILLSIM-MES-BRK-c6177bb6"
        assert logged["age_minutes"] == pytest.approx(
            PENDING_ENTRY_MAX_AGE_MINUTES + 10, abs=0.1)


# ═══════════════ 5. force-expire at the maintenance cutoff, even if young ═════════════
class TestMaintenanceCutoffForcesExpiry:
    def test_young_pending_entry_still_force_expires_inside_the_cutoff_window(self, tmp_path):
        """A pending entry placed only 2 minutes ago (nowhere near
        PENDING_ENTRY_MAX_AGE_MINUTES) must still be force-cleared once the clock is
        inside MINUTES_BEFORE_MAINTENANCE_FLATTEN of the 17:00 ET settlement stop --
        carrying a resting order into the maintenance reset is exactly how a NEW ghost
        order would be born."""
        placed = dt.datetime(2026, 8, 17, 16, 51, 0)  # 9 minutes before 17:00 ET
        now = placed + dt.timedelta(minutes=2)         # only 2 min old
        minutes_to_stop = (
            dt.datetime.combine(now.date(), dt.time(17, 0)) - now
        ).total_seconds() / 60.0
        assert (now - placed).total_seconds() / 60.0 < PENDING_ENTRY_MAX_AGE_MINUTES, (
            "test setup sanity: must be younger than the max age, or this would just be "
            "re-testing test 3's max_age path instead of the cutoff path")
        assert 0 <= minutes_to_stop <= MINUTES_BEFORE_MAINTENANCE_FLATTEN, (
            "test setup sanity: must actually land inside the cutoff window")

        broker = FillSimBroker(state_dir=tmp_path, start_equity=2000.0)
        _write_position(broker, "MES", {
            "status": "pending_entry", "instrument": "MES", "direction": "long", "side": "BUY",
            "qty": 1, "entry": 7800.0, "stop": 7790.0, "tp1": 7810.0, "runner": None,
            "tp1_qty": 1, "order_id": "FILLSIM-MES-BRK-cutoff",
            "placed_time_et": placed.strftime("%Y-%m-%dT%H:%M:%S"),
        })

        r = broker.process_quote("MES", 7800.0, quote_time_et=now)
        assert r["event"] == EV_PENDING_ENTRY_EXPIRED
        assert r["reason"] == "maintenance_cutoff"
        assert broker.is_flat("MES") is True

    def test_outside_the_cutoff_window_a_young_order_is_untouched(self, tmp_path):
        """RED-PROOF companion for test 5: proves the cutoff check is actually WINDOW-
        gated (only fires near 17:00 ET), not an unconditional force-clear."""
        placed = dt.datetime(2026, 8, 17, 14, 0, 0)  # 3 hours before the stop
        now = placed + dt.timedelta(minutes=2)

        broker = FillSimBroker(state_dir=tmp_path, start_equity=2000.0)
        _write_position(broker, "MES", {
            "status": "pending_entry", "instrument": "MES", "direction": "long", "side": "BUY",
            "qty": 1, "entry": 7800.0, "stop": 7790.0, "tp1": 7810.0, "runner": None,
            "tp1_qty": 1, "order_id": "FILLSIM-MES-BRK-nocutoff",
            "placed_time_et": placed.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        r = broker.process_quote("MES", 7810.0, quote_time_et=now)  # 7810 > 7800: long not touched
        assert r["event"] == "noop"
        assert broker.is_flat("MES") is False


# ═══════════════ 6. futures_eod grades a refusal correctly (and honest quiet days) ════
class TestFuturesEodRefusalGrading:
    """These import futures_eod fresh each test and monkeypatch its ledger readers --
    the real analysis/futures-eod/ and automation/state/futures/trader/ files are never
    touched."""

    DATE = "2026-08-28"

    def _coverage_rows(self, n_hold: int, extra: dict | None = None) -> list[dict]:
        rows = [{"ts_et": f"{self.DATE}T10:{i:02d}:00", "action": "HOLD", "n_signals": 0,
                 "freshness": "GREEN"} for i in range(n_hold)]
        if extra:
            rows.append(extra)
        return rows

    def _patch_common(self, monkeypatch, eod, rows):
        monkeypatch.setattr(eod, "_read_ledger", lambda date: rows)
        monkeypatch.setattr(eod, "round_trips", lambda date, fills: {
            "fills": fills, "n": 0, "total_pnl": 0.0, "win_rate": None, "best": None,
            "worst": None, "by_setup": {}, "by_exit": {}, "rows": []})

    def test_refused_despite_cleared_rails_degrades_single_session_to_yellow(self, monkeypatch):
        from futures import futures_eod as eod  # noqa: PLC0415

        refused_row = {"ts_et": f"{self.DATE}T13:10:04", "action": "ENTER_REFUSED",
                       "n_signals": 1, "freshness": "GREEN", "reason": "ERL_IRL_SWEEP_FVG",
                       "entry": {"qty": 1, "risk_usd": 98.0, "stop": 7826.1}}
        rows = self._coverage_rows(77, extra=refused_row)  # 78 total -> full tick coverage
        self._patch_common(monkeypatch, eod, rows)
        monkeypatch.setattr(eod, "_placed_refused_by_date",
                            lambda: {self.DATE: Counter({"existing_pending_entry": 1})})

        d = eod.build(self.DATE)
        assert d["verdict"] == "YELLOW", d
        assert d["refusals"]["n"] == 1
        assert d["refusals"]["sessions"] == 1
        assert not d["rule_breaks"], "a refusal is not itself a rule-audit violation"
        # visible, not merely graded (Task 2's other requirement)
        rendered = eod.render(d)
        assert "Refusals" in rendered and "existing_pending_entry" in rendered

    def test_three_consecutive_sessions_of_the_same_refusal_degrade_to_red(self, monkeypatch):
        from futures import futures_eod as eod  # noqa: PLC0415

        refused_row = {"ts_et": f"{self.DATE}T13:10:04", "action": "ENTER_REFUSED",
                       "n_signals": 1, "freshness": "GREEN", "reason": "ERL_IRL_SWEEP_FVG",
                       "entry": {"qty": 1, "risk_usd": 98.0, "stop": 7826.1}}
        rows = self._coverage_rows(77, extra=refused_row)
        self._patch_common(monkeypatch, eod, rows)
        by_date = {
            "2026-08-26": Counter({"existing_pending_entry": 4}),  # Wed
            "2026-08-27": Counter({"existing_pending_entry": 5}),  # Thu
            self.DATE: Counter({"existing_pending_entry": 1}),      # Fri -- 3 in a row
        }
        monkeypatch.setattr(eod, "_placed_refused_by_date", lambda: by_date)

        d = eod.build(self.DATE)
        assert d["verdict"] == "RED", d
        assert d["refusals"]["sessions"] == 3

    def test_honest_zero_signal_quiet_day_still_grades_green(self, monkeypatch):
        """THE non-regression case (J 2026-08-12: sitting out is a valid day). Full tick
        coverage, zero signals, zero refusals -- must stay GREEN, not be swept up by the
        new grading."""
        from futures import futures_eod as eod  # noqa: PLC0415

        rows = self._coverage_rows(78)
        self._patch_common(monkeypatch, eod, rows)
        monkeypatch.setattr(eod, "_placed_refused_by_date", lambda: {})

        d = eod.build(self.DATE)
        assert d["verdict"] == "GREEN", d
        assert d["refusals"]["n"] == 0
        assert d["refusals"]["sessions"] == 0
        rendered = eod.render(d)
        assert "no refused placements" in rendered

"""Guards for fill_sim_broker.py -- the own-fill-sim paper broker for the futures swing lane
(FUTURES-REVIVAL-PLAN-2026-07-02.md sec 1.3/2d). Every test uses `state_dir=tmp_path` so
NONE of them ever touch real automation/state/futures/ (the real intraday tick's
position.json/decisions.jsonl/last-tick.json/loop-state.json live there and must never be
written by these guards -- see fill_sim_broker.py's module docstring point #1).

Covers the task's required bites:
  - limit-touch entry fill (long + short).
  - gap-through-stop fills WORSE than the stop, never AT it (non-vacuous: the naive "always
    fill at stop_price" behavior is asserted OUT explicitly).
  - TP1 partial + runner target/BE-stop (reuses futures_exit_manager.decide_exit).
  - state survives a process restart (two independent broker instances, same state_dir).
  - et_clock usage: both a static no-naive-datetime.now() guard AND a positive proof that
    _et_now() is actually threaded through (monkeypatched et_clock.et_now changes output).
  - no-stacking refusal, cancel_all, forced close_position, get_positions()/is_flat() shape.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "setup" / "scripts"))

from futures.fill_sim_broker import (  # noqa: E402
    FillSimBroker, gap_aware_stop_fill, EV_PLACED, EV_FILLED, EV_TP1, EV_STOP, EV_CLOSED,
)
from futures.instruments import MNQ  # noqa: E402
import et_clock  # noqa: E402


SRC = (REPO / "backtest" / "futures" / "fill_sim_broker.py").read_text(encoding="utf-8")


def _read_wbt(broker) -> list[dict]:
    if not broker.would_be_file.exists():
        return []
    return [json.loads(line) for line in
            broker.would_be_file.read_text(encoding="utf-8").splitlines() if line.strip()]


# ═══════════════════════ et_clock discipline ══════════════════════════════════
class TestEtClockDiscipline:
    def test_no_naive_datetime_now_in_source(self):
        """Static guard: fill_sim_broker.py must never call the naive datetime.now() (this
        rig runs Mountain time -- ET = local + 2h; CLAUDE.md TZ-systemic scar)."""
        assert "datetime.now(" not in SRC, (
            "fill_sim_broker.py calls naive datetime.now() -- must use et_clock.et_now() "
            "via the module's _et_now() helper instead")

    def test_et_now_is_actually_threaded_through(self, tmp_path, monkeypatch):
        """Positive proof (not just a grep): patching et_clock.et_now changes the timestamps
        fill_sim_broker actually writes -- proves _et_now() is live-wired, not dead code."""
        fixed = dt.datetime(2026, 1, 15, 10, 30, 0)
        monkeypatch.setattr(et_clock, "et_now", lambda: fixed)
        broker = FillSimBroker(state_dir=tmp_path, start_equity=2000.0)
        broker.place_bracket("MNQ", "BUY", 4, 21000.0, 21030.0, 20980.0, runner_price=21060.0)
        pending = broker.get_positions_snapshot()["MNQ"]
        assert pending["placed_time_et"] == "2026-01-15T10:30:00"
        events = _read_wbt(broker)
        assert events[0]["ts_et"] == "2026-01-15T10:30:00"


# ═══════════════════════ account seeding ══════════════════════════════════════
class TestAccountSeeding:
    def test_explicit_start_equity_overrides_risk_json(self, tmp_path):
        broker = FillSimBroker(state_dir=tmp_path, start_equity=9999.0)
        assert broker.get_account_equity() == 9999.0

    def test_default_seed_falls_back_when_risk_json_absent(self, tmp_path):
        # tmp_path has no risk.json sibling -- RISK_FILE points at the REAL repo path, which
        # DOES exist, so this documents (not fights) that seeding without an override reads
        # the real risk.json when present. We only assert it doesn't crash and returns a
        # sane positive number.
        broker = FillSimBroker(state_dir=tmp_path)
        eq = broker.get_account_equity()
        assert eq is not None and eq > 0

    def test_account_file_atomic_write_leaves_no_tmp_litter(self, tmp_path):
        broker = FillSimBroker(state_dir=tmp_path, start_equity=2000.0)
        tmp_files = list(tmp_path.glob("*.tmp*"))
        assert tmp_files == [], f"atomic write left temp file(s): {tmp_files}"


# ═══════════════════════ place_bracket (entry submission) ═════════════════════
class TestPlaceBracket:
    def test_places_pending_entry_returns_order_ids(self, tmp_path):
        broker = FillSimBroker(state_dir=tmp_path, start_equity=2000.0)
        ids = broker.place_bracket("MNQ", "BUY", 4, 21000.0, 21030.0, 20980.0,
                                   runner_price=21060.0, tp1_qty=2)
        assert ids, "place_bracket must return non-empty order ids on success"
        snap = broker.get_positions_snapshot()["MNQ"]
        assert snap["status"] == "pending_entry"
        assert snap["direction"] == "long"
        assert snap["tp1_qty"] == 2

    def test_logs_placed_event(self, tmp_path):
        broker = FillSimBroker(state_dir=tmp_path, start_equity=2000.0)
        broker.place_bracket("MNQ", "BUY", 4, 21000.0, 21030.0, 20980.0)
        events = _read_wbt(broker)
        assert len(events) == 1
        assert events[0]["event"] == EV_PLACED
        assert events[0]["instrument"] == "MNQ"

    def test_refuses_when_already_pending(self, tmp_path):
        """RED-PROOF: no-stacking (Rule 6 mirror) -- a second place_bracket on the SAME
        instrument while one is already pending/open must be refused, not silently overwrite."""
        broker = FillSimBroker(state_dir=tmp_path, start_equity=2000.0)
        first = broker.place_bracket("MNQ", "BUY", 4, 21000.0, 21030.0, 20980.0)
        assert first
        second = broker.place_bracket("MNQ", "BUY", 2, 21100.0, 21130.0, 21080.0)
        assert second == [], "a second place_bracket while one is pending MUST be refused"
        # original pending order must be untouched
        snap = broker.get_positions_snapshot()["MNQ"]
        assert snap["entry"] == 21000.0

    def test_refuses_when_already_open(self, tmp_path):
        broker = FillSimBroker(state_dir=tmp_path, start_equity=2000.0)
        broker.place_bracket("MNQ", "BUY", 4, 21000.0, 21030.0, 20980.0)
        broker.process_quote("MNQ", 21000.0, bar_open=20995.0, bar_high=21005.0, bar_low=20995.0)
        assert broker.get_positions_snapshot()["MNQ"]["status"] == "open"
        second = broker.place_bracket("MNQ", "SELL", 2, 20900.0, 20870.0, 20930.0)
        assert second == []

    def test_short_side_maps_to_short_direction(self, tmp_path):
        broker = FillSimBroker(state_dir=tmp_path, start_equity=2000.0)
        broker.place_bracket("MNQ", "SELL", 4, 21000.0, 20970.0, 21020.0)
        snap = broker.get_positions_snapshot()["MNQ"]
        assert snap["direction"] == "short"


# ═══════════════════ limit-touch entry fill (long + short) ════════════════════
class TestLimitTouchFill:
    def test_long_entry_fills_on_touch(self, tmp_path):
        broker = FillSimBroker(state_dir=tmp_path, start_equity=2000.0)
        broker.place_bracket("MNQ", "BUY", 4, 21000.0, 21030.0, 20980.0, runner_price=21060.0,
                             tp1_qty=2)
        r = broker.process_quote("MNQ", 21000.0, bar_open=21005.0, bar_high=21008.0,
                                 bar_low=20995.0)  # low touches the 21000 limit
        assert r["event"] == EV_FILLED
        assert r["fill_price"] == 21000.0
        snap = broker.get_positions_snapshot()["MNQ"]
        assert snap["status"] == "open"
        assert snap["qty_open"] == 4
        assert snap["entry"] == 21000.0

    def test_long_entry_does_not_fill_before_touch(self, tmp_path):
        """RED-PROOF: a bar that never reaches the limit must NOT fill."""
        broker = FillSimBroker(state_dir=tmp_path, start_equity=2000.0)
        broker.place_bracket("MNQ", "BUY", 4, 21000.0, 21030.0, 20980.0)
        r = broker.process_quote("MNQ", 21010.0, bar_open=21012.0, bar_high=21015.0,
                                 bar_low=21005.0)  # low=21005 never reaches 21000
        assert r["event"] == "noop"
        assert broker.get_positions_snapshot()["MNQ"]["status"] == "pending_entry"

    def test_short_entry_fills_on_touch(self, tmp_path):
        broker = FillSimBroker(state_dir=tmp_path, start_equity=2000.0)
        broker.place_bracket("MNQ", "SELL", 4, 21000.0, 20970.0, 21020.0)
        r = broker.process_quote("MNQ", 21000.0, bar_open=20995.0, bar_high=21005.0,
                                 bar_low=20990.0)  # high touches the 21000 short limit
        assert r["event"] == EV_FILLED
        assert r["fill_price"] == 21000.0

    def test_logs_filled_event(self, tmp_path):
        broker = FillSimBroker(state_dir=tmp_path, start_equity=2000.0)
        broker.place_bracket("MNQ", "BUY", 4, 21000.0, 21030.0, 20980.0)
        broker.process_quote("MNQ", 21000.0, bar_open=20995.0, bar_high=21005.0, bar_low=20995.0)
        events = _read_wbt(broker)
        assert [e["event"] for e in events] == [EV_PLACED, EV_FILLED]


# ═══════════ gap-aware stop fill -- THE non-vacuous requirement ═══════════════
class TestGapAwareStopFillPureFunction:
    """Direct unit tests of the pure gap_aware_stop_fill() helper -- isolates the fill-price
    math from the decide_exit()/state plumbing."""

    def test_long_normal_touch_fills_at_stop(self):
        # bar opened ABOVE the stop (20990 > 20980) -- a normal in-bar touch, not a gap.
        assert gap_aware_stop_fill("long", stop_price=20980.0, price=20975.0,
                                   bar_open=20990.0) == 20980.0

    def test_long_gap_fills_at_open_worse_than_stop(self):
        # bar OPENED below the stop -- a genuine gap. Must fill at the open (20950), which is
        # WORSE (lower) than the stop (20980) -- and explicitly NOT at the stop price.
        fill = gap_aware_stop_fill("long", stop_price=20980.0, price=20950.0, bar_open=20950.0)
        assert fill == 20950.0
        assert fill != 20980.0, "gap fill must NEVER equal the stop price (task requirement)"
        assert fill < 20980.0, "a long gap-down stop fill must be WORSE (lower) than the stop"

    def test_short_normal_touch_fills_at_stop(self):
        assert gap_aware_stop_fill("short", stop_price=21020.0, price=21025.0,
                                   bar_open=21010.0) == 21020.0

    def test_short_gap_fills_at_open_worse_than_stop(self):
        fill = gap_aware_stop_fill("short", stop_price=21020.0, price=21050.0, bar_open=21050.0)
        assert fill == 21050.0
        assert fill != 21020.0
        assert fill > 21020.0, "a short gap-up stop fill must be WORSE (higher) than the stop"

    def test_no_bar_open_falls_back_to_price(self):
        """When only a point quote is available (no bar), treat price as if it were the open --
        conservative (a lone quote past the stop with no bar context is itself gap-shaped)."""
        assert gap_aware_stop_fill("long", stop_price=20980.0, price=20960.0,
                                   bar_open=None) == 20960.0


class TestGapAwareStopFillThroughBroker:
    """End-to-end: process_quote() on an OPEN position actually applies the gap-aware price,
    not just the pure helper in isolation."""

    def _open_long(self, tmp_path, *, entry=21000.0, stop=20980.0, tp1=21030.0,
                   runner=21060.0, qty=4) -> FillSimBroker:
        broker = FillSimBroker(state_dir=tmp_path, start_equity=2000.0)
        broker.place_bracket("MNQ", "BUY", qty, entry, tp1, stop, runner_price=runner,
                             tp1_qty=qty // 2)
        broker.process_quote("MNQ", entry, bar_open=entry - 5, bar_high=entry + 3,
                             bar_low=entry - 5)
        assert broker.get_positions_snapshot()["MNQ"]["status"] == "open"
        return broker

    def test_at_stop_non_gap_fill_equals_stop_price(self, tmp_path):
        broker = self._open_long(tmp_path)
        r = broker.process_quote("MNQ", 20975.0, bar_open=20990.0, bar_high=20995.0,
                                 bar_low=20975.0)
        assert r["event"] == EV_STOP
        assert r["fill_price"] == 20980.0  # AT the stop -- bar_open(20990) was above the stop

    def test_gap_through_stop_fills_worse_never_at_stop(self, tmp_path):
        """THE non-vacuous bite: a gap-down open must fill BELOW the stop, and the test would
        RED against a naive "always fill at stop_price" implementation."""
        broker = self._open_long(tmp_path)
        r = broker.process_quote("MNQ", 20950.0, bar_open=20950.0, bar_high=20955.0,
                                 bar_low=20940.0)
        assert r["event"] == EV_STOP
        assert r["fill_price"] == 20950.0
        assert r["fill_price"] != 20980.0, "gap fill equalled the stop price -- gap logic is dead"
        # P&L must reflect the WORSE fill, not the stop price, else the ledger silently
        # under-reports the loss on every gap day.
        acct = broker.get_account_snapshot()
        expected_points_loss = (20950.0 - 21000.0) * MNQ.point_value * 4  # -400.0
        expected_commission = MNQ.round_turn_usd * 4
        expected_equity = 2000.0 + expected_points_loss - expected_commission
        assert acct["equity"] == pytest.approx(expected_equity)
        # sanity: the NON-gap fill would have lost less -- prove the two numbers really differ.
        non_gap_loss = (20980.0 - 21000.0) * MNQ.point_value * 4
        assert expected_points_loss < non_gap_loss, "gap loss must be strictly worse than a clean stop"


# ═══════════════════ TP1 partial + runner (reuses decide_exit) ════════════════
class TestTp1AndRunner:
    def _open_long(self, tmp_path) -> FillSimBroker:
        broker = FillSimBroker(state_dir=tmp_path, start_equity=2000.0)
        broker.place_bracket("MNQ", "BUY", 4, 21000.0, 21030.0, 20980.0, runner_price=21060.0,
                             tp1_qty=2)
        broker.process_quote("MNQ", 21000.0, bar_open=20995.0, bar_high=21005.0, bar_low=20995.0)
        return broker

    def test_tp1_partial_scales_out_and_moves_stop_to_be(self, tmp_path):
        broker = self._open_long(tmp_path)
        r = broker.process_quote("MNQ", 21030.0, bar_open=21015.0, bar_high=21031.0,
                                 bar_low=21010.0)
        assert r["event"] == EV_TP1
        assert r["exit_qty"] == 2
        assert r["fill_price"] == 21030.0
        snap = broker.get_positions_snapshot()["MNQ"]
        assert snap["status"] == "open"  # runner half still open
        assert snap["qty_open"] == 2
        assert snap["stop"] == 21000.0  # ratcheted to break-even (entry)
        # equity should have grown by the TP1 partial's P&L
        expected_pnl = (21030.0 - 21000.0) * MNQ.point_value * 2 - MNQ.round_turn_usd * 2
        assert broker.get_account_equity() == pytest.approx(2000.0 + expected_pnl)

    def test_runner_target_after_tp1_closes_fully(self, tmp_path):
        broker = self._open_long(tmp_path)
        broker.process_quote("MNQ", 21030.0, bar_open=21015.0, bar_high=21031.0, bar_low=21010.0)
        r = broker.process_quote("MNQ", 21060.0, bar_open=21040.0, bar_high=21061.0, bar_low=21040.0)
        assert r["event"] == EV_CLOSED
        assert r["fill_price"] == 21060.0
        assert broker.get_positions_snapshot()["MNQ"] is None  # fully flat

    def test_runner_be_stop_after_tp1_tags_as_stop(self, tmp_path):
        broker = self._open_long(tmp_path)
        broker.process_quote("MNQ", 21030.0, bar_open=21015.0, bar_high=21031.0, bar_low=21010.0)
        r = broker.process_quote("MNQ", 21000.0, bar_open=21005.0, bar_high=21010.0, bar_low=20999.0)
        assert r["event"] == EV_STOP
        assert r["fill_price"] == 21000.0  # break-even, non-gapped (bar_open 21005 > BE stop 21000)
        assert broker.get_positions_snapshot()["MNQ"] is None


# ═══════════════════════ state survives a process restart ═════════════════════
class TestStateSurvivesRestart:
    def test_pending_entry_survives_restart(self, tmp_path):
        a = FillSimBroker(state_dir=tmp_path, start_equity=2000.0)
        a.place_bracket("MNQ", "BUY", 4, 21000.0, 21030.0, 20980.0, runner_price=21060.0)

        b = FillSimBroker(state_dir=tmp_path)  # simulates a fresh process
        snap = b.get_positions_snapshot()["MNQ"]
        assert snap["status"] == "pending_entry"
        assert snap["entry"] == 21000.0
        assert snap["runner"] == 21060.0

    def test_open_position_and_equity_survive_restart(self, tmp_path):
        a = FillSimBroker(state_dir=tmp_path, start_equity=2000.0)
        a.place_bracket("MNQ", "BUY", 4, 21000.0, 21030.0, 20980.0, runner_price=21060.0,
                        tp1_qty=2)
        a.process_quote("MNQ", 21000.0, bar_open=20995.0, bar_high=21005.0, bar_low=20995.0)
        a.process_quote("MNQ", 21030.0, bar_open=21015.0, bar_high=21031.0, bar_low=21010.0)  # TP1

        b = FillSimBroker(state_dir=tmp_path)
        positions = b.get_positions()
        assert len(positions) == 1
        assert positions[0]["qty"] == 2  # runner half remains
        assert b.get_account_equity() == a.get_account_equity()

        # continue managing the SAME position from the new instance -- proves it's not just
        # readable but genuinely resumable.
        r = b.process_quote("MNQ", 21060.0, bar_open=21040.0, bar_high=21061.0, bar_low=21040.0)
        assert r["event"] == EV_CLOSED
        assert b.get_positions() == []


# ═══════════════════════ cancel_all / close_position ═══════════════════════════
class TestCancelAndClose:
    def test_cancel_all_cancels_pending(self, tmp_path):
        broker = FillSimBroker(state_dir=tmp_path, start_equity=2000.0)
        broker.place_bracket("MNQ", "BUY", 4, 21000.0, 21030.0, 20980.0)
        assert broker.cancel_all("MNQ") is True
        assert broker.get_positions_snapshot().get("MNQ") is None

    def test_cancel_all_noop_when_flat(self, tmp_path):
        broker = FillSimBroker(state_dir=tmp_path, start_equity=2000.0)
        assert broker.cancel_all("MNQ") is True

    def test_close_position_forces_partial_close(self, tmp_path):
        broker = FillSimBroker(state_dir=tmp_path, start_equity=2000.0)
        broker.place_bracket("MNQ", "BUY", 4, 21000.0, 21030.0, 20980.0)
        broker.process_quote("MNQ", 21000.0, bar_open=20995.0, bar_high=21005.0, bar_low=20995.0)
        ok = broker.close_position("MNQ", 2, "BUY", 21010.0)
        assert ok is True
        snap = broker.get_positions_snapshot()["MNQ"]
        assert snap["status"] == "open"
        assert snap["qty_open"] == 2  # 4 - 2 forced-closed

    def test_close_position_false_when_nothing_open(self, tmp_path):
        broker = FillSimBroker(state_dir=tmp_path, start_equity=2000.0)
        assert broker.close_position("MNQ", 1, "BUY", 21000.0) is False


# ═══════════════════════ get_positions() / is_flat() shape ════════════════════
class TestPositionsShape:
    def test_flat_broker_reports_flat(self, tmp_path):
        broker = FillSimBroker(state_dir=tmp_path, start_equity=2000.0)
        assert broker.is_flat("MNQ") is True
        assert broker.get_positions() == []

    def test_pending_entry_occupies_the_slot_but_is_not_a_position(self, tmp_path):
        """CORRECTED 2026-08-29 (was `test_pending_entry_is_still_flat`, asserting
        `is_flat() is True` here). That assertion was the bug itself, not a spec: a
        resting pending_entry is not a REALIZED position (get_positions() correctly
        stays empty -- unchanged below), but place_bracket() has ALWAYS refused a second
        order while one is pending (see TestPlaceBracket.test_refuses_when_already_pending
        above). The old is_flat()==True here meant the engine's OWN flatness check
        disagreed with what place_bracket() would actually do one line later -- exactly
        the 2026-08-14 pending_entry deadlock (is_flat() said FLAT, the engine went
        looking for and rails-cleared a new signal, and place_bracket() then silently
        refused it, every tick, for 15 sessions). is_flat() now means "available for a
        new place_bracket() call", matching place_bracket()'s own refusal condition via
        the shared _is_active_position() predicate -- see fill_sim_broker.py and
        test_fillsim_pending_entry_deadlock_2026_08_29.py for the full guard."""
        broker = FillSimBroker(state_dir=tmp_path, start_equity=2000.0)
        broker.place_bracket("MNQ", "BUY", 4, 21000.0, 21030.0, 20980.0)
        assert broker.is_flat("MNQ") is False
        assert broker.get_positions() == [], (
            "a pending_entry is still not a REALIZED position -- get_positions() is "
            "OPEN-only and must stay unaffected by the is_flat() fix")

    def test_open_short_reports_negative_qty(self, tmp_path):
        broker = FillSimBroker(state_dir=tmp_path, start_equity=2000.0)
        broker.place_bracket("MNQ", "SELL", 3, 21000.0, 20970.0, 21020.0)
        broker.process_quote("MNQ", 21000.0, bar_open=20995.0, bar_high=21005.0, bar_low=20990.0)
        assert broker.is_flat("MNQ") is False
        positions = broker.get_positions()
        assert positions[0]["qty"] == -3

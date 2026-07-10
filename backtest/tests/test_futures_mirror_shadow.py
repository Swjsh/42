"""Guards for setup/scripts/futures_mirror_shadow.py (JOB 1 -- MES forward shadow-mirror of
the live 0DTE SPY fleet signals).

Covers: cross-arm dedupe (the load-bearing "4 arms fire the same signal -> ONE mirror trade"
behavior), the frozen ATR-stop/TP1/trail math, the tp1 -> runner -> time-flat state machine on
fixture quotes (including the stop-first tie-break and the gap-aware stop fill), fail-open on
missing/corrupt state files and a raising fetcher, and the no-naive-datetime discipline.

Runs under either interpreter for the pure-logic tests; the ATR-fetch test monkeypatches
yfinance out entirely so it never touches the network.
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


# ─────────────────────────── fixtures / isolation ──────────────────────────────
@pytest.fixture(autouse=True)
def _isolate_state(monkeypatch, tmp_path):
    """Redirect every state path this module writes to a tmp dir -- guards must NEVER touch
    real automation/state/futures/* or automation/state/logs/* (matches
    test_futures_heartbeat.py's _isolate_state pattern: patch the module attribute, not just
    the directory constant, because each derived Path was computed once at import time)."""
    state_dir = tmp_path / "futures"
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(fms, "STATE_DIR", state_dir)
    monkeypatch.setattr(fms, "LOG_DIR", log_dir)
    monkeypatch.setattr(fms, "WATERMARK_FILE", state_dir / "mirror-shadow-state.json")
    monkeypatch.setattr(fms, "POSITIONS_FILE", state_dir / "mirror-positions.json")
    monkeypatch.setattr(fms, "WOULD_BE_FILE", state_dir / "mirror-would-be.jsonl")
    monkeypatch.setattr(fms, "CALENDAR_FILE", tmp_path / "does-not-exist-calendar.json")


def _write_decisions(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _hold_row(ts_et: str, arm_id: str) -> dict:
    return {"tick_id": None, "ts_et": ts_et, "arm_id": arm_id, "action": "HOLD",
           "side": None, "setup_name": None, "reason": "no qualifying setup"}


def _enter_row(ts_et: str, arm_id: str, action: str = "ENTER_BEAR", side: str = "P",
              setup_name: str = "BEARISH_REJECTION_RIDE_THE_RIBBON") -> dict:
    return {"tick_id": None, "ts_et": ts_et, "arm_id": arm_id, "action": action,
           "side": side, "setup_name": setup_name, "strike": 731, "qty": 4}


# ═══════════════════════ fleet scan + cross-arm dedupe ═════════════════════════
class TestScanArmLines:
    def test_finds_enter_rows_skips_hold(self):
        lines = [
            json.dumps(_hold_row("2026-07-09T10:00:00.000000-04:00", "safe-1")),
            json.dumps(_enter_row("2026-07-09T10:05:03.123456-04:00", "safe-1")),
            json.dumps(_hold_row("2026-07-09T10:06:00.000000-04:00", "safe-1")),
        ]
        candidates, new_count = fms.scan_arm_lines(lines, 0)
        assert new_count == 3
        assert len(candidates) == 1
        assert candidates[0]["direction"] == "short"
        assert candidates[0]["ts_et"] == dt.datetime(2026, 7, 9, 10, 5, 3, 123456)

    def test_watermark_skips_already_scanned_lines(self):
        lines = [json.dumps(_enter_row("2026-07-09T10:05:00-04:00", "safe-1"))]
        candidates, new_count = fms.scan_arm_lines(lines, 1)  # already past this line
        assert candidates == []
        assert new_count == 1

    def test_malformed_json_line_is_skipped_not_fatal(self):
        lines = ["{not json", json.dumps(_enter_row("2026-07-09T10:05:00-04:00", "safe-1"))]
        candidates, new_count = fms.scan_arm_lines(lines, 0)
        assert new_count == 2
        assert len(candidates) == 1

    def test_enter_bull_maps_to_long(self):
        lines = [json.dumps(_enter_row("2026-07-09T10:05:00-04:00", "safe-1",
                                       action="ENTER_BULL", side="C"))]
        candidates, _ = fms.scan_arm_lines(lines, 0)
        assert candidates[0]["direction"] == "long"


class TestDedupeSignals:
    def test_four_arms_same_signal_produce_one_mirror(self):
        """THE load-bearing behavior: all 4 fleet arms firing the identical setup within the
        same minute must collapse to exactly ONE mirror signal, with every arm recorded."""
        ts = "2026-07-09T10:05:00-04:00"
        candidates = []
        for arm in ("safe-3", "safe-1", "risky-1", "risky-3"):
            rows, _ = fms.scan_arm_lines([json.dumps(_enter_row(ts, arm))], 0)
            for r in rows:
                r["arm_id"] = arm
            candidates.extend(rows)
        assert len(candidates) == 4

        now = dt.datetime(2026, 7, 9, 10, 6, 0)
        unique, seen = fms.dedupe_signals(candidates, {}, now)
        assert len(unique) == 1
        assert unique[0]["direction"] == "short"
        assert unique[0]["source_arms"] == ["risky-1", "risky-3", "safe-1", "safe-3"]
        assert len(seen) == 1

    def test_different_minutes_stay_separate(self):
        c1 = {"direction": "short", "ts_et": dt.datetime(2026, 7, 9, 10, 5, 0),
             "arm_id": "safe-1", "setup_name": "X", "side": "P"}
        c2 = {"direction": "short", "ts_et": dt.datetime(2026, 7, 9, 10, 6, 0),
             "arm_id": "safe-1", "setup_name": "X", "side": "P"}
        unique, seen = fms.dedupe_signals([c1, c2], {}, dt.datetime(2026, 7, 9, 10, 7, 0))
        assert len(unique) == 2
        assert len(seen) == 2

    def test_opposite_direction_same_minute_stays_separate(self):
        c1 = {"direction": "short", "ts_et": dt.datetime(2026, 7, 9, 10, 5, 0),
             "arm_id": "safe-1", "setup_name": "X", "side": "P"}
        c2 = {"direction": "long", "ts_et": dt.datetime(2026, 7, 9, 10, 5, 0),
             "arm_id": "risky-1", "setup_name": "Y", "side": "C"}
        unique, _ = fms.dedupe_signals([c1, c2], {}, dt.datetime(2026, 7, 9, 10, 6, 0))
        assert len(unique) == 2

    def test_already_seen_key_is_not_reemitted_on_a_later_poll(self):
        c = {"direction": "short", "ts_et": dt.datetime(2026, 7, 9, 10, 5, 0),
            "arm_id": "safe-1", "setup_name": "X", "side": "P"}
        key = fms.signal_key("short", dt.datetime(2026, 7, 9, 10, 5, 0))
        seen = {key: "2026-07-09T10:06:00"}
        unique, _ = fms.dedupe_signals([c], seen, dt.datetime(2026, 7, 9, 10, 11, 0))
        assert unique == []

    def test_prunes_seen_keys_older_than_retention(self):
        now = dt.datetime(2026, 7, 9, 12, 0, 0)
        stale_dt = now - dt.timedelta(days=fms.SIGNAL_KEY_RETENTION_DAYS + 1)
        fresh_dt = now - dt.timedelta(hours=1)
        seen = {"short|2026-07-01T09:00": stale_dt.strftime("%Y-%m-%dT%H:%M:%S"),
               "short|2026-07-09T11:00": fresh_dt.strftime("%Y-%m-%dT%H:%M:%S")}
        _, pruned = fms.dedupe_signals([], seen, now)
        assert "short|2026-07-01T09:00" not in pruned
        assert "short|2026-07-09T11:00" in pruned


class TestPruneStalePending:
    def test_drops_signals_older_than_max_age(self):
        now = dt.datetime(2026, 7, 9, 12, 0, 0)
        old = {"signal_ref": "x", "ts_et": (now - dt.timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S")}
        new = {"signal_ref": "y", "ts_et": (now - dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")}
        out = fms._prune_stale_pending([old, new], now)
        assert [s["signal_ref"] for s in out] == ["y"]


# ═══════════════════════ next_trading_day (2-session horizon) ═══════════════════
class TestNextTradingDay:
    def test_weekday_to_weekday(self):
        assert fms.next_trading_day(dt.date(2026, 7, 8), holidays=set()) == dt.date(2026, 7, 9)

    def test_friday_skips_to_monday(self):
        assert fms.next_trading_day(dt.date(2026, 7, 10), holidays=set()) == dt.date(2026, 7, 13)

    def test_skips_a_holiday(self):
        # 2026-01-19 is a real holiday in automation/state/calendar.json (MLK day).
        holidays = {"2026-01-19"}
        assert fms.next_trading_day(dt.date(2026, 1, 16), holidays=holidays) == dt.date(2026, 1, 20)

    def test_fail_open_unreadable_calendar_degrades_to_weekend_only(self):
        # CALENDAR_FILE is monkeypatched to a nonexistent path by the autouse fixture.
        result = fms.next_trading_day(dt.date(2026, 7, 10))  # holidays=None -> loads from disk
        assert result == dt.date(2026, 7, 13)


# ═══════════════════════ entry math (frozen ATR-stop spec) ═════════════════════
class TestEntryLevels:
    """Formula-correctness tests -- derive the expected R off the LIVE STOP_ATR_MULT constant
    (not a pinned literal) so a deliberate future spec bump doesn't require editing these; the
    constant's actual VALUE is pinned separately in TestSpecConstantsPinned (drift REDs
    there)."""

    def test_long_stop_below_tp1_above(self):
        levels = fms.compute_entry_levels("long", entry_price=6000.0, atr=10.0)
        expected_r = fms.STOP_ATR_MULT * 10.0                      # v2: 2.0 * ATR
        assert levels["r_points"] == pytest.approx(expected_r)
        assert levels["stop"] == pytest.approx(6000.0 - expected_r)
        assert levels["tp1"] == pytest.approx(6000.0 + expected_r)  # 1R favorable (TP1_R_MULT=1.0)

    def test_short_stop_above_tp1_below(self):
        levels = fms.compute_entry_levels("short", entry_price=6000.0, atr=10.0)
        expected_r = fms.STOP_ATR_MULT * 10.0
        assert levels["r_points"] == pytest.approx(expected_r)
        assert levels["stop"] == pytest.approx(6000.0 + expected_r)
        assert levels["tp1"] == pytest.approx(6000.0 - expected_r)

    def test_open_mirror_position_deadline_is_next_trading_day_1555(self):
        signal = {"signal_ref": "short|2026-07-09T10:05", "direction": "short",
                 "source_arms": ["safe-1"], "setup_name": "X"}
        now = dt.datetime(2026, 7, 9, 10, 6, 0)
        pos = fms.open_mirror_position(signal, entry_price=6000.0, atr=10.0, now_et=now)
        assert pos["qty_open"] == fms.ENTRY_QTY == 2
        assert pos["tp1_filled"] is False
        assert pos["hwm"] is None
        assert pos["deadline_et"] == "2026-07-10T15:55:00"        # next weekday, 15:55 ET


# ═══════════════════════ exit state machine (tp1 / runner / time-flat) ═════════
class TestDecideMirrorExit:
    def _long_position(self, **overrides) -> dict:
        base = {
            "signal_ref": "long|2026-07-09T10:05", "direction": "long", "status": "open",
            "qty_open": 2, "entry": 6000.0, "stop": 5985.0, "tp1": 6015.0, "r_points": 15.0,
            "tp1_filled": False, "hwm": None,
            "entry_time_et": "2026-07-09T10:06:00", "deadline_et": "2026-07-10T15:55:00",
            "closed_at_et": None, "source_arms": ["safe-1"], "setup_name": "X",
            "atr_at_entry": 10.0,
        }
        base.update(overrides)
        return base

    def test_hold_when_nothing_touched(self):
        pos = self._long_position()
        now = dt.datetime(2026, 7, 9, 10, 10, 0)
        row, new_pos = fms.decide_mirror_exit(pos, price=6001.0, now_et=now)
        assert row is None
        assert new_pos == pos

    def test_full_stop_pre_tp1_long(self):
        pos = self._long_position()
        now = dt.datetime(2026, 7, 9, 10, 10, 0)
        row, new_pos = fms.decide_mirror_exit(pos, price=5985.0, now_et=now)
        assert row["event"] == fms.EV_STOPPED
        assert row["exit_qty"] == 2
        assert row["pnl_pts"] == pytest.approx(-15.0)
        assert new_pos["status"] == "closed"
        assert new_pos["qty_open"] == 0

    def test_full_stop_pre_tp1_short(self):
        pos = self._long_position(direction="short", entry=6000.0, stop=6015.0, tp1=5985.0)
        now = dt.datetime(2026, 7, 9, 10, 10, 0)
        row, new_pos = fms.decide_mirror_exit(pos, price=6015.0, now_et=now)
        assert row["event"] == fms.EV_STOPPED
        assert row["pnl_pts"] == pytest.approx(-15.0)
        assert new_pos["status"] == "closed"

    def test_gap_through_stop_fills_worse_than_nominal(self):
        """Reuse of fill_sim_broker.gap_aware_stop_fill: a poll that observes price already
        well past the stop must fill at the OBSERVED price, not the nominal stop level."""
        pos = self._long_position()
        now = dt.datetime(2026, 7, 9, 10, 10, 0)
        row, _ = fms.decide_mirror_exit(pos, price=5950.0, now_et=now)  # 35pts past the stop
        assert row["fill_price"] == pytest.approx(5950.0)
        assert row["fill_price"] != pytest.approx(5985.0)
        assert row["pnl_pts"] == pytest.approx(-50.0)

    def test_tp1_touch_scales_half_and_moves_stop_to_breakeven(self):
        pos = self._long_position()
        now = dt.datetime(2026, 7, 9, 10, 10, 0)
        row, new_pos = fms.decide_mirror_exit(pos, price=6015.0, now_et=now)
        assert row["event"] == fms.EV_TP1
        assert row["exit_qty"] == fms.TP1_QTY == 1
        assert row["pnl_pts"] == pytest.approx(15.0)
        assert new_pos["qty_open"] == 1
        assert new_pos["tp1_filled"] is True
        assert new_pos["stop"] == pytest.approx(6000.0)            # breakeven
        assert new_pos["hwm"] == pytest.approx(6015.0)
        assert new_pos["status"] == "open"                          # runner still working

    def test_runner_trail_ratchets_hwm_then_stops_out(self):
        # Start already past TP1: runner open, stop at BE, hwm at the TP1 fill price.
        pos = self._long_position(qty_open=1, tp1_filled=True, stop=6000.0, hwm=6015.0)
        now = dt.datetime(2026, 7, 9, 10, 15, 0)

        # Poll 1: price makes a new high -> HWM ratchets, trailing stop moves up, no event.
        row1, pos1 = fms.decide_mirror_exit(pos, price=6040.0, now_et=now)
        assert row1 is None
        assert pos1["hwm"] == pytest.approx(6040.0)
        assert pos1["stop"] == pytest.approx(6025.0)                # 6040 - 1R(15)

        # Poll 2: price pulls back through the NEW trailing stop -> stopped out.
        row2, pos2 = fms.decide_mirror_exit(pos1, price=6020.0, now_et=now + dt.timedelta(minutes=5))
        assert row2["event"] == fms.EV_STOPPED
        assert row2["reason"] == "trail_stop_off_hwm"
        assert row2["exit_qty"] == 1
        assert pos2["status"] == "closed"
        # Trailed stop (6025) beat the original breakeven (6000) -- proves the runner
        # never falls back to a fixed target, only the ratcheted 1R-off-HWM trail.
        assert row2["pnl_pts"] > 0

    def test_runner_never_hits_a_fixed_target_only_trails(self):
        """No matter how far price runs, a runner-phase position only ever emits HOLD
        (silent ratchet) or STOPPED -- there is no RUNNER_TARGET-style event in the mirror's
        vocabulary (task spec: trail 1R off HWM, no fixed runner target)."""
        pos = self._long_position(qty_open=1, tp1_filled=True, stop=6000.0, hwm=6015.0)
        now = dt.datetime(2026, 7, 9, 10, 15, 0)
        row, new_pos = fms.decide_mirror_exit(pos, price=6500.0, now_et=now)
        assert row is None
        assert new_pos["status"] == "open"
        assert new_pos["hwm"] == pytest.approx(6500.0)

    def test_time_flat_flattens_full_qty_pre_tp1(self):
        pos = self._long_position()
        deadline = dt.datetime.strptime(pos["deadline_et"], "%Y-%m-%dT%H:%M:%S")
        row, new_pos = fms.decide_mirror_exit(pos, price=6010.0, now_et=deadline)
        assert row["event"] == fms.EV_TIME_FLAT
        assert row["exit_qty"] == 2
        assert row["fill_price"] == pytest.approx(6010.0)
        assert new_pos["status"] == "closed"

    def test_time_flat_flattens_runner_only_post_tp1(self):
        pos = self._long_position(qty_open=1, tp1_filled=True, stop=6000.0, hwm=6020.0)
        deadline = dt.datetime.strptime(pos["deadline_et"], "%Y-%m-%dT%H:%M:%S")
        row, new_pos = fms.decide_mirror_exit(pos, price=6018.0, now_et=deadline + dt.timedelta(minutes=1))
        assert row["event"] == fms.EV_TIME_FLAT
        assert row["exit_qty"] == 1
        assert new_pos["status"] == "closed"

    def test_time_flat_checked_before_stop(self):
        """Deadline is an unconditional flatten -- fires even if price is also past the stop
        this same poll (matches decide_exit's documented priority: TIME_STOP checked first)."""
        pos = self._long_position()
        deadline = dt.datetime.strptime(pos["deadline_et"], "%Y-%m-%dT%H:%M:%S")
        row, _ = fms.decide_mirror_exit(pos, price=5900.0, now_et=deadline)  # also past the stop
        assert row["event"] == fms.EV_TIME_FLAT
        assert row["fill_price"] == pytest.approx(5900.0)          # market flatten, not gap-fill

    def test_already_closed_position_is_a_pure_noop(self):
        pos = self._long_position(status="closed", qty_open=0)
        row, new_pos = fms.decide_mirror_exit(pos, price=5000.0, now_et=dt.datetime(2026, 7, 9, 10, 10))
        assert row is None
        assert new_pos == pos

    def test_decide_mirror_exit_never_mutates_input(self):
        pos = self._long_position()
        snapshot = json.loads(json.dumps(pos))
        fms.decide_mirror_exit(pos, price=6015.0, now_et=dt.datetime(2026, 7, 9, 10, 10))
        assert pos == snapshot


# ═══════════════════════ fail-open ══════════════════════════════════════════════
class TestFailOpen:
    def test_load_json_missing_file_returns_default(self, tmp_path):
        default = {"a": 1}
        out = fms._load_json(tmp_path / "nope.json", default)
        assert out == default
        assert out is not default  # a fresh copy, not the same object

    def test_load_json_corrupt_file_returns_default(self, tmp_path):
        p = tmp_path / "corrupt.json"
        p.write_text("{not valid json", encoding="utf-8")
        out = fms._load_json(p, {"a": 1})
        assert out == {"a": 1}

    def test_load_watermark_state_missing_gives_sane_defaults(self):
        state = fms.load_watermark_state()
        assert state["arm_line_watermarks"] == {}
        assert state["pending_signals"] == []
        assert state["spec_version"] == fms.SPEC_VERSION  # fresh install starts on CURRENT spec

    def test_run_once_survives_raising_quote_fetcher(self, tmp_path):
        def _boom():
            raise RuntimeError("yfinance is down")

        summary = fms.run_once(now_et=dt.datetime(2026, 7, 9, 10, 0, 0),
                               quote_fetcher=_boom, atr_fetcher=_boom, fleet_files=[])
        assert summary["errors"] == []  # nothing to fetch for (no pending, no open positions)

    def test_run_once_survives_raising_fetcher_with_a_real_signal(self, tmp_path):
        arm_file = tmp_path / "safe-1" / "decisions.jsonl"
        arm_file.parent.mkdir(parents=True, exist_ok=True)
        arm_file.touch()
        # Prime the watermark (cold start consumes the empty file with zero candidates)
        # BEFORE the signal under test is appended -- see TestColdStart.
        fms.run_once(now_et=dt.datetime(2026, 7, 9, 10, 0, 0),
                    quote_fetcher=lambda: 6000.0, atr_fetcher=lambda: 10.0, fleet_files=[arm_file])
        _write_decisions(arm_file, [_enter_row("2026-07-09T10:05:00-04:00", "safe-1")])

        def _boom():
            raise RuntimeError("yfinance is down")

        summary = fms.run_once(now_et=dt.datetime(2026, 7, 9, 10, 6, 0),
                               quote_fetcher=_boom, atr_fetcher=_boom, fleet_files=[arm_file])
        assert summary["new_signals"] == 1
        assert summary["opened"] == 0
        assert summary["pending_retry"] == 1          # retried next poll, never dropped
        assert any("quote_fetch_failed" in e for e in summary["errors"])

    def test_run_once_missing_fleet_file_is_not_fatal(self, tmp_path):
        summary = fms.run_once(now_et=dt.datetime(2026, 7, 9, 10, 0, 0),
                               quote_fetcher=lambda: 6000.0, atr_fetcher=lambda: 10.0,
                               fleet_files=[tmp_path / "ghost" / "decisions.jsonl"])
        assert summary["new_signals"] == 0
        assert summary["errors"] == []

    def test_run_once_end_to_end_dedupes_and_opens_one_position(self, tmp_path):
        ts = "2026-07-09T10:05:00-04:00"
        arm_files = []
        for arm in ("safe-3", "safe-1", "risky-1", "risky-3"):
            p = tmp_path / arm / "decisions.jsonl"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch()
            arm_files.append(p)
        # Prime the watermark for all 4 arms (cold start) before the shared signal fires.
        fms.run_once(now_et=dt.datetime(2026, 7, 9, 10, 0, 0),
                    quote_fetcher=lambda: 6000.0, atr_fetcher=lambda: 10.0, fleet_files=arm_files)
        for p, arm in zip(arm_files, ("safe-3", "safe-1", "risky-1", "risky-3")):
            _write_decisions(p, [_enter_row(ts, arm)])

        summary = fms.run_once(now_et=dt.datetime(2026, 7, 9, 10, 6, 0),
                               quote_fetcher=lambda: 6000.0, atr_fetcher=lambda: 10.0,
                               fleet_files=arm_files)
        assert summary["new_signals"] == 1
        assert summary["opened"] == 1
        assert summary["positions_open"] == 1

        positions = fms.load_positions_state()["positions"]
        assert len(positions) == 1
        pos = next(iter(positions.values()))
        assert sorted(pos["source_arms"]) == ["risky-1", "risky-3", "safe-1", "safe-3"]

        would_be_lines = fms.WOULD_BE_FILE.read_text(encoding="utf-8").splitlines()
        parsed = [json.loads(l) for l in would_be_lines]
        assert "_doc" in parsed[0]                                   # arming-bar header first
        events = [r["event"] for r in parsed if "_doc" not in r]
        assert events == [fms.EV_PLACED, fms.EV_FILLED]

    def test_second_poll_does_not_reopen_already_seen_signal(self, tmp_path):
        ts = "2026-07-09T10:05:00-04:00"
        p = tmp_path / "safe-1" / "decisions.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
        fms.run_once(now_et=dt.datetime(2026, 7, 9, 9, 55, 0),  # prime (cold start)
                    quote_fetcher=lambda: 6000.0, atr_fetcher=lambda: 10.0, fleet_files=[p])
        _write_decisions(p, [_enter_row(ts, "safe-1")])

        fms.run_once(now_et=dt.datetime(2026, 7, 9, 10, 6, 0),
                    quote_fetcher=lambda: 6000.0, atr_fetcher=lambda: 10.0, fleet_files=[p])
        summary2 = fms.run_once(now_et=dt.datetime(2026, 7, 9, 10, 11, 0),
                                quote_fetcher=lambda: 6001.0, atr_fetcher=lambda: 10.0,
                                fleet_files=[p])
        assert summary2["new_signals"] == 0
        assert summary2["positions_open"] == 1


class TestColdStart:
    def test_first_ever_scan_of_an_arm_mirrors_nothing(self, tmp_path):
        """A fresh watermark (arm never scanned before) must jump to end-of-file with zero
        candidates -- historical backlog is never retroactively mirrored with today's quote."""
        p = tmp_path / "safe-1" / "decisions.jsonl"
        _write_decisions(p, [
            _enter_row("2026-06-01T10:05:00-04:00", "safe-1"),   # 5+ weeks stale
            _enter_row("2026-07-09T09:00:00-04:00", "safe-1"),   # today, still stale-relative-to-cold-start
        ])
        summary = fms.run_once(now_et=dt.datetime(2026, 7, 9, 10, 0, 0),
                               quote_fetcher=lambda: 6000.0, atr_fetcher=lambda: 10.0,
                               fleet_files=[p])
        assert summary["new_signals"] == 0
        assert summary["opened"] == 0
        state = fms.load_watermark_state()
        assert state["arm_line_watermarks"]["safe-1"] == 2   # watermark still advances

    def test_signal_written_after_cold_start_is_mirrored_on_next_poll(self, tmp_path):
        p = tmp_path / "safe-1" / "decisions.jsonl"
        _write_decisions(p, [_enter_row("2026-06-01T10:05:00-04:00", "safe-1")])
        fms.run_once(now_et=dt.datetime(2026, 7, 9, 10, 0, 0),
                    quote_fetcher=lambda: 6000.0, atr_fetcher=lambda: 10.0, fleet_files=[p])

        _write_decisions(p, [_enter_row("2026-07-09T10:30:00-04:00", "safe-1")])
        summary2 = fms.run_once(now_et=dt.datetime(2026, 7, 9, 10, 35, 0),
                                quote_fetcher=lambda: 6000.0, atr_fetcher=lambda: 10.0,
                                fleet_files=[p])
        assert summary2["new_signals"] == 1
        assert summary2["opened"] == 1

    def test_new_arm_added_later_gets_its_own_cold_start_without_disturbing_others(self, tmp_path):
        p1 = tmp_path / "safe-1" / "decisions.jsonl"
        _write_decisions(p1, [_enter_row("2026-06-01T10:05:00-04:00", "safe-1")])
        fms.run_once(now_et=dt.datetime(2026, 7, 9, 10, 0, 0),
                    quote_fetcher=lambda: 6000.0, atr_fetcher=lambda: 10.0, fleet_files=[p1])

        p2 = tmp_path / "risky-1" / "decisions.jsonl"
        _write_decisions(p2, [_enter_row("2026-06-01T10:05:00-04:00", "risky-1")])
        summary = fms.run_once(now_et=dt.datetime(2026, 7, 9, 10, 5, 0),
                               quote_fetcher=lambda: 6000.0, atr_fetcher=lambda: 10.0,
                               fleet_files=[p1, p2])
        assert summary["new_signals"] == 0   # risky-1 cold-starts too, safe-1 has nothing new
        state = fms.load_watermark_state()
        assert state["arm_line_watermarks"] == {"safe-1": 1, "risky-1": 1}


# ═══════════════════════ SPEC v2 constants pinned (drift REDs) ══════════════════
class TestSpecConstantsPinned:
    """SPEC v2 (2026-07-09) -- see module docstring "SPEC v1 -> v2" for the backfill citation
    (analysis/recommendations/mirror-spec-backfill-sanity.json) and full rationale: NO cell in
    the declared 6-cell grid had positive expectancy in that pre-forward sanity check, so v2
    was chosen on the noise-ratio argument alone (atr_mult=2.0 nearly halves v1's
    single-bar-range/stop-distance ratio, from ~0.66 to ~0.494/0.495). A silent drift on any
    of these constants must RED this test, not slip through unnoticed."""

    def test_spec_version_is_v2(self):
        assert fms.SPEC_VERSION == "v2"

    def test_stop_atr_mult_is_2_0(self):
        assert fms.STOP_ATR_MULT == 2.0

    def test_tp1_r_mult_unchanged_from_v1(self):
        assert fms.TP1_R_MULT == 1.0

    def test_trail_r_mult_unchanged_from_v1(self):
        assert fms.TRAIL_R_MULT == 1.0

    def test_r_points_reflects_the_v2_multiple(self):
        levels = fms.compute_entry_levels("long", entry_price=6000.0, atr=10.0)
        assert levels["r_points"] == pytest.approx(20.0)     # 2.0 * ATR, not v1's 1.5 * ATR

    def test_arming_bar_doc_reflects_current_stop_mult_not_v1(self):
        assert "2.0xATR14" in fms.ARMING_BAR_DOC
        assert "1.5xATR14" not in fms.ARMING_BAR_DOC
        assert "v2" in fms.ARMING_BAR_DOC


# ═══════════════════════ spec-version ledger migration ══════════════════════════
class TestSpecVersionMigration:
    """Covers the v1 -> v2 (and any future spec bump) ledger-reset path: an old-spec
    mirror-would-be.jsonl holding REAL round-trips must be archived, never silently deleted
    or merged into the new spec's arming-bar count; a ledger holding only the `_doc` header
    (today's real-world state -- the v1 forward ledger never accumulated a single closed
    round-trip) is not evidence worth archiving."""

    def _write_ledger(self, rows: list[dict]) -> None:
        fms.WOULD_BE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(fms.WOULD_BE_FILE, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")

    # ── _ledger_has_real_rows ──
    def test_ledger_has_real_rows_true_for_lifecycle_row(self):
        self._write_ledger([{"_doc": "x"}, {"event": "placed", "signal_ref": "a"}])
        assert fms._ledger_has_real_rows(fms.WOULD_BE_FILE) is True

    def test_ledger_has_real_rows_false_for_doc_only(self):
        self._write_ledger([{"_doc": "x"}])
        assert fms._ledger_has_real_rows(fms.WOULD_BE_FILE) is False

    def test_ledger_has_real_rows_false_for_missing_file(self, tmp_path):
        assert fms._ledger_has_real_rows(tmp_path / "nope.jsonl") is False

    # ── _migrate_spec_version_if_needed / _archive_or_reset_ledger_for_migration ──
    def test_migration_archives_ledger_with_real_rows(self):
        """THE load-bearing path: a prior-spec ledger holding real round-trips gets renamed
        to mirror-would-be.v1-archive.jsonl, never silently deleted or merged into v2."""
        self._write_ledger([
            {"_doc": "old v1 arming bar text"},
            {"event": "placed", "signal_ref": "short|2026-07-08T10:05"},
            {"event": "filled", "signal_ref": "short|2026-07-08T10:05"},
        ])
        wm_state = {"arm_line_watermarks": {"safe-1": 10}, "seen_signal_keys": {},
                   "pending_signals": [], "last_run_et": "2026-07-08T10:00:00"}

        new_state = fms._migrate_spec_version_if_needed(wm_state)

        assert new_state["spec_version"] == fms.SPEC_VERSION
        assert new_state["arm_line_watermarks"] == {"safe-1": 10}      # untouched by migration
        assert new_state is not wm_state                                # never mutates input
        assert "spec_version" not in wm_state

        archive_path = fms.STATE_DIR / "mirror-would-be.v1-archive.jsonl"
        assert archive_path.exists()
        archived = [json.loads(l) for l in archive_path.read_text(encoding="utf-8").splitlines()]
        assert len(archived) == 3
        assert archived[1]["signal_ref"] == "short|2026-07-08T10:05"
        assert not fms.WOULD_BE_FILE.exists()            # renamed away, not copied

    def test_migration_with_doc_only_ledger_creates_no_archive(self):
        """Real-world case as of 2026-07-09: the v1 forward ledger held ZERO closed
        round-trips (only the arming-bar _doc header) -- nothing worth archiving."""
        self._write_ledger([{"_doc": "old v1 arming bar text"}])
        wm_state = {"arm_line_watermarks": {}, "seen_signal_keys": {}, "pending_signals": []}

        new_state = fms._migrate_spec_version_if_needed(wm_state)

        assert new_state["spec_version"] == fms.SPEC_VERSION
        archive_path = fms.STATE_DIR / "mirror-would-be.v1-archive.jsonl"
        assert not archive_path.exists()
        assert not fms.WOULD_BE_FILE.exists()    # stale header removed; caller regenerates it

    def test_migration_absent_spec_version_defaults_archive_label_to_v1(self):
        self._write_ledger([{"_doc": "x"}, {"event": "placed", "signal_ref": "a"}])
        new_state = fms._migrate_spec_version_if_needed({})
        assert (fms.STATE_DIR / "mirror-would-be.v1-archive.jsonl").exists()
        assert new_state["spec_version"] == fms.SPEC_VERSION

    def test_migration_labels_archive_after_the_actual_prior_version(self):
        self._write_ledger([{"_doc": "x"}, {"event": "placed", "signal_ref": "a"}])
        fms._migrate_spec_version_if_needed({"spec_version": "v2-preview"})
        assert (fms.STATE_DIR / "mirror-would-be.v2-preview-archive.jsonl").exists()

    def test_migration_is_a_noop_when_already_current(self):
        self._write_ledger([{"_doc": "x"}, {"event": "placed", "signal_ref": "a"}])
        wm_state = {"spec_version": fms.SPEC_VERSION, "arm_line_watermarks": {}}

        new_state = fms._migrate_spec_version_if_needed(wm_state)

        assert new_state is wm_state                      # same object, zero side effect
        assert fms.WOULD_BE_FILE.exists()                  # untouched
        rows = [json.loads(l) for l in fms.WOULD_BE_FILE.read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 2
        assert not (fms.STATE_DIR / "mirror-would-be.v1-archive.jsonl").exists()

    def test_archive_helper_fail_open_on_unreadable_ledger(self, monkeypatch):
        """A migration hiccup (e.g. a permissions error mid-rename) must never raise -- it is
        logged and swallowed, matching every other IO helper in this module."""
        self._write_ledger([{"_doc": "x"}, {"event": "placed", "signal_ref": "a"}])

        def _boom(*_a, **_kw):
            raise OSError("simulated permission error")

        monkeypatch.setattr(fms.os, "replace", _boom)
        result = fms._archive_or_reset_ledger_for_migration("v1")
        assert result is False   # fail-open: reports "no archive happened", never raises

    # ── end-to-end through run_once() ──
    def test_run_once_migrates_and_regenerates_doc_header_end_to_end(self):
        """Drives the migration through run_once() itself (not just the helpers in
        isolation) -- proves the wiring order (migrate BEFORE _ensure_would_be_doc_header)
        is correct: the ledger ends up with exactly ONE line, the CURRENT (v2) doc header."""
        self._write_ledger([{"_doc": "old v1 arming bar text -- 1.5xATR14"}])
        fms._atomic_write_json(fms.WATERMARK_FILE, {
            "arm_line_watermarks": {}, "seen_signal_keys": {}, "pending_signals": [],
            "last_run_et": "2026-07-08T16:00:00",
        })

        summary = fms.run_once(now_et=dt.datetime(2026, 7, 9, 10, 0, 0),
                               quote_fetcher=lambda: 6000.0, atr_fetcher=lambda: 10.0,
                               fleet_files=[])

        assert summary["spec_version"] == fms.SPEC_VERSION
        assert summary["errors"] == []
        lines = fms.WOULD_BE_FILE.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["_doc"] == fms.ARMING_BAR_DOC


# ═══════════════════════ state spec_version round-trip ══════════════════════════
class TestSpecVersionStateRoundTrip:
    def test_run_once_persists_spec_version_on_fresh_install(self):
        """No prior state file at all -- load_watermark_state()'s default already stamps the
        CURRENT SPEC_VERSION (no prior spec to migrate away from)."""
        summary = fms.run_once(now_et=dt.datetime(2026, 7, 9, 10, 0, 0),
                               quote_fetcher=lambda: 6000.0, atr_fetcher=lambda: 10.0,
                               fleet_files=[])
        assert summary["spec_version"] == fms.SPEC_VERSION

        state = fms.load_watermark_state()
        assert state["spec_version"] == fms.SPEC_VERSION

    def test_spec_version_survives_a_second_poll(self):
        fms.run_once(now_et=dt.datetime(2026, 7, 9, 10, 0, 0),
                    quote_fetcher=lambda: 6000.0, atr_fetcher=lambda: 10.0, fleet_files=[])
        fms.run_once(now_et=dt.datetime(2026, 7, 9, 10, 5, 0),
                    quote_fetcher=lambda: 6000.0, atr_fetcher=lambda: 10.0, fleet_files=[])

        state = fms.load_watermark_state()
        assert state["spec_version"] == fms.SPEC_VERSION

    def test_watermark_file_on_disk_carries_spec_version_key(self):
        """Round-trip through the ACTUAL JSON file, not just the in-memory dict returned by
        load_watermark_state()."""
        fms.run_once(now_et=dt.datetime(2026, 7, 9, 10, 0, 0),
                    quote_fetcher=lambda: 6000.0, atr_fetcher=lambda: 10.0, fleet_files=[])
        raw = json.loads(fms.WATERMARK_FILE.read_text(encoding="utf-8"))
        assert raw["spec_version"] == fms.SPEC_VERSION


# ═══════════════════════ no-naive-datetime discipline ═══════════════════════════
class TestNoNaiveDatetime:
    def test_et_now_honors_monkeypatched_et_clock(self, monkeypatch):
        import et_clock

        sentinel = dt.datetime(2099, 1, 1, 12, 0, 0)
        monkeypatch.setattr(et_clock, "et_now", lambda: sentinel)
        assert fms._et_now() == sentinel

    def test_run_once_default_now_et_comes_from_et_clock_not_local_clock(self, monkeypatch):
        import et_clock

        sentinel = dt.datetime(2030, 5, 1, 9, 31, 0)
        monkeypatch.setattr(et_clock, "et_now", lambda: sentinel)
        summary = fms.run_once(quote_fetcher=lambda: 6000.0, atr_fetcher=lambda: 10.0,
                               fleet_files=[])
        state = fms.load_watermark_state()
        assert state["last_run_et"] == sentinel.strftime("%Y-%m-%dT%H:%M:%S")
        assert summary["errors"] == []

    def test_source_has_no_bare_naive_now_call(self):
        """Static guard: the only permitted `datetime.now(` / bare `.now()` call in this file
        lives inside `_et_now()` itself (which goes through the DST-aware et_clock module, not
        a naive local-clock read). Regressing to a stray `dt.datetime.now()` elsewhere in the
        file must RED this test."""
        src = Path(fms.__file__).read_text(encoding="utf-8")
        lines = src.splitlines()
        offenders = []
        in_et_now = False
        for line in lines:
            if line.startswith("def _et_now"):
                in_et_now = True
                continue
            if in_et_now and line and not line.startswith((" ", ")")) and not line.strip().startswith("#"):
                in_et_now = False
            if in_et_now:
                continue
            if "datetime.now(" in line and "et_clock" not in line:
                offenders.append(line)
        assert offenders == [], f"naive datetime.now() call(s) outside _et_now(): {offenders}"

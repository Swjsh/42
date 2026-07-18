"""Guards for setup/scripts/futures_edge3_sim.py -- the own-book SIM lane for EDGE #3
(MES-leads->MNQ-lags divergence, automation/state/fleet/edge3_mesmnq_div.py FROZEN_CONFIG).

Covers: RTH-only session gating (weekday/holiday/time-window), the frozen ATR-vs-chart-stop
math at entry (byte-identical to edge3.b4.simulate's atr_trail branch), the chandelier
trail + stop-touch + EOD-flat state machine, the 1-signal-per-session consumption guard, the
falsification-rail progress computation, fail-open on a bad quote fetch / outside-RTH tick,
and an end-to-end entry off REAL historical MES/MNQ data reproducing a known validated signal
day (same fixture-discovery pattern as automation/state/fleet/test_edge3_mesmnq_div.py) --
proving the sim lane's ENTER path is byte-consistent with the validated backtest's own signal,
never re-derived.

Pure Python + the repo's own cached historical futures CSVs. No network calls in this file.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest", "setup/scripts", "automation/state/fleet"):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

import futures_edge3_sim as fes  # noqa: E402
import edge3_mesmnq_div as e3  # noqa: E402


# ─────────────────────────── fixtures / isolation ──────────────────────────────
@pytest.fixture(autouse=True)
def _isolate_state(monkeypatch, tmp_path):
    """Redirect every state path this module writes to a tmp dir -- guards must NEVER touch
    real automation/state/futures/* or automation/state/logs/* (matches
    test_futures_mirror_shadow.py's _isolate_state pattern)."""
    state_dir = tmp_path / "futures"
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(fes, "STATE_DIR", state_dir)
    monkeypatch.setattr(fes, "LOG_DIR", log_dir)
    monkeypatch.setattr(fes, "STATE_FILE", state_dir / "edge3-sim-state.json")
    monkeypatch.setattr(fes, "POSITION_FILE", state_dir / "edge3-sim-position.json")
    monkeypatch.setattr(fes, "LEDGER_FILE", state_dir / "edge3-sim-fills.jsonl")
    monkeypatch.setattr(fes, "PROGRESS_FILE", state_dir / "edge3-sim-progress.json")
    monkeypatch.setattr(fes, "CALENDAR_FILE", tmp_path / "does-not-exist-calendar.json")


def _b4():
    return e3.b4


# ─────────────────────────── is_rth ─────────────────────────────────────────────
def test_is_rth_true_inside_window_weekday():
    b4mod = _b4()
    now = dt.datetime(2026, 7, 20, 11, 0)  # Monday
    assert fes.is_rth(now, b4mod, set()) is True


def test_is_rth_false_before_open():
    b4mod = _b4()
    now = dt.datetime(2026, 7, 20, 9, 0)
    assert fes.is_rth(now, b4mod, set()) is False


def test_is_rth_false_at_close_boundary():
    b4mod = _b4()
    now = dt.datetime(2026, 7, 20, 16, 0)  # RTH_CLOSE itself is exclusive
    assert fes.is_rth(now, b4mod, set()) is False


def test_is_rth_false_weekend():
    b4mod = _b4()
    saturday = dt.datetime(2026, 7, 18, 11, 0)
    sunday = dt.datetime(2026, 7, 19, 11, 0)
    assert fes.is_rth(saturday, b4mod, set()) is False
    assert fes.is_rth(sunday, b4mod, set()) is False


def test_is_rth_false_on_holiday():
    b4mod = _b4()
    now = dt.datetime(2026, 9, 7, 11, 0)  # Monday, Labor Day
    assert fes.is_rth(now, b4mod, {"2026-09-07"}) is False


# ─────────────────────────── open_position stop math ────────────────────────────
def test_open_position_long_uses_wider_of_atr_and_chart_stop():
    b4mod = _b4()
    cfg = e3.FROZEN_CONFIG
    decision = e3.Edge3Decision(
        edge_id=cfg.edge_id, arm_id=cfg.arm_id, enabled=True, action="ENTER_LONG",
        laggard="MNQ", side="long", entry_idx=100, chart_stop=19900.0, persistence=2,
        reason="test",
    )
    now = dt.datetime(2026, 7, 20, 11, 0)
    # entry=20000, atr=10 -> atr_stop = 20000 - 1.5*10 = 19985; chart_stop=19900 (further away)
    # -> stop = max(19985, 19900) = 19985 (the closer/tighter of the two, per b4.simulate)
    pos = fes.open_position(decision, entry_quote=20000.0, atr_at_signal=10.0, now_et=now,
                            b4mod=b4mod, cfg=cfg)
    slip = b4mod.SLIP_TICKS * b4mod.TICK
    expected_entry = 20000.0 + slip
    expected_stop = max(expected_entry - b4mod.ATR_STOP_MULT * 10.0, 19900.0)
    assert pos["entry"] == pytest.approx(expected_entry)
    assert pos["stop"] == pytest.approx(expected_stop)
    assert pos["direction"] == "long"
    assert pos["status"] == "open"
    assert pos["qty"] == cfg.qty_micros
    assert pos["fidelity"] == fes.FIDELITY


def test_open_position_short_uses_tighter_of_atr_and_chart_stop():
    b4mod = _b4()
    cfg = e3.FROZEN_CONFIG
    decision = e3.Edge3Decision(
        edge_id=cfg.edge_id, arm_id=cfg.arm_id, enabled=True, action="ENTER_SHORT",
        laggard="MNQ", side="short", entry_idx=100, chart_stop=20200.0, persistence=3,
        reason="test",
    )
    now = dt.datetime(2026, 7, 20, 11, 0)
    pos = fes.open_position(decision, entry_quote=20000.0, atr_at_signal=10.0, now_et=now,
                            b4mod=b4mod, cfg=cfg)
    slip = b4mod.SLIP_TICKS * b4mod.TICK
    expected_entry = 20000.0 - slip
    expected_stop = min(expected_entry + b4mod.ATR_STOP_MULT * 10.0, 20200.0)
    assert pos["entry"] == pytest.approx(expected_entry)
    assert pos["stop"] == pytest.approx(expected_stop)
    assert pos["direction"] == "short"


# ─────────────────────────── manage_position state machine ──────────────────────
def _open_long(now, entry=20000.0, stop=19985.0, atr=10.0):
    return {
        "edge_id": "edge3_mesmnq_div", "arm_id": "mes-mnq-div-futures", "laggard": "MNQ",
        "direction": "long", "status": "open", "qty": 1, "entry": entry, "stop": stop,
        "atr_at_entry": atr, "hh": entry, "ll": entry,
        "entry_time_et": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "session_date": now.date().isoformat(), "closed_at_et": None, "persistence": 2,
        "fidelity": fes.FIDELITY,
    }


def test_manage_position_ratchets_trail_up_for_long_without_closing():
    b4mod = _b4()
    now0 = dt.datetime(2026, 7, 20, 11, 0)
    pos = _open_long(now0)
    now1 = dt.datetime(2026, 7, 20, 11, 5)
    # price rallies to 20050; chandelier = 20050 - 2.5*10 = 20025 > current stop 19985.
    # bar_low (20030) stays safely ABOVE the freshly-ratcheted stop so this poll doesn't
    # ALSO stop out -- ratchet-then-check happens in the same pass, by design.
    row, new_pos = fes.manage_position(pos, price=20040.0, bar_high=20050.0, bar_low=20030.0,
                                       now_et=now1, b4mod=b4mod)
    assert row is None
    assert new_pos["stop"] == pytest.approx(20050.0 - b4mod.TRAIL_MULT * 10.0)
    assert new_pos["status"] == "open"


def test_manage_position_stop_touch_closes_via_gap_aware_fill():
    b4mod = _b4()
    now0 = dt.datetime(2026, 7, 20, 11, 0)
    pos = _open_long(now0, entry=20000.0, stop=19985.0)
    now1 = dt.datetime(2026, 7, 20, 11, 5)
    row, new_pos = fes.manage_position(pos, price=19980.0, bar_high=19995.0, bar_low=19980.0,
                                       now_et=now1, b4mod=b4mod)
    assert row is not None
    assert row["event"] == fes.EV_STOPPED
    assert new_pos["status"] == "closed"
    assert row["pnl_usd_mnq"] < 0  # stopped out for a loss
    assert row["fidelity"] == fes.FIDELITY


def test_manage_position_gap_through_stop_fills_worse_than_stop():
    b4mod = _b4()
    now0 = dt.datetime(2026, 7, 20, 11, 0)
    pos = _open_long(now0, entry=20000.0, stop=19985.0)
    now1 = dt.datetime(2026, 7, 20, 11, 5)
    # a real gap: bar_low is far beyond the stop, price (close) also beyond it
    row, _ = fes.manage_position(pos, price=19900.0, bar_high=19950.0, bar_low=19890.0,
                                 now_et=now1, b4mod=b4mod)
    assert row["fill_price"] <= 19900.0  # worse than (or equal to) the observed price
    assert row["fill_price"] < pos["stop"]  # strictly worse than the stop itself


def test_manage_position_flattens_at_rth_close():
    b4mod = _b4()
    now0 = dt.datetime(2026, 7, 20, 11, 0)
    pos = _open_long(now0, entry=20000.0, stop=19900.0)  # stop far away, won't trigger
    now1 = dt.datetime(2026, 7, 20, 16, 0)  # exactly RTH_CLOSE
    row, new_pos = fes.manage_position(pos, price=20010.0, bar_high=20015.0, bar_low=20005.0,
                                       now_et=now1, b4mod=b4mod)
    assert row is not None
    assert row["event"] == fes.EV_EOD_FLAT
    assert new_pos["status"] == "closed"


def test_manage_position_flattens_on_session_rollover():
    b4mod = _b4()
    now0 = dt.datetime(2026, 7, 20, 11, 0)
    pos = _open_long(now0, entry=20000.0, stop=19900.0)
    next_day = dt.datetime(2026, 7, 21, 9, 35)  # a new session date, defensive flatten
    row, new_pos = fes.manage_position(pos, price=20010.0, bar_high=20015.0, bar_low=20005.0,
                                       now_et=next_day, b4mod=b4mod)
    assert row is not None
    assert row["event"] == fes.EV_EOD_FLAT
    assert row["reason"] == "rth_close_same_session"
    assert new_pos["status"] == "closed"


def test_manage_position_flat_status_is_a_noop():
    b4mod = _b4()
    flat = {"status": "flat"}
    row, new_pos = fes.manage_position(flat, price=100.0, bar_high=101.0, bar_low=99.0,
                                       now_et=dt.datetime(2026, 7, 20, 11, 0), b4mod=b4mod)
    assert row is None
    assert new_pos == flat


# ─────────────────────────── falsification-rail progress ────────────────────────
def _closed_row(pnl: float, event: str = fes.EV_STOPPED) -> dict:
    return {"event": event, "pnl_usd_mnq": pnl}


def test_progress_pending_below_floor(tmp_path):
    ledger = tmp_path / "fills.jsonl"
    with open(ledger, "a", encoding="utf-8") as f:
        for i in range(5):
            f.write(json.dumps(_closed_row(70.0)) + "\n")
    progress = fes.compute_progress(e3.FROZEN_CONFIG, ledger_file=ledger)
    assert progress["n_closed_round_trips"] == 5
    assert progress["falsification"] == "PENDING_MORE_DATA"


def test_progress_tracking_validated_at_floor_with_healthy_pnl(tmp_path):
    ledger = tmp_path / "fills.jsonl"
    with open(ledger, "a", encoding="utf-8") as f:
        for i in range(fes.FALSIFICATION_FLOOR):
            f.write(json.dumps(_closed_row(75.0)) + "\n")
    progress = fes.compute_progress(e3.FROZEN_CONFIG, ledger_file=ledger)
    assert progress["n_closed_round_trips"] == fes.FALSIFICATION_FLOOR
    assert progress["falsification"] == "TRACKING_VALIDATED"


def test_progress_flags_investigate_on_material_shortfall(tmp_path):
    ledger = tmp_path / "fills.jsonl"
    with open(ledger, "a", encoding="utf-8") as f:
        for i in range(fes.FALSIFICATION_FLOOR):
            f.write(json.dumps(_closed_row(5.0)) + "\n")  # << far below $71.46
    progress = fes.compute_progress(e3.FROZEN_CONFIG, ledger_file=ledger)
    assert progress["falsification"] == "INVESTIGATE_QUOTE_QUALITY"


def test_progress_ignores_doc_header_and_non_closing_events(tmp_path):
    ledger = tmp_path / "fills.jsonl"
    with open(ledger, "a", encoding="utf-8") as f:
        f.write(json.dumps({"_doc": "header, not a row"}) + "\n")
        f.write(json.dumps({"event": fes.EV_PLACED, "pnl_usd_mnq": 0.0}) + "\n")
        f.write(json.dumps({"event": fes.EV_FILLED, "pnl_usd_mnq": 0.0}) + "\n")
    progress = fes.compute_progress(e3.FROZEN_CONFIG, ledger_file=ledger)
    assert progress["n_closed_round_trips"] == 0
    assert progress["mean_pnl_usd_mnq"] is None


def test_progress_missing_ledger_is_zero_not_a_crash(tmp_path):
    progress = fes.compute_progress(e3.FROZEN_CONFIG, ledger_file=tmp_path / "nope.jsonl")
    assert progress["n_closed_round_trips"] == 0
    assert progress["falsification"] == "PENDING_MORE_DATA"


# ─────────────────────────── run_once: fail-open / gating paths ─────────────────
def test_run_once_outside_rth_is_a_clean_noop_and_never_touches_quotes():
    calls = {"n": 0}

    def _boom():
        calls["n"] += 1
        raise AssertionError("quote fetcher must never be called outside RTH")

    saturday = dt.datetime(2026, 7, 18, 10, 48)
    result = fes.run_once(now_et=saturday, lead_fetcher=_boom, lag_fetcher=_boom)
    assert result["action"] == "noop"
    assert result["reason"] == "market_closed_outside_rth"
    assert result["in_rth"] is False
    assert calls["n"] == 0
    state = json.loads(fes.STATE_FILE.read_text(encoding="utf-8"))
    assert state["last_action"] == "noop"
    assert state["last_reason"] == "market_closed_outside_rth"


def test_run_once_quote_fetch_failure_is_a_clean_noop():
    now = dt.datetime(2026, 7, 20, 11, 0)
    result = fes.run_once(now_et=now, lead_fetcher=lambda: None, lag_fetcher=lambda: None)
    assert result["action"] == "noop"
    assert result["reason"] == "quote_fetch_failed"
    assert result["in_rth"] is True


def test_run_once_never_raises_even_if_fetcher_raises():
    now = dt.datetime(2026, 7, 20, 11, 0)

    def _raise():
        raise RuntimeError("network is on fire")

    result = fes.run_once(now_et=now, lead_fetcher=_raise, lag_fetcher=_raise)
    assert result["action"] == "noop"
    assert any("lead_fetch_failed" in e for e in result["errors"])


# ─────────────────────────── run_once: real historical signal day (end-to-end) ──
@pytest.fixture(scope="module")
def _signal_day_and_frames():
    """Reuses the SAME discovery pattern as test_edge3_mesmnq_div.py's own
    test_signal_for_tick_enters_when_enabled -- a real validated signal day from the cached
    historical data, truncated so the LAST row lands on that session (so run_once's
    `.iloc[-1]` 'current quote' is a real bar from the right day, not some other date)."""
    mes = e3.b4.load_futures("MES")
    mnq = e3.b4.load_futures("MNQ")
    common = sorted(set(mes["date"]) & set(mnq["date"]))
    mes = mes[mes["date"].isin(common)].reset_index(drop=True)
    mnq = mnq[mnq["date"].isin(common)].reset_index(drop=True)
    lag_atr = e3.b4.atr_series(mnq["high"], mnq["low"], mnq["close"], e3.b4.ATR_LEN)
    sm = e3.b4._per_session_state(mes)
    sn = e3.b4._per_session_state(mnq)
    enriched = e3.b5.enrich_signals(mes, mnq, sm, sn, "MNQ", 0.0015, lag_atr)
    kept = e3.b5.fix_min_persistence(enriched, 2)
    assert kept, "expected at least one validated signal day in the cached dataset"
    signal_day = kept[0].date

    mes_slice = mes[mes["date"] <= signal_day].reset_index(drop=True)
    mnq_slice = mnq[mnq["date"] <= signal_day].reset_index(drop=True)
    return signal_day, mes_slice, mnq_slice


def test_run_once_opens_a_sim_position_on_a_real_validated_signal_day(_signal_day_and_frames):
    signal_day, mes_slice, mnq_slice = _signal_day_and_frames
    now = dt.datetime.combine(signal_day, dt.time(11, 0))
    assert now.weekday() < 5, "sanity: cached RTH data should only carry trading days"

    result = fes.run_once(now_et=now, lead_fetcher=lambda: mes_slice, lag_fetcher=lambda: mnq_slice)
    assert result["errors"] == []
    assert result["position_open"] is True
    assert fes.EV_PLACED in result["events"]
    assert fes.EV_FILLED in result["events"]

    position = json.loads(fes.POSITION_FILE.read_text(encoding="utf-8"))
    assert position["status"] == "open"
    assert position["edge_id"] == "edge3_mesmnq_div"
    assert position["laggard"] == "MNQ"
    assert position["fidelity"] == fes.FIDELITY

    ledger_lines = fes.LEDGER_FILE.read_text(encoding="utf-8").splitlines()
    events = [json.loads(line)["event"] for line in ledger_lines]
    assert events == [fes.EV_PLACED, fes.EV_FILLED]

    state = json.loads(fes.STATE_FILE.read_text(encoding="utf-8"))
    assert signal_day.isoformat() in state["consumed_sessions"]


def test_run_once_does_not_reenter_same_session_after_close(_signal_day_and_frames):
    signal_day, mes_slice, mnq_slice = _signal_day_and_frames
    now = dt.datetime.combine(signal_day, dt.time(11, 0))
    fes.run_once(now_et=now, lead_fetcher=lambda: mes_slice, lag_fetcher=lambda: mnq_slice)

    # Force-flatten the open position directly in state (simulating a stop-out later that
    # same session), then tick again same day before the entry cutoff -- must NOT re-enter.
    position = json.loads(fes.POSITION_FILE.read_text(encoding="utf-8"))
    assert position["status"] == "open"
    fes._atomic_write_json(fes.POSITION_FILE, {**position, "status": "flat"})

    later_same_day = dt.datetime.combine(signal_day, dt.time(12, 0))
    result = fes.run_once(now_et=later_same_day, lead_fetcher=lambda: mes_slice,
                          lag_fetcher=lambda: mnq_slice)
    assert result["position_open"] is False
    assert fes.EV_PLACED not in result["events"]


def test_frozen_config_never_mutated_by_the_sim_lane(_signal_day_and_frames):
    # Paranoia guard (no-drift doctrine): the module-level FROZEN_CONFIG singleton must stay
    # enabled=False after any number of run_once() calls -- the sim lane only ever operates on
    # a dataclasses.replace() COPY, never the shared object.
    signal_day, mes_slice, mnq_slice = _signal_day_and_frames
    now = dt.datetime.combine(signal_day, dt.time(11, 0))
    fes.run_once(now_et=now, lead_fetcher=lambda: mes_slice, lag_fetcher=lambda: mnq_slice)
    assert e3.FROZEN_CONFIG.enabled is False
    assert e3.FROZEN_CONFIG.threshold == 0.0015
    assert e3.FROZEN_CONFIG.min_persistence_bars == 2

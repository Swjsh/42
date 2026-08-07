"""test_ssr_shadow.py -- pytest suite for setup/scripts/ssr_shadow.py (the SSR-v1 PULSE
forward own-book shadow ledger). No network calls: every test injects `bar_fetcher` and/or
`signal_fn` seams, or calls the pure per-bar/per-signal functions directly. State/ledger/
progress files are redirected into pytest's tmp_path via an autouse monkeypatch fixture --
this suite never touches the real automation/state/futures/ssr-shadow-* files.
"""
from __future__ import annotations

import datetime as _stdlib_dt  # noqa: F401 -- only used to build tz-aware fixture timestamps
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

import ssr_shadow  # noqa: E402
from futures.ssr.detector import SSRParams, SSRSignal, _Episode, _step_shifted  # noqa: E402

ET = "America/New_York"


# ── fixtures ────────────────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    """Redirects every file this module writes into tmp_path -- never touches the real
    automation/state/futures/ssr-shadow-* files or the real log directory."""
    monkeypatch.setattr(ssr_shadow, "STATE_FILE", tmp_path / "ssr-shadow-state.json")
    monkeypatch.setattr(ssr_shadow, "LEDGER_FILE", tmp_path / "ssr-shadow-would-be.jsonl")
    monkeypatch.setattr(ssr_shadow, "PROGRESS_FILE", tmp_path / "ssr-shadow-progress.json")
    monkeypatch.setattr(ssr_shadow, "LOCK_FILE", tmp_path / "ssr-shadow.lock")
    monkeypatch.setattr(ssr_shadow, "LOG_DIR", tmp_path / "logs")
    return tmp_path


class _FakeInstrument:
    """Duck-types backtest.futures.instruments.Instrument's fields decide_bar_events needs,
    without importing the real registry -- keeps exit-math tests decoupled from instrument
    specs, which are covered separately by test_spec_constants_pinned."""
    def __init__(self, point_value: float = 20.0, tick_size: float = 0.25,
                round_turn_usd: float = 4.0):
        self.point_value = point_value
        self.tick_size = tick_size
        self.round_turn_usd = round_turn_usd


def _make_bars(n: int = 30, start: str = "2026-08-03 04:00:00", freq_minutes: int = 15,
              base_price: float = 15000.0) -> pd.DataFrame:
    idx = pd.date_range(pd.Timestamp(start, tz=ET), periods=n, freq=f"{freq_minutes}min")
    return pd.DataFrame({
        "timestamp_et": idx,
        "open": [base_price + i for i in range(n)],
        "high": [base_price + i + 5 for i in range(n)],
        "low": [base_price + i - 5 for i in range(n)],
        "close": [base_price + i + 1 for i in range(n)],
        "volume": [100] * n,
    })


def _make_signal(bars: pd.DataFrame, bar_index: int, *, direction: str = "short",
                 level_name: str = "LONDON_HIGH", entry_ref_close: float = 15000.0,
                 stop_price: float = 15050.0) -> SSRSignal:
    ts = bars["timestamp_et"].iloc[bar_index]
    return SSRSignal(
        ts_et=ts, bar_index=bar_index, direction=direction, level_name=level_name,
        level_price=entry_ref_close, sweep_extreme=stop_price, stop_price=stop_price,
        entry_ref_close=entry_ref_close,
        state_trace={"swept_at_index": 0, "shifted_at_index": 0, "shift_mode": "bos"},
    )


# ── spec constants pinned ──────────────────────────────────────────────────────────────
def test_spec_constants_pinned():
    assert ssr_shadow.SPEC_VERSION == "ssr-v1"
    nq = ssr_shadow.CONFIGS["NQ"]
    assert nq["symbol"] == "NQ=F" and nq["interval"] == "15m" and nq["period"] == "8d"
    assert nq["zone_atr_mult"] == 0.5 and nq["sweep_atr_mult"] == 0.1
    assert nq["h4_anchor"] == "2000" and nq["include_running"] is True
    gc = ssr_shadow.CONFIGS["GC"]
    assert gc["symbol"] == "GC=F" and gc["interval"] == "1h" and gc["period"] == "60d"
    assert gc["zone_atr_mult"] == 0.5 and gc["sweep_atr_mult"] == 0.1
    assert gc["h4_anchor"] == "2000" and gc["include_running"] is True
    assert ssr_shadow.QTY == 3
    assert ssr_shadow.TP1_QTY == 2
    assert ssr_shadow.RUN_QTY == 1
    assert ssr_shadow.TP1_R_MULT == 1.5
    assert ssr_shadow.RUNNER_FALLBACK_R_MULT == 3.0
    assert ssr_shadow.RUNNER_CAP_R_MULT == 5.0
    assert ssr_shadow.LOOKBACK_BARS == 3
    assert ssr_shadow.ARMING_MIN_ROUND_TRIPS == 20
    assert ssr_shadow.FLAT_HOUR_ET == 16 and ssr_shadow.FLAT_MINUTE_ET == 55


# ── cold start ──────────────────────────────────────────────────────────────────────────
def test_cold_start_sets_watermark_and_opens_nothing():
    bars = _make_bars(30)
    now = bars["timestamp_et"].iloc[-1] + pd.Timedelta(minutes=15)

    def fetcher(symbol, interval, period):
        return bars.copy()

    def signal_fn(bars_, snapshots, atr, params):
        # even if the detector WOULD have signals, cold start must open nothing.
        return [_make_signal(bars_, 27)]

    summary = ssr_shadow.run_once(now_et=now, bar_fetcher=fetcher, signal_fn=signal_fn)

    assert set(summary["cold_start_configs"]) == {"NQ", "GC"}
    assert summary["opened"] == 0
    assert summary["positions_open"] == 0

    state = json.loads(ssr_shadow.STATE_FILE.read_text(encoding="utf-8"))
    expected_watermark = bars["timestamp_et"].iloc[-2].isoformat()  # last bar is dropped (in-progress)
    for cfg in ("NQ", "GC"):
        assert state["configs"][cfg]["watermark_bar_ts_et"] == expected_watermark
    assert state["positions"] == {}


# ── dedupe / lookback (pure _select_new_signals) ──────────────────────────────────────────
def test_select_new_signals_dedupe_via_advancing_watermark():
    bars = _make_bars(30)
    sig = _make_signal(bars, bar_index=27)  # within last-3-bars of a 30-row frame
    wm_before = bars["timestamp_et"].iloc[10]
    got_before = ssr_shadow._select_new_signals([sig], wm_before, n_bars=30)
    assert got_before == [sig]

    # simulate the watermark having already advanced past this signal's own bar (exactly
    # what run_once does at the end of every poll) -- it must never be selected again.
    wm_after = bars["timestamp_et"].iloc[-1]
    got_after = ssr_shadow._select_new_signals([sig], wm_after, n_bars=30)
    assert got_after == []


def test_select_new_signals_stale_beyond_lookback_ignored():
    bars = _make_bars(30)
    sig = _make_signal(bars, bar_index=10)  # far from the tail; n_bars-3 == 27
    wm = bars["timestamp_et"].iloc[0] - pd.Timedelta(minutes=1)  # watermark alone wouldn't exclude it
    got = ssr_shadow._select_new_signals([sig], wm, n_bars=30)
    assert got == []


def test_select_new_signals_cold_start_none_watermark_returns_empty():
    bars = _make_bars(30)
    sig = _make_signal(bars, bar_index=29)
    assert ssr_shadow._select_new_signals([sig], None, n_bars=30) == []


# ── entry-window gate (pins the SAME detector function ssr_shadow relies on) ──────────────
def test_entry_window_rejection_and_acceptance():
    p = SSRParams(zone_atr_mult=0.5, sweep_atr_mult=0.1)  # default entry 03:00-15:00 ET
    entry_start = _stdlib_dt.datetime.strptime(p.entry_start_et, "%H:%M").time()
    entry_end = _stdlib_dt.datetime.strptime(p.entry_end_et, "%H:%M").time()
    level_price, atr_val = 100.0, 1.0
    # short-direction retest-reaction bar: touches the zone band, closes down inside it.
    bar_open, bar_high, bar_low, bar_close = 100.3, 100.3, 99.9, 99.95

    outside_ts = pd.Timestamp("2026-08-03 02:00:00", tz=ET)  # before 03:00 -- rejected
    ep_outside = _Episode(state="SHIFTED", swept_at_index=0, sweep_extreme=100.0,
                          shifted_at_index=0, shift_mode="bos")
    sig_outside = _step_shifted(ep_outside, "short", 5, bar_open, bar_high, bar_low, bar_close,
                                level_price, atr_val, p, "PDH", outside_ts, entry_start, entry_end)
    assert sig_outside is None

    inside_ts = pd.Timestamp("2026-08-03 10:00:00", tz=ET)  # inside 03:00-15:00 -- accepted
    ep_inside = _Episode(state="SHIFTED", swept_at_index=0, sweep_extreme=100.0,
                         shifted_at_index=0, shift_mode="bos")
    sig_inside = _step_shifted(ep_inside, "short", 5, bar_open, bar_high, bar_low, bar_close,
                               level_price, atr_val, p, "PDH", inside_ts, entry_start, entry_end)
    assert sig_inside is not None
    assert sig_inside.direction == "short"


# ── position open + runner selection ───────────────────────────────────────────────────
def test_open_position_entry_math_and_fallback_runner():
    bars = _make_bars(30)
    sig = _make_signal(bars, 27, direction="short", entry_ref_close=15000.0, stop_price=15050.0)
    inst = _FakeInstrument(tick_size=0.25)
    pos = ssr_shadow.open_position("NQ", sig, None, inst)  # snapshot=None -> fallback runner
    assert pos["direction"] == "short"
    assert pos["entry"] == pytest.approx(15000.0 - 0.25)  # short: 1 tick WORSE (sold lower)
    r_points = abs(pos["entry"] - pos["stop"])
    assert pos["tp1"] == pytest.approx(pos["entry"] - 1.5 * r_points)
    assert pos["runner_source"] == "fallback_3r"
    assert pos["runner"] == pytest.approx(pos["entry"] - 3.0 * r_points)
    assert pos["qty_open"] == 3
    assert pos["tp1_filled"] is False
    assert pd.Timestamp(pos["deadline_et"]).hour == 16
    assert pd.Timestamp(pos["deadline_et"]).minute == 55


def test_pick_runner_prefers_nearest_opposing_level_over_fallback():
    class _Snap:
        def all_levels(self):
            return [("PDL", 14900.0), ("RUN_DAY_LOW", 14850.0), ("PDH", 15100.0)]
    # short: entry=15000, tp1=14925 (below tp1 candidates only) -> nearest opposing = 14900
    runner, source = ssr_shadow._pick_runner(_Snap(), entry=15000.0, tp1=14925.0,
                                             direction="short", r_points=50.0)
    assert source == "level"
    assert runner == 14900.0


def test_pick_runner_caps_at_5r_when_level_too_far():
    class _Snap:
        def all_levels(self):
            return [("PWL", 14000.0)]  # way beyond 5R
    runner, source = ssr_shadow._pick_runner(_Snap(), entry=15000.0, tp1=14925.0,
                                             direction="short", r_points=50.0)
    assert source == "capped_5r"
    assert runner == pytest.approx(15000.0 - 5.0 * 50.0)


# ── per-bar exit decision ────────────────────────────────────────────────────────────────
def test_stop_before_tp1_same_bar_priority():
    bars = _make_bars(30)
    sig = _make_signal(bars, 10, direction="short", entry_ref_close=15000.0, stop_price=15050.0)
    inst = _FakeInstrument()
    pos = ssr_shadow.open_position("NQ", sig, None, inst)
    bar = {"ts_et": pd.Timestamp(pos["entry_time_et"]) + pd.Timedelta(minutes=15),
          "high": pos["stop"] + 1.0, "low": pos["tp1"] - 1.0, "close": pos["stop"]}
    events, new_pos = ssr_shadow.decide_bar_events(pos, bar, inst)
    assert len(events) == 1
    assert events[0]["event"] == "closed"
    assert events[0]["reason"] == "stopped_pre_tp1"
    assert events[0]["exit_qty"] == 3
    assert new_pos["status"] == "closed"
    assert new_pos["qty_open"] == 0


def test_tp1_then_be_then_runner_sequence():
    bars = _make_bars(30)
    sig = _make_signal(bars, 10, direction="short", entry_ref_close=15000.0, stop_price=15050.0)
    inst = _FakeInstrument()
    pos = ssr_shadow.open_position("NQ", sig, None, inst)  # runner = fallback_3r
    entry_ts = pd.Timestamp(pos["entry_time_et"])

    bars4 = pd.DataFrame([
        {"timestamp_et": entry_ts, "open": pos["entry"], "high": pos["entry"] + 1,
        "low": pos["entry"] - 1, "close": pos["entry"]},                                # entry bar (not walked)
        {"timestamp_et": entry_ts + pd.Timedelta(minutes=15), "open": pos["entry"],
        "high": pos["entry"] + 1, "low": pos["tp1"] - 1, "close": pos["tp1"]},           # TP1 hit
        {"timestamp_et": entry_ts + pd.Timedelta(minutes=30), "open": pos["tp1"],
        "high": pos["entry"] - 1, "low": pos["tp1"] - 2, "close": pos["tp1"]},           # hold (no BE, no runner)
        {"timestamp_et": entry_ts + pd.Timedelta(minutes=45), "open": pos["tp1"],
        "high": pos["entry"] - 1, "low": pos["runner"] - 1, "close": pos["runner"]},     # runner hit
    ])

    events, new_pos = ssr_shadow.walk_open_position(pos, bars4, inst)
    reasons = [(e["event"], e.get("reason")) for e in events]
    assert reasons == [("tp1", "tp1_touch_1_5R"), ("closed", "runner")]
    assert events[0]["exit_qty"] == 2 and events[0]["qty_open_after"] == 1
    assert events[1]["exit_qty"] == 1 and events[1]["qty_open_after"] == 0
    assert new_pos["status"] == "closed"
    assert new_pos["tp1_filled"] is True


def test_timestop_close_at_1655():
    bars = _make_bars(30, start="2026-08-03 14:30:00")
    sig = _make_signal(bars, 5, direction="short", entry_ref_close=15000.0, stop_price=15050.0)
    inst = _FakeInstrument()
    pos = ssr_shadow.open_position("NQ", sig, None, inst)
    deadline = pd.Timestamp(pos["deadline_et"])
    assert deadline.hour == 16 and deadline.minute == 55

    # bar AT the deadline that doesn't cross stop/tp1/runner -> forced flat at bar close
    flat_bar = {"ts_et": deadline, "high": pos["entry"] + 1, "low": pos["entry"] - 1,
               "close": pos["entry"] + 0.5}
    events, new_pos = ssr_shadow.decide_bar_events(pos, flat_bar, inst)
    assert len(events) == 1
    assert events[0]["reason"] == "time_flat"
    assert events[0]["exit_qty"] == 3
    assert events[0]["bar_close"] == pytest.approx(pos["entry"] + 0.5)
    assert new_pos["status"] == "closed"


def test_no_event_on_bar_that_hits_nothing():
    bars = _make_bars(30)
    sig = _make_signal(bars, 10, direction="short", entry_ref_close=15000.0, stop_price=15050.0)
    inst = _FakeInstrument()
    pos = ssr_shadow.open_position("NQ", sig, None, inst)
    quiet_bar = {"ts_et": pd.Timestamp(pos["entry_time_et"]) + pd.Timedelta(minutes=15),
                "high": pos["entry"] + 1, "low": pos["entry"] - 1, "close": pos["entry"]}
    events, new_pos = ssr_shadow.decide_bar_events(pos, quiet_bar, inst)
    assert events == []
    assert new_pos["status"] == "open"
    assert new_pos["last_processed_bar_ts_et"] == quiet_bar["ts_et"].isoformat()


# ── SHORT-only enforcement + concurrency (run_once, injected signal_fn) ──────────────────
def test_short_only_long_signal_ignored_and_counted(monkeypatch):
    monkeypatch.setattr(ssr_shadow, "CONFIGS", {"NQ": ssr_shadow.CONFIGS["NQ"]})
    poll1_bars = _make_bars(30)   # cold start; post-drop 29 rows (indices 0..28)
    poll2_bars = _make_bars(32)   # same start/freq -> rows 0..28 identical to poll1's;
                                  # post-drop 31 rows (indices 0..30) -- index 30 is genuinely
                                  # new relative to poll1's watermark (index 28).

    calls = {"n": 0}

    def fetcher(symbol, interval, period):
        calls["n"] += 1
        return poll1_bars.copy() if calls["n"] == 1 else poll2_bars.copy()

    def signal_fn(bars_, snapshots, atr, params):
        if len(bars_) < 31:
            return []  # poll 1 (cold start, 29 rows post-drop) -- irrelevant either way
        long_sig = _make_signal(bars_, 30, direction="long", entry_ref_close=15000.0,
                                stop_price=14950.0)
        short_sig = _make_signal(bars_, 30, direction="short", entry_ref_close=15000.0,
                                 stop_price=15050.0)
        return [long_sig, short_sig]

    now1 = poll1_bars["timestamp_et"].iloc[-1]
    summary1 = ssr_shadow.run_once(now_et=now1, bar_fetcher=fetcher, signal_fn=signal_fn)
    assert summary1["cold_start_configs"] == ["NQ"]

    now2 = poll2_bars["timestamp_et"].iloc[-1]
    summary2 = ssr_shadow.run_once(now_et=now2, bar_fetcher=fetcher, signal_fn=signal_fn)
    assert summary2["skipped_long_signal"] == 1
    assert summary2["opened"] == 1
    assert summary2["positions_open"] == 1

    state = json.loads(ssr_shadow.STATE_FILE.read_text(encoding="utf-8"))
    open_positions = [p for p in state["positions"].values() if p["status"] == "open"]
    assert len(open_positions) == 1
    assert open_positions[0]["direction"] == "short"


def test_concurrency_skip_while_open(monkeypatch):
    monkeypatch.setattr(ssr_shadow, "CONFIGS", {"NQ": ssr_shadow.CONFIGS["NQ"]})
    bars = _make_bars(30)

    def fetcher(symbol, interval, period):
        return bars.copy()

    sig1 = _make_signal(bars, 27, direction="short", level_name="PDH",
                        entry_ref_close=15000.0, stop_price=15050.0)
    sig2 = _make_signal(bars, 28, direction="short", level_name="LONDON_HIGH",
                        entry_ref_close=15010.0, stop_price=15060.0)

    def signal_fn(bars_, snapshots, atr, params):
        return [sig1, sig2]

    now = bars["timestamp_et"].iloc[-1]
    # seed the watermark BEFORE both signals so this poll is not a cold start.
    ssr_shadow._atomic_write_json(ssr_shadow.STATE_FILE, {
        "configs": {"NQ": {"watermark_bar_ts_et": bars["timestamp_et"].iloc[5].isoformat()}},
        "positions": {},
    })
    summary = ssr_shadow.run_once(now_et=now, bar_fetcher=fetcher, signal_fn=signal_fn)
    assert summary["opened"] == 1
    assert summary["skipped_while_open"] == 1


def test_degenerate_r_points_skipped(monkeypatch):
    monkeypatch.setattr(ssr_shadow, "CONFIGS", {"NQ": ssr_shadow.CONFIGS["NQ"]})
    bars = _make_bars(30)
    # stop within a fraction of a tick of the post-slippage entry -- sub-tick R, degenerate.
    sig = _make_signal(bars, 27, direction="short", entry_ref_close=15000.0, stop_price=14999.9)

    def fetcher(symbol, interval, period):
        return bars.copy()

    def signal_fn(bars_, snapshots, atr, params):
        return [sig]

    ssr_shadow._atomic_write_json(ssr_shadow.STATE_FILE, {
        "configs": {"NQ": {"watermark_bar_ts_et": bars["timestamp_et"].iloc[5].isoformat()}},
        "positions": {},
    })
    now = bars["timestamp_et"].iloc[-1]
    summary = ssr_shadow.run_once(now_et=now, bar_fetcher=fetcher, signal_fn=signal_fn)
    assert summary["opened"] == 0
    assert summary["skipped_degenerate"] == 1


# ── no-naive-datetime sweep ────────────────────────────────────────────────────────────
def test_no_naive_datetime_construction_in_module_source():
    src = Path(ssr_shadow.__file__).read_text(encoding="utf-8")
    assert "import datetime" not in src
    assert "from datetime import" not in src
    # every timestamp this module manufactures goes through pandas.Timestamp, tz-aware.


def test_et_now_is_tz_aware():
    now = ssr_shadow._et_now()
    assert isinstance(now, pd.Timestamp)
    assert now.tzinfo is not None


def test_position_timestamps_round_trip_tz_aware():
    bars = _make_bars(30)
    sig = _make_signal(bars, 10, direction="short", entry_ref_close=15000.0, stop_price=15050.0)
    inst = _FakeInstrument()
    pos = ssr_shadow.open_position("NQ", sig, None, inst)
    for field in ("entry_time_et", "signal_ts_et", "last_processed_bar_ts_et", "deadline_et"):
        parsed = pd.Timestamp(pos[field])
        assert parsed.tzinfo is not None, f"{field} must be tz-aware"


# ── fail-open ───────────────────────────────────────────────────────────────────────────
def test_fail_open_bar_fetcher_raises(monkeypatch):
    def _raise(symbol, interval, period):
        raise RuntimeError("simulated yfinance outage")
    monkeypatch.setattr(ssr_shadow, "fetch_bars_light", _raise)
    monkeypatch.setattr(sys, "argv", ["ssr_shadow.py", "--once"])

    rc = ssr_shadow.main()
    assert rc == 0

    state = json.loads(ssr_shadow.STATE_FILE.read_text(encoding="utf-8"))
    assert any("fetch_failed" in e for e in state["errors"])
    assert state["positions"] == {}


def test_fail_open_signal_fn_raises_does_not_crash_run_once():
    bars = _make_bars(30)

    def fetcher(symbol, interval, period):
        return bars.copy()

    def bad_signal_fn(bars_, snapshots, atr, params):
        raise ValueError("boom")

    summary = ssr_shadow.run_once(now_et=bars["timestamp_et"].iloc[-1], bar_fetcher=fetcher,
                                  signal_fn=bad_signal_fn)
    assert any("detector_failed" in e for e in summary["errors"])
    assert summary["opened"] == 0


# ── arming-bar progress ────────────────────────────────────────────────────────────────
def test_compute_round_trips_and_progress_positive_expectancy():
    rows = [
        {"ts_et": "2026-08-03T10:00:00-04:00", "config": "NQ", "signal_ref": "NQ|short|PDH|2026-08-03T09:45",
        "direction": "short", "event": "entry", "entry": 15000.0, "fill_price": 15000.0,
        "bar_close": 15000.0, "exit_qty": 0, "qty_open_after": 3, "pnl_usd": 0.0},
        {"ts_et": "2026-08-03T11:00:00-04:00", "config": "NQ", "signal_ref": "NQ|short|PDH|2026-08-03T09:45",
        "direction": "short", "event": "closed", "reason": "runner", "entry": 15000.0,
        "fill_price": 14900.0, "bar_close": 14900.0, "exit_qty": 3, "qty_open_after": 0,
        "pnl_usd": 500.0},
    ]
    trips = ssr_shadow.compute_round_trips(rows)
    assert len(trips) == 1
    assert trips[0]["total_pnl_usd"] == 500.0

    def fake_lookup(cfg):
        return _FakeInstrument(point_value=20.0, tick_size=0.25, round_turn_usd=4.0)

    progress = ssr_shadow.compute_progress(rows, instrument_lookup=fake_lookup,
                                           now_et=pd.Timestamp("2026-08-03T12:00:00", tz=ET))
    assert progress["n_round_trips"] == 1
    assert progress["positive_expectancy"] is True
    # null: same-direction (short) unmanaged hold entry(15000)->bar_close(14900), qty 3
    # = (15000-14900)*20*3 - 4*3 = 6000-12 = 5988; real pnl 500 does NOT beat that -> False
    assert progress["null_check"]["evaluated"] is True
    assert progress["arming_bar"]["beats_null"] is False
    assert progress["arming_bar"]["armable"] is False  # n < 20 regardless


def test_compute_progress_no_trips_never_crashes():
    progress = ssr_shadow.compute_progress([], now_et=pd.Timestamp("2026-08-03T12:00:00", tz=ET))
    assert progress["n_round_trips"] == 0
    assert progress["positive_expectancy"] is False
    assert progress["arming_bar"]["armable"] is False


def test_ledger_doc_header_written_once():
    ssr_shadow._ensure_ledger_doc_header()
    ssr_shadow._ensure_ledger_doc_header()
    lines = ssr_shadow.LEDGER_FILE.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["_doc"] == ssr_shadow.LEDGER_DOC


# ── ADVERSARIAL (verifier pass) ────────────────────────────────────────────────────────────
# Findings below are REFUTE-pass additions per the task's explicit checklist. Each test is
# adversarial: it encodes what the FROZEN SPEC / HARD RULES promise and fails red if
# ssr_shadow.py does not actually deliver it. ssr_shadow.py itself is READ-ONLY to this
# verifier pass -- these tests exist to SURFACE gaps, not to be made to pass by weakening the
# assertion.

def test_error_also_lands_as_a_ledger_meta_line():
    """HARD RULES (task spec, verbatim): 'errors land in the state file's errors list AND a
    line in the ledger meta.' This pins the SECOND half of that sentence. A fetch failure is
    injected (fail-open path, matches test_fail_open_bar_fetcher_raises); the state file's
    `errors` list picking it up is already covered elsewhere -- this test additionally
    requires an error-tagged row to exist in ssr-shadow-would-be.jsonl itself (the "ledger
    meta" the spec names), NOT merely in the state file. Originally filed RED as a verifier
    finding; ssr_shadow.py now appends an {"event": "error", ...} meta line whenever a pass
    ends with a non-empty errors list -- this test guards that closure."""
    def _raise(symbol, interval, period):
        raise RuntimeError("simulated yfinance outage")

    summary = ssr_shadow.run_once(now_et=pd.Timestamp("2026-08-03T10:00:00", tz=ET),
                                   bar_fetcher=_raise, signal_fn=ssr_shadow.default_signal_fn)
    assert any("fetch_failed" in e for e in summary["errors"])  # state-file half: known-good

    ledger_lines = ssr_shadow.LEDGER_FILE.read_text(encoding="utf-8").splitlines()
    rows = [json.loads(ln) for ln in ledger_lines if ln.strip()]
    error_rows = [r for r in rows if "_doc" not in r and (
        r.get("event") == "error" or "error" in r or "errors" in r
    )]
    assert error_rows, (
        "HARD RULES requires an error line in the ledger meta (ssr-shadow-would-be.jsonl) "
        "in addition to the state file's errors list; ssr_shadow.py currently writes none. "
        f"ledger rows seen: {rows}"
    )


def test_overlapping_invocation_blocked_by_lock_no_duplicate_entry():
    """REFUTE-pass (c), CLOSED: the read-modify-write race (two overlapping invocations both
    reading pre-write state and double-appending the same entry to the append-only ledger)
    is now prevented by run_once's exclusive-create LOCK_FILE held across the whole
    read-modify-write window (plus the scheduled task's -MultipleInstances IgnoreNew as the
    scheduler-level layer). The original red-team simulation (monkeypatching load_state to
    force stale reads across two SEQUENTIAL calls) is no longer an achievable interleaving:
    with the lock serializing the window, a second caller can never read state before the
    first has written back. This test pins the lock semantics directly: while the lock is
    held (an in-flight invocation), a second run_once must return skipped_lock_held=True,
    open nothing, and append nothing."""
    bars = _make_bars(30)

    def fetcher(symbol, interval, period):
        return bars.copy()

    sig = _make_signal(bars, 27, direction="short", level_name="PDH",
                        entry_ref_close=15000.0, stop_price=15050.0)

    def signal_fn(bars_, snapshots, atr, params):
        return [sig]

    now = bars["timestamp_et"].iloc[-1]

    # Seed a real watermark (bar 5) so the signal at bar 27 is genuinely fresh -- without
    # this the first unblocked call would cold-start and open nothing by design.
    seeded = {
        "_doc": "test", "spec_version": ssr_shadow.SPEC_VERSION,
        "configs": {"NQ": {"watermark_bar_ts_et": bars["timestamp_et"].iloc[5].isoformat()}},
        "positions": {}, "last_run_et": now.isoformat(), "errors": [],
    }
    ssr_shadow._atomic_write_json(ssr_shadow.STATE_FILE, seeded)
    state_before = ssr_shadow.STATE_FILE.read_text(encoding="utf-8")

    # Simulate an in-flight holder: acquire the lock exactly as a live run would.
    assert ssr_shadow._acquire_lock(now) is True
    try:
        blocked = ssr_shadow.run_once(now_et=now, bar_fetcher=fetcher, signal_fn=signal_fn)
    finally:
        ssr_shadow._release_lock()

    assert blocked.get("skipped_lock_held") is True
    assert blocked["opened"] == 0 and blocked["events"] == 0
    assert ssr_shadow.STATE_FILE.read_text(encoding="utf-8") == state_before, (
        "blocked caller must not touch state")
    rows = ssr_shadow.load_ledger_rows() if ssr_shadow.LEDGER_FILE.exists() else []
    assert not [r for r in rows if r.get("event") == "entry"], "blocked caller appends nothing"

    # Lock released -> the same call now proceeds normally and opens exactly one position,
    # and a follow-up call (fresh state, advanced watermark) does NOT duplicate it.
    s1 = ssr_shadow.run_once(now_et=now, bar_fetcher=fetcher, signal_fn=signal_fn)
    assert s1.get("skipped_lock_held") is None and s1["opened"] == 1
    s2 = ssr_shadow.run_once(now_et=now, bar_fetcher=fetcher, signal_fn=signal_fn)
    assert s2["opened"] == 0, "watermark + real (non-stale) state prevent re-entry"
    entry_rows_for_sig = [r for r in ssr_shadow.load_ledger_rows()
                          if r.get("event") == "entry"
                          and r.get("signal_ref") == ssr_shadow._signal_ref("NQ", sig)]
    assert len(entry_rows_for_sig) == 1, "exactly one ledger entry row for one real signal"

    # Stale-lock recovery: a crashed holder's lock older than LOCK_STALE_S gets broken.
    stale_ts = now - pd.Timedelta(seconds=ssr_shadow.LOCK_STALE_S + 60)
    ssr_shadow.LOCK_FILE.write_text(
        json.dumps({"pid": 99999, "ts_et": stale_ts.isoformat()}), encoding="utf-8")
    s3 = ssr_shadow.run_once(now_et=now, bar_fetcher=fetcher, signal_fn=signal_fn)
    assert s3.get("skipped_lock_held") is None, "stale lock must be broken, not honored"
    assert not ssr_shadow.LOCK_FILE.exists(), "lock released after the pass"


def test_weekend_or_holiday_no_new_bars_is_a_clean_noop(monkeypatch):
    """REFUTE-pass (d): a fire that observes NO new bars beyond a config's own watermark
    (weekend/holiday -- yfinance keeps returning the same trailing window, nothing new lands
    after the last real session close) must be a silent no-op: zero new signals, zero opens,
    zero errors -- never a crash, never a spurious 'insufficient_bars' error just because the
    tail of the window didn't move."""
    monkeypatch.setattr(ssr_shadow, "CONFIGS", {"NQ": ssr_shadow.CONFIGS["NQ"]})
    bars = _make_bars(30)  # e.g. Friday's close, unchanged across a weekend's worth of fires

    def fetcher(symbol, interval, period):
        return bars.copy()  # SAME frame every fire -- exactly what a dead weekend looks like

    def signal_fn(bars_, snapshots, atr, params):
        return []  # detector legitimately finds nothing new either

    now = bars["timestamp_et"].iloc[-1]
    ssr_shadow._atomic_write_json(ssr_shadow.STATE_FILE, {
        "configs": {"NQ": {"watermark_bar_ts_et": bars["timestamp_et"].iloc[-2].isoformat()}},
        "positions": {},
    })
    summary = ssr_shadow.run_once(now_et=now, bar_fetcher=fetcher, signal_fn=signal_fn)
    assert summary["errors"] == []
    assert summary["opened"] == 0
    assert summary["new_signals"] == 0
    assert summary["positions_open"] == 0

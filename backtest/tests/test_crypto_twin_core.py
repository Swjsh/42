"""Tests for the crypto twin (T1+T2) -- setup/scripts/crypto_twin_{core,broker,levels,signal}.py.

Covers: closed-bar-only bar adapter (C6), UTC-day level anchors, exit_manager integration
on twin fixtures (structure stop / catastrophe cap / TP1 / trail / max-hold) via a mocked
broker (no network, no real account needed), the UTC-day breaker, namespace isolation
(static guard -- no state write escapes automation/state/crypto-twin/), and decision-row
schema compatibility with automation/state/core-decisions.jsonl.

All state-writing tests use TwinConfig(state_dir=<tmp>/automation/state/crypto-twin) --
the exact namespace suffix _assert_twin_namespace requires -- so runs are fully isolated
from the real production ledger under a pytest tmp_path.
"""
from __future__ import annotations

import ast
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", "automation/state/fleet", ""):
    sys.path.insert(0, str(REPO / _p) if _p else str(REPO))

import crypto_twin_core as ctc  # noqa: E402
import crypto_twin_broker as ctb  # noqa: E402
import crypto_twin_levels as ctl  # noqa: E402
import crypto_twin_signal as cts  # noqa: E402
import exit_manager as em  # noqa: E402
from crypto.lib.bar import Bar  # noqa: E402


def _twin_cfg(tmp_path: Path, **overrides) -> ctc.TwinConfig:
    state_dir = tmp_path / "automation" / "state" / "crypto-twin"
    return ctc.TwinConfig(state_dir=state_dir, **overrides)


def _raw_bar(ts: datetime, o: float, h: float, l: float, c: float, v: float = 1.0) -> dict:
    return {"t": ts.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": o, "h": h, "l": l, "c": c, "v": v}


# ============================================================================
# Bar adapter -- closed-bar only (C6)
# ============================================================================
def test_fetch_closed_bars_excludes_in_progress_bar(tmp_path):
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 10, 12, 7, 30, tzinfo=timezone.utc)  # mid-way through a 5m bar
    raw = [
        _raw_bar(datetime(2026, 7, 10, 11, 55, tzinfo=timezone.utc), 100, 101, 99, 100.5),
        _raw_bar(datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc), 100.5, 102, 100, 101.5),
        # in-progress: opens 12:05, closes 12:10 > now (12:07:30)
        _raw_bar(datetime(2026, 7, 10, 12, 5, tzinfo=timezone.utc), 101.5, 103, 101, 102.8),
    ]
    bars, meta = ctc.fetch_closed_bars(cfg, now_utc=now, raw_bars=raw)
    assert len(bars) == 2
    assert bars[-1].open_time == datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    assert meta["bars_rejected_as_in_progress"] == 1
    assert meta["verdict"] == "ok"


def test_fetch_closed_bars_stale_feed_flagged(tmp_path):
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 10, 14, 0, 0, tzinfo=timezone.utc)  # 2h after the only bar closed
    raw = [_raw_bar(datetime(2026, 7, 10, 11, 55, tzinfo=timezone.utc), 100, 101, 99, 100.5)]
    bars, meta = ctc.fetch_closed_bars(cfg, now_utc=now, raw_bars=raw)
    assert meta["verdict"] == "stale_data"


def test_run_tick_holds_on_bad_bars_never_crashes(tmp_path):
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 10, 14, 0, 0, tzinfo=timezone.utc)
    row = ctc.run_tick(cfg, live=False, now_utc=now, raw_bars=[])
    assert row["action"] == "HOLD_BAD_BARS"
    assert row["twin"] is True


# ============================================================================
# UTC-day level anchors
# ============================================================================
def test_build_level_set_prior_and_intraday():
    prior_day = datetime(2026, 7, 9, tzinfo=timezone.utc)
    today = datetime(2026, 7, 10, tzinfo=timezone.utc)
    bars = [
        Bar(open_time=prior_day + timedelta(hours=2), open=100, high=110, low=95, close=105,
           volume=1, granularity_seconds=300, source="test"),
        Bar(open_time=prior_day + timedelta(hours=20), open=105, high=108, low=90, close=92,
           volume=1, granularity_seconds=300, source="test"),  # prior-day low=90, close=92 (last prior bar)
        Bar(open_time=today + timedelta(hours=1), open=92, high=97, low=91, close=96,
           volume=1, granularity_seconds=300, source="test"),
        Bar(open_time=today + timedelta(hours=2), open=96, high=99, low=94, close=98,
           volume=1, granularity_seconds=300, source="test"),
    ]
    now = today + timedelta(hours=2, minutes=5)
    levels = ctl.build_level_set(bars, now)
    assert levels.prior_day_high.price == 110
    assert levels.prior_day_low.price == 90
    assert levels.prior_day_close.price == 92
    assert levels.intraday_high.price == 99
    assert levels.intraday_low.price == 91
    assert levels.session_date_utc == "2026-07-10"


def test_build_level_set_no_look_ahead():
    """A bar at/after now_utc must never contribute to intraday H/L."""
    today = datetime(2026, 7, 10, tzinfo=timezone.utc)
    bars = [
        Bar(open_time=today + timedelta(hours=1), open=100, high=101, low=99, close=100,
           volume=1, granularity_seconds=300, source="test"),
        # this bar is AFTER `now` -- must be excluded
        Bar(open_time=today + timedelta(hours=5), open=100, high=500, low=1, close=100,
           volume=1, granularity_seconds=300, source="test"),
    ]
    now = today + timedelta(hours=2)
    levels = ctl.build_level_set(bars, now)
    assert levels.intraday_high.price == 101
    assert levels.intraday_low.price == 99


def test_nearest_directional_level_filters_by_side():
    levels = [ctl.Level(price=110, kind=ctl.LevelKind.PRIOR_PERIOD_HIGH, strength=3),
             ctl.Level(price=90, kind=ctl.LevelKind.PRIOR_PERIOD_LOW, strength=3)]
    # bull wants support AT/BELOW spot
    lvl = ctl.nearest_directional_level(levels, spot=100, side="bull", max_distance_pct=50)
    assert lvl.price == 90
    # bear wants resistance AT/ABOVE spot
    lvl = ctl.nearest_directional_level(levels, spot=100, side="bear", max_distance_pct=50)
    assert lvl.price == 110


# ============================================================================
# Breaker (UTC-day kill-switch) -- reuses crypto.lib.kill_switch
# ============================================================================
def test_breaker_fresh_day_seeds_from_starting_equity(tmp_path):
    cfg = _twin_cfg(tmp_path, starting_equity=2000.0, daily_loss_kill_switch_pct=0.30)
    now = datetime(2026, 7, 10, 5, 0, tzinfo=timezone.utc)
    state = ctc.load_breaker(cfg, now_utc=now, current_equity=2000.0)
    assert state.start_of_day_equity == 2000.0
    assert state.tripped is False


def test_breaker_trips_and_latches(tmp_path):
    cfg = _twin_cfg(tmp_path, starting_equity=2000.0, daily_loss_kill_switch_pct=0.30)
    now = datetime(2026, 7, 10, 5, 0, tzinfo=timezone.utc)
    state = ctc.load_breaker(cfg, now_utc=now, current_equity=2000.0)
    # drop 35% -- past the 30% threshold
    state = ctc.ks_tick(state, 1300.0)
    assert state.tripped is True
    ctc.save_breaker(cfg, state, now_utc=now, current_equity=1300.0)
    # recovery does NOT un-trip (latching)
    state2 = ctc.ks_tick(state, 2500.0)
    assert state2.tripped is True


def test_breaker_carries_equity_forward_on_utc_day_rollover(tmp_path):
    cfg = _twin_cfg(tmp_path, starting_equity=2000.0)
    day1 = datetime(2026, 7, 10, 23, 0, tzinfo=timezone.utc)
    s1 = ctc.load_breaker(cfg, now_utc=day1, current_equity=2200.0)
    s1 = ctc.ks_tick(s1, 2200.0)
    ctc.save_breaker(cfg, s1, now_utc=day1, current_equity=2200.0)
    day2 = datetime(2026, 7, 11, 0, 5, tzinfo=timezone.utc)  # new UTC day
    s2 = ctc.load_breaker(cfg, now_utc=day2, current_equity=2200.0)
    assert s2.start_of_day_equity == 2200.0  # carried forward, not reset to cfg.starting_equity
    assert s2.tripped is False


# ============================================================================
# risk_gate wiring -- the whole-number proxy unit
# ============================================================================
def test_risk_gate_proxy_notional_matches_config(tmp_path):
    cfg = _twin_cfg(tmp_path, notional_usd=200.0, min_contracts=1, per_trade_risk_cap_pct=0.30)
    d = ctc._risk_gate_check(cfg, equity=2000.0, sod_equity=2000.0, kill_switch_tripped=False,
                             position_status="flat", setup_name="TEST")
    assert d.allowed is True
    assert "$200" in d.reason


def test_risk_gate_proxy_blocks_when_kill_switch_tripped(tmp_path):
    cfg = _twin_cfg(tmp_path)
    d = ctc._risk_gate_check(cfg, equity=1300.0, sod_equity=2000.0, kill_switch_tripped=True,
                             position_status="flat", setup_name="TEST")
    assert d.allowed is False
    assert d.code == "KILL_SWITCH"


# ============================================================================
# exit_manager integration on twin fixtures (mocked broker, real exit_manager)
# ============================================================================
class _FakeBroker:
    """Records every call; simulates fills/quotes deterministically. No network."""
    def __init__(self):
        self.orders = []
        self.sells = []
        self.closes = []
        self.position_qty = 0.0
        self.quote = None  # (ask, bid)

    def place_crypto_order(self, creds, *, symbol, side, notional=None, qty=None,
                           order_type="market", limit_price=None, live):
        self.orders.append({"symbol": symbol, "side": side, "notional": notional, "qty": qty, "live": live})
        return {"id": "test-order-1", "status": "accepted"}

    def poll_fill(self, creds, order_id, attempts=4, sleep_sec=1.5):
        return {"filled": True, "status": "filled", "filled_qty": self.position_qty,
               "filled_avg_price": 64000.0, "order": {}}

    def get_crypto_position_qty(self, creds, symbol="BTC/USD"):
        return self.position_qty

    def get_crypto_quote_hilo(self, symbol="BTC/USD", creds=None):
        return self.quote

    def market_sell_crypto(self, creds, *, symbol, qty, live):
        self.sells.append({"symbol": symbol, "qty": qty, "live": live})
        return {"id": f"sell-{len(self.sells)}", "status": "accepted"}

    def close_all_crypto(self, creds, *, symbol="BTC/USD", live):
        self.closes.append({"symbol": symbol, "live": live})
        return {"id": f"close-{len(self.closes)}", "status": "accepted"}


@pytest.fixture
def fake_broker(monkeypatch):
    fb = _FakeBroker()
    monkeypatch.setattr(ctc.broker, "place_crypto_order", fb.place_crypto_order)
    monkeypatch.setattr(ctc.broker, "poll_fill", fb.poll_fill)
    monkeypatch.setattr(ctc.broker, "get_crypto_position_qty", fb.get_crypto_position_qty)
    monkeypatch.setattr(ctc.broker, "get_crypto_quote_hilo", fb.get_crypto_quote_hilo)
    monkeypatch.setattr(ctc.broker, "market_sell_crypto", fb.market_sell_crypto)
    monkeypatch.setattr(ctc.broker, "close_all_crypto", fb.close_all_crypto)
    return fb


_CREDS = {"key": "k", "secret": "s", "base_url": "https://paper-api.alpaca.markets"}


def test_place_entry_registers_structure_mode_exit_state(tmp_path, fake_broker):
    cfg = _twin_cfg(tmp_path, notional_usd=200.0)
    fake_broker.position_qty = ctc.entry_qty_btc(cfg)
    entry_time = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    result = ctc.place_entry(cfg, creds=_CREDS, side="bull", price=64000.0,
                             trigger_level=63500.0, live=True)
    assert result["placed"] is True
    # UNIT-LOT MODE (B1a): a QTY-based buy (never notional) -- exactly
    # units_per_entry * unit_qty_btc, the caller never sees a notional kwarg.
    assert fake_broker.orders[0]["qty"] == ctc.entry_qty_btc(cfg)
    assert fake_broker.orders[0]["notional"] is None
    positions = ctc._load_positions(cfg)
    assert "BTC/USD" in positions
    st = em.ExitState.from_dict(positions["BTC/USD"]["exit_state"])
    assert st.stop_mode == "structure"
    assert st.trigger_level == 63500.0
    # THE 2/1 SPLIT (B1a): qty=3 fixed units through the REAL exit_manager int-floor,
    # not an approximation at wide proxy granularity.
    assert st.total_qty == cfg.units_per_entry == 3
    assert st.tp1_qty == 2
    assert st.runner_qty == 1
    # journal has PLACED + FILLED rows, both carrying the unit-lot fields
    journal = [json.loads(l) for l in (cfg.state_dir / "journal.jsonl").read_text().splitlines()]
    assert [r["event"] for r in journal] == ["PLACED", "FILLED"]
    assert journal[0]["units"] == 3
    assert journal[0]["qty_btc"] == ctc.entry_qty_btc(cfg)
    assert journal[0]["scenario"] is None  # organic entry, no scenario tag
    assert journal[1]["units"] == 3


def test_manage_positions_tp1_fires_and_sells_partial(tmp_path, fake_broker):
    cfg = _twin_cfg(tmp_path, notional_usd=200.0)
    fake_broker.position_qty = ctc.entry_qty_btc(cfg)
    entered = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    ctc.place_entry(cfg, creds=_CREDS, side="bull", price=64000.0, trigger_level=63500.0, live=True,
                    now_utc=entered)
    # tp1_premium_pct=0.015 -> tp1_level = 64000*1.015 = 64960
    fake_broker.quote = (65000.0, 64950.0)  # best=65000 >= 64960 -> TP1 fires
    now = entered + timedelta(minutes=10)
    results = ctc.manage_positions(cfg, creds=_CREDS, now_utc=now, live=True)
    assert len(fake_broker.sells) == 1
    # UNIT-LOT MODE (B1a): TP1 sells EXACTLY 2 whole units -- a deterministic
    # units * unit_qty_btc multiply, not a fraction of whatever the broker happens to
    # currently report (see manage_positions' SELL_PARTIAL conversion).
    assert fake_broker.sells[0]["qty"] == pytest.approx(2 * cfg.unit_qty_btc, abs=1e-9)
    positions = ctc._load_positions(cfg)
    st = em.ExitState.from_dict(positions["BTC/USD"]["exit_state"])
    assert st.tp1_filled is True
    assert st.runner_stop_premium == 64000.0  # ratcheted to break-even
    assert st.runner_qty == 1
    journal = [json.loads(l) for l in (cfg.state_dir / "journal.jsonl").read_text().splitlines()]
    managed = [r for r in journal if r["event"] == "MANAGED"]
    assert managed and managed[0]["kind"] == "SELL_PARTIAL"
    # THE task-required literal proof: "a full lifecycle fixture must show tp1 qty 2 --
    # not fractional sells" -- the journal's own "units" field is a plain int, 2.
    assert managed[0]["units"] == 2
    assert isinstance(managed[0]["units"], int)
    assert results[0]["actions"][0]["units"] == 2


def test_manage_positions_trailing_runner_ratchets_then_stops(tmp_path, fake_broker):
    """The post-TP1 runner in "trailing" mode: HWM rally ratchets the stop (RATCHET_STOP,
    no sell), then a pullback through the new trailing floor exits the remainder
    (SELL_ALL, stage="trail") -- the one exit stage the other fixtures don't reach."""
    cfg = _twin_cfg(tmp_path, notional_usd=200.0)
    fake_broker.position_qty = ctc.entry_qty_btc(cfg)
    entered = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    ctc.place_entry(cfg, creds=_CREDS, side="bull", price=64000.0, trigger_level=63500.0, live=True,
                    now_utc=entered)
    # tick 1: TP1 fires (tp1_level=64960) -> runner rides, profit_lock_armed=True, BE floor
    fake_broker.quote = (65000.0, 64950.0)
    ctc.manage_positions(cfg, creds=_CREDS, now_utc=entered + timedelta(minutes=10), live=True)
    assert em.ExitState.from_dict(ctc._load_positions(cfg)["BTC/USD"]["exit_state"]).tp1_filled

    # tick 2: rallies to 65500 (< runner_target 65920) -> trailing floor ratchets UP,
    # no NEW sell beyond tick 1's TP1 partial (trail_pct=0.01 -> floor = 65500*0.99 =
    # 64845, > current BE floor 64000)
    sells_after_tp1 = len(fake_broker.sells)
    fake_broker.quote = (65500.0, 65450.0)
    r2 = ctc.manage_positions(cfg, creds=_CREDS, now_utc=entered + timedelta(minutes=20), live=True)
    assert len(fake_broker.sells) == sells_after_tp1  # pure ratchet, no new sell this tick
    st2 = em.ExitState.from_dict(ctc._load_positions(cfg)["BTC/USD"]["exit_state"])
    assert st2.runner_stop_premium == pytest.approx(65500.0 * 0.99, abs=1e-6)
    assert r2[0]["actions"][0]["kind"] == "RATCHET_STOP"
    assert r2[0]["actions"][0]["stage"] == "trail"

    # tick 3: pulls back through the new trailing floor -> SELL_ALL, stage="trail"
    fake_broker.quote = (65100.0, 64800.0)  # worst=64800 <= floor 64845
    r3 = ctc.manage_positions(cfg, creds=_CREDS, now_utc=entered + timedelta(minutes=30), live=True)
    assert len(fake_broker.sells) == sells_after_tp1 + 1  # the runner's remaining qty, sold this tick
    assert r3[0]["actions"][0]["kind"] == "SELL_ALL"
    assert r3[0]["actions"][0]["stage"] == "trail"
    assert "BTC/USD" not in ctc._load_positions(cfg)
    journal = [json.loads(l) for l in (cfg.state_dir / "journal.jsonl").read_text().splitlines()]
    # B6: EXIT_FILLED is now journaled AFTER CLOSED (additive telemetry) -- CLOSED is no
    # longer guaranteed journal[-1], but it must still be present with the right stage.
    closed_rows = [r for r in journal if r["event"] == "CLOSED"]
    assert closed_rows[-1]["stage"] == "trail"
    assert journal[-1]["event"] == "EXIT_FILLED" and journal[-1]["kind"] == "SELL_ALL"


def test_manage_positions_structure_stop_closes_all(tmp_path, fake_broker):
    cfg = _twin_cfg(tmp_path, notional_usd=200.0)
    fake_broker.position_qty = ctc.entry_qty_btc(cfg)
    entered = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    ctc.place_entry(cfg, creds=_CREDS, side="bull", price=64000.0, trigger_level=63500.0, live=True,
                    now_utc=entered)
    fake_broker.quote = (64100.0, 64050.0)  # no premium-based exit triggered
    now = entered + timedelta(minutes=10)
    # closed 5m bar broke BELOW the trigger level -> structure stop (bull/"C" side)
    results = ctc.manage_positions(cfg, creds=_CREDS, now_utc=now, live=True,
                                   last_closed_close=63400.0)
    assert len(fake_broker.sells) == 1
    assert results[0]["actions"][0]["stage"] == "structure_stop"
    positions = ctc._load_positions(cfg)
    assert "BTC/USD" not in positions  # fully closed, pruned
    journal = [json.loads(l) for l in (cfg.state_dir / "journal.jsonl").read_text().splitlines()]
    # B6: EXIT_FILLED now trails CLOSED (additive telemetry, see test_manage_positions_
    # trailing_runner_ratchets_then_stops for the same pattern).
    closed_rows = [r for r in journal if r["event"] == "CLOSED"]
    assert closed_rows[-1]["stage"] == "structure_stop"
    exit_filled_rows = [r for r in journal if r["event"] == "EXIT_FILLED"]
    # reason is "structure_stop @ {trigger_level}" -- trigger_level=63500.0 for this fixture
    assert exit_filled_rows[-1]["expected_price"] == pytest.approx(63500.0)
    # fake_broker.poll_fill always returns filled_avg_price=64000.0
    assert exit_filled_rows[-1]["fill_price"] == pytest.approx(64000.0)
    assert exit_filled_rows[-1]["slippage_bps"] == pytest.approx(
        (64000.0 - 63500.0) / 63500.0 * 10_000.0)


def test_manage_positions_max_hold_flattens(tmp_path, fake_broker):
    cfg = _twin_cfg(tmp_path, notional_usd=200.0, max_hold_hours=6.0)
    fake_broker.position_qty = ctc.entry_qty_btc(cfg)
    entered = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    ctc.place_entry(cfg, creds=_CREDS, side="bull", price=64000.0, trigger_level=None, live=True,
                    now_utc=entered)
    later = entered + timedelta(hours=6, minutes=1)
    results = ctc.manage_positions(cfg, creds=_CREDS, now_utc=later, live=True)
    assert results[0]["action"] == "MAX_HOLD_FLATTEN"
    assert len(fake_broker.closes) == 1
    positions = ctc._load_positions(cfg)
    assert "BTC/USD" not in positions
    journal = [json.loads(l) for l in (cfg.state_dir / "journal.jsonl").read_text().splitlines()]
    assert journal[-1]["event"] == "CLOSED"
    assert journal[-1]["reason"] == "max_hold_flatten"


def test_manage_positions_catastrophe_cap_when_no_trigger_level(tmp_path, fake_broker):
    """No trigger_level at entry -> from_entry demotes to premium mode. This twin
    intentionally configures a TIGHTER premium-mode fallback (-3%, TwinConfig.exit_shape)
    than exit_manager's own -50% catastrophe default, so the "no level nearby" branch
    gets a realistic chance to fire during a soak instead of only ever riding to
    max-hold (see TwinConfig.exit_shape's docstring) -- proves that fallback wires
    through from_entry correctly, and that it is still bounded by exit_manager's own
    catastrophe_stop_pct field (unchanged at -0.50) as the true tail-risk cap."""
    cfg = _twin_cfg(tmp_path, notional_usd=200.0)
    fake_broker.position_qty = ctc.entry_qty_btc(cfg)
    entered = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    ctc.place_entry(cfg, creds=_CREDS, side="bull", price=64000.0, trigger_level=None, live=True,
                    now_utc=entered)
    positions = ctc._load_positions(cfg)
    st = em.ExitState.from_dict(positions["BTC/USD"]["exit_state"])
    assert st.stop_mode == "premium"
    assert st.premium_stop_pct == cfg.exit_shape["premium_stop_pct"] == -0.03
    assert st.catastrophe_stop_pct == em.CATASTROPHE_STOP_PCT  # tail-risk cap untouched
    fake_broker.quote = (62000.0, 61900.0)  # -3%+ adverse move -> crosses the tighter fallback
    now = entered + timedelta(minutes=10)
    results = ctc.manage_positions(cfg, creds=_CREDS, now_utc=now, live=True)
    assert results[0]["actions"][0]["stage"] == "premium_stop"


# ============================================================================
# B6 friction calibration -- real exit-fill capture (TWIN-B6-SIM-FRICTION-CALIBRATION)
# ============================================================================
def test_parse_reason_price_extracts_trigger_level():
    assert ctc._parse_reason_price("structure_stop @ 64314.98") == pytest.approx(64314.98)
    assert ctc._parse_reason_price("runner_stop @ 64191.71") == pytest.approx(64191.71)
    assert ctc._parse_reason_price("structure_stop @ 64353.43 (runner)") == pytest.approx(64353.43)
    # no embedded trigger price -> genuinely undefined, not zero
    assert ctc._parse_reason_price("time_stop_15:50") is None
    assert ctc._parse_reason_price("max_hold_flatten") is None
    assert ctc._parse_reason_price("ribbon_flip_back") is None
    assert ctc._parse_reason_price(None) is None


def test_manage_positions_watch_mode_never_journals_exit_filled(tmp_path, fake_broker):
    """WATCH mode (live=False): market_sell_crypto returns {"_skipped": ...} with no "id" --
    the B6 poll must never fire (mirrors the pre-existing live-only guard on every other
    broker-touching branch in this module)."""
    cfg = _twin_cfg(tmp_path, notional_usd=200.0)
    fake_broker.position_qty = ctc.entry_qty_btc(cfg)
    entered = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    ctc.place_entry(cfg, creds=_CREDS, side="bull", price=64000.0, trigger_level=63500.0, live=True,
                    now_utc=entered)
    fake_broker.quote = (64100.0, 64050.0)
    now = entered + timedelta(minutes=10)
    ctc.manage_positions(cfg, creds=_CREDS, now_utc=now, live=False, last_closed_close=63400.0)
    journal = [json.loads(l) for l in (cfg.state_dir / "journal.jsonl").read_text().splitlines()]
    assert not any(r["event"] == "EXIT_FILLED" for r in journal)


def test_manage_positions_failed_sell_all_never_journals_exit_filled(tmp_path, fake_broker, monkeypatch):
    """A broker-rejected SELL_ALL (close_failed=True) must never poll for a fill that was
    never accepted -- same guard class as test_manage_positions_failed_sell_all_keeps_
    position_for_retry, extended to the new B6 telemetry call."""
    cfg = _twin_cfg(tmp_path, notional_usd=200.0)
    fake_broker.position_qty = ctc.entry_qty_btc(cfg)
    entered = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    ctc.place_entry(cfg, creds=_CREDS, side="bull", price=64000.0, trigger_level=None, live=True,
                    now_utc=entered)
    monkeypatch.setattr(ctc.broker, "market_sell_crypto",
                        lambda creds, *, symbol, qty, live: {"_error": "HTTP Error 403: Forbidden",
                                                             "_status": 403})
    fake_broker.quote = (62000.0, 61900.0)  # crosses the -3% premium fallback -> SELL_ALL
    now = entered + timedelta(minutes=10)
    ctc.manage_positions(cfg, creds=_CREDS, now_utc=now, live=True)
    journal = [json.loads(l) for l in (cfg.state_dir / "journal.jsonl").read_text().splitlines()]
    assert not any(r["event"] == "EXIT_FILLED" for r in journal)


def test_journal_exit_fill_capture_error_fails_open(tmp_path, monkeypatch):
    """A poll_fill exception must never propagate -- it's telemetry captured AFTER the
    real exit already happened; a capture bug must not become a trading-path incident."""
    cfg = _twin_cfg(tmp_path)

    def _boom(creds, order_id, attempts=4, sleep_sec=1.5):
        raise RuntimeError("network blip")
    monkeypatch.setattr(ctc.broker, "poll_fill", _boom)
    ctc._journal_exit_fill(cfg, creds=_CREDS, order_id="sell-1", kind="SELL_ALL",
                           reason="structure_stop @ 64000.0", scenario=None)  # must not raise
    journal = [json.loads(l) for l in (cfg.state_dir / "journal.jsonl").read_text().splitlines()]
    assert journal[-1]["event"] == "EXIT_FILLED_CAPTURE_ERROR"
    assert "network blip" in journal[-1]["error"]


def test_manage_positions_blocked_no_account_when_creds_none(tmp_path, fake_broker):
    """T2 fails CLOSED (never crashes, never fakes a fill) when no dedicated twin
    account is configured -- the honest 'do not fake it' path."""
    cfg = _twin_cfg(tmp_path, notional_usd=200.0)
    fake_broker.position_qty = ctc.entry_qty_btc(cfg)
    ctc.place_entry(cfg, creds=_CREDS, side="bull", price=64000.0, trigger_level=None, live=True)
    now = datetime(2026, 7, 10, 12, 10, tzinfo=timezone.utc)
    results = ctc.manage_positions(cfg, creds=None, now_utc=now, live=True)
    assert results[0]["action"] == "BLOCKED_NO_ACCOUNT"
    assert not fake_broker.sells and not fake_broker.closes  # zero broker calls attempted


def test_run_tick_bear_verdict_never_places_short(tmp_path, fake_broker):
    """Alpaca crypto is cash/long-only -- an ENTER_BEAR verdict must be logged but
    never sent to the broker."""
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    bars = [ctc._to_bar(_raw_bar(now - timedelta(minutes=5 * i), 100, 101, 99, 100), 300)
           for i in range(60, 0, -1)]
    raw = [{"t": b.open_time.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": b.open, "h": b.high,
           "l": b.low, "c": b.close, "v": b.volume} for b in bars]
    row = ctc.run_tick(cfg, live=True, force_entry="bear", now_utc=now, raw_bars=raw)
    assert row["action"] == "SKIP_NO_SHORT_CRYPTO"
    assert not fake_broker.orders


# ============================================================================
# B1a: entry_qty_btc / unit-lot quantum
# ============================================================================
def test_entry_qty_btc_is_units_times_quantum(tmp_path):
    cfg = _twin_cfg(tmp_path, units_per_entry=3, unit_qty_btc=0.0008)
    assert ctc.entry_qty_btc(cfg) == pytest.approx(0.0024, abs=1e-9)


def test_entry_qty_btc_production_default_is_150_to_250_dollars_at_recent_btc_price():
    """The quantum picked 2026-07-11 from the live BTC/USD close ($64,178.06) must still
    land units_per_entry units in the ~$150-250 band this session's build note claims --
    a coarse sanity check against BTC drifting wildly, not a live price fetch."""
    cfg = ctc.TwinConfig()
    approx_recent_price = 64178.06
    dollar_size = ctc.entry_qty_btc(cfg) * approx_recent_price
    assert 150.0 <= dollar_size <= 250.0


# ============================================================================
# B1a bugfix: ET (not UTC) drives exit_manager's time_stop
# ============================================================================
def test_manage_positions_time_stop_uses_et_not_raw_utc_clock(tmp_path, fake_broker):
    """2026-07-11 bugfix: manage_positions used to pass now_utc.time() (the RAW UTC
    clock) as exit_manager's `now_et` -- comparing it against the ET-labeled
    TIME_STOP_ET=15:50 constant. UTC 15:55 during EDT is ET 11:55 -- nowhere near
    15:50 ET -- so a position must NOT be force-closed at that instant. With the
    pre-fix bug, this exact now_utc would have wrongly tripped time_stop."""
    cfg = _twin_cfg(tmp_path, notional_usd=200.0)
    fake_broker.position_qty = ctc.entry_qty_btc(cfg)
    entered = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    ctc.place_entry(cfg, creds=_CREDS, side="bull", price=64000.0, trigger_level=None, live=True,
                    now_utc=entered)
    fake_broker.quote = (64100.0, 64050.0)  # inert -- doesn't cross tp1/premium_stop
    now_utc = datetime(2026, 7, 10, 15, 55, tzinfo=timezone.utc)  # UTC 15:55 == ET 11:55 (EDT)
    results = ctc.manage_positions(cfg, creds=_CREDS, now_utc=now_utc, live=True)
    assert results[0]["actions"] == []  # no exit fired -- neither a stray time_stop nor anything else
    assert not fake_broker.sells and not fake_broker.closes
    positions = ctc._load_positions(cfg)
    assert "BTC/USD" in positions  # still open -- NOT spuriously time-stopped


def test_manage_positions_time_stop_fires_at_real_et_1550(tmp_path, fake_broker):
    """The inverse of the bugfix guard above: a GENUINE ET 15:50+ crossing must still
    force-close pre-TP1 (proves the fix converts correctly, doesn't just disable
    time_stop outright). UTC 19:55 during EDT == ET 15:55. max_hold_hours is widened
    so the (unrelated) duration guard can't preempt the specific stage under test."""
    cfg = _twin_cfg(tmp_path, notional_usd=200.0, max_hold_hours=24.0)
    fake_broker.position_qty = ctc.entry_qty_btc(cfg)
    entered = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    ctc.place_entry(cfg, creds=_CREDS, side="bull", price=64000.0, trigger_level=None, live=True,
                    now_utc=entered)
    fake_broker.quote = (64100.0, 64050.0)  # inert -- the ONLY thing that should fire is time_stop
    now_utc = datetime(2026, 7, 10, 19, 55, tzinfo=timezone.utc)  # UTC 19:55 == ET 15:55 (EDT)
    results = ctc.manage_positions(cfg, creds=_CREDS, now_utc=now_utc, live=True)
    assert results[0]["actions"][0]["stage"] == "time_stop"
    assert len(fake_broker.sells) == 1


# ============================================================================
# B1a bugfix: run_tick threads last_closed_close so structure_stop is reachable
# ============================================================================
def test_run_tick_wires_last_closed_close_into_structure_stop(tmp_path, fake_broker):
    """2026-07-11 bugfix: run_tick never forwarded its own just-computed `price` (the
    latest CLOSED 5m bar's close) into manage_positions' last_closed_close -- meaning a
    stop_mode='structure' position could NEVER exit via the dedicated chart-level branch
    through the real run_tick() entrypoint (only when a caller invoked manage_positions
    directly with an explicit override, as the older structure-stop fixture test does).
    This drives the WHOLE tick through run_tick (not manage_positions directly) with a
    trigger_level already breached by the current closed bar's price, and asserts the
    structure stop actually fires -- proving the wiring, not just the exit_manager math
    (which test_manage_positions_structure_stop_closes_all already covers)."""
    cfg = _twin_cfg(tmp_path, notional_usd=200.0)
    fake_broker.position_qty = ctc.entry_qty_btc(cfg)
    entered = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    ctc.place_entry(cfg, creds=_CREDS, side="bull", price=64000.0, trigger_level=63900.0, live=True,
                    now_utc=entered)
    positions = ctc._load_positions(cfg)
    assert em.ExitState.from_dict(positions["BTC/USD"]["exit_state"]).stop_mode == "structure"

    now = entered + timedelta(minutes=5)
    bars = [ctc._to_bar(_raw_bar(now - timedelta(minutes=5 * i), 63800, 63850, 63750, 63800), 300)
           for i in range(60, 0, -1)]
    raw = [{"t": b.open_time.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": b.open, "h": b.high,
           "l": b.low, "c": b.close, "v": b.volume} for b in bars]  # last closed bar's close=63800 < trigger 63900
    fake_broker.quote = (63900.0, 63850.0)  # not a premium-stop touch on its own
    row = ctc.run_tick(cfg, live=True, now_utc=now, raw_bars=raw)
    assert row["exit_pass"][0]["actions"][0]["stage"] == "structure_stop"
    assert "BTC/USD" not in ctc._load_positions(cfg)


# ============================================================================
# B1b plumbing: trigger_level_offset_pct / scenario_tag (crypto_twin_scenarios.py's
# only intended caller-facing surface on run_tick/place_entry)
# ============================================================================
def test_run_tick_trigger_level_offset_pct_overrides_real_level_lookup(tmp_path, fake_broker):
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    bars = [ctc._to_bar(_raw_bar(now - timedelta(minutes=5 * i), 100, 101, 99, 100), 300)
           for i in range(60, 0, -1)]
    raw = [{"t": b.open_time.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": b.open, "h": b.high,
           "l": b.low, "c": b.close, "v": b.volume} for b in bars]
    row = ctc.run_tick(cfg, live=False, force_entry="bull", now_utc=now, raw_bars=raw,
                       trigger_level_offset_pct=0.0004)
    assert row["trigger_level_exact"] == pytest.approx(round(100 * 1.0004, 2))


def test_run_tick_scenario_tag_flows_through_placed_journal_and_decision_row(tmp_path, fake_broker):
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    bars = [ctc._to_bar(_raw_bar(now - timedelta(minutes=5 * i), 100, 101, 99, 100), 300)
           for i in range(60, 0, -1)]
    raw = [{"t": b.open_time.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": b.open, "h": b.high,
           "l": b.low, "c": b.close, "v": b.volume} for b in bars]
    row = ctc.run_tick(cfg, live=True, force_entry="bull", now_utc=now, raw_bars=raw,
                       scenario_tag="ENTRY_TP1_TRAIL")
    assert row["action"] == "ENTERED"
    assert row["scenario"] == "ENTRY_TP1_TRAIL"
    positions = ctc._load_positions(cfg)
    assert positions["BTC/USD"]["scenario"] == "ENTRY_TP1_TRAIL"
    journal = [json.loads(l) for l in (cfg.state_dir / "journal.jsonl").read_text().splitlines()]
    assert journal[0]["scenario"] == "ENTRY_TP1_TRAIL"
    assert journal[1]["scenario"] == "ENTRY_TP1_TRAIL"

    # a follow-up MANAGING tick (unforced -- exactly how the scheduler drives an
    # already-open scenario) must still carry the tag through decisions + journal.
    fake_broker.quote = (100.5, 100.4)  # inert
    now2 = now + timedelta(minutes=5)
    bars2 = bars + [ctc._to_bar(_raw_bar(now2 - timedelta(minutes=5), 100, 101, 99, 100.2), 300)]
    raw2 = [{"t": b.open_time.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": b.open, "h": b.high,
            "l": b.low, "c": b.close, "v": b.volume} for b in bars2]
    row2 = ctc.run_tick(cfg, live=True, now_utc=now2, raw_bars=raw2)
    assert row2["scenario"] == "ENTRY_TP1_TRAIL"  # carried via scenario_before, no forcing needed


def test_run_tick_failed_entry_does_not_falsely_tag_scenario(tmp_path, fake_broker, monkeypatch):
    """A forced tick where the entry attempt FAILS (e.g. risk_gate denies it) must not
    report a scenario tag on a decision row where nothing was actually opened."""
    cfg = _twin_cfg(tmp_path)
    monkeypatch.setattr(ctc, "_risk_gate_check",
                        lambda *a, **k: ctc.rg.Deny("RISK_CAP", "denied for test"))
    now = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    bars = [ctc._to_bar(_raw_bar(now - timedelta(minutes=5 * i), 100, 101, 99, 100), 300)
           for i in range(60, 0, -1)]
    raw = [{"t": b.open_time.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": b.open, "h": b.high,
           "l": b.low, "c": b.close, "v": b.volume} for b in bars]
    row = ctc.run_tick(cfg, live=True, force_entry="bull", now_utc=now, raw_bars=raw,
                       scenario_tag="ENTRY_TP1_TRAIL")
    assert row["action"] == "BLOCKED_RISK_CAP"
    assert row["scenario"] is None
    assert not fake_broker.orders


# ============================================================================
# B1a: get_open_position / read_breaker_tripped (public accessors for
# crypto_twin_scenarios.py's scheduling gate)
# ============================================================================
def test_get_open_position_none_when_flat(tmp_path):
    cfg = _twin_cfg(tmp_path)
    assert ctc.get_open_position(cfg) is None


def test_get_open_position_returns_the_record_when_open(tmp_path, fake_broker):
    cfg = _twin_cfg(tmp_path, notional_usd=200.0)
    fake_broker.position_qty = ctc.entry_qty_btc(cfg)
    ctc.place_entry(cfg, creds=_CREDS, side="bull", price=64000.0, trigger_level=None, live=True,
                    scenario_tag="ENTRY_MAX_HOLD")
    rec = ctc.get_open_position(cfg)
    assert rec is not None
    assert rec["scenario"] == "ENTRY_MAX_HOLD"


def test_read_breaker_tripped_none_when_no_breaker_file(tmp_path):
    cfg = _twin_cfg(tmp_path)
    assert ctc.read_breaker_tripped(cfg) is None


def test_read_breaker_tripped_reads_persisted_flag(tmp_path):
    cfg = _twin_cfg(tmp_path, starting_equity=2000.0, daily_loss_kill_switch_pct=0.30)
    now = datetime(2026, 7, 10, 5, 0, tzinfo=timezone.utc)
    state = ctc.load_breaker(cfg, now_utc=now, current_equity=2000.0)
    state = ctc.ks_tick(state, 1300.0)  # -35% -- trips
    ctc.save_breaker(cfg, state, now_utc=now, current_equity=1300.0)
    assert ctc.read_breaker_tripped(cfg) is True


# ============================================================================
# Namespace isolation -- static guard (mirrors test_fleet_journal_bridge.py's AST guard)
# ============================================================================
_TWIN_MODULE_FILES = [
    REPO / "setup" / "scripts" / "crypto_twin_core.py",
    REPO / "setup" / "scripts" / "crypto_twin_broker.py",
    REPO / "setup" / "scripts" / "crypto_twin_levels.py",
    REPO / "setup" / "scripts" / "crypto_twin_signal.py",
    REPO / "setup" / "scripts" / "crypto_twin_scenarios.py",  # B1b -- everything it writes
                                                               # (path-coverage.json, scenario-
                                                               # state.json, incidents.jsonl) is
                                                               # under cfg.state_dir, same as core.
    REPO / "setup" / "scripts" / "crypto_twin_entry_quality.py",  # B3 -- entry-quality.json is
                                                                   # under the state_dir it is
                                                                   # handed, same as core.
]

_WRITE_ATTR_NAMES = {"write_text", "write_bytes", "mkdir"}


def _is_write_call(node: ast.Call) -> bool:
    """True for open(..., "w"/"a"/...) and Path.write_text/write_bytes/mkdir calls."""
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in _WRITE_ATTR_NAMES:
        return True
    if isinstance(func, ast.Name) and func.id == "open":
        # open(path, mode, ...) -- flag unless mode is explicitly read-only ("r"/"rb").
        mode = None
        if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
            mode = node.args[1].value
        for kw in node.keywords:
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                mode = kw.value.value
        return mode is None or (isinstance(mode, str) and mode not in ("r", "rb"))
    return False


def test_static_no_state_writes_outside_crypto_twin_namespace():
    """Parses each twin module's source, finds every WRITE-actuating call (open() in a
    non-read mode, Path.write_text/write_bytes/mkdir), and asserts no string literal
    ARGUMENT of that call names a path under "automation/state" that isn't crypto-twin's
    own -- catches a future edit that accidentally hardcodes a write into fleet/core
    state. Deliberately scoped to write-CALL arguments only (not every string literal in
    the file -- a naive whole-file scan false-positives on sys.path.insert() read-path
    entries and on docstring prose that merely MENTIONS a path for documentation).
    """
    offenders = []
    for path in _TWIN_MODULE_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and _is_write_call(node)):
                continue
            for sub in ast.walk(node):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    s = sub.value.replace("\\\\", "/").replace("\\", "/")
                    if "automation/state" in s and "crypto-twin" not in s and "crypto_twin" not in s:
                        offenders.append((path.name, s))
    assert offenders == [], f"state path literal(s) in a write call outside crypto-twin namespace: {offenders}"


def test_assert_twin_namespace_rejects_foreign_state_dir(tmp_path):
    bad_cfg = ctc.TwinConfig(state_dir=tmp_path / "automation" / "state" / "fleet")
    with pytest.raises(ValueError):
        ctc._assert_twin_namespace(bad_cfg)


def test_assert_twin_namespace_accepts_production_default():
    ctc._assert_twin_namespace(ctc.TwinConfig())  # the real production default -- must never raise


def test_force_entry_flag_only_reachable_via_twin_config(tmp_path, fake_broker):
    """--force-entry is a run_tick kwarg gated by _assert_twin_namespace at the top of
    run_tick -- a foreign state_dir raises before force_entry is ever consulted."""
    bad_cfg = ctc.TwinConfig(state_dir=tmp_path / "not-the-twin-namespace")
    with pytest.raises(ValueError):
        ctc.run_tick(bad_cfg, live=True, force_entry="bull")


def test_run_tick_distinguishes_crypto_not_approved_from_no_account(tmp_path, monkeypatch):
    """2026-07-11: a configured-but-unapproved twin account must produce its OWN action
    string, not get silently folded into BLOCKED_NO_ACCOUNT -- otherwise J creates the
    account, still sees nothing trade, and has no way to tell the two failure modes apart
    (see crypto_twin_broker.CryptoNotApprovedError + https://docs.alpaca.markets/us/docs/
    crypto-trading-1: crypto is an approval STATE on an existing account, not a separate
    account type)."""
    cfg = _twin_cfg(tmp_path, notional_usd=200.0)
    monkeypatch.setattr(
        ctc.broker, "get_twin_creds",
        lambda: (_ for _ in ()).throw(ctc.broker.CryptoNotApprovedError("crypto_status='INACTIVE'")),
    )
    now = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    bars = [ctc._to_bar(_raw_bar(now - timedelta(minutes=5 * i), 100, 101, 99, 100), 300)
           for i in range(60, 0, -1)]
    raw = [{"t": b.open_time.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": b.open, "h": b.high,
           "l": b.low, "c": b.close, "v": b.volume} for b in bars]
    row = ctc.run_tick(cfg, live=True, force_entry="bull", now_utc=now, raw_bars=raw)
    assert row["action"].startswith("BLOCKED_CRYPTO_NOT_APPROVED")
    assert "INACTIVE" in row["action"]


# ============================================================================
# Decision-row schema compatibility with core-decisions.jsonl
# ============================================================================
_CORE_DECISIONS_KEYS = {
    "ts_et", "account", "armed", "spy", "ribbon", "spread_cents", "vix", "htf_15m",
    "verdict", "side", "setup", "triggers", "reason", "trigger_level_exact", "exit_pass", "action",
}


def test_decision_row_has_core_decisions_key_set_plus_twin_flag(tmp_path):
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    bars = [ctc._to_bar(_raw_bar(now - timedelta(minutes=5 * i), 100, 101, 99, 100), 300)
           for i in range(60, 0, -1)]
    raw = [{"t": b.open_time.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": b.open, "h": b.high,
           "l": b.low, "c": b.close, "v": b.volume} for b in bars]
    row = ctc.run_tick(cfg, live=False, now_utc=now, raw_bars=raw)
    missing = _CORE_DECISIONS_KEYS - set(row.keys())
    assert missing == set(), f"decision row missing core-decisions.jsonl keys: {missing}"
    assert row["twin"] is True
    assert row["account"] == "twin"


def test_decision_row_is_jsonl_appendable(tmp_path):
    """Every row must round-trip through json.dumps/loads (append-only ledger contract)."""
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    row = ctc.run_tick(cfg, live=False, now_utc=now, raw_bars=[])
    encoded = json.dumps(row)
    assert json.loads(encoded) == row
    lines = (cfg.state_dir / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == row


# ============================================================================
# Failed-close guards (2026-07-15, caught LIVE on the TWIN-B3 first passive rep:
# a broker-rejected SELL_ALL -- 403 insufficient balance from the sell-qty
# round-up bug -- still deleted the position record, orphaning REAL broker
# holdings with no exit-managed record. C11: broker is the source of truth.)
# ============================================================================
def test_manage_positions_failed_sell_all_keeps_position_for_retry(tmp_path, fake_broker, monkeypatch):
    cfg = _twin_cfg(tmp_path, notional_usd=200.0)
    fake_broker.position_qty = ctc.entry_qty_btc(cfg)
    entered = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    ctc.place_entry(cfg, creds=_CREDS, side="bull", price=64000.0, trigger_level=None, live=True,
                    now_utc=entered)
    pre_state = ctc._load_positions(cfg)["BTC/USD"]["exit_state"]
    monkeypatch.setattr(ctc.broker, "market_sell_crypto",
                        lambda creds, *, symbol, qty, live: {"_error": "HTTP Error 403: Forbidden",
                                                             "_status": 403})
    fake_broker.quote = (62000.0, 61900.0)  # crosses the -3% premium fallback -> SELL_ALL
    now = entered + timedelta(minutes=10)
    results = ctc.manage_positions(cfg, creds=_CREDS, now_utc=now, live=True)
    assert results[0]["action"] == "CLOSE_FAILED_RETRY"
    positions = ctc._load_positions(cfg)
    assert "BTC/USD" in positions  # record KEPT -- broker still holds the position
    assert positions["BTC/USD"]["exit_state"] == pre_state  # pre-tick state restored
    journal = [json.loads(l) for l in
               (cfg.state_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(r["event"] == "CLOSE_FAILED" for r in journal)
    assert not any(r["event"] == "CLOSED" for r in journal)  # never fakes a CLOSED

    # broker heals -> the next tick re-runs the SAME exit decision and genuinely closes
    monkeypatch.setattr(ctc.broker, "market_sell_crypto", fake_broker.market_sell_crypto)
    results2 = ctc.manage_positions(cfg, creds=_CREDS, now_utc=now + timedelta(minutes=5), live=True)
    assert results2[0]["actions"][0]["kind"] == "SELL_ALL"
    assert "BTC/USD" not in ctc._load_positions(cfg)


def test_manage_positions_failed_max_hold_close_keeps_position_for_retry(tmp_path, fake_broker, monkeypatch):
    cfg = _twin_cfg(tmp_path, notional_usd=200.0)
    fake_broker.position_qty = ctc.entry_qty_btc(cfg)
    entered = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    ctc.place_entry(cfg, creds=_CREDS, side="bull", price=64000.0, trigger_level=None, live=True,
                    now_utc=entered)
    monkeypatch.setattr(ctc.broker, "close_all_crypto",
                        lambda creds, *, symbol, live: {"_error": "boom", "_status": 500})
    now = entered + timedelta(hours=cfg.max_hold_hours + 1)
    results = ctc.manage_positions(cfg, creds=_CREDS, now_utc=now, live=True)
    assert results[0]["action"] == "CLOSE_FAILED_RETRY"
    assert "BTC/USD" in ctc._load_positions(cfg)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

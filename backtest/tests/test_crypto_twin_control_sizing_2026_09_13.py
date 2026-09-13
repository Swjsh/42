"""Guards for GOAL-EARN-YOUR-KEEP item 7b -- crypto twin CONTROL SIZING (2026-09-13).

Covers: (i) organic entries size at 10% of the broker's start-of-day equity, cached once
per UTC day; (ii) FORCED/scenario entries keep the old static ~$200 rail unchanged; (iii)
a broker-equity-read failure fails open to the old rail and journals SIZING_FALLBACK; (iv)
the breaker (TwinConfig.daily_loss_kill_switch_pct) trips at -5% of start-of-day equity,
not the old -30%. Also guards the TP1-leg-math fix this sizing change required: a
dynamically-sized position's SELL_PARTIAL must convert units->BTC using the position's OWN
stamped unit_qty_btc, not the static cfg default (crypto_twin_core.py's own module note:
"so TP1/runner leg math keeps working").
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", "automation/state/fleet", ""):
    sys.path.insert(0, str(REPO / _p) if _p else str(REPO))

import crypto_twin_core as ctc  # noqa: E402
from crypto.lib.kill_switch import tick as ks_tick  # noqa: E402

_CREDS = {"key": "k", "secret": "s", "base_url": "https://paper-api.alpaca.markets"}


def _twin_cfg(tmp_path: Path, **overrides) -> ctc.TwinConfig:
    state_dir = tmp_path / "automation" / "state" / "crypto-twin"
    return ctc.TwinConfig(state_dir=state_dir, **overrides)


def _raw_bar(ts: datetime, o: float, h: float, l: float, c: float, v: float = 1.0) -> dict:
    return {"t": ts.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": o, "h": h, "l": l, "c": c, "v": v}


def _journal_rows(cfg: ctc.TwinConfig) -> list[dict]:
    p = cfg.state_dir / "journal.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


# ============================================================================
# (iv) breaker default + trip threshold
# ============================================================================
def test_default_daily_loss_kill_switch_pct_is_5pct():
    """The knob itself: TwinConfig's default moved 0.30 -> 0.05 (GOAL-EARN-YOUR-KEEP 7b).
    Every existing breaker test pins the value explicitly, so only the DEFAULT needed a
    guard -- this is that guard."""
    assert ctc.TwinConfig().daily_loss_kill_switch_pct == pytest.approx(0.05)


def test_breaker_trips_at_5pct_drawdown_not_30pct(tmp_path):
    cfg = _twin_cfg(tmp_path, starting_equity=10000.0)
    assert cfg.daily_loss_kill_switch_pct == pytest.approx(0.05)
    now = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)

    # seed today's breaker at start_of_day_equity=10000
    state = ctc.load_breaker(cfg, now_utc=now, current_equity=10000.0)
    ctc.save_breaker(cfg, state, now_utc=now, current_equity=10000.0)

    # -3% (well inside 0.30's old floor AND outside 0.05's new one) must NOT trip
    state_3pct = ctc.load_breaker(cfg, now_utc=now, current_equity=9700.0)
    state_3pct = ks_tick(state_3pct, 9700.0)
    assert state_3pct.tripped is False

    # -6% must trip under the new 0.05 threshold (would NOT have tripped under the old 0.30)
    state_6pct = ctc.load_breaker(cfg, now_utc=now, current_equity=9400.0)
    state_6pct = ks_tick(state_6pct, 9400.0)
    assert state_6pct.tripped is True


def test_breaker_json_on_disk_documents_the_new_value(tmp_path):
    """save_breaker's own write carries a `_doc` explaining 0.30 -> 0.05 and how to
    revert -- the task's explicit "documented in the file's `_doc`" requirement."""
    cfg = _twin_cfg(tmp_path, starting_equity=5000.0)
    now = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    state = ctc.load_breaker(cfg, now_utc=now, current_equity=5000.0)
    ctc.save_breaker(cfg, state, now_utc=now, current_equity=5000.0)
    raw = json.loads((cfg.state_dir / "breaker.json").read_text(encoding="utf-8"))
    assert raw["threshold_pct"] == pytest.approx(0.05)
    assert "_doc" in raw and "0.05" in raw["_doc"] and "0.30" in raw["_doc"]


# ============================================================================
# (ii) scenario/forced entries keep the old static rail, untouched
# ============================================================================
def test_scenario_entries_keep_old_200_dollar_rail(tmp_path):
    cfg = _twin_cfg(tmp_path, notional_usd=200.0)
    sizing = ctc._resolve_entry_sizing(cfg, creds=_CREDS, price=64000.0, organic=False,
                                       now_utc=datetime(2026, 9, 13, tzinfo=timezone.utc))
    assert sizing == {"qty_btc": ctc.entry_qty_btc(cfg), "unit_qty_btc": cfg.unit_qty_btc,
                      "notional_usd": 200.0, "sizing_mode": "scenario_rail"}
    # no broker call, no cache file -- a scenario/forced entry never touches sizing.json
    assert not (cfg.state_dir / "sizing.json").exists()


def test_place_entry_default_sizing_is_byte_identical_to_pre_7b(tmp_path, monkeypatch):
    """Every EXISTING direct place_entry() caller (twin_gauntlet, most of
    test_crypto_twin_core.py) passes no `sizing=` kwarg -- must reproduce the exact
    pre-7b qty/notional/mode with ZERO broker calls."""
    calls = []
    monkeypatch.setattr(ctc.broker, "place_crypto_order",
                        lambda creds, *, symbol, side, qty=None, notional=None,
                        order_type="market", limit_price=None, live:
                        (calls.append(qty), {"_skipped": "WATCH"})[1])

    cfg = _twin_cfg(tmp_path, notional_usd=200.0)
    result = ctc.place_entry(cfg, creds=_CREDS, side="bull", price=64000.0,
                             trigger_level=None, live=True)
    assert calls == [ctc.entry_qty_btc(cfg)]
    journal = _journal_rows(cfg)
    assert journal[0]["event"] == "PLACED"
    assert journal[0]["notional_usd"] == 200.0
    assert journal[0]["sizing_mode"] == "scenario_rail"
    assert result["placed"] is False  # WATCH-mode skip via the fake order response


# ============================================================================
# (i) organic entries size at 10% of start-of-day equity, cached once/UTC-day
# ============================================================================
def test_organic_sizing_computes_10pct_of_equity_from_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(ctc.broker, "get_account", lambda creds: {"equity": 9000.0})
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    price = 90000.0

    sizing = ctc._resolve_entry_sizing(cfg, creds=_CREDS, price=price, organic=True, now_utc=now)

    assert sizing["sizing_mode"] == "organic_10pct"
    assert sizing["notional_usd"] == pytest.approx(900.0)  # 10% of 9000
    expected_unit = math.floor(900.0 / cfg.units_per_entry / price * 1e8) / 1e8
    assert sizing["unit_qty_btc"] == pytest.approx(expected_unit, abs=1e-12)
    expected_qty = math.floor(expected_unit * cfg.units_per_entry * 1e8) / 1e8
    assert sizing["qty_btc"] == pytest.approx(expected_qty, abs=1e-12)

    cache = json.loads((cfg.state_dir / "sizing.json").read_text(encoding="utf-8"))
    assert cache["utc_date"] == "2026-09-13"
    assert cache["notional_usd"] == pytest.approx(900.0)
    assert cache["start_of_day_equity"] == pytest.approx(9000.0)


def test_organic_sizing_reads_broker_equity_at_most_once_per_utc_day(tmp_path, monkeypatch):
    calls = {"n": 0}

    def fake_get_account(creds):
        calls["n"] += 1
        return {"equity": 9000.0}

    monkeypatch.setattr(ctc.broker, "get_account", fake_get_account)
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    later_same_day = datetime(2026, 9, 13, 23, 0, tzinfo=timezone.utc)

    s1 = ctc._resolve_entry_sizing(cfg, creds=_CREDS, price=90000.0, organic=True, now_utc=now)
    assert calls["n"] == 1

    # a SECOND organic entry attempt later the SAME UTC day must reuse the cache, not
    # re-read the broker -- even though get_account is still mocked and would happily
    # answer again.
    s2 = ctc._resolve_entry_sizing(cfg, creds=_CREDS, price=91000.0, organic=True,
                                   now_utc=later_same_day)
    assert calls["n"] == 1  # NOT 2
    assert s2["notional_usd"] == s1["notional_usd"] == pytest.approx(900.0)
    # unit_qty_btc DOES still reflect the (cached) notional against the NEW price -- only
    # the equity-derived notional is cached, price-dependent qty is recomputed every time.
    assert s2["unit_qty_btc"] != s1["unit_qty_btc"]

    next_day = datetime(2026, 9, 14, 0, 1, tzinfo=timezone.utc)
    ctc._resolve_entry_sizing(cfg, creds=_CREDS, price=90000.0, organic=True, now_utc=next_day)
    assert calls["n"] == 2  # a new UTC day re-reads once


def test_run_tick_forced_entry_never_calls_broker_get_account(tmp_path, monkeypatch):
    """Blast-radius guard: EVERY existing run_tick(..., force_entry=...) test call site
    must still take the scenario_rail path with zero new broker.get_account calls, since
    is_organic = force_entry is None and scenario_tag is None."""
    calls = {"n": 0}
    monkeypatch.setattr(ctc.broker, "get_account", lambda creds: (calls.__setitem__("n", calls["n"] + 1),
                                                                   {"equity": 9000.0})[1])
    monkeypatch.setattr(ctc.broker, "get_twin_creds", lambda verify_crypto_status=True: _CREDS)
    monkeypatch.setattr(ctc.broker, "place_crypto_order",
                        lambda creds, *, symbol, side, qty=None, notional=None,
                        order_type="market", limit_price=None, live:
                        {"id": "o1", "status": "accepted"})
    monkeypatch.setattr(ctc.broker, "poll_fill",
                        lambda creds, order_id, attempts=4, sleep_sec=1.5:
                        {"filled": True, "status": "filled", "filled_avg_price": 64000.0})
    monkeypatch.setattr(ctc.broker, "get_crypto_position_qty", lambda creds, symbol="BTC/USD": 0.0024)
    monkeypatch.setattr(ctc.broker, "get_crypto_quote_hilo", lambda symbol="BTC/USD", creds=None: (64100.0, 64050.0))
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    raw = [_raw_bar(now - timedelta(minutes=5 * i), 64000, 64050, 63950, 64000)
          for i in range(60, 0, -1)]
    ctc.run_tick(cfg, live=True, force_entry="bull", now_utc=now, raw_bars=raw)
    # get_account is still called once by run_tick's own top-of-tick equity read (pre-
    # existing behavior, unrelated to sizing) -- but the SIZING module must not add a
    # second call for a forced entry, so this must stay at exactly 1.
    assert calls["n"] == 1
    journal = _journal_rows(cfg)
    placed = [r for r in journal if r.get("event") == "PLACED"]
    assert placed and placed[0]["sizing_mode"] == "scenario_rail"


# ============================================================================
# (iii) fail-open to the old rail on a broker failure
# ============================================================================
def test_organic_sizing_falls_back_on_broker_exception(tmp_path, monkeypatch):
    def _boom(creds):
        raise ConnectionError("no network")
    monkeypatch.setattr(ctc.broker, "get_account", _boom)
    cfg = _twin_cfg(tmp_path, notional_usd=200.0)
    now = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)

    sizing = ctc._resolve_entry_sizing(cfg, creds=_CREDS, price=64000.0, organic=True, now_utc=now)

    assert sizing["sizing_mode"] == "fallback_rail"
    assert sizing["notional_usd"] == 200.0
    assert sizing["qty_btc"] == ctc.entry_qty_btc(cfg)
    assert not (cfg.state_dir / "sizing.json").exists()  # a failed read is never cached

    journal = _journal_rows(cfg)
    fallback_rows = [r for r in journal if r["event"] == "SIZING_FALLBACK"]
    assert len(fallback_rows) == 1
    assert fallback_rows[0]["sizing_mode"] == "fallback_rail"
    assert fallback_rows[0]["notional_usd"] == 200.0


def test_organic_sizing_falls_back_when_broker_returns_error(tmp_path, monkeypatch):
    monkeypatch.setattr(ctc.broker, "get_account", lambda creds: {"_error": "401 unauthorized"})
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    sizing = ctc._resolve_entry_sizing(cfg, creds=_CREDS, price=64000.0, organic=True, now_utc=now)
    assert sizing["sizing_mode"] == "fallback_rail"


def test_organic_sizing_falls_back_when_creds_are_none(tmp_path):
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    sizing = ctc._resolve_entry_sizing(cfg, creds=None, price=64000.0, organic=True, now_utc=now)
    assert sizing["sizing_mode"] == "fallback_rail"
    assert sizing["notional_usd"] == cfg.notional_usd


# ============================================================================
# every entry row in journal.jsonl carries notional_usd + sizing_mode
# ============================================================================
def test_placed_and_filled_journal_rows_carry_notional_and_sizing_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(ctc.broker, "place_crypto_order",
                        lambda creds, *, symbol, side, qty=None, notional=None,
                        order_type="market", limit_price=None, live:
                        {"id": "o1", "status": "accepted"})
    monkeypatch.setattr(ctc.broker, "poll_fill",
                        lambda creds, order_id, attempts=4, sleep_sec=1.5:
                        {"filled": True, "status": "filled", "filled_avg_price": 90100.0})
    cfg = _twin_cfg(tmp_path)
    sizing = {"qty_btc": 0.009, "unit_qty_btc": 0.003, "notional_usd": 900.0,
             "sizing_mode": "organic_10pct"}
    ctc.place_entry(cfg, creds=_CREDS, side="bull", price=90000.0, trigger_level=None,
                    live=True, sizing=sizing)
    journal = _journal_rows(cfg)
    events = {r["event"]: r for r in journal}
    assert events["PLACED"]["notional_usd"] == 900.0
    assert events["PLACED"]["sizing_mode"] == "organic_10pct"
    assert events["FILLED"]["notional_usd"] == 900.0
    assert events["FILLED"]["sizing_mode"] == "organic_10pct"


# ============================================================================
# TP1/runner leg math keeps working for a dynamically-sized organic position
# ============================================================================
def test_tp1_partial_sell_uses_the_positions_own_unit_qty_btc(tmp_path, monkeypatch):
    """The whole reason manage_positions/_remaining_qty_btc needed a fix: an organically-
    sized position's unit_qty_btc can differ from cfg.unit_qty_btc (0.0008). A SELL_PARTIAL
    must sell units_sold * THIS position's own quantum, not the static default."""
    sells = []
    monkeypatch.setattr(ctc.broker, "place_crypto_order",
                        lambda creds, *, symbol, side, qty=None, notional=None,
                        order_type="market", limit_price=None, live:
                        {"id": "o1", "status": "accepted"})
    monkeypatch.setattr(ctc.broker, "poll_fill",
                        lambda creds, order_id, attempts=4, sleep_sec=1.5:
                        {"filled": True, "status": "filled", "filled_avg_price": 90000.0})
    monkeypatch.setattr(ctc.broker, "get_crypto_position_qty", lambda creds, symbol="BTC/USD": 0.03)
    monkeypatch.setattr(ctc.broker, "get_crypto_quote_hilo",
                        lambda symbol="BTC/USD", creds=None: (91500.0, 91400.0))  # above TP1

    def _sell(creds, *, symbol, qty, live):
        sells.append(qty)
        return {"id": "sell-1", "status": "accepted"}
    monkeypatch.setattr(ctc.broker, "market_sell_crypto", _sell)

    cfg = _twin_cfg(tmp_path)  # exit_shape tp1_premium_pct=0.015 -> TP1 at 90000*1.015=91350
    organic_unit_qty_btc = 0.01  # deliberately far from cfg.unit_qty_btc (0.0008)
    sizing = {"qty_btc": round(organic_unit_qty_btc * cfg.units_per_entry, 8),
             "unit_qty_btc": organic_unit_qty_btc, "notional_usd": 2700.0,
             "sizing_mode": "organic_10pct"}
    entered = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    ctc.place_entry(cfg, creds=_CREDS, side="bull", price=90000.0, trigger_level=None,
                    live=True, now_utc=entered, sizing=sizing)

    positions = ctc._load_positions(cfg)
    assert positions["BTC/USD"]["unit_qty_btc"] == pytest.approx(organic_unit_qty_btc)

    now = entered + datetime.min.replace(tzinfo=timezone.utc).__class__.min.time().__class__() \
        if False else entered  # no-op, keep now readable below
    ctc.manage_positions(cfg, creds=_CREDS, now_utc=entered.replace(minute=10), live=True)

    assert len(sells) == 1
    # 2 TP1 units at the position's OWN 0.01 BTC/unit quantum -- NOT cfg.unit_qty_btc (0.0008)
    assert sells[0] == pytest.approx(2 * organic_unit_qty_btc, abs=1e-9)

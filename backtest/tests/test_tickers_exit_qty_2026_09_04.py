"""Regression guards for TWO bugs the 2026-09-04 adversarial review found in
multi/core.py::manage_open_positions BEFORE the tickers-lane's armed paper accounts went live
at 09:35 ET, plus the accompanying tickers_execute_support.py / liquidity-gate fixes shipped
in the same pass.

BUG 1 (BLOCKER) -- exit qty was the ORIGINAL entry qty, never broker truth. `evaluate_exit` was
called with `open_qty=getattr(rec, "qty", 0)` -- position_state.py:88 documents `.qty` as the
ORIGINAL entry qty, never decremented after a partial close. qty 3, TP1 sells 1, broker holds
2, every later SELL_ALL asked the broker to close 3 -> rejected -> the runner rode unmanaged.
Fixed by reading broker truth (`open_opts`, this tick's REAL positions) instead.

BUG 2 (HIGH) -- the theta-budget stage compared an INTRADAY entry price against the funnel's
1Day bar, which `fetch_bars_batch` only ever returns as a CLOSED bar (C6 no-look-ahead) -- so
intraday that daily bar is still YESTERDAY's close. Fixed by reading a live last-trade first
(`core.fetch_underlying_last`) and falling back to the (disclosed) daily close only on failure.

Also covered: BUG 3's `entry.liquidity_gate.min_premium_dollars` optional floor, and
`tickers_execute_support.re_derive_exit_record`'s new preference for the row's own persisted
open_qty/underlying_price/atr14 over rec.qty / a fresh bars_facts() recomputation.

No network anywhere in this file. `core.fetch_option_quote_checked` / `core.fetch_underlying_last`
/ `core.now_et` are monkeypatched; position state is seeded for real (mps.save_state) against a
pytest tmp_path so the real automation/state/multi/exit-state.json is never touched.
"""
from __future__ import annotations

import datetime as dt
import types
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
import sys

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from multi import core                                   # noqa: E402
from multi.lib import creds as mc                        # noqa: E402
from multi.lib import exits as mex                        # noqa: E402
from multi.lib import position_state as mps               # noqa: E402
from multi.lib import tickers_execute_support as tes      # noqa: E402

ET = ZoneInfo("America/New_York")

FAKE_CREDS = mc.MultiCreds(key="k", secret="s", base_url="https://paper-api.alpaca.markets",
                           account_number="TESTACCT", source="test")


def _et(y: int, m: int, d: int, hh: int, mm: int) -> dt.datetime:
    return dt.datetime(y, m, d, hh, mm, tzinfo=ET)


def _tickers_params() -> dict:
    """Mirrors automation/state/tickers/params.json's mode/exits/flatten_schedule_et/risk
    blocks (intraday_v1) -- the shape evaluate_exit actually requires. A fresh dict every
    call; tests that need a variant mutate the returned dict directly."""
    return {
        "mode": {"name": "intraday_v1", "time_stop_et": "15:50"},
        "exits": {
            "tp1_premium_pct": 45.0,
            "tp1_qty_fraction": 0.5,
            "runner_target_mult": 1.75,
            "trail_pct": 20.0,
            "profit_lock_arm_pct": 15.0,
            "catastrophe_stop_pct": -50.0,
            "theta_budget": {
                "fires_before_catastrophe_cap": True,
                "max_premium_bleed_pct_without_progress": 30.0,
                "thesis_progress_definition":
                    "underlying has moved >= 0.5 * ATR(14) in the trade's direction from entry",
            },
        },
        "flatten_schedule_et": {
            "soft_time_stop": "14:45", "hard_backstop": "14:50", "last_resort_dne_sweep": "14:55",
        },
        "risk": {"weekend_holds": False},
    }


def _record(**overrides) -> mps.PositionRecord:
    fields = dict(
        symbol="NVDA", contract="NVDA260910C00500000", side="C",
        entry_premium=1.00, entry_underlying_price=500.0, qty=3,
        entry_session_date="2026-09-04", expiry="2026-09-10",
        hwm_premium=1.00, tp1_filled=False, strategy="test",
    )
    fields.update(overrides)
    return mps.PositionRecord(**fields)


def _flat_bars(close: float = 500.0, n: int = 20) -> pd.DataFrame:
    """OHLC frame with a constant $2 high-low range and a flat close -- yields a small,
    predictable ATR14 (~2.0) without depending on the exact EWM formula."""
    idx = pd.date_range("2026-08-01", periods=n, freq="1D", tz="America/New_York")
    return pd.DataFrame({
        "open": [close] * n, "high": [close + 1.0] * n, "low": [close - 1.0] * n,
        "close": [close] * n, "volume": [1_000_000.0] * n,
    }, index=idx)


def _seed_state(tmp_path: Path, contract: str, rec: mps.PositionRecord) -> Path:
    state_path = tmp_path / "exit-state.json"
    mps.ensure_initialized(path=state_path)
    mps.save_state({contract: rec}, path=state_path)
    return state_path


def _stub_quote(monkeypatch, *, bid: float, ask: float) -> None:
    monkeypatch.setattr(core, "fetch_option_quote_checked",
                        lambda creds, occ: ({"bid": bid, "ask": ask, "open_interest": None,
                                             "volume": 500}, None))


# =============================================================================================
# BUG 1 -- broker truth for open qty, never the original entry qty
# =============================================================================================

def test_tp1_then_sell_all_uses_broker_qty_not_record_qty(tmp_path, monkeypatch):
    """record qty 3, broker open_opts says 2 (TP1 already sold 1) -> the SELL_ALL row's
    qty_to_close == 2, open_qty == 2, open_qty_source == 'broker'. Premiums are driven deep
    into catastrophe/theta territory so SOME SELL_ALL stage fires deterministically -- every
    SELL_ALL stage in exits.py sets qty=open_qty, so this is robust to exactly which one wins.
    """
    contract = "NVDA260910C00500000"
    rec = _record(contract=contract, qty=3, entry_premium=1.00, hwm_premium=1.00)
    state_path = _seed_state(tmp_path, contract, rec)

    monkeypatch.setattr(core, "now_et", lambda: _et(2026, 9, 4, 10, 0))
    _stub_quote(monkeypatch, bid=0.05, ask=0.06)  # 94-95% bled from entry -- deep in the red
    monkeypatch.setattr(core, "fetch_underlying_last", lambda creds, symbol: 500.0)  # no move

    open_opts = [{"symbol": contract, "qty": "2"}]
    rows = core.manage_open_positions(_tickers_params(), FAKE_CREDS, open_opts,
                                      {"NVDA": _flat_bars()}, state_path=state_path)

    assert len(rows) == 1, rows
    row = rows[0]
    assert row["decision"] == "SELL_ALL", row
    assert row["qty_to_close"] == 2, row
    assert row["open_qty"] == 2, row
    assert row["open_qty_source"] == "broker", row


def test_broker_flat_produces_stale_state_and_never_calls_evaluate_exit(tmp_path, monkeypatch):
    """broker holds NOTHING for a state contract -> STALE_STATE row, gate=broker_flat,
    open_qty=0, open_qty_source='broker'. Neither evaluate_exit NOR a quote fetch may happen --
    both are monkeypatched to raise if called, proving the short-circuit is real."""
    contract = "NVDA260910C00500000"
    rec = _record(contract=contract, qty=3)
    state_path = _seed_state(tmp_path, contract, rec)

    monkeypatch.setattr(core, "now_et", lambda: _et(2026, 9, 4, 10, 0))

    def _boom_evaluate(*a, **kw):
        raise AssertionError("evaluate_exit must not be called for a broker-flat contract")

    def _boom_quote(*a, **kw):
        raise AssertionError("fetch_option_quote_checked must not be called for a "
                             "broker-flat contract")

    monkeypatch.setattr(core.mex, "evaluate_exit", _boom_evaluate)
    monkeypatch.setattr(core, "fetch_option_quote_checked", _boom_quote)

    rows = core.manage_open_positions(_tickers_params(), FAKE_CREDS, [],  # broker: nothing open
                                      {}, state_path=state_path)

    assert len(rows) == 1, rows
    row = rows[0]
    assert row["decision"] == "STALE_STATE", row
    assert row["gate"] == "broker_flat", row
    assert row["open_qty"] == 0, row
    assert row["open_qty_source"] == "broker", row


def test_open_opts_none_falls_back_to_record_qty(tmp_path, monkeypatch):
    """open_opts=None (the caller could not read positions at all this tick) -> open_qty ==
    rec.qty, open_qty_source == 'record_fallback', and exit evaluation still happens (HOLD on
    a position with no exit condition met)."""
    contract = "NVDA260910C00500000"
    rec = _record(contract=contract, qty=3, entry_premium=1.00, hwm_premium=1.00)
    state_path = _seed_state(tmp_path, contract, rec)

    monkeypatch.setattr(core, "now_et", lambda: _et(2026, 9, 4, 10, 0))
    _stub_quote(monkeypatch, bid=1.00, ask=1.00)  # unchanged premium -- no theta/TP1/cat fires
    monkeypatch.setattr(core, "fetch_underlying_last", lambda creds, symbol: 500.0)

    rows = core.manage_open_positions(_tickers_params(), FAKE_CREDS, None,  # positions unreadable
                                      {"NVDA": _flat_bars()}, state_path=state_path)

    assert len(rows) == 1, rows
    row = rows[0]
    assert row["open_qty"] == 3, row
    assert row["open_qty_source"] == "record_fallback", row
    assert row["decision"] == "HOLD", row


# =============================================================================================
# BUG 2 -- live underlying first, disclosed-stale daily close only as a fallback
# =============================================================================================

def test_theta_uses_live_underlying_and_holds_when_it_shows_progress(tmp_path, monkeypatch):
    """Premium has bled 40% (>= the 30% theta threshold), which alone would fire THETA_STOP --
    but a LIVE underlying read showing a clear favorable move (entry 500 -> live 520, comfortably
    past 0.5*ATR14~1.0) proves thesis progress, so the decision must be HOLD, not THETA_STOP.
    underlying_source must disclose 'live'."""
    contract = "NVDA260910C00500000"
    rec = _record(contract=contract, side="C", qty=3, entry_premium=1.00,
                  entry_underlying_price=500.0, hwm_premium=1.00, tp1_filled=False)
    state_path = _seed_state(tmp_path, contract, rec)

    monkeypatch.setattr(core, "now_et", lambda: _et(2026, 9, 4, 11, 0))  # well before any cutoff
    _stub_quote(monkeypatch, bid=0.60, ask=0.65)  # 40% bled from entry 1.00; below tp1_target 1.45
    monkeypatch.setattr(core, "fetch_underlying_last", lambda creds, symbol: 520.0)

    open_opts = [{"symbol": contract, "qty": "3"}]
    rows = core.manage_open_positions(_tickers_params(), FAKE_CREDS, open_opts,
                                      {"NVDA": _flat_bars()}, state_path=state_path)

    assert len(rows) == 1, rows
    row = rows[0]
    assert row["underlying_source"] == "live", row
    assert row["underlying_price"] == pytest.approx(520.0), row
    assert row["decision"] == "HOLD", row
    assert row["stage"] != mex.STAGE_THETA_BUDGET, row


def test_theta_falls_back_to_daily_close_and_still_evaluates(tmp_path, monkeypatch):
    """SAME position/quote as the test above (40% bled), but the live read now FAILS (returns
    None) -- the fallback daily close is UNCHANGED from entry (500.0), which shows NO thesis
    progress. This is BUG 2's exact real-world consequence: with the stale close, THETA_STOP
    fires where the live read would have shown HOLD. underlying_source must disclose
    'daily_close_stale', and evaluation still happens -- it is not skipped."""
    contract = "NVDA260910C00500000"
    rec = _record(contract=contract, side="C", qty=3, entry_premium=1.00,
                  entry_underlying_price=500.0, hwm_premium=1.00, tp1_filled=False)
    state_path = _seed_state(tmp_path, contract, rec)

    monkeypatch.setattr(core, "now_et", lambda: _et(2026, 9, 4, 11, 0))
    _stub_quote(monkeypatch, bid=0.60, ask=0.65)
    monkeypatch.setattr(core, "fetch_underlying_last", lambda creds, symbol: None)  # live read failed

    open_opts = [{"symbol": contract, "qty": "3"}]
    rows = core.manage_open_positions(_tickers_params(), FAKE_CREDS, open_opts,
                                      {"NVDA": _flat_bars(close=500.0)}, state_path=state_path)

    assert len(rows) == 1, rows
    row = rows[0]
    assert row["underlying_source"] == "daily_close_stale", row
    assert row["underlying_price"] == pytest.approx(500.0), row
    assert row["decision"] == "SELL_ALL", row
    assert row["stage"] == mex.STAGE_THETA_BUDGET, row


def test_stale_state_row_carries_none_underlying_facts_not_missing_keys(tmp_path, monkeypatch):
    """A STALE_STATE row never fetched a quote or an underlying price (BUG 1's short-circuit),
    but the row contract still promises the keys exist (value None), never absent -- so a
    ledger reader can rely on row.get('underlying_source') without a KeyError either way."""
    contract = "NVDA260910C00500000"
    rec = _record(contract=contract, qty=3)
    state_path = _seed_state(tmp_path, contract, rec)
    monkeypatch.setattr(core, "now_et", lambda: _et(2026, 9, 4, 10, 0))

    rows = core.manage_open_positions(_tickers_params(), FAKE_CREDS, [], {}, state_path=state_path)

    row = rows[0]
    assert row["decision"] == "STALE_STATE"
    assert "underlying_price" in row and row["underlying_price"] is None
    assert "underlying_source" in row and row["underlying_source"] is None
    assert "atr14" in row and row["atr14"] is None


# =============================================================================================
# tickers_execute_support.re_derive_exit_record prefers the row's own persisted facts
# =============================================================================================

def test_re_derive_exit_record_prefers_row_open_qty_and_underlying_facts(monkeypatch):
    """When the row already carries open_qty/underlying_price/atr14 (the exact facts
    manage_open_positions evaluated this contract against), re_derive_exit_record must pass
    THOSE to evaluate_exit -- never rec.qty (BUG 1) and never a fresh bars_facts()
    recomputation (BUG 2). bars_facts is monkeypatched to raise if called, proving it is
    genuinely skipped, not merely un-asserted."""
    rec = _record(contract="NVDA260910C00500000", qty=3, entry_premium=1.00,
                  entry_underlying_price=500.0, hwm_premium=1.10)
    row = {"symbol": "NVDA", "open_qty": 2, "underlying_price": 550.0, "atr14": 3.0,
           "ask": 1.10, "bid": 1.05}

    captured: dict = {}

    def _fake_evaluate_exit(record, **kw):
        captured.update(kw)
        return types.SimpleNamespace(record=record)

    def _boom_bars_facts(*a, **kw):
        raise AssertionError("bars_facts must not be called when the row already carries "
                             "underlying_price/atr14")

    monkeypatch.setattr(tes.mex, "evaluate_exit", _fake_evaluate_exit)
    monkeypatch.setattr(tes, "bars_facts", _boom_bars_facts)

    tes.re_derive_exit_record(rec, row, None, {"exits": {}}, now_aware=_et(2026, 9, 4, 10, 0))

    assert captured["open_qty"] == 2, captured
    assert captured["underlying_price"] == 550.0, captured
    assert captured["atr14"] == 3.0, captured


def test_re_derive_exit_record_falls_back_when_row_lacks_facts(monkeypatch):
    """A row shaped like the OLD (pre-fix) contract -- no open_qty/underlying_price/atr14 --
    must still work: falls back to rec.qty and a fresh bars_facts() recomputation, exactly the
    pre-fix behavior. This pins backward compatibility with the existing execute.py test suite
    (test_tickers_execute_2026_09_04.py's _exit_row helper never sets these new keys)."""
    rec = _record(contract="NVDA260910C00500000", qty=3, entry_premium=1.00,
                  entry_underlying_price=500.0, hwm_premium=1.10)
    row = {"symbol": "NVDA", "ask": 1.10, "bid": 1.05}  # no open_qty / underlying_price / atr14

    captured: dict = {}

    def _fake_evaluate_exit(record, **kw):
        captured.update(kw)
        return types.SimpleNamespace(record=record)

    monkeypatch.setattr(tes.mex, "evaluate_exit", _fake_evaluate_exit)
    monkeypatch.setattr(tes, "bars_facts", lambda bars, symbol: (515.0, 2.5))

    tes.re_derive_exit_record(rec, row, {"NVDA": _flat_bars()}, {"exits": {}},
                              now_aware=_et(2026, 9, 4, 10, 0))

    assert captured["open_qty"] == 3, captured           # rec.qty fallback
    assert captured["underlying_price"] == 515.0, captured  # bars_facts fallback
    assert captured["atr14"] == 2.5, captured


# =============================================================================================
# BUG 3 -- entry.liquidity_gate.min_premium_dollars, optional, vary-and-assert
# =============================================================================================

def _premium_params(min_premium_dollars=None) -> dict:
    gate = {"max_spread_pct_of_premium": 8.0}
    if min_premium_dollars is not None:
        gate["min_premium_dollars"] = min_premium_dollars
    return {"entry": {"liquidity_gate": gate}}


@pytest.mark.parametrize("floor,expect_ok", [
    (None, True),   # absent -> no check -> the existing multi-1 shadow lane is unaffected
    (0.50, False),  # mid 0.30 < 0.50 -> blocked
    (0.10, True),   # mid 0.30 >= 0.10 -> passes
])
def test_min_premium_dollars_vary_and_assert(floor, expect_ok):
    quote = {"bid": 0.29, "ask": 0.31, "open_interest": None, "volume": 500}  # mid = 0.30
    ok, why, facts = core.liquidity_ok(quote, _premium_params(floor))
    assert ok is expect_ok, why
    assert facts["mid"] == pytest.approx(0.30)
    if not expect_ok:
        assert "min_premium_dollars" in why, why


def test_min_premium_dollars_absent_is_byte_identical_to_before():
    """A params dict with NO min_premium_dollars key at all (the real, pre-2026-09-04
    multi-1 shadow lane shape) must never block on premium, however low the mid is."""
    quote = {"bid": 0.01, "ask": 0.01, "open_interest": None, "volume": 500}  # mid = 0.01
    ok, why, _ = core.liquidity_ok(quote, {"entry": {"liquidity_gate": {}}})
    assert ok is True, why

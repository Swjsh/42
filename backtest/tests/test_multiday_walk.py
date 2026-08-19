"""Guards for backtest/lib/multiday_walk.py + weekly_fill_model.py.

The headline guard is `test_session_touching_both_target_and_stop_resolves_adversely`. Daily
bars cannot tell you whether a session's high or its low came first. Assuming the favorable
one is the single most effective way to manufacture fake edge in a multi-day options backtest,
and this shop's own doctrine flags exactly that class (the known zero-slippage optimism in the
SPY exit walk). The walker must resolve such sessions against itself, always.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest" / "lib"))

import multiday_walk as mw  # noqa: E402
import weekly_fill_model as wfm  # noqa: E402

PARAMS = json.loads((REPO / "automation" / "state" / "weekly" / "params.json").read_text(encoding="utf-8"))
SHAPE = PARAMS["exits"]


def _bar(d: str, o, h, l, c, *, expiry=False, vol=1000.0) -> mw.SessionBar:
    return mw.SessionBar(
        date_et=dt.date.fromisoformat(d), open=o, high=h, low=l, close=c,
        volume=vol, is_expiry_day=expiry,
    )


def _pos(entry="2026-06-01", mid=1.00, expiry="2026-06-05") -> mw.MultiDayPosition:
    return mw.MultiDayPosition(
        contract="QQQ260605C00700000", symbol="QQQ", side="C",
        entry_date=dt.date.fromisoformat(entry), entry_mid=mid, qty=3,
        expiry=dt.date.fromisoformat(expiry), zone_width=2.0, entry_underlying=700.0,
    )


# --- fill model ------------------------------------------------------------------------

def test_buy_pays_up_and_sell_receives_down():
    b = wfm.buy_fill(1.00, 0.05)
    s = wfm.sell_fill(1.00, 0.05)
    assert b.price > 1.00 and s.price < 1.00
    assert b.price == pytest.approx(1.025) and s.price == pytest.approx(0.975)
    # A round trip at an unchanged mid must LOSE the spread — never break even.
    assert s.price < b.price


def test_fill_model_rejects_percent_given_as_whole_number():
    """5 means 500%, not 5% — a silent misread would erase the modeled cost entirely."""
    with pytest.raises(wfm.FillModelError):
        wfm.buy_fill(1.00, 5)
    with pytest.raises(wfm.FillModelError):
        wfm.buy_fill(0.0, 0.05)


def test_sell_fill_floors_at_zero():
    assert wfm.sell_fill(0.01, 1.9).price >= 0.0


# --- the anti-optimism guard -----------------------------------------------------------

def test_session_touching_both_target_and_stop_resolves_adversely():
    """A session whose HIGH clears TP1 and whose LOW breaches the stop must NOT book the win.

    entry mid 1.00 -> fill 1.025. TP1 +45% ~= 1.49; catastrophe -50% ~= 0.51.
    The session below touches 1.60 AND 0.30, so both are reachable. With daily bars the order
    is unknowable; the walker must take the adverse one.
    """
    bars = [
        _bar("2026-06-01", 1.00, 1.05, 0.95, 1.00),          # entry session
        _bar("2026-06-02", 1.00, 1.60, 0.30, 0.40),          # touches BOTH
    ]
    r = mw.walk(_pos(), bars, SHAPE, params=PARAMS)

    assert r.exit_date == dt.date(2026, 6, 2)
    assert r.adverse_resolution_sessions == 1, (
        "the ambiguous session was not flagged as adversely resolved"
    )
    assert r.return_pct < 0, (
        f"walker booked a POSITIVE return ({r.return_pct:.1f}%) on a session that also "
        f"breached the stop — this is the manufactured-edge failure mode"
    )
    assert r.exit_fill < 1.0, f"exit filled at {r.exit_fill}, i.e. off the high, not the low"


def test_favorable_only_session_is_allowed_to_win():
    """The adverse rule must not be a blanket pessimism that hides real winners."""
    bars = [
        _bar("2026-06-01", 1.00, 1.05, 0.95, 1.00),
        _bar("2026-06-02", 1.50, 1.90, 1.45, 1.85),   # never near the stop
    ]
    r = mw.walk(_pos(), bars, SHAPE, params=PARAMS)
    assert r.adverse_resolution_sessions == 0
    assert r.return_pct > 0, f"a clean winning session returned {r.return_pct}"


# --- overnight gap + expiry-day handling ------------------------------------------------

def test_gap_through_stop_fills_at_open_not_at_the_stop_price():
    """The chart stop is INERT overnight — a gap fills at the open, never at the stop."""
    bars = [
        _bar("2026-06-01", 1.00, 1.05, 0.95, 1.00),
        _bar("2026-06-02", 0.20, 0.25, 0.18, 0.20),   # gapped far below the ~0.51 stop
    ]
    r = mw.walk(_pos(), bars, SHAPE, params=PARAMS)
    assert r.gapped_through_sessions == 1, "overnight gap through the stop was not detected"
    # Fill must reflect the 0.20 open (minus half-spread), NOT the 0.51 stop price.
    assert r.exit_fill == pytest.approx(wfm.sell_fill(0.20, r.spread_pct_assumed).price)
    assert r.exit_fill < 0.51


def test_expiry_day_exit_uses_open_not_the_pathological_low():
    """Observed live: an ATM contract printed low=0.07 on 381k volume closing at 3.20."""
    bars = [
        _bar("2026-06-01", 1.00, 1.05, 0.95, 1.00),
        _bar("2026-06-05", 0.90, 1.00, 0.07, 0.80, expiry=True),
    ]
    r = mw.walk(_pos(), bars, SHAPE, params=PARAMS)
    assert r.exited_on_expiry_day is True
    assert r.exit_fill == pytest.approx(wfm.sell_fill(0.90, r.spread_pct_assumed).price), (
        "expiry-day exit used the pathological low instead of the open"
    )


# --- fail-loud contracts ----------------------------------------------------------------

def test_missing_entry_session_bar_raises_rather_than_shifting_entry():
    bars = [_bar("2026-06-03", 1.0, 1.1, 0.9, 1.0)]
    with pytest.raises(mw.WalkError, match="no bar for the entry session"):
        mw.walk(_pos(entry="2026-06-01"), bars, SHAPE, params=PARAMS)


def test_missing_cache_file_raises():
    with pytest.raises(mw.WalkError, match="no cached bars"):
        mw.load_contract_bars("NOPE260101C00001000", "NOPE")


def test_walk_many_reports_failures_instead_of_dropping_them():
    bad = mw.MultiDayPosition(
        contract="NOPE260101C00001000", symbol="NOPE", side="C",
        entry_date=dt.date(2026, 6, 1), entry_mid=1.0, qty=3,
        expiry=dt.date(2026, 6, 5), zone_width=2.0, entry_underlying=700.0,
    )
    results, failures = mw.walk_many([bad], SHAPE, params=PARAMS)
    assert results == [] and len(failures) == 1
    assert "NOPE" in failures[0]


def test_result_row_always_carries_its_disclosures():
    """A number without its modeling caveats is how modeled results get read as measured."""
    bars = [
        _bar("2026-06-01", 1.00, 1.05, 0.95, 1.00),
        _bar("2026-06-02", 1.50, 1.90, 1.45, 1.85),
    ]
    row = mw.walk(_pos(), bars, SHAPE, params=PARAMS).as_row()
    for k in ("spread_pct_assumed", "intraday_path_unknown",
              "adverse_resolution_sessions", "gapped_through_sessions", "exited_on_expiry_day"):
        assert k in row, f"disclosure field {k} missing from the result row"
    assert row["intraday_path_unknown"] is True

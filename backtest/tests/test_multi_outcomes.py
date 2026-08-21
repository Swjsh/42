"""Guards for multi/outcomes.py -- the surface that turns evaluation cards into evidence.

The failure modes here are subtle and all point the same way: an outcome ledger that is WRONG is
far worse than one that is missing, because it will be believed. So the guards are about
(1) never reading a window that has not closed, (2) never counting a non-directional card as a
win, and (3) never reporting a cut without its n.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from multi import outcomes as oc  # noqa: E402

ET = "America/New_York"


def _bars(start="2026-08-21 09:30", n=60, base=100.0, drift=0.0):
    idx = pd.date_range(start, periods=n, freq="5min", tz=ET)
    closes = [base * (1.0 + drift * i) for i in range(n)]
    return pd.DataFrame({"open": closes, "high": closes, "low": closes,
                         "close": closes, "volume": [1e6] * n}, index=idx)


def _card(ts, symbol="TEST", spot=100.0, bull=9, bear=4, bull_blockers=None):
    return {
        "symbol": symbol, "as_of_et": ts, "spot": spot, "verdict": "WATCH",
        "setup": {"status": "OK", "bull": {"score": bull, "blockers": bull_blockers or []},
                  "bear": {"score": bear, "blockers": []}},
        "structure": {"status": "OK", "trend": "uptrend"},
        "zones": {"status": "OK", "nearest": {"distance_atr": 0.5, "is_shelf": True}},
    }


# --- 1. never read a window that has not closed ---------------------------------------------

def test_an_unsettled_card_is_not_stamped():
    """THE guard. Stamping a card younger than its longest horizon reads an OPEN window and
    manufactures an outcome that has not happened yet."""
    now = pd.Timestamp("2026-08-21 10:40", tz=ET).to_pydatetime()
    card = _card("2026-08-21T10:30:00-04:00")          # 10 minutes old, needs 65
    assert oc.stamp([card], {"TEST": _bars()}, now) == []


def test_a_settled_card_is_stamped():
    """The complement -- proving the stamper actually stamps, not merely that it refuses."""
    now = pd.Timestamp("2026-08-21 12:00", tz=ET).to_pydatetime()
    card = _card("2026-08-21T09:35:00-04:00")
    out = oc.stamp([card], {"TEST": _bars(n=60, base=100.0, drift=0.001)}, now)
    assert len(out) == 1, "a fully-settled card must be stamped"
    r = out[0]
    assert r["fwd_10m_pct"] is not None and r["fwd_30m_pct"] is not None
    assert r["lean"] == "bull"
    assert r["signed_30m_pct"] == pytest.approx(r["fwd_30m_pct"])   # bull: signed == raw


def test_bear_lean_flips_the_sign_so_positive_always_means_the_read_was_right():
    now = pd.Timestamp("2026-08-21 12:00", tz=ET).to_pydatetime()
    card = _card("2026-08-21T09:35:00-04:00", bull=3, bear=9)
    out = oc.stamp([card], {"TEST": _bars(n=60, drift=0.001)}, now)   # price RISES
    r = out[0]
    assert r["lean"] == "bear"
    assert r["fwd_30m_pct"] > 0, "price rose"
    assert r["signed_30m_pct"] < 0, "a bear read into a rising tape must score NEGATIVE"


# --- 2. a card with no directional lean must not be counted as a win ------------------------

def test_a_tied_card_has_no_lean_and_no_signed_return():
    now = pd.Timestamp("2026-08-21 12:00", tz=ET).to_pydatetime()
    card = _card("2026-08-21T09:35:00-04:00", bull=6, bear=6)
    r = oc.stamp([card], {"TEST": _bars(n=60, drift=0.001)}, now)[0]
    assert r["lean"] is None
    assert r["signed_30m_pct"] is None, "a no-lean card must not contribute a directional result"


def test_report_excludes_no_lean_rows_from_directional_stats():
    rows = [
        {"symbol": "A", "lean": None, "signed_30m_pct": None, "bull_score": 6, "bear_score": 6},
        {"symbol": "A", "lean": "bull", "signed_30m_pct": 0.5, "bull_score": 9, "bear_score": 2,
         "bull_blockers": ["F5:ribbon_stack"], "bear_blockers": []},
    ]
    rep = oc.report(rows)
    assert rep["rows_total"] == 2
    assert rep["rows_with_directional_lean"] == 1
    assert rep["overall"]["30m"]["n"] == 1


# --- 3. every cut carries its n -------------------------------------------------------------

def test_every_reported_cut_carries_an_n():
    """A hit rate without an n invites acting on a sample of three."""
    rows = [{"symbol": "A", "lean": "bull", "signed_30m_pct": 0.5, "bull_score": 9,
             "bear_score": 2, "bull_blockers": ["F10:level_tied_trigger"], "bear_blockers": [],
             "nearest_is_shelf": True}]
    rep = oc.report(rows)
    for section in ("by_symbol_30m", "by_lean_score_30m", "by_blocker_30m"):
        for cut, stats in rep[section].items():
            assert "n" in stats, f"{section}[{cut}] reported without an n"
    assert rep["shelf_vs_not_30m"]["nearest_is_shelf"]["n"] == 1
    assert rep["shelf_vs_not_30m"]["not_a_shelf"]["n"] == 0


def test_empty_history_reports_zero_rather_than_crashing_or_implying_a_result():
    rep = oc.report([])
    assert rep["rows_total"] == 0
    assert rep["overall"]["30m"]["n"] == 0
    assert "OBSERVATIONS" in rep["_reading"]


# --- 4. append-only: history is never rewritten ---------------------------------------------

def test_outcomes_module_never_opens_the_card_history_for_writing():
    """Card history is the immutable record. Outcomes go to a SEPARATE file, so a stamping bug
    can never corrupt the observations themselves."""
    src = (REPO / "multi" / "outcomes.py").read_text(encoding="utf-8")
    assert 'HISTORY.open("a"' not in src and 'HISTORY.open("w"' not in src
    assert 'OUTCOMES.open("a"' in src, "outcomes must be APPENDED, never rewritten"

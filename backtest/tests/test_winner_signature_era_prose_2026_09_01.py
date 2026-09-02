"""Guard for the winner_signature.py era-honesty paragraph (W4, 2026-09-01).

`analysis/winner-autopsies/SIGNATURE.md` hardcoded "the post-ladder era is still red" / "did
NOT make the book positive" in its era-split prose while the era table directly above it was
free to compute a positive post-ladder net -- a generated surface that could end up arguing
with its own table. This pins two things:

  1. `_post_ladder_prose()` must be sign-matched to the ACTUAL computed net it is handed --
     positive net gets "DID make the book positive" language, non-positive net keeps the
     "did NOT" / "still red" language. Never a hardcoded claim independent of the input.
  2. `_ex_best_n_days_net()` (the source of the era table's new "ex-best-2-days net" column)
     must actually subtract the N highest-P&L SESSIONS (grouped by date), not the N
     highest-P&L trades -- concentration is a per-day phenomenon, and collapsing by trade
     would silently overstate how many days are propping up the era.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "setup" / "scripts",):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import winner_signature as ws  # noqa: E402


def _rec(date, pnl):
    return {"date": date, "pnl": pnl}


def test_post_ladder_prose_matches_positive_net():
    post = {"net": 2883.0, "ex_best2_net": -154.0}
    text = ws._post_ladder_prose(post)
    assert "DID make the book positive" in text
    assert "still red" not in text
    assert "did NOT make the book positive" not in text
    assert "+$2,883" in text
    assert "$-154" in text


def test_post_ladder_prose_matches_negative_net():
    post = {"net": -1200.0, "ex_best2_net": -1400.0}
    text = ws._post_ladder_prose(post)
    assert "did NOT make the book positive" in text
    assert "DID make the book positive" not in text
    assert "$-1,200" in text


def test_post_ladder_prose_handles_missing_era():
    text = ws._post_ladder_prose(None)
    assert "No post-ladder fills exist yet" in text


def test_ex_best_n_days_net_groups_by_session_not_by_trade():
    # Day A: two small trades summing to $100 (the era's biggest SESSION).
    # Day B: one trade at $60 (would look like the single biggest TRADE if not grouped).
    # Day C: -$20.
    sel = [
        _rec("2026-08-11", 40.0),
        _rec("2026-08-11", 60.0),
        _rec("2026-08-12", 60.0),
        _rec("2026-08-13", -20.0),
    ]
    # Excluding the best 1 day must remove day A's combined $100, not just the $60 trade.
    ex1 = ws._ex_best_n_days_net(sel, n=1)
    assert ex1 == 60.0 + -20.0, f"expected day-grouped exclusion, got ex1={ex1}"


def test_ex_best_n_days_net_matches_r10_measurement():
    """R10 measured the post-08-11 era at -$154 ex its two best days -- sanity-check shape."""
    sel = [
        _rec("2026-08-11", 1500.0),
        _rec("2026-08-12", 1537.0),
        _rec("2026-08-13", -154.0),
    ]
    assert ws._ex_best_n_days_net(sel, n=2) == -154.0

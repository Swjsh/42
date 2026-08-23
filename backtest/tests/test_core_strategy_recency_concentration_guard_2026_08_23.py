"""test_core_strategy_recency_concentration_guard_2026_08_23.py -- OP-25 guard for the
naive-mean-only defect in core_strategy_recency.py::direction_verdict, the THIRD confirmed
instance of the same defect class this weekend (after gate_expiry_check.py's costing_verdict,
commit 71c39545, guarded by test_gate_expiry_naive_red_guard_2026_08_23.py).

Measured on real fills (2026-07-20..08-21, core safe+bold, RIDE_THE_RIBBON, n=31/side): the
old naive check (n>=floor AND sign(exp_per_trade) alone) stamped BULL a clean GREEN at
+$2.45/tr when the ENTIRE +$76 net was TWO DAYS (2026-08-04 +$1,141 and 2026-08-13 +$962 =
+$2,103, i.e. 2,767% of net -- the label dies on dropping either one), while BEAR read a
clean RED at -$16.71/tr for an evenly-spread bleed with a HIGHER win rate (35.5% vs 25.8%).
At drop-top3 the two were statistically indistinguishable (-$55.36 vs -$51.96, gap $3.40;
day-block bootstrap B=20,000 gives P(gap<=0)=0.410) yet read as opposite, confident labels --
a full multi-agent investigation chased a bear-side mechanism that does not exist.

Per OP-25 (same mistake twice = system failure, encode the correction as a guard, not a
memory), this file pins the fix, mirroring test_gate_expiry_naive_red_guard_2026_08_23.py's
structure and naming:
  (a) a cohort whose positive expectancy is carried by 2 DAYS (not merely a few trades) must
      NOT be labeled a clean GREEN -- must downgrade to GREEN_CONCENTRATED;
  (b) an evenly-spread negative cohort with a HIGHER win rate than (a)'s concentrated cohort
      must NOT get the same treatment -- it stays a plain, distinguishable RED;
  (c) a genuinely broad positive cohort (survives both drop-top3 and drop-best2-days) still
      reads a clean GREEN -- proves the fix doesn't neuter every GREEN;
  (d) the shared helper (backtest/lib/concentration.py) returns correct drop_top_n /
      drop_best_days / top_day_share values on a hand-computed fixture.

HOW THESE WERE PROVEN TO RED PRE-FIX (actually run this session, not asserted from memory):
  (a)-(c) exercise core_strategy_recency.py's cell_metrics + direction_verdict end to end.
  `git stash push -- backtest/autoresearch/core_strategy_recency.py` (reverting ONLY the
  source fix to its last-committed, pre-fix state -- this test file and
  backtest/lib/concentration.py stayed in place, untracked/unstashed), then
  `pytest backtest/tests/test_core_strategy_recency_concentration_guard_2026_08_23.py -v`
  reproduced the exact pre-fix failures (see session report for verbatim output), then
  `git stash pop` restored the fix immediately afterward.
  (d) exercises backtest/lib/concentration.py directly -- a module that did not exist before
  this fix, so its pre-fix RED is "ModuleNotFoundError: No module named 'lib.concentration'"
  (proven by running the test against a checkout where the file is absent).
"""
from __future__ import annotations

import pytest

from autoresearch import core_strategy_recency as csr
from lib import concentration as conc

FLOOR = 10


def _events(pnls_by_date: dict[str, list[float]]) -> list[dict]:
    """Build a cell_metrics-shaped events list from {date: [pnl, pnl, ...]}."""
    out = []
    for date, pnls in pnls_by_date.items():
        for p in pnls:
            out.append({"date": date, "pnl": p})
    return out


# ─────────────────────────────────────────────────────────────────────────────
# (a) a positive expectancy carried by 2 DAYS must NOT read a clean GREEN
# ─────────────────────────────────────────────────────────────────────────────

def test_two_day_carried_positive_cohort_is_not_a_clean_green():
    """Mirrors the real bull shape: 10 small losing trades on 10 distinct days (-$5 each,
    -$50 total) plus exactly 2 outsized winning DAYS (2026-08-04 +$1,141, 2026-08-13 +$962).
    n=12 >= floor=10, net +$2,053, exp +$171.08/tr -- a naive check calls this a bare
    actionable GREEN. Dropping either the top-3 winning TRADES or the best-2 DAYS removes
    the same $2,103 and flips the total to -$50.00 -- NEGATIVE. Must downgrade to
    GREEN_CONCENTRATED, never a bare GREEN."""
    events = _events({
        **{f"2026-07-{d:02d}": [-5.0] for d in range(1, 11)},  # 10 losing days, 1 trade each
        "2026-08-04": [1141.0],
        "2026-08-13": [962.0],
    })
    cell = csr.cell_metrics(events)
    assert cell["n"] == 12
    assert cell["exp_per_trade"] == pytest.approx(171.08, abs=0.01)
    assert cell["drop_top3"] == -50.0, "dropping the 2 winning trades must flip the sign"
    assert cell["drop_best2_days"] == -50.0, "dropping the 2 winning DAYS must flip the sign"

    verdict, reason = csr.direction_verdict(cell, floor=FLOOR)
    assert verdict == "GREEN_CONCENTRATED"
    assert verdict != "GREEN"
    assert "NOT ACTIONABLE" in reason
    assert "concentration-carried" in reason.lower()


# ─────────────────────────────────────────────────────────────────────────────
# (b) an evenly-spread negative cohort with a HIGHER win rate stays a plain, distinguishable
#     RED -- never gets the same concentration-carried treatment as (a)
# ─────────────────────────────────────────────────────────────────────────────

def test_evenly_spread_negative_cohort_is_distinguishable_from_concentrated_positive():
    """Mirrors the real bear shape: 5 winners @ +$30 and 7 losers @ -$40, EACH on its own
    day (n=12, 12 distinct days) -- net -$130, exp -$10.83/tr, WR 41.7%. This win rate is
    HIGHER than the concentrated cohort's WR (2 winners / 12 = 16.7%) in
    test_two_day_carried_positive_cohort_is_not_a_clean_green -- exactly the real-data shape
    (bear WR 35.5% > bull WR 25.8%) that made the naive RED/GREEN split misleading. Dropping
    the worst-3 losing trades or the worst-2 losing days still leaves the total negative --
    a genuinely broad bleed, not a couple of blowup days. Must stay a plain RED, and that RED
    must be a DIFFERENT label than (a)'s GREEN_CONCENTRATED (trivially distinguishable, but
    pinned explicitly here so a future change can't collapse the two)."""
    winners = {f"2026-07-{d:02d}": [30.0] for d in range(1, 6)}       # 5 winning days
    losers = {f"2026-07-{d:02d}": [-40.0] for d in range(11, 18)}     # 7 losing days
    events = _events({**winners, **losers})
    cell = csr.cell_metrics(events)

    assert cell["n"] == 12
    assert cell["exp_per_trade"] == pytest.approx(-10.83, abs=0.01)
    bear_wr = cell["wr_pct"]
    assert bear_wr == pytest.approx(41.7, abs=0.1)

    concentrated_events = _events({
        **{f"2026-06-{d:02d}": [-5.0] for d in range(1, 11)},
        "2026-08-04": [1141.0], "2026-08-13": [962.0],
    })
    concentrated_cell = csr.cell_metrics(concentrated_events)
    concentrated_wr = concentrated_cell["wr_pct"]
    assert bear_wr > concentrated_wr, (
        "the evenly-spread negative cohort's win rate must be HIGHER than the "
        "concentration-carried positive cohort's -- exactly the real-data shape this "
        "instrument misread"
    )

    assert cell["drop_bottom3"] == -10.0
    assert cell["drop_worst2_days"] == -50.0
    verdict, reason = csr.direction_verdict(cell, floor=FLOOR)
    assert verdict == "RED"
    assert verdict != "RED_CONCENTRATED"

    concentrated_verdict, _ = csr.direction_verdict(concentrated_cell, floor=FLOOR)
    assert concentrated_verdict == "GREEN_CONCENTRATED"
    assert verdict != concentrated_verdict, (
        "a broad negative cohort and a concentration-carried positive cohort must read as "
        "DIFFERENT, distinguishable verdicts"
    )


# ─────────────────────────────────────────────────────────────────────────────
# (c) a genuinely broad positive cohort still reads a clean GREEN
# ─────────────────────────────────────────────────────────────────────────────

def test_broad_positive_cohort_still_reads_clean_green():
    """8 winners @ +$50 and 4 losers @ -$30, each on its own day (n=12, 12 distinct days) --
    net +$280, exp +$23.33/tr. Dropping the top-3 winning trades leaves +$130 (still
    positive); dropping the best-2 winning days leaves +$180 (still positive). A genuinely
    broad edge, not concentration-carried -- must still read a clean GREEN, proving the fix
    doesn't neuter every positive verdict."""
    winners = {f"2026-07-{d:02d}": [50.0] for d in range(1, 9)}   # 8 winning days
    losers = {f"2026-07-{d:02d}": [-30.0] for d in range(11, 15)}  # 4 losing days
    events = _events({**winners, **losers})
    cell = csr.cell_metrics(events)

    assert cell["n"] == 12
    assert cell["exp_per_trade"] == pytest.approx(23.33, abs=0.01)
    assert cell["drop_top3"] == 130.0
    assert cell["drop_best2_days"] == 180.0

    verdict, reason = csr.direction_verdict(cell, floor=FLOOR)
    assert verdict == "GREEN"
    assert "survives" in reason.lower()


# ─────────────────────────────────────────────────────────────────────────────
# (d) shared helper (backtest/lib/concentration.py) correctness on a hand-computed fixture
# ─────────────────────────────────────────────────────────────────────────────

_FIXTURE = [
    ("2026-08-01", 100.0),
    ("2026-08-01", -20.0),   # same day as above -- daily total 2026-08-01 = 80.0
    ("2026-08-02", 50.0),
    ("2026-08-03", -10.0),
]
# total = 100 - 20 + 50 - 10 = 120.0
# daily totals: 2026-08-01 = 80.0, 2026-08-02 = 50.0, 2026-08-03 = -10.0


def test_concentration_helper_drop_top_n_hand_computed():
    value, n_dropped = conc.drop_top_n(_FIXTURE, 1)
    assert (value, n_dropped) == (20.0, 1), "120 - 100 (the single largest winning trade)"
    value3, n3 = conc.drop_top_n(_FIXTURE, 3)
    assert (value3, n3) == (-30.0, 2), "only 2 winners exist (100, 50); 120 - 150 = -30"


def test_concentration_helper_drop_bottom_n_hand_computed():
    value, n_dropped = conc.drop_bottom_n(_FIXTURE, 1)
    assert (value, n_dropped) == (140.0, 1), "120 - (-20) (the single largest losing trade)"


def test_concentration_helper_drop_best_days_hand_computed():
    value1, n1, dates1 = conc.drop_best_days(_FIXTURE, 1)
    assert (value1, n1, dates1) == (40.0, 1, ["2026-08-01"]), "120 - 80 (best day)"
    value2, n2, dates2 = conc.drop_best_days(_FIXTURE, 2)
    assert (value2, n2, dates2) == (-10.0, 2, ["2026-08-01", "2026-08-02"]), (
        "120 - (80 + 50) -- both positive days dropped, sign flips"
    )


def test_concentration_helper_drop_worst_days_hand_computed():
    value, n_dropped, dates = conc.drop_worst_days(_FIXTURE, 1)
    assert (value, n_dropped, dates) == (130.0, 1, ["2026-08-03"]), "120 - (-10) (worst day)"


def test_concentration_helper_top_day_share_hand_computed():
    share = conc.top_day_share(_FIXTURE)
    assert share["total"] == 120.0
    assert share["best_day"] == "2026-08-01"
    assert share["best_day_pnl"] == 80.0
    assert share["best_day_share_pct"] == pytest.approx(66.7, abs=0.05)
    assert share["worst_day"] == "2026-08-03"
    assert share["worst_day_pnl"] == -10.0
    assert share["worst_day_share_pct"] == pytest.approx(-8.3, abs=0.05)


def test_concentration_helper_empty_input_is_safe():
    """Every helper must fail safe on an empty cohort, never raise (OP-25 fail-open)."""
    assert conc.drop_top_n([], 3) == (0.0, 0)
    assert conc.drop_bottom_n([], 3) == (0.0, 0)
    assert conc.drop_best_days([], 2) == (0.0, 0, [])
    assert conc.drop_worst_days([], 2) == (0.0, 0, [])
    empty_share = conc.top_day_share([])
    assert empty_share["total"] == 0.0
    assert empty_share["best_day"] is None

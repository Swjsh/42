"""Guard for backtest/tools/day_report_card.py -- THE DAY REPORT CARD (bounded v1,
90 trading days), the approved-but-never-built per-day diagnostic (J 2026-07-27 night:
"figure out what we need to replay to make money").

Load-bearing invariants this guard pins:

  1. TAXONOMY ENUM (fixed, closed set): the classifier may ONLY ever emit one of the seven
     approved causes -- GREEN / CORRECTLY_FLAT / NO_VOCABULARY / GATE_BLOCKED /
     EXIT_LEFT_MONEY / EXIT_TOO_LATE / SHOULD_NOT_HAVE_TRADED. A new cause string silently
     appearing (typo, "GREEN ", an eighth category) breaks every downstream consumer of the
     cause histogram, so the enum is pinned here both as a set-equality check AND as a
     property sweep over a full input grid.
  2. DETERMINISM: classify_day / modal_blocker_of / aggregate_cards are PURE functions --
     same inputs => byte-identical outputs, no clock, no RNG, no I/O. Pinned by running the
     full grid twice and comparing serialized output, and by a fixed-fixture aggregate hash.
  3. DECISION-TREE BRANCH PINS: one pinned case per branch of the pre-registered decision
     tree (thresholds FOCUS_DAILY_FLOOR=$100 / MFE_WINNER_PCT=+30% are doctrine constants --
     markdown/doctrine/FOCUS-DOCTRINE.md and params tp1 +30% -- NOT tuned knobs; a silent
     threshold edit flips these pins RED).
  4. AGGREGATOR REJECTS UNKNOWN CAUSES: aggregate_cards must raise on a card whose cause is
     outside the enum (fail-loud, never silently bucket garbage).

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_day_report_card.py -q
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "backtest" / "tools"
for _p in (str(REPO), str(REPO / "backtest"), str(TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import day_report_card as drc  # noqa: E402

EXPECTED_CAUSES = frozenset({
    "GREEN", "CORRECTLY_FLAT", "NO_VOCABULARY", "GATE_BLOCKED",
    "EXIT_LEFT_MONEY", "EXIT_TOO_LATE", "SHOULD_NOT_HAVE_TRADED",
})


def _grid():
    """Full cartesian input grid for the property sweep -- covers every branch boundary
    (0/1 trades; pnl straddling 0 and the $100 floor; left straddling the $100 floor;
    mfe straddling the 30% bar; blocked present/absent; oracle None/neg/pos)."""
    for (n_tr, pnl, left, mfe, peak, n_q, modal, oracle, any_trig) in itertools.product(
        (0, 1, 3),
        (None, -512.0, -1.0, 0.0, 1.0, 99.99, 100.0, 431.5),
        (0.0, 99.99, 100.0, 640.0),
        (0.0, 0.2999, 0.30, 1.8),
        (0.0, 415.0),
        (0, 1, 4),
        (None, 5, 8),
        (None, -260.0, 353.0),
        (False, True),
    ):
        if n_tr > 0 and pnl is None:
            continue  # traded day always has a P&L
        yield dict(
            n_walked_trades=n_tr, day_pnl=pnl, best_left_dollars=left,
            best_mfe_pct=mfe, best_peak_dollars=peak,
            n_qualifying_blocked=n_q, modal_blocker=modal,
            oracle_bound_dollars=oracle, any_trigger_fired=any_trig,
        )


# ------------------------------------------------------------------ 1. taxonomy enum

def test_taxonomy_enum_is_exactly_the_seven_approved_causes():
    assert frozenset(drc.VALID_CAUSES) == EXPECTED_CAUSES


def test_classifier_only_emits_valid_causes_over_full_grid():
    n = 0
    for kwargs in _grid():
        out = drc.classify_day(**kwargs)
        assert out["cause"] in EXPECTED_CAUSES, f"invalid cause {out['cause']!r} for {kwargs}"
        assert set(out.keys()) == {"cause", "cause_detail", "cause_dollars"}
        if out["cause"] == "GATE_BLOCKED":
            assert out["cause_detail"].startswith("filter_") or out["cause_detail"] == "blocker_unknown"
        n += 1
    assert n > 1000  # the sweep actually swept


# ------------------------------------------------------------------ 2. determinism

def test_classifier_is_deterministic_over_full_grid():
    first = [json.dumps(drc.classify_day(**k), sort_keys=True) for k in _grid()]
    second = [json.dumps(drc.classify_day(**k), sort_keys=True) for k in _grid()]
    assert first == second


FIXED_CARDS = [
    {"date": "2026-04-01", "cause": "GREEN", "cause_detail": "day_pnl>=focus_floor", "cause_dollars": 210.0},
    {"date": "2026-04-02", "cause": "GATE_BLOCKED", "cause_detail": "filter_5", "cause_dollars": 353.0},
    {"date": "2026-04-03", "cause": "GATE_BLOCKED", "cause_detail": "filter_5", "cause_dollars": -120.0},
    {"date": "2026-04-06", "cause": "GATE_BLOCKED", "cause_detail": "filter_8", "cause_dollars": None},
    {"date": "2026-04-07", "cause": "CORRECTLY_FLAT", "cause_detail": "triggers_seen_none_qualifying", "cause_dollars": 0.0},
    {"date": "2026-04-08", "cause": "NO_VOCABULARY", "cause_detail": "zero_triggers_all_day", "cause_dollars": 0.0},
    {"date": "2026-04-09", "cause": "SHOULD_NOT_HAVE_TRADED", "cause_detail": "never_reached_+30pct", "cause_dollars": -300.0},
    {"date": "2026-04-10", "cause": "EXIT_TOO_LATE", "cause_detail": "held_+30pct_winner_exited<=0", "cause_dollars": 415.0},
    {"date": "2026-04-13", "cause": "EXIT_LEFT_MONEY", "cause_detail": "positive_day_left>=focus_floor", "cause_dollars": 180.0},
]


def test_aggregate_is_deterministic_and_pinned():
    a = drc.aggregate_cards(FIXED_CARDS)
    b = drc.aggregate_cards(FIXED_CARDS)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    rows = {r["cause_key"]: r for r in a["ranked"]}
    # GATE_BLOCKED splits per filter; None-dollar cards counted but excluded from sums
    assert rows["GATE_BLOCKED[filter_5]"]["n_days"] == 2
    assert rows["GATE_BLOCKED[filter_5]"]["total_dollars"] == pytest.approx(233.0)
    assert rows["GATE_BLOCKED[filter_8]"]["n_days"] == 1
    assert rows["GATE_BLOCKED[filter_8]"]["total_dollars"] == 0.0
    assert rows["GATE_BLOCKED[filter_8]"]["n_days_dollars_unknown"] == 1
    assert rows["GREEN"]["total_dollars"] == pytest.approx(210.0)
    # ranked by |total_dollars| descending
    totals = [abs(r["total_dollars"]) for r in a["ranked"]]
    assert totals == sorted(totals, reverse=True)


# ------------------------------------------------------------------ 3. branch pins

def _base(**over):
    kw = dict(n_walked_trades=0, day_pnl=None, best_left_dollars=0.0, best_mfe_pct=0.0,
              best_peak_dollars=0.0, n_qualifying_blocked=0, modal_blocker=None,
              oracle_bound_dollars=None, any_trigger_fired=False)
    kw.update(over)
    return kw


@pytest.mark.parametrize("kwargs,cause,dollars", [
    # traded tree
    (_base(n_walked_trades=2, day_pnl=150.0), "GREEN", 150.0),
    (_base(n_walked_trades=1, day_pnl=40.0, best_left_dollars=250.0), "EXIT_LEFT_MONEY", 250.0),
    (_base(n_walked_trades=1, day_pnl=40.0, best_left_dollars=99.0), "GREEN", 40.0),
    (_base(n_walked_trades=1, day_pnl=-80.0, best_mfe_pct=0.55, best_peak_dollars=300.0),
     "EXIT_TOO_LATE", 380.0),                       # giveback = pre-exit peak - pnl = 300 - (-80)
    # PRE/POST-EXIT SPLIT PIN (the 2026-06-09 bug this tool's first draft had): a losing day
    # whose money appeared only AFTER the exit (mfe_pct is pre-exit and small, left is big)
    # is EXIT_LEFT_MONEY (stopped out, then it ran) -- NOT EXIT_TOO_LATE (opposite fixes).
    (_base(n_walked_trades=1, day_pnl=-390.0, best_mfe_pct=0.10, best_left_dollars=2900.0),
     "EXIT_LEFT_MONEY", 2900.0),
    (_base(n_walked_trades=1, day_pnl=-80.0, best_mfe_pct=0.10), "SHOULD_NOT_HAVE_TRADED", -80.0),
    (_base(n_walked_trades=1, day_pnl=0.0, best_mfe_pct=0.0), "SHOULD_NOT_HAVE_TRADED", 0.0),
    # flat tree
    (_base(n_qualifying_blocked=2, modal_blocker=5, oracle_bound_dollars=353.0),
     "GATE_BLOCKED", 353.0),
    (_base(n_qualifying_blocked=2, modal_blocker=5, oracle_bound_dollars=-120.0),
     "GATE_BLOCKED", -120.0),
    (_base(n_qualifying_blocked=1, modal_blocker=8, oracle_bound_dollars=None),
     "GATE_BLOCKED", None),
    (_base(any_trigger_fired=True), "CORRECTLY_FLAT", 0.0),
    (_base(), "NO_VOCABULARY", 0.0),
])
def test_branch_pins(kwargs, cause, dollars):
    out = drc.classify_day(**kwargs)
    assert out["cause"] == cause
    if dollars is None:
        assert out["cause_dollars"] is None
    else:
        assert out["cause_dollars"] == pytest.approx(dollars)


def test_traded_tree_wins_over_flat_tree():
    """A day with walked trades AND blocked qualifying moments classifies by the traded
    tree -- blocked moments on traded days are descriptive only."""
    out = drc.classify_day(**_base(n_walked_trades=1, day_pnl=120.0,
                                    n_qualifying_blocked=3, modal_blocker=5,
                                    oracle_bound_dollars=500.0))
    assert out["cause"] == "GREEN"


# ------------------------------------------------------------------ 4. helpers + fail-loud

def test_modal_blocker_tie_breaks_to_lowest_id():
    assert drc.modal_blocker_of([[5], [5, 8], [8]]) == 5      # 5:2, 8:2 -> tie -> lowest
    assert drc.modal_blocker_of([[8], [8], [5]]) == 8
    assert drc.modal_blocker_of([]) is None
    assert drc.modal_blocker_of([[]]) is None


def test_aggregate_rejects_unknown_cause():
    bad = [{"date": "2026-04-01", "cause": "GREEEN", "cause_detail": "x", "cause_dollars": 1.0}]
    with pytest.raises(ValueError):
        drc.aggregate_cards(bad)


def test_thresholds_are_doctrine_constants():
    assert drc.FOCUS_DAILY_FLOOR == 100.0   # FOCUS-DOCTRINE $100/day floor
    assert drc.MFE_WINNER_PCT == 0.30       # the +30% clean-trade bar
    assert drc.QUALIFYING_SCORE_FLOOR == 8  # task-specified score>=8 qualifying moment

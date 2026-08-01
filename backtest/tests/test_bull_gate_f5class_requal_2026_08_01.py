"""Guard tests for bull_gate_f5class_requal_2026_08_01.py (pure functions only).

Pins the FROZEN prereg semantics (analysis/recommendations/bull-gate-f5class-requal-
prereg-2026-08-01.json): trade-level drop-best, day-level day-majority, backward (no
look-ahead) f5 classification, the BH-FDR helper ported from shelf_hold_reclaim_study.py,
the N_FLOOR=20 OP-16 bar, and the four-tier verdict routing (UNDERPOWERED / EVIDENCE_FOR_
REEVAL / EVIDENCE_AGAINST / MIXED) that this study is EVIDENCE for Safe's scheduled re-eval,
never an automatic gate flip.

No network, no broker, no full backtest re-run -- that is exercised manually and its output
is committed to analysis/recommendations/.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest" / "tools"))

import bull_gate_f5class_requal_2026_08_01 as m  # noqa: E402


# --------------------------------------------------------------------------- drop_best
def test_drop_best_removes_single_largest_winner():
    remainder, positive = m.drop_best([-10.0, -20.0, 50.0])
    assert remainder == 20.0 - 50.0 == -30.0
    assert positive is False


def test_drop_best_no_winners_returns_total_unchanged():
    remainder, positive = m.drop_best([-10.0, -5.0])
    assert remainder == -15.0
    assert positive is False


def test_drop_best_empty_is_zero_not_positive():
    remainder, positive = m.drop_best([])
    assert remainder == 0.0
    assert positive is False


def test_drop_best_all_positive_after_removing_best():
    remainder, positive = m.drop_best([10.0, 20.0, 5.0])
    assert remainder == 15.0
    assert positive is True


# --------------------------------------------------------------------------- day_majority
def test_day_majority_aggregates_by_day_not_by_trade():
    # day 1 has two trades netting -$5 (loser day even though it has a winning trade);
    # day 2 has one trade +$100 (winner day) -> 1/2 days win = NOT majority
    trades = [
        {"date": "2026-01-02", "pnl": 50.0}, {"date": "2026-01-02", "pnl": -55.0},
        {"date": "2026-01-03", "pnl": 100.0},
    ]
    dm = m.day_majority(trades)
    assert dm["days"] == 2
    assert dm["win_days"] == 1
    assert dm["is_majority"] is False


def test_day_majority_empty_trades_is_none_not_false():
    dm = m.day_majority([])
    assert dm["days"] == 0
    assert dm["is_majority"] is None


def test_day_majority_true_when_more_than_half_win():
    trades = [{"date": "2026-01-0%d" % d, "pnl": 1.0} for d in (2, 3)]
    trades.append({"date": "2026-01-04", "pnl": -1.0})
    dm = m.day_majority(trades)
    assert dm["win_days"] == 2 and dm["days"] == 3
    assert dm["is_majority"] is True


# --------------------------------------------------------------------------- recent_25 / Cell B
def test_recent_25_slice_filters_by_start_date():
    trades = [{"date": "2026-06-01", "pnl": 1.0}, {"date": "2026-07-01", "pnl": 2.0}]
    sliced = m.recent_25_slice(trades, "2026-06-15")
    assert len(sliced) == 1 and sliced[0]["date"] == "2026-07-01"


def test_recent_25_slice_collapses_to_whole_cell_when_start_is_none():
    # Cell B (post-fix, 4 sessions) has no separate recent-25 window -- the prereg's g4 text:
    # "recent-25 is definitionally the whole cell -- reported as N/A-collapsed"
    trades = [{"date": "2026-07-28", "pnl": 1.0}, {"date": "2026-07-31", "pnl": -2.0}]
    sliced = m.recent_25_slice(trades, None)
    assert sliced == trades


# --------------------------------------------------------------------------- BH-FDR (ported)
def test_bh_fdr_known_case_matches_shelf_hold_reclaim():
    # Same worked example shape as shelf_hold_reclaim_study.py's own BH-FDR usage: one very
    # significant p-value amid noise should survive q=0.10 while the noise does not.
    pvals = [0.001, 0.20, 0.35, 0.50]
    sig = m.bh_fdr(pvals, q=0.10)
    assert sig[0] is True
    assert sig[1:] == [False, False, False]


def test_bh_fdr_empty_returns_empty():
    assert m.bh_fdr([], q=0.10) == []


def test_one_sample_p_single_trade_is_never_significant():
    assert m.one_sample_p([500.0]) == 1.0


# --------------------------------------------------------------------------- f5 classification
def _lookup(rows: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp_et": pd.to_datetime([r[0] for r in rows]),
        "stack": [r[1] for r in rows],
    })


def test_classify_f5_uses_backward_asof_no_lookahead():
    lookup = _lookup([
        ("2026-07-31T10:00:00", "BEAR"),
        ("2026-07-31T10:05:00", "BULL"),
        ("2026-07-31T10:10:00", "BULL"),
    ])
    # an entry at 10:07 must use the 10:05 BULL row (last known AT OR BEFORE), never 10:10
    flags = m.classify_f5([pd.Timestamp("2026-07-31T10:07:00")], lookup)
    assert flags == [True]


def test_classify_f5_before_any_data_is_false_not_true():
    lookup = _lookup([("2026-07-31T10:00:00", "BULL")])
    flags = m.classify_f5([pd.Timestamp("2026-07-31T09:00:00")], lookup)
    assert flags == [False]   # NaN stack != 'BULL' -> False, never silently admitted


def test_classify_f5_exact_bar_match_uses_that_bar():
    lookup = _lookup([("2026-07-31T10:05:00", "BULL"), ("2026-07-31T10:10:00", "BEAR")])
    flags = m.classify_f5([pd.Timestamp("2026-07-31T10:10:00")], lookup)
    assert flags == [False]


def test_classify_f5_preserves_input_order_not_sorted_order():
    lookup = _lookup([("2026-07-31T10:00:00", "BULL"), ("2026-07-31T11:00:00", "BEAR")])
    # deliberately out-of-order input -- output must map back to the ORIGINAL positions
    times = [pd.Timestamp("2026-07-31T11:30:00"), pd.Timestamp("2026-07-31T10:30:00")]
    flags = m.classify_f5(times, lookup)
    assert flags == [False, True]   # [after BEAR row, after BULL row]


# --------------------------------------------------------------------------- added_bull_cohort
def _trade(entry_time_et, side="C", strike=745):
    return SimpleNamespace(entry_time_et=entry_time_et, side=side, strike=strike)


def test_added_bull_cohort_diffs_base_vs_unblock():
    shared = _trade(dt.datetime(2026, 7, 31, 12, 16, 2))
    only_unblocked = _trade(dt.datetime(2026, 7, 31, 13, 24, 3))
    base = SimpleNamespace(trades=[shared])
    unblock = SimpleNamespace(trades=[shared, only_unblocked])
    added = m.added_bull_cohort(base, unblock)
    assert len(added) == 1
    assert added[0] is only_unblocked


def test_added_bull_cohort_excludes_put_side():
    only_unblocked_put = _trade(dt.datetime(2026, 7, 31, 13, 24, 3), side="P")
    base = SimpleNamespace(trades=[])
    unblock = SimpleNamespace(trades=[only_unblocked_put])
    assert m.added_bull_cohort(base, unblock) == []


# --------------------------------------------------------------------------- option_symbol
def test_option_symbol_format_matches_opra_convention():
    assert m.option_symbol(dt.date(2026, 7, 31), 746, "C") == "SPY260731C00746000"


# --------------------------------------------------------------------------- N_FLOOR (OP-16)
def test_n_floor_matches_op16_evidence_bar():
    assert m.N_FLOOR == 20


# --------------------------------------------------------------------------- grade_cell (verdict routing)
def _stats(n, total, day_maj, drop_pos, recent_total):
    return {"n": n, "total_pnl": total,
            "day_majority": {"is_majority": day_maj},
            "drop_best": {"still_positive": drop_pos},
            "recent_25": {"total_pnl": recent_total}}


def test_grade_cell_underpowered_below_n_floor_regardless_of_quality():
    stats = _stats(n=19, total=99999.0, day_maj=True, drop_pos=True, recent_total=1.0)
    g = m.grade_cell(stats)
    assert g["tier"] == "UNDERPOWERED"
    assert g["n_floor"] == 20


def test_grade_cell_evidence_for_reeval_when_all_pass():
    stats = _stats(n=25, total=500.0, day_maj=True, drop_pos=True, recent_total=10.0)
    g = m.grade_cell(stats)
    assert g["tier"] == "EVIDENCE_FOR_REEVAL"


def test_grade_cell_evidence_for_reeval_with_only_one_of_g2_g3():
    # matches the prereg's OR: (g2 OR g3) AND g4 -- drop-best fails but day-majority holds
    stats = _stats(n=25, total=500.0, day_maj=True, drop_pos=False, recent_total=10.0)
    g = m.grade_cell(stats)
    assert g["tier"] == "EVIDENCE_FOR_REEVAL"


def test_grade_cell_evidence_against_when_total_negative():
    stats = _stats(n=25, total=-500.0, day_maj=False, drop_pos=False, recent_total=-10.0)
    g = m.grade_cell(stats)
    assert g["tier"] == "EVIDENCE_AGAINST"


def test_grade_cell_mixed_when_recent25_fails_despite_positive_total():
    # g1/g2/g3 all pass but recent-25 (elevated, first-class per J's recency directive) is
    # negative -- must NOT read as full evidence-for-reeval
    stats = _stats(n=25, total=500.0, day_maj=True, drop_pos=True, recent_total=-1.0)
    g = m.grade_cell(stats)
    assert g["tier"] == "MIXED"


def test_grade_cell_mixed_when_neither_g2_nor_g3_pass():
    stats = _stats(n=25, total=500.0, day_maj=False, drop_pos=False, recent_total=10.0)
    g = m.grade_cell(stats)
    assert g["tier"] == "MIXED"

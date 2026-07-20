"""Guard tests for backtest/tools/premarket_touch_credit_study.py (PREMARKET-TOUCH-CREDIT-STUDY,
queue.md HIGH, filed 2026-07-20). Pure mechanism tests -- no network, no trading-path files."""
from __future__ import annotations

import datetime as dt
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "tools"))

import pandas as pd
import pytest

import premarket_touch_credit_study as ptc


# ---------------------------------------------------------------------------------------------
# BH-FDR -- verify the copied implementation matches the source (backtest/futures/battery.py)
# behavior on known inputs (canonical BH step-up examples).
# ---------------------------------------------------------------------------------------------
def test_bh_fdr_empty():
    assert ptc.bh_fdr([]) == []


def test_bh_fdr_all_significant_survive():
    # all p-values well below alpha at every rank -> all survive
    out = ptc.bh_fdr([0.001, 0.002, 0.003], alpha=0.05)
    assert out == [True, True, True]


def test_bh_fdr_none_survive():
    out = ptc.bh_fdr([0.9, 0.8, 0.95], alpha=0.05)
    assert out == [False, False, False]


def test_bh_fdr_nan_never_survives():
    out = ptc.bh_fdr([0.001, float("nan")], alpha=0.05)
    assert out[1] is False


def test_bh_fdr_step_up_classic_example():
    # classic textbook example: 5 p-values, alpha=0.05 -> only the smallest 2 survive
    pvals = [0.01, 0.04, 0.03, 0.20, 0.50]
    out = ptc.bh_fdr(pvals, alpha=0.05)
    # ranks (sorted): 0.01(1) 0.03(2) 0.04(3) 0.20(4) 0.50(5)
    # thresholds: 1/5*.05=.01 2/5*.05=.02 3/5*.05=.03 4/5*.05=.04 5/5*.05=.05
    # 0.01<=0.01 survives rank1; 0.03<=0.02? no -> largest rank where p<=thresh is rank1 only
    assert out[0] is True          # p=0.01, rank 1, survives
    assert out[2] is False         # p=0.03, rank 2, 0.03 > 0.02 -> does not survive alone
    assert sum(out) <= 2


# ---------------------------------------------------------------------------------------------
# PREMARKET TOUCH DETECTION -- direction-matched production test, synthetic fixture
# ---------------------------------------------------------------------------------------------
def _mk_bar(time_, high, low, close):
    return {"time": time_, "high": high, "low": low, "close": close}


def _mk_spy_full(date_, bars):
    rows = []
    for b in bars:
        rows.append({"date": date_, "time": b["time"], "high": b["high"], "low": b["low"],
                     "close": b["close"]})
    return pd.DataFrame(rows)


def test_premarket_touch_count_put_side_rejection_fires():
    date_ = dt.date(2026, 7, 1)
    # premarket bar pierces 500 and closes back below -> rejection, side='P' (bear trigger)
    bars = [_mk_bar(dt.time(9, 0), 500.5, 499.8, 499.9)]
    spy_full = _mk_spy_full(date_, bars)
    n = ptc.premarket_touch_count(spy_full, date_, 500.0, "P")
    assert n == 1


def test_premarket_touch_count_put_side_no_rejection():
    date_ = dt.date(2026, 7, 1)
    # bar never reaches the level -> no rejection
    bars = [_mk_bar(dt.time(9, 0), 499.5, 499.0, 499.2)]
    spy_full = _mk_spy_full(date_, bars)
    n = ptc.premarket_touch_count(spy_full, date_, 500.0, "P")
    assert n == 0


def test_premarket_touch_count_call_side_reclaim_fires():
    date_ = dt.date(2026, 7, 1)
    # bar dips below 500 and closes back above -> reclaim, side='C' (bull trigger)
    bars = [_mk_bar(dt.time(8, 30), 500.6, 499.5, 500.4)]
    spy_full = _mk_spy_full(date_, bars)
    n = ptc.premarket_touch_count(spy_full, date_, 500.0, "C")
    assert n == 1


def test_premarket_touch_count_excludes_rth_bars():
    date_ = dt.date(2026, 7, 1)
    # a bar AT 09:30 (RTH) that would fire is NOT counted -- premarket only, strictly < 09:30
    bars = [_mk_bar(dt.time(9, 30), 500.5, 499.8, 499.9), _mk_bar(dt.time(9, 29), 499.0, 498.5, 498.8)]
    spy_full = _mk_spy_full(date_, bars)
    n = ptc.premarket_touch_count(spy_full, date_, 500.0, "P")
    assert n == 0   # the 09:29 bar never reaches 500, the 09:30 bar is excluded by time filter


def test_premarket_touch_count_only_reads_own_date():
    # a bar on a DIFFERENT date that would fire must never be counted (no cross-day leakage)
    date_ = dt.date(2026, 7, 1)
    other_date = dt.date(2026, 6, 30)
    bars = [{"date": other_date, "time": dt.time(9, 0), "high": 500.5, "low": 499.8, "close": 499.9}]
    spy_full = pd.DataFrame(bars)
    n = ptc.premarket_touch_count(spy_full, date_, 500.0, "P")
    assert n == 0


# ---------------------------------------------------------------------------------------------
# SEGMENTATION MATH -- pure, no I/O
# ---------------------------------------------------------------------------------------------
def test_segment_delta_basic():
    prepared = [{"pnl": 100.0}, {"pnl": -50.0}, {"pnl": 20.0}, {"pnl": -80.0}]
    flags = [True, True, False, False]
    delta = ptc.segment_delta(prepared, flags)
    # touched mean = (100-50)/2=25, untouched mean=(20-80)/2=-30, delta=55
    assert delta == pytest.approx(55.0)


def test_segment_delta_one_group_empty_returns_zero():
    prepared = [{"pnl": 100.0}, {"pnl": -50.0}]
    flags = [True, True]
    assert ptc.segment_delta(prepared, flags) == 0.0


def test_other_active_levels_excludes_trigger_level():
    class FakeLevelSet:
        active = [500.0, 501.0, 499.0]
    out = ptc.other_active_levels(FakeLevelSet(), 500.0)
    assert 500.0 not in out
    assert set(out) == {501.0, 499.0}


def test_other_active_levels_none_inputs():
    assert ptc.other_active_levels(None, 500.0) == []
    assert ptc.other_active_levels(object(), None) == []


# ---------------------------------------------------------------------------------------------
# NULLS -- deterministic under a fixed seed, sanity on shape/range
# ---------------------------------------------------------------------------------------------
def test_random_label_null_deterministic_and_bounded():
    prepared = [{"pnl": p} for p in [100.0, -50.0, 20.0, -80.0, 60.0, -10.0, 5.0, -5.0]]
    for i, p in enumerate(prepared):
        p["touched"] = i < 4
    observed = ptc.segment_delta(prepared, [p["touched"] for p in prepared])
    out1 = ptc.random_label_null(prepared, observed, random.Random(42))
    out2 = ptc.random_label_null(prepared, observed, random.Random(42))
    assert out1 == out2          # same seed -> byte-identical result
    assert 0.0 <= out1["p_value"] <= 1.0
    assert out1["n_draws"] == ptc.RANDOM_LABEL_DRAWS


# ---------------------------------------------------------------------------------------------
# SIGNAL LOAD + DEDUP -- reads the real cached files (no network), verifies dedup + filter
# ---------------------------------------------------------------------------------------------
def test_load_combined_signals_filters_window_and_dedups():
    signals = ptc.load_combined_signals()
    assert len(signals) > 0
    for s in signals:
        # every signal in the combined set is either in the canonical filtered window or the
        # fresh set's own window -- both are >= 2026-05-19 by construction of this study.
        assert s["date"] >= "2026-05-19"
    keys = [(s["date"], s["entry_ts"], s["side"]) for s in signals]
    assert len(keys) == len(set(keys))     # no duplicate (date, entry_ts, side) triples


def test_load_combined_signals_no_stale_pre_sip_dates():
    signals = ptc.load_combined_signals()
    assert not any(s["date"] < ptc.CANONICAL_FILTER_START for s in signals)


# ---------------------------------------------------------------------------------------------
# PREFLIGHT -- pre-registration hash/version gate
# ---------------------------------------------------------------------------------------------
def test_preflight_passes_on_live_preregistration():
    pf = ptc.preflight()
    assert pf["preregistration_version_ok"] is True


def test_preregistration_file_exists_and_is_frozen():
    preg = json.loads(ptc.PREREG.read_text(encoding="utf-8"))
    assert preg["status"] == "FROZEN_PENDING_RUN"
    assert preg["version"] == 1
    assert "no_wire_this_run" in preg


# ---------------------------------------------------------------------------------------------
# VERDICT LADDER -- pure function, synthetic inputs covering each branch
# ---------------------------------------------------------------------------------------------
def _fake_overall(n_touched, n_untouched, p_random, p_shuffled, concentrated=False, sufficient=True):
    return {
        "n_touched": n_touched, "n_untouched": n_untouched,
        "random_label_null": {"p_value": p_random} if n_touched and n_untouched else None,
        "shuffled_level_null": {"p_value": p_shuffled} if n_touched and n_untouched else None,
        "touched_concentration_flag": {"concentrated": concentrated},
        "touched_day_concentration": {"top3_day_pct_of_net": 90.0 if concentrated else 10.0},
        "significance_floor": {"sufficient": sufficient},
    }


def _fake_subwindows(delta_first, delta_second):
    return {"first_half": {"observed_delta_touched_minus_untouched": delta_first},
            "second_half": {"observed_delta_touched_minus_untouched": delta_second}}


def test_verdict_no_split_possible_when_group_empty():
    overall = _fake_overall(0, 10, 0.5, 0.5)
    v = ptc.build_verdict(overall, _fake_subwindows(0, 0))
    assert v["overall"] == "NO_SPLIT_POSSIBLE"


def test_verdict_kill_when_not_significant():
    overall = _fake_overall(15, 12, 0.21, 0.208)
    v = ptc.build_verdict(overall, _fake_subwindows(50, -30))
    assert v["overall"] == "KILL"


def test_verdict_signal_when_all_conditions_clear():
    overall = _fake_overall(15, 12, 0.001, 0.002, concentrated=False, sufficient=True)
    v = ptc.build_verdict(overall, _fake_subwindows(50, 60))
    assert v["overall"] == "SIGNAL"


def test_verdict_subwindow_unstable_downgrades_significant_result():
    overall = _fake_overall(15, 12, 0.001, 0.002, concentrated=False, sufficient=True)
    v = ptc.build_verdict(overall, _fake_subwindows(50, -30))
    assert v["overall"] == "NO_SHIP_SUBWINDOW_UNSTABLE"


def test_verdict_concentrated_downgrades_significant_result():
    overall = _fake_overall(15, 12, 0.001, 0.002, concentrated=True, sufficient=True)
    v = ptc.build_verdict(overall, _fake_subwindows(50, 60))
    assert v["overall"] == "NO_SHIP_CONCENTRATED"


def test_verdict_underpowered_when_n_floor_fails():
    overall = _fake_overall(5, 4, 0.001, 0.002, concentrated=False, sufficient=False)
    v = ptc.build_verdict(overall, _fake_subwindows(50, 60))
    assert v["overall"] == "INCONCLUSIVE_UNDERPOWERED"


# ---------------------------------------------------------------------------------------------
# LIVE OUTPUT SANITY -- the actual committed run's output has the expected shape/keys
# ---------------------------------------------------------------------------------------------
def test_committed_output_json_has_expected_shape():
    out_path = REPO / "analysis" / "recommendations" / "premarket-touch-credit-2026-07-20.json"
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["verdict"]["overall"] in (
        "KILL", "SIGNAL", "NO_SHIP_SUBWINDOW_UNSTABLE", "NO_SHIP_CONCENTRATED",
        "INCONCLUSIVE_UNDERPOWERED", "NO_SPLIT_POSSIBLE",
    )
    assert data["preflight"]["preregistration_version_ok"] is True
    assert "overall" in data and "sub_windows" in data and "by_direction" in data

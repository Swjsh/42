"""Guard tests for backtest/tools/gate_revalidation_ab.py (GATE-REVALIDATION-2026-08-08).

Pins: (1) the ported stats helpers behave per their documented contract, (2) the CORRECTED
cell-3 population classifier (>=1 real trigger required, not just sole-blocked) never
regresses back to the audit's original mischaracterized definition, (3) cell 1/2 row filters
match on the right account+verdict+armed fields, (4) the G-battery verdict logic.

Pure unit tests on synthetic fixtures -- no live core-decisions.jsonl / OPRA cache dependency,
so these stay green regardless of what today's ledger looks like.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest" / "tools"))

import gate_revalidation_ab as gr  # noqa: E402


# ==================================================================== one_sample_p ==========
def test_one_sample_p_n_lt_2_returns_1():
    assert gr.one_sample_p([]) == 1.0
    assert gr.one_sample_p([5.0]) == 1.0


def test_one_sample_p_zero_variance_returns_1():
    assert gr.one_sample_p([10.0, 10.0, 10.0]) == 1.0


def test_one_sample_p_strong_positive_signal_is_small():
    # tight cluster of positive values, far from zero -> small p
    p = gr.one_sample_p([100.0, 102.0, 98.0, 101.0, 99.0, 103.0])
    assert 0.0 <= p < 0.01


def test_one_sample_p_noisy_near_zero_is_large():
    p = gr.one_sample_p([50.0, -60.0, 40.0, -30.0])
    assert p > 0.3


# ==================================================================== bh_fdr ================
def test_bh_fdr_all_significant_when_all_tiny():
    sig = gr.bh_fdr([0.001, 0.002, 0.003], q=0.10)
    assert sig == [True, True, True]


def test_bh_fdr_none_significant_when_all_large():
    sig = gr.bh_fdr([0.5, 0.6, 0.9], q=0.10)
    assert sig == [False, False, False]


def test_bh_fdr_mixed_case_step_up_procedure():
    # classic textbook-style case: sorted [0.01, 0.04, 0.20] vs q=0.10, m=3
    # thresholds: rank1 0.0333, rank2 0.0667, rank3 0.10
    # 0.01 <= 0.0333 (pass) ; 0.04 <= 0.0667 (pass) ; 0.20 <= 0.10 (fail) -> max_k = rank2 (idx1)
    pvals = [0.01, 0.04, 0.20]
    sig = gr.bh_fdr(pvals, q=0.10)
    assert sig == [True, True, False]


def test_bh_fdr_empty_input():
    assert gr.bh_fdr([], q=0.10) == []


# ==================================================================== drop_top_n ============
def test_drop_top3_all_losers_equals_raw_total():
    pnls = [-10.0, -5.0, -20.0]
    value, k = gr.drop_top_n(pnls, 3)
    assert value == sum(pnls)
    assert k == 0


def test_drop_top3_drops_exactly_three_largest_winners():
    pnls = [100.0, 50.0, 10.0, -5.0, 200.0, 5.0]  # winners: 100,50,10,200,5 -- top3: 200,100,50
    value, k = gr.drop_top_n(pnls, 3)
    assert k == 3
    assert value == round(sum(pnls) - (200.0 + 100.0 + 50.0), 2)


def test_drop_top3_fewer_than_three_winners_drops_all_of_them():
    pnls = [30.0, -10.0, -20.0]  # only 1 winner
    value, k = gr.drop_top_n(pnls, 3)
    assert k == 1
    assert value == round(sum(pnls) - 30.0, 2)


def test_drop_top3_empty_cohort():
    assert gr.drop_top_n([], 3) == (0.0, 0)


# ==================================================================== cell 1/2 row filters ==
def _row(**kw) -> dict:
    base = {"account": "safe", "armed": True, "verdict": "HOLD", "bull_blockers": [],
            "bull_triggers_raw": []}
    base.update(kw)
    return base


def test_cell1_filters_safe_structure_veto_only():
    rows = [
        _row(account="safe", verdict="SKIP_STRUCTURE_VETO", armed=True),   # match
        _row(account="bold", verdict="SKIP_STRUCTURE_VETO", armed=True),   # wrong account
        _row(account="safe", verdict="SKIP_STRUCTURE_VETO", armed=False),  # not armed
        _row(account="safe", verdict="HOLD", armed=True),                  # wrong verdict
    ]
    out = gr.cell1_rows(rows)
    assert len(out) == 1
    assert out[0]["account"] == "safe" and out[0]["verdict"] == "SKIP_STRUCTURE_VETO"


def test_cell2_filters_bold_fill_bar_only():
    rows = [
        _row(account="bold", verdict="SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY", armed=True),  # match
        _row(account="safe", verdict="SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY", armed=True),  # wrong acct
        _row(account="bold", verdict="SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY", armed=False),  # not armed
    ]
    out = gr.cell2_rows(rows)
    assert len(out) == 1
    assert out[0]["account"] == "bold"


# ==================================================================== cell 3 CORRECTED filter
def test_cell3_excludes_zero_trigger_sole_block():
    """THE regression this pins: a sole-[11]-blocked row with ZERO real triggers must be
    EXCLUDED from cell 3's tested population -- including it is exactly the audit's original
    mischaracterization (551/275 'sole-blocked' == almost entirely zero-trigger noise)."""
    rows = [_row(account="safe", armed=True, bull_blockers=[11], bull_triggers_raw=[])]
    assert gr.cell3_rows_corrected(rows) == []


def test_cell3_includes_one_trigger_sole_block():
    """A sole-[11]-blocked row WITH a real trigger present is the honest 'would be unblocked'
    population and must be INCLUDED."""
    rows = [_row(account="safe", armed=True, bull_blockers=[11], bull_triggers_raw=["ribbon_flip"])]
    out = gr.cell3_rows_corrected(rows)
    assert len(out) == 1


def test_cell3_excludes_co_blocked_rows_even_with_a_real_trigger():
    """A row with a real trigger that ALSO fails another filter (blockers != [11] alone) is
    NOT sole-blocked by 11 -- relaxing filter 11 wouldn't unblock it, so it's excluded."""
    rows = [_row(account="safe", armed=True, bull_blockers=[10, 11], bull_triggers_raw=["ribbon_flip"])]
    assert gr.cell3_rows_corrected(rows) == []


def test_cell3_excludes_bold_and_unarmed():
    rows = [
        _row(account="bold", armed=True, bull_blockers=[11], bull_triggers_raw=["level_reclaim"]),
        _row(account="safe", armed=False, bull_blockers=[11], bull_triggers_raw=["level_reclaim"]),
    ]
    assert gr.cell3_rows_corrected(rows) == []


# ==================================================================== g_battery verdicts ====
def _cohort(n: int, mean: float, drop_top3: float) -> dict:
    return {"n": n, "mean": mean, "drop_top3": drop_top3}


def test_g_battery_unblock_eligible_when_all_pass():
    cohort = _cohort(n=20, mean=10.0, drop_top3=50.0)
    oos = {"n": 8, "mean": 5.0}
    out = gr.g_battery(cohort, oos, pval=0.01, bh_pass=True)
    assert out["verdict"] == "UNBLOCK-ELIGIBLE"
    assert all(out["gates"].values())


def test_g_battery_underpowered_when_only_n_fails():
    cohort = _cohort(n=11, mean=10.0, drop_top3=50.0)
    oos = {"n": 5, "mean": 5.0}
    out = gr.g_battery(cohort, oos, pval=0.01, bh_pass=True)
    assert out["verdict"] == "UNDERPOWERED"
    assert out["gates"]["G_n"] is False
    assert out["gates"]["G_mean"] is True


def test_g_battery_not_unblock_eligible_when_mean_negative_even_if_n_large():
    cohort = _cohort(n=40, mean=-5.0, drop_top3=-100.0)
    oos = {"n": 20, "mean": -2.0}
    out = gr.g_battery(cohort, oos, pval=0.9, bh_pass=False)
    assert out["verdict"] == "NOT-UNBLOCK-ELIGIBLE"


def test_g_battery_empty_cohort_is_not_unblock_eligible():
    cohort = _cohort(n=0, mean=0.0, drop_top3=0.0)
    oos = {"n": 0, "mean": 0.0}
    out = gr.g_battery(cohort, oos, pval=1.0, bh_pass=False)
    assert out["verdict"] == "NOT-UNBLOCK-ELIGIBLE"
    assert out["gates"]["G_mean"] is False

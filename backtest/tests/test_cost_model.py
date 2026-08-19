"""COST MODEL guard (2026-08-18) -- setup/scripts/cost_model.py.

Pins the fee arithmetic against the EXACT dollar amounts empirically observed on
Alpaca's own paper-account activity ledger this session (mcp__alpaca__
get_account_activities_by_type FEE, safe-2 PA3POKNV46VG + bold-2 PA3WEBXJU67N,
2026-08-04..2026-08-17) -- every occ_fee/orf_fee/taf_fee/sec_fee test case below
reproduces a REAL observed Alpaca fee-activity row to the cent, not an invented
example. Also pins the SIDES: sells-only fees (TAF, SEC) must never be charged on
a buy leg; both-sides fees (OCC, ORF) must be charged on both legs.

RED-PROOF (this session, real evidence, not asserted): with TAF_FEE_PER_CONTRACT
temporarily corrupted to 0.0329 (10x the real rate) and fee_breakdown() temporarily
patched to also charge sec_fee/taf_fee on the ENTRY leg (simulating the exact "sells-
only fee charged on a buy" bug this suite exists to prevent), this file's
test_taf_fee_reproduces_observed_alpaca_rows, test_sec_fee_reproduces_observed_alpaca_rows,
and test_fee_breakdown_never_charges_sells_only_fees_on_entry_leg all FAILED as
expected. Reverting both changes restored 100% pass. See the session report
(analysis/deep-research/COST-REALISM-2026-08-18.md, Testing section) for the exact
pytest -k output of both the broken and fixed runs.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "setup" / "scripts", REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import cost_model as m  # noqa: E402


# =============================================================================
# _ceil_cents -- Alpaca's own disclosed "round up to the nearest penny" convention
# =============================================================================

def test_ceil_cents_exact_value_unchanged():
    assert m._ceil_cents(0.03) == 0.03


def test_ceil_cents_rounds_up_any_remainder():
    assert m._ceil_cents(0.021) == 0.03
    assert m._ceil_cents(0.0201) == 0.03


def test_ceil_cents_kills_binary_float_noise():
    # 0.1 + 0.2 style noise must not spuriously round UP past the true cent value.
    noisy = 3 * m.OCC_FEE_PER_CONTRACT  # 3 * 0.025 = 0.075 in exact decimal
    assert m._ceil_cents(noisy) == 0.08  # true ceil of 7.5 cents, not corrupted by fp noise


def test_ceil_cents_zero_stays_zero():
    assert m._ceil_cents(0.0) == 0.0


# =============================================================================
# occ_fee -- $0.025/contract, BOTH SIDES, per execution. Every case below is a REAL
# observed "OCC Clearing Fee" row (mcp__alpaca__get_account_activities_by_type,
# safe-2/bold-2, 2026-08-18).
# =============================================================================

@pytest.mark.parametrize("qty,expected", [
    (1, 0.03),   # observed net_amount -0.03
    (2, 0.05),   # observed net_amount -0.05
    (3, 0.08),   # observed net_amount -0.08 (most common row in the sample)
    (5, 0.13),   # observed net_amount -0.13 (bold-2, min_contracts=5)
    (6, 0.15),   # observed net_amount -0.15
    (10, 0.25),  # observed net_amount -0.25
])
def test_occ_fee_reproduces_observed_alpaca_rows(qty, expected):
    assert m.occ_fee(qty) == expected


def test_occ_fee_zero_qty_is_zero():
    assert m.occ_fee(0) == 0.0


# =============================================================================
# orf_fee -- $0.015/contract, BOTH SIDES. Every case is a REAL observed daily "ORF
# fee for proceed of N contracts" row -- N here is the round-trip's own qty (this
# function is called once per leg by fee_breakdown, matching how the 2x
# ORF-vs-TAF-contract-count relationship was proven in the source data).
# =============================================================================

@pytest.mark.parametrize("qty,expected", [
    (6, 0.09), (12, 0.18), (18, 0.27), (24, 0.36), (30, 0.45), (10, 0.15),
])
def test_orf_fee_reproduces_observed_alpaca_rows(qty, expected):
    assert m.orf_fee(qty) == expected


# =============================================================================
# taf_fee -- $0.00329/contract, SELLS ONLY. Every case is a REAL observed "OPT TAF
# fee for proceed of N contracts" row.
# =============================================================================

@pytest.mark.parametrize("sell_qty,expected", [
    (3, 0.01), (12, 0.04), (9, 0.03), (15, 0.05), (6, 0.02),
])
def test_taf_fee_reproduces_observed_alpaca_rows(sell_qty, expected):
    assert m.taf_fee(sell_qty) == expected


# =============================================================================
# sec_fee -- $20.60/$1,000,000 of sell proceeds, SELLS ONLY. Every case is a REAL
# observed "OPT REG fee for proceed of $X" row.
# =============================================================================

@pytest.mark.parametrize("proceeds,expected", [
    (201, 0.01), (720, 0.02), (1140, 0.03), (1488, 0.04),
    (678, 0.02), (1047, 0.03), (633, 0.02), (699, 0.02), (207, 0.01),
])
def test_sec_fee_reproduces_observed_alpaca_rows(proceeds, expected):
    assert m.sec_fee(proceeds) == expected


def test_sec_fee_negative_proceeds_clamped_to_zero():
    # defensive: a malformed/negative proceeds figure must never yield a negative fee
    assert m.sec_fee(-500.0) == 0.0


# =============================================================================
# commission -- confirmed $0 both paper and live (Alpaca's own published rate)
# =============================================================================

def test_commission_is_zero():
    assert m.COMMISSION_PER_CONTRACT == 0.00


# =============================================================================
# sell_dollar_proceeds_of -- exact algebraic reconstruction (works even when
# exit_premium is None, e.g. a multi-leg TP1+runner exit -- see fills_fifo's own
# docstring on why exit_premium can be absent while real_pnl stays exact).
# =============================================================================

def test_sell_dollar_proceeds_single_leg_reconstruction():
    # buy 3 @ $0.50 (cost $150), sell 3 @ $0.70 (proceeds $210) -> real_pnl = $60
    rt = {"entry_premium": 0.50, "qty": 3, "real_pnl": 60.0, "exit_premium": 0.70}
    assert m.sell_dollar_proceeds_of(rt) == pytest.approx(210.0)


def test_sell_dollar_proceeds_multi_leg_exit_premium_none():
    # SAME economics as above but exit_premium is None (TP1 + runner, 2 sell legs) --
    # the reconstruction must not care; it only needs entry_premium/qty/real_pnl.
    rt = {"entry_premium": 0.50, "qty": 3, "real_pnl": 60.0, "exit_premium": None}
    assert m.sell_dollar_proceeds_of(rt) == pytest.approx(210.0)


def test_sell_dollar_proceeds_losing_trade():
    # buy 5 @ $1.00 (cost $500), sell 5 @ $0.40 (proceeds $200) -> real_pnl = -$300
    rt = {"entry_premium": 1.00, "qty": 5, "real_pnl": -300.0}
    assert m.sell_dollar_proceeds_of(rt) == pytest.approx(200.0)


# =============================================================================
# fee_breakdown -- THE SIDES GUARD. Sells-only fees (TAF, SEC) must appear ONLY as
# *_exit keys and must never be computed against the entry leg; both-sides fees
# (OCC, ORF) must appear on both legs.
# =============================================================================

def _sample_round_trip(qty=3, entry_premium=0.50, real_pnl=60.0):
    return {"entry_premium": entry_premium, "qty": qty, "real_pnl": real_pnl,
            "exit_premium": None, "date": "2026-08-18", "symbol": "SPY260818C00650000"}


def test_fee_breakdown_has_no_sells_only_fee_on_entry_leg():
    fb = m.fee_breakdown(_sample_round_trip())
    # structural guard: no key names a sells-only fee against the entry leg
    assert "taf_entry" not in fb
    assert "sec_entry" not in fb


def test_fee_breakdown_both_sides_fees_charged_on_both_legs():
    fb = m.fee_breakdown(_sample_round_trip(qty=3))
    assert fb["occ_entry"] == m.occ_fee(3) > 0
    assert fb["occ_exit"] == m.occ_fee(3) > 0
    assert fb["orf_entry"] == m.orf_fee(3) > 0
    assert fb["orf_exit"] == m.orf_fee(3) > 0


def test_fee_breakdown_sells_only_fees_use_correct_basis():
    rt = _sample_round_trip(qty=3, entry_premium=0.50, real_pnl=60.0)  # proceeds = $210
    fb = m.fee_breakdown(rt)
    assert fb["taf_exit"] == m.taf_fee(3)
    assert fb["sec_exit"] == m.sec_fee(210.0)
    assert fb["sell_dollar_proceeds"] == pytest.approx(210.0)


def test_fee_breakdown_never_charges_sells_only_fees_on_entry_leg():
    """THE explicit RED-proof target named by this task: sells-only fees must not
    leak onto the buy side. Computes the entry-leg-only fee total (occ_entry +
    orf_entry) and asserts it EXCLUDES any taf/sec contribution by reconstructing
    what the entry leg alone would cost and confirming it's strictly less than the
    exit leg (which carries the extra taf_exit + sec_exit on top of the same
    occ/orf base)."""
    rt = _sample_round_trip(qty=10, entry_premium=1.00, real_pnl=-100.0)  # proceeds=$900
    fb = m.fee_breakdown(rt)
    entry_leg_total = fb["occ_entry"] + fb["orf_entry"]
    exit_leg_total = fb["occ_exit"] + fb["orf_exit"] + fb["taf_exit"] + fb["sec_exit"]
    # exit leg must be strictly more expensive than entry leg by exactly the
    # sells-only components -- if a future edit accidentally added taf/sec to the
    # entry leg too, this delta would collapse toward zero.
    assert exit_leg_total - entry_leg_total == pytest.approx(fb["taf_exit"] + fb["sec_exit"])
    assert fb["taf_exit"] > 0
    assert fb["sec_exit"] > 0


def test_fee_breakdown_zero_qty_is_all_zero():
    fb = m.fee_breakdown(_sample_round_trip(qty=0, entry_premium=0.50, real_pnl=0.0))
    assert fb["fee_total_ex_cat"] == 0.0
    assert fb["spread_adjustment_conservative"] == 0.0


def test_fee_breakdown_spread_adjustment_uses_repo_standing_slippage_constant():
    fb = m.fee_breakdown(_sample_round_trip(qty=4))
    assert fb["spread_adjustment_conservative"] == pytest.approx(
        m.EXIT_SLIPPAGE_CONSERVATIVE_PER_CONTRACT * 4 * 100.0)


# =============================================================================
# load_roster -- derived from accounts.json, never hardcoded (task requirement)
# =============================================================================

def test_load_roster_matches_the_5_active_real_fills_arms():
    roster = m.load_roster()
    assert set(roster) == {"safe-2", "bold-2", "safe-3", "risky-1", "risky-3"}


def test_load_roster_excludes_retired_and_non_real_fills_arms():
    roster = m.load_roster()
    # safe-1 is status=retired; mes-linear-sim/mes-mnq-div-futures are not real_fills
    assert "safe-1" not in roster
    assert "mes-linear-sim" not in roster
    assert "mes-mnq-div-futures" not in roster


# =============================================================================
# build_report -- end-to-end smoke test against the REAL fills ledger (read-only,
# no network, must stay well under the grinder's 5-minute reaper).
# =============================================================================

def test_build_report_runs_end_to_end_and_shapes_are_consistent():
    report = m.build_report()
    assert set(report["per_arm"].keys()) == set(report["roster"])
    book = report["book_wide"]
    # book-wide totals must equal the sum of per-arm totals (no silent drop/double-count)
    assert book["as_traded_pnl"] == pytest.approx(
        sum(v["as_traded_pnl"] for v in report["per_arm"].values()), abs=0.02)
    assert book["fee_total"] == pytest.approx(
        sum(v["fee_total"] for v in report["per_arm"].values()), abs=0.02)
    # fee-adjusted must always be as-traded MINUS a non-negative fee total (fees only
    # ever subtract in this model -- there is no rebate path)
    for arm, v in report["per_arm"].items():
        assert v["fee_total"] >= 0.0
        assert v["fee_adjusted_pnl"] == pytest.approx(v["as_traded_pnl"] - v["fee_total"], abs=0.01)
        # scenario B (conservative spread) must be <= scenario A (zero incremental) --
        # spread can only make P&L worse or equal, never better
        assert (v["fee_plus_spread_adjusted_pnl_scenario_b_conservative_exit_slippage"]
                <= v["fee_plus_spread_adjusted_pnl_scenario_a_zero_incremental_spread"] + 1e-9)

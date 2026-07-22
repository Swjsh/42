"""Guard for RSI-EXTENSION-BLOCK-ELITE-BULL (J dojo ruling 2026-07-21).

Pins the committed golden finding: on the widened real-fills window, J's tape-read
hypothesis ("block extended/no-reset ELITE bull reclaims, pass fresh ones") does
NOT generalize to the full removed-by-block_elite_bull population -- only 1 of 9
trades even qualifies as "RSI-extended" at the most permissive pre-registered grid
point (X=65), so the discriminator is population-thin, not just underpowered on
its own scored subsets. n<10 overall -> INCONCLUSIVE per the canonical
significance() bar (probe_stats.py), same ceiling as every prior bull-frontier probe.

If a future engine change or data widening silently flips this to a BH-FDR
significant separation, this guard re-REDs so the finding gets re-audited (C7)
instead of a stale "inconclusive" masking a real discriminator.
"""
import json
import os

import pytest

from autoresearch.rsi_extension_block_probe import (
    _would_block_a, _would_block_b, _bh_fdr, X_GRID, Y_GRID, N_GRID, Z_GRID,
)

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RESULT = os.path.join(REPO, "analysis", "recommendations",
                      "rsi-extension-block-elite-bull-2026-07-22.json")


@pytest.fixture(scope="module")
def result():
    with open(RESULT) as f:
        return json.load(f)


def test_result_file_exists_and_is_this_probe(result):
    assert result["probe"] == "rsi_extension_block_probe"
    assert result["queue_id"] == "RSI-EXTENSION-BLOCK-ELITE-BULL"
    assert result["real_fills"] is True


def test_grid_is_pre_registered_not_hand_picked(result):
    """The grid stored in the result must match the module's frozen constants --
    proves no post-hoc re-running with a favorable grid."""
    grid = result["pre_registered_grid"]
    assert grid["X_rsi_extension"] == list(X_GRID)
    assert grid["Y_reset_below"] == list(Y_GRID)
    assert grid["N_reset_lookback_bars"] == list(N_GRID)
    assert grid["Z_dollars_above_low"] == list(Z_GRID)


def test_sample_too_small_to_conclude(result):
    """The golden finding: n<10 -> INCONCLUSIVE, not a false-confident verdict."""
    assert result["feature_extraction_n"] < 10
    assert result["verdict"] == "INCONCLUSIVE_SAMPLE_TOO_SMALL"


def test_no_bh_fdr_significant_hit(result):
    """No grid cell (condition a or b) clears BH-FDR q=0.10 on this population --
    consistent with the INCONCLUSIVE verdict, not contradicting it."""
    hits = [r["bh_fdr_significant_q10"] for r in result["condition_a_rsi_no_reset"]]
    hits += [r["bh_fdr_significant_q10"] for r in result["condition_b_dollars_above_low"]]
    assert not any(hits)


def test_discriminator_rarely_fires_on_this_population(result):
    """Beyond underpowered: at the MOST permissive grid point (X=65,Y=50,N=6), the
    RSI-extension condition blocks at most 1 of the 9 real trades -- the mechanism
    J read off one exhibit does not characterize the wider removed cohort, so
    widening N alone would not rescue this without more data."""
    cell = next(r for r in result["condition_a_rsi_no_reset"]
                if r["X"] == 65.0 and r["Y"] == 50.0 and r["N"] == 6)
    blocked_n = cell["would_stay_blocked"].get("summary", {}).get("n_trades", 0)
    assert blocked_n <= 1


def test_anchor_no_regression(result):
    assert result["anchor_no_regression"] is True


def test_would_block_a_logic_is_correct():
    """Non-vacuous unit check on the pure condition functions (not just the stored
    JSON) -- proves the guard would catch a real logic regression, not just a
    stale-artifact mismatch."""
    extended_no_reset = {"rsi_at_entry": 72.0, "min_rsi_by_n": {6: 60.0, 10: 58.0}}
    fresh_reset = {"rsi_at_entry": 72.0, "min_rsi_by_n": {6: 45.0, 10: 40.0}}
    assert _would_block_a(extended_no_reset, x=65.0, y=50.0, n=6) is True
    assert _would_block_a(fresh_reset, x=65.0, y=50.0, n=6) is False


def test_would_block_b_logic_is_correct():
    far_above = {"dollars_above_session_low": 6.0}
    near_low = {"dollars_above_session_low": 1.2}
    assert _would_block_b(far_above, z=5.0) is True
    assert _would_block_b(near_low, z=5.0) is False


def test_bh_fdr_flags_a_clearly_significant_pvalue():
    """Non-vacuous BH-FDR check: a tiny p-value among noise should be flagged, but
    an all-noise vector should not (proves the helper isn't a hollow always-False)."""
    sig = _bh_fdr([0.001, 0.6, 0.7, 0.8], q=0.10)
    assert sig[0] is True
    all_noise = _bh_fdr([0.4, 0.5, 0.6, 0.7], q=0.10)
    assert not any(all_noise)

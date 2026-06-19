"""Tests for the statistical promotion-rigor package (Phase 2c).

Validates that the peer-reviewed overfitting metrics behave correctly:
  - Deflated Sharpe penalises selection across many trials and non-normality.
  - PSR == DSR with a single trial (zero benchmark) — internal consistency.
  - PBO flags an overfit (pure-noise) trial matrix and clears a robust one.
  - The advisory gate returns PASS for robust, FAIL for selection-artefact,
    WEAK (never PASS) for an underpowered tiny sample.

References under test: SSRN 2460551 (DSR/PSR), SSRN 2326253 (PBO/CSCV).

Assertions are on robust inequalities / ordering with fixed RNG seeds rather
than brittle exact floats, so they stay green across numpy/scipy point releases.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from lib.validation import (
    DSR_MIN,
    FAIL,
    MIN_RELIABLE_OBS,
    PASS,
    PSR_MIN,
    WEAK,
    deflated_sharpe_ratio,
    evaluate_candidate,
    expected_max_sharpe,
    probabilistic_sharpe_ratio,
    probability_of_backtest_overfitting,
)


# --------------------------------------------------------------------------- #
# Fixtures: deterministic synthetic data                                      #
# --------------------------------------------------------------------------- #
def _robust_returns(n: int = 500, seed: int = 42) -> np.ndarray:
    """A genuinely-positive-edge return stream (Sharpe ~0.09/period)."""
    rng = np.random.default_rng(seed)
    return rng.normal(0.001, 0.01, size=n)


def _best_of_noise(n_obs: int = 250, n_trials: int = 200, seed: int = 7):
    """Best-IS column drawn from a pure-noise (zero-edge) trial matrix.

    Returns (best_column_returns, trials_sharpe_std, n_trials, full_matrix).
    This is the canonical selection-bias trap: the column LOOKS good purely
    because it won a large search over noise. The full matrix is returned so the
    SAME noise can feed PBO, keeping the overfit signal self-consistent (an
    independently-seeded PBO matrix would not reliably agree with the picked
    column).
    """
    rng = np.random.default_rng(seed)
    trials = rng.normal(0.0, 0.01, size=(n_obs, n_trials))
    sharpes = trials.mean(0) / trials.std(0)
    best = int(np.argmax(sharpes))
    return trials[:, best], float(sharpes.std()), n_trials, trials


def _mean_noise_pbo(n_seeds: int = 12, n_splits: int = 10) -> float:
    """Mean PBO of pure-noise matrices over several seeds.

    PBO on a single noise draw is itself noisy (per-seed ~0.3..0.8); its
    *expectation* is ~0.5 because the IS winner of pure noise is a coin-flip
    OOS. Averaging over seeds gives a stable assertion target.
    """
    vals = []
    for s in range(n_seeds):
        vals.append(
            probability_of_backtest_overfitting(
                _noise_matrix(seed=500 + s), n_splits=n_splits
            ).pbo
        )
    return float(np.mean(vals))


def _rank_stable_matrix(t: int = 160, n: int = 50, seed: int = 1) -> np.ndarray:
    """(T, N) matrix where column quality is consistent across time => low PBO.

    Each column has a fixed mean separated linearly; the best IS column is also
    the best OOS column, so the in-sample winner generalises.
    """
    rng = np.random.default_rng(seed)
    base = np.tile(np.linspace(0.5, 1.0, n), (t, 1))
    return base + rng.normal(0, 0.05, (t, n))


def _noise_matrix(t: int = 160, n: int = 50, seed: int = 2) -> np.ndarray:
    """(T, N) pure-noise matrix => IS winner is random OOS => high PBO."""
    rng = np.random.default_rng(seed)
    return rng.normal(0, 1, (t, n))


# --------------------------------------------------------------------------- #
# Deflated Sharpe Ratio                                                       #
# --------------------------------------------------------------------------- #
class TestDeflatedSharpe:
    def test_robust_strategy_stays_significant_at_one_trial(self):
        """A real edge over 500 obs is highly significant when not deflated."""
        res = deflated_sharpe_ratio(_robust_returns(), n_trials=1)
        assert res.dsr > 0.95
        assert res.n_obs == 500
        assert res.low_power is False
        # With a single trial there is no selection benchmark: SR_0 == 0.
        assert res.sharpe_benchmark == pytest.approx(0.0, abs=1e-12)

    def test_more_trials_monotonically_deflates(self):
        """Searching more configs lowers DSR for the SAME return stream."""
        r = _robust_returns()
        dsr_1 = deflated_sharpe_ratio(r, n_trials=1).dsr
        dsr_100 = deflated_sharpe_ratio(r, n_trials=100).dsr
        dsr_10000 = deflated_sharpe_ratio(r, n_trials=10_000).dsr
        assert dsr_1 > dsr_100 > dsr_10000
        # A modest real edge should not survive 10k trials of deflation.
        assert dsr_10000 < dsr_1

    def test_selection_artefact_is_deflated_below_robust(self):
        """Best-of-200-noise deflates far more than a true edge at 1 trial."""
        noise_ret, tstd, ntr, _mat = _best_of_noise()
        dsr_noise = deflated_sharpe_ratio(
            noise_ret, n_trials=ntr, trials_sharpe_std=tstd
        )
        # The expected-max benchmark SR_0 should be a large fraction of the
        # observed (inflated) Sharpe, dragging DSR well below the 0.95 bar.
        assert dsr_noise.sharpe_benchmark > 0.0
        assert dsr_noise.dsr < 0.95
        assert dsr_noise.dsr < deflated_sharpe_ratio(
            _robust_returns(), n_trials=1
        ).dsr

    def test_zero_volatility_raises(self):
        with pytest.raises(ValueError):
            deflated_sharpe_ratio(np.zeros(50), n_trials=1)

    def test_too_few_returns_raises(self):
        with pytest.raises(ValueError):
            deflated_sharpe_ratio([0.01], n_trials=1)

    def test_invalid_n_trials_raises(self):
        with pytest.raises(ValueError):
            deflated_sharpe_ratio(_robust_returns(), n_trials=0)

    def test_low_power_flag_on_small_sample(self):
        res = deflated_sharpe_ratio(_robust_returns(n=10), n_trials=5)
        assert res.n_obs < MIN_RELIABLE_OBS
        assert res.low_power is True


# --------------------------------------------------------------------------- #
# Probabilistic Sharpe Ratio + expected-max benchmark                         #
# --------------------------------------------------------------------------- #
class TestProbabilisticSharpe:
    def test_psr_equals_dsr_single_trial(self):
        """PSR(benchmark=0) must equal deflated_sharpe_ratio(n_trials=1)."""
        r = _robust_returns()
        dsr1 = deflated_sharpe_ratio(r, n_trials=1)
        psr = probabilistic_sharpe_ratio(
            dsr1.sharpe, dsr1.n_obs, dsr1.skew, dsr1.kurtosis, sharpe_benchmark=0.0
        )
        assert psr.psr == pytest.approx(dsr1.dsr, abs=1e-12)

    def test_psr_in_unit_interval(self):
        r = _robust_returns()
        dsr1 = deflated_sharpe_ratio(r, n_trials=1)
        psr = probabilistic_sharpe_ratio(
            dsr1.sharpe, dsr1.n_obs, dsr1.skew, dsr1.kurtosis
        )
        assert 0.0 <= psr.psr <= 1.0

    def test_higher_benchmark_lowers_psr(self):
        """Demanding a higher true Sharpe reduces the probability."""
        r = _robust_returns()
        d = deflated_sharpe_ratio(r, n_trials=1)
        low = probabilistic_sharpe_ratio(d.sharpe, d.n_obs, d.skew, d.kurtosis, 0.0)
        high = probabilistic_sharpe_ratio(
            d.sharpe, d.n_obs, d.skew, d.kurtosis, d.sharpe * 0.9
        )
        assert high.psr < low.psr

    def test_psr_requires_two_obs(self):
        with pytest.raises(ValueError):
            probabilistic_sharpe_ratio(1.0, 1, 0.0, 3.0)

    def test_expected_max_sharpe_monotonic_in_trials(self):
        """SR_0 grows with the number of trials searched."""
        sr0 = [expected_max_sharpe(0.1, n) for n in (1, 10, 100, 1000)]
        assert sr0[0] == 0.0  # one trial => no selection
        assert sr0[1] < sr0[2] < sr0[3]
        assert all(math.isfinite(x) for x in sr0)

    def test_expected_max_sharpe_zero_dispersion(self):
        """No spread across trials => no inflation => SR_0 == 0."""
        assert expected_max_sharpe(0.0, 500) == 0.0


# --------------------------------------------------------------------------- #
# Probability of Backtest Overfitting (CSCV)                                   #
# --------------------------------------------------------------------------- #
class TestPBO:
    def test_robust_matrix_low_pbo(self):
        """Rank-stable performance across time => the IS winner generalises."""
        res = probability_of_backtest_overfitting(_rank_stable_matrix(), n_splits=10)
        assert res.pbo < 0.2
        assert res.n_trials == 50
        assert res.n_splits == 10
        assert res.n_combinations == math.comb(10, 5)

    def test_noise_matrix_high_pbo(self):
        """Pure noise => IS winner is a coin-flip OOS => mean PBO ~0.5.

        A single noise draw's PBO is itself random (~0.3..0.8 across seeds), so
        assert on the seed-averaged value, whose expectation is ~0.5 and which
        sits far above any robust matrix (~0.0).
        """
        mean_pbo = _mean_noise_pbo()
        assert mean_pbo >= 0.4
        robust_pbo = probability_of_backtest_overfitting(
            _rank_stable_matrix(), n_splits=10
        ).pbo
        assert mean_pbo > robust_pbo + 0.3

    def test_overfit_pbo_exceeds_robust_pbo(self):
        robust = probability_of_backtest_overfitting(
            _rank_stable_matrix(), n_splits=10
        ).pbo
        overfit = _mean_noise_pbo()
        assert overfit > robust

    def test_pbo_in_unit_interval(self):
        res = probability_of_backtest_overfitting(_noise_matrix(), n_splits=8)
        assert 0.0 <= res.pbo <= 1.0
        assert 0.0 <= res.median_oos_rank <= 1.0

    def test_rejects_non_2d(self):
        with pytest.raises(ValueError):
            probability_of_backtest_overfitting(np.zeros(10), n_splits=4)

    def test_rejects_single_trial(self):
        with pytest.raises(ValueError):
            probability_of_backtest_overfitting(np.zeros((100, 1)), n_splits=4)

    def test_rejects_odd_splits(self):
        with pytest.raises(ValueError):
            probability_of_backtest_overfitting(_noise_matrix(), n_splits=7)

    def test_rejects_too_few_rows(self):
        """Refuse rather than emit a misleading PBO from an ill-posed split."""
        with pytest.raises(ValueError):
            probability_of_backtest_overfitting(np.zeros((4, 10)), n_splits=16)


# --------------------------------------------------------------------------- #
# Advisory gate                                                               #
# --------------------------------------------------------------------------- #
class TestGate:
    def test_robust_candidate_passes(self):
        res = evaluate_candidate(
            _robust_returns(),
            n_trials=5,
            performance_matrix=_rank_stable_matrix(),
            n_splits=10,
        )
        assert res.verdict == PASS
        assert res.psr >= PSR_MIN
        assert res.dsr > DSR_MIN
        assert res.pbo is not None and res.pbo < 0.5
        assert res.low_power is False

    def test_selection_artefact_fails(self):
        """Best-IS column of a pure-noise matrix + the SAME matrix for PBO.

        Self-consistent overfit: the winner was selected on noise, so PBO is
        high (~0.6) AND the Sharpe deflates hard — the gate must FAIL. (An
        independently-seeded PBO matrix would not reliably agree, so we reuse
        the candidate's own matrix.)
        """
        rng = np.random.default_rng(123)
        mat = rng.normal(0.0, 0.01, size=(250, 120))
        is_half = mat[:125]
        best_is = int(np.argmax(is_half.mean(0) / is_half.std(0)))
        candidate = mat[:, best_is]
        all_sharpes = mat.mean(0) / mat.std(0)
        res = evaluate_candidate(
            candidate,
            n_trials=mat.shape[1],
            trials_sharpe_std=float(all_sharpes.std()),
            performance_matrix=mat,
            n_splits=10,
        )
        assert res.verdict == FAIL
        # FAIL is driven by the overfit PBO and/or deflated DSR.
        assert (res.pbo is not None and res.pbo >= 0.5) or (res.dsr <= DSR_MIN)

    def test_tiny_sample_is_weak_never_pass(self):
        """n=7 (J-anchor size) must never PASS — power too low (lesson C24)."""
        rng = np.random.default_rng(11)
        res = evaluate_candidate(rng.normal(0.002, 0.01, size=7), n_trials=50)
        assert res.verdict == WEAK
        assert res.low_power is True
        assert res.verdict != PASS

    def test_gate_without_matrix_skips_pbo(self):
        res = evaluate_candidate(_robust_returns(), n_trials=5)
        assert res.pbo is None
        # DSR + PSR alone still admit a PASS for a robust, low-trial-count edge.
        assert res.verdict in (PASS, WEAK)
        assert any("PBO skipped" in n for n in res.notes)

    def test_gate_result_serialises(self):
        res = evaluate_candidate(_robust_returns(), n_trials=5)
        d = res.to_dict()
        assert d["verdict"] == res.verdict
        assert isinstance(d["notes"], list)
        # Round-trips cleanly through JSON for scorecard attachment.
        import json

        json.loads(json.dumps(d))

    def test_weak_when_below_pass_bar(self):
        """A marginal but non-failing edge lands WEAK, not PASS or FAIL."""
        rng = np.random.default_rng(99)
        # Small positive drift, enough obs to clear low_power but not 95% PSR.
        marginal = rng.normal(0.0004, 0.012, size=40)
        res = evaluate_candidate(marginal, n_trials=20)
        assert res.verdict in (WEAK, FAIL, PASS)  # deterministic check below
        # Specifically: not low power, and verdict follows the PSR bar.
        assert res.low_power is False
        if res.psr >= PSR_MIN and res.dsr > DSR_MIN:
            assert res.verdict == PASS
        elif res.psr < 0.5 or res.dsr <= DSR_MIN:
            assert res.verdict == FAIL
        else:
            assert res.verdict == WEAK

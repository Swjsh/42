"""Probability of Backtest Overfitting (PBO) via CSCV.

Statistical promotion rigor for Project Gamma — Phase 2c. Complements the
Deflated Sharpe Ratio: where DSR asks "is this one strategy's Sharpe real after
N trials?", PBO asks the population question "across the whole search, how often
does the configuration that looked BEST in-sample fail to stay above median
out-of-sample?". A high PBO means the selection procedure itself is overfitting
— the IS winner is, more likely than not, an OOS also-ran.

Method — Combinatorially-Symmetric Cross-Validation (CSCV)
----------------------------------------------------------
Reference
    Bailey, D. H., Borwein, J., Lopez de Prado, M. and Zhu, Q. J. (2014).
    "The Probability of Backtest Overfitting."  Journal of Computational
    Finance.  SSRN: https://ssrn.com/abstract=2326253

Given a performance matrix M of shape (T, N) — T time slices (rows) by N trials
/ strategy configurations (columns), holding a per-slice performance statistic
(e.g. Sharpe or mean return of each config within that slice):

    1. Split the T rows into S disjoint, equal contiguous sub-slices
       (S even, e.g. 16). Enumerate every way to choose S/2 of them as the
       in-sample (IS) set J; the complementary S/2 form the out-of-sample (OOS)
       set J_bar. There are C(S, S/2) such symmetric combinations.
    2. For each combination:
         - aggregate each column over the IS rows -> pick n* = argmax (best IS
           config),
         - aggregate each column over the OOS rows -> compute the OOS rank of
           that same config n*,
         - convert the OOS rank to a relative rank w in (0, 1] and a logit
           lambda = ln( w / (1 - w) ).
    3. PBO = fraction of combinations whose best-IS config lands at or below the
       OOS median (lambda <= 0). Equivalently, the probability mass of the logit
       distribution at/below zero.

PBO in [0, 1]; lower is better. The conventional decision line is PBO < 0.5
(the IS winner beats the OOS median more often than not).

CAVEAT — small samples / few trials
-----------------------------------
CSCV needs enough independent time slices AND enough trials to be meaningful.
With Gamma's tiny immutable J-anchor set (3 winners / 4 losers) there is neither
the row count to split into S sub-slices nor a trial population to rank — PBO is
NOT applicable to the anchors and will refuse (raise) rather than emit a
misleading number. It is intended for the Kitchen's MANY-candidate matrices.
See lesson C24 (anchors are exceptional one-offs, not a population).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations

import numpy as np


@dataclass(frozen=True)
class PBOResult:
    """Probability of Backtest Overfitting outcome (immutable)."""

    pbo: float                 # P(best-IS config <= OOS median), in [0, 1]
    n_trials: int              # number of configs (columns) compared
    n_splits: int              # S — number of contiguous sub-slices
    n_combinations: int        # C(S, S/2) symmetric IS/OOS partitions evaluated
    logits: tuple              # per-combination logit lambda of the IS winner
    median_oos_rank: float     # mean OOS relative-rank of IS winners (diagnostic)


def _aggregate(matrix: np.ndarray) -> np.ndarray:
    """Per-column performance aggregate over the supplied rows (mean)."""
    return np.nanmean(matrix, axis=0)


def probability_of_backtest_overfitting(
    performance_matrix,
    n_splits: int = 16,
) -> PBOResult:
    """Compute PBO from a (T, N) performance matrix via CSCV.

    Parameters
    ----------
    performance_matrix:
        2-D array-like of shape (T, N): T time slices (rows) by N trials /
        strategy configurations (columns). Entry [t, n] is config n's
        performance statistic within slice t (Sharpe, mean return, etc.).
        Higher = better. Must have N >= 2 columns (something to rank) and
        enough rows to split into ``n_splits`` sub-slices.
    n_splits:
        S — number of disjoint contiguous sub-slices to partition the rows
        into. Must be even (symmetric IS/OOS halves) and >= 2. The number of
        symmetric combinations evaluated is C(S, S/2); 16 gives 12 870 and is
        the value used in the original paper. Reduce for small T.

    Returns
    -------
    PBOResult

    Raises
    ------
    ValueError
        If the matrix is not 2-D, has < 2 trials, ``n_splits`` is not an even
        integer >= 2, or there are fewer rows than ``n_splits`` (cannot form the
        sub-slices). The refusal is deliberate — emitting a PBO from an
        ill-posed split would be misleading (see module CAVEAT).
    """
    mat = np.asarray(performance_matrix, dtype=float)
    if mat.ndim != 2:
        raise ValueError("performance_matrix must be 2-D (T slices x N trials).")
    t_rows, n_trials = mat.shape
    if n_trials < 2:
        raise ValueError("PBO needs at least 2 trials (columns) to rank.")
    if n_splits < 2 or n_splits % 2 != 0:
        raise ValueError("n_splits must be an even integer >= 2.")
    if t_rows < n_splits:
        raise ValueError(
            f"Need at least n_splits={n_splits} rows to form sub-slices; "
            f"got {t_rows}. Use fewer splits or a longer time series."
        )

    # Partition rows into S contiguous, (near-)equal sub-slices. np.array_split
    # tolerates T not divisible by S by making the first chunks one longer.
    row_index = np.arange(t_rows)
    slice_groups = [g for g in np.array_split(row_index, n_splits)]
    half = n_splits // 2

    logits: list[float] = []
    oos_relative_ranks: list[float] = []

    # Enumerate every symmetric split: choose `half` sub-slices as IS, the rest
    # are OOS. Symmetry (evaluating both J and its complement across the full
    # enumeration) is what makes the procedure unbiased.
    for is_groups in combinations(range(n_splits), half):
        is_set = set(is_groups)
        is_rows = np.concatenate([slice_groups[i] for i in range(n_splits) if i in is_set])
        oos_rows = np.concatenate([slice_groups[i] for i in range(n_splits) if i not in is_set])

        is_perf = _aggregate(mat[is_rows, :])
        oos_perf = _aggregate(mat[oos_rows, :])

        # Best config in-sample.
        n_star = int(np.nanargmax(is_perf))

        # OOS rank of that config. rank 1 = worst, n_trials = best.
        # Use 'min' ties so duplicated values share the lowest rank.
        order = np.argsort(np.argsort(oos_perf, kind="stable"), kind="stable")
        # order[n] in [0, n_trials-1]; +1 -> rank in [1, n_trials].
        rank = float(order[n_star]) + 1.0

        # Relative rank w in (0, 1]; map to logit. Clamp away from {0,1} so the
        # logit stays finite at the extremes.
        w = rank / (n_trials + 1.0)
        w = min(max(w, 1e-6), 1.0 - 1e-6)
        lam = math.log(w / (1.0 - w))
        logits.append(lam)
        oos_relative_ranks.append(w)

    logits_arr = np.asarray(logits, dtype=float)
    # PBO = fraction of IS winners that land at or below the OOS median
    # (logit <= 0  <=>  relative rank <= 0.5).
    pbo = float(np.mean(logits_arr <= 0.0))

    return PBOResult(
        pbo=pbo,
        n_trials=int(n_trials),
        n_splits=int(n_splits),
        n_combinations=int(len(logits)),
        logits=tuple(logits),
        median_oos_rank=float(np.mean(oos_relative_ranks)),
    )

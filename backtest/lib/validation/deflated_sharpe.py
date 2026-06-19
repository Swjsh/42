"""Deflated Sharpe Ratio (DSR) and Probabilistic Sharpe Ratio (PSR).

Statistical promotion rigor for Project Gamma — Phase 2c. The Kitchen generates
MANY candidate strategies, so an undeflated Sharpe (or win-rate) is statistically
meaningless: the best of N random trials looks "good" by selection alone
(multiple-testing / selection bias). These metrics correct for that.

References
----------
Bailey, D. H. and Lopez de Prado, M. (2014).
    "The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest
    Overfitting and Non-Normality."  Journal of Portfolio Management 40 (5).
    SSRN: https://ssrn.com/abstract=2460551

Bailey, D. H. and Lopez de Prado, M. (2012).
    "The Sharpe Ratio Efficient Frontier."  Journal of Risk 15 (2).
    (Origin of the Probabilistic Sharpe Ratio.)
    SSRN: https://ssrn.com/abstract=1821643

Key formulas
------------
Probabilistic Sharpe Ratio — probability that the TRUE Sharpe exceeds a
benchmark Sharpe given a finite, possibly non-normal sample::

    PSR(SR*) = Phi( (SR_hat - SR*) * sqrt(n - 1)
                    / sqrt(1 - skew*SR_hat + ((kurt - 1)/4)*SR_hat^2) )

    where Phi is the standard-normal CDF, SR_hat the observed Sharpe,
    n the number of return observations, skew/kurt the sample skewness and
    kurtosis (kurt is the *non-excess* / Pearson kurtosis; a normal dist = 3).

Deflated Sharpe Ratio — PSR evaluated against a benchmark Sharpe that is the
*expected maximum* Sharpe across N independent trials (so a strategy is only
credited for beating what selection-of-the-best would have produced by luck)::

    SR_0 = sqrt(Var(SR_trials)) * ( (1 - gamma) * Phi^-1(1 - 1/N)
                                    + gamma * Phi^-1(1 - 1/(N*e)) )

    DSR = PSR(SR_0)

    where gamma is the Euler-Mascheroni constant (~0.5772), e is Euler's number,
    Phi^-1 the standard-normal inverse-CDF (ppf), and Var(SR_trials) the variance
    of the Sharpe estimates across the N trials. When the per-trial variance is
    unknown a conservative default is used (see ``deflated_sharpe_ratio``).

Convention
----------
All Sharpe inputs/outputs are in the SAME period units as ``returns`` (i.e. NOT
annualised). DSR/PSR are probabilities in [0, 1]; the de-facto significance line
is 0.95 (i.e. 95% confidence the skill is real, not a selection artefact).

CAVEAT — small samples (read before using on Gamma's J-anchors)
---------------------------------------------------------------
DSR/PSR converge to a normal approximation and are only trustworthy with a
reasonable number of return observations (rule of thumb n >= 20-30). Gamma's
immutable J-anchor set is 3 winners / 4 losers (n = 7). At that size these
statistics have very low power and WIDE error — treat them as advisory colour,
never as a hard gate (see lesson C24: anchors are exceptional one-offs, not a
representative population). ``probabilistic_sharpe_ratio`` emits ``low_power``
in its result when n is below ``MIN_RELIABLE_OBS``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import stats

# Euler-Mascheroni constant — appears in the expected-maximum-of-N-Gaussians
# approximation used by the DSR benchmark Sharpe SR_0.
EULER_MASCHERONI = 0.5772156649015329

# Below this many return observations the normal approximation underlying
# PSR/DSR is unreliable; results are flagged low_power. (Bailey & LdP note the
# estimators are asymptotic; ~20-30 obs is the common practitioner floor.)
MIN_RELIABLE_OBS = 20


@dataclass(frozen=True)
class PSRResult:
    """Probabilistic Sharpe Ratio outcome (immutable)."""

    psr: float                 # P(true Sharpe > benchmark), in [0, 1]
    sharpe: float              # observed (sample) Sharpe, period units
    sharpe_benchmark: float    # benchmark Sharpe tested against
    n_obs: int                 # number of return observations used
    skew: float                # sample skewness of returns
    kurtosis: float            # sample (non-excess / Pearson) kurtosis
    low_power: bool            # True when n_obs < MIN_RELIABLE_OBS


@dataclass(frozen=True)
class DSRResult:
    """Deflated Sharpe Ratio outcome (immutable)."""

    dsr: float                 # deflated Sharpe probability, in [0, 1]
    sharpe: float              # observed (sample) Sharpe, period units
    sharpe_benchmark: float    # SR_0 (expected max Sharpe across n_trials)
    n_trials: int              # number of independent trials deflated for
    n_obs: int                 # number of return observations used
    skew: float                # sample skewness of returns
    kurtosis: float            # sample (non-excess / Pearson) kurtosis
    trials_sharpe_std: float   # std of per-trial Sharpe used to build SR_0
    low_power: bool            # True when n_obs < MIN_RELIABLE_OBS


def _moments(returns: np.ndarray) -> tuple[float, float, float, float]:
    """Return (sharpe, std_of_returns, skew, pearson_kurtosis).

    Sharpe is mean/std of the supplied per-period returns (excess returns should
    be passed if a non-zero risk-free is desired). Std uses the population
    estimator (ddof=0), matching Bailey & Lopez de Prado's derivation.
    """
    mu = float(np.mean(returns))
    sigma = float(np.std(returns, ddof=0))
    if sigma == 0.0 or not math.isfinite(sigma):
        raise ValueError(
            "Return series has zero or non-finite volatility; Sharpe undefined."
        )
    sharpe = mu / sigma
    # scipy skew/kurtosis are sample moments; fisher=False gives Pearson
    # kurtosis (normal == 3.0) which is what the PSR formula expects.
    skew = float(stats.skew(returns, bias=True))
    kurt = float(stats.kurtosis(returns, fisher=False, bias=True))
    return sharpe, sigma, skew, kurt


def probabilistic_sharpe_ratio(
    sharpe: float,
    n_obs: int,
    skew: float,
    kurtosis: float,
    sharpe_benchmark: float = 0.0,
) -> PSRResult:
    """Probabilistic Sharpe Ratio: P(true Sharpe > ``sharpe_benchmark``).

    Parameters
    ----------
    sharpe:
        Observed (sample) Sharpe ratio, in the same period units throughout
        (NOT annualised).
    n_obs:
        Number of return observations the Sharpe was computed from.
    skew:
        Sample skewness of the returns.
    kurtosis:
        Sample *non-excess* (Pearson) kurtosis of the returns; a normal
        distribution has kurtosis 3.0. (Pass ``excess_kurtosis + 3`` if you
        only have excess kurtosis.)
    sharpe_benchmark:
        Benchmark Sharpe to test against. 0.0 asks "is the strategy better than
        nothing?"; for DSR this is set to SR_0 (expected max across trials).

    Returns
    -------
    PSRResult

    Notes
    -----
    Implements eq. (3) of Bailey & Lopez de Prado (SSRN 2460551). The estimator
    is asymptotic — see module CAVEAT on small samples. ``low_power`` is set
    when ``n_obs < MIN_RELIABLE_OBS``.
    """
    if n_obs < 2:
        raise ValueError("probabilistic_sharpe_ratio requires n_obs >= 2.")

    # Denominator: standard error of the Sharpe estimator under non-normality.
    # Var(SR_hat) ~ (1 - skew*SR + ((kurt-1)/4)*SR^2) / (n - 1)
    variance_term = (
        1.0
        - skew * sharpe
        + ((kurtosis - 1.0) / 4.0) * (sharpe ** 2)
    )
    # Numerical floor: with extreme skew/kurtosis the term can go <= 0, which is
    # outside the model's validity. Clamp to a tiny positive so we return a
    # saturated (0/1) probability rather than NaN.
    if variance_term <= 0.0 or not math.isfinite(variance_term):
        variance_term = 1e-12

    numerator = (sharpe - sharpe_benchmark) * math.sqrt(n_obs - 1)
    z = numerator / math.sqrt(variance_term)
    psr = float(stats.norm.cdf(z))

    return PSRResult(
        psr=psr,
        sharpe=float(sharpe),
        sharpe_benchmark=float(sharpe_benchmark),
        n_obs=int(n_obs),
        skew=float(skew),
        kurtosis=float(kurtosis),
        low_power=bool(n_obs < MIN_RELIABLE_OBS),
    )


def expected_max_sharpe(
    trials_sharpe_std: float,
    n_trials: int,
) -> float:
    """Expected maximum of ``n_trials`` independent Sharpe estimates: SR_0.

    This is the benchmark a candidate must beat to earn a non-trivial DSR — i.e.
    "how good would the BEST of N random strategies look by luck alone?".

    SR_0 = std * [ (1-gamma)*Z(1 - 1/N) + gamma*Z(1 - 1/(N*e)) ]

    where Z = Phi^-1 (standard-normal ppf), gamma = Euler-Mascheroni.
    Reference: Bailey & Lopez de Prado (SSRN 2460551), eq. (5).

    With a single trial (``n_trials <= 1``) there is no selection to correct
    for, so SR_0 = 0 (DSR reduces to PSR against a zero benchmark).
    """
    if n_trials <= 1:
        return 0.0
    if trials_sharpe_std <= 0.0 or not math.isfinite(trials_sharpe_std):
        # No dispersion across trials -> no inflation from selection.
        return 0.0

    n = float(n_trials)
    z1 = stats.norm.ppf(1.0 - 1.0 / n)
    z2 = stats.norm.ppf(1.0 - 1.0 / (n * math.e))
    sr0 = trials_sharpe_std * (
        (1.0 - EULER_MASCHERONI) * z1 + EULER_MASCHERONI * z2
    )
    return float(sr0)


def deflated_sharpe_ratio(
    returns,
    n_trials: int,
    trials_sharpe_std: float | None = None,
    sharpe: float | None = None,
) -> DSRResult:
    """Deflated Sharpe Ratio for a candidate strategy's return stream.

    Deflates the observed Sharpe for (a) the number of independent trials
    ``n_trials`` that were searched (selection bias) and (b) the skew/kurtosis
    of ``returns`` (non-normality), returning the probability the strategy's
    TRUE Sharpe beats the expected-best-of-N benchmark SR_0.

    Parameters
    ----------
    returns:
        1-D array-like of per-period returns for the candidate. Skew, kurtosis
        and (unless overridden) the observed Sharpe and number of observations
        are derived from this.
    n_trials:
        Number of independent strategy configurations tested while searching
        (e.g. Kitchen candidates / parameter combinations). Drives SR_0.
    trials_sharpe_std:
        Standard deviation of the Sharpe estimates ACROSS the ``n_trials``. If
        omitted, a conservative proxy is used: the standard error of THIS
        strategy's Sharpe, sqrt(Var(SR_hat)). This typically *understates* the
        true cross-trial dispersion (hence overstates DSR), so supply the real
        value when available. Documented limitation.
    sharpe:
        Optionally supply a pre-computed observed Sharpe (period units). If
        omitted it is computed as mean/std of ``returns``.

    Returns
    -------
    DSRResult

    Notes
    -----
    Reference: Bailey & Lopez de Prado (SSRN 2460551). Asymptotic — see module
    CAVEAT on small samples (Gamma's J-anchors are n=7: low power).
    """
    arr = np.asarray(returns, dtype=float).ravel()
    n_obs = int(arr.size)
    if n_obs < 2:
        raise ValueError("deflated_sharpe_ratio requires at least 2 returns.")
    if n_trials < 1:
        raise ValueError("n_trials must be >= 1.")

    obs_sharpe, _sigma, skew, kurt = _moments(arr)
    if sharpe is not None:
        obs_sharpe = float(sharpe)

    # Conservative fallback for cross-trial Sharpe dispersion: the standard
    # error of the observed Sharpe itself. (See parameter docstring.)
    if trials_sharpe_std is None:
        variance_term = (
            1.0
            - skew * obs_sharpe
            + ((kurt - 1.0) / 4.0) * (obs_sharpe ** 2)
        )
        if variance_term <= 0.0 or not math.isfinite(variance_term):
            variance_term = 1e-12
        trials_sharpe_std = math.sqrt(variance_term / (n_obs - 1))

    sr0 = expected_max_sharpe(trials_sharpe_std, n_trials)

    psr = probabilistic_sharpe_ratio(
        sharpe=obs_sharpe,
        n_obs=n_obs,
        skew=skew,
        kurtosis=kurt,
        sharpe_benchmark=sr0,
    )

    return DSRResult(
        dsr=psr.psr,
        sharpe=obs_sharpe,
        sharpe_benchmark=sr0,
        n_trials=int(n_trials),
        n_obs=n_obs,
        skew=skew,
        kurtosis=kurt,
        trials_sharpe_std=float(trials_sharpe_std),
        low_power=bool(n_obs < MIN_RELIABLE_OBS),
    )

"""Statistical promotion-rigor toolkit (Project Gamma — blueprint Phase 2c).

The Kitchen generates MANY candidate strategies, so a raw Sharpe / win-rate is
statistically meaningless (multiple-testing / selection bias). This package
provides the peer-reviewed metrics that gate overfitting:

    deflated_sharpe_ratio / probabilistic_sharpe_ratio
        Bailey & Lopez de Prado (SSRN 2460551) — deflate an observed Sharpe for
        the number of trials searched and for return skew/kurtosis.

    probability_of_backtest_overfitting
        Bailey, Borwein, Lopez de Prado & Zhu (SSRN 2326253) — CSCV estimate of
        how often the in-sample-best config fails OOS.

    evaluate_candidate
        Advisory PASS/WEAK/FAIL verdict combining the above.

ADVISORY ONLY this wave — not wired into the live promotion gate (that is a
doctrine change for J; see ``gate.py`` "How to wire in later"). Small-sample
caveat: Gamma's J-anchors are n=7 and have very low power — never use these as a
hard gate on the anchor set (lesson C24).
"""

from __future__ import annotations

from .deflated_sharpe import (
    MIN_RELIABLE_OBS,
    DSRResult,
    PSRResult,
    deflated_sharpe_ratio,
    expected_max_sharpe,
    probabilistic_sharpe_ratio,
)
from .gate import (
    DSR_MIN,
    FAIL,
    PASS,
    PBO_MAX,
    PSR_MIN,
    WEAK,
    GateResult,
    evaluate_candidate,
)
from .pbo import PBOResult, probability_of_backtest_overfitting

__all__ = [
    # deflated_sharpe
    "deflated_sharpe_ratio",
    "probabilistic_sharpe_ratio",
    "expected_max_sharpe",
    "DSRResult",
    "PSRResult",
    "MIN_RELIABLE_OBS",
    # pbo
    "probability_of_backtest_overfitting",
    "PBOResult",
    # gate
    "evaluate_candidate",
    "GateResult",
    "PASS",
    "WEAK",
    "FAIL",
    "DSR_MIN",
    "PSR_MIN",
    "PBO_MAX",
]

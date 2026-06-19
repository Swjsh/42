"""Advisory promotion-rigor gate: combine DSR + PSR + PBO into one verdict.

Statistical promotion rigor for Project Gamma — Phase 2c. This is the thin
decision layer over ``deflated_sharpe`` and ``pbo``. Given a candidate's return
stream, the number of trials searched, and (optionally) a CSCV performance
matrix, it returns a single advisory verdict — PASS / WEAK / FAIL — plus the
underlying numbers and human-readable notes.

ADVISORY ONLY. This module is deliberately NOT wired into the live promotion
gate. It is a signal for the Kitchen reviewer and J to consult; flipping it into
a hard gate is a doctrine change for J (Rule 9 — no mid-session rule changes;
doctrine changes are weekend/after-hours, in writing). See "How to wire in
later" at the bottom of this docstring.

Thresholds (tunable — these are documented defaults, not law)
-------------------------------------------------------------
    DSR_MIN  = 0.0   Deflated Sharpe probability must be > 0. After deflating
                     for N trials, the strategy's TRUE Sharpe should still beat
                     the expected-best-of-N benchmark with > 50% probability.
                     (DSR is itself a probability; > 0.5 is "more likely than
                     not". We keep the floor at strictly-positive DSR and lean
                     on PSR for the stronger confidence bar.)
    PSR_MIN  = 0.95  Probabilistic Sharpe (vs zero benchmark) — 95% confidence
                     the true Sharpe is positive. This is the standard
                     significance line in Bailey & Lopez de Prado.
    PBO_MAX  = 0.5   Probability of Backtest Overfitting must be < 0.5 — the
                     in-sample winner should beat the OOS median more often than
                     not.

Verdict logic
-------------
    PASS  — PSR >= PSR_MIN  AND  DSR > DSR_MIN  AND  (PBO is None OR PBO < PBO_MAX)
    FAIL  — PSR < 0.5  OR  DSR <= DSR_MIN  OR  (PBO is not None AND PBO >= PBO_MAX)
    WEAK  — anything in between (e.g. positive but sub-0.95 PSR), OR any result
            flagged ``low_power`` (too few observations to trust — never PASS on
            low power).

References: SSRN 2460551 (DSR/PSR), SSRN 2326253 (PBO).

CAVEAT — small samples
----------------------
With a tiny sample (Gamma's J-anchors are n=7) the inputs have very low
statistical power; ``low_power`` propagates and caps the verdict at WEAK so the
gate can never green-light on an underpowered sample. PBO is simply skipped when
no performance matrix is supplied. Do not over-read a WEAK/low-power result —
absence of significance at n=7 is expected, not damning (lesson C24).

How to wire into the promotion gate later (NOT done this wave)
--------------------------------------------------------------
1. At the point a candidate is considered for PROMOTE (e.g. the Kitchen reviewer
   or ``analysis/recommendations/{rule_id}.json`` ratification path), build the
   candidate's per-trade (or per-period) return array from real-fills, and count
   how many configurations were searched to produce it (n_trials).
2. If a CSCV matrix is available (per-slice performance of every searched
   config), pass it for PBO; otherwise leave it None (DSR/PSR still apply).
3. Call ``evaluate_candidate(...)`` and attach the returned dict to the
   candidate's scorecard as an ADVISORY field first — observe it alongside the
   existing OOS/WF/anchor gates for a few promotions.
4. Only after J ratifies promoting it to a HARD gate: add ``verdict != "FAIL"``
   (or a stricter ``verdict == "PASS"``) to the auto-ratify boolean in the
   promotion logic, alongside the existing OOS_positive / WF>=0.70 /
   sub_window_stable / anchor_no_regression conditions. Respect MIN_RELIABLE_OBS
   — never let it block when ``low_power`` is True unless J says so.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Optional

from .deflated_sharpe import MIN_RELIABLE_OBS, deflated_sharpe_ratio
from .pbo import probability_of_backtest_overfitting

# --- Tunable thresholds (documented defaults; see module docstring) ----------
DSR_MIN = 0.0    # deflated Sharpe probability floor (strictly positive)
PSR_MIN = 0.95   # probabilistic Sharpe confidence for PASS
PBO_MAX = 0.5    # probability-of-overfitting ceiling for PASS

# Verdict labels.
PASS = "PASS"
WEAK = "WEAK"
FAIL = "FAIL"


@dataclass(frozen=True)
class GateResult:
    """Advisory promotion-rigor verdict (immutable)."""

    verdict: str                 # PASS | WEAK | FAIL
    dsr: float                   # deflated Sharpe probability
    psr: float                   # probabilistic Sharpe (vs zero benchmark)
    pbo: Optional[float]         # probability of overfitting, or None if no matrix
    n_obs: int                   # number of return observations
    n_trials: int                # number of trials searched
    low_power: bool              # True when sample too small to trust
    notes: tuple                 # human-readable explanation lines

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (notes as a list) for JSON scorecards."""
        d = asdict(self)
        d["notes"] = list(self.notes)
        return d


def evaluate_candidate(
    returns,
    n_trials: int,
    performance_matrix=None,
    trials_sharpe_std: float | None = None,
    n_splits: int = 16,
    dsr_min: float = DSR_MIN,
    psr_min: float = PSR_MIN,
    pbo_max: float = PBO_MAX,
) -> GateResult:
    """Advisory PASS/WEAK/FAIL verdict for one candidate strategy.

    Parameters
    ----------
    returns:
        1-D array-like of the candidate's per-period (or per-trade) returns.
    n_trials:
        Number of independent configurations searched to find this candidate
        (drives the DSR deflation). Use a realistic count of the Kitchen /
        parameter trials that produced it.
    performance_matrix:
        Optional (T, N) per-slice performance matrix for CSCV PBO. When None,
        PBO is reported as None and the verdict rests on DSR + PSR only.
    trials_sharpe_std:
        Optional std of Sharpe across the ``n_trials`` (improves DSR accuracy;
        see ``deflated_sharpe_ratio``).
    n_splits:
        CSCV sub-slice count for PBO (even, >= 2). Ignored when no matrix.
    dsr_min, psr_min, pbo_max:
        Threshold overrides (default to the module constants).

    Returns
    -------
    GateResult
    """
    notes: list[str] = []

    # --- DSR + PSR (always computed) -----------------------------------------
    # PSR vs a zero benchmark is recovered by deflating with n_trials=1 (SR_0=0).
    psr_res = deflated_sharpe_ratio(returns, n_trials=1)
    dsr_res = deflated_sharpe_ratio(
        returns, n_trials=n_trials, trials_sharpe_std=trials_sharpe_std
    )
    psr_val = psr_res.dsr  # deflate-with-1-trial == PSR(benchmark=0)
    dsr_val = dsr_res.dsr
    n_obs = dsr_res.n_obs
    low_power = bool(dsr_res.low_power)

    notes.append(
        f"PSR(vs 0)={psr_val:.4f} on n={n_obs} obs "
        f"(Sharpe={dsr_res.sharpe:.3f}, skew={dsr_res.skew:.2f}, "
        f"kurt={dsr_res.kurtosis:.2f})."
    )
    notes.append(
        f"DSR deflated for n_trials={n_trials} "
        f"(SR_0={dsr_res.sharpe_benchmark:.3f}) = {dsr_val:.4f}."
    )

    # --- PBO (only if a matrix is supplied) ----------------------------------
    pbo_val: Optional[float] = None
    if performance_matrix is not None:
        try:
            pbo_res = probability_of_backtest_overfitting(
                performance_matrix, n_splits=n_splits
            )
            pbo_val = pbo_res.pbo
            notes.append(
                f"PBO={pbo_val:.4f} via CSCV "
                f"(N={pbo_res.n_trials} trials, S={pbo_res.n_splits} splits, "
                f"{pbo_res.n_combinations} partitions)."
            )
        except ValueError as exc:
            notes.append(f"PBO skipped (ill-posed matrix): {exc}")
            pbo_val = None
    else:
        notes.append("PBO skipped (no performance matrix supplied).")

    # --- Combine into a verdict ----------------------------------------------
    pbo_ok = (pbo_val is None) or (pbo_val < pbo_max)
    pbo_bad = (pbo_val is not None) and (pbo_val >= pbo_max)

    hard_fail = (psr_val < 0.5) or (dsr_val <= dsr_min) or pbo_bad
    full_pass = (psr_val >= psr_min) and (dsr_val > dsr_min) and pbo_ok

    if hard_fail:
        verdict = FAIL
        notes.append(
            "Verdict FAIL: failed a hard floor "
            "(PSR<0.5, or DSR<=floor, or PBO>=ceiling)."
        )
    elif low_power:
        # Never PASS on an underpowered sample — cap at WEAK.
        verdict = WEAK
        notes.append(
            f"Verdict WEAK: sample too small (n={n_obs} < "
            f"MIN_RELIABLE_OBS={MIN_RELIABLE_OBS}); "
            "metrics lack power — advisory only (lesson C24)."
        )
    elif full_pass:
        verdict = PASS
        notes.append(
            f"Verdict PASS: PSR>={psr_min}, DSR>{dsr_min}, "
            "and PBO under ceiling (or not tested)."
        )
    else:
        verdict = WEAK
        notes.append(
            "Verdict WEAK: positive but below the PASS confidence bar "
            f"(need PSR>={psr_min})."
        )

    return GateResult(
        verdict=verdict,
        dsr=float(dsr_val),
        psr=float(psr_val),
        pbo=(None if pbo_val is None else float(pbo_val)),
        n_obs=int(n_obs),
        n_trials=int(n_trials),
        low_power=low_power,
        notes=tuple(notes),
    )

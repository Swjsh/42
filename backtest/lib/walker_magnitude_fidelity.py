"""walker_magnitude_fidelity.py -- the magnitude companion to sign-agreement checks.

Filed under WALKER-MAGNITUDE-BIAS-VS-SIGN-FIDELITY (2026-09-02, harness fidelity, HIGH):
every exit-walk study in this repo validated its harness on SIGN AGREEMENT alone. The PDT
counterfactual proved that is not sufficient -- its anchor set cleared 95.35% sign agreement
(n=43) while replaying to -$2,201.60 against an actual -$538.00, a ~4x aggregate-negative
bias. `whole_engine_null.py`'s own V9 already computed the metrics this module now shares
(see its retired-in-place `_magnitude_fidelity`, which explicitly refused to set a PASS/FAIL
bar: "any threshold chosen now would be fitted to values already seen; a magnitude bar needs
pre-registration"). This module IS that pre-registration, derived from
`analysis/harness-fidelity/WALKER-MAGNITUDE-2026-09-03.json` (see that file's
`criterion_derivation` block for the exact numbers the threshold was set against) -- built by
`backtest/tools/walker_fidelity.py`.

CONTRACT: this module NEVER decides a study's own PASS/FAIL/WITHHELD verdict. Every existing
verdict in this repo is gated on SIGN agreement only (`SIGN_AGREEMENT_MIN` /
`HARNESS_SIGN_AGREEMENT_BAR` in the calling studies) -- that gate is untouched. What this
module adds is a SECOND, INDEPENDENT read (`magnitude_fidelity_verdict`) that a caller reports
ALONGSIDE the sign verdict, never in place of it. A study whose sign check PASSES but whose
magnitude check FAILS is directionally trustworthy and dollar-suspect -- exactly the state the
PDT counterfactual was actually in, undisclosed until this filing.

$0, deterministic, pure functions -- no I/O, no network, no mutation of inputs.
"""
from __future__ import annotations

import statistics as stt
from typing import Optional, Sequence

# --- THE CRITERION (derived from data -- see analysis/harness-fidelity/WALKER-MAGNITUDE-2026-09-03.json) ---
#
# N floor: matches this repo's standing "n>=20" decision floor used elsewhere (e.g. the
# recency-qty-clamp prereg's own day-count bar) -- not invented fresh for this module.
#
# AGGREGATE_RATIO_TOLERANCE / MEDIAN_ABS_ERROR_DOLLARS_MAX: anchored to the best-attested
# walker application in this repo, whole_engine_null.py's V9 (n=121, 2026-09-02 run):
# aggregate_ratio 0.6452, median_abs_error_dollars 15.00. The tolerance band is set GENEROUSLY
# above V9's own numbers (so a walker this repo already treats as "reliable enough to gate a
# frozen prereg on" clears the bar without being fitted flush to it) -- 0.40 leaves |0.6452-1|
# = 0.3548 inside the band with room, and $40 leaves V9's $15 median comfortably inside. The
# PDT counterfactual's anchor set (aggregate_ratio 2201.60/538.00 = 4.09, median $32.40) fails
# on aggregate_ratio alone by a wide margin (|4.09-1| = 3.09 >> 0.40) even though its median
# error alone would pass -- which is exactly why BOTH conditions are required: a walker can
# have small per-trade errors that are all one-directional, and the aggregate is where that
# shows up.
MAGNITUDE_FIDELITY_MIN_N = 20
AGGREGATE_RATIO_TOLERANCE = 0.40
MEDIAN_ABS_ERROR_DOLLARS_MAX = 40.0


def magnitude_fidelity(pairs: Sequence[tuple[float, float]]) -> dict:
    """Dollar-level fidelity of a walk, alongside (never instead of) sign agreement.

    `pairs`: a sequence of (real_pnl, walked_pnl) tuples -- deliberately positional/untyped-key
    so either study's own row schema (whole_engine_null's real_pnl/walked_pnl,
    pdt_blocked_counterfactual's actual/replay) can feed it without a translation layer that
    itself could drift.

    `aggregate_ratio` is replay-total / actual-total: 1.00 is faithful, <1 under-reproduces the
    engine's net, >1 over-reproduces. Split winners/losers because the two sides fail
    differently and the aggregate hides which. Returns None for a ratio whose denominator is
    ~0 rather than dividing by it.
    """
    pairs = list(pairs)
    if not pairs:
        return {"n": 0}
    real = [p[0] for p in pairs]
    walk = [p[1] for p in pairs]
    errs = sorted(abs(w - a) for w, a in zip(walk, real))
    n = len(errs)

    def _ratio(num: float, den: float) -> Optional[float]:
        return round(num / den, 4) if abs(den) > 1e-9 else None

    wins = [(w, a) for w, a in zip(walk, real) if a > 0]
    loss = [(w, a) for w, a in zip(walk, real) if a < 0]
    return {
        "n": n,
        "actual_total_dollars": round(sum(real), 2),
        "replay_total_dollars": round(sum(walk), 2),
        "aggregate_ratio": _ratio(sum(walk), sum(real)),
        "total_error_dollars": round(sum(walk) - sum(real), 2),
        "mean_signed_bias_dollars": round(sum(w - a for w, a in zip(walk, real)) / n, 2),
        "median_abs_error_dollars": round(errs[n // 2], 2),
        "p90_abs_error_dollars": round(errs[min(n - 1, (9 * n) // 10)], 2),
        "max_abs_error_dollars": round(errs[-1], 2),
        "winners": {"n": len(wins), "actual": round(sum(a for _, a in wins), 2),
                    "replay": round(sum(w for w, _ in wins), 2),
                    "ratio": _ratio(sum(w for w, _ in wins), sum(a for _, a in wins))},
        "losers": {"n": len(loss), "actual": round(sum(a for _, a in loss), 2),
                   "replay": round(sum(w for w, _ in loss), 2),
                   "ratio": _ratio(sum(w for w, _ in loss), sum(a for _, a in loss))},
    }


def evaluate_magnitude_fidelity(mag: dict) -> str:
    """PASS / FAIL / INSUFFICIENT. Applied AFTER `magnitude_fidelity()` has computed the dict
    -- purely descriptive, never gates a study's own sign-based verdict (see module docstring).

    INSUFFICIENT: n below MAGNITUDE_FIDELITY_MIN_N, or a ratio/median could not be computed
    (e.g. actual_total ~= 0, a denominator this metric refuses to divide by).
    PASS: both |aggregate_ratio - 1| <= AGGREGATE_RATIO_TOLERANCE AND
          median_abs_error_dollars <= MEDIAN_ABS_ERROR_DOLLARS_MAX.
    FAIL: n is sufficient but either condition above is violated.
    """
    n = mag.get("n", 0)
    if n < MAGNITUDE_FIDELITY_MIN_N:
        return "INSUFFICIENT"
    ratio = mag.get("aggregate_ratio")
    med = mag.get("median_abs_error_dollars")
    if ratio is None or med is None:
        return "INSUFFICIENT"
    if abs(ratio - 1.0) <= AGGREGATE_RATIO_TOLERANCE and med <= MEDIAN_ABS_ERROR_DOLLARS_MAX:
        return "PASS"
    return "FAIL"


def stage_decomposition(rows: Sequence[dict], *, real_key: str, walk_key: str,
                        recorded_stage_key: str, walked_stage_key: str) -> dict:
    """Splits dollar error by whether the walker's OWN exit stage SEQUENCE matches the RECORDED
    (broker-truth) exit stage sequence, and reports mean/median error for each bucket. This is
    the diagnostic that actually localizes a magnitude defect: a walker that agrees on stage
    should be a pure pricing question (fill convention, slippage); one that disagrees on stage
    picked a DIFFERENT event entirely (e.g. fired a catastrophe stop on a bar-extreme wick the
    live 1-minute tick never saw), which is a structural defect, not a pricing one.

    WALKER-PDT-ANCHOR-FIDELITY-INPUTS fix #1 (2026-09-03): a recorded stage like
    "premium_stop+ribbon_flip" (compound label -- see exit_manager_walk.py's
    EXITMGR-STAGE-LABEL-CONFLATION note) is now compared against the walker's FULL compound
    leg-stage sequence (e.g. "tp1+trail"), not a first-token truncation on either side.
    First-token comparison was a measurement artifact (WALKER-STAGE-DISAGREE-RESIDUAL-2026-09-
    03.md Finding 0): the caller-side `walked_stage` used to carry only the LAST leg's stage
    (a single token, e.g. "trail"), so a compound recorded label's first token ("tp1") could
    never match it even when the replay fired the IDENTICAL two-leg sequence the broker
    recorded -- inflating the PDT anchor's disagree count from a true 6 rows to a mislabeled
    13. Callers must now build `walked_stage_key`'s value as the FULL "+"-joined leg sequence
    (see `pdt_blocked_counterfactual._walk_via_exit_manager`'s `walked_stage`), matching
    `recorded_stage`'s own already-compound convention (trades-enriched.jsonl's `exit_reason`).
    """
    agree, disagree = [], []
    for r in rows:
        recorded = str(r.get(recorded_stage_key) or "UNKNOWN")
        walked = str(r.get(walked_stage_key) or "UNKNOWN")
        err = abs(float(r[walk_key]) - float(r[real_key]))
        bucket = agree if recorded == walked else disagree
        bucket.append(err)

    def _stats(errs: list[float]) -> dict:
        if not errs:
            return {"n": 0, "mean_abs_error_dollars": None, "median_abs_error_dollars": None,
                    "total_abs_error_dollars": 0.0}
        return {"n": len(errs), "mean_abs_error_dollars": round(stt.mean(errs), 2),
                "median_abs_error_dollars": round(stt.median(errs), 2),
                "total_abs_error_dollars": round(sum(errs), 2)}

    a, d = _stats(agree), _stats(disagree)
    total_abs = a["total_abs_error_dollars"] + d["total_abs_error_dollars"]
    return {
        "stage_agree": a, "stage_disagree": d,
        "disagree_share_of_total_abs_error": (round(d["total_abs_error_dollars"] / total_abs, 4)
                                              if total_abs > 1e-9 else None),
    }


def side_decomposition(rows: Sequence[dict], *, real_key: str, walk_key: str,
                       side_key: str) -> dict:
    """Magnitude fidelity split by option side (C/P) -- cheap, standing diagnostic."""
    by_side: dict[str, list[tuple[float, float]]] = {}
    for r in rows:
        side = str(r.get(side_key) or "UNKNOWN")
        by_side.setdefault(side, []).append((float(r[real_key]), float(r[walk_key])))
    return {side: magnitude_fidelity(pairs) for side, pairs in sorted(by_side.items())}

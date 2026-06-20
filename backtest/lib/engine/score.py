"""engine.score — the ONE scoring entry point (Phase 1 of the shared library).

Spec: ``markdown/specs/SHARED-DECISION-LIBRARY-MIGRATION.md`` §3 "Phase 1 — Extract
scoring into ``engine/score.py``, backtest calls it (assert-agree)".

WHAT THIS WRAPS
---------------
This module is a *thin, faithful relocation* — NOT a reimplementation — of the
two scoring functions that already live in ``backtest/lib/filters.py``:

  * ``filters.evaluate_bearish_setup(ctx, ...) -> filters.SetupResult``
      the 10-filter BEARISH_REJECTION_RIDE_THE_RIBBON checklist.
  * ``filters.evaluate_bullish_setup(ctx, ...) -> filters.BullishSetupResult``
      the 11-filter BULLISH_RECLAIM_RIDE_THE_RIBBON mirror.

``score_bear`` / ``score_bull`` forward EVERY keyword straight through to those
functions and return their results unchanged — same objects, same types, byte-
identical output. There is deliberately ZERO logic here: the goal of Phase 1 is
a stable, tested *import surface* that both the backtest (now) and the live path
(Phase 3-4, via the ``engine_cli.py`` shell-out shim) call, so "does the backtest
match what trades live?" becomes true *by construction* — repeating the proven
``risk_gate.check_order`` -> ``pre_order_gate.py`` move for the scoring layer.

``score_bar`` runs BOTH sides on one ``BarContext`` and returns a frozen
``ScoreResult`` bundling the two underlying results plus the raw ``bear_score`` /
``bull_score`` and blocker lists. The orchestrator calls it as an
*assert-agree oracle* next to its existing ``evaluate_*`` calls (on by default,
opt-out via ``GAMMA_ENGINE_SCORE_ASSERT=0``), which proves the extraction is
faithful with zero behaviour change before any call site is replaced.

WHY A WRAPPER, NOT A MOVE (LEAN)
--------------------------------
The spec is explicit: *"Initially these import and call the existing
``evaluate_bearish_setup`` / ``evaluate_bullish_setup`` — zero logic change, just
a stable, tested entry point."* Re-implementing or even physically moving the
~600 lines of filter logic now would churn ``filters.py`` (and its many other
importers) for zero behaviour gain. Phase 1 adds an interface; later phases can
relocate the implementation behind that interface without touching callers.

PURITY
------
Like ``risk_gate.check_order``: no I/O, no MCP, no mutation. ``ScoreResult`` is a
frozen dataclass; ``score_bar`` reads its inputs and returns a NEW object. The
underlying ``evaluate_*`` functions are themselves pure over the ``BarContext``.

PHASES 2-4 FOLLOW (see the spec):
  * Phase 2 — ``engine/gates.py`` lifts the ~15 inline orchestrator gate blocks
    into one ordered ``evaluate_gates()`` + a ``GATE_ORDER`` declaration.
  * Phase 3 — ``engine/engine_cli.py`` stdin/stdout shim + N>=5 days of read-only
    shadow-mode alongside the live prose.
  * Phase 4 — cutover: the heartbeat consults the verdict and obeys it; the
    scoring/gate prose collapses to a thin stub + codegen kills the last drift
    vector.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Optional

from ..filters import (
    BarContext,
    BullishSetupResult,
    SetupResult,
    evaluate_bearish_setup,
    evaluate_bullish_setup,
)

__all__ = [
    "ScoreResult",
    "score_bar",
    "score_bear",
    "score_bull",
]


@dataclass(frozen=True)
class ScoreResult:
    """The deterministic scoring answer for ONE bar (both directions).

    Pure data — a frozen bundle of the two underlying ``filters`` results plus
    the headline numbers callers key off. The orchestrator uses ``bear`` /
    ``bull`` for its existing routing; the convenience scalars (``bear_score``,
    ``bull_score``, ``bear_blockers``, ``bull_blockers``) are what the
    assert-agree oracle and the parity test compare field-for-field.

    ``bull`` is ``None`` when the caller disabled the bullish side (mirrors the
    orchestrator's ``enable_bullish`` flag), exactly as ``evaluate_bullish_setup``
    is skipped there.
    """

    bear: SetupResult
    bull: Optional[BullishSetupResult]
    bear_score: int
    bull_score: Optional[int]
    bear_blockers: list = field(default_factory=list)
    bull_blockers: Optional[list] = None


def score_bear(ctx: BarContext, **kwargs) -> SetupResult:
    """Score the BEARISH setup for one bar.

    Thin pass-through to ``filters.evaluate_bearish_setup`` — every keyword is
    forwarded verbatim and the returned ``SetupResult`` is unchanged. See the
    module docstring for why this is a wrapper, not a reimplementation.

    Accepts the full ``evaluate_bearish_setup`` keyword surface (``min_triggers``,
    ``vix_soft_mode``, ``allow_one_blocker``, ``no_trade_before``,
    ``no_trade_window``, ``f9_vol_mult``, the sweep-blocker knobs,
    ``bearish_reversal_bypass``, the FHH discriminators, ...) via ``**kwargs`` so
    this entry point never drifts from the underlying signature.
    """
    return evaluate_bearish_setup(ctx, **kwargs)


def score_bull(ctx: BarContext, **kwargs) -> BullishSetupResult:
    """Score the BULLISH setup for one bar.

    Thin pass-through to ``filters.evaluate_bullish_setup`` — every keyword is
    forwarded verbatim and the returned ``BullishSetupResult`` is unchanged.
    Mirror of :func:`score_bear`.
    """
    return evaluate_bullish_setup(ctx, **kwargs)


def score_bar(
    ctx: BarContext,
    *,
    enable_bullish: bool = True,
    bear_kwargs: Optional[dict] = None,
    bull_kwargs: Optional[dict] = None,
) -> ScoreResult:
    """Score BOTH directions for one bar and bundle the results.

    The single scoring interface both the backtest (now) and the live path
    (later phases) call. It reproduces exactly what the orchestrator does at its
    scoring point: always evaluate the bear side; evaluate the bull side only
    when ``enable_bullish`` is True (else ``bull`` is None).

    Args:
        ctx: the fully-populated :class:`filters.BarContext` for the trigger bar.
        enable_bullish: when False, the bullish side is not scored (``bull`` is
            None) — mirrors the orchestrator's ``enable_bullish`` flag.
        bear_kwargs: keyword arguments forwarded to ``evaluate_bearish_setup``
            (the orchestrator's per-run bear knobs). None -> evaluate defaults.
        bull_kwargs: keyword arguments forwarded to ``evaluate_bullish_setup``.
            None -> evaluate defaults.

    Returns:
        A frozen :class:`ScoreResult`. ``bear`` is always present; ``bull`` is
        None iff ``enable_bullish`` is False.
    """
    bear = score_bear(ctx, **(bear_kwargs or {}))
    bull = score_bull(ctx, **(bull_kwargs or {})) if enable_bullish else None
    return ScoreResult(
        bear=bear,
        bull=bull,
        bear_score=bear.bear_score,
        bull_score=(bull.bull_score if bull is not None else None),
        bear_blockers=list(bear.blockers),
        bull_blockers=(list(bull.blockers) if bull is not None else None),
    )

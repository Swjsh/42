"""Gamma decision engine — the shared decision library (Phase 1: scoring).

Spec: ``docs/SHARED-DECISION-LIBRARY-MIGRATION.md``. This package is the
deterministic decision core that — over Phases 1-4 — both the BACKTEST
(``orchestrator.py`` / ``filters.py``) and the LIVE path (``heartbeat.md`` via a
thin shell-out shim, exactly like ``automation/scripts/pre_order_gate.py`` does
for risk today) will import, so "does the backtest match what trades live?"
becomes true *by construction* instead of checked by the manual ``gamma-sync``
ritual. It repeats the proven ``risk_gate.py -> pre_order_gate.py`` move
(ONE pure function, backtest delegates, live shells out) for the scoring layer.

PHASING (per the spec §3 — this package grows one parity-gated phase at a time):

  * Phase 1 (THIS PHASE) — ``score.py``: ONE stable entry point,
    ``score_bar(bear_ctx, bull_ctx, params) -> ScoreResult``, that thinly
    RE-EXPORTS / wraps the existing ``filters.evaluate_bearish_setup`` /
    ``filters.evaluate_bullish_setup``. Zero logic change — a faithful
    relocation behind a narrow interface, proven byte-identical by
    ``backtest/tests/test_engine_score_parity.py`` and an assert-agree oracle
    wired into the orchestrator's scoring point.
  * Phase 2 (THIS PHASE) — ``gates.py``: lift the 15 inline gate blocks from
    ``orchestrator.py`` (~1239-1540) into one ordered ``evaluate_gates(ctx, params)``
    + a ``GATE_ORDER`` declaration. Proven byte-identical by
    ``backtest/tests/test_engine_gates_parity.py`` and an assert-agree oracle
    wired into the orchestrator's gate point (opt-out ``GAMMA_ENGINE_GATES_ASSERT=0``).
    The prose<->GATE_ORDER presence test (``test_heartbeat_gate_intent_parity``)
    is Phase 2c.
  * Phase 3 (LATER) — ``engine_cli.py`` (stdin/stdout shim, mirror
    ``pre_order_gate.py``) + shadow-mode the verdict alongside the live prose for
    N>=5 trading days (read-only, cannot touch an order).
  * Phase 4 (LATER, conductor-driven, propose-and-ping-J) — cutover: the
    heartbeat consults the verdict and obeys it; the scoring/gate prose collapses
    to a thin "compute inputs, call, obey" stub + codegen kills the last drift
    vector.

Phase 1 is ADDITIVE and BACKTEST-ONLY: nothing here is on the live order path,
and the only consumer this phase is the backtest orchestrator (as an
assert-agree oracle). A regression cannot reach live trading.
"""

from __future__ import annotations

from .gates import (
    GATE_ORDER,
    GateBlock,
    GateContext,
    evaluate_gates,
)
from .score import (
    ScoreResult,
    score_bar,
    score_bear,
    score_bull,
)

__all__ = [
    # Phase 1 — scoring
    "ScoreResult",
    "score_bar",
    "score_bear",
    "score_bull",
    # Phase 2 — gates
    "GATE_ORDER",
    "GateBlock",
    "GateContext",
    "evaluate_gates",
]

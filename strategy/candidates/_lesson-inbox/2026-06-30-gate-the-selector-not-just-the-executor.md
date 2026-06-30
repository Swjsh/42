# Lesson candidate: a precondition gate must be honored at the SELECTOR, not only the EXECUTOR

**Date:** 2026-06-30
**Source:** conductor fire (commit 910aad7) — task_scorer recency-gate fix
**Theme fit:** C14 (dead/decorative knobs & divergent gates) + C15 (gates interact) / OP-33d (same wall every fire)

## Symptom
For ~9 consecutive after-hours conductor fires, `task_scorer` ranked
`PROMOTE-KEEPER-OOS-VALIDATION` as the #1 READY item. Every fire then spent real
budget manually re-verifying "its contender is the dead premium axis (WR ~12%)
AND recency-RED → dismiss" before moving on. The conductor was pointed at the
same wall every single fire.

## Root cause
The confirm-before-capital **recency gate was enforced at the EXECUTOR layer**
(both apply chokepoints: `contender_oos_check.assess_recency_gate` cb82456 +
`autonomy_actuator._recency_gate_clears` 8200ac3) — so a recency-RED promote
**could never ship**. But the **SELECTOR layer** (`task_scorer`, which decides
what the conductor *looks at* next) scored the queue line purely on static
metadata (priority + keywords + `status:pending`) with ZERO awareness of the
external dynamic recency state. So the selector kept proposing work the executor
would always refuse → an infinite "propose → verify → reject" waste loop, with
the rejection invisible to the ranker.

## Fix (shipped)
`task_scorer._recency_explicitly_red()` consults the SAME
`headline.edges_confirmed_on_recent` field the executor gates read, and
down-ranks a recency-gated item (`PROMOTE-KEEPER`) to `ready=false` when recency
is explicitly RED. Conservative direction: suppress ONLY on a confident explicit
RED (missing/garbled/confirmed → not suppressed) — attention-routing fails OPEN
toward surfacing, never hides work on uncertainty (the opposite of the capital
gates, which fail CLOSED — different layer, different safe direction). A parity
guard pins the selector's reader to the executor's so the field contract can't
drift (C14). Guard: `backtest/tests/test_task_scorer_recency.py` 17/17.

## Generalizable rule
**When an item's true readiness is gated by external DYNAMIC state, enforce that
gate at the SELECTION/ranking layer too — not only at the execution layer.** A
gate honored only by the executor lets the selector re-propose un-executable
work indefinitely, burning a cycle each time. The selector and executor must
read the SAME precondition (parity-pinned), and the selector's fail-direction is
fail-OPEN (surface on uncertainty) while the executor's is fail-CLOSED (don't
ship on uncertainty).

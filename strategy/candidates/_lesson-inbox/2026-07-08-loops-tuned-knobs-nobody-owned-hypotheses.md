# Loops tuned knobs; nobody owned hypothesis generation from losses

**Date:** 2026-07-08 · **Source:** J ("why doesn't Gamma think 'maybe we're stopping out too
early'? Does Gamma lack trading knowledge / proactive thinking / motivation? I need to stop
having to prompt every single step") + the Fable diagnosis the same night.

**Symptom:** J personally discovered the noise-floor/stop-too-tight defect (the 741P
stopped-then-paid trade, 40/45 winners touching −20% first) — TWICE across two days — while
the rig's 24/7 autonomy layer (kitchen, chef, conductor, analyst, grinders, ~68 scheduled
tasks) never surfaced it. The evidence sat in the broker-truth fills-ledger for two weeks.

**Root cause (architecture, NOT capability):** every autonomous loop was either a
PARAMETER-TUNER (kitchen/chef/mass-grind sweep knobs on shapes they were handed) or a
COMPLIANCE-CHECKER (analyst EOD grades rule adherence). No organ had the JOB of reading our
own fills and asking "why did the money die / what would a different mechanism have kept."
Proof it was a mission gap, not a knowledge gap: once J asked the question, the existing
machinery produced the stop-harvest matrix in 53 seconds. Secondary factors: the discovery
loops search INSIDE the frame they're handed (OP-32's known limit), and the autonomy metrics
rewarded shipped artifacts over learning-from-fills.

**Fix (shipped 2026-07-08, commit 1a463d3):** `Gamma_TradeAutopsy` (16:15 ET daily) —
`setup/scripts/trade_autopsy.py` autopsies every closed engine position: counterfactual
replays through the LIVE exit_manager on real 1-min bars → mechanism tags (stopped_then_paid /
paid_the_spike / exit_shape_cost / exit_beat_theta) → rolling detectors with n-honesty floors
→ structured hypotheses (claim + evidence + concrete tests) into hypothesis-queue.jsonl +
queue.md (conductor/chef intake) + firm-brief line. First fire re-derived the 741P finding
unprompted and emitted 3 hypotheses.

**The generalized lesson (for the L## entry):** an autonomous system is only as proactive as
the QUESTIONS its scheduled processes are pointed at. Capability + data + idle compute do NOT
combine into insight unless some fire's explicit job is "generate the hypothesis." When J has
to hand the system an insight its own data already contained, the fix is never "be smarter" —
it is a new standing consumer of that data with a hypothesis-shaped output contract
(OP-33e generalized from questions to insights).

**Guard:** `backtest/tests/test_trade_autopsy.py` (10/10; detectors have fires + below-threshold
cases so a vacuous always/never-fires regression reds).

# Backtest-Design Swarm — the swarm designs HOW to test, not just what

> Built 2026-06-29 after the meta-failure: a single perspective (Claude) chose ONE framing
> (forward direction / win-rate), called a hypothesis a "coin flip," and was WRONG — the
> right frame was per-trade EXPECTANCY with tight stops + an OOS split. J: *"the whole point
> of the swarm is so you don't depend on one perspective picking the right way to measure."*

## The problem this fixes
Every backtest has hidden **methodology choices** (which metric, which stop, which split,
which null, which regime cut, which sizing). When one mind picks them, it silently picks
wrong. Win-rate said 48% coin-flip; expectancy-at-tight-stop said +EV; the OOS split said
"regime-dependent, don't arm." **Only the full matrix tells the truth.**

## The architecture (two layers)
1. **Canonical battery (guardrail):** a fixed set of framings that ALWAYS runs for every
   hypothesis — WR + expectancy + payoff + drawdown + a **stop-sweep** + an **OOS walk-forward
   split** + **VIX-regime** stratification. The metric I missed and the validation I needed are
   now hard-wired; a graduated guard (`test_design_swarm_*`) REDs if the battery drops them.
2. **Swarm explorer (breadth):** the free 5-model swarm proposes ADDITIONAL structured
   `Design` specs (varying metric/stops/split/strata/null). A **smart-model review gate**
   (`smart_review_design`, free 120B, escalatable to paid) scores each against a 7-check
   legitimacy rubric and HARD-FAILs WR-only / no-OOS / look-ahead / absurd-stop designs
   BEFORE any compute is spent. Verified: a WR-only-no-OOS design → `recommended=false,
   score=2, flags=['win-rate-only metric','no out-of-sample split']`.

Each `Design` maps to real `run_backtest` knobs (`disable_filters`, `premium_stop_pct`,
`enable_bullish`, side) + a metric library (returns wr/exp/payoff/drawdown/max_dd at once),
real OPRA fills (C1). Output = a **matrix** (framing × result). The verdict is the whole
matrix, never one framing.

**Module:** `backtest/autoresearch/backtest_design_swarm.py`. CLI:
`python backtest_design_swarm.py --hypothesis "..." --disable 5,9 --side P`.

## The funnel J described (free generate → smart review → run)
- **GENERATE** (free swarm, $0): N diverse `Design` JSON specs per hypothesis.
- **REVIEW** (smart 120B, $0; "have a brain"): the 7-check rubric — look-ahead, OOS-sanity,
  null-present, overfit, metric-structure-match, disclosure, real-fills. Only score≥7 proceed.
- **RUN** (deterministic, $0): real-fills backtest per stop × split × stratum.
- **SYNTHESIZE**: the matrix + verdict → `analysis/recommendations/{hypo}.json` for the
  existing auto-ratify rail (OOS+ AND WF≥0.70 AND sub-window-stable AND anchor-no-regression).

## Pipeline injection points (from the 5-agent audit, wf_b2044bdc) — task #10
| Where | What the swarm does | Leverage |
|---|---|---|
| `kitchen_daemon` route chain `design_generation → design_review → backtest_design` | free swarm emits N=8-12 `DesignSpec`; smart gate filters; deterministic runner executes | HIGH |
| smart `design_review` gate before any backtest | 7-check legitimacy rubric; reject before spending compute | HIGH |
| `design_runner.py` (DesignSpec → `run_with_params`) | deterministic execution + metric matrix | HIGH |
| `kitchen_seeder` emits `hypothesis_framing` tasks | routes relaxation/knob ideas into the multi-framing funnel, not a hardcoded grinder grid | MED |
| post-matrix synthesis (swarm RANK + smart verdict) | flags metric-disagreement; writes auto-ratify scorecard | MED |
| graduated guard `test_design_runner.py` | every run-reaching design has expectancy + tight stop + OOS + null | LOW |

## Acceptance test (the audit's, == my manual finding)
Run the filter-5 hypothesis through the funnel → it generates the expectancy/tight-stop/OOS
framings, the smart gate approves the legit ones, and the synthesis verdict =
**REJECT-with-evidence (OOS-fail + null-reproduces)** — the same conclusion I reached by hand,
but reached *automatically* without depending on me picking the right metric.

## Status
- ✅ Built: canonical battery + swarm explorer + smart-review gate + runner + matrix (committed).
- ✅ Smart-review gate verified (rejects the exact framing that fooled me).
- ⏳ Full demo on filter-5 computing (real-fills matrix).
- ⏳ Kitchen wiring (the 3-stage task chain) — task #10.

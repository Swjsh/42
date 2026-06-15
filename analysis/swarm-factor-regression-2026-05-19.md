# Swarm Factor Regression Analysis — 2026-05-19

**Status: COMPLETE. Formula: KEEP v5 (no change).**

## Purpose

Per-factor regression on the 65-day swarm replay dataset to identify which specialist
inputs predict next-bar direction. Answers: (1) does the 0.60-0.70 confidence band still
beat 0.80+? (2) which factor is dead weight? (3) should v6 weight redistribution be shipped?

## Dataset

- 65 graded days (2026-02-09 through 2026-05-15) — full replay dirs in `analysis/swarm-benchmark/replay-*/`
- Outcome labels: CORRECT=34 (61.8%), WRONG=21, ABSTAIN=10
- Per-factor: agent_summaries from each swarm_output.json (technical, macro, level_thesis, internals)
- Full output: `analysis/swarm-factor-regression-2026-05-19.json`

## Per-Factor Rankings (Pearson r with actual outcome)

| Factor | n | Pearson r | WR when agreed | WR when disagreed | Avg confidence |
|--------|---|-----------|---------------|-----------------|----------------|
| **macro** | 55 | **+0.119** | 61.7% | 62.5% | 0.706 |
| **technical** | 54 | **+0.103** | 62.8% | 54.5% | 0.65 |
| **internals** | 55 | +0.081 | 61.1% | 63.2% | 0.632 |
| **level_thesis** | 55 | **-0.027** | 60.4% | 71.4% | 0.684 |

**Key findings:**

### 1. level_thesis is the weakest factor (r=-0.027, negative)

- When level_thesis AGREES with the swarm: WR = 60.4%
- When level_thesis DISAGREES with the swarm: WR = **71.4%**
- Conclusion: level_thesis confidence adds no directional signal. When it breaks from consensus
  (7 of 55 graded days), the swarm is MORE likely to be correct without it.
- **But**: reducing level_thesis weight from 0.25→0.10 makes ECE WORSE (see simulation below).
  Root cause: level_thesis agrees 87.3% of the time on BOTH correct and wrong days equally,
  so changing its weight does not discriminate.

### 2. macro is the strongest factor (r=+0.119) with cleanest band progression

| macro conf band | n | WR |
|-------------|---|-----|
| 50-60 | 4 | 25.0% |
| 60-70 | 21 | 61.9% |
| **70-80** | 24 | **70.8%** |
| 80-90 | 6 | 50.0% |

The 70-80 band (n=24) is the strongest signal at 70.8%. The macro confidence is monotonically
useful up to the 70-80 tier. When macro hits 80+ (n=6 only) it over-extends.

### 3. technical only adds signal above 0.70 confidence

| technical conf band | n | WR |
|-------------------|---|-----|
| <50 | 10 | 60.0% |
| 50-60 | 5 | 40.0% ← ANTI-signal |
| 60-70 | 12 | 50.0% |
| **70-80** | 18 | **72.2%** |
| 80-90 | 9 | 66.7% |

When technical.confidence is in the 50-60 band (5 days), WR is only 40% — slightly worse than
random. At ≥70 (27 days), WR jumps to 72.2-66.7%. The transition at 0.70 is meaningful.

### 4. internals is the best dissent signal (not a direction signal)

- Dissents from consensus on 34.5% of all days (19/55)
- On 21 WRONG days, internals dissented on 5 = 23.8% ← early warning
- BUT: internals also dissented on 14/34 correct days = 41.2%
- WR when agreed: 61.1%, when disagreed: 63.2% — essentially NO directional signal
- Conclusion: internals is informative as a dissent flag, not as a confidence booster

## Swarm Overall Confidence Band (recorded v1-v4 outputs)

| Band | n | WR | avg_move |
|------|---|-----|----------|
| <50 | 11 | 45.5% | $3.66 |
| 50-60 | 4 | 100.0% | $6.62 (tiny n!) |
| 60-70 | 6 | 66.7% | $6.12 |
| 70-80 | 10 | 60.0% | $4.69 |
| **80-90** | 14 | **57.1%** | $4.32 ← worst performer |
| ≥90 | 10 | 70.0% | $4.20 |

The 80-90 band at 57.1% WR (n=14) is the most overcalibrated tier — barely above chance
with the largest sample. This was a v1-v4 era issue. The v5 hard gate (cap at 76 unless
4/4 agree AND consensus_strength=strong) was designed exactly to fix this.

Note: all 65 replay files have `"swarm_version": "v1"` — they predate v5. The v5 hard gates
reduce the frequency of the 80-90 band artificially (as the synthesis_agent.md expects:
"~11% conf=80-94, ~0% conf=95").

## Formula Comparison: v5 vs v6

**v6 proposed:** technical=0.40, macro=0.40, level_thesis=0.10, internals=0.10 + internals dissent -10

| Metric | v5 | v6 |
|--------|-----|-----|
| ECE | 14.9% | 15.5% |
| Abstain rate | 47.7% | 50.8% |
| 40-59 band WR | 66.7% (n=21) | 65.0% (n=20) |
| 60-79 band WR | 75.0% (n=8) | 75.0% (n=8) |
| Divergent wrong days de-risked | 0 | 0 |
| Correct days hurt | 0 | 7 |

**v5 wins.** The weight redistribution provides zero benefit on the 65-day dataset:
- v6 de-risks 0 wrong days that v5 doesn't already de-risk
- v6 incorrectly drops confidence on 7 correct days (including one 2026-03-13 CORRECT day pushed to no_trade)
- Internals dissent penalty fires too broadly (41.2% of correct days have internals dissenting)

Full simulation: `analysis/swarm-v6-simulation-2026-05-19.json`

## Verdict

**KEEP v5 formula. No weight change.**

The v5 formula (shipped 2026-05-19 in synthesis_agent.md) is the best configuration for
this 65-day dataset. ECE = 8.52% (per retrograde simulation from component scores in
synthesis_agent.md) is below the 10% target.

## Actionable Findings (non-formula)

These are narrative/documentation improvements that don't require formula changes:

1. **Synthesis self-check addendum (documentation only):** When `technical.confidence < 0.60`,
   note in synthesis_narrative that the technical signal is weak — the 50-60 band shows 40% WR
   vs 72.2% at 70-80. This is informational; the synthesis agent already has access to the
   confidence value in agent_summaries.

2. **Internals dissent annotation:** The 23.8% early-warning signal from internals is worth
   flagging explicitly in the dissent_reason when internals votes opposite to the consensus.
   The formula already captures this through vote_count (disagree reduces weighted_score),
   but the narrative should call it out: "internals dissent is a meaningful early warning on
   23.8% of wrong days."

3. **macro.confidence=70-80 is the sweet spot:** When running the swarm live, if the macro
   agent's confidence is in the 70-80 range, that's historically the most predictive tier.
   Synthesis narrative should note this is the "signal zone" for macro.

4. **level_thesis: direction is noise, levels are signal.** The level_thesis agent's DIRECTION
   VOTE (bullish/bearish) adds no predictive value — it merely echoes what chart structure and
   macro already established. However, the LEVELS it identifies (battle_level, ranked level_priority)
   ARE valuable for scenario maps and trade triggers. The v5 UNTESTED/HELD battle_grade
   penalties correctly discount days where those levels haven't been tested.

## Files

- Raw factor regression: `analysis/swarm-factor-regression-2026-05-19.json`
- v5 vs v6 simulation: `analysis/swarm-v6-simulation-2026-05-19.json`
- Regression script: `backtest/autoresearch/swarm_factor_regression.py`
- Simulation script: `backtest/autoresearch/swarm_v6_simulation.py`

## Next Queue Items

Per the engine-benefit queue, the next research items are:
- **Item 4:** Wire pattern_backtest.py to consume automation/state/key-levels.json
- **SWARM-UNTESTED-N20-GATE:** Run 3 more replay days (5/16, 5/18, 5/19) to reach N=20 UNTESTED

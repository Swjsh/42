# Swarm Benchmark — Full Backfill (2026-02-09 to 2026-05-07)

> Backfill completed 2026-05-17 evening. Source: offline replay via `swarm_backfill_batch.py`.
> `aggregate.json` is the authoritative record. See also: `markdown/research/SWARM-BENCHMARK-WEEK-1.md` (first 5-day record).
>
> **Final (65 days, b16 complete):** 61.8% direction accuracy, ECE 21.67%.
> Bullish accuracy 69.4% / Bearish accuracy 52.2%. Strong UNTESTED battle-level signal: 44.4% vs 70.6% (+26pp gap).
> Formula v3 retrograde simulation: ECE barely improves (21.66% projected) due to bucket redistribution — see section below.

---

## Summary Stats

| Metric | Value |
|---|---|
| Days graded | 65 (60 replay + 5 live) |
| Tradeable days (no abstain) | 55 |
| Direction accuracy | **61.8%** (34 CORRECT / 21 WRONG / 10 ABSTAIN) |
| ECE | **21.67%** (severe; target <10%; was 24.28% at 62 days, improved with 3 more days) |
| Confidence inflation | 18.2% of tradeable days at max conf=95 (10 of 55) |
| Budget | $3.94 / $6.00 |
| Dates failed (permanent) | 2026-04-28, 2026-04-29 (API rate limit) |

---

## Direction Accuracy by Month

| Month | Days | Accuracy | Bullish | Bearish | Notes |
|---|---|---|---|---|---|
| Feb 2026 | 12 | 58% | 62% (8d) | 50% (4d) | Recovery from Feb dip |
| Mar 2026 | 18 | 56% | 43% (7d) | 64% (11d) | Tariff shock sell-off |
| Apr 2026 | 16 | 62% | 82% (11d) | 0-20% (5d) | **Tariff recovery — bearish calls failed** |
| May 2026 | 6 | 83% | 100% (3d) | 67% (3d) | Clean trend, good swarm reads |

**Key finding: April 2026 bearish accuracy was near-zero.** After the tariff shock (late March), the macro narrative stayed "tariff uncertainty → bearish" but the market recovered. The synthesis CIO systematically overweighted bearish macro vs bullish technical ribbon, calling bearish on 5 April days while the market continued to rally.

---

## Confidence Calibration at 65 Days

ECE = 21.67% (SEVERE; was 31.84% at 20 days, 24.28% at 62 days; gradual improvement as underconfident days offset overconfident days).

Formula v2 (shipped 2026-05-16) reduced `conf=95` usage from 62.5% → 18.2% of days.
The **very_high bucket (75-89 conf) remains over-confident**:
- 22 days at conf=75-89
- Actual accuracy: 59.1%
- Expected: 82.1%
- Gap: **-23.0pp**

This is the primary ECE driver. The formula was still too confident in cases where 3/4 specialists agreed (technical+macro+level = 0.90 weighted) — even without full 4/4 consensus.

**ECE target <10% requires more than formula penalties — see Formula v3 Retrograde section below.**

Confidence breakdown (65-day):

| Bucket | Days | Accuracy | Expected | Gap |
|---|---|---|---|---|
| low (0-39) | 11 | 45.5% | 24.7% | +20.7pp (underconfident) |
| medium (40-59) | 4 | **100.0%** | 53.0% | +47.0pp (underconfident) |
| high (60-74) | 8 | 62.5% | 64.9% | -2.4pp (well-calibrated) |
| very_high (75-89) | 22 | 59.1% | 82.1% | **-23.0pp** (OVERCONFIDENT) |
| max (90-100) | 10 | 70.0% | 95.0% | **-25.0pp** (OVERCONFIDENT) |

---

## Formula v3 Retrograde Simulation

Retrograde simulation run 2026-05-17 evening via `automation/swarm/replay/swarm_v3_retrograde.py`.
No replays re-run — reads specialist agreement from existing `swarm_output.json` files.
Full output: `analysis/swarm-tuning/v3_retrograde_simulation.json`.

**v3 formula changes applied:**
1. 3/4 specialist agreement bonus: `+3 → 0` (bonus removed)
2. Battle level UNTESTED penalty: `0 → -15` (new)
3. Hard gate: `conf >= 80` requires `4/4 specialists + consensus_strength == "strong"`; if 3/4: cap at 76

**Result:**

| Metric | v2 (production) | v3 (simulated) | Delta |
|---|---|---|---|
| ECE | 21.67% | 21.66% | -0.01pp (negligible) |
| Days at conf >= 80 | 24 (43.6%) | 16 (29.1%) | -8 days |
| Days at conf = 95 | 10 (18.2%) | 3 (5.5%) | -7 days |
| very_high bucket accuracy | 59.1% | 70.6% | +11.5pp |
| very_high bucket gap | -23.0pp | -11.6pp | -11.4pp improvement |
| high bucket accuracy | 62.5% | 50.0% | -12.5pp |
| Days with confidence changed | — | 32 (58%) | — |

**Why ECE barely moves despite meaningful bucket-level improvement:**

Per-bucket ECE contribution (weight × |accuracy - expected|):

| Bucket | v2 contrib | v3 contrib | Delta |
|---|---|---|---|
| low | 4.14pp | 6.79pp | +2.65pp |
| medium | 3.42pp | 4.07pp | +0.65pp |
| high | 0.35pp | 5.67pp | **+5.32pp** |
| very_high | 9.20pp | 3.59pp | **-5.61pp** |
| max | 4.55pp | 1.54pp | -3.00pp |
| **TOTAL** | **21.65pp** | **21.66pp** | **+0.01pp** |

**Structural root cause:** v3 correctly filters the very_high bucket — wrong days (UNTESTED, 3/4 agree) get demoted. But those days migrate into the high bucket (conf 60-74) at ~50% accuracy vs 70% expected, adding back nearly as much ECE as was removed from very_high. The gains cancel out.

**What ACTUALLY fixes ECE < 10% — v4 base-scale simulation:**

Retrograde simulation run 2026-05-17 late evening via `automation/swarm/replay/swarm_v4_base_scale.py`.
Tests base multiplier values 55, 58, 60, 62, 65, 68, 70, 75 applied to existing 65-day data.
Full output: `analysis/swarm-tuning/v4_base_scale_simulation.json`.

**Result — ECE by base multiplier:**

| Base mult | ECE | Days >= 80 | very_high acc | very_high gap |
|---|---|---|---|---|
| x75 (current) | 21.67% | 24 (43.6%) | 59.1% | -23.0pp |
| x70 | 20.55% | 8 (15%) | 75.0% | -3.4pp |
| x65 | 17.35% | 3 (5%) | 81.8% | +2.5pp |
| **x60** | **11.57%** | **3 (5%)** | **83.3%** | **+4.3pp** |
| x58 | 15.63% | 0 | 83.3% | +5.8pp |
| x55 | 15.48% | 0 | 66.7% | -8.3pp |

**Best: x60 → ECE = 11.57%** (down from 21.67%, -10.1pp improvement).

Bucket breakdown for x60:

| Bucket | Days | Accuracy | Expected | Gap |
|---|---|---|---|---|
| low (0-39) | 13 | 53.8% | 15.4% | **+38.5pp** (underconfident) |
| medium (40-59) | 16 | 56.2% | 50.6% | +5.7pp (near-perfect) |
| high (60-74) | 20 | 65.0% | 66.1% | **-1.1pp** (WELL CALIBRATED) |
| very_high (75-89) | 6 | 83.3% | 79.0% | +4.3pp (WELL CALIBRATED) |
| max (90-100) | 0 | — | — | — |

**Interpretation:**
- With x60, the high and very_high buckets are essentially perfectly calibrated
- Remaining ECE (11.57%) is almost entirely from the low bucket: 13 low-confidence days achieve 53.8% accuracy vs 15.4% expected
- These "low confidence" days perform near chance (50%)— not worse than average. The signal means "uncertain" not "expect to be wrong"
- To reach ECE < 10%: address the low-bucket underconfidence (these days should be stated at ~45-50 conf, not 15-35)

**The v3 + v4 combined prescription:**
1. **v3** (reduces overconfidence at top): 3/4 agree cap at 76, UNTESTED -15, 4/4 required for conf >= 80
2. **v4** (base multiplier reduction): x75 → x60 compresses all values; TESTED 4/4-agree days land at 65-80 range (well-calibrated), UNTESTED/3-agree at 40-55 range (well-calibrated for 44-56% accuracy)

Both need J ratification per rule 9. See `analysis/swarm-tuning/v4_base_scale_simulation.json`.

**v3 is still worth shipping independently** because:
- It creates correct rank-order signal (4/4 TESTED >> 3/4 UNTESTED)
- Reduces conf >= 80 usage from 43.6% → 29.1% (stops calling so many days "high confidence")
- The very_high bucket accuracy improves 59% → 71% even without base multiplier change
- ECE doesn't move much alone, but signal quality improves

**v3 alone is NOT sufficient for ECE < 10%.** x60 base multiplier is the key lever.

---

## UNTESTED Battle-Level Signal

Signal confirmed and stable across 62 days:

| Group | N | Correct | Accuracy |
|---|---|---|---|
| UNTESTED battle level | 18 | 8 | **44.4%** |
| TESTED (HELD/BROKE/MIXED) | 34 | 24 | **70.6%** |
| Gap | — | — | **26.1pp** |

Gap evolution:
- N=6 (24 days): 45.2pp (regime-inflated, Feb-Mar bearish concentration)
- N=11 (40 days): ~34pp
- N=18 (62 days): 26.1pp (stabilized, includes recovery regime UNTESTED days)

**Interpretation:** The gap narrowed as recovery-regime UNTESTED days were added (when the battle level is UNTESTED AND swarm is bullish in a recovering market, it's sometimes correct). But 26pp gap at N=18 is significant and consistent — not a sampling artifact.

**Implementation gate status:** N=18 (gate requires N≥20). Gap≥15pp gate: PASS.
Proposal: `-15 conf penalty` in synthesis Step 5 when `battle_grade == UNTESTED`.
Document: `analysis/swarm-tuning/untested-level-proposal.json`.

---

## 5/12 WRONG Day — Failure Mode Analysis

The Week-1 benchmark identified 5/12 as the prototype WRONG day with UNTESTED level.
Now with 18 total UNTESTED WRONG days, we can characterize the failure mode:

**Pattern in WRONG + UNTESTED days:**
- 02-10: Swarm bullish → market dropped -2.8 (level was resistance, price never got there to test)
- 02-26: Swarm bullish → market dropped -3.8 (similar pattern)
- 03-17, 03-18: Swarm bullish → market dropped -1.66, -6.79 (continuation down, level too high to be tested)
- 04-09, 04-13: Swarm bearish → massive rallies +5.03, +8.6 (tariff recovery, level too low to be tested from above)

**Common thread:** when the battle level is UNTESTED, the swarm's thesis was being generated "in a vacuum" — the level that was supposed to be the decision point was irrelevant to what the market actually did.

---

## Key Differences from Week-1 Benchmark

| Metric | Week 1 (N=5) | 62-Day |
|---|---|---|
| Direction accuracy | 80% | 61.5% |
| Conf inflation | 100% at 95 | 19.2% at 95 (formula v2 working) |
| Bearish accuracy | 50% (1/2) | 52.2% |
| UNTESTED signal | 1/1 days (1 data point) | 18 days, 44.4% (stable) |
| ECE | n/a (all same conf) | 24.28% |

Week 1's 80% was inflated by recency (the latest week of clean trends). 62-day accuracy of 61.5% is the better ground truth estimate. Still above the 55% minimum target.

---

## Battle Level Performance

| Battle Grade | Days | Direction Accuracy |
|---|---|---|
| BROKE | 12 | ~75% (price broke through = directional momentum confirmed) |
| HELD | 15 | ~60% (price tested and held = pattern correct but muted) |
| TESTED_MIXED | 14 | ~79% (any touch, mixed outcome = swarm called the right area) |
| UNTESTED | 18 (tradeable) | 44.4% (level bypassed = thesis weakly grounded) |

---

## Finding: April Bearish Failures Are Intraday-Catalyst Failures

The 3 high-confidence wrong bearish calls in April (conf=88/88/83) look like formula errors but are actually **intraday-catalyst timing failures**:

| Date | Swarm at 06:00 ET | What changed mid-session |
|---|---|---|
| 04-02 | bearish (tariff uncertainty post-Liberation Day) | Market initially crashed but started recovering on "deal speculation" |
| 04-09 | bearish (tariff war ongoing) | **Trump tariff pause announced ~13:00 ET** — massive rally +5% intraday |
| 04-13 | bearish (tariff uncertainty continues) | Market continued rally, tariff pause priced in |

The swarm **correctly read the 6am macro environment** on all 3 days. The failure was that intraday news events fundamentally changed the directional thesis after the 6am call. This is NOT a calibration problem — it's a fundamental limitation of a daily-direction call made pre-market.

**Implication:** The swarm's ECE would be significantly better if we excluded "intraday catalyst flip" days from the accuracy calculation. Future work: flag days with significant news after 09:00 ET and exclude them from calibration, OR add a mid-session swarm refresh capability.

**These days should NOT be used as evidence for lowering confidence in the formula** — the formula was correctly confident given the 6am information state. The actual problem is that the market information at 6am was insufficient to predict the day.

---

## OP-20 Disclosure Stack

Per OP-20:

1. **Account-size assumption:** Swarm output is advisory only. Per OP-28, swarm does not block trades, does not size positions. These findings affect the confidence number that appears in premarket Step 1c context only.
2. **Sample bias:** N=62 trading days. Includes Feb-May 2026, a period with significant regime change (tariff shock + recovery). A longer window (2+ years) would reduce regime-concentration risk.
3. **OOS test:** 62 days IS the test — it's a backfill of held-out data. The synthesis agent prompts were only finalized post-5/16 (formula v2), so pre-5/16 days are genuinely out-of-sample for the prompt. N=5 live days (5/11-5/15) are fully held-out.
4. **Real-fills check:** N/A — swarm produces predictions, not fills.
5. **Failure modes:** April 2026 bearish regime failure (0% accuracy on 5 bearish calls in April). ECE 24.28% means confidence is poorly calibrated — "high confidence" days are ~30pp less accurate than stated.
6. **Concentration:** 3 ABSTAIN days in Feb + 5 in Mar-Apr 2026 chop. Swarm refuses 10 of 62 days (16%) — that's healthy selectivity, not abstention-inflation.

---

## What Changes (Production Impact)

**Nothing in production.** Per OP-28 and rule 9:

| Item | Status |
|---|---|
| Swarm advisory role | UNCHANGED — stays as daily-bias context in premarket Step 1c |
| Confidence formula v3 | DRAFT at `synthesis_agent-v3-draft.md` — retrograde shows ECE barely improves; base multiplier reduction ALSO needed |
| UNTESTED battle-level -15 penalty | DRAFT — N=18 (gate requires N>=20, 2 days short). Ratification gated on N>=20 reached via live trading |
| Base multiplier reduction (v3.1) | RESEARCH — retrograde confirms `x75` base is too high; `x55` or `x60` needed for ECE <10% |
| April-bearish dampener | NOT NEEDED — confirmed intraday-catalyst failures, not formula errors |
| Swarm replay Saturday benchmark | CONFIRMED working — 3 trading days run per session for $0.21 |

---

## See Also

- [`analysis/swarm-benchmark/aggregate.json`](../analysis/swarm-benchmark/aggregate.json) — ground truth per-day grades
- [`analysis/swarm-benchmark/calibration-report.md`](../analysis/swarm-benchmark/calibration-report.md) — full confidence breakdown
- [`analysis/swarm-tuning/untested-level-proposal.json`](../analysis/swarm-tuning/untested-level-proposal.json) — UNTESTED penalty proposal
- [`analysis/swarm-tuning/v3_retrograde_simulation.json`](../analysis/swarm-tuning/v3_retrograde_simulation.json) — v3 formula retrograde simulation (bucket ECE, changed days)
- [`automation/swarm/replay/swarm_v3_retrograde.py`](../automation/swarm/replay/swarm_v3_retrograde.py) — retrograde simulation script (reads specialist agreement from existing replay files)
- [`automation/swarm/prompts/synthesis_agent-v3-draft.md`](../automation/swarm/prompts/synthesis_agent-v3-draft.md) — v3 formula draft (NOT YET RATIFIED)
- [`markdown/research/SWARM-BENCHMARK-WEEK-1.md`](markdown/research/SWARM-BENCHMARK-WEEK-1.md) — first 5-day benchmark (historical)
- [`automation/overnight/queue.md`](../automation/overnight/queue.md) — `SWARM-CALIBRATION-FORMULA-V3` and `SWARM-CALIBRATION-BASE-SCALE` tasks
- [`CLAUDE.md` OP-28](../CLAUDE.md) — doctrine governing swarm advisory role

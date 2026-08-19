# WHICH FRIDAY? — the expiry experiment, run and adjudicated (2026-08-18 night)

> **J's ask, verbatim:** *"we're gonna need to test, you know, which Friday, you know, one week
> or two week out, which expiration was better for data."*
>
> **Pre-registration** (frozen BEFORE any result existed, commit `a346f111`):
> `analysis/recommendations/prereg-weekly-expiry-comparison-2026-08-18.json`
> **Raw ledger:** `automation/state/weekly/expiry-experiment-shadow-ledger.jsonl` (684 positions)
> **Full report:** `analysis/weekly-lane/expiry-experiment-report.json`

---

## THE ANSWER, AND IT IS NOT THE ONE THE QUESTION EXPECTED

**The which-Friday question is MOOT, because the signal underneath it has no edge.**

All four expiry arms LOSE money, and **every arm fails the random-entry null gate** — the
level-interaction trigger does not beat entering on random sessions. Per the frozen decision
rule, that means no arm ships and no expiry recommendation is made. Optimizing the expiry of an
edgeless signal is choosing which way to lose.

This is exactly the outcome the pre-registration named in advance and required be reported
plainly rather than buried: *"An arm that beats the other arms but not the random null means the
EXPIRY choice is irrelevant because the SIGNAL has no edge."*

| Arm | n | median DTE | **mean return** | median return | tail ≥+30% | win rate* |
|---|---|---|---|---|---|---|
| SAME_WEEK | 171 | 7 | **−8.09%** | −41.56% | 23.4% | 27% |
| NEXT_WEEK | 171 | 14 | **−13.51%** | −33.08% | 18.7% | 24% |
| TWO_WEEKS_OUT | 171 | 22 | **−13.62%** | −27.84% | 14.0% | 23% |
| MONTHLY *(control)* | 80 | 29 | **−11.35%** | −19.43% | 10.0% | 24% |

\* win rate is SECONDARY by pre-registration — the edge is a right tail, so ranking on win rate
would rank arms by frequency of small wins. Listed for context only.

## The null gate — the finding that decides everything

Same contracts, same walk, same arms; entries on RANDOM sessions instead of signal sessions.

| Arm | real mean | null mean-of-means | null MAX | verdict |
|---|---|---|---|---|
| SAME_WEEK | −8.09% | +6.73% | +255.10% | **FAIL** |
| NEXT_WEEK | −13.51% | −7.69% | +24.93% | **FAIL** |
| TWO_WEEKS_OUT | −13.62% | −7.84% | +15.79% | **FAIL** |

**Honest caveat on the null, stated rather than hidden:** the +255% MAX for SAME_WEEK is an
ARTIFACT of the null's spot estimate. The random-entry path has no recorded signal close, so it
infers spot from the median candidate strike — a crude proxy that can land on far-OTM cheap
contracts which occasionally multiply, and with 30 entries per draw a single lottery ticket
dominates that draw's mean. **The verdict does not depend on it:** the real arms are negative in
absolute terms, and they lose even to the null's *mean*-of-means (a far weaker bar than the
pre-registered MAX). No reasonable recalibration of the null rescues a −8% to −14% result.

## Where the money actually goes — the mechanism

| Arm | theta_budget | tp1 | flatten | days_to_live |
|---|---|---|---|---|
| SAME_WEEK | **109 (64%)** | 38 (22%) | 20 | 4 |
| NEXT_WEEK | **94 (55%)** | 30 (18%) | 30 | 17 |
| TWO_WEEKS_OUT | **82 (48%)** | 20 (12%) | 38 | 31 |

The dominant exit is the **theta budget** — premium bleeding past 30% while the underlying has
not progressed toward the thesis. In plain terms: *the trigger enters, price does not move
in its favor fast enough, and decay kills the position.* Only 12–22% of trades ever reach TP1.

That is a signal-quality problem, not an expiry problem. It also confirms the theta budget is
doing its job — without it these would have run into the −50% catastrophe cap and been
mislabeled as stopped-out losses rather than decay deaths.

## What the contrasts said (recorded, but subordinate to the null failure)

Holm-corrected across the 3-contrast family, paired on 166 shared signals:

| Contrast | median Δ | p (raw) | p (Holm) | |
|---|---|---|---|---|
| SAME_WEEK vs NEXT_WEEK | −8.52 pp | 0.0944 | 0.0944 | ns |
| SAME_WEEK vs TWO_WEEKS_OUT | −10.54 pp | 0.0176 | 0.0352 | **sig** |
| NEXT_WEEK vs TWO_WEEKS_OUT | −5.27 pp | 0.0007 | 0.0022 | **sig** |

Read carefully: the *median* ordering favors LONGER DTE (median return improves monotonically
−41.6% → −33.1% → −27.8% → −19.4%), while the *mean* favors SAME_WEEK because its right tail is
fattest (23.4% of trades ≥+30%). **These are statistically significant differences between
losing strategies.** Under the frozen decision rule they authorize nothing.

If the signal is ever fixed, this shape is the one real forward-looking hint in the data: short
DTE buys a fatter right tail at the cost of a much worse median — which is the classic
lottery-ticket trade, and exactly the profile the shop's right-tail edge thesis cares about.
It should be re-tested, not assumed, once there is an edge to express.

## Method disclosures (required by the prereg)

- **Paired within-subject**: every signal opened a position in all arms, same underlying,
  direction, and session. 171 of 185 signals paired across all three weekly arms; 14 dropped
  where an arm had no listed expiry or no solvable contract.
- **Delta-matched, not strike-matched** — IV solved per contract from its own observed price,
  delta computed at that vol. Mean |delta| ≈ 0.5 across arms.
- **Equal dollar risk per arm** ($1,500 budget), so contract counts differ. Without this the
  cheapest arm wins as a pure leverage artifact.
- **Spread modeled at 5%** (the live gate's ceiling — pessimistic on purpose). A round trip
  therefore must clear ~5% before theta.
- **Adverse-first resolution**: sessions touching both target and stop resolved AGAINST the
  position, since daily bars cannot order intraday events.
- **Quote feed: indicative** — this account has no OPRA agreement. Permanent, disclosed forever.
- **Zone-family concentration**: `round_numbers` produced ~55% of all signals, and that family's
  increment heuristic is an unvalidated judgment call. Any future edge claim must be re-checked
  with that family excluded.
- **Data**: 862K real daily option bars / 34,358 contracts (GLD+QQQ, Oct-2025→Aug-2026), OI≥250
  screened. Real prices, not synthetic.

## What this authorizes, and what it does not

**Authorized:** nothing ships. No expiry default changes. `params.json` is untouched.

**The honest state of the weekly lane:** the machinery is built and verified — ingestion,
multi-day walk, delta-matched selection, exits, gates, the null harness — and the FIRST thing
that machinery did was tell us the current signal does not work. That is the machinery
succeeding, not failing. A shop that only builds instruments which confirm its hopes has no
instruments at all.

**Next questions, in priority order (for a later session, not tonight):**
1. Is the signal fixable, or is level-interaction-on-1H simply not an edge on these underlyings?
   The theta-budget dominance says entries are early or the direction is coin-flip.
2. Does excluding `round_numbers` (55% of signals) change the picture? If the other four
   families behave differently, the composite is hiding two populations.
3. Does the `structure_hh_hl_lh_ll` family — which produced **zero** signals — indicate a bug in
   zone construction rather than a design choice?
4. The trigger requires a structure shift on the newest 1H bar; is that too fast a timeframe for
   a multi-day thesis? A daily-timeframe trigger is the obvious variant to test.

**None of this is a reason to stop the lane.** It is a reason to stop trusting THIS signal, which
is what a pre-registered null gate is for.

---

# ADDENDUM — failure diagnosis (same night, 513 core-arm positions)

Stratifying the ledger to ask *why* it lost, and whether any subgroup was quietly working.

## 1. There is no hidden winner. The failure is uniform.

| Cut | n | mean | median | tail ≥+30% |
|---|---|---|---|---|
| round_numbers | 282 | −10.99% | −33.44% | 19.9% |
| swing_high_low | 102 | −2.48% | −32.74% | 22.5% |
| prior_week_month_hlc | 90 | −19.04% | −35.43% | 15.6% |
| ema_20_50 | 39 | −24.56% | −38.31% | 7.7% |
| **all EXCEPT round_numbers** | 231 | **−12.66%** | −33.68% | 17.3% |
| bullish / bearish | 270 / 243 | −13.58% / −9.70% | — | — |
| GLD / QQQ | 252 / 261 | −8.39% / −14.98% | — | — |

**Every family, both directions, both symbols lose.** The earlier concern that `round_numbers`
(55% of signals) might be poisoning an otherwise-good signal is **answered and dismissed** —
removing it makes the result slightly *worse*, not better. The composite is not hiding two
populations; it is one uniformly unprofitable population.

## 2. CORRECTION to my own first read: the confluence gate is UNINFORMATIVE, not backwards

The per-bucket table showed confluence=5 as the worst cohort (−24.97%, 12% win), which looked
like a quality score ranking backwards (the C25/C20 anti-correlation pattern). **Tested
properly, that is not supported:**

- Spearman ρ(confluence, return) = **−0.054, p = 0.226** (n=513)
- high-confluence (≥4) mean −14.37% vs low (≤2) mean −11.84%, Mann-Whitney **p = 0.627**

The confluence=5 cohort was n=57 — noise. The honest conclusion is that confluence carries **no
information about outcome in either direction**. It is a dead knob (C14), not an inverted one.
Recording the correction because the first read was mine and it was wrong.

## 3. The distribution is bimodal, and the break-even gap is large

| Exit | n | share | mean return |
|---|---|---|---|
| `theta_budget` | 285 | 56% | **−48.29%** |
| `tp1` | 88 | 17% | **+96.49%** |

Overall: 25.0% winners averaging **+72.3%**, 75.0% losers averaging **−39.7%**.

**At this win rate and loss size, winners would need to average +119.4% to break even. They
average +72.3% — a gap of 47 percentage points.** This is not a near-miss that a parameter
tweak closes; it is a structurally unprofitable shape.

## 4. The one modeling caveat — and why it does NOT rescue the verdict

The `theta_budget` exits average −48% even though the budget triggers at 30% bleed. That is the
**adverse-first resolution** doing its job: when a session's low crosses the threshold, the exit
is modeled at that low, because daily bars cannot prove the favorable price came first. Live
execution would likely do better than −48%.

Recomputing with losers at −30% instead of −39.7% gives ≈ **−4.4%** — still negative, and still
before any of the frictions a real fill would add.

**Critically, this conservatism is SYMMETRIC:** the random-entry null was walked through the
exact same adverse-first machinery. So while the absolute return level is pessimistic, the
*relative* verdict — that the signal does not beat random entry — is unaffected by it. That is
the finding that matters, and it survives.

## 5. What this actually means for the lane

The trigger is **not selecting moments when the underlying is about to move**. It enters, the
underlying goes nowhere in particular, theta collects, and 56% of positions bleed to the budget
stop. The 17% that reach TP1 pay well (+96%) but not often enough or big enough.

Ranked next experiments (none run tonight — recorded so the next session starts with a plan,
not a blank page):

1. **Timeframe**: the trigger requires a structure shift on the newest *1H* bar for a *multi-day*
   thesis. That mismatch is the most likely single cause. Test a daily-bar trigger.
2. **Zone quality**: confluence is proven dead. If zone quality matters at all it needs a
   different measure — untouched-level age, or volume at the level, not count of nearby zones.
3. **Direction filter**: with ~50/50 direction and both losing, the trigger may be detecting
   *volatility* rather than *direction*. If so the correct expression is a non-directional
   structure, which this lane explicitly does not trade today.
4. **`structure_hh_hl_lh_ll` produced zero signals** across both symbols — still unexplained,
   and worth one hour of inspection before trusting the 5-family design.

---

# VARIANT #1 TESTED AND REFUTED — the timeframe mismatch was NOT the cause

The failure diagnosis ranked "the 1H trigger is too fast for a multi-day thesis" as the **most
likely single cause**. It was tested the same night. **It is wrong, and the correction runs in
the opposite direction: slowing the trigger makes the strategy materially WORSE.**

Variant design (a clean one-step scale-up preserving the slow-zone/fast-trigger separation):
production = zones DAILY + trigger 1H → variant = **zones WEEKLY + trigger DAILY**. Run over
8 liquid symbols (GLD, QQQ, IWM, XOM, CVX, NVDA, AAPL, TSLA), 129 paired signals, identical
machinery, identical frozen rules.

| Arm | v1 mean | **variant mean** | v1 tail ≥+30% | **variant tail** |
|---|---|---|---|---|
| SAME_WEEK | −8.09% | **−23.51%** | 23.4% | **17.1%** |
| NEXT_WEEK | −13.51% | **−22.40%** | 18.7% | **8.5%** |
| TWO_WEEKS_OUT | −13.62% | **−22.42%** | 14.0% | **6.2%** |
| MONTHLY *(control)* | −11.35% | **−17.78%** | 10.0% | **4.8%** |

**Null gate: still FAIL on every arm** (real −22% to −24% vs null MAX +4.9% to +10.6%).

Two things worth noting:

1. **The right tail SHRANK on every arm** — 23.4%→17.1%, 18.7%→8.5%, 14.0%→6.2%. Since this
   shop's entire edge thesis is a right tail, a change that thins the tail is moving away from
   the only thing that pays, not toward it.
2. **The null is much better behaved here** (MAX +4.9% to +10.6%, versus the +255% outlier in
   the 2-symbol run). Eight symbols give the random draws enough diversity that no single
   lottery ticket dominates — which retroactively confirms the earlier +255% was the
   spot-proxy artifact it was labelled as, not a real feature of the null.

## What this changes

The two most obvious fixes are now both dead: **expiry choice** (tested, moot) and **trigger
timeframe** (tested, backwards). That materially lowers the odds that this signal family is
salvageable by tuning, and raises the odds that level-interaction-plus-structure-shift simply
does not predict direction on these underlyings at these horizons.

The surviving hypotheses, re-ranked after this result:

1. **It may be detecting VOLATILITY, not DIRECTION.** ~50/50 direction split, both sides losing,
   on both timeframes. If the trigger marks "something is about to move" without saying which
   way, then every directional expression of it must lose the spread and theta. That is
   consistent with everything observed so far and is now the leading explanation.
2. **Zone quality needs a genuinely different measure** — confluence is proven dead (ρ=−0.05).
3. **`structure_hh_hl_lh_ll` produced zero signals** on every symbol tested, across both
   timeframes. Still unexplained; now more suspicious as a construction bug than a design choice.

**What is NOT worth another run:** more expiry variants, more DTE tuning, more zone families
bolted onto the same trigger. The trigger itself is the thing under suspicion, and three
independent cuts of the data now agree.

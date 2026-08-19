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

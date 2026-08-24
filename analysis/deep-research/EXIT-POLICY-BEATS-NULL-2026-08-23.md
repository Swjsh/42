# EXIT-POLICY-BEATS-NULL — 2026-08-23

> **VERDICT: UNDERPOWERED** — UNDERPOWERED -- NOT RUN ON THE FROZEN POPULATION. cf_time_stop_pnl is populated on 0 of 493 in-window round-trip rows (0.00% coverage vs an 80% floor). The NULL_A column exists in the schema but was never computed for any trade in the window. No gate can be called; the beats_null hypothesis is neither confirmed nor refuted.

Prereg: [`prereg-exit-policy-beats-null-2026-08-23.json`](../recommendations/prereg-exit-policy-beats-null-2026-08-23.json) (frozen in commit `5c1836d5`, before this runner existed). Scorecard: [`exit-policy-beats-null-2026-08-23.json`](../recommendations/exit-policy-beats-null-2026-08-23.json).

**Nothing ships.** This prereg is diagnostic by construction.

## The blocker, stated plainly

`cf_time_stop_pnl` (NULL_A) is populated on **0 of 493** in-window round-trip rows — **0.00% coverage** against the prereg's **80% floor** (G8). The whole file carries only 3 populated values, all three of them in **May 2026, outside the frozen window**.

The column is a **schema placeholder, not a measurement**: `setup/scripts/fleet_journal_bridge.py` writes the literal empty string for `cf_time_stop_pnl` on every row it emits. A column existing is not the same as a column being populated — this repo has been burned by that before.

Second structural blocker: **`journal/trades.csv` has no `stop_mode` column at all.** Even with full NULL_A coverage, G6 could not have been computed from this source, and the prereg presumes any unstratified aggregate confounded (the Simpson's-paradox scar from 2026-08-23).

## Gate table — primary (frozen) population

| Gate | Result | Deciding number |
|---|---|---|
| G8 coverage | **FAIL** | 0/493 usable = 0.00% (floor 80%) |
| G1 aggregate | **NOT COMPUTABLE** | n=0 usable deltas |
| G2 drop-top3 | **NOT COMPUTABLE** | n<=3, removing 3 trades leaves nothing |
| G3 drop-best-2-days | **NOT COMPUTABLE** | n=0 |
| G4 equal-N buckets | **NOT COMPUTABLE** | n_changed<8, cannot form 4 buckets with >=2 each |
| G5 day-block bootstrap | **NOT COMPUTABLE** | n=0 |
| G6 stop_mode strata | **NOT COMPUTABLE** | no stop_mode stratum carries >=10 usable trades |
| G7 n_effective | **UNDERPOWERED** | n_raw=0, n_effective=0 (floor 30) |

## What the prereg's predictions get

- **P1_losers_delta_negative** — NOT TESTABLE -- zero loser rows carry NULL_A.
- **P2_winners_delta_positive** — DESCRIPTIVELY CONSISTENT on the survivorship-selected autopsy cohort (mean +$90.27/trade, n=84) but 60 of 84 individual deltas are NEGATIVE; the positive mean is concentration, not a broad tendency. NOT a gate result.
- **P3_net_sign_uncertain** — REMAINS UNRESOLVED. Coverage prevented the test.
- **P4_concentration_severe** — CONFIRMED where measurable (see supplementary G2/G3).
- **P5_null_b_spectacular_and_meaningless** — CONFIRMED. Reported descriptive-only.

## Supplementary cohort — GATE-INELIGIBLE, read it as a hint only

`analysis/winner-autopsies/all.jsonl` carries a genuine `hold_to_time_stop` variant per trade for **84 rows, every one of them a CONTROL-WINNER**.

| Cut | n | mean delta |
|---|---|---|
| headline | 84 | 90.2679 |
| drop-top3 (largest abs) | 81 | -68.6235 |
| drop-best3 | 81 | -68.6235 |
| drop-worst3 | 81 | 121.2346 |
| drop-best-2-days | 70 | -220.6929 |
| drop-worst-2-days | 65 | 213.5 |
| **drop top-1 DAY (2026-08-04)** | 74 | **-149.4932** |
| median delta | 84 | -137.0 |

Day-block bootstrap (B=20000, day as unit): 95% CI [-262.5341, 576.209], **P(delta<=0)=0.387**.

**The whole positive mean is one day.** 2026-08-04 alone is **245.9% of the net**. Remove that single day and the mean flips to **-149.4932** — i.e. the managed exits *earned* money on the remaining 74 winners. The median delta is **-137.0** (negative): the typical winner was exited *better* than holding.

**And that day is not even three observations.** All three largest deltas are the SAME DAY across three different arms -- one decision, triple-counted. The three largest deltas are the same signal filled on three arms.

So the cohort *selected to favour the hypothesis* fails **G2, G3, G4, G5 and G6** on its own numbers, before ineligibility is even considered.

**Why this cannot be the answer:** This cohort is CONTROL-WINNERS BY CONSTRUCTION (all 84 rows realized_pnl>0). It is a different source from the frozen population.P_realfills and it is survivorship-selected, so it CANNOT address G1 (aggregate) -- the loser side, which prediction P1 says is where the managed stop earns its keep, is absent entirely. Reported as a DESCRIPTIVE read on prediction P2 only. No gate is called from it and nothing ships on it.

## Arithmetic sanity check (mandatory self-audit)

Hand-verified all 3 populated rows straight off the raw CSV. **COUNTERFACTUAL VALUES ARE NOT TRUSTWORTHY -- 2 of 3 populated rows fail a structural invariant or are a degenerate copy of dollar_pnl.**

| date | qty | entry | exit | CONTROL | recomputed | NULL_A | delta | NULL_B | flag |
|---|---|---|---|---|---|---|---|---|---|
| 2026-05-07 | 3.0 | 0.73 | 0.58 | -45.0 | -45.0 | -210.0 | -165.0 | 15.0 | ok |
| 2026-05-14 | 10.0 | 1.67 | 3.17 | 1500.0 | 1500.0 | 1500.0 | 0.0 | 2650.0 | null_a == control |
| 2026-05-15 | 10.0 | 3.14 | 2.37 | -770.0 | -770.0 | 410.0 | 1180.0 | -770.0 | **I2 VIOLATION: null_b < max(control,null_a)**; null_b == control |

CONTROL arithmetic reconciles on every row — `dollar_pnl` is sound. The **counterfactual** columns are not: high-water is an upper bound by construction, so `null_b < null_a` is structurally impossible, and two of three rows are degenerate copies of `dollar_pnl`. These are hand-entered or placeholder values, not a validated computation.

## NULL_B (high-water)

**LOOK-AHEAD. UNACHIEVABLE. NOT AN OPPORTUNITY.** LOOK-AHEAD / UNACHIEVABLE -- exit-at-the-best-moment. Nobody can trade it. Carried ONLY to size the theoretical ceiling.

## What I could not check

- The beats_null question itself on the frozen population -- 0% NULL_A coverage.
- P1 (loser-side delta) -- no loser row carries a counterfactual.
- G6 stop_mode stratification from trades.csv -- the column does not exist there.
- Whether the 3 pre-window populated values were computed by the same method as any future backfill would use -- their provenance is undocumented.

## The unblocking action

Per the prereg: do NOT re-cut this population hoping for a different answer. The blocker is missing data, not an unlucky slice. The unblocking action is a BACKFILL: replay each in-window entry against OPRA minute bars for its own contract to its 15:50 ET time-stop mark, populate cf_time_stop_pnl for BOTH winners and losers, then re-run this exact runner unchanged.

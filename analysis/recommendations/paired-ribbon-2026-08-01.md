# PAIRED RIBBON A/B — relax filter 5 + suppress ribbon_flip_back for level-anchored setups (2026-08-01)

**VERDICT: NULL** — pre-reg `analysis/recommendations/prereg-paired-ribbon-2026-08-01.json` frozen **2026-08-01 12:43:22 Saturday EDT** (e5e323f2 (runner did not exist at freeze commit)), runner `backtest/tools/paired_ribbon_ab_2026_08_01.py`.

ONE paired treatment, no grid (m=1): level-anchored setups lose the ribbon MA-stack veto at ENTRY (filter 5) **and** the ribbon_flip_back EXIT — they keep structure_stop, −50% catastrophe cap, TP1, chandelier trail, runner target, 15:40 time stop. Motivated by filter5-ribbon-2026-07-31's mechanism finding: 76.2% of entry-only-unlocked trades were round-tripped by the same lagging ribbon at exit.

## Windows

| window | control | paired | delta | added | dropped | exit-changed common | days +/− | p (1-sided) |
|---|--:|--:|--:|--:|--:|--:|:--|--:|
| full | $4,749.95 (n=192) | $5,250.60 (n=206) | **$+500.65** | 23 | 9 | 0 | 7/14 | 0.3889 |
| recent25 | $-630.40 (n=17) | $-573.40 (n=20) | **$+57.00** | 3 | 0 | 0 | 1/1 | 0.497 |

Added cohort (full, real exits): n=23 total=$-489.85 WR=0.2609 per-trade=$-21.30 ex-best=$-1,148.45
Common-trade exit deltas (full): n=0 total=$+0.00

## Gates

| gate | result | status |
|---|---|:--:|
| G1_recent_window_positive | delta_total_recent=57.0 | UNDETERMINED |
| G2_day_majority_recent | improved=1, worsened=1 | FAIL |
| G3_survives_drop_best_recent | delta_minus_best=-498.5, best_single_contribution=555.5 | FAIL |
| G4_runner_cohort_zero_tolerance | control_n=39, arm_n=42, control_total=18330.05, arm_total=20184.3, floor=1.0 | PASS |
| G5_fire_count_L243_both_levers | n_added_full=23, n_added_recent=3, exit_lever_fires_full=16, floors={'added_full': 10, 'added_recent': 2, 'exit_lever_full': 5} | PASS |

> **G1 is UNDETERMINED, not FAIL.** 4 of 7 raw entries this arm ADDS in the recent window could not be priced (no cached OPRA contract), so only 3 are in the measured delta of $+57.00. G1 is a strict SIGN test on that sum: the missing entries would only need to average $-14.25 each to flip it, which is well inside this book's per-trade dispersion. The sign is therefore UNDETERMINED on the evidence, not measured-negative.
>
> **UNCHANGED EITHER WAY. UNDETERMINED is not a PASS, the ship rule requires all five gates to pass, and G2/G3 fail independently on measured data. ARM_A still NULLs and filter 5 still STAYS. This is a GAP in the evidence, not a refutation of the verdict.**

## The exit lever — did the suppression itself fire? (G5b / L243)

- suppressed walks: **86** | outcomes changed vs a standard walk of the SAME entry: **16** full-window (3 recent) | P&L moved by the suppression alone: **$-109.45**

Exit transition matrix (standard walk → suppressed walk, changed trades only):

| transition | n | P&L delta |
|---|--:|--:|
| ribbon_flip_back -> structure_stop | 11 | $-982.00 |
| ribbon_flip_back -> runner_stop | 3 | $+1,339.05 |
| ribbon_flip_back -> time_stop_15:50 | 1 | $-210.00 |
| ribbon_flip_back -> premium_stop | 1 | $-256.50 |

## Where the entry-side delta comes from (added vs pre-empted)

- Added cohort total: **$-489.85**
- Pre-emption contribution: **$+990.50** (197.8% of the added−dropped part)

| exit reason | added cohort | control book |
|---|--:|--:|
| premium_stop | 1 (4.3%) | 93 (48.4%) |
| ribbon_flip_back | 1 (4.3%) | 19 (9.9%) |
| runner_stop | 4 (17.4%) | 35 (18.2%) |
| structure_stop | 15 (65.2%) | 35 (18.2%) |
| time_stop_15:50 | 2 (8.7%) | 6 (3.1%) |
| time_stop_15:50 (runner) | 0 (0.0%) | 4 (2.1%) |

## OPRA coverage — window-stratified exclusions

Every unpriceable entry is excluded from every total and NEVER Black-Scholes-synthesized; a measured delta covers the PRICEABLE subset only.

| window | arm | walked | excluded (no OPRA) | excluded (no SPY day) |
|---|---|--:|--:|--:|
| full | CONTROL | 192 | 20 | 0 |
| full | PAIRED | 206 | 25 | 0 |
| recent25 | CONTROL | 17 | 5 | 0 |
| recent25 | PAIRED | 20 | 8 | 0 |

| window | raw added entries | measurable | unmeasurable (no OPRA) | measurable % |
|---|--:|--:|--:|--:|
| full | 30 | 23 | 7 | 76.7% |
| recent25 | 7 | 3 | 4 | 42.9% |

Recent-25 days with ZERO cached OPRA coverage: 0 (none).

## Control parity

- raw entries 212 vs 07-31 anchor 211 (drift +1)
- walked 192 / $4,749.95 vs 07-31's 191 / $5,005.95 — raw/walked drift vs the 07-31 run is a CACHE-COVERAGE artifact: the concurrent OPRA backfill grew the cache (largely 2026-07-xx recent-window strikes) and use_real_fills reads cached premiums at ENTRY (simulator_real.py:420), falsifying the prereg anchor's 'cache-independent' premise -- disclosed deviation. The validity-bearing comparison is CONTROL-vs-PAIRED under ONE frozen cache view (freeze_contract_cache), which this run guarantees.

## Ship rule (frozen)

SHIP only if G1 AND G2 AND G3 AND G4 AND G5 all pass. Target: ONE fleet arm as a forward-paper TRIAL -- FLEET-LOOSE-R (display risky-3), the free loose-gate arm (bold-2 carries the block_elite_bull-lift trial, risky-1 carries the full-send experiment, safe-3 stays clean control). Wiring (built ONLY on a pass, never speculatively): re-add the filters.py scoped-bypass flag exactly as reverted + a per-entry exit-side ribbon-suppression flag threaded to that arm only, each with a RED-proofed guard test. KILL CRITERION (pre-registered): auto-revert if the arm's level-anchored cohort reaches (a) n>=10 fills with cumulative cohort P&L < $0, OR (b) 5 consecutive cohort losers, OR (c) any single day cohort P&L <= -$120 (2 catastrophe-cap losses at min size); the standing nightly gate-expiry/revalidation clock applies on top. If ANY gate fails: NULL -- filter 5 STAYS, ribbon_flip_back STAYS, and the ribbon question is declared CLOSED BOTH WAYS (entry-only null 2026-07-31, paired null 2026-08-01) in the graveyard with the numbers; no further ribbon-loosening variants without genuinely new information (a regime break in the population or a structural change to the exit stack).

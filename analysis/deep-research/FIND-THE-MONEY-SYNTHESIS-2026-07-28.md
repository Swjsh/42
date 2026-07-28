**THE MONEY IS LEVEL-TIED AND SCARCE: +$6,895 across 66 level-tied trades ($104/trade, WR .47–.56) is 136% of everything the engine ever made, while trendline-only entries — 65% of replay volume and 89% of live bear verdicts — bleed −$1,830 at WR .19 and die on a −20% premium stop that has ZERO winners in 88 tries; at 0.17 level-tied trades/day the honest run-rate is $13–18/day, so no evidenced path reaches $100–200/day yet — the binding constraint is level-tied setup FREQUENCY, and the deciding evidence is forward data from tonight's fixed SIP level feed.**

# FIND-THE-MONEY SYNTHESIS — 2026-07-28

Six evidence lanes, all adversarially verified. Zero refuted. Two claims downgraded (kept visible in §4).
Target lens: [`FOCUS-DOCTRINE.md`](../../markdown/doctrine/FOCUS-DOCTRINE.md) — $100–200/day = ONE clean +30% level trade at ~$2K.

---

## 1. Where the money is — the one picture

All numbers from the 390-day full-history replay (190 trades, +$5,064.75 — the on-disk artifact figure; the older +$5,307/191 brief number is stale) unless noted.

| Cohort | n | P&L | WR | $/trade | Source |
|---|---|---|---|---|---|
| **LEVEL-tied** | 57 | **+$5,098.05** | .47 | +$89 | [PNL-ATTRIBUTION-2026-07-28.json](PNL-ATTRIBUTION-2026-07-28.json) |
| **BOTH (level+TL)** | 9 | **+$1,796.80** | .56 | +$200 | same |
| **Trendline-only** | 124 | **−$1,830.10** | .19 | −$15 | same |
| — of which −20% premium stops | 88 | −$7,366.80 | .00 | −$84 | [EXIT-LEAK-2026-07-28.json](EXIT-LEAK-2026-07-28.json) |
| Runner-trail exits (the profit engine) | 35 | +$15,774.05 | 1.00 | +$451 | same |

- 🎯 **Two independent lanes converge on the SAME cohort**: the entry lane's trendline-only class IS the exit lane's premium-stop-only class (no trigger_level → structure stop never arms → −20% premium stop, 48.4% of gross loss).
- 🎯 **233 of 261 live bear ENTER verdicts ever are trendline-only** (core-decisions.jsonl, recounted twice) — live volume is concentrated in the losing class.
- 📉 **Run-rate reality**: full book $5,065/390d ≈ **$13/day**; last-90-days report card **+$1,630 = $18/day** ([DAY-CARDS-90D-2026-07-28.md](DAY-CARDS-90D-2026-07-28.md)). GREEN days average $423 and 14/15 met the $100 floor — when it fires on a level, it pays the goal. It fires far too rarely.
- 🚨 **The tension that blocks an immediate kill**: 2026 sub-window delta of the trendline-kill is −$143 and the last live month's trendline-only fills are **+$565 (n=35)** — plausibly because the broken IEX level feed (fixed tonight, 7b4aa3f4) was mislabeling level-tied fires as trendline-only. Forward data decides.

---

## 2. Ranked path toward $100–200/day — three moves, honestly priced

**Stated plainly first: the three moves below sum to roughly +$15–50/day at their honest ranges, on top of a $13–18/day base. No evidenced path reaches $100–200/day tonight. The binding constraint is level-tied setup frequency: 66 qualifying trades in 390 sessions (~1 per 6 days) at $104/trade, vs the ~1–2/day the goal needs (6–12× more). The ONE instrument to build is the forward level-tied opportunity counter on the fixed SIP feed (§5 headless item 3) — it decides whether the constraint was the broken feed or the market.**

### Move 1 — KILL singleton trendline-only bear entries (`min_triggers_bear` 1→2) — STAGED, flip-gated
| | |
|---|---|
| **Evidence** | Pre-registered A/B through the real two-layer pipeline, baseline reproduced the stored scorecard exactly (190/$5,064.75); delta **+$2,568.05**, all 4 gates PASS (day-majority 76/21, drop-best +$2,147, held-out +$652 to the cent), maxDD improves −$2,233→−$1,881. Verifier replicated every number. [min-triggers-bear2-ab-2026-07-28.json](min-triggers-bear2-ab-2026-07-28.json) |
| **Honest lift** | **−$1 to +$7/cal-day** (all improvement is 2025; 2026 sub-window −$143; expectation today ≈ $0 until the live/2026 tension resolves) |
| **Gate before arming** | Flip-gate as filed: ≥10 live sessions on the fixed SIP level feed, then re-slice NEW singleton-bear fills at n≥20. Still negative → flip the knob. Reclassified as level-tied → knob is moot, the win ships through the feed. Held-out is exhausted for this question — confirmatory = forward fills only. |
| **Replay next** | Nothing historical. Forward-only. |

### Move 2 — Pre-TP1 breakeven ratchet at +30% touch (exit repair, ONE cell)
| | |
|---|---|
| **Evidence** | 33 losers touched ≥+30% MFE and round-tripped to a stop: **−$3,829.60** (25 of them trendline premium-stops). Verified against raw OPRA bars. Critically, the blanket alternative is DEAD: exit-all-at-touch is negative at every threshold (+30%: −$4,943) — the ratchet is the only shape that protects the 35/35-winner runner tail. [EXIT-LEAK-2026-07-28.md](EXIT-LEAK-2026-07-28.md) |
| **Honest lift** | **$0 to +$10/cal-day** (the $9.8/day is the full-recovery upper bound; realistic capture is a fraction; could be $0 if BE fills slip) |
| **Gate before arming** | Pre-register the ONE cell (extend `profit_lock_arm_scope`, BE floor arms at first +30% point-sample touch); 4-gate bar; **anchor-no-regression on the 35 RUNNER_TRAIL winners (+$15,774 must not degrade)**; confirmatory set = FRESH forward fills (this population's held-out is exhausted for exit questions). |
| **Replay next** | `exit_manager_walk` replay at live scope, tomorrow headless. |

### Move 3 — Post-stop REARM (one re-entry while the day's level story is intact)
| | |
|---|---|
| **Evidence** | #1 day-level leak, survives drop-best: 9 EXIT_LEFT_MONEY days surrendered $8,173, **7/9 are stopped-out-then-the-same-contract-ran** (06-09: −$390 stop then +$3,336 run; 06-17: −$355 then +$1,268; 05-04: −$232 then +$1,472); $4,837 without the best day. Bound is oracle-flavored (peak-picking), NOT realizable P&L. [DAY-CARDS-90D-2026-07-28.md](DAY-CARDS-90D-2026-07-28.md) |
| **Honest lift** | **$0 to +$20/cal-day** — widest error bars of the three; a diagnostic bound, not a forecast; could easily pre-reg to a null (re-entries in J's own history were part of the C31 killer, so the "level story intact" condition is load-bearing) |
| **Gate before arming** | Full pre-reg (hypothesis + bar BEFORE running) via exit_manager replay at live scope: positive aggregate AND day-majority AND drop-best AND held-out/forward positive. Rule 4 (no adding w/o new trigger) constrains the design: the re-entry must require a fresh confirmed trigger at the SAME level, max ONE per day. |
| **Replay next** | Headless pre-reg cell tomorrow + film-room validation of the 9 days with J (§5). |

---

## 3. The graveyard — do not re-litigate

| # | Hypothesis | Cause of death | Artifact |
|---|---|---|---|
| 1 | Broad score ladder (floors 7/8/9) | Loses at EVERY floor: −$31,015 / −$16,642 / −$10,903; disarmed f030ae6c | analysis/arm-ladder/LADDER-FULLHIST-2026-07-27.json |
| 2 | Ladder subset (score≥9 + confluence + htf BEAR) | −$3,864 / 109tr, WR .22, all 3 frozen gates FAIL; strictly-causal recheck is WORSE (−$4,154). Ladder dead at every expressible granularity | analysis/arm-ladder/LADDER-SUBSET-VERDICT-2026-07-28.md |
| 3 | "Historical level quality was the binding constraint" | Shelf-augmented as-of-date levels: delta −$466.60 over 390d, paired-t −0.27, sign flips on one day = statistically zero | LEVELS-V2-RETRO-2026-07-28.md |
| 4 | Zone-banding `detect_level_rejection` (10c/25c) | −$418 / −$1,141 net, dose-response monotone negative; mechanism is L96 cascade interference, not zone signal | ZONE-WIDTH-2026-07-28.md |
| 5 | Take profit earlier (exit-all-at-touch, any threshold) | Negative at ALL thresholds (+10%: −$9,977; +30%: −$4,943; +100%: −$1,097) — destroys the tail that pays the book | EXIT-LEAK-2026-07-28.md |
| 6 | "−50% catastrophe rides are the exit leak" | 4 trades, −$1,218, 8% of gross loss — exonerated; the leak is the −20% premium stop | EXIT-LEAK-2026-07-28.md |
| 7 | A6 tighter-trendline-exit (kitchen ACCRETE) | Held-out FAILS on its own trendline cohort (−$92.45); the kitchen pass (+$100.45) was 100% structure-tier trail effects (+$192.90). Disposition: revise to KILL/park | EXIT-LEAK-2026-07-28.md |
| 8 | Filter-5 (5m ribbon) as the 07-27 villain | 90-day scale: oracle +$333, first-shot −$624 — the incident does not generalize | DAY-CARDS-90D-2026-07-28.md |
| 9 | Filter-8 (VIX gate) relaxation as the #2 leak | Verifier-corrected: implementable cell only +$476 (5/13 win days), FAILS drop-best — weak hypothesis, demoted | DAY-CARDS review, §4 |
| 10 | 181 pre-registered exit/entry cells (98 edge-matrix + 83 kitchen) | Zero ships; 23 BH-significant were ALL losers | markdown/research/EDGE-MATRIX-FULLHIST-2026-07-23.md |
| 11 | Crypto-twin 72-cell signal backtest (120d real BTC) | Honest null, 0 pass | commit 8f889d5f |
| 12 | Ladder held-out "regime rescue" (2026-03-06+ positivity) | NOT dead but NOT usable: data-suggested, requires fresh pre-reg on a window frozen before looking; this run may not serve as that pre-reg | LADDER-SUBSET-VERDICT-2026-07-28.md caveats |

---

## 4. What the verifiers refuted or downgraded — kept visible

**Refuted outright: nothing.** All six lanes' headline numbers replicated exactly from underlying data. Downgrades and defects:

| Lane | Correction | Consequence |
|---|---|---|
| **day-cards** | 🔻 **DOWNGRADE**: filter-8 "first-shot +$2,859" was hindsight-tinged 3 ways (end-of-day modal blocker selects the day; 4/17 days substituted first PRICED candidate; 8/17 candidates carried OTHER blockers). Implementable cell = **+$476, fails drop-best** | Filter-8 relax drops out of the top-3 moves; must NOT feed LADDER-SUBSET-PREREG at the $2,859 figure. Exits finding + filter-5 exoneration stand as measured |
| **ladder-subset** | 🚨 **C6 leak found (verdict-safe)**: `_precompute_htf_15m_stacks` leaks up to 10 min of 15m-bar future on 70/109 trigger bars. Strict-causal recompute is WORSE (−$4,154) — the leak flattered the FAILED hypothesis, so the kill is conservative | **Systemic debt**: every backtest gating on `htf_15m` carries this leak. Fix + guard test = tomorrow's headless item 4 |
| **zone-width** | Fire counts double-logged ~2×: true unique fires ≈ 3,411 (10c) / 6,689 (25c), not 6,822/13,378 | Diagnostic counter only; zero P&L involvement; kill stands |
| **levels-v2** | New-trade loss driver mislabeled: C28 cohort actually made +$743; real driver is confluence+level_rejection (−$1,415). Guard suite blind to an `<=` off-by-one (shipped code clean). Drop-best-day (−$1,113) omitted next to drop-worst (+$151) | Null verdict unchanged; tighten the as-of-date guard test when next touched |
| **exit-leak** | Prereg timestamp incoherent (written_et postdates the run); `generated_at_et` used naive local time (et_clock violation, metadata only); "ZERO winners" in PS20 partly mechanical | All gate values reproduced independently; verdict stands. Future preregs must carry a verifiable et_clock timestamp |
| **attribution** | Held-out dates touched by descriptive slicing BEFORE the A/B prereg (disclosed; the contaminated prediction pointed the WRONG way). Frozen held-out no longer virgin for min-triggers/trigger-class variants | Confirmatory evidence for Move 1 must be FORWARD live fills — exactly what the flip-gate specifies |

---

## 5. Tomorrow (2026-07-28) — concrete list

### Film-room / dojo — J's TV bar-replay (Plus plan, his surface)
1. **The 3 stopped-then-ran days**: 2026-06-09, 06-17, 05-04, tick-by-tick. Question for J at each stop-out: *was there a takeable re-entry trigger at the original level?* His verdicts pre-register Move 3's "level story intact" condition (two-lane harvest per dojo spec — his calls are the policy pre-regs).
2. **07-27 replayed with the FIXED level feed**: draw the SIP-derived zones (state each line's flavor, body vs wick, per standing rule); was 744.9 the one clean trade? Filter-5 blocked it live and is exonerated at 90-day scale — the film room answers whether 07-27 was the exception worth a narrow carve-out or noise.
3. **Class contrast reel**: 5 level-tied winners vs 5 trendline-only premium-stop losers from the replay, so J sees with his own eyes the cohort split the whole synthesis rests on.

### Headless (after-hours, no market-hours fires)
1. **Move 2 pre-reg + run**: BE-ratchet cell via `exit_manager_walk` at live scope; anchor-no-regression on the 35 runner-trail winners; et_clock timestamp in the prereg block this time.
2. **Move 3 pre-reg + run**: post-stop REARM cell, one re-entry max, fresh-trigger-required design (Rule 4-compliant).
3. **Build the ONE instrument**: daily level-tied opportunity counter on the fixed SIP feed — logs every qualifying level-tied setup/day forward + its sim outcome. This is what resolves both the binding constraint and Move 1's flip-gate. (Crypto-twin ladder-sim ee45de3c keeps accruing the HTF-gate comparison for free — read-only, no action.)
4. **Fix the systemic C6**: `_precompute_htf_15m_stacks` same-bar leak → match the causal per-bar convention + graduated guard test; queue item filed.
5. **Revise A6's disposition** in the kitchen accrete list to reflect §3 row 7.

### Arms / stays off
- **ARMS: NOTHING.** No knob flips, no live-config edits tonight (verified: all six lanes committed pathspec-scoped to new analysis/tools/tests only; params.json untouched).
- **Staged with REVOKE surface**: `min_triggers_bear` 1→2 recommendation on file at [min-triggers-bear2-ab-2026-07-28.json](min-triggers-bear2-ab-2026-07-28.json) with its explicit flip-gate. J's REVOKE = say kill / delete the staged rec; otherwise the gate (not the calendar) decides.
- **STAYS OFF**: broad ladder (disarmed f030ae6c — stays dead), all ladder subsets, zone bands, A6, any 2026-03-06+ "regime" variant (needs fresh pre-reg), filter-8 relaxation.

---

*Discipline notes: entry+1 strict convention and real-OPRA-only P&L held in every lane (verifier-checked). The full-history replay's entry layer remains PROVISIONAL vs live (07-17 anchors 1/4) — cohort CONTRASTS are the signal, absolute dollars are not. Held-out for this population is EXHAUSTED for exit-shape and trigger-class questions: all confirmatory evidence from here is forward live fills.*

---

Good morning J, Gamma here — six replay lanes ran overnight and were adversarially verified, and the answer is finally clean: every dollar this engine ever made came from level-tied trades, about a hundred and four dollars each, while trendline-only entries, two thirds of our volume, bleed out on a minus-twenty-percent premium stop that has never once produced a winner in eighty-eight tries.
The graveyard grew a lot tonight: every ladder variant, zone-banded triggers, retro level repair, and taking profit earlier all tested dead, so none of them get re-litigated.
Three moves survived with honest price tags: killing singleton trendline bears is staged behind a flip-gate, a breakeven ratchet at plus thirty percent targets the thirty-three trades that were green and died, and one disciplined re-entry after a stop-out targets the days we got stopped and the move ran without us — together maybe fifteen to fifty dollars a day, which I will not oversell.
The real bottleneck is frequency: we find one level-tied setup every six sessions and the goal needs one or two a day, so the deciding evidence is whether the SIP level feed I fixed last night surfaces more real setups this week — the counter goes live today.
Nothing armed overnight and nothing needs your yes; your one lever today is the film room — replay June ninth, June seventeenth, and July twenty-seventh on bar replay and tell me which re-entries you would actually have taken.
Losing day equals losing day: the engine's honest run rate is thirteen to eighteen dollars a day right now, but this is the first morning we can say exactly where the money is and exactly what is in the way.

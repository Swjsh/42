# FILTER 5 (ribbon MA-stack) — cost measurement + fate decision (2026-07-31)

Pre-reg `analysis/recommendations/prereg-filter5-ribbon-2026-07-31.json` frozen **2026-07-31 17:34 Friday EDT**, before any run. Runner: `backtest/tools/filter5_ribbon_fate_2026_07_31.py`.

## What filter 5 is
- **BULL** (`filters.py:1174`): `if ctx.ribbon_now is None or ctx.ribbon_now.stack != 'BULL': blockers.append(5)`
- **BEAR** (`filters.py:1463`): `if not (ribbon_bear_ok or structure_shift_bear is not None): blockers.append(5)  -- ribbon_bear_ok = stack == 'BEAR'; the structure_shift OR-alternative is flag-gated (default OFF) and byte-identical to the original when off`
- Ribbon: backtest/lib/ribbon.py -- Saty Pivot Ribbon, EMA fast=13 / pivot=20 / slow=48 on 5-min SPY closes. stack='BULL' iff fast>pivot>slow STRICTLY; 'BEAR' iff fast<pivot<slow STRICTLY; otherwise 'MIXED'. So filter 5 demands a STRICT 3-EMA ordering at the trigger bar, on the same side as the trade.
- Existing precedent: filters.py ~1609-1634 trendline_only_setup: when trendline_rejection is the ONLY level-tied trigger, blockers 5, 8 and 9 are REMOVED and replaced with a -1 score demerit each. A scoped, trigger-conditional bypass of filter 5 already exists in production and has since 2026-05-09. BEAR PATH ONLY -- the bull path has NO bypass of any kind.

## Provenance
**Filter 5 has NO ratification scorecard. It is inherited doctrine, not an evidence-armed gate.**
- git log -S'blockers.append(5)' -- backtest/lib/filters.py returns ONE commit (d0c8ac06 'evening snapshot 2026-06-15'), a squashed snapshot, not an arming commit. Total commit count for filters.py is 9 -- the file predates granular history.
- analysis/recommendations/ contains 36 ribbon-* / filter-* scorecards. NONE of them arms filter 5. They tune ADJACENT knobs (spread minimum, flip detection, momentum, duration, buffer) or test bypasses OF filter 5.
- The only scorecard that measures filter-5-blocked setups at all is structure-shift-cascade-ab-2026-07-28.json -- and that tests a RELAXATION of filter 5, presupposing the gate. It never validated the gate itself.

Under J's standing rule (memory: kill_reentry_lock_gate_provenance_2026_07_02 -- 'every gate needs provenance + evidence or it dies'), filter 5 currently has neither. It survives only if THIS study's measurement earns it.

## Cohort A — setups filter 5 blocked ALONE (blockers == [5])

| side | bars (full) | days (full) | bars (recent 25d) | days (recent) |
|---|--:|--:|--:|--:|
| bull | 173 | 77 | 28 | 12 |
| bear | 76 | 42 | 24 | 10 |

> **CORRECTED 2026-07-31 (n-inflation).** The first run of this study reported these BAR counts at exactly **2x** — 346 bull / 152 bear full-window and 56 / 48 recent — because the capture monkeypatch patches both `lib.orchestrator` and `lib.engine.score` and the per-bar parity cross-check drives every bar through both bindings, appending each qualifying bar twice. DAY counts were never affected (a set of dates absorbs the duplicate), which is why it survived review: only the bar counts were wrong, and they were the ones quoted to J. Deduped at source by `Blockers5Capture`, guarded by `backtest/tests/test_filter5_capture_no_double_count.py`. **No gate, delta or verdict depended on these counts — they are descriptive only.**

## Cohort B — the book filter 5 ALLOWED (CONTROL)

| window | n | total | WR | per-trade | total ex-best |
|---|--:|--:|--:|--:|--:|
| full | 191 | $5,005.95 | 0.2932 | $26.21 | $4,146.00 |
| recent25 | 17 | $-630.40 | 0.2353 | $-37.08 | $-1,119.80 |

## Where the delta actually comes from (artifact hunt)

- Trades filter 5 was ACTUALLY blocking (added cohort): **$103.60**
- Control trades that merely VANISH (pre-empted by an unlocked earlier entry): $-635.00 -> contributes **$+635.00** (86.0% of the delta)
- Pre-empted days that also carry an added trade: **6 of 6**

| exit reason | added cohort | control book |
|---|--:|--:|
| premium_stop | 0 (0.0%) | 93 (48.7%) |
| ribbon_flip_back | 16 (76.2%) | 19 (9.9%) |
| runner_stop | 1 (4.8%) | 35 (18.3%) |
| structure_stop | 3 (14.3%) | 34 (17.8%) |
| time_stop_15:50 | 1 (4.8%) | 6 (3.1%) |
| time_stop_15:50 (runner) | 0 (0.0%) | 4 (2.1%) |

**The gate's own block-set (the ADDED cohort) is worth ~$0/trade. Essentially ALL of the positive full-window delta is pre-emption: unlocked entries occupy the single-position slot and prevent later CONTROL losers from ever being taken, on days that also carry an added trade. That is a sequencing side-effect, not evidence that filter 5 blocks money. Separately, the added cohort's exit mix is dominated by ribbon_flip_back versus the control book's premium_stop -- entries admitted against a non-stacked ribbon are closed by the ribbon-flip EXIT almost immediately. The entry veto and the exit rule read the SAME lagging indicator, so removing the veto alone mostly manufactures round-trips.**

### ⚠️ The by-product that outlives the null: filter 5 is largely REDUNDANT with the ribbon-flip EXIT

**76.2% of the trades this deletion unlocks exit on `ribbon_flip_back` (n=16), against 9.9% of the control book (n=19).** The entry veto and the exit rule read the SAME lagging ribbon, so a setup admitted against a non-stacked ribbon is closed by that ribbon within minutes. The block-set does not get a chance to be right or wrong — it gets round-tripped.

**This pre-refutes any future "loosen the ribbon" that moves only the entry gate.** Relaxing filter 5 while `ribbon_flip_back` still owns the exit will null the same way this arm did, for this mechanism, no matter how the entry gate is scoped. The only version of that change worth running is the PAIRED one: relax the entry gate AND suppress the ribbon-flip exit for the same cohort, in ONE pre-registered change. That paired arm has never been measured. (L243's shape, on the exit side.)

## Arms

### ARM_A_delete — **NULL**

| window | control | arm | delta | added | dropped | days +/- |
|---|--:|--:|--:|--:|--:|:--|
| full | $5,005.95 (n=191) | $5,744.55 (n=204) | **$+738.60** | 21 | 8 | 10/9 |
| recent25 | $-630.40 (n=17) | $-698.40 (n=20) | **$-68.00** | 3 | 0 | 1/1 |

Added-trade cohort (full window, real exits): n=21 total=$103.60 WR=0.5238 per-trade=$4.93 ex-best=$-437.00

| gate | result | status |
|---|---|:--:|
| G1_recent_window_positive | delta_total_recent=-68.0 | UNDETERMINED |
| G2_day_majority_recent | improved=1, worsened=1 | FAIL |
| G3_survives_drop_best_recent | delta_minus_best=-122.0 | FAIL |
| G4_runner_anchor_no_regression | control_n=39, arm_n=39, control_total=18330.05, arm_total=18488.25 | PASS |
| G5_fire_count | n_added_full=21, n_added_recent=3, floor_full=10, floor_recent=2 | PASS |

> **G1 is UNDETERMINED, not FAIL.** 4 of 7 raw entries this arm ADDS in the recent window could not be priced (no cached OPRA contract), so only 3 are in the measured delta of $-68.00. G1 is a strict SIGN test on that sum: the missing entries would only need to average $+17.00 each to flip it, which is well inside this book's per-trade dispersion. The sign is therefore UNDETERMINED on the evidence, not measured-negative.
>
> **UNCHANGED EITHER WAY. UNDETERMINED is not a PASS, the ship rule requires all five gates to pass, and G2/G3 fail independently on measured data. ARM_A still NULLs and filter 5 still STAYS. This is a GAP in the evidence, not a refutation of the verdict.**

### ARM_B_level_anchored_bypass — **NULL** (RUN_2026_07_31_THEN_FLAG_REVERTED)

- full delta $+738.60 (added 21, dropped 8)
- recent25 delta $-68.00 (added 3)
- gates: G1_recent_window_positive=UNDETERMINED, G2_day_majority_recent=FAIL, G3_survives_drop_best_recent=FAIL, G4_runner_anchor_no_regression=PASS, G5_fire_count=PASS

> **G1 is UNDETERMINED, not FAIL.** Inherits ARM_A's recent-window measurability gap verbatim: this arm measured byte-identical to ARM_A (same 21 added / 8 dropped trades), so it adds the SAME raw entries in the recent window and the same ones are unpriceable for want of a cached OPRA contract. See `opra_measurability` for the live numbers. Not a PASS either way -- the arm still NULLs and filter 5 stays. UNCHANGED. UNDETERMINED is not a PASS; G2 and G3 fail independently on measured data and the ship rule needs all five. ARM_B NULLs.

Structural, not coincidental. detect_ribbon_flip_bullish requires ribbon_history[-1].stack == 'BULL' (filters.py ~796), so when filter 5 blocks a bull setup the ribbon_flip trigger CANNOT be in its trigger set -- min_triggers=2 must therefore have been met by {level_reclaim, confluence, sequence_reclaim}. Every bull setup filter 5 alone blocks is level-anchored BY CONSTRUCTION. On the bear side the trendline-only cohort already has its own filter-5 relaxation (2026-05-09). Scoping the bypass to level-anchored setups therefore excludes nothing that deletion admits.

## OPRA coverage — window-stratified exclusions (why G1 is UNDETERMINED)

Every entry with no cached OPRA contract is excluded from every total and is NEVER Black-Scholes-synthesized. That is the right call for P&L honesty, but it means a measured delta covers only the PRICEABLE subset of an arm's book — so the exclusions have to be shown per window, not as one lump total.

| window | arm | walked | excluded (no OPRA) | excluded (no SPY day) |
|---|---|--:|--:|--:|
| full | CONTROL | 191 | 20 | 0 |
| full | ARM_A | 204 | 25 | 0 |
| recent25 | CONTROL | 17 | 5 | 0 |
| recent25 | ARM_A | 20 | 8 | 0 |

**The entries the arm ADDS — how many are even measurable:**

| window | raw added entries | measurable | unmeasurable (no OPRA) | measurable % |
|---|--:|--:|--:|--:|
| full | 27 | 21 | 6 | 77.8% |
| recent25 | 7 | 3 | 4 | 42.9% |

Recent-window added entries that could NOT be priced:

| date | entry (ET) | side | contract | reason |
|---|---|---|---|---|
| 2026-07-24 | 2026-07-24T12:10:00 | P | `SPY260724P00743000` | no_opra |
| 2026-07-27 | 2026-07-27T10:25:00 | P | `SPY260727P00738000` | no_opra |
| 2026-07-28 | 2026-07-28T09:35:00 | P | `SPY260728P00738000` | no_opra |
| 2026-07-31 | 2026-07-31T09:50:00 | P | `SPY260731P00742000` | no_opra |

**The coverage collapse** — cached contracts per trading day, recent 25 days:

| day | cached contracts |
|---|--:|
| 2026-06-26 | 22 |
| 2026-06-29 | 22 |
| 2026-06-30 | 22 |
| 2026-07-01 | 22 |
| 2026-07-02 | 22 |
| 2026-07-06 | 22 |
| 2026-07-07 | 22 |
| 2026-07-08 | 22 |
| 2026-07-09 | 22 |
| 2026-07-10 | 22 |
| 2026-07-13 | 22 |
| 2026-07-14 | 22 |
| 2026-07-15 | 26 |
| 2026-07-16 | 30 |
| 2026-07-17 | 62 |
| 2026-07-20 | 30 |
| 2026-07-21 | 26 |
| 2026-07-22 | 24 |
| 2026-07-23 | 3  ⬅ **collapse** |
| 2026-07-24 | 0  ⬅ **ZERO** |
| 2026-07-27 | 0  ⬅ **ZERO** |
| 2026-07-28 | 2  ⬅ **collapse** |
| 2026-07-29 | 3  ⬅ **collapse** |
| 2026-07-30 | 0  ⬅ **ZERO** |
| 2026-07-31 | 4  ⬅ **collapse** |

**3 trading days in the decisive recent window have ZERO cached OPRA coverage** (2026-07-24, 2026-07-27, 2026-07-30) — no arm can be measured on them at all. Coverage runs ~22–30 contracts/day through 2026-07-22 and then falls to single digits. **The recent window is exactly the stretch J's dynamic-market directive weights hardest, and it is the worst-covered stretch in the study.** An OPRA backfill is the single highest-value input to re-deciding this gate; nothing else about the design needs to change.

## 2026-07-31 forensics (ARM_A) — walked vs excluded vs refused

**CORRECTED.** The first run of this study reported *"zero trades on 2026-07-31 in ANY arm"* and read that as a gate holding. That was true only of the WALKED book. Reporting a data hole as a gating decision is the C7 silent-success shape, so the three cases are now separated by construction.

**Entries WALKED:** 0

**Entries PRODUCED then EXCLUDED for missing data (NOT refused by a gate):** 1

| entry (ET) | side | contract | setup | triggers | reason |
|---|---|---|---|---|---|
| 2026-07-31T09:50:00 | P | `SPY260731P00742000` | BEARISH_REJECTION_RIDE_THE_RIBBON::BS_FALLBACK | level_rejection, confluence | **no_opra** |

**Gate REFUSALS — named cohort gates that refused a qualifying setup. THIS is the actual gating evidence:** 11 (plus 68 bars that simply never cleared scoring — routine, not a gate decision)

| bar (ET) | setup | triggers | level | blockers | action |
|---|---|---|--:|---|---|
| 2026-07-31 09:40:00-04:00 | BEARISH_REJECTION_RIDE_THE_RIBBON | level_rejection | 744.11 | `LEVEL_REJECTION_GATE` | `SKIP_LEVEL_REJECTION_GATE` |
| 2026-07-31 09:45:00-04:00 | BEARISH_REJECTION_RIDE_THE_RIBBON | level_rejection | 742.79 | `LEVEL_REJECTION_GATE` | `SKIP_LEVEL_REJECTION_GATE` |
| 2026-07-31 10:20:00-04:00 | BULLISH_RECLAIM_RIDE_THE_RIBBON | level_reclaim, confluence | 738.85 | `BLOCK_ELITE_BULL` | `SKIP_ELITE_BULL_LEVEL_RECLAIM` |
| 2026-07-31 11:35:00-04:00 | BULLISH_RECLAIM_RIDE_THE_RIBBON | level_reclaim, ribbon_flip, confluence | 741.34 | `BLOCK_BULL_1100_1200` | `SKIP_BULL_1100_1200` |
| 2026-07-31 12:30:00-04:00 | BULLISH_RECLAIM_RIDE_THE_RIBBON | level_reclaim, confluence | 744.68 | `BLOCK_ELITE_BULL` | `SKIP_ELITE_BULL_LEVEL_RECLAIM` |
| 2026-07-31 13:00:00-04:00 | BULLISH_RECLAIM_RIDE_THE_RIBBON | level_reclaim, confluence | 744.68 | `BLOCK_ELITE_BULL` | `SKIP_ELITE_BULL_LEVEL_RECLAIM` |
| 2026-07-31 13:10:00-04:00 | BULLISH_RECLAIM_RIDE_THE_RIBBON | level_reclaim, confluence | 744.68 | `BLOCK_ELITE_BULL` | `SKIP_ELITE_BULL_LEVEL_RECLAIM` |
| 2026-07-31 13:20:00-04:00 | BULLISH_RECLAIM_RIDE_THE_RIBBON | level_reclaim, confluence | 745.53 | `BLOCK_ELITE_BULL` | `SKIP_ELITE_BULL_LEVEL_RECLAIM` |
| 2026-07-31 14:00:00-04:00 | BULLISH_RECLAIM_RIDE_THE_RIBBON | level_reclaim, confluence | 745.53 | `BLOCK_ELITE_BULL` | `SKIP_ELITE_BULL_LEVEL_RECLAIM` |
| 2026-07-31 14:05:00-04:00 | BULLISH_RECLAIM_RIDE_THE_RIBBON | level_reclaim, confluence | 745.53 | `BLOCK_ELITE_BULL` | `SKIP_ELITE_BULL_LEVEL_RECLAIM` |
| 2026-07-31 14:15:00-04:00 | BULLISH_RECLAIM_RIDE_THE_RIBBON | level_reclaim, confluence | 745.80 | `BLOCK_ELITE_BULL` | `SKIP_ELITE_BULL_LEVEL_RECLAIM` |

> An entry under `entries_excluded_for_missing_data` was PRODUCED by the arm and then dropped for want of a cached contract. It is NOT evidence that a gate held; quoting it as such reports a data hole as a gating decision. Gate evidence lives in `gate_refusals`, which names the blocker that actually fired.

## ARM_C (structure-shift replacement) — not run

DROPPED BEFORE RUNNING, not silently omitted. Exactly this semantics -- the market_structure shift as an OR-alternative to filter 5 inside the full cascade -- was already pre-registered and tested on 2026-07-28 (prereg-structure-shift-cascade-2026-07-28.json / structure-shift-cascade-ab-2026-07-28.json). Verdict: delta -$46.00 over the full population, g1 FAIL, g3 FAIL (delta-minus-best -$625), g4 FAIL, g5 FAIL. That study's own note records that the BULL side was a no-op there because the staged wiring waives only the HTF demerit on bull, never filter 5. Re-running it would be retesting a graveyard entry. Option (c) is therefore answered by prior evidence for bear and is NOT re-tested; the bull-side filter-5 question it never touched is covered by ARM_A and ARM_B here.

## Ship rule

An arm SHIPS only if G1 AND G2 AND G3 AND G4 AND G5 all pass. If more than one arm passes, ship the one with the higher RECENT-window delta. If NO arm passes, filter 5 STAYS (option d) and the null goes in the graveyard verbatim -- including the case where deletion looks good on the aggregate but fails the recent window.

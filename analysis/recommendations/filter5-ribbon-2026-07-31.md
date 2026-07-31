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
| bull | 346 | 77 | 56 | 12 |
| bear | 152 | 42 | 48 | 10 |

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

## Arms

### ARM_A_delete — **NULL**

| window | control | arm | delta | added | dropped | days +/- |
|---|--:|--:|--:|--:|--:|:--|
| full | $5,005.95 (n=191) | $5,744.55 (n=204) | **$+738.60** | 21 | 8 | 10/9 |
| recent25 | $-630.40 (n=17) | $-698.40 (n=20) | **$-68.00** | 3 | 0 | 1/1 |

Added-trade cohort (full window, real exits): n=21 total=$103.60 WR=0.5238 per-trade=$4.93 ex-best=$-437.00

| gate | result | pass |
|---|---|:--:|
| G1_recent_window_positive | delta_total_recent=-68.0 | FAIL |
| G2_day_majority_recent | improved=1, worsened=1 | FAIL |
| G3_survives_drop_best_recent | delta_minus_best=-122.0 | FAIL |
| G4_runner_anchor_no_regression | control_n=39, arm_n=39, control_total=18330.05, arm_total=18488.25 | PASS |
| G5_fire_count | n_added_full=21, n_added_recent=3, floor_full=10, floor_recent=2 | PASS |

### ARM_B_level_anchored_bypass — **NULL** (RUN_2026_07_31_THEN_FLAG_REVERTED)

- full delta $+738.60 (added 21, dropped 8)
- recent25 delta $-68.00 (added 3)
- gates: G1_recent_window_positive=FAIL, G2_day_majority_recent=FAIL, G3_survives_drop_best_recent=FAIL, G4_runner_anchor_no_regression=PASS, G5_fire_count=PASS

Structural, not coincidental. detect_ribbon_flip_bullish requires ribbon_history[-1].stack == 'BULL' (filters.py ~796), so when filter 5 blocks a bull setup the ribbon_flip trigger CANNOT be in its trigger set -- min_triggers=2 must therefore have been met by {level_reclaim, confluence, sequence_reclaim}. Every bull setup filter 5 alone blocks is level-anchored BY CONSTRUCTION. On the bear side the trendline-only cohort already has its own filter-5 relaxation (2026-05-09). Scoping the bypass to level-anchored setups therefore excludes nothing that deletion admits.

## ARM_C (structure-shift replacement) — not run

DROPPED BEFORE RUNNING, not silently omitted. Exactly this semantics -- the market_structure shift as an OR-alternative to filter 5 inside the full cascade -- was already pre-registered and tested on 2026-07-28 (prereg-structure-shift-cascade-2026-07-28.json / structure-shift-cascade-ab-2026-07-28.json). Verdict: delta -$46.00 over the full population, g1 FAIL, g3 FAIL (delta-minus-best -$625), g4 FAIL, g5 FAIL. That study's own note records that the BULL side was a no-op there because the staged wiring waives only the HTF demerit on bull, never filter 5. Re-running it would be retesting a graveyard entry. Option (c) is therefore answered by prior evidence for bear and is NOT re-tested; the bull-side filter-5 question it never touched is covered by ARM_A and ARM_B here.

## Ship rule

An arm SHIPS only if G1 AND G2 AND G3 AND G4 AND G5 all pass. If more than one arm passes, ship the one with the higher RECENT-window delta. If NO arm passes, filter 5 STAYS (option d) and the null goes in the graveyard verbatim -- including the case where deletion looks good on the aggregate but fails the recent window.

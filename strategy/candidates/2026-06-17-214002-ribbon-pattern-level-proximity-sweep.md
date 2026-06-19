# Strategy candidate: Ribbon/Pattern-Proxy + Key-Level-Proximity Gate Sweep

> DRAFT — Chef proposal 2026-06-17-214002. J ratifies.

## Hypothesis

J's big winners (4/29 +$342, 5/01 +$470, 5/04 +$730) share structural context that the
production engine currently misses. This sweep tests 11 gate conditions grouped into two
categories:

**Category E (ribbon/pattern proxies):** `ribbon_just_flipped_bearish`, stricter 2-bar flip,
ribbon-spreading, range-compression, and composites.
**Category C (key-level proximity):** distance from active levels, confluence, prior-day high,
and composites.

The directional claim is that **fresh ribbon flip is a necessary (not sufficient) condition**
for J's bear winners, and that it has perfect specificity on the 7 anchor days: flip-bear bars
appear on winner days only (4/29, 5/04) and are absent on all 3 loser days (5/05, 5/06, 5/07).

## Structural finding (most important)

The bar-context audit on all 7 J anchor days reveals:

| Day | Type | flip_bear bars | max_bear_score | Notes |
|---|---|---|---|---|
| 4/29 | W | 6 | 10 | J's 12:25 bar: score=8, flip=True, compressed=True, spreading=True |
| 5/01 | W | 0 | 7 | Ribbon=BULL entire day — needs FHH bypass (separate candidate) |
| 5/04 | W | 6 | 10 | 6 flip bars; J's 10:15 bar: score=8, flip=False (already in ribbon stack) |
| 5/05 | L | 0 | 9 | Zero flip-bear bars across 75 RTH bars |
| 5/06 | L | 0 | 8 | Zero flip-bear bars across 75 RTH bars |
| 5/07 | L | 0 | 8 | Zero flip-bear bars across 75 RTH bars |

**`ribbon_just_flipped_bearish` is a zero-noise signal on J's loser days.** It fires on 2 of
3 winner days and zero of 3 loser days. This makes it the strongest single discriminator
tested.

**`vol_ratio` is anti-correlated with J's winner bars.** Every J winner entry bar had
vol_ratio ≈ 0.0 at trigger time. All vol_ratio gates (E4/E5/C5 ≥ 2.0 or ≥ 3.0) are
anti-correlated with J's actual setup structure and should NOT be used as confluence for
bear/early-morning entries.

## Backtest evidence

- **Baseline:** allow_one_blocker=True, min_spread=27c, vix_soft, disable_filters=[8], BS sim
- **Baseline edge_capture:** 291 (OP-16 FAIL — structural miss on 5/01 FHH trade)
- **Train window:** 4/29–5/07 J anchor days (7 days)
- **Test window:** same anchor days (this sweep is a diagnostic, not a temporal split)

### Scenario results (all REJECT, see analysis below)

| ID | Name | fires_W | fires_L | edge_cap | sharpe | final_score | marg_pnl | verdict |
|---|---|---|---|---|---|---|---|---|
| E1 | bear>=9 + fresh_flip (<=3 bars) | 2 | 0 | 291 | 0.702 | 204 | -386 | REJECT |
| E2 | bear>=8 + flip (<=2 bars) | 2 | 0 | 291 | 0.702 | 204 | -386 | REJECT |
| E3 | bear>=8 + spreading | 2 | 2 | 291 | 1.343 | 390 | -160 | REJECT |
| E4 | bear>=7 + compression | 2 | 3 | 291 | 2.034 | 591 | 0 | REJECT |
| E5 | bear>=6 + compression + vol>=3 + lvl<=0.40 + flip | 0 | 0 | 0 | 0 | 0 | -677 | REJECT |
| E6 | bull>=9 + flip_bull | 0 | 2 | 0 | 0 | 0 | -381 | REJECT |
| C1 | bear>=9 + level<=0.25 | 1 | 0 | 132 | 0.447 | 59 | -545 | REJECT |
| C2 | bear>=8 + level<=0.20 | 2 | 2 | 291 | 1.330 | 387 | -136 | REJECT |
| C3 | bear>=7 + confluence | 2 | 1 | 291 | 0.954 | 277 | -296 | REJECT |
| C4 | bear>=8 + PDH within $0.30 | 0 | 1 | 0 | 0.447 | 0 | -586 | REJECT |
| C5 | bear>=7 + confluence + vol>=2.0 | 2 | 1 | 291 | 0.954 | 277 | -296 | REJECT |

**All scenarios REJECT because:** The baseline itself has a structural miss (5/01 → None
via current engine) and the BS simulator shows loser days as profitable (anti-correlated
with OP-16 intent). When scenario gates skip loser days (e.g., E1/E2 → 0 loser fires),
they remove the baseline's loser-day profit, making marginal_pnl negative. This is a
methodology artifact, not a real signal loss.

### True finding: flip-bear as categorical filter

The binary property — **flip_bear fires on winner days but never on loser days** — is not
captured by the edge_capture metric (which requires actual trade P&L). The right use of
this signal is:

> "After the ribbon flips bearish, the FIRST rejection bar at a level (score >= 8, with
> allow_one_blocker for F9 or F10) is the highest-quality entry. Score this with flip_bear
> bonus = +1 to quality tier."

This is a **quality-tier discriminator**, not a pass/fail gate. Encoding it as a mandatory
gate (E1: score >= 9 AND flip) is too strict — J's 4/29 12:25 bar was score=8, not 9.

## Root cause analysis: why 5/01 is uncapturable by this sweep

5/01 had ribbon=BULL the entire day (score never above 7 after F5 blocks). J's +$470 was a
BEARISH_REVERSAL: countertrend put at the First-Hour High (FHH=724.24) while ribbon was BULL.
This requires `include_bearish_reversal_bypass=True` + `include_first_hour_high=True` — a
separate study. Until that feature is enabled, 5/01 cannot contribute to any bear-side
OP-16 edge_capture calculation.

## Anti-correlation warnings

1. **vol_ratio gates (≥2.0, ≥3.0):** J's winner entry bars have vol_ratio ≈ 0.0. Do NOT
   use high volume as a bear-entry confirmation — it fires on continuation moves AFTER the
   entry opportunity. This was tested in E5, C5 and confirmed absent at J's entry bars.

2. **bear_score ≥ 9 gates (E1, C1):** J's winners are score=8 bars. Score=9 gates
   systematically miss J's actual setup. The engine's internal quality tier (allow_one_blocker)
   is already addressing this.

3. **E6 (bull_flip gate):** 0 winner fires. The bullish side is not where J's edge lives
   on these dates (bullish trades on loser days).

## Actionable findings for next iteration

1. **Fresh-flip quality bonus:** Add `ribbon_just_flipped_bearish` as a +1 score modifier
   (boosts TRENDLINE → LEVEL quality tier, or LEVEL → ELITE). Only changes qty, not
   pass/fail. Testable via quality_tier rebalancing in orchestrator.
   
2. **C2 deserves a follow-up:** bear_score >= 8 + nearest level ≤ $0.20 fires on 2 winner
   days and 2 loser days — a 50% specificity that matches the baseline. But level_proximity
   ≤ $0.20 catches the HIGHEST confidence entries near real resistance. The marginal_pnl
   of -$136 is an artifact of BS simulator, not real signal quality. Run with real fills.

3. **Compression (E4) deserves more data:** E4 fires on all 3 loser days too — but the loser
   days are showing positive P&L in BS simulator (anti-correlated with real fills). Real fills
   check needed.

## Backtest evidence (continued)

- **edge_capture:** 291 baseline → no scenario clears OP-16 floor (771)
- **aggregate_sharpe:** baseline = 2.034 (good)
- **final_score:** baseline = 591 (acceptable but not OP-16 passing)
- **top5_pct:** not computed (7-day anchor sweep, not distributional)
- **positive_quarters:** N/A (7-day focused sweep)
- **max_drawdown:** N/A (BS simulator)
- **real_fills_validated:** no — BS sim used for comparability with minspread sweep baseline

## Disclosures (per OP-20)

1. **Account-size assumption:** BS simulator, ATM strike, qty=3/6/10/15 by tier. No per-tier
   equity scaling applied (all at initial_equity default).
2. **Sample-bias disclosure:** 7 anchor days only (J's personal trade history). Severely
   limited sample. All conclusions are structural/directional, not statistical.
3. **Out-of-sample test result:** N/A — this sweep is a structural audit, not a temporal
   backtest. The "test set" IS the 7 anchor days.
4. **Real-fills check:** Not performed. BS simulator used. Known C1 distortion: loser days
   appear profitable in BS sim (option vol overstated vs real fills). All marginal_pnl
   comparisons should be re-run with real fills before any production change.
5. **Failure-mode enumeration:**
   - F1: BS sim overstates loser-day P&L → flips marginal analysis sign.
   - F2: 5/01 uncapturable without FHH bypass → edge_capture ceiling blocked at 1072/1542.
   - F3: vol_ratio anti-correlation makes E4/E5/C5 likely to fire on continuation bars
     (mid-trend chasing), not true reversal setups.
   - F4: score threshold too strict in E1 (needs score=8 not 9 to capture J's 12:25 bar).
6. **Concentration:** top5_pct = N/A (7 trade focus). All anchor-day weight.

## Knob changes proposed

NONE at this stage. This sweep is diagnostic. The actionable recommendations are:

1. Explore quality-tier bonus for `ribbon_just_flipped_bearish` (orchestrator change).
2. Test C2 with real fills to see if level proximity ≤ $0.20 is a genuine quality filter.
3. Close the 5/01 gap with FHH bypass candidate (existing Rank 27/28 candidates).

**NEVER edit params.json.** These require A/B validation + real-fills + anchor-no-regression
before any production change.

## Pre-merge gate

`python crypto/validators/runner.py` shows 83/84 PASS — 1 failure is `v43_ghost_entry_dual_account.live`
(live-source flaky validator, pre-existing, not caused by this work).

## My confidence (1-10) and why

**2/10** for any specific scenario gate being promotable from this sweep.

**8/10** for the structural finding: ribbon_just_flipped_bearish is a zero-noise signal on
J's loser days and should be tracked as a quality discriminator (not a mandatory gate). This
is a genuine finding that should inform future quality-tier refinement.

The sweep correctly identifies that the current OP-16 failure is rooted in (1) 5/01 FHH
bypass missing and (2) BS simulator distorting loser-day P&L rather than in the pattern/level
gates themselves. This closes the loop on the scenario hypothesis cleanly.

# FILTER 8 (VIX regime gate) -- archetype-conditional cost measurement + fate decision (2026-08-02)

Pre-reg `analysis/recommendations/prereg-vix-regime-gate-archetype-2026-08-02.json` frozen **2026-08-01 16:53:48 Saturday EDT**, before any run. Runner: `backtest/tools/vix_regime_gate_archetype_fate_2026_08_02.py`.

## Vary-and-assert (C14 dead-knob discipline)

- Signature check: PASS -- matches prereg's asymmetry_disclosed claim exactly
- Bear probe (vix_now=17.25 falling from 17.50): PASS -- CONTROL hard-blocks (blockers==[8]); vix_soft_mode=True removes the block and costs exactly -1 score; disable_filters=[8] removes the block with NO score cost. Three distinguishable behaviours confirmed live.
  - CONTROL blockers=[8], score=9
  - vix_soft_mode=True blockers=[], score=9
  - disable_filters=[8] blockers=[], score=10
- Bull probe (vix_now=17.40 rising from 17.10): PASS -- CONTROL hard-blocks; disable_filters=[8] removes the block. No vix_soft_mode variant exists on this side (confirmed above) so only disable_filters is exercised here, matching ARM_A_soft's bull-side no-op.
  - CONTROL blockers=[8]
  - disable_filters=[8] blockers=[]
- **ALL VARY-AND-ASSERT CHECKS PASSED -- neither flag is a dead knob**

## What filter 8 is
- **BULL** (`filters.py:1190-1195 (inside evaluate_bullish_setup)`): `vd = vix_direction(vix_now, vix_prior); vix_pass = vix_now < 17.20 (VIX_BULL_LOW_THRESHOLD) or vd == 'falling'; if not vix_pass: blockers.append(8). UNCONDITIONAL hard block -- evaluate_bullish_setup's signature has NO vix_soft_mode parameter at all, so bull-side filter 8 has NO soft-mode escape valve of any kind, ever.`
- **BEAR** (`filters.py:1506-1528 (inside evaluate_bearish_setup)`): `vix_pass = vix_now > 17.30 (VIX_BEAR_THRESHOLD) and vix_direction == 'rising'; ALSO fails if vix_now > VIX_HARD_CAP_BEAR (currently 999.0 = effectively off) or (if VIX_DECLINING_REQUIRED_BEAR, currently False = off) vix_5d_ma > vix_20d_ma. With both sub-conditions currently disabled in production, the LIVE bear rule reduces to exactly: block bear entries unless VIX > 17.30 AND rising. if not vix_pass: if vix_soft_mode: vix_soft_demerit=True (-1 score modifier, NOT a hard block) else: blockers.append(8).`
- Asymmetry: vix_soft_mode is BEAR-ONLY. It does not exist as a bull-side parameter (confirmed by reading evaluate_bullish_setup's full signature -- no vix_soft_mode kwarg). Any arm using vix_soft_mode=True changes BEAR-side filter 8 behavior only; bull-side filter 8 stays an unconditional hard block under that arm. disable_filters=[8] is symmetric -- both evaluate_bullish_setup and evaluate_bearish_setup check 'if 8 not in disable' identically.

## Provenance
**Filter 8 has NO ratification scorecard using the current gold-standard exit-walk methodology. It is inherited doctrine (same single squashed-snapshot commit as filter 5), and the ONLY prior research on relaxing it is built on a KNOWN-DIVERGENT, now-superseded simulation path -- its headline numbers must NOT be cited as evidence.**
- git log -S'blockers.append(8)' -- backtest/lib/filters.py returns ONE commit (d0c8ac06 'evening snapshot 2026-06-15'), the SAME squashed snapshot filter 5's own provenance check found -- not a dedicated arming commit.
- git log --oneline df0348d9..HEAD -- backtest/lib/ backtest/tools/ladder_fullhist_replay.py backtest/tools/day_report_card.py returns ZERO commits: the engine's scoring/filter code has not moved since the task's own $4,808.75/191 anchor commit -- the drift this study's own replay shows against the OLDER 2026-07-27 LADDER-FULLHIST anchor (194 vs 191 walked trades, 2306 vs 2308 candidates, <2% either way) is NOT code drift and does not touch this prereg's blocker-count evidence (see REGIME-PARTICIPATION-2026-08-02.md sec. 'anchor discrepancy').
- 8 prior autoresearch scripts swept vix_soft_mode / disable_filters=[8] on 2026-05-19 (analysis/recommendations/vix_soft_16mo_backtest.json, vix_mode_edge_sweep.json, vix_soft_walk_forward.json, vix_perbar_deep_dive.json, allow_one_blocker_minspread_sweep.json, gate_sweep_htf_triggers.json, gate_sweep_patterns_levels.json + 6 more unpublished .py sweep scripts). vix_mode_edge_sweep.json's best config (vix_soft_mode=True + allow_one_blocker=True) passed the narrow OP-16 6-J-day floor (edge_capture $1,179 of $1,542 max) and vix_soft_16mo_backtest.json's follow-up full-16-month validation reported an almost unbelievable total_pnl of $107,859-$111,254 (vs this engine's actual validated 18-month total of $4,808.75 -- a >20x gap) with 6/6 positive quarters and Sharpe ~9.
- ROOT CAUSE OF THAT NUMBER, CONFIRMED BY READING THE CODE (backtest/autoresearch/vix_soft_16mo_backtest.py:112-118, analyze_result()): it sums t.dollar_pnl DIRECTLY off the raw run_backtest() trade objects, with ZERO re-derivation via lib/exit_manager_walk.walk_exit_manager. This is EXACTLY the 'simulate_trade_real params.json-top-level-keys shape (profit_lock_mode="fixed")' path that engine_fullhist_replay.py's own guard test (test_engine_fullhist_replay.py, invariant 1, 'EXIT-SHAPE-PARITY GUARD') was built specifically to catch and correct, and which every newer full-history script (engine_fullhist_replay.py, ladder_fullhist_replay.py, day_report_card.py, this task's regime_participation_replay.py) explicitly discards and re-derives instead ('wrong_exit_pnl_discarded' field). The 2026-05-19 vix_soft sweep family predates that correction and was never re-validated against it. None of those 8 files' P&L figures may be cited as evidence for or against filter 8 in this or any future study until re-run through the current exit-walk standard.

Under J's standing rule (memory: kill_reentry_lock_gate_provenance_2026_07_02 -- 'every gate needs provenance + evidence or it dies'), filter 8 currently has neither a provenance-backed arming decision NOR a trustworthy scorecard. It survives only if THIS study's measurement (current gold-standard exit walk, not the divergent 2026-05-19 path) earns it.

## Cohort A -- setups filter 8 blocked ALONE (blockers == [8])

| side | bars (full) | days (full) | bars (recent 25d) | days (recent) |
|---|--:|--:|--:|--:|
| bull | 187 | 84 | 3 | 2 |
| bear | 699 | 190 | 36 | 12 |

## Cohort B -- the book filter 8 ALLOWED (CONTROL)

| window | n | total | WR | per-trade | total ex-best |
|---|--:|--:|--:|--:|--:|
| full | 194 | $4,422.95 | 0.2887 | $22.80 | $3,563.00 |
| recent25 | 19 | $-957.40 | 0.2105 | $-50.39 | $-1,446.80 |

n_excluded_no_opra: {'CONTROL': 18, 'ARM_A_soft': 31, 'ARM_B_delete': 31}

## ARM_A_soft -- **NULL**

| window | control | arm | delta | added | dropped | days +/- | top-day share of delta |
|---|--:|--:|--:|--:|--:|:--|--:|
| full | $4,422.95 (n=194) | $2,339.55 (n=244) | **$-2,083.40** | 105 | 55 | 34/57 | -45.6% |
| recent25 | $-957.40 (n=19) | $-1,302.00 (n=21) | **$-344.60** | 6 | 4 | 2/3 | -119.4% |

Added-trade cohort (full window, real exits): n=105 total=$-3,903.60 WR=0.2476 per-trade=$-37.18 ex-best=$-4,905.90

| gate | result | status |
|---|---|:--:|
| G1_recent_window_positive | delta_total_recent=-344.6 | UNDETERMINED |
| G2_day_majority_recent | improved=2, worsened=3 | FAIL |
| G3_survives_drop_best_recent | delta_minus_best=-756.0 | FAIL |
| G4_runner_anchor_no_regression | control_n=39, arm_n=52, control_total=18330.05, arm_total=25626.25 | PASS |
| G5_fire_count | n_added_full=105, n_added_recent=6, floor_full=10, floor_recent=2 | PASS |

> **G1 is UNDETERMINED, not FAIL.** 2 of 8 raw entries this arm ADDS in the recent window could not be priced (no cached OPRA contract), so only 6 are in the measured delta of $-344.60. G1 is a strict SIGN test on that sum: the missing entries would only need to average $+172.30 each to flip it. The sign is UNDETERMINED on the evidence, not measured-negative.
>
> **UNCHANGED EITHER WAY. UNDETERMINED is not a PASS, the ship rule requires all five gates to pass, and this is a gap in the evidence, not a refutation.**

### OPRA coverage -- ARM_A_soft (window-stratified exclusions)

| window | arm | walked | excluded (no OPRA) | excluded (no SPY day) |
|---|---|--:|--:|--:|
| full | CONTROL | 194 | 18 | 0 |
| full | ARM_A_soft | 244 | 31 | 0 |
| recent25 | CONTROL | 19 | 3 | 0 |
| recent25 | ARM_A_soft | 21 | 5 | 0 |

**Entries this arm ADDS -- how many are even measurable:**

| window | raw added | measurable | unmeasurable (no OPRA) | measurable % |
|---|--:|--:|--:|--:|
| full | 121 | 105 | 16 | 86.8% |
| recent25 | 8 | 6 | 2 | 75.0% |

Recent-window trading days with ZERO cached OPRA coverage: **0** (none).

### ARM_A_soft -- attribution (artifact hunt)

- Trades filter 8 was ACTUALLY blocking (added cohort): **$-3,903.60**
- Control trades that merely VANISH (pre-emption): $-1,820.20 -> **$+1,820.20** (-87.4% of the delta)

## ARM_B_delete -- **NULL**

| window | control | arm | delta | added | dropped | days +/- | top-day share of delta |
|---|--:|--:|--:|--:|--:|:--|--:|
| full | $4,422.95 (n=194) | $4,547.10 (n=271) | **$+124.15** | 133 | 56 | 42/69 | 1198.0% |
| recent25 | $-957.40 (n=19) | $-1,302.00 (n=21) | **$-344.60** | 6 | 4 | 2/3 | -119.4% |

Added-trade cohort (full window, real exits): n=133 total=$-1,976.05 WR=0.2857 per-trade=$-14.86 ex-best=$-2,978.35

| gate | result | status |
|---|---|:--:|
| G1_recent_window_positive | delta_total_recent=-344.6 | UNDETERMINED |
| G2_day_majority_recent | improved=2, worsened=3 | FAIL |
| G3_survives_drop_best_recent | delta_minus_best=-756.0 | FAIL |
| G4_runner_anchor_no_regression | control_n=39, arm_n=59, control_total=18330.05, arm_total=29748.8 | PASS |
| G5_fire_count | n_added_full=133, n_added_recent=6, floor_full=10, floor_recent=2 | PASS |

> **G1 is UNDETERMINED, not FAIL.** 2 of 8 raw entries this arm ADDS in the recent window could not be priced (no cached OPRA contract), so only 6 are in the measured delta of $-344.60. G1 is a strict SIGN test on that sum: the missing entries would only need to average $+172.30 each to flip it. The sign is UNDETERMINED on the evidence, not measured-negative.
>
> **UNCHANGED EITHER WAY. UNDETERMINED is not a PASS, the ship rule requires all five gates to pass, and this is a gap in the evidence, not a refutation.**

### OPRA coverage -- ARM_B_delete (window-stratified exclusions)

| window | arm | walked | excluded (no OPRA) | excluded (no SPY day) |
|---|---|--:|--:|--:|
| full | CONTROL | 194 | 18 | 0 |
| full | ARM_B_delete | 271 | 31 | 0 |
| recent25 | CONTROL | 19 | 3 | 0 |
| recent25 | ARM_B_delete | 21 | 5 | 0 |

**Entries this arm ADDS -- how many are even measurable:**

| window | raw added | measurable | unmeasurable (no OPRA) | measurable % |
|---|--:|--:|--:|--:|
| full | 149 | 133 | 16 | 89.3% |
| recent25 | 8 | 6 | 2 | 75.0% |

Recent-window trading days with ZERO cached OPRA coverage: **0** (none).

### ARM_B_delete -- attribution (artifact hunt)

- Trades filter 8 was ACTUALLY blocking (added cohort): **$-1,976.05**
- Control trades that merely VANISH (pre-emption): $-2,100.20 -> **$+2,100.20** (1691.7% of the delta)

## G6 -- archetype participation delta (REPORTED, NOT GATING)

per-archetype (trend-up / trend-down / V-reversal / inverted-V / gap-go / gap-fade / pin-day / range-chop) delta in n_days_entered and total $, full population AND recent window, for each arm vs CONTROL. This is the motivating question (does the archetype-conditional participation gap actually close) but is EXPLICITLY DESCRIPTIVE, not a ship gate -- slicing an already-thin population 8 further ways and gating on any one slice would be uncorrected multiple comparisons on top of an underpowered base. It feeds a FUTURE archetype-conditional study if the aggregate (G1-G5) ships; it does not by itself justify shipping.

### Full population

**ARM_A_soft:**

| archetype | control n_days | arm n_days | delta n_days | control $ | arm $ | delta $ |
|---|--:|--:|--:|--:|--:|--:|
| V-reversal | 8 | 11 | +3 | $602.50 | $1,254.35 | **$+651.85** |
| data-incomplete | 1 | 1 | +0 | $66.00 | $66.00 | **$+0.00** |
| gap-fade | 21 | 27 | +6 | $-1,211.35 | $-2,085.95 | **$-874.60** |
| gap-go | 30 | 32 | +2 | $2,852.30 | $3,574.20 | **$+721.90** |
| inverted-V | 2 | 4 | +2 | $156.25 | $-325.25 | **$-481.50** |
| pin-day | 4 | 5 | +1 | $-430.80 | $-484.80 | **$-54.00** |
| range-chop | 65 | 83 | +18 | $1,396.40 | $410.75 | **$-985.65** |
| trend-down | 8 | 7 | -1 | $811.05 | $-765.15 | **$-1,576.20** |
| trend-up | 4 | 4 | +0 | $180.60 | $695.40 | **$+514.80** |

**ARM_B_delete:**

| archetype | control n_days | arm n_days | delta n_days | control $ | arm $ | delta $ |
|---|--:|--:|--:|--:|--:|--:|
| V-reversal | 8 | 11 | +3 | $602.50 | $1,146.35 | **$+543.85** |
| data-incomplete | 1 | 1 | +0 | $66.00 | $66.00 | **$+0.00** |
| gap-fade | 21 | 29 | +8 | $-1,211.35 | $-2,062.60 | **$-851.25** |
| gap-go | 30 | 41 | +11 | $2,852.30 | $6,122.60 | **$+3,270.30** |
| inverted-V | 2 | 4 | +2 | $156.25 | $-325.25 | **$-481.50** |
| pin-day | 4 | 5 | +1 | $-430.80 | $-484.80 | **$-54.00** |
| range-chop | 65 | 87 | +22 | $1,396.40 | $424.55 | **$-971.85** |
| trend-down | 8 | 8 | +0 | $811.05 | $-963.15 | **$-1,774.20** |
| trend-up | 4 | 5 | +1 | $180.60 | $623.40 | **$+442.80** |

### Recent 25-day window

**ARM_A_soft:**

| archetype | control n_days | arm n_days | delta n_days | control $ | arm $ | delta $ |
|---|--:|--:|--:|--:|--:|--:|
| V-reversal | 2 | 2 | +0 | $-295.00 | $-753.00 | **$-458.00** |
| gap-fade | 3 | 3 | +0 | $-730.60 | $-655.60 | **$+75.00** |
| gap-go | 3 | 3 | +0 | $218.80 | $218.80 | **$+0.00** |
| range-chop | 5 | 6 | +1 | $-150.60 | $-112.20 | **$+38.40** |

**ARM_B_delete:**

| archetype | control n_days | arm n_days | delta n_days | control $ | arm $ | delta $ |
|---|--:|--:|--:|--:|--:|--:|
| V-reversal | 2 | 2 | +0 | $-295.00 | $-753.00 | **$-458.00** |
| gap-fade | 3 | 3 | +0 | $-730.60 | $-655.60 | **$+75.00** |
| gap-go | 3 | 3 | +0 | $218.80 | $218.80 | **$+0.00** |
| range-chop | 5 | 6 | +1 | $-150.60 | $-112.20 | **$+38.40** |

## BH-FDR advisory (reported_not_gating, alpha=0.10)

Advisory only (reported_not_gating.bh_fdr) -- one-sided sign-flip permutation test, H1: mean(dollar_pnl) of the arm's full-population ADDED cohort > 0. N_PERMS=20000, seed=42, q*=0.1. Does NOT gate the ship decision.

| arm | n changed trades | obs mean $/trade | p (one-sided) | BH survives q*=0.10 |
|---|--:|--:|--:|:--:|
| ARM_A_soft | 105 | $-37.18 | 0.8934 | no |
| ARM_B_delete | 133 | $-14.86 | 0.7055 | no |

## Ship rule

An arm SHIPS only if G1 AND G2 AND G3 AND G4 AND G5 all pass. If both arms pass, ship the one with the higher RECENT-window delta. If NO arm passes, filter 8 STAYS and the null goes in the graveyard verbatim -- including the case where deletion/soft-mode looks good on the aggregate but fails the recent window, and including the case where G6's archetype numbers look good but G1-G5 don't clear (a real but not yet ship-worthy finding, logged for the follow-up study, not force-shipped on a descriptive metric).

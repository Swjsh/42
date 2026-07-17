# PONG resting-limit-at-level study -- PONG-RESTING-LIMIT-2026-07-17

Generated: 2026-07-17T10:03:25.839827. Source: `backtest/tools/pong_resting_limit_study.py`. Pre-reg: `analysis/recommendations/prereg-pong-resting-limit-2026-07-17.json`.

## SAFE

Tier **ATM** (so=0), equity=$1478.13, qty=3, time_stop=15:40:00.

### Mining summary (per cancel rule)

| cancel_rule | arm_events | filled | canceled | unfilled_expired | no_local_bars | bounce | slice_through |
|---|--:|--:|--:|--:|--:|--:|--:|
| no_cancel | 3439 | 2415 | 0 | 109 | 881 | 626 | 1789 |
| cancel_0.15 | 4407 | 855 | 2526 | 90 | 915 | 391 | 464 |
| cancel_0.30 | 4030 | 1405 | 1605 | 88 | 895 | 535 | 870 |
| cancel_0.50 | 3732 | 1806 | 908 | 99 | 885 | 566 | 1240 |

**ADVERSE-SELECTION SPLIT (raw, no_cancel population): bounce n=626, slice_through n=1789, slice_through_share=0.7408.**

Control: 1863 distinct (date,level) episode_ids examined, 1448 would have confirmation-triggered under current engine semantics.

Control-sanity (self-vs-self, mandatory disclosure): is_delta_mean=0.0, oos_delta_mean=0.0, wf_delta=None, ladder=FAIL.

### Per-cell table (cancel_rule x exit_shape)

| cell | n | is/oos | IS delta/tr | OOS delta/tr | WF | ladder | bounce n/delta | slice n/delta | anchor | bh | ship_ready |
|---|--:|--:|--:|--:|--:|---|---|---|:--:|:--:|:--:|
| no_cancel|tp30_structure_t12 | 1504 | 871/633 | $17.6551 | $21.5539 | 1.2208 | PASS | 269/$77.61 | 785/$-6.67 | False | True | False |
| no_cancel|tp30_structure_t30 | 1504 | 871/633 | $20.9583 | $24.3631 | 1.1625 | PASS | 269/$74.48 | 785/$-0.12 | False | True | False |
| no_cancel|tp30_premium35_t12 | 1504 | 871/633 | $10.0718 | $10.414 | 1.034 | PASS | 269/$75.42 | 785/$-21.93 | False | True | False |
| no_cancel|tp30_premium35_t30 | 1504 | 871/633 | $8.5987 | $7.1532 | 0.8319 | PASS | 269/$62.2 | 785/$-21.11 | False | True | False |
| no_cancel|tp50_structure_t12 | 1504 | 871/633 | $20.7756 | $29.563 | 1.423 | PASS | 269/$92.21 | 785/$-0.79 | False | True | False |
| no_cancel|tp50_structure_t30 | 1504 | 871/633 | $25.0499 | $33.4684 | 1.3361 | PASS | 269/$98.78 | 785/$7.73 | False | True | False |
| no_cancel|tp50_premium35_t12 | 1504 | 871/633 | $13.1715 | $20.3176 | 1.5425 | PASS | 269/$94.38 | 785/$-16.68 | False | True | False |
| no_cancel|tp50_premium35_t30 | 1504 | 871/633 | $13.7324 | $18.6112 | 1.3553 | PASS | 269/$90.01 | 785/$-12.03 | False | True | False |
| cancel_0.15|tp30_structure_t12 | 1474 | 851/623 | $32.924 | $39.7713 | 1.208 | PASS | 149/$67.38 | 160/$-0.64 | False | True | False |
| cancel_0.15|tp30_structure_t30 | 1474 | 851/623 | $35.8761 | $43.1805 | 1.2036 | PASS | 149/$59.38 | 160/$6.58 | False | True | False |
| cancel_0.15|tp30_premium35_t12 | 1474 | 851/623 | $35.5369 | $35.7994 | 1.0074 | PASS | 149/$72.3 | 160/$-18.45 | False | True | False |
| cancel_0.15|tp30_premium35_t30 | 1474 | 851/623 | $37.448 | $37.8588 | 1.011 | PASS | 149/$56.7 | 160/$-13.37 | False | True | False |
| cancel_0.15|tp50_structure_t12 | 1474 | 851/623 | $35.3031 | $45.9412 | 1.3013 | PASS | 149/$83.26 | 160/$-6.27 | False | True | False |
| cancel_0.15|tp50_structure_t30 | 1474 | 851/623 | $38.0958 | $49.9495 | 1.3112 | PASS | 149/$81.54 | 160/$9.03 | False | True | False |
| cancel_0.15|tp50_premium35_t12 | 1474 | 851/623 | $38.7139 | $44.4547 | 1.1483 | PASS | 149/$92.21 | 160/$-23.48 | False | True | False |
| cancel_0.15|tp50_premium35_t30 | 1474 | 851/623 | $40.9152 | $48.0222 | 1.1737 | PASS | 149/$84.17 | 160/$-7.32 | False | True | False |
| cancel_0.30|tp30_structure_t12 | 1479 | 853/626 | $31.8926 | $38.0787 | 1.194 | PASS | 205/$75.44 | 323/$2.34 | False | True | False |
| cancel_0.30|tp30_structure_t30 | 1479 | 853/626 | $34.9229 | $41.092 | 1.1766 | PASS | 205/$69.08 | 323/$8.9 | False | True | False |
| cancel_0.30|tp30_premium35_t12 | 1479 | 853/626 | $32.0084 | $34.0656 | 1.0643 | PASS | 205/$78.84 | 323/$-18.22 | False | True | False |
| cancel_0.30|tp30_premium35_t30 | 1479 | 853/626 | $33.3824 | $34.8584 | 1.0442 | PASS | 205/$66.56 | 323/$-17.58 | False | True | False |
| cancel_0.30|tp50_structure_t12 | 1479 | 853/626 | $34.7834 | $45.2679 | 1.3014 | PASS | 205/$91.89 | 323/$0.17 | False | True | False |
| cancel_0.30|tp50_structure_t30 | 1479 | 853/626 | $37.7878 | $49.1752 | 1.3014 | PASS | 205/$92.62 | 323/$10.97 | False | True | False |
| cancel_0.30|tp50_premium35_t12 | 1479 | 853/626 | $35.6164 | $43.692 | 1.2267 | PASS | 205/$97.64 | 323/$-20.8 | False | True | False |
| cancel_0.30|tp50_premium35_t30 | 1479 | 853/626 | $37.6307 | $46.0149 | 1.2228 | PASS | 205/$93.46 | 323/$-16.49 | False | True | False |
| cancel_0.50|tp30_structure_t12 | 1490 | 860/630 | $26.8873 | $35.751 | 1.3297 | PASS | 222/$76.77 | 484/$0.39 | False | True | False |
| cancel_0.50|tp30_structure_t30 | 1490 | 860/630 | $30.233 | $38.4798 | 1.2728 | PASS | 222/$70.09 | 484/$5.44 | False | True | False |
| cancel_0.50|tp30_premium35_t12 | 1490 | 860/630 | $24.7316 | $29.9874 | 1.2125 | PASS | 222/$79.84 | 484/$-15.95 | False | True | False |
| cancel_0.50|tp30_premium35_t30 | 1490 | 860/630 | $25.4918 | $28.8024 | 1.1299 | PASS | 222/$66.27 | 484/$-16.61 | False | True | False |
| cancel_0.50|tp50_structure_t12 | 1490 | 860/630 | $30.1565 | $42.1985 | 1.3993 | PASS | 222/$91.4 | 484/$1.89 | False | True | False |
| cancel_0.50|tp50_structure_t30 | 1490 | 860/630 | $33.7252 | $45.8536 | 1.3596 | PASS | 222/$89.22 | 484/$11.94 | False | True | False |
| cancel_0.50|tp50_premium35_t12 | 1490 | 860/630 | $28.6301 | $39.5205 | 1.3804 | PASS | 222/$97.49 | 484/$-13.15 | False | True | False |
| cancel_0.50|tp50_premium35_t30 | 1490 | 860/630 | $31.0135 | $39.2689 | 1.2662 | PASS | 222/$88.15 | 484/$-8.11 | False | True | False |

**SAFE: NULL RESULT (KILL).** Closest cell: `no_cancel|tp30_structure_t12` (4/5 gates, verdict_ladder=PASS, n=1504, IS=$17.6551, OOS=$21.5539) -- fails: ['anchor_no_regression'].

## BOLD

Tier **OTM-3** (so=-3), equity=$1963.04, qty=3, time_stop=15:40:00.

### Mining summary (per cancel rule)

| cancel_rule | arm_events | filled | canceled | unfilled_expired | no_local_bars | bounce | slice_through |
|---|--:|--:|--:|--:|--:|--:|--:|
| no_cancel | 3638 | 2295 | 0 | 107 | 1236 | 427 | 1868 |
| cancel_0.15 | 4638 | 627 | 2523 | 95 | 1393 | 223 | 404 |
| cancel_0.30 | 4245 | 1153 | 1642 | 100 | 1350 | 333 | 820 |
| cancel_0.50 | 3953 | 1633 | 935 | 100 | 1285 | 393 | 1240 |

**ADVERSE-SELECTION SPLIT (raw, no_cancel population): bounce n=427, slice_through n=1868, slice_through_share=0.8139.**

Control: 1934 distinct (date,level) episode_ids examined, 1375 would have confirmation-triggered under current engine semantics.

Control-sanity (self-vs-self, mandatory disclosure): is_delta_mean=0.0, oos_delta_mean=0.0, wf_delta=None, ladder=FAIL.

### Per-cell table (cancel_rule x exit_shape)

| cell | n | is/oos | IS delta/tr | OOS delta/tr | WF | ladder | bounce n/delta | slice n/delta | anchor | bh | ship_ready |
|---|--:|--:|--:|--:|--:|---|---|---|:--:|:--:|:--:|
| no_cancel|tp30_structure_t12 | 1424 | 846/578 | $2.6656 | $30.8937 | 11.5898 | PASS | 165/$111.09 | 889/$-26.51 | False | True | False |
| no_cancel|tp30_structure_t30 | 1424 | 846/578 | $9.8527 | $40.6461 | 4.1254 | PASS | 165/$108.08 | 889/$-17.18 | False | True | False |
| no_cancel|tp30_premium35_t12 | 1424 | 846/578 | $-0.2605 | $1.911 | None | INSUFFICIENT_REGIME_SHIFT | 165/$133.26 | 889/$-59.26 | False | True | False |
| no_cancel|tp30_premium35_t30 | 1424 | 846/578 | $-12.8301 | $7.9954 | None | INSUFFICIENT_REGIME_SHIFT | 165/$109.25 | 889/$-71.32 | False | True | False |
| no_cancel|tp50_structure_t12 | 1424 | 846/578 | $0.6977 | $28.3073 | 40.5725 | PASS | 165/$109.65 | 889/$-30.91 | False | True | False |
| no_cancel|tp50_structure_t30 | 1424 | 846/578 | $13.409 | $41.9161 | 3.126 | PASS | 165/$114.03 | 889/$-14.14 | False | True | False |
| no_cancel|tp50_premium35_t12 | 1424 | 846/578 | $1.2296 | $0.5555 | 0.4518 | FAIL | 165/$135.18 | 889/$-60.63 | False | True | False |
| no_cancel|tp50_premium35_t30 | 1424 | 846/578 | $-8.7619 | $15.5124 | None | INSUFFICIENT_REGIME_SHIFT | 165/$116.73 | 889/$-66.61 | False | True | False |
| cancel_0.15|tp30_structure_t12 | 1394 | 830/564 | $45.9286 | $73.9408 | 1.6099 | PASS | 77/$97.02 | 173/$-15.95 | False | True | False |
| cancel_0.15|tp30_structure_t30 | 1394 | 830/564 | $54.2348 | $83.6883 | 1.5431 | PASS | 77/$101.76 | 173/$-0.03 | False | True | False |
| cancel_0.15|tp30_premium35_t12 | 1394 | 830/564 | $72.4533 | $82.4457 | 1.1379 | PASS | 77/$91.67 | 173/$-61.14 | False | True | False |
| cancel_0.15|tp30_premium35_t30 | 1394 | 830/564 | $74.6346 | $105.7475 | 1.4169 | PASS | 77/$87.71 | 173/$-75.33 | False | True | False |
| cancel_0.15|tp50_structure_t12 | 1394 | 830/564 | $45.8927 | $69.4147 | 1.5125 | PASS | 77/$101.76 | 173/$-19.23 | False | True | False |
| cancel_0.15|tp50_structure_t30 | 1394 | 830/564 | $59.9034 | $83.0419 | 1.3863 | PASS | 77/$121.4 | 173/$2.14 | False | True | False |
| cancel_0.15|tp50_premium35_t12 | 1394 | 830/564 | $74.9938 | $77.6132 | 1.0349 | PASS | 77/$99.89 | 173/$-66.02 | False | True | False |
| cancel_0.15|tp50_premium35_t30 | 1394 | 830/564 | $80.9972 | $109.6099 | 1.3533 | PASS | 77/$120.77 | 173/$-74.08 | False | True | False |
| cancel_0.30|tp30_structure_t12 | 1396 | 830/566 | $42.9649 | $69.7284 | 1.6229 | PASS | 114/$120.66 | 347/$-18.35 | False | True | False |
| cancel_0.30|tp30_structure_t30 | 1396 | 830/566 | $50.5293 | $79.9451 | 1.5822 | PASS | 114/$117.89 | 347/$-6.45 | False | True | False |
| cancel_0.30|tp30_premium35_t12 | 1396 | 830/566 | $64.4569 | $74.3782 | 1.1539 | PASS | 114/$111.91 | 347/$-58.95 | False | True | False |
| cancel_0.30|tp30_premium35_t30 | 1396 | 830/566 | $62.0742 | $90.9768 | 1.4656 | PASS | 114/$100.9 | 347/$-82.96 | False | True | False |
| cancel_0.30|tp50_structure_t12 | 1396 | 830/566 | $42.7021 | $65.2356 | 1.5277 | PASS | 114/$121.96 | 347/$-23.76 | False | True | False |
| cancel_0.30|tp50_structure_t30 | 1396 | 830/566 | $57.0621 | $78.9324 | 1.3833 | PASS | 114/$134.83 | 347/$-2.82 | False | True | False |
| cancel_0.30|tp50_premium35_t12 | 1396 | 830/566 | $66.8071 | $70.2508 | 1.0515 | PASS | 114/$115.42 | 347/$-64.99 | False | True | False |
| cancel_0.30|tp50_premium35_t30 | 1396 | 830/566 | $68.4823 | $94.9163 | 1.386 | PASS | 114/$125.91 | 347/$-82.8 | False | True | False |
| cancel_0.50|tp30_structure_t12 | 1409 | 840/569 | $32.5837 | $63.543 | 1.9501 | PASS | 145/$114.96 | 545/$-15.61 | False | True | False |
| cancel_0.50|tp30_structure_t30 | 1409 | 840/569 | $39.2568 | $74.1414 | 1.8886 | PASS | 145/$111.29 | 545/$-8.96 | False | True | False |
| cancel_0.50|tp30_premium35_t12 | 1409 | 840/569 | $44.3837 | $60.9854 | 1.3741 | PASS | 145/$122.43 | 545/$-54.77 | False | True | False |
| cancel_0.50|tp30_premium35_t30 | 1409 | 840/569 | $37.9732 | $73.6862 | 1.9405 | PASS | 145/$101.18 | 545/$-79.26 | False | True | False |
| cancel_0.50|tp50_structure_t12 | 1409 | 840/569 | $31.4971 | $59.2008 | 1.8796 | PASS | 145/$119.96 | 545/$-20.78 | False | True | False |
| cancel_0.50|tp50_structure_t30 | 1409 | 840/569 | $44.6883 | $72.3735 | 1.6195 | PASS | 145/$126.2 | 545/$-5.62 | False | True | False |
| cancel_0.50|tp50_premium35_t12 | 1409 | 840/569 | $46.1101 | $57.5472 | 1.248 | PASS | 145/$128.35 | 545/$-57.79 | False | True | False |
| cancel_0.50|tp50_premium35_t30 | 1409 | 840/569 | $42.1817 | $77.9091 | 1.847 | PASS | 145/$115.9 | 545/$-76.35 | False | True | False |

**BOLD: NULL RESULT (KILL).** Closest cell: `no_cancel|tp30_structure_t12` (4/5 gates, verdict_ladder=PASS, n=1424, IS=$2.6656, OOS=$30.8937) -- fails: ['anchor_no_regression'].

## NEAR-MISS DIAGNOSTIC -- fable-too-good artifact hunt

Every one of the 64 (cancel_rule x exit_shape) cells across BOTH accounts fails
`anchor_no_regression` and ONLY that gate -- the same cell (`no_cancel|tp30_structure_t12`)
clears `oos_positive`, `wf_ge_070`, `sub_window_stable`, and `bh_fdr_survivor` on both Safe
(n=1504, IS $17.66/tr, OOS $21.55/tr, WF=1.22) and Bold (n=1424, IS $2.67/tr, OOS $30.89/tr,
WF=11.59). A 100%-uniform gate failure across an entire grid, on the SAME gate, on BOTH
accounts, next to four gates that pass cleanly everywhere, is exactly the shape CLAUDE.md's
"suspicion scales with how good it looks" rule exists for -- before reporting this as a
near-ship, it was decomposed and investigated rather than taken at face value.

**Decomposition of the delta (reference cell `no_cancel|tp30_structure_t12`, independently
re-derived via `backtest/tools/_pong_finalize_scorecard.py`, reusing the study's own
functions verbatim):**

| account | population | n | delta_sum | delta_mean |
|---|---|--:|--:|--:|
| Safe | both_traded (real head-to-head) | 1010 | $18,679.75 | $18.49 |
| Safe | cand_only (control never fired) | 63 | -$1,130.60 | -$17.95 |
| Safe | ctrl_only (PONG never filled) | 157 | -$470.20 | -$2.99 |
| Bold | both_traded (real head-to-head) | 1004 | $13,189.25 | $13.14 |
| Bold | cand_only (control never fired) | 51 | -$5,460.90 | -$107.08 |
| Bold | ctrl_only (PONG never filled) | 143 | $5,823.70 | $40.73 |

**Verdict on the decomposition: the positive aggregate is predominantly a real head-to-head
execution effect, not primarily "PONG just avoided the control's losers."** Safe's
both-traded population alone is 109% of the total delta (cand_only and ctrl_only are both
small/negative net drags); Bold's is 97% (though Bold's ctrl_only population -- 143 episodes
where the confirmation trigger fired but PONG's resting order never filled -- does
contribute a real +$5,824, 43% of the total, from control simply losing on trades PONG
skipped; disclosed, not hidden). This is the more reassuring half of the artifact hunt: the
core mechanism (buying the option nearer its local low via delta-mapping, no entry-side
slippage) does appear to have real head-to-head value on the episodes both sides could
trade.

**The anchor-date evidence is the less reassuring half, and it is the reason this stays a
KILL, not a technicality to explain away.** Every candidate-traded episode landing on one of
the 7 CLAUDE.md OP-16 anchor dates was pulled and its own P&L inspected directly (not just
whether the gate fired):

| account | anchor-date fills | losses | win rate | worst single loss |
|---|--:|--:|--:|--:|
| Safe | 21 | 20 | 4.8% | -$147.90 (05-07 733.28C) |
| Bold | 17 | 16 | 5.9% | -$204.90 (05-07 733.28C) |

On J's own 6 hand-verified best real trading dates (2026-04-29 through 2026-05-07), the
candidate mechanism loses on **36 of 38 combined fills** (20 of 21 Safe, 16 of 17 Bold),
several by well over $100 at qty=3. This is not noise -- it is
a mechanistically coherent story: those 6 dates were fast, volatile, trending sessions
(that is *why* they produced J's best real trades under the current confirmation-based
playbook) rather than the range-bound ping-pong regime PONG's entire thesis depends on. A
resting order sitting at a level on a trending day gets run over, not bounced off.

**anchor_no_regression is not an overly-strict same-calendar-date technicality here -- it
is catching a real, regime-dependent vulnerability that the aggregate full-window number
completely hides.** The gate is doing exactly its job.

## Overall verdict + build-spec-or-kill

any_ship_ready_overall=**False** (safe=False, bold=False) -- **HONEST KILL under the frozen
5-gate rule.** No cell clears all 5 ratification gates plus BH-FDR on either account, so per
the pre-registered `decision_rule.kill_criterion` no build spec is authorized (build specs
are gated on `if >=1 cell is ship-ready`, per the frozen prereg -- none is).

**Closest cell (both accounts, identically):** `no_cancel|tp30_structure_t12` -- 4/5 gates
pass (`oos_positive`, `wf_ge_070`, `sub_window_stable`, `bh_fdr_survivor`), fails only
`anchor_no_regression`. **THE ANSWER TO THE CENTRAL QUESTION (adverse-selection split):**
raw (no_cancel, unfiltered) fill population is **74.1% slice-through on Safe, 81.4%
slice-through on Bold** -- the resting-limit mechanism is adversely selected on 3-4 out of
every 4 fills, exactly the concern the task's framing anticipated. The combined book is
still net positive in the aggregate *only* because bounce wins are roughly an order of
magnitude larger than slice losses on average (Safe: bounce +$77.61/tr on n=269 vs slice
-$6.67/tr on n=785; Bold: bounce +$111.09/tr on n=165 vs slice -$26.51/tr on n=889) -- a
real asymmetric-payoff structure, not a wash -- but that asymmetry inverts on exactly the
highest-conviction days, which is disqualifying for a ship decision regardless of the
aggregate looking clean.

**Cancel-watcher grid finding:** every cancel threshold (0.15/0.30/0.50) roughly HALVES or
more the fill count relative to no_cancel while *raising* per-trade expectancy across nearly
every exit shape (e.g. Safe cancel_0.50|tp50_structure_t30: n=1490, OOS $45.85/tr vs
no_cancel's $33.47/tr) -- cancelling on a level break does filter out some of the worst
slice-through damage, as expected, but does NOT fix the anchor-date problem (anchor
failures recur at every cancel threshold too, since anchor-date volatility produces fast
breaches that a $0.15-0.50 cancel band often cannot outrun before the option bar already
ticked through P(L)).

**Disposition: KILL, current confirmation-entry semantics stand.** This is an unusually
informative kill -- not a dead mechanism, but one requiring a REGIME FILTER before it could
be safely reconsidered. Named follow-up (not authorized by this study, not auto-queued):
re-run this exact grid restricted to range-bound/low-ADX/low-realized-move days only
(excluding trending sessions structurally similar to the anchor dates), since the current
aggregate result is likely not representative of the days it would actually need to perform
well on. No build spec is written; no entry_manager.py / j_intent_executor change is
authorized by this result.

## Disclosures

- MEASURED (real OPRA local cache replay), not REALIZED -- no broker fills exist for this candidate mechanism, which does not exist in production.
- wall-v1 timestamp convention throughout (SPY+options share a year-round-fixed-offset storage artifact, lib/et_frame.py) -- internally consistent SPY-to-option joins, but winter-month (EST) wall-clock labels can be off by up to 1h vs true ET; VIX lookups inherit the same skew against the SPY/option clock even though VIX's own storage is genuinely correct (a coarse IV proxy, low-materiality).
- Entry-zone width ($0.50) and level set are FIXED, not swept -- see the prereg's mechanism_spec.entry_zone.provenance for why (interacts with the one-slot-per-day state machine, unlike a simple post-filter).
- Delta is Black-Scholes-MODELED (lib.pricing.black_scholes, VIX-derived IV) -- OPRA bars carry no greeks; this is the house standard, no empirical-greeks alternative exists in the local cache.
- one_position_at_a_time is enforced at the ENTRY-ATTEMPT level only (no new arm while a prior order is pending or a prior fill's own exit is still open is NOT separately enforced -- exit duration is exit-shape-dependent and evaluated as a post-filter of a shape-agnostic mining pass) -- a disclosed simplification, not full position-slot realism.
- Adverse-selection classification (bounce vs slice_through) uses a 3-bar/15-min window after fill with a 10c break margin -- a disclosed, un-swept convention (not itself a grid axis this study adjudicates).
- Control (confirmation-entry) is scoped to the SAME (date, level) episode, not a full independent orchestrator/gate-stack run -- isolates EXECUTION MECHANISM specifically, per the task's own framing; block_level_rejection and other production gates are a DIFFERENT, separately-provenanced axis, out of scope here (same carve-out zone-rejection-band-2026-07-17 used for the same gate).
- qty=3 fixed BOTH accounts (a disclosed deviation from each account's own live qty knob, per the task's explicit instruction for apples-to-apples comparability in this study).
- min_entry_premium floor (0.30, both accounts) applied against P(L) (candidate) and the raw entry-bar OPEN premium (control); a signal below floor is dropped and counted (floor_skip), never imputed (C7).
- Null-sanity draw count capped at 40 per cell and cached by (exit_shape, capped_n) across cancel_rule cells sharing it; NULL_SEEDS reduced to 10 (vs zone study's 20) given this study's 4x larger grid -- disclosed efficiency simplification, not a per-cell-exact null.
- ONE process, no multiprocessing.Pool -- OPRA local bar cache is process-local; matches the 6-8-worker-ceiling / OPRA-cache-deadlock lesson.


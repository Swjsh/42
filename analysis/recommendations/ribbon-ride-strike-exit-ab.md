# RIBBON-RIDE STRIKE x EXIT A/B — PROFIT-P2 (extended)

Generated: 2026-07-11T19:56:37.732334. Source: `backtest/tools/ribbon_ride_strike_exit_ab.py`.

**Signal cohort:** _signal_cache.load_or_build_signals() (analysis/exit-parity/signal-set.json), window 2025-01-01..2026-06-18, n=250 (call/bull=59, put/bear=191).

## VERDICTS

**STRIKE AXIS — ATM wins.** ATM WINS. The only strike that clears the OP-11 auto-ratify bar AND the full battery: +$47.96/tr over the OTM-2 control (exp $65.82 vs $17.86, n=244/250 identical signals), positive BOTH years (IS-2025 +$4,728 / OOS-2026 +$11,333), WF 4.25, both halves positive, drop-top-3 exp +$36.64, beats its 20-seed random-entry null (p_null 0.0476), BH-FDR survivor, and STABLE on the fill-bar sensitivity toggle (delta +$52.32 old convention, same sign). OTM-1 (+$19.12/tr, toggle-stable) confirms the direction monotonically but FAILS its own random-entry null (null_pass=False, BH non-survivor) and is dominated by ATM on every column -- do not ship the weaker cell. ITM-2 is NOT a valid gradient endpoint on this cohort: its $19,554 OOS rides a -$16,994 IS-2025 (drop-top-3 exp -$30.19, top3-day share 5.5x, maxdd -$20,844) -- a 2026-regime-concentration profile (C22), fails beats-control/WF/sub-window. The WP5 monotonic ITM>ATM>OTM gradient reproduces on ribbon_ride only through ATM (OTM-2 < OTM-1 < ATM) and BREAKS at ITM-2 -- the ranked plan's kill criterion ('gradient doesn't reproduce on this setup's cohort') is PARTIALLY triggered, exactly at the expensive end. Corroborating detail: the OTM-2 control's own drop-top-3 expectancy is NEGATIVE (-$2.13/tr) -- the live tier's entire full-sample edge rides its 3 best trades, independently confirming the friction-stream/WP5 'fragile at OTM-2' read on core ribbon_ride itself.

**EXIT AXIS — SS-B stays.** SS-B STAYS -- nothing ships on the exit axis tonight. At OTM-2 the P5 top-cell shape (stop-8%/tp+30%/sell50%/trail15/ts10) beats SS-B by +$19.04/tr on the CORRECTED fill-bar convention but the delta FLIPS to -$9.45/tr under the OLD convention -- the exact instability the two open audit chips (task_4935ea80, task_86001855) exist to resolve -> UNSTABLE_ON_OPEN_AUDIT per the pre-declared rule; cannot ship until the chips land. (Mechanism: a -8% stop is same-bar-reachable from the fill price on most entries, so this shape family is maximally sensitive to whether the fill bar's own low counts -- SS-B's -50% catastrophe cap is not, which is why the strike axis is toggle-stable.) At ITM-2 the challenger is toggle-stable and +$58.34/tr BUT regresses the OP-16 J-anchor capture (edge_capture_rel 576 vs SS-B's 1149): the structure stop rides J's big winner days fully; the tp+30% partial banks early and caps exactly those days -> fails anchor_no_regression -> WAIT_EVIDENCE. Honest flag for the rematch after the chips land: the challenger's risk profile is dramatically smoother at both strikes (OTM-2 maxdd -$687 vs SS-B's -$4,798; top3-day share 0.30 vs 1.19) -- there is real signal here, it is just not shippable on an unstable toggle / an anchor regression.

**SHIP vs WAIT (OP-11).** MAY SHIP per OP-11 auto-ratify (OOS_positive AND WF>=0.70 AND sub_window_stable AND anchor_no_regression, toggle-stable): the strike move OTM-2 -> ATM for core ribbon_ride under the SS-B exit shape. Scorecard eligibility ONLY -- this task changes no params/config; arming is the separate v15.4 weekend-rule-update step with this scorecard attached (ranked-plan P2 path). OTM-1 clears the OP-11 arithmetic too but fails its own random-entry null -- recommend NOT arming it (ATM dominates). WAITS ON THE OPEN CHIPS (task_4935ea80, task_86001855): the P5-challenger-vs-SS-B exit verdict at OTM-2 (sign-flips on the fill-bar toggle). WAITS ON MORE EVIDENCE: ITM-2 strike (C22 regime concentration, IS-2025 -$17.0K), P5-challenger at ITM-2 (OP-16 anchor regression).

> Note on the AXIS-1 header below: "Winner (by OOS total): ITM-2" is the PRE-FROZEN mechanical selection rule that only decided WHERE axis 2 ran (OTM-2 + ITM-2) -- it is NOT the strike-axis verdict. The verdict above is the comparisons + battery: ATM.

## AXIS 1 — strike (SS-B exit shape fixed)

Control: **OTM-2**. Winner (by OOS total, tie-break full expectancy): **ITM-2**.

| strike | n | exp $/tr | WR | OOS total | OOS+ | WF | qpf | edge_capture_rel | top3-day% | null_pass | p_null | bh_survivor |
|---|--:|--:|--:|--:|:--:|--:|--:|--:|--:|:--:|--:|:--:|
| OTM-2 (control) | 250 | $17.86 | 0.308 | $2759.8 | True | 2.876 | 0.5 | -24.4 | 1.188 | False | 0.1429 | False |
| OTM-1 | 249 | $36.98 | 0.333 | $6753.4 | True | 4.858 | 0.667 | 92.6 | 0.728 | False | 0.0952 | False |
| ATM | 244 | $65.82 | 0.357 | $11333.4 | True | 4.25 | 0.667 | 361.4 | 0.572 | True | 0.0476 | True |
| ITM-2 | 231 | $11.08 | 0.346 | $19554.4 | True | None | 0.5 | 1149.0 | 5.538 | True | 0.0476 | True |

**Comparisons vs control:**

- **OTM-1 vs OTM-2 (SS-B fixed)**: delta_exp=$19.12/tr, delta_OOS=$3993.6, beats_control=True, anchor_no_regression=True, unstable_on_toggle=False (sensitivity delta=$22.77), **SHIP**
- **ATM vs OTM-2 (SS-B fixed)**: delta_exp=$47.96/tr, delta_OOS=$8573.6, beats_control=True, anchor_no_regression=True, unstable_on_toggle=False (sensitivity delta=$52.32), **SHIP**
- **ITM-2 vs OTM-2 (SS-B fixed)**: delta_exp=$-6.78/tr, delta_OOS=$16794.6, beats_control=False, anchor_no_regression=True, unstable_on_toggle=False (sensitivity delta=$-5.9), **WAIT_EVIDENCE**

## AXIS 2 — exit shape (P5-CHALLENGER vs SS-B), at OTM-2 control + strike winner

| strike | shape | n | exp $/tr | WR | OOS total | OOS+ | WF | edge_capture_rel | null_pass | p_null | bh_survivor |
|---|---|--:|--:|--:|--:|:--:|--:|--:|:--:|--:|:--:|
| OTM-2 | SS-B | 250 | $17.86 | 0.308 | $2759.8 | True | 2.876 | -24.4 | False | 0.1429 | False |
| OTM-2 | P5-CHALLENGER | 250 | $36.9 | 0.276 | $5029.55 | True | 2.131 | 479.6 | True | 0.0476 | True |
| ITM-2 | SS-B | 231 | $11.08 | 0.346 | $19554.4 | True | None | 1149.0 | True | 0.0476 | True |
| ITM-2 | P5-CHALLENGER | 231 | $69.42 | 0.286 | $13303.95 | True | 8.681 | 576.05 | False | 0.0952 | False |

**Comparisons (P5-CHALLENGER vs SS-B, same strike, identical episodes):**

- **P5-CHALLENGER vs SS-B (at OTM-2)**: delta_exp=$19.04/tr (P5-challenger minus SS-B), beats_SSB=True, anchor_no_regression=True, unstable_on_toggle=True (sensitivity delta=$-9.45), **WAIT_OPEN_AUDIT_CHIPS**
- **P5-CHALLENGER vs SS-B (at ITM-2)**: delta_exp=$58.34/tr (P5-challenger minus SS-B), beats_SSB=True, anchor_no_regression=False, unstable_on_toggle=False (sensitivity delta=$2.57), **WAIT_EVIDENCE**

## BH-FDR (alpha=0.1, 6 cells compared)

3/6 cells survive BH-FDR.

## Ship vs wait

- **SHIP (clears OP-11 auto-ratify, stable on toggle):** 2
  - OTM-1 vs OTM-2 (SS-B fixed): delta_exp=$19.12/tr
  - ATM vs OTM-2 (SS-B fixed): delta_exp=$47.96/tr
- **WAIT — open audit chips (task_4935ea80, task_86001855) must land first (verdict UNSTABLE on the fill-bar toggle):** 1
  - P5-CHALLENGER vs SS-B (at OTM-2): delta_exp=$19.04/tr (sensitivity delta=$-9.45)
- **WAIT — more evidence needed (does not clear auto-ratify):** 2
  - ITM-2 vs OTM-2 (SS-B fixed): delta_exp=$-6.78/tr, fails: ['wf_ge_070', 'sub_window_stable', 'candidate_does_not_beat_control']
  - P5-CHALLENGER vs SS-B (at ITM-2): delta_exp=$58.34/tr, fails: ['anchor_regression_op16']

## Disclosures

- MEASURED (real OPRA) not REALIZED (no broker fills exist for these strike/exit combinations) -- this is a scorecard/simulation-replay artifact, per OP-33 labeled as such throughout; arming anything is a SEPARATE step this script does not take.
- Signal cohort is the FULL _signal_cache population (n as reported above), NOT re-detected per strike -- axis 1 is a true isolated-variable strike swap. Per-cell n differs slightly only where a given strike/date combination has no cached OPRA file (n_no_local_bars, disclosed per cell) -- exactly the same disclosed coverage-gap pattern WP5-STRIKE-AB and p5_topcell_real_fills_confirm.py already use.
- Trigger-level recovery is DIRECT (tw8_level_context.enrich_signal, the same per-day level-freeze convention lib/orchestrator.py used to fire these signals), NOT the backward-scan heuristic real-fills anchors need -- higher fidelity than a fleet-fills LAYER B, matching structure_stop_study's own FRESH-SLICE tier. Signals with no recoverable trigger_level fall back to SS-B's premium-only catastrophe-cap behavior (never dropped), per structure_stop_study's documented contract.
- Sensitivity column (OLD `>=` fill-bar convention) is HEADLINE METRICS ONLY (n/expectancy/wr/oos/edge_capture_rel via t4.battery) -- the random-entry-null and BH-FDR were NOT re-run a second time under the old convention (out of the stated 'top-line cells' scope; would double an already substantial compute budget for a check whose purpose is a directional-verdict-flip flag, not a second full battery).
- Random-entry null is SEED-LEVEL (random_entry_null: 20 deterministic seeds, each drawing n_signals random RTH entries with the real cell's call/put mix, replayed through the SAME strike+exit-shape engine via a custom sim_fn) -- this is the established WP5/fraud_gates convention for this exact research stream, DISTINCT from ribbon_rejection_wick_battery.bootstrap_p's individual-trade-level bootstrap; p_null here is an add-one empirical p-value over the 20 seed-level means, not a bootstrap p-value -- disclosed, not conflated.
- drop-top-3 (not drop-top-5) is this script's concentration-robustness convention, matching t4_exit_matrix/structure_stop_study/fleet_exit_parity_per_arm (the structure-stop research lineage this ticket extends) -- distinct from fraud_gates/null_baseline's drop-top-5 convention (the vwap_continuation/edgehunt research lineage). null_gate() receives exp_drop_top3 as its drop-top5_per_trade argument (functionally: 'the day-concentration-robust per-trade number', regardless of whether 3 or 5 days were dropped) -- not re-computed as a top-5 variant here.
- sub_window_stable = both chronological halves (fleet_exit_parity_per_arm.py convention) show positive total pnl -- the OP-11 'sub_window_stable' gate leg.
- QTY=10 fixed (t4/p5_topcell/structure_stop_study Layer-A convention) -- absolute $ figures are RELATIVE-to-shape-comparison, not the OP-16 account-size absolute.
- Open audit chips blocking any UNSTABLE_ON_OPEN_AUDIT verdict from shipping: task_4935ea80, task_86001855 (the fill-bar methodology fix itself, per the task brief).


# Bold strike-axis A/B -- delta-WF re-adjudication (2026-07-16)

Generated: 2026-07-16T17:21:23.958439. Source: `backtest/tools/bold_strike_axis_deltawf.py`. Methodology: `analysis/recommendations/WF-GATE-METHODOLOGY-2026-07-16.md`. Original scorecard: `analysis/recommendations/bold-strike-axis-2026-07-15.json`.

**wf_form: `ab_delta_per_trade_v2026_07_16`** -- WF-GATE-METHODOLOGY-2026-07-16.md Option B (A/B-delta WF, per-trade normalized). Control: **OTM-3**. Candidates: ['ATM', 'OTM-1', 'ITM-1', 'ITM-2'].

**Reproduction check (this run vs the original 2026-07-15 replay): all_reproduced=True** -- see `reproduction_checks` in the JSON for the per-cell n/total diff. This proves the replay mechanics are byte-identical; only the pairing/aggregation into delta-WF is new.

## Control-sanity disclosure (mandatory)

OTM-3 vs itself: is_delta_mean=0.0, oos_delta_mean=0.0, wf_delta=None, ladder_verdict=FAIL.

`wf_not_discriminating`: **False** -- candidate is_delta_mean values: {'ATM': -0.6295, 'OTM-1': -8.9658, 'ITM-1': -37.6274, 'ITM-2': -47.3684} (distinct values: [-47.37, -37.63, -8.97, -0.63]). wf_delta is None for all 4 candidates too, but for a DIFFERENT reason than the self-sanity cell's trivial 0/0 -- the ladder's is_delta_mean<=0 branch never divides, by design. The underlying is_delta_mean/oos_delta_mean signal is large, distinct, and non-degenerate per candidate (proof the gate discriminates); only the self-comparison is genuinely 0.0 everywhere.

## Per-cell table

| cell | n_shared_ep | n_is | n_oos | is_delta_mean | oos_delta_mean | WF_delta | ladder | oos_pos (carried) | sub_win (carried) | anchor (carried) | bh_fdr (carried) | all_5_pass | can_trade (carried) | evidence_status |
|---|--:|--:|--:|--:|--:|--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| ATM | 244 | 156 | 88 | -0.6295 | 35.9534 | None | INSUFFICIENT_REGIME_SHIFT | True | True | True | True | False | True | **PARKED_INSUFFICIENT_REGIME_SHIFT** |
| OTM-1 | 201 | 120 | 81 | -8.9658 | 27.6321 | None | INSUFFICIENT_REGIME_SHIFT | True | False | True | True | False | True | **PARKED_INSUFFICIENT_REGIME_SHIFT** |
| ITM-1 | 247 | 157 | 90 | -37.6274 | 97.95 | None | INSUFFICIENT_REGIME_SHIFT | True | False | True | False | False | True | **PARKED_INSUFFICIENT_REGIME_SHIFT** |
| ITM-2 | 245 | 155 | 90 | -47.3684 | 87.0189 | None | INSUFFICIENT_REGIME_SHIFT | True | False | True | True | False | True | **PARKED_INSUFFICIENT_REGIME_SHIFT** |

## Verdicts

- **ATM**: ladder=**INSUFFICIENT_REGIME_SHIFT**, all_5_pass=False, evidence_status=**PARKED_INSUFFICIENT_REGIME_SHIFT**
- **OTM-1**: ladder=**INSUFFICIENT_REGIME_SHIFT**, all_5_pass=False, evidence_status=**PARKED_INSUFFICIENT_REGIME_SHIFT**
- **ITM-1**: ladder=**INSUFFICIENT_REGIME_SHIFT**, all_5_pass=False, evidence_status=**PARKED_INSUFFICIENT_REGIME_SHIFT**
- **ITM-2**: ladder=**INSUFFICIENT_REGIME_SHIFT**, all_5_pass=False, evidence_status=**PARKED_INSUFFICIENT_REGIME_SHIFT**

## risky-3 disposition (retro-application queue item 2)

WF-GATE-METHODOLOGY-2026-07-16.md retro-application queue item 2: 'risky-3 nearer strike table (same study family)'. risky-3 is a fleet_rest arm ('risky x loose' per accounts.json's map) that resolves its <$2K strike via the SAME SHARED V15_BOLD_TIERS table as core Bold, through fleet_executor.py#_tiers_for_arm -- confirmed live by test_bold_core_strike_tier_2026_07_15.py::test_fleet_arms_resolve_otm3_under_2k_via_shared_table. _tiers_for_arm() today only branches on table=='safe' vs everything-else=V15_BOLD_TIERS (fleet_executor.py line ~158) -- it has NO branch for a per-arm nearer-strike override yet; wiring risky-3 to a different strike than core Bold would need a NEW params_patch key (e.g. strike_tier_table: 'bold_core' resolving to V15_BOLD_CORE_TIERS) added to _tiers_for_arm(), which does not exist today.

**Gate result:** NO CELL CLEARS 5/5 gates under delta-WF (all 4 candidates land in INSUFFICIENT_REGIME_SHIFT -- see cells above). The 'if its cells clear' condition this task's instruction 4 poses is FALSE.

**Action taken:** NONE. No params_patch diff drafted, nothing shipped -- there is no ship-ready cell to recommend risky-3 move to. This disposition is recorded so the queue item is CLOSED (not silently dropped), not because a decision was made to change anything.

**Revisit condition:** If a future OOS window extension (>=50% growth or n_oos>=30, per the methodology's INSUFFICIENT_REGIME_SHIFT re-test clause) moves any candidate's is_delta_mean above 0 with WF_delta>=0.70, re-run this same script and re-evaluate risky-3's params_patch wiring at that point.

## Disclosures

- wf_form: 'ab_delta_per_trade_v2026_07_16' -- WF-GATE-METHODOLOGY-2026-07-16.md Option B (A/B-delta WF, per-trade normalized). Absolute-cell WF (t4_exit_matrix.battery's wf field, reported in bold-strike-axis-2026-07-15.json) is DESCRIPTIVE ONLY here, does not gate.
- Shared episode set = union of episodes either the candidate or the control cell traded, from the SAME n=250 signal cohort every strike-AB study in this lineage shares (rrse.load_cohort()). An episode where neither side traded contributes nothing (delta=0, excluded from the shared set) -- it carries no pairing information.
- IS/OOS split reuses OOS_BOUNDARY (2026-01-01, calendar-year split) from autoresearch.strategy_space_grind -- the same boundary bold-strike-axis-2026-07-15.json's per-cell n_is/n_oos and every other strike-AB study in this lineage uses.
- Replay mechanics (SS_B_SHAPE, honest friction, 0.30 min-entry-premium floor modeled IN-SIM, 15:40 ET time stop, QTY=5, corrected fill-bar convention) are BYTE-IDENTICAL to bold_strike_axis_ab.py -- reused via direct import (bsa.SS_B_SHAPE / bsa.QTY / bsa.MIN_ENTRY_PREMIUM / bsa.BOLD_TIME_STOP / bsa.AFTERNOON_CUTOFF / bsa.STRIKE_CELLS), not re-derived. reproduction_checks confirms this run's traded-subset n/total pnl match the original 2026-07-15 scorecard's cell stats exactly for all 5 cells.
- The other 4 ratification gates (oos_positive, sub_window_stable, anchor_no_regression, bh_fdr_survivor) are CARRIED OVER from bold-strike-axis-2026-07-15.json's gates/decisions dicts verbatim, NOT recomputed -- only wf_ge_070 is replaced by wf_delta_pass (delta-WF ladder verdict == PASS) per this task's instruction.
- MEASURED (real OPRA local cache), not REALIZED -- scorecard/simulation-replay artifact, no broker fills exist for these strike/floor combinations.
- Risk-cap notional clamps (per_trade_risk_cap_pct, daily_loss_kill_switch_pct) are NOT modeled -- same disclosed gap every strike-AB study in this lineage carries.
- This is an EVIDENCE-STATUS-ONLY re-adjudication. No params/config/trading-path file touched. No orders placed. The Bold ATM tier flip (crypto/lib/strike_selection.py V15_BOLD_TIERS) stays PARKED for J's explicit words regardless of outcome, per standing commitment (three independent holds) -- a PASS/SHIP-READY-AWAITING-J label does NOT authorize shipping.


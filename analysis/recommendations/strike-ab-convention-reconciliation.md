# Strike A/B convention reconciliation

Generated: 2026-07-14T22:52:19.520853. Source: `backtest/tools/strike_ab_convention_reconciliation.py`.

## Convention audit (read first)

**fill_bar_convention_finding**: debit_spread_ab_study.py's docstring self-identifies its bar loader as 'Fill-bar-INCLUDED convention ... same as t4_exit_matrix._load_bars' -- this IS the OLD, PRE-p5_topcell-fix convention (`>=`), not the corrected one. ribbon_ride_strike_exit_ab.py's PRIMARY convention is `>` (fill bar excluded), found by p5_topcell_real_fills_confirm.py to be the one that reproduces the recorded funnel number. The task brief's framing that debit_spread_ab_study.py carries 'the corrected fill-bar convention' does not match the code -- it REGRESSED to the old one. This script uses the genuinely-corrected `>` convention as its baseline and treats debit_spread's `>=` as a toggled-away factor (old_fillbar), not a target to copy.

**shape_and_structure_layer_finding**: debit_spread_ab_study.py does NOT run at 'SS-B live scope' -- its _live_shape() reads exit-shape knobs fresh from automation/state/params.json at run time ({'premium_stop_pct': -0.5, 'tp1_premium_pct': 0.5, 'tp1_qty_fraction': 0.8, 'profit_lock_mode': 'fixed', 'profit_lock_arm_pct': 0.05, 'trail_pct': 0.125, 'runner_target_pct': 2.5}) which differ from SS_B_SHAPE ({'premium_stop_pct': -0.5, 'tp1_premium_pct': 1.0, 'tp1_qty_fraction': 0.667, 'profit_lock_mode': 'trailing', 'trail_pct': 0.15, 'runner_target_pct': 9.9}) on every knob except premium_stop_pct, AND its replay has NO structure-stop chart layer (premium-only, per its own disclosure list). This is a materially larger mechanical difference than friction/fill-bar/stage-label and is decomposed here as its own 2 factors (use_structure, shape_config) even though the task brief named only friction/fill-bar/stage/qty.

**qty_finding**: BOTH source studies use QTY=10 fixed -- confirmed NOT a source of the +$65.82 -> -$5.24 gap (byte-identical convention on both sides). Per-episode pnl here is linear in qty (every term is qty- or a.qty-scaled), so a per-contract figure = expectancy/10, and a production-qty view scales linearly: production_qty~3 (params.json min_contracts=3; recent journal/trades.csv qty column samples 1-5, mode ~3 -- QTY=10 in both studies is ~3x a typical live Safe-tier fill size, a 'relative dollars' convention per both scripts' own docstrings, not a production-scale estimate).

**Sanity check**: replay_generic at ribbon_ride's own settings reproduces n=244 exp=$65.82 (cached study: n=244 exp=$65.82).

## JOB1(a) — strike axis, SS-B fixed, honest friction added

| strike | n | exp $/tr | OOS exp $/tr | WR | OOS+ | WF | clears-zero (overall) | clears-zero (OOS) |
|---|--:|--:|--:|--:|:--:|--:|:--:|:--:|
| OTM-2 (control) | 250 | $-31.69 | $-22.77 | 0.276 | False | None | False | False |
| OTM-1 | 249 | $-12.41 | $29.75 | 0.301 | True | None | False | True |
| ATM | 244 | $18.83 | $63.81 | 0.328 | True | None | True | True |
| ITM-2 | 231 | $-38.1 | $180.33 | 0.333 | True | None | False | True |

**Comparisons vs OTM-2 control (honest, SS-B fixed, friction added):**

- **OTM-1**: delta_exp=$19.28/tr honest (was $19.12/tr pre-friction) -- beats_control=True, relative_verdict_survives_honest_conventions=True
- **ATM**: delta_exp=$50.52/tr honest (was $47.96/tr pre-friction) -- beats_control=True, relative_verdict_survives_honest_conventions=True
- **ITM-2**: delta_exp=$-6.41/tr honest (was $-6.78/tr pre-friction) -- beats_control=False, relative_verdict_survives_honest_conventions=True

## JOB1(b) — ATM gap bridge (+$65.82 → -$5.24)

ribbon_ride setting exp=$65.82 (n=244) -> debit_spread setting exp=$-5.24 (n=244). Total gap = $-71.06/tr.

**Forward path** (ribbon_ride settings -> debit_spread settings, in this order):

| step | factor | from -> to | exp before | exp after | delta |
|--:|---|---|--:|--:|--:|
| 1 | use_structure | True -> False | $65.82 | $98.37 | $32.55 |
| 2 | shape_config | SS-B -> LIVE | $98.37 | $40.56 | $-57.81 |
| 3 | old_fillbar | False -> True | $40.56 | $42.62 | $2.06 |
| 4 | friction | False -> True | $42.62 | $-5.24 | $-47.86 |
| 5 | stage_fix | False -> True | $-5.24 | $-5.24 | $0.0 |

**Reverse path** (debit_spread settings -> ribbon_ride settings, re-expressed forward), for path-dependence comparison:

| step | factor | from -> to | exp before | exp after | delta |
|--:|---|---|--:|--:|--:|
| 1 | use_structure | False -> True | $65.82 | $98.37 | $32.55 |
| 2 | shape_config | LIVE -> SS-B | $98.37 | $40.56 | $-57.81 |
| 3 | old_fillbar | True -> False | $40.56 | $42.62 | $2.06 |
| 4 | friction | True -> False | $42.62 | $-5.24 | $-47.86 |
| 5 | stage_fix | True -> False | $-5.24 | $-5.24 | $-0.0 |

**Order-independent main effect per factor** (average delta going ribbon->debit setting, averaged over all 16 joint settings of the other 4 factors):

| factor | mean delta | min | max |
|---|--:|--:|--:|
| use_structure | $27.82 | $20.27 | $35.46 |
| shape_config | $-54.09 | $-63.81 | $-45.53 |
| old_fillbar | $2.63 | $0.32 | $4.28 |
| friction | $-48.83 | $-52.83 | $-44.08 |
| stage_fix | $0.0 | $0.0 | $0.0 |

## Disclosures

- MEASURED (real OPRA local cache), not REALIZED -- scorecard/simulation-replay artifact, no broker fills exist for these strike/shape/friction combinations.
- replay_generic degenerates to sss.replay_structure_aware() byte-for-byte when friction=False, stage_fix=False, old_fillbar=False, use_structure=True, shape=SS-B -- verified against the cached ribbon-ride-strike-exit-ab.json ATM cell (see sanity_check_reproduction above).
- premium_stop stage-label fix is empirically confirmed a NO-OP for SS-B specifically: SS_B_SHAPE carries no profit_lock_arm_scope override, so ExitState.from_entry defaults it to ARM_SCOPE_POST_TP1, under which runner_stop_premium is set once at entry and never ratcheted before TP1 -- byte-identical to the static entry*(1+premium_stop_pct) the old code used. The fix matters for ARM_SCOPE_FULL shapes (e.g. hold_posture_ab_study.py's reuse) -- not exercised here.
- No random-entry-null / BH-FDR battery re-run here (out of scope for a convention decomposition -- the original strike A/B's null/FDR results are unaffected by these convention toggles' significance testing, only by point estimates).
- job1a's fill-bar convention is NOT re-toggled (held at the corrected `>` throughout) -- per the finding above, `>` was already correct in the original study; there is no 'fill-bar fix' left to apply to job1a. The old `>=` convention only appears in job1b's gap-bridge as the factor explaining why debit_spread_ab_study.py's number differs.


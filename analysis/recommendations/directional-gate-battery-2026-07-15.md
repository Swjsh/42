# Directional Gate Battery -- 2026-07-15

> Pre-registered battery result. Runner: `backtest/tools/directional_gate_battery.py`. Pre-registration: `analysis/recommendations/prereg-directional-gate-battery-2026-07-15.json`. Source report: `markdown/audits/DIRECTIONAL-GATE-DEEP-RESEARCH-2026-07-15.md`.

Generated: 2026-07-15T17:33:41.093822. Preflight: {'prereg_version': 1, 'prereg_version_ok': True, 'prereg_sha256_16_recomputed': 'c0a96f51cc0af81d', 'prereg_sha256_16_stored': 'c0a96f51cc0af81d', 'prereg_hash_ok': True}.

Exit shape used (derived from `strategies.RIBBON_RIDE.exit.to_dict()`): `{'premium_stop_pct': -0.5, 'tp1_premium_pct': 1.0, 'tp1_qty_fraction': 0.667, 'profit_lock_mode': 'trailing', 'trail_pct': 0.15, 'runner_target_pct': 99.0, 'profit_lock_arm_pct': 0.05}`

Equity used (live-verified this session): Safe $1569.32 (ATM), Bold $1963.04 (OTM-3). Qty: {'safe': 3, 'bold': 5}.

**VERDICT: 0 DISABLE / 6 KEEP / 7 UNCHANGED across the 12 REVALIDATE gates.** No params.json edit was needed unless DISABLE > 0 above.

## Cross-study methodology check (WF-null artifact caution)

A concurrent session flagged mid-run that a related strike-axis study's WF gate was null for ALL its cells including its own control. Mid-run methodology heads-up received from a concurrent session (Bold strike-axis study, analysis/recommendations/bold-strike-axis-2026-07-15.json): that study's WF gate was null for ALL 6 cells including its own control -- a real red flag there. Checked against THIS battery's actual output before shipping (not blindly applied): 4/6 gates have a real, non-null, meaningfully negative WF (driven by genuinely negative recovered OOS dollars vs a positive historical IS baseline); the 2 WF=None cases each have a distinct structural cause (zero prior IS trades / zero surviving OOS trades post-premium-floor), unrelated to the strike-axis study's 2025-half-vs-2026-half split (this battery's WF does not use that split at all -- IS is each gate's own pre-existing ratified scorecard). Spot-checked trade-level strikes/premiums/structure-stop pattern for the largest cohort (block_elite_bull/safe, n=18) -- mechanistically explicable, not degenerate.

**WF is discriminating correctly in this battery, NOT the same artifact. No methodology change made. Moot for shipping regardless (0 DISABLE verdicts either way, well under the >3-disables recommendation threshold).**

- Gates with real, non-null WF this run: ['block_elite_bull__safe', 'entry_bar_body_pct_min__safe', 'block_bull_1100_1200__safe', 'block_conf_lvl_rec_afternoon__bold']
- Gates with a structurally-N/A WF, each with its own distinct cause: {'block_elite_bull__bold': "is_delta=0 (no prior IS trades in this gate's own VIX-band history)", 'require_bearish_fill_bar__bold': 'n_oos=0 (all 10 recovered events sub-$0.30, dropped by the premium floor)'}

## Testable gates (real mined + replayed A/B)

| Gate | Account | n | Total PnL | WR | WF | SubWin stable | Anchor | BH-sig | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| `block_elite_bull` | safe | 18 | $-598.15 | 11% | -4.117 | False | False | False | **KEEP** |
| `block_elite_bull` | bold | 2 | $144.6 | 50% | N/A | True | False | False | **KEEP** |
| `require_bearish_fill_bar` | bold | 0 | $0 | 0% | N/A | True | True | False | **KEEP** |
| `entry_bar_body_pct_min` | safe | 3 | $-126.0 | 0% | -2.136 | True | False | False | **KEEP** |
| `block_conf_lvl_rec_afternoon` | bold | 0 | $0 | 0% | 0.0 | True | True | False | **KEEP** |
| `block_bull_1100_1200` | safe | 2 | $-147.0 | 0% | -9.084 | True | False | False | **KEEP** |

### `block_elite_bull` (safe)

- Verdict: **KEEP** -- fails: ['1_oos_positive', '2_wf_ge_070_or_waived', '3_sub_window_stable', '4_anchor_no_regression']
- Mining: {'n_raw_ticks': 101, 'n_reason_mismatch': 0, 'n_events_total': 21, 'n_excluded': 3, 'n_excluded_stale_echo': 0, 'n_excluded_downstream_double_block': 3, 'n_flagged_open_adjacent': 0, 'n_kept': 18}
- Recovered/replayed n=18 (missing bars=0, drop_reasons={})
- Total PnL $-598.15, expectancy $-33.23/tr, WR 11.1%
- By-day: {'2026-07-09': -4.15, '2026-07-10': -57.0, '2026-07-14': -168.0, '2026-07-15': -369.0}
- Sub-windows: SW1(07-09/10)=$-61.15 SW2(07-13..15)=$-537.0, hurt=2/2, stable=False
- Structure-stop available for 12/18 trades, fired for 9
- WF: -4.117 (per-trade normalized, backtest/safe_fill_bar_gate.py G3 formula) vs prior IS baseline {'source': 'automation/state/params.json _block_elite_bull_doc (2026-06-18 all-VIX[0,25) extension, currently-live ratification)', 'is_delta': 113.0, 'n_is': 14}
- Anchor: False -- PASS (reused).
- BH-FDR: p=0.7814477627001765, threshold=0.05, significant=False

### `block_elite_bull` (bold)

- Verdict: **KEEP** -- fails: ['4_anchor_no_regression', '5_evidence_n_advisory_pass']
- Mining: {'n_raw_ticks': 111, 'n_reason_mismatch': 0, 'n_events_total': 23, 'n_excluded': 9, 'n_excluded_stale_echo': 0, 'n_excluded_downstream_double_block': 9, 'n_flagged_open_adjacent': 0, 'n_kept': 14}
- Recovered/replayed n=2 (missing bars=12, drop_reasons={'sub_floor_premium': 12})
- Total PnL $144.6, expectancy $72.3/tr, WR 50.0%
- By-day: {'2026-07-09': 144.6}
- Sub-windows: SW1(07-09/10)=$144.6 SW2(07-13..15)=$0, hurt=0/2, stable=True
- Structure-stop available for 2/2 trades, fired for 0
- WF: None (N/A structural (no IS baseline / is_delta=0)) vs prior IS baseline {'source': 'automation/state/aggressive/params.json _block_elite_bull_doc (2026-06-18 17.5->18.0 VIX extension only)', 'is_delta': 0.0, 'n_is': 0, 'wf_treatment': "STRUCTURAL N/A (n_is=0, division undefined) -- same precedent as analysis/recommendations/block_elite_bull_vix_high_18.json ('wf_norm: null, OOS positive = economic ratification criterion' when no IS baseline exists). Ratification for this specific gate/account falls back to OOS_positive AND sub_window_stable AND anchor_no_regression AND evidence_n, WF requirement waived-as-N/A rather than treated as a silent fail."}
- Anchor: False -- VIX-band leg does NOT structurally clear the gate as irrelevant to these 2 anchors (both losers). Tier/trigger match is UNVERIFIED this session -- archetype tags for both (drift_chop_trap / manual_anticipation_at_resistance, journal/trades.csv archetype_match_json) suggest anticipation/chop entries rather than a clean confluence+level_reclaim ELITE pattern, but this is not a rigorous re-derivation. Because both anchors here are LOSERS (engine 'must skip or lose less'), the worst case if the gate DID match is NEUTRAL-TO-MILDLY-POSITIVE for the gate being armed (it would correctly filter losers) -- meaning DISABLING carries a real but bounded and non-catastrophic anchor risk (could re-admit 2 known losers, never loses a winner). anchor_no_regression = UNVERIFIED (bounded risk, conservative treatment in the ratification bar below: this leg does NOT count as a clean PASS).
- BH-FDR: p=0.3570157639770122, threshold=0.025, significant=False

### `require_bearish_fill_bar` (bold)

- Verdict: **KEEP** -- fails: ['1_oos_positive', '2_wf_ge_070_or_waived', '5_evidence_n_advisory_pass']
- Mining: {'n_raw_ticks': 37, 'n_reason_mismatch': 0, 'n_events_total': 10, 'n_excluded': 0, 'n_excluded_stale_echo': 0, 'n_excluded_downstream_double_block': 0, 'n_flagged_open_adjacent': 0, 'n_kept': 10}
- Recovered/replayed n=0 (missing bars=10, drop_reasons={'sub_floor_premium': 10})
- Total PnL $0, expectancy $0.0/tr, WR 0.0%
- By-day: {}
- Sub-windows: SW1(07-09/10)=$0 SW2(07-13..15)=$0, hurt=0/2, stable=True
- Structure-stop available for 0/0 trades, fired for 0
- WF: None (N/A structural (n_is=0 or n_oos=0)) vs prior IS baseline {'source': 'analysis/recommendations/fill-bar-gate-sweep.json (2026-06-17 J-approved ratification, Bold row)', 'is_delta': 363.16, 'n_is': 26}
- Anchor: True -- If this gate had been armed on the anchor population, it would have BLOCKED 2 of 3 REAL WINNERS (5/01 +$470, 5/04 +$730) while only correctly filtering both real losers (5/05, 5/06) -- it does not separate winners from losers in J's own anchor trades; on this evidence the mechanism is anti-correlated with J's edge, not merely neutral. For a DISABLE proposal (this battery's direction of test, since the gate is currently ARMED on Bold), this is UNAMBIGUOUSLY SUPPORTIVE: disabling the currently-armed gate does not remove any protection the anchors need -- if anything it removes a mechanism that would have cost 2 of 3 real winning anchor trades. anchor_no_regression = PASS (strong).
- BH-FDR: p=None, threshold=None, significant=False

### `entry_bar_body_pct_min` (safe)

- Verdict: **KEEP** -- fails: ['1_oos_positive', '2_wf_ge_070_or_waived', '4_anchor_no_regression', '5_evidence_n_advisory_pass']
- Mining: {'n_raw_ticks': 12, 'n_reason_mismatch': 0, 'n_events_total': 3, 'n_excluded': 0, 'n_excluded_stale_echo': 0, 'n_excluded_downstream_double_block': 0, 'n_flagged_open_adjacent': 0, 'n_kept': 3}
- Recovered/replayed n=3 (missing bars=0, drop_reasons={})
- Total PnL $-126.0, expectancy $-42.0/tr, WR 0.0%
- By-day: {'2026-07-13': -90.0, '2026-07-14': -36.0}
- Sub-windows: SW1(07-09/10)=$0 SW2(07-13..15)=$-126.0, hurt=1/2, stable=True
- Structure-stop available for 2/3 trades, fired for 2
- WF: -2.136 (per-trade normalized, backtest/safe_fill_bar_gate.py G3 formula) vs prior IS baseline {'source': 'analysis/recommendations/safe_entry_body_gate.json (2026-06-18 ratification)', 'is_delta': 295.0, 'n_is': 15}
- Anchor: False -- PASS (reused).
- BH-FDR: p=0.9595476229940433, threshold=0.075, significant=False

### `block_conf_lvl_rec_afternoon` (bold)

- Verdict: **KEEP** -- fails: ['1_oos_positive', '2_wf_ge_070_or_waived', '5_evidence_n_advisory_pass']
- Mining: {'n_raw_ticks': 10, 'n_reason_mismatch': 0, 'n_events_total': 2, 'n_excluded': 1, 'n_excluded_stale_echo': 1, 'n_excluded_downstream_double_block': 0, 'n_flagged_open_adjacent': 0, 'n_kept': 1}
- Recovered/replayed n=0 (missing bars=1, drop_reasons={'sub_floor_premium': 1})
- Total PnL $0, expectancy $0.0/tr, WR 0.0%
- By-day: {}
- Sub-windows: SW1(07-09/10)=$0 SW2(07-13..15)=$0, hurt=0/2, stable=True
- Structure-stop available for 0/0 trades, fired for 0
- WF: 0.0 (AGGREGATE (not per-trade normalized -- n_is unavailable, see prereg caveat)) vs prior IS baseline {'source': "automation/state/aggressive/params.json _block_conf_lvl_rec_afternoon_doc ('Original ratification 2026-06-17')", 'is_delta': 468.0, 'n_is': None, 'n_is_caveat': 'Exact removed-trade count not cleanly re-extractable from the cited doc this session (aggregate IS_delta only) -- WF for this gate is reported as an AGGREGATE ratio (OOS_delta/IS_delta), NOT the per-trade-normalized (OOS_delta/n_oos)/(IS_delta/n_is) form used for the other 5 gates. Disclosed, not silently treated as equivalent.', 'additional_prior_evidence': 'analysis/recommendations/conf_lvl_rec_afternoon_revalidate.json already found verdict UNBLOCK_SUPPRESSES_WINNERS (removes a +$1,034 winner; $0 OOS due to a suspected bt-vs-entry_time_et timestamp-keying bug at gates.py:386, per source report row 12) -- cited as directional prior evidence, not re-derived here.'}
- Anchor: True -- Structurally clear -- neither anchor could ever have been touched by this gate regardless of any other field. anchor_no_regression = PASS (clean, structural).
- BH-FDR: p=None, threshold=None, significant=False

### `block_bull_1100_1200` (safe)

- Verdict: **KEEP** -- fails: ['1_oos_positive', '2_wf_ge_070_or_waived', '4_anchor_no_regression', '5_evidence_n_advisory_pass']
- Mining: {'n_raw_ticks': 6, 'n_reason_mismatch': 0, 'n_events_total': 2, 'n_excluded': 0, 'n_excluded_stale_echo': 0, 'n_excluded_downstream_double_block': 0, 'n_flagged_open_adjacent': 0, 'n_kept': 2}
- Recovered/replayed n=2 (missing bars=0, drop_reasons={})
- Total PnL $-147.0, expectancy $-73.5/tr, WR 0.0%
- By-day: {'2026-07-10': -147.0}
- Sub-windows: SW1(07-09/10)=$-147.0 SW2(07-13..15)=$0, hurt=1/2, stable=True
- Structure-stop available for 2/2 trades, fired for 2
- WF: -9.084 (per-trade normalized, backtest/safe_fill_bar_gate.py G3 formula) vs prior IS baseline {'source': 'automation/state/params.json _block_bull_1100_1200_doc (2026-06-18 ratification)', 'is_delta': 89.0, 'n_is': 11, 'superseded_revalidation_note': "A 2026-06-26 revalidation (safe_bull_1100_1200_gate.json, cited 'G1 PASS +$1,299, anchor PASS' in the source report) used the OTM-2 strike tier, not the ATM tier live since 07-14 -- that number is NOT reused here (source report section 5 process-failure finding); only the original 06-18 IS baseline is carried forward for WF continuity."}
- Anchor: False -- PASS (reused).
- BH-FDR: p=1.0, threshold=0.1, significant=False

## Untestable this session (left UNCHANGED)

| Gate | Fresh OOS ticks | Current value | Note |
|---|---|---|---|
| `block_level_rejection__safe` | 0 | `True` |  |
| `midday_trendline_gate__both` | 0 | `False` | Already OFF both accounts; 0 fresh evidence either way. The report's 3-way internally-contradictory provenance is NOT resolved by this battery (no data to resolve it with this week) -- stays OFF, flagged for a dedicated re-run once the target population (midday single-trigger trendline_rejection) actually occurs. |
| `block_conf_lvl_rej_midday_afternoon__both` | 0 | `absent(Safe)/False(Bold), both OFF` | 0 fresh blocks is CONSISTENT with the prior evidence's own lean (both prior studies found this gate negative-toward-arming) -- stays OFF, no action needed either way. |
| `entry_bar_body_pct_min_bull__safe` | 0 | `absent, OFF` | Structurally cannot fire (key absent both accounts) -- 0 is expected, not informative either way. Stays OFF (matches the one thin prior study's WATCH, not-ratified verdict). |
| `vix_bear_hard_cap__safe` | 0 | `23.0` | VIX has not touched 23.0 in the fresh OOS window (observed range this session ~15.7-17.3) -- the gate's target population did not occur, not evidence either way. Stays armed at 23.0. |
| `min_ribbon_momentum_cents__both` | 0 | `null(Safe)/absent(Bold), both OFF` | 0 fires since the 2026-07-11 zero-vs-None code fix (source report's own finding); code-guaranteed off regardless of params value. Low urgency, harmless, left UNCHANGED. |
| `max_ribbon_duration_bars__both` | 0 | `999(Safe, arithmetically unreachable)/absent(Bold), both mechanically inert` | Mechanically inert at current values (Safe=999 effectively unreachable, Bold absent). Low urgency, harmless, left UNCHANGED. Also excluded on a second, independent ground: evaluating it would require reconstructing the historical ribbon_df (RibbonState per bar) for the OOS window, which is out of this session's compute budget (see current_config.known_simplifications) -- doubly untestable. |

## Out of scope (J-decision-gated, not re-run)

- trendline_requires_ribbon_flip (J-decision-gated per automation/overnight/queue.md and the source report's 'Do not touch without J' list)
- block_bull_morning_agg (J explicitly killed it 2026-06-24, re-arming needs J directly)

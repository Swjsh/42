# Lesson: Dominant upstream quality filter supersedes all downstream class-based entry blockers

> Queued by autonomous WF validation session 2026-06-18.

## Symptom

6-fold walk-forward validation of AGG production gates revealed 3 gates were consistently hurting OOS performance (0/6 OOS passes each): `midday_trendline_gate`, `block_conf_lvl_rej_midday_afternoon`, `block_level_rejection`. All three had been individually ratified via OP-22 with strong IS and OOS deltas. After 4-way A/B confirmation, all three were removed. Combined effect: AGG OOS WR 55.6% → 68.0%, OOS P&L +$1,205 → +$1,853 (+$648, +53.7%).

## Root cause

`require_bearish_fill_bar` (the dominant bear quality filter, ratified 2026-06-17) changed the composition of which trades survive to the gate layer. Pre-fill-bar:
- Midday trendline bears: weak, 1-trigger entries → blocking them was profitable
- Level_rejection bears: often low-conviction → blocking them was profitable
- Conf+lvl_rej midday/afternoon: historically stop-heavy → blocking was profitable

Post-fill-bar: all the above trade classes must first pass the N+1 bar bearish confirmation. The trades that survive this filter are ALREADY higher quality. Then the downstream class-based blockers (midday_trendline, level_rejection, conf+lvl_rej) remove exactly those quality-filtered winners.

The C15 interaction is asymmetric: the fill_bar gate is applied at entry time and can only pass or block a trade once. The class-based gates have no way to know the fill_bar already verified quality — they block unconditionally by class.

## Pattern

When a strong upstream quality filter (fill_bar, entry confirmation, momentum check) is added AFTER class-based entry blockers were ratified, those class-based blockers should be re-evaluated in the new multi-gate context. The independent-ratification assumption fails when filters share the same trade pool.

**Detection:** Run 6-fold WF validation on all gates together. If a gate shows 0/6 OOS passes (consistently hurting across ALL time windows), it is either redundant or harmful in the multi-gate context — investigate for C15 interactions before accepting it as a real signal.

## Fix

Applied: removed `midday_trendline_gate`, `block_conf_lvl_rej_midday_afternoon`, `block_level_rejection` from AGG. Retained `require_bearish_fill_bar` as the sole bear quality filter.

**Structural rule (new):** When adding a strong quality gate (entry confirmation, fill quality check, momentum filter), immediately re-run WF validation on ALL existing class-based gates in the same trade pool. Any that show 0/6 OOS passes are candidates for removal via 4-way A/B. Do not wait for OOS evidence to accumulate at full IS/OOS split — the rolling WF will surface this faster.

**SAFE exception:** `require_bearish_fill_bar` is AGG-only. SAFE `midday_trendline_gate` remains STABLE (4/6) because SAFE does not have the fill_bar gate. The supersession is tied to which accounts share the upstream filter.

## Cross-reference
- C15: Gates interact multiplicatively — trace session cascades
- L47 (broker is truth), L66 (gates cascade)
- Scorecard: `analysis/recommendations/agg_wf_gate_removal_2026_06_18.json`

## Candidate lesson number
Next available (L152+ — 151 lessons as of 2026-06-17; FOMC-eve + L150 pending)

# Directional Gate Deep Research — 2026-07-15

> J: "why the fuck are strats gated on bearish vs bullish... review EVERYTHING." Full swarm audit of every directional gate in the live decision path (`setup/scripts/heartbeat_core.py` → `backtest/lib/engine/engine_cli.py` → `backtest/lib/engine/gates.py` (15 gates) → `backtest/lib/filters.py` scoring), cross-checked against `automation/state/core-decisions.jsonl` (11,058 rows, 2026-06-25T13:48:17 → 2026-07-15T15:55:06) and `automation/state/fill-funnel-2026-07-*.json` (11 files).
>
> **Reading order:** (1) verdict table, (2) trigger-class asymmetries — the structural root cause, (3) participation math, (4) ranked fix list, (5) process-failure note.
>
> All claims cite `file:line`. UNVERIFIED is labeled explicitly where evidence doesn't reach certainty.

---

## 1. Verdict table — the 15 `GATE_ORDER` gates + the 1 pre-gate structure veto

Doctrine test for KEEP: (1) real non-prose provenance exists, AND (2) validated under the CURRENT engine (post SS-B 2026-07-09/10, post ATM-strike-arming 2026-07-14, post premium-floor 2026-07-09), AND (3) recent live evidence doesn't contradict. Fail test 1 alone with no refutation → KILL. Fail test 2 (provenance real but stale) → REVALIDATE. A KILL that a refutation pass overturned reverts to REVALIDATE with the refuting evidence cited.

| # | Gate | Side | Live: Safe / Bold | Provenance date (file) | Validated-under config | Blocks since 07-01 (favor/adverse/unknown) | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | `block_level_rejection` | bear only (`side=="P"`) | **true** / `false` (removed, agg_wf_gate_removal 06-18) | 2026-06-17, `level-rejection-gate-01.json` — IS +$13,181 (n244→227), OOS +$682, WF=0.842, 5/5 gates PASS | Pre-SS-B / pre-floor / pre-ATM / pre-06-18 strike-tier ship | **0** — target population (LEVEL-tier bear `level_rejection`, no confluence) has not occurred live since 06-25; current bear signals are 290/291 single-trigger `trendline_rejection` | **REVALIDATE** |
| 2 | `trendline_requires_ribbon_flip` | bear-only-by-construction (no bull trendline detector exists) | absent both files → **off** both accounts | 2026-06-17, `trendline-ribbon-flip-01.json` — status **HOLD**, OOS delta −$190, WF=−1.371 FAIL | Pre-SS-B/floor/ATM | 0 (gate off; would have blocked 149 of the 149 live `trendline_rejection`-only ENTER_BEAR episodes since 07-01 had it been armed) | KILL recommendation was issued, then **REFUTED** by adversarial pass: 3 prior audits (`GATE-PROVENANCE-AUDIT-2026-07-02.md:35`, `GATE-PROVENANCE-CENSUS-2026-07-09.md:56`, `GATE-PROVENANCE-SWEEP-2026-07-10.md:48-53`) independently graded this exact dormant code KEEP/ignore, and the code is live-used in `backtest/lib/orchestrator.py:438-439,601,755-756,1310,1365` plus pinned by 3 parity tests (`test_engine_gates_parity.py:113-119,122-140,167-177`) whose deletion the original KILL never scoped. **→ REVALIDATE** (code stays; if J wants the underlying idea re-tested, see revalidation spec below) |
| 3 | `block_elite_bull` | bull only (`level_reclaim`) | Safe **true**, VIX[0,25) / Bold **true**, VIX[15,18) | Safe: 2026-06-18 extended-band + 2026-07-10 SS-B revalidation KEEP (SS-B cohort still negative, `block-elite-bull-ssb-revalidation.json`); Bold: 2026-06-18 only, **explicitly excluded** from the 07-10 revalidation (`block-elite-bull-ssb-preregistration.json:9`) | Safe: SS-B-tested but non-ATM strike (`strike_offset=-2`); Bold: pre-SS-B, never revalidated | 290 raw ticks / 28 episodes / 9 days; 23 scoreable: 7 favor / 6 adverse / 10 chop / 5 censored — 6 of 7 "favor" cluster on one trend day (07-09); by-day tally is 4 AGAINST vs 2 FOR | **REVALIDATE** (Safe: re-test at ATM; Bold: run the study that has never existed) |
| 4 | `block_bull_ribbon_flip` | bull only (`side=="C"`) | absent both → **off** both accounts | 2026-06-17, CHANGELOG.md:190 — **DEFINITIVELY REJECTED**, WF=−23.984, SW_hurt=3/5, OOS −$3,123; param built "research-tool only, never set True" | N/A — never armed on any engine | 0 (never fires; corroborated by `fleet/accounts.json:181`, two prior audits) | **KILL — UPHELD** by adversarial refutation pass (refuted:false). Only scope note: the doctrine text at `markdown/doctrine/BULL-DIRECTION-ACTIVATION.md:25` misattributes this gate to a study (`chef-bull-scope-ab-2026-06-26.json`) that contains no such sub-split — that's a **doc bug**, spawned as `task_59631bcc`, separate from the code (which correctly stays off, has a passing regression guard `test_participation_cascade.py:504-520`, and needs no further action) |
| 5 | `block_bull_1100_1200` | bull only, 11:00–12:00 ET | Safe **true** / Bold absent → off | 2026-06-18 orig (`safe_bull_1100_1200_gate.json`) + 2026-06-26 revalidation (real OPRA fills, G1 PASS +$1,299, anchor PASS) — but revalidation used **OTM-2** strike, not the ATM tier live since 07-14 | Pre-SS-B/floor at both dates; 06-26 revalidation used the wrong (stale) strike convention even on the day it ran | 2 episodes (both 07-10, Safe only): both favorable-if-unblocked (+$0.82/+$1.14 and +$0.00/+$0.79) — 0/2 adverse | **REVALIDATE** |
| 6 | `block_bull_morning_agg` | bull only, 10:00–11:30 + ≥14:00 ET, Bold-labeled | absent Safe / `false` Bold (**intentionally disabled**) | 2026-06-18 ratify (IS +$4,346/OOS +$1,210, 5/5 PASS) → 2026-06-24 **J directive**: "remove this entirely" after it vetoed a real 11/11 BULLISH_RECLAIM | Pre-SS-B/floor | 0 (confirmed no-op) | **REVALIDATE**, but `automation/overnight/queue.md:296` flags any revival as **J-decision-gated** — do not auto-ship even if the numbers hold |
| 7 | `require_bearish_fill_bar` | bear only (`side=="P"`), look-ahead-safe (reads next-bar close) | absent Safe / **true** Bold | 2026-06-17 ratify (J-approved, IS +$363/OOS +$1,153, WF=18.5) → 2026-06-26 revalidation (`fill-bar-gate-revalidate-current-engine.json`) **FAILED 3/5 gates**, verdict="UNBLOCK" — never shipped | Pre-SS-B both times; 06-26 revalidation itself now stale (pre-SS-B/floor) | 22 episodes / 17 scoreable: 6 favor / 5 adverse / 6 chop / 5 no-data — roughly a wash, slight lean COSTING | **REVALIDATE** — two independent stale-config studies already lean UNBLOCK; highest-priority Bold bear re-check in this inventory |
| 8 | `min_ribbon_momentum_cents` | side-blind (not really directional) | Safe **null** (off) / absent Bold → off | 2026-06-16/17 REJECTED (WF=−2.204) + 2026-07-08 residual-bug probe (`GATE_HARMFUL_DISABLE`) + 2026-07-11 code hardening (0/None both mean off, guarded by `test_gate_min_ribbon_momentum_cents_zero_is_off`) | Newest supporting evidence (07-08) predates SS-B/floor/ATM | 13 raw / 3 episodes, **all on 07-07** (before the 07-11 code fix) — 0 fires since 07-11 | **REVALIDATE** (low urgency — code-guaranteed off, zero live impact since the fix) |
| 9 | `max_ribbon_duration_bars` | side-blind | Safe=999 (arithmetically unreachable) / Bold=null (falsy, skipped) | 2026-06-16 REJECTED, `max_ribbon_dur8_ab_scorecard.json`, WF=0.072, unstable sub-windows | Pre-SS-B/floor/ATM | 0 (mechanically inert) | **REVALIDATE** (low urgency, harmless dead knob) |
| 10 | `midday_trendline_gate` | bear only (trendline-tied) | **false** both accounts | Three-way contradiction: 06-16 says ON (+393c), 06-18 says **KEEP-ON for Safe** (`agg_wf_gate_removal_2026_06_18.json` `safe_wf_summary`), 06-26 flipped Safe to OFF citing an un-scorecarded "+$849" swarm-consult number | All pre-SS-B/floor/ATM; the flip itself has no backing JSON | 0 | **REVALIDATE** — internally contradictory provenance, needs a clean rerun split by account |
| 11 | `block_conf_lvl_rej_midday_afternoon` | bear only (`level_rejection`+confluence, ≥11:30) | absent Safe (REJECTED 06-17, IS −$5,152) / `false` Bold (removed 06-18, WF 0/6 folds) | Both real, both negative-toward-arming (consistent with current off state) | Pre-SS-B/floor/ATM, no re-run in the 07-09→07-15 window at all | 0 | **REVALIDATE** (evidence supports staying off; just needs a current-engine confirmation per the standing "re-audit on engine change" rule) |
| 12 | `block_conf_lvl_rec_afternoon` | bull only (`level_reclaim`+confluence, ≥14:00) | absent Safe / **true** Bold ("KEPT but DEAD" per its own doc) | 2026-06-26 revalidation: verdict **"UNBLOCK_SUPPRESSES_WINNERS"** (removes a +$1,034 winner; $0 OOS because of a `bt` vs `entry_time_et` timestamp-keying bug at `gates.py:386`) — never applied, still `true` live | Pre-SS-B/floor; the revalidation itself has a suspected timestamp bug that needs re-checking | 3 episodes: 2 favor / 0 adverse / 1 no-data | **REVALIDATE** — a validated-to-remove gate is still armed on Bold |
| 13 | `entry_bar_body_pct_min` | bear only, doji filter | Safe **0.20** / absent Bold → off | 2026-06-18 ratify (OOS +$566, WF=7.19) → 2026-06-26 15-agent audit recommended UNBLOCK (removes 5 fat-tail winners) → queued in `.claude/agent-memory/chef/project_direction_block_audit_synthesis.md:18` as "ship after-hours" — **never shipped** | Pre-SS-B/floor/ATM; the 06-26 finding is itself now stale too | 17 raw / 4 episodes — all 4 confounded by an orthogonal blocker (already-filled position, PDT cap, or 15:00 ET ceiling), so 0 marginal live effect measurable | **REVALIDATE — highest-priority Safe bear re-check**: a queued-but-dropped removal recommendation sitting on top of stale original evidence |
| 14 | `entry_bar_body_pct_min_bull` | bull only (mirror of #13) | absent **both** → off | `j-entry-quality.json` (2026-06-20, missed by 2 prior audits) — tested at 0.20, OOS **−$1,240** (n=1 removed winner), WF=−4.622, verdict **WATCH** (not ratified) | Pre-SS-B/floor/ATM | 0 (structurally can't fire, key absent both) | **REVALIDATE** — this is the literal asymmetric pair the task named (bear armed 0.20, bull never armed anywhere); real study exists but is thin-n and stale |
| 15 | `vix_bear_hard_cap` | bear only, VIX≥23 ceiling | Safe **23.0** / **absent Bold entirely** (own doc flags "BOLD-VIX-BEAR-CEILING-GAP") | 2026-06-18 ratify (IS +$790/OOS +$420, WF=0.797, "cleanest gate," 5/5 PASS) | Mechanism narrative cites the pre-06-18 asymmetric −10% bear premium stop, superseded twice since (chart-stop-primary 06-18, SS-B 07-09) | Not separately re-audited this pass (07-14 bear-vix-floor study explicitly out of scope for this gate) | **REVALIDATE** — confirmed live, narrative predates 3 engine changes |
| 16 | `structure_veto_enabled` (pre-`GATE_ORDER`, `engine_cli.py:158-170,567-589`) | asymmetric-both (vetoes `P` in uptrend, `C` in downtrend) | Safe **true** (real-fills A/B IS +$583, root cause: 06-26 −$237 wrong-way-short) / **absent Bold** → off | 2026-06-26/live real-fills A/B | Current | Not separately re-audited this pass | Not adjudicated by name in the VERDICTS input — flagged here as a **structural gap**: Bold has zero counter-structure protection on either side while Safe has it both ways. Recommend folding into the fix list as a Bold-arming candidate, not a kill/keep call |

**Dead code, no verdict needed (never armed, never forwarded by `heartbeat_core.py`, so nothing to keep/kill until wired):** `sweep_blocker_enabled` (+ its 4 tuning params, `filters.py:910-930/1313-1334`), `bearish_reversal_bypass` (+`fhh_quality_proximity`/`fhh_above_max_prior_min`, `filters.py:1027-1032,1252-1301` — Rule-9-flagged, requires J ratification per its own docstring), `allow_one_blocker` (+`allow_one_blocker_min_spread_cents`, `filters.py:1016-1017,1054-1062,1351-1377` — bear-only by signature, bull has no equivalent kwarg at all), `vix_soft_mode` (`filters.py:1015,1051-1053` — bear-only demerit-instead-of-hard-block mode). All four are bear-only carve-outs sitting inert in the scoring layer.

**Doc/code drift, UNVERIFIED which is authoritative (not a gate, hardcoded scoring constant):** `vix_hard_cap_scoring` — bull hard cap is `filters.py:805` = 22.0 (reverted from 18 on 06-26), bear equivalent folded into Filter 8 at effectively-off 999.0 (`filters.py:38`). `params.json:79`'s doc claims a lowered-to-18 value and a "different Bold baseline" that doesn't match the code — flagged, not resolved here.

---

## 2. Trigger-class asymmetry — the actual root cause, not the gates

The gates in §1 are downstream. The real asymmetry starts upstream, in what triggers can even exist:

- **Bull fires 4 trigger types** (`level_reclaim`, `ribbon_flip`, `confluence`, `sequence_reclaim`, `filters.py:944-951`). **Bear fires up to 6** (adds `fhh_level_rejection` and `trendline_rejection`, `filters.py:1193-1217`).
- **`trendline_rejection` has no bull twin at all.** `detect_trendline_rejection_bearish` (`filters.py:608-720`) fits a descending-pivot line; grep of the file confirms zero `detect_trendline_reclaim_bullish`. This is why bull can never reach the `TRENDLINE-CHOP-ZONE` filter-relaxation pathway (`filters.py:1219-1250`) — a second-order consequence, not a separate design choice.
- **`fhh_level_rejection` (first-hour-high supplemental check) has no bull twin.** `evaluate_bullish_setup` never reads `ctx.fhh_level` (`filters.py:87` field defined, only bear consumes it, `filters.py:1205-1209`) — no first-hour-low reclaim check exists for bull.
- **Wick-rescue has no bull twin.** `detect_wick_rejection_bearish` (`filters.py:551-605`) promotes a near-miss bearish rejection into a valid `level_rejection` trigger on a strong upper wick — encodes J's 4/29 10:25 entry. No mirror exists for a bullish wick-reclaim; candlestick helpers (`is_hammer`/`is_shooting_star`) exist but are explicitly not wired as triggers (rolled back 2026-05-07).
- **`bearish_reversal_bypass` (countertrend carve-out, the 5/01 11:50 J-anchor pattern) has no bullish twin** — no "BULLISH_REVERSAL" bypass exists to let a countertrend bull reclaim skip its own ribbon/VIX blockers (`filters.py:1252-1301`).
- **Breakout continuation (bull) has ZERO representation, dormant or otherwise.** `detect_level_reclaim` requires a broken level being reclaimed (`low<level AND close>level`), not a fresh breakout through intact resistance — grep for a bull breakout-continuation detector across `backtest/lib/watchers` returns nothing.
- **Breakdown continuation (bear) exists ONLY as an unwired research stub.** `LEVEL_BREAK_FIRST_STRIKE` (`backtest/lib/watchers/level_break_first_strike_watcher.py:1-47`) detects exactly this pattern for bear, but is explicitly WATCH-ONLY — absent from `setup_dispatch.py`'s live 6-detector dispatch list, its own docstring states the live-wiring precondition ("3 live J observations confirmed") was never met.
- **Live evidence, today (2026-07-15):** bear fired only `trendline_rejection` (26/26 occurrences); bull fired `level_reclaim` (80), `confluence` (80), `ribbon_flip` (10) — bear's live trigger diversity really is thinner than bull's, though not literally zero as the task's premise implied. This is a **SPY-price-proxy observation from the live decision ledger, not a backtest** — corrects but doesn't overturn the "bear trigger set is starved" finding.

**Watcher-family (non-core-10-gate) asymmetries, for completeness:**
- `gap_and_go` — symmetric detector, but `params.json:97-98` pins `gap_and_go_side='put'` with a doctrine comment restricting it to bear ("no bull-side scope expansion... Set side=both to also trade gap-up calls"). Currently WATCH-only (not exec-armed) regardless.
- `double_bottom_base_quiet` — structurally bull-only, no side param exists (hardcodes `direction='long'`). Bear mirror `double_top_watcher.py` exists in the repo but its own dispatcher docstring says "DOES NOT CLEAR... NOT wired."
- `vwap_continuation` — both directions live and validated (C +$26.0/77.4%, P +$53.3/75.4%), but carries an **extra** VIX-slope gate on puts only (`j_vwap_cont_put_vix_gate`, `vwap_continuation_watcher.py:40-42,396`) — both armed, bear carries strictly more friction.
- **Controls (proof this isn't a blanket policy):** `vwap_reclaim_failed_break`, `vix_regime_dayside`, and `bollinger_squeeze` are all symmetric, `side='both'`, both directions independently validated positive.

---

## 3. Participation math vs J's model

**J's stated model (2026-07-15):** $2K account, 3-5 contracts at ~$100 premium, a few trades/day, any direction for any validated setup.

**Reality, 11 sessions (2026-07-01 → 2026-07-15, excl. 07-04/05/11/12 holiday/weekend), from `automation/state/fill-funnel-2026-07-*.json` cross-checked against `core-decisions.jsonl` (191 ENTER rows: 113 safe/78 bold, exact match to funnel totals):**

| Account | ENTER-verdicts/day (raw, undeduped) | Broker-attempted/day | Accepted/day | **Filled/day** |
|---|---|---|---|---|
| Safe | 10.27 | 3.09 | 0.36 | **0.64** |
| Bold | 7.09 | 1.27 | 0.18 | **0.18** |

**Combined: 9 total fills over 11 sessions = 0.82/day** vs J's 4-8/day combined target — **roughly a 90% shortfall.** (Caveat: the raw ENTER-verdict counts are per-tick re-evaluations of a persisting signal, not distinct opportunities — the true opportunity count is lower than 10.3/7.1 per day, but this doesn't change the sink ranking below.)

**Top sinks (raw `action` field tally, both accounts, 07-01→07-15):**

| Rank | Sink | Count | Mechanism |
|---|---|---|---|
| 1 | `VETOED_BY_MODELS` | 55 | `heartbeat_core.py:923-926` — 2-free-model veto layer, biggest single killer, Bold-heavy |
| 2 (tie) | `NOT_FLAT` | 34 | `heartbeat_core.py:1286` — no-stacking lockout; mostly correct re-fire noise on already-filled signals (Rule 4 compliant) |
| 2 (tie) | `SKIP_LATE_ENTRY` | 34 | `heartbeat_core.py:912-918` — 15:00 ET ceiling, theta-cliff guard; concentrated 07-13/07-14 Bold afternoons |
| 4 | `RISK_DENY_PDT` | 19 | Rule 7 day-trade cap, concentrated 07-08 (9 safe + 4 bold same-day) |
| 5 | `SKIP_QUALITY_LOCK` | 15 | Safe-only, 07-02 |

**Directional gates from §1 are NOT the primary bottleneck.** Combined, all §1 gates blocked roughly ~500 raw ticks over the period (dominated by `block_elite_bull` at 290 and `require_bearish_fill_bar` at 81) — real, but dwarfed by the 55-count `VETOED_BY_MODELS` free-model veto layer, which isn't a directional gate at all and sits outside this audit's scope. **If the goal is more trades/day, the free-model veto and the time-ceiling/PDT stack are bigger levers than any single directional gate.**

---

## 4. Ranked fix list

### Kill tonight (no provenance, or provenance-and-refuted, no J gate)
- **`block_bull_ribbon_flip`** (`gates.py:279-282`) — KILL upheld by adversarial refutation. Code correctly stays off; leave it (has a passing regression guard, `test_participation_cascade.py:504-520`). **Action item:** fix the doc misattribution at `markdown/doctrine/BULL-DIRECTION-ACTIVATION.md:25` (already spawned as `task_59631bcc`) so a future session doesn't mistake HOLD-status research for a validated-active filter.

### One pre-registered battery — covers every REVALIDATE gate under current SS-B+ATM config
Twelve of the sixteen gates above land in REVALIDATE, and every one shares the same staleness root cause: **validated before 2026-07-09 (SS-B exit shape), 2026-07-09 (min_entry_premium=0.30 floor), or 2026-07-14 (ATM strike arming for Safe ribbon_ride).** Rather than 12 one-off studies, run **one pre-registered battery**, split by account:

**Spec (applies uniformly; per-gate deltas noted only where the mechanism differs):**
- Engine: current production `heartbeat_core.py` → `engine_cli.py` → `gates.py` GATE_ORDER, `use_real_fills=True`.
- Exit shape: SS-B structure-stop (live since 07-09/10), −50%/−50% catastrophe cap (carried forward unchanged, confirmed live).
- Strike tier: **Safe = ATM** via `crypto/lib/strike_selection.py#V15_SAFE_TIERS` (NOT the OTM-2 ladder several prior "revalidations" mistakenly reused — this exact convention error is why `block_elite_bull` (Safe) and `block_bull_1100_1200` need re-running even though both already have a nominally-current-looking prior pass). **Bold = current strike tier per `automation/state/aggressive/params.json`** (verify against its own live value before running — do not assume it matches Safe).
- `min_entry_premium=0.30` floor applied to the replayed cohort.
- Windows: IS through 2026-07-08 (pre-SS-B cutoff for continuity), fresh OOS 2026-07-09 → present (post-SS-B, real fills only) — extend OOS through 2026-07-15 (today) for every gate; several prior "recent" studies (e.g. `block_elite_bull` Safe 07-10) already stop 5 days short of that.
- Ratification bar: OP-16/OP-22 battery — OOS_positive AND WF≥0.70 AND sub_window_stable (≤1 hurt) AND anchor_no_regression AND `evidence_n≥15` (advisory). Auto-ratify on PASS, flip params.json, report for REVOKE (OP-0) — except where a gate is explicitly J-decision-gated (see below).
- Gates in the battery: `block_level_rejection` (Safe), `block_elite_bull` (Safe re-test at ATM, Bold run for the first time ever), `block_bull_1100_1200` (Safe, at ATM not OTM-2), `require_bearish_fill_bar` (Bold), `midday_trendline_gate` (both accounts, split — resolve the 3-way internal contradiction), `block_conf_lvl_rej_midday_afternoon` (confirm-stays-off), `block_conf_lvl_rec_afternoon` (Bold — a validated-to-remove gate that's still armed; this one is closest to a self-evident unblock), `entry_bar_body_pct_min` (Safe — direct causal identity-diff methodology per its own spec, not aggregate diff), `entry_bar_body_pct_min_bull` (Safe, thin-n caveat carries forward), `vix_bear_hard_cap` (Safe), `min_ribbon_momentum_cents` / `max_ribbon_duration_bars` (both accounts, low urgency — currently harmless).
- **J-decision-gated, do NOT auto-ship even on a clean PASS:** `block_bull_morning_agg` (Bold) — `automation/overnight/queue.md:296` explicitly flags reviving this against J's 06-24 "remove entirely" directive; `trendline_requires_ribbon_flip` — reopening this is a genuinely new hypothesis test (see below), not a revalidation of dead code.

### New-trigger work items (the structural gap from §2)
1. **Bull trendline-reclaim detector** — build `detect_trendline_reclaim_bullish` (ascending-pivot mirror of `filters.py:608-720`) so bull can reach a trendline-tied trigger and the `TRENDLINE-CHOP-ZONE` relaxation. Currently zero representation, not even dormant.
2. **Bull first-hour-low (FHL) supplemental check** — mirror of `fhh_level_rejection` (`filters.py:1205-1209`) for bull, reading a new `ctx.fhl_level`.
3. **Bull breakout-continuation detector** — a fresh-resistance-break-and-hold pattern; `detect_level_reclaim` explicitly does not cover this (it requires a prior break, not intact resistance). Zero existing stub, unlike bear's `LEVEL_BREAK_FIRST_STRIKE`.
4. **Wire `LEVEL_BREAK_FIRST_STRIKE` to production** (bear breakdown-continuation) — it exists and is unwired; its own precondition ("3 live J observations confirmed") should be checked before dispatch, not before building.
5. **`structure_veto_enabled` for Bold** — currently Safe-only (§1 row 16); Bold has zero counter-structure protection on either side. Candidate for the same battery, not urgent enough to block tonight's kill/revalidate work.

### Do not touch without J
- `trendline_requires_ribbon_flip` code deletion (refuted — leave in place; it's a real byte-faithful mirror consumed by `orchestrator.py` and 3 parity tests, not dead weight).
- `block_bull_morning_agg` re-arm (J explicitly killed it 06-24).
- `bearish_reversal_bypass` (Rule-9-flagged in its own docstring — "Production heartbeat.md edit requires J ratification").

---

## 5. Process-failure note — honest, no sugar-coating

**The standing rule "re-audit block-filters on engine change" was not executed after either the 2026-07-09 SS-B exit-shape ship or the 2026-07-14 ATM-strike-arming ship.** Evidence: of the 16 gates adjudicated in §1, **12 are REVALIDATE purely because their provenance predates one or both of those changes**, and in at least three cases (`block_elite_bull` Safe, `block_bull_1100_1200`, and the original `entry_bar_body_pct_min` chain) a revalidation WAS run in the intervening weeks but used the **wrong strike-tier convention** (OTM-2/ITM-2 instead of the ATM tier that's actually been live since 07-14) — meaning even the "already revalidated" gates were tested against a config that no longer matches production. Two gates (`entry_bar_body_pct_min` Safe and `require_bearish_fill_bar` Bold) have **explicit unblock recommendations that were queued and never shipped** (`.claude/agent-memory/chef/project_direction_block_audit_synthesis.md:18`; `strategy/candidates/2026-06-26-094331-unblock-require-bearish-fill-bar-bold.md`) — the finding existed, the ship step didn't happen. One gate (`midday_trendline_gate`) has three mutually contradictory studies on record for the same account with no reconciliation. This report's one-battery fix list (§4) is the mechanism to close that gap in a single pass instead of another dated one-off.

---

*Sources: gate census, provenance chain, live-block evidence, adjudication verdicts, and kill-refutation pass all supplied by the audit swarm this session; participation math independently aggregated from `automation/state/fill-funnel-2026-07-{01,02,03,06,07,08,09,10,13,14,15}.json` cross-checked against `automation/state/core-decisions.jsonl`. SPY-direction counterfactuals throughout are price proxies, not option P&L (doctrine C3) — labeled inline wherever used.*

---

## Appendix — 2026-07-15 evening: `VETOED_BY_MODELS` false-veto class root-caused + fixed

Follow-up to §3's #1 sink finding (`VETOED_BY_MODELS`, 55 blocks since 07-01). One specific
false-veto was pulled and root-caused this evening.

### The incident (real, `automation/state/core-decisions.jsonl`)

`ts_et=2026-07-15T14:16:27`, `account=bold`:

```
spy=754.545 ribbon=BULL spread_cents=75.14435908548194 vix=15.78 htf_15m=BULL
verdict=ENTER_BEAR side=P setup=BEARISH_REJECTION_RIDE_THE_RIBBON
bear_score=7 bull_score=8 triggers=["trendline_rejection"]
action=VETOED_BY_MODELS
```

Both free-model lanes (`ollama::qwen3:14b`, twice — coordinator + critic) voted `go=false`.
Lane 1's stated reason, verbatim from the ledger:

> "spread value of 75.14 is implausibly large for SPY options (typical spreads are
> ~$0.10-$0.50), indicating a likely data entry error"

**Root cause (one sentence):** `heartbeat_core._veto_snapshot` rendered the EMA-ribbon
fast-vs-slow gap (`bc['ribbon_now']['spread_cents']`, a value that is ROUTINELY 5–250 on
this engine) as bare `spread={cents}c`, and the free model read that as an option bid-ask
spread quoted in dollars — the trailing "c" was not enough disambiguation — so it vetoed a
real, directionally-correct signal for a units hallucination, not a real risk finding.

**Was the veto costly?** SPY closed the session at 753.63 (`core-decisions.jsonl`,
`ts_et=2026-07-15T15:55:06`) — down from the 754.545 entry snapshot. The blocked
`ENTER_BEAR` was directionally right. `exec` on the vetoed row is `null` (no order was ever
placed, consistent with a veto — this is a price-direction observation, not a claimed
option P&L; doctrine C3 applies, no $ figure is asserted here).

### Fix shipped this session

- `setup/scripts/heartbeat_core.py` — `_veto_snapshot` (L594-L643) now renders
  `ribbon_width_cents=<value> (EMA-ribbon fast-vs-slow gap in CENTS, typical range 5-150c --
  this is NOT an option bid-ask spread)` instead of bare `spread={cents}c`. `_free_model_eval`'s
  `sysmsg` (~L662-L668) carries the same disambiguation as a second, independent line of
  defense.
- `setup/scripts/free_model_audit_heartbeat_veto.py` — the verbatim `_SYSMSG` mirror and the
  degraded-render fallback in `_build_snapshot` updated identically, so the audit harness's
  blind-Sonnet-fallback path (used when counterfactual replay is infeasible) judges against
  the same fixed rubric, not a stale one.
- **Presentation-only, backward compatible:** the payload key
  `bc['ribbon_now']['spread_cents']` and the `spread_cents` field logged to every
  `core-decisions.jsonl` row (`run_account`, L849) are UNCHANGED — only the string rendered
  into the free models' prompt changed. Every existing consumer of the logged decision row,
  including `free_model_audit_heartbeat_veto.collect_items` (reads `spread_cents` straight
  from the ledger), stays compatible.
- Guard: `backtest/tests/test_veto_snapshot_units.py` (new) — asserts the rendered prompt is
  always unit-labeled and never contains the bare `spread=<number>` form, RED-proofed against
  a verbatim reconstruction of the pre-fix rendering (which the same predicate correctly
  fails). `backtest/tests/test_extra_setup_veto_payload.py`'s core-path pin test updated to
  lock the new format (was pinned to the old "byte-identical to pre-2026-07-09-refactor"
  string; that pin is intentionally superseded, not violated).

### Evidence wiring — why no manual grade row was filed

`setup/scripts/free_model_audit.py` + its `heartbeat_veto` adapter
(`free_model_audit_heartbeat_veto.py`) are a fully automated **pull** system:
`collect_items` scans `core-decisions.jsonl` directly for every `free_eval`-evaluated tick,
and `grade_item` grades via counterfactual OPRA replay (or a blind-Sonnet fallback) — there
is no manual "submit one incident" entry point, and OP-33 forbids fabricating a grade row in
a format that was never actually produced by that pipeline.

The 14:16:27 incident is **already present** in `core-decisions.jsonl` with
`free_eval.veto=true` (item_id it will resolve to: `core:bold:2026-07-15T14:16:27`), so the
harness's next due run will pick it up and grade it for real (cadence-gated: last run
`2026-07-14`, cadence 2 days per `automation/state/free-model-audit-state.json`, i.e. due
`2026-07-16` or via `--force`). This appendix is the honest record of the incident and the
fix in the interim — not a substitute for the harness's own grading pass.

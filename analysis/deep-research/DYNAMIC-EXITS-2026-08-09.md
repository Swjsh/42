# Dynamic Exits — build + test (2026-08-09)

Generated 2026-08-09T13:42:36.336016. Runner: `backtest/tools/dynamic_exits_2026_08_09.py`. Pre-reg: `analysis/recommendations/dynamic-exits-prereg-2026-08-09.json` (committed BEFORE the runner existed).

## J's directive

> "ive been demanding dynamic stops and removing the 50% cap for weeks !!! every trade is dynamic, stop, entry, trailing stop, TP, etc."

Verified this session (memory note + fresh greps): never queued, never lessoned, never varied in any prior study including a document specifically about reducing losses. DYNAMIC != WIDER — every candidate below COMPUTES its exit parameter from that trade's own ATR or chart structure at entry, never from a re-picked constant.

## Section 1 — Audit: every exit parameter, fixed vs dynamic

| Parameter | Current value | Classification | What it should adapt to |
|---|---|---|---|
| `premium_stop_pct` | ribbon_ride -0.20 (flag-off fallback) / vwap_continuation -0.06 / vwap_reclaim_failed_break -0.08 / vwap_cont Bold -0.07 | FIXED (per-strategy constant) | trade's own ATR or distance-to-invalidation -- TESTED TONIGHT (DYN-ATR-CAT/DYN-STRUCT-CAT set this AND catastrophe_stop_pct together). CONTROL_HOLDS. |
| `catastrophe_stop_pct` | -0.50 global constant (CATASTROPHE_STOP_PCT), never varied as a COMPUTED value in any prior study | FIXED | trade's own ATR or safety-line distance -- TESTED TONIGHT. CONTROL_HOLDS on the primary population; DYN-ATR-CAT is the mildest loser + only clean G4 (runner-cohort) pass. |
| `tp1_premium_pct` | ribbon_ride 1.0 (+100%, SS-B cell) / vwap_continuation 0.40 / vwap_reclaim_failed_break 0.30 | FIXED | ATR-implied move or distance-to-next-level -- TESTED TONIGHT (DYN-TP-ATR, k=1.0). CONVERGENTLY BAD on both populations (halves the $15,774.05 runner-cohort profit historically; -$10,343.67 with Tuesday harm on real fills). GRAVEYARDED this exact form (k~1.0x ATR). |
| `tp1_qty_fraction` | 0.667 (ribbon_ride SS-B) / 0.8 (vwap arms) | FIXED | NOT TESTED TONIGHT -- not named in the task's BUILD bullet list (stop / catastrophe cap / TP / trailing); flagged as future scope. |
| `trail_pct` | 0.15 (ribbon_ride SS-B) / 0.125 (module default) | FIXED | trade's own ATR -- TESTED TONIGHT (DYN-TRAIL-ATR, k=1.0). CONTROL_HOLDS on the primary population (second-mildest loser) but the ONLY candidate whose real-fill-book positive survives the Tuesday-concentration check. Closest thing to a frontier -- frozen for a forward-clock re-test, not shipped. |
| `profit_lock_arm_pct` | 0.05 flat (arm at +5% favorable) | FIXED | should plausibly scale to volatility too -- NOT TESTED TONIGHT, not named in the task's BUILD bullet list, flagged as future scope. |
| `profit_lock_arm_scope` | 'post_tp1' (today's live behavior) | STRUCTURAL CHOICE between 2 modes, not a magnitude to compute | N/A -- 'full' (pre-TP1 arming) is the graveyard entry that DIED FIVE TIMES (latest: G4 runner cohort -$7,758.85, 22 worse/0 better); correctly never touched by any candidate here (verified by construction). |
| `runner_target_pct` | 99.0 sentinel (never binds -- the runner effectively has no target, rides until trail/structure/time-stop) | FIXED, but already achieves 'unconstrained' via a disable-sentinel rather than a computed value | RECONCILE FLAG: CLAUDE.md doctrine states runner target 2.5x, but the live SHIPPED ribbon_ride cell (strategies.py RIBBON_RIDE) overrides to 99.0 -- doctrine text and shipped code have drifted apart; this predates tonight's build and is a separate, smaller doc-fix, not touched here. Per C30 (unconstrained targets = dead knob), building a genuinely dynamic runner target was judged out of scope tonight. |
| `structure-stop eligibility (stop_mode='structure')` | requires ALL THREE: the strategy's ExitShape declares stop_mode=='structure' AND params.structure_stop_enabled AND a trigger_level resolved at entry | PRECISION CORRECTION to the task's framing: it is NOT that trigger_level is always None for continuation setups -- it is that VWAP_CONTINUATION's and VWAP_RECLAIM_FAILED_BREAK's ExitShape literals in strategies.py NEVER declare stop_mode=='structure' (both default to 'premium'), so resolved_structure is False by construction for those two strategies regardless of trigger_level. Verified by direct code read this session, not assumed from the task brief. | N/A -- this is correctly the live, validated mechanism (v15.3 chart-stop-primary) for ribbon_ride; not a gap to close, a precision note. |
| `time_stop_et` | '15:40' fixed wall-clock | FIXED | could plausibly adapt to theta-decay rate or remaining premium -- NOT TESTED TONIGHT, not named in the task's BUILD bullet list. |
| `pre_tp1_be_floor_arm_pct` | None (inert by default) | FIXED when set | N/A -- currently unused live. |

## Section 2 — Build + test verdict

| Candidate | Axis | Historical auto-ratify | Real-fill Tuesday no-harm | FINAL |
|---|---|:--:|:--:|:--:|
| DYN-ATR-CAT | stop, ATR-scaled | False | True | **PREREG_ONLY** |
| DYN-STRUCT-CAT | stop, safety-line (opposing trendline) | False | True | **PREREG_ONLY** |
| DYN-TP-ATR | TP1, ATR-scaled | False | False | **PREREG_ONLY** |
| DYN-TRAIL-ATR | trail width, ATR-scaled | False | True | **PREREG_ONLY** |
| DYN-ALL | stop+TP1+trail bundled (every axis at once) | False | False | **PREREG_ONLY** |

## Historical population (primary, gated) — 191 ribbon_ride trades, 141 dates, 2025-01-06..2026-07-21

Preflight: {'ok': True, 'n_total': 191, 'n_structure_eligible': 67, 'n_runner_cohort': 35, 'runner_cohort_total': 15774.05}

| Candidate | Control $ | Candidate $ | Δ | G1 | G3 ex-best | G4 runner-cohort | sub-window | drop-best-day | WF | p (raw) |
|---|--:|--:|--:|:--:|:--:|:--:|:--:|:--:|:--:|--:|
| DYN-ATR-CAT | $4,808.75 | $3,992.88 | $-815.87 | False | False | True ($+15,774.05 vs $+15,774.05) | False (2/4) | False | False (wf=-13.075) | 0.65447 |
| DYN-STRUCT-CAT | $4,808.75 | $3,957.78 | $-850.97 | False | False | False ($+15,250.75 vs $+15,774.05) | False (2/4) | False | False (wf=None) | 0.62598 |
| DYN-TP-ATR | $4,808.75 | $3,191.67 | $-1,617.08 | False | False | False ($+7,707.28 vs $+15,774.05) | False (2/4) | False | False (wf=-13.3537) | 0.76491 |
| DYN-TRAIL-ATR | $4,808.75 | $4,080.72 | $-728.03 | False | False | False ($+15,046.02 vs $+15,774.05) | False (2/4) | False | False (wf=None) | 0.95027 |
| DYN-ALL | $4,808.75 | $2,298.44 | $-2,510.31 | False | False | False ($+6,954.49 vs $+15,774.05) | False (1/4) | False | False (wf=None) | 0.81014 |

### Give-back accounting (historical)

| Candidate | Extra captured on beats | n beats | Extra given back | n losses | Net |
|---|--:|--:|--:|--:|--:|
| DYN-ATR-CAT | $+6,089.93 | 17 | $-6,905.80 | 72 | $-815.87 |
| DYN-STRUCT-CAT | $+7,165.72 | 15 | $-8,016.69 | 71 | $-850.97 |
| DYN-TP-ATR | $+8,203.82 | 34 | $-9,820.90 | 42 | $-1,617.08 |
| DYN-TRAIL-ATR | $+618.01 | 7 | $-1,346.04 | 28 | $-728.03 |
| DYN-ALL | $+11,824.79 | 51 | $-14,335.10 | 81 | $-2,510.31 |

### Coverage (how many trades got a genuinely COMPUTED value vs fell back to control)

| Candidate | n | stop computed | TP1 computed | trail computed |
|---|--:|--:|--:|--:|
| DYN-ATR-CAT | 191 | 190 | 0 | 0 |
| DYN-STRUCT-CAT | 191 | 112 | 0 | 0 |
| DYN-TP-ATR | 191 | 0 | 190 | 0 |
| DYN-TRAIL-ATR | 191 | 0 | 0 | 190 |
| DYN-ALL | 191 | 190 | 190 | 190 |

### Disclosure: BH-FDR (alpha=0.10, 5 candidates, REPORTED not gating)

| Candidate | raw p | BH threshold | significant |
|---|--:|--:|:--:|
| DYN-ATR-CAT | 0.65447 | 0.04 | False |
| DYN-STRUCT-CAT | 0.62598 | 0.02 | False |
| DYN-TP-ATR | 0.76491 | 0.06 | False |
| DYN-TRAIL-ATR | 0.95027 | 0.1 | False |
| DYN-ALL | 0.81014 | 0.08 | False |

## Real-fill book (secondary, confirmatory) — 203 repriced positions (18 dropped, no cache), 2026-06-26..2026-08-07

Broker-truth reference (actual live fills, NOT gated): total $+2,109.01, Tuesday 08-04 $+3,624.00.

Repriced comparison (structure_stop_enabled=False parity, one axis changed at a time — control here is NOT broker truth, see disclosures). **Concentration check (OP-33 / fable-too-good discipline) applied BEFORE any positive number is trusted** — delta ex-Tuesday isolates whether a positive aggregate survives removing the single biggest day, exactly like drop-best-day above:

| Candidate | Control-repriced $ | Candidate-repriced $ | Δ | Tuesday Δ | Δ ex-Tuesday | Genuinely + ex-Tue | Days + / total |
|---|--:|--:|--:|--:|--:|:--:|:--:|
| DYN-ATR-CAT | $17,720.24 | $17,949.31 | $+229.07 | $+3,179.52 | $-2,950.45 | False | 9/26 |
| DYN-STRUCT-CAT | $17,720.24 | $18,716.71 | $+996.47 | $+3,226.44 | $-2,229.97 | False | 7/26 |
| DYN-TP-ATR | $17,720.24 | $7,376.57 | $-10,343.67 | $-11,906.42 | $+1,562.75 | True | 7/26 |
| DYN-TRAIL-ATR | $17,720.24 | $23,722.67 | $+6,002.43 | $+4,890.65 | $+1,111.78 | True | 4/26 |
| DYN-ALL | $17,720.24 | $13,332.71 | $-4,387.53 | $-2,493.70 | $-1,893.83 | False | 8/26 |

## Prior-art reconciliation

backtest/autoresearch/dynamic_stop_ab.py + analysis/recommendations/dynamic-stop-ab.json -- THE SAME QUESTION was tried once before (J's 2026-07-07 offline R&D ask), scoped to vwap_continuation ONLY, via the DEPRECATED _dte_expansion_sim (not walk_exit_manager -- predates the 2026-07-09 simulator_real-divergence scar this task explicitly forbids resurrecting), at DTE 0/1/2. VERDICT AT DTE0 (the only DTE relevant to current 0DTE-only live doctrine): 'NO dynamic rule beats static+gates' for BOTH ATM and ITM2 tiers -- ATR/IV cells all lost to static after gates. Only DTE2 (multi-day, not applicable live) saw a structure-based cell (STRUCT_buf0.25) win. This negative DTE0 result was never promoted to a lesson/queue item (consistent with the memory note's grep finding ZERO 'dynamic stop' hits) -- a disclosed, not hidden, prior. THIS STUDY DIFFERS: (a) family=ribbon_ride (the current majority/validated live strategy, not vwap_continuation), (b) harness=walk_exit_manager/plan_exit_actions (the approved production core, not the deprecated sim), (c) DTE0-only by construction (0DTE, no multi-day framing), (d) the safety-line/structure candidate reuses dynamic_stop_ab's OWN winning buffer constant (0.25) rather than re-deriving it, and (e) TP1 and trailing-width dynamism were never tested by the prior study at all (it only varied the stop). A different family + different harness + a genuinely new axis is not a re-litigation of a settled result, but the DTE0 negative prior is disclosed up front as the honest base rate to beat, not silently omitted.

analysis/recommendations/catastrophe-cap-decision-2026-08-08.json tested WIDEN-vs-HOLD the catastrophe cap at a fixed alternative width via a 13-fire shadow ledger (held-to-EOD counterfactual); decision was DO_NOT_WIDEN, cap stays pinned -0.50. This is a DIFFERENT axis (binary widen/hold of a still-CONSTANT cap) from this study's axis (COMPUTING the cap per-trade from ATR/structure, which on any given trade may resolve wider OR narrower than -0.50). Disjoint, not re-litigated.

## Graveyard check (pre-committed, verified by construction — no collision)

- pre_tp1_profit_lock_arm_scope_full: Not touched. Every candidate below inherits CONTROL's profit_lock_arm_scope='post_tp1' unchanged. Verified by construction (the resolver functions never set this key).
- hold_longer: Not touched. time_stop_et unchanged (15:40) in every candidate.
- take_profit_earlier: Not applicable as a category -- DYN-TP-ATR's tp1_premium_pct is computed bidirectionally (can resolve ABOVE or BELOW control's 1.0 depending on that trade's own ATR), not a blanket lower TP.
- level_target_exits: Not touched. No candidate sets a TP at a chart level; DYN-STRUCT-CAT/DYN-ALL use a level-derived value for the STOP side only, which is the ALREADY-LIVE, validated stop_mode='structure' mechanism (v15.3 chart-stop-primary, SS-B), not the dead level-target-TP idea (0/144).
- fixed_stop_width_either_direction: Not touched. No candidate is a single scalar swap; every candidate computes a per-trade value from that trade's own ATR or chart structure. This is the entire point of the study.

## Ship rule outcome

**Nothing shipped.** Every candidate failed G1 (aggregate beats control) on the primary 191-trade historical population — the auto-ratify bar was never in reach, so no gate was softened to force a decision. This is the honest 'nothing cleared, here is the frontier' outcome the task explicitly allows.

**Frozen forward prereg** (next iteration, NOT a re-grade of tonight's data): `analysis/recommendations/dynamic-exits-forward-prereg-2026-08-09.json` — narrows to DYN-TRAIL-ATR (the one candidate with a genuine, non-Tuesday-concentrated positive signal) and a tighter-k re-test of DYN-ATR-CAT/DYN-STRUCT-CAT, evaluated against a forward clock (next n>=20 real fills or a freshly-regenerated historical slice), never against today's already-viewed populations. DYN-TP-ATR (ATR-scaled TP1 near k=1.0) and DYN-ALL (bundling every axis) are explicitly added to the graveyard — convergently bad evidence across both populations.

## Disclosed limitations

- Historical population is 191 ribbon_ride trades / 141 unique dates (2025-01-06..2026-07-21), reused byte-identical from engine-fullhist-replay-2026-07-23.json -- NOT a fresh 391-day regeneration (see prereg's disclosed_span_correction).
- Real-fill-book comparison is REPRICED at structure_stop_enabled=False parity (control vs candidate, one axis at a time) because historical trigger_level is not reliably recoverable from fills-ledger.jsonl alone -- broker-truth P&L (which used live structure-mode stops) is reported separately, never blended into the gated repriced comparison.
- Real-fill-book repricing uses the ribbon_ride CONTROL shape uniformly for ALL positions (the dominant live strategy) even though the ledger also includes vwap_continuation / vwap_reclaim_failed_break fills governed by different registry shapes -- a disclosed simplification. The historical population (100% ribbon_ride) is unaffected.
- ATR is a SIMPLE mean-true-range (not Wilder-smoothed), reused verbatim from dynamic_stop_ab.py's own formula for methodology consistency with that prior study.
- Underlying-to-premium translation uses a FIXED per-tier delta approximation (ATM 0.50 / ITM-2 0.65) -- no per-contract greeks feed in the cache, identical disclosed limitation to dynamic_stop_ab.py.
- Safety-line coverage is necessarily partial (reported per-candidate in coverage_historical / coverage_real_fill_book) -- trades with too few pre-entry swings fall back to CONTROL's own fixed value for that trade, disclosed not hidden.

---
_Source: `backtest/tools/dynamic_exits_2026_08_09.py`. Full per-trade/per-position detail in `DYNAMIC-EXITS-2026-08-09-detail.json`._

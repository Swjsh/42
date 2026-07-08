- 2026-07-08 01:20 ET [overnight-loop] G17 DONE (8c672c0): autonomy_actuator ET/market-hours deduped onto et_clock (C14 verbatim-copy eliminated), parity verified, guard red-proofed.
- 2026-07-08 01:15 ET [overnight-loop] G15 DONE (dd84573): stale vwap_cont docs fixed (were 'DORMANT' while LIVE-armed) + doc/flag drift guard; queue.md consolidated (25 done->Completed); SIP price = $99/mo (Algo Trader Plus) handed to J for D-SIP.
- 2026-07-08 01:05 ET [overnight-loop] G9 DONE (412ec93): sim-live parity ledger shipped. FINDING: 0 reconciled fills across core + 6 fleet arms (filled_avg_price null everywhere) — rig places but has never filled. Now standing-monitored via analysis/parity/. 4 red-proofed tests.
- 2026-07-08 00:58 ET [overnight-loop] G8 DONE (addb959): engine now logs per-entry greeks/IV (delta/gamma/theta/vega/rho+IV) to core-decisions.jsonl — log-only, fail-open (never slows a fill), 6 red-proofed tests. UNVERIFIED: live snapshot URL confirms on first real fill.
- 2026-07-08 00:45 ET [overnight-loop] G7 DONE (d553fe5): armability gate — promote scorecards now disclose min-lot affordability per account (Safe floor <=$2.00/contract, Bold <=$2.78). 9 red-proofed tests, gate PASS.
- 2026-07-08 00:33 ET [overnight-loop] G16 DONE (54ce9b6): et_clock.py now runnable (`python et_clock.py` -> ET + market_hours) + is_market_hours() gate; 2 red-proofed guards, safety gate PASS. Queued G17 (autonomy_actuator ET dedup).
## [2026-07-07 ~22:45 ET] OPUS — Tier-1 gap-audit execution COMPLETE (before-open safety)

> **G1 DONE (commit 55fd164):** adopted manual positions are now CAP-ONLY per D2 -- shape tp1_qty_fraction 0.0 (no TP1 -> no chandelier) + ribbon-flip excluded for strategy 'adopted_manual' + Discord ping on adoption. So a J-manual put can NO LONGER be auto-sold at a TP1 he never chose; only the -50% cap + 15:50 flatten manage it. Guard TestAdoptedShapeCapOnly (3 tests, both directions red-proofed). Curated safety gate green.
> **G2 DONE (verify-only):** the gap-audit assumed the live tick runs under backtest/.venv -- WRONG. run-heartbeat-core.ps1:24-36 launches SYSTEM pythonw with PYTHONPATH=backtest/.venv/Lib/site-packages (L41: venv pythonw re-execs a new console -> window flash). Verified heartbeat_core + exit_actuator + my edits import CLEAN under that faithful env (pandas 2.3.3). Import-dead-at-open retired. FUTURE VERIFICATION NOTE: test under system-python+venv-PYTHONPATH, not bare venv, to be production-faithful.
> **G3 DONE (commit fc8ee27):** today's runners auto-liquidated 15:45 ET (Alpaca 0DTE auto_liquidate; both accounts confirmed FLAT). Safe 747P runner -$13, Bold 750P runner +$125. **DAY TOTAL = +$489 realized** (Safe +$162 / Bold +$327) -- corrects the +$377 (TP1-only) reported all evening. Journal EOD written. Minor flag: a $0.01 SPY 07-08 710P + a $10 BTC round-trip appear ~20:45 ET post-session (canceled/tiny, source unclear) -- flagged for provenance.
> NEXT (Opus, per FABLE gap-audit order): G10 audit-tail recovery, then G5 alert/capture, G8 greeks-capture, G9 parity-ledger, G7 armability-gate.

---

## [2026-07-07] RECENCY-CONFIRMATION (confirm-before-capital gate) — RED-BLOCKED on the freshest 25 trading days (2026-05-27..2026-07-01), real OPRA fills, floor n>=10

> **Signal J wakes to (OP-25).** Weekly recency check (reusable `backtest/autoresearch/recency_check.py`, generalizes the Sunday fresh-revalidation; auto-reads OPRA cache last = 2026-07-01). The CONFIRM-BEFORE-CAPITAL gate: no live flip while an edge is RED; capital scaling waits for CONFIRM.
> - **Live-tier verdicts:** #1 ATM (Safe-2)=YELLOW; #1 ATM (Bold)=YELLOW; #2 ATM=YELLOW; #4 ATM=YELLOW
> - **Books:** Safe2_ATM_1+2+4=RED ($-510.96); Bold_ATM_1+2=YELLOW ($-481.2)
> - **edges_confirmed_on_recent = False** (any RED=True). All live tiers still small-n / not-yet-confirmed on the freshest weeks — full-OOS-2026 base remains the larger-n companion read; HOLD capital scaling until an edge CONFIRMs. RED-BLOCKED: Safe2_ATM_1+2+4 — no live flip on these.
> - Files: `automation/state/recency-confirmation.json`, `backtest/autoresearch/recency_check.py`.

---

## [2026-07-07 ~21:45 ET] FABLE DECISION MEMO — 7 open judgment calls CLOSED (companion to the gap audit)

> **Full memo: `markdown/audits/FABLE-DECISIONS-2026-07-07.md`.** D1 FREEZE new options-entry batteries ~30d (axis exhausted + OOS burned; effort -> fleet/alert/greeks/parity/futures; exceptions: J's-exact-weekly-spec battery + log-analysis). D2 adopted manual positions = CAP-ONLY + flatten + Discord ping (never impose TP1/chandelier on J's trade; guard it). D3 vwap -0.06/0.40 pre-registered REVOKE trigger: realized expectancy < $0 after 15 live fills -> revert (fill-funnel owns the counter). D7 fleet 6-arm profiles pre-designed (2 controls + one-gate-away + 2DTE-forward $10K + scalp-shape + J-mirror), explicitly inside J's arms-are-RISK-PROFILES-not-strategies rule. **J one-word ratifications owed: D4 Safe-2 paper-reset to $2K w/ epoch ledger (rec: yes); D5 min-1 contract for single-exit shapes, min-3 stays for split shapes (his Rule 6); D6 activate G7 EOD-flatten backstop (rec: yes).** Tomorrow-morning watch order included. Nothing left waiting on Fable.

---

## [2026-07-07 ~21:30 ET] FABLE GAP AUDIT — the unknown-unknowns handoff (J at 95% Fable; Opus executes)

> **Full doc: `markdown/audits/FABLE-GAP-AUDIT-2026-07-07.md`** — 15 gaps ranked by trading impact + 3 reframes + execution order. Headlines: (R1) the 2026 OOS window is BURNED (~130 configs read it tonight; forward paper fills = the only virgin holdout; the FLEET is the unused forward-validation farm); (R2) tonight's code meets its first live open tomorrow — G1 adoption-exit-shape is UNSPECIFIED (pin + ping before 09:30), G2 dress-tick under the production interpreter, G3 today's runner exits never verified/journaled; (R3) stop running batteries at J's discretionary edge — build DETECT->ALERT->CAPTURE (the J-call flywheel) instead. Dropped J-directives to build: fleet divergence keystone (G4), alert loop (G5), J's EXACT weekly spec (OTM + underlying-level stop + hold-to-Friday) never actually tested (G6, cache now exists). Cheap compounding instruments: armability gate (G7), live greeks capture (G8), sim-vs-live fill parity ledger (G9), recover the 6 truncated audit findings via resumeFromRunId wf_a6e5356c-0e7 (G10). J-decisions: futures provisioning 5WW73759, Safe-2 equity reset policy (down ~32% in 3wk — sizing doom-loop), paid SIP (~$99/mo, verify).

---

## [2026-07-07 ~21:00 ET] CORRECTION to the evening entry: the "DTE win" is a HOLD, not a shipped edge

> **Verify-don't-claim (OP-33):** the evening entry called DTE "real and validated, +82% OOS, the night's headline." That was OVERCLAIMED — it was the RESEARCH cell (ITM2) without the full OP-22 gate / recency / sizing. Validated on the LIVE ATM Safe-2 cell (vwapcont-dte-atm-ab.json): VERDICT **HOLD** — WF 0.556 (<0.70), loses vs 0DTE in 4/4 most-recent months (2026-03..06), null p=0.065 (concentration in 2025Q4/2026Q1, not regime-robust), AND 2DTE ATM premium 2.33x -> 1.6 lots at the $600 budget < min-3-lot floor (hard Rule-6 blocker at $2K). The DTE *effect* is real (0DTE theta trap is real) but it is NOT a shippable/sizeable edge on the live cell now. Change is STAGED (j_vwap_cont_dte_override + picker patch + guard, in strategy/candidates/2026-07-07-204650-vwapcont-dte-override.md) -> re-opens if a later run re-clears all 6 gates (regime turn / higher equity for 3 lots). Lesson: fable-too-good — scaled confidence with the exciting number instead of suspicion.
> **The night's REAL shipped wins stand:** 75f3a0c vwap exit (+$8.64/tr OOS validated), 35de43f 5 audit fixes, 5d84a5e futures engine (dry-run green, 1 broker-setting from live). Dynamic stops = STATIC-IS-FINE (dynamic-stop-ab.json; burden now on a real greeks feed). J action: provision futures on Tastytrade 5WW73759.

---

## [2026-07-07 EVENING] interactive (J + Gamma) marathon — DTE LEVER FOUND (+82% OOS), 5 audit fixes + vwap exit SHIPPED, edge SHAPE diagnosed

> **Signal J wakes to:** the night's headline is real and validated — **DTE is a monotone edge lever**: same signal 0DTE $36 -> 1DTE $59 -> 2DTE **$66 OOS/tr** (null-crushed, drop-top3 healthy). "Options die to theta" was a **0DTE artifact** (J was right). True 3-4 DTE multi-day-hold test RUNNING (backfill ~40min) — answers whether holding across days pays more or gaps out.
> - **SHIPPED (committed, guarded, revert-able):** `75f3a0c` vwap_continuation exit -0.08/0.30 -> -0.06/0.40 (+$8.64/tr OOS, all OP-22 gates) + `e0160b1` guard-pin fix; `35de43f` 5 AUDIT FIXES (manual-lockout adopted-not-frozen, expired-levels dropped, fill-reconcile poll, funnel false-RED, time_stop dead-knob wired) — each red-proofed, adversarial review OVERALL SHIP, full regression gate green.
> - **LIVE:** J called the 07-07 dump, Gamma executed manual paper puts -> +$377 (Safe 5x747P +$175, Bold 3x750P +$202). Engine generated 18 ENTER_BEAR but NOT_FLAT behind the manual position (the lockout — now fixed).
> - **KILLED (evidence):** ribbon-rejection as a 0DTE entry (6 configs) — RE-OPENED on the DTE axis; confluence (additive/structural/multi-lens all die — adding lenses overfits); "multi-TF=bigger move" REFUTED (predicts SMALLER, corr -0.27); volume-profile 0DTE data-blocked (needs paid SIP).
> - **DIAGNOSED:** J's edge = TREND/REGIME direction, timed at levels, needs DAYS + right DTE (levels=where, regime=why; order-book-mechanical per the literature, not folklore). His winning PUTs were at levels a mechanical engine reads as SUPPORT -> he trades regime, not local level-role.
> - **BUILT:** GENERATIVE-LENS discipline (enumerate market-structure levers before writing "dead") + markdown/trading-knowledge/ base (Greeks/structures, DTE/IV, market-structure) + param_provenance.py (133 params: 23 validated / 93 bare) + level_memory.py perception layer.
> - **QUEUED (evidence-pointed):** (1) true 3-4 DTE multi-day hold [RUNNING]; (2) regime-prior x multi-day options; (3) fleet-divergence (each arm independent + own DTE/exit profile — keystone: build_shared_signal ties all arms to Safe ENTER -> inert when Safe HOLDs); (4) XSP/SPX for multi-day holds (cash-settled, no assignment, 60/40 tax).
> - **REVOKE:** git revert 35de43f / 75f3a0c. Scorecards: multiday-dte-compare / vwapcont-exit-ab-ship-gate / confluence-matrix / ribbon-rejection-{exitgrid,hold,selective,spread}.json.

---

﻿## [2026-07-06 ~10:05 ET] interactive (J + Gamma): full system re-verify + fresh premarket chart cross-check — MCP reconnected, engine GREEN, opening-30-min price action read

> J returned ~30 min post-open to prep for the day. Re-verified everything the 09:52 premarket run flagged, from a second independent source: (1) **Alpaca MCP (both accounts) + TradingView MCP all reconnected** and round-tripped clean this session (`get_clock`/`get_account_info`/`get_all_positions` both accounts, `tv_health_check`) — the 09:52 `MCP_UNRESPONSIVE_REST_FALLBACK` was session-scoped, not a standing outage. Alpaca clock: `is_open=true`, `timestamp=2026-07-06T10:03:34-04:00` (next_open tomorrow — no holiday weirdness). (2) `engine-health.json` cross-checked directly: both heartbeats ticking 1/min, both accounts flat (confirmed via live `get_all_positions`, not just REST), kill-switches armed, level feed 2.8m fresh. Equity matches exactly: Safe $1,425.11 / Bold $1,636.27. (3) Fresh TV chart read confirms the bullish bias 13 min later: ribbon still BULL-stacked (fast 748.55 > pivot 748.36 > slow 748.28). (4) **New since premarket:** SPY spiked to 749.52 in the 09:30-09:35 volume surge, tagging just above the 749.42/749.53 resistance band, then rejected back to the 748.3 pivot/50-SMA area where it's now consolidating — the day's first real test of the key level already happened and faded.
> **Unchanged / still open:** recency-confirmation RED-blocks Safe2_ATM *live-capital* scaling (paper unaffected, per J's 07-01 TRADE-TO-LEARN ruling); macro calendar stale 22 days, Sunday weekly-review silently failing 3+ weeks (flagged for follow-up); overnight Conductor/Drive/ManagerOverseer quiet 4 straight nights, consistent with 07-02 token-saving mode still in effect (no commits or STATUS entries since Fri 07-03 12:01 either way — nothing broke, nothing new shipped over the weekend); `today-bias.json`'s `key_levels.ema_fast/pivot/slow` fields (746.66/745.69/744.47) are stale/mismatched vs the live ribbon — cosmetic, the bias prose + fresh TV read agree with each other, just that structured sub-block lags.
> No code/params changed this session — read-only verification + one live chart pull.

---

## [2026-07-06 09:52 ET] premarket: OK — bullish bias seeded, both accounts flat, ALPACA MCP DOWN (REST fallback used)

> **Known broken:** (1) Alpaca MCP servers (`alpaca`, `alpaca_aggressive`) unresponsive this session — ToolSearch returned no tools after repeated retries. Fell back to direct REST via `.mcp.json` keys for clock/account/positions (confirmed both accounts flat, market open, Safe equity $1425.11, Bold equity $1636.27). Heartbeat should verify MCP connectivity independently before first tick — if still down, it has its own REST fallback per CLAUDE.md tech-stack row. (2) `daytrade_count` field absent from both Alpaca REST account responses — wrote `day_trades_used_5d=0` (permissive default) to both circuit-breaker files. (3) Crypto harness DEGRADED: `v53_setup_dispatch.live` failing (103/104 stages pass) — yellow flag only, not trading-blocking. (4) Macro calendar STALE 22 days (last refresh 2026-06-14, threshold 7) — no confirmed events today, Sunday weekly-review has silently failed for 3+ weeks running.
> Bias: bullish (moderate) — SPY 748.55 pinned between 747.46 support / 749.42 resistance, ribbon BULL tight (17c spread), VIX 16.32 MID (bull-eligible). Both kill-switches re-armed on fresh live equity. Chart wipe/redraw deferred to first heartbeat tick (cost discipline — key-levels.json already current via 5-min intraday refresh).

---

## [2026-07-04T18:31 ET] MCP_AUDIT_YELLOW: Alpaca Safe/Bold healthy, TradingView required relaunch after weekend idle, all operational

---

## [2026-07-02 ~07:53 ET] conductor: OK -- CLOSED THE 4-DAY-OLD OPEN J DECISION cd-2026-06-29-001 (TP1/PROFIT-LOCK REVERT) → KEEP, ZERO PARAMS CHANGE. Adjudicated on evidence, not deferred to J another day; ships nothing to the trading path right before today's first-ever clean money-path proof. No commit (state-only: proposal shelved + queue + lesson).

> **Signal J wakes to (OP-33 verify-don't-claim + close-a-loop > artifact): the standing OPEN decision that has cluttered every STATUS for 4 days is RESOLVED — the 06-28 auto-applied `tp1_qty_fraction 0.8` + `v15_profit_lock_mode fixed` STAY (KEEP), grounded in the actual scorecard + the actual live-code behavior, with zero perturbation before the proof.** After-hours conductor fire, market CLOSED (Thu 07:53 ET, premarket; engine-health **GREEN** — both heartbeats/beacon/watcher-feed/kill-switches/level-feed/gex/dispatch GREEN, both accounts flat, reds:[]; self-check **GREEN**, problems:[] → FUNCTION-first satisfied, no funnel BROKEN; last trading day 07-01 calendar-gated on TODAY's real tape). No `### BROKEN:` flags. Self-audit tail DONE-marked through 07-01T17:33. task_scorer #1 of the 6-way HIGH tie = ADJUDICATE (a genuine loop-CLOSER on 4-day standing debt) — picked it over the FUNCTION-path needle-mover PROMOTER-WRITES-LIVE-KEY *because* it's premarket right before the first-ever clean money-path proof and the right move is to NOT touch the arm/trading surface now (ADJUDICATE ships zero trading-path change; PROMOTER edits the arm-key wiring).
> - **DIAGNOSED before deciding (OP-33, every claim from source):** the proposal (written 06-30 under the OLD propose-only rail) framed the 06-28 change as a "recency-RED CONFIRM-BEFORE-CAPITAL bypass = revert candidate." Read the source: (1) the change came from **pk-2026-06-28-001**, whose scorecard = **CLEARED / eval_bar_cleared=true** (WF 3.566, OOS +$56.86/tr, anchor 1692) → it PASSED the full 4-gate auto-ratify eval; only the *recency* gate was skipped (the bug cb82456 later fixed). (2) **J's own 07-01 TRADE-TO-LEARN grant made recency LIVE-money-ONLY** — these are PAPER accounts, so the "capital bypass" premise is *superseded by J's newer ruling*; the passed eval gate IS the paper bar. (3) `tp1_qty_fraction=0.8` is live-read correctly (`heartbeat_core:1054`, correct key) + doctrine-documented (CLAUDE.md:28, pk-2026-06-28-001). (4) `v15_profit_lock_mode=fixed` is a **DEAD KNOB in live core** — BOTH exit branches force "fixed": L1055 hardcodes it on the primary TRADE-TO-LEARN per-setup path, L1068 fallback reads the **un-prefixed** `profit_lock_mode` (params key is `v15_profit_lock_mode` → absent → default "fixed"). Reverting to "trailing" = **ZERO live effect**.
> - **DECISION = KEEP (shelved the revert), ZERO params change** — validated (scorecard CLEARED) + doctrine-documented (tp1) + behaviorally-inert (profit_lock) + no perturbation before the proof. Proposal `cd-2026-06-29-001` status pending→**shelved** with the full evidence resolution + `resolved_at`. Autonomous-safe: KEEP-status-quo is the null action (changes nothing live); J REVOKE surface = near-inert, trivially re-openable if he prefers revert. Deliberately did NOT do the "shelve=update CLAUDE.md to FIXED" half the proposal offered — CLAUDE.md is rail-4 propose-only → queued CLAUDE-PROFITLOCK-DOCTRINE-RECONCILE instead.
> - **LEARN (4.5):** the dead-knob has a real blind-spot — `v15_profit_lock_mode` PASSES tonight's own just-shipped reconciliation guard (95a603b) because `promote_keeper.py:130` reads it, but that is a READ-TO-MUTATE (writer) reference, not a behavior-path consumer → a behaviorally-dead knob evades the ratchet. Lesson-inbox `2026-07-02-read-to-mutate-consumer-masks-dead-knob.md` + queued fix RECONCILE-GUARD-READ-TO-MUTATE-BLIND-SPOT (LOW). Corollary to C14/L156/L197: a string reference ≠ a behavior dependency.
> - **VALIDATED ($0):** no code/params change → no test run needed; state edits only (proposal JSONL, queue.md, lesson-inbox .md). Confirmed live params UNCHANGED (`tp1_qty_fraction`=0.8, `v15_profit_lock_mode`=fixed both intact). Evidence reads: pk-2026-06-28-001 scorecard verdict=CLEARED; heartbeat_core:1054/1055/1068 quoted; promote_keeper:130 quoted.
> - **REVERT:** state-only, no commit — re-open the proposal by flipping its `status` back to `pending` (or J reacts on Discord). Live behavior untouched either way.
> - **NEXT FIRE picks up:** the Tier-0.1 pipeline-audit HIGH stack still has ready close-a-loops that are the RIGHT post-proof FUNCTION-path work — **PROMOTER-WRITES-LIVE-KEY** (research→arm bridge, audit break #2), **SCHEDULED-OOS-CHECK-FOR-PROMOTE-PROPOSALS** (register the eval-clear schedule), **SINGLE-STRATEGY-REGISTRY-DESIGN** (bigger). NEW LOW residuals queued: CLAUDE-PROFITLOCK-DOCTRINE-RECONCILE (propose-only) + RECONCILE-GUARD-READ-TO-MUTATE-BLIND-SPOT. **The only remaining money-path PROOF is TODAY's (2026-07-02) real tape** — the first engine-originated core fill via the simple-first path (self_check/fill_funnel auto-report it during RTH). Standing direction beyond the money path stays GEX-calendar-gated (premium axis dead L182-184; instrument+bull+range-scalp closed; ~9 of ~60-90 GEX days accrued). J: OPEN decisions now cd-2026-06-28-002 (CLAUDE-INDEX-FOLD L192-198), cd-2026-06-27-001 (G7 EOD-flatten activate) — cd-2026-06-29-001 is now CLOSED.
> - Files: `automation/state/conductor-proposals.jsonl` (cd-2026-06-29-001 pending→shelved + resolution), `automation/overnight/queue.md` (ADJUDICATE→done + 2 follow-ups queued), `strategy/candidates/_lesson-inbox/2026-07-02-read-to-mutate-consumer-masks-dead-knob.md` (new); `conductor-outcomes.jsonl`, this STATUS entry.

---

## [2026-07-02 ~05:56 ET] conductor: OK -- SHIPPED THE GENERAL FORM OF THE DEAD-KNOB CLASS: a BROAD params<->consumer reconciliation ratchet that REDs on ANY ratified-but-unread params key. Measured the real gap: 24 of 114 ratified knobs have ZERO live reader (audit break #7's whole class, one of which -- entry_no_trade_after_et -- caused 10 PLACE_FAIL late ENTER_BEARs on 07-01). Commit 95a603b.

> **Signal J wakes to (OP-33 verify-don't-claim + FUNCTION-adjacent): the C14 dead-knob class is now GUARDED at build time, not audited by hand. A newly-ratified-but-unwired params key can no longer sit silent and mis-steer the money path -- it REDs LOUD.** After-hours conductor fire, market CLOSED (Thu 05:56 ET; engine-health **GREEN**, both accounts flat, reds:[]; self-check **GREEN**, problems:[] -> FUNCTION-first satisfied, no funnel BROKEN; last trading day calendar-gated on 07-02's real tape). task_scorer had 8 HIGH items tied at 6.0 -> picked PARAMS-CONSUMER-RECONCILE-TEST: the last ~5 fires' persistent signal was "trend regressing on small loop-closers, prefer a genuine needle-mover," the 03:55 fire EXPLICITLY named it "the RIGHT general form of tonight's finding," and it's the structural fix for the whole C14 class rather than one knob.
> - **DIAGNOSED before building (OP-33, every number measured):** the EXISTING coverage (`test_params_filters_drift.py` + v25 presence guard) reconciles ONLY the gate family (`block_*`/`*_gate`/`*_min`/`*_hard_cap`/`*_required`) vs the HEARTBEAT PROSE -- its docstring even concludes "no clean NEW hard parity to add," reading as if params<->consumer were fully covered. It is NOT: a broad word-boundary scan of the live consumer surface (code+prompts+installers, excluding the archived `analysis/backtests/*/metadata.json` param snapshots which are copies-not-consumers) found **24 of 114 ratified knobs with ZERO reader** -- exit flags, sizing tiers, entry-window, 5 liquidity thresholds, 4 macro-bias-v2 knobs, 6 session-timing, 4 resilience-harness. Whole-repo cross-check confirmed the only refs are archived snapshots + CHANGELOG (docs) -> genuinely orphaned, not read via a translated name.
> - **SHIPPED (rail-4 CLEAR -- test-only, touches NO params/orders/filters/heartbeat/CLAUDE, arms nothing, ships on green gate):** `backtest/tests/test_params_consumer_reconciliation.py` (4/4). Ratchet: (1) `test_no_new_dead_params_knob` -- dead set MUST be a subset of KNOWN_DEAD; a new unwired key REDs. (2) `test_known_dead_allowlist_shrinks_only` -- a KNOWN_DEAD key that GAINS a consumer must be removed (ratchet can only shrink) -> forces "restore-or-remove each dead key" to actually close. (3) hygiene: no stale allowlist entry. (4) NON-VACUOUS BITE both directions. KNOWN_DEAD documents all 24 with a RESTORE/REMOVE disposition tag.
> - **VALIDATED ($0, verify-now-not-later):** in-process proof BOTH ratchets bite -- injecting a fresh orphan knob REDs test1; feeding a revived `min_disk_free_mb` into the corpus REDs test2. Suite 4/4 (19.8s); siblings test_params_filters_drift + test_validated_setups_enabled 21/21; pre-commit curated safety gate **31 + 5 suites PASS** at 95a603b; verify-committed clean (file in commit, porcelain clean).
> - **LEARN (4.5):** lesson-inbox `2026-07-02-family-scoped-reconcile-guard-masks-other-families.md` -- a reconciliation guard scoped to ONE key family (gates) is easily mistaken for full config<->consumer coverage; its confident "no new parity" docstring HID the 24-knob gap. Corollary to C14/C7: a subset-scoped guard must state its coverage as a fraction of the whole, or a broad guard sits above it.
> - **REVERT:** `git revert 95a603b` removes the guard.
> - **NEXT FIRE picks up:** the follow-up **PARAMS-DEAD-KNOB-DISPOSITION** (MED, now queued) -- drain the 24-key KNOWN_DEAD allowlist by deciding RESTORE-or-REMOVE per knob (the shrinks-only ratchet auto-verifies each close). Other ready HIGH close-a-loops: PROMOTER-WRITES-LIVE-KEY (research->arm bridge), SINGLE-STRATEGY-REGISTRY-DESIGN, ADJUDICATE-CD-2026-06-29-001-TP1-REVERT (bookkeeping). The only remaining money-path PROOF stays 2026-07-02's real tape (first engine-originated core fill via simple-first path; funnel auto-reports). Standing direction beyond the money path stays GEX-calendar-gated (premium axis dead L182-184; instrument+bull+range-scalp closed; ~9 of ~60-90 GEX days accrued). J: OPEN decisions cd-2026-06-29-001 (TP1 revert), cd-2026-06-28-002 (CLAUDE-INDEX-FOLD L192-198), cd-2026-06-27-001 (G7 EOD-flatten activate).
> - Files: `backtest/tests/test_params_consumer_reconciliation.py` (new 4/4, 95a603b); `automation/overnight/queue.md` (item->done + follow-up queued), `strategy/candidates/_lesson-inbox/2026-07-02-family-scoped-reconcile-guard-masks-other-families.md` (new); `conductor-outcomes.jsonl`, this STATUS entry.

---

## [2026-07-02 ~03:55 ET] conductor: OK -- KILLED A MISDIAGNOSED HIGH QUEUE ITEM AT ITS FRAME: PARAMS-TO-KWARGS-CHANDELIER-DEADKNOB would have VIOLATED L156 + RED'd its guard. The "dead-knob to fix" was an INTENTIONAL, lesson-encoded, guard-protected design. Resolved WONT-FIX-BY-DESIGN + strengthened the guard + corrected the misdiagnosis at its source. Commit 0480ced.

> **Signal J wakes to (OP-33 frame-audit + close-a-loop): a HIGH-priority "validation-fidelity bug" was a misdiagnosis — executing it as written would have re-introduced the exact measurement-integrity foot-gun L156 exists to prevent. Caught it BEFORE building, closed the loop, and hardened the guard so the misdiagnosis-applied-as-code cannot land.** After-hours conductor fire, market CLOSED (Thu 03:55 ET; engine-health **GREEN**, both accounts flat, reds:[]; self-check **GREEN**, problems:[]). FUNCTION-first satisfied (no BROKEN funnel; last day calendar-gated on 07-02 tape). No RED/BROKEN; self-audit tail DONE-marked through 07-01T17:33; validator/skill/chef inboxes clear. task_scorer had 6 HIGH items tied at 6.0 — picked the genuine needle-mover (PARAMS-TO-KWARGS-CHANDELIER-DEADKNOB, "sim-accuracy gate class") over a small loop-close, since trend has been regressing on small loops.
> - **DIAGNOSED BEFORE BUILDING (OP-33, every claim evidenced):** the task said `_params_to_kwargs` "silently drops the v15 chandelier keys → every params-path A/B models exits WITHOUT the chandelier → C14 dead-knob, fix the mapping." Read the mapper (orchestrator.py L319-459): it maps premium_stop/tp1/qty/runner/filters/strike-tiers/entry-windows but ZERO chandelier keys — confirmed across the whole function. Then found `test_profit_lock_not_in_baseline.py` graduating **L156**: the drop is INTENTIONAL — the chandelier is regime-conditional (net-negative on the volume-dominant trending IS windows), so mapping it into the baseline would permanently bias EVERY candidate comparison negative. "Fixing" the mapping would VIOLATE L156 and RED its guard.
> - **THE TASK'S PREMISE IS FALSE:** "every A/B verdict suspect" is wrong because the drop is SYMMETRIC across both A/B arms (baseline + candidate both traverse the mapper) → relative verdicts unaffected; only the baseline's absolute-vs-live P&L is conservative, exactly the tradeoff L156 chose. PHASEC RESULTS.md itself: "Does not affect port cells." The mislabel originated in PHASEC caveat 7 ("C14 dead-knob class — flagged for fix") and was transcribed verbatim into the HIGH queue.
> - **SHIPPED (rail-4 CLEAR — guard test + docs; touches NO params/heartbeat/orders/filters/CLAUDE, arms nothing, ships on green tests):** (a) resolved the queue item WONT-FIX-BY-DESIGN with the L156 citation; (b) corrected PHASEC RESULTS.md caveat 7 (the misdiagnosis source); (c) STRENGTHENED the L156 guard — added the REAL production key names (`v15_profit_lock_*`, which the old synthetic un-prefixed `profit_lock_mode` list never exercised = the L197/G16 "test didn't exercise the production surface" vacuousness) + a non-vacuous real-params.json bite `test_real_params_chandelier_keys_dropped` (loads live params.json, asserts its 6 chandelier keys don't leak). Guard 2→3.
> - **VALIDATED ($0, verify-now-not-later):** in-process proof — real mapper leaks [] (green), a simulated leaky "fix" mapper leaks `profit_lock_mode` (the new test would RED); guard 3/3 (0.80s). Live params.json carries 6 chandelier keys (3 real + 3 doc-strings) so the real-data assertion is non-vacuous.
> - **LEARN (4.5):** lesson-inbox `2026-07-02-flagged-for-fix-caveat-was-guarded-intentional-design.md` — a "flagged-for-fix / silently-drops-X" research caveat is a HYPOTHESIS, not a work order; grep the guards + LESSONS for the symbol before queueing/executing a restore. A dead-knob is only dead if NO guard and NO lesson defend its absence. Corollary to L156/L197.
> - **REVERT:** `git revert 0480ced` restores the misleading caveat + weaker guard + reopens the (mis-framed) queue item.
> - **NEXT FIRE picks up:** the Tier-0.1 pipeline-audit HIGH stack still has ready close-a-loops — PARAMS-CONSUMER-RECONCILE-TEST (dead-knob reconciliation, the RIGHT general form of tonight's finding), PROMOTER-WRITES-LIVE-KEY (research→arm bridge), SINGLE-STRATEGY-REGISTRY-DESIGN, ADJUDICATE-CD-2026-06-29-001-TP1-REVERT (bookkeeping close). The only remaining money-path PROOF is 2026-07-02's real tape (first engine-originated core fill via simple-first path; funnel auto-reports). Standing direction beyond the money path stays GEX-calendar-gated (premium axis dead L182-184; instrument+bull+range-scalp closed; ~9 of ~60-90 GEX days accrued). J: OPEN decisions cd-2026-06-29-001 (TP1 revert), cd-2026-06-28-002 (CLAUDE-INDEX-FOLD L192-198), cd-2026-06-27-001 (G7 EOD-flatten activate).
> - Files: `backtest/tests/test_profit_lock_not_in_baseline.py` (guard 2→3), `analysis/j-webull/PHASEC-port/RESULTS.md` (caveat 7 corrected), `automation/overnight/queue.md` (item→done), `strategy/candidates/_lesson-inbox/2026-07-02-flagged-for-fix-caveat-was-guarded-intentional-design.md` (new); `conductor-outcomes.jsonl`, this STATUS entry.

---

## [2026-07-02 ~01:54 ET] conductor: OK -- CLOSED A LIVE APPROVE-BUS INTEGRITY HAZARD: proposal_id cd-2026-06-28-002 was reused on TWO different active proposals, and the actuator resolves a dup id TWO INCOMPATIBLE WAYS in one module -> a J `ship` could approve one row and apply/revert the other. Split the ids + shipped a uniqueness guard. Commit 5e536ca.

> **Signal J wakes to (OP-33 verify-don't-claim + FUNCTION-adjacent): the async approve bus (Discord `ship <id>` / companion wrist Approve) is now UNAMBIGUOUS -- an approval can no longer land on the wrong proposal.** After-hours conductor fire, market CLOSED (Thu 01:54 ET; engine-health **GREEN**, both accounts flat, reds:[]; self-check GREEN, no funnel BROKEN; last trading day 07-01 = 16 ENTER / 4 accepted / 0 fills, still calendar-gated on 07-02's real tape). No RED/BROKEN flags; self-audit tail (07-01T17:33) DONE-marked. task_scorer had 7 HIGH items tied at 6.0 -> picked FIX-CD-2026-06-28-002-ID-COLLISION as the close-a-loop that reduces a KNOWN risk on an order/arm-adjacent surface.
> - **DIAGNOSED before fixing (OP-33, quoted the mechanism):** `conductor-proposals.jsonl` had `cd-2026-06-28-002` on line 24 (BOLD-FLEET per-arm params_patch → accounts.json, `needs_structured_apply` + needs_j_gate) AND line 26 (L192 CLAUDE.md doc-fold, `approved`). Read `autonomy_actuator.py`: `sync_companion_approvals` builds `by_id = {r["proposal_id"]: r ...}` (L155, dict → LAST row wins → doc-fold) while `apply_approved`/`revert` use `next((r ... if id==pid))` (L580/L699, first-match → FIRST row → BOLD-FLEET). Same id, two rows, resolved DIFFERENTLY per code path. **Proof it was actively biting:** line 24 (BOLD-FLEET) carried an `actuator_note` "op[0] find-string not present in CLAUDE.md" dated 2026-07-02T05:30 — but BOLD-FLEET has NO CLAUDE.md op (its ops target accounts.json); the note came from the actuator processing the OTHER -002 (doc-fold's CLAUDE.md op) and mis-attributing it.
> - **SHIPPED (rail-4 CLEAR — approval-bus STATE, zero live-trading behavior change; ships on green tests):** re-id'd the BOLD-FLEET orphan → `cd-2026-06-28-003` (the doc-fold KEEPS `cd-2026-06-28-002` because it is the CANONICAL id-owner in `test_op25_index_reconciliation` baseline comments (5 lines) + 6+ STATUS CLAUDE-INDEX-FOLD refs + J's mental model; BOLD-FLEET is referenced only by title). Deliberately deviated from the queue's literal "re-id the later row" wording — re-id'ing the doc-fold would break MORE references (OP-0 pick-the-obvious-correct). Cleared the mis-attributed actuator_note with an accurate `reid_note`.
> - **GRADUATED TO A GUARD (OP-25, $0):** `backtest/tests/test_proposal_id_uniqueness.py` (4/4) — asserts no two ACTIVE-status rows (`pending`/`approved`/`needs_structured_apply`) share a proposal_id, with a non-vacuous bite (synthetic dup detected) + terminal-re-emission-allowed (a promote_keeper id that already `applied` once is harmless) + a regression pin that the -002 pair is now split.
> - **LEARN (4.5):** lesson-inbox `2026-07-02-same-id-resolved-two-ways-in-one-module.md` — the deeper foot-gun is the actuator's DIVERGENT dup resolution (dict last-wins vs next() first-wins in one module); the guard kills the symptom (dup active id), the owed follow-up (queued LOW `ACTUATOR-RESOLVE-DUP-ID-FAIL-LOUD`) is to route both paths through one `resolve_proposal()` that fails LOUD on a dup. Generalizable: two consumers of one key with different container semantics silently disagree.
> - **VALIDATED ($0, verify-now-not-later):** in-process re-parse — all 32 rows parse, ACTIVE-id collisions == {}, -002→doc-fold(approved) / -003→BOLD-FLEET(needs_structured_apply) cleanly split; reconciliation + actuator + new guard suites **37/37 PASS**; commit 5e536ca contains EXACTLY the 2 intended files (verify-committed clean). Metric: net improving, 0 regressions, trend **improving**.
> - **REVERT:** `git revert 5e536ca` restores the collided id + removes the guard.
> - **NEXT FIRE picks up:** approve bus is unambiguous + guarded. The owed defense-in-depth is `ACTUATOR-RESOLVE-DUP-ID-FAIL-LOUD` (LOW). The Tier-0.1 pipeline-audit HIGH stack still has ready close-a-loops (PARAMS-CONSUMER-RECONCILE-TEST, PARAMS-TO-KWARGS-CHANDELIER-DEADKNOB, PROMOTER-WRITES-LIVE-KEY). **The only remaining money-path PROOF is 2026-07-02's real tape** — the first engine-originated core fill via the simple-first path (funnel auto-reports it). Standing direction beyond the money path stays GEX-calendar-gated (premium axis dead L182-184; instrument+bull+range-scalp closed; ~9 of ~60-90 GEX days accrued). J: OPEN decisions cd-2026-06-29-001 (TP1 revert), cd-2026-06-28-002 (CLAUDE-INDEX-FOLD L192-198, now uniquely the doc-fold), cd-2026-06-27-001 (G7 EOD-flatten activate).
> - Files: `automation/state/conductor-proposals.jsonl` (re-id + note fix), `backtest/tests/test_proposal_id_uniqueness.py` (new 4/4) — both 5e536ca; `strategy/candidates/_lesson-inbox/2026-07-02-same-id-resolved-two-ways-in-one-module.md`, `conductor-outcomes.jsonl`, `queue.md`, this STATUS entry.

---

## [2026-07-02 ~00:02 ET] conductor: OK -- FUNCTION-FIRST: RETIRED THE PERSISTENT FALSE-BROKEN on the fill-funnel. self_check was RED on 2026-07-01's IMMUTABLE pre-fix history; a retired-bracket/oto-ladder rejection is provably NOT a live fault -> frame-corrected to DEGRADED. self_check verified live BROKEN -> DEGRADED. Commit 1e3a6ab.

> **Signal J wakes to (OP-33 verify-don't-claim + FUNCTION FIRST): the priority-1 fill-funnel BROKEN was a false-RED on stale pre-fix data, not a money-path fault -- and I proved it in the code before touching the frame.** After-hours conductor fire, market CLOSED (Wed 23:48 ET; engine-health **GREEN**, both accounts flat, reds:[]). `self-check-last.json` verdict was **BROKEN** (Stage-1 priority-1 FUNCTION signal): core:safe+bold each 5 ENTER / 5 attempted / 0 broker-accepted + ENTER-after-15:00.
> - **DIAGNOSED (OP-33, did NOT trust the 20:15 STATUS "stale artifact" claim):** re-read today's live core-decisions -- all 10 ENTER rows are 15:51-15:55 ET (RTH ran BEFORE b0d6ca0 committed ~19:30), and every rejection's `exec.broker` carries `bracket_err` + `oto_err` + `simple_err` (`_error`="bracket, oto, and simple all rejected"). Then VERIFIED the shipped code: FIX1 15:00 ceiling (SKIP_LATE_ENTRY L649/L921) + FIX2 simple-first (`_place_simple_entry` L693, called direct L1037) ARE in the code. So the funnel BROKEN was stale pre-fix history -- but it will stay RED until tomorrow's tape and MASK any genuinely-new fault (L189/L197 recurrence) + mis-steer every conductor fire's priority-1 pick.
> - **THE FRAME (why bracket/oto is a hard tell):** the shipped `_place_simple_entry` posts ONE plain marketable limit -- NO order_class -- so it can only ever emit `simple_err`/`_error`, NEVER `bracket_err`/`oto_err`. A rejection carrying those is DEFINITIVELY from the retired bracket->oto->simple ladder = pre-fix. The code invariant is guarded build-side (`test_money_path_2026_07_01`: AST `test_no_place_bracket_call_left_in_either_live_path` + behavioral `test_execute_first_and_only_order_call_is_simple_marketable`), so a regression re-adding the ladder REDs at BUILD before it ever reaches the funnel -> two-layer, no masking.
> - **SHIPPED (rail-4 PAPER trading-path monitor-correctness -- guard + revert + REVOKE):** `fill_funnel.py` `_acct_funnel` tracks `retired_ladder_fails`; `_evaluate` classifies an all-retired-ladder placement day as DEGRADED **"PLACEMENT PRE-FIX ARTIFACT"** (still surfaced for J's visibility) instead of RED **"PLACEMENT BROKEN"**. A day with ANY simple-only rejection (no bracket/oto) STILL fires RED. self_check re-run LIVE: **BROKEN -> DEGRADED** (6 problems, none `_problem_is_broken`).
> - **GUARD (frame-corrected SAME commit, L197 applied):** `test_fill_funnel_guard.py` -- `test_real_day_core_placement_broken_red` -> `test_real_day_core_is_pre_fix_artifact_degraded` (today's fixture now asserts pre-fix DEGRADED, `retired_ladder_fails==attempted`, no "PLACEMENT BROKEN"); `test_self_check_flags_placement_broken_as_broken` -> `test_self_check_pre_fix_artifact_not_broken`. Added the NON-VACUOUS BITE: `test_genuine_simple_only_rejection_is_placement_broken_red` + `test_self_check_genuine_placement_fault_is_broken` (a real simple-first reject -> RED/BROKEN). A revert to the old frame REDs these.
> - **VALIDATED ($0):** funnel+money-path suites 50/50; self_check live verdict DEGRADED (was BROKEN 9m prior); graduated_guards confirmed 0 references to fill_funnel (change can't affect it); pre-commit curated safety gate **31 + 5 suites PASS** at 1e3a6ab; verify-committed CLEAN (both files absent from porcelain). Metric: net improving, 0 regressions.
> - **LEARN (4.5):** no new L## -- this is L197 APPLIED (frame-fix the guard in the same commit; don't treat a pre-existing guard as ground truth) + the L189 mask-anti-pattern (a persistently-RED monitor masks new faults), both already encoded. Compound, not accumulate.
> - **REVERT:** `git revert 1e3a6ab` restores the old (false-RED) frame + guard.
> - **NEXT FIRE picks up:** self_check is DEGRADED (honest -- today had pre-fix late-enters + retired-ladder rejects, no live fault); tomorrow's simple-first code with the 15:00 ceiling should produce a clean GREEN (no ladder, no post-ceiling ENTER). **The ONLY remaining money-path proof is 2026-07-02's real tape** -- the first engine-originated core fill via the simple-first path (funnel auto-reports it). Standing direction beyond the money path stays GEX-calendar-gated (premium axis dead L182-184; instrument+bull+range-scalp closed; ~9 of ~60-90 GEX days accrued). J: OPEN decisions cd-2026-06-29-001 (TP1 revert), cd-2026-06-28-002 (CLAUDE-INDEX-FOLD L192-198), cd-2026-06-27-001 (G7 EOD-flatten activate).
> - Files: `setup/scripts/fill_funnel.py` (retired_ladder_fails + pre-fix classification + docstring), `backtest/tests/test_fill_funnel_guard.py` (frame-corrected 2 + 2 new bite tests) -- all 1e3a6ab; `conductor-outcomes.jsonl`, `queue.md`, this STATUS entry.

---

## [2026-07-02 ~00:50 ET] REVOKE-report: vwap_continuation now exit-managed by its VALIDATED cell (stop -8% / TP1 +30%), not ribbon_ride's WR-22% lotto shape. Commit 5ff20b4.

> **Shipped (rail-4 paper autonomy, xp-2026-07-02-vwapcont-exit-parity):** `_SETUP_EXIT_OVERRIDES` omitted vwap_continuation, so an armed fill's exit_manager ran strategies.ribbon_ride's shape (−20% stop / TP1 +150% sell 80%: WR 22.1%, top5-day 47.2%, J-anchor capture −97.2). Now it trades the OP-16 winner cell (stop −0.08 / tp1 0.30: OOS +$66.83/tr, WF 1.688, 6/6 quarters, anchor +44.52). Evidence: `analysis/recommendations/vwapcont-exit-parity.json`. Guards RED on regression (real strategies module wired — the old by_name→None mask is gone); 90/90 green + boot `skipped (not RTH)`. **UNVERIFIED until a real vwap_continuation fill exercises the exit_manager.** Revert: `git revert 5ff20b4`.

---

## [2026-07-01 ~20:15 ET] conductor: OK -- FUNCTION-FIRST: VERIFIED tonight's money-path fix (entry funnel) is real, THEN CLOSED THE EXIT HALF -- the v15.3 PRIMARY exit was SILENTLY DEAD (ribbon-flip-back never fired) + the guard that should have caught it was VACUOUS. Commit f76ac48 (guard) + concurrent-fire 4e71618 (prod).

> **Signal J wakes to (OP-33 verify-don't-claim + FUNCTION FIRST): the engine can now (a) place a fillable order AND (b) actually run its v15.3 chart-stop-PRIMARY exit tomorrow -- both halves of the money path verified, not claimed.** After-hours conductor fire, market CLOSED (Wed 20:15 ET; engine-health **GREEN**, both accounts flat, reds:[]). The live self_check verdict was **BROKEN** (Stage-1 priority-1 FUNCTION signal): today's core:safe+bold had 5 ENTER / 0 broker-accepted + 5 ENTER-after-15:00-ceiling. **DIAGNOSED (OP-33, not trusted the STATUS claim):** those are TODAY's PRE-fix decisions (RTH trading ran before b0d6ca0 committed ~19:30) -> stale-day artifact, not a live code fault. VERIFIED the money-path fix is genuinely shipped: FIX1 ceiling enforced at decision (L635) + placement (L906); FIX2 simple-first (`_place_simple_entry` mirrors the fleet primitive that PROVED filled today); wrapper arms BOTH `GAMMA_CORE_ARMED=1`+`GAMMA_CORE_MANAGES_EXITS=1`; end-to-end guarded (`test_money_path_2026_07_01.py` 35/35 incl. `test_execute_first_and_only_order_call_is_simple_marketable`). Entry funnel = closed-pending-tomorrow's-tape.
> - **THE PICK (the EXIT half of FUNCTION, task_scorer HIGH tied 6.0 -- G14-EXIT-RIBBON-FLIPBACK-WIRE):** the natural sequel -- we made entries fillable tonight; the first fill tomorrow needs its exits correct. Audit #6 said the v15.3 PRIMARY invalidation (ribbon-flip-back) has "no live consumer (`ribbon_flip_back_fn=None`)".
> - **OP-33 FINDING -- the queue claim was STALE but a REAL, WORSE bug sat underneath:** the wiring EXISTS (`_ribbon_flip_fn` L564 + `_manage_exits` passes `flip_fn` L586), so "fn=None" was already fixed. BUT `_ribbon_flip_fn` compared `ribbon_stack == ("BULLISH"/"BEARISH")` while the producer (`backtest/lib/ribbon.py` L102-104) ONLY emits `"BULL"/"BEAR"/"MIXED"/"WARMUP"/"UNKNOWN"` -> the comparison could NEVER match -> **the v15.3 chart-stop-PRIMARY exit silently never fired on ANY live position** (only the -50% catastrophe cap / target / time stops ran). A C14 string-mismatch dead-knob. Verified `manage_tick` (fleet/exit_actuator.py L121) calls the fn with `st.side`="P"/"C" -> invoked exactly as designed; the ONLY defect was the literal.
> - **HIDDEN BY A VACUOUS GUARD (the L197/G16 class):** `test_g14_ribbon_flip_fn_direction` RE-IMPLEMENTED the buggy logic INLINE (asserting the wrong `"BULLISH"` literals) instead of importing the real fn -> it green-lit a dead exit. Exactly L197 (a guard baking in the frame you later need to correct) + the G13/G16 "the test mocked the thing it should exercise" hole.
> - **SHIPPED (rail-4 PAPER trading-path fix -- guard + revert + REVOKE):** prod fix `_ribbon_flip_fn` `"BULLISH"/"BEARISH"` -> `"BULL"/"BEAR"` landed in **concurrent-fire commit 4e71618** (a parallel gamma-drive "arm 3 setups" fire independently converged on the identical fix, byte-identical comment -- same model/context -- but LEFT the vacuous guard, violating L197). MY commit **f76ac48** closed that hole: rewrote the guard to **import the REAL `heartbeat_core._ribbon_flip_fn`**, assert against the producer's ACTUAL literals, pin a producer-alphabet contract (REDs if ribbon.py renames its tokens), add MIXED/UNKNOWN/WARMUP hold cases + a BITE that the retired `"BULLISH"`/`"BEARISH"` literals are dead. Anchor 5/04 721P +$730 (ribbon stayed BEAR -> no premature flip exit) preserved. The guard now PROTECTS the prod fix -> a revert to `"BULLISH"` REDs.
> - **VALIDATED ($0, verify-now-not-later):** in-process behavioral check of the fixed fn vs real literals PASS (`f('BULL')('SPY','P') is True`, `f('BULLISH')...is False`); G14 guard 1/1; money-path 35/35; exit/funnel/trade-to-learn 45/45; **full graduated_guards 105 passed / 1 skipped**; pre-commit curated safety gate **31 + 5 suites PASS** at f76ac48.
> - **LEARN (4.5):** the concurrent fire's 4e71618 fixed prod but left the vacuous guard = a fresh instance of L197 (frame-fix the guard IN THE SAME COMMIT). Not a new L## -- L197 already encodes it; this fire is L197 APPLIED. Compound, not accumulate.
> - **REVERT PATH:** `git revert f76ac48` restores the prior (vacuous) guard; prod behavior lives in 4e71618 (validated-correct, so revert is not indicated -- REVOKE is the surface, not rollback).
> - **NEXT FIRE picks up:** both money-path halves are code-verified + guarded; the ONLY remaining proof is tomorrow's real tape (self_check/fill_funnel auto-report the first engine-originated core fill + that the v15.3 ribbon-flip-back exit fires on a real reversal). NOTE: a concurrent Gamma fire committed 5+ commits during this fire (e03aca5..67fd8ab) -- expect parallel work; STATUS.md saw a mid-fire external modification. Standing direction beyond the money path stays GEX-calendar-gated (premium axis dead L182-184; instrument+bull+range-scalp all closed; ~9 of ~60-90 GEX days accrued). J: OPEN decisions cd-2026-06-29-001 (TP1 revert), cd-2026-06-28-002 (CLAUDE-INDEX-FOLD L192-198), cd-2026-06-27-001 (G7 EOD-flatten activate).
> - Files: `setup/scripts/heartbeat_core.py` (`_ribbon_flip_fn` literal, via concurrent 4e71618), `backtest/tests/test_graduated_guards.py` (non-vacuous G14 guard, f76ac48); `automation/overnight/queue.md`, `conductor-outcomes.jsonl`, this STATUS entry.

---

## [2026-07-01 ~19:30 ET] interactive (J + Gamma): FULL PIPELINE AUDIT -> J RATIFIED 4 DOCTRINE CHANGES -> MONEY-PATH FIX BURST SHIPPED (5 commits, ~92 new guards)

> **Signal J wakes to (OP-33): the engine can now actually place a fillable order tomorrow, and the fill funnel will prove it either way.** J commissioned a full swarm->kitchen->winners->engine->Alpaca audit ("not functional, not trading, crashing"). 7-agent recon found every research->engine handoff broken — full report `markdown/audits/PIPELINE-AUDIT-2026-07-01.md`. J then ratified: (1) FULL PAPER AUTONOMY (rail-4 rewritten — paper trading-path edits ship w/ guard+revert+REVOKE); (2) TRADE-TO-LEARN on paper; (3) CONSOLIDATE HARD; (4) success bar = daily paper trading + honest digest.
> - **Money path (b0d6ca0):** 15:00 entry ceiling now ENFORCED core+fleet (today's 10 late ENTERs -> PLACE_FAIL class is dead); placement goes straight to marketable simple limit (bracket/OTO 422 ladder removed); GATE_KEYS forwards the ratified elite-bull VIX bands; **vwap_continuation ARMED on Safe-2 paper** (extra_setup_exec_armed, ATM qty3, WP-5 override now honored — J's #1 edge, n=153 +$38.3/tr scorecard).
> - **Crash-loops (652bed9):** kitchen stage5 argv poison pill FIXED (daemon survived 158s + completed the poison task exit_code=0, was dying in 1-7s x10 today); fresh stage5 scorecard regenerated (was 2026-05-16-stale); promoter freshness guard; watcher_grader now grades all 584 obs (KeyError x3 days fixed); wrapper exit codes propagate.
> - **Truth instruments (commit 3):** fill_funnel.py per-day funnel (ENTER->attempted->accepted->filled->exited) wired into self_check (BROKEN on ENTER>0/accepted=0) + gamma_glance; EOD quant section now code-generated (today's journal regenerated: 16 ENTERs incl. 4 fleet fills w/ order IDs — replaces the fabricated "ENTER signals: 0"); loop-state ticks_today lie fixed.
> - **Autonomy re-aim (commit 4):** conductor Stage-1 = FUNCTION FIRST (fill-funnel drives the pick); outcome metric now records enters/accepted/fills per fire and trend weights FUNCTION; task_scorer depends-annotation + expense-penalty bugs fixed — J's buried HIGH engine items now top the ready list (9 trading-path HIGH items).
> - **Consolidate-hard (commit 5):** rank_contenders SKIP_UNCHANGED (no more restamping frozen data); kitchen_reviewer requires numeric scorecard evidence (hallucinated "$25000" auto-promotes dead); 8 dead grind/funnel tasks DISABLED (registry reconciled, 58 active rows); crypto drift spam cooldown + PS5.1 -NoNewline fix.
> - **FIRST ENGINE ROUND TRIPS EVER (today 11:22-11:34 ET):** 4 fleet arms placed marketable ENTER_BULL orders, filled, exit-managed to flat (fix #15 PROVEN on the fleet path). Core accounts still 0 post-fix fills — that is tomorrow's UNVERIFIED item; the funnel auto-reports it.
> - **UNVERIFIED until 2026-07-02 open:** engine-originated core-account fill via simple-first path; SKIP_LATE_ENTRY rows on any post-15:00 signal; armed vwap_continuation routing end-to-end on real tape; FUNCTION-FIRST steering the next conductor fire. Gamma_Conductor + Gamma_AutoApply re-enabled after the burst.
> - J: OPEN decisions now queued as HIGH items (ADJUDICATE-CD-2026-06-29-001-TP1-REVERT, FIX-CD-2026-06-28-002-ID-COLLISION, G7 EOD-flatten) — the loop can now pick them.

---

## [2026-07-01 ~17:50 ET] conductor: OK -- CLOSED A RECURRING SELF-AUDIT NOISE HOLE AT ITS FRAME (the 06-29 L-lesson recurred = a missing guardrail): tonight's un-actioned self-audit batch (9 gaps) had **5 of 9 = SCAFFOLD** the 06-29 `_is_real_gap` filter never anticipated. Hardened the filter + graduated the guard + DONE-marked the batch. Commit aab30bb.

> **Signal J wakes to (OP-25) -- the proactive gap-finder organ was flagging its own reasoning-scaffold as "gaps," crowding real gaps out of the [:12] budget (the exact 06-29 crowding-out failure, recurring). Fixed at the producer + guarded so it can't regress; the batch's 4 substantive items are all already-tracked, so no new actionable gap tonight.** After-hours conductor fire, market CLOSED (Wed 17:50 ET; engine-health verdict **GREEN** -- both heartbeats/beacon/watcher-feed/kill-switches/level-feed/gex/dispatch GREEN, both accounts flat, gex-archive healthy 9 sessions). No `### BROKEN:` flags (reds:[]). All 4 author inboxes clear (skill correction-queue 3/3 processed). task_scorer top-3 all MED multi-day / LOW rail-4 doc-folds -> the priority-2 pick (un-actioned self-audit batch) beat them.
> - **THE PICK (priority-2 self-audit gap > the MED multi-day queue):** the `2026-07-01T17:33:35` batch of 9 gaps was NOT DONE-marked. Triaged each (OP-33 skepticism, not hand-wave "noise"): 5 are SCAFFOLD -- "Question for reviewer" (3 words, passed the <3-word gate) + four "Perspective N flags/zeroes/warns/enumerates ..." cross-reference lead-ins (the SYNTHESIS describing perspectives, not stating gaps). The 4 substantive items all overlap tracked/just-fixed work (slippage=range-scalp closed + SKIP_LIQUIDITY; data-feed health=engine-health beacon; lesson-inbox-quarantine-risks-Rule-9=a misconception, conductor never applies lessons to params; volatility-adaptive sizing=SAFE-VIX-CONDITIONAL-SIZING MED queue).
> - **SHIPPED (engine-benefit observability code, rail-4 CLEAR -- self_audit.py is the gap-finder organ, touches NO params/doctrine-rules/orders/heartbeat/filters/CLAUDE, places NO order, arms NOTHING -> ships on green gate):** added "question for reviewer"/"question for the reviewer" to `_SCAFFOLD_PREFIXES` + a `_PERSPECTIVE_REF_RE` (`^perspective\s*\d`) lead-in reject to `_is_real_gap`. Verified in-process ($0): 5 scaffold now rejected, 5 substantive kept (incl. a mid-sentence "per-perspective backtest validation" survivor proving no over-rejection). The narrow-nbsp+CRLF in the real flagged text normalizes to "perspective5" -> still caught.
> - **GRADUATED TO A GUARD (OP-25, $0):** `test_self_audit_extract.py` 41->47 -- +5 scaffold cases (this batch's exact 5) + 1 non-over-rejection survivor. The load-bearing crowding-out regression test already covers the [:12]-budget mechanism.
> - **LEARN (4.5):** no new L## -- this is the SAME L-lesson the 06-29 `_is_real_gap` filter encoded (self-audit scaffold crowds real gaps), now with two more scaffold classes it didn't anticipate. Extending an existing guard, not a new foot-gun (compound, not accumulate).
> - **VALIDATED ($0, verify-now-not-later):** in-process scaffold/substantive check PASS; guard 47/47 (0.10s); pre-commit curated safety gate **31 + 5 suites PASS** at aab30bb; verify-committed clean (all 3 files absent from porcelain). Metric: net +25, 0 regressions, $2.48/drained, trend **regressing** (recent fires close small correctness loops -> low per-fire net; not a break, but next fire should prefer a genuine needle-mover if one is unblocked).
> - **NEXT FIRE picks up:** self-audit batches now DONE-marked through 07-01; the gap-finder organ won't re-flag "Perspective N"/"Question for reviewer" scaffold. Standing direction unchanged: NO armable edge tonight -- premium axis dead (L182-184), instrument rung closed (04adc35), range-scalp DIES_ON_SLIPPAGE on full history (c2bfe39), bull frontier FAILS_WALK_FORWARD on full history / EDGE-gated (6250b15), GEX class rung CALENDAR-gated (~9 of ~60-90 days accrued, free CBOE banker healthy). The high-value genre remains engine-correctness close-a-loops + foot-gun guards until GEX fills OR a genuinely-new needle-mover is unblocked. Two LOW hygiene items still open (rail-3): LESSON-INBOX-ORPHAN-DOTDONE + LEVELS-UPSTREAM-DEDUP-SOURCE. J: OPEN decisions cd-2026-06-29-001 (revert vs keep+doc the 06-28 live params change), cd-2026-06-28-002 (CLAUDE-INDEX-FOLD, carries L192-198), cd-2026-06-27-001 (G7 EOD-flatten activate).
> - Files: `setup/scripts/self_audit.py` (+_PERSPECTIVE_REF_RE +2 scaffold prefixes), `backtest/tests/test_self_audit_extract.py` (41->47), `analysis/self-audit/new-gaps-flagged.md` (batch DONE-marked) -- all aab30bb; `conductor-outcomes.jsonl`, this STATUS entry.

---

## [2026-07-01 ~07:52 ET] conductor: OK -- DRAINED THE LAST ACTIVE LESSON-INBOX ITEM, CLOSED THE LEARN LOOP ON TONIGHT'S OWN FRAME-AUDIT (close-a-loop > artifact): the 04:02 range-scalp + 05:57 bull fires PROVED the "25-day OPRA wall" was a hardcoded-CSV misread over a 533-day master that already existed, and both dropped/referenced the foot-gun into `_lesson-inbox/2026-07-01-hardcoded-window-csv-masks-available-data.md` -- but the learn loop's final encode step (prose into permanent doctrine) had not run. Encoded it as **L198** in LESSONS-LEARNED.md. Commit a78c0f2.

> **Signal J wakes to (OP-25) -- the learn loop closes on tonight's own foot-gun; L198 cites the two already-shipped+guarded wide-window probes (test_range_scalp_widewindow 7/7 + test_bull_unblock_structural_widewindow 9/9), so this is pure encoding (compound, not accumulate). Lesson-inbox is now CLEAR (0 active .md).** After-hours conductor fire, market CLOSED (Wed 07:52 ET; engine-health verdict **GREEN** -- both heartbeats/beacon/watcher-feed/kill-switches/level-feed/gex/dispatch all GREEN, both accounts flat, gex-archive healthy 8 sessions). No `### BROKEN:` flags (reds:[] in engine-health). Self-audit gaps ALL DONE-marked/noise (5 batches: 06-26 x2 DONE, 06-27 DONE, 06-28 DONE, 06-29 100%-noise DONE). task_scorer top-3 all MED multi-day (EOD-PHASE-2.x / MORNING-BULL J-gated / SAFE-VIX) -> rail-3 excludes; LOW items are rail-4 CLAUDE-index doc-folds.
> - **THE PICK (priority-4 author-inbox beats the MED multi-day queue):** the lesson-inbox had **1 ACTIVE (non-.DONE) item** dated 2026-07-01, and LESSONS-LEARNED.md topped out at L197 with it NOT encoded -> a genuine open LEARN loop (gamma.md step 6). The 05:57 fire's "already encoded 3h earlier" referred to the item being CAPTURED (inbox .md), not encoded to doctrine -- the still-`.md` suffix confirmed the encode step was owed. Closing it is a loop-closer, not a new artifact.
> - **NOTE (tool reality, OP-33):** no Agent/Task tool exposed this session -> could NOT fan out `lesson-author`. Did the mechanical encoding directly (read item -> append L## -> baseline the reconciliation guard -> rename inbox -> commit), the conductor's documented fallback. The CONDUCTOR-vs-lesson-author boundary HELD: appended L## prose to LESSONS-LEARNED.md (engine-benefit authoring, NOT rail-4) but did NOT edit the CLAUDE.md OP-25 index (rail-4 -> tracked in KNOWN_UNINDEXED_BASELINE +198).
> - **SHIPPED (engine-benefit doc authoring, rail-4 CLEAR -- LESSONS-LEARNED.md + a test baseline; touches NO params/doctrine-rules/orders/heartbeat/filters/CLAUDE, places NO order, arms NOTHING -> ships on green gate):** **L198** (a hardcoded recent-window data file + a stale comment can fake a "data-blocked" wall over data you already have; re-MEASURE the data span from source before inheriting a data-coverage claim, especially a *shared* wall cited across threads. C14/C4/C7 + L61 mirror-image). Cites exact files/tests/numbers (n 8->155 range-scalp DIES_ON_SLIPPAGE; n 8->82 bull FAILS_WALK_FORWARD; the retired 25-day CSV vs the 533-day master) + the two existing guards that enforce it.
> - **GUARD INTERACTION (caught + honored, not bypassed):** the pre-commit `test_op25_index_reconciliation::test_no_new_unindexed_lessons_beyond_baseline` would RED (L198 defined but not in the CLAUDE.md OP-25 index). Its documented escape hatch is `KNOWN_UNINDEXED_BASELINE` (where L192-197 already sit pending the same batch). Added 198 with the C14/C4/C7 fold target noted -> the ratchet trims it when cd-2026-06-28-002 applies the CLAUDE.md fold. Honest rail-4-deferred fold, NOT a --no-verify bypass.
> - **LEARN (4.5):** no new L## -- "the learn loop's final encode step had not run for tonight's frame-audit" is the normal author-inbox cadence (lesson-author/conductor runs after the fire that drops the item), not a new foot-gun. Loop closed > artifact added.
> - **VALIDATED ($0, verify-now-not-later):** L198 defined (grep 1/1); reconciliation guard 9/9 (0.06s); full pre-commit curated safety gate **31 + 5 suites PASS** at a78c0f2; verify-committed clean (all 3 intentional files absent from porcelain). Metric: net +25, 0 regressions, $2.50/drained, trend **regressing** (recent fires close small foot-gun loops -> low per-fire net; not a break, but next fire should prefer a genuine needle-mover if one is unblocked).
> - **NEXT FIRE picks up:** lesson-inbox is now CLEAR (0 active .md; glob-clean). The OP-25 index fold for L192-198 is the rail-4 batch cd-2026-06-28-002 awaiting J (one interactive CLAUDE.md edit drains all). Standing direction stays GEX-calendar-gated: premium axis dead (L182-184), instrument rung closed (04adc35), range-scalp DIES_ON_SLIPPAGE on full history (c2bfe39), bull frontier EDGE-gated / FAILS_WALK_FORWARD on full history (6250b15), GEX class rung CALENDAR-gated (~8 of ~60-90 days accrued, free CBOE banker healthy). **The honest state is NO armable edge tonight; no lever remains where more data would help.** The high-value genre remains engine-correctness close-a-loops + foot-gun guards until GEX fills OR a genuinely-new needle-mover is unblocked. Two LOW hygiene items still open (rail-3): LESSON-INBOX-ORPHAN-DOTDONE (the stray untracked `2026-06-27-persistently-red-audit-masks-new-orphans.md.DONE`, seen again this fire) + LEVELS-UPSTREAM-DEDUP-SOURCE. J: OPEN decisions cd-2026-06-29-001 (revert vs keep+doc the 06-28 live params change), cd-2026-06-28-002 (CLAUDE-INDEX-FOLD, carries L192-198), cd-2026-06-27-001 (G7 EOD-flatten activate).
> - Files: `markdown/doctrine/LESSONS-LEARNED.md` (+L198), `backtest/tests/test_op25_index_reconciliation.py` (baseline +198), `_lesson-inbox/2026-07-01-hardcoded-window-csv-masks-available-data.md.DONE` (renamed) -- all a78c0f2; `conductor-outcomes.jsonl`, `queue.md`, this STATUS entry.

---

## [2026-07-01 ~05:57 ET] conductor: OK -- ACTED ON THE 04:02 FIRE'S EXPLICIT CARRY-FORWARD: re-ran the LAST open bull-unblock lever over the FULL 533-day OPRA history (the "25-day OPRA wall" was the SAME false-data-blocked frame the range-scalp fire proved false 3h earlier). Got the DECISIVE full-history verdict the 25-day window couldn't: **FAILS_WALK_FORWARD_SIGN_FLIP** -- the structural bull-unblock is NOT a real edge, it was a 2026-only OOS tail. Commit 6250b15.

> **Signal J wakes to (OP-33d frame-audit + close-a-loop) -- the 04:02 fire proved the range-scalp "data-blocked" wall was a hardcoded-25-day-CSV misread and EXPLICITLY named the carry-forward: "the bull-frontier '25-day OPRA wall' (BULL-UNBLOCK-REPLAY-PROBE) was the SAME misread -- re-run those probes over the FULL 370-day OPRA history before accepting 'bull data-gated.'" This fire did exactly that on the one bull lever whose verdict could genuinely FLIP with more data, and closed it for the RIGHT (data-rich) reason.** After-hours conductor fire, market CLOSED (Wed 05:57 ET; engine-health **GREEN** -- both heartbeats/beacon/watcher-feed/kill-switches/level-feed/gex/dispatch GREEN, both accounts flat). No `### BROKEN:` flags (grep 0). All self-audit gaps DONE/noise. task_scorer top-3 all MED multi-day (rail-3 excluded); LOW items are rail-4 CLAUDE-index doc-folds -> the honest pick was the named needle-mover.
> - **THE PICK (the #1 project thread + the 04:02 carry-forward > the MED queue):** the rig has never filled an ENTER_BULL in 2544 decisions. Of the 3 bull-unblock levers, SLICE-1 (elite) was decisively net-NEGATIVE (-$241, KEEP) and SLICE-3 (sequence_reclaim) is structurally coupled-off -- widening those only re-confirms. ONLY the STRUCTURAL lever (min_triggers_bull 2->1) was blocked purely by INCONCLUSIVE n=8 (+$76 GROSS), i.e. the exact "n<10 data-blocked" frame the range-scalp fire proved false -> the single lever whose verdict could FLIP with more data.
> - **DIAGNOSED before building (OP-33):** confirmed the full master exists (`spy_5m_2025-01-01_2026-06-18.csv` + VIX, 533d; OPRA real-fills 370 0DTE days via data-coverage.json) -- the SAME masters range_scalp_widewindow used. The 25-day bull probes hardcode `spy_5m_2026-05-19_2026-06-30.csv` -- the identical hardcoded-recent-CSV pattern. Smoke (Q1-2025, 15s) already showed the added cohort net -$194 (opposite of the 25-day +$76) -> the 25-day positive was a slice artifact.
> - **SHIPPED (engine-benefit research + guard, rail-4 CLEAR -- new probe + guard + result JSON; touches NO params/orders/filters/heartbeat-PROMPT/CLAUDE, places NO order, arms NOTHING, PROPOSES NOTHING since not-proposable -> ships on green tests, no A/B):** `bull_unblock_structural_widewindow_probe.py` runs the SAME min_triggers 2-vs-1 A/B (block_elite_bull held FIXED at prod True to isolate the structural lever) via the REAL engine (`run_backtest`, use_real_fills=True) over 2025-01-02..2026-06-18, splitting the added-bull cohort IS(2025)/OOS(2026), REUSING `_bull_cfg`/`_key`/`_date`/`ANCHOR_DATES` + probe_stats. RESULT (real OPRA fills, 533 days, 2m2s): BASE(min=2) n=243/+$3811, UNBL(min=1) n=323/+$4154 -> added bull cohort **n=82, pooled net +$607.58** BUT **IS-2025 net -$299.70 (exp -$5.55) / OOS-2026 net +$907.28 (exp +$32.4)** -> signs FLIP + FRAGILE_TO_SLIPPAGE (breakeven 0.0123c << 5c) + 215% day-concentrated. **VERDICT = FAILS_WALK_FORWARD_SIGN_FLIP.** The 25-day +$76 was purely a slice of the 2026-only OOS tail; the 2-trigger requirement correctly starves losers IN-SAMPLE. Result JSON `analysis/recommendations/bull-unblock-structural-widewindow-2026-07-01.json`.
> - **GRADUATED TO A GUARD (OP-25, $0):** `backtest/tests/test_bull_unblock_structural_widewindow.py` (9/9, siblings 30/30) -- pins the committed golden finding (verdict FAILS_WALK_FORWARD, pooled n>=10, IS<0 & OOS>0 sign-flip, slippage-fragile, top3>150%), the full ladder + precedence, a **non-vacuous bite** (fixing the 3 genuine defects -> UNBLOCK_ADDS_EDGE_PROPOSE, so the reject is real not hardcoded), + the **frame-audit anti-regression** (probe MUST use the full master: window>365d, files exist, NOT the retired 25-day CSV) so the false "n<10 data-blocked" conclusion cannot silently return.
> - **LEARN (4.5):** no new L## -- this is the SAME frame-audit anti-pattern already encoded 3h earlier (lesson-inbox `2026-07-01-hardcoded-window-csv-masks-available-data.md`: "'data-blocked' is a testable statement, never a standing assumption, and never a *shared* wall cited by other threads without one fresh measurement"). This fire is that lesson APPLIED to the exact "shared wall" the lesson warned about. Loop closed > artifact added.
> - **VALIDATED ($0, verify-now-not-later):** smoke Q1-2025 (15s) confirmed mechanics + sign; full run 82 added / 533 days in 2m2s (backtest .venv reaper-exempt); guard 9/9 + siblings 30/30 (0.95s); curated safety gate **31 + 5 suites PASS** at 6250b15; verify-committed clean (all 3 files absent from porcelain).
> - **NEXT FIRE picks up:** the bull-unblock thread is now CLOSED for the RIGHT reason -- bull is **EDGE-gated (walk-forward failure on full history), NOT data-gated.** The "25-day OPRA wall" is retired as a false frame for BOTH range-scalp AND bull (same hardcoded-CSV misread). No lever remains where more data would help. Standing direction stays on the GEX 'class' rung (calendar-gated, ~8/60-90 days accrued; premium axis dead L182-184; instrument rung closed; range-scalp DIES_ON_SLIPPAGE; bull EDGE-gated) -- the honest state is NO armable edge tonight; the high-value genre remains engine-correctness close-a-loops + foot-gun guards until GEX fills OR a genuinely-new needle-mover is unblocked. Two LOW hygiene items still open (rail-3): LESSON-INBOX-ORPHAN-DOTDONE + LEVELS-UPSTREAM-DEDUP-SOURCE. J: OPEN decisions cd-2026-06-29-001 (revert vs keep+doc the 06-28 live params change), cd-2026-06-28-002 (CLAUDE-INDEX-FOLD, carries L192-197), cd-2026-06-27-001 (G7 EOD-flatten activate).
> - Files: `backtest/autoresearch/bull_unblock_structural_widewindow_probe.py` (new), `backtest/tests/test_bull_unblock_structural_widewindow.py` (new, 9/9), `analysis/recommendations/bull-unblock-structural-widewindow-2026-07-01.json` (new) -- all 6250b15; `conductor-outcomes.jsonl`, `queue.md`, this STATUS entry.

---


- [2026-07-02 05:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T11:57:01.727977+00:00) | fail streak: 27 consecutive fires | stage v02_source_parity pass rate dropped to 64.58% in last 24h (31/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 43.75% in last 24h (21/48) | v02 source parity drift in 35.18% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 05:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 06:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T12:27:01.923376+00:00) | fail streak: 28 consecutive fires | stage v02_source_parity pass rate dropped to 62.5% in last 24h (30/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 41.67% in last 24h (20/48) | v02 source parity drift in 36.4% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 06:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 06:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T12:57:01.789250+00:00) | fail streak: 29 consecutive fires | stage v02_source_parity pass rate dropped to 60.42% in last 24h (29/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 39.58% in last 24h (19/48) | v02 source parity drift in 38.45% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 06:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 07:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T13:27:02.065371+00:00) | fail streak: 30 consecutive fires | stage v02_source_parity pass rate dropped to 58.33% in last 24h (28/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 37.5% in last 24h (18/48) | v02 source parity drift in 40.5% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 07:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 07:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T13:57:02.009400+00:00) | fail streak: 31 consecutive fires | stage v02_source_parity pass rate dropped to 58.33% in last 24h (28/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 35.42% in last 24h (17/48) | v02 source parity drift in 42.48% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 07:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 08:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T14:27:01.843803+00:00) | fail streak: 32 consecutive fires | stage v02_source_parity pass rate dropped to 58.33% in last 24h (28/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 33.33% in last 24h (16/48) | v02 source parity drift in 42.48% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 08:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 08:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T14:57:02.010742+00:00) | fail streak: 33 consecutive fires | stage v02_source_parity pass rate dropped to 58.33% in last 24h (28/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 31.25% in last 24h (15/48) | v02 source parity drift in 42.57% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 08:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 09:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T15:27:02.306773+00:00) | fail streak: 34 consecutive fires | stage v02_source_parity pass rate dropped to 60.42% in last 24h (29/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 29.17% in last 24h (14/48) | v02 source parity drift in 41.4% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 09:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 09:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T15:57:02.200596+00:00) | fail streak: 35 consecutive fires | stage v02_source_parity pass rate dropped to 62.5% in last 24h (30/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 27.08% in last 24h (13/48) | v02 source parity drift in 39.36% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 09:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 10:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T16:27:02.217307+00:00) | fail streak: 36 consecutive fires | stage v02_source_parity pass rate dropped to 64.58% in last 24h (31/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 25.0% in last 24h (12/48) | v02 source parity drift in 37.32% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 10:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 10:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T16:57:02.599113+00:00) | fail streak: 37 consecutive fires | stage v02_source_parity pass rate dropped to 66.67% in last 24h (32/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 22.92% in last 24h (11/48) | v02 source parity drift in 35.42% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 10:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 11:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T17:27:02.145522+00:00) | fail streak: 38 consecutive fires | stage v02_source_parity pass rate dropped to 66.67% in last 24h (32/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 20.83% in last 24h (10/48) | v02 source parity drift in 34.99% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 11:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

## Kitchen
Kitchen: alive, queue 61 pending, last cook 0 min ago, today $0.00, model=ollama::qwen3:14b

- [2026-07-02 11:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T17:57:02.061643+00:00) | fail streak: 39 consecutive fires | stage v02_source_parity pass rate dropped to 66.67% in last 24h (32/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 18.75% in last 24h (9/48) | v02 source parity drift in 34.99% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 11:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 12:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T18:27:02.023835+00:00) | fail streak: 40 consecutive fires | stage v02_source_parity pass rate dropped to 66.67% in last 24h (32/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 16.67% in last 24h (8/48) | v02 source parity drift in 34.99% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 12:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 12:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T18:57:02.118323+00:00) | fail streak: 41 consecutive fires | stage v02_source_parity pass rate dropped to 66.67% in last 24h (32/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 14.58% in last 24h (7/48) | v02 source parity drift in 34.99% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 12:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 13:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T19:27:02.332688+00:00) | fail streak: 42 consecutive fires | stage v02_source_parity pass rate dropped to 66.67% in last 24h (32/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 12.5% in last 24h (6/48) | v02 source parity drift in 34.99% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 13:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 13:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T19:57:02.269461+00:00) | fail streak: 43 consecutive fires | stage v02_source_parity pass rate dropped to 66.67% in last 24h (32/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 10.42% in last 24h (5/48) | v02 source parity drift in 34.99% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 13:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

### INFO: eod-analytics eod-summary used free-tier model (free-tier-primary)
- ts: 2026-07-02T20:00:21+00:00
- task: eod-summary
- date_et: 2026-07-02
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

- [2026-07-02 14:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T20:27:03.461389+00:00) | fail streak: 44 consecutive fires | stage v02_source_parity pass rate dropped to 66.67% in last 24h (32/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 8.33% in last 24h (4/48) | v02 source parity drift in 34.99% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 14:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

### INFO: eod-analytics analyst used free-tier model (free-tier-primary)
- ts: 2026-07-02T20:45:43+00:00
- task: analyst
- date_et: 2026-07-02
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

- [2026-07-02 14:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T20:57:03.142930+00:00) | fail streak: 45 consecutive fires | stage v02_source_parity pass rate dropped to 66.67% in last 24h (32/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 6.25% in last 24h (3/48) | v02 source parity drift in 34.89% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 14:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 21:00:01] gym-session (2026-07-02) → **RED** :: see `automation\state\gym-scorecard-2026-07-02.json`
- [2026-07-02 15:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T21:27:03.006225+00:00) | fail streak: 46 consecutive fires | stage v02_source_parity pass rate dropped to 66.67% in last 24h (32/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 4.17% in last 24h (2/48) | v02 source parity drift in 35.08% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 15:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

### INFO: eod-analytics manager used free-tier model (free-tier-primary)
- ts: 2026-07-02T21:30:29+00:00
- task: manager
- date_et: 2026-07-02
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

- [2026-07-02 15:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T21:57:03.199521+00:00) | fail streak: 47 consecutive fires | stage v02_source_parity pass rate dropped to 66.67% in last 24h (32/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 2.08% in last 24h (1/48) | v02 source parity drift in 34.99% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 15:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 16:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T22:27:03.169897+00:00) | fail streak: 48 consecutive fires | stage v02_source_parity pass rate dropped to 68.75% in last 24h (33/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) | v02 source parity drift in 33.09% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 16:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 16:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T22:57:02.958297+00:00) | fail streak: 49 consecutive fires | stage v02_source_parity pass rate dropped to 70.83% in last 24h (34/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) | v02 source parity drift in 31.0% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 16:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 17:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T23:27:03.055347+00:00) | fail streak: 50 consecutive fires | stage v02_source_parity pass rate dropped to 72.92% in last 24h (35/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 17:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 17:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T23:57:02.989629+00:00) | fail streak: 51 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 17:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 18:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T00:27:02.989104+00:00) | fail streak: 52 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 18:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 18:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T00:57:03.190964+00:00) | fail streak: 53 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 18:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 19:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T01:27:03.129819+00:00) | fail streak: 54 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 19:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 19:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T01:57:03.032623+00:00) | fail streak: 55 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 19:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 20:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T02:27:03.369429+00:00) | fail streak: 56 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 20:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 20:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T02:57:02.896009+00:00) | fail streak: 57 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 20:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 21:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T03:27:02.921837+00:00) | fail streak: 58 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 21:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

### WARN: spend-summary threshold breach
- ts: 2026-07-03T03:30:35+00:00
- date_et: 2026-07-02
- total: $261.95 (threshold $30.00)
- claude: $261.90  minimax: $0.04
- claude_sessions: 23

- [2026-07-02 21:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T03:57:02.728141+00:00) | fail streak: 59 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 21:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 22:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T04:27:02.340980+00:00) | fail streak: 60 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 22:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 22:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T04:57:01.736981+00:00) | fail streak: 61 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 22:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 23:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T05:27:01.766732+00:00) | fail streak: 62 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 23:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 23:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T05:57:01.757797+00:00) | fail streak: 63 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 23:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-03 00:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T06:27:01.681140+00:00) | fail streak: 64 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 00:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 00:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T06:57:01.660258+00:00) | fail streak: 65 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 00:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 01:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T07:27:01.698743+00:00) | fail streak: 66 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 01:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 01:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T07:57:01.870943+00:00) | fail streak: 67 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 01:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 02:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T08:27:01.759105+00:00) | fail streak: 68 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 02:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 02:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T08:57:01.659763+00:00) | fail streak: 69 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 02:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 03:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T09:27:01.643077+00:00) | fail streak: 70 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 03:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 03:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T09:57:01.643815+00:00) | fail streak: 71 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 03:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

[2026-07-03 04:00:01] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-07-03.md

- [2026-07-03 04:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T10:27:01.706981+00:00) | fail streak: 72 consecutive fires | stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 04:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 04:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T10:57:01.642006+00:00) | fail streak: 73 consecutive fires | stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 04:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 05:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T11:27:01.657842+00:00) | fail streak: 74 consecutive fires | stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 05:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 05:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T11:57:01.659899+00:00) | fail streak: 75 consecutive fires | stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 05:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 06:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T12:27:01.628211+00:00) | fail streak: 76 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 06:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

### BROKEN: premarket 2026-07-03
- PREMARKET SILENT FAILURE: claude exit=0 but today-bias.falsifiable_predictions is empty (0) -- the premarket LLM produced no predictions (silent failure).


- [2026-07-03 06:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T12:57:01.672325+00:00) | fail streak: 77 consecutive fires | stage v02_source_parity pass rate dropped to 85.42% in last 24h (41/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 06:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 07:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T13:27:01.730560+00:00) | fail streak: 78 consecutive fires | stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 07:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 07:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T13:57:01.727552+00:00) | fail streak: 79 consecutive fires | stage v02_source_parity pass rate dropped to 89.58% in last 24h (43/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 07:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

### BROKEN: self-check 2026-07-03T10:09:56
- engine-health RED: reds=['watcher_feed: PRODUCER DARK: newest bar 2026-07-02 != today 2026-07-03 -- feed not writing during RTH']

- [2026-07-03 08:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T14:27:01.906149+00:00) | fail streak: 80 consecutive fires | stage v02_source_parity pass rate dropped to 89.58% in last 24h (43/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 08:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 08:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T14:57:01.989363+00:00) | fail streak: 81 consecutive fires | stage v02_source_parity pass rate dropped to 89.58% in last 24h (43/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 08:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 09:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T15:27:02.012017+00:00) | fail streak: 82 consecutive fires | stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 09:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 09:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T15:57:01.708656+00:00) | fail streak: 83 consecutive fires | stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 09:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 10:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T16:27:01.801662+00:00) | fail streak: 84 consecutive fires | stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 10:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 10:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T16:57:03.220784+00:00) | fail streak: 85 consecutive fires | stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 10:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 11:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T17:27:02.985713+00:00) | fail streak: 86 consecutive fires | stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 11:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 11:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T17:57:03.128805+00:00) | fail streak: 87 consecutive fires | stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 11:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 12:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T18:27:02.935352+00:00) | fail streak: 88 consecutive fires | stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 12:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 12:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T18:57:03.519232+00:00) | fail streak: 89 consecutive fires | stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 12:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 13:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T19:27:02.932974+00:00) | fail streak: 90 consecutive fires | stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 13:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

### BROKEN: self-check 2026-07-03T23:05:07
- DRESS-REHEARSAL STALE (RED): last rehearsal '2026-07-02T20:45:01' is >24h old on a weekday evening -- Gamma_DressRehearsal likely not firing.

- [2026-07-04 03:05:13] gym-session (2026-07-03) → **RED** :: see `automation\state\gym-scorecard-2026-07-03.json`
### INFO: eod-analytics analyst used free-tier model (free-tier-primary)
- ts: 2026-07-04T03:05:31+00:00
- task: analyst
- date_et: 2026-07-03
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

### INFO: eod-analytics manager used free-tier model (free-tier-primary)
- ts: 2026-07-04T03:05:54+00:00
- task: manager
- date_et: 2026-07-03
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

---

## Known broken
[2026-07-07T18:30:26-04:00] MCP_AUDIT_RED: TradingView MCP bridge wedged (CDP listening but health_check failing after relaunch attempt). Alpaca accounts recovered (Safe+Bold healthy, auth errors from 07-06 cleared).

[2026-07-06T13:45:15Z] MCP_AUDIT_RED: Alpaca API auth failing (401 Unauthorized) on both Safe and Bold accounts

[2026-07-03T23:06:30-04:00] MCP_AUDIT_YELLOW: All systems healthy; TradingView CDP required relaunch

- [2026-07-03 21:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T03:27:03.867952+00:00) | fail streak: 91 consecutive fires | stage v02_source_parity pass rate dropped to 90.91% in last 24h (30/33) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/33) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 21:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

### WARN: spend-summary threshold breach
- ts: 2026-07-04T03:30:29+00:00
- date_et: 2026-07-03
- total: $67.49 (threshold $30.00)
- claude: $67.46  minimax: $0.03
- claude_sessions: 6

- [2026-07-03 21:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T03:57:03.751642+00:00) | fail streak: 92 consecutive fires | stage v02_source_parity pass rate dropped to 90.91% in last 24h (30/33) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/33) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 21:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 22:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T04:27:03.762857+00:00) | fail streak: 93 consecutive fires | stage v02_source_parity pass rate dropped to 90.91% in last 24h (30/33) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/33) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 22:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 22:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T04:57:03.800537+00:00) | fail streak: 94 consecutive fires | stage v02_source_parity pass rate dropped to 90.91% in last 24h (30/33) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/33) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 22:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 23:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T05:27:03.777193+00:00) | fail streak: 95 consecutive fires | stage v02_source_parity pass rate dropped to 90.91% in last 24h (30/33) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/33) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 23:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

[2026-07-04 08:49:35] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-07-04.md

- [2026-07-04 08:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T14:57:03.512409+00:00) | fail streak: 96 consecutive fires | stage v01_closed_bar.live pass rate dropped to 93.33% in last 24h (14/15) | stage v02_source_parity pass rate dropped to 86.67% in last 24h (13/15) | stage v03_indicators.live pass rate dropped to 93.33% in last 24h (14/15) | stage v04_candlesticks.live pass rate dropped to 93.33% in last 24h (14/15) | stage v05_levels.live pass rate dropped to 93.33% in last 24h (14/15) | stage v06_trendlines.live pass rate dropped to 93.33% in last 24h (14/15) | stage v07_volume.live pass rate dropped to 93.33% in last 24h (14/15) | stage v08_ribbon.live pass rate dropped to 93.33% in last 24h (14/15) | stage v09_regime.live pass rate dropped to 93.33% in last 24h (14/15) | stage v10_divergence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v11_breakout.live pass rate dropped to 93.33% in last 24h (14/15) | stage v12_multi_timeframe.live pass rate dropped to 93.33% in last 24h (14/15) | stage v14_sweep.live pass rate dropped to 93.33% in last 24h (14/15) | stage v15_three_source_parity.live pass rate dropped to 93.33% in last 24h (14/15) | stage v46_market_structure.live pass rate dropped to 93.33% in last 24h (14/15) | stage v50_confluence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v51_structure_veto_gate.live pass rate dropped to 93.33% in last 24h (14/15) | stage v52_trendline_break.live pass rate dropped to 93.33% in last 24h (14/15) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/15) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 08:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 09:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T15:27:03.536698+00:00) | fail streak: 97 consecutive fires | stage v01_closed_bar.live pass rate dropped to 93.33% in last 24h (14/15) | stage v02_source_parity pass rate dropped to 86.67% in last 24h (13/15) | stage v03_indicators.live pass rate dropped to 93.33% in last 24h (14/15) | stage v04_candlesticks.live pass rate dropped to 93.33% in last 24h (14/15) | stage v05_levels.live pass rate dropped to 93.33% in last 24h (14/15) | stage v06_trendlines.live pass rate dropped to 93.33% in last 24h (14/15) | stage v07_volume.live pass rate dropped to 93.33% in last 24h (14/15) | stage v08_ribbon.live pass rate dropped to 93.33% in last 24h (14/15) | stage v09_regime.live pass rate dropped to 93.33% in last 24h (14/15) | stage v10_divergence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v11_breakout.live pass rate dropped to 93.33% in last 24h (14/15) | stage v12_multi_timeframe.live pass rate dropped to 93.33% in last 24h (14/15) | stage v14_sweep.live pass rate dropped to 93.33% in last 24h (14/15) | stage v15_three_source_parity.live pass rate dropped to 93.33% in last 24h (14/15) | stage v46_market_structure.live pass rate dropped to 93.33% in last 24h (14/15) | stage v50_confluence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v51_structure_veto_gate.live pass rate dropped to 93.33% in last 24h (14/15) | stage v52_trendline_break.live pass rate dropped to 93.33% in last 24h (14/15) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/15) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 09:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 09:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T15:57:03.864239+00:00) | fail streak: 98 consecutive fires | stage v01_closed_bar.live pass rate dropped to 93.33% in last 24h (14/15) | stage v02_source_parity pass rate dropped to 80.0% in last 24h (12/15) | stage v03_indicators.live pass rate dropped to 93.33% in last 24h (14/15) | stage v04_candlesticks.live pass rate dropped to 93.33% in last 24h (14/15) | stage v05_levels.live pass rate dropped to 93.33% in last 24h (14/15) | stage v06_trendlines.live pass rate dropped to 93.33% in last 24h (14/15) | stage v07_volume.live pass rate dropped to 93.33% in last 24h (14/15) | stage v08_ribbon.live pass rate dropped to 93.33% in last 24h (14/15) | stage v09_regime.live pass rate dropped to 93.33% in last 24h (14/15) | stage v10_divergence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v11_breakout.live pass rate dropped to 93.33% in last 24h (14/15) | stage v12_multi_timeframe.live pass rate dropped to 93.33% in last 24h (14/15) | stage v14_sweep.live pass rate dropped to 93.33% in last 24h (14/15) | stage v15_three_source_parity.live pass rate dropped to 93.33% in last 24h (14/15) | stage v46_market_structure.live pass rate dropped to 93.33% in last 24h (14/15) | stage v50_confluence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v51_structure_veto_gate.live pass rate dropped to 93.33% in last 24h (14/15) | stage v52_trendline_break.live pass rate dropped to 93.33% in last 24h (14/15) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/15) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 09:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 10:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T16:27:01.914749+00:00) | fail streak: 99 consecutive fires | stage v01_closed_bar.live pass rate dropped to 93.33% in last 24h (14/15) | stage v02_source_parity pass rate dropped to 73.33% in last 24h (11/15) | stage v03_indicators.live pass rate dropped to 93.33% in last 24h (14/15) | stage v04_candlesticks.live pass rate dropped to 93.33% in last 24h (14/15) | stage v05_levels.live pass rate dropped to 93.33% in last 24h (14/15) | stage v06_trendlines.live pass rate dropped to 93.33% in last 24h (14/15) | stage v07_volume.live pass rate dropped to 93.33% in last 24h (14/15) | stage v08_ribbon.live pass rate dropped to 93.33% in last 24h (14/15) | stage v09_regime.live pass rate dropped to 93.33% in last 24h (14/15) | stage v10_divergence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v11_breakout.live pass rate dropped to 93.33% in last 24h (14/15) | stage v12_multi_timeframe.live pass rate dropped to 93.33% in last 24h (14/15) | stage v14_sweep.live pass rate dropped to 93.33% in last 24h (14/15) | stage v15_three_source_parity.live pass rate dropped to 93.33% in last 24h (14/15) | stage v46_market_structure.live pass rate dropped to 93.33% in last 24h (14/15) | stage v50_confluence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v51_structure_veto_gate.live pass rate dropped to 93.33% in last 24h (14/15) | stage v52_trendline_break.live pass rate dropped to 93.33% in last 24h (14/15) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/15) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 10:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 10:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T16:57:03.205720+00:00) | fail streak: 100 consecutive fires | stage v01_closed_bar.live pass rate dropped to 93.33% in last 24h (14/15) | stage v02_source_parity pass rate dropped to 73.33% in last 24h (11/15) | stage v03_indicators.live pass rate dropped to 93.33% in last 24h (14/15) | stage v04_candlesticks.live pass rate dropped to 93.33% in last 24h (14/15) | stage v05_levels.live pass rate dropped to 93.33% in last 24h (14/15) | stage v06_trendlines.live pass rate dropped to 93.33% in last 24h (14/15) | stage v07_volume.live pass rate dropped to 93.33% in last 24h (14/15) | stage v08_ribbon.live pass rate dropped to 93.33% in last 24h (14/15) | stage v09_regime.live pass rate dropped to 93.33% in last 24h (14/15) | stage v10_divergence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v11_breakout.live pass rate dropped to 93.33% in last 24h (14/15) | stage v12_multi_timeframe.live pass rate dropped to 93.33% in last 24h (14/15) | stage v14_sweep.live pass rate dropped to 93.33% in last 24h (14/15) | stage v15_three_source_parity.live pass rate dropped to 93.33% in last 24h (14/15) | stage v46_market_structure.live pass rate dropped to 93.33% in last 24h (14/15) | stage v50_confluence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v51_structure_veto_gate.live pass rate dropped to 93.33% in last 24h (14/15) | stage v52_trendline_break.live pass rate dropped to 93.33% in last 24h (14/15) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/15) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 10:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 11:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T17:27:03.741384+00:00) | fail streak: 101 consecutive fires | stage v01_closed_bar.live pass rate dropped to 93.33% in last 24h (14/15) | stage v02_source_parity pass rate dropped to 73.33% in last 24h (11/15) | stage v03_indicators.live pass rate dropped to 93.33% in last 24h (14/15) | stage v04_candlesticks.live pass rate dropped to 93.33% in last 24h (14/15) | stage v05_levels.live pass rate dropped to 93.33% in last 24h (14/15) | stage v06_trendlines.live pass rate dropped to 93.33% in last 24h (14/15) | stage v07_volume.live pass rate dropped to 93.33% in last 24h (14/15) | stage v08_ribbon.live pass rate dropped to 93.33% in last 24h (14/15) | stage v09_regime.live pass rate dropped to 93.33% in last 24h (14/15) | stage v10_divergence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v11_breakout.live pass rate dropped to 93.33% in last 24h (14/15) | stage v12_multi_timeframe.live pass rate dropped to 93.33% in last 24h (14/15) | stage v14_sweep.live pass rate dropped to 93.33% in last 24h (14/15) | stage v15_three_source_parity.live pass rate dropped to 93.33% in last 24h (14/15) | stage v46_market_structure.live pass rate dropped to 93.33% in last 24h (14/15) | stage v50_confluence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v51_structure_veto_gate.live pass rate dropped to 93.33% in last 24h (14/15) | stage v52_trendline_break.live pass rate dropped to 93.33% in last 24h (14/15) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/15) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 11:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 11:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T17:57:03.731461+00:00) | fail streak: 102 consecutive fires | stage v01_closed_bar.live pass rate dropped to 93.33% in last 24h (14/15) | stage v02_source_parity pass rate dropped to 73.33% in last 24h (11/15) | stage v03_indicators.live pass rate dropped to 93.33% in last 24h (14/15) | stage v04_candlesticks.live pass rate dropped to 93.33% in last 24h (14/15) | stage v05_levels.live pass rate dropped to 93.33% in last 24h (14/15) | stage v06_trendlines.live pass rate dropped to 93.33% in last 24h (14/15) | stage v07_volume.live pass rate dropped to 93.33% in last 24h (14/15) | stage v08_ribbon.live pass rate dropped to 93.33% in last 24h (14/15) | stage v09_regime.live pass rate dropped to 93.33% in last 24h (14/15) | stage v10_divergence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v11_breakout.live pass rate dropped to 93.33% in last 24h (14/15) | stage v12_multi_timeframe.live pass rate dropped to 93.33% in last 24h (14/15) | stage v14_sweep.live pass rate dropped to 93.33% in last 24h (14/15) | stage v15_three_source_parity.live pass rate dropped to 93.33% in last 24h (14/15) | stage v46_market_structure.live pass rate dropped to 93.33% in last 24h (14/15) | stage v50_confluence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v51_structure_veto_gate.live pass rate dropped to 93.33% in last 24h (14/15) | stage v52_trendline_break.live pass rate dropped to 93.33% in last 24h (14/15) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/15) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 11:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 12:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T18:27:03.626606+00:00) | fail streak: 103 consecutive fires | stage v01_closed_bar.live pass rate dropped to 93.33% in last 24h (14/15) | stage v02_source_parity pass rate dropped to 73.33% in last 24h (11/15) | stage v03_indicators.live pass rate dropped to 93.33% in last 24h (14/15) | stage v04_candlesticks.live pass rate dropped to 93.33% in last 24h (14/15) | stage v05_levels.live pass rate dropped to 93.33% in last 24h (14/15) | stage v06_trendlines.live pass rate dropped to 93.33% in last 24h (14/15) | stage v07_volume.live pass rate dropped to 93.33% in last 24h (14/15) | stage v08_ribbon.live pass rate dropped to 93.33% in last 24h (14/15) | stage v09_regime.live pass rate dropped to 93.33% in last 24h (14/15) | stage v10_divergence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v11_breakout.live pass rate dropped to 93.33% in last 24h (14/15) | stage v12_multi_timeframe.live pass rate dropped to 93.33% in last 24h (14/15) | stage v14_sweep.live pass rate dropped to 93.33% in last 24h (14/15) | stage v15_three_source_parity.live pass rate dropped to 93.33% in last 24h (14/15) | stage v46_market_structure.live pass rate dropped to 93.33% in last 24h (14/15) | stage v50_confluence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v51_structure_veto_gate.live pass rate dropped to 93.33% in last 24h (14/15) | stage v52_trendline_break.live pass rate dropped to 93.33% in last 24h (14/15) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/15) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 12:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 12:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T18:57:03.620375+00:00) | fail streak: 104 consecutive fires | stage v01_closed_bar.live pass rate dropped to 93.33% in last 24h (14/15) | stage v02_source_parity pass rate dropped to 73.33% in last 24h (11/15) | stage v03_indicators.live pass rate dropped to 93.33% in last 24h (14/15) | stage v04_candlesticks.live pass rate dropped to 93.33% in last 24h (14/15) | stage v05_levels.live pass rate dropped to 93.33% in last 24h (14/15) | stage v06_trendlines.live pass rate dropped to 93.33% in last 24h (14/15) | stage v07_volume.live pass rate dropped to 93.33% in last 24h (14/15) | stage v08_ribbon.live pass rate dropped to 93.33% in last 24h (14/15) | stage v09_regime.live pass rate dropped to 93.33% in last 24h (14/15) | stage v10_divergence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v11_breakout.live pass rate dropped to 93.33% in last 24h (14/15) | stage v12_multi_timeframe.live pass rate dropped to 93.33% in last 24h (14/15) | stage v14_sweep.live pass rate dropped to 93.33% in last 24h (14/15) | stage v15_three_source_parity.live pass rate dropped to 93.33% in last 24h (14/15) | stage v46_market_structure.live pass rate dropped to 93.33% in last 24h (14/15) | stage v50_confluence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v51_structure_veto_gate.live pass rate dropped to 93.33% in last 24h (14/15) | stage v52_trendline_break.live pass rate dropped to 93.33% in last 24h (14/15) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/15) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 12:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 13:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T19:27:03.638347+00:00) | fail streak: 105 consecutive fires | stage v01_closed_bar.live pass rate dropped to 93.33% in last 24h (14/15) | stage v02_source_parity pass rate dropped to 73.33% in last 24h (11/15) | stage v03_indicators.live pass rate dropped to 93.33% in last 24h (14/15) | stage v04_candlesticks.live pass rate dropped to 93.33% in last 24h (14/15) | stage v05_levels.live pass rate dropped to 93.33% in last 24h (14/15) | stage v06_trendlines.live pass rate dropped to 93.33% in last 24h (14/15) | stage v07_volume.live pass rate dropped to 93.33% in last 24h (14/15) | stage v08_ribbon.live pass rate dropped to 93.33% in last 24h (14/15) | stage v09_regime.live pass rate dropped to 93.33% in last 24h (14/15) | stage v10_divergence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v11_breakout.live pass rate dropped to 93.33% in last 24h (14/15) | stage v12_multi_timeframe.live pass rate dropped to 93.33% in last 24h (14/15) | stage v14_sweep.live pass rate dropped to 93.33% in last 24h (14/15) | stage v15_three_source_parity.live pass rate dropped to 93.33% in last 24h (14/15) | stage v46_market_structure.live pass rate dropped to 93.33% in last 24h (14/15) | stage v50_confluence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v51_structure_veto_gate.live pass rate dropped to 93.33% in last 24h (14/15) | stage v52_trendline_break.live pass rate dropped to 93.33% in last 24h (14/15) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/15) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 13:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 13:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T19:57:03.652819+00:00) | fail streak: 106 consecutive fires | stage v01_closed_bar.live pass rate dropped to 93.75% in last 24h (15/16) | stage v02_source_parity pass rate dropped to 75.0% in last 24h (12/16) | stage v03_indicators.live pass rate dropped to 93.75% in last 24h (15/16) | stage v04_candlesticks.live pass rate dropped to 93.75% in last 24h (15/16) | stage v05_levels.live pass rate dropped to 93.75% in last 24h (15/16) | stage v06_trendlines.live pass rate dropped to 93.75% in last 24h (15/16) | stage v07_volume.live pass rate dropped to 93.75% in last 24h (15/16) | stage v08_ribbon.live pass rate dropped to 93.75% in last 24h (15/16) | stage v09_regime.live pass rate dropped to 93.75% in last 24h (15/16) | stage v10_divergence.live pass rate dropped to 93.75% in last 24h (15/16) | stage v11_breakout.live pass rate dropped to 93.75% in last 24h (15/16) | stage v12_multi_timeframe.live pass rate dropped to 93.75% in last 24h (15/16) | stage v14_sweep.live pass rate dropped to 93.75% in last 24h (15/16) | stage v15_three_source_parity.live pass rate dropped to 93.75% in last 24h (15/16) | stage v46_market_structure.live pass rate dropped to 93.75% in last 24h (15/16) | stage v50_confluence.live pass rate dropped to 93.75% in last 24h (15/16) | stage v51_structure_veto_gate.live pass rate dropped to 93.75% in last 24h (15/16) | stage v52_trendline_break.live pass rate dropped to 93.75% in last 24h (15/16) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/16) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 13:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 14:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T20:27:03.618132+00:00) | fail streak: 107 consecutive fires | stage v01_closed_bar.live pass rate dropped to 94.12% in last 24h (16/17) | stage v02_source_parity pass rate dropped to 76.47% in last 24h (13/17) | stage v03_indicators.live pass rate dropped to 94.12% in last 24h (16/17) | stage v04_candlesticks.live pass rate dropped to 94.12% in last 24h (16/17) | stage v05_levels.live pass rate dropped to 94.12% in last 24h (16/17) | stage v06_trendlines.live pass rate dropped to 94.12% in last 24h (16/17) | stage v07_volume.live pass rate dropped to 94.12% in last 24h (16/17) | stage v08_ribbon.live pass rate dropped to 94.12% in last 24h (16/17) | stage v09_regime.live pass rate dropped to 94.12% in last 24h (16/17) | stage v10_divergence.live pass rate dropped to 94.12% in last 24h (16/17) | stage v11_breakout.live pass rate dropped to 94.12% in last 24h (16/17) | stage v12_multi_timeframe.live pass rate dropped to 94.12% in last 24h (16/17) | stage v14_sweep.live pass rate dropped to 94.12% in last 24h (16/17) | stage v15_three_source_parity.live pass rate dropped to 94.12% in last 24h (16/17) | stage v46_market_structure.live pass rate dropped to 94.12% in last 24h (16/17) | stage v50_confluence.live pass rate dropped to 94.12% in last 24h (16/17) | stage v51_structure_veto_gate.live pass rate dropped to 94.12% in last 24h (16/17) | stage v52_trendline_break.live pass rate dropped to 94.12% in last 24h (16/17) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/17) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 14:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 14:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T20:57:03.571807+00:00) | fail streak: 108 consecutive fires | stage v01_closed_bar.live pass rate dropped to 94.44% in last 24h (17/18) | stage v02_source_parity pass rate dropped to 77.78% in last 24h (14/18) | stage v03_indicators.live pass rate dropped to 94.44% in last 24h (17/18) | stage v04_candlesticks.live pass rate dropped to 94.44% in last 24h (17/18) | stage v05_levels.live pass rate dropped to 94.44% in last 24h (17/18) | stage v06_trendlines.live pass rate dropped to 94.44% in last 24h (17/18) | stage v07_volume.live pass rate dropped to 94.44% in last 24h (17/18) | stage v08_ribbon.live pass rate dropped to 94.44% in last 24h (17/18) | stage v09_regime.live pass rate dropped to 94.44% in last 24h (17/18) | stage v10_divergence.live pass rate dropped to 94.44% in last 24h (17/18) | stage v11_breakout.live pass rate dropped to 94.44% in last 24h (17/18) | stage v12_multi_timeframe.live pass rate dropped to 94.44% in last 24h (17/18) | stage v14_sweep.live pass rate dropped to 94.44% in last 24h (17/18) | stage v15_three_source_parity.live pass rate dropped to 94.44% in last 24h (17/18) | stage v46_market_structure.live pass rate dropped to 94.44% in last 24h (17/18) | stage v50_confluence.live pass rate dropped to 94.44% in last 24h (17/18) | stage v51_structure_veto_gate.live pass rate dropped to 94.44% in last 24h (17/18) | stage v52_trendline_break.live pass rate dropped to 94.44% in last 24h (17/18) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/18) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 14:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 15:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T21:27:03.581796+00:00) | fail streak: 109 consecutive fires | stage v01_closed_bar.live pass rate dropped to 94.74% in last 24h (18/19) | stage v02_source_parity pass rate dropped to 78.95% in last 24h (15/19) | stage v03_indicators.live pass rate dropped to 94.74% in last 24h (18/19) | stage v04_candlesticks.live pass rate dropped to 94.74% in last 24h (18/19) | stage v05_levels.live pass rate dropped to 94.74% in last 24h (18/19) | stage v06_trendlines.live pass rate dropped to 94.74% in last 24h (18/19) | stage v07_volume.live pass rate dropped to 94.74% in last 24h (18/19) | stage v08_ribbon.live pass rate dropped to 94.74% in last 24h (18/19) | stage v09_regime.live pass rate dropped to 94.74% in last 24h (18/19) | stage v10_divergence.live pass rate dropped to 94.74% in last 24h (18/19) | stage v11_breakout.live pass rate dropped to 94.74% in last 24h (18/19) | stage v12_multi_timeframe.live pass rate dropped to 94.74% in last 24h (18/19) | stage v14_sweep.live pass rate dropped to 94.74% in last 24h (18/19) | stage v15_three_source_parity.live pass rate dropped to 94.74% in last 24h (18/19) | stage v46_market_structure.live pass rate dropped to 94.74% in last 24h (18/19) | stage v50_confluence.live pass rate dropped to 94.74% in last 24h (18/19) | stage v51_structure_veto_gate.live pass rate dropped to 94.74% in last 24h (18/19) | stage v52_trendline_break.live pass rate dropped to 94.74% in last 24h (18/19) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/19) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 15:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 15:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T21:57:03.613416+00:00) | fail streak: 110 consecutive fires | stage v02_source_parity pass rate dropped to 80.0% in last 24h (16/20) -- but v15 (3-source) = 95.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/20) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 15:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 16:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T22:27:03.625455+00:00) | fail streak: 111 consecutive fires | stage v02_source_parity pass rate dropped to 80.95% in last 24h (17/21) -- but v15 (3-source) = 95.24% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/21) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 16:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 16:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T22:57:03.632696+00:00) | fail streak: 112 consecutive fires | stage v02_source_parity pass rate dropped to 81.82% in last 24h (18/22) -- but v15 (3-source) = 95.45% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/22) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 16:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 17:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T23:27:03.721596+00:00) | fail streak: 113 consecutive fires | stage v02_source_parity pass rate dropped to 82.61% in last 24h (19/23) -- but v15 (3-source) = 95.65% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/23) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 17:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 17:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T23:57:03.589061+00:00) | fail streak: 114 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (20/24) -- but v15 (3-source) = 95.83% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/24) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 17:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 18:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-05T00:27:03.649795+00:00) | fail streak: 115 consecutive fires | stage v02_source_parity pass rate dropped to 84.0% in last 24h (21/25) -- but v15 (3-source) = 96.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/25) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 18:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 18:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-05T00:57:03.675242+00:00) | fail streak: 116 consecutive fires | stage v02_source_parity pass rate dropped to 84.62% in last 24h (22/26) -- but v15 (3-source) = 96.15% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/26) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 18:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 19:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-05T01:27:03.646668+00:00) | fail streak: 117 consecutive fires | stage v02_source_parity pass rate dropped to 85.19% in last 24h (23/27) -- but v15 (3-source) = 96.3% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/27) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 19:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 19:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-05T01:57:03.652310+00:00) | fail streak: 118 consecutive fires | stage v02_source_parity pass rate dropped to 85.71% in last 24h (24/28) -- but v15 (3-source) = 96.43% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/28) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 19:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 20:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-05T02:27:03.684220+00:00) | fail streak: 119 consecutive fires | stage v02_source_parity pass rate dropped to 86.21% in last 24h (25/29) -- but v15 (3-source) = 96.55% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/29) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 20:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 20:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-05T02:57:03.413016+00:00) | fail streak: 120 consecutive fires | stage v02_source_parity pass rate dropped to 86.67% in last 24h (26/30) -- but v15 (3-source) = 96.67% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/30) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 20:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 21:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-05T03:27:03.351932+00:00) | fail streak: 121 consecutive fires | stage v02_source_parity pass rate dropped to 86.67% in last 24h (26/30) -- but v15 (3-source) = 96.67% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/30) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 21:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 21:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-05T03:57:03.383170+00:00) | fail streak: 122 consecutive fires | stage v02_source_parity pass rate dropped to 86.67% in last 24h (26/30) -- but v15 (3-source) = 96.67% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/30) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 21:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 22:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-05T04:27:03.501210+00:00) | fail streak: 123 consecutive fires | stage v02_source_parity pass rate dropped to 86.67% in last 24h (26/30) -- but v15 (3-source) = 96.67% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/30) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 22:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

### DEGRADED: self-check 2026-07-06T09:43:26
- Gamma_LevelRefresh STALE in RTH: key-levels.json 1985m old (should be <10m). Engine may be blind to live structure.
- Gamma_SightBeacon STALE in RTH: beacon 2473m old (should be <2m). Engine eye may be dark.
- Gamma_HeartbeatCore STALE in RTH: last decision 3956m ago (should be ~1m). Engine may not be ticking.
- PREMARKET STALE: today-bias.json date=2026-07-03 != today 2026-07-06 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

- [2026-07-06 07:43:26] scheduled-tasks audit RED -- see automation/state/scheduled-tasks-audit.json

- [2026-07-06 07:43:27] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T13:43:42.257022+00:00) | fail streak: 124 consecutive fires :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 07:43:27] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

[2026-07-06 07:43:26] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-07-06.md

### BROKEN: self-check 2026-07-06T10:09:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 08:13:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T14:13:27.984737+00:00) | fail streak: 125 consecutive fires :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 08:13:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T10:39:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 08:43:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T14:43:28.143561+00:00) | fail streak: 126 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/3) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 08:43:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T11:09:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 09:13:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T15:13:27.852825+00:00) | fail streak: 127 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/4) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 09:13:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T11:39:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 09:43:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T15:43:27.956680+00:00) | fail streak: 128 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/5) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 09:43:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T12:09:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 10:13:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T16:13:27.627837+00:00) | fail streak: 129 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/6) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 10:13:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T12:39:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 10:43:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T16:43:27.934672+00:00) | fail streak: 130 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/7) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 10:43:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 10:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T16:57:02.415097+00:00) | fail streak: 131 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/8) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 10:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T13:09:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 11:13:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T17:13:27.651872+00:00) | fail streak: 132 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/9) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 11:13:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 11:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T17:27:02.929082+00:00) | fail streak: 133 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/10) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 11:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T13:39:56
- ENGINE CANNOT ENTER: 238 ticks today, 0 ENTER, 3x SKIP_STRUCTURE_VETO -- setups scored AND fired a trigger but every entry was gate-blocked by a NON-data-gated verdict. The engine is structurally sitting out (the 2026-06-30 zero-trade signature).
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 11:43:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T17:43:27.932233+00:00) | fail streak: 134 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/11) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 11:43:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 11:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T17:57:02.927690+00:00) | fail streak: 135 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/12) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 11:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T14:09:56
- ENGINE CANNOT ENTER: 268 ticks today, 0 ENTER, 3x SKIP_STRUCTURE_VETO -- setups scored AND fired a trigger but every entry was gate-blocked by a NON-data-gated verdict. The engine is structurally sitting out (the 2026-06-30 zero-trade signature).
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 12:13:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T18:13:27.737506+00:00) | fail streak: 136 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/13) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 12:13:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 12:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T18:27:02.898476+00:00) | fail streak: 137 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/14) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 12:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T14:39:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 12:43:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T18:43:27.815245+00:00) | fail streak: 138 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/15) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 12:43:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 12:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T18:57:02.845483+00:00) | fail streak: 139 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/16) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 12:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T15:09:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 13:13:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T19:13:27.773335+00:00) | fail streak: 140 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/17) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 13:13:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 13:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T19:27:02.853759+00:00) | fail streak: 141 consecutive fires | stage v02_source_parity pass rate dropped to 94.44% in last 24h (17/18) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/18) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 13:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T15:39:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 13:43:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T19:43:28.149761+00:00) | fail streak: 142 consecutive fires | stage v02_source_parity pass rate dropped to 94.74% in last 24h (18/19) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/19) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 13:43:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 13:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T19:57:02.851238+00:00) | fail streak: 143 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/20) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 13:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### INFO: eod-analytics eod-summary used free-tier model (free-tier-primary)
- ts: 2026-07-06T20:00:35+00:00
- task: eod-summary
- date_et: 2026-07-06
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

### BROKEN: self-check 2026-07-06T16:09:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 14:13:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T20:13:27.643460+00:00) | fail streak: 144 consecutive fires | stage v02_source_parity pass rate dropped to 90.48% in last 24h (19/21) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/21) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 14:13:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 14:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T20:27:02.876824+00:00) | fail streak: 145 consecutive fires | stage v02_source_parity pass rate dropped to 86.36% in last 24h (19/22) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/22) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 14:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T16:39:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 14:43:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T20:43:28.008736+00:00) | fail streak: 146 consecutive fires | stage v02_source_parity pass rate dropped to 82.61% in last 24h (19/23) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/23) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 14:43:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### INFO: eod-analytics analyst used free-tier model (free-tier-primary)
- ts: 2026-07-06T20:45:42+00:00
- task: analyst
- date_et: 2026-07-06
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000
- [07-06 09:58 ET] TvWatchdog: tv=relaunch_kill heartbeat=STALE_47min TV up but CDP dead for 833s - kill+relaunch

- [2026-07-06 14:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T20:57:03.012059+00:00) | fail streak: 147 consecutive fires | stage v02_source_parity pass rate dropped to 79.17% in last 24h (19/24) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/24) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 14:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 21:00:01] gym-session (2026-07-06) → **RED** :: see `automation\state\gym-scorecard-2026-07-06.json`
### BROKEN: self-check 2026-07-06T17:09:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 15:13:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T21:13:27.757864+00:00) | fail streak: 148 consecutive fires | stage v02_source_parity pass rate dropped to 76.0% in last 24h (19/25) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/25) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 15:13:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 15:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T21:27:02.894166+00:00) | fail streak: 149 consecutive fires | stage v02_source_parity pass rate dropped to 73.08% in last 24h (19/26) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/26) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 15:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### INFO: eod-analytics manager used free-tier model (free-tier-primary)
- ts: 2026-07-06T21:30:45+00:00
- task: manager
- date_et: 2026-07-06
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

### BROKEN: self-check 2026-07-06T17:39:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 15:43:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T21:43:27.766806+00:00) | fail streak: 150 consecutive fires | stage v02_source_parity pass rate dropped to 70.37% in last 24h (19/27) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/27) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 15:43:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 15:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T21:57:02.927620+00:00) | fail streak: 151 consecutive fires | stage v02_source_parity pass rate dropped to 67.86% in last 24h (19/28) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/28) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 15:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T18:09:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 16:13:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T22:13:27.478806+00:00) | fail streak: 152 consecutive fires | stage v02_source_parity pass rate dropped to 65.52% in last 24h (19/29) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/29) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 16:13:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 16:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T22:27:02.923368+00:00) | fail streak: 153 consecutive fires | stage v02_source_parity pass rate dropped to 63.33% in last 24h (19/30) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/30) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 16:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T18:39:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 16:43:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T22:43:27.673307+00:00) | fail streak: 154 consecutive fires | stage v02_source_parity pass rate dropped to 61.29% in last 24h (19/31) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/31) | v02 source parity drift in 30.77% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 16:43:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 16:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T22:57:02.879942+00:00) | fail streak: 155 consecutive fires | stage v02_source_parity pass rate dropped to 62.5% in last 24h (20/32) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/32) | v02 source parity drift in 31.2% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 16:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T19:09:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 17:13:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T23:13:27.600075+00:00) | fail streak: 156 consecutive fires | stage v02_source_parity pass rate dropped to 63.64% in last 24h (21/33) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/33) | v02 source parity drift in 30.29% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 17:13:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 17:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T23:27:02.907545+00:00) | fail streak: 157 consecutive fires | stage v02_source_parity pass rate dropped to 64.71% in last 24h (22/34) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/34) | v02 source parity drift in 30.36% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 17:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T19:39:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 17:43:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T23:43:27.825631+00:00) | fail streak: 158 consecutive fires | stage v02_source_parity pass rate dropped to 65.71% in last 24h (23/35) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/35) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 17:43:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 17:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T23:57:02.908278+00:00) | fail streak: 159 consecutive fires | stage v02_source_parity pass rate dropped to 66.67% in last 24h (24/36) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/36) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 17:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T20:09:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 18:13:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T00:13:27.586047+00:00) | fail streak: 160 consecutive fires | stage v02_source_parity pass rate dropped to 64.86% in last 24h (24/37) -- but v15 (3-source) = 97.3% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/37) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 18:13:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 18:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T00:27:02.886999+00:00) | fail streak: 161 consecutive fires | stage v02_source_parity pass rate dropped to 65.79% in last 24h (25/38) -- but v15 (3-source) = 97.37% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/38) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 18:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T20:39:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 18:43:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T00:43:27.491083+00:00) | fail streak: 162 consecutive fires | stage v02_source_parity pass rate dropped to 64.1% in last 24h (25/39) -- but v15 (3-source) = 97.44% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/39) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 18:43:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 18:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T00:57:02.909367+00:00) | fail streak: 163 consecutive fires | stage v02_source_parity pass rate dropped to 62.5% in last 24h (25/40) -- but v15 (3-source) = 97.5% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/40) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 18:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### DEGRADED: self-check 2026-07-06T21:09:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']

- [2026-07-06 19:13:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T01:13:27.505098+00:00) | fail streak: 164 consecutive fires | stage v02_source_parity pass rate dropped to 60.98% in last 24h (25/41) -- but v15 (3-source) = 97.56% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/41) | v02 source parity drift in 30.72% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 19:13:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 19:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T01:27:02.912312+00:00) | fail streak: 165 consecutive fires | stage v02_source_parity pass rate dropped to 59.52% in last 24h (25/42) -- but v15 (3-source) = 97.62% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/42) | v02 source parity drift in 31.95% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 19:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### DEGRADED: self-check 2026-07-06T21:39:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']

- [2026-07-06 19:43:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T01:43:28.724100+00:00) | fail streak: 166 consecutive fires | stage v02_source_parity pass rate dropped to 58.14% in last 24h (25/43) -- but v15 (3-source) = 97.67% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/43) | v02 source parity drift in 33.72% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 19:43:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 19:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T01:57:02.907033+00:00) | fail streak: 167 consecutive fires | stage v02_source_parity pass rate dropped to 56.82% in last 24h (25/44) -- but v15 (3-source) = 97.73% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/44) | v02 source parity drift in 34.56% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 19:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### DEGRADED: self-check 2026-07-06T22:09:57
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']

- [2026-07-06 20:13:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T02:13:28.972693+00:00) | fail streak: 168 consecutive fires | stage v02_source_parity pass rate dropped to 57.78% in last 24h (26/45) -- but v15 (3-source) = 97.78% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/45) | v02 source parity drift in 35.46% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 20:13:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 20:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T02:27:01.673840+00:00) | fail streak: 169 consecutive fires | stage v02_source_parity pass rate dropped to 58.7% in last 24h (27/46) -- but v15 (3-source) = 97.83% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/46) | v02 source parity drift in 34.88% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 20:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### DEGRADED: self-check 2026-07-06T22:39:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']

- [2026-07-06 20:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T02:57:01.771810+00:00) | fail streak: 170 consecutive fires | stage v02_source_parity pass rate dropped to 59.57% in last 24h (28/47) -- but v15 (3-source) = 97.87% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/47) | v02 source parity drift in 33.6% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 20:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### DEGRADED: self-check 2026-07-06T23:09:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']

- [2026-07-06 21:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T03:27:02.022532+00:00) | fail streak: 171 consecutive fires | stage v02_source_parity pass rate dropped to 58.33% in last 24h (28/48) -- but v15 (3-source) = 97.92% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) | v02 source parity drift in 34.09% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 21:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### WARN: spend-summary threshold breach
- ts: 2026-07-07T03:30:06+00:00
- date_et: 2026-07-06
- total: $190.19 (threshold $30.00)
- claude: $189.48  minimax: $0.04
- claude_sessions: 14

### DEGRADED: self-check 2026-07-06T23:39:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']

- [2026-07-06 21:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T03:57:01.695157+00:00) | fail streak: 172 consecutive fires | stage v02_source_parity pass rate dropped to 57.14% in last 24h (28/49) -- but v15 (3-source) = 97.96% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/49) | v02 source parity drift in 35.61% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 21:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-07 06:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T12:57:01.637833+00:00) | fail streak: 173 consecutive fires | stage v02_source_parity pass rate dropped to 58.0% in last 24h (29/50) -- but v15 (3-source) = 98.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/50) | v02 source parity drift in 35.84% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 06:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### DEGRADED: self-check 2026-07-07T08:58:54
- PREMARKET STALE: today-bias.json date=2026-07-06 != today 2026-07-07 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

[2026-07-07 06:58:54] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-07-07.md
- [07-07 09:13 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 827s - kill+relaunch
- [07-07 09:18 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 1127s - kill+relaunch
- [07-07 09:23 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 1427s - kill+relaunch

- [2026-07-07 07:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T13:27:01.727254+00:00) | fail streak: 174 consecutive fires | stage v02_source_parity pass rate dropped to 58.82% in last 24h (30/51) -- but v15 (3-source) = 98.04% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) | v02 source parity drift in 34.58% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 07:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 09:28 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 1727s - kill+relaunch
- [07-07 09:33 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 2027s - kill+relaunch
- [07-07 09:38 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 2327s - kill+relaunch
- [07-07 09:48 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 372s - kill+relaunch
- [07-07 09:53 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 672s - kill+relaunch

- [2026-07-07 07:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T13:57:01.972249+00:00) | fail streak: 175 consecutive fires | stage v02_source_parity pass rate dropped to 58.82% in last 24h (30/51) -- but v15 (3-source) = 98.04% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) | v02 source parity drift in 34.02% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 07:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 09:58 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 973s - kill+relaunch
- [07-07 10:03 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 1273s - kill+relaunch
- [07-07 10:08 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 1572s - kill+relaunch
- [07-07 10:13 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 1872s - kill+relaunch
- [07-07 10:18 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 2172s - kill+relaunch
- [07-07 10:23 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 2472s - kill+relaunch

- [2026-07-07 08:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T14:27:01.733758+00:00) | fail streak: 176 consecutive fires | stage v02_source_parity pass rate dropped to 56.86% in last 24h (29/51) -- but v15 (3-source) = 98.04% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) | v02 source parity drift in 35.86% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 08:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 10:28 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 2772s - kill+relaunch
- [07-07 10:33 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 3072s - kill+relaunch
- [07-07 10:38 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 3372s - kill+relaunch
- [07-07 10:43 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 3672s - kill+relaunch
- [07-07 10:48 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 3972s - kill+relaunch
- [07-07 10:53 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 4272s - kill+relaunch

- [2026-07-07 08:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T14:57:01.687942+00:00) | fail streak: 177 consecutive fires | stage v02_source_parity pass rate dropped to 54.9% in last 24h (28/51) -- but v15 (3-source) = 98.04% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) | v02 source parity drift in 39.31% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 08:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 10:58 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 4572s - kill+relaunch
- [07-07 11:03 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 4872s - kill+relaunch
- [07-07 11:08 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 5172s - kill+relaunch

### BROKEN: self-check 2026-07-07T11:09:56
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 5 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- [07-07 11:13 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 5472s - kill+relaunch
- [07-07 11:18 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 5772s - kill+relaunch
- [07-07 11:23 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 6072s - kill+relaunch

- [2026-07-07 09:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T15:27:01.737005+00:00) | fail streak: 178 consecutive fires | stage v02_source_parity pass rate dropped to 52.94% in last 24h (27/51) -- but v15 (3-source) = 98.04% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) | v02 source parity drift in 42.53% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 09:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 11:28 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 6372s - kill+relaunch
- [07-07 11:33 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 6672s - kill+relaunch
- [07-07 11:38 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 6972s - kill+relaunch

### BROKEN: self-check 2026-07-07T11:39:56
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 5 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- [07-07 11:43 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 7272s - kill+relaunch
- [07-07 11:48 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 7572s - kill+relaunch
- [07-07 11:53 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 7872s - kill+relaunch

- [2026-07-07 09:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T15:57:01.726683+00:00) | fail streak: 179 consecutive fires | stage v02_source_parity pass rate dropped to 50.98% in last 24h (26/51) -- but v15 (3-source) = 98.04% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) | v02 source parity drift in 45.16% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 09:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 11:58 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 8172s - kill+relaunch
- [07-07 12:03 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 8472s - kill+relaunch
- [07-07 12:08 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 8772s - kill+relaunch

### BROKEN: self-check 2026-07-07T12:09:56
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 5 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- [07-07 12:13 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 9072s - kill+relaunch
- [07-07 12:18 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 9372s - kill+relaunch
- [07-07 12:23 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 9672s - kill+relaunch

- [2026-07-07 10:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T16:27:01.824786+00:00) | fail streak: 180 consecutive fires | stage v02_source_parity pass rate dropped to 49.02% in last 24h (25/51) -- but v15 (3-source) = 98.04% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) | v02 source parity drift in 48.51% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 10:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 12:28 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 9972s - kill+relaunch
- [07-07 12:33 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 10272s - kill+relaunch
- [07-07 12:38 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 10572s - kill+relaunch

### BROKEN: self-check 2026-07-07T12:39:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 3 ENTER, 3 attempted, 0 broker-accepted. Reasons: 3x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 5 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- [07-07 12:43 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 10872s - kill+relaunch
- [07-07 12:48 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 11172s - kill+relaunch
- [07-07 12:53 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 11472s - kill+relaunch

- [2026-07-07 10:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T16:57:02.962902+00:00) | fail streak: 182 consecutive fires | stage v02_source_parity pass rate dropped to 45.1% in last 24h (23/51) -- but v15 (3-source) = 98.04% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) | v02 source parity drift in 51.72% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 10:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

- [2026-07-07 10:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 12:58 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 11772s - kill+relaunch
- [07-07 13:03 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 12072s - kill+relaunch
- [07-07 13:08 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 12372s - kill+relaunch

### BROKEN: self-check 2026-07-07T13:09:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 3 ENTER, 3 attempted, 0 broker-accepted. Reasons: 3x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 5 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- [07-07 13:13 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 12672s - kill+relaunch
- [07-07 13:18 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 12972s - kill+relaunch
- [07-07 13:23 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 13272s - kill+relaunch

- [2026-07-07 11:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T17:27:03.322205+00:00) | fail streak: 183 consecutive fires | stage v02_source_parity pass rate dropped to 44.0% in last 24h (22/50) -- but v15 (3-source) = 98.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/50) | v02 source parity drift in 53.79% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 11:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 13:28 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 13572s - kill+relaunch
- [07-07 13:33 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 13872s - kill+relaunch
- [07-07 13:38 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 14172s - kill+relaunch

### BROKEN: self-check 2026-07-07T13:39:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 3 ENTER, 3 attempted, 0 broker-accepted. Reasons: 3x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 5 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- [07-07 13:43 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 14472s - kill+relaunch
- [07-07 13:48 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 14772s - kill+relaunch
- [07-07 13:53 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 15072s - kill+relaunch

- [2026-07-07 11:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T17:57:02.457099+00:00) | fail streak: 184 consecutive fires | stage v02_source_parity pass rate dropped to 42.86% in last 24h (21/49) -- but v15 (3-source) = 97.96% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/49) | v02 source parity drift in 53.79% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 11:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 13:58 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 15372s - kill+relaunch
- [07-07 14:03 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 15672s - kill+relaunch
- [07-07 14:08 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 15972s - kill+relaunch

### BROKEN: self-check 2026-07-07T14:09:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 3 ENTER, 3 attempted, 0 broker-accepted. Reasons: 3x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 5 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- [07-07 14:13 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 16272s - kill+relaunch
- [07-07 14:18 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 16572s - kill+relaunch
- [07-07 14:23 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 16872s - kill+relaunch

- [2026-07-07 12:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T18:27:02.462625+00:00) | fail streak: 185 consecutive fires | stage v02_source_parity pass rate dropped to 41.67% in last 24h (20/48) -- but v15 (3-source) = 97.92% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) | v02 source parity drift in 53.92% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 12:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 14:28 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 17172s - kill+relaunch
- [07-07 14:33 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 17472s - kill+relaunch
- [07-07 14:38 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 17772s - kill+relaunch

### BROKEN: self-check 2026-07-07T14:39:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 8 ENTER, 8 attempted, 0 broker-accepted. Reasons: 8x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 5 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- [07-07 14:43 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 18072s - kill+relaunch
- [07-07 14:48 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 18372s - kill+relaunch
- [07-07 14:53 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 18672s - kill+relaunch

- [2026-07-07 12:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T18:57:02.483038+00:00) | fail streak: 186 consecutive fires | stage v02_source_parity pass rate dropped to 40.43% in last 24h (19/47) -- but v15 (3-source) = 97.87% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/47) | v02 source parity drift in 53.56% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 12:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 14:58 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 18973s - kill+relaunch
- [07-07 15:03 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 19272s - kill+relaunch
- [07-07 15:08 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 19572s - kill+relaunch

### BROKEN: self-check 2026-07-07T15:09:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 8 ENTER, 8 attempted, 0 broker-accepted. Reasons: 8x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 5 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- [07-07 15:13 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 19872s - kill+relaunch
- [07-07 15:18 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 20172s - kill+relaunch
- [07-07 15:23 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 20472s - kill+relaunch

- [2026-07-07 13:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T19:27:02.408568+00:00) | fail streak: 187 consecutive fires | stage v02_source_parity pass rate dropped to 39.13% in last 24h (18/46) -- but v15 (3-source) = 97.83% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/46) | v02 source parity drift in 54.71% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 13:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 15:28 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 20772s - kill+relaunch
- [07-07 15:33 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 21072s - kill+relaunch
- [07-07 15:38 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 21372s - kill+relaunch

### BROKEN: self-check 2026-07-07T15:39:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 8 ENTER, 8 attempted, 0 broker-accepted. Reasons: 8x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 5 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- [07-07 15:43 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 21672s - kill+relaunch
- [07-07 15:48 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 21972s - kill+relaunch
- [07-07 15:53 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 22272s - kill+relaunch

- [2026-07-07 13:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T19:57:02.408401+00:00) | fail streak: 188 consecutive fires | stage v02_source_parity pass rate dropped to 35.56% in last 24h (16/45) -- but v15 (3-source) = 97.78% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/45) | v02 source parity drift in 57.83% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 13:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 15:58 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 22572s - kill+relaunch

### INFO: eod-analytics eod-summary used free-tier model (free-tier-primary)
- ts: 2026-07-07T20:00:21+00:00
- task: eod-summary
- date_et: 2026-07-07
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000
- [07-07 16:03 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 22872s - kill+relaunch
- [07-07 16:08 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 23172s - kill+relaunch

### BROKEN: self-check 2026-07-07T16:09:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 8 ENTER, 8 attempted, 0 broker-accepted. Reasons: 8x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 10 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']
- [07-07 16:13 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 23472s - kill+relaunch
- [07-07 16:18 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 23772s - kill+relaunch
- [07-07 16:23 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 24072s - kill+relaunch

- [2026-07-07 14:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T20:27:03.296538+00:00) | fail streak: 189 consecutive fires | stage v02_source_parity pass rate dropped to 36.36% in last 24h (16/44) -- but v15 (3-source) = 95.45% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/44) | v02 source parity drift in 57.83% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 14:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 16:28 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 24372s - kill+relaunch
- [07-07 16:33 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 24672s - kill+relaunch
- [07-07 16:38 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 24972s - kill+relaunch

### BROKEN: self-check 2026-07-07T16:39:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 8 ENTER, 8 attempted, 0 broker-accepted. Reasons: 8x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 10 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']
- [07-07 16:43 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 25272s - kill+relaunch

### INFO: eod-analytics analyst used free-tier model (free-tier-primary)
- ts: 2026-07-07T20:45:14+00:00
- task: analyst
- date_et: 2026-07-07
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000
- [07-07 16:48 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 25572s - kill+relaunch
- [07-07 16:53 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 25872s - kill+relaunch

- [2026-07-07 14:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T20:57:03.321808+00:00) | fail streak: 190 consecutive fires | stage v02_source_parity pass rate dropped to 39.53% in last 24h (17/43) -- but v15 (3-source) = 95.35% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/43) | v02 source parity drift in 55.76% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 14:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

- [2026-07-07 21:00:01] gym-session (2026-07-07) → **RED** :: see `automation\state\gym-scorecard-2026-07-07.json`
### BROKEN: self-check 2026-07-07T17:09:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 8 ENTER, 8 attempted, 0 broker-accepted. Reasons: 8x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 10 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 15:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T21:27:03.545450+00:00) | fail streak: 191 consecutive fires | stage v02_source_parity pass rate dropped to 42.86% in last 24h (18/42) -- but v15 (3-source) = 95.24% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/42) | v02 source parity drift in 52.53% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 15:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### INFO: eod-analytics manager used free-tier model (free-tier-primary)
- ts: 2026-07-07T21:30:32+00:00
- task: manager
- date_et: 2026-07-07
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

### BROKEN: self-check 2026-07-07T17:39:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 8 ENTER, 8 attempted, 0 broker-accepted. Reasons: 8x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 10 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 15:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T21:57:03.594678+00:00) | fail streak: 192 consecutive fires | stage v02_source_parity pass rate dropped to 46.34% in last 24h (19/41) -- but v15 (3-source) = 95.12% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/41) | v02 source parity drift in 49.31% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 15:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### BROKEN: self-check 2026-07-07T18:09:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 8 ENTER, 8 attempted, 0 broker-accepted. Reasons: 8x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 10 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 16:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T22:27:03.527362+00:00) | fail streak: 193 consecutive fires | stage v02_source_parity pass rate dropped to 50.0% in last 24h (20/40) -- but v15 (3-source) = 95.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/40) | v02 source parity drift in 45.85% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 16:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### DEGRADED: self-check 2026-07-07T18:39:57
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 16:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T22:57:03.734286+00:00) | fail streak: 194 consecutive fires | stage v02_source_parity pass rate dropped to 51.28% in last 24h (20/39) | stage v15_three_source_parity.live pass rate dropped to 94.87% in last 24h (37/39) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/39) | v02 source parity drift in 43.32% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 16:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### DEGRADED: self-check 2026-07-07T19:09:57
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 17:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T23:27:03.625589+00:00) | fail streak: 195 consecutive fires | stage v02_source_parity pass rate dropped to 50.0% in last 24h (19/38) | stage v15_three_source_parity.live pass rate dropped to 94.74% in last 24h (36/38) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/38) | v02 source parity drift in 42.86% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 17:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### DEGRADED: self-check 2026-07-07T19:39:56
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 17:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T23:57:03.658909+00:00) | fail streak: 197 consecutive fires | stage v02_source_parity pass rate dropped to 50.0% in last 24h (19/38) | stage v15_three_source_parity.live pass rate dropped to 94.74% in last 24h (36/38) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/38) | v02 source parity drift in 42.86% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 17:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### DEGRADED: self-check 2026-07-07T20:09:57
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 18:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T00:27:03.566269+00:00) | fail streak: 198 consecutive fires | stage v02_source_parity pass rate dropped to 51.35% in last 24h (19/37) -- but v15 (3-source) = 97.3% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/37) | v02 source parity drift in 42.86% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 18:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### DEGRADED: self-check 2026-07-07T20:39:57
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 18:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T00:57:03.322358+00:00) | fail streak: 201 consecutive fires | stage v02_source_parity pass rate dropped to 57.89% in last 24h (22/38) -- but v15 (3-source) = 97.37% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/38) | v02 source parity drift in 40.78% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 18:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### DEGRADED: self-check 2026-07-07T21:09:57
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 19:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T01:27:03.407903+00:00) | fail streak: 202 consecutive fires | stage v02_source_parity pass rate dropped to 62.16% in last 24h (23/37) -- but v15 (3-source) = 97.3% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/37) | v02 source parity drift in 37.56% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 19:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### DEGRADED: self-check 2026-07-07T21:39:57
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 19:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T01:57:03.377938+00:00) | fail streak: 203 consecutive fires | stage v02_source_parity pass rate dropped to 66.67% in last 24h (24/36) -- but v15 (3-source) = 97.22% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/36) | v02 source parity drift in 34.33% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 19:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### DEGRADED: self-check 2026-07-07T22:09:57
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 20:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T02:27:03.813780+00:00) | fail streak: 204 consecutive fires | stage v02_source_parity pass rate dropped to 65.71% in last 24h (23/35) -- but v15 (3-source) = 97.14% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/35) | v02 source parity drift in 32.95% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 20:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### DEGRADED: self-check 2026-07-07T22:39:57
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 20:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T02:57:03.713484+00:00) | fail streak: 205 consecutive fires | stage v02_source_parity pass rate dropped to 65.71% in last 24h (23/35) -- but v15 (3-source) = 97.14% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/35) | v02 source parity drift in 32.87% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 20:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### DEGRADED: self-check 2026-07-07T23:09:57
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 21:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T03:27:03.617558+00:00) | fail streak: 206 consecutive fires | stage v02_source_parity pass rate dropped to 68.57% in last 24h (24/35) -- but v15 (3-source) = 97.14% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/35) | v02 source parity drift in 31.34% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 21:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### WARN: spend-summary threshold breach
- ts: 2026-07-08T03:30:33+00:00
- date_et: 2026-07-07
- total: $780.71 (threshold $30.00)
- claude: $780.67  minimax: $0.04
- claude_sessions: 8

### DEGRADED: self-check 2026-07-07T23:39:57
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 21:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T03:57:03.671139+00:00) | fail streak: 207 consecutive fires | stage v02_source_parity pass rate dropped to 71.43% in last 24h (25/35) -- but v15 (3-source) = 97.14% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/35) :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 21:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

- [2026-07-07 22:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T04:27:03.288932+00:00) | fail streak: 208 consecutive fires | stage v02_source_parity pass rate dropped to 72.22% in last 24h (26/36) -- but v15 (3-source) = 97.22% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/36) :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 22:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

- [2026-07-07 22:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T04:57:03.344302+00:00) | fail streak: 209 consecutive fires | stage v02_source_parity pass rate dropped to 72.97% in last 24h (27/37) -- but v15 (3-source) = 97.3% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/37) :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 22:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
